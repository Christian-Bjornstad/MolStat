import pytest

from PyQt6.QtCore import QDate, Qt

from molstat.ui.dashboard import OverviewPage
from molstat.ui.diagnostics import DiagnosticsPage
from molstat.ui.settings import SettingsPage
from molstat.ui.import_page import ImportPage
from molstat.modules import DEFAULT_UNITS, UnitDefinition, UnitRegistry


def test_hist_is_absent_from_settings_and_manual_import(qtbot):
    settings = SettingsPage()
    importer = ImportPage()
    qtbot.addWidget(settings)
    qtbot.addWidget(importer)
    assert "hist" not in settings.config_fields
    assert "hist" not in settings.unit_panels
    assert importer.unit_combo.findData("hist") == -1


def test_settings_edits_only_selected_unit_and_keeps_other_drafts(qtbot):
    page = SettingsPage()
    qtbot.addWidget(page)
    page.resize(870, 700)
    page.show()
    page.config_fields["hemato"].setText("K:/drafts/hemato.json")
    page.select_unit("fish")
    assert page.unit_stack.currentWidget() is page.unit_panels["fish"]
    assert not page.unit_panels["hemato"].isVisible()
    page.config_fields["fish"].setText("K:/drafts/fish.json")
    page.tabs.setCurrentIndex(1)
    page.select_unit("hemato")
    assert page.tabs.currentIndex() == 0
    assert page.config_fields["hemato"].text() == "K:/drafts/hemato.json"
    assert page.config_fields["fish"].text() == "K:/drafts/fish.json"
    assert page.save_button.isVisible()


def test_unit_json_validation_reports_error_next_to_selected_file(qtbot, tmp_path):
    page = SettingsPage()
    qtbot.addWidget(page)
    source = tmp_path / "broken.json"
    source.write_text('{"schema_version": 1,', encoding="utf-8")
    page.config_fields["hemato"].setText(str(source))
    page.unit_panels["hemato"].validate_config()
    assert "CONFIG_SYNTAX" in page.unit_panels["hemato"].preview.text()
    assert page.config_fields["hemato"].property("tone") == "danger"
    assert page.unit_panels["fish"].preview.property("tone") != "danger"


def test_overview_search_activation_and_attention_filter_are_independent(qtbot):
    page = OverviewPage()
    qtbot.addWidget(page)
    page.resize(870, 700)
    page.show()
    page.set_enabled_units({"hemato", "fish"})
    assert page.unit_filter.currentData() == "active"
    assert not page.unit_cards["pre"].isVisible()
    page.unit_cards["fish"].set_status("Feilet", "Kontroller oppslaget")
    page.unit_filter.setCurrentIndex(page.unit_filter.findData("attention"))
    assert page.unit_cards["fish"].isVisible()
    assert not page.unit_cards["hemato"].isVisible()
    assert "1 trenger oppfølging" in page.summary_label.text()
    page.unit_search.setText("hemato")
    assert page.empty_label.isVisible()
    page.unit_filter.setCurrentIndex(page.unit_filter.findData("active"))
    assert page.unit_cards["hemato"].isVisible()
    assert not page.unit_cards["fish"].isVisible()
    assert not page.empty_label.isVisible()


def test_per_capability_status_does_not_overwrite_other_outcome(qtbot):
    page = OverviewPage()
    qtbot.addWidget(page)
    card = page.unit_cards["hemato"]
    card.set_capability_status("statistics", "Fullført", "4 rader")
    card.set_capability_status("backlog", "Feilet", "Kontroller restanseoppsettet")
    assert "Fullført" in card.capability_status_labels["statistics"].text()
    assert "Feilet" in card.capability_status_labels["backlog"].text()
    assert "Feilet" not in page.unit_cards["fish"].accessibleName()


def test_custom_runtime_definition_changes_visible_unit_capabilities(qtbot):
    page = OverviewPage()
    qtbot.addWidget(page)
    original = DEFAULT_UNITS.require("solide")
    custom = UnitDefinition("solide", "Solide med restanse", "active", (
        *original.capabilities, DEFAULT_UNITS.require("hemato").capability("backlog"),
    ))
    page.set_definitions(UnitRegistry((custom,)))
    card = page.unit_cards["solide"]
    assert card.unit is custom
    assert card.title_label.text() == "Solide med restanse"
    assert card.capability_label.text() == "Statistikk + restanse"
    card.set_capability_status("backlog", "Fullført", "8 rader")
    assert "8 rader" in card.capability_status_labels["backlog"].text()
    page.set_definitions(UnitRegistry((original,)))
    assert "backlog" not in card.capability_status_labels
    assert card.capability_label.text() == "Statistikk"


def test_custom_unit_names_and_capabilities_are_consistent_in_editing_and_import(qtbot):
    settings = SettingsPage()
    importing = ImportPage()
    qtbot.addWidget(settings)
    qtbot.addWidget(importing)
    original = DEFAULT_UNITS.require("solide")
    custom = UnitDefinition("solide", "Tumorlaboratoriet", "active", (
        *original.capabilities, DEFAULT_UNITS.require("hemato").capability("backlog"),
    ))
    definitions = UnitRegistry((custom,))
    settings.config_fields["solide"].setText("K:/local-draft.json")
    settings.set_definitions(definitions)
    importing.set_definitions(definitions)
    importing.set_enabled_units({"solide"})
    panel = settings.unit_panels["solide"]
    assert panel.heading_label.text() == "Tumorlaboratoriet"
    assert "restanse" in panel.capability_hint.text()
    assert settings.config_fields["solide"].text() == "K:/local-draft.json"
    settings.select_unit("solide")
    assert "Tumorlaboratoriet" in settings.unit_list.currentItem().text()
    assert importing.unit_combo.currentText() == "Tumorlaboratoriet"


