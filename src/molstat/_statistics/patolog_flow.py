"""Deduplicated pathology workflow facts shared by MolStat and Power BI."""
from __future__ import annotations
import csv
import json
import math
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path
import re
from datetime import date, timedelta

STEM = "PAT-TID-STOP-SNITT-OU"

GROUPS = ["Ben bløtvev (sarkom)", "Hode-hals-oral", "GI og tarmscreening", "Øye", "Hjerte-tx",
    "Ikke-neoplastisk nyre", "Lever", "Lunge, tx", "Nevro biopsi", "Nevro muskel", "Nevro obd muskel",
    "Solide svulster barn", "Thorax", "Thyreoidea", "Gyn", "Hemato og Beinmarg", "Mamma", "URO", "Hud"]
GROUP_MAP = dict(zip(["BEN-BLØTVEV", "HODE-HALS-ORAL", "GI", "ØYE", "HJERTE-TX", "IKKE-NEOPLASTISK NYRE", "LEVER",
    "LUNGE TX", "NEVRO BIOPSI", "NEVRO MUSKEL", "NEVRO OBD MUSKEL", "SOLIDE SVULSTER BARN", "THORAX", "THYREOIDEA",
    "GYN", "HEMATO", "MAMMA", "URO", "HUD"], GROUPS))
GROUP_MAP["HEMATO BENMARG"] = "Hemato og Beinmarg"
GROUP_MAP["HEMATO-BEINMARG"] = "Hemato og Beinmarg"
GROUP_MAP["HEMATO BEINMARG"] = "Hemato og Beinmarg"
GROUP_MAP.update({"IKKE NEOPLASTISK NYR": "Ikke-neoplastisk nyre", "LUNGE-TX": "Lunge, tx",
                  "TARMSCREENING": "GI og tarmscreening"})
DATE_FIELDS = ["Prøvetakingstidspunkt", "Ankomsttid", "Makro utført", "Støpt dato", "Glass opprettet",
               "Glass etterbestilt", "Snittet dato", "Ferdig farget", "Godkjent dato"]
EMPTY_FIELDS = {
    "Glass": ["GlassId", "Prøvenummer", "Gruppe", "Prosess", "Prioritet", "Ankomst", "AnkomstDato", "Glasstype",
        "Glasspor", "Opprettet", "Etterbestilt", "Makro", "Støpt", "Snittet", "Farget", "FargetDato", "Ufarget",
        "ErEtterbestilt", "Glassstatus", "OpprettetTilSnitt", "SnittTilFarget", "OpprettetTilFarget"],
    "Signeringer": ["Prøvenummer", "Lege", "Rolle", "Gruppe", "Prosess", "Prioritet", "AnkomstDato", "GodkjentDato",
        "GodkjentTid", "Godkjent", "SvartidDager", "LegeDager", "MakroTilGodkjent", "Tidsstatus", "AntallGlass"],
    "Leger": ["Lege"],
}


def clean(value):
    text = str(value or "").strip()
    return text[4:-2].replace('""', '"') if text.startswith('=T("') and text.endswith('")') else text


def moment(value):
    if isinstance(value, datetime):
        return value
    value = clean(value)
    if not value:
        return None
    for pattern in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%d.%m.%Y %H:%M:%S"):
        try:
            return datetime.strptime(str(value).strip(), pattern)
        except ValueError:
            pass
    raise ValueError("Ugyldig tidspunkt i kildefilen")


def quantile(values, q):
    ordered = sorted(values)
    if not ordered:
        return None
    index = (len(ordered) - 1) * q
    lo, hi = math.floor(index), math.ceil(index)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo)


def duration(start, end):
    return (end - start).total_seconds() / 86400 if start is not None and end is not None and end >= start else None


def latest(rows, field):
    return max((r[field] for r in rows if r.get(field)), default=None)


