"""Unit configuration failures must never become unrelated unit failures."""
from dataclasses import replace
from datetime import date, timedelta
import json
from pathlib import Path

import pytest

from molstat.database import MolStatDatabase, WriterLeaseBusy
from molstat.orchestrator import MolStatOrchestrator
from molstat.services import DefaultServices
from molstat.system import CapabilityRun
from molstat.unit_settings import default_unit_file


def _services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DefaultServices:
    sensitive = tmp_path / "sensitive"
    public = tmp_path / "public"
    sensitive.mkdir()
    public.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    services = DefaultServices(tmp_path / "settings.json")
    services.settings = replace(
        services.settings,
        sensitive_root=sensitive,
        sharepoint_root=public,
        lvms_url="https://lvms.test/clims/",
        enabled_units=("flow", "solide"),
        unit_config_paths={key: default_unit_file(key) for key in ("flow", "solide")},
        statistics_lookup_paths={"solide": tmp_path / "missing.xlsx"},
    )
    services.settings.save(services.settings_path)
    services._settings_exist = True

    class SyntheticFetcher:
        def __init__(self, **kwargs):
            pass

        def fetch_statistics(self, keys=None):
            return {key: () for key in keys or ("flow", "solide")}

        def fetch_backlog(self):
            raise AssertionError("No external fetch is allowed in this test")

    monkeypatch.setattr("molstat.services.UnifiedLvmsFetcher", SyntheticFetcher)
    monkeypatch.setattr(
        "molstat.system.MolStatSystem._process_statistics",
        lambda self, key, reports: {"rows": 2, "units": 1},
    )
    return services


def test_invalid_lookup_preserves_gui_and_healthy_unit_runner(tmp_path, monkeypatch):
    services = _services(tmp_path, monkeypatch)

    orchestrator, error = services.refresh_gui_runtime()

    assert error is None
    assert orchestrator is not None
    assert services.unit_status_fields()["flow"][0] == "Klar"
    assert services.unit_status_fields()["solide"][0] == "Oppsett må rettes"
    result = orchestrator.run("flow", "manual")
    assert result.status == "succeeded"
    assert [(item.unit_key, item.job_kind, item.status) for item in result.capability_results] == [
        ("flow", "statistics", "succeeded")
    ]


def test_composite_run_reports_bad_lookup_only_for_affected_unit(tmp_path, monkeypatch):
    services = _services(tmp_path, monkeypatch)
    orchestrator, _ = services.refresh_gui_runtime()

    result = orchestrator.run("statistics", "manual")

    assert result.status == "partial"
    assert [(item.unit_key, item.status) for item in result.capability_results] == [
        ("flow", "succeeded"), ("solide", "failed")
    ]
    assert result.capability_results[1].error_code == "LOOKUP_INVALID"
    assert "missing.xlsx" not in result.capability_results[1].message


def test_invalid_unit_json_is_reported_without_blocking_other_units(tmp_path, monkeypatch):
    services = _services(tmp_path, monkeypatch)
    invalid = tmp_path / "solide.json"
    invalid.write_text('{"schema_version":1,', encoding="utf-8")
    services.settings = replace(
        services.settings,
        unit_config_paths={**services.settings.unit_config_paths, "solide": invalid},
    )

    orchestrator, error = services.refresh_gui_runtime()
    result = orchestrator.run("all", "manual")

    assert error is None
    assert result.status == "partial"
    assert result.capability_results[0].unit_key == "flow"
    assert result.capability_results[0].status == "succeeded"
    assert result.capability_results[1].unit_key == "solide"
    assert result.capability_results[1].error_code == "CONFIG_INVALID"


def test_local_processing_runtime_does_not_require_lvms(tmp_path, monkeypatch):
    services = _services(tmp_path, monkeypatch)
    services.settings = replace(services.settings, lvms_url="")
    monkeypatch.setattr(
        services, "_ensure_lvms_config",
        lambda path: (_ for _ in ()).throw(AssertionError("LVMS must not be initialized")),
    )

    system = services._build_system(
        require_statistics=True, unit_keys=("flow",), require_lvms=False
    )

    assert tuple(unit.key for unit in system.units) == ("flow",)
    assert tuple(system.statistics_processors) == ("flow",)
    assert system.capability_errors == {}


