from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

import pytest

from app import create_app


def test_empty_database(client):
    assert client.get("/api/health").json == {"status": "ok", "database": "connected"}
    assert client.get("/api/vehicles").json["vehicles"][0]["vehicle_id"] == "FM01"
    assert client.get("/api/vehicles/FM01/location").json["location"] is None
    assert client.get("/api/vehicles/FM01/history").json["locations"] == []


def test_valid_latest_and_history(client, reading):
    assert client.post("/api/locations", json=reading()).status_code == 201
    assert client.post("/api/locations", json=reading(3, lat=17.4126)).status_code == 201
    latest = client.get("/api/vehicles/FM01/location").json
    assert latest["location"]["lat"] == 17.4126
    assert latest["location"]["source"] == "SIMULATED"
    assert latest["location"]["gps_valid"] is True
    rows = client.get("/api/vehicles/FM01/history?limit=1").json["locations"]
    assert len(rows) == 1 and rows[0]["lat"] == 17.4126


@pytest.mark.parametrize("changes", [{"lat": 91}, {"lon": -181}, {"lat": True}, {"lat": "17"},
    {"lat": float("nan")}, {"lat": 10**400}, {"gps_valid": False}, {"gps_valid": 1},
    {"speed_kmh": -1}, {"speed_kmh": 201}, {"speed_kmh": "30"}, {"source": "DEMO"},
    {"source": None}, {"timestamp": "nope"}, {"timestamp": "2026-01-01T10:00:00"},
    {"timestamp": "2026-02-30T00:00:00Z"}])
def test_invalid_location(client, reading, changes):
    response = client.post("/api/locations", json=reading(**changes))
    assert response.status_code == 400
    assert "error" in response.json
    assert client.get("/api/vehicles/FM01/history").json["locations"] == []


@pytest.mark.parametrize("field", ["vehicle_id", "lat", "lon", "timestamp", "gps_valid", "source"])
def test_missing_field(client, reading, field):
    payload = reading()
    del payload[field]
    assert client.post("/api/locations", json=payload).status_code == 400


@pytest.mark.parametrize("body", ["{", "null", "[]", '"text"'])
def test_malformed_json(client, body):
    response = client.post("/api/locations", data=body, content_type="application/json")
    assert response.status_code == 400
    assert "error" in response.json


def test_unknown_vehicle(client, reading):
    assert client.post("/api/locations", json=reading(vehicle_id="FM02")).status_code == 404
    assert client.get("/api/vehicles/UNKNOWN/location").status_code == 404


def test_duplicate_and_timestamp_conflict(client, reading):
    payload = reading()
    client.post("/api/locations", json=payload)
    duplicate = client.post("/api/locations", json=payload)
    assert duplicate.status_code == 200 and duplicate.json["duplicate"] is True
    assert client.post("/api/locations", json=reading(lat=18)).status_code == 409
    assert client.post("/api/locations", json=reading(-3)).status_code == 409
    assert len(client.get("/api/vehicles/FM01/history").json["locations"]) == 1


def test_timezone_normalized_duplicate(client, reading):
    data = reading()
    client.post("/api/locations", json=data)
    stamp = datetime.fromisoformat(data["timestamp"]).astimezone(timezone(timedelta(hours=5, minutes=30)))
    data["timestamp"] = stamp.isoformat()
    assert client.post("/api/locations", json=data).json["duplicate"] is True


def test_missing_speed_is_derived(client, reading):
    first = reading()
    first.pop("speed_kmh")
    assert client.post("/api/locations", json=first).json["vehicle"]["location"]["speed_kmh"] == 0
    data = reading(10, lat=17.4134, speed_kmh=None)
    response = client.post("/api/locations", json=data)
    assert response.status_code == 201
    assert response.json["vehicle"]["location"]["speed_kmh"] == pytest.approx(40.03, abs=.1)
    assert client.post("/api/locations", json=reading(11, lat=18, speed_kmh=None)).status_code == 400


def test_future_timestamp(client, reading):
    stamp = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert client.post("/api/locations", json=reading(timestamp=stamp)).status_code == 400


@pytest.mark.parametrize("limit", ["0", "501", "-1", "foo", "2.5"])
def test_invalid_limit(client, limit):
    assert client.get(f"/api/vehicles/FM01/history?limit={limit}").status_code == 400


def test_persistence(app, client, reading):
    client.post("/api/locations", json=reading(source="HARDWARE"))
    restarted = create_app({"TESTING": True, "DATABASE": app.config["DATABASE"], "ROUTING_ENABLED": False})
    assert restarted.test_client().get("/api/vehicles/FM01/location").json["location"]["source"] == "HARDWARE"


def test_concurrent_retries_only_insert_once(app, reading):
    payload = reading()
    def send(_):
        with app.test_client() as client:
            return client.post("/api/locations", json=payload).status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = list(pool.map(send, range(8)))
    assert codes.count(201) == 1
    assert codes.count(200) == 7


def test_stale_location(app, client, reading):
    app.config["STALE_AFTER_SECONDS"] = 30
    client.post("/api/locations", json=reading())
    assert client.get("/api/vehicles/FM01/location").json["stale"] is True
