"""
Country of each route end (load / discharge area), from the route's end points and the
Natural Earth country polygons of the base map (data/geo/countries.topo.json).

    python pipeline/freight/route_countries.py     # adds "ends": [iso3_a, iso3_b] to data/freight/routes.json

build_freight.py calls add_end_countries() before writing routes.json. The site uses "ends" (with the
route's trade corridor) to keep only the routes that load or discharge in a selected country.
Ports sit on the coast, often just outside the 1:50m polygon: the nearest country within ~3 degrees (offshore loading points)
is taken when the point is in the sea.
"""
import json
import os

from shapely.geometry import Point, Polygon, MultiPolygon
from shapely.strtree import STRtree

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOPO = os.path.join(ROOT, "data", "geo", "countries.topo.json")
MAX_DEG = 3.0


def _country_shapes():
    topo = json.load(open(TOPO))
    sx, sy = topo["transform"]["scale"] if "transform" in topo else (1, 1)
    tx, ty = topo["transform"]["translate"] if "transform" in topo else (0, 0)
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            if "transform" in topo:
                x += dx
                y += dy
                pts.append((x * sx + tx, y * sy + ty))
            else:
                pts.append((dx, dy))
        arcs.append(pts)

    def ring(idx):
        out = []
        for i in idx:
            pts = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(pts if not out else pts[1:])
        return out

    shapes, codes = [], []
    for g in topo["objects"]["countries"]["geometries"]:
        c = g["properties"].get("c")
        if not c or c == "-99":
            continue
        polys = [g["arcs"]] if g["type"] == "Polygon" else g["arcs"] if g["type"] == "MultiPolygon" else []
        parts = []
        for p in polys:
            rings = [ring(r) for r in p]
            if len(rings[0]) >= 4:
                parts.append(Polygon(rings[0], [r for r in rings[1:] if len(r) >= 4]).buffer(0))
        if parts:
            shapes.append(MultiPolygon([q for s in parts for q in (s.geoms if hasattr(s, "geoms") else [s])]))
            codes.append(c)
    return shapes, codes


_CACHE = None


def country_at(lon, lat):
    """ISO3 of the country containing (lon, lat), else the nearest one within MAX_DEG, else None."""
    global _CACHE
    if _CACHE is None:
        shapes, codes = _country_shapes()
        _CACHE = (STRtree(shapes), shapes, codes)
    tree, shapes, codes = _CACHE
    p = Point(lon, lat)
    for i in tree.query(p):
        if shapes[i].contains(p):
            return codes[i]
    best, dist = None, MAX_DEG
    for i in tree.query(p.buffer(MAX_DEG)):
        d = shapes[i].distance(p)
        if d < dist:
            best, dist = codes[i], d
    return best


def add_end_countries(routes):
    for r in routes:
        a, b = r.get("a"), r.get("b")
        # `_ends`: the country build_freight.py knows for a terminal (Basrah Oil Terminal is in Iraq, although its point is nearer Iran)
        known = r.pop("_ends", None) or [None, None]
        if a and b:
            r["ends"] = [known[0] or country_at(*a), known[1] or country_at(*b)]
    return routes


if __name__ == "__main__":
    path = os.path.join(ROOT, "data", "freight", "routes.json")
    routes = add_end_countries(json.load(open(path)))
    json.dump(routes, open(path, "w"), separators=(",", ":"))
    missing = [r["id"] for r in routes if None in r.get("ends", [None])]
    print(f"{len(routes)} routes; ends missing for: {missing or 'none'}")
