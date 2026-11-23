"""
The vintage of each yearly input, read from the input itself: the one place the builders take a year or an edition
from, so that a new release (USGS MCS in January, BACI once a year, a new USDA marketing year in May) moves every label
with the figures, and no year is written by hand in a builder.

    from common import vintage as V
    V.baci_year()          latest year of the customs cache (pipeline/cache/baci_flows.csv.gz)
    V.usgs_file()          the newest raw/usgs/MCS<yyyy>_Commodities_Data.csv (its tables report year yyyy - 1)
    V.usgs_edition()       yyyy of that file
    V.psd_market_year()    the newest market year most crops have in the USDA PSD file: USDA's forecast of the year in
                           progress (the file holds no later year; PSD adds the next one in May)

A fresh clone has no raw/ folder (the downloads are not in git): the USGS edition is then the one the status file
records for the last download (data/_status/updates.json), and the PSD market year the one the published commodity
pages carry. tests/test_update_jobs.py checks that the published pages name no other edition or year.
"""
import glob
import json
import os
import re
import statistics

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW = os.path.join(ROOT, "raw")
CACHE = os.path.join(ROOT, "pipeline", "cache")
DATA = os.path.join(ROOT, "data")
PSD_FILE = os.path.join(RAW, "usda", "psd_csv", "psd_alldata.csv")
# the crops whose newest market year sets the year of every PSD table (the median, so one early crop does not)
PSD_CROPS = ["Wheat", "Corn", "Oilseed, Soybean", "Rice, Milled", "Cotton", "Sugar, Centrifugal", "Oil, Palm"]
PSD_PAGES = ["wheat", "corn", "soybeans", "rice", "cotton", "sugar", "palm-oil"]


def _status(source):
    try:
        with open(os.path.join(DATA, "_status", "updates.json"), encoding="utf-8") as fh:
            return json.load(fh)["sources"].get(source) or {}
    except (OSError, ValueError, KeyError):
        return {}


def baci_year():
    import pandas as pd

    return int(pd.read_csv(os.path.join(CACHE, "baci_flows.csv.gz"), usecols=["year"])["year"].max())


def usgs_file():
    files = sorted(glob.glob(os.path.join(RAW, "usgs", "MCS*_Commodities_Data.csv")))
    if files:
        return files[-1]
    edition = (_status("usgs-mcs").get("state") or {}).get("year")
    if not edition:
        raise ValueError("no USGS MCS file in raw/usgs and no edition in data/_status/updates.json")
    return os.path.join(RAW, "usgs", f"MCS{int(edition)}_Commodities_Data.csv")


def usgs_edition():
    return int(os.path.basename(usgs_file())[3:7])


def published_psd_year():
    """The market year of the PSD figures of the published crop pages (the median over the crops), or None."""
    years = []
    for page in PSD_PAGES:
        found = []

        def visit(o):
            if isinstance(o, list):
                for x in o:
                    visit(x)
            elif isinstance(o, dict):
                if o.get("s") == "usda-psd" and (m := re.match(r"(\d{4})/\d{2}", str(o.get("y", "")))):
                    found.append(int(m.group(1)))
                for v in o.values():
                    visit(v)
        try:
            with open(os.path.join(DATA, "commodities", page + ".json"), encoding="utf-8") as fh:
                visit(json.load(fh))
        except (OSError, ValueError):
            continue
        if found:
            years.append(max(found))
    return int(statistics.median(years)) if years else None


def psd_market_year():
    if os.path.exists(PSD_FILE):
        import pandas as pd

        x = pd.read_csv(PSD_FILE, usecols=["Commodity_Description", "Market_Year"], encoding="latin-1")
        newest = x[x["Commodity_Description"].isin(PSD_CROPS)].groupby("Commodity_Description")["Market_Year"].max()
        if len(newest):
            return int(newest.median())
    my = published_psd_year()
    if my is None:
        raise ValueError("no USDA PSD file in raw/usda and no PSD figure in the published crop pages")
    return my