def process_rows(raw, as_of=None):
    rows = [{k: moment(v) if k in DATE_FIELDS else clean(v) for k, v in r.items()} for r in raw]
    if not rows:
        raise ValueError("Ingen datarader")
    as_of = as_of or max(r[k] for r in rows for k in DATE_FIELDS if k != "Prøvetakingstidspunkt" and r.get(k))
    by_sample, by_glass = defaultdict(list), defaultdict(list)
    for row in rows:
        if row.get("Ankomsttid") is None:
            raise ValueError("Ankomsttid mangler")
        if not row.get("Prøvenummer") or row.get("Prosess") not in GROUP_MAP:
            raise ValueError("Prøvenummer mangler eller ukjent prosesskode; ingen stille bortfiltrering")
        by_sample[row["Prøvenummer"]].append(row)
        if row.get("GlassId"):
            by_glass[row["GlassId"]].append(row)
    slides, slide_index = [], defaultdict(list)
    fields = ["Prøvenummer", "Lab", "Prosess", "Prioritet", "Ankomsttid", "BeholderId", "Makro utført",
              "BlokkId", "Støpt dato", "Glasstype", "Glass opprettet", "Glass etterbestilt", "Snittet dato", "Ferdig farget"]
    for gid, duplicates in by_glass.items():
        if any(len({r.get(k) for r in duplicates}) > 1 for k in fields):
            raise ValueError("Motstridende glassdata for samme glass")
        r = duplicates[0]
        if not r["Ferdig farget"]:
            stage = "Mangler snitting" if not r["Snittet dato"] else "Snittet – ikke farget"
        else:
            stage = "Ferdig farget"
        record = {"GlassId": gid, "Prøvenummer": r["Prøvenummer"], "Gruppe": GROUP_MAP[r["Prosess"]],
            "Prosess": r["Prosess"], "Prioritet": r["Prioritet"], "Ankomst": r["Ankomsttid"],
            "AnkomstDato": r["Ankomsttid"].date(), "Glasstype": r["Glasstype"],
            "Glasspor": "Immun" if r["Glasstype"] in {"SKANN_IMM", "IMMUN"} else "Rutine / øvrig",
            "Opprettet": r["Glass opprettet"], "Etterbestilt": r["Glass etterbestilt"],
            "Makro": r["Makro utført"], "Støpt": r["Støpt dato"], "Snittet": r["Snittet dato"],
            "Farget": r["Ferdig farget"], "FargetDato": r["Ferdig farget"].date() if r["Ferdig farget"] else None,
            "Ufarget": int(not r["Ferdig farget"]), "ErEtterbestilt": int(bool(r["Glass etterbestilt"])), "Glassstatus": stage,
            "OpprettetTilSnitt": duration(r["Glass opprettet"], r["Snittet dato"]),
            "SnittTilFarget": duration(r["Snittet dato"], r["Ferdig farget"]),
            "OpprettetTilFarget": duration(r["Glass opprettet"], r["Ferdig farget"])}
        slides.append(record)
        slide_index[r["Prøvenummer"]].append(record)
    samples, signatures, audit = [], [], Counter()
    for sid, records in by_sample.items():
        r = records[0]
        for k in ["Ankomsttid", "Prosess", "Prioritet", "Lab", "Godkjent dato"]:
            if len({v.get(k) for v in records}) > 1:
                raise ValueError("Motstridende prøvedata; prøvenivå krever eksplisitt avklaring")
        end, arrival = r["Godkjent dato"], r["Ankomsttid"]
        glass = slide_index[sid]
        initial = [g for g in glass if g["ErEtterbestilt"] == 0]
        # Consistent initial batch, all initial glasses complete, same sample
        # cohort for every stacked component. Never sum independently filtered medians.
        macro = max((g["Makro"] for g in initial if g["Makro"]), default=None)
        cast = max((g["Støpt"] for g in initial if g["Støpt"]), default=None)
        cut = max((g["Snittet"] for g in initial if g["Snittet"]), default=None)
        color = max((g["Farget"] for g in initial if g["Farget"]), default=None)
        complete = bool(initial) and all(all(g[k] for k in ["Makro", "Støpt", "Snittet", "Farget"]) for g in initial)
        chain = [arrival, macro, cast, cut, color, end]
        valid = complete and all(chain) and all(a <= b for a, b in zip(chain, chain[1:]))
        main = sorted({v["Signert av"] for v in records if v["Godkjent type"] == "Hovedansvarlig" and v["Signert av"]})
        approved = bool(end)
        pending = sum(g["Ufarget"] for g in glass)
        last_color = max((g["Farget"] for g in glass if g["Farget"] and (not end or g["Farget"] <= end)), default=None)
        # Do not report a short doctor interval if any glass created before
        # approval is missing color or was colored only after approval.
        before_approval = [g for g in glass if end and g["Opprettet"] and g["Opprettet"] <= end]
        doctor_valid = bool(before_approval) and all(g["Farget"] and g["Farget"] <= end for g in before_approval)
        doctor_start = max((g["Farget"] for g in before_approval if g["Farget"]), default=None) if doctor_valid else None
        total = duration(arrival, end)
        age = duration(arrival, as_of)
        status = "Godkjent" if approved else "Glass ikke ferdig farget" if pending else "Uten glass" if not glass else "Farget – ikke godkjent"
        sample = {"Prøvenummer": sid, "Referansetid": as_of, "Lab": r["Lab"], "Prosess": r["Prosess"], "Gruppe": GROUP_MAP[r["Prosess"]],
            "Prioritet": r["Prioritet"], "Ankomst": arrival, "AnkomstDato": arrival.date(),
            "Prøvetaking": r["Prøvetakingstidspunkt"], "GodkjentTid": end, "GodkjentDato": end.date() if end else None,
            "Godkjent": int(approved), "Åpen": int(not approved), "Hovedlege": ", ".join(main) or "Ikke registrert",
            "AntallHovedleger": len(main), "AntallGlass": len(glass), "UfargedeGlass": pending,
            "ImmunGlass": sum(g["Glasspor"] == "Immun" for g in glass), "EtterbestilteGlass": sum(g["ErEtterbestilt"] for g in glass),
            "AntallBlokker": len({v["BlokkId"] for v in records if v["BlokkId"]}),
            "AntallBeholdere": len({v["BeholderId"] for v in records if v["BeholderId"]}),
            "Makro": latest(records, "Makro utført"), "SisteFarget": last_color,
            "Status": status, "AlderDager": age, "SvartidDager": total,
            "LegeDager": duration(doctor_start, end), "LegeStart": doctor_start,
            "MakroTilGodkjent": duration(latest(records, "Makro utført"), end),
            "AnkomstTilMakro": duration(arrival, latest(records, "Makro utført")),
            "KjedeGyldig": int(bool(valid)), "Tidsstatus": "Gyldig kjede" if valid else "Mangler trinn eller ugyldig rekkefølge",
            "Aldersgruppe": "0–2 dager" if age is not None and age <= 2 else "3–7 dager" if age is not None and age <= 7 else "8–14 dager" if age is not None and age <= 14 else "15–30 dager" if age is not None and age <= 30 else "Over 30 dager"}
        sample["AldersgruppeSort"] = next((i for i, limit in enumerate((2, 7, 14, 30), 1) if age is not None and age <= limit), 5)
        sample["FørstebestilteGlass"] = len(initial)
        bands = [(0, "Uten glass"), (1, "1 glass"), (2, "2 glass"), (5, "3–5 glass"), (10, "6–10 glass"), (20, "11–20 glass"), (math.inf, "Over 20 glass")]
        band, label = next((i, label) for i, (limit, label) in enumerate(bands) if len(glass) <= limit)
        sample["Glassmengde"], sample["GlassmengdeSort"] = label, band
        for i, (a, b) in enumerate(zip(chain, chain[1:]), 1):
            sample[f"Trinn{i}"] = duration(a, b) if valid else None
        samples.append(sample)
        sig_keys = set()
        for v in records:
            if not v["Signert av"]:
                continue
            key = (v["Signert av"], v["Godkjent type"], end)
            if key in sig_keys:
                continue
            sig_keys.add(key)
            signatures.append({"Prøvenummer": sid, "Lege": key[0], "Rolle": key[1], "Gruppe": sample["Gruppe"],
                "Prosess": sample["Prosess"], "Prioritet": sample["Prioritet"], "AnkomstDato": sample["AnkomstDato"],
                "GodkjentDato": sample["GodkjentDato"], "GodkjentTid": end, "Godkjent": int(approved),
                "SvartidDager": total, "LegeDager": sample["LegeDager"], "MakroTilGodkjent": sample["MakroTilGodkjent"],
                "Tidsstatus": "Gyldig legetid" if sample["LegeDager"] is not None else "Mangler entydig ferdig-farget før godkjenning",
                "AntallGlass": len(glass)})
        audit["valid_chains"] += int(bool(valid))
        audit["approved_with_uncolored_glass"] += int(approved and pending > 0)
        audit["approved_missing_doctor_interval"] += int(approved and sample["LegeDager"] is None)
        audit["multiple_main_doctors"] += int(len(main) > 1)
        audit["collection_after_arrival_samples"] += int(bool(r["Prøvetakingstidspunkt"] and r["Prøvetakingstidspunkt"] > arrival))
    completed = [s["SvartidDager"] for s in samples if s["SvartidDager"] is not None]
    global_limit = max(1, math.ceil(quantile(completed, .9) or 14))
    group_rows = []
    for index, group in enumerate(GROUPS):
        values = [s["SvartidDager"] for s in samples if s["Gruppe"] == group and s["SvartidDager"] is not None]
        enough = len(values) >= 30
        limit = max(1, math.ceil(quantile(values, .9))) if enough else global_limit
        group_rows.append({"Gruppe": group, "Rekkefølge": index + 1, "VarselDager": limit,
            "GrunnlagN": len(values), "Datadekning": "Med data" if any(s["Gruppe"] == group for s in samples) else "Ingen prøver i uttrekket",
            "Grensegrunnlag": "Gruppens P90, minst 30 godkjente" if enough else "Samlet P90, for lite gruppegrunnlag"})
    limits = {r["Gruppe"]: r["VarselDager"] for r in group_rows}
    for s in samples:
        s["VarselDager"] = limits[s["Gruppe"]]
        s["OverGrense"] = int(s["Åpen"] and s["AlderDager"] is not None and s["AlderDager"] > s["VarselDager"])
    audit.update(source_rows=len(rows), samples=len(samples), unique_glass=len(slides), signatures=len(signatures),
        approved_samples=sum(s["Godkjent"] for s in samples), open_samples=sum(s["Åpen"] for s in samples),
        uncolored_glass=sum(g["Ufarget"] for g in slides), rows_without_glass=sum(not r["GlassId"] for r in rows))
    return {"Prøver": samples, "Glass": slides, "Signeringer": signatures, "Grupper": group_rows,
            "audit": dict(audit) | {"as_of": as_of.isoformat(), "arrival_from": min(s["Ankomst"] for s in samples).isoformat(),
                "arrival_to": max(s["Ankomst"] for s in samples).isoformat(), "global_p90_days": global_limit,
                "raw_p90_days": quantile(completed, .9), "groups_with_data": len({s["Gruppe"] for s in samples})}}


