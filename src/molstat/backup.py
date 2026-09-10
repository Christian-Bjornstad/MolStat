"""Verified SQLite backup and restore operations for sensitive MolStat data."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from .database import SCHEMA_VERSION, MolStatDatabase


class BackupIntegrityError(RuntimeError):
    """Raised when a database candidate cannot be proven healthy."""


@dataclass(frozen=True, slots=True)
class VerifiedBackup:
    path: Path
    integrity_result: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def verify_database_file(path: Path) -> str:
    """Validate a stable database copy without depending on share locking."""

    candidate = Path(path).resolve()
    if not candidate.is_file():
        raise BackupIntegrityError("Databasefilen finnes ikke.")
    try:
        # Backup candidates are closed, stable files.  ``immutable`` keeps the
        # read-only integrity check independent of advisory locks and journal
        # discovery, which are unreliable on some enterprise network shares.
        uri = candidate.as_uri() + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    except sqlite3.Error as exc:
        error_code = getattr(exc, "sqlite_errorname", "SQLITE_ERROR")
        raise BackupIntegrityError(
            f"Databasefilen kunne ikke valideres ({error_code})."
        ) from exc
    messages = tuple(str(row[0]) for row in rows)
    if messages != ("ok",) or foreign_keys:
        raise BackupIntegrityError("Databasens integritetskontroll feilet.")
    return "ok"


def create_verified_backup(
    database: MolStatDatabase,
    backup_dir: Path,
    *,
    now: Callable[[], datetime] = _utc_now,
) -> VerifiedBackup:
    """Create and validate a consistent backup using SQLite's backup API."""

    destination_dir = Path(backup_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = now().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = destination_dir / f"molstat-{stamp}-{uuid4().hex[:8]}.sqlite3"
    temporary = destination_dir / f".{destination.name}.{uuid4().hex}.tmp"
    try:
        with closing(database._connect()) as source, closing(
            sqlite3.connect(temporary)
        ) as target:
            source.backup(target)
        with temporary.open("r+b") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        integrity = verify_database_file(temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return VerifiedBackup(destination, integrity)


def backup_before_migration(
    database: MolStatDatabase,
    backup_dir: Path,
) -> VerifiedBackup | None:
    """Back up an existing non-current schema before migration starts."""

    source = database.path.resolve()
    if not source.is_file():
        return None
    version: int | None = None
    try:
        uri = source.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            row = connection.execute(
                "SELECT version FROM schema_info LIMIT 1"
            ).fetchone()
            if row is not None:
                version = int(row[0])
    except sqlite3.OperationalError:
        version = None
    if version == SCHEMA_VERSION:
        return None
    return create_verified_backup(database, backup_dir)


def restore_verified_backup(backup_path: Path, destination_path: Path) -> None:
    """Validate a backup, restore to staging, then atomically replace a target."""

    source_path = Path(backup_path).resolve()
    verify_database_file(source_path)
    destination = Path(destination_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.name}.{uuid4().hex}.restore"
    try:
        source_uri = source_path.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(source_uri, uri=True)) as source, closing(
            sqlite3.connect(temporary)
        ) as target:
            source.backup(target)
        verify_database_file(temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
