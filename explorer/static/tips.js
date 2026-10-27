'use strict';
// Plain-language explanations shown when hovering over (or tabbing to) a control.
// They are attached by selector, so content rendered later (stats, confidence
// scores, job lists) gets them too. The first matching selector wins.

const TIPS = [
  // Sidebar
  ['#sidebar-new', 'Design and run a new AlphaFold 3 prediction.'],
  ['#import-open', 'Add a structure to your library: a PDB ID from your local snapshot, an AF3 output folder, or an mmCIF file.'],
  ['#system-open', 'Check that your databases, model weights, and search tools were found.'],

  // Structure view
  ['[data-style="cartoon"]', 'Cartoon: ribbons trace each protein and DNA/RNA backbone (helices as spirals, strands as arrows). Ligands are drawn as sticks.'],
  ['[data-style="stick"]', 'Sticks: every bond between heavy atoms. Shows side chains, useful for looking at contacts.'],
  ['[data-style="sphere"]', 'Ball & stick: atoms as small balls joined by bonds. The easiest way to see individual atoms.'],
  ['.compact-select', 'Color the structure by:\n• Chain: one color per molecule.\n• Confidence: AF3\'s pLDDT score (predictions only). Blue = confident, orange = low confidence.\n• Conservation: how conserved each amino acid is across related proteins. Run a conservation analysis first.'],
  ['#reset-view', 'Re-center the 3D view and zoom to fit the whole structure.'],
  ['#compare-current', 'Show this structure on the Compare page, next to another one.'],
  ['#download-cif', 'Download the original structure file (mmCIF format), unchanged.'],
  ['#structure-stats .stat:nth-child(1)', 'Heavy atoms: all non-hydrogen atoms in the first model, not counting water.'],
  ['#structure-stats .stat:nth-child(2)', 'Resolved residues: amino acids and nucleotides that have coordinates. Flexible regions are often missing from experimental structures.'],
  ['#structure-stats .stat:nth-child(3)', 'Molecular chains: separate molecules in the file, such as protein chains, DNA or RNA strands, and ligands.'],
  ['#structure-stats .stat:nth-child(4)', 'Residue contacts: pairs of residues on different chains whose closest heavy atoms are within the distance cutoff.'],

  // Contacts
  ['.contact-controls label:nth-child(1)', 'Two residues count as a contact when any of their heavy atoms are this close.\n• 3.5 Å: mostly hydrogen bonds and salt bridges\n• 4.0–4.5 Å: also close packing (4.5 Å is a common default)\n• 5–8 Å: residues that are near each other but not necessarily touching'],
  ['.contact-controls label:nth-child(2)', 'Show contacts between all chains, or only between one pair. The number in brackets is how many residue pairs touch.'],
  ['#download-contacts', 'Download every contact at this distance as a spreadsheet (CSV).'],

  // Confidence
  ['.confidence-metrics div:nth-child(1)', 'pLDDT (0–100): AF3\'s confidence in the local position of each atom, averaged here.\n• 90 or more: very high\n• 70–90: confident\n• 50–70: low\n• Under 50: very low, often a flexible or disordered region'],
  ['.confidence-metrics div:nth-child(2)', 'ipTM (0–1): confidence in how the chains are placed relative to each other.\n• Above 0.8: usually a reliable interface\n• 0.6–0.8: uncertain\n• Below 0.6: likely incorrect\nOnly meaningful when there are two or more chains.'],
  ['.confidence-metrics div:nth-child(3)', 'pTM (0–1): confidence in the overall fold of the whole complex. Above 0.5 suggests the predicted fold may resemble the true structure.'],
  ['.plddt-legend', 'Colors used by "Color: By confidence", from AF3\'s per-atom pLDDT score.'],
  ['.pae-plot', 'Predicted aligned error, in Å: how far off the residue on the x-axis may be when the structure is aligned on the residue on the y-axis. Dark means confident. A dark block between two chains means their relative placement is confident.'],
  ['#interface-confidence', 'Chain-pair ipTM (0–1): AF3\'s confidence in how these two chains are placed relative to each other.'],

  // Conservation
  ['#conservation-open', 'Start a new conservation analysis for the selected protein chain.'],
  ['.conservation-controls label:nth-child(1)', 'The protein chain whose amino-acid conservation is shown.'],
  ['.conservation-controls label:nth-child(2)', 'Choose between conservation analyses already run for this chain.'],
  ['#conservation-color', 'Color this chain in 3D by conservation: purple = conserved, teal-green = variable, gray = not enough data.'],
  ['.conservation-metrics div:nth-child(1)', 'Related sequences used for scoring, after removing near-duplicates and poor matches.'],
  ['.conservation-metrics div:nth-child(2)', 'Sequence positions with enough aligned sequences to be scored.'],
  ['.conservation-metrics div:nth-child(3)', 'Residues in this 3D structure that received a conservation score.'],
  ['.conservation-interface label', 'Compare the conservation of residues that touch this partner with all other residues. Conserved contact residues can point to important binding sites.'],

  // Compare
  ['.compare-select-label', 'Pick any structure from your library for this side.'],
  ['.alignment-controls label', 'Protein chain to superimpose. Both chains must have identical resolved sequences.'],
  ['#align-button', 'Superimpose structure B onto A using the backbone (Cα) atoms of the chosen chains. RMSD is the average distance between matched atoms afterwards:\n• Under 1 Å: nearly identical\n• 1–2 Å: very similar\n• Over 3 Å: clearly different'],
  ['#compare-reset', 'Reload both structures and reset their cameras.'],

  // New experiment
  ['.form-row label:nth-child(1)', 'A name for this run. It is also used for the output file names.'],
  ['.seeds-label', 'Each seed starts AF3 from a different random point. Several seeds (for example 1, 2, 3) give more predictions to compare; each one adds runtime.'],
  ['#blank-input', 'Start from an empty list of molecules.'],
  ['.preset-sidebar .file-button', 'Open an AlphaFold 3 input file (.json) from your computer.'],
  ['#builder-tab', 'Build the input by adding molecules one at a time.'],
  ['#json-tab', 'Edit the raw AlphaFold 3 input file. For advanced options such as chemical modifications and bonds.'],
  ['#finder-kinds [data-kind=""]', 'Search every type of molecule at once.'],
  ['#finder-kinds [data-kind="protein"]', 'Proteins: chains of amino acids, such as enzymes, antibodies, and receptors.'],
  ['#finder-kinds [data-kind="dna"]', 'DNA strands seen in PDB structures. Double-stranded DNA is two separate strands.'],
  ['#finder-kinds [data-kind="rna"]', 'RNA chains, such as transfer RNA, ribosomal RNA, riboswitches, and aptamers.'],
  ['#finder-kinds [data-kind="ligand"]', 'Small molecules: drugs, cofactors such as ATP and heme, sugars, and other chemicals from the PDB\'s Chemical Component Dictionary.'],
  ['#finder-kinds [data-kind="ion"]', 'Single charged atoms such as Mg²⁺, Zn²⁺, and Ca²⁺. Many enzymes and DNA or RNA complexes need them.'],
  ['.entry-copies', 'How many copies of this molecule to add. Each copy becomes its own chain.'],
  ['.molecule-type', 'Molecule type:\n• Protein: an amino-acid sequence\n• DNA / RNA: a nucleotide sequence (A, C, G, and T or U)\n• Ligand / ion: a small molecule or metal ion, by CCD code or SMILES'],
  ['.chain-hint', 'Letters that name each copy. One letter is one chain; "A, B" makes two identical copies, such as a homodimer.'],
  ['.molecule-ids', 'Letters that name each copy. One letter is one chain; "A, B" makes two identical copies, such as a homodimer.'],
  ['.ligand-format', '• CCD codes: the PDB\'s short codes, such as ATP, HEM, or MG\n• SMILES: a text formula, for molecules without a CCD code'],
  ['.add-complement', 'Add the matching opposite strand. Double-stranded DNA needs both strands as separate chains.'],
  ['.run-settings label:nth-child(1)', '• Search databases + predict: the accurate, standard mode. Searches your local databases first; can take hours.\n• Prepare MSAs & templates only: runs just the search and saves it, so you can predict later.\n• Sequence-only prediction: skips the search. A fast check that everything works, but much less accurate.\n• Predict from prepared input: uses the search results from a "Prepare" run.'],
  ['.run-settings label:nth-child(2)', '• Apple Silicon · MPS: your Mac\'s GPU, about 3× faster than CPU (experimental)\n• CPU: slower, but the most compatible\n• NVIDIA GPU: only on Linux computers with an NVIDIA card'],
  ['.run-settings label:nth-child(3)', 'How many structures AF3 generates for each seed. More samples give more alternatives to rank; each one adds runtime. AF3\'s own default is 5.'],
  ['.run-settings label:nth-child(4)', 'How many times AF3 refines its internal picture before building the structure. 10 is the standard setting; fewer is faster but less accurate.'],
  ['#validate-input', 'Check the input for mistakes without running anything.'],
  ['#queue-job', 'Start the experiment. Jobs run one at a time, in the order they were added.'],

  // Conservation analysis dialog
  ['.conservation-form-grid label:nth-child(1)', '• Search local databases: find related sequences with Jackhmmer (can take hours)\n• Reuse a prepared AF3 alignment: the alignment AF3 already built for this protein\n• Upload or paste: use your own alignment file'],
  ['.conservation-form-grid label:nth-child(2)', '• Rate4Site: estimates how fast each position evolves on a family tree; the method behind ConSurf. Most rigorous.\n• Weighted entropy: measures the variety of amino acids at each position. Fast; good for a first look.'],
  ['#conservation-search-fields label', '• UniRef90: broad coverage of known proteins. Best results, but slow.\n• PDB sequences: only proteins with known structures. A fast preview from a biased sample.'],
  ['.conservation-parameters label:nth-child(1)', 'The most related sequences to keep for scoring. More can be more accurate, but slower.'],
  ['.conservation-parameters label:nth-child(2)', 'Related sequences must align over at least this percentage of your protein.'],
  ['.conservation-parameters label:nth-child(3)', 'Related sequences must have at least this percentage of identical amino acids at aligned positions. Filters out very distant matches.'],
  ['.conservation-parameters label:nth-child(4)', 'Sequences more similar to each other than this are treated as duplicates; only one is kept.'],

  // Experiments
  ['.status-tag.queued', 'Queued: waiting for the job ahead of it to finish.'],
  ['.status-tag.running', 'Running: in progress. The live log shows what it is doing.'],
  ['.status-tag.cancelling', 'Cancelling: stopping the job and its search tools.'],
  ['.status-tag.completed', 'Completed: finished successfully.'],
  ['.status-tag.failed', 'Failed: stopped with an error. The log shows why.'],
  ['.status-tag.cancelled', 'Cancelled: stopped by you.'],
  ['.status-tag.interrupted', 'Interrupted: the explorer was closed while this job was running. Use its input again to restart it.'],
];

