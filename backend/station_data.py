"""NOAA NCEI/CDO monthly observations: fixed station cohorts, never area grids."""
import calendar
import datetime as dt
import hashlib
import json
import math
import time
from pathlib import Path

import requests
import geography
import jobs
import nasa_data
from giovanni_data import RegionalSeries
from spatial import unwrap

BASE='https://www.ncei.noaa.gov/access/services/'
FIELDS={'STATION_TAVG':'TAVG','STATION_TMAX':'TMAX','STATION_TMIN':'TMIN','STATION_WIND':'AWND','STATION_RAIN':'PRCP'}
CACHE=Path(__file__).resolve().parent/'cache'/'noaa'


def inside(feature,lon,lat):
    def ring_contains(ring):
        points=unwrap(ring);x=lon
        while x-points[0][0]>180:x-=360
        while x-points[0][0]<-180:x+=360
        hit=False
        for a,b in zip(points,points[1:]):
            cross=(b[0]-a[0])*(lat-a[1])-(b[1]-a[1])*(x-a[0])
            if abs(cross)<1e-10 and min(a[0],b[0])-1e-10<=x<=max(a[0],b[0])+1e-10 and min(a[1],b[1])-1e-10<=lat<=max(a[1],b[1])+1e-10:return True
            if (a[1]>lat)!=(b[1]>lat) and x<(b[0]-a[0])*(lat-a[1])/(b[1]-a[1])+a[0]:hit=not hit
        return hit
    return any(ring_contains(poly[0]) and not any(ring_contains(r) for r in poly[1:]) for poly in geography.polygons(feature['geometry']))


def _request(route,params):
    if route not in {'search/v1/data','data/v1'}:raise ValueError('Unsupported NOAA route')
    try:
        with requests.Session() as s:
            s.auth=lambda r:r
            with s.get(BASE+route,params=params,timeout=(10,60),stream=True,allow_redirects=False) as r:
                if r.status_code!=200:raise ValueError(f'NOAA returned HTTP {r.status_code}; no station observations were substituted.')
                body=bytearray()
                for part in r.iter_content(64000):
                    jobs.check_cancelled();body.extend(part)
                    if len(body)>2_000_000:raise ValueError('NOAA response exceeds 2 MB; choose a smaller area or period')
                return json.loads(body)
    except requests.RequestException as e:raise ValueError('Cannot reach NOAA Climate Data Online observations; retry later.') from e


def monthly_series(rows,field,start,end):
    months=[y*100+m for y in range(start,end+1) for m in range(1,13)]
    observations={};seen=set()
    for row in rows:
        try:
            sid=row['STATION'];date=dt.date.fromisoformat(row['DATE'][:7]+'-01');month=date.year*100+date.month
            if not start<=date.year<=end:raise ValueError('NOAA returned a date outside the requested window')
            key=(sid,month)
            if key in seen:raise ValueError('Duplicate NOAA station/month record')
            seen.add(key)
            raw=row.get(field)
            if raw in {None,''}:continue
            value=float(raw)
            if not math.isfinite(value) or value<=-999:continue
            # GSOM a,S (TAVG/AWND) or a,M,Q,S (TMAX/TMIN/PRCP).
            # Source letters are not quality flags. Require no reported missing
            # days; reject failed QA and precipitation accumulations over gaps.
            # https://www.ncei.noaa.gov/data/gsom/doc/GSOM_documentation.pdf
            attributes=[v.strip() for v in str(row.get(field+'_ATTRIBUTES','')).split(',')]
            if attributes[0].isdigit() and int(attributes[0])>0:continue
            if field in {'TMAX','TMIN','PRCP'} and len(attributes)>2 and attributes[2]:continue
            if field=='PRCP' and len(attributes)>1 and attributes[1] in {'a','P'}:continue
            if field=='PRCP':value/=calendar.monthrange(date.year,date.month)[1]
            observations.setdefault(sid,{})[month]=value
        except (KeyError,TypeError) as e:raise ValueError('Invalid NOAA station/month record') from e
    cohort=sorted(s for s,v in observations.items() if len(v)>=.8*len(months))
    values={}
    for month in months:
        current=[observations[s][month] for s in cohort if month in observations[s]]
        values[month]=sum(current)/len(current) if current and len(current)>=.8*len(cohort) else None
    return values,cohort


