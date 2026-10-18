"""Prepare Solide restanse visuals and unit configuration from supplied registers.

Uses the latest supplied Solide register, not the obsolete first lookup.
The workbook's eleven operator-selected groups take precedence over statistics.
--update-default explicitly updates the packaged app definition.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import zipfile


GROUP_CODES = {
    "Sanger Sekvensering": "SOLIDE-SANGER",
    "Enkeltanalyser": "SOLIDE-ENKELT",
    "HTS Childhood": "SOLIDE-CHILDHOOD",
    "HTS OPA": "SOLIDE-OPA",
    "HTS HRR": "SOLIDE-HRR",
    "Sanger": "SOLIDE-SANGER",
    "MLPA": "SOLIDE-MLPA", "MGMT": "SOLIDE-MGMT", "HPV": "SOLIDE-HPV",
    "MLH1": "SOLIDE-MLH1", "Prosigna": "SOLIDE-PROSIGNA",
    "HTS - bestillingsanalyser og varianter": "SOLIDE-HTS-BESTILLING",
    "Childhood": "SOLIDE-CHILDHOOD", "OPA": "SOLIDE-OPA",
    "HRR": "SOLIDE-HRR", "Nanopore": "SOLIDE-NANOPORE",
}

# Explicit selection supplied by the operator; all other workbook rows are excluded.
BACKLOG_LABELS = {
    "3730, Sanger": "Sanger", "3730, MLPA": "MLPA",
    "Biorad, MGMT": "MGMT", "Biorad, HPV": "HPV", "Biorad, MLH1": "MLH1",
    "Nanostring, Prosigna": "Prosigna",
    "HTS, bestillingsanalyser og varianter": "HTS - bestillingsanalyser og varianter",
    "HTS, Childhood": "Childhood", "HTS, OPA": "OPA", "HRR": "HRR", "Nanopore": "Nanopore",
}


def parse_backlog_rows(rows):
    result, seen = [], set()
    for source_label, report_groups, codes, *_ in rows:
        label = BACKLOG_LABELS.get(" ".join(str(source_label or "").split()))
        if not label:
            continue
        groups = [value.strip() for value in str(report_groups).split(",") if value.strip()]
        if not groups or any(not g.startswith("OU-") for g in groups):
            raise ValueError(f"Missing report groups for {label}")
        for code in [value.strip() for value in str(codes).split(",") if value.strip()]:
            if code in seen or not re.fullmatch(r"[A-Z0-9-]+-OU", code):
                raise ValueError(f"Duplicate or invalid backlog code: {code}")
            seen.add(code)
            result.append(dict(code=code, name=code, group=label, report_groups=groups))
    return result


def read_backlog_list(path, statistics_rows):
    from openpyxl import load_workbook
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        rows = parse_backlog_rows(workbook["Rapport - Restanse"].iter_rows(min_row=12, max_row=29, values_only=True))
    finally:
        workbook.close()
    if {r["group"] for r in rows} != set(BACKLOG_LABELS.values()):
        raise ValueError("The supplied backlog list must contain all eleven selected groups")
    lookup = {r["code"]: r for r in statistics_rows}
    # The supplied statistics register gives 15 days for the selected parent
    # analyses in every group; helper codes retain the group's warning thresholds.
    for row in rows:
        row["deadline_days"] = lookup.get(row["code"], {}).get("deadline_days", 15)
    return rows


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_register(path):
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        selected = workbook["Fremgangsmåte og dokumentasjon"]["B25"].value.split(",")
        selected = [code.strip() for code in selected if code.strip()]
        rows = {}
        for code, name, group, deadline, endpoint, active, *_ in list(workbook["Analyseregister"].values)[1:]:
            if code and str(active).casefold() == "ja":
                if code in rows:
                    raise ValueError(f"Duplicate register code: {code}")
                rows[code] = dict(code=code, name=name, group=group,
                                  deadline_days=int(deadline), deadline_endpoint=endpoint)
        if len(set(selected)) != len(selected) or set(selected) - rows.keys():
            raise ValueError("B25 contains duplicate or unregistered/inactive codes")
        return [rows[code] for code in selected]
    finally:
        workbook.close()


def unit_draft(unit, backlog_template, rows):
    result = copy.deepcopy(unit)
    backlog = result["backlog"] = copy.deepcopy(backlog_template)
    # Statistics-only input deliberately remains invalid until real groups exist.
    backlog["report"]["report_groups"] = list(dict.fromkeys(g for r in rows for g in r.get("report_groups", [])))
    backlog["report"]["analysis_codes"] = [r["code"] for r in rows]
    config = backlog["analyses"]
    config["unit"] = {"key": "solide", "label": "Solide"}
    config["analyses"] = []
    for group in dict.fromkeys(r["group"] for r in rows):
        members = [r for r in rows if r["group"] == group]
        deadlines = {r["deadline_days"] for r in members}
        if len(deadlines) != 1:
            raise ValueError("Group has different deadlines; needs separate definitions")
        deadline = deadlines.pop()
        config["analyses"].append({
            "code": GROUP_CODES.get(group, group), "label": group, "group": group,
            "priority": "standard", "enabled": True,
            "source_codes": [r["code"] for r in members], "report_group": ",".join(members[0].get("report_groups", [])),
            "warning_hours": max(1, deadline * 24 * 3 // 4), "critical_hours": deadline * 24,
        })
    return result


def empty_model(model, groups):
    result = copy.deepcopy(model)
    for table in result["model"]["tables"]:
        if table["name"] == "Restanse":
            types = {"string": "text", "dateTime": "datetime", "int64": "Int64.Type", "double": "number"}
            columns = [c for c in table["columns"] if c.get("type", "data") == "data" and "sourceColumn" in c]
            fields = ", ".join('#"' + c["sourceColumn"].replace('"', '""') + '" = nullable ' +
                               types[c["dataType"]] for c in columns)
            table["partitions"][0]["source"] = {"type": "m", "expression": f"#table(type table [{fields}], {{}})"}
            table["description"] = "Solide-restanse"
        elif table["name"] == "DimAnalysegruppe":
            values = ",".join('{"' + code + '","' + label.replace('"', '""') + '"}' for code, label in groups)
            table["partitions"][0]["source"]["expression"] = (
                'DATATABLE("Analysegruppe_kode", STRING, "Analysegruppe", STRING, {' + values + '})')
    return result


def rewrite(value):
    if isinstance(value, dict):
        return {k: rewrite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rewrite(v) for v in value]
    if isinstance(value, str):
        return value.replace("Hemato", "Solide").replace("hemato", "solide")
    return value


def make_report(source, destination, groups):
    with zipfile.ZipFile(source) as archive:
        docs = {name: rewrite(json.loads(archive.read(name))) for name in archive.namelist()
                if name.startswith("Report/definition/") and name.endswith(".json")}
        cards = sorted([n for n in docs if re.search(r"/analysis-(?:cards|card-\d+)/visual.json$", n)],
                       key=lambda n: (0 if "/analysis-cards/" in n else int(n.split("analysis-card-")[1].split("/")[0])))
        retained = set()
        for index, name in enumerate(cards):
            if index >= len(groups):
                del docs[name]
                continue
            doc = docs[name]
            retained.add(doc["name"])
            label = groups[index][1]
            old = doc["filterConfig"]["filters"][0]["filter"]["Where"][0]["Condition"]["In"]["Values"][0][0]["Literal"]["Value"]
            # Replace exact group literals in title, filter and formatting selectors.
            def replace_group(node):
                if isinstance(node, dict):
                    return {k: replace_group(v) for k, v in node.items()}
                if isinstance(node, list):
                    return [replace_group(v) for v in node]
                return "'" + label.replace("'", "''") + "'" if node == old else node
            docs[name] = replace_group(doc)
            title = docs[name]["visual"]["visualContainerObjects"]["title"][0]["properties"]
            title["show"]["expr"]["Literal"]["Value"] = "true"
            title["text"]["expr"]["Literal"]["Value"] = "'" + label.replace("'", "''") + "'"
            docs[name]["visual"]["visualContainerObjects"]["subTitle"][0]["properties"]["show"]["expr"]["Literal"]["Value"] = "false"
        removed = {n.split("/")[-2] for n in cards} - retained
        table_y = max(docs[n]["position"]["y"] + docs[n]["position"]["height"] for n in cards if n in docs) + 20
        for name, doc in docs.items():
            if name.endswith("/page.json"):
                if doc["name"] != "restanse-forklaringer":
                    doc["displayName"] = "Solide Restanse"
                doc["visualInteractions"] = [i for i in doc.get("visualInteractions", [])
                                              if i["source"] not in removed and i["target"] not in removed]
            if name.endswith("/detail-table/visual.json"):
                bottom = doc["position"]["y"] + doc["position"]["height"]
                doc["position"].update(y=table_y, height=bottom - table_y)
            dump(destination / name.removeprefix("Report/"), doc)
        for name in archive.namelist():
            if name.startswith("Report/StaticResources/") and not name.endswith("/"):
                path = destination / name.removeprefix("Report/")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(name))
    return docs


def build(args):
    root = Path(__file__).resolve().parents[1]
    rows = read_register(args.register)
    if args.backlog_list:
        rows = read_backlog_list(args.backlog_list, rows)
    groups = [(GROUP_CODES[group], group) for group in dict.fromkeys(r["group"] for r in rows)]
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    unit = json.loads((root / "src/molstat/defaults/units/solide.json").read_text("utf-8"))
    hemato = json.loads((root / "src/molstat/defaults/units/hemato.json").read_text("utf-8"))
    definition = unit_draft(unit, hemato["backlog"], rows)
    dump(output / ("solide.json" if args.backlog_list else "solide-restanse-utkast.json"), definition)
    dump(output / "solide-register.json", {"source": str(args.backlog_list or args.register), "analyses": rows})
    if args.update_default:
        if not args.backlog_list:
            raise ValueError("An actual backlog list is required to update the app default")
        dump(root / "src/molstat/defaults/units/solide.json", definition)
    model = empty_model(json.loads(args.model.read_text("utf-8-sig")), groups)
    dump(output / "Model/database.json", model)
    make_report(args.source, output / "Solide.Restanse.Report", groups)
    with zipfile.ZipFile(args.source) as source, zipfile.ZipFile(output / "Restanse_Solide_MAL.pbit", "w", zipfile.ZIP_DEFLATED) as target:
        for name in source.namelist():
            if name in {"DataModel", "SecurityBindings"} or name.startswith("Report/"):
                continue
            data = source.read(name)
            if name == "[Content_Types].xml":
                data = data.decode("utf-8-sig").replace("/DataModel\"", "/DataModelSchema\"").encode("utf-8")
            target.writestr(name, data)
        target.writestr("DataModelSchema", json.dumps(model, ensure_ascii=False).encode("utf-16-le"))
        for path in (output / "Solide.Restanse.Report").rglob("*"):
            if path.is_file():
                target.write(path, "Report/" + path.relative_to(output / "Solide.Restanse.Report").as_posix())
    # Save the future refresh query separately. The delivered template never
    # silently displays cached Hemato data or attempts a cloud connection.
    original = next(t for t in json.loads(args.model.read_text("utf-8-sig"))["model"]["tables"] if t["name"] == "Restanse")
    expression = original["partitions"][0]["source"]["expression"]
    if isinstance(expression, list):
        expression = "\n".join(expression)
    (output / "Restanse_Solide_SharePoint.pq").write_text(expression.replace("restansehistorikk_hemato.csv", "restansehistorikk_solide.csv"), encoding="utf-8")
    if args.backlog_list:
        production = copy.deepcopy(model)
        for table in production["model"]["tables"]:
            if table["name"] == "Restanse":
                table["partitions"][0]["source"]["expression"] = expression.replace("restansehistorikk_hemato.csv", "restansehistorikk_solide.csv")
        with zipfile.ZipFile(output / "Restanse_Solide_MAL.pbit") as preview, zipfile.ZipFile(output / "Restanse_Solide.pbit", "w", zipfile.ZIP_DEFLATED) as target:
            for name in preview.namelist():
                data = json.dumps(production, ensure_ascii=False).encode("utf-16-le") if name == "DataModelSchema" else preview.read(name)
                target.writestr(name, data)
    print(json.dumps({"template": str(output / "Restanse_Solide_MAL.pbit"), "groups": groups,
                      "codes": len(rows), "status": "ready_for_first_extract" if args.backlog_list else "awaiting_verified_lvms_backlog_definition"}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--register", type=Path, required=True)
    parser.add_argument("--backlog-list", type=Path)
    parser.add_argument("--update-default", action="store_true")
    parser.add_argument("--model", type=Path, required=True, help="pbi-tools Raw database.json")
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args())
