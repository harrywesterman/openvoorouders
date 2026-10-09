#!/usr/bin/env python3
"""Lock own code independently, without resolving upstream versions."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from openvoorouders.integrity import local_components
path=ROOT/(sys.argv[1] if len(sys.argv)>1 else 'releases/candidate.json')
manifest=json.loads(path.read_text())
manifest['components'].update(local_components(ROOT))
path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
