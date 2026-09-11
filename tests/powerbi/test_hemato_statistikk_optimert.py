from __future__ import annotations

import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "powerbi" / "Hemato_Statistikk_Optimert"
SEMANTIC = PROJECT / "Hemato Semantikk"
REPORT = PROJECT / "Hemato Statistikk Rapport.Report"
PBIX = ROOT / "powerbi" / "Hemato_Statistikk_Optimert.pbix"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_project_is_a_portable_pbip_with_linked_semantic_model() -> None:
    manifest = json.loads(read_text(PROJECT / "Hemato_Statistikk_Optimert.pbip"))
    assert manifest["version"] == "1.0"
    assert manifest["artifacts"][0]["report"]["path"] == "Hemato Statistikk Rapport.Report"

    report_ref = json.loads(read_text(REPORT / "definition.pbir"))
    assert report_ref["datasetReference"]["byPath"]["path"] == "../Hemato Semantikk"
    assert (SEMANTIC / "definition.pbism").is_file()


def test_deliverable_pbix_contains_report_and_embedded_data_model() -> None:
    assert PBIX.is_file()
    assert PBIX.stat().st_size > 1_000_000
    with zipfile.ZipFile(PBIX) as package:
        entries = set(package.namelist())
    assert "DataModel" in entries
    assert "Report/Layout" in entries or "Report/definition/report.json" in entries


def test_all_pbip_text_files_are_utf8_without_bom() -> None:
    text_suffixes = {".tmdl", ".json", ".pbip", ".pbir", ".pbism", ".md", ".dax"}
    files_with_bom = [
        path.relative_to(PROJECT)
        for path in PROJECT.rglob("*")
        if path.is_file()
        and path.suffix.lower() in text_suffixes
        and path.read_bytes().startswith(b"\xef\xbb\xbf")
    ]
    assert files_with_bom == []


def test_calendar_is_controlled_and_auto_date_tables_are_removed() -> None:
    tables = SEMANTIC / "definition" / "tables"
    calendar = read_text(tables / "Dato.tmdl")
    required_columns = {
        "Date",
        "År",
        "Kvartal",
        "MånedNr",
        "Måned",
        "ÅrMåned",
        "ÅrMånedSort",
        "ISOÅr",
        "ISOUke",
        "ÅrUke",
        "UkeStart",
    }
    for column in required_columns:
        assert f"column '{column}'" in calendar or f"column {column}" in calendar

    generated = [path.name for path in tables.glob("*.tmdl") if "DateTable" in path.name]
    assert generated == []


def test_turnaround_columns_reject_invalid_intervals_instead_of_zeroing_them() -> None:
    resultater = read_text(
        SEMANTIC / "definition" / "tables" / "resultater.tmdl"
    )
    for column in (
        "Svartid pasient dager",
        "Svartid seksjon dager",
        "Svartid enhet dager",
        "Godkjenningsetterslep dager",
        "Enhet starttid",
        "Enhet startkilde",
        "Datakvalitet status",
    ):
        assert f"column '{column}'" in resultater

    assert "timer < 0,\n\t\tBLANK" in resultater or "varighet < 0" in resultater
    assert '"Negativ analysetid - sjekk data"' in resultater


def test_turnaround_calculated_columns_have_explicit_numeric_types() -> None:
    resultater = read_text(
        SEMANTIC / "definition" / "tables" / "resultater.tmdl"
    )
    for column in (
        "Svartid pasient dager",
        "Svartid seksjon dager",
        "Svartid enhet dager",
        "Godkjenningsetterslep dager",
    ):
        block = resultater.split(f"column '{column}'", 1)[1].split("\n\tcolumn ", 1)[0]
        assert "dataType: double" in block


