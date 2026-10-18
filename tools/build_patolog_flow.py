"""Build experimental pathology workflow reports without changing MolStat."""
from __future__ import annotations
import copy
import csv
import json
import math
import shutil
import uuid
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import build_hemato_statistikk_v4_report as base
from build_hemato_statistikk_v5_report import PolishedPage
from patolog_flow_data import process_rows, read_source, write_data, GROUPS

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "powerbi/Patolog_Forlop_20261018"
SOURCE = Path.home() / "Downloads/PAT-TID-STOP-SNITT-OU.csv"
REFERENCE = Path.home() / "Downloads/Restanse_Hemato (1).pbix"
STAT_REFERENCE = ROOT / "powerbi/Hemato_Statistikk_V13.pbix"
DATA = PROJECT / "Data"
REPORT = PROJECT / "Patolog.Statistikk.Report"
REST = PROJECT / "Patolog.Restanse.Report"
PAGES = [(f"pf{i:018x}", title) for i, title in enumerate([
    "Oversikt", "Volum og produksjon", "Restanse og alder", "Forløp stablet", "Forløp per uke",
    "Legetider", "Legevolum og roller", "Immun og rutine", "Glassproduksjon", "Etterbestillinger",
    "Prioritet", "Prosessgrupper", "Prøvedetaljer", "Glassdetaljer", "Legegodkjenninger",
    "Datakvalitet", "Prøver og glass", "Definisjoner", "Legeutvikling", "Svartid over tid"], 1)]


def dump(path, value):
    base.dump(path, value)


def selected(expr, table="Prøver", field="AnkomstDato"):
    return f"CALCULATE({expr}, KEEPFILTERS(TREATAS(VALUES(Periode[Dato]), '{table}'[{field}])))"


MEASURES = {
    "Mottatte prøver": (selected("COUNTROWS('Prøver')"), "#,##0"),
    "Godkjente prøver": (selected("COUNTROWS('Prøver')", field="GodkjentDato"), "#,##0"),
    "Godkjent i ankomstutvalg": (selected("SUM('Prøver'[Godkjent])"), "#,##0"),
    "Åpne prøver": (selected("SUM('Prøver'[Åpen])"), "#,##0"),
    "Alle åpne prøver": ("SUM('Prøver'[Åpen])", "#,##0"),
    "Ufargede glass": (selected("SUM('Prøver'[UfargedeGlass])"), "#,##0"),
    "Alle ufargede glass": ("SUM('Prøver'[UfargedeGlass])", "#,##0"),
    "Over foreløpig grense": (selected("SUM('Prøver'[OverGrense])"), "#,##0"),
    "Antall glass": (selected("SUM('Prøver'[AntallGlass])"), "#,##0"),
    "Blokker": (selected("SUM('Prøver'[AntallBlokker])"), "#,##0"),
    "Beholdere": (selected("SUM('Prøver'[AntallBeholdere])"), "#,##0"),
    "Immun-glass": (selected("SUM('Prøver'[ImmunGlass])"), "#,##0"),
    "Etterbestilte glass": (selected("SUM('Prøver'[EtterbestilteGlass])"), "#,##0"),
    "Andel immun": ("DIVIDE([Immun-glass],[Antall glass])", "0.0%"),
    "Glass per prøve": ("DIVIDE([Antall glass],[Mottatte prøver])", "0.0"),
    "Andel etterbestilt": ("DIVIDE([Etterbestilte glass],[Antall glass])", "0.0%"),
    "Prøver med etterbestilling": (selected("COUNTROWS(FILTER('Prøver','Prøver'[EtterbestilteGlass]>0))"), "#,##0"),
    "Median svartid dager": (selected("MEDIAN('Prøver'[SvartidDager])", field="GodkjentDato"), "0.0"),
    "Gjennomsnitt svartid": (selected("AVERAGE('Prøver'[SvartidDager])", field="GodkjentDato"), "0.0"),
    "P90 svartid": (selected("PERCENTILEX.INC(FILTER('Prøver',NOT ISBLANK('Prøver'[SvartidDager])),'Prøver'[SvartidDager],0.9)", field="GodkjentDato"), "0.0"),
    "N svartid": (selected("COUNT('Prøver'[SvartidDager])", field="GodkjentDato"), "#,##0"),
    "Median alder restanse": (selected("MEDIANX(FILTER('Prøver','Prøver'[Åpen]=1),'Prøver'[AlderDager])"), "0.0"),
    "Eldste restanse": (selected("MAXX(FILTER('Prøver','Prøver'[Åpen]=1),'Prøver'[AlderDager])"), "0.0"),
    "Foreløpig grense dager": ("SELECTEDVALUE(Grupper[VarselDager])", "0"),
    "Grensegrunnlag": ("SELECTEDVALUE(Grupper[Grensegrunnlag])", ""),
    "Dekning": ("SELECTEDVALUE(Grupper[Datadekning])", ""),
    "Godkjente med ufargede glass": (selected("COUNTROWS(FILTER('Prøver','Prøver'[Godkjent]=1 && 'Prøver'[UfargedeGlass]>0))"), "#,##0"),
    "Kjede N": (selected("SUM('Prøver'[KjedeGyldig])", field="GodkjentDato"), "#,##0"),
    "Kjede uten beregnbar tid": ("[Godkjente prøver]-[Kjede N]", "#,##0"),
    "Kjede total gjennomsnitt": (selected("AVERAGEX(FILTER('Prøver','Prøver'[KjedeGyldig]=1),'Prøver'[SvartidDager])", field="GodkjentDato"), "0.0"),
    "Median legetid dager": (selected("MEDIAN('Prøver'[LegeDager])", field="GodkjentDato"), "0.0"),
    "N legetid": (selected("COUNT('Prøver'[LegeDager])", field="GodkjentDato"), "#,##0"),
    "Median ankomst til makro": (selected("MEDIAN('Prøver'[AnkomstTilMakro])"), "0.0"),
    "Utvalgsrad": ("IF([Mottatte prøver]>0,1,0)", "0"),
    "Restanserad": ("IF([Åpne prøver]>0,1,0)", "0"),
    "Kortstatus farge": ("SWITCH(TRUE(), [Over foreløpig grense]>0,\"#F05252\",[Ufargede glass]>0,\"#A78BFA\",[Åpne prøver]>0,\"#65C466\",\"#263750\")", ""),
    "Datatid": ('"15.10.2026 12:37"', ""),
    "Valgt gruppe": ('COALESCE(SELECTEDVALUE(Grupper[Gruppe]),"Alle prosessgrupper")', ""),
}
STAGES = ["Ankomst → makro", "Makro → støpt", "Støpt → snittet", "Snittet → farget", "Farget → godkjent"]
FIELD_LABELS = {"Prøvenummer": "Prøvenummer", "AntallGlass": "Glass", "UfargedeGlass": "Ufargede glass",
    "AlderDager": "Alder · dager", "VarselDager": "Varselgrense · dager", "SvartidDager": "Ankomst → godkjent · dager",
    "LegeDager": "Farget → godkjent · dager", "GodkjentTid": "Godkjent", "OpprettetTilFarget": "Opprettet → farget · dager",
    "Datadekning": "Datadekning", "GrunnlagN": "N bak varselgrensen"}
