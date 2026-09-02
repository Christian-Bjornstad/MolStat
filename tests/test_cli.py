import json
from pathlib import Path

from molstat.cli import main
from molstat.config import MolStatSettings


def test_check_config_returns_zero_for_valid_settings(
    tmp_path: Path, capsys
) -> None:
    settings_path = tmp_path / "settings.json"
    MolStatSettings(sensitive_root=tmp_path / "sensitive").save(settings_path)

    result = main(["check-config", "--settings", str(settings_path)])

    assert result == 0
    assert json.loads(capsys.readouterr().out) == {"status": "ok"}


def test_check_config_returns_two_without_printing_paths(
    tmp_path: Path, capsys
) -> None:
    settings_path = tmp_path / "settings.json"
    MolStatSettings(
        sensitive_root=tmp_path,
        sharepoint_root=tmp_path,
    ).save(settings_path)

    result = main(["check-config", "--settings", str(settings_path)])

    assert result == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "invalid"
    assert str(tmp_path) not in str(output)
