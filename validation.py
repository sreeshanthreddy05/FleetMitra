"""Strict API validation, shared by all data sources."""
from datetime import datetime, timezone, timedelta
import math

from flask import request


class APIError(Exception):
    def __init__(self, message, status=400):
        self.message = message
        self.status = status


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_timestamp(value):
    if not isinstance(value, str) or "T" not in value:
        raise APIError("timestamp must be an ISO 8601 date/time with timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError
        parsed = parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise APIError("timestamp must be a valid ISO 8601 date/time with timezone") from None
    if parsed > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise APIError("timestamp is more than five minutes in the future")
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("Request body must be a valid JSON object")
    return data


def number(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise APIError(f"{name} must be a number")
    try:
        valid = math.isfinite(value) and minimum <= value <= maximum
    except (OverflowError, TypeError):
        valid = False
    if not valid:
        raise APIError(f"{name} must be between {minimum} and {maximum}")
    return float(value)


def coordinates(data, lat_key="lat", lon_key="lon"):
    return (number(data.get(lat_key), lat_key, -90, 90),
            number(data.get(lon_key), lon_key, -180, 180))


def text_field(value, name, default=None):
    if value is None and default is not None:
        return default
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 100:
        raise APIError(f"{name} must be 1–100 characters")
    return value.strip()


def vehicle_exists(db, vehicle_id):
    if not isinstance(vehicle_id, str) or not vehicle_id:
        raise APIError("vehicle_id is required")
    if not db.execute("SELECT 1 FROM vehicles WHERE vehicle_id = ?", (vehicle_id,)).fetchone():
        raise APIError("Unknown vehicle", 404)
    return vehicle_id


def history_limit():
    try:
        limit = int(request.args.get("limit", "20"))
    except ValueError:
        raise APIError("limit must be an integer between 1 and 500") from None
    if not 1 <= limit <= 500:
        raise APIError("limit must be between 1 and 500")
    return limit
