/* Controller unit tests: no browser, network or WebGL dependency. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../frontend/workflow.js'), 'utf8');

function context(fetch) {
  const elements = new Map();
  function element() {return {value:'',hidden:true,textContent:'',style:{},dataset:{},children:[],classList:{toggle(){},add(){},remove(){}},replaceChildren(){this.children=[];},append(...values){this.children.push(...values);},setAttribute(){},focus(){},getContext(){return {};}};}
  const get = id => {if(!elements.has(id))elements.set(id,element());return elements.get(id);};
  get('region').value='country:gha';get('compare-region').value='country:nga';get('start').value='2000';get('end').value='2024';
  const noOp=()=>{};
  const ctx={console,URLSearchParams,Map,Set,Promise,AbortController,setTimeout:fn=>setTimeout(fn,0),clearTimeout,requestAnimationFrame:noOp,
    document:{body:{dataset:{}},querySelectorAll:()=>[],createElement:element},
    window:{TerraLegacy:{render:noOp,clearResults:noOp,renderSatellite:noOp,renderDataModal:noOp},TerraSelection:require('../frontend/selection-geometry.js'),TerraDataReview:{review:async()=>true,cancel:noOp}},
    $:get,MAX_VARS:3,ixState:{},setStatus:noOp,renderRegionCard:noOp,renderVarList:noOp,flashHint:noOp,closeInterconnectScreen:noOp,esc:String,
    C:{fall:'#0ff'},num:(v,n)=>Number(v).toFixed(n),
    state:{selected:['T2M'],compareMode:false,analyzeSeq:0,activeVarIdx:0,mode:'yearly',catalog:{variables:[],regions:[{id:'country:gha',name:'Ghana'},{id:'country:nga',name:'Nigeria'}]}},fetch,
    Chart:function(canvas,config){ctx.chartConfig=config;this.destroy=noOp;},chart:null};
  vm.createContext(ctx);vm.runInContext(source,ctx);vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../frontend/selection-tools.js'),'utf8'),ctx);vm.runInContext('investigation.provider="project-cache"',ctx);return {ctx,get,run:code=>vm.runInContext(code,ctx)};
}
function response(data) {return {ok:true,json:async()=>data};}

test('moving among result pages never changes the investigation or discards its result',()=>{
  const {ctx,run}=context(async()=>response({}));
  const completed={region:{id:'country:gha'},series:[]};ctx.state.result=completed;
  run('showInvestigationScreen("compare");showInvestigationScreen("sources");showInvestigationScreen("analysis");showInvestigationScreen("map")');
  assert.equal(ctx.state.result,completed);assert.equal(ctx.state.compareMode,false);
});

test('editing an investigation retains its completed evidence with its original context',()=>{
  const {ctx,get,run}=context(async()=>response({}));
  const completed={region:{id:'country:gha',name:'Ghana'},series:[]};ctx.state.result=completed;
  get('end').value='2023';run('prepareInvestigation()');
  assert.equal(ctx.state.result,completed);
  assert.match(get('analysis-context').textContent,/previous|completed/i);
});

test('remote relationships use explicitly selected B rather than unrelated countries',()=>{
  const {ctx,get,run}=context(async()=>response({}));ctx.state.compareMode=true;get('ix-remote-search').checked=true;
  ctx.state.selected=['T2M','QV2M'];ctx.state.catalog.variables=[{id:'T2M'},{id:'QV2M'}];
  const spec=run('jobSpec("interconnections")');
  assert.deepEqual(Array.from(spec.target_regions||[]),['country:nga']);
});

test('chart tooltip explains the observation distance from its actual calendar trend',()=>{
  const {ctx,run}=context(async()=>response({}));
  ctx.state.result={region:{name:'Ghana'},series:[{variable:{name:'Temperature',unit:'°C',color:'#fff'},yearly_timeseries:[{year:2000,value:10,complete:true},{year:2002,value:13,complete:true}],overall:{ok:true,slope:1,intercept:-1990}}]};
  run('drawChart()');
  const label=ctx.chartConfig.options.plugins.tooltip.callbacks.label({dataset:ctx.chartConfig.data.datasets[0],parsed:{x:2002,y:13}});
  assert.match(String(label),/1\.000 °C above trend/);
});

test('preset mode changes the displayed layer while preserving independent selected areas',async()=>{
  const {ctx,run}=context(async()=>response({}));ctx.levelCalls=[];
  run('setGeographicLevel=async(level,scope)=>{levelCalls.push([level,scope]);investigation.level=level;investigation.scope=scope;}');
  const before=run('currentRegion().id');
  await run('togglePresetRegions()');
  assert.equal(ctx.levelCalls[0][0],'preset');assert.equal(run('currentRegion().id'),before);
  await run('togglePresetRegions()');assert.equal(ctx.levelCalls[1][0],'continent');
});

test('linked relationship request retains chosen measurements and defaults to local only',()=>{
  const {ctx,run}=context(async()=>response({}));
  ctx.state.selected=['GWETROOT','NDVI'];ctx.state.catalog.variables=[{id:'GWETROOT'},{id:'NDVI'}];
  run('investigation.provider="multi-source";investigation.providers=[{id:"multi-source",variables:["GWETROOT","NDVI"]}]');
  const spec=run('jobSpec("interconnections")');
  assert.equal(spec.relationship_scope,'local');
  assert.deepEqual(Array.from(spec.relationship_variables),['GWETROOT','NDVI']);
  assert.equal(spec.target_regions,undefined);
});

test('Giovanni availability filters measurements and never accepts a country as a rectangle',()=>{
  const {ctx,run}=context(async()=>response({}));
  ctx.state.catalog.variables=[{id:'T2M'},{id:'QV2M'},{id:'GWETROOT'}];
  run('investigation.provider="nasa-giovanni";investigation.nasa={configured:true,reader_installed:true};investigation.providers=[{id:"nasa-giovanni",variables:["T2M","QV2M"]}]');
  assert.equal(run('variableSourceAvailable("GWETROOT")'),false);
  assert.throws(()=>run('jobSpec("analyze")'),/rectangle|bounds/i);
});

test('Giovanni accepts rectangular lassos and local relationships but blocks non-preset layers and remote searches',()=>{
  const {ctx,run}=context(async()=>response({}));
  const feature=ctx.window.TerraSelection.bounds(-2,6,0,8);
  ctx.box=feature;ctx.state.catalog.custom_selections=true;ctx.state.catalog.variables=[{id:'T2M'},{id:'QV2M'}];
  run('investigation.provider="nasa-giovanni";investigation.nasa={configured:true,reader_installed:true};investigation.providers=[{id:"nasa-giovanni",variables:["T2M","QV2M"]}];investigation.areas.a={...box.properties,id:"custom:box"};investigation.featureStore.set("custom:box",box)');
  assert.equal(run('jobSpec("analyze").provider'),'nasa-giovanni');
  assert.throws(()=>run('jobSpec("overview")'),/native|rectangle/i);
  assert.equal(run('jobSpec("interconnections").relationship_scope'),'local');
});

test('Giovanni can prepare every displayed preset rectangle through the explicit layer action',()=>{
  const {ctx,run}=context(async()=>response({}));const box=ctx.window.TerraSelection.bounds(-2,6,0,8);
  ctx.box=box;ctx.state.catalog.variables=[{id:'T2M'}];
  run('investigation.provider="nasa-giovanni";investigation.nasa={configured:true,reader_installed:true};investigation.providers=[{id:"nasa-giovanni",variables:["T2M"]}];investigation.level="preset";investigation.features=[{...box,id:"focus:one",properties:{...box.properties,id:"focus:one",level:"preset"}}]');
  assert.equal(run('jobSpec("overview").operation'),'overview');
});

test('area-only Analyze opens discovery rather than requiring a variable', async()=>{
  const {ctx,run}=context(async()=>response({}));
  ctx.state.selected=[];ctx.discoveryOpened=false;
  run('scanAll=async()=>{discoveryOpened=true;}');
  await run('analyze()');
  assert.equal(ctx.discoveryOpened,true);
});

test('discovery distinguishes a nonsignificant result, missing observations and source failure',()=>{
  const {ctx,get,run}=context(async()=>response({}));
  const app=fs.readFileSync(require('node:path').join(__dirname,'../frontend/app.js'),'utf8');
  run(app.slice(app.indexOf('function rankRows('),app.indexOf('function closeScan(')));
  get('scan-table').querySelectorAll=()=>[];
  ctx.rows=[{id:'a',name:'Nonsignificant',ok:true,significant:false,p:.2,direction:'rising',slope_decade:.1,tau:.2},
    {id:'b',name:'Missing observations',ok:false},
    {id:'c',name:'Unavailable source',ok:false,error:'Service could not be reached'}];
  run('renderScan(rows,rows.length)');
  const html=get('scan-table').innerHTML;
  assert.match(html,/NOT SIGNIFICANT/);assert.match(html,/INSUFFICIENT DATA/);assert.match(html,/SOURCE ERROR/);
  assert.doesNotMatch(html,/>STABLE</);
});

test('opening a discovery row prepares its measurement and shows the Analysis screen',()=>{
  const {ctx,run}=context(async()=>response({}));
  ctx.state.selected=[];ctx.navigation=[];
  run('hideModal=()=>{};showInvestigationScreen=screen=>navigation.push(screen);analyze=()=>navigation.push("review-analysis")');
  run('openFromScan("T2M")');
  assert.deepEqual(Array.from(ctx.state.selected),['T2M']);
  assert.deepEqual(ctx.navigation,['analysis','review-analysis']);
  assert.equal(run('currentRegion().id'),'country:gha');
});

test('a discovery specification includes supported fields without requiring comparison B', ()=>{
  const {ctx,get,run}=context(async()=>response({}));
  ctx.state.selected=[];ctx.state.compareMode=true;get('compare-region').value='';
  ctx.state.catalog.variables=[{id:'T2M'},{id:'GWETROOT'},{id:'WS2M'}];
  run('investigation.provider="nasa-merra2";investigation.nasa={configured:true,reader_installed:true,variables:["T2M","GWETROOT"]}');
  const spec=run('jobSpec("scan")');
  assert.deepEqual(Array.from(spec.variables),['T2M','GWETROOT']);
  assert.equal(spec.region,'country:gha');
  assert.equal(spec.compare_region,undefined);
});

test('declining the data review submits no scientific request', async()=>{
  const calls=[];
  const {ctx,run}=context(async url=>{calls.push(url);return response({id:'job',status:'complete',result:{}});});
  ctx.window.TerraDataReview={review:async()=>false};
  assert.equal(await run('runInvestigationJob(jobSpec("analyze"), "Testing")'),null);
  assert.deepEqual(calls,[]);
});

test('a selection changed during data review cannot submit the old area', async()=>{
  const calls=[];let finishReview;
  const {ctx,get,run}=context(async url=>{calls.push(url);return response({id:'job',status:'complete',result:{}});});
  ctx.window.TerraDataReview={review:()=>new Promise(resolve=>{finishReview=resolve;})};
  const pending=run('runInvestigationJob(jobSpec("analyze"), "Testing")');
  await Promise.resolve(); // The download review completes before the job is submitted.
  get('region').value='country:nga';run('prepareInvestigation(false)');
  if(finishReview)finishReview(true);
  assert.equal(await pending,null);
  assert.deepEqual(calls,[]);
});

test('a completed response for an old selection is cancelled and never accepted',async()=>{
  let finish;
  const calls=[];
  const {run,get}=context((url)=>{calls.push(url);if(url.endsWith('/cancel'))return Promise.resolve(response({status:'cancelled'}));return new Promise(resolve=>{finish=resolve;});});
  const pending=run('runInvestigationJob(jobSpec("analyze"), "Testing")');
  await new Promise(resolve=>setImmediate(resolve)); // Flush the cross-context review before the response race.
  get('region').value='country:nga';run('prepareInvestigation(false)');
  finish(response({id:'old',status:'complete',result:{region:{id:'country:gha'}}}));
  assert.equal(await pending,null);assert.ok(calls.includes('/api/jobs/old/cancel'));
});

test('selection changes while cancelling the previous job do not launch the old spec',async()=>{
  let finishCancel;const calls=[];
  const {run,get}=context((url)=>{calls.push(url);return new Promise(resolve=>{finishCancel=resolve;});});
  run('investigation.job="previous"');
  const pending=run('runInvestigationJob(jobSpec("analyze"), "Testing")');
  get('region').value='country:nga';run('prepareInvestigation(false)');
  finishCancel(response({status:'cancelled'}));
  assert.equal(await pending,null);assert.deepEqual(calls,['/api/jobs/previous/cancel']);
});

test('a matching completed result is returned without substituting numbers',async()=>{
  const result={series:[],region:{id:'country:gha'}};
  const {run}=context(async()=>response({id:'current',status:'complete',result}));
  assert.equal(await run('runInvestigationJob(jobSpec("analyze"), "Testing")'),result);
});

test('an A-only request never demands area B, and a comparison needs two different units',()=>{
  const {run,get}=context(async()=>response({}));
  // Comparison armed but no B chosen: the A-only request must still be valid.
  run('state.compareMode=true');get('compare-region').value='';
  assert.equal(run('resolveRunAction().kind'),'need-b');
  const aOnly=run('jobSpec("analyze",{compare:false})');
  assert.equal(aOnly.region,'country:gha');
  assert.equal(aOnly.compare_region,undefined);
  // An explicit comparison without a distinct B is still refused.
  assert.throws(()=>run('jobSpec("analyze",{compare:true})'),/comparison area B/);
  get('compare-region').value='country:gha';
  assert.throws(()=>run('jobSpec("analyze",{compare:true})'),/comparison area B/);
});

test('chart trend lines use actual calendar coordinates across a missing year',()=>{
  const {run,ctx}=context(async()=>response({}));
  ctx.state.result={region:{name:'Ghana'},series:[{variable:{name:'Temperature',unit:'°C',color:'#fff'},yearly_timeseries:[{year:2000,value:10,complete:true},{year:2002,value:12,complete:true}],overall:{ok:true,slope:1,intercept:-1990}}]};
  run('drawChart()');
  const data=ctx.chartConfig.data.datasets;
  assert.deepEqual(Array.from(data[0].data,p=>p.x),[2000,2002]);
  assert.deepEqual(Array.from(data[1].data,p=>p.y),[10,12]);
});

test('expanded comparison uses each area’s fitted calendar intercept',()=>{
  const {ctx,get,run}=context(async()=>response({}));
  get('chart-expanded').getContext=()=>({createLinearGradient:()=>({addColorStop(){}})});
  ctx.$=id=>id==='expanded-trendline'?null:get(id);
  ctx.expandedChart=null;ctx.hexA=()=> '#fff';ctx.updateZoomBadge=()=>{};
  ctx.state.expandedMode='yearly';ctx.state.expandedVarIdx=0;
  const block=(values,intercept)=>({variable:{name:'Temperature',unit:'°C',color:'#fff'},yearly_timeseries:[2000,2002,2004].map((year,i)=>({year,value:values[i],complete:true})),overall:{ok:true,slope:1,intercept}});
  ctx.state.result={start:2000,region:{name:'Ghana'},series:[block([10,13,14],-1990)],compare:{region:{name:'Nigeria'},series:[block([20,30,24],-1980)]}};
  const app=fs.readFileSync(require('node:path').join(__dirname,'../frontend/app.js'),'utf8');
  const start=app.indexOf('function drawExpandedChart()');
  run(app.slice(start,app.indexOf('\nfunction ',start+10)));
  run('drawExpandedChart()');
  const trend=ctx.chartConfig.data.datasets.find(d=>d.$side==='b'&&d.$kind==='trend');
  assert.ok(trend,'area B must have its own fitted trend series');
  assert.match(String(trend.label),/B \/ Nigeria/);
  assert.match(String(trend.label),/fitted trend/);
  assert.equal(trend.borderColor,'#e9c77a');
  assert.deepEqual(Array.from(trend.borderDash),[2,3]);
  assert.deepEqual(Array.from(trend.data,p=>p.x),[2000,2002,2004]);
  assert.deepEqual(Array.from(trend.data,p=>p.y),[20,22,24]);
  // Area A keeps its own identity colour and dash so the two areas never merge.
  const trendA=ctx.chartConfig.data.datasets.find(d=>d.$side==='a'&&d.$kind==='trend');
  assert.equal(trendA.borderColor,'#68b8ff');
  assert.deepEqual(Array.from(trendA.borderDash),[7,4]);
});

test('A and B use independent methods and survive a boundary-level change',async()=>{
  const {run,ctx}=context(async()=>response({}));ctx.state.catalog.custom_selections=true;
  run(`assignSelectionArea('a',{id:'continent:africa',properties:{id:'continent:africa',name:'Africa',level:'continent'}})`);
  run(`investigation.slot='b';previewSelection(window.TerraSelection.shape('circle',[11,2],100))`);
  await run('applySelectionDraft()');
  const b=run('currentCompareRegion().id');
  run(`investigation.level='country';setAreaOptions(state.catalog.regions.filter(r=>r.id.startsWith('country:')))`);
  assert.equal(run('currentRegion().id'),'continent:africa');assert.equal(run('currentCompareRegion().id'),b);
  const spec=run('jobSpec("analyze")');assert.equal(spec.region,'continent:africa');assert.equal(spec.compare_region,b);assert.equal(spec.custom_areas.length,1);
});

test('picking A explicitly does not redirect the next click to B',()=>{
  const {run,get}=context(async()=>response({}));get('region').value='';get('compare-region').value='';
  run(`state.compareMode=true;activateSelectionSlot('a');selectMapFeature({id:'country:gha',properties:{id:'country:gha',name:'Ghana',level:'country'}})`);
  assert.equal(run('investigation.slot'),'a');assert.equal(run('currentRegion().id'),'country:gha');
  run(`activateSelectionSlot('b');selectMapFeature({id:'country:nga',properties:{id:'country:nga',name:'Nigeria',level:'country'}})`);
  assert.equal(run('currentRegion().id'),'country:gha');assert.equal(run('currentCompareRegion().id'),'country:nga');
});

test('a new shape method does not report the previous area as its preview',async()=>{
  const {run,get}=context(async()=>response({}));
  const feature=await run(`window.TerraSelection.identify(window.TerraSelection.bounds(-3,4,1,11))`);
  run('investigation.slot="b"');
  const json=JSON.stringify(feature);
  run(`assignSelectionArea('b',${json});setSelectionTool('square');selectionTools.size=120;refreshSelectionTools()`);
  assert.equal(get('selection-shape-area').textContent,'Place a centre dot');
});

test('selection toolbar reopens after X and opening it alone never opens settings',()=>{
  const {run,get}=context(async()=>response({}));
  run('toggleSelectionDock(true)');assert.equal(get('selection-dock-tools').hidden,false);assert.equal(get('selection-workbench').hidden,true);
  run('setSelectionTool("lasso")');assert.equal(get('selection-workbench').hidden,false);
  run('closeSelectionTools()');assert.equal(get('selection-workbench').hidden,true);assert.equal(get('selection-dock-tools').hidden,false);
  run('toggleSelectionDock(false);toggleSelectionDock(true)');assert.equal(get('selection-workbench').hidden,true);assert.equal(get('selection-dock-tools').hidden,false);
});
test('clicking the selected primary area deselects A while preserving B',()=>{
  const {run}=context(async()=>response({}));
  run(`state.compareMode=true;investigation.slot='a';selectMapFeature({id:'country:gha',properties:{id:'country:gha',name:'Ghana'}})`);
  assert.equal(run('currentRegion()'),null);assert.equal(run('currentCompareRegion().id'),'country:nga');
  run(`investigation.slot='b';selectMapFeature({id:'country:nga',properties:{id:'country:nga',name:'Nigeria'}})`);
  assert.equal(run('currentCompareRegion()'),null);
});
test('a slower country boundary response cannot replace a more recent layer',async()=>{
  let finishOld;const signals=[];
  const feature={id:'country:egy',properties:{id:'country:egy',name:'Egypt',level:'country'}};
  const {run,get}=context((url,options)=>{signals.push(options.signal);return url.includes('level=region')?new Promise(resolve=>{finishOld=resolve;}):Promise.resolve(response({features:[feature]}));});
  const old=run('setGeographicLevel("region","country:gha")');
  await run('setGeographicLevel("country","")');
  finishOld(response({features:[]}));await old;
  assert.equal(signals[0].aborted,true);assert.equal(run('investigation.features[0].id'),'country:egy');assert.equal(get('boundary-loading').hidden,true);
});
test('missing NASA authorization is reported before submitting an analysis job',()=>{
  const {run}=context(async()=>response({}));run('investigation.provider="nasa-merra2";investigation.nasa={configured:false,variables:["T2M"],reader_installed:true}');
  assert.throws(()=>run('jobSpec("analyze")'),/Connect Earthdata/);
});
test('unsupported automatic fields are named instead of substituted',()=>{
  const {run,ctx}=context(async()=>response({}));ctx.state.selected=['WS2M'];ctx.state.catalog.variables=[{id:'WS2M',name:'Wind Speed'}];
  run('investigation.provider="nasa-merra2";investigation.nasa={configured:true,reader_installed:true,variables:["T2M"]}');
  assert.throws(()=>run('jobSpec("analyze")'),/Wind Speed/);
});

test('an old API preserves the automatic source instead of silently using the cache',async()=>{
  const calls=[];
  const {run,get}=context(async url=>{calls.push(url);return response({providers:[{id:'project-cache',name:'Existing cache',description:'Sparse local files'}]});});
  run('investigation.provider="nasa-merra2"');assert.equal(await run('loadProviders()'),true);
  assert.equal(run('investigation.provider'),'nasa-merra2');assert.equal(run('sourceReadiness().code'),'server-update');
  assert.equal(get('data-through').textContent,'RESTART SERVER');assert.equal(get('earthdata-connect').disabled,true);
  assert.equal(get('nasa-restart-help').hidden,false);assert.ok(get('science-provider').children.some(o=>o.value==='project-cache'));
  for(const action of ['analyze()','analyzeLayer()','scanAll()','loadInterconnectData(currentRegion(),"T2M")'])await run(action);
  assert.deepEqual(calls,['/api/data-sources']);assert.equal(run('investigation.screen'),'sources');assert.equal(run('currentRegion().id'),'country:gha');
});
test('an explicitly chosen legacy cache remains usable on an old server',async()=>{
  const {run,get}=context(async()=>response({providers:[{id:'project-cache',name:'Existing cache',description:'Sparse local files'}]}));
  await run('loadProviders("project-cache")');
  assert.equal(run('investigation.provider'),'project-cache');assert.equal(run('jobSpec("analyze").provider'),'project-cache');
  assert.equal(get('data-through').textContent,'CACHED');assert.equal(get('k-scan-cta').textContent,'INVESTIGATE');
});
test('NASA setup distinguishes a missing reader from a missing account connection',async()=>{
  const data={providers:[{id:'nasa-merra2',name:'Automatic NASA'}],earthdata:{configured:false,reader_installed:false,variables:['T2M']}};
  const {run,get}=context(async()=>response(data));run('investigation.provider="nasa-merra2"');await run('loadProviders()');
  assert.equal(run('sourceReadiness().code'),'reader-missing');assert.equal(get('earthdata-token').disabled,true);
  data.earthdata.reader_installed=true;await run('loadProviders()');
  assert.equal(run('sourceReadiness().code'),'login');assert.equal(get('earthdata-token').disabled,false);assert.equal(get('nasa-restart-help').hidden,true);
  assert.equal(get('k-scan-cta').textContent,'INVESTIGATE');
  data.earthdata.configured=true;await run('loadProviders()');
  assert.equal(run('sourceReadiness().code'),'ready');assert.equal(get('k-scan-cta').textContent,'INVESTIGATE');assert.equal(run('jobSpec("analyze").provider'),'nasa-merra2');
});
test('a source-service failure cannot turn into a cached scientific result',async()=>{
  const calls=[];const {run,get}=context(async url=>{calls.push(url);throw new Error('Data-source service offline');});
  run('investigation.provider="nasa-merra2"');assert.equal(await run('loadProviders()'),false);
  await run('analyze()');assert.equal(run('investigation.provider'),'nasa-merra2');assert.equal(run('investigation.screen'),'sources');
  assert.equal(get('data-through').textContent,'SOURCE OFFLINE');assert.deepEqual(calls,['/api/data-sources']);
});
test('automatic source availability is visible and does not prevent removing an unsupported choice',()=>{
  const {run,ctx,get}=context(async()=>response({}));ctx.state.catalog.variables=[{id:'T2M',name:'Temperature',unit:'°C'},{id:'WS2M',name:'Wind Speed',unit:'m/s'}];
  run('investigation.provider="nasa-merra2";investigation.nasa={configured:true,reader_installed:true,variables:["T2M"]};refreshVariableStrip()');
  assert.equal(get('active-variable-strip').children.length,1);assert.equal(get('active-variable-strip').children[0].disabled,false);assert.equal(run('variableSourceAvailable("WS2M")'),false);
  run('toggleVar("WS2M")');assert.deepEqual(Array.from(ctx.state.selected),['T2M']);
  ctx.state.selected=['WS2M'];run('toggleVar("WS2M")');assert.equal(ctx.state.selected.length,0);
  ctx.state.selected=['T2M','WS2M'];run('investigation.provider="project-cache";refreshVariableStrip()');assert.equal(get('active-variable-strip').children[1].disabled,false);
});
test('an unavailable NASA route does not accept a credential submission',async()=>{
  const calls=[];const {run,get,ctx}=context(async url=>{calls.push(url);return response({});});
  run('investigation.provider="nasa-merra2";investigation.providersLoaded=true');get('earthdata-token').value='private-token';ctx.event={preventDefault(){}};
  await run('connectEarthdata(event)');assert.deepEqual(calls,[]);assert.equal(run('investigation.screen'),'sources');
});

/* -------------------------------------------------------------------------
   Persistent saved-result trend map
   ------------------------------------------------------------------------- */
