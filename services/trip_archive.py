"""Snapshot route provenance at trip start/reroute; history never calls a provider."""
import json

from services.route_planner import route_by_id
from validation import utc_now


def archive_route(db, trip_id, route_id, reason):
    route = route_by_id(db, route_id)
    db.execute("INSERT INTO trip_route_versions (trip_id,route_id,reason,timestamp,route_json) VALUES (?,?,?,?,?)",
               (trip_id,route_id,reason,utc_now(),json.dumps(route)))
    return route


def initialize_trip(db, trip_id, route_id=None, start_label=None, speed=None, multiplier=None):
    trip=db.execute("SELECT * FROM trips WHERE trip_id = ?",(trip_id,)).fetchone()
    route=archive_route(db,trip_id,route_id,'INITIAL') if route_id else None
    label=start_label or f"{trip['start_lat']:.6f}, {trip['start_lon']:.6f}"
    db.execute("UPDATE trips SET created_at = start_time, start_label = ?, initial_route_id = ?, "
               "initial_route_distance_m = ?, initial_eta_seconds = ?, initial_traffic_json = ?, "
               "initial_speed_kmh = ?, initial_multiplier = ? WHERE trip_id = ?",
               (label,route_id,route['distance_m'] if route else None,route['duration_seconds'] if route else None,
                json.dumps(route['traffic']) if route and route.get('traffic') else None,speed,multiplier,trip_id))
    original=(route['requested_destination'] if route else {'lat':trip['destination_lat'],'lon':trip['destination_lon']})|{'label':trip['destination_label']}
    db.execute('UPDATE trips SET original_destination_json=? WHERE trip_id=?',(json.dumps(original),trip_id))
