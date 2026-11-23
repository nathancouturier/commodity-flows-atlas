"""
Series by country and year of the commodity tables: data/commodities/history/<id>.json (CommodityHistory, web/src/types.ts).

Called from build_commodities.main(). A table writer of build_commodities.py leaves on each table it builds the years its
source has and a function that builds the same table for another year (`_hist`): the same reader, cleaning rules, world
total and estimate marks. Each year is built with it, so the latest year of a series is the table the page shows.

  exports, imports   CEPII BACI, cleaned frame of pipeline/trade/clean.py, HIST_FROM to the latest year
  energy tables      EIA International Energy Data, annual series, HIST_FROM to the year of the table
  agriculture        USDA PSD, market years HIST_FROM/.. to PSD_MY (the year rule of _latest_inputs)
  metals, minerals   USGS MCS: the two years of the file (the year before the edition, and the edition's own year)

File (no pretty-printing; values rounded as the tables are):
  {"id", "t": {<table key>: {"u", "s", "years", "labels"?, "world", "worldEst"?, "pub"?, "other"?, "yl"?, "n"?,
                             "c": {iso: [value or null per year]}, "est"?: {iso: [year index]}, "srcEst"?: {iso: [year index]},
                             "out"?: {iso: [year index]}, "worldOut"?: [year index], "cl"?: {iso: [label or null per year]},
                             "brk"?: {iso: [year index]}}}}
  - `est`: the row is mostly an Atlas estimate that year (tonnage computed from the declared value), as `est` of a table row;
  - `srcEst`: the value is the source's own estimate (USGS "Estimated.");
  - `worldEst`: years whose world total holds a tenth or more of Atlas estimates;
  - `pub`: the published world total where the shares rest on the sum of the lines (`world`); `other`: USGS "Other countries";
  - `yl`: what each year is, in the words the source supports (USGS MCS);
  - `out`: the source's value is far out of line with the years around it (out_of_line): kept as published, not ranked or
    drawn that year; `worldOut`: the years whose world total holds such a value;
  - `cl`: the name of a row in the years where the source's entity is not the one of the latest year (USDA PSD's European
    Union row); `brk`: the years at which the series of a row breaks (its entity changes): no change is computed across them;
  - `n`: notes on the series as a whole (a first year set by a rule, a change of membership or coverage, a country that
    split), in plain words, with the years read from the files.
A table key is a section of the commodity file (production, exports...) or the `key` of one of its `extra` tables.
"""
import csv
import json
import os

FAILED = (KeyError, SystemExit, ValueError, ZeroDivisionError)

# A value far out of line with the years around it (a unit or reporting break of the source, such as the EIA's US LPG
# consumption of 2021): it is kept in the file, flagged, and neither ranked nor drawn. A value is out of line when
#  - the world total of that year is OUT_WORLD times above or below both neighbouring years, and
#  - one country is OUT_ROW times above or below both its neighbouring years (or, where its series starts or stops next to
#    that year, OUT_ROW times above the one neighbour it has) and accounts for OUT_PART or more of the world's departure, and
#  - where the source gives a declared value (CEPII BACI), that value did not move with the tonnage: a unit value within
#    UV_SAME times the neighbouring years' means a real change of trade, kept as reported.
# Shocks spread over many countries (2009, 2020, 2022) move the world without one country carrying the jump: not caught.
OUT_WORLD, OUT_ROW, OUT_PART, UV_SAME = 1.3, 3.0, 0.5, 2.0
# A country whose figures stop before the last year of a series while it held this share of the world: the series note says so.
COVER_SHARE = 0.05

# Codes of the sources that ended inside the period and the countries that took their place: the last year of each is read
# from the CEPII country list (pipeline/cache/baci_country_codes.csv, "Sudan (...2011)"); a series note is written only for a
# series in which a successor's own figures start within SPLIT_LAG years after it.
CODE_CHANGES = {"SDN": ("SSD",), "SCG": ("SRB", "MNE"), "ANT": ("CUW", "SXM", "BES")}
SPLIT_LAG = 2
CODES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cache", "baci_country_codes.csv")


