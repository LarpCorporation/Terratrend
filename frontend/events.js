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
    verified_from_source: { text: 'Verified', cls: 'ev-ok' },
    awaiting_source: { text: 'Awaiting source', cls: 'ev-await' },
    unavailable: { text: 'Not connected', cls: 'ev-off' },
    insufficient_data: { text: 'Insufficient data', cls: 'ev-thin' },
    declared: { text: 'Declared', cls: 'ev-thin' }
  };

  const state = {
    index: null,
    activeId: null,
    payloads: new Map(),
    abort: null
  };

  const EMPTY_DETAIL = 'Pick an event from the menu to load its observations, '
    + 'its pathways on the globe, and photographs of what happened.';

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
      'Documented Earth-system events. Choose one to load NASA observations, '
      + 'its pathways on the globe, and photographs of what happened.';
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
    list.append(buildLegend());
  }

  function buildLegend() {
    const legend = node('details', 'ev-legend');
    legend.append(node('summary', null, 'What the badges mean'));
    const rows = state.index.status_legend || {};
    const ul = node('ul', 'ev-legend-list');
    for (const key of ['verified_from_source', 'unavailable', 'awaiting_source', 'insufficient_data']) {
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
      img.addEventListener('error', () => { figure.hidden = true; });
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

    const head = node('div', 'ev-edge-head');
    head.append(node('strong', 'ev-edge-title', edge.label));
    head.append(node('span', 'ev-badge ' + status.cls, status.text));
    card.append(head);

    if (v.status === 'verified_from_source') {
      const numbers = node('p', 'ev-numbers');
      numbers.append(node('b', null, 'r = ' + num(v.r_value, 2)));
      numbers.append(node('span', null, v.lag_months_observed > 0
        ? 'leads by ' + v.lag_months_observed + ' months'
        : v.lag_months_observed < 0
          ? 'follows by ' + Math.abs(v.lag_months_observed) + ' months'
          : 'simultaneous'));
      numbers.append(node('span', null, 'p = ' + pText(v.p_value_neff)));
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
      if (x.proxy_for) {
        card.append(node('p', 'ev-proxy', sentence(x.variable + ' stands in for '
          + x.proxy_for + '. ' + (x.proxy_note || ''))));
      }
    } else {
      card.append(node('p', 'ev-reason', v.reason || 'This pathway has no available source yet.'));
      const legend = (state.index.status_legend || {})[v.status];
      if (legend) card.append(node('p', 'ev-mini', legend));
      const x = v.x || {};
      if (x.proxy_for) card.append(node('p', 'ev-provenance', x.variable + ' stands in for ' + x.proxy_for));
    }

    const details = node('details', 'ev-details');
    details.append(node('summary', null, 'Mechanism and evidence'));
    details.append(mechanismBlock(edge));
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

    const pics = gallery(data.images);
    if (pics) detail.append(pics);

    if (data.status === 'ongoing_developing') {
      const watch = node('div', 'ev-watch-note');
      watch.append(node('strong', null, 'How to read this card'));
      watch.append(node('p', null,
        'An El Niño is Pacific warming by definition, so the driver is observable now. '
        + 'What is not observable yet is the regional response: rainfall lags the Pacific '
        + 'by months and has not played out. The numbers below describe the historical '
        + 'relationship, not a forecast.'));
      detail.append(watch);
    }

    detail.append(node('h3', 'ev-section', 'What the data shows'));
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

  function drawEvent(data) {
    const map = renderer();
    if (!map) return;
    const nodes = new Map((data.nodes || []).map(n => [n.id, n]));

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

    const connections = (data.edges || []).map(edge => {
      const a = nodes.get(edge.source_node), b = nodes.get(edge.target_node);
      if (!a || !b || a.id === b.id) return null;
      const v = edge.verification || {};
      const r = (typeof v.r_value === 'number') ? v.r_value : 0;
      return {
        source_region: a,
        target_region: b,
        relationship: v.lag_months_observed === 0 ? 'simultaneous' : 'response',
        lag_months: v.lag_months_observed || 0,
        direction: r < 0 ? 'inverse' : 'direct',
        label: edge.label,
        confidence: edge.confidence
      };
    }).filter(Boolean);
    map.setConnections(connections);

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
      return;
    }

    detail.textContent = '';
    const loading = node('div', 'events-loading');
    loading.append(node('p', null, 'Reading NASA observations for this event…'));
    loading.append(node('p', 'ev-mini',
      'The first visit downloads and caches the series; later visits are instant.'));
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
    } catch (err) {
      if (err.name === 'AbortError' || state.activeId !== id) return;
      detail.textContent = '';
      detail.append(node('p', 'events-error', err.message));
    }
  }

  /* ---------------------------------------------------------- public ---- */

  async function enter() {
    const detail = byId('events-detail');
    if (!detail.childElementCount) {
      detail.append(node('p', 'events-placeholder', EMPTY_DETAIL));
    }
    try {
      await loadIndex();
      if (!byId('events-list').childElementCount) renderRail();
      // Opening the screen shows no event and draws nothing: the reader picks.
      renderer()?.resize?.();
    } catch (err) {
      byId('events-lede').textContent = err.message;
    }
  }

  function leave() {
    const map = renderer();
    if (map) { map.setConnections([]); map.setEventNodes([]); }
  }

  window.TerraEvents = {
    enter: enter,
    leave: leave,
    open: openEvent,
    clear: clearEvent,
    state: state
  };
})();
