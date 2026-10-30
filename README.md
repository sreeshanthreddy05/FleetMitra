# FleetMitra

**Port 5000 mismatch fixed:** The old dashboard was served by a stale Flask process sharing port 5000 with another process, not by missing feature files. Startup now binds the port exclusively before opening SQLite, prints the exact project/database/Python paths, and uses the local venv when launched with bare `python app.py`. Stop an existing server with Ctrl+C before starting another. Asset URLs are content-versioned and templates revalidate. See the latest section in [FLEETMITRA_PROGRESS_REPORT.md](FLEETMITRA_PROGRESS_REPORT.md). Verified on port 5000 with the original database: **204 tests passed**.

**Saved-work audit (30 October 2026):** All final feature modules are saved in this checkout and were already included in Git commit f59f113. See [FLEETMITRA_AUDIT_REPORT.md](FLEETMITRA_AUDIT_REPORT.md). The default database and review database contain different records; use the launch commands below for the dataset you intend to review.

**Final features — Drivers and destination changes:** Register a driver, assign FM01, select the driver, start navigation, then change destination during the same active/paused trip. Review fresh route alternatives before activation. Driver snapshots, original/final destinations and all route versions remain in SQLite. Start with [PROJECT_DEMO_GUIDE.md](PROJECT_DEMO_GUIDE.md). Install updated dependencies with `.\venv\Scripts\python.exe -m pip install -r requirements.txt` (adds authenticated encryption for private driver fields). Back up the database and its `driver-profiles.key`; keep the server bound to localhost for this local operator prototype. **200 tests passed, 0 failed** from a verified baseline of 161. The isolated review configuration uses [port 5004](http://127.0.0.1:5004).

**Final navigation upgrade (30 October 2026):** A spacious, collapsible planner surrounds the large map. Search for places, use exact saved Home, or select endpoints manually. Compare genuine road routes with clearly simulated traffic, follow the rotating vehicle at zoom 17, and watch the travelled line turn grey. Automatic rerouting and the optional deviation test remain available.

**Permanent Trip History:** SQLite stores trips, driver snapshots, GPS samples, destination changes, events, original routes and replacements. History provides driver/date/status filters, pagination, historical maps and complete CSV/JSON exports. Restarting pauses unfinished simulations for explicit resumption. Read the [final demo guide](PROJECT_DEMO_GUIDE.md), [navigation guide](docs/NAVIGATION_GUIDE.md), and [progress report](FLEETMITRA_PROGRESS_REPORT.md). Original CLI and ESP32 contracts remain; older test counts below are historical.

**IoT-Based Smart Vehicle Tracking and Fleet Management System**

A working single-vehicle college prototype for **FM01**. Track location on a live map, start and stop trips, measure distance, choose a destination, estimate arrival, and record geofence crossings. Everything is demonstrable with the included Python GPS simulator.

**Current status: software prototype. Simulator readings are labelled `SIMULATED`. Hardware integration is prepared but not physically tested because hardware is currently unavailable.**

## How the project works

```text
Now:    Python GPS simulator ──┐
                              ├─ POST /api/locations → Flask → SQLite
Later:  NEO-6M GPS → ESP32 ─────┘                           ↓
                                              Distance / trips / geofences / ETA
                                                          ↓
                                              Dashboard polls every ~3 seconds
```

The simulator uses actual HTTP requests to the **same location endpoint** as future hardware. There is no simulator-only tracking path and no generated dashboard telemetry.

Stack: Python 3, Flask, SQLite, HTML, CSS, vanilla JavaScript, Leaflet 1.9.4, OpenStreetMap and pytest. No Node.js, frontend build step, Docker or database server is required. All application timestamps are stored in UTC; the browser displays local time.

## Installation — Windows PowerShell

Install Python 3.11 or newer (verified here with Python 3.13), then open PowerShell in the project directory:

```powershell
Set-Location 'D:\College Projects\CBP IOT\Fleet Mitra'
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The activation command is **`.\venv\Scripts\Activate.ps1`** in PowerShell. After activation, the prompt normally starts with `(venv)`.

If PowerShell blocks script activation, you can run everything without activation:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe app.py
```

Dependencies need internet access for their initial installation. Leaflet's JavaScript and CSS are already bundled locally.

## Start the backend

From the project directory, with the environment activated:

```powershell
python app.py
```

Expected address: **[http://127.0.0.1:5000](http://127.0.0.1:5000)**.

Flask creates `instance/fleet_mitra.sqlite3` automatically and registers FM01. The first launch has no locations, trips, or geofences. Restarting retains all data. The database folder is ignored by Git. Stop Flask with Ctrl+C.

Check health in another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health
```

Expected JSON: `{"status":"ok","database":"connected"}`.

## Open the dashboard

Visit **[http://127.0.0.1:5000](http://127.0.0.1:5000)** in a modern browser. The page uses backend APIs and refreshes its values without reloading. It initially says **Waiting for GPS data…**, **No active trip**, and **ETA unavailable**. It shows **Backend disconnected** when API requests fail, and **STALE GPS** when the last fix is more than 30 seconds old.

The initial map is centered on the **sample area**, not a vehicle position. FM01's marker appears only after a real API reading. Map tiles need internet; without tiles the local Leaflet map still supports markers, circles, and coordinate selection on a grid. You can always enter coordinates manually.

## Start the GPS simulator

Keep Flask running. Open a **second PowerShell terminal** in the project directory:

```powershell
.\venv\Scripts\Activate.ps1
python simulator/gps_simulator.py
```

Or, without activation:

```powershell
.\venv\Scripts\python.exe simulator/gps_simulator.py
```

It sends a valid, UTC-stamped location for FM01 to `/api/locations` about every **3 seconds**, with `source: "SIMULATED"`. The terminal prints coordinates, speed, acceptance status, and ETA state. Initial speed is zero; subsequent speed uses movement and elapsed time.

The bundled route contains 68 illustrative coordinates around **Tank Bund, Hyderabad**, about 1.76 km overall. It is artificial sample data, not recorded GPS or a surveyed road path. It starts south of the demo zone, enters the zone, pauses briefly inside, exits, and reaches the destination. A full pass takes about 3½ minutes plus request time. Default speeds are roughly 25–40 km/h, depending on network latency.

Useful options:

```powershell
# Continue back and forth; reversing avoids a teleport at the end of a loop.
python simulator/gps_simulator.py --loop

# Faster playback (reported simulated speeds increase accordingly).
python simulator/gps_simulator.py --interval 1.5

# Send only a few readings for a quick connection check.
python simulator/gps_simulator.py --max-points 5

# Use another backend address or route JSON file.
python simulator/gps_simulator.py --url http://127.0.0.1:5001 --route simulator/sample_route.json
```

Ctrl+C stops the simulator. Connection failures retry the **same timestamp and payload**, so a lost HTTP response cannot add distance or events twice. A 4xx validation error stops with an explanation. Run only one location sender for FM01 at a time.

## FleetMitra 5-Minute Demo

1. **Start Flask.** Run `python app.py`. Open the dashboard. On a fresh database, point out **Waiting for GPS data** and the empty histories. If previous data exists, it is intentionally retained; see the fresh demo option below.
2. **Prepare the demo zone.** In Geofence zone, click **Use demo zone ↗**, then **Create Geofence**. The preset is center `17.4174, 78.4825`, radius `100 m`. Before GPS data arrives, its state is **WAITING FOR GPS**. In Trip manager, click **Use demo destination ↗** to fill `17.4237, 78.4881`.
3. **Start the simulator.** In the second terminal, run `python simulator/gps_simulator.py`. Within one polling cycle, FM01 appears with coordinates, speed, and the obvious **SIMULATED** badge. The first point initializes geofence state as OUTSIDE without a fake event.
4. **Start a trip promptly.** Click **Start Trip** in the dashboard. It uses the latest GPS location as the start. Alternatively, click **Pick on map**, click a location, add a label, and start the trip. Press Esc to cancel map selection. For this demonstration, keep the demo destination so the route actually reaches it.
5. **Show tracking and ETA.** Watch the marker move and trip kilometers increase. The dashboard displays remaining kilometers and ETA. `ROAD_ROUTE` means OSRM road distance and model duration; `FALLBACK` means clearly labelled straight-line distance divided by rolling GPS speed. During the brief pause, ETA says **WAITING FOR MOVEMENT**. Once within 35 m of the destination, it says **Arrived**. Arrival does not automatically stop the trip.
6. **Show geofencing.** Roughly 80–100 seconds into the default route, the zone becomes **INSIDE** and an **ENTER** event appears. A short pause lets you inspect it. About 25–35 seconds later, FM01 moves out: **OUTSIDE**, then **EXIT**. Remaining in the same state never produces repeated events. Exact timing depends on request latency. The GPS history shows the actual accepted points.
7. **Stop the trip.** Click **Stop Trip**, then **Completed trips** in Recent activity. Show the stored start/end times, destination, COMPLETED status, and distance. Restart Flask to demonstrate SQLite persistence.

For a slower live demonstration use `--interval 4`. A loop produces another ENTER/EXIT as the vehicle returns; keep the trip active if you want to measure the return leg too.

### Fresh demo without deleting previous data

Stop Flask and the simulator. In the backend terminal set a **new, unused** database filename and restart:

```powershell
$env:FLEET_DATABASE = "instance/fresh_demo.sqlite3"
python app.py
```

Choose another filename for another fresh run. Existing files reopen their saved data. To return to the default database, stop Flask, run `Remove-Item Env:FLEET_DATABASE -ErrorAction SilentlyContinue`, and restart. The simulator still targets the same URL and needs no database setting.

## Calculations and data integrity

- **Distance:** reusable Haversine formula with Earth radius 6,371,000 m. Trips accumulate straight-line segments between accepted GPS positions, not road-route length. A 5 m movement threshold ignores small jitter. Distance uses the last counted point as an anchor so several small forward movements eventually count. Motion before trip start or after stop is excluded. This simple filter reduces jitter; it is not a full GPS noise filter.
- **Speed:** valid supplied GPS speed is preferred. If omitted or null, speed is derived from the previous point's distance and positive timestamp difference. First fix without speed uses zero. Supplied negative/nonfinite/speeds over 200 km/h, impossible derived speeds, and out-of-order timestamps are rejected.
- **Remaining distance:** OSRM road distance if a road route is available, otherwise Haversine straight-line distance. The dashboard explicitly labels fallback distance; it is not presented as road distance.
- **ETA:** OSRM's road travel-time model when available. Fallback uses up to five most recent trip speed samples (km/h), with the latest sample first. A latest speed below 3 km/h, or an average below 3 km/h, returns `WAITING_FOR_MOVEMENT`. A stale fix returns `WAITING_FOR_GPS`. Within 35 m, the last known location is `ARRIVED`. The stale indicator remains visible even at the destination.
- **Routing resilience:** one optional OSRM request has a 1.2 second timeout; successful routes are cached for 30 seconds per approximately 11 m coordinate cell, with a 60 second retry backoff on failure. This is a demonstration estimate, not traffic-aware navigation. Accepted readings are committed before routing lookup.
- **Timestamp contract:** ISO 8601 with a timezone, normalized to UTC microseconds. More than five minutes into the future is rejected; historical timestamps are allowed, but stale data is marked. Same vehicle + same canonical timestamp + identical payload is a successful idempotent retry. Different data at that timestamp gives 409. Older new readings give 409 rather than changing the live state.
- **Atomic writes:** one SQLite transaction stores each location, updates trip distance, and writes geofence state/events together. A unique database index allows only one ACTIVE trip per vehicle. Concurrent duplicate posts insert one reading.
- **Geofences:** circular, using Haversine distance; boundary points count as INSIDE. First fix or newly created boundary initializes its state without an event. State survives restarts. Disabled geofences do not generate events. Deleting a geofence also removes that zone's states and events.
- **Polling:** the dashboard waits for all requests to settle before scheduling the next poll, preventing overlapping polling cycles. Untrusted labels are rendered as text.

## REST API

All errors return JSON such as `{"error":"Unknown vehicle"}`. Create operations return 201; exact location retries return 200 with `duplicate: true`. Validation errors return 400, unknown resources 404, trip/timestamp conflicts 409, oversized requests 413, and database failures 503. GPS-fix rejection does not create a location record.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Backend and SQLite connectivity |
| GET | `/api/vehicles` | Registered vehicles (FM01) |
| POST | `/api/locations` | Shared simulator / ESP32 location ingestion |
| GET | `/api/vehicles/FM01/location` | Latest location, active trip, remaining distance, ETA, geofences, stale flag |
| GET | `/api/vehicles/FM01/history?limit=20` | Latest GPS records, newest first |
| POST | `/api/trips/start` | Start trip from latest known location to a required destination |
| POST | `/api/trips/stop` | Stop and persist current trip |
| GET | `/api/trips/current?vehicle_id=FM01` | Current trip or `null` |
| GET | `/api/trips/history?limit=20` | Completed trips, newest first |
| POST | `/api/geofences` | Create circular geofence |
| GET | `/api/geofences` | List fences with current status |
| GET | `/api/geofences/status` | Current position relative to each fence |
| GET | `/api/geofences/events?limit=20` | Stored ENTER/EXIT events, newest first |
| DELETE | `/api/geofences/<id>` | Delete zone, associated states and events |
| GET | `/api/demo-config` | Form presets from the sample route; never inserts readings |

History/event endpoints accept integer `limit` from 1 to 500. Trip and geofence GET endpoints accept optional `vehicle_id`, default FM01. The latest-location response uses nested `location`, `trip`, `eta`, and `geofences` objects. No location is `location: null`; no active trip or destination means `trip: null` and `eta: null`.

Sample accepted payload (use a **current** UTC timestamp when testing manually):

```json
{
  "vehicle_id": "FM01",
  "lat": 17.4124,
  "lon": 78.4767,
  "timestamp": "2026-10-23T10:30:00Z",
  "speed_kmh": 30.0,
  "gps_valid": true,
  "source": "SIMULATED"
}
```

`vehicle_id`, `lat`, `lon`, `timestamp`, `gps_valid` and `source` are required. `speed_kmh` may be a number, omitted, or null. Latitude is −90 to 90; longitude −180 to 180. JSON numbers must be finite; numeric strings and booleans are rejected. `gps_valid` must be boolean true. `source` must be exactly `SIMULATED` or `HARDWARE`.

Trip start JSON:

```json
{"vehicle_id":"FM01","destination_lat":17.4237,"destination_lon":78.4881,"destination_label":"Demo destination"}
```

Trip stop JSON: `{"vehicle_id":"FM01"}`.

Geofence JSON:

```json
{"vehicle_id":"FM01","name":"Demo Zone","center_lat":17.4174,"center_lon":78.4825,"radius_m":100,"enabled":true}
```

Names/labels are 1–100 characters, radius is 1–100,000 m. `vehicle_id` and `enabled` default to FM01 and true on geofence creation. The dashboard supports create/delete; API clients can create disabled fences.

## Configuration

`.env.example` is a **reference**, not an automatically loaded file. Set environment variables in the terminal that starts Flask:

```powershell
# Completely offline ETA demonstration:
$env:FLEET_ROUTING_ENABLED = "false"
python app.py
```

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `FLEET_DATABASE` | `instance/fleet_mitra.sqlite3` | Relative to project root, or an absolute SQLite filename |
| `FLEET_HOST` | `127.0.0.1` | Local bind interface; future LAN hardware uses `0.0.0.0` |
| `FLEET_PORT` | `5000` | Backend port; update simulator `--url` if changed |
| `FLEET_ROUTING_ENABLED` | `true` | Attempt optional OSRM routing; false always uses fallback |
| `FLEET_ROUTING_TIMEOUT` | `1.2` | OSRM timeout in seconds |
| `FLEET_MIN_MOVEMENT_M` | `5` | Minimum movement before adding trip distance |
| `FLEET_ARRIVAL_RADIUS_M` | `35` | Destination arrival threshold |

Use positive values for thresholds and timeout. The code's remaining simple limits (200 km/h speed ceiling, five speed samples, 30 second stale threshold) are in `config.py`.

## Run automated tests

```powershell
python -m pytest -q
```

Or ` .\venv\Scripts\python.exe -m pytest -q` without activation.

Tests create **separate temporary SQLite databases** and never use the demonstration database. They cover Haversine, speed and ETA, strict location validation, malformed JSON, timezone-normalized duplicates, concurrent retries, stale/out-of-order readings, trip start/stop and jitter filtering, geofence transition initialization and persistence, routing success/cache/failure/backoff, simulator retry behavior, static assets, and a complete simulator route through a real local HTTP server. OSRM success/failure tests are deterministic mocks, so tests need no internet. Local loopback sockets are required for the real HTTP test.

For the actual execution results and manual browser checks from development, see [docs/VERIFICATION.md](docs/VERIFICATION.md).

## Final project structure

```text
Fleet Mitra/
├── app.py                       # Flask factory, health, demo presets, startup
├── config.py                    # Environment settings and calculation thresholds
├── database.py                  # SQLite schema, indexes, connection lifecycle
├── validation.py                # JSON and field validation
├── calculations.py              # Haversine, derived speed, ETA
├── geofence.py                  # Circular boundaries and persistent transitions
├── services/
│   ├── __init__.py
│   ├── tracking_service.py       # One atomic location ingestion pipeline
│   └── routing_service.py        # Optional cached OSRM lookup
├── routes/
│   ├── __init__.py
│   ├── location_routes.py
│   ├── trip_routes.py
│   └── geofence_routes.py
├── templates/index.html
├── static/
│   ├── css/style.css
│   ├── js/app.js
│   ├── js/map.js
│   └── vendor/leaflet/           # Local JS, CSS, license
├── simulator/
│   ├── gps_simulator.py
│   └── sample_route.json
├── firmware/
│   ├── fleet_mitra_esp32.ino     # Prepared, UNTESTED hardware example
│   └── README.md
├── tests/
│   ├── conftest.py
│   ├── test_calculations.py
│   ├── test_locations.py
│   ├── test_trips.py
│   ├── test_geofences.py
│   ├── test_routing.py
│   └── test_simulator.py
├── docs/VERIFICATION.md
├── requirements.txt
├── pytest.ini
├── .env.example
├── .gitignore
└── README.md
```

`venv/`, caches, and `instance/` are generated locally. SQLite tables are `vehicles`, `locations`, `trips`, `geofences`, `geofence_states`, and `geofence_events`. SQL data values use parameters, not string interpolation.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `No module named flask` | Install with the same Python executable used to start the backend; use `venv\Scripts\python.exe` explicitly |
| PowerShell activation blocked | Use the direct virtual-environment executable commands above |
| Port 5000 already in use | Stop the earlier FleetMitra terminal, or use `$env:FLEET_PORT="5001"` and simulator `--url http://127.0.0.1:5001` |
| Backend disconnected | Start Flask, check `/api/health`, and confirm the page URL/port |
| Start Trip disabled | Wait for the first location; only one trip may be active |
| ETA waiting for movement | Start the simulator or wait until it leaves its brief stationary pause |
| ETA says FALLBACK | OSRM is unavailable, unsnappable, disabled or timing out; fallback is expected |
| Blank/grid map | Internet is needed for OSM tiles; markers, zones, manual coordinates and backend still work |
| No ENTER event initially | First point initializes state. Place the zone on the route before crossing it |
| GPS data stale | Simulator stopped or no fresh GPS reading for 30 seconds |
| Simulator gets 409 | Ensure no second simulator/hardware sender is running and the system clock is correct |
| Previous data on startup | SQLite persistence is working; use a new database filename for a fresh demo |

## Viva — simple explanations

**What does GPS do?** It determines the vehicle's geographical position and provides UTC time and often ground speed.

**What does ESP32 do?** It reads GPS NMEA data over UART, connects to Wi-Fi, and posts readings to Flask.

**Why use a simulator now?** Physical ESP32/GPS hardware is unavailable. The simulator produces GPS-like readings and sends them through the exact API that hardware will later use.

**Does it replace hardware permanently?** No. Later, GPS → ESP32 replaces the Python simulator. Everything from the Flask API onward remains the same.

**What does Flask do?** It validates incoming GPS data, stores it, runs tracking calculations, and exposes APIs for the dashboard.

**What does SQLite do?** It stores vehicle details, accepted locations, trips, geofences, persistent boundary states, and events in a local file.

**What is Haversine distance?** An approximation of the shortest surface distance between two latitude/longitude coordinates on a spherical Earth. It is straight-line geographical distance, not driving distance.

**What is geofencing?** A virtual geographic boundary. FleetMitra compares the vehicle's distance to a circle's center with its radius, then records ENTER/EXIT only when the state changes.

**How is ETA calculated?** Prefer OSRM road route duration. If unavailable, divide remaining straight-line meters by average speed in meters per second. Show no moving ETA when stopped; show ARRIVED within the configured arrival radius.

**Why not add distance for duplicate GPS readings?** A retry is the same measurement. A unique vehicle/timestamp key and an atomic transaction prevent double counting.

## Later: purchase ESP32 and NEO-6M

Follow [firmware/README.md](firmware/README.md) for pin connections, correct power/logic levels, Arduino libraries, Wi-Fi credentials, and the laptop's LAN IP. `localhost` on an ESP32 refers to the ESP32, not the laptop. Stop the simulator before enabling hardware input. Compile/upload the sketch and physically verify fixes, movement, Wi-Fi recovery and boundary transitions. **Neither firmware compilation nor physical ESP32/GPS testing has been completed here.**

Reference documentation: [Flask SQLite integration](https://flask.palletsprojects.com/en/stable/patterns/sqlite3/), [Leaflet 1.9.4](https://leafletjs.com/reference.html), [OSRM route API](https://project-osrm.org/docs/v5.24.0/api/). Leaflet's BSD license is included in `static/vendor/leaflet/LICENSE`.



