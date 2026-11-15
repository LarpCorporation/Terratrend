const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const THREE = require('../frontend/vendor/three.min.js');
const context = {window:{THREE},setTimeout,clearTimeout};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/earth-renderer.js'),'utf8'),context);
const Globe=context.window.TerraGlobe;

test('a hidden map schedules its next frame without doing projection or GPU work',()=>{
  let scheduled=0;context.requestAnimationFrame=()=>scheduled++;
  const map={host:{offsetParent:null},frame(){},updateProjection(){throw new Error('Hidden maps must not redraw');}};
  Globe.prototype.frame.call(map,1000);assert.equal(scheduled,1);
});

test('significant increases are blue and decreases red while uncertain areas stay neutral',()=>{
  const nodes=['up','down','uncertain'].map(id=>({feature:{id},mesh:{material:{color:new THREE.Color()}},lines:{material:{color:new THREE.Color()}}}));
  const map={nodes,selected:[],hover:null,results:new Map([
    ['up',{overall:{ok:true,significant:true,direction:'rising'}}],['down',{overall:{ok:true,significant:true,direction:'falling'}}],['uncertain',{overall:{ok:true,significant:false,direction:'rising'}}]])};
  Globe.prototype.paint.call(map);
  const colors=nodes.map(n=>n.mesh.material.color);
  assert.ok(colors[0].b>colors[0].r,'increase must use blue');assert.ok(colors[1].r>colors[1].b,'decrease must use red');
  assert.notEqual(colors[2].getHex(),colors[0].getHex());
});

test('relationship arcs use measurement colors and animate only a supported temporal lead',()=>{
  const map={arcs:new THREE.Group(),planeArcs:new THREE.Group(),packets:[]};
  const link={source_region:{lon:0,lat:6},target_region:{lon:8,lat:9},target_variable:{color:'#ab79cf'},direction:'direct',relationship:'simultaneous',lag_months:0};
  Globe.prototype.setConnections.call(map,[link]);
  assert.equal(map.arcs.children[0].material.color.getHexString(),'ab79cf');assert.equal(map.packets.length,0);
  Globe.prototype.setConnections.call(map,[{...link,relationship:'response',lag_months:2}]);assert.equal(map.packets.length,2);
});

test('clearing trend colors does not discard the relationship overlay',()=>{
  const map={results:new Map([['a',{}]]),paint(){},setConnections(){throw new Error('Relationship evidence must survive');}};
  Globe.prototype.clearResults.call(map);assert.equal(map.results.size,0);
});
function feature(coordinates,type='Polygon'){return {geometry:{type,coordinates},properties:{name:'Test area',bbox:[-20,-30,50,40]}};}

test('large-area fill triangles follow the sphere above the ocean surface',()=>{
  const g=Globe.buildFeatureGeometry(feature([[[-20,-30],[50,-30],[10,40],[-20,-30]]]));
  const a=g.mesh.attributes.position.array,indices=g.mesh.index.array;
  assert.ok(indices.length>100);
  let minRadius=Infinity;
  for(let i=0;i<indices.length;i+=3){const centre=new THREE.Vector3();for(let j=0;j<3;j++)centre.add(new THREE.Vector3().fromArray(a,indices[i+j]*3));minRadius=Math.min(minRadius,centre.multiplyScalar(1/3).length());}
  assert.ok(minRadius>.999,`A fill triangle cuts through the ocean: radius ${minRadius}`);
  g.mesh.dispose();g.lines.dispose();
});

test('date-line polygons have no triangles stretching across the flat map',()=>{
  const g=Globe.buildFeatureGeometry(feature([[[179,-2],[-179,-2],[-179,2],[179,2],[179,-2]]]));
  const a=g.mesh.userData.plane,indices=g.mesh.index.array;
  for(let i=0;i<indices.length;i+=3){const xs=[0,1,2].map(j=>a[indices[i+j]*3]);assert.ok(Math.max(...xs)-Math.min(...xs)<.1);assert.ok(xs.every(x=>Math.abs(x)<=2.801));}
  assert.ok(g.lines.attributes.position.count>4);
  g.mesh.dispose();g.lines.dispose();
});

test('parent boundaries omit the shared interior edge',()=>{
  const g=Globe.buildFeatureGeometry(feature([
    [[[0,0],[1,0],[1,1],[0,1],[0,0]]],
    [[[1,0],[2,0],[2,1],[1,1],[1,0]]]
  ],'MultiPolygon'));
  assert.equal(g.lines.attributes.position.count,12);
  g.mesh.dispose();g.lines.dispose();
});

