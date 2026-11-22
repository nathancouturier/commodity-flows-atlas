"""
Sea routing of the trade-flow engine: gates, crossing detection, a tagged searoute network and the routing
policy (METHODOLOGY.md, section 3).

- A gate is a short line drawn across a strait, canal or cape, both ends on land. The same lines detect a
  crossing (`crossings()`) and forbid a passage (`route(a, b, avoid)`).
- `plan(a, b, classes)` applies the routing policy for one load and one discharge port and the lane's vessel
  classes: regions always avoided, the Cape Horn rule, canal limits and draught limits of the primary class,
  the Cape preference of the largest classes, the parallel passages (`via` / `viaAlt`) and the alternatives
  shown to the reader.
- Caches written from these results carry a version key `_v` (`load_cache()` / `save_cache()`): a cache built
  with other gates, thresholds, draught tables, speeds, rule code or another searoute release is discarded at load.

Every rule here is an Atlas assumption, documented in METHODOLOGY.md. Longitudes are in -180..180; searoute
returns lines whose longitudes run on past 180, and `crossings()` accepts either form.
"""
import hashlib
import inspect
import json
import os
import warnings
from collections import namedtuple

import searoute as sr
from searoute.searoute import setup_M
from shapely.geometry import LineString

import vessel_rules as VR

# id -> segment [(lon, lat), (lon, lat)]. The two cape gates sit 0.03 degree off 20 E and 69 W because the
# network has nodes exactly on those meridians, and a route through such a node must not be missed.
GATES = {
    "hormuz": [(56.45, 26.15), (56.45, 27.25)],
    "bab-el-mandeb": [(42.9, 12.6), (43.75, 12.6)],
    "suez": [(31.9, 30.5), (32.8, 30.5)],
    "malacca": [(99.9, 2.0), (101.7, 3.3)],
    "singapore": [(103.85, 0.9), (103.85, 1.33)],
    "sunda": [(105.3, -5.95), (106.2, -5.95)],
    "lombok": [(115.5, -8.7), (116.15, -8.7)],
    "makassar": [(116.3, -2.0), (119.5, -2.0)],
    "panama": [(-80.2, 9.1), (-79.3, 9.1)],
    "gibraltar": [(-5.6, 35.7), (-5.6, 36.2)],
    "bosphorus": [(28.8, 41.1), (29.3, 41.1)],
    "danish-straits": [(9.3, 55.5), (13.4, 55.5)],
    "dover": [(1.2, 51.2), (1.95, 50.85)],
    "cape-good-hope": [(20.03, -34.7), (20.03, -60.0)],     # any passage of 20.03 E south of Africa
    "cape-horn": [(-69.03, -52.0), (-69.03, -66.0)],        # includes the Strait of Magellan
    "taiwan-strait": [(118.0, 24.5), (120.7, 24.5)],
    "luzon": [(120.85, 21.95), (121.4, 18.5)],
    "korea-strait": [(128.9, 35.2), (130.5, 33.5)],
    "ombai": [(124.5, -8.2), (125.2, -9.1)],
    "torres": [(142.2, -9.2), (142.2, -10.8)],
}

# Near substitutes that customs data cannot tell apart: a member is a set of gates crossed together.
PARALLEL = [
    [frozenset({"sunda"}), frozenset({"malacca", "singapore"}), frozenset({"lombok", "makassar"})],
    [frozenset({"taiwan-strait"}), frozenset({"luzon"})],
]
PARALLEL_PCT, PARALLEL_NM = 0.05, 300

# The network has a lane along 50 S that no cargo ship uses between South America and Asia: every edge with
# a point south of 42 S between 55 W and 140 E is always forbidden.
SOUTHERN_OCEAN = {"lat": -42.0, "lon": (-55.0, 140.0)}
ALWAYS_AVOID = ("southern-ocean",)

# Network edges that no ocean-going ship can sail, closed in every route (not gates: never in `via`). The
# network runs through the Johor Strait, which the Johor-Singapore Causeway (about 103.77 E) blocks; through it
# a route would leave Singapore without crossing the Singapore gate.
CLOSED = {"johor-causeway": [(103.77, 1.40), (103.77, 1.52)]}

