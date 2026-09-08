# MolStat UI and Power BI Implementation Plan

> **Execution:** Run inline with `superpowers:executing-plans`; test and commit each vertical slice.

**Goal:** Replace browser-board affordances with a Power BI workflow, apply the approved accessible pastel-yellow visual system, and deliver a reproducible Prøveflyt report starter matching `restansehistorikk.csv`.

**Design system:** Power BI yellow `#F2C811`, pastel background `#FFF9E6`, soft surface `#FFF3C4`, foreground `#2B2618`, muted text `#5C553D`, dark sidebar `#3A321B`, focus `#8A6A00`, success `#1B7D3A`, warning `#9A6A00`, danger `#A4262C`. All text pairs retain at least WCAG AA contrast.

---

### Task 1: Apply the pastel Power BI-inspired UI

**Files:**
- Modify: `src/molstat/ui/theme.py`
- Modify: `design-system/molstat/MASTER.md`
- Modify: `tests/ui/test_control_center.py`

- [ ] Add failing assertions for the approved semantic color tokens and visible focus treatment.
- [ ] Replace blue surfaces, borders, hover and navigation states with the approved yellow/dark palette.
- [ ] Keep 44 px hit targets, keyboard focus, Segoe UI and existing layout/density.
- [ ] Render the main window offscreen to PNG and inspect it visually.
- [ ] Run `python -m pytest tests/ui/test_control_center.py -q`.
- [ ] Commit as `style: apply Power BI inspired pastel theme`.

### Task 2: Replace the browser-board action with Power BI

**Files:**
- Modify: `src/molstat/config.py`
- Modify: `src/molstat/services.py`
- Modify: `src/molstat/ui/app.py`
- Modify: `src/molstat/ui/dashboard.py`
- Modify: `src/molstat/ui/settings.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_services.py`
- Modify: `tests/ui/test_control_center.py`

- [ ] Add optional `power_bi_report_url`, persisted in local settings and accepted only as HTTPS on `app.powerbi.com`.
- [ ] Replace `BoardController` with a controller that opens only the validated report URL.
- [ ] Rename the action to `Åpne Prøveflyt i Power BI`; show a settings hint if no URL is configured.
- [ ] Add a labeled accessible URL field in Settings and include it in load/save flows.
- [ ] Update backlog completion status to report published row/snapshot counts.
- [ ] Keep the old web server code dormant until the Power BI flow has been accepted, but remove all GUI and automation entry points to it.
- [ ] Run config, service and UI tests; commit as `feat: open Prøveflyt in Power BI`.

### Task 3: Build the reproducible Power BI starter

**Files:**
- Replace: `docs/powerbi/BYGG_PBI_MAL.md`
- Create: `docs/powerbi/molstat-proveflyt-theme.json`
- Create: `docs/powerbi/sample_restansehistorikk.csv`
- Create: `docs/powerbi/power-query.m`
- Create: `docs/powerbi/measures.dax`

- [ ] Generate synthetic hourly rows using the exact 15-column public contract, including enabled groups with zeros.
- [ ] Define `FactRestanse`, `DimDato`, and `DimAnalysegruppe`; only `DimDato[Dato]` is marked as the date table.
- [ ] Define latest-observation measures from `MAX(FactRestanse[Observert_tidspunkt])`, never `TODAY()` and never sum across snapshots.
- [ ] Specify three pages: `Prøveflyt – nå`, `Utvikling`, and aggregate drill-through `Analysegruppe`.
- [ ] Use a matrix/card-grid driven by the dimension so new analysis groups appear automatically.
- [ ] Validate JSON/CSV, scan for forbidden identifiers and update the guide with SharePoint-folder parameter instructions.
- [ ] Commit as `docs: deliver Power BI Prøveflyt starter`.

### Task 4: Seed the open Power BI Desktop model

- [ ] Connect with the installed `pbi-cli` and verify the target model is the empty MolStat session.
- [ ] Create the file-path parameter, `FactRestanse`, dimensions, relationships and measures from the checked-in starter definitions.
- [ ] Refresh and run DAX row-count/latest-timestamp checks.
- [ ] If PBIR report source is available, create the three pages and apply the checked-in theme; otherwise leave the verified semantic model open and provide the exact Desktop save step without inventing a saved artifact.
- [ ] Do not install `power-bi-codex` unless a missing capability remains after `pbi-cli`; it is optional guidance, not a runtime dependency.

### Task 5: Final verification

- [ ] Run the full Python test suite and `git diff --check` over all implementation commits.
- [ ] Confirm no production CSV, database, PBIX/PBIT, settings or identifiers are tracked.
- [ ] Confirm the branch is clean and summarize the one remaining external SharePoint/settings action, if any.
