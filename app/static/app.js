const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = {user: null, documents: [], busy: false, view: 'advisory'};
const names = {advisory: ['Advisory desk', 'Your advisory desk.', 'Ask a question. Get the evidence. Make your next move.'], library: ['Document library', 'Your knowledge, connected.', 'Every source in one place, with the right permissions.'], automation: ['Automation', 'Less admin. More insight.', 'An upload starts the workflow. The database keeps the record.'], reliability: ['Demo guide', 'Put the evidence to the test.', 'Six practical scenarios for a focused walkthrough.'], audit: ['Audit trail', 'A trace of every action.', 'See access checks, processing events and advisor activity.']};
const advisorNames = {finance:'Finance advisor', hr:'HR / Management advisor', knowledge:'Knowledge assistant', mixed:'Request router'};
const modeNames = {code:'Calculated in Python', ai:'AI-selected evidence', evidence:'Evidence mode', fallback:'Local fallback'};

function el(tag, cls, text) { const node = document.createElement(tag); if (cls) node.className = cls; if (text !== undefined) node.textContent = text; return node; }
function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(state.toastTimer); state.toastTimer = setTimeout(() => $('#toast').hidden = true, 5500); }
async function api(path, options = {}) {
  const headers = {...options.headers};
  if (state.user?.csrf) headers['X-CSRF-Token'] = state.user.csrf;
  if (options.json !== undefined) { headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(options.json); delete options.json; }
  let response;
  try { response = await fetch(path, {...options, headers, credentials:'same-origin', signal: AbortSignal.timeout(26000)}); }
  catch { throw new Error('The server could not be reached in time. Check the connection and try again.'); }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && state.user) { await showLogin(); }
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Please check the input and try again.');
  }
  return body;
}

async function showLogin() {
  state.user = null; state.documents = []; state.busy = false;
  $('#question').value = '';
  $('#login-screen').hidden = false; $('#workspace').hidden = true;
  $$('.message').forEach(node => node.remove()); $('#welcome').hidden = false;
  for (const selector of ['#documents-list','#jobs-list','#audit-list','#document-content','#document-title','#document-meta']) $(selector).replaceChildren();
  $('#evidence-list').replaceChildren(el('div', 'evidence-empty', 'Source references appear after a question.'));
  $$('dialog[open]').forEach(dialog => dialog.close());
  const config = await api('/api/config').catch(() => ({demo:false}));
  $('#demo-logins').hidden = !config.demo;
}

async function startWorkspace() {
  state.user = await api('/api/me');
  $('#login-screen').hidden = true; $('#workspace').hidden = false;
  $('#password').value = '';
  const admin = state.user.role === 'admin';
  $$('.admin-only').forEach(node => node.hidden = !admin);
  $$('.standard-only').forEach(node => node.hidden = admin);
  $('#profile-name').textContent = state.user.name;
  $('#profile-role').textContent = admin ? 'Administrator' : 'Standard User';
  $('#avatar').textContent = state.user.name.split(' ').map(x => x[0]).join('');
  $('#stat-access').textContent = admin ? 'Administrator' : 'Standard User';
  $('#stat-access-detail').textContent = admin ? 'Shared + confidential documents' : 'Shared documents only';
  $('#mode-badge').textContent = state.user.ai_enabled ? 'AI evidence · connected' : 'Local evidence mode';
  $('#mode-note').textContent = state.user.ai_enabled ? 'AI selects source quotes. Every quote is checked against the original passage.' : 'No API key configured. Showing exact excerpts with local retrieval. Finance always uses code.';
  $('#today').textContent = new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',year:'numeric'}).format(new Date());
  await refreshDocuments(); setView('advisory');
}

async function refreshDocuments() {
  state.documents = await api('/api/documents');
  $('#stat-docs').textContent = String(state.documents.length).padStart(2,'0');
  $('#nav-count').textContent = state.documents.length;
  $('#stat-jobs').textContent = String(state.documents.filter(d => d.status === 'completed').length).padStart(2,'0');
  renderDocuments(); renderJobs();
}

function setView(view) {
  if (view === 'audit' && state.user?.role !== 'admin') return;
  state.view = view;
  $$('.view').forEach(node => node.hidden = node.id !== `view-${view}`);
  $$('.nav-item').forEach(node => node.classList.toggle('active', node.dataset.view === view));
  $('#view-name').textContent = names[view][0]; $('#page-title').textContent = names[view][1]; $('#page-subtitle').textContent = names[view][2];
  if (view === 'audit') refreshAudit().catch(e => toast(e.message));
  if (view === 'library' || view === 'automation') refreshDocuments().catch(e => toast(e.message));
}

