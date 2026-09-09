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

from .archive import RawArchive
from .backlog import BacklogProcessor, CsvContract, load_app_config, load_restanse_columns
from .config import MolStatSettings
from .database import MolStatDatabase
from .fetching import UnifiedLvmsFetcher
from .modules import DEFAULT_UNITS
from .orchestrator import MolStatOrchestrator
from .publisher import PublicationPolicy, SharePointPublisher, default_forbidden_patterns
from .schedule import due_jobs
from .statistics import StatisticsProcessor, load_lookup, load_units
from .system import MolStatSystem


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
        orchestrator, error = self.refresh_gui_runtime()
        window = MainWindow(
            orchestrator,
            self,
            configuration_error=error,
        )
        window.show()
        return int(application.exec())

    def refresh_gui_runtime(self) -> tuple[object | None, str | None]:
        try:
            system = self._build_system(require_statistics=True)
            orchestrator = self._orchestrator(system)
        except Exception as exc:
            self._record_failure("gui_configuration_failed", exc)
            return None, f"{type(exc).__name__}: {exc}"
        return orchestrator, None

    def run(self, kind: str) -> int:
        try:
            system = self._build_system(require_statistics=kind != "backlog")
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
        due = due_jobs(
            now,
            database.last_successes(),
            statistics_hour=self.settings.statistics_hour,
            backlog_first_hour=self.settings.backlog_first_hour,
            backlog_last_hour=self.settings.backlog_last_hour,
        )
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
        result = install_automation(
            paths,
            statistics_hour=self.settings.statistics_hour,
            backlog_first_hour=self.settings.backlog_first_hour,
            backlog_last_hour=self.settings.backlog_last_hour,
        )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "tasks": [
                        result.statistics_task,
                        result.backlog_task,
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
        if self.settings.sharepoint_root is None:
            raise ValueError("SharePoint-mappe mangler.")
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
            units = {unit.key: unit for unit in load_units(units_path)}
            for definition in DEFAULT_UNITS.for_job(
                "statistics", self.settings.enabled_units
            ):
                capability = definition.capability("statistics")
                unit = units.get(definition.key)
                if unit is None:
                    raise ValueError(
                        f"Hentedefinisjon mangler for {definition.key}."
                    )
                if unit.profile != capability.processor_profile:
                    raise ValueError(
                        f"Prosessorprofil for {definition.key} stemmer ikke med enhetsregisteret."
                    )
                lookup = self.settings.statistics_lookup_paths.get(definition.key)
                if lookup is None:
                    raise ValueError(
                        f"Lookup-fil mangler for {definition.display_name}."
                    )
                statistics_processors[definition.key] = StatisticsProcessor(
                    lookup, profile=capability.processor_profile
                )
                publishers[definition.key] = SharePointPublisher(
                    PublicationPolicy(
                        allowed_columns=capability.allowed_columns,
                        forbidden_patterns=default_forbidden_patterns(),
                    )
                )
        backlog_capability = DEFAULT_UNITS.require("hemato").capability("backlog")
        backlog_publisher = SharePointPublisher(
            PublicationPolicy(
                allowed_columns=backlog_capability.allowed_columns,
                forbidden_patterns=default_forbidden_patterns(),
            )
        )
        hemato_lookup = self.settings.statistics_lookup_paths.get("hemato")
        analysis_lookup = (
            load_lookup(hemato_lookup)
            if hemato_lookup is not None and "hemato" in self.settings.enabled_units
            else {}
        )
        return MolStatSystem(
            database=database,
            archive=RawArchive(self.settings.sensitive_root),
            statistics_processors=statistics_processors,
            backlog_processor=BacklogProcessor(
                backlog_config,
                contract,
                analysis_lookup=analysis_lookup,
            ),
            publisher=publishers,
            backlog_publisher=backlog_publisher,
            sharepoint_root=self.settings.sharepoint_root,
            work_root=self.settings.sensitive_root / "work" / "processing",
            statistics_fetch=fetcher.fetch_statistics,
            backlog_fetch=fetcher.fetch_backlog,
            units=DEFAULT_UNITS,
        )

    def _orchestrator(self, system: MolStatSystem) -> MolStatOrchestrator:
        enabled = self.settings.enabled_units
        runners = {
            "all": lambda: system.run_all(enabled),
            "statistics": lambda: system.run_job("statistics", enabled),
            "backlog": lambda: system.run_job("backlog", enabled),
        }
        runners.update(
            {
                unit.key: lambda key=unit.key: system.run_unit(key)
                for unit in DEFAULT_UNITS.active(enabled)
            }
        )
        return MolStatOrchestrator(
            system.database,
            runners,
            owner=socket.gethostname() or "molstat-pc",
            failure_reporter=self._record_job_failure,
        )

    def load_settings_fields(self) -> dict[str, str]:
        if not self._settings_exist:
            fields = {
                "sensitive_root": "",
                "sharepoint_root": "",
                "lvms_url": "",
            }
            fields.update(
                {
                    f"lookup_{unit.key}": ""
                    for unit in DEFAULT_UNITS.for_job("statistics")
                }
            )
            fields.update(
                {
                    f"enabled_{unit.key}": "true"
                    for unit in DEFAULT_UNITS.active()
                }
            )
            return fields
        lookups = self.settings.statistics_lookup_paths
        fields = {
            "sensitive_root": str(self.settings.sensitive_root),
            "sharepoint_root": (
                str(self.settings.sharepoint_root)
                if self.settings.sharepoint_root is not None
                else ""
            ),
            "lvms_url": self.settings.lvms_url,
        }
        fields.update(
            {
                f"lookup_{unit.key}": str(lookups.get(unit.key, ""))
                for unit in DEFAULT_UNITS.for_job("statistics")
            }
        )
        fields.update(
            {
                f"enabled_{unit.key}": (
                    "true" if unit.key in self.settings.enabled_units else "false"
                )
                for unit in DEFAULT_UNITS.active()
            }
        )
        return fields

    def overview_status_fields(self) -> dict[str, tuple[str, str]]:
        if not self._settings_exist:
            return {
                "database": ("Ikke satt opp", "Velg K-sensitiv mappe i Innstillinger"),
                "sharepoint": ("Ikke satt opp", "Velg mappe i Innstillinger"),
            }

        database_status = (
            ("Klar", "K-sensitiv mappe er tilgjengelig")
            if self.settings.sensitive_root.is_dir()
            else ("Ikke tilgjengelig", "Kontroller K-sensitiv mappe")
        )
        sharepoint = self.settings.sharepoint_root
        if sharepoint is None:
            sharepoint_status = ("Ikke satt opp", "Velg mappe i Innstillinger")
        elif sharepoint.is_dir():
            sharepoint_status = ("Klar", "Konfigurert mappe er tilgjengelig")
        else:
            sharepoint_status = (
                "Ikke tilgjengelig",
                "Kontroller SharePoint-synkronisering og mappe",
            )
        return {
            "database": database_status,
            "sharepoint": sharepoint_status,
        }

    def save_settings_fields(self, values: dict[str, str]) -> None:
        sensitive_text = values.get("sensitive_root", "").strip()
        if not sensitive_text:
            raise ValueError("K-sensitiv mappe må fylles ut.")
        sharepoint_text = values.get("sharepoint_root", "").strip()
        lookups = {
            unit.key: Path(text)
            for unit in DEFAULT_UNITS.for_job("statistics")
            if (text := values.get(f"lookup_{unit.key}", "").strip())
        }
        updated = replace(
            self.settings,
            sensitive_root=Path(sensitive_text),
            sharepoint_root=Path(sharepoint_text) if sharepoint_text else None,
            statistics_lookup_paths=lookups,
            lvms_url=values.get("lvms_url", "").strip(),
            enabled_units=tuple(
                unit.key
                for unit in DEFAULT_UNITS.active()
                if values.get(
                    f"enabled_{unit.key}",
                    "true" if unit.key in self.settings.enabled_units else "false",
                ).casefold()
                == "true"
            ),
        )
        errors = updated.validate()
        if errors:
            raise ValueError(errors[0])
        _validate_production_paths(updated)
        updated.save(self.settings_path)
        self.settings = updated
        self._settings_exist = True

    def export_settings(self, path: Path) -> None:
        self.settings.export_to(path)

    def import_settings(self, path: Path) -> tuple[str, ...]:
        imported = MolStatSettings.import_from(path)
        warnings = _unavailable_path_messages(imported)
        imported.save(self.settings_path)
        self.settings = imported
        self._settings_exist = True
        return warnings

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
    for unit in DEFAULT_UNITS.for_job("statistics", settings.enabled_units):
        lookup = settings.statistics_lookup_paths.get(unit.key)
        if lookup is None or not lookup.is_file():
            raise ValueError(f"Lookup-fil for {unit.display_name} finnes ikke.")
    parsed = urlparse(settings.lvms_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("LVMS-adressen må være en fullstendig http- eller https-adresse.")


def _unavailable_path_messages(settings: MolStatSettings) -> tuple[str, ...]:
    unavailable: list[str] = []
    if not settings.sensitive_root.is_dir():
        unavailable.append("K-sensitiv mappe")
    if settings.sharepoint_root is None or not settings.sharepoint_root.is_dir():
        unavailable.append("SharePoint-mappe")
    for unit in DEFAULT_UNITS.for_job("statistics", settings.enabled_units):
        lookup = settings.statistics_lookup_paths.get(unit.key)
        if lookup is None or not lookup.is_file():
            unavailable.append(f"Lookup-fil for {unit.display_name}")
    return tuple(unavailable)
