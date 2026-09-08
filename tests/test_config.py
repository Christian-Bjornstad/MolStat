from pathlib import Path

import pytest

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
        power_bi_report_url="https://app.powerbi.com/groups/me/reports/report-id",
    )

    expected.save(settings_path)

    assert MolStatSettings.load(settings_path) == expected


@pytest.mark.parametrize(
    "url",
    (
        "http://app.powerbi.com/groups/me/reports/id",
        "https://example.invalid/groups/me/reports/id",
        "https://user@app.powerbi.com/groups/me/reports/id",
        "https://app.powerbi.com:8443/groups/me/reports/id",
    ),
)
def test_settings_reject_unsafe_power_bi_report_url(
    tmp_path: Path, url: str
) -> None:
    settings = MolStatSettings(
        sensitive_root=tmp_path / "sensitive",
        power_bi_report_url=url,
    )

    assert settings.validate() == (
        "Power BI-lenken må være en HTTPS-lenke på app.powerbi.com.",
    )
