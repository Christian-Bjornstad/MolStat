# Hemato Statistikk – optimert Power BI-rapport

Dette er en versjonert videreutvikling av `C:\Users\molpa\Downloads\Hemato_Statistikk.pbix`. Originalfilen er ikke endret. Den ferdige, selvstendige filen er `C:\Users\molpa\Documents\MolStat\powerbi\Hemato_Statistikk_2_0.pbix`; den åpner med cachede data uten SharePoint-innlogging. PBIP-kilden ligger i [Hemato_Statistikk_Optimert.pbip](./Hemato_Statistikk_Optimert.pbip).

## Rapportstruktur

Rapporten er bygget for 1280 × 720 og har fem sider:

1. **Ledelsesoversikt** – samlet volum, pasient-, seksjons- og enhetstid, fristoppnåelse, uketrend og tydelig varsel om datakvalitet.
2. **Volum og kapasitet** – uke- og månedsmønster, fireukers glidende volum, lave uker, rapportgrupper og analyser.
3. **Svartid** – valg mellom tre perspektiver, median/P75/P90, fristoppnåelse, trend og rangering.
4. **Oppfølging** – detaljrader, avvik, friststatus og klargjort retning for senere kommentarer/writeback.
5. **Datakvalitet** – gyldige og ekskluderte rader, avvikstyper og synlige kvalitetsregler.

Designet bruker OUS-inspirert blågrønn palett, fast venstremeny, konsistent 8-punkts rytme, høy kontrast og synlige forklaringer. Kritisk informasjon ligger ikke bare i hover. Standard tooltips viser blant annet antall gyldige rader, P90, fristoppnåelse og ekskluderinger.

## Definisjoner

Alle tre hovedperspektivene slutter ved `Tidspunkt.analyseresultat`:

- **Pasientforløp:** `Tidspunkt.prøvetaking` → analyseresultat. Viser hvor raskt pasienten kan få et svar.
- **Seksjonstid:** `Tidspunkt.analysebestilling` → analyseresultat. Viser seksjonens leveransetid etter bestilling.
- **Enhetstid:** den seneste av `Tidspunkt.analysebestilling` og `Tidspunkt.ekstraksjon.slutt` → analyseresultat. Dette er det korteste relevante interne intervallet når begge hendelser finnes. Målet viser også hvilken startkilde som ble brukt.
- **Godkjenningsetterslep:** analyseresultat → `Tidspunkt.godkjenning`.

Svartid måles i kalenderdager med desimaler. Manglende start/slutt, negativ varighet og varighet over 365 dager blir `BLANK()` og teller som ekskludert datakvalitet – aldri som null eller innen frist.

Fristoppnåelse beregnes rad for rad mot den enkelte radens `Svarfrist`. En stiplet, felles fristlinje skal bare vises når filterkonteksten har nøyaktig én svarfrist; målet `Entydig svarfrist dager` returnerer ellers blank. Median, P75 og P90 er primære statistikker; gjennomsnitt er sekundært. Kort og tooltips viser gyldig nevner og ekskluderinger.

## Dato og filtersemantikk

Modellen har én kontrollert `Dato`-tabell med dato, år, kvartal, måned, ISO-år, ISO-uke, år–uke og ukestart. Automatiske lokale datotabeller er fjernet.

Standard datofilter bruker **analyseresultatdato** for resultater og **analysebestillingsdato** for volumtabellen. Alternative hendelsesdatoer (prøvetaking, analysebestilling og godkjenning i resultattabellen) har inaktive relasjoner og kan aktiveres eksplisitt i mål med `USERELATIONSHIP`. Dette hindrer at et sidefilter skifter betydning uten at brukeren ser det.

## Datakvalitetsregler

- Start og slutt må finnes.
- Slutt må være lik eller senere enn start.
- Intervaller over 365 dager ekskluderes som sannsynlige registreringsavvik.
- Fristmål krever både gyldig valgt svartid og gyldig individuell svarfrist.
- Ekskludert antall og andel skal alltid vises sammen med svartidsstatistikk.

Kontrollgrunnlaget mot den åpne originalmodellen er dokumentert i [VALIDATION.md](./VALIDATION.md). DAX-kontrollene ligger i mappen `validation`.

## Oppdatering og videre arbeid

1. Åpne `C:\Users\molpa\Documents\MolStat\powerbi\Hemato_Statistikk_2_0.pbix` for vanlig bruk og kontroll. Bruk PBIP-filen når selve rapport-/modellkilden skal videreutvikles.
2. Godkjenn personvern-/datakildenivå og logg inn mot SharePoint-kildene ved behov.
3. Kjør full oppdatering og kontroller tallene med DAX-filene i `validation`.
4. Kontroller font, etiketter, tabellbredder og betinget formatering i 1280 × 720 før publisering.
5. Vurder eventuell drillthrough-binding etter at rapporten er testet med oppdaterte data. Navigasjon og detaljside finnes allerede.
6. Følg [WRITEBACK.md](./WRITEBACK.md) før kommentarflyt aktiveres. Rapporten later ikke som Power BI-tabellen er en skriveflate.

Modellen kan regenereres med `py -3 tools/build_hemato_statistikk_model.py`, og rapportdefinisjonen med `py -3 tools/build_hemato_statistikk_report.py`. Kjør deretter `py -3 -m pytest tests/powerbi/test_hemato_statistikk_optimert.py -q` og `pbi --json report --path "powerbi\Hemato_Statistikk_Optimert\Hemato Statistikk Rapport.Report" validate`.
