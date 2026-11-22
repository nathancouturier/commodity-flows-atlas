"""
Derive land neighbours and coastal status for each country from the TopoJSON base layer.

    python pipeline/geo/adjacency.py   ->  pipeline/cache/adjacency.json, data/countries/places.json

An arc shared by two countries is a land border; an arc used by one country only is coastline.
Countries whose only "coast" is the Caspian Sea are treated as landlocked for ocean shipping.
Only mainland borders count: the borders listed in OVERSEAS_BORDERS (an overseas territory that shares a polygon with
its country) are moved from `neighbours` to `overseas`. Territories that BACI reports but the base map has no polygon
for (pipeline/geo/places_extra.json) are written under `extra`, and the coastal ones are added to `coastal`.
"""
import json
import math
from collections import defaultdict, namedtuple

topo = json.load(open("data/geo/countries.topo.json"))
geoms = topo["objects"]["countries"]["geometries"]
arc_users = defaultdict(set)


def arcs_of(g):
    a = g.get("arcs", [])
    if g["type"] == "Polygon":
        return [x for ring in a for x in ring]
    if g["type"] == "MultiPolygon":
        return [x for poly in a for ring in poly for x in ring]
    return []


for g in geoms:
    c = g["properties"]["c"]
    for x in arcs_of(g):
        arc_users[x if x >= 0 else ~x].add(c)

neigh = defaultdict(set)
coastal = set()
for users in arc_users.values():
    if len(users) == 1:
        coastal |= users
    else:
        for u in users:
            neigh[u] |= users - {u}

CASPIAN_ONLY = {"KAZ", "TKM", "AZE"}
coastal -= CASPIAN_ONLY

# A border that exists only because an overseas territory is part of the country's polygon. Explicit list, never a
# distance threshold: the check below prints the longest remaining borders so that a new one is noticed.
Overseas = namedtuple("Overseas", "pair reason")
OVERSEAS_BORDERS = [
    Overseas(("FRA", "BRA"), "French Guiana (part of France) borders Brazil; metropolitan France does not"),
    Overseas(("FRA", "SUR"), "French Guiana (part of France) borders Suriname; metropolitan France does not"),
]
for o in OVERSEAS_BORDERS:
    a, b = o.pair
    neigh[a].discard(b)
    neigh[b].discard(a)

# BACI codes with no polygon in the base map (and so none in data/countries/index.json)
extra = json.load(open("pipeline/geo/places_extra.json"))
coastal |= {p["c"] for p in extra if p["coastal"]}
# a former state made of countries of the map (Serbia and Montenegro) borders what its parts border
for p in extra:
    parts = set(p.get("parts", []))
    for c in set().union(*(neigh[x] for x in parts)) - parts if parts else ():
        neigh[p["c"]].add(c)
        neigh[c].add(p["c"])

index = {c["c"]: c for c in json.load(open("data/countries/index.json"))}


def km(a, b):
    (x1, y1), (x2, y2) = (math.radians(v) for v in a), (math.radians(v) for v in b)
    h = math.sin((y2 - y1) / 2) ** 2 + math.cos(y1) * math.cos(y2) * math.sin((x2 - x1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


far = sorted(
    ((round(km(index[a]["at"], index[b]["at"])), a, b) for a in neigh for b in neigh[a] if a < b and a in index and b in index),
    reverse=True,
)
print("longest remaining borders (label point to label point, km); check that each is a mainland border:", far[:6])

out = {
    "coastal": sorted(coastal),
    "neighbours": {k: sorted(v) for k, v in sorted(neigh.items()) if v},
    "overseas": [list(o.pair) for o in OVERSEAS_BORDERS],
    "overseasWhy": {"-".join(o.pair): o.reason for o in OVERSEAS_BORDERS},
    "extra": extra,
}
json.dump(out, open("pipeline/cache/adjacency.json", "w"), indent=0)
json.dump([{"c": p["c"], "name": p["name"]} for p in extra], open("data/countries/places.json", "w"), indent=0)
print("coastal", len(coastal), "with neighbours", len(neigh))
print("landlocked sample", sorted({g['properties']['c'] for g in geoms} - coastal)[:60])
print("CHN", out["neighbours"].get("CHN")); print("USA", out["neighbours"].get("USA"))
