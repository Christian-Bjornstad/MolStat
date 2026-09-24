"""V5 presentation layer; reuse V4's report contents and semantic measures."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import build_hemato_statistikk_v4_report as base


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "powerbi" / "Hemato_Statistikk_V5"
REPORT = PROJECT / "Hemato Statistikk Rapport.Report"


class PolishedPage(base.Page):
    def slicer(self, visual_id, x, y, w, h, entity, field, title):
        super().slicer(visual_id, x, y, w, h, entity, field, title)
        path = self.visuals / visual_id / "visual.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        objects = doc["visual"]["objects"]
        objects["header"] = [{"properties": {"show": base.lit("false")}}]
        objects["items"][0]["properties"]["textSize"] = base.lit("11D")
        selection = objects["selection"][0]["properties"]
        if visual_id == "perspective":
            selection.update(singleSelect=base.lit("true"), strictSingleSelect=base.lit("true"))
            objects["general"] = [{"properties": {"filter": {"filter": {
                "Version": 2,
                "From": [{"Name": "s", "Entity": entity, "Type": 0}],
                "Where": [{"Condition": {"In": {
                    "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": field}}],
                    "Values": [[{"Literal": {"Value": "'Enhetstid'"}}]],
                }}}],
            }}}}]
        else:
            selection["selectAllCheckboxEnabled"] = base.lit("true")
        container = doc["visual"]["visualContainerObjects"]
        container["title"][0]["properties"].update(fontSize=base.lit("10D"), titleWrap=base.lit("false"))
        container["padding"][0]["properties"] = {key: base.lit("8D") for key in ("top", "bottom", "left", "right")}
        base.dump(path, doc)

    def card(self, visual_id, x, y, w, h, entity, metric, label, accent, subtitle=""):
        # Classic card has a stable formatting contract and no nested card
        # layout: a single title, one large value, no intersecting accent bar.
        is_percent = "Andel" in metric or "prosent" in metric
        is_days = "dager" in metric
        if is_days:
            label = "Median svartid · dager" if "Median" in metric else label + " · dager"
        elif metric == "Andel innen individuell frist":
            label = "Innen frist · %"
        elif metric == "Antall over individuell frist":
            label = "Over frist · antall"
        container = base.container(label)
        container["title"][0]["properties"].update(fontSize=base.lit("11D"), fontColor=base.solid(base.C["muted"]))
        container["padding"][0]["properties"] = {key: base.lit("12D") for key in ("top", "bottom", "left", "right")}
        self.write_visual(visual_id, {
            "visualType": "card",
            "query": {"queryState": {"Values": {"projections": [base.measure(entity, metric)]}}},
            "objects": {
                "labels": [{"properties": {
                    "color": base.solid(accent), "fontFamily": base.lit("'Segoe UI Semibold'"),
                    "fontSize": base.lit("29D"), "labelDisplayUnits": base.lit("1D"),
                    "labelPrecision": base.lit("1L" if is_percent or is_days else "0L"),
                }}],
                "categoryLabels": [{"properties": {"show": base.lit("false")}}],
                "wordWrap": [{"properties": {"show": base.lit("false")}}],
            },
            "visualContainerObjects": container,
            "drillFilterOtherVisuals": True,
        }, x, y - 8 if y == 176 else y, w, h + 8)


def filter_row(page, specs, y=82, height=70):
    specs = [spec for spec in specs if spec[0] != "filter-analysis"]
    if page.page_id == "1f0a1111111111111111":
        specs.insert(-1, ("filter-group", "resultater", "Rapportgruppe", "Rapportgruppe"))
    # Wider selectors for longer values; calendar filters remain compact.
    weights = {"filter-year": 0.75, "filter-month": 1.0, "filter-week": 0.9,
               "filter-material": 0.9, "filter-group": 1.45, "perspective": 1.4}
    usable = 1048 - 8 * (len(specs) - 1)
    total = sum(weights.get(s[0], 1) for s in specs)
    x = 204
    for index, (vid, entity, field, title) in enumerate(specs):
        width = 1252 - x if index == len(specs) - 1 else round(usable * weights.get(vid, 1) / total)
        page.slicer(vid, x, y, width, height, entity, field, title)
        x += width + 8


def polish_charts():
    for path in (REPORT / "definition" / "pages").glob("*/visuals/*/visual.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        visual = doc["visual"]
        kind = visual.get("visualType", "")
        if "Chart" not in kind:
            continue
        objects = visual.setdefault("objects", {})
        for entry in objects.get("labels", []):
            entry["properties"]["labelDisplayUnits"] = base.lit("1D")
        axes = objects.setdefault("valueAxis", [{"properties": {}}])
        axes[0]["properties"].update(labelDisplayUnits=base.lit("1D"), secLabelDisplayUnits=base.lit("1D"))
        # Set the native chart palette explicitly; retain conditional colors.
        objects.setdefault("dataPoint", [{"properties": {"defaultColor": base.solid(base.C["blue"])}}])
        if "line" in kind.lower():
            objects.setdefault("lineStyles", [{"properties": {"strokeWidth": base.lit("2D")}}])
        base.dump(path, doc)


def main():
    if not PROJECT.exists():
        shutil.copytree(ROOT / "powerbi" / "Hemato_Statistikk_V4", PROJECT)
        (PROJECT / "Hemato_Statistikk_V4.pbip").rename(PROJECT / "Hemato_Statistikk_V5.pbip")
    base.PROJECT = PROJECT
    base.REPORT = REPORT
    base.DEFINITION = REPORT / "definition"
    base.PAGES = base.DEFINITION / "pages"
    base.RESOURCES = REPORT / "StaticResources" / "RegisteredResources"
    base.Page = PolishedPage
    base.add_filter_row = filter_row
    # Base generator removes only this checked V5 generated pages directory.
    assert base.PAGES.resolve().is_relative_to(PROJECT.resolve())
    base.main()
    polish_charts()
    print(f"V5: {PROJECT}")


if __name__ == "__main__":
    main()
