"""Reproduce the historical Hemato + small incremental processing profile.

Run from the checkout root:
    python tests/statistics/profile_incremental.py --history 10000 --daily 90

All records are synthetic. Each role has one historical archive and one
three-day incremental archive. The timed operation retains all CSV history.
Temporary fixtures are removed unless --keep-output is supplied.
"""
from __future__ import annotations

import argparse
import cProfile
import csv
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import pstats
import sys
import tempfile
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))

from molstat.database import MolStatDatabase
from molstat.statistics import StatisticsProcessor


def write_reports(root: Path, start: str, end: str, prefix: str, count: int) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    for role in ('ANTALL', 'RESULTATER', 'EKSTRAKSJON'):
        path = root / f'PAT-DIT-{role}-OU__{start}__{end}.csv'
        with path.open('w', encoding='cp1252', newline='') as stream:
            writer = csv.writer(stream, delimiter=';')
            writer.writerow(['Sample ID', 'WorkItem', 'Analyse', 'Materiale',
                             'Tidspunkt opprettet', 'Tidspunkt analysebestilling',
                             'Tidspunkt analyseresultat', 'Tidspunkt godkjenning'])
            for index in range(count):
                sample = f'{prefix}-{index:06}'
                extraction = role == 'EKSTRAKSJON'
                writer.writerow([sample, f'{sample}-EXT' if extraction else f'{sample}-CALR',
                                 'EKSTRAAPKOL-H-OU' if extraction else 'CALR-OU', 'Blood',
                                 '01.09.2026 07:00', '01.09.2026 08:00',
                                 '01.09.2026 09:00', '01.09.2026 10:00'])
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', type=int, default=10000)
    parser.add_argument('--daily', type=int, default=90)
    parser.add_argument('--no-profile', action='store_true')
    parser.add_argument('--keep-output', action='store_true',
                        help='Retain synthetic archives, database and CSVs for inspection.')
    args = parser.parse_args()
    if args.history < 0 or args.daily < 0:
        parser.error('Sample counts must be non-negative.')
    temporary = None if args.keep_output else tempfile.TemporaryDirectory(prefix='molstat-statistics-perf-')
    root = Path(tempfile.mkdtemp(prefix='molstat-statistics-perf-') if temporary is None else temporary.name)
    database = MolStatDatabase(root / 'registry.sqlite3')
    database.migrate()
    processor = StatisticsProcessor(analysis_codes={'CALR-OU'}, database=database,
                                    now=lambda: datetime(2026, 10, 1, 12))
    history = write_reports(root / 'archive', '2024-01-01', '2026-09-01', 'H', args.history)
    processor.process('hemato', history, root / 'first')
    daily = write_reports(root / 'archive', '2026-09-02', '2026-09-04', 'N', args.daily)
    profile = cProfile.Profile()
    start = perf_counter()
    if not args.no_profile:
        profile.enable()
    result = processor.process('hemato', daily, root / 'daily')
    profile.disable()
    elapsed = perf_counter() - start
    with database.read_connection() as connection:
        imports = [row[0] for row in connection.execute('SELECT row_count FROM import_run ORDER BY id')]
        tables = {name: connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
                  for name in ('sample', 'analysis_occurrence', 'analysis_event', 'source_observation')}
    report = {'seconds': elapsed, 'historical_samples': args.history,
                      'daily_samples': args.daily, 'counts': dict(result.row_counts),
                      'import_rows': imports, 'tables': tables,
                      'root': str(root) if args.keep_output else None,
                      'csv_sha256': {name: hashlib.sha256((root / 'daily' / name).read_bytes()).hexdigest()
                                     for name in ('antall.csv', 'resultater.csv')}}
    if temporary is not None:
        temporary.cleanup()
    print(json.dumps(report))
    if not args.no_profile:
        output = io.StringIO()
        pstats.Stats(profile, stream=output).strip_dirs().sort_stats('cumulative').print_stats(20)
        print(output.getvalue())


if __name__ == '__main__':
    main()
