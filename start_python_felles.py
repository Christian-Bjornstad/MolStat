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
import tempfile
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


def _record_failure(stage: str, error: BaseException) -> Path | None:
    for fallback in (False, True):
        try:
            path = Path(tempfile.gettempdir()) / "MolStat" / "logs" / "bootstrap.log" if fallback else _log_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(f"\n[{stage}] {type(error).__name__}: {error}\n")
                stream.write(f"Startskript: {Path(__file__).resolve()}\nPython: {sys.executable}\n")
                traceback.print_exception(type(error), error, error.__traceback__, file=stream)
            return path
        except OSError:
            continue
    return None


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
        # Python FELLES may reuse an interactive interpreter after updating
        # the application. sys.path changes alone do not replace cached modules.
        for name in tuple(sys.modules):
            if name == "molstat" or name.startswith("molstat."):
                del sys.modules[name]
        import molstat
        origin = Path(molstat.__file__).resolve()
        if not origin.is_relative_to(project / "src" / "molstat"):
            raise RuntimeError(f"MolStat ble lastet fra feil programmappe: {origin}")
        from molstat.cli import main as app_main

    active_settings = settings_file or SETTINGS_FILE
    print(f"MolStat-programmappe: {project}")
    print(f"Innstillinger: {active_settings}")
    try:
        print(f"Oppstartslogg: {_log_file()}")
    except OSError:
        print("AppData-loggmappen er ikke tilgjengelig; ved feil brukes midlertidig mappe.")
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
        log_path = _record_failure("molstat_start_failed", error)
        print()
        print("MolStat kunne ikke startes.")
        print(f"Feil: {error}")
        if log_path is not None:
            print(f"Detaljer er skrevet til: {log_path}")
        else:
            print("Loggen kunne ikke skrives. Kopier feilmeldingen over.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