# Cape Horn rule. The Indo-Pacific side is east of 20 E, outside the Mediterranean, the Black Sea and the Baltic
# (north of 30 N and west of 45 E). From its Indian Ocean and Asian part a ship bound for the Atlantic goes round
# the Cape of Good Hope. Its South Pacific part (south of the equator and east of 140 E, where SOUTHERN_OCEAN
# ends: eastern Australia, New Zealand, the Pacific islands) may use Cape Horn or the Strait of Magellan.
INDO_PACIFIC = {"east_of": 20.0, "inland_seas": {"north_of": 30.0, "west_of": 45.0}}
SOUTH_PACIFIC = {"south_of": 0.0, "east_of": SOUTHERN_OCEAN["lon"][1]}

# Inside the cape-horn gate, Tierra del Fuego parts the Strait of Magellan (north) from the passages round Cape
# Horn (south); at 69.03 W the island spans about 52.7 S to 54.9 S. An alternative is named by where it crosses.
MAGELLAN_SOUTH_OF = -54.0

# Laden transit limits (Panama Canal Authority: Neopanamax 51.25 m beam / 15.24 m draft; Suez Canal
# Authority: 20.1 m draft). Same lists as build_lanes.py.
NO_PANAMA = {"vloc", "capesize", "newcastlemax", "vlcc", "suezmax"}
NO_SUEZ = {"vloc", "vlcc"}
# Classes that take the Cape of Good Hope instead of Suez when it costs this many extra days or fewer.
CAPE_PREFERRED = {"vloc", "capesize", "newcastlemax", "vlcc"}
CAPE_MAX_EXTRA_DAYS = 4

# An alternative more than this many times as long as the main route is not published.
ALT_MAX_RATIO = 3.0

NAMES = {"suez": "Suez Canal", "bab-el-mandeb": "Bab el-Mandeb", "panama": "Panama Canal"}
RED_SEA = {"suez", "bab-el-mandeb"}

Route = namedtuple("Route", "coords nm via")
Plan = namedtuple("Plan", "main via via_alt parallel alts alt_note classes avoid")


# ------------------------------------------------------------------ geometry and crossings
def norm(x):
    return ((x + 180.0) % 360.0) - 180.0


def _ccw(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])


def seg_cross(p, q, a, b):
    """Half-open test: a point exactly on a line counts on the non-positive side, so a route vertex that
    sits on a gate is counted once and never missed."""
    d1, d2, d3, d4 = _ccw(p, q, a), _ccw(p, q, b), _ccw(a, b, p), _ccw(a, b, q)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _frame(p, q):
    """Both points of a segment in one longitude frame, the first one in -180..180."""
    x1, y1, x2, y2 = norm(p[0]), p[1], norm(q[0]), q[1]
    if x2 - x1 > 180:
        x2 -= 360
    elif x2 - x1 < -180:
        x2 += 360
    return (x1, y1), (x2, y2)


def gates_crossed(p, q, gates=None):
    p, q = _frame(p, q)
    return [gid for gid, (a, b) in (gates or GATES).items()
            if any(seg_cross(p, q, (a[0] + sh, a[1]), (b[0] + sh, b[1])) for sh in (0, 360, -360))]


def crossings(coords):
    """Gate ids crossed by a line, in order of first crossing. A gate crossed an even number of times (a line
    that touches it and turns back) has not been passed."""
    n, first = {}, {}
    for i in range(len(coords) - 1):
        for g in gates_crossed(coords[i], coords[i + 1]):
            n[g] = n.get(g, 0) + 1
            first.setdefault(g, i)
    return [g for g in sorted(first, key=first.get) if n[g] % 2 == 1]


def horn_passage(coords):
    """"Magellan Strait" or "Cape Horn": the passage by which a line first crosses the cape-horn gate (None
    when it does not)."""
    (ax, _), _ = GATES["cape-horn"]
    for i in range(len(coords) - 1):
        if "cape-horn" in gates_crossed(coords[i], coords[i + 1]):
            (x1, y1), (x2, y2) = _frame(coords[i], coords[i + 1])
            gx = min((ax + sh for sh in (0, 360, -360)), key=lambda g: abs(g - (x1 + x2) / 2))
            y = y1 + (y2 - y1) * (gx - x1) / (x2 - x1) if x2 != x1 else y1
            return "Magellan Strait" if y > MAGELLAN_SOUTH_OF else "Cape Horn"
    return None


