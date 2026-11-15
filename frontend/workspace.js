/* One investigation workspace, saved evidence, accessible guidance and map links. */
(function(){
  'use strict';
  let initialized=false,highlight=null,lastSavedId=null;
  const pinned=new Map();
  const names=()=>state.selected.map(id=>state.catalog.variables.find(v=>v.id===id)?.name||id);
  const button=(text,action)=>{const b=document.createElement('button');b.type='button';b.className='toolbar-button';b.textContent=text;b.onclick=action;return b;};
  const announce=(action,detail)=>{try{document.dispatchEvent(new CustomEvent('terratrend:action',{detail:{action,...(detail||{})}}));}catch(_){} };

  /* ---------------------------------------------------------------------
     Saved investigations: local, durable, server-side evidence.
     --------------------------------------------------------------------- */
  const resultsApi={
    async list(params={}){
      const qs=new URLSearchParams(Object.entries(params).filter(([,v])=>v!==undefined&&v!==null&&v!==''));
      const r=await fetch('/api/results?'+qs.toString());const body=await r.json();
      if(!r.ok)throw new Error(body.error||'The saved-result library could not be read.');
      return body;
    },
    async get(id){
      const r=await fetch('/api/results/'+encodeURIComponent(id));const body=await r.json();
      if(!r.ok)throw new Error(body.error||'This saved result could not be opened.');
      return body;
    },
    async remove(id){
      const r=await fetch('/api/results',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'delete',id})});
      const body=await r.json();if(!r.ok)throw new Error(body.error||'This saved result could not be removed.');return body;
    }
  };
  const formatBytes=n=>{n=Number(n)||0;if(n<1024)return n+' B';if(n<1024*1024)return (n/1024).toFixed(1)+' KB';if(n<1073741824)return (n/1048576).toFixed(1)+' MB';return (n/1073741824).toFixed(2)+' GB';};
  const formatWhen=iso=>{try{return new Date(iso).toLocaleString(undefined,{year:'numeric',month:'short',day:'2-digit',hour:'2-digit',minute:'2-digit'});}catch(_){return iso||'unknown time';}};
  const recordYears=r=>r?.window?`${r.window.start}–${r.window.end}`:'';
  const recordAreaNames=r=>(r?.areas||[]).filter(a=>a.role!=='layer').map(a=>a.name).filter(Boolean);
  function recordTitle(r){
    if(r.title)return r.title;
    const areas=recordAreaNames(r).join(' + ')||'Area';
    const vars=(r.variables||[]).map(v=>v.name||v.id).join(', ')||'measurements';
    return `${areas} · ${vars}${recordYears(r)?' · '+recordYears(r):''}`;
  }

  /* ------------------------------------------------------------------ */
  function open(){
    if(investigation.screen!=='map')showInvestigationScreen('map');
    if(typeof expandMapPanel==='function')expandMapPanel('k-region-card',true);
    const picker=$('measurement-picker');if(picker)picker.open=true;
    requestAnimationFrame(()=>{$('measurement-picker')?.querySelector('summary')?.focus();scrollPanelTo('measurement-picker');});
  }
  /* Keep an opened control visible inside the single outer scroll area. */
  function scrollPanelTo(id,block='nearest'){
    const el=$(id),body=$('area-panel-body');if(!el||!body)return;
    const top=el.offsetTop-(body.scrollTop?0:0);
    if(el.getBoundingClientRect().top<body.getBoundingClientRect().top||el.getBoundingClientRect().bottom>body.getBoundingClientRect().bottom){
      body.scrollTo({top:Math.max(0,top-8),behavior:(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches)?'auto':'smooth'});
    }
  }

  function refresh(){
    if(!state.catalog)return;
    const a=currentRegion(),b=validComparisonArea();
    const action=resolveRunAction();
    $('measurement-summary').textContent=names().join(' · ')||'None selected · discover trends';
    $('measurement-summary').title=names().join(', ');
    const run=$('run');
    if(run){
      const label={analyze:'ANALYZE REGION',compare:'COMPARE REGIONS','need-b':'ADD A REGION TO COMPARE',discover:'FIND WHAT IS CHANGING HERE',blocked:'CHOOSE A REGION'}[action.kind]||action.label;
      run.textContent=label;run.dataset.action=action.kind;
      run.disabled=false;
      run.title=[action.areaA?.name,action.areaB?.name,names().join(', ')||'All compatible measurements',$('start').value+'–'+$('end').value].filter(Boolean).join(' · ');
      run.setAttribute('aria-describedby','run-requirement');
    }
    const requirement=$('run-requirement');
    if(requirement){
      const show=action.kind==='need-b'||action.kind==='blocked';
      requirement.hidden=!show;requirement.replaceChildren();
      if(show){
        const p=document.createElement('span');p.textContent=action.reason||'Choose an area first.';requirement.append(p);
        if(action.kind==='need-b'){
          const row=document.createElement('span');row.className='run-requirement-actions';
          row.append(button('Study this region only',()=>{removeComparisonArea();setStatus('ok','Comparison removed. Analyze area A on its own.');}));
          row.append(button('Change comparison areas',()=>addComparisonArea()));
          requirement.append(row);
        }
      }
    }
    $('toggle-compare-mode').textContent=state.compareMode?'A + B · COMPARISON ON':'ADD COMPARISON B';
    $('compare-region-group').style.display=state.compareMode?'block':'none';
    $('analyze-layer').textContent=`ANALYZE ALL ${investigation.features.length} DISPLAYED AREAS`;
    $('layer-scope-note').textContent='Whole-layer request: every displayed area, using the first selected measurement. This does not limit the request to A and B.';
    const needsRectangle=investigation.provider==='nasa-giovanni'||state.selected.some(id=>['T10M','QV10M'].includes(id));
    for(const el of document.querySelectorAll('[data-level], [data-selection-mode]')){
      const unsupported=needsRectangle&&(el.dataset.level||['boundary','circle','square'].includes(el.dataset.selectionMode));
      el.disabled=!!unsupported;
      el.title=unsupported?'The selected measurements require a rectangle. Use Presets or Latitude / Longitude bounds.':el.dataset.level?'Select a geographic level':el.getAttribute('aria-label')||'';
    }
    /* Remote screening needs a real, different B and an active comparison. */
    const remote=$('ix-remote-search');
    if(remote){const needsB=!comparisonActive();remote.disabled=needsB;if(needsB)remote.checked=false;}
    $('completed-result-summary').hidden=!state.result;
    $('card-analysis').disabled=!state.result;$('card-connections').disabled=!ixState.local;
    const result=state.result,match=result&&investigation.resultKey===investigationContextKey();
    $('k-region-card').dataset.hasResult=result?'true':'false';
    if(!result){$('krc-unit').textContent='Ready to investigate';$('krc-verdict').textContent='Choose measurements or discover trends';$('selection-coverage').textContent=a?'Your selection is prepared. Review the request before data is fetched.':'Choose primary area A on the map or from the area list.';}
    else if(!match){$('selection-coverage').textContent=resultContextSentence();}
    $('k-region-card').dataset.compare=String(!!state.compareMode);
    renderCompareBanner({a,b,result,match,action});
    if(investigation.pendingRemoteAfterPick&&validComparisonArea()){
      investigation.pendingRemoteAfterPick=false;
      showInvestigationScreen('interconnect');
      setStatus('ok','Area B chosen. Run remote relationships when you are ready; your local results are kept.');
    }
    filterMeasurements();refreshConnections();
    if(initialized)connectionStates();
    refreshSavedCount();
  }

  /* Plain, explicit description of what the displayed evidence actually is. */
  function resultContextSentence(){
    const r=state.result;if(!r)return '';
    const area=r.compare?`${r.region.name} and ${r.compare.region.name}`:r.region?.name||'the saved area';
    const vars=(r.series||[]).map(s=>s.variable.name).join(', ');
    return `Displayed evidence: ${area} · ${vars||'measurements'} · ${r.start}–${r.end}. Your edited selection has not been calculated yet.`.trim();
  }

  function renderCompareBanner(ctx){
    const info=$('comparison-ready');if(!info)return;
    const onCompare=investigation.screen==='compare';
    info.hidden=!onCompare;info.replaceChildren();
    if(!onCompare)return;
    const {a,b,result,match}=ctx;
    const computed=result&&result.compare;
    const row=document.createElement('div');row.className='compare-context';
    const head=document.createElement('h3');head.style.cssText='margin:0 0 8px;font-size:18px;font-weight:500;color:#e4f3e8';
    const lines=[],actions=[];
    if(computed){
      const vars=(result.series||[]).map(s=>s.variable.name).join(', ');
      head.textContent=`Completed comparison · ${result.region.name} and ${result.compare.region.name}`;
      lines.push(`Measurement: ${vars||'—'}`);
      lines.push(`Requested period: ${result.start}–${result.end}`);
      if(!match)lines.push('These are the values that were calculated. Your edited areas or dates are not in this result yet.');
      actions.push(button('Change comparison areas',()=>addComparisonArea()));
    }else if(result&&!result.compare){
      head.textContent=`Displayed result: ${result.region.name} only`;
      const vars=(result.series||[]).map(s=>s.variable.name).join(', ');
      lines.push(`Measurement: ${vars||'—'}`);
      lines.push(`Requested period: ${result.start}–${result.end}`);
      if(b)lines.push(`Selected for comparison but not yet calculated: ${a?.name||'Area A'} + ${b.name}.`);
      else lines.push(`Selected for comparison but not yet calculated: ${a?.name||'Area A'} + an area B that has not been chosen.`);
      actions.push(button(b?'Change comparison areas':'Add comparison area B',()=>addComparisonArea()));
    }else{
      head.textContent='Two places, one question';
      if(b&&a){
        lines.push(`Selected: ${a.name} + ${b.name}`);
        lines.push(`Requested period: ${$('start').value}–${$('end').value}`);
        lines.push(`Measurement: ${names().join(', ')||'choose a measurement'}`);
        lines.push('Run Compare A + B in the investigation panel. Observations already downloaded for area A are reused.');
        actions.push(button('Change comparison areas',()=>addComparisonArea()));
      }else{
        lines.push(`${a?.name||'Area A'} stays selected. Add a second area to compare two places; this does not start a download.`);
        actions.push(button('Add comparison area B',()=>addComparisonArea()));
      }
    }
    row.append(head);
    for(const line of lines){const p=document.createElement('p');p.className='compare-line';p.textContent=line;row.append(p);}
    if(actions.length){const bar=document.createElement('div');bar.className='compare-actions';for(const x of actions)bar.append(x);row.append(bar);}
    info.append(row);
  }

  function requireComparison(){
    if(investigation.screen!=='map')showInvestigationScreen('map');
    if(typeof expandMapPanel==='function')expandMapPanel('k-region-card',true);
    state.compareMode=true;refresh();
    const row=document.querySelector('.area-picker-row.slot-b');
    if(row)row.scrollIntoView({block:'nearest'});
    setTimeout(()=>$('pick-area-b')?.focus(),30);
  }

  let lastSearch=null;
  function filterMeasurements(){
    const search=($('measurement-search').value||'').trim().toLowerCase();
    let shown=0;
    document.querySelectorAll('#var-list [data-variable]').forEach(el=>{const hide=!!search&&!el.textContent.toLowerCase().includes(search);el.hidden=hide;if(!hide)shown++;});
    /* Only jump back to the top when the query itself changed, so checking a
       measurement deep in the list does not scroll the panel away. */
    if(search!==lastSearch){
      lastSearch=search;
      const body=$('area-panel-body');
      if(body&&$('measurement-picker')?.open)scrollPanelTo('measurement-picker');
      announce('measurement-filtered',{shown,search});
    }
  }
  function showIssues(issues){
    const box=$('compatibility-help');box.hidden=false;box.replaceChildren();
    for(const issue of issues){
      const p=document.createElement('p');p.textContent=issue.message;box.append(p);
      if(issue.action==='bounds')box.append(button('Use coordinate rectangle',()=>{showInvestigationScreen('map');openDrawer(false);activateSelectionSlot(issue.region===currentCompareRegion()?.id?'b':'a');setSelectionTool('bounds');}));
      else if(issue.action==='connect')box.append(button('Connect NASA services',()=>showInvestigationScreen('sources')));
      else box.append(button(issue.action==='measurements'?'Choose companion measurements':'Change area or measurements',()=>{open();if(issue.action!=='measurements')$('area-list-picker').open=true;}));
    }
    if(state.selected.length===1&&issues.some(i=>i.action==='measurements')){
      const suggestions=['PRECTOTCORR','GWETROOT','NDVI'].filter(id=>id!==state.selected[0]&&variableSourceAvailable(id));
      for(const id of suggestions)box.append(button('Add '+(state.catalog.variables.find(v=>v.id===id)?.name||id),()=>{toggleVar(id);box.hidden=true;}));
    }
  }

  /* ---------------------------------------------------------------------
     Saving the completed result. The server persists the record itself when
     the job completes; here we only discover its id and keep a small
     in-page list for instant switching.
     --------------------------------------------------------------------- */
  function saveResult(result){
    lastSavedId=result.saved_record_id||null;
    const snapshot={result,selected:state.selected.slice(),provider:investigation.provider,key:investigationContextKey()};
    investigation.savedResults=investigation.savedResults.filter(item=>item.key!==snapshot.key);
    investigation.savedResults.unshift(snapshot);investigation.savedResults=investigation.savedResults.slice(0,24);
    const select=$('saved-results');if(!select)return;
    select.replaceChildren();
    investigation.savedResults.forEach((item,i)=>{const option=document.createElement('option');option.value=i;option.textContent=`${item.result.region.name}${item.result.compare?' / '+item.result.compare.region.name:''} · ${item.result.start}–${item.result.end} · ${item.result.series.map(s=>s.variable.name).join(', ')}`;select.append(option);});
    $('saved-results-control').hidden=false;
    resolveSavedId(result).then(id=>{if(state.result!==result)return;lastSavedId=id;if(id)announce('result-saved',{resultId:id});});
    refreshSavedCount();
  }
  async function resolveSavedId(result){
    if(!result)return null;
    if(result.saved_record_id)return result.saved_record_id;
    try{
      const variable=result.series?.[0]?.variable?.id;
      const body=await resultsApi.list({variable,limit:25});
      const rows=body.results||[];
      const areaIds=[result.region?.id,result.compare?.region?.id].filter(Boolean).sort();
      const variables=(result.series||[]).map(s=>s.variable.id).sort();
      for(const row of rows){
        const ids=(row.areas||[]).filter(a=>['a','b'].includes(String(a.role).toLowerCase())).map(a=>a.id).filter(Boolean).sort();
        if(JSON.stringify(ids)!==JSON.stringify(areaIds))continue;
        if(row.status==='current'&&JSON.stringify((row.variables||[]).map(v=>v.id).sort())===JSON.stringify(variables)&&row.window?.start===result.start&&row.window?.end===result.end&&row.provider_family===investigation.provider)return row.id;
      }
    }catch(_){/* storage may be unavailable; the library will report it */}
    return null;
  }
  function restoreResult(index){
    const item=investigation.savedResults[index];if(!item)return;
    cancelPendingWork();state.result=item.result;state.selected=item.selected.slice();state.activeVarIdx=0;
    investigation.areas.a=item.result.region;investigation.areas.b=item.result.compare?.region||null;state.compareMode=!!item.result.compare;
    $('start').value=item.result.start;$('end').value=item.result.end;investigation.provider=item.provider;
    $('methods-provider').value=$('science-provider').value=item.provider;
    setAreaOptions(investigation.features.map(f=>f.properties),item.result.region.id,item.result.compare?.region.id);
    investigation.resultKey=investigationContextKey();renderVarList();render();refresh();
  }

  /* ---------------------------------------------------------------------
     Saved investigations library (durable, served by the backend).
     --------------------------------------------------------------------- */
  let savedCache=[];
  function openSavedLibrary(){
    const dialog=$('saved-library');if(!dialog)return;
    if(!dialog.open){dialog.showModal();loadSaved();if($('saved-search'))$('saved-search').focus();}
  }
  function closeSavedLibrary(){const d=$('saved-library');if(d&&d.open)d.close();}
  async function refreshSavedCount(){
    if(!$('saved-open'))return;
    try{const body=await resultsApi.list({limit:1});$('saved-open').textContent=(body.total||0)?`SAVED · ${body.total}`:'SAVED';$('saved-open').title=`${body.total||0} saved investigations on this computer`;}
    catch(_){$('saved-open').textContent='SAVED';}
  }
  async function loadSaved(){
    const list=$('saved-list'),storage=$('saved-storage');
    if(!list)return;
    list.replaceChildren();storage.textContent='Reading the local result library…';
    try{
      const q=($('saved-search')?.value||'').trim();
      const body=await resultsApi.list({q,limit:200});
      savedCache=body.results||[];
      renderSaved();
      const s=body.storage||{};
      storage.textContent=[`${s.count??savedCache.length} completed investigation${(s.count??savedCache.length)===1?'':'s'} stored locally`,`${formatBytes(s.bytes)} of scientific payload`,`No automatic deletion: older results stay until you remove them`].join(' · ');
    }catch(e){
      storage.textContent='Saved investigations could not be read. The analysis features still work; this library is unavailable until the server is reachable.'+(e.message?' ('+e.message+')':'');
      list.replaceChildren();
    }
  }
  function renderSaved(){
    const list=$('saved-list');if(!list)return;list.replaceChildren();
    $('saved-count').textContent=`${savedCache.length} saved result${savedCache.length===1?'':'s'}`;
    if(!savedCache.length){
      const p=document.createElement('li');p.className='saved-empty';p.textContent='No completed investigations are stored yet. Finish an analysis, comparison, discovery or relationship check and it will appear here automatically, even after you close this browser.';
      list.append(p);return;
    }
    for(const record of savedCache){
      const li=document.createElement('li');li.className='saved-item';
      const h=document.createElement('h3');h.textContent=recordTitle(record);
      const meta=document.createElement('p');meta.className='saved-meta';
      const kindLabel={analysis:'Analysis',compare:'Comparison',discovery:'Discovery',relationships:'Relationships',layer:'Area layer'}[record.kind]||record.kind;
      const badge=document.createElement('span');badge.className='saved-badge'+(record.status==='legacy'?' stale':'');
      badge.textContent=kindLabel+(record.status==='legacy'?' · older method':'');
      meta.append(badge,document.createTextNode(`${recordYears(record)} · saved ${formatWhen(record.created_at)}`));
      const vars=document.createElement('p');vars.className='saved-meta';vars.textContent=(record.variables||[]).map(v=>v.name||v.id).join(', ');
      li.append(h,meta,vars);
      if(record.status==='legacy'&&record.stale_reason){const note=document.createElement('p');note.className='saved-meta';note.textContent=record.stale_reason;li.append(note);}
      const actions=document.createElement('div');actions.className='saved-item-actions';
      const open=button('Open this result',()=>restoreSavedById(record.id));
      open.setAttribute('aria-label',`Open saved result: ${recordTitle(record)}`);
      actions.append(open);
      const explain=button('Explain this result',()=>{closeSavedLibrary();openExplanation(record.id);});
      explain.setAttribute('aria-label',`Explain saved result: ${recordTitle(record)}`);
      actions.append(explain);
      const del=button('Remove',async()=>{try{await resultsApi.remove(record.id);await loadSaved();refreshSavedCount();}catch(e){$('saved-storage').textContent=e.message;}});
      del.setAttribute('aria-label',`Remove saved result: ${recordTitle(record)}`);
      actions.append(del);
      li.append(actions);list.append(li);
    }
  }

  function areaFromRecord(record,role){
    const area=(record.areas||[]).find(a=>a.role===role)||(role==='A'?(record.areas||[])[0]:null);
    if(!area)return null;
    return {id:area.id,name:area.name,level:area.level,bbox:area.bbox,desc:area.level?`${area.level} · saved boundary`:''};
  }
  async function restoreSavedById(id){
    try{const record=await resultsApi.get(id);await applySavedRecord(record);return record;}
    catch(e){const s=$('saved-storage');if(s)s.textContent=e.message;return null;}
  }
  async function applySavedRecord(record){
    if(!record)return;
    closeSavedLibrary();
    cancelPendingWork();
    const payload=record.payload||null;
    if(record.kind==='event'){
      showInvestigationScreen('events');window.TerraEvents?.restore?.({...payload,saved_record_id:record.id});
      announce('result-restored',{resultId:record.id,kind:'event'});return;
    }
    lastSavedId=record.id;
    /* Re-register an exact saved polygon so the area keeps its real shape. */
    for(const area of record.areas||[]){
      if(area.geometry){
        try{const r=await fetch('/api/geography/custom',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({geometry:area.geometry,name:area.name})});
          if(r.ok){const feature=await r.json();if(feature&&feature.id)investigation.featureStore.set(feature.id,feature);}
        }catch(_){/* the saved evidence is still readable without re-registration */}
      }
    }
    /* Prefer the saved record's human area label: the analysis payload may
       only carry a generic name ("Coordinate bounds"), which cannot tell two
       compared areas apart in the banner, chart keys or legend. */
    const namedFrom=(area,meta)=>{
      if(!area||!meta)return area||meta||null;
      if(!area.name||!meta.name)return area;
      return {...area,name:meta.name};
    };
    const a=namedFrom(payload?.region,areaFromRecord(record,'A'))||areaFromRecord(record,'A');
    const b=namedFrom(payload?.compare?.region,areaFromRecord(record,'B'))||areaFromRecord(record,'B');
    investigation.areas.a=a||null;investigation.areas.b=b||null;
    state.compareMode=!!b;
    state.selected=record.kind==='discovery'?[]:(record.variables||[]).map(v=>v.id).filter(Boolean);
    state.activeVarIdx=0;
    if(record.window?.start)$('start').value=record.window.start;
    if(record.window?.end)$('end').value=record.window.end;
    if(record.provider_family){investigation.provider=record.provider_family;$('methods-provider').value=record.provider_family;$('science-provider').value=record.provider_family;}
    /* Claim the context before anything re-renders, so the restored result is
       shown as the current result rather than as an earlier unmatched edit. */
    if(payload)investigation.resultKey=investigationContextKey();
    const regions=investigation.features.map(f=>f.properties);
    for(const meta of [a,b])if(meta&&meta.id&&!regions.some(r=>r.id===meta.id))regions.push(meta);
    setAreaOptions(regions,a?.id||'',b?.id||'');
    renderVarList();
    const kind=record.kind;
    if(kind==='analysis'||kind==='compare'){
      state.result=payload?{...payload,saved_record_id:record.id,
        region:a?.name?{...payload.region,name:a.name}:payload.region,
        compare:payload.compare&&b?.name?{...payload.compare,region:{...payload.compare.region,name:b.name}}:payload.compare}:payload;
      investigation.resultKey=investigationContextKey();
      render();renderGlobeRegions?.(payload);
      /* Put the investigation back where it was: the map, the selected area and
         measurement, and the colouring produced by this result. Analysis is
         already loaded when the user opens it. */
      showInvestigationScreen('map');
      await attachRelatedEvidence(record);
      loadSavedTrendMap(true);
    }else if(kind==='event'){
      showInvestigationScreen('events');window.TerraEvents?.restore?.(payload);
    }else if(kind==='discovery'){
      state.result=null;
      if(payload?.scanned){renderScan(payload.scanned,payload.scanned.length);showModal($('scan-modal'));}
      showInvestigationScreen('map');
    }else if(kind==='relationships'){
      ixState.recordId=record.id;
      ixState.local=payload?.local||null;ixState.global=payload?.global||null;
      const reg=a||{id:record.areas?.[0]?.id,name:record.areas?.[0]?.name};
      if(reg)ixState.regionId=reg.id;
      if(payload&&payload.local){
        const vId=state.selected[0];
        renderIxHero(payload.local,payload.global);renderIxLocal(payload.local,vId);renderIxGlobal(payload.global,vId);renderIxAnomaly(payload.global||{source:payload.local?.source_anomaly});
        $('ix-sub').textContent=`Saved relationship evidence for ${reg?.name||'the selected area'}. These are statistical associations, not established physical causes.`;
        $('ix-period').textContent=`${record.window?.start||'—'}–${record.window?.end||'—'}`;
      }
      showInvestigationScreen('interconnect');
    }else{
      showInvestigationScreen('map');
    }
    refresh();
    announce('result-restored',{resultId:record.id,kind});
    setStatus('ok','Opened a saved result from local storage. No download was started.');
  }

  /* Optional grounded explanation. When no AI provider is configured the
     server returns the deterministic summary and says so; the app never
     depends on the AI layer to explain a result. */
  async function openExplanation(resultId){
    if(window.TerraAssistant)return window.TerraAssistant.explain(resultId);
    let dialog=$('explain-dialog');
    if(!dialog){
      dialog=document.createElement('dialog');dialog.id='explain-dialog';dialog.className='explain-dialog';
      dialog.innerHTML='<div class="explain-head"><div><span class="eyebrow">PLAIN-LANGUAGE SUMMARY · GROUNDED IN THIS RESULT</span><h2>What this result says</h2></div><button type="button" class="toolbar-button" id="explain-close" aria-label="Close explanation">×</button></div><div id="explain-body" class="explain-body"></div>';
      document.body.append(dialog);
      $('explain-close').onclick=()=>dialog.close();
      dialog.addEventListener('close',()=>{dialog.dataset.for='';});
    }
    if(!dialog.dataset.for||dialog.dataset.for!==String(resultId||'live')){
      dialog.dataset.for=String(resultId||'live');
      const body=$('explain-body');
      body.textContent='Building a summary from the stored numbers…';
      try{
        const reply=await fetch('/api/explain',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(resultId?{record_id:resultId}:{result:state.result,kind:state.result?.compare?'compare':'analysis'})});
        const data=await reply.json();
        if(!reply.ok)throw new Error(data.error||'The explanation service is unavailable.');
        body.replaceChildren();
        const summary=data.summary||{};
        const provider=document.createElement('p');provider.className='explain-provider';
        provider.textContent=data.available
          ? 'Plain-language wording supplied by the configured explanation model, restricted to the numbers below.'
          : String(data.reason||'Live AI explanation is not configured').replace(/\.$/,'')+'. This summary is generated deterministically from the stored numbers, so the app works fully without any AI service.';
        body.append(provider);
        if(summary.headline){const h=document.createElement('p');h.className='explain-headline';h.textContent=summary.headline;body.append(h);}
        if(summary.sentences?.length){const ul=document.createElement('ul');ul.className='explain-list';for(const line of summary.sentences){const li=document.createElement('li');li.textContent=line;ul.append(li);}body.append(ul);}
        if(summary.caveats?.length){const box=document.createElement('div');box.className='explain-caveats';const label=document.createElement('strong');label.textContent='Read this with';box.append(label);const ul=document.createElement('ul');for(const line of summary.caveats){const li=document.createElement('li');li.textContent=line;ul.append(li);}box.append(ul);body.append(box);}
        if(summary.sources?.length){const src=document.createElement('p');src.className='explain-sources';src.textContent='Sources reported by this result: '+summary.sources.join(' · ');body.append(src);}
        const note=document.createElement('p');note.className='explain-note';note.textContent='Every number above is taken from the stored analysis; the wording adds no new evidence and no forecast, attribution or hazard assessment.';
        body.append(note);
      }catch(e){
        body.textContent='An explanation could not be produced ('+e.message+'). The stored result and its statistics are unchanged.';
      }
    }
    if(!dialog.open)dialog.showModal();
  }

  /* A saved analysis can have a saved relationship check for the same area and
     window. Load it so Interconnections shows what was already computed instead
     of asking the user to run it again. */
  async function attachRelatedEvidence(record){
    try{
      const areaId=(record.areas||[])[0]?.id;
      if(!areaId)return;
      const listing=await resultsApi.list({kind:'relationships',limit:100});
      const match=(listing.results||[]).find(row=>
        (row.areas||[]).some(x=>x.id===areaId)&&
        row.window?.start===record.window?.start&&row.window?.end===record.window?.end);
      if(!match)return;
      const full=await resultsApi.get(match.id);
      const data=full.payload||{};
      if(!data.local)return;
      ixState.local=data.local;ixState.global=data.global||null;ixState.scope=data.scope||'local';
      investigation.remoteTask={regionId:areaId,regionName:(full.areas||[])[0]?.name||'',
        variableId:(full.variables||[])[0]?.id||null,
        fields:(full.variables||[]).map(v=>v.id).filter(Boolean),
        start:full.window?.start,end:full.window?.end,provider:full.provider_family,scope:data.scope||'local'};
      if(data.local.pairs){
        const vId=investigation.remoteTask.variableId;
        renderIxHero(data.local,data.global);renderIxLocal(data.local,vId);renderIxGlobal(data.global,vId);
        renderIxAnomaly(data.global||{source:data.local?.source_anomaly});
        const sub=$('ix-sub');
        if(sub)sub.textContent=`Saved relationship evidence for ${investigation.remoteTask.regionName||'this area'} · ${full.window?.start||''}–${full.window?.end||''}. These are statistical associations, not established causes.`;
        const period=$('ix-period');
        if(period)period.textContent=`${full.window?.start||'—'}–${full.window?.end||'—'}`;
      }
    }catch(_){/* related evidence is a bonus, never a failure */}
  }

  function connectionStates(){
    for(const [name,status] of [['earthdata',investigation.nasa],['appeears',investigation.appeears]]){
      const form=$(name+'-connect-form'),badge=$(name+'-connected-badge');if(!form||!badge)continue;
      const connected=!!status?.configured;badge.hidden=!connected;badge.textContent=connected?'CONNECTED'+(status.remembered?' · REMEMBERED':''):'';
      if(form.dataset.editing!=='true')form.hidden=connected;
      $(name+'-reconnect').hidden=!connected;$(name+'-disconnect').hidden=!connected;
    }
  }
  function refreshConnections(){
    const links=investigation.connections||[],legend=$('connection-legend');if(!legend)return;
    legend.hidden=!links.length;legend.replaceChildren();
    if(!links.length)return;
    const label=document.createElement('strong');label.textContent='RELATIONSHIPS ON MAP';legend.append(label);
    const seen=new Set();
    for(const c of links){const id=c.target_variable.id;if(seen.has(id))continue;seen.add(id);const row=document.createElement('span');const swatch=document.createElement('i');swatch.style.background=c.target_variable.color||'#b5d3c1';row.append(swatch,document.createTextNode(c.target_variable.name));legend.append(row);}
    const note=document.createElement('p');note.textContent='Moving dots show a possible temporal lead. A plain line has no resolved lead. Hover for evidence; click to pin.';legend.append(note);
  }
  function viewConnectionSeries(c){
    const dialog=document.createElement('dialog');dialog.className='connection-series-dialog';const h=document.createElement('h2');h.textContent='The two observation histories';
    const note=document.createElement('p');note.textContent=`${c.source_region.name} / ${c.source_variable.name} and ${c.target_region.name} / ${c.target_variable.name}. Separate axes retain each measurement's units. These curves do not establish a physical cause.`;
    const wrap=document.createElement('div');wrap.className='connection-series-chart';const canvas=document.createElement('canvas');wrap.append(canvas);
    const close=button('Close',()=>dialog.close());dialog.append(h,note,wrap,close);document.body.append(dialog);dialog.showModal();
    const datasets=[['source','y'],['target','yB']].map(([side,axis])=>({label:(side==='source'?'A / ':'B / ')+c[side+'_region'].name+' · '+c[side+'_variable'].name,data:(c[side+'_yearly']||[]).map(p=>({x:p.year,y:p.complete?p.value:null})),borderColor:side==='source'?'#68b8ff':'#e9c77a',borderDash:side==='target'?[6,4]:[],yAxisID:axis,spanGaps:false,pointRadius:3}));
    const graph=new Chart(canvas.getContext('2d'),{type:'line',data:{datasets},options:{responsive:true,maintainAspectRatio:false,parsing:false,scales:{x:{type:'linear',ticks:{callback:v=>String(Math.round(v))}},y:{title:{display:true,text:c.source_variable.unit}},yB:{position:'right',title:{display:true,text:c.target_variable.unit},grid:{drawOnChartArea:false}}},plugins:{legend:{labels:{color:'#cee3d4'}}}}});
    dialog.addEventListener('close',()=>{graph.destroy();dialog.remove();});close.focus();
  }
  function pinConnection(c){
    const id=[c.source_region.id,c.target_region.id,c.source_variable.id,c.target_variable.id].join('|');
    if(pinned.has(id)){pinned.get(id).scrollIntoView({block:'nearest'});return;}
    if(pinned.size>=4){const [key,card]=pinned.entries().next().value;card.remove();pinned.delete(key);}
    let dock=$('pinned-connections');if(!dock){dock=document.createElement('div');dock.id='pinned-connections';$('globe').append(dock);}
    const card=document.createElement('article');card.className='relationship-evidence';
    const close=button('×',()=>{card.remove();pinned.delete(id);});close.setAttribute('aria-label','Unpin relationship');
    const title=document.createElement('h3');title.textContent='A / '+c.source_region.name+' / '+c.source_variable.name+' ↔ B / '+c.target_region.name+' / '+c.target_variable.name;
    const evidence=document.createElement('p');evidence.textContent=`${c.direction==='inverse'?'Move in opposite directions':'Move in the same direction'} · relationship strength ${Number(c.r).toFixed(2)} on a −1 to +1 scale · ${c.lead_note}. Adjusted significance ${(c.p_adjusted??c.p)<.001?'<0.001':Number(c.p_adjusted??c.p).toFixed(3)}.`;
    const note=document.createElement('p');note.textContent='A unitless association between the tested series, not a change in measurement units, and not proof of a physical cause.';
    card.append(close,title,evidence,note,button('Compare these histories',()=>viewConnectionSeries(c)));dock.append(card);pinned.set(id,card);close.focus();
  }

  /* The static tour is retired; the interactive tutorial lives in onboarding.js. */
  function startTour(){
    if(window.TerraTour?.start){window.TerraTour.start();return;}
    setStatus('warn','The interactive tour could not load. Reload TerraTrend to try again.');
  }

  function init(){
    if(initialized)return;initialized=true;
    $('measurement-search').oninput=filterMeasurements;
    $('help-tour').onclick=startTour;
    $('measurement-picker').addEventListener('toggle',()=>{
      const open=$('measurement-picker').open;
      if(open){requestAnimationFrame(()=>scrollPanelTo('measurement-picker'));}
      announce('measurement-panel',{open});
    });
    for(const id of ['start','end'])$(id).addEventListener('input',refresh);
    for(const id of ['start','end'])$(id).addEventListener('change',()=>announce('dates-changed',{start:$('start').value,end:$('end').value}));
    $('add-comparison-area').onclick=()=>addComparisonArea();
    const techToggle=$('toggle-tech');
    if(techToggle)techToggle.onclick=()=>{
      const screen=$('analysis-screen');
      const on=!screen.classList.contains('show-tech');
      screen.classList.toggle('show-tech',on);
      techToggle.setAttribute('aria-expanded',String(on));
      techToggle.textContent=on?'Hide the statistics':'Show the statistics';
      const stats=$('pv-stats');if(stats)stats.hidden=!on;
    };
    $('saved-open').onclick=openSavedLibrary;
    $('saved-close').onclick=closeSavedLibrary;
    $('saved-search').oninput=()=>{clearTimeout(init._t);init._t=setTimeout(loadSaved,180);};
    $('saved-library').addEventListener('click',e=>{if(e.target===$('saved-library'))closeSavedLibrary();});
    $('ix-rerun').onclick=()=>open();
    const analysis=$('analysis-screen'),info=document.createElement('div');info.id='comparison-ready';info.className='comparison-ready';info.hidden=true;analysis.prepend(info);
    const history=document.createElement('label');history.id='saved-results-control';history.className='saved-results-control';history.hidden=true;history.textContent='COMPLETED INVESTIGATIONS THIS SESSION';const select=document.createElement('select');select.id='saved-results';select.onchange=()=>restoreResult(Number(select.value));history.append(select);analysis.prepend(history);
    const explainButton=button('Explain this result in plain language',()=>openExplanation(state.result?.saved_record_id||lastSavedId||null));
    explainButton.id='explain-result';explainButton.className='hud-btn ghost explain-result-button';
    analysis.prepend(explainButton);
    const explanation=document.createElement('details');explanation.className='statistics-guide';explanation.innerHTML='<summary>What do these numbers mean?</summary>'
      +'<p><b>Sen’s slope / trend per decade</b> is the estimated rate of change: how much the measurement typically changed over ten years, in that measurement’s own units. A value of +0.20 °C per decade means the fitted rate of change is one fifth of a degree Celsius per ten years (equivalently +0.020 °C per year).</p>'
      +'<p><b>Significant</b> means the trend passed the stated statistical test at the chosen threshold; it does not mean the change is large, important or dangerous. <b>p</b> is evidence against the “no trend” model, not the probability that the result is true. A <b>nonsignificant</b> result is not the same as “no data”.</p>'
      +'<p><b>Relationship strength</b> is a unitless score from −1 to +1: positive means two series tended to move together, negative means they moved oppositely. 0.58 is not 0.58 units of anything. Correlation is not causation, and a correlation alone cannot decide whether something is a concern.</p>'
      +'<p><b>Insufficient data</b> means coverage was inadequate for testing. <b>Variation across the area</b> (spatial grid) shows how the individual source cells differ inside the selected area; regional summaries and station records have no cells to show.</p>';
    analysis.prepend(explanation);
    const legend=document.createElement('aside');legend.id='connection-legend';legend.className='connection-legend';legend.hidden=true;$('globe').append(legend);
    for(const name of ['earthdata','appeears']){
      const form=$(name+'-connect-form'),badge=document.createElement('strong');badge.id=name+'-connected-badge';badge.className='connected-badge';form.before(badge);
      const reconnect=button('Update connection',()=>{form.hidden=false;form.dataset.editing='true';form.querySelector('input:not([type=checkbox])').focus();});reconnect.id=name+'-reconnect';form.before(reconnect);form.before($(name+'-disconnect'));
      form.addEventListener('submit',()=>{delete form.dataset.editing;});
    }
    refresh();
    if(window.TerraTour?.maybeWelcome)window.TerraTour.maybeWelcome();
  }
  window.TerraWorkspace={init,open,refresh,showIssues,saveResult,restoreResult,pinConnection,viewConnectionSeries,startTour,refreshConnections,requireComparison,openSavedLibrary,restoreSavedById,applySavedRecord,openExplanation,lastSavedId:()=>lastSavedId,scrollPanelTo};
})();