function renderDocuments() {
  const container = $('#documents-list'); container.replaceChildren();
  if (!state.documents.length) { container.append(el('p','muted','No accessible documents yet. Ask an administrator to upload a source.')); return; }
  for (const doc of state.documents) {
    const row = el('button','document-row'); row.type = 'button'; row.setAttribute('aria-label',`Open ${doc.name}`);
    // Buttons use a reset so the entire row remains keyboard accessible.
    row.append(el('span','doc-icon',doc.name.split('.').pop().toUpperCase()));
    const info = el('div'); info.append(el('strong','',doc.name), el('small','',`${doc.category === 'hr' ? 'HR / Management' : doc.category === 'finance' ? 'Finance' : 'General knowledge'} · ${doc.chunks} passages`));
    row.append(info, el('span',`tag ${doc.access}`,doc.access === 'public' ? 'SHARED' : 'CONFIDENTIAL'), el('span',`tag ${doc.status}`,doc.status.toUpperCase()),el('span','','↗'));
    row.addEventListener('click', () => openDocument(doc.id)); container.append(row);
  }
}

function renderJobs() {
  const container = $('#jobs-list'); container.replaceChildren();
  for (const doc of state.documents) {
    const card = el('article','job-card'); const top = el('div','job-top');
    top.append(el('strong','',doc.name),el('span',`tag ${doc.status}`,doc.status.toUpperCase()));
    card.append(top,el('p','',doc.summary || doc.error || 'Waiting for processing…'),el('small','',`Extractive summary · SQLite record · ${doc.attempts} processing attempt${doc.attempts === 1 ? '' : 's'}`));
    if (doc.status === 'failed' && state.user.role === 'admin') {
      const retry = el('button','button secondary','Retry processing ↻');
      retry.addEventListener('click', async () => { retry.disabled = true; try { await api(`/api/documents/${doc.id}/retry`, {method:'POST'}); await refreshDocuments(); } catch(e) { toast(e.message); } finally {retry.disabled=false;} }); card.append(retry);
    }
    container.append(card);
  }
}

async function openDocument(id, chunkId) {
  try {
    const doc = await api(`/api/documents/${encodeURIComponent(id)}`);
    $('#document-title').textContent = doc.name;
    $('#document-meta').replaceChildren(el('span',`tag ${doc.access}`,doc.access.toUpperCase()),el('span','tag',doc.category.toUpperCase()));
    const chunk = doc.chunks.find(c => c.id === chunkId);
    $('#document-content').textContent = chunk ? `${chunk.location}\n\n${chunk.text}\n\n──────── FULL DOCUMENT ────────\n\n${doc.text}` : doc.text;
    $('#document-content').scrollTop = 0; $('#document-dialog').showModal();
  } catch(e) { toast(e.message); }
}

async function ask(question) {
  if (state.busy || !question.trim()) return;
  state.busy = true; $('#send').disabled = true; $('#conversation').setAttribute('aria-busy','true');
  const requester = state.user.csrf;
  $('#welcome').hidden = true; setView('advisory');
  const conversation = $('#conversation'); conversation.append(el('div','message user',question));
  const thinking = el('div','message thinking','Finding permitted sources and checking the evidence…'); conversation.append(thinking); conversation.scrollTop = conversation.scrollHeight;
  $('#question').value = '';
  try {
    const result = await api('/api/ask',{method:'POST',json:{question}});
    thinking.remove();
    if (!state.user || state.user.csrf !== requester) return;
    const message = el('article','message assistant'); const heading = el('div','answer-heading');
    heading.append(el('span','answer-mark','✳'),el('strong','',advisorNames[result.advisor]),el('span','',modeNames[result.mode]));
    message.append(heading,el('div','answer-body',result.answer));
    for (const calc of result.calculations) {
      const block = el('div','calculation'); const top = el('div','calc-result'); top.append(el('span','',calc.label),el('strong','',calc.value));
      block.append(top,el('div','calc-formula',calc.formula));
      for (const [key,value] of Object.entries(calc.inputs)) { const line = el('div','calc-input'); line.append(el('span','',key),el('span','',value)); block.append(line); }
      block.append(el('div','calc-formula',calc.rounding)); message.append(block);
    }
    for (const warning of result.warnings) message.append(el('div','answer-warning',warning));
    if (result.status === 'conflict') message.append(el('div','answer-warning','Conflicting evidence is preserved. An authorized owner must confirm which document governs.'));
    const pills = el('div','answer-source-list');
    for (const source of result.citations) { const button = el('button','source-pill',`[${source.ref}] ${source.name} ↗`); button.addEventListener('click', () => openDocument(source.document_id,source.chunk_id)); pills.append(button); }
    message.append(pills); conversation.append(message); renderEvidence(result.citations);
  } catch(e) { thinking.remove(); conversation.append(el('div','message answer-warning',e.message)); }
  finally { state.busy = false; $('#send').disabled = false; $('#conversation').setAttribute('aria-busy','false'); conversation.scrollTop = conversation.scrollHeight; }
}

