"""
Build the index of the ports of the lanes, for the site's search field.

    python pipeline/freight/build_port_index.py

Input   data/freight/pairs/<group>.json    every recorded pair with the typical loading and discharging port of its
                                           main route (``ports`` table, ``load`` / ``dis`` columns, flag 4 of ``f`` =
                                           a main lane exists)
        data/freight/lanes/<group>.json    the lane pages: the ports they name in their ``load`` and ``discharge`` lists
                                           (``ports`` table of the file), which can be more than the typical ports of
                                           the pairs (GR4D.10)
        data/infrastructure/ports.geojson  the port assets: a port whose trade-engine code is the ``locode`` of an asset
                                           gets that asset (``asset``, "port:<id>"), so the search finds it as the asset
        pipeline/freight/routes_def.json   the names the routes give the ports (pipeline/infrastructure/route_assets.py):
                                           a row that is an asset lists, in ``aka``, the names of the asset that the
                                           engine and the routes use and the asset's own name is not ("Pusan" for Busan)
Output  data/freight/ports.json

Nothing is recomputed: the file only lists, for each port of the pairs tables and of the lane pages, the customs groups
it serves and the largest lane page that uses it, so that a search for a port can open that lane. The site would
otherwise have to download the 52 pairs files (more than 1 MB) to know the ports. Run it after build_lanes.py.
"""
import glob
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PAIRS = os.path.join(ROOT, "data", "freight", "pairs")
LANES = os.path.join(ROOT, "data", "freight", "lanes")
INFRA_PORTS = os.path.join(ROOT, "data", "infrastructure", "ports.geojson")
ROUTES_DEF = os.path.join(ROOT, "pipeline", "freight", "routes_def.json")
OUT = os.path.join(ROOT, "data", "freight", "ports.json")
LANE_FLAG = 4  # bit of a pairs row's ``f``: a main lane exists, id ``<group>:<o>-<d>``
GROUPS_PER_PORT = 3
LANES_PER_PORT = 5  # the largest lane pages that use a port, listed on its asset page


def port_assets(path=INFRA_PORTS):
    """{trade-engine code: "port:<id>"} of the port assets that carry a ``locode``."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        feats = json.load(fh)["features"]
    out = {}
    for f in feats:
        p = f["properties"]
        if p.get("locode"):
            out.setdefault(p["locode"], f"port:{p['id']}")
    return out


def asset_names(path=INFRA_PORTS):
    """{"port:<id>": name} of the port assets."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return {f"port:{f['properties']['id']}": f["properties"]["name"] for f in json.load(fh)["features"]}


def route_names(defs_path=ROUTES_DEF, infra_dir=None):
    """{"type:id": {names}}: the names the hand-written routes give each asset (the generated routes use the engine's
    names, which are the rows' own)."""
    if not defs_path or not os.path.exists(defs_path):
        return {}
    sys.path.insert(0, os.path.join(ROOT, "pipeline", "infrastructure"))
    import route_assets as RA  # noqa: E402
    with open(defs_path, encoding="utf-8") as fh:
        defs = json.load(fh)
    out = defaultdict(set)
    for r in defs:
        for side in ("from", "to"):
            assets = RA.route_port_assets(r[side], r.get("cargoes"), *([infra_dir] if infra_dir else []))
            for p, a in zip(r[side].get("ports") or [], assets):
                if a:
                    out[a].add(p["name"])
    return out


