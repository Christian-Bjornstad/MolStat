from pathlib import Path
import pytest

from molstat.publisher import PublicationPolicy, SharePointPublisher
from molstat.delivery import deliver, retry_pending


def test_failed_delivery_can_be_retried_without_fetch_or_import(tmp_path, monkeypatch):
    source = tmp_path / "processed" / "hemato" / "statistics" / "run1" / "antall.csv"
    source.parent.mkdir(parents=True)
    source.write_text("Analyse;Antall\nSYNTHETIC;1\n")
    publisher = SharePointPublisher(PublicationPolicy({"antall.csv": frozenset({"Analyse", "Antall"})}, ()))
    original = publisher.publish
    monkeypatch.setattr(publisher, "publish", lambda *a: (_ for _ in ()).throw(PermissionError("locked")))
    with pytest.raises(PermissionError):
        deliver(publisher, {"antall.csv": source}, tmp_path / "sharepoint", source.parent)
    assert (source.parent / "delivery.json").is_file()
    monkeypatch.setattr(publisher, "publish", original)
    assert retry_pending(publisher, source.parent.parent, tmp_path / "sharepoint") == 1
    assert (tmp_path / "sharepoint" / "antall.csv").read_bytes() == source.read_bytes()
    assert retry_pending(publisher, source.parent.parent, tmp_path / "sharepoint") == 0


def test_altered_candidate_is_not_republished(tmp_path):
    import json
    source = tmp_path / "run" / "antall.csv"
    source.parent.mkdir()
    source.write_text("Analyse;Antall\nSYNTHETIC;1\n")
    publisher = SharePointPublisher(PublicationPolicy({"antall.csv": frozenset({"Analyse", "Antall"})}, ()))
    deliver(publisher, {"antall.csv": source}, tmp_path / "sharepoint", source.parent)
    manifest = source.parent / "delivery.json"
    payload = json.loads(manifest.read_text()); payload["status"] = "pending"
    manifest.write_text(json.dumps(payload))
    source.write_text("Analyse;Antall\nSYNTHETIC;999\n")
    with pytest.raises(ValueError, match="endret"):
        retry_pending(publisher, tmp_path, tmp_path / "sharepoint")
