# Oppgaver: Hemato Statistikk 2.0

## 1. Modell og kontrakt

- [x] Automatiske tester dekker dato, tre svartidsperspektiver, godkjenningsetterslep, ugyldige intervaller, individuell frist og nevner.
- [x] Modellmål valideres mot cachede data med DAX.

## 2. Rapportdesign

- [x] Ledelsesoversikt, Volum og kapasitet, Svartid, Oppfølging og Datakvalitet følger samme layoutsystem.
- [x] OUS-inspirert tema, 8-punkts rytme, tilgjengelig kontrast og tekstlig status er på plass.
- [x] Definisjoner, filterdato og datakvalitet er synlig uten hover.

## 3. Analyseflyt

- [x] Uke-/månedstrend, fireukers nivå og historisk lave uker er implementert.
- [x] Perspektivvelger, median, P75/P90, fristoppnåelse og rangering er implementert.
- [x] Oppfølgingstabell og diagnostikk inneholder avtalte felt.
- [x] Rapporttooltips og sidenavigasjon er dokumentert og validert.
- [ ] Drillthrough-binding vurderes etter test med oppdaterte data på jobb-PC.

## 4. Distribusjonsfil

- [x] Ny rapportflate er koblet til `powerbi/Hemato_Statistikk_2_0.pbix` med innebygde data.
- [x] SharePoint-partisjonene er bevart for oppdatering på jobb-PC.

## 5. Sluttkontroll

- [x] PBIR og alle automatiske tester består.
- [x] Alle fem sider er visuelt kontrollert i Desktop.
- [x] PBIX er lukket og gjenåpnet med data.
- [x] Original PBIX er urørt.
- [ ] Full SharePoint-oppdatering og publisering testes på jobb-PC.
