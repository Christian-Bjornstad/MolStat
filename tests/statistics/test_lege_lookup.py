from pathlib import Path
from dataclasses import replace

import pytest

from molstat._statistics.lege_lookup import default_lege_lookup_path, validate_lege_lookup
from molstat.services import DefaultServices


def test_lege_lookup_accepts_supplied_csv_format(tmp_path: Path) -> None:
    path = tmp_path / "lege_lookup.csv"
    path.write_text(
        "Brukernavn,Navn,Faggruppe\nESP,Eva Sigstad,CYT/SARKOM/MAMMA\n"
        "UXYSGA,Øystein Garred,HEMATO\n",
        encoding="cp1252",
    )
    assert validate_lege_lookup(path) == 2


def test_bundled_lege_lookup_contains_supplied_roster() -> None:
    assert validate_lege_lookup(default_lege_lookup_path()) == 39


def test_existing_pathology_settings_without_lookup_use_bundled_roster(tmp_path: Path) -> None:
    sensitive = tmp_path / "sensitive"
    sharepoint = tmp_path / "sharepoint"
    sensitive.mkdir()
    sharepoint.mkdir()
    services = DefaultServices(tmp_path / "settings.json")
    services.save_settings_fields({
        "sensitive_root": str(sensitive),
        "sharepoint_root": str(sharepoint),
        "lvms_url": "https://lvms.example.invalid/clims/",
        "enabled_hemato": "false", "enabled_solide": "false",
        "enabled_lege": "true",
    })
    services.settings = replace(services.settings, statistics_lookup_paths={})
    system = services._build_system(require_statistics=True)
    assert system.statistics_fetch.__self__.lege_lookup_path == default_lege_lookup_path()
    assert system.statistics_processors["lege"].lookup_path == default_lege_lookup_path()
    assert services.load_settings_fields()["lookup_lege"] == str(default_lege_lookup_path())


@pytest.mark.parametrize("data", [
    "Brukernavn,Navn,Faggruppe\nESP,Eva,HEMATO\nESP,Else,GYN/URO\n",
    "Brukernavn,Navn,Faggruppe\nESP,=HYPERLINK(1),HEMATO\n",
    "Brukernavn,Navn\nESP,Eva\n",
])
def test_lege_lookup_rejects_invalid_roster(tmp_path: Path, data: str) -> None:
    path = tmp_path / "lege_lookup.csv"
    path.write_text(data, encoding="utf-8")
    with pytest.raises(ValueError, match="Legeregisteret"):
        validate_lege_lookup(path)


def test_settings_store_selected_lege_lookup_snapshot(tmp_path: Path) -> None:
    sensitive = tmp_path / "sensitive"
    sharepoint = tmp_path / "sharepoint"
    sensitive.mkdir()
    sharepoint.mkdir()
    roster = tmp_path / "lege_lookup.csv"
    roster.write_text("Brukernavn,Navn,Faggruppe\nESP,Eva Sigstad,HEMATO\n", encoding="cp1252")
    services = DefaultServices(tmp_path / "settings.json")

    services.save_settings_fields({
        "sensitive_root": str(sensitive),
        "sharepoint_root": str(sharepoint),
        "lvms_url": "https://lvms.example.invalid/clims/",
        "enabled_hemato": "false", "enabled_solide": "false",
        "enabled_lege": "true", "lookup_lege": str(roster),
    })

    stored = services.settings.statistics_lookup_paths["lege"]
    assert stored.is_relative_to(sensitive / "config" / "lookups" / "lege")
    assert stored.read_bytes() == roster.read_bytes()
    assert services.load_settings_fields()["lookup_lege"] == str(stored)
    assert services._build_system(require_statistics=True).statistics_processors["lege"].lookup_path == stored


def test_settings_reject_invalid_lege_lookup(tmp_path: Path) -> None:
    sensitive = tmp_path / "sensitive"
    sharepoint = tmp_path / "sharepoint"
    sensitive.mkdir()
    sharepoint.mkdir()
    roster = tmp_path / "bad.csv"
    roster.write_text("Wrong,Columns\nA,B\n", encoding="utf-8")
    services = DefaultServices(tmp_path / "settings.json")

    with pytest.raises(ValueError, match="Legeregisteret"):
        services.save_settings_fields({
            "sensitive_root": str(sensitive),
            "sharepoint_root": str(sharepoint),
            "lvms_url": "https://lvms.example.invalid/clims/",
            "enabled_hemato": "false", "enabled_solide": "false",
            "enabled_lege": "true", "lookup_lege": str(roster),
        })
