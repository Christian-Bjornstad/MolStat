"""Validate the CSV lookups used by FLOW, FISH and PRE processors."""

from __future__ import annotations

import csv
from pathlib import Path


REQUIRED = {
    "flow": {"Analyse", "Analysenavn", "Rapportgruppe", "Svarfrist", "Pris2026NOK", "Priskobling"},
    "fish": {"Analyse", "Analysenavn", "Rapportgruppe", "Svarfrist", "Svartidstype"},
    "pre": {"Analyse", "Analysenavn", "Rapportgruppe", "Aktivitetstype", "NormProsess", "NormTotalt"},
}


def default_lookup_path(profile: str) -> Path:
    if profile not in REQUIRED:
        raise ValueError(f"Unknown specialized profile: {profile}")
    return Path(__file__).resolve().parents[1] / "defaults" / "lookups" / f"{profile}.csv"


def validate_lookup(path: Path, profile: str, expected_codes: set[str]) -> None:
    if profile not in REQUIRED:
        raise ValueError(f"Unknown specialized profile: {profile}")
    codes: list[str] = []
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";", strict=True)
            headers = reader.fieldnames or ()
            if not REQUIRED[profile] <= set(headers):
                raise ValueError(f"Lookup-filen for {profile} mangler nødvendige kolonner.")
            if len(headers) != len(set(headers)) or any(not name.strip() for name in headers):
                raise ValueError(f"Lookup-filen for {profile} har tomme eller duplikate kolonnenavn.")
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"Lookup-filen for {profile} har feil antall felt på rad {reader.line_num}.")
                if not any(value.strip() for value in row.values()):
                    continue
                code = row["Analyse"]
                # The processors use the source codes as exact dictionary keys.
                if not code or code != code.strip():
                    raise ValueError(f"Lookup-filen for {profile} har tom analysekode eller ekstra mellomrom på rad {reader.line_num}.")
                codes.append(code)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValueError(f"Lookup-filen for {profile} kunne ikke leses som en semikolonseparert UTF-8 CSV-fil.") from exc
    if not codes or len(codes) != len(set(codes)) or set(codes) != expected_codes:
        raise ValueError(f"Lookup-filen for {profile} stemmer ikke med LVMS-kodelisten.")
