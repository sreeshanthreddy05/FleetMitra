from datetime import datetime, timezone, timedelta

from app import create_app
from database import get_db


def test_legacy_arrival_closes_trip_releases_vehicle_and_allows_driver(client, reading, destination):
    client.post('/api/locations', json=reading())
    trip = client.post('/api/trips/start', json=destination).json['trip']
    fix = reading(120, lat=destination['destination_lat'], lon=destination['destination_lon'])
    assert client.post('/api/locations', json=fix).json['vehicle']['trip'] is None
    record = client.get('/api/trips/'+str(trip['trip_id'])).json
    assert record['trip']['lifecycle_status'] == 'COMPLETED'
    assert record['trip']['completion_status'] == 'ARRIVED'
    assert record['trip']['progress_percent'] == 100
    client.post('/api/locations', json=fix)
    assert len([e for e in client.get('/api/trips/'+str(trip['trip_id'])).json['events'] if e['kind']=='DESTINATION_REACHED']) == 1
    driver = client.post('/api/drivers', json={'full_name':'Recovery Sample','is_sample':True}).json['driver']
    assert client.put('/api/drivers/'+driver['driver_id']+'/vehicle', json={'vehicle_id':'FM01'}).status_code == 200
    assert client.post('/api/trips/start', json=destination|{'driver_id':driver['driver_id']}).status_code == 201


def test_stale_destination_fix_does_not_complete_or_claim_arrival(app, client, reading, destination):
    app.config['STALE_AFTER_SECONDS'] = 30
    client.post('/api/locations', json=reading())
    trip = client.post('/api/trips/start', json=destination).json['trip']
    snapshot = client.post('/api/locations', json=reading(120, lat=destination['destination_lat'], lon=destination['destination_lon'])).json['vehicle']
    assert snapshot['stale'] is True
    assert snapshot['trip']['status'] == 'ACTIVE'
    assert snapshot['eta']['status'] == 'WAITING_FOR_GPS'
    assert snapshot['eta']['duration_seconds'] is None
    assert not any(e['kind']=='DESTINATION_REACHED' for e in client.get('/api/trips/'+str(trip['trip_id'])).json['events'])


def test_recovery_survives_restart_preserves_records_and_allows_new_simulation(app, client, reading, destination):
    client.post('/api/locations', json=reading())
    trip_id = client.post('/api/trips/start', json=destination).json['trip']['trip_id']
    client.post('/api/locations', json=reading(10, lat=17.4134))
    before = client.get('/api/trips/'+str(trip_id)).json
    assert client.post('/api/trips/stop', json={'vehicle_id':'FM01','trip_id':trip_id+1}).status_code == 409
    assert client.post('/api/trips/stop', json={'vehicle_id':'FM01','trip_id':trip_id}).status_code == 200
    restarted = create_app({'TESTING':True,'DATABASE':app.config['DATABASE'],'ROUTING_ENABLED':False,'SIMULATION_AUTORUN':False})
    c = restarted.test_client()
    after = c.get('/api/trips/'+str(trip_id)).json
    assert after['trip']['lifecycle_status'] == 'STOPPED'
    assert after['locations'] == before['locations']
    assert after['trip']['distance_m'] == before['trip']['distance_m']
    assert c.get('/api/trips/current').json['trip'] is None
    driver = c.post('/api/drivers', json={'full_name':'Restart Sample','is_sample':True}).json['driver']
    assert c.put('/api/drivers/'+driver['driver_id']+'/vehicle', json={'vehicle_id':'FM01'}).status_code == 200
    route = c.post('/api/routes', json={'demo_id':'quick-review'}).json['routes'][0]
    response = c.post('/api/simulation/start', json={'route_id':route['route_id'],'driver_id':driver['driver_id'],'speed_kmh':40,'multiplier':1})
    assert response.status_code == 201
    assert response.json['simulation']['trip_id'] != trip_id


def test_stale_routed_fix_cannot_arrive(app, client):
    app.config['SIMULATION_AUTORUN'] = False
    route = client.post('/api/routes', json={'demo_id':'quick-review'}).json['routes'][0]
    trip_id = client.post('/api/simulation/start', json={'route_id':route['route_id'],'speed_kmh':40,'multiplier':1}).json['simulation']['trip_id']
    from services.monitoring_service import monitor_route
    with app.app_context():
        db=get_db()
        trip=db.execute('SELECT * FROM trips WHERE trip_id=?',(trip_id,)).fetchone()
        with db:
            monitor_route(db, {'vehicle_id':'FM01','trip_id':trip_id,'lat':trip['destination_lat'],'lon':trip['destination_lon'],
                              'timestamp':(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()}, trip)
        assert db.execute('SELECT status FROM trips WHERE trip_id=?',(trip_id,)).fetchone()[0]=='ACTIVE'
