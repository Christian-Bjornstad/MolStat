"""Add the aggregate process-count page to the existing pathology PBIP."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil

import build_hemato_statistikk_v4_report as base
from build_hemato_statistikk_v5_report import PolishedPage


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "powerbi" / "Patolog_Statistikk_V1"
MODEL = PROJECT / "Patolog.SemanticModel" / "definition"
REPORT = PROJECT / "Patolog Statistikk.Report" / "definition" / "pages"
PAGE_ID = "0000000000000000006e"


def build() -> None:
    data_file = PROJECT / "TemplateData" / "FactProsess.csv"
    if not data_file.exists():
        data_file.parent.mkdir(parents=True, exist_ok=True)
        with data_file.open("w", encoding="utf-8-sig", newline="") as stream:
            csv.writer(stream, delimiter=";").writerow((
                "Maaned", "Profil", "Lab", "Prosesskode", "Prosessgruppe",
                "AntallProver", "AntallBlokker", "AntallGlass", "UttrekkTom",
            ))
    model = MODEL / "model.tmdl"
    content = model.read_text(encoding="utf-8")
    if "ref table FactProsess" not in content:
        model.write_text(content.rstrip() + "\nref table FactProsess\n", encoding="utf-8")
    table = MODEL / "tables" / "FactProsess.tmdl"
    table.write_text(_table_tmdl(data_file), encoding="utf-8")

    metadata = REPORT / "pages.json"
    pages = json.loads(metadata.read_text(encoding="utf-8"))
    existing = pages["pageOrder"]
    if PAGE_ID not in existing:
        existing.append(PAGE_ID)
    pages["pageOrder"] = existing
    metadata.write_text(json.dumps(pages, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    base.PAGES = REPORT
    base.PAGE_DEFS = [
        (page_id, json.loads((REPORT / page_id / "page.json").read_text(encoding="utf-8"))["displayName"])
        for page_id in existing if page_id != PAGE_ID
    ] + [(PAGE_ID, "Prosessvolum")]
    page = PolishedPage(PAGE_ID, "Prosessvolum", "Registrerte rekvisisjoner, blokker og glass", "Periode: opprettelsesdato")
    page.textbox("brand", 18, 16, 150, 62, [("OUS", 23, "#FFFFFF", True), ("Patologi", 10, "#CFE3F2", False)])
    page.slicer("month", 204, 92, 220, 66, "FactProsess", "Maaned", "Måned")
    page.slicer("group", 432, 92, 280, 66, "FactProsess", "Prosessgruppe", "Prosessgruppe")
    page.slicer("profile", 720, 92, 225, 66, "FactProsess", "Profil", "Profil")
    page.slicer("lab", 953, 92, 299, 66, "FactProsess", "Lab", "Laboratorium")
    for vid, x, metric, label, color in (
        ("samples", 204, "Registrerte prøver", "Registrerte prøver", "blue"),
        ("blocks", 468, "Blokker", "Blokker", "teal"),
        ("slides", 732, "Glass", "Glass", "blue"),
        ("slides-per-sample", 996, "Glass per prøve", "Glass per prøve", "amber"),
    ):
        page.card(vid, x, 214, 256, 100, "FactProsess", metric, label, base.C[color])
    measure = lambda name: base.measure("FactProsess", name)
    page.chart("trend", "clusteredColumnChart", 204, 346, 520, 306,
               "Prøver per måned", "", {
                   "Category": [base.column("FactProsess", "Maaned")],
                   "Y": [measure("Registrerte prøver")],
               }, show_legend=False)
    page.chart("groups", "clusteredBarChart", 740, 346, 512, 306,
               "Prøver per prosessgruppe", "", {
                   "Category": [base.column("FactProsess", "Prosessgruppe")],
                   "Y": [measure("Registrerte prøver")],
                   "Tooltips": [measure("Blokker"), measure("Glass")],
               }, show_legend=False, show_labels=True,
               sort_field=measure("Registrerte prøver"))
    page.textbox("footer", 204, 668, 1048, 26, [(
        "LVMS-aggregater per profil/lab/prosess · summen er ikke distinkte prøver på tvers av kilderader",
        9, base.C["muted"], False,
    )])
    navigation = REPORT / PAGE_ID / "visuals" / "navigation-10" / "visual.json"
    for old_id in existing:
        if old_id == PAGE_ID:
            continue
        target = REPORT / old_id / "visuals" / "navigation-10" / "visual.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(navigation, target)


def _table_tmdl(data_file: Path) -> str:
    fields = (
        ("Maaned", "dateTime"), ("Profil", "string"), ("Lab", "string"),
        ("Prosesskode", "string"), ("Prosessgruppe", "string"),
        ("AntallProver", "int64"), ("AntallBlokker", "int64"),
        ("AntallGlass", "int64"), ("UttrekkTom", "dateTime"),
    )
    lines = ["table FactProsess", "\tlineageTag: 9836b122-679a-48cc-85d5-66e145ea73ce"]
    for name, kind in fields:
        lines += [f"\n\tcolumn '{name}'", f"\t\tdataType: {kind}",
                  "\t\tsummarizeBy: none", f"\t\tsourceColumn: {name}"]
        if kind == "dateTime":
            lines.append("\t\tformatString: yyyy-MM-dd")
    for name, expression, fmt in (
        ("Registrerte prøver", "SUM(FactProsess[AntallProver])", "#,##0"),
        ("Blokker", "SUM(FactProsess[AntallBlokker])", "#,##0"),
        ("Glass", "SUM(FactProsess[AntallGlass])", "#,##0"),
        ("Glass per prøve", "DIVIDE([Glass],[Registrerte prøver])", "0.0"),
    ):
        lines += [f"\n\tmeasure '{name}' =", f"\t\t\t{expression}", f"\t\tformatString: {fmt}"]
    transforms = []
    for name, kind in fields:
        expression = ("DateTime.FromText(_, [Culture=\"en-US\"])" if kind == "dateTime"
                      else "Int64.From(Number.FromText(_, \"en-US\"))" if kind == "int64" else "_")
        mtype = "datetime" if kind == "dateTime" else "number" if kind == "int64" else "text"
        transforms.append(f'{{"{name}", each if _ = "" then null else {expression}, type nullable {mtype}}}')
    m = (
        "let\n"
        f'    Raw = Csv.Document(File.Contents("{data_file}"), [Delimiter=";",Encoding=65001,QuoteStyle=QuoteStyle.Csv]),\n'
        "    Headers = Table.PromoteHeaders(Raw,[PromoteAllScalars=true]),\n"
        f"    Typed = Table.TransformColumns(Headers,{{{','.join(transforms)}}})\n"
        "in Typed"
    )
    lines += ["\n\tpartition FactProsess = m", "\t\tmode: import", "\t\tsource ="]
    lines += ["\t\t\t\t" + line for line in m.splitlines()]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    build()
