"""
Series by country and year of the commodity tables: data/commodities/history/<id>.json (CommodityHistory, web/src/types.ts).

Called from build_commodities.main(). A table writer of build_commodities.py leaves on each table it builds the years its
source has and a function that builds the same table for another year (`_hist`): the same reader, cleaning rules, world
total and estimate marks. Each year is built with it, so the latest year of a series is the table the page shows.

  exports, imports   CEPII BACI, cleaned frame of pipeline/trade/clean.py, HIST_FROM to the latest year
  energy tables      EIA International Energy Data, annual series, HIST_FROM to the year of the table
  agriculture        USDA PSD, market years HIST_FROM/.. to PSD_MY (the year rule of _latest_inputs)
  metals, minerals   USGS MCS: the two years of the file (the year before the edition, as revised, and its estimates)

File (no pretty-printing; values rounded as the tables are):
  {"id", "t": {<table key>: {"u", "s", "years", "labels"?, "world", "worldEst"?, "pub"?, "other"?, "yl"?,
                             "c": {iso: [value or null per year]}, "est"?: {iso: [year index]}, "srcEst"?: {iso: [year index]}}}}
  - `est`: the row is mostly an Atlas estimate that year (tonnage computed from the declared value), as `est` of a table row;
  - `srcEst`: the value is the source's own estimate (USGS "Estimated.");
  - `worldEst`: years whose world total holds a tenth or more of Atlas estimates;
  - `pub`: the published world total where the shares rest on the sum of the lines (`world`); `other`: USGS "Other countries".
A table key is a section of the commodity file (production, exports...) or the `key` of one of its `extra` tables.
"""
import json
import os

FAILED = (KeyError, SystemExit, ValueError, ZeroDivisionError)


def _tables(d):
    for sec in ("production", "refinery", "reserves", "consumption", "exports", "imports"):
        if isinstance(d.get(sec), dict):
            yield sec, d[sec]
    for x in d.get("extra") or []:
        yield x["key"], x["table"]


def series(t):
    """The series of one table, or None when its source has fewer than two years."""
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
    if t["s"] == "usgs-mcs":
        # the edition gives the year before its own as revised figures, and its last year as estimates
        out["yl"] = ["revised" if i < len(ys) - 1 else "estimated" for i in range(len(ys))]
    vals, est, src = {}, {}, {}
    for i, y in enumerate(ys):
        for row in by[y]["rows"]:
            vals.setdefault(row["c"], [None] * len(ys))[i] = row["v"]
            if row.get("est"):
                est.setdefault(row["c"], []).append(i)
        for c in sorted(by[y].get("_srcest") or ()):
            if c in vals and vals[c][i] is not None:
                src.setdefault(c, []).append(i)
    # largest in the latest year first, then the countries that no longer have a figure
    last = len(ys) - 1
    order = sorted(vals, key=lambda c: (-(vals[c][last] or 0), -max(v or 0 for v in vals[c]), c))
    out["c"] = {c: vals[c] for c in order}
    if est:
        out["est"] = est
    if src:
        out["srcEst"] = src
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


def write_all(docs, out_dir):
    """Writes one file per commodity that has a series; removes the files of commodities that no longer have one.
    Returns (summary lines for QA.md, mismatches)."""
    os.makedirs(out_dir, exist_ok=True)
    total, written, mism = 0, [], []
    for cid in sorted(docs):
        tabs = {}
        for key, t in _tables(docs[cid]):
            if "_hist" not in t:
                continue
            h = series(t)
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
