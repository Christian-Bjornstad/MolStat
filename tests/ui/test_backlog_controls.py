from molstat.ui.app import MainWindow
from molstat.orchestrator import JobResult
from PyQt6.QtWidgets import QLabel
import pytest


class Store:
    def load_settings_fields(self):
        return {'enabled_hemato': 'true', 'enabled_solide': 'true'}


@pytest.mark.parametrize('unit_key', ['hemato', 'solide'])
def test_backlog_button_dispatches_only_selected_units_backlog(qtbot, unit_key):
    class Runner:
        calls = []
        def run(self, target, trigger):
            self.calls.append((target, trigger))
            return JobResult(target, 'succeeded', {'rows': 1})
    runner = Runner()
    window = MainWindow(runner, Store())
    qtbot.addWidget(window)
    button = window.overview.unit_cards[unit_key].backlog_button
    assert button.isEnabled()
    button.click()
    qtbot.waitUntil(lambda: not window._workers)
    assert runner.calls == [(f'{unit_key}:backlog', 'manual')]
    assert window.overview.unit_cards['flow'].backlog_button.isHidden()


def test_restanse_fields_and_patolog_workflow_are_present_in_settings(qtbot):
    window = MainWindow(None, Store())
    qtbot.addWidget(window)
    page = window.settings_page
    assert set(page.backlog_fields) == {'hemato', 'solide'}
    for key, field in page.backlog_fields.items():
        assert field.accessibleName()
        assert page.unit_panels[key].backlog_group.isHidden() is False
    assert 'PAT-TID-STØP-SNITT-OU' in page.unit_panels['lege'].workflow_hint.text()
    assert page.unit_panels['lege'].lookup_group.isHidden()
    assert not any(label.text() == 'Sensitive rådata forblir på K-sensitiv'
        for label in window.findChildren(QLabel))
