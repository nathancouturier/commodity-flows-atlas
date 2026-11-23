"""
The largest vessel class of the atlas that each port can take, by the limits a page gives for the port.

    python pipeline/infrastructure/port_limits.py        # writes `maxClass` on the ports of data/infrastructure/ports.geojson

Input   data/infrastructure/ports.geojson         `limits` of a port: {draught, loa, beam (metres), dwt (tonnes), seg, cls,
                                                  depth, at, n, s, url, y}
        pipeline/freight/vessel_classes.json      `std` of a class: its standard vessel {draught, loa, beam, dwt}; `size`:
                                                  its band and typical size (`typical`, in `u`: dwt, cbm, teu)
Output  `maxClass` on each port with limits: {"dry" | "tanker" | "gas": class id, "n": method} (Atlas estimate)

The rules:
- No class from a depth alone. A class is derived only when the page gives a size of ship: its deadweight, length or
  beam. A draught, a channel depth or a berth depth is shown as a limit and gives no class on its own (a depth is an
  upper bound of a ship's draught, so it can still rule a class out).
- A limit stated for one kind of berth (`limits.seg`: dry, tanker or gas) is compared for that segment only: the oil
  berth of a port that also loads grain says nothing of its grain berths.
- A class with a standard vessel fits when that vessel is no larger than the port's limit in every dimension that both
  give. A class without one is compared by its typical deadweight (`size.typical` when `size.u` is dwt) with the
  port's deadweight limit, and is never placed above a smaller class whose standard vessel does not fit. A class
  measured in cubic metres without a standard vessel is not compared.
- Where the page itself names the class of ship the berths take (`limits.cls`: "for Capesize ships"), the class is
  that statement.
The largest class that fits is the port's class for each segment the port handles (its commodities `k`: gas for LNG and
LPG, tankers for oil and vegetable oils, dry bulk for the rest), and `n` says for each class on which basis it was
compared. This is a derivation of the atlas, not the port's own statement: a larger ship may call part-laden, at an
offshore berth or with the tide, and a limit stated for one berth says nothing of the others. Nothing is guessed: a port
without limits gets no class, and the class is removed when no class fits.
"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PORTS = os.path.join(ROOT, "data", "infrastructure", "ports.geojson")
CLASSES = os.path.join(ROOT, "pipeline", "freight", "vessel_classes.json")
DIMS = ("draught", "loa", "beam", "dwt")
SHIP_DIMS = ("loa", "beam", "dwt")  # a size of ship: without one of them, no class (a depth alone gives none)
GAS = {"lng", "lpg"}
TANKER = {"crude-oil", "refined-products", "palm-oil", "soyoil"}
SEGMENTS = ("dry", "tanker", "gas")
SEGMENT_LABEL = {"dry": "Dry bulk", "tanker": "Tankers", "gas": "Gas carriers"}
BERTH_LABEL = {"dry": "dry bulk", "tanker": "tanker", "gas": "gas"}
NOTE = ("Atlas estimate, derived from the limits the page gives; not the port's own statement. A class is derived only "
        "where the page gives a size of ship (deadweight, length or beam), never from a depth alone. A class with a "
        "standard vessel fits when that vessel is no larger than every limit given; a class without one is compared by "
        "its typical deadweight with the deadweight limit, and is never placed above a smaller class whose standard "
        "vessel does not fit. A larger ship may call part-laden, at another berth or with the tide.")


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _fmt(x):
    return f"{x:,.0f}" if float(x).is_integer() else f"{x:,}"


def segments_of(k):
    """The vessel segments a port's commodities travel in."""
    out = set()
    for c in k or []:
        out.add("gas" if c in GAS else "tanker" if c in TANKER else "dry")
    return [s for s in SEGMENTS if s in out]


def fits(std, limits):
    """Whether a standard vessel fits the limits: False when it exceeds one of them; True when it is within all and at
    least one of them is a size of ship; None when nothing compares (a draught or a depth alone can rule out, not in)."""
    shared = [d for d in DIMS if _num(std.get(d)) and _num(limits.get(d))]
    if any(std[d] > limits[d] for d in shared):
        return False
    return True if any(d in SHIP_DIMS for d in shared) else None


