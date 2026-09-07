# MolStat – historikk, Prøveflyt i Power BI og videreutvikling

**Dato:** 07.09.2026  
**Status:** Godkjent design, avventer gjennomgang av skrevet spesifikasjon

## Mål

MolStat skal bevare komplett statistikkhistorikk, publisere en
identifikatorfri restansehistorikk til SharePoint og erstatte den lokale
nettlesertavlen med en automatisk oppdatert Power BI-rapport. Samtidig skal
kontrollappen få et lyst, pastellgult Power BI-inspirert uttrykk, Edge/CDP skal
bruke en robust dynamisk port, og tidsstyrte kjøringer skal kunne installeres,
kontrolleres og repareres fra MolStat.

Løsningen skal gjøre det enklere å legge til nye statistikktyper uten å bygge
nye hardkodede kontrollflyter i appens service-lag.

## Nåtilstand og bekreftede avvik

Kartleggingen er gjort på grenen `docs/powerbi-restanse-mal` ved commit
`f9dd023`.

1. Den aktive statistikkflyten henter et overlappende inkrementelt vindu på tre
   dager, arkiverer filene og sender bare filene fra denne kjøringen til
   `StatisticsProcessor`. SharePoint-filene erstattes deretter atomisk. Kode
   for å slå sammen hele råarkivet finnes, men brukes ikke av den aktive
   produksjonsflyten. Dette forklarer at Power BI bare får de siste dagene i
   stedet for historikk fra 2024.
2. Restanseimporten erstatter tabellen `backlog_sample` ved hver kjøring. Det
   finnes ingen permanent aggregert snapshot-tabell, og appen genererer ikke
   `restansehistorikk.csv`. Den eksisterende Power BI-guiden beskriver derfor
   et datasett som ikke produseres av MolStat.
3. Edge/CDP forhåndsvelger fortsatt en ledig port, sender portnummeret til Edge
   og setter `--remote-allow-origins`. Den dokumenterte robuste løsningen er å
   la Edge velge port med `--remote-debugging-port=0`, lese
   `DevToolsActivePort` og åpne WebSocket uten Origin-header.
4. Windows Task Scheduler-støtte og tester finnes, men oppgavene er ikke
   installert på den undersøkte PC-en. Dagens installer oppretter også en
   tavleserveroppgave som ikke skal finnes når Power BI erstatter
   nettlesertavlen.
5. PyQt6-temaet er klinisk blått. Det eksisterende designsystemet og
   `theme.py` må oppdateres samlet for å unngå at dokumenterte tokens og
   implementerte farger divergerer.
6. Power BI Desktop har `pbi-cli` 3.10.10 tilgjengelig og den lokale
   Desktop-instansen kan oppdages. Den åpne modellen var tom under
   kartleggingen. `power-bi-codex` er derfor en valgfri arbeidsflytforsterker,
   ikke en forutsetning for rapportbyggingen.

Alle målrettede tester for publisering, historisk merge, restansebehandling,
CDP og tidsstyring besto før designarbeidet. Testene dokumenterer dagens kode,
men dekker ikke avvikene over.

## Kildekontrakt for restanse

Referansefilene er:

- `PAT-DIT RESTANSE-OU.csv`, et sensitivt LVMS-uttrekk;
- `Hemato - Restanseliste LVMS.xlsx`, den operative oversikten over
  analysegrupper, rapportgrupper og analysekoder.

Excel-oversikten inneholder 23 analysegrupper. Alle 23 gruppene,
rapportgruppene og analysekodene matcher `config/backlog-analyses.json`
nøyaktig. Konfigurasjonsfilen er den versjonskontrollerte autoritative
mappingen. Excel-filen brukes som verifiseringskilde, ikke som en runtime-
avhengighet.

Den undersøkte CSV-en inneholdt 68 rader. MolStats eksisterende parser leste
den uten ugyldige rader og slo den sammen til 35 unike grupperecords for
Klonalitet. LVMS-formatets `=T("...")`-innpakking håndteres allerede.

