from datetime import datetime
from pathlib import Path
import csv

import pytest

from molstat.database import MolStatDatabase
from molstat.registry import AmbiguousOccurrenceError, SampleRegistry
from molstat.statistics import StatisticsProcessor


HEADER = ['Sample ID', 'WorkItem', 'Analyse', 'Materiale',
          'Tidspunkt opprettet', 'Tidspunkt analysebestilling',
          'Tidspunkt analyseresultat', 'Tidspunkt godkjenning']
ROLES = ('ANTALL', 'RESULTATER', 'EKSTRAKSJON')


def reports(root, start, end, samples, *, revision=''):
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    for role in ROLES:
        path = root / f'PAT-DIT-{role}-OU__{start}__{end}{revision}.csv'
        with path.open('w', encoding='cp1252', newline='') as stream:
            writer = csv.writer(stream, delimiter=';')
            writer.writerow(HEADER)
            for sample in samples:
                extraction = role == 'EKSTRAKSJON'
                writer.writerow([sample, f'{sample}-EXT' if extraction else f'{sample}-CALR',
                    'EKSTRAAPKOL-H-OU' if extraction else 'CALR-OU', 'Blood',
                    '01.09.2026 07:00', '01.09.2026 08:00',
                    '01.09.2026 09:00', '01.09.2026 10:00'])
        paths.append(path)
    return paths


def processor(tmp_path):
    database = MolStatDatabase(tmp_path / 'registry.sqlite3')
    database.migrate()
    return StatisticsProcessor(analysis_codes={'CALR-OU'}, database=database,
        now=lambda: datetime(2026, 10, 1, 12)), database


def import_counts(database):
    with database.read_connection() as connection:
        return [row[0] for row in connection.execute(
            "SELECT row_count FROM import_run WHERE kind='statistics' ORDER BY id")]


def test_incremental_import_only_writes_new_archived_records_and_keeps_history(tmp_path):
    run, database = processor(tmp_path)
    archive = tmp_path / 'archive'
    history = reports(archive, '2024-01-01', '2026-09-01', ['OLD-1', 'OLD-2'])
    first = run.process('hemato', history, tmp_path / 'first')
    ids = SampleRegistry(database).molstat_ids()
    with database.read_connection() as connection:
        first_observations = connection.execute(
            'SELECT occurrence_id, source_kind, last_import_run_id FROM source_observation ORDER BY 1,2').fetchall()
    daily = reports(archive, '2026-09-02', '2026-09-04', ['NEW'])
    second = run.process('hemato', daily, tmp_path / 'second')
    repeated = run.process('hemato', daily, tmp_path / 'repeated')
    assert import_counts(database) == [6, 3, 0]
    assert SampleRegistry(database).molstat_ids() == {**ids, 'NEW': 'M-000003'}
    assert second.row_counts == {'antall': 3, 'resultater': 3}
    assert second.antall.read_bytes() == repeated.antall.read_bytes()
    assert second.resultater.read_bytes() == repeated.resultater.read_bytes()
    with database.read_connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM analysis_event').fetchone()[0] == 18
        assert connection.execute('SELECT COUNT(*) FROM source_observation').fetchone()[0] == 9
        assert connection.execute(
            'SELECT occurrence_id, source_kind, last_import_run_id FROM source_observation WHERE last_import_run_id=1 ORDER BY 1,2'
        ).fetchall() == first_observations


def test_new_registry_bootstraps_complete_archive_even_with_only_daily_inputs(tmp_path):
    run, database = processor(tmp_path)
    reports(tmp_path / 'archive', '2024-01-01', '2026-09-01', ['OLD'])
    daily = reports(tmp_path / 'archive', '2026-09-02', '2026-09-04', ['NEW'])
    result = run.process('hemato', daily, tmp_path / 'out')
    assert import_counts(database) == [6]
    assert SampleRegistry(database).molstat_ids() == {'OLD': 'M-000001', 'NEW': 'M-000002'}
    assert result.row_counts == {'antall': 2, 'resultater': 2}


def test_historical_correction_updates_exports_and_imports_only_changed_archives(tmp_path):
    run, database = processor(tmp_path)
    archive = tmp_path / 'archive'
    history = reports(archive, '2024-01-01', '2026-09-01', ['OLD'])
    daily = reports(archive, '2026-09-02', '2026-09-04', ['NEW'])
    run.process('hemato', daily, tmp_path / 'first')
    ids = SampleRegistry(database).molstat_ids()
    corrected = reports(archive, '2024-01-01', '2026-09-01', ['CORRECTED'], revision='__r2')
    result = run.process('hemato', daily, tmp_path / 'second')
    assert import_counts(database) == [6, 3]
    assert SampleRegistry(database).molstat_ids() == {**ids, 'CORRECTED': 'M-000003'}
    with result.resultater.open(encoding='utf-8-sig', newline='') as stream:
        assert {row['MolStat-ID'] for row in csv.DictReader(stream, delimiter=';')} == {'M-000002', 'M-000003'}
    assert all(path.exists() for path in history + corrected)


