"""Loopback-only HTTP app. Launch with .venv/bin/python -m explorer.app."""
import argparse
import csv
from functools import lru_cache
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import mimetypes
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import threading
from urllib.parse import parse_qs, unquote, urlsplit

from explorer.analysis import parse_structure, viewer_cif, contacts, align_structures
from explorer.jobs import JobManager, now, save_json, validate_input
from explorer.conservation import rate4site_binary, read_alignment, interface_comparison, DATABASE_NAMES

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).parent / 'static'
DATABASES = ['bfd-first_non_consensus_sequences.fasta', 'mgy_clusters_2022_05.fa',
    'uniref90_2022_05.fa', 'uniprot_all_2021_04.fa', 'pdb_seqres_2022_09_28.fasta',
    'rnacentral_active_seq_id_90_cov_80_linclust.fasta',
    'nt_rna_2023_02_23_clust_seq_id_90_cov_80_rep_seq.fasta',
    'rfam_14_9_clust_seq_id_90_cov_80_rep_seq.fasta', 'mmcif_files']
PRESETS = {
    'tetr_homodimer': ('TetR · protein alone', 'Two copies of the tetracycline repressor.', 'TetR study'),
    'tetr_dimer_dna': ('TetR · DNA complex', 'Explore the protein–DNA interface.', 'TetR study'),
    'tetr_dimer_tetracycline': ('TetR · tetracycline', 'Explore small-molecule contacts in the binding pocket.', 'TetR study'),
    'ubiquitin_monomer': ('Ubiquitin', 'A small, 76-residue protein for your first prediction.', 'Protein'),
    'barnase_barstar': ('Barnase + barstar', 'A compact protein–protein complex.', 'Protein'),
    'u1a_rna_hairpin': ('U1A + RNA', 'A protein bound to an RNA hairpin.', 'Nucleic acid'),
    'streptavidin_biotin_smiles': ('Streptavidin + biotin', 'A ligand defined by its SMILES string.', 'Ligand'),
}


@lru_cache(maxsize=16)
def cached_structure(path, mtime, predicted):
    return parse_structure(Path(path).read_text(), predicted)


@lru_cache(maxsize=24)
def cached_contacts(path, mtime, predicted, cutoff):
    return contacts(cached_structure(path, mtime, predicted), cutoff)


