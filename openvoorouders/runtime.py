"""Docker-adapter: alle engine-aanroepen blijven op de host."""
import json
import os
import subprocess
import tempfile
from pathlib import Path


class Docker:
    def __init__(self, root):
        self.root = Path(root)

    def command(self, *args, capture=False):
        result = subprocess.run(["docker", *args], check=True, text=True,
                                stdout=subprocess.PIPE if capture else None)
        return result.stdout if capture else ""

    def compose(self, *args, capture=False):
        return self.command("compose", "--project-name", "openvoorouders", "--env-file",
                            str(self.root / "compose.env"), "-f", str(self.root / "compose.yaml"),
                            *args, capture=capture)

    def pull(self, release):
        for image in release["images"].values():
            self.command("pull", image)
            self.command("image", "inspect", image, capture=True)

    def stop(self):
        self.compose("stop", "-t", "120")

    def start(self):
        self.compose("up", "-d", "--wait", "--wait-timeout", "240", "--remove-orphans")

    def busy(self):
        result = self.compose("exec", "-T", "agent", "python3", "-c",
                              "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:4080/internal/status', timeout=10).read().decode())",
                              capture=True)
        return json.loads(result)["busy"]

    def verify(self):
        self.compose("exec", "-T", "webtrees", "php", "/opt/openvoorouders/smoke.php")
        self.compose("exec", "-T", "agent", "python3", "-c",
                     "import urllib.request,json; r=json.load(urllib.request.urlopen('http://127.0.0.1:4080/internal/health',timeout=20)); assert r['ok'],r")

    def inventory(self):
        raw = self.compose("exec", "-T", "webtrees", "php", "/opt/openvoorouders/inventory.php", capture=True)
        return json.loads(raw)


def environment(root, release, config):
    # Docker Compose interpolation accepts dollars: reject rather than execute/expand user values.
    bind = '[' + config['bind'] + ']' if ':' in config['bind'] else config['bind']
    values = {"OVO_ROOT": str(Path(root).resolve()), "OVO_BIND": bind,
              "OVO_VERSION": release['version'],
              "OVO_PORT": str(config["port"]), "OVO_URL": config["url"],
              "WEBTREES_IMAGE": release["images"]["webtrees"],
              "AGENT_IMAGE": release["images"]["agent"], "DATABASE_IMAGE": release["images"]["database"]}
    if any(any(c in value for c in "\n\r$'\"#\\") for value in values.values()):
        raise ValueError("Ongeldig teken in installatiepad of adres.")
    target = Path(root) / "compose.env"
    fd, temporary = tempfile.mkstemp(dir=Path(root))
    try:
        with os.fdopen(fd, 'w') as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(''.join(f'{key}={value}\n' for key, value in values.items()))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
