from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "powerbi" / "Hemato_Statistikk_Optimert"
BASELINE = ROOT / "powerbi" / "Hemato_Statistikk_Optimert.PbixProj" / "Model"
DEFINITION = PROJECT / "Hemato Semantikk" / "definition"
TABLES = DEFINITION / "tables"


def partition_tail(table_name: str) -> str:
    baseline_path = BASELINE / "tables" / f"{table_name}.tmdl"
    project_path = TABLES / f"{table_name}.tmdl"
    source_path = baseline_path if baseline_path.exists() else project_path
    source = source_path.read_text(encoding="utf-8")
    marker = f"\n\tpartition {table_name} = m"
    return source[source.index(marker) :].rstrip() + "\n"


def remove_variations(text: str) -> str:
    return re.sub(r"\n\t\tvariation Variasjon\n(?:\t{3,}.*\n)+", "\n", text)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def build_calendar() -> None:
    write(
        TABLES / "Dato.tmdl",
        """table Dato
\tdataCategory: Time

\tcolumn Date
\t\tdataType: dateTime
\t\tformatString: dd.MM.yyyy
\t\tisKey
\t\tsummarizeBy: none
\t\tisNameInferred
\t\tsourceColumn: [Date]

\tcolumn År = YEAR ( Dato[Date] )
\t\tformatString: 0
\t\tsummarizeBy: none

\tcolumn Kvartal = "K" & FORMAT ( Dato[Date], "Q" )
\t\tsummarizeBy: none

\tcolumn MånedNr = MONTH ( Dato[Date] )
\t\tformatString: 0
\t\tsummarizeBy: none

\tcolumn Måned = FORMAT ( Dato[Date], "mmmm" )
\t\tsummarizeBy: none
\t\tsortByColumn: MånedNr

\tcolumn ÅrMåned = FORMAT ( Dato[Date], "yyyy-MM" )
\t\tsummarizeBy: none
\t\tsortByColumn: ÅrMånedSort

\tcolumn ÅrMånedSort = YEAR ( Dato[Date] ) * 100 + MONTH ( Dato[Date] )
\t\tformatString: 0
\t\tsummarizeBy: none

\tcolumn ISOÅr = YEAR ( Dato[Date] - WEEKDAY ( Dato[Date], 2 ) + 4 )
\t\tformatString: 0
\t\tsummarizeBy: none

\tcolumn ISOUke = WEEKNUM ( Dato[Date], 21 )
\t\tformatString: 00
\t\tsummarizeBy: none

\tcolumn ÅrUke = FORMAT ( Dato[ISOÅr], "0000" ) & "-U" & FORMAT ( Dato[ISOUke], "00" )
\t\tsummarizeBy: none
\t\tsortByColumn: UkeStart

\tcolumn UkeStart = Dato[Date] - WEEKDAY ( Dato[Date], 2 ) + 1
\t\tformatString: dd.MM.yyyy
\t\tsummarizeBy: none

\tpartition Dato = calculated
\t\tmode: import
\t\tsource =
\t\t\t\tVAR AlleDatoer =
\t\t\t\t\tUNION (
\t\t\t\t\t\tSELECTCOLUMNS ( antall, "D", antall[Tidspunkt.analysebestilling] ),
\t\t\t\t\t\tSELECTCOLUMNS ( resultater, "D", resultater[Tidspunkt.prøvetaking] ),
\t\t\t\t\t\tSELECTCOLUMNS ( resultater, "D", resultater[Tidspunkt.analysebestilling] ),
\t\t\t\t\t\tSELECTCOLUMNS ( resultater, "D", resultater[Tidspunkt.analyseresultat] ),
\t\t\t\t\t\tSELECTCOLUMNS ( resultater, "D", resultater[Tidspunkt.godkjenning] )
\t\t\t\t\t)
\t\t\t\tVAR MinDato = DATE ( YEAR ( MINX ( AlleDatoer, [D] ) ), 1, 1 )
\t\t\t\tVAR MaksDato = DATE ( YEAR ( MAXX ( AlleDatoer, [D] ) ), 12, 31 )
\t\t\t\tRETURN CALENDAR ( MinDato, MaksDato )
""",
    )


