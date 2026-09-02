# MolStat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one installable MolStat system that replaces LVMS-STAT and MolPat Puls while keeping sensitive data on K-sensitiv and publishing only identifier-free outputs.

**Architecture:** One `molstat` Python package owns configuration, scheduling, Edge/CDP fetching, SQLite storage, processing and publication. A PyQt6 control center operates the system; a read-only local web server is the only backlog board. Statistics and backlog share infrastructure but use isolated job transactions so either can fail without damaging the other's last valid result.

**Tech Stack:** Python 3.11+, PyQt6 6.7–6.x, websocket-client 1.8–1.x, SQLite, stdlib HTTP server, pytest 8+, pytest-qt 4.4+

**Spec:** `docs/superpowers/specs/2026-09-02-molstat-design.md`

## Global Constraints

- App, package and repository name: `MolStat` / `molstat`.
- Raw data, SQLite, manifests and operational logs stay on K-sensitiv.
- SharePoint receives only allowlisted, identifier-free processed files.
- Statistics runs daily at 05:00; backlog runs hourly 06:00–18:00 inclusive.
- One active writer is allowed; another PC may take over only after the lease is free or expired.
- Raw CSV files are immutable and never overwritten.
- The board never exposes SampleID, PID, WorkItem, raw result text, comments or paths.
- Existing LVMS-STAT gold-standard output and MolPat Puls classification behavior must remain green.

## File Map

- `src/molstat/config.py`: typed settings, path validation and local settings persistence.
- `src/molstat/database.py`: schema migration, transactions and single-writer lease.
- `src/molstat/archive.py`: immutable raw-file archive.
- `src/molstat/lvms/`: the single Edge/CDP/report runtime ported from the two source repos.
- `src/molstat/statistics.py`: validated LVMS-STAT merge and statistics processing.
- `src/molstat/backlog.py`: MolPat Puls ingestion, classification and aggregation.
- `src/molstat/publisher.py`: privacy gate and atomic SharePoint publication.
- `src/molstat/orchestrator.py`: serialized jobs and failure isolation.
- `src/molstat/schedule.py`: due-job calculation and Windows task definitions.
- `src/molstat/web.py` and `src/molstat/web_assets/`: read-only backlog board.
- `src/molstat/ui/`: PyQt6 control center, settings and diagnostics.
- `src/molstat/cli.py`: `gui`, `run`, `serve`, `check-config` and `auto` entry points.

---

### Task 1: Bootstrap and safe configuration

**Files:**
- Create: `pyproject.toml`, `src/molstat/__init__.py`, `src/molstat/config.py`, `src/molstat/cli.py`
- Create: `tests/test_config.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `MolStatSettings.load(path: Path) -> MolStatSettings`
- Produces: `MolStatSettings.validate() -> tuple[str, ...]`
- Produces: `main(argv: Sequence[str] | None = None) -> int`

- [ ] **Step 1: Write failing configuration tests**

```python
def test_settings_require_distinct_sensitive_and_sharepoint_roots(tmp_path):
    settings = MolStatSettings(sensitive_root=tmp_path, sharepoint_root=tmp_path)
    assert settings.validate() == ("K-sensitiv og SharePoint må være ulike mapper.",)

def test_missing_sharepoint_is_allowed_until_publication(tmp_path):
    settings = MolStatSettings(sensitive_root=tmp_path, sharepoint_root=None)
    assert settings.validate() == ()
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_config.py -q`  
Expected: FAIL because `molstat.config` does not exist.

- [ ] **Step 3: Add package metadata and the immutable settings dataclass**

```python
@dataclass(frozen=True, slots=True)
class MolStatSettings:
    sensitive_root: Path
    sharepoint_root: Path | None = None
    statistics_hour: int = 5
    backlog_first_hour: int = 6
    backlog_last_hour: int = 18

    def validate(self) -> tuple[str, ...]:
        if self.sharepoint_root and self.sensitive_root.resolve() == self.sharepoint_root.resolve():
            return ("K-sensitiv og SharePoint må være ulike mapper.",)
        return ()
