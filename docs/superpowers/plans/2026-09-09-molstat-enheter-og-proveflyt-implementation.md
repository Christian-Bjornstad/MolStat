# MolStat Units and Prøveflyt Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unit-centred MolStat control app with safe portable settings, Hemato/Solide run targets, and a UTF-8 Hemato Prøveflyt export that includes verbatim analysis results and external comments.

**Architecture:** Replace the flat job-module registry with explicit unit definitions whose capabilities drive fetching, processing, publication, validation, and UI construction. Keep permanent detail history in schema-versioned SQLite and atomically rebuild one public CSV per unit. Preserve the existing `statistics` and `backlog` CLI targets as compatibility aliases while adding `all`, `hemato`, and `solide` targets for the GUI.

**Tech Stack:** Python 3.11+, PyQt6, SQLite, pytest/pytest-qt, stdlib CSV/JSON/file APIs, existing LVMS CDP automation.

**Spec:** `docs/superpowers/specs/2026-09-09-molstat-enheter-og-proveflyt-design.md`

## Global Constraints

- `Analyseresultat` and `Ekstern.analysekommentar` are copied verbatim after removing the LVMS `=T("...")` wrapper.
- `Rapportgruppe` is absent from the public Prøveflyt contract.
- Public Prøveflyt CSV uses semicolon delimiters, CRLF-compatible records, and UTF-8 with BOM.
- `SampleID`, `PID`, `Workitemgruppe`/`WorkItem`, source paths, and source fingerprints never cross into the public detail table or CSV.
- Hemato publishes `Prøveflyt/restansehistorikk_hemato.csv`; existing statistics files stay under `hemato/` and `solide/`.
- Settings transfer files are versioned UTF-8 JSON and never contain credentials, cookies, sessions, Edge profile data, dynamic CDP ports, databases, or raw data.
- Import validates the complete document before mutating current settings; invalid imports are atomic no-ops.
- Lege, Flow, Pre, and Hist are visible disabled placeholders marked `Kommer`.
- A failed unit does not stop the remaining independent units in `Kjør alt`.
- UI text, focus indicators, and status retain the tested WCAG contrast and 44 px minimum control height.
- No Power BI report or template work is included.

---

## File Structure

- `src/molstat/modules.py`: authoritative unit/capability registry and publication contracts.
- `src/molstat/config.py`: settings schema v2, legacy migration, portable import/export serialization, and validation.
- `src/molstat/_backlog/domain.py`: transient backlog row fields, including result and comment.
- `src/molstat/_backlog/ingestion.py`: exact LVMS text extraction.
- `src/molstat/_backlog/history.py`: identifier-free permanent row shape.
- `src/molstat/database.py`: additive schema v4 migration.
- `src/molstat/backlog.py`: transactional persistence of the expanded public detail history.
- `src/molstat/_backlog/export.py`: exact 19-column CSV allowlist and atomic writer.
- `src/molstat/fetching.py`: statistics fetch scoped to one requested unit.
- `src/molstat/system.py`: capability execution and per-unit publication routing.
- `src/molstat/orchestrator.py`: target execution, partial outcomes, leases, and safe diagnostics.
- `src/molstat/services.py`: runtime wiring, legacy CLI aliases, path validation, and settings transfer services.
- `src/molstat/ui/dashboard.py`: responsive unit cards and run actions.
- `src/molstat/ui/settings.py`: global/unit settings sections and transfer controls.
- `src/molstat/ui/app.py`: target workers, selective button locking, settings dialogs, and window icon.
- `src/molstat/ui/theme.py`: styling for unit/coming/status cards using the existing palette.
- `src/molstat/assets/molstat.png`: high-resolution source icon.
- `src/molstat/assets/molstat.ico`: multi-resolution Windows icon.
- `pyproject.toml`: package the two icon assets.
- `README.md`: operator-focused Norwegian project documentation.
- Existing focused tests are extended in place; no parallel replacement test suite is created.

### Task 1: Define the unit and capability registry

**Files:**
- Modify: `src/molstat/modules.py`
- Modify: `tests/test_modules.py`

**Interfaces:**
- Produces: `UnitStatus = Literal["active", "coming"]`
- Produces: `CapabilityDefinition(job_kind, schedule_key, processor_profile, sharepoint_folder, publication_files, status_fields)`
- Produces: `UnitDefinition(key, display_name, status, capabilities)` with `capability(job_kind)`
- Produces: `UnitRegistry.require(key)`, `active(enabled_keys=None)`, and `for_job(job_kind, enabled_keys=None)`
- Produces: `DEFAULT_UNITS`; retain `DEFAULT_MODULES = DEFAULT_UNITS` as a temporary compatibility alias.

- [ ] **Step 1: Replace flat-module expectations with failing unit-registry tests**