def typical_dwt(c):
    """The typical deadweight of a class (`size.typical` when its unit is dwt), or None."""
    size = c.get("size") if isinstance(c.get("size"), dict) else {}
    return size["typical"] if size.get("u") == "dwt" and _num(size.get("typical")) else None


def _weight(c):
    std = c.get("std") if isinstance(c.get("std"), dict) else None
    if std and _num(std.get("dwt")):
        return std["dwt"]
    return typical_dwt(c)


def largest_class(limits, classes, segment):
    """(class, basis, classes not compared) for the largest class of a segment that fits the limits; class is None when
    none fits. `basis` is "std" (its standard vessel) or "typical" (its typical deadweight)."""
    cands = [c for c in classes if c.get("segment") == segment]
    with_std = [c for c in cands if isinstance(c.get("std"), dict)]
    failed = [_weight(c) for c in with_std if fits(c["std"], limits) is False and _weight(c) is not None]
    verdicts, skipped = [], []
    for c in cands:
        w = _weight(c)
        if isinstance(c.get("std"), dict):
            ok = fits(c["std"], limits)
            basis = "std"
        elif typical_dwt(c) is not None and any(f <= typical_dwt(c) for f in failed):
            ok, basis = False, "typical"  # never placed above a smaller class whose standard vessel does not fit
        elif typical_dwt(c) is not None and _num(limits.get("dwt")):
            ok = typical_dwt(c) <= limits["dwt"]
            basis = "typical"
        else:
            ok, basis = None, None
        if ok is None or w is None:
            skipped.append(c)
        elif ok:
            verdicts.append((w, c, basis))
    if not verdicts:
        return None, None, skipped
    w, c, basis = max(verdicts, key=lambda v: v[0])
    return c, basis, skipped


def _basis_text(c, basis, limits):
    if basis == "std":
        std = c["std"]
        unit = {"draught": "m draught", "loa": "m long", "beam": "m beam", "dwt": "dwt"}
        dims = [f"{_fmt(std[d])} {unit[d]}" for d in ("dwt", "loa", "beam", "draught") if _num(std.get(d)) and _num(limits.get(d))]
        return f"compared by its standard vessel ({', '.join(dims)})"
    return f"compared by its typical deadweight ({_fmt(typical_dwt(c))} dwt) with the deadweight limit ({_fmt(limits['dwt'])} dwt)"


def max_class(props, classes):
    """The `maxClass` of a port, or None."""
    lim = props.get("limits")
    if not isinstance(lim, dict):
        return None
    by_id = {c["id"]: c for c in classes}
    segs = segments_of(props.get("k"))
    named = by_id.get(lim.get("cls")) if lim.get("cls") else None
    seg_only = lim.get("seg") or (named or {}).get("segment")
    if seg_only:
        segs = [s for s in segs if s == seg_only]
    ship_size = any(_num(lim.get(d)) for d in SHIP_DIMS)
    out, lines, skipped = {}, [], []
    for seg in segs:
        if named and named.get("segment") == seg:
            out[seg] = named["id"]
            lines.append(f"{SEGMENT_LABEL[seg]}: {named.get('name', named['id'])}, the class the page itself names for these berths.")
            continue
        if not ship_size:
            continue
        c, basis, sk = largest_class(lim, classes, seg)
        if c is None:
            continue
        out[seg] = c["id"]
        lines.append(f"{SEGMENT_LABEL[seg]}: {c.get('name', c['id'])}, {_basis_text(c, basis, lim)}.")
        skipped += [s for s in sk if s["id"] != c["id"]]
    if not out:
        return None
    note = " ".join([NOTE, *lines])
    other = [s for s in segments_of(props.get("k")) if s not in segs]
    if seg_only and other:
        note += f" The limits are those of the {BERTH_LABEL[seg_only]} berths: no class for the other cargoes."
    if skipped:
        note += f" Not compared, for want of a standard vessel or of a deadweight limit: {', '.join(s.get('name', s['id']) for s in skipped)}."
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
