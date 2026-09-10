"""Generate the macro-free, read-only Excel view of the sample registry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import xlsxwriter

from .database import MolStatDatabase


@dataclass(frozen=True, slots=True)
class ExcelSampleRow:
    molstat_key: str
    sample_number: str
    first_seen_at: datetime
    last_seen_at: datetime
    occurrence_count: int
    backlog_count: int


@dataclass(frozen=True, slots=True)
class ExcelAnalysisRow:
    molstat_key: str
    sample_number: str
    analysis_code: str
    ordered_at: datetime
    source_occurrence_id: str | None
    identity_status: str
    in_backlog: bool
    source_kinds: str
    resulted_at: datetime | None
    approved_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExcelSnapshot:
    generated_at: datetime
    samples: tuple[ExcelSampleRow, ...]
    analyses: tuple[ExcelAnalysisRow, ...]


def read_excel_snapshot(
    database: MolStatDatabase,
    *,
    generated_at: datetime,
) -> ExcelSnapshot:
    """Read all workbook rows from one consistent SQLite snapshot."""

    with database._connect() as connection:
        connection.execute("BEGIN")
        try:
            sample_rows = connection.execute(
                """
                SELECT s.molstat_key, si.identifier_value,
                       s.first_seen_at, s.last_seen_at,
                       COUNT(DISTINCT ao.id), COUNT(DISTINCT bc.occurrence_id)
                FROM sample AS s
                JOIN sample_identifier AS si ON si.sample_id = s.id
                    AND si.identifier_type = 'sample_number'
                LEFT JOIN analysis_occurrence AS ao ON ao.sample_id = s.id
                LEFT JOIN backlog_current AS bc ON bc.occurrence_id = ao.id
                GROUP BY s.id, s.molstat_key, si.identifier_value,
                         s.first_seen_at, s.last_seen_at
                ORDER BY si.normalized_value, s.molstat_key
                """
            ).fetchall()
            analysis_rows = connection.execute(
                """
                SELECT s.molstat_key, si.identifier_value, ao.analysis_code,
                       ao.ordered_at, ao.source_occurrence_id,
                       ao.identity_status,
                       CASE WHEN bc.occurrence_id IS NULL THEN 0 ELSE 1 END,
                       (
                           SELECT GROUP_CONCAT(source_kind, ', ')
                           FROM (
                               SELECT source_kind
                               FROM source_observation
                               WHERE occurrence_id = ao.id
                               ORDER BY source_kind
                           )
                       ),
                       MAX(CASE WHEN ae.event_type = 'resulted' THEN ae.event_at END),
                       MAX(CASE WHEN ae.event_type = 'approved' THEN ae.event_at END)
                FROM analysis_occurrence AS ao
                JOIN sample AS s ON s.id = ao.sample_id
                JOIN sample_identifier AS si ON si.sample_id = s.id
                    AND si.identifier_type = 'sample_number'
                LEFT JOIN backlog_current AS bc ON bc.occurrence_id = ao.id
                LEFT JOIN analysis_event AS ae ON ae.occurrence_id = ao.id
                GROUP BY ao.id, s.molstat_key, si.identifier_value,
                         ao.analysis_code, ao.ordered_at,
                         ao.source_occurrence_id, ao.identity_status,
                         bc.occurrence_id
                ORDER BY si.normalized_value, ao.ordered_at, ao.id
                """
            ).fetchall()
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
    return ExcelSnapshot(
        generated_at=generated_at,
        samples=tuple(
            ExcelSampleRow(
                molstat_key=str(row[0]),
                sample_number=str(row[1]),
                first_seen_at=datetime.fromisoformat(str(row[2])),
                last_seen_at=datetime.fromisoformat(str(row[3])),
                occurrence_count=int(row[4]),
                backlog_count=int(row[5]),
            )
            for row in sample_rows
        ),
        analyses=tuple(
            ExcelAnalysisRow(
                molstat_key=str(row[0]),
                sample_number=str(row[1]),
                analysis_code=str(row[2]),
                ordered_at=datetime.fromisoformat(str(row[3])),
                source_occurrence_id=(str(row[4]) if row[4] is not None else None),
                identity_status=str(row[5]),
                in_backlog=bool(row[6]),
                source_kinds=str(row[7] or ""),
                resulted_at=(
                    datetime.fromisoformat(str(row[8])) if row[8] is not None else None
                ),
                approved_at=(
                    datetime.fromisoformat(str(row[9])) if row[9] is not None else None
                ),
            )
            for row in analysis_rows
        ),
    )


def _workbook_formats(workbook: xlsxwriter.Workbook) -> dict[str, object]:
    return {
        "title": workbook.add_format(
            {"font_name": "Arial", "font_size": 14, "bold": True, "font_color": "#17365D"}
        ),
        "header": workbook.add_format(
            {
                "font_name": "Arial", "font_size": 10, "bold": True,
                "font_color": "#FFFFFF", "bg_color": "#1F4E78",
                "align": "center", "valign": "vcenter",
            }
        ),
        "body": workbook.add_format({"font_name": "Arial", "font_size": 10}),
        "text": workbook.add_format(
            {"font_name": "Arial", "font_size": 10, "num_format": "@", "quote_prefix": True}
        ),
        "date": workbook.add_format(
            {"font_name": "Arial", "font_size": 10, "num_format": "yyyy-mm-dd hh:mm"}
        ),
        "input": workbook.add_format(
            {
                "font_name": "Arial", "font_size": 11, "num_format": "@",
                "quote_prefix": True, "bg_color": "#FFF2CC",
                "border": 1, "border_color": "#D6B656",
            }
        ),
        "note": workbook.add_format(
            {"font_name": "Arial", "font_size": 10, "italic": True, "font_color": "#666666"}
        ),
    }


def generate_search_workbook(snapshot: ExcelSnapshot, destination: Path) -> None:
    """Generate the four-sheet, macro-free registry search workbook."""

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(path)
    try:
        workbook.set_calc_mode("auto")
        formats = _workbook_formats(workbook)
        search = workbook.add_worksheet("Prøvesøk")
        samples = workbook.add_worksheet("Prøver")
        analyses = workbook.add_worksheet("Analyser")
        about = workbook.add_worksheet("Om")
        for sheet in (search, samples, analyses, about):
            sheet.hide_gridlines(2)

        search.write("A2", "Prøvesøk", formats["title"])
        search.write("A4", "Prøvenummer eller MolStat-ID", formats["body"])
        search.write_blank("B4", None, formats["input"])
        search.write("A6", "Skriv inn prøvenummer eller MolStat-ID", formats["note"])
        search.write_row(
            "A8",
            ["MolStat-ID", "Prøvenummer", "Først sett", "Sist sett", "Analyser", "I RESTANSE nå"],
            formats["header"],
        )
        search.write_row(
            "A13",
            ["Analyse", "Bestilt", "WorkItem", "Identitetsstatus", "I RESTANSE nå", "Kilder", "Resultat", "Godkjent"],
            formats["header"],
        )
        search.set_column("A:A", 24)
        search.set_column("B:B", 26)
        search.set_column("C:D", 18)
        search.set_column("E:E", 16)
        search.set_column("F:H", 22)

        sample_headers = [
            "MolStat-ID", "Prøvenummer", "Først sett", "Sist sett",
            "Analyser", "I RESTANSE nå", "Restanser",
        ]
        samples.write_row(0, 0, sample_headers, formats["header"])
        for row_index, row in enumerate(snapshot.samples, start=1):
            samples.write_string(row_index, 0, row.molstat_key, formats["text"])
            samples.write_string(row_index, 1, row.sample_number, formats["text"])
            samples.write_datetime(row_index, 2, row.first_seen_at, formats["date"])
            samples.write_datetime(row_index, 3, row.last_seen_at, formats["date"])
            samples.write_number(row_index, 4, row.occurrence_count, formats["body"])
            samples.write_string(row_index, 5, "Ja" if row.backlog_count else "Nei", formats["body"])
            samples.write_number(row_index, 6, row.backlog_count, formats["body"])
        sample_last_row = max(1, len(snapshot.samples))
        samples.add_table(
            0, 0, sample_last_row, len(sample_headers) - 1,
            {"name": "tblProver", "style": "Table Style Medium 2", "columns": [{"header": name} for name in sample_headers]},
        )
        samples.freeze_panes(1, 2)
        samples.set_column("A:B", 26)
        samples.set_column("C:D", 18)
        samples.set_column("E:G", 15)

        analysis_headers = [
            "MolStat-ID", "Prøvenummer", "Analyse", "Bestilt", "WorkItem",
            "Identitetsstatus", "I RESTANSE nå", "Kilder", "Resultat", "Godkjent",
        ]
        analyses.write_row(0, 0, analysis_headers, formats["header"])
        for row_index, row in enumerate(snapshot.analyses, start=1):
            analyses.write_string(row_index, 0, row.molstat_key, formats["text"])
            analyses.write_string(row_index, 1, row.sample_number, formats["text"])
            analyses.write_string(row_index, 2, row.analysis_code, formats["text"])
            analyses.write_datetime(row_index, 3, row.ordered_at, formats["date"])
            analyses.write_string(row_index, 4, row.source_occurrence_id or "", formats["text"])
            analyses.write_string(row_index, 5, row.identity_status, formats["body"])
            analyses.write_string(row_index, 6, "Ja" if row.in_backlog else "Nei", formats["body"])
            analyses.write_string(row_index, 7, row.source_kinds, formats["body"])
            if row.resulted_at is not None:
                analyses.write_datetime(row_index, 8, row.resulted_at, formats["date"])
            if row.approved_at is not None:
                analyses.write_datetime(row_index, 9, row.approved_at, formats["date"])
        analysis_last_row = max(1, len(snapshot.analyses))
        analyses.add_table(
            0, 0, analysis_last_row, len(analysis_headers) - 1,
            {"name": "tblAnalyser", "style": "Table Style Medium 2", "columns": [{"header": name} for name in analysis_headers]},
        )
        analyses.freeze_panes(1, 2)
        analyses.set_column("A:B", 26)
        analyses.set_column("C:C", 22)
        analyses.set_column("D:D", 18)
        analyses.set_column("E:H", 24)
        analyses.set_column("I:J", 18)

        about.write("A2", "Om Prøvesøk", formats["title"])
        about.write("A4", "Sist generert", formats["body"])
        about.write_datetime("B4", snapshot.generated_at, formats["date"])
        about.write("A6", "Datakilde", formats["body"])
        about.write("B6", "MolStat prøveregister på K-sensitiv", formats["body"])
        about.write("A8", "Bruk", formats["body"])
        about.write(
            "B8",
            "Skriv prøvenummer eller MolStat-ID i det gule feltet på Prøvesøk. Arbeidsboken er en lesekopi og skriver ikke til databasen.",
            formats["body"],
        )
        about.set_column("A:A", 18)
        about.set_column("B:B", 82)
        about.set_row(7, 32)
    finally:
        workbook.close()


def generate_compatibility_workbook(destination: Path) -> None:
    """Write a minimal target-engine compatibility workbook."""

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(path)
    try:
        workbook.set_calc_mode("auto")
        sheet = workbook.add_worksheet("Kompatibilitet")
        sheet.hide_gridlines(2)
        title = workbook.add_format(
            {"font_name": "Arial", "font_size": 14, "bold": True, "font_color": "#17365D"}
        )
        header = workbook.add_format(
            {
                "font_name": "Arial",
                "font_size": 10,
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#1F4E78",
                "align": "center",
                "valign": "vcenter",
            }
        )
        text = workbook.add_format(
            {
                "font_name": "Arial",
                "font_size": 10,
                "num_format": "@",
                "quote_prefix": True,
                "align": "left",
            }
        )
        timestamp = workbook.add_format(
            {"font_name": "Arial", "font_size": 10, "num_format": "yyyy-mm-dd hh:mm"}
        )
        sheet.write("A2", "Prøvesøk – kompatibilitetstest", title)
        sheet.write_row("A4", ["Felt", "Verdi"], header)
        sheet.write_string("A5", "Prøvenummer", text)
        sheet.write_string("B5", "00123456789012345678", text)
        sheet.write_string("A6", "MolStat-ID", text)
        sheet.write_string("B6", "MS-0000000000000001", text)
        sheet.write_string("A7", "Tidspunkt", text)
        sheet.write_datetime("B7", datetime(2026, 9, 10, 8, 15), timestamp)
        sheet.write_string("A8", "Formel", text)
        sheet.write_formula("B8", "=B6", text, "MS-0000000000000001")
        sheet.set_column("A:A", 18)
        sheet.set_column("B:B", 26)
        sheet.freeze_panes(4, 0)
    finally:
        workbook.close()
