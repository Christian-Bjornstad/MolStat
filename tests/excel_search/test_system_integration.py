from datetime import datetime
from pathlib import Path

from molstat.system import MolStatSystem

from .helpers import populated_database


def _system(tmp_path: Path) -> MolStatSystem:
    system = object.__new__(MolStatSystem)
    system.database = populated_database(tmp_path / "molstat.sqlite3")
    system.excel_search_path = tmp_path / "Prøvesøk.xlsx"
    system._excel_now = lambda: datetime(2026, 9, 10, 12, 30)
    system._excel_failure_reporter = None
    system.excel_status = None
    return system


def test_system_refreshes_search_workbook_and_records_safe_status(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path)

    published = system._refresh_excel_search()

    assert published is True
    assert system.excel_search_path.is_file()
    assert system.excel_status.status == "published"
    assert system.excel_status.generated_at == datetime(2026, 9, 10, 12, 30)
    assert system.excel_status.error_type is None


def test_excel_failure_is_isolated_and_status_omits_sensitive_details(
    tmp_path: Path, monkeypatch
) -> None:
    system = _system(tmp_path)
    failure = RuntimeError("SAMPLE-SECRET at K:/sensitive")
    reported = []
    system._excel_failure_reporter = lambda stage, error: reported.append((stage, error))
    monkeypatch.setattr(
        "molstat.system.publish_search_workbook",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
    )

    published = system._refresh_excel_search()

    assert published is False
    assert system.excel_status.status == "failed"
    assert system.excel_status.error_type == "RuntimeError"
    assert "SECRET" not in repr(system.excel_status)
    assert "K:/" not in repr(system.excel_status)
    assert reported == [("excel_search_refresh_failed", failure)]
