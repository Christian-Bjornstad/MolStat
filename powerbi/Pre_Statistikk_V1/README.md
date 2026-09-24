# PRE-statistikk V1

MolStat henter PRE-resultatrapporten og publiserer `pre/resultater.csv` sammen med en tom `pre/antall.csv` for modellkompatibilitet. Åpne `Pre_Statistikk_V1_MolStat.pbit` på jobb-PC-en, angi `MolStatPublicRoot` som **roten over `pre`-mappen** i konfigurert SharePoint-område, oppdater og lagre som PBIX. Analyseoppslaget er bakt inn i malen. Den opprinnelige `Pre_Statistikk_V1.pbix` bruker lokale filbaner.

## Leveranse

Malen har åtte sider: oversikt, aktivitet per uke, grupper og metoder, prosesstid, total svartid, normoppnåelse, analyseoppslag og definisjoner. Den er bygget på Hemato/Solide-oppsettet og inneholder ingen cached fakta; tall vises etter oppdatering mot MolStats publiserte filer.

## Kilde og antall

Eneste uttak er **PRODSTAT / PATOLOGI / PAT-DIT-RESULTATER-OU**, med de 50 kodene i `Data/analyse_lookup.csv`. Det finnes ingen separat ANTALL-eksport. Bearbeidingen teller én aktivitet per **Sample ID + analysekode**, og kollapser gjentatte rader for samme kombinasjon til første analyseresultat. `Sample ID` brukes bare under bearbeiding; den skrives ikke til Power BI-dataene. En prøve som har flere aktiviteter telles flere ganger i totalt antall aktiviteter. Derfor er totalen ikke et antall unike prøver.

## Tider og normer

`NormProsess` er målet for ett prosesstrinn. `NormTotalt` er målet fra DIT-opprettelse til aktivitetens analyseresultat. Begge måles i kalenderdøgn. Rapporten viser median, gjennomsnitt og andel enkeltaktiviteter innen norm. Den opprinnelige arbeidsboken har også status på gjennomsnitt per metode/måned; prosentene kan derfor avvike.

| Aktivitet | Prosesstid | Totaltid |
| --- | --- | --- |
| Utført forbehandling | Første ekstraksjonsvalg (mottatt på lab) → aktivitetens analyseresultat | Første opprettelse → analyseresultat |
| Utført ekstraksjon | Første utførte forbehandling → aktivitetens analyseresultat | Første opprettelse → analyseresultat |
| Videresendt | Første utførte forbehandling → aktivitetens analyseresultat | Første opprettelse → analyseresultat |
| Analyse ferdig | Ingen prosessnorm oppgitt | Første opprettelse → analyseresultat |

Valgaktiviteter og Idylla-kassettaktiviteter uten en gitt norm inngår i antall, men ikke i den tilsvarende normandelen. Nødvendig starttid som mangler gir tom tid og datakvalitetsavvik. Negative intervaller og intervaller over 365 døgn holdes utenfor tids- og normmålene. Kontrollfilen viser hvor mange tider som er gyldige.

## Kildekontroll

Alle 50 kodene i Excel-arbeidsbokens uttaksliste finnes i aktivitetsregisteret. Fem Idylla-kassettkoder (`FORBIDYLLA-*`) hadde tom aktivitetstype og gruppe i arbeidsboken; de er satt til `UtførtForbehandling` og `Forbehandling PRE` fra brukerens oppgitte liste. De får **ingen oppdiktet norm**. Avvikene står i `Data/kildekontroll.json` og på oppslagssiden.

## Månedlig oppdatering sammen med MolStat

1. Eksporter `PAT-DIT-RESULTATER-OU` fra LVMS med analysekodene i oppslaget. Velg periode etter analyseresultat.
2. Behold et godkjent, sensitivt område med samlede månedsfiler. Tidligere aktiviteter må være tilgjengelige når en prøve får et nytt trinn i en senere måned. Unngå andre CSV-filer i denne mappen.
3. Kjør fra MolStat-roten:

   ```powershell
   $env:PYTHONPATH='src;.'
   python tools/process_pre_reports.py --resultater 'C:\sikker\PRE-uttak' --output 'powerbi\Pre_Statistikk_V1\Data'
   ```

4. Kontroller `Data/kontroll.json`: antall kildefiler, ekskluderte koder, kollapsede duplikater og gyldige tider. Oppdater deretter PBIX i Power BI Desktop. `Data/antall.csv` er bare en tom kompatibilitetstabell; alle viste antall kommer fra `resultater.csv`.
5. Ved ordinær drift henter MolStat uttaket automatisk. Oppdater Power BI etter at den publiserte resultatfilen er skrevet. Malens filbane angis gjennom `MolStatPublicRoot`.

Ikke legg råuttrekk, kontrollfil med produksjonstall eller pasientdata i Git.