Rå CSV, prøveidentifikatorer, pasientidentifikatorer, resultater og kommentarer
skal aldri publiseres til SharePoint eller tas inn i Power BI-modellen.

## Målarkitektur

### Overordnet dataflyt

```text
LVMS
  ├─ statistikkrapporter ─> uforanderlig råarkiv på K-sensitiv
  │                           └─ full arkiv-merge og prosessering
  │                               └─ personvernkontroll
  │                                   └─ SharePoint/Hemato og SharePoint/Solide
  │
  └─ restanserapport ─────> sensitiv nåtilstand i SQLite på K-sensitiv
                              └─ aggregert timesnapshot i SQLite
                                  └─ deterministisk historieeksport
                                      └─ personvernkontroll
                                          └─ SharePoint/Prøveflyt
                                              └─ Power BI
```

Råarkivet og SQLite er autoritative. SharePoint inneholder bare avledede,
identifikatorfrie presentasjonsdata og kan alltid bygges opp igjen.

### Felles modulgrense

Hemato, Solide og Prøveflyt skal registreres som datamoduler bak et lite felles
grensesnitt. En modul beskriver:

- stabil modulnøkkel og visningsnavn;
- hentedefinisjon og tidsplan;
- prosessor;
- publiseringsfiler og eksplisitt kolonne-allowlist;
- målmappe relativt til konfigurert SharePoint-rot;
- statusfelter som kontrollappen kan vise.

Service-laget skal iterere registrerte moduler fremfor å inneholde egne
hardkodede grener for `hemato`, `solide` og senere statistikktyper. Modellen er
ikke et dynamisk plugin-system og skal ikke laste vilkårlig kode fra
konfigurasjon. Nye prosessorer implementeres fortsatt som testet Python-kode og
registreres eksplisitt.

## Historisk statistikk for Hemato og Solide

Den inkrementelle hentingen beholdes med tre dagers overlapp. Etter at nye
filer er arkivert skal prosessoren finne alle arkiverte filer for hver
rapport-ID under `raw/statistics/<enhet>`, slå dem sammen og deduplisere før
godkjent prosesseringslogikk kjøres.

Krav:

- første kjøring henter fra 01.01.2024;
- senere kjøringer henter siste fullførte dato minus to dager til dagens dato;
- prosessert output bygges fra hele arkivet, ikke bare siste intervall;
- eksakte duplikatrader fjernes deterministisk;
- råfiler overskrives aldri;
- en mislykket merge, prosessering eller personvernkontroll beholder siste
  gyldige SharePoint-publisering;
- enhetens `antall.csv` og `resultater.csv` erstattes atomisk som ett validert
  filsett;
- tester skal bevise at en tredagers inkrementell kjøring ikke reduserer den
  publiserte historikken.

## Permanent restansehistorikk

### Sensitiv nåtilstand

`backlog_sample` fortsetter å representere siste komplette sensitive
LVMS-snapshot. Tabellen erstattes transaksjonelt etter vellykket parsing. Den
er kun intern på K-sensitiv og brukes til å beregne aggregater.

### Aggregert snapshot-tabell

Databasen får en ny migrasjon og en append-only tabell for aggregert historikk.
Kornet er én rad per:

`observert_tidspunkt × enhet × analysegruppe × klassifikatorversjon`.

Hvert snapshot inneholder alle de 23 aktiverte gruppene, også grupper med null
prøver. Dermed betyr fravær av en rad aldri det samme som null.

Foreslåtte felt:

- `observed_at`;
- `unit_key`;
- `analysis_code` og stabilt visningsnavn;
- `ready_count`;
- `awaiting_approval_count`;
- `in_transit_count`;
- `overdue_count`;
- `median_ready_hours`;
- `oldest_ready_hours`;
- `severity`;
- `invalid_rows` og `excluded_rows`;
- `source_is_fresh`;
- `classifier_version`;
- kildefingeravtrykk for idempotens og revisjonsspor.

En unik nøkkel skal gjøre gjentakelse av samme vellykkede kjøring idempotent.
Snapshot og oppdatering av sensitiv nåtilstand skal skje i én avgrenset
databaseoperasjon, slik at en halvferdig import ikke blir synlig.

