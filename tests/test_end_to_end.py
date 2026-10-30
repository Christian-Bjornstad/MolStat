from unit_fixtures import analysis_codes
import csv
import pytest
from typing import Mapping
from datetime import date, datetime
from pathlib import Path
import re

from molstat.archive import RawArchive
from molstat.backlog import (
    AnalysisConfig,
    AppConfig,
    BacklogProcessor,
    CsvContract,
    ThresholdsConfig,
    UnitConfig,
)
from molstat.database import MolStatDatabase
from molstat._backlog.export import BACKLOG_PUBLIC_COLUMNS
from molstat.lvms.report import ReportRequest
from molstat.publisher import PublicationPolicy, SharePointPublisher, default_forbidden_patterns
from molstat.statistics import StatisticsProcessor, StatisticsResult
from molstat.system import MolStatSystem
import molstat.system as system_module
from molstat.modules import DEFAULT_UNITS


def test_statistics_only_system_returns_safe_empty_public_board(tmp_path):
    database = MolStatDatabase(tmp_path / "data.sqlite3")
    system = MolStatSystem(
        database=database, archive=RawArchive(tmp_path), statistics_processors={},
        backlog_processor=None, publisher={}, sharepoint_root=tmp_path / "public",
        work_root=tmp_path / "work", statistics_fetch=lambda _keys: {},
        backlog_fetch=lambda: None,
    )
    now = datetime(2026, 10, 7, 12, 0)
    assert system.public_snapshot(now) == {
        "schemaVersion": 1, "generatedAt": now.isoformat(),
        "unitLabel": "Ingen aktiv restanseenhet", "isStale": True,
        "totals": {"ready": 0, "awaitingApproval": 0, "inTransit": 0, "overdue": 0},
        "emptyAnalysisCount": 0, "analyses": [],
    }
    assert not database.path.exists()


def test_daily_pathology_refresh_publishes_complete_history_and_reports_real_stages(tmp_path):
    from molstat._statistics import patolog_flow as flow
    from molstat.progress import progress_context
    from molstat.modules import UnitRegistry
    sensitive = tmp_path / 'sensitive'
    database = MolStatDatabase(sensitive / 'database/molstat.sqlite3')
    database.migrate()
    archive = RawArchive(sensitive)
    public = tmp_path / 'sharepoint'
    capability = DEFAULT_UNITS.require('lege').capability('statistics')
    publisher = SharePointPublisher(PublicationPolicy(capability.allowed_columns, default_forbidden_patterns()))
    fields = flow.DATE_FIELDS + ['Prøvenummer', 'Lab', 'Prosess', 'Prioritet', 'BeholderId',
                                'BlokkId', 'GlassId', 'Glasstype', 'Signert av', 'Godkjent type']
    def snapshot(name, arrivals):
        path = tmp_path / name
        with path.open('w', encoding='cp1252', newline='') as stream:
            writer = csv.DictWriter(stream, fields, delimiter=';')
            writer.writeheader()
            for sample, arrival, approval in arrivals:
                row = dict.fromkeys(fields, '')
                row.update(Prøvenummer=sample, Lab='TEST', Prosess='HEMATO', Ankomsttid=arrival)
                row['Godkjent dato'] = approval
                writer.writerow(row)
        return path
    old = snapshot('old.csv', [('KEEP','01.10.2026 08:00',''),('UPDATED','19.10.2026 08:00','')])
    archive.store(old, ReportRequest('statistics','lege',flow.STEM,date(2026,10,1),date(2026,10,20)))
    new = snapshot('new.csv', [('UPDATED','19.10.2026 08:00','21.10.2026 08:00'),('NEW','21.10.2026 09:00','')])
    request = ReportRequest('statistics','lege',flow.STEM,date(2026,10,18),date(2026,10,21))
    system = MolStatSystem(database=database, archive=archive,
        statistics_processors={'lege': StatisticsProcessor(analysis_codes=set(), profile='lege', now=lambda: datetime(2026,10,21,12))},
        backlog_processor=None, publisher={'lege': publisher}, sharepoint_root=public, work_root=sensitive / 'data/processed',
        statistics_fetch=lambda keys: {'lege': ((request,new),)}, backlog_fetch=lambda: None,
        units=UnitRegistry((DEFAULT_UNITS.require('lege'),)))
    events = []
    with progress_context(events.append):
        outcome, = system.run_unit('lege')
    assert outcome.error is None
    with (public / 'lege/Prøver.csv').open(encoding='utf-8-sig',newline='') as stream:
        rows = list(csv.DictReader(stream, delimiter=';'))
    assert {r['Prøvenummer']: r['Godkjent'] for r in rows} == {'KEEP':'0','UPDATED':'1','NEW':'0'}
    assert {p.stem for p in (public / 'lege').glob('*.csv')} == set(flow.TABLE_FIELDS)
    assert [e.stage for e in events] == ['planned','started','fetching','processing','publishing','excel','finished']


