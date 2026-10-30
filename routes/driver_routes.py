"""Local operator driver management; bulk responses and trip exports omit private fields."""
import json
import uuid

from flask import Blueprint, jsonify, render_template, request

from database import get_db
from services.driver_service import (cipher,find_driver,private_profile,public_driver,validate,age_from)
from validation import APIError,json_body,utc_now,vehicle_exists

bp=Blueprint('drivers',__name__)


@bp.get('/drivers')
def page():
    return render_template('drivers.html')


@bp.get('/api/drivers')
def drivers():
    db=get_db();q=request.args.get('q','').strip().casefold()
    if len(q)>100:raise APIError('Search is too long')
    status=request.args.get('status','')
    if status not in ('','Available','On Trip','Inactive'):raise APIError('Invalid driver status')
    rows=[public_driver(db,row) for row in db.execute('SELECT * FROM drivers ORDER BY full_name,driver_id')]
    return jsonify(drivers=[row for row in rows if (not q or q in (row['full_name']+' '+row['driver_id']).casefold()) and (not status or row['status']==status)])


@bp.get('/api/drivers/<driver_id>')
def detail(driver_id):
    db=get_db();row=find_driver(db,driver_id);result=public_driver(db,row)
    from routes.trip_routes import summary
    trips=[summary(db,r['trip_id']) for r in db.execute('SELECT trip_id FROM trips WHERE driver_id=? ORDER BY trip_id DESC',(driver_id,))]
    finished=[t for t in trips if t['lifecycle_status']!='ACTIVE']
    distance=sum(t['distance_m'] for t in trips);duration=sum(t['duration_seconds'] for t in trips)
    result['statistics']={'total_trips':len(trips),'completed_trips':sum(t['lifecycle_status']=='COMPLETED' for t in trips),
        'total_distance_m':distance,'average_trip_duration_seconds':sum(t['duration_seconds'] for t in finished)/len(finished) if finished else 0,
        'average_recorded_speed_kmh':distance/duration*3.6 if duration else 0,
        'maximum_recorded_speed_kmh':max((t['maximum_speed_kmh'] for t in trips),default=0),
        'deviation_count':sum(t['deviation_count'] for t in trips),'most_recent_trip_id':trips[0]['trip_id'] if trips else None}
    return jsonify(driver=result)


@bp.get('/api/drivers/<driver_id>/profile')
def profile(driver_id):
    db=get_db();row=find_driver(db,driver_id);private=private_profile(db,row)
    response=jsonify(driver=public_driver(db,row)|private|{'age':age_from(private.get('date_of_birth'))})
    response.headers['Cache-Control']='no-store'
    return response


@bp.post('/api/drivers')
def create():
    db=get_db();data=json_body();name,private,experience,expiry,joined=validate(data)
    if 'driver_id' in data:raise APIError('Driver IDs are generated automatically')
    driver_id='DR-'+uuid.uuid4().hex[:12].upper();now=utc_now()
    with db:
        db.execute('BEGIN IMMEDIATE')
        encrypted=cipher(db).encrypt(json.dumps(private).encode()).decode()
        db.execute('INSERT INTO drivers (driver_id,full_name,is_active,is_sample,experience_years,date_joined,license_expiry,license_mask,phone_mask,private_encrypted,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (driver_id,name,int(data.get('is_active',True)),int(data.get('is_sample',False)),experience,joined,expiry,
             '••••'+private['license_number'][-4:] if private['license_number'] else '',
             '••••'+private['phone'][-4:] if private['phone'] else '',encrypted,now,now))
    return jsonify(driver=public_driver(db,find_driver(db,driver_id))),201


@bp.patch('/api/drivers/<driver_id>')
def edit(driver_id):
    db=get_db();changes=json_body()
    if 'driver_id' in changes or 'assigned_vehicle_id' in changes:raise APIError('Use vehicle assignment controls; driver ID is immutable')
    with db:
        db.execute('BEGIN IMMEDIATE');row=find_driver(db,driver_id)
        data=dict(row)|private_profile(db,row)|{'is_active':bool(row['is_active']),'is_sample':bool(row['is_sample'])}|changes
        name,private,experience,expiry,joined=validate(data)
        encrypted=cipher(db).encrypt(json.dumps(private).encode()).decode()
        db.execute('UPDATE drivers SET full_name=?,is_active=?,is_sample=?,experience_years=?,date_joined=?,license_expiry=?,license_mask=?,phone_mask=?,private_encrypted=?,updated_at=? WHERE driver_id=?',
            (name,int(data['is_active']),int(data['is_sample']),experience,joined,expiry,
             '••••'+private['license_number'][-4:] if private['license_number'] else '',
             '••••'+private['phone'][-4:] if private['phone'] else '',encrypted,utc_now(),driver_id))
    return jsonify(driver=public_driver(db,find_driver(db,driver_id)))


@bp.put('/api/drivers/<driver_id>/vehicle')
def assign(driver_id):
    db=get_db();vehicle=json_body().get('vehicle_id')
    with db:
        db.execute('BEGIN IMMEDIATE');row=find_driver(db,driver_id)
        if db.execute("SELECT 1 FROM trips WHERE driver_id=? AND status='ACTIVE'",(driver_id,)).fetchone():
            raise APIError('End the active trip before changing vehicle assignment',409)
        if vehicle is not None:
            vehicle_exists(db,vehicle)
            if not row['is_active']:raise APIError('Activate the driver before assigning a vehicle',409)
            if db.execute('SELECT 1 FROM drivers WHERE assigned_vehicle_id=? AND driver_id<>?',(vehicle,driver_id)).fetchone():
                raise APIError('Vehicle is already assigned. Unassign its current driver first.',409)
            if db.execute("SELECT 1 FROM trips WHERE vehicle_id=? AND status='ACTIVE'",(vehicle,)).fetchone():
                raise APIError('Vehicle has an active trip',409)
        db.execute('UPDATE drivers SET assigned_vehicle_id=?,updated_at=? WHERE driver_id=?',(vehicle,utc_now(),driver_id))
    return jsonify(driver=public_driver(db,find_driver(db,driver_id)))
