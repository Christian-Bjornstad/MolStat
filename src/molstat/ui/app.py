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
    def __init__(self, orchestrator: Any, target: str) -> None:
        super().__init__()
        self.orchestrator = orchestrator
        self.target = target
        self.signals = _WorkerSignals()

    def run(self) -> None:
        self.signals.finished.emit(self.orchestrator.run(self.target, "manual"))


class MainWindow(QMainWindow):
    def __init__(
        self,
        orchestrator: Any,
        settings_store: Any,
        *,
        configuration_error: str | None = None,
    ) -> None:
        super().__init__()
        self.orchestrator = orchestrator
        self.settings_store = settings_store
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
        self.diagnostics.set_configuration_error(configuration_error)
        self.stack.addWidget(self.overview)
        self.stack.addWidget(self.settings_page)
        self.stack.addWidget(self.diagnostics)
        shell_layout.addWidget(self.stack, 1)
        self.setCentralWidget(shell)

        self.nav_overview.clicked.connect(lambda: self._navigate(0))
        self.nav_settings.clicked.connect(lambda: self._navigate(1))
        self.nav_diagnostics.clicked.connect(lambda: self._navigate(2))
        self.overview.run_all.clicked.connect(lambda: self._start_job("all"))
        for key, card in self.overview.unit_cards.items():
            if card.unit.status == "active":
                card.run_button.clicked.connect(
                    lambda _checked=False, target=key: self._start_job(target)
                )
        self.settings_page.save_button.clicked.connect(self._save_settings)
        self._load_settings()
        self._refresh_overview_status()
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

    def _start_job(self, target: str) -> None:
        if self.orchestrator is None:
            self.statusBar().showMessage("Kjøring er ikke konfigurert.")
            return
        self.statusBar().showMessage("Kjøring pågår …")
        worker = _JobWorker(self.orchestrator, target)
        self._workers.add(worker)
        self._refresh_run_button_states()
        worker.signals.finished.connect(
            lambda result, active=worker: self._job_finished(result, active)
        )
        QThreadPool.globalInstance().start(worker)

    def _job_finished(self, result: Any, worker: _JobWorker) -> None:
        self._workers.discard(worker)
        self._refresh_run_button_states()
        if result.status == "succeeded":
            detail = self._completion_detail(result.summary)
            self._set_target_status(result.kind, "Fullført", detail)
            self.overview.cards["sharepoint"].set_status(
                "Publisert", "Siste kjøring ble fullført"
            )
            self.statusBar().showMessage("Kjøringen er fullført.", 5000)
        elif result.status == "partial":
            succeeded = int(result.summary.get("succeeded", 0))
            failed = int(result.summary.get("failed", 0))
            detail = f"{succeeded} fullført, {failed} feilet"
            self._set_target_status(result.kind, "Delvis feil", detail)
            self._refresh_diagnostics()
            self.statusBar().showMessage(
                "Kjøringen ble delvis fullført. Se Diagnostikk.", 7000
            )
        elif result.status == "busy":
            self.statusBar().showMessage("En annen kjøring er allerede aktiv.", 5000)
        else:
            self._set_target_status(
                result.kind, "Feilet", "Se personvernsikker diagnostikk"
            )
            self._refresh_diagnostics()
            self.statusBar().showMessage("Kjøringen feilet. Se Diagnostikk.", 7000)

    def _completion_detail(self, summary: dict[str, object]) -> str:
        capabilities = int(summary.get("capabilities", 0))
        if capabilities:
            return f"{capabilities} funksjoner fullført"
        rows = int(summary.get("rows", 0))
        return f"{rows} rader behandlet"

    def _set_target_status(self, target: str, state: str, detail: str) -> None:
        if target == "all":
            for card in self.overview.unit_cards.values():
                if card.unit.status == "active":
                    card.set_status(state, detail)
            return
        card = self.overview.unit_cards.get(target)
        if card is not None:
            card.set_status(state, detail)

    def _refresh_diagnostics(self) -> None:
        if self.settings_store is None or not hasattr(
            self.settings_store, "diagnostic_messages"
        ):
            return
        self.diagnostics.set_messages(self.settings_store.diagnostic_messages())

    def _refresh_overview_status(self) -> None:
        runtime_status = (
            ("Klar", "Manuell kjøring er tilgjengelig")
            if self.orchestrator is not None
            else ("Ikke klar", "Kontroller Innstillinger og Diagnostikk")
        )
        for card in self.overview.unit_cards.values():
            if card.unit.status == "active":
                card.set_status(*runtime_status)
        if self.settings_store is None or not hasattr(
            self.settings_store, "overview_status_fields"
        ):
            return
        for key, status in self.settings_store.overview_status_fields().items():
            if key in self.overview.cards:
                self.overview.cards[key].set_status(*status)

    def _refresh_run_button_states(self) -> None:
        running = {worker.target for worker in self._workers}
        self.overview.run_all.setEnabled(not running)
        for key, card in self.overview.unit_cards.items():
            if card.unit.status != "active":
                card.run_button.setEnabled(False)
            else:
                card.run_button.setEnabled(
                    "all" not in running and key not in running
                )

    def _load_settings(self) -> None:
        if self.settings_store is None or not hasattr(
            self.settings_store, "load_settings_fields"
        ):
            return
        values = self.settings_store.load_settings_fields()
        self.settings_page.sensitive_root.setText(values.get("sensitive_root", ""))
        self.settings_page.sharepoint_root.setText(values.get("sharepoint_root", ""))
        self.settings_page.lvms_url.setText(values.get("lvms_url", ""))
        for key, field in self.settings_page.lookup_fields.items():
            field.setText(values.get(f"lookup_{key}", ""))

    def _save_settings(self) -> None:
        if self.settings_store is None or not hasattr(
            self.settings_store, "save_settings_fields"
        ):
            self.statusBar().showMessage("Innstillingslagring er ikke tilgjengelig.")
            return
        values = {
            "sensitive_root": self.settings_page.sensitive_root.text().strip(),
            "sharepoint_root": self.settings_page.sharepoint_root.text().strip(),
            "lvms_url": self.settings_page.lvms_url.text().strip(),
        }
        values.update(
            {
                f"lookup_{key}": field.text().strip()
                for key, field in self.settings_page.lookup_fields.items()
            }
        )
        try:
            self.settings_store.save_settings_fields(values)
        except ValueError as exc:
            self.statusBar().showMessage(str(exc), 8000)
            return
        if hasattr(self.settings_store, "refresh_gui_runtime"):
            orchestrator, error = self.settings_store.refresh_gui_runtime()
            self.orchestrator = orchestrator
            self.diagnostics.set_configuration_error(error)
            self._refresh_overview_status()
            if error:
                self.statusBar().showMessage(
                    "Innstillingene er lagret, men kjøring er ikke klar. Se Diagnostikk.",
                    8000,
                )
                return
        self.statusBar().showMessage(
            "Innstillingene er validert og lagret. MolStat er klar.", 5000
        )


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