```python
def test_default_registry_groups_capabilities_by_unit() -> None:
    assert tuple(unit.key for unit in DEFAULT_UNITS) == (
        "hemato", "solide", "lege", "flow", "pre", "hist"
    )
    hemato = DEFAULT_UNITS.require("hemato")
    assert hemato.status == "active"
    assert tuple(cap.job_kind for cap in hemato.capabilities) == (
        "statistics", "backlog"
    )
    assert hemato.capability("backlog").publication_files == (
        ("restansehistorikk_hemato.csv", frozenset(BACKLOG_PUBLIC_COLUMNS)),
    )


def test_coming_units_have_no_runnable_capabilities() -> None:
    for key in ("lege", "flow", "pre", "hist"):
        unit = DEFAULT_UNITS.require(key)
        assert unit.status == "coming"
        assert unit.capabilities == ()
```

- [ ] **Step 2: Run the focused registry tests and confirm the old model fails**

Run: `python -m pytest tests/test_modules.py -q`

Expected: FAIL because `DEFAULT_UNITS`, `UnitDefinition`, and grouped capabilities do not exist.

- [ ] **Step 3: Implement immutable unit definitions and registry filters**

```python
@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    job_kind: JobKind
    schedule_key: str
    processor_profile: str
    sharepoint_folder: str
    publication_files: tuple[tuple[str, frozenset[str]], ...]
    status_fields: tuple[str, ...]

    @property
    def allowed_columns(self) -> Mapping[str, frozenset[str]]:
        return MappingProxyType(dict(self.publication_files))


@dataclass(frozen=True, slots=True)
class UnitDefinition:
    key: str
    display_name: str
    status: UnitStatus
    capabilities: tuple[CapabilityDefinition, ...]

    def capability(self, job_kind: JobKind) -> CapabilityDefinition:
        matches = tuple(c for c in self.capabilities if c.job_kind == job_kind)
        if len(matches) != 1:
            raise KeyError(f"Enheten {self.key} har ikke kapabiliteten {job_kind}.")
        return matches[0]
```

Build `DEFAULT_UNITS` with active Hemato (`statistics`, `backlog`), active Solide (`statistics`), and four `coming` units without capabilities. Configure the Hemato backlog capability with folder `Prøveflyt` and filename `restansehistorikk_hemato.csv`.

- [ ] **Step 4: Run registry tests**

Run: `python -m pytest tests/test_modules.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the registry boundary**

```bash
git add src/molstat/modules.py tests/test_modules.py
git commit -m "refactor: organize modules by unit"
```

### Task 2: Add versioned portable settings and atomic transfer

**Files:**
- Modify: `src/molstat/config.py`
- Modify: `tests/test_config.py`

**Interfaces:**
- Produces: `SETTINGS_SCHEMA_VERSION = 2`
- Produces: `MolStatSettings.enabled_units: tuple[str, ...] = ("hemato", "solide")`
- Produces: `MolStatSettings.to_transfer_payload() -> dict[str, object]`
- Produces: `MolStatSettings.from_transfer_payload(payload: Mapping[str, object]) -> MolStatSettings`
- Produces: `MolStatSettings.export_to(path: Path) -> None`
- Produces: `MolStatSettings.import_from(path: Path) -> MolStatSettings`
- Existing `save`/`load` remain the local persistence boundary and migrate legacy unversioned JSON in memory.

- [ ] **Step 1: Write failing schema, exclusion, migration, and atomicity tests**

```python
def test_transfer_payload_is_versioned_and_excludes_local_runtime_data(tmp_path: Path) -> None:
    settings = MolStatSettings(
        sensitive_root=tmp_path / "sensitive",
        sharepoint_root=tmp_path / "sharepoint",
        lvms_url="https://lvms.example.invalid/clims/",
        lvms_config_path=tmp_path / "private-lvms.json",
        enabled_units=("hemato",),
        statistics_lookup_paths={"hemato": tmp_path / "lookup.xlsx"},
    )
    payload = settings.to_transfer_payload()
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["schema_version"] == 2
    assert payload["units"]["hemato"]["enabled"] is True
    for forbidden in ("lvms_config_path", "profile", "cookie", "cdp", "token"):
        assert forbidden not in serialized.casefold()


def test_invalid_import_does_not_replace_existing_settings(tmp_path: Path) -> None:
    current_path = tmp_path / "settings.json"
    current = MolStatSettings(sensitive_root=tmp_path / "original")
    current.save(current_path)
    transfer = tmp_path / "bad.json"
    transfer.write_text('{"schema_version": 999}', encoding="utf-8")
    with pytest.raises(ValueError, match="skjemaversjon"):
        MolStatSettings.import_from(transfer)
    assert MolStatSettings.load(current_path).sensitive_root == tmp_path / "original"
```

Add a legacy fixture without `schema_version` and assert it loads with both active units enabled and preserves existing roots, lookup paths, schedule hours, and LVMS URL.

- [ ] **Step 2: Run focused settings tests and verify failure**

Run: `python -m pytest tests/test_config.py -q`

Expected: FAIL because schema v2 and transfer methods do not exist.

- [ ] **Step 3: Implement strict parsing before object construction**

```python
SETTINGS_SCHEMA_VERSION = 2

