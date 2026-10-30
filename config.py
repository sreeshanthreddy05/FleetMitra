"""Small, environment-based configuration. Distances are meters internally."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def settings():
    database = Path(os.getenv("FLEET_DATABASE", "instance/fleet_mitra.sqlite3"))
    return {
        "DATABASE": str(database if database.is_absolute() else ROOT / database),
        "MIN_MOVEMENT_M": float(os.getenv("FLEET_MIN_MOVEMENT_M", "5")),
        "ARRIVAL_RADIUS_M": float(os.getenv("FLEET_ARRIVAL_RADIUS_M", "35")),
        "MAX_SPEED_KMH": 200.0,
        "MIN_ETA_SPEED_KMH": 3.0,
        "SPEED_WINDOW": 5,
        "STALE_AFTER_SECONDS": 30,
        "ROUTING_ENABLED": os.getenv("FLEET_ROUTING_ENABLED", "true").lower() == "true",
        "ROUTING_TIMEOUT": float(os.getenv("FLEET_ROUTING_TIMEOUT", "1.2")),
        "ROUTING_URL": os.getenv("FLEET_ROUTING_URL", "https://router.project-osrm.org/route/v1/driving"),
        "ROUTE_PLANNING_TIMEOUT": float(os.getenv("FLEET_ROUTE_PLANNING_TIMEOUT", "6")),
        "DEFAULT_VEHICLE_ID": "FM01",
        "DEFAULT_SPEED_KMH": 40,
        "SIMULATION_MULTIPLIERS": (1, 2, 4, 8, 16),
        "SIMULATION_INTERVAL": 0.5,
        "SIMULATION_AUTORUN": True,
        "DEVIATION_THRESHOLD_M": float(os.getenv("FLEET_DEVIATION_THRESHOLD_M", "75")),
        "DEVIATION_CONFIRM_COUNT": 3,
        "DEMO_STALE_SECONDS": 5,
        "DEFAULT_MAP_CENTER": [17.4174, 78.4825],
        "SAVED_PLACES": [{"id": "home", "name": "Home", "lat": 17.415666, "lon": 78.573060}],
        "GEOCODING_URL": os.getenv("FLEET_GEOCODING_URL", "https://photon.komoot.io/api/"),
        "GEOCODING_ENABLED": os.getenv("FLEET_GEOCODING_ENABLED", "true").lower()=="true",
        "GEOCODING_TIMEOUT": 5,
        "MAX_CONTENT_LENGTH": 128 * 1024,
    }