```

- [ ] **Step 4: Add `check-config` CLI and run tests**

Run: `python -m pytest tests/test_config.py tests/test_cli.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml src/molstat tests/test_config.py tests/test_cli.py
git commit -m "feat: bootstrap MolStat configuration"
```

### Task 2: Database, migration and writer lease

**Files:**
- Create: `src/molstat/database.py`
- Create: `tests/test_database.py`

**Interfaces:**
- Produces: `MolStatDatabase(path: Path)`
- Produces: `MolStatDatabase.migrate() -> None`
- Produces: `MolStatDatabase.writer_lease(owner: str, ttl: timedelta) -> ContextManager[None]`
- Produces tables: `schema_info`, `writer_lease`, `job_run`, `raw_file`, `statistics_publication`, `backlog_sample`

- [ ] **Step 1: Write lease and migration tests**

```python
def test_second_writer_is_rejected(tmp_path):
    db = MolStatDatabase(tmp_path / "molstat.sqlite3")
    db.migrate()
    with db.writer_lease("pc-a", timedelta(minutes=30)):
        with pytest.raises(WriterLeaseBusy):
            with db.writer_lease("pc-b", timedelta(minutes=30)):
                pass

def test_database_migration_is_idempotent(tmp_path):
    db = MolStatDatabase(tmp_path / "molstat.sqlite3")
    db.migrate(); db.migrate()
    assert db.schema_version() == 1
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_database.py -q`  
Expected: FAIL because the database API is missing.

- [ ] **Step 3: Implement transactional migration and lease compare-and-set**

Use `BEGIN IMMEDIATE`, UTC expiry timestamps and an owner check on release. Do not use WAL on the shared K-drive; use `journal_mode=DELETE`, `synchronous=FULL`, a 30-second busy timeout and explicit short transactions.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_database.py -q`  
Expected: PASS, including forced expiry and owner-safe release tests.

- [ ] **Step 5: Commit**

```powershell
git add src/molstat/database.py tests/test_database.py
git commit -m "feat: add safe shared database lease"
```

### Task 3: One LVMS runtime and immutable archive

**Files:**
- Create: `src/molstat/archive.py`
- Create: `src/molstat/lvms/{cdp,edge,dom,batch,report}.py`
- Create: `tests/lvms/`, `tests/test_archive.py`
- Source reference: `C:/Users/molpa/Documents/LVMS-STAT` `main:src/lvms_stat/`
- Source reference: `C:/Users/molpa/Documents/MolPat-Pulse` `main:src/molpat_puls/lvms_runtime/`

**Interfaces:**
- Produces: `ReportRequest(kind: Literal["statistics", "backlog"], unit: str, date_from: date, date_to: date)`
- Produces: `LvmsClient.fetch(request: ReportRequest, download_dir: Path) -> Path`
- Produces: `RawArchive.store(source: Path, request: ReportRequest) -> ArchivedRawFile`

- [ ] **Step 1: Port the frozen runtime tests before production code**

Copy the behavior tests for batch controls, form, navigation, runner, browser session, CDP, downloads, Edge and report jobs into `tests/lvms/`; change imports only from the old package names to `molstat.lvms`.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/lvms tests/test_archive.py -q`  
Expected: collection FAIL because `molstat.lvms` is absent.

- [ ] **Step 3: Port one canonical implementation**

Use LVMS-STAT `main` as the canonical runtime and bring across only behavior required by the ported tests. Replace package-specific paths/config objects with `ReportRequest` and dependency injection. Keep exactly one copy of each CDP/Edge class.

- [ ] **Step 4: Implement collision-safe archive naming**

```text
<sensitive_root>/raw/<kind>/<unit>/<report>__YYYY-MM-DD__YYYY-MM-DD.csv
<sensitive_root>/raw/<kind>/<unit>/<report>__YYYY-MM-DD__YYYY-MM-DD__r2.csv
```

Store by copy-to-temporary, flush, `os.fsync`, atomic rename and SHA-256 registration. Never replace an existing archive file.

- [ ] **Step 5: Verify GREEN and commit**

Run: `python -m pytest tests/lvms tests/test_archive.py -q`  
Expected: PASS.

```powershell
git add src/molstat/lvms src/molstat/archive.py tests/lvms tests/test_archive.py
git commit -m "feat: unify LVMS fetching and raw archive"
```

### Task 4: Validated statistics flow

**Files:**
- Create: `src/molstat/statistics.py`
- Create: `tests/statistics/`
- Source reference: `C:/Users/molpa/Documents/LVMS-STAT` `main:src/lvms_stat/{merge_raw,processing,post_processing,incremental}.py`

**Interfaces:**
- Produces: `StatisticsProcessor.process(unit: str, raw_files: Sequence[Path], output_dir: Path) -> StatisticsResult`
- Produces: `StatisticsResult(antall: Path, resultater: Path, row_counts: Mapping[str, int])`

- [ ] **Step 1: Port gold-standard, merge, incremental and cross-unit tests**

Retain the fixture data and expected column order. Change imports to `molstat.statistics`; keep every documented R nondeterminism allowance unchanged.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/statistics -q`  
Expected: collection FAIL because `StatisticsProcessor` is absent.

