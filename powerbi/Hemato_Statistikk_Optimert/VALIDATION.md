# Valideringsnotat

Kontrollene ble gjort 10. september 2026 mot den åpne originalmodellen på Power BI Desktops lokale Analysis Services-instans. Kilde-PBIX-en ble bare lest.

## Baseline fra rå tidsstempler

| Kontroll | Resultat |
|---|---:|
| Resultatrader | 49 949 |
| Volumrader | 50 788 |
| Pasientforløp, median | ca. 12,03 dager |
| Pasientforløp, P90 | ca. 34,13 dager |
| Seksjonstid, median | ca. 8,17 dager |
| Seksjonstid, P90 | ca. 21,12 dager |
| Enhetstid, median | ca. 5,83 dager |
| Enhetstid, P90 | ca. 19,95 dager |
| Pasientintervaller som er negative eller over 365 dager | 154 |
| Negative intervaller bestilling → resultat | 121 |
| Median ukevolum siste 52 uker | ca. 379,5 |
| Observerte lave ferie-/helligdagsuker | ca. 182–190 |

Tallene er kontrollreferanser, ikke hardkodede mål. De skal variere med oppdaterte kildedata og filterkontekst.

## Teknisk verifikasjon

- PBIR-validering: gyldig, ingen feil, 5 sider og 86 visualer.
- Alle sider er 1280 × 720.
- Testpakke: 7 tester bestått.
- TMDL ble konvertert til rå modell og kompilert til PBIT med `pbi-tools.core`.
- Modellen ble importert i en tom lokal Power BI-instans: 5 tabeller, 51 kolonner, 26 mål og 7 relasjoner.
- Full testoppdatering i den tomme instansen stoppet ved manglende SharePoint-legitimasjon; derfor skal sluttbruker kjøre oppdatering i sin vanlige, autentiserte Desktop-kontekst.

## Kontroll ved hver publisering

Kjør DAX-filene i `validation` mot oppdatert modell og kontroller:

1. Radantall og datoperiode er plausible.
2. Negativ/manglende/ekstrem varighet er blank og inngår i ekskluderingsmål.
3. Median og P90 fra målene matcher beregning direkte fra rå tidsstempler innen avrunding.
4. År, måned, ISO-uke, rapportgruppe og analyse filtrerer både kort og relevante detaljer konsistent.
5. Summen innen frist + over frist matcher nevneren for rader som både har gyldig svartid og svarfrist.
6. `Entydig svarfrist dager` er blank når flere frister er valgt.
