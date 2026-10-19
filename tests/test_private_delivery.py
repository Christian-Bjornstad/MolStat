from pathlib import Path
import os

import pytest

from molstat.failures import RunFailure


def files(tmp_path):
    source = tmp_path / 'candidate'
    target = tmp_path / 'powerbi'
    source.mkdir()
    target.mkdir()
    result = {}
    for name in ('Prøver.csv', 'Glass.csv', 'Signeringer.csv'):
        result[name] = source / name
        result[name].write_text('new-' + name, encoding='utf-8')
        (target / name).write_text('old-' + name, encoding='utf-8')
    return result, target


def test_private_delivery_retries_a_temporary_windows_file_lock(tmp_path, monkeypatch):
    from molstat.private_delivery import install_private_files

    candidates, target = files(tmp_path)
    original = os.replace
    calls = []
    def locked_once(source, destination):
        if Path(destination) == target / 'Glass.csv' and not calls:
            calls.append(1)
            raise PermissionError('synthetic sharing violation')
        return original(source, destination)
    monkeypatch.setattr('molstat.private_delivery.os.replace', locked_once)
    install_private_files(candidates, target, sleep=lambda _: None)
    assert calls == [1]
    for name, path in candidates.items():
        assert (target / name).read_bytes() == path.read_bytes()


def test_private_delivery_restores_the_complete_old_set_when_a_file_stays_locked(tmp_path, monkeypatch):
    from molstat.private_delivery import install_private_files

    candidates, target = files(tmp_path)
    before = {name: (target / name).read_bytes() for name in candidates}
    original = os.replace
    def locked(source, destination):
        if Path(destination) == target / 'Glass.csv':
            raise PermissionError('SECRET raw error')
        return original(source, destination)
    monkeypatch.setattr('molstat.private_delivery.os.replace', locked)
    with pytest.raises(RunFailure) as caught:
        install_private_files(candidates, target, sleep=lambda _: None)
    assert caught.value.code == 'PRIVATE_FILES_LOCKED'
    assert 'SECRET' not in str(caught.value)
    for name, path in candidates.items():
        assert (target / name).read_bytes() == before[name]
        assert path.exists()


def test_private_delivery_cannot_publish_after_writer_token_is_replaced(tmp_path):
    from datetime import timedelta
    from molstat.database import MolStatDatabase
    from molstat._writer_lease import WriterLeaseLost
    from molstat.private_delivery import install_private_files

    candidates, target = files(tmp_path)
    before = {name: (target / name).read_bytes() for name in candidates}
    database = MolStatDatabase(tmp_path / 'db.sqlite3')
    database.migrate()
    with database.writer_lease('pc-a', timedelta(minutes=5), renew=True):
        with database._connect(guard_lease=False) as connection:
            connection.execute("UPDATE writer_lease SET token='other', owner='pc-b'")
        with pytest.raises(WriterLeaseLost):
            install_private_files(candidates, target, sleep=lambda _: None)
    assert {name: (target / name).read_bytes() for name in candidates} == before


def test_blocked_rollback_keeps_recovery_files_instead_of_deleting_them(tmp_path, monkeypatch):
    from molstat.private_delivery import install_private_files

    candidates, target = files(tmp_path)
    original = os.replace
    def locked(source, destination):
        if Path(destination) == target / 'Glass.csv' or Path(source).name.endswith('.old.tmp'):
            raise PermissionError('synthetic persistent lock')
        return original(source, destination)
    monkeypatch.setattr('molstat.private_delivery.os.replace', locked)
    with pytest.raises(RunFailure) as caught:
        install_private_files(candidates, target, sleep=lambda _: None)
    assert caught.value.code == 'PRIVATE_FILES_RECOVERY'
    backups = list(target.glob('.molstat-*/*.old.tmp'))
    assert any(p.read_text('utf-8') == 'old-Prøver.csv' for p in backups)
    assert all(p.exists() for p in candidates.values())
