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
import river_legs as RL  # noqa: E402
import routing as RT  # noqa: E402
import vessel_rules as VR  # noqa: E402

sys.path.insert(0, os.path.join(HERE, "..", "trade"))
import caveats as CV  # noqa: E402
import checks as K  # noqa: E402
sys.path.insert(0, os.path.join(HERE, ".."))
from common import constants as CN  # noqa: E402  (the Earth radius and the nautical mile, with the page that gives each)
from clean import LAST_DROPPED, LITHIUM_MIN_UV, clean as clean_baci, despike, history_flags  # noqa: E402,F401  (despike: used by build_freight.py)

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
    "coffee": "Mt", "cocoa": "Mt", "cotton": "Mt", "nickel-fe": "Mt", "spodumene": "Mt",
    # minor metals (M-015): concentrate in bulk like zinc concentrate, the others as general cargo like refined copper
    "lead-ore": "Mt", "lead-metal": "Mt", "zinc-metal": "Mt", "tin-metal": "Mt", "tin-ore": "Mt", "cobalt": "Mt",
    "lithium": "Mt", "rare-earths": "Mt",
    # the other fertilisers and sulphur (M-022); ammonia, UAN and phosphoric acid are liquids (vessel_rules.py)
    "potassium-sulphate": "Mt", "monoammonium-phosphate": "Mt", "superphosphates": "Mt", "phosphoric-acid": "Mt", "npk": "Mt",
    "ammonia": "Mt", "ammonium-nitrate": "Mt", "uan": "Mt", "ammonium-sulphate": "Mt", "sulphur": "Mt",
    # ammonium nitrate with limestone (HS 310240) and the two-nutrient compounds (HS 310551, 310559, 310560), added with review GNC1.4
    "ammonium-nitrate-limestone": "Mt", "npk-two-nutrient": "Mt",
    # the grains, oilseeds and products added with M-023: the oils sail in tankers, the rest as grain in dry bulk (vessel_rules.py).
    # Wheat flour and brewing and distilling dregs go in bags and boxes for a large part: tables only, no lanes
    "barley": "Mt", "sorghum": "Mt", "sunflower-seed": "Mt", "sunflower-oil": "Mt", "sunflower-meal": "Mt",
    "rapeseed-oil": "Mt", "rapeseed-meal": "Mt", "pulses": "Mt",
    # the metal bulks added with A-010: scrap, chromite, pig iron, direct-reduced iron and coke sail in bulk, the ferro-alloys as general cargo
    "ferrous-scrap": "Mt", "chromium-ore": "Mt", "pig-iron": "Mt", "dri": "Mt", "coke": "Mt",
    "ferro-chromium": "Mt", "ferro-manganese": "Mt", "silico-manganese": "Mt", "ferro-silicon": "Mt",
}
# atlas commodity id for each group (the site loads lanes by commodity)
COMMODITY = {
    "coal": "thermal-coal", "alumina": "bauxite", "copper-ore": "copper", "copper-refined": "copper",
    "nickel-ore": "nickel", "nickel-int": "nickel", "zinc-ore": "zinc", "phosphate-rock": "phosphate",
    "dap": "phosphate", "nickel-fe": "nickel", "spodumene": "lithium",
    "lead-ore": "lead", "lead-metal": "lead", "zinc-metal": "zinc", "tin-metal": "tin", "tin-ore": "tin",
    "potassium-sulphate": "potash", "monoammonium-phosphate": "phosphate", "superphosphates": "phosphate",
    "phosphoric-acid": "phosphate", "ammonia": "urea", "ammonium-nitrate": "urea", "uan": "urea", "ammonium-sulphate": "urea",
    "ammonium-nitrate-limestone": "urea", "npk-two-nutrient": "npk",
    "sunflower-seed": "sunflower", "sunflower-oil": "sunflower", "sunflower-meal": "sunflower",
    "rapeseed-oil": "rapeseed", "rapeseed-meal": "rapeseed",
    "chromium-ore": "chromium", "dri": "pig-iron", "coke": "met-coal",
    "ferro-chromium": "ferro-alloys", "ferro-manganese": "ferro-alloys", "silico-manganese": "ferro-alloys", "ferro-silicon": "ferro-alloys",
}
LABEL = {
    "coal": "Coal (all types)", "copper-ore": "Copper concentrate", "copper-refined": "Refined & blister copper",
    "nickel-ore": "Nickel ore", "nickel-int": "Nickel matte, intermediates & metal", "zinc-ore": "Zinc concentrate",
    "phosphate-rock": "Phosphate rock", "dap": "DAP", "alumina": "Alumina", "bauxite": "Bauxite",
    "nickel-fe": "Ferro-nickel and nickel pig iron", "spodumene": "Spodumene concentrate (Atlas estimate)",
    "lead-ore": "Lead concentrate", "lead-metal": "Unwrought lead", "zinc-metal": "Unwrought zinc",
    "tin-metal": "Unwrought tin", "tin-ore": "Tin concentrate", "cobalt": "Cobalt intermediates, metal and ores",
    "lithium": "Lithium carbonate and hydroxide", "rare-earths": "Rare-earth metals and compounds",
    "potassium-sulphate": "Potassium sulphate (SOP)", "monoammonium-phosphate": "MAP", "superphosphates": "Superphosphates",
    "phosphoric-acid": "Phosphoric acid", "ammonia": "Ammonia", "ammonium-nitrate": "Ammonium nitrate", "uan": "UAN solution",
    "ammonium-sulphate": "Ammonium sulphate",
    # HS 310240 is ammonium nitrate mixed with calcium carbonate or other inorganic substances (calcium ammonium nitrate); the three codes of
    # the second group are the compounds that carry two of the three nutrients (nitrates and phosphates, nitrogen and phosphorus, phosphorus and potassium)
    "ammonium-nitrate-limestone": "Ammonium nitrate with limestone", "npk-two-nutrient": "Two-nutrient compound fertilisers",
    # what each code holds in HS 1992 (the oils' codes hold two oils each; pulses are every dried leguminous vegetable, shelled)
    "sunflower-seed": "Sunflower seed", "sunflower-oil": "Sunflower and safflower oil", "sunflower-meal": "Sunflower meal",
    "rapeseed-oil": "Rapeseed, canola and mustard oil", "rapeseed-meal": "Rapeseed meal", "pulses": "Dried pulses",
    # what each code holds in HS 1992 (A-010): heading 7204 is every ferrous waste and scrap; 7203 also holds spongy ferrous products and
    # iron of 99.94% purity or more; 2704 is coke and semi-coke of coal, lignite or peat; the last ferro-alloy group is every alloy
    # of heading 7202 that has no group of its own, ferro-nickel excepted
    "ferrous-scrap": "Ferrous scrap", "chromium-ore": "Chromium ore (chromite)", "pig-iron": "Pig iron",
    "dri": "Direct-reduced iron and spongy iron", "coke": "Coke and semi-coke", "ferro-chromium": "Ferro-chromium",
    "ferro-manganese": "Ferro-manganese", "silico-manganese": "Silico-manganese", "ferro-silicon": "Ferro-silicon",
}
# Groups that are an Atlas estimate by construction (a read of a customs code that mixes products, hs_map.SPLIT): their
# flows, lane file and pairs file carry the source id "atlas" and this note of the method.
EST_GROUP = {
    "spodumene": ("Atlas estimate: spodumene concentrate has no customs code of its own; the atlas reads it from HS 253090 "
                  "('mineral substances not elsewhere specified', CEPII BACI customs data, gross weight), keeping only the rows from "
                  "Australia, Zimbabwe and Brazil to China, the exporters for which a page read by the atlas says that they ship "
                  "lithium concentrate to China (the pages are listed on the lithium page). These rows may still hold other minerals"),
}
# First year from which a page supports the reading of such a group; the earlier years are published as null points
# (flag "nodata") with the note.
FIRST_YEAR = {
    "spodumene": (2021, "Not read as spodumene before 2021: Australia's statistics office created the national subheading 25309011 "
                        "'Lithium concentrates' in January 2021 (Australian Bureau of Statistics, Insights into Australian Exports of "
                        "Lithium, 4 August 2022); no page read says what HS 253090 from these exporters held before"),
}

