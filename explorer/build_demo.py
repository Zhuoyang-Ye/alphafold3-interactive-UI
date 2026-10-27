"""Save a running explorer as a static, read-only site for GitHub Pages.

Start the explorer first (bash run_explorer.sh). Usually run through
explorer/publish_demo.sh, which also publishes the result.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
from urllib.error import HTTPError
from urllib.parse import parse_qsl, quote, urlsplit
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
STATIC=Path(__file__).parent/'static'
DEMO=Path(__file__).parent/'demo'
EXTENSIONS={'application/json':'.json','chemical/x-mmcif':'.cif','text/csv':'.csv','text/plain':'.txt'}
TERMS_NOTICE='''By using this information, you agree to AlphaFold 3 Output Terms of Use found at
https://github.com/google-deepmind/alphafold3/blob/main/OUTPUT_TERMS_OF_USE.md.

To request access to the AlphaFold 3 model parameters, follow the process set out at
https://github.com/google-deepmind/alphafold3. You may only use these if received directly
from Google. Use is subject to terms of use available at
https://github.com/google-deepmind/alphafold3/blob/main/WEIGHTS_TERMS_OF_USE.md.
'''


def canonical(url):
    """Path plus sorted, non-empty query parameters. Must match canonical() in demo.js."""
    parts=urlsplit(url)
    params=sorted((k,v) for k,v in parse_qsl(parts.query) if v)
    return parts.path+('?'+'&'.join(k+'='+v for k,v in params) if params else '')


class Snapshot:
    def __init__(self,server,out):
        self.server=server.rstrip('/')
        self.out=out
        self.home=str(Path.home())
        self.entries={}
        (out/'demo'/'data').mkdir(parents=True,exist_ok=True)

    def request(self,url,data=None,token=None):
        body,headers=None,{}
        if data is not None:
            body=json.dumps(data).encode()
            headers={'Content-Type':'application/json','X-Explorer-Token':token}
        try:
            with urlopen(Request(self.server+url,data=body,headers=headers),timeout=600) as response:
                return response.status,response.headers,response.read()
        except HTTPError as error:
            return error.code,error.headers,error.read()

    def clean(self,value):
        """Replace the home folder in every string so no local paths are published."""
        if isinstance(value,str):
            return value.replace(self.home,'~')
        if isinstance(value,list):
            return [self.clean(v) for v in value]
        if isinstance(value,dict):
            return {k:self.clean(v) for k,v in value.items()}
        return value

    def blob(self,body,extension):
        name='data/'+hashlib.sha256(body).hexdigest()[:20]+extension
        if not (self.out/'demo'/name).exists():
            (self.out/'demo'/name).write_bytes(body)
        return name

    def save(self,key,url,data=None,token=None,edit=None):
        status,headers,body=self.request(url,data,token)
        kind=headers.get('Content-Type','application/octet-stream').split(';')[0].strip()
        filename=re.search(r'filename="([^"]+)"',headers.get('Content-Disposition',''))
        entry=dict(status=status,type=kind,name=filename.group(1) if filename else None,refs=False)
        value=None
        if kind=='application/json':
            value=self.clean(json.loads(body))
            stored=edit(value) if edit else value
            # Conservation profiles repeat for every cutoff and partner; store each once.
            if isinstance(stored,dict) and isinstance(stored.get('result'),dict):
                stored={**stored,'result':{'$ref':self.blob(json.dumps(stored['result'],separators=(',',':')).encode(),'.json')}}
                entry['refs']=True
            body=json.dumps(stored,separators=(',',':')).encode()
        else:
            body=self.clean(body.decode()).encode()
        entry['file']=self.blob(body,EXTENSIONS.get(kind,'.bin'))
        self.entries[key]=entry
        return status,value

    def get(self,url,**options):
        return self.save(canonical(url),url,**options)


def crawl(snap,cutoffs):
    token=json.loads(snap.request('/api/bootstrap')[2])['token']
    _,boot=snap.get('/api/bootstrap',edit=lambda v:{**v,'token':'demo'})
    snap.get('/api/state')
    snap.get('/api/status')
    proteins={}
    for record in boot['structures']:
        sid=record['id']
        _,detail=snap.get(f'/api/structures/{sid}')
        for action in ('view','download','confidence'):
            snap.get(f'/api/structures/{sid}/{action}')
        for cutoff in cutoffs:
            snap.get(f'/api/structures/{sid}/contacts?cutoff={cutoff}')
            snap.get(f'/api/structures/{sid}/contacts.csv?cutoff={cutoff}')
        proteins[sid]=[c['id'] for c in detail['chains'] if 'polypeptide' in c['kind']]
        for chain in detail['chains']:
            if not chain.get('sequence') or 'polypeptide' not in chain['kind']:
                continue
            runs=[r['id'] for r in boot['conservation_runs'] if r['structure_id']==sid and r['chain']==chain['id']]
            partners=['']+[c['id'] for c in detail['chains'] if c['id']!=chain['id']] if runs else ['']
            for cutoff in cutoffs:
                for run in ['']+runs:
                    for partner in partners:
                        url=f'/api/structures/{sid}/conservation?chain={quote(chain["id"])}&cutoff={cutoff}'
                        snap.get(url+(f'&run={run}' if run else '')+(f'&partner={quote(partner)}' if partner else ''))
    for job in boot['jobs']:
        actions=['log','input']+(['prepared'] if job.get('prepared_input') else [])
        if job.get('kind')=='conservation' and job['status']=='completed':
            actions+=['alignment','scores','rates','tree']
        for action in actions:
            snap.get(f'/api/jobs/{job["id"]}/{action}')
    for left,left_chains in proteins.items():
        for right,right_chains in proteins.items():
            for left_chain in left_chains:
                for right_chain in right_chains:
                    snap.save('|'.join(['align',left,right,left_chain,right_chain]),'/api/align',
                        data=dict(left=left,right=right,left_chain=left_chain,right_chain=right_chain),token=token)


def private_matches(out):
    """Files that still mention this account's user name or computer name."""
    words=[Path.home().name,socket.gethostname().split('.')[0]]
    pattern=re.compile('|'.join(re.escape(w) for w in words if len(w)>2),re.IGNORECASE)
    return [str(f.relative_to(out)) for f in (out/'demo').rglob('*') if f.is_file() and pattern.search(f.read_text(errors='ignore'))]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server',default='http://127.0.0.1:8765',help='Address of the running explorer')
    parser.add_argument('--repo-url',required=True,help='GitHub page linked from the demo banner')
    parser.add_argument('--out',required=True,help='Folder to write the site into')
    args=parser.parse_args()
    out=Path(args.out).expanduser().resolve()
    out.mkdir(parents=True,exist_ok=True)
    html=(STATIC/'index.html').read_text()
    cutoffs=re.findall(r'value="([\d.]+)"',re.search(r'<select id="contact-cutoff">(.*?)</select>',html).group(1))
    snap=Snapshot(args.server,out)
    try:
        crawl(snap,cutoffs)
    except OSError as error:
        raise SystemExit(f'Could not reach the explorer at {args.server} ({error}). Start it with: bash run_explorer.sh')
    leaks=private_matches(out)
    if leaks:
        raise SystemExit('Not publishing: these saved files still contain your user or computer name:\n  '+'\n  '.join(leaks))
    (out/'demo'/'manifest.json').write_text(json.dumps(dict(repo=args.repo_url.rstrip('/'),entries=snap.entries),indent=1))
    shutil.copytree(STATIC,out,dirs_exist_ok=True,ignore=shutil.ignore_patterns('index.html','.DS_Store'))
    shutil.copy2(DEMO/'demo.js',out/'demo.js')
    html=html.replace('href="/"','href="./"').replace('href="/','href="').replace('src="/','src="')
    html=html.replace('<script defer','<script src="demo.js"></script>\n  <script defer',1)
    html=html.replace('<title>Molecule · Interaction studio</title>','<title>Molecule · AlphaFold 3 explorer demo</title>')
    (out/'index.html').write_text(html)
    shutil.copy2(ROOT/'OUTPUT_TERMS_OF_USE.md',out/'OUTPUT_TERMS_OF_USE.md')
    (out/'LEGALLY_BINDING_TERMS_OF_USE.txt').write_text(TERMS_NOTICE)
    (out/'.nojekyll').write_text('')
    size=sum(f.stat().st_size for f in out.rglob('*') if f.is_file() and '.git' not in f.parts)
    print(f'Saved {len(snap.entries)} views into {out} ({size/1e6:.1f} MB).')


if __name__=='__main__':
    main()
