from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from molstat.statistics import (
    Unit,
    UnitsConfigError,
    default_units_path,
    load_units,
    validate_units,
)


VALID = {
    "units": {
        "hemato": {
            "label": "Hemato",
            "analysis_codes": ["JAK2-V617F-OU", "CALR-OU"],
            "reports": [
                {"job_key": "ordered", "report_id": "PAT-DIT-ANTALL-OU"},
                {"job_key": "answered", "report_id": "PAT-DIT-RESULTATER-OU"},
            ],
        },
        "solide": {
            "profile": "solide",
            "analysis_codes": ["EKSTRAKSJON-SO-OU"],
            "reports": [
                {"job_key": "ordered", "report_id": "PAT-DIT-ANTALL-OU"},
            ]
        },
    }
}


def test_validate_units_builds_units() -> None:
    units = validate_units(VALID)
    assert [unit.key for unit in units] == ["hemato", "solide"]
    hemato = units[0]
    assert hemato.label == "Hemato"
    assert hemato.report_by_key("ordered").report_id == "PAT-DIT-ANTALL-OU"


def test_profile_defaults_to_hemato_and_validates() -> None:
    units = validate_units(VALID)
    assert units[0].profile == "hemato"
    assert units[1].profile == "solide"
    invalid = {
        "units": {
            "x": {
                "profile": "ukjent",
                "analysis_codes": ["JAK2-V617F-OU"],
                "reports": [
                    {"job_key": "ordered", "report_id": "PAT-DIT-ANTALL-OU"}
                ],
            }
        }
    }
    with pytest.raises(UnitsConfigError):
        validate_units(invalid)


def test_label_falls_back_to_key() -> None:
    units = validate_units(VALID)
    assert units[1].label == "solide"


def test_missing_units_object_is_rejected() -> None:
    with pytest.raises(UnitsConfigError):
        validate_units({})


def test_duplicate_job_keys_within_unit_are_rejected() -> None:
    raw = {
        "units": {
            "hemato": {
                "reports": [
                    {"job_key": "ordered", "report_id": "A-OU"},
                    {"job_key": "ordered", "report_id": "B-OU"},
                ]
            }
        }
    }
    with pytest.raises(UnitsConfigError):
        validate_units(raw)


def test_invalid_report_id_is_rejected() -> None:
    raw = {
        "units": {
            "hemato": {
                "analysis_codes": ["CALR-OU"],
                "reports": [{"job_key": "ordered", "report_id": "bad id!"}]
            }
        }
    }
    with pytest.raises(UnitsConfigError):
        validate_units(raw)


def test_invalid_unit_key_is_rejected() -> None:
    raw = {"units": {"ikke gyldig!": {"analysis_codes": ["CALR-OU"], "reports": [{"job_key": "a", "report_id": "A"}]}}}
    with pytest.raises(UnitsConfigError):
        validate_units(raw)


def test_load_units_reads_file(tmp_path: Path) -> None:
    path = tmp_path / "units.json"
    path.write_text(json.dumps(VALID), encoding="utf-8")
    units = load_units(path)
    assert len(units) == 2


def test_load_units_missing_file(tmp_path: Path) -> None:
    with pytest.raises(UnitsConfigError):
        load_units(tmp_path / "missing.json")


def test_default_units_path_sits_beside_config() -> None:
    config = Path("C:/app/config.json")
    assert default_units_path(config) == Path("C:/app/units.json")


def test_analysis_codes_are_loaded() -> None:
    units = validate_units(VALID)
    assert units[0].analysis_codes == ("JAK2-V617F-OU", "CALR-OU")


def test_production_units_match_documented_report_specific_code_lists() -> None:
    units_path = Path(__file__).parents[2] / "config" / "units.json"
    units = {unit.key: unit for unit in load_units(units_path)}

    hemato = units["hemato"]
    assert len(hemato.analysis_codes) == 70
    assert hemato.report_by_key("ordered").analysis_codes is None
    assert hemato.report_by_key("answered").analysis_codes is None

    solide = units["solide"]
    ordered = solide.report_by_key("ordered").analysis_codes
    answered = solide.report_by_key("answered").analysis_codes
    assert ordered is not None
    assert answered is None
    assert len(ordered) == 69
    assert ordered[0] == "EKSTRAKSJON-OU"
    assert "BRCA1-OU" not in ordered
    assert "BRCA2-OU" not in ordered
    assert len(solide.analysis_codes) == 70
    assert solide.analysis_codes[0] == "FORBVIDERE-OU"
    assert "EKSTRAKSJON-OU" not in solide.analysis_codes
    assert "BRCA1-OU" in solide.analysis_codes
    assert "BRCA2-OU" in solide.analysis_codes


def test_missing_analysis_codes_is_rejected() -> None:
    import copy

    raw = copy.deepcopy(VALID)
    del raw["units"]["hemato"]["analysis_codes"]
    with pytest.raises(UnitsConfigError):
        validate_units(raw)


def test_duplicate_analysis_codes_are_rejected() -> None:
    import copy

    raw = copy.deepcopy(VALID)
    raw["units"]["hemato"]["analysis_codes"] = ["CALR-OU", "CALR-OU"]
    with pytest.raises(UnitsConfigError):
        validate_units(raw)


def test_invalid_analysis_code_is_rejected() -> None:
    import copy

    raw = copy.deepcopy(VALID)
    raw["units"]["hemato"]["analysis_codes"] = ["bad code!"]
    with pytest.raises(UnitsConfigError):
        validate_units(raw)

