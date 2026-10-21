from unit_fixtures import analysis_codes
import csv
from datetime import date
from pathlib import Path

import pytest

from molstat.archive import RawArchive
from molstat.database import MolStatDatabase
from molstat.manual_import import ManualImportError, ManualImportPlan, process_manual_import
from molstat.modules import configured_registry
from molstat.publisher import PublicationPolicy, SharePointPublisher, default_forbidden_patterns
from molstat.statistics import StatisticsProcessor
from molstat.system import MolStatSystem
from molstat.unit_settings import load_unit_file
from unit_fixtures import default_unit_file
from unit_fixtures import analysis_codes as default_lookup_path
from molstat.backlog import BacklogProcessor, CsvContract
from molstat._backlog.config import validate_app_config
import xlsxwriter


def _system(tmp_path, key="hemato", workflow=False):
    lookup = tmp_path / "lookup.xlsx"
    with xlsxwriter.Workbook(lookup) as workbook:
        sheet = workbook.add_worksheet("Lookup")
        sheet.write_row(0, 0, ["Analyse", "Nukleinsyre", "Rapportgruppe", "Svarfrist"])
        sheet.write_row(1, 0, ["CALR-OU", "DNA", "MPN", "21"])
    definition = load_unit_file(default_unit_file(key))
    if key == "lege" and not workflow:
        from dataclasses import replace
        from molstat._statistics.units import validate_units
        roles = {"current": ("PAT-ANTALL REGISTRERTE PRØVER PROSESS-OU", "PAT-PROSESS-CURRENT-OU"),
            "previous": ("PAT-ANTALL REGISTRERTE PRØVER PROSESS-OU", "PAT-PROSESS-PREVIOUS-OU"),
            "production": ("PAT-EGEN PRODUKSJON", "PAT-EGEN-PRODUKSJON-OU"), "macro": ("PAT-EGEN MAKRO", "PAT-EGEN-MAKRO-OU")}
        reports = {role: {"job_key": role, "fetch_report_id": fetch, "report_id": stem, "analysis_codes": []} for role, (fetch, stem) in roles.items()}
        definition.payload["statistics"] = reports
        definition = replace(definition, unit=validate_units({"units": {"lege": {"label": "Patologer", "profile": "lege", "analysis_codes": [], "reports": list(reports.values())}}})[0])
    database = MolStatDatabase(tmp_path / "sensitive/data/molstat.sqlite3")
    database.migrate()
    registry = configured_registry({key: definition})
    capability = registry.require(key).capability("statistics")
    system = MolStatSystem(
        database=database, archive=RawArchive(tmp_path / "sensitive"),
        statistics_processors={key: StatisticsProcessor(
            analysis_codes=analysis_codes("hemato"), database=database,
            report_ids={role: value["report_id"] for role, value in definition.payload["statistics"].items()},
        )}, backlog_processor=None,
        publisher={key: SharePointPublisher(PublicationPolicy(capability.allowed_columns, default_forbidden_patterns()))},
        sharepoint_root=tmp_path / "public", work_root=tmp_path / "sensitive/processed",
        statistics_fetch=lambda _: pytest.fail("Manual import must not access LVMS"),
        backlog_fetch=lambda: pytest.fail("Manual import must not access LVMS"),
        excel_search_path=tmp_path / "sensitive/Prøvesøk.xlsx", units=registry,
    )
    return system, definition


