# FleetMitra — final college demonstration

Software status: **READY FOR DEMO** for the verified local simulation workflow. Physical ESP32/GPS integration remains untested.

## Launch

Open Windows PowerShell:

```powershell
Set-Location 'D:\College Projects\CBP IOT\Fleet Mitra'
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe app.py
```

Open [FleetMitra](http://127.0.0.1:5000). Use one Flask process per database. No Node build or separate GPS sender is needed for dashboard simulation. For a new installation, create the environment with `python -m venv venv` first. Stop Flask with Ctrl+C.

Launch the isolated final feature review on [port 5004](http://127.0.0.1:5004), with a clearly labelled sample driver and real saved simulation records:

```powershell
$env:FLEET_DATABASE='instance/final-features-qa.sqlite3'
$env:FLEET_PORT='5004'
.\venv\Scripts\python.exe app.py
```

The default instance/fleet_mitra.sqlite3 and review instance/final-features-qa.sqlite3 are independent datasets, not different software versions. At audit start, the default had zero drivers and one trip; the review had one sample driver and three trips. Register a driver in the default database or explicitly launch the review configuration to see its records. No records are automatically copied between databases.

Use a new PowerShell session for the default database/port. Existing operator databases were retained. Do not delete `instance/*.sqlite3` or `instance/driver-profiles.key` when resetting a simulation.

## Demonstrate the complete workflow

1. Open **Drivers → Add Driver**. Only Full Name is required. For a review, choose **Use Fictional Sample Name**; the profile is visibly labelled SAMPLE. Optional fields remain optional. Date of birth calculates age; license number requires an expiry date.
2. Save, then **Assign Vehicle → FM01**. The driver becomes eligible when active, available, assigned to FM01 and without an expired supplied license. Search/filter, edit, view details, activate/deactivate and unassign controls work on this page. Vehicle reassignment is blocked during an active trip.
3. Return to Live Tracking. Choose the driver in **Select Driver**; type into its search box to narrow available profiles. Name, ID, vehicle and availability are shown. With no driver, the dashboard directs you to Add / Manage Drivers and does not start a trip.
4. Choose start and destination by search, map or exact coordinates. **Home** is exactly **17.415666, 78.573060** and can be either endpoint. It is never forced as the origin.
5. Compare genuine road alternatives. Traffic is explicitly **SIMULATED**. Route availability varies; FleetMitra does not invent extra road routes. Click **Use This Route**.
6. Set speed **40 km/h** and acceleration **1×** initially. Start Trip. The trip stores its driver name snapshot, original endpoints/geometry and timestamps. Collapse the planner to enlarge the map. Expand **Driver Information** when needed.
7. Enable **Follow vehicle**. The map moves to street-level zoom 17; the vehicle arrow rotates and remains below center. The selected route is blue, travelled geometry grey. Pan/zoom to suspend follow; enable it again to resume. Fit Entire Route is a separate camera action.
8. While moving, click **Change Destination**. Search another place, select on the map, or choose **Use Home**. The proposed marker does not replace the active destination. Cancel leaves the route/trip unchanged.
9. Click **Confirm Destination** to calculate routes from the current vehicle fix. The existing journey continues during this network request. Review adjusted ETA, distance and simulated traffic; the recommendation is selected automatically, but any offered alternative can be chosen.
10. Click **Apply Selected Route**. FleetMitra checks the latest GPS point and navigation revision. If the vehicle has moved away from the proposal geometry, fresh choices are requested and you must review/apply again. No stale route is forced. An already-valid route is projected onto the latest position. The popup **Destination Updated** appears only after activation.
11. The trip ID, driver, start time, travelled distance, logical duration, physical speed and acceleration are retained. New remaining distance, planned total and ETA update. Follow stays enabled if it was enabled. **Fit New Route** explicitly frames the new geometry.
12. Expand **Advanced & review tools → Test Route Deviation** early enough to demonstrate monitoring. A sustained deviation raises a warning, pauses for rerouting and activates a validated replacement. The test first seeks a genuine alternative road prefix; if unavailable, its event explicitly labels a synthetic test offset. Failure keeps the active destination and pauses for retry.
13. For a faster finish, explicitly choose **8× → Apply speed / clock** after the destination-change demonstration. Wait for the action to finish before pressing another control. Physical speed stays 40 km/h. Let the vehicle reach the updated destination.
14. Open **Trip History**, filter by driver, and select the trip. Inspect original/final destinations, driver snapshot, distance/duration, chronological destination/deviation/reroute events and saved paths. Purple = original route; teal = destination replacement; amber = deviation reroute; blue = actual recorded path.
15. Export CSV or JSON. CSV includes typed trip/location/event/route-version rows with nested JSON details. Driver ID/name snapshots are included; private driver profile fields are excluded.
16. Edit the driver's name. The old trip still shows the original name snapshot. Driver analytics come from actual persisted journeys. A finished/stopped trip releases its driver; manual deactivation remains in effect.
17. Stop and restart Flask using the same database. Driver records and trips remain. If interrupted while RUNNING, a simulation returns PAUSED and its driver remains On Trip; Resume is explicit and downtime movement is not invented.

You can also change destinations while paused, make several changes in one trip, or Stop early. Selecting the same destination is a no-op. Destinations under 10 m from the vehicle are rejected with a useful message. Refreshing discards only unconfirmed browser draft controls; committed navigation remains on the server.

## Implementation choices for the viva

- **Same architecture:** Flask endpoints, SQLite transactions, vanilla JavaScript and Leaflet remain. There is no new frontend framework.
- **Safe destination change:** Planning creates a bounded-lived proposal tied to a trip/navigation revision. Activation is an atomic transaction under the existing simulation lock. Provider calls during planning do not lock movement. Latest-position projection avoids restarting at the old origin. Competing proposals cannot overwrite a newer navigation change; repeated application is idempotent.
- **Continuous totals:** Physical distance and logical time remain accumulated. A new route offset/planned total changes navigation progress while retaining the original start and immutable route snapshots.
- **Safe driver status:** Available/On Trip/Inactive derives from persisted active trips and the active-profile flag. Unique indexes and transactions prevent conflicting vehicle/active-trip assignments. No independent status flag can drift after restart.
- **Historical identity:** A trip stores only driver ID, name and sample flag. Profile edits do not rewrite previous journeys. Old pre-driver records remain Unassigned.
- **Measured statistics:** Total/completed trips, distance, duration, aggregate distance/time speed, maximum accepted sample speed and deviation counts are calculated from saved trips and events. Finished trips supply average trip duration; active samples contribute to cumulative distance/speed.
- **Privacy:** DOB, gender, phone, email, address and license number are encrypted with authenticated Fernet encryption. Bulk responses mask phone/license; personal details are requested separately, and the profile response is not cached. Age is calculated rather than stored. [Fernet documentation](https://cryptography.io/en/latest/fernet/) explains the library used.

## Configuration and data safety

- SQLite defaults to `instance/fleet_mitra.sqlite3`; override `FLEET_DATABASE` if needed. Migrations are additive. Back up the database plus its WAL safely while running, or stop the app before copying the SQLite file.
- Private driver encryption uses `FLEET_DRIVER_KEY` if configured, otherwise a generated `driver-profiles.key` alongside the database. Keep the original key backed up separately; losing it prevents profile decryption. No key is printed or put in frontend code. The local key file inherits Windows folder access rules; protect the instance folder. These local operator pages do not add production authentication; keep the default `127.0.0.1` binding.
- `FLEET_ROUTING_URL` defaults to the public OSRM driving service; `FLEET_ROUTE_PLANNING_TIMEOUT` defaults to 6 seconds. External route failures leave the old trip/destination intact. Automatic deviation rerouting preserves its existing safe-pause behavior.
- Destination proposals constrain origin snapping to 10 m and use OSRM's supported `snapping=any`, allowing a current fix on road edges excluded as default starting points. This prevents a nearby-road snap from causing a jump. Latest-position projection still validates activation. [OSRM options](https://project-osrm.org/docs/v5.24.0/api/#general-options) document these settings. If the provider cannot route from that segment, the trip remains unchanged; no fake connector is invented.
- Photon search uses `FLEET_GEOCODING_URL` (default `https://photon.komoot.io/api/`) and `FLEET_GEOCODING_ENABLED`. Public-service fair-use limits apply. Manual map input/Home work independently.
- Standard Map uses OpenStreetMap. Localhost-only Navigation Map uses Stadia Alidade Smooth development access with attribution/high-DPI tile support and Standard fallback. No satellite option or unrestricted free-hosting claim is made. See [provider details](docs/REVIEW_GUIDE.md).
- Dashboard trips require a selected driver. For compatibility, old API/GPS clients can omit drivers only while the registry is empty; after registration, new API trips require an eligible driver. Pre-upgrade trips remain valid and Unassigned.

## Verification and limits

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

**200 passed, 0 failed**, including the original verified 161 cases and 39 new driver/destination cases. JavaScript syntax and Python compilation also passed.

The actual browser workflow registered/assigned a sample driver, searched endpoints, started Trip #1, enabled Follow, cancelled one draft, changed destination with live alternatives, received success, triggered deviation, accepted automatic rerouting and reached the new destination. History persisted **7.15 km**, **644 logical seconds**, **936 GPS samples**, one destination change and one deviation/reroute. Editing the profile retained the old name in history. Driver status/assignment controls and mobile history/driver layouts were inspected. Server-restart row digests matched for driver, trip, position, event, route-version and proposal tables.

A second real browser trip verified the expanded live Driver Information panel, same-destination no-op, manual map selection, two changes while PAUSED (manual destination → exact Home), Follow remaining off, and STOPPED persistence under the same trip/driver. A 40 m provider-snap issue was found, safely rejected, fixed with the documented exact-segment options and successfully retested. Pausing does not accumulate logical movement time.

Routing, geocoding and map tiles still depend on provider/network availability; public services are not production SLAs. Three road alternatives are not guaranteed. Physical ESP32/GPS, physical high-DPI/touch screens and speaker audibility remain untested. Some edge cases use deterministic provider mocks in tests rather than live services. Historical paths are persisted observations, not regenerated routes. The folder is now a Git repository on main. The complete implementation was already committed as f59f113. See FLEETMITRA_AUDIT_REPORT.md for the fresh verification and local audit commit; this audit does not push to GitHub.