function savedCell(overrides={}) {
  return Object.assign({
    result_id:'saved-1', area_id:'country:gha', area_name:'Ghana', level:'country',
    variables:[{id:'NDVI',name:'Vegetation Greenness (NDVI)',unit:'index'}],
    window:{start:2016,end:2024,first_month:'2016-01',last_month:'2024-12',months:108},
    verdict:{ok:true,per_decade:-0.0136,unit:'index',direction:'flat',significant:false,p_value:0.7098,method:'Mann-Kendall'},
    saved_at:'2026-11-15T12:00:00Z', status:'current',
  }, overrides);
}

test('a saved trend layer colours only the exact measurement and window',async()=>{
  const calls=[];
  const {ctx,get,run}=context(async url=>{
    calls.push(url);
    if(String(url).startsWith('/api/results/map'))return response({cells:[savedCell()],window:{start:2016,end:2024},exact:true,alternatives:[]});
    return response({});
  });
  run("investigation.level='country'");
  ctx.state.catalog.variables=[{id:'NDVI',name:'Vegetation Greenness (NDVI)'}];
  ctx.state.selected=['NDVI'];
  get('start').value='2016';get('end').value='2024';
  await run('loadSavedTrendMap(true)');
  assert.ok(calls.some(url=>String(url).indexOf('/api/results/map')>=0),'the map index is queried');
  assert.equal(run('savedCellFor("country:gha").result_id'),'saved-1');
  assert.equal(run('savedCellFor("country:nga")'),null,'an uncomputed country stays uncoloured');
  const note=get('saved-trend-note');
  assert.match(String(note.textContent),/saved/i);
  assert.match(String(note.textContent),/no analysis or observation request/i);
  assert.equal(note.dataset.state,'ok');
});