def code_ends():
    """{code: (name, last year)} for the codes of the CEPII country list whose name carries their last year."""
    out = {}
    try:
        with open(CODES_FILE, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                name = r["country_name"]
                if "(..." in name and r["country_iso3"] in CODE_CHANGES:
                    out[r["country_iso3"]] = (name.split(" (...")[0], int(name.split("(...")[1].rstrip(")")))
    except (OSError, ValueError, KeyError):
        pass
    return out


def _tables(d):
    for sec in ("production", "refinery", "reserves", "consumption", "exports", "imports"):
        if isinstance(d.get(sec), dict):
            yield sec, d[sec]
    for x in d.get("extra") or []:
        yield x["key"], x["table"]


def _off(v, ns, k):
    """How far `v` lies outside `k` times its neighbours `ns` (signed, in the unit of the table); 0 when it is in line."""
    ns = [x for x in ns if x]
    if not v or not ns:
        return 0
    if v >= k * max(ns):
        return v - max(ns)
    if v <= min(ns) / k and len(ns) > 1:  # a fall needs both neighbours: a country that stops after a drop is not a break
        return v - min(ns)
    return 0


def out_of_line(world, vals, usd=None):
    """{iso: [year index]} of the values far out of line with the years around them (the rule above OUT_WORLD)."""
    out = {}
    n = len(world)
    for i in range(1, n - 1):
        ex = _off(world[i], [world[i - 1], world[i + 1]], OUT_WORLD)
        if not ex:
            continue
        for c, v in vals.items():
            prev, nxt = v[i - 1], v[i + 1]
            if prev is None and nxt is None:
                continue
            if (prev is None and any(x is not None for x in v[:i])) or (nxt is None and any(x is not None for x in v[i + 1:])):
                continue  # a gap inside the series, not its start or end: no neighbour to compare with on that side
            e = _off(v[i], [prev, nxt], OUT_ROW)
            if not e or e / ex < OUT_PART:
                continue
            u = (usd or {}).get(c)
            if u and u[i] and v[i]:
                uv = [u[j] / v[j] for j in (i - 1, i + 1) if u[j] and v[j]]
                if uv and 1 / UV_SAME <= (u[i] / v[i]) / (sum(uv) / len(uv)) <= UV_SAME:
                    continue  # the declared value moved with the tonnage: a real change, kept as reported
            out.setdefault(c, []).append(i)
    return out


def series(t, name=None):
    """The series of one table, or None when its source has fewer than two years. name: iso -> country name, for the notes."""
    name = name or (lambda c: c)
    years, build = t["_hist"]
    by = {}
    for y in years:
        try:
            r = build(y)
        except FAILED:
            continue
        if r and r.get("rows") and r.get("world"):
            by[y] = r
    if len(by) < 2:
        return None
    ys = sorted(by)
    out = {"u": t["u"], "s": t["s"], "years": ys}
    labels = [str(by[y]["y"]) for y in ys]
    if labels != [str(y) for y in ys]:
        out["labels"] = labels  # PSD market years: "2010/11"
    out["world"] = [by[y]["world"] for y in ys]
    west = [i for i, y in enumerate(ys) if by[y].get("_west")]
    if west:
        out["worldEst"] = west
    if any("worldPublished" in by[y] for y in ys):
        out["pub"] = [by[y].get("worldPublished", by[y]["world"]) for y in ys]
    if any(by[y].get("other") for y in ys):
        out["other"] = [by[y].get("other") for y in ys]
    if t.get("_yl"):
        out["yl"] = [t["_yl"][y] for y in ys]  # what the source says each year is (USGS: the edition's estimates)
    vals, est, src, usd, lab = {}, {}, {}, {}, {}
    for i, y in enumerate(ys):
        for row in by[y]["rows"]:
            vals.setdefault(row["c"], [None] * len(ys))[i] = row["v"]
            if row.get("est"):
                est.setdefault(row["c"], []).append(i)
        for c in sorted(by[y].get("_srcest") or ()):
            if c in vals and vals[c][i] is not None:
                src.setdefault(c, []).append(i)
        for c, u in (by[y].get("_usd") or {}).items():
            usd.setdefault(c, [None] * len(ys))[i] = u
        for c, lb in (by[y].get("_cl") or {}).items():
            if c in vals and vals[c][i] is not None:
                lab.setdefault(c, [None] * len(ys))[i] = lb
    # largest in the latest year first, then the countries that no longer have a figure
    last = len(ys) - 1
    order = sorted(vals, key=lambda c: (-(vals[c][last] or 0), -max(v or 0 for v in vals[c]), c))
    out["c"] = {c: vals[c] for c in order}
    if est:
        out["est"] = est
    if src:
        out["srcEst"] = src
    label = out.get("labels") or [str(y) for y in ys]
    notes = list(t.get("_hn") or [])
    bad = out_of_line(out["world"], vals, usd)
    if bad:
        out["out"] = {c: bad[c] for c in order if c in bad}
        out["worldOut"] = sorted({i for ix in bad.values() for i in ix})
    brk = {}
    # a row whose entity changes (USDA PSD's European Union): its name in each year and a break where it changes
    if lab:
        out["cl"] = lab
        for c, lb in lab.items():
            v = vals[c]
            seg = []  # (label, first index, last index) of the years with a figure
            for i in range(len(ys)):
                if v[i] is None:
                    continue
                if seg and seg[-1][0] == lb[i]:
                    seg[-1][2] = i
                else:
                    seg.append([lb[i], i, i])
            for a, b in zip(seg, seg[1:]):
                brk.setdefault(c, []).append(b[1])
            default = t.get("_clname", {}).get(c, name(c))
            why = t.get("_clwhy", {})
            parts = []
            for lb_, a, b in seg:
                span = label[a] if a == b else (f"from {label[a]}" if b == last else f"{label[a]} to {label[b]}")
                parts.append(f"{lb_ or default}, {span}" + (f", {why[lb_]}" if lb_ in why else ""))
            if len(seg) > 1:
                notes.append(f"The {default} row is the source's own entity, whose membership changes: " + "; ".join(parts)
                             + ". The atlas does not add or remove members: the trend line breaks where the row changes.")
    # countries that split or changed code inside the period (the code list of the source names the last year of the old code)
    for old, (oname, end) in sorted(code_ends().items()):
        new = []
        for c in CODE_CHANGES[old]:
            v = vals.get(c)
            first = next((i for i, x in enumerate(v) if x is not None), None) if v else None
            if first and end <= ys[first] <= end + SPLIT_LAG:
                new.append((c, first))
        if not new:
            continue
        first = min(i for _, i in new)
        names = " and ".join(name(c) for c, _ in new)
        if any(x is not None for x in (vals.get(old) or [])[:first]):  # the old code is a country of the index too (Sudan)
            notes.append(f"{names} {'has' if len(new) == 1 else 'have'} figures of {'its' if len(new) == 1 else 'their'} own from {label[first]}: "
                         f"the source's {oname} up to {end} covers {'it' if len(new) == 1 else 'them'} too.")
            brk.setdefault(old, []).append(first)
        else:
            notes.append(f"{names} {'has' if len(new) == 1 else 'have'} figures of {'its' if len(new) == 1 else 'their'} own from {label[first]}: "
                         f"up to {end} the source gives {oname} as one entity, which is not a country row of the table.")
        for c, i in new:
            brk.setdefault(c, []).append(i)
    # a large country whose figures stop before the last year: the world total of the later years leaves it out
    for c in order:
        v = vals[c]
        lastv = max((i for i, x in enumerate(v) if x is not None), default=None)
        if lastv is None or lastv >= last:
            continue
        ref = next((i for i in range(lastv, -1, -1) if v[i] is not None and i not in bad.get(c, ())), None)
        if ref is None or not out["world"][ref] or v[ref] / out["world"][ref] < COVER_SHARE:
            continue
        notes.append(f"{name(c)} has no figure after {label[lastv]} ({v[ref] / out['world'][ref]:.0%} of the world total in {label[ref]}): "
                     f"the world totals of the later years leave it out.")
    if brk:
        out["brk"] = {c: sorted(set(ix)) for c, ix in brk.items()}
    if notes:
        out["n"] = notes
    return out


def check(t, h):
    """Differences between the latest year of a series and the table (both built by the same function): [] when equal."""
    last = len(h["years"]) - 1
    got = {c: v[last] for c, v in h["c"].items() if v[last] is not None}
    want = {r["c"]: r["v"] for r in t["rows"]}
    bad = [c for c in set(got) | set(want) if got.get(c) != want.get(c)]
    if h["world"][last] != t.get("world"):
        bad.append("world")
    return sorted(bad)


def write_all(docs, out_dir, name=None):
    """Writes one file per commodity that has a series; removes the files of commodities that no longer have one.
    name: iso -> country name, for the series notes. Returns (summary lines for QA.md, mismatches)."""
    os.makedirs(out_dir, exist_ok=True)
    total, written, mism = 0, [], []
    for cid in sorted(docs):
        tabs = {}
        for key, t in _tables(docs[cid]):
            if "_hist" not in t:
                continue
            h = series(t, name)
            if not h:
                continue
            bad = check(t, h)
            if bad:
                mism.append(f"{cid}/{key}: {', '.join(bad[:6])}")
            tabs[key] = h
        path = os.path.join(out_dir, f"{cid}.json")
        if not tabs:
            if os.path.exists(path):
                os.remove(path)
            continue
        txt = json.dumps({"id": cid, "t": tabs}, ensure_ascii=False, separators=(",", ":"))
        with open(path, "w", encoding="utf-8") as f:
            f.write(txt)
        total += len(txt.encode("utf-8"))
        written.append(f"{cid} ({', '.join(f'{k} {h['years'][0]}-{h['years'][-1]}' for k, h in tabs.items())})")
    lines = [f"{len(written)} files, {total / 1e6:.2f} MB in all."] + written
    return lines, mism
