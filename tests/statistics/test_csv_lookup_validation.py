import pytest

from molstat._statistics.specialized_lookup import validate_lookup


HEADER = "Analyse;Analysenavn;Rapportgruppe;Svarfrist;Svartidstype\n"


@pytest.mark.parametrize("contents", [
    "SYNTHETIC-OU;Navn\n",
    "SYNTHETIC-OU;Navn;FISH;5;Analysetid;Extra\n",
    ";Navn;FISH;5;Analysetid\n",
    " SYNTHETIC-OU ;Navn;FISH;5;Analysetid\n",
])
def test_specialized_lookup_rejects_incomplete_or_shifted_rows(tmp_path, contents):
    path = tmp_path / "lookup.csv"
    path.write_text(HEADER + contents, encoding="utf-8")
    with pytest.raises(ValueError, match="Lookup-filen"):
        validate_lookup(path, "fish", {"SYNTHETIC-OU"})


def test_specialized_lookup_rejects_duplicate_headers(tmp_path):
    path = tmp_path / "lookup.csv"
    path.write_text(HEADER.rstrip("\n") + ";Analyse\nSYNTHETIC-OU;Navn;FISH;5;Analysetid;SYNTHETIC-OU\n")
    with pytest.raises(ValueError, match="kolonnenavn"):
        validate_lookup(path, "fish", {"SYNTHETIC-OU"})
