#!/usr/bin/env python3
"""Exercise the pinned binary API in an isolated home; no model calls or user auth."""
import argparse
import base64
import hashlib
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PATHS=['/auth/{providerID}','/provider/auth','/provider/{providerID}/oauth/authorize','/provider/{providerID}/oauth/callback',
       '/session','/session/status','/session/{sessionID}/prompt_async','/session/{sessionID}/abort','/session/{sessionID}/message','/mcp']


def main():
    p=argparse.ArgumentParser();p.add_argument('binary',type=Path);p.add_argument('--record',action='store_true');args=p.parse_args()
    version=json.load(open(ROOT/'releases/candidate.json'))['components']['opencode']['version']
    binary=args.binary.resolve()
    with tempfile.TemporaryDirectory() as directory:
        home=Path(directory)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        key=secrets.token_hex(32)
        config={'$schema':'https://opencode.ai/config.json','share':'disabled','permission':{'*':'deny','read':{'*':'deny',str(home/'public/**'):'allow'},'external_directory':'deny'},
                'mcp':{'webtrees':{'type':'local','command':['node','/not-used.mjs'],'enabled':False}}}
        file=home/'config.json';file.write_text(json.dumps(config))
        env={k:v for k,v in os.environ.items() if k in ('PATH','TMPDIR','SYSTEMROOT')}
        env.update(HOME=str(home),XDG_CONFIG_HOME=str(home/'config'),XDG_DATA_HOME=str(home/'data'),XDG_CACHE_HOME=str(home/'cache'),
                   OPENCODE_SERVER_PASSWORD=key,OPENCODE_CONFIG=str(file))
        with (home/'engine.log').open('w') as log:
            process=subprocess.Popen([str(binary),'serve','--hostname','127.0.0.1','--port',str(port)],env=env,cwd=home,stdout=log,stderr=log)
            def request(method,path,body=None):
                headers={'Authorization':'Basic '+base64.b64encode(('opencode:'+key).encode()).decode(),'Content-Type':'application/json'}
                req=urllib.request.Request(f'http://127.0.0.1:{port}'+path,data=None if body is None else json.dumps(body).encode(),headers=headers,method=method)
                with urllib.request.urlopen(req,timeout=30) as response:
                    raw=response.read();return json.loads(raw) if raw else None
            try:
                for _ in range(150):
                    if process.poll() is not None: raise RuntimeError('Vastgezette OpenCode-binary start niet.')
                    try: health=request('GET','/global/health');break
                    except OSError: time.sleep(.2)
                else: raise RuntimeError('OpenCode start niet op tijd.')
                assert health=={'healthy':True,'version':version},health
                spec=request('GET','/doc')
                contract={path:hashlib.sha256(json.dumps(spec['paths'][path],sort_keys=True).encode()).hexdigest() for path in PATHS}
                for name in ['Config','Model']:
                    if name in spec['components']['schemas']:
                        contract[name]=hashlib.sha256(json.dumps(spec['components']['schemas'][name],sort_keys=True).encode()).hexdigest()
                contract_path=ROOT/'tests/contracts'/('opencode-'+version+'.json')
                if args.record: contract_path.write_text(json.dumps(contract,indent=2)+'\n')
                elif not contract_path.exists() or json.loads(contract_path.read_text())!=contract:
                    raise RuntimeError('OpenCode-toolinterface/auth/config gewijzigd. Beoordeel het contract vóór vrijgave.')
                providers=request('GET','/provider')
                assert isinstance(providers['all'],list) and isinstance(providers['connected'],list)
                for provider in providers['all']:
                    for model in provider['models'].values(): assert isinstance(model['capabilities']['toolcall'],bool)
                assert isinstance(request('GET','/provider/auth'),dict)
                actual=request('GET','/config')
                assert actual['permission']['external_directory']=='deny'
                session=request('POST','/session',{'title':'Openvoorouders contractcontrole'})
                assert isinstance(session['id'],str)
                assert request('GET','/session/'+session['id']+'/message')==[]
                assert isinstance(request('GET','/session/status'),dict)
                assert isinstance(request('GET','/mcp'),dict)
                print('OpenCode',version,': server, configuratie, providers, modelmogelijkheden, auth en sessiecontracten geslaagd. Geen AI-aanroepen gedaan.')
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill();process.wait()

if __name__=='__main__':main()
