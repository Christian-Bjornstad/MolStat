from pathlib import Path


def test_repository_contains_no_production_csv_or_database() -> None:
    root = Path(__file__).parents[1]
    tracked_candidates = [
        *root.rglob("*.sqlite"),
        *root.rglob("*.sqlite3"),
        *root.rglob("*.db"),
    ]
    assert tracked_candidates == []
