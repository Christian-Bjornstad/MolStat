from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .dashboard import OverviewPage
from .diagnostics import DiagnosticsPage
from .settings import SettingsPage
from .theme import build_stylesheet


class _WorkerSignals(QObject):
    finished = pyqtSignal(object)


class _JobWorker(QRunnable):
    def __init__(self, orchestrator: Any, kind: str) -> None:
        super().__init__()
        self.orchestrator = orchestrator
        self.kind = kind
        self.signals = _WorkerSignals()

    def run(self) -> None:
        self.signals.finished.emit(self.orchestrator.run(self.kind, "manual"))


class MainWindow(QMainWindow):
    def __init__(
        self,
        orchestrator: Any,
        settings_store: Any,
        board_controller: Any,
    ) -> None:
        super().__init__()
        self.orchestrator = orchestrator
        self.settings_store = settings_store
        self.board_controller = board_controller
        self._workers: set[_JobWorker] = set()
        self.setWindowTitle("MolStat")
        self.setMinimumSize(1100, 720)
        self.resize(1280, 800)
        self.setStyleSheet(build_stylesheet())

        shell = QWidget()
        shell.setObjectName("app-shell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        sidebar = self._build_sidebar()
        shell_layout.addWidget(sidebar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("page-stack")
        self.overview = OverviewPage()
        self.settings_page = SettingsPage()
        self.diagnostics = DiagnosticsPage()
        self.stack.addWidget(self.overview)
        self.stack.addWidget(self.settings_page)
        self.stack.addWidget(self.diagnostics)
        shell_layout.addWidget(self.stack, 1)
        self.setCentralWidget(shell)

        self.nav_overview.clicked.connect(lambda: self._navigate(0))
        self.nav_settings.clicked.connect(lambda: self._navigate(1))
        self.nav_diagnostics.clicked.connect(lambda: self._navigate(2))
        self.overview.run_statistics.clicked.connect(
            lambda: self._start_job("statistics")
        )
        self.overview.run_backlog.clicked.connect(lambda: self._start_job("backlog"))
        self.overview.open_board.clicked.connect(self._open_board)
        self._navigate(0)
        self.statusBar().showMessage("MolStat er klar.")

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 26, 20, 22)
        layout.setSpacing(10)
        brand = QLabel("MolStat")
        brand.setObjectName("brand")
        subtitle = QLabel("Statistikk og driftsinnsikt")
        subtitle.setObjectName("brand-subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(brand)
        layout.addWidget(subtitle)
        layout.addSpacing(28)
        self.nav_overview = _nav_button("Oversikt", "nav-overview")
        self.nav_settings = _nav_button("Innstillinger", "nav-settings")
        self.nav_diagnostics = _nav_button("Diagnostikk", "nav-diagnostics")
        layout.addWidget(self.nav_overview)
        layout.addWidget(self.nav_settings)
        layout.addWidget(self.nav_diagnostics)
        layout.addStretch(1)
        footer = QLabel("Sensitive rådata forblir på K-sensitiv")
        footer.setObjectName("brand-subtitle")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        return sidebar

    def _navigate(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for button_index, button in enumerate(
            (self.nav_overview, self.nav_settings, self.nav_diagnostics)
        ):
            button.setProperty("active", button_index == index)
            button.style().unpolish(button)
            button.style().polish(button)

    def _start_job(self, kind: str) -> None:
        if self.orchestrator is None:
            self.statusBar().showMessage("Kjøring er ikke konfigurert.")
            return
        self._set_run_buttons_enabled(False)
        self.statusBar().showMessage("Kjøring pågår …")
        worker = _JobWorker(self.orchestrator, kind)
        self._workers.add(worker)
        worker.signals.finished.connect(
            lambda result, active=worker: self._job_finished(result, active)
        )
        QThreadPool.globalInstance().start(worker)

    def _job_finished(self, result: Any, worker: _JobWorker) -> None:
        self._workers.discard(worker)
        self._set_run_buttons_enabled(True)
        if result.status == "succeeded":
            self.statusBar().showMessage("Kjøringen er fullført.", 5000)
        elif result.status == "busy":
            self.statusBar().showMessage("En annen kjøring er allerede aktiv.", 5000)
        else:
            self.statusBar().showMessage("Kjøringen feilet. Se Diagnostikk.", 7000)

    def _set_run_buttons_enabled(self, enabled: bool) -> None:
        self.overview.run_statistics.setEnabled(enabled)
        self.overview.run_backlog.setEnabled(enabled)

    def _open_board(self) -> None:
        if self.board_controller is None:
            self.statusBar().showMessage("Tavleserveren er ikke konfigurert.")
            return
        self.board_controller.open()
        self.statusBar().showMessage("Restansetavlen er åpnet.", 5000)


def _nav_button(text: str, name: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(name)
    button.setAccessibleName(text)
    button.setMinimumHeight(44)
    button.setProperty("nav", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def create_application(settings_path: Path) -> QApplication:
    del settings_path
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication(sys.argv)
