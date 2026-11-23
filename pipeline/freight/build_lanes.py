"""
Build the seaborne lanes and the pairs table (country-to-country commodity flows on sea routes) from CEPII BACI.

    python pipeline/freight/build_lanes.py

Inputs
  pipeline/cache/baci_flows.csv.gz   (pipeline/trade/extract_baci.py)
  pipeline/cache/adjacency.json      (pipeline/geo/adjacency.py, read by modes.py)
  data/countries/index.json
  raw/usda, raw/eia, raw/usgs        (checks only; skipped quietly when absent)
Outputs
  data/freight/lanes/<group>.json    lanes of each commodity group, lazy-loaded by the site
  data/freight/pairs/<group>.json    every recorded pair of the latest year, with mode, ports, route and passages
  data/freight/caveats.json          caveat texts of the active entries of pipeline/trade/caveats.py
  data/freight/zones.json            freight zones and their gateways (pipeline/freight/gateways/)
  pipeline/cache/sea_flows.csv.gz    seaborne pairs of every year (mode sea or transit)
  pipeline/cache/mixed_flows.csv.gz  pairs that move both by sea and overland (split not known)
  pipeline/cache/seaborne_totals.json  seaborne, mixed and all-modes tonnage per group and year
  pipeline/cache/trade_checks.json   findings of the checks (single writer; build_freight.py adds K9)
  pipeline/cache/route_cache.json    plans of every routed pair (no geometry), versioned (routing.VERSION)
  pipeline/cache/geom_cache.json     plans with geometry of the lanes and routes, versioned

Method (METHODOLOGY.md, sections 1 to 3; trade-engine plan, sections 2.1 to 2.8):
  * clean() repairs the customs table (pipeline/trade/clean.py); a tonnage estimated from value is an
    Atlas estimate (source id "atlas") wherever it is shown on its own.
  * modes.mode_of() classes every pair: sea, transit (sea through a foreign port), mixed or land.
  * ports.assign() gives the gateways of a pair per cargo family and coast; a landlocked end (or a coast with no
    port of its own) uses its sourced transit port (gateways/energy.py TRANSIT), at either end or both, or the pair
    is "sea, not routed". Each port is published with its basis (ports.basis_of) and the source of that cargo's row.
  * routing.plan() routes every option: passages certain for every option and parallel passage go to
    `via`, the others to `viaAlt`; alternatives avoid Suez, Bab el-Mandeb or Panama.
  * Lanes of the latest year first: every seaborne pair at or above the group's floor, up to its cap
    ("main" set), the mixed pairs above the floor, and the largest pairs of sample past years ("history"
    set). The rest of each exporter's seaborne tonnage is published per exporter (`rest`).
"""
import json
import math
import os
import sys
import time
from collections import defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import modes as MD  # noqa: E402
import ports as P  # noqa: E402
import routing as RT  # noqa: E402
import vessel_rules as VR  # noqa: E402

sys.path.insert(0, os.path.join(HERE, "..", "trade"))
import caveats as CV  # noqa: E402
import checks as K  # noqa: E402
from clean import LAST_DROPPED, clean as clean_baci, despike, history_flags  # noqa: E402,F401  (despike: used by build_freight.py)

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CACHE = os.path.join(ROOT, "pipeline", "cache")
OUT = os.path.join(ROOT, "data", "freight", "lanes")
PAIRS_OUT = os.path.join(ROOT, "data", "freight", "pairs")
CAVEATS_OUT = os.path.join(ROOT, "data", "freight", "caveats.json")
ZONES_OUT = os.path.join(ROOT, "data", "freight", "zones.json")
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
    "coal": "Coal (all types)", "copper-ore": "Copper concentrate", "copper-refined": "Refined & blister copper",
    "nickel-ore": "Nickel ore", "nickel-int": "Nickel matte, intermediates & metal", "zinc-ore": "Zinc concentrate",
    "phosphate-rock": "Phosphate rock", "dap": "DAP", "alumina": "Alumina", "bauxite": "Bauxite",
}

# Selection of the lanes (trade-engine plan 2.2). Caps bound the main set of each group; the floor is the smallest
# latest-year tonnage of a main lane (Mt).
CAP = {
    "crude-oil": 120, "refined-products": 150, "lng": 100, "lpg": 80, "coal": 100, "iron-ore": 60, "steel": 150,
    "wheat": 120, "corn": 100, "soybeans": 60, "soymeal": 80, "rice": 100, "sugar": 100, "urea": 100, "dap": 60,
    "potash": 60, "phosphate-rock": 60, "palm-oil": 80, "soyoil": 60, "rapeseed": 50, "bauxite": 40, "alumina": 60,
    "manganese": 40, "copper-ore": 60, "copper-refined": 80, "aluminium": 100, "nickel-ore": 20, "nickel-int": 40,
    "zinc-ore": 60, "coffee": 100, "cocoa": 60, "cotton": 60,
}
FLOOR = {"coffee": 0.02, "cocoa": 0.02, "cotton": 0.02, "nickel-int": 0.02, "copper-refined": 0.02, "zinc-ore": 0.02,
         "aluminium": 0.03, "soyoil": 0.03}
