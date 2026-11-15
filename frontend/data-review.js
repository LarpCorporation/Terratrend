/* Offline planning estimates and an explicit review before science requests. */
(function(root) {
  'use strict';
  let pending = null;

  function estimate(spec, catalog, supported) {
    if(spec.operation==='event'){
      if(!Array.isArray(spec.event_requests)||!spec.event_requests.length)throw new Error('The event needs an explicit source plan.');
      const regions=[...catalog.regions,...(spec.areas||[])];
      const parts=spec.event_requests.map(request=>estimate(request,{...catalog,regions},supported));
      return {months:Math.max(...parts.map(p=>p.months)),bytes:parts.reduce((n,p)=>n+p.bytes,0),
        requests:parts.reduce((n,p)=>n+p.requests,0),variables:[...new Set(parts.flatMap(p=>p.variables))],
        areas:[...new Map(parts.flatMap(p=>p.areas).map(a=>[a.id,a])).values()],
        routes:[...new Set(parts.flatMap(p=>p.routes))],discovery:false,automatic:false,regional:false,network:true,event:true};
    }
    const start = Number(spec.start), end = Number(spec.end);
    if (!Number.isInteger(start) || !Number.isInteger(end) || end - start < 8 || end - start > 100) throw new Error('Choose a valid period of at least nine years.');
    const months = 12 * (end - start + 1), automatic = spec.provider === 'nasa-merra2', regional=spec.provider==='nasa-giovanni';
    const network=['nasa-merra2','nasa-giovanni','nasa-hydrology','nasa-appeears','noaa-cdo','multi-source','auto'].includes(spec.provider);
    const available = catalog.variables.map(v => v.id).filter(id => !network || supported.includes(id));
    const discovery = spec.operation === 'scan';
    const variables = spec.operation==='interconnections'&&spec.relationship_variables?.length?spec.relationship_variables.slice():discovery ? (spec.routing?.variables||available).slice() : spec.operation === 'interconnections' ? available : spec.variables.slice();
    if (!variables.length) throw new Error('No supported measurements are available for this data source.');
    const features = new Map(catalog.regions.map(f => [f.id, f]));
    for (const f of spec.custom_areas || []) features.set(f.id, { ...f.properties, id: f.id });
    const tasks = new Map(), areas = new Map();
    function add(id, fields) {
      const area = features.get(id), b = area?.bbox;
      if (!Array.isArray(b) || b.length !== 4 || !b.every(Number.isFinite) || b[3] < b[1]) throw new Error('The selected area needs geographic bounds before its data use can be estimated.');
      areas.set(id, area);
      for (const field of fields) tasks.set(id + '|' + field, { area, field });
    }
    if (spec.operation === 'overview') {
      if (!spec.features?.length) throw new Error('Choose a geographic layer with areas first.');
      for (const id of spec.features) add(id, variables.slice(0, 1));
    } else {
      add(spec.region, variables);
      if (spec.compare_region && !discovery && spec.operation !== 'interconnections') add(spec.compare_region, variables);
    }
    if (spec.operation === 'interconnections' && spec.relationship_scope!=='local') {
      const defaults = ['T2M', 'PRECTOTCORR', 'GWETROOT', 'TS', 'WS2M', 'RH2M', 'EVPTRNS', 'ALLSKY_SFC_SW_DNI'];
      let remoteFields = (spec.relationship_variables?.length?spec.relationship_variables:spec.target_vars?.length ? spec.target_vars : defaults).filter(id => available.includes(id));
      if (!remoteFields.length) remoteFields = defaults.filter(id => available.includes(id));
      for (const id of spec.target_regions || []) if (id !== spec.region) add(id, remoteFields);
    }
    let bytes = 0, requests = 0;const routes=new Set();
    for (const { area,field } of tasks.values()) {
      const route=spec.routing?.routes?.[area.id]?.[field] || (spec.provider!=='multi-source'&&spec.provider!=='auto'?spec.provider:['NDVI','EVI'].includes(field)?'nasa-appeears':['T10M','QV10M'].includes(field)?'nasa-giovanni':field.startsWith('GLDAS_')?'nasa-hydrology':field.startsWith('STATION_')?'noaa-cdo':'nasa-merra2');
      routes.add(route);
      if(route==='nasa-giovanni'||route==='nasa-appeears'){requests++;bytes+=months*160+100000;continue;}
      if(route==='noaa-cdo'){requests+=13;bytes+=1000000+60*months*160;continue;}
      if(route==='nasa-hydrology'){
        const [w,s,e,n]=area.bbox,count=(Math.ceil((e-w)/.25)+2)*(Math.ceil((n-s)/.25)+2);
        requests+=count;bytes+=count*(months*80+1000);continue;
      }
      if(route!=='nasa-merra2')continue;
      const [west, south, east, north] = area.bbox;
      const across = west > east;
      const nx = across ? Math.min(576, Math.ceil((east + 360 - west) / .625) + 2)
        : Math.min(576, Math.floor((east + 180 + .3125) / .625) - Math.ceil((west + 180 - .3125) / .625) + 1);
      const low = Math.max(0, Math.ceil((south + 90 - .25) / .5));
      const high = Math.min(360, Math.floor((north + 90 + .25) / .5));
      const ny = Math.max(1, high - low + 1), parts = across ? 2 : 1;
      // Cold-cache planning allowance: 8 bytes per value/axis plus 50 kB per
      // native subset for its container and metadata. Actual files can differ.
      bytes += months * (Math.max(1, nx) * ny * 8 + (Math.max(1, nx) + ny) * 8 + parts * 50000);
      requests += months * parts;
    }
    return { months, bytes, requests, variables, areas: [...areas.values()], routes:[...routes],discovery, automatic, regional,network,
      relationships: spec.operation === 'interconnections', layer: spec.operation === 'overview' };
  }

  function finish(approved) {
    if (!pending) return;
    const current = pending; pending = null;
    const restoreFocus = current.modal.contains(root.document.activeElement);
    current.modal.classList.remove('open'); current.modal.hidden = true;
    if (restoreFocus) current.previous?.focus?.();
    current.resolve(approved);
  }

  function review(spec, catalog, supported) {
    const plan = estimate(spec, catalog, supported), d = root.document;
    const modal = d?.getElementById('data-review-modal');
    if (!modal) return Promise.reject(new Error('Reload TerraTrend to load its data-use review before starting an analysis.'));
    finish(false);
    const el = id => d.getElementById(id);
    el('data-review-title').textContent = plan.discovery ? 'Find what is changing.' : plan.relationships ? 'Check the relationship search.' : 'Here is what we will look up.';
    /* Say it the way a person would: where, what, when. */
    const placeNames = plan.areas.map(a => a.name + (a.level==='custom' ? ` (${a.bbox.map(v=>Number(v).toFixed(1)).join(', ')})` : '')).join(' and ');
    el('data-review-scope').textContent = `${plan.variables.map(id => catalog.variables.find(v => v.id === id)?.name || id).join(', ')} for ${placeNames}, ${spec.start}–${spec.end}.`;
    el('data-review-size').textContent = plan.network ? `about ${(plan.bytes / 1e6).toLocaleString(undefined, { maximumFractionDigits: plan.bytes < 1e7 ? 1 : 0 })} MB` : 'nothing new';
    el('data-review-files').textContent = plan.network ? `Usually far less, because anything already looked up is reused. This is a worst case with nothing saved yet.` : 'This result is already on this computer.';
    if(plan.regional){el('data-review-files').textContent = `A worst case with nothing saved yet; anything already looked up is reused.`;}
    el('data-review-note').textContent = plan.regional?'NASA Giovanni calculates rectangle averages on its servers. This estimate covers small CSV results and an allowance for metadata; progress checks and actual responses can change total transfer. Each response is limited to 2 MB. No native-grid download fallback. This mode uses monthly M2IMNXASM, a different MERRA-2 product from native mode; values need not match. Native-cell maps and monthly area-coverage checks are not supplied.':plan.automatic
      ? 'Planning estimate for an empty cache, not a hard data cap. It allows for native grid values and file metadata. Compression and existing cached subsets can reduce the transfer; actual service responses can differ. NASA sends selected grid windows, then this computer stores them and calculates the trends.'
      : plan.network?'Planning estimate, not a traffic cap. '+plan.routes.map(route=>({
          'nasa-merra2':'NASA returns selected native grid windows; this computer weights them to the polygon.',
          'nasa-hydrology':'Hydrology returns monthly histories for every intersecting 0.25° cell (maximum 512 per area).',
          'noaa-cdo':'NOAA returns observations from a fixed station cohort inside the polygon; these are not area averages.',
          'nasa-appeears':'AppEEARS processes the polygon on NASA servers; only statistics CSVs are downloaded. No extra pixel-quality filter or monthly area audit is applied.',
          'nasa-giovanni':'Giovanni returns monthly MERRA-2 rectangle averages; monthly area support is unknown.'
        })[route]||'').join(' ')+' Metadata and processing checks add traffic. Summary/point-service responses are limited to 2 MB each; native windows have their own limit. Matching observations are cached.':'This provider reads scientific observations already stored on this computer. Missing observations stay missing.';
    el('data-review-note').textContent = 'Method: ' + el('data-review-note').textContent;
    if(spec.routing){el('data-review-note').textContent+=' '+(spec.routing.warnings||[]).join(' ');if(spec.routing.excluded?.length)el('data-review-note').textContent+=' '+spec.routing.excluded.length+' incompatible measurements excluded from discovery; their sources do not support this extent.';}
    const list = el('data-review-variables'); list.replaceChildren();
    for (const id of plan.variables) {
      const item = d.createElement('li'); item.textContent = (catalog.variables.find(v => v.id === id)?.name || id)+(spec.routing?' · '+[...new Set(Object.values(spec.routing.routes).map(r=>r[id]).filter(Boolean))].map(r=>({'nasa-merra2':'NASA native grids','nasa-giovanni':'NASA rectangle series','nasa-appeears':'NASA vegetation summary','nasa-hydrology':'NASA hydrology series','noaa-cdo':'NOAA stations'})[r]||r).join(' / '):''); list.append(item);
    }
    el('data-review-purpose').textContent = plan.discovery
      ? 'Nothing is selected yet, so we will test which measurements have enough data to answer for this place.'
      : plan.relationships
        ? 'We will test whether these measurements moved together over the same months. A link is an association, not a cause.'
        : plan.layer
          ? 'Every area you can see gets its own result.'
          : 'The result is calculated from NASA observations for exactly this place and period.';
    if(plan.event)el('data-review-purpose').textContent='This checks only the listed event study areas and measurements. The selected window tests historical associations; it does not attribute the individual event to a cause. '+(spec.exclusions?.length?spec.exclusions.length+' unsupported source slots will remain explicitly unavailable.':'');
    if(false)el('data-review-purpose').textContent = plan.regional
      ? 'Giovanni will calculate monthly averages for the selected rectangle'+(plan.areas.length>1?'s':'')+'. '+(plan.discovery?`Discovery tests this mode’s ${plan.variables.length} supported measurements. `:'')+'NASA’s rectangle weighting and M2IMNXASM product are used; these are not exact-polygon native-grid results. An existing matching regional result can be reused.'
      : plan.discovery
      ? 'No variable is selected: discovery tests the supported measurements for primary area A. Significant increases, significant decreases, nonsignificant results and insufficient data remain distinct. Choose a result to open its chart.'
      : plan.relationships ? (spec.relationship_scope==='local'?'This search tests only the selected area and companion measurements. No remote-country search is included. ':'This search also tests the explicitly listed remote areas. ')+'Source-qualified monthly observations share a calendar and selected boundary, but can have different resolution, weighting and quality. Relationships are exploratory; they do not establish physical causes or predict future impacts.'
      : plan.layer ? 'Each area in the displayed layer receives its own calculation. A result for the parent area is not reused as its children’s verdict.'
      : 'The selected measurements will be analyzed for the exact saved areas. Existing source subsets are reused when their field, revision and native window match.';
    return new Promise(resolve => {
      pending = { modal, previous: d.activeElement, resolve };
      el('data-review-start').onclick = () => finish(true);
      el('data-review-cancel').onclick = el('data-review-close').onclick = () => finish(false);
      modal.onclick = event => { if (event.target === modal) finish(false); };
      modal.onkeydown = event => {
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); finish(false); }
        if (event.key === 'Tab') {
          const buttons = [...modal.querySelectorAll('button')].filter(b => !b.disabled);
          const first = buttons[0], last = buttons.at(-1);
          if (event.shiftKey && d.activeElement === first) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && d.activeElement === last) { event.preventDefault(); first.focus(); }
        }
      };
      modal.hidden = false; modal.classList.add('open'); el('data-review-cancel').focus();
    });
  }

  const api = { estimate, review, cancel: () => finish(false) };
  root.TerraDataReview = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window === 'undefined' ? globalThis : window);
