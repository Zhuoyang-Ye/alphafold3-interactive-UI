"""Local alignment conservation, Rate4Site inference, and structure mapping.

Rate4Site uses its published empirical-Bayes implementation. The optional fast
method uses Henikoff weights and normalized Shannon entropy; it is explicitly
labelled separately from evolutionary-rate inference.
"""
import argparse
from collections import OrderedDict
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from alphafold3.data import parsers
from explorer.analysis import parse_structure
from explorer.jobs import now, save_json

ALPHABET = 'ACDEFGHIKLMNPQRSTVWY'
VALID = set(ALPHABET)
DATABASE_NAMES = {'uniref90':'uniref90_2022_05.fa', 'pdb':'pdb_seqres_2022_09_28.fasta'}


def rate4site_binary(data_dir):
    configured = os.environ.get('RATE4SITE_BIN')
    if configured and Path(configured).is_file() and os.access(configured, os.X_OK):
        return str(Path(configured).resolve())
    bundled = Path(data_dir) / 'tools' / 'rate4site'
    return str(bundled) if bundled.is_file() and os.access(bundled, os.X_OK) else shutil.which('rate4site')


def read_alignment(text, query, format='auto'):
    if not isinstance(text, str) or len(text) > 50_000_000:
        raise ValueError('Supply an alignment smaller than 50 MB.')
    if format not in ('auto','a3m','fasta','stockholm'):
        raise ValueError('Choose A3M, aligned FASTA, or Stockholm.')
    if format == 'stockholm' or text.lstrip().startswith('# STOCKHOLM'):
        # The AF3 conversion preserves the query and removes insertion columns.
        text = parsers.convert_stockholm_to_a3m(io.StringIO(text), max_sequences=10_000)
        format = 'a3m'
    records, name, chunks = [], None, []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('>'):
            if name is not None:
                records.append((name, ''.join(chunks)))
            name, chunks = line[1:].strip() or 'Unnamed sequence', []
        elif name is None:
            raise ValueError('Alignments need FASTA headers (>query), or a Stockholm header.')
        else:
            chunks.append(''.join(line.split()))
    if name is not None:
        records.append((name, ''.join(chunks)))
    if not records:
        raise ValueError('The alignment is empty. Sequence-only AF3 runs do not contain homologous alignments.')
    if len(records) > 10_000:
        records = records[:10_000]
    if format == 'auto':
        format = 'a3m' if any(any(c.islower() for c in s) for _,s in records) else 'fasta'
    clean = []
    for name, sequence in records:
        if format == 'a3m':
            sequence = re.sub(r'[a-z.]', '', sequence)
        else:
            sequence = sequence.upper().replace('.', '-')
        if not sequence or re.search(r'[^A-Z-]', sequence):
            raise ValueError('An alignment row contains unsupported characters. Use protein letters and gaps.')
        clean.append((name, sequence))
    lengths = {len(s) for _,s in clean}
    if len(lengths) != 1:
        raise ValueError('Rows do not have equal aligned lengths. Supply an aligned FASTA/A3M file, not unaligned sequences.')
    candidates = [i for i,(_,s) in enumerate(clean) if s.replace('-', '') == query]
    if not candidates:
        raise ValueError('No alignment row matches this protein chain exactly. Include the full chain sequence as the query row.')
    query_index = candidates[0]
    clean.insert(0, clean.pop(query_index))
    keep = [i for i,c in enumerate(clean[0][1]) if c != '-']
    projected = [(name, ''.join(seq[i] for i in keep)) for name,seq in clean]
    if len(query) > 4096:
        raise ValueError('This local conservation workflow supports protein chains up to 4096 residues.')
    return projected