# Selection of the lanes (trade-engine plan 2.2). Caps bound the main set of each group; the floor is the smallest
# latest-year tonnage of a main lane (Mt).
CAP = {
    "crude-oil": 120, "refined-products": 150, "lng": 100, "lpg": 80, "coal": 100, "iron-ore": 60, "steel": 150,
    "wheat": 120, "corn": 100, "soybeans": 60, "soymeal": 80, "rice": 100, "sugar": 100, "urea": 100, "dap": 60,
    "potash": 60, "phosphate-rock": 60, "palm-oil": 80, "soyoil": 60, "rapeseed": 50, "bauxite": 40, "alumina": 60,
    "manganese": 40, "copper-ore": 60, "copper-refined": 80, "aluminium": 100, "nickel-ore": 20, "nickel-int": 40,
    "zinc-ore": 60, "coffee": 100, "cocoa": 60, "cotton": 60, "nickel-fe": 40, "spodumene": 20,
    "lead-ore": 60, "lead-metal": 60, "zinc-metal": 60, "tin-metal": 40, "tin-ore": 20, "cobalt": 20, "lithium": 30,
    "rare-earths": 30,
    "potassium-sulphate": 40, "monoammonium-phosphate": 60, "superphosphates": 40, "phosphoric-acid": 40, "npk": 80,
    "ammonia": 60, "ammonium-nitrate": 40, "uan": 40, "ammonium-sulphate": 60, "sulphur": 60,
    "ammonium-nitrate-limestone": 40, "npk-two-nutrient": 60,
    "barley": 80, "sorghum": 40, "sunflower-seed": 60, "sunflower-oil": 60, "sunflower-meal": 60, "rapeseed-oil": 60,
    "rapeseed-meal": 40, "pulses": 80,
    "ferrous-scrap": 80, "chromium-ore": 30, "pig-iron": 40, "dri": 30, "coke": 60,
    "ferro-chromium": 40, "ferro-manganese": 40, "silico-manganese": 40, "ferro-silicon": 60,
}
# The minor metals trade in parcels of a few thousand tonnes (tin, cobalt, lithium and rare-earth groups hold 0.1 to
# 0.7 Mt a year in all) and unwrought lead and zinc over hundreds of small pairs: their floor is lower, so that the main
# set carries about two thirds of their seaborne tonnes or more (unwrought tin: 60%).
FLOOR = {"coffee": 0.02, "cocoa": 0.02, "cotton": 0.02, "nickel-int": 0.02, "copper-refined": 0.02, "zinc-ore": 0.02,
         "aluminium": 0.03, "soyoil": 0.03, "lead-ore": 0.02, "lead-metal": 0.01, "zinc-metal": 0.015,
         "tin-metal": 0.001, "tin-ore": 0.002, "cobalt": 0.002, "lithium": 0.005, "rare-earths": 0.002,
         # potassium sulphate (1.5 Mt over 193 seaborne pairs, 54 kt at most) and ammonium nitrate (a few large pairs over 300 small
         # ones): the default floor kept 21% and 57% of their seaborne tonnes in the main set (M-022)
         "potassium-sulphate": 0.01, "ammonium-nitrate": 0.02,
         # ammonium nitrate with limestone (4.1 Mt by sea over 281 pairs): the default floor kept 62% of its seaborne tonnes (FNCB)
         "ammonium-nitrate-limestone": 0.02,
         # sunflower seed (2.2 Mt by sea over 358 pairs) and rapeseed oil (2.8 Mt over 323 pairs) trade in parcels of a few tens of
         # thousands of tonnes: the default floor kept 49% and 35% of their seaborne tonnes in the main set (M-023)
         "sunflower-seed": 0.01, "rapeseed-oil": 0.01,
         # the ferro-alloys (A-010) trade in parcels of a few thousand tonnes: ferro-manganese and silico-manganese (1.6 and 2.7 Mt by sea over
         # 146 and 217 pairs) and ferro-silicon (1.8 Mt over 266 pairs) kept 39%, 45% and 31% of their seaborne tonnes in the main set at the
         # default floor; ferro-silicon, more scattered, needs a lower floor than the other two. The other ferro-alloys (0.58 Mt over 396 sea and transit pairs, seven
         # codes of different alloys) reach no coverage at a floor that leaves a readable set: they have tables and no lanes
         "ferro-manganese": 0.02, "silico-manganese": 0.02, "ferro-silicon": 0.005}
