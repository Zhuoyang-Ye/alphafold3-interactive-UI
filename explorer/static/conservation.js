'use strict';

function conservationColor(score) {
  if(score==null)return '#899495';
  const low=[80,139,120],mid=[238,242,218],high=[166,73,140];
  const a=score<.5?low:mid,b=score<.5?mid:high,t=score<.5?score*2:(score-.5)*2;
  return '#'+a.map((v,i)=>Math.round(v+(b[i]-v)*t).toString(16).padStart(2,'0')).join('');
}
function conservationAtomColor(atom,profile) {
  if(atom.chain!==profile.chain)return '#506368';
  if(!profile._colorMap)profile._colorMap=new Map(profile.residues.map(r=>[r.resi,conservationColor(r.score)]));
  return profile._colorMap.get(atom.resi)||'#899495';
}
function conservationRunOptions() {
  const chain=$('conservation-chain').value,previous=$('conservation-run').value;
  const runs=state.conservationRuns.filter(r=>r.structure_id===state.selected&&r.chain===chain);
  $('conservation-run').innerHTML=runs.length?runs.map(r=>`<option value="${r.id}">${r.method==='rate4site'?'Rate4Site':'Weighted entropy'} · ${r.sequence_count} sequences · ${new Date(r.finished_at).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'})}</option>`).join(''):'<option value="">No analysis yet</option>';
  if(runs.some(r=>r.id===previous))$('conservation-run').value=previous;
  return runs;
}
async function initConservation(version) {
  state.conservation=null;state.conservationSources=null;
  const chains=state.detail.chains.filter(c=>c.sequence&&shortKind(c.kind)==='Protein');
  $('conservation-chain').innerHTML=chains.map(c=>`<option value="${esc(c.id)}">${esc(c.id)} · ${c.sequence.length} aa</option>`).join('');
  $('conservation-open').disabled=!chains.length;
  $('conservation-color').disabled=true;
  $('color-mode').querySelector('[value="conservation"]').disabled=true;
  if(!chains.length){$('conservation-content').innerHTML='<div class="confidence-empty"><p>Select a structure containing a protein chain to calculate amino-acid conservation.</p></div>';return;}
  conservationRunOptions();
  if(version===state.loadVersion)await loadConservation();
}
async function loadConservation(runId=$('conservation-run').value) {
  const version=++state.conservationVersion,id=state.selected,chain=$('conservation-chain').value;
  if(!id||!chain)return;
  const partner=$('conservation-partner')?.value||'';
  const url=`/api/structures/${id}/conservation?chain=${encodeURIComponent(chain)}&cutoff=${$('contact-cutoff').value}${runId?'&run='+runId:''}${partner?'&partner='+encodeURIComponent(partner):''}`;
  const data=await api(url);
  if(version!==state.conservationVersion||id!==state.selected||chain!==$('conservation-chain').value)return;
  state.conservation=data.result;
  $('conservation-color').disabled=!data.result;
  $('color-mode').querySelector('[value="conservation"]').disabled=!data.result;
  if(!data.result){
    if(state.color==='conservation'){state.color='chain';$('color-mode').value='chain';applyMainStyle();}
    const running=state.jobs.find(j=>j.kind==='conservation'&&j.structure_id===id&&j.chain===chain&&['running','queued'].includes(j.status));
    $('conservation-content').innerHTML=`<div class="confidence-empty"><span class="empty-symbol">⌁</span><p>${running?'A conservation analysis is '+esc(running.status)+'. Follow its progress under Experiments.':'No conservation analysis for this chain yet. Reuse an AF3 alignment, upload aligned sequences, or search your local databases.'}</p></div>`;
    return;
  }
  conservationRunOptions();$('conservation-run').value=data.result.job_id;
  renderConservation(data.result,data.interface_comparison,partner);
  if(state.color==='conservation')applyMainStyle();
}
function renderConservation(profile,comparison,partner) {
  const supported=profile.supported_positions;
  const partners=state.detail.chains.filter(c=>c.id!==profile.chain);
  $('conservation-content').innerHTML=`<div class="conservation-metrics"><div><strong>${profile.sequence_count}</strong><small>Aligned sequences retained</small></div><div><strong>${supported} / ${profile.positions.length}</strong><small>Positions with sufficient coverage</small></div><div><strong>${profile.mapped_residues}</strong><small>Resolved residues mapped to sequence</small></div></div><p class="conservation-source-line"><strong>${esc(profile.method_label)}</strong><br>${esc(profile.source_label)} · Weighted effective alignment size ${fmt(profile.effective_sequences)}<br>${esc(profile.score_description)}</p><div class="conservation-legend"><span>0 · lower conservation</span><span class="conservation-gradient"></span><span>100 · higher conservation</span><span><i class="chain-dot"></i> Insufficient data</span></div><div class="conservation-chart-wrap"><canvas id="conservation-chart" class="conservation-chart" width="960" height="210" role="img" aria-label="Conservation by query sequence position; gray bars indicate insufficient alignment coverage"></canvas></div><div class="conservation-jump"><label for="conservation-position">Inspect query position</label><input id="conservation-position" type="number" min="1" max="${profile.positions.length}" value="1"><button id="conservation-inspect" class="secondary">Inspect</button><span class="muted">Dots mark contact residues.</span></div><div id="conservation-readout" class="conservation-readout">Hover over the sequence chart for scores; click a position to locate it in 3D.</div><div class="conservation-interface"><h4>Are contact residues more conserved?</h4><label>Binding partner<select id="conservation-partner"><option value="">Any other chain</option>${partners.map(c=>`<option value="${esc(c.id)}">${esc(c.id)} · ${esc(shortKind(c.kind))}</option>`).join('')}</select></label><div id="conservation-interface-content"></div></div><div class="conservation-actions"><a class="text-button" href="/api/jobs/${profile.job_id}/scores">↓ Residue scores CSV</a><a class="text-button" href="/api/jobs/${profile.job_id}/alignment">↓ Filtered alignment</a>${profile.method==='rate4site'?`<a class="text-button" href="/api/jobs/${profile.job_id}/rates">↓ Raw Rate4Site scores</a><a class="text-button" href="/api/jobs/${profile.job_id}/tree">↓ Evolutionary tree</a>`:''}</div><div class="conservation-warnings">${profile.warnings.map(w=>`<p>${esc(w)}</p>`).join('')}</div><details class="conservation-homologues"><summary>Inspect selected homologues (${profile.sequence_count})</summary><table><thead><tr><th>SEQUENCE / DESCRIPTION</th><th>IDENTITY</th><th>COVERAGE</th></tr></thead><tbody>${profile.homologues.slice(0,50).map(h=>`<tr><td>${esc(h.name)}</td><td>${Math.round(h.identity*100)}%</td><td>${Math.round(h.coverage*100)}%</td></tr>`).join('')}</tbody></table>${profile.sequence_count>50?'<p class="small muted">Showing the first 50; the alignment export includes every selected sequence.</p>':''}</details><p class="scientific-note">Conservation reflects constraints within the sampled protein family. It can suggest functional or structural importance. Alignment diversity, coverage, and sampling affect the result.</p>`;
  $('conservation-partner').value=partner;
  renderInterfaceComparison(comparison);
  drawConservationChart(profile);
  on('conservation-partner','change',async()=>{
    const selected=$('conservation-partner').value;
    const data=await api(`/api/structures/${state.selected}/conservation?chain=${encodeURIComponent(profile.chain)}&run=${profile.job_id}&cutoff=${$('contact-cutoff').value}&partner=${encodeURIComponent(selected)}`);
    if(state.conservation?.job_id!==profile.job_id)return;
    renderInterfaceComparison(data.interface_comparison);drawConservationChart(profile);
  });
  on('conservation-inspect','click',()=>inspectConservationPosition(Number($('conservation-position').value),true));
}
function renderInterfaceComparison(comparison) {
  const format=group=>group.mean==null?'—':(group.mean*100).toFixed(1);
  const row=(label,group)=>`<div class="conservation-bar-row"><span>${label} (${group.count})</span><div class="conservation-bar"><span style="width:${(group.mean||0)*100}%"></span></div><strong>${format(group)}</strong></div>`;
  $('conservation-interface-content').innerHTML=row('Contact residues',comparison.interface)+row('Other residues',comparison.other_residues)+`<p class="conservation-interface-note">${comparison.difference==null?'Both groups need scored residues for a comparison.':`Mean-score difference: ${comparison.difference>=0?'+':''}${(comparison.difference*100).toFixed(1)} points.`} ${comparison.contact_residues} unique contact residues at ${comparison.cutoff.toFixed(1)} Å; ${comparison.supported_contact_residues} have sufficient alignment data. This is a descriptive comparison.</p>`;
}
function conservationContactPositions(profile) {
  const partner=$('conservation-partner')?.value||'';
  const positions=new Set();
  for(const contact of state.contacts?.rows||[]) {
    const a=contact.left,b=contact.right;
    const endpoint=a.chain===profile.chain&&(!partner||b.chain===partner)?a:b.chain===profile.chain&&(!partner||a.chain===partner)?b:null;
    if(endpoint){const residue=profile.residues.find(r=>r.resi===endpoint.resi);if(residue?.query_position)positions.add(residue.query_position);}
  }
  return positions;
}
function drawConservationChart(profile) {
  const canvas=$('conservation-chart');if(!canvas)return;
  const ctx=canvas.getContext('2d'),n=profile.positions.length,left=36,width=900,base=155,height=110;
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.fillStyle='#7b8c70';ctx.font='12px sans-serif';ctx.textAlign='right';ctx.fillText('100',27,49);ctx.fillText('0',27,158);
  const contactPositions=conservationContactPositions(profile);
  for(let i=0;i<n;i++) {
    const row=profile.positions[i],x=left+i/n*width,w=Math.max(1,width/n-.7);
    ctx.fillStyle=conservationColor(row.score);
    const h=row.score==null?height:Math.max(2,row.score*height);
    if(row.score==null)ctx.globalAlpha=.25;ctx.fillRect(x,base-h,w,h);ctx.globalAlpha=1;
    ctx.fillStyle='#89a078';ctx.fillRect(x,178-row.coverage*9,w,row.coverage*9);
    if(contactPositions.has(row.position)){ctx.fillStyle='#3e4c3e';ctx.beginPath();ctx.arc(x+w/2,162,1.7,0,Math.PI*2);ctx.fill();}
  }
  ctx.strokeStyle='#dee5d7';ctx.beginPath();ctx.moveTo(left,base);ctx.lineTo(left+width,base);ctx.stroke();
  ctx.textAlign='center';ctx.fillStyle='#7b8c70';
  const step=n>500?100:n>100?50:n>40?20:10;
  for(let i=1;i<=n;i++){if(i===1||i===n||i%step===0)ctx.fillText(String(i),left+(i-.5)/n*width,197);}
  const position=event=>{const rect=canvas.getBoundingClientRect();return Math.max(1,Math.min(n,Math.floor(((event.clientX-rect.left)/rect.width*960-left)/width*n)+1));};
  canvas.onmousemove=e=>inspectConservationPosition(position(e),false);
  canvas.onclick=e=>inspectConservationPosition(position(e),true);
}
function inspectConservationPosition(position,zoom) {
  const profile=state.conservation;
  if(!profile||!Number.isInteger(position)||position<1||position>profile.positions.length)return;
  const row=profile.positions[position-1],residue=profile.residues.find(r=>r.query_position===position);
  const score=row.score==null?'Insufficient alignment coverage':`Conservation ${(row.score*100).toFixed(1)} / 100`;
  $('conservation-readout').innerHTML=`<strong>${esc(profile.chain)} · Query ${row.aa}${position}${residue?' · Structure '+esc(residue.name)+' '+esc(residue.label):' · Not resolved in the structure'}</strong><br>${score} · Coverage ${Math.round(row.coverage*100)}% (${row.observed_sequences}/${profile.sequence_count} sequences)${row.rate!=null?`<br>Normalized evolutionary rate ${row.rate.toFixed(4)} · Posterior 25–75% interval [${row.rate_interval.map(v=>v.toFixed(3)).join(', ')}]`:''}${residue?.plddt!=null?' · pLDDT '+residue.plddt.toFixed(1):''}`;
  if(zoom&&residue){
    $('conservation-position').value=position;state.selectedContact=null;$('selection-note').classList.add('hidden');
    state.hidden.delete(profile.chain);state.color='conservation';$('color-mode').value='conservation';applyMainStyle();renderChains();
    const selection={chain:profile.chain,resi:residue.resi};
    state.viewer.addStyle(selection,{stick:{radius:.2,color:conservationColor(row.score)}});
    state.viewer.zoomTo(selection,300);state.viewer.addResLabels(selection,{fontSize:11,backgroundColor:'#344139',fontColor:'#eef4e1'});state.viewer.render();
  }
}
async function openConservation() {
  if(!state.detail||!$('conservation-chain').value)return;
  const chain=$('conservation-chain').value;
  const sources=await api(`/api/structures/${state.selected}/conservation-sources?chain=${encodeURIComponent(chain)}`);
  state.conservationSources=sources;
  $('conservation-query').innerHTML=`<strong>${esc(state.detail.name)} · Chain ${esc(chain)}</strong><br>${sources.query.length} amino acids · ${esc(sources.sequence_source)}<code>${esc(sources.query)}</code>`;
  $('conservation-prepared').innerHTML=sources.prepared.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('');
  $('conservation-source').querySelector('[value="prepared"]').disabled=!sources.prepared.length;
  $('conservation-source').value=sources.prepared.length?'prepared':'search';
  $('conservation-method').querySelector('[value="rate4site"]').disabled=!state.rate4site;
  $('conservation-method').value=state.rate4site?'rate4site':'entropy';
  $('conservation-message').innerHTML='';$('conservation-alignment').value='';state.conservationFilename='pasted alignment';
  conservationFormChanged();$('conservation-dialog').showModal();
}
function conservationFormChanged() {
  const source=$('conservation-source').value;
  for(const type of ['search','prepared','upload'])$('conservation-'+type+'-fields').classList.toggle('hidden',type!==source);
  $('conservation-method-note').textContent=$('conservation-method').value==='rate4site'?'Rate4Site estimates per-position evolutionary rates using an inferred tree and an empirical-Bayes JTT model. Lower rates mean stronger conservation. The 3D view uses relative percentiles within this protein; posterior rate intervals remain available.':'This fast view uses Henikoff sequence weights and Shannon entropy. It summarizes amino-acid diversity without fitting an evolutionary tree. Both methods mask positions with fewer than three observations or less than 50% coverage.';
}
async function submitConservation() {
  $('conservation-submit').disabled=true;
  try {
    const source=$('conservation-source').value;
    const payload={structure_id:state.selected,chain:$('conservation-chain').value,source,
      method:$('conservation-method').value,max_sequences:Number($('conservation-max-sequences').value),
      min_coverage:Number($('conservation-min-coverage').value)/100,
      min_identity:Number($('conservation-min-identity').value)/100,
      redundancy:Number($('conservation-redundancy').value)/100};
    if(source==='search')payload.database=$('conservation-database').value;
    if(source==='prepared')payload.prepared_source=$('conservation-prepared').value;
    if(source==='upload')Object.assign(payload,{alignment:$('conservation-alignment').value,format:$('conservation-format').value,filename:state.conservationFilename});
    const job=await api('/api/conservation',payload);
    state.jobs.unshift(job);state.job=job.id;$('conservation-dialog').close();setPage('experiments');await selectJob(job.id);toast('Conservation analysis added to your local queue.');
  }catch(error){message('conservation-message',error.message);}
  finally{$('conservation-submit').disabled=false;}
}
function setupConservation() {
  on('conservation-open','click',openConservation);
  on('conservation-chain','change',async()=>{state.conservationSources=null;conservationRunOptions();await loadConservation();});
  on('conservation-run','change',()=>loadConservation());
  on('conservation-color','click',()=>{state.color='conservation';$('color-mode').value='conservation';applyMainStyle();state.viewer.zoomTo();state.viewer.render();});
  on('conservation-source','change',conservationFormChanged);on('conservation-method','change',conservationFormChanged);
  on('conservation-submit','click',submitConservation);
  on('conservation-upload','change',async event=>{
    const file=event.target.files[0];if(!file)return;
    let text=await file.text(),format='auto';
    if(file.name.endsWith('.json')){
      const raw=JSON.parse(text),query=state.conservationSources.query;
      const protein=(raw.sequences||[]).map(s=>s.protein).find(p=>p?.sequence===query);
      text=protein?.unpairedMsa||protein?.pairedMsa;
      if(!text)throw new Error('This AF3 input has no inline alignment matching the selected protein sequence.');format='a3m';
    }else if(/\.a3m$/i.test(file.name))format='a3m';else if(/\.(sto|stockholm)$/i.test(file.name))format='stockholm';else if(/\.(fa|fasta|faa)$/i.test(file.name))format='fasta';
    $('conservation-alignment').value=text;$('conservation-format').value=format;state.conservationFilename=file.name;
    $('conservation-filename').textContent=file.name+' · The query row must match this chain exactly.';event.target.value='';
  });
}

