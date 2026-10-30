"""Persistent transition state prevents duplicate ENTER / EXIT events."""
from calculations import haversine
from services.event_service import record_event


def fence_status(fence, lat, lon):
    distance = haversine(lat, lon, fence["center_lat"], fence["center_lon"])
    return ("INSIDE" if distance <= fence["radius_m"] else "OUTSIDE"), distance


def update_geofences(db, location):
    fences = db.execute(
        "SELECT * FROM geofences WHERE enabled = 1 AND vehicle_id = ?",
        (location["vehicle_id"],),
    ).fetchall()
    for fence in fences:
        status, _ = fence_status(fence, location["lat"], location["lon"])
        previous = db.execute(
            "SELECT status FROM geofence_states WHERE geofence_id = ? AND vehicle_id = ?",
            (fence["geofence_id"], location["vehicle_id"]),
        ).fetchone()
        if previous and previous["status"] != status:
            db.execute(
                """INSERT INTO geofence_events
                (geofence_id, vehicle_id, trip_id, event_type, timestamp, location_id)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (fence["geofence_id"], location["vehicle_id"], location["trip_id"],
                 "ENTER" if status == "INSIDE" else "EXIT", location["timestamp"], location["id"]),
            )
            entering = status == "INSIDE"
            record_event(db, location["vehicle_id"], location["trip_id"],
                         "GEOFENCE_ENTER" if entering else "GEOFENCE_EXIT",
                         "Geofence entered" if entering else "Geofence exited",
                         f"FM01 {'entered' if entering else 'exited'} {fence['name']}.",
                         "INFO", True, details={"geofence_id": fence["geofence_id"]})
        db.execute(
            """INSERT INTO geofence_states VALUES (?, ?, ?)
            ON CONFLICT(geofence_id, vehicle_id) DO UPDATE SET status = excluded.status""",
            (fence["geofence_id"], location["vehicle_id"], status),
        )


def statuses(db, vehicle_id, location):
    result = []
    for row in db.execute("SELECT * FROM geofences WHERE vehicle_id = ? ORDER BY geofence_id",
                          (vehicle_id,)).fetchall():
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        item.update(status="WAITING_FOR_GPS", distance_from_center_m=None)
        if not item["enabled"]:
            item["status"] = "DISABLED"
        elif location:
            item["status"], item["distance_from_center_m"] = fence_status(
                item, location["lat"], location["lon"])
        result.append(item)
    return result
