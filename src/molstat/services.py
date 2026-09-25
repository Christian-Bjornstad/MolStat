from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from dataclasses import replace
import json
import hashlib
import os
from pathlib import Path
import socket
import sqlite3
import shutil
from uuid import uuid4
from threading import Event
import traceback
from urllib.parse import urlparse

from .archive import RawArchive
from .backlog import BacklogProcessor, CsvContract, CsvImportError
from .backup import backup_before_migration
from .config import MolStatSettings
from .database import SCHEMA_VERSION, MolStatDatabase
from .fetching import UnifiedLvmsFetcher
from .failures import RunFailure, database_failure
from .unit_settings import load_active_units, materialize_snapshot, load_unit_file, write_json, upgrade_source, UnitConfigError
from ._backlog.config import validate_app_config
from .delivery import retry_pending
from .excel_search import read_excel_snapshot, publish_search_workbook
from .modules import DEFAULT_UNITS, configured_registry
from .orchestrator import MolStatOrchestrator
from .publisher import PublicationPolicy, SharePointPublisher, default_forbidden_patterns
from .schedule import due_jobs
from .statistics import StatisticsProcessor, load_lookup
from ._statistics.specialized_lookup import default_lookup_path
from ._statistics.lege_lookup import default_lege_lookup_path, validate_lege_lookup
from .system import MolStatSystem, ExcelRefreshStatus


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
            if isinstance(exc, sqlite3.Error):
                return None, str(database_failure(exc))
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
        if (self.settings.sensitive_root / "molstat.sqlite3").is_file():
            raise ValueError("DB_LOCATION: Du har valgt selve databasemappen. Velg MolStat-roten som inneholder data-mappen; eksisterende database er bevart.")
        database = MolStatDatabase(
            self.settings.sensitive_root / "data" / "molstat.sqlite3"
        )
        if database.schema_version_if_present() == SCHEMA_VERSION:
            return database
        backup_before_migration(
            database,
            self.settings.sensitive_root / "data" / "backups",
        )
        database.migrate()
        return database

    def _build_system(self, *, require_statistics: bool) -> MolStatSystem:
        if not self._settings_exist:
            raise ValueError("MolStat må konfigureres i Innstillinger.")
        if self.settings.sharepoint_root is None:
            raise ValueError("SharePoint-mappe mangler.")
        errors = self.settings.validate()
        if errors:
            raise ValueError(errors[0])
        if not self.settings.sensitive_root.is_dir():
            raise ValueError("K-sensitiv mappe er ikke tilgjengelig. Ingen erstatningsdatabase opprettes.")
        definitions = load_active_units(self.settings.sensitive_root, self.settings.unit_config_paths, self.settings.enabled_units)
        config_root = materialize_snapshot(self.settings.sensitive_root, definitions)
        registry = configured_registry(definitions)
        local_root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "MolStat"
        lvms_config = self._ensure_lvms_config(local_root)
        database = self._database()
        fetcher = UnifiedLvmsFetcher(
            lvms_config_path=lvms_config, sensitive_root=self.settings.sensitive_root,
            work_root=self.settings.sensitive_root / "work" / "fetch",
            units_path=config_root / "units.json",
            backlog_report_path=config_root / "hemato" / "backlog-report.json",
            lege_lookup_path=self.settings.statistics_lookup_paths.get("lege") or default_lege_lookup_path(),
        )
        statistics_processors, publishers = {}, {}
        for definition in registry.for_job("statistics") if require_statistics else ():
            capability = definition.capability("statistics")
            lookup = self.settings.statistics_lookup_paths.get(definition.key)
            if lookup is None and capability.processor_profile in {"flow", "fish", "pre"}:
                lookup = default_lookup_path(capability.processor_profile)
            if lookup is None and capability.processor_profile == "lege":
                lookup = default_lege_lookup_path()
            if lookup is None:
                raise ValueError(f"Lookup-fil mangler for {definition.display_name}.")
            if capability.processor_profile in {"flow", "fish", "pre"}:
                from ._statistics.specialized_lookup import validate_lookup
                validate_lookup(
                    lookup, capability.processor_profile,
                    set(definitions[definition.key].unit.analysis_codes),
                )
            elif capability.processor_profile == "lege":
                validate_lege_lookup(lookup)
            elif capability.processor_profile != "lege":
                load_lookup(lookup)
            statistics_processors[definition.key] = StatisticsProcessor(
                lookup, profile=capability.processor_profile, database=database,
                report_ids={role: report["report_id"] for role, report in definitions[definition.key].payload["statistics"].items()},
            )
            publishers[definition.key] = SharePointPublisher(PublicationPolicy(
                allowed_columns=capability.allowed_columns, forbidden_patterns=default_forbidden_patterns(),
            ))
        backlog_processors, backlog_publishers, backlog_fetchers = {}, {}, {}
        for definition in registry.for_job("backlog"):
            key = definition.key
            payload = definitions[key].payload["backlog"]
            raw = payload["columns"]
            contract = CsvContract(delimiter=raw["delimiter"], encoding=raw["encoding"],
                                   columns=raw["columns"], completed_values=tuple(raw["completed_values"]),
                                   classifier_version=raw["classifier_version"])
            lookup = self.settings.statistics_lookup_paths.get(key)
            backlog_processors[key] = BacklogProcessor(validate_app_config(payload["analyses"]), contract,
                                                       analysis_lookup=load_lookup(lookup) if lookup else {})
            backlog_publishers[key] = SharePointPublisher(PublicationPolicy(
                allowed_columns=definition.capability("backlog").allowed_columns,
                forbidden_patterns=default_forbidden_patterns(),
            ))
            # Preserve the default no-argument hook for existing integrations.
            backlog_fetchers[key] = (fetcher.fetch_backlog if key == "hemato" else
                                    lambda unit=key: fetcher.fetch_backlog(unit, config_root / unit / "backlog-report.json"))
        system = MolStatSystem(
            database=database, archive=RawArchive(self.settings.sensitive_root),
            statistics_processors=statistics_processors,
            backlog_processor=backlog_processors.get("hemato"), publisher=publishers,
            backlog_publisher=backlog_publishers.get("hemato"),
            excel_search_path=self.settings.sensitive_root / "Prøvesøk.xlsx",
            excel_failure_reporter=self._record_job_failure,
            sharepoint_root=self.settings.sharepoint_root,
            work_root=self.settings.sensitive_root / "processed",
            statistics_fetch=fetcher.fetch_statistics, backlog_fetch=fetcher.fetch_backlog,
            units=registry,
        )
        system.backlog_processors = backlog_processors
        system.backlog_publishers = backlog_publishers
        system.backlog_fetchers = backlog_fetchers
        self._last_system = system
        return system

    def _orchestrator(self, system: MolStatSystem) -> MolStatOrchestrator:
        enabled = self.settings.enabled_units
        runners = {
            "all": lambda: self._build_system(require_statistics=True).run_all(enabled),
            "statistics": lambda: self._build_system(require_statistics=True).run_job("statistics", enabled),
            "backlog": lambda: self._build_system(require_statistics=False).run_job("backlog", enabled),
            "excel": self.regenerate_excel,
            "publish": self.retry_publication,
        }
        runners.update(
            {
                unit.key: lambda key=unit.key: self._build_system(require_statistics=True).run_unit(key)
                for unit in system.units.active(enabled)
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
                    f"lookup_{unit.key}": (
                        str(default_lookup_path(unit.key))
                        if unit.key in {"flow", "fish", "pre"}
                        else str(default_lege_lookup_path()) if unit.key == "lege" else ""
                    )
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
                f"lookup_{unit.key}": str(
                    lookups.get(unit.key)
                    or (default_lookup_path(unit.key) if unit.key in {"flow", "fish", "pre"}
                        else default_lege_lookup_path() if unit.key == "lege" else "")
                )
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

        fields.update({f"config_{key}": str(self.settings.unit_config_paths.get(key) or self.settings.sensitive_root / "config" / "units" / f"{key}.json") for key in self.settings.enabled_units})
        fields.update({key: str(getattr(self.settings, key)) for key in ("statistics_hour", "backlog_first_hour", "backlog_last_hour")})
        return fields

    def regenerate_excel(self) -> dict[str, object]:
        database = self._database()
        now = datetime.now()
        snapshot = read_excel_snapshot(database, generated_at=now)
        result = publish_search_workbook(snapshot, self.settings.sensitive_root / "Prøvesøk.xlsx")
        if hasattr(self, "_last_system"):
            self._last_system.excel_status = ExcelRefreshStatus(result.status, now)
        if result.status != "published":
            raise RunFailure("EXCEL_REFRESH_FAILED", "excel_publication")
        return {"excel_published": True}

    def retry_publication(self) -> dict[str, object]:
        system = self._build_system(require_statistics=True)
        published = 0
        for unit in system.units:
            for capability in unit.capabilities:
                publisher = (system.publisher[unit.key] if capability.job_kind == "statistics"
                             else system.backlog_publishers[unit.key])
                published += retry_pending(publisher, system.work_root / unit.key / capability.job_kind,
                                           system.sharepoint_root / capability.sharepoint_folder)
        return {"published": published}

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
        statuses = {
            "database": database_status,
            "sharepoint": sharepoint_status,
        }
        workbook = self.settings.sensitive_root / "Prøvesøk.xlsx"
        statuses["excel"] = (("Tilgjengelig", "Sist oppdatert " + datetime.fromtimestamp(workbook.stat().st_mtime).strftime("%d.%m.%Y %H:%M"))
                             if workbook.is_file() else ("Ikke generert", "Oppdater fra eksisterende database"))
        system = getattr(self, "_last_system", None)
        excel_status = getattr(system, "excel_status", None)
        if excel_status and excel_status.status != "published":
            statuses["excel"] = ("Ikke oppdatert", "Lukk Excel-filen og velg Oppdater Excel-søk")
        return statuses

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
            statistics_hour=int(values.get("statistics_hour", self.settings.statistics_hour)),
            backlog_first_hour=int(values.get("backlog_first_hour", self.settings.backlog_first_hour)),
            backlog_last_hour=int(values.get("backlog_last_hour", self.settings.backlog_last_hour)),
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
        updated = replace(updated, statistics_lookup_paths={
            **updated.statistics_lookup_paths,
            **{
                key: default_lookup_path(key)
                for key in updated.enabled_units
                if key in {"flow", "fish", "pre"}
                and key not in updated.statistics_lookup_paths
            },
            **({"lege": default_lege_lookup_path()}
               if "lege" in updated.enabled_units and "lege" not in updated.statistics_lookup_paths
               else {}),
        })
        errors = updated.validate()
        if errors:
            raise ValueError(errors[0])
        _validate_production_paths(updated)
        candidates = {}
        for key in updated.enabled_units:
            text = values.get(f"config_{key}", "").strip()
            source = Path(text) if text else updated.unit_config_paths.get(key)
            if source is None:
                source = updated.sensitive_root / "config" / "units" / f"{key}.json"
                if not source.exists():
                    source = upgrade_source(updated.sensitive_root, key)
            candidates[key] = load_unit_file(source, key)
        # Prepare complete versions first; only the settings pointer activates them.
        # Failure while preparing another file cannot replace the active settings.
        config_paths = dict(updated.unit_config_paths)
        for key, candidate in candidates.items():
            destination = updated.sensitive_root / "config" / "units" / key / f"{candidate.digest}.json"
            write_json(destination, candidate.payload)
            config_paths[key] = destination
        lookup_paths = dict(updated.statistics_lookup_paths)
        for key, source in lookup_paths.items():
            with source.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            destination = updated.sensitive_root / "config" / "lookups" / key / f"{digest}{source.suffix.lower()}"
            if source.resolve() != destination.resolve():
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
                try:
                    shutil.copyfile(source, temporary)
                    with temporary.open("rb") as stream:
                        if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                            raise ValueError("Lookup-filen endret seg under kopiering. Prøv igjen.")
                    os.replace(temporary, destination)
                finally:
                    temporary.unlink(missing_ok=True)
            lookup_paths[key] = destination
        updated = replace(updated, unit_config_paths=config_paths, statistics_lookup_paths=lookup_paths)
        updated.save(self.settings_path)
        self.settings = updated
        self._settings_exist = True

    def export_settings(self, path: Path) -> None:
        self.settings.export_to(path)

    def import_settings(self, path: Path) -> tuple[str, ...]:
        imported = MolStatSettings.import_from(path)
        for key, source in imported.unit_config_paths.items():
            if source.is_file():
                load_unit_file(source, key)
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
        safe_error = database_failure(error) if isinstance(error, sqlite3.Error) else error
        if isinstance(error, CsvImportError):
            safe_error = RunFailure("CSV_INVALID", "csv_import")
        message = f"{stage}: {safe_error if isinstance(safe_error, (RunFailure, UnitConfigError)) else type(error).__name__}"
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
        if unit.key == "lege":
            lookup = settings.statistics_lookup_paths.get("lege") or default_lege_lookup_path()
            if not lookup.is_file():
                raise ValueError("Legeregister for Patologer finnes ikke.")
            validate_lege_lookup(lookup)
            continue
        lookup = settings.statistics_lookup_paths.get(unit.key) or (
            default_lookup_path(unit.key) if unit.key in {"flow", "fish", "pre"} else None
        )
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
        if unit.key == "lege":
            lookup = settings.statistics_lookup_paths.get("lege") or default_lege_lookup_path()
            if not lookup.is_file():
                unavailable.append("Legeregister for Patologer")
            continue
        lookup = settings.statistics_lookup_paths.get(unit.key) or (
            default_lookup_path(unit.key) if unit.key in {"flow", "fish", "pre"} else None
        )
        if lookup is None or not lookup.is_file():
            unavailable.append(f"Lookup-fil for {unit.display_name}")
    for key, source in settings.unit_config_paths.items():
        if key in settings.enabled_units and not source.is_file():
            unavailable.append(f"Enhetsfil for {key}")
    return tuple(unavailable)
