"""Private doctor-level facts from monthly LVMS production and macro exports."""

from __future__ import annotations

from collections import defaultdict
import csv
from datetime import date, datetime, timedelta
from pathlib import Path

from .lege_lookup import load_lege_lookup
from .patolog_process import _text, _ARCHIVE


PRODUCTION_STEM = "PAT-EGEN-PRODUKSJON-OU"
MACRO_STEM = "PAT-EGEN-MAKRO-OU"
FACT_FIELDS = ("SampleID", "Brukernavn", "Rolle", "Profil", "Prosess", "GodkjentTid",
               "SisteFerdigFarget", "GodkjentDato", "SvartidDager", "Tidsstatus",
               "MakroTid", "MakroSvartidDager")
MACRO_FIELDS = ("SampleID", "Brukernavn", "Prioritet", "Prosess", "MakroTid", "MakroDato")
SOURCE_FIELDS = {
    "production": {"Antall prøver", "Godkj. type", "Profil", "Prosess", "Godkjent av", "Ferdig farget", "Godkj. når"},
    "macro": {"SampleID", "Prioritet", "Prosess", "Makro når", "Makro av"},
}


def _read(path: Path, role: str):
    with path.open(encoding="cp1252", newline="") as stream:
        title = next(stream, "")
        if not title:
            raise ValueError("Tom LVMS-legerapport.")
        reader = csv.DictReader(stream, delimiter=";")
        if not SOURCE_FIELDS[role] <= set(reader.fieldnames or ()):
            raise ValueError("LVMS-legerapporten mangler forventede kolonner.")
        for row in reader:
            if None in row:
                raise ValueError("LVMS-legerapporten har en ugyldig rad.")
            yield row


def validate_source(path: Path, role: str) -> None:
    next(_read(path, role), None)


def _latest(archive_dir: Path, stem: str) -> tuple[Path, ...]:
    selected: dict[date, tuple[date, int, Path]] = {}
    for path in archive_dir.glob(f"{stem}__*.csv"):
        match = _ARCHIVE.search(path.name)
        if match is None:
            continue
        start, end = date.fromisoformat(match.group(1)), date.fromisoformat(match.group(2))
        if start.day != 1 or (start.year, start.month) != (end.year, end.month):
            continue
        key = (end, path.stat().st_mtime_ns, path)
        if start not in selected or key[:2] > selected[start][:2]:
            selected[start] = key
    return tuple(item[2] for _, item in sorted(selected.items()))


def _moment(value: str) -> datetime | None:
    value = _text(value)
    if not value:
        return None
    for pattern in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    raise ValueError("Ugyldig dato i LVMS-legerapport.")


def _stamp(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def _write(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def process(archive_dir: Path, lookup_path: Path, output_dir: Path) -> dict[str, Path]:
    doctors = load_lege_lookup(lookup_path)
    users = {row["Brukernavn"] for row in doctors}
    macro_times: dict[str, list[datetime]] = defaultdict(list)
    macro_rows: dict[tuple[str, ...], dict[str, object]] = {}
    for path in _latest(archive_dir, MACRO_STEM):
        for raw in _read(path, "macro"):
            sample = _text(raw["SampleID"])
            user = _text(raw["Makro av"]).upper()
            when = _moment(raw["Makro når"])
            if not sample or when is None:
                continue
            macro_times[sample].append(when)
            if user not in users:
                continue
            priority, process_code = _text(raw["Prioritet"]), _text(raw["Prosess"])
            key = (sample, user, priority, process_code, _stamp(when))
            macro_rows[key] = {"SampleID": sample, "Brukernavn": user,
                               "Prioritet": priority, "Prosess": process_code,
                               "MakroTid": _stamp(when), "MakroDato": when.date().isoformat()}
    for times in macro_times.values():
        times.sort()

    production: dict[tuple[str, ...], tuple[datetime | None, datetime]] = {}
    for path in _latest(archive_dir, PRODUCTION_STEM):
        for raw in _read(path, "production"):
            sample = _text(raw["Antall prøver"])
            user = _text(raw["Godkjent av"]).upper()
            approved = _moment(raw["Godkj. når"])
            if not sample or user not in users or approved is None:
                continue
            key = (sample, user, _text(raw["Godkj. type"]), _text(raw["Profil"]),
                   _text(raw["Prosess"]), _stamp(approved))
            stain = _moment(raw["Ferdig farget"])
            previous = production.get(key)
            if previous is None or (stain is not None and (previous[0] is None or stain > previous[0])):
                production[key] = stain, approved

    facts: list[dict[str, object]] = []
    for key, (stain, approved) in sorted(production.items()):
        sample = key[0]
        macro = max((value for value in macro_times.get(sample, ()) if value <= approved), default=None)
        days = (approved - stain).total_seconds() / 86400 if stain else None
        facts.append(dict(zip(("SampleID", "Brukernavn", "Rolle", "Profil", "Prosess", "GodkjentTid"), key),
                          SisteFerdigFarget=_stamp(stain), GodkjentDato=approved.date().isoformat(),
                          SvartidDager=days if days is not None and days >= 0 else "",
                          Tidsstatus="Mangler tidspunkt" if days is None else ("Negativt intervall" if days < 0 else "Gyldig"),
                          MakroTid=_stamp(macro),
                          MakroSvartidDager=(approved - macro).total_seconds() / 86400 if macro else ""))
    result = {"FactPatologRolle.csv": output_dir / "FactPatologRolle.csv",
              "FactMakro.csv": output_dir / "FactMakro.csv",
              "DimPatolog.csv": output_dir / "DimPatolog.csv",
              "DimDato.csv": output_dir / "DimDato.csv"}
    _write(result["FactPatologRolle.csv"], FACT_FIELDS, facts)
    _write(result["FactMakro.csv"], MACRO_FIELDS, list(macro_rows.values()))
    _write(result["DimPatolog.csv"], ("Brukernavn", "Navn", "Faggruppe"), doctors)
    months = ("januar", "februar", "mars", "april", "mai", "juni", "juli",
              "august", "september", "oktober", "november", "desember")
    start, end = date(2024, 1, 1), date(datetime.now().year + 2, 1, 1)
    calendar_rows: list[dict[str, object]] = []
    day = start
    while day < end:
        iso_year, iso_week, _ = day.isocalendar()
        calendar_rows.append({
            "Dato": day.isoformat(), "År": day.year, "MånedNr": day.month,
            "Måned": months[day.month - 1], "ÅrMåned": day.strftime("%Y-%m"),
            "ÅrMånedSort": day.year * 100 + day.month, "Uke": iso_week,
            "Ukeår": iso_year, "ÅrUke": f"{iso_year}-U{iso_week:02d}",
            "UkeStart": (day - timedelta(days=day.weekday())).isoformat(),
            "ÅrUkeSort": iso_year * 100 + iso_week,
        })
        day += timedelta(days=1)
    _write(result["DimDato.csv"], tuple(calendar_rows[0]), calendar_rows)
    return result
