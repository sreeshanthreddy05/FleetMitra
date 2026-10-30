from flask import Blueprint, jsonify, request, current_app

from database import get_db
from services.tracking_service import active_trip, latest_location, trip_dict, vehicle_snapshot
from validation import APIError, coordinates, history_limit, json_body, text_field, utc_now, vehicle_exists
from services.event_service import record_event, events
from services.route_planner import route_by_id
from services.trip_archive import initialize_trip

bp = Blueprint("trips", __name__)


@bp.post("/api/trips/start")
def start():
    data = json_body()
    db = get_db()
    vehicle_id = vehicle_exists(db, data.get("vehicle_id"))
    lat, lon = coordinates(data, "destination_lat", "destination_lon")
    label = text_field(data.get("destination_label"), "destination_label", "Destination")
    with db:
        db.execute("BEGIN IMMEDIATE")
        if active_trip(db, vehicle_id):
            raise APIError("A trip is already active for this vehicle", 409)
        latest = latest_location(db, vehicle_id)
        if latest is None:
            raise APIError("Waiting for GPS data; send a location before starting a trip", 409)
        db.execute(
            """INSERT INTO trips (vehicle_id, start_time, start_lat, start_lon,
            destination_lat, destination_lon, destination_label, status,
            distance_anchor_lat, distance_anchor_lon) VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)""",
            (vehicle_id, utc_now(), latest["lat"], latest["lon"], lat, lon, label,
             latest["lat"], latest["lon"]),
        )
        trip = active_trip(db, vehicle_id)
        from services.driver_service import assign_trip_driver
        assign_trip_driver(db,trip['trip_id'],data.get('driver_id'),vehicle_id)
        route_id = data.get("route_id")
        if route_id is not None:
            route = route_by_id(db, route_id)
            db.execute("UPDATE trips SET route_id = ?, route_total_m = ?, route_status = 'ON_ROUTE' WHERE trip_id = ?",
                       (route_id, route["distance_m"], trip["trip_id"]))
        db.execute("UPDATE trips SET data_source = ? WHERE trip_id = ?", (latest["source"], trip["trip_id"]))
        initialize_trip(db,trip['trip_id'],route_id,text_field(data.get('start_label'),'start_label',f"{latest['lat']:.6f}, {latest['lon']:.6f}"))
        record_event(db, vehicle_id, trip["trip_id"], "TRIP_STARTED", "Trip started", f"Trip to {label} started.")
    return jsonify(trip=vehicle_snapshot(vehicle_id)["trip"]), 201


@bp.post("/api/trips/stop")
def stop():
    db = get_db()
    data = json_body()
    vehicle_id = vehicle_exists(db, data.get("vehicle_id"))
    with current_app.extensions['simulation'].lock, db:
        db.execute("BEGIN IMMEDIATE")
        trip = active_trip(db, vehicle_id)
        if not trip:
            raise APIError("No active trip to stop", 409)
        if data.get('trip_id') is not None and data['trip_id'] != trip['trip_id']:
            raise APIError('Active trip changed. Refresh before ending it.', 409)
        db.execute("UPDATE trips SET status = 'COMPLETED', end_time = ? WHERE trip_id = ?",
                   (utc_now(), trip["trip_id"]))
        db.execute("UPDATE simulation_sessions SET state = 'STOPPED' WHERE trip_id = ?", (trip["trip_id"],))
        db.execute("UPDATE trips SET end_reason = 'OPERATOR_STOP' WHERE trip_id = ?", (trip['trip_id'],))
        record_event(db, vehicle_id, trip["trip_id"], "TRIP_STOPPED", "Trip stopped", "The operator stopped the trip.")
        result = trip_dict(db.execute("SELECT * FROM trips WHERE trip_id = ?", (trip["trip_id"],)).fetchone())
    return jsonify(trip=result)


@bp.get("/api/trips/current")
def current():
    return jsonify(trip=vehicle_snapshot(request.args.get("vehicle_id", "FM01"))["trip"])


@bp.get("/api/trips/history")
def history():
    db = get_db()
    vehicle_id = vehicle_exists(db, request.args.get("vehicle_id", "FM01"))
    rows = db.execute("SELECT * FROM trips WHERE vehicle_id = ? AND status = 'COMPLETED' "
                      "ORDER BY trip_id DESC LIMIT ?", (vehicle_id, history_limit())).fetchall()
    return jsonify(trips=[trip_dict(row) for row in rows])


def summary(db, trip_id):
    row = db.execute("SELECT * FROM trips WHERE trip_id = ?", (trip_id,)).fetchone()
    if row is None:
        raise APIError("Trip not found", 404)
    trip = trip_dict(row)
    trip['lifecycle_status']='ACTIVE' if row['status']=='ACTIVE' else 'STOPPED' if row['end_reason'] in ('RESET','OPERATOR_STOP') else 'COMPLETED'
    import json
    trip['initial_traffic']=json.loads(trip['initial_traffic_json']) if trip['initial_traffic_json'] else None
    trip['original_destination']=json.loads(trip['original_destination_json']) if trip.get('original_destination_json') else None
    from datetime import datetime
    duration = trip["elapsed_seconds"]
    if not duration and trip.get('initial_multiplier') is None:
        duration = max(0, (datetime.fromisoformat(trip["end_time"] or utc_now()) -
                           datetime.fromisoformat(trip["start_time"])).total_seconds())
    speeds = db.execute("SELECT MAX(speed_kmh) FROM locations WHERE trip_id = ?", (trip_id,)).fetchone()
    counts = dict(db.execute("SELECT kind, COUNT(*) FROM trip_events WHERE trip_id = ? GROUP BY kind", (trip_id,)))
    trip.update(duration_seconds=duration, average_speed_kmh=trip["distance_m"] / duration * 3.6 if duration else 0,
                maximum_speed_kmh=speeds[0] or 0,
                geofence_event_count=counts.get("GEOFENCE_ENTER", 0) + counts.get("GEOFENCE_EXIT", 0),
                deviation_count=counts.get("ROUTE_DEVIATION", 0), reroute_count=counts.get("REROUTE_ACCEPTED", 0))
    trip['destination_change_count']=counts.get('DESTINATION_CHANGED',0)
    return trip


@bp.get("/api/trips/<int:trip_id>")
def detail(trip_id):
    db = get_db()
    trip = summary(db, trip_id)
    path = db.execute("SELECT lat, lon, timestamp, received_at, speed_kmh, source FROM locations WHERE trip_id = ? "
                      "ORDER BY timestamp", (trip_id,)).fetchall()
    route = route_by_id(db, trip["route_id"]) if trip["route_id"] else None
    import json
    versions=[{**dict(row),'route':json.loads(row['route_json'])} for row in db.execute(
        'SELECT * FROM trip_route_versions WHERE trip_id = ? ORDER BY version_id',(trip_id,))]
    return jsonify(trip=trip, locations=[dict(row) for row in path], route=route,route_versions=versions,
                   events=events(db, trip["vehicle_id"], trip_id, 1000000))