def build_perspective_table() -> None:
    write(
        TABLES / "Svartidsperspektiv.tmdl",
        """table Svartidsperspektiv

\tcolumn Perspektiv
\t\tdataType: string
\t\tsummarizeBy: none
\t\tsourceColumn: [Perspektiv]
\t\tsortByColumn: Sortering

\tcolumn Sortering
\t\tdataType: int64
\t\tformatString: 0
\t\tsummarizeBy: none
\t\tsourceColumn: [Sortering]

\tpartition Svartidsperspektiv = calculated
\t\tmode: import
\t\tsource = DATATABLE ( "Perspektiv", STRING, "Sortering", INTEGER, { { "Pasientforløp", 1 }, { "Seksjonstid", 2 }, { "Enhetstid", 3 } } )
""",
    )


RESULTATER_HEADER = r'''table resultater

	measure 'Valgt perspektiv' = SELECTEDVALUE ( Svartidsperspektiv[Perspektiv], "Enhetstid" )

	measure 'Antall resultater' = COUNTROWS ( resultater )
		formatString: #,0

	measure 'Median pasientforløp dager' = MEDIAN ( resultater[Svartid pasient dager] )
		formatString: 0.0

	measure 'Median seksjonstid dager' = MEDIAN ( resultater[Svartid seksjon dager] )
		formatString: 0.0

	measure 'Median enhetstid dager' = MEDIAN ( resultater[Svartid enhet dager] )
		formatString: 0.0

	measure 'Antall gyldige svartider' =
			VAR Perspektiv = [Valgt perspektiv]
			RETURN
				SWITCH (
					Perspektiv,
					"Pasientforløp", COUNT ( resultater[Svartid pasient dager] ),
					"Seksjonstid", COUNT ( resultater[Svartid seksjon dager] ),
					COUNT ( resultater[Svartid enhet dager] )
				)
		formatString: #,0

	measure 'Median svartid dager' =
			VAR Perspektiv = [Valgt perspektiv]
			RETURN
				SWITCH (
					Perspektiv,
					"Pasientforløp", MEDIAN ( resultater[Svartid pasient dager] ),
					"Seksjonstid", MEDIAN ( resultater[Svartid seksjon dager] ),
					MEDIAN ( resultater[Svartid enhet dager] )
				)
		formatString: 0.0

	measure 'Gjennomsnitt svartid dager' =
			VAR Perspektiv = [Valgt perspektiv]
			RETURN
				SWITCH (
					Perspektiv,
					"Pasientforløp", AVERAGE ( resultater[Svartid pasient dager] ),
					"Seksjonstid", AVERAGE ( resultater[Svartid seksjon dager] ),
					AVERAGE ( resultater[Svartid enhet dager] )
				)
		formatString: 0.0

	measure 'P75 svartid dager' =
			VAR Perspektiv = [Valgt perspektiv]
			RETURN
				SWITCH (
					Perspektiv,
					"Pasientforløp", PERCENTILEX.INC ( FILTER ( resultater, NOT ISBLANK ( resultater[Svartid pasient dager] ) ), resultater[Svartid pasient dager], 0.75 ),
					"Seksjonstid", PERCENTILEX.INC ( FILTER ( resultater, NOT ISBLANK ( resultater[Svartid seksjon dager] ) ), resultater[Svartid seksjon dager], 0.75 ),
					PERCENTILEX.INC ( FILTER ( resultater, NOT ISBLANK ( resultater[Svartid enhet dager] ) ), resultater[Svartid enhet dager], 0.75 )
				)
		formatString: 0.0

	measure 'P90 svartid dager' =
			VAR Perspektiv = [Valgt perspektiv]
			RETURN
				SWITCH (
					Perspektiv,
					"Pasientforløp", PERCENTILEX.INC ( FILTER ( resultater, NOT ISBLANK ( resultater[Svartid pasient dager] ) ), resultater[Svartid pasient dager], 0.90 ),
					"Seksjonstid", PERCENTILEX.INC ( FILTER ( resultater, NOT ISBLANK ( resultater[Svartid seksjon dager] ) ), resultater[Svartid seksjon dager], 0.90 ),
					PERCENTILEX.INC ( FILTER ( resultater, NOT ISBLANK ( resultater[Svartid enhet dager] ) ), resultater[Svartid enhet dager], 0.90 )
				)
		formatString: 0.0

	measure 'Antall innen individuell frist' =
			VAR Perspektiv = [Valgt perspektiv]
			RETURN
				SUMX (
					resultater,
					VAR Varighet = SWITCH ( Perspektiv, "Pasientforløp", resultater[Svartid pasient dager], "Seksjonstid", resultater[Svartid seksjon dager], resultater[Svartid enhet dager] )
					RETURN IF ( NOT ISBLANK ( Varighet ) && NOT ISBLANK ( resultater[Svarfrist] ) && Varighet <= resultater[Svarfrist], 1, 0 )
				)
		formatString: #,0

	measure 'Antall over individuell frist' =
			VAR Perspektiv = [Valgt perspektiv]
			RETURN
				SUMX (
					resultater,
					VAR Varighet = SWITCH ( Perspektiv, "Pasientforløp", resultater[Svartid pasient dager], "Seksjonstid", resultater[Svartid seksjon dager], resultater[Svartid enhet dager] )
					RETURN IF ( NOT ISBLANK ( Varighet ) && NOT ISBLANK ( resultater[Svarfrist] ) && Varighet > resultater[Svarfrist], 1, 0 )
				)
		formatString: #,0

	measure 'Andel innen individuell frist' = DIVIDE ( [Antall innen individuell frist], [Antall innen individuell frist] + [Antall over individuell frist] )
		formatString: 0.0%

	measure 'Antall ekskludert datakvalitet' = COUNTROWS ( resultater ) - [Antall gyldige svartider]
		formatString: #,0

	measure 'Andel ekskludert datakvalitet' = DIVIDE ( [Antall ekskludert datakvalitet], COUNTROWS ( resultater ) )
		formatString: 0.0%

	measure 'Entydig svarfrist dager' = SELECTEDVALUE ( resultater[Svarfrist] )
		formatString: 0

	measure 'Godkjenningsetterslep median dager' = MEDIAN ( resultater[Godkjenningsetterslep dager] )
		formatString: 0.0

	measure 'Datakvalitet OK' = CALCULATE ( COUNTROWS ( resultater ), resultater[Datakvalitet status] = "OK" )
		formatString: #,0

	measure 'Datakvalitet avvik' = COUNTROWS ( resultater ) - [Datakvalitet OK]
		formatString: #,0

	measure 'Svartid status tekst' =
			VAR Andel = [Andel innen individuell frist]
			RETURN SWITCH ( TRUE (), ISBLANK ( Andel ), "Ingen gyldige observasjoner", Andel >= 0.90, "På mål", Andel >= 0.75, "Følg med", "Krever oppfølging" )

	measure 'Svartid status farge' =
			VAR Andel = [Andel innen individuell frist]
			RETURN SWITCH ( TRUE (), ISBLANK ( Andel ), "#64748B", Andel >= 0.90, "#0F766E", Andel >= 0.75, "#B45309", "#B42318" )

	measure 'Fireukers glidende volum' = DIVIDE ( CALCULATE ( [Antall analyser], DATESINPERIOD ( Dato[Date], MAX ( Dato[Date] ), -28, DAY ) ), 4 )
		formatString: #,0

	measure 'Lavvolumgrense P10' = PERCENTILEX.INC ( ALLSELECTED ( Dato[ÅrUke] ), CALCULATE ( [Antall analyser] ), 0.10 )
		formatString: #,0

	column Materiale
		dataType: string
		summarizeBy: none
		sourceColumn: Materiale

	column Analyse
		dataType: string
		summarizeBy: none
		sourceColumn: Analyse

	column Nukleinsyre
		dataType: string
		summarizeBy: none
		sourceColumn: Nukleinsyre

	column Rapportgruppe
		dataType: string
		summarizeBy: none
		sourceColumn: Rapportgruppe

	column 'Tidspunkt.prøvetaking'
		dataType: dateTime
		formatString: dd.MM.yyyy HH:mm
		summarizeBy: none
		sourceColumn: Tidspunkt.prøvetaking

	column 'Tidspunkt.opprettet'
		dataType: dateTime
		formatString: dd.MM.yyyy HH:mm
		summarizeBy: none
		sourceColumn: Tidspunkt.opprettet

	column 'Tidspunkt.analysebestilling'
		dataType: dateTime
		formatString: dd.MM.yyyy HH:mm
		summarizeBy: none
		sourceColumn: Tidspunkt.analysebestilling

	column 'Tidspunkt.analyseresultat'
		dataType: dateTime
		formatString: dd.MM.yyyy HH:mm
		summarizeBy: none
		sourceColumn: Tidspunkt.analyseresultat

	column 'Tidspunkt.godkjenning'
		dataType: dateTime
		formatString: dd.MM.yyyy HH:mm
		summarizeBy: none
		sourceColumn: Tidspunkt.godkjenning

	column 'Ekstraksjon.analysebestilling'
		dataType: dateTime
		formatString: dd.MM.yyyy HH:mm
		summarizeBy: none
		sourceColumn: Ekstraksjon.analysebestilling

	column 'Ekstraksjon.ferdig'
		dataType: dateTime
		formatString: dd.MM.yyyy HH:mm
		summarizeBy: none
		sourceColumn: Ekstraksjon.ferdig

	column Svarfrist
		dataType: int64
		formatString: 0
		summarizeBy: none
		sourceColumn: Svarfrist

	column 'Prøvetaking dato' = IF ( ISBLANK ( resultater[Tidspunkt.prøvetaking] ), BLANK (), DATE ( YEAR ( resultater[Tidspunkt.prøvetaking] ), MONTH ( resultater[Tidspunkt.prøvetaking] ), DAY ( resultater[Tidspunkt.prøvetaking] ) ) )
		formatString: dd.MM.yyyy
		summarizeBy: none

	column 'Analysebestilling dato' = IF ( ISBLANK ( resultater[Tidspunkt.analysebestilling] ), BLANK (), DATE ( YEAR ( resultater[Tidspunkt.analysebestilling] ), MONTH ( resultater[Tidspunkt.analysebestilling] ), DAY ( resultater[Tidspunkt.analysebestilling] ) ) )
		formatString: dd.MM.yyyy
		summarizeBy: none

	column 'Analyseresultat dato' = IF ( ISBLANK ( resultater[Tidspunkt.analyseresultat] ), BLANK (), DATE ( YEAR ( resultater[Tidspunkt.analyseresultat] ), MONTH ( resultater[Tidspunkt.analyseresultat] ), DAY ( resultater[Tidspunkt.analyseresultat] ) ) )
		formatString: dd.MM.yyyy
		summarizeBy: none

	column 'Godkjenning dato' = IF ( ISBLANK ( resultater[Tidspunkt.godkjenning] ), BLANK (), DATE ( YEAR ( resultater[Tidspunkt.godkjenning] ), MONTH ( resultater[Tidspunkt.godkjenning] ), DAY ( resultater[Tidspunkt.godkjenning] ) ) )
		formatString: dd.MM.yyyy
		summarizeBy: none

	column 'Enhet starttid' =
			VAR Bestilling = resultater[Tidspunkt.analysebestilling]
			VAR Ekstraksjon = resultater[Ekstraksjon.ferdig]
			RETURN SWITCH ( TRUE (), ISBLANK ( Bestilling ), Ekstraksjon, ISBLANK ( Ekstraksjon ), Bestilling, Bestilling >= Ekstraksjon, Bestilling, Ekstraksjon )
		formatString: dd.MM.yyyy HH:mm
		summarizeBy: none

	column 'Enhet startkilde' =
			VAR Bestilling = resultater[Tidspunkt.analysebestilling]
			VAR Ekstraksjon = resultater[Ekstraksjon.ferdig]
			RETURN SWITCH ( TRUE (), ISBLANK ( Bestilling ) && ISBLANK ( Ekstraksjon ), "Mangler start", ISBLANK ( Ekstraksjon ), "Analysebestilling", ISBLANK ( Bestilling ), "Ekstraksjon ferdig", Bestilling >= Ekstraksjon, "Analysebestilling (senest)", "Ekstraksjon ferdig (senest)" )
		summarizeBy: none

	column 'Svartid pasient dager' =
			VAR Starttid = resultater[Tidspunkt.prøvetaking]
			VAR Sluttid = resultater[Tidspunkt.analyseresultat]
			VAR varighet = Sluttid - Starttid
			RETURN IF ( ISBLANK ( Starttid ) || ISBLANK ( Sluttid ) || varighet < 0 || varighet > 365, BLANK (), varighet )
		formatString: 0.0
		summarizeBy: none

	column 'Svartid seksjon dager' =
			VAR Starttid = resultater[Tidspunkt.analysebestilling]
			VAR Sluttid = resultater[Tidspunkt.analyseresultat]
			VAR varighet = Sluttid - Starttid
			RETURN IF ( ISBLANK ( Starttid ) || ISBLANK ( Sluttid ) || varighet < 0 || varighet > 365, BLANK (), varighet )
		formatString: 0.0
		summarizeBy: none

	column 'Svartid enhet dager' =
			VAR Starttid = resultater[Enhet starttid]
			VAR Sluttid = resultater[Tidspunkt.analyseresultat]
			VAR varighet = Sluttid - Starttid
			RETURN IF ( ISBLANK ( Starttid ) || ISBLANK ( Sluttid ) || varighet < 0 || varighet > 365, BLANK (), varighet )
		formatString: 0.0
		summarizeBy: none

	column 'Godkjenningsetterslep dager' =
			VAR Starttid = resultater[Tidspunkt.analyseresultat]
			VAR Sluttid = resultater[Tidspunkt.godkjenning]
			VAR varighet = Sluttid - Starttid
			RETURN IF ( ISBLANK ( Starttid ) || ISBLANK ( Sluttid ) || varighet < 0 || varighet > 365, BLANK (), varighet )
		formatString: 0.0
		summarizeBy: none

	column 'Datakvalitet status' =
			VAR Resultat = resultater[Tidspunkt.analyseresultat]
			VAR Prøve = resultater[Tidspunkt.prøvetaking]
			VAR Bestilling = resultater[Tidspunkt.analysebestilling]
			VAR EnhetStart = resultater[Enhet starttid]
			VAR Godkjenning = resultater[Tidspunkt.godkjenning]
			RETURN
				SWITCH (
					TRUE (),
					ISBLANK ( Resultat ), "Mangler sluttid",
					ISBLANK ( Prøve ), "Mangler prøvetaking",
					Prøve > Resultat, "Negativ analysetid - sjekk data",
					Resultat - Prøve > 365, "Ekstrem prøvetakingsdato",
					ISBLANK ( Bestilling ), "Mangler analysebestilling",
					Bestilling > Resultat, "Negativ analysetid - sjekk data",
					ISBLANK ( EnhetStart ), "Mangler enhetsstart",
					EnhetStart > Resultat, "Negativ analysetid - sjekk data",
					NOT ISBLANK ( Godkjenning ) && Godkjenning < Resultat, "Godkjenning før analyseresultat",
					ISBLANK ( resultater[Svarfrist] ), "Mangler svarfrist",
					"OK"
				)
		summarizeBy: none
'''


