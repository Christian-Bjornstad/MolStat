from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "powerbi" / "Hemato_Statistikk_Optimert"
REPORT = PROJECT / "Hemato Statistikk Rapport.Report"
DEFINITION = REPORT / "definition"
PAGES = DEFINITION / "pages"
RESOURCES = REPORT / "StaticResources" / "RegisteredResources"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.12.0/schema.json"

C = {
    "nav": "#0B3154",
    "nav_selected": "#145B86",
    "canvas": "#F4F7FA",
    "panel": "#FFFFFF",
    "border": "#D7E0E8",
    "text": "#172B3A",
    "muted": "#526579",
    "blue": "#0B4F7A",
    "teal": "#007A78",
    "green": "#0F766E",
    "amber": "#A15C00",
    "red": "#B42318",
    "pale_blue": "#EAF2F8",
    "pale_teal": "#E7F5F3",
    "pale_amber": "#FFF4DC",
    "pale_red": "#FDECEA",
}

PAGE_DEFS = [
    ("1f0a1111111111111111", "Ledelsesoversikt"),
    ("2f0a2222222222222222", "Volum og kapasitet"),
    ("3f0a3333333333333333", "Svartid"),
    ("4f0a4444444444444444", "Oppfølging"),
    ("5f0a5555555555555555", "Datakvalitet"),
]


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def lit(value: str) -> dict[str, Any]:
    return {"expr": {"Literal": {"Value": value}}}


def solid(color: str) -> dict[str, Any]:
    return {"solid": {"color": lit(f"'{color}'")}}


def column(entity: str, prop: str) -> dict[str, Any]:
    return {
        "field": {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
        "queryRef": f"{entity}.{prop}",
        "nativeQueryRef": prop,
    }


def measure(entity: str, prop: str) -> dict[str, Any]:
    return {
        "field": {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
        "queryRef": f"{entity}.{prop}",
        "nativeQueryRef": prop,
    }


def sum_column(entity: str, prop: str) -> dict[str, Any]:
    return {
        "field": {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}, "Function": 0}},
        "queryRef": f"Sum({entity}.{prop})",
        "nativeQueryRef": f"Sum of {prop}",
    }


def position(x: int, y: int, w: int, h: int, z: int) -> dict[str, Any]:
    return {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z}


def container(title: str = "", subtitle: str = "") -> dict[str, Any]:
    title_props = {
        "show": lit("true" if title else "false"),
        "text": lit(f"'{title}'"),
        "fontFamily": lit("'Segoe UI Semibold'"),
        "fontSize": lit("13D"),
        "fontColor": solid(C["text"]),
        "titleWrap": lit("true"),
    }
    result: dict[str, Any] = {
        "title": [{"properties": title_props}],
        "background": [{"properties": {"show": lit("true"), "color": solid(C["panel"]), "transparency": lit("0D")}}],
        "border": [{"properties": {"show": lit("true"), "color": solid(C["border"]), "width": lit("1D"), "radius": lit("10D")}}],
        "padding": [{"properties": {"top": lit("8D"), "bottom": lit("8D"), "left": lit("8D"), "right": lit("8D")}}],
        "visualTooltip": [{"properties": {"show": lit("true")}}],
    }
    if subtitle:
        result["subTitle"] = [{"properties": {"show": lit("true"), "text": lit(f"'{subtitle}'"), "fontSize": lit("9D"), "fontColor": solid(C["muted"])}}]
    return result


