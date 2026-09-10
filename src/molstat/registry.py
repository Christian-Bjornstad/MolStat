"""Sensitive sample identity and registry contracts.

Only opaque hashes are used as cross-report occurrence keys. Human-readable
sample numbers remain inside the protected database and must never be logged.
"""

from __future__ import annotations

from collections.abc import Iterable, Sized
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .database import MolStatDatabase


class IdentityContractError(ValueError):
    """Raised when the versioned LVMS identity contract is invalid."""


class AmbiguousOccurrenceError(ValueError):
    """Raised instead of joining conflicting source identities."""


@dataclass(frozen=True, slots=True)
class ReportIdentityContract:
    sample_id_columns: tuple[str, ...]
    occurrence_id_columns: tuple[str, ...]
    analysis_code_columns: tuple[str, ...]
    ordered_at_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IdentityContract:
    source_system: str
    sample_number_scope: str
    reports: dict[str, ReportIdentityContract]


@dataclass(frozen=True, slots=True)
class OccurrenceIdentity:
    key: str
    uses_fallback: bool


@dataclass(frozen=True, slots=True)
class OccurrenceInput:
    source_system: str
    sample_number: str
    analysis_code: str
    ordered_at: datetime
    source_kind: str
    source_occurrence_id: str | None = None


@dataclass(frozen=True, slots=True)
class RegisteredOccurrence:
    sample_id: int
    occurrence_id: int
    molstat_key: str
    identity_status: str


@dataclass(frozen=True, slots=True)
class OccurrenceEventInput:
    event_type: str
    event_at: datetime


@dataclass(frozen=True, slots=True)
class RegistryImportItem:
    occurrence: OccurrenceInput
    events: tuple[OccurrenceEventInput, ...] = ()


@dataclass(frozen=True, slots=True)
class OccurrenceSearchRow:
    occurrence_id: int
    analysis_code: str
    ordered_at: datetime
    source_occurrence_id: str | None
    identity_status: str


@dataclass(frozen=True, slots=True)
class SampleSearchRow:
    sample_id: int
    molstat_key: str
    sample_number: str
    occurrences: tuple[OccurrenceSearchRow, ...]


