const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

test('analysis signals distinguish nonsignificance, missing evidence and significant change',()=>{
  const app=fs.readFileSync(require('node:path').join(__dirname,'../frontend/app.js'),'utf8');
  const rendered=[];
  const box={innerHTML:'',appendChild:el=>rendered.push(el.innerHTML)};
  const ctx={$:()=>box,state:{activeVarIdx:0},esc:String,num:(v,n)=>Number(v).toFixed(n),
    document:{createElement:()=>({style:{setProperty(){}},addEventListener(){}})}};
  vm.createContext(ctx);
  vm.runInContext(app.slice(app.indexOf('function renderSignals('),app.indexOf('\nfunction renderCells(')),ctx);
  ctx.renderSignals({series:[
    {variable:{name:'Uncertain'},overall:{ok:true,direction:'flat',significant:false,per_decade:-.31,p:.348}},
    {variable:{name:'Missing'},overall:{ok:false}},
    {variable:{name:'Measured increase'},overall:{ok:true,direction:'rising',significant:true,per_decade:.82,p:.029}},
  ]});
  assert.match(rendered[0],/NOT SIGNIFICANT/);assert.doesNotMatch(rendered[0],/STABLE/);
  assert.match(rendered[1],/INSUFFICIENT DATA/);
  assert.match(rendered[2],/RISING/);
});
