"""Persistent selected routes, with explicit road/demo/straight-line provenance."""
import json
import secrets
from pathlib import Path

from flask import current_app

from database import get_db
from services.route_geometry import prepare, project, point_at
from services.traffic_service import simulated_traffic
from validation import APIError, utc_now


def demo_routes():
    path = Path(current_app.root_path) / "simulator/demo_routes.json"
    return json.loads(path.read_text(encoding="utf-8"))


def save_route(db, name, method, geometry, duration=None):
    encoded = json.dumps(geometry, separators=(",", ":"))
    distance = prepare(encoded)[1][-1]
    if distance < 10:
        raise APIError("Start and destination must be at least 10 meters apart")
    cursor = db.execute("INSERT INTO route_plans (name, method, geometry_json, distance_m, duration_seconds, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)", (name, method, encoded, distance, duration or distance / (40 / 3.6), utc_now()))
    return route_dict(db.execute("SELECT * FROM route_plans WHERE route_id = ?", (cursor.lastrowid,)).fetchone())


def route_dict(row):
    if row is None:
        raise APIError("Route not found", 404)
    item = dict(row)
    item["geometry"] = json.loads(item.pop("geometry_json"))
    item["start"] = {"lat": item["geometry"]["coordinates"][0][1], "lon": item["geometry"]["coordinates"][0][0]}
    item["destination"] = {"lat": item["geometry"]["coordinates"][-1][1], "lon": item["geometry"]["coordinates"][-1][0]}
    item["traffic"] = json.loads(item.pop("traffic_json")) if item.get("traffic_json") else None
    for name in ("requested_start", "requested_destination"):
        encoded = item.pop(name + "_json", None)
        item[name] = json.loads(encoded) if encoded else item[name.replace('requested_', '')]
    return item


def route_by_id(db, route_id):
    if isinstance(route_id, bool) or not isinstance(route_id, int):
        raise APIError("route_id must be an integer")
    return route_dict(db.execute("SELECT * FROM route_plans WHERE route_id = ?", (route_id,)).fetchone())


def plan_routes(start, destination, demo_id=None, allow_fallback=False, origin_radius=None):
    db = get_db()
    if demo_id is not None:
        preset = next((r for r in demo_routes() if r["id"] == demo_id), None)
        if not preset:
            raise APIError("Demo route not found", 404)
        with db:
            routes = [save_route(db, preset["name"], "DEMO_ROUTE", preset["geometry"])]
        return {"routes": routes, "message": "Stored DEMO ROUTE. Illustrative fixture, not live traffic routing.", "preset": preset}
    options={} if origin_radius is None else {'origin_radius':origin_radius,'snap_any':True}
    raw_routes = distinct_routes(current_app.extensions["routing"].options(*start, *destination,**options))
    with db:
        routes = [save_route(db, "Recommended road route" if index == 0 else f"Alternative road route {index}",
                             "ROAD_ROUTE", route["geometry"], route["duration_seconds"])
                  for index, route in enumerate(raw_routes)]
        if not routes and allow_fallback:
            routes = [save_route(db, "Straight-line fallback", "FALLBACK", {
                "type": "LineString", "coordinates": [[start[1], start[0]], [destination[1], destination[0]]]})]
    if not routes:
        raise APIError("Road routing unavailable or no route found. Retry, choose other points, or explicitly enable labelled straight-line fallback.", 503)
    seed = secrets.token_hex(8)
    with db:
        for route in routes:
            traffic = simulated_traffic(route["geometry"], route["duration_seconds"], seed)
            db.execute("UPDATE route_plans SET traffic_json = ?, requested_start_json = ?, requested_destination_json = ? WHERE route_id = ?",
                       (json.dumps(traffic), json.dumps({"lat":start[0],"lon":start[1]}),
                        json.dumps({"lat":destination[0],"lon":destination[1]}), route["route_id"]))
        routes = [route_by_id(db, route["route_id"]) for route in routes]
    recommended = min(routes, key=lambda route:route["traffic"]["adjusted_duration_seconds"])["route_id"]
    return {"routes": routes, "recommended_route_id": recommended, "message":
            f"OSRM supplied {len(routes)} distinct road route(s). Three alternatives are not guaranteed by the network/provider. Traffic is SIMULATED."
            if routes[0]["method"] == "ROAD_ROUTE" else "FALLBACK: straight-line geometry, not a road route."}


def distinct_routes(routes):
    """Drop traces with similar length and bidirectional sampled separation <=25 m."""
    unique = []
    for candidate in routes:
        encoded = json.dumps(candidate["geometry"])
        length = prepare(encoded)[1][-1]
        duplicate = False
        for other in unique:
            other_json = json.dumps(other["geometry"])
            other_length = prepare(other_json)[1][-1]
            if abs(length - other_length) / max(length, other_length, 1) > .08:
                continue
            distances = []
            for source, target, size in [(encoded, other_json, length), (other_json, encoded, other_length)]:
                for i in range(21):
                    lat, lon, _ = point_at(source, size * i / 20)
                    distances.append(project(target, lat, lon)["distance_m"])
            if sum(distances) / len(distances) <= 25:
                duplicate = True
                break
        if not duplicate:
            unique.append(candidate)
    return unique


def demo_reconnect(db, trip, location):
    original = db.execute("SELECT * FROM route_plans WHERE route_id = ?", (trip["route_id"],)).fetchone()
    projected = project(original["geometry_json"], location["lat"], location["lon"])
    points = json.loads(original["geometry_json"])["coordinates"]
    coordinates = [[location["lon"], location["lat"]], projected["point"], *points[projected["segment"] + 1:]]
    with db:
        return save_route(db, "Demo reconnect — off-road connector", "DEMO_ROUTE", {"type": "LineString", "coordinates": coordinates})