for i, name in enumerate(STAGES, 1):
    MEASURES[name] = (selected(f"AVERAGE('Prøver'[Trinn{i}])", field="GodkjentDato"), "0.00")
for name, expr in list(MEASURES.items()):
    if expr[1] == "#,##0":
        MEASURES[name] = (f"COALESCE({expr[0]},0)", expr[1])

GLASS_MEASURES = {
    "Unike glass": (selected("COUNTROWS(Glass)", "Glass"), "#,##0"),
    "Glass farget i periode": (selected("COUNTROWS(Glass)", "Glass", "FargetDato"), "#,##0"),
    "Ufarget i glassutvalg": (selected("SUM(Glass[Ufarget])", "Glass"), "#,##0"),
    "Median snitting til farget": (selected("MEDIAN(Glass[SnittTilFarget])", "Glass"), "0.00"),
    "Median opprettet til farget": (selected("MEDIAN(Glass[OpprettetTilFarget])", "Glass"), "0.00"),
    "N glass med fargetid": (selected("COUNT(Glass[OpprettetTilFarget])", "Glass"), "#,##0"),
    "Glassrad": ("IF([Unike glass]>0,1,0)", "0"),
}
DOCTOR_MEASURES = {
    "Signerte prøver": (selected("DISTINCTCOUNT(Signeringer[Prøvenummer])", "Signeringer", "GodkjentDato"), "#,##0"),
    "Godkjenningsroller": (selected("COUNTROWS(Signeringer)", "Signeringer", "GodkjentDato"), "#,##0"),
    "Tildelte åpne prøver": (selected("CALCULATE(DISTINCTCOUNT(Signeringer[Prøvenummer]),Signeringer[Godkjent]=0)", "Signeringer"), "#,##0"),
    "Lege median farget til godkjent": (selected("MEDIAN(Signeringer[LegeDager])", "Signeringer", "GodkjentDato"), "0.0"),
    "Lege median ankomst til godkjent": (selected("MEDIAN(Signeringer[SvartidDager])", "Signeringer", "GodkjentDato"), "0.0"),
    "Lege median makro til godkjent": (selected("MEDIAN(Signeringer[MakroTilGodkjent])", "Signeringer", "GodkjentDato"), "0.0"),
    "Lege N tid": (selected("COUNT(Signeringer[LegeDager])", "Signeringer", "GodkjentDato"), "#,##0"),
    "Legerad": ("IF([Godkjenningsroller]>0 || [Tildelte åpne prøver]>0,1,0)", "0"),
}
DOCTOR_MEASURES.pop("Tildelte åpne prøver")
DOCTOR_MEASURES["Legerad"] = ("IF([Godkjenningsroller]>0,1,0)", "0")
# All-role views must not give a sample extra weight when the same doctor
# occurs in several approval roles on that sample.
for label, field in [("farget til godkjent", "LegeDager"), ("ankomst til godkjent", "SvartidDager"), ("makro til godkjent", "MakroTilGodkjent")]:
    unique = f'SUMMARIZE(FILTER(Signeringer,NOT ISBLANK(Signeringer[{field}])),Signeringer[Prøvenummer],"V",MAX(Signeringer[{field}]))'
    DOCTOR_MEASURES["Lege median " + label] = (selected(f"MEDIANX({unique},[V])", "Signeringer", "GodkjentDato"), "0.0")
    if field == "LegeDager":
        DOCTOR_MEASURES["Lege P90 farget til godkjent"] = (selected(f"PERCENTILEX.INC({unique},[V],0.9)", "Signeringer", "GodkjentDato"), "0.0")
        DOCTOR_MEASURES["Lege N tid"] = (selected(f"COUNTROWS({unique})", "Signeringer", "GodkjentDato"), "#,##0")
DOCTOR_MEASURES["Lege glass på godkjente prøver"] = (selected('SUMX(SUMMARIZE(Signeringer,Signeringer[Prøvenummer],"G",MAX(Signeringer[AntallGlass])),[G])', "Signeringer", "GodkjentDato"), "#,##0")


def model_table(name, rows, measures=None, hidden=False):
    columns = []
    for key in rows[0]:
        values = [r[key] for r in rows if r[key] is not None]
        value = values[0] if values else None
        typ = "dateTime" if isinstance(value, (date, datetime)) else "int64" if isinstance(value, int) else "double" if isinstance(value, float) else "string"
        col = {"name": key, "dataType": typ, "sourceColumn": key, "summarizeBy": "none", "lineageTag": str(uuid.uuid4())}
        if typ == "dateTime":
            col["formatString"] = "dd.MM.yyyy" if key.endswith("Dato") or key == "Dato" else "dd.MM.yyyy HH:mm"
        elif typ == "double":
            col["formatString"] = "0.00"
        elif typ == "int64":
            col["formatString"] = "0"
        columns.append(col)
    transformations = []
    for c in columns:
        converter = {"dateTime": 'DateTime.FromText(_, [Culture="en-US"])', "double": 'Number.FromText(_,"en-US")',
                     "int64": 'Int64.From(Number.FromText(_,"en-US"))', "string": "_"}[c["dataType"]]
        typ = {"dateTime": "datetime", "double": "number", "int64": "number", "string": "text"}[c["dataType"]]
        type_expression = "Int64.Type" if c["dataType"] == "int64" else "type nullable " + typ
        transformations.append('{"' + c["name"] + '", each if _ = "" then null else ' + converter + ', ' + type_expression + '}')
    expression = f'''let
 Raw=Csv.Document(File.Contents(Datamappe & "/{name}.csv"),[Delimiter=";",Encoding=65001,QuoteStyle=QuoteStyle.Csv]),
 Headers=Table.PromoteHeaders(Raw,[PromoteAllScalars=true]),
 Typed=Table.TransformColumns(Headers,{{{','.join(transformations)}}})
in Typed'''
    result = {"name": name, "lineageTag": str(uuid.uuid4()), "columns": columns, "isHidden": hidden,
        "partitions": [{"name": name, "mode": "import", "source": {"type": "m", "expression": expression}}]}
    if measures:
        result["measures"] = [{"name": key, "expression": expr, "formatString": fmt, "lineageTag": str(uuid.uuid4())} for key, (expr, fmt) in measures.items()]
    return result


