'use strict';
// Molecule finder in the experiment builder: search the local PDB and CCD catalog,
// add single molecules or the contents of a whole PDB entry to the draft.

const finder = {kind:'', offset:0, version:0, timer:null, query:'', results:[], entry:null};
const KIND_LABELS = {protein:'Protein', dna:'DNA', rna:'RNA', ligand:'Ligand', ion:'Ion'};
const MAX_CHAINS = 32;

function draftChainIds() {return state.draft.sequences.flatMap(s=>[Object.values(s)[0].id].flat());}
function isFilled(entry) {const m=Object.values(entry)[0];return Boolean(m.sequence||m.ccdCodes?.length||m.smiles);}
function nextChainIds(count) {
  const used=new Set(draftChainIds()),ids=[];
  for(let n=0;ids.length<count;n++) {
    let id='',k=n;
    do {id=String.fromCharCode(65+k%26)+id;k=Math.floor(k/26)-1;} while(k>=0);
    if(!used.has(id))ids.push(id);
  }
  return ids;
}
function reverseComplement(sequence) {return [...sequence].reverse().map(c=>({A:'T',T:'A',G:'C',C:'G'}[c]||'N')).join('');}
function addComplement(index) {
  syncBuilder();
  const strand=Object.values(state.draft.sequences[index])[0];
  if(!strand.sequence)throw new Error('Enter the DNA sequence first.');
  const [id]=nextChainIds(1);
  state.draft.sequences.splice(index+1,0,{dna:{id,sequence:reverseComplement(strand.sequence)}});
  renderMolecules();toast(`Added the complementary strand as chain ${id}.`);
}

function renderDraftSummary() {
  if(!$('draft-summary')||!state.draft)return;
  let residues=0,ligands=0;
  for(const entry of state.draft.sequences) {
    const [kind,m]=Object.entries(entry)[0],copies=[m.id].flat().length;
    if(kind==='ligand')ligands+=copies;else residues+=(m.sequence||'').length*copies;
  }
  const chains=draftChainIds().length;
  $('draft-summary').innerHTML=`${chains} chain${chains===1?'':'s'} · ${fmt(residues)} residues${ligands?` · ${ligands} ligand${ligands===1?'':'s'}`:''}`+
    (residues>1500?' · <span class="draft-warning">Large input: this can take many hours or run out of memory on a Mac.</span>':'');
}

function addToDraft(items) {
  syncBuilder();
  // Drop the empty placeholder that a new or custom input starts with.
  state.draft.sequences=state.draft.sequences.filter(isFilled);
  const total=draftChainIds().length+items.reduce((n,x)=>n+x.copies,0);
  if(total>MAX_CHAINS)throw new Error(`That would make ${total} chains. The local explorer allows ${MAX_CHAINS}; choose fewer copies or molecules.`);
  const added=[];
  for(const {molecule,copies} of items) {
    const ids=nextChainIds(copies),id=ids.length===1?ids[0]:ids;
    state.draft.sequences.push(['ligand','ion'].includes(molecule.kind)?{ligand:{id,ccdCodes:[molecule.code]}}:{[molecule.kind]:{id,sequence:molecule.sequence}});
    added.push(ids.join(', '));
  }
  renderMolecules();
  const list=$('molecule-list');list.scrollIntoView({block:'end',behavior:'smooth'});
  toast(items.length===1?`Added ${items[0].molecule.name} as chain ${added[0]}.`:`Added ${items.length} molecules (chains ${added.join('; ')}).`);
}

function moleculeMeta(m) {
  if(['ligand','ion'].includes(m.kind))return `${esc(m.code)}${m.formula&&m.formula!=='?'?' · '+esc(m.formula):''}`;
  const unit=m.kind==='protein'?'amino acids':'nucleotides',length=m.length??m.sequence.length;
  return `${fmt(length)} ${unit}${length>1500?' · <span class="draft-warning">very large</span>':''}`;
}
function entriesLine(m) {
  if(!m.entries)return 'Not seen in the local PDB snapshot';
  const links=m.examples.map(([id])=>`<button class="pdb-link" data-entry="${esc(id)}" title="Open every molecule in PDB ${esc(id)}">${esc(id)}</button>`).join(' ');
  return `In ${fmt(m.entries)} PDB entr${m.entries===1?'y':'ies'}${links?' · '+links:''}`;
}

