"""
The largest vessel class of the atlas that each port can take, by the limits a page gives for the port.

    python pipeline/infrastructure/port_limits.py        # writes `maxClass` on the ports of data/infrastructure/ports.geojson

Input   data/infrastructure/ports.geojson         `limits` of a port: {draught, loa, beam (metres), dwt (tonnes), n, s, url, y}
        pipeline/freight/vessel_classes.json      `std` of a class: its standard vessel {draught, loa, beam, dwt}
Output  `maxClass` on each port with limits: {"dry" | "tanker" | "gas": class id, "n": method} (Atlas estimate)

A class fits a port when its standard vessel is no larger than the port's limit in every dimension that both give
(draught, length, beam, deadweight). The largest class that fits, by the deadweight of its standard vessel, is the port's
class for each segment the port handles (its commodities `k`: gas for LNG and LPG, tankers for oil and vegetable oils,
dry bulk for the rest). A class without a standard vessel, or with no dimension that the page also gives, is not
compared. This is a derivation of the atlas, not the port's own statement: a larger ship may call part-laden, at
an offshore berth or with the tide, and a limit stated for one berth says nothing of the others. Nothing is guessed:
a port without limits gets no class, and the class is removed when no class fits.
"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PORTS = os.path.join(ROOT, "data", "infrastructure", "ports.geojson")
CLASSES = os.path.join(ROOT, "pipeline", "freight", "vessel_classes.json")
DIMS = ("draught", "loa", "beam", "dwt")
GAS = {"lng", "lpg"}
TANKER = {"crude-oil", "refined-products", "palm-oil", "soyoil"}
SEGMENTS = ("dry", "tanker", "gas")
NOTE = ("Atlas estimate: the largest class whose standard vessel is no larger than every limit the page gives "
        "(draught, length, beam, deadweight). Only the dimensions the page gives are compared: a port whose page gives its "
        "depth alone may not take a ship that long or that wide. Not the port's own statement: a larger ship may call "
        "part-laden, at another berth or with the tide.")


def segments_of(k):
    """The vessel segments a port's commodities travel in."""
    out = set()
    for c in k or []:
        out.add("gas" if c in GAS else "tanker" if c in TANKER else "dry")
    return [s for s in SEGMENTS if s in out]


def fits(std, limits):
    """None when no dimension can be compared; else whether the standard vessel fits every limit given."""
    shared = [d for d in DIMS if isinstance(std.get(d), (int, float)) and isinstance(limits.get(d), (int, float))]
    if not shared:
        return None
    return all(std[d] <= limits[d] for d in shared)


def largest_class(limits, classes, segment):
    """Id of the largest class of a segment that fits the limits, or None."""
    cands = [c for c in classes if c.get("segment") == segment and isinstance(c.get("std"), dict)]
    cands.sort(key=lambda c: -(c["std"].get("dwt") or 0))
    for c in cands:
        if fits(c["std"], limits):
            return c["id"]
    return None


def max_class(props, classes):
    """The `maxClass` of a port, or None."""
    lim = props.get("limits")
    if not isinstance(lim, dict):
        return None
    out = {}
    for seg in segments_of(props.get("k")):
        cid = largest_class(lim, classes, seg)
        if cid:
            out[seg] = cid
    if not out:
        return None
    skipped = sorted(c["id"] for c in classes if c.get("segment") in out and not isinstance(c.get("std"), dict))
    note = NOTE + (f" Classes without a standard vessel in the atlas are not compared ({', '.join(skipped)})." if skipped else "")
    return {**out, "n": note}


def apply(ports_path=PORTS, classes_path=CLASSES):
    with open(classes_path, encoding="utf-8") as fh:
        classes = json.load(fh)
    with open(ports_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    n = 0
    for f in doc["features"]:
        p = f["properties"]
        m = max_class(p, classes)
        if m is None:
            p.pop("maxClass", None)
            continue
        n += 1
        if "maxClass" in p:
            p["maxClass"] = m
        else:
            # after `limits`, the field it is derived from
            keys = list(p)
            i = keys.index("limits") + 1
            f["properties"] = {k: p[k] for k in keys[:i]} | {"maxClass": m} | {k: p[k] for k in keys[i:]}
    with open(ports_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=1, ensure_ascii=False))
    print(f"port limits: {sum(1 for f in doc['features'] if f['properties'].get('limits'))} ports with limits, {n} with a class")
    return doc


if __name__ == "__main__":
    apply(*sys.argv[1:])
