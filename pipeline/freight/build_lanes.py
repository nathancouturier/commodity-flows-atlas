"""
Build seaborne lanes (country-to-country commodity flows on real sea routes) from CEPII BACI.

    python pipeline/freight/build_lanes.py

Inputs
  pipeline/cache/baci_flows.csv.gz   (pipeline/trade/extract_baci.py)
  pipeline/cache/adjacency.json      (pipeline/geo/adjacency.py)
  data/countries/index.json
Outputs
  data/freight/lanes/<group>.json    one file per commodity group, lazy-loaded by the site
  pipeline/cache/seaborne_totals.json  seaborne tonnage per group and year (used by build_routes.py)
  pipeline/cache/geom_cache.json     sea-route geometry cache (port pair -> line)

Method (see METHODOLOGY.md):
  * A flow is "seaborne" when both countries have an ocean gateway and they do not share a land
    border (except listed sea-trading neighbours). Landlocked exporters with a known sea outlet
    (Kazakh crude via CPC, Zambian copper via Dar es Salaam...) use that outlet.
  * Missing tonnages are imputed from the median unit value of the commodity that year.
  * Each lane is routed between the exporter's and importer's main gateway port for that cargo
    with the searoute maritime network; chokepoints are detected geometrically.
"""
import json
import math
import os
import sys
from collections import defaultdict

import pandas as pd
import searoute as sr
from shapely.geometry import LineString

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ports as P  # noqa: E402
import vessel_rules as VR  # noqa: E402

sys.path.insert(0, os.path.join(HERE, "..", "trade"))
from clean import clean as clean_baci, despike  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CACHE = os.path.join(ROOT, "pipeline", "cache")
OUT = os.path.join(ROOT, "data", "freight", "lanes")
LATEST_MIN_YEAR = 2005

# commodity groups that move as seaborne cargo, with display unit
GROUPS = {
    "iron-ore": "Mt", "coal": "Mt", "bauxite": "Mt", "alumina": "Mt", "manganese": "Mt",
    "copper-ore": "Mt", "nickel-ore": "Mt", "zinc-ore": "Mt", "nickel-int": "Mt",
    "crude-oil": "Mt", "refined-products": "Mt", "lng": "Mt", "lpg": "Mt",
    "wheat": "Mt", "corn": "Mt", "soybeans": "Mt", "soymeal": "Mt", "soyoil": "Mt", "rice": "Mt",
    "sugar": "Mt", "palm-oil": "Mt", "rapeseed": "Mt", "potash": "Mt", "phosphate-rock": "Mt",
    "dap": "Mt", "urea": "Mt", "steel": "Mt", "copper-refined": "Mt", "aluminium": "Mt",
    "coffee": "Mt", "cocoa": "Mt", "cotton": "Mt",
}
# atlas commodity id for each group (the site loads lanes by commodity)
COMMODITY = {
    "coal": "thermal-coal", "alumina": "bauxite", "copper-ore": "copper", "copper-refined": "copper",
    "nickel-ore": "nickel", "nickel-int": "nickel", "zinc-ore": "zinc", "phosphate-rock": "phosphate",
    "dap": "phosphate",
}
LABEL = {
    "coal": "Coal (thermal and metallurgical)", "copper-ore": "Copper concentrate", "copper-refined": "Refined & blister copper",
    "nickel-ore": "Nickel ore", "nickel-int": "Nickel matte, intermediates & metal", "zinc-ore": "Zinc concentrate",
    "phosphate-rock": "Phosphate rock", "dap": "DAP", "alumina": "Alumina", "bauxite": "Bauxite",
}

