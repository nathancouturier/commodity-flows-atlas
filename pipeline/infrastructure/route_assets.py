"""
The infrastructure asset that each port of a freight route is, so that the route page links its ports to their pages.

    from route_assets import route_port_assets           # build_freight.py: out["from"]["assets"] = ...
    python pipeline/infrastructure/route_assets.py       # list the route ports that are not assets (hand-written and
                                                         # generated routes: routes_def.json and data/freight/routes.json)

A route port ({"name", "c"} in pipeline/freight/routes_def.json) is the asset of the same country whose name, or a part
of it (before " (", either side of " / ", or inside the brackets), is the route's name for the port: "Tubarao" is
"Tubarao (Vitoria)", "Shanghai" is "Shanghai". ALIAS names the assets whose name differs from the routes' word for the
place ("Basra" is the Basrah Oil Terminal, "Barrow Island" is Gorgon LNG). A port that is no asset gets None.
"""
import glob
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
INFRA = os.path.join(ROOT, "data", "infrastructure")
ROUTES_DEF = os.path.join(ROOT, "pipeline", "freight", "routes_def.json")
ROUTES_PUB = os.path.join(ROOT, "data", "freight", "routes.json")  # the published routes, the generated ones included
PORT_INDEX = os.path.join(ROOT, "data", "freight", "ports.json")
# the types a route port can be, in the order they are tried (an LNG cargo tries the LNG terminals first)
PORT_TYPES = ("port", "lng-export", "lng-import", "storage", "field", "refinery")

# (name in the routes, country) -> "type:id", where the asset's name is not the routes' word for the place
ALIAS = {
    ("New Orleans", "USA"): "port:south-louisiana",
    ("Ningbo", "CHN"): "port:ningbo-zhoushan",
    ("Basrah", "IRQ"): "port:basrah-oil-terminal",
    ("Basra", "IRQ"): "port:basrah-oil-terminal",
    ("Hay Point", "AUS"): "port:hay-point-dalrymple-bay",
    ("Dalrymple Bay", "AUS"): "port:hay-point-dalrymple-bay",
    ("Richards Bay", "ZAF"): "port:richards-bay",
    ("Rosario", "ARG"): "port:rosario-up-river",
    ("Pasir Gudang", "MYS"): "port:johor-port-pasir-gudang",
    ("Los Angeles", "USA"): "port:los-angeles-long-beach",
    ("Long Beach", "USA"): "port:los-angeles-long-beach",
    ("New York", "USA"): "port:new-york-new-jersey",
    ("Portland", "USA"): "port:portland-oregon",
    ("Stabroek FPSOs", "GUY"): "field:stabroek",
    ("Jamnagar", "IND"): "refinery:jamnagar",
    # LNG terminals named by their place
    ("Sabine Pass", "USA"): "lng-export:sabine-pass-lng",
    ("Cameron", "USA"): "lng-export:cameron-lng",
    ("Freeport", "USA"): "lng-export:freeport-lng",
    ("Ras Laffan", "QAT"): "lng-export:ras-laffan-lng",
    ("Barrow Island", "AUS"): "lng-export:gorgon-lng",
    ("Karratha", "AUS"): "lng-export:nws-lng",
    ("Isle of Grain", "GBR"): "lng-import:isle-of-grain-lng",
    ("Zeebrugge", "BEL"): "lng-import:zeebrugge-lng",
    ("Montoir", "FRA"): "lng-import:montoir-lng",
    ("Barcelona", "ESP"): "lng-import:barcelona-lng",
    ("Dahej", "IND"): "lng-import:dahej-lng",
    ("Hazira", "IND"): "lng-import:hazira-lng",
    ("Incheon", "KOR"): "lng-import:incheon-lng",
    ("Tianjin", "CHN"): "lng-import:tianjin-sinopec-lng",
    # the spellings of the trade engine's port table, which the generated routes use
    ("Pusan", "KOR"): "port:busan",
    ("Port Kelang", "MYS"): "port:port-klang",
    ("Odessa", "UKR"): "port:odesa",
    ("Saint Petersburg", "RUS"): "port:st-petersburg",
    ("Dumai, Sumatra", "IDN"): "port:dumai",
    ("Up-River (Rosario hub)", "ARG"): "port:rosario-up-river",
    ("Dunkerque", "FRA"): "port:dunkirk",
    ("Surigao (nickel ore loading)", "PHL"): "port:surigao",
    ("Caofeidian Pt", "CHN"): "port:caofeidian",
    ("Dongjiakou (Qingdao LNG terminal)", "CHN"): "lng-import:qingdao-lng",
    ("Sabetta (Yamal LNG)", "RUS"): "lng-export:yamal-lng",
    ("Bintulu, Sarawak", "MYS"): "lng-export:bintulu-mlng",
    ("Prigorodnoye (Sakhalin-2 LNG)", "RUS"): "lng-export:sakhalin-2-lng",
}


