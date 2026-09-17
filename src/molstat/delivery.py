"""Retry a validated, completed export without repeating the source import."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .unit_settings import write_json


def _digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def deliver(publisher, files, destination: Path, candidate_root: Path):
    for name, source in files.items():
        publisher._validate_candidate(name, source)
        if source.resolve() != (candidate_root / name).resolve():
            raise ValueError("Publiseringsfilen ligger utenfor kandidatens mappe.")
    manifest = candidate_root / "delivery.json"
    payload = {"created_at": datetime.now(timezone.utc).isoformat(), "status": "pending",
               "files": {name: _digest(source) for name, source in files.items()}}
    write_json(manifest, payload)
    result = publisher.publish(files, destination)
    write_json(manifest, {**payload, "status": "published"})
    return result


def retry_pending(publisher, candidates: Path, destination: Path) -> int:
    manifests = [(path, json.loads(path.read_text(encoding="utf-8")))
                 for path in candidates.glob("*/delivery.json")]
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
    write_json(manifest, {**payload, "status": "published"})
    return 1
