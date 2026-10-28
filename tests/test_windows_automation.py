import json

from molstat.services import DefaultServices
from molstat.windows_automation import retire_legacy_launchers


def test_cleanup_retires_only_recognized_old_launchers_without_executables(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Windows executables must not be invoked")

    monkeypatch.setattr("subprocess.run", forbidden)
    for name, command in (("statistics", "run statistics"), ("backlog", "run backlog"), ("board", "serve")):
        (tmp_path / f"{name}.cmd").write_text(
            '@echo off\nsetlocal\n"python.exe" -m molstat.cli '
            f'{command} --settings "settings.json"\nexit /b %ERRORLEVEL%\n', encoding="utf-8")
    (tmp_path / "settings.json").write_text("{}")
    (tmp_path / "unrelated.cmd").write_text("keep")
    retire_legacy_launchers(tmp_path)
    retire_legacy_launchers(tmp_path)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["settings.json", "unrelated.cmd"]


def test_cleanup_preserves_custom_scripts_and_absent_directories(tmp_path):
    custom = tmp_path / "statistics.cmd"
    custom.write_text("custom user command", encoding="utf-8")
    retire_legacy_launchers(tmp_path)
    retire_legacy_launchers(tmp_path / "missing")
    assert custom.read_text() == "custom user command"


def test_retired_install_command_never_creates_tasks(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("Windows executables must not be invoked")

    monkeypatch.setattr("subprocess.run", forbidden)
    assert DefaultServices(tmp_path / "settings.json").install_automation() == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "retired"
    assert "Innstillinger" in result["message"]
    assert not list(tmp_path.iterdir())