# neighbours whose trade in these goods is largely seaborne
SEA_NEIGHBOURS = {
    frozenset(("IDN", "MYS")), frozenset(("MYS", "SGP")), frozenset(("ARG", "BRA")), frozenset(("ARG", "URY")),
    frozenset(("BRA", "URY")), frozenset(("CHN", "VNM")), frozenset(("IND", "BGD")), frozenset(("SAU", "ARE")),
    frozenset(("SAU", "KWT")), frozenset(("ESP", "FRA")), frozenset(("ESP", "PRT")), frozenset(("NOR", "SWE")),
    frozenset(("CHL", "PER")), frozenset(("COL", "VEN")), frozenset(("EGY", "LBY")), frozenset(("TUR", "GRC")),
    frozenset(("THA", "MYS")), frozenset(("PNG", "IDN")), frozenset(("FRA", "BEL")), frozenset(("NLD", "BEL")),
    frozenset(("NLD", "DEU")), frozenset(("DEU", "POL")), frozenset(("RUS", "FIN")), frozenset(("USA", "MEX")),
}
# landlocked exporters/importers with a recognised sea outlet (country -> gateway port via ports.P)
SEA_OUTLET = {"KAZ": {"crude-oil"}, "AZE": {"crude-oil"}, "ZMB": {"copper-ore", "copper-refined"}, "BLR": {"potash"}, "PRY": {"soybeans", "soymeal", "soyoil", "corn"}}

# geometric chokepoint detection: id -> (lon, lat, radius_km)
CHOKE = {
    "hormuz": (56.4, 26.5, 90), "bab-el-mandeb": (43.35, 12.6, 80), "suez": (32.4, 30.3, 120),
    "malacca": (100.9, 2.5, 160), "singapore": (103.85, 1.2, 50), "sunda": (105.8, -6.0, 60),
    "lombok": (115.75, -8.6, 60), "panama": (-79.7, 9.1, 70), "gibraltar": (-5.6, 35.95, 60),
    "bosphorus": (29.05, 41.1, 40), "danish-straits": (11.5, 55.7, 120), "dover": (1.45, 51.0, 60),
    "cape-good-hope": (19.0, -35.5, 500), "cape-horn": (-67.5, -56.2, 300), "taiwan-strait": (119.6, 24.4, 130),
    "korea-strait": (129.2, 34.6, 90),
}


def km(lon1, lat1, lon2, lat2):
    p = math.pi / 180
    x = (lon2 - lon1) * p * math.cos((lat1 + lat2) * p / 2)
    y = (lat2 - lat1) * p
    return 6371 * math.hypot(x, y)


def seg_dist_km(px, py, ax, ay, bx, by):
    """Distance from point to segment, local equirectangular projection (km)."""
    k = math.cos(py * math.pi / 180)
    ax, bx, qx = (ax - px) * k, (bx - px) * k, 0.0
    ay, by, qy = ay - py, by - py, 0.0
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((qx - ax) * dx + (qy - ay) * dy) / L))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(cx, cy) * 111.2


def detect_via(coords):
    via = []
    for cid, (x, y, r) in CHOKE.items():
        for i in range(len(coords) - 1):
            a, b = coords[i], coords[i + 1]
            if abs(a[0] - b[0]) > 180:
                continue
            if seg_dist_km(x, y, a[0], a[1], b[0], b[1]) <= r:
                via.append((i, cid))
                break
    have = {c for _, c in via}
    for i in range(len(coords) - 1):
        (x1, y1), (x2, y2) = coords[i], coords[i + 1]
        if abs(x1 - x2) > 180:
            continue
        if "cape-good-hope" not in have and (x1 - 20) * (x2 - 20) <= 0 and min(y1, y2) < -30:
            via.append((i, "cape-good-hope"))
            have.add("cape-good-hope")
        if "cape-horn" not in have and (x1 + 67) * (x2 + 67) <= 0 and min(y1, y2) < -50:
            via.append((i, "cape-horn"))
            have.add("cape-horn")
    return [c for _, c in sorted(via)]


def unwrap(coords):
    out = [list(coords[0])]
    shift = 0.0
    for i in range(1, len(coords)):
        dx = coords[i][0] - coords[i - 1][0]
        if dx > 180:
            shift -= 360
        elif dx < -180:
            shift += 360
        out.append([coords[i][0] + shift, coords[i][1]])
    return out


_geom = {}
_geom_path = os.path.join(CACHE, "geom_cache.json")
if os.path.exists(_geom_path):
    _geom = json.load(open(_geom_path))


