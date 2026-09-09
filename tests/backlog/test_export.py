import csv
import json
from pathlib import Path

from molstat._backlog.export import (
    BACKLOG_PUBLIC_COLUMNS,
    export_backlog_history,
)
from molstat.database import MolStatDatabase


EXPECTED_COLUMNS = (
    "Observert_tidspunkt",
    "Enhet",
    "Materiale",
    "Analyse",
    "Nukleinsyre",
    "Analysegruppe_kode",
    "Analysegruppe",
    "Tidspunkt.prøvetaking",
    "Tidspunkt.ankomst",
    "Tidspunkt.analysebestilling",
    "Prioritet.analyse",
    "Prioritet.rekvisisjon",
    "Status.analyse",
    "Status.prelgruppe",
    "Restansestatus",
    "Svarfrist",
    "Analyseresultat",
    "Ekstern.analysekommentar",
    "Klassifikatorversjon",
)


def _insert_detail(
    database: MolStatDatabase,
    observed_at: str,
    unit: str,
    code: str,
) -> None:
    with database._connect() as connection:
        connection.execute(
            """
            INSERT INTO backlog_detail_snapshot(
             observed_at, unit_key, row_number, material, analysis_code,
             nucleic_acid, report_group, analysis_group_code,
             analysis_group_label, collected_at, arrived_at, ordered_at,
             analysis_priority, request_priority, analysis_status,
             preliminary_status, workflow_stage, response_deadline,
             analysis_result, external_analysis_comment, classifier_version,
             source_fingerprint
            ) VALUES
            (?, ?, 1, 'Blod', ?, 'DNA', 'lymfom', 'KLONALITET',
             'Klonalitet', '2026-09-06T07:30:00', '2026-09-06T08:00:00',
             '2026-09-06T08:15:00', 'Høy', 'Vanlig', 'Initial', 'Initial',
             'ready', '14', 'Påvist – behold æøå', 'Ordrett kommentar',
             2, 'internal-secret-fingerprint')
            """,
            (
                observed_at,
                unit,
                code,
            ),
        )


def test_export_is_deterministic_and_contains_only_public_columns(
    tmp_path: Path,
) -> None:
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    _insert_detail(
        database,
        "2026-09-07T11:00:00",
        "hemato",
        "B",
    )
    _insert_detail(
        database,
        "2026-09-07T10:00:00",
        "hemato",
        "A",
    )
    _insert_detail(
        database,
        "2026-09-07T10:00:00",
        "solide",
        "SKAL-IKKE-MED",
    )
    destination = tmp_path / "export" / "restansehistorikk_hemato.csv"

    exported = export_backlog_history(database, destination, unit_key="hemato")

    assert exported == 2
    assert BACKLOG_PUBLIC_COLUMNS == EXPECTED_COLUMNS
    raw = destination.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    assert text.splitlines()[0] == ";".join(EXPECTED_COLUMNS)
    assert "internal-secret-fingerprint" not in text
    with destination.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter=";"))
    assert [row["Analyse"] for row in rows] == ["A", "B"]
    assert "Rapportgruppe" not in rows[0]
    assert rows[0]["Analysegruppe"] == "Klonalitet"
    assert rows[0]["Svarfrist"] == "14"
    assert rows[0]["Analyseresultat"] == "Påvist – behold æøå"
    assert rows[0]["Ekstern.analysekommentar"] == "Ordrett kommentar"
    serialized = repr(rows)
    for forbidden in (
        "SampleID",
        "PID",
        "WorkItem",
        "internal-secret-fingerprint",
        "SKAL-IKKE-MED",
    ):
        assert forbidden not in serialized


def test_detail_sample_matches_public_contract_and_hourly_history() -> None:
    root = Path(__file__).parents[2]
    sample = root / "docs" / "powerbi" / "sample_restansehistorikk.csv"

    with sample.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        rows = list(reader)

    assert tuple(reader.fieldnames or ()) == BACKLOG_PUBLIC_COLUMNS
    assert rows
    groups_by_time: dict[str, set[str]] = {}
    for row in rows:
        groups_by_time.setdefault(row["Observert_tidspunkt"], set()).add(
            row["Analysegruppe_kode"]
        )
    assert len({frozenset(groups) for groups in groups_by_time.values()}) == 1
    assert all(groups == {"KLONALITET"} for groups in groups_by_time.values())
    assert {row["Analyse"] for row in rows} == {"IGH-VDJ-OU", "TRG-OU"}
    assert any("æøå" in row["Analyseresultat"] for row in rows)
    serialized = repr(rows).casefold()
    for forbidden in (
        "sampleid",
        "pid",
        "workitem",
        "fingerprint",
        "pasient",
    ):
        assert forbidden not in serialized


def test_power_bi_tmdl_uses_portable_ascii_ids_and_export_number_culture() -> None:
    root = Path(__file__).parents[2]
    definition = root / "docs" / "powerbi" / "MolStatProveflyt.SemanticModel" / "definition"
    fact = (definition / "tables" / "FactRestanse.tmdl").read_text(
        encoding="utf-8"
    )
    expressions = (definition / "expressions.tmdl").read_text(encoding="utf-8")

    assert "expression ProveflytFil" in expressions
    assert "column Paa_vei" in fact
    assert '"en-US"' in fact
    assert "FactRestanse[På_vei]" not in fact
    assert "PrøveflytFil" not in expressions


def test_power_bi_report_starter_has_expected_pages_and_model_reference() -> None:
    root = Path(__file__).parents[2]
    project = root / "docs" / "powerbi" / "MolStatProveflyt.Report"
    report = project / "MolStatProveflyt.Report"
    pages = json.loads(
        (report / "definition" / "pages" / "pages.json").read_text(
            encoding="utf-8"
        )
    )
    reference = json.loads((report / "definition.pbir").read_text(encoding="utf-8"))

    assert (project / "MolStatProveflyt.pbip").is_file()
    semantic_model = project.parent / "MolStatProveflyt.SemanticModel"
    model_manifest = json.loads(
        (semantic_model / "definition.pbism").read_text(encoding="utf-8")
    )
    assert model_manifest["version"] == "4.0"
    assert (semantic_model / ".platform").is_file()
    assert pages["pageOrder"] == ["proveflyt-naa", "utvikling", "analysegruppe"]
    assert pages["activePageName"] == "proveflyt-naa"
    assert reference["datasetReference"]["byPath"]["path"] == (
        "../../MolStatProveflyt.SemanticModel"
    )
    assert (report / reference["datasetReference"]["byPath"]["path"]).resolve().is_dir()
