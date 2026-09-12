from __future__ import annotations

import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "powerbi" / "Hemato_Statistikk_V4"
REPORT = PROJECT / "Hemato Statistikk Rapport.Report"
PBIX = ROOT / "powerbi" / "Hemato_Statistikk_V4.pbix"

PAGE_NAMES = [
    "Oversikt",
    "Antall per uke",
    "Antall per rapportgruppe",
    "Antall per analyse",
    "Svartid over tid",
    "Svartid per analyse",
    "Oppfølging",
    "Om rapporten",
]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def visual(page_id: str, visual_id: str) -> dict:
    return read_json(
        REPORT / "definition" / "pages" / page_id / "visuals" / visual_id / "visual.json"
    )


def all_page_visual_text(page_ids: list[str]) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for page_id in page_ids
        for path in (REPORT / "definition" / "pages" / page_id / "visuals").glob("*/visual.json")
    )


def test_v4_has_complete_eight_page_structure() -> None:
    assert (PROJECT / "Hemato_Statistikk_V4.pbip").is_file()
    pages_root = REPORT / "definition" / "pages"
    order = read_json(pages_root / "pages.json")["pageOrder"]
    assert len(order) == 8
    assert [read_json(pages_root / page_id / "page.json")["displayName"] for page_id in order] == PAGE_NAMES


def test_overview_prioritizes_volume_and_selected_turnaround_perspective() -> None:
    page_id = "1f0a1111111111111111"
    raw = all_page_visual_text([page_id])
    assert (REPORT / "definition" / "pages" / page_id / "visuals" / "perspective" / "visual.json").is_file()
    assert "Svartidsperspektiv" in raw
    assert "Antall resultater" in raw
    assert "Median svartid dager" in raw
    assert "Andel innen individuell frist" in raw
    assert "P90" not in raw
    assert "Datakvalitetsavvik" not in raw


def test_original_style_analysis_volume_chart_is_large_and_direct() -> None:
    chart = visual("4f0a4444444444444444", "analysis-volume")
    assert chart["visual"]["visualType"] == "clusteredBarChart"
    assert chart["position"]["width"] >= 800
    assert chart["position"]["height"] >= 480
    raw = json.dumps(chart, ensure_ascii=False)
    assert '"Entity": "antall"' in raw
    assert '"Property": "Analyse"' in raw
    assert '"Property": "Antall analyser"' in raw


def test_original_style_turnaround_chart_uses_selected_perspective_and_median() -> None:
    page_id = "5f0a5555555555555555"
    chart = visual(page_id, "analysis-turnaround")
    assert chart["visual"]["visualType"] == "lineClusteredColumnComboChart"
    query = chart["visual"]["query"]["queryState"]
    assert {"Category", "Y", "Y2", "Tooltips"}.issubset(query)
    raw = json.dumps(chart, ensure_ascii=False)
    assert '"Property": "Analyse"' in raw
    assert '"Property": "Median svartid dager"' in raw
    assert '"Property": "Entydig svarfrist dager"' in raw
    assert '"Property": "Andel innen individuell frist"' in raw
    assert (REPORT / "definition" / "pages" / page_id / "visuals" / "perspective" / "visual.json").is_file()
    assert "P90" not in all_page_visual_text(["3f0a3333333333333333", page_id])


def test_result_pages_keep_material_filter_including_pak_capability() -> None:
    for page_id in (
        "1f0a1111111111111111",
        "3f0a3333333333333333",
        "5f0a5555555555555555",
        "6f0a6666666666666666",
    ):
        raw = visual(page_id, "filter-material")
        assert raw["visual"]["visualType"] == "slicer"
        assert '"Property": "Materiale"' in json.dumps(raw, ensure_ascii=False)


def test_quality_is_supporting_content_not_a_primary_dashboard() -> None:
    raw = all_page_visual_text(["8f0a8888888888888888"])
    assert "Om rapporten" in raw
    assert "Datakvalitet avvik" in raw
    assert "P90" not in raw
    card_count = raw.count('"visualType": "cardVisual"')
    assert card_count <= 1


def test_pbip_avoids_the_custom_theme_reference_that_breaks_desktop_loading() -> None:
    report = read_json(REPORT / "definition" / "report.json")
    assert "customTheme" not in report.get("themeCollection", {})
    registered = next(
        (package for package in report.get("resourcePackages", []) if package.get("name") == "RegisteredResources"),
        {"items": []},
    )
    assert all(item.get("type") != 202 for item in registered.get("items", []))


def test_v4_pbix_contains_cached_model_and_complete_report() -> None:
    assert PBIX.is_file() and PBIX.stat().st_size > 1_000_000
    with zipfile.ZipFile(PBIX) as package:
        assert "DataModel" in package.namelist()
        pages = json.loads(package.read("Report/definition/pages/pages.json"))
        names = [
            json.loads(package.read(f"Report/definition/pages/{page_id}/page.json"))["displayName"]
            for page_id in pages["pageOrder"]
        ]
    assert names == PAGE_NAMES
