"""Python port of Hemato_Statistikk.R / Solide_Statistikk.R.

Reads the archived LVMS report exports (Windows-1252, semicolon,
``=T("...")`` wrapped), applies the exact same cleaning, classification,
extraction matching and turnaround computation as the R scripts, and
writes ``Prosessert/antall.csv`` and ``resultater.csv`` in the same
format Power BI already consumes.
"""

from __future__ import annotations

import csv
import re
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

RAW_ENCODING = "cp1252"
DELIMITER = ";"
OUTPUT_DATETIME_FORMAT = "%Y/%m/%d %H:%M:%S"

DATE_COLUMNS = (
    "Tidspunkt.prøvetaking",
    "Tidspunkt.opprettet",
    "Tidspunkt.analysebestilling",
    "Tidspunkt.analyseresultat",
    "Tidspunkt.godkjenning",
)

RESULTATER_COLUMNS = (
    "Materiale",
    "Analyse",
    "Nukleinsyre",
    "Rapportgruppe",
    "Tidspunkt.prøvetaking",
    "Tidspunkt.opprettet",
    "Tidspunkt.analysebestilling",
    "Tidspunkt.analyseresultat",
    "Tidspunkt.godkjenning",
    "Ekstraksjon.analysebestilling",
    "Ekstraksjon.ferdig",
    "Svarfrist",
)

# Solide export (Solide_Statistikk.R -> resultater_super2): 13 columns,
# no Nukleinsyre, keeps Ekstraksjon.Analyse and Starttid.svartid.
SOLIDE_RESULTATER_COLUMNS = (
    "Materiale",
    "Analyse",
    "Rapportgruppe",
    "Tidspunkt.prøvetaking",
    "Tidspunkt.opprettet",
    "Tidspunkt.analysebestilling",
    "Tidspunkt.analyseresultat",
    "Tidspunkt.godkjenning",
    "Ekstraksjon.Analyse",
    "Ekstraksjon.analysebestilling",
    "Ekstraksjon.ferdig",
    "Starttid.svartid",
    "Svarfrist",
)

ANTALL_COLUMNS = (
    "Analyse",
    "Tidspunkt.analysebestilling",
    "Nukleinsyre",
    "Rapportgruppe",
    "Maaned",
)

# Solide antall (antall_super2 = select(c(2, 5, 8, 9, 11))): Analyse,
# Tidspunkt.analysebestilling, Rapportgruppe, Svarfrist, Maaned.
SOLIDE_ANTALL_COLUMNS = (
    "Analyse",
    "Tidspunkt.analysebestilling",
    "Rapportgruppe",
    "Svarfrist",
    "Maaned",
)

_T_WRAPPER = re.compile(r'^=T\((.*)\)$')


def clean_text(value: object) -> str:
    """Strip quotes and the ``=T(...)`` wrapper exactly like R's clean_text."""
    text = "" if value is None else str(value)
    text = text.replace('"', "")
    match = _T_WRAPPER.match(text.strip())
    if match:
        text = match.group(1).replace('"', "")
    return text.strip()


def parse_tidspunkt(value: object) -> datetime | None:
    """Parse ``dd.mm.yyyy [hh:mm[:ss]]``; return None when absent/unparsable."""
    text = clean_text(value)
    if not text:
        return None
    for pattern in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def klassifiser_ekstraksjon(value: object) -> str:
    upper = clean_text(value).upper()
    if "RNA" in upper:
        return "RNA"
    if "DNA" in upper:
        return "DNA"
    if "APKOL" in upper or "FFPEKOL" in upper:
        return "DNA"
    return "Ukjent/generell"


def _normalize_header(row: Sequence[str]) -> list[str]:
    return [name.replace(" ", ".") for name in row]


def read_lvms_csv(path: Path) -> list[dict[str, str]]:
    """Read one raw LVMS export with cleaned text values."""
    with open(path, encoding=RAW_ENCODING, newline="") as handle:
        reader = csv.reader(handle, delimiter=DELIMITER)
        header = _normalize_header(next(reader))
        rows: list[dict[str, str]] = []
        for raw in reader:
            if not any(cell.strip() for cell in raw):
                continue
            rows.append(
                {
                    name: clean_text(raw[index]) if index < len(raw) else ""
                    for index, name in enumerate(header)
                }
            )
    return rows


