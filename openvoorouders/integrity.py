import hashlib


def managed_checksums(root):
    paths = [root / 'compose.yaml']
    paths += [p for p in (root / 'host').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
