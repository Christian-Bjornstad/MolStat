"""Prepare the two FISH LVMS exports for Power BI without direct identifiers."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
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
    return f"{days:.10f}", "Gyldig", "Innen norm" if days <= 5 else "Over norm"


def process(ordered: Path, answered: Path, output: Path, lookup_path: Path) -> dict:
    with lookup_path.open(encoding="utf-8-sig", newline="") as handle:
        lookup = {row["Analyse"]: row for row in csv.DictReader(handle, delimiter=";")}
    counts = Counter()
    antall = []
    resultater = []
    raw_antall = read_lvms_csv(ordered)
    raw_resultater = read_lvms_csv(answered)
    for row in raw_antall:
        code = row.get("Analyse", "").strip()
        if code not in lookup:
            counts[("antall", code)] += 1
            continue
        order = parse_time(row.get("Tidspunkt.analysebestilling"))
        antall.append({"Analyse": code, "Tidspunkt.analysebestilling": display(order), "Rapportgruppe": "FISH", "Svarfrist": 5, "Maaned": order.month if order else ""})
    for row in raw_resultater:
        code = row.get("Analyse", "").strip()
        if code not in lookup:
            counts[("resultater", code)] += 1
            continue
        times = {field: parse_time(row.get(field)) for field in DATE_FIELDS}
        days, status, norm = turnaround(times["Tidspunkt.analysebestilling"], times["Tidspunkt.analyseresultat"])
        resultater.append({"Materiale": "", "Analyse": code, "Rapportgruppe": "FISH", **{field: display(value) for field, value in times.items()}, "Svarfrist": 5, "MolStat-ID": "", "Pris2026NOK": "", "Priskobling": "", "Svartid dager": days, "Svartid status": status, "Normstatus": norm})
    write_csv(output / "antall.csv", ANTALL_FIELDS, antall)
    write_csv(output / "resultater.csv", RESULT_FIELDS, resultater)
    summary = {"input_antall": len(raw_antall), "input_resultater": len(raw_resultater), "antall": len(antall), "resultater": len(resultater), "gyldige_svartider": sum(row["Svartid status"] == "Gyldig" for row in resultater), "innen_norm": sum(row["Normstatus"] == "Innen norm" for row in resultater), "ekskluderte_koder": [{"rapport": kind, "kode": code, "rader": number} for (kind, code), number in sorted(counts.items())]}
    (output / "kontroll.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def empty_template(output: Path) -> None:
    write_csv(output / "antall.csv", ANTALL_FIELDS, [])
    write_csv(output / "resultater.csv", RESULT_FIELDS, [])
