from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import logging
import os
from pathlib import Path
import re
import stat
import tempfile

from .storage_layout import StorageLayout
from .lvms.report import ReportRequest
from ._writer_lease import guarded_output
from .recovery import check_cancelled, retry_operation, uncancellable_cleanup
from .failures import storage_failure


@dataclass(frozen=True, slots=True)
class ArchivedRawFile:
    path: Path
    sha256: str


class RawArchive:
    def __init__(self, sensitive_root: Path) -> None:
        self.sensitive_root = sensitive_root

    def store(self, source: Path, request: ReportRequest) -> ArchivedRawFile:
        with guarded_output():
            return self._store(source, request)

    def _store(self, source: Path, request: ReportRequest) -> ArchivedRawFile:
        if not source.is_file():
            raise FileNotFoundError(source)
        destination_dir = (
            StorageLayout(self.sensitive_root).raw_root / request.kind / request.unit
        )
        retry_operation(lambda: destination_dir.mkdir(parents=True, exist_ok=True),
                        stage='raw_archive_directory')
        stem = (
            f"{request.report_name}__{request.date_from.isoformat()}"
            f"__{request.date_to.isoformat()}"
        )
        destination = retry_operation(lambda: _next_destination(destination_dir, stem),
                                      stage='raw_archive_destination')
        temporary, digest = retry_operation(
            lambda: _stage_source(source, destination_dir, stem), stage='raw_archive_copy')
        retry_operation(lambda: _install_archive(temporary, destination, digest),
                        stage='raw_archive_install',
                        retry_if=lambda error: _rename_denied(error, temporary, destination))
        _cleanup(lambda: temporary.unlink(missing_ok=True), 'raw_archive_staging_cleanup')

        # Copy dates only: copystat would also copy Windows' READONLY attribute.
        # The content has already been installed. An optional metadata failure
        # must not turn this into a failed archive and cause a new revision.
        try:
            source_stat = source.stat()
            os.utime(destination, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
        except OSError:
            logging.getLogger(__name__).warning('RAW_ARCHIVE_METADATA: timestamp metadata unavailable.')
        return ArchivedRawFile(path=destination, sha256=digest)


def _stage_source(source: Path, directory: Path, stem: str) -> tuple[Path, str]:
    digest = hashlib.sha256()
    temporary: Path | None = None
    try:
        with source.open('rb') as reader, tempfile.NamedTemporaryFile(
            mode='wb', dir=directory, prefix=f'.{stem}.', suffix='.tmp', delete=False,
        ) as writer:
            temporary = Path(writer.name)
            while chunk := reader.read(1024 * 1024):
                check_cancelled()
                digest.update(chunk)
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        return temporary, digest.hexdigest()
    except BaseException:
        if temporary is not None:
            _cleanup(lambda: temporary.unlink(missing_ok=True), 'raw_archive_staging_cleanup')
        raise


def _rename_denied(error: BaseException, temporary: Path, destination: Path) -> bool:
    failure = storage_failure(error)
    if failure is None or failure.code not in {'FILE_ACCESS', 'FILE_BUSY'}:
        return False
    try:
        return temporary.is_file() and not destination.exists()
    except OSError:
        return False


def _install_archive(temporary: Path, destination: Path, expected_digest: str) -> None:
    try:
        os.replace(temporary, destination)
    except OSError:
        # A remote file server may commit rename and then lose its reply. Accept
        # that outcome only after the same staged bytes are confirmed in place.
        if not temporary.exists() and destination.is_file():
            def installed_digest() -> str:
                with destination.open('rb') as stream:
                    return hashlib.file_digest(stream, 'sha256').hexdigest()
            if retry_operation(installed_digest, stage='raw_archive_verify') == expected_digest:
                return
        raise


def _next_destination(directory: Path, stem: str) -> Path:
    candidate = directory / f"{stem}.csv"
    revision = 2
    while candidate.exists():
        candidate = directory / f"{stem}__r{revision}.csv"
        revision += 1
    return candidate


def _cleanup(operation: Callable[[], None], stage: str,
             failure_reporter: Callable[[str, BaseException], None] | None = None) -> bool:
    try:
        with uncancellable_cleanup():
            retry_operation(operation, stage=stage)
    except OSError as error:
        _report_cleanup_failure(stage, error, failure_reporter)
        return False
    return True


def _report_cleanup_failure(stage: str, error: OSError,
                            failure_reporter: Callable[[str, BaseException], None] | None) -> None:
    if failure_reporter is not None:
        try:
            failure_reporter(stage + '_failed', error)
        except Exception:
            pass
    logging.getLogger(__name__).warning('%s: archived files retained; cleanup unavailable.', stage)


def _is_link(path: Path) -> bool:
    details = path.lstat()
    return (stat.S_ISLNK(details.st_mode)
            or bool(getattr(details, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT))


def _known_empty_attempt(path: Path) -> bool:
    if _is_link(path) or not path.is_dir():
        return False
    for child in path.iterdir():
        if _is_link(child):
            return False
        if child.name == 'rådata' and child.is_dir() and not any(child.iterdir()):
            continue
        if child.name == 'jobs.json' and child.is_file():
            continue
        return False
    return True


def _completed_job_directory(source: Path, sensitive_root: Path) -> tuple[Path, ...]:
    jobs = (StorageLayout(sensitive_root).raw_root / '.jobs').resolve()
    run = source.parent.parent
    if source.parent.name != 'rådata' or _is_link(run) or _is_link(source.parent):
        return ()
    resolved = run.resolve()
    if resolved.parent != jobs or not resolved.is_relative_to(jobs):
        return ()
    if any(source.parent.iterdir()):
        return ()
    attempts = []
    for path in run.iterdir():
        if _is_link(path):
            return ()
        if path.name == 'rådata' and path.is_dir():
            continue
        if path.name == 'jobs.json' and path.is_file():
            continue
        if re.fullmatch(r'attempt-[0-9a-f]{32}', path.name) and _known_empty_attempt(path):
            attempts.append(path)
            continue
        return ()
    return (*attempts, run)


def _remove_empty_job_directory(path: Path) -> None:
    raw = path / 'rådata'
    if raw.exists():
        raw.rmdir()
    (path / 'jobs.json').unlink(missing_ok=True)
    path.rmdir()


def remove_archived_download(source: Path, sensitive_root: Path, *,
                             failure_reporter: Callable[[str, BaseException], None] | None = None) -> None:
    """Remove a consumed download without failing its completed archive/import.

    Call only after archiving succeeded. Unknown files in the private run are
    retained; no recursive deletion is used for a potentially incomplete run.
    """
    with uncancellable_cleanup():
        _remove_archived_download(source, sensitive_root, failure_reporter)


def _remove_archived_download(source: Path, sensitive_root: Path,
                              failure_reporter: Callable[[str, BaseException], None] | None) -> None:
    if not _cleanup(lambda: source.unlink(missing_ok=True), 'raw_download_cleanup', failure_reporter):
        return
    try:
        directories = retry_operation(lambda: _completed_job_directory(source, sensitive_root),
                              stage='raw_job_inspection')
    except OSError as error:
        _report_cleanup_failure('raw_job_inspection', error, failure_reporter)
        return
    for directory in directories:
        if not _cleanup(lambda: _remove_empty_job_directory(directory), 'raw_job_cleanup', failure_reporter):
            return
