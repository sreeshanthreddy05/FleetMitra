import pytest

from app import create_app


def create_fence(client, **changes):
    data = {"name": "College Zone", "center_lat": 17.4134, "center_lon": 78.4767, "radius_m": 50}
    data.update(changes)
    return client.post("/api/geofences", json=data)


def test_transitions(client, reading, destination):
    assert create_fence(client).status_code == 201
    assert client.get("/api/geofences/status").json["geofences"][0]["status"] == "WAITING_FOR_GPS"
    for second, lat, event_count in [(0, 17.4124, 0), (3, 17.4125, 0),
                                     (12, 17.4134, 1), (15, 17.4135, 1), (24, 17.4144, 2)]:
        assert client.post("/api/locations", json=reading(second, lat=lat)).status_code == 201
        events = client.get("/api/geofences/events").json["events"]
        assert len(events) == event_count
        if second == 0:
            client.post("/api/trips/start", json=destination)
    assert [event["event_type"] for event in events] == ["EXIT", "ENTER"]
    assert all(event["trip_id"] is not None for event in events)
    assert client.get("/api/geofences/status").json["geofences"][0]["status"] == "OUTSIDE"
    client.post("/api/locations", json=reading(24, lat=17.4144))
    assert len(client.get("/api/geofences/events").json["events"]) == 2


def test_first_inside_no_fake_enter(client, reading):
    create_fence(client)
    client.post("/api/locations", json=reading(lat=17.4134))
    assert client.get("/api/geofences/status").json["geofences"][0]["status"] == "INSIDE"
    assert client.get("/api/geofences/events").json["events"] == []


def test_created_after_location_and_delete(client, reading):
    client.post("/api/locations", json=reading(lat=17.4134))
    fence_id = create_fence(client).json["geofence"]["geofence_id"]
    client.post("/api/locations", json=reading(30, lat=17.415))
    assert client.get("/api/geofences/events").json["events"][0]["event_type"] == "EXIT"
    assert client.delete(f"/api/geofences/{fence_id}").status_code == 200
    assert client.get("/api/geofences").json["geofences"] == []
    assert client.get("/api/geofences/events").json["events"] == []
    assert client.delete(f"/api/geofences/{fence_id}").status_code == 404


@pytest.mark.parametrize("changes", [{"radius_m": 0}, {"radius_m": -10}, {"radius_m": "50"},
    {"center_lat": 100}, {"center_lon": None}, {"name": ""}, {"enabled": "true"}])
def test_invalid_geofence(client, changes):
    assert create_fence(client, **changes).status_code == 400


def test_disabled_geofence(client, reading):
    create_fence(client, enabled=False)
    client.post("/api/locations", json=reading())
    client.post("/api/locations", json=reading(30, lat=17.4134))
    assert client.get("/api/geofences/status").json["geofences"][0]["status"] == "DISABLED"
    assert client.get("/api/geofences/events").json["events"] == []


def test_state_survives_restart(app, client, reading):
    create_fence(client)
    client.post("/api/locations", json=reading())
    restarted = create_app({"TESTING": True, "DATABASE": app.config["DATABASE"], "ROUTING_ENABLED": False})
    other = restarted.test_client()
    other.post("/api/locations", json=reading(30, lat=17.4134))
    assert other.get("/api/geofences/events").json["events"][0]["event_type"] == "ENTER"
