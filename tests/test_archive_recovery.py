from datetime import date
import errno
import hashlib
import os
from pathlib import Path
import stat

import pytest

from molstat.archive import RawArchive, remove_archived_download
from molstat.lvms.report import ReportRequest
from molstat.system import MolStatSystem


@pytest.fixture(autouse=True)
def immediate_storage_retry(monkeypatch):
    monkeypatch.setattr('molstat.recovery._sleep', lambda _delay: None)


def request():
    return ReportRequest(kind='backlog', unit='hemato', report_name='SYNTHETIC',
                         date_from=date(2026, 10, 1), date_to=date(2026, 10, 2))


def test_archive_retries_transient_source_read_without_duplicate(tmp_path, monkeypatch):
    source = tmp_path / 'source.csv'
    source.write_bytes(b'SYNTHETIC;1\n')
    original = Path.open
    failures = []
    def sometimes_locked(path, *args, **kwargs):
        if path == source and args and args[0] == 'rb' and not failures:
            failures.append(True)
            raise PermissionError(errno.EACCES, 'SENSITIVE-PATH')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', sometimes_locked)

    archived = RawArchive(tmp_path / 'private').store(source, request())

    assert archived.path.read_bytes() == b'SYNTHETIC;1\n'
    assert archived.sha256 == hashlib.sha256(b'SYNTHETIC;1\n').hexdigest()
    assert list(archived.path.parent.glob('*.csv')) == [archived.path]
    assert not list(archived.path.parent.glob('*.tmp'))


def test_archive_retries_atomic_install_without_recopied_revision(tmp_path, monkeypatch):
    source = tmp_path / 'source.csv'
    source.write_bytes(b'SYNTHETIC')
    replace = os.replace
    failures = []
    def locked_once(src, dst):
        if not failures:
            failures.append(True)
            raise PermissionError(errno.EACCES, 'SENSITIVE-PATH')
        return replace(src, dst)
    monkeypatch.setattr('molstat.archive.os.replace', locked_once)

    archived = RawArchive(tmp_path / 'private').store(source, request())

    assert archived.path.read_bytes() == b'SYNTHETIC'
    assert list(archived.path.parent.glob('*.csv')) == [archived.path]


def test_archive_verifies_ambiguous_install_instead_of_new_revision(tmp_path, monkeypatch):
    source = tmp_path / 'source.csv'
    source.write_bytes(b'SYNTHETIC')
    replace = os.replace
    def committed_but_lost_response(src, dst):
        replace(src, dst)
        raise PermissionError(errno.EACCES, 'SENSITIVE-PATH')
    monkeypatch.setattr('molstat.archive.os.replace', committed_but_lost_response)

    archived = RawArchive(tmp_path / 'private').store(source, request())

    assert archived.path.read_bytes() == b'SYNTHETIC'
    assert list(archived.path.parent.glob('*.csv')) == [archived.path]


@pytest.mark.skipif(os.name != 'nt', reason='Windows READONLY file attribute')
def test_archive_does_not_copy_readonly_attribute_from_source(tmp_path):
    source = tmp_path / 'source.csv'
    source.write_bytes(b'SYNTHETIC')
    source.chmod(stat.S_IREAD)
    try:
        archived = RawArchive(tmp_path / 'private').store(source, request())
        assert not archived.path.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
        assert source.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
    finally:
        source.chmod(stat.S_IWRITE)
        if 'archived' in locals():
            archived.path.chmod(stat.S_IWRITE)


def test_archive_timestamp_denial_cannot_turn_committed_copy_into_failure(tmp_path, monkeypatch):
    source = tmp_path / 'source.csv'
    source.write_bytes(b'SYNTHETIC')
    monkeypatch.setattr('molstat.archive.os.utime', lambda *a, **k: (_ for _ in ()).throw(PermissionError(errno.EACCES, 'SENSITIVE-PATH')))

    archived = RawArchive(tmp_path / 'private').store(source, request())

    assert archived.path.read_bytes() == b'SYNTHETIC'
    assert list(archived.path.parent.glob('*.csv')) == [archived.path]