function renderEvidence(sources) {
  const container = $('#evidence-list'); container.replaceChildren();
  if (!sources.length) { container.append(el('div','evidence-empty','No verified source references for this answer.')); return; }
  for (const source of sources) {
    const card = el('article','evidence-card'); const button = el('button');
    button.append(el('strong','',`[${source.ref}] ${source.name} ↗`),el('small','',source.location));
    button.addEventListener('click',() => openDocument(source.document_id,source.chunk_id));
    card.append(button,el('p','',source.quote)); container.append(card);
  }
}

async function refreshAudit() {
  const events = await api('/api/audit'); const container = $('#audit-list'); container.replaceChildren();
  for (const event of events) {
    const row = el('div','audit-row');
    row.append(el('span','',event.actor),el('strong','',event.event.replaceAll('_',' ')),el('small','',event.detail),el('small','',new Date(event.created_at*1000).toLocaleTimeString('en-GB'))); container.append(row);
  }
}

const scenarios = [
  ['01 / FINANCIAL ACCURACY','Recompute, then compare.','Q3 reports a 45% margin. The code calculates 40% and flags the discrepancy.','What is the gross margin for 2026-Q3?'],
  ['02 / POLICY CONFLICT','Keep both sides visible.','Two sources disagree about remote work: 2 and 3 days per week. No policy is silently chosen.','What is the remote work policy?'],
  ['03 / MISSING EVIDENCE','Know when to stop.','The sample library has no parental leave policy. The assistant should say evidence is insufficient.','What is our parental leave policy?'],
  ['04 / ACCESS CONTROL','Test both accounts.','Ask this as Administrator, then Standard User. The Standard User cannot retrieve the confidential executive salary.','What is the executive salary?'],
  ['05 / CODE CALCULATIONS','Show the working.','Q2 revenue is AED 1m and Q3 revenue is AED 1.2m. Growth should be exactly 20%.','Compare revenue growth from 2026-Q2 to 2026-Q3.'],
  ['06 / KNOWLEDGE ASSISTANT','Follow the source.','Retrieve a general business fact, then open its reference to inspect the source text.','What services does Northstar Studio provide?']
];
for (const [label,title,description,question] of scenarios) { const card = el('button','guide-card'); card.append(el('span','eyebrow accent',label),el('strong','',title),el('p','',description),el('span','','Try this scenario ↗')); card.addEventListener('click',() => ask(question)); $('#guide-cards').append(card); }

$('#login-form').addEventListener('submit',async event => {
  event.preventDefault(); const button = $('.login-submit'); button.disabled = true; $('#login-error').textContent = '';
  try { state.user = await api('/api/login',{method:'POST',json:{username:$('#username').value,password:$('#password').value}}); await startWorkspace(); }
  catch(e) { $('#login-error').textContent = e.message; } finally {button.disabled = false;}
});
$('#demo-admin').addEventListener('click',() => { $('#username').value='admin'; $('#password').value='AdminDemo!2026'; $('#username').focus(); });
$('#demo-standard').addEventListener('click',() => { $('#username').value='user'; $('#password').value='UserDemo!2026'; $('#username').focus(); });
for (const button of [$('#logout'),$('#logout-mobile')]) button.addEventListener('click',async () => { try { await api('/api/logout',{method:'POST'}); await showLogin(); } catch(e) {toast(e.message);} });
$$('.nav-item').forEach(button => button.addEventListener('click',()=>setView(button.dataset.view)));
$$('[data-question]').forEach(button => button.addEventListener('click',()=>ask(button.dataset.question)));
$('#ask-form').addEventListener('submit', event => {event.preventDefault(); ask($('#question').value.trim());});
$('#question').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault(); ask($('#question').value.trim());}});
$('#upload-shortcut').addEventListener('click',()=>{$('#upload-error').textContent='';$('#upload-dialog').showModal();});
$$('.close-dialog').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
$('#refresh-audit').addEventListener('click',()=>refreshAudit().catch(e=>toast(e.message)));
$('#upload-form').addEventListener('submit',async event=>{
  event.preventDefault(); const file = $('#file').files[0]; if(!file)return;
  if(file.size>5*1024*1024){$('#upload-error').textContent='Maximum upload size is 5 MB.';return;}
  $('#upload-submit').disabled=true;$('#upload-error').textContent='';
  try {
    const query=new URLSearchParams({name:file.name,category:$('#category').value,access:$('#access').value});
    const result=await api(`/api/documents?${query}`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
    $('#upload-dialog').close(); $('#upload-form').reset(); toast(result.message); await refreshDocuments();setView('automation');
    // Only poll while a job is actually running; keep every read permission filtered.
    for(let attempt=0;attempt<8&&state.documents.some(d=>d.status==='pending'||d.status==='processing');attempt++){await new Promise(resolve=>setTimeout(resolve,750));if(!state.user)break;await refreshDocuments();}
  }catch(e){$('#upload-error').textContent=e.message;}finally{$('#upload-submit').disabled=false;}
});
(async()=>{try{await startWorkspace();}catch{await showLogin();}})();
