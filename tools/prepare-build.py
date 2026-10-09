#!/usr/bin/env python3
"""Download en controleer vastgezette bronbestanden vóór de containerbuild."""
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from openvoorouders.manifest import load
from openvoorouders.integrity import local_components


def extract(component, target):
    with urllib.request.urlopen(component["url"], timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != component["sha256"]:
        raise RuntimeError("Download wijkt af van release-lock: " + component["url"])
    target.mkdir(parents=True)
    if component["archive"] == "tar":
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            members = archive.getmembers()
            for member in members:
                parts = Path(member.name).parts
                if ".." in parts or member.name.startswith("/") or member.issym() or member.islnk():
                    raise RuntimeError("Onveilig bronarchief")
                if len(parts) > 1:
                    member.name = str(Path(*parts[1:]))
                    archive.extract(member, target, filter="data")
    else:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            prefix = names[0].split("/")[0] + "/" if all("/" in n for n in names) and len({n.split('/')[0] for n in names}) == 1 else ""
            for info in archive.infolist():
                name = info.filename.removeprefix(prefix)
                if not name:
                    continue
                if name.startswith("/") or ".." in Path(name).parts or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise RuntimeError("Onveilig bronarchief")
                dest = target / name
                if info.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(archive.read(info))


def main():
    manifest = load(sys.argv[1] if len(sys.argv) > 1 else ROOT / "releases/candidate.json", deploy=False)
    for name, component in local_components(ROOT).items():
        if manifest['components'].get(name) != component:
            raise RuntimeError('Lokale broncode wijkt af van de release-lock: ' + name + '. Draai tools/lock-local.py en beoordeel het manifest.')
    dest = ROOT / "dist/build"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name, component in manifest["components"].items():
        if component.get("url"):
            target = dest / ("modules" if component.get("folder") else "tools") / (component.get("folder") or name)
            extract(component, target)
            print("Gecontroleerd:", name, component["version"])
    for source in ("containers", "agent", "module", "skills", "tools"):
        shutil.copytree(ROOT / source, dest / source, dirs_exist_ok=True)
    # Deliberately narrow distribution patch, applied AFTER verifying upstream bytes.
    bridge = dest / 'modules/api-mcp/bin/webtrees-mcp.mjs'
    old = "if (url.protocol !== 'https:' || url.username || url.password)"
    new = "if ((url.protocol !== 'https:' && url.href !== 'http://webtrees/mcp') || url.username || url.password)"
    text = bridge.read_text()
    if text.count(old) != 1:
        raise RuntimeError('Webtrees MCP transportcontract is gewijzigd; beoordeel de interne HTTP-patch.')
    bridge.write_text(text.replace(old, new))
    # The shared library has no Composer autoload mapping. Its own loader can
    # skip registration when InstalledVersions already reports the same version.
    # Register a fallback only when another module has not loaded it already.
    autoload = dest / 'modules/api-mcp/autoload.php'
    old = "require_once __DIR__ . '/vendor/jefferson49/webtrees-common/autoload.php';"
    fallback = r'''
if (!trait_exists('Jefferson49\\Webtrees\\Module\\ModuleCustomTrait')) {
    $common_loader = new ClassLoader(__DIR__ . '/vendor');
    $common_loader->addPsr4('Jefferson49\\Webtrees\\', __DIR__ . '/vendor/jefferson49/webtrees-common');
    $common_loader->register(true);
}
'''
    text = autoload.read_text()
    if text.count(old) != 1:
        raise RuntimeError('Webtrees API-autoloadcontract gewijzigd; beoordeel de common-library-fallback.')
    autoload.write_text(text.replace(old, old + fallback))
    settings = dest / 'modules/api-mcp/resources/views/settings.phtml'
    text = settings.read_text().replace('Local LLMs: Allow MCP scope mcp_read_member', 'Openvoorouders: privégegevens na toestemming per provider')
    text = text.replace('It is highly recommended to activate for local LLMs only, because LLMs will get MCP read access without applying strict privacy rules.', 'Openvoorouders beheert dit uitsluitend na expliciete toestemming voor de gekozen provider. Privégegevens kunnen naar die provider worden verstuurd.')
    text = text.replace('Please make sure that "mcp_read_member" is only used for local LLMs, because LLMs will get MCP read access without applying strict privacy rules (e.g to protect the data of living persons).', 'Openvoorouders requires explicit consent for the chosen provider before sending private data, including data about living people.')
    settings.write_text(text)
    manager = dest / 'modules/custom_module_manager/src/RequestHandlers/ModuleUpgradeWizardStep.php'
    old = '$this->module_update_service = CustomModuleUpdateFactory::make($module_name);'
    guard = '''$managed_manifest = json_decode(file_get_contents('/opt/openvoorouders/release.json'), true, 512, JSON_THROW_ON_ERROR);
        $managed_folders = ['openvoorouders'];
        foreach ($managed_manifest['components'] as $component) if (!empty($component['folder'])) $managed_folders[] = $component['folder'];
        foreach ($managed_folders as $folder) {
            if ($module_name === $folder || $module_name === '_' . $folder . '_') {
                return response('Deze module wordt beheerd door Openvoorouders. Gebruik de Nederlandse beheeropdracht om Openvoorouders bij te werken.', 403);
            }
        }
        ''' + old
    text = manager.read_text()
    if text.count(old) != 1: raise RuntimeError('Custom Module Manager-contract gewijzigd; beoordeel de beheerde-modulebeveiliging.')
    manager.write_text(text.replace(old, guard))
    # API source archive needs production Composer dependencies; lock file stays upstream-owned.
    package = {"private": True, "dependencies": {"opencode-ai": manifest["components"]["opencode"]["version"]}}
    (dest / "package.json").write_text(json.dumps(package))
    uv = manifest['components']['uv']
    (dest / 'uv-requirements.txt').write_text('uv==' + uv['version'] + ''.join(' \\\n    --hash=sha256:' + h for h in uv['wheel_sha256']) + '\n')
    committed = ROOT / 'releases/opencode-package-lock.json'
    if not committed.exists():
        raise RuntimeError('Genereer en beoordeel eerst releases/opencode-package-lock.json met de releaseversie.')
    shutil.copyfile(committed, dest / 'package-lock.json')
    lock = json.loads((dest / "package-lock.json").read_text())
    if lock["packages"]["node_modules/opencode-ai"]["integrity"] != manifest["components"]["opencode"]["npm_integrity"]:
        raise RuntimeError("OpenCode npm-integriteit wijkt af van het manifest.")
    (dest / "release.json").write_text(json.dumps(manifest, indent=2))
    print("Buildcontext:", dest)


if __name__ == "__main__":
    main()
