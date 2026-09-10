# MolStat Prøveflyt — Power BI-mal

Malen leser `restansehistorikk.csv`, som MolStat bygger fra permanent
SQLite-historikk og erstatter atomisk i den konfigurerte SharePoint-roten under
`Prøveflyt`.

## Filer i startsettet

- `sample_restansehistorikk.csv`: syntetisk timesett med eksakt offentlig kontrakt.
- `power-query.m`: parameterstyrt import og typer for `FactRestanse`.
- `measures.dax`: datodimensjon, analysedimensjon og snapshot-sikre mål.
- `molstat-proveflyt-theme.json`: samme pastellgule tema som MolStat-appen.
- `MolStatProveflyt.SemanticModel/definition`: ferdig, validert TMDL-modell
  eksportert fra den levende Power BI Desktop-modellen.
- `MolStatProveflyt.Report/MolStatProveflyt.pbip`: ferdig PBIR-rapportskall med
  tre 16:9-sider, 18 bundne visualer og det godkjente temaet.

Eksempelfilen inneholder syntetiske MolStat-ID-er. MolStat-ID er en pseudonym
koblingsnøkkel; rått prøvenummer, pasientdata, WorkItem, kildefilstier og
interne fingeravtrykk er fortsatt utelatt.

## 1. Opprett filparameteren

I Power Query velger du **Administrer parametere → Ny parameter**:

- Navn: `ProveflytFil` (ASCII-ID for stabil Power BI/CLI-import)
- Type: Tekst
- Verdi under bygging:
  `C:\Users\molpa\Documents\MolStat\docs\powerbi\sample_restansehistorikk.csv`
- Produksjonsverdi senere:
  `<konfigurert SharePoint-rot>\Prøveflyt\restansehistorikk.csv`

Gateway-/SharePoint-tilkoblingen kan dermed bytte verdi uten å endre modellen.
Hvis TMDL-kilden brukes direkte, endres samme parameter i
`definition/expressions.tmdl` eller i Power Query etter at prosjektet er åpnet.

## 2. Opprett `FactRestanse`

Velg **Ny kilde → Tom spørring → Avansert redigering**, lim inn
`power-query.m`, og kall spørringen `FactRestanse`. Kontroller at den gir 16
modellkolonner: de 15 offentlige feltene pluss den avledede `Dato`. Power Query
gir den offentlige sjuende kolonnen `På_vei` den tekniske modell-ID-en
`Paa_vei` for stabilitet mot Windows-verktøy som ikke håndterer
Unicode-identifikatorer korrekt. Den eksakte CSV-rekkefølgen håndheves av
MolStats eksporttest.

Power Query bruker `en-US` ved typekonvertering fordi MolStat eksporterer
desimaltall med punktum uavhengig av norsk Windows-region.

`Observert_tidspunkt` er snapshot-tidspunktet. Det skal ikke erstattes med
`TODAY()`, og verdier fra flere snapshots skal ikke summeres i «nå»-kort.

## 3. Modell

Opprett de to beregnede tabellene fra `measures.dax` og relasjonene:

```text
DimDato[Date]                         1 ─── * FactRestanse[Dato]
DimAnalysegruppe[Analysegruppe_kode] 1 ─── * FactRestanse[Analysegruppe_kode]
```

Begge relasjoner filtrerer én vei fra dimensjon til fakta. Marker bare
`DimDato` som datotabell og velg `DimDato[Date]`. Faktatabellen har gjentatte
datoer og skal aldri markeres som datotabell.

Legg de resterende uttrykkene fra `measures.dax` som mål i `FactRestanse`.
`Siste_observerte_tidspunkt` hentes fra data, og «nå»-målene filtrerer til
dette tidspunktet. Fordi MolStat skriver alle aktiverte analysegrupper også når
de har null, blir gruppelista stabil og nye grupper vises automatisk.

## 4. Side «Prøveflyt – nå»

- Sideformat: 16:9.
- Topp: kort for `Siste_observerte_tidspunkt`, `Total_restanse_naa`, `Klar_naa`,
  `Mangler_godkjenning_naa`, `Paa_vei_naa` og `Over_frist_naa`.
- Hovedfelt: Matrix med `DimAnalysegruppe[Analysegruppe]` på rader og målene
  `Klar_naa`, `Mangler_godkjenning_naa`, `Paa_vei_naa`, `Over_frist_naa` og
  `Eldste_klare_timer_naa` som verdier.
- Betinget formatering: grønn `#1B7D3A`, advarsel `#9A6A00`, kritisk
  `#A4262C`; bruk tekst eller ikon i tillegg til farge.
- Slicere: Enhet og Analysegruppe.

Matrixen erstatter hardkodede enkeltkort. En ny analysegruppe krever derfor
ingen rapportendring.

## 5. Side «Utvikling»

- Linjediagram med `FactRestanse[Observert_tidspunkt]` på x-aksen.
- Verdier: de fire målene `… ved tidspunkt`.
- Small multiples eller legend: `DimAnalysegruppe[Analysegruppe]`.
- Datointervall fra `DimDato[Date]`.

På denne siden gir tidspunktet filterkonteksten; målene summerer grupper innen
ett snapshot, aldri timer over hverandre.

## 6. Drill-through-side «Analysegruppe»

Legg `DimAnalysegruppe[Analysegruppe]` i drill-through-filteret og bruk samme
felt i matrixen på oversiktssiden. Vis kun aggregater:

- nå-kortene for valgt gruppe;
- tidsserie for de fire statusene;
- tabell med tidspunkt, statusantall, over frist, median/eldste timer og
  alvorlighetsgrad.

Det finnes ingen prøve-/pasientdetaljer å drille til, med vilje.

## 7. Tema, refresh og lagring

Den raskeste starten er å åpne
`MolStatProveflyt.Report/MolStatProveflyt.pbip`. Rapporten peker relativt til
den versjonsstyrte TMDL-modellen ved siden av prosjektmappen. Ved manuell
bygging importeres `molstat-proveflyt-theme.json` fra **Vis → Tema → Bla
gjennom temaer**.

Etter at `ProveflytFil` peker på synket SharePoint-fil, publiser rapporten og
konfigurer gateway/refresh etter lokale IT-regler. MolStat oppdaterer fila hver
time 06:00–18:00; Power BI-refresh bør legges etter disse tidspunktene.

Lagre først som PBIX. Når modellen og tilkoblingen er godkjent, velg
**Fil → Eksporter → Power BI-mal** og lagre `MolStat_Proeveflyt.pbit` utenfor
Git-repoet. Legg deretter rapportens HTTPS-lenke fra `app.powerbi.com` i MolStat
under **Innstillinger → Power BI-rapport**.