def read_source(path):
    with path.open(encoding="cp1252", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        required = set(DATE_FIELDS) | {"Prøvenummer", "Lab", "Prosess", "Prioritet", "BeholderId", "BlokkId",
                                      "GlassId", "Glasstype", "Signert av", "Godkjent type"}
        if not required <= set(reader.fieldnames or []) or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("Kilden mangler forventede kolonner")
        rows = list(reader)
        if any(None in r or any(value is None for value in r.values()) for r in rows):
            raise ValueError("Ugyldig kolonneantall")
        return rows


def write_data(folder, data):
    folder.mkdir(parents=True, exist_ok=True)
    for name, rows in data.items():
        if name == "audit":
            (folder / "source_audit.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            continue
        fields = list(rows[0]) if rows else EMPTY_FIELDS.get(name)
        if not fields:
            raise ValueError("Kan ikke skrive tabell uten kolonneskjema")
        with (folder / f"{name}.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: v.isoformat(sep=" ") if isinstance(v, datetime) else v for k, v in row.items()})


def latest_months(folder):
    pattern = re.compile(r"__(\d{4}-\d{2}-\d{2})__(\d{4}-\d{2}-\d{2})(?:__r(\d+))?\.csv$")
    chosen = {}
    for path in folder.glob(STEM + "__*.csv"):
        match = pattern.search(path.name)
        if not match:
            continue
        start, end = date.fromisoformat(match[1]), date.fromisoformat(match[2])
        if start.day != 1 or start.replace(day=1) != end.replace(day=1):
            continue
        key = (end, path.stat().st_mtime_ns, int(match[3] or 1))
        if start not in chosen or key > chosen[start][0]:
            chosen[start] = key, path
    return {month: (entry[1], entry[0][0]) for month, entry in chosen.items()}


def validate_month(path, start, end, *, laboratory=None, processes=()):
    rows = read_source(path)
    if any(not (arrival := moment(row.get("Ankomsttid"))) or not start <= arrival.date() <= end for row in rows):
        raise ValueError("Uttrekket inneholder ankomst utenfor forespurt periode")
    if laboratory and any(clean(r.get("Lab")) != laboratory for r in rows):
        raise ValueError("Uttrekket inneholder feil laboratorium")
    if processes and any(clean(r.get("Prosess")) not in processes for r in rows):
        raise ValueError("Uttrekket inneholder prosess utenfor filteret")
    # Validate conflicts, IDs, process mapping and timestamps before archiving.
    if rows:
        process_rows(rows)
    return rows


def needs_refresh(path, start, end, today):
    month_end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    if end != month_end or (today - datetime.fromtimestamp(path.stat().st_mtime).date()).days >= 30:
        return True
    try:
        rows = validate_month(path, start, end)
        return any(not clean(r.get("Godkjent dato")) or
                   (clean(r.get("GlassId")) and not clean(r.get("Ferdig farget"))) for r in rows)
    except ValueError:
        return True


def read_archive(folder, as_of=None):
    rows, seen = [], set()
    for month, (path, end) in sorted(latest_months(folder).items()):
        part = validate_month(path, month, end)
        ids = {clean(r["Prøvenummer"]) for r in part}
        if ids & seen:
            raise ValueError("Samme prøve finnes i flere ankomstmåneder")
        seen.update(ids)
        rows.extend(part)
    return process_rows(rows, as_of=as_of)


def add_dimensions(data):
    start = min(row["AnkomstDato"] for row in data["Prøver"])
    end = datetime.fromisoformat(data["audit"]["as_of"]).date()
    months = ["januar", "februar", "mars", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "desember"]
    dates = []
    while start <= end:
        iso = start.isocalendar()
        dates.append({"Dato": start, "År": start.year, "MånedNr": start.month, "Måned": months[start.month - 1],
            "ÅrMåned": start.strftime("%Y-%m"), "Uke": iso.week, "ÅrUke": f"{iso.year}-U{iso.week:02d}"})
        start += timedelta(days=1)
    data["Periode"] = dates
    data["Leger"] = [{"Lege": name} for name in sorted({r["Lege"] for r in data["Signeringer"]})]
    data["Prioriteter"] = [{"Prioritet": name} for name in sorted({r["Prioritet"] for r in data["Prøver"]})]
    return data


def write_process_summary(path, data):
    """Keep the aggregate delivery derived exclusively from workflow facts."""
    from .patolog_process import FIELDS
    grouped = defaultdict(list)
    for row in data["Prøver"]:
        grouped[(row["AnkomstDato"].replace(day=1), row["Lab"], row["Prosess"], row["Gruppe"])].append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, delimiter=";")
        writer.writeheader()
        for (month, lab, code, group), rows in sorted(grouped.items()):
            writer.writerow(dict(zip(FIELDS, (month.isoformat(), "Ikke oppgitt i kilden", lab, code, group,
                len(rows), sum(r["AntallBlokker"] for r in rows), sum(r["AntallGlass"] for r in rows), data["audit"]["as_of"][:10]))))
    return len(grouped)
