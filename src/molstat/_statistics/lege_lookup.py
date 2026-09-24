"""Validate the pathologist roster used by the doctor-level report."""

from __future__ import annotations

import csv
from pathlib import Path
import re


_USERNAME = re.compile(r"[A-Za-z0-9._-]{1,80}")
_COLUMNS = ("Brukernavn", "Navn", "Faggruppe")


def validate_lege_lookup(path: Path) -> int:
    """Accept the supplied comma CSV and exported semicolon CSV, without rewriting it."""
    if path.suffix.lower() != ".csv" or path.stat().st_size > 1_000_000:
        raise ValueError("Legeregisteret må være en CSV-fil under 1 MB.")
    raw = path.read_bytes()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp1252")
    first_line = content.splitlines()[0] if content.splitlines() else ""
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.DictReader(content.splitlines(), delimiter=delimiter)
    if tuple(reader.fieldnames or ()) != _COLUMNS:
        raise ValueError("Legeregisteret må ha kolonnene Brukernavn, Navn og Faggruppe.")
    seen: set[str] = set()
    count = 0
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Legeregisteret har en ugyldig rad.")
        username = row["Brukernavn"].strip().upper()
        name = row["Navn"].strip()
        group = row["Faggruppe"].strip()
        if (not _USERNAME.fullmatch(username) or username in seen or not name or not group
                or any(value.startswith(("=", "+", "-", "@")) for value in (name, group))):
            raise ValueError("Legeregisteret har tomme, dupliserte eller ugyldige verdier.")
        seen.add(username)
        count += 1
        if count > 500:
            raise ValueError("Legeregisteret har for mange brukere.")
    if count == 0:
        raise ValueError("Legeregisteret er tomt.")
    return count
