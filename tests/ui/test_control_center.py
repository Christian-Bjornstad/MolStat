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


class FakeSettingsStore:
    def __init__(self) -> None:
        self.saved: dict[str, str] | None = None

    def load_settings_fields(self) -> dict[str, str]:
        return {
            "sensitive_root": "K:/sensitiv",
            "sharepoint_root": "C:/SharePoint/MolStat",
            "lvms_url": "https://lvms.example.invalid/app",
            "lookup_hemato": "K:/sensitiv/lookup-hemato.xlsx",
            "lookup_solide": "K:/sensitiv/lookup-solide.xlsx",
        }

    def save_settings_fields(self, values: dict[str, str]) -> None:
        self.saved = values


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


def test_settings_are_loaded_and_saved_through_controller(qtbot) -> None:
    store = FakeSettingsStore()
    window = MainWindow(FakeOrchestrator(), store, FakeBoardController())
    qtbot.addWidget(window)
    window.show()

    assert window.settings_page.sensitive_root.text() == "K:/sensitiv"
    window.settings_page.sharepoint_root.setText("C:/SharePoint/Ny")
    qtbot.mouseClick(
        window.settings_page.save_button, Qt.MouseButton.LeftButton
    )

    assert store.saved is not None
    assert store.saved["sharepoint_root"] == "C:/SharePoint/Ny"
    assert "lagret" in window.statusBar().currentMessage().casefold()