def load_lookup(path: Path) -> dict[str, dict[str, str]]:
    """Read Analyse_lookup.xlsx (stdlib only) keyed by cleaned Analyse."""
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        try:
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{namespace}si"):
                shared.append(
                    "".join(
                        node.text or ""
                        for node in item.iter(f"{namespace}t")
                    )
                )
            sheet_names = [
                name
                for name in archive.namelist()
                if name.startswith("xl/worksheets/sheet")
            ]
            sheet_names.sort()
            sheet_root = ElementTree.fromstring(archive.read(sheet_names[0]))
        except KeyError:
            return {}
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target_map = {
            rel.get("Id"): rel.get("Target", "")
            for rel in rels.iter(f"{rel_ns}Relationship")
        }
        sheets = [
            (sheet.get("name"), target_map.get(sheet.get(f"{rel_ns}id"), ""))
            for sheet in workbook.iter(f"{namespace}sheet")
        ]
        first_target = sheets[0][1].lstrip("/") if sheets else ""
        if first_target and not first_target.startswith("xl/"):
            first_target = f"xl/{first_target}"
        if not first_target:
            first_target = sheet_names[0] if sheet_names else ""
        if not first_target:
            return {}
        sheet_root = ElementTree.fromstring(archive.read(first_target))

    def cell_text(cell: ElementTree.Element) -> str:
        value_node = cell.find(f"{namespace}v")
        if value_node is None or value_node.text is None:
            inline = cell.find(f"{namespace}is/{namespace}t")
            return inline.text if inline is not None and inline.text else ""
        if cell.get("t") == "s":
            return shared[int(value_node.text)]
        return value_node.text

    grid: list[list[str]] = []
    for row in sheet_root.iter(f"{namespace}row"):
        grid.append([cell_text(cell) for cell in row.findall(f"{namespace}c")])
    if not grid:
        return {}
    header = [clean_text(name) for name in grid[0]]
    lookup: dict[str, dict[str, str]] = {}
    for row in grid[1:]:
        record = {
            header[i]: clean_text(row[i]) if i < len(row) else ""
            for i in range(len(header))
        }
        key = record.get("Analyse", "")
        if key and key not in lookup:
            lookup[key] = record
    return lookup


def _fmt(dt: datetime | None) -> str:
    return dt.strftime(OUTPUT_DATETIME_FORMAT) if dt else ""


