# Molecular interaction explorer

A local web app for the AlphaFold 3 installation in this repository. It uses the
existing Python environment, downloaded databases, and model weights. The 3D
viewer is bundled, so exploration works offline.

## Start

From the repository root:

```bash
bash run_explorer.sh

```



Open **http://127.0.0.1:8765** in a browser. Stop the server with Ctrl+C. To use
another port or data location:

```bash
bash run_explorer.sh --port 8766 --db-dir ~/public_databases --model-dir ~/models
```

The default database and model locations are `~/public_databases` and `~/models`.
`DB_DIR` and `MODEL_DIR` environment variables also work. All explorer inputs,
logs, predictions, and the job history are stored in `explorer/data/`, which is
ignored by Git. Existing AF3 source files and downloaded databases are not edited.

Hover over (or tab to) a setting, score, or option for a plain-language
explanation. The text for every control is in `static/tips.js`.

## Explore

The initial library contains local experimental TetR–DNA (1QPI),
TetR–tetracycline (2TRT), and ubiquitin (1UBQ) structures when those files exist.
These views show the deposited **asymmetric unit**, not a reconstructed
biological assembly. Crystal symmetry can generate additional chains and
interfaces beyond those displayed.

- Rotate and zoom the 3D view; switch representations and toggle chains.
- Choose an interface and distance cutoff. A contact is one inter-chain
  residue pair whose closest heavy atoms are within the cutoff.
- Click a contact to highlight both residues, the closest atoms, and their distance.
- Download the unchanged source mmCIF or export all contacts as CSV.
- Predictions show pLDDT coloring, pTM, ipTM, and a PAE heatmap when accompanying
  confidence files are present. Select an interface for its chain-pair ipTM.

Coordinates use the first model, omit waters and hydrogens, and prefer the
unlabelled/A/1 alternate location. The viewer uses normalized consecutive residue
numbers internally; the contact table preserves the source residue labels.
Confidence is shown for predictions only. Geometric proximity and confidence
scores do not measure binding affinity or prove that two molecules bind.

## Run experiments

Click **New experiment** and choose a TetR preset, another of the 13 examples,
or **Custom input**. The molecule builder accepts proteins, DNA, RNA, ligands
defined by CCD codes or SMILES, and repeated chains such as `A, B`.

**Find a molecule**, at the top of the builder, searches every protein, DNA, and
RNA chain in the local PDB snapshot (about 196,000 entries, grouped by identical
sequence) and every ligand and ion in the Chemical Component Dictionary. Filter
by type, then search by name, PDB ID, ligand code, or a pasted sequence, and
click **Add**. With an empty search it lists the most-studied molecules of that
type. Click a PDB ID to open that entry and add its molecules together: water is
left out, common crystallization additives start unselected, and the 32-chain
limit is checked before anything is added. DNA cards offer **+ Complementary
strand**. Sequences are the PDB's canonical sequences, so modified residues
appear as their standard parents.

The catalog is built from local files the first time the explorer starts (about
a minute) and saved as `explorer/data/molecules.sqlite`.

The **AF3 JSON** editor also accepts inline alignments, templates, modifications,
and covalent bonds. Its name and seed fields are authoritative while editing JSON.
File-path fields are rejected; embed referenced data in the input JSON instead.

Run modes:

| Mode | Result |
| --- | --- |
| Search databases + predict | Local sequence/template searches, followed by AF3 inference |
| Prepare MSAs & templates only | Reusable AF3 input JSON; no inference |
| Sequence-only prediction | Inference with explicitly empty MSAs/templates; useful for a runtime check |
| Predict from prepared input | Inference using already supplied MSAs/templates |

One job runs at a time to limit contention for memory. Watch the live process log
under **Experiments**. Completed models and individual seed/sample outputs are
added to the library automatically. A preparation job offers **Predict prepared
input**, which reuses its alignments and templates.

Cancellation stops the AF3 process group, including search tools. After a server
restart, jobs that were queued or running are marked interrupted instead of
silently rerunning. Use **Use input again** to create a fresh job.

To delete a finished, failed, or cancelled job, swipe its card left in the
**Experiments** list (drag, touch, or a two-finger trackpad swipe; with the
keyboard, focus the card and press ←) and click **Delete**. After confirmation
this removes its folder, the predictions it added to the library, and any
conservation analyses of those predictions. Cancel an active job before
deleting it. **New experiment** is also available in the sidebar.

Full database searches may take hours and use substantial RAM. MPS on Apple
Silicon is experimental; CPU inference is available as a slower alternative.
Start with ubiquitin before larger complexes. For scientific use, keep normal
recycles and sample across multiple seeds; sequence-only, one-recycle runtime
checks are not validated biological predictions.

## Import and compare

Use **+** in the structure library to load a PDB ID from the local September
2022 snapshot, upload mmCIF, or import an existing AF3 output folder. Folder
imports include `*_model.cif` files at the root and up to two folder levels down,
and use their sibling AF3 confidence JSON files. Compressed outputs should be
decompressed first.

**Compare** displays two structures side by side. Backbone alignment uses
Kabsch fitting of Cα atoms and requires identical resolved residue sequences.
Choose matching chains; different constructs or missing residues can prevent
alignment. The RMSD is the fitted Cα coordinate deviation.

## Evolutionary conservation

Choose a protein structure and scroll to **Sequence conservation**. Select a
protein chain and click **+ Analyze**. You can:

- Reuse a prepared AF3 alignment that matches the chain sequence exactly.
- Upload/paste A3M, aligned FASTA, or Stockholm, or load an AF3 JSON containing
  an inline alignment. Include the full query sequence as an alignment row.
