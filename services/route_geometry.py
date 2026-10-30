"""Polyline distances and interpolation in meters; GeoJSON uses [longitude, latitude]."""
from functools import lru_cache
import json
import math

from calculations import EARTH_RADIUS_M, haversine


@lru_cache(maxsize=128)
def prepare(geometry_json):
    points = json.loads(geometry_json)["coordinates"]
    cumulative = [0.0]
    for a, b in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + haversine(a[1], a[0], b[1], b[0]))
    return points, cumulative


def point_at(geometry_json, distance_m):
    points, lengths = prepare(geometry_json)
    distance_m = max(0, min(lengths[-1], distance_m))
    for index in range(1, len(points)):
        if lengths[index] >= distance_m and lengths[index] > lengths[index - 1]:
            fraction = (distance_m - lengths[index - 1]) / (lengths[index] - lengths[index - 1])
            a, b = points[index - 1], points[index]
            lon, lat = (a[j] + (b[j] - a[j]) * fraction for j in range(2))
            bearing = math.degrees(math.atan2((b[0] - a[0]) * math.cos(math.radians(lat)), b[1] - a[1])) % 360
            return lat, lon, bearing
    return points[-1][1], points[-1][0], 0


def project(geometry_json, lat, lon):
    """Nearest point on short segments using a local equirectangular projection.

    Adequate for city-scale review routes; Haversine supplies segment lengths.
    """
    points, lengths = prepare(geometry_json)
    scale_y = math.pi / 180 * EARTH_RADIUS_M
    scale_x = scale_y * max(.000001, math.cos(math.radians(lat)))
    best = (float("inf"), 0, 0, points[0])
    for index, (a, b) in enumerate(zip(points, points[1:])):
        ax, ay = (a[0] - lon) * scale_x, (a[1] - lat) * scale_y
        dx, dy = (b[0] - a[0]) * scale_x, (b[1] - a[1]) * scale_y
        denominator = dx * dx + dy * dy
        fraction = max(0, min(1, -(ax * dx + ay * dy) / denominator)) if denominator else 0
        distance = math.hypot(ax + fraction * dx, ay + fraction * dy)
        if distance < best[0]:
            best = (distance, lengths[index] + fraction * (lengths[index + 1] - lengths[index]), index,
                    [a[0] + fraction * (b[0] - a[0]), a[1] + fraction * (b[1] - a[1])])
    return {"distance_m": best[0], "along_m": best[1], "segment": best[2], "point": best[3]}
