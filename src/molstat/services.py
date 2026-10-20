from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from datetime import datetime, timezone
from dataclasses import replace
import json
import os
from pathlib import Path
import socket
import sqlite3
from threading import Event
import traceback
from urllib.parse import urlparse

from .archive import RawArchive
from .storage_layout import StorageLayout, prepare_storage_layout
from .backlog import BacklogProcessor, CsvContract, CsvImportError
from .backup import backup_before_migration
from .config import MolStatSettings
from .database import SCHEMA_VERSION, MolStatDatabase
from .fetching import UnifiedLvmsFetcher
from .failures import RunFailure, database_failure
from .unit_settings import load_active_units, load_unit_file, load_backlog_file, write_json, UnitConfigError
from ._backlog.config import validate_app_config
from .delivery import retry_pending
from .excel_search import read_excel_snapshot, publish_search_workbook
from .modules import DEFAULT_UNITS, UnitRegistry, configured_registry
from .orchestrator import JobResult, MolStatOrchestrator
from .publisher import PublicationPolicy, SharePointPublisher, default_forbidden_patterns
from .schedule import due_jobs
from .statistics import StatisticsProcessor
from .lvms.config import validate_app_config as validate_lvms_config
from .system import CapabilityRun, MolStatSystem, ExcelRefreshStatus
from .manual_import import ManualImportPlan, ManualImportError
from ._writer_lease import guarded_output, WriterLeaseLost


