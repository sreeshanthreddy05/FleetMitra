// Exercise the actual browser modules with a small Leaflet/DOM boundary adapter.
// Real tile rendering and gesture behavior are verified separately in the browser.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const geometry=require('../static/js/navigation_geometry.js');

function element(){
  return {style:{},dataset:{},attrs:{},children:[],events:{},value:'',
    classList:{toggle(){}},setAttribute(k,v){this.attrs[k]=v;},
    removeAttribute(k){delete this.attrs[k];},
    addEventListener(k,v){this.events[k]=v;},removeEventListener(){},
    append(child){this.children.push(child);},replaceChildren(){this.children=[];},
    scrollIntoView(){},querySelector(){return this.svg??=(element());}};
}
function mapHarness(){
  const nodes=new Map(), lines=[],markers=[],events={},camera=[],areas=[];
  const document={getElementById(id){if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);},
    createElement:element,addEventListener(){}};
  const point=p=>Array.isArray(p)?{lat:p[0],lng:p[1]}:p;
  const map={zoom:15,on(k,v){events[k]=v;return this;},
    setView(p,z){this.zoom=z;return this;},getZoom(){return this.zoom;},
    getContainer(){return document.getElementById('map');},getSize(){return {y:600};},
    project(p){return {subtract(){return p;}};},unproject(p){return p;},
    flyTo(p,z){this.zoom=z;camera.push(['fly',p,z]);return this;},
    panTo(p){camera.push(['pan',p]);},stop(){camera.push(['stop']);},
    fitBounds(){camera.push(['fit']);},removeLayer(){},invalidateSize(){}};
  const layer=()=>({addTo(){return this;},on(){return this;},clearLayers(){},bindTooltip(){return this;}});
  const L={map:()=>map,tileLayer:layer,layerGroup:layer,circle:layer,divIcon:x=>x,latLng:point,
    geoJSON:(data,options)=>{const area={...layer(),style:options?.style,getBounds(){return {};}};areas.push(area);return area;},
    polyline(points,style){const line={...layer(),points,style,
      setLatLngs(p){this.points=p;return this;},setStyle(s){Object.assign(this.style,s);return this;}};
      lines.push(line);return line;},
    marker(p,options){const marker={...layer(),position:point(p),options,node:element(),
      getElement(){return this.node;},getLatLng(){return this.position;},
      setLatLng(p){this.position=point(p);return this;}};markers.push(marker);return marker;}};
  const context={document,L,NavigationGeometry:geometry,performance:{now:()=>1},
    ResizeObserver:class{observe(){}},cancelAnimationFrame(){},requestAnimationFrame:fn=>{fn(1);return 1;},
    window:{L,matchMedia:()=>({matches:true})},location:{hostname:'localhost'}};
  vm.runInNewContext(fs.readFileSync('static/js/map.js','utf8'),context);
  const api=context.window.FleetMap;api.init(()=>{});
  return {api,map,nodes,lines,markers,events,camera,areas};
}
const route={route_id:7,geometry:{type:'LineString',coordinates:[[78,17],[78.01,17],[78.01,17.01]]}};
function snapshot(timestamp='one',lat=17,lon=78){return {geofences:[],location:{lat,lon,timestamp},trip:null};}

test('Home and freely chosen endpoint markers retain exact coordinates',()=>{
  const h=mapHarness(),home={lat:17.415666,lon:78.573060};
  h.api.savedPlaces([{...home,name:'Home'}]);
  h.api.plannerPoints(home,{lat:17.5,lon:78.6},()=>{});
  assert.equal(h.markers[0].position.lat,home.lat);
  assert.equal(h.markers[0].position.lng,home.lon);
  assert.equal(h.markers[1].node.dataset.lat,String(home.lat));
  assert.equal(h.markers[2].node.dataset.lon,'78.6');
  h.api.plannerPoints({lat:18,lon:79},home,()=>{});
  assert.equal(h.markers.at(-1).position.lng,home.lon);
});

