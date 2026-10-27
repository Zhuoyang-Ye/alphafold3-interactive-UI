"""Start a real TetR/PDB-sequence conservation run or inspect its result."""
import argparse
import json
from urllib.request import Request, urlopen


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--job')
    parser.add_argument('--method',choices=['rate4site','entropy'],default='rate4site')
    args=parser.parse_args()
    base=f'http://127.0.0.1:{args.port}'
    def get(path):
        with urlopen(base+path,timeout=30) as response:
            return json.load(response)
    if args.job:
        data=get('/api/jobs/'+args.job+'/log');job=data['job']
        print(json.dumps({k:job.get(k) for k in ('id','status','stage','error','sequence_count')},indent=2))
        if job['status']=='completed':
            result=get(f"/api/structures/{job['structure_id']}/conservation?chain={job['chain']}&run={job['id']}")
            profile=result['result']
            print(json.dumps({k:profile[k] for k in ('method_label','source_label','sequence_count','mapped_residues','supported_positions','warnings')},indent=2))
            print('Interface comparison:',json.dumps(result['interface_comparison']))
        else:
            print(data['log'][-5000:])
        return
    bootstrap=get('/api/bootstrap')
    record=next(r for r in bootstrap['structures'] if r.get('pdb_id')=='2TRT')
    detail=get('/api/structures/'+record['id'])
    chain=next(c['id'] for c in detail['chains'] if c.get('sequence'))
    payload=dict(structure_id=record['id'],chain=chain,source='search',database='pdb',
        method=args.method,max_sequences=100)
    request=Request(base+'/api/conservation',data=json.dumps(payload).encode(),
        headers={'Content-Type':'application/json','X-Explorer-Token':bootstrap['token']})
    with urlopen(request,timeout=30) as response:
        job=json.load(response)
    print(json.dumps({k:job[k] for k in ('id','name','status','method','source_label')},indent=2))


if __name__=='__main__':
    main()