test('a different saved window is never mixed into the requested one',async()=>{
  const {ctx,get,run}=context(async url=>{
    if(String(url).startsWith('/api/results/map'))return response({cells:[],exact:false,alternatives:[{window:{start:2016,end:2024},result_id:'saved-1'}]});
    return response({});
  });
  ctx.state.catalog.variables=[{id:'NDVI',name:'NDVI'}];ctx.state.selected=['NDVI'];
  get('start').value='2005';get('end').value='2024';
  await run('loadSavedTrendMap(true)');
  assert.equal(run('savedCellFor("country:gha")'),null,'2005–2024 must not borrow a 2016–2024 verdict');
  const note=get('saved-trend-note');
  assert.equal(note.dataset.state,'empty');
  assert.match(String(note.textContent),/2005–2024/);
});

test('the remote action is built from the completed local investigation',async()=>{
  const {ctx,get,run}=context(async()=>response({}));
  ctx.state.catalog.variables=[{id:'T2M',name:'Air Temperature',unit:'°C'},{id:'GLDAS_SOILT',name:'Soil Temperature',unit:'K'}];
  ctx.state.selected=['T2M','GLDAS_SOILT'];ctx.state.activeVarIdx=0;
  run('investigation.remoteTask={regionId:"focus:ghana_north",regionName:"Ghana North",variableId:"T2M",fields:["T2M","GLDAS_SOILT"],start:2016,end:2024,provider:"project-cache",scope:"local"}');
  run('investigation.areas.b=null;state.compareMode=false');
  get('compare-region').value='';
  run('ixState.local={pairs:[]};ixState.global=null;syncRemoteAction()');
  assert.equal(get('ix-run-remote').hidden,false);
  assert.match(String(get('ix-run-remote').textContent),/CHOOSE COMPARISON AREA B/);
  assert.match(String(get('ix-remote-context').textContent),/Ghana North/);
  assert.match(String(get('ix-remote-context').textContent),/2016–2024/);
  // A different unsaved selection must be reported as an edit, not silently used.
  ctx.state.selected=['T2M'];
  run('investigation.areas.b={id:"country:nga",name:"Nigeria",level:"country"}');
  get('start').value='2016';get('end').value='2024';
  run('syncRemoteAction()');
  assert.match(String(get('ix-run-remote').textContent),/RUN REMOTE RELATIONSHIPS/);
  assert.match(String(get('ix-remote-context').textContent),/Nigeria/);
  assert.match(String(get('ix-remote-context').textContent),/only/i);
});