def build_antall(
    rows: Iterable[Mapping[str, str]],
    lookup: Mapping[str, Mapping[str, str]],
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in rows:
        analyse = clean_text(row.get("Analyse"))
        entry = lookup.get(analyse, {})
        opprettet = parse_tidspunkt(row.get("Tidspunkt.opprettet"))
        out.append(
            {
                # NB: kept as the original cleaned string, like the R output.
                "Analyse": analyse,
                "Tidspunkt.analysebestilling": clean_text(
                    row.get("Tidspunkt.analysebestilling")
                ),
                "Nukleinsyre": entry.get("Nukleinsyre", ""),
                "Rapportgruppe": entry.get("Rapportgruppe", ""),
                "Svarfrist": entry.get("Svarfrist", ""),
                "Maaned": str(opprettet.month) if opprettet else "",
            }
        )
    return out


def _best_extraction(
    sample_id: str,
    resultat_nukleinsyre: str,
    godkjenning: datetime | None,
    extractions: Sequence[Mapping[str, object]],
) -> dict[str, object] | None:
    """Pick the best candidate; input is pre-sorted finished-descending.

    Scanning in order and taking the first hit whose priority ties with the
    best possible outcome is safe because any later candidate has a strictly
    earlier ``ferdig`` — exactly R's tie-break.
    """
    if godkjenning is None:
        return None
    best: tuple[int, int, dict[str, object]] | None = None
    for index, extraction in enumerate(extractions):
        finished = extraction["ferdig"]
        assert isinstance(finished, datetime)
        if finished > godkjenning:
            continue
        nukleinsyre = str(extraction["nukleinsyre"])
        if resultat_nukleinsyre and nukleinsyre == resultat_nukleinsyre:
            priority = 1
            # cannot be beaten: priority 1 + latest finished (first in scan)
            best = (priority, -index, extraction)
            break
        elif nukleinsyre == "Ukjent/generell":
            priority = 2
        else:
            priority = 3
        candidate = (priority, -index, extraction)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        return None
    chosen = dict(best[2])
    chosen["status"] = {
        1: "Match på Sample.ID og Nukleinsyre",
        2: "Match på Sample.ID med generell/ukjent ekstraksjon",
        3: "Match på Sample.ID, men annen nukleinsyre",
    }[best[0]]
    return chosen


def build_resultater(
    result_rows: Iterable[Mapping[str, str]],
    extraction_rows: Iterable[Mapping[str, str]],
    lookup: Mapping[str, Mapping[str, str]],
) -> list[dict[str, str]]:
    extraction_index: dict[str, list[dict[str, object]]] = {}
    for row in extraction_rows:
        sample_id = clean_text(row.get("Sample.ID"))
        ferdig = parse_tidspunkt(row.get("Tidspunkt.analyseresultat"))
        if ferdig is None:
            continue  # candidates without a finished time can never match
        nukleinsyre = klassifiser_ekstraksjon(row.get("Analyse"))
        bucket = extraction_index.setdefault((sample_id, nukleinsyre), [])
        generic = extraction_index.setdefault((sample_id, "Ukjent/generell"), [])
        target = (
            generic
            if nukleinsyre == "Ukjent/generell"
            else bucket
        )
        target.append(
            {
                "analyse": clean_text(row.get("Analyse")),
                "nukleinsyre": nukleinsyre,
                "bestilling": parse_tidspunkt(
                    row.get("Tidspunkt.analysebestilling")
                ),
                "ferdig": ferdig,
                "ekstr_godkjenning": parse_tidspunkt(
                    row.get("Tidspunkt.godkjenning")
                ),
            }
        )
        if nukleinsyre != "Ukjent/generell":
            # also visible to priority-2 lookups via the per-sample generic list
            pass

    by_sample: dict[str, list[dict[str, object]]] = {}
    for (sample_id, _nucleic), rows in extraction_index.items():
        by_sample.setdefault(sample_id, []).extend(rows)
    extractions_by_sample = by_sample

    # Pre-sort each sample's extractions once: finished descending. The
    # per-sample candidate scan then short-circuits on the first hit that
    # satisfies the deadline, because later candidates can only be worse.
    for rows in extractions_by_sample.values():
        rows.sort(key=lambda e: e["ferdig"], reverse=True)

    out: list[dict[str, str]] = []
    for row in result_rows:
        analyse = clean_text(row.get("Analyse"))
        if analyse.upper().startswith("EKSTRA"):
            continue
        entry = lookup.get(analyse, {})
        sample_id = clean_text(row.get("Sample.ID"))
        materiale = clean_text(row.get("Materiale"))
        nukleinsyre = entry.get("Nukleinsyre", "")
        provetakining = parse_tidspunkt(row.get("Tidspunkt.prøvetaking"))
        opprettet = parse_tidspunkt(row.get("Tidspunkt.opprettet"))
        bestilling = parse_tidspunkt(row.get("Tidspunkt.analysebestilling"))
        analyseresultat = parse_tidspunkt(row.get("Tidspunkt.analyseresultat"))
        godkjenning = parse_tidspunkt(row.get("Tidspunkt.godkjenning"))

        chosen = _best_extraction(
            sample_id,
            nukleinsyre,
            godkjenning,
            extractions_by_sample.get(sample_id, []),
        )

        if chosen is None:
            ekstr_bestilling = None
            ekstr_ferdig = None
            match_status = (
                "Ingen gyldig ekstraksjon funnet før resultatgodkjenning"
            )
        else:
            ekstr_bestilling = chosen["bestilling"]
            ekstr_ferdig = chosen["ferdig"]
            assert isinstance(ekstr_bestilling, datetime) or ekstr_bestilling is None
            assert isinstance(ekstr_ferdig, datetime) or ekstr_ferdig is None
            match_status = str(chosen["status"])

        if bestilling is not None and ekstr_ferdig is not None:
            starttid = max(bestilling, ekstr_ferdig)
        elif bestilling is not None:
            starttid = bestilling
        else:
            starttid = ekstr_ferdig

        if bestilling is None and ekstr_ferdig is None:
            startgrunnlag = "Mangler analysebestilling og ekstraksjon"
        elif ekstr_ferdig is None:
            startgrunnlag = "Analysebestilling - ingen ekstraksjon funnet"
        elif bestilling is None:
            startgrunnlag = "Ekstraksjon ferdig - mangler analysebestilling"
        elif bestilling > ekstr_ferdig:
            startgrunnlag = "Analysebestilling"
        elif bestilling < ekstr_ferdig:
            startgrunnlag = "Ekstraksjon ferdig"
        else:
            startgrunnlag = "Analysebestilling og ekstraksjon ferdig lik tid"

        svartid_timer: float | None = None
        if godkjenning is not None and starttid is not None:
            svartid_timer = (godkjenning - starttid).total_seconds() / 3600
        if godkjenning is None:
            svartid_status = "Mangler resultatgodkjenning"
        elif starttid is None:
            svartid_status = "Mangler starttid"
        elif svartid_timer is not None and svartid_timer < 0:
            svartid_status = "Negativ svartid - sjekk data"
        else:
            svartid_status = "OK"

        out.append(
            {
                "Materiale": materiale,
                "Analyse": analyse,
                "Nukleinsyre": nukleinsyre,
                "Rapportgruppe": entry.get("Rapportgruppe", ""),
                "Tidspunkt.prøvetaking": _fmt(provetakining),
                "Tidspunkt.opprettet": _fmt(opprettet),
                "Tidspunkt.analysebestilling": _fmt(bestilling),
                "Tidspunkt.analyseresultat": _fmt(analyseresultat),
                "Tidspunkt.godkjenning": _fmt(godkjenning),
                "Ekstraksjon.analysebestilling": _fmt(ekstr_bestilling),
                "Ekstraksjon.ferdig": _fmt(ekstr_ferdig),
                "Svarfrist": entry.get("Svarfrist", ""),
                "_svartid_status": svartid_status,
                "_startgrunnlag": startgrunnlag,
            }
        )
    return out


def _best_extraction_solide(
    godkjenning: datetime | None,
    extractions: Sequence[Mapping[str, object]],
) -> dict[str, object] | None:
    """Solide rule (Solide_Statistikk.R §8-9): latest finished extraction
    on the same Sample.ID that finished before the result approval.

    No nucleic-acid priority - input is pre-sorted finished-descending,
    so the first candidate meeting the deadline is the answer.
    """
    if godkjenning is None:
        return None
    for extraction in extractions:
        finished = extraction["ferdig"]
        assert isinstance(finished, datetime)
        if finished <= godkjenning:
            return dict(extraction)
    return None


def build_resultater_solide(
    result_rows: Iterable[Mapping[str, str]],
    extraction_rows: Iterable[Mapping[str, str]],
    lookup: Mapping[str, Mapping[str, str]],
) -> list[dict[str, str]]:
    """Solide resultater: 13-column export with Starttid.svartid."""
    by_sample: dict[str, list[dict[str, object]]] = {}
    for row in extraction_rows:
        sample_id = clean_text(row.get("Sample.ID"))
        ferdig = parse_tidspunkt(row.get("Tidspunkt.analyseresultat"))
        if ferdig is None:
            continue  # candidates without a finished time can never match
        by_sample.setdefault(sample_id, []).append(
            {
                "analyse": clean_text(row.get("Analyse")),
                "bestilling": parse_tidspunkt(
                    row.get("Tidspunkt.analysebestilling")
                ),
                "ferdig": ferdig,
            }
        )
    for rows in by_sample.values():
        rows.sort(key=lambda e: e["ferdig"], reverse=True)

    out: list[dict[str, str]] = []
    for row in result_rows:
        analyse = clean_text(row.get("Analyse"))
        entry = lookup.get(analyse, {})
        sample_id = clean_text(row.get("Sample.ID"))
        materiale = clean_text(row.get("Materiale"))
        bestilling = parse_tidspunkt(row.get("Tidspunkt.analysebestilling"))
        godkjenning = parse_tidspunkt(row.get("Tidspunkt.godkjenning"))

        chosen = _best_extraction_solide(
            godkjenning, by_sample.get(sample_id, [])
        )
        if chosen is None:
            ekstr_analyse = ""
            ekstr_bestilling = None
            ekstr_ferdig = None
        else:
            ekstr_analyse = str(chosen["analyse"])
            ekstr_bestilling = chosen["bestilling"]
            ekstr_ferdig = chosen["ferdig"]
            assert isinstance(ekstr_bestilling, datetime) or ekstr_bestilling is None
            assert isinstance(ekstr_ferdig, datetime) or ekstr_ferdig is None

        if bestilling is not None and ekstr_ferdig is not None:
            starttid = max(bestilling, ekstr_ferdig)
        elif bestilling is not None:
            starttid = bestilling
        else:
            starttid = ekstr_ferdig

        out.append(
            {
                "Materiale": materiale,
                "Analyse": analyse,
                "Rapportgruppe": entry.get("Rapportgruppe", ""),
                "Tidspunkt.prøvetaking": _fmt(
                    parse_tidspunkt(row.get("Tidspunkt.prøvetaking"))
                ),
                "Tidspunkt.opprettet": _fmt(
                    parse_tidspunkt(row.get("Tidspunkt.opprettet"))
                ),
                "Tidspunkt.analysebestilling": _fmt(bestilling),
                "Tidspunkt.analyseresultat": _fmt(
                    parse_tidspunkt(row.get("Tidspunkt.analyseresultat"))
                ),
                "Tidspunkt.godkjenning": _fmt(godkjenning),
                "Ekstraksjon.Analyse": ekstr_analyse,
                "Ekstraksjon.analysebestilling": _fmt(ekstr_bestilling),
                "Ekstraksjon.ferdig": _fmt(ekstr_ferdig),
                "Starttid.svartid": _fmt(starttid),
                "Svarfrist": entry.get("Svarfrist", ""),
            }
        )
    return out


def write_excel_csv2(
    rows: Iterable[Mapping[str, str]],
    path: Path,
    columns: Sequence[str],
) -> None:
    """Write semicolon-separated UTF-8 BOM CSV quoting every field."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=DELIMITER, quoting=csv.QUOTE_ALL)
        writer.writerow(list(columns))
        for row in rows:
            writer.writerow(["" if row.get(name) is None else row[name] for name in columns])


def process_reports(
    antall_path: Path,
    resultater_path: Path,
    ekstraksjon_path: Path,
    lookup_path: Path,
    output_dir: Path,
    *,
    profile: str = "hemato",
) -> dict[str, int]:
    """Full pipeline over one unit's reports; returns exported row counts.

    ``profile`` selects the export dialect: ``"hemato"`` (default, the
    original 12/5-column Hemato_Statistikk.R layout) or ``"solide"``
    (the 13/5-column Solide_Statistikk.R layout with its own simpler
    extraction rule).
    """
    lookup = load_lookup(lookup_path)
    antall = build_antall(read_lvms_csv(antall_path), lookup)
    if profile == "solide":
        resultater = build_resultater_solide(
            read_lvms_csv(resultater_path),
            read_lvms_csv(ekstraksjon_path),
            lookup,
        )
        antall_columns = SOLIDE_ANTALL_COLUMNS
        resultater_columns = SOLIDE_RESULTATER_COLUMNS
    else:
        resultater = build_resultater(
            read_lvms_csv(resultater_path),
            read_lvms_csv(ekstraksjon_path),
            lookup,
        )
        antall_columns = ANTALL_COLUMNS
        resultater_columns = RESULTATER_COLUMNS
    write_excel_csv2(antall, output_dir / "antall.csv", antall_columns)
    write_excel_csv2(
        resultater, output_dir / "resultater.csv", resultater_columns
    )
    return {"antall": len(antall), "resultater": len(resultater)}