def fetch_region(variable,feature,start,end):
    if variable not in FIELDS:raise ValueError('No NOAA mapping for this measurement')
    field=FIELDS[variable];west,south,east,north=feature['bbox']
    if east<west or (east-west)*(north-south)>300:raise ValueError('Choose a smaller NOAA station area; continental station requests are not downloaded automatically.')
    key=hashlib.sha256(json.dumps(['noaa-fixed-cohort-v2-quality',field,feature['geometry_version'],start,end]).encode()).hexdigest()
    path=CACHE/(key+'.json');hit=False
    try:
        saved=json.loads(path.read_text())
        if time.time()-saved['saved']>86400:raise ValueError('expired')
        values={int(k):v for k,v in saved['values'].items()};stations=saved['stations'];cohort=saved['cohort'];retrieved=saved['retrieved'];hit=True
    except (OSError,ValueError,KeyError):
        jobs.progress(0,1,'Finding NOAA stations inside the selected boundary')
        common={'dataset':'global-summary-of-the-month','startDate':f'{start}-01-01','endDate':f'{end}-12-31'}
        found=_request('search/v1/data',{**common,'bbox':f'{north},{west},{south},{east}','limit':1000})
        if not isinstance(found,dict) or not isinstance(found.get('results'),list):raise ValueError('Invalid NOAA station discovery response')
        if found.get('count',0)>1000:raise ValueError('NOAA station limit exceeded; choose a smaller area')
        stations=[]
        for item in found['results']:
            try:
                lon,lat=item['boundingPoints'][0]['coordinates'];st=item['stations'][0]
                if inside(feature,lon,lat) and any(x.get('id')==field for x in st.get('dataTypes',[])):
                    stations.append({'id':st['id'],'name':st.get('name',st['id']),'lon':lon,'lat':lat})
            except (KeyError,IndexError,TypeError,ValueError) as e:raise ValueError('Invalid NOAA station coordinates') from e
        unique={s['id']:s for s in stations};stations=list(unique.values())
        if len(stations)>60:raise ValueError('This NOAA area has more than 60 stations; choose a smaller area')
        rows=[]
        for offset in range(0,len(stations),5):
            jobs.check_cancelled()
            reply=_request('data/v1',{**common,'stations':','.join(s['id'] for s in stations[offset:offset+5]),'dataTypes':field,
                'format':'json','units':'metric','includeAttributes':'true','includeStationLocation':'true'})
            if not isinstance(reply,list):raise ValueError('Invalid NOAA observation response')
            allowed={s['id'] for s in stations[offset:offset+5]}
            if any(r.get('STATION') not in allowed for r in reply):raise ValueError('NOAA returned an unrequested station')
            rows.extend(reply);jobs.progress(min(offset+5,len(stations)),len(stations),'Reading NOAA monthly station observations')
        values,cohort=monthly_series(rows,field,start,end);retrieved=dt.datetime.now(dt.timezone.utc).isoformat()
        nasa_data._atomic_write(path,json.dumps({'saved':time.time(),'values':values,'stations':stations,'cohort':cohort,'retrieved':retrieved}).encode())
    observed=sorted(m for m,v in values.items() if v is not None)
    provenance={'provider':'noaa-cdo','source':'NOAA NCEI / Climate Data Online observations','resource':'Climate Data Online',
        'dataset':'Global Summary of the Month','collection_version':'NCEI access service v1','field':field,'policy':'challenge_resource',
        'citation':'https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id=gov.noaa.ncdc:C00946',
        'access':'Public NCEI monthly station API; no CDO v2 token required',
        'aggregation':'Fixed station cohort inside polygon; equal station weights, not an area average. At least 80% cohort support each month.',
        'quality':'Stations require 80% monthly availability over the requested period; records reporting missing days, failed quality checks or rain accumulations over gaps excluded. Spatial representativeness and station homogenization are not established.',
        'stations':[s for s in stations if s['id'] in cohort],'station_count':len(cohort),'candidate_station_count':len(stations),
        'geometry_version':feature['geometry_version'],'spatial_detail_available':False,'monthly_area_coverage_known':False,
        'cache_hit':hit,'retrieved_utc':retrieved,'first_observed_month':observed[0] if observed else None,'last_observed_month':observed[-1] if observed else None}
    return RegionalSeries(values,provenance)