function applyTips() {
  for(const [selector, text] of TIPS) {
    document.querySelectorAll(selector).forEach(el => {
      if(el.dataset.tip) return;
      el.dataset.tip = text;
      el.removeAttribute('title');
    });
  }
}

function setupTips() {
  const tip = document.createElement('div');
  tip.id = 'tooltip'; tip.className = 'tooltip'; tip.setAttribute('role', 'tooltip'); tip.hidden = true;
  let target = null, timer = null;
  function hide() {
    clearTimeout(timer);
    if(target) target.removeAttribute('aria-describedby');
    target = null; tip.hidden = true;
  }
  function show(el) {
    // Dialogs sit in the browser's top layer, so the tooltip must live inside an open one.
    (el.closest('dialog[open]') || document.body).append(tip);
    tip.textContent = el.dataset.tip; tip.hidden = false;
    el.setAttribute('aria-describedby', 'tooltip');
    const box = el.getBoundingClientRect(), width = tip.offsetWidth, height = tip.offsetHeight;
    const below = box.bottom + 8 + height <= innerHeight - 8;
    tip.style.top = (below ? box.bottom + 8 : Math.max(8, box.top - height - 8)) + 'px';
    tip.style.left = Math.max(8, Math.min(box.left, innerWidth - width - 8)) + 'px';
  }
  document.addEventListener('mouseover', event => {
    const el = event.target.closest('[data-tip]');
    if(el === target) return;
    hide();
    if(el) {target = el; timer = setTimeout(() => show(el), 300);}
  });
  document.addEventListener('focusin', event => {
    const el = event.target.closest('[data-tip]');
    hide();
    if(el && event.target.matches(':focus-visible')) {target = el; show(el);}
  });
  document.addEventListener('focusout', hide);
  document.addEventListener('pointerdown', hide);
  document.addEventListener('scroll', hide, true);
  document.addEventListener('keydown', event => {if(event.key === 'Escape') hide();});
  applyTips();
  let pending = false;
  new MutationObserver(() => {
    if(pending) return;
    pending = true;
    requestAnimationFrame(() => {pending = false; applyTips();});
  }).observe(document.body, {childList: true, subtree: true});
}

document.addEventListener('DOMContentLoaded', setupTips);
