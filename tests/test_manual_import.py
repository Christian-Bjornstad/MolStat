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
from molstat.unit_settings import default_unit_file, load_unit_file
from molstat._statistics.specialized_lookup import default_lookup_path
from molstat.backlog import BacklogProcessor, CsvContract
from molstat._backlog.config import validate_app_config
import xlsxwriter


def _system(tmp_path, key="hemato"):
    lookup = tmp_path / "lookup.xlsx"
    with xlsxwriter.Workbook(lookup) as workbook:
        sheet = workbook.add_worksheet("Lookup")
        sheet.write_row(0, 0, ["Analyse", "Nukleinsyre", "Rapportgruppe", "Svarfrist"])
        sheet.write_row(1, 0, ["CALR-OU", "DNA", "MPN", "21"])
    definition = load_unit_file(default_unit_file(key))
    database = MolStatDatabase(tmp_path / "sensitive/data/molstat.sqlite3")
    database.migrate()
    registry = configured_registry({key: definition})
    capability = registry.require(key).capability("statistics")
    system = MolStatSystem(
        database=database, archive=RawArchive(tmp_path / "sensitive"),
        statistics_processors={key: StatisticsProcessor(
            lookup, database=database,
            report_ids={role: value["report_id"] for role, value in definition.payload["statistics"].items()},
        )}, backlog_processor=None,
        publisher={key: SharePointPublisher(PublicationPolicy(capability.allowed_columns, default_forbidden_patterns()))},
        sharepoint_root=tmp_path / "public", work_root=tmp_path / "sensitive/processed",
        statistics_fetch=lambda _: pytest.fail("Manual import must not access LVMS"),
        backlog_fetch=lambda: pytest.fail("Manual import must not access LVMS"),
        excel_search_path=tmp_path / "sensitive/Prøvesøk.xlsx", units=registry,
    )
    return system, definition


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
    assert len(list((tmp_path / "sensitive/raw/statistics/hemato").glob("*.csv"))) == 3
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
    assert not (tmp_path / "sensitive/raw").exists()
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
    archive = next((tmp_path / "sensitive/raw/statistics/hemato").glob("*RESULTATER*"))
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
    assert not (tmp_path / "sensitive/raw").exists()


