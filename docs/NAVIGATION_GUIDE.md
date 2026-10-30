# User-controlled navigation and saved Home

**Latest additions:** [Final demo guide](../PROJECT_DEMO_GUIDE.md) covers Drivers, driver selection, Change Destination, safe concurrent proposal activation, encryption/key backups and **200 passing tests**. The verified final feature instance uses `instance/final-features-qa.sqlite3`, port **5004**. Earlier 5003/161-test references below describe the previous navigation upgrade.

Final dashboard, search, history, provider configuration and viva explanations: [current review guide](REVIEW_GUIDE.md). This document retains the navigation calculations and APIs.

## Run

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5000. Final browser QA uses a separate database at `instance/final-review-qa.sqlite3`, port 5003. Existing databases and ESP32 firmware are preserved.

## Plan your journey

1. Use **Set Starting Point**, then click an unoccupied map point. Use **Set Destination** and click another point. Green S and red D markers show the exact chosen coordinates. Drag either marker to adjust it. Pan/zoom normally; selection mode ignores marker, route and map-control clicks. Escape cancels selection.
2. Alternatively open **🏠 Home** and choose **Set Home as Start** or **Set Home as Destination**. Home is stored in `config.py`: latitude **17.415666**, longitude **78.573060**. These coordinates are never rounded or approximated in application configuration or the selected-point markers. It is not an automatic origin.
3. **Go to Home** centers/zooms the map without changing route selection. It disables vehicle-follow so the next poll cannot immediately pull the view away. Toggle Follow vehicle to resume following.
4. Search starting location or destination with Photon place suggestions (minimum three characters); select by mouse or ↑ / ↓ / Enter. Escape dismisses suggestions. Home resolves locally. Numeric input remains in the **Exact coordinates** disclosure. Map selection works independently of search.
5. Routes are requested automatically after both points are present. Swap Start & Destination reverses points and labels; Clear planner removes selections. **Find routes** retries the provider. Existing active trip/session state remains stored separately from the planner.

## Genuine alternatives and simulated traffic

OSRM is requested with `alternatives=3`, full GeoJSON and a bounded timeout. Up to four provider-returned routes are validated. Near-identical routes are removed when lengths differ by no more than 8% and the bidirectional mean distance of 21 sampled points per geometry is at most 25 m. No invented alternatives are added. Three different routes cannot be guaranteed; the UI reports the actual distinct count.

Selected routes are bright blue with a darker outline, rounded joins and zoom-dependent width; alternatives are thinner muted grey. Click an alternative line or **Use This Route**. Travelled geometry becomes grey while the remaining geometry stays blue. SVG markers stay sharp and the vehicle arrow rotates with movement. Start/destination markers stay at the requested coordinates, including Home. OSRM may snap its driving geometry to a nearby road; exact requested coordinates remain stored separately and are shown in history.

**Follow vehicle** smoothly zooms to 17 and pans with fresh GPS readings, keeping the vehicle below center. Disable it to preserve zoom and explore freely. Dragging, wheel/double-click zoom, pinch, keyboard navigation and zoom buttons suspend following. **Fit Entire Route** shows all selected geometry. **Go to Home** changes only the camera. Polylines update without recreating the map.

Each new planning request receives a random seed. SHA-256 of seed + geometry selects Low/Moderate/Heavy **SIMULATED TRAFFIC**. Delay = base provider duration × 5%/25%/60%; adjusted ETA = base duration + delay. These values are persisted with the route so comparison remains stable across polling and restart. **Refresh simulated traffic** explicitly generates a new seed without requesting or changing geometry. The lowest adjusted ETA is recommended; any route can be selected.

Traffic is an illustrative comparison model, not measured traffic. It does not multiply physical GPS speed or silently slow the simulator. While travelling, the main tracking ETA uses remaining selected-route distance and the current physical vehicle speed. Comparison ETA and tracking ETA therefore answer different questions and are labelled separately.

## Simulation and deviation

Choose physical speed and 1/2/4/8/16× acceleration, then **Start Trip**. At 40 km/h and 8× the dashboard reports 40 km/h. Pause freezes position/logical time; Resume continues. Stop or Reset ends an active trip as STOPPED in the new history view; arrival ends it as COMPLETED / ARRIVED. Preset scenarios are removed from the main interface; backend fixtures remain for legacy tests and API compatibility. Advanced controls are collapsed by default.

**Test Route Deviation** looks for a provider-returned alternative whose first 800 m contains a point at least corridor + 30 m from the planned route. If available, it follows that real geometry. Otherwise the timeline explicitly states that a synthetic lateral offset is being used. It always sends accepted simulated telemetry through the normal ingestion pipeline. It does not directly create a deviation alert.

Three consecutive points beyond the configured corridor (75 m default) confirm deviation. A persistent event, notification, audible warning when enabled, and acknowledgement popup follow. With automatic rerouting enabled, the current location and original destination request a replacement road route. A valid accepted replacement updates remaining distance and resumes. Failure retains the original route and pauses; retry with Recalculate Road Route, accept the proposal, then Resume. Each episode attempts automatic rerouting once; a successful replacement preserves automatic mode for later episodes. No success is reported when the provider fails.

Arrival remains radius-based with the route-end guard. It stores ARRIVED, stops motion and shows a small notification; full details are in Trip History. Deviation/replacement acknowledgement alerts are nonblocking and queued. No hardware testing is claimed. Sounds require user interaction and working device audio.

## Provider outage

Road-route failure is displayed. Retry or explicitly check **Allow labelled straight-line fallback**. FALLBACK is never presented as road routing. The dashboard contains no predefined demo-scenario selector. Original CLI simulator, fixtures and older API contracts remain available for compatibility.

## Tests

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Final result: **161 passed, 0 failed**, including all previous 144 cases. New tests cover geocoding coordinates/cache/failures, immutable trip/route/event history, exports, filters, pagination and restart recovery. Two pytest cases run eight optional Node geometry/camera/module checks. Browser QA exercised real search, Home markers, blue/grey progress, zoom-17 follow, manual pan suspension, automatic road rerouting, completion/stop, history, application restart and CSV download. Two live routes were available for Home → Uppal. Mocked alternatives prove handling, not live availability of three routes.



