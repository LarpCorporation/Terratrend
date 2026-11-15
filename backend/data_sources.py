"""Science-data adapters. New map requests never silently fetch unlisted data.

Existing project POWER files remain available as explicitly labeled legacy
cache data. Challenge-resource imports carry user-supplied provenance.
"""
import csv
import datetime
import hashlib
import io
import json
import math
import re
import threading
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

import catalog
import power_client
import spatial
import nasa_data
import giovanni_data
import hydrology_data
import appeears_data
import station_data

PROVIDER = ContextVar("terratrend_provider", default="legacy-live")
AUTO_AREAS = ContextVar('terratrend_auto_areas', default=())
STORE = Path(__file__).resolve().parent / "cache" / "imports"
ALLOWED = {"giovanni": "Giovanni", "hydrology": "Hydrology Time Series",
           "appeears": "AppEEARS", "cdo": "Climate Data Online", "knmi": "KNMI Climate Explorer"}
_LOCK = threading.RLock()

ADAPTERS={'nasa-merra2':nasa_data,'nasa-giovanni':giovanni_data,'nasa-hydrology':hydrology_data,
          'nasa-appeears':appeears_data,'noaa-cdo':station_data}
LINKED_ROUTES={variable:provider for provider in ('nasa-merra2','nasa-hydrology','nasa-appeears','noaa-cdo')
               for variable in ADAPTERS[provider].FIELDS}
LINKED_ROUTES.update({'T10M':'nasa-giovanni','QV10M':'nasa-giovanni'})


def supported(provider):
    if provider in {'auto','multi-source'}:return list(LINKED_ROUTES)
    if provider in ADAPTERS:return list(ADAPTERS[provider].FIELDS)
    return [v['id'] for v in catalog.CATALOG]


def _rectangle(feature):
    try:giovanni_data.rectangle(feature);return True
    except (ValueError,KeyError,TypeError):return False


def automatic_route(variable,feature,areas=()):
    label=next((v['name'] for v in catalog.CATALOG if v['id']==variable),variable)
    route=LINKED_ROUTES.get(variable)
    if not route:raise ValueError(f'{label} has no verified automatic data mapping yet. Choose an available measurement.')
    if variable in {'T2M','QV2M'} and all(_rectangle(a) for a in (areas or [feature])):route='nasa-giovanni'
    if route=='nasa-giovanni' and not _rectangle(feature):
        raise ValueError(f"{feature['name']}: {label} needs a latitude/longitude rectangle. Use coordinate bounds or a rectangular preset; your existing boundary is retained.")
    return route


def request_areas(spec):
    import geography
    ids=spec.get('features',[]) if spec.get('operation')=='overview' else [spec.get('region'),spec.get('compare_region')]
    if spec.get('relationship_scope')=='remote':ids=list(ids)+spec.get('target_regions',[])
    return [geography.resolve(fid) for fid in dict.fromkeys(ids) if fid]


def plan_request(spec):
    """Read-only preflight. No observation download or boundary substitution."""
    areas=request_areas(spec);provider=spec.get('provider','auto');operation=spec.get('operation','analyze')
    fields=spec.get('relationship_variables') if operation=='interconnections' else spec.get('variables')
    fields=fields or supported(provider)
    routes={a['id']:{} for a in areas};issues=[];warnings=[];excluded=[]
    for field in fields:
        for a in areas:
            try:
                route=automatic_route(field,a,areas) if provider=='auto' else LINKED_ROUTES.get(field) if provider=='multi-source' else provider
                if route in ADAPTERS and field not in ADAPTERS[route].FIELDS:raise ValueError('This measurement is not available in the advanced processing override. Choose Automatic processing.')
                if route=='nasa-giovanni':giovanni_data.rectangle(a)
                west,south,east,north=a['bbox'];width=(east-west)%360 if east<west else east-west
                if route=='nasa-hydrology':hydrology_data.plan(a)
                if route in {'nasa-appeears','noaa-cdo'} and (width*(north-south)>300 or east<west):
                    raise ValueError('Choose a smaller country, region or focus box for this measurement. Continental requests are not submitted automatically.')
                if route=='noaa-cdo' and operation=='overview':raise ValueError('Station summaries cannot color whole-area trends. Analyze the selected areas instead.')
                routes[a['id']][field]=route
            except (ValueError,KeyError) as e:
                message=str(e) if str(e).startswith(a['name']) else a['name']+' / '+next((v['name'] for v in catalog.CATALOG if v['id']==field),field)+': '+str(e)
                item={'region':a['id'],'variable':field,'message':message,'action':'bounds' if field in {'T10M','QV10M'} or provider=='nasa-giovanni' else 'smaller-area'}
                (excluded if operation=='scan' else issues).append(item)
    valid=[v for v in fields if all(v in routes[a['id']] for a in areas)]
    if provider=='auto' and len(areas)>1 and any(routes[a['id']].get('T2M')=='nasa-merra2' or routes[a['id']].get('QV2M')=='nasa-merra2' for a in areas):
        warnings.append('Temperature/humidity use the same native MERRA-2 product for both areas because at least one boundary is not a rectangle.')
    if any('noaa-cdo' in r.values() for r in routes.values()):warnings.append('Station observations are fixed-cohort summaries, not whole-area averages.')
    return {'routes':routes,'variables':valid,'issues':issues,'excluded':excluded,'warnings':warnings}