def test_failed_incremental_batch_does_not_advance_archive_checkpoint(tmp_path):
    run, database = processor(tmp_path)
    archive = tmp_path / 'archive'
    history = reports(archive, '2024-01-01', '2026-09-01', ['OLD'])
    run.process('hemato', history, tmp_path / 'first')
    daily = reports(archive, '2026-09-02', '2026-09-04', ['NEW', 'COLLISION'])
    for path in daily:
        path.write_text(path.read_text(encoding='cp1252').replace('COLLISION-CALR', 'OLD-CALR'), encoding='cp1252')
    with pytest.raises(AmbiguousOccurrenceError):
        run.process('hemato', daily, tmp_path / 'failed')
    assert import_counts(database) == [3]
    assert SampleRegistry(database).molstat_ids() == {'OLD': 'M-000001'}
    daily = reports(archive, '2026-09-02', '2026-09-04', ['NEW', 'RECOVERED'])
    run.process('hemato', daily, tmp_path / 'recovered')
    assert import_counts(database) == [3, 6]
    assert set(SampleRegistry(database).molstat_ids()) == {'OLD', 'NEW', 'RECOVERED'}


def test_standard_timestamps_avoid_repeated_strptime_work(monkeypatch):
    from molstat._statistics import processing
    class ObservedDatetime(datetime):
        strptime_calls = 0
        @classmethod
        def strptime(cls, value, pattern):
            cls.strptime_calls += 1
            return super().strptime(value, pattern)
    monkeypatch.setattr(processing, 'datetime', ObservedDatetime)
    assert processing.parse_tidspunkt('01.09.2026') == datetime(2026, 9, 1)
    assert processing.parse_tidspunkt('01.09.2026 08:15') == datetime(2026, 9, 1, 8, 15)
    assert processing.parse_tidspunkt('01.09.2026 08:15:30') == datetime(2026, 9, 1, 8, 15, 30)
    assert ObservedDatetime.strptime_calls == 0


@pytest.mark.parametrize('value', [
    '1.9.2026', '01.9.2026 8:1', '01.09.2026 08:01:2',
    '01.09.2026\t08:01', '01.09.2026  08:01:02',
    '=T("01.09.2026 08:01")', '29.02.2024 23:59:59',
    '29.02.2026', '31.09.2026', '01.09.2026 24:01',
    '01.09.2026 08:60', '01.09.2026 08:01:60',
    '01.09.2026T08:01', '01.09.2026 08:01:02.3', '', None,
])
def test_timestamp_fast_path_keeps_legacy_validation(value):
    from molstat._statistics.processing import clean_text, parse_tidspunkt
    expected = None
    for pattern in ('%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H:%M', '%d.%m.%Y'):
        try:
            expected = datetime.strptime(clean_text(value), pattern)
            break
        except ValueError:
            pass
    assert parse_tidspunkt(value) == expected


@pytest.mark.parametrize('checkpoint', ['legacy-fingerprint', 'statistics-archives-v1:{broken'])
def test_legacy_or_malformed_checkpoint_catches_up_complete_history(tmp_path, checkpoint):
    run, database = processor(tmp_path)
    history = reports(tmp_path / 'archive', '2024-01-01', '2026-09-01', ['OLD'])
    run.process('hemato', history, tmp_path / 'first')
    with database._connect() as connection:
        connection.execute('UPDATE import_run SET source_fingerprint=?', (checkpoint,))
    daily = reports(tmp_path / 'archive', '2026-09-02', '2026-09-04', ['NEW'])
    run.process('hemato', daily, tmp_path / 'second')
    assert import_counts(database) == [3, 6]
    assert SampleRegistry(database).molstat_ids() == {'OLD': 'M-000001', 'NEW': 'M-000002'}


def test_incremental_import_discovers_intermediate_archives(tmp_path):
    run, database = processor(tmp_path)
    archive = tmp_path / 'archive'
    history = reports(archive, '2024-01-01', '2026-09-01', ['OLD'])
    run.process('hemato', history, tmp_path / 'first')
    reports(archive, '2026-09-02', '2026-09-03', ['INTERMEDIATE'])
    final = reports(archive, '2026-09-04', '2026-09-05', ['FINAL'])
    result = run.process('hemato', final, tmp_path / 'second')
    assert import_counts(database) == [3, 6]
    assert SampleRegistry(database).molstat_ids() == {'OLD': 'M-000001', 'INTERMEDIATE': 'M-000002', 'FINAL': 'M-000003'}
    assert result.row_counts == {'antall': 3, 'resultater': 3}


def test_archive_content_change_updates_existing_source_events_and_csv(tmp_path):
    run, database = processor(tmp_path)
    history = reports(tmp_path / 'archive', '2024-01-01', '2026-09-01', ['OLD'])
    run.process('hemato', history, tmp_path / 'first')
    answered = history[1]
    answered.write_text(answered.read_text(encoding='cp1252').replace(
        '01.09.2026 10:00', '02.09.2026 10:00'), encoding='cp1252')
    result = run.process('hemato', history, tmp_path / 'second')
    assert import_counts(database) == [3, 1]
    assert SampleRegistry(database).molstat_ids() == {'OLD': 'M-000001'}
    with database.read_connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM analysis_event').fetchone()[0] == 7
    with result.resultater.open(encoding='utf-8-sig', newline='') as stream:
        row, = csv.DictReader(stream, delimiter=';')
    assert row['Tidspunkt.godkjenning'] == '2026/09/02 10:00:00'
    assert row['MolStat-ID'] == 'M-000001'
