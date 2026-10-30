# FleetMitra final review and demo guide

**Latest workflow:** [PROJECT_DEMO_GUIDE.md](../PROJECT_DEMO_GUIDE.md) includes driver registration/assignment, mandatory dashboard driver selection, changing destination during an active/paused trip, immutable driver/destination history and current **200-test** verification. Install updated requirements before starting. The map/provider explanations below remain applicable; the earlier 161-test count describes the previous upgrade.

## Start the project

In Windows PowerShell:

```powershell
Set-Location 'D:\College Projects\CBP IOT\Fleet Mitra'
.\venv\Scripts\python.exe app.py
```

Open [FleetMitra](http://127.0.0.1:5000). No activation or Node build is required. For a fresh environment only, run `python -m venv venv`, then `.\venv\Scripts\python.exe -m pip install -r requirements.txt` first. Stop the server with Ctrl+C. Keep `instance/fleet_mitra.sqlite3`; it contains permanent records.

To reopen the isolated review database demonstrated during QA:

```powershell
Set-Location 'D:\College Projects\CBP IOT\Fleet Mitra'
$env:FLEET_DATABASE='instance/final-review-qa.sqlite3'
$env:FLEET_PORT='5003'
.\venv\Scripts\python.exe app.py
```

Open [review instance](http://127.0.0.1:5003) and [saved trips](http://127.0.0.1:5003/history). Environment variables apply in that PowerShell session; use a new session for normal defaults. Do not run two servers against the same database or combine the CLI sender with a dashboard simulation.

## Suggested college demonstration

1. Open the dashboard in SIMULATION MODE. The sidebar contains navigation; the adjacent planner collapses to enlarge the map. Analytics, exact coordinates and review tools are disclosures.
2. Click **🏠 Home → Set Home as Start**. Verify **17.415666, 78.573060**. Alternatively search for an origin or use **Set Starting Point** and click an unoccupied map location.
3. Search **Uppal Hyderabad**, then choose a suggestion with the mouse or ↑ / ↓ / Enter. Alternatively use **Set Destination** on the map. Endpoints remain freely selectable and draggable.
4. Wait for road alternatives or click **Find routes**. Compare distance, base ETA and SIMULATED TRAFFIC. Home → Uppal returned two genuine OSRM alternatives during QA; availability varies. Click **Use This Route**.
5. Set speed **40 km/h**, acceleration **4×**, then **Start Trip**. This creates one persistent record. Acceleration changes the simulation clock, not physical speed.
6. Collapse the planner. The active road line is blue with a darker border; travelled geometry becomes grey. **Follow vehicle** zooms to 17 and follows the rotating arrow. Pan or zoom to suspend follow; enable it again to resume. **Fit Entire Route** shows the full selected route.
7. Optionally select **Navigation Map** on localhost. **🏠 Home → Go to Home** moves only the camera and retains the selected route.
8. Expand **Advanced & review tools** and click **Test Route Deviation** early while running. Sustained off-route telemetry produces the warning. If a suitable real alternative is unavailable, the event explicitly identifies a synthetic test offset. Automatic rerouting validates and activates a replacement road route before reporting success. Failure pauses safely for retry.
9. Pause/resume or refresh to reconnect to the same active trip. Let the vehicle arrive for COMPLETED / ARRIVED, or Stop for STOPPED. Reset retains history.
10. Open **Trip History**, filter/search and select the record. Inspect original/replacement/actual route layers, timestamps, statistics and events. Export CSV or JSON.
11. Stop Flask and restart using the same database. Reload history: records remain. An unfinished simulation is paused after restart and requires Resume.

For geofence review, use the expandable geofence controls to create a zone intersecting the chosen road route. Enter/exit events use the shared monitoring pipeline. Hardware mode and original `simulator\gps_simulator.py` remain available; no physical ESP32 testing was performed.

## Permanent history and database design

History reuses `trips`, `locations` and `trip_events`. Additive nullable columns retain creation/start labels, original route ID/distance/ETA/traffic, initial speed/acceleration and end reason. New `trip_route_versions` rows have version ID, trip/route foreign keys, timestamp, reason and immutable route JSON. Indexes support trip/date and archived-route queries. No table rebuild, reset or deletion is needed.

A successful start transaction creates the trip and original-route snapshot. Accepted reroutes archive full geometry in the same transaction as activation. Pause/resume, deviations, failed/accepted reroutes, geofence transitions, arrival and stop events update that same trip. Existing unique active-trip/session indexes prevent repeated Start from duplicating records. Reset and subsequent trips retain prior records.

The original SQLite status CHECK and old stop API compatibility are preserved. The new history lifecycle/end reason distinguishes STOPPED from successful completion. Missing pre-upgrade route metadata is displayed as unavailable, never invented.

GPS samples are saved through the existing shared ingestion pipeline, independently of animation frames. Simulator substeps cover at most 10 m, preserving road bends and monitoring events. SQLite stores accepted meaningful samples rather than browser redraws. This is a single-vehicle prototype, without high-volume fleet downsampling.

History reads all saved positions and immutable snapshots; it never regenerates an old path with a current routing API. Original plans are purple, accepted replacement routes amber, actual recorded paths blue. Both requested endpoints and road-snapped endpoints appear when available.

CSV has typed `trip`, `location`, `event` and `route_version` rows, with nested fields preserved in `details_json`. JSON exports the same full persisted record. Simulation duration/average speed use logical time; UTC start/end timestamps remain wall time. Back up the SQLite database for protection against disk loss.

## Search and map providers

Photon is used through a Flask proxy. No Google key or public Nominatim autocomplete is used. Configuration:

```powershell
$env:FLEET_GEOCODING_ENABLED='true'
$env:FLEET_GEOCODING_URL='https://photon.komoot.io/api/'
```

The URL can point to a compatible self-hosted Photon instance. Search requires 3–120 characters, debounces 650 ms, limits outbound calls to one per 750 ms per process, serializes requests, caches up to 128 queries for ten minutes, and bounds result count/size/timeout. Coordinates are validated. Loading, empty, rate-limit and provider errors are displayed. Home resolves locally even with online search disabled. Map selection remains independent.

Photon's public demo offers fair-use availability without guarantees; use a configured/self-hosted service for sustained deployment. Place queries go to the configured Photon service; route endpoints go to OSRM; tiles go to the selected provider.

**Standard Map:** OpenStreetMap raster tiles, native max zoom 19, required attribution, normal browser cache, no bulk prefetch. This remains the reliable default.

**Navigation Map:** Stadia Alidade Smooth, available only on localhost/127.0.0.1, native max zoom 20, supported `{r}` high-DPI tiles and Stadia/OpenMapTiles/OSM attribution. Development access is strictly rate limited; it is not unrestricted free hosting. Errors switch back to Standard Map. Remote deployment needs a separately licensed/configured integration. Satellite imagery is not offered. No CSS blur/filter or artificial tile upscaling is applied.

Provider references: [Photon](https://photon.komoot.io/), [OSM tile policy](https://operations.osmfoundation.org/policies/tiles/), [Stadia development authentication](https://docs.stadiamaps.com/authentication/), [Alidade Smooth](https://docs.stadiamaps.com/map-styles/alidade-smooth/), [Stadia attribution](https://docs.stadiamaps.com/attribution/).

## Explain the implementation in your viva

- **Why keep Leaflet and Flask?** The working architecture already handles GPS, SQLite and simulation. We reorganized controls and added focused modules.
- **How does blue become grey?** Measured route progress splits the provider's actual road geometry. Existing line layers update in place.
- **Follow versus Fit?** Follow uses a street-level camera around fresh readings. Fit shows all route geometry. User map gestures suspend Follow.
- **Is traffic live?** No. It is a labelled, persisted comparison model. Physical speed drives simulation and movement ETA.
- **Why does history survive restart?** SQLite stores trips, samples, events and original/replacement route snapshots. The browser displays these committed records.
- **What prevents duplicates?** Transactions and unique indexes allow one active trip/session per vehicle. Refresh reads state; it does not start another trip.
- **What happens after a power interruption?** Committed data remains; a running simulation pauses on restart without inventing downtime movement.
- **Why are requested and recorded endpoints different?** Home stays exact. A road provider may snap driving geometry onto a nearby road; both coordinates are retained.

## Verification

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Final result: **161 passed, 0 failed**; the verified baseline was **144**. Two pytest cases run eight optional Node geometry/camera/module checks when Node is installed; Node is not needed to run FleetMitra.

Real-browser QA completed two trips including actual automatic road rerouting, saved a third as STOPPED, verified refresh and server-restart persistence, downloaded CSV, inspected desktop/mobile layouts and map zooms 12/14/16/17/18. High-DPI tile support is configured; physical Retina/high-DPI displays, browser zoom settings, actual ESP32 hardware and speaker audibility were not independently verified. Search/routing/tiles remain network- and provider-dependent.

See the [progress report](../FLEETMITRA_PROGRESS_REPORT.md) and [navigation calculations](NAVIGATION_GUIDE.md).




