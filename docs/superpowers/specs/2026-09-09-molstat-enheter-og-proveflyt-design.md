# MolStat-enheter og detaljert Prøveflyt

**Dato:** 2026-09-09  
**Status:** Godkjent design, klart for implementeringsplan

## Mål

MolStat skal organiseres rundt hovedenheter i stedet for separate globale
jobber. En bruker skal kunne kjøre alt eller én enhet, konfigurere relevante
filveier per enhet og flytte et trygt innstillingsoppsett mellom PC-er.
Prøveflyt-eksporten skal samtidig være detaljert nok til Power BI-drilldown,
uten strukturerte prøve- eller pasientidentifikatorer.

## Avgrensning

Denne leveransen omfatter:

- detaljert Hemato-Prøveflyt med ordrett analyseresultat og ekstern kommentar;
- enhetsbasert kjøring og status i kontrollappen;
- aktiv Hemato og Solide samt synlige plassholdere for Lege, Flow, Pre og Hist;
- import og eksport av innstillinger;
- nytt MolStat-appikon;
- en oppdatert README.

Solide-restanse og reell prosessering for Lege, Flow, Pre og Hist inngår ikke.
Power BI-rapport eller Power BI-mal inngår heller ikke.

## Enhetsmodell

Det eksisterende eksplisitte modulregisteret utvides til å beskrive enheter og
deres kapabiliteter. Konfigurasjon skal aldri kunne importere eller kjøre
vilkårlig Python-kode.

Hver enhet har:

- stabil maskinnøkkel;
- visningsnavn;
- livssyklusstatus: `active` eller `coming`;
- null eller flere kapabiliteter: `statistics` og `backlog`;
- SharePoint-mappenavn for statistikk;
- filnavn for Prøveflyt;
- nødvendige konfigurasjonsfelt, for eksempel lookup-fil.

Første register:

| Enhet | Status | Statistikk | Restanse |
|---|---|---:|---:|
| Hemato | Aktiv | Ja | Ja |
| Solide | Aktiv | Ja | Nei |
| Lege | Kommer | Nei | Nei |
| Flow | Kommer | Nei | Nei |
| Pre | Kommer | Nei | Nei |
| Hist | Kommer | Nei | Nei |

`Kjør alt` kjører alle kapabiliteter for alle aktive enheter. En enhetsknapp
kjører alle ferdige kapabiliteter for den valgte enheten. Kommende enheter kan
ikke startes og skal være tydelig merket `Kommer`.

Orkestratoren skal motta et eksplisitt kjøringsmål, ikke tolke knappetekst.
Feil i én enhet skal registreres på den enheten. Ved `Kjør alt` fortsetter de
øvrige uavhengige enhetene, og totalsammendraget viser delvis feil hvis minst én
enhet feiler.

## Lagring og SharePoint-struktur

Brukeren konfigurerer fortsatt én K-sensitiv rot og én SharePoint-rot. MolStat
utleder undermappene deterministisk:

```text
MolStat/
├─ hemato/
│  ├─ antall.csv
│  └─ resultater.csv
├─ solide/
│  ├─ antall.csv
│  └─ resultater.csv
└─ Prøveflyt/
   ├─ restansehistorikk_hemato.csv
   ├─ restansehistorikk_solide.csv       # først når Solide-restanse finnes
   └─ restansehistorikk_<enhet>.csv      # senere enheter
```

Statistikkmappene beholder dagens navn for bakoverkompatibilitet.
`restansehistorikk.csv` erstattes av `restansehistorikk_hemato.csv` ved neste
vellykkede Hemato-restansekjøring. MolStat skal ikke slette den gamle filen
automatisk; operatøren kan fjerne den etter at Power BI-kilden er flyttet.

Hver enhetsfil bygges fra hele den permanente detaljhistorikken for den aktuelle
enheten og erstattes atomisk. En mislykket import, databaseoppdatering,
personvernkontroll eller publisering skal beholde forrige gyldige fil.

## Prøveflyt-datakontrakt

Grunnlaget er én rad per restanseanalyse per timesnapshot. Underanalyser
beholdes som egne rader, slik at valg av `Klonalitet` kan vise de konkrete
analysene som inngår i gruppen.

