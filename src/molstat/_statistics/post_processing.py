"""Post-fetch processing: merge archived raw exports, run the Python
port of the R statistics logic and write ``Prosessert/*.csv`` for Power BI.

``process_unit`` is called automatically at the end of every fetch
(auto mode and GUI), so the processed files are always fresh.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from molstat._statistics.processing import process_reports

# report_id -> (antall stem, resultater stem, ekstraksjon stem)
REPORT_ROLES: dict[str, tuple[str, str, str]] = {}


@dataclass(frozen=True)
class ProcessOutcome:
    antall_rows: int
    resultater_rows: int
    merged_files: int
    output_dir: Path


def find_report_archives(
    raw_dir: Path,
    report_id: str,
) -> list[Path]:
    """All archived files for one report id (stem prefix match)."""
    return sorted(raw_dir.glob(f"{report_id}__*.csv"))


def process_unit(
    unit_dir: Path,
    lookup_path: Path,
    report_ids: Mapping[str, str],
    *,
    profile: str = "hemato",
) -> ProcessOutcome:
    """Merge + process all reports of one unit.

    ``report_ids`` maps role -> report id, e.g.::

        {"ordered": "PAT-DIT-ANTALL-OU",
         "answered": "PAT-DIT-RESULTATER-OU",
         "extraction": "PAT-DIT-EKSTRAKSJON-OU"}

    ``profile`` selects the processing dialect (see
    :func:`lvms_stat.processing.process_reports`).

    The merged raw file is written next to the archives as
    ``merged/<report_id>.csv``, then fed through the R-port which writes
    ``prosessert/antall.csv`` and ``resultater.csv`` under ``unit_dir``.
    """
    from molstat._statistics.merge_raw import merge_report_csvs, write_merged_csv

    raa_dir = unit_dir / "raa"
    ordered = report_ids["ordered"]
    answered = report_ids["answered"]
    extraction = report_ids.get("extraction", "")

    inputs: dict[str, Path] = {}
    merged_count = 0
    for role, report_id in (
        ("ordered", ordered),
        ("answered", answered),
        ("extraction", extraction),
    ):
        if not report_id:
            continue
        # files live directly under raa/ as STEM__from__to.csv, and may
        # alternatively be nested in raa/<report_id>/
        files = sorted(raa_dir.glob(f"{report_id}__*.csv"))
        if not files:
            nested = raa_dir / report_id
            if nested.is_dir():
                files = sorted(nested.glob("*.csv"))
        if not files:
            continue
        header, rows = merge_report_csvs(files)
        merged_path = unit_dir / "merged" / f"{report_id}.csv"
        write_merged_csv(header, rows, merged_path)
        merged_count += 1
        inputs[role] = merged_path

    output_dir = unit_dir / "prosessert"
    if "ordered" not in inputs or "answered" not in inputs:
        return ProcessOutcome(
            antall_rows=0,
            resultater_rows=0,
            merged_files=merged_count,
            output_dir=output_dir,
        )

    counts = process_reports(
        inputs["ordered"],
        inputs["answered"],
        inputs.get("extraction", inputs["answered"]),
        lookup_path,
        output_dir,
        profile=profile,
    )
    return ProcessOutcome(
        antall_rows=counts["antall"],
        resultater_rows=counts["resultater"],
        merged_files=merged_count,
        output_dir=output_dir,
    )

