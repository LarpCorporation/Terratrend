const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const context={window:{}};vm.createContext(context);vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../frontend/map-panels.js'),'utf8'),context);
test('dragged panels remain reachable after moving or shrinking the map',()=>{
  const fit=context.window.TerraPanelPosition;
  assert.deepEqual({...fit(-50,-80,267,360,1280,570)},{x:8,y:8});
  assert.deepEqual({...fit(1000,500,267,360,1280,570)},{x:1000,y:202});
  assert.deepEqual({...fit(1000,500,267,360,375,459)},{x:100,y:91});
});
