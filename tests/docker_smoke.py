#!/usr/bin/env python3
"""Real Compose + MariaDB + webtrees acceptance fixture. Requires a disposable Linux host.
No external AI requests. Never run against an existing installation.
"""
import copy
import hashlib
import http.cookiejar
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from openvoorouders.lifecycle import Lifecycle
from openvoorouders.integrity import managed_checksums
from openvoorouders.runtime import Docker,environment
from openvoorouders.storage import atomic


def main():
    if os.geteuid()!=0: raise SystemExit('Deze geïsoleerde proef vereist root voor bestandsownership.')
    existing=subprocess.check_output(['docker','ps','-aq','--filter','label=com.docker.compose.project=openvoorouders'],text=True).strip()
    if existing: raise SystemExit('Er bestaan al Openvoorouders-containers. Gebruik een lege testhost.')
    manifest=json.loads(Path(sys.argv[1]).read_text())
    archive=Path(sys.argv[2]).resolve()
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['host']['sha256']: raise RuntimeError('Hostpakket-checksum ongeldig.')
    root=Path(tempfile.mkdtemp(prefix='openvoorouders-ci-'))
    runtime=Docker(root)
    report={}
    succeeded=False
    try:
        for name in ['data/database','data/webtrees','data/modules','data/research','data/opencode','data/agent-config','secrets','control','host']:
            (root/name).mkdir(parents=True,exist_ok=True)
        for name in ['research','opencode','agent-config']:
            os.chown(root/'data'/name,10001,10001);os.chmod(root/'data'/name,0o2770)
        with tarfile.open(archive) as source: source.extractall(root/'host',filter='data')
        shutil.copyfile(root/'host/compose.yaml',root/'compose.yaml')
        config={'bind':'127.0.0.1','port':18080,'url':'http://127.0.0.1:18080','managed_files':managed_checksums(root)}
        atomic(root/'installation.json',config)
        values={'database':secrets.token_hex(32),'database_root':secrets.token_hex(32),'agent':secrets.token_hex(32),
                'bootstrap_username':'ci-onderzoeker','bootstrap_name':'CI onderzoeker','bootstrap_email':'ci@example.invalid','bootstrap_password':secrets.token_hex(32)}
        for name,value in values.items():
            file=root/'secrets'/name;file.write_text(value);os.chmod(file,0o440);os.chown(file,0,10001 if name=='agent' else 0)
        atomic(root/'current.json',manifest,0o644)
        environment(root,manifest,config)
        life=Lifecycle(root,runtime);life.maintenance(False)
        runtime.pull(manifest);runtime.start();runtime.verify()
        report['container_start_database_login']=True
        base=config['url'];module='/module/_openvoorouders_/AdminResearch'
        cookies=http.cookiejar.CookieJar();browser=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
        def get(path):
            with browser.open(base+path,timeout=180) as response:return response.read().decode()
        def post(path,body,expected=200):
            page=get(path)
            token=re.search(r'name="_csrf"[^>]*value="([^"]+)"',page)
            if not token: raise RuntimeError('CSRF ontbreekt: '+path)
            payload=urllib.parse.urlencode(body|{'_csrf':token[1]}).encode()
            try:
                with browser.open(base+path,data=payload,timeout=180) as response:
                    if response.status!=expected:raise RuntimeError('Onverwachte status')
                    return response.read().decode()
            except urllib.error.HTTPError as error:
                if error.code!=expected:raise
                text=error.read().decode();error.close();return text
        post('/login',{'username':values['bootstrap_username'],'password':values['bootstrap_password'],'url':base+'/admin/trees/create'})
        post('/admin/trees/create',{'name':'ci-tree','title':'CI stamboom'})
        page=get(module)
        tree=re.search(r'<option value="(\d+)">CI stamboom',page)
        if not tree: raise RuntimeError('Openvoorouders kan de nieuwe stamboom niet kiezen.')
        post(module,{'do':'configure','tree':tree[1]})
        family=module+'?tab=familiestart'
        post(family,{'do':'draft','tab':'familiestart','review':'1','people[self][given]':'CI persoon','people[self][surname]':'Voorouder',
                     'people[self][birth]':'ABT 1900','people[self][source]':'CI familiebron','people[father][given]':'CI vader','people[father][birth]':'1870'})
        page=get(family)
        draft=re.search(r'name="draft_hash" value="([a-f0-9]{64})"',page)
        if not draft:raise RuntimeError('Controleoverzicht ontbreekt.')
        post(family,{'do':'save-family','tab':'familiestart','draft_hash':draft[1]})
        report['family_draft_review_save']=True
        def sql(statement):
            # Pass statements over stdin, never interpolate them into shell code.
            php="$p=new PDO('mysql:host=database;dbname=webtrees','webtrees',trim(file_get_contents('/run/secrets/database')),[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);$s=stream_get_contents(STDIN);echo json_encode($p->query($s)->fetchAll(PDO::FETCH_ASSOC));"
            command=['docker','compose','--project-name','openvoorouders','--env-file',str(root/'compose.env'),'-f',str(root/'compose.yaml'),'exec','-T','webtrees','php','-r',php]
            return json.loads(subprocess.check_output(command,input=statement,text=True))
        records=sql("SELECT xref,new_gedcom FROM wt_change WHERE status='pending' UNION ALL SELECT i_id AS xref,i_gedcom AS new_gedcom FROM wt_individuals")
        if not any('CI persoon' in r['new_gedcom'] and '\n1 FAMC @' in r['new_gedcom'] for r in records):
            raise RuntimeError('Beginpersoon of ouderverband ontbreekt na opslaan.')
        if not any('CI vader' in r['new_gedcom'] and '\n1 FAMS @' in r['new_gedcom'] for r in records):
            raise RuntimeError('Vader of familieverband ontbreekt na opslaan.')
        if any('0 @@' in r['new_gedcom'] for r in records):raise RuntimeError('Een opgeslagen persoon mist zijn echte XREF.')
        report['gedcom_xref_integrity']=True
        # Starting with an unknown model mints/configures MCP but can never call a paid provider.
        error=post(module,{'do':'research','provider':'opencode','model':'ci-deliberately-absent-model','prompt':'CI toolcontractcontrole'},400)
        if 'model' not in error:raise RuntimeError('Modelcontrole geeft een onverwachte fout: '+error[:500])
        probe="import sys,json;sys.path.insert(0,'/opt/agent');import server;print(json.dumps(server.engine('GET','/mcp',directory=server.DATA/'public')))"
        status=json.loads(runtime.compose('exec','-T','agent','python3','-c',probe,capture=True))
        for name in ['webtrees','archiefakte','newspapers']:
            if status.get(name,{}).get('status')!='connected':raise RuntimeError('MCP niet verbonden: '+name+' '+str(status.get(name)))
        report['local_mcp_handshakes']=True
        bridge="import {Bridge} from '/opt/tools/webtrees-bin/webtrees-mcp.mjs';import fs from 'node:fs';const c=JSON.parse(fs.readFileSync('/workspace/engine-config.json'));const b=new Bridge({endpoint:'http://webtrees/mcp',token:c.mcp.webtrees.environment.TOKEN,roots:['/workspace/public']});const t=await b.list();if(!t.tools.some(x=>x.name==='get-trees'))throw Error('get-trees missing');const r=await b.rpc('tools/call',{name:'get-trees',arguments:{}});if(r.isError)throw Error('MCP trees failed');console.log('bridge: get-trees verified');"
        runtime.compose('exec','-T','agent','node','--input-type=module','-e',bridge)
        report['webtrees_mcp_read']=True
        for profile in ['public','private']:
            path=root/'data/research'/profile/'dossiers/CI.md';path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('Bronnen, onzekerheid en vervolgstappen: CI.');os.chown(path,10001,10001)
        scan=root/'data/webtrees/media/ci-scan.txt';scan.parent.mkdir(exist_ok=True);scan.write_text('scan fixture')
        # Test the real lifecycle with local verified host bytes, identical images and a fixture upgrade version.
        old=copy.deepcopy(manifest);old['status']='stable';old['version']='0.0.0';atomic(root/'current.json',old,0o644)
        target=copy.deepcopy(manifest);target['status']='stable';target['upgrade_from']=['0.0.0']
        stage=root/'host-fixture';shutil.copytree(root/'host',stage)
        sql('CREATE TABLE ovo_ci_marker(value VARCHAR(100))');sql("INSERT INTO ovo_ci_marker VALUES('before')")
        with patch('openvoorouders.lifecycle.prepare_host',return_value=stage):life.update(target)
        sql("UPDATE ovo_ci_marker SET value='after'")
        (root/'data/research/public/dossiers/CI.md').write_text('after')
        life.restore()
        if sql('SELECT value FROM ovo_ci_marker')[0]['value']!='before':raise RuntimeError('Database-snapshot niet volledig hersteld.')
        if (root/'data/research/public/dossiers/CI.md').read_text()!='Bronnen, onzekerheid en vervolgstappen: CI.':raise RuntimeError('Dossier niet hersteld.')
        if scan.read_text()!='scan fixture' or (root/'secrets/agent').read_text()!=values['agent']:raise RuntimeError('Media/geheimen niet hersteld.')
        report['real_snapshot_upgrade_fixture_full_restore']=True
        print(json.dumps(report,indent=2))
        succeeded=True
    finally:
        # Only this newly generated CI fixture; never removes volumes or an existing installation.
        if not succeeded and os.environ.get('OVO_KEEP_FAILED_FIXTURE')=='1':
            print('Mislukte testomgeving bewaard voor diagnose: '+str(root),file=sys.stderr)
        else:
            if (root/'compose.env').exists():
                runtime.compose('down')
            shutil.rmtree(root)

if __name__=='__main__':main()
