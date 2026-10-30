"""Pure calculations: meters, seconds, and km/h. No database or network."""
from datetime import datetime, timezone, timedelta
import math

EARTH_RADIUS_M = 6_371_000


def _coordinate(value, bound):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Coordinates must be finite numbers")
    if not -bound <= value <= bound or not math.isfinite(value):
        raise ValueError("Coordinates are outside their valid range")


def haversine(lat1, lon1, lat2, lon2):
    for value, bound in ((lat1, 90), (lat2, 90), (lon1, 180), (lon2, 180)):
        _coordinate(value, bound)
    a1, a2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = a2 - a1, math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_M * 2 * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def derived_speed(distance_m, elapsed_seconds, max_speed=200):
    if elapsed_seconds <= 0 or distance_m < 0:
        return None
    speed = distance_m / elapsed_seconds * 3.6
    return speed if math.isfinite(speed) and speed <= max_speed else None


def estimate_eta(straight_m, samples, route=None, arrival_radius_m=35, minimum_speed=3,
                 stale=False, now=None):
    """Road duration is OSRM's model; fallback uses up to five recent GPS speeds.

    A stopped latest sample suppresses an ETA even when older samples were moving.
    """
    method = "ROAD_ROUTE" if route else "FALLBACK"
    remaining = route["distance_m"] if route else straight_m
    result = {"method": method, "status": "WAITING_FOR_MOVEMENT",
              "remaining_distance_m": remaining, "straight_line_distance_m": straight_m,
              "duration_seconds": None, "arrival_time": None,
              "average_speed_kmh": sum(samples) / len(samples) if samples else None,
              "geometry": route.get("geometry") if route else None}
    if straight_m <= arrival_radius_m:
        result.update(status="ARRIVED", remaining_distance_m=0.0, duration_seconds=0.0)
        result["arrival_time"] = (now or datetime.now(timezone.utc)).isoformat()
        return result
    if stale:
        result["status"] = "WAITING_FOR_GPS"
        return result
    average = result["average_speed_kmh"]
    if not samples or samples[0] < minimum_speed or average < minimum_speed:
        return result
    seconds = route["duration_seconds"] if route else remaining / (average / 3.6)
    result.update(status="EN_ROUTE", duration_seconds=round(seconds, 1),
                  arrival_time=((now or datetime.now(timezone.utc)) +
                                timedelta(seconds=seconds)).isoformat())
    return result
