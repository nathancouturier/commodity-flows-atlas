"""
Fetch the IMF PortWatch daily chokepoint transits and rebuild data/freight/portwatch/ (weekly, Wednesday).

    python pipeline/freight/fetch_portwatch.py

Source  ArcGIS feature service Daily_Chokepoints_Data (services9.arcgis.com/weJ1QsnbMYJlCHdG), paged
        2000 records at a time ordered by ObjectId, 1-2 s pause between pages.
Validation  record count not lower than 95% of the previous run, latest date not older than the
        previous run's, every page well formed. Only then are raw/portwatch/*.json pages replaced and
        build_portwatch.py run (into a temporary folder, then moved into data/freight/portwatch/).

Always exits 0: a failure is recorded in data/_status/updates.json and the previous files are kept.
"""
import glob
import json
import os
import random
import shutil
import sys
import tempfile
import time
import traceback

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "freight"))

from common import fetch, status  # noqa: E402

SOURCE = "portwatch"
URL = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query"
PAGE = 2000
MAX_PAGES = 200
RAW = os.path.join(ROOT, "raw", "portwatch")
OUT = os.path.join(ROOT, "data", "freight", "portwatch")
NEEDED = {"date", "portid", "n_tanker", "n_dry_bulk", "n_container", "n_general_cargo", "n_roro", "n_total", "capacity"}


def fetch_pages(stage):
    """Download all pages into ``stage``; returns (record count, latest date)."""
    total, latest, offset, n = 0, "", 0, 0
    while n < MAX_PAGES:
        n += 1
        doc = fetch.get_json(URL, params={
            "where": "1=1", "outFields": "*", "f": "json", "orderByFields": "ObjectId",
            "resultOffset": offset, "resultRecordCount": PAGE,
        })
        feats = doc.get("features")
        if not isinstance(feats, list):
            raise fetch.FetchError("page without features")
        if feats:
            attrs = feats[0].get("attributes", {})
            if not NEEDED <= set(attrs):
                raise fetch.FetchError("unexpected fields: missing " + ",".join(sorted(NEEDED - set(attrs))))
            latest = max(latest, max(f["attributes"]["date"] for f in feats))
            with open(os.path.join(stage, f"chokepoints_daily_page{n}.json"), "w") as fh:
                json.dump({"features": feats, "exceededTransferLimit": bool(doc.get("exceededTransferLimit"))}, fh,
                          separators=(",", ":"))
        total += len(feats)
        offset += len(feats)
        if not feats or not doc.get("exceededTransferLimit"):
            break
        time.sleep(random.uniform(1.0, 2.0))
    else:
        raise fetch.FetchError("too many pages")
    return total, latest


def main():
    prev = status.get(SOURCE)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            stage = os.path.join(tmp, "pages")
            built = os.path.join(tmp, "built")
            os.makedirs(stage)
            total, latest = fetch_pages(stage)
            print(f"  {total} records, latest {latest}")
            if total < 1000:
                raise fetch.FetchError(f"only {total} records")
            if prev.get("records") and total < 0.95 * prev["records"]:
                raise fetch.FetchError(f"record count {total} is below 95% of previous {prev['records']}")
            if prev.get("data_to") and latest < prev["data_to"]:
                raise fetch.FetchError(f"latest date {latest} is older than previous {prev['data_to']}")
            import build_portwatch as BW

            chk = json.load(open(os.path.join(ROOT, "data", "freight", "chokepoints.json")))
            rows = BW.read_rows(stage)
            if len(rows) != total:
                raise fetch.FetchError("page files do not match the record count")
            BW.build(rows, chk, built)
            if len(glob.glob(os.path.join(built, "*.json"))) < 10:
                raise fetch.FetchError("too few chokepoint series built")
            # all good: replace raw pages, then the data files
            os.makedirs(RAW, exist_ok=True)
            for old in glob.glob(os.path.join(RAW, "chokepoints_daily_page*.json")):
                os.remove(old)
            for p in glob.glob(os.path.join(stage, "*.json")):
                shutil.copy2(p, os.path.join(RAW, os.path.basename(p)))
            os.makedirs(OUT, exist_ok=True)
            for p in glob.glob(os.path.join(built, "*.json")):
                shutil.copy2(p, os.path.join(OUT, os.path.basename(p)))
        status.record_success(SOURCE, records=total, data_to=latest)
        print("done: updated")
    except Exception as e:  # noqa: BLE001
        if not isinstance(e, fetch.FetchError):
            traceback.print_exc()
        status.record_failure(SOURCE, e if isinstance(e, fetch.FetchError) else f"{e.__class__.__name__}: {e}")
        print("failed, previous data kept:", e)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    sys.exit(0)
