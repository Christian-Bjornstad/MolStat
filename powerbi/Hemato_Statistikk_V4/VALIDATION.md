# Valideringsnotat for V4

Kontrollert 12. september 2026 mot lagret og gjenåpnet `Hemato_Statistikk_V4.pbix` i Power BI Desktop.

## Teknisk kontroll

- PBIR fullvalidering: 0 feil og 0 advarsler.
- V4-regresjonstester: 8 bestått.
- Modell: 5 tabeller, 64 kolonner, 40 mål og 7 relasjoner.
- PBIX inneholder cachet `DataModel` og alle åtte rapportsider.
- Ingen egendefinert temareferanse som kan blokkere Desktop-innlasting.

## Perspektivkontroll

| Perspektiv | Gyldige | Median dager | Innen frist | Over frist |
|---|---:|---:|---:|---:|
| Pasientforløp | 49 795 | 12,03 | 51,35 % | 24 224 |
| Seksjonstid | 49 826 | 8,17 | 70,60 % | 14 651 |
| Enhetstid | 48 099 | 5,83 | 79,95 % | 9 644 |

## Visuell kontroll

- Oversikt åpner med fem tydelige filtre og fire sentrale KPI-er.
- Antall per analyse viser sorterte stolper og synlige verdier.
- Svartid per analyse viser perspektivstyrt median, statusfarge og stiplet entydig frist.
- P90 forekommer ikke på hovedsidene.
- Datakvalitet er samlet som støttestoff på `Om rapporten`.