def test_cleanup_retains_unrecognized_files_in_private_job(tmp_path):
    folder = tmp_path / 'data/raw/.jobs/synthetic/rådata'
    folder.mkdir(parents=True)
    source = folder / 'download.csv'
    source.write_bytes(b'SYNTHETIC')
    unrelated = folder.parent / 'unverified-output.csv'
    unrelated.write_bytes(b'UNVERIFIED')
    (folder.parent / 'jobs.json').write_text('{}')

    remove_archived_download(source, tmp_path)

    assert unrelated.read_bytes() == b'UNVERIFIED'
    assert not source.exists()


def test_persistent_download_cleanup_denial_keeps_archive_for_processing(tmp_path, monkeypatch):
    source = tmp_path / 'download.csv'
    source.write_bytes(b'SYNTHETIC')
    system = object.__new__(MolStatSystem)
    system.archive = RawArchive(tmp_path / 'private')
    reported = []
    system._excel_failure_reporter = lambda stage, error: reported.append((stage, error))
    original = Path.unlink
    def locked_download(path, *a, **k):
        if path == source:
            raise PermissionError(errno.EACCES, 'SENSITIVE-PATH')
        return original(path, *a, **k)
    monkeypatch.setattr(Path, 'unlink', locked_download)

    archived_path = system._archive_and_remove((request(), source))

    assert archived_path.read_bytes() == b'SYNTHETIC'
    assert source.read_bytes() == b'SYNTHETIC'
    assert len(reported) == 1
    assert reported[0][0] == 'raw_download_cleanup_failed'


def test_transient_download_cleanup_is_retried(tmp_path, monkeypatch):
    source = tmp_path / 'download.csv'
    source.write_bytes(b'SYNTHETIC')
    original = Path.unlink
    failures = []
    def locked_once(path, *a, **k):
        if path == source and not failures:
            failures.append(True)
            raise PermissionError(errno.EACCES, 'SENSITIVE-PATH')
        return original(path, *a, **k)
    monkeypatch.setattr(Path, 'unlink', locked_once)

    remove_archived_download(source, tmp_path)

    assert not source.exists()

def test_archive_cancel_after_install_does_not_replace_completed_result_with_cleanup_error(tmp_path, monkeypatch):
    from threading import Event
    from molstat.recovery import recovery_context
    source = tmp_path / 'source.csv'
    source.write_bytes(b'SYNTHETIC')
    cancelled = Event()
    original = os.replace
    def install_then_cancel(src, dst):
        original(src, dst)
        cancelled.set()
    monkeypatch.setattr('molstat.archive.os.replace', install_then_cancel)

    with recovery_context(cancel=cancelled):
        archived = RawArchive(tmp_path / 'private').store(source, request())

    assert archived.path.read_bytes() == b'SYNTHETIC'
    assert source.read_bytes() == b'SYNTHETIC'


def test_uncertain_archive_install_never_overwrites_other_bytes_and_keeps_candidate(tmp_path, monkeypatch):
    source = tmp_path / 'source.csv'
    source.write_bytes(b'SYNTHETIC')
    def ambiguous_install(src, dst):
        Path(dst).write_bytes(b'OTHER-CONTENT')
        raise OSError(errno.EIO, 'SECRET-PATH')
    monkeypatch.setattr('molstat.archive.os.replace', ambiguous_install)

    with pytest.raises(OSError):
        RawArchive(tmp_path / 'private').store(source, request())

    folder = tmp_path / 'private/data/raw/backlog/hemato'
    assert [path.read_bytes() for path in folder.glob('*.csv')] == [b'OTHER-CONTENT']
    assert [path.read_bytes() for path in folder.glob('*.tmp')] == [b'SYNTHETIC']
    assert source.read_bytes() == b'SYNTHETIC'