def providers():
    connection=nasa_data.status()
    out = [{"id": "nasa-merra2", "name": "NASA MERRA-2 · exact boundaries", "policy": "challenge_resource", "source": "NASA GES DISC / MERRA-2",
            "variables": connection["variables"], "configured": connection["configured"],
            "description": "Fetches native monthly NASA grids automatically for your boundary. Connect Earthdata in Data & Methods once; first analyses download and later runs reuse the cache."},
           {"id":"nasa-giovanni","name":"NASA Giovanni · rectangle summaries (preview)","policy":"challenge_resource",
            "source":"NASA Giovanni / MERRA-2","variables":list(giovanni_data.FIELDS),"geometry":"rectangle",
            "configured":connection['configured'],"description":"NASA calculates rectangle averages for temperature and humidity at 2 m and 10 m. Small monthly series; M2IMNXASM differs from native mode. No per-cell maps or monthly area-support audit. Choose a preset or coordinate rectangle; no raw-grid fallback."},
           {"id":"nasa-appeears","name":"NASA AppEEARS · monthly vegetation","source":"NASA AppEEARS / Terra MODIS","policy":"challenge_resource",
            "variables":list(appeears_data.FIELDS),"configured":appeears_data.status()['configured'],
            "description":"Monthly NDVI/EVI for your actual polygon. NASA processes the extraction; only summary CSVs are downloaded. Separate AppEEARS sign-in. No extra pixel-quality filter or monthly area audit."},
           {"id":"nasa-hydrology","name":"NASA Hydrology · monthly GLDAS","source":"NASA Hydrology Time Series / GLDAS","policy":"challenge_resource",
            "variables":list(hydrology_data.FIELDS),"configured":connection['configured'],
            "description":"Soil water mass, soil temperature and near-surface wind. Monthly histories for every intersecting 0.25° cell, then polygon weighting. Uses Earthdata; at most 512 cells per area."},
           {"id":"noaa-cdo","name":"NOAA Climate Data Online · stations","source":"NOAA NCEI / Climate Data Online observations","policy":"challenge_resource",
            "variables":list(station_data.FIELDS),"configured":True,
            "description":"Monthly temperature, rainfall and wind from stations inside the selected boundary. Fixed station cohort; not a country area average. Coverage varies. Public access API; no separate key needed."},
           {"id":"multi-source","name":"Linked datasets · NASA + NOAA","source":"Linked NASA / NOAA measurements","policy":"challenge_resource",
            "variables":list(LINKED_ROUTES),"configured":True,"routes":LINKED_ROUTES,
            "description":"Combine source-qualified measurements, such as MERRA-2 soil moisture and MODIS vegetation. Each keeps its own definition and provenance. Select 2–3 measurements for local relationship screening; missing source connections stay explicit."},
           {"id": "project-cache", "name": "Existing project cache", "policy": "legacy_unverified",
            "description": "NASA POWER cache only. This access route has not been verified against the challenge resource list; no new downloads."}]
    out.insert(0,{'id':'auto','name':'Automatic · choose compatible NASA / NOAA data','source':'Automatic NASA / NOAA routing',
        'policy':'challenge_resource','configured':True,'variables':list(LINKED_ROUTES),
        'description':'Chooses a verified source for each measurement and actual boundary. Prepared rectangle series are used when compatible; paired comparisons retain matching products. Actual sources accompany every result.'})
    if STORE.is_dir():
        for p in sorted(STORE.glob("*.json")):
            try:
                d = json.loads(p.read_text())
                out.append({"id": p.stem, "name": d["name"], "source": d["source"],
                            "policy": "user_import", "variable": d["variable"], "unit": d["unit"],
                            "description": "Imported challenge-resource data; provenance supplied by the uploader"})
            except (ValueError, KeyError):
                continue
    return out


