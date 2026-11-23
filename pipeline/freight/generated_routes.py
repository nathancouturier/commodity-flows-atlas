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

import routing

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
# per-group lists exceed it, the first corridor of each group of AUDIT_GROUPS is kept first, then the corridors are taken
# by their tonnes across groups (each group's in its own order), so that no corridor is left out for a smaller one of
# another group (review GL1.8: three corridors of 1.1 to 1.5 Mt had given way to corridors of 0.5 Mt of small groups).
TOTAL_CAP = 120
# The groups that the audit's entries on named routes name (M-030: crude oil, iron ore, coal, refined products, LNG, steel,
# sugar, rice, manganese, alumina, rapeseed; M-031: sugar, rice, rapeseed, coffee, cocoa, cotton, phosphate rock, DAP, urea,
# soybean meal, palm oil, corn, wheat, potash, soybeans).
AUDIT_GROUPS = frozenset({"crude-oil", "iron-ore", "coal", "refined-products", "lng", "steel", "manganese", "alumina", "sugar", "rice",
                          "rapeseed", "coffee", "cocoa", "cotton", "phosphate-rock", "dap", "urea", "soymeal", "palm-oil", "corn",
                          "wheat", "potash", "soybeans"})

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
# When one country holds at least this share of the tonnes of an end of a corridor (counted by the customs country of its
# pairs), the route name says that country instead of the zone: "West Africa" would send a reader to Nigeria or Ghana for
# cargo that loads in Morocco. A zone whose own name already says the country (ZONE_SAYS) keeps its name, which also
# says the coast ("Eastern Australia", "US Gulf").
COUNTRY_SHARE = 0.8
ZONE_SAYS = {**{z: {"USA"} for z in ("us-gulf", "us-atlantic", "us-pnw", "us-west")},
             **{z: {"CAN"} for z in ("canada-east", "canada-west")},
             **{z: {"MEX"} for z in ("mexico-gulf", "mexico-pacific")},
             **{z: {"AUS"} for z in ("w-australia", "e-australia", "n-australia")},
             **{z: {"CHN"} for z in ("n-china", "e-china", "s-china")},
             "taiwan": {"TWN"}, "russia-far-east": {"RUS"}, "arctic-russia": {"RUS"}, "japan-korea": {"JPN", "KOR"}}
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


def _end(rows, side, ports):
    """(country, share) of the country that holds the most tonnes at one end ("load" or "dis") of a corridor: the customs
    country of each pair (exporter or importer), not the country of its typical port, which is another country for a
    landlocked end (DR Congo's cobalt loads at Dar es Salaam, review GL1.8)."""
    t = defaultdict(float)
    for r in rows:
        t[r["o"] if side == "load" else r["d"]] += r["t"]
    iso = max(sorted(t), key=lambda c: t[c])
    return iso, t[iso] / sum(t.values())


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


def _note(p, c, big, a_label, b_label, what, hand_ids, route_names, ports, country, named):
    """How the route was derived, from which customs year, and what a hand-written route already covers of it. `named` lists
    the ends whose country names the route: (end, country, share)."""
    sea = p["seaborne"]
    n = (f"Atlas corridor, generated from customs pairs: the {len(c['rows'])} recorded seaborne {what} pairs whose typical ports lie in "
         f"{a_label} (loading) and {b_label} (discharge), {p['y']}: {_mt(c['t'])}, {100 * c['t'] / sea:.1f}% of the {_mt(sea)} of seaborne "
         f"{what} trade (CEPII BACI customs data)")
    if c["level"] == 1:
        n += f". The discharge zones are the zones of this region that no zone-to-zone corridor from {a_label} already holds"
    n += (f". Ports, vessel class, distance and passages are those of its largest pair, {country(big['o'])} to {country(big['d'])} "
          f"({_mt(big['t'])}): {ports[big['load']][1]} to {ports[big['dis']][1]}, as the Route finder gives them. The ports are the atlas's "
          "typical ports (an assumption): the route stands for the corridor, not for each of its pairs")
    if named:
        n += (". The name says the country that holds at least " + f"{100 * COUNTRY_SHARE:.0f}% of the tonnes of an end: "
              + " and ".join(f"{country(iso)} ({'loading' if end == 'load' else 'discharge'}, {100 * sh:.0f}% of the tonnes)" for end, iso, sh in named))
    if hand_ids:
        top = sorted(hand_ids.items(), key=lambda x: (-x[1], x[0]))[:3]
        n += ". A hand-written route already covers part of it: " + "; ".join(f"{route_names.get(i, i)} ({_mt(t)})" for i, t in top)
    return n


