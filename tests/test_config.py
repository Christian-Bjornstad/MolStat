from pathlib import Path

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
    )

    expected.save(settings_path)

    assert MolStatSettings.load(settings_path) == expected
