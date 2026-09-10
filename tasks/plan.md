# Implementation Plan: MolStat prøveregister og Excel-søk

## Overview

MolStat skal bruke eksisterende SQLite-database på K-sensitiv som autoritativt
prøveregister. RESTANSE skal alltid hentes for perioden 01.01.2024
til dagens dato og oppdatere én komplett nåtilstand uten permanent råfilarkiv.
Statistikkrapportene skal kobles til de samme prøvene og analyseforekomstene.
Etter vellykket import genererer MolStat en makrofri `Prøvesøk.xlsx` på
K-sensitiv med enkelt formelbasert oppslag på prøvenummer eller MolStat-ID.

Godkjente spesifikasjoner er indeksert i `CAPABILITY-MAP.md`.

## Assumptions

1. MolStat genererer en stabil intern MolStat-ID automatisk.
2. Målmiljøet bruker Microsoft 365 Excel med `LET`, `FILTER` og `XLOOKUP`.
3. Excel-filen åpnes fra samme K-sensitive område som brukerne allerede har tilgang til.
4. Bare én MolStat-prosess skriver til databasen om gangen. Excel skriver aldri tilbake.
5. Nåværende RESTANSE- og statistikkoutput til SharePoint skal fungere uendret med samme personverngrense.
6. Faktisk WorkItem-/ordrelinjefelt verifiseres før identitetsalgoritmen låses.

## Architecture Decisions

- Utvid `molstat.sqlite3` i stedet for å etablere en ny database. Dette beholder én transaksjonsgrense og én writer lease.
- Skill permanent prøveidentitet, analyseforekomst, kildeobservasjon og nåværende restanse. En forekomst slettes ikke fordi den forsvinner fra RESTANSE.
- Bruk LVMS WorkItem-/ordrelinje-ID som forekomstnøkkel når tilgjengelig. Reserveidentitet er en dokumentert, deterministisk kombinasjon som aldri bruker mutable status-/resultatfelt.
- Behold Statistikkens uforanderlige råarkiv. RESTANSE bruker bare en midlertidig arbeidsfil og teknisk importmetadata.
- Generer Excel fra én konsistent, skrivebeskyttet database-snapshot. Arbeidsboken har ingen databasekobling, makro eller SharePoint-publisering.
- Bruk en liten, vedlikeholdt XLSX-generator bare dersom den kan installeres i Python FELLES og består en kompatibilitetstest. Excel COM-automatisering inngår ikke.
- Publiser arbeidsboken med staging, validering og atomisk filbytte. Hvis målfilen er låst, beholdes forrige gyldige fil og neste kjøring prøver igjen.
- Lag identifikatorer som tekst og datoer som ekte Excel-datoer. Del analysedata på årsark før en tabell nærmer seg Excels radgrense.

## Dependency Graph

```text
LVMS identitetskontrakt
        │
        ▼
SQLite schema v5
        │
        ▼
Registry repository/query API
        │
        ├───────────────┐
        ▼               ▼
RESTANSE current   Statistics linking
        │               │
        └───────┬───────┘
                ▼
      Backup and integrity
                │
                ▼
       Excel read model
                │
                ▼
 XLSX writer and atomic publish
                │
                ▼
 Service wiring and full verification
```

## Data Model

### Permanent identity

- `sample`: intern ID, MolStat-ID, første/siste observert.
- `sample_identifier`: kilde, identifikatortype, original og normalisert verdi.
- `analysis_occurrence`: prøve, analysekode, bestillingstid og stabil kilde-ID.
- `analysis_event`: bestilt/ankommet/ekstrahert/besvart med tidspunkt og kilde.
- `source_observation`: første/siste observasjon per rapporttype.
- `import_run`: jobbmetadata, intervall, hash, radantall og status.

### Current state

- `backlog_current`: forekomstene fra siste komplette, vellykkede RESTANSE-import.
- Eksisterende aggregert/detaljert Prøveflyt-historikk migreres ikke inn i registeret og slettes ikke.
- Nåtilstanden erstattes i samme transaksjon som nye identiteter og observasjoner lagres.

## Excel Contract

`Prøvesøk.xlsx` får arkene i denne rekkefølgen:

1. `Prøvesøk`: søkecelle, treffliste, valgt prøve og analyser.
2. `Prøver`: én skrivebeskyttet tabellrad per prøve.
3. `Analyser`: én rad per analyseforekomst, eventuelt delt i årsark ved volum-terskel.
4. `Om`: sist oppdatert, datagrunnlag og kort bruksforklaring.

Oppslagsarket støtter:

- eksakt søk på prøvenummer og MolStat-ID;
- prefikssøk som kan returnere flere prøver;
- tydelig `Ingen treff` og `Skriv inn prøvenummer eller MolStat-ID`;
- analysedetaljer for et entydig treff;
- synlig `I RESTANSE nå`, kilde og relevante tidspunkter;
- ledende nuller og lange identifikatorer uten Excel-konvertering.

Formler lagres med invariant OOXML-syntaks. Den norske Excel-installasjonen
lokaliserer funksjonsnavn og skilletegn ved visning.

## Implementation Phases

### Phase 1: Identity foundation