class Page:
    def __init__(self, page_id: str, display_name: str, subtitle: str, event_date: str) -> None:
        self.page_id = page_id
        self.root = PAGES / page_id
        self.visuals = self.root / "visuals"
        self.visuals.mkdir(parents=True, exist_ok=True)
        self.next_z = 0
        dump(
            self.root / "page.json",
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
                "name": page_id,
                "displayName": display_name,
                "displayOption": "FitToPage",
                "height": 720,
                "width": 1280,
                "objects": {
                    "background": [{"properties": {"color": solid(C["canvas"]), "transparency": lit("0D")}}],
                    "outspace": [{"properties": {"color": solid(C["canvas"]), "transparency": lit("0D")}}],
                },
            },
        )
        self.shape("nav-bg", 0, 0, 184, 720, C["nav"])
        self.textbox("brand", 18, 18, 150, 72, [("OUS", 24, "#FFFFFF", True), ("Hematologi", 11, "#CFE3F2", False)])
        self.navigator("navigation", 14, 130, 156, 360)
        self.textbox("nav-help", 18, 620, 148, 72, [("Dato i visningen", 10, "#CFE3F2", True), (event_date, 9, "#FFFFFF", False)])
        self.textbox("page-title", 208, 16, 590, 44, [(display_name, 24, C["text"], True)])
        self.textbox("page-subtitle", 208, 56, 620, 32, [(subtitle, 10, C["muted"], False)])
        self.slicer("filter-year", 844, 18, 118, 58, "Dato", "År", "År")
        self.slicer("filter-month", 974, 18, 142, 58, "Dato", "Måned", "Måned")
        self.slicer("filter-week", 1128, 18, 128, 58, "Dato", "ÅrUke", "Uke")

    def write_visual(self, visual_id: str, visual: dict[str, Any], x: int, y: int, w: int, h: int) -> None:
        self.next_z += 1
        dump(
            self.visuals / visual_id / "visual.json",
            {"$schema": SCHEMA, "name": visual_id, "position": position(x, y, w, h, self.next_z), "visual": visual},
        )

    def shape(self, visual_id: str, x: int, y: int, w: int, h: int, color: str) -> None:
        self.write_visual(
            visual_id,
            {
                "visualType": "shape",
                "objects": {
                    "shape": [{"properties": {"tileShape": lit("'rectangle'")}}],
                    "outline": [{"properties": {"show": lit("false")}}],
                    "fill": [{"properties": {"fillColor": solid(color), "transparency": lit("0D")}, "selector": {"id": "default"}}],
                },
                "drillFilterOtherVisuals": True,
            },
            x, y, w, h,
        )

    def textbox(self, visual_id: str, x: int, y: int, w: int, h: int, rows: list[tuple[str, int, str, bool]], panel: bool = False) -> None:
        paragraphs = [
            {"textRuns": [{"value": text, "textStyle": {"fontFamily": "Segoe UI Semibold" if bold else "Segoe UI", "fontSize": f"{size}pt", "color": color}}]}
            for text, size, color, bold in rows
        ]
        objects: dict[str, Any] = {"general": [{"properties": {"paragraphs": paragraphs}}]}
        self.write_visual(
            visual_id,
            {
                "visualType": "textbox",
                "objects": objects,
                "visualContainerObjects": {
                    "title": [{"properties": {"show": lit("false")}}],
                    "background": [{"properties": {"show": lit("true" if panel else "false"), "color": solid(C["panel"]), "transparency": lit("0D")}}],
                    "border": [{"properties": {"show": lit("true" if panel else "false"), "color": solid(C["border"]), "width": lit("1D"), "radius": lit("10D")}}],
                    "padding": [{"properties": {"top": lit("8D"), "bottom": lit("8D"), "left": lit("10D"), "right": lit("10D")}}],
                },
                "drillFilterOtherVisuals": True,
            },
            x, y, w, h,
        )

    def navigator(self, visual_id: str, x: int, y: int, w: int, h: int) -> None:
        self.write_visual(
            visual_id,
            {
                "visualType": "pageNavigator",
                "objects": {
                    "pages": [{"properties": {"showByDefault": lit("true")}}],
                    "shape": [{"properties": {"tileShape": lit("'rectangleRounded'")}, "selector": {"id": "default"}}],
                    "fill": [
                        {"properties": {"show": lit("true"), "fillColor": solid(C["nav"]), "transparency": lit("100D")}, "selector": {"id": "default"}},
                        {"properties": {"show": lit("true"), "fillColor": solid(C["nav_selected"]), "transparency": lit("0D")}, "selector": {"id": "selected"}},
                    ],
                    "outline": [{"properties": {"show": lit("false")}}],
                    "text": [
                        {"properties": {"fontFamily": lit("'Segoe UI'"), "fontSize": lit("11D"), "fontColor": solid("#FFFFFF")}, "selector": {"id": "default"}},
                        {"properties": {"fontFamily": lit("'Segoe UI Semibold'"), "fontSize": lit("11D"), "fontColor": solid("#FFFFFF")}, "selector": {"id": "selected"}},
                    ],
                },
                "drillFilterOtherVisuals": True,
            },
            x, y, w, h,
        )

    def slicer(self, visual_id: str, x: int, y: int, w: int, h: int, entity: str, field: str, title: str) -> None:
        self.write_visual(
            visual_id,
            {
                "visualType": "slicer",
                "query": {"queryState": {"Values": {"projections": [column(entity, field)]}}},
                "objects": {
                    "data": [{"properties": {"mode": lit("'Dropdown'")}}],
                    "selection": [{"properties": {"singleSelect": lit("false"), "strictSingleSelect": lit("false")}}],
                    "items": [{"properties": {"fontFamily": lit("'Segoe UI'"), "fontColor": solid(C["text"])}}],
                },
                "visualContainerObjects": container(title),
                "drillFilterOtherVisuals": True,
            },
            x, y, w, h,
        )

    def card(self, visual_id: str, x: int, y: int, w: int, h: int, entity: str, metric: str, label: str, accent: str, subtitle: str = "") -> None:
        self.write_visual(
            visual_id,
            {
                "visualType": "cardVisual",
                "query": {"queryState": {"Data": {"projections": [measure(entity, metric)]}}},
                "objects": {
                    "fillCustom": [{"properties": {"show": lit("true"), "fillColor": solid(C["panel"]), "transparency": lit("0D")}, "selector": {"id": "default"}}],
                    "accentBar": [{"properties": {"show": lit("true"), "position": lit("'Top'"), "width": lit("5D"), "color": solid(accent)}, "selector": {"id": "default"}}],
                    "outline": [{"properties": {"show": lit("false")}, "selector": {"id": "default"}}],
                    "shapeCustomRectangle": [{"properties": {"tileShape": lit("'rectangleRoundedByPixel'"), "rectangleRoundedCurve": lit("10L")}}],
                    "value": [{"properties": {"fontFamily": lit("'Segoe UI Semibold'"), "fontSize": lit("24D"), "bold": lit("true"), "fontColor": solid(C["text"]), "horizontalAlignment": lit("'Left'")}, "selector": {"id": "default"}}],
                    "label": [{"properties": {"show": lit("true"), "text": lit(f"'{label}'"), "fontFamily": lit("'Segoe UI Semibold'"), "fontSize": lit("10D"), "fontColor": solid(C["muted"]), "position": lit("'aboveValue'"), "horizontalAlignment": lit("'Left'")}, "selector": {"id": "default"}}],
                },
                "visualContainerObjects": container("", subtitle),
                "drillFilterOtherVisuals": True,
            },
            x, y, w, h,
        )

    def chart(self, visual_id: str, visual_type: str, x: int, y: int, w: int, h: int, title: str, subtitle: str, roles: dict[str, list[dict[str, Any]]]) -> None:
        query_state = {role: {"projections": projections} for role, projections in roles.items()}
        self.write_visual(
            visual_id,
            {
                "visualType": visual_type,
                "query": {"queryState": query_state},
                "objects": {
                    "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}],
                    "labels": [{"properties": {"show": lit("false")}}],
                    "categoryAxis": [{"properties": {"show": lit("true"), "showAxisTitle": lit("false"), "concatenateLabels": lit("false")}}],
                    "valueAxis": [{"properties": {"show": lit("true"), "showAxisTitle": lit("false"), "gridlineStyle": lit("'dotted'")}}],
                },
                "visualContainerObjects": container(title, subtitle),
                "drillFilterOtherVisuals": True,
            },
            x, y, w, h,
        )

    def table(self, visual_id: str, x: int, y: int, w: int, h: int, title: str, fields: list[dict[str, Any]]) -> None:
        self.write_visual(
            visual_id,
            {
                "visualType": "tableEx",
                "query": {"queryState": {"Values": {"projections": fields}}},
                "objects": {
                    "columnHeaders": [{"properties": {"autoSizeColumnWidth": lit("true"), "fontFamily": lit("'Segoe UI Semibold'"), "fontSize": lit("10D"), "fontColor": solid("#FFFFFF"), "backColor": solid(C["blue"]), "wordWrap": lit("true")}}],
                    "values": [{"properties": {"fontFamily": lit("'Segoe UI'"), "fontSize": lit("9D"), "fontColorPrimary": solid(C["text"]), "fontColorSecondary": solid(C["text"]), "backColorPrimary": solid("#FFFFFF"), "backColorSecondary": solid("#F7F9FB"), "wordWrap": lit("false")}}],
                    "grid": [{"properties": {"gridVertical": lit("false"), "gridHorizontal": lit("true"), "rowPadding": lit("5D"), "gridHorizontalColor": solid(C["border"])}}],
                },
                "visualContainerObjects": container(title),
                "drillFilterOtherVisuals": True,
            },
            x, y, w, h,
        )


