from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from PyQt6.QtCore import QDateTime, QObject, QRunnable, QThreadPool, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
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
from .import_page import ImportPage
from .theme import build_stylesheet
from ..orchestrator import JobResult


class _WorkerSignals(QObject):
    finished = pyqtSignal(object)


class _JobWorker(QRunnable):
    def __init__(self, orchestrator: Any, target: str, *, operation: Any = None) -> None:
        super().__init__()
        self.orchestrator = orchestrator
        self.target = target
        self.operation = operation
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            result = self.operation() if self.operation else self.orchestrator.run(self.target, "manual")
        except Exception as exc:
            if hasattr(self.orchestrator, "_report_failure"):
                self.orchestrator._report_failure(f"{self.target}_run_failed", exc)
            result = JobResult(self.target, "failed", {}, "Kjøringen feilet. Se Diagnostikk.")
        self.signals.finished.emit(result)


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
        self._configuration_error = configuration_error
        self._workers: set[_JobWorker] = set()
        self._capability_outcomes: dict[tuple[str, str], Any] = {}
        self._history_database: Path | None = None
        self.setWindowTitle("MolStat")
        self.setWindowIcon(QIcon(str(asset_path("molstat.ico"))))
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
        self._saved_enabled_units = {
            key for key, field in self.settings_page.enabled_fields.items()
            if field.isChecked()
        }
        self.diagnostics = DiagnosticsPage()
        self.diagnostics.open_log_button.clicked.connect(self._open_diagnostic_log_directory)
        self.import_page = ImportPage()
        self.diagnostics.set_configuration_error(configuration_error)
        self.stack.addWidget(self.overview)
        self.stack.addWidget(self.settings_page)
        self.stack.addWidget(self.diagnostics)
        self.stack.addWidget(self.import_page)
        shell_layout.addWidget(self.stack, 1)
        self.setCentralWidget(shell)

        self.nav_overview.clicked.connect(lambda: self._navigate(0))
        self.nav_settings.clicked.connect(lambda: self._navigate(1))
        self.nav_diagnostics.clicked.connect(lambda: self._navigate(2))
        self.nav_import.clicked.connect(lambda: self._navigate(3))
        self.overview.import_button.clicked.connect(lambda: self._navigate(3))
        self.overview.settings_requested.connect(self._open_unit_settings)
        self.import_page.selection_changed.connect(self._refresh_import_selection)
        self.import_page.import_button.clicked.connect(self._start_manual_import)
        self.overview.run_all.clicked.connect(lambda: self._start_job("all"))
        self.overview.refresh_excel.clicked.connect(lambda: self._start_job("excel"))
        self.overview.retry_publish.clicked.connect(lambda: self._start_job("publish"))
        for key, card in self.overview.unit_cards.items():
            if card.unit.status == "active":
                card.run_button.clicked.connect(
                    lambda _checked=False, target=key: self._start_job(target)
                )
                card.backlog_button.clicked.connect(
                    lambda _checked=False, target=key: self._start_job(f"{target}:backlog")
                )
        self.settings_page.save_button.clicked.connect(self._save_settings)
        self.settings_page.import_button.clicked.connect(self._import_settings)
        self.settings_page.export_button.clicked.connect(self._export_settings)
        self._load_settings()
        self._refresh_overview_status()
        self._refresh_diagnostics()
        self._navigate(0)
        self.statusBar().showMessage(
            "Kontroller Innstillinger og Diagnostikk." if self._configuration_error
            else "MolStat er klar."
        )

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
        self.nav_import = _nav_button("Manuell import", "nav-import")
        layout.addWidget(self.nav_overview)
        layout.addWidget(self.nav_settings)
        layout.addWidget(self.nav_import)
        layout.addWidget(self.nav_diagnostics)
        layout.addStretch(1)
        return sidebar

    def _navigate(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for button_index, button in enumerate(
            (self.nav_overview, self.nav_settings, self.nav_diagnostics, self.nav_import)
        ):
            button.setProperty("active", button_index == index)
            button.style().unpolish(button)
            button.style().polish(button)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._workers:
            event.ignore()
            self.statusBar().showMessage("En kjøring pågår. Vent til den er ferdig før appen lukkes.", 8000)
            return
        super().closeEvent(event)

    def _open_unit_settings(self, key: str) -> None:
        self.settings_page.select_unit(key)
        self._navigate(1)

    def _refresh_import_selection(self, unit_key: str = "", job_kind: str = "") -> None:
        del job_kind
        unit_key = unit_key or self.import_page.unit_combo.currentData()
        if not unit_key or self.settings_store is None:
            self.import_page.set_roles(())
            return
        if not hasattr(self.settings_store, "manual_import_roles"):
            self.import_page.set_roles(())
            return
        try:
            jobs = self.settings_store.manual_import_available_jobs(unit_key)
            self.import_page.set_available_jobs(jobs)
            selected_job = self.import_page.job_combo.currentData()
            self.import_page.set_roles(self.settings_store.manual_import_roles(unit_key, selected_job))
            self.import_page.set_result("", "Velg rapportfiler og kontroller uttrekksperioden.")
        except (ValueError, OSError) as exc:
            self.import_page.set_roles(())
            self.import_page.set_result("Oppsett må rettes", str(exc))

    def _start_manual_import(self) -> None:
        if self._workers or not hasattr(self.settings_store, "manual_import"):
            return
        try:
            plan = self.import_page.get_plan()
        except ValueError as exc:
            self.import_page.set_result("Kontroller filene", str(exc))
            return
        worker = _JobWorker(
            self.orchestrator, plan.unit_key,
            operation=lambda: self.settings_store.manual_import(plan),
        )
        self._workers.add(worker)
        self.import_page.set_busy(True)
        self._refresh_run_button_states()
        self.statusBar().showMessage("Manuell import pågår …")
        worker.signals.finished.connect(lambda result, active=worker: self._job_finished(result, active))
        QThreadPool.globalInstance().start(worker)

    def _start_job(self, target: str) -> None:
        if self._workers:
            return
        if self.orchestrator is None:
            self.statusBar().showMessage("Kjøring er ikke konfigurert.")
            return
        unit_key = target.partition(":")[0]
        if unit_key in self.settings_page.enabled_fields and (
            unit_key not in self._enabled_unit_keys()
        ):
            self.statusBar().showMessage(
                "Enheten er deaktivert. Aktiver den i Innstillinger.", 5000
            )
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
        if self.settings_store and hasattr(self.settings_store, "overview_status_fields"):
            for key, value in self.settings_store.overview_status_fields().items():
                if key in self.overview.cards:
                    self.overview.cards[key].set_status(*value)
        if result.status == "succeeded":
            detail = self._completion_detail(result.summary)
            self._apply_capability_results(result, "Fullført", detail)
            if result.kind != "excel":
                self.overview.cards["sharepoint"].set_status(
                    "Publisert" if result.kind != "publish" or result.summary.get("published") else "Ingen ventende filer",
                    "Siste handling ble fullført",
                )
            self.statusBar().showMessage("Kjøringen er fullført.", 5000)
        elif result.status == "partial":
            succeeded = int(result.summary.get("succeeded", 0))
            failed = int(result.summary.get("failed", 0))
            detail = f"{succeeded} fullført, {failed} feilet"
            self._apply_capability_results(result, "Delvis feil", detail)
            self._refresh_diagnostics()
            self.statusBar().showMessage(
                "Kjøringen ble delvis fullført. Se Diagnostikk.", 7000
            )
        elif result.status == "busy":
            self.statusBar().showMessage("En annen kjøring er allerede aktiv.", 5000)
        else:
            self._apply_capability_results(result, "Feilet", "Se personvernsikker diagnostikk")
            self._refresh_diagnostics()
            self.statusBar().showMessage("Kjøringen feilet. Se Diagnostikk.", 7000)
        if worker.operation is not None:
            if result.status == "succeeded":
                self.import_page.set_result("Fullført", "Data er behandlet. Se enhetsstatus og Excel-status i Oversikt.")
            elif result.status == "busy":
                self.import_page.set_result("Opptatt", "En annen MolStat-kjøring pågår. Prøv igjen når den er ferdig.")
            else:
                outcomes = getattr(result, "capability_results", ())
                detail = next((item.message for item in outcomes if item.message), result.message)
                self.import_page.set_result("Feilet", detail or "Kontroller rapportfilene og enhetsoppsettet i Diagnostikk.")
        self.overview.refresh_summary()

    def _apply_capability_results(self, result: Any, state: str, detail: str) -> None:
        # A publication retry does not change whether the source import worked.
        if result.kind == "publish":
            return
        outcomes = getattr(result, "capability_results", ())
        if not outcomes:
            self._set_target_status(result.kind, state, detail)
            return
        by_unit: dict[str, list[Any]] = {}
        for outcome in outcomes:
            card = self.overview.unit_cards.get(outcome.unit_key)
            if (card is None or outcome.unit_key not in self._enabled_unit_keys()
                    or outcome.job_kind not in card.capability_status_labels):
                continue
            self._capability_outcomes[(outcome.unit_key, outcome.job_kind)] = outcome
            by_unit.setdefault(outcome.unit_key, [])
            outcome_detail = (self._completion_detail(outcome.summary)
                              if outcome.status == "succeeded"
                              else outcome.message or "Se Diagnostikk")
            finished_at = getattr(outcome, "finished_at", None)
            if finished_at:
                moment = QDateTime.fromString(finished_at, Qt.DateFormat.ISODate)
                if moment.isValid():
                    outcome_detail += f" · Sist kjørt {moment.toLocalTime().toString('dd.MM.yyyy HH:mm')}"
            card.set_capability_status(
                outcome.job_kind,
                "Fullført" if outcome.status == "succeeded" else "Feilet",
                outcome_detail,
            )
        for key in by_unit:
            results = [item for (unit, _job), item in self._capability_outcomes.items() if unit == key]
            failed = sum(item.status == "failed" for item in results)
            state = "Fullført" if not failed else "Feilet" if failed == len(results) else "Delvis feil"
            detail = f"{len(results) - failed} fullført, {failed} feilet" if failed else self._completion_detail({
                "rows": sum(item.summary.get("rows", 0) for item in results),
            })
            self.overview.unit_cards[key].set_status(state, detail)

    def _completion_detail(self, summary: dict[str, object]) -> str:
        capabilities = int(summary.get("capabilities", 0))
        if capabilities:
            return f"{capabilities} funksjoner fullført"
        rows = int(summary.get("rows", 0))
        return f"{rows} rader behandlet"

    def _set_target_status(self, target: str, state: str, detail: str) -> None:
        target = target.partition(":")[0]
        card = self.overview.unit_cards.get(target)
        if card is not None and target in self._enabled_unit_keys():
            card.set_status(state, detail)

    def _refresh_diagnostics(self) -> None:
        if self.settings_store is None:
            return
        if hasattr(self.settings_store, "diagnostic_messages"):
            self.diagnostics.set_messages(self.settings_store.diagnostic_messages())
        if hasattr(self.settings_store, "diagnostic_log_directory"):
            self.diagnostics.set_log_directory(self.settings_store.diagnostic_log_directory())

    def _open_diagnostic_log_directory(self) -> None:
        resolver = getattr(self.settings_store, "diagnostic_log_directory", None)
        if resolver is None:
            return
        directory = resolver()
        self.diagnostics.set_log_directory(directory)
        if directory is None:
            self.statusBar().showMessage("Loggmappe er ikke tilgjengelig. Hendelsene vises i Diagnostikk.", 8000)
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory))):
            self.statusBar().showMessage(f"Loggmappen kunne ikke åpnes: {directory}", 8000)

    def _refresh_overview_status(self) -> None:
        database_path = getattr(getattr(self.orchestrator, "database", None), "path", None)
        if database_path != self._history_database:
            self._history_database = database_path
            self._capability_outcomes.clear()
            for card in self.overview.unit_cards.values():
                for label in card.capability_status_labels.values():
                    label.clear()
                    label.hide()
        if self.settings_store is not None and hasattr(self.settings_store, "unit_definitions"):
            definitions = self.settings_store.unit_definitions()
            self.overview.set_definitions(definitions)
            self.settings_page.set_definitions(definitions)
            self.import_page.set_definitions(definitions)
        current_capabilities = {
            (key, capability.job_kind)
            for key, card in self.overview.unit_cards.items()
            for capability in card.unit.capabilities
        }
        self._capability_outcomes = {
            key: outcome for key, outcome in self._capability_outcomes.items()
            if key in current_capabilities
        }
        runtime_status = (
            ("Klar", "Manuell kjøring er tilgjengelig")
            if self.orchestrator is not None
            else ("Ikke klar", "Kontroller Innstillinger og Diagnostikk")
        )
        for card in self.overview.unit_cards.values():
            if card.unit.status == "active":
                card.set_status(*runtime_status)
        enabled = self._enabled_unit_keys()
        self.overview.set_enabled_units(enabled)
        self.import_page.set_enabled_units(enabled)
        self._refresh_import_selection()
        for key, card in self.overview.unit_cards.items():
            if card.unit.status == "active" and key not in enabled:
                card.set_status("Deaktivert", "Aktiver enheten i Innstillinger")
        if self.orchestrator is not None and hasattr(self.orchestrator, "capability_statuses"):
            try:
                outcomes = self.orchestrator.capability_statuses()
            except Exception:
                outcomes = ()
            self._apply_capability_results(JobResult("all", "succeeded", {}, capability_results=outcomes), "", "")
        if self.settings_store is not None and hasattr(self.settings_store, "unit_status_fields"):
            for key, status in self.settings_store.unit_status_fields().items():
                if key in self.overview.unit_cards and (status[0] != "Klar" or not any(unit == key for unit, _job in self._capability_outcomes)):
                    self.overview.unit_cards[key].set_status(*status)
        self._refresh_run_button_states()
        if self.settings_store is not None and hasattr(
            self.settings_store, "overview_status_fields"
        ):
            for key, status in self.settings_store.overview_status_fields().items():
                if key in self.overview.cards:
                    self.overview.cards[key].set_status(*status)
        if self._configuration_error and "BackupIntegrityError" in (
            self._configuration_error
        ):
            self.overview.cards["database"].set_status(
                "Feil", "Databasekontrollen feilet. Se Diagnostikk"
            )

    def _refresh_run_button_states(self) -> None:
        running = {worker.target for worker in self._workers}
        enabled = self._enabled_unit_keys()
        self.overview.run_all.setEnabled(not running and bool(enabled) and self.orchestrator is not None)
        self.overview.refresh_excel.setEnabled(not running and self.orchestrator is not None)
        self.overview.retry_publish.setEnabled(not running and self.orchestrator is not None)
        self.settings_page.setEnabled(not running)
        importing = any(worker.operation is not None for worker in self._workers)
        self.import_page.set_busy(importing)
        self.import_page.setEnabled(not running or importing)
        available_import = self.settings_store is not None and hasattr(self.settings_store, "manual_import")
        self.overview.import_button.setEnabled(not running and bool(enabled) and available_import)
        for key, card in self.overview.unit_cards.items():
            if card.unit.status != "active" or key not in enabled:
                card.run_button.setEnabled(False)
            else:
                card.run_button.setEnabled(
                    not running and self.orchestrator is not None
                )
            card.backlog_button.setEnabled(card.run_button.isEnabled())

    def _enabled_unit_keys(self) -> set[str]:
        return set(self._saved_enabled_units)

    def _load_settings(self) -> None:
        if self.settings_store is None or not hasattr(
            self.settings_store, "load_settings_fields"
        ):
            return
        values = self.settings_store.load_settings_fields()
        self.settings_page.sensitive_root.setText(values.get("sensitive_root", ""))
        self.settings_page.sharepoint_root.setText(values.get("sharepoint_root", ""))
        self.settings_page.lvms_url.setText(values.get("lvms_url", ""))
        for key, field in self.settings_page.config_fields.items():
            field.setText(values.get(f"config_{key}", ""))
        for key, field in self.settings_page.backlog_fields.items():
            field.setText(values.get(f"backlog_{key}", ""))
        for key, field in self.settings_page.schedule_fields.items():
            field.setValue(int(values.get(key, field.value())))
        for key, field in self.settings_page.enabled_fields.items():
            field.setChecked(values.get(f"enabled_{key}", "true") == "true")
        self._saved_enabled_units = {
            key for key, field in self.settings_page.enabled_fields.items()
            if field.isChecked()
        }
        self._refresh_overview_status()

    def _save_settings(self) -> None:
        if self._workers:
            self.statusBar().showMessage("Vent til kjøringen er ferdig før innstillinger endres.")
            return
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
                f"enabled_{key}": "true" if field.isChecked() else "false"
                for key, field in self.settings_page.enabled_fields.items()
            }
        )
        values.update({f"config_{key}": field.text().strip() for key, field in self.settings_page.config_fields.items()})
        values.update({f"backlog_{key}": field.text().strip() for key, field in self.settings_page.backlog_fields.items()})
        values.update({key: str(field.value()) for key, field in self.settings_page.schedule_fields.items()})
        try:
            self.settings_store.save_settings_fields(values)
        except (ValueError, OSError) as exc:
            self.statusBar().showMessage(str(exc), 8000)
            return
        self._load_settings()
        if hasattr(self.settings_store, "refresh_gui_runtime"):
            orchestrator, error = self.settings_store.refresh_gui_runtime()
            self.orchestrator = orchestrator
            self._configuration_error = error
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

    def _export_settings(self) -> None:
        if self.settings_store is None or not hasattr(
            self.settings_store, "export_settings"
        ):
            self.statusBar().showMessage(
                "Eksport av innstillinger er ikke tilgjengelig."
            )
            return
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Eksporter MolStat-innstillinger",
            "molstat-innstillinger.json",
            "JSON-filer (*.json)",
        )
        if not selected:
            return
        try:
            self.settings_store.export_settings(Path(selected))
        except (OSError, ValueError):
            self.statusBar().showMessage(
                "Innstillingene kunne ikke eksporteres.", 8000
            )
            return
        self.statusBar().showMessage("Innstillingene er eksportert.", 5000)

    def _import_settings(self) -> None:
        if self.settings_store is None or not hasattr(
            self.settings_store, "import_settings"
        ):
            self.statusBar().showMessage(
                "Import av innstillinger er ikke tilgjengelig."
            )
            return
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Importer MolStat-innstillinger",
            "",
            "JSON-filer (*.json)",
        )
        if not selected:
            return
        try:
            warnings = self.settings_store.import_settings(Path(selected))
        except (OSError, ValueError) as error:
            self.statusBar().showMessage(str(error), 8000)
            return
        self._load_settings()
        if hasattr(self.settings_store, "refresh_gui_runtime"):
            orchestrator, error = self.settings_store.refresh_gui_runtime()
            self.orchestrator = orchestrator
            self._configuration_error = error
            self.diagnostics.set_configuration_error(error)
            self._refresh_overview_status()
        if warnings:
            labels = ", ".join(warnings)
            self.statusBar().showMessage(
                f"Importert. Må velges på denne PC-en: {labels}.", 10000
            )
        else:
            self.statusBar().showMessage(
                "Innstillingene er importert og klare.", 5000
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
        existing.setWindowIcon(QIcon(str(asset_path("molstat.ico"))))
        return existing
    application = QApplication(sys.argv)
    application.setWindowIcon(QIcon(str(asset_path("molstat.ico"))))
    return application


def asset_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / name
