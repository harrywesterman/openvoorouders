# Openvoorouders

Een Nederlandstalige, zelf te hosten onderzoeksomgeving binnen webtrees. Je gebruikt één webtrees-login, één actieve stamboom en één onderzoeker. AI zoekt in archieven, leest eerdere dossiers en zet onderbouwde wijzigingen klaar voor jouw beoordeling.

**Status: eerste implementatie / releasekandidaat. Nog geen stabiele installatie voor eindgebruikers.** Het manifest weigert installatie totdat de images met digest, het hostpakket en de acceptatie van de volledige combinatie beschikbaar zijn. Op de ontwikkelmachine is geen Docker Engine aanwezig; een geslaagde Ubuntu/Docker-proef wordt hier niet geclaimd. Zie [de acceptatiestatus](docs/acceptatie.md).

## Wat er staat

- Nederlandse Ubuntu-installer met officiële Docker-APT-installatie, accountinvoer, platform-/geheugen-/opslag-/poortcontroles en gegenereerde geheimen.
- Docker Compose voor webtrees/Openvoorouders, MariaDB en een afgeschermde OpenCode-adapter. Alleen de webtrees-poort wordt gepubliceerd; er wordt nergens een Docker-socket gemount.
- JustLight, Faces, Descendants Chart, Pedigree Chart, Fan Chart, Custom Module Manager, webtrees-API en de onderzoeksinterface, met gecontroleerde brondownloads.
- Webtrees-module met accountcontrole op iedere aanvraag, familiestart zonder AI, concepten en controle vóór opslaan, onderzoek, vervolgonderzoek, stoppen, dossiers en providerinstellingen. GEDCOM-import gebruikt webtrees.
- Persoonlijke download met GEDCOM, media, dossiers, gesprekken en voorstellen. Authenticatieopslag en technische geheimen worden uitgesloten; dit is geen volledig herstelarchief.
- OpenCode-provider-/modelcatalogus, API-sleutels en native OAuth-routes, inclusief providerprompts. Eigen endpoints en lokale modelservers gebruiken de blijvende OpenCode-configuratie. Sommige browsercallbacks vereisen voorlopig native aanmelding op de Linux-machine.
- Standaard openbare privacycontext en een aparte privécontext met expliciete toestemming per provider. De technische editor kan geen voorstellen goedkeuren.
- Hostbeheer voor gecontroleerde updates, dagelijkse cold back-ups, volledig herstel, herstelbare onderbrekingen en afzonderlijke releasecontrole.
- CI voor tests, dagelijkse upstreamvoorstellen en afzonderlijk bouwen van agent- en webtrees-images. Stabiele vrijgave vereist een apart acceptatierapport en menselijke beoordeling.

## Installeren — na de eerste stabiele release

Ondersteund: Ubuntu 22.04, 24.04 of 26.04 LTS op AMD64/ARM64, minimaal 4 GiB RAM en 10 GiB vrije opslag. Houd extra ruimte voor stamboom, scans, images en volledige back-ups. Gebruik Docker Engine met de Compose-plugin; Docker Desktop en Podman zijn geen onderdeel van deze installer.

Download en pak het bronpakket van de gekozen **stabiele Openvoorouders-release** uit. Plaats het bijbehorende manifest op `releases/stable.json`, controleer de gepubliceerde checksums en start vanuit die map:

```sh
sudo bash install.sh
```

De installer vraagt je lokale IP-adres, poort (standaard 8080), browseradres en webtrees-accountgegevens. Databases, interne wachtwoorden en agentsleutels worden automatisch ingesteld. Daarna open je bijvoorbeeld `http://linuxserver:8080`, meld je je aan, maak/importeer je een stamboom en kies je hem bij **Onderzoek**.

HTTP is bedoeld voor je eigen vertrouwde netwerk. Publiceer deze poort niet rechtstreeks op internet. DNS, publieke toegang, HTTPS/tunnels, desktopinstallatie en FamilySearch komen later.

## Beheer op de Linux-machine

```sh
sudo openvoorouders status
sudo openvoorouders versiecontrole
sudo openvoorouders bijwerken
sudo openvoorouders backup
sudo openvoorouders herstel
```

