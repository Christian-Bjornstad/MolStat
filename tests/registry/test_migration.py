from pathlib import Path
import sqlite3

import pytest

from molstat.database import MolStatDatabase


def test_v4_migration_preserves_existing_backlog_rows(tmp_path: Path) -> None:
    path = tmp_path / "molstat.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE schema_info (version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_info VALUES (4)")
        connection.execute(
            """
            CREATE TABLE backlog_sample (
                sample_key TEXT NOT NULL,
                analysis_group TEXT NOT NULL,
                ordered_at TEXT NOT NULL,
                arrived_at TEXT,
                workflow_stage TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                PRIMARY KEY (sample_key, analysis_group)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO backlog_sample VALUES
            ('preserved-sample', 'CALR', '2026-09-10T08:00:00', NULL,
             'ready', '2026-09-10T09:00:00')
            """
        )

    database = MolStatDatabase(path)
    database.migrate()

    assert database.schema_version() == 5
    with database._connect() as connection:
        row = connection.execute(
            "SELECT sample_key, analysis_group FROM backlog_sample"
        ).fetchone()
    assert row == ("preserved-sample", "CALR")


def test_registry_schema_enforces_foreign_keys_and_unique_identifiers(
    tmp_path: Path,
) -> None:
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()

    with database._connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        connection.execute(
            """
            INSERT INTO sample(molstat_key, first_seen_at, last_seen_at)
            VALUES ('MS-000000001', '2026-09-10T08:00:00', '2026-09-10T08:00:00')
            """
        )
        sample_id = connection.execute(
            "SELECT id FROM sample WHERE molstat_key = 'MS-000000001'"
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO sample_identifier(
                sample_id, source_system, identifier_type,
                identifier_value, normalized_value
            ) VALUES (?, 'LVMS', 'sample_number', '00123', '00123')
            """,
            (sample_id,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO sample_identifier(
                    sample_id, source_system, identifier_type,
                    identifier_value, normalized_value
                ) VALUES (?, 'LVMS', 'sample_number', '00123', '00123')
                """,
                (sample_id,),
            )


def test_registry_schema_has_search_indexes(tmp_path: Path) -> None:
    database = MolStatDatabase(tmp_path / "molstat.sqlite3")
    database.migrate()

    with database._connect() as connection:
        indexes = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }

    assert {
        "idx_sample_identifier_value",
        "idx_analysis_occurrence_sample",
        "idx_analysis_occurrence_code",
        "idx_analysis_occurrence_ordered",
        "idx_source_observation_kind",
    } <= indexes


def test_unknown_schema_version_is_rejected_without_rewrite(tmp_path: Path) -> None:
    path = tmp_path / "molstat.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE schema_info (version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_info VALUES (99)")

    with pytest.raises(RuntimeError, match="Ukjent databaseskjema: 99"):
        MolStatDatabase(path).migrate()

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version FROM schema_info").fetchone() == (99,)
