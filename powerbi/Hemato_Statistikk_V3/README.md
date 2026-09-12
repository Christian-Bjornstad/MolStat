# Hemato Statistikk V3

V3 er en selvstendig videreutvikling av Hemato-rapporten. Originalen i `C:\Users\molpa\Downloads\Hemato_Statistikk.pbix` og V2 er ikke endret.

## Filer

- Ferdig PBIX med cachede data: `C:\Users\molpa\Documents\MolStat\powerbi\Hemato_Statistikk_V3.pbix`
- Redigerbar PBIP: `C:\Users\molpa\Documents\MolStat\powerbi\Hemato_Statistikk_V3\Hemato_Statistikk_V3.pbip`

PBIX-en kan åpnes og vises uten SharePoint-innlogging. En full dataoppdatering må kjøres på jobb-PC-en i en autentisert Power BI-kontekst.

## Rapportstruktur

Rapporten er laget for 1280 × 720 og har åtte sider:

1. **Oversikt** – resultatvolum, median enhetstid, fristoppnåelse, datakvalitet, uketrend og rapportgrupper.
2. **Volum og uker** – uke-/månedstrend, fireukers nivå og historisk lavvolumgrense.
3. **Volum per analyse** – stor analyseflate og rapportgrupper uten lang rulleliste.
4. **Svartid** – perspektivvelger, median/P90, individuell frist og rapportgruppesammenligning.
5. **Svartid per analyse** – sammenligning av analyser og materialer.
6. **Oppfølging** – kompakt detaljtabell med svartid, frist og kvalitetsstatus.
7. **Tidslinje** – fullbreddetabell fra prøvetaking til godkjenning.
8. **Datakvalitet** – avvikstyper og hvilken startkilde enhetstiden bruker.

År, måned og ISO-uke er klikkbare dropdown-filtre. Resultatsidene har også Materiale-filter, der blant annet `PAK` kan velges eller filtreres bort. Kategoritunge sammenligninger bruker treemap eller punktdiagram for å unngå dekorative scrollbarer.

## Svartidsdefinisjoner

Alle hovedperspektivene slutter ved `Tidspunkt.analyseresultat`:

- **Pasientforløp:** prøvetaking → analyseresultat.
- **Seksjonstid:** analysebestilling → analyseresultat.
- **Enhetstid:** seneste gyldige tidspunkt av analysebestilling og `Ekstraksjon.ferdig` → analyseresultat.
- **Godkjenningsetterslep:** analyseresultat → godkjenning.

Manglende, negative og åpenbart ekstreme intervaller returnerer `BLANK()` og inngår i egne datakvalitetsmål. Fristoppnåelse beregnes rad for rad mot individuell `Svarfrist`. Median og P90 er hovedstatistikkene.

## Dato og oppdatering

Den kontrollerte `Dato`-tabellen dekker 2024–2026 i den cachede modellen og bygges fra de to aktive filterdatoene: analyseresultatdato for resultatsider og analysebestillingsdato for volum. Ekstreme prøvetakingsdatoer utvider derfor ikke årfilteret.

Regenerer kilden med:

```powershell
python tools\build_hemato_statistikk_model.py
python tools\build_hemato_statistikk_report.py
python -m pytest tests\powerbi\test_hemato_statistikk_v3.py -q
pbi --json report --path "powerbi\Hemato_Statistikk_V3\Hemato Statistikk Rapport.Report" validate
```

Kontrollresultatene er dokumentert i [VALIDATION.md](./VALIDATION.md).
