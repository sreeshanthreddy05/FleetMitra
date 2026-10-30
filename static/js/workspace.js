/* Reorganize existing controls; their event handlers and API behavior stay attached. */
(() => {
  const $=id=>document.getElementById(id);
  const details=(title,nodes)=>{const section=document.createElement('details');section.className='disclosure';const summary=document.createElement('summary');summary.textContent=title;section.append(summary,...nodes.filter(Boolean));return section;};
  document.body.classList.add('navigation-shell');
  $('search-start').id='coordinate-use-start';$('search-destination').id='coordinate-use-destination';
  const top=document.querySelector('.topbar');
  const title=document.createElement('strong');title.textContent='FleetMitra';top.prepend(title);
  const historyLink=document.createElement('a');historyLink.href='/history';historyLink.textContent='Trip History';historyLink.className='button subtle';top.append(historyLink,$('input-mode'),$('sound-toggle'),$('notification-toggle'));
  const nav=document.querySelector('.sidebar nav');nav.replaceChildren();
  for(const [text,href] of [['Dashboard','/'],['Live Tracking','#map'],['Trip History','/history'],['Drivers','/drivers'],['Notifications','#notification-center'],['Settings','#planner-settings']]){const a=document.createElement('a');a.textContent=text;a.href=href;a.className='nav-link';if(text==='Notifications')a.onclick=()=>{$('notification-center').hidden=false;};nav.append(a);}
  const workspace=document.querySelector('.navigation-workspace'),panel=$('review-controls');
  const heading=panel.querySelector('.panel-heading');heading.replaceChildren();const h=document.createElement('h2');h.textContent='Plan your journey';const collapse=document.createElement('button');collapse.className='button subtle';collapse.id='collapse-planner';collapse.textContent='Collapse';collapse.setAttribute('aria-expanded','true');collapse.onclick=()=>{const closed=workspace.classList.toggle('planner-collapsed');collapse.textContent=closed?'Plan trip':'Collapse';collapse.setAttribute('aria-expanded',String(!closed));};heading.append(h,collapse);
  const planner=panel.querySelector('.review-layout > div:first-child');
  const search=document.createElement('div');search.className='location-searches';
  for(const [id,label] of [['start','Search starting location'],['destination','Search destination']]){const row=document.createElement('div');row.className='search-box';const field=document.createElement('label');field.textContent=label;const input=document.createElement('input');input.id='search-'+id;input.type='search';input.autocomplete='off';input.placeholder=id==='start'?'Where are you starting?':'Where are you going?';input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-expanded','false');input.setAttribute('aria-controls','results-'+id);field.append(input);const results=document.createElement('div');results.id='results-'+id;results.setAttribute('role','listbox');const status=document.createElement('small');status.id='search-status-'+id;status.setAttribute('role','status');row.append(field,results,status);search.append(row);}
  const attr=document.createElement('small');attr.className='search-attribution';attr.textContent='Search: Photon · © OpenStreetMap contributors';search.append(attr);
  planner.prepend(search);planner.querySelector('h3').hidden=true;
  const coordinateFields=planner.querySelector('.review-fields');
  const manualButtons=document.createElement('div');manualButtons.className='review-actions';manualButtons.append($('set-start'),$('set-destination'));search.after(manualButtons);
  const coords=details('Exact coordinates',[coordinateFields]);planner.append(coords);
  const actions=planner.querySelector('.review-actions');
  const primary=document.createElement('div');primary.className='planner-quick';primary.append($('home-shortcut'),$('swap-points'),$('clear-plan'));search.after(primary,$('home-options'));
  const hiddenHome=panel.querySelector('.home-controls');hiddenHome.hidden=true;
  const settings=details('Routing preferences',[$('refresh-traffic'),$('allow-fallback').parentElement]);settings.id='planner-settings';planner.append(settings);
  $('calculate-routes').textContent='Find routes';
  const sim=$('simulation-controls');sim.querySelector('h3').textContent='Journey controls';
  const advanced=details('Advanced & review tools',[$('speed-presets'),$('auto-reroute').parentElement,$('trigger-deviation').parentElement,$('reroute-road').parentElement,sim.querySelector('p.review-help'),$('reroute-options'),$('simulation-reset')]);sim.append(advanced);$('simulation-start').textContent='Start Trip';
  sim.querySelectorAll(':scope > p.review-help').forEach(p=>advanced.append(p));
  const info=$('review-progress').closest('.review-status');document.querySelector('.metrics').append(info);info.classList.add('compact-progress');
  const side=document.querySelector('.tracking-side');const secondary=details('Vehicle details & geofence events',[side]);workspace.after(secondary);
  const geo=document.querySelector('.controls-grid');secondary.after(details('Geofence setup & hardware trip controls',[geo]));
  const metric=document.querySelector('.metrics');workspace.before(metric);
  const mapHeading=document.querySelector('.map-panel .panel-heading');const fit=document.createElement('button');fit.id='fit-route';fit.textContent='Fit Entire Route';fit.disabled=true;fit.className='button subtle';fit.onclick=()=>FleetMap.fitRoute();mapHeading.append(fit);
  const layers=document.createElement('select');layers.id='map-layer';layers.setAttribute('aria-label','Map Layers');layers.innerHTML='<option value="standard">Standard Map</option>';if(['localhost','127.0.0.1'].includes(location.hostname))layers.add(new Option('Navigation Map','navigation'));layers.onchange=()=>FleetMap.setLayer(layers.value);mapHeading.append(layers);
  const notification=$('notification-center');top.after(notification);notification.classList.add('notification-drawer');
  $('navigation-alert').classList.add('nonblocking-alert');
  document.querySelector('.map-legend').innerHTML='<span>● Vehicle</span><span style="color:#2580ff">━ Remaining route</span><span style="color:#8a96a5">━ Travelled</span>';
})();
