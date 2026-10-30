"""Review operations built on the existing tracking, trip and geofence services."""
import json

from flask import Blueprint, current_app, jsonify, request

from calculations import haversine
from database import get_db
from routes.trip_routes import summary
from services.event_service import events, notifications, record_event
from services.monitoring_service import planned_eta
from services.route_geometry import project
from services.route_planner import demo_routes, demo_reconnect, plan_routes, route_by_id
from services.simulation_service import SCENARIOS
from services.tracking_service import active_trip, latest_location, location_dict, vehicle_snapshot
from services.traffic_service import simulated_traffic
import secrets
from validation import APIError, coordinates, history_limit, json_body, utc_now, vehicle_exists

bp = Blueprint("operations", __name__)


def engine():
    return current_app.extensions["simulation"]


@bp.get("/api/config")
def config():
    settings = current_app.config
    mode = get_db().execute("SELECT input_mode FROM vehicles WHERE vehicle_id = ?", (settings["DEFAULT_VEHICLE_ID"],)).fetchone()[0]
    return jsonify(vehicle_id=settings["DEFAULT_VEHICLE_ID"], mode=mode, default_speed_kmh=settings["DEFAULT_SPEED_KMH"],
                   multipliers=settings["SIMULATION_MULTIPLIERS"], map_center=settings["DEFAULT_MAP_CENTER"],
                   arrival_radius_m=settings["ARRIVAL_RADIUS_M"], deviation_threshold_m=settings["DEVIATION_THRESHOLD_M"],
                   stale_after_seconds=settings["STALE_AFTER_SECONDS"], scenarios=SCENARIOS,
                   saved_places=settings["SAVED_PLACES"])


@bp.post("/api/mode")
def mode():
    selected = json_body().get("mode")
    if selected not in ("SIMULATED", "HARDWARE"):
        raise APIError("mode must be SIMULATED or HARDWARE")
    if engine().status()["state"] in ("RUNNING", "PAUSED"):
        raise APIError("Stop the active simulation before changing mode", 409)
    with get_db():
        get_db().execute("UPDATE vehicles SET input_mode = ? WHERE vehicle_id = ?",
                         (selected, current_app.config["DEFAULT_VEHICLE_ID"]))
    return jsonify(mode=selected)


@bp.get("/api/demo-routes")
def demos():
    return jsonify(routes=demo_routes(), scenarios=SCENARIOS)


@bp.post("/api/routes")
def plan():
    data = json_body()
    if data.get("demo_id") is not None:
        return jsonify(plan_routes(None, None, data["demo_id"])), 201
    start = coordinates(data, "start_lat", "start_lon")
    destination = coordinates(data, "destination_lat", "destination_lon")
    if haversine(*start, *destination) < 10:
        raise APIError("Choose points at least 10 meters apart")
    allow_fallback = data.get("allow_fallback", False)
    if not isinstance(allow_fallback, bool):
        raise APIError("allow_fallback must be true or false")
    return jsonify(plan_routes(start, destination, allow_fallback=allow_fallback)), 201


@bp.get("/api/simulation/status")
def simulation_status():
    return jsonify(simulation=engine().status())


@bp.post("/api/routes/traffic")
def refresh_traffic():
    ids = json_body().get("route_ids")
    if not isinstance(ids, list) or not 1 <= len(ids) <= 4:
        raise APIError("route_ids must contain 1–4 routes")
    db = get_db()
    routes = [route_by_id(db, route_id) for route_id in ids]
    seed = secrets.token_hex(8)
    with db:
        for route in routes:
            db.execute("UPDATE route_plans SET traffic_json = ? WHERE route_id = ?",
                       (json.dumps(simulated_traffic(route["geometry"], route["duration_seconds"], seed)), route["route_id"]))
    routes = [route_by_id(db, route_id) for route_id in ids]
    return jsonify(routes=routes, recommended_route_id=min(routes,key=lambda r:r["traffic"]["adjusted_duration_seconds"])["route_id"])


@bp.post("/api/simulation/start")
def simulation_start():
    return jsonify(simulation=engine().start(json_body())), 201


@bp.post("/api/simulation/<action>")
def simulation_control(action):
    if action not in ("pause", "resume", "stop", "reset"):
        raise APIError("Simulation action not found", 404)
    return jsonify(simulation=engine().control(action))


@bp.patch("/api/simulation/speed")
def simulation_speed():
    return jsonify(simulation=engine().change_speed(json_body()))


@bp.post("/api/simulation/scenario")
def simulation_scenario():
    return jsonify(simulation=engine().trigger(json_body().get("action")))


@bp.get("/api/events")
def event_history():
    db = get_db()
    vehicle_id = vehicle_exists(db, request.args.get("vehicle_id", "FM01"))
    trip_id = request.args.get("trip_id")
    if trip_id is not None:
        try:
            trip_id = int(trip_id)
        except ValueError:
            raise APIError("trip_id must be an integer") from None
    return jsonify(events=events(db, vehicle_id, trip_id, history_limit()))


