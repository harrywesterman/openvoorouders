# Licenties en herkomst

Eigen Openvoorouders-code: GPL-3.0-or-later, zie LICENSE. Copyright 2026 Openvoorouders-bijdragers.

Gebundelde componenten behouden hun eigen licentie, copyright, auteursvermelding en broncode. Het release-manifest bevat vaste herkomstadressen, versies/commits en SHA-256-checksums. Bronarchieven worden gecontroleerd voordat distributiepatches worden toegepast. De containerbuild verwijdert de upstream-licentiebestanden niet. Controleer licenties en benodigde bronbeschikbaarheid vóór een stabiele publicatie.

- webtrees: fisharebest/webtrees; GPL-3.0-or-later. De applicatie komt uit het vastgezette nathanvaughn/webtrees-image, inclusief de upstream-patch die de eigen updater uitschakelt. De PHP-runtime wordt apart vastgezet.
- Het opstartscript uit NathanVaughn/webtrees-docker krijgt gecontroleerde distributiepatches: de automatische setup probeert opnieuw wanneer Apache nog geen verbinding accepteert; Apache wordt het hoofdproces zodat het afsluitsignalen ontvangt. De patches staan in `containers/webtrees/patch-entrypoint.py` en weigeren een onverwachte upstream-structuur.
- JustLight, Faces, Descendants Chart, Pedigree Chart, Fan Chart en Custom Module Manager: repositories en release-assets in het manifest; oorspronkelijke auteursvermeldingen blijven in de distributie staan.
- webtrees-API: harrywesterman/webtrees-API, gebaseerd op werk van Jefferson49. Openvoorouders wijzigt de bridge uitsluitend om exact `http://webtrees/mcp` binnen Docker toe te staan, en past de privacytekst aan toestemming per provider aan. De originele bronchecksum en de distributiepatchlogica blijven beschikbaar.
- OpenCode: anomalyco/opencode; opencode-ai npm-distributie, MIT.
- archiefakte-mcp: harrywesterman/archiefakte-mcp; MIT volgens pyproject.toml.
- newspapers-mcp: raphink/newspapers-mcp; oorspronkelijk pakket en licentiebestand worden meegeleverd.
- De Nederlandse werkwijze is gebaseerd op harrywesterman/stamboom-template. Het manifest legt de broncommit vast; relevante werkwijzedocumenten worden in het agent-image opgenomen.
- Open Archieven en Delpher zijn externe bronnen. Hun serverversies en beschikbaarheid kunnen door Openvoorouders niet worden vastgezet. Toolcontracten en bronuitval horen bij releaseacceptatie.
- MariaDB, PHP, Node.js, Python, uv, Composer, Imagick en distributiepakketten behouden hun oorspronkelijke licenties. BuildKit genereert SBOM- en provenance-attestaties bij imagepublicatie.

Publiceer bij elke stabiele release ook de gebruikte bronarchieven of een controleerbaar bronpakket, de distributiepatches, npm-/uv-/Composer-lockbestanden en het volledige release-manifest.
