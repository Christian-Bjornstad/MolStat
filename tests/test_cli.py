import json
from pathlib import Path

from molstat.cli import main
from molstat.config import MolStatSettings


class FakeServices:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def gui(self) -> int:
        self.calls.append(("gui", None))
        return 0

    def run(self, kind: str) -> int:
        self.calls.append(("run", kind))
        return 0

    def serve(self) -> int:
        self.calls.append(("serve", None))
        return 0

    def auto(self) -> int:
        self.calls.append(("auto", None))
        return 0

    def install_automation(self) -> int:
        self.calls.append(("install-automation", None))
        return 0


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


def test_check_config_handles_missing_settings_file(tmp_path: Path, capsys) -> None:
    result = main(["check-config", "--settings", str(tmp_path / "missing.json")])

    assert result == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "invalid",
        "errors": ["Innstillingsfil mangler."],
    }


def test_cli_dispatches_all_integrated_commands(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    MolStatSettings(sensitive_root=tmp_path / "sensitive").save(settings_path)
    services = FakeServices()

    assert main(["gui", "--settings", str(settings_path)], services=services) == 0
    assert main(
        ["run", "statistics", "--settings", str(settings_path)], services=services
    ) == 0
    assert main(
        ["run", "backlog", "--settings", str(settings_path)], services=services
    ) == 0
    assert main(["serve", "--settings", str(settings_path)], services=services) == 0
    assert main(["auto", "--settings", str(settings_path)], services=services) == 0
    assert main(
        ["install-automation", "--settings", str(settings_path)],
        services=services,
    ) == 0
    assert services.calls == [
        ("gui", None),
        ("run", "statistics"),
        ("run", "backlog"),
        ("serve", None),
        ("auto", None),
        ("install-automation", None),
    ]