FLOOR_DEFAULT = 0.05
# history set: the largest seaborne pairs of these years that are not in the main set (fixed early years, then the
# three years before the latest, so that a new BACI year moves the window)
HIST_EARLY = (2005, 2010, 2015, 2019)
HIST_TOP, HIST_MIN_SHARE = 10, 0.01


def hist_years(latest):
    return tuple(sorted(set(HIST_EARLY) | {latest - 3, latest - 2, latest - 1}))


HIST_YEARS = hist_years(2024)  # the years of the 2024 build; main() uses hist_years(latest)
SMALL_MT = 1.0  # a group whose latest seaborne total is under this (Mt) is published in kt, with one decimal
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
    return CN.EARTH_RADIUS_KM * math.hypot(x, y)


def gc_nm(a, b):
    """Great-circle distance between two [lon, lat] points, nautical miles (check K12)."""
    p = math.pi / 180
    h = math.sin((b[1] - a[1]) * p / 2) ** 2 + math.cos(a[1] * p) * math.cos(b[1] * p) * math.sin((b[0] - a[0]) * p / 2) ** 2
    return 2 * CN.EARTH_RADIUS_KM * math.asin(math.sqrt(h)) / CN.KM_PER_NAUTICAL_MILE


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
    basis, src, url = max(use, key=lambda u: (BASIS_RANK[u[0]], u[1] or "", u[2] or ""))  # same pick on every run
    out = {"id": code, "name": p["name"], "c": port_iso3(code), "at": p["at"], "zone": m.get("zone"), "basis": basis, "s": src}
    if url:
        out["url"] = url
    river = RL.public(code, p["name"])
    if river:  # a port up a river: the distance of every lane through it includes the leg (river_legs.py)
        out["river"] = river
    return out