def pair_passages(plan_via, row_via, row_alt, parallel=None):
    """`via` and `viaAlt` of a route that stands for a pair, from the pair's row of the pairs file: the passages every
    port option crosses (in the order of the drawn route), and the others as the lists of `viaAlt` (each parallel group
    one list, any other passage a list of its own: what the site's `altLists` makes of the same mask). The drawn route
    is that of the main port option, which may cross more than the pair's own list. `plan_via` is its list, `row_via` and
    `row_alt` the sets of the row."""
    if parallel is None:
        parallel = [set().union(*g) for g in routing.PARALLEL]
    via = [g for g in plan_via if g in row_via] + sorted(g for g in row_via if g not in plan_via)
    alt_flat = sorted(row_alt - set(via), key=list(routing.GATES).index)  # the order of a pairs file's mask, as the site reads it
    lists = [[g for g in alt_flat if g in grp] for grp in parallel]
    lists = [lst for lst in lists if lst]
    lists += [[g] for g in alt_flat if not any(g in grp for grp in parallel)]
    return via, lists


def _describe(g, p, c, ports, names, zone, country, cargo_label):
    """Name, labels and the countries that name it, of a corridor `c` of select_group()."""
    the = lambda key, label: ("the " + label) if key in THE else label  # noqa: E731
    a_label = names[c["a"]]
    a_name, to_zone = the(c["a"], a_label), c["b"]
    b_single = None  # the zone of the discharge end when it is one zone
    if to_zone.startswith("r:"):
        to_zones = {zone(r["b"]) for r in c["rows"]}
        region = REGIONS[to_zone[2:]][0] if to_zone[2:] in REGIONS else names[to_zone[2:]]
        one = len(to_zones) == 1
        b_zone_label = names[next(iter(to_zones))] if one else region
        if one:
            b_single = next(iter(to_zones))
        # a region that holds the exporting zone: the buyers are its other zones
        b_name = f"the rest of {the(to_zone, region)}" if REGION_OF.get(c["a"], c["a"]) == to_zone[2:] and not one else the(b_single if one else to_zone, b_zone_label)
    else:
        b_single, b_zone_label = to_zone, names[to_zone]
        b_name = the(to_zone, b_zone_label)
    cargo, what = cargo_label(g)
    zone_form = f"{cargo} within {a_name}" if a_label == b_zone_label else f"{cargo}: {a_name} to {b_name}"
    # a country that holds most of the tonnes of an end names the route, unless the zone's own name says it
    named = []
    for end, zid in (("load", c["a"]), ("dis", b_single)):
        iso, share = _end(c["rows"], end, ports)
        if share >= COUNTRY_SHARE and iso not in ZONE_SAYS.get(zid, ()):
            named.append((end, iso, share))
    ends = {end: country(iso) for end, iso, _ in named}
    a_txt, b_txt = ends.get("load", a_name), ends.get("dis", b_name)
    if named and a_label == b_zone_label and len(named) == 1:
        # one country of the zone to the rest of that zone
        if "load" in ends:
            b_txt = f"the rest of {a_name}"
        else:
            a_txt = f"the rest of {a_name}"
    name = f"{cargo}: {a_txt} to {b_txt}" if named else zone_form
    return {"name": name, "zoneName": zone_form, "a_label": a_label, "b_label": b_zone_label, "b_name": b_name, "named": named,
            "what": what, "cargo": cargo}