def build_leadership(page: Page) -> None:
    cards = [
        ("total", "antall", "Antall analyser", "Analyser", C["blue"], "Bestillinger i valgt periode"),
        ("patient", "resultater", "Median pasientforløp dager", "Pasientforløp", C["teal"], "Prøve → analyseresultat"),
        ("section", "resultater", "Median seksjonstid dager", "Seksjonstid", C["green"], "Bestilling → analyseresultat"),
        ("unit", "resultater", "Median enhetstid dager", "Enhetstid", C["amber"], "Seneste operative start"),
        ("sla", "resultater", "Andel innen individuell frist", "Innen frist", C["blue"], "Valgt perspektiv • individuell frist"),
    ]
    for idx, (vid, entity, metric, label, accent, note) in enumerate(cards):
        page.card(f"kpi-{vid}", 208 + idx * 210, 100, 198, 120, entity, metric, label, accent, note)
    tips = [measure("resultater", "Antall gyldige svartider"), measure("resultater", "P90 svartid dager"), measure("resultater", "Antall ekskludert datakvalitet")]
    page.chart("weekly-volume", "lineChart", 208, 244, 506, 238, "Volum per uke", "Analysebestillingsdato • 4-ukers nivå som kapasitetsreferanse", {"Category": [column("Dato", "ÅrUke")], "Y": [measure("antall", "Antall analyser"), measure("resultater", "Fireukers glidende volum")], "Tooltips": tips})
    page.chart("group-p90", "clusteredBarChart", 730, 244, 526, 238, "Svartid per rapportgruppe", "P90 og median • velg perspektiv på Svartid-siden", {"Category": [column("resultater", "Rapportgruppe")], "Y": [measure("resultater", "Median svartid dager"), measure("resultater", "P90 svartid dager")], "Tooltips": tips + [measure("resultater", "Andel innen individuell frist")]})
    page.textbox("definitions", 208, 500, 720, 164, [("Tre perspektiver – samme sluttpunkt", 13, C["blue"], True), ("Pasientforløp: prøvetaking → analyseresultat", 10, C["text"], False), ("Seksjonstid: analysebestilling → analyseresultat", 10, C["text"], False), ("Enhetstid: seneste av bestilling og ekstraksjon → analyseresultat", 10, C["text"], False), ("Godkjenningsetterslep vises separat.", 10, C["muted"], False)], panel=True)
    page.card("dq-warning", 944, 500, 312, 164, "resultater", "Datakvalitet avvik", "Datakvalitet", C["red"], "Synlige avvik • åpne Datakvalitet for detaljer")