def test_last_capability_results_are_persisted_and_are_safe_after_restart(tmp_path):
    database = MolStatDatabase(tmp_path / "database.sqlite3")
    database.migrate()
    orchestrator = MolStatOrchestrator(
        database,
        {"all": lambda: (
            CapabilityRun("hemato", "statistics", {}, RuntimeError("SECRET-42")),
            CapabilityRun("hemato", "backlog", {"rows": 3, "path": "K:/SECRET.csv"}),
            CapabilityRun("solide", "statistics", {"rows": 4}),
        )},
        owner="synthetic-pc",
    )

    result = orchestrator.run("all", "manual")
    restarted = MolStatOrchestrator(database, {}, owner="synthetic-pc")
    statuses = restarted.capability_statuses()

    assert statuses == result.capability_results
    assert [(item.unit_key, item.job_kind, item.status) for item in statuses] == [
        ("hemato", "statistics", "failed"),
        ("hemato", "backlog", "succeeded"),
        ("solide", "statistics", "succeeded"),
    ]
    with database._connect() as connection:
        stored = connection.execute("SELECT summary FROM job_run").fetchone()[0]
    assert "SECRET" not in stored
    assert "K:/" not in stored
    assert json.loads(stored)["capability_results"][1]["summary"] == {"rows": 3}

    MolStatOrchestrator(database, {"hemato": lambda: (
        CapabilityRun("hemato", "statistics", {"rows": 5}),
    )}, owner="synthetic-pc").run("hemato", "manual")
    latest = {(item.unit_key, item.job_kind): item for item in restarted.capability_statuses()}
    assert latest[("hemato", "statistics")].status == "succeeded"
    assert latest[("hemato", "backlog")].summary == {"rows": 3}
    assert latest[("solide", "statistics")].summary == {"rows": 4}


def test_manual_service_holds_lease_and_never_initializes_lvms(tmp_path, monkeypatch):
    from molstat.manual_import import ManualImportPlan

    services = _services(tmp_path, monkeypatch)
    services.settings = replace(services.settings, lvms_url="")
    monkeypatch.setattr(services, "_ensure_lvms_config", lambda _: pytest.fail("No LVMS initialization"))
    files = {role: tmp_path / f"{role}.csv" for role in ("antall", "resultater")}
    for path in files.values():
        path.write_text("synthetic data", encoding="utf-8")
    plan = ManualImportPlan("flow", "statistics", date.today(), date.today(), files)

    def process(system, selected_plan, definition):
        assert selected_plan is plan
        assert definition.key == "flow"
        assert tuple(unit.key for unit in system.units) == ("flow",)
        with pytest.raises(WriterLeaseBusy):
            with system.database.writer_lease("other-pc", timedelta(minutes=5)):
                pytest.fail("The manual import must already hold the writer lease")
        return (CapabilityRun("flow", "statistics", {"rows": 3}),)

    monkeypatch.setattr("molstat.manual_import.process_manual_import", process)

    result = services.manual_import(plan)

    assert result.status == "succeeded"
    assert result.capability_results[0].unit_key == "flow"
    assert services.manual_import_available_jobs("flow") == ("statistics",)
    assert services.manual_import_roles("flow", "statistics") == ("antall", "resultater")
    with services._database()._connect() as connection:
        assert connection.execute("SELECT trigger FROM job_run").fetchone()[0] == "manual_import"


def test_manual_service_reports_invalid_lookup_for_selected_unit(tmp_path, monkeypatch):
    from molstat.manual_import import ManualImportPlan

    services = _services(tmp_path, monkeypatch)
    files = {role: tmp_path / f"{role}.csv" for role in ("antall", "resultater", "ekstraksjon")}
    for path in files.values():
        path.write_text("synthetic data", encoding="utf-8")
    plan = ManualImportPlan("solide", "statistics", date.today(), date.today(), files)

    result = services.manual_import(plan)

    assert result.status == "failed"
    assert result.capability_results[0].unit_key == "solide"
    assert result.capability_results[0].error_code == "LOOKUP_INVALID"
    assert services.unit_status_fields()["solide"][0] == "Oppsett må rettes"
    assert not (services.settings.sensitive_root / "raw").exists()


def test_corrupt_saved_settings_open_recoverable_configuration_without_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    path = tmp_path / "settings.json"
    original = '{"schema_version":2,invalid}'
    path.write_text(original, encoding="utf-8")

    services = DefaultServices(path)
    orchestrator, error = services.refresh_gui_runtime()

    assert orchestrator is None
    assert "Innstillingsfilen" in error
    assert path.read_text(encoding="utf-8") == original
    assert services.load_settings_fields()["sensitive_root"] == ""
    assert not (tmp_path / "data").exists()


def test_backlog_only_build_does_not_clear_statistics_configuration_error(tmp_path, monkeypatch):
    services = _services(tmp_path, monkeypatch)
    services.settings = replace(services.settings, enabled_units=("hemato",),
                                unit_config_paths={"hemato": default_unit_file("hemato")},
                                statistics_lookup_paths={})
    services.refresh_gui_runtime()
    assert services.unit_status_fields()["hemato"][0] == "Delvis klar"

    services._build_system(require_statistics=False)

    assert services.unit_status_fields()["hemato"][0] == "Delvis klar"


