from threading import Event, get_ident

from PyQt6.QtCore import QDateTime, Qt

from molstat.modules import DEFAULT_UNITS, UnitDefinition, UnitRegistry
from molstat.orchestrator import CapabilityResult, JobResult
from molstat.ui.app import MainWindow


class ReviewStore:
    def load_settings_fields(self):
        return {f"enabled_{unit.key}": "true" if unit.key in {"hemato", "solide"} else "false"
                for unit in DEFAULT_UNITS.active()}


def test_removed_capability_history_does_not_mark_current_unit_failed(qtbot):
    class History:
        def capability_statuses(self):
            return (
                CapabilityResult("hemato", "statistics", "succeeded", {"rows": 3}),
                CapabilityResult("hemato", "backlog", "failed", {}, "Old backlog error"),
            )

    class MutableDefinitions(ReviewStore):
        registry = DEFAULT_UNITS

        def unit_definitions(self):
            return self.registry

    store = MutableDefinitions()
    window = MainWindow(History(), store)
    qtbot.addWidget(window)
    card = window.overview.unit_cards["hemato"]
    assert "Delvis feil" in card.status_label.text()
    original = DEFAULT_UNITS.require("hemato")
    statistics_only = UnitDefinition("hemato", "Hemato", "active", (original.capability("statistics"),))
    store.registry = UnitRegistry((statistics_only, DEFAULT_UNITS.require("solide")))
    window._refresh_overview_status()
    assert "backlog" not in card.capability_status_labels
    assert "Fullført" in card.status_label.text()
    assert "feil" not in card.status_label.text().casefold()


def test_manual_import_works_without_automatic_runtime_and_closes_after_worker(qtbot, tmp_path):
    started, release = Event(), Event()
    main_thread = get_ident()

    class ManualOnly(ReviewStore):
        worker_thread = None

        def manual_import_available_jobs(self, unit):
            return ("statistics",)

        def manual_import_roles(self, unit, kind):
            return ("resultater",)

        def manual_import(self, plan):
            self.worker_thread = get_ident()
            started.set()
            release.wait(3)
            return JobResult(plan.unit_key, "succeeded", {"rows": 1}, capability_results=(
                CapabilityResult(plan.unit_key, "statistics", "succeeded", {"rows": 1}),
            ))

    store = ManualOnly()
    window = MainWindow(None, store, configuration_error="LVMS setup unavailable")
    qtbot.addWidget(window)
    window.show()
    assert not window.overview.unit_cards["hemato"].run_button.isEnabled()
    assert window.overview.import_button.isEnabled()
    window.overview.import_button.click()
    source = tmp_path / "resultater.csv"
    source.write_text("A;B\n1;2\n", encoding="utf-8")
    window.import_page.file_fields["resultater"].setText(str(source))
    window.import_page.import_button.click()
    qtbot.waitUntil(started.is_set)
    try:
        assert store.worker_thread != main_thread
        assert not window.close()
        assert not window.settings_page.isEnabled()
    finally:
        release.set()
        qtbot.waitUntil(lambda: not window._workers)
    assert window.settings_page.isEnabled()
    assert window.import_page.import_button.isEnabled()
    assert "Fullført" in window.import_page.feedback.text()
    assert source.is_file()
    assert window.close()


def test_invalid_selected_unit_import_configuration_does_not_block_other_unit(qtbot):
    class SelectiveImport(ReviewStore):
        def manual_import_available_jobs(self, unit):
            if unit == "hemato":
                raise ValueError("Correct Hemato report definition")
            return ("statistics", "backlog")

        def manual_import_roles(self, unit, kind):
            return ("backlog",) if kind == "backlog" else ("antall", "resultater")

        def manual_import(self, plan):
            raise AssertionError("No import should start during configuration review")

    window = MainWindow(None, SelectiveImport())
    qtbot.addWidget(window)
    assert not window.import_page.import_button.isEnabled()
    assert "Hemato" in window.import_page.feedback.text()
    window.import_page.unit_combo.setCurrentIndex(window.import_page.unit_combo.findData("solide"))
    assert window.import_page.import_button.isEnabled()
    assert set(window.import_page.file_fields) == {"antall", "resultater"}
    window.import_page.job_combo.setCurrentIndex(window.import_page.job_combo.findData("backlog"))
    assert set(window.import_page.file_fields) == {"backlog"}


def test_runtime_definition_names_are_consistent_and_partial_registry_keeps_other_units(qtbot):
    class CustomStore(ReviewStore):
        original = DEFAULT_UNITS.require("solide")
        custom = UnitDefinition("solide", "Tumorlaboratoriet", "active", (
            *original.capabilities, DEFAULT_UNITS.require("hemato").capability("backlog"),
        ))
        definitions = UnitRegistry((custom, DEFAULT_UNITS.require("hemato")))

        def unit_definitions(self):
            return self.definitions

        def manual_import_available_jobs(self, unit):
            return ("statistics", "backlog")

        def manual_import_roles(self, unit, kind):
            return ("backlog",) if kind == "backlog" else ("resultater",)

    store = CustomStore()
    window = MainWindow(None, store)
    qtbot.addWidget(window)
    window.overview.unit_cards["solide"].settings_button.click()
    assert window.settings_page.unit_panels["solide"].heading_label.text() == "Tumorlaboratoriet"
    assert "restanse" in window.settings_page.unit_panels["solide"].capability_hint.text()
    window.import_page.unit_combo.setCurrentIndex(window.import_page.unit_combo.findData("solide"))
    assert window.import_page.unit_combo.currentText() == "Tumorlaboratoriet"
    assert window.overview.unit_cards["solide"].title_label.text() == "Tumorlaboratoriet"
    store.definitions = UnitRegistry((DEFAULT_UNITS.require("hemato"),))
    window._refresh_overview_status()
    assert window.overview.unit_cards["solide"].title_label.text() == "Tumorlaboratoriet"
    assert "Tumorlaboratoriet" in window.settings_page.unit_list.currentItem().text()
    assert window.import_page.unit_combo.currentText() == "Tumorlaboratoriet"


def test_persisted_capability_timestamp_is_rendered_locally_and_invalid_value_is_ignored(qtbot):
    timestamp = "2026-10-07T08:30:00+00:00"

    class History:
        def capability_statuses(self):
            return (
                CapabilityResult("hemato", "statistics", "succeeded", {"rows": 1}, finished_at=timestamp),
                CapabilityResult("hemato", "backlog", "failed", {}, "CSV_INVALID", finished_at="invalid-time"),
            )

    window = MainWindow(History(), ReviewStore())
    qtbot.addWidget(window)
    expected = QDateTime.fromString(timestamp, Qt.DateFormat.ISODate).toLocalTime().toString("dd.MM.yyyy HH:mm")
    labels = window.overview.unit_cards["hemato"].capability_status_labels
    assert f"Sist kjørt {expected}" in labels["statistics"].text()
    assert "invalid-time" not in labels["backlog"].text()
    assert "Sist kjørt" not in labels["backlog"].text()
