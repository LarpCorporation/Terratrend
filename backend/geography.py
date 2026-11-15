"""Versioned geographic selections shared by the map and the analysis engine.

Boundaries are cartographic reference data, separate from science observations.
Country/subregion membership follows Natural Earth's published UN groupings.
"""
import hashlib
import json
import math
import re
import threading
import unicodedata
import urllib.request
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "frontend" / "data"
CACHE = Path(__file__).resolve().parent / "cache" / "geography"
_LOCK = threading.RLock()
_FEATURES = {}
_ADMIN_LOADED = set()
_ADMIN_LOCKS = {}


def slug(text):
    ascii_name=unicodedata.normalize('NFKD',text).encode('ascii','ignore').decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", ascii_name).strip("_") or 'area_'+hashlib.sha256(text.encode()).hexdigest()[:12]


def polygons(geometry):
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return geometry["coordinates"]
    raise ValueError("Only Polygon and MultiPolygon selections are supported")


def bounds(geometry):
    pts = [p for poly in polygons(geometry) for p in poly[0]]
    return [min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts)]


def _feature(fid, name, level, geometry, parent=None, **meta):
    b = bounds(geometry)
    version = hashlib.sha256(json.dumps(geometry, separators=(",", ":")).encode()).hexdigest()[:16]
    return dict(id=fid, name=name, level=level, parent=parent, geometry=geometry,
                geometry_version=version, bbox=b, surface="land",
                desc=f"{name} · {level} · full boundary selection", **meta)


@lru_cache(maxsize=1)
def initialize():
    collection = json.loads((DATA / "countries.geojson").read_text())
    for item in collection["features"]:
        p = item["properties"]
        iso3 = p.get("ISO_A3_EH")
        if not iso3 or iso3 == "-99":
            iso3 = p["ADM0_A3"]
        continent = slug(p["CONTINENT"])
        if continent=="seven_seas_open_ocean":
            continent=slug(p["REGION_UN"])
            if continent=="americas":continent="south_america" if p["SUBREGION"]=="South America" else "north_america"
        sub = slug(p["SUBREGION"])
        # Antarctica has no UN subdivision in the source.
        if sub in {"antarctica", "seven_seas_open_ocean"}:
            sub = continent
        fid = "country:" + iso3.lower()
        if fid in _FEATURES:
            previous=_FEATURES[fid]
            geometry={"type":"MultiPolygon","coordinates":polygons(previous["geometry"])+polygons(item["geometry"])}
            previous.update(geometry=geometry,bbox=bounds(geometry),geometry_version=hashlib.sha256(json.dumps(geometry).encode()).hexdigest()[:16])
            continue
        _FEATURES[fid] = _feature(fid, p.get("NAME_EN") or p["ADMIN"], "country",
            item["geometry"], "subcontinent:" + sub, iso3=iso3,
            iso2=p.get("ISO_A2_EH", p.get("ISO_A2")), continent="continent:" + continent,
            center=[p.get("LABEL_X", 0), p.get("LABEL_Y", 0)],
            boundary_source="Natural Earth 1:50m", boundary_scheme="UN regional grouping")
    for level, key in [("subcontinent", "parent"), ("continent", "continent")]:
        groups = {}
        for f in list(_FEATURES.values()):
            if f["level"] == "country":
                groups.setdefault(f[key], []).append(f)
        for fid, children in groups.items():
            geometry = {"type": "MultiPolygon", "coordinates": [poly for f in children for poly in polygons(f["geometry"])]}
            parent = children[0]["continent"] if level == "subcontinent" else None
            _FEATURES[fid] = _feature(fid, fid.split(":")[1].replace("_", " ").title(), level,
                geometry, parent, children=[f["id"] for f in children],
                boundary_source="Natural Earth 1:50m", boundary_scheme="UN country membership; transcontinental countries assigned as whole units")
    for f in _FEATURES.values():
        if f["level"]=="continent":f["children"]=[s["id"] for s in _FEATURES.values() if s["level"]=="subcontinent" and s["parent"]==f["id"]]
    _load_admin("GHA", json.loads((DATA / "ghana-regions.geojson").read_text()),
                "Ghana regional boundaries · 16 regions", "495f4d9192fca74256536100b512006ba3702ffc")
    import catalog as science_catalog
    for preset in science_catalog.REGIONS:
        west,south,east,north=preset['bbox']
        fid='focus:'+preset['id']
        f=_feature(fid,preset['name'],'preset',{'type':'Polygon','coordinates':[
            [[west,south],[east,south],[east,north],[west,north],[west,south]]]},
            boundary_source='TerraTrend curated focus box; not an official ecological boundary',
            center=[(west+east)/2,(south+north)/2],selection_kind='bounds')
        f.update(surface=preset.get('surface','land'),desc=preset['desc']+' · preset focus box')
        _FEATURES[fid]=f
    return True