@bp.get("/api/notifications")
def notification_history():
    db = get_db()
    vehicle_id = vehicle_exists(db, request.args.get("vehicle_id", "FM01"))
    return jsonify(notifications(db, vehicle_id, history_limit()))


@bp.patch("/api/notifications/<int:notification_id>/read")
def read_notification(notification_id):
    db = get_db()
    with db:
        changed = db.execute("UPDATE notifications SET is_read = 1 WHERE notification_id = ?", (notification_id,)).rowcount
        if not changed:
            raise APIError("Notification not found", 404)
    return jsonify(read=True)


@bp.post("/api/notifications/read-all")
def read_all():
    with get_db():
        get_db().execute("UPDATE notifications SET is_read = 1 WHERE vehicle_id = ?", (current_app.config["DEFAULT_VEHICLE_ID"],))
    return jsonify(read=True)


@bp.post("/api/routes/reroute")
def reroute():
    data = json_body()
    db = get_db()
    trip = active_trip(db, current_app.config["DEFAULT_VEHICLE_ID"])
    latest = latest_location(db, current_app.config["DEFAULT_VEHICLE_ID"])
    if not trip or not trip["route_id"] or not latest:
        raise APIError("No active planned trip to reroute", 409)
    if engine().status()["state"] == "RUNNING":
        engine().control("pause")
        latest = latest_location(db, trip["vehicle_id"])
    if data.get("demo_fallback") is True:
        route = demo_reconnect(db, trip, latest)
        return jsonify(routes=[route], message="DEMO ROUTE: off-road connector back to the original path. Simulation paused for review.")
    return jsonify(plan_routes((latest["lat"], latest["lon"]), (trip["destination_lat"], trip["destination_lon"])))


@bp.post("/api/routes/accept")
def accept_reroute():
    data = json_body()
    with engine().lock:
        db = get_db()
        route = route_by_id(db, data.get("route_id"))
        trip = active_trip(db, current_app.config["DEFAULT_VEHICLE_ID"])
        latest = latest_location(db, current_app.config["DEFAULT_VEHICLE_ID"])
        if not trip or not latest:
            raise APIError("No active trip", 409)
        if haversine(latest["lat"], latest["lon"], route["start"]["lat"], route["start"]["lon"]) > 100:
            raise APIError("Reroute origin is too far from the current vehicle. Recalculate while paused.", 409)
        if haversine(trip["destination_lat"], trip["destination_lon"], route["destination"]["lat"], route["destination"]["lon"]) > 150:
            raise APIError("Reroute must keep the original destination")
        with db:
            db.execute("UPDATE trips SET navigation_revision=navigation_revision+1, route_id = ?, route_offset_m = route_progress_m, "
                       "route_total_m = route_progress_m + ?, route_status = 'ON_ROUTE', off_route_count = 0 WHERE trip_id = ?",
                       (route["route_id"], route["distance_m"], trip["trip_id"]))
            session = engine().session()
            flags = json.loads(session["flags_json"]) if session else {}
            flags.update(deviation_scripted=True, speed_scripted=True, outage_scripted=True,
                         deviation_hold=False, offset_m=0, auto_attempted=False)
            for key in ("test_geometry", "test_position_m", "test_limit_m"):
                flags.pop(key, None)
            db.execute("UPDATE simulation_sessions SET route_id = ?, position_m = 0, flags_json = ? WHERE trip_id = ?",
                       (route["route_id"], json.dumps(flags), trip["trip_id"]))
            record_event(db, trip["vehicle_id"], trip["trip_id"], "REROUTE_ACCEPTED", "New route accepted",
                         f"Replaced route with {route['method']} ({route['distance_m'] / 1000:.2f} km remaining).", "INFO", True)
            from services.trip_archive import archive_route
            archive_route(db,trip['trip_id'],route['route_id'],'REROUTE_ACCEPTED')
        return jsonify(route=route, simulation=engine().status())


@bp.get("/api/dashboard")
def dashboard_data():
    db = get_db()
    vehicle_id = current_app.config["DEFAULT_VEHICLE_ID"]
    snapshot = vehicle_snapshot(vehicle_id)
    rows = db.execute("SELECT * FROM locations WHERE vehicle_id = ? ORDER BY timestamp DESC LIMIT 160", (vehicle_id,)).fetchall()
    trips = db.execute("SELECT trip_id FROM trips WHERE vehicle_id = ? AND status = 'COMPLETED' ORDER BY trip_id DESC LIMIT 12",
                       (vehicle_id,)).fetchall()
    active = snapshot["trip"]
    last = summary(db, trips[0]["trip_id"]) if trips else None
    display = active or last
    route = route_by_id(db, display["route_id"]) if display and display["route_id"] else None
    initial_route=route_by_id(db,active['initial_route_id']) if active and active.get('initial_route_id') else None
    return jsonify(vehicle=snapshot, simulation=engine().status(), route=route, initial_route=initial_route,last_trip=last,
                   locations=[location_dict(row) for row in rows], events=events(db, vehicle_id),
                   trips=[summary(db, row["trip_id"]) for row in trips], **notifications(db, vehicle_id))
