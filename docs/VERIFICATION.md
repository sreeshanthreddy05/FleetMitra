# Software verification — 23 October 2026

The following checks were actually executed in the Windows development environment with Python 3.13.15, Flask 3.1.3, and pytest 9.1.1.

## Automated results

```text
Command: .\venv\Scripts\python.exe -m pytest -q
91 passed in 5.91s
```

Every test uses a separate temporary SQLite database. No internet request is needed by the suite. The full-route integration test starts a real local HTTP server, uses the simulator's actual HTTP sender to post the bundled 68-point route, verifies all points are stored, checks growing trip distance, ARRIVED, exactly one ENTER and one EXIT, then stops the trip and checks completed-trip history. A separate test exercises an uncertain-delivery retry with the identical timestamp and payload.

Other coverage includes invalid coordinates/JSON/timestamps/GPS fixes/speeds, unknown vehicles, missing fields, stale readings, timezone-normalized duplicates and conflicts, out-of-order rejection, simultaneous duplicate requests, database restart persistence, jitter suppression, trip exclusion before/after its active period, stopped/moving/arrived ETA, disabled/deleted boundaries, initial inside/outside states, and OSRM cache/backoff/fallback/malformed responses.

Additional checks completed successfully:

```text
node --check static/js/app.js
node --check static/js/map.js
python -m compileall -q app.py config.py database.py validation.py calculations.py geofence.py services routes simulator tests
```

## Manual backend, simulator, and browser checks

- Launched Flask at `http://127.0.0.1:5000`; `/api/health` returned `status: ok`, `database: connected`.
- Confirmed automatic database creation and registration of FM01 with no fabricated initial location.
- Opened the dashboard in the desktop in-app browser. Empty state showed waiting for GPS, no active trip, no ETA, and no boundary events. Leaflet and actual OpenStreetMap tiles rendered.
- Created the demo zone and filled the destination using the dashboard's preset buttons.
- Ran the actual CLI simulator with `--interval 1.5 --max-points 68`. All **68 readings were accepted** through `/api/locations` and stored in SQLite.
- Watched FM01 appear and its coordinates and marker update through background polling. The source badge and GPS rows displayed **SIMULATED**.
- Started a trip using the dashboard after several readings had arrived. Cumulative distance reached **1.44 km**, excluding movement before start; remaining distance reached zero and the ETA displayed **Arrived**. FALLBACK was visibly identified as straight-line distance.
- Verified stored boundary events: ENTER at **21:36:52 IST** and EXIT at **21:37:07 IST**; final zone state OUTSIDE. No repeated same-state events occurred.
- Stopped the trip using the dashboard and opened Completed trips. Its destination, start/end times, COMPLETED status and **1.44 km** appeared.
- Selected a new destination by clicking the map; the coordinate input fields changed to the clicked position.
- Verified stale data was labelled **STALE GPS** after the simulator ended.
- Stopped Flask and verified the page displayed **Backend disconnected**.
- Browser console contained no JavaScript errors or warnings at the end of the connected demonstration.

[Dashboard screenshot after the completed demonstration](dashboard-preview.png). The screenshot shows saved demo data; its speed is the last received fix, clearly marked stale after simulation stops.

The manually generated database was preserved in `instance/verification-2026-10-23/fleet_mitra.sqlite3`. Flask was restarted with a fresh default database so the next demonstration begins with **Waiting for GPS data**. The archive and fresh database are generated local files ignored by Git.

## Boundaries of verification

- **ESP32/NEO-6M hardware is unavailable. No physical hardware integration has been tested.**
- The provided firmware has **not** been compiled using an ESP32 Arduino toolchain in this environment.
- Successful OSRM route distance, duration, geometry parsing and caching are covered with deterministic mocked responses. The live demonstration exercised fallback; a successful live public OSRM road-route response was not established. External routing availability is optional, and its failure does not block tracking.
- The Hyderabad sample route is artificial demo data, not recorded GPS or a surveyed road trace. No real road journey or real-world GPS accuracy has been measured.

The development environment restricted temporary directories and loopback sockets; tests and the local HTTP demonstration were run with approved access outside that sandbox. This is an execution-environment requirement, not an additional application dependency.
