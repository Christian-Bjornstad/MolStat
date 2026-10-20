from unit_fixtures import analysis_codes
import csv
from datetime import date
from pathlib import Path

from molstat._statistics import patolog_flow as flow
from molstat.fetching import UnifiedLvmsFetcher
from molstat.lvms.report_job import validate_report_job, load_report_jobs, batch_filename
from molstat.unit_settings import load_unit_file
from unit_fixtures import default_unit_file


def export(path, arrival="01.09.2026 08:00", approved="", sample="T1"):
    row = dict.fromkeys(flow.DATE_FIELDS + ["Prøvenummer", "Lab", "Prosess", "Prioritet", "BeholderId",
        "BlokkId", "GlassId", "Glasstype", "Signert av", "Godkjent type"], "")
    row.update(Prøvenummer=sample, Lab="OU-PAT-HIST-RA", Prosess="HEMATO", Ankomsttid=arrival)
    row["Godkjent dato"] = approved
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="cp1252", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row), delimiter=";")
        writer.writeheader()
        writer.writerow(row)


def test_workflow_job_requires_scoped_lab_and_processes():
    import pytest
    raw = dict(job_key="workflow", report_type="PRODSTAT", category="PATOLOGI",
        report_id="PAT-TID-STØP-SNITT-OU", analysis_codes=[], created_from="01.09.2026",
        created_to="30.09.2026", output_stem="PAT-TID-STOP-SNITT-OU",
        laboratory="OU-PAT-HIST-RA", process_codes=["HEMATO", "HEMATO BENMARG"])
    job = validate_report_job(raw)
    assert job.laboratory == "OU-PAT-HIST-RA"
    assert job.process_codes == ("HEMATO", "HEMATO BENMARG")
    with pytest.raises(ValueError):
        validate_report_job(raw | {"process_codes": []})


def test_monthly_flow_fetch_and_refresh_open_history(tmp_path):
    import json
    definition = load_unit_file(default_unit_file("lege"))
    unit = definition.unit
    report = unit.report_by_key("workflow")
    calls = []
    def runner(config, jobs_path, keys, **kwargs):
        job, = load_report_jobs(jobs_path)
        calls.append(job)
        export(kwargs["repository_root"] / "rådata" / batch_filename(job),
               arrival=job.interval.created_from.strftime("%d.%m.%Y 08:00"),
               sample=job.interval.created_from.isoformat())
        return 0
    fetcher = UnifiedLvmsFetcher(lvms_config_path=tmp_path / "lvms.json", sensitive_root=tmp_path,
        work_root=tmp_path / "work", units_path=tmp_path / "units.json", backlog_report_path=tmp_path / "backlog.json",
        run_batch=runner, today=lambda: date(2026, 10, 18), history_from=date(2026, 8, 1))
    fetcher._backfill_flow_months(unit, date(2026, 10, 18))
    assert [(j.interval.created_from, j.interval.created_to) for j in calls] == [
        (date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 9, 1), date(2026, 9, 30))]
    assert all(j.laboratory == "OU-PAT-HIST-RA" and j.process_codes for j in calls)
    calls.clear()
    fetcher._backfill_flow_months(unit, date(2026, 10, 18))
    assert len(calls) == 2  # Both months still have open samples.


def test_archive_uses_latest_complete_month_snapshot_without_double_count(tmp_path):
    export(tmp_path / "PAT-TID-STOP-SNITT-OU__2026-09-01__2026-09-30.csv")
    export(tmp_path / "PAT-TID-STOP-SNITT-OU__2026-09-01__2026-09-30__r2.csv",
           approved="03.09.2026 08:00")
    data = flow.read_archive(tmp_path, as_of=__import__('datetime').datetime(2026, 10, 18))
    assert data["audit"]["samples"] == 1
    assert data["audit"]["open_samples"] == 0
    assert data["Prøver"][0]["Godkjent"] == 1


def test_month_export_cannot_silently_include_other_month(tmp_path):
    import pytest
    path = tmp_path / "month.csv"
    export(path, arrival="01.10.2026 00:00")
    with pytest.raises(ValueError, match="periode"):
        flow.validate_month(path, date(2026, 9, 1), date(2026, 9, 30))


def test_empty_glass_and_signers_write_refreshable_headers(tmp_path):
    source = tmp_path / "source.csv"
    export(source)
    data = flow.add_dimensions(flow.process_rows(flow.read_source(source)))
    flow.write_data(tmp_path / "out", data)
    for name in ("Glass", "Signeringer", "Leger"):
        with (tmp_path / "out" / (name + ".csv")).open(encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream, delimiter=";")
            assert reader.fieldnames == flow.TABLE_FIELDS[name]
            assert list(reader) == []


def test_complete_fetch_path_includes_current_workflow_month(tmp_path):
    definition = load_unit_file(default_unit_file("lege"))
    jobs = []
    def runner(config, jobs_path, keys, **kwargs):
        job, = load_report_jobs(jobs_path)
        jobs.append(job)
        path = kwargs["repository_root"] / "rådata" / batch_filename(job)
        if job.job_key == "workflow":
            export(path, arrival=job.interval.created_from.strftime("%d.%m.%Y 08:00"))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Profil;Lab;s_w_labprocess;Distinct_SampleId;Distinct_Ant. blokker;Distinct_Ant. glass\n", encoding="cp1252")
        return 0
    fetcher = UnifiedLvmsFetcher(lvms_config_path=tmp_path / "lvms.json", sensitive_root=tmp_path,
        work_root=tmp_path / "work", units=(definition.unit,),
        run_batch=runner, today=lambda: date(2026, 10, 18), history_from=date(2026, 10, 1))
    result = fetcher.fetch_statistics(("lege",))["lege"]
    workflow, = [request for request, _ in result if request.report_name == flow.STEM]
    assert (workflow.date_from, workflow.date_to) == (date(2026, 10, 1), date(2026, 10, 18))
    assert len(result) == 1
    assert {job.job_key for job in jobs} == {"workflow"}