Kolonnene, i fast rekkefølge, er:

1. `Observert_tidspunkt`
2. `Enhet`
3. `Materiale`
4. `Analyse`
5. `Nukleinsyre`
6. `Analysegruppe_kode`
7. `Analysegruppe`
8. `Tidspunkt.prøvetaking`
9. `Tidspunkt.ankomst`
10. `Tidspunkt.analysebestilling`
11. `Prioritet.analyse`
12. `Prioritet.rekvisisjon`
13. `Status.analyse`
14. `Status.prelgruppe`
15. `Restansestatus`
16. `Svarfrist`
17. `Analyseresultat`
18. `Ekstern.analysekommentar`
19. `Klassifikatorversjon`

`Rapportgruppe` fjernes fordi `Analysegruppe_kode` og `Analysegruppe` er den
autoritative rapportinndelingen i denne datastrømmen. `Nukleinsyre` og
`Svarfrist` slås opp fra Hemato-statistikkens lookup-fil. De to fritekstfeltene
kopieres ordrett fra LVMS etter at `=T("...")`-innpakning er fjernet på samme
måte som for øvrige LVMS-felt.

CSV skrives med semikolon, CRLF-kompatible linjeskift og UTF-8 med BOM, slik at
norske tegn leses stabilt i Excel og Power BI.

## Personvern og tillitsgrense

Følgende strukturerte felt er forbudt i den offentlige detaljhistorikken og i
SharePoint-filen:

- `SampleID`;
- `PID`;
- `Workitemgruppe`/`WorkItem`;
- kildefilsti;
- kildefingeravtrykk.

Analyseresultat og ekstern analysekommentar eksporteres ordrett etter uttrykkelig
produktbeslutning. MolStat skal ikke forsøke å redigere, tolke eller maskere
innholdet. Den operative forutsetningen er at identifikatorer ikke skrives i
disse feltene. README og innstillingssiden skal opplyse om dette ansvaret uten
å antyde at friteksten er anonymisert.

Publiseringslaget beholder en eksakt kolonne-allowlist. Interne
dedupliseringsnøkler kan behandles på K-sensitiv, men må ikke finnes i tabellen
som den offentlige CSV-en bygges fra.

## Innstillinger

Innstillingssiden deles i:

1. globale felt for K-sensitiv rot, SharePoint-rot og LVMS-adresse;
2. én seksjon per aktiv enhet;
3. en egen rad for import og eksport av innstillinger.

Hemato og Solide viser lookup-fil for statistikk. Kapabiliteter som ennå ikke
finnes, skal ikke vise ubrukelige obligatoriske felt. Nye enheter kan senere
legge til felter gjennom den kontrollerte enhetsdefinisjonen.

Eksportfilen heter som standard `molstat-innstillinger.json` og skrives som
versjonert UTF-8 JSON. Den inneholder:

- skjemaversjon;
- K-sensitiv rot;
- SharePoint-rot;
- LVMS-adresse;
- klokkeslett for automatiske jobber;
- enhetsaktivering;
- enhetsspesifikke lookup- og konfigurasjonsstier.

Den inneholder aldri:

- brukernavn eller passord;
- informasjonskapsler eller sesjonstokener;
- Edge-profil eller profilinnhold;
- dynamisk CDP-port;
- databaseinnhold eller rådata.

Ved import parses og valideres hele filen før eksisterende innstillinger
endres. Ukjent skjemaversjon eller ugyldige typer avvises uten delvis lagring.
Gyldige, men utilgjengelige PC-spesifikke stier importeres og markeres som
`Må velges på denne PC-en`. Kjøring forblir sperret til obligatoriske stier er
tilgjengelige. Lagring og eksport skjer atomisk.

## Kontrollapp

Oversikten får et responsivt kortgitter med:

- en primær `Kjør alt`-knapp;
- aktive enhetskort for Hemato og Solide;
- deaktiverte kort for Lege, Flow, Pre og Hist;
- siste status og tilgjengelige kapabiliteter på hvert aktivt kort.

Hemato-kortet viser og starter `Statistikk + restanse`. Solide-kortet viser og
starter `Statistikk`. Knapper deaktiveres mens deres kjøring pågår. Andre
uavhengige enhetsknapper skal ikke låses unødvendig.

