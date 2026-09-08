from molstat._backlog.export import BACKLOG_PUBLIC_COLUMNS
from pathlib import Path
from types import SimpleNamespace

from molstat.modules import DEFAULT_MODULES, DataModule, ModuleRegistry
from molstat.statistics import (
    ANTALL_COLUMNS,
    RESULTATER_COLUMNS,
    SOLIDE_ANTALL_COLUMNS,
    SOLIDE_RESULTATER_COLUMNS,
)
from molstat.system import MolStatSystem


def test_default_registry_has_unique_explicit_modules() -> None:
    assert tuple(module.key for module in DEFAULT_MODULES) == (
        "hemato",
        "solide",
        "proveflyt",
    )
    assert len({module.key for module in DEFAULT_MODULES}) == len(DEFAULT_MODULES)


def test_statistics_modules_define_runtime_and_publication_contracts() -> None:
    hemato = DEFAULT_MODULES.require("hemato")
    solide = DEFAULT_MODULES.require("solide")

    assert hemato.job_kind == solide.job_kind == "statistics"
    assert hemato.schedule_key == solide.schedule_key == "statistics_daily"
    assert hemato.processor_profile == "hemato"
    assert solide.processor_profile == "solide"
    assert hemato.sharepoint_folder == "hemato"
    assert solide.sharepoint_folder == "solide"
    assert hemato.allowed_columns == {
        "antall.csv": frozenset(ANTALL_COLUMNS),
        "resultater.csv": frozenset(RESULTATER_COLUMNS),
    }
    assert solide.allowed_columns == {
        "antall.csv": frozenset(SOLIDE_ANTALL_COLUMNS),
        "resultater.csv": frozenset(SOLIDE_RESULTATER_COLUMNS),
    }


def test_proveflyt_module_defines_detail_privacy_boundary() -> None:
    module = DEFAULT_MODULES.require("proveflyt")

    assert module.display_name == "Prøveflyt"
    assert module.job_kind == "backlog"
    assert module.schedule_key == "backlog_hourly"
    assert module.processor_profile == "backlog"
    assert module.sharepoint_folder == "Prøveflyt"
    assert module.allowed_columns == {
        "restansehistorikk.csv": frozenset(BACKLOG_PUBLIC_COLUMNS)
    }
    assert module.status_fields == (
        "rows",
        "invalid",
        "excluded",
        "snapshots",
        "published_rows",
    )


def test_registry_filters_by_job_kind_and_rejects_unknown_key() -> None:
    assert tuple(module.key for module in DEFAULT_MODULES.for_job("statistics")) == (
        "hemato",
        "solide",
    )
    assert tuple(module.key for module in DEFAULT_MODULES.for_job("backlog")) == (
        "proveflyt",
    )

    try:
        DEFAULT_MODULES.require("ukjent")
    except KeyError as error:
        assert "ukjent" in str(error)
    else:
        raise AssertionError("Unknown module key should fail explicitly")


def test_system_routes_new_statistics_module_without_unit_branch(tmp_path: Path) -> None:
    module = DataModule(
        key="ny",
        display_name="Ny statistikk",
        job_kind="statistics",
        schedule_key="statistics_daily",
        processor_profile="ny",
        sharepoint_folder="Ny mappe",
        publication_files=(("antall.csv", frozenset({"Antall"})),),
        status_fields=("rows",),
    )
    registry = ModuleRegistry((module,))
    destinations: list[Path] = []

    class Processor:
        def process(self, unit, archived, output_dir):
            assert unit == "ny"
            assert archived == ()
            return SimpleNamespace(
                antall=output_dir / "antall.csv",
                resultater=output_dir / "resultater.csv",
                row_counts={"antall.csv": 2},
            )

    class Publisher:
        def publish(self, files, destination):
            assert set(files) == {"antall.csv", "resultater.csv"}
            destinations.append(destination)

    system = MolStatSystem.__new__(MolStatSystem)
    system.statistics_fetch = lambda: {"ny": ()}
    system.statistics_processors = {"ny": Processor()}
    system.publisher = {"ny": Publisher()}
    system.sharepoint_root = tmp_path / "sharepoint"
    system.work_root = tmp_path / "work"
    system.modules = registry

    assert system.run_statistics() == {"rows": 2, "units": 1}
    assert destinations == [tmp_path / "sharepoint" / "Ny mappe"]
