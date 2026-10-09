#!/usr/bin/env python3
"""Build/push only changed components; never resolve runtime tags."""
import argparse
import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from openvoorouders.manifest import load


def host_archive(target):
    with target.open('wb') as raw, gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,filename='') as zipped, tarfile.open(fileobj=zipped,mode='w') as archive:
        for name in ('openvoorouders','bin','compose.yaml','install.sh'):
            source=ROOT/name
            paths=[source]+sorted(source.rglob('*')) if source.is_dir() else [source]
            for path in paths:
                if '__pycache__' in path.parts or path.suffix=='.pyc': continue
                info=archive.gettarinfo(str(path),arcname=str(path.relative_to(ROOT)))
                info.uid=info.gid=info.mtime=0; info.uname=info.gname='root'
                if path.is_file():
                    with path.open('rb') as stream: archive.addfile(info,stream)
                else: archive.addfile(info)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--manifest',default='releases/candidate.json')
    p.add_argument('--registry',required=True,help='Bijvoorbeeld ghcr.io/eigenaar/openvoorouders')
    p.add_argument('--component',choices=['all','agent','webtrees'],default='all')
    p.add_argument('--previous',help='Eerder geteste volledige combinatie voor ongewijzigde images')
    p.add_argument('--asset-base',required=True,help='HTTPS-release-assetadres voor dit versienummer')
    args=p.parse_args()
    manifest=load(ROOT/args.manifest,deploy=False)
    if args.component!='all':
        if not args.previous: p.error('--previous is verplicht bij afzonderlijk bouwen')
        previous=load(args.previous)
        manifest['images'].update(previous['images'])
        # Only reuse an image if EVERY component that contributes to it is unchanged.
        groups={'webtrees':['webtrees','php','composer','imagick','webtrees-api','justlight','faces','descendants','pedigree','fan','module-manager'],
                'agent':['node','python','uv','opencode','webtrees-api','archiefakte','delpher','openarchieven','onderzoeksskill','research-template']}
        for service,names in groups.items():
            if service!=args.component and any(manifest['components'].get(n)!=previous['components'].get(n) for n in names):
                raise RuntimeError('Ongewijzigd image bevat gewijzigde componenten: '+service)
    subprocess.run([sys.executable,'tools/prepare-build.py',args.manifest],cwd=ROOT,check=True)
    for service in ['webtrees','agent']:
        if args.component not in ('all',service): continue
        tag=args.registry+'-'+service+':'+manifest['version']
        metadata=ROOT/'dist'/('build-'+service+'.json')
        base=manifest['components']['webtrees' if service=='webtrees' else 'node']['image']
        arg=('WEBTREES_BASE' if service=='webtrees' else 'NODE_BASE')+'='+base
        extra = []
        if service == 'webtrees':
            for name in ('php','composer'): extra += ['--build-arg', name.upper()+'_BASE='+manifest['components'][name]['image']]
        subprocess.run(['docker','buildx','build','--platform','linux/amd64,linux/arm64','--push',
                        '--provenance=mode=max','--sbom=true','--build-arg',arg,*extra,
                        '-f','dist/build/containers/'+service+'/Dockerfile','-t',tag,
                        '--metadata-file',str(metadata),'dist/build'],cwd=ROOT,check=True)
        image_digest=json.loads(metadata.read_text())['containerimage.digest']
        manifest['images'][service]=tag.split(':')[0]+'@'+image_digest
    archive=ROOT/'dist/host.tar.gz';host_archive(archive)
    manifest['host']={'url':args.asset_base.rstrip('/')+'/host.tar.gz','sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    manifest['status']='candidate'
    (ROOT/'dist/release.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('Images en hostpakket gebouwd. dist/release.json blijft kandidaat tot acceptatie en beoordeling.')

if __name__=='__main__': main()
