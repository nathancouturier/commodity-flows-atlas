"""
Derive land neighbours and coastal status for each country from the TopoJSON base layer.

    python pipeline/geo/adjacency.py   ->  pipeline/cache/adjacency.json

An arc shared by two countries is a land border; an arc used by one country only is coastline.
Countries whose only "coast" is the Caspian Sea are treated as landlocked for ocean shipping.
"""
import json
from collections import defaultdict

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
out = {"coastal": sorted(coastal), "neighbours": {k: sorted(v) for k, v in sorted(neigh.items())}}
json.dump(out, open("pipeline/cache/adjacency.json", "w"), indent=0)
print("coastal", len(coastal), "with neighbours", len(neigh))
print("landlocked sample", sorted({g['properties']['c'] for g in geoms} - coastal)[:60])
print("CHN", out["neighbours"].get("CHN")); print("USA", out["neighbours"].get("USA"))