class Explorer:
    def __init__(self, data_dir, db_dir, model_dir, start_jobs=True):
        self.data_dir, self.db_dir, self.model_dir = map(lambda p: Path(p).expanduser().resolve(), (data_dir, db_dir, model_dir))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.catalog_path = self.data_dir / 'structures.json'
        self.catalog = json.loads(self.catalog_path.read_text()) if self.catalog_path.exists() else {}
        for code, name in [('1qpi', 'TetR · DNA'), ('2trt', 'TetR · tetracycline'), ('1ubq', 'Ubiquitin')]:
            path = self.db_dir / 'mmcif_files' / (code + '.cif')
            if path.is_file():
                self.register(path, name, 'reference', pdb_id=code.upper())
        self.jobs = JobManager(ROOT, self.data_dir, self.db_dir, self.model_dir, self.index_job) if start_jobs else None
        if self.jobs:
            for job in self.jobs.list():
                self.index_job(job)

    def register(self, path, name, kind, **metadata):
        path = Path(path).resolve()
        if not path.is_file() or path.suffix.lower() not in ('.cif', '.mmcif'):
            raise ValueError('Choose an existing .cif or .mmcif structure.')
        if path.stat().st_size > 80_000_000:
            raise ValueError('The structure file exceeds the 80 MB limit.')
        key = hashlib.sha256(str(path).encode()).hexdigest()[:16]
        with self.lock:
            self.catalog[key] = dict(id=key, path=str(path), name=name, kind=kind,
                added_at=self.catalog.get(key, {}).get('added_at', now()), **metadata)
            save_json(self.catalog_path, self.catalog)
        return self.catalog[key]

    def index_job(self, job):
        if job.get('kind') == 'conservation':
            return
        output = Path(job['output_dir'])
        for path in sorted(output.glob('**/*_model.cif')):
            sample = path.parent.name if path.parent.name.startswith('seed-') else 'Best ranked'
            self.register(path, job['name'], 'prediction', job_id=job['id'], sample=sample,
                mode=job['mode'])

    def record(self, key):
        with self.lock:
            if key not in self.catalog:
                raise ValueError('Structure not found.')
            record = dict(self.catalog[key])
        if not Path(record['path']).is_file():
            raise ValueError('This structure has moved or been removed from disk.')
        return record

    def parsed(self, key):
        record = self.record(key)
        path = Path(record['path'])
        return cached_structure(str(path), path.stat().st_mtime_ns, record['kind']=='prediction')

    def confidence_path(self, record, suffix):
        path = Path(record['path'])
        return path.with_name(path.stem.removesuffix('_model') + suffix + '.json')

    def detail(self, key):
        record = self.record(key)
        structure = self.parsed(key)
        summary_path = self.confidence_path(record, '_summary_confidences')
        summary = json.loads(summary_path.read_text()) if summary_path.is_file() else None
        return {**record, **{k:v for k,v in structure.items() if k != 'atoms'}, 'summary': summary}

    def contact_data(self, key, cutoff):
        record = self.record(key)
        path = Path(record['path'])
        return cached_contacts(str(path), path.stat().st_mtime_ns, record['kind']=='prediction', cutoff)

    def structures(self):
        with self.lock:
            return sorted((dict(r) for r in self.catalog.values()), key=lambda r: (r['kind'] != 'reference', r['added_at'], r.get('sample','')))

    def presets(self):
        result = []
        for path in (ROOT / 'examples').glob('*.json'):
            raw = json.loads(path.read_text())
            name, description, group = PRESETS.get(path.stem, (raw['name'].replace('_',' '), 'Ready-to-run AF3 input.', 'More examples'))
            result.append(dict(id=path.stem, name=name, description=description, group=group, input=raw))
        order = list(PRESETS)
        return sorted(result, key=lambda r: order.index(r['id']) if r['id'] in order else 99)

    def status(self):
        files = [dict(name=name, present=(self.db_dir/name).exists(), bytes=(self.db_dir/name).stat().st_size if (self.db_dir/name).is_file() else None) for name in DATABASES]
        tools = {name: shutil.which(name, path='/opt/homebrew/bin:' + os.environ.get('PATH','')) for name in ('jackhmmer','nhmmer','hmmsearch','hmmalign','hmmbuild')}
        return dict(db_dir=str(self.db_dir), model_dir=str(self.model_dir), data_dir=str(self.data_dir),
            databases=files, database_ready=all(f['present'] for f in files),
            weights_ready=(self.model_dir/'af3.bin').is_file(), tools=tools, cpu_count=os.cpu_count(),
            backend_default='mps' if os.uname().sysname == 'Darwin' else 'gpu',
            rate4site=rate4site_binary(self.data_dir),
            note='Presence check only; database checksums are not verified.')

    def conservation_runs(self):
        if not self.jobs:
            return []
        return [{k:j.get(k) for k in ('id','name','structure_id','chain','method','source_label','sequence_count','finished_at')}
            for j in self.jobs.list() if j.get('kind')=='conservation' and j['status']=='completed' and j.get('analysis_result')]

    def conservation_sources(self, key, chain_id):
        record = self.record(key)
        chain = next((c for c in self.parsed(key)['chains'] if c['id']==chain_id and c.get('sequence')),None)
        if not chain:
            raise ValueError('Choose a protein chain with a sequence.')
        candidates = []
        if self.jobs:
            candidates += [Path(j['prepared_input']) for j in self.jobs.list() if j.get('prepared_input')]
        model = Path(record['path'])
        for parent in (model.parent, model.parent.parent):
            candidates += list(parent.glob('*_data.json'))
        sources = []
        for candidate in dict.fromkeys(candidates):
            if not candidate.is_file() or candidate.stat().st_size > 100_000_000:
                continue
            raw = json.loads(candidate.read_text())
            for index, entry in enumerate(raw.get('sequences', [])):
                protein = entry.get('protein', {})
                msa = protein.get('unpairedMsa') or protein.get('pairedMsa')
                if protein.get('sequence') != chain['sequence'] or not msa or msa.count('>') < 3:
                    continue
                source_id = hashlib.sha256((str(candidate)+':'+str(index)).encode()).hexdigest()[:16]
                sources.append(dict(id=source_id, name=raw.get('name',candidate.stem),
                    path=str(candidate), chain_index=index, msa_key='unpairedMsa' if protein.get('unpairedMsa') else 'pairedMsa'))
        return dict(query=chain['sequence'], sequence_source=chain['sequence_source'],
            prepared=[{k:v for k,v in s.items() if k not in ('path','chain_index','msa_key')} for s in sources],
            _sources=sources)

    def create_conservation(self, request):
        key, chain_id = request['structure_id'], str(request['chain'])
        record = self.record(key)
        sources = self.conservation_sources(key,chain_id)
        query = sources['query']
        if not 3 <= len(query) <= 4096:
            raise ValueError('Choose a protein sequence between 3 and 4096 residues.')
        source = request.get('source','search')
        if source not in ('search','prepared','upload'):
            raise ValueError('Choose local search, prepared AF3 alignment, or alignment upload.')
        method = request.get('method','rate4site')
        if method not in ('rate4site','entropy'):
            raise ValueError('Choose Rate4Site or weighted entropy.')
        executable = rate4site_binary(self.data_dir)
        if method=='rate4site' and not executable:
            raise ValueError('Rate4Site is not installed. Run .venv/bin/python -m explorer.install_rate4site, or choose weighted entropy.')
        max_sequences = request.get('max_sequences',150)
        if type(max_sequences) is not int or not 3 <= max_sequences <= 300:
            raise ValueError('Keep between 3 and 300 aligned sequences.')
        parameters = {}
        for name,default,low,high in [('min_coverage',.7,.2,1.),('min_identity',.2,.1,.95),('redundancy',.95,.8,1.)]:
            value = float(request.get(name,default))
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'{name} must be between {low} and {high}.')
            parameters[name] = value
        config = dict(name='Conservation · '+record['name']+' · '+chain_id,
            structure_id=key, structure_path=record['path'], chain=chain_id,
            structure_sha256=hashlib.sha256(Path(record['path']).read_bytes()).hexdigest(),
            predicted=record['kind']=='prediction', query_sequence=query,
            source=source, method=method, max_sequences=max_sequences,
            rate4site=executable, **parameters)
        if source=='search':
            database = request.get('database','uniref90')
            if database not in DATABASE_NAMES:
                raise ValueError('Choose UniRef90 or the PDB sequence database.')
            file = self.db_dir / DATABASE_NAMES[database]
            tool = shutil.which('jackhmmer',path='/opt/homebrew/bin:'+os.environ.get('PATH',''))
            if not file.is_file() or not tool:
                raise ValueError('The selected sequence database or Jackhmmer executable is missing.')
            config.update(database_name=database,database_path=str(file),jackhmmer=tool,
                cpus=max(1,min(4,os.cpu_count() or 1)),
                source_label='Local UniRef90 search' if database=='uniref90' else 'Local PDB sequence search · preview subset')
        else:
            if source=='prepared':
                option = next((s for s in sources['_sources'] if s['id']==request.get('prepared_source')),None)
                if not option:
                    raise ValueError('A matching prepared alignment was not found. Select another source.')
                protein = json.loads(Path(option['path']).read_text())['sequences'][option['chain_index']]['protein']
                config.update(alignment=protein[option['msa_key']],format='a3m',source_label='Prepared AF3 MSA · '+option['name'])
            else:
                config.update(alignment=request.get('alignment',''),format=request.get('format','auto'),
                    source_label='Uploaded alignment · '+str(request.get('filename','custom'))[:100])
            # Catch query/format errors before adding work to the queue.
            read_alignment(config['alignment'],query,config['format'])
        return self.jobs.create_analysis(config)

    def conservation(self, key, chain_id, run_id=None):
        runs = [r for r in self.conservation_runs() if r['structure_id']==key and r['chain']==chain_id]
        if run_id:
            runs = [r for r in runs if r['id']==run_id]
        if not runs:
            return dict(result=None, runs=[])
        job = self.jobs.get(runs[0]['id'])
        result = json.loads(Path(job['analysis_result']).read_text())
        record = self.record(key)
        if result.get('structure_sha256') != hashlib.sha256(Path(record['path']).read_bytes()).hexdigest():
            raise ValueError('The structure changed after this conservation run. Run a new analysis before mapping scores.')
        result['job_id'] = job['id']
        return dict(result=result,runs=runs)

    def import_data(self, request):
        if request.get('pdb_id'):
            code = str(request['pdb_id']).lower().strip()
            if not re.fullmatch(r'[a-z0-9]{4}', code):
                raise ValueError('Enter a four-character PDB ID, such as 1QPI.')
            path = self.db_dir / 'mmcif_files' / (code + '.cif')
            if not path.is_file():
                raise ValueError('This PDB entry is not in your local September 2022 snapshot.')
            structure = parse_structure(path.read_text())
            return [self.register(path, code.upper() + ' · ' + structure['title'][:80], 'reference', pdb_id=code.upper())]
        if request.get('cif'):
            text = request['cif']
            if not isinstance(text, str):
                raise ValueError('The uploaded mmCIF must be text.')
            parsed = parse_structure(text)
            directory = self.data_dir / 'imports'
            directory.mkdir(exist_ok=True)
            path = directory / (secrets.token_hex(8) + '.cif')
            path.write_text(text)
            kind = 'prediction' if request.get('kind') == 'prediction' else 'reference'
            return [self.register(path, str(request.get('name') or parsed['title'])[:160], kind)]
        supplied = request.get('path', '')
        if not supplied or not isinstance(supplied, str):
            raise ValueError('Supply a local AF3 output directory, structure file, or PDB ID.')
        path = Path(supplied).expanduser().resolve()
        if path.is_file():
            parse_structure(path.read_text())
            return [self.register(path, path.stem, request.get('kind','reference') if request.get('kind') in ('prediction','reference') else 'reference')]
        if not path.is_dir():
            raise ValueError('That local path does not exist.')
        paths = list(path.glob('*_model.cif')) + list(path.glob('*/*_model.cif')) + list(path.glob('*/*/*_model.cif'))
        if not paths:
            raise ValueError('No AF3 *_model.cif outputs were found within two subfolders.')
        if len(paths) > 300:
            raise ValueError('Choose a smaller output folder (at most 300 models).')
        return [self.register(p, p.stem.removesuffix('_model'), 'prediction', sample=p.parent.name if p.parent.name.startswith('seed-') else 'Best ranked') for p in sorted(set(paths))]


