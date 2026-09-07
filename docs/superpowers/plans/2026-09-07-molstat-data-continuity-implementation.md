# MolStat Data Continuity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve complete Hemato/Solide history and publish an idempotent, identifier-free hourly Prøveflyt history from SQLite to SharePoint.

**Architecture:** Statistics processing merges every archived file for each report before running the existing validated processor. Backlog processing keeps the sensitive current-state table, adds one aggregate row per enabled analysis group and hourly slot, then rebuilds one deterministic CSV from aggregate history and publishes it through the existing privacy gate.

**Tech Stack:** Python 3.11+, SQLite, stdlib CSV, pytest 8+, existing `SharePointPublisher`

**Spec:** `docs/superpowers/specs/2026-09-07-molstat-powerbi-evolution-design.md`

## Global Constraints

- Raw files, identifiers and SQLite remain on K-sensitiv.
- SharePoint receives only exact allowlisted aggregate columns.
- Statistics history begins at 2024-01-01 and retains the existing two-day overlap.
- Every successful hourly backlog slot contains all enabled groups, including zero rows.
- Failed processing or validation preserves the last valid SharePoint files.
- No patient, sample, WorkItem, result, comment, source path or source fingerprint enters the public CSV.

---

### Task 1: Process statistics from the complete raw archive

**Files:**
- Modify: `src/molstat/statistics.py`
- Test: `tests/statistics/test_processing.py`
- Test: `tests/test_end_to_end.py`

**Interfaces:**
- Consumes: newly archived paths passed to `StatisticsProcessor.process(unit, raw_files, output_dir)`
- Produces: `_report_archives(current: Path) -> tuple[Path, ...]`
- Preserves: `StatisticsProcessor.process(...) -> StatisticsResult`

- [ ] **Step 1: Add a failing archive-discovery test**

```python
def test_report_archives_include_old_and_new_intervals(tmp_path: Path) -> None:
    archive = tmp_path / "raw" / "statistics" / "hemato"
    archive.mkdir(parents=True)
    old = archive / "PAT-DIT-ANTALL-OU__2024-01-01__2026-09-04.csv"
    new = archive / "PAT-DIT-ANTALL-OU__2026-09-05__2026-09-07.csv"
    other = archive / "PAT-DIT-RESULTATER-OU__2026-09-05__2026-09-07.csv"
    for path in (old, new, other):
        path.write_text("A;B\n1;2\n", encoding="cp1252")

    assert _report_archives(new) == (old, new)
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `python -m pytest tests/statistics/test_processing.py::test_report_archives_include_old_and_new_intervals -q`

Expected: import or assertion failure because `_report_archives` does not exist.

- [ ] **Step 3: Implement exact report-ID archive discovery**

```python
def _report_archives(current: Path) -> tuple[Path, ...]:
    report_id, separator, _interval = current.name.partition("__")
    if not separator or not report_id:
        raise ValueError(f"Ugyldig arkivnavn: {current.name}")
    paths = tuple(sorted(current.parent.glob(f"{report_id}__*.csv")))
    if not paths:
        raise ValueError(f"Fant ingen arkiver for {report_id}.")
    return paths