@pytest.mark.parametrize("key", ["flow", "fish", "pre"])
def test_manual_specialized_units_process_and_update_registry(tmp_path, key):
    system, definition = _system(tmp_path, key)
    system.statistics_processors[key] = StatisticsProcessor(
        default_lookup_path(key), profile=key, database=system.database,
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
    assert not (tmp_path / "sensitive/raw/backlog").exists()


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

    assert not (tmp_path / "sensitive/raw").exists()


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
    assert not (tmp_path / "sensitive/raw").exists()
    with system.database._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 0


def test_invalid_older_archive_is_detected_before_manual_files_enter_history(tmp_path):
    system, definition = _system(tmp_path)
    root = tmp_path / "sensitive/raw/statistics/hemato"
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
    root = tmp_path / "sensitive/raw/statistics/hemato"
    root.mkdir(parents=True)
    for revision in ("", "__r2"):
        (root / f"PAT-DIT-ANTALL-OU__2026-10-01__2026-10-07{revision}.csv").write_text(
            "bad;header\nPRIVATE-OLD;invalid\n", encoding="cp1252"
        )
    plan = ManualImportPlan("hemato", "statistics", date(2026, 10, 1), date(2026, 10, 7), _files(tmp_path))

    result = process_manual_import(system, plan, definition)

    assert result[0].summary["rows"] == 2
    assert (root / "PAT-DIT-ANTALL-OU__2026-10-01__2026-10-07__r3.csv").is_file()


def _pathology_files(tmp_path):
    files = {}
    for role in ("current", "previous", "production_current", "production_previous",
                 "macro_current", "macro_previous"):
        previous = role == "previous" or role.endswith("_previous")
        moment = "02.09.2026" if previous else "02.10.2026"
        path = tmp_path / f"{role}.csv"
        with path.open("w", encoding="cp1252", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            if role in {"current", "previous"}:
                writer.writerow(["Totalt antall registrerte rekvisisjoner"])
                writer.writerow(["Profil", "Lab", "s_w_labprocess", "Distinct_SampleId",
                                 "Distinct_Ant. blokker", "Distinct_Ant. glass"])
                writer.writerow(["HISTO", "OU-PAT-SPES-RA", "HEMATO", "2", "3", "4"])
            elif role.startswith("production"):
                writer.writerow(["Produksjon"])
                writer.writerow(["Antall prøver", "Godkj. type", "Profil", "Prosess", "Godkjent av",
                                 "Ferdig farget", "Godkj. når"])
                writer.writerow(["PRIVATE-PAT-PREV" if previous else "PRIVATE-PAT-CURRENT",
                                 "Histologi", "HISTO", "HEMATO", "ESP", moment + " 08:00", moment + " 10:00"])
            else:
                writer.writerow(["Makro"])
                writer.writerow(["SampleID", "Prioritet", "Prosess", "Makro når", "Makro av"])
                writer.writerow(["PRIVATE-PAT-PREV" if previous else "PRIVATE-PAT-CURRENT",
                                 "Standard", "HEMATO", moment + " 07:00", "ESP"])
        files[role] = path
    return files


def test_all_six_pathology_files_publish_aggregates_and_keep_doctor_facts_private(tmp_path):
    from molstat._statistics.lege_lookup import default_lege_lookup_path

    system, definition = _system(tmp_path, "lege")
    system.statistics_processors["lege"] = StatisticsProcessor(default_lege_lookup_path(), profile="lege", database=system.database)
    files = _pathology_files(tmp_path)
    originals = {role: path.read_bytes() for role, path in files.items()}
    plan = ManualImportPlan("lege", "statistics", date(2026, 10, 1), date(2026, 10, 7), files)

    result = process_manual_import(system, plan, definition)

    assert result[0].summary["rows"] >= 2
    assert all(path.read_bytes() == originals[role] for role, path in files.items())
    assert len(list((tmp_path / "sensitive/raw/statistics/lege").glob("*.csv"))) == 6
    public = (tmp_path / "public/lege/prosess.csv").read_text(encoding="utf-8-sig")
    assert "2026-09-01" in public and "2026-10-01" in public
    assert "PRIVATE-PAT" not in public and "ESP" not in public
    private = (tmp_path / "sensitive/processed/lege/powerbi/FactPatologRolle.csv").read_text(encoding="utf-8-sig")
    assert "PRIVATE-PAT-PREV" in private and "PRIVATE-PAT-CURRENT" in private
    assert (tmp_path / "sensitive/Prøvesøk.xlsx").is_file()


def test_pathology_previous_month_file_cannot_be_mislabeled_as_current(tmp_path):
    from molstat._statistics.lege_lookup import default_lege_lookup_path

    system, definition = _system(tmp_path, "lege")
    system.statistics_processors["lege"] = StatisticsProcessor(default_lege_lookup_path(), profile="lege", database=system.database)
    files = _pathology_files(tmp_path)
    path = files["production_previous"]
    path.write_text(path.read_text(encoding="cp1252").replace("02.09.2026", "02.10.2026"), encoding="cp1252")
    plan = ManualImportPlan("lege", "statistics", date(2026, 10, 1), date(2026, 10, 7), files)

    with pytest.raises(ManualImportError, match="periode"):
        process_manual_import(system, plan, definition)

    assert not (tmp_path / "sensitive/raw").exists()


@pytest.mark.parametrize("damage", ["empty_lab", "empty_profile", "extra_cell", "missing_cell", "duplicate_header"])
def test_malformed_pathology_process_row_cannot_silently_replace_month_with_zero(tmp_path, damage):
    from molstat._statistics.lege_lookup import default_lege_lookup_path

    system, definition = _system(tmp_path, "lege")
    system.statistics_processors["lege"] = StatisticsProcessor(default_lege_lookup_path(), profile="lege", database=system.database)
    files = _pathology_files(tmp_path)
    path = files["current"]
    with path.open(encoding="cp1252", newline="") as stream:
        rows = list(csv.reader(stream, delimiter=";"))
    if damage == "empty_lab":
        rows[2][1] = ""
    elif damage == "empty_profile":
        rows[2][0] = ""
    elif damage == "extra_cell":
        rows[2].append("PRIVATE-INVALID")
    elif damage == "missing_cell":
        rows[2].pop()
    else:
        rows[1][-1] = rows[1][0]
    with path.open("w", encoding="cp1252", newline="") as stream:
        csv.writer(stream, delimiter=";").writerows(rows)
    plan = ManualImportPlan("lege", "statistics", date(2026, 10, 1), date(2026, 10, 7), files)

    with pytest.raises(ManualImportError) as failure:
        process_manual_import(system, plan, definition)

    assert "PRIVATE-INVALID" not in str(failure.value)
    assert not (tmp_path / "sensitive/raw").exists()


@pytest.mark.parametrize("role", ["production_current", "macro_current"])
@pytest.mark.parametrize("damage", ["missing_cell", "duplicate_header", "empty_sample", "empty_user"])
def test_malformed_pathology_doctor_rows_are_rejected_before_archiving(tmp_path, role, damage):
    from molstat._statistics.lege_lookup import default_lege_lookup_path

    system, definition = _system(tmp_path, "lege")
    system.statistics_processors["lege"] = StatisticsProcessor(default_lege_lookup_path(), profile="lege", database=system.database)
    files = _pathology_files(tmp_path)
    path = files[role]
    with path.open(encoding="cp1252", newline="") as stream:
        rows = list(csv.reader(stream, delimiter=";"))
    user_column = "Godkjent av" if role.startswith("production") else "Makro av"
    user_index = rows[1].index(user_column)
    # User is a required field even when it is the final column in a custom
    # LVMS export. DictReader previously turned a missing cell into None.
    for row in rows[1:]:
        row.append(row.pop(user_index))
    if damage == "missing_cell":
        rows[2].pop()
    elif damage == "duplicate_header":
        rows[1].append(user_column)
        rows[2].append("ESP")
    elif damage == "empty_sample":
        rows[2][0] = ""
    else:
        rows[2][-1] = ""
    with path.open("w", encoding="cp1252", newline="") as stream:
        csv.writer(stream, delimiter=";").writerows(rows)
    originals = {name: source.read_bytes() for name, source in files.items()}
    plan = ManualImportPlan("lege", "statistics", date(2026, 10, 1), date(2026, 10, 7), files)

    with pytest.raises(ManualImportError):
        process_manual_import(system, plan, definition)

    assert all(source.read_bytes() == originals[name] for name, source in files.items())
    assert not (tmp_path / "sensitive/raw").exists()
    assert not (tmp_path / "public").exists()


def test_pathology_optional_stain_date_and_unknown_nonempty_users_remain_valid(tmp_path):
    from molstat._statistics.lege_lookup import default_lege_lookup_path

    system, definition = _system(tmp_path, "lege")
    system.statistics_processors["lege"] = StatisticsProcessor(default_lege_lookup_path(), profile="lege", database=system.database)
    files = _pathology_files(tmp_path)
    for role in ("production_current", "production_previous", "macro_current", "macro_previous"):
        path = files[role]
        with path.open(encoding="cp1252", newline="") as stream:
            rows = list(csv.reader(stream, delimiter=";"))
        user_column = "Godkjent av" if role.startswith("production") else "Makro av"
        rows[2][rows[1].index(user_column)] = "UNKNOWN-NONEMPTY"
        if role.startswith("production"):
            rows[2][rows[1].index("Ferdig farget")] = ""
        with path.open("w", encoding="cp1252", newline="") as stream:
            csv.writer(stream, delimiter=";").writerows(rows)
    plan = ManualImportPlan("lege", "statistics", date(2026, 10, 1), date(2026, 10, 7), files)

    result = process_manual_import(system, plan, definition)

    assert result[0].error is None
    assert len(list((tmp_path / "sensitive/raw/statistics/lege").glob("*.csv"))) == 6
