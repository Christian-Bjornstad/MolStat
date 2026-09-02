from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton, QStackedWidget

from molstat.orchestrator import JobResult
from molstat.ui.app import MainWindow


class FakeOrchestrator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def run(self, kind: str, trigger: str) -> JobResult:
        self.calls.append((kind, trigger))
        return JobResult(kind, "succeeded", {"rows": 4})


class FakeBoardController:
    def __init__(self) -> None:
        self.opened = False

    def open(self) -> None:
        self.opened = True


def test_control_center_has_accessible_navigation_and_status(qtbot) -> None:
    window = MainWindow(FakeOrchestrator(), None, FakeBoardController())
    qtbot.addWidget(window)
    window.show()

    assert window.windowTitle() == "MolStat"
    assert window.minimumSize().width() >= 1024
    for object_name in (
        "nav-overview",
        "nav-settings",
        "nav-diagnostics",
        "run-statistics",
        "run-backlog",
        "open-board",
    ):
        button = window.findChild(QPushButton, object_name)
        assert button is not None
        assert button.accessibleName()
        assert button.minimumHeight() >= 44

    assert window.findChild(QStackedWidget, "page-stack").currentWidget().objectName() == (
        "overview-page"
    )


def test_navigation_and_board_action_work_without_icons(qtbot) -> None:
    board = FakeBoardController()
    window = MainWindow(FakeOrchestrator(), None, board)
    qtbot.addWidget(window)
    window.show()

    qtbot.mouseClick(window.findChild(QPushButton, "nav-settings"), Qt.MouseButton.LeftButton)
    assert window.findChild(QStackedWidget, "page-stack").currentWidget().objectName() == (
        "settings-page"
    )

    qtbot.mouseClick(window.findChild(QPushButton, "nav-overview"), Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.findChild(QPushButton, "open-board"), Qt.MouseButton.LeftButton)
    assert board.opened is True


def test_manual_job_disables_buttons_and_reports_completion(qtbot) -> None:
    orchestrator = FakeOrchestrator()
    window = MainWindow(orchestrator, None, FakeBoardController())
    qtbot.addWidget(window)
    window.show()
    button = window.findChild(QPushButton, "run-statistics")

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: button.isEnabled(), timeout=3000)
    assert orchestrator.calls == [("statistics", "manual")]
    assert "fullført" in window.statusBar().currentMessage().casefold()


def test_settings_fields_have_labels_and_accessible_names(qtbot) -> None:
    window = MainWindow(FakeOrchestrator(), None, FakeBoardController())
    qtbot.addWidget(window)

    for name in ("sensitive-root", "sharepoint-root", "lvms-url"):
        field = window.findChild(object, name)
        assert field is not None
        assert field.accessibleName()
