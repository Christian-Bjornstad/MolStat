import csv
from datetime import date
from pathlib import Path

import pytest

from molstat._statistics.specialized_lookup import default_lookup_path, validate_lookup
from molstat.fetching import _statistics_job
from molstat.lvms.report_job import validate_report_job
from molstat.statistics import StatisticsProcessor
from molstat.services import DefaultServices
from molstat.modules import DEFAULT_UNITS
from molstat.publisher import PublicationPolicy, SharePointPublisher, default_forbidden_patterns
from molstat.unit_settings import default_unit_file, load_unit_file


ROOT = Path(__file__).resolve().parents[2]
LOOKUPS = {
    "flow": ROOT / "powerbi/Flow_Statistikk_V1/Data/analyse_lookup.csv",
    "fish": ROOT / "powerbi/Fish_Statistikk_V1/Data/analyse_lookup.csv",
    "pre": ROOT / "powerbi/Pre_Statistikk_V1/Data/analyse_lookup.csv",
}


def archive(folder, report_id, rows):
    path = folder / f"{report_id}__2026-09-01__2026-09-02.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="cp1252", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(["Sample ID", "PID", "Analyse", "Tidspunkt opprettet", "Tidspunkt prøvetaking", "Tidspunkt analysebestilling", "Tidspunkt analyseresultat", "Tidspunkt godkjenning"])
        writer.writerows(rows)
    return path


@pytest.mark.parametrize("key,count,roles", [
    ("flow", 66, ("antall", "resultater")),
    ("fish", 61, ("antall", "resultater")),
    ("pre", 50, ("resultater",)),
])
def test_specialized_defaults_match_lookup_and_roles(key, count, roles):
    unit = load_unit_file(default_unit_file(key)).unit
    assert len(unit.analysis_codes) == count
    assert tuple(unit_file.job_key for unit_file in unit.reports) == tuple("ordered" if r == "antall" else "answered" for r in roles)
    validate_lookup(LOOKUPS[key], key, set(unit.analysis_codes))
    validate_lookup(default_lookup_path(key), key, set(unit.analysis_codes))


def test_fish_codes_keep_original_case_and_slash():
    job = validate_report_job({"job_key": "answered", "report_type": "PRODSTAT", "category": "PATOLOGI", "report_id": "PAT-DIT-RESULTATER-OU", "analysis_codes": ["FISH-11qEP-OU", "FISH-X/Y-EP-OU"], "created_from": "01.09.2026", "created_to": "02.09.2026", "output_stem": "PAT-DIT-RESULTATER-FISH-OU"})
    assert job.analysis_text() == "FISH-11qEP-OU,FISH-X/Y-EP-OU"


def test_new_unit_jobs_use_lvms_report_id_and_separate_archive_stem():
    for key, expected_fetches in (
        ("flow", ("PAT-DIT-ANTALL-OU", "PAT-DIT-RESULTATER-OU")),
        ("fish", ("PAT-DIT-ANTALL-OU", "PAT-DIT-RESULTATER-OU")),
        ("pre", ("PAT-DIT-RESULTATER-OU",)),
    ):
        unit = load_unit_file(default_unit_file(key)).unit
        jobs = tuple(_statistics_job(unit, report, date(2026, 9, 1), date(2026, 9, 2)) for report in unit.reports)
        assert tuple(job.report_id for job in jobs) == expected_fetches
        assert all(job.output_stem.endswith(f"-{key.upper()}-OU") for job in jobs)
        assert all(tuple(job.analysis_codes) == unit.analysis_codes for job in jobs)


def test_new_units_can_be_enabled_in_molstat_settings(tmp_path):
    sensitive = tmp_path / "sensitive"
    sharepoint = tmp_path / "sharepoint"
    sensitive.mkdir()
    sharepoint.mkdir()
    service = DefaultServices(tmp_path / "settings.json")
    service.save_settings_fields({
        "sensitive_root": str(sensitive), "sharepoint_root": str(sharepoint),
        "lvms_url": "https://lvms.example.invalid",
        "enabled_hemato": "false", "enabled_solide": "false",
        "enabled_flow": "true", "enabled_fish": "true", "enabled_pre": "true",
    })
    assert service.settings.enabled_units == ("flow", "fish", "pre")
    assert all(service.settings.statistics_lookup_paths[key].is_relative_to(sensitive) for key in LOOKUPS)
    system = service._build_system(require_statistics=True)
    assert tuple(unit.key for unit in system.units.for_job("statistics")) == ("flow", "fish", "pre")


@pytest.mark.parametrize("key,code", [("flow", "FLOW-02-OU"), ("fish", "FISH-ALKBA-OU")])
def test_two_report_profiles_process_archives_without_identifiers(tmp_path, key, code):
    unit = load_unit_file(default_unit_file(key)).unit
    report_ids = {"antall": unit.reports[0].report_id, "resultater": unit.reports[1].report_id}
    raw = tmp_path / "raw"
    row = ["SENSITIVE", "PERSON", code, "01.09.2026 08:00:00", "01.09.2026 07:00:00", "01.09.2026 09:00:00", "02.09.2026 08:00:00", "02.09.2026 09:00:00"]
    files = [archive(raw, report_id, [row]) for report_id in report_ids.values()]
    result = StatisticsProcessor(LOOKUPS[key], profile=key, report_ids=report_ids).process(key, files, tmp_path / "out")
    assert result.row_counts == {"antall": 1, "resultater": 1}
    text = result.resultater.read_text(encoding="utf-8-sig")
    assert "SENSITIVE" not in text and "PERSON" not in text
    capability = DEFAULT_UNITS.require(key).capability("statistics")
    publisher = SharePointPublisher(PublicationPolicy(capability.allowed_columns, default_forbidden_patterns()))
    publisher.publish({"antall.csv": result.antall, "resultater.csv": result.resultater}, tmp_path / "published")


def test_pre_single_report_processes_activity_chain(tmp_path):
    unit = load_unit_file(default_unit_file("pre")).unit
    report_id = unit.reports[0].report_id
    rows = [
        ["SENSITIVE", "PERSON", "EKSTRAKSJON-OU", "01.09.2026 08:00:00", "", "", "01.09.2026 09:00:00", ""],
        ["SENSITIVE", "PERSON", "FORBVEVDNA-OU", "01.09.2026 08:00:00", "", "", "01.09.2026 12:00:00", ""],
        ["SENSITIVE", "PERSON", "EKSTRAMAXDNA-OU", "01.09.2026 08:00:00", "", "", "02.09.2026 08:00:00", ""],
    ]
    current = archive(tmp_path / "raw", report_id, rows)
    processor = StatisticsProcessor(LOOKUPS["pre"], profile="pre", report_ids={"resultater": report_id})
    result = processor.process("pre", [current], tmp_path / "out")
    assert result.row_counts == {"antall": 0, "resultater": 3}
    with result.resultater.open(encoding="utf-8-sig", newline="") as handle:
        data = {row["Analyse"]: row for row in csv.DictReader(handle, delimiter=";")}
    assert data["EKSTRAMAXDNA-OU"]["Prosessdager"] == "0.8333333333"
    assert "SENSITIVE" not in result.resultater.read_text(encoding="utf-8-sig")
    capability = DEFAULT_UNITS.require("pre").capability("statistics")
    publisher = SharePointPublisher(PublicationPolicy(capability.allowed_columns, default_forbidden_patterns()))
    publisher.publish({"antall.csv": result.antall, "resultater.csv": result.resultater}, tmp_path / "published")
