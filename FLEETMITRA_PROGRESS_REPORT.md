# FleetMitra progress report — 30 October 2026

## Port 5000 dashboard mismatch — actual application fix

The earlier audit checked port 5004 and did not identify the stale server on port 5000. The database distinction was real but did **not** explain the outdated interface. This investigation reproduced the user's exact screen at port 5000 before making changes.

**Confirmed cause:** Windows had two LISTENING sockets at 127.0.0.1:5000, owned by Python PIDs 28500 and 9532. PID 28500 started at 19:19, before the final feature changes. A fresh uncached HTTP request returned the old cached HTML with Demo Scenarios and without navigation_geometry.js, workspace.js, search.js or journey_extensions.js. The same server served the current map.js from disk. `/drivers` returned 404. Browser errors were `NavigationGeometry is not defined` and a null `addEventListener` in review.js. Initialization stopped before telemetry polling, leaving Connecting / NO DATA. This was a stale-process/template and mixed-asset problem, not merely a browser cache or empty database.

Both verified port-5000 listeners were stopped; other ports were left alone. No database was reset, copied over or deleted. The corrected application was launched with the exact command `python app.py` from D:\College Projects\CBP IOT\Fleet Mitra. Startup printed the venv interpreter and original instance/fleet_mitra.sqlite3 path. The system Python lacks Flask, so the bare command now delegates to the existing project venv automatically.

Changes:

- `app.py`: retain Flask/create_app and all blueprints; use a threaded Werkzeug server with address reuse disabled and Windows SO_EXCLUSIVEADDRUSE. Reserve the port before database initialization; a second launch fails before touching trip recovery. Print project/interpreter/database/URL. Enable Jinja template reload, content-hash static URL versions, and cache revalidation for HTML/static responses. Backend Python changes still require a restart.
- `templates/index.html`: Drivers and Trip History links exist in initial HTML as well as the enhanced sidebar; JavaScript-disabled guidance added.
- `templates/review_controls.html`: initial heading is Plan your journey, not Operations control. Current template already excludes Demo Scenarios; it now actually reaches port 5000. Advanced coordinates remain in the collapsed Exact coordinates disclosure after initialization.
- `tests/test_dashboard_delivery.py`: four new regression tests cover the complete dependency-ordered/versioned script bundle, no scenario/operations headings, template reload, asset-content invalidation and duplicate listener rejection.
- `README.md`, this report and `docs/port-5000-fixed.png`: updated diagnosis and fresh browser evidence.

Verification: **204 passed, 0 failed, in 28.76 seconds** (all previous 200 retained). `git diff --check` passed. A second real `python app.py` invocation exited with code 1 and an explicit port-in-use message. Fresh port-5000 browser displayed Backend connected, map-first layout, Home in map and planner, Drivers, search fields, history and Change Destination. Home centered the map; Photon returned Uppal suggestions and selection worked; the dynamic-destination panel opened and cancelled; Drivers/Add Driver form loaded; history displayed the existing trip. Browser error log was empty. Screenshot: [corrected port 5000](docs/port-5000-fixed.png).

Original Trip #1 remains ACTIVE with 416.2926711184512 m and its original telemetry. SQLite integrity is ok. The default database still has zero drivers; none were fabricated or copied from QA. Its last GPS sample is from October 27, so GPS data stale is an honest telemetry status, distinct from backend disconnection. This audit did not stop/complete that legacy trip or submit a new destination; full mutation workflows remain covered by the regression suite and earlier recorded browser verification. No hardware verification is claimed.

Launch from the project directory with `python app.py`, then open http://127.0.0.1:5000. One corrected server is left running. Local commit only; no GitHub push.

## Saved-work audit — current findings