def route_geom(a, b, avoid=()):
    """Sea route between two [lon, lat] points. Returns (coords, nm, via)."""
    key = f"{a[0]:.2f},{a[1]:.2f}|{b[0]:.2f},{b[1]:.2f}|{','.join(sorted(avoid))}"
    if key in _geom:
        g = _geom[key]
        return g["c"], g["nm"], g["via"]
    restr = ["northwest"] + list(avoid)
    r = sr.searoute(a, b, units="naut", restrictions=restr)
    raw = r["geometry"]["coordinates"]
    if len(raw) < 2:
        return None, 0, []
    nm = round(r["properties"]["length"])
    line = LineString(raw).simplify(0.05, preserve_topology=False)
    coords = [[round(x, 2), round(y, 2)] for x, y in line.coords]
    via = detect_via(raw)
    coords = unwrap(coords)
    _geom[key] = {"c": coords, "nm": nm, "via": via}
    return coords, nm, via


CAPE_PREFERRED = {"vloc", "capesize", "newcastlemax", "vlcc"}
# Laden transit limits (Panama Canal Authority: Neopanamax 51.25 m beam / 15.24 m draft;
# Suez Canal Authority: 20.1 m draft). These classes are routed around the canal.
NO_PANAMA = {"vloc", "capesize", "newcastlemax", "vlcc", "suezmax"}
NO_SUEZ = {"vloc", "vlcc"}


def routing(a, b, primary_class, speed_kn):
    """Main routing plus an alternative, following carrier practice.

    Capesize/VLOC/VLCC voyages take the Cape of Good Hope instead of Suez when it costs <= 4 extra
    days (canal tolls and draft make Suez uneconomic for them). Otherwise the shortest route is the
    main one, and the alternative avoids Suez/Bab el-Mandeb or Panama when the main route uses them.
    Returns (coords, nm, via, alt|None).
    """
    base = []
    if primary_class in NO_PANAMA:
        base.append("panama")
    if primary_class in NO_SUEZ:
        base.append("suez")
    coords, nm, via = route_geom(a, b, base)
    if not coords:
        return None, 0, [], None
    avoid = ["suez", "babalmandab"] if ("suez" in via or "bab-el-mandeb" in via) else (["panama"] if "panama" in via else [])
    if not avoid:
        return coords, nm, via, None
    ac, anm, avia = route_geom(a, b, sorted(set(avoid + base)))
    if not ac:
        return coords, nm, via, None
    extra = round((anm - nm) / (speed_kn * 24), 1)
    if primary_class in CAPE_PREFERRED and "suez" in via and extra <= 4:
        alt = {"label": "Via Suez Canal (shorter, subject to tolls and Red Sea security)", "via": via, "distanceNm": nm, "extraDays": -extra, "g": coords}
        return ac, anm, avia, alt
    names = {"suez": "Suez Canal", "bab-el-mandeb": "Bab el-Mandeb", "panama": "Panama Canal"}
    avoided = [names[v] for v in via if v in names]
    label = "Avoiding " + " and ".join(avoided) + (" (via Cape of Good Hope)" if "cape-good-hope" in avia else "")
    return coords, nm, via, {"label": label, "avoids": [v for v in via if v in names], "via": avia, "distanceNm": anm, "extraDays": extra, "g": ac}


def save_geom_cache():
    json.dump(_geom, open(_geom_path, "w"), separators=(",", ":"))


# ------------------------------------------------------------------ helpers for countries/ports
COUNTRIES = {c["c"]: c for c in json.load(open(os.path.join(ROOT, "data", "countries", "index.json")))}
ADJ = json.load(open(os.path.join(CACHE, "adjacency.json")))
COASTAL = set(ADJ["coastal"])
NEIGH = {k: set(v) for k, v in ADJ["neighbours"].items()}
A2 = {c: v.get("a2") for c, v in COUNTRIES.items()}


def nearest_port(iso3):
    """Fallback gateway: the searoute port of that country closest to the country label point."""
    a2 = A2.get(iso3)
    meta = COUNTRIES.get(iso3)
    if not a2 or not meta:
        return None
    best, bd = None, 1e9
    for code, (_, (x, y)) in P._sr.items():
        if code[:2] != a2:
            continue
        d = km(meta["at"][0], meta["at"][1], x, y)
        if d < bd:
            best, bd = code, d
    return best


def gateway(iso3, group):
    g = P.gateway(iso3, group)
    if g:
        return g
    if iso3 in COASTAL:
        return nearest_port(iso3)
    return None


