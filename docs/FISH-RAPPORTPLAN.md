# FISH – plan for senere Power BI-rapport

Avklart 20. oktober 2026: Rapporten skal følge samme hovedoppsett og uttrykk som Solide, Hemato og Flow, tilpasset FISH-data. Dette er en plan; ingen Power BI-rapport er opprettet eller endret. Eksisterende rapportprosjekter finnes ikke i dette repoet, så nøyaktig layout og gjenbruk av mål avklares ved senere gjennomgang av dem.

## Rapportinnhold

Første versjon har to sider og ingen egen datakvalitetsside, feillister eller tekniske kontrollvisualer.

| Side | Innhold |
| --- | --- |
| Aktivitet | Antall bestilte analyser, resultatrader, månedsutvikling, sammenligning med samme periode året før og fordeling på analyse/rapportgruppe. |
| Svartid | Median og P90 for bestilling til analyseresultat, bestilling til godkjenning og eventuelt resultat til godkjenning. Trend per måned og analysetabell med antall observasjoner og svartider. |

Bruk samme farger, navigasjon, filterplassering og KPI-uttrykk som de eksisterende rapportene. Aktuelle filtre er år, måned, analysekode og rapportgruppe. Materiale filtrerer resultat-/svartidsvisualer; bestillingsfilen har ikke materiale. Vis antall sammen med svartid slik at analyser med lite datagrunnlag kan vurderes riktig. Sammenlign et ufullstendig år med tilsvarende periode året før.

Ingen restansemåling beregnes som bestillinger minus resultatrader. Unike prøver/pasienter, positivandel og kliniske resultater inngår ikke med dagens eksport. Pris-/inntektsmål og andel innen svarfrist tas bare med dersom egne, avklarte oppslag og beregningsregler foreligger.

## Datamodell og mål

- SharePoint `fish/antall.csv`: én eksportert bestillingsrad som grunnlag for bestillingsvolum etter bestillingsdato.
- SharePoint `fish/resultater.csv`: resultatrader og tidsintervaller. Resultatvolum vises etter resultatdato, godkjenninger etter godkjenningsdato.
- Felles analyseoppslag med avklarte visningsnavn og rapportgrupper. Ingen direkte kobling mellom faktatabellene etter bare analysekode eller dato.
- Kalender med tydelige datoroller for bestilling, resultat og godkjenning. Svartidstrend bruker en konsekvent angitt sluttdato for hvert intervall.
- Dagens `Svartid dager` betyr bestilling til analyseresultat, i kalenderdøgn. Bestilling til godkjenning beregnes separat. Manglende og negative intervaller bidrar ikke med null til tidsmålene; antall i grunnlaget vises.
- `Rapportgruppe`, `Svarfrist`, `MolStat-ID`, `Pris2026NOK` og `Priskobling` er tomme i det undersøkte uttrekket. Rapportgruppe, priser og svarfrister må komme fra egne oppslag i Power BI; MolStat-ID gir foreløpig ingen prøvekobling.

## Forutsetninger før bygging

FISH-resultatfilen i data.zip har 13 poster splittet over flere CSV-rader. Dagens import fyller ut de korte radene og behandler fortsettelsesrader som egne poster. Dette må løses og kontrolleres i databehandlingen før rapporttallene ferdigstilles; kontrollen skal foregå i bakgrunnen og trenger ingen egen rapportside. Denne endringen i patologpublisering retter ikke FISH-importen.

Undersøkt behandlet eksport har 2 376 bestillingsrader, 2 361 resultatrader og 51 analysekoder med data. Dette er kontrollreferanser for uttrekket, ikke permanente forventede totaler eller ferdig validerte produksjonstall. Det foreløpige svartidsgrunnlaget gir median 4,07 kalenderdøgn til resultat og 5,55 til godkjenning, med ulike gyldige grunnlag.

Ved senere bygging: sammenlign layouten med de eksisterende rapportene, rett og verifiser FISH-importen, avklar analyseoppslag og svartidsdefinisjoner, og bygg deretter de to sidene. Kontroller tellinger, datoroller og filtre uten å legge til en datakvalitetsside.