The final implementation is saved in this exact project and was already committed as f59f113b960a75f2e8795b4a3bee765aaf35b9d0 on main. Initial working tree was clean. Earlier no-Git statements below are historical and superseded. See [FLEETMITRA_AUDIT_REPORT.md](FLEETMITRA_AUDIT_REPORT.md) for requirement coverage, exact changed files and database distinctions. Fresh suite: **200 passed, 0 failed, 31.42 seconds**. A new browser trip (#4) completed after automatic rerouting and a destination change; all saved rows across six trip/driver tables survived an actual Flask restart unchanged. No application code or tests needed modification. The audit updates documentation and adds a browser screenshot, then makes a local commit without pushing.

The default database had zero drivers and one trip; the final-feature review database had one driver and three trips before this audit. They are separate datasets using the same code. Review now includes the fourth, real audit simulation trip. No databases were deleted, reset or merged.

## Dynamic destinations and Driver Management — final completion

**Status: READY FOR DEMO (verified local software simulation).** Physical GPS/ESP32 hardware is not claimed complete. The existing application was extended, with no framework replacement or destructive database operation. The actual starting baseline was **161 passed in 19.53 seconds**. Final verification: **200 passed in 30.19 seconds, 0 failed**; all 161 earlier cases remain. JavaScript syntax and Python compilation passed. Thirty-nine new pytest cases cover drivers and dynamic destinations; the existing optional Node checks remain included.

### Implementation and files saved

| Area | New or modified files |
| --- | --- |
| Driver backend | New `services/driver_service.py`, `routes/driver_routes.py`; updated `requirements.txt` with `cryptography`, `.env.example` with key guidance |
| Dynamic destinations | New `routes/destination_routes.py`; updated `services/routing_service.py`, `services/route_planner.py`, `services/trip_archive.py`, `services/simulation_service.py` |
| Integration/schema | `app.py`, `database.py`, `routes/trip_routes.py`, `routes/operations_routes.py`, `routes/history_routes.py` |
| UI | New `templates/drivers.html`, `templates/journey_extensions.html`, `static/js/drivers.js`, `static/js/journey_extensions.js`, `static/css/drivers.css`; updated `templates/index.html`, `templates/history.html`, `static/js/app.js`, `static/js/map.js`, `static/js/review.js`, `static/js/workspace.js`, `static/js/history.js`, `static/css/workspace.css`, `static/css/history.css` |
| Verification/docs | New `tests/test_drivers_destinations.py`, root `PROJECT_DEMO_GUIDE.md`; updated README, both guides in `docs/`, this report; saved browser evidence screenshots in `docs/` |

Driver Management supports generated unique IDs, name-only minimal registration, optional validated private/professional details, calculated age, masked phone/license, edit/view, search/status filters, vehicle assignment/unassignment and activation/deactivation. A fictional sample-name button explicitly labels sample profiles; no real personal data was generated. Available drivers assigned to FM01 appear in the searchable trip selector. The compact live driver panel is collapsible.

Driver status derives from persisted active trips plus the active-profile flag. Database transactions and unique indexes enforce one driver per assigned vehicle and one active trip per driver. Assignment changes are blocked during active trips. A deactivated profile remains unavailable after its trip ends. Driver analytics use saved trips, GPS speeds and events. Each new driver-linked trip snapshots only driver ID/name/sample flag; later profile edits never rename historical journeys. Legacy trips remain Unassigned. Dashboard starts require a driver; legacy API clients may omit it only while the registry is empty, preserving initial hardware/API compatibility.

Private DOB, gender, phone, email, address and license number are encrypted using Fernet. The encryption key comes from `FLEET_DRIVER_KEY` or a generated `driver-profiles.key` beside the database. Routine lists mask phone/license; full profile reads are explicit and `no-store`. CSV/JSON trip exports contain driver ID/name snapshots, not private profile fields. Back up the original key separately from the database. These pages retain the existing localhost operator trust model; production authentication and deployment are outside this upgrade.

### Destination planning and activation

Change Destination opens a separate panel with search, map selection, exact Home, a proposal preview, Confirm and Cancel. It does not mutate ordinary planner fields or stop movement. Confirm requests genuine road alternatives from the latest fix and recommends the lowest simulated-traffic-adjusted ETA. Provider calls run outside the simulation lock. The user selects an alternative before Apply.

Proposals are persisted with a random ID, trip ID, navigation revision, destination, allowed route IDs and creation time, expiring for activation after five minutes. Apply locks/validates the current active trip, proposal membership, revision and latest-position projection. Repeated application is idempotent; competing proposals cannot overwrite a newer navigation revision. Moving away from the proposed road geometry triggers refreshed choices, requiring review again. Provider failures preserve the old route/destination. Simulation settings, trip ID, driver, start time, accumulated distance and logical time remain intact. Navigation offset, remaining distance, planned total and progress are revised. Paused sessions remain paused.

Live QA caught OSRM snapping a paused fix about 40 m to another road, which was correctly rejected. Destination planning now uses a 10 m origin radius plus documented `snapping=any` so a fix on a valid driving edge excluded as a default start point can remain on its current segment. The same live request then returned an origin within the coordinate precision of the fix and activated successfully. Ordinary manual trip planning retains its existing 150 m snapping allowance. No off-road connector or fabricated alternative was added. [OSRM API reference](https://project-osrm.org/docs/v5.24.0/api/#general-options).

Successful activation emits a persistent DESTINATION_CHANGED event and the exact requested Destination Updated acknowledgement. Event details retain previous/new endpoints, time, fix, travelled/old/new remaining distance, ETA, traffic and selected route. Immutable route snapshots are archived in the same transaction. Original destination is retained separately from the final/current one. Map layers update in place; the current vehicle remains, earlier persisted path is grey, remaining navigation blue, and Follow state is retained. Fit New Route is explicit. Follow also scrolls the map into view on shorter screens.

### Additive schema changes

Added `drivers` (identity, assigned-vehicle FK, active/sample flags, experience/dates, masks and encrypted private JSON) and `destination_proposals` (proposal/trip/revision/destination/allowed routes/timestamp/applied-route FK). Added nullable trip driver ID/name/sample and original-destination JSON, plus a navigation revision defaulting to zero. Added unique active-driver-trip and unique assigned-vehicle indexes and driver-trip history index. Existing trips/locations/events/route versions are reused. No table reset, deletion, destructive migration or firmware change occurred.

History adds driver filters/name snapshots and original/final destination fields. Events are chronological. The map distinguishes original plan (purple), destination replacements (teal), deviation reroutes (amber), actual recorded GPS (blue). Historical routes come only from persisted data; missing legacy metadata is not fabricated.

### Actual verification evidence

- **Trip #1, live browser:** registered `Sample Driver 01` as fictional, assigned FM01, selected driver, Home origin and searched Uppal destination. OSRM supplied two real alternatives. Started at 40 km/h / 1×, enabled zoom-17 Follow, selected Home in a change panel and cancelled without a committed change. Searched Habsiguda, received two genuine new alternatives and applied the recommendation while moving. Trip #1 and its driver/start time/settings remained; distance continued. Destination Updated appeared after activation and Follow remained true.
- Triggered Test Route Deviation after the destination change; this run found a provider-returned alternative road prefix. Confirmed deviation warning and actual accepted OSRM reroute to the new destination. Explicitly applied 8× later to finish. Trip #1 reached Habsiguda as COMPLETED / ARRIVED: **7.15 km**, **644 logical seconds**, **936 saved positions**, **one destination change**, **one deviation**, **one accepted reroute**, three route versions. Original Uppal and final Habsiguda remained in history.
- Browser-tested profile editing to `Sample Driver 01 Updated`, unassign/reassign and deactivate/reactivate. Historical Trip #1 still showed `Sample Driver 01`, while the profile/table changed. Driver statistics correctly showed one completed trip, 7.15 km, 39.9 km/h average and 40 km/h maximum at that stage. Individual history links/filtering worked.
- Stopped and restarted Flask against the same isolated database. SHA-256 digests of all rows in drivers, trips, locations, trip events, route versions and destination proposals matched before/after. Reloaded history and driver details successfully. SQLite integrity was `ok` and foreign-key checks returned no violations.
- Repeated the full row-digest restart check after Trip #2 was stopped; both saved trips, driver profile, events and all route/proposal records remained identical. The final software version is left running on port 5004.
- **Trip #2, live browser:** searched Uppal as origin, exact Home as destination, same registered driver with updated profile name. Started then paused. Expanded live Driver Information showed driver ID/name, FM01, PAUSED, zero speed, origin and Home. Same-destination confirmation returned a no-op. Manual map selection proposed a different location. After the exact-origin fix, it activated while remaining PAUSED. A second change returned to exact Home; Follow remained off, with unchanged trip ID/driver/settings and no added movement. Stop saved STOPPED with **two destination changes**; Trip #1 remained intact.
- Driver/history pages inspected at desktop and **390×844 mobile**; document scroll width was 375 px at the 390 px viewport. Large tables scroll within their container; details stack. Earlier map clarity/zoom checks remain recorded below. Console inspection before deliberate server interruptions returned no errors; server restarts naturally caused brief failed-fetch/reconnection indications.
- Automated tests cover minimal/full registration, privacy/encryption/masking, profile edit, validation, age/date/phone/email/license errors, assignments/conflicts, eligible selection, status release/deactivation/restart, statistics/snapshots, legacy compatibility, moving/paused/multiple destination changes, no-op/nearby destinations, failure/expiry/foreign-route rejection, cancellation-equivalent uncommitted proposals, movement during provider calls, idempotence, concurrent competing activations, route/driver persistence and deviation after a change. Tight origin query parameters have a dedicated regression.
- Exact requested destination identity is read from the latest persisted destination change (or original trip metadata), rather than a road-snapped reroute endpoint. An additional regression proves choosing exact Home after rerouting remains a no-op even when road geometry snaps several metres away.

Screenshots: [destination updated](docs/destination-updated.png), [historical route layers](docs/dynamic-trip-history.png), [driver management](docs/drivers-verified.png), [mobile history](docs/dynamic-history-mobile.png), [mobile driver details](docs/drivers-mobile.png), [stopped trip with multiple changes](docs/paused-destination-history.png).

### Finalization, startup and limitations

`git status --short` again reported that the folder is not a Git repository. All files are saved locally; no commit hash exists and nothing was pushed. No temporary debug files were introduced. QA SQLite files and the persistent encryption key live under the already ignored `instance/`; screenshots are intentional review evidence.

Normal launch:

```powershell
Set-Location 'D:\College Projects\CBP IOT\Fleet Mitra'
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5000. Current isolated final-feature instance:

```powershell
$env:FLEET_DATABASE='instance/final-features-qa.sqlite3'
$env:FLEET_PORT='5004'
.\venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5004. Complete usage/configuration/viva notes: [PROJECT_DEMO_GUIDE.md](PROJECT_DEMO_GUIDE.md). Tests: `.\venv\Scripts\python.exe -m pytest -q`.

Known limits: single-vehicle/local-operator prototype; public OSRM, Photon and map services can throttle/fail, and alternative counts vary. An origin without a routable road within 10 m may need a fresh valid fix/retry; stale routes are not forced. Traffic is simulated. Driver DOB/license details are optional for review; supplied expired licenses prevent new trips. Encryption key loss prevents private-profile decryption. No physical ESP32/GPS, speaker, physical Retina/high-DPI or touchscreen integration is claimed. Software simulation end-to-end, database persistence and the requested driver/destination workflow were actually verified.

## Earlier UI, navigation, search and permanent history upgrade — historical

The existing Flask/SQLite/Leaflet architecture was inspected and extended incrementally. The actual starting suite was **144 passed in 15.35 seconds**, not the previously reported 136. No existing tests were removed. Original databases and ESP32 firmware were retained; browser QA used a separate `instance/final-review-qa.sqlite3` on port 5003. This folder is not a Git checkout.

### Files modified or added

| Area | Files |
| --- | --- |
| Configuration and schema | `app.py`, `config.py`, `database.py`, `.env.example` |
| Backend | `routes/history_routes.py` (new), `routes/trip_routes.py`, `routes/operations_routes.py`, `services/trip_archive.py` (new), `services/geocoding_service.py` (new), `services/simulation_service.py`, `services/monitoring_service.py` |
| Dashboard and history | `templates/index.html`, `templates/history.html` (new), `static/css/workspace.css` (new), `static/css/history.css` (new), `static/js/workspace.js` (new), `static/js/search.js` (new), `static/js/navigation_geometry.js` (new), `static/js/history.js` (new), `static/js/map.js`, `static/js/review.js` |
| Automated checks | `tests/test_history_upgrade.py`, `tests/test_geocoding.py`, `tests/test_frontend_navigation.py`, `tests/frontend_navigation.test.cjs`, `tests/frontend_contracts.test.cjs` (all new) |
| Documentation and evidence | README, this report, `docs/REVIEW_GUIDE.md`, `docs/NAVIGATION_GUIDE.md`, final dashboard/history/follow screenshots and `docs/map-zoom-12/14/16/17/18.png` |

### Dashboard and navigation

The sidebar provides Dashboard, Live Tracking, Trip History, Notifications and Settings. The 300 px planner collapses to 65 px; the map expands across the remaining workspace. Exact coordinates, routing preferences, review/testing controls, analytics and geofence/hardware setup are disclosures. Five essential metrics sit above the map. Notifications use a drawer; acknowledgement alerts are nonblocking. Existing controls were moved with their handlers attached instead of replacing backend functionality. At 1440 px with the planner collapsed, the measured map width was approximately 1112 px. Mobile uses a stacked map/planner layout.

Selected road geometry is bright blue with a dark outline, rounded joins and zoom-dependent width. Alternatives are thinner muted grey. Route progress splits the actual geometry into grey travelled and blue remaining sections; existing polyline coordinates update in place. The SVG navigation arrow rotates with movement and stays above route lines. A global 19 px SVG icon rule was clipping Leaflet overlays; a scoped override restores Leaflet-owned SVG dimensions. Geofence layers only rebuild when zone configuration changes.

Follow starts disabled until a fix exists. Enabling smoothly zooms to 17 and pans on fresh timestamps, placing the vehicle below center for more space ahead. Disabling stops ongoing camera animation and preserves the current view. Drag, wheel, double-click, keyboard, pinch and zoom buttons suspend Follow. Fit Entire Route and Go to Home are separate camera actions. Active-route restoration and accepted rerouting retain an enabled navigation camera. Exact Home remains **17.415666, 78.573060**, available as either endpoint without becoming an automatic origin.

Deviation still uses the shared monitoring logic. A warning, off-route marker halo and rerouting message precede replacement activation. Only a validated, accepted route produces success; failure retains the original route and pauses. The optional Test Route Deviation remains in advanced controls. The live tested episode used an explicitly labelled synthetic offset when no suitable alternative road prefix was available, then accepted a genuine OSRM replacement.

### Search and map clarity

Starting/destination search uses Photon through Flask, with 650 ms debounce, six-result limit, 5-second timeout, strict coordinate validation, per-process serialized 750 ms outbound rate limiting and a ten-minute/128-query cache. Native clear, keyboard navigation, loading/empty/error messages and stale-request cancellation are implemented. Home resolves locally. Map/coordinate input remains independent. Configure `FLEET_GEOCODING_ENABLED` and `FLEET_GEOCODING_URL`; no Google keys or public Nominatim autocomplete are used.

OpenStreetMap Standard Map remains the default (native maximum zoom 19). Optional localhost Navigation Map uses Stadia Alidade Smooth (native maximum 20) and supported `{r}` high-DPI raster tiles. Stadia/OpenMapTiles/OSM attribution is included. Navigation tile errors switch to Standard Map. No blurry CSS filters, artificial tile upscaling, bulk prefetch or nonfunctional satellite option were added. Stadia development access is rate limited, so the option is restricted to localhost/127.0.0.1; remote deployment requires a separately licensed integration. Photon public demo access is fair-use without availability guarantees. Provider policies and configuration are linked in the [review guide](docs/REVIEW_GUIDE.md).

### Database schema and trip persistence

Additive nullable `trips` columns capture creation/start label, original route ID/distance/ETA/simulated traffic, initial speed/acceleration and end reason. New `trip_route_versions` stores version ID, trip/route foreign keys, timestamp, reason and immutable full route JSON. Trip/date and archive indexes were added. Existing `locations`, `trip_events`, notifications and their indexes are reused. No destructive migration or status-CHECK table rebuild was performed.

Successful Start creates the record and original geometry snapshot transactionally. Accepted reroutes archive replacement geometry within activation. The same trip accumulates GPS samples and events through pause/resume, geofence changes, deviation, rerouting, arrival and stop. Existing unique active-trip/session indexes prevent duplicate starts. Reset after arrival no longer appends a misleading TRIP_STOPPED event to the completed record. Reset/new trip never overwrites old history. RUNNING sessions become PAUSED on process restart without invented catch-up movement.

The original SQLite status constraint/API compatibility is retained; the new history `lifecycle_status` and end reason distinguish STOPPED from COMPLETED/ARRIVED. Legacy records are preserved without fabricating missing original geometry. Simulation duration/average speed use logical time; UTC creation/start/end timestamps are wall time. Meaningful accepted GPS samples use the existing ingestion path and simulator substeps of at most 10 m, independently of browser animation frames. No extra frame-by-frame persistence was introduced.

The dedicated `/history` page offers search, UTC date/vehicle/status/deviation filters, validated sorting and pagination. Details show statistics, requested and snapped endpoints, traffic, events and saved route geometry: original purple, replacement amber, actual recorded path blue. Historical paths never use a current routing API. CSV and JSON export full persisted summary, positions, events and route versions, including nested fields.

### Tests and browser evidence

New automated coverage: seven history tests, eight geocoding cases and two pytest wrappers running eight Node checks. Checks exercise exact Home/endpoints, marker movement/rotation, actual frontend search-coordinate selection, route emphasis/progress without layer recreation, Follow/gesture transitions, completion/stop/events, immutable routes/traffic, filters/pagination, duplicate protection, export, restart recovery and provider failures. Existing routing/geofence/ESP32 payload tests remain intact. Node is optional for these checks and is not an application runtime dependency.

**Final complete suite: 161 passed in 22.70 seconds, 0 failed.** JavaScript syntax checks and Python compilation also passed. The previous full run before the additional frontend wrapper had 160 passes in 19.15 seconds.

Actual browser QA on the isolated review database:

- Search Home locally; search **Uppal Hyderabad** through live Photon; choose the destination with keyboard suggestions. Green/red markers received exact requested coordinates. OSRM returned **two genuine alternatives**, with an honest fewer-than-three explanation and simulated traffic labels.
- Trip #1: 40 km/h, 8×; Start, Pause, reload without duplicate, Resume, Follow at zoom 17, manual pan suspending Follow at the same zoom, arrival. Saved **2.61 km**, **236 logical seconds**, **279 positions**, original route and pause/resume/arrival events.
- Trip #2: 40 km/h, 4×; Test Route Deviation, visible warning, accepted replacement road route, continued simulation and arrival. History showed **2.80 km**, **252 logical seconds**, **331 positions**, **one deviation**, **one accepted reroute**, two archived route versions and the event timeline.
- Stopped and restarted the actual Flask QA process. SHA-256 digests of all rows in `trips`, `locations`, `trip_events` and `trip_route_versions` matched before/after restart. Reloaded Trip #2 in the browser and confirmed its details remained.
- Downloaded Trip #1 CSV through the browser; read the downloaded file and verified **285 data rows**, including 279 location rows plus summary, events and route version. JSON equality/export was checked automatically.
- Trip #3: observed active blue/grey geometry, rotating marker, moving Follow camera below center at zoom 17; Pause and Fit Entire Route; Stop persisted as **STOPPED**, with pause/stop events.
- Rendered and inspected Standard and Navigation layers; inspected Navigation Map at zoom **12, 14, 16, 17 and 18**. Road/locality labels, markers and selected geometry were visible. Desktop **1440×900**, tablet **820×1180**, mobile **390×844** had no document horizontal overflow. History uses a horizontally scrollable table on mobile and stacked details. Browser console error inspection on the tested history/navigation tab returned no errors at the point checked.

Evidence: [desktop dashboard](docs/final-dashboard-desktop.png), [Follow navigation](docs/final-follow-navigation.png), [mobile dashboard](docs/final-dashboard-mobile.png), [tablet](docs/final-dashboard-tablet.png), [saved history](docs/final-history.png), [mobile history](docs/final-history-mobile.png). Zoom captures are saved under `docs/map-zoom-*.png`.

### Remaining limitations and exact startup commands

Public routing, geocoding and tile services can fail or throttle; errors/fallback behavior are handled but availability and three alternatives cannot be guaranteed. Traffic is simulated. Physical Retina/high-DPI screens, browser zoom settings, actual ESP32/GPS hardware and speaker audibility were not independently tested. Touch-pinch suspension is regression-tested at the event boundary, without a physical touchscreen test. Older trips cannot gain geometry that was never saved. This remains one local review vehicle, without high-volume fleet downsampling or production authentication/deployment changes. SQLite survives normal restarts; backups remain necessary against disk loss.

Normal startup from Windows PowerShell:

```powershell
Set-Location 'D:\College Projects\CBP IOT\Fleet Mitra'
.\venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5000. The currently demonstrated isolated review instance runs at http://127.0.0.1:5003 with this command:

```powershell
$env:FLEET_DATABASE='instance/final-review-qa.sqlite3'
$env:FLEET_PORT='5003'
.\venv\Scripts\python.exe app.py
```

Full tests: `.\venv\Scripts\python.exe -m pytest -q`. Fresh setup and the current demo/viva guide are in [README](README.md) and [Review guide](docs/REVIEW_GUIDE.md).

## Earlier navigation and saved Home upgrade — historical

Baseline at the beginning of this upgrade: **136 passed in 14.69 seconds**. Existing schema, routing/simulation services, frontend and tests were inspected. This folder remains outside Git; no database reset or firmware changes were made.

Implemented: persistent Home configuration with exact **17.415666, 78.573060**; map and planner Home shortcuts; Home as either endpoint; separate Go to Home; saved-place/coordinate search; draggable green/red endpoints; automatic planning; clickable colored route alternatives; near-duplicate filtering; stable persisted SIMULATED TRAFFIC and explicit refresh; best adjusted-ETA recommendation; map-first responsive layout. Removed preset scenario selectors from the main interface while retaining backend compatibility. Deviation popups are queued so quick replacement success cannot overwrite the initial warning. Automatic rerouting preserves its setting after successful replacement. The testing control first seeks a genuine alternative road prefix, otherwise clearly identifies a synthetic offset.

Major files changed: `config.py`, `database.py`, `routes/operations_routes.py`, `services/route_planner.py`, `services/simulation_service.py`, new `services/traffic_service.py`, `static/js/map.js`, `static/js/review.js`, `static/css/review.css`, `templates/index.html`, `templates/review_controls.html`, new `tests/test_navigation.py`, README and navigation guide. Migration adds nullable route comparison/requested-endpoint columns; original stored data is retained.

Automated interim result: **143 passed**, including all 136 previous tests. JavaScript syntax and Python compilation checks passed. An additional Home-specific automatic-rerouting regression was then added; final results are recorded below.

**Final complete result: 144 passed in 14.74 seconds**, including Home-specific automatic reroute destination preservation. No tests were deleted or weakened.

Browser evidence: used isolated `instance/navigation-qa.sqlite3` on port **5002**. Home as Start populated 17.415666 / 78.573060 and the marker carried those exact numeric values. A live OSRM request to 17.420000 / 78.580000 returned **one** distinct road route (1.17 km), honestly reported as fewer than three. Stable traffic comparison displayed. At physical 40 km/h / 8×, start, pause and resume worked. Go to Home preserved route ID/card. Controlled deviation generated one event, actual OSRM rerouting returned and accepted a ROAD_ROUTE, simulation continued and ARRIVED persisted. Summary: 1.30 km accepted GPS-segment distance, 115 logical seconds, one deviation and one reroute. Screenshot: [Home road arrival](docs/home-road-arrival.png). A reverse live plan using Home as Destination also returned one valid road route. Dragging D changed manual destination coordinates while leaving saved Home unchanged. Provider latency caused one earlier request failure; retry succeeded and the failure was displayed honestly.

Limitations: three live alternatives were not available for the tested Home pair; three-option handling is covered with deterministic provider mocks. Global geocoding is not configured; saved Home, coordinates, and unrestricted map input are available. Traffic is a labelled comparison-only model, not live traffic and not an input to physical simulation velocity. Synthetic off-route geometry is used only by the explicit testing control when a suitable alternative road prefix is unavailable. Actual device sound output and physical ESP32/GPS integration remain unverified. No personal location was made a default origin.

Run normally with `.\venv\Scripts\python.exe app.py`, open http://127.0.0.1:5000. The isolated QA instance is http://127.0.0.1:5002. See [Navigation guide](docs/NAVIGATION_GUIDE.md) for current controls, calculations and APIs.

## Initial audit and stabilization

The interrupted session added backend review services but left them disconnected from the earlier dashboard. Repository inventory, README, requirements, configuration, schema, routes, services, CLI sender, HTML/CSS/JavaScript and tests were inspected before editing. Git status reports that this folder is not a Git repository. Baseline source/database backups exist in `instance/upgrade-backup/`; no existing database was deleted, reset or replaced in this session. Firmware was left untouched.

Original baseline: **91 passing tests** (previous implementation). Resumed-state audit: **134 passed in 13.63 seconds**, using `venv\Scripts\python.exe -m pytest -v`. This established backend evidence, not proof of frontend integration.

| Feature | Initial status / evidence | Work completed |
| --- | --- | --- |
| GPS tracking | Working; location tests and original dashboard | Preserved shared ingestion and CLI |
| Trip management | Working; lifecycle tests | Added connected review controls and summaries |
| Route planning | Backend working; planning tests | Map origin/destination, route comparison and selection |
| Route alternatives | Mocked provider tests pass | Render only returned options |
| Speed controls | Backend working; review tests | Presets, numeric control, live change |
| Acceleration | All five factors tested | Exposed 1/2/4/8/16 independently of physical speed |
| Geofencing | Transition/persistence tests pass | Scenario zone, timeline, sound and notifications |
| Deviation | Sustained/noisy/recovery tests pass | Browser trigger and warning presentation |
| Automatic rerouting | Missing | One-attempt automatic road/demo replacement, safe failure |
| Notifications | Backend persistence/read tests pass | Alert center, count, mark-read controls |
| Sound | Missing | Web Audio tone categories and persistent mute |
| Dashboard | Partial; earlier UI only | Connected operations panel, route map layers, progress |
| Analytics | Backend summaries tested | Summary dialog, event timeline, historical detail |
| ESP32 | Payload tests pass; hardware untested | Preserved firmware and API |

## Implementation decisions and files

Incremental changes kept the earlier dashboard and API contracts. `templates/review_controls.html`, `static/js/review.js` and `static/css/review.css` extend the existing page. `templates/index.html` includes them. `static/js/map.js` exposes route rendering and map selection without recreating the map. `static/js/app.js` now confirms geofence deletion. `services/simulation_service.py` adds optional automatic rerouting and start/stop notifications. `simulator/demo_routes.json` adds a labelled long-distance fixture and urban delivery name. Tests add automatic rerouting coverage and account for the new real trip-start alert. README links the current review guide; this report records outcomes.

The same ingestion function processes simulator and ESP32 readings. Logical time is separate from UTC telemetry time. Geofence events still require a transition; deviation requires consecutive off-route points; arrival uses a radius and route-end condition. Deduplication and unique trip/session constraints prevent retries from creating duplicate trips, arrival notifications or distance.

## Automated verification

After integration and automatic rerouting: **135 passed in 13.28 seconds**. A further regression test checks that failed automatic road routing retains the original plan and pauses safely; the final suite contains 136 tests. No existing tests were deleted. The notification-count assertion increased to include the newly implemented trip-start notification. The original 91 tests still pass. Deterministic tests cover pause/resume, speed/ETA, factors, arrival, state persistence, migration, geofences, recovery, routes and notifications. JavaScript syntax was checked with Node; it is not an application dependency.

## Manual verification performed

**Final complete suite: 136 passed in 13.64 seconds** (`python -m pytest -v`). Map destination picking was also rechecked after the click-capture fix and populated latitude successfully.

Used a separate SQLite database, `instance/review-qa-20261030.sqlite3`, on port 5001 to preserve the operator's existing active legacy trip on port 5000. The browser loaded the quick-review fixture with the geofence scenario, started at physical 40 km/h and 8×, paused, changed to 20 km/h, resumed, and triggered deviation. Timeline confirmed one ROUTE_DEVIATION, one REROUTE_ACCEPTED, then normal movement. ENTER and EXIT occurred. Arrival summary persisted **1.15 km**, **208 logical seconds**, **two geofence events**, **one deviation**, and **one reroute**. ARRIVED survived a page refresh. Mark all as read changed unread count to zero. Web Audio dispatch recorded DESTINATION_REACHED; actual speaker audibility was not independently measured. Browser console showed no errors during this run.

Desktop, 820 px tablet and 390 px mobile layouts were inspected. DOM width checks showed no horizontal overflow at the smaller sizes. Map start selection populated coordinates; a click-interception issue over an existing marker was fixed by capturing the selected map click before marker handling. The screenshot [review-completed.png](docs/review-completed.png) records the actual completed trip summary. Live OSRM route success remains provider-dependent and was not established during this session; deterministic provider response tests and local fixture paths passed.

## Run and demonstrate

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5000. Existing active legacy trips should be stopped by the operator before a new simulation. For a separate demonstration database and port:

```powershell
$env:FLEET_DATABASE = 'instance/my_review.sqlite3'
$env:FLEET_PORT = '5001'
.\venv\Scripts\python.exe app.py
```

Use [the current guide](docs/REVIEW_GUIDE.md) for the five-minute demo, APIs, calculations and viva explanations. Recommended review: quick demo + geofence scenario → 40 km/h, 8× → change to 20 → pause/resume → deviation/automatic reconnect → ENTER/EXIT → arrival summary → history → refresh.

## Limitations and next steps

Physical GPS, firmware compilation, live road driving accuracy and actual device audio output are not established by automated tests. OSRM and map tiles depend on internet; local fixtures are clearly illustrative and support offline operation. The simulator is a single-process local prototype. No traffic information, SMS, WhatsApp or email is fabricated or transmitted. Improve road-fixture fidelity and physically validate ESP32/UART/Wi-Fi when hardware is purchased; no architectural rewrite is needed.

