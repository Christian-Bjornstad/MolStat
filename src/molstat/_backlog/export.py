"""Deterministic, identifier-free Power BI export of backlog history."""

from __future__ import annotations

import csv
import os
from pathlib import Path
import tempfile

from ..database import MolStatDatabase


BACKLOG_PUBLIC_COLUMNS = (
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


def export_backlog_history(
    database: MolStatDatabase,
    destination: Path,
) -> int:
    with database._connect() as connection:
        rows = connection.execute(
            """
            SELECT observed_at,
                   unit_key,
                   analysis_code,
                   analysis_label,
                   ready_count,
                   awaiting_approval_count,
                   in_transit_count,
                   overdue_count,
                   median_ready_hours,
                   oldest_ready_hours,
                   severity,
                   invalid_rows,
                   excluded_rows,
                   source_is_fresh,
                   classifier_version
            FROM backlog_snapshot
            ORDER BY observed_at, unit_key, analysis_code
            """
        ).fetchall()

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(BACKLOG_PUBLIC_COLUMNS)
            for row in rows:
                public_row = [*row]
                public_row[13] = "Ja" if bool(public_row[13]) else "Nei"
                writer.writerow(public_row)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return len(rows)
