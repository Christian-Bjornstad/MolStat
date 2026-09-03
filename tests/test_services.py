from pathlib import Path

import pytest

from molstat.services import DefaultServices


def test_first_launch_opens_with_empty_settings(tmp_path: Path) -> None:
    services = DefaultServices(tmp_path / "settings.json")

    assert services.load_settings_fields() == {
        "sensitive_root": "",
        "sharepoint_root": "",
        "lvms_url": "",
        "lookup_hemato": "",
        "lookup_solide": "",
    }


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

    orchestrator, board, error = services.refresh_gui_runtime()

    assert orchestrator is None
    assert board is None
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
