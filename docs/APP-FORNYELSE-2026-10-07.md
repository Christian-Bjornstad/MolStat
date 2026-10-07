# MolStat: enheter, innstillinger og manuell import

Arbeidet er bestilt 7. oktober 2026 på branchen
`codex/app-redesign-unit-isolation`.

## Mål og avgrensning

Enhetene skal kunne kjøres og feilsøkes hver for seg. Hovedsiden skal vise
faktisk status for hver funksjon, og innstillinger skal redigeres for én
enhet om gangen. Operatøren skal kunne velge manuelt nedlastede LVMS-filer
og bruke samme prosessering, register og publisering som ved automatisk henting.

| Område | Ansvar | Verifikasjon |
|---|---|---|
| Enhetskjøring | Isolert konfigurasjon og resultater per enhet/funksjon | En feil påvirker ikke andre enheter |
| JSON og lookup | Tydelige valideringsfeil, korrekt XLSX-lesing og atomisk lagring | Feilformat, duplikater og tomme Excel-celler |
| Manuell import | Valgt enhet, rapportroller og periode, originalfiler bevares | CSV-validering, register, arkiv, Excel og publisering |
| Kontrollsenter | Oversikt, enhetsinnstillinger, import og diagnostikk | PyQt-interaksjon og skjermbilder |

Implementeringsrekkefølge: kontrakter → parallelle backend/UI-rettelser →
integrasjon → regresjonstester → uavhengig kodegjennomgang.

## Forutsetninger

- Eksisterende Python/PyQt-app og permanente SQLite-register videreføres.
- Bare én skriver kjører om gangen; enhetsisolasjon betyr separate resultater,
  ikke parallelle skrivere mot samme database.
- Sensitive filer forblir i konfigurert sensitiv rot; bare eksisterende
  tillatte publiseringskolonner sendes til SharePoint.
- Manuell import mottar originale LVMS CSV-uttrekk, ikke prosesserte Power BI-filer.
- JSON-/lookup-endringer beholder eksisterende rapport- og publiseringskontrakter.
- Lokale endringer som allerede finnes ved oppstart tas ikke med i våre commits.

## Akseptansekriterier

1. Ugyldig oppsett i én enhet hindrer ikke en annen gyldig enhet i å kjøre.
2. Delvis feil i «Kjør alt» vises på berørte enheter og funksjoner.
3. Innstillinger har separate områder for felles oppsett og hver enkelt enhet.
4. Manuell import validerer hele filsettet før statistikkarkivet oppdateres,
   beholder originalfilene og bruker eksisterende writer lease og prosessering.
5. Excel-lookup bruker celleadresser og riktig arkrekkefølge; ugyldige lookup-
   og JSON-filer avvises med forståelig feilmelding.
6. Testene dekker feilbaner, delvis feil, manuell import og UI-integrasjon.

## Verifikasjon

`python -m pytest` og `python -m compileall -q src` er prosjektets kontroller.
GUI testes med syntetisk oppsett og skjermbilder. Reell innlogging, uttrekk og
skriving mot jobbens K-sensitive/SharePoint-røtter utføres ikke i utviklingstesten.

Ingen nye biblioteker, endring av backup-retensjon eller sletting av historikk
inngår.

## Leveranse

- Oversikt med søk, filter, aktive enheter først, oppsettssnarveier og resultat
  per funksjon. Sist kjørt vises i lokal tid. Resultatene bevares ved omstart.
- Innstillinger med enhetsliste og én editor om gangen. Felles mapper,
  automatikk og flytting av innstillinger ligger i separate faner. Ulagrede
  felter beholdes når en annen enhet velges.
- Manuell import med dynamiske rapportroller og periodekontroll. Importen
  validerer et helt sett, beholder originalene og bruker eksisterende arkiv,
  register, publisering og Excel-eksport. Den fungerer uten LVMS-henting.
- Isolert oppsett og feilhåndtering for hver enhet/funksjon. En ugyldig JSON
  eller lookup hindrer bare berørte funksjoner. Ny publisering kan prøves
  uten å hente og importere på nytt, og uten å endre status for kildeimporten.
- Fornyelse av databaselåsen under lange kjøringer og eierskapskontroll før
  databaseoppdatering, råarkiv og delte eksportfiler.
- Streng JSON-, CSV- og XLSX-validering og rettede dynamiske Excel-formler.

## Funn fra kodegjennomgangen