def to_transfer_payload(self) -> dict[str, object]:
    return {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "sensitive_root": str(self.sensitive_root),
        "sharepoint_root": str(self.sharepoint_root) if self.sharepoint_root else None,
        "lvms_url": self.lvms_url,
        "schedules": {
            "statistics_hour": self.statistics_hour,
            "backlog_first_hour": self.backlog_first_hour,
            "backlog_last_hour": self.backlog_last_hour,
        },
        "units": {
            key: {
                "enabled": key in self.enabled_units,
                "statistics_lookup_path": str(self.statistics_lookup_paths.get(key, "")),
            }
            for key in ("hemato", "solide")
        },
    }
```

Validate exact top-level types, `schema_version == 2`, hour ranges, known unit keys, boolean activation values, and string-or-null paths. Parse into a new immutable object before writing anything. Use the existing temp-file-plus-`os.replace` pattern in both `save` and `export_to`.

- [ ] **Step 4: Run settings tests**

Run: `python -m pytest tests/test_config.py -q`

Expected: PASS, including non-ASCII JSON round-trip.

- [ ] **Step 5: Commit portable settings**

```bash
git add src/molstat/config.py tests/test_config.py
git commit -m "feat: add portable versioned settings"
```

### Task 3: Persist verbatim result and comment in schema v4

**Files:**
- Modify: `src/molstat/_backlog/domain.py`
- Modify: `src/molstat/_backlog/ingestion.py`
- Modify: `src/molstat/_backlog/history.py`
- Modify: `src/molstat/database.py`
- Modify: `src/molstat/backlog.py`
- Modify: `tests/backlog/test_ingestion.py`
- Modify: `tests/backlog/test_history.py`
- Modify: `tests/backlog/test_processor.py`
- Modify: `tests/test_database.py`

**Interfaces:**
- `BacklogDetail` adds `analysis_result: str` and `external_analysis_comment: str`.
- `BacklogDetailHistoryRow` adds the same two fields and removes `report_group`.
- SQLite schema version becomes `4`; `backlog_detail_snapshot` adds non-null `analysis_result` and `external_analysis_comment`, and old rows receive empty strings.
- `build_detail_history_rows(...)` maps exact unwrapped source text without interpretation.

- [ ] **Step 1: Write failing ingestion tests for exact text preservation**

```python
def test_detail_keeps_unwrapped_result_and_comment_verbatim(tmp_path: Path) -> None:
    path = tmp_path / "restanse.csv"
    path.write_text(
        "SampleID;Analyse;Tidspunkt analysebestilling;Status analyse;"
        "Analyseresultat;Ekstern analysekommentar\n"
        '=T("S1");TRG-OU;21.08.2026 09:00;Initial;'
        '=T("Påvist – behold æøå");=T("Linje 1, vurdert")\n',
        encoding="utf-8",
    )
    result = read_restanse_csv(path, real_contract())
    assert result.details[0].analysis_result == "Påvist – behold æøå"
    assert result.details[0].external_analysis_comment == "Linje 1, vurdert"
```

Update the existing privacy assertion: identifiers remain absent, while the two explicitly approved text fields are present.

- [ ] **Step 2: Write a failing additive database migration test**

Create a schema-v3 database using the former `backlog_detail_snapshot` definition, insert one row, call `migrate()`, and assert:

```python
assert database.schema_version() == 4
columns = {row[1] for row in connection.execute("PRAGMA table_info(backlog_detail_snapshot)")}
assert {"analysis_result", "external_analysis_comment"} <= columns
assert connection.execute(
    "SELECT analysis_result, external_analysis_comment FROM backlog_detail_snapshot"
).fetchone() == ("", "")
```

- [ ] **Step 3: Run the focused tests and confirm failure**

Run: `python -m pytest tests/backlog/test_ingestion.py tests/backlog/test_history.py tests/backlog/test_processor.py tests/test_database.py -q`

Expected: FAIL on missing dataclass fields and schema version 4.

- [ ] **Step 4: Extend transient and public row types**

```python
@dataclass(frozen=True)
class BacklogDetail:
    sample_id: str = field(repr=False)
    analysis_code: str
    analysis_group: str
    material: str
    collected_at: datetime | None
    arrived_at: datetime | None
    ordered_at: datetime
    analysis_priority: str
    request_priority: str
    analysis_status: str
    preliminary_status: str
    stage: WorkflowStage
    analysis_result: str
    external_analysis_comment: str


