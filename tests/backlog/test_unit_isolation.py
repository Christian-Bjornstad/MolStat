from dataclasses import replace
from datetime import datetime
import sqlite3

from molstat.backlog import BacklogProcessor, UnitConfig
from molstat.database import MolStatDatabase
from .test_processor import _config, _contract, _write_snapshot


def test_same_occurrence_can_be_current_in_two_units(tmp_path):
    database = MolStatDatabase(tmp_path / "db.sqlite3")
    database.migrate()
    source = tmp_path / "source.csv"
    _write_snapshot(source, "SYNTHETIC")
    now = datetime(2026, 9, 17, 10)
    hemato = BacklogProcessor(_config(), _contract(), now=lambda: now)
    solide = BacklogProcessor(replace(_config(), unit=UnitConfig("solide", "Solide")), _contract(), now=lambda: now)
    hemato.import_snapshot(source, database)
    solide.import_snapshot(source, database)
    with database._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM backlog_current").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM backlog_sample").fetchone()[0] == 2
    assert hemato.public_snapshot(database, now)["totals"]["ready"] == 1
    assert solide.public_snapshot(database, now)["totals"]["ready"] == 1


def test_v6_board_rows_are_preserved_as_hemato(tmp_path):
    path = tmp_path / "db.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE schema_info(version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_info VALUES (6)")
        connection.execute("CREATE TABLE backlog_sample(sample_key TEXT, analysis_group TEXT, ordered_at TEXT, arrived_at TEXT, workflow_stage TEXT, observed_at TEXT, PRIMARY KEY(sample_key, analysis_group))")
        connection.execute("INSERT INTO backlog_sample VALUES ('SYNTHETIC','CALR','2026-09-17',NULL,'ready','2026-09-17')")
    database = MolStatDatabase(path)
    database.migrate()
    with database._connect() as connection:
        assert connection.execute("SELECT unit_key,sample_key FROM backlog_sample").fetchall() == [("hemato", "SYNTHETIC")]
