"""Optional server-averaged rectangle series from NASA Giovanni / Harmony.

This uses monthly instantaneous assimilation diagnostics, M2IMNXASM 5.12.4.
It does not substitute that product for native-mode M2TMNXSLV observations.
No polygon-to-box conversion, sparse sampling, or native-download fallback.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import math
import re
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse, urljoin

import requests
import jobs
import nasa_data
import spatial
import earthdata_credentials

BASE = "https://harmony.earthdata.nasa.gov"
PRODUCT = "M2IMNXASM"
CONCEPT = "C1276812823-GES_DISC"
FIELDS = {"T2M": (1., -273.15), "QV2M": (1000., 0.), "T10M": (1., -273.15), "QV10M": (1000., 0.)}
CACHE = Path(__file__).resolve().parent / "cache" / "giovanni"
VERSION = "giovanni-monthly-rectangle-v1"
OUTPUT_HOSTS = {f"{bucket}.s3{region}.amazonaws.com"
                for bucket in ("harmony-prod-public", "harmony-prod-staging")
                for region in ("", ".us-west-2", ".us-east-1")}
# The observed authenticated Harmony result redirect uses this delivery proxy.
# Restrict it to the NASA staging bucket and CSV paths; never send it EDL auth.
RESULT_CDN = 'dqzb5lcolc8fj.cloudfront.net'
RESULT_CDN_PATH = '/s3-ed54538b88f6e9fc0ec110d0f71c8fa0/harmony-prod-staging.s3.us-west-2.amazonaws.com/public/'


class RegionalSeries(spatial.Grid):
    def __init__(self, values, provenance):
        super().__init__()
        self.regional_series = values
        self.provenance = provenance
        self.expected_weight = 1.

    def __bool__(self):
        return bool(self.regional_series)


def rectangle(feature):
    geometry = feature.get("geometry", {})
    rings = geometry.get("coordinates", [])
    error = "Giovanni mode requires a latitude/longitude rectangle. Use native mode for this exact boundary."
    if geometry.get("type") != "Polygon" or len(rings) != 1 or len(rings[0]) < 5:
        raise ValueError(error)
    ring = rings[0]
    if any(len(p) != 2 or any(not isinstance(v, (int,float)) or not math.isfinite(v) for v in p) for p in ring):
        raise ValueError(error)
    west,south = min(p[0] for p in ring),min(p[1] for p in ring)
    east,north = max(p[0] for p in ring),max(p[1] for p in ring)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90) or east-west > 180:
        raise ValueError(error + " Rectangles crossing the date line require native mode.")
    edges = list(zip(ring,ring[1:]))
    area = abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in edges))/2
    if (ring[0] != ring[-1] or any(abs(a[0]-b[0])>1e-8 and abs(a[1]-b[1])>1e-8 for a,b in edges)
            or not math.isclose(area,(east-west)*(north-south),rel_tol=1e-9,abs_tol=1e-9)):
        raise ValueError(error)
    return west,south,east,north


def request_url(variable, feature, start, end):
    if variable not in FIELDS:
        raise ValueError(f"{variable} is not supported in Giovanni rectangle mode; choose native mode for its existing mapping.")
    west,south,east,north = rectangle(feature)
    params = [("variable",f"{PRODUCT}_5_12_4_{variable}"), ("subset",f"lon({west}:{east})"),
              ("subset",f"lat({south}:{north})"),
              ("subset",f'time("{start}-01-01T00:00:00Z":"{end}-12-31T23:59:59Z")'),
              ("format","text/csv"),("average","area"),("forceAsync","true"),
              ("skipPreview","true"),("ignoreErrors","false"),("label","terratrend-rectangle")]
    return f"{BASE}/{CONCEPT}/ogc-api-coverages/1.0.0/collections/parameter_vars/coverage/rangeset?"+urlencode(params)


def _destination(url, bearer=""):
    parsed = urlparse(url)
    nasa = parsed.hostname == "harmony.earthdata.nasa.gov"
    output = parsed.hostname in OUTPUT_HOSTS and parsed.path.startswith("/public/") and parsed.path.lower().endswith('.csv')
    output = output or (parsed.hostname==RESULT_CDN and parsed.path.startswith(RESULT_CDN_PATH) and parsed.path.lower().endswith('.csv'))
    if parsed.scheme != "https" or not (nasa or output) or (bearer and not nasa):
        raise ValueError("Unsupported Giovanni result destination")
    return nasa


def _request(url, bearer="", cancel=False):
    _destination(url,bearer)
    try:
        with requests.Session() as session:
            session.auth = lambda request: request
            for redirect in range(5):
                nasa=_destination(url)
                headers={"Accept":"application/json" if nasa and '/service-results/' not in url else "text/csv",
                         "User-Agent":"TerraTrend/1.0 (NASA Space Apps)"}
                if nasa and bearer:headers['Authorization']='Bearer '+bearer
                with session.get(url,headers=headers,timeout=(10,60) if not cancel else (3,5),
                                 stream=True,allow_redirects=False) as response:
                    if response.status_code in {301,302,303,307,308}:
                        target=urljoin(url,response.headers.get('Location',''))
                        if not response.headers.get('Location') or urlparse(target).hostname=='urs.earthdata.nasa.gov':
                            raise nasa_data.EarthdataRequired("Giovanni needs valid Earthdata authorization. Connect Earthdata in Data & Methods; no native download was substituted.")
                        _destination(target)
                        url=target
                        continue
                    if response.status_code==401:
                        raise nasa_data.EarthdataRequired("Giovanni needs valid Earthdata authorization. Connect Earthdata in Data & Methods; no native download was substituted.")
                    if response.status_code==403:
                        raise ValueError("NASA refused this request (HTTP 403). Check Giovanni authorization and cloud credits, or retry an expired result. No native download was substituted.")
                    if response.status_code not in {200,201,202}:
                        raise ValueError(f"NASA Giovanni returned HTTP {response.status_code}. No native download was substituted.")
                    body=bytearray()
                    for part in response.iter_content(64_000):
                        if not cancel: jobs.check_cancelled()
                        body.extend(part)
                        if len(body)>2_000_000: raise ValueError("Giovanni response exceeds the 2 MB limit")
                    return bytes(body)
            raise ValueError("NASA Giovanni returned too many redirects")
    except requests.RequestException as exc:
        raise ValueError("Cannot reach NASA Giovanni. Retry later; no native download was substituted.") from exc


def run_remote(variable, feature, start, end, bearer):
    reply = json.loads(_request(request_url(variable,feature,start,end),bearer=bearer))
    jid = reply.get("jobID", "")
    if not re.fullmatch(r"[a-fA-F0-9-]{36}",jid): raise ValueError("NASA returned an invalid processing-job identity")
    completed = False
    try:
        deadline = time.monotonic()+900
        while True:
            jobs.check_cancelled()
            status = reply.get("status")
            if status == "successful":
                completed = True
                break
            if status in {"failed","canceled","cancelled","complete_with_errors"}:
                raise ValueError("NASA Giovanni could not complete this request. Check source coverage, Earthdata access and your Giovanni quota; no native download was substituted.")
            if time.monotonic()>deadline: raise ValueError("Giovanni processing timed out; its remote job was cancelled")
            jobs.progress(0,1,"NASA Giovanni is calculating the rectangle average on its servers")
            reply=json.loads(_request(BASE+"/jobs/"+jid,bearer=bearer))
            if reply.get("status") not in {"successful","failed","canceled","cancelled","complete_with_errors"}:
                time.sleep(1.5)
        links=[v for v in reply.get("links",[]) if v.get("rel")=="data"
               and v.get("type","").split(';')[0] in {'text/csv','GEOTIFF/CSV'}
               and urlparse(v.get('href','')).path.lower().endswith('.csv')]
        if len(links)!=1: raise ValueError("Giovanni did not return one complete regional CSV")
        _destination(links[0]["href"])
        output=links[0]['href']
        return _request(output,bearer=bearer if urlparse(output).hostname=='harmony.earthdata.nasa.gov' else ''),jid
    finally:
        if not completed:
            try: _request(BASE+"/jobs/"+jid+"/cancel",bearer=bearer,cancel=True)
            except (ValueError,requests.RequestException): pass


def decode_csv(raw, variable, bounds, start, end):
    text=raw.decode("utf-8-sig")
    rows=list(csv.reader(io.StringIO(text)))
    expected="mean_"+PRODUCT+"_5_12_4_"+variable
    header=next((i for i,row in enumerate(rows) if row and row[0].strip().lower()=="time"),None)
    if header is None or rows[header] != ["time",expected]: raise ValueError("Giovanni CSV does not match the requested monthly field")
    metadata={r[0].strip().rstrip(':'):r[1] for r in rows[:header] if len(r)==2 and r[0].strip()}
    try:
        observed_bounds=[float(v) for v in metadata['User Bounding Box'].split(',')]
        fill=float(metadata['Fill Value'])
    except (KeyError,ValueError) as exc: raise ValueError("Giovanni CSV lacks its bounding box or fill-value metadata") from exc
    if len(observed_bounds)!=4 or any(not math.isclose(a,b,abs_tol=1e-6) for a,b in zip(observed_bounds,bounds)):
        raise ValueError("Giovanni returned data for a different rectangle")
    values={};scale,offset=FIELDS[variable]
    for row in rows[header+1:]:
        if not row or not any(row):continue
        if len(row)!=2:raise ValueError("Invalid Giovanni monthly record")
        try:
            date=dt.datetime.fromisoformat(row[0].strip().replace('Z','+00:00'))
            month=date.year*100+date.month
            value=float(row[1]) if row[1].strip() else None
        except ValueError as exc:raise ValueError("Invalid Giovanni monthly observation") from exc
        if month in values:raise ValueError("Giovanni returned multiple observations per month for a monthly product")
        if not start <= date.year <= end:raise ValueError("Giovanni returned dates outside the requested period")
        values[month]=None if value is None or not math.isfinite(value) or math.isclose(value,fill,abs_tol=1e-5) else value*scale+offset
    if not values:raise ValueError("Giovanni returned no monthly observations")
    return values


def fetch_region(variable, feature, start, end):
    bounds=rectangle(feature)
    request_url(variable,feature,start,end)  # Validate before credentials, cache or remote work.
    bearer=nasa_data.token()
    if not bearer:raise nasa_data.EarthdataRequired("Connect Earthdata in Data & Methods to request a Giovanni rectangle summary.")
    # Adopt a connected session after the user enables remembering, including
    # an adapter update without restarting the process holding that session.
    if earthdata_credentials.should_remember():earthdata_credentials.remember(bearer)
    key=hashlib.sha256(json.dumps([VERSION,variable,bounds,start,end]).encode()).hexdigest()
    path=CACHE/(key+'.json');hit=False
    retrieved=dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        cached=json.loads(path.read_text())
        if time.time()-cached['saved']>86400:raise ValueError('expired')
        values={int(k):v for k,v in cached['values'].items()};jid=cached['job_id'];retrieved=cached['retrieved_utc'];hit=True
    except (OSError,ValueError,KeyError):
        raw,jid=run_remote(variable,feature,start,end,bearer)
        values=decode_csv(raw,variable,bounds,start,end)
        jobs.check_cancelled()
        nasa_data._atomic_write(path,json.dumps({'saved':time.time(),'values':values,'job_id':jid,'retrieved_utc':retrieved}).encode())
    observed=sorted(m for m,v in values.items() if v is not None)
    provenance={"provider":"nasa-giovanni","source":"NASA Giovanni / MERRA-2", "resource":"Giovanni",
        "dataset":PRODUCT,"collection_version":"5.12.4","field":variable,"policy":"challenge_resource",
        "citation":"https://disc.gsfc.nasa.gov/datasets/M2IMNXASM_5.12.4/summary",
        "access":"Giovanni area averaging through NASA Harmony; regional CSV only",
        "aggregation":"NASA server rectangle average; monthly spatial support is not supplied",
        "quality":"Monthly mean instantaneous assimilation diagnostics; a different product from native mode. Cell weighting follows NASA's service.",
        "geometry_version":feature['geometry_version'],"requested_bbox":bounds,"spatial_detail_available":False,
        "monthly_area_coverage_known":False,"dlon":.625,"dlat":.5,"cache_hit":hit,"remote_job_id":jid,
        "requested_months":12*(end-start+1),"published_months":len(values),
        "first_observed_month":observed[0] if observed else None,"last_observed_month":observed[-1] if observed else None,
        "retrieved_utc":retrieved}
    return RegionalSeries(values,provenance)
