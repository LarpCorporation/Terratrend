/* Independent A/B area picking. Drawing stays local until Analyze submits the
   exact saved polygon; changing a method never changes the other area's shape. */
const selectionTools={mode:'boundary',draft:null,center:null,size:250,revision:0,working:false,invalid:false};

function selectionToolMessage(message,error=false){$('selection-tool-status').textContent=message;$('selection-tool-status').classList.toggle('error',error);}
function selectedFeature(slot){const meta=slot==='a'?currentRegion():currentCompareRegion();return investigation.featureStore.get(meta?.id)||null;}
function refreshSelectionTools(){
  const slot=investigation.slot,a=currentRegion(),b=typeof validComparisonArea==='function'?validComparisonArea():(state.compareMode?currentCompareRegion():null);
  if(investigation.map)investigation.map.selectionSlot=slot;
  $('picked-area-a').textContent=a?.name||'Choose an area';$('picked-area-b').textContent=b?.name||'Add a second area';
  for(const role of ['a','b']){const active=role===slot,button=$('pick-area-'+role);button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));}
  $('clear-area-a').disabled=!a;$('clear-area-b').disabled=!b;
  $('dock-clear-area').disabled=!(slot==='a'?a:b);
  $('selection-dock').dataset.slot=slot;
  $('dock-clear-area').setAttribute('aria-label',`Clear area ${slot.toUpperCase()}`);
  document.querySelectorAll('[data-selection-slot]').forEach(b=>{b.classList.toggle('active',b.dataset.selectionSlot===slot);b.setAttribute('aria-pressed',String(b.dataset.selectionSlot===slot));});
  $('selection-title').textContent=slot==='a'?'Select primary area A':'Select comparison area B';
  $('selection-workbench').dataset.slot=slot;$('selection-workbench').dataset.mode=selectionTools.mode;$('selection-apply').textContent=`USE FOR AREA ${slot.toUpperCase()}`;
  $('selection-apply').disabled=!selectionTools.draft||selectionTools.working;
  const feature=selectionTools.draft||selectedFeature(slot),area=feature?.properties.area_km2,center=feature?.properties.center;
  $('selection-draft-summary').hidden=!(area>0);
  const shapeArea=selectionTools.draft?.properties.area_km2||(selectionTools.center&&!selectionTools.invalid&&feature?.properties.selection_kind===selectionTools.mode&&feature.properties.size_km===selectionTools.size?area:null);
  $('selection-shape-area').textContent=shapeArea>0?shapeArea.toLocaleString(undefined,{maximumFractionDigits:shapeArea<100?2:0})+' km²':selectionTools.invalid?'Adjust the size':'Place a centre dot';
  if(area>0){$('selection-area-value').textContent=area.toLocaleString(undefined,{maximumFractionDigits:area<100?2:0})+' km²';$('selection-center-value').textContent=`Centre: ${center[1].toFixed(4)}° latitude, ${center[0].toFixed(4)}° longitude`+(feature.properties.crosses_dateline?' · crosses 180°':'');}
}
function clearSelectionDraft(){
  selectionTools.revision++;selectionTools.draft=null;selectionTools.center=null;selectionTools.invalid=false;
  investigation.map?.setSelectionDraft(null);if(investigation.map)investigation.map.lassoPoints=[];
  $('lasso-point-count').textContent='0 points';selectionToolMessage('');refreshSelectionTools();
}
function activateSelectionSlot(slot){
  if(slot==='b'&&!state.compareMode)toggleCompareMode();
  investigation.slot=slot;clearSelectionDraft();showInvestigationScreen('map');openDrawer(false);
  toggleSelectionDock(true);
  setSelectionTool(selectionTools.mode);refreshSelection(false);
}
function toggleSelectionDock(open=$('selection-dock-tools').hidden){
  $('selection-dock-tools').hidden=!open;
  $('selection-dock-toggle').setAttribute('aria-expanded',String(open));
  $('selection-dock-toggle').setAttribute('aria-label',open?'Close selection toolbar':'Open selection toolbar');
  $('selection-dock-label').textContent=open?'Close selection toolbar':'Selection tools';
  if(!open)closeSelectionTools();
}
function closeSelectionTools(){
  $('selection-workbench').hidden=true;document.body.dataset.selecting='closed';clearSelectionDraft();
  selectionTools.mode='boundary';investigation.map?.setSelectionMode('boundary',investigation.slot);
  document.querySelectorAll('[data-selection-mode]').forEach(b=>{const active=b.dataset.selectionMode==='boundary';b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
}
function setSelectionTool(mode){
  clearSelectionDraft();selectionTools.mode=mode;investigation.map?.setSelectionMode(mode,investigation.slot);
  $('selection-workbench').hidden=mode==='boundary';document.body.dataset.selecting=mode==='boundary'?'closed':'open';
  if(mode!=='boundary'&&typeof expandMapPanel==='function')expandMapPanel('selection-workbench');
  refreshSelectionTools();
  document.querySelectorAll('[data-selection-mode]').forEach(b=>{b.classList.toggle('active',b.dataset.selectionMode===mode);b.setAttribute('aria-pressed',String(b.dataset.selectionMode===mode));});
  $('selection-shape-controls').hidden=!['circle','square'].includes(mode);$('selection-bounds-form').hidden=mode!=='bounds';$('selection-lasso-controls').hidden=mode!=='lasso';
  $('selection-size-label').textContent=mode==='square'?'SIDE LENGTH':'RADIUS';
  $('selection-size').setAttribute('aria-label',mode==='square'?'Square side length in kilometres':'Circle radius in kilometres');
  $('selection-help').textContent=({boundary:'Choose a geographic level above, then click a whole area. The Country menu loads regions worldwide when available.',lasso:'Drag an outline and release to close it. Or click vertices, then Finish outline. Shift-drag moves the map; scroll to zoom.',circle:'Click anywhere on the Earth to place a centre dot. Adjust the radius below, preview the covered area, then choose Use.',square:'Click anywhere on the Earth to place a centre dot. Adjust the side length below, preview the covered area, then choose Use. This square follows curved Earth edges; use Latitude / longitude for a coordinate rectangle and compact temperature/humidity summaries when supported.',bounds:'Enter west/east longitude and south/north latitude. Preview the bounds on the map, then choose Use.'})[mode];
  if(mode==='bounds'){
    const meta=investigation.slot==='a'?currentRegion():currentCompareRegion(),b=meta?.bbox;
    if(b)for(const [id,value] of [['bound-west',b[0]],['bound-south',b[1]],['bound-east',b[2]],['bound-north',b[3]]])$(id).value=value.toFixed(4);
  }
}
function clearSelectionArea(slot=investigation.slot){
  investigation.map?.cancelSelectionClick?.();
  investigation.areas[slot]=null;$(slot==='a'?'region':'compare-region').value='';
  if(slot==='b'){
    /* Removing B removes the comparison itself: no active comparison intent,
       no remote screening that needs B, and the A-only action returns. */
    state.compareMode=false;
    if(investigation.slot==='b')investigation.slot='a';
    const remote=$('ix-remote-search');if(remote){remote.checked=false;remote.disabled=true;}
  }
  if(slot===investigation.slot)clearSelectionDraft();
  prepareInvestigation(false);refreshSelection(false);
  flashHint(slot==='b'?'COMPARISON REMOVED · ANALYZE AREA A IS AVAILABLE AGAIN':`AREA ${slot.toUpperCase()} CLEARED · PICK A NEW AREA`);
  window.TerraWorkspace?.refresh?.();
  if(typeof announceAction==='function')announceAction('area-selected',{slot,id:null,name:null,level:null,cleared:true});
}
function previewSelection(feature){
  selectionTools.revision++;selectionTools.draft=feature;selectionTools.invalid=false;investigation.map?.setSelectionDraft(feature,investigation.slot);
  selectionToolMessage(`Preview only · choose Use for area ${investigation.slot.toUpperCase()} to save this boundary.`);refreshSelectionTools();
}
function placeSelectionShape(point){
  selectionTools.center=point;
  try{previewSelection(window.TerraSelection.shape(selectionTools.mode,point,selectionTools.size));}
  catch(e){selectionTools.draft=null;selectionTools.invalid=true;investigation.map?.setSelectionDraft(null);selectionToolMessage(e.message,true);refreshSelectionTools();}
}
function previewSelectionLasso(points){
  try{previewSelection(window.TerraSelection.lasso(points));}
  catch(e){selectionTools.draft=null;selectionToolMessage(e.message,true);refreshSelectionTools();}
}
function assignSelectionArea(slot,feature){
  if(slot==='b'&&!state.compareMode)toggleCompareMode();
  const other=slot==='a'?currentCompareRegion():currentRegion();
  if(state.compareMode&&other?.id===feature.id){selectionToolMessage('A and B must be different areas. Choose another boundary.',true);return false;}
  const meta=feature.properties;investigation.featureStore.set(feature.id,feature);
  const index=state.catalog.regions.findIndex(f=>f.id===feature.id);
  if(index>=0)state.catalog.regions[index]=meta;else state.catalog.regions.push(meta);
  investigation.areas[slot]=meta;
  const select=$(slot==='a'?'region':'compare-region');
  if(!Array.from(select.options||[]).some(o=>o.value===feature.id)){const option=document.createElement('option');option.value=feature.id;option.textContent=meta.name;select.append(option);}
  select.value=feature.id;state.pendingBbox=null;prepareInvestigation(false);refreshSelection(false);
  if(typeof announceAction==='function')announceAction('area-selected',{slot,id:feature.id,name:meta.name,level:meta.level||null});
  return true;
}
async function applySelectionDraft(){
  if(!selectionTools.draft||selectionTools.working)return;
  const draft=selectionTools.draft,slot=investigation.slot,revision=selectionTools.revision;
  selectionTools.working=true;refreshSelectionTools();
  try{
    const feature=await window.TerraSelection.identify(draft);
    if(revision!==selectionTools.revision||slot!==investigation.slot)return;
    feature.properties.surface='mixed';feature.properties.desc=`${feature.properties.name} · ${feature.properties.area_km2.toLocaleString(undefined,{maximumFractionDigits:1})} km² · custom boundary`;
    if(assignSelectionArea(slot,feature)){
      selectionTools.draft=null;investigation.map?.setSelectionDraft(null);refreshSelectionTools();
      selectionToolMessage(`Area ${slot.toUpperCase()} saved. You can choose a different method for the other area.`);
    }
  }catch(e){selectionToolMessage(e.message,true);}finally{selectionTools.working=false;refreshSelectionTools();}
}
function showAnalysisEvidence(mode){
  showInvestigationScreen('analysis');document.body.dataset.evidence=mode;
  $('analysis-empty').hidden=mode==='satellite'||!!state.result;
  document.querySelectorAll('[data-analysis-evidence]').forEach(b=>{b.classList.toggle('active',b.dataset.analysisEvidence===mode);b.setAttribute('aria-pressed',String(b.dataset.analysisEvidence===mode));});
}
function wireSelectionTools(){
  for(const [id,slot] of [['pick-area-a','a'],['pick-area-b','b'],['drawer-pick-a','a'],['drawer-pick-b','b']])$(id).onclick=()=>activateSelectionSlot(slot);
  document.querySelectorAll('[data-selection-slot]').forEach(b=>b.onclick=()=>activateSelectionSlot(b.dataset.selectionSlot));
  document.querySelectorAll('[data-selection-mode]').forEach(b=>b.onclick=()=>{
    setSelectionTool(b.dataset.selectionMode);
    if(typeof announceAction==='function')announceAction('selection-mode',{mode:b.dataset.selectionMode});
  });
  $('selection-dock-toggle').onclick=()=>toggleSelectionDock($('selection-dock-tools').hidden);
  $('selection-close').onclick=closeSelectionTools;$('selection-reset').onclick=clearSelectionDraft;$('selection-apply').onclick=applySelectionDraft;
  $('selection-clear-slot').onclick=$('dock-clear-area').onclick=()=>clearSelectionArea();
  $('clear-area-a').onclick=()=>clearSelectionArea('a');$('clear-area-b').onclick=()=>clearSelectionArea('b');
  $('lasso-undo').onclick=()=>investigation.map?.undoLasso();$('lasso-finish').onclick=()=>investigation.map?.finishLasso();
  for(const id of ['selection-size','selection-size-number'])$(id).oninput=()=>{
    const value=Number($(id).value);
    if(!Number.isFinite(value)||value<1||value>5000){selectionTools.draft=null;selectionTools.invalid=true;investigation.map?.setSelectionDraft(null);selectionToolMessage('Choose a size between 1 and 5,000 km.',true);refreshSelectionTools();return;}
    selectionTools.size=value;$(id==='selection-size'?'selection-size-number':'selection-size').value=value;
    if(selectionTools.center)placeSelectionShape(selectionTools.center);
  };
  $('selection-bounds-form').onsubmit=e=>{e.preventDefault();try{previewSelection(window.TerraSelection.bounds(...['bound-west','bound-south','bound-east','bound-north'].map(id=>$(id).value)));investigation.map?.focusFeature(selectionTools.draft);}catch(error){selectionTools.draft=null;investigation.map?.setSelectionDraft(null);selectionToolMessage(error.message,true);refreshSelectionTools();}};
  for(const id of ['bound-west','bound-south','bound-east','bound-north'])$(id).oninput=()=>{selectionTools.revision++;selectionTools.draft=null;investigation.map?.setSelectionDraft(null);refreshSelectionTools();};
  document.querySelectorAll('[data-analysis-evidence]').forEach(b=>b.onclick=()=>showAnalysisEvidence(b.dataset.analysisEvidence));
  refreshSelectionTools();
}
