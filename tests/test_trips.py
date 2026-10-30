import pytest

from app import create_app


def test_no_location(client, destination):
    assert client.post("/api/trips/start", json=destination).status_code == 409
    assert client.get("/api/trips/current").json["trip"] is None
    assert client.post("/api/trips/stop", json={"vehicle_id": "FM01"}).status_code == 409


def test_trip_lifecycle(client, reading, destination):
    client.post("/api/locations", json=reading())
    start = client.post("/api/trips/start", json=destination)
    assert start.status_code == 201
    trip = start.json["trip"]
    assert trip["status"] == "ACTIVE" and trip["start_lat"] == 17.4124
    assert client.post("/api/trips/start", json=destination).status_code == 409
    data = reading(10, lat=17.4134)
    move = client.post("/api/locations", json=data)
    distance = move.json["vehicle"]["trip"]["distance_m"]
    assert distance == pytest.approx(111.195, abs=.01)
    client.post("/api/locations", json=data)  # A retry cannot add distance.
    assert client.get("/api/trips/current").json["trip"]["distance_m"] == distance
    assert move.json["vehicle"]["eta"]["status"] == "EN_ROUTE"
    assert move.json["vehicle"]["eta"]["method"] == "FALLBACK"
    stopped = client.post("/api/trips/stop", json={"vehicle_id": "FM01"})
    assert stopped.json["trip"]["status"] == "COMPLETED"
    assert stopped.json["trip"]["end_time"]
    client.post("/api/locations", json=reading(20, lat=17.4144))
    assert client.get("/api/trips/current").json["trip"] is None
    history = client.get("/api/trips/history").json["trips"]
    assert len(history) == 1 and history[0]["distance_m"] == distance
    assert client.get("/api/vehicles/FM01/history").json["locations"][0]["trip_id"] is None


def test_jitter_and_accumulated_small_moves(client, reading, destination):
    client.post("/api/locations", json=reading())
    client.post("/api/trips/start", json=destination)
    client.post("/api/locations", json=reading(3, lat=17.41241))
    assert client.get("/api/trips/current").json["trip"]["distance_m"] == 0
    for index in range(2, 7):
        client.post("/api/locations", json=reading(index * 3, lat=17.4124 + index * .00001))
    assert client.get("/api/trips/current").json["trip"]["distance_m"] >= 5


@pytest.mark.parametrize("changes", [{"destination_lat": None}, {"destination_lon": 181},
                                    {"destination_label": ""}, {"vehicle_id": "FM02"}])
def test_invalid_trip(client, reading, destination, changes):
    client.post("/api/locations", json=reading())
    destination.update(changes)
    assert client.post("/api/trips/start", json=destination).status_code in (400, 404)


def test_arrival_and_stationary(client, reading, destination):
    client.post("/api/locations", json=reading(speed_kmh=0))
    response = client.post("/api/trips/start", json=destination)
    assert response.json["trip"]["eta"]["status"] == "WAITING_FOR_MOVEMENT"
    arrived = client.post("/api/locations", json=reading(120, lat=destination["destination_lat"],
                         lon=destination["destination_lon"], speed_kmh=0))
    assert arrived.json["vehicle"]["eta"]["status"] == "ARRIVED"
    assert arrived.json["vehicle"]["eta"]["remaining_distance_m"] == 0


def test_trip_survives_restart(app, client, reading, destination):
    client.post("/api/locations", json=reading())
    trip_id = client.post("/api/trips/start", json=destination).json["trip"]["trip_id"]
    new_app = create_app({"TESTING": True, "DATABASE": app.config["DATABASE"], "ROUTING_ENABLED": False})
    assert new_app.test_client().get("/api/trips/current").json["trip"]["trip_id"] == trip_id