@dataclass(frozen=True, slots=True)
class BacklogDetailHistoryRow:
    observed_at: datetime
    unit_key: str
    material: str
    analysis_code: str
    nucleic_acid: str
    analysis_group_code: str
    analysis_group_label: str
    collected_at: datetime | None
    arrived_at: datetime | None
    ordered_at: datetime
    analysis_priority: str
    request_priority: str
    analysis_status: str
    preliminary_status: str
    workflow_stage: str
    response_deadline: str
    analysis_result: str
    external_analysis_comment: str
    classifier_version: int
```

Set these fields from the already-unwrapped `result_text` and `external_comment` variables in `read_restanse_csv`, then carry them unchanged through `build_detail_history_rows` and the parameterized insert in `BacklogProcessor.import_snapshot`.

- [ ] **Step 5: Implement schema-v4 migration transactionally**

In `MolStatDatabase.migrate`, inspect `PRAGMA table_info(backlog_detail_snapshot)` and run only missing additions:

```sql
ALTER TABLE backlog_detail_snapshot
ADD COLUMN analysis_result TEXT NOT NULL DEFAULT '';
ALTER TABLE backlog_detail_snapshot
ADD COLUMN external_analysis_comment TEXT NOT NULL DEFAULT '';
```

Keep migration inside the existing `BEGIN IMMEDIATE` transaction, accept versions 1–3, and update `schema_info` only after all statements succeed.

- [ ] **Step 6: Run detail and migration tests**

Run: `python -m pytest tests/backlog/test_ingestion.py tests/backlog/test_history.py tests/backlog/test_processor.py tests/test_database.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the expanded history model**

```bash
git add src/molstat/_backlog/domain.py src/molstat/_backlog/ingestion.py src/molstat/_backlog/history.py src/molstat/database.py src/molstat/backlog.py tests/backlog/test_ingestion.py tests/backlog/test_history.py tests/backlog/test_processor.py tests/test_database.py
git commit -m "feat: retain approved backlog detail text"
```

### Task 4: Publish the exact Hemato Prøveflyt CSV contract

**Files:**
- Modify: `src/molstat/_backlog/export.py`
- Modify: `tests/backlog/test_export.py`
- Modify: `tests/test_privacy_boundary.py`
- Modify: `docs/powerbi/sample_restansehistorikk.csv`

**Interfaces:**
- `BACKLOG_PUBLIC_COLUMNS` becomes the exact 19-column tuple from the spec.
- `export_backlog_history(database, destination, *, unit_key: str) -> int` exports only that unit.

- [ ] **Step 1: Write failing contract and byte-level tests**

```python
EXPECTED_COLUMNS = (
    "Observert_tidspunkt", "Enhet", "Materiale", "Analyse", "Nukleinsyre",
    "Analysegruppe_kode", "Analysegruppe", "Tidspunkt.prøvetaking",
    "Tidspunkt.ankomst", "Tidspunkt.analysebestilling", "Prioritet.analyse",
    "Prioritet.rekvisisjon", "Status.analyse", "Status.prelgruppe",
    "Restansestatus", "Svarfrist", "Analyseresultat",
    "Ekstern.analysekommentar", "Klassifikatorversjon",
)

assert BACKLOG_PUBLIC_COLUMNS == EXPECTED_COLUMNS
assert raw.startswith(b"\xef\xbb\xbf")
assert "Rapportgruppe" not in raw.decode("utf-8-sig")
assert rows[0]["Analyseresultat"] == "Påvist – behold æøå"
assert rows[0]["Ekstern.analysekommentar"] == "Ordrett kommentar"
```

Insert both Hemato and Solide rows and assert `unit_key="hemato"` exports only Hemato. Retain assertions excluding `SampleID`, `PID`, `WorkItem`, fingerprints, and paths.

- [ ] **Step 2: Run export/privacy tests and confirm failure**

Run: `python -m pytest tests/backlog/test_export.py tests/test_privacy_boundary.py -q`

Expected: FAIL because the old contract contains `Rapportgruppe` and omits text fields.

- [ ] **Step 3: Update SQL selection and atomic CSV mapping**

Use an explicit query—never `SELECT *`—with `WHERE unit_key = ?`. Select fields in the public header order and omit `report_group` and `source_fingerprint`:

```sql
SELECT observed_at, unit_key, material, analysis_code, nucleic_acid,
       analysis_group_code, analysis_group_label, collected_at, arrived_at,
       ordered_at, analysis_priority, request_priority, analysis_status,
       preliminary_status, workflow_stage, response_deadline,
       analysis_result, external_analysis_comment, classifier_version
FROM backlog_detail_snapshot
WHERE unit_key = ?
ORDER BY observed_at, row_number
```

Keep `NamedTemporaryFile(encoding="utf-8-sig", newline="")`, `csv.writer(delimiter=";")`, `fsync`, and `os.replace`.

- [ ] **Step 4: Update the synthetic sample to the exact contract**

Use safe fictional values, at least two analysis rows per `KLONALITET` snapshot, and include Norwegian characters in one result/comment. Do not include real IDs or real comments.

- [ ] **Step 5: Run export/privacy tests**

