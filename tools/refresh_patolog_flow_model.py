"""Refresh an explicitly selected local Power BI instance from generated facts."""
import json
import sys
from pathlib import Path
from pbi_cli.core.session import connect, disconnect

source = Path(__file__).resolve().parents[1] / "powerbi/Patolog_Forlop_20261018/Model/database.json"
schema = json.loads(source.read_text("utf-8"))["model"]
session = connect(sys.argv[1])
from Microsoft.AnalysisServices.Tabular import DataColumn, DataType, RefreshType, NamedExpression, ExpressionKind, Measure

for definition in schema.get("expressions", []):
    expression = session.model.Expressions.Find(definition["name"])
    if expression is None:
        expression = NamedExpression()
        expression.Name = definition["name"]
        expression.Kind = ExpressionKind.M
        session.model.Expressions.Add(expression)
    expression.Expression = definition["expression"]

for definition in schema["tables"]:
    table = session.model.Tables.Find(definition["name"])
    if table is None:
        raise ValueError("Selected model is not the pathology workflow model")
    table.Partitions.Find(definition["name"]).Source.Expression = definition["partitions"][0]["source"]["expression"]
    for field in definition["columns"]:
        column = table.Columns.Find(field["name"])
        if column is None:
            column = DataColumn()
            column.Name = field["name"]
            column.SourceColumn = field["sourceColumn"]
            table.Columns.Add(column)
        column.DataType = {"int64": DataType.Int64, "double": DataType.Double,
            "string": DataType.String, "dateTime": DataType.DateTime}[field["dataType"]]
        column.FormatString = field.get("formatString", "")
        column.IsHidden = field.get("isHidden", False)
    for field in definition["columns"]:
        if "sortByColumn" in field:
            table.Columns.Find(field["name"]).SortByColumn = table.Columns.Find(field["sortByColumn"])
    for measure in definition.get("measures", []):
        existing = table.Measures.Find(measure["name"])
        if existing is None:
            existing = Measure()
            existing.Name = measure["name"]
            table.Measures.Add(existing)
        existing.Expression = measure["expression"]
        existing.FormatString = measure["formatString"]
session.model.RequestRefresh(RefreshType.Full)
session.model.SaveChanges()
query = session.adomd_connection.CreateCommand()
query.CommandText = 'EVALUATE ROW("Prøver",COUNTROWS(\'Prøver\'),"Glass",COUNTROWS(Glass),"Åpne",[Alle åpne prøver],"Tid",[Datatid])'
reader = query.ExecuteReader()
while reader.Read():
    print(json.dumps({reader.GetName(i): str(reader.GetValue(i)) for i in range(reader.FieldCount)}, ensure_ascii=True))
reader.Close()
disconnect(session)
