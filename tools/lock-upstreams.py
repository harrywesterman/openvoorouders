#!/usr/bin/env python3
"""Maak een kandidaat; dit publiceert of installeert geen release.

Alleen de onderhoudspijplijn resolveert bewegende upstreamnamen. Builds consumeren
uitsluitend de resulterende vaste URLs/digests en controleren iedere download.
"""
import argparse
import concurrent.futures
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from openvoorouders.integrity import local_components
REPOS = {
    "webtrees-api": ("harrywesterman/webtrees-API", "master", "api-mcp"),
    "archiefakte": ("harrywesterman/archiefakte-mcp", "main", None),
    "delpher": ("raphink/newspapers-mcp", "master", None),
    "research-template": ("harrywesterman/stamboom-template", "main", None),
}
MODULES = {
    "justlight": ("JustCarmen/webtrees-theme-justlight", "jc-theme-justlight"),
    "faces": ("UksusoFF/webtrees-faces", "faces"),
    "descendants": ("magicsunday/webtrees-descendants-chart", "webtrees-descendants-chart"),
    "pedigree": ("magicsunday/webtrees-pedigree-chart", "webtrees-pedigree-chart"),
    "fan": ("magicsunday/webtrees-fan-chart", "webtrees-fan-chart"),
    "module-manager": ("Jefferson49/CustomModuleManager", "custom_module_manager"),
}


def github(path):
    return json.loads(subprocess.check_output(["gh", "api", path]))


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Openvoorouders-release-builder"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read()


def pin_image(repository, tag):
    url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repository}:pull"
    token = json.loads(download(url))["token"]
    req = urllib.request.Request(f"https://registry-1.docker.io/v2/{repository}/manifests/{tag}", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return f"docker.io/{repository}@{response.headers['Docker-Content-Digest']}"


def image_version(reference, variable):
    repository, digest = reference.removeprefix('docker.io/').split('@')
    token = json.loads(download(f'https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repository}:pull'))['token']
    def get(path):
        request = urllib.request.Request(f'https://registry-1.docker.io/v2/{repository}/{path}', headers={
            'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'})
        with urllib.request.urlopen(request, timeout=60) as response: return json.load(response)
    manifest = get('manifests/' + digest)
    if 'manifests' in manifest:
        child = next(m for m in manifest['manifests'] if m.get('platform', {}).get('architecture') == 'amd64' and m['platform'].get('os') == 'linux')
        manifest = get('manifests/' + child['digest'])
    config = get('blobs/' + manifest['config']['digest'])
    return next(v.split('=',1)[1] for v in config['config']['Env'] if v.startswith(variable+'='))


def archive(name, repo, ref, folder):
    sha = github(f"repos/{repo}/commits/{ref}")["sha"]
    url = f"https://api.github.com/repos/{repo}/tarball/{sha}"
    return name, {"version": sha, "repository": repo, "url": url,
                  "sha256": hashlib.sha256(download(url)).hexdigest(), "folder": folder, "archive": "tar"}


def module(name, repo, folder):
    release = github(f"repos/{repo}/releases/latest")
    assets = [a for a in release["assets"] if a["name"].endswith(".zip")]
    if not assets and name == "faces":
        return archive(name, repo, release["tag_name"], folder)
    if len(assets) != 1:
        raise RuntimeError(f"{name}: kies een expliciet release-asset ({[a['name'] for a in assets]}).")
    asset = assets[0]
    url = asset["browser_download_url"]
    return name, {"version": release["tag_name"], "repository": repo, "url": url,
                  "sha256": hashlib.sha256(download(url)).hexdigest(), "folder": folder, "archive": "zip"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="releases/candidate.json")
    parser.add_argument("--version", default="0.1.0")
    args = parser.parse_args()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [pool.submit(archive, name, *values) for name, values in REPOS.items()]
        tasks += [pool.submit(module, name, *values) for name, values in MODULES.items()]
        components = dict(t.result() for t in tasks)
    webtrees = github("repos/fisharebest/webtrees/releases/latest")["tag_name"]
    components["webtrees"] = {"version": webtrees, "image": pin_image("nathanvaughn/webtrees", webtrees)}
    components["php"] = {"version": "8.4", "image": pin_image("library/php", "8.4-apache")}
    components["mariadb"] = {"version": "11.4", "image": pin_image("library/mariadb", "11.4")}
    components["node"] = {"version": "22-trixie", "image": pin_image("library/node", "22-trixie-slim")}
    components["python"] = {"version": "3.13", "note": "Python uit het vastgezette Debian trixie Node-image."}
    components["uv"] = {"version": "0.9.5"}
    uv_metadata = json.loads(download('https://pypi.org/pypi/uv/0.9.5/json'))
    components['uv']['wheel_sha256'] = [f['digests']['sha256'] for f in uv_metadata['urls'] if 'manylinux' in f['filename'] and any(a in f['filename'] for a in ('x86_64','aarch64'))]
    components['composer'] = {'version': '2.8.12', 'image': pin_image('library/composer','2.8.12')}
    imagick = 'https://pecl.php.net/get/imagick-3.8.1.tgz'
    components['imagick'] = {'version': '3.8.1', 'url': imagick, 'sha256': hashlib.sha256(download(imagick)).hexdigest(), 'archive': 'tar'}
    for name, variable in [('php','PHP_VERSION'), ('node','NODE_VERSION'), ('mariadb','MARIADB_VERSION')]:
        components[name]['version'] = image_version(components[name]['image'], variable)
    opencode = json.loads(download("https://registry.npmjs.org/opencode-ai/latest"))
    components["opencode"] = {"version": opencode["version"], "npm_integrity": opencode["dist"]["integrity"]}
    components["openarchieven"] = {"version": "remote-1", "endpoint": "https://mcp.openarchieven.nl/",
                                  "note": "Externe dienst; toolcontract wordt per release gecontroleerd, serverversie niet beheerbaar."}
    components["onderzoeksskill"] = {"version": args.version}
    components.update(local_components(ROOT))
    manifest = {"schema": 1, "version": args.version, "status": "candidate", "upgrade_from": [],
                "minimum": {"docker": "24.0.0", "compose": "2.20.0"},
                "migration": {"recovery": "full-snapshot", "description": "Eerste installatie; upstream migraties bij start."},
                "images": {"webtrees": None, "agent": None, "database": components["mariadb"]["image"]},
                "components": components, "extra_modules": {}}
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"Kandidaat opgeslagen: {output}")


if __name__ == "__main__":
    main()