def select_homologues(records, max_sequences=150, min_coverage=.7, min_identity=.2, redundancy=.95):
    query = records[0][1]
    q = np.frombuffer(query.encode('ascii'), dtype='S1')
    canonical = np.isin(q, np.array(list(ALPHABET), dtype='S1'))
    candidates, seen = [], {query}
    stats = dict(input_sequences=len(records), duplicates=0, low_coverage=0, low_identity=0, redundant=0)
    for name, sequence in records[1:]:
        if sequence in seen:
            stats['duplicates'] += 1
            continue
        seen.add(sequence)
        row = np.frombuffer(sequence.encode('ascii'), dtype='S1')
        valid = np.isin(row, np.array(list(ALPHABET), dtype='S1')) & canonical
        coverage = float(valid.sum() / max(1, canonical.sum()))
        identity = float(((row == q) & valid).sum() / max(1, valid.sum()))
        if coverage < min_coverage:
            stats['low_coverage'] += 1
            continue
        if identity < min_identity:
            stats['low_identity'] += 1
            continue
        candidates.append(dict(name=name, sequence=sequence, identity=identity, coverage=coverage, row=row))
    # Keep one representative of near-identical aligned sequences. Start with
    # the most complete rows so fragments do not displace complete homologues.
    candidates.sort(key=lambda r: (r['identity'], r['name']))
    pool_limit=min(1200,max_sequences*4)
    if len(candidates)>pool_limit:
        indices=np.linspace(0,len(candidates)-1,pool_limit,dtype=int)
        stats['prefilter_sampled_out']=len(candidates)-pool_limit
        candidates=[candidates[i] for i in indices]
    candidates.sort(key=lambda r: (-r['coverage'], -r['identity'], r['name']))
    representatives, retained = [q], []
    valid_alphabet=np.array(list(ALPHABET),dtype='S1')
    representative_valid=[np.isin(q,valid_alphabet)]
    for candidate in candidates:
        row = candidate['row']
        row_valid=np.isin(row,valid_alphabet)
        rep_matrix=np.stack(representatives)
        valid=np.stack(representative_valid)&row_valid
        overlaps=valid.sum(axis=1)
        identities=((rep_matrix==row)&valid).sum(axis=1)/np.maximum(1,overlaps)
        duplicate=bool(np.any((overlaps>=min_coverage*len(query))&(identities>=redundancy)))
        if duplicate:
            stats['redundant'] += 1
        else:
            representatives.append(row)
            representative_valid.append(row_valid)
            retained.append(candidate)
    # Sample across similarity to the query instead of keeping only top hits.
    retained.sort(key=lambda r: (r['identity'], r['name']))
    if len(retained) > max_sequences - 1:
        indices = np.linspace(0, len(retained)-1, max_sequences-1, dtype=int)
        retained = [retained[i] for i in indices]
    selected = [dict(name=records[0][0], sequence=query, identity=1., coverage=1.)] + [
        {k:v for k,v in r.items() if k != 'row'} for r in retained]
    if len(selected) < 3:
        raise ValueError('Fewer than three distinct sequences remain after filtering. Use a broader alignment or database; a query alone cannot establish conservation.')
    stats.update(retained_sequences=len(selected), sampled_sequences=len(retained)+1,
        min_identity=min_identity, min_coverage=min_coverage, redundancy_identity=redundancy)
    return selected, stats


def entropy_profile(selected):
    matrix = np.array([list(r['sequence']) for r in selected], dtype='U1')
    counts = np.array([(matrix == aa).sum(axis=0) for aa in ALPHABET], dtype=float)
    variety = (counts > 0).sum(axis=0)
    weights = np.zeros(len(selected))
    for i,aa in enumerate(ALPHABET):
        denominator = variety * counts[i]
        contribution = np.divide(1., denominator, out=np.zeros_like(denominator), where=denominator>0)
        weights += ((matrix == aa) * contribution).sum(axis=1)
    if weights.sum() == 0:
        raise ValueError('The alignment contains no standard amino acids.')
    weights /= weights.sum()
    weighted_counts = np.array([((matrix == aa) * weights[:,None]).sum(axis=0) for aa in ALPHABET])
    observed_weight = weighted_counts.sum(axis=0)
    probabilities = np.divide(weighted_counts, observed_weight, out=np.zeros_like(weighted_counts), where=observed_weight>0)
    logarithms = np.zeros_like(probabilities)
    np.log2(probabilities, out=logarithms, where=probabilities>0)
    entropy = -(probabilities * logarithms).sum(axis=0)
    coverage = counts.sum(axis=0) / len(selected)
    rows = [dict(position=i+1, aa=selected[0]['sequence'][i],
        coverage=round(float(coverage[i]),4), observed_sequences=int(counts[:,i].sum()),
        residue_variety=int(variety[i]), entropy_bits=round(float(entropy[i]),5),
        entropy_conservation=round(float(1-entropy[i]/math.log2(20)),5),
        enough_data=bool(coverage[i] >= .5 and counts[:,i].sum() >= 3 and selected[0]['sequence'][i] in VALID)) for i in range(matrix.shape[1])]
    return rows, round(float(1/(weights**2).sum()),2)


