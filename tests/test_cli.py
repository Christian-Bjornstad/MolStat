import json
from pathlib import Path

import pytest

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
    invalid = MolStatSettings(
        sensitive_root=tmp_path,
        sharepoint_root=tmp_path,
    )
    # Simulate an externally edited/corrupt file; save() rejects this state.
    settings_path.write_text(json.dumps(invalid.to_transfer_payload()), encoding="utf-8")

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


@pytest.mark.parametrize("contents", ['{"sensitive_root":', '{"sensitive_root":42}', '[]', '\xff'])
def test_check_config_rejects_malformed_external_files_safely(tmp_path, capsys, contents):
    path = tmp_path / "settings.json"
    path.write_bytes(contents.encode("latin-1"))
    assert main(["check-config", "--settings", str(path)]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "invalid"
    assert str(tmp_path) not in captured.out
    assert not captured.err


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