ANTALL_HEADER = r'''table antall

	measure 'Antall analyser' = COUNTROWS ( antall )
		formatString: #,0

	measure 'Antall analyser forrige periode' = CALCULATE ( [Antall analyser], DATEADD ( Dato[Date], -1, MONTH ) )
		formatString: #,0

	measure 'Endring analyser prosent' = DIVIDE ( [Antall analyser] - [Antall analyser forrige periode], [Antall analyser forrige periode] )
		formatString: 0.0%

	column Analyse
		dataType: string
		summarizeBy: none
		sourceColumn: Analyse

	column 'Tidspunkt.analysebestilling'
		dataType: dateTime
		formatString: dd.MM.yyyy HH:mm
		summarizeBy: none
		sourceColumn: Tidspunkt.analysebestilling

	column Nukleinsyre
		dataType: string
		summarizeBy: none
		sourceColumn: Nukleinsyre

	column Rapportgruppe
		dataType: string
		summarizeBy: none
		sourceColumn: Rapportgruppe

	column Maaned
		dataType: int64
		formatString: 0
		summarizeBy: none
		sourceColumn: Maaned

	column 'Analysebestilling dato' = IF ( ISBLANK ( antall[Tidspunkt.analysebestilling] ), BLANK (), DATE ( YEAR ( antall[Tidspunkt.analysebestilling] ), MONTH ( antall[Tidspunkt.analysebestilling] ), DAY ( antall[Tidspunkt.analysebestilling] ) ) )
		formatString: dd.MM.yyyy
		summarizeBy: none
'''