def build_volume(page: Page) -> None:
    cards = [
        ("volume", "antall", "Antall analyser", "Analyser", C["blue"], "Analysebestillinger"),
        ("previous", "antall", "Antall analyser forrige periode", "Forrige måned", C["teal"], "Samme filterkontekst"),
        ("change", "antall", "Endring analyser prosent", "Endring", C["amber"], "Mot forrige måned"),
        ("rolling", "resultater", "Fireukers glidende volum", "4-ukers nivå", C["green"], "Gjennomsnitt per uke"),
    ]
    for idx, (vid, entity, metric, label, accent, note) in enumerate(cards):
        page.card(f"kpi-{vid}", 208 + idx * 262, 100, 246, 116, entity, metric, label, accent, note)
    volume_tips = [measure("resultater", "Lavvolumgrense P10"), measure("antall", "Endring analyser prosent")]
    page.chart("volume-week", "lineChart", 208, 240, 676, 250, "Ukevolum og fireukers trend", "Lave uker identifiseres mot historisk P10 – beslutningsstøtte, ikke bemanningsfasit", {"Category": [column("Dato", "ÅrUke")], "Y": [measure("antall", "Antall analyser"), measure("resultater", "Fireukers glidende volum"), measure("resultater", "Lavvolumgrense P10")], "Tooltips": volume_tips})
    page.chart("volume-group", "clusteredBarChart", 900, 240, 356, 250, "Volum per rapportgruppe", "Klikk for å filtrere resten av siden", {"Category": [column("antall", "Rapportgruppe")], "Y": [measure("antall", "Antall analyser")], "Tooltips": volume_tips})
    page.chart("volume-analysis", "clusteredBarChart", 208, 510, 1048, 174, "Analyser med høyest volum", "Bruk rapportgruppefilteret i visualet for detaljering", {"Category": [column("antall", "Analyse")], "Y": [measure("antall", "Antall analyser")], "Tooltips": volume_tips})


