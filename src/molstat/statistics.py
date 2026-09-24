from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
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
from .database import MolStatDatabase
from .registry import (
    OccurrenceEventInput,
    OccurrenceInput,
    RegistryImportItem,
    SampleRegistry,
)

# Compatibility name for the validated manifest interval contract.
UnitReport = ManifestUnitReport


@dataclass(frozen=True, slots=True)
class StatisticsResult:
    antall: Path
    resultater: Path
    row_counts: Mapping[str, int]
    publication_files: Mapping[str, Path] | None = None


class StatisticsProcessor:
    def __init__(
        self,
        lookup_path: Path,
        *,
        profile: str = "hemato",
        database: MolStatDatabase | None = None,
        now: Callable[[], datetime] = datetime.now,
        report_ids: Mapping[str, str] | None = None,
    ) -> None:
        self.lookup_path = lookup_path
        self.profile = profile
        self.database = database
        self._now = now
        self.report_ids = report_ids

    def process(
        self,
        unit: str,
        raw_files: Sequence[Path],
        output_dir: Path,
    ) -> StatisticsResult:
        merged_dir = output_dir / "merged"
        if self.profile == "lege":
            from ._statistics.patolog_process import process

            if len(raw_files) != 2:
                raise ValueError("Patolograpporten krever inneværende og forrige måned.")
            destination = output_dir / "prosess.csv"
            count = process(raw_files[0].parent, destination)
            return StatisticsResult(
                antall=destination, resultater=destination,
                row_counts={"prosess": count},
                publication_files={"prosess.csv": destination},
            )
        if self.profile in {"flow", "fish", "pre"}:
            if self.report_ids is None:
                raise ValueError("Rapport-ID-er mangler for spesialisert statistikkprofil.")
            from ._statistics import fish_reports, flow_reports, pre_reports

            inputs: dict[str, Path] = {}
            for role, report_id in self.report_ids.items():
                matches = [path for path in raw_files if path.name.partition("__")[0] == report_id]
                if len(matches) != 1:
                    raise ValueError(f"Forventet nøyaktig én rapport for {role}.")
                inputs[role] = _merge_archives(matches[0], merged_dir)
            if self.profile == "flow":
                counts = flow_reports.process(
                    inputs["antall"], inputs["resultater"], output_dir, self.lookup_path
                )
                antall_count, result_count = counts["antall"], counts["resultater"]
            elif self.profile == "fish":
                counts = fish_reports.process(
                    inputs["antall"], inputs["resultater"], output_dir, self.lookup_path
                )
                antall_count, result_count = counts["antall"], counts["resultater"]
            else:
                counts = pre_reports.process(inputs["resultater"], output_dir, self.lookup_path)
                antall_count, result_count = 0, counts["activity_rows"]
            return StatisticsResult(
                antall=output_dir / "antall.csv",
                resultater=output_dir / "resultater.csv",
                row_counts={"antall": antall_count, "resultater": result_count},
            )

        def report(role: str, legacy_marker: str) -> Path:
            if self.report_ids is None:
                return _one_report(raw_files, legacy_marker)
            matches = [path for path in raw_files if path.name.partition("__")[0] == self.report_ids[role]]
            if len(matches) != 1:
                raise ValueError(f"Forventet nøyaktig én rapport for {role}.")
            return matches[0]

        ordered = _merge_archives(report("antall", "ANTALL"), merged_dir)
        answered = _merge_archives(
            report("resultater", "RESULTATER"), merged_dir
        )
        extraction = _merge_archives(
            report("ekstraksjon", "EKSTRAKSJON"), merged_dir
        )
        molstat_ids: Mapping[str, str] | None = None
        if self.database is not None:
            interval_from, interval_to = _archive_interval(raw_files)
            records = _registry_records(ordered, answered, extraction)
            registry = SampleRegistry(self.database)
            registry.import_batch(
                records,
                kind="statistics",
                unit_key=unit,
                date_from=interval_from,
                date_to=interval_to,
                observed_at=self._now(),
                source_fingerprint=_combined_fingerprint(
                    (ordered, answered, extraction)
                ),
            )
            molstat_ids = registry.molstat_ids()
        counts = process_reports(
            ordered,
            answered,
            extraction,
            self.lookup_path,
            output_dir,
            profile=self.profile,
            molstat_ids=molstat_ids,
        )
        return StatisticsResult(
            antall=output_dir / "antall.csv",
            resultater=output_dir / "resultater.csv",
            row_counts=counts,
        )


