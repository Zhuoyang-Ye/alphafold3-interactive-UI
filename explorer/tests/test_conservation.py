"""Conservation score meaning, alignment projection, and residue-map regressions."""
import copy
import math
import unittest

from alphafold3.cpp import cif_dict
from explorer.analysis import parse_structure
from explorer.conservation import (read_alignment, select_homologues, entropy_profile,
    parse_rate4site, add_rate_percentiles, map_profile, interface_comparison)
from test_explorer import cif_text


class ConservationTests(unittest.TestCase):
    def test_a3m_insertions_and_aligned_fasta_query_gaps_are_removed(self):
        a3m='>query\nACDE\n>one\nACqqDE\n>two\nA-rtDE\n'
        self.assertEqual(read_alignment(a3m,'ACDE','a3m')[1][1],'ACDE')
        self.assertEqual(read_alignment(a3m,'ACDE','a3m')[2][1],'A-DE')
        fasta='>other\nAVCE\n>query\nA-CD\n'
        projected=read_alignment(fasta,'ACD','fasta')
        self.assertEqual(projected,[('query','ACD'),('other','ACE')])

    def test_stockholm_blocks_preserve_query_positions(self):
        stockholm='# STOCKHOLM 1.0\nquery AC-D\none ACTD\n\nquery E\none E\n//\n'
        projected=read_alignment(stockholm,'ACDE','stockholm')
        self.assertEqual(projected[0][1],'ACDE')
        self.assertEqual(projected[1][1],'ACDE')

    def test_rejects_unaligned_and_wrong_query_inputs(self):
        for alignment in ['>q\nACD\n>one\nACDE\n','>q\nACE\n>one\nACF\n','ACD\nACE','>q\nAC*\n']:
            with self.assertRaises(ValueError):
                read_alignment(alignment,'ACD','fasta')

    def test_filter_deduplicates_and_cannot_score_a_query_alone(self):
        records=[('query','ACDE'),('copy','ACDE'),('short','A---'),('different','YYYY'),('one','ACDA'),('two','ACDD')]
        selected,stats=select_homologues(records)
        self.assertEqual(len(selected),3)
        self.assertEqual(stats['duplicates'],1)
        self.assertEqual(stats['low_coverage'],1)
        self.assertEqual(stats['low_identity'],1)
        with self.assertRaisesRegex(ValueError,'three'):
            select_homologues(records[:3])

    def test_entropy_matches_known_distributions_and_masks_unsupported_columns(self):
        selected=[dict(name=str(i),sequence=s) for i,s in enumerate(['ACDE','ACDA','ACDD','ACDG'])]
        rows,effective=entropy_profile(selected)
        self.assertEqual(effective,4)
        self.assertEqual(rows[0]['entropy_conservation'],1)
        self.assertAlmostEqual(rows[3]['entropy_conservation'],1-2/math.log2(20),places=5)
        sparse=entropy_profile([dict(sequence=s) for s in ['ACD','AC-','AC-']])[0]
        self.assertFalse(sparse[2]['enough_data'])
        self.assertAlmostEqual(sparse[2]['coverage'],1/3,places=4)
        uniform=entropy_profile([dict(sequence='A'+aa) for aa in 'ACDEFGHIKLMNPQRSTVWY'])[0]
        self.assertAlmostEqual(uniform[1]['entropy_conservation'],0,places=5)

    def test_position_based_weights_reduce_duplicate_sequence_influence(self):
        rows,effective=entropy_profile([dict(sequence=s) for s in ['ACDA','ACDA','ACDA','ACDE']])
        self.assertLess(effective,4)
        self.assertGreater(rows[-1]['entropy_bits'],.811)

    def test_rate4site_parser_retains_posterior_intervals_and_rank_direction(self):
        text='#POS SEQ SCORE QQ-INTERVAL STD MSA DATA\n1 A -1.2 [-1.5,-0.8] 0.3 3/3\n2 C 0.0 [-.2,0.3] 0.2 3/3\n3 D 1.2 [0.8,1.8] 0.4 3/3\n'
        # Rate4Site emits leading zeroes on fractional numbers.
        text=text.replace('[-.2','[-0.2')
        rates=parse_rate4site(text,'ACD')
        rows=entropy_profile([dict(sequence=s) for s in ['ACD','ACE','ACF']])[0]
        add_rate_percentiles(rows,rates)
        self.assertEqual([r['score'] for r in rows],[1.,.5,0.])
        self.assertEqual(rows[0]['rate_interval'],[-1.5,-.8])
        with self.assertRaises(ValueError):
            parse_rate4site(text,'ACE')
        with self.assertRaises(ValueError):
            parse_rate4site(text.replace('3 D','3 X'),'ACD')

    def test_missing_coordinates_do_not_shift_conservation_scores(self):
        text=cif_text([('A','1','ALA','CA','C',0,0,0),('A','3','ASP','CA','C',1,0,0)])
        cif=cif_dict.from_string(text).copy_and_update({'_entity_poly.pdbx_seq_one_letter_code_can':['ACD']})
        structure=parse_structure(cif.to_string())
        rows=[dict(aa=aa,position=i+1,score=score,coverage=1,enough_data=True) for i,(aa,score) in enumerate(zip('ACD',[.1,.5,.9]))]
        residues,mapped=map_profile(structure,'A',rows)
        self.assertEqual(mapped,2)
        self.assertEqual([(r['resi'],r['query_position'],r['score']) for r in residues],[(1,1,.1),(2,3,.9)])
        wrong=copy.deepcopy(rows);wrong[0]['aa']='G'
        with self.assertRaises(ValueError):
            map_profile(structure,'A',wrong)

    def test_interface_summary_counts_unique_residues_and_masks_missing_scores(self):
        profile=dict(chain='A',residues=[dict(resi=1,score=.9),dict(resi=2,score=.2),dict(resi=3,score=None)])
        contact_data=dict(cutoff=4.5,rows=[
            dict(left=dict(chain='A',resi=1),right=dict(chain='B',resi=1)),
            dict(left=dict(chain='A',resi=1),right=dict(chain='B',resi=2)),
            dict(left=dict(chain='A',resi=3),right=dict(chain='B',resi=3)),
            dict(left=dict(chain='A',resi=2),right=dict(chain='C',resi=1))])
        result=interface_comparison(profile,contact_data,'B')
        self.assertEqual(result['contact_residues'],2)
        self.assertEqual(result['interface']['count'],1)
        self.assertEqual(result['interface']['mean'],.9)
        self.assertEqual(result['other_residues']['mean'],.2)
        self.assertEqual(result['difference'],.7)


if __name__=='__main__':
    unittest.main()