def build_turnaround(page: Page) -> None:
    page.slicer("perspective", 208, 96, 412, 68, "Svartidsperspektiv", "Perspektiv", "Velg svartidsperspektiv")
    page.textbox("perspective-help", 636, 96, 620, 68, [("Alle mål under bruker samme sluttpunkt: analyseresultat", 11, C["blue"], True), ("Frist vurderes rad for rad. Stiplet målverdi brukes bare når én frist er entydig.", 9, C["muted"], False)], panel=True)
    cards = [
        ("median", "Median svartid dager", "Median", C["teal"], "50 % er raskere"),
        ("p75", "P75 svartid dager", "P75", C["green"], "75 % er raskere"),
        ("p90", "P90 svartid dager", "P90", C["amber"], "90 % er raskere"),
        ("sla", "Andel innen individuell frist", "Innen frist", C["blue"], "Gyldig n i tooltip"),
        ("valid", "Antall gyldige svartider", "Gyldige n", C["blue"], "Ekskluderer ugyldige intervaller"),
    ]
    for idx, (vid, metric, label, accent, note) in enumerate(cards):
        page.card(f"kpi-{vid}", 208 + idx * 210, 180, 198, 108, "resultater", metric, label, accent, note)
    tips = [measure("resultater", "Antall gyldige svartider"), measure("resultater", "Andel innen individuell frist"), measure("resultater", "Antall over individuell frist"), measure("resultater", "Antall ekskludert datakvalitet"), measure("resultater", "Entydig svarfrist dager")]
    page.chart("analysis-turnaround", "lineClusteredColumnComboChart", 208, 310, 650, 286, "Svartid per analyse", "Stolpe = median • linje = P90 • frist vises bare når entydig", {"Category": [column("resultater", "Analyse")], "Y": [measure("resultater", "Median svartid dager")], "Y2": [measure("resultater", "P90 svartid dager"), measure("resultater", "Entydig svarfrist dager")], "Tooltips": tips})
    page.chart("turnaround-trend", "lineChart", 874, 310, 382, 286, "Utvikling over tid", "Median og P90 per måned", {"Category": [column("Dato", "ÅrMåned")], "Y": [measure("resultater", "Median svartid dager"), measure("resultater", "P90 svartid dager")], "Tooltips": tips})
    page.textbox("turnaround-note", 208, 614, 1048, 70, [("Lesing av status", 11, C["blue"], True), ("På mål / Følg med / Krever oppfølging vises med både tekst og farge. Gjennomsnitt finnes kun som sekundær informasjon i tooltip.", 9, C["text"], False)], panel=True)


