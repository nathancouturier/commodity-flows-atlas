"""
Build the weekly chokepoint transit series served by the site from IMF PortWatch daily data.

    python pipeline/freight/build_portwatch.py [pages_dir] [out_dir]

Input   pipeline/cache/portwatch/daily_<year>.csv.gz (the daily table, one file per year; kept by fetch_portwatch.py,
                                                     which downloads only the days after the last one stored)
        raw/portwatch/chokepoints_daily_page*.json  (ArcGIS query pages: a local mirror, used when there is no cache)
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
import csv
import glob
import gzip
import io
import json
import math
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RAW_PAGES = os.path.join(ROOT, "raw", "portwatch")
CACHE_DIR = os.path.join(ROOT, "pipeline", "cache", "portwatch")
OUT = os.path.join(ROOT, "data", "freight", "portwatch")
DATA_CHK = os.path.join(ROOT, "data", "freight", "chokepoints.json")

# the five vessel types PortWatch counts; the site draws general cargo and ro-ro together as "other"
VESSELS = "Tankers, dry bulk, container, general cargo and ro-ro"
COUNT = {"tanker": "n_tanker", "dry": "n_dry_bulk", "container": "n_container", "other": "other", "total": "n_total"}
VOLUME = {"tanker": "capacity_tanker", "dry": "capacity_dry_bulk", "container": "capacity_container",
          "other": "capacity_other", "total": "capacity"}
# the fields of the daily table the atlas keeps (the cache and the page checks of fetch_portwatch.py)
FIELDS = ["date", "portid", "portname", "n_tanker", "n_dry_bulk", "n_container", "n_general_cargo", "n_roro", "n_total",
          "capacity_tanker", "capacity_dry_bulk", "capacity_container", "capacity_general_cargo", "capacity_roro", "capacity"]
TEXT_FIELDS = {"date", "portid", "portname"}
# the headline and the comparison of a chokepoint cover this many days; the reference year is the last full year before
# every disruption the atlas lists (the Red Sea diversions start in December 2023)
WINDOW_DAYS = 28
REFERENCE_YEAR = 2023


def read_pages(pages_dir=RAW_PAGES):
    """All attribute dicts from saved ArcGIS pages (empty list when there are none)."""
    rows = []
    for p in sorted(glob.glob(os.path.join(pages_dir, "chokepoints_daily_page*.json")),
                    key=lambda p: int(os.path.basename(p).split("page")[1].split(".")[0])):
        rows += [f["attributes"] for f in json.load(open(p))["features"]]
    return rows


def read_cache(cache_dir=CACHE_DIR):
    """The daily table kept between runs (rows as dicts of FIELDS, oldest first); empty when there is no cache."""
    rows = []
    for p in sorted(glob.glob(os.path.join(cache_dir, "daily_*.csv.gz"))):
        with gzip.open(p, "rt", encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                rows.append({k: (v if k in TEXT_FIELDS else (int(v) if v != "" else None)) for k, v in r.items()})
    return rows


def write_cache(rows, cache_dir=CACHE_DIR):
    """Write the daily table, one file per year, sorted and without a timestamp in the archive, so that a year
    that did not change gives byte-identical files and no change in git."""
    by_year = {}
    for r in rows:
        by_year.setdefault(r["date"][:4], []).append(r)
    os.makedirs(cache_dir, exist_ok=True)
    for y, rs in by_year.items():
        rs.sort(key=lambda r: (r["date"], r["portid"]))
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(FIELDS)
        for r in rs:
            w.writerow(["" if r.get(k) is None else r[k] for k in FIELDS])
        path = os.path.join(cache_dir, f"daily_{y}.csv.gz")
        tmp = path + ".tmp"
        with open(tmp, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, compresslevel=9) as gz:
            gz.write(buf.getvalue().encode("utf-8"))
        os.replace(tmp, path)
    for p in glob.glob(os.path.join(cache_dir, "daily_*.csv.gz")):
        if os.path.basename(p)[6:10] not in by_year:
            os.remove(p)


def merge_days(old, new):
    """``old`` with the days of ``new`` added or replaced: one row per (date, portid), the newer row wins (PortWatch
    revises its latest days). Rows are cut to FIELDS and sorted."""
    out = {}
    for rows in (old, new):
        for r in rows:
            out[(r["date"], r["portid"])] = {k: r.get(k) for k in FIELDS}
    return [out[k] for k in sorted(out)]


def read_rows(pages_dir=None):
    """The daily rows: the cache, or the saved pages of ``pages_dir`` (default raw/portwatch) when there is no cache or
    when a folder is given. Empty list when neither exists."""
    if pages_dir is None:
        return read_cache() or read_pages(RAW_PAGES)
    return read_pages(pages_dir)


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


def _decimals(v, digits):
    """Decimals to keep: a fixed number, or (digits=None) three significant figures of the value itself,
    so a small recent value keeps its precision whatever the history of the series."""
    if digits is not None:
        return digits
    return 3 if v == 0 else max(2, 2 - int(math.floor(math.log10(abs(v)))))


def _headline(daily, unit, ref_unit, digits, text):
    """Last 28 days of a daily series, with the 2023 and previous-year averages as references."""
    last = daily.index.max()
    recent = float(daily[daily.index > last - pd.Timedelta(days=28)].mean())
    refs = []
    for yr in (2023, last.year - 1):
        yv = daily[daily.index.year == yr]
        if len(yv) > 300:
            m = float(yv.mean())
            refs.append(f"{yr} average {m:.{_decimals(m, digits)}f}{ref_unit}")
    return {"v": round(recent, _decimals(recent, digits)), "u": unit, "y": f"28 days to {last.date()}", "s": "portwatch",
            "n": "; ".join([text] + refs)}


def _window(s, end, days):
    """Sum of a daily series over the ``days`` days ending on ``end`` (included); None when a day is missing."""
    w = s[(s.index > end - pd.Timedelta(days=days)) & (s.index <= end)]
    return float(w.sum()) if len(w) == days else None


def compare(day):
    """What the alerts and the weekly digest compare, from the daily table of one chokepoint (``day``: DataFrame indexed by
    date with n_total and capacity). Transits and estimated tonnes (Mt) over the last WINDOW_DAYS days, over the same days
    a year earlier (364 days back, the same weekdays) and the average of REFERENCE_YEAR scaled to the same length; and the
    daily average of the last 7 days against the 28 and 365 days before them. A value is None when its days are not all
    in the table."""
    last = day.index.max()
    n, mt = day["n_total"], day["capacity"] / 1e6
    year_ago = last - pd.Timedelta(days=364)
    ref = day[day.index.year == REFERENCE_YEAR]
    complete = len(ref) >= 365

    def block(s, nd):
        now, ago = _window(s, last, WINDOW_DAYS), _window(s, year_ago, WINDOW_DAYS)
        return {"now": None if now is None else round(now, nd), "yearAgo": None if ago is None else round(ago, nd),
                "avg2023": round(float(s[s.index.year == REFERENCE_YEAR].mean()) * WINDOW_DAYS, nd) if complete else None}

    def per_day(s, end, days):
        v = _window(s, end, days)
        return None if v is None else round(v / days, 2)

    before = last - pd.Timedelta(days=7)
    return {"to": str(last.date()), "days": WINDOW_DAYS, "yearAgoTo": str(year_ago.date()), "refYear": REFERENCE_YEAR,
            "transits": block(n, 0), "mt": block(mt, 2),
            "perDay": {"week": per_day(n, last, 7), "prior28": per_day(n, before, 28), "prior365": per_day(n, before, 365)}}


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
    unmapped = sorted(set(pw["portid"]) - set(ids))
    if unmapped:
        # no failure: a counter PortWatch adds is only noted in the log until it gets a record in chokepoints.json
        print("warning: PortWatch ids without a chokepoint record, not published:", ", ".join(map(str, unmapped)))
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
        doc["headlineVol"] = _headline(day["capacity"] / 1e6, "Mt/day", " Mt/day", None,
                                       "Estimated trade volume of the vessels counted (IMF PortWatch estimate, not a customs statistic)")
        doc["compare"] = compare(day)
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
    pages = sys.argv[1] if len(sys.argv) > 1 else None
    out = sys.argv[2] if len(sys.argv) > 2 else OUT
    rows = read_rows(pages)
    if not rows:
        sys.exit("no PortWatch data found in " + (pages or CACHE_DIR))
    chk = json.load(open(DATA_CHK))
    build(rows, chk, out)
    if os.path.abspath(out) == os.path.abspath(OUT):
        print("headlines", update_headlines())


if __name__ == "__main__":
    main()
