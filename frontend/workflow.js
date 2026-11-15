/* Geographic investigation workflow. Legacy chart/statistics controllers are
   retained in app.js; this module owns selection, jobs and renderer binding. */
const investigation = {level:'continent',scope:'',features:[],areas:{a:null,b:null},featureStore:new Map(),seq:0,analysisCall:0,job:null,provider:'auto',nasa:null,appeears:null,boundaryView:{level:'continent',scope:''},providersLoaded:false,providerError:null,connecting:false,screen:'map',slot:'a',map:null,mapVariable:null,evidenceElement:null,geoCache:new Map(),geographicCall:0,geoAbort:null,loadingBoundaries:false,resultKey:null,completedJobs:new Map(),savedResults:[],connections:[]};
const oldRender = window.TerraLegacy.render;
const oldClearResults = window.TerraLegacy.clearResults;
const oldRenderSatellite = window.TerraLegacy.renderSatellite;
const oldRenderDataModal = window.TerraLegacy.renderDataModal;

function currentRegion() {return investigation.areas.a||state.catalog?.regions.find(r=>r.id===$('region')?.value)||null;}
function currentCompareRegion() {return investigation.areas.b||state.catalog?.regions.find(r=>r.id===$('compare-region')?.value)||null;}
function investigationKey() {return [currentRegion()?.id,currentCompareRegion()?.id,state.compareMode,state.selected.join(','),state.selected[state.activeVarIdx],$('start')?.value,$('end')?.value,investigation.provider].join('|');}
function investigationContextKey() {return [currentRegion()?.id,state.compareMode?currentCompareRegion()?.id:'',state.selected.join(','),$('start')?.value,$('end')?.value,investigation.provider].join('|');}

/* ---------------------------------------------------------------------------
   ONE source of truth for "what does the run control do?".
   The requested operation, the editable selection and the context of the
   displayed completed result are separate things. A button labelled
   "Analyze Area A" only ever submits area A. A comparison needs a real,
   different area B, and the label says so when it does not have one.
   --------------------------------------------------------------------------- */
function validComparisonArea(){const a=currentRegion(),b=currentCompareRegion();return b&&a&&b.id!==a.id?b:null;}
function comparisonActive(){return state.compareMode===true&&!!validComparisonArea();}
function resolveRunAction(){
  const a=currentRegion(),b=validComparisonArea();
  if(!state.selected.length)return {kind:'discover',label:'FIND WHAT IS CHANGING HERE',areaA:a,areaB:null};
  if(!a)return {kind:'blocked',label:'CHOOSE A REGION',reason:'Pick a region on the map or from the list first.'};
  if(state.compareMode&&!b)return {kind:'need-b',label:'ADD A REGION TO COMPARE',areaA:a,areaB:null,reason:`Comparison is on but no second region is chosen. Add one below, or remove the comparison to study ${a.name} alone.`};
  if(state.compareMode&&b)return {kind:'compare',label:'COMPARE REGIONS',areaA:a,areaB:b};
  return {kind:'analyze',label:'ANALYZE REGION',areaA:a,areaB:null};
}
/* The tutorial and other listeners observe real user actions here. */
function announceAction(action,detail){try{document.dispatchEvent(new CustomEvent('terratrend:action',{detail:{action,...(detail||{})}}));}catch(_){/*older browsers*/}}
function requireComparisonArea(){
  state.compareMode=true;prepareInvestigation(false);refreshSelection(false);
  window.TerraWorkspace?.requireComparison?.();
  setStatus('warn','Comparison is on but area B is empty. Choose area B, or remove the comparison to analyze area A only.');
  if(typeof activateSelectionSlot==='function')activateSelectionSlot('b');
  else openDrawer(true);
}