EAST_ASIA = {"CHN", "JPN", "KOR", "TWN", "PRK", "VNM", "PHL", "THA", "MYS", "IDN", "SGP", "HKG"}
MED_BLACK = {"TUR", "EGY", "ISR", "MAR", "GRC", "ITA", "ESP", "CYP", "LBN", "TUN", "DZA", "LBY", "BGR", "ROU", "HRV", "SVN", "SYR", "MLT", "GEO"}
# Russia exports from three coasts; the load port depends on where the cargo goes
RUS_PORTS = {
    "coal": {"east": "RUVYP", "south": "RUTAM", "west": "RUULU"},
    "crude-oil": {"east": "RUKOZ", "south": "RUNVS", "west": "RUPRI"},
    "refined-products": {"east": "RUNJK", "south": "RUTUA", "west": "RUPRI"},
    "lng": {"east": "RUPRG", "south": "RUSAB", "west": "RUSAB"},
    "wheat": {"east": "RUVYP", "south": "RUNVS", "west": "RUNVS"},
}


def gateway_pair(o, d, group):
    """Load and discharge gateways for a lane (origin-dependent rules for multi-coast exporters)."""
    go = gateway(o, group)
    if o == "RUS" and group in RUS_PORTS:
        side = "east" if d in EAST_ASIA or (group == "coal" and d == "IND") else ("south" if d in MED_BLACK else "west")
        go = RUS_PORTS[group][side]
    gd = gateway(d, group)
    # South-east Asian coal discharges in South China (Guangdong/Guangxi), not in the north
    if d == "CHN" and group == "coal" and o in ("IDN", "PHL", "VNM", "MYS"):
        gd = "CNZHA"
    return go, gd


# lanes crossing a currently disrupted chokepoint carry a status note (event ids in events.json)
DISRUPTIONS = [
    ({"bab-el-mandeb", "suez"}, "red-sea-houthi-2023",
     "Drawn on the normal routing. Since December 2023 most of this traffic has diverted around the Cape of Good Hope because of attacks in the Red Sea; Suez transits were recovering in late 2026."),
    ({"hormuz"}, "iran-war-hormuz-2026",
     "The Strait of Hormuz has been largely closed to commercial traffic since March 2026: volumes shown are the 2024 baseline."),
]


# customs reporting gaps worth flagging on the affected lanes
KNOWN_GAPS = {
    ("crude-oil", "IRN"): "Customs data gap: since 2019 most Iranian crude is declared under other origins (e.g. Malaysia) or not recorded, so this lane understates real flows.",
    ("crude-oil", "VEN"): "Customs data gap: sanctioned Venezuelan crude is often declared under other origins.",
}


def mode_of(o, d, group):
    o_ok = o in COASTAL or group in SEA_OUTLET.get(o, ())
    d_ok = d in COASTAL or group in SEA_OUTLET.get(d, ())
    if not (o_ok and d_ok):
        return "land"
    if d in NEIGH.get(o, ()) and frozenset((o, d)) not in SEA_NEIGHBOURS:
        return "land"
    return "sea"


