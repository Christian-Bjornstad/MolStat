import json
from pathlib import Path

import pytest

from molstat.config import MolStatSettings
from molstat.modules import DEFAULT_UNITS
from molstat.unit_settings import load_unit_file, load_active_units
from unit_fixtures import default_unit_file


def test_solide_is_runnable_with_backlog_before_runtime_initialization():
    assert DEFAULT_UNITS.require('solide').capability('backlog').publication_files[0][0] == 'restansehistorikk_solide.csv'


def test_old_solide_unit_gets_backlog_without_changing_statistics(tmp_path):
    payload = json.loads(default_unit_file('solide').read_text('utf-8'))
    payload['backlog'] = None
    payload['statistics']['antall']['analysis_codes'].append('SYNTHETIC-OU')
    source = tmp_path / 'old-solide.json'
    source.write_text(json.dumps(payload), encoding='utf-8')
    loaded = load_unit_file(source, 'solide')
    assert loaded.payload['statistics'] == payload['statistics']
    assert loaded.payload['backlog'] is None


@pytest.mark.parametrize('key', ['hemato', 'solide'])
def test_external_backlog_is_validated_and_reread_for_each_run(tmp_path, key):
    payload = json.loads(default_unit_file(key).read_text('utf-8'))['backlog']
    source = tmp_path / 'restanse.json'
    source.write_text(json.dumps(payload), encoding='utf-8')
    definitions = {key: default_unit_file(key)}
    first = load_active_units(tmp_path, definitions, (key,), backlog_paths={key: source})[key]
    payload['analyses']['thresholds']['warning_hours'] = 17
    source.write_text(json.dumps(payload), encoding='utf-8')
    second = load_active_units(tmp_path, definitions, (key,), backlog_paths={key: source})[key]
    assert first.digest != second.digest
    assert second.payload['backlog']['analyses']['thresholds']['warning_hours'] == 17
    with pytest.raises(ValueError):
        load_active_units(tmp_path, definitions, (key,), backlog_paths={key: tmp_path / 'missing.json'})


def test_external_backlog_cannot_replace_another_units_setup(tmp_path):
    payload = json.loads(default_unit_file('solide').read_text('utf-8'))['backlog']
    source = tmp_path / 'solide.json'
    source.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError):
        load_unit_file(default_unit_file('hemato'), 'hemato', backlog_path=source)


def test_incomplete_external_backlog_reports_validation_error(tmp_path):
    from molstat.unit_settings import load_backlog_file, UnitConfigError
    payload = json.loads(default_unit_file('hemato').read_text('utf-8'))['backlog']
    del payload['columns']['encoding']
    source = tmp_path / 'incomplete.json'
    source.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(UnitConfigError, match='CONFIG_INVALID'):
        load_backlog_file(source, 'hemato')


def test_backlog_paths_survive_save_load_and_transfer(tmp_path):
    settings = MolStatSettings(sensitive_root=tmp_path / 'sensitive',
        backlog_config_paths={'hemato': tmp_path / 'hemato.json', 'solide': tmp_path / 'solide.json'})
    path = tmp_path / 'settings.json'
    settings.save(path)
    assert MolStatSettings.load(path).backlog_config_paths == settings.backlog_config_paths
    assert MolStatSettings.from_transfer_payload(settings.to_transfer_payload()).backlog_config_paths == settings.backlog_config_paths


def test_save_creates_separate_editable_backlogs_and_runtime_uses_edits(tmp_path):
    from molstat.services import DefaultServices

    sensitive, public = tmp_path / 'sensitive', tmp_path / 'public'
    sensitive.mkdir()
    public.mkdir()
    service = DefaultServices(tmp_path / 'settings.json')
    paths = {}
    for key in ('hemato', 'solide'):
        path = tmp_path / f'{key}-restanse.json'
        payload = json.loads(default_unit_file(key).read_text('utf-8'))['backlog']
        path.write_text(json.dumps(payload), encoding='utf-8')
        paths[key] = path
    service.save_settings_fields({'sensitive_root': str(sensitive), 'sharepoint_root': str(public),
        'lvms_url': 'https://lvms.test/app',
        **{f'config_{key}': str(default_unit_file(key)) for key in paths},
        **{f'backlog_{key}': str(path) for key, path in paths.items()}})
    for key, path in paths.items():
        assert service.settings.backlog_config_paths[key] == path
        assert not (sensitive / 'config').exists()
        payload = json.loads(path.read_text('utf-8'))
        payload['analyses']['thresholds']['warning_hours'] = 19
        path.write_text(json.dumps(payload), encoding='utf-8')
        assert service._manual_import_definition(key).payload['backlog']['analyses']['thresholds']['warning_hours'] == 19


def test_backlog_runner_only_selects_one_unit_without_statistics(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from molstat.services import DefaultServices
    from molstat.database import MolStatDatabase

    database = MolStatDatabase(tmp_path / 'db.sqlite3')
    database.migrate()
    calls = []
    system = SimpleNamespace(database=database, units=DEFAULT_UNITS,
        run_job=lambda kind, keys: calls.append((kind, keys)) or ())
    service = DefaultServices(tmp_path / 'settings.json')
    service.settings = MolStatSettings(sensitive_root=tmp_path, enabled_units=('solide',))
    def build(**kwargs):
        assert kwargs == {'require_statistics': False, 'unit_keys': ('solide',)}
        return system
    monkeypatch.setattr(service, '_build_system', build)
    result = service._orchestrator(system).run('solide:backlog', 'manual')
    assert result.status == 'succeeded'
    assert calls == [('backlog', ('solide',))]
