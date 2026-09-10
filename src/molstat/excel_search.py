"""Generate the macro-free, read-only Excel view of the sample registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import zipfile
from uuid import uuid4

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


class WorkbookValidationError(RuntimeError):
    """Raised when a generated workbook is unsafe or structurally incomplete."""


@dataclass(frozen=True, slots=True)
class WorkbookPublication:
    status: str
    path: Path


def search_samples(
    samples: tuple[ExcelSampleRow, ...],
    query: str,
    *,
    prefix: bool,
) -> tuple[ExcelSampleRow, ...]:
    normalized = query.strip().upper()
    if not normalized:
        return ()
    if prefix:
        return tuple(
            row
            for row in samples
            if row.sample_number.upper().startswith(normalized)
            or row.molstat_key.upper().startswith(normalized)
        )
    return tuple(
        row
        for row in samples
        if row.sample_number.upper() == normalized
        or row.molstat_key.upper() == normalized
    )


def select_unique_sample(
    samples: tuple[ExcelSampleRow, ...],
    query: str,
    *,
    prefix: bool,
) -> str | None:
    matches = search_samples(samples, query, prefix=prefix)
    return matches[0].molstat_key if len(matches) == 1 else None


def partition_analysis_rows(
    rows: tuple[ExcelAnalysisRow, ...],
    *,
    row_limit: int = 900_000,
) -> dict[str, tuple[ExcelAnalysisRow, ...]]:
    if row_limit < 1:
        raise ValueError("Excel-radgrensen må være positiv.")
    if len(rows) <= row_limit:
        return {"Analyser": rows}
    by_year: dict[int, list[ExcelAnalysisRow]] = {}
    for row in sorted(rows, key=lambda item: (item.ordered_at, item.molstat_key)):
        by_year.setdefault(row.ordered_at.year, []).append(row)
    partitions: dict[str, tuple[ExcelAnalysisRow, ...]] = {}
    for year in sorted(by_year):
        year_rows = by_year[year]
        chunks = [
            tuple(year_rows[index : index + row_limit])
            for index in range(0, len(year_rows), row_limit)
        ]
        for chunk_number, chunk in enumerate(chunks, start=1):
            suffix = "" if len(chunks) == 1 else f"-{chunk_number}"
            partitions[f"Analyser {year}{suffix}"] = chunk
    return partitions


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


def generate_search_workbook(
    snapshot: ExcelSnapshot,
    destination: Path,
    *,
    analysis_row_limit: int = 900_000,
) -> None:
    """Generate the four-sheet, macro-free registry search workbook."""

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(path)
    try:
        workbook.set_calc_mode("auto")
        formats = _workbook_formats(workbook)
        search = workbook.add_worksheet("Prøvesøk")
        samples = workbook.add_worksheet("Prøver")
        analysis_partitions = partition_analysis_rows(
            snapshot.analyses,
            row_limit=analysis_row_limit,
        )
        analysis_sheets = {
            name: workbook.add_worksheet(name) for name in analysis_partitions
        }
        about = workbook.add_worksheet("Om")
        for sheet in (search, samples, *analysis_sheets.values(), about):
            sheet.hide_gridlines(2)

        search.write("A2", "Prøvesøk", formats["title"])
        search.write("A4", "Prøvenummer eller MolStat-ID", formats["body"])
        search.write_blank("B4", None, formats["input"])
        search.write("A5", "Søketype", formats["body"])
        search.write("B5", "Eksakt", formats["input"])
        search.data_validation("B5", {"validate": "list", "source": ["Eksakt", "Prefiks"]})
        search.write("A6", "Valgt MolStat-ID", formats["body"])
        search.write_row(
            "A8",
            ["MolStat-ID", "Prøvenummer", "Først sett", "Sist sett", "Analyser", "I RESTANSE nå"],
            formats["header"],
        )
        search.write_row(
            "H8",
            ["Analyse", "Bestilt", "WorkItem", "Identitetsstatus", "I RESTANSE nå", "Kilder", "Resultat", "Godkjent"],
            formats["header"],
        )
        sample_end_row = max(2, len(snapshot.samples) + 1)
        sample_keys = f"'Prøver'!$A$2:$A${sample_end_row}"
        sample_numbers = f"'Prøver'!$B$2:$B${sample_end_row}"
        sample_output = f"'Prøver'!$A$2:$F${sample_end_row}"
        exact_match = (
            f"({sample_numbers}=TRIM($B$4))"
            f"+({sample_keys}=UPPER(TRIM($B$4)))"
        )
        prefix_match = (
            f"(LEFT({sample_numbers},LEN(TRIM($B$4)))=TRIM($B$4))"
            f"+(LEFT({sample_keys},LEN(UPPER(TRIM($B$4))))=UPPER(TRIM($B$4)))"
        )
        match_expression = f'IF($B$5="Eksakt",{exact_match},{prefix_match})'
        search.write_dynamic_array_formula(
            "A9",
            f'=IF(TRIM($B$4)="","",FILTER({sample_output},'
            f'{match_expression},"Ingen treff"))',
        )
        search.write_formula(
            "B6",
            '=IF($A$7="1 treff – detaljer vises",$A$9,"")',
            formats["body"],
            "",
        )
        search.write_formula(
            "A7",
            '=IF(TRIM($B$4)="","Skriv inn prøvenummer eller MolStat-ID",'
            f'IF(SUM(--({match_expression}))=0,"Ingen treff",'
            f'IF(SUM(--({match_expression}))=1,"1 treff – detaljer vises",'
            f'SUM(--({match_expression}))&" treff – avgrens søket")))',
            formats["note"],
            "Skriv inn prøvenummer eller MolStat-ID",
        )
        table_names = [
            "tbl" + name.replace(" ", "").replace("-", "")
            for name in analysis_partitions
        ]
        detail_ranges = [
            (
                f"'{name}'!$A$2:$J${max(2, len(rows) + 1)}",
                f"'{name}'!$A$2:$A${max(2, len(rows) + 1)}",
            )
            for name, rows in analysis_partitions.items()
        ]
        if len(detail_ranges) == 1:
            detail_data, detail_keys = detail_ranges[0]
            detail_condition = f"{detail_keys}=$B$6"
        else:
            detail_data = "VSTACK(" + ",".join(item[0] for item in detail_ranges) + ")"
            detail_keys = "VSTACK(" + ",".join(item[1] for item in detail_ranges) + ")"
            detail_condition = f"{detail_keys}=$B$6"
        search.write_dynamic_array_formula(
            "H9",
            f'=IF($B$6="","",FILTER({detail_data},{detail_condition},"Ingen analyser"))',
        )
        search.set_column("A:A", 24)
        search.set_column("B:B", 26)
        search.set_column("C:D", 18)
        search.set_column("E:E", 16)
        search.set_column("F:F", 18)
        search.set_column("G:G", 3)
        search.set_column("H:Q", 20)

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
        for (sheet_name, partition_rows), table_name in zip(
            analysis_partitions.items(), table_names, strict=True
        ):
            analysis_sheet = analysis_sheets[sheet_name]
            analysis_sheet.write_row(0, 0, analysis_headers, formats["header"])
            for row_index, row in enumerate(partition_rows, start=1):
                analysis_sheet.write_string(row_index, 0, row.molstat_key, formats["text"])
                analysis_sheet.write_string(row_index, 1, row.sample_number, formats["text"])
                analysis_sheet.write_string(row_index, 2, row.analysis_code, formats["text"])
                analysis_sheet.write_datetime(row_index, 3, row.ordered_at, formats["date"])
                analysis_sheet.write_string(row_index, 4, row.source_occurrence_id or "", formats["text"])
                analysis_sheet.write_string(row_index, 5, row.identity_status, formats["body"])
                analysis_sheet.write_string(row_index, 6, "Ja" if row.in_backlog else "Nei", formats["body"])
                analysis_sheet.write_string(row_index, 7, row.source_kinds, formats["body"])
                if row.resulted_at is not None:
                    analysis_sheet.write_datetime(row_index, 8, row.resulted_at, formats["date"])
                if row.approved_at is not None:
                    analysis_sheet.write_datetime(row_index, 9, row.approved_at, formats["date"])
            analysis_last_row = max(1, len(partition_rows))
            analysis_sheet.add_table(
                0, 0, analysis_last_row, len(analysis_headers) - 1,
                {"name": table_name, "style": "Table Style Medium 2", "columns": [{"header": name} for name in analysis_headers]},
            )
            analysis_sheet.freeze_panes(1, 2)
            analysis_sheet.set_column("A:B", 26)
            analysis_sheet.set_column("C:C", 22)
            analysis_sheet.set_column("D:D", 18)
            analysis_sheet.set_column("E:H", 24)
            analysis_sheet.set_column("I:J", 18)

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


def validate_search_workbook(path: Path) -> None:
    """Validate the allowlisted workbook structure before publication."""

    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            bad_members = {
                name
                for name in names
                if name == "xl/vbaProject.bin"
                or name.startswith("xl/externalLinks/")
                or name == "xl/connections.xml"
            }
            workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
            table_xml = "\n".join(
                archive.read(name).decode("utf-8")
                for name in names
                if name.startswith("xl/tables/table")
            )
            corrupt_member = archive.testzip()
    except (OSError, KeyError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
        raise WorkbookValidationError("Arbeidsboken kunne ikke valideres.") from exc
    if corrupt_member is not None or bad_members:
        raise WorkbookValidationError("Arbeidsboken inneholder ugyldige deler.")
    for required_sheet in ("Prøvesøk", "Prøver", "Om"):
        if f'name="{required_sheet}"' not in workbook_xml:
            raise WorkbookValidationError("Arbeidsboken mangler et påkrevd ark.")
    if 'name="tblProver"' not in table_xml or "tblAnalyser" not in table_xml:
        raise WorkbookValidationError("Arbeidsboken mangler påkrevde datatabeller.")


def publish_search_workbook(
    snapshot: ExcelSnapshot,
    destination: Path,
    *,
    validate: Callable[[Path], None] = validate_search_workbook,
    replace: Callable[[Path, Path], None] = os.replace,
) -> WorkbookPublication:
    """Generate, validate and atomically publish one workbook candidate."""

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.parent / f".{target.stem}.{uuid4().hex}.pending.xlsx"
    try:
        generate_search_workbook(snapshot, pending)
        with pending.open("r+b") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        validate(pending)
        try:
            replace(pending, target)
        except PermissionError:
            return WorkbookPublication("locked", target)
        return WorkbookPublication("published", target)
    finally:
        pending.unlink(missing_ok=True)


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
