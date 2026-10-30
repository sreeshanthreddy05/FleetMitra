"""Route monitoring and once-per-transition notifications for every telemetry source."""
from datetime import datetime, timezone
import json

from flask import current_app

from calculations import haversine
from services.event_service import record_event
from services.route_geometry import prepare, project
from validation import utc_now


def monitor_route(db, location, trip):
    if not trip or not trip["route_id"]:
        return
    route = db.execute("SELECT * FROM route_plans WHERE route_id = ?", (trip["route_id"],)).fetchone()
    nearest = project(route["geometry_json"], location["lat"], location["lon"])
    off_route = nearest["distance_m"] > current_app.config["DEVIATION_THRESHOLD_M"]
    count = trip["off_route_count"] + 1 if off_route else 0
    state = trip["route_status"]
    if count >= current_app.config["DEVIATION_CONFIRM_COUNT"] and state != "DEVIATED":
        state = "DEVIATED"
        record_event(db, location["vehicle_id"], trip["trip_id"], "ROUTE_DEVIATION",
                     "Route deviation detected", "FM01 has moved outside the planned route corridor.",
                     "CRITICAL", True, details={"distance_from_route_m": round(nearest["distance_m"], 1)})
    elif not off_route:
        if state == "DEVIATED":
            record_event(db, location["vehicle_id"], trip["trip_id"], "ROUTE_RECOVERED",
                         "Route recovered", "FM01 returned to the planned route.", "SUCCESS", True)
        state = "ON_ROUTE"
    progress = trip["route_progress_m"]
    if not off_route:
        progress = max(progress, trip["route_offset_m"] + nearest["along_m"])
    radius = current_app.config["ARRIVAL_RADIUS_M"]
    arrived = (not off_route and prepare(route["geometry_json"])[1][-1] - nearest["along_m"] <= radius
               and haversine(location["lat"], location["lon"], trip["destination_lat"], trip["destination_lon"]) <= radius)
    db.execute("UPDATE trips SET route_status = ?, off_route_count = ?, route_progress_m = ? WHERE trip_id = ?",
               (state, count, min(trip["route_total_m"], progress), trip["trip_id"]))
    if arrived:
        db.execute("UPDATE trips SET status = 'COMPLETED', completion_status = 'ARRIVED', "
                   "route_status = 'ARRIVED', end_reason = 'DESTINATION_REACHED', route_progress_m = route_total_m, end_time = ? WHERE trip_id = ?",
                   (utc_now(), trip["trip_id"]))
        db.execute("UPDATE simulation_sessions SET state = 'ARRIVED', updated_at = ? WHERE trip_id = ?",
                   (utc_now(), trip["trip_id"]))
        record_event(db, location["vehicle_id"], trip["trip_id"], "DESTINATION_REACHED",
                     "Destination reached", "FM01 has reached the selected destination.", "SUCCESS", True,
                     dedupe_key=f"arrival:{trip['trip_id']}")


def monitor_freshness(db, vehicle_id, location):
    if not location:
        return False
    session = db.execute("SELECT * FROM simulation_sessions WHERE vehicle_id = ? ORDER BY session_id DESC LIMIT 1",
                         (vehicle_id,)).fetchone()
    threshold = current_app.config["STALE_AFTER_SECONDS"]
    if session and session["scenario"] == "connectivity" and session["state"] == "RUNNING":
        threshold = current_app.config["DEMO_STALE_SECONDS"]
    stamp = datetime.fromisoformat(location["timestamp"])
    stale = (datetime.now(timezone.utc) - stamp).total_seconds() > threshold
    # Intentional pause and completed simulations are not connection failures.
    expected = not session or session["state"] == "RUNNING" or location["source"] == "HARDWARE"
    desired = "STALE" if stale and expected else "FRESH"
    with db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT freshness_state FROM vehicles WHERE vehicle_id = ?", (vehicle_id,)).fetchone()[0]
        if desired != previous:
            if desired == "STALE":
                record_event(db, vehicle_id, location["trip_id"], "TELEMETRY_LOST", "Telemetry interrupted",
                             "Telemetry from FM01 has become stale.", "WARNING", True)
            elif previous == "STALE":
                record_event(db, vehicle_id, location["trip_id"], "TELEMETRY_RESTORED", "Telemetry restored",
                             "Telemetry from FM01 has resumed.", "SUCCESS", True)
            db.execute("UPDATE vehicles SET freshness_state = ? WHERE vehicle_id = ?", (desired, vehicle_id))
    return stale


def planned_eta(db, trip, location, stale):
    route = dict(db.execute("SELECT * FROM route_plans WHERE route_id = ?", (trip["route_id"],)).fetchone())
    remaining = max(0, trip["route_total_m"] - trip["route_progress_m"])
    speed = location["speed_kmh"] if location else 0
    session = db.execute("SELECT * FROM simulation_sessions WHERE trip_id = ?", (trip["trip_id"],)).fetchone()
    if session:
        speed = session["speed_kmh"]
    status = "EN_ROUTE"
    if stale and (not session or session["state"] == "RUNNING"):
        status = "WAITING_FOR_GPS"
    elif speed < current_app.config["MIN_ETA_SPEED_KMH"] or (session and session["state"] == "PAUSED"):
        status = "WAITING_FOR_MOVEMENT"
    if trip.get("completion_status") == "ARRIVED":
        status, remaining = "ARRIVED", 0
    seconds = remaining / (speed / 3.6) if status == "EN_ROUTE" else 0 if status == "ARRIVED" else None
    from datetime import timedelta
    eta = {"method": route["method"], "status": status, "remaining_distance_m": remaining,
           "duration_seconds": seconds, "arrival_time": (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
           if seconds is not None else None, "geometry": json.loads(route["geometry_json"]),
           "speed_kmh": speed, "distance_basis": "SELECTED_ROUTE_GEOMETRY"}
    return eta
