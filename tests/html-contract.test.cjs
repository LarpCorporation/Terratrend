const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
test('the shared scientific renderer retains its required result and legend containers',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../frontend/index.html'),'utf8');
  for(const id of ['signal-list','legend-active','chart','analysis-screen','cell-summary','krc-value','selection-coverage'])assert.ok(html.includes(`id="${id}"`),`Scientific result container missing: ${id}`);
  const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);assert.equal(ids.length,new Set(ids).size,'IDs must be unique');
});
