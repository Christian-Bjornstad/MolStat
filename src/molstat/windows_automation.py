from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable
from xml.sax.saxutils import escape


STATISTICS_TASK_NAME = "MolStat - daglig statistikk"
BACKLOG_TASK_NAME = "MolStat - restansehenting"
BOARD_TASK_NAME = "MolStat - tavleserver"
_TASK_NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"


@dataclass(frozen=True, slots=True)
class AutomationPaths:
    app_root: Path
    project_root: Path
    settings_path: Path
    python_executable: Path


@dataclass(frozen=True, slots=True)
class AutomationResult:
    statistics_task: str
    backlog_task: str
    board_task: str


def default_automation_paths(
    *, project_root: Path, settings_path: Path, env: dict[str, str] | None = None
) -> AutomationPaths:
    active_env = dict(os.environ) if env is None else env
    local_text = str(active_env.get("LOCALAPPDATA") or "").strip()
    local_root = Path(local_text) if local_text else Path.home() / "AppData" / "Local"
    return AutomationPaths(
        app_root=local_root / "MolStat",
        project_root=Path(project_root).resolve(),
        settings_path=Path(settings_path).resolve(),
        python_executable=Path(sys.executable).resolve(),
    )


def install_automation(
    paths: AutomationPaths,
    *,
    username: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> AutomationResult:
    active_user = username or os.environ.get("USERNAME")
    domain = os.environ.get("USERDOMAIN")
    if active_user and domain and "\\" not in active_user:
        active_user = f"{domain}\\{active_user}"
    if not active_user:
        raise RuntimeError("Fant ikke Windows-brukeren som skal eie oppgavene.")

    launchers = _write_launchers(paths)
    definitions = (
        (
            STATISTICS_TASK_NAME,
            paths.app_root / "statistics-task.xml",
            _task_xml(active_user, launchers["statistics"], range(5, 6)),
        ),
        (
            BACKLOG_TASK_NAME,
            paths.app_root / "backlog-task.xml",
            _task_xml(active_user, launchers["backlog"], range(6, 19)),
        ),
        (
            BOARD_TASK_NAME,
            paths.app_root / "board-task.xml",
            _task_xml(active_user, launchers["board"], None),
        ),
    )
    for name, xml_path, content in definitions:
        xml_path.write_text(content, encoding="utf-16")
        _register_task(name, xml_path, runner)
    return AutomationResult(
        STATISTICS_TASK_NAME,
        BACKLOG_TASK_NAME,
        BOARD_TASK_NAME,
    )


def _write_launchers(paths: AutomationPaths) -> dict[str, Path]:
    paths.app_root.mkdir(parents=True, exist_ok=True)
    commands = {
        "statistics": "run statistics",
        "backlog": "run backlog",
        "board": "serve",
    }
    result: dict[str, Path] = {}
    for name, command in commands.items():
        path = paths.app_root / f"{name}.cmd"
        log_path = paths.app_root / f"{name}.log"
        path.write_text(
            "@echo off\nsetlocal\n"
            f"cd /d {_cmd_quote(paths.project_root)}\n"
            f"{_cmd_quote(paths.python_executable)} -m molstat.cli {command} "
            f"--settings {_cmd_quote(paths.settings_path)} >> {_cmd_quote(log_path)} 2>&1\n"
            "exit /b %ERRORLEVEL%\n",
            encoding="utf-8",
        )
        result[name] = path
    return result


def _cmd_quote(value: Path | str) -> str:
    return f'"{str(value).replace("%", "%%")}"'


def _task_xml(username: str, command: Path, hours: range | None) -> str:
    if hours is None:
        triggers = (
            "<LogonTrigger><Enabled>true</Enabled>"
            f"<UserId>{escape(username)}</UserId></LogonTrigger>"
        )
        limit = "PT0S"
    else:
        day = date.today().isoformat()
        triggers = "".join(
            "<CalendarTrigger>"
            f"<StartBoundary>{day}T{hour:02d}:00:00</StartBoundary>"
            "<Enabled>true</Enabled><ScheduleByDay><DaysInterval>1</DaysInterval>"
            "</ScheduleByDay></CalendarTrigger>"
            for hour in hours
        )
        limit = "PT30M"
    return (
        '<?xml version="1.0" encoding="UTF-16"?>'
        f'<Task version="1.4" xmlns="{_TASK_NS}"><Triggers>{triggers}</Triggers>'
        '<Principals><Principal id="Author">'
        f"<UserId>{escape(username)}</UserId><LogonType>InteractiveToken</LogonType>"
        "<RunLevel>LeastPrivilege</RunLevel></Principal></Principals>"
        "<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>"
        "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"
        "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>"
        "<StartWhenAvailable>true</StartWhenAvailable>"
        "<RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>"
        f"<ExecutionTimeLimit>{limit}</ExecutionTimeLimit><Enabled>true</Enabled></Settings>"
        '<Actions Context="Author"><Exec>'
        f"<Command>{escape(str(command))}</Command>"
        "</Exec></Actions></Task>"
    )


def _register_task(
    name: str,
    xml_path: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    result = runner(
        ["schtasks.exe", "/Create", "/TN", name, "/XML", str(xml_path), "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "ukjent feil").strip()
        raise RuntimeError(f"Kunne ikke opprette «{name}»: {detail}")
