# Capability Map: MolStat prøveregister og Excel-søk

**Status:** Godkjent 2026-09-10

| Modul-id | Ansvar | Avhenger av |
|---|---|---|
| `sample-registry` | Stabil MolStat-nøkkel, prøvenummer, analyseforekomster og søkeindekser i SQLite | — |
| `restanse-current` | Hente RESTANSE fra 01.01.2024 til dagens dato og oppdatere komplett nåtilstand uten råfilhistorikk | `sample-registry` |
| `statistics-linking` | Koble ANTALL, RESULTATER og ekstraksjonsdata til de samme prøvene og analyseforekomstene | `sample-registry` |
| `data-safety` | Migrering, transaksjoner, skrivelås, integritetskontroll og gjenopprettbare sikkerhetskopier | `sample-registry`, `restanse-current`, `statistics-linking` |
| `excel-search` | Generere en makrofri, skrivebeskyttet `Prøvesøk.xlsx` på K-sensitiv | `sample-registry`, `restanse-current`, `statistics-linking`, `data-safety` |

Byggerekkefølge:

```text
sample-registry
    ├─ restanse-current
    ├─ statistics-linking
    └─ data-safety
             └─ excel-search
```

Grensesnittene mellom modulene beskrives i leverandørmodulens spesifikasjon.
Delspesifikasjonene ble godkjent 2026-09-10.
