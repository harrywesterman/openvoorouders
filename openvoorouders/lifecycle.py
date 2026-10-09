"""Herstelbare updates met cold snapshots van alle veranderlijke toestand.

Onderhoud wordt vóór de quiescence gezet en pas na functionele controles opgeheven.
Een mislukking laat de installatie bewust in onderhoud; herstel is een expliciete actie.
"""
import hashlib
import json
import os
import shutil
import tarfile
import time
from pathlib import Path

from .manifest import digest, upgrade
from .storage import atomic, lock
from .runtime import environment
from .assets import prepare_host
from .integrity import managed_checksums


class Lifecycle:
    def __init__(self, root, runtime):
        self.root = Path(root)
        self.runtime = runtime

    def read(self, name):
        return json.loads((self.root / name).read_text())

    def mark(self, phase, **changes):
        self.journal.update(changes, phase=phase)
        self.journal.setdefault('id', time.strftime('%Y%m%dT%H%M%S') + '-' + os.urandom(6).hex())
        atomic(self.root / "update.json", self.journal)
        atomic(self.root / 'journals' / (self.journal['id'] + '.json'), self.journal)

    def maintenance(self, enabled):
        atomic(self.root / "control/maintenance.json", {"enabled": enabled}, 0o644)

    def check_space(self):
        size = sum(p.stat().st_size for p in (self.root / "data").rglob("*") if p.is_file())
        if shutil.disk_usage(self.root).free < max(2 * size, 2 * 1024**3):
            raise RuntimeError("Onvoldoende vrije ruimte voor een volledige back-up en herstel.")

    def check_local(self):
        config = self.read("installation.json")
        actual = managed_checksums(self.root)
        if config['managed_files'] != actual:
            changed = sorted(k for k in config['managed_files'].keys() | actual.keys() if config['managed_files'].get(k) != actual.get(k))
            raise RuntimeError('Beheerd bestand is lokaal gewijzigd: ' + ', '.join(changed))

    def snapshot(self, release):
        target = self.root / "backups" / (time.strftime("%Y%m%dT%H%M%S") + "-" + os.urandom(4).hex())
        target.mkdir(parents=True, mode=0o700)
        archive = target / "state.tar"
        managed = {"openvoorouders"} | {c["folder"] for c in release["components"].values() if c.get("folder")}
        def include(info):
            parts = Path(info.name).parts
            # Managed symlinks are regenerated from the new image; never archive program code.
            if len(parts) >= 3 and parts[:2] == ("data", "modules") and parts[2] in managed:
                return None
            # OpenCode installs its pinned plugin here. This is regenerated code,
            # not settings; retain package.json/lock, auth and user configuration.
            if parts[:3] == ("data", "agent-config", "node_modules"):
                return None
            if info.issym() or info.islnk() or not (info.isfile() or info.isdir()):
                raise RuntimeError("Back-up bevat een niet-ondersteunde link of speciaal bestand: " + info.name)
            return info
        with tarfile.open(archive, "w") as out:
            for name in ("data", "secrets", "host", "current.json", "installation.json", "compose.yaml", "compose.env"):
                out.add(self.root / name, arcname=name, filter=include)
        os.chmod(archive, 0o600)
        with archive.open("rb") as source:
            os.fsync(source.fileno())
            checksum = hashlib.file_digest(source, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else self.hash_file(archive)
        atomic(target / "receipt.json", {"sha256": checksum, "release": release,
                                          "manifest_sha256": digest(release), "complete": True})
        return str(target)

    @staticmethod
    def hash_file(path):
        h = hashlib.sha256()
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def pending(self):
        path = self.root / "update.json"
        return path.exists() and self.read("update.json")["phase"] not in ("complete", "restored", "cancelled")

    def update(self, target):
        with lock(self.root):
            if self.pending():
                raise RuntimeError("Een eerdere update is onvoltooid. Gebruik eerst 'herstel' of 'annuleer'.")
            current = self.read("current.json")
            upgrade(current, target)
            self.check_local()
            self.check_space()
            if self.runtime.busy():
                raise RuntimeError("Er loopt onderzoek. Rond het af of stop het via de website.")
            extras = self.runtime.inventory()
            unsupported = [m for m in extras if m["enabled"] and
                           target.get("extra_modules", {}).get(m["name"]) != m["version"]]
            if unsupported:
                raise RuntimeError("Schakel eerst aanvullende modules zonder geteste compatibiliteit uit: " +
                                   ", ".join(m["name"] for m in unsupported))
            # Download failures occur while the existing release is still available.
            self.runtime.pull(target)
            host = prepare_host(self.root, target)
            self.check_space()
            self.journal = {"from": current, "to": target, "backup": None, "phase": "prepared"}
            self.mark("prepared")
            self.maintenance(True)
            try:
                # Recheck after locking out new web/agent requests to close the start race.
                if self.runtime.busy():
                    self.mark("cancelled")
                    self.maintenance(False)
                    raise RuntimeError("Onderzoek is zojuist gestart; probeer later opnieuw.")
                self.mark("stopping")
                self.runtime.stop()
                self.mark("snapshotting")
                backup = self.snapshot(current)
                self.mark("backed-up", backup=backup)
                # From here a full snapshot restore is required, including host code/config.
                self.mark("migrating")
                os.replace(self.root / 'host', self.root / ('host-previous-' + os.urandom(4).hex()))
                os.replace(host, self.root / 'host')
                shutil.copyfile(self.root / 'host/compose.yaml', self.root / 'compose.yaml')
                config = self.read('installation.json')
                config['managed_files'] = managed_checksums(self.root)
                atomic(self.root / 'installation.json', config)
                atomic(self.root / "current.json", target, 0o644)
                environment(self.root, target, config)
                self.runtime.start()
                self.mark("checking")
                self.runtime.verify()
                self.maintenance(False)
                self.mark("complete")
            except Exception:
                # A crash never loses which release/snapshot belongs to this transaction.
                raise

    def restore(self, selected=None):
        with lock(self.root):
            if selected:
                if self.pending():
                    raise RuntimeError('Herstel eerst de onvoltooide update zonder een andere back-up te kiezen.')
                if self.runtime.busy():
                    raise RuntimeError('Stop of rond het lopende onderzoek eerst af.')
                self.journal = {'kind': 'manual-restore', 'backup': str(Path(selected).resolve()), 'phase': 'prepared'}
            else:
                self.journal = self.read("update.json")
            backup_name = self.journal.get("backup")
            if not backup_name:
                raise RuntimeError("Geen volledige back-up aanwezig. Gebruik 'annuleer' vóór een migratie.")
            backup = Path(backup_name).resolve()
            if backup.parent != (self.root / "backups").resolve():
                raise RuntimeError("Ongeldig back-uppad.")
            receipt = json.loads((backup / "receipt.json").read_text())
            if not receipt.get("complete") or self.hash_file(backup / "state.tar") != receipt["sha256"]:
                raise RuntimeError("Back-up is onvolledig of beschadigd; herstel is afgebroken.")
            if digest(receipt["release"]) != receipt["manifest_sha256"]:
                raise RuntimeError("Back-upmanifest is beschadigd.")
            self.check_space()
            self.runtime.pull(receipt["release"])
            self.maintenance(True)
            failed = self.root / self.journal.get("failed_state", ("failed-state-" + os.urandom(4).hex()))
            if failed.parent != self.root or not failed.name.startswith("failed-state-"):
                raise RuntimeError("Ongeldig hersteljournaal.")
            failed.mkdir(mode=0o700, exist_ok=True)
            self.mark("restoring", failed_state=failed.name)
            self.runtime.stop()
            staging = self.root / "restore-staging"
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(mode=0o700)
            with tarfile.open(backup / "state.tar") as archive:
                for member in archive.getmembers():
                    path = Path(member.name)
                    if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                        raise RuntimeError("Back-up bevat onveilige bestandspaden.")
                # Paths/types checked above; preserve ownership for MariaDB and UID 10001.
                archive.extractall(staging, filter="fully_trusted")
            for name in ("data", "secrets", "host", "current.json", "installation.json", "compose.yaml", "compose.env"):
                source = staging / name
                if not source.exists():
                    raise RuntimeError("Back-up mist " + name)
            # Preserve failed state; never delete a volume as an update operation.
            for name in ("data", "secrets", "host", "current.json", "installation.json", "compose.yaml", "compose.env"):
                destination = self.root / name
                if destination.exists():
                    if (failed / name).exists():
                        # On resumed restoration preserve the partial restore as well as original state.
                        retry = failed / ("retry-" + os.urandom(4).hex())
                        retry.mkdir(mode=0o700)
                        os.replace(destination, retry / name)
                    else:
                        os.replace(destination, failed / name)
                os.replace(staging / name, destination)
                self.mark("restoring", last_restored=name)
            self.runtime.start()
            self.runtime.verify()
            self.maintenance(False)
            self.mark("restored")

    def cancel(self):
        with lock(self.root):
            self.journal = self.read("update.json")
            if self.journal["phase"] not in ("prepared", "stopping", "snapshotting", "backed-up"):
                raise RuntimeError("De migratie is mogelijk begonnen. Gebruik volledig herstel.")
            atomic(self.root / "current.json", self.journal["from"], 0o644)
            environment(self.root, self.journal["from"], self.read("installation.json"))
            self.runtime.start()
            self.runtime.verify()
            self.maintenance(False)
            self.mark("cancelled")

    def backup(self):
        with lock(self.root):
            if self.pending():
                raise RuntimeError("Rond eerst de onvoltooide update af.")
            if self.runtime.busy():
                raise RuntimeError("Er loopt onderzoek; de back-up probeert het later opnieuw.")
            self.check_space()
            self.journal = {"kind": "backup", "from": self.read("current.json"), "to": self.read("current.json"), "backup": None}
            self.mark("prepared")
            self.maintenance(True)
            if self.runtime.busy():
                self.maintenance(False)
                self.mark("cancelled")
                raise RuntimeError("Onderzoek is zojuist gestart; probeer later opnieuw.")
            self.mark("stopping")
            self.runtime.stop()
            self.mark("snapshotting")
            try:
                path = self.snapshot(self.read("current.json"))
                self.mark("backed-up", backup=path)
            finally:
                self.runtime.start()
                self.runtime.verify()
            self.maintenance(False)
            self.mark("complete")
            return path
