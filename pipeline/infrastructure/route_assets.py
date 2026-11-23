"""
The infrastructure asset that each port of a freight route is, so that the route page links its ports to their pages.

    from route_assets import route_port_assets           # build_freight.py: out["from"]["assets"] = ...
    python pipeline/infrastructure/route_assets.py       # list the route ports that are not assets

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


def report(defs_path=ROUTES_DEF, infra_dir=INFRA):
    """Every distinct route port, and whether it is an asset."""
    with open(defs_path, encoding="utf-8") as fh:
        defs = json.load(fh)
    seen = {}
    for r in defs:
        for side in ("from", "to"):
            for p, a in zip(r[side].get("ports") or [], route_port_assets(r[side], r.get("cargoes"), infra_dir)):
                seen.setdefault((p["name"], p["c"]), a)
    missing = sorted(k for k, a in seen.items() if not a)
    print(f"route ports: {len(seen)} distinct, {len(seen) - len(missing)} are assets, {len(missing)} are not")
    for name, c in missing:
        print(f"  not an asset: {name} ({c})")
    return seen


if __name__ == "__main__":
    report(*sys.argv[1:])