def _report_archives(current: Path) -> tuple[Path, ...]:
    report_id, separator, _interval = current.name.partition("__")
    if not separator or not report_id:
        raise ValueError(f"Ugyldig arkivnavn: {current.name}")
    paths = tuple(sorted(current.parent.glob(f"{report_id}__*.csv")))
    if not paths:
        raise ValueError(f"Fant ingen arkiver for {report_id}.")
    return paths


def _merge_archives(current: Path, output_dir: Path) -> Path:
    archives = _report_archives(current)
    header, rows = merge_report_csvs(list(archives))
    report_id = current.name.partition("__")[0]
    destination = output_dir / f"{report_id}.csv"
    write_merged_csv(header, rows, destination)
    return destination


def _one_report(raw_files: Sequence[Path], marker: str) -> Path:
    matches = [path for path in raw_files if marker in path.name.upper()]
    if len(matches) != 1:
        raise ValueError(
            f"Forventet nøyaktig én {marker}-rapport, fant {len(matches)}."
        )
    return matches[0]


def _first_value(row: Mapping[str, str], names: Sequence[str]) -> str:
    for name in names:
        value = clean_text(row.get(name))
        if value:
            return value
    return ""


def _registry_records(
    ordered: Path,
    answered: Path,
    extraction: Path,
) -> tuple[RegistryImportItem, ...]:
    records: list[RegistryImportItem] = []
    sources = (
        ("statistics_ordered", ordered, ("ordered",)),
        ("statistics_answered", answered, ("resulted", "approved")),
        (
            "statistics_extraction",
            extraction,
            ("ordered", "resulted", "approved"),
        ),
    )
    event_columns = {
        "ordered": ("Tidspunkt.analysebestilling", "Tidspunkt.opprettet"),
        "resulted": ("Tidspunkt.analyseresultat",),
        "approved": ("Tidspunkt.godkjenning",),
    }
    for source_kind, path, event_types in sources:
        for row in read_lvms_csv(path):
            sample_number = _first_value(row, ("Sample.ID", "SampleID"))
            analysis_code = _first_value(row, ("Analyse",))
            ordered_at = parse_tidspunkt(
                _first_value(
                    row,
                    ("Tidspunkt.analysebestilling", "Tidspunkt.opprettet"),
                )
            )
            if not sample_number or not analysis_code or ordered_at is None:
                continue
            events = tuple(
                OccurrenceEventInput(event_type, event_at)
                for event_type in event_types
                if (
                    event_at := parse_tidspunkt(
                        _first_value(row, event_columns[event_type])
                    )
                )
                is not None
            )
            records.append(
                RegistryImportItem(
                    occurrence=OccurrenceInput(
                        source_system="LVMS",
                        sample_number=sample_number,
                        analysis_code=analysis_code,
                        ordered_at=ordered_at,
                        source_occurrence_id=(
                            _first_value(
                                row,
                                ("WorkItem", "Workitem", "WorkItem.ID"),
                            )
                            or None
                        ),
                        source_kind=source_kind,
                    ),
                    events=events,
                )
            )
    return tuple(records)


def _archive_interval(raw_files: Sequence[Path]) -> tuple[date, date]:
    starts: list[date] = []
    ends: list[date] = []
    for current in raw_files:
        for path in _report_archives(current):
            parts = path.name.split("__")
            if len(parts) < 3:
                continue
            try:
                starts.append(date.fromisoformat(parts[1]))
                ends.append(date.fromisoformat(parts[2].removesuffix(".csv")))
            except ValueError:
                continue
    if not starts or not ends:
        raise ValueError("Kunne ikke lese statistikkperioden fra arkivnavnene.")
    return min(starts), max(ends)


def _combined_fingerprint(paths: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()
