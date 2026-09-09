from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFileDialog, QPushButton, QStackedWidget

from molstat.orchestrator import JobResult
from molstat.ui.app import MainWindow
from molstat.ui.theme import COLORS, build_stylesheet


class FakeOrchestrator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def run(self, kind: str, trigger: str) -> JobResult:
        self.calls.append((kind, trigger))
        return JobResult(kind, "succeeded", {"rows": 4})


class FakeSettingsStore:
    def __init__(self) -> None:
        self.saved: dict[str, str] | None = None
        self.exported: Path | None = None
        self.imported: Path | None = None

    def load_settings_fields(self) -> dict[str, str]:
        return {
            "sensitive_root": "K:/sensitiv",
            "sharepoint_root": "C:/SharePoint/MolStat",
            "lvms_url": "https://lvms.example.invalid/app",
            "lookup_hemato": "K:/sensitiv/lookup-hemato.xlsx",
            "lookup_solide": "K:/sensitiv/lookup-solide.xlsx",
            "enabled_hemato": "true",
            "enabled_solide": "true",
        }

    def save_settings_fields(self, values: dict[str, str]) -> None:
        self.saved = values

    def export_settings(self, path: Path) -> None:
        self.exported = path

    def import_settings(self, path: Path) -> tuple[str, ...]:
        self.imported = path
        return ("SharePoint-mappe",)


class RefreshingSettingsStore(FakeSettingsStore):
    def __init__(self, orchestrator, error: str | None = None) -> None:
        super().__init__()
        self.runtime = (orchestrator, error)

    def refresh_gui_runtime(self):
        return self.runtime


class DisabledSolideSettingsStore(FakeSettingsStore):
    def load_settings_fields(self) -> dict[str, str]:
        values = super().load_settings_fields()
        values["enabled_solide"] = "false"
        return values


class DiagnosticSettingsStore(FakeSettingsStore):
    def diagnostic_messages(self) -> tuple[str, ...]:
        return ("statistics_run_failed: RuntimeError",)


class FailingOrchestrator:
    def run(self, kind: str, trigger: str) -> JobResult:
        return JobResult(kind, "failed", {})


def _contrast(first: str, second: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            value / 12.92
            if value <= 0.04045
            else ((value + 0.055) / 1.055) ** 2.4
            for value in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_theme_uses_accessible_power_bi_pastel_palette() -> None:
    assert COLORS == {
        "primary": "#F2C811",
        "background": "#FFF9E6",
        "muted": "#FFF3C4",
        "surface": "#FFFFFF",
        "foreground": "#2B2618",
        "muted_text": "#5C553D",
        "border": "#E6D17A",
        "focus": "#8A6A00",
        "success": "#1B7D3A",
        "warning": "#9A6A00",
        "danger": "#A4262C",
        "sidebar": "#3A321B",
    }
    assert _contrast(COLORS["foreground"], COLORS["background"]) >= 4.5
    assert _contrast(COLORS["muted_text"], COLORS["background"]) >= 4.5
    assert _contrast("#FFFFFF", COLORS["sidebar"]) >= 4.5
    assert _contrast(COLORS["focus"], COLORS["surface"]) >= 4.5
    assert f"border: 3px solid {COLORS['focus']}" in build_stylesheet()


def test_control_center_has_accessible_navigation_and_status(qtbot) -> None:
    window = MainWindow(FakeOrchestrator(), None)
    qtbot.addWidget(window)
    window.show()

    assert window.windowTitle() == "MolStat"
    assert window.minimumSize().width() >= 1024
    for object_name in (
        "nav-overview",
        "nav-settings",
        "nav-diagnostics",
        "run-all",
        "run-hemato",
        "run-solide",
    ):
        button = window.findChild(QPushButton, object_name)
        assert button is not None
        assert button.accessibleName()
        assert button.minimumHeight() >= 44

    assert window.findChild(QStackedWidget, "page-stack").currentWidget().objectName() == (
        "overview-page"
    )


def test_navigation_works_and_power_bi_action_is_removed(qtbot) -> None:
    window = MainWindow(FakeOrchestrator(), None)
    qtbot.addWidget(window)
    window.show()

    qtbot.mouseClick(window.findChild(QPushButton, "nav-settings"), Qt.MouseButton.LeftButton)
    assert window.findChild(QStackedWidget, "page-stack").currentWidget().objectName() == (
        "settings-page"
    )

    qtbot.mouseClick(window.findChild(QPushButton, "nav-overview"), Qt.MouseButton.LeftButton)
    assert window.findChild(QPushButton, "open-power-bi") is None


def test_manual_unit_job_dispatches_stable_target_and_reports_completion(qtbot) -> None:
    orchestrator = FakeOrchestrator()
    window = MainWindow(orchestrator, None)
    qtbot.addWidget(window)
    window.show()
    button = window.findChild(QPushButton, "run-hemato")

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: button.isEnabled(), timeout=3000)
    assert orchestrator.calls == [("hemato", "manual")]
    assert "fullført" in window.statusBar().currentMessage().casefold()


