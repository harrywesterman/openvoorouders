import hashlib
import json


def managed_checksums(root):
    paths = [root / 'compose.yaml']
    paths += [p for p in (root / 'host').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def local_components(root):
    groups = {'agent-adapter':['agent','containers/agent'], 'onderzoeksinterface':['module','containers/webtrees'],
              'hostbeheer':['openvoorouders','bin','compose.yaml','install.sh'], 'buildsysteem':['tools'],
              'onderzoeksskill':['skills/nederlands-onderzoek']}
    result = {}
    for name, names in groups.items():
        files = []
        for item in names:
            path = root / item
            files.extend([path] if path.is_file() else [p for p in path.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'])
        checksums = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
        checksum = hashlib.sha256(json.dumps(checksums, sort_keys=True).encode()).hexdigest()
        result[name] = {'version': checksum, 'source_sha256': checksum}
    return result
