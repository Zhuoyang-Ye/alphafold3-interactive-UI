'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = value => value == null ? '—' : Number(value).toLocaleString(undefined, {maximumFractionDigits:2});
const palette = ['#aacd84','#6ab5d6','#e7ae74','#b997d3','#e1c879','#df92a2','#67bca4','#8f9cd6'];
const state = {token:null, page:'explore', structures:[], jobs:[], presets:[], selected:null, detail:null,
  contacts:null, viewer:null, style:'cartoon', color:'chain', hidden:new Set(), selectedContact:null,
  draft:null, jsonMode:false, job:null, compare:{}, loadVersion:0, compareVersion:0,
  conservation:null, conservationRuns:[], conservationVersion:0, rate4site:null};
let toastTimer;
function toast(message) { $('toast').textContent=message; $('toast').classList.remove('hidden'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').classList.add('hidden'),6500); }
function message(id, text, ok=false) { $(id).innerHTML=`<div class="${ok?'success-message':'error-message'}">${esc(text)}</div>`; }
function on(id,event,fn) { $(id).addEventListener(event, async e=>{try {await fn(e);} catch(error) {toast(error.message);}}); }
async function api(path, data) {
  const options = data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Explorer-Token':state.token},body:JSON.stringify(data)};
  const response = await fetch(path,options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status}).`);
  return body;
}
function colorFor(chain, detail=state.detail) {const index=(detail?.chains||[]).findIndex(c=>c.id===chain); return palette[Math.max(0,index)%palette.length];}
function shortKind(kind) {return kind.includes('polypeptide')?'Protein':kind.includes('deoxyribo')?'DNA':kind.includes('ribonucleotide')?'RNA':kind==='non-polymer'?'Ligand':kind==='branched'?'Glycan':kind;}
function structureLabel(r) {return r.name + (r.sample && r.sample!=='Best ranked'?' · '+r.sample:'');}
function modeName(mode) {return {full:'Database search + prediction',prepare:'MSAs & templates',inference:'Prepared-input prediction',quick:'Sequence-only prediction',conservation:'Conservation analysis'}[mode]||mode;}
function setPage(page) {
  state.page=page;
  document.querySelectorAll('.page').forEach(el=>el.classList.toggle('hidden',el.id!=='page-'+page));
  document.querySelectorAll('[data-page]').forEach(el=>el.classList.toggle('active',el.dataset.page===page));
  $('page-title').textContent={explore:'Molecular interactions',compare:'Compare structures',experiments:'Your experiments'}[page];
  $('page-description').textContent={explore:'Look closer at the connections that shape biology.',compare:'Explore how a molecular context changes the picture.',experiments:'Build, run, and revisit your local AlphaFold 3 predictions.'}[page];
  if(page==='explore') requestAnimationFrame(()=>state.viewer?.resize());
  if(page==='compare') {updateCompareOptions(); loadComparison().catch(e=>toast(e.message));}
  if(page==='experiments') renderJobs();
}
function renderLibrary() {
  const search=$('structure-search').value.toLowerCase();
  const items=state.structures.filter(r=>(r.name+' '+(r.pdb_id||'')+' '+(r.sample||'')).toLowerCase().includes(search));
  $('library').innerHTML=['reference','prediction'].map(kind=>{
    const group=items.filter(r=>r.kind===kind);
    return `<div class="library-group">${kind==='reference'?'Experimental references':'Your predictions'} · ${group.length}</div>` +
      (group.length?group.map(r=>`<button class="structure-item ${state.selected===r.id?'selected':''}" data-structure="${r.id}"><span class="structure-icon">${kind==='reference'?'◇':'◈'}</span><span><strong>${esc(r.name)}</strong><small>${esc(kind==='reference'?(r.pdb_id?'PDB '+r.pdb_id+' · ':'')+'Experimental':r.sample||'Imported prediction')}</small></span></button>`).join(''):`<p class="small muted" style="padding:3px 10px;font-size:10px">${kind==='prediction'?'Completed predictions will appear here.':'No matching references.'}</p>`);
  }).join('');
  $('library').querySelectorAll('[data-structure]').forEach(b=>b.onclick=()=>{setPage('explore');loadStructure(b.dataset.structure).catch(e=>toast(e.message));});
  const picker=$('structure-picker');
  if(picker) {picker.innerHTML=state.structures.map(r=>`<option value="${r.id}">${esc(structureLabel(r))}</option>`).join(''); picker.value=state.selected||'';}
}
function makeViewer(id) {
  const element=$(id); element.innerHTML='';
  if(!window.$3Dmol) throw new Error('The local 3D viewer did not load. Reload the page.');
  let viewer;
  try {viewer=$3Dmol.createViewer(element,{backgroundColor:'#111f24',antialias:true});}
  catch(error) {element.innerHTML='<div class="viewer-loading">3D rendering needs WebGL enabled in your browser.</div>'; throw error;}
  new ResizeObserver(()=>viewer.resize()).observe(element);
  return viewer;
}
function confidenceColor(atom) {return atom.b>=90?'#1769dc':atom.b>=70?'#58b8db':atom.b>=50?'#efcc53':'#e98a3b';}
function styleViewer(viewer, detail, {style='cartoon',color='chain',hidden=new Set(),conservation=null}={}) {
  viewer.setStyle({},{});
  for(const chain of detail.chains) {
    if(hidden.has(chain.id)) continue;
    const c=colorFor(chain.id,detail);
    const paint=color==='conservation'&&conservation?{colorfunc:a=>conservationAtomColor(a,conservation)}:color==='confidence'&&detail.predicted?{colorfunc:confidenceColor}:{color:c};
    const polymer=['Protein','DNA','RNA'].includes(shortKind(chain.kind));
    let representation;
    if(style==='sphere') representation={stick:{radius:.10,...paint},sphere:{scale:.24,...paint}};
    else if(style==='stick') representation={stick:{radius:.15,...paint}};
    else representation=polymer?{cartoon:{...paint,arrows:true,thickness:.35},stick:{radius:.07,...paint,hidden:true}}:{stick:{radius:.19,...paint},sphere:{scale:.22,...paint}};
    viewer.setStyle({chain:chain.id},representation);
  }
  viewer.render();
}
function applyMainStyle() {
  if(!state.viewer||!state.detail) return;
  state.viewer.removeAllLabels();state.viewer.removeAllShapes();
  styleViewer(state.viewer,state.detail,{style:state.style,color:state.color,hidden:state.hidden,conservation:state.conservation});
  if(state.selectedContact) highlightContact(state.selectedContact,false);
}
async function loadStructure(id) {
  const version=++state.loadVersion;
  state.conservation=null;
  if(state.color==='conservation'){state.color='chain';$('color-mode').value='chain';}
  state.selected=id;state.hidden=new Set();state.selectedContact=null;
  $('selection-note').classList.add('hidden');
  renderLibrary();
  $('structure-title').textContent='Loading structure…';
  $('contact-list').innerHTML='<div class="empty">Calculating contacts from local coordinates…</div>';
  const [detail,response]=await Promise.all([api('/api/structures/'+id),fetch('/api/structures/'+id+'/view')]);
  if(!response.ok) {const error=await response.json();throw new Error(error.error);}
  const cif=await response.text();
  if(version!==state.loadVersion) return;
  state.detail=detail; state.contacts=null;
  $('structure-title').textContent=detail.name;
  $('structure-kind').textContent=detail.kind==='reference'?'EXPERIMENTAL REFERENCE':'ALPHAFOLD 3 PREDICTION';
  $('structure-subtitle').textContent=detail.kind==='reference'?`${detail.pdb_id?'PDB '+detail.pdb_id+' · ':''}Deposited asymmetric unit · First model · Waters omitted`:`${detail.sample||'Imported model'} · ${detail.mode?modeName(detail.mode):'Local prediction'}`;
  $('download-cif').href=`/api/structures/${id}/download`;
  $('viewer-badge').textContent=detail.kind==='reference'?'EXPERIMENTAL · '+(detail.pdb_id||'LOCAL FILE'):'PREDICTED · '+(detail.sample||'LOCAL MODEL');
  $('atom-caption').textContent=fmt(detail.atom_count)+' heavy atoms';
  $('color-mode').querySelector('[value="confidence"]').disabled=!detail.predicted;
  if(!detail.predicted) {state.color='chain';$('color-mode').value='chain';}
  renderStats();
  if(!state.viewer) state.viewer=makeViewer('main-viewer');
  state.viewer.removeAllModels();state.viewer.removeAllLabels();state.viewer.removeAllShapes();
  state.viewer.addModel(cif,'cif',{doAssembly:false,keepH:false});
  applyMainStyle();state.viewer.zoomTo();state.viewer.render();
  state.viewer.setClickable({},true,(atom,viewer)=>{
    const residue=state.detail.residues.find(r=>r.chain===atom.chain&&r.resi===atom.resi);
    viewer.removeAllLabels();viewer.addLabel(`${atom.chain} · ${atom.resn} ${residue?.label||atom.resi}`,{position:atom,fontSize:12,backgroundColor:'#253f35',backgroundOpacity:.95,fontColor:'#eff7e9',borderRadius:4});viewer.render();
  });
  state.viewer.render();
  renderChains();
  await Promise.all([loadContacts(version),renderConfidence(version),initConservation(version)]);
}
function renderStats() {
  const d=state.detail;
  const stats=[['⌬',fmt(d.atom_count),'Heavy atoms'],['⋮',fmt(d.residue_count),'Resolved residues'],['⌁',d.chains.length,'Molecular chains'],['⟷',state.contacts?fmt(state.contacts.count):'…','Residue contacts']];
  $('structure-stats').innerHTML=stats.map(([icon,n,label])=>`<div class="stat"><span class="stat-icon">${icon}</span><div><strong>${n}</strong><small>${label}</small></div></div>`).join('');
}
function renderChains() {
  $('chain-bar').innerHTML='<span>VISIBLE CHAINS</span>'+state.detail.chains.map(c=>`<button class="chain-chip ${state.hidden.has(c.id)?'hidden-chain':''}" data-chain="${esc(c.id)}" title="${esc(c.name)}" aria-pressed="${!state.hidden.has(c.id)}"><span class="chain-dot" style="background:${colorFor(c.id)}"></span>${esc(c.id)} <span class="muted">${esc(shortKind(c.kind))}</span></button>`).join('');
  $('chain-bar').querySelectorAll('button').forEach(button=>button.onclick=()=>{const chain=button.dataset.chain;state.hidden.has(chain)?state.hidden.delete(chain):state.hidden.add(chain);state.selectedContact=null;$('selection-note').classList.add('hidden');renderChains();applyMainStyle();});
}
async function loadContacts(version=state.loadVersion) {
  const id=state.selected, cutoff=$('contact-cutoff').value;
  const data=await api(`/api/structures/${id}/contacts?cutoff=${cutoff}`);
  if(version!==state.loadVersion||id!==state.selected||cutoff!==$('contact-cutoff').value) return;
  state.contacts=data;
  const previous=$('interface-filter').value;
  $('interface-filter').innerHTML='<option value="">All chains</option>'+data.interfaces.map(p=>`<option value="${esc(p.left+'|'+p.right)}">${esc(p.left)} ↔ ${esc(p.right)} (${p.contacts})</option>`).join('');
  if(data.interfaces.some(p=>p.left+'|'+p.right===previous)) $('interface-filter').value=previous;
  $('interface-summary').innerHTML=data.interfaces.slice(0,8).map(p=>`<span class="interface-badge">${esc(p.left)} ↔ ${esc(p.right)} <strong>${p.contacts}</strong></span>`).join('');
  $('download-contacts').href=`/api/structures/${id}/contacts.csv?cutoff=${cutoff}`;
  renderStats();renderContactRows();
  if(state.conservation)drawConservationChart(state.conservation);
}
function renderContactRows() {
  if(!state.contacts) return;
  const filter=$('interface-filter').value;
  // This AF3 checkout writes token-level chain IDs into its summary file.
  const summary=state.detail?.summary,ids=summary?.chain_ids?[...new Set(summary.chain_ids)]:null;
  $('interface-confidence').classList.add('hidden');
  if(filter&&ids&&summary.chain_pair_iptm) {
    const [a,b]=filter.split('|'),i=ids.indexOf(a),j=ids.indexOf(b),score=summary.chain_pair_iptm[i]?.[j];
    if(score!=null){$('interface-confidence').textContent=`${a} ↔ ${b} · Interface ipTM ${fmt(score)} / 1`;$('interface-confidence').classList.remove('hidden');}
  }
  const rows=state.contacts.rows.map((r,i)=>({...r,index:i})).filter(r=>!filter||r.left.chain+'|'+r.right.chain===filter);
  $('contact-count').textContent=fmt(rows.length);
  $('contacts-note').textContent=rows.length>200?`Showing the closest 200 of ${fmt(rows.length)} residue pairs. Export includes all ${fmt(state.contacts.count)} pairs.`:`Minimum heavy-atom separation ≤ ${state.contacts.cutoff.toFixed(1)} Å. Click a pair to inspect it in 3D.`;
  $('contact-list').innerHTML=rows.length?rows.slice(0,200).map(r=>`<button class="contact-row" data-contact="${r.index}"><span class="contact-pair"><span><i class="chain-dot" style="background:${colorFor(r.left.chain)}"></i>${esc(r.left.chain)}:${esc(r.left.resn)} ${esc(r.left.residue_label)}</span><span class="arrow">↔</span><span><i class="chain-dot" style="background:${colorFor(r.right.chain)}"></i>${esc(r.right.chain)}:${esc(r.right.resn)} ${esc(r.right.residue_label)}</span></span><span class="distance">${r.distance.toFixed(2)} Å</span></button>`).join(''):'<div class="empty"><span class="empty-symbol">⌁</span>No inter-chain contacts at this distance.<br>Try a larger cutoff or a complex with multiple chains.</div>';
  $('contact-list').querySelectorAll('button').forEach(button=>button.onclick=()=>{state.selectedContact=state.contacts.rows[Number(button.dataset.contact)];state.hidden.delete(state.selectedContact.left.chain);state.hidden.delete(state.selectedContact.right.chain);applyMainStyle();highlightContact(state.selectedContact,true);renderChains();document.querySelectorAll('.contact-row').forEach(b=>b.classList.toggle('active',b===button));});
}
function highlightContact(row, zoom) {
  const viewer=state.viewer;viewer.removeAllLabels();viewer.removeAllShapes();
  for(const a of [row.left,row.right]) {viewer.addStyle({chain:a.chain,resi:a.resi},{stick:{radius:.22,color:colorFor(a.chain)},sphere:{scale:.23,color:colorFor(a.chain)}});viewer.addLabel(`${a.chain}:${a.resn} ${a.residue_label}`,{position:a,fontSize:11,backgroundColor:'#2b3f37',backgroundOpacity:.9,fontColor:'#e9f2de'});}
  viewer.addCylinder({start:row.left,end:row.right,radius:.06,color:'#f0d091',fromCap:1,toCap:1});
  if(zoom) viewer.zoomTo({or:[{chain:row.left.chain,resi:row.left.resi},{chain:row.right.chain,resi:row.right.resi}]},350);
  viewer.render();
  $('selection-note').classList.remove('hidden');
  $('selection-note').querySelector('span').textContent=`${row.left.chain}:${row.left.resn} ${row.left.residue_label} ↔ ${row.right.chain}:${row.right.resn} ${row.right.residue_label} · ${row.distance.toFixed(2)} Å (${row.left.atom}–${row.right.atom})`;
}
async function renderConfidence(version) {
  const detail=state.detail;
  $('confidence-badge').textContent=detail.predicted?'AF3 confidence':'Experimental';
  if(!detail.predicted) {$('confidence-content').innerHTML='<div class="confidence-empty"><span class="empty-symbol">◇</span><p>This is an experimental structure from your local PDB archive. AF3 confidence scores do not apply.<br>Run a prediction to explore pLDDT, interface confidence, and predicted aligned error.</p></div>';return;}
  const summary=detail.summary||{};
  const atomWeighted=detail.chains.reduce((sum,c)=>sum+(c.plddt||0)*c.atoms,0)/detail.atom_count;
  $('confidence-content').innerHTML=`<div class="confidence-metrics"><div><strong>${fmt(atomWeighted)}</strong><small>Mean pLDDT / 100</small></div><div><strong>${fmt(summary.iptm)}</strong><small>Interface ipTM / 1</small></div><div><strong>${fmt(summary.ptm)}</strong><small>Global pTM / 1</small></div></div><div class="plddt-legend"><span style="--color:#1769dc">Very high ≥ 90</span><span style="--color:#58b8db">Confident ≥ 70</span><span style="--color:#efcc53">Low ≥ 50</span><span style="--color:#e98a3b">Very low &lt; 50</span></div><div id="pae-region"></div><p class="scientific-note">Confidence estimates describe the predicted structure, not binding strength. ${summary.has_clash?'This model has a significant atom-clash flag.':''}</p>`;
  const conf=await api(`/api/structures/${detail.id}/confidence`);
  if(version!==state.loadVersion) return;
  if(!conf.pae?.length) {$('pae-region').innerHTML='<p class="panel-description">No accompanying PAE file is available for this imported structure.</p>';return;}
  $('pae-region').innerHTML='<div class="pae-layout"><canvas id="pae-canvas" class="pae-plot" width="480" height="480" role="img" aria-label="Predicted aligned error heatmap"></canvas><div class="pae-legend"><h3>Predicted aligned error</h3><p>Dark regions indicate greater confidence in relative token positions. Lines mark chain boundaries.</p><div class="gradient-bar"></div><div class="legend-values"><span>0 Å · lower error</span><span>30 Å</span></div><p id="pae-readout" style="margin-top:15px">Hover over the map for a value.</p></div></div>';
  const canvas=$('pae-canvas'),ctx=canvas.getContext('2d'),n=conf.pae.length,size=440,pad=24;
  const temp=document.createElement('canvas');temp.width=temp.height=n;const tc=temp.getContext('2d'),pixels=tc.createImageData(n,n);
  for(let y=0;y<n;y++) for(let x=0;x<n;x++){const v=Math.max(0,Math.min(1,conf.pae[y][x]/30)),o=(y*n+x)*4;pixels.data[o]=22+v*220;pixels.data[o+1]=75+v*171;pixels.data[o+2]=56+v*179;pixels.data[o+3]=255;}
  tc.putImageData(pixels,0,0);ctx.imageSmoothingEnabled=false;ctx.drawImage(temp,pad,pad,size,size);
  const ids=conf.token_chain_ids||[];const ranges=[];
  for(let i=0;i<ids.length;i++)if(i===0||ids[i]!==ids[i-1]){if(ranges.length)ranges[ranges.length-1].end=i;ranges.push({id:ids[i],start:i,end:n});}
  ctx.font='14px sans-serif';ctx.fillStyle='#65765e';ctx.textAlign='center';
  for(const range of ranges){const pos=pad+(range.start+range.end)/2/n*size;ctx.fillText(range.id,pos,17);ctx.fillText(range.id,11,pos+4);if(range.start){const v=pad+range.start/n*size;ctx.strokeStyle='#fff9';ctx.beginPath();ctx.moveTo(v,pad);ctx.lineTo(v,pad+size);ctx.moveTo(pad,v);ctx.lineTo(pad+size,v);ctx.stroke();}}
  canvas.onmousemove=event=>{const rect=canvas.getBoundingClientRect(),x=Math.floor(((event.clientX-rect.left)/rect.width*480-pad)/size*n),y=Math.floor(((event.clientY-rect.top)/rect.height*480-pad)/size*n);if(x>=0&&y>=0&&x<n&&y<n)$('pae-readout').textContent=`Aligned on ${ids[y]||'?'} token ${y+1} → ${ids[x]||'?'} token ${x+1}: ${conf.pae[y][x].toFixed(2)} Å`;};
}

function updateCompareOptions() {
  for(const side of ['left','right']) {const select=$('compare-'+side),current=select.value;select.innerHTML=state.structures.map(r=>`<option value="${r.id}">${esc(structureLabel(r))} ${r.pdb_id?'· '+r.pdb_id:''}</option>`).join('');if(state.structures.some(r=>r.id===current))select.value=current;else select.value=(side==='left'?state.selected:state.structures.find(r=>r.id!==state.selected)?.id)||state.structures[0]?.id||'';}
}
async function loadComparison() {
  const version=++state.compareVersion;
  $('alignment-result').classList.add('hidden');
  await Promise.all(['left','right'].map(async side=>{
    const id=$('compare-'+side).value;if(!id)return;
    const [detail,response,contact]=await Promise.all([api('/api/structures/'+id),fetch('/api/structures/'+id+'/view'),api(`/api/structures/${id}/contacts?cutoff=4.5`)]);
    if(!response.ok)throw new Error('Could not load comparison coordinates.');const cif=await response.text();
    if(version!==state.compareVersion) return;
    const old=state.compare[side];const viewer=old?.viewer||makeViewer('compare-view-'+side);
    viewer.removeAllModels();viewer.removeAllLabels();viewer.addModel(cif,'cif',{doAssembly:false,keepH:false});styleViewer(viewer,detail);viewer.zoomTo();viewer.render();
    state.compare[side]={viewer,detail,cif};
    $('compare-info-'+side).innerHTML=`<strong>${fmt(detail.residue_count)}</strong> residues &nbsp;·&nbsp; <strong>${detail.chains.length}</strong> chains &nbsp;·&nbsp; <strong>${fmt(contact.count)}</strong> contacts at 4.5 Å<br>${detail.predicted?'Prediction · ipTM '+fmt(detail.summary?.iptm):'Experimental reference · '+esc(detail.pdb_id||'Local file')}`;
    const chains=detail.chains.filter(c=>shortKind(c.kind)==='Protein');
    $('align-'+side).innerHTML=chains.map(c=>`<option>${esc(c.id)}</option>`).join('');
  }));
}
async function alignComparison() {
  const left=state.compare.left,right=state.compare.right;if(!left||!right)return;
  $('align-button').disabled=true;
  try {
    const result=await api('/api/align',{left:left.detail.id,right:right.detail.id,left_chain:$('align-left').value,right_chain:$('align-right').value});
    right.viewer.removeAllModels();right.viewer.addModel(right.cif,'cif',{doAssembly:false,keepH:false});
    const model=right.viewer.getModel();
    for(const atom of model.selectedAtoms({})) {const p=[atom.x,atom.y,atom.z],q=[0,0,0];for(let j=0;j<3;j++)q[j]=p.reduce((s,v,i)=>s+v*result.rotation[i][j],result.translation[j]);[atom.x,atom.y,atom.z]=q;}
    styleViewer(right.viewer,right.detail);right.viewer.setView(left.viewer.getView());right.viewer.render();
    $('alignment-result').classList.remove('hidden');$('alignment-result').textContent=`Cα RMSD ${result.rmsd.toFixed(3)} Å across ${result.matched_atoms} matched atoms. Structure B is aligned to A. Cameras now share the same orientation.`;
  } catch(error) {$('alignment-result').classList.remove('hidden');$('alignment-result').textContent=error.message;}
  finally {$('align-button').disabled=false;}
}

function loadDraft(raw,presetId=null) {
  if(!raw||typeof raw!=='object'||Array.isArray(raw)||!Array.isArray(raw.sequences)) throw new Error('Load one AF3 JSON object containing a sequences array.');
  state.draft=structuredClone(raw);state.jsonMode=false;
  $('experiment-name').disabled=false;$('experiment-seeds').disabled=false;
  $('experiment-name').value=raw.name;$('experiment-seeds').value=(raw.modelSeeds||[42]).join(', ');
  $('validation-message').innerHTML='';
  document.querySelectorAll('.preset-button').forEach(b=>b.classList.toggle('selected',b.dataset.preset===presetId));
  $('builder-pane').classList.remove('hidden');$('json-pane').classList.add('hidden');$('builder-tab').classList.add('selected');$('json-tab').classList.remove('selected');renderMolecules();
}
function openExperiment(raw=null) {
  loadDraft(raw||state.presets.find(p=>p.id==='tetr_homodimer')?.input||{name:'My experiment',sequences:[{protein:{id:'A',sequence:''}}],modelSeeds:[42],dialect:'alphafold3',version:4},raw?null:'tetr_homodimer');
  $('run-mode').value='full';modeNote();$('experiment-dialog').showModal();resetFinder();
}
function renderMolecules() {
  $('molecule-list').innerHTML=state.draft.sequences.map((entry,i)=>{
    const [kind,m]=Object.entries(entry)[0];const ids=Array.isArray(m.id)?m.id.join(', '):m.id;
    const content=kind==='ligand'?(m.smiles||m.ccdCodes?.join(', ')||''):(m.sequence||'');
    return `<div class="molecule-card" data-molecule="${i}"><div class="molecule-top"><select class="molecule-type" aria-label="Molecule ${i+1} type">${['protein','dna','rna','ligand'].map(k=>`<option value="${k}" ${kind===k?'selected':''}>${{protein:'Protein',dna:'DNA',rna:'RNA',ligand:'Ligand / ion'}[k]}</option>`).join('')}</select><span class="chain-hint">Chain IDs</span><input class="molecule-ids" value="${esc(ids)}" placeholder="A, B" aria-label="Molecule ${i+1} chain IDs"><button class="remove-molecule" aria-label="Remove molecule ${i+1}">×</button></div><label class="sr-only">${kind==='ligand'?'Ligand definition':'Sequence'}</label><textarea class="molecule-sequence" aria-label="Molecule ${i+1} ${kind==='ligand'?'definition':'sequence'}" spellcheck="false" placeholder="${kind==='ligand'?'CCD code (e.g. TAC), or select SMILES':'Paste the sequence (one-letter codes)'}">${esc(content)}</textarea><div class="molecule-caption"><span>${kind==='ligand'?'Ligand definition':`${content.length} residues · ${Array.isArray(m.id)?m.id.length:1} chain(s)`}${m.modifications?.length?' · Modifications preserved':''}</span>${kind==='ligand'?`<select class="ligand-format" aria-label="Ligand format"><option value="ccd" ${!m.smiles?'selected':''}>CCD codes</option><option value="smiles" ${m.smiles?'selected':''}>SMILES</option></select>`:''}${kind==='dna'?'<button class="text-button add-complement">+ Complementary strand</button>':''}</div></div>`;
  }).join('');
  renderDraftSummary();
  $('molecule-list').querySelectorAll('.molecule-card').forEach(card=>{
    const i=Number(card.dataset.molecule);
    const complement=card.querySelector('.add-complement');if(complement)complement.onclick=()=>{try{addComplement(i);}catch(error){toast(error.message);}};
    card.querySelector('.molecule-type').onchange=()=>{syncBuilder();const kind=card.querySelector('.molecule-type').value;const previous=Object.values(state.draft.sequences[i])[0];state.draft.sequences[i]={[kind]:{id:previous.id,...(kind==='ligand'?{ccdCodes:[]}:{sequence:''})}};renderMolecules();};
    card.querySelector('.remove-molecule').onclick=()=>{syncBuilder();state.draft.sequences.splice(i,1);renderMolecules();};
  });
}
function syncBuilder() {
  $('molecule-list').querySelectorAll('.molecule-card').forEach(card=>{
    const index=Number(card.dataset.molecule),entry=state.draft.sequences[index];
    const [kind,m]=Object.entries(entry)[0],ids=card.querySelector('.molecule-ids').value.split(',').map(v=>v.trim()).filter(Boolean);
    m.id=ids.length===1?ids[0]:ids;
    let content=card.querySelector('.molecule-sequence').value.trim();
    if(kind==='ligand') {if(card.querySelector('.ligand-format').value==='smiles'){m.smiles=content;delete m.ccdCodes;}else {m.ccdCodes=content.split(',').map(v=>v.trim()).filter(Boolean);delete m.smiles;}}
    else m.sequence=content.replace(/\s/g,'').toUpperCase();
  });
}
function collectInput() {
  if(state.jsonMode) {
    const draft=JSON.parse($('input-json').value);
    if(!draft||typeof draft!=='object'||Array.isArray(draft)||!Array.isArray(draft.sequences)) throw new Error('Supply one AF3 JSON object with a sequences array.');
    state.draft=draft;
    $('experiment-name').value=draft.name||'';$('experiment-seeds').value=(draft.modelSeeds||[]).join(', ');
    return state.draft;
  }
  syncBuilder();
  state.draft.name=$('experiment-name').value.trim();
  const parts=$('experiment-seeds').value.split(',').map(v=>v.trim());
  if(parts.some(v=>!/^\d+$/.test(v)))throw new Error('Enter comma-separated nonnegative integer seeds, such as 42, 43.');
  state.draft.modelSeeds=parts.map(Number);
  return state.draft;
}
function switchEditor(jsonMode) {
  const draft=collectInput();state.jsonMode=jsonMode;
  $('json-pane').classList.toggle('hidden',!jsonMode);$('builder-pane').classList.toggle('hidden',jsonMode);
  $('json-tab').classList.toggle('selected',jsonMode);$('builder-tab').classList.toggle('selected',!jsonMode);
  $('experiment-name').disabled=jsonMode;$('experiment-seeds').disabled=jsonMode;
  if(jsonMode)$('input-json').value=JSON.stringify(draft,null,2);else renderMolecules();
}
function modeNote() {
  const notes={full:'Search the downloaded sequence databases, build MSAs and templates, then predict the 3D structure. Searches are CPU- and memory-intensive and may take hours.',prepare:'Search your local databases and save reusable MSAs and templates. No structure prediction runs in this mode.',quick:'Predict without sequence alignments or templates. Useful for checking the runtime; it may give substantially worse structures. Existing MSAs and templates are cleared for this run.',inference:'Use an input with inline MSAs and templates already supplied. The database search is skipped.'};
  $('run-mode-note').textContent=notes[$('run-mode').value];
  $('run-backend').disabled=$('run-mode').value==='prepare';
}
async function submitJob() {
  $('queue-job').disabled=true;
  try {const job=await api('/api/jobs',{input:collectInput(),mode:$('run-mode').value,backend:$('run-backend').value,samples:Number($('run-samples').value),recycles:Number($('run-recycles').value)});state.jobs.unshift(job);state.job=job.id;$('experiment-dialog').close();setPage('experiments');await selectJob(job.id);toast('Experiment added to your local queue.');}
  catch(error){message('validation-message',error.message);}
  finally{$('queue-job').disabled=false;}
}
function renderJobs() {
  $('job-count').textContent=state.jobs.filter(j=>['running','queued','cancelling'].includes(j.status)).length||state.jobs.length;
  $('job-list').innerHTML=state.jobs.length?state.jobs.map(j=>`<button class="job-card ${state.job===j.id?'selected':''}" data-job="${j.id}"><div class="job-card-header"><strong>${esc(j.name)}</strong><span class="status-tag ${esc(j.status)}">${esc(j.status)}</span></div><p>${esc(modeName(j.mode))}<br>${new Date(j.created_at).toLocaleString([], {month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})} · ${j.backend.toUpperCase()}</p></button>`).join(''):'<div class="empty">Your experiments will appear here.<br>Start with a small protein or a TetR example.</div>';
  $('job-list').querySelectorAll('button').forEach(b=>b.onclick=()=>selectJob(b.dataset.job).catch(e=>toast(e.message)));
  if(!state.job&&state.jobs.length) selectJob(state.jobs[0].id).catch(e=>toast(e.message));
}
function phaseFromLog(log, job) {
  if(job.status!=='running')return job.stage;
  if(job.kind==='conservation') {
    if(/Mapping scores/.test(log))return 'Mapping scores to structure residues';
    if(/calculating rate4site/.test(log))return 'Inferring evolutionary rates and an evolutionary tree';
    if(/calculating entropy/.test(log))return 'Calculating weighted sequence conservation';
    if(/Filtering homologues/.test(log))return 'Filtering and aligning related sequences';
    if(/Searching /.test(log))return 'Searching local sequences with Jackhmmer';
    return job.stage;
  }
  if(/Writing outputs|Writing output|post.processing/i.test(log))return 'Writing predictions and confidence files';
  if(/Running model inference|Running inference|Predicting 3D structure/i.test(log))return 'Running model inference · compilation can take time';
  if(/Featurising|Featurizing/i.test(log))return 'Preparing model features';
  if(/jackhmmer|nhmmer|Running data pipeline|Searching/i.test(log))return 'Searching local databases and preparing alignments';
  if(/Building model|parameters|Found local/i.test(log))return 'Loading weights and compiling the model';
  return job.stage;
}
async function selectJob(id) {
  state.job=id;renderJobs();
  const result=await api(`/api/jobs/${id}/log`);if(state.job!==id)return;
  renderJobDetail(result.job,result.log);
}
function renderJobDetail(job, log) {
  if(job.kind==='conservation')return renderConservationJob(job,log);
  const active=['running','queued','cancelling'].includes(job.status);
  const result=state.structures.find(r=>r.job_id===job.id&&r.sample==='Best ranked');
  $('job-detail').innerHTML=`<div class="job-title-row"><div><div class="eyebrow muted">EXPERIMENT / ${job.id}</div><h2 style="font-size:23px;margin-top:8px">${esc(job.name)}</h2></div><span class="status-tag ${esc(job.status)}">${esc(job.status)}</span></div><div class="job-meta"><span>${esc(modeName(job.mode))}</span><span>${job.backend.toUpperCase()}</span><span>${job.seeds.length} seed(s) × ${job.samples} sample(s)</span><span>${job.recycles} recycles</span></div><div class="job-stage">${active?'<span class="spinner"></span>':'<span>◇</span>'}<span>${esc(phaseFromLog(log,job))}</span></div>${job.mode==='quick'?'<p class="notice">Sequence-only run: no database alignments or structural templates were used.</p>':''}<div class="job-actions"><a class="secondary" href="/api/jobs/${job.id}/input">↓ Input JSON</a>${job.prepared_input?`<a class="secondary" href="/api/jobs/${job.id}/prepared">↓ Prepared input</a>`:''}${job.mode==='prepare'&&job.prepared_input?'<button id="predict-prepared" class="primary">Predict prepared input →</button>':''}${result?'<button id="view-job-result" class="primary">Explore result →</button>':''}${active?'<button id="cancel-job" class="secondary">Cancel job</button>':'<button id="rerun-job" class="secondary">Use input again</button><button id="delete-job" class="secondary danger">Delete</button>'}</div>${job.error?`<div class="job-error">${esc(job.error)}</div>`:''}<div class="log-heading"><span>LIVE PROCESS LOG</span><span>${active?'UPDATING EVERY 3 SECONDS':'SAVED LOCALLY'}</span></div><pre class="job-log" id="job-log">${esc(log||'Waiting for the worker to start…')}</pre><p class="small muted" style="margin-top:12px">Output folder<br><code>${esc(job.output_dir)}</code></p>`;
  if($('cancel-job'))on('cancel-job','click',async()=>{await api(`/api/jobs/${job.id}/cancel`,{});await refresh();await selectJob(job.id);});
  if($('rerun-job'))on('rerun-job','click',async()=>{openExperiment(await api(`/api/jobs/${job.id}/input`));$('run-mode').value=job.mode;modeNote();});
  if($('delete-job'))on('delete-job','click',()=>deleteJob(job));
  if($('view-job-result'))on('view-job-result','click',async()=>{setPage('explore');await loadStructure(result.id);});
  if($('predict-prepared'))on('predict-prepared','click',async()=>{const next=await api('/api/jobs',{prepared_job:job.id,mode:'inference',backend:job.backend,samples:job.samples,recycles:job.recycles});await refresh();await selectJob(next.id);});
  const el=$('job-log');el.scrollTop=el.scrollHeight;
}
async function deleteJob(job) {
  const structures=state.structures.filter(r=>r.job_id===job.id);
  const analyses=state.jobs.filter(j=>j.kind==='conservation'&&structures.some(r=>r.id===j.structure_id));
  const effects=[structures.length?`${structures.length} predicted structure${structures.length===1?'':'s'} will be removed from your library.`:'',
    analyses.length?`${analyses.length} conservation analys${analyses.length===1?'is':'es'} of ${structures.length===1?'it':'them'} will also be deleted.`:''].filter(Boolean).join(' ');
  if(!confirm(`Delete “${job.name}”?\n\nIts input, log, and output files will be permanently removed from this Mac. ${effects}`))return;
  await api(`/api/jobs/${job.id}/delete`,{});
  state.job=null;
  await refresh();renderJobs();
  if(!state.jobs.length){$('job-detail').innerHTML=state.emptyJobDetail;on('empty-new','click',()=>openExperiment());}
  toast(`Deleted “${job.name}”.`);
}
async function refresh() {
  const data=await api('/api/state');
  $('connection-warning').classList.add('hidden');
  const changed=JSON.stringify(data.structures)!==JSON.stringify(state.structures);
  const jobsChanged=JSON.stringify(data.jobs)!==JSON.stringify(state.jobs);
  const conservationChanged=JSON.stringify(data.conservation_runs||[])!==JSON.stringify(state.conservationRuns);
  state.conservationRuns=data.conservation_runs||[];
  state.structures=data.structures;state.jobs=data.jobs;
  if(changed) {
    renderLibrary();
    if(state.selected&&!state.structures.some(r=>r.id===state.selected))state.selected=null;
    if(!state.selected&&state.structures.length)await loadStructure(state.structures[0].id);
  }
  if(jobsChanged)renderJobs();
  if(conservationChanged&&state.detail&&$('conservation-chain').value){const runs=conservationRunOptions();await loadConservation(runs[0]?.id||'');}
  if(state.page==='experiments'&&state.job) {
    const data=await api(`/api/jobs/${state.job}/log`);
    if(data.job.id!==state.job)return;
    if(jobsChanged||!$('job-log'))renderJobDetail(data.job,data.log);
    else {const log=$('job-log'),bottom=log.scrollTop+log.clientHeight>=log.scrollHeight-45;log.textContent=data.log||'Waiting for the worker to start…';if(bottom)log.scrollTop=log.scrollHeight;const stage=$('job-detail').querySelector('.job-stage span:last-child');if(stage)stage.textContent=phaseFromLog(data.log,data.job);}
  }
}
async function importData(data) {
  try {const result=await api('/api/import',data);await refresh();$('import-dialog').close();setPage('explore');if(result.structures[0])await loadStructure(result.structures[0].id);toast(`Added ${result.structures.length} structure(s) to your library.`);}
  catch(error){message('import-message',error.message);}
}
function renderSystem(status) {
  $('system-caption').textContent=status.database_ready&&status.weights_ready?'Databases & weights found':'Some files need attention';
  $('system-dot').classList.toggle('bad',!status.database_ready||!status.weights_ready);
  $('system-content').innerHTML=`<p class="small muted">Database location</p><div class="system-path">${esc(status.db_dir)}</div><p class="small muted">Model weights</p><div class="system-path">${esc(status.model_dir)}</div><div class="system-row"><span>af3.bin model weights</span><b class="${status.weights_ready?'ok':''}">${status.weights_ready?'Found':'Missing'}</b></div>${status.databases.map(f=>`<div class="system-row"><code>${esc(f.name)}</code><span class="${f.present?'ok':''}">${f.present?(f.bytes?(f.bytes/1024**3).toFixed(1)+' GiB':'Found'):'Missing'}</span></div>`).join('')}<p class="small muted">Search tools</p>${Object.entries(status.tools).map(([name,path])=>`<div class="system-row"><span>${esc(name)}</span><span class="${path?'ok':''}">${path?'Found':'Missing'}</span></div>`).join('')}<p class="small muted">${esc(status.note)} ${status.cpu_count} logical CPU cores detected. The Apple Silicon backend is experimental.</p><p class="small muted">Explorer outputs</p><div class="system-path">${esc(status.data_dir)}</div>`;
}
async function init() {
  document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>setPage(b.dataset.page));
  document.querySelectorAll('.close-dialog').forEach(b=>b.onclick=()=>b.closest('dialog').close());
  on('structure-search','input',renderLibrary);
  on('structure-picker','change',()=>loadStructure($('structure-picker').value));
  on('mobile-import','click',()=>{$('import-message').innerHTML='';$('import-dialog').showModal();});
  on('new-experiment','click',()=>openExperiment());on('empty-new','click',()=>openExperiment());
  on('import-open','click',()=>{$('import-message').innerHTML='';$('import-dialog').showModal();});
  on('system-open','click',async()=>{renderSystem(await api('/api/status'));$('system-dialog').showModal();});
  on('reset-view','click',()=>{state.viewer.zoomTo();state.viewer.render();});
  on('clear-selection','click',()=>{state.selectedContact=null;$('selection-note').classList.add('hidden');applyMainStyle();});
  document.querySelectorAll('[data-style]').forEach(b=>b.onclick=()=>{state.style=b.dataset.style;document.querySelectorAll('[data-style]').forEach(x=>x.classList.toggle('selected',x===b));applyMainStyle();});
  on('color-mode','change',()=>{state.color=$('color-mode').value;applyMainStyle();});
  on('contact-cutoff','change',async()=>{await loadContacts();if(state.conservation)await loadConservation();});on('interface-filter','change',renderContactRows);
  on('compare-current','click',()=>{updateCompareOptions();$('compare-left').value=state.selected;setPage('compare');});
  on('compare-left','change',loadComparison);on('compare-right','change',loadComparison);on('align-button','click',alignComparison);
  on('compare-reset','click',loadComparison);
  on('builder-tab','click',()=>switchEditor(false));on('json-tab','click',()=>switchEditor(true));
  on('add-molecule','click',()=>{syncBuilder();const ids=state.draft.sequences.flatMap(s=>Object.values(s)[0].id);let i=0;while(ids.includes(String.fromCharCode(65+i)))i++;state.draft.sequences.push({protein:{id:String.fromCharCode(65+i),sequence:''}});renderMolecules();});
  on('blank-input','click',()=>loadDraft({name:'My experiment',sequences:[{protein:{id:'A',sequence:''}}],modelSeeds:[42],dialect:'alphafold3',version:4}));
  on('json-upload','change',async e=>{const file=e.target.files[0];if(file){loadDraft(JSON.parse(await file.text()));e.target.value='';}});
  on('run-mode','change',modeNote);on('queue-job','click',submitJob);
  on('validate-input','click',async()=>{try{const result=await api('/api/validate',{input:collectInput(),mode:$('run-mode').value});message('validation-message',`Input is valid. ${result.input.sequences.length} molecule entries, ${result.input.modelSeeds.length} seed(s).`,true);}catch(error){message('validation-message',error.message);}});
  on('import-pdb','click',()=>importData({pdb_id:$('pdb-code').value}));
  on('import-folder','click',()=>importData({path:$('import-path').value,kind:$('import-predicted').checked?'prediction':'reference'}));
  on('cif-upload','change',async e=>{const file=e.target.files[0];if(file){await importData({cif:await file.text(),name:file.name,kind:$('import-predicted').checked?'prediction':'reference'});e.target.value='';}});
  setupConservation();setupFinder();
  state.emptyJobDetail=$('job-detail').innerHTML;
  const initial=await api('/api/bootstrap');Object.assign(state,{token:initial.token,structures:initial.structures,presets:initial.presets,jobs:initial.jobs,conservationRuns:initial.conservation_runs||[],rate4site:initial.status.rate4site});
  $('run-backend').value=initial.status.backend_default;renderSystem(initial.status);renderLibrary();renderJobs();
  $('preset-list').innerHTML=state.presets.map(p=>`<button class="preset-button" data-preset="${esc(p.id)}"><strong>${esc(p.name)}</strong><small>${esc(p.description)}</small></button>`).join('');
  document.querySelectorAll('.preset-button').forEach(b=>b.onclick=()=>loadDraft(state.presets.find(p=>p.id===b.dataset.preset).input,b.dataset.preset));
  if(state.structures.length)await loadStructure(state.structures[0].id);
  else {$('main-viewer').innerHTML='<div class="viewer-loading">Import a local mmCIF or run your first prediction.</div>';$('structure-title').textContent='Your structure library is empty';}
  let refreshing=false;
  setInterval(async()=>{if(refreshing||document.hidden)return;refreshing=true;try{await refresh();}catch(error){$('connection-warning').classList.remove('hidden');}finally{refreshing=false;}},3000);
}
init().catch(error=>{toast(error.message);$('connection-warning').classList.remove('hidden');$('connection-warning').textContent='Could not finish loading: '+error.message;});
