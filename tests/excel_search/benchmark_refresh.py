"""Manual synthetic Excel refresh benchmark (no production files).

Run from the checkout root:
    python tests/excel_search/benchmark_refresh.py --samples 10000 --repeats 3
To compare a saved previous excel_search.py source:
    python tests/excel_search/benchmark_refresh.py --baseline-source C:/temp/excel_search.py
All database/workbook files are synthetic and removed after the run.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from molstat.database import MolStatDatabase
from molstat import excel_search


def synthetic_database(path: Path, sample_count: int) -> MolStatDatabase:
    database = MolStatDatabase(path)
    database.migrate()
    when = "2026-10-28T12:00:00"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """INSERT INTO import_run(id, kind, unit_key, date_from, date_to,
               started_at, finished_at, status) VALUES
               (1, 'statistics', 'hemato', '2026-10-26', '2026-10-28', ?, ?, 'completed')""",
            (when, when),
        )
        connection.executemany(
            "INSERT INTO sample VALUES (?, ?, ?, ?)",
            ((i, f"MS-{i:08}", when, when) for i in range(1, sample_count + 1)),
        )
        connection.executemany(
            "INSERT INTO sample_identifier VALUES (?, ?, ?, ?, ?, ?)",
            ((i, i, "LVMS", "sample_number", f"{i:020}", f"{i:020}")
             for i in range(1, sample_count + 1)),
        )
        connection.executemany(
            "INSERT INTO analysis_occurrence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ((i, (i - 1) // 3 + 1, f"KEY-{i}", "LVMS", f"WORK-{i}",
              f"ANALYSIS-{i % 10}", when, 0, "resolved", when, when)
             for i in range(1, sample_count * 3 + 1)),
        )
        connection.executemany(
            """INSERT INTO analysis_event(occurrence_id, event_type, event_at,
               source_kind, import_run_id) VALUES (?, ?, ?, 'statistics_answered', 1)""",
            ((i, event, when) for i in range(1, sample_count * 3 + 1)
             for event in ("resulted", "approved")),
        )
        connection.executemany(
            "INSERT INTO source_observation VALUES (?, ?, ?, ?, 1)",
            ((i, kind, when, when) for i in range(1, sample_count * 3 + 1)
             for kind in ("statistics_answered", "statistics_ordered")),
        )
        connection.executemany(
            """INSERT INTO backlog_current(occurrence_id, import_run_id, unit_key,
               analysis_group, workflow_stage, updated_at)
               VALUES (?, 1, 'hemato', 'TEST', 'ready', ?)""",
            ((i, when) for i in range(1, sample_count * 3 + 1, 7)),
        )
    return database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=10000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--baseline-source", type=Path)
    args = parser.parse_args()
    if args.samples < 1 or args.repeats < 1:
        parser.error("samples and repeats must be positive")
    modules = {"current": excel_search}
    if args.baseline_source:
        name = "molstat._excel_benchmark_baseline"
        spec = importlib.util.spec_from_file_location(name, args.baseline_source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        modules = {"baseline": module, **modules}
    timings = {name: [] for name in modules}
    with tempfile.TemporaryDirectory(prefix="molstat-excel-benchmark-") as directory:
        root = Path(directory)
        database = synthetic_database(root / "synthetic.sqlite3", args.samples)
        # Each measured read opens a new read-only connection. Alternate writer
        # order to reduce the effect of warm filesystem caches and load drift.
        for repeat in range(args.repeats):
            order = list(modules.items())
            if repeat % 2:
                order.reverse()
            for name, module in order:
                started = time.perf_counter()
                snapshot = module.read_excel_snapshot(database, generated_at=datetime(2026, 10, 29))
                read_seconds = time.perf_counter() - started
                assert len(snapshot.samples) == args.samples
                assert len(snapshot.analyses) == args.samples * 3
                destination = root / f"{name}.xlsx"
                started = time.perf_counter()
                module.generate_search_workbook(snapshot, destination)
                generate_seconds = time.perf_counter() - started
                started = time.perf_counter()
                module.validate_search_workbook(destination)
                validate_seconds = time.perf_counter() - started
                result = dict(read=read_seconds, generate=generate_seconds,
                              validate=validate_seconds, bytes=destination.stat().st_size)
                timings[name].append(result)
                print(json.dumps(dict(repeat=repeat + 1, version=name, **result)), flush=True)
    medians = {name: {phase: statistics.median(row[phase] for row in rows)
                      for phase in ("read", "generate", "validate", "bytes")}
               for name, rows in timings.items()}
    print(json.dumps(dict(samples=args.samples, analyses=args.samples * 3, medians=medians), indent=2))


if __name__ == "__main__":
    main()