FLOOR_DEFAULT = 0.05
# history set: the largest seaborne pairs of these years that are not in the main set (fixed early years, then the
# three years before the latest, so that a new BACI year moves the window)
HIST_EARLY = (2005, 2010, 2015, 2019)
HIST_TOP, HIST_MIN_SHARE = 10, 0.01


def hist_years(latest):
    return tuple(sorted(set(HIST_EARLY) | {latest - 3, latest - 2, latest - 1}))


HIST_YEARS = hist_years(2024)  # the years of the 2024 build; main() uses hist_years(latest)
EST_NOTE_MIN = 0.005  # a year whose seaborne total is at least this share Atlas estimates gets a yearNotes line
MIN_NM = 50  # a route shorter than this is not drawn (same port area)

# pairs table: m codes and f bits (plan 2.3)
M_CODE = {"sea": 0, "transit": 1, "mixed": 2, "land": 3}
F_EST, F_CAVEAT, F_LANE, F_CHECK = 1, 2, 4, 8
PAIR_CHECKS = ("K2", "K8")  # checks whose finding on a pair of the latest year sets bit 3


def kt(t):
    """Tonnage of a pairs row in kt: whole kt from 1 Mt, one decimal below (small parcels must not round to zero)."""
    return round(t / 1e3) if t >= 1e6 else round(t / 1e3, 1)


def km(lon1, lat1, lon2, lat2):
    p = math.pi / 180
    x = (lon2 - lon1) * p * math.cos((lat1 + lat2) * p / 2)
    y = (lat2 - lat1) * p
    return 6371 * math.hypot(x, y)


def gc_nm(a, b):
    """Great-circle distance between two [lon, lat] points, nautical miles (check K12)."""
    p = math.pi / 180
    h = math.sin((b[1] - a[1]) * p / 2) ** 2 + math.cos(a[1] * p) * math.cos(b[1] * p) * math.sin((b[0] - a[0]) * p / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h)) / 1.852


# ------------------------------------------------------------------ routing caches
_GEOM_PATH = os.path.join(CACHE, "geom_cache.json")
_ROUTE_PATH = os.path.join(CACHE, "route_cache.json")
_geom = RT.load_cache(_GEOM_PATH)      # plans with geometry (lanes, routes of build_freight.py)
_plans = RT.load_cache(_ROUTE_PATH)    # plans without geometry (every routed pair); None = no route


def _strip(summary):
    s = {k: v for k, v in summary.items() if k != "g"}
    s["alts"] = [{k: v for k, v in a.items() if k != "g"} for a in summary["alts"]]
    return s


def plan_summary(a, b, classes, geometry=False):
    """routing.summary() of the plan between two [lon, lat] points for the classes, from the caches when they hold it.
    None when there is no route."""
    key = RT.cache_key(a, b, ",".join(classes))
    if geometry and key in _geom:
        return _geom[key]
    if not geometry:
        if key in _plans:
            return _plans[key]
        if key in _geom:
            return _strip(_geom[key])
    p = RT.plan(a, b, classes)
    s = RT.summary(p, geometry=geometry) if p else None
    _plans[key] = _strip(s) if s else None
    if s and geometry:
        _geom[key] = s
    return s


def routing(a, b, primary_class, speed_kn):
    """Wrapper of routing.plan() for build_freight.py (routes): (coords, nm, via, alt|None). `via` holds the certain
    passages plus the first member of each "one of" list, until build_freight.py uses plan() itself."""
    s = plan_summary(a, b, [primary_class], geometry=True)
    if not s:
        return None, 0, [], None
    via = list(s["via"]) + [lst[0] for lst in s["viaAlt"] if lst and lst[0] not in s["via"]]
    alt = None
    if s["alts"]:
        alt = {k: v for k, v in s["alts"][0].items() if k != "redSea"}
    return s["g"], s["nm"], via, alt


def save_geom_cache():
    RT.save_cache(_GEOM_PATH, _geom)
    RT.save_cache(_ROUTE_PATH, _plans)


# ------------------------------------------------------------------ helpers for countries/ports
with open(os.path.join(ROOT, "data", "countries", "index.json"), encoding="utf-8") as _f:
    COUNTRIES = {c["c"]: c for c in json.load(_f)}
A2 = {c: v.get("a2") for c, v in COUNTRIES.items()}
ISO3_OF_A2 = {a2: c for c, a2 in A2.items() if a2}
with open(os.path.join(ROOT, "pipeline", "geo", "places_extra.json"), encoding="utf-8") as _f:
    for _p in json.load(_f):
        if _p.get("a2"):
            ISO3_OF_A2.setdefault(_p["a2"], _p["c"])


def nearest_port(iso3):
    """Fallback gateway: the searoute port of that country closest to the country label point."""
    return P.nearest_port(iso3)


def gateway(iso3, group):
    g = P.gateway(iso3, group)
    if g:
        return g
    if MD.coastal(iso3):
        return nearest_port(iso3)
    return None


def port_iso3(code):
    if code in P.MANUAL:
        return P.MANUAL[code][1]
    return ISO3_OF_A2.get(code[:2], code[:2])


_meta = {}


