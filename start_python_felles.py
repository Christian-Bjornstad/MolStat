"""Start MolStat inne i Python FELLES.

Kjøres via MOLSTAT_START.cmd (Ivanti PowerGate) eller direkte:

    python start_python_felles.py

Skriptet legger brukerens site-packages og repoets src-mappe først på
sys.path og starter deretter MolStat-GUI-et via CLI-en.
"""
from __future__ import annotations

import importlib
import os
import site
import sys
import traceback
from collections.abc import Callable
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = (
    Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    / "MolStat"
    / "settings.json"
)


def _add_path_first(path: Path) -> None:
    text = str(path)
    while text in sys.path:
        sys.path.remove(text)
    sys.path.insert(0, text)


def activate_user_site() -> Path:
    """Legg brukerens site-packages for Python FELLES først på sys.path."""
    if sys.version_info[:2] != (3, 14):
        raise RuntimeError(
            "MolStat krever Python FELLES 3.14, men aktiv versjon er "
            f"{sys.version.split()[0]}."
        )
    user_site = Path(site.getusersitepackages())
    user_site.mkdir(parents=True, exist_ok=True)
    _add_path_first(user_site)
    return user_site


def _log_file() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    logs = base / "MolStat" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs / "bootstrap.log"


def _record_failure(stage: str, error: BaseException) -> None:
    with _log_file().open("a", encoding="utf-8") as stream:
        stream.write(f"\n[{stage}] {type(error).__name__}: {error}\n")
        traceback.print_exception(type(error), error, error.__traceback__, file=stream)


def start(
    *,
    project_dir: Path = PROJECT_DIR,
    user_site: Path | None = None,
    settings_file: Path | None = None,
    app_main: Callable[[list[str]], int | None] | None = None,
) -> int:
    project = project_dir.resolve()
    if not (project / "src" / "molstat").is_dir():
        raise RuntimeError("Finner ikke MolStat-koden i src\\molstat.")

    package_site = (user_site or Path(site.getusersitepackages())).resolve()
    _add_path_first(package_site)
    _add_path_first(project / "src")
    _add_path_first(project)
    importlib.invalidate_caches()

    if app_main is None:
        from molstat.cli import main as app_main

    active_settings = settings_file or SETTINGS_FILE
    result = int(app_main(["gui", "--settings", str(active_settings)]) or 0)
    if result != 0:
        raise RuntimeError(f"MolStat stoppet med kode {result}.")
    return 0


def main(*, project_dir: Path = PROJECT_DIR) -> int:
    """Sikkerhetsgrense mot Python FELLES: fang og logg alle feil."""
    try:
        activate_user_site()
        return start(project_dir=project_dir)
    except Exception as error:  # noqa: BLE001
        _record_failure("molstat_start_failed", error)
        print()
        print("MolStat kunne ikke startes.")
        print(f"Feil: {error}")
        print(f"Detaljer er skrevet til: {_log_file()}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
