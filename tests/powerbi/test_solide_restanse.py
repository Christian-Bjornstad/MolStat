"""Solide templates must never carry Hemato patients or activate guessed jobs."""
import copy
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("solide_rest", ROOT / "tools/build_solide_restanse.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def test_correct_reference_keeps_help_dropdown_and_original_status_display(tmp_path):
    import zipfile
    source = Path.home() / "Downloads/Restanse_Hemato (1).pbix"
    if not source.exists():
        pytest.skip("Local supplied reference is unavailable")
    groups = [(builder.GROUP_CODES[label], label) for label in builder.BACKLOG_LABELS.values()]
    docs = builder.make_report(source, tmp_path, groups)
    text = json.dumps(docs, ensure_ascii=False)
    assert "Mal –" not in text and "Venter på første uttrekk" not in text
    pages = [v for k, v in docs.items() if k.endswith("/page.json")]
    assert {p["displayName"] for p in pages} == {"Solide Restanse", "Forklaringer"}
    assert any(k.endswith("/analysis-dropdown/visual.json") for k in docs)
    with zipfile.ZipFile(source) as z:
        name = next(k for k in docs if k.endswith("/last-observed/visual.json"))
        assert docs[name] == json.loads(z.read(name))
    assert "Kortstatus farge" in text
    assert len([k for k in docs if re.search(r"/analysis-(cards|card-\d+)/visual.json$", k)]) == 11


def test_draft_cannot_be_activated_without_lvms_groups(tmp_path):
    from molstat.unit_settings import UnitConfigError, load_unit_file

    unit = json.loads((ROOT / "src/molstat/defaults/units/solide.json").read_text("utf-8"))
    hemato = json.loads((ROOT / "src/molstat/defaults/units/hemato.json").read_text("utf-8"))
    rows = [{"code": "TERT-OU", "name": "TERT", "group": "Sanger", "deadline_days": 15}]
    draft = builder.unit_draft(unit, hemato["backlog"], rows)
    path = tmp_path / "solide.json"
    path.write_text(json.dumps(draft), encoding="utf-8")
    with pytest.raises(UnitConfigError, match="minst én gruppe"):
        load_unit_file(path, "solide")
    draft["backlog"]["report"]["report_groups"] = ["SYNTHETIC-SOLIDE"]
    path.write_text(json.dumps(draft), encoding="utf-8")
    loaded = load_unit_file(path, "solide")
    assert loaded.payload["statistics"] == unit["statistics"]
    assert loaded.payload["backlog"]["analyses"]["unit"]["key"] == "solide"
    assert loaded.payload["backlog"]["report"]["analysis_codes"] == ["TERT-OU"]


def test_template_model_has_empty_fact_source_and_fixed_solide_groups():
    model = {"model": {"tables": [
        {"name": "Restanse", "columns": [{"name": "Enhet", "sourceColumn": "Enhet", "dataType": "string"}],
         "partitions": [{"source": {"type": "m", "expression": "Web.Contents(hemato)"}}]},
        {"name": "DimAnalysegruppe", "partitions": [{"source": {"type": "calculated", "expression": "old"}}]},
    ]}}
    original = copy.deepcopy(model)
    result = builder.empty_model(model, [("SOLIDE-SANGER", "Sanger")])
    assert model == original
    source = result["model"]["tables"][0]["partitions"][0]["source"]["expression"]
    assert "#table" in source and "{}" in source
    assert "Web.Contents" not in source and "hemato" not in source
    assert "SOLIDE-SANGER" in result["model"]["tables"][1]["partitions"][0]["source"]["expression"]


def test_backlog_list_uses_selected_rows_and_cleans_group_names():
    rows = [
        ("3730, Sanger", "OU-SOLIDE,OU-HEM", "TERT-OU,TERT-SEKV-OU,"),
        ("3730, ID-PCR", "OU-SOLIDE", "ID-PCR-OU,MOLA-PCR-OU"),
        ("Idylla", "OU-SOLIDE", "MSI-OU"),
        ("HTS, Childhood", "OU-SOLIDE", "HTS-BIBLIOTEK-DNA-OU"),
        ("HTS, bestillingsanalyser og varianter", "OU-SOLIDE", "HTS-CRC-OU,SEKV20-OU"),
        ("Myriad, utsvaring", "OU-SOLIDE", "MYRIAD-OU"),
    ]
    selected = builder.parse_backlog_rows(rows)
    assert {r["group"] for r in selected} == {"Sanger", "Childhood", "HTS - bestillingsanalyser og varianter"}
    assert {r["code"] for r in selected} == {"TERT-OU", "TERT-SEKV-OU", "HTS-BIBLIOTEK-DNA-OU", "HTS-CRC-OU", "SEKV20-OU"}
    assert selected[0]["report_groups"] == ["OU-SOLIDE", "OU-HEM"]


def test_default_solide_backlog_is_ready_and_does_not_include_excluded_codes():
    from molstat.unit_settings import default_unit_file, load_unit_file
    from molstat.modules import configured_registry

    definition = load_unit_file(default_unit_file("solide"))
    backlog = definition.payload["backlog"]
    assert backlog is not None
    assert len(backlog["analyses"]["analyses"]) == 11
    assert backlog["report"]["report_groups"] == ["OU-SOLIDE", "OU-HEM"]
    codes = set(backlog["report"]["analysis_codes"])
    assert {"TERT-SEKV-OU", "HRR-BIBLIOTEK-OU", "SEKV20-OU", "NANOPORE-OU"} <= codes
    assert not codes & {"ID-PCR-OU", "MOLA-PCR-OU", "MSI-OU", "MYRIAD-OU", "FORBVIDERE-OU", "BESKJED-OU", "EKSTRAKSJON-OU"}
    capability = configured_registry({"solide": definition}).require("solide").capability("backlog")
    assert capability.publication_files[0][0] == "restansehistorikk_solide.csv"


def test_legacy_solide_upgrade_keeps_statistics_and_adds_verified_backlog(tmp_path):
    from molstat.unit_settings import default_unit_file, load_unit_file, upgrade_source
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    original = json.loads((ROOT / "config/units.json").read_text("utf-8"))
    original["units"]["solide"]["analysis_codes"].append("CUSTOM-OU")
    original["units"]["solide"]["reports"][0]["analysis_codes"].append("CUSTOM-OU")
    (legacy / "units.json").write_text(json.dumps(original), encoding="utf-8")
    migrated = load_unit_file(upgrade_source(tmp_path / "sensitive", "solide", legacy))
    assert "CUSTOM-OU" in migrated.payload["statistics"]["antall"]["analysis_codes"]
    assert migrated.payload["backlog"] == load_unit_file(default_unit_file("solide")).payload["backlog"]


def test_all_selected_codes_reach_the_correct_solide_export_group(tmp_path):
    import csv
    from datetime import datetime
    from molstat.unit_settings import default_unit_file, load_unit_file
    from molstat._backlog.config import validate_app_config
    from molstat.backlog import BacklogProcessor, CsvContract
    from molstat.database import MolStatDatabase
    from molstat._backlog.export import export_backlog_history

    backlog = load_unit_file(default_unit_file("solide")).payload["backlog"]
    columns = backlog["columns"]
    contract = CsvContract(delimiter=columns["delimiter"], encoding=columns["encoding"],
                           columns=columns["columns"], completed_values=tuple(columns["completed_values"]),
                           classifier_version=columns["classifier_version"])
    config = validate_app_config(backlog["analyses"])
    source = tmp_path / "synthetic.csv"
    with source.open("w", encoding=contract.encoding, newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(contract.columns.values()), delimiter=";")
        writer.writeheader()
        for index, code in enumerate(backlog["report"]["analysis_codes"]):
            writer.writerow({"SampleID": f"SYNTHETIC-{index}", "WorkItem": str(index), "Analyse": code,
                             "Tidspunkt analysebestilling": "17.10.2026 08:00", "Tidspunkt ankomst": "17.10.2026 09:00",
                             "Status analyse": "Initial"})
    database = MolStatDatabase(tmp_path / "synthetic.sqlite")
    database.migrate()
    imported = BacklogProcessor(config, contract, now=lambda: datetime(2026, 10, 18, 10)).import_snapshot(source, database)
    assert imported.rows_read == 213
    output = tmp_path / "restansehistorikk_solide.csv"
    assert export_backlog_history(database, output, unit_key="solide") == 213
    with output.open(encoding="utf-8-sig") as stream:
        exported = list(csv.DictReader(stream, delimiter=";"))
    expected = {code: group["label"] for group in backlog["analyses"]["analyses"] for code in group["source_codes"]}
    assert {r["Analyse"]: r["Analysegruppe"] for r in exported} == expected
    assert {r["Enhet"] for r in exported} == {"solide"}
    assert "SYNTHETIC-" not in output.read_text("utf-8-sig")


def test_solide_fetch_sends_full_backlog_definition_and_hemato_date_window(tmp_path):
    from datetime import date
    from molstat.unit_settings import default_unit_file, load_unit_file, materialize_snapshot
    from molstat.fetching import UnifiedLvmsFetcher
    from molstat.lvms.report_job import load_report_jobs, batch_filename

    definition = load_unit_file(default_unit_file("solide"))
    snapshot = materialize_snapshot(tmp_path, {"solide": definition})
    jobs = []
    def runner(config, jobs_path, keys, **kwargs):
        jobs.extend(load_report_jobs(jobs_path))
        output = kwargs["repository_root"] / "rådata"
        output.mkdir(parents=True)
        for job in jobs:
            (output / batch_filename(job)).write_text("synthetic")
        return 0
    fetcher = UnifiedLvmsFetcher(lvms_config_path=tmp_path / "lvms.json", sensitive_root=tmp_path,
        work_root=tmp_path / "work", units_path=snapshot / "units.json",
        backlog_report_path=snapshot / "solide/backlog-report.json", run_batch=runner,
        today=lambda: date(2026, 10, 18))
    request, source = fetcher.fetch_backlog("solide")
    assert source.is_file() and request.unit == "solide"
    assert (request.date_from, request.date_to) == (date(2024, 1, 1), date(2026, 10, 18))
    assert len(jobs) == 1
    assert jobs[0].report_groups == ("OU-SOLIDE", "OU-HEM")
    assert list(jobs[0].analysis_codes) == definition.payload["backlog"]["report"]["analysis_codes"]
