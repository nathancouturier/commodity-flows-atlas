"""
Build the table of the recorded seaborne pairs that cross each chokepoint (chokepoint pages).

    python pipeline/freight/build_chokepoint_lanes.py

Input   data/freight/pairs/<group>.json    every recorded pair of the latest year with its passages: ``via``
                                           (has to cross) and ``alt`` (may cross, one of several) bit masks
        data/freight/lanes/<group>.json    labels of the groups
        pipeline/freight/chokepoints.json the catalogue of passages (every passage gets a split file)
Output  data/freight/chokepoint-lanes.json
        data/freight/chokepoint-lanes/<id>.json   the same table split by passage (same note and row shape; the file of
                                                   a passage with no recorded lane holds an empty list of rows)

Nothing is recomputed here: the tonnages are the customs tonnages of the pairs table and the seaborne totals
are those of the same files, so the table follows any rebuild of the lanes. The fifth column of a row is 1 when
the passage is in the pair's ``via`` and 0 when it is one of the passages the pair may use (``viaAlt``); the
rows flagged 1 of a group sum to the "at least" tonnage of chokepoints.json. build_freight.py calls ``build``.
"""
import glob
import json
import os
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LANES = os.path.join(ROOT, "data", "freight", "lanes")
PAIRS = os.path.join(ROOT, "data", "freight", "pairs")
OUT = os.path.join(ROOT, "data", "freight", "chokepoint-lanes.json")
CATALOGUE = os.path.join(ROOT, "pipeline", "freight", "chokepoints.json")
# one file per passage (chokepoint pages) in the directory of the same name; the single file stays until the site
# reads these
SPLIT = os.path.splitext(OUT)[0]
SEABORNE = (0, 1)  # m of the pairs table: sea, sea through a foreign port (mixed and land pairs are not seaborne)


def build(pairs_dir=PAIRS, out=OUT, lanes_dir=LANES, split_dir=None, catalogue=CATALOGUE):
    groups, through = {}, defaultdict(list)
    for f in sorted(glob.glob(os.path.join(pairs_dir, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        g = d["group"]
        label = None
        lf = os.path.join(lanes_dir, os.path.basename(f))
        if os.path.exists(lf):
            with open(lf, encoding="utf-8") as fh:
                label = json.load(fh).get("label")
        # seaborne trade of the group in the latest year: the denominator of every share
        # a group under 1 Mt a year keeps its 0.1 kt (the site prints it in kt, as its lane file)
        nd = 3 if d["seaborne"] >= 1e3 else 4
        groups[g] = {"k": d["k"], "label": label, "y": d["y"], "s": d["s"], "seaborne": round(d["seaborne"] / 1e3, 2 if nd == 3 else 4)}
        c = {k: i for i, k in enumerate(d["cols"])}
        for r in d["rows"]:
            v = round(r[c["kt"]] / 1e3, nd)
            if r[c["m"]] not in SEABORNE or v <= 0:
                continue
            for i, cp in enumerate(d["gates"]):
                if r[c["via"]] >> i & 1:
                    through[cp].append([g, r[c["o"]], r[c["d"]], v, 1])
                elif r[c["alt"]] >> i & 1:
                    through[cp].append([g, r[c["o"]], r[c["d"]], v, 0])
    years = sorted({g["y"] for g in groups.values()})
    doc = {
        "s": "atlas", "y": years[-1] if len(years) == 1 else f"{years[0]}-{years[-1]}", "unit": "Mt",
        "n": "Recorded seaborne country pairs (CEPII BACI) whose route, as the atlas assumes it, crosses the passage. "
             "Rows marked 1 have to cross it: every recorded seaborne pair whose assumed route has to cross this "
             "passage, the 'at least' figure. Rows marked 0 may use it or a parallel passage of similar length, or "
             "load or discharge on another coast: added, they give the 'up to' figure. Mixed sea-and-land pairs, pairs "
             "that could not be routed and trades that customs data do not record are not in it.",
        "groups": groups,
        # per chokepoint: [group, origin, destination, Mt, 1 = has to cross | 0 = may cross], largest first
        "chokepoints": {cp: sorted(rows, key=lambda r: (-r[3], -r[4])) for cp, rows in sorted(through.items())},
    }
    json.dump(doc, open(out, "w"), separators=(",", ":"))
    with open(catalogue, encoding="utf-8") as fh:
        passages = [c["id"] for c in json.load(fh)]
    write_split(doc, split_dir or os.path.splitext(out)[0], passages)
    print("chokepoint lanes", {cp: len(rows) for cp, rows in doc["chokepoints"].items()})
    return doc


def write_split(doc, split_dir=SPLIT, passages=()):
    """One file per passage, <split_dir>/<id>.json, in the shape of the single file (same note and row shape, the
    passage's rows only and the groups those rows use), so a chokepoint page loads only its own rows. Every passage of
    ``passages`` has a file, with an empty list of rows when no lane crosses it (the page asks for its file and would
    otherwise get a 404 before it falls back to the whole table). Files of other passages are removed."""
    os.makedirs(split_dir, exist_ok=True)
    keep = set()
    for cp in sorted(set(passages) | set(doc["chokepoints"])):
        rows = doc["chokepoints"].get(cp, [])
        used = {r[0] for r in rows}
        part = {k: v for k, v in doc.items() if k not in ("groups", "chokepoints")}
        part["groups"] = {g: v for g, v in doc["groups"].items() if g in used}
        part["chokepoints"] = {cp: rows}
        name = cp + ".json"
        json.dump(part, open(os.path.join(split_dir, name), "w"), separators=(",", ":"))
        keep.add(name)
    for f in glob.glob(os.path.join(split_dir, "*.json")):
        if os.path.basename(f) not in keep:
            os.remove(f)


if __name__ == "__main__":
    build()
