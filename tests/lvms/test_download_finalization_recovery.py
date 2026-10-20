from pathlib import Path
import shutil

import pytest

from molstat.lvms.downloads import DownloadError, finalize_csv
from molstat.recovery import retry_operation


def test_failed_copy_does_not_leave_partial_canonical_report(tmp_path, monkeypatch):
    source = tmp_path / "source.csv"
    source.write_bytes(b"synthetic full report")
    directory = tmp_path / "confirmed"
    directory.mkdir()
    original_copy = shutil.copyfileobj
    calls = []
    def copy_with_one_failure(reader, writer, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            writer.write(b"partial")
            raise PermissionError(13, "synthetic temporary lock")
        return original_copy(reader, writer, *args, **kwargs)
    monkeypatch.setattr(shutil, "copyfileobj", copy_with_one_failure)

    destination = retry_operation(lambda: finalize_csv(source, directory, "report.csv"),
                                  stage="lvms_finalize", sleep=lambda _: None)

    assert len(calls) == 2
    assert destination.read_bytes() == b"synthetic full report"
    assert not source.exists()
    assert list(directory.iterdir()) == [destination]