| Feil | Rettelse og kontroll |
|---|---|
| Oppsett for én enhet kunne blokkere alle andre | Enhetsvis bygging og egne resultater; ugyldig Solide/gyldig Flow testes sammen |
| Samlet feilmelding merket alle enheter som feilet | UI bruker resultater per funksjon, inkludert delvis feil i samme enhet |
| Historisk feil på fjernet funksjon ble fortsatt vist | Historikk filtreres mot gjeldende funksjoner; egen regresjonstest |
| Statistikk for Flow, FISH og Pre oppdaterte ikke prøveregisteret | Samme registerimport og Excel-datakilde som de øvrige prøveprofilene |
| Korrigert uttrekk kunne blandes med eldre revisjon fra samme periode | Nyeste numeriske revisjon brukes; gamle råfiler beholdes |
| Manuelle feilfiler kunne forurense statistikkarkivet | Privat validering av filsett og tidligere historikk før normal import |
| XLSX-lookup flyttet verdier når tomme celler ble utelatt | Celleadresser og faktisk arkrekkefølge styrer lesingen |
| Excel-søk hadde ugyldig spillreferanse og LET-variabel | Formler kontrollert og rettet med faktisk Excel-beregning |
| Store analysepartisjoner ble stablet før filtrering | Hver partisjon filtreres før resultatene kombineres |
| Databaselåsen kunne utløpe mens en lang jobb fortsatt kjørte | Låsen fornyes, og mistet eierskap stopper videre skriving |
| Uleselige innstillinger kunne ende med database i arbeidsmappen | Kontrollsenteret åpnes for retting; automatikk avvises uten å lage database |
| Patologprofilen aksepterte arkivnavn prosessoren ikke leste | Støttede arkivnavn valideres; hente-ID er fortsatt et eget felt |
| Enkelte tester krevde lokale Excel-filer og verktøy utenfor Git | Bevarte domenekontroller bruker medfølgende lookup og appens faktiske prosessorer |

`config/units/<enhet>.json` og medfølgende maler er kilde til enhetsoppsettet.
Det eldre `config/units.json` beholdes for migrering. Valideringen er rettet
uten å overskrive lokale analysevalg eller vedlikeholde to aktive oppsett.

## Testgrunnlag

GUI er gjennomgått i 1100 × 720 og 1280 × 800 med syntetiske data.
Skjermbilder av oversikt, alle innstillingsfaner, manuell import og diagnostikk
ligger lokalt under `artifacts/app-redesign`. Ingen horisontal overflyt ble
observert. Arbeidstråd, sperring av innstillinger og lukking under kjøring er
testet gjennom Qt.

Excel-søk er åpnet og beregnet i Microsoft Excel 16.0, build 20430, med
midlertidige syntetiske arbeidsbøker. Eksakt søk, prefiks, flere verdier,
tomme/blanke søk, datoformat, ledende nuller, lange prøvenumre og analyse-
partisjoner er kontrollert. Produksjonsfiler er ikke brukt i denne testen.

Hele det eksisterende arbeidsområdet ble kontrollert underveis med
`python -m pytest`: **779 tester bestått**. Det inkluderer lokale Power BI-
tester som ikke er lagt i Git; disse inngår ikke i leveransen. Siste
sluttkontroll bruker en separat kopi av branchens filer uten disse lokale
avhengighetene.

Installasjonspakken ble bygget fra en separat kopi av Git-indeksen med
`python -m pip wheel . --no-deps --no-build-isolation`, og installert i en
egen testmappe uten å endre det normale Python-miljøet. Oppstart av Qt-app,
manuell-importmodul, SVG-ressurs og alle seks standardenheter er kontrollert
fra den installerte pakken. **49 tester for manuell import og enhetskjøring**
passerer også mot den installerte pakken. `compileall` og
`git diff --check` passerer.

Endelig full testpakke fra den separate Git-kopien: **755 tester bestått**
på Python 3.12.10, inkludert **51 UI-tester**, med følgende oppsett:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:QT_QPA_FONTDIR = 'C:/Windows/Fonts'
python -m pytest
python -m compileall -q src
```

De nye feilbanene er dekket med regresjoner som feilet før rettingen.
Enhetskjøring, JSON/lookup/Excel og UI-integrasjon har også vært gjennomgått
av andre agenter enn den som skrev endringen. Ingen blokkerende funn står
åpne i denne gjennomgangen. Neste driftskontroll er reell LVMS-henting og
publisering mot jobbens K-sensitive/SharePoint-røtter, slik pilotlisten i
[enhetsfiler og drift](APP-OPPSETT.md) beskriver.
