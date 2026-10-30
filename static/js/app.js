/* All values on the dashboard come from the Flask API. No simulated UI state. */
(() => {
  const $ = id => document.getElementById(id);
  let refreshInFlight = null, currentSnapshot = null, busy = false, demo;
  let noticeTimer;
  const formatTime = value => value ? new Date(value).toLocaleString(undefined, {month:"short", day:"numeric", hour:"2-digit", minute:"2-digit", second:"2-digit"}) : "—";
  const fixed = (value, decimals = 2) => Number.isFinite(value) ? value.toFixed(decimals) : "—";
  const set = (id, value) => { $(id).textContent = value; };

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(path, {...options, signal: controller.signal,
        headers: {"Content-Type": "application/json", ...options.headers}});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
      return data;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("Backend request timed out");
      throw error;
    } finally { clearTimeout(timeout); }
  }
  function notify(message, error = false) {
    clearTimeout(noticeTimer);
    set("notice", message);
    $("notice").className = `notice${error ? " error" : ""}`;
    $("notice").hidden = false;
    noticeTimer = setTimeout(() => { $("notice").hidden = true; }, error ? 14000 : 7000);
  }
  function badge(text, className) {
    const span = document.createElement("span"); span.className = className; span.textContent = text; return span;
  }
  function emptyRow(body, columns, text) {
    body.replaceChildren();
    const row = body.insertRow(), cell = row.insertCell(); cell.colSpan = columns; cell.className = "empty"; cell.textContent = text;
  }
  function renderLocations(locations) {
    const body = $("locations-body");
    if (!locations.length) return emptyRow(body, 6, "Waiting for GPS data… Start the simulator to see your vehicle.");
    body.replaceChildren();
    locations.forEach(location => {
      const row = body.insertRow();
      [formatTime(location.timestamp), fixed(location.lat, 6), fixed(location.lon, 6), `${fixed(location.speed_kmh, 1)} km/h`].forEach(value => { row.insertCell().textContent = value; });
      row.insertCell().append(badge(location.source, `table-source${location.source === "HARDWARE" ? " hardware" : ""}`));
      row.insertCell().textContent = location.trip_id ? `#${location.trip_id}` : "—";
    });
  }
  function renderTrips(trips) {
    const body = $("trips-body");
    if (!trips.length) return emptyRow(body, 6, "No completed trips yet. Start and stop a trip to see it here.");
    body.replaceChildren();
    trips.forEach(trip => {
      const row = body.insertRow();
      [`#${trip.trip_id}`, trip.destination_label, formatTime(trip.start_time), formatTime(trip.end_time), `${fixed(trip.distance_km)} km`].forEach(value => { row.insertCell().textContent = value; });
      row.insertCell().append(badge("COMPLETED", "badge inside"));
    });
  }
  function renderEvents(events) {
    set("event-count", events.length);
    const list = $("events"); list.replaceChildren();
    if (!events.length) { list.append(badge("No ENTER or EXIT events yet. Transitions will appear here.", "empty")); return; }
    events.forEach(event => {
      const row = document.createElement("div"); row.className = `event ${event.event_type.toLowerCase()}`;
      row.append(badge(event.event_type === "ENTER" ? "↳" : "↗", "event-icon"));
      const content = document.createElement("div"), title = document.createElement("p"), time = document.createElement("time");
      time.dateTime = event.timestamp; time.textContent = new Date(event.timestamp).toLocaleTimeString();
      title.textContent = event.event_type; title.append(time);
      const name = document.createElement("small"); name.textContent = event.name;
      content.append(title, name); row.append(content); list.append(row);
    });
  }
  function renderFences(fences) {
    const container = $("fences"); container.replaceChildren();
    if (!fences.length) { container.append(badge("No geofence configured", "empty")); return; }
    fences.forEach(fence => {
      const row = document.createElement("div"); row.className = "fence-row";
      const title = badge(fence.name, "fence-name"), radius = document.createElement("small");
      radius.textContent = `${fixed(fence.radius_m, 0)} m radius`; title.append(radius);
      const remove = document.createElement("button"); remove.type = "button"; remove.className = "delete-fence";
      remove.textContent = "×"; remove.setAttribute("aria-label", `Delete geofence ${fence.name}`); remove.disabled = busy;
      remove.addEventListener("click", () => { if (confirm(`Delete ${fence.name} and its boundary event history?`)) mutate(`/api/geofences/${fence.geofence_id}`, "DELETE", undefined, `Deleted ${fence.name}.`); });
      row.append(title, badge(fence.status.replaceAll("_", " "), `badge ${fence.status === "INSIDE" ? "inside" : "outside"}`), remove);
      container.append(row);
    });
  }
  function setControls() {
    const active = Boolean(currentSnapshot?.trip);
    $("start-trip").disabled = busy || active || !currentSnapshot?.location || !window.FleetDrivers?.ready();
    $("stop-trip").disabled = busy || !active;
    $("geofence-form").querySelector('[type="submit"]').disabled = busy;
    document.querySelectorAll(".delete-fence").forEach(button => { button.disabled = busy; });
  }
  function renderSnapshot(snapshot, locations) {
    currentSnapshot = snapshot;
    const location = snapshot.location, trip = snapshot.trip, eta = snapshot.eta;
    set("source", location?.source || "NO DATA");
    $("source").className = `badge source-badge${location?.source === "HARDWARE" ? " hardware" : ""}`;
    set("speed", location ? fixed(location.speed_kmh, 1) : "—");
    set("motion", !location ? "Waiting for GPS data" : snapshot.stale ? "GPS data stale · awaiting a new fix" : location.speed_kmh < 3 ? "Vehicle stationary" : "Vehicle moving");
    set("distance", trip ? fixed(trip.distance_km) : "—");
    set("trip-status", trip ? `ACTIVE · Trip #${trip.trip_id}` : "No active trip");
    set("remaining", eta ? fixed(eta.remaining_distance_m / 1000) : "—");
    set("distance-method", !eta ? "Choose a destination to begin" : eta.method === "ROAD_ROUTE" ? "Road route · OSRM" : "Straight-line estimate · FALLBACK");
    set("eta", eta?.status === "ARRIVED" ? "Arrived" : eta?.duration_seconds != null ? String(Math.max(1, Math.ceil(eta.duration_seconds / 60))) : "—");
    set("eta-unit", eta?.status === "ARRIVED" ? "" : "min");
    set("arrival", !eta ? "ETA unavailable" : eta.status === "WAITING_FOR_MOVEMENT" ? "WAITING FOR MOVEMENT" : eta.status === "WAITING_FOR_GPS" ? "WAITING FOR GPS" : eta.status === "ARRIVED" ? "Within destination arrival radius" : `At ${new Date(eta.arrival_time).toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"})} · ${eta.method === "ROAD_ROUTE" ? "ROAD ROUTE" : "FALLBACK"}`);
    set("latitude", location ? fixed(location.lat, 6) : "—");
    set("longitude", location ? fixed(location.lon, 6) : "—");
    set("last-update", location ? formatTime(location.timestamp) : "Waiting for GPS data…");
    set("gps-state", !location ? "WAITING" : snapshot.stale ? "STALE GPS" : "GPS VALID");
    set("map-caption", location ? `FM01 · ${location.source}${snapshot.stale ? " · GPS data stale" : " · Live GPS updates"}` : "FM01 · Waiting for GPS data…");
    const enabledFences = snapshot.geofences.filter(fence => fence.enabled);
    const fenceSummary = enabledFences.length === 1 ? enabledFences[0].status : enabledFences.length ? `${enabledFences.filter(fence => fence.status === "INSIDE").length} / ${enabledFences.length} INSIDE` : "No geofence configured";
    set("geofence-summary", fenceSummary.replaceAll("_", " "));
    set("destination-summary", trip ? `${trip.destination_label} · ${fixed(trip.destination_lat, 5)}, ${fixed(trip.destination_lon, 5)}` : "No active trip");
    renderFences(snapshot.geofences); setControls();
    FleetMap.update(snapshot, locations);
  }
  async function refresh() {
    if (refreshInFlight) return refreshInFlight;
    refreshInFlight = (async () => {
      const paths = ["/api/health", "/api/vehicles/FM01/location", "/api/vehicles/FM01/history?limit=12", "/api/geofences/events?limit=8", "/api/trips/history?limit=12"];
      // Settle every request before scheduling the next poll, including on failure.
      const results = await Promise.allSettled(paths.map(path => api(path)));
      const failed = results.find(result => result.status === "rejected");
      if (failed) throw failed.reason;
      const [health, snapshot, history, events, trips] = results.map(result => result.value);
      if (health.database !== "connected") throw new Error("Database unavailable");
      $("connection").className = "connection connected";
      $("connection").replaceChildren(badge("", "status-dot"), document.createTextNode("Backend connected · 3s refresh"));
      renderSnapshot(snapshot, history.locations); renderLocations(history.locations); renderEvents(events.events); renderTrips(trips.trips);
    })().catch(error => {
      $("connection").className = "connection disconnected";
      $("connection").replaceChildren(badge("", "status-dot"), document.createTextNode("Backend disconnected"));
      $("connection").title = error.message;
    }).finally(() => { refreshInFlight = null; });
    return refreshInFlight;
  }
  async function mutate(path, method, data, success) {
    if (busy) return;
    busy = true; setControls();
    try {
      const result = await api(path, {method, body: data ? JSON.stringify(data) : undefined});
      await refreshInFlight; await refresh();
      notify(success); return result;
    } catch (error) { notify(error.message, true); }
    finally { busy = false; setControls(); }
  }
  FleetMap.init((mode, lat, lon) => {
    const prefix = mode === "destination" ? "destination" : "fence";
    $(`${prefix}-lat`).value = lat.toFixed(6); $(`${prefix}-lon`).value = lon.toFixed(6);
    notify(mode === "destination" ? "Destination selected. Add a label and start your trip." : "Center selected. Name your zone and create the geofence.");
  });
  $("pick-destination").addEventListener("click", () => FleetMap.pick("destination"));
  $("pick-fence").addEventListener("click", () => FleetMap.pick("fence"));
  $("trip-form").addEventListener("submit", event => {
    event.preventDefault();
    mutate("/api/trips/start", "POST", {vehicle_id:"FM01", driver_id:window.FleetDrivers?.selected(), destination_lat:Number($("destination-lat").value), destination_lon:Number($("destination-lon").value), destination_label:$("destination-label").value}, "Trip started. Distance and ETA will update as FM01 moves.");
  });
  $("stop-trip").addEventListener("click", () => mutate("/api/trips/stop", "POST", {vehicle_id:"FM01"}, "Trip completed and saved to trip history."));
  $("geofence-form").addEventListener("submit", event => {
    event.preventDefault();
    mutate("/api/geofences", "POST", {vehicle_id:"FM01", name:$("fence-name").value, center_lat:Number($("fence-lat").value), center_lon:Number($("fence-lon").value), radius_m:Number($("fence-radius").value)}, "Geofence created. ENTER and EXIT events appear when FM01 crosses the boundary.");
  });
  async function preset(type) {
    try {
      demo = demo || await api("/api/demo-config");
      if (type === "destination") {
        $("destination-label").value = demo.destination.label;
        $("destination-lat").value = demo.destination.lat;
        $("destination-lon").value = demo.destination.lon;
        FleetMap.previewDestination(demo.destination.lat, demo.destination.lon);
      } else {
        $("fence-name").value = demo.geofence.name;
        $("fence-lat").value = demo.geofence.center_lat;
        $("fence-lon").value = demo.geofence.center_lon;
        $("fence-radius").value = demo.geofence.radius_m;
      }
    } catch (error) { notify(error.message, true); }
  }
  $("demo-destination").addEventListener("click", () => preset("destination"));
  $("demo-fence").addEventListener("click", () => preset("geofence"));
  for (const type of ["locations", "trips"]) $(type + "-tab").addEventListener("click", () => {
    for (const panel of ["locations", "trips"]) {
      $(panel + "-tab").setAttribute("aria-selected", String(type === panel));
      $(panel + "-panel").hidden = type !== panel;
    }
  });
  set("today", new Date().toLocaleDateString(undefined, {weekday:"short", day:"numeric", month:"short", year:"numeric"}));
  setControls();
  (async function poll() { await refresh(); setTimeout(poll, 3000); })();
})();