test('plane-view focus pans to a country and permits a regional zoom',()=>{
  const map={targetBlend:1,world:new THREE.Group(),zoom:4.6};
  Globe.prototype.focusFeature.call(map,{bbox:[-3,4,1,11],center:[-1,7.5]});
  assert.ok(map.zoom<1);assert.ok(map.world.position.y<0);assert.ok(map.world.position.x>0);
});

test('base mesh keeps each country’s triangles aligned at range boundaries',()=>{
  const data={countries:[{face_offset:0,face_count:4},{face_offset:4,face_count:3}]};
  assert.deepEqual(Array.from(Globe.decodeBaseFaces(data,[0,1,2,99,3,4,5])),[0,1,2,3,4,5]);
  const actual=JSON.parse(fs.readFileSync(path.join(__dirname,'../frontend/data/map.json'),'utf8'));
  const vertices=new Int16Array(Uint8Array.from(Buffer.from(actual.geom.verts,'base64')).buffer);
  const raw=new Uint16Array(Uint8Array.from(Buffer.from(actual.geom.faces,'base64')).buffer);
  const faces=Globe.decodeBaseFaces(actual,raw);
  for(let i=0;i<faces.length;i+=3){
    const lon=faces.slice(i,i+3).map(index=>180*vertices[2*index]/32768);
    assert.ok(Math.max(...lon)-Math.min(...lon)<=180,'A base triangle crosses the entire plane map');
  }
});

test('clicked lasso segments remain above the curved Earth',()=>{
  const map={draftGroup:new THREE.Group(),geometries:[],selectionSlot:'a',options:{},updateProjection(){},clearSelectionGroup:Globe.prototype.clearSelectionGroup};
  Globe.prototype.setLassoTrail.call(map,[[0,0],[90,0]]);
  const points=map.draftGroup.children[0].geometry.attributes.position.array;
  assert.ok(points.length>100);
  for(let i=0;i<points.length;i+=6){const a=new THREE.Vector3().fromArray(points,i),b=new THREE.Vector3().fromArray(points,i+3);assert.ok(a.add(b).multiplyScalar(.5).length()>1.01);}
});

test('globe focus fits the full coordinate area vertically',()=>{
  const map={targetBlend:0,world:new THREE.Group(),zoom:3.6};
  Globe.prototype.focusFeature.call(map,{bbox:[-3,4,1,11],center:[-1,7.5]});map.world.updateMatrixWorld(true);
  const camera=new THREE.PerspectiveCamera(38,1.8,.015,100);camera.position.z=map.zoom;camera.lookAt(0,0,0);camera.updateMatrixWorld(true);
  for(const lon of [-3,1])for(const lat of [4,11]){
    const a=lon*Math.PI/180,b=lat*Math.PI/180;
    const p=new THREE.Vector3(Math.cos(b)*Math.sin(a),Math.sin(b),Math.cos(b)*Math.cos(a)).applyMatrix4(map.world.matrixWorld).project(camera);
    assert.ok(Math.abs(p.y)<.9,'The area is clipped by automatic focus');
  }
});

test('freehand drawing closes a polygon while Shift-drag navigates',()=>{
  const handlers={},canvas={style:{},setPointerCapture(){},addEventListener:(name,fn)=>{handlers[name]=fn;}};
  let received=null;
  const map={renderer:{domElement:canvas},host:{clientHeight:600},world:new THREE.Group(),zoom:3.6,targetBlend:0,selectionMode:'lasso',selectionSlot:'a',lassoPoints:[],draftGroup:new THREE.Group(),geometries:[],options:{onLasso:points=>{received=points;}},tooltip:{hidden:true},updateProjection(){},paint(){},screenToGeo:e=>[e.clientX/10,e.clientY/10]};
  for(const name of ['clearSelectionGroup','setLassoTrail','finishLasso','setAutoRotation','moveMap'])map[name]=Globe.prototype[name];
  Globe.prototype.bind.call(map);
  handlers.pointerdown({button:0,pointerId:1,clientX:0,clientY:0,shiftKey:false});
  for(const [clientX,clientY] of [[100,0],[100,100],[0,100],[0,0]])handlers.pointermove({clientX,clientY});
  handlers.pointerup({clientX:0,clientY:0});
  const selection=require('../frontend/selection-geometry.js').lasso(received);
  assert.ok(selection.properties.area_km2>1000000);assert.equal(map.world.rotation.y,0);
  received=null;
  handlers.pointerdown({button:0,pointerId:2,clientX:0,clientY:0,shiftKey:true});
  handlers.pointermove({clientX:100,clientY:40});handlers.pointerup({clientX:100,clientY:40});
  assert.equal(received,null);assert.notEqual(map.world.rotation.y,0);
});

