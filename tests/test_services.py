import json
from pathlib import Path
import sqlite3

import pytest

from molstat._backlog.export import BACKLOG_PUBLIC_COLUMNS
from molstat.services import DefaultServices, _unavailable_path_messages
from molstat._statistics.specialized_lookup import default_lookup_path
from molstat._statistics.lege_lookup import default_lege_lookup_path


def test_first_launch_opens_with_empty_settings(tmp_path: Path) -> None:
    services = DefaultServices(tmp_path / "settings.json")

    assert services.load_settings_fields() == {
        "sensitive_root": "",
        "sharepoint_root": "",
        "lvms_url": "",
        "lookup_hemato": "",
        "lookup_solide": "",
        "lookup_flow": str(default_lookup_path("flow")),
        "lookup_fish": str(default_lookup_path("fish")),
        "lookup_pre": str(default_lookup_path("pre")),
        "lookup_lege": str(default_lege_lookup_path()),
        "enabled_hemato": "true",
        "enabled_solide": "true",
        "enabled_flow": "false",
        "enabled_fish": "false",
        "enabled_pre": "false",
        "enabled_lege": "false",
    }


def test_second_pc_opens_current_shared_database_without_migrating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A current shared database must be read-only during app startup."""

    sensitive = tmp_path / "shared-sensitive"
    database_path = sensitive / "data" / "molstat.sqlite3"
    database_path.parent.mkdir(parents=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE schema_info(version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_info VALUES (7)")

    services = DefaultServices(tmp_path / "pc-b-settings.json")
    services.settings = services.settings.__class__(sensitive_root=sensitive)
    migrate_calls: list[Path] = []
    monkeypatch.setattr(
        "molstat.services.MolStatDatabase.migrate",
        lambda database: migrate_calls.append(database.path),
    )

    database = services._database()

    assert database.path == database_path
    assert migrate_calls == []
    assert not (sensitive / "data" / "backups").exists()


def test_refresh_gui_runtime_reports_and_logs_configuration_failure(
    tmp_path: Path, monkeypatch
) -> None:
    local_app_data = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    services = DefaultServices(tmp_path / "settings.json")
    monkeypatch.setattr(
        services,
        "_build_system",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("Lookup-fil mangler.")),
    )

    orchestrator, error = services.refresh_gui_runtime()

    assert orchestrator is None
    assert error == "ValueError: Lookup-fil mangler."
    log = local_app_data / "MolStat" / "logs" / "bootstrap.log"
    assert "gui_configuration_failed" in log.read_text(encoding="utf-8")
    assert "ValueError: Lookup-fil mangler." in log.read_text(encoding="utf-8")


def test_save_settings_rejects_paths_that_do_not_exist(tmp_path: Path) -> None:
    services = DefaultServices(tmp_path / "settings.json")

    with pytest.raises(ValueError, match="K-sensitiv mappe finnes ikke"):
        services.save_settings_fields(
            {
                "sensitive_root": str(tmp_path / "missing"),
                "sharepoint_root": str(tmp_path / "sharepoint"),
                "lvms_url": "https://lvms.example.invalid/clims/",
                "lookup_hemato": str(tmp_path / "hemato.xlsx"),
                "lookup_solide": str(tmp_path / "solide.xlsx"),
            }
        )


def test_save_settings_accepts_existing_production_paths(tmp_path: Path) -> None:
    sensitive = tmp_path / "sensitive"
    sharepoint = tmp_path / "sharepoint"
    sensitive.mkdir()
    sharepoint.mkdir()
    hemato = tmp_path / "hemato.xlsx"
    solide = tmp_path / "solide.xlsx"
    hemato.write_bytes(b"lookup")
    solide.write_bytes(b"lookup")
    services = DefaultServices(tmp_path / "settings.json")

    services.save_settings_fields(
        {
            "sensitive_root": str(sensitive),
            "sharepoint_root": str(sharepoint),
            "lvms_url": "https://lvms.example.invalid/clims/",
            "lookup_hemato": str(hemato),
            "lookup_solide": str(solide),
        }
    )

    assert services.load_settings_fields()["lvms_url"] == (
        "https://lvms.example.invalid/clims/"
    )


def test_save_settings_uses_bundled_patolog_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    sensitive = tmp_path / "sensitive"
    sharepoint = tmp_path / "sharepoint"
    sensitive.mkdir()
    sharepoint.mkdir()
    services = DefaultServices(tmp_path / "settings.json")

    services.save_settings_fields({
        "sensitive_root": str(sensitive),
        "sharepoint_root": str(sharepoint),
        "lvms_url": "https://lvms.test/clims/",
        "enabled_hemato": "false",
        "enabled_solide": "false",
        "enabled_lege": "true",
    })

    assert services.settings.enabled_units == ("lege",)
    lookup = services.settings.statistics_lookup_paths["lege"]
    assert lookup.is_relative_to(sensitive / "config" / "lookups" / "lege")
    assert lookup.read_bytes() == default_lege_lookup_path().read_bytes()
    assert services.load_settings_fields()["lookup_lege"] == str(lookup)
    assert services.settings.unit_config_paths["lege"].is_file()
    assert services._build_system(require_statistics=True).statistics_processors["lege"].profile == "lege"
    assert (local / "MolStat" / "lvms-config.json").is_file()
    assert _unavailable_path_messages(services.settings) == ()


def test_job_failure_diagnostic_omits_exception_text(
    tmp_path: Path, monkeypatch
) -> None:
    local_app_data = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    services = DefaultServices(tmp_path / "settings.json")

    services._record_job_failure(
        "statistics_run_failed", RuntimeError("SECRET-SAMPLE-42")
    )

    assert services.diagnostic_messages() == (
        "statistics_run_failed: RuntimeError",
    )
    log = local_app_data / "MolStat" / "logs" / "runtime.log"
    contents = log.read_text(encoding="utf-8")
    assert "statistics_run_failed: RuntimeError" in contents
    assert "SECRET-SAMPLE-42" not in contents


def test_system_build_wires_exact_backlog_publication_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sensitive = tmp_path / "sensitive"
    sharepoint = tmp_path / "sharepoint"
    sensitive.mkdir()
    sharepoint.mkdir()
    hemato = tmp_path / "hemato.xlsx"
    solide = tmp_path / "solide.xlsx"
    hemato.write_bytes(b"lookup")
    solide.write_bytes(b"lookup")
    services = DefaultServices(tmp_path / "settings.json")
    services.save_settings_fields(
        {
            "sensitive_root": str(sensitive),
            "sharepoint_root": str(sharepoint),
            "lvms_url": "https://lvms.test/clims/",
            "lookup_hemato": str(hemato),
            "lookup_solide": str(solide),
        }
    )

    class FakeFetcher:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def fetch_statistics(self, _unit_keys=None):
            return {}

        def fetch_backlog(self):
            raise AssertionError("unused")

    monkeypatch.setattr("molstat.services.UnifiedLvmsFetcher", FakeFetcher)
    monkeypatch.setattr("molstat.services.load_lookup", lambda _path: {})
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    system = services._build_system(require_statistics=False)

    assert system.backlog_publisher is not None
    assert system.backlog_publisher.policy.allowed_columns == {
        "restansehistorikk_hemato.csv": frozenset(BACKLOG_PUBLIC_COLUMNS)
    }
    assert system.sharepoint_root == sharepoint
    assert system.excel_search_path == sensitive / "Prøvesøk.xlsx"


def test_settings_transfer_imports_unavailable_paths_with_safe_labels(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.json"
    services = DefaultServices(settings_path)
    transfer = tmp_path / "molstat-innstillinger.json"
    payload = services.settings.to_transfer_payload()
    payload["sensitive_root"] = str(tmp_path / "mangler-sensitiv")
    payload["sharepoint_root"] = str(tmp_path / "mangler-sharepoint")
    payload["lvms_url"] = "https://lvms.example.invalid/clims/"
    payload["units"]["hemato"]["statistics_lookup_path"] = str(
        tmp_path / "mangler-hemato.xlsx"
    )
    payload["units"]["solide"]["statistics_lookup_path"] = str(
        tmp_path / "mangler-solide.xlsx"
    )
    transfer.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    warnings = services.import_settings(transfer)

    assert warnings == (
        "K-sensitiv mappe",
        "SharePoint-mappe",
        "Lookup-fil for Hemato",
        "Lookup-fil for Solide",
    )
    assert services.settings.sensitive_root == tmp_path / "mangler-sensitiv"
    assert settings_path.is_file()


def test_settings_transfer_failure_is_atomic(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    services = DefaultServices(settings_path)
    services.settings.save(settings_path)
    services = DefaultServices(settings_path)
    before = settings_path.read_bytes()
    transfer = tmp_path / "ugyldig.json"
    transfer.write_text('{"schema_version":999}', encoding="utf-8")

    with pytest.raises(ValueError):
        services.import_settings(transfer)

    assert settings_path.read_bytes() == before
    assert services.settings.sensitive_root == Path(".")


def test_settings_export_excludes_local_lvms_runtime(tmp_path: Path) -> None:
    services = DefaultServices(tmp_path / "settings.json")
    transfer = tmp_path / "molstat-innstillinger.json"

    services.export_settings(transfer)

    exported = transfer.read_text(encoding="utf-8").casefold()
    assert '"schema_version": 2' in exported
    for forbidden in ("lvms_config_path", "profile_directory", "cdp", "session"):
        assert forbidden not in exported


def test_database_folder_selection_never_creates_nested_replacement(tmp_path):
    from dataclasses import replace
    services = DefaultServices(tmp_path / "settings.json")
    (tmp_path / "molstat.sqlite3").write_bytes(b"synthetic-existing")
    services.settings = replace(services.settings, sensitive_root=tmp_path)
    with pytest.raises(ValueError, match="DB_LOCATION"):
        services._database()
    assert not (tmp_path / "data" / "molstat.sqlite3").exists()


def test_manual_excel_regeneration_works_with_real_workbook_writer(tmp_path):
    from dataclasses import replace
    services = DefaultServices(tmp_path / "settings.json")
    services.settings = replace(services.settings, sensitive_root=tmp_path)
    assert services.regenerate_excel() == {"excel_published": True}
    assert (tmp_path / "Prøvesøk.xlsx").is_file()


@pytest.mark.parametrize("custom_runtime", [False, True])
def test_changed_lvms_url_updates_runtime_without_losing_paths(tmp_path, custom_runtime):
    from dataclasses import replace
    from molstat.lvms.config import load_app_config

    local = tmp_path / "local"
    local.mkdir()
    runtime = local / "custom-runtime.json" if custom_runtime else local / "MolStat" / "lvms-config.json"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "landing_url": "https://old.internal/clims/",
        "profile_directory": str(local / "custom-profile"),
        "download_directory": str(local / "custom-downloads"),
        "operator_note": "preserve custom fields",
    }
    if custom_runtime:
        payload["expected_origin"] = "https://old.internal"
    runtime.write_text(json.dumps(payload), encoding="utf-8")
    services = DefaultServices(tmp_path / "settings.json")
    services.settings = replace(
        services.settings,
        lvms_config_path=runtime if custom_runtime else None,
        lvms_url="https://new.internal:8443/clims/",
    )

    assert services._ensure_lvms_config(local / "MolStat") == runtime

    updated = json.loads(runtime.read_text(encoding="utf-8"))
    expected = {
        **payload,
        "landing_url": "https://new.internal:8443/clims/",
    }
    if custom_runtime:
        expected["expected_origin"] = "https://new.internal:8443"
    assert updated == expected
    validated = load_app_config(
        runtime, repository_root=tmp_path / "repository", allowed_local_root=local
    )
    assert validated.expected_origin == "https://new.internal:8443"


@pytest.mark.parametrize("url", [
    "http://new.internal/clims/",
    "https://name:secret@new.internal/clims/",
    "https://new.internal/clims/?token=secret",
])
def test_invalid_changed_lvms_url_preserves_runtime(tmp_path, url):
    from dataclasses import replace

    runtime = tmp_path / "runtime.json"
    original = json.dumps({
        "landing_url": "https://old.internal/clims/",
        "profile_directory": str(tmp_path / "profile"),
        "download_directory": str(tmp_path / "downloads"),
    })
    runtime.write_text(original, encoding="utf-8")
    services = DefaultServices(tmp_path / "settings.json")
    services.settings = replace(
        services.settings, lvms_config_path=runtime, lvms_url=url
    )

    with pytest.raises(ValueError):
        services._ensure_lvms_config(tmp_path / "MolStat")

    assert runtime.read_text(encoding="utf-8") == original


def test_missing_disabled_lookup_does_not_block_saving_active_unit(tmp_path):
    sensitive = tmp_path / "sensitive"
    sharepoint = tmp_path / "sharepoint"
    sensitive.mkdir()
    sharepoint.mkdir()
    services = DefaultServices(tmp_path / "settings.json")
    missing = tmp_path / "missing-solide.xlsx"

    services.save_settings_fields({
        "sensitive_root": str(sensitive),
        "sharepoint_root": str(sharepoint),
        "lvms_url": "https://lvms.internal/clims/",
        "enabled_hemato": "false",
        "enabled_solide": "false",
        "enabled_lege": "true",
        "lookup_solide": str(missing),
    })

    assert services.settings.enabled_units == ("lege",)
    assert services.settings.statistics_lookup_paths["solide"] == missing
    assert services.settings.statistics_lookup_paths["lege"].is_file()
    assert services.settings_path.is_file()