- Search the local UniRef90 database, or use the smaller PDB sequence database
  for a faster preview. The PDB sequence collection has structural sampling bias.

**Rate4Site** estimates evolutionary rates using empirical Bayes, a JTT
substitution model, and an inferred neighbor-joining tree with optimized branch
lengths and Gamma rate variation. Lower normalized rates indicate greater
conservation. The 3D view displays within-protein conservation percentiles, from
0 to 100. Raw rates, posterior 25–75% intervals, and the tree are exported.
This uses ConSurf's core rate-estimation method; it does not reproduce the entire
ConSurf server's sequence-selection procedure or its nine conservation grades.

**Weighted entropy** is a faster alternative using Henikoff position-based
sequence weights and `1 − H/log₂(20)`. The interface displays this value on a
0–100 scale. It measures amino-acid diversity rather than phylogenetic rates.

Both methods filter by coverage and identity, remove exact duplicates and
near-identical aligned sequences, and sample across similarity to the query.
Defaults retain up to 150 sequences, require 70% query coverage and 20%
identity, and remove redundancy at 95% identity. Very large input alignments
are bounded to 10,000 rows and a sampled clustering pool; selection counts are
recorded in the result's provenance.

Scores are masked where fewer than three sequences have a standard amino acid
or column coverage is below 50%. The result warns when fewer than 20 distinct
sequences remain. Effective alignment size is calculated from Henikoff weights;
it is not a count of independent species or a confidence probability.

Sequence positions are mapped using mmCIF polymer numbering, so missing
coordinates do not shift later scores. Files without a full polymer sequence
use their resolved residues as the query and are labelled accordingly. A source
file fingerprint prevents applying a saved analysis to a subsequently changed
structure.

After completion, click **Explore conservation →** in Experiments, or choose
the saved analysis in the structure's conservation panel. **Color in 3D** shows
the selected chain's scores; gray marks insufficient data. Other chains are
muted. Inspect a position on the sequence chart to see its coverage, raw rate,
posterior interval, and AF3 pLDDT when available. Clicking a resolved position
locates it in the 3D view. The contact comparison counts unique residues and
compares their mean conservation with other scored residues. It is descriptive
and does not establish statistical significance or binding affinity.

Alignment, score CSV, raw rate, and tree exports remain local. Conservation jobs
share the AF3 queue and cancellation controls.

Rate4Site is installed locally in `explorer/data/tools/`. To rebuild it on
another machine:

```bash
.venv/bin/python -m explorer.install_rate4site
```

This downloads the published source from Tel Aviv University and builds its
extended-range arithmetic version with a C++ compiler. An existing executable
can also be supplied through `RATE4SITE_BIN`. The weighted-entropy method works
without this executable. The source URL, archive SHA-256, and build flags are
saved beside the binary. Rate4Site remains subject to its authors' terms.

Method references: [Rate4Site](https://www.tau.ac.il/~itaymay/cp/rate4site.html),
[ConSurf](https://consurf.tau.ac.il/), and
[Henikoff sequence weighting](https://pubmed.ncbi.nlm.nih.gov/7966282/).

A real TetR conservation check using the local PDB subset is available:

```bash
.venv/bin/python explorer/tests/conservation_probe.py
.venv/bin/python explorer/tests/conservation_probe.py --job JOB_ID
```

## Online demo

A read-only copy of the explorer is published with GitHub Pages at
**<https://zhuoyang-ye.github.io/alphafold3-interactive-UI/>**. It shows the
structures, contacts, confidence, conservation results, and job logs that were
in the local library when it was published. Predictions, imports, and new
analyses need the local explorer.

To update it after adding structures or results, start the explorer and run:

```bash
bash run_explorer.sh            # in one Terminal window
bash explorer/publish_demo.sh   # in another, from the repository root
```

This saves every view of the current library into static files
(`explorer/build_demo.py`), adds `explorer/demo/demo.js` to serve them, and
commits the result to the `gh-pages` branch. Your home folder is replaced by `~`
in all saved data, and publishing stops if your user or computer name remains
in any file. **Everything in your library is published**, so remove anything
you want to keep private first. Published AF3 predictions remain subject to the
[AlphaFold 3 Output Terms of Use](../OUTPUT_TERMS_OF_USE.md); the demo shows
the required notice and citation.

For a fork, enable Pages once under **Settings → Pages**: deploy from the
`gh-pages` branch, root folder.

## Verification

```bash
.venv/bin/python -m unittest discover -s explorer/tests -p 'test_*.py' -v
```

The tests cover contact distances, residue-pair aggregation, coordinate parsing,
Kabsch alignment, input validation, HTTP access checks, output imports, prepared
input reuse, and job cancellation. Integration tests use a small fixture process,
not the model weights or full databases.

An optional actual AF3 runtime check, with the explorer running:

```bash
.venv/bin/python explorer/tests/runtime_probe.py
# Inspect the printed job ID:
.venv/bin/python explorer/tests/runtime_probe.py --job JOB_ID
```

The runtime check uses ubiquitin without MSAs/templates, one sample, and one
recycle. It verifies that AF3 can produce structure and confidence files on the
local MPS backend. It does not benchmark prediction accuracy or exercise a full
database search.

The server binds to `127.0.0.1` only. Mutations require a session token and are
restricted to the local origin. No hosting, cloud uploads, or telemetry are used.

## Third-party software

The bundled viewer is 3Dmol.js **2.5.3**, downloaded from the npm package via
unpkg. Its license and included third-party notices are in
`static/vendor/3Dmol-LICENSE.txt`. AlphaFold 3 code, model weights, and outputs
remain subject to the terms distributed with this repository and each output.
