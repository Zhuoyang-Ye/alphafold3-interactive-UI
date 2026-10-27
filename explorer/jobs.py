"""Durable, single-worker AF3 queue. Commands are argument arrays, never shells."""
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import threading
import uuid

from alphafold3.common.folding_input import Input


def now():
    return datetime.now(timezone.utc).isoformat()


def save_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False))
    temp.replace(path)


def validate_input(value, mode):
    if not isinstance(value, dict):
        raise ValueError('Supply one AlphaFold 3 JSON object.')
    value = copy.deepcopy(value)
    def check_paths(obj):
        if isinstance(obj, dict):
            for key, child in obj.items():
                if key.endswith('Path') and child:
                    raise ValueError(f'{key} is not supported in browser inputs. Embed the data directly in the JSON.')
                check_paths(child)
        elif isinstance(obj, list):
            for child in obj:
                check_paths(child)
    check_paths(value)
    seeds = value.get('modelSeeds', [])
    if not isinstance(seeds, list) or not 1 <= len(seeds) <= 8 or any(type(s) is not int or not 0 <= s < 2**32 for s in seeds):
        raise ValueError('Provide 1–8 integer modelSeeds between 0 and 4294967295.')
    if len(set(seeds)) != len(seeds):
        raise ValueError('Model seeds must be unique.')
    if not str(value.get('name', '')).strip():
        raise ValueError('Give this experiment a name.')
    # AF3 accepts empty molecules here but fails much later with "Unknown residue type".
    for entry in value.get('sequences', []) if isinstance(value.get('sequences'), list) else []:
        for kind, molecule in entry.items() if isinstance(entry, dict) else []:
            if not isinstance(molecule, dict):
                continue
            if kind in ('protein', 'dna', 'rna') and not str(molecule.get('sequence') or '').strip():
                raise ValueError(f'Chain {molecule.get("id")} ({"protein" if kind == "protein" else kind.upper()}) has no sequence. Paste one or remove it.')
            if kind == 'ligand' and not (molecule.get('ccdCodes') or molecule.get('smiles')):
                raise ValueError(f'Ligand chain {molecule.get("id")} has no CCD code or SMILES. Add one or remove it.')
    if mode == 'quick':
        for entry in value.get('sequences', []):
            for kind, molecule in entry.items():
                if kind in ('protein', 'rna'):
                    molecule['unpairedMsa'] = ''
                if kind == 'protein':
                    molecule['pairedMsa'] = ''
                    molecule['templates'] = []
    if mode == 'inference':
        for entry in value.get('sequences', []):
            for kind, molecule in entry.items():
                required = ('unpairedMsa','pairedMsa','templates') if kind == 'protein' else ('unpairedMsa',) if kind == 'rna' else ()
                if any(molecule.get(k) is None for k in required):
                    raise ValueError('Inference-only needs prepared MSAs/templates. Run Prepare first, or use Sequence-only.')
    parsed = Input.from_json(json.dumps(value))
    if not parsed.chains:
        raise ValueError('Add at least one molecule.')
    if len(parsed.chains) > 32:
        raise ValueError('The local explorer supports at most 32 chains per job.')
    return json.loads(parsed.to_json())