def test_ambiguous_access_error_cannot_overwrite_new_destination(tmp_path, monkeypatch):
    source = tmp_path / 'source.csv'
    source.write_bytes(b'SYNTHETIC')
    original = os.replace
    denied = []
    def conflicting_install(src, dst):
        if not denied:
            denied.append(True)
            Path(dst).write_bytes(b'OTHER-CONTENT')
            raise PermissionError(errno.EACCES, 'SECRET-PATH')
        return original(src, dst)
    monkeypatch.setattr('molstat.archive.os.replace', conflicting_install)

    with pytest.raises(PermissionError):
        RawArchive(tmp_path / 'private').store(source, request())

    folder = tmp_path / 'private/data/raw/backlog/hemato'
    assert [path.read_bytes() for path in folder.glob('*.csv')] == [b'OTHER-CONTENT']
    assert [path.read_bytes() for path in folder.glob('*.tmp')] == [b'SYNTHETIC']
    assert source.read_bytes() == b'SYNTHETIC'

def test_consumed_fetch_attempt_layout_removes_only_completed_private_job(tmp_path):
    from molstat.fetching import UnifiedLvmsFetcher
    from molstat.lvms.report_job import ReportInterval, ReportJob, batch_filename, load_report_jobs
    report = ReportJob('ordered', 'PRODSTAT', 'PATOLOGI', 'SYNTHETIC', ('CALR-OU',),
                       ReportInterval(date(2026, 10, 1), date(2026, 10, 2)), 'SYNTHETIC')
    def runner(config, jobs_path, keys, **kwargs):
        current, = load_report_jobs(jobs_path)
        source = kwargs['repository_root'] / 'rådata' / batch_filename(current)
        source.parent.mkdir()
        source.write_bytes(b'SYNTHETIC')
        return 0
    fetcher = UnifiedLvmsFetcher(lvms_config_path=tmp_path / 'lvms.json',
        sensitive_root=tmp_path, work_root=tmp_path / 'data/raw/.jobs',
        units=(), run_batch=runner, sleep=lambda delay: None)
    source, = fetcher._run_jobs((report,), 'hemato')
    run = source.parent.parent
    assert list(run.glob('attempt-*/jobs.json'))

    remove_archived_download(source, tmp_path)

    assert not run.exists()


@pytest.mark.parametrize('unexpected', ['partial.csv', 'candidate.tmp', 'unknown.txt'])
def test_fetch_attempt_with_unverified_file_is_preserved(tmp_path, unexpected):
    run = tmp_path / 'data/raw/.jobs/synthetic'
    folder = run / 'rådata'
    folder.mkdir(parents=True)
    source = folder / 'download.csv'
    source.write_bytes(b'SYNTHETIC')
    attempt = run / ('attempt-' + 'a' * 32)
    (attempt / 'rådata').mkdir(parents=True)
    (attempt / 'jobs.json').write_text('{}')
    candidate = attempt / 'rådata' / unexpected
    candidate.write_bytes(b'UNVERIFIED')

    remove_archived_download(source, tmp_path)

    assert candidate.read_bytes() == b'UNVERIFIED'
    assert (attempt / 'jobs.json').exists()
    assert run.exists()


def test_non_attempt_directory_is_never_treated_as_owned_job_cleanup(tmp_path):
    run = tmp_path / 'data/raw/.jobs/synthetic'
    folder = run / 'rådata'
    folder.mkdir(parents=True)
    source = folder / 'download.csv'
    source.write_bytes(b'SYNTHETIC')
    unknown = run / 'attempt-personal'
    (unknown / 'rådata').mkdir(parents=True)
    (unknown / 'jobs.json').write_text('{}')

    remove_archived_download(source, tmp_path)

    assert (unknown / 'jobs.json').exists()
    assert unknown.exists()
