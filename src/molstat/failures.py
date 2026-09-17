"""Public diagnostics contain known codes, never raw external error messages."""
from __future__ import annotations

import sqlite3

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
    "EXCEL_REFRESH_FAILED": "Excel-søket kunne ikke oppdateres. Lukk filen i Excel og prøv igjen.",
    "CSV_INVALID": "Uttrekket stemmer ikke med CSV-oppsettet eller inneholder ugyldige rader. Kontroller skilletegn, kolonner og datoformat i enhetsfilen.",
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
    primary = getattr(error, "sqlite_errorcode", 0) & 0xFF
    if primary in (5, 6) or name in ("SQLITE_BUSY", "SQLITE_LOCKED"):
        code = "DB_BUSY"
    elif primary in (8, 10, 14) or name.startswith(("SQLITE_CANTOPEN", "SQLITE_READONLY", "SQLITE_IOERR")):
        code = "DB_ACCESS"
    elif primary in (11, 26):
        code = "DB_INTEGRITY"
    else:
        code = "DB_ERROR"
    return RunFailure(code, "database", detail=name)