@pytest.mark.parametrize("fail_publication", [False, True])
def test_pathologist_publishes_seven_tables_and_keeps_local_copies(tmp_path, monkeypatch, fail_publication):
    import json
    from molstat._statistics import patolog_flow as flow
    from molstat.delivery import retry_pending

    sensitive = tmp_path / "sensitive"
    public = tmp_path / "sharepoint"
    database = MolStatDatabase(sensitive / "database/molstat.sqlite3")
    database.migrate()
    download = tmp_path / "download.csv"
    row = dict.fromkeys(flow.DATE_FIELDS + ["Prøvenummer", "Lab", "Prosess", "Prioritet", "BeholderId",
        "BlokkId", "GlassId", "Glasstype", "Signert av", "Godkjent type", "PID"], "")
    row.update(Prøvenummer="SYNTHETIC-1", Lab="TEST", Prosess="HEMATO", Prioritet="Low",
        Ankomsttid="01.09.2026 08:00", GlassId="GLASS-1", Glasstype="VANLIG", PID="SECRET-PATIENT")
    row["Signert av"] = "Lege A"
    row["Godkjent type"] = "Hovedansvarlig"
    with download.open("w", encoding="cp1252", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row), delimiter=";")
        writer.writeheader()
        writer.writerow(row)
    capability = DEFAULT_UNITS.require("lege").capability("statistics")
    publisher = SharePointPublisher(PublicationPolicy(capability.allowed_columns, default_forbidden_patterns()))
    request = ReportRequest("statistics", "lege", flow.STEM, date(2026, 9, 1), date(2026, 9, 30))
    system = MolStatSystem(
        database=database, archive=RawArchive(sensitive),
        statistics_processors={"lege": StatisticsProcessor(analysis_codes=set(), profile="lege",
            now=lambda: datetime(2026, 10, 20))}, backlog_processor=None,
        publisher={"lege": publisher}, sharepoint_root=public,
        work_root=sensitive / "processed",
        statistics_fetch=lambda _keys: {"lege": ((request, download),)}, backlog_fetch=lambda: None,
    )
    original_publish = publisher.publish
    if fail_publication:
        def locked(*args):
            raise PermissionError("synthetic publication lock")
        monkeypatch.setattr(publisher, "publish", locked)
        with pytest.raises(PermissionError):
            system.run_statistics_unit("lege")
        monkeypatch.setattr(publisher, "publish", original_publish)
        assert retry_pending(publisher, sensitive / "processed/lege/statistics", public / "lege") == 1
    else:
        system.run_statistics_unit("lege")

    expected = {"Prøver.csv", "Glass.csv", "Signeringer.csv", "Grupper.csv", "Periode.csv", "Leger.csv", "Prioriteter.csv"}
    assert set(capability.allowed_columns) == expected
    assert {p.name for p in (public / "lege").iterdir()} == expected
    for name in expected:
        target = public / "lege" / name
        assert target.read_bytes() == (sensitive / "processed/lege/powerbi" / name).read_bytes()
        assert "SECRET-PATIENT" not in target.read_text("utf-8-sig")
    manifest, = (sensitive / "processed/lege/statistics").glob("*/delivery.json")
    payload = json.loads(manifest.read_text("utf-8"))
    assert payload["status"] == "published" and set(payload["files"]) == expected
    assert retry_pending(publisher, manifest.parent.parent, public / "lege") == 0
    assert (manifest.parent / "source_audit.json").is_file()
    assert not (public / "lege/source_audit.json").exists()


