"""Start or inspect a real, small AF3 runtime check through the explorer API."""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--job')
    args = parser.parse_args()
    base = f'http://127.0.0.1:{args.port}'
    if args.job:
        with urlopen(base + '/api/jobs/' + args.job + '/log') as response:
            data = json.load(response)
        print(json.dumps({k:data['job'].get(k) for k in ('id','status','stage','error','returncode','prepared_input')}, indent=2))
        print(data['log'][-5000:])
        return
    with urlopen(base + '/api/bootstrap') as response:
        bootstrap = json.load(response)
    raw = json.loads((Path(__file__).resolve().parents[2] / 'examples/ubiquitin_monomer.json').read_text())
    raw['name'] = 'Runtime_check_ubiquitin'
    request = Request(base + '/api/jobs', data=json.dumps(dict(input=raw,mode='quick',backend='mps',samples=1,recycles=1)).encode(),
        headers={'Content-Type':'application/json','X-Explorer-Token':bootstrap['token']})
    with urlopen(request) as response:
        job = json.load(response)
    print(json.dumps({k:job[k] for k in ('id','name','status','mode')}, indent=2))


if __name__ == '__main__':
    main()
