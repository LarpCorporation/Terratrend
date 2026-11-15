/* Geographic investigation workflow. Legacy chart/statistics controllers are
   retained in app.js; this module owns selection, jobs and renderer binding. */
const investigation = {level:'continent',scope:'',features:[],areas:{a:null,b:null},featureStore:new Map(),seq:0,analysisCall:0,job:null,provider:'nasa-merra2',nasa:null,appeears:null,boundaryView:{level:'continent',scope:''},providersLoaded:false,providerError:null,connecting:false,screen:'map',slot:'a',map:null,mapVariable:null,evidenceElement:null,geoCache:new Map(),geographicCall:0,geoAbort:null,loadingBoundaries:false,resultKey:null};
const oldRender = window.TerraLegacy.render;
const oldClearResults = window.TerraLegacy.clearResults;
const oldRenderSatellite = window.TerraLegacy.renderSatellite;
const oldRenderDataModal = window.TerraLegacy.renderDataModal;

function currentRegion() {return investigation.areas.a||state.catalog?.regions.find(r=>r.id===$('region')?.value)||null;}
function currentCompareRegion() {return investigation.areas.b||state.catalog?.regions.find(r=>r.id===$('compare-region')?.value)||null;}
function investigationKey() {return [currentRegion()?.id,currentCompareRegion()?.id,state.compareMode,state.selected.join(','),state.selected[state.activeVarIdx],$('start')?.value,$('end')?.value,investigation.provider].join('|');}
function openDrawer(open) {document.body.dataset.drawer=open?'open':'closed';$('drawer-toggle').setAttribute('aria-expanded',String(open));if(open)$('drawer-close').focus();}
function showInvestigationScreen(screen) {
  investigation.screen=screen;document.body.dataset.screen=screen;
  document.body.dataset.evidence='graphs';
  document.querySelectorAll('[data-analysis-evidence]').forEach(b=>{b.classList.toggle('active',b.dataset.analysisEvidence==='graphs');b.setAttribute('aria-pressed',String(b.dataset.analysisEvidence==='graphs'));});
  $('data-methods-screen').hidden=screen!=='sources';
  document.querySelectorAll('[data-kview]').forEach(el=>el.classList.toggle('active',el.dataset.kview===(screen==='analysis'?'observatory':screen)));
  if(screen==='compare'&&!state.compareMode)toggleCompareMode();
  if(screen==='map'){closeInterconnectScreen();investigation.map?.resize();}
  else if(typeof closeSelectionTools==='function')closeSelectionTools();
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
  cancelPendingWork();state.result=null;state.satellite=null;ixState.local=null;ixState.global=null;
  investigation.evidenceElement?.remove();investigation.evidenceElement=null;
  investigation.map?.setConnections([]);
  setStatus('ok','');
  if(clearMap){investigation.map?.clearResults();investigation.mapVariable=null;}
  oldClearResults();renderRegionCard(null);updateGlobeOverlay();
  $('sat-summary').textContent='Satellite comparison is retained here. Its imagery source is paused until the challenge-resource data setup is completed.';$('sat-tag').textContent='SOURCE SETUP';
  $('analysis-empty').hidden=false;$('analysis-context').textContent='PREPARED · CHOOSE ANALYZE';
  const readiness=sourceReadiness();$('selection-coverage').textContent=readiness.code==='ready'?(state.selected.length?'Selection prepared. Choose Analyze to calculate its trend.':'Selection prepared. Choose Analyze to discover which supported measurements are changing.'):'Selection saved. '+readiness.message;
  refreshVariableStrip();refreshSelection(false);
}
function clearResults() {oldClearResults();investigation.map?.clearResults();}
function renderRegionSelect() {
  const level=investigation.level;
  const list=state.catalog.regions.filter(r=>r.level===level&&(!investigation.scope||r.parent===investigation.scope||r.continent===investigation.scope));
  setAreaOptions(list,'continent:africa','');
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
  const a=currentRegion(),b=state.compareMode?currentCompareRegion():null;
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
  if(typeof refreshSelectionTools==='function')refreshSelectionTools();
}
function onRegionChange() {investigation.areas.a=state.catalog.regions.find(f=>f.id===$('region').value)||null;state.pendingBbox=null;prepareInvestigation(false);refreshSelection();}
function onCompareRegionChange() {investigation.areas.b=state.catalog.regions.find(f=>f.id===$('compare-region').value)||null;prepareInvestigation(false);refreshSelection(false);}
function toggleCompareMode() {
  state.compareMode=!state.compareMode;investigation.slot=state.compareMode?'b':'a';
  $('toggle-compare-mode').textContent=state.compareMode?'A + B · COMPARE':'MODE: SINGLE';
  $('toggle-compare-mode').classList.toggle('active',state.compareMode);
  $('compare-region-group').style.display=state.compareMode?'block':'none';
  if(state.compareMode&&$('region').value===$('compare-region').value){$('compare-region').value='';investigation.areas.b=null;}
  prepareInvestigation(false);refreshSelection(false);
}
function selectMapFeature(feature) {
  if(investigation.loadingBoundaries)return;
  const selected=investigation.slot==='a'?currentRegion():currentCompareRegion();
  if(selected?.id===feature.id){clearSelectionArea();return;}
  if(!assignSelectionArea(investigation.slot,feature))return;
  if(typeof selectionToolMessage==='function')selectionToolMessage(`Area ${investigation.slot.toUpperCase()} selected. Choose another tool or run Analyze.`);
  flashHint(`${feature.properties.name.toUpperCase()} SELECTED · CHOOSE ANALYZE`);
}
async function setGeographicLevel(level,scope=null) {
  const seq=++investigation.geographicCall;
  investigation.geoAbort?.abort();investigation.geoAbort=new AbortController();
  investigation.loadingBoundaries=true;$('boundary-loading').hidden=false;
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
    $('boundary-loading-label').textContent=`Drawing ${data.features.length} boundaries…`;
    if(investigation.map&&!await investigation.map.setFeatures(data.features,()=>seq===investigation.geographicCall))return;
    if(seq!==investigation.geographicCall)return;
    const a=currentRegion()?.id,b=currentCompareRegion()?.id;
    setAreaOptions(data.features.map(f=>f.properties),a,b);
    prepareInvestigation();refreshSelection(false);
    if(level==='region')investigation.map?.focusFeature(state.catalog.regions.find(r=>r.id===investigation.scope));
    const country=state.catalog.regions.find(r=>r.id===investigation.scope);
    $('coord-readout').textContent=`${data.features.length} ${level==='preset'?'PRESET FOCUS BOXES · NOT OFFICIAL ECOLOGICAL BOUNDARIES':level==='region'?'REGIONS · '+country?.name.toUpperCase()+' · CHANGE COUNTRY ABOVE':'AREAS · NATURAL EARTH 1:50M'}`;
  }catch(e){if(e.name==='AbortError')return;if(seq===investigation.geographicCall){setStatus('err',esc(e.message));$('coord-readout').textContent='BOUNDARIES UNAVAILABLE';investigation.features=[];investigation.map?.setFeatures([]);setAreaOptions([]);prepareInvestigation();setStatus('err',esc(e.message));openDrawer(true);}}finally{if(seq===investigation.geographicCall){investigation.loadingBoundaries=false;$('boundary-loading').hidden=true;if(investigation.map)investigation.map.pickingDisabled=false;}}
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
  state.activeVarIdx=0;prepareInvestigation();renderVarList();
}
function refreshVariableStrip() {
  if(!state.catalog)return;
  const strip=$('active-variable-strip');strip.replaceChildren();
  for(const v of state.catalog.variables){
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
  investigation.map?.setResults(rows);refreshSelection(false);
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
  $('k-scan-cta').onclick=analyze;$('card-analysis').onclick=()=>showInvestigationScreen('analysis');$('card-connections').onclick=()=>openInterconnectScreen({force:true});
  $('analysis-back').onclick=$('analysis-empty-map').onclick=$('methods-back').onclick=()=>showInvestigationScreen('map');
  document.querySelectorAll('[data-level]').forEach(b=>b.onclick=()=>setGeographicLevel(b.dataset.level));
  $('geography-presets').onclick=togglePresetRegions;
  $('geography-scope').onchange=()=>{if(investigation.level==='preset'){const f=investigation.featureStore.get($('geography-scope').value);if(f)selectMapFeature(f);}else setGeographicLevel(investigation.level,$('geography-scope').value);};
  $('mc-style').onclick=()=>investigation.map?.setProjection(investigation.map?.targetBlend?'globe':'plane');
  $('mc-zoom-in').onclick=()=>investigation.map?.zoomBy(-150);
  $('mc-zoom-out').onclick=()=>investigation.map?.zoomBy(150);
  $('mc-rotate').onclick=()=>{if(investigation.map)investigation.map.setAutoRotation(!investigation.map.auto);};
  $('mc-reset').onclick=()=>investigation.map?.setProjection('globe');
  document.querySelectorAll('[data-kview]').forEach(link=>link.onclick=e=>{e.preventDefault();if(link.dataset.kview==='interconnect')openInterconnectScreen({force:true});else showInvestigationScreen(link.dataset.kview==='observatory'?'analysis':link.dataset.kview);});
  for(const id of ['start','end'])$(id).addEventListener('change',()=>prepareInvestigation());
  const changeProvider=event=>{investigation.provider=event.target.value;$('science-provider').value=investigation.provider;$('methods-provider').value=investigation.provider;providerNote();prepareInvestigation();};
  $('science-provider').onchange=changeProvider;$('methods-provider').onchange=changeProvider;
  $('analyze-layer').onclick=analyzeLayer;$('cancel-work').onclick=()=>{prepareInvestigation(false);setStatus('ok','Analysis cancelled.');};
  $('resource-import-form').onsubmit=importChallengeData;
  $('earthdata-connect-form').onsubmit=connectEarthdata;
  $('earthdata-disconnect').onclick=disconnectEarthdata;
  $('appeears-connect-form').onsubmit=connectAppEEARS;
  $('appeears-disconnect').onclick=async()=>{const r=await fetch('/api/data-sources/appeears',{method:'POST',headers:{'Content-Type':'application/json'},body:'{"disconnect":true}'});if(r.ok){await loadProviders();prepareInvestigation();}};
  $('ix-remote-search').onchange=()=>{ixState.local=null;ixState.global=null;$('ix-sub').textContent='Choose Recompute to review '+($('ix-remote-search').checked?'the larger remote search.':'a local-only relationship request.');};
  $('connect-source-open').onclick=()=>{openDrawer(false);showInvestigationScreen('sources');};
  wireSelectionTools();
  if(typeof wireMapPanels==='function')wireMapPanels();
  const variable=$('import-variable');for(const v of state.catalog.variables){const option=document.createElement('option');option.value=v.id;option.textContent=v.name;variable.append(option);}variable.value='GWETROOT';
  variable.onchange=()=>{$('import-unit').value=state.catalog.variables.find(v=>v.id===variable.value).unit;};variable.onchange();
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){openDrawer(false);closeSelectionTools();}});
  if(await loadProviders())await setGeographicLevel('continent','');
  else{$('coord-readout').textContent='SERVER UPDATE REQUIRED';openDrawer(true);}
}
function sourceReadiness(){
  if(investigation.provider==='nasa-appeears')return investigation.appeears?.configured?{code:'ready',label:'Analyze',message:'AppEEARS connected. NASA will process the polygon; only summary files are returned.'}:{code:'login',label:'Connect AppEEARS',message:'Connect AppEEARS in Data & Methods using its separate NASA sign-in form.'};
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
  const readiness=sourceReadiness(),canConnect=['login','ready'].includes(readiness.code);
  $('k-scan-cta').textContent=readiness.label;$('k-scan-cta').title=readiness.message||'Analyze the selected area';
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
  const automatic=['nasa-merra2','nasa-giovanni','nasa-hydrology','nasa-appeears','noaa-cdo','multi-source'].includes(investigation.provider);
  $('active-source-label').textContent=({'nasa-giovanni':'NASA GIOVANNI','nasa-hydrology':'NASA HYDROLOGY','nasa-appeears':'NASA APPEEARS','noaa-cdo':'NOAA STATIONS','multi-source':'LINKED SOURCES','nasa-merra2':'NASA GES DISC','project-cache':'PROJECT CACHE'})[investigation.provider]||'RESOURCE IMPORT';
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
function jobSpec(operation) {
  const region=currentRegion();if(!region)throw new Error('Choose an area first');
  const discovery=operation==='scan';
  if(!discovery&&!state.selected.length)throw new Error('Choose a variable for this action, or use Analyze without variables to discover trends.');
  const variables=discovery?state.catalog.variables.filter(v=>variableSourceAvailable(v.id)).map(v=>v.id):['overview','interconnections'].includes(operation)?[state.selected[state.activeVarIdx]||state.selected[0]]:state.selected.slice();
  if(['nasa-merra2','nasa-giovanni'].includes(investigation.provider)){
    const readiness=sourceReadiness();if(readiness.code!=='ready')throw new Error(readiness.message);
    if(['analyze','overview','interconnections'].includes(operation)){const unavailable=variables.filter(id=>!variableSourceAvailable(id));if(unavailable.length)throw new Error('Automatic source mapping is still needed for: '+unavailable.map(id=>state.catalog.variables.find(v=>v.id===id)?.name||id).join(', ')+'. See the supported measurements in Data & Methods.');}
  }
  if(investigation.provider==='nasa-giovanni'){
    if(operation==='overview'&&investigation.level!=='preset')throw new Error('Choose the preset rectangles for a Giovanni layer request; geographic boundary layers need native mode.');
    if(operation==='interconnections'&&$('ix-remote-search')?.checked)throw new Error('Giovanni supports local rectangle relationships; remote country searches need native mode.');
    const areas=operation==='overview'?investigation.features:[region,...(state.compareMode&&!discovery&&operation!=='interconnections'?[currentCompareRegion()]:[])];
    if(areas.some(a=>!isGiovanniRectangle(a.geometry?a:investigation.featureStore.get(a?.id))))throw new Error('Giovanni needs a latitude/longitude rectangle for each area. Use presets, Lat / Lon bounds or an axis-aligned rectangular lasso; choose native mode for countries, circles and other exact boundaries.');
  }
  const spec={operation,region:region.id,variables,start:+$('start').value,end:+$('end').value,provider:investigation.provider};
  if(operation==='interconnections'){
    if(investigation.provider==='multi-source'&&state.selected.length<2)throw new Error('Select two or three measurements to link, such as soil moisture and vegetation greenness.');
    spec.relationship_variables=state.selected.length>=2?state.selected.slice():state.catalog.variables.filter(v=>variableSourceAvailable(v.id)).map(v=>v.id);
    spec.relationship_scope=$('ix-remote-search')?.checked===true?'remote':'local';
  }
  if(state.compareMode&&!discovery){const b=currentCompareRegion();if(!b||b.id===region.id)throw new Error('Choose two different areas for comparison');spec.compare_region=b.id;}
  const custom=[region,state.compareMode&&!discovery?currentCompareRegion():null].filter(f=>f?.level==='custom').map(f=>investigation.featureStore.get(f.id));
  if(custom.length){if(!state.catalog.custom_selections)throw new Error('Restart the TerraTrend Python server to analyze custom areas. Your selections are ready.');spec.custom_areas=custom;}
  return spec;
}
async function runInvestigationJob(spec,title) {
  const identity=investigationKey(),seq=++investigation.seq;
  if(investigation.job){const previous=investigation.job;investigation.job=null;await fetch(`/api/jobs/${previous}/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).catch(()=>{});}
  if(seq!==investigation.seq||identity!==investigationKey())return null;
  if(!window.TerraDataReview)throw new Error('Reload TerraTrend to load its data-use review.');
  const approved=await window.TerraDataReview.review(spec,state.catalog,sourceVariables()||[]);
  if(seq!==investigation.seq||identity!==investigationKey())return null;
  if(!approved){setStatus('ok','This request was not started.');return null;}
  setStatus('busy',title);
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
  investigation.job=null;$('work-progress').hidden=true;return job.result;
}
async function analyze() {
  if(!ensureSourceReady())return;
  if(!state.selected.length)return scanAll();
  const call=++investigation.analysisCall;
  try{const spec=jobSpec('analyze');$('run').disabled=true;$('k-scan-cta').disabled=true;setStatus('ok','Review the data request before starting.');
    const result=await runInvestigationJob(spec,state.compareMode?'Comparing selected areas':'Analyzing '+currentRegion().name);if(!result)return;
    const active=state.selected[state.activeVarIdx];state.result=result;state.activeVarIdx=Math.max(0,result.series.findIndex(s=>s.variable.id===active));investigation.resultKey=investigationKey();render();announceVerdict(result);setStatus('ok','');openDrawer(false);
  }catch(e){if(call===investigation.analysisCall){setStatus('err',esc(e.message));$('work-progress').hidden=true;openDrawer(true);}}finally{if(call===investigation.analysisCall){$('run').disabled=false;$('k-scan-cta').disabled=false;}}
}
function render() {
  oldRender();const d=state.result;if(!d)return;const s=d.series[state.activeVarIdx]||d.series[0],o=s.overall,p=s.provenance||{};
  $('analysis-empty').hidden=true;$('analysis-context').textContent=`${d.region.name.toUpperCase()} · ${d.start}–${d.end}`;
  $('analysis-page-description').textContent=[s.variable.name,p.source,p.aggregation].filter(Boolean).join(' · ');
  $('krc-value').textContent=o.ok?`${o.per_decade>0?'+':''}${num(o.per_decade,2)}`:'—';
  $('krc-unit').textContent=o.ok?`${s.variable.unit} / decade`:'insufficient data';
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
  const datasets=[];
  function add(block,name,color) {
    const points=yearly?block.yearly_timeseries.filter(p=>p.complete).map(p=>({x:p.year,y:p.value})):
      block.monthly_timeseries.map(p=>{const [y,m]=p.month.split('-').map(Number);return {x:y+(m-1)/12,y:p.value};});
    datasets.push({label:name,data:points,borderColor:color,backgroundColor:color,borderWidth:1.8,pointRadius:yearly?2:0,tension:.12,spanGaps:false});
    if(block.overall.ok&&points.length){const o=block.overall;datasets.push({label:`Trend / ${name}`,data:[points[0],points[points.length-1]].map(p=>({x:p.x,y:o.intercept+o.slope*p.x})),borderColor:color,borderDash:[5,4],borderWidth:1,pointRadius:0});}
    if(yearly){const partial=block.yearly_timeseries.filter(p=>!p.complete).map(p=>({x:p.year,y:p.value}));if(partial.length)datasets.push({label:'Partial year / excluded from trend',data:partial,showLine:false,pointStyle:'rectRot',pointRadius:4,backgroundColor:color,borderColor:color});}
  }
  add(s,d.region.name,s.variable.color);
  if(d.compare)add(d.compare.series[index]||d.compare.series[0],d.compare.region.name,C.fall);
  chart=new Chart($('chart').getContext('2d'),{type:'line',data:{datasets},options:{responsive:true,maintainAspectRatio:false,parsing:false,animation:false,interaction:{mode:'nearest',intersect:false},plugins:{legend:{display:!!d.compare,labels:{color:'#9bbba6',font:{family:'monospace',size:9},boxWidth:12}},tooltip:{callbacks:{label:ctx=>`${ctx.dataset.label}: ${num(ctx.parsed.y,3)} ${s.variable.unit}`}}},scales:{x:{type:'linear',grid:{color:'#284232'},ticks:{color:'#7b9f87',font:{family:'monospace',size:9},precision:0,maxTicksLimit:7,callback:x=>Number(x).toFixed(0)}},y:{grid:{color:'#284232'},ticks:{color:'#8db39a',font:{family:'monospace',size:9}},title:{display:true,text:s.variable.unit,color:'#789d84',font:{size:9}}}}}});
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
  if(spec.relationship_scope==='remote')spec.target_regions=reg.level==='continent'?state.catalog.regions.filter(r=>r.level==='continent'&&r.id!==reg.id).map(r=>r.id):['country:bra','country:aus','country:usa','country:chn','country:ind','country:deu','country:ken'].filter(id=>id!==reg.id);
  let data;
  try{data=await runInvestigationJob(spec,'Investigating candidate relationships');}catch(e){$('work-progress').hidden=true;setStatus('err',esc(e.message));$('ix-pair-list').innerHTML=`<p class="micro">${esc(e.message)}</p>`;$('ix-global-list').innerHTML='<p class="micro">No relationship result is available for this request.</p>';}
  if(!data)return;
  ixState.local=data.local;ixState.global=data.global;ixState.anomaly=data.global?.source||null;
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
  investigation.map?.setConnections(data.global?.teleconnections||[]);
}
async function traceGlobalImpacts() {await openInterconnectScreen({force:true});}
function render3DTeleconArcs(data) {investigation.map?.setConnections(data?.teleconnections||[]);}
function showConnectionEvidence(connection) {
  investigation.evidenceElement?.remove();
  const card=document.createElement('section');card.className='relationship-evidence';card.setAttribute('role','dialog');card.setAttribute('aria-label','Computed relationship evidence');
  const close=document.createElement('button');close.type='button';close.textContent='×';close.setAttribute('aria-label','Close evidence');close.onclick=()=>{card.remove();investigation.evidenceElement=null;};
  const label=document.createElement('span');label.className='eyebrow';label.textContent='COMPUTED RELATIONSHIP';
  const heading=document.createElement('h3');heading.textContent=`${connection.source_region.name} / ${connection.source_variable.name} ↔ ${connection.target_region.name} / ${connection.target_variable.name}`;
  const evidence=document.createElement('p');evidence.textContent=`${connection.direction.toUpperCase()} · r ${connection.r>=0?'+':''}${connection.r.toFixed(2)} · ${connection.lead_note}`;
  const significance=document.createElement('p');significance.textContent=`Lag-adjusted p ${connection.p.toPrecision(3)} · FDR-adjusted p ${(connection.p_adjusted??connection.p).toPrecision(3)}`;
  const interpretation=document.createElement('p');interpretation.className='micro';interpretation.textContent=connection.mechanism;
  const caution=document.createElement('p');caution.className='micro';caution.textContent='Statistical association and possible lead direction. A physical cause is not established.';
  card.append(close,label,heading,evidence,significance,interpretation,caution);$('globe').append(card);investigation.evidenceElement=card;close.focus();
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
    for(const c of group){const card=document.createElement('article');card.className='relationship-card';const title=document.createElement('strong');title.textContent=`${c.target_region.name} / ${c.target_variable.name}`;const evidence=document.createElement('p');evidence.textContent=`${c.direction.toUpperCase()} · r ${c.r>=0?'+':''}${c.r.toFixed(2)} · ${c.lead_note} · adjusted p ${(c.p_adjusted??c.p).toPrecision(3)}`;const note=document.createElement('p');note.className='micro';note.textContent=c.mechanism;const action=document.createElement('button');action.className='toolbar-button';action.type='button';action.textContent='SHOW ON MAP ↗';action.onclick=()=>{closeInterconnectScreen();showInvestigationScreen('map');investigation.map?.setConnections([c]);};card.append(title,evidence,note,action);list.append(card);}
  }
}