def import_csv(body):
    source = body.get("source")
    if source not in ALLOWED:
        raise ValueError("Choose a resource from the challenge list")
    variable = next((v for v in catalog.CATALOG if v["id"] == body.get("variable")), None)
    if not variable:
        raise ValueError("Unknown variable")
    title = str(body.get("name", "")).strip()[:150]
    citation = str(body.get("citation", "")).strip()[:2000]
    if not title or not citation:
        raise ValueError("A dataset name and source citation are required")
    dlon, dlat = float(body.get("dlon", .625)), float(body.get("dlat", .5))
    if not (0.01 <= dlon <= 10 and 0.01 <= dlat <= 10):
        raise ValueError("Native cell spacing must be between 0.01 and 10 degrees")
    unit = str(body.get("unit", variable["unit"]))
    if unit != variable["unit"]:
        raise ValueError(f"Convert the input values to {variable['unit']} before importing")
    rows = csv.DictReader(line for line in str(body.get("csv", "")).splitlines() if line.strip() and not line.lstrip().startswith("#"))
    records = {}
    origin=None
    fill=body.get("fill_value","")
    fill=float(fill) if str(fill).strip() else None
    if fill is not None and not math.isfinite(fill):raise ValueError("Fill value must be finite")
    missing={-999.,-9999.,-99999.,-999999.}
    if fill is not None:missing.add(fill)
    for i, row in enumerate(rows):
        if i >= 500_000:
            raise ValueError("An import is limited to 500,000 monthly records")
        row = {str(k).strip().lower(): v for k,v in row.items() if k}
        try:
            lon = float(row.get("lon", row.get("longitude", "")))
            lat = float(row.get("lat", row.get("latitude", "")))
            if not math.isfinite(lon) or not math.isfinite(lat) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("Coordinate outside Earth")
            lon=(lon+180)%360-180
            if origin is None:origin=(lon,lat)
            steps=((lon-origin[0])/dlon,(lat-origin[1])/dlat)
            if any(abs(step-round(step))>1e-3 for step in steps):
                raise ValueError("Coordinates do not match the declared native grid spacing")
            raw_month = row.get("month", row.get("date", ""))
            digits = re.sub(r"[^0-9]", "", raw_month)
            month = int(digits[:6])
            if len(digits) < 6 or not (1900 <= month//100 <= datetime.date.today().year and 1 <= month%100 <= 12):
                raise ValueError("Use month dates in YYYY-MM format")
            raw_value=row.get("value",row.get(variable["id"].lower(),""))
            if raw_value is None or not raw_value.strip():continue
            value = float(raw_value)
            if not math.isfinite(value) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("Nonfinite value or coordinate outside Earth")
            if value in missing:continue
            key = f"{lon:.6f},{lat:.6f}"
            if str(month) in records.get(key, {}):
                raise ValueError("Duplicate cell/month; aggregate daily records to monthly first")
            records.setdefault(key, {})[str(month)] = value
        except (ValueError, TypeError) as e:
            raise ValueError(f"CSV row {i+2}: {e}") from e
    if not records:
        raise ValueError("CSV needs lon,lat,month,value columns and monthly grid-cell records")
    data = {"name": title, "source": ALLOWED[source], "source_id": source, "citation": citation,
            "variable": variable["id"], "unit": unit, "dlon": dlon, "dlat": dlat,
            "records": records, "policy": "user_import", "grid_origin": "Coordinates identify native cell centres; overlap uses declared spacing"}
    data["quality"]="Monthly observations prepared by uploader; provider QA flags not independently validated"
    data["fill_value"]=fill
    fid = "import-" + hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()[:16]
    STORE.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        (STORE / (fid + ".json")).write_text(json.dumps(data))
    return {"id": fid, "name": title, "cells": len(records), "records": sum(map(len,records.values()))}


@lru_cache(maxsize=2)
def _cache_index():
    index = {}
    for p in power_client.CACHE_DIR.glob("*.json"):
        match = re.fullmatch(r"P(.+)_S(\d+)_E(\d+)_x(-?[\d.]+)_y(-?[\d.]+)\.json", p.name)
        if not match:
            continue
        var, start, end, lon, lat = match.groups()
        dx, dy = (1.,1.) if var.startswith("ALLSKY") else (.625,.5)
        # Requests inside a source cell represent that same native measurement.
        x = round(round((float(lon)+180)/dx)*dx-180,6)
        y = round(round((float(lat)+90)/dy)*dy-90,6)
        index.setdefault((var,x,y),[]).append((int(start),int(end),p))
    return index


def fetch_region(variable, feature, start, end):
    provider = PROVIDER.get()
    if provider=='auto':provider=automatic_route(variable,feature,AUTO_AREAS.get() or [feature])
    if provider=='multi-source':
        provider=LINKED_ROUTES.get(variable)
        if not provider:raise ValueError('No linked source mapping for this measurement')
    if provider in ADAPTERS:return ADAPTERS[provider].fetch_region(variable,feature,start,end)
    imported = None
    if provider != "project-cache":
        if not re.fullmatch(r"import-[a-f0-9]{16}", provider):
            raise ValueError("Unknown data source")
        path = STORE / (provider + ".json")
        if not path.is_file():
            raise ValueError("Imported dataset not found")
        imported = json.loads(path.read_text())
        if imported["variable"] != variable:
            companion=None
            for other in STORE.glob("*.json"):
                candidate=json.loads(other.read_text())
                if candidate["variable"]==variable and candidate["name"]==imported["name"] and candidate["source"]==imported["source"]:
                    companion=candidate
                    break
            if companion is None:
                raise ValueError(f"This collection has no {variable} grid. Import that variable under the same dataset name and resource to investigate it.")
            imported=companion
    dx,dy = (imported["dlon"], imported["dlat"]) if imported else ((1.,1.) if variable.startswith("ALLSKY") else (.625,.5))
    planned = spatial.cells(feature["id"], dx, dy)
    grid = spatial.Grid(weights={(lon,lat):w for lon,lat,w in planned})
    if imported:
        # Source centres may have a different grid origin. Clip each actual
        # imported cell, rather than snapping arbitrary observations to a grid.
        all_months = [y*100+m for y in range(start,end+1) for m in range(1,13)]
        from spatial import unwrap, clip, area
        weights = {}
        prepared=[]
        for polygon in __import__('geography').polygons(feature["geometry"]):
            rings=[unwrap(r) for r in polygon]
            b=(min(p[0] for p in rings[0]),min(p[1] for p in rings[0]),max(p[0] for p in rings[0]),max(p[1] for p in rings[0]))
            prepared.append((rings,b))
        for key, values in imported["records"].items():
            lon,lat = map(float,key.split(","))
            w = 0.0
            for rings,b in prepared:
                centre = lon
                while centre-rings[0][0][0]>180: centre-=360
                while centre-rings[0][0][0]<-180: centre+=360
                if centre+dx/2<b[0] or centre-dx/2>b[2] or lat+dy/2<b[1] or lat-dy/2>b[3]:continue
                box=(centre-dx/2,max(-90,lat-dy/2),centre+dx/2,min(90,lat+dy/2))
                w += max(0.0,area(clip(rings[0],box),lat)-sum(area(clip(r,box),lat) for r in rings[1:]))
            if w>1e-10:
                weights[(lon,lat)] = w
                grid.setdefault(lon,{})[lat] = {m:float(values[str(m)]) for m in all_months if str(m) in values}
        # Expected support is the full selected land area, not only uploaded cells.
        grid.weights = weights
        grid.expected_weight = sum(w for _,_,w in planned)
        grid.provenance = {k:v for k,v in imported.items() if k != "records"}
    else:
        index = _cache_index()
        for lon,lat,w in planned:
            series = {}
            matches = [(a,b,p) for a,b,p in index.get((variable,lon,lat),[]) if a<=end and b>=start]
            # Keep observed overlapping months, never fill missing years. The
            # analysis reports actual monthly/annual coverage for this window.
            for a,b,p in sorted(matches,key=lambda x:(x[1]-x[0],x[2].stat().st_mtime)):
                try:
                    raw=json.loads(p.read_text())["data"]
                    values={int(k):power_client._scale(variable,power_client._clean(v)) for k,v in raw.items() if start*100<int(k)<=end*100+12 and 1<=int(k)%100<=12}
                    series.update({k:v for k,v in values.items() if v is not None})
                except (OSError,ValueError,KeyError):
                    continue
            grid.setdefault(lon,{})[lat] = series
        grid.expected_weight = sum(grid.weights.values())
        grid.provenance = {"source":"NASA POWER project cache", "dataset":"MERRA-2 / CERES as distributed by POWER",
            "policy":"legacy_unverified", "description":"Existing local files only; the access route is not verified against the challenge resource list"}
    available = sum(w for (lon,lat),w in grid.weights.items() if any(v is not None for v in grid.get(lon,{}).get(lat,{}).values()))
    grid.provenance.update({"provider":provider,"dlon":dx,"dlat":dy,"geometry_version":feature["geometry_version"],
        "aggregation":"Native-cell polygon overlap × cos(latitude); at least 80% area coverage each month",
        "available_area_fraction":min(1.,available/grid.expected_weight) if grid.expected_weight else 0.,
        "expected_cells":len(planned),"available_cells":sum(bool(v) for col in grid.values() for v in col.values())})
    return grid
