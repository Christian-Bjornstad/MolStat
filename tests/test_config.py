import json
from pathlib import Path

import pytest

import molstat.config as config
from molstat.config import MolStatSettings


def test_settings_reject_same_sensitive_and_sharepoint_roots(tmp_path: Path) -> None:
    settings = MolStatSettings(
        sensitive_root=tmp_path,
        sharepoint_root=tmp_path,
    )

    assert settings.validate() == (
        "K-sensitiv og SharePoint må være ulike mapper.",
    )


def test_missing_sharepoint_is_allowed_until_publication(tmp_path: Path) -> None:
    settings = MolStatSettings(
        sensitive_root=tmp_path,
        sharepoint_root=None,
    )

    assert settings.validate() == ()


def test_settings_round_trip_json(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    expected = MolStatSettings(
        sensitive_root=tmp_path / "sensitive",
        sharepoint_root=tmp_path / "sharepoint",
        statistics_lookup_paths={
            "hemato": tmp_path / "lookup-hemato.xlsx",
            "solide": tmp_path / "lookup-solide.xlsx",
        },
        lvms_config_path=tmp_path / "lvms-config.json",
        enabled_units=("hemato",),
    )

    expected.save(settings_path)

    assert MolStatSettings.load(settings_path) == expected


def test_settings_load_ignores_removed_power_bi_report_url(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        '{"sensitive_root":"K:/sensitiv","power_bi_report_url":'
        '"https://app.powerbi.com/legacy"}',
        encoding="utf-8",
    )

    settings = MolStatSettings.load(settings_path)

    assert settings.sensitive_root == Path("K:/sensitiv")
    assert not hasattr(settings, "power_bi_report_url")


def test_transfer_payload_is_versioned_and_excludes_local_runtime_data(
    tmp_path: Path,
) -> None:
    settings = MolStatSettings(
        sensitive_root=tmp_path / "sensitiv",
        sharepoint_root=tmp_path / "sharepoint",
        lvms_url="https://lvms.example.invalid/clims/",
        lvms_config_path=tmp_path / "private-lvms.json",
        enabled_units=("hemato",),
        statistics_lookup_paths={"hemato": tmp_path / "oppslag.xlsx"},
    )

    payload = settings.to_transfer_payload()
    serialized = json.dumps(payload, ensure_ascii=False).casefold()

    assert payload["schema_version"] == config.SETTINGS_SCHEMA_VERSION == 2
    assert payload["units"]["hemato"]["enabled"] is True
    assert payload["units"]["solide"]["enabled"] is False
    for forbidden in (
        "lvms_config_path",
        "profile_directory",
        "cookie",
        "session",
        "cdp",
        "token",
    ):
        assert forbidden not in serialized


def test_transfer_file_round_trips_utf8_norwegian_paths(tmp_path: Path) -> None:
    transfer = tmp_path / "molstat-innstillinger.json"
    expected = MolStatSettings(
        sensitive_root=tmp_path / "K-sensitiv æøå",
        sharepoint_root=tmp_path / "Prøveflyt",
        statistics_lookup_paths={"hemato": tmp_path / "Oppslag prøve.xlsx"},
        enabled_units=("hemato",),
        statistics_hour=4,
        backlog_first_hour=7,
        backlog_last_hour=19,
        lvms_url="https://lvms.example.invalid/clims/",
    )

    expected.export_to(transfer)
    imported = MolStatSettings.import_from(transfer)

    assert imported == expected
    assert "æøå" in transfer.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "payload",
    (
        {"schema_version": 999},
        {"schema_version": 2, "units": {"ukjent": {"enabled": True}}},
        {"schema_version": 2, "units": {"hemato": {"enabled": "ja"}}},
    ),
)
def test_transfer_import_rejects_unknown_schema_units_and_types(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    transfer = tmp_path / "ugyldig.json"
    transfer.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        MolStatSettings.import_from(transfer)


def test_invalid_transfer_does_not_replace_existing_settings(tmp_path: Path) -> None:
    current_path = tmp_path / "settings.json"
    current = MolStatSettings(sensitive_root=tmp_path / "original")
    current.save(current_path)
    before = current_path.read_bytes()
    transfer = tmp_path / "bad.json"
    transfer.write_text('{"schema_version": 999}', encoding="utf-8")

    with pytest.raises(ValueError, match="skjemaversjon"):
        MolStatSettings.import_from(transfer)

    assert current_path.read_bytes() == before


def test_unversioned_settings_migrate_in_memory_with_active_defaults(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "legacy.json"
    settings_path.write_text(
        json.dumps(
            {
                "sensitive_root": "K:/sensitiv",
                "sharepoint_root": "S:/MolStat",
                "statistics_hour": 4,
                "backlog_first_hour": 7,
                "backlog_last_hour": 17,
                "statistics_lookup_paths": {
                    "hemato": "K:/lookup-hemato.xlsx",
                    "solide": "K:/lookup-solide.xlsx",
                },
                "lvms_url": "https://lvms.example.invalid/clims/",
            }
        ),
        encoding="utf-8",
    )

    settings = MolStatSettings.load(settings_path)

    assert settings.enabled_units == ("hemato", "solide")
    assert settings.statistics_hour == 4
    assert settings.backlog_first_hour == 7
    assert settings.statistics_lookup_paths["solide"] == Path(
        "K:/lookup-solide.xlsx"
    )
