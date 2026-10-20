import errno
import json
from pathlib import Path

import pytest

from molstat.delivery import deliver, retry_pending
from molstat.publisher import PublicationPolicy, SharePointPublisher


@pytest.fixture(autouse=True)
def immediate_storage_retry(monkeypatch):
    monkeypatch.setattr('molstat.recovery._sleep', lambda _delay: None)


def candidate(tmp_path):
    source = tmp_path / 'processed/run/antall.csv'
    source.parent.mkdir(parents=True)
    source.write_text('Analyse;Antall\nSYNTHETIC;1\n', encoding='utf-8')
    publisher = SharePointPublisher(PublicationPolicy({'antall.csv': frozenset({'Analyse', 'Antall'})}, ()))
    return source, publisher


def test_manifest_pending_write_retries_before_any_publication(tmp_path, monkeypatch):
    source, publisher = candidate(tmp_path)
    original = Path.open
    denied = []
    def locked_once(path, *args, **kwargs):
        if path.name.startswith('.delivery.json.') and args[0] == 'w' and not denied:
            denied.append(True)
            raise PermissionError(errno.EACCES, 'SECRET-PATH')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', locked_once)

    deliver(publisher, {'antall.csv': source}, tmp_path / 'public', source.parent)

    assert (tmp_path / 'public/antall.csv').read_bytes() == source.read_bytes()
    assert json.loads((source.parent / 'delivery.json').read_text())['status'] == 'published'


def test_published_manifest_retry_does_not_republish_completed_exports(tmp_path, monkeypatch):
    source, publisher = candidate(tmp_path)
    original_write = __import__('molstat.delivery', fromlist=['write_json']).write_json
    writes = []
    def locked_published_once(path, payload):
        if payload['status'] == 'published' and not writes:
            writes.append(True)
            raise PermissionError(errno.EACCES, 'SECRET-PATH')
        return original_write(path, payload)
    monkeypatch.setattr('molstat.delivery.write_json', locked_published_once)
    original_publish = publisher.publish
    def publish_once(files, destination):
        assert not (destination / 'antall.csv').exists(), 'Completed export replayed'
        return original_publish(files, destination)
    monkeypatch.setattr(publisher, 'publish', publish_once)

    deliver(publisher, {'antall.csv': source}, tmp_path / 'public', source.parent)

    assert (tmp_path / 'public/antall.csv').read_bytes() == source.read_bytes()
    assert json.loads((source.parent / 'delivery.json').read_text())['status'] == 'published'


def test_candidate_read_is_retried_before_validation(tmp_path, monkeypatch):
    source, publisher = candidate(tmp_path)
    original = Path.open
    denied = []
    def locked_once(path, *args, **kwargs):
        if path == source and (args[0] if args else kwargs.get('mode')) == 'r' and not denied:
            denied.append(True)
            raise PermissionError(errno.EACCES, 'SECRET-PATH')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', locked_once)

    deliver(publisher, {'antall.csv': source}, tmp_path / 'public', source.parent)

    assert (tmp_path / 'public/antall.csv').read_bytes() == source.read_bytes()


def test_pending_manifest_read_retries_without_new_processing(tmp_path, monkeypatch):
    source, publisher = candidate(tmp_path)
    original_publish = publisher.publish
    monkeypatch.setattr(publisher, 'publish', lambda *a: (_ for _ in ()).throw(PermissionError(errno.EACCES, 'SECRET-PATH')))
    with pytest.raises(PermissionError):
        deliver(publisher, {'antall.csv': source}, tmp_path / 'public', source.parent)
    monkeypatch.setattr(publisher, 'publish', original_publish)
    original = Path.open
    denied = []
    def locked_once(path, *args, **kwargs):
        if path.name == 'delivery.json' and (args[0] if args else kwargs.get('mode')) == 'r' and not denied:
            denied.append(True)
            raise PermissionError(errno.EACCES, 'SECRET-PATH')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', locked_once)

    assert retry_pending(publisher, source.parent.parent, tmp_path / 'public') == 1

    assert (tmp_path / 'public/antall.csv').read_bytes() == source.read_bytes()

def test_cancel_after_publication_still_records_published_manifest(tmp_path, monkeypatch):
    from threading import Event
    from molstat.recovery import recovery_context
    source, publisher = candidate(tmp_path)
    cancelled = Event()
    original_publish = publisher.publish
    def publish_then_cancel(files, destination):
        result = original_publish(files, destination)
        cancelled.set()
        return result
    monkeypatch.setattr(publisher, 'publish', publish_then_cancel)

    with recovery_context(cancel=cancelled):
        deliver(publisher, {'antall.csv': source}, tmp_path / 'public', source.parent)

    assert json.loads((source.parent / 'delivery.json').read_text())['status'] == 'published'
    assert (tmp_path / 'public/antall.csv').read_bytes() == source.read_bytes()