def cap_order(per_group, total_cap=TOTAL_CAP):
    """[(rank, group)] of the corridors kept under the cap of the whole atlas, in the order they are taken: the first
    corridor of each group of AUDIT_GROUPS, then the largest corridor (Mt that no hand-written route names) among the next
    corridor of every group, and so on."""
    order = [(0, g) for g in sorted(per_group) if g in AUDIT_GROUPS and per_group[g]]
    nxt = {g: (1 if g in AUDIT_GROUPS else 0) for g in per_group}
    while len(order) < total_cap:
        heads = [(per_group[g][i]["new"], g) for g, i in nxt.items() if i < len(per_group[g])]
        if not heads:
            break
        _, g = min(heads, key=lambda x: (-x[0], x[1]))
        order.append((nxt[g], g))
        nxt[g] += 1
    return order[:total_cap]


def generate(pairs, ports_by_group, hand, zones, at, cargo_label, route_names, country, target=TARGET, total_cap=TOTAL_CAP):
    """Route definitions of the generated corridors, and a report.

    pairs: decoded pairs files (build_freight.load_pairs, with `ports`); hand: {(group, o, d): [route ids]} of the
    hand-written routes still running; zones: zones.json; at(code): [lon, lat] of a port; cargo_label(group): (name for a route
    name, noun for a sentence) of the cargo; country(iso3): its name; route_names: {route id: name} of the hand-written
    routes. Returns (defs, report). A def holds the fields of a routes_def.json entry plus `generated`, `_ports` (load and
    discharge port of the largest pair), `_pair` (group, exporter, importer, Mt of that pair) and `_nm` (its distance);
    build_freight.py plans and measures it like any other route. The report gives, for each group, its seaborne
    Mt, the share named by the hand-written routes, the share after the generated routes, the corridors the cap left out
    (`left`: name and Mt that no route names) and the reason when the target is not reached."""
    names = zone_names(zones)
    zone = zone_lookup(ports_by_group, at)
    per_group = {}
    for g in sorted(pairs):
        per_group[g] = select_group(g, pairs[g], ports_by_group[g], hand, zone, target)
    kept = {(g, i) for i, g in cap_order(per_group, total_cap)}
    desc = {(g, i): _describe(g, pairs[g], c, ports_by_group[g], names, zone, country, cargo_label)
            for g, cs in per_group.items() for i, c in enumerate(cs)}
    # two routes of a group never share a name: the zone names tell them apart
    count = defaultdict(int)
    for (g, i), d in desc.items():
        if (g, i) in kept:
            count[d["name"]] += 1
    for (g, i), d in desc.items():
        if (g, i) in kept and count[d["name"]] > 1:
            d["name"], d["named"] = d["zoneName"], []
    defs, report = [], {}
    for g in sorted(pairs):
        p = pairs[g]
        sea = p["seaborne"]
        named = sum(r["t"] for r in p["rows"] if r["m"] in (0, 1) and (g, r["o"], r["d"]) in hand)
        union = {(r["o"], r["d"]) for r in p["rows"] if r["m"] in (0, 1) and (g, r["o"], r["d"]) in hand}
        got, left = 0, []
        for i, c in enumerate(per_group[g]):
            d = desc[(g, i)]
            if (g, i) not in kept:
                left.append({"name": d["zoneName"], "mt": c["new"]})
                continue
            got += 1
            for r in c["rows"]:
                union.add((r["o"], r["d"]))
            big = max((r for r in c["rows"]), key=lambda r: (r["t"], r["o"], r["d"]))
            ports = ports_by_group[g]
            ids = f"gen-{g}-{c['a']}-{c['b'].replace('r:', 'r-')}"
            hand_ids = defaultdict(float)
            for r in c["rows"]:
                for rid in hand.get((g, r["o"], r["d"]), []):
                    hand_ids[rid] += r["t"]
            end = {e: (iso, sh) for e, iso, sh in d["named"]}
            # the end of the route page says the country when the name does
            bare = lambda n: n[4:] if n.startswith("the ") else n  # noqa: E731
            a_region = bare(country(end["load"][0])) if "load" in end else d["a_label"]
            b_region = bare(country(end["dis"][0])) if "dis" in end else d["b_label"]
            defs.append({
                "id": ids, "name": d["name"], "benchmark": False, "generated": True, "vclass": big["cls"], "cargoes": [p["k"]],
                "from": {"region": a_region, "ports": [{"name": ports[big["load"]][1], "c": ports[big["load"]][2]}]},
                "to": {"region": b_region, "ports": [{"name": ports[big["dis"]][1], "c": ports[big["dis"]][2]}]},
                "corridor": _corridor(p["k"], g, c["rows"]), "s": "atlas",
                "notes": _note(p, c, big, d["a_label"], d["b_name"], d["what"], hand_ids, route_names, ports, country, d["named"]),
                "_ports": (big["a"], big["b"]), "_pair": (g, big["o"], big["d"], big["t"]), "_nm": big["nm"],
            })
        tonnes = sum(r["t"] for r in p["rows"] if r["m"] in (0, 1) and (r["o"], r["d"]) in union)
        why = None
        if tonnes < target * sea:
            if left:
                why = f"the cap of {total_cap} generated routes left out {len(left)} corridor{'s' if len(left) > 1 else ''}"
            elif got >= GROUP_CAP:
                why = f"the cap of {GROUP_CAP} routes per group was reached"
            else:
                why = (f"the remaining corridors are each under {max(FLOOR_MT, FLOOR_SHARE * sea):.1f} Mt, or mostly named by "
                       "hand-written routes, or have no routed port")
        report[g] = {"seaborne": sea, "handShare": 100 * named / sea, "share": 100 * tonnes / sea, "generated": got, "left": left, "why": why}
    return defs, report


