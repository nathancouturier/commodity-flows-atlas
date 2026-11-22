"""
Build the weekly chokepoint transit series served by the site from IMF PortWatch daily data.

    python pipeline/freight/build_portwatch.py [pages_dir] [out_dir]

Input   raw/portwatch/chokepoints_daily_page*.json  (ArcGIS query pages; written by fetch_portwatch.py)
        data/freight/chokepoints.json                (maps PortWatch ids to atlas chokepoint ids)
Output  data/freight/portwatch/<chokepoint id>.json  weekly averages of daily vessel counts and of
                                                     PortWatch's estimated trade volume, by vessel type,
                                                     plus the headline figures of the chokepoint card
        data/freight/chokepoints.json                ``traffic`` / ``trafficVol`` refreshed from those files

The same functions are used by build_freight.py and fetch_portwatch.py, so the output is identical.
The headline figures live in the series files (tracked in git) and every job copies them from there
into chokepoints.json (``apply_headlines``): a rebuild on a machine without raw/ cannot lose them.

PortWatch fields: ``n_*`` are daily transit counts by vessel type; ``capacity_*`` are PortWatch's
estimate of the trade volume carried, in tonnes (not deadweight). ``n_total`` and ``capacity`` are the
sums over the five types (container, dry bulk, general cargo, ro-ro, tanker).
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
DATA_CHK = os.path.join(ROOT, "data", "freight", "chokepoints.json")

# the five vessel types PortWatch counts; the site draws general cargo and ro-ro together as "other"
VESSELS = "Tankers, dry bulk, container, general cargo and ro-ro"
COUNT = {"tanker": "n_tanker", "dry": "n_dry_bulk", "container": "n_container", "other": "other", "total": "n_total"}
VOLUME = {"tanker": "capacity_tanker", "dry": "capacity_dry_bulk", "container": "capacity_container",
          "other": "capacity_other", "total": "capacity"}


def read_rows(pages_dir=RAW_PAGES):
    """All attribute dicts from the saved pages (empty list when there are none)."""
    rows = []
    for p in sorted(glob.glob(os.path.join(pages_dir, "chokepoints_daily_page*.json")),
                    key=lambda p: int(os.path.basename(p).split("page")[1].split(".")[0])):
        rows += [f["attributes"] for f in json.load(open(p))["features"]]
    return rows


def mapped(chk):
    """PortWatch id -> atlas chokepoint id. One PortWatch counter belongs to one chokepoint only:
    two records sharing an id would silently overwrite each other's series."""
    ids = {}
    for c in chk:
        pid = c.get("portwatch")
        if not pid:
            continue
        if pid in ids:
            raise ValueError(f"PortWatch {pid} is mapped to both {ids[pid]} and {c['id']}")
        ids[pid] = c["id"]
    return ids


def _headline(daily, unit, ref_unit, digits, text):
    """Last 28 days of a daily series, with the 2023 and previous-year averages as references."""
    last = daily.index.max()
    recent = daily[daily.index > last - pd.Timedelta(days=28)].mean()
    refs = []
    for yr in (2023, last.year - 1):
        yv = daily[daily.index.year == yr]
        if len(yv) > 300:
            refs.append(f"{yr} average {yv.mean():.{digits}f}{ref_unit}")
    return {"v": round(float(recent), digits), "u": unit, "y": f"28 days to {last.date()}", "s": "portwatch",
            "n": "; ".join([text] + refs)}


