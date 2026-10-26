"""Process Hemato and Solide statistics from archived LVMS reports.

Reads the archived LVMS report exports (Windows-1252, semicolon,
``=T("...")`` wrapped). Hemato retains the legacy extraction rules;
Solide exports method selection separately from extraction completion.
Power BI supplies groups and deadlines from the analysis lookup.
"""

from __future__ import annotations

import csv
import re
from .selection import AnalysisSelection, codes_for_report
from .lvms_csv import read_lvms_rows

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path


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
    "MolStat-ID",
)

# Keep legacy field order; append explicit selection/provenance fields.
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
    "MolStat-ID",
    "Ekstraksjon.valgt",
    "Ekstraksjon.metode",
    "Ekstraksjon.status",
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
        reader = read_lvms_rows(handle)
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
            best = (priority, index, extraction)
            break
        elif nukleinsyre == "Ukjent/generell":
            priority = 2
        else:
            priority = 3
        candidate = (priority, index, extraction)
        if best is None or candidate[:2] < best[:2]:
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
    *,
    molstat_ids: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    require_molstat_id = molstat_ids is not None
    resolved_ids = molstat_ids or {}
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
        molstat_id = resolved_ids.get(sample_id.upper(), "")
        if require_molstat_id and not molstat_id:
            raise ValueError("En resultatlinje kunne ikke kobles til MolStat-ID.")
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
                "MolStat-ID": molstat_id,
                "_svartid_status": svartid_status,
                "_startgrunnlag": startgrunnlag,
            }
        )
    return out


SOLIDE_PRE_CODES = frozenset({
    "MYRIAD-OU", "KRAS-VAR-OU", "NRASBRAF-VAR-OU", "MSI-OU",
    "GENEFUSION-OU", "EGFR-VAR-OU",
})


def _best_extraction_solide(
    godkjenning: datetime | None,
    extractions: Sequence[Mapping[str, object]],
) -> dict[str, object] | None:
    """Preserve the original Solide completion rule, sorted latest first.

    Completion is the extraction row's result timestamp, bounded by final
    analysis approval. It is not the extraction row's approval timestamp.
    """
    if godkjenning is None:
        return None
    for extraction in extractions:
        if extraction["ferdig"] <= godkjenning:
            return dict(extraction)
    return None


