# Spec: excel-search

**Status:** Godkjent 2026-09-10

## Objective

Generere én makrofri `Prøvesøk.xlsx` på K-sensitiv slik at ansatte kan slå opp
prøvenummer eller MolStat-nøkkel uten å åpne MolStat. Databasen er eneste
skrivbare fasit. Arbeidsboken er en regenererbar, skrivebeskyttet lesekopi.

## Tech Stack

Microsoft 365 Excel med engelske, OOXML-lagrede formler (`LET`, `FILTER`,
`XLOOKUP`). Arbeidsbokens visning og etiketter er norske. Implementeringen skal
først gjennom en avgrenset kompatibilitetstest av valgt XLSX-generator på
jobb-PC. Ingen VBA, ODBC eller direkte SQLite-tilkobling.

## Commands

```powershell
python -m pytest tests/excel_search -q
python -m pytest -q
python -m compileall -q src tests
```

## Project Structure

- `src/molstat/excel_search.py`: lesemodell, XLSX-generering og atomisk publisering.
- `src/molstat/services.py`: plassering og status etter vellykket import.
- `tests/excel_search/`: struktur, formler, lås, personvern og volum.
- `artifacts/` eller midlertidig testområde: kun syntetiske visuelle verifikasjoner.

## Workbook Contract

Fysisk arkorden er:

1. `Prøvesøk`: 50 gule inndatarader, treffliste og analysedetaljer.
2. `Prøver`: skrivebeskyttet Excel-tabell med én rad per prøve.
3. `Analyser`: skrivebeskyttet Excel-tabell med én rad per analyseforekomst.
4. `Om`: kort forklaring av oppdateringstid, datakilde og bruk.

Identifikatorer lagres som tekst. Datoer lagres som ekte Excel-datoer. Arkene
med data får autofilter, fryste overskrifter og ingen redigeringsmarkering.
Formlene skal gi tydelig «Ingen treff» og kunne kombinere flere eksakte søk
eller prefikssøk. `WorkItem` og intern identitetsstatus skal ikke vises.

Foreslått søkemønster:

```excel
=FILTER(tblPrøver;COUNTIF($A$5:$A$54;tblPrøver[Prøvenummer])+COUNTIF($A$5:$A$54;tblPrøver[MolStat-ID])>0;"Ingen treff")
```

Den faktiske OOXML-formelen lagres med engelske funksjonsnavn og komma som
argumentseparator. Excel lokaliserer visningen. Detaljer filtreres på alle
MolStat-ID-er i trefflisten. Datamodellen skal kunne deles på årsark før en tabell nærmer
seg Excels radgrense.

## Code Style

```python
candidate = export_root / ".Prøvesøk.pending.xlsx"
writer.write(candidate, snapshot)
verify_workbook(candidate)
os.replace(candidate, export_root / "Prøvesøk.xlsx")
```

Lesemodell, workbook-layout og filpublisering holdes som separate funksjoner.

## Testing Strategy

Bruk syntetiske identifikatorer. Kontroller eksakt ark-/tabellkontrakt,
formler, tekstbevarte ledende nuller, tomt søk, eksakt treff, prefikstreff,
duplikate analysekoder, manglende felt og radgrensevakt. Render alle ark og
kontroller lesbarhet. Åpne sluttfilen i målversjonen av Excel og verifiser at
formler rekalkulerer etter endring av søkecellen.

## Boundaries

- Always: generer fra én konsistent database-snapshot, verifiser før filbytte og vis sist oppdatert-tid.
- Ask first: nye sensitive kolonner, ekstern deling eller avhengighet som må installeres på jobb-PC.
- Never: makroer, databasepassord i arbeidsboken eller SQLite-skriving fra Excel.

## Success Criteria

1. Brukeren finner prøve på prøvenummer eller MolStat-ID fra `Prøvesøk`.
2. Alle koblede analyseforekomster vises, også gjentatt analysekode.
3. «I RESTANSE nå» stemmer med siste vellykkede import.
4. Åpen/låst arbeidsbok stopper ikke databaseimport og ødelegger ikke forrige gyldige Excel-fil.
5. Filen inneholder ingen makroer eller direkte databasetilkobling.
6. Syntetisk volumtest og visuell kontroll består uten avkuttede felter eller formelfeil.

## Open Questions

- Detaljtabellen deles per år når en dokumentert terskel nås. Første leveranse skal dekke alle data fra 2024 og måle faktisk filstørrelse og åpningstid.

## Generatorbeslutning 2026-09-10

Produksjonsgeneratoren er `XlsxWriter>=3.2,<4`. Biblioteket finnes i dagens
Python-miljø, lager makrofrie OOXML-filer og krever ingen Excel-installasjon på
skriver-PC-en. En syntetisk kompatibilitetsfil er kontrollert for tekstlagrede
identifikatorer, numerisk Excel-dato, formel, automatisk full rekalkulering ved
åpning og fravær av VBA. Uavhengig import og formelfeilskann besto. Endelig
manuell åpning og rekalkulering i jobb-PC-ens Excel gjenstår som pilotport.
