"""AppEEARS polygon statistics for monthly MODIS vegetation indices.

The app retrieves summary CSVs only. NASA may create rasters in its remote
task; TerraTrend never downloads those or falls back to a raster bundle.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import math
import re
import threading
import time
from pathlib import Path
from urllib.parse import urljoin,urlsplit

import requests
import jobs
import nasa_data
import service_credentials
from giovanni_data import RegionalSeries

BASE='https://appeears.earthdatacloud.nasa.gov/api/'
RESULT_HOST='d2v96idf0qj40l.cloudfront.net'
RESULT_PREFIX='/s3-eab5ea0d219da2588ae2241aa105a663/appeears-output.s3.amazonaws.com/'
FIELDS={'NDVI':'_1_km_monthly_NDVI','EVI':'_1_km_monthly_EVI'}
PRODUCT='MOD13A3.061'
VERSION='appeears-monthly-statistics-v2-physical-summary'
CACHE=Path(__file__).resolve().parent/'cache'/'appeears'
_TOKEN=''
_LOCK=threading.RLock()


def token():
    with _LOCK:return _TOKEN or service_credentials.load('appeears')


def status():
    return {'configured':bool(token()),**service_credentials.status('appeears'),
        'message':'AppEEARS uses a separate service token, which NASA may expire after about 48 hours.'}


def _request(route,method='GET',body=None,bearer='',auth=None,raw=False):
    if not re.fullmatch(r'(login|task(?:/[a-fA-F0-9-]+)?|status/[a-fA-F0-9-]+|bundle/[a-fA-F0-9-]+(?:/[a-fA-F0-9-]+)?)',route):raise ValueError('Unsupported AppEEARS destination')
    try:
        with requests.Session() as s:
            s.auth=lambda r:r
            headers={'User-Agent':'TerraTrend/1.0','Accept':'text/csv' if raw else 'application/json'}
            if bearer:headers['Authorization']='Bearer '+bearer
            with s.request(method,BASE+route,json=body,auth=auth,headers=headers,timeout=(10,60),stream=True,allow_redirects=False) as r:
                if r.status_code==303 and route.startswith('status/') and method=='GET':
                    target=urljoin(BASE+route,r.headers.get('Location',''))
                    expected=BASE+'task/'+route.split('/')[1]
                    if target!=expected:raise ValueError('AppEEARS redirected progress outside the requested NASA task')
                    return _request('task/'+route.split('/')[1],bearer=bearer)
                if r.status_code==302 and route.startswith('bundle/') and raw and method=='GET':
                    target=r.headers.get('Location','');parsed=urlsplit(target)
                    expected_path=RESULT_PREFIX+route.split('/')[1]+'/MOD13A3-061-Statistics.csv'
                    if parsed.scheme!='https' or parsed.netloc!=RESULT_HOST or parsed.path!=expected_path or parsed.fragment:
                        raise ValueError('AppEEARS result is not the requested NASA summary CSV')
                    # This signed result URL goes to NASA's delivery CDN.
                    # Never forward the AppEEARS bearer or login credentials.
                    with s.get(target,headers={'Accept':'text/csv','User-Agent':'TerraTrend/1.0'},timeout=(10,60),stream=True,allow_redirects=False) as output:
                        if output.status_code!=200:raise ValueError('NASA summary delivery failed; retry the existing AppEEARS task')
                        result=bytearray()
                        for part in output.iter_content(64000):
                            jobs.check_cancelled();result.extend(part)
                            if len(result)>2_000_000:raise ValueError('AppEEARS summary exceeds 2 MB')
                        return bytes(result)
                if r.status_code in {401,403}:raise ValueError('AppEEARS authorization is missing or expired. Connect AppEEARS in Data & Methods; your Earthdata key remains separate.')
                if r.status_code not in {200,201,202,204}:raise ValueError(f'AppEEARS returned HTTP {r.status_code}; no raster fallback was used.')
                data=bytearray()
                for part in r.iter_content(64000):
                    jobs.check_cancelled();data.extend(part)
                    if len(data)>2_000_000:raise ValueError('AppEEARS response exceeds the 2 MB summary limit')
                return bytes(data) if raw else json.loads(data) if data else {}
    except requests.RequestException as e:raise ValueError('Cannot reach NASA AppEEARS; retry later.') from e


def connect(username,password,remember=True):
    global _TOKEN
    if not isinstance(username,str) or not username.strip() or len(username)>200 or not isinstance(password,str) or not password or len(password)>4096:
        raise ValueError('Enter your NASA Earthdata username and password in this local form.')
    reply=_request('login',method='POST',auth=(username.strip(),password))
    value=reply.get('token','')
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9._-]{20,4096}',value):raise ValueError('AppEEARS did not issue a valid service token')
    if remember:service_credentials.remember('appeears',value)
    else:service_credentials.forget('appeears')
    with _LOCK:_TOKEN=value
    return status()


def disconnect():
    global _TOKEN
    service_credentials.forget('appeears')
    with _LOCK:_TOKEN=''
    return status()


def task_spec(variable,feature,start,end):
    if variable not in FIELDS:raise ValueError('This measurement has no AppEEARS mapping')
    return {'task_type':'area','task_name':'TerraTrend monthly vegetation',
        'params':{'dates':[{'startDate':f'01-01-{start}','endDate':f'12-31-{end}'}],
        'layers':[{'product':PRODUCT,'layer':FIELDS[variable]}],
        'geo':{'type':'FeatureCollection','features':[{'type':'Feature','properties':{'name':feature['name']},'geometry':feature['geometry']}]},
        'output':{'format':{'type':'geotiff'},'projection':'native'}}}


def summary_file(files):
    candidates=[f for f in files if f.get('file_name','').endswith('MOD13A3-061-Statistics.csv')]
    if len(candidates)!=1:raise ValueError('AppEEARS did not return one complete MODIS statistics CSV; no raster files were downloaded')
    return candidates[0]


def remote_status(reply,jid):
    if isinstance(reply,list):
        matching=[r for r in reply if r.get('task_id')==jid]
        if not matching:raise ValueError('AppEEARS progress does not identify the requested task')
        row=max(matching,key=lambda r:r.get('updated',''))
        progress=row.get('progress',{});percent=float(progress.get('summary',0))
        if not math.isfinite(percent) or not 0<=percent<=100:raise ValueError('Invalid NASA processing progress')
        steps=progress.get('details',[])
        current=next((s.get('desc','Processing') for s in steps if float(s.get('pct_complete',0))<100),'Finalizing')
        return {'task_id':jid,'status':'processing','percent':percent,
            'message':f'NASA AppEEARS: {percent:g}% · {current} on NASA servers; local download is summaries only'}
    if not isinstance(reply,dict) or reply.get('task_id')!=jid:raise ValueError('AppEEARS status identifies a different task')
    return {'task_id':jid,'status':reply.get('status'),'percent':100 if reply.get('status')=='done' else 0,'message':'NASA AppEEARS is preparing the selected polygon'}


def decode_statistics(raw,variable,start,end):
    rows=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if not rows.fieldnames or not {'Date','Dataset','Count','Mean'}.issubset(rows.fieldnames):raise ValueError('Invalid AppEEARS statistics schema')
    values={};aids=set()
    for row in rows:
        identity=(row.get('Dataset','')+' '+row.get('File Name','')).upper()
        if variable not in identity:continue
        date=dt.date.fromisoformat(row['Date'][:10]);month=date.year*100+date.month
        if date.day!=1 or month in values or not start<=date.year<=end:raise ValueError('Invalid or duplicate monthly MODIS date')
        aids.add(row.get('aid',row.get('ID','0')))
        if len(aids)>1:raise ValueError('AppEEARS returned more than the one requested area')
        count=float(row['Count']);mean=float(row['Mean'])
        # AppEEARS area-summary CSVs already contain physical index values,
        # unlike packed MODIS rasters. Never apply the raster scale again.
        if count<=0 or not math.isfinite(mean) or mean in {-3000.,-.3}:values[month]=None
        elif not -.20000001<=mean<=1.00000001:raise ValueError('AppEEARS summary is outside the physical vegetation-index range; refusing an unverified scale')
        else:values[month]=mean
    if not values:raise ValueError('AppEEARS statistics do not contain the requested vegetation measurement')
    return values


def fetch_region(variable,feature,start,end):
    if variable not in FIELDS:raise ValueError('This measurement has no AppEEARS mapping')
    west,south,east,north=feature['bbox']
    if (east-west)*(north-south)>300:raise ValueError('Choose a country, region or smaller preset for AppEEARS. Continental raster tasks are not submitted automatically.')
    key=hashlib.sha256(json.dumps([VERSION,variable,feature['geometry_version'],start,end]).encode()).hexdigest()
    path=CACHE/(key+'.json');pending_path=CACHE/(key+'.pending.json');hit=False
    try:
        saved=json.loads(path.read_text())
        if time.time()-saved['saved']>30*86400:raise ValueError('expired')
        values={int(k):v for k,v in saved['values'].items()};jid=saved['task_id'];retrieved=saved['retrieved'];hit=True
    except (OSError,ValueError,KeyError):
        bearer=token()
        if not bearer:raise ValueError('Connect AppEEARS in Data & Methods to fetch monthly vegetation. No manual dataset download is needed.')
        try:
            pending=json.loads(pending_path.read_text());jid=pending['task_id']
            if not re.fullmatch(r'[a-fA-F0-9-]{36}',jid):raise ValueError('Invalid saved AppEEARS task identity')
            task=remote_status(_request('status/'+jid,bearer=bearer),jid)
        except FileNotFoundError:
            task=_request('task',method='POST',body=task_spec(variable,feature,start,end),bearer=bearer)
        jid=task.get('task_id','')
        if not re.fullmatch(r'[a-fA-F0-9-]{36}',jid):raise ValueError('Invalid AppEEARS processing identity')
        nasa_data._atomic_write(pending_path,json.dumps({'task_id':jid}).encode())
        complete=False
        try:
            deadline=time.monotonic()+21600
            while task.get('status')!='done':
                jobs.check_cancelled()
                if task.get('status') in {'error','failed','cancelled'}:raise ValueError('NASA AppEEARS could not process the vegetation request')
                if time.monotonic()>deadline:raise ValueError('AppEEARS processing exceeded six hours; retry later or choose a smaller area')
                jobs.progress(task.get('percent',0),100,task.get('message','NASA AppEEARS is processing monthly vegetation for the selected polygon'))
                task=remote_status(_request('status/'+jid,bearer=bearer),jid)
                if task.get('status')!='done':time.sleep(5)
            complete=True
            bundle=_request('bundle/'+jid,bearer=bearer)
            selected=summary_file(bundle.get('files',[]))
            values=decode_statistics(_request('bundle/'+jid+'/'+selected['file_id'],bearer=bearer,raw=True),variable,start,end)
        finally:
            if not complete:
                try:_request('task/'+jid,method='DELETE',bearer=bearer)
                except ValueError:pass
                pending_path.unlink(missing_ok=True)
        retrieved=dt.datetime.now(dt.timezone.utc).isoformat()
        nasa_data._atomic_write(path,json.dumps({'saved':time.time(),'values':values,'task_id':jid,'retrieved':retrieved}).encode())
        pending_path.unlink(missing_ok=True)
    observed=sorted(m for m,v in values.items() if v is not None)
    provenance={'provider':'nasa-appeears','source':'NASA AppEEARS / Terra MODIS','resource':'AppEEARS','dataset':'MOD13A3','collection_version':'061',
        'field':FIELDS[variable],'policy':'challenge_resource','citation':'https://doi.org/10.5067/MODIS/MOD13A3.061',
        'access':'AppEEARS polygon processing; statistics CSV only, no raster downloads',
        'aggregation':'AppEEARS monthly polygon summary mean; physical index values supplied by NASA, no additional raster scaling',
        'quality':'Monthly vegetation composites; fill and range checks applied. No additional per-pixel VI quality filtering or monthly valid-area audit; exploratory screening.',
        'geometry_version':feature['geometry_version'],'spatial_detail_available':False,'monthly_area_coverage_known':False,
        'resolution':'1 km','cache_hit':hit,'remote_job_id':jid,'retrieved_utc':retrieved,
        'first_observed_month':observed[0] if observed else None,'last_observed_month':observed[-1] if observed else None}
    return RegionalSeries(values,provenance)
