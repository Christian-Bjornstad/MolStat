from __future__ import annotations

import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "powerbi" / "Hemato_Statistikk_V3"
SEMANTIC = PROJECT / "Hemato Semantikk"
REPORT = PROJECT / "Hemato Statistikk Rapport.Report"
PBIX = ROOT / "powerbi" / "Hemato_Statistikk_V3.pbix"

PAGE_NAMES = [
    "Oversikt",
    "Volum og uker",
    "Volum per analyse",
    "Svartid",
    "Svartid per analyse",
    "Oppfølging",
    "Tidslinje",
    "Datakvalitet",
]
RESULT_PAGE_IDS = {
    "1f0a1111111111111111",
    "3f0a3333333333333333",
    "5f0a5555555555555555",
    "6f0a6666666666666666",
    "7f0a7777777777777777",
    "8f0a8888888888888888",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def visual_paths(page_id: str) -> list[Path]:
    return list((REPORT / "definition" / "pages" / page_id / "visuals").glob("*/visual.json"))


def test_v3_is_a_separate_eight_page_project() -> None:
    assert (PROJECT / "Hemato_Statistikk_V3.pbip").is_file()
    pages_root = REPORT / "definition" / "pages"
    order = read_json(pages_root / "pages.json")["pageOrder"]
    assert len(order) == 8
    assert [read_json(pages_root / p / "page.json")["displayName"] for p in order] == PAGE_NAMES


def test_date_table_supports_continuous_week_and_month_axes() -> None:
    date_tmdl = (SEMANTIC / "definition" / "tables" / "Dato.tmdl").read_text(encoding="utf-8")
    assert "column MånedStart" in date_tmdl or "column 'MånedStart'" in date_tmdl
    all_visuals = "\n".join(path.read_text(encoding="utf-8") for page in PAGE_NAMES for path in [])
    all_visuals = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPORT / "definition" / "pages").glob("*/visuals/*/visual.json")
    )
    assert '"Property": "UkeStart"' in all_visuals
    assert '"Property": "MånedStart"' in all_visuals
    assert "'Scalar'" in all_visuals
    partition = date_tmdl.split("partition Dato = calculated", 1)[1]
    assert "resultater[Tidspunkt.prøvetaking]" not in partition
    assert "resultater[Tidspunkt.godkjenning]" not in partition


def test_all_date_slicers_are_large_dropdowns() -> None:
    for path in (REPORT / "definition" / "pages").glob("*/visuals/filter-*/visual.json"):
        visual = read_json(path)
        if visual["visual"]["visualType"] != "slicer":
            continue
        assert visual["position"]["height"] >= 76
        data = visual["visual"]["objects"]["data"][0]["properties"]
        assert data["mode"]["expr"]["Literal"]["Value"] == "'Dropdown'"


def test_result_pages_offer_material_filter() -> None:
    for page_id in RESULT_PAGE_IDS:
        material = REPORT / "definition" / "pages" / page_id / "visuals" / "filter-material" / "visual.json"
        assert material.is_file()
        raw = material.read_text(encoding="utf-8")
        assert '"Entity": "resultater"' in raw
        assert '"Property": "Materiale"' in raw


def test_report_removes_redundant_status_copy() -> None:
    all_visuals = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPORT / "definition" / "pages").glob("*/visuals/*/visual.json")
    )
    assert "Lesing av status" not in all_visuals
    assert "Oppfølging uten falsk writeback" not in all_visuals
    assert "Klikk for å filtrere resten av siden" not in all_visuals


def test_followup_tables_are_narrow_enough_for_the_canvas() -> None:
    for page_id, visual_id in (
        ("6f0a6666666666666666", "followup-table"),
        ("7f0a7777777777777777", "timeline-table"),
    ):
        visual = read_json(REPORT / "definition" / "pages" / page_id / "visuals" / visual_id / "visual.json")
        fields = visual["visual"]["query"]["queryState"]["Values"]["projections"]
        assert len(fields) <= 7
        headers = visual["visual"]["objects"]["columnHeaders"][0]["properties"]
        assert headers["autoSizeColumnWidth"]["expr"]["Literal"]["Value"] == "true"
    timeline = read_json(REPORT / "definition" / "pages" / "7f0a7777777777777777" / "visuals" / "timeline-table" / "visual.json")
    assert timeline["position"]["width"] >= 1000


def test_titles_and_cards_are_not_clipped() -> None:
    page_id = "1f0a1111111111111111"
    title = read_json(REPORT / "definition" / "pages" / page_id / "visuals" / "page-title" / "visual.json")
    padding = title["visual"]["visualContainerObjects"]["padding"][0]["properties"]
    assert padding["top"]["expr"]["Literal"]["Value"] == "0D"
    assert padding["bottom"]["expr"]["Literal"]["Value"] == "0D"
    card = read_json(REPORT / "definition" / "pages" / page_id / "visuals" / "kpi-total" / "visual.json")
    accent = card["visual"]["objects"]["accentBar"][0]["properties"]
    assert accent["position"]["expr"]["Literal"]["Value"] == "'Top'"
    compact_card = read_json(REPORT / "definition" / "pages" / "5f0a5555555555555555" / "visuals" / "kpi-median" / "visual.json")
    assert compact_card["position"]["height"] >= 96


def test_volume_rolling_measure_respects_antall_filters() -> None:
    antall_tmdl = (SEMANTIC / "definition" / "tables" / "antall.tmdl").read_text(encoding="utf-8")
    assert "measure 'Fireukers glidende analyser'" in antall_tmdl
    assert "MAX ( antall[Tidspunkt.analysebestilling] )" in antall_tmdl
    volume = read_json(REPORT / "definition" / "pages" / "2f0a2222222222222222" / "visuals" / "volume-week" / "visual.json")
    raw = json.dumps(volume, ensure_ascii=False)
    assert '"Entity": "antall"' in raw
    assert '"Property": "Fireukers glidende analyser"' in raw


def test_dense_category_comparisons_do_not_require_scrollbars() -> None:
    overview = read_json(REPORT / "definition" / "pages" / "1f0a1111111111111111" / "visuals" / "group-turnaround" / "visual.json")
    assert len(overview["visual"]["query"]["queryState"]["Y"]["projections"]) == 1
    turnaround = read_json(REPORT / "definition" / "pages" / "3f0a3333333333333333" / "visuals" / "turnaround-group" / "visual.json")
    material = read_json(REPORT / "definition" / "pages" / "5f0a5555555555555555" / "visuals" / "material-turnaround" / "visual.json")
    assert turnaround["visual"]["visualType"] == "scatterChart"
    assert material["visual"]["visualType"] == "scatterChart"
    for visual in (turnaround, material):
        query_state = visual["visual"]["query"]["queryState"]
        assert "Category" in query_state
        assert "Details" not in query_state


def test_v3_pbix_contains_cached_model_and_eight_pages() -> None:
    assert PBIX.is_file() and PBIX.stat().st_size > 1_000_000
    with zipfile.ZipFile(PBIX) as package:
        assert "DataModel" in package.namelist()
        pages = json.loads(package.read("Report/definition/pages/pages.json"))
        names = [
            json.loads(package.read(f"Report/definition/pages/{page_id}/page.json"))["displayName"]
            for page_id in pages["pageOrder"]
        ]
    assert names == PAGE_NAMES