- [ ] **Step 3: Port the minimum validated pipeline behind `StatisticsProcessor`**

Keep hemato and solide configuration-driven, preserve full-row deduplication and write candidate outputs only beneath a run-specific temporary directory.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest tests/statistics -q`  
Expected: PASS with cell-for-cell gold-standard compatibility.

```powershell
git add src/molstat/statistics.py tests/statistics
git commit -m "feat: port validated statistics processing"
```

### Task 5: Backlog ingestion and safe snapshot

**Files:**
- Create: `src/molstat/backlog.py`
- Create: `tests/backlog/`
- Source reference: `C:/Users/molpa/Documents/MolPat-Pulse` `main:src/molpat_puls/{domain,ingestion,dashboard,store}.py`

**Interfaces:**
- Produces: `BacklogProcessor.import_snapshot(csv_path: Path, db: MolStatDatabase) -> ImportResult`
- Produces: `BacklogProcessor.public_snapshot(db: MolStatDatabase, now: datetime) -> dict[str, object]`

- [ ] **Step 1: Port classification, reclassification, ingestion and dashboard tests**

Add an assertion that recursively scans snapshot keys and values for `SampleID`, `PID`, `WorkItem`, raw result strings and filesystem paths.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/backlog -q`  
Expected: collection FAIL because `molstat.backlog` is absent.

- [ ] **Step 3: Port classification and aggregation into the shared database**

Persist only the local deduplication key, configured analysis group, ordered/arrived timestamps and derived workflow stage. Build the public snapshot from aggregate queries and the configured analysis catalog.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest tests/backlog -q`  
Expected: PASS with no identifiers in the public snapshot.

```powershell
git add src/molstat/backlog.py tests/backlog
git commit -m "feat: integrate backlog processing"
```

### Task 6: Privacy gate and atomic SharePoint publication

**Files:**
- Create: `src/molstat/publisher.py`
- Create: `tests/test_publisher.py`

**Interfaces:**
- Produces: `PublicationPolicy(allowed_columns: Mapping[str, frozenset[str]], forbidden_patterns: tuple[Pattern[str], ...])`
- Produces: `SharePointPublisher.publish(files: Mapping[str, Path], destination: Path) -> PublicationResult`

- [ ] **Step 1: Write privacy and interrupted-write tests**

```python
def test_publisher_rejects_patient_identifier_column(tmp_path):
    source = write_csv(tmp_path / "bad.csv", ["Analyse", "Pasientnummer"], [["A", "123"]])
    with pytest.raises(PrivacyViolation):
        publisher.publish({"resultater.csv": source}, tmp_path / "sharepoint")

def test_failed_validation_preserves_last_publication(tmp_path):
    destination = tmp_path / "sharepoint"; destination.mkdir()
    (destination / "resultater.csv").write_text("old", encoding="utf-8")
    with pytest.raises(PrivacyViolation):
        publisher.publish({"resultater.csv": bad_source}, destination)
    assert (destination / "resultater.csv").read_text(encoding="utf-8") == "old"
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_publisher.py -q`  
Expected: FAIL because publisher types are missing.

- [ ] **Step 3: Implement allowlist validation and atomic replacement**

Parse headers before copying, require the exact policy allowlist, scan normalized headings for forbidden patterns, copy to a destination-local temporary file, flush/fsync and replace only after every candidate passes.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest tests/test_publisher.py -q`  
Expected: PASS.

