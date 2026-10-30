"""Review feature tests use the same engine with a deterministic monotonic-clock seam."""
from datetime import datetime, timezone, timedelta
import json

import pytest

from database import get_db
from services.route_geometry import point_at, project, prepare


@pytest.fixture
def review(app, client):
    app.config["SIMULATION_AUTORUN"] = False
    response = client.post("/api/routes", json={"demo_id": "quick-review"})
    assert response.status_code == 201
    return response.json["routes"][0]


def start(client, route, **changes):
    data = {"route_id": route["route_id"], "speed_kmh": 40, "multiplier": 8}
    data.update(changes)
    return client.post("/api/simulation/start", json=data)


def advance(app, seconds):
    with app.app_context():
        app.extensions["simulation"].advance(seconds)


def test_start_and_duplicate_start(app, client, review):
    assert start(client, review).status_code == 201
    assert start(client, review).status_code == 409
    data = client.get("/api/dashboard").json
    assert data["simulation"]["state"] == "RUNNING"
    assert data["vehicle"]["location"]["source"] == "SIMULATED"
    assert data["vehicle"]["trip"]["route_id"] == review["route_id"]


@pytest.mark.parametrize("changes", [{"speed_kmh": 0}, {"speed_kmh": 121}, {"speed_kmh": True},
    {"speed_kmh": "40"}, {"multiplier": 3}, {"multiplier": True}, {"multiplier": 8.0},
    {"scenario": "bogus"}, {"route_id": -1}, {"route_id": "1"}])
def test_invalid_simulation_settings(client, review, changes):
    assert start(client, review, **changes).status_code in (400, 404)
    assert client.get("/api/trips/current").json["trip"] is None


@pytest.mark.parametrize("multiplier", [1, 2, 4, 8, 16])
def test_multiplier_does_not_multiply_reported_speed(app, client, review, multiplier):
    start(client, review, speed_kmh=40, multiplier=multiplier)
    advance(app, 1)
    data = client.get("/api/dashboard").json
    assert data["vehicle"]["location"]["speed_kmh"] == 40
    assert data["simulation"]["position_m"] == pytest.approx(40 / 3.6 * multiplier, rel=1e-5)
    assert data["simulation"]["elapsed_seconds"] == pytest.approx(multiplier)


def test_pause_resume_and_speed_eta(app, client, review):
    start(client, review)
    advance(app, 1)
    before = client.get("/api/dashboard").json
    assert client.patch("/api/simulation/speed", json={"speed_kmh": 20}).status_code == 200
    changed = client.get("/api/dashboard").json
    assert changed["vehicle"]["eta"]["duration_seconds"] == pytest.approx(before["vehicle"]["eta"]["duration_seconds"] * 2)
    assert changed["simulation"]["trip_id"] == before["simulation"]["trip_id"]
    assert changed["simulation"]["position_m"] == before["simulation"]["position_m"]
    assert client.post("/api/simulation/pause").status_code == 200
    position = client.get("/api/simulation/status").json["simulation"]["position_m"]
    advance(app, 10)
    assert client.get("/api/simulation/status").json["simulation"]["position_m"] == position
    assert client.get("/api/vehicles/FM01/location").json["eta"]["status"] == "WAITING_FOR_MOVEMENT"
    assert client.post("/api/simulation/resume").status_code == 200
    advance(app, 1)
    assert client.get("/api/simulation/status").json["simulation"]["position_m"] > position


def test_stop_reset_preserves_history(app, client, review):
    start(client, review)
    advance(app, 2)
    assert client.post("/api/simulation/stop").status_code == 200
    assert client.get("/api/trips/current").json["trip"] is None
    trip_id = client.get("/api/trips/history").json["trips"][0]["trip_id"]
    assert client.get(f"/api/trips/{trip_id}").json["trip"]["distance_m"] > 0
    assert client.post("/api/simulation/reset").status_code == 200
    assert len(client.get("/api/trips/history").json["trips"]) == 1
    assert start(client, review).status_code == 201