def qa_markdown(report, target=TARGET, total_cap=TOTAL_CAP):
    """The QA report of the generated corridors (pipeline/freight/QA_routes.md): coverage of the 2024 seaborne tonnes by
    customs group, with and without the generated routes, and the corridors the cap left out. Built from the report of
    generate() only, so a rebuild on the same data writes the same text."""
    tot = sum(x["seaborne"] for x in report.values())
    hand = sum(x["seaborne"] * x["handShare"] for x in report.values()) / tot
    both = sum(x["seaborne"] * x["share"] for x in report.values()) / tot
    short = sorted(g for g, x in report.items() if x["share"] < 100 * target)
    out = [
        "# Generated freight corridors: coverage report",
        "",
        "Written by `pipeline/freight/build_freight.py` (step `generated_routes.py`) at each build; do not edit. "
        "Method: METHODOLOGY.md, section 3, \"Generated corridors\".",
        "",
        f"- Target: {100 * target:.0f}% of the seaborne tonnes of each customs group named by routes. Caps: {GROUP_CAP} generated routes "
        f"per group, {total_cap} in all. Floors: {FLOOR_MT} Mt and {100 * FLOOR_SHARE:.0f}% of the group's seaborne tonnes of a corridor not named by "
        f"hand-written routes, at least {100 * MIN_NEW_SHARE:.0f}% of the corridor's own tonnes outside them.",
        f"- {sum(x['generated'] for x in report.values())} generated routes over {len(report)} groups, {tot:,.0f} Mt of seaborne trade. "
        f"Named by hand-written routes: {hand:.1f}%. With the generated routes: {both:.1f}%.",
        f"- {len(report) - len(short)} of {len(report)} groups reach the target; {len(short)} are short of it.",
        "",
        "| Group | Seaborne Mt | Hand-written % | With generated % | Generated routes | Reason when under target |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for g, x in sorted(report.items()):
        out.append(f"| {g} | {x['seaborne']:,.1f} | {x['handShare']:.1f} | {x['share']:.1f} | {x['generated']} | {x['why'] or ''} |")
    left = [(g, c) for g, x in sorted(report.items()) for c in x["left"]]
    out += ["", f"## Corridors the cap left out ({len(left)})", "",
            "Mt are the tonnes of the corridor that no hand-written route names. The corridors of a group are listed in the order they were chosen.", ""]
    for g, c in left:
        out.append(f"- {g}: {c['name']}, {c['mt']:.1f} Mt")
    return "\n".join(out) + "\n"
