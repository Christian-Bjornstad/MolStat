import json
from pathlib import Path

import pytest

from molstat.unit_settings import load_unit_file, default_unit_file, activate_unit_file


def test_defaults_cover_separate_hemato_reports():
    unit = load_unit_file(default_unit_file("hemato"))
    assert set(unit.payload["statistics"]) == {"antall", "resultater", "ekstraksjon"}
    assert unit.payload["statistics"]["ekstraksjon"]["analysis_codes"] != unit.payload["statistics"]["antall"]["analysis_codes"]
    assert unit.payload["backlog"]["analyses"]["analyses"]


@pytest.mark.parametrize("contents,code", [
    ('{"key":"hemato" "schema_version":1}', "CONFIG_SYNTAX"),
    ('{"key":"hemato","key":"solide"}', "CONFIG_INVALID"),
])
def test_bad_json_has_specific_diagnostic(tmp_path, contents, code):
    path = tmp_path / "unit.json"
    path.write_text(contents)
    with pytest.raises(ValueError, match=code):
        load_unit_file(path)


def test_invalid_import_keeps_active_file(tmp_path):
    root = tmp_path / "config"
    active = activate_unit_file(default_unit_file("hemato"), root, "hemato")
    before = active.read_bytes()
    bad = tmp_path / "bad.json"
    payload = json.loads(before)
    payload["statistics"]["antall"]["analysis_codes"] = ["CALR-OU", "CALR-OU"]
    bad.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        activate_unit_file(bad, root, "hemato")
    assert active.read_bytes() == before


def test_unknown_fields_and_csv_delimiter_are_rejected(tmp_path):
    payload = json.loads(default_unit_file("hemato").read_text(encoding="utf-8"))
    payload["backlog"]["columns"]["delimiter"] = ",;"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="delimiter"):
        load_unit_file(path)
    payload["backlog"]["columns"]["delimiter"] = ";"
    payload["statistics"]["antall"]["analysis_codez"] = []
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="analysis_codez"):
        load_unit_file(path)


def test_changed_file_produces_new_snapshot(tmp_path):
    path = tmp_path / "hemato.json"
    path.write_bytes(default_unit_file("hemato").read_bytes())
    first = load_unit_file(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["statistics"]["antall"]["analysis_codes"].append("SYNTHETIC-OU")
    path.write_text(json.dumps(payload))
    second = load_unit_file(path)
    assert first.digest != second.digest
    assert "SYNTHETIC-OU" not in first.unit.reports[0].analysis_codes
    assert "SYNTHETIC-OU" in second.unit.reports[0].analysis_codes


def test_active_snapshot_changes_only_between_runs(tmp_path):
    from molstat.unit_settings import load_active_units, materialize_snapshot
    active = activate_unit_file(default_unit_file("hemato"), tmp_path / "config", "hemato")
    first = load_active_units(tmp_path, {}, ("hemato",))
    snapshot = materialize_snapshot(tmp_path, first)
    before = (snapshot / "units.json").read_bytes()
    payload = json.loads(active.read_text(encoding="utf-8"))
    payload["statistics"]["antall"]["analysis_codes"].append("SYNTHETIC-OU")
    active.write_text(json.dumps(payload))
    second = materialize_snapshot(tmp_path, load_active_units(tmp_path, {}, ("hemato",)))
    assert second != snapshot
    assert (snapshot / "units.json").read_bytes() == before


def test_upgrade_preserves_edited_legacy_codes(tmp_path):
    from molstat.unit_settings import upgrade_source
    import shutil
    legacy = tmp_path / "old"
    shutil.copytree(Path("config"), legacy)
    path = legacy / "units.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["units"]["hemato"]["analysis_codes"].append("CUSTOM-OU")
    path.write_text(json.dumps(payload))
    before = path.read_bytes()
    migrated = load_unit_file(upgrade_source(tmp_path / "sensitive", "hemato", legacy))
    assert "CUSTOM-OU" in migrated.payload["statistics"]["antall"]["analysis_codes"]
    assert path.read_bytes() == before


def test_backlog_report_requires_nonempty_groups(tmp_path):
    payload = json.loads(default_unit_file("hemato").read_text(encoding="utf-8"))
    payload["backlog"]["report"]["report_groups"] = []
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="report_groups"):
        load_unit_file(path)


def test_settings_persist_validated_unit_file_and_invalid_replacement_is_atomic(tmp_path):
    from molstat.services import DefaultServices
    service = DefaultServices(tmp_path / "settings.json")
    sensitive = tmp_path / "sensitive"
    sharepoint = tmp_path / "sharepoint"
    sensitive.mkdir(); sharepoint.mkdir()
    lookup = tmp_path / "lookup.xlsx"
    lookup.write_bytes(b"synthetic")
    values = {"sensitive_root": str(sensitive), "sharepoint_root": str(sharepoint),
              "lvms_url": "https://lvms.example.invalid", "lookup_hemato": str(lookup),
              "enabled_solide": "false", "config_hemato": str(default_unit_file("hemato"))}
    service.save_settings_fields(values)
    active = service.settings.unit_config_paths["hemato"]
    assert active.is_relative_to(sensitive / "config")
    before = service.settings_path.read_bytes()
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version":')
    with pytest.raises(ValueError, match="CONFIG_SYNTAX"):
        service.save_settings_fields({**values, "config_hemato": str(bad)})
    assert service.settings_path.read_bytes() == before
    assert service.settings.unit_config_paths["hemato"] == active