def build_followup(page: Page) -> None:
    page.slicer("filter-group", 208, 96, 260, 64, "resultater", "Rapportgruppe", "Rapportgruppe")
    page.slicer("filter-quality", 484, 96, 260, 64, "resultater", "Datakvalitet status", "Datakvalitet")
    page.textbox("writeback-note", 760, 96, 496, 64, [("Oppfølging uten falsk writeback", 11, C["blue"], True), ("Kommentarer krever stabil saksnøkkel og godkjent lagringskilde.", 9, C["muted"], False)], panel=True)
    cards = [
        ("valid", "Antall gyldige svartider", "Gyldige", C["green"]),
        ("excluded", "Antall ekskludert datakvalitet", "Ekskludert", C["red"]),
        ("within", "Antall innen individuell frist", "Innen frist", C["teal"]),
        ("over", "Antall over individuell frist", "Over frist", C["amber"]),
    ]
    for idx, (vid, metric, label, accent) in enumerate(cards):
        page.card(f"kpi-{vid}", 208 + idx * 262, 180, 246, 100, "resultater", metric, label, accent, "Valgt perspektiv")
    fields = [
        column("resultater", "Rapportgruppe"), column("resultater", "Analyse"), column("resultater", "Tidspunkt.prøvetaking"),
        column("resultater", "Tidspunkt.analysebestilling"), column("resultater", "Ekstraksjon.ferdig"), column("resultater", "Enhet starttid"),
        column("resultater", "Enhet startkilde"), column("resultater", "Tidspunkt.analyseresultat"), column("resultater", "Tidspunkt.godkjenning"),
        column("resultater", "Svartid pasient dager"), column("resultater", "Svartid seksjon dager"), column("resultater", "Svartid enhet dager"),
        column("resultater", "Svarfrist"), column("resultater", "Datakvalitet status"),
    ]
    page.table("followup-table", 208, 300, 1048, 384, "Detaljer • sorter og filtrer før faglig oppfølging", fields)


def build_quality(page: Page) -> None:
    cards = [
        ("all", "Antall resultater", "Resultater", C["blue"]),
        ("ok", "Datakvalitet OK", "Datakvalitet OK", C["green"]),
        ("issues", "Datakvalitet avvik", "Datakvalitet avvik", C["red"]),
        ("excluded", "Andel ekskludert datakvalitet", "Andel ekskludert", C["amber"]),
    ]
    for idx, (vid, metric, label, accent) in enumerate(cards):
        page.card(f"kpi-{vid}", 208 + idx * 262, 100, 246, 116, "resultater", metric, label, accent, "Valgt periode og filter")
    page.chart("quality-status", "clusteredBarChart", 208, 240, 506, 238, "Avvik etter type", "Negative, manglende og ekstreme verdier vises – aldri som null", {"Category": [column("resultater", "Datakvalitet status")], "Y": [measure("resultater", "Antall resultater")], "Tooltips": [measure("resultater", "Andel ekskludert datakvalitet")]})
    page.chart("quality-source", "clusteredBarChart", 730, 240, 526, 238, "Valgt enhetsstart", "Viser om bestilling eller ekstraksjon var seneste operative start", {"Category": [column("resultater", "Enhet startkilde")], "Y": [measure("resultater", "Antall resultater")], "Tooltips": [measure("resultater", "Median enhetstid dager")]})
    page.textbox("quality-rules", 208, 500, 1048, 184, [("Datakvalitetsregler", 13, C["blue"], True), ("• Manglende start eller analyseresultat ekskluderes fra relevante svartidsmål.", 10, C["text"], False), ("• Negative intervaller og intervaller over 365 dager returnerer BLANK – aldri 0.", 10, C["text"], False), ("• Godkjenning før analyseresultat flagges separat.", 10, C["text"], False), ("• Alle prosentmål bruker kun gyldige observasjoner og viser antall i tooltip.", 10, C["text"], False)], panel=True)


