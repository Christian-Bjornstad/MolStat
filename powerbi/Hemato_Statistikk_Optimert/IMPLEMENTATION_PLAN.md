# Implementeringsplan: Hemato Statistikk 2.0

## Mål

Levere en produksjonsklar, versjonert femsiders Power BI-rapport som kombinerer den nye PBIR-rapportflaten med den validerte semantiske modellen og de innebygde dataene fra arbeidskopien. Originalfilen i Downloads skal ikke endres.

## Arkitekturbeslutninger

- PBIP/PBIR er kildekoden for modell, rapport og tema; PBIX er den testbare distribusjonsfilen med innebygd datacache.
- Én kontrollert `Dato`-tabell brukes. Aktiv dato er analyseresultat for svartid/resultater og analysebestilling for volum; alternative hendelsesdatoer er eksplisitte, inaktive relasjoner.
- Svartid beregnes radvis og ugyldige intervaller returnerer `BLANK()`. Fristoppnåelse bruker individuell svarfrist.
- Rapporten bruker fem faste 1280 × 720-sider, konsistent navigasjon og et OUS-inspirert, tilgjengelig lyst tema.
- Midlertidige lokale datauttrekk kan bare brukes til å få rapporten åpnet og testet lokalt. De skal ikke committes eller erstatte SharePoint-spørringene i leveransen.

## Faser

1. Revider modellkontrakten og rapportkravene med automatiske tester.
2. Fullfør modellmål, dato-/fristsemantikk, datakvalitet og tooltipgrunnlag.
3. Fullfør fem rapportsider, tema, synlige definisjoner, navigasjon og detaljflyt.
4. Bygg en PBIX-distribusjonskopi med innebygde data uten å endre originalen.
5. Verifiser PBIR, DAX, alle sider i Desktop, lukking/gjenåpning og dokumentasjon.

## Risiko og tiltak

| Risiko | Tiltak |
|---|---|
| SharePoint kan ikke autentiseres her | Behold eksisterende cache og SharePoint-partisjoner; sluttoppdatering testes på jobb-PC |
| PBIR kan ikke pakkes direkte inn i PBIX | Bruk støttet Desktop-flyt og visuell gjenåpning; aldri rediger PBIX-arkivet direkte |
| Gamle visualer forventer eldre feltnavn | Behold bakoverkompatible aliaser i modellen |
| Ulike svarfrister gir misvisende referanselinje | Vis linje bare via `SELECTEDVALUE`; ellers individuell fristoppnåelse og avvik |
| Kritisk informasjon skjules i hover | Vis status, nevner og kvalitetsavvik i kort/tekst; tooltips er supplement |

## Ferdigkriterier

- PBIP-validering uten feil og full Power BI-testpakke grønn.
- Alle fem sider åpner og viser data i Power BI Desktop.
- PBIX kan lukkes og åpnes på nytt uten reparasjonsvarsel eller feltfeil.
- Originalfilens hash og endringstid er uendret.
- SharePoint-kilder og nødvendig jobb-PC-test er tydelig dokumentert.
