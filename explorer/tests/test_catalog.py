"""Molecule catalog: reading PDB entries and the CCD, grouping, search, and entry views."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from explorer import catalog
from explorer.catalog import Catalog, read_entry

PROTEIN = 'MKTAYIAKQRQISFVKSHFSRQLEE'


def entry_text(code, title, polymers, ligands):
    entities = [(str(i + 1), 'polymer', name, str(copies)) for i, (_, name, _, copies) in enumerate(polymers)]
    entities += [(str(len(polymers) + i + 1), 'non-polymer', f"'{name}'", '1') for i, (_, name) in enumerate(ligands)]
    entities.append((str(len(entities) + 1), 'water', 'water', '10'))
    poly_rows = [f"{i + 1} '{kind}' {sequence} {','.join('ABCDEFGH'[:copies])}" for i, (kind, _, sequence, copies) in enumerate(polymers)]
    nonpoly_rows = [f"{len(polymers) + i + 1} '{name}' {code_}" for i, (code_, name) in enumerate(ligands)]
    nonpoly_rows.append(f'{len(entities)} water HOH')
    return f'''data_{code}
#
_entry.id {code}
#
loop_
_entity.id
_entity.type
_entity.pdbx_description
_entity.pdbx_number_of_molecules
{chr(10).join(' '.join(e) for e in entities)}
#
loop_
_entity_poly.entity_id
_entity_poly.type
_entity_poly.pdbx_seq_one_letter_code_can
_entity_poly.pdbx_strand_id
{chr(10).join(poly_rows)}
#
_struct.entry_id {code}
_struct.title '{title}'
#
_struct_keywords.entry_id {code}
#
loop_
_pdbx_entity_nonpoly.entity_id
_pdbx_entity_nonpoly.name
_pdbx_entity_nonpoly.comp_id
{chr(10).join(nonpoly_rows)}
#
'''


def ccd_text(*components):
    return ''.join(f'''data_{code}
#
_chem_comp.id {code}
_chem_comp.name '{name}'
_chem_comp.type '{kind}'
_chem_comp.formula '{formula}'
_chem_comp.pdbx_synonyms '{synonyms}'
_chem_comp.pdbx_formal_charge {charge}
_chem_comp.pdbx_release_status {status}
#
_chem_comp_atom.comp_id {code}
#
''' for code, name, kind, formula, synonyms, charge, status in components)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db = root / 'db'
        (self.db / 'mmcif_files').mkdir(parents=True)
        (self.db / 'mmcif_files' / '1abc.cif').write_text(entry_text('1ABC', 'Repressor bound to operator DNA',
            [('polypeptide(L)', "'Tet repressor'", PROTEIN, 2), ('polydeoxyribonucleotide', "'Operator DNA'", 'ACGTACGT', 1)],
            [('MG', 'MAGNESIUM ION'), ('GOL', 'GLYCEROL')]))
        (self.db / 'mmcif_files' / '2xyz.cif').write_text(entry_text('2XYZ', 'Repressor with a riboswitch',
            [('polypeptide(L)', "'TET REPRESSOR'", PROTEIN, 1), ('polyribonucleotide', "'Riboswitch'", 'GGACUU', 1)],
            [('HEM', 'PROTOPORPHYRIN IX CONTAINING FE')]))
        ccd = root / 'components.cif'
        ccd.write_text(ccd_text(
            ('MG', 'MAGNESIUM ION', 'NON-POLYMER', 'Mg', '?', '2', 'REL'),
            ('GOL', 'GLYCEROL', 'NON-POLYMER', 'C3 H8 O3', 'GLYCERIN', '0', 'REL'),
            ('HEM', 'PROTOPORPHYRIN IX CONTAINING FE', 'NON-POLYMER', 'C34 H32 Fe N4 O4', 'HEME', '0', 'REL'),
            ('XYZ', 'RETIRED COMPONENT', 'NON-POLYMER', 'C H4', '?', '0', 'OBS'),
            ('ALA', 'ALANINE', 'L-PEPTIDE LINKING', 'C3 H7 N O2', '?', '0', 'REL')))
        patcher = mock.patch.object(catalog, 'ccd_path', return_value=ccd)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.catalog = Catalog(self.db, root / 'molecules.sqlite')
        self.catalog.build()
        self.catalog.state['state'] = 'ready'

    def tearDown(self):
        self.temp.cleanup()

    def test_reads_polymers_ligands_and_skips_water(self):
        entry = read_entry(self.db / 'mmcif_files' / '1abc.cif')
        self.assertEqual(entry['title'], 'Repressor bound to operator DNA')
        self.assertEqual([(m['kind'], m.get('sequence') or m.get('code'), m['copies']) for m in entry['molecules']],
            [('protein', PROTEIN, 2), ('dna', 'ACGTACGT', 1), ('ligand', 'MG', 1), ('ligand', 'GOL', 1)])

    def test_groups_identical_sequences_and_counts_ccd_components(self):
        status = self.catalog.status()
        self.assertEqual(status['entries'], 2)
        self.assertEqual(status['counts'], {'protein': 1, 'dna': 1, 'rna': 1, 'ion': 1, 'ligand': 2})
        protein = self.catalog.search('repressor', 'protein')['results'][0]
        self.assertEqual(protein['name'], 'Tet repressor')
        self.assertEqual(protein['entries'], 2)
        self.assertEqual([e[0] for e in protein['examples']], ['1ABC', '2XYZ'])

    def test_search_by_synonym_category_sequence_and_pdb_id(self):
        self.assertEqual(self.catalog.search('heme')['results'][0]['code'], 'HEM')
        self.assertEqual([r['code'] for r in self.catalog.search('', 'ion')['results']], ['MG'])
        self.assertEqual(self.catalog.search(PROTEIN.lower())['results'][0]['kind'], 'protein')
        self.assertEqual(self.catalog.search('riboswitch', 'rna')['results'][0]['sequence'], 'GGACUU')
        self.assertEqual(self.catalog.search('1abc')['entry'], '1ABC')
        self.assertEqual(self.catalog.search('repressor', 'ligand')['results'], [])

    def test_existing_catalog_is_reused_at_startup(self):
        reopened = Catalog(self.db, self.catalog.path)
        self.assertEqual(reopened.build_in_background()['state'], 'ready')
        self.assertEqual(Catalog(self.db / 'elsewhere', self.catalog.path).status()['state'], 'missing')

    def test_entry_marks_additives_and_ion_kinds(self):
        entry = self.catalog.entry('1abc')
        ligands = {m['code']: m for m in entry['molecules'] if 'code' in m}
        self.assertEqual(ligands['MG']['kind'], 'ion')
        self.assertTrue(ligands['MG']['selected'])
        self.assertFalse(ligands['GOL']['selected'])
        with self.assertRaises(ValueError):
            self.catalog.entry('9zzz')


if __name__ == '__main__':
    unittest.main()
