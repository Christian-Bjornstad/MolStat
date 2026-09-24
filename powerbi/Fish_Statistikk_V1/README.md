# FISH-statistikk V1

MolStat henter begge LVMS-rapportene og publiserer `fish/antall.csv` og `fish/resultater.csv`. Åpne `Fish_Statistikk_V1_MolStat.pbit` på jobb-PC-en, angi `MolStatPublicRoot` som **roten over `fish`-mappen** i konfigurert SharePoint-område, oppdater og lagre som PBIX. Analyseoppslaget er bakt inn i malen. Den opprinnelige `Fish_Statistikk_V1.pbix` bruker lokale filbaner.

## Innhold

Malen har åtte sider i samme visuelle oppsett som Hemato/Solide: oversikt, antall per uke, antall per analyse, svartid over tid, svartid per analyse, normoppnåelse, analyseoppslag og definisjoner. Den inneholder ingen cached fakta; tall vises etter oppdatering mot MolStats publiserte filer.

## Kilder og definisjoner

Begge eksportene er `PRODSTAT` / `PATOLOGI` og skal bruke de samme 61 kodene i `Data/analyse_lookup.csv`.

| Rapport-ID | Formål | Periodefelt ved eksport og rapportering |
| --- | --- | --- |
| `PAT-DIT-ANTALL-OU` | Registrerte analyser | Analysebestilling/opprettet |
| `PAT-DIT-RESULTATER-OU` | Besvarte analyser | Analyseresultat |

Arbeidsbokens analyseregister har én gruppe, `FISH`, norm **5 kalenderdøgn** og svartidstype **Resultat** for alle kodene. Svartid er derfor `Tidspunkt analyseresultat − Tidspunkt analysebestilling`. Manglende, negative eller over 365 døgn lange intervaller tas ut av svartidsmålene og telles som datakvalitetsavvik. `FISH-BCL1-IGHDF-OU` er merket inaktiv/erstattet av `FISH-IGH-CCND1-DF-OU`, men er med i brukerens uttaksliste og oppslaget slik at historiske forekomster ikke mistes.

Normoppnåelsen i PBIX er **andel enkeltresultater** med gyldig svartid ≤ 5 døgn. Den eldre Excel-arbeidsboken merket derimot gjennomsnittlig svartid per analyse/måned som OK eller avvik. De to målene kan derfor gi ulike prosenttall; median og gjennomsnitt vises begge i PBIX.

## Oppdatering via MolStat

1. Eksporter begge rapportene for samme periode fra LVMS til et godkjent område for sensitive data. Velg analyseresultat fra/til for resultatrapporten og analyse opprettet fra/til for antallsrapporten, slik prosedyren i FISH-arbeidsboken angir.
2. Kjør fra MolStat-roten:

   ```powershell
   $env:PYTHONPATH='src;.'
   python tools/process_fish_reports.py --antall 'C:\sikker\FISH-antall.csv' --resultater 'C:\sikker\FISH-resultater.csv' --output 'powerbi\Fish_Statistikk_V1\Data'
   ```

3. Sjekk `Data/kontroll.json` for rader med ukjent analysekode, antall gyldige svartider og antall innen norm. Denne manuelle kontrollen oppdaterer bare lokale `Data`-filer; MolStat-malen leser publiserte filer under `MolStatPublicRoot`.
4. Ved ordinær drift henter MolStat begge uttakene automatisk. Oppdater Power BI etter at begge publiserte CSV-filer er skrevet.

Bearbeidingen skriver ikke `Sample ID` eller `PID` til rapportdataene. Filene `Data/antall.csv` og `Data/resultater.csv` i denne leveransen inneholder bare kolonneoverskrifter. Ikke legg rådata eller pasientdata i Git.
