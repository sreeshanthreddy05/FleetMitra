"""Optimistic destination proposals leave movement untouched until atomic activation."""
from datetime import datetime, timezone, timedelta
import json
import secrets

from flask import Blueprint,current_app,jsonify

from calculations import haversine
from database import get_db
from services.event_service import record_event
from services.route_geometry import project
from services.route_planner import plan_routes,route_by_id
from services.tracking_service import latest_location
from services.trip_archive import archive_route
from validation import APIError,coordinates,json_body,text_field,utc_now

bp=Blueprint('destinations',__name__)


def requested_destination(db,trip):
    event=db.execute("SELECT details_json FROM trip_events WHERE trip_id=? AND kind='DESTINATION_CHANGED' ORDER BY event_id DESC LIMIT 1",(trip['trip_id'],)).fetchone()
    if event:
        return json.loads(event['details_json'])['new_destination']
    if trip['original_destination_json']:
        return json.loads(trip['original_destination_json'])
    if trip['route_id']:
        return route_by_id(db,trip['route_id'])['requested_destination']
    return {'lat':trip['destination_lat'],'lon':trip['destination_lon']}


def trip_location(db,trip_id):
    trip=db.execute("SELECT * FROM trips WHERE trip_id=? AND status='ACTIVE'",(trip_id,)).fetchone()
    if not trip:raise APIError('This trip is no longer active',409)
    location=latest_location(db,trip['vehicle_id'])
    if not location or location['trip_id']!=trip_id:
        raise APIError('A valid current vehicle position is required',409)
    if location['source']=='HARDWARE' and (datetime.now(timezone.utc)-datetime.fromisoformat(location['timestamp'])).total_seconds()>current_app.config['STALE_AFTER_SECONDS']:
        raise APIError('Waiting for a fresh GPS position',409)
    return trip,location


@bp.post('/api/trips/<int:trip_id>/destination-options')
def options(trip_id):
    data=json_body();lat,lon=coordinates(data);label=text_field(data.get('label'),'label',f'{lat:.6f}, {lon:.6f}')
    db=get_db();engine=current_app.extensions['simulation']
    with engine.lock:
        trip,location=trip_location(db,trip_id)
        previous=requested_destination(db,trip)
        if haversine(lat,lon,previous['lat'],previous['lon'])<1:
            return jsonify(unchanged=True,message='This is already the current destination.')
        if haversine(location['lat'],location['lon'],lat,lon)<10:
            raise APIError('Choose a destination at least 10 meters from the vehicle')
        revision=trip['navigation_revision'];origin=(location['lat'],location['lon'])
    # Provider requests do not hold the simulation lock: the current trip keeps moving.
    try:
        planned=plan_routes(origin,(lat,lon),origin_radius=10)
    except APIError as error:
        if error.status==503:
            raise APIError('Road routing unavailable from the current GPS segment. Retry or choose another destination. Current trip retained.',503) from None
        raise
    proposal_id=secrets.token_urlsafe(24)
    with db:
        db.execute('BEGIN IMMEDIATE')
        current,_=trip_location(db,trip_id)
        if current['navigation_revision']!=revision:raise APIError('Navigation changed while planning. Calculate new options.',409)
        db.execute('INSERT INTO destination_proposals (proposal_id,trip_id,revision,destination_json,route_ids_json,created_at) VALUES (?,?,?,?,?,?)',
                   (proposal_id,trip_id,revision,json.dumps({'lat':lat,'lon':lon,'label':label}),json.dumps([r['route_id'] for r in planned['routes']]),utc_now()))
    return jsonify(**planned,proposal_id=proposal_id,destination={'lat':lat,'lon':lon,'label':label},trip_id=trip_id)


