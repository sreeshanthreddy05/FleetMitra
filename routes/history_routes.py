"""Dedicated persisted history, pagination, filters and complete exports."""
import csv
from datetime import date
import io
import json

from flask import Blueprint, jsonify, render_template, request, Response, current_app

from database import get_db
from routes.trip_routes import summary, detail
from validation import APIError

bp=Blueprint('history',__name__)


@bp.get('/api/search')
def search():
    return jsonify(results=current_app.extensions['geocoder'].search(request.args.get('q','')),
                   attribution='Photon / © OpenStreetMap contributors')


@bp.get('/history')
@bp.get('/history/<int:trip_id>')
def page(trip_id=None):
    return render_template('history.html',trip_id=trip_id)


@bp.get('/api/trip-records')
def records():
    db=get_db()
    try:
        page=int(request.args.get('page',1));per_page=int(request.args.get('per_page',20))
    except ValueError:raise APIError('page and per_page must be integers') from None
    if not 1<=page<=100000 or not 1<=per_page<=100:raise APIError('Invalid page or per_page')
    clauses=['1=1'];params=[]
    q=request.args.get('q','').strip()
    if len(q)>120:raise APIError('Search too long')
    if q:
        pattern='%'+q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        clauses.append("(CAST(t.trip_id AS TEXT) LIKE ? ESCAPE '\\' OR t.start_label LIKE ? ESCAPE '\\' OR t.destination_label LIKE ? ESCAPE '\\')")
        params.extend([pattern]*3)
    if request.args.get('vehicle'):
        clauses.append('t.vehicle_id = ?');params.append(request.args['vehicle'])
    driver=request.args.get('driver')
    if driver=='unassigned':clauses.append('t.driver_id IS NULL')
    elif driver:
        if len(driver)>100:raise APIError('Invalid driver filter')
        clauses.append('t.driver_id = ?');params.append(driver)
    for key,operator in [('from','>='),('to','<=')]:
        if request.args.get(key):
            try:value=date.fromisoformat(request.args[key]).isoformat()
            except ValueError:raise APIError('Dates must use YYYY-MM-DD') from None
            clauses.append(f'substr(t.start_time,1,10) {operator} ?');params.append(value)
    status=request.args.get('status','')
    if status not in ('','COMPLETED','STOPPED','ACTIVE'):raise APIError('Invalid status filter')
    lifecycle="CASE WHEN t.status='ACTIVE' THEN 'ACTIVE' WHEN t.end_reason IN ('RESET','OPERATOR_STOP') THEN 'STOPPED' ELSE 'COMPLETED' END"
    if status:clauses.append(lifecycle+' = ?');params.append(status)
    if request.args.get('deviations')=='true':
        clauses.append("EXISTS (SELECT 1 FROM trip_events e WHERE e.trip_id=t.trip_id AND e.kind='ROUTE_DEVIATION')")
    sort=request.args.get('sort','date');direction=request.args.get('direction','desc')
    if sort not in ('date','distance','duration','id') or direction not in ('asc','desc'):raise APIError('Invalid sort')
    column={'date':'t.start_time','distance':'t.distance_m','duration':'t.elapsed_seconds','id':'t.trip_id'}[sort]
    where=' AND '.join(clauses)
    count=db.execute('SELECT COUNT(*) FROM trips t WHERE '+where,params).fetchone()[0]
    ids=db.execute(f'SELECT t.trip_id FROM trips t WHERE {where} ORDER BY {column} {direction}, t.trip_id {direction} LIMIT ? OFFSET ?',
                   (*params,per_page,(page-1)*per_page)).fetchall()
    return jsonify(trips=[summary(db,row['trip_id']) for row in ids],total=count,page=page,per_page=per_page)


@bp.get('/api/trips/<int:trip_id>/export.<format>')
def export(trip_id,format):
    if format not in ('csv','json'):raise APIError('Export format must be csv or json')
    data=detail(trip_id).get_json()
    if format=='json':
        body=json.dumps(data,ensure_ascii=False,indent=2)
        mime='application/json'
    else:
        output=io.StringIO(newline='');writer=csv.writer(output)
        writer.writerow(['record_type','trip_id','timestamp','latitude','longitude','speed_kmh','details_json'])
        writer.writerow(['trip',trip_id,data['trip']['start_time'],'','','',json.dumps(data['trip'],ensure_ascii=False)])
        for row in data['locations']:
            writer.writerow(['location',trip_id,row['timestamp'],row['lat'],row['lon'],row['speed_kmh'],json.dumps(row)])
        for event in data['events']:
            writer.writerow(['event',trip_id,event['timestamp'],'','','',json.dumps(event,ensure_ascii=False)])
        for route in data['route_versions']:
            writer.writerow(['route_version',trip_id,route['timestamp'],'','','',json.dumps(route,ensure_ascii=False)])
        body=output.getvalue();mime='text/csv'
    return Response(body,content_type=mime+'; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="fleetmitra-trip-{trip_id}.{format}"'})
