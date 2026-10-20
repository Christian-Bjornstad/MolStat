from pathlib import Path

def default_unit_file(key):
    return Path(__file__).parent / "fixtures" / "units" / f"{key}.json"

def analysis_codes(key):
    import json
    payload = json.loads(default_unit_file(key).read_text(encoding="utf-8"))
    return {code for report in payload["statistics"].values() for code in report["analysis_codes"]}