def test_closed_month_is_cached_but_periodically_refreshed(tmp_path):
    from datetime import timedelta
    path = tmp_path / "closed.csv"
    export(path, approved="03.09.2026 08:00")
    assert not flow.needs_refresh(path, date(2026, 9, 1), date(2026, 9, 30), date.today())
    assert flow.needs_refresh(path, date(2026, 9, 1), date(2026, 9, 30), date.today() + timedelta(days=31))


def test_processor_produces_all_seven_sharepoint_and_local_powerbi_tables(tmp_path):
    from datetime import datetime
    from molstat.statistics import StatisticsProcessor
    sources = []
    for role in ("CURRENT", "PREVIOUS"):
        path = tmp_path / f"PAT-PROSESS-{role}-OU__2026-09-01__2026-09-30.csv"
        path.write_text("Profil;Lab;s_w_labprocess;Distinct_SampleId;Distinct_Ant. blokker;Distinct_Ant. glass\n", encoding="cp1252")
        sources.append(path)
    source = tmp_path / "PAT-TID-STOP-SNITT-OU__2026-09-01__2026-09-30.csv"
    export(source)
    result = StatisticsProcessor(analysis_codes=analysis_codes("lege"), profile="lege", now=lambda: datetime(2026, 10, 18)).process(
        "lege", [source], tmp_path / "out")
    assert set(result.private_files) == {name + ".csv" for name in ("Prøver", "Glass", "Signeringer", "Grupper", "Periode", "Leger", "Prioriteter")}
    assert result.row_counts["forlop_prover"] == 1
    assert result.publication_files == result.private_files
    assert all(path.parent == tmp_path / "out" for path in result.publication_files.values())
    assert not (tmp_path / "out" / "prosess.csv").exists()


def test_existing_config_switches_to_only_workflow(tmp_path):
    import json
    raw = json.loads(default_unit_file("lege").read_text("utf-8"))
    raw["statistics"]["current"] = {"job_key": "current", "fetch_report_id": "PAT-ANTALL REGISTRERTE PRØVER PROSESS-OU", "report_id": "PAT-PROSESS-CURRENT-OU", "analysis_codes": []}
    path = tmp_path / "lege.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    import pytest
    with pytest.raises(ValueError, match="statistics"):
        load_unit_file(path)


def test_pathology_file_lock_is_reported_without_secondary_lease_loss(tmp_path, monkeypatch):
    import os
    from datetime import datetime, timedelta, timezone
    from pathlib import Path
    from molstat.archive import RawArchive
    from molstat.database import MolStatDatabase
    from molstat.modules import DEFAULT_UNITS, UnitRegistry
    from molstat.orchestrator import MolStatOrchestrator
    from molstat.publisher import SharePointPublisher, PublicationPolicy
    from molstat.statistics import StatisticsProcessor
    from molstat.system import MolStatSystem
    from molstat.lvms.report import ReportRequest
    import molstat.private_delivery as private

    clock = [datetime(2026, 10, 19, 8, 0, tzinfo=timezone.utc)]
    sensitive = tmp_path / 'sensitive'
    database = MolStatDatabase(sensitive / 'data/molstat.sqlite3', now=lambda: clock[0])
    database.migrate()
    source = tmp_path / 'download.csv'
    export(source)
    request = ReportRequest('statistics', 'lege', flow.STEM, date(2026, 9, 1), date(2026, 9, 30))
    def fetch(keys):
        clock[0] += timedelta(minutes=2)
        return {'lege': ((request, source),)}
    target = sensitive / 'processed/lege/powerbi'
    target.mkdir(parents=True)
    (target / 'Glass.csv').write_text('old glass data', encoding='utf-8')
    original_replace = os.replace
    def lock_glass(src, dest):
        if Path(dest) == target / 'Glass.csv':
            raise PermissionError('synthetic file lock')
        return original_replace(src, dest)
    monkeypatch.setattr(private.os, 'replace', lock_glass)
    original_retry = private._replace
    monkeypatch.setattr(private, '_replace', lambda src, dest, sleep: original_retry(src, dest, lambda _: None))
    unit = DEFAULT_UNITS.require('lege')
    system = MolStatSystem(database=database, archive=RawArchive(sensitive),
        statistics_processors={'lege': StatisticsProcessor(analysis_codes=analysis_codes('lege'), profile='lege')},
        backlog_processor=None, publisher=SharePointPublisher(PublicationPolicy(unit.capability('statistics').allowed_columns, ())),
        sharepoint_root=tmp_path / 'public', work_root=sensitive / 'processed',
        statistics_fetch=fetch, backlog_fetch=lambda: None, units=UnitRegistry((unit,)))
    result = MolStatOrchestrator(database, {'lege': lambda: system.run_unit('lege')},
        owner='synthetic-pc', lease_ttl=timedelta(seconds=30)).run('lege', 'manual')
    assert result.status == 'failed'
    assert result.capability_results[0].error_code == 'PRIVATE_FILES_LOCKED'
    assert (target / 'Glass.csv').read_text('utf-8') == 'old glass data'
    assert not (target / 'Prøver.csv').exists()
    assert database.current_lease_owner() is None
    assert database.job_statuses() == (('lege', 'failed'),)
