from pathlib import Path

import pytest

from molstat.services import DefaultServices
from molstat.unit_settings import UnitConfigError


def test_diagnostics_use_redirected_local_app_data(tmp_path, monkeypatch):
    local = tmp_path / "redirected-profile" / "Local Data"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    services = DefaultServices(tmp_path / "settings.json")

    services._record_job_failure("hemato_backlog_run_failed", RuntimeError("PRIVATE-PAYLOAD"))

    directory = local / "MolStat" / "logs"
    assert services.diagnostic_log_directory() == directory
    assert "hemato_backlog_run_failed: RuntimeError" in (directory / "runtime.log").read_text("utf-8")


@pytest.mark.parametrize("record", ["_record_failure", "_record_job_failure"])
def test_unavailable_profile_falls_back_to_temporary_logs(tmp_path, monkeypatch, record):
    import tempfile

    blocked = tmp_path / "blocked-profile"
    blocked.write_text("synthetic blocker", encoding="utf-8")
    temporary = tmp_path / "local-temporary"
    monkeypatch.setenv("LOCALAPPDATA", str(blocked))
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(temporary))
    services = DefaultServices(tmp_path / "settings.json")

    try:
        raise RuntimeError("PRIVATE-PAYLOAD")
    except RuntimeError as error:
        getattr(services, record)("hemato_backlog_run_failed", error)

    directory = temporary / "MolStat" / "logs"
    assert services.diagnostic_log_directory() == directory
    assert services.diagnostic_messages() == ("hemato_backlog_run_failed: RuntimeError",)
    filename = "bootstrap.log" if record == "_record_failure" else "runtime.log"
    text = (directory / filename).read_text("utf-8")
    assert "hemato_backlog_run_failed: RuntimeError" in text
    assert "PRIVATE-PAYLOAD" not in text
    assert "test_unavailable_profile_falls_back_to_temporary_logs" in text


def test_total_logging_failure_preserves_diagnostics_and_original_runtime_result(tmp_path, monkeypatch):
    import tempfile

    blocked = tmp_path / "blocked"
    blocked.write_text("synthetic blocker", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(blocked))
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(blocked))
    services = DefaultServices(tmp_path / "settings.json")
    monkeypatch.setattr(services, "_build_system", lambda **kwargs: (_ for _ in ()).throw(ValueError("PRIVATE-PAYLOAD")))

    orchestrator, error = services.refresh_gui_runtime()
    services._record_job_failure("hemato_backlog_run_failed", RuntimeError("PRIVATE-PAYLOAD"))

    assert orchestrator is None
    assert error.startswith("ValueError:")
    assert services.diagnostic_messages() == (
        "gui_configuration_failed: ValueError",
        "hemato_backlog_run_failed: RuntimeError",
    )
    assert services.diagnostic_log_directory() is None


def test_bootstrap_log_omits_external_exception_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    services = DefaultServices(tmp_path / "settings.json")

    services._record_failure("gui_configuration_failed", ValueError("PRIVATE-PAYLOAD"))

    directory = services.diagnostic_log_directory()
    text = (directory / "bootstrap.log").read_text("utf-8")
    assert "gui_configuration_failed: ValueError" in text
    assert "PRIVATE-PAYLOAD" not in text


def test_invalid_unicode_in_configuration_diagnostic_does_not_mask_original_error(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    services = DefaultServices(tmp_path / "settings.json")
    error = UnitConfigError("CONFIG_INVALID: ukjent JSON-felt " + chr(0xD800))

    services._record_job_failure("hemato_configuration_failed", error)

    assert services.diagnostic_messages() == (f"hemato_configuration_failed: {error}",)
    directory = services.diagnostic_log_directory()
    contents = (directory / "runtime.log").read_text("utf-8")
    assert "hemato_configuration_failed: CONFIG_INVALID" in contents
    assert "\\ud800" in contents
