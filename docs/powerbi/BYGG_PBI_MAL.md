# MolStat Prøveflyt — Power BI-mal (guide)

> Denne mappen (`docs/powerbi/`) inneholder guiden, en syntetisk
> test-CSV og en visuell mockup. Den ferdige `.pbit`-filen bygges i
> PBI Desktop etter denne guiden og lagres lokalt (ikke i repoet).

> **Mål:** En PBI Desktop-fil som leser `restanseoversikt.csv` fra
> `C:\Users\molpa\Documents\MolStat\out\Prøveflyt\` (eller
> SharePoint-mappen "Prøveflyt") og viser en tavle med **én boks per
> analysegruppe**. Klikk på en boks → tabell med prøver for den gruppa.

## 1. Datakilde

MolStat skriver filen `restanseoversikt.csv` med dette skjemaet:

| Kolonne | Type | Beskrivelse |
|---|---|---|
| `Analysegruppe` | Tekst | f.eks. `KLONALITET`, `MYELOID`, `CYTOMETRI` |
| `Dato` | Dato (YYYY-MM-DD) | Bestillingsdato for prøvene i raden |
| `Bestilt` | Heltall | Antall bestilte prøver den dagen |
| `Kommet` | Heltall | Antall prøver med ankommet materiale |
| `Restanse` | Heltall | `Bestilt − Kommet` (de som ikke er kommet) |
| `Eldste_dager` | Heltall (kan være tom) | Alder i dager på eldste ventende prøve i gruppa/datoen |

**Ingen pasient-ID, ingen PID, ingen WorkItem, ingen rå-tekst, ingen
filstier.** Dette er personvern-kontrakten — du kan trygt peke PBI
Desktop direkte på filen i SharePoint.

Test-CSV: `docs/powerbi/sample_restanseoversikt.csv` i dette repoet
(228 rader, 6 grupper, 38 dager) — bruk denne når du bygger. Filen er
fullstendig syntetisk (ingen reelle prøver), men følger samme
kolonnekontrakt og personvernregler som produksjons-CSV-en.

## 2. Åpne PBI Desktop → Get Data → Text/CSV

1. **Home → Get Data → Text/CSV**
2. Velg `<repo>\docs\powerbi\sample_restanseoversikt.csv`
   (f.eks. `C:\Users\molpa\Documents\MolStat\docs\powerbi\sample_restanseoversikt.csv`)
3. I forhåndsvisningen:
   - Delimiter: `Semicolon`
   - Encoding: `65001 (UTF-8)`
   - Trykk **Transform Data** (ikke Load)

## 3. Power Query-transform

I Power Query Editor:

1. **Endre typer** (Transform → Detect Data Type virker ikke med norske
   overskrifter, så gjør manuelt):
   - `Analysegruppe` → Text
   - `Dato` → Date (`YYYY-MM-DD`-formatet parse'er automatisk)
   - `Bestilt`, `Kommet`, `Restanse`, `Eldste_dager` → Whole Number
2. **Marker Dato som dato-tabell** (Table → Mark as date table → velg
   `Dato`).
3. Lukk og bruk (**Close & Apply**).

## 4. DAX-measures

I Model-view (venstre ikon), tabell `Restanseoversikt`, New Measure:

```dax
Bestilt total = SUM ( Restanseoversikt[Bestilt] )
```

```dax
Kommet total = SUM ( Restanseoversikt[Kommet] )
```

```dax
Restanse total = SUM ( Restanseoversikt[Restanse] )
```

```dax
Restanse i dag =
CALCULATE (
    [Restanse total],
    Restanseoversikt[Dato] = TODAY ()
)
```

```dax
Restanse % =
DIVIDE ( [Restanse total], [Bestilt total] )
```

```dax
Eldste ventende dager =
CALCULATE (
    MAX ( Restanseoversikt[Eldste_dager] ),
    FILTER (
        ALL ( Restanseoversikt ),
        Restanseoversikt[Restanse] > 0
    )
)
```

```dax
Aktive analysegrupper i dag =
CALCULATE (
    DISTINCTCOUNT ( Restanseoversikt[Analysegruppe] ),
    Restanseoversikt[Dato] = TODAY (),
    Restanseoversikt[Restanse] > 0
)
```

## 5. Tavle-side (Report view)

Ny side, kall den **Prøveflyt – oversikt**. Sett sidestørrelse til
**16:9 (1366×768)** i Page-view (Format → Page size → Custom:
1280×720 for kompakt visning, eller 1920×1080 for full HD).

### 5.1 Header-boks (topp, 1280 px bred)

Visual: **Multi-row card** eller **Card** med tre målinger side om side:

- `[Restanse total]` (stor font, 36-48pt, rød hvis > 0)
- `[Bestilt total]`
- `[Kommet total]`

Under: tekst "Sist oppdatert: " + `MAX(Restanseoversikt[Dato])`.

Se `tavle_mockup.png` i samme mappe for hvordan tavlen skal se ut.

### 5.2 Analysegruppe-bokser (hovedinnhold)

For hver analysegruppe lager du en **Card**-visual (eller **Multi-row
card** for flere målinger i samme boks):

**Oppsett (3 kolonner × 2 rader, 6 analysegrupper):**

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ CYTOMETRI    │  │ KLONALITET   │  │ SEKV         │
│   12  (3%)   │  │   21  (9%)   │  │   46  (16%)  │
│  3 d eldste  │  │  7 d eldste  │  │  7 d eldste  │
└──────────────┘  └──────────────┘  └──────────────┘
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ MYELOID      │  │ FISH         │  │ PATOLOGI     │
│   55  (18%)  │  │   77  (31%)  │  │  107  (43%)  │
│ 14 d eldste  │  │ 29 d eldste  │  │ 35 d eldste  │
└──────────────┘  └──────────────┘  └──────────────┘
```
(Tall fra test-CSV-en — fargen følger `[Restanse %]`.)