@bp.post('/api/trips/<int:trip_id>/destination')
def activate(trip_id):
    data=json_body();db=get_db();engine=current_app.extensions['simulation']
    token=data.get('proposal_id')
    if not isinstance(token,str) or len(token)>100:raise APIError('A destination proposal is required')
    with engine.lock, db:
        db.execute('BEGIN IMMEDIATE')
        proposal=db.execute('SELECT * FROM destination_proposals WHERE proposal_id=? AND trip_id=?',(token,trip_id)).fetchone()
        if not proposal:raise APIError('Destination proposal not found',404)
        if proposal['applied_route_id']:
            if data.get('route_id')!=proposal['applied_route_id']:raise APIError('This proposal was already applied with another route',409)
            return jsonify(applied=True,duplicate=True,route=route_by_id(db,proposal['applied_route_id']))
        trip,location=trip_location(db,trip_id)
        if proposal['revision']!=trip['navigation_revision']:
            raise APIError('Another navigation change was applied. Calculate new routes.',409)
        if datetime.now(timezone.utc)-datetime.fromisoformat(proposal['created_at'])>timedelta(minutes=5):
            raise APIError('Route options expired. Calculate new routes.',409)
        route=route_by_id(db,data.get('route_id'))
        if route['route_id'] not in json.loads(proposal['route_ids_json']) or route['method']!='ROAD_ROUTE':
            raise APIError('Select a road route from this destination proposal')
        nearest=project(json.dumps(route['geometry']),location['lat'],location['lon'])
        if nearest['distance_m']>10:
            raise APIError('Vehicle has moved beyond these route options. Refresh routes from its current position.',409)
        destination=json.loads(proposal['destination_json']);remaining=max(0,route['distance_m']-nearest['along_m'])
        old=requested_destination(db,trip)|{'label':trip['destination_label']}
        if not trip['original_destination_json']:
            db.execute('UPDATE trips SET original_destination_json=? WHERE trip_id=?',(json.dumps(old),trip_id))
        # Keep physical distance, start time, logical duration, driver and settings unchanged.
        progress=trip['distance_m'];offset=progress-nearest['along_m']
        db.execute("UPDATE trips SET destination_lat=?,destination_lon=?,destination_label=?,route_id=?,route_offset_m=?,route_progress_m=?,route_total_m=?,route_status='ON_ROUTE',off_route_count=0,navigation_revision=navigation_revision+1 WHERE trip_id=?",
            (route['destination']['lat'],route['destination']['lon'],destination['label'],route['route_id'],offset,progress,progress+remaining,trip_id))
        session=db.execute("SELECT * FROM simulation_sessions WHERE trip_id=? AND state IN ('RUNNING','PAUSED')",(trip_id,)).fetchone()
        speed=session['speed_kmh'] if session else location['speed_kmh']
        if session:
            flags=json.loads(session['flags_json'])
            flags.update(offset_m=0,deviation_hold=False,auto_attempted=False,deviation_scripted=True,speed_scripted=True,outage_scripted=True)
            for key in ('test_geometry','test_position_m','test_limit_m'):flags.pop(key,None)
            db.execute('UPDATE simulation_sessions SET route_id=?,position_m=?,flags_json=?,updated_at=? WHERE session_id=?',
                       (route['route_id'],nearest['along_m'],json.dumps(flags),utc_now(),session['session_id']))
        archive_route(db,trip_id,route['route_id'],'DESTINATION_CHANGED')
        details={'previous_destination':old,'new_destination':destination,'vehicle_location':{'lat':location['lat'],'lon':location['lon'],'timestamp':location['timestamp']},
                 'distance_travelled_m':progress,'previous_remaining_m':max(0,trip['route_total_m']-trip['route_progress_m']),
                 'remaining_distance_m':remaining,'eta_seconds':remaining/(speed/3.6) if speed else None,
                 'traffic':route['traffic'],'traffic_adjusted_eta_seconds':route['traffic']['adjusted_duration_seconds']*remaining/route['distance_m'],
                 'selected_route_id':route['route_id'],'timestamp':utc_now()}
        record_event(db,trip['vehicle_id'],trip_id,'DESTINATION_CHANGED','Destination Updated',
            'Your destination has been changed successfully. A new route has been calculated from your current location. Navigation is continuing toward the new destination.',
            'SUCCESS',True,details=details,dedupe_key='destination:'+token)
        db.execute('UPDATE destination_proposals SET applied_route_id=? WHERE proposal_id=?',(route['route_id'],token))
    return jsonify(applied=True,route=route,trip_id=trip_id)
