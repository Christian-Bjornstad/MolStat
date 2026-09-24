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
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        if not REQUIRED[profile] <= set(reader.fieldnames or ()):
            raise ValueError(f"Lookup-filen for {profile} mangler nødvendige kolonner.")
        codes = [row["Analyse"].strip() for row in reader]
    if len(codes) != len(set(codes)) or set(codes) != expected_codes:
        raise ValueError(f"Lookup-filen for {profile} stemmer ikke med LVMS-kodelisten.")
