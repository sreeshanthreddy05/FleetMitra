"""Persistent driver/destination regression checks. All identities and routes are fictional."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest

from app import create_app
from database import get_db


def driver(client,**changes):
    data={'full_name':'Sample Driver Alpha','is_sample':True,'phone':'0000000000',
          'email':'driver@example.invalid','license_number':'DEMO-LIC-0001','license_expiry':'2099-01-01',
          'experience_years':2,'date_of_birth':'1995-01-01'}|changes
    result=client.post('/api/drivers',json=data)
    assert result.status_code==201,result.json
    return result.json['driver']


def begin(app,client):
    app.config['SIMULATION_AUTORUN']=False
    d=driver(client)
    assert client.put(f"/api/drivers/{d['driver_id']}/vehicle",json={'vehicle_id':'FM01'}).status_code==200
    route=client.post('/api/routes',json={'demo_id':'quick-review'}).json['routes'][0]
    result=client.post('/api/simulation/start',json={'route_id':route['route_id'],'driver_id':d['driver_id'],
                'speed_kmh':40,'multiplier':4,'start_label':'Original start','destination_label':'Original destination','auto_reroute':True})
    assert result.status_code==201,result.json
    return result.json['simulation']['trip_id'],d,route


def road_provider(app,monkeypatch):
    def routes(lat,lon,dlat,dlon,**kwargs):
        return [{'geometry':{'type':'LineString','coordinates':[[lon,lat],[dlon,lat],[dlon,dlat]]},'duration_seconds':120}]
    monkeypatch.setattr(app.extensions['routing'],'options',routes)


def propose(client,trip,lat=17.425,lon=78.49,label='Updated destination'):
    result=client.post(f'/api/trips/{trip}/destination-options',json={'lat':lat,'lon':lon,'label':label})
    assert result.status_code==200,result.json
    return result.json


def apply(client,trip,proposal):
    return client.post(f'/api/trips/{trip}/destination',json={'proposal_id':proposal['proposal_id'],
                        'route_id':proposal['recommended_route_id']})


def test_driver_registration_encryption_masking_and_profile(client,app):
    d=driver(client);identity=d['driver_id']
    assert identity.startswith('DR-') and d['status']=='Available' and not d['eligible']
    assert d['phone_mask']=='••••0000' and d['license_mask']=='••••0001'
    public=client.get('/api/drivers').get_data(as_text=True)
    assert 'DEMO-LIC-0001' not in public and 'driver@example.invalid' not in public and '0000000000' not in public
    with app.app_context():
        encrypted=get_db().execute('SELECT private_encrypted FROM drivers WHERE driver_id=?',(identity,)).fetchone()[0]
        assert 'DEMO-LIC-0001' not in encrypted and '1995' not in encrypted
    profile=client.get(f'/api/drivers/{identity}/profile').json['driver']
    assert profile['license_number']=='DEMO-LIC-0001' and profile['age']==date.today().year-1995


@pytest.mark.parametrize('changes',[
    {'full_name':''},{'date_of_birth':'not-a-date'},{'date_of_birth':'2099-01-01'},
    {'date_of_birth':'1900-01-01'},{'phone':'abc'},{'phone':'12'},{'email':'wrong'},
    {'experience_years':-1},{'experience_years':100},{'experience_years':70},
    {'license_expiry':''},{'license_expiry':'bad-date'},{'date_joined':'2099-01-01'},
    {'driver_id':'injected'},{'is_active':'yes'},{'gender':'invalid'},
    {'age':12},{'date_joined':'2000-01-01'},{'phone':0}])
def test_driver_validation(client,changes):
    data={'full_name':'Sample Driver','date_of_birth':'1995-01-01','license_number':'DEMO-0001','license_expiry':'2099-01-01'}|changes
    assert client.post('/api/drivers',json=data).status_code==400
    assert client.get('/api/drivers').json['drivers']==[]


def test_profile_edit_assignment_conflicts_and_status(app,client):
    first=driver(client);second=driver(client,full_name='Sample Driver Beta')
    first_id=first['driver_id'];second_id=second['driver_id']
    assert client.put(f'/api/drivers/{first_id}/vehicle',json={'vehicle_id':'FM01'}).status_code==200
    assert client.put(f'/api/drivers/{second_id}/vehicle',json={'vehicle_id':'FM01'}).status_code==409
    assert client.put(f'/api/drivers/{first_id}/vehicle',json={'vehicle_id':None}).status_code==200
    assert client.put(f'/api/drivers/{second_id}/vehicle',json={'vehicle_id':'FM01'}).status_code==200
    assert client.patch(f'/api/drivers/{first_id}',json={'full_name':'Sample Renamed','phone':'0000000001'}).status_code==200
    assert client.get(f'/api/drivers/{first_id}/profile').json['driver']['phone']=='0000000001'
    assert client.patch(f'/api/drivers/{first_id}',json={'is_active':False}).json['driver']['status']=='Inactive'
    assert len(client.get('/api/drivers?status=Inactive').json['drivers'])==1
    assert len(client.get('/api/drivers?q=Renamed').json['drivers'])==1


def test_driver_selection_lifecycle_snapshot_statistics_and_export(app,client):
    trip,d,route=begin(app,client);identity=d['driver_id']
    assert client.get(f'/api/drivers/{identity}').json['driver']['status']=='On Trip'
    assert client.put(f'/api/drivers/{identity}/vehicle',json={'vehicle_id':None}).status_code==409
    assert client.post('/api/simulation/start',json={'route_id':route['route_id'],'driver_id':identity}).status_code==409
    client.patch(f'/api/drivers/{identity}',json={'full_name':'Sample Edited Later','is_active':False})
    with app.app_context():app.extensions['simulation'].advance(100)
    saved=client.get(f'/api/trips/{trip}').json['trip']
    assert saved['driver_name']=='Sample Driver Alpha' and saved['driver_id']==identity
    assert saved['lifecycle_status']=='COMPLETED'
    details=client.get(f'/api/drivers/{identity}').json['driver']
    assert details['status']=='Inactive'
    assert details['statistics']['completed_trips']==1 and details['statistics']['total_trips']==1
    assert details['statistics']['total_distance_m']==saved['distance_m']
    assert details['statistics']['maximum_recorded_speed_kmh']==40
    exported=client.get(f'/api/trips/{trip}/export.json').get_data(as_text=True)
    assert 'Sample Driver Alpha' in exported and 'DEMO-LIC-0001' not in exported and 'driver@example.invalid' not in exported
    assert client.get('/api/trip-records?driver='+identity).json['total']==1


@pytest.mark.parametrize('issue',['missing','unassigned','inactive','expired'])
def test_ineligible_driver_cannot_start(app,client,issue):
    app.config['SIMULATION_AUTORUN']=False
    d=driver(client,license_expiry='2001-01-01' if issue=='expired' else '2099-01-01')
    if issue!='unassigned':client.put(f"/api/drivers/{d['driver_id']}/vehicle",json={'vehicle_id':'FM01'})
    if issue=='inactive':client.patch(f"/api/drivers/{d['driver_id']}",json={'is_active':False})
    route=client.post('/api/routes',json={'demo_id':'quick-review'}).json['routes'][0]
    response=client.post('/api/simulation/start',json={'route_id':route['route_id'],'driver_id':None if issue=='missing' else d['driver_id']})
    assert response.status_code==409
    assert client.get('/api/trip-records').json['total']==0


def test_legacy_unassigned_trip_remains_valid(app,client,reading,destination):
    client.post('/api/locations',json=reading())
    old=client.post('/api/trips/start',json=destination).json['trip']['trip_id']
    client.post('/api/trips/stop',json={'vehicle_id':'FM01'})
    driver(client)
    assert client.get(f'/api/trips/{old}').json['trip']['driver_id'] is None
    assert client.get('/api/trip-records?driver=unassigned').json['total']==1


@pytest.mark.parametrize('paused',[False,True])
def test_destination_change_keeps_trip_driver_clock_distance_and_camera_data(app,client,monkeypatch,paused):
    trip,d,route=begin(app,client);road_provider(app,monkeypatch)
    with app.app_context():app.extensions['simulation'].advance(1)
    if paused:client.post('/api/simulation/pause')
    before=client.get(f'/api/trips/{trip}').json
    session=client.get('/api/simulation/status').json['simulation']
    proposal=propose(client,trip)
    assert client.get(f'/api/trips/{trip}').json==before  # Planning/cancel/refresh cannot change the trip.
    assert apply(client,trip,proposal).status_code==200
    after=client.get(f'/api/trips/{trip}').json
    for field in ('trip_id','driver_id','driver_name','start_time','start_lat','start_lon','distance_m','elapsed_seconds','maximum_speed_kmh'):
        assert after['trip'][field]==before['trip'][field]
    state=client.get('/api/simulation/status').json['simulation']
    for field in ('state','speed_kmh','multiplier','elapsed_seconds'):assert state[field]==session[field]
    assert state['position_m']<100 and after['locations']==before['locations']
    assert after['trip']['destination_label']=='Updated destination'
    assert after['trip']['original_destination']['label']=='Original destination'
    assert len(after['route_versions'])==2 and after['route_versions'][1]['reason']=='DESTINATION_CHANGED'
    event=next(e for e in after['events'] if e['kind']=='DESTINATION_CHANGED')
    assert event['details']['new_destination']['label']=='Updated destination'
    assert event['details']['distance_travelled_m']==before['trip']['distance_m']
    assert apply(client,trip,proposal).json['duplicate'] is True
    assert client.get('/api/trip-records').json['total']==1


def test_multiple_changes_restart_arrival_and_driver_recovery(app,client,monkeypatch):
    trip,d,_=begin(app,client);road_provider(app,monkeypatch)
    for lat,lon,label in [(17.425,78.49,'Second destination'),(17.415666,78.573060,'Home')]:
        assert apply(client,trip,propose(client,trip,lat,lon,label)).status_code==200
    before=client.get(f'/api/trips/{trip}').json
    restarted=create_app({'TESTING':True,'DATABASE':app.config['DATABASE'],'SIMULATION_AUTORUN':False,'ROUTING_ENABLED':False})
    other=restarted.test_client()
    assert other.get('/api/simulation/status').json['simulation']['state']=='PAUSED'
    assert other.get(f"/api/drivers/{d['driver_id']}").json['driver']['status']=='On Trip'
    assert other.get(f"/api/drivers/{d['driver_id']}/profile").json['driver']['license_number']=='DEMO-LIC-0001'
    assert other.get(f'/api/trips/{trip}').json==before
    other.post('/api/simulation/resume')
    with restarted.app_context():restarted.extensions['simulation'].advance(10000)
    # advance caps one call at 30 seconds, so complete with bounded repeated advances.
    with restarted.app_context():
        for _ in range(20):restarted.extensions['simulation'].advance(30)
    final=other.get(f'/api/trips/{trip}').json
    assert final['trip']['lifecycle_status']=='COMPLETED' and final['trip']['destination_label']=='Home'
    assert final['trip']['destination_change_count']==2
    assert final['trip']['driver_id']==d['driver_id']
    assert other.get(f"/api/drivers/{d['driver_id']}").json['driver']['status']=='Available'


def test_same_nearby_failure_and_stale_route_options_preserve_trip(app,client,monkeypatch):
    trip,_,route=begin(app,client);road_provider(app,monkeypatch)
    before=client.get(f'/api/trips/{trip}').json
    same=route['destination'];response=client.post(f'/api/trips/{trip}/destination-options',json=same)
    assert response.json['unchanged'] is True
    location=before['locations'][-1]
    assert client.post(f'/api/trips/{trip}/destination-options',json={'lat':location['lat'],'lon':location['lon']}).status_code==400
    monkeypatch.setattr(app.extensions['routing'],'options',lambda *args,**kwargs:[])
    assert client.post(f'/api/trips/{trip}/destination-options',json={'lat':17.425,'lon':78.49}).status_code==503
    assert client.get(f'/api/trips/{trip}').json==before
    road_provider(app,monkeypatch);proposal=propose(client,trip)
    with app.app_context():app.extensions['simulation'].advance(3)
    assert apply(client,trip,proposal).status_code==409
    assert client.get(f'/api/trips/{trip}').json['trip']['destination_label']=='Original destination'
    assert apply(client,trip,propose(client,trip)).status_code==200


def test_concurrent_destination_requests_only_activate_one_revision(app,client,monkeypatch):
    trip,_,_=begin(app,client);road_provider(app,monkeypatch)
    proposals=[propose(client,trip,17.425,78.49,'First proposal'),propose(client,trip,17.426,78.491,'Second proposal')]
    def activate(proposal):
        with app.test_client() as concurrent:return apply(concurrent,trip,proposal).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(activate,proposals))
    assert sorted(results)==[200,409]
    saved=client.get(f'/api/trips/{trip}').json
    assert saved['trip']['destination_change_count']==1 and len(saved['route_versions'])==2


def test_deviation_after_destination_change_retains_new_destination(app,client,monkeypatch):
    trip,_,_=begin(app,client);road_provider(app,monkeypatch)
    assert apply(client,trip,propose(client,trip)).status_code==200
    client.post('/api/simulation/scenario',json={'action':'deviation'})
    with app.app_context():app.extensions['simulation'].advance(4)
    final=client.get(f'/api/trips/{trip}').json
    assert final['trip']['destination_label']=='Updated destination'
    assert final['trip']['reroute_count']==1 and final['trip']['deviation_count']==1
    assert final['trip']['destination_change_count']==1


def test_driver_page_and_privacy_exports(client):
    assert client.get('/drivers').status_code==200
    assert client.get('/api/drivers/not-found').status_code==404


def test_planning_does_not_hold_movement_lock(app,client,monkeypatch):
    trip,_,_=begin(app,client)
    entered=threading.Event();release=threading.Event()
    def provider(lat,lon,dlat,dlon,**kwargs):
        entered.set()
        assert release.wait(3)
        return [{'geometry':{'type':'LineString','coordinates':[[lon,lat],[dlon,dlat]]},'duration_seconds':90}]
    monkeypatch.setattr(app.extensions['routing'],'options',provider)
    def request_options():
        with app.test_client() as other:
            return other.post(f'/api/trips/{trip}/destination-options',json={'lat':17.425,'lon':78.49}).status_code
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(request_options)
        assert entered.wait(3)
        try:
            with app.app_context():app.extensions['simulation'].advance(1)
            assert client.get(f'/api/trips/{trip}').json['trip']['elapsed_seconds']>0
        finally:release.set()
        assert pending.result(timeout=5)==200


def test_stopping_releases_driver_and_expired_proposal_preserves_state(app,client,monkeypatch):
    trip,d,_=begin(app,client);road_provider(app,monkeypatch)
    proposal=propose(client,trip)
    with app.app_context(),get_db():
        get_db().execute("UPDATE destination_proposals SET created_at='2000-01-01T00:00:00Z' WHERE proposal_id=?",(proposal['proposal_id'],))
    assert apply(client,trip,proposal).status_code==409
    assert client.get(f'/api/trips/{trip}').json['trip']['destination_change_count']==0
    client.post('/api/simulation/stop')
    assert client.get(f"/api/drivers/{d['driver_id']}").json['driver']['status']=='Available'


def test_proposals_reject_foreign_routes_and_finished_trip(app,client,monkeypatch):
    trip,_,route=begin(app,client);road_provider(app,monkeypatch)
    proposal=propose(client,trip)
    wrong=client.post(f'/api/trips/{trip}/destination',json={'proposal_id':proposal['proposal_id'],'route_id':route['route_id']})
    assert wrong.status_code==400
    client.post('/api/simulation/stop')
    assert apply(client,trip,proposal).status_code==409


def test_destination_options_request_tight_origin_snapping(app,client,monkeypatch):
    from io import BytesIO
    trip,_,_=begin(app,client);app.config['ROUTING_ENABLED']=True;calls=[]
    def provider(url,**kwargs):
        calls.append(url)
        return BytesIO(json.dumps({'code':'Ok','routes':[{'distance':1000,'duration':100,
            'geometry':{'type':'LineString','coordinates':[[78.48,17.41],[78.49,17.425]]}}]}).encode())
    monkeypatch.setattr('services.routing_service.urlopen',provider)
    propose(client,trip)
    assert 'radiuses=10;150' in calls[0]
    assert 'snapping=any' in calls[0]


def test_same_requested_home_after_road_snapping_and_reroute_is_noop(app,client,monkeypatch):
    trip,_,_=begin(app,client)
    def snapped(lat,lon,dlat,dlon,**kwargs):
        return [{'geometry':{'type':'LineString','coordinates':[[lon,lat],[dlon,dlat+.00003]]},'duration_seconds':100}]
    monkeypatch.setattr(app.extensions['routing'],'options',snapped)
    assert apply(client,trip,propose(client,trip,17.415666,78.573060,'Home')).status_code==200
    replacement=client.post('/api/routes/reroute',json={}).json['routes'][0]
    assert client.post('/api/routes/accept',json={'route_id':replacement['route_id']}).status_code==200
    before=client.get(f'/api/trips/{trip}').json
    response=client.post(f'/api/trips/{trip}/destination-options',json={'lat':17.415666,'lon':78.573060,'label':'Home'})
    assert response.json['unchanged'] is True
    assert client.get(f'/api/trips/{trip}').json==before