def southern_ocean(u, v):
    lo, hi = SOUTHERN_OCEAN["lon"]
    return min(u[1], v[1]) < SOUTHERN_OCEAN["lat"] and (lo < norm(u[0]) < hi or lo < norm(v[0]) < hi)


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


def line(coords):
    """Published form of a route line: simplified, rounded, longitudes continuous (as build_lanes.py)."""
    ls = LineString(coords).simplify(0.05, preserve_topology=False)
    return unwrap([[round(x, 2), round(y, 2)] for x, y in ls.coords])


# ------------------------------------------------------------------ tagged network
_M = None
_EDGES = {}      # gate or region id -> attribute dictionaries of the directed edges that cross it


def graph():
    """The searoute network with every directed edge tagged with the gates it crosses (once per process).

    The package keeps one attribute dictionary per direction of an edge, so both are tagged: going through
    M.edges() would tag one direction only and a search could walk the "forbidden" edge from the other side.
    The edges across a CLOSED line get the passage "atlas-closed", which route() always restricts.
    """
    global _M
    if _M is None:
        M = setup_M()
        for u, nbrs in M.adj.items():
            for v, data in nbrs.items():
                if gates_crossed(u, v, CLOSED):
                    data["passage"] = "atlas-closed"
                gs = set(gates_crossed(u, v))
                if southern_ocean(u, v):
                    gs.add("southern-ocean")
                if gs:
                    data["gates"] = gs
                    for g in gs:
                        _EDGES.setdefault(g, []).append(data)
        _M = M
    return _M


def gate_edge_counts():
    graph()
    return {g: len(v) for g, v in _EDGES.items()}


def nodes_on_gates(M=None):
    """Network nodes lying exactly on a gate (there must be none: the crossing test is half-open)."""
    M = M or graph()
    out = []
    for u in M.adj:
        x, y = norm(u[0]), u[1]
        for gid, (a, b) in GATES.items():
            if abs(_ccw(a, b, (x, y))) < 1e-12 and min(a[0], b[0]) <= x <= max(a[0], b[0]) \
                    and min(a[1], b[1]) <= y <= max(a[1], b[1]):
                out.append((gid, u))
    return out


_routes = {}


def route(a, b, avoid=()):
    """Shortest sea route from a to b ([lon, lat]) that crosses none of the gates or regions in `avoid`.

    Returns Route(coords, nm, via) with the raw searoute line, or None (silently) when no such route exists.
    """
    avoid = frozenset(avoid)
    k = (round(a[0], 4), round(a[1], 4), round(b[0], 4), round(b[1], 4), avoid)
    if k in _routes:
        return _routes[k]
    M = graph()
    touched = []
    for g in avoid:
        for data in _EDGES.get(g, ()):
            touched.append((data, data.get("passage")))
            data["passage"] = "atlas-avoid"
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = sr.searoute(list(a), list(b), units="naut", restrictions=["northwest", "atlas-avoid", "atlas-closed"],
                            M=M)
    finally:
        for data, old in reversed(touched):
            if old is None:
                data.pop("passage", None)
            else:
                data["passage"] = old
    c = r["geometry"]["coordinates"]
    out = None
    if len(c) >= 2:
        out = Route(c, round(r["properties"]["length"]), crossings(c))
    _routes[k] = out
    return out


# ------------------------------------------------------------------ policy
def indo_pacific(pt):
    """Indian Ocean, Asia and Oceania side: east of 20 E, except the Mediterranean, the Black Sea and the Baltic."""
    x, y = norm(pt[0]), pt[1]
    x = 180.0 if x == -180.0 else x
    inland = INDO_PACIFIC["inland_seas"]
    return INDO_PACIFIC["east_of"] < x <= 180 and not (y > inland["north_of"] and x < inland["west_of"])


def south_pacific(pt):
    """South Pacific part of the Indo-Pacific side: south of the equator and east of 140 E."""
    x, y = norm(pt[0]), pt[1]
    x = 180.0 if x == -180.0 else x
    return indo_pacific(pt) and y < SOUTH_PACIFIC["south_of"] and x > SOUTH_PACIFIC["east_of"]


def horn_allowed(a, b):
    """Cape Horn (or Magellan) is a route unless a port is on the Indian Ocean or Asian part of the Indo-Pacific side."""
    return all(not indo_pacific(p) or south_pacific(p) for p in (a, b))


