import csv
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
from molstat.lvms.report import ReportRequest
from molstat.publisher import PublicationPolicy, SharePointPublisher
from molstat.statistics import StatisticsResult
from molstat.system import MolStatSystem


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
        statistics_fetch=lambda: {"hemato": ((statistics_request, stats_download),)},
        backlog_fetch=lambda: (backlog_request, backlog_download),
    )

    assert system.run_statistics()["rows"] == 2
    assert system.run_backlog()["rows"] == 1
    snapshot = system.public_snapshot(now)

    assert not stats_download.exists()
    assert not backlog_download.exists()
    archived_text = " ".join(
        path.read_text(errors="ignore")
        for path in (sensitive / "raw").rglob("*.csv")
    )
    assert "SECRET-STAT-RAW" in archived_text
    assert "SECRET-BACKLOG-42" in archived_text
    public_text = repr(snapshot) + " ".join(
        path.read_text(encoding="utf-8-sig")
        for path in sharepoint.rglob("*.csv")
    )
    assert "SECRET" not in public_text
    assert "SampleID" not in public_text
