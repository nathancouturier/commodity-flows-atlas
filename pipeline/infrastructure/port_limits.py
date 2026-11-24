"""
The vessel class of the atlas that each port can take, by the limits a page gives for the port.

    python pipeline/infrastructure/port_limits.py        # writes `maxClass` on the ports of data/infrastructure/ports.geojson

Input   data/infrastructure/ports.geojson         `limits` of a port: {draught, loa, beam (metres), dwt (tonnes), seg, cls,
                                                  depth, at, n, s, url, y}
        pipeline/freight/vessel_classes.json      `size` of a class: its band `min` to `max` in `u` (dwt, cbm or teu);
                                                  `std`: its standard vessel {draught, loa, beam, dwt}
Output  `maxClass` on each port with limits: {"dry" | "tanker" | "gas": {"classes": [...]}, "n": method} (Atlas estimate).
        Each entry of `classes` is {"id": class id, "orLarger"?: true, "by": "By deadweight", "basis": one sentence}.
        One entry: the class of the segment. Two entries: the two rules disagree, so the page shows both with their
        basis and no single class.

The rules, for each segment the port handles (its commodities `k`: gas for LNG and LPG, tankers for oil and vegetable
oils, dry bulk for the rest):
- By deadweight. The class whose size band (`size.min` to `size.max`, unit dwt) contains the port's deadweight limit,
  the upper edge included and the lower edge not, so that a limit of 80,000 dwt is Panamax and not Kamsarmax. Where
  several bands contain the limit, the widest band is the class: Newcastlemax (185,000 to 210,000 dwt) lies across the
  Capesize and VLOC bands and is never chosen, and Aframax and LR2 share one band (the one listed first, Aframax,
  stands for both). A limit above the band of the largest class of the segment gives that class "or larger"; a limit
  not above the smallest band gives no class. Classes measured in cubic metres or TEU have no deadweight band.
- By dimensions. When the page gives a draught, a length or a beam, the largest class of the segment whose standard
  vessel (`std`) is no larger than the limit in every one of those dimensions that both give. A class whose standard
  vessel has none of them is not compared, and the note names it; one whose size lies between the class found and
  the next larger class ruled out is named beside the class found (`also`), since nothing rules it out. A water depth
  is entered as a draught (`depth`): it is an upper bound of a ship's draught, so it can rule a class out, but it
  never gives a class on its own.
- Only a size of ship (deadweight, length or beam) opens the way to a class: a draught, a channel depth or a berth depth
  alone gives none.
- Both rules give the same class, or only one applies: that class, with its basis. They disagree: both, each with its
  basis, and no single class. A deadweight limit below the smallest band gives no class at all.
- Where the page itself names the class of ship the berths take (`limits.cls`: "for Capesize ships"), the class is
  that statement. A limit stated for one kind of berth (`limits.seg`: dry, tanker or gas) is compared for that segment
  only: the oil berth of a port that also loads grain says nothing of its grain berths.
This is a derivation of the atlas, not the port's own statement: a larger ship may call part-laden, at an offshore berth
or with the tide, and a limit stated for one berth says nothing of the others. Nothing is guessed: a port without limits
gets no class.
"""
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PORTS = os.path.join(ROOT, "data", "infrastructure", "ports.geojson")
CLASSES = os.path.join(ROOT, "pipeline", "freight", "vessel_classes.json")
DIMS = ("draught", "loa", "beam")  # the dimensions of a ship compared with a standard vessel
WORD = {"draught": "draught", "loa": "length", "beam": "beam"}
SHIP_DIMS = ("loa", "beam", "dwt")  # a size of ship: without one of them, no class (a depth alone gives none)
GAS = {"lng", "lpg"}
TANKER = {"crude-oil", "refined-products", "palm-oil", "soyoil"}
SEGMENTS = ("dry", "tanker", "gas")
SEGMENT_LABEL = {"dry": "Dry bulk", "tanker": "Tankers", "gas": "Gas carriers"}
BERTH_LABEL = {"dry": "dry bulk", "tanker": "tanker", "gas": "gas"}
NOTE = ("Atlas estimate, derived from the limits the page gives; not the port's own statement. By deadweight: the class "
        "whose size band holds the deadweight limit (\"or larger\" above the largest band; where bands overlap, the widest). "
        "By dimensions: the largest class whose standard vessel is no larger than the draught, length and beam given. "
        "No class from a depth alone. A larger ship may call part-laden, at another berth or with the tide.")


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


def _band(c):
    """(min, max) of the dwt band of a class, or None (a class measured in cbm or teu, or without a band)."""
    size = c.get("size") if isinstance(c.get("size"), dict) else {}
    if size.get("u") == "dwt" and _num(size.get("min")) and _num(size.get("max")):
        return size["min"], size["max"]
    return None


def _weight(c):
    """What orders the classes of a segment: the deadweight of the standard vessel, else the typical size."""
    std = c.get("std") if isinstance(c.get("std"), dict) else {}
    if _num(std.get("dwt")):
        return std["dwt"]
    size = c.get("size") if isinstance(c.get("size"), dict) else {}
    return size.get("typical") if _num(size.get("typical")) else 0


def class_by_deadweight(dwt, classes, segment):
    """(class, or_larger, band) for the class of a segment whose band holds the limit; (None, False, None) when the
    limit is not above the smallest band or no class of the segment has a deadweight band."""
    banded = [(c, _band(c)) for c in classes if c.get("segment") == segment and _band(c)]
    if not banded or dwt <= min(b[0] for _, b in banded):
        return None, False, None
    top = max(banded, key=lambda cb: cb[1][1])
    if dwt > top[1][1]:
        return top[0], True, top[1]
    inside = [cb for cb in banded if cb[1][0] < dwt <= cb[1][1]]
    if not inside:
        return None, False, None
    # the widest band; on a tie the class listed first (max keeps the first of equal keys)
    c, b = max(inside, key=lambda cb: cb[1][1] - cb[1][0])
    return c, False, b


