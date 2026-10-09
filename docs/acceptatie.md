# Acceptatie en resterend werk

Dit is een implementatie van de eerste releasekandidaat. Er is nog geen stabiele release. De Ubuntu/Docker-integratieproef is geslaagd. De installer weigert de onvolledige kandidaat terecht; er worden geen image-digests verzonnen.

## Lokaal gecontroleerd

- Python-tests voor update-/back-up-/hersteltransacties: behoud van stamboom, scans, dossiers, gesprekken, aanvullende modules, hostcode, schema en geheimen.
- Foutinjecties: volle schijf, downloadfout, onvolledige back-up, migratie-/startfout, falende healthcheck en onderbreking tijdens herstel. Dit gebruikt een gecontroleerde runtime-adapter, geen echte Docker/MariaDB-foutinjectie.
- Agenttests: toestemming per provider, gescheiden privacycontext, één onderzoek tegelijk, geen providerfallback, modellen zonder tools, stoppen, hervatten, herstart/interruption, authenticatie van de adapter, eigen endpoints en exportredactie.
- Releasecatalogus: semantische volgorde, expliciete tussenstappen, weigeren van onbekende paden en bronuitval.
- PHP: syntaxis, familiestart met onbekende/geschatte gegevens, bronvermelding en GEDCOM-injectiecontrole. De module is ook geïnstantieerd tegen de webtrees 2.2.6-autoloader.
- Pinned OpenCode 1.18.35: geïsoleerd gestart met een lege home, server-, configuratie-, provider-, model-, OAuth- en sessiecontracten gecontroleerd. Geen betaalde AI-aanroepen of bestaande gebruikersaccounts gebruikt.
- Alle gebundelde release-/bronarchieven zijn gedownload en met hun vastgelegde checksums gecontroleerd.

## Ubuntu-test-VM