Den eksisterende pastellgule, Power BI-inspirerte paletten beholdes. All tekst,
fokusmarkering og status skal fortsatt møte WCAG-kontrastkravene som allerede
er testet. Funksjoner skal ikke være avhengige av ikon alene.

## Appikon

MolStat får et originalt, enkelt symbol som kombinerer molekyl/DNA og en liten
statistisk søyleform. Uttrykket bruker pastellgul bakgrunn, mørk brun/svart
forgrunn og få former, slik at det fungerer fra 16 × 16 til 256 × 256 piksler.

Leveranser:

- en høyoppløselig PNG med transparent eller kontrollert bakgrunn;
- en fleroppløselig Windows `.ico`;
- kobling til PyQt-vinduet og eventuell Windows-pakkekonfigurasjon som finnes i
  repoet.

Ikonet skal være lesbart uten tekst og ikke etterligne Power BI-logoen.

## README

README skrives om på norsk og skal dekke:

- hva MolStat gjør;
- aktive og kommende enheter;
- sikker dataflyt og mappestruktur;
- installasjon på jobb-PC;
- første gangs konfigurasjon;
- manuell og automatisk kjøring;
- import og eksport av innstillinger;
- Prøveflyt-kolonner og fritekstansvar;
- utviklings- og testkommandoer;
- lenker til den mer detaljerte driftsveiledningen.

README skal ikke inneholde lokale brukernavn, reelle nettverksstier,
pasientdata eller skjermbilder med sensitiv informasjon.

## Migrering og kompatibilitet

- Eksisterende innstillingsfil migreres til den nye versjonerte modellen ved
  lasting og lagres først når brukeren bekrefter.
- Eksisterende globale røtter og lookup-stier for Hemato/Solide beholdes.
- SQLite migreres additivt for de to nye fritekstkolonnene og eventuell
  enhetsnøkkel som mangler; gammel historikk får tom fritekst.
- Gammel aggregathistorikk beholdes internt, men blandes ikke inn i den
  detaljerte CSV-en.
- Eksisterende statistikkfilnavn og mapper endres ikke.
- CLI-jobbene `statistics` og `backlog` beholdes som kompatible innganger, men
  delegerer til det nye enhetsbaserte kjørelaget.

## Feilhåndtering

- En tom, manglende eller korrupt importfil endrer ikke gjeldende innstillinger.
- En obligatorisk sti som mangler gir en konkret melding per enhet.
- En ukjent enhetsnøkkel i importfilen ignoreres ikke stille; importen avvises
  med en forståelig feil.
- En feil i Hemato-restanse skal ikke rulle tilbake vellykket
  Hemato-statistikk, men `Kjør alt` skal rapportere delvis feil.
- Publiseringsfeil beholder siste gyldige SharePoint-fil.
- UI- og diagnostikkmeldinger skal aldri inneholde fritekstresultat,
  kommentarer eller identifikatorverdier.

## Test- og akseptansekriterier

Implementasjonen er ferdig når:

1. en detaljert Hemato-fil publiseres som
   `Prøveflyt/restansehistorikk_hemato.csv`;
2. filen inneholder eksakt kontrakt over, inkludert ordrett analyseresultat og
   kommentar, men uten forbudte strukturkolonner;
3. norske tegn overlever en bytebasert UTF-8/BOM-kontroll;
4. reell, lokal testdata gir én detaljrad per forventet restanseanalyse og alle
   kjente analyser får lookup-feltene sine;
5. `Kjør alt`, Hemato og Solide sender riktige eksplisitte kjøringsmål;
6. kommende enheter er synlige, utilgjengelige og tilgjengelige for
   hjelpemidler;
7. innstillinger kan eksporteres, importeres og round-trippes uten hemmelige
   felter;
8. ugyldig import er atomisk og utilgjengelige stier blokkerer kjøring;
9. gammelt innstillings- og databaseskjema migreres uten datatap;
10. appen viser det nye ikonet i testbar størrelse;
11. README beskriver den faktiske løsningen;
12. hele testpakken, bytekodekompilering og diff-kontroll er grønne.

