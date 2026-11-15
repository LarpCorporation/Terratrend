/* Geographic selection geometry. Kilometres refer to the Earth surface, not
   screen pixels, so selections retain their size through zoom/projection. */
(function(root){
  'use strict';
  const R=6371.0088, RAD=Math.PI/180;
  const longitude=x=>((x+180)%360+360)%360-180;
  const round=x=>Math.round(x*1e6)/1e6;
  function coordinate(point){
    if(!Array.isArray(point)||point.length<2||!point.slice(0,2).every(Number.isFinite)||Math.abs(point[0])>180||Math.abs(point[1])>90)throw new Error('Use longitude −180…180 and latitude −90…90.');
    return [round(point[0]),round(point[1])];
  }
  function unwrap(points){
    const out=[];
    for(const p of points){let x=p[0];if(out.length){while(x-out.at(-1)[0]>180)x-=360;while(x-out.at(-1)[0]<-180)x+=360;}out.push([x,p[1]]);}
    return out;
  }
  function area(geometry){
    const polys=geometry.type==='Polygon'?[geometry.coordinates]:geometry.coordinates;
    const ringArea=ring=>{const p=unwrap(ring);let sum=0;for(let i=1;i<p.length;i++)sum+=(p[i][0]-p[i-1][0])*RAD*(Math.sin(p[i][1]*RAD)+Math.sin(p[i-1][1]*RAD));return Math.abs(sum)*R*R/2;};
    return polys.reduce((sum,p)=>sum+ringArea(p[0])-p.slice(1).reduce((s,r)=>s+ringArea(r),0),0);
  }
  function destination(center,distance,bearing){
    const phi=center[1]*RAD,lambda=center[0]*RAD,theta=bearing*RAD,d=distance/R;
    const lat=Math.asin(Math.sin(phi)*Math.cos(d)+Math.cos(phi)*Math.sin(d)*Math.cos(theta));
    const lon=lambda+Math.atan2(Math.sin(theta)*Math.sin(d)*Math.cos(phi),Math.cos(d)-Math.sin(phi)*Math.sin(lat));
    return [round(longitude(lon/RAD)),round(lat/RAD)];
  }
  function intersects(a,b,c,d){
    const cross=(p,q,r)=>(q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0]);
    const on=(p,q,r)=>Math.abs(cross(p,q,r))<1e-10&&r[0]>=Math.min(p[0],q[0])-1e-10&&r[0]<=Math.max(p[0],q[0])+1e-10&&r[1]>=Math.min(p[1],q[1])-1e-10&&r[1]<=Math.max(p[1],q[1])+1e-10;
    const x=cross(a,b,c),y=cross(a,b,d),z=cross(c,d,a),w=cross(c,d,b);
    return (x*y<0&&z*w<0)||on(a,b,c)||on(a,b,d)||on(c,d,a)||on(c,d,b);
  }
  function feature(kind,geometry,center,details={}){
    const pts=(geometry.type==='Polygon'?[geometry.coordinates]:geometry.coordinates).flatMap(p=>p[0]);
    const bbox=[Math.min(...pts.map(p=>p[0])),Math.min(...pts.map(p=>p[1])),Math.max(...pts.map(p=>p[0])),Math.max(...pts.map(p=>p[1]))];
    const areaKm2=area(geometry);
    if(!(areaKm2>.001))throw new Error('Select an area larger than 1,000 m².');
    return {type:'Feature',geometry,properties:{name:details.name||({circle:`Circle · ${details.size_km} km radius`,square:`Square · ${details.size_km} km side`,bounds:'Coordinate bounds',lasso:'Lasso area'})[kind],level:'custom',selection_kind:kind,center:center.map(round),bbox,area_km2:areaKm2,...details}};
  }
  function shape(kind,center,size){
    center=coordinate(center);size=Number(size);
    if(!['circle','square'].includes(kind)||!Number.isFinite(size)||size<1||size>5000)throw new Error('Choose a size between 1 and 5,000 km.');
    const extent=kind==='circle'?size:size/Math.sqrt(2);
    if(Math.abs(center[1])+extent/R/RAD>=89.9)throw new Error('Move the centre away from the pole or reduce the size.');
    let points=[];
    if(kind==='circle')for(let b=0;b<360;b+=4)points.push(destination(center,size,b));
    else{
      // Four equal-distance corners; interpolate each edge on a great circle.
      const corners=[315,45,135,225].map(b=>destination(center,extent,b));
      const vec=p=>[Math.cos(p[1]*RAD)*Math.cos(p[0]*RAD),Math.cos(p[1]*RAD)*Math.sin(p[0]*RAD),Math.sin(p[1]*RAD)];
      for(let j=0;j<4;j++){
        const a=vec(corners[j]),b=vec(corners[(j+1)%4]),angle=Math.acos(Math.max(-1,Math.min(1,a.reduce((s,x,i)=>s+x*b[i],0))));
        const n=Math.max(2,Math.ceil(size/100));
        for(let i=0;i<n;i++){const t=i/n,u=Math.sin((1-t)*angle)/Math.sin(angle),v=Math.sin(t*angle)/Math.sin(angle),p=a.map((x,k)=>u*x+v*b[k]);points.push([round(longitude(Math.atan2(p[1],p[0])/RAD)),round(Math.atan2(p[2],Math.hypot(p[0],p[1]))/RAD)]);}
      }
    }
    points.push(points[0].slice());
    return feature(kind,{type:'Polygon',coordinates:[points]},center,{size_km:size});
  }
  function bounds(west,south,east,north){
    [west,south]=coordinate([Number(west),Number(south)]);[east,north]=coordinate([Number(east),Number(north)]);
    if(north<=south)throw new Error('North latitude must be greater than south latitude.');
    if(west===east)throw new Error('West and east must define a nonzero width.');
    const width=east>west?east-west:east+360-west,polys=[];
    const pieces=Math.ceil(width/120);
    for(let j=0;j<pieces;j++){
      const x0=west+width*j/pieces,x1=west+width*(j+1)/pieces,ring=[];
      // Densify parallel edges so longitude unwrapping retains wide boxes.
      const n=Math.max(1,Math.ceil((x1-x0)/5));
      for(let i=0;i<=n;i++)ring.push([round(longitude(x0+(x1-x0)*i/n)),south]);
      for(let i=n;i>=0;i--)ring.push([round(longitude(x0+(x1-x0)*i/n)),north]);
      ring.push(ring[0].slice());polys.push([ring]);
    }
    return feature('bounds',{type:polys.length===1?'Polygon':'MultiPolygon',coordinates:polys.length===1?polys[0]:polys},[longitude(west+width/2),(south+north)/2],{bounds:[west,south,east,north],crosses_dateline:west>east});
  }
  function lasso(raw){
    const points=[];
    for(const p of raw){const q=coordinate(p),last=points.at(-1);if(!last||Math.hypot(q[0]-last[0],q[1]-last[1])>1e-6)points.push(q);}
    if(points.length>1&&points[0].every((x,i)=>x===points.at(-1)[i]))points.pop();
    if(points.length<3)throw new Error('Draw an outline with at least three distinct points.');
    if(points.length>1000)throw new Error('Draw a shorter outline with fewer than 1,000 points.');
    points.push(points[0].slice());const unwrapped=unwrap(points);
    if(Math.abs(unwrapped[0][0]-unwrapped.at(-1)[0])>180)throw new Error('Lassos around a pole are not supported. Use coordinate bounds instead.');
    for(let i=0;i<unwrapped.length-1;i++)for(let j=i+2;j<unwrapped.length-1;j++){
      if(i===0&&j===unwrapped.length-2)continue;
      if(intersects(unwrapped[i],unwrapped[i+1],unwrapped[j],unwrapped[j+1]))throw new Error('The lasso crosses itself. Redraw one simple outline.');
    }
    const p=unwrapped.slice(0,-1),center=[longitude(p.reduce((s,p)=>s+p[0],0)/p.length),p.reduce((s,p)=>s+p[1],0)/p.length];
    return feature('lasso',{type:'Polygon',coordinates:[points]},center);
  }
  async function identify(feature){
    const g=feature.geometry,polys=g.type==='Polygon'?[g.coordinates]:g.coordinates;
    const canonical=g.type+':'+polys.map(p=>p[0].map(v=>v.map(x=>(x===0?0:x).toFixed(6)).join(',')).join(';')).join('|');
    const hash=await root.crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical));
    const id='custom:'+Array.from(new Uint8Array(hash),v=>v.toString(16).padStart(2,'0')).join('').slice(0,20);
    return {...feature,id,properties:{...feature.properties,id,geometry_version:id.slice(7)}};
  }
  const api={R,area,shape,bounds,lasso,unwrap,destination,identify};
  root.TerraSelection=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window==='undefined'?globalThis:window);
