"""Merge archived raw report exports into one deduplicated dataset.

The manifest archives one file per run, so a full history for a report
lives as ``STEM__from__to.csv`` files. This module concatenates every
file for a report and drops duplicate rows on the documented key
(Sample ID + Analyse + all Tidspunkt columns), which makes the 3-day
overlap in incremental fetches harmless.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

RAW_ENCODING = "cp1252"
DELIMITER = ";"


def _row_key(header: list[str], row: list[str]) -> str:
    """Stable key over the whole row (order-independent column names)."""
    pairs = sorted(zip(header, row))
    payload = repr(pairs).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def merge_report_csvs(
    paths: list[Path],
) -> tuple[list[str], list[dict[str, str]]]:
    """Concatenate CSVs, dropping exact duplicate rows.

    Returns ``(header, rows)`` using the header of the newest file
    (last in the list), falling back to earlier headers when a column
    is missing in an older file.
    """
    if not paths:
        return [], []
    seen: set[str] = set()
    merged: list[dict[str, str]] = []
    final_header: list[str] = []
    for path in paths:
        with open(path, encoding=RAW_ENCODING, newline="") as handle:
            reader = csv.reader(handle, delimiter=DELIMITER)
            try:
                header = next(reader)
            except StopIteration:
                continue
            if not final_header:
                final_header = header
            elif len(header) > len(final_header):
                # extend older rows implicitly; keep the widest header
                extra = [c for c in header if c not in final_header]
                final_header = final_header + extra
            index_of = {name: i for i, name in enumerate(header)}
            for raw in reader:
                if not any(cell.strip() for cell in raw):
                    continue
                key = _row_key(header, [
                    raw[index_of[name]] if name in index_of else ""
                    for name in header
                ])
                if key in seen:
                    continue
                seen.add(key)
                merged.append(
                    {
                        name: (
                            raw[index_of[name]]
                            if name in index_of and index_of[name] < len(raw)
                            else ""
                        )
                        for name in final_header
                    }
                )
    return final_header, merged


def write_merged_csv(
    header: list[str],
    rows: list[dict[str, str]],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=RAW_ENCODING, newline="") as handle:
        writer = csv.writer(handle, delimiter=DELIMITER)
        writer.writerow(header)
        for row in rows:
            writer.writerow([row.get(name, "") for name in header])