def _first(a, b, order):
    """Route under the restrictions in `order`; when none exists, drop the last restriction added, and so on."""
    for k in range(len(order), -1, -1):
        r = route(a, b, order[:k])
        if r:
            return r, set(order[:k])
    return None, set()


def _options(a, b, avoid, group):
    """Best route through each member of a parallel group, by forbidding the members found one after the
    other. Returns [(sorted gates of the group that the route crosses, nm), ...] in the order found: every gate
    of the group, so that a gate crossed by every option (Makassar from a port inside that strait) is seen."""
    out, extra = [], set()
    members = set().union(*group)
    r = route(a, b, avoid)
    while r:
        used = [m for m in group if m & set(r.via) and not m & extra]
        if not used:
            break
        out.append((sorted(members & set(r.via)), r.nm))
        extra |= used[0]
        r = route(a, b, avoid | extra)
    return out


def classify(main_via, parallel, classes, pct=PARALLEL_PCT, nmx=PARALLEL_NM):
    """Split the passages of a route into `via` (crossed whatever the parallel choice) and `viaAlt` (lists of
    passages of which one is used). For each class, the members it may use under the draught rule and whose
    distance is within `pct` or `nmx` nm of its best one are kept; a gate crossed by every option kept is certain."""
    drop, certain, via_alt = set(), [], []
    for gi, opts in parallel:
        if not opts:
            continue
        keep = set()
        for c in classes:
            av = VR.avoids(c)
            ok = [(tuple(m), nm) for m, nm in opts if not set(m) & av] or [(tuple(m), nm) for m, nm in opts]
            best = min(nm for _, nm in ok)
            keep |= {m for m, nm in ok if nm <= best * (1 + pct) or nm <= best + nmx}
        drop |= set().union(*PARALLEL[gi])
        common = set.intersection(*(set(m) for m in keep))
        certain += sorted(common)
        if len(keep) > 1:
            lst = []
            for m, _ in sorted(opts, key=lambda o: o[1]):
                if tuple(m) in keep:
                    lst += [g for g in m if g not in common and g not in lst]
            via_alt.append(lst)
    via = [g for g in main_via if g not in drop or g in certain]
    via += [g for g in certain if g not in via]
    return via, via_alt


def _alt(label, avoids, main, r, spd):
    a = {"label": label, "avoids": avoids, "via": r.via, "distanceNm": r.nm,
         "extraDays": round((r.nm - main.nm) / (spd * 24), 1), "g": line(r.coords)}
    if RED_SEA & set(r.via):
        a["redSea"] = True     # the builder attaches the Red Sea status note
    return a


def _label(avoided, r):
    names = [NAMES[g] for g in avoided]
    s = "Avoiding " + (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1])
    if "cape-good-hope" in r.via:
        return s + " (via Cape of Good Hope)"
    if "cape-horn" in r.via:
        return s + f" (via {horn_passage(r.coords)})"
    if "suez" in r.via:
        return s + " (via Suez Canal)"
    return s