Run: `python -m pytest tests/backlog/test_export.py tests/test_privacy_boundary.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the public contract**

```bash
git add src/molstat/_backlog/export.py tests/backlog/test_export.py tests/test_privacy_boundary.py docs/powerbi/sample_restansehistorikk.csv
git commit -m "feat: publish detailed Hemato proveflyt CSV"
```

### Task 5: Add explicit unit run targets and partial outcomes

**Files:**
- Modify: `src/molstat/fetching.py`
- Modify: `src/molstat/system.py`
- Modify: `src/molstat/orchestrator.py`
- Modify: `src/molstat/services.py`
- Modify: `src/molstat/cli.py`
- Modify: `tests/test_fetching.py`
- Modify: `tests/test_end_to_end.py`
- Modify: `tests/test_orchestrator.py`
- Modify: `tests/test_services.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `UnifiedLvmsFetcher.fetch_statistics(unit_keys: Sequence[str] | None = None)`.
- Produces: `CapabilityRun(unit_key: str, job_kind: JobKind, summary: Mapping[str, object], error: BaseException | None = None)`.
- Produces: `MolStatSystem._run_capability(unit_key: str, job_kind: JobKind) -> Mapping[str, object]` as the single dispatch boundary used by unit/all execution.
- Produces: `MolStatSystem.run_unit(unit_key: str) -> tuple[CapabilityRun, ...]`.
- Produces: `MolStatSystem.run_all(enabled_units: Sequence[str]) -> tuple[CapabilityRun, ...]`.
- Produces: `JobStatus = Literal["succeeded", "partial", "failed", "busy"]`.
- `MolStatOrchestrator.run(target: str, trigger: str) -> JobResult` accepts `all`, unit keys, and compatibility aliases `statistics`/`backlog`.

- [ ] **Step 1: Write failing fetch scoping tests**

```python
result = fetcher.fetch_statistics(("solide",))
assert tuple(result) == ("solide",)
assert run_labels == ["solide"]
```

Reject unknown keys before launching LVMS and keep `None` meaning all configured statistics units for the legacy CLI path.

- [ ] **Step 2: Write failing run-target and continuation tests**

```python
def test_run_all_continues_after_one_capability_fails(tmp_path: Path) -> None:
    calls: list[str] = []
    system = MolStatSystem.__new__(MolStatSystem)
    system.units = DEFAULT_UNITS

    def run_capability(unit_key: str, job_kind: str) -> dict[str, int]:
        label = f"{unit_key}:{job_kind}"
        calls.append(label)
        if label == "hemato:statistics":
            raise RuntimeError("private test failure")
        return {"rows": 2 if job_kind == "backlog" else 3}

    system._run_capability = run_capability
    runs = system.run_all(("hemato", "solide"))
    assert calls == [
        "hemato:statistics", "hemato:backlog", "solide:statistics"
    ]
    assert [(run.unit_key, run.job_kind, run.error is None) for run in runs] == [
        ("hemato", "statistics", False),
        ("hemato", "backlog", True),
        ("solide", "statistics", True),
    ]
```

Add assertions that `hemato` executes statistics then backlog, `solide` executes only statistics, coming units are rejected, `statistics` maps to enabled statistics units, and `backlog` maps to Hemato backlog.

- [ ] **Step 3: Run focused routing tests and confirm failure**

Run: `python -m pytest tests/test_fetching.py tests/test_end_to_end.py tests/test_orchestrator.py tests/test_services.py tests/test_cli.py -q`

Expected: FAIL because only job-kind targets exist.

- [ ] **Step 4: Scope fetching and publication per capability**

Refactor the existing bodies behind this exact dispatcher:

```python
def _run_capability(
    self, unit_key: str, job_kind: JobKind
) -> Mapping[str, object]:
    if job_kind == "statistics":
        return self.run_statistics_unit(unit_key)
    if job_kind == "backlog":
        return self.run_backlog_unit(unit_key)
    raise ValueError(f"Ukjent kapabilitet: {job_kind}")
```

`run_statistics_unit` calls `self.statistics_fetch((unit_key,))`, processes only
the returned unit, and publishes to that capability's configured statistics
folder. `run_backlog_unit` rejects every key except a unit with a registered
backlog capability, fetches one backlog report, and publishes through that
capability's contract.

`run_backlog_unit("hemato")` must call:

```python
filename = "restansehistorikk_hemato.csv"
published_rows = export_backlog_history(
    self.database, output_dir / filename, unit_key="hemato"
)
self.backlog_publishers["hemato"].publish(
    {filename: output_dir / filename}, self.sharepoint_root / "Prøveflyt"
)
```

Build run order from `DEFAULT_UNITS`, catch errors per capability in `run_all`, and return each exception only inside the private `CapabilityRun` object.

- [ ] **Step 5: Aggregate safe statuses in the orchestrator**

