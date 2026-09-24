# FLOW-statistikk V1

MolStat henter begge LVMS-rapportene og publiserer `flow/antall.csv` og `flow/resultater.csv`. Åpne `Flow_Statistikk_V1_MolStat.pbit` på jobb-PC-en, angi `MolStatPublicRoot` som **roten over `flow`-mappen** i konfigurert SharePoint-område, oppdater og lagre som PBIX. Analyseoppslaget er bakt inn i malen. Den opprinnelige `Flow_Statistikk_V1.pbix` er en eldre, tom modell med lokale filbaner.

## Leveranse

Rapporten er bygget på utformingen fra Hemato/Solide. Den har åtte sider: oversikt, antall per uke, analysegrupper, antall per analyse, svartid over tid, svartid per analyse, pris per test og definisjoner. Malen inneholder ingen cached fakta; tall vises etter oppdatering mot MolStats publiserte filer.

## LVMS-uttak

| Rapport | Rapporttype | Kategori | Rapport-ID | Bruk |
| --- | --- | --- | --- | --- |
| Antall | PRODSTAT | PATOLOGI | PAT-DIT-ANTALL-OU | Registrerte analyser, datert etter analysebestilling |
| Resultater | PRODSTAT | PATOLOGI | PAT-DIT-RESULTATER-OU | Besvarte analyser, datert etter analyseresultat; svartid til godkjenning |

Begge uttakene skal bruke de 66 kodene i `Data/analyse_lookup.csv`. `Sample ID` og `PID` blir ikke skrevet til de bearbeidede CSV-filene. Den lokale rapporten bruker kun aggregert analysekode, gruppe, materiale, tidspunkter og pris. Det er ingen ekstraksjonsrapport eller ekstraksjonsmålinger.

Svartid måles som (1) godkjenning minus prøvetaking og (2) godkjenning minus opprettelse, i kalenderdøgn. Manglende, negative eller over 365 døgn lange intervaller utelates fra medianene. Gyldige antall vises separat. Det finnes ingen individuell svarfrist i disse kildene.

## Analysegrupper og priser

`Data/analyse_lookup.csv` har én rad per forespurt LVMS-kode. Gruppe er en **rapportinndeling utledet av analysenavn**, ikke en bekreftet LVMS-analysegruppe. Gruppene er bestilling/frysing, B-celle/basis, T/NK, AML/MDS, NOPHO og spesial. Behold analysekoden som eget detaljnivå for kontroll.

`Data/pris_2026.csv` inneholder 2026-pris per test (antistoff + Fix&perm) for 64 prisførte workitems. Pris kobles bare når workitem og analysekode er identiske; ingen variant gis pris fra en annen variant. Av de 66 uttakskodene har 60 eksakt pris. Disse seks mangler eksakt treff:

| Uttakskode | Årsak |
| --- | --- |
| FLOW-06-B-OU | Prislisten bruker FLOW-06-ALT-OU |
| FLOW-36-OU | Prislisten bruker FLOW-36-MC-OU og FLOW-36-MK-OU |
| FLOW-56-OU | Ingen pris oppgitt |
| FLOW-BB-OU, FLOW-BESTILT-OU, FRYSFLOW-OU | Bestillings-/frysehendelser uten testpris i oppgitt liste |

Fire prisførte koder finnes ikke i uttakslisten: `FLOW-06-ALT-OU`, `FLOW-36-MC-OU`, `FLOW-36-MK-OU`, `FLOW-39-KMML-OU`. Vurder disse i LVMS før de eventuelt legges til i begge rapportdefinisjonene og oppslaget. `FLOW-61-OU` er satt til brukeroppgitt **250 kr**; den vedlagte arbeidsboken hadde 300 kr. Prisvisualiseringen er derfor et estimat, ikke dokumentert faktisk forbruk. `Data/kildekontroll.json` dokumenterer alle avvik.

## Oppdatering sammen med MolStat

1. Eksporter de to angitte PRODSTAT-rapportene for samme periode til et godkjent område for sensitive data.
2. Kjør fra MolStat-roten:

   ```powershell
   $env:PYTHONPATH='src;.'
   python tools/process_flow_reports.py --antall 'C:\sikker\FLOW-antall.csv' --resultater 'C:\sikker\FLOW-resultater.csv' --output 'powerbi\Flow_Statistikk_V1\Data'
   ```

3. Kontroller `Data/kontroll.json`, særlig ekskluderte analysekoder og antall gyldige svartider. Denne manuelle kontrollen oppdaterer bare lokale `Data`-filer; MolStat-malen leser publiserte filer under `MolStatPublicRoot`.
4. Ved ordinær drift henter MolStat begge uttakene automatisk. Oppdater Power BI etter at begge publiserte CSV-filer er skrevet.

De lokale `Data/antall.csv` og `Data/resultater.csv` er bare kolonneoverskrifter. Ikke legg pasientdata i Git.
