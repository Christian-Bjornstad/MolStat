from types import SimpleNamespace
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDesktopServices

from molstat.ui.app import MainWindow


def test_diagnostics_opens_actual_successful_log_directory(qtbot, tmp_path, monkeypatch):
    directory = tmp_path / "fallback" / "MolStat" / "logs"
    directory.mkdir(parents=True)
    store = SimpleNamespace(diagnostic_messages=lambda: ("hemato_backlog_run_failed: RuntimeError",),
                            diagnostic_log_directory=lambda: directory)
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    window = MainWindow(None, store)
    qtbot.addWidget(window)
    window.show()
    qtbot.mouseClick(window.nav_diagnostics, Qt.MouseButton.LeftButton)

    button = window.diagnostics.open_log_button
    assert button.text() == "Åpne loggmappe"
    assert button.isEnabled()
    assert str(directory) in window.diagnostics.log_directory.text()
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert len(opened) == 1
    assert opened[0].isLocalFile()
    assert Path(opened[0].toLocalFile()) == directory


def test_fake_store_without_log_directory_keeps_control_hidden(qtbot):
    store = SimpleNamespace(diagnostic_messages=lambda: ())
    window = MainWindow(None, store)
    qtbot.addWidget(window)

    assert window.diagnostics.open_log_button.isHidden()


def test_unavailable_log_directory_disables_control(qtbot):
    store = SimpleNamespace(diagnostic_messages=lambda: ("hemato_backlog_run_failed: RuntimeError",),
                            diagnostic_log_directory=lambda: None)
    window = MainWindow(None, store)
    qtbot.addWidget(window)

    assert not window.diagnostics.open_log_button.isEnabled()
    assert "kunne ikke opprettes" in window.diagnostics.log_directory.text()
