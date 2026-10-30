# Behandling og Excel-søk – 29. oktober 2026

Målet er at daglig Hemato-behandling, inkludert Excel-søk, skal ta høyst tre minutter på jobb-PC-en. Nedenstående målinger bruker syntetiske data på utviklingsmaskinen og bekrefter en vesentlig reduksjon i CPU-arbeid. De dokumenterer ikke faktisk varighet på jobb-PC, LVMS, nettverksdisk eller SharePoint.

## Hva som tok tid

- Statistikkprosessoren flettet hele råhistorikken og importerte hele det flettede datasettet til registeret ved hvert uttrekk. En tredagers nedlasting førte derfor til at også flere års gamle registerobservasjoner ble skrevet på nytt.
- CSV-leseren gjennomgikk hvert tegn i Python selv når en linje ikke inneholdt CSV-sitater. Dette ble gjentatt ved fletting, registerimport og behandling.
- Datoer ble prøvd mot flere `strptime`-formater per celle. Det vanligste, nullutfylte LVMS-formatet kan valideres direkte av `datetime.fromisoformat`, med samme gamle fallback for andre støttede formater.
- Excel-eksporten gjentok de samme søkeuttrykkene i hver prøveformel. XlsxWriter brukte mye tid på å normalisere disse formlene. Eksplisitte funksjonsprefikser og LET lar eksporten normalisere søkeinnholdet én gang per formel. Arbeidsboken bruker fortsatt dynamiske formler for Excel 2021/365.
- En samlet kjøring bygget hele Excel-søket etter hver statistikk- og restansekapabilitet. Det kunne bety åtte komplette arbeidsbøker ved kjøring av alle seks enheter.

## Endringer og databevaring

Registerimporten lagrer nå et versjonert sett med arkivfilenes navn og innholdsfingeravtrykk i importens eksisterende `source_fingerprint`. Neste kjøring importerer bare nye eller endrede arkiver, også mellomliggende månedsuttrekk og rettelser av eldre perioder. Import og kontrollpunkt bekreftes i samme transaksjon. Feil ruller begge tilbake. Ugyldig, gammel eller manglende kontrollpunktinformasjon utløser full registerinnhenting.

**Første kjøring etter oppgradering kan fortsatt gjøre én full registerinnhenting.** Dette bevarer gamle identiteter og gjør at en ny eller gjenopprettet database får med hele arkivet. Påfølgende daglige kjøringer bruker endringene. Filnavn alene brukes ikke som bevis på uendret innhold.

Power BI-filene bygges fremdeles fra komplett arkivhistorikk. Excel-søket inneholder fremdeles hele registeret og alle analyser. Ingen perioder, kolonner eller valideringer er fjernet for å få bedre tid. Uendrede, gamle råarkiver får ikke kunstig ny registerobservasjon ved hver kjøring.

En samlet kjøring av aktive enheter, én enhet med både statistikk og restanse, eller flere enheters statistikk/restanse, bygger Excel én gang etter siste deljobb. Ferdige importer fra en delvis mislykket kjøring blir med. En enkelt kapabilitet eller manuell import oppdaterer fortsatt Excel direkte. Avbrudd og mistet skrivelås starter ikke et nytt, langt Excel-steg. Låste Excel-filer bruker eksisterende kandidater, validering og gjenforsøk.

## Før/etter-målinger

| Måling | Før | Etter | Resultat |
|---|---:|---:|---|
| Profilert Hemato: 10 000 historiske + 90 nye prøver, alle tre rapporter | 28,765 s | 4,319 s | 6,66 ganger raskere; 85 % kortere tid |
| Registerrader importert ved samme daglige kjøring | 30 270 | 270 | Historiske rader skrives ikke på nytt |
| Excel-generering: 10 000 prøver / 30 000 analyser, median av tre vekslende kjøringer | 8,913 s | 3,819 s | 57 % kortere generering |
| Excel lesing + generering + validering: 50 000 prøver / 150 000 analyser, én kjøring per versjon | 49,276 s | 23,124 s | 53 % kortere tid |
| Fire gamle Excel-oppdateringer mot én ny: 10 000 prøver / 30 000 analyser, én samlet måling | 40,697 s | 5,386 s | Omtrent 87 % kortere Excel-arbeid for denne kjøringen |
| CSV-lesing: 50 000 vanlige rader, median av tre kjøringer | 5,786 s | 0,452 s | 12,79 ganger raskere |
| CSV-lesing: 50 000 siterte/flerlinjerader, median av tre kjøringer | 5,732 s | 0,749 s | 7,65 ganger raskere |

Den profilerte Hemato-sammenligningen ga identiske SHA256-fingeravtrykk for begge historiske CSV-utdata. Antall prøver, analyseforekomster, hendelser og kildeobservasjoner var identisk. CSV-normalisering kontrolleres mot den gamle implementasjonen over genererte sitat-/felt-/linjeskifttilfeller, og Excel-søkeuttrykkene kontrolleres mot samme eksakt-/prefiksregler som før.

Native Excel-rekalkulering og arbeidsplassens lagring er ikke målt. Store historiske arkiver må fortsatt leses for komplette rapporter, og hele Excel-arbeidsboken må fortsatt skrives. Derfor øker tiden fortsatt med total historikk, selv når LVMS-uttrekket bare dekker tre dager.

## Gjenta målingene med syntetiske data

Fra programmappen:

```powershell
python tests/statistics/profile_incremental.py --history 10000 --daily 90
python tests/statistics/profile_incremental.py --history 10000 --daily 90 --no-profile
python tests/excel_search/benchmark_refresh.py --samples 10000 --repeats 3
python tests/excel_search/benchmark_refresh.py --samples 50000 --repeats 1
python -c "import sys,runpy;sys.path.insert(0,'src');runpy.run_path('tests/statistics/test_lvms_csv_performance.py',run_name='__main__')"
```

CSV-kommandoen legger `src` på Python-stien. Statistikk- og Excel-benchmarkene setter kildekodestien selv og rydder sine midlertidige syntetiske filer. `--keep-output` på statistikkmålingen beholder data for inspeksjon.

Se [XlsxWriter sine formelregler](https://xlsxwriter.readthedocs.io/working_with_formulas.html) for eksplisitte prefikser og dynamiske formler, og [Python sin datoparsing](https://docs.python.org/3/library/datetime.html#datetime.datetime.fromisoformat).
