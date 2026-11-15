"""Polygon/native-cell overlap and area weights, with no GIS dependency.

Overlap is clipped in lon/lat and weighted by cos(latitude). This is a
documented small-cell spherical-area approximation, not a point-sample mean.
"""
import math
from functools import lru_cache
import geography


class Grid(dict):
    def __init__(self, *args, weights=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.weights = weights or {}
        self.provenance = {}


def unwrap(ring):
    out = []
    for x, y, *_ in ring:
        if out:
            while x - out[-1][0] > 180:
                x -= 360
            while x - out[-1][0] < -180:
                x += 360
        out.append((x, y))
    return out


def clip(ring, box):
    result = ring
    for axis, edge, lower in [(0, box[0], True), (0, box[2], False), (1, box[1], True), (1, box[3], False)]:
        src, result = result, []
        if not src:
            break
        prev = src[-1]
        inside = lambda p: p[axis] >= edge if lower else p[axis] <= edge
        for cur in src:
            if inside(cur) != inside(prev):
                t = (edge - prev[axis]) / (cur[axis] - prev[axis])
                result.append((prev[0] + t*(cur[0]-prev[0]), prev[1] + t*(cur[1]-prev[1])))
            if inside(cur):
                result.append(cur)
            prev = cur
    return result


def area(ring, latitude=None):
    if len(ring) < 3:
        return 0.0
    planar = abs(sum(ring[i-1][0]*p[1] - p[0]*ring[i-1][1] for i, p in enumerate(ring))) / 2
    return planar * max(0.0, math.cos(math.radians(latitude if latitude is not None else sum(p[1] for p in ring)/len(ring))))


@lru_cache(maxsize=128)
def cells(feature_id, dlon=0.625, dlat=0.5, origin_lon=-180., origin_lat=-90.):
    feature = geography.resolve(feature_id)
    if not feature:
        raise ValueError("Unknown geographic selection")
    weights = {}
    for polygon in geography.polygons(feature["geometry"]):
        rings = [unwrap(ring) for ring in polygon]
        outer = rings[0]
        x0, x1 = min(p[0] for p in outer), max(p[0] for p in outer)
        y0, y1 = min(p[1] for p in outer), max(p[1] for p in outer)
        for iy in range(max(0, math.ceil((y0-origin_lat-dlat/2)/dlat)), min(math.floor((90-origin_lat)/dlat), math.floor((y1-origin_lat+dlat/2)/dlat))+1):
            lat = origin_lat + iy*dlat
            # Clip to a latitude strip once. This avoids repeatedly scanning
            # a continental coastline for every native cell in that strip.
            strip=[clip(r,(x0-1,max(-90,lat-dlat/2),x1+1,min(90,lat+dlat/2))) for r in rings]
            if len(strip[0])<3:continue
            sx0,sx1=min(p[0] for p in strip[0]),max(p[0] for p in strip[0])
            for ix in range(math.ceil((sx0-origin_lon-dlon/2)/dlon), math.floor((sx1-origin_lon+dlon/2)/dlon)+1):
                lon = origin_lon + ix*dlon
                box = (lon-dlon/2, max(-90,lat-dlat/2), lon+dlon/2,min(90,lat+dlat/2))
                overlap = area(clip(strip[0], box),lat) - sum(area(clip(ring, box),lat) for ring in strip[1:])
                if overlap > 1e-10:
                    key = (round((lon+180)%360-180, 6), round(lat, 6))
                    weights[key] = weights.get(key, 0.0) + overlap
    return tuple((lon, lat, weight) for (lon, lat), weight in sorted(weights.items()))


def weighted_series(grid, months):
    weights = getattr(grid, "weights", {})
    out, support = [], []
    for month in months:
        total, valid = 0.0, 0.0
        for lon in grid:
            for lat, values in grid[lon].items():
                value = values.get(month)
                if value is not None:
                    w = weights.get((lon,lat), 1.0)
                    total += w*value
                    valid += w
        out.append(round(total/valid, 6) if valid else None)
        support.append(valid)
    return out, support