def build(rows, chk, out_dir=OUT):
    """Write one weekly series file per chokepoint in ``chk`` (list of dicts with ``id`` and ``portwatch``)
    and delete the files of chokepoints that no longer have a PortWatch counter.

    Returns the latest date in the data as a string."""
    pw = pd.DataFrame(rows)
    pw["date"] = pd.to_datetime(pw["date"])
    pw["other"] = pw["n_general_cargo"] + pw["n_roro"]
    pw["capacity_other"] = pw["capacity_general_cargo"] + pw["capacity_roro"]
    os.makedirs(out_dir, exist_ok=True)
    ids = mapped(chk)
    for pid, g in pw.groupby("portid"):
        if pid not in ids:
            continue
        day = g.set_index("date").sort_index()
        wk = day[list(COUNT.values()) + list(VOLUME.values())].resample("W-MON", label="left", closed="left").mean().dropna()
        years = [int(y) for y, n in day.groupby(day.index.year).size().items() if n >= 365]
        doc = {
            "id": ids[pid], "portwatch": pid, "name": str(day["portname"].iloc[-1]), "s": "portwatch", "y": str(g["date"].max().date()),
            "unit": "vessels/day (weekly average)", "start": str(wk.index[0].date()), "step": "week",
        }
        for k, col in COUNT.items():
            doc[k] = [round(x, 1) for x in wk[col]]
        # PortWatch's estimated trade volume of the transiting vessels, million tonnes a day
        doc["vol"] = {"unit": "Mt/day (weekly average)", **{k: [round(x / 1e6, 4) for x in wk[col]] for k, col in VOLUME.items()}}
        # complete calendar years: transits and estimated trade volume
        doc["annual"] = {"years": years,
                         "transits": [int(day.loc[day.index.year == y, "n_total"].sum()) for y in years],
                         "mt": [round(float(day.loc[day.index.year == y, "capacity"].sum()) / 1e6, 1) for y in years]}
        # headline traffic on the chokepoint card: last 28 days, with yearly references
        doc["headline"] = _headline(day["n_total"], "vessels/day", "/day", 1, VESSELS + " (IMF PortWatch daily transits)")
        doc["headlineVol"] = _headline(day["capacity"] / 1e6, "Mt/day", " Mt/day", 3 if day["capacity"].mean() < 1e6 else 2,
                                       "Estimated trade volume of the vessels counted (IMF PortWatch estimate, not a customs statistic)")
        json.dump(doc, open(os.path.join(out_dir, f"{ids[pid]}.json"), "w"), separators=(",", ":"))
    prune(out_dir, chk)
    print("portwatch series", len(ids), "last date", pw["date"].max().date())
    return str(pw["date"].max().date())


def prune(out_dir, chk):
    """Remove the series of chokepoints that have no PortWatch counter (any more)."""
    keep = set(mapped(chk).values())
    for p in glob.glob(os.path.join(out_dir, "*.json")):
        if os.path.basename(p)[:-5] not in keep:
            os.remove(p)


def apply_headlines(chk, series_dir=OUT):
    """Copy the latest traffic figures from the weekly series files into the chokepoint records.

    The series files are the only place the PortWatch headline is stored, so chokepoints.json gets the
    same figures whichever job writes it. A non-PortWatch figure (e.g. Panama Canal Authority
    fiscal-year transits) is kept as ``trafficRef``. Returns the number of records updated."""
    n = 0
    for c in chk:
        old = c.get("traffic")
        if old and old.get("s") != "portwatch":
            c["trafficRef"] = c.pop("traffic")
        p = os.path.join(series_dir, f"{c['id']}.json")
        doc = json.load(open(p)) if c.get("portwatch") and os.path.exists(p) else None
        if not doc or doc.get("portwatch") != c["portwatch"] or "headline" not in doc:
            # no series for this record: a PortWatch figure left on it would belong to another counter or be stale
            for k in ("traffic", "trafficVol", "portwatchName"):
                c.pop(k, None)
            continue
        c["traffic"] = doc["headline"]
        c["trafficVol"] = doc["headlineVol"]
        c["portwatchName"] = doc["name"]  # PortWatch's own name for the counter
        n += 1
    return n


def update_headlines(path=DATA_CHK, series_dir=OUT):
    """Refresh the traffic figures of data/freight/chokepoints.json from the series files (weekly job)."""
    if not os.path.exists(path):
        return 0
    chk = json.load(open(path))
    n = apply_headlines(chk, series_dir)
    json.dump(chk, open(path, "w"), indent=0)
    return n


def main():
    pages = sys.argv[1] if len(sys.argv) > 1 else RAW_PAGES
    out = sys.argv[2] if len(sys.argv) > 2 else OUT
    rows = read_rows(pages)
    if not rows:
        sys.exit("no PortWatch pages found in " + pages)
    chk = json.load(open(DATA_CHK))
    build(rows, chk, out)
    if os.path.abspath(out) == os.path.abspath(OUT):
        print("headlines", update_headlines())


if __name__ == "__main__":
    main()
