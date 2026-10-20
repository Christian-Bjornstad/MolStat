"""Private storage paths and a conservative, restartable layout upgrade."""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4

from .backup import verify_database_file
from .database import readonly_uri


@dataclass(frozen=True)
class StorageLayout:
    root: Path

    @property
    def database_path(self) -> Path:
        return self.root / 'database' / 'molstat.sqlite3'

    @property
    def backups_root(self) -> Path:
        return self.root / 'database' / 'backups'

    @property
    def raw_root(self) -> Path:
        return self.root / 'data' / 'raw'

    @property
    def processed_root(self) -> Path:
        return self.root / 'data' / 'processed'


@contextmanager
def _migration_lock(root: Path):
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.ReleaseMutex.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        name = hashlib.sha256(str(root.resolve()).casefold().encode()).hexdigest()
        handle = kernel.CreateMutexW(None, False, f'Local\\MolStatLayout-{name}')
        if not handle:
            raise ValueError('DB_LOCATION: Kunne ikke låse mappeflyttingen.')
        acquired = kernel.WaitForSingleObject(handle, 0) in (0, 0x80)
        try:
            if not acquired:
                raise ValueError('DB_LOCATION: En annen MolStat flytter datamappene.')
            yield
        finally:
            if acquired:
                kernel.ReleaseMutex(handle)
            kernel.CloseHandle(handle)
    else:
        import fcntl
        # A directory descriptor provides a process-scoped lock without a file.
        descriptor = os.open(root, os.O_RDONLY)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        except BlockingIOError as exc:
            raise ValueError('DB_LOCATION: En annen MolStat flytter datamappene.') from exc
        finally:
            os.close(descriptor)


@contextmanager
def _exclusive_source(source: Path):
    if os.name != 'nt':
        with source.open('rb') as stream:
            yield stream
        return
    import ctypes
    from ctypes import wintypes
    import msvcrt
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    kernel.CreateFileW.restype = wintypes.HANDLE
    # FILE_SHARE_DELETE allows our atomic rename while denying every new
    # reader/writer. See Microsoft CreateFileW's dwShareMode contract.
    handle = kernel.CreateFileW(str(source.resolve()), 0x80000000, 4, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    with os.fdopen(descriptor, 'rb') as stream:
        yield stream


def _assert_no_live_job(connection):
    if connection.execute("SELECT 1 FROM sqlite_master WHERE name='writer_lease'").fetchone():
        lease = connection.execute('SELECT expires_at FROM writer_lease WHERE singleton=1').fetchone()
        if lease and datetime.fromisoformat(lease[0]) > datetime.now(timezone.utc):
            raise ValueError('DB_LOCATION: En MolStat-jobb kjører fortsatt. Vent til den er ferdig.')


def _relocate_database(source: Path, layout: StorageLayout) -> None:
    layout.backups_root.mkdir(parents=True, exist_ok=True)
    candidate = layout.backups_root / f'before-layout-{uuid4().hex}.sqlite3'
    try:
        # Fail quickly on live writers/readers instead of waiting or copying WAL
        # incompletely. A verified snapshot is retained before the old file moves.
        with closing(sqlite3.connect(source, timeout=0)) as connection:
            checkpoint = connection.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            if checkpoint and checkpoint[0]:
                raise ValueError('DB_LOCATION: Databasen er i bruk. Lukk andre MolStat-vinduer.')
            connection.execute('BEGIN EXCLUSIVE')
            _assert_no_live_job(connection)
            connection.rollback()
        with _exclusive_source(source) as reader:
            wal = source.with_name(source.name + '-wal')
            journal = source.with_name(source.name + '-journal')
            if any(p.exists() and p.stat().st_size for p in (wal, journal)):
                raise ValueError('DB_LOCATION: Databasen har en aktiv journal. Lukk andre MolStat-vinduer og prøv igjen.')
            with candidate.open('wb') as writer:
                shutil.copyfileobj(reader, writer)
            with candidate.open('r+b') as stream:
                stream.flush()
                os.fsync(stream.fileno())
            verify_database_file(candidate)
            with closing(sqlite3.connect(readonly_uri(candidate, immutable=True), uri=True)) as snapshot:
                _assert_no_live_job(snapshot)
            # Keep the Windows sharing guard until the original changes names.
            source.rename(layout.database_path)
        for suffix in ('-wal', '-shm', '-journal'):
            sidecar = source.with_name(source.name + suffix)
            if sidecar.exists():
                # The connection checkpointed and closed; retain sidecars for
                # recovery rather than silently discard unexplained state.
                sidecar.rename(candidate.with_name(candidate.name + '.retired' + suffix))
    except (sqlite3.Error, OSError) as exc:
        raise ValueError('DB_LOCATION: Kunne ikke flytte databasen. Original eller verifisert sikkerhetskopi er bevart. Lukk andre programmer og prøv igjen.') from exc


def prepare_storage_layout(root: Path) -> StorageLayout:
    layout = StorageLayout(root)
    if not root.is_dir():
        raise ValueError('DB_LOCATION: Velg en eksisterende MolStat-rot.')
    if (root / 'molstat.sqlite3').exists():
        raise ValueError('DB_LOCATION: Velg MolStat-roten, ikke selve databasemappen.')
    source = root / 'data' / 'molstat.sqlite3'
    old_backups = source.parent / 'backups'
    moves = ((root / 'raw', layout.raw_root), (root / 'processed', layout.processed_root))
    if not source.exists() and not old_backups.exists() and not any(old.exists() for old, _ in moves):
        return layout
    with _migration_lock(root):
        # Another process may have completed the upgrade while we acquired it.
        if source.exists() and layout.database_path.exists():
            raise ValueError('DB_LOCATION: Både gammel og ny database finnes. Ingen er overskrevet.')
        for old, new in moves:
            if old.exists() and new.exists():
                raise ValueError('DB_LOCATION: Både gammel og ny datamappe finnes. Ingen filer er overskrevet.')
        if old_backups.exists() and layout.backups_root.exists():
            if any((layout.backups_root / p.name).exists() for p in old_backups.iterdir()):
                raise ValueError('DB_LOCATION: Sikkerhetskopiene har en navnekollisjon.')
        if source.exists():
            _relocate_database(source, layout)
        if old_backups.exists():
            layout.backups_root.mkdir(parents=True, exist_ok=True)
            for entry in old_backups.iterdir():
                entry.rename(layout.backups_root / entry.name)
            old_backups.rmdir()
        for old, new in moves:
            if old.exists():
                new.parent.mkdir(parents=True, exist_ok=True)
                old.rename(new)
    return layout
