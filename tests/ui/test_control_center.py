from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFileDialog, QPushButton, QStackedWidget

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


class RefreshingSettingsStore(FakeSettingsStore):
    def __init__(self, orchestrator, board, error: str | None = None) -> None:
        super().__init__()
        self.runtime = (orchestrator, board, error)

    def refresh_gui_runtime(self):
        return self.runtime


class DiagnosticSettingsStore(FakeSettingsStore):
    def diagnostic_messages(self) -> tuple[str, ...]:
        return ("statistics_run_failed: RuntimeError",)


class FailingOrchestrator:
    def run(self, kind: str, trigger: str) -> JobResult:
        return JobResult(kind, "failed", {})


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


def test_settings_browse_buttons_fill_directory_and_lookup_paths(
    qtbot, monkeypatch
) -> None:
    window = MainWindow(FakeOrchestrator(), None, FakeBoardController())
    qtbot.addWidget(window)

    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: "K:/sensitiv/valgt",
    )
    sensitive_browse = window.findChild(QPushButton, "browse-sensitive-root")
    assert sensitive_browse is not None
    qtbot.mouseClick(sensitive_browse, Qt.MouseButton.LeftButton)
    assert window.settings_page.sensitive_root.text() == "K:/sensitiv/valgt"

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: ("K:/sensitiv/Analyse_lookup.xlsx", "Excel (*.xlsx)"),
    )
    hemato_browse = window.findChild(QPushButton, "browse-lookup-hemato")
    assert hemato_browse is not None
    qtbot.mouseClick(hemato_browse, Qt.MouseButton.LeftButton)
    assert (
        window.settings_page.lookup_hemato.text()
        == "K:/sensitiv/Analyse_lookup.xlsx"
    )


def test_settings_browse_buttons_are_accessible(qtbot) -> None:
    window = MainWindow(FakeOrchestrator(), None, FakeBoardController())
    qtbot.addWidget(window)

    for name in (
        "browse-sensitive-root",
        "browse-sharepoint-root",
        "browse-lookup-hemato",
        "browse-lookup-solide",
    ):
        button = window.findChild(QPushButton, name)
        assert button is not None
        assert button.accessibleName()
        assert button.minimumHeight() >= 44


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


def test_saving_settings_reconfigures_jobs_without_restart(qtbot) -> None:
    orchestrator = FakeOrchestrator()
    board = FakeBoardController()
    store = RefreshingSettingsStore(orchestrator, board)
    window = MainWindow(None, store, None)
    qtbot.addWidget(window)

    qtbot.mouseClick(window.settings_page.save_button, Qt.MouseButton.LeftButton)

    assert window.orchestrator is orchestrator
    assert window.board_controller is board
    assert "klar" in window.statusBar().currentMessage().casefold()


def test_configuration_error_is_visible_in_diagnostics(qtbot) -> None:
    window = MainWindow(
        None,
        None,
        None,
        configuration_error="ValueError: Lookup-fil mangler.",
    )
    qtbot.addWidget(window)

    assert "Lookup-fil mangler" in window.diagnostics.log.toPlainText()


def test_failed_manual_job_refreshes_safe_diagnostics(qtbot) -> None:
    window = MainWindow(
        FailingOrchestrator(),
        DiagnosticSettingsStore(),
        FakeBoardController(),
    )
    qtbot.addWidget(window)
    button = window.findChild(QPushButton, "run-statistics")

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: button.isEnabled(), timeout=3000)
    assert "statistics_run_failed: RuntimeError" in (
        window.diagnostics.log.toPlainText()
    )