def test_arrival_summary_and_single_notification(app, client, review):
    start(client, review, scenario="geofence")
    advance(app, 20)
    data = client.get("/api/dashboard").json
    assert data["simulation"]["state"] == "ARRIVED"
    assert data["last_trip"]["status"] == "ARRIVED"
    assert data["last_trip"]["progress_percent"] == 100
    assert data["last_trip"]["duration_seconds"] > 0
    assert 0 < data["last_trip"]["average_speed_kmh"] <= 41
    assert data["last_trip"]["maximum_speed_kmh"] == 40
    assert data["last_trip"]["geofence_event_count"] == 2
    arrivals = [n for n in data["notifications"] if n["kind"] == "DESTINATION_REACHED"]
    assert len(arrivals) == 1
    advance(app, 10)
    assert len([n for n in client.get("/api/notifications?limit=50").json["notifications"] if n["kind"] == "DESTINATION_REACHED"]) == 1
    detail = client.get(f"/api/trips/{data['last_trip']['trip_id']}").json
    assert len(detail["locations"]) > 10 and detail["route"]["method"] == "DEMO_ROUTE"


def test_notifications_read_and_persist(app, client, review):
    start(client, review, scenario="geofence")
    advance(app, 20)
    data = client.get("/api/notifications?limit=50").json
    assert data["unread_count"] == 4  # start, ENTER, EXIT, arrival
    notification_id = data["notifications"][0]["notification_id"]
    assert client.patch(f"/api/notifications/{notification_id}/read").status_code == 200
    assert client.get("/api/notifications").json["unread_count"] == 3
    assert client.post("/api/notifications/read-all").status_code == 200
    assert client.get("/api/notifications").json["unread_count"] == 0


def test_automatic_demo_reroute(app, client, review):
    start(client, review, auto_reroute=True)
    client.post('/api/simulation/scenario', json={'action':'deviation'})
    advance(app, 4)
    data = client.get('/api/dashboard').json
    assert data['simulation']['state'] == 'RUNNING'
    assert data['vehicle']['trip']['route_id'] != review['route_id']
    assert any(event['kind'] == 'REROUTE_ACCEPTED' for event in data['events'])


def test_automatic_road_failure_is_safe(app, client, review):
    with app.app_context():
        with get_db():
            get_db().execute("UPDATE route_plans SET method = 'ROAD_ROUTE' WHERE route_id = ?", (review['route_id'],))
    start(client, review, auto_reroute=True)
    client.post('/api/simulation/scenario', json={'action':'deviation'})
    advance(app, 4)
    data = client.get('/api/dashboard').json
    assert data['simulation']['state'] == 'PAUSED'
    assert data['vehicle']['trip']['route_id'] == review['route_id']
    assert len([event for event in data['events'] if event['kind'] == 'REROUTE_FAILED']) == 1
    assert client.post("/api/notifications/read-all").status_code == 200
    assert client.get("/api/notifications").json["unread_count"] == 0
    assert client.patch("/api/notifications/999999/read").status_code == 404
    from app import create_app
    restarted = create_app({"TESTING": True, "DATABASE": app.config["DATABASE"], "ROUTING_ENABLED": False})
    assert restarted.test_client().get("/api/notifications").json["unread_count"] == 0


def test_mode_and_sender_ownership(client, review, reading):
    assert client.post("/api/mode", json={"mode": "HARDWARE"}).status_code == 200
    assert client.get("/api/config").json["mode"] == "HARDWARE"
    start(client, review)
    assert client.post("/api/mode", json={"mode": "HARDWARE"}).status_code == 409
    assert client.post("/api/locations", json=reading()).status_code == 409
    assert client.post("/api/mode", json={"mode": "OTHER"}).status_code == 400


def test_sustained_deviation_and_recovery_once(app, client, review):
    start(client, review)
    client.post("/api/simulation/scenario", json={"action": "deviation"})
    advance(app, 5)
    data = client.get("/api/dashboard").json
    assert data["vehicle"]["trip"]["route_status"] == "DEVIATED"
    assert len([n for n in data["notifications"] if n["kind"] == "ROUTE_DEVIATION"]) == 1
    advance(app, 1)
    assert len([n for n in client.get("/api/notifications").json["notifications"] if n["kind"] == "ROUTE_DEVIATION"]) == 1
    client.post("/api/simulation/scenario", json={"action": "recover"})
    advance(app, 4)
    data = client.get("/api/dashboard").json
    assert data["vehicle"]["trip"]["route_status"] == "ON_ROUTE"
    assert len([n for n in data["notifications"] if n["kind"] == "ROUTE_RECOVERED"]) == 1


