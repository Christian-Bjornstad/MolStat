"""Public diagnostics contain known codes, never raw external error messages."""
from __future__ import annotations

import sqlite3
import errno
import re

MESSAGES = {
    "LVMS_TIMEOUT": "LVMS svarte ikke i tide. Kontroller forbindelsen.",
    "LVMS_LOGIN_REQUIRED": "Åpne LVMS og kontroller innloggingen.",
    "LVMS_FORM": "Rapportskjemaet kunne ikke fylles ut. Kontroller rapportoppsettet.",
    "LVMS_FAILED": "LVMS-kjøringen feilet. Kontroller diagnostikken.",
    "DOWNLOAD_INCOMPLETE": "Nedlastingen er ikke bekreftet. Kontroller LVMS før nytt uttrekk.",
    "BROWSER_CLEANUP": "Nettleseren ble ikke lukket korrekt. Kontroller før ny kjøring.",
    "CANCELLED": "Kjøringen ble avbrutt.",
    "DB_BUSY": "Databasen er opptatt. Vent til annen kjøring er ferdig.",
    "DB_ACCESS": "Databasen kunne ikke åpnes. Kontroller mappe, nettverk og skrivetilgang.",
    "DB_SCHEMA": "Databaseskjemaet støttes ikke av denne appversjonen.",
    "DB_INTEGRITY": "Databasekontrollen feilet. Behold filen og kontroller en sikkerhetskopi.",
    "DB_ERROR": "Databaseoperasjonen feilet. Se teknisk feilkode.",
    "DB_FULL": "Disken har ikke nok ledig plass til å skrive databasen. Frigjør plass før nytt forsøk.",
    "FILE_ACCESS": "Filtilgang ble nektet. Filen eller mappen kan være skrivebeskyttet.",
    "FILE_BUSY": "Filen brukes av et annet program. MolStat beholder ferdigbehandlede data.",
    "FILE_UNAVAILABLE": "Filområdet er midlertidig utilgjengelig. Kontroller forbindelsen til K-sensitiv eller SharePoint.",
    "FILE_IO": "Filområdet svarte med en lese- eller skrivefeil. Kontroller lagringen.",
    "FILE_FULL": "Disken har ikke nok ledig plass. Frigjør plass før nytt forsøk.",
    "FILE_MISSING": "En nødvendig fil eller mappe finnes ikke. Kontroller valgt oppsett.",
    "FILE_ERROR": "Filoperasjonen feilet. Se trinn og numerisk OS-feilkode i Diagnostikk.",
    "DB_LEASE_LOST": "Databaselåsen ble mistet. Kjøringen er stoppet for å unngå samtidige skrivere. Kontroller nettverk og andre kjøringer før nytt forsøk.",
    "EXCEL_REFRESH_FAILED": "Excel-søket kunne ikke oppdateres. Lukk filen i Excel og prøv igjen.",
    "PRIVATE_FILES_LOCKED": "Power BI-datafilene kunne ikke erstattes. Lukk Power BI/Excel som bruker filene, og kontroller skrivetilgangen. Behandlede kandidater er bevart.",
    "PRIVATE_FILES_RECOVERY": "Gjenoppretting av Power BI-filsettet ble blokkert. Lukk programmer som bruker filene. Behandlede kandidater og gjenopprettingsfiler er bevart; filsettet må kontrolleres før oppdatering.",
    "PUBLICATION_RECOVERY": "Gjenoppretting av publiserte rapportfiler ble blokkert. Kandidater og sikkerhetskopier er bevart. Kontroller filsettet før rapportene oppdateres.",
    "CSV_INVALID": "Uttrekket stemmer ikke med CSV-oppsettet eller inneholder ugyldige rader. Kontroller skilletegn, kolonner og datoformat i enhetsfilen.",
    "CONFIG_INVALID": "Enhetsfilen må rettes. Kontroller JSON-oppsettet for denne enheten i Innstillinger.",
    "LVMS_CONFIG_INVALID": "LVMS-oppsettet må rettes. Kontroller adresse og nettleseroppsett i Innstillinger, eller importer uttrekk manuelt.",
}


