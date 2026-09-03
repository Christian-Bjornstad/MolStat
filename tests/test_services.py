from pathlib import Path

from molstat.services import DefaultServices


def test_first_launch_opens_with_empty_settings(tmp_path: Path) -> None:
    services = DefaultServices(tmp_path / "settings.json")

    assert services.load_settings_fields() == {
        "sensitive_root": "",
        "sharepoint_root": "",
        "lvms_url": "",
        "lookup_hemato": "",
        "lookup_solide": "",
    }
