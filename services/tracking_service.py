"""Single ingestion path for simulator, hardware, and API tests."""
from datetime import datetime, timezone

from flask import current_app

from calculations import haversine, derived_speed, estimate_eta
from database import get_db
from geofence import update_geofences, statuses
from services.monitoring_service import monitor_route, monitor_freshness, planned_eta
from validation import APIError, coordinates, number, parse_timestamp, utc_now, vehicle_exists


def latest_location(db, vehicle_id):
    return db.execute("SELECT * FROM locations WHERE vehicle_id = ? ORDER BY timestamp DESC LIMIT 1",
                      (vehicle_id,)).fetchone()


def active_trip(db, vehicle_id):
    return db.execute("SELECT * FROM trips WHERE vehicle_id = ? AND status = 'ACTIVE'",
                      (vehicle_id,)).fetchone()


def location_dict(row):
    if row is None:
        return None
    result = dict(row)
    result["gps_valid"] = bool(result["gps_valid"])
    return result


def trip_dict(row):
    if row is None:
        return None
    result = dict(row)
    result.pop("distance_anchor_lat", None)
    result.pop("distance_anchor_lon", None)
    result["distance_km"] = result["distance_m"] / 1000
    if result.get("completion_status"):
        result["status"] = result["completion_status"]
    total = result.get("route_total_m", 0)
    result["progress_percent"] = min(100, max(0, result.get("route_progress_m", 0) / total * 100)) if total else 0
    return result


def vehicle_snapshot(vehicle_id):
    db = get_db()
    vehicle_exists(db, vehicle_id)
    latest = latest_location(db, vehicle_id)
    trip = trip_dict(active_trip(db, vehicle_id))
    now = datetime.now(timezone.utc)
    stale = monitor_freshness(db, vehicle_id, latest)
    eta = None
    if trip and latest and trip.get("route_id"):
        eta = planned_eta(db, trip, latest, stale)
        trip["eta"] = eta
        trip["remaining_distance_m"] = eta["remaining_distance_m"]
    elif trip and latest:
        distance = haversine(latest["lat"], latest["lon"], trip["destination_lat"], trip["destination_lon"])
        samples = db.execute(
            "SELECT speed_kmh FROM locations WHERE vehicle_id = ? AND trip_id = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (vehicle_id, trip["trip_id"], current_app.config["SPEED_WINDOW"]),
        ).fetchall()
        speeds = [row["speed_kmh"] for row in samples] or [latest["speed_kmh"]]
        route = None
        if distance > current_app.config["ARRIVAL_RADIUS_M"]:
            route = current_app.extensions["routing"].route(
                latest["lat"], latest["lon"], trip["destination_lat"], trip["destination_lon"])
        eta = estimate_eta(distance, speeds, route,
                           current_app.config["ARRIVAL_RADIUS_M"],
                           current_app.config["MIN_ETA_SPEED_KMH"], stale, now)
        trip["eta"] = eta
        trip["remaining_distance_m"] = eta["remaining_distance_m"]
    return {"vehicle_id": vehicle_id, "location": location_dict(latest), "stale": stale,
            "trip": trip, "trip_status": "ACTIVE" if trip else "NO_ACTIVE_TRIP",
            "distance_travelled_km": trip["distance_km"] if trip else None,
            "remaining_distance_m": eta["remaining_distance_m"] if eta else None,
            "eta": eta, "geofences": statuses(db, vehicle_id, latest)}


def ingest_location(data, simulation_session_id=None, include_snapshot=True):
    db = get_db()
    vehicle_id = vehicle_exists(db, data.get("vehicle_id"))
    lat, lon = coordinates(data)
    timestamp = parse_timestamp(data.get("timestamp"))
    if data.get("gps_valid") is not True:
        raise APIError("gps_valid must be true; invalid GPS fixes are rejected")
    source = data.get("source")
    if source not in ("SIMULATED", "HARDWARE"):
        raise APIError("source must be SIMULATED or HARDWARE")
    supplied_speed = data.get("speed_kmh")
    if supplied_speed is not None:
        supplied_speed = number(supplied_speed, "speed_kmh", 0, current_app.config["MAX_SPEED_KMH"])
    duplicate = False
    # The lock covers the previous-point read, insert, distance and fence updates.
    with db:
        db.execute("BEGIN IMMEDIATE")
        owner = db.execute("SELECT session_id FROM simulation_sessions WHERE vehicle_id = ? "
                           "AND state IN ('RUNNING', 'PAUSED')", (vehicle_id,)).fetchone()
        if owner and owner["session_id"] != simulation_session_id:
            raise APIError("FM01 is owned by an active simulation. Stop it before using another telemetry sender.", 409)
        previous = latest_location(db, vehicle_id)
        existing = db.execute("SELECT * FROM locations WHERE vehicle_id = ? AND timestamp = ?",
                              (vehicle_id, timestamp)).fetchone()
        if existing:
            if (existing["lat"], existing["lon"], existing["source"], existing["supplied_speed_kmh"]) != (
                    lat, lon, source, supplied_speed):
                raise APIError("Conflicting reading at this vehicle timestamp", 409)
            duplicate = True
            location_id = existing["id"]
        else:
            if previous and timestamp <= previous["timestamp"]:
                raise APIError("Out-of-order reading; timestamp must be newer than the latest location", 409)
            speed = supplied_speed
            if speed is None and previous:
                distance = haversine(previous["lat"], previous["lon"], lat, lon)
                elapsed = (datetime.fromisoformat(timestamp) -
                           datetime.fromisoformat(previous["timestamp"])).total_seconds()
                speed = derived_speed(distance, elapsed, current_app.config["MAX_SPEED_KMH"])
                if speed is None:
                    raise APIError("Cannot derive a realistic speed from these GPS points")
            speed = speed if speed is not None else 0.0
            trip = active_trip(db, vehicle_id)
            trip_id = trip["trip_id"] if trip else None
            cursor = db.execute(
                """INSERT INTO locations
                (vehicle_id, trip_id, lat, lon, timestamp, received_at, speed_kmh,
                 supplied_speed_kmh, gps_valid, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (vehicle_id, trip_id, lat, lon, timestamp, utc_now(), speed, supplied_speed, source),
            )
            location_id = cursor.lastrowid
            if trip:
                movement = haversine(trip["distance_anchor_lat"], trip["distance_anchor_lon"], lat, lon)
                if movement >= current_app.config["MIN_MOVEMENT_M"]:
                    db.execute("UPDATE trips SET distance_m = distance_m + ?, "
                               "distance_anchor_lat = ?, distance_anchor_lon = ? WHERE trip_id = ?",
                               (movement, lat, lon, trip_id))
            update_geofences(db, {"id": location_id, "vehicle_id": vehicle_id, "trip_id": trip_id,
                                   "lat": lat, "lon": lon, "timestamp": timestamp})
            monitor_route(db, {"id": location_id, "vehicle_id": vehicle_id, "trip_id": trip_id,
                               "lat": lat, "lon": lon, "timestamp": timestamp}, trip)
    return {"accepted": True, "duplicate": duplicate, "location_id": location_id,
            "vehicle": vehicle_snapshot(vehicle_id) if include_snapshot else None}