test('close-up zoom and orbit scale with altitude instead of globe radius',()=>{
  const far=Globe.navigationZoom(3.6,-120),near=Globe.navigationZoom(1.1,-120);
  assert.ok(1.1-near<(3.6-far)/20);
  assert.ok(Globe.navigationScale(1.1,600)<Globe.navigationScale(3.6,600)/20);
  assert.equal(Globe.navigationZoom(1.08,-10000),1.08);
  assert.ok(Globe.navigationZoom(3.6,-10000)>3.1,'A large scroll event should not jump to ground level');
  assert.ok(Globe.navigationZoom(.2,-120,true)<.2);
});

function navigationMap(){
  const handlers={},canvas={style:{},setPointerCapture(){},addEventListener:(name,fn)=>{handlers[name]=fn;}};
  const map=Object.assign(Object.create(Globe.prototype),{renderer:{domElement:canvas},host:{clientHeight:600},world:new THREE.Group(),zoom:3.6,targetBlend:0,selectionMode:'boundary',options:{},tooltip:{hidden:true},paint(){},pickConnection:()=>null,pick:()=>({id:'africa'})});
  map.bind();return {map,handlers};
}
test('horizontal wheel movement rotates the globe and pans the plane without zooming',()=>{
  const {map,handlers}=navigationMap();let prevented=false;
  const event={deltaX:45,deltaY:2,deltaMode:0,preventDefault(){prevented=true;}};
  handlers.wheel(event);assert.ok(prevented);assert.ok(map.world.rotation.y<0);assert.equal(map.zoom,3.6);
  map.targetBlend=1;handlers.wheel(event);assert.ok(map.world.position.x<0);assert.equal(map.zoom,3.6);
  const x=map.world.position.x;handlers.wheel({...event,deltaX:0,deltaY:-90});assert.equal(map.world.position.x,x);assert.ok(map.zoom<3.6);
});
test('line-mode wheel deltas match pixel-mode input and pinch remains a zoom',()=>{
  const a=navigationMap(),b=navigationMap();
  a.handlers.wheel({deltaX:0,deltaY:3,deltaMode:1,preventDefault(){}});
  b.handlers.wheel({deltaX:0,deltaY:48,deltaMode:0,preventDefault(){}});
  assert.equal(a.map.zoom,b.map.zoom);
  a.handlers.wheel({deltaX:100,deltaY:-12,ctrlKey:true,deltaMode:0,preventDefault(){}});
  assert.equal(a.map.world.rotation.y,0);assert.ok(a.map.zoom<b.map.zoom);
});
test('double-click starts spin without toggling the clicked selection',()=>{
  const oldSet=context.setTimeout,oldClear=context.clearTimeout,timers=new Map();let counter=0,selections=0;
  context.setTimeout=fn=>{timers.set(++counter,fn);return counter;};context.clearTimeout=id=>timers.delete(id);
  try{
    const {map,handlers}=navigationMap();map.options.onSelect=()=>selections++;
    for(let i=0;i<2;i++){handlers.pointerdown({button:0,pointerId:1,clientX:100,clientY:100});handlers.pointerup({clientX:100,clientY:100});}
    handlers.dblclick({preventDefault(){}});for(const fn of timers.values())fn();
    assert.equal(map.auto,true);assert.equal(selections,0);assert.equal(timers.size,0);
    handlers.pointerdown({button:0,pointerId:1,clientX:100,clientY:100});assert.equal(map.auto,false);
  }finally{context.setTimeout=oldSet;context.clearTimeout=oldClear;}
});

test('returning to an administrative layer reuses its compiled meshes',async()=>{
  context.document={createElement:()=>({textContent:''})};
  const map=Object.assign(Object.create(Globe.prototype),{nodes:[],features:[],selectionFeatures:[],geometries:[],overlays:new THREE.Group(),labelLayer:{replaceChildren(){}},updateProjection(){},paint(){},setSelectionFeatures(){}});
  const make=(id,x)=>({id,properties:{name:id,level:'region',geometry_version:id},geometry:{type:'Polygon',coordinates:[[[x,0],[x+1,0],[x+1,1],[x,1],[x,0]]]}});
  const a=make('a',0),b=make('b',4);
  await map.setFeatures([a]);const compiled=map.nodes[0].mesh.geometry;
  await map.setFeatures([b]);await map.setFeatures([a]);
  assert.equal(map.nodes[0].mesh.geometry,compiled);assert.equal(map.overlays.children.length,2);assert.equal(map.geometries.length,2);
});
