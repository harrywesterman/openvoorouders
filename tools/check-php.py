#!/usr/bin/env python3
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for folder in ('module','containers/webtrees'):
    for file in sorted((ROOT/folder).rglob('*')):
        if file.suffix in ('.php','.phtml'): subprocess.run(['php','-l',str(file)],check=True)
