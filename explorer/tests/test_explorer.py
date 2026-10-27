"""Scientific calculations and actual HTTP/subprocess workflow integration tests."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
from alphafold3.cpp import cif_dict

from explorer.analysis import parse_structure, contacts, viewer_cif, align_structures
from explorer.app import Explorer, make_server
from explorer.jobs import JobManager, save_json, validate_input


def input_json(name='queue_test'):
    return dict(name=name, sequences=[{'protein':{'id':'A','sequence':'ACD'}}],
        modelSeeds=[42], dialect='alphafold3', version=4)


def cif_text(rows=None):
    rows = rows or [('A','1','ALA','CA','C',0,0,0),('A','2','CYS','CA','C',1,0,0),('A','3','ASP','CA','C',0,1,0)]
    fields = {'group_PDB':[], 'id':[], 'type_symbol':[], 'label_atom_id':[],
        'label_comp_id':[], 'label_asym_id':[], 'auth_asym_id':[], 'label_seq_id':[],
        'auth_seq_id':[], 'Cartn_x':[], 'Cartn_y':[], 'Cartn_z':[],
        'B_iso_or_equiv':[], 'label_entity_id':[], 'label_alt_id':[], 'pdbx_PDB_model_num':[]}
    for i,(chain,resi,name,atom,elem,x,y,z) in enumerate(rows):
        values=['ATOM',str(i+1),elem,atom,name,chain,chain,resi,resi,str(x),str(y),str(z),'88','1','.','1']
        for key,value in zip(fields,values):
            fields[key].append(value)
    return cif_dict.CifDict({'data_':['fixture'], '_entity.id':['1'],
        '_entity.type':['polymer'], '_entity_poly.entity_id':['1'],
        '_entity_poly.type':['polypeptide(L)'], **{'_atom_site.'+k:v for k,v in fields.items()}}).to_string()


def wait_until(predicate, timeout=8):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError('Timed out waiting for the subprocess queue.')


class AnalysisTests(unittest.TestCase):
    def test_contacts_collapse_atoms_to_residue_pairs_and_use_minimum_distance(self):
        structure=parse_structure(cif_text([
            ('A','1','ALA','CA','C',0,0,0), ('A','1','ALA','CB','C',1,0,0),
            ('B','7','GLY','CA','C',4,0,0), ('B','7','GLY','O','O',4.2,0,0),
            ('A','2','ALA','CA','C',100,0,0)]))
        result=contacts(structure,4.5)
        self.assertEqual(result['count'],1)
        self.assertEqual(result['rows'][0]['distance'],3)
        self.assertEqual(result['rows'][0]['left']['atom'],'CB')
        self.assertEqual(result['rows'][0]['right']['residue_label'],'7')
        self.assertEqual(result['interfaces'],[dict(left='A',right='B',contacts=1)])
        self.assertEqual(contacts(structure,2.5)['count'],0)

    def test_parser_excludes_water_hydrogen_and_keeps_chain_identity(self):
        structure=parse_structure(cif_text([
            ('AB','15','ALA','CA','C',0,0,0), ('AB','15','ALA','H','H',1,0,0),
            ('W','1','HOH','O','O',2,0,0), ('CD','99','GLY','CA','C',4,0,0)]))
        self.assertEqual(structure['atom_count'],2)
        self.assertEqual([c['id'] for c in structure['chains']],['AB','CD'])
        normalized=parse_structure(viewer_cif(structure))
        self.assertEqual([a['chain'] for a in normalized['atoms']],['AB','CD'])
        self.assertEqual([a['resi'] for a in normalized['atoms']],[1,1])
        self.assertIsNone(structure['chains'][0]['plddt'])
        self.assertEqual(parse_structure(cif_text(),True)['chains'][0]['plddt'],88)

    def test_kabsch_recovers_rigid_transform_and_rejects_mismatched_sequences(self):
        left=parse_structure(cif_text())
        right=copy.deepcopy(left)
        rotation=np.array([[0,-1,0],[1,0,0],[0,0,1]])
        for a in right['atoms']:
            xyz=np.array([a[k] for k in ('x','y','z')]) @ rotation + [5,9,2]
            a.update(zip(('x','y','z'),xyz))
        aligned=align_structures(left,right,'A','A')
        self.assertEqual(aligned['rmsd'],0)
        self.assertEqual(aligned['matched_atoms'],3)
        right['residues'][0]['name']='GLY'
        with self.assertRaises(ValueError):
            align_structures(left,right,'A','A')

    def test_invalid_cutoff(self):
        for value in [0,9,float('nan')]:
            with self.assertRaises(ValueError):
                contacts(parse_structure(cif_text()),value)


class InputTests(unittest.TestCase):
    def test_quick_mode_clears_evidence_and_inference_requires_prepared_data(self):
        raw=input_json()
        with self.assertRaises(ValueError):
            validate_input(raw,'inference')
        quick=validate_input(raw,'quick')
        protein=quick['sequences'][0]['protein']
        self.assertEqual(protein['unpairedMsa'],'')
        self.assertEqual(protein['pairedMsa'],'')
        self.assertEqual(protein['templates'],[])
        self.assertEqual(validate_input(quick,'inference')['name'],'queue_test')
        self.assertNotIn('unpairedMsa',raw['sequences'][0]['protein'])

    def test_rejects_paths_and_invalid_seeds(self):
        raw=input_json()
        raw['sequences'][0]['protein']['unpairedMsaPath']='/etc/passwd'
        with self.assertRaisesRegex(ValueError,'Embed'):
            validate_input(raw,'full')
        for seeds in [[],[1,1],[True],[-1],['42'],[2**32]]:
            raw=input_json();raw['modelSeeds']=seeds
            with self.assertRaises(ValueError):
                validate_input(raw,'full')


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.db=self.root/'db';(self.db/'mmcif_files').mkdir(parents=True)
        self.models=self.root/'models';self.models.mkdir();(self.models/'af3.bin').write_text('test fixture')
        self.data=self.root/'data'
        self.fixture=self.root/'fixture.cif';self.fixture.write_text(cif_text())
        self.fake=self.root/'fake_af3.py'
        self.fake.write_text('''import json, pathlib, sys, time
args=dict(a[2:].split('=',1) for a in sys.argv[1:] if a.startswith('--'))
raw=json.loads(pathlib.Path(args['json_path']).read_text())
if raw['name']=='long':
    print('Long job started',flush=True)
    time.sleep(30)
output=pathlib.Path(args['output_dir'])/'queue_test'
output.mkdir(parents=True,exist_ok=True)
for entry in raw['sequences']:
    for kind,m in entry.items():
        if kind=='protein': m.update(unpairedMsa='',pairedMsa='',templates=[])
(output/'queue_test_data.json').write_text(json.dumps(raw))
if args['run_inference']=='true':
    (output/'queue_test_model.cif').write_text(pathlib.Path(sys.argv[-1]).read_text())
    (output/'queue_test_summary_confidences.json').write_text(json.dumps(dict(iptm=.7,ptm=.8,has_clash=False)))
    (output/'queue_test_confidences.json').write_text(json.dumps(dict(pae=[[0,1,2],[1,0,1],[2,1,0]],token_chain_ids=['A']*3)))
print('Fixture process completed',flush=True)
''')
        self.commands=[]
        def runner(command,**kwargs):
            self.commands.append(command)
            if 'explorer.conservation' in command:
                kwargs['cwd']=Path(__file__).resolve().parents[2]
                return subprocess.Popen([sys.executable,*command[1:]],**kwargs)
            return subprocess.Popen([sys.executable,str(self.fake),*command[3:],str(self.fixture)],**kwargs)
        self.app=Explorer(self.data,self.db,self.models,start_jobs=False)
        self.manager=JobManager(self.root,self.data,self.db,self.models,self.app.index_job,runner=runner)
        self.app.jobs=self.manager
        self.server=make_server(self.app,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.manager.shutdown();self.temp.cleanup()

    def request(self,path,data=None,token=True,headers=None):
        headers=dict(headers or {})
        if data is not None:
            headers['Content-Type']='application/json'
            if token:headers['X-Explorer-Token']=self.app.token
        request=Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        with urlopen(request,timeout=5) as response:
            return json.load(response)

    def test_http_submission_output_indexing_confidence_and_downloads(self):
        job=self.request('/api/jobs',dict(input=input_json(),mode='quick',backend='cpu'))
        wait_until(lambda:self.manager.get(job['id'])['status']=='completed')
        wait_until(lambda:len(self.app.structures())==1)
        listing=self.request('/api/state')
        record=listing['structures'][0]
        self.assertEqual(record['job_id'],job['id'])
        detail=self.request('/api/structures/'+record['id'])
        self.assertEqual(detail['summary']['iptm'],.7)
        self.assertEqual(detail['atom_count'],3)
        confidence=self.request('/api/structures/'+record['id']+'/confidence')
        self.assertEqual(len(confidence['pae']),3)
        with urlopen(self.base+'/api/structures/'+record['id']+'/view') as response:
            self.assertEqual(parse_structure(response.read().decode())['atom_count'],3)
        with urlopen(self.base+'/api/structures/'+record['id']+'/contacts.csv') as response:
            self.assertIn('distance_angstrom',response.read().decode())
        self.assertIn('--run_data_pipeline=false',self.commands[0])
        self.assertIn('Fixture process completed',self.request('/api/jobs/'+job['id']+'/log')['log'])

    def test_prepare_then_predict_reuses_input(self):
        prepared=self.request('/api/jobs',dict(input=input_json(),mode='prepare',backend='cpu'))
        wait_until(lambda:self.manager.get(prepared['id'])['status']=='completed')
        self.assertTrue(self.manager.get(prepared['id'])['prepared_input'])
        prediction=self.request('/api/jobs',dict(prepared_job=prepared['id'],mode='inference',backend='cpu'))
        wait_until(lambda:self.manager.get(prediction['id'])['status']=='completed')
        self.assertIn('--run_data_pipeline=false',self.commands[-1])
        self.assertIn('--run_inference=false',self.commands[0])

    def test_queue_cancellation_stops_process_and_runs_next_job(self):
        first=self.manager.create(dict(input=input_json('long'),mode='quick',backend='cpu'))
        wait_until(lambda:'Long job started' in self.manager.log(first['id']))
        second=self.manager.create(dict(input=input_json(),mode='quick',backend='cpu'))
        self.assertEqual(self.manager.get(second['id'])['status'],'queued')
        self.manager.cancel(first['id'])
        wait_until(lambda:self.manager.get(first['id'])['status']=='cancelled')
        wait_until(lambda:self.manager.get(second['id'])['status']=='completed')
        self.assertFalse(list(Path(first['output_dir']).glob('**/*_model.cif')))

    def test_requests_require_token_local_host_and_origin(self):
        for token,headers in [(False,{}),(True,{'Origin':'https://example.com'}),(True,{'Host':'example.com'})]:
            with self.assertRaises(HTTPError) as error:
                self.request('/api/import',{'cif':cif_text()},token=token,headers=headers)
            self.assertEqual(error.exception.code,403)
        with self.assertRaises(HTTPError) as error:
            self.request('/../jobs.py')
        self.assertEqual(error.exception.code,404)

    def test_imported_reference_has_no_fabricated_confidence(self):
        imported=self.request('/api/import',dict(cif=cif_text(),name='Imported reference'))
        detail=self.request('/api/structures/'+imported['structures'][0]['id'])
        self.assertIsNone(detail['summary'])
        self.assertIsNone(detail['chains'][0]['plddt'])
        self.assertEqual(detail['kind'],'reference')

    def test_actual_conservation_process_maps_scores_and_exports_alignment(self):
        record=self.app.register(self.fixture,'Fixture','reference')
        alignment='>query\nACD\n>one\nACE\n>two\nACF\n>three\nACG\n'
        job=self.request('/api/conservation',dict(structure_id=record['id'],chain='A',
            source='upload',method='entropy',alignment=alignment,format='fasta'))
        wait_until(lambda:self.manager.get(job['id'])['status'] not in ('running','queued'))
        finished=self.manager.get(job['id'])
        self.assertEqual(finished['status'],'completed',finished.get('error'))
        result=self.request('/api/structures/'+record['id']+'/conservation?chain=A')
        self.assertEqual(result['result']['positions'][0]['score'],1.)
        self.assertEqual(result['result']['residues'][2]['query_position'],3)
        self.assertEqual(result['result']['sequence_count'],4)
        with urlopen(self.base+'/api/jobs/'+job['id']+'/alignment') as response:
            self.assertTrue(response.read().decode().startswith('>query\nACD\n'))
        with urlopen(self.base+'/api/jobs/'+job['id']+'/scores') as response:
            self.assertIn('normalized_rate',response.read().decode())

    def test_prepared_af3_alignment_is_discovered_and_reused(self):
        record=self.app.register(self.fixture,'Fixture','reference')
        raw=input_json('Existing_AF3_input')
        raw['sequences'][0]['protein']['unpairedMsa']='>query\nACD\n>one\nACE\n>two\nACF\n'
        save_json(self.root/'prepared_data.json',raw)
        sources=self.request('/api/structures/'+record['id']+'/conservation-sources?chain=A')
        self.assertEqual(len(sources['prepared']),1)
        self.assertNotIn('path',sources['prepared'][0])
        job=self.request('/api/conservation',dict(structure_id=record['id'],chain='A',source='prepared',
            method='entropy',prepared_source=sources['prepared'][0]['id']))
        wait_until(lambda:self.manager.get(job['id'])['status'] not in ('running','queued'))
        self.assertEqual(self.manager.get(job['id'])['status'],'completed')
        result=self.request('/api/structures/'+record['id']+'/conservation?chain=A')
        self.assertEqual(result['result']['source'],'prepared')
        self.assertEqual(result['result']['sequence_count'],3)

    def test_rejects_wrong_alignment_and_detects_changed_structure(self):
        record=self.app.register(self.fixture,'Fixture','reference')
        with self.assertRaises(HTTPError) as error:
            self.request('/api/conservation',dict(structure_id=record['id'],chain='A',source='upload',
                method='entropy',alignment='>query\nAAA\n>one\nAAC\n>two\nAAD\n'))
        self.assertEqual(error.exception.code,400)
        job=self.request('/api/conservation',dict(structure_id=record['id'],chain='A',source='upload',
            method='entropy',alignment='>query\nACD\n>one\nACE\n>two\nACF\n'))
        wait_until(lambda:self.manager.get(job['id'])['status']=='completed')
        self.fixture.write_text(self.fixture.read_text()+'\n# changed\n')
        with self.assertRaises(HTTPError) as error:
            self.request('/api/structures/'+record['id']+'/conservation?chain=A')
        self.assertEqual(error.exception.code,400)


if __name__=='__main__':
    unittest.main()
