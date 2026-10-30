import csv
from io import StringIO
import json

from app import create_app
from database import get_db


def begin(app,client,**changes):
    app.config['SIMULATION_AUTORUN']=False
    route=client.post('/api/routes',json={'demo_id':'quick-review'}).json['routes'][0]
    data={'route_id':route['route_id'],'speed_kmh':40,'multiplier':8,'start_label':'Home','destination_label':'College'}
    data.update(changes)
    response=client.post('/api/simulation/start',json=data)
    assert response.status_code==201
    return response.json['simulation']['trip_id'],route


def test_complete_history_survives_restart_new_trip_and_reset(app,client):
    trip_id,route=begin(app,client)
    with app.app_context():app.extensions['simulation'].advance(20)
    original=client.get(f'/api/trips/{trip_id}').json
    assert original['trip']['lifecycle_status']=='COMPLETED'
    assert original['trip']['start_label']=='Home'
    assert original['trip']['destination_label']=='College'
    assert original['trip']['initial_speed_kmh']==40 and original['trip']['initial_multiplier']==8
    assert original['route_versions'][0]['route']['geometry']==route['geometry']
    assert len(original['locations'])>10
    assert any(e['kind']=='DESTINATION_REACHED' for e in original['events'])
    client.post('/api/simulation/reset')
    second,_=begin(app,client)
    assert second!=trip_id
    client.post('/api/simulation/stop')
    restarted=create_app({'TESTING':True,'DATABASE':app.config['DATABASE'],'ROUTING_ENABLED':False,'SIMULATION_AUTORUN':False})
    after=restarted.test_client().get(f'/api/trips/{trip_id}').json
    assert after==original
    assert client.get('/api/trip-records?status=COMPLETED').json['total']==1
    assert client.get('/api/trip-records?status=STOPPED').json['total']==1


def test_stop_is_distinguished_and_pause_events_saved(app,client):
    trip_id,_=begin(app,client)
    client.post('/api/simulation/pause');client.post('/api/simulation/resume');client.post('/api/simulation/stop')
    data=client.get(f'/api/trips/{trip_id}').json
    assert data['trip']['status']=='STOPPED' and data['trip']['lifecycle_status']=='STOPPED'
    assert {'TRIP_STARTED','SIMULATION_PAUSED','SIMULATION_RUNNING','TRIP_STOPPED'}<=set(e['kind'] for e in data['events'])
    assert data['trip']['duration_seconds']==0


def test_immutable_route_and_traffic_snapshots(app,client):
    trip_id,route=begin(app,client)
    before=client.get(f'/api/trips/{trip_id}').json['route_versions']
    client.post('/api/routes/traffic',json={'route_ids':[route['route_id']]})
    assert client.get(f'/api/trips/{trip_id}').json['route_versions']==before
    client.post('/api/simulation/scenario',json={'action':'deviation'})
    with app.app_context():app.extensions['simulation'].advance(4)
    replacement=client.post('/api/routes/reroute',json={'demo_fallback':True}).json['routes'][0]
    client.post('/api/routes/accept',json={'route_id':replacement['route_id']})
    data=client.get(f'/api/trips/{trip_id}').json
    assert len(data['route_versions'])==2
    assert data['trip']['initial_route_id']==route['route_id']
    assert data['trip']['initial_route_distance_m']==route['distance_m']
    assert data['route']['route_id']==replacement['route_id']


def test_exports_include_real_positions_events_and_versions(app,client):
    trip_id,_=begin(app,client)
    with app.app_context():app.extensions['simulation'].advance(1)
    client.post('/api/simulation/stop')
    response=client.get(f'/api/trips/{trip_id}/export.csv')
    assert response.status_code==200 and 'attachment;' in response.headers['Content-Disposition']
    rows=list(csv.DictReader(StringIO(response.get_data(as_text=True))))
    assert {'trip','location','event','route_version'}==set(row['record_type'] for row in rows)
    assert json.loads(rows[0]['details_json'])['trip_id']==trip_id
    assert client.get(f'/api/trips/{trip_id}/export.json').json==client.get(f'/api/trips/{trip_id}').json
    assert client.get('/api/trips/999999/export.csv').status_code==404
    assert client.get(f'/api/trips/{trip_id}/export.xml').status_code==400


def test_history_filters_sort_pagination_validation(app,client):
    for i in range(3):
        begin(app,client,start_label=f'Origin {i}')
        with app.app_context():app.extensions['simulation'].advance(i+1)
        client.post('/api/simulation/stop')
    result=client.get('/api/trip-records?per_page=2&sort=id&direction=asc').json
    assert result['total']==3 and len(result['trips'])==2
    assert client.get('/api/trip-records?page=2&per_page=2').json['trips'][0]['start_label']=='Origin 0'
    assert client.get('/api/trip-records?q=Origin%201').json['total']==1
    assert client.get('/api/trip-records?deviations=true').json['total']==0
    assert client.get('/api/trip-records?from=2000-01-01&to=2099-01-01&vehicle=FM01').json['total']==3
    for query in ['page=0','per_page=101','from=oops','sort=drop','direction=sideways','status=INVALID']:
        assert client.get('/api/trip-records?'+query).status_code==400


def test_restart_active_trip_pauses_without_duplicate_creation(app,client):
    trip_id,_=begin(app,client)
    with app.app_context():app.extensions['simulation'].advance(1)
    before=client.get(f'/api/trips/{trip_id}').json
    restarted=create_app({'TESTING':True,'DATABASE':app.config['DATABASE'],'ROUTING_ENABLED':False,'SIMULATION_AUTORUN':False})
    other=restarted.test_client()
    assert other.get('/api/simulation/status').json['simulation']['state']=='PAUSED'
    assert other.get('/api/trip-records').json['total']==1
    assert other.get(f'/api/trips/{trip_id}').json['locations']==before['locations']
    assert other.get(f'/api/trips/{trip_id}').json['trip']['lifecycle_status']=='ACTIVE'


def test_history_pages_load(client):
    assert client.get('/history').status_code==200
    assert client.get('/history/1').status_code==200
