"""Vendored LVMS-STAT Edge/CDP runtime (FROZEN).

Source: Christian-Bjornstad/LVMS-STAT, branch codex/config-bootstrap-fix,
commit e758516 (local checkout C:/Users/molpa/Documents/LVMS-STAT).

These 13 modules are the frozen Edge/CDP download flow (LVMS-STAT commits
c1360fe-3cba604 lineage). They are vendored VERBATIM except for the
mechanical import rewrite ``lvms_stat.X`` -> ``molstat.lvms.X``.
Do NOT refactor logic here; fix upstream in LVMS-STAT and re-vendor.

MolPat Puls uses only the RESTANSE report (PAT-DIT-RESTANSE-OU) through this
runtime. Callers must always pass ``repository_root`` explicitly to
``run_report_batch`` — the in-module ``parents[2]`` fallback resolves to the
wrong directory at this vendored depth and must never be relied upon.
"""

