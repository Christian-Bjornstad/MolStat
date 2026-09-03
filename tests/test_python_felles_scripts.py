from __future__ import annotations

import runpy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_installer_installs_editable_project_and_verifies_imports(tmp_path: Path) -> None:
    functions = runpy.run_path(str(ROOT / "install_python_felles.py"))
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "src" / "molstat").mkdir(parents=True)
    pip_calls: list[list[str]] = []
    imported: list[str] = []

    result = functions["install"](
        project_dir=tmp_path,
        user_site=tmp_path / "user-site",
        pip_main=lambda args: pip_calls.append(list(args)) or 0,
        importer=lambda name: imported.append(name) or object(),
    )

    assert result == 0
    assert pip_calls == [
        [
            "install",
            "--user",
            "--disable-pip-version-check",
            "-e",
            f"{tmp_path.resolve()}[dev]",
        ]
    ]
    assert imported == ["PyQt6", "websocket", "molstat"]


def test_start_dispatches_gui_with_local_settings_path(tmp_path: Path) -> None:
    functions = runpy.run_path(str(ROOT / "start_python_felles.py"))
    (tmp_path / "src" / "molstat").mkdir(parents=True)
    calls: list[list[str]] = []
    settings = tmp_path / "local" / "MolStat" / "settings.json"

    result = functions["start"](
        project_dir=tmp_path,
        user_site=tmp_path / "user-site",
        settings_file=settings,
        app_main=lambda args: calls.append(list(args)) or 0,
    )

    assert result == 0
    assert calls == [["gui", "--settings", str(settings)]]


@pytest.mark.parametrize(
    ("script_name", "stage"),
    [
        ("install_python_felles.py", "installer_start_failed"),
        ("start_python_felles.py", "molstat_start_failed"),
    ],
)
def test_main_logs_full_bootstrap_failure(
    tmp_path: Path, monkeypatch, script_name: str, stage: str
) -> None:
    functions = runpy.run_path(str(ROOT / script_name))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    result = functions["main"](project_dir=tmp_path / "missing")

    assert result == 1
    content = (
        tmp_path / "local" / "MolStat" / "logs" / "bootstrap.log"
    ).read_text(encoding="utf-8")
    assert stage in content
    assert "RuntimeError" in content
    assert "Traceback" in content


def test_python_felles_scripts_require_python_314() -> None:
    functions = runpy.run_path(str(ROOT / "start_python_felles.py"))

    if functions["sys"].version_info[:2] != (3, 14):
        with pytest.raises(RuntimeError, match="Python FELLES 3.14"):
            functions["activate_user_site"]()
