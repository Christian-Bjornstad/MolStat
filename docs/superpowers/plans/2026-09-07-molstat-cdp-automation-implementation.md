# MolStat CDP and Automation Implementation Plan

> **Execution:** Run inline with `superpowers:executing-plans`, one tested commit per task.

**Goal:** Make managed Edge discovery follow `DevToolsActivePort` and install only the two clock-driven jobs still needed after Power BI replaces the browser board.

**Architecture:** Edge chooses its own debugging port with `--remote-debugging-port=0`; MolStat waits for the profile-owned `DevToolsActivePort`, validates the announced loopback port, then discovers the page. WebSocket connections omit Origin. Windows Task Scheduler retains daily statistics at 05:00 and hourly Prøveflyt snapshots from 06:00 through 18:00 with `IgnoreNew`; installation removes the obsolete board task.

**Reference:** `C:\Users\molpa\Downloads\edge-cdp-dynamic-port.md`

---

### Task 1: Discover Edge's actual dynamic port

**Files:**
- Modify: `src/molstat/lvms/edge.py`
- Modify: `src/molstat/lvms/browser_session.py`
- Modify: `tests/lvms/test_edge.py`
- Modify: `tests/lvms_superset/test_edge.py`
- Modify: `tests/lvms/test_browser_session.py`

- [ ] Change `build_edge_arguments` to accept no requested port, send `--remote-debugging-port=0`, retain loopback address and isolated absolute profile, and omit `--remote-allow-origins`.
- [ ] Add `_read_devtools_active_port(path)` with numeric/range validation and a bounded `wait_for_devtools_port(profile, process, timeout_seconds=20)` loop.
- [ ] Delete a stale `DevToolsActivePort` before launch; start Edge; wait for the fresh file; store the actual port in `EdgeProcess`.
- [ ] Test stale-file removal, delayed/invalid port files, early process exit, timeout cleanup, and the exact launch flags.
- [ ] Update browser-session tests so retry behavior still closes a failed owned process.
- [ ] Run `python -m pytest tests/lvms/test_edge.py tests/lvms_superset/test_edge.py tests/lvms/test_browser_session.py -q`.
- [ ] Commit as `fix: discover managed Edge dynamic CDP port`.

### Task 2: Open CDP WebSockets without Origin

**Files:**
- Modify: `src/molstat/lvms/cdp.py`
- Modify: `tests/lvms/test_cdp.py`

- [ ] Add a failing test that records `websocket.create_connection` arguments and requires `suppress_origin=True` with no explicit `origin`.
- [ ] Preserve loopback URL and port validation.
- [ ] Run `python -m pytest tests/lvms/test_cdp.py tests/lvms/test_browser_session.py -q`.
- [ ] Commit as `fix: suppress CDP websocket origin`.

### Task 3: Retire the board task and retain clock jobs

**Files:**
- Modify: `src/molstat/windows_automation.py`
- Modify: `src/molstat/services.py`
- Modify: `tests/test_windows_automation.py`

- [ ] Change `AutomationResult` to report only statistics and backlog tasks.
- [ ] Generate only `statistics.cmd`/XML and `backlog.cmd`/XML.
- [ ] Register statistics at 05:00 and backlog at every hour 06:00–18:00, local Windows time, with `IgnoreNew` and `StartWhenAvailable`.
- [ ] Best-effort delete the legacy `MolStat - tavleserver` task during installation; ignore only the documented “not found” result and surface other failures.
- [ ] Remove `board_task` from the CLI result.
- [ ] Run `python -m pytest tests/test_windows_automation.py tests/test_schedule.py tests/test_services.py -q`.
- [ ] Commit as `fix: install only Power BI data jobs`.

### Task 4: Operational verification

- [ ] Run the full test suite.
- [ ] Query the three named Windows tasks before installation.
- [ ] If MolStat settings validate, run the installer and query tasks again; otherwise report the exact non-sensitive prerequisite without mutating tasks.
- [ ] Confirm statistics and backlog task XML schedules and that the board task is absent.
- [ ] Run a bounded live Edge/CDP startup smoke test with a temporary profile when Edge is available; terminate only the process started by the smoke test.
- [ ] Run `git diff --check HEAD~3..HEAD` and confirm a clean status.
