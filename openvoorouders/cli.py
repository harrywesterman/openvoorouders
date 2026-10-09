"""Nederlandse beheeropdrachten voor de Ubuntu-host."""
import argparse
import hashlib
import getpass
import ipaddress
import json
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import tarfile
from pathlib import Path
from urllib.parse import urlsplit

from .manifest import ReleaseError, load
from .runtime import Docker, environment
from .lifecycle import Lifecycle
from .storage import atomic, lock
from .assets import prepare_host
from .catalogue import refresh, upgrade_path
from .integrity import managed_checksums

SOURCE = Path(__file__).resolve().parents[1]


def check_ubuntu():
    if platform.system() != "Linux":
        raise RuntimeError("De begeleide installatie ondersteunt voorlopig alleen Ubuntu LTS.")
    fields = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
    if fields.get("ID", "").strip('"') != "ubuntu" or fields.get("VERSION_ID", "").strip('"') not in ("22.04", "24.04", "26.04"):
        raise RuntimeError("Gebruik Ubuntu 22.04, 24.04 of 26.04 LTS.")
    if os.geteuid() != 0:
        raise RuntimeError("Start de installer met sudo; de beheerbestanden blijven alleen voor root toegankelijk.")


def check_docker(release):
    if not shutil.which("docker"):
        raise RuntimeError("Docker ontbreekt. Start install.sh om Docker Engine via de officiële APT-repository te installeren.")
    for command, key in ((["docker", "version", "--format", "{{.Server.Version}}"], "docker"),
                         (["docker", "compose", "version", "--short"], "compose")):
        raw = subprocess.check_output(command, text=True).strip().lstrip("v")
        def version(value):
            return tuple(int(p) for p in value.split("-")[0].split(".")[:3])
        if version(raw) < version(release["minimum"][key]):
            raise RuntimeError(f"{key} moet eerst worden bijgewerkt naar {release['minimum'][key]} of nieuwer.")


def install(root, release, bind, port, url):
    check_ubuntu()
    check_docker(release)
    if platform.machine() not in ('x86_64', 'aarch64', 'arm64'):
        raise RuntimeError('Deze release ondersteunt AMD64 en ARM64.')
    if os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') < 4 * 1024**3:
        raise RuntimeError('Minimaal 4 GiB werkgeheugen nodig; lokale OCR vraagt meer.')
    if not 1024 <= port <= 65535:
        raise RuntimeError("Kies een poort tussen 1024 en 65535.")
    ipaddress.ip_address(bind)
    parsed = urlsplit(url)
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise RuntimeError("Gebruik een HTTP-basisadres zoals http://linuxserver:8080.")
    if (parsed.port or 80) != port:
        raise RuntimeError("De poort in het basisadres moet overeenkomen met de gekozen poort.")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock(root):
        if (root / "current.json").exists():
            raise RuntimeError("Deze installatie bestaat al; gebruik 'status' of 'bijwerken'. Gegevens blijven behouden.")
        with socket.socket(socket.AF_INET6 if ':' in bind else socket.AF_INET) as sock:
            sock.bind((bind, port))
        if shutil.disk_usage(root).free < 10 * 1024**3:
            raise RuntimeError("Minimaal 10 GiB vrije ruimte nodig voor installatie en back-ups.")
        for name in ("webtrees", "database", "modules", "research", "opencode", "agent-config"):
            path = root / "data" / name
            path.mkdir(parents=True, exist_ok=True)
            if name in ("research", "opencode", "agent-config"):
                os.chown(path, 10001, 10001)
                os.chmod(path, 0o2770)
        for name in ("secrets", "control", "backups"):
            (root / name).mkdir(exist_ok=True, mode=0o700 if name != "control" else 0o755)
        for name in ("database", "database_root", "agent"):
            path = root / "secrets" / name
            if not path.exists():
                path.write_text(secrets.token_hex(32))
                os.chmod(path, 0o440)
                os.chown(path, 0, 10001 if name == "agent" else 0)
        # Human settings only; database names, passwords and networking are generated.
        for name, prompt, default in [('username','Gebruikersnaam','onderzoeker'), ('name','Je naam','Onderzoeker'), ('email','Je e-mailadres','')]:
            path = root / 'secrets' / ('bootstrap_' + name)
            if not path.exists():
                value = input(f'{prompt} [{default}]: ').strip() or default
                if not value or any(c in value for c in '\r\n\x00'):
                    raise RuntimeError('Vul een geldige waarde in voor ' + prompt.lower())
                path.write_text(value)
                os.chmod(path, 0o400)
        password_file = root / 'secrets/bootstrap_password'
        if not password_file.exists():
            password = getpass.getpass('Kies een webtrees-wachtwoord (minimaal 12 tekens): ')
            repeat = getpass.getpass('Herhaal het wachtwoord: ')
            if password != repeat or len(password) < 12:
                raise RuntimeError('Wachtwoorden verschillen of zijn korter dan 12 tekens.')
            password_file.write_text(password)
            os.chmod(password_file, 0o400)
        host = prepare_host(root, release)
        if (root / 'host').exists():
            os.replace(root / 'host', root / ('host-unused-' + secrets.token_hex(4)))
        os.replace(host, root / 'host')
        shutil.copyfile(root / 'host/compose.yaml', root / 'compose.yaml')
        config = {"bind": bind, "port": port, "url": url.rstrip("/"), "managed_files": managed_checksums(root)}
        atomic(root / "installation.json", config)
        environment(root, release, config)
        runtime = Docker(root)
        runtime.pull(release)
        atomic(root / "current.json", release, 0o644)
        atomic(root / "control/maintenance.json", {"enabled": False}, 0o644)
        runtime.start()
        runtime.verify()
        atomic(root / "installation-complete.json", {"version": release["version"]})
        print(f"Openvoorouders is gestart. Open {config['url']} en meld je aan met je gekozen account.")


