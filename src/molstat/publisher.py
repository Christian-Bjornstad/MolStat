from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import logging
import os
from pathlib import Path
import re
import tempfile
from typing import Mapping, Pattern
from uuid import uuid4
from ._writer_lease import guarded_output
from .failures import RunFailure, storage_failure
from .recovery import retry_operation, uncancellable_cleanup


def _retry_replace(error: BaseException) -> bool:
    failure = storage_failure(error)
    return failure is not None and failure.code in {"FILE_ACCESS", "FILE_BUSY"}


class PrivacyViolation(ValueError):
    """Raised before publication when a candidate breaks the public contract."""


@dataclass(frozen=True, slots=True)
class PublicationPolicy:
    allowed_columns: Mapping[str, frozenset[str]]
    forbidden_patterns: tuple[Pattern[str], ...]


@dataclass(frozen=True, slots=True)
class PublishedFile:
    path: Path
    sha256: str


@dataclass(frozen=True, slots=True)
class PublicationResult:
    files: Mapping[str, PublishedFile]


class SharePointPublisher:
    def __init__(self, policy: PublicationPolicy) -> None:
        self.policy = policy

    def publish(
        self,
        files: Mapping[str, Path],
        destination: Path,
    ) -> PublicationResult:
        with guarded_output():
            return self._publish(files, destination)

    def _publish(self, files: Mapping[str, Path], destination: Path) -> PublicationResult:
        expected_files = set(self.policy.allowed_columns)
        if set(files) != expected_files:
            raise PrivacyViolation(
                "Publiseringskandidaten har et annet filsett enn allowlisten."
            )

        for output_name, source in files.items():
            retry_operation(lambda: self._validate_candidate(output_name, source), stage="public_stage")

        retry_operation(lambda: destination.mkdir(parents=True, exist_ok=True), stage="public_stage")
        staged: dict[str, tuple[Path, str]] = {}
        backups: dict[str, Path] = {}
        installed: list[str] = []
        keep_recovery = False
        try:
            for output_name, source in files.items():
                staged[output_name] = retry_operation(
                    lambda: _stage_file(source, destination, output_name), stage="public_stage"
                )

            for output_name in files:
                target = destination / output_name
                if target.exists():
                    backup = destination / f".{output_name}.{uuid4().hex}.bak"
                    backups[output_name] = backup
                    retry_operation(lambda: os.replace(target, backup), stage="public_replace",
                                    retry_if=_retry_replace)
                # Record intent first: an I/O error can occur after a rename
                # reached the filesystem. Rollback must account for that file.
                installed.append(output_name)
                retry_operation(lambda: os.replace(staged[output_name][0], target), stage="public_replace",
                                retry_if=_retry_replace)

        except BaseException:
            restore_errors = []
            with uncancellable_cleanup():
                for output_name in reversed(tuple(files)):
                    try:
                        if output_name in backups:
                            backup = backups[output_name]
                            if backup.exists():
                                # Replace directly: deleting the new file first can
                                # expose a missing target if restoring is blocked.
                                retry_operation(lambda: os.replace(backup, destination / output_name),
                                                stage="public_rollback", retry_if=_retry_replace)
                        elif output_name in installed:
                            retry_operation(lambda: (destination / output_name).unlink(missing_ok=True),
                                            stage="public_rollback")
                    except OSError as exc:
                        restore_errors.append(exc)
            if restore_errors:
                keep_recovery = True
                raise RunFailure("PUBLICATION_RECOVERY", "public_rollback") from restore_errors[0]
            raise
        finally:
            if not keep_recovery:
                for temporary, _digest in staged.values():
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        logging.getLogger(__name__).warning("En midlertidig publiseringsfil kunne ikke ryddes.")

        # All targets are now installed. Cleanup must not roll back a committed
        # publication: earlier backups may already have been removed.
        for backup in backups.values():
            try:
                backup.unlink(missing_ok=True)
            except OSError:
                logging.getLogger(__name__).warning(
                    "Publisering fullført, men en backupfil kunne ikke slettes."
                )

        return PublicationResult(
            files={
                output_name: PublishedFile(
                    path=destination / output_name,
                    sha256=staged[output_name][1],
                )
                for output_name in files
            }
        )

    def _validate_candidate(self, output_name: str, source: Path) -> None:
        if Path(output_name).name != output_name:
            raise PrivacyViolation(f"Ugyldig publiseringsnavn: {output_name}")
        if not source.is_file():
            raise PrivacyViolation(f"Mangler publiseringsfil: {output_name}")
        try:
            with source.open("r", encoding="utf-8-sig", newline="") as stream:
                header = next(csv.reader(stream, delimiter=";"), None)
        except (UnicodeError, csv.Error) as exc:
            raise PrivacyViolation(
                f"Kunne ikke validere {output_name}."
            ) from exc
        if not header:
            raise PrivacyViolation(f"{output_name} mangler kolonneoverskrift.")
        forbidden = [
            column
            for column in header
            if any(pattern.search(column) for pattern in self.policy.forbidden_patterns)
        ]
        allowed = self.policy.allowed_columns[output_name]
        if forbidden or set(header) != allowed or len(header) != len(allowed):
            raise PrivacyViolation(
                f"{output_name} inneholder kolonner utenfor personvernkontrakten."
            )


def _stage_file(source: Path, destination: Path, output_name: str) -> tuple[Path, str]:
    digest = hashlib.sha256()
    temporary: Path | None = None
    try:
        with source.open("rb") as reader, tempfile.NamedTemporaryFile(
            mode="wb", dir=destination, prefix=f".{output_name}.", suffix=".tmp", delete=False,
        ) as writer:
            temporary = Path(writer.name)
            while chunk := reader.read(1024 * 1024):
                digest.update(chunk)
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
    except BaseException:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                logging.getLogger(__name__).warning("En mislykket publiseringskandidat kunne ikke ryddes.")
        raise
    return temporary, digest.hexdigest()


def default_forbidden_patterns() -> tuple[Pattern[str], ...]:
    return (
        re.compile(r"pasient", re.IGNORECASE),
        re.compile(r"sample[ ._-]*id", re.IGNORECASE),
        re.compile(r"prøve[ ._-]*id", re.IGNORECASE),
        re.compile(r"work[ ._-]*item", re.IGNORECASE),
        re.compile(r"(?:fødsels|person)[ ._-]*nummer", re.IGNORECASE),
    )