def create_model(data):
    MEASURES["Datatid"] = ('FORMAT(MAX(\'Prøver\'[Referansetid]),"dd.MM.yyyy HH:mm")', "")
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
    write_data(DATA, data)
    tables = [model_table(name, data[name], metrics) for name, metrics in
              [("Prøver", MEASURES), ("Glass", GLASS_MEASURES), ("Signeringer", DOCTOR_MEASURES),
               ("Grupper", None), ("Periode", None), ("Leger", None), ("Prioriteter", None)]]
    period = next(t for t in tables if t["name"] == "Periode")
    next(c for c in period["columns"] if c["name"] == "Måned")["sortByColumn"] = "MånedNr"
    groups = next(t for t in tables if t["name"] == "Grupper")
    next(c for c in groups["columns"] if c["name"] == "Gruppe")["sortByColumn"] = "Rekkefølge"
    samples = next(t for t in tables if t["name"] == "Prøver")
    next(c for c in samples["columns"] if c["name"] == "Aldersgruppe")["sortByColumn"] = "AldersgruppeSort"
    next(c for c in samples["columns"] if c["name"] == "AldersgruppeSort")["isHidden"] = True
    next(c for c in samples["columns"] if c["name"] == "Glassmengde")["sortByColumn"] = "GlassmengdeSort"
    next(c for c in samples["columns"] if c["name"] == "GlassmengdeSort")["isHidden"] = True
    pairs = [("Prøver", "Gruppe", "Grupper", "Gruppe"), ("Prøver", "Prioritet", "Prioriteter", "Prioritet"),
             ("Glass", "Prøvenummer", "Prøver", "Prøvenummer"), ("Signeringer", "Prøvenummer", "Prøver", "Prøvenummer"),
             ("Signeringer", "Lege", "Leger", "Lege")]
    return {"name": "Patolog_Forlop", "compatibilityLevel": 1606, "model": {"culture": "nb-NO", "sourceQueryCulture": "nb-NO",
        "defaultPowerBIDataSourceVersion": "powerBI_V3", "tables": tables,
        "expressions": [{"name": "Datamappe", "kind": "m", "expression":
            '"' + DATA.as_posix() + '" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'}],
        "relationships": [{"name": str(uuid.uuid4()), "fromTable": a, "fromColumn": b, "toTable": c, "toColumn": d,
                            "crossFilteringBehavior": "oneDirection"} for a, b, c, d in pairs],
        "annotations": [{"name": "__PBI_TimeIntelligenceEnabled", "value": "0"}]}}


class ReportPage(PolishedPage):
    def navigator(self, visual_id, x, y, w, h):
        super().navigator(visual_id, x, y, w, h)
        for i, _ in enumerate(base.PAGE_DEFS):
            path = self.visuals / f"{visual_id}-{i + 1}" / "visual.json"
            doc = json.loads(path.read_text("utf8"))
            doc["position"].update(y=98 + i * 28, height=26)
            for item in doc["visual"]["objects"]["text"]:
                item["properties"]["fontSize"] = base.lit("9D")
            dump(path, doc)

    def card(self, visual_id, x, y, w, h, entity, metric, label, accent, subtitle=""):
        super().card(visual_id, x, y, w, h, entity, metric, label, accent, subtitle)
        path = self.visuals / visual_id / "visual.json"
        doc = json.loads(path.read_text("utf8"))
        # The source helper recognizes only names containing 'dager'. These
        # timing and ratio measures also need one decimal instead of integer labels.
        fractional = any(word in metric.casefold() for word in ["median", "gjennomsnitt", "p90", "andel", "per prøve"])
        doc["visual"]["objects"]["labels"][0]["properties"]["labelPrecision"] = base.lit("1L" if fractional else "0L")
        dump(path, doc)


def selection(page, vid, entity, field, value, numeric=False):
    path = page.visuals / vid / "visual.json"
    doc = json.loads(path.read_text("utf8"))
    doc["visual"]["objects"]["general"] = [{"properties": {"filter": {"filter": {
        "Version": 2, "From": [{"Name": "s", "Entity": entity, "Type": 0}],
        "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": field}}],
                    "Values": [[{"Literal": {"Value": str(value) + "L" if numeric else "'" + value + "'"}}]]}}}]}}}}]
    dump(path, doc)


