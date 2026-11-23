"""
Build the index of the typical ports of the lanes, for the site's search field.

    python pipeline/freight/build_port_index.py

Input   data/freight/pairs/<group>.json    every recorded pair with the typical loading and discharging port of its
                                           main route (``ports`` table, ``load`` / ``dis`` columns, flag 4 of ``f`` =
                                           a main lane exists)
Output  data/freight/ports.json

Nothing is recomputed: the file only lists, for each port of the pairs tables, the customs groups it serves and the
largest pair that has a lane page, so that a search for a port can open that lane. The site would otherwise have to
download the 34 pairs files (more than 1 MB) to know the ports. Run it after build_lanes.py.
"""
import glob
import json
import os
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PAIRS = os.path.join(ROOT, "data", "freight", "pairs")
OUT = os.path.join(ROOT, "data", "freight", "ports.json")
LANE_FLAG = 4  # bit of a pairs row's ``f``: a main lane exists, id ``<group>:<o>-<d>``
GROUPS_PER_PORT = 3


def build(pairs_dir=PAIRS, out=OUT):
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
    rows = []
    for pid in sorted(ports, key=lambda k: (-sum(tonnes[k].values()), k)):
        top = sorted(tonnes[pid], key=lambda g: (-tonnes[pid][g], g))[:GROUPS_PER_PORT]
        rows.append({**ports[pid], "n": n_pairs[pid], "g": top, "lane": best_lane[pid][1] if pid in best_lane else None})
    doc = {
        "s": "atlas",
        "y": max(years) if len(years) == 1 else f"{min(years)}-{max(years)}",
        "n": "Typical ports of the main routes of the recorded seaborne pairs (the pairs tables, CEPII BACI customs data): "
             "`n` = pairs that use the port, `g` = customs groups it serves (largest first), `lane` = the largest pair "
             "that has a lane page. Only the names and the links are used by the search field; no figure is published here.",
        "ports": rows,
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, separators=(",", ":"), ensure_ascii=False)
    print(f"port index: {len(rows)} ports, {sum(1 for r in rows if r['lane'])} with a lane page, {os.path.getsize(out)} bytes")
    return doc


if __name__ == "__main__":
    build()