def _load_admin(iso3, collection, source, revision=""):
    seen=set()
    for item in collection.get("features", []):
        p = item.get("properties", {})
        name = p.get("shapeName") or p.get("region") or p.get("name") or p.get("NAME_1")
        if not name or not item.get("geometry"):
            continue
        fid = f"region:{iso3.lower()}:{slug(name)}"
        if fid in seen:fid+='_'+hashlib.sha256(str(p.get('shapeID') or item['geometry']).encode()).hexdigest()[:8]
        seen.add(fid)
        _FEATURES[fid] = _feature(fid, name, "region", item["geometry"],
            "country:" + iso3.lower(), iso3=iso3, boundary_source=source,
            boundary_revision=revision)
    _ADMIN_LOADED.add(iso3)
    country=_FEATURES.get("country:"+iso3.lower())
    if country:country["children"]=[f["id"] for f in _FEATURES.values() if f["level"]=="region" and f["parent"]==country["id"]]


def load_admin(country_id):
    initialize()
    country = _FEATURES.get(country_id)
    if not country or country["level"] != "country":
        raise ValueError("Choose a country before loading its administrative regions")
    iso3 = country["iso3"]
    with _LOCK:
        country_lock=_ADMIN_LOCKS.setdefault(iso3,threading.Lock())
    # A slow first download for one country must not block cached boundaries
    # or an unrelated country's request.
    with country_lock:
        if iso3 in _ADMIN_LOADED:
            return
        path = CACHE / f"{iso3}.json"
        if path.is_file():
            data = json.loads(path.read_text())
        else:
            def read_json(url):
                req = urllib.request.Request(url, headers={"User-Agent": "TerraTrend geography/1.0"})
                with urllib.request.urlopen(req, timeout=25) as response:
                    raw = response.read(12_000_001)
                if len(raw) > 12_000_000:
                    raise ValueError("Boundary file exceeds the supported size")
                return json.loads(raw)
            try:
                meta = read_json(f"https://www.geoboundaries.org/api/current/gbOpen/{iso3}/ADM1/")
                url = meta.get("simplifiedGeometryGeoJSON") or meta.get("gjDownloadURL")
                from urllib.parse import urlparse
                if not url or urlparse(url).hostname not in {"github.com", "raw.githubusercontent.com", "media.githubusercontent.com", "www.geoboundaries.org", "geoboundaries.org"}:
                    raise ValueError("Unsupported boundary download source")
                data = {"collection": read_json(url), "revision": meta.get("boundaryID", ""),
                        "source": f"geoBoundaries gbOpen · {meta.get('boundaryYearRepresented', '')}"}
            except Exception as e:
                raise ValueError(f"Administrative boundaries are not available locally for {country['name']}. Online boundary loading failed; retry with network access. ({type(e).__name__})") from e
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))
        with _LOCK:
            _load_admin(iso3, data["collection"], data["source"], data.get("revision", ""))


def resolve(fid):
    if not isinstance(fid,str):raise ValueError("Geographic IDs must be strings")
    initialize()
    if re.fullmatch(r"custom:[a-f0-9]{20}",fid) and fid not in _FEATURES:
        path=CACHE / 'custom' / (fid.split(':')[1]+'.json')
        if path.is_file():register_custom(json.loads(path.read_text()),persist=False)
    if fid.startswith("region:") and fid not in _FEATURES:
        parts = fid.split(":")
        if len(parts) == 3:
            load_admin("country:" + parts[1])
    return _FEATURES.get(fid)


