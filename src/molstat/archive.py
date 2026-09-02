from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

from .lvms.report import ReportRequest


@dataclass(frozen=True, slots=True)
class ArchivedRawFile:
    path: Path
    sha256: str


class RawArchive:
    def __init__(self, sensitive_root: Path) -> None:
        self.sensitive_root = sensitive_root

    def store(self, source: Path, request: ReportRequest) -> ArchivedRawFile:
        if not source.is_file():
            raise FileNotFoundError(source)
        destination_dir = (
            self.sensitive_root / "raw" / request.kind / request.unit
        )
        destination_dir.mkdir(parents=True, exist_ok=True)
        stem = (
            f"{request.report_name}__{request.date_from.isoformat()}"
            f"__{request.date_to.isoformat()}"
        )
        destination = _next_destination(destination_dir, stem)

        digest = hashlib.sha256()
        temporary_path: Path | None = None
        try:
            with source.open("rb") as reader, tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination_dir,
                prefix=f".{stem}.",
                suffix=".tmp",
                delete=False,
            ) as writer:
                temporary_path = Path(writer.name)
                while chunk := reader.read(1024 * 1024):
                    digest.update(chunk)
                    writer.write(chunk)
                writer.flush()
                os.fsync(writer.fileno())
            os.replace(temporary_path, destination)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        shutil.copystat(source, destination)
        return ArchivedRawFile(path=destination, sha256=digest.hexdigest())


def _next_destination(directory: Path, stem: str) -> Path:
    candidate = directory / f"{stem}.csv"
    revision = 2
    while candidate.exists():
        candidate = directory / f"{stem}__r{revision}.csv"
        revision += 1
    return candidate