def lane_ports(lanes_dir):
    """The ports the lane pages name: ({port: {"id", "name", "c"}}, {port: {group: kt}}, {port: (kt, lane id)}, {port: pages},
    {port: {lane id: kt}}). The tonnes and the lanes count the main lanes of each file, whose pages exist."""
    ports, tonnes, best, n = {}, defaultdict(lambda: defaultdict(float)), {}, defaultdict(int)
    per_lane = defaultdict(dict)  # port -> {lane id: kt}
    for f in sorted(glob.glob(os.path.join(lanes_dir, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        for ln in d.get("lanes", []):
            if ln.get("set") != "main":
                continue
            kt = ln["flow"]["v"] * (1000 if ln["flow"].get("u") == "Mt" else 1)
            # the lane's ports and those of its options (another loading or discharging port of the same pair)
            # (a lane lists its ports; an option names one loading and one discharging port)
            named = {pid for part in (ln, *(ln.get("opts") or [])) for col in ("load", "discharge")
                     for pid in ([part[col]] if isinstance(part.get(col), str) else part.get(col) or [])}
            for pid in named:
                p = d["ports"].get(pid)
                if not p:
                    continue
                ports.setdefault(pid, {"id": pid, "name": p["name"], "c": p["c"]})
                tonnes[pid][d["group"]] += kt
                n[pid] += 1
                per_lane[pid][ln["id"]] = max(kt, per_lane[pid].get(ln["id"], 0))
                if pid not in best or kt > best[pid][0]:
                    best[pid] = (kt, ln["id"])
    return ports, tonnes, best, n, per_lane


def build(pairs_dir=PAIRS, out=OUT, lanes_dir=None, infra_ports=INFRA_PORTS, routes_def=ROUTES_DEF):
    ports, years = {}, set()
    tonnes = defaultdict(lambda: defaultdict(float))  # port -> group -> kt
    n_pairs = defaultdict(int)
    best_lane = {}  # port -> (kt, lane id)
    lanes_of = defaultdict(dict)  # port -> {lane id: kt}
    for f in sorted(glob.glob(os.path.join(pairs_dir, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        years.add(d["y"])
        c = {k: i for i, k in enumerate(d["cols"])}
        for r in d["rows"]:
            kt = r[c["kt"]]
            for col in ("load", "dis"):
                i = r[c[col]]
                if i is None or i < 0:
                    continue
                p = d["ports"][i]
                ports.setdefault(p[0], {"id": p[0], "name": p[1], "c": p[2]})
                tonnes[p[0]][d["group"]] += kt
                n_pairs[p[0]] += 1
                if r[c["f"]] & LANE_FLAG:
                    lane = f"{d['group']}:{r[c['o']]}-{r[c['d']]}"
                    lanes_of[p[0]][lane] = max(kt, lanes_of[p[0]].get(lane, 0))
                    if p[0] not in best_lane or kt > best_lane[p[0]][0]:
                        best_lane[p[0]] = (kt, lane)
    # the ports a lane page names and no pair of the files uses as its typical port: Brisbane, Darwin, Yantian...
    lp, lt, lbest, ln_, lper = lane_ports(lanes_dir or os.path.join(os.path.dirname(os.path.normpath(pairs_dir)), "lanes"))
    for pid, p in lp.items():
        # a lane page that names a port lists it among the port's lanes, whichever table found the port first
        for lane, kt in lper.get(pid, {}).items():
            lanes_of[pid][lane] = max(kt, lanes_of[pid].get(lane, 0))
        if pid in ports:
            continue
        ports[pid] = p
        tonnes[pid] = lt[pid]
        n_pairs[pid] = ln_[pid]
        best_lane[pid] = lbest[pid]
    assets = port_assets(infra_ports)
    names = asset_names(infra_ports)
    by_route = route_names(routes_def, os.path.dirname(infra_ports)) if assets else {}
    rows = []
    for pid in sorted(ports, key=lambda k: (-sum(tonnes[k].values()), k)):
        top = sorted(tonnes[pid], key=lambda g: (-tonnes[pid][g], g))[:GROUPS_PER_PORT]
        row = {**ports[pid], "n": n_pairs[pid], "g": top, "lane": best_lane[pid][1] if pid in best_lane else None}
        if lanes_of.get(pid):
            row["lanes"] = sorted(lanes_of[pid], key=lambda k: (-lanes_of[pid][k], k))[:LANES_PER_PORT]
        if pid in assets:
            row["asset"] = assets[pid]
            own = names.get(assets[pid], "").casefold()
            aka = sorted({ports[pid]["name"], *by_route.get(assets[pid], ())} - {names.get(assets[pid])},
                         key=str.casefold)
            aka = [a for a in aka if a.casefold() != own]
            if aka:
                row["aka"] = aka
        rows.append(row)
    doc = {
        "s": "atlas",
        "y": max(years) if len(years) == 1 else f"{min(years)}-{max(years)}",
        "n": "Ports of the lanes: the typical ports of the main routes of the recorded seaborne pairs (the pairs tables, CEPII BACI customs data) "
             "and the ports the lane pages name. `n` = pairs that use the port (for a port only the lane pages name: the lane pages "
             "that name it), `g` = customs groups it serves (largest first), `lane` = the largest pair that has a lane page "
             "(for a port only the lane pages name: the largest lane that names it), `lanes` = the largest lane pages that use it, "
             "`asset` = the port asset of the infrastructure layer that is this place (its `locode`): the search opens the asset; "
             "`aka` = the other names of that asset that the trade engine and the routes use (\"Pusan\" for Busan). "
             "Only the names and the links are used by the site; no figure is published here.",
        "ports": rows,
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, separators=(",", ":"), ensure_ascii=False)
    print(f"port index: {len(rows)} ports, {sum(1 for r in rows if r['lane'])} with a lane page, "
          f"{sum(1 for r in rows if r.get('asset'))} are assets ({sum(1 for r in rows if r.get('aka'))} with other names), "
          f"{os.path.getsize(out)} bytes")
    return doc


if __name__ == "__main__":
    build()