function openDrawer(open) {document.body.dataset.drawer='closed';$('drawer-toggle').setAttribute('aria-expanded',String(open));const picker=$('measurement-picker');if(picker)picker.open=open;if(open)window.TerraWorkspace?.open?.();}
function showInvestigationScreen(screen) {
  const previousScreen=investigation.screen;
  investigation.screen=screen;document.body.dataset.screen=screen;
  document.body.dataset.evidence='graphs';
  document.querySelectorAll('[data-analysis-evidence]').forEach(b=>{b.classList.toggle('active',b.dataset.analysisEvidence==='graphs');b.setAttribute('aria-pressed',String(b.dataset.analysisEvidence==='graphs'));});
  $('data-methods-screen').hidden=screen!=='sources';
  if($('events-screen')){
    $('events-screen').hidden=screen!=='events';
    if(screen==='events')window.TerraEvents?.enter?.();
    else if(previousScreen==='events')window.TerraEvents?.leave?.();
  }
  document.querySelectorAll('[data-kview]').forEach(el=>el.classList.toggle('active',el.dataset.kview===(screen==='analysis'?'observatory':screen)));
  $('ix-screen').hidden=screen!=='interconnect';$('ix-screen').classList.toggle('open',screen==='interconnect');
  if(screen==='interconnect'&&typeof syncRemoteAction==='function')syncRemoteAction();
  announceAction('navigate',{screen});
  if(screen==='map')investigation.map?.resize();
  else if(typeof closeSelectionTools==='function')closeSelectionTools();
  window.TerraWorkspace?.refresh?.();
  if(screen==='analysis'||screen==='compare'){
    $('analysis-page-title').textContent=screen==='compare'?'Two places. One question.':'A closer look at change.';
    $('analysis-empty').hidden=!!state.result;
    requestAnimationFrame(()=>chart?.resize());
  }
}
function cancelPendingWork() {
  state.analyzeSeq++;investigation.seq++;investigation.analysisCall++;
  window.TerraDataReview?.cancel?.();
  $('run').disabled=false;$('k-scan-cta').disabled=false;$('scan').disabled=false;
  if(investigation.job){fetch(`/api/jobs/${investigation.job}/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).catch(()=>{});investigation.job=null;}
  $('work-progress').hidden=true;
}
function prepareInvestigation(clearMap=true) {
  setTimeout(()=>loadSavedTrendMap(true),0);
  cancelPendingWork();
  if($('compatibility-help'))$('compatibility-help').hidden=true;
  setStatus('ok','');
  if(!state.result){oldClearResults();renderRegionCard(null);}
  updateGlobeOverlay();
  $('sat-summary').textContent='Satellite comparison is retained here. Its imagery source is paused until the challenge-resource data setup is completed.';$('sat-tag').textContent='SOURCE SETUP';
  $('analysis-empty').hidden=!!state.result;$('analysis-context').textContent=state.result?'PREVIOUS COMPLETED RESULT · EDITS ARE NOT YET ANALYZED':'PREPARED · CHOOSE ANALYZE';
  const readiness=sourceReadiness();$('selection-coverage').textContent=readiness.code==='ready'?(state.selected.length?'Selection prepared. Choose Analyze to calculate its trend.':'Selection prepared. Choose Analyze to discover which supported measurements are changing.'):'Selection saved. '+readiness.message;
  refreshVariableStrip();refreshSelection(false);
  window.TerraWorkspace?.refresh?.();
}
function clearResults() {prepareInvestigation(false);}
function renderRegionSelect() {
  const level=investigation.level;
  /* Prefer the boundary layer that is actually on the map. A legacy caller can
     run this after a layer has loaded; falling back to the catalog alone would
     leave the list showing continents while the globe shows countries. */
  const loaded=investigation.features.map(f=>f.properties).filter(f=>f&&f.level===level);
  const list=loaded.length?loaded
    :state.catalog.regions.filter(r=>r.level===level&&(!investigation.scope||r.parent===investigation.scope||r.continent===investigation.scope));
  setAreaOptions(list,currentRegion()?.id||'',$('compare-region')?.value||'');
}
function setAreaOptions(list, a=currentRegion()?.id||$('region').value, b=currentCompareRegion()?.id||$('compare-region').value) {
  for(const [id,wanted] of [['region',a],['compare-region',b]]){
    const slot=id==='region'?'a':'b',selected=state.catalog.regions.find(f=>f.id===wanted)||investigation.areas[slot];
    const select=$(id);select.replaceChildren();
    const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent=id==='region'?'SELECT AREA A':'SELECT AREA B';select.append(placeholder);
    for(const f of list){const option=document.createElement('option');option.value=f.id;option.textContent=f.name;select.append(option);}
    if(selected&&!list.some(f=>f.id===selected.id)){const option=document.createElement('option');option.value=selected.id;option.textContent=`${selected.name} · selected ${selected.level||'area'}`;select.append(option);}
    select.value=selected?.id||'';investigation.areas[slot]=selected||null;
  }
  refreshSelection(false);
}
function refreshSelection(focus=true) {
  const a=currentRegion(),b=state.compareMode?validComparisonArea():null;
  investigation.map?.setSelections([a?.id,b?.id]);
  investigation.map?.setSelectionFeatures([investigation.featureStore.get(a?.id),investigation.featureStore.get(b?.id)]);
  if(focus&&a)investigation.map?.focusFeature(a);
  $('region-desc').textContent=a?.desc||'Choose an area';$('compare-region-desc').textContent=b?.desc||'';
  $('krc-name').textContent=a?.name||'Select an area';$('krc-surface').textContent=a?.level||'—';
  $('compare-selection-summary').hidden=!state.compareMode;
  $('compare-selection-summary').textContent=state.compareMode?`B / ${b?.name||'Choose a second area'}`:'';
  $('region-readout').textContent=a?.name||'NO AREA SELECTED';$('k-foot-region').textContent=a?.name?.toUpperCase()||'EARTH';
  const scope=state.catalog?.regions.find(r=>r.id===investigation.scope);
  $('selection-breadcrumb').textContent=['WORLD',scope?.name,investigation.level.toUpperCase(),state.compareMode?'SELECT A + B':null].filter(Boolean).join(' / ');
  const card=$('k-region-card');if(card)card.dataset.compare=String(!!state.compareMode);
  const pill=$('toggle-compare-mode');if(pill){pill.textContent=state.compareMode?'A + B · COMPARISON ON':'ADD COMPARISON B';pill.classList.toggle('active',!!state.compareMode);pill.setAttribute('aria-pressed',String(!!state.compareMode));}
  const group=$('compare-region-group');if(group)group.style.display=state.compareMode?'block':'none';
  const hint=$('comparison-hint');
  if(hint){hint.hidden=!(state.compareMode&&!b);hint.textContent=state.compareMode&&!b?'Area B is empty. Choose a second area on the map or from the list below. Until then the run control will not start a comparison.':'';}
  if(typeof refreshSelectionTools==='function')refreshSelectionTools();
}
/* Resolve an area chosen from a list against everything the app knows: the
   catalog, the displayed boundary layer, a stored feature and the current
   selection. Without this a list choice silently registered no area at all. */
function areaMetaFor(id){
  if(!id)return null;
  return state.catalog?.regions?.find(f=>f.id===id)
    || investigation.features.map(f=>f.properties).find(f=>f.id===id)
    || investigation.featureStore.get(id)?.properties
    || [investigation.areas.a,investigation.areas.b].find(a=>a?.id===id)
    || null;
}
function areaFeatureFor(id){
  const meta=areaMetaFor(id);if(!meta)return null;
  const stored=investigation.featureStore.get(id);
  return stored||{type:'Feature',id,properties:meta,geometry:meta.geometry||null};
}
function onRegionChange() {
  const id=$('region').value;
  investigation.areas.a=areaMetaFor(id);
  const feature=areaFeatureFor(id);
  if(feature&&feature.geometry)investigation.featureStore.set(id,feature);
  state.pendingBbox=null;prepareInvestigation(false);refreshSelection(true);
  announceAction('area-selected',{slot:'a',id:investigation.areas.a?.id||null,name:investigation.areas.a?.name||null,level:investigation.areas.a?.level||null});
}
function onCompareRegionChange() {
  const id=$('compare-region').value;
  investigation.areas.b=areaMetaFor(id);
  const feature=areaFeatureFor(id);
  if(feature&&feature.geometry)investigation.featureStore.set(id,feature);
  prepareInvestigation(false);refreshSelection(false);
  announceAction('area-selected',{slot:'b',id:investigation.areas.b?.id||null,name:investigation.areas.b?.name||null,level:investigation.areas.b?.level||null});
}
/* Turning comparison on is an explicit request for a second area; turning it
   off removes the comparison area and restores the A-only action. */
function toggleCompareMode() {
  state.compareMode=!state.compareMode;investigation.slot=state.compareMode?'b':'a';
  if(!state.compareMode){investigation.areas.b=null;const bSel=$('compare-region');if(bSel)bSel.value='';}
  prepareInvestigation(false);refreshSelection(false);
  announceAction('compare-mode',{enabled:state.compareMode});
}
function addComparisonArea(){
  if(!state.compareMode)state.compareMode=true;
  requireComparisonArea();
}
function removeComparisonArea(){
  cancelPendingWork();
  state.compareMode=false;investigation.areas.b=null;investigation.slot='a';
  const bSel=$('compare-region');if(bSel)bSel.value='';
  prepareInvestigation(false);refreshSelection(false);
  window.TerraWorkspace?.refresh?.();
  announceAction('compare-mode',{enabled:false});
}
function selectMapFeature(feature) {
  if(investigation.loadingBoundaries)return;
  if((investigation.provider==='nasa-giovanni'||state.selected.some(id=>['T10M','QV10M'].includes(id)))&&!isGiovanniRectangle(feature)){
    window.TerraWorkspace?.showIssues?.([{region:feature.id,message:'These measurements need a coordinate rectangle. Use a rectangular preset or coordinate bounds; your current area is retained.',action:'bounds'}]);return;
  }
  const selected=investigation.slot==='a'?currentRegion():currentCompareRegion();
  if(selected?.id===feature.id){clearSelectionArea();return;}
  /* A saved coloured area opens its own stored evidence unless a fresher
     current result already exists for it. */
  const saved=savedCellFor(feature.id);
  if(saved&&!state.result){
    window.TerraWorkspace?.restoreSavedById?.(saved.result_id);
    flashHint(`${feature.properties.name.toUpperCase()} · OPENING SAVED RESULT`);
    return;
  }
  if(!assignSelectionArea(investigation.slot,feature))return;
  if(typeof selectionToolMessage==='function')selectionToolMessage(`Area ${investigation.slot.toUpperCase()} selected. Choose another tool or run Analyze.`);
  flashHint(`${feature.properties.name.toUpperCase()} SELECTED · CHOOSE ANALYZE`);
}
async function setGeographicLevel(level,scope=null) {
  const seq=++investigation.geographicCall;
  investigation.geoAbort?.abort();investigation.geoAbort=new AbortController();
  investigation.loadingBoundaries=true;$('boundary-loading').hidden=false;window.TerraTour?.setBusy?.(true,'Loading boundaries for this layer…');
  if(investigation.map){investigation.map.cancelSelectionClick();investigation.map.pickingDisabled=true;}
  const selected=investigation.slot==='b'?currentCompareRegion():currentRegion();
  investigation.level=level;
  if(level==='preset')scope='';
  if(scope!==null)investigation.scope=scope;
  else if(level==='continent')investigation.scope='';
  else if(level==='region')investigation.scope=selected?.level==='country'?selected.id:(selected?.parent?.startsWith('country:')?selected.parent:investigation.scope.startsWith('country:')?investigation.scope:'country:gha');
  else if(level==='subcontinent')investigation.scope=selected?.level==='continent'?selected.id:'';
  else if(level==='country')investigation.scope=['subcontinent','continent'].includes(selected?.level)?selected.id:'';
  document.querySelectorAll('[data-level]').forEach(b=>{b.classList.toggle('active',b.dataset.level===level);b.setAttribute('aria-pressed',String(b.dataset.level===level));});
  $('geography-presets').setAttribute('aria-pressed',String(level==='preset'));$('geography-presets').classList.toggle('active',level==='preset');
  populateScope();$('coord-readout').textContent='LOADING BOUNDARIES…';
  const key=level+'|'+investigation.scope;
  const scopeName=state.catalog.regions.find(r=>r.id===investigation.scope)?.name;
  $('boundary-loading-label').textContent=`Loading ${scopeName||'world'} boundaries… First-time country downloads can take longer.`;
  try{
    let data=investigation.geoCache.get(key);
    if(!data){const response=await fetch('/api/geography?'+new URLSearchParams({level,...(investigation.scope?{parent:investigation.scope}:{})}),{signal:investigation.geoAbort.signal});data=await response.json();if(!response.ok)throw new Error(response.status===404?'Restart the TerraTrend Python server to load geographic boundaries.':data.error||'Boundary data unavailable');investigation.geoCache.set(key,data);}
    if(seq!==investigation.geographicCall)return;
    investigation.features=data.features;
    for(const f of data.features){investigation.featureStore.set(f.id,f);if(!state.catalog.regions.some(r=>r.id===f.id))state.catalog.regions.push(f.properties);}
    /* Populate the area list from the layer that just loaded BEFORE touching
       the globe. A superseded map redraw must never leave the list showing the
       previous layer's areas. */
    const a=currentRegion()?.id,b=currentCompareRegion()?.id;
    setAreaOptions(data.features.map(f=>f.properties),a,b);
    refreshSelection(false);
    $('boundary-loading-label').textContent=`Drawing ${data.features.length} boundaries…`;
    if(investigation.map&&!await investigation.map.setFeatures(data.features,()=>seq===investigation.geographicCall))return;
    if(seq!==investigation.geographicCall)return;
    prepareInvestigation();refreshSelection(false);
    if(level==='region')investigation.map?.focusFeature(state.catalog.regions.find(r=>r.id===investigation.scope));
    const country=state.catalog.regions.find(r=>r.id===investigation.scope);
    $('coord-readout').textContent=`${data.features.length} ${level==='preset'?'PRESET FOCUS BOXES · NOT OFFICIAL ECOLOGICAL BOUNDARIES':level==='region'?'REGIONS · '+country?.name.toUpperCase()+' · CHANGE COUNTRY ABOVE':'AREAS · NATURAL EARTH 1:50M'}`;
  }catch(e){if(e.name==='AbortError')return;if(seq===investigation.geographicCall){setStatus('err',esc(e.message));$('coord-readout').textContent='BOUNDARIES UNAVAILABLE';investigation.features=[];investigation.map?.setFeatures([]);setAreaOptions([]);prepareInvestigation();setStatus('err',esc(e.message));openDrawer(true);}}finally{if(seq===investigation.geographicCall){investigation.loadingBoundaries=false;$('boundary-loading').hidden=true;if(investigation.map)investigation.map.pickingDisabled=false;window.TerraTour?.setBusy?.(false);announceAction('boundary-loaded',{level:investigation.level,count:investigation.features.length});}}
}
async function togglePresetRegions(){
  if(investigation.level==='preset')return setGeographicLevel(investigation.boundaryView.level,investigation.boundaryView.scope);
  investigation.boundaryView={level:investigation.level,scope:investigation.scope};
  return setGeographicLevel('preset','');
}
function populateScope() {
  const select=$('geography-scope');select.replaceChildren();
  const level=investigation.level;
  if(level==='preset'){
    const empty=document.createElement('option');empty.value='';empty.textContent='CHOOSE A PRESET';select.append(empty);
    for(const f of state.catalog.regions.filter(r=>r.level==='preset')){const o=document.createElement('option');o.value=f.id;o.textContent=f.name;select.append(o);}
    select.value=currentRegion()?.level==='preset'?currentRegion().id:'';select.disabled=false;$('scope-label').textContent='FOCUS BOX';return;
  }
  if(level!=='region'){const option=document.createElement('option');option.value='';option.textContent=level==='continent'?'WORLD':'ALL AREAS';select.append(option);}
  const scopes=level==='region'?state.catalog.regions.filter(r=>r.level==='country'):level==='continent'?[]:state.catalog.regions.filter(r=>r.level==='continent'||(level==='country'&&r.level==='subcontinent'));
  for(const f of scopes){const option=document.createElement('option');option.value=f.id;option.textContent=f.name;select.append(option);}
  select.value=investigation.scope;select.disabled=level==='continent';
  $('scope-label').textContent=level==='region'?'COUNTRY':'WITHIN';
}
function toggleVar(id) {
  if(!state.selected.includes(id)&&!variableSourceAvailable(id)){const variable=state.catalog.variables.find(v=>v.id===id);setStatus('warn',esc(`${variable?.name||id} still needs a verified mapping for this source. Choose an available measurement or change the data source.`));return;}
  if(state.selected.includes(id))state.selected=state.selected.filter(v=>v!==id);
  else if(state.selected.length<MAX_VARS)state.selected.push(id);
  else{setStatus('warn','Choose up to three variables. Deselect one to add another.');return;}
  state.activeVarIdx=0;prepareInvestigation();
  /* Update the checked item in place: rebuilding the list would drop keyboard
     focus to the document and lose the user's place in a long list. */
  const item=typeof document.querySelector==='function'?document.querySelector(`#var-list [data-variable="${id}"]`):null;
  if(item){const on=state.selected.includes(id);item.classList.toggle('on',on);const check=item.querySelector('input');if(check)check.checked=on;}
  else renderVarList();
  if($('var-count'))$('var-count').textContent=`${state.selected.length} / ${MAX_VARS}`;
  window.TerraWorkspace?.refresh?.();
  announceAction('measurement-checked',{id,checked:state.selected.includes(id),count:state.selected.length});
  loadSavedTrendMap(true);
}
function refreshVariableStrip() {
  if(!state.catalog)return;
  const strip=$('active-variable-strip');strip.replaceChildren();
  for(const v of state.catalog.variables.filter(v=>state.selected.includes(v.id))){
    const button=document.createElement('button');button.type='button';button.dataset.variable=v.id;button.className=state.selected.includes(v.id)?'active':'';
    button.className=(state.selected.includes(v.id)?'selected ':'')+(state.selected[state.activeVarIdx]===v.id?'active':'');
    const available=variableSourceAvailable(v.id);button.disabled=!available;button.classList.toggle('source-unavailable',!available);
    button.title=`${v.name} · ${v.id} · ${v.unit}`+(available?'':' · Source mapping needed');button.textContent=v.name;button.setAttribute('aria-pressed',String(state.selected[state.activeVarIdx]===v.id));
    button.onclick=()=>{
      if(state.selected.includes(v.id)&&state.result){cancelPendingWork();state.activeVarIdx=state.selected.indexOf(v.id);render();refreshVariableStrip();}
      else{if(state.selected.includes(v.id))state.activeVarIdx=state.selected.indexOf(v.id);else{state.selected=[v.id];state.activeVarIdx=0;}prepareInvestigation();renderVarList();}
    };strip.append(button);
  }
  requestAnimationFrame(()=>strip.querySelector('[aria-pressed="true"]')?.scrollIntoView({block:'nearest',inline:'nearest'}));
  $('selected-variable-count').textContent=state.selected.length;
}
function updateGlobeOverlay() {refreshVariableStrip();}
/* ---------------------------------------------------------------------------
   Persistent trend map built from previously completed, compatible results.
   This only READS stored verdicts: it never creates a job or an observation
   request. A cell appears only for the exact measurement, date window and
   geographic level that was actually saved, so a national result never
   colours its subregions and two different windows are never mixed.
   --------------------------------------------------------------------------- */
const savedTrendState={token:0,variable:null,start:null,end:null,cells:[],exact:false,alternatives:[],loaded:false,error:null};
async function loadSavedTrendMap(force=false){
  const variable=state.selected[state.activeVarIdx]||state.selected[0]||null;
  const start=$('start')?.value,end=$('end')?.value;
  if(!variable||!start||!end||+end<+start){renderSavedTrendLayer();return;}
  if(!force&&savedTrendState.loaded&&savedTrendState.variable===variable&&savedTrendState.start===start&&savedTrendState.end===end)return;
  const token=++savedTrendState.token;
  savedTrendState.variable=variable;savedTrendState.start=start;savedTrendState.end=end;savedTrendState.loaded=true;
  try{
    /* No level restriction: every stored cell is keyed by its exact area id and
       level, and only areas actually present in the displayed boundary layer
       can be coloured. A national result therefore never bleeds into a
       subregion, while switching layers still reveals stored colours. */
    const qs=new URLSearchParams({variable,start:String(start),end:String(end)});
    const reply=await fetch('/api/results/map?'+qs.toString());
    const body=await reply.json();
    if(token!==savedTrendState.token)return;
    if(!reply.ok){savedTrendState.error=body.error||'stored results unavailable';savedTrendState.cells=[];savedTrendState.alternatives=[];savedTrendState.exact=false;}
    else{savedTrendState.error=null;savedTrendState.cells=body.cells||[];savedTrendState.alternatives=body.alternatives||[];savedTrendState.exact=!!body.exact;}
  }catch(e){if(token!==savedTrendState.token)return;savedTrendState.error=e.message;savedTrendState.cells=[];savedTrendState.exact=false;}
  renderSavedTrendLayer();
}
function savedCellFor(areaId){
  return (savedTrendState.cells||[]).find(c=>c.area_id===areaId)||null;
}
function renderSavedTrendLayer(){
  const rows=(savedTrendState.cells||[]).filter(c=>c.area_id).map(c=>({
    id:c.area_id,
    unit:c.verdict?.unit||(c.variables||[])[0]?.unit||'',
    window:c.window,
    saved:true,
    overall:{...c.verdict,ok:c.verdict?.ok!==false,significant:!!c.verdict?.significant,direction:c.verdict?.direction,per_decade:c.verdict?.per_decade},
    provenance:{source:'saved result'}
  }));
  investigation.map?.setSavedTrends?.(rows);
  const note=$('saved-trend-note');
  if(!note)return;
  if(!savedTrendState.variable){note.hidden=true;return;}
  note.hidden=false;
  const variable=state.catalog?.variables.find(v=>v.id===savedTrendState.variable)?.name||savedTrendState.variable;
  const n=rows.length;
  if(savedTrendState.error){note.textContent=`Saved trend colours are unavailable (${savedTrendState.error}). Nothing was downloaded.`;note.dataset.state='error';return;}
  if(!n){
    note.dataset.state='empty';
    note.textContent=`No saved ${variable} result matches ${savedTrendState.start}–${savedTrendState.end}. Coloured areas appear only for completed analyses of this exact measurement and period; nothing has been downloaded.`;
    const alternatives=(savedTrendState.alternatives||[]).filter(a=>a.window).slice(0,4);
    if(alternatives.length){
      const row=document.createElement('span');row.className='saved-window-actions';
      for(const alt of alternatives){
        const areas=(alt.areas||alt.area_names||[]).slice(0,3).join(', ');
        const b=document.createElement('button');b.type='button';b.className='toolbar-button';
        b.textContent=`Show saved ${alt.window.start}–${alt.window.end}`+(areas?` · ${areas}`:'');
        b.onclick=()=>{$('start').value=alt.window.start;$('end').value=alt.window.end;prepareInvestigation(false);loadSavedTrendMap(true);};
        row.append(b);
      }
      note.append(row);
    }
    return;
  }
  note.dataset.state='ok';
  note.textContent=`${n} saved ${variable} area${n===1?'':'s'} shown for ${savedTrendState.start}–${savedTrendState.end}. Read from local stored results; no analysis or observation request was started. Select a coloured area to open its saved evidence.`;
}
function renderGlobeRegions(d) {
  if(!d)return;
  const s=d.series[state.activeVarIdx]||d.series[0];
  if(s.provenance?.provider==='noaa-cdo'){investigation.map?.clearResults();investigation.mapVariable=null;refreshSelection(false);return;}
  if(investigation.mapVariable!==s.variable.id){
    if(investigation.mapVariable)cancelPendingWork();
    investigation.map?.clearResults();investigation.mapVariable=s.variable.id;
  }
  const rows=[{id:d.region.id,overall:s.overall,provenance:s.provenance}];
  if(d.compare){const b=d.compare.series[state.activeVarIdx]||d.compare.series[0];rows.push({id:d.compare.region.id,overall:b.overall,provenance:b.provenance});}
  investigation.map?.setResults(rows);if(investigation.connections.length)investigation.map?.setConnections(investigation.connections);refreshSelection(false);
}
function previewRegionSelection(region) {investigation.map?.setSelections([region?.id,state.compareMode?currentCompareRegion()?.id:null]);}
function applyRegionSelection(region) {refreshSelection(false);}
function wireStartModal() { $('start-modal').hidden=true;$('start-close').onclick=()=>$('start-modal').hidden=true; }
async function initGlobe() {
  try{
    investigation.map=new window.TerraGlobe($('globe'),{onSelect:selectMapFeature,onConnection:showConnectionEvidence,onSelectionPoint:placeSelectionShape,onLasso:previewSelectionLasso,onLassoCount:n=>{$('lasso-point-count').textContent=n+' points';},onSelectionError:message=>selectionToolMessage(message,true),onAutoRotation:active=>{$('mc-rotate').classList.toggle('on',active);$('mc-rotate').setAttribute('aria-pressed',String(active));},onProjection:mode=>{$('proj-readout').textContent=mode==='plane'?'PLANE / MERCATOR':'3D GLOBE';$('mc-style').classList.toggle('on',mode==='plane');}});
  }catch(e){$('globe').innerHTML='<div class="globe-failure">The 3D view needs WebGL. You can still choose areas and analyze them using the Variables drawer.</div>';setStatus('warn','WebGL unavailable; area-list selection remains available.');}
  state.selected=[];renderVarList();refreshVariableStrip();
  $('drawer-toggle').onclick=()=>openDrawer(document.body.dataset.drawer!=='open');$('drawer-close').onclick=()=>openDrawer(false);
  $('k-scan-cta').onclick=()=>{showInvestigationScreen('map');openDrawer(true);};$('card-analysis').onclick=()=>showInvestigationScreen('analysis');$('card-connections').onclick=()=>openInterconnectScreen();
  $('analysis-back').onclick=$('analysis-empty-map').onclick=$('methods-back').onclick=()=>showInvestigationScreen('map');
  document.querySelectorAll('[data-level]').forEach(b=>b.onclick=()=>setGeographicLevel(b.dataset.level));
  $('geography-presets').onclick=togglePresetRegions;
  $('geography-scope').onchange=()=>{if(investigation.level==='preset'){const f=investigation.featureStore.get($('geography-scope').value);if(f)selectMapFeature(f);}else setGeographicLevel(investigation.level,$('geography-scope').value);};
  $('mc-style').onclick=()=>investigation.map?.setProjection(investigation.map?.targetBlend?'globe':'plane');
  $('mc-zoom-in').onclick=()=>investigation.map?.zoomBy(-150);
  $('mc-zoom-out').onclick=()=>investigation.map?.zoomBy(150);
  $('mc-rotate').onclick=()=>{if(investigation.map)investigation.map.setAutoRotation(!investigation.map.auto);};
  $('mc-reset').onclick=()=>investigation.map?.setProjection('globe');
  document.querySelectorAll('[data-kview]').forEach(link=>link.onclick=e=>{e.preventDefault();if(link.dataset.kview==='interconnect')openInterconnectScreen();else showInvestigationScreen(link.dataset.kview==='observatory'?'analysis':link.dataset.kview);});
  for(const id of ['start','end'])$(id).addEventListener('change',()=>prepareInvestigation());
  const changeProvider=event=>{investigation.provider=event.target.value;$('science-provider').value=investigation.provider;$('methods-provider').value=investigation.provider;providerNote();prepareInvestigation();};
  $('science-provider').onchange=changeProvider;$('methods-provider').onchange=changeProvider;
  $('analyze-layer').onclick=analyzeLayer;$('cancel-work').onclick=()=>{prepareInvestigation(false);setStatus('ok','Analysis cancelled.');};
  $('resource-import-form').onsubmit=importChallengeData;
  $('earthdata-connect-form').onsubmit=connectEarthdata;
  $('earthdata-disconnect').onclick=disconnectEarthdata;
  $('appeears-connect-form').onsubmit=connectAppEEARS;
  $('appeears-disconnect').onclick=async()=>{const r=await fetch('/api/data-sources/appeears',{method:'POST',headers:{'Content-Type':'application/json'},body:'{"disconnect":true}'});if(r.ok){await loadProviders();prepareInvestigation();}};
  $('ix-remote-search').onchange=()=>{$('ix-sub').textContent='Search scope changed. Your last result is retained; use Find relationships in the investigation panel to run the updated request.';syncRemoteAction();};
  $('btn-open-interconnect').onclick=()=>openInterconnectScreen({run:true});
  $('ix-run-remote').onclick=runRemoteRelationships;
  $('connect-source-open').onclick=()=>{openDrawer(false);showInvestigationScreen('sources');};
  wireSelectionTools();
  if(typeof wireMapPanels==='function')wireMapPanels();
  const variable=$('import-variable');for(const v of state.catalog.variables){const option=document.createElement('option');option.value=v.id;option.textContent=v.name;variable.append(option);}variable.value='GWETROOT';
  variable.onchange=()=>{$('import-unit').value=state.catalog.variables.find(v=>v.id===variable.value).unit;};variable.onchange();
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){openDrawer(false);closeSelectionTools();}});
  if(await loadProviders()){
    /* Wire the interface FIRST so one failing layer redraw can never leave the
       dates, saved library or tutorial unwired. Most investigations are run for
       countries, so that is the level the app opens on. */
    window.TerraWorkspace?.init?.();
    try{
      await setGeographicLevel('country','');
      refreshSelection(false);
    }catch(error){
      setStatus('warn','The map layer could not finish loading. The investigation controls still work.');
    }
    loadSavedTrendMap(true);
  }
  else{$('coord-readout').textContent='SERVER UPDATE REQUIRED';openDrawer(true);}
}
function sourceReadiness(){
  if(investigation.provider==='nasa-appeears')return investigation.appeears?.configured?{code:'ready',label:'Analyze',message:'AppEEARS connected. NASA will process the polygon; only summary files are returned.'}:{code:'login',label:'Connect AppEEARS',message:'Connect AppEEARS in Data & Methods using its separate NASA sign-in form.'};
  if(investigation.provider==='auto'&&!investigation.providersLoaded)return {code:'checking',label:'Checking sources',message:'Checking automatic data routes.'};
  if(!['nasa-merra2','nasa-giovanni','nasa-hydrology'].includes(investigation.provider))return {code:'ready',message:'',label:'Analyze'};
  if(investigation.provider==='nasa-giovanni'&&!(investigation.providers||[]).some(p=>p.id==='nasa-giovanni'))return {code:'server-update',label:'Set up Giovanni',message:'This running server needs the Giovanni update. Use the updated preview, or restart TerraTrend and reconnect Earthdata.'};
  if(!investigation.nasa){
    if(investigation.providerError)return {code:'unavailable',label:'Check data source',message:investigation.providerError};
    if(!investigation.providersLoaded)return {code:'checking',label:'Checking data…',message:'Checking the NASA data connection.'};
    return {code:'server-update',label:'Set up NASA',message:'Restart the TerraTrend server with ./start.sh 8517, reload this page, then connect Earthdata.'};
  }
  if(!investigation.nasa.reader_installed)return {code:'reader-missing',label:'Set up NASA',message:'Start TerraTrend with ./start.sh 8517 to install its NASA reader, then reload this page.'};
  if(!investigation.nasa.configured)return {code:'login',label:'Connect NASA',message:'Connect Earthdata in Data & Methods once. TerraTrend then downloads observations automatically; no file uploads are needed.'};
  return {code:'ready',label:'Analyze',message:investigation.nasa.remembered?'Earthdata connection restored from private storage. Review data use before requesting NASA observations.':'Earthdata connected. Review data use before downloading NASA observations.'};
}
function sourceVariables(){return (investigation.providers||[]).find(p=>p.id===investigation.provider)?.variables||(investigation.provider==='nasa-merra2'?investigation.nasa?.variables:null);}
function variableSourceAvailable(id){const variables=sourceVariables();return !Array.isArray(variables)||variables.includes(id);}
function isGiovanniRectangle(feature){
  const g=feature?.geometry,ring=g?.type==='Polygon'&&g.coordinates?.length===1?g.coordinates[0]:null;
  if(!ring||ring.length<5)return false;
  const xs=ring.map(p=>p[0]),ys=ring.map(p=>p[1]),west=Math.min(...xs),east=Math.max(...xs),south=Math.min(...ys),north=Math.max(...ys);
  let area=0;for(let i=1;i<ring.length;i++){const a=ring[i-1],b=ring[i];if(Math.abs(a[0]-b[0])>1e-8&&Math.abs(a[1]-b[1])>1e-8)return false;area+=a[0]*b[1]-b[0]*a[1];}
  return east>west&&east-west<=180&&north>south&&Math.abs(Math.abs(area)/2-(east-west)*(north-south))<1e-8;
}
function refreshSourceControls(){
  const readiness=sourceReadiness(),canConnect=['login','ready'].includes(readiness.code)||investigation.provider==='auto';
  $('k-scan-cta').textContent='INVESTIGATE';$('k-scan-cta').title='Edit the areas, measurements and dates in one place';
  $('nasa-restart-help').hidden=!['server-update','reader-missing','unavailable'].includes(readiness.code);
  $('earthdata-token').disabled=!canConnect||investigation.connecting;
  $('earthdata-connect').disabled=!canConnect||investigation.connecting;
  $('earthdata-connect').textContent=investigation.connecting?'CHECKING NASA…':'CONNECT EARTHDATA';
  document.body.dataset.dataReadiness=readiness.code;
}
function ensureSourceReady(){
  const readiness=sourceReadiness();if(readiness.code==='ready')return true;
  closeInterconnectScreen();openDrawer(false);showInvestigationScreen('sources');
  $('earthdata-status').textContent=readiness.message;refreshSourceControls();return false;
}
function providerNote() {
  const selected=$('science-provider').selectedOptions?.[0];$('provider-note').textContent=selected?.dataset.description||'';
  if(investigation.provider==='project-cache')$('provider-note').textContent+=' Coverage is limited to those files. Missing observations cannot establish that an area has no trend.';
  const automatic=['auto','nasa-merra2','nasa-giovanni','nasa-hydrology','nasa-appeears','noaa-cdo','multi-source'].includes(investigation.provider);
  $('active-source-label').textContent=({'auto':'AUTOMATIC','nasa-giovanni':'NASA GIOVANNI','nasa-hydrology':'NASA HYDROLOGY','nasa-appeears':'NASA APPEEARS','noaa-cdo':'NOAA STATIONS','multi-source':'LINKED SOURCES','nasa-merra2':'NASA GES DISC','project-cache':'PROJECT CACHE'})[investigation.provider]||'RESOURCE IMPORT';
  const readiness=sourceReadiness();
  $('data-through').textContent=automatic?({ready:'AUTO FETCH',login:'CONNECT NASA','server-update':'RESTART SERVER','reader-missing':'READER SETUP',checking:'SOURCE CHECK',unavailable:'SOURCE OFFLINE'}[readiness.code]):investigation.provider==='project-cache'?'CACHED':'PER DATASET';
  if(automatic&&readiness.code!=='ready')$('provider-note').textContent=readiness.message;
  $('methods-provider-note').textContent=$('provider-note').textContent;
  refreshSourceControls();renderVarList();refreshVariableStrip();
}
async function loadProviders(preferred=null) {
  try{const response=await fetch('/api/data-sources');if(response.status===404)throw new Error('Restart the TerraTrend server with ./start.sh 8517, then reload this page.');if(!response.ok)throw new Error('The data-source service is unavailable. Check the TerraTrend server and retry.');const data=await response.json();if(!Array.isArray(data.providers))throw new Error('The server returned an invalid data-source list. Restart TerraTrend and reload.');const select=$('science-provider');select.replaceChildren();
    $('methods-provider').replaceChildren();
    for(const p of data.providers){for(const target of [select,$('methods-provider')]){const o=document.createElement('option');o.value=p.id;o.textContent=p.name;o.dataset.description=p.description;target.append(o);}}
    investigation.providers=data.providers;
    investigation.nasa=data.earthdata||null;investigation.providersLoaded=true;investigation.providerError=null;
    investigation.appeears=data.appeears||null;
    $('appeears-status').textContent=data.appeears?.configured?'AppEEARS connected'+(data.appeears.remembered?' and remembered on this computer.':'.')+' NASA may expire its separate service token.':'Connect AppEEARS below to request monthly vegetation summaries.';
    $('appeears-disconnect').hidden=!data.appeears?.configured;
    if(typeof data.earthdata?.remembered==='boolean'&&data.earthdata.configured)$('earthdata-remember').checked=data.earthdata.remembered;
    const candidate=preferred||investigation.provider;
    const wanted=data.providers.some(p=>p.id===candidate)?candidate:'nasa-merra2';
    // An older server is a setup state, not consent to switch to sparse data.
    if(!data.providers.some(p=>p.id==='nasa-merra2')){const option=document.createElement('option');option.value='nasa-merra2';option.textContent='NASA automatic · restart server';option.dataset.description='Restart TerraTrend to enable automatic NASA data.';select.append(option);}
    select.value=wanted;$('methods-provider').value=wanted;investigation.provider=wanted;
    $('earthdata-status').textContent=sourceReadiness().message;
    $('earthdata-disconnect').hidden=!data.earthdata?.configured;
    providerNote();return true;
  }catch(e){investigation.providerError=e.message;setStatus('err',esc(e.message));$('earthdata-status').textContent=e.message;providerNote();return false;}
}
async function connectAppEEARS(event){
  event.preventDefault();const button=$('appeears-connect');button.disabled=true;$('appeears-status').textContent='Connecting directly to NASA AppEEARS…';
  try{
    const response=await fetch('/api/data-sources/appeears',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('appeears-username').value,password:$('appeears-password').value,remember:$('appeears-remember').checked})});
    const data=await response.json();if(!response.ok)throw new Error(data.error||'AppEEARS connection failed');
    await loadProviders();prepareInvestigation(false);
  }catch(e){$('appeears-status').textContent=e.message;}finally{$('appeears-password').value='';button.disabled=false;}
}
async function connectEarthdata(event){
  event.preventDefault();if(!['login','ready'].includes(sourceReadiness().code)){ensureSourceReady();return;}
  investigation.connecting=true;refreshSourceControls();
  $('earthdata-status').textContent='Checking NASA authorization and reading a one-cell observation…';
  try{
    const response=await fetch('/api/data-sources/earthdata',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:$('earthdata-token').value,remember:$('earthdata-remember')?.checked!==false})});
    const data=await response.json();if(!response.ok)throw new Error(response.status===404?'Restart TerraTrend with ./start.sh to enable automatic downloads.':data.error||'NASA connection failed');
    if(!await loadProviders(investigation.provider))throw new Error('NASA accepted the token, but the server connection status could not be refreshed. Reload and check Data & Methods.');prepareInvestigation();$('earthdata-status').textContent=investigation.nasa?.remembered?'NASA connected and remembered on this computer. TerraTrend will restore it after a restart; NASA may still expire or revoke the token.':'Earthdata connection verified with a real observation. Giovanni authorization is checked separately when its processing request runs.';
  }catch(e){$('earthdata-status').textContent=e.message;}finally{$('earthdata-token').value='';investigation.connecting=false;refreshSourceControls();}
}
async function disconnectEarthdata(){
  try{const response=await fetch('/api/data-sources/earthdata',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({disconnect:true})}),data=await response.json();if(!response.ok)throw new Error(data.error||'Could not disconnect');prepareInvestigation();await loadProviders();if(data.configured)$('earthdata-status').textContent='Session token removed. EARTHDATA_TOKEN is still configured in the server environment.';}
  catch(e){$('earthdata-status').textContent=e.message;}
}
async function importChallengeData(event) {
  event.preventDefault();const form=event.currentTarget,button=form.querySelector('button[type=submit]');button.disabled=true;
  try{const data=new FormData(form),file=data.get('file');if(file.size>25_000_000)throw new Error('Choose a CSV smaller than 25 MB');
    $('import-status').textContent='Validating monthly grid records…';
    const payload=Object.fromEntries([...data.entries()].filter(([k])=>k!=='file'));payload.csv=await file.text();
    const response=await fetch('/api/data-sources/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),result=await response.json();if(!response.ok)throw new Error(result.error);
    await loadProviders(result.id);state.selected=[payload.variable];renderVarList();prepareInvestigation();$('import-status').textContent=`Imported ${result.records.toLocaleString()} monthly records across ${result.cells.toLocaleString()} cells. Ready for analysis.`;
  }catch(e){$('import-status').textContent=e.message;}finally{button.disabled=false;}
}
function jobSpec(operation, options={}) {
  const region=currentRegion();if(!region)throw new Error('Choose an area first');
  const discovery=operation==='scan';
  /* Comparison is included ONLY when this operation is explicitly a comparison.
     options.compare === true  -> a real B is required by the caller
     options.compare === false -> never include B (an A-only request)
     options.compare undefined -> include B only when comparison is genuinely active */
  let compareArea=null;
  if(!discovery&&operation!=='interconnections'){
    const b=validComparisonArea();
    if(options.compare===true){if(!b)throw new Error('Choose a different comparison area B before comparing two places.');compareArea=b;}
    else if(options.compare===false)compareArea=null;
    else compareArea=comparisonActive()?b:null;
  }
  if(!discovery&&!state.selected.length)throw new Error('Choose a variable for this action, or use Analyze without variables to discover trends.');
  const variables=discovery?state.catalog.variables.filter(v=>variableSourceAvailable(v.id)).map(v=>v.id):['overview','interconnections'].includes(operation)?[state.selected[state.activeVarIdx]||state.selected[0]]:state.selected.slice();
  if(['nasa-merra2','nasa-giovanni'].includes(investigation.provider)){
    const readiness=sourceReadiness();if(readiness.code!=='ready')throw new Error(readiness.message);
    if(['analyze','overview','interconnections'].includes(operation)){const unavailable=variables.filter(id=>!variableSourceAvailable(id));if(unavailable.length)throw new Error('Automatic source mapping is still needed for: '+unavailable.map(id=>state.catalog.variables.find(v=>v.id===id)?.name||id).join(', ')+'. See the supported measurements in Data & Methods.');}
  }
  if(investigation.provider==='nasa-giovanni'){
    if(operation==='overview'&&investigation.level!=='preset')throw new Error('Choose the preset rectangles for a Giovanni layer request; geographic boundary layers need native mode.');
    if(operation==='interconnections'&&$('ix-remote-search')?.checked)throw new Error('Giovanni supports local rectangle relationships; remote country searches need native mode.');
    const areas=operation==='overview'?investigation.features:[region,...(compareArea?[compareArea]:[])];
    if(areas.some(a=>!isGiovanniRectangle(a.geometry?a:investigation.featureStore.get(a?.id))))throw new Error('Giovanni needs a latitude/longitude rectangle for each area. Use presets, Lat / Lon bounds or an axis-aligned rectangular lasso; choose native mode for countries, circles and other exact boundaries.');
  }
  const spec={operation,region:region.id,variables,start:+$('start').value,end:+$('end').value,provider:investigation.provider};
  if(operation==='interconnections'){
    if(['auto','multi-source'].includes(investigation.provider)&&state.selected.length<2)throw new Error('Select two or three measurements to link, such as soil moisture and vegetation greenness.');
    spec.relationship_variables=state.selected.length>=2?state.selected.slice():state.catalog.variables.filter(v=>variableSourceAvailable(v.id)).map(v=>v.id);
    spec.relationship_scope=$('ix-remote-search')?.checked===true?'remote':'local';
    if(spec.relationship_scope==='remote'){const b=validComparisonArea();if(!state.compareMode||!b||b.id===region.id)throw new Error('Choose a different comparison area B to test remote relationships.');spec.target_regions=[b.id];}
  }
  if(compareArea)spec.compare_region=compareArea.id;
  const custom=[region,compareArea].filter(f=>f?.level==='custom').map(f=>investigation.featureStore.get(f.id));
  if(custom.length){if(!state.catalog.custom_selections)throw new Error('Restart the TerraTrend Python server to analyze custom areas. Your selections are ready.');spec.custom_areas=custom;}
  return spec;
}
async function runInvestigationJob(spec,title) {
  const identity=investigationKey(),seq=++investigation.seq;
  if(investigation.job){const previous=investigation.job;investigation.job=null;await fetch(`/api/jobs/${previous}/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).catch(()=>{});}
  if(seq!==investigation.seq||identity!==investigationKey())return null;
  const requestKey=JSON.stringify(spec);
  if(investigation.completedJobs.has(requestKey)){setStatus('ok','Reusing completed observations and results.');return investigation.completedJobs.get(requestKey);}
  if(spec.provider==='auto'){
    const reply=await fetch('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(spec)}),plan=await reply.json();
    if(!reply.ok)throw new Error(plan.error||'Cannot check this selection.');
    if(seq!==investigation.seq||identity!==investigationKey())return null;
    if(plan.issues?.length){window.TerraWorkspace?.showIssues?.(plan.issues);throw new Error('Update the selection using the guidance above. No observations were requested.');}
    spec.routing=plan;if(spec.operation==='scan')spec.variables=plan.variables;
    const routes=Object.values(plan.routes).flatMap(r=>Object.values(r));
    if(routes.some(r=>['nasa-merra2','nasa-giovanni','nasa-hydrology'].includes(r))&&!investigation.nasa?.configured){window.TerraWorkspace?.showIssues?.([{message:'Connect NASA once in Data & Methods to request these measurements.',action:'connect'}]);throw new Error('NASA connection required. Your investigation is saved.');}
    if(routes.includes('nasa-appeears')&&!investigation.appeears?.configured){window.TerraWorkspace?.showIssues?.([{message:'Connect AppEEARS in Data & Methods to request vegetation measurements.',action:'connect'}]);throw new Error('AppEEARS connection required. Your investigation is saved.');}
  }
  if(!window.TerraDataReview)throw new Error('Reload TerraTrend to load its data-use review.');
  const approved=await window.TerraDataReview.review(spec,state.catalog,sourceVariables()||[]);
  if(seq!==investigation.seq||identity!==investigationKey())return null;
  if(!approved){setStatus('ok','This request was not started.');return null;}
  setStatus('busy',title);window.TerraTour?.setBusy?.(true,title);
  $('work-progress').hidden=false;$('work-progress-title').textContent=title;$('work-progress-detail').textContent='Preparing available scientific data';
  const response=await fetch('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(spec)});let job=await response.json();if(!response.ok)throw new Error(job.error||'Could not start analysis');
  if(seq!==investigation.seq||identity!==investigationKey()){
    fetch(`/api/jobs/${job.id}/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).catch(()=>{});return null;
  }
  investigation.job=job.id;
  while(job.status!=='complete'){
    if(seq!==investigation.seq||identity!==investigationKey())return null;
    if(job.status==='failed'||job.status==='cancelled')throw new Error(job.error||job.message);
    $('work-progress-detail').textContent=job.message+(job.total?` · ${job.completed}/${job.total}`:'');
    await new Promise(resolve=>setTimeout(resolve,650));
    const poll=await fetch(`/api/jobs/${job.id}`);job=await poll.json();if(!poll.ok)throw new Error(job.error||'Could not read analysis progress');
  }
  if(seq!==investigation.seq||identity!==investigationKey())return null;
  investigation.job=null;$('work-progress').hidden=true;window.TerraTour?.setBusy?.(false);investigation.completedJobs.set(requestKey,job.result);
  while(investigation.completedJobs.size>12)investigation.completedJobs.delete(investigation.completedJobs.keys().next().value);
  return job.result;
}
async function analyze() {
  if(!ensureSourceReady())return;
  /* The label and the submitted request come from the same resolved action:
     "Analyze Area A" can never demand or silently include area B. */
  const action=resolveRunAction();
  if(action.kind==='blocked'){setStatus('warn',esc(action.reason));return;}
  if(action.kind==='need-b')return requireComparisonArea();
  if(action.kind==='discover')return scanAll();
  const call=++investigation.analysisCall;
  try{const spec=jobSpec('analyze',{compare:action.kind==='compare'});$('run').disabled=true;$('k-scan-cta').disabled=true;setStatus('ok','Review the data request before starting.');
    announceAction('run-clicked',{kind:action.kind,compare:action.kind==='compare'});
    const title=action.kind==='compare'?`Comparing ${action.areaA.name} and ${action.areaB.name}`:'Analyzing '+action.areaA.name;
    const result=await runInvestigationJob(spec,title);if(!result)return;
    const active=state.selected[state.activeVarIdx];state.result=result;state.activeVarIdx=Math.max(0,result.series.findIndex(s=>s.variable.id===active));investigation.resultKey=investigationContextKey();window.TerraWorkspace?.saveResult?.(result);render();window.TerraWorkspace?.refresh?.();announceVerdict(result);setStatus('ok','');openDrawer(false);
    announceAction('analysis-complete',{kind:result.compare?'compare':'analysis',resultId:window.TerraWorkspace?.lastSavedId||null});
  }catch(e){if(call===investigation.analysisCall){setStatus('err',esc(e.message));$('work-progress').hidden=true;openDrawer(true);}}finally{if(call===investigation.analysisCall){$('run').disabled=false;$('k-scan-cta').disabled=false;}}
}
/* ---------------------------------------------------------------------------
   Plain-English verdict. A first-time reader should be able to answer "is it
   getting hotter or not?" without knowing what Mann, Kendall, Sen or a p-value
   are. The statistical detail stays available behind "Show the statistics".
   --------------------------------------------------------------------------- */
const WARMING_FIELDS=new Set(['T2M','T2M_MAX','T2M_MIN','TS','T10M','GLDAS_SOILT','STATION_TAVG','STATION_TMAX','STATION_TMIN']);
function plainVerdict(d,s,o){
  const start=Number(d.start),end=Number(d.end),years=end-start;
  const period=`${d.start}–${d.end}`;
  const area=d.compare?`${d.region.name} and ${d.compare.region.name}`:d.region.name;
  const variable=s.variable.name,unit=s.variable.unit;
  const warming=WARMING_FIELDS.has(s.variable.id);
  if(!o.ok){
    return {headline:'Not enough data to tell',
      detail:`${variable} over ${area} could not be tested for ${period}.`,
      explain:'Too many months are missing for a trend test, so no trend is reported. That is not the same as “no change”.'};
  }
  const total=o.per_decade/10*years;
  const round=v=>Math.abs(v)<0.05?v.toFixed(3):Math.abs(v)<1?v.toFixed(2):v.toFixed(1);
  const sign=total>0?'+':'';
  const direction=o.significant?(o.direction==='falling'?'cooler':'warmer'):null;
  const headline=!o.significant
    ? `No clear ${warming?'warming or cooling':'change'} trend`
    : warming
      ? (o.direction==='falling'?'Getting cooler overall':'Getting warmer overall')
      : (o.direction==='falling'?'A clear decrease':'A clear increase');
  const movement=`about ${sign}${round(total)} ${unit} in total over ${years} years (roughly ${sign}${round(o.per_decade)} ${unit} every ten years)`;
  const detail=o.significant
    ? `${variable} over ${area} ${total>=0?'rose':'fell'} by ${movement}.`
    : `${variable} over ${area} changed by ${movement}.`;
  const explain=o.significant
    ? 'The change is larger than the year-to-year ups and downs in these data, so it is unlikely to be chance. That does not tell us what caused it.'
    : 'A change this size is within the normal year-to-year ups and downs of these data, so we cannot say the region is clearly changing. The small difference above is an estimate, not a proven shift.';
  return {headline,detail,explain,period,area,variable,unit,total};
}
function renderPlainVerdict(d,s,o){
  const card=$('plain-verdict');if(!card)return;
  card.hidden=false;
  const v=plainVerdict(d,s,o);
  $('pv-region').textContent=`${d.compare?`${d.region.name} + ${d.compare.region.name}`:d.region.name} · ${v.period||`${d.start}–${d.end}`} · ${s.variable.name}`;
  $('pv-headline').textContent=v.headline;
  $('pv-detail').textContent=v.detail;
  $('pv-explain').textContent=v.explain;
  /* Where inside the region? A plain sentence plus the existing cell view. */
  let where=$('pv-where');
  if(!where){
    where=document.createElement('p');where.id='pv-where';where.className='pv-where';
    $('toggle-tech').before(where);
  }
  const summary=s.summary||{};
  if(Number.isFinite(summary.significant_cells)&&Number.isFinite(summary.total_cells)&&summary.total_cells){
    where.hidden=false;
    where.textContent=`Inside ${d.region.name} the evidence is not uniform: ${summary.significant_cells.toLocaleString()} of ${summary.total_cells.toLocaleString()} source cells showed a clear change. `;
    const b=document.createElement('button');b.type='button';b.className='link-btn';b.id='pv-show-where';
    b.textContent='Show where';
    b.onclick=()=>{if(typeof openDataModal==='function')openDataModal(state.activeVarIdx);};
    where.append(b);
  }else{
    where.textContent = summary.spatial_detail_available===false
      ? 'This source reports a single value for the whole region, so there is no inside-the-region grid to show.'
      : '';
    where.hidden = !where.textContent;
  }
  const stats=$('pv-stats');
  if(stats){
    const p=o.p!=null?o.p:o.p_value;
    const lo=o.ci_low_per_decade!=null?o.ci_low_per_decade:o.ci_low;
    const hi=o.ci_high_per_decade!=null?o.ci_high_per_decade:o.ci_high;
    const f=v=>Number(v).toFixed(3);
    stats.textContent=[
      `Estimated change: ${o.ok?`${o.per_decade>0?'+':''}${f(o.per_decade)} ${s.variable.unit} every ten years`:'not calculated'}`,
      `Test used: ${o.method||'Mann–Kendall with a Theil–Sen slope'}`,
      o.ok&&p!=null?`p-value: ${p<0.001?'<0.001':p.toFixed(3)} — the chance of seeing a trend this strong if nothing were really changing. Below 0.05 counts as statistically significant.`:'',
      o.ok&&lo!=null&&hi!=null?`95% plausible range: ${f(lo)} to ${f(hi)} ${s.variable.unit} per decade. Because it includes 0, a “no clear trend” reading is the honest one.`:'',
      'In plain terms: Mann–Kendall asks whether a trend is detectable at all; Theil–Sen estimates how big it is. Both are standard climate-science methods.',
    ].filter(Boolean).join('\n');
  }
}
function render() {
  oldRender();const d=state.result;if(!d)return;const s=d.series[state.activeVarIdx]||d.series[0],o=s.overall,p=s.provenance||{};
  $('analysis-empty').hidden=true;$('analysis-context').textContent=`${d.region.name.toUpperCase()} · ${d.start}–${d.end}`;
  $('analysis-page-description').textContent=[s.variable.name,p.source,p.aggregation].filter(Boolean).join(' · ');
  renderPlainVerdict(d,s,o);
  const v=plainVerdict(d,s,o);
  $('krc-value').textContent=o.ok?`${v.total>0?'+':''}${Math.abs(v.total)<0.05?v.total.toFixed(3):v.total.toFixed(2)}`:'—';
  $('krc-unit').textContent=o.ok?`${s.variable.unit} in total, ${d.start}–${d.end}`:'not enough data';
  if(d.compare){const other=d.compare.series[state.activeVarIdx]||d.compare.series[0];$('krc-unit').textContent=(o.ok?'A / ':'')+$('krc-unit').textContent;$('compare-selection-summary').textContent=`B / ${d.compare.region.name}\n${other.overall.ok?(other.overall.per_decade>0?'+':'')+num(other.overall.per_decade,2)+' '+other.variable.unit+' / decade':'Insufficient data'}`;}
  $('krc-verdict').textContent=!o.ok?'INSUFFICIENT DATA':o.significant?o.direction.toUpperCase():'NO SIGNIFICANT TREND';
  $('selection-coverage').textContent=p.spatial_detail_available===false?`${p.resource||'Regional source'} summary · per-cell and monthly area coverage not supplied`:Number.isFinite(p.available_area_fraction)?`${Math.round(p.available_area_fraction*100)}% area has data · ${p.available_cells} native cells`+(p.policy==='legacy_unverified'?' · legacy cache route unverified':''):'See analysis for coverage and sources.';
  if(p.cache_hit)$('selection-coverage').textContent+=' · cached observations reused';
  else if(p.cached_subsets)$('selection-coverage').textContent+=` · ${p.cached_subsets} monthly subsets reused`;
  if(!o.ok)$('selection-coverage').textContent+=p.provider==='nasa-merra2'?' · Check the observed dates and valid monthly coverage in Analysis.':' · Check data coverage or connect the automatic NASA source in Data & Methods.';
  if(p.provider==='nasa-merra2'&&p.last_observed_month){const value=String(p.last_observed_month);$('data-through').textContent=value.slice(0,4)+'-'+value.slice(4);}
  $('krc-surface').textContent=d.region.level||'FOCUS AREA';
}
function renderSatellite(d) {
  if(d.satellite?.enabled===false){$('sat-summary').innerHTML='<p class="micro">Satellite evidence is preserved as an optional tool. Its imagery route must be verified against the allowed resources before use.</p>';$('sat-tag').textContent='SOURCE POLICY';return;}
  oldRenderSatellite(d);
}
function drawChart() {
  if(chart){chart.destroy();chart=null;}
  const d=state.result;if(!d)return;
  const index=state.activeVarIdx,s=d.series[index]||d.series[0],yearly=state.mode==='yearly';
  const comparing=!!(d.compare&&d.compare.series);
  const datasets=[],keyRows=[];
  /* Each area keeps its OWN colour for both the observed line and its fitted
     trend; direction is carried by the labels and the statistics, never by
     repainting a series. Observed is solid, the fitted trend is dashed with a
     per-area dash so the two also differ without colour. */
  function add(block,side,regionName,color,dash){
    if(!block)return;
    const points=yearly?block.yearly_timeseries.filter(p=>p.complete).map(p=>({x:p.year,y:p.value})):
      block.monthly_timeseries.map(p=>{const [y,m]=p.month.split('-').map(Number);return {x:y+(m-1)/12,y:p.value};});
    const areaName=`${side} / ${regionName} · ${block.variable.name}`;
    datasets.push({label:areaName,data:points,borderColor:color,backgroundColor:color,trendModel:block.overall,calendarStart:null,$side:side.toLowerCase(),$kind:'observed',$areaName:areaName,$unit:block.variable.unit,borderWidth:2.2,pointRadius:yearly?3:0,pointHoverRadius:5,tension:.12,spanGaps:false});
    keyRows.push({text:`${areaName} — observed (solid)`,color,dashed:false});
    if(block.overall.ok&&points.length){const o=block.overall;
      datasets.push({label:`${side} / ${regionName} · fitted trend`,data:[points[0],points[points.length-1]].map(p=>({x:p.x,y:o.intercept+o.slope*p.x})),borderColor:color,borderDash:dash,borderWidth:1.8,pointRadius:0,$side:side.toLowerCase(),$kind:'trend',$areaName:`${side} / ${regionName}`,$unit:block.variable.unit});
      keyRows.push({text:`${side} / ${regionName} — fitted trend (dashed)`,color,dashed:true});
    }
    if(yearly){const partial=block.yearly_timeseries.filter(p=>!p.complete).map(p=>({x:p.year,y:p.value}));if(partial.length){datasets.push({label:`${side} / ${regionName} · incomplete year (excluded from trend)`,data:partial,showLine:false,pointStyle:'rectRot',pointRadius:5,backgroundColor:color,borderColor:color,$side:side.toLowerCase(),$kind:'partial',$areaName:`${side} / ${regionName}`,$unit:block.variable.unit});keyRows.push({text:`${side} / ${regionName} — incomplete year (excluded)`,color,dashed:false});}}
  }
  add(s,'A',d.region.name,comparing?'#68b8ff':(s.variable.color||'#68b8ff'),[7,4]);
  if(comparing)add(d.compare.series[index]||d.compare.series[0],'B',d.compare.region.name,'#e9c77a',[2,3]);
  chart=new Chart($('chart').getContext('2d'),{type:'line',data:{datasets},options:{responsive:true,maintainAspectRatio:false,parsing:false,animation:false,interaction:{mode:'nearest',intersect:false},
    plugins:{legend:{display:!!d.compare,labels:{color:'#c2dccb',font:{family:'Inter, system-ui, sans-serif',size:12},boxWidth:14}},
      tooltip:{backgroundColor:'rgba(8,18,13,.97)',borderColor:'#5c7c66',borderWidth:1,titleColor:'#e6f4ea',bodyColor:'#d3e8da',titleFont:{family:'Inter, system-ui, sans-serif',size:13,weight:'600'},bodyFont:{family:'Inter, system-ui, sans-serif',size:13},callbacks:{label:ctx=>trendTooltip(ctx,s.variable.unit),labelTextColor:()=>'#d3e8da'}}},
    scales:{x:{type:'linear',grid:{color:'#284232'},ticks:{color:'#bfe0c9',font:{family:'Inter, system-ui, sans-serif',size:12},precision:0,maxTicksLimit:7,callback:x=>Number(x).toFixed(0)}},
      y:{grid:{color:'#284232'},ticks:{color:'#c2dccb',font:{family:'Inter, system-ui, sans-serif',size:12}},title:{display:true,text:s.variable.unit,color:'#bfe0c9',font:{size:13}}}}}});
  if(typeof chartSeriesKey==='function')chartSeriesKey(keyRows,$('chart-series-key'));
}
function renderDataModal() {
  if(!state.result)return;
  const s=state.result.series[state.expandedVarIdx]||state.result.series[0],cells=s.cells;
  if(cells.length>400){const stride=Math.ceil(cells.length/400);s.cells=cells.filter((_,i)=>i%stride===0);}
  try{oldRenderDataModal();}finally{s.cells=cells;}
  $('data-modal-sub').textContent=`${state.result.start}–${state.result.end} · ${s.summary.total_cells} NATIVE CELLS · ${s.provenance?.source||s.variable.mission} · α = 0.05`;
  $('eg-cell-count').textContent=cells.length>400?`SPATIAL EXCERPT / ${Math.ceil(cells.length/Math.ceil(cells.length/400))} OF ${cells.length} CELLS`:`${cells.length} NATIVE CELLS`;
}
async function analyzeLayer() {
  if(!ensureSourceReady())return;
  try{const spec=jobSpec('overview');delete spec.compare_region;spec.features=investigation.features.map(f=>f.id);if(!spec.features.length)throw new Error('No areas in this layer');
    const result=await runInvestigationJob(spec,'Analyzing geographic layer');if(result){if(investigation.mapVariable!==spec.variables[0])investigation.map?.clearResults();investigation.mapVariable=spec.variables[0];investigation.map?.setResults(result.rows);setStatus('ok',`Layer complete: ${result.rows.filter(r=>r.overall.ok).length}/${result.rows.length} areas have sufficient data.`);}
  }catch(e){$('work-progress').hidden=true;setStatus('err',esc(e.message));openDrawer(true);}
}
async function scanAll() {
  if(!ensureSourceReady())return;
  const call=++investigation.analysisCall;
  try{$('scan').disabled=true;$('run').disabled=true;$('k-scan-cta').disabled=true;const result=await runInvestigationJob(jobSpec('scan'),'Discovering variable trends');if(!result)return;
    $('scan-title').textContent=`${result.region.name} · ${result.start}–${result.end}`;$('scan-sub').textContent='AVAILABLE VARIABLE EVIDENCE';renderScan(result.scanned,result.scanned.length);showModal($('scan-modal'));
    setStatus('ok','Discovery complete. Choose a measurement to inspect its graph.');
  }catch(e){if(call===investigation.analysisCall){$('work-progress').hidden=true;setStatus('err',esc(e.message));}}finally{if(call===investigation.analysisCall){$('scan').disabled=false;$('run').disabled=false;$('k-scan-cta').disabled=false;}}
}
function openFromScan(vid) {
  hideModal($('scan-modal'));state.selected=[vid];state.activeVarIdx=0;state.preferredVar=vid;
  prepareInvestigation(false);renderVarList();showInvestigationScreen('analysis');analyze();
}
async function loadInterconnectData(reg,vId) {
  if(!ensureSourceReady())return;
  let spec;
  try{spec=jobSpec('interconnections');}catch(e){$('ix-pair-list').textContent=e.message;$('ix-global-list').textContent='No data request was submitted.';setStatus('err',esc(e.message));return;}
  spec.variables=[vId];delete spec.compare_region;
  if(spec.relationship_scope==='local')$('ix-global-list').textContent='Remote search is off. Only the selected area and measurements will be tested.';
  // A bounded, disclosed remote search. It does not claim global exhaustiveness.
  // Remote screening is limited to the explicitly chosen comparison area B.
  let data;
  try{data=await runInvestigationJob(spec,'Investigating candidate relationships');}catch(e){$('work-progress').hidden=true;setStatus('err',esc(e.message));$('ix-pair-list').innerHTML=`<p class="micro">${esc(e.message)}</p>`;$('ix-global-list').innerHTML='<p class="micro">No relationship result is available for this request.</p>';}
  if(!data)return;
  ixState.local=data.local;ixState.global=data.global;ixState.anomaly=data.global?.source||null;
  ixState.recordId=data.saved_record_id||null;
  $('ix-sub').textContent=`Candidate drivers and responses for ${reg.name}. Connections are statistical evidence, not established physical causes.`;
  $('ix-method').textContent='Seasonal/trend anomalies · lag-family correction · full-family FDR · conditional checks where data exist';
  renderIxHero(data.local,data.global);renderIxLocal(data.local,vId);renderIxGlobal(data.global,vId);renderIxAnomaly(data.global||{source:data.local?.source_anomaly});
  for(const [id,message] of Object.entries(data.local?.source_errors||{})){const p=document.createElement('p');p.className='micro';p.textContent=`${state.catalog.variables.find(v=>v.id===id)?.name||id}: ${message}`;$('ix-pair-list').append(p);}
  if(Object.keys(data.local?.provenance||{}).length){const p=document.createElement('p');p.className='micro';p.textContent=Object.entries(data.local.provenance).map(([id,v])=>`${state.catalog.variables.find(x=>x.id===id)?.name||id} — ${v.source}; ${v.aggregation}; ${v.quality}`).join(' | ');$('ix-pair-list').append(p);}
  if(data.scope==='local')$('ix-global-list').innerHTML='<p class="micro">Remote search was not requested. This result checks only the selected area and measurements. Enable “Include remote areas” and Recompute to review a larger data request.</p>';
  const model=data.local?.conditional_drivers;
  if(model){
    const card=document.createElement('article');card.className='relationship-card';
    const heading=document.createElement('strong');heading.textContent='EXPLORATORY JOINT DRIVER SCREEN';card.append(heading);
    const note=document.createElement('p');note.className='micro';note.textContent=model.ok?`${model.n} common months · in-sample R² ${model.r_squared.toFixed(2)}. Candidate-selected conditional prediction; this is not a physical attribution.`:model.reason;card.append(note);
    for(const row of model.drivers||[]){const p=document.createElement('p'),name=state.catalog.variables.find(v=>v.id===row.id)?.name||row.id;p.textContent=`${name} · lag ${row.lag_months} mo · standardized coefficient ${row.standardized_coefficient.toFixed(2)} · adjusted p ${row.p_adjusted.toPrecision(3)}`;card.append(p);}
    $('ix-pair-list').append(card);
  }
  investigation.connections=data.global?.teleconnections||[];investigation.map?.setConnections(investigation.connections);
  investigation.remoteTask={regionId:reg.id,regionName:reg.name,variableId:vId,fields:spec.relationship_variables.slice(),start:spec.start,end:spec.end,provider:spec.provider,scope:data.scope||'local'};
  syncRemoteAction();window.TerraWorkspace?.refresh?.();setStatus('ok','Relationship analysis complete.');
}
async function traceGlobalImpacts() {await openInterconnectScreen();}
function render3DTeleconArcs(data) {investigation.map?.setConnections(data?.teleconnections||[]);}
function showConnectionEvidence(connection) {
  if(connection.event_edge)return window.TerraEvents?.focusEdge?.(connection.event_edge);
  window.TerraWorkspace?.pinConnection?.(connection);
}
function renderIxGlobal(global,vId) {
  const list=$('ix-global-list');list.replaceChildren();
  if(!global){list.innerHTML='<p class="micro">No remote analysis is available for this investigation.</p>';return;}
  const summary=document.createElement('p');summary.className='micro';summary.textContent=`${global.summary.valid_tests||0} valid tests across ${global.summary.geographic_coverage?.length||0} screened areas. No connection is drawn without a surviving statistical result.`;list.append(summary);
  const links=global.teleconnections||[];
  if(!links.length){const empty=document.createElement('div');empty.className='relationship-empty';empty.textContent=global.summary.valid_tests?'No remote relationship passed the evidence checks for the available data. This does not establish that the area has no physical connections.':'There were not enough overlapping observations to test remote relationships. This is insufficient data, rather than a finding that no relationships exist.';list.append(empty);return;}
  for(const relationship of ['driver','response','simultaneous']){
    const group=links.filter(c=>c.relationship===relationship);if(!group.length)continue;
    const heading=document.createElement('h3');heading.textContent=relationship==='driver'?'CANDIDATE INCOMING DRIVERS':relationship==='response'?'ASSOCIATED DOWNSTREAM RESPONSES':'NO CLEAR LEAD';list.append(heading);
    for(const c of group){const card=document.createElement('article');card.className='relationship-card';const title=document.createElement('strong');title.textContent=`${c.target_region.name} / ${c.target_variable.name}`;const evidence=document.createElement('p');evidence.textContent=`Relationship strength ${c.r>=0?'+':''}${c.r.toFixed(2)} on a −1 to +1 scale (unitless, not a change in ${c.target_variable.unit}) · ${c.direction==='inverse'?'moving oppositely':'moving together'} · ${c.lead_note} · adjusted significance ${((c.p_adjusted??c.p)<.001?'<0.001':(c.p_adjusted??c.p).toPrecision(3))}`;const note=document.createElement('p');note.className='micro';note.textContent=c.mechanism+' Significance is evidence against a no-association model; it is not importance, danger or causation.';const action=document.createElement('button');action.className='toolbar-button';action.type='button';action.textContent='SHOW ON MAP ↗';action.onclick=()=>{closeInterconnectScreen();showInvestigationScreen('map');investigation.map?.setConnections(investigation.connections.length?investigation.connections:[c]);window.TerraWorkspace?.pinConnection?.(c);window.TerraWorkspace?.refreshConnections?.();};card.append(title,evidence,note,action);list.append(card);}
  }
}

function trendTooltip(ctx,unit) {
  const value=`${ctx.dataset.label}: ${num(ctx.parsed.y,3)} ${unit}`,o=ctx.dataset.trendModel;
  if(!o?.ok||!Number.isFinite(ctx.parsed.y))return value;
  const x=ctx.dataset.calendarStart==null?ctx.parsed.x:ctx.dataset.calendarStart+ctx.parsed.x/12;
  const fit=o.intercept+o.slope*x,delta=ctx.parsed.y-fit;
  return [value,`Trend: ${num(fit,3)} ${unit}`,`${delta>=0?'+':'−'}${num(Math.abs(delta),3)} ${unit} ${delta>=0?'above':'below'} trend`];
}
/* ---------------------------------------------------------------------------
   Remote relationships straight from the Interconnections page.
   The request is built from the COMPLETED local investigation stored in
   investigation.remoteTask, never from unrelated unsaved form values, and it
   goes through the same preflight, data-use review, progress, cancellation,
   caching and job runner as every other request.
   --------------------------------------------------------------------------- */
function remoteTask(){
  const task=investigation.remoteTask;
  if(!task||!task.regionId)return null;
  const edits=[];
  if(currentRegion()?.id&&currentRegion().id!==task.regionId)edits.push('area A has been edited');
  if(state.selected.length&&state.selected[state.activeVarIdx]&&state.selected[state.activeVarIdx]!==task.variableId)edits.push('the focus measurement has been edited');
  if($('start').value!=String(task.start)||$('end').value!=String(task.end))edits.push('the dates have been edited');
  return {...task,edits};
}
function syncRemoteAction(){
  const run=$('ix-run-remote'),ctx=$('ix-remote-context');
  if(!run||!ctx)return;
  const task=remoteTask(),b=validComparisonArea();
  const localOnly=!!ixState.local&&!ixState.global&&!ixState.loading;
  const show=!!task&&localOnly;
  run.hidden=!show;ctx.hidden=!show;
  if(!show)return;
  const fields=(task.fields||[]).map(id=>state.catalog?.variables.find(v=>v.id===id)?.name||id).join(', ');
  const names2=task.fields?.length?fields:task.variableId;
  if(b){
    run.textContent='RUN REMOTE RELATIONSHIPS';
    run.title=`Test the saved local investigation against ${b.name} only`;
    ctx.textContent=`Remote search was not requested. Local evidence: ${task.regionName} · ${names2} · ${task.start}–${task.end}. The intended remote area is ${b.name}; only that area and ${task.fields.length} selected measurement${task.fields.length===1?'':'s'} will be requested.`+(task.edits.length?` Not yet calculated: ${task.edits.join(', ')}.`:'');
  }else{
    run.textContent='CHOOSE COMPARISON AREA B';
    run.title='Choose the single area to screen remotely; local results are kept';
    ctx.textContent=`Remote search was not requested. Local evidence: ${task.regionName} · ${names2} · ${task.start}–${task.end}. Choose one comparison area B to screen remotely; your local results stay available.`+(task.edits.length?` Not yet calculated: ${task.edits.join(', ')}.`:'');
  }
}
async function runRemoteRelationships(){
  const task=remoteTask();
  if(!task){setStatus('warn','Run Find relationships first, then test remote relationships from here.');return;}
  const b=validComparisonArea();
  if(!b){investigation.pendingRemoteAfterPick=true;addComparisonArea();setStatus('ok','Choose one comparison area B. Remote screening uses only that area and your selected measurements.');return;}
  if(ixState.loading)return;
  const spec={operation:'interconnections',region:task.regionId,variables:[task.variableId],start:task.start,end:task.end,provider:task.provider,relationship_variables:task.fields.slice(),relationship_scope:'remote',target_regions:[b.id]};
  ixState.loading=true;announceAction('remote-run',{started:true,areaB:b.id});
  try{
    const data=await runInvestigationJob(spec,`Testing remote relationships with ${b.name}`);
    if(!data)return;
    ixState.global=data.global;ixState.scope='remote';
    investigation.connections=data.global?.teleconnections||[];
    investigation.map?.setConnections(investigation.connections);
    renderIxGlobal(data.global,task.variableId);
    renderIxAnomaly(data.global||{source:data.local?.source_anomaly});
    renderIxHero(data.local,data.global);
    setIxTab('global');
    $('ix-sub').textContent=`Remote screening with ${b.name} only. These are statistical associations with possible temporal leads, not established physical causes.`;
    setStatus('ok','Remote relationship screening complete. Your local results were kept.');
  }catch(e){setStatus('err',esc(e.message));$('work-progress').hidden=true;}
  finally{ixState.loading=false;syncRemoteAction();window.TerraWorkspace?.refresh?.();}
}
async function openInterconnectScreen(options={}) {
  showInvestigationScreen('interconnect');setIxTab(ixState.tab||'local');
  if(options.run||options.force){
    try{jobSpec('interconnections');}catch(e){window.TerraWorkspace?.showIssues?.([{message:e.message,action:'measurements'}]);showInvestigationScreen('map');openDrawer(true);return;}
    if(ixState.loading)return;
    const {reg,vId,vMeta}=ixDrivers();if(!reg)return;
    ixState.loading=true;ixState.regionId=reg.id;ixState.varId=vId;
    $('ix-sub').textContent=`Testing relationships for ${reg.name}. Statistical associations do not establish physical causes.`;
    $('ix-period').textContent=$('start').value+'–'+$('end').value;
    try{showIxPanels(true);await loadInterconnectData(reg,vId);}finally{ixState.loading=false;window.TerraWorkspace?.refresh?.();}
  }else if(!ixState.local){
    $('ix-sub').textContent='Your selected areas and measurements are retained. Use Find relationships in the investigation panel to run this feature.';
    $('ix-pair-list').innerHTML='<p class="relationship-empty">Relationships have not been calculated yet. Choose at least two measurements, then Find relationships.</p>';
    $('ix-global-list').innerHTML='<p class="micro">Remote screening uses only your chosen area B when enabled.</p>';
    $('ix-hero').innerHTML='';
  }
}
