import json
import pytest
from io import BytesIO
from urllib.error import URLError

from services.routing_service import RoutingService


def test_routing_failure_falls_back_with_backoff(app, client, reading, destination, monkeypatch):
    calls = []
    def fail(*args, **kwargs):
        calls.append(args)
        raise URLError("offline")
    monkeypatch.setattr("services.routing_service.urlopen", fail)
    app.config["ROUTING_ENABLED"] = True
    client.post("/api/locations", json=reading())
    trip = client.post("/api/trips/start", json=destination).json["trip"]
    assert trip["eta"]["method"] == "FALLBACK"
    assert trip["eta"]["duration_seconds"] > 0
    client.get("/api/trips/current")
    assert len(calls) == 1


def test_successful_route_and_cache(app, monkeypatch):
    calls = []
    def route(*args, **kwargs):
        calls.append(args)
        return BytesIO(json.dumps({"code": "Ok", "routes": [{"distance": 1500, "duration": 180,
            "geometry": {"type": "LineString", "coordinates": [[78, 17], [78.1, 17.1]]}}]}).encode())
    monkeypatch.setattr("services.routing_service.urlopen", route)
    app.config["ROUTING_ENABLED"] = True
    service = RoutingService(app.config)
    result = service.route(17, 78, 17.1, 78.1)
    assert result["distance_m"] == 1500 and result["duration_seconds"] == 180
    assert service.route(17, 78, 17.1, 78.1) == result
    assert len(calls) == 1


def test_malformed_route_fallback(app, monkeypatch):
    monkeypatch.setattr("services.routing_service.urlopen", lambda *a, **k: BytesIO(b'{"code":"Ok","routes":[]}'))
    app.config["ROUTING_ENABLED"] = True
    assert RoutingService(app.config).route(17, 78, 17.1, 78.1) is None


@pytest.mark.parametrize("payload", [[], None, {"code": "Ok", "routes": [None]},
                                    {"code": "Ok", "routes": [{"distance": "nan", "duration": 2}]}])
def test_unexpected_routing_json(app, monkeypatch, payload):
    monkeypatch.setattr("services.routing_service.urlopen", lambda *a, **k: BytesIO(json.dumps(payload).encode()))
    app.config["ROUTING_ENABLED"] = True
    assert RoutingService(app.config).route(17, 78, 17.1, 78.1) is None


def test_bad_geometry_is_not_sent_to_map(app, monkeypatch):
    payload = {"code": "Ok", "routes": [{"distance": 1500, "duration": 180,
               "geometry": {"type": "LineString", "coordinates": [[999, 17], [78, 17]]}}]}
    monkeypatch.setattr("services.routing_service.urlopen", lambda *a, **k: BytesIO(json.dumps(payload).encode()))
    app.config["ROUTING_ENABLED"] = True
    result = RoutingService(app.config).route(17, 78, 17.1, 78.1)
    assert result["geometry"] is None and result["distance_m"] == 1500
