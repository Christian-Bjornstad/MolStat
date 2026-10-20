"""Install a complete set of private Power BI CSVs while preserving recovery files."""
from pathlib import Path
import logging
import os
import shutil
from uuid import uuid4

from ._writer_lease import guarded_output
from .failures import RunFailure, storage_failure
from .recovery import retry_operation, uncancellable_cleanup


def _known_no_change(error):
    failure = storage_failure(error)
    return failure is not None and failure.code in {"FILE_ACCESS", "FILE_BUSY"}


def _replace(source, destination, sleep):
    def known_unmoved(error):
        # Even an access error can be reported after a remote rename completed.
        # A consumed source must be reconciled/rolled back, never retried.
        return _known_no_change(error) and source.exists()
    retry_operation(lambda: os.replace(source, destination), stage="private_replace",
                    sleep=sleep, retry_if=known_unmoved)


def _copy(source, destination):
    # Copy bytes, not Windows read-only attributes from a downloaded export.
    with source.open('rb') as reader, destination.open('wb') as writer:
        shutil.copyfileobj(reader, writer, 1024 * 1024)
        writer.flush()
        os.fsync(writer.fileno())


def install_private_files(files, destination: Path, *, sleep=None):
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
    retry_operation(lambda: destination.mkdir(parents=True, exist_ok=True),
                    stage="private_stage", sleep=sleep)
    staging = destination / ('.molstat-' + uuid4().hex)
    retry_operation(staging.mkdir, stage="private_stage", sleep=sleep)
    staged, backups, installed = {}, {}, []
    keep_recovery = False
    try:
        # Prepare every new file and every old copy before replacing the first CSV.
        for index, (name, source) in enumerate(files.items()):
            candidate = staging / f'{index}.new.tmp'
            retry_operation(lambda: _copy(source, candidate), stage="private_stage", sleep=sleep)
            staged[name] = candidate
            target = destination / name
            if target.exists():
                backup = staging / f'{name}.old.tmp'
                retry_operation(lambda: _copy(target, backup), stage="private_stage", sleep=sleep)
                backups[name] = backup
        try:
            for name, candidate in staged.items():
                installed.append(name)
                try:
                    _replace(candidate, destination / name, sleep)
                except BaseException:
                    # The unique candidate still exists only if its atomic
                    # rename did not complete. Avoid restoring an unchanged,
                    # locked target, but include consumed candidates on cancel.
                    if candidate.exists():
                        installed.pop()
                    raise
        except BaseException:
            restore_errors = []
            with uncancellable_cleanup():
                for name in reversed(installed):
                    try:
                        if name in backups:
                            _replace(backups[name], destination / name, sleep)
                        else:
                            retry_operation(lambda: (destination / name).unlink(missing_ok=True),
                                            stage="private_rollback", sleep=sleep)
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
