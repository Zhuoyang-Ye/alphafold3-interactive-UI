'use strict';
// Read-only mode for the static GitHub Pages copy of the explorer. build_demo.py
// loads this before app.js; it answers the app's API requests from saved files.
(() => {
  const realFetch = window.fetch.bind(window);
  const READ_ONLY = 'This online demo is read-only. Install the explorer on your Mac to run predictions, imports, and new analyses.';
  let manifest = null;
  const ready = realFetch('demo/manifest.json').then(r => r.json()).then(m => (manifest = m));

  // Must match canonical() in build_demo.py.
  function canonical(url) {
    const [path, query = ''] = url.split('?');
    const params = [...new URLSearchParams(query)].filter(([, v]) => v !== '')
      .sort(([a, x], [b, y]) => a < b ? -1 : a > b ? 1 : x < y ? -1 : x > y ? 1 : 0);
    return params.length ? path + '?' + params.map(([k, v]) => k + '=' + v).join('&') : path;
  }
  function reply(body, status, type = 'application/json') {
    return new Response(body, {status, headers: {'Content-Type': type}});
  }
  async function serve(key) {
    const entry = (await ready).entries[key];
    if (!entry) return reply(JSON.stringify({error: 'This view is not included in the online demo.'}), 404);
    const response = await realFetch('demo/' + entry.file);
    if (!entry.refs) return reply(await response.blob(), entry.status, entry.type);
    const body = await response.json();
    await Promise.all(Object.entries(body).map(async ([key, value]) => {
      if (value?.$ref) body[key] = await (await realFetch('demo/' + value.$ref)).json();
    }));
    return reply(JSON.stringify(body), entry.status);
  }

  window.fetch = async (input, options = {}) => {
    const url = typeof input === 'string' ? input : input.url;
    if (!url.startsWith('/api/')) return realFetch(input, options);
    if ((options.method || 'GET').toUpperCase() !== 'GET') {
      if (url !== '/api/align') return reply(JSON.stringify({error: READ_ONLY}), 403);
      const body = JSON.parse(options.body);
      return serve(['align', body.left, body.right, body.left_chain, body.right_chain].join('|'));
    }
    return serve(canonical(url));
  };

  // Download links point at /api/...; send them to the saved copies instead.
  document.addEventListener('click', event => {
    const link = event.target.closest?.('a[href^="/api/"]');
    if (!link) return;
    const entry = manifest?.entries[canonical(link.getAttribute('href'))];
    if (!entry || entry.status !== 200) {
      event.preventDefault();
      if (typeof toast === 'function') toast('This file is not included in the online demo.');
      return;
    }
    link.href = 'demo/' + entry.file;
    if (entry.name) link.download = entry.name;
  }, true);

  const style = document.createElement('style');
  style.textContent = '#new-experiment,#empty-new,#import-open,#mobile-import,#conservation-open,#system-open,' +
    '#cancel-job,#rerun-job,#rerun-conservation,#predict-prepared,#delete-job{display:none!important}' +
    '.demo-notice{margin:-8px 0 26px}.demo-notice a{color:var(--green);font-weight:600}' +
    '.demo-notice small{display:block;margin-top:6px;color:var(--muted);font-size:11px}';
  document.head.append(style);

  document.addEventListener('DOMContentLoaded', async () => {
    const {repo} = await ready;
    document.querySelector('.workspace-label').innerHTML = '<span class="dot"></span> ONLINE DEMO <span class="version">AF3</span>';
    document.querySelector('.sidebar-footer').textContent = 'Read-only demo, saved from a local run.';
    document.querySelector('.page-header .eyebrow').textContent = 'ALPHAFOLD 3 / ONLINE DEMO';
    document.querySelector('.experiment-intro p').textContent = 'Saved jobs from a local run, with their inputs and logs as recorded.';
    const banner = document.createElement('div');
    banner.className = 'notice demo-notice';
    banner.innerHTML = `<strong>Read-only online demo.</strong> Explore structures, contacts, confidence, and conservation saved from a local run of this explorer. To run your own predictions, <a href="${repo}/blob/main/GETTING_STARTED_MACOS.md">install it on your Mac</a> · <a href="${repo}">Source on GitHub</a>` +
      '<small>Predicted structures are AlphaFold 3 output, provided under and subject to the <a href="https://github.com/google-deepmind/alphafold3/blob/main/OUTPUT_TERMS_OF_USE.md">AlphaFold 3 Output Terms of Use</a>. ' +
      'The 3D view shows modified coordinates (first model; waters and hydrogens removed); ↓ mmCIF downloads the unmodified file. ' +
      'Cite: Abramson, J. et al. Accurate structure prediction of biomolecular interactions with AlphaFold 3. <i>Nature</i> 630, 493–500 (2024). ' +
      'Experimental structures are from the <a href="https://www.wwpdb.org/">Protein Data Bank</a>.</small>';
    document.querySelector('.page-header').after(banner);
  });
})();