### SharePoint-eksport

Etter hvert vellykket snapshot bygger MolStat hele
`restansehistorikk.csv` deterministisk fra snapshot-tabellen. Filen skrives som
UTF-8 med semikolon og sorteres stabilt på tidspunkt, enhet og analysegruppe.

Målsti:

`<sharepoint_root>/Prøveflyt/restansehistorikk.csv`

SharePoint-filen skal bare inneholde følgende presentasjonskontrakt:

- `Observert_tidspunkt`;
- `Enhet`;
- `Analysegruppe_kode`;
- `Analysegruppe`;
- `Klar`;
- `Mangler_godkjenning`;
- `På_vei`;
- `Over_frist`;
- `Median_klare_timer`;
- `Eldste_klare_timer`;
- `Alvorlighetsgrad`;
- `Ugyldige_rader`;
- `Ekskluderte_rader`;
- `Kilde_fersk`;
- `Klassifikatorversjon`.

Kildefingeravtrykk, SampleID, PID, WorkItem, råresultat, kommentarer, filstier
og databaseinformasjon skal ikke inngå i eksporten. Kolonnene valideres mot en
eksakt allowlist før atomisk erstatning. Feil beholder siste gyldige fil.

Historikken starter når snapshot-funksjonen settes i produksjon. Eldre
restansehistorikk kan bare importeres dersom det finnes tidligere tidsstemplete
kilder som kan valideres; systemet skal ikke konstruere kunstig historikk fra
ett nåværende restanseuttrekk.

## Power BI-modell

Rapporten bygges som PBIP med PBIR-format slik at definisjoner kan
versjonskontrolleres og valideres. Det leveres også en distribuerbar Power BI-
artefakt etter at PBIP-modellen er validert i Desktop.

### Semantisk modell

- `FaktRestanse`: én rad per snapshot og analysegruppe fra
  `restansehistorikk.csv`.
- `DimDato`: separat, sammenhengende datodimensjon med én unik rad per dato.
- `DimAnalysegruppe`: stabile gruppefelt utledet fra faktakilden eller en
  kontrollert mapping.

Faktatabellen skal ikke merkes som datotabell. Alle «nå»-mål bruker høyeste
tilgjengelige `Observert_tidspunkt`, ikke `TODAY()`, slik at rapporten fortsatt
viser siste gyldige snapshot dersom en kjøring uteblir.

Additive antall kan summeres innen ett snapshot. Verdier fra flere snapshots
skal ikke summeres som om de var hendelser. Målene skal derfor etablere
eksplisitt snapshot-kontekst før totaler beregnes.

### Rapportsider

1. **Prøveflyt – nå** viser siste snapshot. Alle analysegrupper vises i et
   dynamisk kategori-basert kortoppsett, sortert kritisk, advarsel, normal.
   Hver gruppe viser Klar, Mangler godkjenning, På vei, Over frist og eldste
   ventetid. Siste oppdatering og kildeferskhet er alltid synlig.
2. **Utvikling** viser time- og dagstrender for valgt gruppe og status uten å
   summere snapshot-lagre over tid. Brukeren kan filtrere enhet,
   analysegruppe, status og datoperiode.
3. **Analysegruppe** er en aggregert drill-through-side med historikk,
   ventetider og datakvalitet for valgt gruppe. Den inneholder ingen prøve- eller
   pasientdetaljer.

Drill-through-feltet skal være en faktisk datarolle i kildevisualet. Rapporten
skal ikke bruke seks eller 23 manuelt filtrerte kort. Nye analysegrupper skal
dukke opp uten at rapportdefinisjonen redigeres.

## Visuelt system

MolStat-kontrollappen og Power BI-rapporten bruker samme varme, lyse
designspråk:

