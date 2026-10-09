"""Verified host release payloads, staged before maintenance."""
import hashlib
import os
import shutil
import tarfile
import urllib.request
from pathlib import Path


def prepare_host(root, release):
    asset = release['host']
    root = Path(root)
    stage = root / ('host-staged-' + os.urandom(6).hex())
    stage.mkdir(mode=0o700)
    archive = stage / 'host.tar.gz'
    try:
        with urllib.request.urlopen(asset['url'], timeout=120) as response, archive.open('wb') as output:
            h = hashlib.sha256()
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 20 * 1024**2:
                    raise RuntimeError('Hostpakket is onverwacht groot.')
                h.update(chunk)
                output.write(chunk)
        if h.hexdigest() != asset['sha256']:
            raise RuntimeError('Hostpakket wijkt af van de release-checksum.')
        content = stage / 'content'
        content.mkdir()
        with tarfile.open(archive) as source:
            if sum(m.size for m in source.getmembers()) > 100 * 1024**2:
                raise RuntimeError('Uitgepakt hostpakket is te groot.')
            for m in source.getmembers():
                if Path(m.name).is_absolute() or '..' in Path(m.name).parts or not (m.isfile() or m.isdir()):
                    raise RuntimeError('Onveilig hostpakket.')
            source.extractall(content, filter='data')
        for name in ('openvoorouders/cli.py', 'bin/openvoorouders', 'compose.yaml'):
            if not (content / name).is_file():
                raise RuntimeError('Hostpakket mist ' + name)
        os.chmod(content / 'bin/openvoorouders', 0o755)
        return content
    except BaseException:
        shutil.rmtree(stage)
        raise
