# Acceptatie en resterend werk

Dit is een implementatie van de eerste releasekandidaat. Er is nog geen stabiele release of geslaagde Ubuntu/Docker-integratieproef. De installer weigert de onvolledige kandidaat terecht; er worden geen image-digests verzonnen.

## Lokaal gecontroleerd

- Python-tests voor update-/back-up-/hersteltransacties: behoud van stamboom, scans, dossiers, gesprekken, aanvullende modules, hostcode, schema en geheimen.
- Foutinjecties: volle schijf, downloadfout, onvolledige back-up, migratie-/startfout, falende healthcheck en onderbreking tijdens herstel. Dit gebruikt een gecontroleerde runtime-adapter, geen echte Docker/MariaDB-foutinjectie.
- Agenttests: toestemming per provider, gescheiden privacycontext, één onderzoek tegelijk, geen providerfallback, modellen zonder tools, stoppen, hervatten, herstart/interruption, authenticatie van de adapter, eigen endpoints en exportredactie.
- Releasecatalogus: semantische volgorde, expliciete tussenstappen, weigeren van onbekende paden en bronuitval.
- PHP: syntaxis, familiestart met onbekende/geschatte gegevens, bronvermelding en GEDCOM-injectiecontrole. De module is ook geïnstantieerd tegen de webtrees 2.2.6-autoloader.
- Pinned OpenCode 1.18.35: geïsoleerd gestart met een lege home, server-, configuratie-, provider-, model-, OAuth- en sessiecontracten gecontroleerd. Geen betaalde AI-aanroepen of bestaande gebruikersaccounts gebruikt.
- Alle gebundelde release-/bronarchieven zijn gedownload en met hun vastgelegde checksums gecontroleerd.

## Nog vereist vóór stabiele vrijgave

- Images daadwerkelijk bouwen op AMD64 en ARM64. Controleer Python-, PHP-, Composer-, uv- en native bibliotheekversies in de buildattestatie. Bouwafhankelijkheden worden niet allemaal hermetisch uit een eigen pakketarchief gehaald; de uiteindelijke runtime-images zijn wel met digest vastgezet.
- De webtrees-MCP-bridge, archiefakte en newspapers als echte processen starten; toolnamen, schema's, scopes, authenticatie, media-upload en read-before-write/hashverificatie testen. Externe Open Archieven-toolcontracten vastleggen en tegen drift controleren. Alleen OpenCode-health is hiervoor onvoldoende.
- Schone Ubuntu-installatie doorlopen: automatisch webtrees-account, eerste stamboom, familiestart, GEDCOM-import en providerkeuze.
- Alle plugins samen met JustLight en de onderzoeksinterface visueel en functioneel testen, inclusief CMM-aanvullingen en de bescherming van beheerde modules.
- Upgrade en volledig herstel op echte MariaDB met bestaande gegevens, pending wijzigingen en gewijzigde schema's. Controleer ook bestandsownership en een stroomuitval tijdens iedere relevante fase.
- Privacy van alle MCP-reads/writes, exportredactie, toolprompt-injectie, bronuitval, stopgedrag, modellen zonder tools/beeld en alle aangeboden authenticatiemethoden testen. Native OAuth met een localhostcallback werkt niet vanzelf vanuit een browser op een andere computer; hiervoor bestaat de hostaanmeldroute, maar iedere providerflow moet nog worden beproefd.
- Controleer de integriteitscontrole voor lokale Compose-/hostcodewijzigingen en aanvullende modules ook op de echte Ubuntu-installatie.
- De persoonlijke export is een portabele GEDCOM-/media-/dossier-/gespreksdownload, geen volledig herstelarchief. Herstellen gebruikt afgeschermde lokale snapshots via de host. Een grafische herstelwizard met upload van een secretvrij herstelbestand is nog niet aanwezig.
- Optionele lokale handschriftherkenning/OCR is nog niet als containerprofiel geleverd. Voor activering zijn afzonderlijk vastgezette software- en modelassets, resources en tests nodig.
- Een niet-technische proefgebruiker laat installatie, eerste onderzoek, update en herstel zien. Automatische tests vervangen deze proef niet.
- Licenties, bronbeschikbaarheid, Nederlandse wijzigingsinformatie, bekende beperkingen, migraties en geteste upgradepaden beoordelen. Publiceer pas daarna het stabiele manifest en de bijbehorende assets.

## Acceptatierapport

Gebruik `releases/acceptance.example.json` als structuur. Iedere verplichte controle moet een echte bewijsverwijzing hebben, en het rapport moet de SHA-256 van precies het kandidaatmanifest bevatten. `tools/approve-release.py` weigert onvolledige rapporten. Een verklaring in JSON alleen is geen bewijs dat de controle daadwerkelijk is uitgevoerd; de reviewer controleert de gekoppelde resultaten.
