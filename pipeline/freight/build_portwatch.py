"""
Build the weekly chokepoint transit series served by the site from IMF PortWatch daily data.

    python pipeline/freight/build_portwatch.py [pages_dir] [out_dir]

Input   raw/portwatch/chokepoints_daily_page*.json  (ArcGIS query pages; written by fetch_portwatch.py)
        data/freight/chokepoints.json                (maps PortWatch ids to atlas chokepoint ids)
Output  data/freight/portwatch/<chokepoint id>.json  weekly averages of daily vessel counts by type

The same function (``build``) is used by build_freight.py, so the output format is identical.
"""
import glob
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RAW_PAGES = os.path.join(ROOT, "raw", "portwatch")
OUT = os.path.join(ROOT, "data", "freight", "portwatch")


def read_rows(pages_dir=RAW_PAGES):
    """All attribute dicts from the saved pages (empty list when there are none)."""
    rows = []
    for p in sorted(glob.glob(os.path.join(pages_dir, "chokepoints_daily_page*.json")),
                    key=lambda p: int(os.path.basename(p).split("page")[1].split(".")[0])):
        rows += [f["attributes"] for f in json.load(open(p))["features"]]
    return rows


def build(rows, chk, out_dir=OUT):
    """Write one weekly series file per chokepoint in ``chk`` (list of dicts with ``id`` and ``portwatch``).

    Returns the latest date in the data as a string."""
    pw = pd.DataFrame(rows)
    pw["date"] = pd.to_datetime(pw["date"])
    pw["other"] = pw["n_general_cargo"] + pw["n_roro"]
    os.makedirs(out_dir, exist_ok=True)
    ids = {c.get("portwatch"): c["id"] for c in chk if c.get("portwatch")}
    headline = {}
    for pid, g in pw.groupby("portid"):
        if pid not in ids:
            continue
        wk = g.set_index("date").sort_index()[["n_tanker", "n_dry_bulk", "n_container", "other", "n_total", "capacity"]].resample("W-MON", label="left", closed="left").mean().dropna()
        doc = {
            "id": ids[pid], "portwatch": pid, "s": "portwatch", "y": str(g["date"].max().date()), "unit": "vessels/day (weekly average)",
            "start": str(wk.index[0].date()), "step": "week",
            "tanker": [round(x, 1) for x in wk["n_tanker"]], "dry": [round(x, 1) for x in wk["n_dry_bulk"]],
            "container": [round(x, 1) for x in wk["n_container"]], "other": [round(x, 1) for x in wk["other"]],
            "total": [round(x, 1) for x in wk["n_total"]], "dwt": [round(x / 1e6, 2) for x in wk["capacity"]],
        }
        json.dump(doc, open(os.path.join(out_dir, f"{ids[pid]}.json"), "w"), separators=(",", ":"))
        # headline traffic on the chokepoint card: last 28 days, with yearly references
        daily = g.set_index("date").sort_index()["n_total"]
        last = daily.index.max()
        recent = daily[daily.index > last - pd.Timedelta(days=28)].mean()
        refs = []
        for yr in (2023, last.year - 1):
            yv = daily[daily.index.year == yr]
            if len(yv) > 300:
                refs.append(f"{yr} average {yv.mean():.1f}/day")
        headline[ids[pid]] = {"v": round(float(recent), 1), "u": "vessels/day", "y": f"28 days to {last.date()}", "s": "portwatch",
                              "n": "All cargo vessel types, IMF PortWatch daily transits; " + "; ".join(refs)}
    update_headlines(headline, os.path.join(out_dir, "..", "chokepoints.json"))
    print("portwatch series", len(ids), "last date", pw["date"].max().date())
    return str(pw["date"].max().date())


def update_headlines(headline, path):
    """Write the latest traffic figure into data/freight/chokepoints.json (kept in sync weekly).
    A non-PortWatch figure already there (e.g. Panama Canal Authority fiscal-year transits) is kept as `trafficRef`."""
    if not os.path.exists(path):
        return
    chk = json.load(open(path))
    for c in chk:
        h = headline.get(c["id"])
        if not h:
            continue
        old = c.get("traffic")
        if old and old.get("s") != "portwatch":
            c["trafficRef"] = old
        c["traffic"] = h
    json.dump(chk, open(path, "w"), indent=0)


def main():
    pages = sys.argv[1] if len(sys.argv) > 1 else RAW_PAGES
    out = sys.argv[2] if len(sys.argv) > 2 else OUT
    rows = read_rows(pages)
    if not rows:
        sys.exit("no PortWatch pages found in " + pages)
    chk = json.load(open(os.path.join(ROOT, "data", "freight", "chokepoints.json")))
    build(rows, chk, out)


if __name__ == "__main__":
    main()