def port_entry(code, use):
    """A port of the lane file's `ports` table: id, name, country, coordinates, freight zone, and the basis and source
    for that file's cargo. use: (basis, source id, url) of the roles that use the port in the file, from port_use(); the
    weakest basis wins, with its source (null when no page was read for the cargo)."""
    if code not in _meta:
        _meta[code] = P.port_meta(code)
    m = _meta[code]
    p = P.port(code)
    basis, src, url = max(use, key=lambda u: BASIS_RANK[u[0]])
    out = {"id": code, "name": p["name"], "c": port_iso3(code), "at": p["at"], "zone": m.get("zone"), "basis": basis, "s": src}
    if url:
        out["url"] = url
    return out


BASIS_RANK = {b: i for i, b in enumerate(P.BASES)}  # strongest first


def port_use(iso3, group, role, code, transit_rows=()):
    """(basis, source id, url) of a port at one end of a pair: its TRANSIT row when it is the end's transit port (a
    family row is a page that names the cargo, a "default" row a general port of that country's trade), else the
    gateway row behind ports.basis_of()."""
    for t in transit_rows:
        if t and t["port"] == code and t["end"] == iso3:
            return (P.BASIS_PAGE if t["family"] else P.BASIS_GENERAL), t["s"], t["url"]
    basis = P.basis_of(iso3, group, role, code)
    s, url = P.source_of(iso3, group, role, code)
    return basis, s, url


def mode_of(o, d, group):
    """Compatibility wrapper: "sea" for a seaborne pair (sea or transit), "land" otherwise (mixed, land, no mode)."""
    m = MD.mode_of(o, d, group)
    return "sea" if m and m.kind in ("sea", "transit") else "land"


# lanes crossing a currently disrupted chokepoint carry a status note (event ids in events.json)
DISRUPTIONS = [
    ({"bab-el-mandeb", "suez"}, "red-sea-houthi-2023",
     "Drawn on the normal routing. Since December 2023 most of this traffic has diverted around the Cape of Good Hope because of attacks in the Red Sea; Suez transits were recovering in late 2026."),
    ({"hormuz"}, "iran-war-hormuz-2026",
     "The Strait of Hormuz has been largely closed to commercial traffic since the strikes of 28 February 2026: volumes shown are the 2024 pre-disruption baseline."),
]
# added to a status note when the passage is only one of the options of the lane (viaAlt)
PARTIAL = {
    "red-sea-houthi-2023": "It applies only to the part of this trade that would go through the Red Sea.",
    "iran-war-hormuz-2026": "It applies only to the part of this trade loaded or discharged inside the Gulf.",
}


def status_of(via, alt_gates):
    out = []
    for cps, ev, text in DISRUPTIONS:
        if cps & set(via):
            out.append({"text": text, "event": ev})
        elif cps & alt_gates:
            out.append({"text": f"{text} {PARTIAL[ev]}", "event": ev})
    return out


# ------------------------------------------------------------------ routing of a pair
def _merge_lists(lists):
    """"One of" lists of several options as one set of lists: identical lists once, overlapping lists merged."""
    out = []
    for lst in lists:
        lst = list(dict.fromkeys(lst))
        hit = next((x for x in out if set(x) & set(lst)), None)
        if hit is None:
            out.append(lst)
        else:
            hit.extend(g for g in lst if g not in hit)
    return out


def combine(summaries):
    """`via` and `viaAlt` of a pair from the plans of its port options, main option first (plan 2.4): a passage is
    certain only when every option crosses it whatever the parallel choice; a passage crossed by some options only
    is one more "one of" list."""
    sets = [set(s["via"]) for s in summaries]
    via = [g for g in summaries[0]["via"] if all(g in x for x in sets)]
    lists = _merge_lists([lst for s in summaries for lst in s["viaAlt"]])
    listed = {g for lst in lists for g in lst}
    some = [g for s in summaries for g in s["via"] if g not in via and g not in listed]
    # each such passage is its own list ("on some options"): passages that one option crosses together are no
    # alternatives to each other
    lists.extend([g] for g in dict.fromkeys(some))
    return via, lists


def _classes_and_plan(group, o, d, t, a, b, geometry=False):
    c0 = VR.classes(group, o, d, t, 5000)
    s = plan_summary(a, b, c0, geometry)
    if not s:
        return c0, None
    c1 = VR.classes(group, o, d, t, s["nm"])
    if c1 != c0:
        s = plan_summary(a, b, c1, geometry) or s
        return (c1 if s else c0), s
    return c0, s


def transit_row(iso3, group):
    """TRANSIT row of a country for the group's cargo family: {port, c, s, url} plus `end` and `family` (whether the
    row is the family's own, not the "default" one), or None when no page was read."""
    rows = P.TRANSIT.get(iso3) or {}
    fam = MD.FAMILY.get(group)
    row = rows.get(fam) or rows.get("default")
    if not row:
        return None
    code, src, url = row[0], row[1], row[2]
    return {"port": code, "c": port_iso3(code), "s": src, "url": url, "end": iso3, "family": fam in rows}


def public_transit(t):
    return {k: t[k] for k in ("port", "c", "s", "url")} if t else None


