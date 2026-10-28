"""Retire our old Task Scheduler launchers without invoking Windows programs."""
from __future__ import annotations

import os
from pathlib import Path


def retire_legacy_launchers(app_root: Path | None = None) -> None:
    if app_root is None:
        local = os.environ.get("LOCALAPPDATA")
        app_root = (Path(local) if local else Path.home() / "AppData" / "Local") / "MolStat"
    # Only remove launchers bearing our generated command and header. Task
    # Scheduler entries may remain, but can no longer launch the old data jobs.
    for name, command in (("statistics", "run statistics"), ("backlog", "run backlog"), ("board", "serve")):
        path = app_root / f"{name}.cmd"
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except UnicodeError:
            continue
        if (content.startswith("@echo off\nsetlocal\n")
                and f"-m molstat.cli {command} --settings " in content
                and "exit /b %ERRORLEVEL%" in content):
            path.unlink()
