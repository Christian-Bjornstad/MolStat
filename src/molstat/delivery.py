"""Retry a validated, completed export without repeating the source import."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .unit_settings import write_json
from .recovery import retry_operation, uncancellable_cleanup


def _digest(path):
    def read_digest():
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    return retry_operation(read_digest, stage="publication_candidate_hash")


def _write_manifest(path, payload):
    retry_operation(lambda: write_json(path, payload), stage="publication_manifest_write")


def deliver(publisher, files, destination: Path, candidate_root: Path):
    for name, source in files.items():
        retry_operation(lambda: publisher._validate_candidate(name, source),
                        stage="publication_candidate_validate")
        if source.resolve() != (candidate_root / name).resolve():
            raise ValueError("Publiseringsfilen ligger utenfor kandidatens mappe.")
    manifest = candidate_root / "delivery.json"
    payload = {"created_at": datetime.now(timezone.utc).isoformat(), "status": "pending",
               "files": {name: _digest(source) for name, source in files.items()}}
    _write_manifest(manifest, payload)
    result = publisher.publish(files, destination)
    with uncancellable_cleanup():
        _write_manifest(manifest, {**payload, "status": "published"})
    return result


def retry_pending(publisher, candidates: Path, destination: Path) -> int:
    paths = retry_operation(lambda: tuple(candidates.glob("*/delivery.json")),
                            stage="publication_manifest_scan")
    manifests = [(path, retry_operation(
        lambda: json.loads(path.read_text(encoding="utf-8")),
        stage="publication_manifest_read")) for path in paths]
    if not manifests:
        return 0
    # A newer successful export must never be overwritten by an older failure.
    manifest, payload = max(manifests, key=lambda item: item[1]["created_at"])
    if payload["status"] != "pending":
        return 0
    if set(payload["files"]) != set(publisher.policy.allowed_columns):
        raise ValueError("Publiseringskandidaten stemmer ikke med gjeldende filkontrakt.")
    files = {name: manifest.parent / name for name in payload["files"]}
    if any(_digest(source) != payload["files"][name] for name, source in files.items()):
        raise ValueError("Publiseringskandidaten er endret etter behandling. Kjør behandlingen på nytt.")
    publisher.publish(files, destination)
    with uncancellable_cleanup():
        _write_manifest(manifest, {**payload, "status": "published"})
    return 1
