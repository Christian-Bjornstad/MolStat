from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from ._statistics.incremental import (
    IncrementalPlan,
    IncrementalPlanError,
    PlannedFetch,
    plan_all_units,
    plan_unit,
)
from ._statistics.manifest import (
    ManifestError,
    ManifestStore,
    RunRecord,
    UnitReport as ManifestUnitReport,
    load_statistics_settings,
    plan_incremental_interval,
    resolve_statistics_root,
)
from ._statistics.merge_raw import merge_report_csvs, write_merged_csv
from ._statistics.post_processing import (
    ProcessOutcome,
    find_report_archives,
    process_unit,
)
from ._statistics.processing import (
    ANTALL_COLUMNS,
    RESULTATER_COLUMNS,
    SOLIDE_ANTALL_COLUMNS,
    SOLIDE_RESULTATER_COLUMNS,
    _best_extraction,
    build_antall,
    build_resultater,
    build_resultater_solide,
    clean_text,
    klassifiser_ekstraksjon,
    load_lookup,
    parse_tidspunkt,
    process_reports,
    read_lvms_csv,
    write_excel_csv2,
)
from ._statistics.units import (
    Unit,
    UnitReport as ConfiguredUnitReport,
    UnitsConfigError,
    default_units_path,
    load_units,
    validate_units,
)

# Compatibility name for the validated manifest interval contract.
UnitReport = ManifestUnitReport


@dataclass(frozen=True, slots=True)
class StatisticsResult:
    antall: Path
    resultater: Path
    row_counts: Mapping[str, int]


class StatisticsProcessor:
    def __init__(self, lookup_path: Path, *, profile: str = "hemato") -> None:
        self.lookup_path = lookup_path
        self.profile = profile

    def process(
        self,
        unit: str,
        raw_files: Sequence[Path],
        output_dir: Path,
    ) -> StatisticsResult:
        del unit
        ordered = _one_report(raw_files, "ANTALL")
        answered = _one_report(raw_files, "RESULTATER")
        extraction = _one_report(raw_files, "EKSTRAKSJON")
        counts = process_reports(
            ordered,
            answered,
            extraction,
            self.lookup_path,
            output_dir,
            profile=self.profile,
        )
        return StatisticsResult(
            antall=output_dir / "antall.csv",
            resultater=output_dir / "resultater.csv",
            row_counts=counts,
        )


def _one_report(raw_files: Sequence[Path], marker: str) -> Path:
    matches = [path for path in raw_files if marker in path.name.upper()]
    if len(matches) != 1:
        raise ValueError(
            f"Forventet nøyaktig én {marker}-rapport, fant {len(matches)}."
        )
    return matches[0]