def parse_rate4site(text, query):
    values = {}
    number = r'[-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?'
    pattern = re.compile(r'^\s*(\d+)\s+([A-Z-])\s+('+number+r')\s+\[\s*('+number+r')\s*,\s*('+number+r')\s*\]\s*('+number+r')\s+(\d+)\s*/\s*(\d+)')
    for line in text.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        pos, aa, rate, lower, upper, std, observed, total = match.groups()
        pos = int(pos)
        if not 1 <= pos <= len(query) or query[pos-1] != aa:
            raise ValueError('Rate4Site output does not match the query sequence.')
        metrics = [float(v) for v in (rate,lower,upper,std)]
        if not all(math.isfinite(v) for v in metrics):
            raise ValueError('Rate4Site returned non-finite rates.')
        values[pos] = dict(rate=metrics[0], rate_interval=metrics[1:3], rate_std=metrics[3])
    if len(values) != len(query):
        raise ValueError('Rate4Site did not return a finite Bayesian score for every query position. Inspect the log or use weighted entropy.')
    return values


def add_rate_percentiles(rows, rates):
    supported = [r for r in rows if r['enough_data']]
    values = np.array([rates[r['position']]['rate'] for r in supported])
    for row in rows:
        row.update(rates[row['position']])
        if row['enough_data'] and len(values)>1:
            rate=row['rate']
            # Average tied ranks. Smaller rates indicate stronger conservation.
            percentile=(float((values>rate).sum()) + (float((values==rate).sum())-1)/2)/(len(values)-1)
            row['score'] = round(percentile,5)
        else:
            row['score'] = None


def map_profile(structure, chain_id, rows):
    chain = next((c for c in structure['chains'] if c['id']==chain_id and c.get('sequence')),None)
    if not chain:
        raise ValueError('Choose a protein chain with a known sequence.')
    if ''.join(r['aa'] for r in rows) != chain['sequence']:
        raise ValueError('Conservation query does not match the structure chain sequence.')
    residues = []
    for residue in structure['residues']:
        if residue['chain'] != chain_id:
            continue
        pos = residue.get('query_position')
        profile = rows[pos-1] if pos is not None and 1 <= pos <= len(rows) else None
        atoms = [a for a in structure['atoms'] if a['chain']==chain_id and a['resi']==residue['resi']]
        residues.append({**residue, 'score':profile['score'] if profile else None,
            'coverage':profile['coverage'] if profile else None,
            'enough_data':profile['enough_data'] if profile else False,
            'plddt':round(float(np.mean([a['b'] for a in atoms])),1) if structure['predicted'] else None})
    mapped = sum(r.get('query_position') is not None for r in residues)
    if not mapped:
        raise ValueError('No resolved residues could be mapped reliably to the full protein sequence.')
    return residues, mapped


def interface_comparison(profile, contact_data, partner=None):
    chain = profile['chain']
    contact_residues = set()
    for row in contact_data['rows']:
        a,b = row['left'],row['right']
        if a['chain']==chain and (not partner or b['chain']==partner):
            contact_residues.add(a['resi'])
        if b['chain']==chain and (not partner or a['chain']==partner):
            contact_residues.add(b['resi'])
    supported = [r for r in profile['residues'] if r['score'] is not None]
    interface = [r for r in supported if r['resi'] in contact_residues]
    remainder = [r for r in supported if r['resi'] not in contact_residues]
    def group(rows):
        return dict(count=len(rows), mean=round(float(np.mean([r['score'] for r in rows])),4) if rows else None)
    left,right = group(interface),group(remainder)
    return dict(chain=chain, partner=partner, cutoff=contact_data['cutoff'],
        contact_residues=len(contact_residues), supported_contact_residues=len(interface),
        interface=left, other_residues=right,
        difference=round(left['mean']-right['mean'],4) if left['mean'] is not None and right['mean'] is not None else None,
        note='Descriptive comparison of unique resolved residues. No significance test or causal conclusion is implied.')


