"""Deterministisk, pseudonym detaljeksport av restansehistorikk."""

from __future__ import annotations

import csv
import os
from pathlib import Path
import tempfile

from ..database import MolStatDatabase


BACKLOG_PUBLIC_COLUMNS = (
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
    "MolStat-ID",
)


def export_backlog_history(
    database: MolStatDatabase,
    destination: Path,
    *,
    unit_key: str,
) -> int:
    with database._connect() as connection:
        rows = connection.execute(
            """
            SELECT observed_at,
                   unit_key,
                   material,
                   analysis_code,
                   nucleic_acid,
                   analysis_group_code,
                   analysis_group_label,
                   collected_at,
                   arrived_at,
                   ordered_at,
                   analysis_priority,
                   request_priority,
                   analysis_status,
                   preliminary_status,
                   workflow_stage,
                   response_deadline,
                   analysis_result,
                   external_analysis_comment,
                   classifier_version,
                   molstat_key
            FROM backlog_detail_snapshot
            WHERE unit_key = ?
            ORDER BY observed_at, row_number
            """,
            (unit_key,),
        ).fetchall()

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
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
                writer.writerow(row)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return len(rows)
