from io import BytesIO
import json
from urllib.error import URLError

import pytest


REQUEST = {"start_lat":17,"start_lon":78,"destination_lat":17.01,"destination_lon":78.01}


def test_route_options_are_provider_options(app, client, monkeypatch):
    app.config["ROUTING_ENABLED"] = True
    route = {"distance":1500,"duration":180,"geometry":{"type":"LineString","coordinates":[[78,17],[78.01,17.01]]}}
    alternative = {**route,"duration":200,"geometry":{"type":"LineString","coordinates":[[78,17],[78.005,17],[78.01,17.01]]}}
    monkeypatch.setattr("services.routing_service.urlopen",lambda *a,**k: BytesIO(json.dumps({"code":"Ok","routes":[route,alternative]}).encode()))
    response = client.post("/api/routes",json=REQUEST)
    assert response.status_code == 201
    assert len(response.json["routes"]) == 2
    assert all(r["method"] == "ROAD_ROUTE" for r in response.json["routes"])


@pytest.mark.parametrize("payload", [None, [], {}, {"code":"NoRoute"}, {"code":"Ok","routes":[{}]},
    {"code":"Ok","routes":[{"distance":1,"duration":1,"geometry":{"type":"Point","coordinates":[78,17]}}]}])
def test_planning_malformed_or_no_route(app, client, monkeypatch, payload):
    app.config["ROUTING_ENABLED"] = True
    monkeypatch.setattr("services.routing_service.urlopen",lambda *a,**k: BytesIO(json.dumps(payload).encode()))
    assert client.post("/api/routes",json=REQUEST).status_code == 503


def test_provider_failure_and_explicit_fallback(app, client, monkeypatch):
    def fail(*a,**k): raise URLError("offline")
    app.config["ROUTING_ENABLED"] = True
    monkeypatch.setattr("services.routing_service.urlopen",fail)
    assert client.post("/api/routes",json=REQUEST).status_code == 503
    fallback = client.post("/api/routes",json={**REQUEST,"allow_fallback":True})
    assert fallback.status_code == 201 and fallback.json["routes"][0]["method"] == "FALLBACK"


def test_demo_routes_are_complete_and_available_offline(client):
    presets = client.get("/api/demo-routes").json["routes"]
    assert len(presets) >= 3
    for preset in presets:
        assert preset["expected_distance_m"] > 0 and preset["recommended_speed_kmh"] == 40
        route = client.post("/api/routes",json={"demo_id":preset["id"]}).json["routes"][0]
        assert route["method"] == "DEMO_ROUTE" and route["geometry"] == preset["geometry"]


@pytest.mark.parametrize("data", [{}, {**REQUEST,"start_lat":91}, {**REQUEST,"allow_fallback":"yes"},
                                 {**REQUEST,"destination_lat":17,"destination_lon":78}])
def test_invalid_planner_input(client,data):
    assert client.post("/api/routes",json=data).status_code == 400
