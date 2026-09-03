"""Installer MolStat for gjeldende Python FELLES-bruker.

Kjøres via MOLSTAT_INSTALL.cmd (Ivanti PowerGate) eller direkte:

    python install_python_felles.py

Skriptet installerer MolStat fra denne mappen i brukerens egne
site-packages, slik at det ikke kreves administratorrettigheter.
"""
from __future__ import annotations

import ensurepip
import importlib
import os
import site
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
REQUIRED_IMPORTS = ("PyQt6", "websocket", "molstat")


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


def install(
    *,
    project_dir: Path = PROJECT_DIR,
    user_site: Path | None = None,
    pip_main: Callable[[list[str]], int | None] | None = None,
    importer: Callable[[str], Any] = importlib.import_module,
) -> int:
    project = project_dir.resolve()
    if not (project / "pyproject.toml").is_file():
        raise RuntimeError("Finner ikke pyproject.toml i MolStat-mappen.")
    if not (project / "src" / "molstat").is_dir():
        raise RuntimeError("Finner ikke MolStat-koden i src\\molstat.")

    package_site = (user_site or Path(site.getusersitepackages())).resolve()
    package_site.mkdir(parents=True, exist_ok=True)
    _add_path_first(package_site)

    if pip_main is None:
        try:
            import pip  # noqa: F401
        except ImportError:
            ensurepip.bootstrap(user=True, upgrade=True)
        from pip._internal.cli.main import main as pip_main

    result = int(
        pip_main(
            [
                "install",
                "--user",
                "--disable-pip-version-check",
                "-e",
                f"{project}[dev]",
            ]
        )
        or 0
    )
    if result != 0:
        raise RuntimeError(f"Installasjonen stoppet med kode {result}.")

    _add_path_first(project / "src")
    importlib.invalidate_caches()
    for module_name in REQUIRED_IMPORTS:
        importer(module_name)

    print()
    print("MolStat er installert med Python FELLES.")
    print("Lukk Python FELLES og start MolStat med MOLSTAT_START.cmd.")
    return 0


def main(*, project_dir: Path = PROJECT_DIR) -> int:
    """Sikkerhetsgrense mot Python FELLES: fang og logg alle feil."""
    try:
        activate_user_site()
        return install(project_dir=project_dir)
    except Exception as error:  # noqa: BLE001
        _record_failure("installer_start_failed", error)
        print()
        print("MolStat-installasjonen kunne ikke fullføres.")
        print(f"Feil: {error}")
        print(f"Detaljer er skrevet til: {_log_file()}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