async function searchMolecules(more=false) {
  const version=++finder.version,query=$('finder-query').value.trim();
  if(!more){finder.offset=0;finder.entry=null;}
  const data=await api(`/api/catalog?q=${encodeURIComponent(query)}&kind=${finder.kind}&offset=${finder.offset}`);
  if(version!==finder.version)return;
  finder.query=query;finder.results=more?finder.results.concat(data.results):data.results;finder.offset+=data.results.length;
  renderFinder(data);
  if(data.status.state==='building')setTimeout(()=>{if(version===finder.version&&$('experiment-dialog').open)searchMolecules().catch(e=>toast(e.message));},2000);
}

function renderFinder(data) {
  const status=data.status,counts=status.counts||{};
  $('finder-status').textContent=status.state==='ready'?`${fmt(status.entries)} PDB entries · ${fmt((counts.ligand||0)+(counts.ion||0))} ligands and ions`:'';
  if(status.state!=='ready') {
    const building=status.state==='building';
    $('finder-results').innerHTML=`<div class="finder-empty">${building?`<span class="spinner"></span><p>${esc(status.message)} · ${Math.round(status.progress*100)}%</p><p class="small muted">This runs once, takes about a minute, and reads only your local files.</p>`:
      `<p>${esc(status.message||'The molecule catalog has not been built yet.')}</p><button class="secondary" id="finder-build">Build the molecule catalog</button>`}</div>`;
    return;
  }
  const label=finder.kind?KIND_LABELS[finder.kind].toLowerCase():'molecule';
  const heading=finder.query?`${fmt(finder.results.length)}${data.more?'+':''} match${finder.results.length===1?'':'es'}`:
    `Most-studied ${finder.kind==='dna'?'DNA':finder.kind==='rna'?'RNA':label+(label.endsWith('s')?'':'s')} in the PDB`;
  const entry=data.entry?`<div class="finder-row finder-entry-suggestion"><span class="kind-badge entry">PDB</span><div class="finder-main"><strong>PDB entry ${esc(data.entry)}</strong><small>Add its proteins, DNA, RNA, and ligands together</small></div><button class="secondary" data-entry="${esc(data.entry)}">Open entry</button></div>`:'';
  const rows=finder.results.map((m,i)=>`<div class="finder-row"><span class="kind-badge ${m.kind}">${KIND_LABELS[m.kind]}</span><div class="finder-main"><strong>${esc(m.name)}</strong><small>${moleculeMeta(m)} · ${entriesLine(m)}</small>${['dna','rna'].includes(m.kind)&&m.examples[0]?`<small class="finder-context">From “${esc(m.examples[0][1])}”</small>`:''}</div><button class="secondary" data-add="${i}">Add</button></div>`).join('');
  $('finder-results').innerHTML=`<div class="finder-list-heading">${heading}</div>${entry}${rows||(entry?'':`<div class="finder-empty"><p>No ${label}s match “${esc(finder.query)}”.</p><p class="small muted">Try a shorter name, a PDB ID such as 1UBQ, or a ligand code such as ATP.</p></div>`)}${data.more?'<button class="text-button finder-more" data-more="1">Show more results</button>':''}`;
}