def test_overview_exposes_active_and_coming_units(qtbot) -> None:
    window = MainWindow(FakeOrchestrator(), None)
    qtbot.addWidget(window)

    assert "statistikk + restanse" in (
        window.findChild(object, "capabilities-hemato").text().casefold()
    )
    assert "statistikk" in (
        window.findChild(object, "capabilities-solide").text().casefold()
    )
    for key in ("lege", "flow", "pre", "hist"):
        button = window.findChild(QPushButton, f"run-{key}")
        assert button is not None
        assert button.isEnabled() is False
        assert "kommer" in button.text().casefold()
        assert button.accessibleName()


def test_run_all_and_solide_dispatch_explicit_targets(qtbot) -> None:
    orchestrator = FakeOrchestrator()
    window = MainWindow(orchestrator, None)
    qtbot.addWidget(window)

    all_button = window.findChild(QPushButton, "run-all")
    qtbot.mouseClick(all_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: all_button.isEnabled(), timeout=3000)
    solide = window.findChild(QPushButton, "run-solide")
    qtbot.mouseClick(solide, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: solide.isEnabled(), timeout=3000)

    assert orchestrator.calls == [("all", "manual"), ("solide", "manual")]


def test_disabled_unit_cannot_be_dispatched(qtbot) -> None:
    orchestrator = FakeOrchestrator()
    window = MainWindow(orchestrator, DisabledSolideSettingsStore())
    qtbot.addWidget(window)
    solide = window.findChild(QPushButton, "run-solide")

    assert solide.isEnabled() is False
    assert "deaktivert" in (
        window.overview.unit_cards["solide"].status_label.text().casefold()
    )


def test_settings_fields_have_labels_and_accessible_names(qtbot) -> None:
    window = MainWindow(FakeOrchestrator(), None)
    qtbot.addWidget(window)

    for name in (
        "sensitive-root",
        "sharepoint-root",
        "lvms-url",
    ):
        field = window.findChild(object, name)
        assert field is not None
        assert field.accessibleName()

    for key in ("hemato", "solide"):
        enabled = window.findChild(object, f"enabled-{key}")
        assert enabled is not None
        assert enabled.accessibleName()
        assert enabled.isChecked()


def test_settings_browse_buttons_fill_directory_and_lookup_paths(
    qtbot, monkeypatch
) -> None:
    window = MainWindow(FakeOrchestrator(), None)
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
    window = MainWindow(FakeOrchestrator(), None)
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
    window = MainWindow(FakeOrchestrator(), store)
    qtbot.addWidget(window)
    window.show()

    assert window.settings_page.sensitive_root.text() == "K:/sensitiv"
    window.settings_page.sharepoint_root.setText("C:/SharePoint/Ny")
    qtbot.mouseClick(
        window.settings_page.save_button, Qt.MouseButton.LeftButton
    )

    assert store.saved is not None
    assert store.saved["sharepoint_root"] == "C:/SharePoint/Ny"
    assert store.saved["enabled_hemato"] == "true"
    assert "power_bi_report_url" not in store.saved
    assert "lagret" in window.statusBar().currentMessage().casefold()


def test_settings_import_and_export_use_json_dialogs(qtbot, monkeypatch) -> None:
    store = FakeSettingsStore()
    window = MainWindow(FakeOrchestrator(), store)
    qtbot.addWidget(window)
    export_path = Path("C:/temp/molstat-innstillinger.json")
    import_path = Path("C:/temp/fra-annen-pc.json")

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(export_path), "JSON (*.json)"),
    )
    export_button = window.findChild(QPushButton, "export-settings")
    qtbot.mouseClick(export_button, Qt.MouseButton.LeftButton)
    assert store.exported == export_path

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(import_path), "JSON (*.json)"),
    )
    import_button = window.findChild(QPushButton, "import-settings")
    qtbot.mouseClick(import_button, Qt.MouseButton.LeftButton)
    assert store.imported == import_path
    assert "må velges" in window.statusBar().currentMessage().casefold()


def test_saving_settings_reconfigures_jobs_without_restart(qtbot) -> None:
    orchestrator = FakeOrchestrator()
    store = RefreshingSettingsStore(orchestrator)
    window = MainWindow(None, store)
    qtbot.addWidget(window)

    qtbot.mouseClick(window.settings_page.save_button, Qt.MouseButton.LeftButton)

    assert window.orchestrator is orchestrator
    assert "klar" in window.statusBar().currentMessage().casefold()


def test_configuration_error_is_visible_in_diagnostics(qtbot) -> None:
    window = MainWindow(
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
    )
    qtbot.addWidget(window)
    button = window.findChild(QPushButton, "run-hemato")

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: button.isEnabled(), timeout=3000)
    assert "statistics_run_failed: RuntimeError" in (
        window.diagnostics.log.toPlainText()
    )


def test_partial_run_has_clear_non_success_feedback(qtbot) -> None:
    class PartialOrchestrator:
        def run(self, kind: str, trigger: str) -> JobResult:
            return JobResult(
                kind,
                "partial",
                {"capabilities": 3, "succeeded": 2, "failed": 1},
            )

    window = MainWindow(PartialOrchestrator(), DiagnosticSettingsStore())
    qtbot.addWidget(window)
    button = window.findChild(QPushButton, "run-all")

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: button.isEnabled(), timeout=3000)
    assert "delvis" in window.statusBar().currentMessage().casefold()


def test_window_has_packaged_molstat_icon(qtbot) -> None:
    window = MainWindow(FakeOrchestrator(), FakeSettingsStore())
    qtbot.addWidget(window)

    assert window.windowIcon().isNull() is False
