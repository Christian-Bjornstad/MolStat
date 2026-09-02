from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Mapping, Pattern
from uuid import uuid4


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
        expected_files = set(self.policy.allowed_columns)
        if set(files) != expected_files:
            raise PrivacyViolation(
                "Publiseringskandidaten har et annet filsett enn allowlisten."
            )

        for output_name, source in files.items():
            self._validate_candidate(output_name, source)

        destination.mkdir(parents=True, exist_ok=True)
        staged: dict[str, tuple[Path, str]] = {}
        backups: dict[str, Path] = {}
        installed: list[str] = []
        try:
            for output_name, source in files.items():
                staged[output_name] = _stage_file(source, destination, output_name)

            for output_name in files:
                target = destination / output_name
                if target.exists():
                    backup = destination / f".{output_name}.{uuid4().hex}.bak"
                    os.replace(target, backup)
                    backups[output_name] = backup
                os.replace(staged[output_name][0], target)
                installed.append(output_name)

            for backup in backups.values():
                backup.unlink(missing_ok=True)
        except BaseException:
            for output_name in reversed(installed):
                (destination / output_name).unlink(missing_ok=True)
            for output_name, backup in backups.items():
                if backup.exists():
                    os.replace(backup, destination / output_name)
            raise
        finally:
            for temporary, _digest in staged.values():
                temporary.unlink(missing_ok=True)

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
        except (OSError, UnicodeError, csv.Error) as exc:
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
    with source.open("rb") as reader, tempfile.NamedTemporaryFile(
        mode="wb",
        dir=destination,
        prefix=f".{output_name}.",
        suffix=".tmp",
        delete=False,
    ) as writer:
        temporary = Path(writer.name)
        while chunk := reader.read(1024 * 1024):
            digest.update(chunk)
            writer.write(chunk)
        writer.flush()
        os.fsync(writer.fileno())
    shutil.copystat(source, temporary)
    return temporary, digest.hexdigest()


def default_forbidden_patterns() -> tuple[Pattern[str], ...]:
    return (
        re.compile(r"pasient", re.IGNORECASE),
        re.compile(r"sample[ ._-]*id", re.IGNORECASE),
        re.compile(r"prøve[ ._-]*id", re.IGNORECASE),
        re.compile(r"work[ ._-]*item", re.IGNORECASE),
        re.compile(r"(?:fødsels|person)[ ._-]*nummer", re.IGNORECASE),
    )