def test_single_noisy_point_does_not_alert(app, client, review):
    from services.monitoring_service import monitor_route
    start(client, review)
    with app.app_context():
        db = get_db()
        trip = db.execute("SELECT * FROM trips WHERE status = 'ACTIVE'").fetchone()
        with db:
            monitor_route(db, {"vehicle_id":"FM01", "lat":17.8, "lon":78.8}, trip)
        trip = db.execute("SELECT * FROM trips WHERE status = 'ACTIVE'").fetchone()
        with db:
            monitor_route(db, {"vehicle_id":"FM01", **review["start"]}, trip)
    assert not [n for n in client.get("/api/notifications").json["notifications"] if n["kind"] == "ROUTE_DEVIATION"]


def test_reroute_failure_keeps_original_then_demo_acceptance(app, client, review):
    start(client, review)
    client.post("/api/simulation/scenario", json={"action": "deviation"})
    advance(app, 4)
    assert client.post("/api/routes/reroute", json={}).status_code == 503
    assert client.get("/api/trips/current").json["trip"]["route_id"] == review["route_id"]
    proposed = client.post("/api/routes/reroute", json={"demo_fallback":True}).json["routes"][0]
    assert client.post("/api/routes/accept", json={"route_id":proposed["route_id"]}).status_code == 200
    data = client.get("/api/dashboard").json
    assert data["vehicle"]["trip"]["route_status"] == "ON_ROUTE"
    assert data["vehicle"]["trip"]["route_id"] == proposed["route_id"]
    client.post("/api/simulation/resume")
    advance(app, 25)
    assert client.get("/api/dashboard").json["last_trip"]["reroute_count"] == 1


def test_stale_recovery_no_spam(app, client, review):
    start(client, review, scenario="connectivity")
    with app.app_context():
        db = get_db()
        old = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        with db:
            db.execute("UPDATE locations SET timestamp = ?", (old,))
    assert client.get("/api/dashboard").json["vehicle"]["stale"] is True
    client.get("/api/dashboard")
    assert len([n for n in client.get("/api/notifications").json["notifications"] if n["kind"] == "TELEMETRY_LOST"]) == 1
    advance(app, .5)
    assert client.get("/api/dashboard").json["vehicle"]["stale"] is False
    assert len([n for n in client.get("/api/notifications").json["notifications"] if n["kind"] == "TELEMETRY_RESTORED"]) == 1


def test_connectivity_interruption_holds_position(app, client, review):
    start(client, review)
    client.post("/api/simulation/scenario", json={"action":"connectivity"})
    advance(app, 4)
    data = client.get("/api/simulation/status").json["simulation"]
    assert data["position_m"] == 0 and data["outage_remaining_s"] == 4
    advance(app, 4)
    advance(app, 1)
    assert client.get("/api/simulation/status").json["simulation"]["position_m"] > 0


def test_scripted_speed_changes_once(app, client, review):
    start(client, review, scenario="speed")
    advance(app, 6)
    assert client.get("/api/simulation/status").json["simulation"]["speed_kmh"] == 20
    assert len([e for e in client.get("/api/events?limit=100").json["events"] if e["kind"] == "SPEED_CHANGED"]) == 1


def test_restart_pauses_simulation_without_losing_position(app, client, review):
    from app import create_app
    start(client, review)
    advance(app, 1)
    before = client.get("/api/simulation/status").json["simulation"]["position_m"]
    new_app = create_app({"TESTING":True,"DATABASE":app.config["DATABASE"],"ROUTING_ENABLED":False,"SIMULATION_AUTORUN":False})
    session = new_app.test_client().get("/api/simulation/status").json["simulation"]
    assert session["state"] == "PAUSED" and session["position_m"] == before


def test_geometry_interpolation_and_projection(review):
    encoded = json.dumps(review["geometry"])
    total = prepare(encoded)[1][-1]
    lat, lon, _ = point_at(encoded, total * .5)
    result = project(encoded, lat, lon)
    assert result["distance_m"] < .01
    assert result["along_m"] == pytest.approx(total * .5, abs=.1)
