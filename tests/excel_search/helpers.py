from datetime import date, datetime
from pathlib import Path

from molstat.database import MolStatDatabase
from molstat.registry import (
    OccurrenceEventInput,
    OccurrenceInput,
    RegistryImportItem,
    SampleRegistry,
)


def populated_database(path: Path) -> MolStatDatabase:
    database = MolStatDatabase(path)
    database.migrate()
    registry = SampleRegistry(database)
    items = (
        RegistryImportItem(
            OccurrenceInput(
                source_system="LVMS",
                sample_number="00123456789012345678",
                analysis_code="CALR-OU",
                ordered_at=datetime(2026, 9, 8, 8, 0),
                source_occurrence_id="WORK-1",
                source_kind="statistics_answered",
            ),
            (
                OccurrenceEventInput("resulted", datetime(2026, 9, 9, 9, 0)),
                OccurrenceEventInput("approved", datetime(2026, 9, 9, 10, 0)),
            ),
        ),
        RegistryImportItem(
            OccurrenceInput(
                source_system="LVMS",
                sample_number="00123456789012345678",
                analysis_code="CALR-OU",
                ordered_at=datetime(2026, 9, 10, 8, 0),
                source_occurrence_id="WORK-2",
                source_kind="backlog",
            ),
        ),
    )
    run_id = registry.import_batch(
        items,
        kind="statistics",
        unit_key="hemato",
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 10),
        observed_at=datetime(2026, 9, 10, 12, 0),
        source_fingerprint="synthetic-excel",
    )
    with database._connect() as connection:
        current_occurrence = connection.execute(
            "SELECT id FROM analysis_occurrence WHERE source_occurrence_id = 'WORK-2'"
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO backlog_current(
                occurrence_id, import_run_id, unit_key, analysis_group,
                workflow_stage, updated_at
            ) VALUES (?, ?, 'hemato', 'CALR', 'ready', ?)
            """,
            (current_occurrence, run_id, datetime(2026, 9, 10, 12, 0).isoformat()),
        )
    return database
