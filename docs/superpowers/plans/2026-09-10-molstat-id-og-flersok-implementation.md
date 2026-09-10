# Implementeringsplan: kort ID, flersøk og eksportkobling

1. Skriv røde registertester for sekvensielle, permanente korte ID-er.
2. Implementer transaksjonssikker ID-tildeling uten egen gjenbrukssekvens.
3. Skriv røde tester for MolStat-ID i statistikk- og restanse-detaljeksport,
   og for fravær i `antall.csv`.
4. Importer statistikk til registeret før prosessering, bygg en begrenset
   prøvenummer→ID-oppslagstabell og legg ID til resultatene.
5. Utvid restansesnapshot og databaseversjon med MolStat-ID, og oppdater
   allowlists, eksempeldata og Power BI-kontrakter.
6. Skriv røde Excel-tester for flersøk og fravær av WorkItem/
   Identitetsstatus, og implementer formler/layout.
7. Kjør målrettede tester, hele testsuiten, bygg pakke, generer og valider en
   eksempelarbeidsbok visuelt.
8. Gjennomgå diff, commit og push til GitHub.
