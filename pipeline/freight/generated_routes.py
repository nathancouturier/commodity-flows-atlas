"""
Generated corridor routes: named routes for the seaborne corridors that no hand-written route covers.

    build_freight.py calls generate(); nothing here reads or writes a file.

The routes of routes_def.json are written by hand and cover about 45% of the 2024 seaborne tonnes. For the rest, the
pairs table of build_lanes.py (every recorded seaborne pair, with its typical ports, class, distance and passages)
is grouped into corridors, one per customs group, exporting freight zone and importing zone, and the largest corridors
that no hand-written corridor covers become routes (METHODOLOGY.md, section 3, "Generated corridors").

A generated route is the atlas's own corridor, never a market benchmark: its source is "atlas", its id starts with
"gen-", and it carries `generated: true`. Its ports, class, distance and passages are those of the largest pair of its
corridor, as the Route finder reads them (build_freight.py plans the route with the same call as build_lanes.py).
"""
import math
import re
from collections import defaultdict

# Share of a group's seaborne tonnes that named routes should reach. Corridors are added, largest first, until a
# group reaches it, runs out of corridors above the floor, or reaches GROUP_CAP routes.
TARGET = 0.70
# A corridor needs this many Mt of tonnes that no hand-written route names, and this share of its group's seaborne tonnes:
# below that it is a thin trade, not a route (the smaller groups would otherwise get dozens of lines of 0.1 Mt).
FLOOR_MT, FLOOR_SHARE = 0.5, 0.02
# ... and at least this share of its own tonnes must be outside the hand-written corridors (else it is already named).
MIN_NEW_SHARE = 0.5
GROUP_CAP = 12
# Cap on the generated routes of the whole atlas: the map draws every route, so the count has to stay readable. When the
# per-group lists exceed it, the lower-ranked corridors of the groups with the most routes are left out first (the
# first corridor of every group, then the second of every group, and so on).
TOTAL_CAP = 120

# Importing end seen at a coarser level when no zone-to-zone corridor holds the tonnes: a region is a set of freight zones
# (an Atlas grouping, listed here with the name each region takes in a route name).
REGIONS = {
    "north-america": ("North America", ["us-gulf", "us-atlantic", "us-pnw", "us-west", "canada-east", "canada-west"]),
    "central-america": ("Central America and the Caribbean", ["mexico-gulf", "mexico-pacific", "cam-caribbean", "cam-pacific", "caribbean"]),
    "south-america": ("South America", ["ecsa", "wcsa"]),
    "europe": ("Europe", ["nw-europe", "baltic", "med", "black-sea", "arctic-russia"]),
    "middle-east": ("Middle East", ["meg", "gulf-of-oman", "red-sea"]),
    "south-asia": ("South Asia", ["wc-india", "ec-india"]),
    "east-asia": ("East Asia", ["n-china", "e-china", "s-china", "japan-korea", "taiwan", "russia-far-east"]),
    "south-east-asia": ("South-East Asia", ["sea"]),
    "australia": ("Australia", ["w-australia", "e-australia", "n-australia"]),
    "africa": ("Africa", ["waf", "s-africa", "e-africa"]),
}
REGION_OF = {z: r for r, (_, zs) in REGIONS.items() for z in zs}
# zone names of zones.json that are too long for a route name
ZONE_NAME = {"gulf-of-oman": "Gulf of Oman", "us-pnw": "US Pacific Northwest"}
# zones and regions a route name puts "the" before ("Corn: Black Sea to the Mediterranean")
THE = {"med", "baltic", "black-sea", "red-sea", "gulf-of-oman", "us-pnw", "caribbean", "r:middle-east"}
# the cargo as a route name says it, where the group's own label does not
CARGO_NAME = {"coal": "Coal", "nickel-fe": "Ferro-nickel and NPI", "copper-ore": "Copper concentrate", "copper-refined": "Refined copper",
              "nickel-int": "Nickel intermediates", "zinc-ore": "Zinc concentrate", "soymeal": "Soybean meal", "soyoil": "Soybean oil"}


def _hav_km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def zone_lookup(ports_by_group, at):
    """port code -> zone id. A port with no zone in the pairs files (its page was read for a role no gateway row of the
    atlas names) takes the zone of the nearest port with one, preferring the same country: only the name of the corridor
    depends on it, never a route, a distance or a share. `at(code)` gives [lon, lat]."""
    info = {}
    for ports in ports_by_group.values():
        for code, _name, iso, zone, *_ in ports:
            if zone or code not in info:
                info[code] = (iso, zone)
    zoned = sorted((c, v) for c, v in info.items() if v[1])
    cache = {}

    def zone(code):
        if code not in cache:
            iso, z = info[code]
            if not z:
                here = at(code)
                z = min(zoned, key=lambda cv: (cv[1][0] != iso, _hav_km(here, at(cv[0])), cv[0]))[1][1]
            cache[code] = z
        return cache[code]
    return zone


