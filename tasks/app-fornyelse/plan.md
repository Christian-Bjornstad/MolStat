# MolStat: robust app, enhetsoppsett og sammenhengende dataflyt

Dato: 2026-09-17. Branch: `codex/robust-app-config`.
Status: kartlagt og planlagt; implementeringen nedenfor er ikke utført.

## Mål

Appen skal gjenbruke eksisterende database, tåle midlertidige hentefeil,
forklare feil presist og gjøre analyser for statistikk og restanse enkle å
vedlikeholde per enhet. Innstillinger, lokal behandling, SharePoint-publisering
og eksisterende Excel-søk skal inngå i én forståelig arbeidsflyt.

Brukeren har gitt frihet til utforming og bedt om planlegging først. Vi beholder
Python/PyQt6 og eksisterende datagrunnlag. Oppgavene står i [todo.md](todo.md).

## Hva kartleggingen viser

- `fetching.py` gjør en mislykket batch om til generell `RuntimeError`.
  `batch_runner.py` kjenner feiltrinnet, men denne informasjonen følger ikke
  strukturert helt opp til appen. `services.py` viser i hovedsak exceptiontypen.
  Dette forklarer den lite informative meldingen, ikke den sporadiske rotårsaken.
- `services._database()` skal allerede åpne `data/molstat.sqlite3` igjen og
  hoppe over migrering når versjonen er gjeldende (6). Lokal gjenåpning består.
  Feilen på jobb-PC er ikke reprodusert: SQLite-feilkode, faktisk sti, tilgang,
  låsing og migrering må undersøkes før valg av retting.
- Rapportlister finnes allerede i `config/units.json` og `backlog-report.json`.
  Restanseklassifisering og kolonner ligger i to andre JSON-filer. Oppsettet
  lastes fra installasjonstreet, mens tilgjengelige enheter/profiler og flere
  Hemato-koblinger er kodet i `modules.py`, `services.py` og `system.py`.
- Statistikkoppsettet leses ved henting, men restanseprosessoren opprettes
  tidligere. Et konsistent oppsett per kjøring er derfor et eget krav.
- Excel-søk er implementert: flere søk, prefiks/eksakt, analysedetaljer,
  årsdeling og atomisk publisering. Det genereres etter import; en låst fil
  eller eksportfeil kan etterlate en eldre lesekopi.

## Sammenheng med tidligere arbeid

[Tidligere plan](../plan.md), [tidligere oppgaver](../todo.md) og
[Excel-spesifikasjonen](../../SPEC-excel-search.md) beholdes som historikk og
funksjonskontrakter. Åpne bokser betyr ikke at Excel-søket må bygges på nytt.

| Tidligere åpne punkter | Videre oppfølging |
| --- | --- |
| Produksjonsheader og stabil WorkItem-identitet, oppgave 1 | Ny oppgave 12: kontroll i målmiljø; syntetiske tester i oppgave 10 |
| Mål-Excel-rekalkulering, oppgave 9 og Excel-kontrollpunkt | Ny oppgave 10 og 12 |
| Backup, retensjon og K-sensitiv målmappe | Ny oppgave 2, 3 og 12; ingen automatisk sletting før policy er avklart |
| Pilot og operativ overlevering, oppgave 15 | Ny oppgave 12 |

Ingen gamle godkjenninger eller produksjonskontroller markeres fullført uten
evidens. Brukerens erfaring med delvis fungerende søk tas inn i måltesten.

## Beslutninger for implementeringen

### 1. Presise feil og avgrenset gjenforsøk

Én feilmodell bærer kode, trinn, enhet, kjørings-ID, forsøk og om feilen kan
prøves igjen. Brukertekst forklarer hva som feilet og neste handling.
Tekniske logger skal ikke inneholde pasientverdier, rapportinnhold eller tokens.

Foreslåtte koder: `LVMS_TIMEOUT`, `LVMS_LOGIN_REQUIRED`, `DOWNLOAD_INCOMPLETE`,
`CONFIG_SYNTAX`, `CONFIG_INVALID`, `DB_BUSY`, `DB_ACCESS`, `DB_SCHEMA`,
`DB_INTEGRITY`, `PUBLISH_LOCKED`, `EXCEL_REFRESH_FAILED`.
Underliggende SQLite-kode bevares der tilgjengelig.

