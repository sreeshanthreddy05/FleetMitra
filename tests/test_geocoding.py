from io import BytesIO
import json
from urllib.error import URLError

import pytest


def test_saved_home_does_not_need_provider(client,monkeypatch):
    monkeypatch.setattr('services.geocoding_service.urlopen',lambda *a,**k:pytest.fail('Saved Home must be local'))
    home=client.get('/api/search?q=Home').json['results'][0]
    assert home['lat']==17.415666 and home['lon']==78.573060


def test_search_coordinates_cache_and_rate_limit(client,monkeypatch):
    calls=[]
    def response(*a,**k):
        calls.append(a)
        return BytesIO(json.dumps({'features':[{'geometry':{'type':'Point','coordinates':[78.4867,17.385]},'properties':{'name':'Hyderabad','country':'India'}}]}).encode())
    monkeypatch.setattr('services.geocoding_service.urlopen',response)
    result=client.get('/api/search?q=Hyderabad')
    assert result.status_code==200
    assert result.json['results'][0]['lat']==17.385 and result.json['results'][0]['lon']==78.4867
    assert client.get('/api/search?q=hyderabad').json==result.json and len(calls)==1
    assert client.get('/api/search?q=Delhi').status_code==429


@pytest.mark.parametrize('payload',[None,[],{'features':None},'bad'])
def test_malformed_provider(client,monkeypatch,payload):
    monkeypatch.setattr('services.geocoding_service.urlopen',lambda *a,**k:BytesIO(json.dumps(payload).encode()))
    assert client.get('/api/search?q=Hyderabad').status_code==503


def test_failure_and_validation(app,client,monkeypatch):
    def failure(*a,**k):raise URLError('offline')
    monkeypatch.setattr('services.geocoding_service.urlopen',failure)
    assert client.get('/api/search?q=Hyderabad').status_code==503
    assert client.get('/api/search?q=ab').status_code==400
    app.config['GEOCODING_ENABLED']=False
    assert client.get('/api/search?q=Delhi').status_code==503


def test_bad_coordinates_ignored(client,monkeypatch):
    monkeypatch.setattr('services.geocoding_service.urlopen',lambda *a,**k:BytesIO(json.dumps({'features':[{'geometry':{'type':'Point','coordinates':[float('nan'),17]},'properties':{'name':'bad'}}]}).encode()))
    assert client.get('/api/search?q=Hyderabad').json['results']==[]
