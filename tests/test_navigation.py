"""Navigation regression tests; external routes are deterministic provider mocks."""
import json
from io import BytesIO

import pytest

from app import create_app
from services.traffic_service import simulated_traffic
from services.route_planner import distinct_routes

HOME = {"lat":17.415666,"lon":78.573060}


def provider_route(points, duration=120):
    return {"geometry":{"type":"LineString","coordinates":points},"duration":duration,"distance":1000}


def test_home_persists_without_setting_an_origin(app, client):
    assert client.get('/api/config').json['saved_places'][0] == {"id":"home","name":"Home",**HOME}
    new = create_app({"TESTING":True,"DATABASE":app.config['DATABASE'],"ROUTING_ENABLED":False})
    assert new.test_client().get('/api/config').json['saved_places'][0]['lon'] == 78.573060
    assert client.get('/api/trips/current').json['trip'] is None
    assert client.get('/api/vehicles/FM01/location').json['location'] is None


@pytest.mark.parametrize('reverse',[False,True])
def test_home_origin_or_destination_routes_simulation_and_arrival(app, client, monkeypatch, reverse):
    app.config.update(ROUTING_ENABLED=True,SIMULATION_AUTORUN=False)
    points=[[HOME['lon'],HOME['lat']],[HOME['lon']+.002,HOME['lat']+.002]]
    if reverse: points.reverse()
    monkeypatch.setattr('services.routing_service.urlopen',lambda *a,**k:BytesIO(json.dumps({'code':'Ok','routes':[provider_route(points)]}).encode()))
    result=client.post('/api/routes',json={'start_lat':points[0][1],'start_lon':points[0][0],
        'destination_lat':points[-1][1],'destination_lon':points[-1][0]}).json
    route=result['routes'][0]
    assert route['requested_destination' if reverse else 'requested_start'] == HOME
    assert route['traffic']['label'] == 'SIMULATED TRAFFIC'
    assert client.post('/api/simulation/start',json={'route_id':route['route_id'],'speed_kmh':40,'multiplier':8}).status_code==201
    with app.app_context(): app.extensions['simulation'].advance(10)
    assert client.get('/api/dashboard').json['last_trip']['status']=='ARRIVED'


def test_identical_and_near_identical_routes_filtered():
    def route(points):return {'geometry':{'type':'LineString','coordinates':points}}
    a=route([[78,17],[78.01,17.01]])
    nearby=route([[78,17],[78.00501,17.005],[78.01,17.01]])
    different=route([[78,17],[78.01,17],[78.01,17.01]])
    assert len(distinct_routes([a,a,nearby,different]))==2


def test_three_genuine_alternatives_traffic_stability_and_refresh(app,client,monkeypatch):
    app.config['ROUTING_ENABLED']=True
    routes=[provider_route([[78,17],[78.003,17.007],[78.01,17.01]],100),
            provider_route([[78,17],[78.01,17],[78.01,17.01]],110),
            provider_route([[78,17],[78,17.01],[78.01,17.01]],120)]
    monkeypatch.setattr('services.routing_service.urlopen',lambda *a,**k:BytesIO(json.dumps({'code':'Ok','routes':routes+routes[:1]}).encode()))
    result=client.post('/api/routes',json={'start_lat':17,'start_lon':78,'destination_lat':17.01,'destination_lon':78.01}).json
    assert len(result['routes'])==3
    assert result['recommended_route_id']==min(result['routes'],key=lambda r:r['traffic']['adjusted_duration_seconds'])['route_id']
    from services.route_planner import route_by_id
    with app.app_context():
        assert route_by_id(__import__('database').get_db(),result['routes'][0]['route_id'])['traffic']==result['routes'][0]['traffic']
    refreshed=client.post('/api/routes/traffic',json={'route_ids':[r['route_id'] for r in result['routes']]}).json
    assert refreshed['routes'][0]['traffic']['seed'] != result['routes'][0]['traffic']['seed']


def test_traffic_formula_reproducible():
    geometry={'type':'LineString','coordinates':[[78,17],[78.01,17.01]]}
    a=simulated_traffic(geometry,100,'seed')
    assert a==simulated_traffic(geometry,100,'seed')
    assert a['adjusted_duration_seconds']==100+a['delay_seconds']
    assert a['delay_seconds'] in [5,25,60]


def test_dashboard_has_home_and_no_scenario_picker(client):
    html=client.get('/').get_data(as_text=True)
    assert 'home-start' in html and 'home-destination' in html and 'home-center' in html
    assert 'demo-scenario' not in html and 'load-demo' not in html
    assert 'place-search' in html


def test_home_trip_automatic_reroute_keeps_destination(app,client,monkeypatch):
    app.config['SIMULATION_AUTORUN']=False
    def options(lat,lon,dlat,dlon):
        return [{'geometry':{'type':'LineString','coordinates':[[lon,lat],[dlon,dlat]]},'duration_seconds':120,'distance_m':1000}]
    monkeypatch.setattr(app.extensions['routing'],'options',options)
    route=client.post('/api/routes',json={'start_lat':HOME['lat'],'start_lon':HOME['lon'],
        'destination_lat':17.425666,'destination_lon':78.583060}).json['routes'][0]
    client.post('/api/simulation/start',json={'route_id':route['route_id'],'speed_kmh':40,'multiplier':8,'auto_reroute':True})
    client.post('/api/simulation/scenario',json={'action':'deviation'})
    with app.app_context():app.extensions['simulation'].advance(4)
    data=client.get('/api/dashboard').json
    assert data['vehicle']['trip']['route_id']!=route['route_id']
    assert data['vehicle']['trip']['destination_lat']==17.425666
    assert data['vehicle']['trip']['destination_lon']==78.583060
    assert data['simulation']['flags']['auto_reroute'] is True
