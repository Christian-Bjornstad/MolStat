# Enhetsfiler og drift

## Oppgradering og database

Velg samme K-sensitive MolStat-rot som tidligere. Databasen ligger under
`data/molstat.sqlite3`. Velges selve databasemappen, stopper appen med
`DB_LOCATION` fremfor å lage en erstatningsdatabase i en ny undermappe.

Schema 7 skiller restansens nåtilstand per enhet. Før migrering av eksisterende
database lager appen verifisert backup under `data/backups`. Prøver,
MolStat-ID-er og historikk beholdes. Gjeldende skjema åpnes uten ny migrering.

Tilgjengelig eldre `config/units.json` og Hematos restansefiler overføres ved
første overgang. Originaloppsettet kopieres under `config/migration`.
Ugyldig gammelt oppsett blokkerer overføringen. Når de eldre filene ikke finnes
i installasjonen, brukes medfølgende maler: importér da tidligere lokale
tilpasninger før uttrekk.

## Redigere analyser

Velg JSON-fil under «Analyser og rapporter» i Innstillinger. «Valider fil»
viser kodetall og konkrete feil. «Valider og lagre» aktiverer oppsettet samlet.
Ugyldige filer erstatter ikke gjeldende innstillinger. «Åpne filmappe» åpner
mappen med aktiv fil. Maler følger installasjonen under `molstat/defaults/units`.

Filseksjoner:

- `statistics.antall`: antallsrapportens koder.
- `statistics.resultater`: resultatrapportens koder.
- `statistics.ekstraksjon`: ekstraksjonskoder og separat hente-/arkiv-ID.
- `backlog.report`: rapport, grupper og koder som hentes.
- `backlog.analyses`: klassifisering, navn, kildereferanser og terskler.
- `backlog.columns`: CSV-format og kolonnekartlegging.

JSON bruker doble anførselstegn og komma mellom elementene:

```json
"analysis_codes": ["CALR-OU", "JAK2-V617F-OU"]
```

Ikke sett komma etter siste element. Manglende komma gir filnavn, linje og
kolonne. Duplikate nøkler/koder, ukjente felt og feil typer blir avvist.
CSV-skilletegnet er et eget felt; vanlige LVMS-uttrekk bruker `"delimiter": ";"`.

Rapportkodelisten bestemmer henting; restansens analyseliste bestemmer
klassifisering. Oppdater begge ved relevante endringer. Deaktivering eller
fjerning av analyser sletter ikke historikk. Statistikkprofiler er `hemato`
og `solide`; nye beregningsregler krever fortsatt programkode.

Filene leses før neste kjøring. Samme validerte snapshot brukes gjennom hele
kjøringen. En ugyldig direkte redigering blokkerer neste kjøring. For
tilbakeføring velger du en tidligere gyldig fil og lagrer på nytt.

## Mapper

```text
K-sensitiv rot/
  config/units/<enhet>/<versjon>.json
  config/lookups/<enhet>/<hash>.xlsx
  config/revisions/<oppsett-hash>/
  config/migration/<hash>/originals/
  data/molstat.sqlite3
  data/backups/
  raw/statistics/<enhet>/
  work/fetch/<kjøring>/
  processed/<enhet>/statistics/<kjøring>/
  processed/<enhet>/backlog/<kjøring>/
  Prøvesøk.xlsx
```

Lookup kopieres med hashkontroll ved lagring; originalen beholdes.
Statistikkrådata er permanent arkiv. Restanserådata er en midlertidig arbeidsfil
som fjernes etter importforsøket. Ingen automatisk retensjon/sletting av
backups, konfigurasjonsversjoner eller behandlingskandidater er aktivert.
K-sensitiv og SharePoint skal være separate røtter som ikke ligger inni hverandre.

Ferdige kandidater ligger i `processed`. `delivery.json` registrerer status
og hash. «Prøv publisering igjen» bruker siste ventende kandidat per enhet/jobb
uten nytt uttrekk/import. En eldre feil kan ikke overskrive en nyere vellykket
kandidat. Endrede kandidater avvises og personvernkontroll kjøres igjen.
SharePoint-filnavn og kolonner beholder dagens kontrakter.

## Excel og feilkoder

«Oppdater Excel-søk» regenererer arbeidsboken fra databasen uten LVMS.
Lukk filen i Excel først. Oversikten viser oppdateringstid og mislykket eksport.
Databaseimport og Excel-eksport har separate resultater. Eksakt søk, prefiks
og flere samtidige søk bygger videre på eksisterende arbeidsbok.

| Kode | Handling |
| --- | --- |
| `CONFIG_SYNTAX` | Rett komma, anførselstegn/klammer på oppgitt linje |
| `CONFIG_INVALID` | Rett oppgitt felt |
| `CONFIG_MIGRATION` | Kontroller eldre oppsett; originaler beholdes |
| `CSV_INVALID` | Kontroller format, kolonner og datoer; gammel nåtilstand beholdes |
| `LVMS_TIMEOUT` | Kontroller forbindelse; bare feil før innsending gjentas automatisk |
| `LVMS_LOGIN_REQUIRED` | Kontroller innlogging |
| `DOWNLOAD_INCOMPLETE` | Kontroller rapportstatus før nytt manuelt uttrekk |
| `BROWSER_CLEANUP` | Kontroller nettleseren før ny kjøring |
| `DB_BUSY` | Vent til annen kjøring er ferdig |
| `DB_ACCESS` | Kontroller nettverkssti og database-/journalrettigheter |
| `DB_LOCATION` | Velg roten som inneholder `data` |
| `EXCEL_REFRESH_FAILED` | Lukk arbeidsboken og prøv igjen |

LVMS-feil viser trinn, forsøk og kjørings-ID uten rapportinnhold.
Maskinlokale logger ligger under den lokale MolStat-appmappen.

## Pilot på jobb-PC

1. Behold dagens innstillinger og verifisert databasebackup.
2. Åpne samme rot, lukk og åpne appen igjen; bekreft samme ID-er og historikk.
3. Verifiser UNC/nettverkssti og blokkering av en annen skriver.
4. Bekreft reell LVMS-nedlasting, kolonneheader og WorkItem-identitet.
5. Test låst SharePoint-fil og ny publisering etter opplåsing.
6. Test eksakt/prefiks, flere verdier og ledende nuller i Microsoft 365 Excel.
7. Test restore på en separat kopi; ikke overskriv operativ database i piloten.

Lokal syntetisk verifikasjon erstatter ikke nettverks- og mål-Excel-piloten.