def test_unit_settings_shortcut_requests_just_that_unit(qtbot):
    page = OverviewPage()
    qtbot.addWidget(page)
    with qtbot.waitSignal(page.settings_requested) as signal:
        qtbot.mouseClick(page.unit_cards["pre"].settings_button, Qt.MouseButton.LeftButton)
    assert signal.args == ["pre"]


def test_diagnostics_filter_preserves_configuration_error_and_source_messages(qtbot):
    page = DiagnosticsPage()
    qtbot.addWidget(page)
    page.set_configuration_error("Database not available")
    page.set_messages(("statistics:hemato: LOOKUP_INVALID", "statistics:fish: succeeded"))
    assert "Database not available" in page.log.toPlainText()
    page.unit_filter.setCurrentIndex(page.unit_filter.findData("hemato"))
    assert "LOOKUP_INVALID" in page.log.toPlainText()
    assert "fish" not in page.log.toPlainText()
    page.search_field.setText("succeeded")
    assert "Ingen hendelser passer" in page.log.toPlainText()
    assert not page.copy_button.isEnabled()
    page.search_field.clear()
    page.unit_filter.setCurrentIndex(0)
    assert "fish" in page.log.toPlainText()
    assert "Database not available" in page.log.toPlainText()


def test_import_fields_keep_separate_unit_and_job_drafts(qtbot):
    page = ImportPage()
    qtbot.addWidget(page)
    page.set_roles(("antall", "resultater"))
    page.file_fields["antall"].setText("K:/reports/hemato-antall.csv")
    page.unit_combo.setCurrentIndex(page.unit_combo.findData("fish"))
    page.set_roles(("antall", "resultater"))
    assert page.file_fields["antall"].text() == ""
    page.file_fields["antall"].setText("K:/reports/fish-antall.csv")
    page.unit_combo.setCurrentIndex(page.unit_combo.findData("hemato"))
    page.set_available_jobs(("statistics", "backlog"))
    page.set_roles(("antall", "resultater"))
    assert page.file_fields["antall"].text() == "K:/reports/hemato-antall.csv"
    page.job_combo.setCurrentIndex(page.job_combo.findData("backlog"))
    page.set_roles(("backlog",))
    assert page.file_fields["backlog"].text() == ""
    page.job_combo.setCurrentIndex(page.job_combo.findData("statistics"))
    page.set_roles(("antall", "resultater"))
    assert page.file_fields["antall"].text() == "K:/reports/hemato-antall.csv"


def test_import_backlog_period_is_locked_and_statistics_period_is_restored(qtbot):
    page = ImportPage()
    qtbot.addWidget(page)
    page.set_available_jobs(("statistics", "backlog"))
    page.from_date.setDate(QDate(2025, 2, 1))
    page.to_date.setDate(QDate(2025, 2, 28))
    page.job_combo.setCurrentIndex(page.job_combo.findData("backlog"))
    assert page.from_date.date() == QDate(2024, 1, 1)
    assert page.to_date.date() == QDate.currentDate()
    assert not page.from_date.isEnabled()
    assert not page.to_date.isEnabled()
    page.job_combo.setCurrentIndex(page.job_combo.findData("statistics"))
    assert page.from_date.date() == QDate(2025, 2, 1)
    assert page.to_date.date() == QDate(2025, 2, 28)
    assert page.from_date.isEnabled()


def test_import_plan_checks_missing_files_then_preserves_selected_sources(qtbot, tmp_path):
    page = ImportPage()
    qtbot.addWidget(page)
    page.set_roles(("antall", "resultater"))
    with pytest.raises(ValueError, match="Velg fil for"):
        page.get_plan()
    assert page.file_fields["antall"].property("tone") == "danger"
    paths = {}
    for role, field in page.file_fields.items():
        source = tmp_path / f"{role}.csv"
        source.write_text("A;B\n1;2\n", encoding="utf-8")
        paths[role] = source
        field.setText(str(source))
    plan = page.get_plan()
    assert plan.unit_key == "hemato"
    assert plan.job_kind == "statistics"
    assert plan.files == paths
    assert all(path.read_text(encoding="utf-8") == "A;B\n1;2\n" for path in paths.values())


def test_import_action_and_validation_feedback_remain_visible_when_scrolled(qtbot):
    page = ImportPage()
    qtbot.addWidget(page)
    page.resize(870, 698)
    page.unit_combo.setCurrentIndex(page.unit_combo.findData("lege"))
    page.set_roles(("current", "previous", "production_current", "production_previous", "macro_current", "macro_previous"))
    page.show()
    assert page.import_button.isVisible()
    assert page.feedback.isVisible()
    assert page.import_button.geometry().bottom() < page.import_button.parentWidget().height()
    assert "forrige måned" in page.period_hint.text()
    page.set_busy(True)
    assert not page.import_button.isEnabled()
    assert not page.form_container.isEnabled()
    page.set_busy(False)
    assert page.import_button.isEnabled()


def test_workflow_import_requires_one_file_and_describes_one_month(qtbot):
    page = ImportPage()
    qtbot.addWidget(page)
    page.unit_combo.setCurrentIndex(page.unit_combo.findData("lege"))
    page.set_roles(("workflow",))
    assert set(page.file_fields) == {"workflow"}
    assert "én fil" in page.period_hint.text()
    assert "forrige måned" not in page.period_hint.text()
