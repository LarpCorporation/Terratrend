/* Floating map cards: drag the heading, collapse the body, keep controls reachable. */
const mapPanelState=new Map();
function saveMapPanel(id){
  const panel=$(id),saved={collapsed:panel.classList.contains('collapsed')};
  if(panel.dataset.moved==='true'){saved.x=panel.offsetLeft;saved.y=panel.offsetTop;}
  try{localStorage.setItem('terratrend-panel-'+id,JSON.stringify(saved));}catch(_){/* Private browsing may disable storage. */}
}
function placeMapPanel(panel,x,y){
  const parent=panel.offsetParent;if(!parent)return;
  const position=window.TerraPanelPosition(x,y,panel.offsetWidth,panel.offsetHeight,parent.clientWidth,parent.clientHeight);
  panel.style.left=position.x+'px';panel.style.top=position.y+'px';panel.style.right='auto';panel.dataset.moved='true';
}
function expandMapPanel(id,expanded=true,persist=true){
  const panel=$(id),body=panel.querySelector('[data-panel-body]'),button=panel.querySelector('[data-panel-collapse]');
  panel.classList.toggle('collapsed',!expanded);body.hidden=!expanded;
  button.textContent=expanded?'−':'+';button.setAttribute('aria-expanded',String(expanded));
  button.setAttribute('aria-label',(expanded?'Collapse ':'Expand ')+(id==='k-region-card'?'area':'selection')+' panel');button.title=expanded?'Collapse panel':'Expand panel';
  if(panel.dataset.moved==='true')placeMapPanel(panel,panel.offsetLeft,panel.offsetTop);
  if(persist)saveMapPanel(id);
}
function wireMapPanels(){
  for(const id of ['k-region-card','selection-workbench']){
    const panel=$(id),header=panel.querySelector('[data-panel-header]'),handle=panel.querySelector('[data-panel-drag]');
    mapPanelState.set(id,null);
    header.addEventListener('pointerdown',event=>{
      if(event.button!==0||event.target.closest('button:not([data-panel-drag])'))return;
      event.preventDefault();const start={x:event.clientX,y:event.clientY,left:panel.offsetLeft,top:panel.offsetTop};
      mapPanelState.set(id,start);header.setPointerCapture(event.pointerId);panel.classList.add('dragging');
    });
    header.addEventListener('pointermove',event=>{const drag=mapPanelState.get(id);if(drag)placeMapPanel(panel,drag.left+event.clientX-drag.x,drag.top+event.clientY-drag.y);});
    const end=()=>{if(!mapPanelState.get(id))return;mapPanelState.set(id,null);panel.classList.remove('dragging');saveMapPanel(id);};
    header.addEventListener('pointerup',end);header.addEventListener('pointercancel',end);header.addEventListener('lostpointercapture',end);
    handle.addEventListener('keydown',event=>{
      const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];if(!delta)return;
      event.preventDefault();const step=event.shiftKey?40:10;placeMapPanel(panel,panel.offsetLeft+delta[0]*step,panel.offsetTop+delta[1]*step);saveMapPanel(id);
    });
    panel.querySelector('[data-panel-collapse]').onclick=()=>expandMapPanel(id,panel.classList.contains('collapsed'));
    try{const saved=JSON.parse(localStorage.getItem('terratrend-panel-'+id)||'null');if(saved){expandMapPanel(id,!saved.collapsed,false);if(Number.isFinite(saved.x)&&Number.isFinite(saved.y))placeMapPanel(panel,saved.x,saved.y);}}catch(_){}
  }
  const observer=new ResizeObserver(()=>{for(const id of mapPanelState.keys()){const p=$(id);if(p.dataset.moved==='true'&&!p.hidden)placeMapPanel(p,p.offsetLeft,p.offsetTop);}});
  observer.observe(document.querySelector('.hud-grid'));
  for(const id of mapPanelState.keys())observer.observe($(id));
}
window.TerraPanelPosition=(x,y,width,height,parentWidth,parentHeight)=>({
  x:Math.max(8,Math.min(Math.max(8,parentWidth-width-8),x)),
  y:Math.max(8,Math.min(Math.max(8,parentHeight-height-8),y))
});
