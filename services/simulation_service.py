"""One server-side clock for FM01. Frames only render; they never advance the trip."""
import json
import math
import threading
import time

from flask import current_app

from database import get_db
from services.event_service import record_event
from services.route_geometry import point_at, prepare, project
from services.route_planner import route_by_id
from services.tracking_service import active_trip, ingest_location
from validation import APIError, number, utc_now
from validation import text_field
from services.trip_archive import initialize_trip

SCENARIOS = {
    "normal": "Follow the selected geometry to the destination.",
    "geofence": "Create a review zone halfway along the selected route; cross it normally.",
    "speed": "At 40% route progress, change physical speed to 20 km/h once.",
    "deviation": "At 30%, move 160 m sideways, then follow a parallel offset until recovery or rerouting.",
    "connectivity": "At 25%, interrupt telemetry for 8 real seconds while holding position. Demo stale threshold: 5 seconds.",
}


class SimulationEngine:
    def __init__(self, app):
        self.app = app
        self.lock = threading.RLock()
        self.shutdown = threading.Event()
        self.thread = None
        # A process restart pauses persisted running sessions; it never teleports forward.
        with app.app_context():
            db = get_db()
            with db:
                db.execute("UPDATE simulation_sessions SET state = 'PAUSED' WHERE state = 'RUNNING'")

    def session(self):
        return get_db().execute("SELECT * FROM simulation_sessions WHERE vehicle_id = ? ORDER BY session_id DESC LIMIT 1",
                                (current_app.config["DEFAULT_VEHICLE_ID"],)).fetchone()

    def status(self):
        row = self.session()
        if not row:
            return {"state": "IDLE", "speed_kmh": current_app.config["DEFAULT_SPEED_KMH"], "multiplier": 1}
        result = dict(row)
        result["flags"] = json.loads(result.pop("flags_json"))
        route = route_by_id(get_db(), row["route_id"])
        result.update(route=route, route_distance_m=route["distance_m"],
                      remaining_distance_m=max(0, route["distance_m"] - row["position_m"]))
        return result

    def start(self, data):
        with self.lock:
            db = get_db()
            vehicle = current_app.config["DEFAULT_VEHICLE_ID"]
            if active_trip(db, vehicle) or (self.session() and self.session()["state"] in ("RUNNING", "PAUSED")):
                raise APIError("A trip or simulation is already active", 409)
            route = route_by_id(db, data.get("route_id"))
            speed, multiplier = self.validate_settings(data)
            scenario = data.get("scenario", "normal")
            start_label=text_field(data.get('start_label'),'start_label',f"{route['requested_start']['lat']:.6f}, {route['requested_start']['lon']:.6f}")
            destination_label=text_field(data.get('destination_label'),'destination_label',route['name'])
            if scenario not in SCENARIOS:
                raise APIError("Unknown demo scenario")
            from services.driver_service import assign_trip_driver
            assign_trip_driver(db,None,data.get('driver_id'),vehicle)
            # The initial fix goes through exactly the same validation/processing function.
            ingest_location({"vehicle_id": vehicle, **route["start"], "timestamp": utc_now(),
                             "speed_kmh": speed, "gps_valid": True, "source": "SIMULATED"}, include_snapshot=False)
            with db:
                db.execute("BEGIN IMMEDIATE")
                if active_trip(db, vehicle):
                    raise APIError("A trip is already active", 409)
                cursor = db.execute("""INSERT INTO trips
                    (vehicle_id, start_time, start_lat, start_lon, destination_lat, destination_lon,
                     destination_label, status, distance_anchor_lat, distance_anchor_lon,
                     route_id, route_status, route_total_m, data_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, 'ON_ROUTE', ?, 'SIMULATED')""",
                    (vehicle, utc_now(), route["start"]["lat"], route["start"]["lon"],
                     route["destination"]["lat"], route["destination"]["lon"], destination_label,
                     route["start"]["lat"], route["start"]["lon"], route["route_id"], route["distance_m"]))
                trip_id = cursor.lastrowid
                assign_trip_driver(db,trip_id,data.get('driver_id'),vehicle)
                initialize_trip(db,trip_id,route['route_id'],start_label,speed,multiplier)
                seed=db.execute("SELECT id FROM locations WHERE vehicle_id = ? ORDER BY timestamp DESC LIMIT 1",(vehicle,)).fetchone()
                db.execute("UPDATE locations SET trip_id = ? WHERE id = ?",(trip_id,seed['id']))
                db.execute("""INSERT INTO simulation_sessions
                    (vehicle_id, trip_id, route_id, state, speed_kmh, multiplier, scenario, updated_at, flags_json)
                    VALUES (?, ?, ?, 'RUNNING', ?, ?, ?, ?, ?)""",
                    (vehicle, trip_id, route["route_id"], speed, multiplier, scenario, utc_now(),
                     json.dumps({"auto_reroute": data.get("auto_reroute") is True})))
                db.execute("UPDATE vehicles SET input_mode = 'SIMULATED' WHERE vehicle_id = ?", (vehicle,))
                if scenario == "geofence":
                    lat, lon, _ = point_at(json.dumps(route["geometry"]), route["distance_m"] / 2)
                    from geofence import fence_status
                    fence_id = db.execute("INSERT INTO geofences (name, center_lat, center_lon, radius_m, vehicle_id) "
                                          "VALUES (?, ?, ?, ?, ?)",
                                          (f"Review Zone · Trip {trip_id}", lat, lon, min(80, route["distance_m"] / 5), vehicle)).lastrowid
                    fence = db.execute("SELECT * FROM geofences WHERE geofence_id = ?", (fence_id,)).fetchone()
                    initial, _ = fence_status(fence, route["start"]["lat"], route["start"]["lon"])
                    db.execute("INSERT INTO geofence_states VALUES (?, ?, ?)", (fence_id, vehicle, initial))
                record_event(db, vehicle, trip_id, "TRIP_STARTED", "Simulation started",
                             f"{speed:g} km/h physical speed · {multiplier}× logical time · {scenario} scenario.", "INFO", True)
            self.ensure_worker()
            return self.status()

    def validate_settings(self, data, previous=None):
        speed = number(data.get("speed_kmh", previous["speed_kmh"] if previous else current_app.config["DEFAULT_SPEED_KMH"]),
                       "speed_kmh", 5, 120)
        multiplier = data.get("multiplier", previous["multiplier"] if previous else 1)
        if isinstance(multiplier, bool) or not isinstance(multiplier, int) or multiplier not in current_app.config["SIMULATION_MULTIPLIERS"]:
            raise APIError("multiplier must be one of 1, 2, 4, 8, 16")
        return speed, multiplier

    def change_speed(self, data):
        with self.lock:
            session = self.require_live()
            speed, multiplier = self.validate_settings(data, session)
            db = get_db()
            with db:
                db.execute("UPDATE simulation_sessions SET speed_kmh = ?, multiplier = ?, updated_at = ? WHERE session_id = ?",
                           (speed, multiplier, utc_now(), session["session_id"]))
                if speed != session["speed_kmh"]:
                    record_event(db, session["vehicle_id"], session["trip_id"], "SPEED_CHANGED", "Vehicle speed changed",
                                 f"Physical speed changed from {session['speed_kmh']:g} to {speed:g} km/h.")
                if multiplier != session["multiplier"]:
                    record_event(db, session["vehicle_id"], session["trip_id"], "MULTIPLIER_CHANGED", "Demo clock changed",
                                 f"Simulation clock changed to {multiplier}×; physical speed stays {speed:g} km/h.")
            self.send_current(self.session())
            return self.status()

    def require_live(self):
        session = self.session()
        if not session or session["state"] not in ("RUNNING", "PAUSED"):
            raise APIError("No active simulation", 409)
        return session

    def control(self, action):
        with self.lock:
            session = self.session()
            if action != "reset":
                session = self.require_live()
            if not session:
                return self.status()
            if action == "pause" and session["state"] != "RUNNING":
                raise APIError("Simulation is not running", 409)
            if action == "resume" and session["state"] != "PAUSED":
                raise APIError("Simulation is not paused", 409)
            state = {"pause": "PAUSED", "resume": "RUNNING", "stop": "STOPPED", "reset": "RESET"}[action]
            db = get_db()
            with db:
                db.execute("UPDATE simulation_sessions SET state = ?, updated_at = ? WHERE session_id = ?",
                           (state, utc_now(), session["session_id"]))
                if action in ("stop", "reset"):
                    db.execute("UPDATE trips SET status = 'COMPLETED', completion_status = 'STOPPED', end_reason = ?, end_time = ? WHERE trip_id = ? AND status = 'ACTIVE'",
                               ('RESET' if action=='reset' else 'OPERATOR_STOP',utc_now(), session["trip_id"]))
                ending_live_trip=action in ('stop','reset') and session['state'] in ('RUNNING','PAUSED')
                record_event(db, session["vehicle_id"], session["trip_id"] if action!='reset' or ending_live_trip else None,
                             "TRIP_STOPPED" if ending_live_trip else f"SIMULATION_{state}",
                             f"Simulation {state.lower()}", "Stored trip history is retained." if action == "reset" else f"Simulation {state.lower()} by the operator.", "INFO", action in ("stop", "reset"))
            if action in ("pause", "resume"):
                self.send_current(self.session())
            if action == "resume":
                self.ensure_worker()
            return self.status()

    def trigger(self, action):
        with self.lock:
            session = self.require_live()
            flags = json.loads(session["flags_json"])
            if action == "deviation":
                flags["deviation_hold"] = True
                route = route_by_id(get_db(), session["route_id"])
                location = get_db().execute("SELECT * FROM locations WHERE vehicle_id = ? ORDER BY timestamp DESC LIMIT 1",
                                            (session["vehicle_id"],)).fetchone()
                # Prefer a genuine nearby alternative road prefix for the test.
                alternatives = current_app.extensions["routing"].options(location["lat"],location["lon"],
                    route["destination"]["lat"],route["destination"]["lon"])
                for alternative in alternatives:
                    encoded = json.dumps(alternative["geometry"])
                    for distance in range(100, 801, 50):
                        if distance > prepare(encoded)[1][-1]:
                            break
                        lat, lon, _ = point_at(encoded, distance)
                        if project(json.dumps(route["geometry"]),lat,lon)["distance_m"] > current_app.config["DEVIATION_THRESHOLD_M"] + 30:
                            flags.update(test_geometry=encoded,test_position_m=0,test_limit_m=distance)
                            break
                    if flags.get("test_geometry"):
                        break
                record_event(get_db(),session["vehicle_id"],session["trip_id"],"DEVIATION_TEST_STARTED",
                    "Controlled deviation test", "Following a provider-returned alternative road." if flags.get("test_geometry")
                    else "No suitable alternative road found; using an explicit synthetic offset for testing.")
            elif action == "recover":
                flags["deviation_hold"] = False
                for key in ("test_geometry", "test_position_m", "test_limit_m"):
                    flags.pop(key, None)
            elif action == "connectivity":
                with get_db():
                    get_db().execute("UPDATE simulation_sessions SET outage_remaining_s = 8 WHERE session_id = ?", (session["session_id"],))
            else:
                raise APIError("action must be deviation, recover or connectivity")
            with get_db():
                get_db().execute("UPDATE simulation_sessions SET flags_json = ? WHERE session_id = ?",
                                 (json.dumps(flags), session["session_id"]))
            return self.status()

    def send_current(self, session):
        route = route_by_id(get_db(), session["route_id"])
        lat, lon, bearing = point_at(json.dumps(route["geometry"]), session["position_m"])
        offset = json.loads(session["flags_json"]).get("offset_m", 0)
        flags = json.loads(session["flags_json"])
        if flags.get("test_geometry"):
            lat, lon, bearing = point_at(flags["test_geometry"], flags["test_position_m"])
            offset = 0
        lat += math.cos(math.radians(bearing + 90)) * offset / 111195
        lon += math.sin(math.radians(bearing + 90)) * offset / (111195 * max(.01, math.cos(math.radians(lat))))
        ingest_location({"vehicle_id": session["vehicle_id"], "lat": lat, "lon": lon, "timestamp": utc_now(),
                         "speed_kmh": session["speed_kmh"] if session["state"] == "RUNNING" else 0,
                         "gps_valid": True, "source": "SIMULATED"},
                        simulation_session_id=session["session_id"], include_snapshot=False)

    def advance(self, real_seconds):
        """Deterministic test seam; worker uses measured monotonic elapsed time."""
        with self.lock:
            session = self.session()
            if not session or session["state"] != "RUNNING":
                return
            if session["outage_remaining_s"] > 0:
                with get_db():
                    get_db().execute("UPDATE simulation_sessions SET outage_remaining_s = MAX(0, outage_remaining_s - ?) WHERE session_id = ?",
                                     (real_seconds, session["session_id"]))
                return
            logical_remaining = max(0, min(real_seconds, 30)) * session["multiplier"]
            while logical_remaining > .000001:
                session = self.session()
                if session["state"] != "RUNNING":
                    break
                # At most ten meters per accepted point, independent of frame/worker rate.
                step = min(logical_remaining, 10 / (session["speed_kmh"] / 3.6))
                self.step(session, step)
                logical_remaining -= step
            self.automatic_reroute()

    def automatic_reroute(self):
        """One attempt per episode. Demo connectors are explicitly labelled."""
        session = self.session()
        if not session or session["state"] != "RUNNING":
            return
        flags = json.loads(session["flags_json"])
        trip = active_trip(get_db(), session["vehicle_id"])
        if not trip or trip["route_status"] != "DEVIATED" or not flags.get("auto_reroute") or flags.get("auto_attempted"):
            return
        flags["auto_attempted"] = True
        with get_db():
            get_db().execute("UPDATE simulation_sessions SET flags_json = ? WHERE session_id = ?", (json.dumps(flags), session["session_id"]))
        from routes.operations_routes import reroute, accept_reroute
        route = route_by_id(get_db(), trip["route_id"])
        try:
            with self.app.test_request_context(json={"demo_fallback": route["method"] == "DEMO_ROUTE"}):
                result = reroute().get_json()
                proposal = next((r for r in result["routes"] if r["route_id"] == result.get("recommended_route_id")),result["routes"][0])
            with self.app.test_request_context(json={"route_id": proposal["route_id"]}):
                accept_reroute()
            self.control("resume")
        except APIError as error:
            with get_db():
                record_event(get_db(), session["vehicle_id"], session["trip_id"], "REROUTE_FAILED",
                             "Automatic rerouting unavailable", error.message + " Original route retained; simulation paused for review.", "WARNING", True)

    def step(self, session, logical_seconds):
        db = get_db()
        route = route_by_id(db, session["route_id"])
        flags = json.loads(session["flags_json"])
        ratio = session["position_m"] / route["distance_m"]
        if session["scenario"] == "deviation" and ratio >= .3 and not flags.get("deviation_scripted"):
            flags.update(deviation_hold=True, deviation_scripted=True)
        if session["scenario"] == "speed" and ratio >= .4 and not flags.get("speed_scripted"):
            flags["speed_scripted"] = True
            with db:
                db.execute("UPDATE simulation_sessions SET speed_kmh = 20 WHERE session_id = ?", (session["session_id"],))
                record_event(db, session["vehicle_id"], session["trip_id"], "SPEED_CHANGED", "Scripted speed change",
                             f"Speed & ETA Demo changed physical speed from {session['speed_kmh']:g} to 20 km/h.")
            session = self.session()
        if session["scenario"] == "connectivity" and ratio >= .25 and not flags.get("outage_scripted"):
            flags["outage_scripted"] = True
            with db:
                db.execute("UPDATE simulation_sessions SET outage_remaining_s = 8, flags_json = ? WHERE session_id = ?",
                           (json.dumps(flags), session["session_id"]))
            return
        if session["outage_remaining_s"] > 0:
            return
        budget = session["speed_kmh"] / 3.6 * logical_seconds
        if flags.get("test_geometry"):
            flags["test_position_m"] = min(flags["test_limit_m"],flags["test_position_m"] + budget)
            with db:
                db.execute("UPDATE simulation_sessions SET elapsed_seconds = elapsed_seconds + ?, flags_json = ?, updated_at = ? WHERE session_id = ?",
                           (logical_seconds,json.dumps(flags),utc_now(),session["session_id"]))
                db.execute("UPDATE trips SET elapsed_seconds = elapsed_seconds + ? WHERE trip_id = ?",(logical_seconds,session["trip_id"]))
            self.send_current(self.session())
            return
        old_offset = flags.get("offset_m", 0)
        target = 160 if flags.get("deviation_hold") else 0
        delta = max(-budget, min(budget, target - old_offset))
        flags["offset_m"] = old_offset + delta
        forward = math.sqrt(max(0, budget * budget - delta * delta))
        position = min(route["distance_m"], session["position_m"] + forward)
        with db:
            db.execute("UPDATE simulation_sessions SET position_m = ?, elapsed_seconds = elapsed_seconds + ?, "
                       "flags_json = ?, updated_at = ? WHERE session_id = ?",
                       (position, logical_seconds, json.dumps(flags), utc_now(), session["session_id"]))
            db.execute("UPDATE trips SET elapsed_seconds = elapsed_seconds + ? WHERE trip_id = ?",
                       (logical_seconds, session["trip_id"]))
        self.send_current(self.session())

    def ensure_worker(self):
        if not self.app.config["SIMULATION_AUTORUN"] or (self.thread and self.thread.is_alive()):
            return
        self.thread = threading.Thread(target=self.run, name="fleetmitra-simulator", daemon=True)
        self.thread.start()

    def run(self):
        last = time.monotonic()
        while not self.shutdown.wait(self.app.config["SIMULATION_INTERVAL"]):
            now = time.monotonic()
            elapsed, last = min(2, now - last), now
            try:
                with self.app.app_context():
                    self.advance(elapsed)
            except Exception:
                self.app.logger.exception("Simulation paused after processing failure")
                with self.app.app_context():
                    db = get_db()
                    with db:
                        row = self.session()
                        if row and row["state"] == "RUNNING":
                            db.execute("UPDATE simulation_sessions SET state = 'PAUSED' WHERE session_id = ?", (row["session_id"],))
                            record_event(db, row["vehicle_id"], row["trip_id"], "SIMULATION_ERROR", "Simulation paused",
                                         "Telemetry could not be processed. Check the server log and resume after fixing the cause.", "WARNING", True)
