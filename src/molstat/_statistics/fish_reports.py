"""Prepare the two FISH LVMS exports for Power BI without direct identifiers."""

from __future__ import annotations

import csv
import json
import re
from .selection import AnalysisSelection, codes_for_report

from collections import Counter
from datetime import date, datetime
from pathlib import Path

from molstat._statistics.processing import read_lvms_csv


ANTALL_FIELDS = ("Analyse", "Tidspunkt.analysebestilling", "Rapportgruppe", "Svarfrist", "Maaned")
RESULT_FIELDS = ("Materiale", "Analyse", "Rapportgruppe", "Tidspunkt.prøvetaking", "Tidspunkt.opprettet", "Tidspunkt.analysebestilling", "Tidspunkt.analyseresultat", "Tidspunkt.godkjenning", "Svarfrist", "MolStat-ID", "Pris2026NOK", "Priskobling", "Svartid dager", "Svartid status", "Normstatus")
DATE_FIELDS = ("Tidspunkt.prøvetaking", "Tidspunkt.opprettet", "Tidspunkt.analysebestilling", "Tidspunkt.analyseresultat", "Tidspunkt.godkjenning")


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fields, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def parse_time(value: str | None) -> datetime | None:
    value = (value or "").strip()
    if not value or value == "NA":
        return None
    for pattern in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            pass
    raise ValueError(f"Invalid FISH timestamp: {value!r}")


def display(value: datetime | None) -> str:
    return value.strftime("%Y/%m/%d %H:%M:%S") if value else ""


def turnaround(start: datetime | None, end: datetime | None) -> tuple[str, str, str]:
    if start is None or end is None:
        return "", "Mangler tidspunkt", "Ikke beregnet"
    days = (end - start).total_seconds() / 86400
    if days < 0:
        return "", "Negativ tid", "Ikke beregnet"
    if days > 365:
        return "", "Over 365 dager", "Ikke beregnet"
    return f"{days:.10f}", "Gyldig", "Ikke beregnet"


def process(ordered: Path, answered: Path, output: Path, analysis_codes: AnalysisSelection) -> dict:
    ordered_codes = codes_for_report(analysis_codes, "antall")
    result_codes = codes_for_report(analysis_codes, "resultater")
    counts = Counter()
    antall = []
    resultater = []
    raw_antall = read_lvms_csv(ordered)
    raw_resultater = read_lvms_csv(answered)
    for row in raw_antall:
        code = row.get("Analyse", "").strip()
        if code not in ordered_codes:
            counts[("antall", code)] += 1
            continue
        order = parse_time(row.get("Tidspunkt.analysebestilling"))
        antall.append({"Analyse": code, "Tidspunkt.analysebestilling": display(order), "Rapportgruppe": "", "Svarfrist": "", "Maaned": order.month if order else ""})
    for row in raw_resultater:
        code = row.get("Analyse", "").strip()
        if code not in result_codes:
            counts[("resultater", code)] += 1
            continue
        times = {field: parse_time(row.get(field)) for field in DATE_FIELDS}
        days, status, norm = turnaround(times["Tidspunkt.analysebestilling"], times["Tidspunkt.analyseresultat"])
        resultater.append({"Materiale": row.get("Materiale", ""), "Analyse": code, "Rapportgruppe": "", **{field: display(value) for field, value in times.items()}, "Svarfrist": "", "MolStat-ID": "", "Pris2026NOK": "", "Priskobling": "", "Svartid dager": days, "Svartid status": status, "Normstatus": norm})
    write_csv(output / "antall.csv", ANTALL_FIELDS, antall)
    write_csv(output / "resultater.csv", RESULT_FIELDS, resultater)
    summary = {"input_antall": len(raw_antall), "input_resultater": len(raw_resultater), "antall": len(antall), "resultater": len(resultater), "gyldige_svartider": sum(row["Svartid status"] == "Gyldig" for row in resultater), "innen_norm": sum(row["Normstatus"] == "Innen norm" for row in resultater), "ekskluderte_koder": [{"rapport": kind, "kode": code, "rader": number} for (kind, code), number in sorted(counts.items())]}
    (output / "kontroll.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def empty_template(output: Path) -> None:
    write_csv(output / "antall.csv", ANTALL_FIELDS, [])
    write_csv(output / "resultater.csv", RESULT_FIELDS, [])


def merge_archives(paths: list[Path]) -> tuple[list[str], list[dict[str, str]]]:
    """Newest FISH snapshot owns its analysis-order interval, including deletions."""
    from .merge_raw import merge_report_csvs
    from .processing import clean_text

    pattern = re.compile(r"__(\d{4}-\d{2}-\d{2})__(\d{4}-\d{2}-\d{2})(?:__r\d+)?\.csv$")
    covered: list[tuple[date, date]] = []
    header: list[str] = []
    merged: list[dict[str, str]] = []
    for path in sorted(paths, key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True):
        match = pattern.search(path.name)
        if match is None:
            raise ValueError("FISH-arkivet mangler en gyldig uttrekksperiode.")
        start, end = date.fromisoformat(match[1]), date.fromisoformat(match[2])
        if any(a <= start and end <= b for a, b in covered):
            continue
        fields, rows = merge_report_csvs([path])
        header.extend(field for field in fields if field not in header)
        order_column = next((field for field in fields
            if field.strip().replace(" ", ".") == "Tidspunkt.analysebestilling"), None)
        for row in rows:
            ordered = parse_time(clean_text(row.get(order_column)))
            if ordered is None or not start <= ordered.date() <= end:
                raise ValueError("FISH-arkivet inneholder analysebestilling utenfor uttrekksperioden.")
            if not any(a <= ordered.date() <= b for a, b in covered):
                merged.append(row)
        intervals: list[tuple[date, date]] = []
        for a, b in sorted([*covered, (start, end)]):
            if intervals and (a - intervals[-1][1]).days <= 1:
                intervals[-1] = intervals[-1][0], max(intervals[-1][1], b)
            else:
                intervals.append((a, b))
        covered = intervals
    return header, merged
