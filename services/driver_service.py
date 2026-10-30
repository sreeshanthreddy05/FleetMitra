"""Driver eligibility is derived from persisted trips, never a drifting status flag."""
from datetime import date
import json
import os
from pathlib import Path
import re

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from validation import APIError, number, text_field

PRIVATE_FIELDS = ('date_of_birth', 'gender', 'phone', 'email', 'address', 'license_number')


def cipher(db):
    configured = os.getenv('FLEET_DRIVER_KEY')
    if configured:
        key = configured.encode()
    else:
        path = Path(current_app.config['DATABASE']).parent / 'driver-profiles.key'
        if not path.exists():
            if db.execute('SELECT 1 FROM drivers LIMIT 1').fetchone():
                raise APIError('Driver encryption key is missing. Restore the original key backup.', 503)
            try:
                with path.open('xb') as stream:
                    stream.write(Fernet.generate_key())
                path.chmod(0o600)
            except FileExistsError:
                pass
        key = path.read_bytes()
    try:
        return Fernet(key)
    except ValueError:
        raise APIError('Driver encryption key configuration is invalid.', 503) from None


def private_profile(db, row):
    try:
        return json.loads(cipher(db).decrypt(row['private_encrypted']).decode())
    except InvalidToken:
        raise APIError('Driver profile cannot be decrypted with the configured key.', 503) from None


def parse_date(value, field):
    if value in (None, ''):
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise APIError(f'{field} must be a valid YYYY-MM-DD date') from None


def age_from(value):
    born = parse_date(value, 'date_of_birth')
    today = date.today()
    return today.year-born.year-((today.month,today.day)<(born.month,born.day)) if born else None


def validate(data):
    if 'age' in data:
        raise APIError('Age is calculated from date_of_birth and cannot be edited')
    name = text_field(data.get('full_name'), 'full_name')
    private = {}
    for field in PRIVATE_FIELDS:
        value = data.get(field)
        if value is None:value=''
        if not isinstance(value, str) or len(value)> (500 if field=='address' else 100):
            raise APIError(f'Invalid {field}')
        private[field] = value.strip()
    age = age_from(private['date_of_birth'])
    if age is not None and not 18<=age<=100:
        raise APIError('Driver age must be between 18 and 100')
    if private['phone'] and not re.fullmatch(r'\+?[0-9 ()-]{7,22}',private['phone']):
        raise APIError('Enter a valid phone number')
    if private['phone'] and not 7<=len(re.sub(r'\D','',private['phone']))<=15:
        raise APIError('Enter a valid phone number')
    if private['email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',private['email']):
        raise APIError('Enter a valid email address')
    if private['gender'] not in ('','Female','Male','Non-binary','Prefer not to say'):
        raise APIError('Invalid gender')
    if private['license_number'] and not re.fullmatch(r'[A-Za-z0-9 /-]{5,40}',private['license_number']):
        raise APIError('Enter a valid license number (5–40 characters)')
    expiry = parse_date(data.get('license_expiry'), 'license_expiry')
    if private['license_number'] and not expiry:
        raise APIError('License expiry is required when a license number is provided')
    if expiry and not private['license_number']:
        raise APIError('License number is required with license expiry')
    joined = parse_date(data.get('date_joined'), 'date_joined')
    if joined and joined>date.today():
        raise APIError('Date joined cannot be in the future')
    born=parse_date(private['date_of_birth'],'date_of_birth')
    if born and joined and (joined.year-born.year-((joined.month,joined.day)<(born.month,born.day)))<18:
        raise APIError('Date joined cannot precede age 18')
    experience = number(data.get('experience_years',0),'experience_years',0,70)
    if age is not None and experience>age-18:
        raise APIError('Experience cannot exceed years since age 18')
    for field in ('is_active','is_sample'):
        if field in data and not isinstance(data[field],bool):
            raise APIError(f'{field} must be true or false')
    return name,private,experience,expiry.isoformat() if expiry else None,joined.isoformat() if joined else None


def find_driver(db, driver_id):
    row = db.execute('SELECT * FROM drivers WHERE driver_id=?',(driver_id,)).fetchone()
    if row is None:
        raise APIError('Driver not found',404)
    return row


def public_driver(db,row):
    active = db.execute("SELECT trip_id FROM trips WHERE driver_id=? AND status='ACTIVE'",(row['driver_id'],)).fetchone()
    completed = db.execute("SELECT COUNT(*) FROM trips WHERE driver_id=? AND status='COMPLETED' AND completion_status='ARRIVED'",(row['driver_id'],)).fetchone()[0]
    expired = bool(row['license_expiry'] and row['license_expiry']<date.today().isoformat())
    return {key:row[key] for key in ('driver_id','full_name','assigned_vehicle_id','experience_years','date_joined','license_expiry','license_mask','phone_mask','created_at','updated_at')} | {
        'is_active':bool(row['is_active']),'is_sample':bool(row['is_sample']),
        'status':'On Trip' if active else 'Available' if row['is_active'] else 'Inactive',
        'active_trip_id':active['trip_id'] if active else None,'completed_trips':completed,
        'license_expired':expired,'eligible':bool(row['is_active'] and not active and not expired and row['assigned_vehicle_id'])}


def assign_trip_driver(db,trip_id,driver_id,vehicle_id):
    # Backward-compatible ingestion/API clients may omit drivers only on an empty registry.
    if not driver_id:
        if db.execute('SELECT 1 FROM drivers LIMIT 1').fetchone():
            raise APIError('Select an available driver before starting a trip',409)
        return
    if not isinstance(driver_id,str):
        raise APIError('driver_id must be a registered driver ID')
    row=find_driver(db,driver_id)
    if not public_driver(db,row)['eligible'] or row['assigned_vehicle_id']!=vehicle_id:
        raise APIError('Driver must be active, available, licensed if provided, and assigned to this vehicle',409)
    if trip_id is not None:
        db.execute('UPDATE trips SET driver_id=?,driver_name=?,driver_sample=? WHERE trip_id=?',
                   (driver_id,row['full_name'],row['is_sample'],trip_id))
