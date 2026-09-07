import csv
from pathlib import Path

from molstat._backlog.export import (
    BACKLOG_PUBLIC_COLUMNS,
    export_backlog_history,
)
from molstat.database import MolStatDatabase


EXPECTED_COLUMNS = (
    "Observert_tidspunkt",
    "Enhet",
    "Analysegruppe_kode",
    "Analysegruppe",
    "Klar",
    "Mangler_godkjenning",
    "På_vei",
    "Over_frist",
    "Median_klare_timer",
    "Eldste_klare_timer",
    "Alvorlighetsgrad",
    "Ugyldige_rader",
    "Ekskluderte_rader",
    "Kilde_fersk",
    "Klassifikatorversjon",
)


def _insert_snapshot(
    database: MolStatDatabase,
    observed_at: str,
    unit: str,
    code: str,
    *,
    median_hours: float | None,
    oldest_hours: float | None,
    source_is_fresh: int,
) -> None:
    with database._connect() as connection:
        connection.execute(
            """
            INSERT INTO backlog_snapshot VALUES
            (?, ?, ?, ?, 2, 1, 3, 1, ?, ?, 'WARNING', 4, 5, ?, 2,
             'internal-secret-fingerprint')
            """,
            (
                observed_at,
                unit,
                code,
                f"Analyse {code}",
                median_hours,
                oldest_hours,
                source_is_fresh,
            ),
        )


def test_export_is_deterministic_and_contains_only_public_columns(
    tmp_path: Path,
) -> None:
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()
    _insert_snapshot(
        database,
        "2026-09-07T11:00:00",
        "hemato",
        "B",
        median_hours=None,
        oldest_hours=None,
        source_is_fresh=0,
    )
    _insert_snapshot(
        database,
        "2026-09-07T10:00:00",
        "hemato",
        "A",
        median_hours=7.5,
        oldest_hours=12.0,
        source_is_fresh=1,
    )
    destination = tmp_path / "export" / "restansehistorikk.csv"

    exported = export_backlog_history(database, destination)

    assert exported == 2
    assert BACKLOG_PUBLIC_COLUMNS == EXPECTED_COLUMNS
    raw = destination.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert text.splitlines()[0] == ";".join(EXPECTED_COLUMNS)
    assert "internal-secret-fingerprint" not in text
    with destination.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter=";"))
    assert [row["Analysegruppe_kode"] for row in rows] == ["A", "B"]
    assert rows[0]["Median_klare_timer"] == "7.5"
    assert rows[0]["Eldste_klare_timer"] == "12.0"
    assert rows[0]["Kilde_fersk"] == "Ja"
    assert rows[1]["Median_klare_timer"] == ""
    assert rows[1]["Eldste_klare_timer"] == ""
    assert rows[1]["Kilde_fersk"] == "Nei"