def row_filter(doc, entity, metric):
    doc.setdefault("filterConfig", {})["filters"] = [{"name": "rowInPeriod", "field": {"Measure": {
        "Expression": {"SourceRef": {"Entity": entity}}, "Property": metric}}, "type": "Advanced", "filter": {
        "Version": 2, "From": [{"Name": "s", "Entity": entity, "Type": 0}], "Where": [{"Condition": {"Comparison": {
            "ComparisonKind": 0, "Left": {"Measure": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": metric}},
            "Right": {"Literal": {"Value": "1L"}}}}}]}}]


def shell(source, target):
    with zipfile.ZipFile(source) as z:
        for name in z.namelist():
            if name in {"Report/definition/report.json", "Report/definition/version.json"} or name.startswith("Report/StaticResources/"):
                path = target / name.removeprefix("Report/")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(z.read(name))


def build_statistics(audit):
    shell(STAT_REFERENCE, REPORT)
    generated_pages = (REPORT / "definition/pages").resolve()
    assert generated_pages.is_relative_to(PROJECT.resolve())
    if generated_pages.exists():
        shutil.rmtree(generated_pages)
    base.PAGES = REPORT / "definition/pages"
    base.PAGE_DEFS = PAGES
    c, m = base.column, lambda name: base.measure("Prøver", name)
    for index, (pid, title) in enumerate(PAGES):
        page = ReportPage(pid, title, "Patologi · prøver, glass, leger og prosessforløp", "Data til 15.10.2026 12:37")
        page.textbox("brand", 18, 16, 150, 62, [("OUS", 23, "#FFFFFF", True), ("Patologi", 11, "#CFE3F2", False)])
        about = index in [15, 17]
        if not about:
            for vid, x, w, entity, field, label in [("year", 204, 110, "Periode", "År", "År"),
                ("month", 322, 160, "Periode", "Måned", "Måned"), ("group", 490, 300, "Grupper", "Gruppe", "Prosessgruppe"),
                ("priority", 798, 200, "Prioriteter", "Prioritet", "Prioritet")]:
                page.slicer(vid, x, 82, w, 64, entity, field, label)
            selection(page, "year", "Periode", "År", 2026, True)
            if index == 0:
                selection(page, "month", "Periode", "Måned", "oktober")
            if index in [5, 6, 14, 18]:
                page.slicer("doctor", 1006, 82, 246, 64, "Leger", "Lege", "Lege")
                page.slicer("role", 204, 151, 245, 60, "Signeringer", "Rolle", "Godkjenningsrolle")
        def cards(specs, y=164):
            for i, (entity, name, label, color) in enumerate(specs):
                page.card("kpi" + str(i), 204 + i * 264, y, 256, 90, entity, name, label, color)
        def chart(vid, kind, x, y, w, h, label, entity, category, names, metric_entity="Prøver", subtitle="", sort=False):
            projections = [base.measure(metric_entity, name) for name in names]
            roles = {"Category": [c(entity, category)], "Y": projections}
            if any(name in STAGES for name in names):
                roles["Tooltips"] = [m("Kjede N"), m("Kjede uten beregnbar tid")]
            elif metric_entity == "Signeringer":
                roles["Tooltips"] = [base.measure("Signeringer", name) for name in ["Signerte prøver", "Lege N tid"]]
            elif any(word in name.casefold() for name in names for word in ["svartid", "p90"]):
                roles["Tooltips"] = [m("N svartid")]
            page.chart(vid, kind, x, y, w, h, label, subtitle, roles,
                       show_legend=len(names) > 1, show_labels=kind in {"clusteredBarChart", "clusteredColumnChart", "columnChart"}, sort_field=projections[0] if sort else None)
        def table(vid, y, label, entity, fields, measures=(), h=340, metric=None):
            projections = [c(entity, name) for name in fields] + [base.measure(entity, name) for name in measures]
            for projection in projections:
                projection["nativeQueryRef"] = FIELD_LABELS.get(projection["nativeQueryRef"], projection["nativeQueryRef"])
            page.table(vid, 204, y, 1048, h, label, projections)
            if metric:
                path = page.visuals / vid / "visual.json"
                doc = json.loads(path.read_text("utf8")); row_filter(doc, entity, metric); dump(path, doc)
        if index == 0:
            cards([("Prøver", "Mottatte prøver", "Mottatt i valgt periode", base.C["blue"]),
                   ("Prøver", "Godkjente prøver", "Godkjent i valgt periode", base.C["green"]),
                   ("Prøver", "Ufargede glass", "Ufargede glass · ankomstutvalg", "#7C3AED"),
                   ("Prøver", "Over foreløpig grense", "Åpne over foreløpig grense", base.C["red"])])
            chart("trend", "clusteredColumnChart", 204, 278, 520, 340, "Mottatt og godkjent per uke", "Periode", "ÅrUke", ["Mottatte prøver", "Godkjente prøver"])
            chart("groups", "clusteredBarChart", 740, 278, 512, 340, "Åpne prøver per gruppe", "Grupper", "Gruppe", ["Åpne prøver"], sort=True)
        elif index == 1:
            cards([("Prøver", "Mottatte prøver", "Mottatte prøver", base.C["blue"]), ("Prøver", "Godkjente prøver", "Godkjente prøver", base.C["green"]),
                   ("Prøver", "Blokker", "Blokker i ankomstutvalget", base.C["teal"]), ("Prøver", "Antall glass", "Unike glass", base.C["blue"])])
            chart("daily", "lineChart", 204, 278, 1048, 340, "Daglig volum", "Periode", "Dato", ["Mottatte prøver", "Godkjente prøver"])
        elif index == 2:
            cards([("Prøver", "Åpne prøver", "Åpne i ankomstutvalget", base.C["blue"]), ("Prøver", "Alle åpne prøver", "Alle åpne i hele filen", base.C["teal"]),
                   ("Prøver", "Median alder restanse", "Median alder restanse", base.C["amber"]), ("Prøver", "Eldste restanse", "Eldste restanse · dager", base.C["red"])])
            chart("status", "clusteredBarChart", 204, 278, 520, 340, "Åpne per prosesstatus", "Prøver", "Status", ["Åpne prøver"])
            chart("age", "clusteredColumnChart", 740, 278, 512, 340, "Aldersfordeling · åpne", "Prøver", "Aldersgruppe", ["Åpne prøver"])
        elif index in [3, 4]:
            cards([("Prøver", "Kjede N", "Prøver i samme kjedeutvalg", base.C["blue"]), ("Prøver", "Kjede total gjennomsnitt", "Gjennomsnitt samlet · dager", base.C["teal"]),
                   ("Prøver", "Kjede uten beregnbar tid", "Godkjente uten gyldig kjede", base.C["amber"]), ("Prøver", "Godkjente prøver", "Godkjente i perioden", base.C["green"])])
            chart("stack", "barChart" if index == 3 else "columnChart", 204, 278, 1048, 340,
                  "Gjennomsnitt per trinn · samme komplette prøveutvalg", "Grupper" if index == 3 else "Periode",
                  "Gruppe" if index == 3 else "ÅrUke", STAGES,
                  subtitle="Førstebestilling · ingen etterbestillinger · delene summerer til samlet gjennomsnitt")
        elif index == 5:
            cards([("Signeringer", "Lege median farget til godkjent", "Farget → godkjent · median", base.C["teal"]),
                   ("Signeringer", "Lege N tid", "N gyldige legeintervaller", base.C["blue"]),
                   ("Signeringer", "Lege median ankomst til godkjent", "Ankomst → godkjent · median", base.C["teal"]),
                   ("Signeringer", "Lege median makro til godkjent", "Makro → godkjent · median", base.C["teal"])], 223)
            chart("doctor-times", "clusteredBarChart", 204, 328, 1048, 290, "Forløpstid per lege · sammenlikn innen samme gruppe og prioritet",
                  "Leger", "Lege", ["Lege median farget til godkjent"], "Signeringer", sort=True)
        elif index == 6:
            cards([("Signeringer", "Signerte prøver", "Unike signerte prøver", base.C["blue"]), ("Signeringer", "Godkjenningsroller", "Godkjenningsroller", base.C["teal"]),
                   ("Signeringer", "Lege glass på godkjente prøver", "Glass på godkjente prøver", base.C["amber"]), ("Signeringer", "Lege N tid", "Med beregnbar legetid", base.C["green"])], 223)
            chart("doctors", "clusteredBarChart", 204, 328, 700, 290, "Godkjente prøver per lege", "Leger", "Lege", ["Signerte prøver"], "Signeringer", sort=True)
            chart("roles", "clusteredColumnChart", 920, 328, 332, 290, "Prøver per rolle", "Signeringer", "Rolle", ["Signerte prøver"], "Signeringer", subtitle="Følger valgt lege · én prøve per rolle")
        elif index in [7, 8, 9]:
            cards([("Prøver", "Antall glass", "Unike glass · ankomstutvalg", base.C["blue"]), ("Prøver", "Immun-glass", "SKANN_IMM + IMMUN", base.C["teal"]),
                   ("Prøver", "Etterbestilte glass", "Etterbestilte glass", base.C["amber"]), ("Prøver", "Glass per prøve", "Glass per prøve", base.C["green"])])
            if index == 7:
                chart("types", "clusteredBarChart", 204, 278, 520, 340, "Unike glass per type", "Glass", "Glasstype", ["Unike glass"], "Glass")
                chart("tracks", "clusteredColumnChart", 740, 278, 512, 340, "Ufargede glass per spor", "Glass", "Glasspor", ["Ufarget i glassutvalg"], "Glass")
            elif index == 8:
                chart("glass-week", "clusteredColumnChart", 204, 278, 520, 340, "Glass ferdig farget per uke", "Periode", "ÅrUke", ["Glass farget i periode"], "Glass")
                chart("stain-time", "clusteredBarChart", 740, 278, 512, 340, "Opprettet → farget · median dager", "Glass", "Glasstype", ["Median opprettet til farget"], "Glass")
            else:
                chart("after", "clusteredBarChart", 204, 278, 520, 340, "Etterbestilte glass per gruppe", "Grupper", "Gruppe", ["Etterbestilte glass"])
                chart("after-trend", "lineChart", 740, 278, 512, 340, "Andel etterbestilte · ankomstuke", "Periode", "ÅrUke", ["Andel etterbestilt"])
        elif index == 10:
            cards([("Prøver", "Mottatte prøver", "Mottatte prøver", base.C["blue"]), ("Prøver", "Median svartid dager", "Median svartid", base.C["teal"]),
                   ("Prøver", "P90 svartid", "P90 svartid · dager", base.C["amber"]), ("Prøver", "N svartid", "N gyldige svartider", base.C["green"])])
            chart("priority-volume", "clusteredBarChart", 204, 278, 520, 340, "Antall per prioritet", "Prioriteter", "Prioritet", ["Mottatte prøver"])
            chart("priority-time", "clusteredBarChart", 740, 278, 512, 340, "Median svartid per prioritet", "Prioriteter", "Prioritet", ["Median svartid dager"])
        elif index == 11:
            page.table("group-overview", 204, 166, 1048, 450, "Prosessgrupper · dekning, volum og tider", [c("Grupper", "Gruppe"), c("Grupper", "Datadekning"),
                m("Mottatte prøver"), m("Godkjente prøver"), m("Åpne prøver"), m("Antall glass"), m("Median svartid dager"), m("N svartid"),
                c("Grupper", "VarselDager"), c("Grupper", "GrunnlagN")])
        elif index == 12:
            table("sample-details", 164, "Én rad per prøve · valgt ankomstperiode", "Prøver",
                  ["Prøvenummer", "Gruppe", "Prosess", "Prioritet", "Hovedlege", "Ankomst", "GodkjentTid", "Status", "AntallGlass", "UfargedeGlass", "AlderDager", "VarselDager", "SvartidDager", "LegeDager"], h=454, metric="Utvalgsrad")
        elif index == 13:
            page.slicer("glass-type", 1006, 82, 246, 64, "Glass", "Glasstype", "Glasstype")
            table("glass-details", 164, "Én rad per glass · valgt ankomstperiode", "Glass",
                ["Prøvenummer", "GlassId", "Prosess", "Glasstype", "Glassstatus", "Opprettet", "Etterbestilt", "Snittet", "Farget", "OpprettetTilFarget"], h=454, metric="Glassrad")
        elif index == 14:
            table("signature-details", 223, "Én rad per prøve, lege og rolle · godkjenningsperiode", "Signeringer",
                ["Prøvenummer", "Lege", "Rolle", "Gruppe", "Prioritet", "GodkjentTid", "LegeDager", "SvartidDager", "Tidsstatus"], h=395, metric="Legerad")
        elif index == 15:
            page.textbox("quality", 204, 88, 1048, 210, [("Datakvalitet i dette uttrekket", 18, base.C["blue"], True),
                (f"{audit['source_rows']:,} rader → {audit['samples']:,} prøver → {audit['unique_glass']:,} unike glass.", 13, base.C["text"], False),
                (f"{audit['rows_without_glass']} rader uten GlassId teller ikke som glass. Ingen motstridende gjentatte glassverdier.", 12, base.C["text"], False),
                (f"{audit['approved_with_uncolored_glass']} godkjente prøver har ufargede glass; dette er separate arbeidslister.", 12, base.C["text"], False),
                (f"{audit['approved_missing_doctor_interval']} godkjente prøver mangler entydig legeintervall. {audit['valid_chains']} komplette monotone kjeder.", 12, base.C["text"], False),
                (f"{audit['collection_after_arrival_samples']} prøver har prøvetaking etter ankomst, inkludert fremtidige datoer.", 12, base.C["red"], False)], True)
            page.table("quality-groups", 204, 316, 1048, 300, "Dekning og foreløpige varselgrenser", [c("Grupper", f) for f in ["Gruppe", "Datadekning", "VarselDager", "GrunnlagN", "Grensegrunnlag"]])
        elif index == 16:
            cards([("Prøver", "Mottatte prøver", "Unike prøvenumre", base.C["blue"]),
                ("Prøver", "Antall glass", "Unike glass", base.C["teal"]),
                ("Prøver", "Glass per prøve", "Glass per prøve", base.C["amber"]),
                ("Prøver", "Prøver med etterbestilling", "Prøver med ekstra glass", base.C["green"])])
            chart("glass-load", "clusteredColumnChart", 204, 278, 520, 340, "Prøver etter antall glass", "Prøver", "Glassmengde", ["Mottatte prøver"])
            chart("glass-time", "clusteredColumnChart", 740, 278, 512, 340, "Svartid per glassmengde · median dager", "Prøver", "Glassmengde", ["Median svartid dager"],
                subtitle="Godkjenningsperiode · hvert prøvenummer teller én gang")
        elif index == 18:
            cards([("Signeringer", "Signerte prøver", "Unike godkjente prøver", base.C["blue"]),
                ("Signeringer", "Lege median farget til godkjent", "Median farget → godkjent", base.C["teal"]),
                ("Signeringer", "Lege P90 farget til godkjent", "P90 farget → godkjent", base.C["amber"]),
                ("Signeringer", "Lege N tid", "Prøver med gyldig tid", base.C["green"])], 223)
            chart("doctor-week-volume", "clusteredColumnChart", 204, 328, 520, 290, "Godkjente prøver per uke", "Periode", "ÅrUke", ["Signerte prøver"], "Signeringer")
            chart("doctor-week-time", "lineChart", 740, 328, 512, 290, "Forløpstid per uke · valgt lege og rolle", "Periode", "ÅrUke", ["Lege median farget til godkjent", "Lege P90 farget til godkjent"], "Signeringer")
        elif index == 19:
            cards([("Prøver", "Godkjente prøver", "Godkjente prøver", base.C["blue"]),
                ("Prøver", "Median svartid dager", "Median ankomst → godkjent", base.C["teal"]),
                ("Prøver", "Gjennomsnitt svartid", "Gjennomsnitt · dager", base.C["amber"]),
                ("Prøver", "P90 svartid", "P90 · dager", base.C["green"])])
            chart("time-week", "lineChart", 204, 278, 1048, 340, "Ankomst → godkjent per uke", "Periode", "ÅrUke", ["Median svartid dager", "Gjennomsnitt svartid", "P90 svartid"],
                subtitle="Godkjenningsperiode · prøver teller én gang · P90: 90 prosent var raskere")
        else:
            notes = [
                ("Antall og periode", ["Prøver og glass telles hver for seg; gjentatte legeroller gir ikke flere glass.",
                    "Blått = mottatt etter ankomst. Grønt = godkjent etter godkjenningsdato.",
                    "Restanse og glass følger valgt ankomstperiode. Alle måneder = hele uttrekksutvalget."]),
                ("Tider og sammenlikning", ["Stablede stolper: gjennomsnitt av fem trinn på samme komplette prøveutvalg.",
                    "Kun førstebestilte glass i kjeden; alle må ha gyldig tidsrekkefølge. N vises.",
                    "Legetid er prøvens forløp fra farget til godkjent. Kilden har ikke separat signeringstid per rolle."]),
                ("Foreløpig grense og uttrekk", ["Rød grense er gruppens P90 fra godkjente prøver, avrundet opp til hele dager.",
                    "Minst 30 godkjente per gruppe; ellers samlet P90 = 21 dager. Ingen fastsatt svarfrist.",
                    "Referansetid 15.10.2026 12:37 er siste prosesstempel; kilden har ikke uttrekkstid."]),
            ]
            for j, (heading, lines) in enumerate(notes):
                page.textbox(f"note{j}", 204, 88 + j * 178, 1048, 164,
                    [(heading, 17, base.C["blue"], True)] + [(t, 12, base.C["text"], False) for t in lines], True)
        if not about:
            note = "Legetider er forløpstid · rollefiltrert · N viser beregnbare tider" if index in [5, 6, 14, 18] else "Restanse/glass: ankomstperiode · godkjenning/tider: godkjenningsperiode · siste prosesstempel 15.10.2026"
            if index == 6:
                note = "Prøver telles én gang per lege/rolle · samme prøve kan inngå hos flere leger og i flere roller"
            elif index == 9:
                note = "Etterbestilt = Glass etterbestilt er utfylt i kilden · årsaken til bestillingen er ikke oppgitt"
            elif index == 16:
                note = "1 prøve med 5 glass = 1 prøve og 5 glass · velg prosessgruppe og prioritet for sammenlikning"
            page.textbox("footer", 204, 662, 1048, 40, [(note, 10, base.C["muted"], False)])
    dump(REPORT / "definition/pages/pages.json", {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [p[0] for p in PAGES], "activePageName": PAGES[0][0]})


def rename_tree(node, mapping):
    if isinstance(node, dict):
        return {k: rename_tree(v, mapping) for k, v in node.items()}
    if isinstance(node, list):
        return [rename_tree(v, mapping) for v in node]
    if isinstance(node, str):
        if node in mapping:
            return mapping[node]
        for before, after in mapping.items():
            node = node.replace(before, after)
        return node
    return node


def build_restanse():
    with zipfile.ZipFile(REFERENCE) as z:
        docs = {n: json.loads(z.read(n)) for n in z.namelist() if n.startswith("Report/definition/") and n.endswith(".json")}
        cards = sorted([n for n in docs if "/visuals/analysis-card" in n], key=lambda n: 0 if "/analysis-cards/" in n else int(n.split("analysis-card-")[1].split("/")[0]))
        removed = set()
        for i, name in enumerate(cards):
            if i >= len(GROUPS):
                removed.add(docs[name]["name"]); del docs[name]; continue
            d = docs[name]
            old = d["filterConfig"]["filters"][0]["filter"]["Where"][0]["Condition"]["In"]["Values"][0][0]["Literal"]["Value"]
            d = rename_tree(d, {old: "'" + GROUPS[i] + "'"})
            # Replace all card projections: open samples, median age, pending glass.
            d["visual"]["query"]["queryState"]["Data"]["projections"] = [base.measure("Prøver", n) for n in ["Åpne prøver", "Median alder restanse", "Ufargede glass"]]
            for projection, label in zip(d["visual"]["query"]["queryState"]["Data"]["projections"], ["Åpne", "Median · d", "Ufarget"]):
                projection["nativeQueryRef"] = label
                projection["displayName"] = label
            title = d["visual"]["visualContainerObjects"]["title"][0]["properties"]
            title["text"] = base.lit("'" + GROUPS[i] + "'")
            title["show"] = base.lit("true")
            coverage = {r["Gruppe"]: r["Datadekning"] for r in csv.DictReader((DATA / "Grupper.csv").open(encoding="utf-8-sig"), delimiter=";")}
            subtitle = d["visual"]["visualContainerObjects"].setdefault("subTitle", [{"properties": {}}])[0]["properties"]
            subtitle["show"] = base.lit("true" if coverage[GROUPS[i]] != "Med data" else "false")
            subtitle["text"] = base.lit("'Ingen prøver i uttrekket'")
            docs[name] = d
        # Preserve visual styles and replace the original model bindings.
        mapping = {"DimAnalysegruppe": "Grupper", "Analysegruppe_kode": "Gruppe", "Analysegruppe": "Gruppe", "Restanse": "Prøver",
            "Siste observasjon": "Datatid", "Antall analyser": "Åpne prøver", "Alder dager": "AlderDager",
            "Over svarfrist": "Over foreløpig grense", "Antall ready": "Mottatte prøver", "Antall avventer godkjenning": "Ufargede glass",
            "Valgt analysegruppe": "Valgt gruppe", "Median alder timer": "Median alder restanse"}
        for name, d in list(docs.items()):
            docs[name] = rename_tree(d, mapping)
        page_name = "c3b2365a0015035e0110"
        page_key = f"Report/definition/pages/{page_name}/page.json"
        page = docs[page_key]
        page["displayName"] = "Patologi Restanse"
        page.pop("filterConfig", None)  # One current snapshot, no Hemato history field.
        page["visualInteractions"] = [i for i in page.get("visualInteractions", []) if i["source"] not in removed and i["target"] not in removed]
        for name, d in docs.items():
            if name.endswith("/brand/visual.json"):
                runs = d["visual"]["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"]
                runs[0]["value"] = "Patologi "
                runs[1]["value"] = "Restanse"
                d["position"]["width"] = 590
            if name.endswith("/analysis-dropdown/visual.json"):
                d["position"].update(x=1610, y=12, width=285, height=80)
            if name.endswith("/last-observed/visual.json"):
                d["position"].update(x=1210, y=14, width=375)
                d["visual"]["query"]["queryState"]["Data"]["projections"] = [base.measure("Prøver", "Datatid")]
                for item in d["visual"]["objects"].get("label", []):
                    item["properties"]["text"] = base.lit("'Referansetid · siste prosesstempel'")
            if name.endswith("/detail-table/visual.json"):
                d["visual"]["query"]["queryState"]["Values"]["projections"] = [base.column("Prøver", n) for n in
                    ["Prøvenummer", "Gruppe", "Prioritet", "Ankomst", "Hovedlege", "Status", "AntallGlass", "UfargedeGlass", "AlderDager", "VarselDager"]]
                for projection in d["visual"]["query"]["queryState"]["Values"]["projections"]:
                    projection["nativeQueryRef"] = FIELD_LABELS.get(projection["nativeQueryRef"], projection["nativeQueryRef"])
                d["visual"]["query"].pop("sortDefinition", None)
                # Preserve the readable dark table style, drop only old
                # per-column rules that refer to Hemato fields.
                d["visual"]["objects"] = {key: [entry for entry in entries if not entry.get("selector")]
                    for key, entries in d["visual"]["objects"].items()}
                row_filter(d, "Prøver", "Restanserad")
            if name.endswith("/legend/visual.json"):
                paragraphs = d["visual"]["objects"]["general"][0]["properties"]["paragraphs"]
                labels = ["Rød: over foreløpig P90-grense", "Lilla: glass ikke ferdig farget", "Grønn: åpne uten varsler", "Grå: ingen åpne i utvalget"]
                for line, label in zip(paragraphs, labels):
                    line["textRuns"][0]["value"] = label
            for suffix, metric, label in [("kpi-total", "Mottatte prøver", "Mottatt i valgt måned"),
                ("kpi-ready", "Godkjente prøver", "Godkjent i valgt måned"), ("kpi-approval", "Ufargede glass", "Glass ikke ferdig farget"),
                ("kpi-age", "Median alder restanse", "Median alder åpne · dager"), ("kpi-overdue", "Over foreløpig grense", "Over foreløpig grense")]:
                if name.endswith(f"/{suffix}/visual.json"):
                    d["visual"]["query"]["queryState"]["Data"]["projections"] = [base.measure("Prøver", metric)]
                    d.pop("filterConfig", None)
                    for item in d["visual"]["objects"].get("value", []):
                        item["properties"]["labelDisplayUnits"] = base.lit("1D")
                        item["properties"]["labelPrecision"] = base.lit("1L" if suffix == "kpi-age" else "0L")
                    for item in d["visual"]["objects"].get("label", []):
                        if "text" in item["properties"]:
                            item["properties"]["text"] = base.lit("'" + label + "'")
        # Add compact year/month selectors using the same native slicer contract.
        template = copy.deepcopy(docs[next(n for n in docs if n.endswith("/analysis-dropdown/visual.json"))])
        for vid, field, label, x, width, value in [("period-year", "År", "År", 610, 180, 2026), ("period-month", "Måned", "Måned", 800, 260, "oktober")]:
            d = copy.deepcopy(template); d["name"] = vid; d["position"].update(x=x, y=12, width=width, height=80)
            d["visual"]["query"]["queryState"]["Values"]["projections"] = [base.column("Periode", field)]
            d["visual"]["objects"].pop("general", None)
            d.pop("filterConfig", None)
            d["visual"]["visualContainerObjects"]["title"][0]["properties"]["text"] = base.lit("'" + label + "'")
            docs[f"Report/definition/pages/{page_name}/visuals/{vid}/visual.json"] = d
        # The first two small top selectors default to October; selection remains editable.
        for name, doc in docs.items():
            dump(REST / name.removeprefix("Report/"), doc)
        fake = type("Page", (), {"visuals": REST / "definition/pages" / page_name / "visuals"})()
        selection(fake, "period-year", "Periode", "År", 2026, True)
        selection(fake, "period-month", "Periode", "Måned", "oktober")
        # Reset button in source occupies the selector area: place below header.
        reset = fake.visuals / "f7eed2af534861d0b5b0/visual.json"
        d = json.loads(reset.read_text("utf8")); d["position"].update(x=1070, y=22, width=120, height=60); dump(reset, d)
        # Reset bookmark must know the new selectors and cannot reference deleted cards.
        for path in (REST / "definition/bookmarks").glob("*.bookmark.json"):
            d = json.loads(path.read_text("utf8"))
            targets = ["analysis-dropdown"] + [docs[n]["name"] for n in cards if n in docs]
            d["options"]["targetVisualNames"] = targets
            states = {"analysis-dropdown": {"singleVisual": {"visualType": "slicer", "objects": {}}}}
            for name in cards:
                if name not in docs:
                    continue
                card = docs[name]
                states[card["name"]] = {"filters": {"byExpr": [{k: f[k] for k in ("name", "type", "filter") if k in f}
                    for f in card.get("filterConfig", {}).get("filters", [])]},
                    "singleVisual": {"visualType": "cardVisual", "objects": {}}}
            d["explorationState"] = {"version": "1.3", "activeSection": page_name, "sections": {
                page_name: {"visualContainers": states}}}
            dump(path, d)
        for n in z.namelist():
            if n.startswith("Report/StaticResources/"):
                path = REST / n.removeprefix("Report/"); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(z.read(n))
    # Replace Hemato-specific help with compact, correct pathology definitions.
    help_dir = REST / "definition/pages/restanse-forklaringer/visuals"
    for path in help_dir.glob("*/visual.json"):
        doc = json.loads(path.read_text("utf8"))
        paragraphs = doc["visual"].get("objects", {}).get("general", [{}])[0].get("properties", {}).get("paragraphs", [])
        for paragraph in paragraphs:
            for run in paragraph.get("textRuns", []):
                run["value"] = run.get("value", "").replace("analyse", "prøve").replace("Analyse", "Prøve").replace("Hemato", "Patologi")
        replacements = {
            "guide-priority": ["Farger: rød = over foreløpig grense · lilla = ufargede glass · grønn = åpne uten varsler"],
            "guide-status-red": ["Rød: foreløpig grense", "Minst én åpen prøve er eldre enn gruppens foreløpige P90-grense."],
            "guide-status-yellow": ["Datadekning", "Grå kort kan bety at gruppen ikke finnes i uttrekket, ikke at laboratoriet har null restanse."],
            "guide-status-purple": ["Lilla: ufargede glass", "Det finnes glass uten Ferdig farget på prøver i valgt ankomstperiode."],
            "guide-status-green": ["Grønn: åpne uten varsler", "Åpne prøver finnes, men ingen er over grensen og ingen glass mangler farging."],
            "guide-row-vs-card": ["Prøver og glass er forskjellige", "1 prøve med 5 glass = 1 prøve og 5 glass. Prøvenummer er ikke en unik pasient.", "Etterbestilt betyr at Glass etterbestilt er utfylt; årsaken er ikke oppgitt.", "Godkjente prøver kan fortsatt ha ufargede etterbestillinger."],
            "guide-deadline": ["Foreløpig grense", "Gruppens P90 ankomst → godkjent avrundes opp. Minst 30 godkjente; ellers samlet 21 dager.", "Dette er en databasert varselgrense, ikke en avtalt svarfrist."],
            "guide-card-numbers": ["Kortene", "Åpne prøver: mangler Godkjent dato.", "Median alder: dager fra ankomst til referansetid.", "Ufargede glass: unike glass uten Ferdig farget."],
            "guide-top-kpis": ["Nøkkeltall", "Blå: mottatt i valgt periode. Grønn: godkjent i valgt periode.", "Lilla: ufargede glass på periodens ankomster. Rød: åpne over foreløpig grense."],
            "guide-usage": ["Periode og kildedekning", "Velg år/måned øverst. Restanse og glass følger ankomstperioden.", "Referansetid: 15.10.2026 12:37, siste prosesstempel. Kun ett laboratorium og åtte av nitten grupper har data."]}
        if path.parent.name in replacements and paragraphs:
            style = paragraphs[0]["textRuns"][0].get("textStyle", {})
            doc["visual"]["objects"]["general"][0]["properties"]["paragraphs"] = [
                {"textRuns": [{"value": text, "textStyle": style | {"fontSize": "20pt" if i == 0 else "17pt"}}]} for i, text in enumerate(replacements[path.parent.name])]
        dump(path, doc)


def pbit(report, model, target):
    with zipfile.ZipFile(REFERENCE) as z, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out:
        for name in ["Version", "[Content_Types].xml", "Settings", "Metadata", "Connections"]:
            b = z.read(name)
            if name == "[Content_Types].xml":
                b = b.decode("utf-8-sig").replace('/DataModel"', '/DataModelSchema"').encode("utf8")
            out.writestr(name, b)
        out.writestr("DataModelSchema", json.dumps(model, ensure_ascii=False).encode("utf-16-le"))
        for path in report.rglob("*"):
            if path.is_file() and path.suffix == ".json":
                out.write(path, "Report/" + path.relative_to(report).as_posix())


def build():
    data = process_rows(read_source(SOURCE))
    model = create_model(data)
    dump(PROJECT / "Model/database.json", model)
    build_statistics(data["audit"])
    build_restanse()
    finish_reports(data["audit"])
    pbit(REPORT, model, PROJECT / "Patolog_Statistikk.pbit")
    pbit(REST, model, PROJECT / "Patolog_Restanse.pbit")
    print(json.dumps(data["audit"], ensure_ascii=False, indent=2))


def finish_reports(audit):
    """Use full numeric labels, chronological axes and current source metadata."""
    stamp = datetime.fromisoformat(audit["as_of"]).strftime("%d.%m.%Y %H:%M")
    first = datetime.fromisoformat(audit["arrival_from"]).strftime("%d.%m.%Y")
    last = datetime.fromisoformat(audit["arrival_to"]).strftime("%d.%m.%Y")
    replacements = {"15.10.2026 12:37": stamp, "siste prosesstempel 15.10.2026": "siste prosesstempel " + stamp,
        "15.09–15.10.2026": first + "–" + last,
        "samlet P90 = 21 dager": f"samlet P90 = {audit['global_p90_days']} dager",
        "ellers samlet 21 dager": f"ellers samlet {audit['global_p90_days']} dager",
        "Mangler uttrekkstid og filterparametre, profil, endringslogg og signeringstype per versjon.":
        "Mangler uttrekkstid, profil, makrolege og separat signeringstid per legerolle."}
    for report in (REPORT, REST):
        for path in (report / "definition").rglob("*.json"):
            doc = rename_tree(json.loads(path.read_text("utf-8")), replacements)
            visual = doc.get("visual", {})
            kind = visual.get("visualType", "")
            objects = visual.setdefault("objects", {}) if visual else {}
            if "chart" in kind.lower():
                objects.setdefault("valueAxis", [{"properties": {}}])[0]["properties"].update(
                    labelDisplayUnits=base.lit("1D"), secLabelDisplayUnits=base.lit("1D"))
            for key in ("labels", "value", "calloutValue", "referenceLabel"):
                for entry in objects.get(key, []):
                    entry["properties"]["labelDisplayUnits"] = base.lit("1D")
            query = visual.get("query", {})
            for projection in query.get("queryState", {}).get("Category", {}).get("projections", []):
                column = projection.get("field", {}).get("Column", {})
                entity = column.get("Expression", {}).get("SourceRef", {}).get("Entity")
                if entity == "Periode" or column.get("Property") in {"Aldersgruppe", "Glassmengde"}:
                    query["sortDefinition"] = {"sort": [{"field": projection["field"], "direction": "Ascending"}]}
                if report == REPORT and entity == "Grupper":
                    doc["filterConfig"] = {"filters": [{"name": "groupsWithSourceRows",
                        "field": base.column("Grupper", "Datadekning")["field"], "type": "Categorical",
                        "filter": {"Version": 2, "From": [{"Name": "g", "Entity": "Grupper", "Type": 0}],
                            "Where": [{"Condition": {"In": {"Expressions": [{"Column": {
                                "Expression": {"SourceRef": {"Source": "g"}}, "Property": "Datadekning"}}],
                                "Values": [[{"Literal": {"Value": "'Med data'"}}]]}}}]}}]}
            dump(path, doc)


if __name__ == "__main__":
    build()
