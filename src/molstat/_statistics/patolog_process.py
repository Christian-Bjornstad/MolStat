"""Monthly pathology process counts from the aggregate LVMS report."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
import re


FIELDS = (
    "Maaned", "Profil", "Lab", "Prosesskode", "Prosessgruppe",
    "AntallProver", "AntallBlokker", "AntallGlass", "UttrekkTom",
)
GROUPS = {
    "BEN-BLØTVEV": "Ben og bløtvev",
    "GYN": "Gyn",
    "MAMMA": "Mamma",
    "THYREOIDEA": "Thyroidea",
    "URO": "Uro",
}
REPORT_STEMS = ("PAT-PROSESS-CURRENT-OU", "PAT-PROSESS-PREVIOUS-OU")
_ARCHIVE = re.compile(r"__(\d{4}-\d{2}-\d{2})__(\d{4}-\d{2}-\d{2})(?:__r(\d+))?\.csv$")
_LVMS_TEXT = re.compile(r'^=T\("(.*)"\)$')


def _text(value: str | None) -> str:
    value = (value or "").strip()
    match = _LVMS_TEXT.fullmatch(value)
    if match:
        return match.group(1)
    if value.startswith(("=", "+", "-", "@")):
        raise ValueError("Ugyldig tekstfelt i patolograpporten.")
    return value


def _count(value: str | None) -> int:
    value = (value or "").strip().replace("\u00a0", "").replace(" ", "")
    if not value:
        return 0
    if not value.isdecimal():
        raise ValueError("Ugyldig antall i patolograpporten.")
    return int(value)


def _latest_by_month(archive_dir: Path) -> dict[date, tuple[Path, date]]:
    selected: dict[date, tuple[tuple[date, int, int], Path]] = {}
    for stem in REPORT_STEMS:
        for path in archive_dir.glob(f"{stem}__*.csv"):
            match = _ARCHIVE.search(path.name)
            if match is None:
                continue
            start, end = date.fromisoformat(match.group(1)), date.fromisoformat(match.group(2))
            if start.day != 1 or start.year != end.year or start.month != end.month:
                continue
            key = (end, path.stat().st_mtime_ns, int(match.group(3) or 1))
            month = start.replace(day=1)
            if month not in selected or key > selected[month][0]:
                selected[month] = key, path
    return {month: (path, key[0]) for month, (key, path) in selected.items()}


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="cp1252", newline="") as stream:
        lines = stream.readlines()
    if lines and lines[0].strip().startswith("Totalt antall registrerte rekvisisjoner"):
        lines = lines[1:]
    reader = csv.DictReader(lines, delimiter=";")
    required = {"Profil", "Lab", "Distinct_SampleId", "Distinct_Ant. blokker", "Distinct_Ant. glass"}
    if not required <= set(reader.fieldnames or ()) or not ({"s_w_labprocess", "s_w_labprosess"} & set(reader.fieldnames or ())):
        raise ValueError("Patolograpporten mangler forventede kolonner.")
    return [row for row in reader if row.get("Lab") and row.get("Profil")]


def process(archive_dir: Path, output_path: Path) -> int:
    """Keep the newest snapshot per month; sum LVMS distinct counts by source row."""
    rows: list[dict[str, object]] = []
    for month, (path, end) in sorted(_latest_by_month(archive_dir).items()):
        for raw in _read(path):
            process_code = _text(raw.get("s_w_labprocess") or raw.get("s_w_labprosess"))
            lab = _text(raw["Lab"])
            if process_code == "HEMATO":
                group = "Hemato Flow" if lab == "OU-PAT-SPES-RA" else "Hemato uten Flow"
            else:
                group = GROUPS.get(process_code)
            if group is None:
                continue
            rows.append({
                "Maaned": month.isoformat(),
                "Profil": _text(raw["Profil"]),
                "Lab": lab,
                "Prosesskode": process_code,
                "Prosessgruppe": group,
                "AntallProver": _count(raw["Distinct_SampleId"]),
                "AntallBlokker": _count(raw["Distinct_Ant. blokker"]),
                "AntallGlass": _count(raw["Distinct_Ant. glass"]),
                "UttrekkTom": end.isoformat(),
            })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
