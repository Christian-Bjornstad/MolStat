# Patologuttak i MolStat

Patologer har tre LVMS-rapporter under `PRODSTAT` / `PATOLOGI`:

| Rapport i LVMS | Parameter | Bruk i MolStat |
| --- | --- | --- |
| `PAT-ANTALL REGISTRERTE PRØVER PROSESS-OU` | Rapportens egne datofelt | Aggregert `prosess.csv` |
| `PAT-EGEN PRODUKSJON` | `Brukernavn`, `Fra dato`, `Til dato` | `FactPatologRolle.csv` |
| `PAT-EGEN MAKRO` | `Makro utført av`, `Fra dato`, `Til dato` | `FactMakro.csv` |

I Innstillinger → Patologer velges et CSV-legeregister med `Brukernavn,Navn,Faggruppe`.
Kodene valideres, gjøres om til store bokstaver og sendes til begge legeuttakene
som én kommaseparert verdi uten mellomrom. Den valgte filen kopieres versjonert
til K-sensitiv `config/lookups/lege/`. Uten legeregister kjøres fortsatt bare
prosessrapporten.

Første kjøring henter hver historiske måned separat fra januar 2024. Hver
fullførte måned arkiveres med en gang, slik at en avbrutt kjøring fortsetter ved
første manglende hele måned. Hver videre kjøring henter inneværende måned til
dagens dato og hele forrige måned for alle tre rapportene. Forrige måned
erstatter et eventuelt delvis uttrekk av samme måned i de behandlede tallene.

`prosess.csv` publiseres i den konfigurerte SharePoint-mappen `lege`.
Prøvenivåfilene for Power BI lagres **bare** på K-sensitivt område under
`processed/lege/powerbi/FactPatologRolle.csv` og
`processed/lege/powerbi/FactMakro.csv`. De inneholder prøvenummer og må ikke
flyttes til den vanlige SharePoint-mappen. Den eksisterende PBIX-en må peke
mot disse to filene på jobb-PC-en; legedimensjonen i PBIX-en har de korrigerte
navnene.

MolStat validerer CSV-kolonnene før et månedsuttak arkiveres. Testene dekker
månedlig gjenopptak, skjemafeltene i LVMS, privat lagring og behandling av
produksjons-/makrofilene. Lokal sammenligning mot `lege.zip` ga identiske
rader i begge faktafilene som den tidligere Patolog-Power BI-modellen.