BASIS_RANK = {b: i for i, b in enumerate(P.BASES)}  # strongest first


def port_use(iso3, group, role, code, transit_rows=()):
    """(basis, source id, url) of a port at one end of a pair: its TRANSIT row when it is the end's transit port (a
    family row is a page that names the cargo, a "default" row a general port of that country's trade), else the
    gateway row behind ports.basis_of()."""
    for t in transit_rows:
        if t and code in t.get("ports", [t["port"]]) and t["end"] == iso3:
            return t.get("basis") or (P.BASIS_PAGE if t["family"] else P.BASIS_GENERAL), t["s"], t["url"]
    basis = P.basis_of(iso3, group, role, code)
    s, url = P.source_of(iso3, group, role, code)
    return basis, s, url


def mode_of(o, d, group):
    """Compatibility wrapper: "sea" for a seaborne pair (sea or transit), "land" otherwise (mixed, land, no mode)."""
    m = MD.mode_of(o, d, group)
    return "sea" if m and m.kind in ("sea", "transit") else "land"


def split_known(df):
    """A pair-year of mode "mixed" whose split a source measures (modes.KNOWN_SPLIT) becomes two rows: its tonnage by sea (mode "sea",
    `split` = "sea", the lane and the seaborne totals read it) and the rest (mode "land", `split` = "rest"), each with its share of the
    declared value. The two rows add up to the pair's tonnage, so every total over all modes stays as it was. The rows of the other
    pair-years are untouched (`split` empty). The checks of K and the caveats read the frame before this cut."""
    df = df.assign(split="", t_all=float("nan"), sea_share=float("nan"))
    if df["mode"].eq("mixed").any():
        keys = [(o, d, g, int(y)) for o, d, g, y in zip(df["o"], df["d"], df["group"], df["year"])]
        sh = pd.Series([MD.known_split(o, d, g, y)[0] if m == "mixed" and MD.known_split(o, d, g, y) else None
                        for (o, d, g, y), m in zip(keys, df["mode"])], index=df.index, dtype=float)
        hit = sh.notna()
        if hit.any():
            sea, rest = df[hit].copy(), df[hit].copy()
            for part, f, mode, tag in ((sea, sh[hit], "sea", "sea"), (rest, 1 - sh[hit], "land", "rest")):
                part["t_all"], part["sea_share"] = part["t"], sh[hit]
                part["t"], part["usd"], part["mode"], part["split"] = part["t"] * f, part["usd"] * f, mode, tag
            df = pd.concat([df[~hit], sea, rest], ignore_index=True)
    return df


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
    is one more "one of" list. A parallel group that the main option crosses stays one list (the drawn route uses one
    of its members); a group that only another option crosses is one list per member (the gates crossed together stay
    together), which the site prints "may also cross": the drawn route uses none of them."""
    sets = [set(s["via"]) for s in summaries]
    via = [g for g in summaries[0]["via"] if all(g in x for x in sets)]
    main_gates = set(summaries[0]["via"]) | {g for lst in summaries[0]["viaAlt"] for g in lst}
    lists = []
    for lst in _merge_lists([lst for s in summaries for lst in s["viaAlt"]]):
        if len(lst) > 1 and not main_gates & set(lst):
            members = [m for grp in RT.PARALLEL for m in grp if m & set(lst)]
            lists.extend([g for g in lst if g in m] for m in members)
            lists.extend([g] for g in lst if not any(g in m for m in members))
        else:
            lists.append(lst)
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


def transit_row(iso3, group, other=None):
    """TRANSIT row of a country for the group's cargo (ports.transit_for: the group's own row, its family's, or the
    "default" one) and the partner `other`: {port, c, s, url} plus `end`, `ports` (the principal port, then the ports
    that are an open choice for that partner), `family` (whether the row is a cargo row, not the "default" one) and
    `basis` (a cargo row that names other groups only is a general port for this one). None when no page was read, or
    when the row's page names other buyers only."""
    row = P.transit_for(iso3, MD.FAMILY.get(group), group, other)
    if not row:
        return None
    code, src, url, _, extra, key = row
    alts = [c for c, to in (extra.get("alt") or {}).items() if to is None or other is None or other in to]
    cargo = key != "default" and group in extra.get("names", {group})
    return {"port": code, "c": port_iso3(code), "s": src, "url": url, "end": iso3, "family": key != "default",
            "ports": [code] + alts, "basis": P.BASIS_PAGE if cargo else P.BASIS_GENERAL}