```python
successful = sum(run.error is None for run in runs)
failed = len(runs) - successful
status = "succeeded" if failed == 0 else "failed" if successful == 0 else "partial"
summary = {"capabilities": len(runs), "succeeded": successful, "failed": failed}
```

Call the existing private failure reporter once per failure using a stage such as `hemato_statistics_run_failed`; never put exception text in `JobResult`, SQLite summaries, UI strings, or stdout JSON. Record the requested target as `job_run.kind`, preserving scheduled `statistics` and `backlog` records for `due_jobs`.

- [ ] **Step 6: Wire services and keep CLI compatibility**

Make `_build_system` construct processors/publishers only for enabled active units and validate only their required lookup files. `DefaultServices.run(target)` accepts `statistics`, `backlog`, `all`, `hemato`, and `solide`; keep argparse choices unchanged for the public CLI until a separate CLI extension is requested.

- [ ] **Step 7: Run routing and compatibility tests**

Run: `python -m pytest tests/test_fetching.py tests/test_end_to_end.py tests/test_orchestrator.py tests/test_services.py tests/test_cli.py tests/test_schedule.py -q`

Expected: PASS, including legacy scheduled-job behavior.

- [ ] **Step 8: Commit target orchestration**

```bash
git add src/molstat/fetching.py src/molstat/system.py src/molstat/orchestrator.py src/molstat/services.py src/molstat/cli.py tests/test_fetching.py tests/test_end_to_end.py tests/test_orchestrator.py tests/test_services.py tests/test_cli.py tests/test_schedule.py
git commit -m "feat: run MolStat by unit"
```

### Task 6: Build the unit-centred overview

**Files:**
- Modify: `src/molstat/ui/dashboard.py`
- Modify: `src/molstat/ui/app.py`
- Modify: `src/molstat/ui/theme.py`
- Modify: `tests/ui/test_control_center.py`

**Interfaces:**
- Produces: `UnitCard(unit: UnitDefinition)` with `run_button: QPushButton` and `set_status(state, detail)`.
- `OverviewPage.unit_cards: dict[str, UnitCard]` contains all six units.
- `OverviewPage.run_all: QPushButton` dispatches target `all`; each active card dispatches its stable unit key.
- `_JobWorker` stores `target`, not a job-kind label.

- [ ] **Step 1: Write failing accessibility and dispatch tests**

```python
def test_overview_exposes_all_units_and_stable_run_targets(qtbot) -> None:
    orchestrator = FakeOrchestrator()
    window = MainWindow(orchestrator, FakeSettingsStore())
    qtbot.addWidget(window)
    for name in ("run-all", "run-hemato", "run-solide"):
        button = window.findChild(QPushButton, name)
        assert button is not None
        assert button.minimumHeight() >= 44
        assert button.accessibleName()
    for key in ("lege", "flow", "pre", "hist"):
        button = window.findChild(QPushButton, f"run-{key}")
        assert button is not None
        assert button.isEnabled() is False
        assert "kommer" in button.text().casefold()

    qtbot.mouseClick(window.findChild(QPushButton, "run-hemato"), Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window._workers, timeout=3000)
    assert orchestrator.calls == [("hemato", "manual")]
```

Add tests for `all` and `solide`, capability labels (`Statistikk + restanse` / `Statistikk`), and `partial` completion text.

- [ ] **Step 2: Run UI tests and confirm failure**

Run: `python -m pytest tests/ui/test_control_center.py -q`

Expected: FAIL because the overview still has global statistics/backlog controls.

- [ ] **Step 3: Implement registry-driven unit cards**

Create cards from `DEFAULT_UNITS` rather than hard-coding six widget blocks. Use a two-column `QGridLayout`, set `Kommer` buttons disabled, and retain visible text labels for every action. Add style selectors for `unitStatus="coming"`, disabled buttons, and partial status using existing `COLORS` only.

- [ ] **Step 4: Implement independent button locking**

Track active targets in `MainWindow._workers`. While `all` runs, disable all active run buttons. While a single unit runs, disable `Kjør alt` and only that unit button; leave the other independent unit button enabled. Restore the exact set when its worker finishes.

- [ ] **Step 5: Run UI and theme tests**

Run: `python -m pytest tests/ui/test_control_center.py -q`

Expected: PASS, including contrast and accessible names.

- [ ] **Step 6: Commit the overview**

```bash
git add src/molstat/ui/dashboard.py src/molstat/ui/app.py src/molstat/ui/theme.py tests/ui/test_control_center.py
git commit -m "feat: add unit-centred control overview"
```

### Task 7: Add per-unit settings sections and JSON import/export UI

**Files:**
- Modify: `src/molstat/services.py`
- Modify: `src/molstat/ui/settings.py`
- Modify: `src/molstat/ui/app.py`
- Modify: `tests/test_services.py`
- Modify: `tests/ui/test_control_center.py`