class Handler(BaseHTTPRequestHandler):
    server_version = 'MoleculeExplorer/1.0'
    protocol_version = 'HTTP/1.1'

    @property
    def app(self):
        return self.server.app

    def log_message(self, fmt, *args):
        if str(args[1] if len(args)>1 else '') not in ('200', '304'):
            super().log_message(fmt, *args)

    def allowed_host(self):
        return self.headers.get('Host') in self.server.allowed_hosts

    def send(self, data, content_type='application/json; charset=utf-8', status=200, filename=None):
        if isinstance(data, (dict, list)):
            data = json.dumps(data, allow_nan=False).encode()
        elif isinstance(data, str):
            data = data.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; worker-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
        if filename:
            self.send_header('Content-Disposition', 'attachment; filename="' + re.sub(r'[^a-zA-Z0-9_.-]', '_', filename) + '"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.dispatch('GET')

    def do_POST(self):
        self.dispatch('POST')

    def dispatch(self, method):
        try:
            if not self.allowed_host():
                return self.send({'error':'Only localhost access is allowed.'}, status=403)
            target = urlsplit(self.path)
            path, query = unquote(target.path), parse_qs(target.query)
            if method == 'POST':
                if self.headers.get('X-Explorer-Token') != self.app.token:
                    return self.send({'error':'Refresh the explorer before making changes.'}, status=403)
                origin = self.headers.get('Origin')
                if origin and origin not in {'http://' + host for host in self.server.allowed_hosts}:
                    return self.send({'error':'Cross-origin requests are not allowed.'}, status=403)
                if not self.headers.get('Content-Type','').startswith('application/json'):
                    return self.send({'error':'Use application/json.'}, status=415)
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 80_000_000:
                    return self.send({'error':'Request is empty or exceeds 80 MB.'}, status=413)
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('Expected a JSON object.')
                return self.post(path, data)
            return self.get(path, query)
        except (ValueError, KeyError, TypeError, FileNotFoundError) as error:
            self.send({'error':str(error)}, status=400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:
            import traceback
            traceback.print_exc()
            self.send({'error':str(error)}, status=500)

    def get(self, path, query):
        app = self.app
        if path == '/api/bootstrap':
            return self.send(dict(token=app.token, status=app.status(), presets=app.presets(), structures=app.structures(), jobs=app.jobs.list(), conservation_runs=app.conservation_runs()))
        if path == '/api/state':
            return self.send(dict(structures=app.structures(), jobs=app.jobs.list(), conservation_runs=app.conservation_runs()))
        if path == '/api/status':
            return self.send(app.status())
        match = re.fullmatch(r'/api/jobs/([a-f0-9]{12})/(log|input|prepared|alignment|scores|rates|tree)', path)
        if match:
            job_id, action = match.groups()
            job = app.jobs.get(job_id)
            if action == 'log':
                return self.send(dict(log=app.jobs.log(job_id), job=job))
            if action in ('alignment','scores','rates','tree'):
                if job.get('kind') != 'conservation' or job['status']!='completed':
                    raise ValueError('This conservation export is not available yet.')
                filename = {'alignment':'alignment.fasta','scores':'conservation.csv','rates':'rate4site.txt','tree':'tree.nwk'}[action]
                file = Path(job['output_dir']) / filename
                if not file.is_file():
                    raise ValueError('That export is not available for this method.')
                return self.send(file.read_bytes(),'text/csv' if action=='scores' else 'text/plain',filename=filename)
            file = app.jobs.jobs_dir / job_id / 'input.json' if action == 'input' else Path(job['prepared_input']) if job.get('prepared_input') else None
            if file is None:
                raise ValueError('Prepared input is not available yet.')
            return self.send(file.read_bytes(), filename=job['name'] + '_' + action + '.json')
        match = re.fullmatch(r'/api/structures/([a-f0-9]{16})(?:/(view|download|contacts|contacts.csv|confidence|conservation|conservation-sources))?', path)
        if match:
            key, action = match.groups()
            if not action:
                return self.send(app.detail(key))
            record = app.record(key)
            if action == 'conservation-sources':
                sources = app.conservation_sources(key,query.get('chain',[''])[0])
                return self.send({k:v for k,v in sources.items() if k!='_sources'})
            if action == 'conservation':
                data = app.conservation(key,query.get('chain',[''])[0],query.get('run',[None])[0])
                if data['result']:
                    partner = query.get('partner',[None])[0]
                    data['interface_comparison'] = interface_comparison(data['result'],app.contact_data(key,float(query.get('cutoff',['4.5'])[0])),partner)
                return self.send(data)
            if action == 'view':
                return self.send(viewer_cif(app.parsed(key)), 'chemical/x-mmcif')
            if action == 'download':
                return self.send(Path(record['path']).read_bytes(), 'chemical/x-mmcif', filename=Path(record['path']).name)
            if action in ('contacts', 'contacts.csv'):
                result = app.contact_data(key, float(query.get('cutoff',['4.5'])[0]))
                if action == 'contacts':
                    return self.send(result)
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(['chain_1','residue_1','name_1','atom_1','chain_2','residue_2','name_2','atom_2','distance_angstrom'])
                for row in result['rows']:
                    a,b = row['left'],row['right']
                    writer.writerow([a['chain'],a['residue_label'],a['resn'],a['atom'],b['chain'],b['residue_label'],b['resn'],b['atom'],row['distance']])
                return self.send(buf.getvalue(), 'text/csv', filename='contacts.csv')
            if action == 'confidence':
                file = app.confidence_path(record, '_confidences')
                if not file.is_file():
                    return self.send(dict(pae=None, token_chain_ids=[], message='No AF3 confidence file accompanies this structure.'))
                raw = json.loads(file.read_text())
                return self.send({k:raw.get(k) for k in ('pae','token_chain_ids','token_res_ids')})
        if path.startswith('/api/'):
            return self.send({'error':'Endpoint not found.'}, status=404)
        file = STATIC / ('index.html' if path == '/' else path.lstrip('/'))
        if not file.resolve().is_relative_to(STATIC.resolve()) or not file.is_file():
            return self.send('Not found', 'text/plain', 404)
        return self.send(file.read_bytes(), mimetypes.guess_type(file)[0] or 'application/octet-stream')

    def post(self, path, data):
        if path == '/api/conservation':
            return self.send(self.app.create_conservation(data),status=201)
        if path == '/api/jobs':
            return self.send(self.app.jobs.create(data), status=201)
        if path == '/api/validate':
            parsed = validate_input(data.get('input'), data.get('mode','full'))
            return self.send(dict(valid=True, input=parsed))
        if path == '/api/import':
            return self.send(dict(structures=self.app.import_data(data)), status=201)
        if path == '/api/align':
            return self.send(align_structures(self.app.parsed(data['left']), self.app.parsed(data['right']), data['left_chain'], data['right_chain']))
        match = re.fullmatch(r'/api/jobs/([a-f0-9]{12})/cancel', path)
        if match:
            return self.send(self.app.jobs.cancel(match[1]))
        return self.send({'error':'Endpoint not found.'}, status=404)


def make_server(app, port):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.app = app
    server.allowed_hosts = {'127.0.0.1:' + str(server.server_port), 'localhost:' + str(server.server_port)}
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--db-dir', default=os.environ.get('DB_DIR', '~/public_databases'))
    parser.add_argument('--model-dir', default=os.environ.get('MODEL_DIR', '~/models'))
    parser.add_argument('--data-dir', default=str(ROOT / 'explorer/data'))
    args = parser.parse_args()
    app = Explorer(args.data_dir, args.db_dir, args.model_dir)
    server = make_server(app, args.port)
    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f'Molecular interaction explorer: http://127.0.0.1:{server.server_port}', flush=True)
    print(f'Databases: {app.db_dir}\nResults: {app.data_dir}\nPress Ctrl+C to stop.', flush=True)
    try:
        server.serve_forever()
    finally:
        app.jobs.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
