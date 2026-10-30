"""Persistent timeline + real in-app admin notifications, in the caller's transaction."""
import json

from validation import utc_now


def record_event(db, vehicle_id, trip_id, kind, title, message, severity="INFO", notify=False,
                 timestamp=None, details=None, dedupe_key=None):
    timestamp = timestamp or utc_now()
    cursor = db.execute("""INSERT OR IGNORE INTO trip_events
        (vehicle_id, trip_id, kind, title, message, timestamp, details_json, dedupe_key)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (vehicle_id, trip_id, kind, title, message, timestamp, json.dumps(details or {}), dedupe_key))
    if cursor.rowcount and notify:
        db.execute("""INSERT INTO notifications
            (event_id, vehicle_id, trip_id, type, title, message, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (cursor.lastrowid, vehicle_id, trip_id, severity, title, message, timestamp))
    return cursor.lastrowid


def events(db, vehicle_id="FM01", trip_id=None, limit=40):
    query = "SELECT * FROM trip_events WHERE vehicle_id = ?"
    params = [vehicle_id]
    if trip_id is not None:
        query += " AND trip_id = ?"
        params.append(trip_id)
    query += " ORDER BY event_id DESC LIMIT ?"
    result = []
    for row in db.execute(query, (*params, limit)):
        item = dict(row)
        item["details"] = json.loads(item.pop("details_json"))
        result.append(item)
    return result


def notifications(db, vehicle_id="FM01", limit=50):
    rows = db.execute("SELECT n.*, e.kind FROM notifications n JOIN trip_events e USING(event_id) "
                      "WHERE n.vehicle_id = ? ORDER BY notification_id DESC LIMIT ?", (vehicle_id, limit))
    items = [dict(row) for row in rows]
    for item in items:
        item["is_read"] = bool(item["is_read"])
    unread = db.execute("SELECT COUNT(*) FROM notifications WHERE vehicle_id = ? AND is_read = 0",
                        (vehicle_id,)).fetchone()[0]
    return {"notifications": items, "unread_count": unread}
