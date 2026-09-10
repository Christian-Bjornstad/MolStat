from datetime import datetime
from pathlib import Path
import zipfile

from molstat.excel_search import (
    publish_search_workbook,
    read_excel_snapshot,
    search_samples,
)

from .helpers import populated_database


def test_registry_to_excel_keeps_one_cross_source_sample_and_no_live_connections(
    tmp_path: Path,
) -> None:
    database = populated_database(tmp_path / "sensitive" / "data" / "molstat.sqlite3")
    snapshot = read_excel_snapshot(
        database,
        generated_at=datetime(2026, 9, 10, 12, 30),
    )
    destination = tmp_path / "sensitive" / "Prøvesøk.xlsx"

    publication = publish_search_workbook(snapshot, destination)

    assert publication.status == "published"
    assert len(snapshot.samples) == 1
    assert len(snapshot.analyses) == 2
    assert {row.source_kinds for row in snapshot.analyses} == {
        "backlog",
        "statistics_answered",
    }
    assert len(search_samples(snapshot.samples, "001234", prefix=True)) == 1
    with zipfile.ZipFile(destination) as archive:
        names = set(archive.namelist())
        text = "\n".join(
            archive.read(name).decode("utf-8", errors="ignore")
            for name in names
            if name.endswith((".xml", ".rels"))
        )
    assert "xl/vbaProject.bin" not in names
    assert not any(name.startswith("xl/externalLinks/") for name in names)
    assert "xl/connections.xml" not in names
    assert "molstat.sqlite3" not in text
    assert str(tmp_path).replace("\\", "/") not in text
