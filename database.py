"""One SQLite connection per Flask request; writes use explicit transactions."""
import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id TEXT PRIMARY KEY,
    vehicle_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trips (
    trip_id INTEGER PRIMARY KEY,
    vehicle_id TEXT NOT NULL REFERENCES vehicles(vehicle_id),
    start_time TEXT NOT NULL,
    end_time TEXT,
    start_lat REAL NOT NULL,
    start_lon REAL NOT NULL,
    destination_lat REAL NOT NULL,
    destination_lon REAL NOT NULL,
    destination_label TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'COMPLETED')),
    distance_m REAL NOT NULL DEFAULT 0,
    distance_anchor_lat REAL NOT NULL,
    distance_anchor_lon REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_trip ON trips(vehicle_id)
    WHERE status = 'ACTIVE';
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY,
    vehicle_id TEXT NOT NULL REFERENCES vehicles(vehicle_id),
    trip_id INTEGER REFERENCES trips(trip_id),
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    timestamp TEXT NOT NULL,
    received_at TEXT NOT NULL,
    speed_kmh REAL NOT NULL,
    supplied_speed_kmh REAL,
    gps_valid INTEGER NOT NULL CHECK(gps_valid = 1),
    source TEXT NOT NULL CHECK(source IN ('SIMULATED', 'HARDWARE')),
    UNIQUE(vehicle_id, timestamp)
);
CREATE INDEX IF NOT EXISTS location_history ON locations(vehicle_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS trip_locations ON locations(trip_id, timestamp DESC);
CREATE TABLE IF NOT EXISTS geofences (
    geofence_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    center_lat REAL NOT NULL,
    center_lon REAL NOT NULL,
    radius_m REAL NOT NULL CHECK(radius_m > 0),
    enabled INTEGER NOT NULL DEFAULT 1,
    vehicle_id TEXT NOT NULL REFERENCES vehicles(vehicle_id)
);
CREATE TABLE IF NOT EXISTS geofence_states (
    geofence_id INTEGER NOT NULL REFERENCES geofences(geofence_id) ON DELETE CASCADE,
    vehicle_id TEXT NOT NULL REFERENCES vehicles(vehicle_id),
    status TEXT NOT NULL CHECK(status IN ('INSIDE', 'OUTSIDE')),
    PRIMARY KEY(geofence_id, vehicle_id)
);
CREATE TABLE IF NOT EXISTS geofence_events (
    event_id INTEGER PRIMARY KEY,
    geofence_id INTEGER NOT NULL REFERENCES geofences(geofence_id) ON DELETE CASCADE,
    vehicle_id TEXT NOT NULL REFERENCES vehicles(vehicle_id),
    trip_id INTEGER REFERENCES trips(trip_id),
    event_type TEXT NOT NULL CHECK(event_type IN ('ENTER', 'EXIT')),
    timestamp TEXT NOT NULL,
    location_id INTEGER NOT NULL REFERENCES locations(id)
);
CREATE INDEX IF NOT EXISTS recent_events ON geofence_events(vehicle_id, event_id DESC);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()  # Also rolls back an unfinished write on an error.


def init_db():
    from validation import utc_now

    Path(current_app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    db = get_db()
    db.execute("PRAGMA journal_mode = WAL")
    db.executescript(SCHEMA)
    migrate_review_schema(db)
    db.execute(
        "INSERT OR IGNORE INTO vehicles (vehicle_id, vehicle_name, created_at) VALUES (?, ?, ?)",
        ("FM01", "FleetMitra Demo Vehicle", utc_now()),
    )
    db.commit()


def migrate_review_schema(db):
    """Additive, repeatable migration; never rebuild or discard an existing table."""
    db.executescript("""
    CREATE TABLE IF NOT EXISTS route_plans (
        route_id INTEGER PRIMARY KEY, name TEXT NOT NULL, method TEXT NOT NULL,
        geometry_json TEXT NOT NULL, distance_m REAL NOT NULL, duration_seconds REAL NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS trip_events (
        event_id INTEGER PRIMARY KEY, vehicle_id TEXT NOT NULL REFERENCES vehicles(vehicle_id),
        trip_id INTEGER REFERENCES trips(trip_id), kind TEXT NOT NULL, title TEXT NOT NULL,
        message TEXT NOT NULL, timestamp TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}',
        dedupe_key TEXT UNIQUE
    );
    CREATE INDEX IF NOT EXISTS trip_event_history ON trip_events(trip_id, event_id DESC);
    CREATE TABLE IF NOT EXISTS notifications (
        notification_id INTEGER PRIMARY KEY, event_id INTEGER UNIQUE REFERENCES trip_events(event_id),
        vehicle_id TEXT NOT NULL REFERENCES vehicles(vehicle_id), trip_id INTEGER REFERENCES trips(trip_id),
        type TEXT NOT NULL, title TEXT NOT NULL, message TEXT NOT NULL, timestamp TEXT NOT NULL,
        is_read INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS notification_history ON notifications(vehicle_id, notification_id DESC);
    CREATE TABLE IF NOT EXISTS simulation_sessions (
        session_id INTEGER PRIMARY KEY, vehicle_id TEXT NOT NULL REFERENCES vehicles(vehicle_id),
        trip_id INTEGER NOT NULL REFERENCES trips(trip_id), route_id INTEGER NOT NULL REFERENCES route_plans(route_id),
        state TEXT NOT NULL, speed_kmh REAL NOT NULL, multiplier INTEGER NOT NULL,
        position_m REAL NOT NULL DEFAULT 0, elapsed_seconds REAL NOT NULL DEFAULT 0,
        scenario TEXT NOT NULL DEFAULT 'normal', flags_json TEXT NOT NULL DEFAULT '{}',
        outage_remaining_s REAL NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS one_live_simulation ON simulation_sessions(vehicle_id)
        WHERE state IN ('RUNNING', 'PAUSED');
    CREATE TABLE IF NOT EXISTS trip_route_versions (
        version_id INTEGER PRIMARY KEY, trip_id INTEGER NOT NULL REFERENCES trips(trip_id),
        route_id INTEGER NOT NULL REFERENCES route_plans(route_id), reason TEXT NOT NULL,
        timestamp TEXT NOT NULL, route_json TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS trip_route_archive ON trip_route_versions(trip_id, version_id);
    CREATE TABLE IF NOT EXISTS drivers (
        driver_id TEXT PRIMARY KEY, full_name TEXT NOT NULL,
        assigned_vehicle_id TEXT REFERENCES vehicles(vehicle_id),
        is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
        is_sample INTEGER NOT NULL DEFAULT 0 CHECK(is_sample IN (0,1)),
        experience_years REAL NOT NULL DEFAULT 0, date_joined TEXT,
        license_expiry TEXT, license_mask TEXT NOT NULL DEFAULT '', phone_mask TEXT NOT NULL DEFAULT '',
        private_encrypted TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS one_assigned_driver ON drivers(assigned_vehicle_id)
        WHERE assigned_vehicle_id IS NOT NULL;
    CREATE TABLE IF NOT EXISTS destination_proposals (
        proposal_id TEXT PRIMARY KEY, trip_id INTEGER NOT NULL REFERENCES trips(trip_id),
        revision INTEGER NOT NULL, destination_json TEXT NOT NULL, route_ids_json TEXT NOT NULL,
        created_at TEXT NOT NULL, applied_route_id INTEGER REFERENCES route_plans(route_id)
    );
    """)
    additions = {
        "route_plans": {"traffic_json": "TEXT", "requested_start_json": "TEXT", "requested_destination_json": "TEXT"},
        "trips": {"route_id": "INTEGER REFERENCES route_plans(route_id)",
                  "created_at": "TEXT", "start_label": "TEXT", "initial_route_id": "INTEGER REFERENCES route_plans(route_id)",
                  "initial_route_distance_m": "REAL", "initial_eta_seconds": "REAL", "initial_traffic_json": "TEXT",
                  "initial_speed_kmh": "REAL", "initial_multiplier": "INTEGER", "end_reason": "TEXT",
                  "driver_id": "TEXT REFERENCES drivers(driver_id)", "driver_name": "TEXT", "driver_sample": "INTEGER",
                  "original_destination_json": "TEXT", "navigation_revision": "INTEGER NOT NULL DEFAULT 0",
                  "completion_status": "TEXT", "route_status": "TEXT NOT NULL DEFAULT 'UNPLANNED'",
                  "route_progress_m": "REAL NOT NULL DEFAULT 0", "route_total_m": "REAL NOT NULL DEFAULT 0",
                  "route_offset_m": "REAL NOT NULL DEFAULT 0", "off_route_count": "INTEGER NOT NULL DEFAULT 0",
                  "elapsed_seconds": "REAL NOT NULL DEFAULT 0", "data_source": "TEXT"},
        "vehicles": {"freshness_state": "TEXT NOT NULL DEFAULT 'WAITING'", "input_mode": "TEXT NOT NULL DEFAULT 'SIMULATED'"},
    }
    for table, columns in additions.items():
        existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        for column, definition in columns.items():
            if column not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    db.execute("UPDATE trips SET created_at = start_time WHERE created_at IS NULL")
    db.execute("CREATE INDEX IF NOT EXISTS trip_history_search ON trips(vehicle_id, start_time DESC)")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_active_driver_trip ON trips(driver_id) WHERE status='ACTIVE' AND driver_id IS NOT NULL")
    db.execute("CREATE INDEX IF NOT EXISTS driver_trip_history ON trips(driver_id, start_time DESC)")