def public_transit(t):
    """The `transit` of a lane: {port, c, s, url, landlocked}. `landlocked` says whether the end has no coast at all (from the
    adjacency data, modes.coastal), or has one and still ships through this foreign port (DR Congo through Dar es Salaam)."""
    return {**{k: t[k] for k in ("port", "c", "s", "url")}, "landlocked": not MD.coastal(t["end"])} if t else None


def transit_of(o, d, group):
    """Transit row of the landlocked end of a pair: (end, {port, c, s, url}) or (end, None) when no page was read."""
    end = o if not MD.coastal(o) else d
    return end, public_transit(transit_row(end, group, d if end == o else o))


def transit_ends(o, d, kind):
    """Ends of a pair that reach the sea through a foreign port: the landlocked ends of a transit or mixed pair
    (Belarusian potash to China), and a coast with no port of its own that has a TRANSIT row (Bosnia and Herzegovina,
    through Ploce)."""
    out = [e for e in (o, d) if kind in ("transit", "mixed") and not MD.coastal(e)]
    return out + [e for e in (o, d) if e not in out and MD.coastal(e) and e in P.TRANSIT]


# Minor metals (package L1): many of their ports have no page for the cargo, and a lane from the wrong coast of a country
# draws passages and chokepoint tonnes that the trade does not cross (review GL1.3: Russian lead concentrate for China from
# Novorossiysk through Suez). A pair whose route is more than DETOUR times the great-circle distance of its two ports is not
# routed when an end's port has no page that names the cargo and either (1) another port of that country in the atlas's
# tables reaches the other end in under NEAR_SHARE of the distance, or (2) the port is only the country's nearest seaport.
COAST_CHECK = P.BOX_GENERAL | {"lead-ore"}
DETOUR, NEAR_SHARE = 1.8, 0.6


def own_ports(iso3):
    """Ports of a country in the atlas's tables (gateway rows of any cargo, the legacy table), in that country."""
    codes = [r.code for r in P.G.get(iso3, ())] + list((P.LEGACY_P.get(iso3) or {}).values())
    return [c for c in dict.fromkeys(codes) if P._known(c) and port_iso3(c) == iso3]


def wrong_coast(o, d, group, opt, at, nm, classes, trows):
    """The reason a pair of a COAST_CHECK group is not routed (see above), or None."""
    if nm <= DETOUR * gc_nm(at[opt[0]], at[opt[1]]):
        return None
    for iso3, role, mine, other in ((o, "load", opt[0], opt[1]), (d, "discharge", opt[1], opt[0])):
        if iso3 in trows or port_iso3(mine) != iso3:
            continue
        basis = P.basis_of(iso3, group, role, mine)
        if basis == P.BASIS_PAGE:
            continue
        if basis == P.BASIS_NEAREST:
            return "only the nearest seaport, on a long detour"
        for code in own_ports(iso3):
            s = plan_summary(P.port(code)["at"], at[other], classes) if code != mine else None
            if s and s["nm"] < NEAR_SHARE * nm:
                return "port on the other coast of the country"
    return None


def route_pair(o, d, group, t, kind):
    """Ports and route of a seaborne or mixed pair. Returns a record, or (None, reason) when the pair is not routed.
    A landlocked end uses its TRANSIT port whatever the gateway rows hold; a pair of two landlocked countries is
    routed between their two transit ports (`transit` for the loading end, `transit2` for the discharging end)."""
    a = P.assign(o, d, group)
    opts = [(x.load, x.discharge) for x in a.options]
    basis, transit, transit2, trows = a.basis, None, None, {}
    for end in transit_ends(o, d, kind):
        row = transit_row(end, group, d if end == o else o)
        if row:
            trows[end] = row
        elif not MD.coastal(end):
            return None, "no sourced transit port"
    if trows:
        # a transit row with an open choice of ports for this partner gives one option per port (principal first)
        opts = [(lo, di) for oo, dd in opts for lo in (trows[o]["ports"] if o in trows else [oo])
                for di in (trows[d]["ports"] if d in trows else [dd])]
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
    if group in COAST_CHECK:
        why = wrong_coast(o, d, group, opts[0], at, main["nm"], classes, trows)
        if why:
            return None, why
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