def transit_of(o, d, group):
    """Transit row of the landlocked end of a pair: (end, {port, c, s, url}) or (end, None) when no page was read."""
    end = o if not MD.coastal(o) else d
    return end, public_transit(transit_row(end, group))


def transit_ends(o, d, kind):
    """Ends of a pair that reach the sea through a foreign port: the landlocked ends of a transit pair, and a coast
    with no port of its own that has a TRANSIT row (Bosnia and Herzegovina, through Ploce)."""
    out = [e for e in (o, d) if kind == "transit" and not MD.coastal(e)]
    return out + [e for e in (o, d) if e not in out and MD.coastal(e) and e in P.TRANSIT]


def route_pair(o, d, group, t, kind):
    """Ports and route of a seaborne or mixed pair. Returns a record, or (None, reason) when the pair is not routed.
    A landlocked end uses its TRANSIT port whatever the gateway rows hold; a pair of two landlocked countries is
    routed between their two transit ports (`transit` for the loading end, `transit2` for the discharging end)."""
    a = P.assign(o, d, group)
    opts = [(x.load, x.discharge) for x in a.options]
    basis, transit, transit2, trows = a.basis, None, None, {}
    for end in transit_ends(o, d, kind):
        row = transit_row(end, group)
        if row:
            trows[end] = row
        elif not MD.coastal(end):
            return None, "no sourced transit port"
    if trows:
        opts = [(trows[o]["port"] if o in trows else oo, trows[d]["port"] if d in trows else dd) for oo, dd in opts]
        opts = list(dict.fromkeys(opts))
        basis = "single" if len(opts) == 1 else "open"
        transit = public_transit(trows.get(o) or trows.get(d))
        if o in trows and d in trows:
            transit2 = public_transit(trows[d])
    if basis == "unrouted" or not all(c and P._known(c) for c in opts[0]):
        return None, "no gateway"
    if opts[0][0] == opts[0][1]:
        return None, "same port at both ends"
    opts = [x for x in opts if all(c and P._known(c) for c in x) and x[0] != x[1]]
    at = {c: P.port(c)["at"] for x in opts for c in x}
    classes, main = _classes_and_plan(group, o, d, t, at[opts[0][0]], at[opts[0][1]])
    if not main:
        return None, "no sea route"
    if main["nm"] < MIN_NM:
        return None, "route under 50 nm"
    summaries, kept = [main], [opts[0]]
    for x in opts[1:]:
        s = plan_summary(at[x[0]], at[x[1]], classes)
        if s and s["nm"] >= MIN_NM:
            summaries.append(s)
            kept.append(x)
    if len(kept) == 1 and basis == "open":
        basis = "single"
    via, via_alt = combine(summaries)
    return {"opts": kept, "plans": summaries, "classes": classes, "nm": main["nm"], "via": via, "viaAlt": via_alt,
            "basis": basis, "transit": transit, "transit2": transit2, "trows": list(trows.values()), "at": at}, None


# ------------------------------------------------------------------ notes
def _mt(v):
    return K._mt(v)


def hist_note(flags, years):
    """Compatibility text of the chart note (the site shows `histNote` until it reads `histFlags`)."""
    by = defaultdict(list)
    for y, f in sorted(flags.items()):
        by[f].append(y)
    parts = []
    if by.get("est"):
        parts.append("Atlas estimate (tonnage estimated from declared value) for " + ", ".join(by["est"]))
    if by.get("nodata"):
        parts.append("no customs record for " + ", ".join(by["nodata"]))
    if by.get("suspect"):
        parts.append("not shown for " + ", ".join(by["suspect"]) + " (unit value at odds with the neighbouring years)")
    if by.get("check"):
        parts.append("checked against USDA PSD for " + ", ".join(by["check"]) + " (see the notes)")
    if not parts:
        return None
    s = "; ".join(parts)
    return s[0].upper() + s[1:]


def pipelines_on(o, d, group):
    """Pipelines of the atlas's layer between the two countries for this cargo, quoted on a mixed lane (nothing is
    subtracted from the customs tonnage)."""
    out = []
    for f in _PIPELINES:
        p = f["properties"]
        if group in (p.get("k") or []) and {o, d} <= set(p.get("cs") or [p.get("c")]):
            cap = p.get("capacity")
            out.append(p["name"] + (f", {cap['v']:g} {cap['u']}" if cap else "") + f" ({p.get('s')}, {p.get('y')})")
    return out


with open(os.path.join(ROOT, "data", "infrastructure", "pipelines.geojson"), encoding="utf-8") as _f:
    _PIPELINES = json.load(_f)["features"]


# ------------------------------------------------------------------ main
def write_json(path, doc):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)