def run_analysis(config_path, output_dir):
    config = json.loads(Path(config_path).read_text())
    output = Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    structure_text = Path(config['structure_path']).read_text()
    if config.get('structure_sha256') and hashlib.sha256(Path(config['structure_path']).read_bytes()).hexdigest() != config['structure_sha256']:
        raise ValueError('The source structure changed since this analysis was queued.')
    structure = parse_structure(structure_text,config['predicted'])
    chain = next(c for c in structure['chains'] if c['id']==config['chain'])
    query = chain['sequence']
    if query != config['query_sequence']:
        raise ValueError('The source structure changed since this analysis was queued.')
    if config['source']=='search':
        print(f"Searching {config['database_name']} for chain {config['chain']} ({len(query)} residues)…",flush=True)
        query_file=output/'query.fasta';query_file.write_text('>query\n'+query+'\n')
        alignment_file=output/'search.sto'
        command=[config['jackhmmer'], '-N','1','--cpu',str(config['cpus']),
            '--incE','1e-4','--incdomE','1e-4','-E','1e-4','--noali',
            '-A',str(alignment_file),'-o',str(output/'search.log'),
            '--tblout',str(output/'hits.tbl'),str(query_file),config['database_path']]
        print('One Jackhmmer iteration; inclusion E-value 1e-4. Full database search can take time.',flush=True)
        subprocess.run(command,check=True)
        alignment=alignment_file.read_text();format='stockholm'
    else:
        print('Loading the supplied alignment…',flush=True)
        alignment=config['alignment'];format=config.get('format','auto')
    print('Filtering homologues and projecting the alignment onto the query…',flush=True)
    records=read_alignment(alignment,query,format)
    selected,stats=select_homologues(records,max_sequences=config['max_sequences'],
        min_coverage=config['min_coverage'],min_identity=config['min_identity'],redundancy=config['redundancy'])
    selected_file=output/'alignment.fasta'
    selected_file.write_text(''.join(f">{'query' if i==0 else 'seq'+str(i).zfill(4)}\n{r['sequence']}\n" for i,r in enumerate(selected)))
    rows,effective=entropy_profile(selected)
    print(f"Retained {len(selected)} aligned sequences; calculating {config['method']}…",flush=True)
    if config['method']=='rate4site':
        rate_file=output/'rate4site.txt'
        subprocess.run([config['rate4site'],'-s',str(selected_file),'-a','query',
            '-o',str(rate_file),'-x',str(output/'tree.nwk'),'-y',str(output/'unnormalized_rates.txt'),
            '-l',str(output/'rate4site.log'),'-ib','-Mj','-bg'],cwd=output,check=True)
        add_rate_percentiles(rows,parse_rate4site(rate_file.read_text(),query))
        method_label='Rate4Site · empirical Bayes / JTT'
        scale='Within-protein relative conservation percentile (0–100); lower normalized evolutionary rates are more conserved.'
    else:
        for row in rows:
            row['score']=row['entropy_conservation'] if row['enough_data'] else None
        method_label='Henikoff-weighted Shannon entropy'
        scale='Conservation = 1 − H / log₂(20), on a 0–1 scale. This is a composition-based score, not a phylogenetic rate estimate.'
    print('Mapping scores to resolved structure residues…',flush=True)
    residues,mapped=map_profile(structure,config['chain'],rows)
    warnings=[]
    if len(selected)<20:
        warnings.append('Fewer than 20 distinct sequences: interpret conservation cautiously. Larger, diverse alignments are preferable.')
    if config.get('database_name')=='pdb':
        warnings.append('PDB sequences are a structure-biased subset. Use UniRef90 or a curated alignment for broader evolutionary coverage.')
    if chain['sequence_source']=='resolved residues only':
        warnings.append('The file does not provide a full polymer sequence. The query consists of resolved residues only.')
    if mapped<len(residues):
        warnings.append(f'{len(residues)-mapped} residues lack a reliable sequence-position mapping.')
    result=dict(version=1,structure_id=config['structure_id'],chain=config['chain'],query_sequence=query,
        structure_sha256=hashlib.sha256(Path(config['structure_path']).read_bytes()).hexdigest(),
        method=config['method'],method_label=method_label,score_description=scale,
        source=config['source'],source_label=config['source_label'],created_at=now(),
        alignment_sha256=hashlib.sha256(selected_file.read_bytes()).hexdigest(),
        sequence_count=len(selected),effective_sequences=effective,filtering=stats,
        homologues=[{k:v for k,v in r.items() if k!='sequence'} for r in selected],
        positions=rows,residues=residues,mapped_residues=mapped,
        supported_positions=sum(r['score'] is not None for r in rows),warnings=warnings)
    save_json(output/'conservation.json',result)
    with (output/'conservation.csv').open('w',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['query_position','amino_acid','conservation_score','coverage','observed_sequences','entropy_bits','normalized_rate','rate_interval_lower','rate_interval_upper'])
        for row in rows:
            interval=row.get('rate_interval',[None,None])
            writer.writerow([row['position'],row['aa'],row['score'],row['coverage'],row['observed_sequences'],row['entropy_bits'],row.get('rate'),*interval])
    print('Conservation analysis complete. Scores, alignment, and provenance saved locally.',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--output-dir',required=True)
    args=parser.parse_args()
    run_analysis(args.config,args.output_dir)


if __name__=='__main__':
    main()
