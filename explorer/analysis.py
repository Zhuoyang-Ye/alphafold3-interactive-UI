"""Read actual coordinates and calculate geometric inter-chain contacts."""
from collections import defaultdict
from itertools import product
import math

import numpy as np
from alphafold3.cpp import cif_dict

AMINO_ACIDS = dict(zip(
    'ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split(),
    'ARNDCQEGHILKMFPSTWYV'))
AMINO_ACIDS.update(MSE='M', SEP='S', TPO='T', PTR='Y', HYP='P', SEC='U', PYL='O')


def parse_structure(text, predicted=False):
    cif = cif_dict.from_string(text)
    xs = cif.get('_atom_site.Cartn_x', [])
    if not xs:
        raise ValueError('This mmCIF has no atom coordinates.')
    if len(xs) > 200_000:
        raise ValueError('Please use a structure with fewer than 200,000 atoms.')
    n = len(xs)
    def col(name, default='?'):
        return cif.get('_atom_site.' + name, [default] * n)
    columns = {k: col(k) for k in ['Cartn_y', 'Cartn_z', 'label_asym_id',
        'label_comp_id', 'label_atom_id', 'type_symbol', 'label_seq_id',
        'auth_seq_id', 'auth_asym_id', 'pdbx_PDB_ins_code', 'B_iso_or_equiv',
        'label_alt_id', 'pdbx_PDB_model_num', 'label_entity_id']}
    entity_names = dict(zip(cif.get('_entity.id', []), cif.get('_entity.pdbx_description', [])))
    entity_types = dict(zip(cif.get('_entity.id', []), cif.get('_entity.type', [])))
    poly_types = dict(zip(cif.get('_entity_poly.entity_id', []), cif.get('_entity_poly.type', [])))
    poly_sequences = {entity: ''.join(sequence.split()).upper() for entity, sequence in zip(
        cif.get('_entity_poly.entity_id', []), cif.get('_entity_poly.pdbx_seq_one_letter_code_can', []))}
    scheme_ids = cif.get('_pdbx_poly_seq_scheme.seq_id', [])
    scheme_map = dict(zip(zip(cif.get('_pdbx_poly_seq_scheme.asym_id', []),
        cif.get('_pdbx_poly_seq_scheme.auth_seq_num', []),
        cif.get('_pdbx_poly_seq_scheme.pdb_ins_code', ['.'] * len(scheme_ids))), scheme_ids))
    first_model = columns['pdbx_PDB_model_num'][0]
    atoms, chains, residues, seen = [], {}, {}, set()
    for i, x in enumerate(xs):
        c = {k: v[i] for k, v in columns.items()}
        if c['pdbx_PDB_model_num'] != first_model or c['type_symbol'] in ('H', 'D'):
            continue
        if c['label_comp_id'] in ('HOH', 'DOD', 'WAT'):
            continue
        if c['label_alt_id'] not in ('.', '?', 'A', '1'):
            continue
        chain = c['label_asym_id']
        if chain in ('.', '?'):
            chain = c['auth_asym_id']
        seq = c['label_seq_id']
        if seq in ('.', '?'):
            seq = c['auth_seq_id']
        insertion = '' if c['pdbx_PDB_ins_code'] in ('.', '?') else c['pdbx_PDB_ins_code']
        key = (chain, seq, insertion, c['label_comp_id'])
        atom_key = (*key, c['label_atom_id'])
        if atom_key in seen:
            continue
        seen.add(atom_key)
        xyz = [float(x), float(c['Cartn_y']), float(c['Cartn_z'])]
        if not all(math.isfinite(v) for v in xyz):
            raise ValueError('Atom coordinates must be finite numbers.')
        if chain not in chains:
            entity = c['label_entity_id']
            chains[chain] = dict(id=chain, name=entity_names.get(entity, chain),
                kind=poly_types.get(entity, entity_types.get(entity, 'unknown')),
                residues=0, atoms=0, author_id=c['auth_asym_id'],
                sequence=poly_sequences.get(entity), sequence_source='polymer sequence')
        if key not in residues:
            chains[chain]['residues'] += 1
            query_position = c['label_seq_id'] if c['label_seq_id'].isdigit() else scheme_map.get((chain, c['auth_seq_id'], insertion or '.'), '')
            residues[key] = dict(chain=chain, resi=chains[chain]['residues'],
                name=c['label_comp_id'], label=seq + insertion,
                author_label=c['auth_seq_id'] + insertion,
                query_position=int(query_position) if query_position.isdigit() and int(query_position)>0 else None)
        residue = residues[key]
        b = c['B_iso_or_equiv']
        atom = dict(x=xyz[0], y=xyz[1], z=xyz[2], elem=c['type_symbol'],
            atom=c['label_atom_id'], chain=chain, resi=residue['resi'],
            resn=c['label_comp_id'], b=float(b) if b not in ('.', '?') else 0,
            residue_label=residue['label'])
        atoms.append(atom)
        chains[chain]['atoms'] += 1
    if not atoms:
        raise ValueError('No non-water heavy atoms were found in the first model.')
    for chain in chains.values():
        chain['plddt'] = round(float(np.mean([a['b'] for a in atoms if a['chain'] == chain['id']])), 1) if predicted else None
        if 'polypeptide' in chain['kind'] or (chain['kind'] == 'polymer' and any(a['atom'] == 'CA' for a in atoms if a['chain'] == chain['id'])):
            chain_residues = [r for r in residues.values() if r['chain'] == chain['id']]
            if not chain['sequence']:
                chain['sequence'] = ''.join(AMINO_ACIDS.get(r['name'], 'X') for r in chain_residues)
                chain['sequence_source'] = 'resolved residues only'
                for i, residue in enumerate(chain_residues, 1):
                    residue['query_position'] = i
            for residue in chain_residues:
                pos = residue['query_position']
                if pos is not None and (not 1 <= pos <= len(chain['sequence']) or
                    (chain['sequence'][pos-1] != 'X' and AMINO_ACIDS.get(residue['name'], 'X') not in (chain['sequence'][pos-1], 'X'))):
                    residue['query_position'] = None
        else:
            chain['sequence'] = None
    return dict(title=' '.join(cif.get('_struct.title', [cif.get_data_name()])),
        atoms=atoms, chains=list(chains.values()), residues=list(residues.values()),
        atom_count=len(atoms), residue_count=len(residues), predicted=predicted)


