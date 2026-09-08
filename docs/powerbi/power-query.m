let
    Kilde = Csv.Document(
        File.Contents(PrøveflytFil),
        [Delimiter = ";", Columns = 15, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Overskrifter = Table.PromoteHeaders(Kilde, [PromoteAllScalars = true]),
    Typer = Table.TransformColumnTypes(
        Overskrifter,
        {
            {"Observert_tidspunkt", type datetime},
            {"Enhet", type text},
            {"Analysegruppe_kode", type text},
            {"Analysegruppe", type text},
            {"Klar", Int64.Type},
            {"Mangler_godkjenning", Int64.Type},
            {"På_vei", Int64.Type},
            {"Over_frist", Int64.Type},
            {"Median_klare_timer", type number},
            {"Eldste_klare_timer", type number},
            {"Alvorlighetsgrad", type text},
            {"Ugyldige_rader", Int64.Type},
            {"Ekskluderte_rader", Int64.Type},
            {"Kilde_fersk", type text},
            {"Klassifikatorversjon", Int64.Type}
        },
        "nb-NO"
    ),
    MedDato = Table.AddColumn(Typer, "Dato", each Date.From([Observert_tidspunkt]), type date)
in
    MedDato