def plan(a, b, classes, speed_kn=None):
    """Routing policy for one load port a and one discharge port b ([lon, lat]) and the lane's classes, primary
    first. Returns Plan(main, via, via_alt, parallel, alts, alt_note, classes, avoid), or None without a route.

    main      Route of the primary class (raw line, nm, every gate crossed)
    via       passages every option has to cross; via_alt: lists of passages of which one is used
    parallel  [(index in PARALLEL, [(member gates, nm), ...]), ...]: the option distances, for classify()
    alts      alternatives shown to the reader, first one the former `alt`; alt_note: why none is shown
    """
    classes = list(classes) or ["supramax"]
    primary = classes[0]
    spd = speed_kn or VR.speed(primary)
    order = list(ALWAYS_AVOID)
    if not horn_allowed(a, b):
        order.append("cape-horn")
    if primary in NO_PANAMA:
        order.append("panama")
    if primary in NO_SUEZ:
        order.append("suez")
    order += sorted(VR.avoids(primary) - set(order))
    main, avoid = _first(a, b, order)
    if main is None:
        return None

    alts, alt_note, dropped = [], None, []
    if RED_SEA & set(main.via):
        cape = route(a, b, avoid | RED_SEA | {"panama"})
        if cape and primary in CAPE_PREFERRED and (cape.nm - main.nm) / (spd * 24) <= CAPE_MAX_EXTRA_DAYS:
            suez, main, avoid = main, cape, avoid | RED_SEA | {"panama"}
            alts.append(_alt("Via Suez Canal (shorter, subject to tolls and Red Sea security)", [], main, suez, spd))
        elif cape:
            avoided = [g for g in ("suez", "bab-el-mandeb") if g in main.via]
            alts.append(_alt(_label(avoided, cape), avoided, main, cape, spd))
    elif "panama" in main.via:
        r1 = route(a, b, avoid | {"panama"})
        if r1:
            alts.append(_alt(_label(["panama"], r1), ["panama"], main, r1, spd))
            if RED_SEA & set(r1.via):
                r2 = route(a, b, avoid | {"panama"} | RED_SEA)
                if r2:
                    avoided = ["panama"] + [g for g in ("suez", "bab-el-mandeb") if g in r1.via]
                    alts.append(_alt(_label(avoided, r2), avoided, main, r2, spd))
    for x in list(alts):
        if x["distanceNm"] > ALT_MAX_RATIO * main.nm:
            alts.remove(x)
            dropped.append(x)
    if dropped and not alts:
        names = [NAMES[g] for g in dropped[0]["avoids"]]
        what = "the " + " and the ".join(names)
        alt_note = f"No practical sea alternative: the route avoiding {what} is more than three times as long"

    parallel = []
    for gi, group in enumerate(PARALLEL):
        members = set().union(*group)
        if members & set(main.via):
            # in-group draught limits are left to classify(), per class
            parallel.append((gi, _options(a, b, avoid - members, group)))
    via, via_alt = classify(main.via, parallel, classes)
    return Plan(main, via, via_alt, parallel, alts, alt_note, classes, tuple(sorted(avoid)))


def summary(p, geometry=False):
    """JSON form of a plan, for the caches (no geometry unless asked)."""
    alts = [{k: v for k, v in x.items() if geometry or k != "g"} for x in p.alts]
    out = {"nm": p.main.nm, "route": p.main.via, "via": p.via, "viaAlt": p.via_alt,
           "par": [[gi, opts] for gi, opts in p.parallel], "alts": alts, "altNote": p.alt_note}
    if geometry:
        out["g"] = line(p.main.coords)
    return out


# ------------------------------------------------------------------ caches
def _code():
    """The rules written as code: this module's source and the vessel_rules functions that plan() calls."""
    with open(os.path.abspath(__file__), "rb") as f:
        src = f.read()
    for fn in (VR.avoids, VR.speed):
        src += inspect.getsource(fn).encode()
    return hashlib.sha1(src).hexdigest()


def version():
    """Hash of everything a cached route or plan depends on: the tables, the speeds, the searoute release and the
    code of the rules (any edit of this module discards the caches)."""
    key = {
        "gates": GATES, "parallel": [[sorted(m) for m in g] for g in PARALLEL], "pct": PARALLEL_PCT,
        "nm": PARALLEL_NM, "so": SOUTHERN_OCEAN, "always": ALWAYS_AVOID, "closed": CLOSED,
        "indo": INDO_PACIFIC, "south_pacific": SOUTH_PACIFIC, "magellan": MAGELLAN_SOUTH_OF,
        "no_panama": sorted(NO_PANAMA), "no_suez": sorted(NO_SUEZ), "cape": sorted(CAPE_PREFERRED),
        "cape_days": CAPE_MAX_EXTRA_DAYS, "ratio": ALT_MAX_RATIO, "draught": VR.DRAUGHT_M,
        "limits": VR.PASSAGE_LIMIT_M, "speed": VR.SPEED, "searoute": sr.__version__, "code": _code(),
    }
    return hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()[:12]


VERSION = version()


def cache_key(a, b, *parts):
    return f"{a[0]:.2f},{a[1]:.2f}|{b[0]:.2f},{b[1]:.2f}|" + "|".join(str(p) for p in parts)


def load_cache(path):
    """Cache dictionary of a file, or an empty one when the file is missing, unreadable or of another version."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("_v") == VERSION:
            return data
    except (OSError, ValueError):
        pass
    return {"_v": VERSION}


def save_cache(path, data):
    data["_v"] = VERSION
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, path)
