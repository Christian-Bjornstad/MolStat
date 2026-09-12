# Hemato Statistikk V4

V4 kombinerer de direkte og oversiktlige analysefigurene fra originalrapporten med den kontrollerte datomodellen, perspektivvelgeren og kapasitetsanalysen fra V3.

## Leveranse

- PBIX med cachede data: `C:\Users\molpa\Documents\MolStat\powerbi\Hemato_Statistikk_V4.pbix`
- Redigerbar PBIP: `C:\Users\molpa\Documents\MolStat\powerbi\Hemato_Statistikk_V4\Hemato_Statistikk_V4.pbip`

PBIX-en kan åpnes uten SharePoint-pålogging. Oppdatering av kildedata må gjøres på en autentisert jobb-PC.

## Sider

1. **Oversikt** – samlet bilde av antall, median, fristoppnåelse og ukeutvikling.
2. **Antall per uke** – ukevolum, månedsvolum og fireukers nivå.
3. **Antall per rapportgruppe** – sortert sammenligning og månedstrend.
4. **Antall per analyse** – stor, sortert stolpegraf etter mønsteret fra originalrapporten.
5. **Svartid over tid** – median og fristoppnåelse for valgt perspektiv.
6. **Svartid per analyse** – medianstolper med statusfarge og stiplet frist når fristen er entydig.
7. **Oppfølging** – detaljtabell som sammenligner pasient-, seksjons- og enhetstid.
8. **Om rapporten** – korte definisjoner og nedtonet teknisk kvalitetskontroll.

År, måned, ISO-uke, materiale, rapportgruppe og analyse er tilgjengelig der de er relevante. `Materiale` kan brukes til å velge bort blant annet `PAK`.

## Svartid

Alle perspektiver slutter ved `Tidspunkt.analyseresultat`:

- **Pasientforløp:** prøvetaking til analyseresultat.
- **Seksjonstid:** analysebestilling til analyseresultat.
- **Enhetstid:** seneste gyldige tidspunkt av analysebestilling og ekstraksjon ferdig til analyseresultat.

Median og andel innen individuell svarfrist er hovedmål. P90 finnes fortsatt i modellen for eventuell faglig kontroll, men brukes ikke i rapportens hovedflater. Negative eller manglende intervaller holdes utenfor svartidsmålene og behandles som tekniske avvik; dette kan være forventet når bestilling registreres etter utført arbeid.

## Regenerering

```powershell
python tools\build_hemato_statistikk_v4_report.py
python tools\package_hemato_pbix.py powerbi\Hemato_Statistikk_V3.pbix powerbi\Hemato_Statistikk_V4.pbix --report "powerbi\Hemato_Statistikk_V4\Hemato Statistikk Rapport.Report" --omit-custom-theme
python -m pytest tests\powerbi\test_hemato_statistikk_v4.py -q
```
