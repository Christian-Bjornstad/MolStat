# Implementeringsplan: Hemato Statistikk V3

## Arkitekturvalg

- Kopier V2-kilden og bygg V3 i egen PBIP/PBIX.
- Behold semantisk modell, men utvid datotabellen med `MånedStart` og mål som støtter kompakte visualer.
- Bruk separate sider fremfor scrollbare kombinasjonsvisualer.
- Bruk `Materiale` direkte fra `resultater`; ikke late som volumtabellen `antall` har samme felt.

## Faser

1. Etabler V3-kontrakt og regresjonstester.
2. Bygg datofilter, materialfilter og kontinuerlige tidsakser.
3. Bygg åtte kompakte sider uten overflødig tekst.
4. Pakk PBIX med cachet modell, åpne og kontroller alle sider.
5. Lagre, gjenåpne, kjør DAX/PBIR/testvalidering og dokumenter.

## Risikoer

- Power BI kan generere scrollbar for kategoriske akser. Mottiltak: ekte datoakse og `axisType = Scalar`.
- Materiale finnes ikke i `antall`. Mottiltak: materialfilter kun på resultatsider og tydelig datokilde på volum.
- 65 analyser får ikke plass samtidig. Mottiltak: dedikert helside, søkbart analysefilter og stor rangeringsflate.
