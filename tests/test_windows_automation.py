import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from molstat.windows_automation import (
    BACKLOG_TASK_NAME,
    BOARD_TASK_NAME,
    STATISTICS_TASK_NAME,
    AutomationPaths,
    install_automation,
)


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, command, **kwargs):
        self.calls.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="SUCCESS", stderr="")


def _paths(tmp_path: Path) -> AutomationPaths:
    return AutomationPaths(
        app_root=tmp_path / "local" / "MolStat",
        project_root=tmp_path / "MolStat",
        settings_path=tmp_path / "local" / "MolStat" / "settings.json",
        python_executable=Path(r"C:\Python\python.exe"),
    )


def _trigger_hours(xml_path: Path) -> list[str]:
    root = ET.parse(xml_path).getroot()
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    starts = root.findall(".//t:CalendarTrigger/t:StartBoundary", ns)
    return [str(node.text)[-8:] for node in starts]


def test_install_registers_statistics_backlog_and_board_tasks(tmp_path: Path) -> None:
    runner = RecordingRunner()

    result = install_automation(
        _paths(tmp_path), username="DOMAIN\\bruker", runner=runner
    )

    assert result.statistics_task == STATISTICS_TASK_NAME
    assert result.backlog_task == BACKLOG_TASK_NAME
    assert result.board_task == BOARD_TASK_NAME
    assert [call[3] for call in runner.calls] == [
        STATISTICS_TASK_NAME,
        BACKLOG_TASK_NAME,
        BOARD_TASK_NAME,
    ]


def test_task_xml_has_exact_schedule_and_never_overlaps(tmp_path: Path) -> None:
    install_automation(
        _paths(tmp_path), username="DOMAIN\\bruker", runner=RecordingRunner()
    )

    assert _trigger_hours(_paths(tmp_path).app_root / "statistics-task.xml") == [
        "05:00:00"
    ]
    assert _trigger_hours(_paths(tmp_path).app_root / "backlog-task.xml") == [
        f"{hour:02d}:00:00" for hour in range(6, 19)
    ]
    root = ET.parse(_paths(tmp_path).app_root / "backlog-task.xml").getroot()
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    assert root.findtext(".//t:MultipleInstancesPolicy", namespaces=ns) == "IgnoreNew"
    assert root.findtext(".//t:LogonType", namespaces=ns) == "InteractiveToken"


def test_launchers_use_one_molstat_cli(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    install_automation(paths, username="DOMAIN\\bruker", runner=RecordingRunner())

    statistics = (paths.app_root / "statistics.cmd").read_text(encoding="utf-8")
    backlog = (paths.app_root / "backlog.cmd").read_text(encoding="utf-8")
    board = (paths.app_root / "board.cmd").read_text(encoding="utf-8")
    assert "-m molstat.cli run statistics" in statistics
    assert "-m molstat.cli run backlog" in backlog
    assert "-m molstat.cli serve" in board
