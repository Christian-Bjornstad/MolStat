let
    Kilde = Csv.Document(
        File.Contents(ProveflytFil),
        [Delimiter = ";", Columns = 15, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Overskrifter = Table.PromoteHeaders(Kilde, [PromoteAllScalars = true]),
    Modellnavn = Table.RenameColumns(
        Overskrifter,
        {{Table.ColumnNames(Overskrifter){6}, "Paa_vei"}}
    ),
    Typer = Table.TransformColumnTypes(
        Modellnavn,
        {
            {"Observert_tidspunkt", type datetime},
            {"Enhet", type text},
            {"Analysegruppe_kode", type text},
            {"Analysegruppe", type text},
            {"Klar", Int64.Type},
            {"Mangler_godkjenning", Int64.Type},
            {"Paa_vei", Int64.Type},
            {"Over_frist", Int64.Type},
            {"Median_klare_timer", type number},
            {"Eldste_klare_timer", type number},
            {"Alvorlighetsgrad", type text},
            {"Ugyldige_rader", Int64.Type},
            {"Ekskluderte_rader", Int64.Type},
            {"Kilde_fersk", type text},
            {"Klassifikatorversjon", Int64.Type}
        },
        "en-US"
    ),
    MedDato = Table.AddColumn(Typer, "Dato", each Date.From([Observert_tidspunkt]), type date)
in
    MedDato