test('selected route dominates alternatives and progress updates existing geometry layers',()=>{
  const h=mapHarness();h.api.showRoutes([route,{...route,route_id:8}],7);
  const active=h.lines.find(line=>line.style.color==='#2580ff');
  const complete=h.lines.find(line=>line.style.color==='#a0adba');
  const outline=h.lines.find(line=>line.style.color==='#1555a2');
  assert(outline.style.weight>active.style.weight);
  assert(h.areas[0].style.weight<active.style.weight);
  assert.equal(h.areas[0].style.color,'#8798ab');
  const count=h.lines.length,data=snapshot();
  data.trip={route_id:7,destination_lat:17.01,destination_lon:78.01,destination_label:'College',
    route_status:'ON_ROUTE',route_progress_m:geometry.meters([78,17],[78.005,17]),route_offset_m:0,progress_percent:25};
  h.api.update(data,[]);
  assert.equal(h.lines.length,count);
  assert.equal(complete.points.length,2);
  assert(Math.abs(active.points[0][1]-78.005)<1e-7);
  assert.equal(active.points.at(-1)[0],17.01);
  assert.equal(h.nodes.get('map').dataset.progress,'25');
  h.map.zoom=18;h.events.zoomend();assert.equal(active.style.weight,7);
});

test('follow zooms to 17, gestures stop camera animation, and Home preserves route selection',()=>{
  const h=mapHarness();h.api.showRoutes([route],7);h.api.update(snapshot(),[]);
  const toggle=h.nodes.get('follow').events.click;
  toggle();assert.equal(h.map.zoom,17);assert.equal(h.nodes.get('map').dataset.follow,'true');
  h.nodes.get('map').events.keydown({key:'ArrowRight'});
  assert.equal(h.nodes.get('map').dataset.follow,'false');assert.equal(h.map.zoom,17);
  assert.equal(h.camera.at(-1)[0],'stop');
  toggle();h.nodes.get('map').events.touchstart({touches:[{},{}]});
  assert.equal(h.nodes.get('map').dataset.follow,'false');
  const lines=h.lines.length;h.api.goTo({lat:17.415666,lon:78.573060});
  assert.equal(h.lines.length,lines);h.api.fitRoute();assert.equal(h.camera.at(-1)[0],'fit');
});

test('fresh positions move and rotate the existing navigation marker',()=>{
  const h=mapHarness();h.api.update(snapshot(),[]);const marker=h.markers[0];
  h.api.update(snapshot('two',17,78.001),[]);
  assert.equal(h.markers.length,1);assert.equal(marker.position.lng,78.001);
  assert.match(marker.node.svg.style.transform,/rotate\(90/);
});

test('keyboard search selection passes the provider coordinates and label to the planner',async()=>{
  const nodes=new Map();for(const name of ['start','destination'])for(const prefix of ['search-','results-','search-status-'])nodes.set(prefix+name,element());
  let pending,selected,centered;
  const item={lat:17.4025091,lon:78.5612562,label:'Uppal, Telangana, India'};
  const document={getElementById:id=>nodes.get(id),createElement:element};
  const context={document,AbortController,clearTimeout(){},setTimeout(fn){pending=fn;},
    fetch:async()=>({ok:true,json:async()=>({results:[item]})}),
    FleetMap:{goTo:p=>centered=p},window:{FleetPlanner:{setPoint:(...p)=>selected=p}}};
  vm.runInNewContext(fs.readFileSync('static/js/search.js','utf8'),context);
  const input=nodes.get('search-destination');input.value='Uppal Hyderabad';input.oninput();await pending();
  input.onkeydown({key:'ArrowDown',preventDefault(){}});input.onkeydown({key:'Enter',preventDefault(){}});
  assert.deepEqual(selected,['destination',item.lat,item.lon,item.label]);
  assert.equal(centered,item);assert.equal(input.value,item.label);
  assert.equal(nodes.get('results-destination').children.length,0);
});