def test_retry_publication_continues_for_healthy_unit_after_invalid_configuration(tmp_path, monkeypatch):
    import csv
    from molstat.delivery import deliver
    from molstat.modules import configured_registry
    from molstat.publisher import PublicationPolicy, SharePointPublisher, default_forbidden_patterns
    from molstat.unit_settings import load_unit_file

    services = _services(tmp_path, monkeypatch)
    invalid = tmp_path / "solide.json"
    invalid.write_text("invalid", encoding="utf-8")
    services.settings = replace(services.settings, enabled_units=("solide", "flow"),
                                unit_config_paths={"solide": invalid, "flow": default_unit_file("flow")})
    definition = load_unit_file(default_unit_file("flow"))
    capability = configured_registry({"flow": definition}).require("flow").capability("statistics")
    publisher = SharePointPublisher(PublicationPolicy(capability.allowed_columns, default_forbidden_patterns()))
    candidate = services.settings.sensitive_root / "processed/flow/statistics/synthetic-run"
    candidate.mkdir(parents=True)
    files = {}
    for name, columns in capability.publication_files:
        path = candidate / name
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(sorted(columns))
            writer.writerow(["1" for _ in columns])
        files[name] = path
    original = publisher.publish
    monkeypatch.setattr(publisher, "publish", lambda *args: (_ for _ in ()).throw(PermissionError("locked")))
    with pytest.raises(PermissionError):
        deliver(publisher, files, services.settings.sharepoint_root / "flow", candidate)
    monkeypatch.setattr(publisher, "publish", original)
    before = {name: path.read_bytes() for name, path in files.items()}

    runs = services.retry_publication()

    assert [(run.unit_key, run.error is None) for run in runs] == [("solide", False), ("flow", True)]
    assert runs[1].summary == {"published": 1}
    assert all((services.settings.sharepoint_root / "flow" / name).read_bytes() == content
               for name, content in before.items())
    assert json.loads((candidate / "delivery.json").read_text(encoding="utf-8"))["status"] == "published"
    again = services.retry_publication()
    assert again[1].summary == {"published": 0}


def test_publication_maintenance_does_not_replace_latest_source_status(tmp_path):
    database = MolStatDatabase(tmp_path / "database.sqlite3")
    database.migrate()
    initial = MolStatOrchestrator(database, {"flow": lambda: (
        CapabilityRun("flow", "statistics", {}, RuntimeError("source failure")),
    )}, owner="pc").run("flow", "manual")
    orchestrator = MolStatOrchestrator(database, {"publish": lambda: (
        CapabilityRun("flow", "statistics", {"published": 1}),
    )}, owner="pc")

    result = orchestrator.run("publish", "manual")

    assert result.capability_results[0].status == "succeeded"
    assert orchestrator.capability_statuses() == initial.capability_results


def test_lvms_setup_error_keeps_manual_processing_available(tmp_path, monkeypatch):
    services = _services(tmp_path, monkeypatch)
    services.settings = replace(services.settings, enabled_units=("flow",), lvms_url="")

    orchestrator, error = services.refresh_gui_runtime()

    assert error is None
    assert orchestrator is not None
    assert services.unit_status_fields()["flow"][0] == "Manuell import tilgjengelig"
    assert services.overview_status_fields()["lvms"][0] == "Oppsett må rettes"
    assert services.manual_import_available_jobs("flow") == ("statistics",)
    assert services.unit_definitions().require("flow").display_name == "FLOW"


def test_corrupt_settings_cannot_create_database_through_scheduling(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "settings.json"
    path.write_text("broken", encoding="utf-8")
    services = DefaultServices(path)

    assert services.auto() == 2
    with pytest.raises(ValueError, match="Innstillingsfilen"):
        services._database()

    assert not (tmp_path / "data").exists()


def test_unconfigured_disabled_unit_can_be_enabled_using_bundled_definition(tmp_path, monkeypatch):
    sensitive, public = tmp_path / "sensitive", tmp_path / "public"
    sensitive.mkdir()
    public.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    services = DefaultServices(tmp_path / "settings.json")
    services.save_settings_fields({
        "sensitive_root": str(sensitive), "sharepoint_root": str(public),
        "lvms_url": "https://lvms.test/clims/", "enabled_hemato": "false",
        "enabled_solide": "false", "enabled_lege": "true",
    })
    fields = services.load_settings_fields()
    assert fields.get("config_flow", "") == ""
    fields["enabled_flow"] = "true"

    services.save_settings_fields(fields)

    assert set(services.settings.enabled_units) == {"flow", "lege"}
    assert services.settings.unit_config_paths["flow"].is_file()
