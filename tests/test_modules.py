from molstat._backlog.export import BACKLOG_PUBLIC_COLUMNS
import molstat.modules as modules
from molstat.statistics import (
    ANTALL_COLUMNS,
    RESULTATER_COLUMNS,
    SOLIDE_ANTALL_COLUMNS,
    SOLIDE_RESULTATER_COLUMNS,
)


def test_default_registry_groups_capabilities_by_unit() -> None:
    assert tuple(unit.key for unit in modules.DEFAULT_UNITS) == (
        "hemato",
        "solide",
        "lege",
        "flow",
        "fish",
        "pre",
    )
    assert len({unit.key for unit in modules.DEFAULT_UNITS}) == len(
        modules.DEFAULT_UNITS
    )

    hemato = modules.DEFAULT_UNITS.require("hemato")
    assert hemato.status == "active"
    assert tuple(cap.job_kind for cap in hemato.capabilities) == (
        "statistics",
        "backlog",
    )


def test_active_unit_capabilities_define_runtime_and_publication_contracts() -> None:
    hemato = modules.DEFAULT_UNITS.require("hemato")
    solide = modules.DEFAULT_UNITS.require("solide")
    hemato_statistics = hemato.capability("statistics")
    solide_statistics = solide.capability("statistics")
    hemato_backlog = hemato.capability("backlog")

    assert hemato_statistics.processor_profile == "hemato"
    assert hemato_statistics.sharepoint_folder == "hemato"
    assert hemato_statistics.allowed_columns == {
        "antall.csv": frozenset(ANTALL_COLUMNS),
        "resultater.csv": frozenset(RESULTATER_COLUMNS),
    }
    assert solide_statistics.processor_profile == "solide"
    assert solide_statistics.sharepoint_folder == "solide"
    assert solide_statistics.allowed_columns == {
        "antall.csv": frozenset(SOLIDE_ANTALL_COLUMNS),
        "resultater.csv": frozenset(SOLIDE_RESULTATER_COLUMNS),
    }
    assert hemato_backlog.schedule_key == "backlog_hourly"
    assert hemato_backlog.sharepoint_folder == "Prøveflyt"
    assert hemato_backlog.allowed_columns == {
        "restansehistorikk_hemato.csv": frozenset(BACKLOG_PUBLIC_COLUMNS)
    }


def test_hist_is_not_available_in_registry_or_runnable_lists() -> None:
    import pytest
    assert "hist" not in {unit.key for unit in modules.DEFAULT_UNITS}
    with pytest.raises(KeyError):
        modules.DEFAULT_UNITS.require("hist")
    for kind in ("statistics", "backlog"):
        assert "hist" not in {unit.key for unit in modules.DEFAULT_UNITS.for_job(kind)}


def test_registry_filters_by_job_kind_and_enabled_units() -> None:
    assert tuple(unit.key for unit in modules.DEFAULT_UNITS.for_job("statistics")) == (
        "hemato",
        "solide",
        "lege",
        "flow",
        "fish",
        "pre",
    )
    assert tuple(unit.key for unit in modules.DEFAULT_UNITS.for_job("backlog")) == (
        "hemato",
    )
    assert tuple(
        unit.key
        for unit in modules.DEFAULT_UNITS.for_job(
            "statistics", enabled_keys=("solide",)
        )
    ) == ("solide",)
    assert tuple(unit.key for unit in modules.DEFAULT_UNITS.active(("hemato",))) == (
        "hemato",
    )


def test_registry_rejects_unknown_unit_and_missing_capability() -> None:
    try:
        modules.DEFAULT_UNITS.require("ukjent")
    except KeyError as error:
        assert "ukjent" in str(error)
    else:
        raise AssertionError("Unknown unit key should fail explicitly")

    try:
        modules.DEFAULT_UNITS.require("solide").capability("backlog")
    except KeyError as error:
        assert "backlog" in str(error)
    else:
        raise AssertionError("Missing capability should fail explicitly")
