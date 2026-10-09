"""Only Openvoorouders stable releases, never upstream component updates."""
import json
import urllib.request
from datetime import datetime, timezone
from .manifest import validate, VERSION
from .storage import atomic

REPOSITORY = 'harrywesterman/openvoorouders'


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Openvoorouders-releasecontrole', 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(2 * 1024**2 + 1)
        if len(data) > 2 * 1024**2: raise RuntimeError('Release-informatie is onverwacht groot.')
        return json.loads(data)


def refresh(root):
    path = root / 'control/releases.json'
    previous = json.loads(path.read_text()) if path.exists() else {'releases': []}
    try:
        releases = []
        for entry in fetch(f'https://api.github.com/repos/{REPOSITORY}/releases?per_page=30'):
            if entry['draft'] or entry['prerelease']: continue
            asset = next((a for a in entry['assets'] if a['name'] == 'release.json'), None)
            if asset is None: continue
            url = asset['browser_download_url']
            if not url.startswith(f'https://github.com/{REPOSITORY}/releases/download/'): continue
            manifest = validate(fetch(url))
            releases.append({'manifest': manifest, 'url': entry['html_url'], 'notes': entry.get('body', '')})
        catalogue = {'checked': datetime.now(timezone.utc).isoformat(), 'error': None, 'releases': releases}
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        catalogue = previous | {'error': 'Releasecontrole niet beschikbaar; eerder gevonden releases blijven zichtbaar.'}
    atomic(path, catalogue, 0o644)
    return catalogue


def upgrade_path(current, entries):
    """Find the explicit tested sequence to the newest stable semantic version."""
    manifests = {e['manifest']['version']: e['manifest'] for e in entries}
    stable = [v for v in manifests if '-' not in v]
    if not stable: return []
    def key(v): return tuple(map(int, v.split('.')))
    latest = max(stable, key=key)
    if key(latest) <= key(current): return []
    queue = [(current, [])]
    seen = {current}
    while queue:
        version, path = queue.pop(0)
        for target, manifest in manifests.items():
            if target not in seen and version in manifest['upgrade_from']:
                steps = path + [manifest]
                if target == latest: return steps
                seen.add(target);queue.append((target, steps))
    raise RuntimeError('Geen getest upgradepad naar de nieuwste release. Raadpleeg de Nederlandse release-informatie.')