def test_single_workflow_file_imports_without_legacy_reports_or_roster(tmp_path):
    from molstat._statistics import patolog_flow as flow
    from molstat.manual_import import manual_import_roles
    system, definition = _system(tmp_path, "lege", workflow=True)
    system.statistics_processors["lege"] = StatisticsProcessor(analysis_codes=analysis_codes("lege"), profile="lege")
    assert manual_import_roles(definition, "statistics") == ("workflow",)
    row = dict.fromkeys(flow.DATE_FIELDS + ["Prøvenummer", "Lab", "Prosess", "Prioritet", "BeholderId", "BlokkId", "GlassId", "Glasstype", "Signert av", "Godkjent type"], "")
    row.update(Prøvenummer="PRIVATE-FLOW-1", Lab="OU-PAT-HIST-RA", Prosess="HEMATO", Ankomsttid="01.10.2026 08:00")
    source = tmp_path / "workflow.csv"
    with source.open("w", encoding="cp1252", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row), delimiter=";")
        writer.writeheader(); writer.writerow(row)
    original = source.read_bytes()
    result = process_manual_import(system, ManualImportPlan("lege", "statistics", date(2026, 10, 1), date(2026, 10, 7), {"workflow": source}), definition)
    assert result[0].error is None
    assert source.read_bytes() == original
    assert len(list((tmp_path / "sensitive/data/raw/statistics/lege").glob("*.csv"))) == 1
    assert "PRIVATE-FLOW-1" in (tmp_path / "sensitive/processed/lege/powerbi/Prøver.csv").read_text(encoding="utf-8-sig")
    expected = {name + ".csv" for name in ("Prøver", "Glass", "Signeringer", "Grupper", "Periode", "Leger", "Prioriteter")}
    public = tmp_path / "public/lege"
    assert {path.name for path in public.iterdir()} == expected
    for name in expected:
        assert (public / name).read_bytes() == (tmp_path / "sensitive/processed/lege/powerbi" / name).read_bytes()
    assert "PRIVATE-FLOW-1" in (public / "Prøver.csv").read_text(encoding="utf-8-sig")
    assert not (public / "source_audit.json").exists()


