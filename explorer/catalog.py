"""Searchable catalog of the molecules in the local PDB snapshot and the CCD.

Proteins, DNA, and RNA come from every entry in <db_dir>/mmcif_files, grouped by
identical sequence. Ligands and ions come from the Chemical Component Dictionary
installed with AlphaFold 3, ranked by how many PDB entries contain them.
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import re
import site
import sqlite3
import threading

from alphafold3.cpp import cif_dict

VERSION = 1
POLYMER_KINDS = {'polypeptide(L)':'protein', 'polydeoxyribonucleotide':'dna', 'polyribonucleotide':'rna'}
KINDS = ('protein', 'dna', 'rna', 'ligand', 'ion')
IGNORED_CODES = {'HOH', 'DOD', 'UNX', 'UNL', 'UNK'}
# Buffer, cryoprotectant, and crystallization components. Shown unselected when
# adding a whole PDB entry, because they are rarely part of the biology.
ADDITIVES = set('''GOL EDO SO4 PO4 PEG PGE PG4 1PE P6G 12P 15P PE4 PE8 ACT ACY DMS MPD FMT CL NA K IOD
    BR NO3 IMD TRS EPE MES BME CIT FLC SCN NH4 MLI TLA BTB CO3 AZI HEZ BU3 TAR IPA EOH MOH DTT B3P
    CAC NHE MRD PEU 2PE 7PE XPE BCN SIN MAL GAI'''.split())
SEQUENCE = re.compile(r'[A-Za-z\s]{20,}')


def ccd_path():
    for directory in site.getsitepackages():
        path = Path(directory) / 'share/libcifpp/components.cif'
        if path.is_file():
            return path
    return None


def _block(text, category):
    """One mmCIF category, from the '#' line before it to the '#' line after it."""
    i = text.find('\n' + category + '.')
    if i < 0:
        return ''
    end = text.find('\n#', i)
    return text[text.rfind('\n#', 0, i) + 1:end if end >= 0 else len(text)] + '\n'


def read_entry(path):
    """Molecules in one PDB entry, reading only the start and end of the file."""
    with open(path, 'rb') as f:
        head = b''
        while b'\n_struct_keywords.' not in head:
            chunk = f.read(32768)
            if not chunk:
                break
            head += chunk
        size = f.seek(0, 2)
        f.seek(max(0, size - 65536))
        tail = f.read().decode(errors='replace')
        if '\n_pdbx_entity_nonpoly.' not in tail and size > 65536:
            f.seek(max(0, size - 1_000_000))
            tail = f.read().decode(errors='replace')
    head = head.decode(errors='replace')
    cif = cif_dict.from_string('data_entry\n' + _block(head, '_entity') + _block(head, '_entity_poly')
        + _block(head, '_struct') + _block(tail, '_pdbx_entity_nonpoly'))
    poly = {e: (t, s, c) for e, t, s, c in zip(cif.get('_entity_poly.entity_id', []), cif.get('_entity_poly.type', []),
        cif.get('_entity_poly.pdbx_seq_one_letter_code_can', []), cif.get('_entity_poly.pdbx_strand_id', []))}
    codes = dict(zip(cif.get('_pdbx_entity_nonpoly.entity_id', []), cif.get('_pdbx_entity_nonpoly.comp_id', [])))
    molecules, skipped = [], []
    for entity, kind, name, count in zip(cif.get('_entity.id', []), cif.get('_entity.type', []),
            cif.get('_entity.pdbx_description', []), cif.get('_entity.pdbx_number_of_molecules', [])):
        copies = int(count) if count.isdigit() else 1
        if kind == 'polymer' and entity in poly:
            poly_type, sequence, chains = poly[entity]
            sequence = ''.join(sequence.split()).upper()
            if poly_type in POLYMER_KINDS and sequence and sequence != '?':
                molecules.append(dict(kind=POLYMER_KINDS[poly_type], name=name, sequence=sequence,
                    copies=max(1, len([c for c in chains.split(',') if c.strip()]))))
            else:
                skipped.append(f'{name} ({poly_type})')
        elif kind == 'non-polymer' and codes.get(entity) and codes[entity] not in IGNORED_CODES:
            molecules.append(dict(kind='ligand', name=name, code=codes[entity], copies=copies))
        elif kind == 'branched':
            skipped.append(f'{name} (glycan)')
    return dict(pdb_id=Path(path).stem.upper(), title=(cif.get('_struct.title') or [''])[0], molecules=molecules, skipped=skipped)


def read_ccd(path):
    """(code, name, kind, formula, synonyms) for each current CCD component."""
    text = Path(path).read_text(errors='replace')
    position = text.find('data_')
    while position >= 0:
        start = text.find('\n#', position)
        end = text.find('\n#', start + 2)
        following = text.find('\ndata_', position + 5)
        cif = cif_dict.from_string('data_x\n' + text[start + 1:end] + '\n')
        get = lambda key: (cif.get('_chem_comp.' + key) or ['?'])[0]
        position = following + 1 if following >= 0 else -1
        if get('pdbx_release_status') == 'OBS' or get('id') in IGNORED_CODES:
            continue
        formula, charge = get('formula'), get('pdbx_formal_charge')
        ion = re.fullmatch(r'[A-Z][a-z]?', formula) and charge not in ('0', '?')
        yield get('id'), get('name'), get('type'), 'ion' if ion else 'ligand', formula, get('pdbx_synonyms')


class Catalog:
    def __init__(self, db_dir, path):
        self.db_dir, self.path = Path(db_dir), Path(path)
        self.lock = threading.Lock()
        self.state = dict(state='ready' if self.current() else 'missing', progress=0, message='')

    def current(self):
        if not self.path.is_file():
            return False
        try:
            with sqlite3.connect(f'file:{self.path}?mode=ro', uri=True) as con:
                meta = dict(con.execute('SELECT key, value FROM meta'))
            return meta.get('version') == str(VERSION) and meta.get('db_dir') == str(self.db_dir)
        except sqlite3.Error:
            return False

    def status(self):
        with self.lock:
            state = dict(self.state)
        if state['state'] == 'ready':
            with sqlite3.connect(f'file:{self.path}?mode=ro', uri=True) as con:
                state['counts'] = dict(con.execute('SELECT kind, COUNT(*) FROM molecules GROUP BY kind'))
                state['entries'] = int(dict(con.execute('SELECT key, value FROM meta'))['entries'])
        return state

    def build_in_background(self, force=False):
        with self.lock:
            start = self.state['state'] != 'building' and (force or self.state['state'] != 'ready')
            if start:
                self.state = dict(state='building', progress=0, message='Starting the molecule catalog…')
        if start:
            threading.Thread(target=self._build, daemon=True).start()
        return self.status()

    def _progress(self, fraction, message):
        with self.lock:
            self.state.update(progress=round(fraction, 3), message=message)

    def _build(self):
        try:
            self.build()
            with self.lock:
                self.state = dict(state='ready', progress=1, message='')
        except Exception as error:
            with self.lock:
                self.state = dict(state='error', progress=0, message=f'Could not build the molecule catalog: {error}')

    def build(self):
        polymers, ligand_entries, entries = {}, Counter(), 0
        files = sorted((self.db_dir / 'mmcif_files').glob('*.cif'))
        def read(path):
            try:
                return read_entry(path)
            except Exception:
                return None
        with ThreadPoolExecutor(16) as pool:
            for i, entry in enumerate(pool.map(read, files)):
                if i % 2000 == 0:
                    self._progress(.9 * i / max(1, len(files)), f'Reading PDB entries ({i:,} of {len(files):,})')
                if not entry:
                    continue
                entries += 1
                for molecule in entry['molecules']:
                    if molecule['kind'] == 'ligand':
                        ligand_entries[molecule['code']] += 1
                        continue
                    group = polymers.setdefault((molecule['kind'], molecule['sequence']), dict(names=Counter(), entries=0, examples=[], titles=set()))
                    group['names'][molecule['name']] += 1
                    group['entries'] += 1
                    if len(group['examples']) < 5 and entry['pdb_id'] not in (e[0] for e in group['examples']):
                        group['examples'].append((entry['pdb_id'], entry['title']))
                    if len(group['titles']) < 20:
                        group['titles'].add(entry['title'])
        self._progress(.92, 'Reading the chemical component dictionary…')
        temp = self.path.with_name(self.path.name + '.tmp')
        temp.unlink(missing_ok=True)
        with sqlite3.connect(temp) as con:
            con.executescript('''
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE molecules(id INTEGER PRIMARY KEY, kind TEXT, name TEXT, sequence TEXT, code TEXT,
                    formula TEXT, length INTEGER, entries INTEGER, examples TEXT, popularity REAL);
                CREATE VIRTUAL TABLE search USING fts5(name, context, tokenize='unicode61 remove_diacritics 2');''')
            rows = []
            for (kind, sequence), group in polymers.items():
                # Prefer a mixed-case name over the all-caps style of older entries.
                names = group['names'].most_common()
                name = next((n for n, _ in names if n != n.upper()), names[0][0])
                rows.append((kind, name, sequence, None, None, len(sequence), group['entries'], json.dumps(group['examples']),
                    name, ' '.join(sorted(group['titles']))))
            path = ccd_path()
            for code, name, ccd_type, kind, formula, synonyms in (read_ccd(path) if path else []):
                if 'LINKING' in ccd_type.upper() and not ligand_entries[code]:
                    continue
                # Common names such as "heme" are often CCD synonyms, so search them as names.
                rows.append((kind, name, None, code, formula, None, ligand_entries[code], '[]',
                    name + ' ' + ('' if synonyms == '?' else synonyms), code))
            self._progress(.97, 'Writing the search index…')
            for i, row in enumerate(rows, 1):
                con.execute('INSERT INTO molecules VALUES (?,?,?,?,?,?,?,?,?,?)', (i, *row[:8], math.log1p(row[6])))
                con.execute('INSERT INTO search(rowid, name, context) VALUES (?,?,?)', (i, row[8], row[9]))
            con.execute('CREATE INDEX molecules_kind ON molecules(kind, entries DESC)')
            con.execute('CREATE INDEX molecules_sequence ON molecules(sequence)')
            con.execute('CREATE INDEX molecules_code ON molecules(code)')
            con.executemany('INSERT INTO meta VALUES (?,?)', [('version', str(VERSION)), ('db_dir', str(self.db_dir)), ('entries', str(entries))])
        temp.replace(self.path)

    def search(self, text='', kind='', offset=0, limit=30):
        status = self.status()
        if status['state'] != 'ready':
            return dict(status=status, results=[], more=False, entry=None)
        text, kind = text.strip()[:2000], kind if kind in KINDS else ''
        where, params = ('AND m.kind = ?', [kind]) if kind else ('', [])
        entry = None
        with sqlite3.connect(f'file:{self.path}?mode=ro', uri=True) as con:
            con.row_factory = sqlite3.Row
            if re.fullmatch(r'\d[A-Za-z0-9]{3}', text) and (self.db_dir / 'mmcif_files' / (text.lower() + '.cif')).is_file():
                entry = text.upper()
            if not text:
                if kind:
                    rows = con.execute(f'SELECT * FROM molecules m WHERE 1 {where} ORDER BY entries DESC LIMIT ? OFFSET ?', (*params, limit + 1, offset)).fetchall()
                else:
                    rows = [r for k in KINDS for r in con.execute('SELECT * FROM molecules WHERE kind = ? ORDER BY entries DESC LIMIT 4', (k,))]
                    return dict(status=status, results=[self._row(r) for r in rows], more=False, entry=None)
            elif SEQUENCE.fullmatch(text):
                sequence = ''.join(text.split()).upper()
                rows = con.execute(f'SELECT * FROM molecules m WHERE sequence = ? {where}', (sequence, *params)).fetchall()
            else:
                tokens = re.findall(r'\w+', text.lower())
                query = ' '.join(f'"{t}"*' for t in tokens)
                rows = [] if not tokens else con.execute(f'''SELECT m.* FROM search JOIN molecules m ON m.id = search.rowid
                    WHERE search MATCH ? {where} ORDER BY bm25(search, 8.0, 1.0) - m.popularity * 1.2 LIMIT ? OFFSET ?''',
                    (query, *params, limit + 1, offset)).fetchall()
                # A typed CCD code such as ATP or MG goes first, unless the code is rare
                # and probably an accident (P53 is a ligand, but "p53" means the protein).
                if offset == 0 and re.fullmatch(r'\w{1,5}', text):
                    exact = con.execute(f'SELECT * FROM molecules m WHERE code = ? {where}', (text.upper(), *params)).fetchone()
                    if exact and (exact['entries'] >= 20 or kind in ('ligand', 'ion')):
                        rows = [exact] + [r for r in rows if r['id'] != exact['id']]
        return dict(status=status, results=[self._row(r) for r in rows[:limit]], more=len(rows) > limit, entry=entry)

    @staticmethod
    def _row(row):
        return dict(kind=row['kind'], name=row['name'], sequence=row['sequence'], code=row['code'], formula=row['formula'],
            length=row['length'], entries=row['entries'], examples=json.loads(row['examples']))

    def entry(self, pdb_id):
        if not re.fullmatch(r'\d[A-Za-z0-9]{3}', pdb_id):
            raise ValueError('Enter a four-character PDB ID, such as 1QPI.')
        path = self.db_dir / 'mmcif_files' / (pdb_id.lower() + '.cif')
        if not path.is_file():
            raise ValueError('This PDB entry is not in your local September 2022 snapshot.')
        entry = read_entry(path)
        codes = [m['code'] for m in entry['molecules'] if m['kind'] == 'ligand']
        known = {}
        if codes and self.current():
            with sqlite3.connect(f'file:{self.path}?mode=ro', uri=True) as con:
                known = {code: (kind, formula) for code, kind, formula in con.execute(
                    f'SELECT code, kind, formula FROM molecules WHERE code IN ({",".join("?" * len(codes))})', codes)}
        for molecule in entry['molecules']:
            if molecule['kind'] == 'ligand':
                molecule['kind'], molecule['formula'] = known.get(molecule['code'], ('ligand', None))
            molecule['selected'] = molecule.get('code') not in ADDITIVES
        return entry