def _short(name):
    """A zone name of zones.json without its parenthesis ("North-West Europe (Skaw to Brest)")."""
    return re.sub(r"\s*\(.*\)$", "", name)


def zone_names(zones):
    return {z["id"]: ZONE_NAME.get(z["id"]) or _short(z["name"]) for z in zones}


def _candidates(rows, level, zone_of):
    """Cells of one level: {(exporting zone, importing zone or region): [pair rows]}."""
    cells = defaultdict(list)
    for r in rows:
        a, b = zone_of(r["a"]), zone_of(r["b"])
        cells[(a, b if level == 0 else "r:" + REGION_OF.get(b, b))].append(r)
    return cells


def select_group(group, p, ports, covered, zone, target=TARGET):
    """Corridors of one group, in the order they are chosen: [{level, a, b, rows, t, new}]. `p` is the decoded pairs file,
    `ports` its port table, `covered` {(group, o, d): [route ids]} of the hand-written routes. Only routed seaborne pairs
    take part: a pair with no gateway, or no sea route, has no ports to draw."""
    sea = p["seaborne"]
    rows, named = [], 0.0
    for r in p["rows"]:
        if r["m"] not in (0, 1):
            continue
        if (group, r["o"], r["d"]) in covered:
            named += r["t"]
        if r["load"] >= 0 and r["dis"] >= 0 and r["nm"] > 0 and r["cls"]:
            rows.append(dict(r, a=ports[r["load"]][0], b=ports[r["dis"]][0], new=(group, r["o"], r["d"]) not in covered))
    floor = max(FLOOR_MT, FLOOR_SHARE * sea)
    chosen, taken = [], set()
    reached = named
    for level in (0, 1):
        left = [r for r in rows if id(r) not in taken]
        cells = _candidates(left, level, zone)
        ranked = sorted(cells.items(), key=lambda kv: (-sum(r["t"] for r in kv[1] if r["new"]), kv[0]))
        for (a, b), rs in ranked:
            if reached >= target * sea or len(chosen) >= GROUP_CAP:
                return chosen
            tot, new = sum(r["t"] for r in rs), sum(r["t"] for r in rs if r["new"])
            if new < floor or new < MIN_NEW_SHARE * tot:
                continue
            chosen.append({"level": level, "a": a, "b": b, "rows": rs, "t": tot, "new": new})
            taken.update(id(r) for r in rs)
            reached += new
    return chosen


def _corridor(k, group, rows):
    """The `corridor` field of a route: one entry per exporter, exporters with the same buyers sharing an entry. The
    entries name exactly the pairs of the generated corridor (no pair of another generated corridor is in their
    product), so the shares and the history are those of these pairs."""
    by_o = defaultdict(set)
    for r in rows:
        by_o[r["o"]].add(r["d"])
    by_d = defaultdict(list)
    for o, ds in by_o.items():
        by_d[tuple(sorted(ds))].append(o)
    return [{"k": k, "g": group, "o": sorted(os), "d": list(ds)} for ds, os in sorted(by_d.items(), key=lambda x: (x[1], x[0]))]


def _mt(v):
    return f"{v:,.0f} Mt" if v >= 10 else f"{v:.1f} Mt" if v >= 1 else f"{v:.2f} Mt"


def _note(p, c, big, a_label, b_label, what, hand_ids, route_names, ports, country):
    """How the route was derived, from which customs year, and what a hand-written route already covers of it."""
    sea = p["seaborne"]
    n = (f"Atlas corridor, generated from customs pairs: the {len(c['rows'])} recorded seaborne {what} pairs whose typical ports lie in "
         f"{a_label} (loading) and {b_label} (discharge), {p['y']}: {_mt(c['t'])}, {100 * c['t'] / sea:.1f}% of the {_mt(sea)} of seaborne "
         f"{what} trade (CEPII BACI customs data)")
    if c["level"] == 1:
        n += f". The discharge zones are the zones of this region that no zone-to-zone corridor from {a_label} already holds"
    n += (f". Ports, vessel class, distance and passages are those of its largest pair, {country(big['o'])} to {country(big['d'])} "
          f"({_mt(big['t'])}): {ports[big['load']][1]} to {ports[big['dis']][1]}, as the Route finder gives them. The ports are the atlas's "
          "typical ports (an assumption): the route stands for the corridor, not for each of its pairs")
    if hand_ids:
        top = sorted(hand_ids.items(), key=lambda x: (-x[1], x[0]))[:3]
        n += ". A hand-written route already covers part of it: " + "; ".join(f"{route_names.get(i, i)} ({_mt(t)})" for i, t in top)
    return n