def _files(tmp_path, encoding="cp1252"):
    header = ["Sample ID", "Analyse", "Tidspunkt opprettet", "Tidspunkt analysebestilling",
              "Tidspunkt analyseresultat", "Tidspunkt godkjenning", "Materiale"]
    files = {}
    for role, code in (("antall", "CALR-OU"), ("resultater", "CALR-OU"), ("ekstraksjon", "EKSTRAKSJON-DNA-OU")):
        path = tmp_path / f"{role}.csv"
        with path.open("w", encoding=encoding, newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(header)
            writer.writerow(["PRIVATE-42", code, "01.10.2026 08:00", "01.10.2026 08:00",
                             "02.10.2026 09:00", "02.10.2026 10:00", "Bløtvev"])
        files[role] = path
    return files


def test_manual_statistics_uses_register_archive_publication_and_excel(tmp_path):
    system, definition = _system(tmp_path)
    files = _files(tmp_path)
    originals = {role: path.read_bytes() for role, path in files.items()}
    plan = ManualImportPlan("hemato", "statistics", date(2026, 10, 1), date(2026, 10, 7), files)

    results = process_manual_import(system, plan, definition)

    assert results[0].error is None
    assert results[0].summary["rows"] == 2
    assert all(path.read_bytes() == originals[role] for role, path in files.items())
    assert len(list((tmp_path / "sensitive/data/raw/statistics/hemato").glob("*.csv"))) == 3
    assert (tmp_path / "sensitive/Prøvesøk.xlsx").is_file()
    public = (tmp_path / "public/hemato/resultater.csv").read_text(encoding="utf-8-sig")
    assert "PRIVATE-42" not in public and "M-000001" in public
    with system.database._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 1


def test_invalid_last_file_does_not_poison_archive_or_import_database(tmp_path):
    system, definition = _system(tmp_path)
    files = _files(tmp_path)
    files["ekstraksjon"].write_text("wrong;header\nPRIVATE-INVALID;garbage\n")
    plan = ManualImportPlan("hemato", "statistics", date(2026, 10, 1), date(2026, 10, 7), files)

    with pytest.raises(ManualImportError) as failure:
        process_manual_import(system, plan, definition)

    assert "PRIVATE-INVALID" not in str(failure.value)
    assert not list((tmp_path / "sensitive/data/raw").rglob("*.csv"))
    with system.database._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 0
    assert all(path.is_file() for path in files.values())
    assert not list((tmp_path / "sensitive/work/manual-import").glob("*"))


def test_utf8_csv_is_normalized_without_modifying_original(tmp_path):
    system, definition = _system(tmp_path)
    files = _files(tmp_path, "utf-8-sig")
    plan = ManualImportPlan("hemato", "statistics", date(2026, 10, 1), date(2026, 10, 7), files)

    process_manual_import(system, plan, definition)

    assert files["resultater"].read_bytes().startswith(b"\xef\xbb\xbf")
    archive = next((tmp_path / "sensitive/data/raw/statistics/hemato").glob("*RESULTATER*"))
    assert "Bløtvev" in archive.read_text(encoding="cp1252")


@pytest.mark.parametrize("alter", ["missing", "duplicate", "future", "reversed"])
def test_bad_plan_is_rejected_before_creating_files(tmp_path, alter):
    system, definition = _system(tmp_path)
    files = _files(tmp_path)
    start, end = date(2026, 10, 1), date(2026, 10, 7)
    if alter == "missing":
        files.pop("resultater")
    if alter == "duplicate":
        files["resultater"] = files["antall"]
    if alter == "future":
        end = date(2999, 1, 1)
    if alter == "reversed":
        start, end = end, start
    plan = ManualImportPlan("hemato", "statistics", start, end, files)
    with pytest.raises(ManualImportError):
        process_manual_import(system, plan, definition)
    assert not list((tmp_path / "sensitive/data/raw").rglob("*.csv"))


@pytest.mark.parametrize("key", ["flow", "fish", "pre"])
def test_manual_specialized_units_process_and_update_registry(tmp_path, key):
    system, definition = _system(tmp_path, key)
    system.statistics_processors[key] = StatisticsProcessor(
        analysis_codes=analysis_codes(key), profile=key, database=system.database,
        report_ids={role: value["report_id"] for role, value in definition.payload["statistics"].items()},
    )
    files = _files(tmp_path)
    files = {role: files[role] for role in definition.payload["statistics"]}
    code = definition.unit.analysis_codes[0]
    for path in files.values():
        path.write_text(path.read_text(encoding="cp1252").replace("CALR-OU", code), encoding="cp1252")
    plan = ManualImportPlan(key, "statistics", date(2026, 10, 1), date(2026, 10, 7), files)

    result = process_manual_import(system, plan, definition)

    assert result[0].summary["rows"] >= 1
    assert (tmp_path / f"public/{key}/resultater.csv").is_file()
    with system.database._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 1
    assert (tmp_path / "sensitive/Prøvesøk.xlsx").is_file()


def test_manual_fish_accepts_multiline_lvms_comment_and_preserves_all_result_dates(tmp_path):
    system, definition = _system(tmp_path, "fish")
    code = "FISH-ALKBA-OU"
    system.statistics_processors["fish"] = StatisticsProcessor(
        analysis_codes=analysis_codes("fish"), profile="fish", database=system.database,
        report_ids={role: value["report_id"] for role, value in definition.payload["statistics"].items()},
    )
    files = {role: path for role, path in _files(tmp_path).items() if role in ("antall", "resultater")}
    for path in files.values():
        path.write_text(path.read_text("cp1252").replace("CALR-OU", code), encoding="cp1252")
    files["resultater"].write_text(
        'Sample ID;Analyse;Ekstern analysekommentar;Tidspunkt opprettet;Tidspunkt analysebestilling;Tidspunkt analyseresultat;Materiale\n'
        f'PRIVATE-42;{code};"PRIVATE "signal" text\ncontinuation";01.10.2026 08:00;01.10.2026 08:00;03.10.2026 08:00;PAK\n',
        encoding="cp1252", newline="",
    )
    original = files["resultater"].read_bytes()

    result = process_manual_import(system, ManualImportPlan("fish", "statistics", date(2026, 10, 1),
                                   date(2026, 10, 7), files), definition)

    assert result[0].summary["rows"] == 2
    assert files["resultater"].read_bytes() == original
    output = (tmp_path / "public/fish/resultater.csv").read_text("utf-8-sig")
    rows = list(csv.DictReader(output.splitlines(), delimiter=";"))
    assert len(rows) == 1 and rows[0]["Svartid dager"] == "2.0000000000"
    assert "PRIVATE" not in output


@pytest.mark.parametrize("role", ["antall", "resultater"])
@pytest.mark.parametrize("created", ["", "01.01.2020 08:00"])
def test_fish_manual_period_uses_analysis_order_not_sample_creation(tmp_path, role, created):
    from molstat.manual_import import _validate_statistics_csv
    from molstat.lvms.report import ReportRequest
    source = tmp_path / "fish.csv"
    source.write_text(
        'Sample ID;Analyse;Tidspunkt opprettet;Tidspunkt analysebestilling;Tidspunkt analyseresultat\n'
        f'SYNTHETIC;FISH-ALKBA-OU;{created};01.10.2026 08:00;03.10.2026 08:00\n', encoding="cp1252")
    before = source.read_bytes()
    request = ReportRequest("statistics", "fish", "REPORT", date(2026, 10, 1), date(2026, 10, 7))
    _validate_statistics_csv(source, "fish", role, request)
    assert source.read_bytes() == before


@pytest.mark.parametrize("role", ["antall", "resultater"])
def test_fish_manual_rejects_order_outside_period_even_if_sample_created_inside(tmp_path, role):
    from molstat.manual_import import _validate_statistics_csv
    from molstat.lvms.report import ReportRequest
    source = tmp_path / "fish.csv"
    source.write_text(
        'Sample ID;Analyse;Tidspunkt opprettet;Tidspunkt analysebestilling;Tidspunkt analyseresultat\n'
        'SYNTHETIC;FISH-ALKBA-OU;01.10.2026 08:00;30.09.2026 08:00;03.10.2026 08:00\n', encoding="cp1252")
    request = ReportRequest("statistics", "fish", "REPORT", date(2026, 10, 1), date(2026, 10, 7))
    with pytest.raises(ManualImportError, match="periode"):
        _validate_statistics_csv(source, "fish", role, request)


def test_manual_backlog_preserves_original_and_uses_normal_snapshot(tmp_path):
    system, definition = _system(tmp_path)
    payload = definition.payload["backlog"]
    raw = payload["columns"]
    contract = CsvContract(raw["delimiter"], raw["encoding"], raw["columns"], tuple(raw["completed_values"]))
    system.backlog_processor = BacklogProcessor(validate_app_config(payload["analyses"]), contract)
    capability = system.units.require("hemato").capability("backlog")
    system.backlog_publisher = SharePointPublisher(PublicationPolicy(capability.allowed_columns, default_forbidden_patterns()))
    source = tmp_path / "backlog.csv"
    source.write_text("SampleID;Analyse;Tidspunkt analysebestilling;Status analyse\n"
                      "PRIVATE-REST;IGH-OU;01.10.2026 08:00;Initial\n", encoding="cp1252")
    original = source.read_bytes()
    plan = ManualImportPlan("hemato", "backlog", date(2024, 1, 1), date.today(), {"backlog": source})

    result = process_manual_import(system, plan, definition)

    assert result[0].summary["rows"] == 1
    assert source.read_bytes() == original
    assert (tmp_path / "public/Prøveflyt/restansehistorikk_hemato.csv").is_file()
    assert len(list((tmp_path / "sensitive/data/raw/backlog").rglob("*.csv"))) == 1


def test_partial_backlog_period_is_rejected(tmp_path):
    system, definition = _system(tmp_path)
    source = tmp_path / "backlog.csv"
    source.write_text("anything")
    plan = ManualImportPlan("hemato", "backlog", date(2026, 10, 1), date.today(), {"backlog": source})
    with pytest.raises(ManualImportError, match="hele uttrekket"):
        process_manual_import(system, plan, definition)


def test_statistics_file_outside_selected_period_is_rejected_before_archive(tmp_path):
    system, definition = _system(tmp_path)
    files = _files(tmp_path)
    files["antall"].write_text(
        files["antall"].read_text(encoding="cp1252").replace("01.10.2026", "01.01.2025"),
        encoding="cp1252",
    )
    plan = ManualImportPlan("hemato", "statistics", date(2026, 10, 1), date(2026, 10, 7), files)

    with pytest.raises(ManualImportError, match="periode"):
        process_manual_import(system, plan, definition)

    assert not list((tmp_path / "sensitive/data/raw").rglob("*.csv"))


@pytest.mark.parametrize("damage", ["extra_cell", "missing_cell", "duplicate_header", "timestamp"])
def test_malformed_statistics_csv_does_not_change_archive_or_database(tmp_path, damage):
    system, definition = _system(tmp_path)
    files = _files(tmp_path)
    path = files["resultater"]
    with path.open(encoding="cp1252", newline="") as stream:
        rows = list(csv.reader(stream, delimiter=";"))
    if damage == "extra_cell":
        rows[1].append("PRIVATE-INVALID")
    elif damage == "missing_cell":
        rows[1].pop()
    elif damage == "duplicate_header":
        rows[0][-1] = rows[0][0]
    else:
        rows[1][3] = "wrong date"
    with path.open("w", encoding="cp1252", newline="") as stream:
        csv.writer(stream, delimiter=";").writerows(rows)
    plan = ManualImportPlan("hemato", "statistics", date(2026, 10, 1), date(2026, 10, 7), files)

    with pytest.raises(ManualImportError) as failure:
        process_manual_import(system, plan, definition)

    assert "PRIVATE-INVALID" not in str(failure.value)
    assert not list((tmp_path / "sensitive/data/raw").rglob("*.csv"))
    with system.database._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 0


def test_invalid_older_archive_is_detected_before_manual_files_enter_history(tmp_path):
    system, definition = _system(tmp_path)
    root = tmp_path / "sensitive/data/raw/statistics/hemato"
    root.mkdir(parents=True)
    old = root / "PAT-DIT-ANTALL-OU__2026-09-01__2026-09-30.csv"
    old.write_text("bad;header\nPRIVATE-OLD;invalid\n", encoding="cp1252")
    files = _files(tmp_path)
    plan = ManualImportPlan("hemato", "statistics", date(2026, 10, 1), date(2026, 10, 7), files)

    with pytest.raises(ManualImportError, match="behandles"):
        process_manual_import(system, plan, definition)

    assert list(root.iterdir()) == [old]
    assert "PRIVATE-OLD" in old.read_text(encoding="cp1252")
    with system.database._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 0


def test_manual_replacement_validates_new_revision_for_same_interval(tmp_path):
    system, definition = _system(tmp_path)
    root = tmp_path / "sensitive/data/raw/statistics/hemato"
    root.mkdir(parents=True)
    for revision in ("", "__r2"):
        (root / f"PAT-DIT-ANTALL-OU__2026-10-01__2026-10-07{revision}.csv").write_text(
            "bad;header\nPRIVATE-OLD;invalid\n", encoding="cp1252"
        )
    plan = ManualImportPlan("hemato", "statistics", date(2026, 10, 1), date(2026, 10, 7), _files(tmp_path))

    result = process_manual_import(system, plan, definition)

    assert result[0].summary["rows"] == 2
    assert (root / "PAT-DIT-ANTALL-OU__2026-10-01__2026-10-07__r3.csv").is_file()
