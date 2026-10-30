"""Photon search proxy: bounded calls, per-process rate limit and ten-minute cache."""
import json
import math
import threading
import time
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import URLError
from http.client import HTTPException

from validation import APIError


class Geocoder:
    def __init__(self, config):
        self.config=config
        self.cache={}
        self.last_request=-100
        self.lock=threading.Lock()

    def search(self, query):
        query=query.strip()
        if not 3<=len(query)<=120:
            raise APIError('Search must contain 3–120 characters')
        saved=[{**p,'label':p['name'],'provider':'Saved place'} for p in self.config['SAVED_PLACES'] if query.casefold() in p['name'].casefold()]
        if saved:return saved
        if not self.config['GEOCODING_ENABLED']:
            raise APIError('Place search is disabled. Select coordinates on the map.',503)
        key=query.casefold()
        with self.lock:
            now=time.monotonic()
            self.cache={k:v for k,v in self.cache.items() if v[0]>now}
            if key in self.cache:return self.cache[key][1]
            if now-self.last_request<.75:
                raise APIError('Please wait a moment before searching again.',429)
            self.last_request=now
            url=self.config['GEOCODING_URL']+'?'+urlencode({'q':query,'limit':6,'lat':17.415666,'lon':78.573060,'lang':'en'})
            try:
                req=Request(url,headers={'User-Agent':'FleetMitra-AcademicPrototype/1.0','Accept':'application/json'})
                with urlopen(req,timeout=self.config['GEOCODING_TIMEOUT']) as response:
                    data=json.loads(response.read(500000))
                if not isinstance(data,dict) or not isinstance(data.get('features'),list):raise ValueError()
                result=[]
                for feature in data['features'][:6]:
                    if not isinstance(feature,dict):continue
                    geometry=feature.get('geometry',{});properties=feature.get('properties',{})
                    if not isinstance(geometry,dict) or not isinstance(properties,dict) or geometry.get('type')!='Point':continue
                    coords=geometry.get('coordinates')
                    if not isinstance(coords,list) or len(coords)<2:continue
                    if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and -b<=v<=b and math.isfinite(v) for v,b in zip(coords[:2],[180,90])):continue
                    labels=[]
                    for name in ('name','street','housenumber','city','state','country'):
                        value=properties.get(name)
                        if isinstance(value,str) and value and value not in labels:labels.append(value)
                    result.append({'label':', '.join(labels)[:250] or f'{coords[1]}, {coords[0]}','lat':coords[1],'lon':coords[0],'provider':'Photon / OpenStreetMap'})
                if len(self.cache)>=128:self.cache.pop(next(iter(self.cache)))
                self.cache[key]=(now+600,result)
                return result
            except (URLError,OSError,HTTPException,ValueError,TypeError,KeyError):
                raise APIError('Place search is temporarily unavailable. Map selection and saved Home still work.',503) from None