| Rolle | Farge |
|---|---|
| Power BI-gul aksent | `#F2C811` |
| Pastellgul bakgrunn | `#FFF9E6` |
| Lys gul sekundærflate | `#FFF3C4` |
| Kortflate | `#FFFFFF` |
| Hovedtekst | `#2B2618` |
| Sekundærtekst | `#5C553D` |
| Mørk sidemeny | `#3A321B` |
| Fokusmarkering | `#8A6A00` |
| Normal | `#1B7D3A` |
| Advarsel | `#9A6A00` |
| Kritisk | `#A4262C` |

Kontrollerte kontrastpar oppfyller minst WCAG AA for normal tekst. Gul brukes
som bakgrunn eller aksent med mørk tekst, ikke som lys tekst på hvit bakgrunn.
Status kommuniseres alltid med tekst i tillegg til farge.

Eksisterende tastaturnavigasjon, tilgjengelige navn, 44-pikslers minste
kontrollhøyde og synlig fokus beholdes. Designsystemets masterfil og PyQt6-
temaet oppdateres i samme oppgave.

Kontrollappen endres slik:

- «Åpne restansetavle» erstattes med «Åpne Prøveflyt i Power BI»;
- innstillinger får en valgfri, validert Power BI-rapportadresse;
- Prøveflyt-status viser siste henting, siste publisering, antall snapshots og
  datakvalitetsstatus;
- SharePoint-status skiller mellom Hemato, Solide og Prøveflyt der dette gir en
  handlingsrettet feil;
- nettlesertavlen fjernes først etter at Power BI-flyten er validert ende til
  ende.

## Edge/CDP

Den eksisterende portreservasjonen erstattes i hele den frosne LVMS-runtime-
kopien:

1. Start Edge med `--remote-debugging-port=0` og loopback-adresse.
2. Fjern `--remote-allow-origins`.
3. Slett en foreldet `DevToolsActivePort` før oppstart når den dedikerte
   MolStat-profilen gjenbrukes.
4. Vent avgrenset på `<profile>/DevToolsActivePort`, valider første linje som
   et gyldig ikke-privilegert portnummer og bruk bare loopback.
5. Oppdag mål via Edge sitt lokale JSON-endepunkt på den faktiske porten.
6. Åpne WebSocket med `suppress_origin=True` og uten eksplisitt Origin-header.
7. Behold avgrensede timeouts, opptil tre oppstartsforsøk og sikker avslutning
   av kun prosessen MolStat startet.

Tester skal dekke foreldet/manglende/ugyldig portfil, forsinket portfil,
prosess som avsluttes tidlig, Origin-undertrykking og vellykket dynamisk
oppdagelse. Eksisterende testsuite for CDP-kall og LVMS-batchflyt skal fortsatt
bestå.

## Tidsstyrte jobber

Windows Task Scheduler er produksjonsmekanismen; «cron-jobber» brukes bare som
et uformelt navn i brukerkommunikasjon.

MolStat skal installere to oppgaver:

- statistikk daglig kl. 05:00 lokal tid;
- restanse hver hele time kl. 06:00–18:00 lokal tid.

Oppgavene bruker `MultipleInstancesPolicy=IgnoreNew`, og databaseleasen er en
ekstra sperre mot overlapp på tvers av PC-er. `StartWhenAvailable` beholdes.
Kjøringene skal bruke lokal tid konsekvent når de beregner forfall.

Kontrollappen skal kunne:

- vise om hver oppgave finnes, er aktiv og har forventede triggere;
- vise siste resultat og neste kjøring uten å eksponere interne stier;
- installere eller reparere oppgavene etter at konfigurasjonen er validert.

Tavleserveroppgaven og `serve`-kommandoen fjernes når Power BI-erstatningen er
godkjent. Fjerning skal være eksplisitt og avgrenset til MolStats kjente
oppgavenavn.

## Feilhåndtering og observasjon

- Statistikk- og restansejobber forblir separate transaksjoner.
- Henting kan arkivere rådata uten at en senere prosesseringsfeil ødelegger
  tidligere publisering.
- Snapshot-eksport bruker en midlertidig fil i målmappe og atomisk erstatning.
- Personvernfeil stopper publisering og beholder siste gyldige output.
- Appen viser modul, trinn, tidspunkt og handlingsrettet feilårsak, men aldri
  rå rader, identifikatorer eller sensitive filstier.