def previous_caveats(path):
    """The caveats.json of the previous build, or {} when it is missing or unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def keep_caveats(active, previous, ran):
    """Active caveats, plus the previous entries whose check reads raw/ and did not run this time (a download that
    failed must not remove a warning); the entry must still be in the registry. Registry order."""
    order = [e[0] for e in CV.REGISTRY]
    out = dict(active)
    for cid, e in previous.items():
        if (cid not in out and cid in order and isinstance(e, dict) and e.get("check") in K.RAW_CHECKS
                and e.get("check") not in ran):
            out[cid] = e
    return {cid: out[cid] for cid in sorted(out, key=lambda c: order.index(c) if c in order else len(order))}


def flow_notes(r, kind, pc, f2, pipelines=()):
    """Notes of the latest-year flow of a pair (lane `flow.n`, and the pairs file's `notes` for a pair without a lane):
    the Atlas estimate, the all-modes note of a mixed pair, the K8 and K2 findings. r: the cleaned row or None."""
    out = []
    if r is not None and r.imputed:
        out.append(r.enote)
    if kind == "mixed":
        out.append("Customs total for all modes: this trade moves both by sea and overland and the split is not known"
                   + (". Pipelines on this border in the atlas: " + "; ".join(pipelines) if pipelines else ""))
    if pc and pc["check"] == "K8":
        out.append(pc["text"])
    if f2:
        out.append(f2["text"])
    return ". ".join(n[:1].upper() + n[1:].rstrip(".") for n in out) if out else None


def main():
    t_start = time.time()
    df = pd.read_csv(os.path.join(CACHE, "baci_flows.csv.gz"))
    df = df[df["group"].isin(GROUPS)]
    df = clean_baci(df)  # shared rules: Taiwan code, tonnage repair, Qatari LPG, bulk unit values (pipeline/trade/clean.py)
    print("tonnage estimated from value:", int(df["imputed"].sum()), "flows")
    df = df.reset_index(drop=True)

    # mode of every pair in every year (an LNG terminal counts from its opening year)
    mcache = {}

    def kind_of(o, d, group, year):
        k = (o, d, group, int(year))
        if k not in mcache:
            m = MD.mode_of(o, d, group, int(year))
            mcache[k] = m.kind if m else "land"
        return mcache[k]

    df["mode"] = [kind_of(*k) for k in zip(df["o"], df["d"], df["group"], df["year"])]
    latest = int(df["year"].max())
    years = list(range(LATEST_MIN_YEAR, latest + 1))
    sea = df[df["mode"].isin(["sea", "transit"])]
    mixed = df[df["mode"] == "mixed"]
    cols = ["year", "group", "o", "d", "t", "imputed", "mode"]
    sea[cols].round({"t": 0}).to_csv(os.path.join(CACHE, "sea_flows.csv.gz"), index=False, compression="gzip")
    mixed[cols].round({"t": 0}).to_csv(os.path.join(CACHE, "mixed_flows.csv.gz"), index=False, compression="gzip")
    totals = sea.groupby(["group", "year"])["t"].sum()
    est_tot = sea[sea["imputed"].astype(bool)].groupby(["group", "year"])["t"].sum()  # Atlas estimates in the seaborne totals
    mtot = mixed.groupby(["group", "year"])["t"].sum()
    world = df.groupby(["group", "year"])["t"].sum()
    write_json(os.path.join(CACHE, "seaborne_totals.json"),
               {g: {str(y): {"sea": round(totals.get((g, y), 0)), "all": round(world.get((g, y), 0)),
                             "mixed": round(mtot.get((g, y), 0))} for y in years} for g in GROUPS})

    # checks (single writer of trade_checks.json) and caveats
    ran = set()
    findings = K.run(df, latest, ran=ran)
    active = keep_caveats(CV.build(df, findings, latest), previous_caveats(CAVEATS_OUT), ran)
    write_json(CAVEATS_OUT, active)
    write_json(ZONES_OUT, P.zones())
    k2 = {(r["group"], r["o"], r["d"], r["year"]): r for r in findings if r["check"] == "K2"}
    pair_check = {(r["group"], r["o"], r["d"]): r for r in findings
                  if r["check"] in PAIR_CHECKS and r.get("year") == latest and r.get("o")}
    year_notes = defaultdict(lambda: defaultdict(list))
    for r in findings:
        if r["check"] in ("K6", "K7") and r.get("level") == "flag" and r["group"] in GROUPS:
            year_notes[r["group"]][r["year"]].append(r["text"])
    for r in LAST_DROPPED:
        year_notes[r["group"]][r["year"]].append(None)  # summarised below
    detour_in = []

    os.makedirs(OUT, exist_ok=True)
    os.makedirs(PAIRS_OUT, exist_ok=True)
    unrouted_all = defaultdict(float)
    gates = list(RT.GATES)
    bit = {g: 1 << i for i, g in enumerate(gates)}
    for group, unit in GROUPS.items():
        t_group = time.time()
        g = df[df["group"] == group]
        if g.empty:
            continue
        rows = {}
        for r in g.itertuples(index=False):
            rows[(r.o, r.d, int(r.year))] = r
        gy = g[g["year"] == latest].sort_values("t", ascending=False)
        sea_tot = {y: totals.get((group, y), 0) for y in years}
        tot_latest = sea_tot[latest] or 1
        dest_tot = gy.groupby("d")["t"].sum()
        floor = FLOOR.get(group, FLOOR_DEFAULT) * 1e6

        # route every seaborne and mixed pair of the latest year
        routed, why = {}, {}
        for r in gy.itertuples(index=False):
            if r.mode in ("sea", "transit", "mixed"):
                rec, reason = route_pair(r.o, r.d, group, r.t, r.mode)
                if rec:
                    routed[(r.o, r.d)] = rec
                else:
                    why[(r.o, r.d)] = reason
                    if r.mode != "mixed":
                        unrouted_all[reason] += r.t

        # selection: main set (latest year, floor, cap), mixed lanes, history set
        main, mixed_l = [], []
        for r in gy.itertuples(index=False):
            if r.t < floor or (r.o, r.d) not in routed:
                continue
            if r.mode == "mixed":
                mixed_l.append((r.o, r.d))
            elif len(main) < CAP[group]:
                main.append((r.o, r.d))
        mainset = set(main) | set(mixed_l)
        history, hist_t, hist_y = [], {}, {}
        gs = g[g["mode"].isin(["sea", "transit"])]
        for y in hist_years(latest):
            z = gs[gs["year"] == y].sort_values("t", ascending=False)
            zt = z["t"].sum()
            for r in z.head(HIST_TOP).itertuples(index=False):
                if (r.o, r.d) in mainset or zt <= 0 or r.t / zt < HIST_MIN_SHARE:
                    continue
                if r.t > hist_t.get((r.o, r.d), 0):
                    hist_t[(r.o, r.d)], hist_y[(r.o, r.d)] = r.t, y

        def lane_kind(o, d):
            """Mode of a lane: that of the latest year, or of its history year when the pair has no seaborne row then."""
            k = kind_of(o, d, group, latest)
            return k if k != "land" or (o, d) not in hist_y else kind_of(o, d, group, hist_y[(o, d)])

        for (o, d), t in sorted(hist_t.items(), key=lambda x: -x[1]):
            rec = routed.get((o, d))
            if rec is None:
                rec, _ = route_pair(o, d, group, t, lane_kind(o, d))
            if rec:
                routed.setdefault((o, d), rec)
                history.append((o, d))

        # lanes
        lanes, ports_used = [], {}
        for (o, d), lset in [(k, "main") for k in main + mixed_l] + [(k, "history") for k in history]:
            rec = routed[(o, d)]
            kind = lane_kind(o, d)
            r_latest = rows.get((o, d, latest))
            vlat = float(r_latest.t) if r_latest is not None else 0.0
            a, b = rec["at"][rec["opts"][0][0]], rec["at"][rec["opts"][0][1]]
            s = plan_summary(a, b, rec["classes"], geometry=True)
            speed = VR.speed(rec["classes"][0])
            series = [rows.get((o, d, y)) for y in years]
            tonnes = [float(x.t) / 1e6 if x is not None else 0.0 for x in series]
            values = [float(x.usd) if x is not None else 0.0 for x in series]
            hflags = [x.flag if x is not None else "" for x in series]
            hist, marks = history_flags(tonnes, values, hflags)
            flags, notes = {}, {}
            for i, code in marks.items():
                flags[str(years[i])] = code
                x = series[i]
                if code == "est" and "uv-repair" in (x.flag or ""):
                    notes[str(years[i])] = x.enote
                elif code == "nodata":
                    notes[str(years[i])] = f"No customs record for {years[i]}"
                elif code == "suspect" and x is not None:
                    notes[str(years[i])] = (f"{years[i]}: {_mt(x.t0 / 1e6)} reported for USD {x.usd / 1e3:,.0f} million, a unit value at odds "
                                            "with the neighbouring years; not shown")
            for y in years:
                f = k2.get((group, o, d, y))
                if f:
                    if str(y) not in flags or flags[str(y)] == "kept":
                        flags[str(y)] = "check"
                    notes[str(y)] = (notes[str(y)] + ". " if str(y) in notes else "") + f["text"]
            flow = {"v": round(vlat / 1e6, 3), "u": "Mt", "y": latest, "s": "baci"}
            est = bool(r_latest is not None and r_latest.imputed)
            if est:
                flow["s"], flow["est"] = "atlas", True
            fn = flow_notes(r_latest, kind, pair_check.get((group, o, d)), k2.get((group, o, d, latest)),
                            pipelines_on(o, d, group) if kind == "mixed" else ())
            if fn:
                flow["n"] = fn
            alt_gates = {x for lst in rec["viaAlt"] for x in lst}
            lane = {
                "id": f"{group}:{o}-{d}",
                "k": COMMODITY.get(group, group),
                "p": group,
                "o": o,
                "d": d,
                "set": lset,
            }
            if kind == "mixed":
                lane["mode"] = "mixed"
            if rec["transit"]:
                lane["transit"] = rec["transit"]
            if rec.get("transit2"):
                lane["transit2"] = rec["transit2"]
            lane.update({
                "load": [rec["opts"][0][0]],
                "discharge": [rec["opts"][0][1]],
                "portBasis": rec["basis"],
            })
            if rec["basis"] in ("open", "measured") and len(rec["opts"]) > 1:
                lane["opts"] = [{"load": x[0], "discharge": x[1], "nm": ps["nm"], "days": round(ps["nm"] / (speed * 24), 1),
                                 "via": ps["via"], "w": None} for x, ps in zip(rec["opts"][1:], rec["plans"][1:])]
            lane.update({
                "vclass": rec["classes"],
                "distanceNm": rec["nm"],
                "days": round(rec["nm"] / (speed * 24), 1),
                "via": rec["via"],
                "viaAlt": rec["viaAlt"],
                "flow": flow,
                "share": None if kind == "mixed" else round(vlat / tot_latest, 4),
            })
            if not est:
                lane["shareDest"] = round(vlat / float(dest_tot[d]), 4) if d in dest_tot and dest_tot[d] > 0 else None
            lane["hist"] = [None if v is None else round(v, 3) for v in hist]
            if flags:
                lane["histFlags"] = flags
            if notes:
                lane["histNotes"] = notes
            hn = hist_note({k: v for k, v in flags.items() if v != "kept"}, years)
            if hn:
                lane["histNote"] = hn
            cid = CV.lookup(active, group, o, d)
            if cid:
                lane["caveat"] = cid
            lane["g"] = s["g"]
            alts = []
            for x in s["alts"]:
                x = dict(x)
                if x.pop("redSea", False):
                    x["status"] = [{"text": DISRUPTIONS[0][2], "event": DISRUPTIONS[0][1]}]
                alts.append(x)
            if alts:
                lane["alts"] = alts
            if s.get("altNote"):
                lane["altNote"] = s["altNote"]
            st = status_of(rec["via"], alt_gates)
            if st:
                lane["status"] = st
            lanes.append(lane)
            for code in lane["load"] + [o_["load"] for o_ in lane.get("opts", [])]:
                ports_used.setdefault(code, set()).add(port_use(o, group, "load", code, rec["trows"]))
            for code in lane["discharge"] + [o_["discharge"] for o_ in lane.get("opts", [])]:
                ports_used.setdefault(code, set()).add(port_use(d, group, "discharge", code, rec["trows"]))

        lanes.sort(key=lambda x: (x["set"] != "main", -x["flow"]["v"], -max(v or 0 for v in x["hist"])))
        main_t = sum(rows[(o, d, latest)].t for o, d in main)
        rest, on_main = defaultdict(lambda: [0.0, 0, 0.0]), set(main)
        for r in gy.itertuples(index=False):
            if r.mode in ("sea", "transit") and (r.o, r.d) not in on_main:
                rest[r.o][0] += r.t
                rest[r.o][1] += 1
                if r.imputed:
                    rest[r.o][2] += r.t
        est_t = gy[gy["mode"].isin(["sea", "transit"]) & gy["imputed"]]["t"].sum()
        yn = {}
        for y, texts in sorted(year_notes[group].items()):
            parts = [x for x in texts if x]
            drops = [r for r in LAST_DROPPED if r["group"] == group and r["year"] == y]
            if drops:
                os_ = sorted({r["o"] for r in drops})
                parts.append(f"{len(drops)} rows of {K.label(group)} from {', '.join(K._name(c) for c in os_)} ({_mt(sum(r['t'] for r in drops) / 1e6)}) "
                             "dropped: pairs with no flow in both neighbouring years, which may be LNG cargoes recorded a second time "
                             "under this code; this is not established")
            if parts:
                yn[str(y)] = ". ".join(p[0].upper() + p[1:].rstrip(".") for p in parts)
        # share of each year's seaborne tonnes that is an Atlas estimate, and a line for the years where it shows
        est_y = [round(est_tot.get((group, y), 0) / sea_tot[y], 3) if sea_tot[y] else 0 for y in years]
        for y in years:
            e = est_tot.get((group, y), 0)
            if sea_tot[y] and e / sea_tot[y] >= EST_NOTE_MIN:
                txt = (f"Includes {_mt(e / 1e6)} of Atlas estimates ({e / sea_tot[y]:.1%} of the year's seaborne tonnes): "
                       "tonnage estimated from declared value")
                yn[str(y)] = (yn[str(y)] + ". " if str(y) in yn else "") + txt
        rep = g[g["flag"].str.contains("uv-repair", na=False) | g["flag"].str.contains("uv-suspect-t", na=False)]
        for y, z in rep.groupby("year"):
            if y < LATEST_MIN_YEAR:
                continue
            big = z[(z["t"] >= 0.01 * (sea_tot.get(y) or 1)) | (z["t0"] >= 0.01 * (sea_tot.get(y) or 1))].sort_values("t", ascending=False)
            if big.empty:
                continue
            if "uv-repair" in "".join(big["flag"]):
                txt = "Includes Atlas estimates for pairs whose declared tonnage is at odds with their value: " + "; ".join(
                    f"{K._name(r.o)} to {K._name(r.d)} {_mt(r.t / 1e6)} (customs data: {_mt(r.t0 / 1e6)})" for r in big.head(5).itertuples())
            else:
                txt = "The total includes declared tonnages at odds with their value: " + "; ".join(
                    f"{K._name(r.o)} to {K._name(r.d)} {_mt(r.t0 / 1e6)}" for r in big.head(5).itertuples())
            yn[str(int(y))] = (yn[str(int(y))] + ". " if str(int(y)) in yn else "") + txt
        doc = {
            "group": group,
            "k": COMMODITY.get(group, group),
            "label": LABEL.get(group),
            "unit": unit,
            "y": latest,
            "s": "baci",
            "years": years,
            "seaborne": [round(sea_tot[y] / 1e6, 2) for y in years],
            "mixed": [round(mtot.get((group, y), 0) / 1e6, 2) for y in years],
            "world": [round(world.get((group, y), 0) / 1e6, 2) for y in years],
            "yearNotes": dict(sorted(yn.items())),
            "est": round(est_t / tot_latest, 4),
            "estY": est_y,
            "coverage": {"lanes": len(main), "share": round(main_t / tot_latest, 4)},
            "rest": [{"o": o, "v": round(v / 1e6, 3), "n": n, **({"est": float(f"{e / 1e6:.3g}")} if e > 0 else {})}
                     for o, (v, n, e) in sorted(rest.items(), key=lambda x: -x[1][0])],
            "ports": {c: port_entry(c, ports_used[c]) for c in sorted(ports_used)},
            "lanes": lanes,
        }
        write_json(os.path.join(OUT, f"{group}.json"), doc)

        # pairs table: every recorded pair of the latest year
        pport, pcls, prow, puse, pnotes = {}, {}, [], defaultdict(set), {}
        lane_pairs = set(main) | set(mixed_l)
        for r in gy.itertuples(index=False):
            rec = routed.get((r.o, r.d)) if r.mode != "land" else None
            f = (F_EST if r.imputed else 0) | (F_CAVEAT if CV.lookup(active, group, r.o, r.d) else 0)
            f |= (F_LANE if (r.o, r.d) in lane_pairs else 0) | (F_CHECK if (group, r.o, r.d) in pair_check else 0)
            if f & (F_EST | F_CHECK) and not f & F_LANE:
                # the note the lane would carry, for the pairs that have none (Route finder)
                fn = flow_notes(r, r.mode, pair_check.get((group, r.o, r.d)), k2.get((group, r.o, r.d, latest)),
                                pipelines_on(r.o, r.d, group) if r.mode == "mixed" else ())
                if fn:
                    pnotes[f"{r.o}-{r.d}"] = fn
            m = M_CODE[r.mode]
            if rec:
                lo, di = rec["opts"][0]
                for code in (lo, di):
                    if code not in pport:
                        pport[code] = len(pport)
                puse[lo].add(port_use(r.o, group, "load", lo, rec["trows"])[0])
                puse[di].add(port_use(r.d, group, "discharge", di, rec["trows"])[0])
                cls = rec["classes"][0]
                if cls not in pcls:
                    pcls[cls] = len(pcls)
                via = sum(bit[x] for x in rec["via"])
                alt = sum(bit[x] for x in {x for lst in rec["viaAlt"] for x in lst})
                prow.append([r.o, r.d, kt(r.t), m, pport[lo], pport[di], rec["nm"], pcls[cls], via, alt, f])
                if r.mode != "mixed":
                    a, b = rec["at"][lo], rec["at"][di]
                    detour_in.append({"group": group, "o": r.o, "d": r.d, "t": r.t, "nm": rec["nm"], "gc_nm": round(gc_nm(a, b)),
                                      "load": lo, "dis": di})
            else:
                prow.append([r.o, r.d, kt(r.t), m, -1, -1, 0, -1, 0, 0, f])
        assert len(gates) <= 31  # JavaScript bit operations are 32-bit
        pdoc = {
            "group": group, "k": COMMODITY.get(group, group), "y": latest, "s": "baci", "unit": "kt",
            "seaborne": round(sea_tot[latest] / 1e3),
            # [code, name, country, zone, basis]: basis indexes `bases`, the weakest of the roles the port has in this file
            "ports": [[c, P.port(c)["name"], port_iso3(c), (_meta.get(c) or P.port_meta(c)).get("zone"),
                       max(BASIS_RANK[b] for b in puse[c])] for c in pport],
            "bases": list(P.BASES),
            "classes": list(pcls),
            "gates": gates,
            "cols": ["o", "d", "kt", "m", "load", "dis", "nm", "cls", "via", "alt", "f"],
            "rows": prow,
            "notes": pnotes,
        }
        write_json(os.path.join(PAIRS_OUT, f"{group}.json"), pdoc)
        n_main = len(main)
        print(f"{group:18s} main={n_main:3d} mixed={len(mixed_l):2d} history={len(history):2d} seaborne {latest}={sea_tot[latest] / 1e6:8.1f} Mt  "
              f"covered={main_t / tot_latest:.1%}  pairs={len(prow)}  not routed={sum(1 for k in why if kind_of(k[0], k[1], group, latest) != 'mixed')}  "
              f"{time.time() - t_group:.0f}s", flush=True)
        save_geom_cache()
        RT._routes.clear()  # in-process memo of raw routes: the plans are in the caches

    # check K12 (detour of the main route against the great-circle distance), then the single write of the checks
    findings += K.detour(detour_in, latest)
    ran.add("K12")
    K.save(findings, ran, latest)
    save_geom_cache()
    print("seaborne tonnage not routed, by reason (Mt):", {k: round(v / 1e6, 1) for k, v in sorted(unrouted_all.items())})
    print(f"build_lanes: {time.time() - t_start:.0f} s")


if __name__ == "__main__":
    main()
