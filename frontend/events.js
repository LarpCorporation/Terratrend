/* Curated Earth-events catalogue.
   The narrative — which places, which pathway, which mechanism, which
   references — is editorial and ships with the backend. Every number is
   fetched and computed from NASA observations by /api/events/<id>, and every
   photograph is a reviewed Wikimedia Commons file cached by the server.
   Nothing is filled in: a pathway with no source says so.

   Opening this screen deliberately loads nothing. An event is shown only once
   a reader picks one, and only one at a time. */
(function () {
  'use strict';

  const STATUS = {
    verified_from_source: { text: 'Computed', cls: 'ev-ok' },
    not_checked: { text: 'Not checked', cls: 'ev-thin' },
    awaiting_source: { text: 'Awaiting source', cls: 'ev-await' },
    unavailable: { text: 'Unavailable', cls: 'ev-off' },
    insufficient_data: { text: 'Insufficient data', cls: 'ev-thin' },
    declared: { text: 'Declared', cls: 'ev-thin' }
  };

  const state = {
    index: null,
    activeId: null,
    payloads: new Map(),
    abort: null
  };

  const EMPTY_DETAIL = 'Choose an event to explore its documented pathways. Observation checks start only after a separate data-use review.';

  function byId(id) { return document.getElementById(id); }

  function node(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  function renderer() {
    try { return typeof investigation !== 'undefined' ? investigation.map : null; }
    catch (err) { return null; }
  }

  function num(value, digits) {
    return (typeof value === 'number' && isFinite(value)) ? value.toFixed(digits) : '—';
  }

  function pText(p) {
    if (typeof p !== 'number' || !isFinite(p)) return '—';
    return p < 0.001 ? p.toExponential(1) : p.toFixed(3);
  }

  function statusOf(status) {
    return STATUS[status] || { text: status || 'Unknown', cls: 'ev-thin' };
  }

  function sentence(text) {
    if (!text) return '';
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  /* ------------------------------------------------------------ rail ---- */

  async function loadIndex() {
    if (state.index) return state.index;
    const res = await fetch('/api/events', { cache: 'no-store' });
    if (!res.ok) throw new Error('The event catalogue could not be loaded. Restart the TerraTrend server.');
    state.index = await res.json();
    return state.index;
  }

  function renderRail() {
    const list = byId('events-list');
    list.textContent = '';
    byId('events-lede').textContent =
      'Choose a documented story. Gold lines show catalogue pathways; blue lines show associations that passed this investigation’s statistical checks. Neither establishes a cause.';
    byId('events-disclaimer').textContent = state.index.disclaimer || '';

    const label = node('label', 'ev-select-label', 'Choose an event');
    label.setAttribute('for', 'event-select');
    const select = document.createElement('select');
    select.id = 'event-select';
    select.className = 'ev-select';

    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = '— select an event —';
    select.append(placeholder);

    // Grouped by category so a long catalogue stays navigable.
    const groups = new Map();
    for (const event of state.index.events) {
      const key = event.category || 'Other events';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(event);
    }
    for (const [name, events] of groups) {
      const group = document.createElement('optgroup');
      group.label = name;
      for (const event of events) {
        const option = document.createElement('option');
        option.value = event.id;
        option.textContent = event.title + (event.status === 'ongoing_developing' ? '  ·  watch' : '');
        group.append(option);
      }
      select.append(group);
    }
    select.addEventListener('change', () => {
      const id = select.value;
      if (!id) { clearEvent(); return; }
      openEvent(id);
    });

    list.append(label, select);
    const tour=node('button','toolbar-button','Walk through an event');tour.type='button';tour.id='events-walkthrough';tour.onclick=()=>{clearEvent();window.TerraTour?.start({chapter:'advanced',plan:['event-story','event-pathway','event-evidence','event-explanation']});};list.append(tour);
    list.append(buildLegend());
  }

  function buildLegend() {
    const legend = node('details', 'ev-legend');
    legend.append(node('summary', null, 'What the badges mean'));
    const rows = state.index.status_legend || {};
    const ul = node('ul', 'ev-legend-list');
    for (const key of ['not_checked','verified_from_source', 'unavailable', 'awaiting_source', 'insufficient_data']) {
      if (!rows[key]) continue;
      const li = node('li');
      const badge = statusOf(key);
      li.append(node('span', 'ev-badge ' + badge.cls, badge.text));
      li.append(node('span', null, rows[key]));
      ul.append(li);
    }
    legend.append(ul);
    return legend;
  }

  /* ---------------------------------------------------------- detail ---- */

  function gallery(images) {
    if (!images || !images.length) return null;
    const wrap = node('section', 'ev-gallery');
    wrap.append(node('h3', 'ev-section', 'Photographs'));
    const grid = node('div', 'ev-gallery-grid');
    for (const image of images) {
      const figure = node('figure', 'ev-figure');
      const img = document.createElement('img');
      img.src = image.src;
      img.alt = image.caption || image.title || 'Event photograph';
      img.loading = 'lazy';
      img.addEventListener('error', () => {img.remove();figure.append(node('p','ev-mini','Photograph unavailable. Its source and credits are listed below.'));});
      figure.append(img);
      if (image.caption) figure.append(node('figcaption', null, image.caption));
      const credit = [image.artist, image.licence].filter(Boolean).join(' · ');
      if (credit) {
        const small = node('small', 'ev-credit', credit);
        if (image.page) {
          const link = document.createElement('a');
          link.href = image.page;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          link.textContent = 'source';
          small.append(' · ', link);
        }
        figure.append(small);
      }
      grid.append(figure);
    }
    wrap.append(grid);
    return wrap;
  }

  function sparkline(series) {
    if (!series || series.length < 12) return null;
    const w = 300, h = 56, pad = 3;
    const values = series.reduce((acc, p) => acc.concat([p.x, p.y]), []);
    const min = Math.min.apply(null, values);
    const max = Math.max.apply(null, values);
    if (!isFinite(min) || !isFinite(max)) return null;
    const span = (max - min) || 1;
    const px = i => pad + (w - 2 * pad) * (i / (series.length - 1));
    const py = v => pad + (h - 2 * pad) * (1 - (v - min) / span);
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    svg.setAttribute('class', 'ev-spark');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'Detrended anomaly of both sides of this pathway');
    for (const spec of [['x', 'ev-spark-x'], ['y', 'ev-spark-y']]) {
      const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
      poly.setAttribute('points', series.map((p, i) =>
        px(i).toFixed(1) + ',' + py(p[spec[0]]).toFixed(1)).join(' '));
      poly.setAttribute('class', spec[1]);
      svg.append(poly);
    }
    return svg;
  }

  function evidenceBlock(edge) {
    const wrap = node('div', 'ev-evidence');
    const datasets = (edge.evidence && edge.evidence.datasets) || [];
    const references = (edge.evidence && edge.evidence.references) || [];
    if (datasets.length) {
      wrap.append(node('p', 'ev-mini', 'Declared datasets'));
      const ul = node('ul', 'ev-list');
      for (const d of datasets) {
        ul.append(node('li', null, d.name + ' — ' + (d.type || '') + (d.years ? ' · ' + d.years : '')));
      }
      wrap.append(ul);
    }
    if (references.length) {
      wrap.append(node('p', 'ev-mini', 'Literature'));
      const ul = node('ul', 'ev-list');
      for (const ref of references) ul.append(node('li', null, ref));
      wrap.append(ul);
    }
    return wrap;
  }

  function mechanismBlock(edge) {
    const wrap = node('div', 'ev-mech');
    if (edge.why_it_exists) wrap.append(node('p', 'ev-why', edge.why_it_exists));
    const steps = edge.mechanism || [];
    if (steps.length) {
      const ol = node('ol', 'ev-steps');
      for (const step of steps) {
        const li = node('li', 'ev-step');
        li.append(node('span', 'ev-step-layer ev-layer-' + step.layer, step.layer));
        li.append(node('span', null, step.process));
        ol.append(li);
      }
      wrap.append(ol);
    }
    wrap.append(evidenceBlock(edge));
    return wrap;
  }

  function edgeBlock(edge) {
    const v = edge.verification || {};
    const status = statusOf(v.status);
    const card = node('article', 'ev-edge');
    card.dataset.edgeId=edge.id;card.tabIndex=-1;

    const head = node('div', 'ev-edge-head');
    head.append(node('strong', 'ev-edge-title', edge.label));
    head.append(node('span', 'ev-badge ' + status.cls, status.text));
    card.append(head);

    if (v.status === 'verified_from_source') {
      const numbers = node('p', 'ev-numbers');
      numbers.append(node('b', null, 'Relationship strength: ' + num(v.r_value, 2)+' (unitless)'));
      numbers.append(node('span', null, v.lag_months_observed > 0
        ? 'leads by ' + v.lag_months_observed + ' months'
        : v.lag_months_observed < 0
          ? 'follows by ' + Math.abs(v.lag_months_observed) + ' months'
          : 'simultaneous'));
      numbers.append(node('span', null, 'Adjusted test value p = ' + pText(v.p_value_neff)));
      numbers.append(node('span', null, v.sample_months + ' paired months'));
      card.append(numbers);

      const fdr = node('p', 'ev-fdr ' + (v.survives_fdr ? 'ev-ok' : 'ev-thin'));
      fdr.textContent = 'Benjamini–Hochberg across ' + v.family_size + ' pathways: p = '
        + pText(v.p_value_fdr) + (v.survives_fdr ? ' · survives false-discovery control' : ' · does not survive');
      card.append(fdr);

      const spark = sparkline(v.chart_series);
      if (spark) card.append(spark);

      const x = v.x || {}, y = v.y || {};
      card.append(node('p', 'ev-provenance',
        'Computed from ' + (x.source || '?') + ' against ' + (y.source || '?')));
      for(const x of [v.x||{},v.y||{}]) if(x.proxy_for||x.proxy_note){
        card.append(node('p', 'ev-proxy', sentence(x.variable + ' stands in for '
          + (x.proxy_for||'the declared study footprint') + '. ' + (x.proxy_note || ''))));
      }
    } else {
      card.append(node('p', 'ev-reason', v.reason || 'This pathway has no available source yet.'));
      const legend = (state.index.status_legend || {})[v.status];
      if (legend) card.append(node('p', 'ev-mini', legend));
      const x = v.x || {};
      if (x.proxy_for) card.append(node('p', 'ev-provenance', x.variable + ' stands in for ' + x.proxy_for));
    }

    const details = node('details', 'ev-details');
    const summary=node('summary', null, 'Documented mechanism and references');
    details.append(summary);
    details.append(mechanismBlock(edge));
    let learnerToggle=false;
    summary.addEventListener('click',event=>{if(event.isTrusted)learnerToggle=true;});
    details.addEventListener('toggle',()=>{if(details.open&&learnerToggle&&typeof announceAction==='function')announceAction('event-pathway-open',{edgeId:edge.id});learnerToggle=false;});
    card.append(details);
    return card;
  }

  function renderDetail(data) {
    const detail = byId('events-detail');
    detail.textContent = '';

    const head = node('header', 'ev-head');
    head.append(node('p', 'eyebrow', data.category || 'EARTH EVENT'));
    head.append(node('h2', 'ev-title', data.title));
    const meta = node('div', 'ev-head-meta');
    meta.append(node('span', 'ev-period', data.period || ''));
    if (data.status === 'ongoing_developing') {
      meta.append(node('span', 'ev-badge ev-watch', 'WATCH — not yet complete'));
    }
    head.append(meta);
    head.append(node('p', 'ev-summary', data.summary || ''));
    detail.append(head);

    const controls=node('section','event-run-controls');
    controls.append(node('p',null,data.computed?`Checked window: ${data.start}–${data.end}. These are historical associations across that window, not an attribution of the individual event.`:'This is a sourced story. No observation check has been run for this selection.'));
    const dates=node('div','event-date-row');
    const eventYear=Number((data.period||'').slice(0,4))||2023;
    const defaultEnd=Math.min(new Date().getFullYear(),eventYear<2000?eventYear+8:Math.max(eventYear+1,2024));
    for(const [id,label,value] of [['event-start','From',data.start||Math.max(1982,defaultEnd-8)],['event-end','To',data.end||defaultEnd]]){
      const l=node('label',null,label);l.htmlFor=id;const input=node('input');input.id=id;input.type='number';input.min=1981;input.max=new Date().getFullYear();input.value=value;l.append(input);dates.append(l);
    }
    controls.append(dates);
    const run=node('button','toolbar-button',data.computed?'Check another window':'Check with data');run.type='button';run.onclick=()=>checkEvent(data.id,run);controls.append(run);
    const explain=node('button','toolbar-button','Explain this event');explain.type='button';explain.id='event-explain';explain.onclick=()=>{window.TerraAssistant?.explain(data.saved_record_id||null,data.saved_record_id?null:{result:data,kind:'event'});if(typeof announceAction==='function')announceAction('event-explanation-opened',{eventId:data.id});};controls.append(explain);
    detail.append(controls);

    if(data.images?.length){
      const photos=node('details','event-photos');photos.append(node('summary',null,'Photographs and credits · load when opened'));
      photos.addEventListener('toggle',()=>{if(photos.open&&!photos.dataset.loaded){const pics=gallery(data.images);if(pics)photos.append(pics);photos.dataset.loaded='true';}});detail.append(photos);
    }

    if (data.status === 'ongoing_developing') {
      const watch = node('div', 'ev-watch-note');
      watch.append(node('strong', null, 'How to read this card'));
      watch.append(node('p', null,
        'This catalogue item is a watch, not a verified account of a completed event or a current forecast. Any data check below describes the selected historical observation window.'));
      detail.append(watch);
    }

    detail.append(node('h3', 'ev-section', data.computed?'What this data check found':'Pathways to investigate'));
    if (!data.edges.length) {
      detail.append(node('p', 'ev-placeholder', 'This event has no pathways declared.'));
    }
    for (const edge of data.edges) detail.append(edgeBlock(edge));

    if (data.limitations && data.limitations.length) {
      detail.append(node('h3', 'ev-section', 'What we still cannot say'));
      const ul = node('ul', 'ev-list ev-limits');
      for (const line of data.limitations) ul.append(node('li', null, line));
      detail.append(ul);
    }

    if (data.composite_analogs) {
      const analogs = data.composite_analogs;
      detail.append(node('h3', 'ev-section', 'Composite analogs'));
      detail.append(node('p', 'ev-mini', (analogs.events_compared || []).join(' · ')
        + ' (n = ' + analogs.sample_size_n + ')'));
      if (analogs.note) detail.append(node('p', 'ev-note', analogs.note));
    }

    if (data.declared && Object.keys(data.declared).length) {
      const declared = node('div', 'ev-declared');
      declared.append(node('p', 'ev-mini', 'Sources resolved for this event'));
      const ul = node('ul', 'ev-list');
      for (const key of Object.keys(data.declared)) {
        const slot = data.declared[key];
        ul.append(node('li', null, slot.slot + ' — ' + slot.source
          + (slot.proxy_for ? ' (stands in for ' + slot.proxy_for + ')' : '')));
      }
      declared.append(ul);
      detail.append(declared);
    }
  }

  /* ----------------------------------------------------------- globe ---- */

  function bboxArray(b) {
    if (!b) return null;
    if (Array.isArray(b)) {
      return (b.length === 4 && b.every(v => typeof v === 'number' && isFinite(v))) ? b : null;
    }
    const box = [b.lon_min, b.lat_min, b.lon_max, b.lat_max];
    return box.every(v => typeof v === 'number' && isFinite(v)) ? box : null;
  }

  function stageBounds() {
    const map = renderer();
    if (!map) return null;
    const host = map.host.getBoundingClientRect();
    const stage = byId('events-stage');
    if (!stage) return null;
    const rect = stage.getBoundingClientRect();
    if (rect.width < 40) return null;          // narrow layout: panels cover it
    return { left: rect.left - host.left, right: rect.right - host.left };
  }

  function eventConnections(data) {
    const nodes = new Map((data.nodes || []).map(n => [n.id, n]));
    return (data.edges||[]).map(edge=>{
      const a=nodes.get(edge.source_node),b=nodes.get(edge.target_node);if(!a||!b||a.id===b.id)return null;
      const v=edge.verification||{},tested=v.status==='verified_from_source'&&v.survives_fdr===true;
      const lag=tested&&Number.isFinite(v.lag_months_observed)?v.lag_months_observed:0;
      return {source_region:a,target_region:b,event_edge:edge.id,
        source_variable:{id:v.x?.variable||'event-source',name:v.x?.variable||'Documented pathway'},
        target_variable:{id:v.y?.variable||'event-target',name:edge.label,color:tested?'#68b8ff':'#e9c77a'},
        relationship:lag===0?'simultaneous':'response',lag_months:lag,
        direction:tested&&v.r_value<0?'inverse':'direct',r:tested?v.r_value:null,
        evidence_label:edge.label+' · '+(tested?'Computed association, correlation '+num(v.r_value,2)+' · '+(v.lead_note||'No resolved lead'):'Catalogue pathway · no surviving statistical link established here')+' · Click to inspect',
        lead_note:tested?v.lead_note:'Not a computed lead',label:edge.label};
    }).filter(Boolean);
  }
  function drawEvent(data) {
    const map = renderer();
    if (!map) return;

    // Which pathways begin or end at each named point, so hovering a dot can
    // say exactly what the line leaving it is.
    const routes = new Map();
    for (const edge of data.edges || []) {
      const add = (id, role) => {
        if (!id) return;
        if (!routes.has(id)) routes.set(id, []);
        routes.get(id).push({ role: role, label: edge.label });
      };
      add(edge.source_node, 'starts here');
      add(edge.target_node, 'ends here');
    }
    const marked = (data.nodes || []).map(n => Object.assign({}, n, {
      pathways: routes.get(n.id) || []
    }));
    map.setEventNodes(marked, stageBounds());

    map.setConnections(eventConnections(data));

    const boxes = (data.nodes || []).map(n => bboxArray(n.bbox)).filter(Boolean);
    if (boxes.length) {
      const bbox = boxes.reduce((acc, b) => [
        Math.min(acc[0], b[0]), Math.min(acc[1], b[1]),
        Math.max(acc[2], b[2]), Math.max(acc[3], b[3])
      ]);
      // Hold the view on the event: a slowly spinning globe would carry the
      // named points off the visible stage while someone is reading them.
      map.setAutoRotation(false);
      map.focusFeature({ bbox: bbox, name: data.title });
    }
  }

  function clearEvent() {
    state.activeId = null;
    const select = byId('event-select');
    if (select) select.value = '';
    const map = renderer();
    if (map) { map.setConnections([]); map.setEventNodes([]); }
    const detail = byId('events-detail');
    detail.textContent = '';
    detail.append(node('p', 'events-placeholder', EMPTY_DETAIL));
  }

  async function openEvent(id) {
    if (state.abort) state.abort.abort();
    const controller = new AbortController();
    state.abort = controller;
    state.activeId = id;

    const select = byId('event-select');
    if (select && select.value !== id) select.value = id;
    const detail = byId('events-detail');

    if (state.payloads.has(id)) {
      const cached = state.payloads.get(id);
      renderDetail(cached);
      drawEvent(cached);
      if(typeof announceAction==='function')announceAction('event-selected',{eventId:id});
      return;
    }

    detail.textContent = '';
    const loading = node('div', 'events-loading');
    loading.append(node('p', null, 'Opening the documented event story…'));
    loading.append(node('p', 'ev-mini',
      'Observation checks are separate; selecting a story requests no science data.'));
    detail.append(loading);

    try {
      const res = await fetch('/api/events/' + encodeURIComponent(id),
        { cache: 'no-store', signal: controller.signal });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Could not load this event.');
      if (controller.signal.aborted || state.activeId !== id) return;
      state.payloads.set(id, data);
      renderDetail(data);
      drawEvent(data);
      if(typeof announceAction==='function')announceAction('event-selected',{eventId:id});
    } catch (err) {
      if (err.name === 'AbortError' || state.activeId !== id) return;
      detail.textContent = '';
      detail.append(node('p', 'events-error', err.message));
    }
  }

  async function checkEvent(id,button){
    if(investigation.job){byId('events-detail').append(node('p','events-error','An investigation is already running. Let it finish or cancel it through the existing progress control.'));return;}
    button.disabled=true;
    try{
      const response=await fetch('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operation:'event',event_id:id,start:Number(byId('event-start').value),end:Number(byId('event-end').value)})});
      const spec=await response.json();if(!response.ok)throw new Error(spec.error||'This event request is unavailable.');
      const result=await runInvestigationJob(spec,'Checking event observations');
      if(!result||state.activeId!==id)return;
      state.payloads.set(id,result);renderDetail(result);drawEvent(result);
    }catch(error){byId('events-detail').append(node('p','events-error',error.message));}
    finally{button.disabled=false;byId('work-progress').hidden=true;}
  }
  function focusEdge(id){
    const card=Array.from(document.querySelectorAll('[data-edge-id]')).find(e=>e.dataset.edgeId===id);
    if(!card)return;document.querySelectorAll('.event-edge-focused').forEach(e=>e.classList.remove('event-edge-focused'));card.classList.add('event-edge-focused');card.scrollIntoView({block:'center',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});card.focus();
  }
  function restore(data){state.activeId=data.id;state.payloads.set(data.id,data);renderDetail(data);drawEvent(data);const select=byId('event-select');if(select)select.value=data.id;}

  /* ---------------------------------------------------------- public ---- */

  async function enter() {
    const detail = byId('events-detail');
    if (!detail.childElementCount) {
      detail.append(node('p', 'events-placeholder', EMPTY_DETAIL));
    }
    try {
      await loadIndex();
      if (!byId('events-list').childElementCount) renderRail();
      if(state.activeId&&state.payloads.has(state.activeId)){renderDetail(state.payloads.get(state.activeId));drawEvent(state.payloads.get(state.activeId));}
      // Opening the screen shows no event and draws nothing: the reader picks.
      renderer()?.resize?.();
    } catch (err) {
      byId('events-lede').textContent = err.message;
    }
  }

  function leave() {
    const map = renderer();
    if (map) { map.setConnections(investigation.connections||[]); map.setEventNodes([]); }
  }

  window.TerraEvents = {
    enter: enter,
    leave: leave,
    open: openEvent,
    clear: clearEvent,
    restore:restore,
    focusEdge:focusEdge,
    eventConnections:eventConnections,
    state: state
  };
  if(typeof module!=='undefined'&&module.exports)module.exports={eventConnections,edgeBlock};
})();
