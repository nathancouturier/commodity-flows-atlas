"""
Build the index of the ports of the lanes, for the site's search field.

    python pipeline/freight/build_port_index.py

Input   data/freight/pairs/<group>.json    every recorded pair with the typical loading and discharging port of its
                                           main route (``ports`` table, ``load`` / ``dis`` columns, flag 4 of ``f`` =
                                           a main lane exists)
        data/freight/lanes/<group>.json    the lane pages: the ports they name in their ``load`` and ``discharge`` lists
                                           (``ports`` table of the file), which can be more than the typical ports of
                                           the pairs (GR4D.10)
Output  data/freight/ports.json

Nothing is recomputed: the file only lists, for each port of the pairs tables and of the lane pages, the customs groups
it serves and the largest lane page that uses it, so that a search for a port can open that lane. The site would
otherwise have to download the 42 pairs files (more than 1 MB) to know the ports. Run it after build_lanes.py.
"""
import glob
import json
import os
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PAIRS = os.path.join(ROOT, "data", "freight", "pairs")
LANES = os.path.join(ROOT, "data", "freight", "lanes")
OUT = os.path.join(ROOT, "data", "freight", "ports.json")
LANE_FLAG = 4  # bit of a pairs row's ``f``: a main lane exists, id ``<group>:<o>-<d>``
GROUPS_PER_PORT = 3


def lane_ports(lanes_dir):
    """The ports the lane pages name: ({port: {"id", "name", "c"}}, {port: {group: kt}}, {port: (kt, lane id)}). The tonnes and the
    largest lane count the main lanes of each file, whose pages exist."""
    ports, tonnes, best, n = {}, defaultdict(lambda: defaultdict(float)), {}, defaultdict(int)
    for f in sorted(glob.glob(os.path.join(lanes_dir, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        for ln in d.get("lanes", []):
            if ln.get("set") != "main":
                continue
            kt = ln["flow"]["v"] * (1000 if ln["flow"].get("u") == "Mt" else 1)
            # the lane's ports and those of its options (another loading or discharging port of the same pair)
            named = {pid for part in (ln, *(ln.get("opts") or [])) for col in ("load", "discharge") for pid in part.get(col) or []}
            for pid in named:
                p = d["ports"].get(pid)
                if not p:
                    continue
                ports.setdefault(pid, {"id": pid, "name": p["name"], "c": p["c"]})
                tonnes[pid][d["group"]] += kt
                n[pid] += 1
                if pid not in best or kt > best[pid][0]:
                    best[pid] = (kt, ln["id"])
    return ports, tonnes, best, n


def build(pairs_dir=PAIRS, out=OUT, lanes_dir=None):
    ports, years = {}, set()
    tonnes = defaultdict(lambda: defaultdict(float))  # port -> group -> kt
    n_pairs = defaultdict(int)
    best_lane = {}  # port -> (kt, lane id)
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
                    if p[0] not in best_lane or kt > best_lane[p[0]][0]:
                        best_lane[p[0]] = (kt, lane)
    # the ports a lane page names and no pair of the files uses as its typical port: Brisbane, Darwin, Yantian...
    lp, lt, lbest, ln_ = lane_ports(lanes_dir or os.path.join(os.path.dirname(os.path.normpath(pairs_dir)), "lanes"))
    for pid, p in lp.items():
        if pid in ports:
            continue
        ports[pid] = p
        tonnes[pid] = lt[pid]
        n_pairs[pid] = ln_[pid]
        best_lane[pid] = lbest[pid]
    rows = []
    for pid in sorted(ports, key=lambda k: (-sum(tonnes[k].values()), k)):
        top = sorted(tonnes[pid], key=lambda g: (-tonnes[pid][g], g))[:GROUPS_PER_PORT]
        rows.append({**ports[pid], "n": n_pairs[pid], "g": top, "lane": best_lane[pid][1] if pid in best_lane else None})
    doc = {
        "s": "atlas",
        "y": max(years) if len(years) == 1 else f"{min(years)}-{max(years)}",
        "n": "Ports of the lanes: the typical ports of the main routes of the recorded seaborne pairs (the pairs tables, CEPII BACI customs data) "
             "and the ports the lane pages name. `n` = pairs that use the port (for a port only the lane pages name: the lane pages "
             "that name it), `g` = customs groups it serves (largest first), `lane` = the largest pair that has a lane page "
             "(for a port only the lane pages name: the largest lane that names it). Only the names and the links are used by the search field; no figure is published here.",
        "ports": rows,
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, separators=(",", ":"), ensure_ascii=False)
    print(f"port index: {len(rows)} ports, {sum(1 for r in rows if r['lane'])} with a lane page, {os.path.getsize(out)} bytes")
    return doc


if __name__ == "__main__":
    build()
