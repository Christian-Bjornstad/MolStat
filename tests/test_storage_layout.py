import sqlite3
import os
from contextlib import closing

import pytest

from molstat.storage_layout import StorageLayout, prepare_storage_layout


def test_new_layout_separates_database_and_data(tmp_path):
    layout = prepare_storage_layout(tmp_path)
    assert layout.database_path == tmp_path / 'database' / 'molstat.sqlite3'
    assert layout.raw_root == tmp_path / 'data' / 'raw'
    assert layout.processed_root == tmp_path / 'data' / 'processed'
    assert not layout.database_path.exists()
    assert not (tmp_path / 'config').exists()
    assert not (tmp_path / 'work').exists()


def old_database(root):
    source = root / 'data' / 'molstat.sqlite3'
    source.parent.mkdir()
    with closing(sqlite3.connect(source)) as connection:
        connection.execute('CREATE TABLE synthetic(id TEXT)')
        connection.execute("INSERT INTO synthetic VALUES ('STABLE-ID')")
        connection.commit()
    return source


def test_existing_data_migrates_without_losing_ids_or_archives(tmp_path):
    source = old_database(tmp_path)
    raw = tmp_path / 'raw' / 'statistics' / 'lege'
    raw.mkdir(parents=True)
    (raw / 'synthetic.csv').write_bytes(b'unchanged')
    processed = tmp_path / 'processed'
    processed.mkdir()
    (processed / 'pending.json').write_bytes(b'pending')
    layout = prepare_storage_layout(tmp_path)
    assert not source.exists()
    with closing(sqlite3.connect(layout.database_path)) as connection:
        assert connection.execute('SELECT id FROM synthetic').fetchone() == ('STABLE-ID',)
        assert connection.execute('PRAGMA integrity_check').fetchone() == ('ok',)
    assert (layout.raw_root / 'statistics/lege/synthetic.csv').read_bytes() == b'unchanged'
    assert (layout.processed_root / 'pending.json').read_bytes() == b'pending'
    assert list(layout.backups_root.glob('*.sqlite3'))
    assert prepare_storage_layout(tmp_path) == layout


def test_two_databases_stop_without_overwrite(tmp_path):
    source = old_database(tmp_path)
    before = source.read_bytes()
    target = tmp_path / 'database'
    target.mkdir()
    (target / 'molstat.sqlite3').write_bytes(b'keep')
    with pytest.raises(ValueError, match='DB_LOCATION'):
        prepare_storage_layout(tmp_path)
    assert source.read_bytes() == before
    assert (target / 'molstat.sqlite3').read_bytes() == b'keep'


def test_locked_database_keeps_original_and_does_not_create_new_database(tmp_path):
    source = old_database(tmp_path)
    with closing(sqlite3.connect(source)) as connection:
        connection.execute('BEGIN EXCLUSIVE')
        with pytest.raises(ValueError, match='DB_LOCATION'):
            prepare_storage_layout(tmp_path)
    assert source.exists()
    assert not StorageLayout(tmp_path).database_path.exists()


def test_archive_collision_is_detected_before_database_migration(tmp_path):
    source = old_database(tmp_path)
    (tmp_path / 'raw').mkdir()
    (tmp_path / 'data/raw').mkdir()
    with pytest.raises(ValueError, match='DB_LOCATION'):
        prepare_storage_layout(tmp_path)
    assert source.exists()


def test_interrupted_backup_move_is_finished_on_next_start(tmp_path):
    source = old_database(tmp_path)
    layout = StorageLayout(tmp_path)
    layout.database_path.parent.mkdir()
    source.rename(layout.database_path)
    backups = tmp_path / 'data/backups'
    backups.mkdir()
    (backups / 'historical.sqlite3').write_bytes(b'preserve')
    prepare_storage_layout(tmp_path)
    assert (layout.backups_root / 'historical.sqlite3').read_bytes() == b'preserve'
    assert not backups.exists()


@pytest.mark.skipif(os.name != 'nt', reason='Windows sharing contract')
def test_source_cannot_be_reopened_between_checkpoint_and_rename(tmp_path, monkeypatch):
    from pathlib import Path
    source = old_database(tmp_path)
    original = Path.rename
    def rename(path, target):
        if path == source:
            with pytest.raises(sqlite3.OperationalError):
                with closing(sqlite3.connect(source, timeout=0)):
                    pass
        return original(path, target)
    monkeypatch.setattr(Path, 'rename', rename)
    prepare_storage_layout(tmp_path)