def hist_note(flags, years, volume=()):
    """Compatibility text of the chart note (the site shows `histNote` until it reads `histFlags`). volume: the years whose tonnage is
    estimated from a volume (rule 10 of clean.py), not from the declared value."""
    by = defaultdict(list)
    for y, f in sorted(flags.items()):
        by[f].append(y)
    parts = []
    if [y for y in by.get("est", []) if y in volume]:
        parts.append("Atlas estimate (tonnage from the volume in the United States' own export statistics, not the customs tonnage) for "
                     + ", ".join(y for y in by["est"] if y in volume))
    if [y for y in by.get("est", []) if y not in volume]:
        parts.append("Atlas estimate (tonnage estimated from declared value) for " + ", ".join(y for y in by["est"] if y not in volume))
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
    failed must not remove a warning); the entry must still be in the registry (the entries of check K14, one per exporter, are built from the data and are
    in the registry while their group is in K.NO_PRODUCTION: FNCF, review GV6B.1, a build without the EIA file dropped them). Registry order."""
    order = [e[0] for e in CV.REGISTRY]
    out = dict(active)
    for cid, e in previous.items():
        if (cid not in out and isinstance(e, dict) and e.get("check") in K.RAW_CHECKS and e.get("check") not in ran
                and (cid in order or (e.get("kind") == "no-production" and e.get("group") in K.NO_PRODUCTION))):
            out[cid] = e
    return {cid: out[cid] for cid in sorted(out, key=lambda c: order.index(c) if c in order else len(order))}


def flow_notes(r, kind, pc, f2, pipelines=()):
    """Notes of the latest-year flow of a pair (lane `flow.n`, and the pairs file's `notes` for a pair without a lane):
    the Atlas estimate, the all-modes note of a mixed pair, the K8 and K2 findings. r: the cleaned row or None."""
    out = []
    if r is not None and (r.imputed or r.flag == "added"):
        out.append(r.enote)
    if r is not None and getattr(r, "split", "") == "sea":
        out.append("The tonnage of this lane is its share by sea. " + MD.split_note(r.sea_share, MD.known_split(r.o, r.d, r.group, int(r.year))[1],
                                                                                   int(r.year), _mt(r.t_all / 1e6)))
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
    whole = df  # the checks and the caveats read a pair as one row; the lanes and the totals read it cut by mode (split_known)
    df = split_known(df)
    latest = int(df["year"].max())
    years = list(range(LATEST_MIN_YEAR, latest + 1))
    sea = df[df["mode"].isin(["sea", "transit"])]
    mixed = df[df["mode"] == "mixed"]
    cols = ["year", "group", "o", "d", "t", "imputed", "mode"]
    # mtime 0: the gzip header carries no clock time, so an unchanged frame gives an unchanged file
    gz = {"method": "gzip", "mtime": 0}
    sea[cols].round({"t": 0}).to_csv(os.path.join(CACHE, "sea_flows.csv.gz"), index=False, compression=gz)
    mixed[cols].round({"t": 0}).to_csv(os.path.join(CACHE, "mixed_flows.csv.gz"), index=False, compression=gz)
    totals = sea.groupby(["group", "year"])["t"].sum()
    est_tot = sea[sea["imputed"].astype(bool)].groupby(["group", "year"])["t"].sum()  # Atlas estimates in the seaborne totals
    mtot = mixed.groupby(["group", "year"])["t"].sum()
    world = df.groupby(["group", "year"])["t"].sum()
    write_json(os.path.join(CACHE, "seaborne_totals.json"),
               {g: {str(y): {"sea": round(totals.get((g, y), 0)), "all": round(world.get((g, y), 0)),
                             "mixed": round(mtot.get((g, y), 0))} for y in years} for g in GROUPS})

    # checks (single writer of trade_checks.json) and caveats
    ran = set()
    findings = K.run(whole, latest, ran=ran)
    active = keep_caveats(CV.build(whole, findings, latest), previous_caveats(CAVEATS_OUT), ran)
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
    for r in whole[whole["flag"].str.contains("est-volume", na=False)].itertuples():
        if r.group in GROUPS:
            year_notes[r.group][int(r.year)].append(
                f"{K._name(r.o)} to {K._name(r.d)}: the customs tonnage of {_mt(r.t0 / 1e6)} is the volume in cubic metres read as tonnes; "
                f"replaced by {_mt(r.t / 1e6)}, an Atlas estimate from the United States' own export statistics (see the lane's note)")
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
            if r.split != "rest":  # the rest of a pair cut by split_known is not the pair's row
                rows[(r.o, r.d, int(r.year))] = r
        gy = g[g["year"] == latest].sort_values("t", ascending=False)
        sea_tot = {y: totals.get((group, y), 0) for y in years}
        tot_latest = sea_tot[latest] or 1
        dest_tot = gy.groupby("d")["t"].sum()
        floor = FLOOR.get(group, FLOOR_DEFAULT) * 1e6
        # a group under SMALL_MT a year (tin, cobalt, lithium, rare earths) is published in kt with 0.1 kt, as its commodity
        # page prints it (review GL1.9: one unit per group on every page that reads the lane file's `unit`)
        small = tot_latest < SMALL_MT * 1e6
        unit, div = ("kt", 1e3) if small else (unit, 1e6)
        nd, nt = (1, 1) if small else (3, 2)

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
            if r.t < floor or (r.o, r.d) not in routed or r.split == "rest":
                continue
            if r.mode == "mixed":
                mixed_l.append((r.o, r.d))
            elif len(main) < CAP[group]:
                main.append((r.o, r.d))
        mainset = set(main) | set(mixed_l)
        history, hist_t, hist_y = [], {}, {}
        gs = g[g["mode"].isin(["sea", "transit"])]
        first = FIRST_YEAR.get(group)
        for y in hist_years(latest):
            if first and y < first[0]:
                continue
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
            r_latest = rows.get((o, d, latest))
            # a pair cut by split_known is a sea lane in the year of the split: its tonnage is the share by sea
            kind = "sea" if r_latest is not None and r_latest.split == "sea" else lane_kind(o, d)
            vlat = float(r_latest.t) if r_latest is not None else 0.0
            a, b = rec["at"][rec["opts"][0][0]], rec["at"][rec["opts"][0][1]]
            s = plan_summary(a, b, rec["classes"], geometry=True)
            speed = VR.speed(rec["classes"][0])
            series = [rows.get((o, d, y)) for y in years]
            # a pair cut by split_known keeps its history in all modes, as the years before the year of the split: the sea share is in the lane note
            tonnes = [(float(x.t_all) if x.split == "sea" else float(x.t)) / 1e6 if x is not None else 0.0 for x in series]
            values = [(float(x.usd) / x.sea_share if x.split == "sea" else float(x.usd)) if x is not None else 0.0 for x in series]
            hflags = [x.flag if x is not None else "" for x in series]
            if first:
                tonnes = [None if y < first[0] else t for y, t in zip(years, tonnes)]
            hist, marks = history_flags(tonnes, values, hflags)
            if first:
                marks.update({i: "nodata" for i, y in enumerate(years) if y < first[0]})
            flags, notes = {}, {}
            for i, code in marks.items():
                flags[str(years[i])] = code
                x = series[i]
                if code == "est" and any(c in (x.flag or "") for c in ("uv-repair", "est-peer", "est-volume")):
                    notes[str(years[i])] = x.enote
                elif code == "nodata" and first and years[i] < first[0]:
                    notes[str(years[i])] = f"{years[i]}: no figure, the reading of the customs code starts in {first[0]} (see the lane note)"
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
            flow = {"v": round(vlat / div, nd), "u": unit, "y": latest, "s": "baci"}
            est = bool(r_latest is not None and r_latest.imputed)
            if est:
                flow["s"], flow["est"] = "atlas", True
            fn = flow_notes(r_latest, kind, pair_check.get((group, o, d)), k2.get((group, o, d, latest)),
                            pipelines_on(o, d, group) if kind == "mixed" else ())
            if group in EST_GROUP:
                flow["s"] = "atlas"
                fn = EST_GROUP[group] + (". " + fn if fn else "")
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
            lane["hist"] = [None if v is None else round(v * 1e6 / div, nd) for v in hist]
            if flags:
                lane["histFlags"] = flags
            if notes:
                lane["histNotes"] = notes
            hn = hist_note({k: v for k, v in flags.items() if v != "kept" and not (first and int(k) < first[0])}, years,
                           {str(y) for y, x in zip(years, series) if x is not None and x.flag == "est-volume"})
            if first:
                hn = first[1] + (". " + hn if hn else "")
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
            drops = [r for r in LAST_DROPPED if r["group"] == group and r["year"] == y and r["rule"] == "new-pair"]
            low = [r for r in LAST_DROPPED if r["group"] == group and r["year"] == y and r["rule"] == "low-uv"]
            if low:
                parts.append(f"{len(low)} flows of {K.label(group)} ({sum(r['t'] for r in low) / 1e3:,.1f} kt) declared under {LITHIUM_MIN_UV:,} USD per tonne, the price of "
                             "ore or concentrate rather than of a lithium chemical, are left out; the cause is not established")
            if drops:
                os_ = sorted({r["o"] for r in drops})
                parts.append(f"{len(drops)} rows of {K.label(group)} from {', '.join(K._name(c) for c in os_)} ({_mt(sum(r['t'] for r in drops) / 1e6)}) "
                             "dropped: pairs with no flow in both neighbouring years, which may be LNG cargoes recorded a second time "
                             "under this code; this is not established")
            if parts:
                yn[str(y)] = ". ".join(p[0].upper() + p[1:].rstrip(".") for p in parts)
        # share of each year's seaborne tonnes that is an Atlas estimate, and a line for the years where it shows
        est_y = [round(est_tot.get((group, y), 0) / sea_tot[y], 3) if sea_tot[y] else 0 for y in years]
        if first:
            est_y = [None if y < first[0] else v for y, v in zip(years, est_y)]
        for y, share in zip(years, est_y):
            if share is None:
                continue
            e = est_tot.get((group, y), 0)
            if share >= EST_NOTE_MIN:  # on the published share, so that every year it marks has its line
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
            "s": "atlas" if group in EST_GROUP else "baci",
            **({"n": EST_GROUP[group] + (f". {first[1]}" if first else "")} if group in EST_GROUP else {}),
            "years": years,
            "seaborne": [None if first and y < first[0] else round(sea_tot[y] / div, nt) for y in years],
            # three significant digits, not two decimals: 23,849 t of DAP read "Plus 0.020 Mt" (review GNC1.9)
            "mixed": [None if first and y < first[0] else float(f"{mtot.get((group, y), 0) / div:.3g}") for y in years],
            "world": [None if first and y < first[0] else round(world.get((group, y), 0) / div, nt) for y in years],
            "yearNotes": dict(sorted(yn.items())),
            "est": round(est_t / tot_latest, 4),
            "estY": est_y,
            "coverage": {"lanes": len(main), "share": round(main_t / tot_latest, 4)},
            "rest": [{"o": o, "v": round(v / div, nd), "n": n, **({"est": float(f"{e / div:.3g}")} if e > 0 else {})}
                     for o, (v, n, e) in sorted(rest.items(), key=lambda x: -x[1][0])],
            "ports": {c: port_entry(c, ports_used[c]) for c in sorted(ports_used)},
            "lanes": lanes,
        }
        write_json(os.path.join(OUT, f"{group}.json"), doc)

        # pairs table: every recorded pair of the latest year
        pport, pcls, prow, puse, pnotes = {}, {}, [], {"load": defaultdict(set), "discharge": defaultdict(set)}, {}
        landlocked = set()  # ends of routed rows that reach the sea through a foreign port and have no coast
        lane_pairs = set(main) | set(mixed_l)
        rest_rows = []  # the overland part of the pairs that split_known cut: the row of the pair carries the part by sea
        for r in gy.itertuples(index=False):
            if r.split == "rest":
                rest_rows.append([r.o, r.d, kt(r.t)])
                continue
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
                landlocked.update(t["end"] for t in rec["trows"] if not MD.coastal(t["end"]))
                for code in (lo, di):
                    if code not in pport:
                        pport[code] = len(pport)
                puse["load"][lo].add(port_use(r.o, group, "load", lo, rec["trows"])[0])
                puse["discharge"][di].add(port_use(r.d, group, "discharge", di, rec["trows"])[0])
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
            "group": group, "k": COMMODITY.get(group, group), "y": latest, "s": "atlas" if group in EST_GROUP else "baci", "unit": "kt",
            **({"n": EST_GROUP[group]} if group in EST_GROUP else {}),
            # the unrounded seaborne sum, as the lanes file and the commodity page give it (a small group in kt, one decimal;
            # the sum of its rows, each rounded to 0.1 kt, differs from it by up to 0.4 kt: GR4D.3)
            "seaborne": round(sea_tot[latest] / 1e3, 1) if small else round(sea_tot[latest] / 1e3),
            # [code, name, country, zone, basis as a loading port, basis as a discharging port]: each basis indexes `bases`
            # and is null when no pair of the file uses the port in that role. A page can name a cargo at a port in one
            # direction only, so the two differ (the weakest is kept where several countries share the port in one role).
            "ports": [[c, P.port(c)["name"], port_iso3(c), (_meta.get(c) or P.port_meta(c)).get("zone")]
                      + [max(BASIS_RANK[b] for b in puse[role][c]) if puse[role].get(c) else None for role in ("load", "discharge")]
                      for c in pport],
            "bases": list(P.BASES),
            # the ports above that are up a river: the distance of every pair through them includes the leg (river_legs.py)
            **({"rivers": {c: RL.public(c, P.port(c)["name"]) for c, _ in sorted(pport.items(), key=lambda x: x[1]) if c in RL.RIVER_LEGS}}
               if any(c in RL.RIVER_LEGS for c in pport) else {}),
            "classes": list(pcls),
            "gates": gates,
            "cols": ["o", "d", "kt", "m", "load", "dis", "nm", "cls", "via", "alt", "f"],
            "rows": prow,
            # a pair whose split by mode is known has its row for the part by sea; the rest of its tonnage went overland (the file's country pages count it so)
            **({"rest": rest_rows} if rest_rows else {}),
            "notes": pnotes,
            # the ends above with no coast at all; another end whose port lies in a third country has a coast (DR Congo)
            "landlocked": sorted(landlocked),
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