def generate(pairs, ports_by_group, hand, zones, at, cargo_label, route_names, country, target=TARGET, total_cap=TOTAL_CAP):
    """Route definitions of the generated corridors, and a report.

    pairs: decoded pairs files (build_freight.load_pairs, with `ports`); hand: {(group, o, d): [route ids]} of the
    hand-written routes still running; zones: zones.json; at(code): [lon, lat] of a port; cargo_label(group): (name for a route
    name, noun for a sentence) of the cargo; country(iso3): its name; route_names: {route id: name} of the hand-written
    routes. Returns (defs, report). A def holds the fields of a routes_def.json entry plus `generated`, `_ports` (load and
    discharge port of the largest pair), `_pair` (group, exporter, importer, Mt of that pair) and `_nm` (its distance);
    build_freight.py plans and measures it like any other route. The report gives, for each group, its seaborne
    Mt, the share named by the hand-written routes, the share after the generated routes, and the reason when the target
    is not reached."""
    names = zone_names(zones)
    zone = zone_lookup(ports_by_group, at)
    per_group = {}
    for g in sorted(pairs):
        per_group[g] = select_group(g, pairs[g], ports_by_group[g], hand, zone, target)
    # the cap on the whole atlas: the corridors ranked first within their group are kept first
    order = sorted(((i, g) for g, cs in per_group.items() for i in range(len(cs))), key=lambda x: (x[0], -per_group[x[1]][x[0]]["new"] / pairs[x[1]]["seaborne"], x[1]))
    kept = {(g, i) for i, g in order[:total_cap]}
    defs, report = [], {}
    for g in sorted(pairs):
        p = pairs[g]
        sea = p["seaborne"]
        named = sum(r["t"] for r in p["rows"] if r["m"] in (0, 1) and (g, r["o"], r["d"]) in hand)
        union = {(r["o"], r["d"]) for r in p["rows"] if r["m"] in (0, 1) and (g, r["o"], r["d"]) in hand}
        got, cut = 0, 0
        for i, c in enumerate(per_group[g]):
            if (g, i) not in kept:
                cut += 1
                continue
            got += 1
            for r in c["rows"]:
                union.add((r["o"], r["d"]))
            big = max((r for r in c["rows"]), key=lambda r: (r["t"], r["o"], r["d"]))
            to_zone = c["b"]
            a_label = names[c["a"]]
            the = lambda key, label: ("the " + label) if key in THE else label  # noqa: E731
            if to_zone.startswith("r:"):
                to_zones = {zone(r["b"]) for r in c["rows"]}
                region = REGIONS[to_zone[2:]][0] if to_zone[2:] in REGIONS else names[to_zone[2:]]
                one = len(to_zones) == 1
                b_zone_label = names[next(iter(to_zones))] if one else region
                # a region that holds the exporting zone: the buyers are its other zones
                b_name = f"the rest of {the(to_zone, region)}" if REGION_OF.get(c["a"], c["a"]) == to_zone[2:] and not one else the(next(iter(to_zones)) if one else to_zone, b_zone_label)
            else:
                b_zone_label = names[to_zone]
                b_name = the(to_zone, b_zone_label)
            cargo, what = cargo_label(g)
            name = f"{cargo} within {the(c['a'], a_label)}" if a_label == b_zone_label else f"{cargo}: {the(c['a'], a_label)} to {b_name}"
            ids = f"gen-{g}-{c['a']}-{to_zone.replace('r:', 'r-')}"
            hand_ids = defaultdict(float)
            for r in c["rows"]:
                for rid in hand.get((g, r["o"], r["d"]), []):
                    hand_ids[rid] += r["t"]
            defs.append({
                "id": ids, "name": name, "benchmark": False, "generated": True, "vclass": big["cls"], "cargoes": [p["k"]],
                "from": {"region": a_label, "ports": [{"name": ports_by_group[g][big["load"]][1], "c": ports_by_group[g][big["load"]][2]}]},
                "to": {"region": b_zone_label, "ports": [{"name": ports_by_group[g][big["dis"]][1], "c": ports_by_group[g][big["dis"]][2]}]},
                "corridor": _corridor(p["k"], g, c["rows"]), "s": "atlas",
                "notes": _note(p, c, big, a_label, b_name, what, hand_ids, route_names, ports_by_group[g], country),
                "_ports": (big["a"], big["b"]), "_pair": (g, big["o"], big["d"], big["t"]), "_nm": big["nm"],
            })
        tonnes = sum(r["t"] for r in p["rows"] if r["m"] in (0, 1) and (r["o"], r["d"]) in union)
        why = None
        if tonnes < target * sea:
            if cut:
                why = f"the cap of {total_cap} generated routes left out {cut} corridor{'s' if cut > 1 else ''}"
            elif got >= GROUP_CAP:
                why = f"the cap of {GROUP_CAP} routes per group was reached"
            else:
                why = (f"the remaining corridors are each under {max(FLOOR_MT, FLOOR_SHARE * sea):.1f} Mt, or mostly named by "
                       "hand-written routes, or have no routed port")
        report[g] = {"seaborne": sea, "handShare": 100 * named / sea, "share": 100 * tonnes / sea, "generated": got, "why": why}
    return defs, report
