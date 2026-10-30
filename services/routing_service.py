"""Optional OSRM lookup with bounded waits, caching and failure backoff."""
import json
import math
import time
from http.client import HTTPException
from urllib.request import urlopen
from urllib.error import URLError
from threading import Lock


class RoutingService:
    def __init__(self, config):
        self.config = config
        self.cache = {}
        self.retry_after = 0
        self.lock = Lock()

    def options(self, lat, lon, dest_lat, dest_lon, origin_radius=150, snap_any=False):
        """Planning is explicit and may wait longer than a live telemetry lookup."""
        if not self.config["ROUTING_ENABLED"]:
            return []
        url = (f"{self.config['ROUTING_URL']}/{lon},{lat};{dest_lon},{dest_lat}"
               f"?overview=full&geometries=geojson&alternatives=3&radiuses={origin_radius};150")
        if snap_any:
            url += '&snapping=any'  # A moving fix may lie on an edge excluded as a default start point.
        try:
            with urlopen(url, timeout=self.config["ROUTE_PLANNING_TIMEOUT"]) as response:
                data = json.loads(response.read(2_000_000))
            if not isinstance(data, dict) or data.get("code") != "Ok" or not isinstance(data.get("routes"), list):
                return []
            results = []
            for route in data["routes"][:4]:
                if not isinstance(route, dict) or not isinstance(route.get("geometry"), dict):
                    continue
                geometry = route["geometry"]
                distance, duration = float(route["distance"]), float(route["duration"])
                if (geometry.get("type") == "LineString" and self.valid_geometry(geometry)
                        and len(geometry["coordinates"]) <= 10000
                        and all(math.isfinite(v) and v > 0 for v in (distance, duration))):
                    results.append({"geometry": geometry, "distance_m": distance, "duration_seconds": duration})
            return results
        except (URLError, TimeoutError, OSError, HTTPException, ValueError, KeyError, TypeError, IndexError):
            return []

    def route(self, lat, lon, dest_lat, dest_lon):
        if not self.config["ROUTING_ENABLED"]:
            return None
        key = tuple(round(x, 4) for x in (lat, lon, dest_lat, dest_lon))
        with self.lock:
            now = time.monotonic()
            self.cache = {k: v for k, v in self.cache.items() if v[0] > now}
            if key in self.cache:
                return self.cache[key][1]
            if now < self.retry_after:
                return None
            url = (f"{self.config['ROUTING_URL']}/{lon},{lat};{dest_lon},{dest_lat}"
                   "?overview=full&geometries=geojson&radiuses=150;150")
            try:
                with urlopen(url, timeout=self.config["ROUTING_TIMEOUT"]) as response:
                    data = json.loads(response.read(1_000_000))
                if not isinstance(data, dict) or data.get("code") != "Ok":
                    raise ValueError("No road route")
                route = data["routes"][0]
                if not isinstance(route, dict):
                    raise ValueError("Invalid route object")
                distance, duration = float(route["distance"]), float(route["duration"])
                if not all(math.isfinite(x) and x > 0 for x in (distance, duration)):
                    raise ValueError("Invalid road route")
                geometry = route.get("geometry")
                if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
                    geometry = None
                elif not self.valid_geometry(geometry):
                    geometry = None
                result = {"distance_m": distance, "duration_seconds": duration,
                          "geometry": geometry}
                self.cache[key] = (now + 30, result)
                return result
            except (URLError, TimeoutError, OSError, HTTPException, ValueError, KeyError, IndexError, TypeError):
                self.retry_after = now + 60
                return None

    @staticmethod
    def valid_geometry(geometry):
        points = geometry.get("coordinates")
        if not isinstance(points, list) or len(points) < 2:
            return False
        return all(isinstance(point, list) and len(point) >= 2
                   and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                           and -bound <= v <= bound and math.isfinite(v)
                           for v, bound in zip(point[:2], (180, 90))) for point in points)