# ------------------------------------------------------------------ main
def main():
    df = pd.read_csv(os.path.join(CACHE, "baci_flows.csv.gz"))
    df = df[df["group"].isin(GROUPS)]
    df = clean_baci(df)  # shared rules: Taiwan code, tonnage repair, misclassifications (pipeline/trade/clean.py)
    print("tonnage imputed from value:", int(df["imputed"].sum()), "flows")

    df["mode"] = [mode_of(o, d, g) for o, d, g in zip(df["o"], df["d"], df["group"])]
    sea = df[df["mode"] == "sea"]
    sea[["year", "group", "o", "d", "t", "imputed"]].round({"t": 0}).to_csv(os.path.join(CACHE, "sea_flows.csv.gz"), index=False, compression="gzip")
    totals = sea.groupby(["group", "year"])["t"].sum()
    world = df.groupby(["group", "year"])["t"].sum()
    latest = int(df["year"].max())
    json.dump(
        {g: {str(y): {"sea": round(totals.get((g, y), 0)), "all": round(world.get((g, y), 0))} for y in range(LATEST_MIN_YEAR, latest + 1)} for g in GROUPS},
        open(os.path.join(CACHE, "seaborne_totals.json"), "w"),
    )

    os.makedirs(OUT, exist_ok=True)
    years = list(range(LATEST_MIN_YEAR, latest + 1))
    for group, unit in GROUPS.items():
        g = sea[sea["group"] == group]
        if g.empty:
            continue
        # union of the top pairs (covering 80% of seaborne volume, max 22) across sample years
        chosen = set()
        for y in sorted(set([2005, 2010, 2015, 2019, 2021, 2022, 2023, latest])):
            gy = g[g["year"] == y].sort_values("t", ascending=False)
            tot = gy["t"].sum()
            if tot <= 0:
                continue
            cum, added = 0.0, 0
            for o, d, t in zip(gy["o"], gy["d"], gy["t"]):
                share = t / tot
                if share < 0.006 or cum > 0.8 or added >= 22 or len(chosen) >= 45:
                    break
                chosen.add((o, d))
                cum += share
                added += 1
        piv = g[g["o"].isin({o for o, _ in chosen})].pivot_table(index=["o", "d"], columns="year", values="t", aggfunc="sum").fillna(0)
        imp = g[g["year"] == latest].set_index(["o", "d"])["imputed"].to_dict()
        tot_latest = totals.get((group, latest), 0) or 1
        dest_tot = df[(df["group"] == group) & (df["year"] == latest)].groupby("d")["t"].sum()
        lanes = []
        for (o, d) in sorted(chosen):
            go, gd = gateway_pair(o, d, group)
            if not go or not gd or go == gd:
                continue
            po, pd_ = P.port(go), P.port(gd)
            row = piv.loc[(o, d)] if (o, d) in piv.index else None
            vlat = float(row.get(latest, 0)) if row is not None else 0.0
            _, nm0, _ = route_geom(po["at"], pd_["at"])
            classes = VR.classes(group, o, d, vlat, nm0)
            speed = VR.speed(classes[0])
            coords, nm, via, alt = routing(po["at"], pd_["at"], classes[0], speed)
            if not coords or nm < 50:
                continue
            hist = [round(float(row.get(y, 0)) / 1e6, 3) if row is not None else 0 for y in years]
            hist, spikes = despike(hist)
            lane = {
                "id": f"{group}:{o}-{d}",
                "k": COMMODITY.get(group, group),
                "p": group,
                "o": o,
                "d": d,
                "load": [po["id"]],
                "discharge": [pd_["id"]],
                "vclass": classes,
                "distanceNm": nm,
                "days": round(nm / (speed * 24), 1),
                "via": via,
                "flow": {"v": round(vlat / 1e6, 3), "u": "Mt", "y": latest, "s": "baci",
                         **({"n": KNOWN_GAPS[(group, o)]} if (group, o) in KNOWN_GAPS else ({"n": "tonnage estimated from value"} if imp.get((o, d)) else {}))},
                "share": round(vlat / tot_latest, 4),
                "shareDest": round(vlat / float(dest_tot.get(d, 0) or 1), 4) if d in dest_tot else None,
                "hist": hist,
                "g": coords,
            }
            if alt:
                lane["alt"] = alt
            for cps, ev, text in DISRUPTIONS:
                if cps & set(via):
                    lane.setdefault("status", []).append({"text": text, "event": ev})
            if spikes:
                lane["histNote"] = "Isolated customs outlier removed for " + ", ".join(str(years[i]) for i in spikes)
            lanes.append(lane)
        lanes.sort(key=lambda x: -x["flow"]["v"])
        ports_used = {}
        for ln in lanes:
            for code in ln["load"] + ln["discharge"]:
                ports_used[code] = P.port(code)
        doc = {
            "group": group,
            "k": COMMODITY.get(group, group),
            "label": LABEL.get(group),
            "unit": unit,
            "y": latest,
            "s": "baci",
            "years": years,
            "seaborne": [round(totals.get((group, y), 0) / 1e6, 2) for y in years],
            "world": [round(world.get((group, y), 0) / 1e6, 2) for y in years],
            "ports": ports_used,
            "lanes": lanes,
        }
        json.dump(doc, open(os.path.join(OUT, f"{group}.json"), "w"), separators=(",", ":"))
        print(f"{group:18s} lanes={len(lanes):3d} seaborne {latest}={doc['seaborne'][-1]:8.1f} Mt  covered={sum(l['share'] for l in lanes):.0%}")
        save_geom_cache()
    save_geom_cache()


if __name__ == "__main__":
    main()
