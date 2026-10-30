from flask import Blueprint, jsonify

from database import get_db
from services.tracking_service import ingest_location, location_dict, vehicle_snapshot
from validation import json_body, vehicle_exists, history_limit

bp = Blueprint("locations", __name__)


@bp.post("/api/locations")
def add_location():
    result = ingest_location(json_body())
    return jsonify(result), 200 if result["duplicate"] else 201


@bp.get("/api/vehicles")
def vehicles():
    return jsonify(vehicles=[dict(r) for r in get_db().execute("SELECT * FROM vehicles")])


@bp.get("/api/vehicles/<vehicle_id>/location")
def location(vehicle_id):
    return jsonify(vehicle_snapshot(vehicle_id))


@bp.get("/api/vehicles/<vehicle_id>/history")
def history(vehicle_id):
    db = get_db()
    vehicle_exists(db, vehicle_id)
    rows = db.execute("SELECT * FROM locations WHERE vehicle_id = ? ORDER BY timestamp DESC LIMIT ?",
                      (vehicle_id, history_limit())).fetchall()
    return jsonify(locations=[location_dict(row) for row in rows])
