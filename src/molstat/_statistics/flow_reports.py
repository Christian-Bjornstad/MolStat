"""Prepare FLOW ANTALL and RESULTATER exports for Power BI, without extraction.

Raw LVMS files remain at the caller's sensitive location. This processor never
writes Sample ID, PID, Workitemgruppe or other direct identifiers to output.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from molstat._statistics.processing import read_lvms_csv


DATE_FIELDS = (
    "Tidspunkt.prøvetaking", "Tidspunkt.opprettet", "Tidspunkt.analysebestilling",
    "Tidspunkt.analyseresultat", "Tidspunkt.godkjenning",
)
ANTALL_FIELDS = ("Analyse", "Tidspunkt.analysebestilling", "Rapportgruppe", "Svarfrist", "Maaned")
RESULTATER_FIELDS = (
    "Materiale", "Analyse", "Rapportgruppe", *DATE_FIELDS,
    "Svarfrist", "MolStat-ID", "Pris2026NOK", "Priskobling",
    "Svartid prøvetaking-godkjenning dager", "Svartid opprettet-godkjenning dager",
    "Svartid prøvetaking status", "Svartid opprettet status",
)


def read_lookup(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    result = {row["Analyse"]: row for row in rows}
    if len(rows) != len(result):
        raise ValueError("FLOW lookup has duplicate analysis codes")
    return result


def parse_time(value: str | None) -> datetime | None:
    value = (value or "").strip()
    if not value or value == "NA":
        return None
    for pattern in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            pass
    raise ValueError(f"Invalid FLOW timestamp format: {value!r}")


def formatted(value: datetime | None) -> str:
    return value.strftime("%Y/%m/%d %H:%M:%S") if value else ""


def turnaround(start: datetime | None, end: datetime | None) -> tuple[str, str]:
    if start is None or end is None:
        return "", "Mangler tidspunkt"
    days = (end - start).total_seconds() / 86400
    if days < 0:
        return "", "Negativ tid"
    if days > 365:
        return "", "Over 365 dager"
    return f"{days:.10f}", "Gyldig"


def write_rows(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def process(ordered_file: Path, answered_file: Path, output_dir: Path, lookup_path: Path) -> dict:
    lookup = read_lookup(lookup_path)
    raw_ordered = read_lvms_csv(ordered_file)
    raw_answered = read_lvms_csv(answered_file)
    antall = []
    resultater = []
    excluded = Counter()
    for row in raw_ordered:
        code = row.get("Analyse", "")
        if code not in lookup:
            excluded[("antall", code)] += 1
            continue
        ordered = parse_time(row.get("Tidspunkt.analysebestilling"))
        antall.append({
            "Analyse": code,
            "Tidspunkt.analysebestilling": formatted(ordered),
            "Rapportgruppe": lookup[code]["Rapportgruppe"],
            "Svarfrist": "",
            "Maaned": ordered.month if ordered else "",
        })
    for row in raw_answered:
        code = row.get("Analyse", "")
        if code not in lookup:
            excluded[("resultater", code)] += 1
            continue
        times = {field: parse_time(row.get(field)) for field in DATE_FIELDS}
        approval = times["Tidspunkt.godkjenning"]
        patient_days, patient_status = turnaround(times["Tidspunkt.prøvetaking"], approval)
        created_days, created_status = turnaround(times["Tidspunkt.opprettet"], approval)
        info = lookup[code]
        resultater.append({
            "Materiale": "",
            "Analyse": code,
            "Rapportgruppe": info["Rapportgruppe"],
            **{field: formatted(value) for field, value in times.items()},
            "Svarfrist": "",
            "MolStat-ID": "",  # Only the secure MolStat registry may assign this.
            "Pris2026NOK": info["Pris2026NOK"],
            "Priskobling": info["Priskobling"],
            "Svartid prøvetaking-godkjenning dager": patient_days,
            "Svartid opprettet-godkjenning dager": created_days,
            "Svartid prøvetaking status": patient_status,
            "Svartid opprettet status": created_status,
        })
    write_rows(output_dir / "antall.csv", ANTALL_FIELDS, antall)
    write_rows(output_dir / "resultater.csv", RESULTATER_FIELDS, resultater)
    summary = {
        "input_antall": len(raw_ordered), "input_resultater": len(raw_answered),
        "antall": len(antall), "resultater": len(resultater),
        "excluded_unlisted": [{"report": report, "code": code, "rows": count} for (report, code), count in sorted(excluded.items())],
        "valid_patient_turnaround": sum(row["Svartid prøvetaking status"] == "Gyldig" for row in resultater),
        "valid_created_turnaround": sum(row["Svartid opprettet status"] == "Gyldig" for row in resultater),
    }
    (output_dir / "kontroll.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def empty_template(output_dir: Path) -> None:
    write_rows(output_dir / "antall.csv", ANTALL_FIELDS, [])
    write_rows(output_dir / "resultater.csv", RESULTATER_FIELDS, [])