- Publiseringsmetadata lagres slik at appen kan skille vellykket henting fra
  vellykket SharePoint-publisering.

## Power BI Codex

`pbi-cli` er den faktiske lokale motoren. Den installerte versjonen kan koble
til Power BI Desktop og tilbyr kommandoer for rapporter, visualer, tema,
validering og reload. `power-bi-codex` tilfører primært Codex-rettede
arbeidsflyter og guardrails.

Derfor skal pluginen ikke ligge i kritisk sti. Før eventuell installasjon skal
plugininnhold, manifest, installasjonsskript og CLI-versjonskrav gjennomgås.
Den kan tas i bruk etter at CSV-kontrakten og PBIP-strukturen er etablert, og
bare dersom verifikasjonskommandoene passer den lokale CLI-versjonen eller en
kontrollert oppgradering er godkjent.

## Migrering og utrulling

Implementeringen deles i vertikale, testbare steg:

1. reparer full historisk statistikk-merge og verifiser SharePoint-output;
2. migrer databasen og lagre aggregert restansehistorikk;
3. generer og publiser den identifikatorfrie Prøveflyt-filen;
4. bytt Edge/CDP til faktisk dynamisk port;
5. reparer og installer de to tidsstyrte oppgavene;
6. oppdater kontrollapp og designsystem;
7. bygg og valider PBIP/PBIR mot syntetiske data, deretter aggregert
   produksjonsoutput;
8. fjern nettlesertavle, `serve`-kommando og tavleserveroppgave;
9. vurder `power-bi-codex` etter at den ordinære pbi-cli-flyten fungerer.

Hvert steg skal etterlate MolStat i en kjørbar tilstand. Nettlesertavlen kan
eksistere midlertidig i kode under byggingen, men regnes ikke som ferdig
sluttarkitektur.

## Akseptansekriterier

1. En statistikkjobb som bare henter siste tredagersvindu publiserer fortsatt
   komplett deduplisert historikk fra 01.01.2024.
2. Restansejobben lagrer ett idempotent aggregert snapshot for alle aktiverte
   analysegrupper ved hver vellykkede timekjøring.
3. `SharePoint/Prøveflyt/restansehistorikk.csv` kan bygges opp igjen fra SQLite
   og inneholder ingen forbudte identifikatorfelt.
4. Power BI-siden «Prøveflyt – nå» viser siste tilgjengelige snapshot og alle
   grupper dynamisk; historikksiden viser korrekt utvikling uten å summere
   snapshot-lagre feil.
5. Power BI erstatter nettlesertavlen, og MolStat åpner den konfigurerte
   Power BI-rapporten.
6. App og rapport følger det godkjente pastellgule temaet med WCAG AA-kontrast,
   synlig fokus og tekstlige statusetiketter.
7. Edge bruker port `0`, leser `DevToolsActivePort` og undertrykker WebSocket-
   Origin; den gamle portreservasjonen og allow-origin-argumentet er fjernet.
8. Bare de to forventede Windows-oppgavene finnes etter installasjon:
   statistikk 05:00 og restanse 06:00–18:00 lokal tid. Overlapp avvises.
9. En ny statistikkmodul kan registreres gjennom den felles modulgrensen uten
   å legge til en ny modulspesifikk gren i service-laget.
10. Hele testpakken består, og syntetisk ende-til-ende-test beviser flyten fra
    arkiv/snapshot gjennom personvernkontroll til publiserte filer.

## Avgrensninger

- Power BI Service-, gateway- og tenantoppsett administreres utenfor MolStat.
- MolStat publiserer til den lokalt synkroniserte SharePoint-roten som allerede
  brukes for Hemato og Solide.
- Ingen historiske restansesnapshots fabrikeres fra ett enkelt gammelt uttrekk.
- Ingen generisk tredjeparts plugin-plattform bygges i MolStat.
- Produksjonsnøkler, SharePoint-adresser og sensitive stier legges ikke i Git.