Op 9 oktober 2026 zijn alle 53 Python-tests geslaagd. Op Ubuntu 26.04.1 LTS (AMD64) zijn Docker Engine 29.9.0 en Compose 5.6.0 via de officiële Docker-APT-repository geïnstalleerd. `tests/docker_smoke.py` is geslaagd op deze VM en in [GitHub Actions, broncommit 93a3a8a](https://github.com/harrywesterman/openvoorouders/actions/runs/37937167722). Dezelfde CI-run bouwde de images voor AMD64 en ARM64; de functionele containerproef draaide alleen op AMD64.

De proef gebruikte echte MariaDB, webtrees en OpenCode/MCP-processen en controleerde:

- Containerstart, databaseverbinding en daadwerkelijke webtrees-login.
- Onderhoud: browseraanvragen geblokkeerd, interne logincontrole beschikbaar.
- Nieuwe lege stamboom, familiestart, beoordeling, pending wijzigingen en GEDCOM-koppelingen.
- MCP-handshakes met webtrees, archiefakte en newspapers, plus een echte webtrees-read via de bridge.
- Update en volledige snapshotrestore met dossiers, scans, pending gegevens en geheimen.

De upgradefixture gebruikt synthetische versies 0.0.0 → 0.1.0 met dezelfde images. Alleen het ophalen van het hostpakket wordt naar een lokaal, gecontroleerd pakket omgeleid. Dit bewijst de transactieroute; er bestaat nog geen vorige stabiele release om een werkelijke versieovergang mee te testen. Een aanvullende VM-proef wijzigde de databasestructuur na de snapshot: herstel verwijderde de toegevoegde kolom, herstelde de oorspronkelijke rij en behield het oorspronkelijke agentgeheim. Deze schemawijziging is ook opgenomen in de containerfixture.

De proefomgeving bevat uitsluitend synthetische onderzoeksgegevens. Er zijn geen betaalde AI-aanroepen uitgevoerd. `TMPDIR=/var/tmp` voorkomt dat de vrije-ruimtecontrole de RAM-schijf op `/tmp` meet.

## Proef met eigen modelserver

Op 9 oktober 2026 is een eigen OpenAI-compatibel endpoint gekoppeld met `mlx-community/Qwen3.8-27B-4bit`. Eerst is een gestructureerde functieaanroep gecontroleerd. Daarna is via de browser een volledige leesopdracht gestart: OpenCode riep `webtrees_get-trees` aan, ontving de echte stamboomlijst en het model gaf de correcte actieve stamboom terug in het Nederlands. De opdracht eindigde als `complete`; de toolaanroep als `completed`. Er waren geen externe archiefzoekacties of schrijfaanroepen in deze proef. Privéonderzoek was uitgeschakeld.

Dit bewijst deze provider-/modelcombinatie en een MCP-read; het is geen bewijs voor de kwaliteit van genealogisch onderzoek, andere providers, beeldherkenning of alle MCP-writes. Het endpoint en de toegangssleutel zijn lokale instellingen en worden niet in de repository opgenomen.

## Live onderzoekslog en ingestelde AI-keuzes

De VM gebruikt sinds 9 oktober 2026 een automatisch bijgewerkt onderzoekslog. Het toont zichtbare vragen, antwoorden en toolopdrachten met hun uitvoer, zonder redeneerblokken of toegangssleutels. Automatisch volgen kan worden uitgezet om terug te lezen. De browserproef met dezelfde JavaScript-code ontving opeenvolgende antwoordfragmenten zonder de conceptvraag opnieuw te laden; terugscrollen en de volgschakelaar zijn gecontroleerd.

Op de echte VM is gecontroleerd dat de owner voortgang kan lezen, een ongeldig onderzoek-ID wordt geweigerd en anonieme aanvragen geen voortgang krijgen (HTTP 403). De antwoorden worden niet gecachet. Het gestopte gesprek bleef behouden na de containerupdate. Bij Onderzoek verschijnt alleen de zelf ingestelde provider met het geconfigureerde model; de volledige catalogus blijft beschikbaar bij AI instellen. Alle 55 Python-tests, de PHP-voortgangscontroles en CI zijn geslaagd.

De eerste inhoudelijke kwartierstaatproef liet ook resterende agentproblemen zien: de onderzoeksskill was als instructiebestand beschikbaar maar niet geregistreerd voor de skill-tool, en de native read-tool weigerde dossierpaden ondanks de bedoelde profielregels. Het model probeerde bovendien herhaaldelijk de beginpersoon te identificeren en raakte in contextsamenvattingen. Deze proef is op verzoek van de gebruiker gestopt; dit is geen geslaagde inhoudelijke kwartierstaatacceptatie. Herstel en test skillregistratie, padrechten en expliciete beginpersooncontext vóór stabiele vrijgave.

## Eén stamboom in familiestart en webtrees

Op 9 oktober 2026 is op de gebruikers-VM de achtergebleven lege CI-boom verwijderd via de native webtrees-handler, na een volledige lokale snapshot. Westerman bleef behouden met zeven personen en 21 geaccepteerde wijzigingen. De startpagina, standaardboom, onderzoeksmenu's en familiestart verwijzen naar Westerman. Een tweede boom aanmaken via Openvoorouders wordt geweigerd. De opgeslagen familiestart en gesprekken blijven aanwezig.

De containerfixture controleert aanvullend dat het wissen van alleen de modulekeuze de bestaande boom opnieuw selecteert en de webtrees-standaard instelt. Ook een directe aanmaak-POST vóór die automatische selectie moet mislukken zonder een tweede boom te maken. De eerste schone proef ontdekte een ontbrekende autoloadregistratie in de gedeelde API-bibliotheek; de build registreert nu een fallback wanneer de gedeelde trait nog niet beschikbaar is.

Een afzonderlijk Compose-project op de VM doorliep daarna met succes schone installatie, echte login, onderhoud, automatische boomselectie, beide aanmaakweigeringen, familiestart en GEDCOM-koppelingen. Er zijn geen AI-aanroepen gedaan; alleen de nieuw aangemaakte testomgeving is opgeruimd. [CI voor broncommit 01b4556](https://github.com/harrywesterman/openvoorouders/actions/runs/37982245411) slaagde eveneens. De stamboomreparatie is actief op de gebruikers-VM. De aanvullende autoload-fallback is in het nieuwe image getest; dat image is daar nog niet geplaatst omdat inmiddels opnieuw onderzoek loopt.

## Nog vereist vóór stabiele vrijgave

- Functionele ARM64-containerproef uitvoeren. Controleer Python-, PHP-, Composer-, uv- en native bibliotheekversies in de buildattestatie. Bouwafhankelijkheden worden niet allemaal hermetisch uit een eigen pakketarchief gehaald; de uiteindelijke runtime-images zijn wel met digest vastgezet.
- De al gestarte MCP-processen uitgebreider toetsen: toolnamen, schema's, scopes, authenticatie, media-upload en read-before-write/hashverificatie. Externe Open Archieven-toolcontracten vastleggen en tegen drift controleren. Alleen OpenCode-health is hiervoor onvoldoende.
- De volledige interactieve installer met gepubliceerde release-assets doorlopen: automatisch webtrees-account, eerste stamboom, familiestart, GEDCOM-import en providerkeuze.
- Alle plugins samen met JustLight en de onderzoeksinterface visueel en functioneel testen, inclusief CMM-aanvullingen en de bescherming van beheerde modules.
- Een echte upgrade vanaf de vorige stabiele release testen zodra die bestaat. Breid de geslaagde snapshotrestore uit met echte stroomuitval en foutinjecties tijdens iedere relevante fase; controleer bestandsownership.
- Privacy van alle MCP-reads/writes, exportredactie, toolprompt-injectie, bronuitval, stopgedrag, modellen zonder tools/beeld en alle aangeboden authenticatiemethoden testen. Native OAuth met een localhostcallback werkt niet vanzelf vanuit een browser op een andere computer; hiervoor bestaat de hostaanmeldroute, maar iedere providerflow moet nog worden beproefd.
- Controleer de integriteitscontrole voor lokale Compose-/hostcodewijzigingen en aanvullende modules ook op de echte Ubuntu-installatie.
- De persoonlijke export is een portabele GEDCOM-/media-/dossier-/gespreksdownload, geen volledig herstelarchief. Herstellen gebruikt afgeschermde lokale snapshots via de host. Een grafische herstelwizard met upload van een secretvrij herstelbestand is nog niet aanwezig.
- Optionele lokale handschriftherkenning/OCR is nog niet als containerprofiel geleverd. Voor activering zijn afzonderlijk vastgezette software- en modelassets, resources en tests nodig.
- Een niet-technische proefgebruiker laat installatie, eerste onderzoek, update en herstel zien. Automatische tests vervangen deze proef niet.
- Licenties, bronbeschikbaarheid, Nederlandse wijzigingsinformatie, bekende beperkingen, migraties en geteste upgradepaden beoordelen. Publiceer pas daarna het stabiele manifest en de bijbehorende assets.

## Acceptatierapport

Gebruik `releases/acceptance.example.json` als structuur. Iedere verplichte controle moet een echte bewijsverwijzing hebben, en het rapport moet de SHA-256 van precies het kandidaatmanifest bevatten. `tools/approve-release.py` weigert onvolledige rapporten. Een verklaring in JSON alleen is geen bewijs dat de controle daadwerkelijk is uitgevoerd; de reviewer controleert de gekoppelde resultaten.