```

- [ ] **Step 4: Add a processor test that captures the merged inputs**

Create old and new `ANTALL`, `RESULTATER` and `EKSTRAKSJON` archives with one duplicate overlap row. Monkeypatch `molstat.statistics.process_reports` with a recorder that reads the three received merged files. Assert that each input contains old and new rows once and that the returned output paths remain `antall.csv` and `resultater.csv`.

- [ ] **Step 5: Change `StatisticsProcessor.process` to merge before processing**

For each newly archived report, call `_report_archives`, then `merge_report_csvs`, and write the result below `output_dir / "merged"`. Pass those three merged paths to `process_reports`. Do not publish or mutate raw archive files.

- [ ] **Step 6: Prove the original regression is fixed end to end**

Extend `tests/test_end_to_end.py` with two statistics runs. The second fetch contains only the overlap window; assert the second published CSV still contains the first run's historical row and contains the overlap row only once.

Run: `python -m pytest tests/statistics/test_processing.py tests/statistics/test_merge_raw.py tests/test_end_to_end.py tests/test_publisher.py -q`

Expected: all pass.

- [ ] **Step 7: Commit the historical merge fix**

```powershell
git add src/molstat/statistics.py tests/statistics/test_processing.py tests/test_end_to_end.py
git commit -m "fix: preserve complete statistics history"
```

---

### Task 2: Add an idempotent aggregate backlog history

**Files:**
- Modify: `src/molstat/database.py`
- Create: `src/molstat/_backlog/history.py`
- Modify: `src/molstat/backlog.py`
- Test: `tests/test_database.py`
- Create: `tests/backlog/test_history.py`
- Modify: `tests/backlog/test_processor.py`

**Interfaces:**
- Produces: `BacklogHistoryRow`
- Produces: `hour_slot(value: datetime) -> datetime`
- Produces: `build_history_rows(config, samples, observed_at, *, invalid_rows, excluded_rows, classifier_version) -> tuple[BacklogHistoryRow, ...]`
- Preserves: `BacklogProcessor.import_snapshot(...) -> CsvImportResult`

- [ ] **Step 1: Add failing schema migration tests**

Update the expected schema version from `1` to `2` and require the table
`backlog_snapshot`. Add a v1 fixture database, call `migrate()`, and assert its
existing rows remain readable after the v2 table is added.

Required table definition:

```sql
CREATE TABLE backlog_snapshot (
    observed_at TEXT NOT NULL,
    unit_key TEXT NOT NULL,
    analysis_code TEXT NOT NULL,
    analysis_label TEXT NOT NULL,
    ready_count INTEGER NOT NULL CHECK (ready_count >= 0),
    awaiting_approval_count INTEGER NOT NULL CHECK (awaiting_approval_count >= 0),
    in_transit_count INTEGER NOT NULL CHECK (in_transit_count >= 0),
    overdue_count INTEGER NOT NULL CHECK (overdue_count >= 0),
    median_ready_hours REAL,
    oldest_ready_hours REAL,
    severity TEXT NOT NULL,
    invalid_rows INTEGER NOT NULL CHECK (invalid_rows >= 0),
    excluded_rows INTEGER NOT NULL CHECK (excluded_rows >= 0),
    source_is_fresh INTEGER NOT NULL CHECK (source_is_fresh IN (0, 1)),
    classifier_version INTEGER NOT NULL,
    source_fingerprint TEXT NOT NULL,
    PRIMARY KEY (observed_at, unit_key, analysis_code, classifier_version)
)
```

- [ ] **Step 2: Run migration tests and confirm RED**

Run: `python -m pytest tests/test_database.py -q`

Expected: schema version/table assertions fail.

- [ ] **Step 3: Implement explicit v1-to-v2 migration**

Keep fresh-database creation and existing-database migration transactional.
Only accept schema versions 1 and 2; reject unknown versions. Never drop or
rewrite `backlog_sample`, `job_run`, `raw_file` or publication history.

- [ ] **Step 4: Add failing aggregate-history tests**

Tests must prove:

```python
assert len(rows) == len(tuple(item for item in config.analyses if item.enabled))
assert {row.analysis_code for row in rows} == {
    item.code for item in config.analyses if item.enabled
}
assert hour_slot(datetime(2026, 9, 7, 11, 42, 19)).isoformat().endswith("11:00:00")
```

Use samples from two groups and assert every other enabled group receives zero
counts and `Severity.EMPTY`. Assert ready, awaiting approval, in transit,
overdue, median and oldest values match the existing dashboard rules.

- [ ] **Step 5: Implement `history.py` by reusing domain rules**

Move or extract the per-analysis aggregation from
`build_dashboard_snapshot` so both the old presentation model and history use
one definition. Normalize the observation time to the local hour while
preserving timezone offset when present. Do not copy SampleID into
`BacklogHistoryRow`.

- [ ] **Step 6: Persist current state and history in one transaction**

In `BacklogProcessor.import_snapshot`, compute `file_fingerprint(csv_path)` and
history rows before opening the transaction. Inside one `BEGIN IMMEDIATE`:

1. replace `backlog_sample`;
2. insert all history rows using `ON CONFLICT DO NOTHING`;
3. commit only after both operations succeed.

Call the injected clock once so every group receives the same `observed_at`.

- [ ] **Step 7: Add idempotence and rollback tests**

Import the same file twice with the same injected hour and assert exactly one
row per group. Force the history insert to fail and assert the previous
`backlog_sample` and snapshot rows remain unchanged.

Run: `python -m pytest tests/test_database.py tests/backlog/test_history.py tests/backlog/test_processor.py tests/backlog/test_dashboard.py -q`

Expected: all pass.

- [ ] **Step 8: Commit the history store**

```powershell
git add src/molstat/database.py src/molstat/backlog.py src/molstat/_backlog/history.py tests/test_database.py tests/backlog/test_history.py tests/backlog/test_processor.py
git commit -m "feat: retain hourly backlog history"
```

---

### Task 3: Export and publish `restansehistorikk.csv`

**Files:**
- Create: `src/molstat/_backlog/export.py`
- Modify: `src/molstat/backlog.py`
- Modify: `src/molstat/system.py`
- Modify: `src/molstat/services.py`
- Test: `tests/backlog/test_export.py`
- Modify: `tests/test_publisher.py`
- Modify: `tests/test_end_to_end.py`

**Interfaces:**
- Produces: `BACKLOG_PUBLIC_COLUMNS: tuple[str, ...]`
- Produces: `export_backlog_history(database: MolStatDatabase, destination: Path) -> int`
- Extends: `MolStatSystem.run_backlog() -> dict[str, int]` with `snapshots` and `published_rows`

- [ ] **Step 1: Add failing deterministic-export tests**

Insert snapshot rows out of order, export, and assert the exact header:

```python
BACKLOG_PUBLIC_COLUMNS = (
    "Observert_tidspunkt",
    "Enhet",
    "Analysegruppe_kode",
    "Analysegruppe",
    "Klar",
    "Mangler_godkjenning",
    "På_vei",
    "Over_frist",
    "Median_klare_timer",
    "Eldste_klare_timer",
    "Alvorlighetsgrad",
    "Ugyldige_rader",
    "Ekskluderte_rader",
    "Kilde_fersk",
    "Klassifikatorversjon",
)
```

Assert semicolon delimiters, UTF-8, stable ordering by timestamp/unit/group,
Norwegian booleans `Ja`/`Nei`, empty cells for absent median/oldest values and
no internal fingerprint column.

- [ ] **Step 2: Run export tests and confirm RED**

Run: `python -m pytest tests/backlog/test_export.py -q`

Expected: module import failure.

- [ ] **Step 3: Implement atomic local export**

Query only aggregate columns from `backlog_snapshot`. Write to a temporary
file in `destination.parent`, flush and `os.fsync`, then `os.replace` the
destination. Return the number of exported rows. Delete the temporary file in
`finally` after failures.

- [ ] **Step 4: Configure an exact Prøveflyt publication policy**

In `services.py`, create a `SharePointPublisher` whose only allowed file is
`restansehistorikk.csv` and whose columns are exactly
`BACKLOG_PUBLIC_COLUMNS`. Destination is
`settings.sharepoint_root / "Prøveflyt"`.

- [ ] **Step 5: Publish after successful backlog import**

After `import_snapshot`, export to a unique work directory under
`work/processing`, validate it through `SharePointPublisher`, and publish it.
Do not publish when import, snapshot insertion, export or validation fails.

- [ ] **Step 6: Add privacy and failure-preservation tests**

Assert the public file contains no header matching `SampleID`, `PID`,
`WorkItem`, result, comment, path or fingerprint. Seed an older valid
SharePoint file, force the new export validation to fail, and assert the older
file remains byte-for-byte unchanged.

- [ ] **Step 7: Add an end-to-end two-hour test**

Run backlog at 10:00 and 11:00 with different aggregate counts. Assert the
second published file contains both hours and every configured group for each
hour. Assert the database retains current sensitive state only for the second
run while aggregate history retains both hours.

Run: `python -m pytest tests/backlog tests/test_publisher.py tests/test_end_to_end.py tests/test_privacy_boundary.py -q`

Expected: all pass.

- [ ] **Step 8: Commit Prøveflyt publishing**

```powershell
git add src/molstat/_backlog/export.py src/molstat/backlog.py src/molstat/system.py src/molstat/services.py tests/backlog/test_export.py tests/test_publisher.py tests/test_end_to_end.py
git commit -m "feat: publish aggregate backlog history"
```

---

### Task 4: Data-continuity checkpoint

**Files:**
- Modify only if verification exposes a defect in Tasks 1–3.

**Interfaces:**
- Produces the verified data contracts consumed by the later Power BI/UI plan.

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest -q`

Expected: all tests pass with no skipped regression tests added by this plan.

- [ ] **Step 2: Run a synthetic publication rehearsal**

Use temporary sensitive/sharepoint roots and synthetic identifiers. Execute
two statistics intervals and two backlog hours. Verify:

- published statistics include the oldest and newest interval;
- overlap rows occur once;
- `Prøveflyt/restansehistorikk.csv` contains two hourly slots;
- its header equals `BACKLOG_PUBLIC_COLUMNS`;
- scanning public files for the synthetic identifiers returns no matches.

- [ ] **Step 3: Inspect the repository diff**

Run: `git diff --check HEAD~3..HEAD` and `git status --short`.

Expected: no whitespace errors and no uncommitted generated data.

- [ ] **Step 4: Record the checkpoint**

Add the passing commands and row-count summary to the implementation handoff;
do not add production paths, identifiers or raw source rows to Git.
