"""Derive PRE activity and turnaround data from one LVMS results export."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from molstat._statistics.processing import read_lvms_csv


ANTALL_FIELDS = ("Analyse", "Tidspunkt.analysebestilling", "Rapportgruppe", "Svarfrist", "Maaned")
RESULT_FIELDS = ("Materiale", "Analyse", "Rapportgruppe", "Tidspunkt.prøvetaking", "Tidspunkt.opprettet", "Tidspunkt.analysebestilling", "Tidspunkt.analyseresultat", "Tidspunkt.godkjenning", "Svarfrist", "MolStat-ID", "Pris2026NOK", "Priskobling", "Aktivitetstype", "NormProsess", "NormTotalt", "Prosessdager", "Totaldager", "Prosessstatus", "Totalstatus", "Prosessnormstatus", "Totalnormstatus")


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
    raise ValueError(f"Invalid PRE timestamp: {value!r}")


def display(value: datetime | None) -> str:
    return value.strftime("%Y/%m/%d %H:%M:%S") if value else ""


def elapsed(start: datetime | None, end: datetime | None, norm: str) -> tuple[str, str, str]:
    if start is None or end is None:
        return "", "Mangler tidspunkt", "Ikke beregnet"
    days = (end - start).total_seconds() / 86400
    if days < 0:
        return "", "Negativ tid", "Ikke beregnet"
    if days > 365:
        return "", "Over 365 dager", "Ikke beregnet"
    status = "Innen norm" if norm and days <= float(norm) else "Over norm" if norm else "Ingen norm"
    return f"{days:.10f}", "Gyldig", status


def first_event(events: list[dict], kind: str) -> datetime | None:
    times = [event["result"] for event in events if event["type"] == kind and event["result"]]
    return min(times) if times else None


def process(source: Path, output: Path, lookup_path: Path) -> dict:
    with lookup_path.open(encoding="utf-8-sig", newline="") as handle:
        lookup = {row["Analyse"]: row for row in csv.DictReader(handle, delimiter=";")}
    sources = sorted(source.glob("*.csv")) if source.is_dir() else [source]
    if not sources:
        raise ValueError(f"No PRE results CSV files found in {source}")
    raw = [row for path in sources for row in read_lvms_csv(path)]
    by_sample = defaultdict(list)
    excluded = Counter()
    for row in raw:
        code = row.get("Analyse", "").strip()
        if code not in lookup:
            excluded[code] += 1
            continue
        sample_id = row.get("Sample.ID", "").strip()
        if not sample_id:
            excluded["<mangler Sample ID>"] += 1
            continue
        info = lookup[code]
        by_sample[sample_id].append({"code": code, "type": info["Aktivitetstype"], "row": row, "created": parse_time(row.get("Tidspunkt.opprettet")), "result": parse_time(row.get("Tidspunkt.analyseresultat")), "approved": parse_time(row.get("Tidspunkt.godkjenning"))})
    output_rows = []
    duplicates = 0
    for events in by_sample.values():
        created_dates = [event["created"] for event in events if event["created"]]
        created = min(created_dates) if created_dates else None
        received = first_event(events, "ValgEkstraksjon")
        pretreated = first_event(events, "UtførtForbehandling")
        per_code = {}
        for event in events:
            current = per_code.get(event["code"])
            if current is None or (event["result"] or datetime.max) < (current["result"] or datetime.max):
                per_code[event["code"]] = event
        duplicates += len(events) - len(per_code)
        for event in per_code.values():
            info = lookup[event["code"]]
            kind = event["type"]
            start = received if kind == "UtførtForbehandling" else pretreated if kind in ("UtførtEkstraksjon", "Videresendt") else None
            process_days, process_status, process_norm = elapsed(start, event["result"], info["NormProsess"])
            if not info["NormProsess"] or kind not in ("UtførtForbehandling", "UtførtEkstraksjon", "Videresendt"):
                process_days, process_status, process_norm = "", "Ikke definert", "Ikke beregnet"
            total_days, total_status, total_norm = elapsed(created, event["result"], info["NormTotalt"])
            if not info["NormTotalt"]:
                total_days, total_status, total_norm = "", "Ikke definert", "Ikke beregnet"
            output_rows.append({"Materiale": "", "Analyse": event["code"], "Rapportgruppe": info["Rapportgruppe"], "Tidspunkt.prøvetaking": "", "Tidspunkt.opprettet": display(created), "Tidspunkt.analysebestilling": "", "Tidspunkt.analyseresultat": display(event["result"]), "Tidspunkt.godkjenning": display(event["approved"]), "Svarfrist": info["NormTotalt"], "MolStat-ID": "", "Pris2026NOK": "", "Priskobling": "", "Aktivitetstype": kind, "NormProsess": info["NormProsess"], "NormTotalt": info["NormTotalt"], "Prosessdager": process_days, "Totaldager": total_days, "Prosessstatus": process_status, "Totalstatus": total_status, "Prosessnormstatus": process_norm, "Totalnormstatus": total_norm})
    write_csv(output / "antall.csv", ANTALL_FIELDS, [])  # Compatibility table; there is no ANTALL export.
    write_csv(output / "resultater.csv", RESULT_FIELDS, output_rows)
    summary = {"input_files": len(sources), "input_rows": len(raw), "unique_samples_in_input": len(by_sample), "activity_rows": len(output_rows), "duplicate_sample_code_rows_collapsed": duplicates, "excluded_codes": dict(excluded), "valid_process": sum(row["Prosessstatus"] == "Gyldig" for row in output_rows), "valid_total": sum(row["Totalstatus"] == "Gyldig" for row in output_rows)}
    (output / "kontroll.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def empty_template(output: Path) -> None:
    write_csv(output / "antall.csv", ANTALL_FIELDS, [])
    write_csv(output / "resultater.csv", RESULT_FIELDS, [])