def build_resultater_solide(
    result_rows: Iterable[Mapping[str, str]],
    extraction_rows: Iterable[Mapping[str, str]],
    lookup: Mapping[str, Mapping[str, str]],
    *,
    molstat_ids: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    """Export method selection alongside the original extraction completion."""
    require_molstat_id = molstat_ids is not None
    resolved_ids = molstat_ids or {}
    by_sample: dict[str, list[dict[str, object]]] = {}
    selections: dict[str, list[dict[str, object]]] = {}
    for row in extraction_rows:
        sample_id = clean_text(row.get("Sample.ID")).upper()
        method = clean_text(row.get("Analyseresultat"))
        selected = parse_tidspunkt(row.get("Tidspunkt.analyseresultat"))
        if not sample_id or selected is None:
            continue
        # This is the original completion candidate pool, including its ordering.
        by_sample.setdefault(sample_id, []).append({
            "analyse": clean_text(row.get("Analyse")),
            "bestilling": parse_tidspunkt(row.get("Tidspunkt.analysebestilling")),
            "ferdig": selected,
        })
        if (clean_text(row.get("Analyse")).upper() != "EKSTRAKSJON-OU"
                or any(marker in method.casefold() for marker in
                    ("ikke utført", "ikke aktuell", "kansellert")) or not re.search(
                    r"dna|rna|maxwell|genexus|geneuxus|recover|ez1|kolonne|qia", method, re.I)):
            continue
        selections.setdefault(sample_id, []).append({"metode": method, "valgt": selected})
    for rows in by_sample.values():
        rows.sort(key=lambda e: e["ferdig"], reverse=True)
    for rows in selections.values():
        rows.sort(key=lambda e: e["valgt"], reverse=True)

    out: list[dict[str, str]] = []
    for row in result_rows:
        analyse = clean_text(row.get("Analyse"))
        if analyse.upper() in SOLIDE_PRE_CODES:
            continue
        entry = lookup.get(analyse, {})
        sample_id = clean_text(row.get("Sample.ID")).upper()
        molstat_id = resolved_ids.get(sample_id.upper(), "")
        if require_molstat_id and not molstat_id:
            raise ValueError("En resultatlinje kunne ikke kobles til MolStat-ID.")
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

        resultat_tid = parse_tidspunkt(row.get("Tidspunkt.analyseresultat"))
        selection_limit = min(ekstr_ferdig, resultat_tid) if ekstr_ferdig and resultat_tid else resultat_tid
        selection = next((e for e in selections.get(sample_id, [])
                          if selection_limit is not None and e["valgt"] <= selection_limit), None)
        ekstr_valgt = selection["valgt"] if selection else None
        ekstr_metode = str(selection["metode"]) if selection else ""
        if selection is None:
            extraction_status = "Mangler metodevalg"
        elif ekstr_ferdig is None:
            extraction_status = "Mangler ekstraksjonsslutt"
        elif ekstr_ferdig < ekstr_valgt:
            extraction_status = "Ekstraksjon ferdig før metodevalg"
        elif ekstr_ferdig > resultat_tid:
            extraction_status = "Ekstraksjon ferdig etter analyseresultat"
        else:
            extraction_status = "OK"
        starttid = (ekstr_ferdig if ekstr_ferdig is not None and resultat_tid is not None
                    and ekstr_ferdig <= resultat_tid else None)

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
                "MolStat-ID": molstat_id,
                "Ekstraksjon.valgt": _fmt(ekstr_valgt),
                "Ekstraksjon.metode": ekstr_metode,
                "Ekstraksjon.status": extraction_status,
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
    analysis_codes: AnalysisSelection,
    output_dir: Path,
    *,
    profile: str = "hemato",
    molstat_ids: Mapping[str, str] | None = None,
) -> dict[str, int]:
    """Full pipeline over one unit's reports; returns exported row counts.

    ``profile`` selects Hemato's legacy fields or Solide's explicit
    method-selection/approval fields. Metadata stays in Power BI's lookup.
    """
    lookup = {}
    ordered_codes = codes_for_report(analysis_codes, "antall")
    result_codes = codes_for_report(analysis_codes, "resultater")
    if profile == "solide":
        ordered_codes = ordered_codes - SOLIDE_PRE_CODES
        result_codes = result_codes - SOLIDE_PRE_CODES
    antall = build_antall((row for row in read_lvms_csv(antall_path) if row.get("Analyse") in ordered_codes), lookup)
    if profile == "solide":
        resultater = build_resultater_solide(
            (row for row in read_lvms_csv(resultater_path) if row.get("Analyse") in result_codes),
            read_lvms_csv(ekstraksjon_path),
            lookup,
            molstat_ids=molstat_ids,
        )
        antall_columns = SOLIDE_ANTALL_COLUMNS
        resultater_columns = SOLIDE_RESULTATER_COLUMNS
    else:
        resultater = build_resultater(
            (row for row in read_lvms_csv(resultater_path) if row.get("Analyse") in result_codes),
            read_lvms_csv(ekstraksjon_path),
            lookup,
            molstat_ids=molstat_ids,
        )
        antall_columns = ANTALL_COLUMNS
        resultater_columns = RESULTATER_COLUMNS
    write_excel_csv2(antall, output_dir / "antall.csv", antall_columns)
    write_excel_csv2(
        resultater, output_dir / "resultater.csv", resultater_columns
    )
    return {"antall": len(antall), "resultater": len(resultater)}