class JobManager:
    def __init__(self, root, data_dir, db_dir, model_dir, on_complete=None, runner=None):
        self.root, self.data_dir = Path(root), Path(data_dir)
        self.db_dir, self.model_dir = Path(db_dir), Path(model_dir)
        self.jobs_dir = self.data_dir / 'jobs'
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.jobs, self.process = {}, None
        self.lock = threading.RLock()
        self.queue = queue.Queue()
        self.on_complete = on_complete or (lambda job: None)
        self.runner = runner or subprocess.Popen
        self.stopping = False
        for path in sorted(self.jobs_dir.glob('*/job.json')):
            job = json.loads(path.read_text())
            if job['status'] in ('running', 'queued', 'cancelling'):
                job.update(status='interrupted', error='The explorer stopped before this job finished. Re-run to start a new job.', finished_at=now())
                save_json(path, job)
            self.jobs[job['id']] = job
        self.worker = threading.Thread(target=self._work, daemon=True, name='af3-worker')
        self.worker.start()

    def list(self):
        with self.lock:
            return copy.deepcopy(sorted(self.jobs.values(), key=lambda j: j['created_at'], reverse=True))

    def get(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise ValueError('Job not found.')
            return copy.deepcopy(self.jobs[job_id])

    def _save(self, job):
        save_json(self.jobs_dir / job['id'] / 'job.json', job)

    def create(self, request):
        mode = request.get('mode', 'full')
        if mode not in ('full','prepare','inference','quick'):
            raise ValueError('Unknown run mode.')
        backend = request.get('backend', 'mps')
        if backend not in ('mps','cpu','gpu'):
            raise ValueError('Unknown compute backend.')
        samples, recycles = request.get('samples', 1), request.get('recycles', 10)
        if type(samples) is not int or not 1 <= samples <= 5:
            raise ValueError('Choose 1–5 samples per seed.')
        if type(recycles) is not int or not 1 <= recycles <= 20:
            raise ValueError('Choose 1–20 recycles.')
        source = request.get('input')
        if request.get('prepared_job'):
            prior = self.get(request['prepared_job'])
            if not prior.get('prepared_input'):
                raise ValueError('This job has no prepared input yet.')
            source = json.loads(Path(prior['prepared_input']).read_text())
        parsed = validate_input(source, mode)
        if mode != 'prepare' and not (self.model_dir / 'af3.bin').is_file():
            raise ValueError(f'Model weights af3.bin are missing from {self.model_dir}.')
        if mode in ('full','prepare') and not (self.db_dir / 'mmcif_files').is_dir():
            raise ValueError(f'The PDB template directory is missing from {self.db_dir}.')
        with self.lock:
            if self.stopping:
                raise ValueError('The explorer is shutting down.')
            if sum(j['status'] in ('queued','running','cancelling') for j in self.jobs.values()) >= 32:
                raise ValueError('The queue is full. Wait for jobs to finish.')
            job_id = uuid.uuid4().hex[:12]
            directory = self.jobs_dir / job_id
            directory.mkdir()
            save_json(directory / 'input.json', parsed)
            job = dict(id=job_id, name=parsed['name'], mode=mode, backend=backend,
                samples=samples, recycles=recycles, seeds=parsed['modelSeeds'],
                status='queued', stage='Waiting for the worker', created_at=now(),
                output_dir=str(directory / 'output'), prepared_input=None,
                error=None, returncode=None)
            job['command'] = self.command(job)
            self.jobs[job_id] = job
            self._save(job)
            self.queue.put(job_id)
            return copy.deepcopy(job)

    def command(self, job):
        if job.get('kind') == 'conservation':
            return [str(self.root / '.venv/bin/python'), '-u', '-m', 'explorer.conservation',
                '--config=' + str(self.jobs_dir / job['id'] / 'input.json'),
                '--output-dir=' + job['output_dir']]
        cpu = max(1, min(4, (os.cpu_count() or 4) // 4))
        return [str(self.root / '.venv/bin/python'), '-u', str(self.root / 'run_alphafold.py'),
            '--json_path=' + str(self.jobs_dir / job['id'] / 'input.json'),
            '--output_dir=' + job['output_dir'], '--db_dir=' + str(self.db_dir),
            '--model_dir=' + str(self.model_dir), '--jax_backend=' + job['backend'],
            '--flash_attention_implementation=xla',
            '--run_data_pipeline=' + str(job['mode'] in ('full','prepare')).lower(),
            '--run_inference=' + str(job['mode'] != 'prepare').lower(),
            '--num_diffusion_samples=' + str(job['samples']), '--num_recycles=' + str(job['recycles']),
            '--jackhmmer_n_cpu=' + str(cpu), '--nhmmer_n_cpu=' + str(cpu),
            '--hmmsearch_n_cpu=' + str(cpu),
            '--jax_compilation_cache_dir=' + str(self.data_dir / 'jax_cache')]

    def create_analysis(self, config):
        """Queue a server-validated conservation config on the same worker."""
        with self.lock:
            if self.stopping:
                raise ValueError('The explorer is shutting down.')
            if sum(j['status'] in ('queued','running','cancelling') for j in self.jobs.values()) >= 32:
                raise ValueError('The queue is full. Wait for jobs to finish.')
            job_id = uuid.uuid4().hex[:12]
            directory = self.jobs_dir / job_id
            directory.mkdir()
            save_json(directory / 'input.json', config)
            job = dict(id=job_id, kind='conservation', name=config['name'],
                mode='conservation', backend='cpu', samples=1, recycles=1, seeds=[],
                structure_id=config['structure_id'], chain=config['chain'],
                method=config['method'], source_label=config['source_label'],
                status='queued', stage='Waiting for the worker', created_at=now(),
                output_dir=str(directory / 'output'), prepared_input=None,
                analysis_result=None, error=None, returncode=None)
            job['command'] = self.command(job)
            self.jobs[job_id] = job
            self._save(job)
            self.queue.put(job_id)
            return copy.deepcopy(job)

    def log(self, job_id):
        self.get(job_id)
        path = self.jobs_dir / job_id / 'run.log'
        if not path.exists():
            return ''
        with path.open('rb') as stream:
            stream.seek(max(0, path.stat().st_size - 80_000))
            return stream.read().decode('utf-8', errors='replace')

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                raise ValueError('Job not found.')
            if job['status'] == 'queued':
                job.update(status='cancelled', stage='Cancelled', finished_at=now())
            elif job['status'] == 'running':
                job.update(status='cancelling', stage='Stopping process and search tools')
                if self.process:
                    self._terminate(self.process)
            self._save(job)
            return copy.deepcopy(job)

    def delete(self, job_id):
        """Remove a finished job and everything in its folder."""
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                raise ValueError('Job not found.')
            if job['status'] in ('queued', 'running', 'cancelling'):
                raise ValueError('Cancel this job before deleting it.')
            del self.jobs[job_id]
        shutil.rmtree(self.jobs_dir / job_id, ignore_errors=True)
        return copy.deepcopy(job)

    @staticmethod
    def _terminate(process):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        def force_stop():
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        threading.Thread(target=force_stop, daemon=True).start()

    def _work(self):
        while True:
            job_id = self.queue.get()
            if job_id is None:
                return
            with self.lock:
                job = self.jobs[job_id]
                if job['status'] != 'queued':
                    continue
                job.update(status='running', started_at=now(), stage='Starting conservation analysis' if job.get('kind')=='conservation' else 'Starting AlphaFold 3')
                self._save(job)
            try:
                env = dict(os.environ, PYTHONUNBUFFERED='1')
                env['PATH'] = '/opt/homebrew/bin:' + env.get('PATH', '')
                with (self.jobs_dir / job_id / 'run.log').open('w') as log:
                    with self.lock:
                        if job['status'] == 'cancelling':
                            job.update(status='cancelled', finished_at=now())
                            self._save(job)
                            continue
                        self.process = self.runner(job['command'], cwd=self.root, env=env,
                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                        process = self.process
                    code = process.wait()
                with self.lock:
                    self.process = None
                    prepared = sorted(Path(job['output_dir']).glob('**/*_data.json'))
                    if prepared:
                        job['prepared_input'] = str(prepared[0])
                    cancelled = job['status'] == 'cancelling'
                    if job.get('kind') == 'conservation' and code == 0 and not cancelled:
                        result = Path(job['output_dir']) / 'conservation.json'
                        if not result.is_file():
                            raise ValueError('The analysis process exited without a conservation result.')
                        analysis = json.loads(result.read_text())
                        job['analysis_result'] = str(result)
                        job['sequence_count'] = analysis['sequence_count']
                    job.update(status='cancelled' if cancelled else 'completed' if code == 0 else 'failed',
                        returncode=code, finished_at=now())
                    job['stage'] = {'cancelled':'Cancelled', 'completed':'Prepared input ready' if job['mode']=='prepare' else 'Prediction complete', 'failed':'AlphaFold exited with an error'}[job['status']]
                    if job.get('kind') == 'conservation':
                        job['stage'] = {'cancelled':'Cancelled', 'completed':'Conservation map ready', 'failed':'Conservation analysis exited with an error'}[job['status']]
                    if code and not cancelled:
                        tail = self.log(job_id).strip().splitlines()
                        job['error'] = '\n'.join(tail[-12:])
                    self._save(job)
                self.on_complete(copy.deepcopy(job))
            except Exception as error:
                with self.lock:
                    self.process = None
                    job.update(status='failed', error=str(error), stage='Job failed', finished_at=now())
                    self._save(job)

    def shutdown(self):
        with self.lock:
            self.stopping = True
            for job in self.jobs.values():
                if job['status'] in ('running','queued'):
                    self.cancel(job['id'])
            self.queue.put(None)
        self.worker.join(timeout=7)