`bijwerken` kiest uitsluitend stabiele Openvoorouders-releases en volgt expliciete geteste tussenstappen. Je kunt ook een lokaal gecontroleerd manifest meegeven. Docker Engine en Ubuntu worden hierbij niet bijgewerkt.

Een update downloadt eerst alle images en het hostpakket, inventariseert aanvullende modules, blokkeert nieuwe opdrachten, controleert opnieuw op lopend onderzoek en stopt alle containers voor een consistente snapshot. Daarna worden hostsoftware en containers vervangen, upstreammigraties uitgevoerd en controles gedaan. Bij een fout blijft onderhoud actief en blijft het journaal bewaard.

```sh
sudo openvoorouders annuleer          # alleen zolang migraties niet kunnen zijn begonnen
sudo openvoorouders herstel           # volledige snapshot van de laatste transactie
sudo openvoorouders herstel --backup /opt/openvoorouders/backups/NAAM
sudo openvoorouders installatie-afronden
```

Back-ups staan onder `/opt/openvoorouders/backups`, journaals onder `journals`. De volledige archieven bevatten geheimen en zijn alleen voor root toegankelijk. Maak ook een kopie op een andere schijf. De dagelijkse back-up veroorzaakt kort onderhoud; bij lopend onderzoek probeert de service het later opnieuw. Geen enkele update verwijdert gegevensvolumes.

Aanvullende modules blijven in `data/modules`. Beheerde modules zijn root-owned verwijzingen naar code in het image. Een aanvullende module zonder geteste codechecksum moet je vóór een upgrade uitschakelen in webtrees. Wijzig beheerde modules of `compose.yaml` niet rechtstreeks; de updater weigert lokale afwijkingen.

## AI en lokale modellen

API-sleutels en beschikbare OAuth-methoden stel je in bij **AI instellen**. Voor native aanmeldmethoden die niet vanuit een browser op een andere computer werken:

```sh
sudo openvoorouders ai-aanmelden
```

Eigen endpoints configureer je volgens de meegeleverde OpenCode-versie in `/opt/openvoorouders/data/agent-config/opencode.json`. Voor een modelserver op de Linux-host is `host.docker.internal` beschikbaar. De modelserver moet bereikbaar zijn vanaf het Docker-netwerk; een server die uitsluitend op host-loopback luistert is dat niet automatisch. Een andere LAN-machine kan via haar eigen adres worden gebruikt. De geselecteerde provider en het model worden nooit stilzwijgend vervangen.

Onderzoek vereist toolgebruik. Dossiers staan in `data/research/public/dossiers` en `private/dossiers`; scans blijven in de bijbehorende context. Geef uitsluitend toestemming voor privégegevens als die naar jouw gekozen provider mogen. De agent krijgt geen hostbeheer of algemene shelltoegang.

## Ontwikkelen en releases

```sh
python3 -m unittest discover -s tests -v
php -d zend.assertions=1 -d assert.exception=1 tests/family-start.php
python3 tools/prepare-build.py releases/candidate.json
cd dist/build && npm ci --omit=dev
```

Vanuit de projectroot:

```sh
python3 tools/check-opencode.py dist/build/node_modules/.bin/opencode
python3 tools/build-release.py \
  --registry ghcr.io/harrywesterman/openvoorouders \
  --asset-base https://github.com/harrywesterman/openvoorouders/releases/download/v0.1.0
```

De laatste opdracht publiceert kandidaat-images in het register; deze opdracht hoort bij een geautoriseerde releasebuild. Gebruik `--component agent` of `webtrees` met `--previous` voor afzonderlijk onderhoud. Ongewijzigde images mogen alleen worden hergebruikt als hun componenten gelijk gebleven zijn.

`tools/approve-release.py` maakt pas een stabiel manifest als het acceptatierapport bij de checksum van precies deze kandidaat hoort en alle verplichte controles bewijs hebben. Publiceer daarna na beoordeling Nederlandse release-informatie, `release.json`, `host.tar.gz`, bronpakket en checksums. Het project bevat bewust geen verzonnen stabiele image-digests.

Eigen code: [GPL-3.0-or-later](LICENSE). Zie [herkomst en componentlicenties](NOTICE.md), [architectuur](docs/architectuur.md) en [acceptatie](docs/acceptatie.md).
