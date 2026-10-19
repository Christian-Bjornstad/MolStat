"""Install a complete set of private Power BI CSVs while preserving recovery files."""
from pathlib import Path
import logging
import os
import shutil
import time
from uuid import uuid4

from ._writer_lease import guarded_output
from .failures import RunFailure


def _replace(source, destination, sleep):
    for attempt in range(4):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == 3:
                raise
            sleep(0.25 * 2 ** attempt)


def _copy(source, destination):
    # Copy bytes, not Windows read-only attributes from a downloaded export.
    with source.open('rb') as reader, destination.open('wb') as writer:
        shutil.copyfileobj(reader, writer, 1024 * 1024)
        writer.flush()
        os.fsync(writer.fileno())


def install_private_files(files, destination: Path, *, sleep=time.sleep):
    if any(Path(name).name != name for name in files):
        raise ValueError('Ugyldig privat filnavn.')
    try:
        with guarded_output():
            _install(files, destination, sleep)
    except PermissionError as exc:
        codes = ', '.join(f'{name}={value}' for name in ('errno', 'winerror')
            if isinstance(value := getattr(exc, name, None), int))
        raise RunFailure('PRIVATE_FILES_LOCKED', 'patolog/private_files', detail=codes) from exc


def _install(files, destination, sleep):
    destination.mkdir(parents=True, exist_ok=True)
    staging = destination / ('.molstat-' + uuid4().hex)
    staging.mkdir()
    staged, backups, installed = {}, {}, []
    keep_recovery = False
    try:
        # Prepare every new file and every old copy before replacing the first CSV.
        for index, (name, source) in enumerate(files.items()):
            candidate = staging / f'{index}.new.tmp'
            _copy(source, candidate)
            staged[name] = candidate
            target = destination / name
            if target.exists():
                backup = staging / f'{name}.old.tmp'
                _copy(target, backup)
                backups[name] = backup
        try:
            for name, candidate in staged.items():
                _replace(candidate, destination / name, sleep)
                installed.append(name)
        except BaseException:
            restore_errors = []
            for name in reversed(installed):
                try:
                    if name in backups:
                        _replace(backups[name], destination / name, sleep)
                    else:
                        (destination / name).unlink(missing_ok=True)
                except OSError as exc:
                    restore_errors.append(exc)
            if restore_errors:
                keep_recovery = True
                raise RunFailure('PRIVATE_FILES_RECOVERY', 'patolog/private_files/rollback') from restore_errors[0]
            raise
    finally:
        if not keep_recovery:
            # Only our uniquely named staging directory; no recursive deletions.
            try:
                for path in staging.iterdir():
                    path.unlink()
                staging.rmdir()
            except OSError:
                logging.getLogger(__name__).warning('Private datafiler er behandlet; en midlertidig fil kunne ikke ryddes.')
