"""Independent counts, time arithmetic, every DAX measure and report binding."""
import csv
import json
import statistics
import sys
from pathlib import Path
from pbi_cli.core.session import connect, disconnect

root = Path(__file__).resolve().parents[1] / "powerbi/Patolog_Forlop_20261018"
schema = json.loads((root / "Model/database.json").read_text("utf-8"))["model"]
audit = json.loads((root / "Data/source_audit.json").read_text("utf-8"))
session = connect(sys.argv[1])

def query(dax):
    cmd = session.adomd_connection.CreateCommand()
    cmd.CommandText = dax
    reader = cmd.ExecuteReader()
    rows = []
    while reader.Read():
        rows.append({reader.GetName(i): str(reader.GetValue(i)) for i in range(reader.FieldCount)})
    reader.Close()
    return rows

metrics = [m for table in schema["tables"] for m in table.get("measures", [])]
result = query('EVALUATE ROW(' + ','.join('"' + str(i) + '",[' + m["name"] + ']' for i,m in enumerate(metrics)) + ')')[0]
measures = {m["name"]: result[f"[{i}]"] for i,m in enumerate(metrics)}
for name, expected in [("Mottatte prøver", "samples"), ("Godkjente prøver", "approved_samples"),
        ("Åpne prøver", "open_samples"), ("Ufargede glass", "uncolored_glass"), ("Unike glass", "unique_glass"),
        ("Kjede N", "valid_chains")]:
    assert int(measures[name]) == audit[expected], (name, measures[name], audit[expected])
with (root / "Data/Prøver.csv").open(encoding="utf-8-sig") as stream:
    samples = list(csv.DictReader(stream, delimiter=";"))
expected = statistics.median(float(row["SvartidDager"]) for row in samples if row["SvartidDager"])
assert abs(float(measures["Median svartid dager"]) - expected) < 1e-9
assert abs(sum(float(measures[name]) for name in ["Ankomst → makro", "Makro → støpt", "Støpt → snittet", "Snittet → farget", "Farget → godkjent"])
           - float(measures["Kjede total gjennomsnitt"])) < 1e-9

with (root / "Data/Signeringer.csv").open(encoding="utf-8-sig") as stream:
    signatures = list(csv.DictReader(stream, delimiter=";"))
doctor_checks = []
for doctor in sorted({r["Lege"] for r in signatures}):
    rows = [r for r in signatures if r["Lege"] == doctor and r["GodkjentDato"]]
    unique = {r["Prøvenummer"]: r for r in rows}
    values = [float(r["LegeDager"]) for r in unique.values() if r["LegeDager"]]
    escaped = doctor.replace('"', '""')
    got = query('EVALUATE CALCULATETABLE(ROW("N",[Signerte prøver],"TidN",[Lege N tid],"Median",[Lege median farget til godkjent],"Glass",[Lege glass på godkjente prøver]),TREATAS({"' + escaped + '"},Leger[Lege]))')[0]
    count = lambda value: 0 if value in {"", "None"} else int(value)
    assert count(got["[N]"]) == len(unique), (doctor, got)
    assert count(got["[TidN]"]) == len(values), (doctor, got)
    assert count(got["[Glass]"]) == sum(int(r["AntallGlass"]) for r in unique.values()), (doctor, got)
    if values:
        assert abs(float(got["[Median]"]) - statistics.median(values)) < 1e-9, (doctor, got)
    for role in sorted({r["Rolle"] for r in rows}):
        expected = len({r["Prøvenummer"] for r in rows if r["Rolle"] == role})
        role_filter = role.replace('"', '""')
        actual = query('EVALUATE CALCULATETABLE(ROW("N",[Signerte prøver]),TREATAS({"' + escaped + '"},Leger[Lege]),TREATAS({"' + role_filter + '"},Signeringer[Rolle]))')[0]
        assert count(actual["[N]"]) == expected
    doctor_checks.append({"samples": len(unique), "valid_times": len(values)})

columns = {t["name"]: {c["name"] for c in t["columns"]} for t in schema["tables"]}
measure_names = {m["name"] for m in metrics}
def walk(node):
    if isinstance(node, dict):
        for kind in ("Column", "Measure"):
            field = node.get(kind, {})
            entity = field.get("Expression", {}).get("SourceRef", {}).get("Entity")
            if entity:
                assert entity in columns, field
                assert field["Property"] in (columns[entity] if kind == "Column" else measure_names), field
        for value in node.values(): walk(value)
    elif isinstance(node, list):
        for value in node: walk(value)
visual_count = 0
for report in (root / "Patolog.Statistikk.Report", root / "Patolog.Restanse.Report"):
    for path in report.glob("definition/pages/*/visuals/*/visual.json"):
        doc = json.loads(path.read_text("utf-8")); walk(doc); visual_count += 1
        visual = doc["visual"]
        if "chart" in visual.get("visualType", "").lower():
            assert visual["objects"]["valueAxis"][0]["properties"]["labelDisplayUnits"]["expr"]["Literal"]["Value"] == "1D"
assert "'Hemato og Beinmarg'" in json.dumps([json.loads(p.read_text("utf-8")) for p in
    (root / "Patolog.Restanse.Report").glob("definition/pages/*/visuals/analysis-card*/visual.json")],ensure_ascii=False)
result = {"audit": audit, "measures": measures, "visuals_checked": visual_count, "doctor_scenarios": doctor_checks,
    "age_bands": query("EVALUATE SUMMARIZE('Prøver','Prøver'[Aldersgruppe],'Prøver'[AldersgruppeSort]) ORDER BY 'Prøver'[AldersgruppeSort]")}
(root / "validation/updated_model.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"PASS: {len(metrics)} measures, {visual_count} visual bindings, source counts, median, stage sum and full numeric axes")
disconnect(session)