def build_fact_tables() -> None:
    write(TABLES / "resultater.tmdl", RESULTATER_HEADER + partition_tail("resultater"))
    write(TABLES / "antall.tmdl", ANTALL_HEADER + partition_tail("antall"))


def build_relationships() -> None:
    write(
        DEFINITION / "relationships.tmdl",
        """relationship ResultaterInfo
\tfromColumn: resultater.Analyse
\ttoColumn: info.Analyse

relationship AntallInfo
\tfromColumn: antall.Analyse
\ttoColumn: info.Analyse

relationship Resultatdato
\tfromColumn: resultater.'Analyseresultat dato'
\ttoColumn: Dato.Date

relationship Prøvedato
\tisActive: false
\tfromColumn: resultater.'Prøvetaking dato'
\ttoColumn: Dato.Date

relationship BestillingsdatoResultat
\tisActive: false
\tfromColumn: resultater.'Analysebestilling dato'
\ttoColumn: Dato.Date

relationship Godkjenningsdato
\tisActive: false
\tfromColumn: resultater.'Godkjenning dato'
\ttoColumn: Dato.Date

relationship BestillingsdatoVolum
\tfromColumn: antall.'Analysebestilling dato'
\ttoColumn: Dato.Date
""",
    )


def clean_model() -> None:
    for path in TABLES.glob("*.tmdl"):
        if "DateTable" in path.name:
            path.unlink()

    model_path = DEFINITION / "model.tmdl"
    model = model_path.read_text(encoding="utf-8")
    model = re.sub(r"annotation __PBI_TimeIntelligenceEnabled = \d", "annotation __PBI_TimeIntelligenceEnabled = 0", model)
    model = "\n".join(line for line in model.splitlines() if "DateTable" not in line)
    if "ref table Svartidsperspektiv" not in model:
        model = model.replace("ref table resultater", "ref table resultater\nref table Svartidsperspektiv")
    write(model_path, model)

    for path in TABLES.glob("*.tmdl"):
        write(path, remove_variations(path.read_text(encoding="utf-8")))


def main() -> None:
    build_calendar()
    build_perspective_table()
    build_fact_tables()
    build_relationships()
    clean_model()
    print(f"Bygget semantisk modell i {DEFINITION}")


if __name__ == "__main__":
    main()