def build_theme() -> None:
    RESOURCES.mkdir(parents=True, exist_ok=True)
    theme = {
        "name": "Hemato OUS",
        "dataColors": [C["blue"], C["teal"], "#3E7EA6", "#6BA5C8", C["amber"], C["green"], C["red"]],
        "good": C["green"], "neutral": C["amber"], "bad": C["red"],
        "background": C["canvas"], "foreground": C["text"], "tableAccent": C["blue"],
        "textClasses": {
            "callout": {"fontSize": 24, "fontFace": "Segoe UI Semibold", "color": C["text"]},
            "title": {"fontSize": 13, "fontFace": "Segoe UI Semibold", "color": C["text"]},
            "header": {"fontSize": 11, "fontFace": "Segoe UI Semibold", "color": C["blue"]},
            "label": {"fontSize": 10, "fontFace": "Segoe UI", "color": C["muted"]},
        },
    }
    dump(RESOURCES / "hemato-ous-theme.json", theme)

    report_path = DEFINITION / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report.setdefault("themeCollection", {})["customTheme"] = {"name": "Hemato OUS", "reportVersionAtImport": "5.55", "type": "RegisteredResources"}
    packages = report.setdefault("resourcePackages", [])
    registered = next((p for p in packages if p.get("name") == "RegisteredResources"), None)
    if registered is None:
        registered = {"name": "RegisteredResources", "type": "RegisteredResources", "items": []}
        packages.append(registered)
    registered["items"] = [item for item in registered.get("items", []) if item.get("name") != "hemato-ous-theme.json"]
    registered["items"].append({"name": "hemato-ous-theme.json", "type": 202, "path": "hemato-ous-theme.json"})
    dump(report_path, report)


def main() -> None:
    if PAGES.exists():
        shutil.rmtree(PAGES)
    PAGES.mkdir(parents=True)
    pages = [
        Page(PAGE_DEFS[0][0], PAGE_DEFS[0][1], "Ledelsesbilde med volum, svartid og synlige kvalitetsvarsler", "Resultater: analyseresultat • Volum: analysebestilling"),
        Page(PAGE_DEFS[1][0], PAGE_DEFS[1][1], "Ukevis kapasitet, sesongmønster og analysefordeling", "Analysebestilling"),
        Page(PAGE_DEFS[2][0], PAGE_DEFS[2][1], "Median, P75, P90 og individuell fristoppnåelse", "Analyseresultat"),
        Page(PAGE_DEFS[3][0], PAGE_DEFS[3][1], "Tidsstempler, startkilde, frist og datakvalitet på detaljnivå", "Analyseresultat"),
        Page(PAGE_DEFS[4][0], PAGE_DEFS[4][1], "Diagnostikk som gjør ekskluderinger synlige og etterprøvbare", "Analyseresultat"),
    ]
    build_leadership(pages[0])
    build_volume(pages[1])
    build_turnaround(pages[2])
    build_followup(pages[3])
    build_quality(pages[4])
    dump(
        PAGES / "pages.json",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
            "pageOrder": [page_id for page_id, _ in PAGE_DEFS],
            "activePageName": PAGE_DEFS[0][0],
        },
    )
    build_theme()
    print(f"Bygget fem rapportider i {REPORT}")


if __name__ == "__main__":
    main()
