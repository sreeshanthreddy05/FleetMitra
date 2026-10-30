from contextlib import contextmanager
import json
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen

from werkzeug.serving import make_server

from simulator.gps_simulator import simulate


@contextmanager
def live_server(app):
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def http_json(url, path, data=None):
    request = Request(url + path, data=json.dumps(data).encode() if data is not None else None,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def test_full_route_through_real_http(app, reading, monkeypatch):
    """Exercise simulator -> actual HTTP -> Flask -> SQLite -> every downstream API."""
    data = json.loads((Path(__file__).parents[1] / "simulator/sample_route.json").read_text())
    monkeypatch.setattr("simulator.gps_simulator.time.sleep", lambda _: None)
    with live_server(app) as url:
        assert http_json(url, "/api/health")["status"] == "ok"
        http_json(url, "/api/locations", reading())
        http_json(url, "/api/geofences", data["geofence"])
        http_json(url, "/api/trips/start", {"vehicle_id": "FM01",
            "destination_lat": data["destination"]["lat"],
            "destination_lon": data["destination"]["lon"],
            "destination_label": data["destination"]["label"]})
        assert simulate(url, data["points"], interval=3) == 0
        snapshot = http_json(url, "/api/vehicles/FM01/location")
        assert snapshot["location"]["source"] == "SIMULATED"
        assert snapshot["eta"]["status"] == "ARRIVED"
        assert snapshot['trip'] is None  # Arrival closes the trip without a manual stop.
        completed = http_json(url, '/api/trips/history')['trips']
        assert len(completed) == 1
        assert completed[0]['distance_m'] > 1500
        assert completed[0]['completion_status'] == 'ARRIVED'
        assert completed[0]['progress_percent'] == 100
        events = http_json(url, "/api/geofences/events")["events"]
        assert [event["event_type"] for event in events] == ["EXIT", "ENTER"]
        assert len(http_json(url, "/api/vehicles/FM01/history?limit=500")["locations"]) == len(data["points"]) + 1
        assert http_json(url, '/api/trips/current')['trip'] is None
        assert len(http_json(url, "/api/trips/history")["trips"]) == 1


def test_simulator_retries_identical_reading(monkeypatch):
    attempts = []
    def send(url, payload):
        attempts.append(payload.copy())
        if len(attempts) == 1:
            raise OSError("Connection lost")
        return 200, {"accepted": True, "duplicate": True, "vehicle": {"eta": None}}
    monkeypatch.setattr("simulator.gps_simulator.send_reading", send)
    monkeypatch.setattr("simulator.gps_simulator.time.sleep", lambda _: None)
    assert simulate("http://localhost", [{"lat": 17, "lon": 78}, {"lat": 17.1, "lon": 78.1}], max_points=1) == 0
    assert attempts[0] == attempts[1]


def test_dashboard_assets_and_presets(client):
    html = client.get("/")
    assert html.status_code == 200 and b"FleetMitra" in html.data
    for path in ["css/style.css", "js/app.js", "js/map.js", "vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css"]:
        response = client.get("/static/" + path)
        assert response.status_code == 200
        response.close()
    assert client.get("/api/demo-config").json["geofence"]["radius_m"] == 100
