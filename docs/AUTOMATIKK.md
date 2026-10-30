# Daglig oppdatering i MolStat

MolStat kjører statistikk og restanse for alle lagrede, aktiverte enheter når valgt klokkeslett nås mens programmet er åpent, uavhengig av tidligere kjøringer samme dag. Standard er 07:00. Timer og minutter velges i Innstillinger → Automatikk → Daglig kl., og tas i bruk med Valider og lagre. PC-ens klokke og tidssone brukes; jobb-PC-en skal stå på norsk tid, inkludert automatisk sommer-/vintertid.

- Tidskontroll skjer ved oppstart og hvert 30. sekund. En forsinket kontroll tar igjen dagens kjøring etter valgt tidspunkt, også etter hvilemodus.
- Klokkeslettet lagres som HH:mm i schedules.daily_time. Eldre innstillinger uten feltet bruker 07:00. Tidspunktet følger med ved eksport/import og tas i bruk uten omstart. Ulagrede endringer påvirker ikke planen. Et nytt tidspunkt utløser ny kjøring selv om et tidligere tidspunkt allerede er kjørt samme dag.
- Hvert planlagte tidspunkt identifiseres som scheduled:ÅÅÅÅ-MM-DDTHH:mm i eksisterende kjøringshistorikk. Det hindrer at samme tidspunkt starter om igjen hvert 30. sekund, etter omstart eller ved overgang til vintertid. Tidligere forsøk med andre klokkeslett, og den eldre generelle scheduled-historikken, blokkerer ikke et nytt tidspunkt. Ingen skjemaendring kreves.
- Pågående manuelle jobber får fullføre først. Databasens eksisterende skrivelås hindrer samtidige oppdateringer på flere PC-er.
- Fullførte automatiske forsøk lagres i eksisterende kjøringshistorikk, også ved feil eller avbrudd. Etter feil kan et nytt tidspunkt velges samme dag, eller manuell kjøring brukes. Et krasjet, uavsluttet forsøk kan gjenopptas ved en ny oppstart når skrivelåsen er frigitt.
- Samme behandling, publisering og Excel-generering brukes som ved «Kjør aktive enheter». Feil og fremdrift vises i Oversikt og Diagnostikk.
- Ingen ny exe, Windows-oppgave, bakgrunnstjeneste eller administratorrettighet kreves for tidsstyringen. Programmet må være åpent, PC-en våken og LVMS/datarot/SharePoint tilgjengelige ved valgt tidspunkt.
- Gamle tidsplanfelt beholdes bare for å kunne lese tidligere innstillingsfiler; de styrer ikke den nye kjøringen. Windows-oppgaver opprettes ikke lenger.
- Gjenkjennelige, gamle MolStat-startere i brukerens lokale MolStat-mappe fjernes ved GUI-oppstart uten å starte Windows-programmer. Eventuelle gjenværende oppgaveoppføringer kan slettes i Oppgaveplanlegging. Nektet opprydding vises i Diagnostikk.

Verifisering: før/ved/etter valgt klokkeslett, minuttpresisjon, lagring/omstart/eksport/import, endret tid etter dagens forsøk, neste dag, sommer/vintertid, to prosesser mot samme database, opptatt skrivelås, feil, avbrudd og Qt-timerens tilkobling til faktisk samlet kjøring.

Qt kan levere forsinkede timerhendelser. Derfor sammenlignes klokkeslett og lagret kjøringshistorikk ved hver kontroll, i stedet for å være avhengig av én hendelse nøyaktig kl. 07:00. Se [Qt-dokumentasjonen for QTimer](https://doc.qt.io/qt-6/qtimer.html#accuracy-and-timer-resolution).
