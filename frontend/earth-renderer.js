/* TerraTrend globe adapter. Ports TerraTrend 2's country/coast geometry into
   a maintained Three.js scene; scientific overlays use the shared geography. */
(function () {
  'use strict';
  const T = window.THREE;
  const RAD = Math.PI / 180;
  const palette = { rise: '#ff786a', fall: '#59cfda', neutral: '#53695a', missing: '#26382e', a: '#68b8ff', b: '#e9c77a' };
  const continentCenters={'continent:africa':[20,2],'continent:asia':[95,35],'continent:europe':[20,55],'continent:north_america':[-105,40],'continent:south_america':[-60,-15],'continent:oceania':[135,-25],'continent:antarctica':[0,-78]};
  const centerOf=p=>p.center||continentCenters[p.id]||[(p.bbox[0]+p.bbox[2])/2,(p.bbox[1]+p.bbox[3])/2];
  function ll(lon, lat, r=1) {
    lat *= RAD; lon *= RAD;
    return [r*Math.cos(lat)*Math.sin(lon), r*Math.sin(lat), r*Math.cos(lat)*Math.cos(lon)];
  }
  function flat(lon, lat, r=1) {
    return [lon*RAD/Math.PI*2.8, Math.log(Math.tan(Math.PI/4+Math.max(-85,Math.min(85,lat))*RAD/2))/Math.PI*2.8, (r-1)*3];
  }
  function typed(base64, Type) {
    const bytes = Uint8Array.from(atob(base64), c=>c.charCodeAt(0));
    return new Type(bytes.buffer);
  }
  function baseFaces(data, faces) {
    const indices=[];
    // The source draws each country's index range separately. A range can
    // end with an incomplete triangle; flattening the raw buffer shifts every
    // subsequent country's triangles and creates lines across the plane map.
    for(const country of data.countries){
      const end=country.face_offset+country.face_count;
      for(let i=country.face_offset;i+2<end;i+=3)indices.push(faces[i],faces[i+1],faces[i+2]);
    }
    return indices;
  }
  function geo(coords, indices=null, r=1, normals=true) {
    const sphere=[], plane=[];
    for (const p of coords) { sphere.push(...ll(p[0],p[1],r)); plane.push(...flat(p[0],p[1],r)); }
    const g=new T.BufferGeometry();
    g.setAttribute('position',new T.Float32BufferAttribute(sphere,3));
    if(indices)g.setIndex(indices);
    g.userData.sphere=new Float32Array(sphere);g.userData.plane=new Float32Array(plane);
    if(normals)g.computeVertexNormals();g.computeBoundingSphere();return g;
  }
  function clipLongitude(points, edge, less) {
    const out=[];let previous=points[points.length-1];
    const inside=p=>less?p.x<=edge:p.x>=edge;
    for(const current of points){
      if(inside(current)!==inside(previous)){const t=(edge-previous.x)/(current.x-previous.x);out.push(new T.Vector2(edge,previous.y+t*(current.y-previous.y)));}
      if(inside(current))out.push(current);previous=current;
    }
    return out;
  }
  function datelinePieces(points) {
    const shift=360*Math.floor((points.reduce((n,p)=>n+p.x,0)/points.length+180)/360);
    points=points.map(p=>new T.Vector2(p.x-shift,p.y));
    if(points.some(p=>p.x>180))return [clipLongitude(points,180,true),clipLongitude(points,180,false).map(p=>new T.Vector2(p.x-360,p.y))];
    if(points.some(p=>p.x< -180))return [clipLongitude(points,-180,false),clipLongitude(points,-180,true).map(p=>new T.Vector2(p.x+360,p.y))];
    return [points];
  }
  function datelineLine(a,b) {
    const shift=360*Math.floor(((a.x+b.x)/2+180)/360);
    a=new T.Vector2(a.x-shift,a.y);b=new T.Vector2(b.x-shift,b.y);
    const edge=Math.max(a.x,b.x)>180?180:Math.min(a.x,b.x)<-180?-180:null;
    if(edge===null)return [[a,b]];
    const t=(edge-a.x)/(b.x-a.x),mid=new T.Vector2(edge,a.y+t*(b.y-a.y));
    const move=point=>new T.Vector2(point.x+(edge===180?-360:360),point.y);
    const outside=p=>edge===180?p.x>180:p.x< -180;
    return [outside(a)?[move(a),move(mid)]:[a,mid],outside(b)?[move(mid),move(b)]:[mid,b]];
  }
  function shapes(feature) {
    const polys=feature.geometry.type==='Polygon'?[feature.geometry.coordinates]:feature.geometry.coordinates;
    const coords=[], faces=[], outlines=[],edges=new Map();
    const distance=(a,b)=>Math.hypot((a.x-b.x)*Math.max(.05,Math.cos((a.y+b.y)*RAD/2)),a.y-b.y);
    function triangle(a,b,c,depth=0){
      const lengths=[distance(a,b),distance(b,c),distance(c,a)],largest=Math.max(...lengths);
      // Large flat triangles cut through the ocean sphere. Subdivide in the
      // source coordinates so every fill follows the curved Earth surface.
      if(largest>4&&depth<16){
        const i=lengths.indexOf(largest),v=[a,b,c],p=v[i],q=v[(i+1)%3],r=v[(i+2)%3],mid=p.clone().lerp(q,.5);
        triangle(p,mid,r,depth+1);triangle(mid,q,r,depth+1);return;
      }
      for(const piece of datelinePieces([a,b,c]))for(let i=1;i+1<piece.length;i++){
        const offset=coords.length;coords.push([piece[0].x,piece[0].y],[piece[i].x,piece[i].y],[piece[i+1].x,piece[i+1].y]);faces.push(offset,offset+1,offset+2);
      }
    }
    for (const poly of polys) {
      // Natural Earth supplies dateline-cut polygons. Administrative shapes
      // are unwrapped so triangles never span the opposite hemisphere.
      const rings=poly.map(ring=>{
        let last=null;
        return ring.slice(0,-1).map(p=>{let x=p[0];if(last!==null){while(x-last>180)x-=360;while(x-last< -180)x+=360;}last=x;return new T.Vector2(x,p[1]);});
      });
      if(!rings[0]||rings[0].length<3)continue;
      const vertices=[];
      for (const ring of rings) {
        vertices.push(...ring);
        for(let i=0;i<ring.length;i++){
          const a=ring[i],b=ring[(i+1)%ring.length];
          const keyOf=p=>`${(((p.x+180)%360+360)%360-180).toFixed(6)},${p.y.toFixed(6)}`;
          const x=keyOf(a),y=keyOf(b),key=x<y?x+'|'+y:y+'|'+x;
          // A parent layer draws its exterior, not every shared country edge.
          if(edges.has(key))edges.delete(key);else edges.set(key,[a,b]);
        }
      }
      const tris=T.ShapeUtils.triangulateShape(rings[0],rings.slice(1));
      for(const tri of tris)triangle(...tri.map(i=>vertices[i]));
    }
    for(const [a,b] of edges.values()){
      const n=Math.max(1,Math.ceil(distance(a,b)/2));
      for(let i=0;i<n;i++){
        const p=a.clone().lerp(b,i/n),q=a.clone().lerp(b,(i+1)/n);
        const pieces=datelineLine(p,q);
        for(const piece of pieces)if(piece.length>=2)outlines.push([piece[0].x,piece[0].y],[piece[piece.length-1].x,piece[piece.length-1].y]);
      }
    }
    return { mesh:geo(coords,faces,1.006,false), lines:geo(outlines,null,1.009,false) };
  }
  class TerraGlobe {
    constructor(host,options={}) {
      this.host=host;this.options=options;this.blend=0;this.targetBlend=0;this.auto=false;this.zoom=3.6;
      this.features=[];this.nodes=[];this.results=new Map();this.selected=[];this.hover=null;this.geometries=[];this.packets=[];
      this.selectionMode='boundary';this.selectionFeatures=[];this.selectionSlot='a';this.lassoPoints=[];
      this.renderer=new T.WebGLRenderer({antialias:true,alpha:true,powerPreference:'high-performance'});
      this.renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));this.renderer.setClearColor(0x050b08,1);
      this.renderer.domElement.setAttribute('aria-label','Earth map. Use the area lists for keyboard selection.');
      host.append(this.renderer.domElement);
      this.scene=new T.Scene();this.camera=new T.PerspectiveCamera(38,1,.015,100);
      this.world=new T.Group();this.world.rotation.set(.12,-.2,0);this.scene.add(this.world);
      this.overlays=new T.Group();this.world.add(this.overlays);this.arcs=new T.Group();this.world.add(this.arcs);this.planeArcs=new T.Group();this.planeArcs.visible=false;this.world.add(this.planeArcs);
      this.selectionGroup=new T.Group();this.draftGroup=new T.Group();this.world.add(this.selectionGroup,this.draftGroup);
      this.scene.add(new T.AmbientLight(0x9db5a1,.75));
      const light=new T.DirectionalLight(0xc2d6aa,1.2);light.position.set(-3,4,5);this.scene.add(light);
      this.ocean=new T.Mesh(new T.SphereGeometry(.993,80,56),new T.MeshPhongMaterial({color:0x12251b,shininess:3,specular:0x203a29}));this.world.add(this.ocean);
      this.planeOcean=new T.Mesh(new T.PlaneGeometry(5.6,5.6),new T.MeshBasicMaterial({color:0x0c1912}));this.planeOcean.position.z=-.025;this.planeOcean.visible=false;this.world.add(this.planeOcean);
      this.glow=new T.Mesh(new T.SphereGeometry(1.08,56,40),new T.ShaderMaterial({transparent:true,side:T.BackSide,depthWrite:false,blending:T.AdditiveBlending,
        vertexShader:'varying vec3 n; varying vec3 p; void main(){ n=normalize(normalMatrix*normal); vec4 v=modelViewMatrix*vec4(position,1.);p=v.xyz;gl_Position=projectionMatrix*v;}',
        fragmentShader:'varying vec3 n;varying vec3 p;void main(){float a=pow(max(0.,1.-abs(dot(normalize(n),normalize(-p)))),3.);gl_FragColor=vec4(.15,.38,.23,a*.35);}'
      }));this.world.add(this.glow);
      this.ray=new T.Raycaster();this.pointer=new T.Vector2();
      this.labelLayer=document.createElement('div');this.labelLayer.className='earth-label-layer';host.append(this.labelLayer);
      // Named markers for the curated event network. Kept in their own layer:
      // labelLayer is replaced whenever the geographic layer changes.
      this.nodeLayer=document.createElement('div');this.nodeLayer.className='earth-label-layer earth-node-layer';host.append(this.nodeLayer);
      this.eventNodes=[];
      this.tooltip=document.createElement('div');this.tooltip.className='earth-tooltip';this.tooltip.hidden=true;host.append(this.tooltip);
      this.stars();this.grid();this.bind();new ResizeObserver(()=>this.resize()).observe(host);this.resize();
      this.loadBase().catch(e=>{this.host.dataset.baseError=e.message;});
      this.frame=this.frame.bind(this);requestAnimationFrame(this.frame);
    }
    async loadBase() {
      const response=await fetch('data/map.json');if(!response.ok)throw new Error('Base geometry unavailable');
      const data=await response.json(),v=typed(data.geom.verts,Int16Array),f=typed(data.geom.faces,Uint16Array),coast=typed(data.geom.coast,Uint16Array);
      const coords=[];for(let i=0;i<v.length;i+=2)coords.push([180*v[i]/32768,90*v[i+1]/32768]);
      const g=geo(coords,baseFaces(data,f),1);
      g.userData.recomputeNormals=true;this.base=new T.Mesh(g,new T.MeshLambertMaterial({color:0x57664b,side:T.DoubleSide}));this.world.add(this.base);this.geometries.push(g);
      const top=[],bottom=[];
      for(let i=0;i<coast.length;i+=2){const a=coords[coast[i]],b=coords[coast[i+1]];top.push(a,b,a,b,b,a);bottom.push(1,1,.983,1,.983,.983);}
      const wall=geo(top,null,1);
      wall.userData.sphere=new Float32Array(top.flatMap((p,i)=>ll(p[0],p[1],bottom[i])));
      wall.userData.plane=new Float32Array(top.flatMap((p,i)=>flat(p[0],p[1],bottom[i])));
      wall.attributes.position.array.set(wall.userData.sphere);wall.computeVertexNormals();
      wall.userData.recomputeNormals=true;
      this.world.add(new T.Mesh(wall,new T.MeshLambertMaterial({color:0x1a251e,side:T.DoubleSide})));this.geometries.push(wall);
      this.updateProjection(true);
    }
    stars() {
      const pos=[];let seed=29;const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
      for(let i=0;i<900;i++){const a=random()*Math.PI*2,b=Math.acos(2*random()-1);pos.push(13*Math.sin(b)*Math.cos(a),13*Math.cos(b),13*Math.sin(b)*Math.sin(a));}
      const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(pos,3));
      this.starfield=new T.Points(g,new T.PointsMaterial({size:.012,color:0x748b79,transparent:true,opacity:.45}));this.scene.add(this.starfield);
    }
    grid() {
      const points=[];
      for(let lat=-60;lat<=60;lat+=30)for(let lon=-180;lon<180;lon+=3)points.push([lon,lat],[lon+3,lat]);
      for(let lon=-180;lon<=180;lon+=30)for(let lat=-84;lat<84;lat+=3)points.push([lon,lat],[lon,lat+3]);
      const g=geo(points,null,.995,false);this.geometries.push(g);this.world.add(new T.LineSegments(g,new T.LineBasicMaterial({color:0x244231,transparent:true,opacity:.25})));
    }
    resize() {
      const w=this.host.clientWidth||1000,h=this.host.clientHeight||600;
      this.renderer.setSize(w,h);this.camera.aspect=w/h;
      if(w>800)this.camera.setViewOffset(w,h,-w*.055,0,w,h);else this.camera.clearViewOffset();
      this.camera.updateProjectionMatrix();
    }
    setProjection(mode) {this.targetBlend=mode==='plane'?1:0;this.setAutoRotation(false);this.world.position.set(0,0,0);this.world.rotation.set(this.targetBlend?0:.12,this.targetBlend?0:-.2,0);this.zoom=this.targetBlend?4.6:3.6;this.options.onProjection?.(mode);}
    setAutoRotation(active) {this.auto=!!active&&this.targetBlend===0;this.options.onAutoRotation?.(this.auto);}
    zoomBy(delta) {this.zoom=TerraGlobe.navigationZoom(this.zoom,delta,!!this.targetBlend);}
    moveMap(dx,dy=0,origin=null) {
      const scale=TerraGlobe.navigationScale(this.zoom,this.host.clientHeight,!!this.targetBlend);
      if(!this.targetBlend){this.world.rotation.y=(origin?.ry??this.world.rotation.y)+dx*scale;this.world.rotation.x=Math.max(-1.5,Math.min(1.5,(origin?.rx??this.world.rotation.x)+dy*scale));}
      else{this.world.position.x=Math.max(-5.6,Math.min(5.6,(origin?.px??this.world.position.x)+dx*scale));this.world.position.y=Math.max(-2.8,Math.min(2.8,(origin?.py??this.world.position.y)-dy*scale));}
    }
    updateProjection(force=false) {
      if(!force&&Math.abs(this.targetBlend-this.blend)<.0001)return;
      this.blend += (this.targetBlend-this.blend)*.16;if(Math.abs(this.targetBlend-this.blend)<.001)this.blend=this.targetBlend;
      for(const g of this.geometries){const out=g.attributes.position.array,a=g.userData.sphere,b=g.userData.plane;if(!a)continue;for(let i=0;i<out.length;i++)out[i]=a[i]+(b[i]-a[i])*this.blend;g.attributes.position.needsUpdate=true;if(this.blend===this.targetBlend){g.computeBoundingSphere();if(g.userData.recomputeNormals)g.computeVertexNormals();}else{g.boundingSphere=new T.Sphere(new T.Vector3(),4.1);}}
      this.ocean.visible=this.blend<.85;this.ocean.scale.setScalar(1-this.blend*.7);this.planeOcean.visible=this.blend>.2;this.glow.visible=this.blend<.2;this.arcs.visible=this.blend<.02;this.planeArcs.visible=this.blend>.98;
    }
    async setFeatures(features,isCurrent=()=>true) {
      this.layerCache??=new Map();const build=this.featureBuild=(this.featureBuild||0)+1;
      const key=features.map(f=>f.id+'@'+f.properties.geometry_version).join('|');
      let nodes=this.layerCache.get(key),slice=Date.now();
      const dispose=items=>{for(const n of items){n.mesh.geometry.dispose();n.lines.geometry.dispose();n.mesh.material.dispose();n.lines.material.dispose();}};
      if(!nodes){nodes=[];for(const feature of features){
        if(build!==this.featureBuild||!isCurrent()){dispose(nodes);return false;}
        const geometry=shapes(feature);if(!geometry.mesh.attributes.position.count)continue;
        const material=new T.MeshBasicMaterial({color:palette.neutral,side:T.DoubleSide,transparent:true,opacity:.02,depthWrite:false});
        const mesh=new T.Mesh(geometry.mesh,material);mesh.userData.feature=feature;
        const lines=new T.LineSegments(geometry.lines,new T.LineBasicMaterial({color:0x799382,transparent:true,opacity:.24,depthWrite:false}));
        const label=document.createElement('span');label.textContent=feature.properties.name.toUpperCase();
        nodes.push({feature,mesh,lines,label});
        if(Date.now()-slice>10){await new Promise(resolve=>setTimeout(resolve,0));slice=Date.now();}
      }}
      if(build!==this.featureBuild||!isCurrent()){if(!this.layerCache.has(key))dispose(nodes);return false;}
      for(const n of this.nodes)this.overlays.remove(n.mesh,n.lines);
      const old=new Set(this.nodes.flatMap(n=>[n.mesh.geometry,n.lines.geometry]));this.geometries=this.geometries.filter(g=>!old.has(g));
      if(this.nodes!==nodes&&![...this.layerCache.values()].includes(this.nodes))dispose(this.nodes);
      if(features.length&&features[0].properties.level==='region'&&nodes.reduce((n,o)=>n+o.mesh.geometry.attributes.position.count,0)<100000){
        this.layerCache.delete(key);this.layerCache.set(key,nodes);
        while(this.layerCache.size>4){const oldest=this.layerCache.keys().next().value;const items=this.layerCache.get(oldest);this.layerCache.delete(oldest);if(items!==nodes)dispose(items);}
      }
      this.nodes=nodes;this.features=features;this.labelLayer.replaceChildren(...nodes.map(n=>n.label));
      for(const n of nodes){this.overlays.add(n.mesh,n.lines);this.geometries.push(n.mesh.geometry,n.lines.geometry);}
      this.updateProjection(true);this.paint();this.setSelectionFeatures(this.selectionFeatures);
      return true;
    }
    setSelections(ids) {this.selected=ids.slice(0,2);this.paint();}
    setResults(rows) {for(const row of rows)this.results.set(row.id,row);this.paint();}
    clearResults() {this.results.clear();this.paint();this.setConnections([]);}
    clearSelectionGroup(group) {
      const old=new Set(group.children.map(n=>n.geometry));
      while(group.children.length){const n=group.children[0];group.remove(n);n.geometry?.dispose();n.material?.dispose();}
      this.geometries=this.geometries.filter(g=>!old.has(g));
    }
    selectionObjects(group,feature,slot,draft=false) {
      const color=slot==='b'?palette.b:palette.a,g=shapes(feature);
      const mesh=new T.Mesh(g.mesh,new T.MeshBasicMaterial({color,transparent:true,opacity:draft ? .13 : .08,side:T.DoubleSide,depthWrite:false}));
      const lines=new T.LineSegments(g.lines,new T.LineBasicMaterial({color,transparent:true,opacity:.98,depthWrite:false}));
      mesh.userData.feature=feature;mesh.userData.outline=lines;
      group.add(mesh,lines);this.geometries.push(g.mesh,g.lines);
      const center=feature.properties.center;
      if(center&&feature.properties.level==='custom'){
        const point=geo([center],null,1.017,false);
        group.add(new T.Points(point,new T.PointsMaterial({color,size:7,sizeAttenuation:false,depthWrite:false})));this.geometries.push(point);
      }
    }
    setSelectionFeatures(features,force=false) {
      const active=new Set(this.features.map(f=>f.id));
      const signature=features.map(f=>f?f.id+'@'+(f.properties.geometry_version||'')+':'+(active.has(f.id)?'layer':'overlay'):'').join('|');
      if(!force&&signature===this.selectionSignature)return;
      this.selectionSignature=signature;this.selectionFeatures=features.slice();this.clearSelectionGroup(this.selectionGroup);
      features.forEach((feature,i)=>{if(feature&&!active.has(feature.id))this.selectionObjects(this.selectionGroup,feature,i===0?'a':'b');});
      this.updateProjection(true);this.paint();
    }
    setSelectionMode(mode,slot='a') {
      this.cancelSelectionClick?.();this.setAutoRotation(false);
      this.selectionMode=mode;this.selectionSlot=slot;this.lassoPoints=[];this.hover=null;this.tooltip.hidden=true;this.paint();
      this.renderer.domElement.style.cursor=mode==='boundary'?'grab':'crosshair';
    }
    setSelectionDraft(feature,slot='a') {
      this.clearSelectionGroup(this.draftGroup);
      if(feature)this.selectionObjects(this.draftGroup,feature,slot,true);
      this.updateProjection(true);
    }
    setLassoTrail(points) {
      this.clearSelectionGroup(this.draftGroup);
      if(points.length>1){
        const segments=[];
        for(let i=1;i<points.length;i++){
          const a=new T.Vector2(...points[i-1]),b=new T.Vector2(...points[i]);while(b.x-a.x>180)b.x-=360;while(b.x-a.x< -180)b.x+=360;
          const n=Math.max(1,Math.ceil(Math.hypot((a.x-b.x)*Math.cos((a.y+b.y)*RAD/2),a.y-b.y)/2));
          for(let k=0;k<n;k++)for(const pair of datelineLine(a.clone().lerp(b,k/n),a.clone().lerp(b,(k+1)/n)))segments.push([pair[0].x,pair[0].y],[pair[1].x,pair[1].y]);
        }
        const g=geo(segments,null,1.014,false);this.geometries.push(g);this.draftGroup.add(new T.LineSegments(g,new T.LineBasicMaterial({color:this.selectionSlot==='b'?palette.b:palette.a,depthWrite:false})));
      }
      this.updateProjection(true);this.options.onLassoCount?.(points.length);
    }
    finishLasso() {const points=this.lassoPoints.slice();this.lassoPoints=[];this.setLassoTrail([]);this.options.onLasso?.(points);}
    undoLasso() {this.lassoPoints.pop();this.setLassoTrail(this.lassoPoints);}
    screenToGeo(event) {
      if(Math.abs(this.blend-this.targetBlend)>.015)return null;
      const b=this.host.getBoundingClientRect();this.pointer.set((event.clientX-b.left)/b.width*2-1,-(event.clientY-b.top)/b.height*2+1);this.ray.setFromCamera(this.pointer,this.camera);
      const ray=this.ray.ray.clone().applyMatrix4(this.world.matrixWorld.clone().invert());
      const point=this.targetBlend?ray.intersectPlane(new T.Plane(new T.Vector3(0,0,1),0),new T.Vector3()):ray.intersectSphere(new T.Sphere(new T.Vector3(),1),new T.Vector3());
      if(!point)return null;
      if(this.targetBlend){if(Math.abs(point.x)>2.8||Math.abs(point.y)>2.8)return null;return [point.x/2.8*180,(2*Math.atan(Math.exp(point.y/2.8*Math.PI))-Math.PI/2)/RAD];}
      return [Math.atan2(point.x,point.z)/RAD,Math.asin(Math.max(-1,Math.min(1,point.y/point.length())))/RAD];
    }
    paint() {
      const extra=this.selectionGroup?.children.filter(n=>n.userData.feature).map(n=>({feature:n.userData.feature,mesh:n,lines:n.userData.outline}))||[];
      for(const n of [...this.nodes,...extra]){const id=n.feature.id,sel=this.selected.indexOf(id),hover=id===this.hover,row=this.results.get(id),o=row?.overall;
        let color=palette.neutral,opacity=.025;
        if(o){color=!o.ok?palette.missing:!o.significant?palette.neutral:o.direction==='falling'?palette.fall:palette.rise;opacity=o.ok ? .72 : .18;}
        n.mesh.material.color.set(color);n.mesh.material.opacity=hover?Math.max(.25,opacity):sel>=0?Math.max(.12,opacity):opacity;
        n.lines.material.color.set(sel>=0?(sel===0?palette.a:palette.b):hover?'#d4eedc':'#6e8a77');
        n.lines.material.opacity=(sel>=0||hover) ? .95 : .27;
      }
    }
    focusFeature(feature) {
      if(!feature)return;const p=feature.properties||feature,b=p.bbox;
      // A non-finite box propagates NaN into the camera and blanks the entire
      // canvas, so an unusable box keeps the current view instead.
      if(!Array.isArray(b)||b.length!==4||!b.every(v=>typeof v==='number'&&Number.isFinite(v)))return;
      const centre=centerOf(p);
      if(this.targetBlend===0){
        this.world.rotation.set(centre[1]*RAD,-centre[0]*RAD,0);
        const horizontal=Math.min(180,b[2]-b[0])*Math.max(.15,Math.cos(centre[1]*RAD));
        const half=Math.max(horizontal,b[3]-b[1])*RAD*.625;
        this.zoom=half>.95?3.4:Math.max(1.08,Math.cos(half)+Math.sin(half)/Math.tan(19*RAD));
      }
      else{const pt=flat(centre[0],centre[1]);this.world.position.set(-pt[0],-pt[1],0);this.zoom=Math.max(.1,Math.min(6,Math.max(b[2]-b[0],b[3]-b[1])*.055));this.world.rotation.set(0,0,0);}
    }
    setConnections(connections) {
      for(const group of [this.arcs,this.planeArcs])while(group.children.length){const o=group.children[0];group.remove(o);o.geometry?.dispose();o.material?.dispose();}this.packets=[];
      for(const c of connections.slice(0,18)){
        let a=c.source_region,b=c.target_region;if(!a||!b)continue;if(c.relationship==='driver'||c.lag_months<0)[a,b]=[b,a];
        const p1=new T.Vector3(...ll(a.lon,a.lat,1.018)),p2=new T.Vector3(...ll(b.lon,b.lat,1.018));
        const angle=p1.angleTo(p2),points=[];
        for(let i=0;i<=80;i++){const t=i/80;let p;if(Math.abs(Math.sin(angle))>.001)p=p1.clone().multiplyScalar(Math.sin((1-t)*angle)/Math.sin(angle)).add(p2.clone().multiplyScalar(Math.sin(t*angle)/Math.sin(angle)));else p=p1.clone().lerp(p2,t).normalize();points.push(p.normalize().multiplyScalar(1.018+.22*Math.sin(Math.PI*t)));}
        const curve=new T.CatmullRomCurve3(points),color=c.direction==='inverse'?0x59cfda:0xf091d3;
        const line=new T.Line(new T.BufferGeometry().setFromPoints(points),new T.LineBasicMaterial({color,transparent:true,opacity:.7,depthWrite:false}));line.userData.connection=c;this.arcs.add(line);
        const planePoints=points.map(p=>flat(Math.atan2(p.x,p.z)/RAD,Math.asin(p.y/p.length())/RAD,1.015)),segments=[];
        for(let i=1;i<planePoints.length;i++)if(Math.abs(planePoints[i][0]-planePoints[i-1][0])<2.8)segments.push(new T.Vector3(...planePoints[i-1]),new T.Vector3(...planePoints[i]));
        const planeLine=new T.LineSegments(new T.BufferGeometry().setFromPoints(segments),new T.LineBasicMaterial({color,transparent:true,opacity:.7,depthWrite:false}));planeLine.userData.connection=c;this.planeArcs.add(planeLine);
        if(c.relationship!=='simultaneous'&&c.lag_months!==0){
          const packet=new T.Mesh(new T.SphereGeometry(.006,6,6),new T.MeshBasicMaterial({color:0xe5fff4}));this.arcs.add(packet);this.packets.push({mesh:packet,curve,t:0});
          const planePacket=new T.Mesh(new T.SphereGeometry(.006,6,6),new T.MeshBasicMaterial({color:0xe5fff4}));this.planeArcs.add(planePacket);this.packets.push({mesh:planePacket,curve,t:0,plane:true});
        }
      }
    }
    /* Named points for one curated event. Each marker shows where a pathway
       starts or ends; hovering it explains, in plain language, what is
       happening at that place. */
    setEventNodes(nodes, bounds) {
      this.eventNodes=(nodes||[]).filter(n=>typeof n.lat==='number'&&typeof n.lon==='number');
      // The Events screen keeps the globe visible between two panels. A label
      // whose dot sits under a panel is unreadable, so labels are kept inside
      // the visible stage while their dots stay at the true location.
      this.eventBounds=(bounds&&bounds.right>bounds.left)?bounds:null;
      this.nodeLayer.replaceChildren();
      this.tooltip.hidden=true;
      for(const n of this.eventNodes){
        const el=document.createElement('button');
        el.type='button';
        el.className='ev-node ev-node-'+(n.layer||'land');
        el.setAttribute('aria-label',n.name+' — '+(n.description||''));
        const dot=document.createElement('span');dot.className='ev-node-dot';el.append(dot);
        const name=document.createElement('span');name.className='ev-node-name';name.textContent=n.name;el.append(name);
        el.addEventListener('pointerenter',e=>this.showNodeTip(e,n));
        el.addEventListener('pointermove',e=>this.showNodeTip(e,n));
        el.addEventListener('pointerleave',()=>{this.tooltip.hidden=true;});
        el.addEventListener('focus',()=>this.showNodeTip(null,n));
        el.addEventListener('blur',()=>{this.tooltip.hidden=true;});
        el.addEventListener('click',e=>{e.stopPropagation();this.options.onEventNode?.(n);});
        this.nodeLayer.append(el);n.el=el;
      }
    }
    showNodeTip(event,n) {
      const tip=this.tooltip;
      tip.hidden=false;tip.classList.add('ev-node-tip');tip.replaceChildren();
      const head=document.createElement('strong');head.textContent=n.name;
      const where=document.createElement('em');
      where.textContent=[n.layer,n.where].filter(Boolean).join(' · ');
      const body=document.createElement('span');body.textContent=n.description||'';
      tip.append(head,where,body);
      const routes=n.pathways||[];
      if(routes.length){
        const list=document.createElement('span');list.className='ev-node-routes';
        for(const route of routes){
          const line=document.createElement('span');
          line.textContent=route.role+': '+route.label;
          list.append(line);
        }
        tip.append(list);
      }
      const b=this.host.getBoundingClientRect();
      const x=event?event.clientX-b.left:b.width/2;
      const y=event?event.clientY-b.top:120;
      tip.style.left=Math.max(10,Math.min(b.width-310,x+18))+'px';
      tip.style.top=Math.max(10,Math.min(b.height-150,y-30))+'px';
    }
    pick(event) {
      if(this.pickingDisabled)return null;
      if(Math.abs(this.blend-this.targetBlend)>.015)return null;
      const b=this.host.getBoundingClientRect();this.pointer.set((event.clientX-b.left)/b.width*2-1,-(event.clientY-b.top)/b.height*2+1);this.ray.setFromCamera(this.pointer,this.camera);
      const hit=this.ray.intersectObjects(this.nodes.map(n=>n.mesh))[0];
      if(!hit)return null;
      if(this.blend<.1){const world=hit.point.clone();this.world.worldToLocal(world);const normal=world.normalize().transformDirection(this.world.matrixWorld);if(normal.dot(this.camera.position.clone().sub(hit.point).normalize())<0)return null;}
      return hit.object.userData.feature;
    }
    pickConnection(event) {
      if(this.pickingDisabled)return null;
      if(Math.abs(this.blend-this.targetBlend)>.015)return null;
      const bounds=this.host.getBoundingClientRect();this.pointer.set((event.clientX-bounds.left)/bounds.width*2-1,-(event.clientY-bounds.top)/bounds.height*2+1);this.ray.setFromCamera(this.pointer,this.camera);
      this.ray.params.Line.threshold=4*2*this.zoom*Math.tan(19*RAD)/bounds.height;
      const group=this.targetBlend?this.planeArcs:this.arcs;
      const hit=this.ray.intersectObjects(group.children.filter(o=>o.userData.connection))[0];if(!hit)return null;
      if(!this.targetBlend){const surface=this.ray.ray.intersectSphere(new T.Sphere(new T.Vector3(),.993),new T.Vector3());if(surface&&hit.distance>this.ray.ray.origin.distanceTo(surface)+.01)return null;}
      return hit.object.userData.connection;
    }
    bind() {
      const canvas=this.renderer.domElement;let drag=null,clickTimer=null;
      this.cancelSelectionClick=()=>{clearTimeout(clickTimer);clickTimer=null;};
      canvas.style.touchAction='none';
      canvas.addEventListener('pointerdown',e=>{
        if(e.button!==0)return;
        drag={x:e.clientX,y:e.clientY,rx:this.world.rotation.x,ry:this.world.rotation.y,px:this.world.position.x,py:this.world.position.y,moved:false,mode:this.selectionMode,navigation:this.selectionMode==='lasso'&&e.shiftKey};canvas.setPointerCapture(e.pointerId);this.setAutoRotation(false);
        if(this.selectionMode==='lasso'&&!drag.navigation){const point=this.screenToGeo(e);drag.invalid=!point;drag.points=this.lassoPoints.concat(point?[point]:[]);drag.last=[e.clientX,e.clientY];}
      });
      canvas.addEventListener('pointermove',e=>{
        if(drag&&drag.mode!==this.selectionMode)drag=null;
        if(drag&&this.selectionMode==='lasso'&&!drag.navigation){
          if(Math.hypot(e.clientX-drag.x,e.clientY-drag.y)>4)drag.moved=true;
          if(drag.moved&&Math.hypot(e.clientX-drag.last[0],e.clientY-drag.last[1])>=4){const point=this.screenToGeo(e);if(!point)drag.invalid=true;else if(drag.points.length<900)drag.points.push(point);drag.last=[e.clientX,e.clientY];this.setLassoTrail(drag.points);}
          return;
        }
        if(drag){const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>4)drag.moved=true;if(drag.moved){clearTimeout(clickTimer);this.moveMap(dx,dy,drag);}this.tooltip.hidden=true;return;}
        if(this.selectionMode!=='boundary'){canvas.style.cursor='crosshair';this.tooltip.hidden=true;return;}
        const connection=this.pickConnection(e),f=connection?null:this.pick(e);if(this.hover!==(f?.id||null)){this.hover=f?.id||null;this.paint();}canvas.style.cursor=f||connection?'pointer':'grab';
        if(connection){this.tooltip.hidden=false;this.tooltip.textContent=`${connection.target_region.name} / ${connection.target_variable.name} · CLICK FOR EVIDENCE`;const b=this.host.getBoundingClientRect();this.tooltip.style.left=Math.min(b.width-250,e.clientX-b.left+16)+'px';this.tooltip.style.top=Math.max(12,e.clientY-b.top-38)+'px';return;}
        this.tooltip.hidden=!f;if(f){const row=this.results.get(f.id),o=row?.overall;this.tooltip.textContent=f.properties.name+(o?o.ok?' · '+(o.significant?o.direction.toUpperCase():'NO SIGNIFICANT TREND'):' · INSUFFICIENT DATA':' · CLICK TO SELECT');const b=this.host.getBoundingClientRect();this.tooltip.style.left=Math.min(b.width-250,e.clientX-b.left+16)+'px';this.tooltip.style.top=Math.max(12,e.clientY-b.top-38)+'px';}
      });
      canvas.addEventListener('pointerup',e=>{
        if(!drag)return;
        if(drag.mode!==this.selectionMode){drag=null;return;}
        if(this.selectionMode==='lasso'&&!drag.navigation){
          if(drag.invalid){this.lassoPoints=[];this.setLassoTrail([]);this.options.onSelectionError?.('Keep the entire outline on the visible Earth.');}
          else{this.lassoPoints=drag.points;this.setLassoTrail(this.lassoPoints);if(drag.moved)this.finishLasso();}
        }else if(!drag.moved&&['circle','square'].includes(this.selectionMode)){const point=this.screenToGeo(e);if(point)this.options.onSelectionPoint?.(point);else this.options.onSelectionError?.('Click a point on the visible Earth.');}
        else if(!drag.moved&&this.selectionMode==='boundary'){
          const connection=this.pickConnection(e),feature=connection?null:this.pick(e);
          clearTimeout(clickTimer);
          // Wait briefly so a double-click starts rotation without changing A/B.
          clickTimer=setTimeout(()=>{if(this.selectionMode!=='boundary')return;if(connection)this.options.onConnection?.(connection);else if(feature)this.options.onSelect?.(feature);},300);
        }
        drag=null;
      });
      canvas.addEventListener('pointercancel',()=>{drag=null;});canvas.addEventListener('pointerleave',()=>{this.hover=null;this.paint();this.tooltip.hidden=true;});
      canvas.addEventListener('dblclick',e=>{if(this.selectionMode!=='boundary'||this.targetBlend)return;e.preventDefault();clearTimeout(clickTimer);this.setAutoRotation(true);});
      canvas.addEventListener('wheel',e=>{
        e.preventDefault();clearTimeout(clickTimer);this.setAutoRotation(false);
        const multiplier=e.deltaMode===1?16:e.deltaMode===2?this.host.clientHeight:1;
        const dx=(e.shiftKey&&!e.deltaX?e.deltaY:e.deltaX)*multiplier,dy=(e.shiftKey&&!e.deltaX?0:e.deltaY)*multiplier;
        if(!e.ctrlKey&&Math.abs(dx)>Math.abs(dy)){this.moveMap(-Math.max(-180,Math.min(180,dx)));}
        else this.zoomBy(dy);
      },{passive:false});
    }
    frame(time) {
      requestAnimationFrame(this.frame);this.updateProjection();if(this.auto&&this.targetBlend===0)this.world.rotation.y+=Math.min(50,time-(this.lastFrame??time))*.000045;this.lastFrame=time;
      this.camera.position.set(0,0,this.zoom);this.camera.lookAt(0,0,0);this.world.updateMatrixWorld();
      for(const n of this.nodes){const p=n.feature.properties,b=p.bbox,c=centerOf(p);const xyz=this.blend>.5?flat(c[0],c[1],1.01):ll(c[0],c[1],1.01),v=new T.Vector3(...xyz).applyMatrix4(this.world.matrixWorld);
        const visible=(this.blend>.5||v.z>.18)&&((b[2]-b[0])*(b[3]-b[1])>10||this.zoom<1.6||this.selected.includes(n.feature.id));v.project(this.camera);
        n.label.hidden=!visible||Math.abs(v.x)>1||Math.abs(v.y)>1;n.label.style.transform=`translate(${(v.x+1)*this.host.clientWidth/2}px,${(1-v.y)*this.host.clientHeight/2}px) translate(-50%,-50%)`;
      }
      for(const p of this.packets){p.t=(time*.00015)%1;const point=p.curve.getPoint(p.t);if(p.plane){p.mesh.position.set(...flat(Math.atan2(point.x,point.z)/RAD,Math.asin(point.y/point.length())/RAD,1.018));p.mesh.scale.setScalar(Math.min(1,this.zoom*.7));}else p.mesh.position.copy(point);}
      for(const n of this.eventNodes){
        if(!n.el)continue;
        const xyz=this.blend>.5?flat(n.lon,n.lat,1.012):ll(n.lon,n.lat,1.012);
        const v=new T.Vector3(...xyz).applyMatrix4(this.world.matrixWorld);
        const front=this.blend>.5||v.z>.12;
        v.project(this.camera);
        const w=this.host.clientWidth, h=this.host.clientHeight;
        let x=(v.x+1)*w/2, y=(1-v.y)*h/2;
        const on=front&&Math.abs(v.x)<=1&&Math.abs(v.y)<=1;
        n.el.hidden=!on;
        if(!on)continue;
        // Keep the whole caption inside the visible stage; only the caption
        // moves, the dot keeps its true position. The label is centred on the
        // dot, so half of its measured width is what can overflow a panel.
        if(this.eventBounds){
          const half=(n.el.offsetWidth||120)/2+10;
          const left=this.eventBounds.left+half, right=this.eventBounds.right-half;
          if(right>left)x=Math.max(left,Math.min(right,x));
        }
        n.el.style.transform=`translate(${x}px,${y}px) translate(-50%,-50%)`;
      }
      this.renderer.render(this.scene,this.camera);
    }
  }
  TerraGlobe.buildFeatureGeometry=shapes;
  // Zoom scales camera altitude above the globe, keeping close-up movement gentle.
  TerraGlobe.navigationZoom=(zoom,delta,plane=false)=>{
    const factor=Math.exp(Math.max(-180,Math.min(180,delta))*.0009);
    return plane?Math.max(.08,Math.min(9,zoom*factor)):1+Math.max(.08,Math.min(5,(zoom-1)*factor));
  };
  TerraGlobe.navigationScale=(zoom,height,plane=false)=>{
    const scale=2*(plane?zoom:Math.max(.03,zoom-1))*Math.tan(19*RAD)/Math.max(200,height);
    return plane?scale:Math.min(.003,scale);
  };
  TerraGlobe.decodeBaseFaces=baseFaces;
  window.TerraGlobe=TerraGlobe;
})();