def _norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _names(name):
    """The words a feature name answers to: the whole name, the part before " (", each side of " / ", the brackets."""
    out = {_norm(name)}
    base, _, rest = name.partition(" (")
    out.add(_norm(base))
    if rest:
        out.add(_norm(rest.rstrip(")")))
    for part in base.split(" / "):
        out.add(_norm(part))
    return {n for n in out if n}


def load_assets(infra_dir=INFRA):
    """{(type, id): feature properties} of every point asset that a route port can be."""
    feats = {}
    for f in sorted(glob.glob(os.path.join(infra_dir, "*.geojson"))):
        with open(f, encoding="utf-8") as fh:
            for ft in json.load(fh)["features"]:
                p = ft["properties"]
                if p.get("type") in PORT_TYPES:
                    feats.setdefault((p["type"], p["id"]), p)
    return feats


def asset_of(name, c, cargoes, feats):
    """"type:id" of the asset a route port is, or None."""
    key = ALIAS.get((name, c))
    if key:
        t, _, i = key.partition(":")
        return key if (t, i) in feats else None
    n = _norm(name)
    order = PORT_TYPES if "lng" not in (cargoes or []) else ("lng-export", "lng-import") + PORT_TYPES
    # the name itself, or the part before " (", wins over a word inside the brackets ("Novorossiysk" is the port of
    # Novorossiysk, not the "CPC terminal (Novorossiysk)")
    for strict in (True, False):
        for t in order:
            if t in ("field", "refinery"):
                continue  # a field or a refinery is a route port only through ALIAS
            for (ft, fid), p in sorted(feats.items()):
                if ft != t or p.get("c") != c:
                    continue
                words = {_norm(p["name"]), _norm(p["name"].partition(" (")[0])} if strict else _names(p["name"])
                if n in words:
                    return f"{ft}:{fid}"
    return None


_cache = {}


def route_port_assets(side, cargoes, infra_dir=INFRA):
    """The assets of the ports of one end of a route ({"ports": [{"name", "c"}]}), in the order of the ports."""
    if infra_dir not in _cache:
        _cache[infra_dir] = load_assets(infra_dir)
    feats = _cache[infra_dir]
    return [asset_of(p["name"], p["c"], cargoes, feats) for p in side.get("ports") or []]


def published_ports(routes_path=ROUTES_PUB, index_path=PORT_INDEX):
    """The ports of the published routes that routes_def.json does not hold (the generated routes): [(name, country,
    cargoes)]. A generated route names the ports of the lane port index, whose row gives the country (the route's own
    country at that end where two rows share the name)."""
    if not os.path.exists(routes_path):
        return []
    with open(routes_path, encoding="utf-8") as fh:
        routes = json.load(fh)
    routes = routes if isinstance(routes, list) else routes.get("routes", [])
    rows = []
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as fh:
            rows = json.load(fh).get("ports", [])
    out = []
    for r in routes:
        if not r.get("generated"):
            continue
        for i, side in enumerate(("from", "to")):
            end = (r.get("ends") or [None, None])[i]
            for name in r[side].get("ports") or []:
                same = [p for p in rows if p["name"] == name]
                row = next((p for p in same if p["c"] == end), same[0] if len(same) == 1 else None)
                out.append((name, row["c"] if row else end, r.get("cargoes")))
    return out


def report(defs_path=ROUTES_DEF, infra_dir=INFRA, routes_path=ROUTES_PUB):
    """Every distinct route port, of the hand-written routes and of the generated routes, and whether it is an asset."""
    with open(defs_path, encoding="utf-8") as fh:
        defs = json.load(fh)
    seen = {}
    for r in defs:
        for side in ("from", "to"):
            for p, a in zip(r[side].get("ports") or [], route_port_assets(r[side], r.get("cargoes"), infra_dir)):
                seen.setdefault((p["name"], p["c"]), a)
    feats = _cache.setdefault(infra_dir, load_assets(infra_dir))
    gen = {}
    for name, c, cargoes in published_ports(routes_path):
        gen.setdefault((name, c), asset_of(name, c, cargoes, feats))
    for key, a in gen.items():
        seen.setdefault(key, a)
    missing = sorted(k for k, a in seen.items() if not a)
    print(f"route ports: {len(seen)} distinct ({len(gen)} named by the generated routes), {len(seen) - len(missing)} are "
          f"assets, {len(missing)} are not")
    for name, c in missing:
        print(f"  not an asset: {name} ({c})")
    return seen


if __name__ == "__main__":
    report(*sys.argv[1:])