Kontroller faktisk side-/nedlastingsstatus fremfor bare faste pauser.
Maksimalt to automatiske gjenforsøk etter første forsøk, med ventetid og
avbrytbarhet, bare for klassifiserte midlertidige feil. Verifiser hva som
allerede er utført før rapporten sendes inn igjen. Import og publisering
skal ikke dupliseres ved gjenforsøk. Innlogging, ugyldig oppsett, ukjent skjema
og integritetsfeil krever retting, ikke blind gjentakelse.

### 2. Én redigerbar JSON-fil per enhet

Velg UTF-8 JSON: gjenbruker eksisterende format, gir entydig syntaks og
feilposisjon ved manglende komma/anførselstegn. Lever formaterte eksempelmaler.

`hemato.json` inneholder `schema_version`, stabil enhetsnøkkel, navn,
aktivering, valgt støttet prosessorprofil og separate rapportseksjoner:

- `statistics.antall`: rapport-ID, grupper og analysekoder.
- `statistics.resultater`: rapport-ID, grupper og analysekoder.
- `statistics.ekstraksjon`: egen kodeliste og separat hente-/arkiv-ID.
- `backlog`: rapport, grupper, analysekoder, klassifisering og terskler.
- Kolonnekartlegging, råfilens skilletegn/tegnsett og lookup-referanse.

Delte lister kan refereres eksplisitt innen samme fil. Ingen skjult arv mellom
rapporttyper. Lookup kan fortsatt være en egen tabellfil. Formatkontrakt og
syntetisk eksempel låses i oppgave 4 før parser/UI bygges.

Analyser kan legges til, deaktiveres og fjernes uten kodeendring innen støttede
prosessorprofiler. Historiske prøver og analyser slettes ikke ved deaktivering.
Helt nye beregningsregler eller nye LVMS-rapporttyper kan kreve programkode;
konfigurasjonsfiler skal ikke inneholde kjørbar kode eller SQL.

### 3. Valider ved import og før hver kjøring

Innstillinger får «Velg fil», «Valider», forhåndsvisning av endringer og
«Aktiver». Vis fil, linje/kolonne ved syntaksfeil og feltsti ved innholdsfeil.
Kontroller skjema, påkrevde felt, typer, ukjente felt, duplikate JSON-nøkler,
analysekoder, tomme lister, referanser, terskler og støttet prosessorprofil.

JSON-komma og rådataenes CSV-skilletegn er forskjellige ting. CSV skal leses
etter deklarert format og valideres med kolonner og korrekt quoting, ikke
med en sjekk av om teksten inneholder et komma.

En ugyldig import erstatter aldri aktivt oppsett. Før en kjøring leses hele
det aktive oppsettet på nytt og valideres samlet. Hvis det er endret til noe
ugyldig utenfor appen, blokkeres kjøringen med konkret feil. Et uforanderlig
oppsett med versjon/hash brukes gjennom hele kjøringen, slik at endringer
underveis først får effekt neste gang. Forrige gyldige oppsett kan gjenopprettes
eksplisitt; appen skal ikke skjule feil ved å bruke det automatisk.

### 4. Fast mappekontrakt

```text
K-sensitiv/MolStat/
  config/
    units/hemato.json
    units/solide.json
    lookups/
    revisions/
  data/molstat.sqlite3       # behold eksisterende relative databaseplassering
  data/backups/
  raw/statistics/<enhet>/    # eksisterende uforanderlig råarkiv
  work/<kjørings-id>/        # midlertidige nedlastinger, også restanse
  processed/<enhet>/<jobb>/  # validerte kandidater og siste ferdige output
  Prøvesøk.xlsx             # behold etablert plassering
```

Restansens permanenthistorikk ligger i databasen; råuttrekket er midlertidig.
Rydding skal være knyttet til kjøringsstatus og aldri slette en annen aktiv
kjørings filer. Definer levetid/retensjon før automatisk opprydding aktiveres.
Maskinlokale innstillinger, Edge-profil og sanitiserte logger ligger separat
under lokal MolStat-appmappe.

Bare validerte, godkjente publiseringsfiler går videre til valgt SharePoint-rot.
Behold dagens filnavn/kolonnekontrakter for Power BI. Enhetsoppsett skal ikke
kunne omgå personverngrensen ved å utvide publiseringskolonner fritt.
Mislykket publisering kan prøves igjen fra ferdig kandidat uten nytt uttrekk.