**Interfaces:**
- Produces: `DefaultServices.export_settings(path: Path) -> None`.
- Produces: `DefaultServices.import_settings(path: Path) -> tuple[str, ...]`, returning unavailable-path messages after successful atomic replacement.
- `SettingsPage.enabled_fields: dict[str, QCheckBox]` for Hemato and Solide.
- `SettingsPage.import_button` and `export_button` use JSON file dialogs.

- [ ] **Step 1: Write failing service tests for transfer and unavailable paths**

```python
def test_import_replaces_settings_only_after_full_validation(tmp_path: Path) -> None:
    services = configured_services(tmp_path)
    transfer = tmp_path / "molstat-innstillinger.json"
    services.export_settings(transfer)
    payload = json.loads(transfer.read_text(encoding="utf-8"))
    payload["sharepoint_root"] = str(tmp_path / "other-pc-sharepoint")
    transfer.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    warnings = services.import_settings(transfer)
    assert "SharePoint" in " ".join(warnings)
    assert services.settings.sharepoint_root == tmp_path / "other-pc-sharepoint"
```

Also corrupt the JSON and assert both the in-memory object and local settings file bytes remain unchanged.

- [ ] **Step 2: Write failing UI dialog and unit-section tests**

Mock `QFileDialog.getSaveFileName` to return `molstat-innstillinger.json` and assert `export_settings` receives it. Mock `getOpenFileName`, assert imported values refill all fields, and verify an unavailable path displays `Må velges på denne PC-en` without exposing the path in diagnostics.

- [ ] **Step 3: Run focused settings tests and confirm failure**

Run: `python -m pytest tests/test_services.py tests/ui/test_control_center.py -q`

Expected: FAIL because transfer services and controls do not exist.

- [ ] **Step 4: Implement service-level atomic replacement**

```python
def import_settings(self, path: Path) -> tuple[str, ...]:
    imported = MolStatSettings.import_from(path)
    warnings = _unavailable_path_messages(imported)
    imported.save(self.settings_path)
    self.settings = imported
    self._settings_exist = True
    return warnings
```

`_unavailable_path_messages` returns labels only (`K-sensitiv mappe`, `SharePoint-mappe`, `Lookup-fil for Hemato`, `Lookup-fil for Solide`) and does not include raw paths. `_validate_production_paths` blocks runs for missing paths but saving/importing a valid portable configuration remains possible.

- [ ] **Step 5: Build global, Hemato, Solide, and transfer groups**

Use one `QGroupBox` for global roots/LVMS, one for each active unit with enable checkbox and lookup file, and one `QGroupBox("Flytt innstillinger")` containing `Importer …` and `Eksporter …`. Build unit groups from `DEFAULT_UNITS.active()` and do not render required fields for coming units.

- [ ] **Step 6: Wire dialogs, refresh, and safe status messages**

After import, call `_load_settings()`, `refresh_gui_runtime()`, `_refresh_overview_status()`, and show either a success message or the unavailable field labels. Never place imported JSON values in the status bar or diagnostics.

- [ ] **Step 7: Run service and UI settings tests**

Run: `python -m pytest tests/test_services.py tests/ui/test_control_center.py -q`

Expected: PASS.

- [ ] **Step 8: Commit settings UI and transfer**

```bash
git add src/molstat/services.py src/molstat/ui/settings.py src/molstat/ui/app.py tests/test_services.py tests/ui/test_control_center.py
git commit -m "feat: import and export unit settings"
```

### Task 8: Create and package the MolStat icon

**Files:**
- Create: `src/molstat/assets/molstat.png`
- Create: `src/molstat/assets/molstat.ico`
- Modify: `src/molstat/ui/app.py`
- Modify: `pyproject.toml`
- Modify: `tests/ui/test_control_center.py`
- Modify: `tests/test_python_felles_scripts.py`

**Interfaces:**
- Produces: `asset_path(name: str) -> Path` in `src/molstat/ui/app.py` or a focused `src/molstat/assets.py` if the helper exceeds one responsibility.
- `create_application` sets the application icon; `MainWindow` sets the same icon explicitly.

- [ ] **Step 1: Write failing icon presence and runtime tests**

```python
def test_window_has_packaged_molstat_icon(qtbot) -> None:
    window = MainWindow(FakeOrchestrator(), FakeSettingsStore())
    qtbot.addWidget(window)
    assert window.windowIcon().isNull() is False


def test_icon_assets_are_packaged() -> None:
    root = Path(__file__).parents[2]
    assert (root / "src/molstat/assets/molstat.png").stat().st_size > 1000
    assert (root / "src/molstat/assets/molstat.ico").stat().st_size > 1000
```

- [ ] **Step 2: Run icon tests and verify failure**

Run: `python -m pytest tests/ui/test_control_center.py tests/test_python_felles_scripts.py -q`

Expected: FAIL because no assets or window icon exist.

- [ ] **Step 3: Generate the original source icon using the imagegen skill**

