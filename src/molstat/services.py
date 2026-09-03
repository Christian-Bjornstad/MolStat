from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from dataclasses import replace
import json
import os
from pathlib import Path
import socket
from threading import Event
import traceback
from urllib.parse import urlparse
import webbrowser

from .archive import RawArchive
from .backlog import BacklogProcessor, CsvContract, load_app_config, load_restanse_columns
from .config import MolStatSettings
from .database import MolStatDatabase
from .fetching import UnifiedLvmsFetcher
from .orchestrator import MolStatOrchestrator
from .publisher import PublicationPolicy, SharePointPublisher, default_forbidden_patterns
from .schedule import due_jobs
from .statistics import (
    ANTALL_COLUMNS,
    RESULTATER_COLUMNS,
    SOLIDE_ANTALL_COLUMNS,
    SOLIDE_RESULTATER_COLUMNS,
    StatisticsProcessor,
    load_units,
)
from .system import MolStatSystem


class BoardController:
    def __init__(self, snapshot_provider, *, port: int = 8765) -> None:
        from .web import BoardServer

        self.server = BoardServer(snapshot_provider, port=port)

    def open(self) -> None:
        self.server.start()
        webbrowser.open(f"http://127.0.0.1:{self.server.port}/board")


class DefaultServices:
    def __init__(self, settings_path: Path) -> None:
        self.settings_path = settings_path
        self._diagnostics: deque[str] = deque(maxlen=100)
        self._settings_exist = settings_path.is_file()
        self.settings = (
            MolStatSettings.load(settings_path)
            if self._settings_exist
            else MolStatSettings(sensitive_root=Path("."))
        )

    def gui(self) -> int:
        from .ui.app import MainWindow, create_application

        application = create_application(self.settings_path)
        orchestrator, board, error = self.refresh_gui_runtime()
        window = MainWindow(
            orchestrator,
            self,
            board,
            configuration_error=error,
        )
        window.show()
        return int(application.exec())

    def refresh_gui_runtime(self) -> tuple[object | None, object | None, str | None]:
        try:
            system = self._build_system(require_statistics=True)
            orchestrator = self._orchestrator(system)
            board = BoardController(
                lambda: system.public_snapshot(datetime.now()), port=8765
            )
        except Exception as exc:
            self._record_failure("gui_configuration_failed", exc)
            return None, None, f"{type(exc).__name__}: {exc}"
        return orchestrator, board, None

    def run(self, kind: str) -> int:
        try:
            system = self._build_system(require_statistics=kind == "statistics")
            result = self._orchestrator(system).run(kind, "scheduled")
        except Exception:
            print(json.dumps({"status": "failed", "message": "Kontroller MolStat-oppsettet."}, ensure_ascii=False))
            return 2
        print(json.dumps({"status": result.status, **result.summary}, ensure_ascii=False))
        return 0 if result.status == "succeeded" else 2

    def serve(self) -> int:
        from .web import BoardServer

        system = self._build_system(require_statistics=False)
        server = BoardServer(lambda: system.public_snapshot(datetime.now()))
        server.start()
        try:
            while True:
                Event().wait(3600)
        except KeyboardInterrupt:
            server.stop()
        return 0

    def auto(self) -> int:
        database = self._database()
        now = datetime.now(timezone.utc)
        due = due_jobs(now, database.last_successes())
        statuses = [self.run(kind) for kind in due]
        if not due:
            print(json.dumps({"status": "idle"}))
        return 0 if all(status == 0 for status in statuses) else 2

    def install_automation(self) -> int:
        from .windows_automation import default_automation_paths, install_automation

        if not self._settings_exist:
            print(json.dumps({"status": "failed", "message": "Konfigurer MolStat først."}, ensure_ascii=False))
            return 2
        paths = default_automation_paths(
            project_root=Path(__file__).resolve().parents[2],
            settings_path=self.settings_path,
        )
        result = install_automation(paths)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "tasks": [
                        result.statistics_task,
                        result.backlog_task,
                        result.board_task,
                    ],
                },
                ensure_ascii=False,
            )
        )
        return 0

    def _database(self) -> MolStatDatabase:
        database = MolStatDatabase(
            self.settings.sensitive_root / "data" / "molstat.sqlite3"
        )
        database.migrate()
        return database

    def _build_system(self, *, require_statistics: bool) -> MolStatSystem:
        if not self._settings_exist:
            raise ValueError("MolStat må konfigureres i Innstillinger.")
        root = Path(__file__).resolve().parents[2]
        config_root = root / "config"
        local_text = str(os.environ.get("LOCALAPPDATA") or "").strip()
        local_root = (
            Path(local_text) if local_text else Path.home() / "AppData" / "Local"
        ) / "MolStat"
        lvms_config = self._ensure_lvms_config(local_root)
        units_path = config_root / "units.json"
        backlog_config = load_app_config(config_root / "backlog-analyses.json")
        raw_contract = load_restanse_columns(config_root / "backlog-columns.json")
        contract = CsvContract(
            delimiter=raw_contract["delimiter"],
            encoding=raw_contract["encoding"],
            columns=raw_contract["columns"],
            completed_values=tuple(raw_contract["completed_values"]),
            classifier_version=int(raw_contract["classifier_version"]),
        )
        database = self._database()
        fetcher = UnifiedLvmsFetcher(
            lvms_config_path=lvms_config,
            sensitive_root=self.settings.sensitive_root,
            work_root=self.settings.sensitive_root / "work" / "fetch",
            units_path=units_path,
            backlog_report_path=config_root / "backlog-report.json",
        )
        statistics_processors: dict[str, StatisticsProcessor] = {}
        publishers: dict[str, SharePointPublisher] = {}
        if require_statistics:
            if self.settings.sharepoint_root is None:
                raise ValueError("SharePoint-mappe mangler.")
            for unit in load_units(units_path):
                lookup = self.settings.statistics_lookup_paths.get(unit.key)
                if lookup is None:
                    raise ValueError(f"Lookup-fil mangler for {unit.key}.")
                statistics_processors[unit.key] = StatisticsProcessor(
                    lookup, profile=unit.profile
                )
                antall = (
                    SOLIDE_ANTALL_COLUMNS if unit.profile == "solide" else ANTALL_COLUMNS
                )
                resultater = (
                    SOLIDE_RESULTATER_COLUMNS
                    if unit.profile == "solide"
                    else RESULTATER_COLUMNS
                )
                publishers[unit.key] = SharePointPublisher(
                    PublicationPolicy(
                        allowed_columns={
                            "antall.csv": frozenset(antall),
                            "resultater.csv": frozenset(resultater),
                        },
                        forbidden_patterns=default_forbidden_patterns(),
                    )
                )
        else:
            publishers["hemato"] = SharePointPublisher(
                PublicationPolicy(
                    allowed_columns={
                        "antall.csv": frozenset(ANTALL_COLUMNS),
                        "resultater.csv": frozenset(RESULTATER_COLUMNS),
                    },
                    forbidden_patterns=default_forbidden_patterns(),
                )
            )
        return MolStatSystem(
            database=database,
            archive=RawArchive(self.settings.sensitive_root),
            statistics_processors=statistics_processors,
            backlog_processor=BacklogProcessor(backlog_config, contract),
            publisher=publishers,
            sharepoint_root=(
                self.settings.sharepoint_root
                or self.settings.sensitive_root / "publication-disabled"
            ),
            work_root=self.settings.sensitive_root / "work" / "processing",
            statistics_fetch=fetcher.fetch_statistics,
            backlog_fetch=fetcher.fetch_backlog,
        )

    def _orchestrator(self, system: MolStatSystem) -> MolStatOrchestrator:
        return MolStatOrchestrator(
            system.database,
            {
                "statistics": system.run_statistics,
                "backlog": system.run_backlog,
            },
            owner=socket.gethostname() or "molstat-pc",
            failure_reporter=self._record_job_failure,
        )

    def load_settings_fields(self) -> dict[str, str]:
        if not self._settings_exist:
            return {
                "sensitive_root": "",
                "sharepoint_root": "",
                "lvms_url": "",
                "lookup_hemato": "",
                "lookup_solide": "",
            }
        lookups = self.settings.statistics_lookup_paths
        return {
            "sensitive_root": str(self.settings.sensitive_root),
            "sharepoint_root": (
                str(self.settings.sharepoint_root)
                if self.settings.sharepoint_root is not None
                else ""
            ),
            "lvms_url": self.settings.lvms_url,
            "lookup_hemato": str(lookups.get("hemato", "")),
            "lookup_solide": str(lookups.get("solide", "")),
        }

    def save_settings_fields(self, values: dict[str, str]) -> None:
        sensitive_text = values.get("sensitive_root", "").strip()
        if not sensitive_text:
            raise ValueError("K-sensitiv mappe må fylles ut.")
        sharepoint_text = values.get("sharepoint_root", "").strip()
        lookups = {
            unit: Path(text)
            for unit, text in (
                ("hemato", values.get("lookup_hemato", "").strip()),
                ("solide", values.get("lookup_solide", "").strip()),
            )
            if text
        }
        updated = replace(
            self.settings,
            sensitive_root=Path(sensitive_text),
            sharepoint_root=Path(sharepoint_text) if sharepoint_text else None,
            statistics_lookup_paths=lookups,
            lvms_url=values.get("lvms_url", "").strip(),
        )
        errors = updated.validate()
        if errors:
            raise ValueError(errors[0])
        _validate_production_paths(updated)
        updated.save(self.settings_path)
        self.settings = updated
        self._settings_exist = True

    def _ensure_lvms_config(self, local_root: Path) -> Path:
        path = self.settings.lvms_config_path or local_root / "lvms-config.json"
        if path.exists():
            return path
        if not self.settings.lvms_url:
            raise ValueError("LVMS-adresse mangler.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "landing_url": self.settings.lvms_url,
                    "profile_directory": str(local_root / "edge-profile"),
                    "download_directory": str(local_root / "downloads"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def _record_failure(self, stage: str, error: BaseException) -> None:
        local_text = str(os.environ.get("LOCALAPPDATA") or "").strip()
        local_root = (
            Path(local_text) if local_text else Path.home() / "AppData" / "Local"
        )
        log = local_root / "MolStat" / "logs" / "bootstrap.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as stream:
            stream.write(f"\n[{stage}] {type(error).__name__}: {error}\n")
            traceback.print_exception(type(error), error, error.__traceback__, file=stream)

    def _record_job_failure(self, stage: str, error: BaseException) -> None:
        message = f"{stage}: {type(error).__name__}"
        self._diagnostics.append(message)
        local_text = str(os.environ.get("LOCALAPPDATA") or "").strip()
        local_root = Path(local_text) if local_text else Path.home() / "AppData" / "Local"
        log = local_root / "MolStat" / "logs" / "runtime.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as stream:
            stream.write(f"\n{message}\n")
            if error.__traceback__ is not None:
                stream.writelines(traceback.format_tb(error.__traceback__))

    def diagnostic_messages(self) -> tuple[str, ...]:
        return tuple(self._diagnostics)


def _validate_production_paths(settings: MolStatSettings) -> None:
    if not settings.sensitive_root.is_dir():
        raise ValueError("K-sensitiv mappe finnes ikke eller er ikke tilgjengelig.")
    if settings.sharepoint_root is None or not settings.sharepoint_root.is_dir():
        raise ValueError("SharePoint-mappe finnes ikke eller er ikke tilgjengelig.")
    for unit in ("hemato", "solide"):
        lookup = settings.statistics_lookup_paths.get(unit)
        if lookup is None or not lookup.is_file():
            raise ValueError(f"Lookup-fil for {unit.capitalize()} finnes ikke.")
    parsed = urlparse(settings.lvms_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("LVMS-adressen må være en fullstendig http- eller https-adresse.")