function renderConservationJob(job,log) {
  const active=['running','queued','cancelling'].includes(job.status);
  $('job-detail').innerHTML=`<div class="job-title-row"><div><div class="eyebrow muted">CONSERVATION / ${job.id}</div><h2 style="font-size:22px;margin-top:8px">${esc(job.name)}</h2></div><span class="status-tag ${esc(job.status)}">${esc(job.status)}</span></div><div class="job-meta"><span>Chain ${esc(job.chain)}</span><span>${job.method==='rate4site'?'Rate4Site · empirical Bayes':'Weighted entropy'}</span><span>CPU</span><span>${esc(job.source_label)}</span></div><div class="job-stage">${active?'<span class="spinner"></span>':'<span>◇</span>'}<span>${esc(phaseFromLog(log,job))}</span></div><div class="job-actions"><a class="secondary" href="/api/jobs/${job.id}/input">↓ Analysis config</a>${job.status==='completed'?`<button id="view-conservation-result" class="primary">Explore conservation →</button><a class="secondary" href="/api/jobs/${job.id}/scores">↓ Scores CSV</a><a class="secondary" href="/api/jobs/${job.id}/alignment">↓ Alignment</a>`:''}${active?'<button id="cancel-job" class="secondary">Cancel job</button>':'<button id="rerun-conservation" class="secondary">Use settings again</button><button id="delete-job" class="secondary danger">Delete</button>'}</div>${job.error?`<div class="job-error">${esc(job.error)}</div>`:''}<div class="log-heading"><span>LIVE PROCESS LOG</span><span>${active?'UPDATING EVERY 3 SECONDS':'SAVED LOCALLY'}</span></div><pre class="job-log" id="job-log">${esc(log||'Waiting for the worker to start…')}</pre><p class="small muted" style="margin-top:12px">Output folder<br><code>${esc(job.output_dir)}</code></p>`;
  if($('cancel-job'))on('cancel-job','click',async()=>{await api(`/api/jobs/${job.id}/cancel`,{});await refresh();await selectJob(job.id);});
  if($('delete-job'))on('delete-job','click',()=>deleteJob(job));
  if($('view-conservation-result'))on('view-conservation-result','click',async()=>{setPage('explore');await loadStructure(job.structure_id);$('conservation-chain').value=job.chain;conservationRunOptions();await loadConservation(job.id);state.color='conservation';$('color-mode').value='conservation';applyMainStyle();});
  if($('rerun-conservation'))on('rerun-conservation','click',async()=>{
    const config=await api(`/api/jobs/${job.id}/input`);
    setPage('explore');await loadStructure(job.structure_id);$('conservation-chain').value=job.chain;await openConservation();
    $('conservation-method').value=config.method;
    $('conservation-max-sequences').value=config.max_sequences;
    $('conservation-min-coverage').value=config.min_coverage*100;$('conservation-min-identity').value=config.min_identity*100;$('conservation-redundancy').value=config.redundancy*100;
    if(config.source==='search'){$('conservation-source').value='search';$('conservation-database').value=config.database_name;}
    else{$('conservation-source').value='upload';$('conservation-alignment').value=config.alignment;$('conservation-format').value=config.format;state.conservationFilename='reused alignment';}
    conservationFormChanged();
  });
  $('job-log').scrollTop=$('job-log').scrollHeight;
}
