/* Ask TerraTrend: bounded plans, existing data review, verified result wording. */
(function(){
  'use strict';
  const $=id=>document.getElementById(id);
  let recordId=null,busy=false,explainSeq=0,explainContext=null;
  let level='plain';try{level=localStorage.getItem('terratrend-reader-level')||'plain';}catch(_){}
  if(!['plain','student','researcher'].includes(level))level='plain';
  const node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;};
  const button=(text,action)=>{const b=node('button','toolbar-button',text);b.type='button';b.onclick=action;return b;};
  async function api(path,data){const r=await fetch(path,data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{});const body=await r.json();if(!r.ok)throw new Error(body.error||'This request could not be completed.');return body;}
  function setLevel(value){level=value;try{localStorage.setItem('terratrend-reader-level',value);}catch(_){}document.querySelectorAll('.ai-reader-select').forEach(s=>s.value=value);}
  function readerPicker(onchange){const label=node('label','ai-reader-label','Reading level');const select=document.createElement('select');select.className='ai-reader-select';select.setAttribute('aria-label','Explanation reading level');for(const [id,name] of [['plain','Plain'],['student','Student'],['researcher','Researcher']]){const option=node('option',null,name);option.value=id;select.append(option);}select.value=level;select.onchange=()=>{setLevel(select.value);onchange?.();};label.append(select);return label;}
  function message(text,role='assistant'){const card=node('article','assistant-message '+role);card.append(node('strong',null,role==='user'?'YOU':'TERRATREND'));card.append(node('p',null,text));$('assistant-log').append(card);card.scrollIntoView({block:'nearest'});return card;}
  function context(){
    const screen=investigation.screen;
    const activeId=screen==='events'?window.TerraEvents?.state.payloads.get(window.TerraEvents?.state.activeId)?.saved_record_id:screen==='interconnect'?ixState.recordId:state.result?.saved_record_id;
    return {region:typeof currentRegion==='function'?currentRegion()?.id:null,compare_region:typeof validComparisonArea==='function'?validComparisonArea()?.id:null,variables:typeof state!=='undefined'?state.selected.slice():[],start:Number($('start')?.value)||2016,end:Number($('end')?.value)||2024,record_id:activeId||(screen==='events'?null:recordId),has_result:!!state.result};
  }
  function connectionSettings(){showInvestigationScreen('sources');$('assistant-panel').hidden=true;$('assistant-open').setAttribute('aria-expanded','false');$('groq-card').scrollIntoView({block:'center'});$('groq-api-key')?.focus();}
  function open(){const panel=$('assistant-panel');panel.hidden=false;$('assistant-open').setAttribute('aria-expanded','true');$('assistant-message').focus();}
  function close(){ $('assistant-panel').hidden=true;$('assistant-open').setAttribute('aria-expanded','false');$('assistant-open').focus();}
  async function send(event){event?.preventDefault();if(busy)return;const input=$('assistant-message'),text=input.value.trim();if(!text)return;if(/gsk_[\w-]+|(?:api[_-]?key|password|token)\s*[=:]/i.test(text)){input.value='';message('Keep keys out of chat. Use Connect Groq in Data & Methods.');return;}input.value='';message(text,'user');busy=true;$('assistant-send').disabled=true;$('assistant-status').textContent='Understanding your request…';
    try{const reply=await api('/api/assistant',{message:text,context:context(),reader_level:level});
      if(reply.kind==='plan'){
        const card=message(reply.title);card.classList.add('assistant-plan');
        if(reply.draft.operation!=='scan')card.append(node('p',null,reply.measurements.join(' · ')));
        card.append(node('p',null,reply.message));
        const run=button('Review data & run',async()=>{run.disabled=true;await runDraft(reply.draft,card);run.disabled=false;});card.append(run);
        if(reply.parser==='local-fallback')card.append(node('p','ai-evidence-note','Groq is unavailable; this familiar request was understood locally.'));
      }else if(reply.kind==='answer'){
        recordId=reply.record_id;message(reply.message);
        if(!reply.explanation?.available)message('This answer uses the verified local explanation.');
      }else if(reply.kind==='events')message(reply.message).append(button('Open Events',()=>showInvestigationScreen('events')));
      else {const card=message(reply.message);if(reply.measurements?.length){const details=node('details');details.append(node('summary',null,'Available measurements'));const list=node('ul');for(const name of reply.measurements)list.append(node('li',null,name));details.append(list);card.append(details);}}
    }catch(error){message(error.message);}finally{busy=false;$('assistant-send').disabled=false;$('assistant-status').textContent='';}
  }
  async function prepareDraft(draft){
    const ids=[draft.region,draft.compare_region,...(draft.target_regions||[])].filter(Boolean);
    const aId=draft.region;
    let meta=state.catalog.regions.find(r=>r.id===aId)||investigation.featureStore.get(aId)?.properties;
    const type=aId.split(':')[0];
    if(!meta||investigation.level!==type){await setGeographicLevel(type==='focus'?'preset':type,meta?.parent||'');meta=state.catalog.regions.find(r=>r.id===aId)||investigation.featureStore.get(aId)?.properties;}
    if(!meta)throw new Error('Choose this region on the map first, then ask again.');
    const lookup=id=>state.catalog.regions.find(r=>r.id===id)||investigation.featureStore.get(id)?.properties;
    const bId=draft.compare_region||draft.target_regions?.[0];
    if(bId&&!lookup(bId))throw new Error('Choose the comparison region on the map first.');
    investigation.areas.a=meta;investigation.areas.b=bId?lookup(bId):null;
    state.compareMode=!!bId;investigation.slot='a';investigation.provider='auto';
    state.selected=draft.operation==='scan'?[]:(draft.relationship_variables||draft.variables).slice();state.activeVarIdx=0;
    $('start').value=draft.start;$('end').value=draft.end;$('science-provider').value=$('methods-provider').value='auto';
    $('ix-remote-search').checked=draft.relationship_scope==='remote';
    setAreaOptions(investigation.features.map(f=>f.properties),aId,bId||'');
    prepareInvestigation(false);renderVarList();refreshSelection();window.TerraWorkspace?.refresh?.();showInvestigationScreen('map');
  }
  async function runDraft(draft,card){
    if(investigation.job){message('An investigation is already running. Let it finish or cancel it with the existing progress control before starting another.');return;}
    try{
      await prepareDraft(draft);
      $('assistant-status').textContent='Reviewing the request…';
      const result=await runInvestigationJob(structuredClone(draft),'Running your requested investigation');
      if(!result){message('The request was not started, or your selection changed.');return;}
      recordId=result.saved_record_id||null;
      if(recordId){const restored=await window.TerraWorkspace.restoreSavedById(recordId);if(!restored)throw new Error('The calculation completed, but its saved result could not be opened. Use Saved investigations to retry.');}
      else if(draft.operation==='analyze'){state.result=result;investigation.resultKey=investigationContextKey();render();window.TerraWorkspace.saveResult(result);}
      else if(draft.operation==='scan'){renderScan(result.scanned,result.scanned.length);showModal($('scan-modal'));}
      else{ixState.local=result.local;ixState.global=result.global;showInvestigationScreen('interconnect');renderIxHero(result.local,result.global);renderIxLocal(result.local,draft.variables[0]);renderIxGlobal(result.global,draft.variables[0]);}
      const explanation=await api('/api/explain',{...(recordId?{record_id:recordId}:{result,kind:draft.operation==='scan'?'discovery':draft.operation==='interconnections'?'relationships':result.compare?'compare':'analysis'}),reader_level:level});
      message(explanation.live||explanation.answer||explanation.summary.headline);
      const done=message('The findings above come from the completed analysis. You can open the evidence or ask a follow-up.');
      done.append(button('Open result',()=>{if(recordId)window.TerraWorkspace.restoreSavedById(recordId);else showInvestigationScreen('analysis');}));
      if(draft.operation==='scan')done.append(node('p',null,'Choose a measurement in the discovery table to inspect its history, or ask to link two named measurements.'));
      card.append(node('p','ai-evidence-note',recordId?'Completed and available in Saved investigations.':'Completed. Saving was unavailable; keep this result open.'));
    }catch(error){message(error.message);}finally{$('assistant-status').textContent='';$('work-progress').hidden=true;}
  }
  function renderExplanation(body,data){
    body.replaceChildren();const summary=data.summary||{};
    if(data.live){const live=node('div','explain-live');live.append(node('strong',null,'AI-guided explanation'),node('p',null,data.live));body.append(live);}
    else body.append(node('p','explain-provider',data.provider?'AI wording is unavailable for this request. Showing the explanation from the verified evidence.':'Groq is not connected. This explanation uses the verified evidence and works without AI.'));
    body.append(node('p','explain-headline',summary.headline));
    const details=node('details','explain-details');details.open=!data.live;details.append(node('summary',null,'Verified evidence and caveats'));
    const list=node('ul');for(const line of summary.sentences||[])list.append(node('li',null,line));details.append(list);
    for(const line of summary.caveats||[])details.append(node('p',null,line));body.append(details);
    if(summary.sources?.length)body.append(node('p','ai-evidence-note','Sources: '+summary.sources.join(' · ')));
    const audit=node('details','ai-evidence-note');audit.append(node('summary',null,'Explanation details'),node('p',null,'Reading level: '+data.reader_level+' · Explanation version: '+data.explainer_version+'. Stored with the evidence fingerprint.'));body.append(audit);
  }
  async function loadExplanation(question=null){
    const seq=++explainSeq,body=$('ai-explain-body');body.textContent='Reading the verified result…';
    try{const reply=await api('/api/explain',{...explainContext,reader_level:level,...(question?{question}:{})});if(seq!==explainSeq)return;renderExplanation(body,reply);if(question)body.prepend(node('p','explain-followup',reply.live||reply.answer));}
    catch(error){if(seq===explainSeq)body.textContent=error.message;}
  }
  function explain(id,extra=null){
    let dialog=$('ai-explain-dialog');
    if(!dialog){dialog=node('dialog','explain-dialog');dialog.id='ai-explain-dialog';
      const head=node('div','explain-head');head.append(node('h2',null,'Understand this result'),button('Close',()=>dialog.close()));
      const body=node('div','explain-body');body.id='ai-explain-body';body.setAttribute('aria-live','polite');
      const form=node('form','assistant-question'),label=node('label',null,'Ask about this result');label.htmlFor='explain-question';
      const input=node('textarea');input.id='explain-question';input.rows=2;input.maxLength=2000;input.placeholder='What does significance mean? What caused this change?';
      const submit=button('Ask about this result',null);submit.type='submit';form.append(label,input,submit);form.onsubmit=e=>{e.preventDefault();const question=input.value.trim();if(!question)return;if(/gsk_[\w-]+|api[_-]?key\s*[=:]/i.test(question)){input.value='';body.textContent='Use the local Groq connection form for keys.';return;}loadExplanation(question);};
      dialog.append(head,readerPicker(()=>loadExplanation()),body,form);document.body.append(dialog);dialog.addEventListener('close',()=>{explainSeq++;});
    }
    explainContext=extra|| (id?{record_id:id}:{result:structuredClone(state.result),kind:state.result?.compare?'compare':'analysis'});
    if(id)recordId=id;
    if(!dialog.open)dialog.showModal();loadExplanation();
  }
  function updateConnection(info){
    const connected=info.configured;$('groq-badge').textContent=connected?'CONNECTED · '+info.model+(info.remembered?' · REMEMBERED':' · THIS SESSION'):'Optional · local explanations are available';
    $('groq-connect-form').hidden=connected;$('groq-update').hidden=!connected;$('groq-forget').hidden=!connected;
    $('groq-status').textContent=connected?'Ask can now use Groq to understand requests and select verified explanations.':'Connect Groq for AI assistance. Familiar analysis commands and local explanations also work without it.';
    $('assistant-connection').textContent=connected?'Groq connected':'Local mode · Connect Groq in Data & Methods';
  }
  async function refreshConnection(){try{updateConnection(await api('/api/ai/connection'));}catch(_){$('groq-status').textContent='Restart the updated preview to enable the Groq connection.';}}
  function init(){
    const panel=node('aside','assistant-panel');panel.id='assistant-panel';panel.hidden=true;panel.setAttribute('aria-label','Ask TerraTrend');
    const head=node('div','assistant-head');head.append(node('h2',null,'Ask TerraTrend'),button('Close',close));
    const intro=node('p','assistant-intro','Ask a question, review the data request, then explore the measured results.');
    const connection=node('p','ai-evidence-note');connection.id='assistant-connection';connection.textContent='Checking AI connection…';
    const log=node('div','assistant-log');log.id='assistant-log';log.setAttribute('role','log');log.setAttribute('aria-live','polite');
    const form=node('form','assistant-form');const label=node('label',null,'Your question');label.htmlFor='assistant-message';const input=node('textarea');input.id='assistant-message';input.rows=3;input.maxLength=2000;input.placeholder='Scan all variables in Ghana from 2016 to 2024';
    const controls=node('div','assistant-controls');const submitButton=button('Send',null);submitButton.type='submit';submitButton.id='assistant-send';controls.append(button('AI connection',connectionSettings),submitButton);form.append(label,input,controls);form.onsubmit=send;
    const status=node('p','assistant-status');status.id='assistant-status';status.setAttribute('role','status');
    panel.append(head,intro,connection,readerPicker(),log,form,status);document.body.append(panel);$('assistant-open').onclick=()=>panel.hidden?open():close();panel.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();close();}});
    const card=node('article','method-card groq-card');card.id='groq-card';card.innerHTML='<span class="eyebrow">OPTIONAL AI ASSISTANT</span><h3>Connect Groq</h3><strong id="groq-badge" class="groq-badge"></strong><p class="groq-privacy">When you ask the assistant or request an AI explanation, your question and a small verified result summary are sent to Groq. NASA keys and raw observation files stay local. No AI request is sent just by changing pages.</p><form id="groq-connect-form"><label for="groq-api-key">Groq API key</label><input id="groq-api-key" type="password" autocomplete="off" required placeholder="Enter your key here, not in chat"><label for="groq-model">Text model</label><select id="groq-model"><option value="openai/gpt-oss-20b">GPT OSS 20B</option><option value="openai/gpt-oss-120b">GPT OSS 120B</option><option value="llama-3.3-70b-versatile">Llama 3.3 70B</option><option value="llama-3.1-8b-instant">Llama 3.1 8B</option></select><label class="remember-ai"><input id="groq-remember" type="checkbox">Remember this connection privately on this computer</label><button class="toolbar-button" type="submit" id="groq-connect">Connect Groq</button></form><p id="groq-status" role="status"></p>';
    const actions=node('div','assistant-controls');const update=button('Update connection',()=>{$('groq-connect-form').hidden=false;$('groq-api-key').focus();});update.id='groq-update';const forget=button('Forget Groq connection',async()=>{try{updateConnection(await api('/api/ai/connection',{disconnect:true}));}catch(e){$('groq-status').textContent=e.message;}});forget.id='groq-forget';actions.append(update,forget);card.append(actions);$('data-methods-screen').querySelector('.methods-grid').prepend(card);
    $('groq-connect-form').onsubmit=async e=>{e.preventDefault();const key=$('groq-api-key').value;$('groq-api-key').value='';$('groq-connect').disabled=true;$('groq-status').textContent='Checking your key with Groq…';try{updateConnection(await api('/api/ai/connection',{api_key:key,model:$('groq-model').value,remember:$('groq-remember').checked}));}catch(error){$('groq-status').textContent=error.message;}finally{$('groq-connect').disabled=false;}};
    document.addEventListener('terratrend:action',event=>{const d=event.detail||{};if(['result-restored','result-saved'].includes(d.action)&&typeof d.resultId==='string')recordId=d.resultId;});
    refreshConnection();
  }
  window.TerraAssistant={open,close,send,explain,runDraft,settings:connectionSettings,refreshConnection};
  init();
})();
