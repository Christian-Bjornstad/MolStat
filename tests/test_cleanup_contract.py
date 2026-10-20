import json
from pathlib import Path

import pytest

from molstat.config import MolStatSettings
from molstat.services import DefaultServices
from molstat.unit_settings import load_active_units
from unit_fixtures import default_unit_file


def test_selected_json_is_used_in_place_without_lookup_or_config_copies(tmp_path):
    private, public = tmp_path / 'private', tmp_path / 'public'
    private.mkdir()
    public.mkdir()
    source = tmp_path / 'my_patolog.json'
    original = default_unit_file('lege').read_bytes()
    source.write_bytes(original)
    settings = tmp_path / 'settings.json'
    service = DefaultServices(settings)
    service.save_settings_fields({
        'sensitive_root': str(private), 'sharepoint_root': str(public),
        'lvms_url': 'https://example.test/lvms', 'config_lege': str(source),
        **{f'enabled_{key}': str(key == 'lege') for key in ('hemato', 'solide', 'flow', 'fish', 'pre', 'lege')},
        'lookup_lege': str(tmp_path / 'missing_lege.csv'),
    })
    reopened = DefaultServices(settings)
    assert reopened.settings.unit_config_paths['lege'] == source.resolve()
    assert source.read_bytes() == original
    assert not (private / 'config').exists()
    assert not any(name.startswith('lookup_') for name in reopened.load_settings_fields())
    assert 'statistics_lookup_path' not in json.loads(settings.read_text())['units']['lege']


def test_missing_selected_json_never_creates_defaults(tmp_path):
    with pytest.raises(ValueError, match='JSON|[Ee]nhetsfil'):
        load_active_units(tmp_path, {}, ('lege',))
    assert list(tmp_path.iterdir()) == []


def test_old_lookup_setting_is_discarded_without_opening_file(tmp_path):
    payload = MolStatSettings(sensitive_root=tmp_path).to_transfer_payload()
    payload['units']['lege']['statistics_lookup_path'] = str(tmp_path / 'unreadable.csv')
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps(payload))
    loaded = MolStatSettings.load(path)
    assert 'statistics_lookup_path' not in loaded.to_transfer_payload()['units']['lege']


@pytest.mark.parametrize('profile', ['flow', 'fish', 'pre'])
def test_processors_keep_json_codes_without_lookup_metadata(tmp_path, profile):
    import csv
    from molstat._statistics import flow_reports, fish_reports, pre_reports

    raw = tmp_path / 'raw.csv'
    fields = ['Sample ID', 'Analyse', 'Tidspunkt opprettet', 'Tidspunkt analysebestilling', 'Tidspunkt analyseresultat', 'Tidspunkt godkjenning']
    with raw.open('w', encoding='cp1252', newline='') as handle:
        writer = csv.writer(handle, delimiter=';')
        writer.writerow(fields)
        writer.writerow(['SYNTHETIC', 'INCLUDED', '01.10.2026 08:00', '01.10.2026 09:00', '02.10.2026 09:00', '02.10.2026 10:00'])
        writer.writerow(['SYNTHETIC', 'EXCLUDED', '', '', '', ''])
    dest = tmp_path / 'processed'
    if profile == 'pre':
        pre_reports.process(raw, dest, {'INCLUDED'})
    else:
        module = flow_reports if profile == 'flow' else fish_reports
        module.process(raw, raw, dest, {'INCLUDED'})
    with (dest / 'resultater.csv').open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle, delimiter=';'))
    assert [row['Analyse'] for row in rows] == ['INCLUDED']
    assert rows[0]['Rapportgruppe'] == ''
    assert rows[0]['Svarfrist'] == ''
    assert rows[0]['Pris2026NOK'] == ''
    if profile == 'pre':
        assert rows[0]['Totalstatus'] == 'Gyldig'
        assert rows[0]['Totalnormstatus'] == 'Ingen norm'
        assert rows[0]['Aktivitetstype'] == ''
    if profile == 'fish':
        assert rows[0]['Svartid status'] == 'Gyldig'
        assert rows[0]['Normstatus'] == 'Ikke beregnet'


def test_all_six_runtime_profiles_are_ready_with_only_external_json(tmp_path):
    keys = ('hemato', 'solide', 'flow', 'fish', 'pre', 'lege')
    private, public = tmp_path / 'private', tmp_path / 'public'
    private.mkdir()
    public.mkdir()
    service = DefaultServices(tmp_path / 'settings.json')
    service.save_settings_fields({
        'sensitive_root': str(private), 'sharepoint_root': str(public),
        'lvms_url': 'https://example.test/lvms',
        **{f'enabled_{key}': 'true' for key in keys},
        **{f'config_{key}': str(default_unit_file(key)) for key in keys},
    })
    system = service._build_system(require_statistics=True, require_lvms=False)
    assert set(system.statistics_processors) == set(keys)
    assert set(system.backlog_processors) == {'hemato', 'solide'}
    assert system.capability_errors == {}
    assert system.database.path == private / 'database' / 'molstat.sqlite3'
    assert system.work_root == private / 'data' / 'processed'
    assert not (private / 'config').exists()
    assert not (private / 'work').exists()


def test_consumed_fetch_folder_is_removed_only_after_last_download(tmp_path):
    from molstat.archive import remove_archived_download
    folder = tmp_path / 'data/raw/.jobs/synthetic/rådata'
    folder.mkdir(parents=True)
    first, second = folder / 'first.csv', folder / 'second.csv'
    first.write_bytes(b'first')
    second.write_bytes(b'second')
    (folder.parent / 'jobs.json').write_text('{}')
    remove_archived_download(first, tmp_path)
    assert second.read_bytes() == b'second'
    remove_archived_download(second, tmp_path)
    assert not folder.parent.exists()


def test_report_specific_codes_do_not_get_dropped_or_cross_roles(tmp_path):
    import csv
    from molstat._statistics.flow_reports import process
    path = tmp_path / 'source.csv'
    path.write_text('Sample ID;Analyse;Tidspunkt analysebestilling\nS1;ORDER;01.10.2026 08:00\nS2;RESULT;01.10.2026 08:00\n', encoding='cp1252')
    out = tmp_path / 'out'
    process(path, path, out, {'antall': {'ORDER'}, 'resultater': {'RESULT'}})
    def codes(name):
        with (out / name).open(encoding='utf-8-sig') as handle:
            return [row['Analyse'] for row in csv.DictReader(handle, delimiter=';')]
    assert codes('antall.csv') == ['ORDER']
    assert codes('resultater.csv') == ['RESULT']