def register_custom(body,persist=True):
    """Validate a user-drawn boundary; observations still use the same adapter.

    Store geometry by content identity so A and B can use independent methods
    and job requests survive a normal server restart without changing the area.
    """
    initialize()
    geometry=body.get('geometry')
    if not isinstance(geometry,dict):raise ValueError('A polygon selection is required')
    polys=polygons(geometry)
    if not isinstance(polys,list) or not 1<=len(polys)<=8:raise ValueError('Choose one area with no more than eight polygon parts')
    normalized=[];total=0;area=0.;R=6371.0088
    from spatial import unwrap
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def touches(a,b,p):return abs(cross(a,b,p))<1e-10 and min(a[0],b[0])-1e-10<=p[0]<=max(a[0],b[0])+1e-10 and min(a[1],b[1])-1e-10<=p[1]<=max(a[1],b[1])+1e-10
    def intersects(a,b,c,d):return (cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0) or touches(a,b,c) or touches(a,b,d) or touches(c,d,a) or touches(c,d,b)
    for polygon in polys:
        if not isinstance(polygon,list) or len(polygon)!=1:raise ValueError('Custom areas must be simple polygons without holes')
        ring=polygon[0]
        if not isinstance(ring,list) or not 4<=len(ring)<=1001:raise ValueError('A selection needs 3–1,000 vertices and a closed outline')
        clean=[]
        for point in ring:
            if not isinstance(point,list) or len(point)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in point):raise ValueError('Coordinates must be finite longitude/latitude pairs')
            lon,lat=map(float,point)
            if not (-180<=lon<=180 and -90<=lat<=90):raise ValueError('Coordinates outside Earth')
            clean.append([round(lon,6),round(lat,6)])
        total+=len(clean)
        if total>2000:raise ValueError('Selection exceeds 2,000 total vertices')
        if clean[0]!=clean[-1] or len(set(map(tuple,clean[:-1])))<3:raise ValueError('Close the outline with at least three distinct vertices')
        points=unwrap(clean)
        if abs(points[-1][0]-points[0][0])>180:raise ValueError('Polar lassos are not supported; use coordinate bounds')
        for i in range(len(points)-1):
            for j in range(i+2,len(points)-1):
                if i==0 and j==len(points)-2:continue
                if intersects(points[i],points[i+1],points[j],points[j+1]):raise ValueError('The selected outline crosses itself; redraw a simple area')
        area+=abs(sum(math.radians(points[i][0]-points[i-1][0])*(math.sin(math.radians(points[i][1]))+math.sin(math.radians(points[i-1][1]))) for i in range(1,len(points))))*R*R/2
        normalized.append([clean])
    if area<=.001:raise ValueError('Select an area larger than 1,000 square metres')
    geometry={'type':'Polygon' if len(normalized)==1 else 'MultiPolygon','coordinates':normalized[0] if len(normalized)==1 else normalized}
    canonical=geometry['type']+':'+ '|'.join(';'.join(','.join(f'{(v if v else 0):.6f}' for v in point) for point in poly[0]) for poly in normalized)
    version=hashlib.sha256(canonical.encode()).hexdigest()
    fid='custom:'+version[:20]
    if body.get('id') and body['id']!=fid:raise ValueError('Custom selection identity does not match its geometry')
    props=body.get('properties') or {}
    if not isinstance(props,dict):raise ValueError('Invalid selection properties')
    kind=props.get('selection_kind','lasso')
    if kind not in {'lasso','circle','square','bounds'}:raise ValueError('Unknown selection method')
    name=str(props.get('name') or 'Custom area').strip()[:100]
    b=bounds(geometry);center=props.get('center',[(b[0]+b[2])/2,(b[1]+b[3])/2])
    if not isinstance(center,list) or len(center)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in center) or not (-180<=center[0]<=180 and -90<=center[1]<=90):raise ValueError('Invalid selection centre')
    f=_feature(fid,name,'custom',geometry,center=center,selection_kind=kind,area_km2=round(area,4),boundary_source='User-defined selection')
    f.update(surface='mixed',desc=f'{name} · {area:,.1f} km² · user-defined boundary')
    with _LOCK:
        _FEATURES[fid]=f
        if persist:
            path=CACHE/'custom'/(fid.split(':')[1]+'.json');path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps({'type':'Feature','geometry':geometry,'properties':public(f)}))
    return {'type':'Feature','id':fid,'geometry':geometry,'properties':public(f)}


def public(f):
    return {k: v for k, v in f.items() if k != "geometry"}


def catalog():
    initialize()
    with _LOCK: features=list(_FEATURES.values())
    return [public(f) for f in sorted(features, key=lambda f: f["name"])]


def collection(level="continent", parent=None):
    initialize()
    if level not in {"continent", "subcontinent", "country", "region", "preset"}:
        raise ValueError("Unknown geographic level")
    if level == "region":
        load_admin(parent or "country:gha")
        parent = parent or "country:gha"
    features = []
    for f in list(_FEATURES.values()):
        if f["level"] != level:
            continue
        if parent and f.get("parent") != parent and f.get("continent") != parent:
            continue
        features.append({"type": "Feature", "id": f["id"], "properties": public(f), "geometry": f["geometry"]})
    return {"type": "FeatureCollection", "features": features,
            "scheme": "Curated focus boxes; not official ecological boundaries" if level=='preset' else "UN regional country membership (Natural Earth); administrative regions as published",
            "level": level, "parent": parent}
