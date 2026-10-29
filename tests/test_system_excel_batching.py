import pytest

from molstat.modules import DEFAULT_UNITS, UnitRegistry
from molstat.progress import progress_context
from molstat.system import MolStatSystem


def batch_system():
    system = MolStatSystem.__new__(MolStatSystem)
    system.units = UnitRegistry((DEFAULT_UNITS.require("hemato"), DEFAULT_UNITS.require("solide")))
    system.excel_status = None
    system.refreshes = []

    def refresh():
        system.refreshes.append("refreshed")
        return True

    system._refresh_excel_search = refresh

    def run(unit, kind):
        return {"rows": 3, "excel_published": system._refresh_capability_excel(unit, kind)}

    system._run_capability = run
    return system


@pytest.mark.parametrize("target,expected_capabilities", [("all", 4), ("statistics", 2), ("unit", 2)])
def test_composite_rebuilds_excel_once_with_final_data(target, expected_capabilities):
    system = batch_system()
    events = []
    with progress_context(events.append):
        if target == "all":
            results = system.run_all(("hemato", "solide"))
        elif target == "unit":
            results = system.run_unit("hemato")
        else:
            results = system.run_job("statistics", ("hemato", "solide"))
    assert len(results) == expected_capabilities
    assert system.refreshes == ["refreshed"]
    assert all(item.summary["excel_published"] for item in results)
    assert any(event.stage == "excel" for event in events)


def test_partial_failure_still_refreshes_once_for_completed_imports():
    system = batch_system()
    run = system._run_capability

    def partial(unit, kind):
        if unit == "solide":
            raise ValueError("synthetic")
        return run(unit, kind)

    system._run_capability = partial
    results = system.run_all(("hemato", "solide"))
    assert system.refreshes == ["refreshed"]
    assert [item.error is None for item in results] == [True, True, False, False]
    assert results[0].summary["excel_published"] is True


def test_all_failed_before_refresh_request_does_not_build_excel():
    system = batch_system()
    system._run_capability = lambda *args: (_ for _ in ()).throw(ValueError("synthetic"))
    results = system.run_all(("hemato", "solide"))
    assert all(item.error for item in results)
    assert system.refreshes == []


def test_direct_capability_still_refreshes_immediately():
    system = batch_system()
    result = system._run_capability("hemato", "statistics")
    assert result["excel_published"] is True
    assert system.refreshes == ["refreshed"]


def test_cancellation_does_not_start_final_workbook_and_resets_batch_state():
    from molstat.failures import RunFailure

    system = batch_system()
    run = system._run_capability

    def stopped(unit, kind):
        if kind == "backlog":
            raise RunFailure("CANCELLED", "job_run")
        return run(unit, kind)

    system._run_capability = stopped
    with pytest.raises(RunFailure, match="CANCELLED"):
        system.run_all(("hemato", "solide"))
    assert system.refreshes == []
    system._run_capability = run
    assert run("hemato", "statistics")["excel_published"] is True


def test_failed_final_excel_does_not_claim_publication_succeeded():
    system = batch_system()
    system._refresh_excel_search = lambda: False
    results = system.run_all(("hemato", "solide"))
    assert all(item.error is None for item in results)
    assert all(item.summary["excel_published"] is False for item in results)


def test_real_unit_pipeline_workbook_contains_statistics_and_later_backlog(tmp_path, monkeypatch):
    from datetime import date, datetime
    from types import SimpleNamespace
    from molstat.archive import RawArchive
    from molstat.database import MolStatDatabase
    from molstat.lvms.report import ReportRequest
    from molstat.publisher import PublicationPolicy, SharePointPublisher, default_forbidden_patterns
    from molstat.registry import OccurrenceInput, SampleRegistry
    from molstat.statistics import StatisticsProcessor
    import molstat.system as system_module
    from test_statistics_performance import reports

    sensitive = tmp_path / "sensitive"
    database = MolStatDatabase(sensitive / "database/molstat.sqlite3")
    database.migrate()
    sources = reports(tmp_path / "downloads", "2026-09-01", "2026-09-03", ["STATISTICS"])
    fetched = tuple((ReportRequest("statistics", "hemato", path.name.partition("__")[0],
                                   date(2026, 9, 1), date(2026, 9, 3)), path) for path in sources)
    backlog = tmp_path / "backlog.csv"
    backlog.write_text("synthetic", encoding="utf-8")

    class Backlog:
        def import_snapshot(self, *args, **kwargs):
            SampleRegistry(database).register_occurrence(OccurrenceInput(
                "LVMS", "BACKLOG", "CALR-OU", datetime(2026, 9, 3), "backlog"),
                observed_at=datetime(2026, 9, 3))
            return SimpleNamespace(rows_read=1, invalid_rows=0, excluded_rows=0)

    published = []
    original = system_module.publish_search_workbook

    def publish(snapshot, destination):
        published.append({row.sample_number for row in snapshot.samples})
        return original(snapshot, destination)

    monkeypatch.setattr(system_module, "publish_search_workbook", publish)
    capability = DEFAULT_UNITS.require("hemato").capability("statistics")
    system = MolStatSystem(database=database, archive=RawArchive(sensitive),
        statistics_processors={"hemato": StatisticsProcessor(analysis_codes={"CALR-OU"}, database=database)},
        backlog_processor=Backlog(), publisher=SharePointPublisher(PublicationPolicy(
            capability.allowed_columns, default_forbidden_patterns())),
        sharepoint_root=tmp_path / "sharepoint", work_root=sensitive / "data/processed",
        statistics_fetch=lambda keys: {"hemato": fetched},
        backlog_fetch=lambda: (ReportRequest("backlog", "hemato", "BACKLOG", date(2024, 1, 1), date(2026, 9, 3)), backlog),
        excel_search_path=sensitive / "Prøvesøk.xlsx")

    results = system.run_unit("hemato")
    assert all(item.error is None for item in results)
    assert published == [{"STATISTICS", "BACKLOG"}]
    assert system.excel_status.status == "published"
    assert (tmp_path / "sharepoint/hemato/antall.csv").is_file()
