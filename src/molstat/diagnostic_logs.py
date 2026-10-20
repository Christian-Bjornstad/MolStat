"""Best-effort local diagnostics without external exception payloads."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import traceback
from collections.abc import Iterator


def _directories(preferred: Path | None = None) -> Iterator[Path]:
    seen: set[Path] = set()
    local = str(os.environ.get("LOCALAPPDATA") or "").strip()
    primary = (Path(local) if local else Path.home() / "AppData" / "Local") / "MolStat" / "logs"
    for directory in (preferred, primary):
        if directory is not None and directory not in seen:
            seen.add(directory)
            yield directory
    try:
        temporary = Path(tempfile.gettempdir()) / "MolStat" / "logs"
    except OSError:
        return
    if temporary not in seen:
        yield temporary


def diagnostic_log_directory(preferred: Path | None = None) -> Path | None:
    """Return an actually writable directory, including any successful fallback."""
    for directory in _directories(preferred):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=directory, prefix=".molstat-log-probe-"):
                pass
            return directory
        except OSError:
            continue
    return None


def write_diagnostic_log(filename: str, summary: str, error: BaseException,
                         *, preferred: Path | None = None) -> Path | None:
    """Append safe diagnostics; storage errors must never replace the run failure."""
    if filename not in {"runtime.log", "bootstrap.log"}:
        raise ValueError("Unsupported diagnostic log.")
    # Source lines can themselves contain identifiers. Retain frame locations
    # without copying exception messages, locals or the failing source line.
    frames = "".join(
        f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}\n'
        for frame in traceback.extract_tb(error.__traceback__)
    )
    for directory in _directories(preferred):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / filename).open("a", encoding="utf-8", errors="backslashreplace") as stream:
                stream.write(f"\n{summary}\n{frames}")
            return directory
        except OSError:
            continue
    return None