```powershell
git add src/molstat/publisher.py tests/test_publisher.py
git commit -m "feat: add privacy-safe SharePoint publishing"
```

### Task 7: Unified orchestrator and schedule

**Files:**
- Create: `src/molstat/orchestrator.py`, `src/molstat/schedule.py`
- Create: `tests/test_orchestrator.py`, `tests/test_schedule.py`

**Interfaces:**
- Produces: `JobKind = Literal["statistics", "backlog"]`
- Produces: `MolStatOrchestrator.run(kind: JobKind, trigger: str) -> JobResult`
- Produces: `due_jobs(now: datetime, last_success: Mapping[JobKind, datetime | None]) -> tuple[JobKind, ...]`

- [ ] **Step 1: Write schedule and failure-isolation tests**

```python
@pytest.mark.parametrize("hour", range(6, 19))
def test_backlog_is_due_each_inclusive_operating_hour(hour):
    assert "backlog" in due_jobs(datetime(2026, 9, 2, hour, 0), {"backlog": None, "statistics": None})

def test_statistics_failure_does_not_replace_last_backlog_snapshot(system):
    before = system.read_public_snapshot()
    system.statistics_processor.fail_next_run()
    assert system.orchestrator.run("statistics", "manual").status == "failed"
    assert system.read_public_snapshot() == before
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_schedule.py tests/test_orchestrator.py -q`  
Expected: FAIL because schedule/orchestrator APIs are missing.

- [ ] **Step 3: Implement serialized, transaction-bounded job execution**

Acquire the database lease, fetch and archive first, process into a run directory, validate/publish, then mark success. Record sanitized failure details and leave prior successful outputs untouched.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest tests/test_schedule.py tests/test_orchestrator.py -q`  
Expected: PASS for 05:00, 06:00–18:00 inclusive, overlap rejection and failure isolation.

```powershell
git add src/molstat/orchestrator.py src/molstat/schedule.py tests/test_orchestrator.py tests/test_schedule.py
git commit -m "feat: add unified MolStat job orchestration"
```

### Task 8: Browser-only backlog board

**Files:**
- Create: `src/molstat/web.py`, `src/molstat/web_assets/{board.html,board.css,board.js}`
- Create: `tests/test_web.py`, `tests/test_web_assets.py`

**Interfaces:**
- Produces: `create_board_server(snapshot_provider, host="127.0.0.1", port=8765) -> HTTPServer`
- Routes: `GET /board`, `GET /api/v1/snapshot`, `GET /healthz`

- [ ] **Step 1: Port the MolPat Puls route/security/assets tests**

Require GET/HEAD only, no CORS, no-store responses, strict CSP and exact allowlisted assets. Assert that `/api/v1/snapshot` contains only the public snapshot contract.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_web.py tests/test_web_assets.py -q`  
Expected: FAIL because the server and assets are absent.

- [ ] **Step 3: Port and rebrand the board**

Use `MolStat` branding, preserve stale/offline feedback, 1366×768 and 1920×1080 no-horizontal-scroll behavior, and keep the server local by default.

- [ ] **Step 4: Verify GREEN and commit**

Run: `python -m pytest tests/test_web.py tests/test_web_assets.py -q`  
Expected: PASS.

```powershell
git add src/molstat/web.py src/molstat/web_assets tests/test_web.py tests/test_web_assets.py
git commit -m "feat: add MolStat browser board"
```

### Task 9: PyQt6 control center and Windows automation

**Files:**
- Create: `design-system/molstat/MASTER.md`
- Create: `src/molstat/ui/{app,theme,dashboard,settings,diagnostics}.py`
- Create: `src/molstat/windows_automation.py`
- Create: `tests/ui/`, `tests/test_windows_automation.py`