Generate a square 1024 × 1024 bitmap with this art direction: pastel-yellow field, dark brown/near-black molecular or DNA path forming three ascending statistical bars, rounded geometry, no text, no Power BI logo imitation, high legibility at 16 px. Save the selected PNG as `src/molstat/assets/molstat.png`.

- [ ] **Step 4: Convert the approved PNG to a multi-resolution ICO**

Use the workspace-provided Python/Pillow runtime rather than adding a production dependency:

```python
from PIL import Image

source = Image.open("src/molstat/assets/molstat.png").convert("RGBA")
source.save(
    "src/molstat/assets/molstat.ico",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
```

- [ ] **Step 5: Wire and package both assets**

Add `assets/*.png` and `assets/*.ico` to `[tool.setuptools.package-data]`. Resolve paths relative to `Path(__file__).resolve().parents[1]`, construct `QIcon`, and apply it to both `QApplication` and `MainWindow`.

- [ ] **Step 6: Visually inspect 16, 32, and 256 px renders**

Render or open the PNG and ICO sizes. Confirm the DNA/bar silhouette remains distinguishable, edges are clean, background/foreground match the app palette, and there is no embedded text.

- [ ] **Step 7: Run icon and package tests**

Run: `python -m pytest tests/ui/test_control_center.py tests/test_python_felles_scripts.py -q`

Expected: PASS.

- [ ] **Step 8: Commit the icon**

```bash
git add src/molstat/assets/molstat.png src/molstat/assets/molstat.ico src/molstat/ui/app.py pyproject.toml tests/ui/test_control_center.py tests/test_python_felles_scripts.py
git commit -m "feat: add MolStat application icon"
```

### Task 9: Rewrite README and verify the full release candidate

**Files:**
- Modify: `README.md`
- Modify: `JOBBS-PC.md` only where README links reveal stale command or path names
- Modify: `tests/test_python_felles_scripts.py` only if documentation command assertions require alignment

**Interfaces:**
- Documents the exact UI, directory layout, schedules, privacy boundary, import/export process, and supported commands delivered by Tasks 1–8.

- [ ] **Step 1: Replace the stale README with the operator flow**

Use these top-level sections:

```markdown
# MolStat
## Hva MolStat gjør
## Enheter
## Sikker dataflyt
## Mappestruktur i SharePoint
## Installasjon på jobb-PC
## Første gangs oppsett
## Kjøring og automatisering
## Flytte innstillinger mellom PC-er
## Prøveflyt-data
## Personvernansvar for fritekst
## Utvikling og test
## Mer dokumentasjon
```

State that Hemato has statistics and Prøveflyt, Solide has statistics, and Lege/Flow/Pre/Hist are disabled placeholders. Show `MolStat/hemato`, `MolStat/solide`, and `MolStat/Prøveflyt/restansehistorikk_hemato.csv`. List the 19 public columns and explicitly state that result/comment are verbatim and operational users must not enter identifiers there.

- [ ] **Step 2: Document exact commands and automation behavior**

Include:

```powershell
python -m pip install -e ".[dev]"
python -m molstat gui --settings "C:\ProgramData\MolStat\settings.json"
python -m molstat check-config --settings "C:\ProgramData\MolStat\settings.json"
python -m pytest
```

Explain that scheduled `statistics` runs daily at the configured hour and `backlog` runs hourly inside its configured window; Windows Task Scheduler invokes existing CLI compatibility targets.

- [ ] **Step 3: Scan documentation for private paths and stale browser-board claims**

Run: `rg -n "C:\\Users|CHRBJ5|molpa|åpne.*nettles|Power BI-rapport|restansehistorikk\.csv" README.md JOBBS-PC.md`

Expected: no usernames, no claim that the removed browser board or Power BI launcher is part of the app, and no unqualified old backlog filename.

- [ ] **Step 4: Run the complete automated verification**

Run: `python -m pytest`

Expected: all tests pass.

Run: `python -m compileall -q src tests`

Expected: exit code 0.

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 5: Perform a safe local acceptance run**

Against copied/synthetic input and temporary roots, confirm:

```text
Kjør alt -> Hemato statistics + Hemato backlog + Solide statistics
Hemato -> Hemato statistics + Hemato backlog
Solide -> Solide statistics only
Prøveflyt output -> Prøveflyt/restansehistorikk_hemato.csv
Encoding -> EF BB BF prefix and readable æ/ø/å
Forbidden structured columns -> absent
Settings export -> no lvms_config_path/profile/session/CDP data
```

Do not publish test data to the user’s real SharePoint folder.

- [ ] **Step 6: Commit documentation and final alignment**

```bash
git add README.md JOBBS-PC.md tests/test_python_felles_scripts.py
git commit -m "docs: update MolStat operator guide"
```

- [ ] **Step 7: Review final history and working tree**

Run: `git status --short; git log --oneline -10`

Expected: clean worktree and nine focused implementation commits after the design commit.