**Per boks (CYTOMETRI som eksempel):**

1. Visual: **Card** (eller Multi-row card med `[Restanse total]`
   og `[Eldste ventende dager]`)
2. Filter (Filters-pane → Visual level filters): `Analysegruppe = CYTOMETRI`
3. Fields: `[Restanse total]`
4. Format → Conditional formatting → **Background color** på callout:
   farger etter `[Restanse %]`-regelen under
5. Under tittel: `"Eldste: " & [Eldste ventende dager] & " dager"`

**Farge­regler (samme som mockup):**

| Restanse % | Farge | Merke |
|---|---|---|
| < 10 % | Grønn `#1B7D3A` | OK flyt |
| 10–25 % | Gul `#B8821A` | Merk restanse |
| > 25 % | Rød `#A4262C` | Kritisk restanse |

I PBI Desktop: Conditional formatting → Background color → farger etter
felt, regler: hvis `[Restanse %]` er større enn 0,25 → `#A4262C`;
ellers større enn 0,10 → `#B8821A`; ellers `#1B7D3A`.

**Gjenta for hver gruppe** (eller bruk en **Decomposition tree**-visual
for automatisk oppdeling — raskere, men mindre visuell kontroll).

### 5.3 Klikk-for-tabell (drill-through)

Høyreklikk på en analysegruppe-boks → **Drill through** → opprett en
detaljside:

**Side 2: "Detaljer – <gruppe>"**

- Visual: **Table**
- Fields: `Dato`, `Bestilt`, `Kommet`, `Restanse`, `Eldste_dager`
- Filter: `Analysegruppe` = samme som boksen (via drill-through-filter)
- Sorter: `Dato DESC`

I boksen på side 1: **Drill through → Enable** for denne siden. Nå
dobbelklikker brukeren på en boks → hopp til detaljtabell.

### 5.4 Fargepalett (CY26SU05-basert)

| Bruk | Farge | Hex |
|---|---|---|
| Bakgrunn | Lys grå | `#F2F2F2` |
| Primærtekst | Mørk grå | `#252423` |
| Restanse % < 10 (grønn — OK flyt) | – | `#1B7D3A` |
| Restanse % 10–25 (gul — merk restanse) | – | `#B8821A` |
| Restanse % > 25 (rød — kritisk restanse) | – | `#A4262C` |
| Kort bakgrunn | Hvit | `#FFFFFF` |

(Dette matcher CY26SU05-base-temaet i din nåværende PBI-mal.)

## 6. Lagre som .pbit

Når tavla ser riktig ut:

1. **File → Save As**
2. Filnavn: `MolStat_Proeveflyt.pbit`
3. Filtype: **Power BI template (*.pbit)**
4. Lagre lokalt, f.eks. `C:\Users\molpa\Downloads\MolStat_PBIX\`

Fremtidige brukere dobbelklikker .pbit → PBI Desktop ber om
datakildestien → velg CSV-en fra SharePoint.

## 7. Publiser til SharePoint (valgfritt)

Hvis du vil at tavla skal oppdateres automatisk:

1. **File → Publish → Publish to Power BI Service**
2. Logg på din organisasjons Power BI-tenant
3. Velg workspace, f.eks. "Molekylærpatologi"
4. Sett opp **Scheduled refresh** (daglig kl. 06:30 — etter MolStat
   backlog-jobb som kjører 06:00–18:00).

## 8. Vedlikehold

- Når MolStat legger til nye analysegrupper: oppdater Card-filtrene
  (eller bytt til Decomposition tree).
- Når kolonnekontrakten endres: oppdater Power Query-stegene og
  oppdater measures.

---

**Filstier å notere seg:**

| Hva | Hvor |
|---|---|
| Test-CSV (syntetisk) | `docs/powerbi/sample_restanseoversikt.csv` (i repoet) |
| Mockup (HTML/PNG) | `docs/powerbi/tavle_mockup.html` / `tavle_mockup.png` (i repoet) |
| Ferdig .pbit (din output) | Lokal fil — lagres utenfor repoet, f.eks. `C:\Users\molpa\Downloads\MolStat_PBIX\MolStat_Proeveflyt.pbit` |

Referansefiler som ikke ligger i repoet (lokalt på jobb-PC):

- Rå LVMS-restanse (input): `C:\Users\molpa\Downloads\LVMS-STAT_restanse\Statistikk\[TEST]\PAT-DIT RESTANSE-OU.csv`
- Eksisterende PBI-mal (statistikk): `C:\Users\molpa\Downloads\LVMS-STAT_restanse\Statistikk\[TEST]\Power BI\Statistikk_Hemato.pbit`