def export(root, backup, target):
    """Alleen expliciet toegestane gegevens: geen sessions, tokens of database met secrets."""
    # A whole webtrees DB can contain OAuth secrets. Exporting that DB cannot honestly be secret-free.
    # Export readable research only; full recovery is a separate root-only snapshot operation.
    target = Path(target)
    if target.exists():
        raise RuntimeError("Het exportbestand bestaat al.")
    with tarfile.open(target, "w:gz") as archive:
        base = root / "data/research"
        for name in ("public/dossiers", "private/dossiers"):
            path = base / name
            if path.exists():
                archive.add(path, arcname=name)
    os.chmod(target, 0o600)
    print("Dossiers geëxporteerd. Volledig herstel gebruikt de afgeschermde lokale back-up.")


def main():
    parser = argparse.ArgumentParser(description="Openvoorouders beheren")
    parser.add_argument("--map", type=Path, default=Path("/opt/openvoorouders"))
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("installeren", help="Nieuwe installatie")
    init.add_argument("manifest", type=Path)
    init.add_argument("--bind", default="127.0.0.1")
    init.add_argument("--poort", type=int, default=8080)
    init.add_argument("--adres", default="http://localhost:8080")
    update = sub.add_parser("bijwerken", help="Geteste release installeren")
    update.add_argument("manifest", type=Path, nargs='?')
    for name in ("status", "backup", "annuleer", "ai-aanmelden", "installatie-afronden", "versiecontrole"):
        sub.add_parser(name)
    restore = sub.add_parser('herstel')
    restore.add_argument('--backup', type=Path, help='Andere volledige lokale back-up terugzetten')
    check = sub.add_parser("controleer-manifest")
    check.add_argument("manifest", type=Path)
    check.add_argument("--kandidaat", action="store_true")
    args = parser.parse_args()
    try:
        root = args.map.resolve()
        runtime = Docker(root)
        lifecycle = Lifecycle(root, runtime)
        if args.command == "controleer-manifest":
            release = load(args.manifest, deploy=not args.kandidaat)
            print("Manifest geldig:", release["version"], release["status"])
        elif args.command == "installeren":
            install(root, load(args.manifest), args.bind, args.poort, args.adres)
        elif args.command == "status":
            print(json.dumps({"release": lifecycle.read("current.json")["version"],
                              "onvoltooide_update": lifecycle.pending(),
                              "installatie_voltooid": (root / "installation-complete.json").exists()}, indent=2))
        else:
            check_ubuntu()
            if args.command == "bijwerken":
                if args.manifest:
                    steps = [load(args.manifest)]
                else:
                    catalogue = refresh(root)
                    if catalogue['error']: raise RuntimeError(catalogue['error'])
                    steps = upgrade_path(lifecycle.read('current.json')['version'], catalogue['releases'])
                if not steps: print('Openvoorouders is bijgewerkt; er is geen nieuwere stabiele release.')
                for release in steps:
                    print('Release installeren:', release['version'])
                    check_docker(release)
                    lifecycle.update(release)
            elif args.command == "herstel":
                lifecycle.restore(args.backup)
            elif args.command == "annuleer":
                lifecycle.cancel()
            elif args.command == "backup":
                print("Back-up opgeslagen:", lifecycle.backup())
            elif args.command == 'installatie-afronden':
                if lifecycle.pending():
                    raise RuntimeError('Rond eerst de onvoltooide update af met herstel of annuleer.')
                runtime.start()
                runtime.verify()
                atomic(root / 'installation-complete.json', {'version': lifecycle.read('current.json')['version']})
                print('Installatie gecontroleerd en afgerond.')
            elif args.command == 'ai-aanmelden':
                with lock(root):
                    if lifecycle.pending() or runtime.busy():
                        raise RuntimeError('Rond onderzoek en onderhoud eerst af.')
                    lifecycle.maintenance(True)
                    try:
                        runtime.compose('exec', '-u', '10001:10001', 'agent', 'opencode', 'auth', 'login')
                        runtime.compose('restart', 'agent')
                    finally: lifecycle.maintenance(False)
            elif args.command == 'versiecontrole':
                catalogue = refresh(root)
                if catalogue['error']: raise RuntimeError(catalogue['error'])
                print('Releasecontrole afgerond; gevonden stabiele releases:', len(catalogue['releases']))
    except (RuntimeError, ReleaseError, OSError, subprocess.CalledProcessError, ValueError) as exc:
        print("Openvoorouders:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
