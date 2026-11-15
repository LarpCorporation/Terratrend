const test=require('node:test');
const assert=require('node:assert/strict');
const S=require('../frontend/selection-geometry.js');

test('circle radius is geographic and preserves area at different latitudes',()=>{
  const equator=S.shape('circle',[0,0],100),north=S.shape('circle',[40,60],100);
  const cap=2*Math.PI*S.R*S.R*(1-Math.cos(100/S.R));
  assert.ok(Math.abs(equator.properties.area_km2/cap-1)<.002);
  assert.ok(Math.abs(north.properties.area_km2/equator.properties.area_km2-1)<.0001);
});
test('square side length is in kilometres rather than map degrees',()=>{
  for(const center of [[0,0],[120,60]])assert.ok(Math.abs(S.shape('square',center,100).properties.area_km2/10000-1)<.001);
});
test('bounds cross the dateline without selecting the rest of the world',()=>{
  const crossing=S.bounds(179,-1,-179,1),ordinary=S.bounds(-1,-1,1,1);
  assert.ok(Math.abs(crossing.properties.area_km2/ordinary.properties.area_km2-1)<1e-8);
  assert.equal(crossing.properties.crosses_dateline,true);
  assert.ok(Math.abs(crossing.properties.center[0])===180);
});
test('wide coordinate bounds retain the full selected width',()=>{
  const globe=S.bounds(-180,-90,180,90);
  assert.ok(Math.abs(globe.properties.area_km2/(4*Math.PI*S.R*S.R)-1)<1e-8);
  assert.equal(globe.geometry.type,'MultiPolygon');
});
test('invalid and self-intersecting selections are rejected',()=>{
  assert.throws(()=>S.lasso([[0,0],[2,2],[0,2],[2,0]]),/crosses itself/);
  assert.throws(()=>S.bounds(-1,10,1,5),/North latitude/);
  assert.throws(()=>S.shape('circle',[0,89],1000),/pole/);
  assert.throws(()=>S.lasso([[0,0],[Infinity,1],[1,0]]),/longitude/);
});
test('a lasso on the dateline keeps its local area',()=>{
  const a=S.lasso([[179,-1],[-179,-1],[-179,1],[179,1]]);
  assert.ok(Math.abs(a.properties.area_km2-S.bounds(-1,-1,1,1).properties.area_km2)<.01);
});
test('custom identity is stable across frontend and backend serialization',async()=>{
  const f=await S.identify(S.bounds(-3,4,1,11));
  assert.equal(f.id,'custom:60fbc5bb7a895a8905ab');
  const other=await S.identify(S.bounds(-3,4,1,12));
  assert.notEqual(f.id,other.id);
});
