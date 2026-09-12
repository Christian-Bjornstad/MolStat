# Spesifikasjon: Hemato Statistikk V3

## Mål

V3 skal gjøre rapporten raskere å lese og enklere å filtrere enn V2, samtidig som den beholder de robuste svartids- og datakvalitetsdefinisjonene. Ledelsen skal se status uten scrolling; fagbrukere skal kunne filtrere bort blant annet `Materiale = PAK` og få dedikerte flater for rapportgrupper, analyser og oppfølging.

## Leveranse

- Selvstendig PBIX: `powerbi/Hemato_Statistikk_V3.pbix` med cachede data.
- Redigerbar PBIP: `powerbi/Hemato_Statistikk_V3/Hemato_Statistikk_V3.pbip`.
- V1-original og V2-filer skal ikke endres.

## Rapportstruktur

1. **Oversikt** – fire beslutnings-KPI-er, uketrend, fristoppnåelse og rapportgrupper.
2. **Volum og uker** – uke-/månedskapasitet og lave uker uten horisontal scrollbar.
3. **Volum per analyse** – stor analyseflate med rapportgruppe- og analysesøk.
4. **Svartid** – perspektiv, materiale og rapportgruppe; median, P90 og frist.
5. **Svartid per analyse** – stor rangeringsflate med materiale-/analysefilter.
6. **Oppfølging** – kompakt tabell med identitet, svartid, frist og status.
7. **Tidslinje** – romslig fullbreddetabell med tidsstempler uten unødvendig horisontal scrolling.
8. **Datakvalitet** – egne KPI-er og diagnostikk for avvikstype og valgt enhetsstart.

## Interaksjon og design

- År, måned og uke skal vises som ekte, klikkbare dropdown-slicere med minst 84 px høyde.
- Resultatsider skal ha Materiale-filter; PAK skal kunne velges bort.
- Ingen tekstblokker som «Lesing av status» eller forklaringer som gjentar visualets tittel.
- Tidsserier bruker ekte datoakse (`UkeStart`/`MånedStart`) og skal ikke vise horisontal scrollbar.
- Navigasjonen skal være lesbar og fordele detaljinnhold over egne sider.
- Ingen kritisk informasjon skal være avhengig av hover eller bare rød/grønn farge.

## Teststrategi

- `python -m pytest tests/powerbi/test_hemato_statistikk_v3.py -q`
- `pbi --json report --path "powerbi/Hemato_Statistikk_V3/Hemato Statistikk Rapport.Report" validate`
- DAX-kontroller mot lagret og gjenåpnet PBIX.
- Visuell skjermkontroll av alle åtte sider i Power BI Desktop.

## Grenser

- Alltid: bevare SharePoint-partisjoner, individuell fristlogikk og BLANK for ugyldige intervaller.
- Senere på jobb-PC: autentisert full refresh og publisering.
- Aldri: endre `C:\Users\molpa\Downloads\Hemato_Statistikk.pbix` eller overskrive `Hemato_Statistikk_2_0.pbix`.

## Godkjent grunnlag

Brukerens beskjed 11. september 2026 om å «lage en versjon 3 og fortsette jobbingen» er godkjenningen for denne avgrensede videreutviklingen.