class SyntheticStatisticsProcessor:
    def process(
        self, unit: str, raw_files: tuple[Path, ...], output_dir: Path
    ) -> StatisticsResult:
        del unit
        assert any("SECRET-STAT-RAW" in path.read_text() for path in raw_files)
        output_dir.mkdir(parents=True, exist_ok=True)
        antall = output_dir / "antall.csv"
        resultater = output_dir / "resultater.csv"
        _write(antall, ["Analyse", "Maaned"], [["CALR-OU", "9"]])
        _write(
            resultater,
            ["Analyse", "Rapportgruppe"],
            [["CALR-OU", "MPN"]],
        )
        return StatisticsResult(
            antall=antall,
            resultater=resultater,
            row_counts={"antall": 1, "resultater": 1},
        )


def _write(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(header)
        writer.writerows(rows)


def test_complete_flow_keeps_identifiers_out_of_public_outputs(tmp_path: Path) -> None:
    sensitive = tmp_path / "k-sensitive"
    sharepoint = tmp_path / "sharepoint"
    database = MolStatDatabase(sensitive / "data" / "molstat.sqlite3")
    database.migrate()
    stats_download = tmp_path / "stat-download.csv"
    stats_download.write_text("SECRET-STAT-RAW", encoding="utf-8")
    backlog_download = tmp_path / "backlog-download.csv"
    backlog_download.write_text(
        "SampleID;Analyse;Tidspunkt analysebestilling;Tidspunkt ankomst;"
        "Status analyse;Analyseresultat\n"
        "SECRET-BACKLOG-42;IGH-OU;30.08.2026 07:00;30.08.2026 08:00;"
        "Initial;\n",
        encoding="cp1252",
    )
    now = datetime(2026, 9, 2, 9, 0)
    backlog = BacklogProcessor(
        AppConfig(
            report_id="PAT-DIT-RESTANSE-OU",
            unit=UnitConfig("hemato", "MolPat hemato"),
            thresholds=ThresholdsConfig(24, 48),
            analyses=(
                AnalysisConfig(
                    "KLONALITET",
                    "Klonalitet",
                    "Molekylær",
                    "standard",
                    source_codes=("IGH-OU",),
                ),
            ),
        ),
        CsvContract(
            delimiter=";",
            encoding="cp1252",
            columns={
                "sample_id": "SampleID",
                "analysis_code": "Analyse",
                "created_at": "Tidspunkt analysebestilling",
                "arrival_at": "Tidspunkt ankomst",
                "status": "Status analyse",
                "result": "Analyseresultat",
            },
            completed_values=("Completed",),
        ),
        now=lambda: now,
    )
    publisher = SharePointPublisher(
        PublicationPolicy(
            allowed_columns={
                "antall.csv": frozenset({"Analyse", "Maaned"}),
                "resultater.csv": frozenset({"Analyse", "Rapportgruppe"}),
            },
            forbidden_patterns=(
                re.compile(r"pasient", re.I),
                re.compile(r"sample[ ._-]*id", re.I),
            ),
        )
    )
    statistics_request = ReportRequest(
        "statistics",
        "hemato",
        "PAT-DIT-ANTALL-OU",
        date(2026, 9, 1),
        date(2026, 9, 2),
    )
    backlog_request = ReportRequest(
        "backlog",
        "hemato",
        "PAT-DIT-RESTANSE-OU",
        date(2026, 8, 30),
        date(2026, 9, 2),
    )
    system = MolStatSystem(
        database=database,
        archive=RawArchive(sensitive),
        statistics_processors={"hemato": SyntheticStatisticsProcessor()},
        backlog_processor=backlog,
        publisher=publisher,
        sharepoint_root=sharepoint,
        work_root=sensitive / "work",
        statistics_fetch=lambda _unit_keys=None: {
            "hemato": ((statistics_request, stats_download),)
        },
        backlog_fetch=lambda: (backlog_request, backlog_download),
    )

    assert system.run_statistics()["rows"] == 2
    assert system.run_backlog()["rows"] == 1
    snapshot = system.public_snapshot(now)

    assert not stats_download.exists()
    assert not backlog_download.exists()
    archived_text = " ".join(
        path.read_text(errors="ignore")
        for path in (sensitive / "data" / "raw").rglob("*.csv")
    )
    assert "SECRET-STAT-RAW" in archived_text
    assert "SECRET-BACKLOG-42" in archived_text
    assert len(list((sensitive / "data" / "raw" / "backlog").rglob("*.csv"))) == 1
    public_text = repr(snapshot) + " ".join(
        path.read_text(encoding="utf-8-sig")
        for path in sharepoint.rglob("*.csv")
    )
    assert "SECRET" not in public_text
    assert "SampleID" not in public_text


def test_second_statistics_run_publishes_complete_deduplicated_history(
    tmp_path: Path, monkeypatch
) -> None:
    sensitive = tmp_path / "k-sensitive"
    sharepoint = tmp_path / "sharepoint"
    database = MolStatDatabase(sensitive / "data" / "molstat.sqlite3")
    calls = 0

    def make_report(
        marker: str, interval: int, values: list[str]
    ) -> tuple[ReportRequest, Path]:
        source = tmp_path / f"download-{interval}-{marker}.csv"
        with source.open("w", encoding="cp1252", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(["Value", "Analyse"])
            writer.writerows((value, marker) for value in values)
        request = ReportRequest(
            "statistics",
            "hemato",
            f"PAT-DIT-{marker}-OU",
            date(2024, 1, 1) if interval == 1 else date(2026, 9, 5),
            date(2026, 9, 4) if interval == 1 else date(2026, 9, 7),
        )
        return request, source

    def fetch_statistics(_unit_keys=None):
        nonlocal calls
        calls += 1
        values = ["historical", "overlap"] if calls == 1 else ["overlap", "latest"]
        return {
            "hemato": tuple(
                make_report(marker, calls, values)
                for marker in ("ANTALL", "RESULTATER", "EKSTRAKSJON")
            )
        }

    def process_merged(
        ordered: Path,
        answered: Path,
        extraction: Path,
        lookup_path: Path,
        output_dir: Path,
        *,
        profile: str,
        molstat_ids: Mapping[str, str],
    ) -> dict[str, int]:
        del extraction, lookup_path, profile, molstat_ids
        output_dir.mkdir(parents=True, exist_ok=True)
        row_counts: dict[str, int] = {}
        for name, source in (("antall", ordered), ("resultater", answered)):
            rows = list(csv.DictReader(source.open(encoding="cp1252"), delimiter=";"))
            _write(
                output_dir / f"{name}.csv",
                ["Value", "Analyse"],
                [[row["Value"], row["Analyse"]] for row in rows],
            )
            row_counts[name] = len(rows)
        return row_counts

    monkeypatch.setattr("molstat.statistics.process_reports", process_merged)
    publisher = SharePointPublisher(
        PublicationPolicy(
            allowed_columns={
                "antall.csv": frozenset({"Value", "Analyse"}),
                "resultater.csv": frozenset({"Value", "Analyse"}),
            },
            forbidden_patterns=(),
        )
    )
    system = MolStatSystem(
        database=database,
        archive=RawArchive(sensitive),
        statistics_processors={
            "hemato": StatisticsProcessor(analysis_codes=analysis_codes("hemato"))
        },
        backlog_processor=object(),
        publisher=publisher,
        sharepoint_root=sharepoint,
        work_root=sensitive / "work",
        statistics_fetch=fetch_statistics,
        backlog_fetch=lambda: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert system.run_statistics()["rows"] == 4
    assert system.run_statistics()["rows"] == 6

    with (sharepoint / "hemato" / "antall.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        published = list(csv.DictReader(stream, delimiter=";"))
    assert [row["Value"] for row in published] == [
        "historical",
        "overlap",
        "latest",
    ]


def test_two_backlog_hours_publish_complete_identifier_free_history(
    tmp_path: Path,
) -> None:
    sensitive = tmp_path / "k-sensitive"
    sharepoint = tmp_path / "sharepoint"
    database = MolStatDatabase(sensitive / "data" / "molstat.sqlite3")
    database.migrate()
    clock = [datetime(2026, 9, 7, 10, 15)]
    config = AppConfig(
        report_id="PAT-DIT-RESTANSE-OU",
        unit=UnitConfig("hemato", "MolPat hemato"),
        thresholds=ThresholdsConfig(24, 48),
        analyses=(
            AnalysisConfig(
                "KLONALITET",
                "Klonalitet",
                "Molekylær",
                "standard",
                source_codes=("IGH-OU",),
            ),
            AnalysisConfig("EMPTY", "Tom analyse", "Molekylær", "standard"),
        ),
    )
    processor = BacklogProcessor(config, _backlog_contract(), now=lambda: clock[0])
    fetch_count = 0

    def fetch_backlog():
        nonlocal fetch_count
        fetch_count += 1
        source = tmp_path / f"backlog-download-{fetch_count}.csv"
        sample_id = f"PRIVATE-SYNTHETIC-{fetch_count}"
        source.write_text(
            "SampleID;Analyse;Tidspunkt analysebestilling;Tidspunkt ankomst;"
            "Status analyse;Analyseresultat\n"
            f"{sample_id};IGH-OU;06.09.2026 07:00;06.09.2026 08:00;Initial;\n",
            encoding="cp1252",
        )
        return (
            ReportRequest(
                "backlog",
                "hemato",
                "PAT-DIT-RESTANSE-OU",
                date(2026, 9, 6),
                date(2026, 9, 7),
            ),
            source,
        )

    backlog_publisher = SharePointPublisher(
        PublicationPolicy(
            allowed_columns={
                "restansehistorikk_hemato.csv": frozenset(BACKLOG_PUBLIC_COLUMNS)
            },
            forbidden_patterns=(
                re.compile(r"sample[ ._-]*id", re.I),
                re.compile(r"work[ ._-]*item", re.I),
                re.compile(r"fingerprint", re.I),
            ),
        )
    )
    system = MolStatSystem(
        database=database,
        archive=RawArchive(sensitive),
        statistics_processors={},
        backlog_processor=processor,
        publisher={},
        backlog_publisher=backlog_publisher,
        sharepoint_root=sharepoint,
        work_root=sensitive / "work" / "processing",
        statistics_fetch=lambda _unit_keys=None: {},
        backlog_fetch=fetch_backlog,
    )

    assert system.run_backlog()["published_rows"] == 1
    clock[0] = datetime(2026, 9, 7, 11, 15)
    assert system.run_backlog()["published_rows"] == 2

    public_file = sharepoint / "Prøveflyt" / "restansehistorikk_hemato.csv"
    with public_file.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter=";"))
    assert len(rows) == 2
    assert {
        (row["Observert_tidspunkt"], row["Analyse"])
        for row in rows
    } == {
        ("2026-09-07T10:00:00", "IGH-OU"),
        ("2026-09-07T11:00:00", "IGH-OU"),
    }
    with database._connect() as connection:
        current = connection.execute(
            "SELECT sample_key FROM backlog_sample"
        ).fetchall()
    assert current == [("PRIVATE-SYNTHETIC-2",)]
    public_text = public_file.read_text(encoding="utf-8")
    assert "PRIVATE-SYNTHETIC" not in public_text
    assert "fingerprint" not in public_text.casefold()


def _backlog_contract() -> CsvContract:
    return CsvContract(
        delimiter=";",
        encoding="cp1252",
        columns={
            "sample_id": "SampleID",
            "analysis_code": "Analyse",
            "created_at": "Tidspunkt analysebestilling",
            "arrival_at": "Tidspunkt ankomst",
            "status": "Status analyse",
            "result": "Analyseresultat",
        },
        completed_values=("Completed",),
    )


def test_run_all_continues_after_one_capability_fails() -> None:
    calls: list[str] = []
    system = MolStatSystem.__new__(MolStatSystem)
    system.units = DEFAULT_UNITS

    def run_capability(unit_key: str, job_kind: str) -> dict[str, int]:
        label = f"{unit_key}:{job_kind}"
        calls.append(label)
        if label == "hemato:statistics":
            raise RuntimeError("private test failure")
        return {"rows": 2 if job_kind == "backlog" else 3}

    system._run_capability = run_capability

    runs = system.run_all(("hemato", "solide"))

    assert calls == [
        "hemato:statistics",
        "hemato:backlog",
        "solide:statistics",
        "solide:backlog",
    ]
    assert [
        (run.unit_key, run.job_kind, run.error is None) for run in runs
    ] == [
        ("hemato", "statistics", False),
        ("hemato", "backlog", True),
        ("solide", "statistics", True),
        ("solide", "backlog", True),
    ]
    assert isinstance(runs[0], system_module.CapabilityRun)


def test_unit_target_runs_only_its_registered_capabilities() -> None:
    calls: list[tuple[str, str]] = []
    system = MolStatSystem.__new__(MolStatSystem)
    system.units = DEFAULT_UNITS
    system._run_capability = lambda unit, job: (
        calls.append((unit, job)) or {"rows": 1}
    )

    runs = system.run_unit("solide")

    assert calls == [("solide", "statistics"), ("solide", "backlog")]
    assert len(runs) == 2
