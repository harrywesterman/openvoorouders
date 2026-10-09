"""Validatie van reproduceerbare releases. Geen impliciete latest-resolutie."""
import hashlib
import json
import re
from pathlib import Path


class ReleaseError(ValueError):
    pass


IMAGE = re.compile(r"^[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}$")
SHA = re.compile(r"^[a-f0-9]{64}$")
VERSION = re.compile(r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$")
COMPONENTS = {"webtrees", "php", "mariadb", "opencode", "webtrees-api", "justlight",
              "faces", "descendants", "pedigree", "fan", "module-manager",
              "archiefakte", "openarchieven", "delpher", "onderzoeksskill"}


def canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(data):
    return hashlib.sha256(canonical(data)).hexdigest()


def validate(data, deploy=True):
    if data.get("schema") != 1 or not VERSION.fullmatch(data.get("version", "")):
        raise ReleaseError("Ongeldig releaseformaat of versienummer.")
    if data.get("status") not in ("candidate", "stable"):
        raise ReleaseError("Onbekende releasestatus.")
    if deploy and data["status"] != "stable":
        raise ReleaseError("Deze kandidaat is nog niet als stabiele release vrijgegeven.")
    if deploy:
        host = data.get('host', {})
        if not host.get('url', '').startswith('https://') or not SHA.fullmatch(host.get('sha256', '')):
            raise ReleaseError('Een gecontroleerd hostpakket ontbreekt.')
    components = data.get("components", {})
    if not COMPONENTS <= components.keys():
        raise ReleaseError("Het manifest mist verplichte componenten.")
    for name, component in components.items():
        if not re.fullmatch(r'[a-z0-9-]+', name) or (component.get('folder') and not re.fullmatch(r'[A-Za-z0-9_-]{1,30}', component['folder'])):
            raise ReleaseError('Onveilige componentnaam.')
        if not component.get("version") or component["version"] in ("latest", "main", "master"):
            raise ReleaseError(f"{name}: een vaste versie is verplicht.")
        if component.get("url"):
            if not component["url"].startswith("https://") or not SHA.fullmatch(component.get("sha256", "")):
                raise ReleaseError(f"{name}: HTTPS-bron en SHA-256 zijn verplicht.")
        if component.get("image") and not IMAGE.fullmatch(component["image"]):
            raise ReleaseError(f"{name}: image-digest ontbreekt.")
    images = data.get("images", {})
    for service in ("webtrees", "agent", "database"):
        if deploy or images.get(service):
            if not isinstance(images.get(service), str) or not IMAGE.fullmatch(images[service]):
                raise ReleaseError(f"{service}: publiceer eerst een image met digest.")
    if data.get("migration", {}).get("recovery") != "full-snapshot":
        raise ReleaseError("Een volledige herstelroute is verplicht.")
    if not isinstance(data.get("upgrade_from"), list):
        raise ReleaseError("Ondersteunde upgradepaden ontbreken.")
    for previous in data["upgrade_from"]:
        if not VERSION.fullmatch(previous) or previous == data["version"]:
            raise ReleaseError("Ongeldig upgradepad.")
    return data


def load(path, deploy=True):
    return validate(json.loads(Path(path).read_text()), deploy)


def upgrade(current, target):
    validate(target)
    if current["version"] not in target["upgrade_from"]:
        raise ReleaseError("Dit upgradepad is niet getest. Installeer eerst de aangegeven tussenrelease.")
    return target
