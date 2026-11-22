"""
Build the table of mapped lanes that cross each chokepoint (chokepoint pages, "Cargo on mapped lanes").

    python pipeline/freight/build_chokepoint_lanes.py

Input   data/freight/lanes/<group>.json    every lane lists the chokepoints it crosses in ``via``
Output  data/freight/chokepoint-lanes.json

Nothing is recomputed here: the tonnages are the lane flows of the lane files (customs data) and the
seaborne totals are those of the same files, so the table follows any rebuild of the lanes.
build_freight.py calls ``build`` after the lanes are written.
"""
import glob
import json
import os
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LANES = os.path.join(ROOT, "data", "freight", "lanes")
OUT = os.path.join(ROOT, "data", "freight", "chokepoint-lanes.json")


def build(lanes_dir=LANES, out=OUT):
    groups, through = {}, defaultdict(list)
    for f in sorted(glob.glob(os.path.join(lanes_dir, "*.json"))):
        d = json.load(open(f))
        g = d["group"]
        # seaborne trade of the group in the year of the lane flows: the denominator of every share
        groups[g] = {"k": d["k"], "label": d.get("label"), "y": d["y"], "s": d["s"],
                     "seaborne": d["seaborne"][d["years"].index(d["y"])]}
        for ln in d["lanes"]:
            v = round(ln["flow"]["v"], 3)
            for cp in dict.fromkeys(ln["via"]) if v > 0 else ():
                through[cp].append([g, ln["o"], ln["d"], v])
    years = sorted({g["y"] for g in groups.values()})
    doc = {
        "s": "atlas", "y": years[-1] if len(years) == 1 else f"{years[0]}-{years[-1]}", "unit": "Mt",
        "n": "Country-pair lanes mapped in the atlas whose routing crosses the passage; tonnages from each lane's customs "
             "source. Lanes not mapped are missing, so the sums are lower bounds.",
        "groups": groups,
        # per chokepoint: [group, origin, destination, Mt], largest first
        "chokepoints": {cp: sorted(rows, key=lambda r: -r[3]) for cp, rows in sorted(through.items())},
    }
    json.dump(doc, open(out, "w"), separators=(",", ":"))
    print("chokepoint lanes", {cp: len(rows) for cp, rows in doc["chokepoints"].items()})
    return doc


if __name__ == "__main__":
    build()
