/* Leaflet is bundled locally; map tiles and provider-backed planning need internet. */
window.FleetMap = (() => {
  let map, vehicle, destination, routeLayer, fences, trail, draft, animation;
  let following = false, mode = null, fenceSignature = "", tileFailed = false;
  let standardTiles, navigationTiles, activeTiles, selectedGeometry, activeLine, routeOutline, completedLine, activeRouteId;
  let lastPosition, lastTimestamp;
  const message = document.getElementById("map-message");
  const followButton = document.getElementById("follow");
  function label(text) { const node = document.createElement("span"); node.textContent = text; return node; }
  function init(onPick) {
    if (!window.L) {
      document.getElementById("map").textContent = "Map library unavailable. Use the coordinate fields below.";
      message.textContent = "Map unavailable; tracking data and manual controls still work.";
      followButton.disabled = true;
      return;
    }
    map = L.map("map", {zoomControl: true}).setView([17.4174, 78.4825], 15);
    standardTiles=L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, maxNativeZoom:19, keepBuffer:2, updateWhenIdle:true,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).on("tileerror", () => {
      tileFailed = true;
      message.textContent = "Map tiles unavailable. GPS markers, zones and coordinate controls still work.";
    }).addTo(map);activeTiles=standardTiles;
    navigationTiles=L.tileLayer('https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png',{
      maxZoom:20,maxNativeZoom:20,keepBuffer:2,updateWhenIdle:true,
      attribution:'&copy; <a href="https://stadiamaps.com/attribution/">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'});
    let navigationFailed=false;navigationTiles.on('tileerror',()=>{if(!navigationFailed&&activeTiles===navigationTiles){navigationFailed=true;setLayer('standard');message.textContent='Navigation tiles unavailable or rate limited. Standard Map selected.';}});
    fences = L.layerGroup().addTo(map);
    trail = L.polyline([], {color: "#41875d", weight: 3, opacity: .65, dashArray: "5 7"}).addTo(map);
    map.on("dragstart", () => setFollow(false));
    map.getContainer().addEventListener('wheel',()=>setFollow(false),{passive:true});
    map.getContainer().addEventListener('dblclick',()=>setFollow(false));
    map.getContainer().addEventListener('touchstart',event=>{if(event.touches.length>1)setFollow(false);},{passive:true});
    map.getContainer().addEventListener('keydown',event=>{if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','+','-','='].includes(event.key))setFollow(false);});
    map.getContainer().addEventListener('click',e=>{if(e.target.closest('.leaflet-control-zoom'))setFollow(false);});
    map.on('zoomend',()=>{map.getContainer().dataset.zoom=String(map.getZoom());styleRoute();});
    map.getContainer().dataset.zoom=String(map.getZoom());
    map.on("click", event => {
      if (!mode) return;
      const selected = mode;
      mode = null;
      document.getElementById("map-mode").hidden = true;
      map.getContainer().style.cursor = "";
      onPick(selected, event.latlng.lat, event.latlng.lng);
      if (selected === "destination") previewDestination(event.latlng.lat, event.latlng.lng);
    });
    followButton.addEventListener("click", () => setFollow(!following));
    followButton.disabled=true;
    setFollow(false);
    new ResizeObserver(() => map.invalidateSize()).observe(document.getElementById("map"));
  }
  function setFollow(value) {
    if(map&&!value)map.stop();
    following = NavigationGeometry.cameraState({following,zoom:map?.getZoom()},value?'FOLLOW':'EXPLORE').following;
    followButton.setAttribute("aria-pressed", String(value));
    if(map)map.getContainer().dataset.follow=String(value);
    if (map && vehicle && value) map.flyTo(cameraCenter(vehicle.getLatLng(),17),17,{duration:.65});
    if(map&&vehicle&&value)map.getContainer().scrollIntoView({block:'center',behavior:'smooth'});
  }
  function cameraCenter(point,zoom=map.getZoom()){return map.unproject(map.project(point,zoom).subtract([0,map.getSize().y*.14]),zoom);}
  function pick(selected) {
    if (!map) return;
    mode = selected;
    const hint = document.getElementById("map-mode");
    hint.textContent = selected === "destination" ? "Click the map to choose your destination · Esc to cancel" : "Click the map to choose a geofence center · Esc to cancel";
    hint.hidden = false;
    map.getContainer().style.cursor = "crosshair";
    document.getElementById("map").scrollIntoView({behavior: "smooth", block: "center"});
  }
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      mode = null;
      document.getElementById("map-mode").hidden = true;
      if (map) map.getContainer().style.cursor = "";
    }
  });
  function destinationIcon() {
    return L.divIcon({className: "vehicle-map-icon", html: '<div class="destination-bubble">◆</div>', iconSize: [26, 26], iconAnchor: [13, 13]});
  }
  function previewDestination(lat, lon) {
    if (!map) return;
    if (draft) map.removeLayer(draft);
    draft = L.marker([lat, lon], {icon: destinationIcon(), opacity: .65}).addTo(map).bindTooltip("Selected destination (not started)");
  }
  function animateVehicle(latlng) {
    cancelAnimationFrame(animation);
    const start = vehicle.getLatLng();
    const started = performance.now();
    const duration = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 850;
    function frame(now) {
      const progress = duration ? Math.min(1, (now - started) / duration) : 1;
      vehicle.setLatLng([start.lat + (latlng[0] - start.lat) * progress, start.lng + (latlng[1] - start.lng) * progress]);
      if (progress < 1) animation = requestAnimationFrame(frame);
    }
    animation = requestAnimationFrame(frame);
  }
  function update(snapshot, history) {
    if (!map) return;
    const location = snapshot.location;
    if (location) {
      followButton.disabled=false;
      const latlng = [location.lat, location.lon];
      if (!vehicle) {
        const icon = L.divIcon({className: "vehicle-map-icon", html: '<div class="navigation-arrow"><svg viewBox="0 0 24 24"><path d="M12 2 21 21 12 17 3 21Z"/></svg></div>', iconSize: [38, 38], iconAnchor: [19, 19]});
        vehicle = L.marker(latlng, {icon, zIndexOffset: 1000}).addTo(map).bindTooltip("FM01", {permanent: true, direction: "top", offset: [0, -21]});
        if (following) map.setView(cameraCenter(L.latLng(latlng),17),17);
      } else if(lastTimestamp!==location.timestamp)animateVehicle(latlng);
      if(lastPosition&&lastTimestamp!==location.timestamp){const heading=NavigationGeometry.bearing([lastPosition[1],lastPosition[0]],[location.lon,location.lat]);if(Math.hypot(lastPosition[0]-location.lat,lastPosition[1]-location.lon)>.000001)vehicle.getElement().querySelector('svg').style.transform=`rotate(${heading}deg)`;}
      vehicle.getElement().classList.toggle('vehicle-deviated',snapshot.trip?.route_status==='DEVIATED');
      if (following && lastTimestamp!==location.timestamp) map.panTo(cameraCenter(L.latLng(latlng)), {animate: true, duration: .8});
      lastTimestamp=location.timestamp;lastPosition=latlng;
      trail.setLatLngs([...history].reverse().map(point => [point.lat, point.lon]));
    } else {
      followButton.disabled=true;
      cancelAnimationFrame(animation);
      if (vehicle) { map.removeLayer(vehicle); vehicle = null; }
      trail.setLatLngs([]);
    }
    const signature = JSON.stringify(snapshot.geofences.map(f=>[f.geofence_id,f.enabled,f.center_lat,f.center_lon,f.radius_m]));
    if (signature !== fenceSignature) {
      fences.clearLayers();
      snapshot.geofences.filter(fence => fence.enabled).forEach(fence => {
        L.circle([fence.center_lat, fence.center_lon], {radius: fence.radius_m,
          color: "#7f9d5f", weight: 1.5, dashArray: "5 5", fillColor: "#a3bd78", fillOpacity: .16})
          .bindTooltip(label(fence.name)).addTo(fences);
      });
      fenceSignature = signature;
    }
    if (snapshot.trip) {
      if (draft) { map.removeLayer(draft); draft = null; }
      const trip = snapshot.trip;
      if(!destination)destination = L.marker([trip.destination_lat, trip.destination_lon], {icon: destinationIcon()}).bindTooltip(label(trip.destination_label)).addTo(map);
      else destination.setLatLng([trip.destination_lat,trip.destination_lon]);
      if(snapshot.eta?.geometry&&trip.route_id!==activeRouteId)showRoutes([{route_id:trip.route_id,geometry:snapshot.eta.geometry}],trip.route_id,null,false);
      if(selectedGeometry&&activeLine){const parts=NavigationGeometry.split(selectedGeometry.coordinates,Math.max(0,trip.route_progress_m-trip.route_offset_m));activeLine.setLatLngs(parts.remaining.map(p=>[p[1],p[0]]));routeOutline.setLatLngs(parts.remaining.map(p=>[p[1],p[0]]));completedLine.setLatLngs(parts.travelled.map(p=>[p[1],p[0]]));map.getContainer().dataset.progress=String(trip.progress_percent);}
    }
    if (!tileFailed) message.textContent='Blue: remaining navigation route · Grey: travelled route · Dashed: recorded GPS path';
  }
  let plannedLayer, plannedMarkers, reviewPick, pointLayer,changeMarker,recordedLine;
  let pointerStart, selectionDragged=false;
  function styleRoute(){
    if(!activeLine)return;
    const width=map.getZoom()<14?5:map.getZoom()<17?6:7;
    activeLine.setStyle({weight:width});
    routeOutline.setStyle({weight:width+3});
    completedLine.setStyle({weight:width});
  }
  document.addEventListener('pointerdown',event=>{pointerStart=[event.clientX,event.clientY];selectionDragged=false;},true);
  document.addEventListener('pointermove',event=>{if(pointerStart&&Math.hypot(event.clientX-pointerStart[0],event.clientY-pointerStart[1])>5)selectionDragged=true;},true);
  function showRoutes(routes, selectedId, onSelect, fit = true) {
    if (!map) return;
    if (plannedLayer) map.removeLayer(plannedLayer);
    if (plannedMarkers) map.removeLayer(plannedMarkers);
    plannedLayer = L.layerGroup().addTo(map);
    plannedMarkers = L.layerGroup().addTo(map);
    routes.filter(r=>r.route_id!==selectedId).forEach(route=>L.geoJSON(route.geometry,{style:{color:'#8798ab',weight:4,opacity:.5,lineCap:'round',lineJoin:'round'}}).on('click',()=>onSelect?.(route)).addTo(plannedLayer));
    const selected = routes.find(route => route.route_id === selectedId);
    const fitButton=document.getElementById('fit-route');if(fitButton)fitButton.disabled=!selected;
    if (selected) {
      selectedGeometry=selected.geometry;activeRouteId=selected.route_id;
      const points=selected.geometry.coordinates.map(p=>[p[1],p[0]]);
      routeOutline=L.polyline(points,{color:'#1555a2',weight:10,opacity:.8,lineCap:'round',lineJoin:'round'}).addTo(plannedLayer);
      activeLine=L.polyline(points,{color:'#2580ff',weight:7,opacity:1,lineCap:'round',lineJoin:'round'}).on('click',()=>onSelect?.(selected)).addTo(plannedLayer);
      completedLine=L.polyline([],{color:'#a0adba',weight:7,lineCap:'round',lineJoin:'round'}).addTo(plannedLayer);
      styleRoute();
      const bounds = L.geoJSON(selected.geometry).getBounds();
      if (fit) { setFollow(false); map.fitBounds(bounds,{padding:[35,35]}); }
    }else{selectedGeometry=null;activeRouteId=null;}
  }
  function selectPoint(callback) {
    if (!map) return;
    map.getContainer().style.cursor = 'crosshair';
    if (reviewPick) map.getContainer().removeEventListener('click',reviewPick,true);
    reviewPick = event => {
      if (selectionDragged||event.target.closest('.leaflet-control,.leaflet-marker-icon,.leaflet-interactive')) return;
      map.getContainer().removeEventListener('click',reviewPick,true);
      map.getContainer().style.cursor='';
      const latlng = map.mouseEventToLatLng(event);
      callback(latlng.lat,latlng.lng);
    };
    map.getContainer().addEventListener('click',reviewPick,true);
    document.getElementById('map').scrollIntoView({block:'center',behavior:'smooth'});
  }
  function plannerPoints(start, end, onChange) {
    if (!map) return;
    if (pointLayer) map.removeLayer(pointLayer);
    pointLayer = L.layerGroup().addTo(map);
    for (const [name,point,color] of [['start',start,'#15945e'],['destination',end,'#dc3838']]) {
      if (!point) continue;
      const icon=L.divIcon({className:'planner-marker',html:`<span style="background:${color}">${name==='start'?'S':'D'}</span>`,iconSize:[30,36],iconAnchor:[15,30]});
      const marker=L.marker([point.lat,point.lon],{icon,draggable:true,zIndexOffset:1200}).addTo(pointLayer).bindTooltip(name==='start'?'Start · drag to adjust':'Destination · drag to adjust');
      marker.on('dragend',()=>{const p=marker.getLatLng();onChange(name,p.lat,p.lng);});
      marker.getElement().dataset.point=name;
      marker.getElement().dataset.lat=String(point.lat);
      marker.getElement().dataset.lon=String(point.lon);
    }
  }
  function savedPlaces(places) {
    if (!map) return;
    places.forEach(place=>L.marker([place.lat,place.lon],{icon:L.divIcon({className:'home-marker',html:'⌂',iconSize:[28,28],iconAnchor:[14,14]})}).bindTooltip(label(`${place.name} · ${place.lat}, ${place.lon}`)).addTo(map));
  }
  function goTo(place) { if(map){setFollow(false);map.setView([place.lat,place.lon],16);document.getElementById('map').scrollIntoView({block:'center',behavior:'smooth'});} }
  function cancelSelection(){if(map&&reviewPick){map.getContainer().removeEventListener('click',reviewPick,true);map.getContainer().style.cursor='';reviewPick=null;}}
  document.addEventListener('keydown',event=>{if(event.key==='Escape')cancelSelection();});
  function fitRoute(){if(map&&selectedGeometry){setFollow(false);map.fitBounds(L.geoJSON(selectedGeometry).getBounds(),{padding:[40,40],animate:true});}}
  function setLayer(name){if(!map)return;const tiles=name==='navigation'&&['localhost','127.0.0.1'].includes(location.hostname)?navigationTiles:standardTiles;if(activeTiles!==tiles){map.removeLayer(activeTiles);tiles.addTo(map);activeTiles=tiles;}if(document.getElementById('map-layer'))document.getElementById('map-layer').value=tiles===navigationTiles?'navigation':'standard';}
  function previewChange(point){clearChange();if(map)changeMarker=L.marker([point.lat,point.lon],{icon:destinationIcon(),opacity:.7,zIndexOffset:1300}).bindTooltip(label('Proposed destination · not applied')).addTo(map);}
  function clearChange(){if(map&&changeMarker){map.removeLayer(changeMarker);changeMarker=null;}}
  function recordedPath(points){if(!map)return;if(!recordedLine)recordedLine=L.polyline([],{color:'#a0adba',weight:5,opacity:.85}).addTo(map);recordedLine.setLatLngs(points.map(p=>[p.lat,p.lon]));recordedLine.bringToBack();}
  return {init, pick, update, previewDestination, showRoutes, selectPoint, plannerPoints, savedPlaces, goTo, cancelSelection,fitRoute,setLayer,previewChange,clearChange,recordedPath};
})();