def test_existing_report_fields_remain_backwards_compatible() -> None:
    resultater = read_text(
        SEMANTIC / "definition" / "tables" / "resultater.tmdl"
    )
    antall = read_text(SEMANTIC / "definition" / "tables" / "antall.tmdl")

    for column in (
        "DatoGodkjenning",
        "Prøvetaking tidspunkt",
        "Analysebestilling",
        "Tidspunkt ekstraksjon ferdig",
        "Tidspunkt ferdig analyse",
        "Starttid analyse",
        "Starttid analyse kilde",
        "Analysetid timer",
        "Analysetid dager",
        "Analysetid status",
    ):
        assert f"column '{column}'" in resultater or f"column {column}" in resultater

    for measure in (
        "Gjennomsnitt analysetid dager",
        "Svarfrist mål",
        "Antall innen frist",
        "Antall over frist",
        "Andel innen frist",
        "Avvik fra svarfrist dager",
        "Farge svartid",
    ):
        assert f"measure '{measure}'" in resultater

    for column in ("DatoOpprettet", "Analyse ferdig dato"):
        assert f"column '{column}'" in antall or f"column {column}" in antall

    for measure in (
        "Analyser denne måned",
        "Antall",
        "Mål",
        "Analyser forrige måned",
        "Endring analyser %",
    ):
        assert f"measure '{measure}'" in antall or f"measure {measure}" in antall


def test_robust_measures_and_individual_deadlines_are_present() -> None:
    resultater = read_text(
        SEMANTIC / "definition" / "tables" / "resultater.tmdl"
    )
    required_measures = (
        "Antall gyldige svartider",
        "Median svartid dager",
        "P75 svartid dager",
        "P90 svartid dager",
        "Antall innen individuell frist",
        "Antall over individuell frist",
        "Andel innen individuell frist",
        "Antall ekskludert datakvalitet",
        "Andel ekskludert datakvalitet",
        "Entydig svarfrist dager",
        "Fireukers glidende volum",
    )
    for measure in required_measures:
        assert f"measure '{measure}'" in resultater

    assert "SELECTEDVALUE ( resultater[Svarfrist] )" in resultater
    assert "PERCENTILEX.INC" in resultater


def test_report_has_five_accessible_1280_by_720_pages() -> None:
    pages_root = REPORT / "definition" / "pages"
    pages = json.loads(read_text(pages_root / "pages.json"))["pageOrder"]
    names = []
    for page_id in pages:
        page = json.loads(read_text(pages_root / page_id / "page.json"))
        names.append(page["displayName"])
        assert page["width"] == 1280
        assert page["height"] == 720

    assert names == [
        "Ledelsesoversikt",
        "Volum og kapasitet",
        "Svartid",
        "Oppfølging",
        "Datakvalitet",
    ]


def test_report_uses_custom_theme_and_documents_definitions() -> None:
    report = json.loads(read_text(REPORT / "definition" / "report.json"))
    packages = report["resourcePackages"]
    registered = next(item for item in packages if item["name"] == "RegisteredResources")
    resource_names = {item["name"] for item in registered["items"]}
    assert "hemato-ous-theme.json" in resource_names
    assert (REPORT / "StaticResources" / "RegisteredResources" / "hemato-ous-theme.json").is_file()

    all_visuals = "\n".join(
        read_text(path)
        for path in (REPORT / "definition" / "pages").glob("*/visuals/*/visual.json")
    )
    for label in (
        "Pasientforløp",
        "Seksjonstid",
        "Enhetstid",
        "Godkjenningsetterslep",
        "Datakvalitet",
    ):
        assert label in all_visuals
    assert "Innen frist" in all_visuals


def test_writeback_plan_is_explicit_and_does_not_claim_native_comments() -> None:
    plan = read_text(PROJECT / "WRITEBACK.md")
    for field in (
        "Stabil saksnøkkel",
        "Status",
        "Eier",
        "Kommentar",
        "Opprettet dato",
        "Sist endret",
    ):
        assert field in plan
    assert "ikke" in plan.lower()


def test_followup_table_shows_row_level_durations_without_summing_them() -> None:
    visual = read_text(
        REPORT
        / "definition"
        / "pages"
        / "4f0a4444444444444444"
        / "visuals"
        / "followup-table"
        / "visual.json"
    )
    for duration in (
        "Svartid pasient dager",
        "Svartid seksjon dager",
        "Svartid enhet dager",
    ):
        assert f"Sum(resultater.{duration})" not in visual
        assert f'"Property": "{duration}"' in visual