class SampleRegistry:
    """Transactional persistence and indexed lookup for sensitive samples."""

    def __init__(self, database: MolStatDatabase) -> None:
        self.database = database

    def register_occurrence(
        self,
        item: OccurrenceInput,
        *,
        observed_at: datetime,
    ) -> RegisteredOccurrence:
        with self.database._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                registered = self.register_occurrence_in_transaction(
                    connection,
                    item,
                    observed_at=observed_at,
                )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        return registered

    def register_occurrence_in_transaction(
        self,
        connection: sqlite3.Connection,
        item: OccurrenceInput,
        *,
        observed_at: datetime,
        import_run_id: int | None = None,
    ) -> RegisteredOccurrence:
        """Register one occurrence inside a caller-owned transaction."""

        source_system = normalize_identifier(item.source_system)
        sample_value = _clean_identifier(item.sample_number)
        sample_number = normalize_identifier(sample_value)
        analysis_code = normalize_identifier(item.analysis_code)
        source_occurrence_id = normalize_identifier(item.source_occurrence_id) or None
        source_kind = item.source_kind.strip().casefold()
        if not source_system or not sample_number or not analysis_code or not source_kind:
            raise ValueError("Registerfeltene kan ikke være tomme.")
        identity = build_occurrence_identity(
            source_system=source_system,
            sample_number=sample_number,
            analysis_code=analysis_code,
            ordered_at=item.ordered_at,
            source_occurrence_id=source_occurrence_id,
        )
        observed_text = observed_at.isoformat(timespec="seconds")
        ordered_text = item.ordered_at.isoformat(timespec="seconds")
        sample_id, molstat_key = self._resolve_sample(
            connection,
            source_system=source_system,
            sample_value=sample_value,
            sample_number=sample_number,
            observed_at=observed_text,
        )
        occurrence_id, identity_status = self._resolve_occurrence(
            connection,
            sample_id=sample_id,
            identity=identity,
            source_system=source_system,
            source_occurrence_id=source_occurrence_id,
            analysis_code=analysis_code,
            ordered_at=ordered_text,
            observed_at=observed_text,
        )
        connection.execute(
            """
            INSERT INTO source_observation(
                occurrence_id, source_kind, first_seen_at, last_seen_at,
                last_import_run_id
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(occurrence_id, source_kind) DO UPDATE SET
                last_seen_at = excluded.last_seen_at,
                last_import_run_id = excluded.last_import_run_id
            """,
            (
                occurrence_id,
                source_kind,
                observed_text,
                observed_text,
                import_run_id,
            ),
        )
        return RegisteredOccurrence(
            sample_id=sample_id,
            occurrence_id=occurrence_id,
            molstat_key=molstat_key,
            identity_status=identity_status,
        )

    def import_batch(
        self,
        items: Iterable[RegistryImportItem],
        *,
        row_count: int | None = None,
        kind: str,
        unit_key: str,
        date_from: date,
        date_to: date,
        observed_at: datetime,
        source_fingerprint: str,
    ) -> int:
        """Atomically import a complete source batch and its events."""

        if row_count is None:
            if not isinstance(items, Sized):
                items = tuple(items)
            row_count = len(items)
        if row_count < 0:
            raise ValueError("Radantall kan ikke være negativt.")
        observed_text = observed_at.isoformat(timespec="seconds")
        with self.database._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO import_run(
                        kind, unit_key, date_from, date_to, started_at,
                        finished_at, status, source_fingerprint, row_count,
                        invalid_rows, excluded_rows
                    ) VALUES (?, ?, ?, ?, ?, ?, 'completed', ?, ?, 0, 0)
                    """,
                    (
                        kind,
                        unit_key,
                        date_from.isoformat(),
                        date_to.isoformat(),
                        observed_text,
                        observed_text,
                        source_fingerprint,
                        row_count,
                    ),
                )
                import_run_id = int(cursor.lastrowid)
                processed_count = 0
                for item in items:
                    processed_count += 1
                    registered = self.register_occurrence_in_transaction(
                        connection,
                        item.occurrence,
                        observed_at=observed_at,
                        import_run_id=import_run_id,
                    )
                    connection.executemany(
                        """
                        INSERT INTO analysis_event(
                            occurrence_id, event_type, event_at, source_kind,
                            import_run_id
                        ) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(occurrence_id, event_type, event_at, source_kind)
                        DO UPDATE SET import_run_id = excluded.import_run_id
                        """,
                        (
                            (
                                registered.occurrence_id,
                                event.event_type,
                                event.event_at.isoformat(timespec="seconds"),
                                item.occurrence.source_kind.strip().casefold(),
                                import_run_id,
                            )
                            for event in item.events
                        ),
                    )
                if processed_count != row_count:
                    raise ValueError(
                        "Radantallet stemmer ikke med den strømmede importen."
                    )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        return import_run_id

    def counts(self) -> tuple[int, int]:
        with self.database._connect() as connection:
            samples = int(connection.execute("SELECT COUNT(*) FROM sample").fetchone()[0])
            occurrences = int(
                connection.execute("SELECT COUNT(*) FROM analysis_occurrence").fetchone()[0]
            )
        return samples, occurrences

    def molstat_ids(self, *, source_system: str = "LVMS") -> dict[str, str]:
        """Return normalized sample numbers mapped to stable MolStat IDs."""

        source = normalize_identifier(source_system)
        with self.database._connect() as connection:
            rows = connection.execute(
                """
                SELECT si.normalized_value, s.molstat_key
                FROM sample_identifier AS si
                JOIN sample AS s ON s.id = si.sample_id
                WHERE si.source_system = ?
                  AND si.identifier_type = 'sample_number'
                """,
                (source,),
            ).fetchall()
        return {str(row[0]): str(row[1]) for row in rows}

    def search(self, query: str, *, prefix: bool = False) -> tuple[SampleSearchRow, ...]:
        normalized = normalize_identifier(query)
        if not normalized:
            return ()
        with self.database._connect() as connection:
            if prefix:
                pattern = _escape_like(normalized) + "%"
                samples = connection.execute(
                    """
                    SELECT DISTINCT s.id, s.molstat_key, si.identifier_value
                    FROM sample AS s
                    JOIN sample_identifier AS si ON si.sample_id = s.id
                    WHERE si.identifier_type = 'sample_number'
                      AND (si.normalized_value LIKE ? ESCAPE '\\'
                           OR s.molstat_key LIKE ? ESCAPE '\\')
                    ORDER BY si.identifier_value, s.molstat_key
                    """,
                    (pattern, pattern),
                ).fetchall()
            else:
                samples = connection.execute(
                    """
                    SELECT DISTINCT s.id, s.molstat_key, si.identifier_value
                    FROM sample AS s
                    JOIN sample_identifier AS si ON si.sample_id = s.id
                    WHERE si.identifier_type = 'sample_number'
                      AND (si.normalized_value = ? OR s.molstat_key = ?)
                    ORDER BY si.identifier_value, s.molstat_key
                    """,
                    (normalized, normalized),
                ).fetchall()
            return tuple(self._search_row(connection, row) for row in samples)

    def explain_sample_number_search(self, query: str) -> tuple[str, ...]:
        normalized = normalize_identifier(query)
        with self.database._connect() as connection:
            rows = connection.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT sample_id FROM sample_identifier
                WHERE normalized_value = ?
                """,
                (normalized,),
            ).fetchall()
        return tuple(str(row[3]) for row in rows)

    @staticmethod
    def _resolve_sample(
        connection: sqlite3.Connection,
        *,
        source_system: str,
        sample_value: str,
        sample_number: str,
        observed_at: str,
    ) -> tuple[int, str]:
        row = connection.execute(
            """
            SELECT s.id, s.molstat_key
            FROM sample_identifier AS si
            JOIN sample AS s ON s.id = si.sample_id
            WHERE si.source_system = ? AND si.identifier_type = 'sample_number'
              AND si.normalized_value = ?
            """,
            (source_system, sample_number),
        ).fetchone()
        if row is not None:
            connection.execute(
                "UPDATE sample SET last_seen_at = ? WHERE id = ?",
                (observed_at, row[0]),
            )
            return int(row[0]), str(row[1])
        cursor = connection.execute(
            """
            INSERT INTO sample(molstat_key, first_seen_at, last_seen_at)
            VALUES (?, ?, ?)
            """,
            (f"PENDING-{uuid4().hex}", observed_at, observed_at),
        )
        sample_id = int(cursor.lastrowid)
        molstat_key = f"M-{sample_id:06d}"
        connection.execute(
            "UPDATE sample SET molstat_key = ? WHERE id = ?",
            (molstat_key, sample_id),
        )
        connection.execute(
            """
            INSERT INTO sample_identifier(
                sample_id, source_system, identifier_type,
                identifier_value, normalized_value
            ) VALUES (?, ?, 'sample_number', ?, ?)
            """,
            (sample_id, source_system, sample_value, sample_number),
        )
        return sample_id, molstat_key

    @staticmethod
    def _resolve_occurrence(
        connection: sqlite3.Connection,
        *,
        sample_id: int,
        identity: OccurrenceIdentity,
        source_system: str,
        source_occurrence_id: str | None,
        analysis_code: str,
        ordered_at: str,
        observed_at: str,
    ) -> tuple[int, str]:
        row = connection.execute(
            """
            SELECT id, sample_id, analysis_code, ordered_at, identity_status
            FROM analysis_occurrence WHERE occurrence_key = ?
            """,
            (identity.key,),
        ).fetchone()
        if row is not None:
            if int(row[1]) != sample_id or str(row[2]) != analysis_code or str(row[3]) != ordered_at:
                raise AmbiguousOccurrenceError(
                    "Kildeidentiteten peker på motstridende analysedata."
                )
            connection.execute(
                "UPDATE analysis_occurrence SET last_seen_at = ? WHERE id = ?",
                (observed_at, row[0]),
            )
            return int(row[0]), str(row[4])
        identity_status = "fallback_review" if identity.uses_fallback else "resolved"
        cursor = connection.execute(
            """
            INSERT INTO analysis_occurrence(
                sample_id, occurrence_key, source_system, source_occurrence_id,
                analysis_code, ordered_at, uses_fallback, identity_status,
                first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                identity.key,
                source_system,
                source_occurrence_id,
                analysis_code,
                ordered_at,
                int(identity.uses_fallback),
                identity_status,
                observed_at,
                observed_at,
            ),
        )
        return int(cursor.lastrowid), identity_status

    @staticmethod
    def _search_row(connection: sqlite3.Connection, row: tuple) -> SampleSearchRow:
        occurrences = connection.execute(
            """
            SELECT id, analysis_code, ordered_at, source_occurrence_id,
                   identity_status
            FROM analysis_occurrence
            WHERE sample_id = ?
            ORDER BY ordered_at, id
            """,
            (row[0],),
        ).fetchall()
        return SampleSearchRow(
            sample_id=int(row[0]),
            molstat_key=str(row[1]),
            sample_number=str(row[2]),
            occurrences=tuple(
                OccurrenceSearchRow(
                    occurrence_id=int(item[0]),
                    analysis_code=str(item[1]),
                    ordered_at=datetime.fromisoformat(str(item[2])),
                    source_occurrence_id=(str(item[3]) if item[3] is not None else None),
                    identity_status=str(item[4]),
                )
                for item in occurrences
            ),
        )


def normalize_identifier(value: object) -> str:
    """Normalize an LVMS identifier without interpreting it as a number."""

    return _clean_identifier(value).upper()


def _clean_identifier(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith('=T("') and text.endswith('")'):
        text = text[4:-2].replace('""', '"').strip()
    return text


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_occurrence_identity(
    *,
    source_system: str,
    sample_number: str,
    analysis_code: str,
    ordered_at: datetime,
    source_occurrence_id: str | None = None,
) -> OccurrenceIdentity:
    """Build a stable opaque key from immutable source identity fields."""

    source = normalize_identifier(source_system)
    occurrence = normalize_identifier(source_occurrence_id)
    if occurrence:
        parts = ("source-id", source, occurrence)
        uses_fallback = False
    else:
        sample = normalize_identifier(sample_number)
        analysis = normalize_identifier(analysis_code)
        if not source or not sample or not analysis:
            raise ValueError("Identitetsfeltene kan ikke være tomme.")
        parts = (
            "fallback",
            source,
            sample,
            analysis,
            ordered_at.isoformat(timespec="seconds"),
        )
        uses_fallback = True
    digest = hashlib.sha256()
    for part in parts:
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return OccurrenceIdentity(digest.hexdigest(), uses_fallback)


def load_identity_contract(path: Path) -> IdentityContract:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityContractError("Kunne ikke lese identitetskontrakten.") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise IdentityContractError("Ukjent identitetskontrakt.")
    source_system = _required_text(raw, "source_system")
    scope = _required_text(raw, "sample_number_scope")
    reports_raw = raw.get("reports")
    if not isinstance(reports_raw, dict) or not reports_raw:
        raise IdentityContractError("Identitetskontrakten mangler rapporter.")
    reports: dict[str, ReportIdentityContract] = {}
    for name, report_raw in reports_raw.items():
        if not isinstance(name, str) or not isinstance(report_raw, dict):
            raise IdentityContractError("Ugyldig rapport i identitetskontrakten.")
        reports[name] = ReportIdentityContract(
            sample_id_columns=_text_list(report_raw, "sample_id_columns"),
            occurrence_id_columns=_text_list(report_raw, "occurrence_id_columns"),
            analysis_code_columns=_text_list(report_raw, "analysis_code_columns"),
            ordered_at_columns=_text_list(report_raw, "ordered_at_columns"),
        )
    return IdentityContract(source_system, scope, reports)


def _required_text(raw: dict, key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise IdentityContractError(f"Identitetskontrakten mangler {key}.")
    return value.strip()


def _text_list(raw: dict, key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise IdentityContractError(f"Identitetskontrakten har ugyldig {key}.")
    result = tuple(item.strip() for item in value)
    if len(set(result)) != len(result):
        raise IdentityContractError(f"Identitetskontrakten har duplikater i {key}.")
    return result