Eksisterende røtter kartlegges før migrering. Vis kilde/mål og funn, valider
kopier og bytt referanser først når alt er kontrollert. Ingen automatisk
sletting, ny tom database eller stille valg mellom flere databasekandidater.

### 5. Gjenåpning og databasevern

Skill mellom «bruk eksisterende» og «opprett ny». Vis identifisert database,
skjemaversjon og status. Undersøk både stasjonsbokstav og UNC-sti, også
URI-konstruksjon i skrivebeskyttet åpning, samt mappe-/journalrettigheter.
Kontroller at forbindelser faktisk lukkes: transaksjonskontekst er ikke en
eksplisitt ressurslukking. Én skriver om gangen og kontrollert låsehåndtering.

Migrer eldre støttede skjemaer først etter verifisert backup. Ukjent nyere
skjema eller skadet fil gir en forståelig blokkering med bevarte originaler.
Test gjenoppretting på kopier. Nettverksdiskens oppførsel må verifiseres på
jobb-PC; beståtte lokale tester beviser ikke at nettverkslåsing fungerer.

### 6. Samlet visuell utforming

Behold PyQt6. Velg Segoe UI, rolige flater og faste størrelser/avstander.
Palett: bakgrunn `#F4F7FB`, flate `#FFFFFF`, tekst `#172033`, sekundærtekst
`#526176`, hovedfarge `#2457C5`, sidefelt `#18263D`, kant `#D6DFEB`.
Status: grønn `#18734A`, varsel `#8A5800`, feil `#B42332`.
Kontrast må måles for faktiske fargepar før levering.

Bruk 8 px avrunding på kontroller, 12 px på kort og avstandsskala 8/16/24/32.
Samle hover, fokus, deaktivert og status i temaverdier; ingen spredte særfarger.
Status vises alltid med tekst/ikon i tillegg til farge.

Navigasjon: Oversikt, Kjøringer, Enheter, Innstillinger og Diagnostikk.
Innstillinger grupperes i lagring/database, enhetsfiler, LVMS og tidsplan.
Oversikten viser siste vellykkede import, gjeldende kjøring/trinn,
publiseringsstatus og Excel-oppdatering hver for seg. Tilgjengelig tastaturfokus,
skjermskalering og rulling skal testes med Qt.

### 7. Excel som del av systemet

Bygg videre på eksisterende søk. Skill manglende treff fra gammel lesekopi,
formelfeil og ufullstendig import. Legg til tydelig oppdateringsstatus i appen
og mulighet til å regenerere fra databasen uten LVMS-kjøring.
Test flere søk, ledende nuller, gjentatte analyser, årsdeling, tomt register,
prefiks og eksakt søk. Fil som er låst i Excel skal beholde forrige gyldige
versjon og få en forståelig status og ny publiseringsmulighet.

## Rekkefølge og kontrollpunkter

1. Diagnostikk og databasegjenåpning (oppgave 1–3).
2. Enhetskontrakt, import og full Hemato-flyt (oppgave 4–7).
3. Mappeovergang og kontrollert gjenforsøk (oppgave 8–9).
4. Excel-forbedring og samlet UI (oppgave 10–11).
5. Regresjon, målmiljøtest og utrulling (oppgave 12).

Hver leveranse får målrettede tester før neste. Ikke kombiner omfattende
utseendeendring med datamigrering i samme endring. Hele appen skal kunne
kjøres med syntetiske røtter uten Citrix under utvikling.

## Verifikasjon utført under planlegging

111 målrettede tester består: 56 for database/services/fetching/batch/enhets-
og restansedomene, 43 for migrering/backup/innstillinger/personvern/Qt, 12 for
Excel. `git diff --check` bestod før plandokumentene ble skrevet.
Full testsuite, virkelig Excel-rekalkulering, nettverksdisk og live LVMS er
ikke verifisert i denne kartleggingen. Ingen produksjonsdatabase er endret.

## Når Citrix og jobbmiljø trengs

Først ved reproduksjon av den sporadiske hentefeilen og endelig pilot:
eksakt SQLite-feilkode med sanitiserte tekniske detaljer, åpning av samme
database etter restart, LVMS-rapportheader/identitet, reell nedlasting og
mål-Excel med syntetiske søk. Be brukeren åpne miljøet når disse testene er
klargjort; kartlegging og lokal implementering kan gå uten dette.
