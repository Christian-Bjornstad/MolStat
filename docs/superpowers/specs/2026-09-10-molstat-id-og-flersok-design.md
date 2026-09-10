# Kort MolStat-ID, flersøk og sporbare detaljeksporter

## Godkjent retning

- Ny database starter ID-serien på `M-000001`.
- ID-en er permanent og gjenbrukes aldri. Nummerfeltet vokser utover seks
  sifre ved behov.
- Teknisk forekomstidentitet (`WorkItem`/fallback) beholdes i databasen, men
  vises ikke i Prøvesøk.
- `Prøvesøk.xlsx` forblir en makrofri, skrivebeskyttet lesekopi. Brukeren kan
  lime inn flere prøvenumre eller MolStat-ID-er, ett søk per rad.
- `MolStat-ID` legges til i detaljfilene `resultater.csv` og
  `restansehistorikk_hemato.csv`. `antall.csv` forblir aggregert uten ID.

## Kapabilitetskart og rekkefølge

1. **Kort, stabil ID**
   - Databasen tildeler monoton `M-NNNNNN` ved første observasjon.
   - Gjentatte rapporter og analyser for samme prøvenummer gjenbruker ID-en.
2. **Sporbar statistikkeksport**
   - Registerimport skjer før resultatfilen bygges.
   - Resultatrader kobles til ID med normalisert LVMS-prøvenummer.
   - Manglende kobling skal gi tom ID i lavnivåprosessoren, men appflyten med
     database skal alltid kunne koble registrerte prøver.
3. **Sporbar restansehistorikk**
   - Detaljsnapshot lagrer MolStat-ID, ikke rått prøvenummer eller WorkItem.
   - Eksportens eksplisitte allowlist utvides bare med `MolStat-ID`.
4. **Excel-flersøk**
   - Søkeområdet har flere gule inndatarader.
   - Resultatlisten viser unike prøver som matcher minst ett søk.
   - Detaljlisten viser alle analyser for alle MolStat-ID-er i trefflisten.
   - `WorkItem` og `Identitetsstatus` fjernes fra synlige ark og formler.

## Kontrakter og personvern

`MolStat-ID` er en pseudonym, stabil koblingsnøkkel. Når den publiseres blir
detaljfilene koblingsbare over tid og skal behandles deretter i godkjent
SharePoint/Power BI-område. Rått prøvenummer, PID, WorkItem, filsti og
fingeravtrykk er fortsatt forbudt utenfor K-sensitiv.

Eksisterende kolonner beholdes uendret. `MolStat-ID` legges sist i
detaljfilene for å redusere risikoen for å bryte posisjonsbaserte importer.
