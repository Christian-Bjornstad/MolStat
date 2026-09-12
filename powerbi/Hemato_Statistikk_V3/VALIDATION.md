# Valideringsnotat for V3

Sluttkontrollen ble kjørt 11. september 2026 mot en lagret og gjenåpnet V3-PBIX i Power BI Desktop August 2026. Originalfilen ble bare brukt som lesereferanse.

## Kontrolltall fra cachet modell

| Kontroll | Resultat |
|---|---:|
| Resultatrader | 49 949 |
| Volumrader | 50 788 |
| Pasientforløp, median / P90 | 12,03 / 34,13 dager |
| Seksjonstid, median / P90 | 8,17 / 21,12 dager |
| Enhetstid, median / P90 | 5,83 / 19,95 dager |
| Enhetstid, gyldige observasjoner | 48 099 |
| Innen individuell frist | 38 455 (79,95 %) |
| Fireukers nivå ved siste dato med data | 395,25 analyser/uke |
| Datakvalitetsavvik | 2 016 |
| Materiale PAK | 5 439 rader |

## Teknisk verifikasjon

- PBIR: gyldig, 199 filer kontrollert, åtte sider.
- Semantisk modell: 5 tabeller, 64 kolonner, 40 mål og 7 relasjoner.
- Den cachede datotabellen viser 2024, 2025 og 2026.
- År-dropdown ble åpnet i Desktop og viste disse tre årene.
- Materiale-dropdown ble åpnet i Desktop og viste blant annet PAK.
- Alle åtte sider ble åpnet og visuelt kontrollert.
- Uke- og månedsakser er kontinuerlige og viste ingen horisontal scrollbar.
- Tidslinjen viser syv kolonner i full bredde uten horisontal scrollbar.
- PBIX-en ble pakket uten den ustabile egendefinerte temareferansen; OUS-fargene er fortsatt definert direkte på visualene.
- DAX-kontroll bekreftet radantall, tre svartidsperspektiver, fristandel, datakvalitet og fireukersnivå etter gjenåpning.

Full SharePoint-refresh er ikke kjørt lokalt fordi denne maskinen ikke har jobbinnlogging. Den skal kjøres og tallene avstemmes på jobb-PC før publisering.