class RunFailure(RuntimeError):
    def __init__(self, code: str, stage: str, *, retryable: bool = False,
                 attempt: int = 1, run_id: str = "", detail: str = "") -> None:
        self.code = code
        self.stage = stage
        self.retryable = retryable
        self.attempt = attempt
        self.run_id = run_id
        self.detail = detail
        super().__init__(code)

    def __str__(self) -> str:
        return (f"{self.code}: {MESSAGES.get(self.code, 'Kontroller oppsettet.')} "
                f"Trinn: {self.stage}; forsøk: {self.attempt}"
                + (f"; kjøring: {self.run_id}" if self.run_id else "")
                + (f"; {self.detail}" if self.detail else ""))


def database_failure(error: sqlite3.Error) -> RunFailure:
    name = getattr(error, "sqlite_errorname", "SQLITE_ERROR")
    if not (isinstance(name, str) and name.startswith("SQLITE_")
            and type(getattr(sqlite3, name, None)) is int):
        name = "SQLITE_ERROR"
    value = getattr(error, "sqlite_errorcode", 0)
    numeric_code = value if type(value) is int and 0 <= value <= 2**31 - 1 else 0
    primary = numeric_code & 0xFF
    if primary in (5, 6) or name in ("SQLITE_BUSY", "SQLITE_LOCKED"):
        code = "DB_BUSY"
    elif primary in (8, 10, 14) or name.startswith(("SQLITE_CANTOPEN", "SQLITE_READONLY", "SQLITE_IOERR")):
        code = "DB_ACCESS"
    elif primary == sqlite3.SQLITE_FULL:
        code = "DB_FULL"
    elif primary in (11, 26):
        code = "DB_INTEGRITY"
    else:
        code = "DB_ERROR"
    stage = getattr(error, "database_stage", "database")
    if not isinstance(stage, str) or stage not in {"database", "database_open", "database_write", "database_read",
                     "database_access", "database_directory"}:
        stage = "database"
    detail = name + (f"; SQLITE_CODE={numeric_code}" if numeric_code else "")
    os_code = getattr(error, "os_errorcode", None)
    if type(os_code) is int and 0 <= os_code <= 2**32 - 1:
        detail += f"; OS_ERROR={os_code}"
    return RunFailure(code, stage, detail=detail, retryable=primary in (5, 6, 8, 14))


def os_failure(error: OSError, *, stage: str = "file_access") -> RunFailure:
    """Explain a filesystem failure without copying paths or exception text."""
    number = error.errno if type(error.errno) is int else None
    value = getattr(error, "winerror", None)
    windows = value if type(value) is int and 0 <= value <= 2**32 - 1 else None
    if number == errno.ENOSPC or windows == 112:
        code, retryable = "FILE_FULL", False
    elif windows in (32, 33) or number in (errno.EBUSY, errno.EAGAIN, errno.ETXTBSY):
        code, retryable = "FILE_BUSY", True
    elif windows in (53, 54, 55, 59, 64, 67, 121, 1231, 1232) or number in (
            errno.ENETDOWN, errno.ENETUNREACH, errno.ECONNRESET, errno.ETIMEDOUT, errno.ESTALE):
        code, retryable = "FILE_UNAVAILABLE", True
    elif isinstance(error, PermissionError) or number in (errno.EACCES, errno.EPERM) or windows in (5, 19, 65):
        code, retryable = "FILE_ACCESS", True
    elif number == errno.EIO:
        code, retryable = "FILE_IO", True
    elif isinstance(error, FileNotFoundError) or number in (errno.ENOENT, errno.ENOTDIR):
        code, retryable = "FILE_MISSING", False
    else:
        code, retryable = "FILE_ERROR", False
    if not isinstance(stage, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,59}", stage):
        stage = "file_access"
    numeric = windows if windows is not None else number
    detail = f"OS_ERROR={numeric}" if numeric is not None else ""
    if windows is not None and number is not None:
        detail += f"; ERRNO={number}"
    return RunFailure(code, stage, detail=detail, retryable=retryable)


def storage_failure(error: BaseException, *, stage: str = "file_access") -> RunFailure | None:
    """Recognise native and wrapped I/O failures; never inspect raw messages."""
    seen: set[int] = set()
    current: BaseException | None = error
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        if isinstance(current, RunFailure):
            return current
        if isinstance(current, sqlite3.Error):
            return database_failure(current)
        if isinstance(current, OSError):
            return os_failure(current, stage=stage)
        current = current.__cause__ or current.__context__
    return None
