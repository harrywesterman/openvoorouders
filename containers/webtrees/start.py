"""Persistent extras; root-owned sticky entries protect managed image code."""
import os
from pathlib import Path

modules = Path('/var/www/webtrees/modules_v4')
modules.mkdir(exist_ok=True)
os.chown(modules, 0, 0)
os.chmod(modules, 0o1777)
for target in modules.iterdir():
    if target.is_symlink() and str(target.readlink()).startswith('/opt/managed-modules/') and not target.exists():
        target.unlink()
for source in Path('/opt/managed-modules').iterdir():
    target = modules / source.name
    if target.is_symlink():
        target.unlink()
    elif target.exists():
        raise RuntimeError('Beheerde module is lokaal vervangen: ' + source.name)
    target.symlink_to(source, target_is_directory=True)
    os.lchown(target, 0, 0)
os.execvp('python3', ['python3', '/docker-entrypoint.py'])
