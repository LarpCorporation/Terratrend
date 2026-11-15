const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ctx={window:{},module:{exports:{}}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../frontend/events.js'),'utf8'),ctx);
const {eventConnections}=ctx.module.exports;
const nodes=[{id:'pacific',name:'Pacific',lon:-130,lat:0},{id:'ghana',name:'Ghana',lon:0,lat:7}];
function connection(verification){return eventConnections({nodes,edges:[{id:'link',source_node:'pacific',target_node:'ghana',label:'Rainfall pathway',verification}]})[0];}
test('editorial pathways have no invented score or direction of time',()=>{
  const c=connection({status:'not_checked',lag_months_observed:4});
  assert.equal(c.r,null);assert.equal(c.relationship,'simultaneous');assert.equal(c.lag_months,0);
  assert.match(c.evidence_label,/Catalogue pathway/);assert.equal(c.target_variable.color,'#e9c77a');
});
test('a computed pathway that fails adjusted significance stays an editorial line',()=>{
  const c=connection({status:'verified_from_source',survives_fdr:false,r_value:.82,lag_months_observed:3});
  assert.equal(c.r,null);assert.equal(c.lag_months,0);
});
test('only a surviving computed time lead becomes an animated relationship',()=>{
  const c=connection({status:'verified_from_source',survives_fdr:true,r_value:-.67,lag_months_observed:-2});
  assert.equal(c.r,-.67);assert.equal(c.relationship,'response');assert.equal(c.lag_months,-2);
  assert.equal(c.direction,'inverse');assert.equal(c.target_variable.color,'#68b8ff');
});
test('event request review counts the actual independent source tasks',()=>{
  const review=require('../frontend/data-review.js');
  const catalog={variables:[{id:'T2M'},{id:'PRECTOTCORR'}],regions:[]};
  const areas=[{id:'a',name:'A',bbox:[-2,6,0,8]},{id:'b',name:'B',bbox:[-1,8,0,10]}];
  const base={operation:'analyze',provider:'multi-source',start:2016,end:2024};
  const requests=[{...base,region:'a',variables:['T2M']},{...base,region:'b',variables:['PRECTOTCORR']}];
  const combined=review.estimate({...base,operation:'event',areas,event_requests:requests},catalog,['T2M','PRECTOTCORR']);
  const separate=requests.map(r=>review.estimate(r,{...catalog,regions:areas},['T2M','PRECTOTCORR']));
  assert.equal(combined.requests,separate.reduce((n,p)=>n+p.requests,0));
  assert.equal(combined.bytes,separate.reduce((n,p)=>n+p.bytes,0));assert.equal(combined.areas.length,2);
});
test('event walkthrough waits for actual selection, details and explanation actions',()=>{
  const p=require('../frontend/onboarding.js').__pure;
  const ids=['event-story','event-pathway','event-evidence','event-explanation'];
  assert.ok(ids.every(id=>p.lessonById(id)));
  let s=p.createSession({chapter:'advanced',plan:ids});
  assert.equal(p.canAdvance(s),false);
  s=p.reduce(s,{type:'action',detail:{action:'event-selected',eventId:'el_nino_2023_2024'}});
  assert.equal(p.currentLesson(s).id,'event-pathway');
  s=p.reduce(s,{type:'action',detail:{action:'event-pathway-open',edgeId:'link'}});
  assert.equal(p.currentLesson(s).id,'event-evidence');
});
test('revealing details for a spotlight cannot impersonate a learner click',()=>{
  class Element{
    constructor(tag){this.tagName=tag;this.children=[];this.listeners={};this.dataset={};}
    append(...items){this.children.push(...items);}
    addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}
    setAttribute(){}
    fire(type,event={}){for(const fn of this.listeners[type]||[])fn(event);}
  }
  const actions=[];
  ctx.document={createElement:tag=>new Element(tag)};
  ctx.announceAction=(...args)=>actions.push(args);
  ctx.window.TerraEvents.state.index={status_legend:{}};
  const card=ctx.module.exports.edgeBlock({id:'edge-1',label:'Test pathway',verification:{status:'not_checked'}});
  const details=card.children.find(n=>n.tagName==='details');
  const summary=details.children.find(n=>n.tagName==='summary');
  details.open=true;details.fire('toggle');
  assert.equal(actions.length,0,'a programmatic reveal is not a learner action');
  details.open=false;details.fire('toggle');summary.fire('click',{isTrusted:true});details.open=true;details.fire('toggle');
  assert.equal(actions.length,1);assert.equal(actions[0][0],'event-pathway-open');
});
