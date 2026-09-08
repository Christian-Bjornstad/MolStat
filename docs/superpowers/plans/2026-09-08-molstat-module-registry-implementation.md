# MolStat Module Registry Implementation Plan

**Goal:** Centralize Hemato, Solide and Prøveflyt metadata in an explicit,
immutable registry so a later data module does not require a new unit-specific
branch in the service layer.

### Task 1: Define and test the registry contract

- Add failing tests for unique keys, stable display names, job kind, schedule,
  processor profile, publication allowlist, SharePoint folder and status fields.
- Implement immutable module and publication-file definitions plus lookup by key
  and job kind.

### Task 2: Route runtime construction through the registry

- Build statistics processors and publication policies by iterating registered
  statistics modules.
- Resolve all publication destinations from the registry in `MolStatSystem`.
- Keep registration explicit Python code; never load executable plugins from
  settings or external files.

### Task 3: Verify

- Run module, service and system tests, then the complete test suite.
- Confirm the service layer has no Hemato/Solide profile or folder branch.
