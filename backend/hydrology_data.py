"""Monthly GLDAS point series, aggregated over every intersecting source cell."""
import csv
import datetime as dt
import hashlib
import io
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from pathlib import Path

import requests
import jobs
import nasa_data
import spatial

BASE='https://api.giovanni.earthdata.nasa.gov/timeseries'
PRODUCT='GLDAS_NOAH025_M'
FIELDS={
    'GLDAS_SM_TOP':('SoilMoi0_10cm_inst','kg m-2',1.,0.),
    'GLDAS_SOILT':('SoilTMP0_10cm_inst','K',1.,-273.15),
    'GLDAS_WIND':('Wind_f_inst','m s-1',1.,0.),
}
CACHE=Path(__file__).resolve().parent/'cache'/'hydrology'
MAX_CELLS=512


def plan(feature):
    west,south,east,north=feature['bbox']
    if south < -60 or east < west or (east-west)*(north-south)/.0625>MAX_CELLS*2:
        raise ValueError('Hydrology supports at most 512 native cells per area. Choose a smaller region within 60°S–90°N; no sparse sampling is substituted.')
    planned=spatial.cells(feature['id'],.25,.25,-179.875,-59.875)
    if not planned or len(planned)>MAX_CELLS:raise ValueError('Choose a smaller Hydrology area: the native-cell limit is 512.')
    return planned


def _request(params,bearer):
    try:
        with requests.Session() as s:
            s.auth=lambda r:r
            with s.get(BASE,params=params,headers={'Authorization':'Bearer '+bearer,'User-Agent':'TerraTrend/1.0'},
                       timeout=(10,60),stream=True,allow_redirects=False) as r:
                if r.status_code in {401,403}:raise nasa_data.EarthdataRequired('Hydrology needs a valid Earthdata connection. Open Data & Methods to reconnect.')
                if r.status_code!=200:raise ValueError(f'Hydrology service returned HTTP {r.status_code}; no other dataset was substituted.')
                body=bytearray()
                for part in r.iter_content(64000):
                    jobs.check_cancelled();body.extend(part)
                    if len(body)>2_000_000:raise ValueError('Hydrology response exceeds the 2 MB limit')
                return bytes(body)
    except requests.RequestException as e:raise ValueError('Cannot reach NASA Hydrology Time Series; retry later.') from e


def decode_csv(raw,variable,lon,lat,start,end):
    rows=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
    header=next((i for i,r in enumerate(rows) if r and r[0]=='Timestamp (UTC)'),None)
    if header is None or rows[header]!=['Timestamp (UTC)','Data']:raise ValueError('Hydrology returned an invalid time-series schema')
    meta={r[0]:r[1] for r in rows[:header] if len(r)==2}
    field,unit,scale,offset=FIELDS[variable]
    try:
        if meta['prod_name']!='GLDAS_NOAH025_M.2.1' or meta['param_short_name']!=field or meta['unit']!=unit:
            raise ValueError('Hydrology product, field or units differ from the requested monthly measurement')
        if any(not math.isclose(float(meta[k]),v,abs_tol=1e-6) for k,v in [('lon',lon),('lat',lat),('lon_resolution',.25),('lat_resolution',.25)]):
            raise ValueError('Hydrology returned a different native cell')
        fill=float(meta['undef'])
        values={}
        for row in rows[header+1:]:
            if not row:continue
            if len(row)!=2:raise ValueError('Invalid Hydrology record')
            date=dt.datetime.fromisoformat(row[0]);month=date.year*100+date.month
            if date.day!=1 or month in values or not start<=date.year<=end:raise ValueError('Invalid or duplicate monthly Hydrology date')
            value=float(row[1]) if row[1].strip() else float('nan')
            values[month]=value*scale+offset if math.isfinite(value) and not math.isclose(value,fill) else None
    except (KeyError,TypeError) as e:raise ValueError('Hydrology CSV lacks required source metadata') from e
    if not values:raise ValueError('Hydrology returned no observations')
    return values


def fetch_region(variable,feature,start,end):
    if variable not in FIELDS:raise ValueError('This measurement has no Hydrology mapping')
    planned=plan(feature)
    bearer=nasa_data.token()
    if not bearer:raise nasa_data.EarthdataRequired('Connect Earthdata in Data & Methods for Hydrology Time Series.')
    field=FIELDS[variable][0]
    grid=spatial.Grid(weights={(x,y):w for x,y,w in planned});grid.expected_weight=sum(grid.weights.values())
    def cell(lon,lat):
        jobs.check_cancelled()
        key=hashlib.sha256(json.dumps(['hydrology-monthly-v1',variable,lon,lat,start,end]).encode()).hexdigest()
        path=CACHE/(key+'.json');hit=False
        try:
            saved=json.loads(path.read_text())
            if time.time()-saved['saved']>30*86400:raise ValueError('expired')
            values={int(m):v for m,v in saved['values'].items()};hit=True
        except (OSError,ValueError,KeyError):
            raw=_request({'data':PRODUCT+'_2_1_'+field,'location':f'[{lat},{lon}]',
                          'time':f'{start}-01-01T00:00:00/{end}-12-31T23:59:59'},bearer)
            values=decode_csv(raw,variable,lon,lat,start,end)
            nasa_data._atomic_write(path,json.dumps({'saved':time.time(),'values':values}).encode())
        return lon,lat,values,hit
    cached=0
    with ThreadPoolExecutor(max_workers=3,thread_name_prefix='hydrology-series') as pool:
        # Batches keep queued work and cancellation bounded.
        for offset in range(0,len(planned),3):
            futures=[pool.submit(copy_context().run,cell,x,y) for x,y,w in planned[offset:offset+3]]
            for future in as_completed(futures):
                lon,lat,values,hit=future.result();grid.setdefault(lon,{})[lat]=values;cached+=int(hit)
            jobs.progress(min(offset+3,len(planned)),len(planned),f'Hydrology {field}: native-cell monthly series ({cached} cached)')
    observed=sorted({m for c in grid.values() for s in c.values() for m,v in s.items() if v is not None})
    grid.provenance={'provider':'nasa-hydrology','source':'NASA Hydrology Time Series / GLDAS','resource':'Hydrology Time Series',
        'dataset':PRODUCT,'collection_version':'2.1','field':field,'policy':'challenge_resource',
        'citation':'https://doi.org/10.5067/SXAVCZFAQLNO','access':'Monthly point-series API for every intersecting GLDAS source cell',
        'aggregation':'Native-cell polygon overlap × cos(latitude); at least 80% selected area each month',
        'quality':'GLDAS model estimates; provider fill excluded. Soil water mass is not a saturation fraction; wind is near-surface forcing, not a verified 2 m measurement.',
        'geometry_version':feature['geometry_version'],'dlon':.25,'dlat':.25,'expected_cells':len(planned),
        'available_cells':sum(len(c) for c in grid.values()),'cached_series':cached,'monthly_area_coverage_known':True,
        'first_observed_month':observed[0] if observed else None,'last_observed_month':observed[-1] if observed else None,
        'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    return grid