class DefaultServices:
    def __init__(self, settings_path: Path) -> None:
        self.settings_path = settings_path
        self._diagnostics: deque[str] = deque(maxlen=100)
        self._unit_readiness: dict[str, tuple[str, str]] = {}
        self._capability_readiness: dict[tuple[str, str], str | None] = {}
        self._settings_exist = settings_path.is_file()
        self._settings_load_error: str | None = None
        self.settings = MolStatSettings(sensitive_root=Path("."))
        if self._settings_exist:
            try:
                self.settings = MolStatSettings.load(settings_path)
            except (ValueError, OSError) as exc:
                self._settings_exist = False
                self._settings_load_error = "Innstillingsfilen kunne ikke leses. Originalfilen er bevart. Rett opp eller importer innstillinger."
                self._record_job_failure("settings_configuration_failed", exc)

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
        if not self._settings_exist:
            print(json.dumps({"status": "failed", "message": "Konfigurer MolStat først."}, ensure_ascii=False))
            return 2
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
        if self._settings_load_error:
            raise ValueError(self._settings_load_error)
        layout = prepare_storage_layout(self.settings.sensitive_root)
        database = MolStatDatabase(layout.database_path)
        if database.schema_version_if_present() == SCHEMA_VERSION:
            return database
        backup_before_migration(
            database,
            layout.backups_root,
        )
        database.migrate()
        return database

    def _build_system(
        self,
        *,
        require_statistics: bool,
        unit_keys: Sequence[str] | None = None,
        require_lvms: bool = True,
    ) -> MolStatSystem:
        if not self._settings_exist:
            raise ValueError(self._settings_load_error or "MolStat må konfigureres i Innstillinger.")
        if self.settings.sharepoint_root is None:
            raise ValueError("SharePoint-mappe mangler.")
        errors = self.settings.validate()
        if errors:
            raise ValueError(errors[0])
        if not self.settings.sensitive_root.is_dir():
            raise ValueError("K-sensitiv mappe er ikke tilgjengelig. Ingen erstatningsdatabase opprettes.")
        selected = tuple(self.settings.enabled_units if unit_keys is None else unit_keys)
        if set(selected) - set(self.settings.enabled_units):
            raise ValueError("Aktiver enheten i Innstillinger før kjøring.")
        definitions = {}
        definition_errors = {}
        for key in selected:
            try:
                definitions.update(load_active_units(
                    self.settings.sensitive_root, self.settings.unit_config_paths, (key,),
                    backlog_paths=self.settings.backlog_config_paths,
                ))
            except Exception as exc:
                definition_errors[key] = RunFailure("CONFIG_INVALID", "unit_configuration")
                self._record_job_failure(f"{key}_configuration_failed", exc)
        valid_registry = configured_registry(definitions)
        valid_by_key = {unit.key: unit for unit in valid_registry}
        registry = UnitRegistry(tuple(
            valid_by_key.get(key) or DEFAULT_UNITS.require(key) for key in selected
        ))
        capability_errors = {
            (key, capability.job_kind): error
            for key, error in definition_errors.items()
            for capability in registry.require(key).capabilities
        }
        local_root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "MolStat"
        database = self._database()
        fetcher, fetch_error = None, None
        if require_lvms:
            try:
                lvms_config = self._ensure_lvms_config(local_root)
                fetcher = UnifiedLvmsFetcher(
                    lvms_config_path=lvms_config, sensitive_root=self.settings.sensitive_root,
                    work_root=StorageLayout(self.settings.sensitive_root).raw_root / ".jobs",
                    units=tuple(item.unit for item in definitions.values()),
                    backlog_reports={key: item.payload["backlog"]["report"] for key, item in definitions.items() if item.payload.get("backlog")},
                )
            except Exception as exc:
                fetch_error = RunFailure("LVMS_CONFIG_INVALID", "lvms_configuration")
                self._record_job_failure("lvms_configuration_failed", exc)

        def unavailable_fetch(*args, **kwargs):
            raise RunFailure("LVMS_CONFIG_INVALID", "fetch_unavailable")

        statistics_fetch = fetcher.fetch_statistics if fetcher else unavailable_fetch
        backlog_fetch = fetcher.fetch_backlog if fetcher else unavailable_fetch
        statistics_processors, publishers = {}, {}
        for definition in valid_registry.for_job("statistics") if require_statistics else ():
            capability = definition.capability("statistics")
            publishers[definition.key] = SharePointPublisher(PublicationPolicy(
                allowed_columns=capability.allowed_columns, forbidden_patterns=default_forbidden_patterns(),
            ))
            statistics_processors[definition.key] = StatisticsProcessor(
                profile=capability.processor_profile, database=database,
                analysis_codes=set(definitions[definition.key].unit.analysis_codes),
                report_codes={role: report["analysis_codes"] for role, report in definitions[definition.key].payload["statistics"].items()},
                report_ids={role: report["report_id"] for role, report in definitions[definition.key].payload["statistics"].items()},
            )
        backlog_processors, backlog_publishers, backlog_fetchers = {}, {}, {}
        for definition in valid_registry.for_job("backlog"):
            key = definition.key
            payload = definitions[key].payload["backlog"]
            raw = payload["columns"]
            contract = CsvContract(delimiter=raw["delimiter"], encoding=raw["encoding"],
                                   columns=raw["columns"], completed_values=tuple(raw["completed_values"]),
                                   classifier_version=raw["classifier_version"])
            backlog_publishers[key] = SharePointPublisher(PublicationPolicy(
                allowed_columns=definition.capability("backlog").allowed_columns,
                forbidden_patterns=default_forbidden_patterns(),
            ))
            try:
                backlog_processors[key] = BacklogProcessor(validate_app_config(payload["analyses"]), contract,
                                                           analysis_lookup={})
            except Exception as exc:
                capability_errors[(key, "backlog")] = RunFailure("CONFIG_INVALID", "backlog_configuration")
                self._record_job_failure(f"{key}_backlog_configuration_failed", exc)
            # Preserve the default no-argument hook for existing integrations.
            backlog_fetchers[key] = (backlog_fetch if key == "hemato" or fetcher is None else
                                    lambda unit=key: fetcher.fetch_backlog(unit))
        system = MolStatSystem(
            database=database, archive=RawArchive(self.settings.sensitive_root),
            statistics_processors=statistics_processors,
            backlog_processor=backlog_processors.get("hemato"), publisher=publishers,
            backlog_publisher=backlog_publishers.get("hemato"),
            excel_search_path=self.settings.sensitive_root / "Prøvesøk.xlsx",
            excel_failure_reporter=self._record_job_failure,
            sharepoint_root=self.settings.sharepoint_root,
            work_root=StorageLayout(self.settings.sensitive_root).processed_root,
            statistics_fetch=statistics_fetch, backlog_fetch=backlog_fetch,
            units=registry,
            capability_errors=capability_errors,
            fetch_error=fetch_error,
        )
        system.backlog_processors = backlog_processors
        system.backlog_publishers = backlog_publishers
        system.backlog_fetchers = backlog_fetchers
        for unit in registry:
            considered = tuple(cap for cap in unit.capabilities
                               if require_statistics or cap.job_kind != "statistics" or unit.key in definition_errors)
            if not considered:
                continue
            for cap in considered:
                error = capability_errors.get((unit.key, cap.job_kind))
                self._capability_readiness[(unit.key, cap.job_kind)] = error.code if error else None
            errors = tuple(self._capability_readiness[(unit.key, cap.job_kind)]
                           for cap in unit.capabilities
                           if self._capability_readiness.get((unit.key, cap.job_kind)))
            if errors:
                label = "Oppsett må rettes" if len(errors) == len(unit.capabilities) else "Delvis klar"
                detail = "; ".join(dict.fromkeys(
                    "Kontroller enhetsfilen i Innstillinger" if code == "CONFIG_INVALID"
                    else "Kontroller enhetsoppsettet i Innstillinger" for code in errors
                ))
                self._unit_readiness[unit.key] = (label, detail)
            elif fetch_error is not None:
                self._unit_readiness[unit.key] = ("Manuell import tilgjengelig", "LVMS-oppsettet må rettes for automatisk uttrekk")
            else:
                self._unit_readiness[unit.key] = ("Klar", "Oppsettet er validert for denne enheten")
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
                unit.key: lambda key=unit.key: self._build_system(require_statistics=True, unit_keys=(key,)).run_unit(key)
                for unit in system.units.active(enabled)
            }
        )
        runners.update({
            f"{unit.key}:backlog": lambda key=unit.key: self._build_system(
                require_statistics=False, unit_keys=(key,)).run_job("backlog", (key,))
            for unit in system.units.for_job("backlog", enabled)
        })

        return MolStatOrchestrator(
            system.database,
            runners,
            owner=socket.gethostname() or "molstat-pc",
            failure_reporter=self._record_job_failure,
        )

    def unit_status_fields(self) -> dict[str, tuple[str, str]]:
        return {
            key: self._unit_readiness.get(key, ("Ikke kontrollert", "Lagre eller kontroller innstillingene"))
            for key in self.settings.enabled_units
        }

    def unit_definitions(self) -> UnitRegistry:
        system = getattr(self, "_last_system", None)
        return system.units if system is not None else DEFAULT_UNITS

    def _manual_import_definition(self, unit_key: str):
        if unit_key not in self.settings.enabled_units:
            raise ManualImportError("Aktiver enheten i Innstillinger før manuell import.")
        if not self._settings_exist or not self.settings.sensitive_root.is_dir():
            raise ManualImportError("Konfigurer en tilgjengelig K-sensitiv mappe før manuell import.")
        return load_active_units(
            self.settings.sensitive_root, self.settings.unit_config_paths, (unit_key,),
            backlog_paths=self.settings.backlog_config_paths,
        )[unit_key]

    def manual_import_available_jobs(self, unit_key: str) -> tuple[str, ...]:
        definition = self._manual_import_definition(unit_key)
        return ("statistics", "backlog") if definition.payload.get("backlog") else ("statistics",)

    def manual_import_roles(self, unit_key: str, job_kind: str) -> tuple[str, ...]:
        from .manual_import import manual_import_roles

        return manual_import_roles(self._manual_import_definition(unit_key), job_kind)

    def manual_import(self, plan: ManualImportPlan) -> JobResult:
        from .manual_import import process_manual_import, validate_manual_import

        if plan.unit_key not in self.settings.enabled_units:
            raise ManualImportError("Aktiver enheten i Innstillinger før manuell import.")
        if plan.job_kind not in ("statistics", "backlog"):
            raise ManualImportError("Velg statistikk eller restanse.")
        if not self._settings_exist or not self.settings.sensitive_root.is_dir():
            raise ManualImportError("Konfigurer en tilgjengelig K-sensitiv mappe før manuell import.")

        def runner():
            try:
                definition = self._manual_import_definition(plan.unit_key)
                validate_manual_import(plan, definition)
                system = self._build_system(
                    require_statistics=plan.job_kind == "statistics",
                    unit_keys=(plan.unit_key,), require_lvms=False,
                )
                error = system.capability_errors.get((plan.unit_key, plan.job_kind))
                if error is not None:
                    raise error
                return process_manual_import(system, plan, definition)
            except Exception as exc:
                if isinstance(exc, UnitConfigError):
                    self._unit_readiness[plan.unit_key] = ("Oppsett må rettes", "Kontroller enhetsfilen i Innstillinger")
                return (CapabilityRun(plan.unit_key, plan.job_kind, {}, exc),)

        orchestrator = MolStatOrchestrator(
            self._database(), {plan.unit_key: runner},
            owner=socket.gethostname() or "molstat-pc",
            failure_reporter=self._record_job_failure,
        )
        return orchestrator.run(plan.unit_key, "manual_import")

    def load_settings_fields(self) -> dict[str, str]:
        if not self._settings_exist:
            fields = {
                "sensitive_root": "",
                "sharepoint_root": "",
                "lvms_url": "",
            }
            fields.update(
                {
                    f"enabled_{unit.key}": (
                        "true" if unit.key in self.settings.enabled_units else "false"
                    )
                    for unit in DEFAULT_UNITS.active()
                }
            )
            return fields
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
                f"enabled_{unit.key}": (
                    "true" if unit.key in self.settings.enabled_units else "false"
                )
                for unit in DEFAULT_UNITS.active()
            }
        )

        for unit in DEFAULT_UNITS.active():
            configured = self.settings.unit_config_paths.get(unit.key)
            fields[f"config_{unit.key}"] = str(configured or "")
        fields.update({f"backlog_{key}": str(self.settings.backlog_config_paths.get(key, ""))
                       for key in ("hemato", "solide")})
        fields.update({key: str(getattr(self.settings, key)) for key in ("statistics_hour", "backlog_first_hour", "backlog_last_hour")})
        return fields

    def regenerate_excel(self) -> dict[str, object]:
        if self._settings_load_error:
            raise ValueError(self._settings_load_error)
        database = self._database()
        now = datetime.now()
        snapshot = read_excel_snapshot(database, generated_at=now)
        with guarded_output():
            result = publish_search_workbook(snapshot, self.settings.sensitive_root / "Prøvesøk.xlsx")
        if hasattr(self, "_last_system"):
            self._last_system.excel_status = ExcelRefreshStatus(result.status, now)
        if result.status != "published":
            raise RunFailure("EXCEL_REFRESH_FAILED", "excel_publication")
        return {"excel_published": True}

    def retry_publication(self) -> tuple[CapabilityRun, ...]:
        system = self._build_system(require_statistics=True, require_lvms=False)
        runs = []
        for unit in system.units:
            for capability in unit.capabilities:
                try:
                    publishers = system.publisher if capability.job_kind == "statistics" else system.backlog_publishers
                    publisher = publishers.get(unit.key)
                    if publisher is None:
                        raise system.capability_errors.get(
                            (unit.key, capability.job_kind), RunFailure("CONFIG_INVALID", "publication_configuration")
                        )
                    published = retry_pending(publisher, system.work_root / unit.key / capability.job_kind,
                                              system.sharepoint_root / capability.sharepoint_folder)
                    runs.append(CapabilityRun(unit.key, capability.job_kind, {"published": published}))
                except Exception as error:
                    runs.append(CapabilityRun(unit.key, capability.job_kind, {}, error))
        return tuple(runs)

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
        if system and system.fetch_error is not None:
            statuses["lvms"] = ("Oppsett må rettes", "Manuell import kan brukes mens LVMS-oppsettet rettes")
        else:
            statuses["lvms"] = ("Konfigurert", "Innlogging og forbindelse kontrolleres ved automatisk uttrekk")
        excel_status = getattr(system, "excel_status", None)
        if excel_status and excel_status.status != "published":
            statuses["excel"] = ("Ikke oppdatert", "Lukk Excel-filen og velg Oppdater Excel-søk")
        return statuses

    def save_settings_fields(self, values: dict[str, str]) -> None:
        sensitive_text = values.get("sensitive_root", "").strip()
        if not sensitive_text:
            raise ValueError("K-sensitiv mappe må fylles ut.")
        sharepoint_text = values.get("sharepoint_root", "").strip()
        updated = replace(
            self.settings,
            sensitive_root=Path(sensitive_text),
            sharepoint_root=Path(sharepoint_text) if sharepoint_text else None,
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
        errors = updated.validate()
        if errors:
            raise ValueError(errors[0])
        _validate_production_paths(updated)
        config_paths = dict(updated.unit_config_paths)
        backlog_paths = dict(updated.backlog_config_paths)
        for key in DEFAULT_UNITS.active():
            name = key.key
            config_text = values.get(f"config_{name}")
            if config_text is not None:
                if config_text.strip():
                    config_paths[name] = Path(config_text.strip()).resolve()
                else:
                    config_paths.pop(name, None)
            if name in {"hemato", "solide"}:
                backlog_text = values.get(f"backlog_{name}")
                if backlog_text is not None:
                    if backlog_text.strip():
                        backlog_paths[name] = Path(backlog_text.strip()).resolve()
                    else:
                        backlog_paths.pop(name, None)
        for key in updated.enabled_units:
            source = config_paths.get(key)
            if source is None:
                raise UnitConfigError(f"Enhetsfil (JSON) mangler for {key}.")
            load_unit_file(source, key, backlog_path=backlog_paths.get(key))
        updated = replace(updated, unit_config_paths=config_paths, backlog_config_paths=backlog_paths)
        updated.save(self.settings_path)
        self.settings = updated
        self._settings_exist = True
        self._settings_load_error = None
        self._unit_readiness.clear()
        self._capability_readiness.clear()

    def export_settings(self, path: Path) -> None:
        self.settings.export_to(path)

    def import_settings(self, path: Path) -> tuple[str, ...]:
        imported = MolStatSettings.import_from(path)
        for key, source in imported.backlog_config_paths.items():
            if source.is_file():
                load_backlog_file(source, key)
        for key, source in imported.unit_config_paths.items():
            if source.is_file():
                backlog_path = imported.backlog_config_paths.get(key)
                load_unit_file(source, key, backlog_path=backlog_path if backlog_path and backlog_path.is_file() else None)
        warnings = _unavailable_path_messages(imported)
        imported.save(self.settings_path)
        self.settings = imported
        self._settings_exist = True
        self._settings_load_error = None
        self._unit_readiness.clear()
        self._capability_readiness.clear()
        return warnings

    def _ensure_lvms_config(self, local_root: Path) -> Path:
        path = self.settings.lvms_config_path or local_root / "lvms-config.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("LVMS-oppsettet må være et JSON-objekt.")
            if self.settings.lvms_url and payload.get("landing_url") != self.settings.lvms_url:
                payload["landing_url"] = self.settings.lvms_url
                # The origin is derived from the newly selected URL. Preserve
                # other local runtime fields and validate before replacing it.
                had_origin = "expected_origin" in payload
                payload.pop("expected_origin", None)
                validated = validate_lvms_config(
                    payload,
                    repository_root=Path(__file__).resolve().parents[2],
                    allowed_local_root=local_root.parent,
                )
                if had_origin:
                    payload["expected_origin"] = validated.expected_origin
                write_json(path, payload)
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
        if isinstance(error, WriterLeaseLost):
            reason = error.reason if error.reason in {"OWNERSHIP_CHANGED", "EXPIRED", "RENEWAL_FAILED"} or (
                error.reason.startswith("SQLITE_") and isinstance(getattr(sqlite3, error.reason, None), int)) else ""
            safe_error = RunFailure("DB_LEASE_LOST", "writer_lease", detail=reason)
        if isinstance(error, CsvImportError):
            safe_error = RunFailure("CSV_INVALID", "csv_import")
        message = f"{stage}: {safe_error if isinstance(safe_error, (RunFailure, UnitConfigError, ManualImportError)) else type(error).__name__}"
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
    parsed = urlparse(settings.lvms_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("LVMS-adressen må være en fullstendig http- eller https-adresse.")


def _unavailable_path_messages(settings: MolStatSettings) -> tuple[str, ...]:
    unavailable: list[str] = []
    if not settings.sensitive_root.is_dir():
        unavailable.append("K-sensitiv mappe")
    if settings.sharepoint_root is None or not settings.sharepoint_root.is_dir():
        unavailable.append("SharePoint-mappe")
    for key, source in settings.unit_config_paths.items():
        if key in settings.enabled_units and not source.is_file():
            unavailable.append(f"Enhetsfil for {key}")
    for key, source in settings.backlog_config_paths.items():
        if key in settings.enabled_units and not source.is_file():
            unavailable.append(f"Restansefil for {key}")
    return tuple(unavailable)
