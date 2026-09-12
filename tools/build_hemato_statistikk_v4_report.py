from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "powerbi" / "Hemato_Statistikk_V4"
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
    ("1f0a1111111111111111", "Oversikt"),
    ("2f0a2222222222222222", "Antall per uke"),
    ("9f0a9999999999999999", "Antall per rapportgruppe"),
    ("4f0a4444444444444444", "Antall per analyse"),
    ("3f0a3333333333333333", "Svartid over tid"),
    ("5f0a5555555555555555", "Svartid per analyse"),
    ("6f0a6666666666666666", "Oppfølging"),
    ("8f0a8888888888888888", "Om rapporten"),
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
    # Desktop writes PBIR stacking/tab order in 1000-point steps. Keeping that
    # convention avoids the navigation hit area falling through to nav-bg.
    layer = z * 1000
    return {"x": x, "y": y, "z": layer, "height": h, "width": w, "tabOrder": layer}


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
                    "background": [{"properties": {"color": solid(C["nav"]), "transparency": lit("0D")}}],
                    "outspace": [{"properties": {"color": solid(C["canvas"]), "transparency": lit("0D")}}],
                },
            },
        )
        self.shape("main-bg", 184, 0, 1096, 720, C["canvas"])
        self.textbox("brand", 18, 16, 150, 62, [("OUS", 23, "#FFFFFF", True), ("Hematologi", 10, "#CFE3F2", False)])
        self.navigator("navigation", 14, 104, 156, 350)
        self.textbox("page-title", 204, 12, 700, 40, [(display_name, 23, C["text"], True)])
        self.textbox("page-subtitle", 204, 48, 720, 26, [(subtitle, 9, C["muted"], False)])
        self.textbox("event-date", 1010, 18, 242, 42, [(event_date, 9, C["muted"], False)])

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
        padding = "8D" if panel else "0D"
        side_padding = "10D" if panel else "0D"
        self.write_visual(
            visual_id,
            {
                "visualType": "textbox",
                "objects": objects,
                "visualContainerObjects": {
                    "title": [{"properties": {"show": lit("false")}}],
                    "background": [{"properties": {"show": lit("true" if panel else "false"), "color": solid(C["panel"]), "transparency": lit("0D")}}],
                    "border": [{"properties": {"show": lit("true" if panel else "false"), "color": solid(C["border"]), "width": lit("1D"), "radius": lit("10D")}}],
                    "padding": [{"properties": {"top": lit(padding), "bottom": lit(padding), "left": lit(side_padding), "right": lit(side_padding)}}],
                },
                "drillFilterOtherVisuals": True,
            },
            x, y, w, h,
        )

    def navigator(self, visual_id: str, x: int, y: int, w: int, h: int) -> None:
        for index, (target_page_id, _) in enumerate(PAGE_DEFS):
            page_visibility = [{"properties": {"showByDefault": lit("false")}}]
            page_visibility.extend(
                {
                    "properties": {"showPage": lit("true" if page_id == target_page_id else "false")},
                    "selector": {"id": page_id},
                }
                for page_id, _ in PAGE_DEFS
            )
            self.write_visual(
                f"{visual_id}-{index + 1}",
                {
                    "visualType": "pageNavigator",
                    "objects": {
                        "pages": page_visibility,
                        "shape": [{"properties": {"tileShape": lit("'rectangleRounded'")}, "selector": {"id": "default"}}],
                        "fill": [
                            {"properties": {"show": lit("true"), "fillColor": solid(C["nav"]), "transparency": lit("0D")}, "selector": {"id": "default"}},
                            {"properties": {"show": lit("true"), "fillColor": solid(C["nav_selected"]), "transparency": lit("0D")}, "selector": {"id": "selected"}},
                        ],
                        "outline": [{"properties": {"show": lit("false")}}],
                        "text": [
                            {"properties": {"fontFamily": lit("'Segoe UI'"), "fontSize": lit("10D"), "fontColor": solid("#FFFFFF")}, "selector": {"id": "default"}},
                            {"properties": {"fontFamily": lit("'Segoe UI Semibold'"), "fontSize": lit("10D"), "fontColor": solid("#FFFFFF")}, "selector": {"id": "selected"}},
                        ],
                    },
                    "drillFilterOtherVisuals": True,
                },
                x, y + index * 50, w, 44,
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
                    "accentBar": [{"properties": {"show": lit("true"), "position": lit("'Top'"), "width": lit("3D"), "color": solid(accent)}, "selector": {"id": "default"}}],
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

    def chart(
        self,
        visual_id: str,
        visual_type: str,
        x: int,
        y: int,
        w: int,
        h: int,
        title: str,
        subtitle: str,
        roles: dict[str, list[dict[str, Any]]],
        scalar_axis: bool = False,
        show_legend: bool = True,
        show_labels: bool = False,
        sort_field: dict[str, Any] | None = None,
    ) -> None:
        query_state = {role: {"projections": projections} for role, projections in roles.items()}
        category_properties = {"show": lit("true"), "showAxisTitle": lit("false"), "concatenateLabels": lit("false")}
        if scalar_axis:
            category_properties["axisType"] = lit("'Scalar'")
        query: dict[str, Any] = {"queryState": query_state}
        if sort_field is not None:
            query["sortDefinition"] = {"sort": [{"field": sort_field["field"], "direction": "Descending"}]}
        self.write_visual(
            visual_id,
            {
                "visualType": visual_type,
                "query": query,
                "objects": {
                    "legend": [{"properties": {"show": lit("true" if show_legend else "false"), "position": lit("'Top'")}}],
                    "labels": [{"properties": {"show": lit("true" if show_labels else "false"), "labelPosition": lit("'Auto'")}}],
                    "categoryAxis": [{"properties": category_properties}],
                    "valueAxis": [{"properties": {"show": lit("true"), "showAxisTitle": lit("false"), "gridlineStyle": lit("'dotted'")}}],
                },
                "visualContainerObjects": container(title, subtitle),
                "drillFilterOtherVisuals": True,
            },
            x, y, w, h,
        )

    def turnaround_combo(self, visual_id: str, x: int, y: int, w: int, h: int) -> None:
        median = measure("resultater", "Median svartid dager")
        deadline = measure("resultater", "Entydig svarfrist dager")
        self.write_visual(
            visual_id,
            {
                "visualType": "lineClusteredColumnComboChart",
                "query": {
                    "queryState": {
                        "Category": {"projections": [column("resultater", "Analyse")]},
                        "Y": {"projections": [median]},
                        "Y2": {"projections": [deadline]},
                        "Tooltips": {
                            "projections": [
                                measure("resultater", "Andel innen individuell frist"),
                                measure("resultater", "Antall innen individuell frist"),
                                measure("resultater", "Antall over individuell frist"),
                                measure("resultater", "Antall gyldige svartider"),
                                measure("resultater", "Gjennomsnitt svartid dager"),
                            ]
                        },
                    },
                    "sortDefinition": {"sort": [{"field": median["field"], "direction": "Descending"}]},
                },
                "objects": {
                    "dataPoint": [
                        {
                            "properties": {
                                "fill": {
                                    "solid": {
                                        "color": {
                                            "expr": {
                                                "Measure": {
                                                    "Expression": {"SourceRef": {"Entity": "resultater"}},
                                                    "Property": "Svartid status farge",
                                                }
                                            }
                                        }
                                    }
                                }
                            },
                            "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]},
                        }
                    ],
                    "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}],
                    "categoryAxis": [{"properties": {"show": lit("true"), "showAxisTitle": lit("false"), "concatenateLabels": lit("false")}}],
                    "valueAxis": [{"properties": {"show": lit("true"), "showAxisTitle": lit("false"), "secShow": lit("false"), "gridlineStyle": lit("'dotted'")}}],
                    "lineStyles": [{"properties": {"lineStyle": lit("'dashed'"), "strokeWidth": lit("2D")}}],
                    "labels": [
                        {"properties": {"show": lit("true"), "labelPosition": lit("'Auto'")}},
                        {"properties": {"showSeries": lit("false")}, "selector": {"metadata": "resultater.Entydig svarfrist dager"}},
                    ],
                },
                "visualContainerObjects": container(
                    "Median svartid og frist per analyse",
                    "Stolpe = median · stiplet linje = entydig frist",
                ),
                "drillFilterOtherVisuals": True,
            },
            x,
            y,
            w,
            h,
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


def add_filter_row(page: Page, specs: list[tuple[str, str, str, str]], y: int = 82, height: int = 78) -> None:
    gap = 8
    total_width = 1048
    width = (total_width - gap * (len(specs) - 1)) // len(specs)
    for index, (visual_id, entity, field, title) in enumerate(specs):
        page.slicer(visual_id, 204 + index * (width + gap), y, width, height, entity, field, title)


def date_filters() -> list[tuple[str, str, str, str]]:
    return [
        ("filter-year", "Dato", "År", "År"),
        ("filter-month", "Dato", "Måned", "Måned"),
        ("filter-week", "Dato", "ÅrUke", "Uke"),
    ]


def result_filters(*extra: tuple[str, str, str, str]) -> list[tuple[str, str, str, str]]:
    return date_filters() + [("filter-material", "resultater", "Materiale", "Materiale"), *extra]


def build_leadership(page: Page) -> None:
    add_filter_row(page, result_filters(("perspective", "Svartidsperspektiv", "Perspektiv", "Perspektiv")))
    cards = [
        ("total", "Antall resultater", "Resultater", C["blue"]),
        ("median", "Median svartid dager", "Median svartid", C["teal"]),
        ("sla", "Andel innen individuell frist", "Innen frist", C["amber"]),
        ("over", "Antall over individuell frist", "Over frist", C["red"]),
    ]
    for idx, (vid, metric, label, accent) in enumerate(cards):
        page.card(f"kpi-{vid}", 204 + idx * 266, 176, 254, 96, "resultater", metric, label, accent)
    tips = [measure("resultater", "Antall gyldige svartider"), measure("resultater", "Andel innen individuell frist"), measure("resultater", "Antall over individuell frist")]
    page.chart("weekly-results", "lineChart", 204, 288, 618, 396, "Resultater per uke", "", {"Category": [column("Dato", "UkeStart")], "Y": [measure("resultater", "Antall resultater")], "Tooltips": tips}, scalar_axis=True, show_legend=False)
    page.chart("group-turnaround", "clusteredBarChart", 838, 288, 414, 396, "Median per rapportgruppe", "Valgt perspektiv", {"Category": [column("resultater", "Rapportgruppe")], "Y": [measure("resultater", "Median svartid dager")], "Tooltips": tips}, show_legend=False, show_labels=True, sort_field=measure("resultater", "Median svartid dager"))


def build_volume(page: Page) -> None:
    add_filter_row(page, date_filters() + [("filter-group", "antall", "Rapportgruppe", "Rapportgruppe")])
    cards = [
        ("volume", "antall", "Antall analyser", "Analyser", C["blue"]),
        ("previous", "antall", "Antall analyser forrige periode", "Forrige måned", C["teal"]),
        ("change", "antall", "Endring analyser prosent", "Endring", C["amber"]),
        ("rolling", "antall", "Fireukers glidende analyser", "4-ukers nivå", C["green"]),
    ]
    for idx, (vid, entity, metric, label, accent) in enumerate(cards):
        page.card(f"kpi-{vid}", 204 + idx * 266, 176, 254, 96, entity, metric, label, accent)
    tips = [measure("resultater", "Lavvolumgrense P10"), measure("antall", "Endring analyser prosent")]
    page.chart("volume-week", "lineChart", 204, 288, 682, 396, "Ukevolum", "Volum, 4-ukers nivå og historisk P10", {"Category": [column("Dato", "UkeStart")], "Y": [measure("antall", "Antall analyser"), measure("antall", "Fireukers glidende analyser"), measure("resultater", "Lavvolumgrense P10")], "Tooltips": tips}, scalar_axis=True)
    page.chart("volume-month", "lineChart", 902, 288, 350, 396, "Månedsvolum", "", {"Category": [column("Dato", "MånedStart")], "Y": [measure("antall", "Antall analyser")], "Tooltips": tips}, scalar_axis=True, show_legend=False)


def build_volume_group(page: Page) -> None:
    add_filter_row(page, date_filters() + [("filter-group", "antall", "Rapportgruppe", "Rapportgruppe")])
    page.card("kpi-volume", 204, 176, 254, 96, "antall", "Antall analyser", "Analyser", C["blue"])
    page.card("kpi-rolling", 470, 176, 254, 96, "antall", "Fireukers glidende analyser", "4-ukers nivå", C["teal"])
    page.chart("volume-group", "clusteredBarChart", 204, 288, 682, 396, "Antall per rapportgruppe", "", {"Category": [column("antall", "Rapportgruppe")], "Y": [measure("antall", "Antall analyser")]}, show_legend=False, show_labels=True, sort_field=measure("antall", "Antall analyser"))
    page.chart("group-month", "lineChart", 902, 288, 350, 396, "Utvikling per måned", "Valgt rapportgruppe", {"Category": [column("Dato", "MånedStart")], "Y": [measure("antall", "Antall analyser")]}, scalar_axis=True, show_legend=False)


def build_volume_analysis(page: Page) -> None:
    add_filter_row(page, date_filters() + [("filter-group", "antall", "Rapportgruppe", "Rapportgruppe"), ("filter-analysis", "antall", "Analyse", "Analyse")])
    page.chart("analysis-volume", "clusteredBarChart", 204, 176, 1048, 508, "Antall per analyse", "Velg rapportgruppe for en kortere og mer relevant liste", {"Category": [column("antall", "Analyse")], "Y": [measure("antall", "Antall analyser")], "Tooltips": [column("antall", "Rapportgruppe")]}, show_legend=False, show_labels=True, sort_field=measure("antall", "Antall analyser"))


def build_turnaround(page: Page) -> None:
    add_filter_row(page, result_filters(("filter-group", "resultater", "Rapportgruppe", "Rapportgruppe"), ("perspective", "Svartidsperspektiv", "Perspektiv", "Perspektiv")))
    cards = [
        ("median", "Median svartid dager", "Median", C["teal"]),
        ("sla", "Andel innen individuell frist", "Innen frist", C["blue"]),
        ("over", "Antall over individuell frist", "Over frist", C["red"]),
        ("valid", "Antall gyldige svartider", "Gyldige", C["green"]),
    ]
    for idx, (vid, metric, label, accent) in enumerate(cards):
        page.card(f"kpi-{vid}", 204 + idx * 266, 176, 254, 96, "resultater", metric, label, accent)
    tips = [measure("resultater", "Antall gyldige svartider"), measure("resultater", "Antall over individuell frist"), measure("resultater", "Antall ekskludert datakvalitet"), measure("resultater", "Entydig svarfrist dager")]
    page.chart("turnaround-month", "lineChart", 204, 288, 618, 396, "Median svartid per måned", "Valgt perspektiv", {"Category": [column("Dato", "MånedStart")], "Y": [measure("resultater", "Median svartid dager")], "Tooltips": tips}, scalar_axis=True, show_legend=False)
    page.chart("turnaround-group", "clusteredBarChart", 838, 288, 414, 396, "Median per rapportgruppe", "Valgt perspektiv", {"Category": [column("resultater", "Rapportgruppe")], "Y": [measure("resultater", "Median svartid dager")], "Tooltips": tips}, show_legend=False, show_labels=True, sort_field=measure("resultater", "Median svartid dager"))


def build_turnaround_analysis(page: Page) -> None:
    add_filter_row(page, result_filters(("filter-group", "resultater", "Rapportgruppe", "Rapportgruppe"), ("filter-analysis", "resultater", "Analyse", "Analyse"), ("perspective", "Svartidsperspektiv", "Perspektiv", "Perspektiv")))
    page.card("kpi-median", 204, 176, 254, 96, "resultater", "Median svartid dager", "Median", C["teal"])
    page.card("kpi-sla", 470, 176, 254, 96, "resultater", "Andel innen individuell frist", "Innen frist", C["blue"])
    page.card("kpi-within", 736, 176, 254, 96, "resultater", "Antall innen individuell frist", "Innen frist (antall)", C["green"])
    page.card("kpi-over", 1002, 176, 250, 96, "resultater", "Antall over individuell frist", "Over frist", C["red"])
    page.turnaround_combo("analysis-turnaround", 204, 288, 1048, 396)


def build_followup(page: Page) -> None:
    add_filter_row(page, result_filters(("filter-group", "resultater", "Rapportgruppe", "Rapportgruppe"), ("perspective", "Svartidsperspektiv", "Perspektiv", "Perspektiv")))
    cards = [
        ("median", "Median svartid dager", "Median", C["teal"]),
        ("within", "Antall innen individuell frist", "Innen frist", C["teal"]),
        ("over", "Antall over individuell frist", "Over frist", C["amber"]),
        ("valid", "Antall gyldige svartider", "Gyldige", C["green"]),
    ]
    for idx, (vid, metric, label, accent) in enumerate(cards):
        page.card(f"kpi-{vid}", 204 + idx * 266, 176, 254, 96, "resultater", metric, label, accent)
    fields = [
        column("resultater", "Analyse"), column("resultater", "Materiale"),
        column("resultater", "Svartid pasient dager"), column("resultater", "Svartid seksjon dager"),
        column("resultater", "Svartid enhet dager"), column("resultater", "Svarfrist"),
        column("resultater", "Tidspunkt.analyseresultat"),
    ]
    page.table("followup-table", 204, 288, 1048, 396, "Oppfølging", fields)


def build_about(page: Page) -> None:
    page.textbox(
        "definitions",
        204,
        92,
        650,
        220,
        [
            ("Svartidsperspektiver", 15, C["text"], True),
            ("Pasientforløp: prøvetaking til analyseresultat", 11, C["text"], False),
            ("Seksjonstid: analysebestilling til analyseresultat", 11, C["text"], False),
            ("Enhetstid: seneste av analysebestilling og ekstraksjon til analyseresultat", 11, C["text"], False),
            ("Median og individuell svarfrist brukes i hovedrapporten.", 11, C["muted"], False),
        ],
        panel=True,
    )
    page.card("kpi-issues", 870, 92, 382, 104, "resultater", "Datakvalitet avvik", "Tekniske tidsavvik", C["amber"])
    page.textbox(
        "quality-note",
        870,
        208,
        382,
        104,
        [("Negative eller manglende intervaller holdes utenfor svartidsberegningen. Dette kan være forventet når bestilling registreres etter at arbeidet er utført.", 10, C["muted"], False)],
        panel=True,
    )
    page.chart("start-source", "clusteredBarChart", 204, 328, 1048, 356, "Startkilde for enhetstid", "Analysebestilling eller ekstraksjon – den seneste gyldige hendelsen brukes", {"Category": [column("resultater", "Enhet startkilde")], "Y": [measure("resultater", "Antall resultater")]}, show_legend=False, show_labels=True)


def build_theme() -> None:
    # Visual colors are defined directly. A customTheme reference validated as
    # PBIR but failed at Power BI Desktop runtime in V3, so V4 deliberately
    # keeps only the built-in base theme.
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
    report.setdefault("themeCollection", {}).pop("customTheme", None)
    packages = report.setdefault("resourcePackages", [])
    registered = next((p for p in packages if p.get("name") == "RegisteredResources"), None)
    if registered is None:
        registered = {"name": "RegisteredResources", "type": "RegisteredResources", "items": []}
        packages.append(registered)
    registered["items"] = [
        item
        for item in registered.get("items", [])
        if item.get("name") != "hemato-ous-theme.json" and item.get("type") != 202
    ]
    dump(report_path, report)


def main() -> None:
    if PAGES.exists():
        shutil.rmtree(PAGES)
    PAGES.mkdir(parents=True)
    pages = [
        Page(PAGE_DEFS[0][0], PAGE_DEFS[0][1], "Antall og svartid i ett bilde", "Analyseresultatdato"),
        Page(PAGE_DEFS[1][0], PAGE_DEFS[1][1], "Ukevolum, måned og 4-ukers nivå", "Analysebestillingsdato"),
        Page(PAGE_DEFS[2][0], PAGE_DEFS[2][1], "Fordeling og utvikling", "Analysebestillingsdato"),
        Page(PAGE_DEFS[3][0], PAGE_DEFS[3][1], "Alle analyser i én oversikt", "Analysebestillingsdato"),
        Page(PAGE_DEFS[4][0], PAGE_DEFS[4][1], "Median og fristoppnåelse", "Analyseresultatdato"),
        Page(PAGE_DEFS[5][0], PAGE_DEFS[5][1], "Originalens oversikt – nå med perspektiv", "Analyseresultatdato"),
        Page(PAGE_DEFS[6][0], PAGE_DEFS[6][1], "Detaljer og sammenligning av tre svartider", "Analyseresultatdato"),
        Page(PAGE_DEFS[7][0], PAGE_DEFS[7][1], "Definisjoner og teknisk kontroll", "Analyseresultatdato"),
    ]
    build_leadership(pages[0])
    build_volume(pages[1])
    build_volume_group(pages[2])
    build_volume_analysis(pages[3])
    build_turnaround(pages[4])
    build_turnaround_analysis(pages[5])
    build_followup(pages[6])
    build_about(pages[7])
    dump(
        PAGES / "pages.json",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
            "pageOrder": [page_id for page_id, _ in PAGE_DEFS],
            "activePageName": PAGE_DEFS[0][0],
        },
    )
    build_theme()
    print(f"Bygget komplett V4-rapport med åtte sider i {REPORT}")


if __name__ == "__main__":
    main()
