from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class DownloadError(RuntimeError):
    """CSV detection or local opening failed without exposing a path."""


class DownloadStatus(StrEnum):
    WAITING = "waiting"
    DETECTED = "detected"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"


@dataclass(frozen=True)
class FileStamp:
    size: int
    modified_ns: int


def finalize_csv(source: Path, directory: Path, filename: str) -> Path:
    if not source.is_absolute() or not directory.is_absolute():
        raise DownloadError("CSV finalization target is invalid")
    resolved_directory = directory.resolve()
    resolved_source = source.resolve()
    destination = resolved_directory / filename
    if (
        resolved_source.suffix.lower() != ".csv"
        or destination.parent != resolved_directory
        or destination.suffix.lower() != ".csv"
        or not resolved_source.is_file()
        or destination.exists()
    ):
        raise DownloadError("CSV finalization target is invalid")
    try:
        shutil.move(str(resolved_source), str(destination))
    except OSError as exc:
        raise DownloadError("CSV finalization failed") from exc
    return destination


def _stamp(path: Path) -> FileStamp:
    stat = path.stat()
    return FileStamp(stat.st_size, stat.st_mtime_ns)


class CsvArrivalDetector:
    def __init__(self, directory: Path) -> None:
        if not directory.is_absolute():
            raise DownloadError("download directory must be absolute")
        self._directory = directory.resolve()
        self._baseline: dict[Path, FileStamp] = {}
        self._temporary_baseline: set[Path] = set()
        self._entry_baseline: set[Path] = set()
        self._pending: tuple[Path, FileStamp] | None = None
        self._detected: Path | None = None
        self._started = False

    def _scan(self) -> dict[Path, FileStamp]:
        try:
            return {
                item.resolve(): _stamp(item)
                for item in self._directory.iterdir()
                if item.is_file() and item.suffix.lower() == ".csv"
            }
        except OSError as exc:
            raise DownloadError("download directory is unavailable") from exc

    def _scan_temporary(self) -> set[Path]:
        try:
            return {
                item.resolve()
                for item in self._directory.iterdir()
                if item.is_file()
                and item.name.lower().endswith((".crdownload", ".tmp", ".partial"))
            }
        except OSError as exc:
            raise DownloadError("download directory is unavailable") from exc

    def _scan_files(self) -> set[Path]:
        try:
            return {item.resolve() for item in self._directory.iterdir() if item.is_file()}
        except OSError as exc:
            raise DownloadError("download directory is unavailable") from exc

    def start(self) -> None:
        self._baseline = self._scan()
        self._temporary_baseline = self._scan_temporary()
        if self._temporary_baseline:
            raise DownloadError("temporary download already exists")
        self._entry_baseline = self._scan_files()
        self._pending = None
        self._detected = None
        self._started = True

    def poll(self) -> DownloadStatus:
        if not self._started:
            raise DownloadError("download detector has not started")
        if self._detected is not None:
            return (
                DownloadStatus.DETECTED
                if self._detected.is_file()
                else DownloadStatus.MISSING
            )
        if self._scan_temporary() - self._temporary_baseline:
            self._pending = None
            return DownloadStatus.WAITING
        unexpected = {
            path
            for path in self._scan_files() - self._entry_baseline
            if path.suffix.lower() != ".csv"
        }
        if unexpected:
            self._pending = None
            return DownloadStatus.AMBIGUOUS
        current = self._scan()
        changed_files = {
            path: stamp
            for path, stamp in current.items()
            if path not in self._baseline or self._baseline[path] != stamp
        }
        if len(changed_files) > 1:
            self._pending = None
            return DownloadStatus.AMBIGUOUS
        if not changed_files:
            self._pending = None
            return DownloadStatus.WAITING
        item = next(iter(changed_files.items()))
        if self._pending == item:
            self._detected = item[0]
            return DownloadStatus.DETECTED
        self._pending = item
        return DownloadStatus.WAITING

    def detected_path(self) -> Path | None:
        return self._detected


def open_local(
    path: Path,
    *,
    opener: Callable[[str], object] | None = None,
) -> None:
    if not path.is_absolute() or path.suffix.lower() != ".csv" or not path.is_file():
        raise DownloadError("detected CSV is unavailable")
    active_opener = opener or getattr(os, "startfile", None)
    if active_opener is None:
        raise DownloadError("local CSV opening is unavailable")
    try:
        active_opener(str(path))
    except OSError as exc:
        raise DownloadError("local CSV opening failed") from exc