async function openEntry(pdbId) {
  const version=++finder.version;
  $('finder-results').innerHTML='<div class="finder-empty"><span class="spinner"></span><p>Reading PDB '+esc(pdbId)+'…</p></div>';
  const entry=await api('/api/catalog/entry/'+encodeURIComponent(pdbId));
  if(version!==finder.version)return;
  finder.entry=entry;renderEntry();
}
function renderEntry() {
  const e=finder.entry;
  const rows=e.molecules.map((m,i)=>`<div class="finder-row entry-row"><input type="checkbox" id="entry-pick-${i}" data-pick="${i}" ${m.selected?'checked':''}><span class="kind-badge ${m.kind}">${KIND_LABELS[m.kind]}</span><label class="finder-main" for="entry-pick-${i}"><strong>${esc(m.name)}</strong><small>${moleculeMeta(m)}${m.selected?'':' · likely a crystallization additive'}</small></label><label class="entry-copies">Copies<input type="number" min="1" max="${MAX_CHAINS}" value="${m.copies}" data-copies="${i}"></label></div>`).join('');
  $('finder-results').innerHTML=`<div class="finder-entry-header"><button class="text-button" data-back="1">← Back to results</button><strong>PDB ${esc(e.pdb_id)}</strong><span class="muted">${esc(e.title)}</span></div>
    <p class="small muted finder-note">Molecules in the deposited structure (asymmetric unit). The biological assembly can contain more or fewer copies. Water is not included.</p>
    ${rows||'<div class="finder-empty"><p>This entry has no molecules the builder can add.</p></div>'}
    ${e.skipped.length?`<p class="small muted finder-note">Not added (not supported by the builder): ${esc(e.skipped.join('; '))}.</p>`:''}
    <div class="finder-entry-actions"><span id="entry-count" class="small muted"></span><button class="primary" id="finder-add-entry">Add selected</button></div>`;
  updateEntryCount();
}
function selectedEntryItems() {
  return [...$('finder-results').querySelectorAll('[data-pick]:checked')].map(box=>{
    const i=Number(box.dataset.pick),copies=Math.max(1,Math.min(MAX_CHAINS,Number($('finder-results').querySelector(`[data-copies="${i}"]`).value)||1));
    return {molecule:finder.entry.molecules[i],copies};
  });
}
function updateEntryCount() {
  if(!finder.entry||!$('entry-count'))return;
  syncBuilder();
  const existing=state.draft.sequences.filter(isFilled).reduce((n,s)=>n+[Object.values(s)[0].id].flat().length,0);
  const chains=selectedEntryItems().reduce((n,x)=>n+x.copies,0),total=chains+existing;
  $('entry-count').innerHTML=`${chains} chain${chains===1?'':'s'} selected`+(total>MAX_CHAINS?` · <span class="draft-warning">over the ${MAX_CHAINS}-chain limit</span>`:'');
}

function resetFinder() {
  $('finder-query').value='';finder.kind='';
  document.querySelectorAll('#finder-kinds button').forEach(b=>b.classList.toggle('selected',b.dataset.kind===''));
  searchMolecules().catch(e=>toast(e.message));
}
function setupFinder() {
  on('finder-query','input',()=>{clearTimeout(finder.timer);finder.timer=setTimeout(()=>searchMolecules().catch(e=>toast(e.message)),250);});
  document.querySelectorAll('#finder-kinds button').forEach(b=>b.onclick=()=>{
    finder.kind=b.dataset.kind;document.querySelectorAll('#finder-kinds button').forEach(x=>x.classList.toggle('selected',x===b));
    searchMolecules().catch(e=>toast(e.message));
  });
  on('finder-results','click',async event=>{
    const target=event.target.closest('button');if(!target)return;
    if(target.dataset.add)addToDraft([{molecule:finder.results[Number(target.dataset.add)],copies:1}]);
    else if(target.dataset.entry)await openEntry(target.dataset.entry);
    else if(target.dataset.more)await searchMolecules(true);
    else if(target.dataset.back)await searchMolecules();
    else if(target.id==='finder-add-entry') {
      const items=selectedEntryItems();
      if(!items.length)throw new Error('Select at least one molecule to add.');
      addToDraft(items);
    }
    else if(target.id==='finder-build'){await api('/api/catalog/build',{});await searchMolecules();}
  });
  on('finder-results','change',updateEntryCount);
  on('molecule-list','input',()=>{syncBuilder();renderDraftSummary();});
}