**Interfaces:**
- Produces: `create_application(settings_path: Path) -> QApplication`
- Produces: `MainWindow(orchestrator, settings_store, board_controller) -> QMainWindow`
- Produces: `WindowsAutomation.install(statistics_hour=5, backlog_hours=range(6, 19)) -> InstallResult`

- [ ] **Step 1: Generate and persist the UI system**

Run:

```powershell
py -3 'C:\Users\molpa\.codex\skills\ui-ux-pro-max\scripts\search.py' 'clinical laboratory operations statistics desktop dashboard calm accessible dense' --design-system --persist -p 'MolStat' --output-dir 'C:\Users\molpa\Documents\MolStat' --variance 4 --motion 2 --density 7
```

Read `design-system/molstat/MASTER.md` and use its tokens unless they conflict with the design spec's accessibility requirements.

- [ ] **Step 2: Write failing UI and task-definition tests**

Test keyboard navigation, accessible names, text status labels, disabled run controls while a job is active, settings validation, sanitized diagnostics and the exact 05:00 plus 06:00–18:00 task triggers.

- [ ] **Step 3: Verify RED**

Run: `python -m pytest tests/ui tests/test_windows_automation.py -q`  
Expected: FAIL because UI/automation APIs are absent.

- [ ] **Step 4: Implement the control center**

Build status overview, manual run action, settings, diagnostics and open-board action. Keep all long-running work off the Qt event loop and marshal results back with Qt signals. Use text plus icon/color for every state.

- [ ] **Step 5: Verify GREEN and commit**

Run: `python -m pytest tests/ui tests/test_windows_automation.py -q`  
Expected: PASS.

```powershell
git add design-system src/molstat/ui src/molstat/windows_automation.py tests/ui tests/test_windows_automation.py
git commit -m "feat: build MolStat control center"
```

### Task 10: Packaging, migration and end-to-end verification

**Files:**
- Create: `README.md`, `JOBBS-PC.md`, `MOLSTAT_INSTALLER.cmd`, `MOLSTAT_START.cmd`
- Create: `tests/test_end_to_end.py`, `tests/test_privacy_boundary.py`
- Modify: `src/molstat/cli.py`, `pyproject.toml`

**Interfaces:**
- CLI: `molstat gui`, `molstat run statistics`, `molstat run backlog`, `molstat serve`, `molstat auto`, `molstat check-config`

- [ ] **Step 1: Write a synthetic end-to-end test**

Use only synthetic identifiers. Feed one statistics CSV and one backlog CSV through archive, database, processing, SharePoint publication and board snapshot. Assert raw files exist only under the sensitive root, published headers match the allowlist and no synthetic identifier appears in SharePoint, JSON, HTML or logs.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_end_to_end.py tests/test_privacy_boundary.py -q`  
Expected: FAIL until CLI wiring and packaging are complete.

- [ ] **Step 3: Add entry points, offline installation and migration runbook**

Document side-by-side validation: install MolStat without removing old apps, configure K/SharePoint in settings, run manual statistics/backlog, compare outputs, enable scheduling, observe one full day, then disable old scheduled tasks. Do not delete old raw data or databases.

- [ ] **Step 4: Run complete verification**

Run: `python -m pytest -q`  
Expected: all MolStat tests pass.

Run: `python -m molstat check-config`  
Expected: exit 0 with synthetic/local test settings and no secrets printed.

- [ ] **Step 5: Commit**

```powershell
git add README.md JOBBS-PC.md MOLSTAT_INSTALLER.cmd MOLSTAT_START.cmd pyproject.toml src/molstat/cli.py tests/test_end_to_end.py tests/test_privacy_boundary.py
git commit -m "feat: complete MolStat integrated system"
```

## Final Review Gate

- Run `python -m pytest -q` from a clean checkout.
- Confirm `git status --short` is empty.
- Compare generated statistics output with the LVMS-STAT gold standard.
- Recursively scan SharePoint candidates, board JSON, HTML and logs for fixture identifiers and forbidden headings.
- Render and inspect the PyQt6 control center at 100%, 125% and 150% Windows scaling.
- Inspect the browser board at 1366×768 and 1920×1080.
- Perform the first production run manually before enabling Windows scheduling.