def _shared(std, limits):
    return [d for d in DIMS if _num(std.get(d)) and _num(limits.get(d))]


def class_by_dimensions(limits, classes, segment):
    """(class, excluded, not compared, between) for the largest class of a segment whose standard vessel is within
    every dimension (draught, length, beam) that it and the page both give. `excluded` is (class, dimensions that rule
    out) for the next larger class compared, or None; `not compared` lists the classes with no dimension in common;
    `between` lists those of them that are larger than the class found and smaller than the one ruled out: nothing
    rules them out, so the class found is not named alone."""
    cands = [c for c in classes if c.get("segment") == segment]
    fit, out, skipped = [], [], []  # the list of classes not compared is of use only when some class was compared
    for c in cands:
        std = c.get("std") if isinstance(c.get("std"), dict) else {}
        shared = _shared(std, limits)
        if not shared:
            skipped.append(c)
        elif any(std[d] > limits[d] for d in shared):
            out.append((c, [d for d in shared if std[d] > limits[d]]))
        else:
            fit.append(c)
    if not fit:
        return None, None, skipped if out else [], []
    best = max(fit, key=_weight)
    larger = [(c, ds) for c, ds in out if _weight(c) > _weight(best)]
    excluded = min(larger, key=lambda cd: _weight(cd[0])) if larger else None
    # a class with no figure to compare that sits between the class found and the one ruled out (Panamax between
    # Ultramax and Kamsarmax); with no class ruled out, nothing bounds the list, and none is named
    between = sorted((c for c in skipped if excluded and _weight(best) < _weight(c) < _weight(excluded[0])), key=_weight)
    return best, excluded, skipped, between


def _dim_text(d, limits):
    v = _fmt(limits[d])
    if d == "draught":
        return f"the {v} m depth" if limits.get("depth") else f"the {v} m draught"
    return f"the {v} m {WORD[d]}"


def _join(parts):
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _name(c):
    """The name of a class in a sentence: without the alternative names in brackets (VLOC, not VLOC (Valemax/Guaibamax))."""
    return re.sub(r"\s*\(.*\)$", "", c.get("name", c["id"]))


def _dwt_entry(c, or_larger, band, limits):
    if or_larger:
        basis = (f"The {_fmt(limits['dwt'])} dwt limit is above the {_name(c)} band ({_fmt(band[0])} to {_fmt(band[1])} dwt), "
                 "the largest of the segment.")
    else:
        basis = f"The {_fmt(limits['dwt'])} dwt limit is in the {_name(c)} band ({_fmt(band[0])} to {_fmt(band[1])} dwt)."
    return {"id": c["id"], **({"orLarger": True} if or_larger else {}), "by": "By deadweight", "basis": basis}


def _dim_entry(c, excluded, limits, between=()):
    if excluded:
        ex, dims = excluded
        by = f"By {_join([_dim_text(d, limits) for d in dims])}"
        what = _join([f"a {_fmt(ex['std'][d])} m {WORD[d]}" for d in dims])
        basis = f"Its standard vessel is within every limit given; the next larger class compared, {_name(ex)}, has {what}."
        if between:
            names = _join([_name(b) for b in between])
            basis += (f" {names}, between the two in size, {'has' if len(between) == 1 else 'have'} no standard vessel in the "
                      "atlas and cannot be ruled out.")
            return {"id": c["id"], "also": [b["id"] for b in between], "by": by, "basis": basis}
    else:
        given = [d for d in DIMS if _num(c["std"].get(d)) and _num(limits.get(d))]
        by = f"By {_join([_dim_text(d, limits) for d in given])}"
        basis = "Its standard vessel is within every limit given; no larger class has one to compare."
    return {"id": c["id"], "by": by, "basis": basis}


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
    out, skipped = {}, []
    for seg in segs:
        if named and named.get("segment") == seg:
            out[seg] = {"classes": [{"id": named["id"], "by": "Named by the page",
                                     "basis": "The page itself names this class for these berths."}]}
            continue
        if not ship_size:
            continue
        entries = []
        dwt_none = False
        if _num(lim.get("dwt")):
            c, or_larger, band = class_by_deadweight(lim["dwt"], classes, seg)
            if c:
                entries.append(_dwt_entry(c, or_larger, band, lim))
            elif band is None and any(_band(x) for x in classes if x.get("segment") == seg):
                dwt_none = True  # a limit not above the smallest band: no class, whatever the dimensions say
        if not dwt_none:
            c, excluded, sk, between = class_by_dimensions(lim, classes, seg)
            skipped += sk
            if c:
                e = _dim_entry(c, excluded, lim, between)
                if entries and entries[0]["id"] == e["id"]:
                    entries[0] = {**entries[0], "by": f"{entries[0]['by']} and {e['by'][3:]}", "basis": f"{entries[0]['basis']} {e['basis']}"}
                else:
                    entries.append(e)
        if entries:
            out[seg] = {"classes": entries}
    if not out:
        return None
    note = NOTE
    other = [s for s in segments_of(props.get("k")) if s not in segs]
    if seg_only and other:
        note += f" The limits are those of the {BERTH_LABEL[seg_only]} berths: no class for the other cargoes."
    shown = {e["id"] for v in out.values() for e in v["classes"]}
    skipped = [s for s in skipped if s["id"] not in shown]
    if skipped:
        note += (" Not compared by dimensions, for want of a draught, length or beam of their standard vessel: "
                 + ", ".join(_name(s) for s in skipped) + ".")
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