- Task 1: Verifiser LVMS-identitetskontrakten.
- Task 2: Migrer databasen additivt til registerskjema.
- Task 3: Implementer idempotent register- og søke-API.

### Checkpoint: Foundation

- Dagens database migrerer uten tap.
- Samme prøve får samme MolStat-ID.
- Gjentatte analyser beholdes som separate forekomster.

### Phase 2: Source integration

- Task 4: Gjør RESTANSE-vinduet fast og fjern ny råfilarkivering.
- Task 5: Bygg transaksjonell `backlog_current`.
- Task 6: Koble Statistikk til registeret uten outputendring.

### Checkpoint: Source integration

- RESTANSE spør alltid 01.01.2024–i dag.
- Forsvunne restanser slettes ikke fra registeret.
- Statistikkens eksisterende gullstandard består.

### Phase 3: Operational safety

- Task 7: Legg til backup, integritetskontroll og migreringsvern.
- Task 8: Belastnings- og spørringsoptimaliser registeret.

### Checkpoint: Data safety

- Feilinjeksjon ruller tilbake hele importen.
- Verifisert backup kan åpnes og gjenopprettes.
- Søk bruker forventede indekser ved syntetisk flerårsvolum.

### Phase 4: Excel delivery

- Task 9: Gjennomfør XLSX-kompatibilitetstest og lås generatorvalg.
- Task 10: Implementer Excel-lesemodell og workbook-layout.
- Task 11: Implementer formler, validering og årsdeling.
- Task 12: Implementer atomisk publisering og låst-fil-håndtering.

### Checkpoint: Excel

- Filen åpnes uten reparasjonsvarsel i målversjonen av Excel.
- Eksakt søk, prefikssøk og detaljer rekalkulerer korrekt.
- Alle ark er visuelt kontrollert og uten formelfeil.

### Phase 5: Wiring and rollout

- Task 13: Koble eksport til vellykkede MolStat-kjøringer og status.
- Task 14: Kjør full ende-til-ende-, personvern- og regresjonsverifikasjon.
- Task 15: Oppdater operatørdokumentasjon og gjennomfør kontrollert utrulling.

## Verification Strategy

- Enhetstester for normalisering, nøkkelgenerering, forekomstidentitet og Excel-lesemodell.
- Migreringstester fra dagens schema v4 med eksisterende rader bevart.
- Feilinjeksjon før og under database-commit og filbytte.
- Regresjonstester for dagens Statistikk- og Prøveflyt-output.
- Syntetisk ende-til-ende-test med samme prøve i RESTANSE, ANTALL og RESULTATER.
- Syntetisk volumtest med minst ti års prøver og flere analyseforekomster per prøve.
- Workbook-inspeksjon av verdier/formler, rekalkulering og formelfeilskann.
- Visuell rendering av alle ark og manuell åpning i jobb-PC-ens Excel.
- Full `python -m pytest`, `compileall` og `git diff --check` før ferdigmelding.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Ingen stabil WorkItem-ID i alle rapporter | Høy | Verifiser først; ikke slå sammen tvetydige forekomster automatisk |
| Prøvenummer gjenbrukes | Høy | Identitetsgrense inkluderer kildesystem og utvides med verifisert år/enhet ved behov |
| Excel-fil blir for stor | Middels | Én prøverad per prøve, årsdeling av analyser og målt terskel før 1 048 576 rader |
| Bruker har arbeidsboken åpen under oppdatering | Middels | Staging, atomisk bytte, behold forrige fil og retry ved neste kjøring |
| XLSX-bibliotek finnes ikke i Python FELLES | Middels | Tidlig kompatibilitetstest og eksplisitt beslutningsport før avhengighet legges til |
| SQLite ligger på SMB/nettverksdisk | Høy | Én utpekt skriver, eksisterende lease, `DELETE` journal og restore-test; databaseserver kreves for reell flerbrukerskriving |
| Sensitive felt havner i feil output | Høy | Separat Excel-allowlist, lokal K-sensitiv målrot og personvernregresjonstest |
| Ny registerskriving endrer statistikkresultater | Høy | Separat intern kontrakt og eksisterende celle-for-celle-gullstandard |

## Rollout and Recovery

1. Ta verifisert SQLite-backup før schema v5-migrering.
2. Kjør migrering og registerimport med syntetiske data i midlertidige røtter.
3. Kjør mot produksjonsuttrekk uten Excel-publisering og sammenlign radkontroller.
4. Generer `Prøvesøk.xlsx` til en separat pilotmappe på K-sensitiv.
5. Verifiser søk med godkjente prøver på jobb-PC.
6. Aktiver automatisk eksport etter vellykket kjøring.
7. Ved Excel-feil deaktiveres bare eksporten. Database og eksisterende MolStat-flyt fortsetter.
8. Ved databaseskjema-feil gjenopprettes den verifiserte pre-migreringsbackupen.

## Open Decisions Before Relevant Tasks

- Task 1 må fastslå den faktiske stabile LVMS-identifikatoren.
- Task 7 må få en godkjent backup-retensjon før automatisk rotasjon aktiveres.
- Task 9 må dokumentere generatorvalg og eventuell ny produksjonsavhengighet før Task 10.
- Før produksjonsaktivering må ansvarlig K-sensitiv målmappe og tilgangsgruppe bekreftes.
