/* Review controls use persisted server state. Browser timers never advance simulation. */
(() => {
  const $ = id => document.getElementById(id);
  let selected, routes = [], state, busy = false, initialized = false, lastNotification = 0, lastSummary = 0;
  let home, recommendedId, planRevision=0, planTimer, planning=false;
  const alertQueue=[];
  function showNextAlert(){if($('navigation-alert').open||!alertQueue.length)return;const n=alertQueue.shift();$('navigation-alert-title').textContent=n.title;$('navigation-alert-message').textContent=n.message+(n.kind==='ROUTE_DEVIATION'?' Requesting a replacement road route when automatic rerouting is enabled.':'');$('navigation-alert').show();}
  $('navigation-alert').addEventListener('close',showNextAlert);
  let audio, muted = localStorage.getItem('fleetmitra-muted') === 'true';
  const safe = (tag, text, cls='') => { const node=document.createElement(tag);node.textContent=text;node.className=cls;return node; };
  const navigation=document.createElement('div');navigation.className='navigation-workspace';const tracking=document.querySelector('.tracking-grid');tracking.before(navigation);navigation.append(tracking,$('review-controls'));
  const km = meters => (meters / 1000).toFixed(2);
  function toast(message,error=false){$('notice').textContent=message;$('notice').className='notice'+(error?' error':'');$('notice').hidden=false;setTimeout(()=>$('notice').hidden=true,9000);}
  async function api(path, data, method='POST') {
    const response = await fetch(path,{method:data===undefined?'GET':method,headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data),signal:AbortSignal.timeout(12000)});
    const result=await response.json();if(!response.ok)throw new Error(result.error||'Request failed');return result;
  }
  async function action(callback){if(busy)return;busy=true;try{await callback();await refresh();}catch(error){toast(error.message,true);}finally{busy=false;buttons();}}
  function sound(kind){
    if(muted||!audio||audio.state!=='running')return;
    const frequencies=kind==='DESTINATION_REACHED'?[523,659,784]:kind==='ROUTE_DEVIATION'?[330,220,330]:[660];
    frequencies.forEach((frequency,index)=>{const oscillator=audio.createOscillator(),gain=audio.createGain(),time=audio.currentTime+index*.18;oscillator.frequency.value=frequency;gain.gain.setValueAtTime(.0001,time);gain.gain.exponentialRampToValueAtTime(.08,time+.015);gain.gain.exponentialRampToValueAtTime(.0001,time+.16);oscillator.connect(gain);gain.connect(audio.destination);oscillator.start(time);oscillator.stop(time+.18);});
    $('sound-toggle').dataset.lastPlayed=kind;
  }
  document.addEventListener('pointerdown',()=>{try{audio=audio||new (window.AudioContext||window.webkitAudioContext)();audio.resume().catch(()=>{});}catch{}},{once:true});
  function soundLabel(){$('sound-toggle').textContent=muted?'Sound Off':'Sound On';}
  soundLabel();$('sound-toggle').onclick=()=>{muted=!muted;localStorage.setItem('fleetmitra-muted',muted);soundLabel();};
  $('notification-toggle').onclick=()=>{$('notification-center').hidden=!$('notification-center').hidden;$('notification-toggle').setAttribute('aria-expanded',String(!$('notification-center').hidden));};
  $('read-all').onclick=()=>action(()=>api('/api/notifications/read-all',{}));
  function renderOptions(items,target,reroute=false){
    $(target).replaceChildren();items.forEach((route,index)=>{const row=safe('div', '', 'route-option'+(selected?.route_id===route.route_id?' selected':''));row.style.borderLeft=`5px solid ${['#2563eb','#15945e','#e58b21'][index%3]}`;const traffic=route.traffic;row.append(safe('span',`Route ${index+1} · ${route.method} · ${km(route.distance_m)} km · Base ${Math.ceil(route.duration_seconds/60)} min${traffic?` · SIMULATED TRAFFIC: ${traffic.level} · Delay ${Math.round(traffic.delay_seconds)} s · Adjusted ETA ${Math.ceil(traffic.adjusted_duration_seconds/60)} min`:''}${route.route_id===recommendedId?' · Recommended (lowest adjusted ETA)':''}`));const button=safe('button',reroute?'Accept New Route':'Use This Route','button subtle');button.onclick=()=>reroute?action(async()=>{await api('/api/routes/accept',{route_id:route.route_id});selected=route;routes=[route];FleetMap.showRoutes(routes,route.route_id);$(target).replaceChildren();toast('New route accepted. Resume when ready.');}):choose(route);row.append(button);if(!reroute){row.tabIndex=0;row.onclick=event=>{if(event.target!==button)choose(route);};row.onkeydown=e=>{if(e.key==='Enter')choose(route);};}$(target).append(row);});
  }
  function choose(route,fit=true){selected=route;FleetMap.showRoutes(routes,route.route_id,r=>choose(r),fit);renderOptions(routes,'route-options');buttons();}
  function coords(){const keys=['plan-start-lat','plan-start-lon','plan-dest-lat','plan-dest-lon'];if(keys.some(id=>!$(id).value.trim()))throw new Error('Select a start and destination first');return Object.fromEntries(['start_lat','start_lon','destination_lat','destination_lon'].map((name,i)=>[name,Number($(keys[i]).value)]));}
  function fill(route){const start=route.requested_start||route.start,end=route.requested_destination||route.destination;$('plan-start-lat').value=start.lat;$('plan-start-lon').value=start.lon;$('plan-dest-lat').value=end.lat;$('plan-dest-lon').value=end.lon;drawPoints();}
  function drawPoints(){const point=prefix=>{const a=$(prefix+'-lat').value,b=$(prefix+'-lon').value;return a!==''&&b!==''?{lat:Number(a),lon:Number(b)}:null;};FleetMap.plannerPoints(point('plan-start'),point('plan-dest'),setPoint);}
  const selectedNames={start:'',destination:''};
  function setPoint(name,lat,lon,label){selectedNames[name]=label||`${lat.toFixed(6)}, ${lon.toFixed(6)}`;const searchInput=document.getElementById('search-'+name);if(searchInput)searchInput.value=selectedNames[name];FleetMap.cancelSelection();const prefix=name==='start'?'plan-start':'plan-dest';$(prefix+'-lat').value=String(lat);$(prefix+'-lon').value=String(lon);invalidate();}
  function invalidate(){FleetMap.cancelSelection();planRevision++;selected=null;routes=[];renderOptions([],'route-options');FleetMap.showRoutes([],null);drawPoints();buttons();clearTimeout(planTimer);if(['plan-start-lat','plan-start-lon','plan-dest-lat','plan-dest-lon'].every(id=>$(id).value!==''))planTimer=setTimeout(requestRoutes,700);}
  for(const [button,name] of [['set-start','start'],['set-destination','destination']])$(button).onclick=()=>{toast('Click the map to select '+name);FleetMap.selectPoint((lat,lon)=>setPoint(name,lat,lon));};
  ['plan-start-lat','plan-start-lon','plan-dest-lat','plan-dest-lon'].forEach(id=>$(id).onchange=()=>{const name=id.startsWith('plan-start')?'start':'destination';selectedNames[name]='';const input=document.getElementById('search-'+name);if(input)input.value='';invalidate();});
  $('swap-points').onclick=()=>{[selectedNames.start,selectedNames.destination]=[selectedNames.destination,selectedNames.start];for(const name of ['start','destination']){const input=document.getElementById('search-'+name);if(input)input.value=selectedNames[name];}for(const suffix of ['lat','lon']){const a=$('plan-start-'+suffix),b=$('plan-dest-'+suffix);[a.value,b.value]=[b.value,a.value];}invalidate();};
  $('clear-plan').onclick=()=>{selectedNames.start='';selectedNames.destination='';for(const name of ['start','destination']){const input=document.getElementById('search-'+name);if(input)input.value='';}['plan-start-lat','plan-start-lon','plan-dest-lat','plan-dest-lon'].forEach(id=>$(id).value='');invalidate();};
  async function requestRoutes(){if(planning){planTimer=setTimeout(requestRoutes,500);return;}const revision=planRevision;planning=true;$('routing-message').textContent='Requesting road alternatives…';try{const result=await api('/api/routes',{...coords(),allow_fallback:$('allow-fallback').checked});if(revision!==planRevision)return;routes=result.routes;recommendedId=result.recommended_route_id;$('routing-message').textContent=result.message;choose(routes.find(r=>r.route_id===recommendedId)||routes[0]);}catch(error){if(revision===planRevision){$('routing-message').textContent=error.message;toast(error.message,true);}}finally{planning=false;}}
  $('calculate-routes').onclick=()=>{clearTimeout(planTimer);requestRoutes();};
  $('refresh-traffic').onclick=()=>action(async()=>{if(!routes.length)throw new Error('Plan routes first');const result=await api('/api/routes/traffic',{route_ids:routes.map(r=>r.route_id)});routes=result.routes;recommendedId=result.recommended_route_id;selected=routes.find(r=>r.route_id===selected?.route_id)||routes[0];renderOptions(routes,'route-options');});
  function useHome(name){if(home){setPoint(name,home.lat,home.lon,'Home');FleetMap.goTo(home);}}
  for(const id of ['home-shortcut','map-home-shortcut'])$(id).onclick=()=>{$('home-options').hidden=!$('home-options').hidden;$('home-shortcut').scrollIntoView({block:'center',behavior:'smooth'});};
  $('home-start').onclick=()=>useHome('start');$('home-destination').onclick=()=>useHome('destination');$('home-center').onclick=()=>home&&FleetMap.goTo(home);
  function searchPoint(name){const value=$('place-search').value.trim();if(value.toLowerCase()==='home')return useHome(name);const values=value.split(',').map(Number);if(values.length!==2||!values.every(Number.isFinite)||Math.abs(values[0])>90||Math.abs(values[1])>180)return toast('Choose Home or enter latitude, longitude',true);setPoint(name,...values);}
  $('search-start').onclick=()=>searchPoint('start');$('search-destination').onclick=()=>searchPoint('destination');
  const settings=()=>({speed_kmh:Number($('physical-speed').value),multiplier:Number($('time-multiplier').value)});
  $('simulation-start').onclick=()=>action(async()=>{await api('/api/simulation/start',{route_id:selected.route_id,...settings(),scenario:'normal',driver_id:window.FleetDrivers?.selected(),start_label:(selectedNames.start||'').slice(0,100)||undefined,destination_label:(selectedNames.destination||'').slice(0,100)||undefined,auto_reroute:$('auto-reroute').checked});toast('Simulation started');});
  for(const name of ['pause','resume','stop','reset'])$('simulation-'+name).onclick=()=>{if(name==='reset'&&!confirm('Reset simulation controls? Existing trip history is retained.'))return;action(async()=>{await api('/api/simulation/'+name,{});toast('Simulation '+name);});};
  $('apply-speed').onclick=()=>action(()=>api('/api/simulation/speed',settings(),'PATCH'));
  for(const speed of [20,30,40,50,60,80]){const button=safe('button',String(speed),'button subtle');button.onclick=()=>{$('physical-speed').value=speed;if(['RUNNING','PAUSED'].includes(state?.state))$('apply-speed').click();};$('speed-presets').append(button);}
  for(const [button,name] of [['trigger-deviation','deviation'],['trigger-recovery','recover'],['trigger-connectivity','connectivity']])$(button).onclick=()=>action(()=>api('/api/simulation/scenario',{action:name}));
  $('reroute-road').onclick=()=>action(async()=>{const result=await api('/api/routes/reroute',{});renderOptions(result.routes,'reroute-options',true);toast(result.message||'Route proposal ready; simulation paused');});
  $('input-mode').onchange=()=>action(()=>api('/api/mode',{mode:$('input-mode').value}));
  function buttons(){const live=['RUNNING','PAUSED'].includes(state?.state),hardware=$('input-mode').value==='HARDWARE';$('simulation-start').disabled=busy||live||!selected||hardware||!window.FleetDrivers?.ready();$('simulation-pause').disabled=busy||state?.state!=='RUNNING';$('simulation-resume').disabled=busy||state?.state!=='PAUSED';$('simulation-stop').disabled=busy||!live;$('apply-speed').disabled=busy||!live;$('simulation-controls').hidden=hardware;$('trip-controls').hidden=!hardware;$('demo-destination').hidden=true;$('demo-fence').hidden=true;for(const id of ['trigger-deviation','trigger-recovery','trigger-connectivity','reroute-road'])$(id).disabled=!live||busy;}
  async function showSummary(tripId){const data=await api('/api/trips/'+tripId);const t=data.trip;$('summary-content').textContent=`FM01 · ${t.status} · ${t.data_source||'Unknown source'}\n${t.destination_label}\nTravelled: ${km(t.distance_m)} km · Planned: ${km(t.route_total_m)} km\nLogical duration: ${Math.round(t.duration_seconds)} s\nAverage: ${t.average_speed_kmh.toFixed(1)} km/h · Maximum: ${t.maximum_speed_kmh.toFixed(1)} km/h\nGeofence events: ${t.geofence_event_count} · Deviations: ${t.deviation_count} · Reroutes: ${t.reroute_count}\n\n`+data.events.map(e=>`${e.kind}: ${e.message}`).join('\n');if(data.route)FleetMap.showRoutes([data.route],data.route.route_id);$('trip-summary').showModal();}
  async function refresh(){const data=await api('/api/dashboard');state=data.simulation;const trip=data.vehicle.trip||data.last_trip;$('simulation-state').textContent=`${state.state} · Physical ${state.speed_kmh} km/h · Clock ${state.multiplier}×`;$('review-progress').textContent=trip?trip.progress_percent.toFixed(1)+'%':'—';$('trip-progress').value=trip?.progress_percent||0;$('review-route-status').textContent=trip?.route_status||'UNPLANNED';$('review-route-status').className=trip?.route_status==='DEVIATED'?'route-warning':'';$('review-source').textContent=data.vehicle.location?.source||'Waiting for telemetry';$('unread-count').textContent=data.unread_count;
    if(!selected&&data.route&&['RUNNING','PAUSED'].includes(state.state)){routes=[data.route];selected=data.route;selectedNames.start=data.vehicle.trip?.start_label||'';selectedNames.destination=data.vehicle.trip?.destination_label||'';for(const name of ['start','destination']){const input=document.getElementById('search-'+name);if(input)input.value=selectedNames[name];}activateRoute(selected,data.vehicle.trip,data.initial_route?.requested_start);}
    if(selected&&data.route&&data.vehicle.trip&&selected.route_id!==data.route.route_id){activateRoute(data.route,data.vehicle.trip,data.initial_route?.requested_start);}
    $('review-events').replaceChildren(...data.events.map(e=>{const row=safe('div',e.title+' · '+e.message,'review-event');row.append(safe('small',new Date(e.timestamp).toLocaleString()));return row;}));
    $('notification-items').replaceChildren(...data.notifications.map(n=>{const row=safe('div',`${n.type} · ${n.title}: ${n.message}`,'notification-item'+(n.is_read?'':' unread'));const button=safe('button',n.is_read?'Read':'Mark read','button subtle');button.disabled=n.is_read;button.onclick=()=>action(()=>api(`/api/notifications/${n.notification_id}/read`,{},'PATCH'));row.append(button);return row;}));
    $('review-history').replaceChildren(...data.trips.map(t=>{const button=safe('button',`Trip #${t.trip_id} · ${t.status} · ${km(t.distance_m)} km · ${Math.round(t.duration_seconds)} s · ${t.average_speed_kmh.toFixed(1)} km/h`,'button subtle');button.onclick=()=>action(()=>showSummary(t.trip_id));return button;}));
    document.dispatchEvent(new CustomEvent('fleet:update',{detail:data}));
    const fresh=data.notifications.filter(n=>n.notification_id>lastNotification);if(initialized)fresh.reverse().forEach(n=>{sound(n.kind);toast(n.title,n.type==='CRITICAL');if(['ROUTE_DEVIATION','REROUTE_ACCEPTED','REROUTE_FAILED','DESTINATION_CHANGED'].includes(n.kind)){ alertQueue.push(n);showNextAlert();}});lastNotification=Math.max(lastNotification,...data.notifications.map(n=>n.notification_id),0);
    if(initialized&&data.last_trip?.status==='ARRIVED'&&data.last_trip.trip_id>lastSummary){lastSummary=data.last_trip.trip_id;toast('Destination reached. Your complete trip is saved in Trip History.');}if(!initialized)lastSummary=data.last_trip?.trip_id||0;initialized=true;buttons();
  }
  function activateRoute(route,trip,originalStart){
    routes=[route];selected=route;selectedNames.destination=trip.destination_label;
    selectedNames.start=trip.start_label||selectedNames.start;
    const origin=originalStart||{lat:Number($('plan-start-lat').value)||trip.start_lat,lon:Number($('plan-start-lon').value)||trip.start_lon};
    $('plan-start-lat').value=origin.lat;$('plan-start-lon').value=origin.lon;
    const end=route.requested_destination||route.destination;
    $('plan-dest-lat').value=end.lat;$('plan-dest-lon').value=end.lon;
    for(const name of ['start','destination']){const input=document.getElementById('search-'+name);if(input)input.value=selectedNames[name];}
    drawPoints();choose(route,false);
  }
  document.addEventListener('fleet:driver-selection',buttons);
  window.FleetPlanner={setPoint,activateRoute};
  (async()=>{try{const config=await api('/api/config');$('input-mode').value=config.mode;home=config.saved_places.find(place=>place.id==='home');FleetMap.savedPlaces(config.saved_places);}catch(error){toast(error.message,true);}async function poll(){try{await refresh();}catch(error){$('simulation-state').textContent='Backend unavailable · '+error.message;}setTimeout(poll,1200);}poll();})();
})();
