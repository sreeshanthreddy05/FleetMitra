from flask import Blueprint, jsonify, request

from database import get_db
from geofence import fence_status, statuses
from services.tracking_service import latest_location
from validation import APIError, coordinates, history_limit, json_body, number, text_field, vehicle_exists

bp = Blueprint("geofences", __name__)


@bp.post("/api/geofences")
def create():
    data = json_body()
    db = get_db()
    vehicle_id = vehicle_exists(db, data.get("vehicle_id", "FM01"))
    lat, lon = coordinates(data, "center_lat", "center_lon")
    radius = number(data.get("radius_m"), "radius_m", 1, 100_000)
    name = text_field(data.get("name"), "name")
    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise APIError("enabled must be true or false")
    with db:
        db.execute("BEGIN IMMEDIATE")
        cursor = db.execute("INSERT INTO geofences (name, center_lat, center_lon, radius_m, enabled, vehicle_id) "
                            "VALUES (?, ?, ?, ?, ?, ?)", (name, lat, lon, radius, int(enabled), vehicle_id))
        fence_id = cursor.lastrowid
        fence = db.execute("SELECT * FROM geofences WHERE geofence_id = ?", (fence_id,)).fetchone()
        location = latest_location(db, vehicle_id)
        # Creating a boundary around a known position initializes state without an event.
        if location and enabled:
            status, _ = fence_status(fence, location["lat"], location["lon"])
            db.execute("INSERT INTO geofence_states VALUES (?, ?, ?)", (fence_id, vehicle_id, status))
    result = dict(fence)
    result["enabled"] = bool(result["enabled"])
    return jsonify(geofence=result), 201


@bp.get("/api/geofences")
@bp.get("/api/geofences/status")
def status():
    db = get_db()
    vehicle_id = vehicle_exists(db, request.args.get("vehicle_id", "FM01"))
    return jsonify(geofences=statuses(db, vehicle_id, latest_location(db, vehicle_id)))


@bp.get("/api/geofences/events")
def events():
    db = get_db()
    vehicle_id = vehicle_exists(db, request.args.get("vehicle_id", "FM01"))
    rows = db.execute("SELECT e.*, g.name FROM geofence_events e JOIN geofences g USING(geofence_id) "
                      "WHERE e.vehicle_id = ? ORDER BY event_id DESC LIMIT ?",
                      (vehicle_id, history_limit())).fetchall()
    return jsonify(events=[dict(row) for row in rows])


@bp.delete("/api/geofences/<int:fence_id>")
def delete(fence_id):
    db = get_db()
    with db:
        cursor = db.execute("DELETE FROM geofences WHERE geofence_id = ?", (fence_id,))
        if cursor.rowcount == 0:
            raise APIError("Geofence not found", 404)
    return jsonify(deleted=True, geofence_id=fence_id)