def viewer_cif(structure):
    """Normalize chain/residue IDs so viewer selections match contact analysis.

    The original mmCIF remains available as an unchanged download. This view
    contains first-model heavy atoms, with unique consecutive residue numbers.
    """
    atoms = structure['atoms']
    fields = {
        'group_PDB': ['ATOM' if len(a['resn']) == 3 and a['atom'] in ('N','CA','C','O') else 'HETATM' for a in atoms],
        'id': [str(i+1) for i in range(len(atoms))],
        'type_symbol': [a['elem'] for a in atoms],
        'label_atom_id': [a['atom'] for a in atoms],
        'label_comp_id': [a['resn'] for a in atoms],
        'label_asym_id': [a['chain'] for a in atoms],
        'auth_asym_id': [a['chain'] for a in atoms],
        'label_seq_id': [str(a['resi']) for a in atoms],
        'auth_seq_id': [str(a['resi']) for a in atoms],
        'Cartn_x': [str(a['x']) for a in atoms],
        'Cartn_y': [str(a['y']) for a in atoms],
        'Cartn_z': [str(a['z']) for a in atoms],
        'B_iso_or_equiv': [str(a['b']) for a in atoms],
        'occupancy': ['1'] * len(atoms),
        'label_alt_id': ['.'] * len(atoms),
        'pdbx_PDB_ins_code': ['?'] * len(atoms),
        'pdbx_PDB_model_num': ['1'] * len(atoms),
    }
    # Mark all atoms of polymer chains consistently for cartoon rendering.
    polymer = {c['id'] for c in structure['chains'] if 'polypeptide' in c['kind'] or 'ribonucleotide' in c['kind'] or c['kind'] == 'polymer'}
    fields['group_PDB'] = ['ATOM' if a['chain'] in polymer else 'HETATM' for a in atoms]
    return cif_dict.CifDict({'data_': ['explorer_view'], **{'_atom_site.'+k: v for k,v in fields.items()}}).to_string()


def contacts(structure, cutoff=4.5):
    """One row per residue pair; minimum heavy-atom distance, no affinity claim."""
    if not 2 <= cutoff <= 8 or not math.isfinite(cutoff):
        raise ValueError('Contact distance must be between 2 and 8 Å.')
    atoms = structure['atoms']
    grid, pairs = defaultdict(list), {}
    cutoff2 = cutoff * cutoff
    for a in atoms:
        cell = tuple(math.floor(a[k] / cutoff) for k in ('x', 'y', 'z'))
        for delta in product((-1, 0, 1), repeat=3):
            for b in grid[tuple(cell[j] + delta[j] for j in range(3))]:
                if a['chain'] == b['chain']:
                    continue
                distance2 = sum((a[k] - b[k]) ** 2 for k in ('x', 'y', 'z'))
                if distance2 > cutoff2:
                    continue
                left, right = sorted((a, b), key=lambda v: (v['chain'], v['resi']))
                key = (left['chain'], left['resi'], right['chain'], right['resi'])
                if key not in pairs or distance2 < pairs[key][0]:
                    pairs[key] = (distance2, left, right)
        grid[cell].append(a)
    rows, counts = [], defaultdict(int)
    for distance2, left, right in sorted(pairs.values(), key=lambda x: x[0]):
        def endpoint(a):
            return {k: a[k] for k in ('chain','resi','resn','residue_label','atom','x','y','z')}
        rows.append(dict(left=endpoint(left), right=endpoint(right), distance=round(math.sqrt(distance2), 3)))
        counts[(left['chain'], right['chain'])] += 1
    return dict(cutoff=cutoff, count=len(rows), rows=rows,
        interfaces=[dict(left=a, right=b, contacts=n) for (a,b),n in sorted(counts.items())])


def align_structures(left, right, left_chain, right_chain):
    """Kabsch alignment for identically sequenced chains; never guess homology."""
    def backbone(s, chain):
        residues = [r for r in s['residues'] if r['chain'] == chain]
        atoms = [a for a in s['atoms'] if a['chain'] == chain and a['atom'] == 'CA']
        return residues, atoms
    lr, la = backbone(left, left_chain)
    rr, ra = backbone(right, right_chain)
    if len(la) < 3 or len(la) != len(ra) or [r['name'] for r in lr] != [r['name'] for r in rr]:
        raise ValueError('Alignment requires protein chains with the same resolved residue sequence and at least three Cα atoms. Choose matching chains.')
    p = np.array([[a[k] for k in ('x','y','z')] for a in la])
    q = np.array([[a[k] for k in ('x','y','z')] for a in ra])
    pc, qc = p.mean(axis=0), q.mean(axis=0)
    u, _, vt = np.linalg.svd((q-qc).T @ (p-pc))
    correction = np.eye(3)
    correction[2,2] = np.linalg.det(u @ vt)
    rotation = u @ correction @ vt
    translation = pc - qc @ rotation
    rmsd = np.sqrt(np.mean(np.sum((q @ rotation + translation - p)**2, axis=1)))
    return dict(rmsd=round(float(rmsd), 4), matched_atoms=len(p),
                rotation=rotation.tolist(), translation=translation.tolist())
