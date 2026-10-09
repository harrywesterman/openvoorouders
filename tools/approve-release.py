#!/usr/bin/env python3
"""Prepare a stable manifest only with explicit acceptance evidence. No publication."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from openvoorouders.manifest import validate,digest
CHECKS=['clean_install','previous_upgrade','plugins_justlight','login','mcp_contracts','privacy',
        'stop_research','model_capabilities','failure_injection','full_restore','data_preservation','nontechnical_user']
p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('acceptance',type=Path);p.add_argument('--output',type=Path,default=Path('dist/stable.json'));a=p.parse_args()
m=json.loads(a.manifest.read_text());report=json.loads(a.acceptance.read_text())
if report.get('manifest_sha256')!=digest(m): raise SystemExit('Acceptatierapport hoort niet bij dit manifest.')
if not report.get('reviewer') or any(not report.get('checks',{}).get(c,{}).get('passed') or not report['checks'][c].get('evidence') for c in CHECKS): raise SystemExit('Acceptatie of onderbouwing ontbreekt; stabiele vrijgave geweigerd.')
if not report.get('release_notes_nl') or not report.get('known_limitations_nl'): raise SystemExit('Nederlandse release-informatie en bekende beperkingen ontbreken.')
m.update(status='stable',acceptance=report)
validate(m)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
print('Stabiel manifest voorbereid:',a.output)
