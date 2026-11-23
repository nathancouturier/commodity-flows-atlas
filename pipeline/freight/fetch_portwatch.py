"""
Fetch the IMF PortWatch daily chokepoint transits and rebuild data/freight/portwatch/ (weekly, Wednesday).

    python pipeline/freight/fetch_portwatch.py

Source  ArcGIS feature service Daily_Chokepoints_Data (services9.arcgis.com/weJ1QsnbMYJlCHdG), paged
        2000 records at a time (the service allows 10,000) ordered by ObjectId, 1-2 s pause between pages.
Incremental  the daily table is kept between runs in pipeline/cache/portwatch/ (one file per year, tracked in git:
        the runners of GitHub keep nothing else). A run asks only for the days after the last one stored, minus
        OVERLAP_DAYS days that PortWatch may revise (about 400 records, one page), and replaces those days. Every
        FULL_EVERY_DAYS days (about once a month) it asks for the whole table again, which also picks up any older
        revision. The date of the last full download is kept in the "state" of the status file.
Validation  a page without the expected fields stops the run; the table after the merge must not have fewer records
        than 95% of the previous run's, nor end earlier; a full download of fewer than 1000 records is refused.
        Only then are the cache, the series files (built into a temporary folder, then moved into
        data/freight/portwatch/) and the traffic figures of data/freight/chokepoints.json replaced.
        raw/portwatch/*.json, a local mirror, is rewritten only on a machine that already has that folder.

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
from datetime import date, timedelta

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
CHK = os.path.join(ROOT, "data", "freight", "chokepoints.json")
NEEDED = {"date", "portid", "portname", "n_tanker", "n_dry_bulk", "n_container", "n_general_cargo", "n_roro", "n_total",
          "capacity_tanker", "capacity_dry_bulk", "capacity_container", "capacity_general_cargo", "capacity_roro", "capacity"}
OVERLAP_DAYS = 14
FULL_EVERY_DAYS = 28


def plan(has_cache, full_on, last_date, today):
    """("full", where) or ("incremental", where): ``full_on`` is the date of the last full download (ISO, or None),
    ``last_date`` the latest day in the cache. A run with no cache, no known full download, or a full download
    FULL_EVERY_DAYS days old or more, takes the whole table."""
    if not has_cache or not last_date or not full_on or (today - date.fromisoformat(full_on)).days >= FULL_EVERY_DAYS:
        return "full", "1=1"
    since = date.fromisoformat(last_date) - timedelta(days=OVERLAP_DAYS)
    return "incremental", f"date > '{since.isoformat()}'"


def fetch_rows(where):
    """Download the records matching ``where``; returns them as dicts of the fields the atlas keeps."""
    rows, offset, n = [], 0, 0
    while n < MAX_PAGES:
        n += 1
        doc = fetch.get_json(URL, params={
            "where": where, "outFields": "*", "f": "json", "orderByFields": "ObjectId",
            "resultOffset": offset, "resultRecordCount": PAGE,
        })
        feats = doc.get("features")
        if not isinstance(feats, list):
            raise fetch.FetchError("page without features")
        if feats:
            attrs = feats[0].get("attributes", {})
            if not NEEDED <= set(attrs):
                raise fetch.FetchError("unexpected fields: missing " + ",".join(sorted(NEEDED - set(attrs))))
            rows += [f["attributes"] for f in feats]
        offset += len(feats)
        if not feats or not doc.get("exceededTransferLimit"):
            break
        time.sleep(random.uniform(1.0, 2.0))
    else:
        raise fetch.FetchError("too many pages")
    return rows


def write_mirror(rows):
    """Rewrite raw/portwatch/ (the pages other local scripts read) from the merged table, on a machine that has it."""
    if not os.path.isdir(RAW):
        return
    for old in glob.glob(os.path.join(RAW, "chokepoints_daily_page*.json")):
        os.remove(old)
    for i in range(0, len(rows), PAGE):
        feats = [{"attributes": {**r, "year": int(r["date"][:4])}} for r in rows[i:i + PAGE]]
        with open(os.path.join(RAW, f"chokepoints_daily_page{i // PAGE + 1}.json"), "w") as fh:
            json.dump({"features": feats, "exceededTransferLimit": i + PAGE < len(rows)}, fh, separators=(",", ":"))


def main():
    import build_portwatch as BW

    prev = status.get(SOURCE)
    try:
        stored = BW.read_cache()
        # runs before the cache existed were all full downloads: their date counts as the last full one
        full_on = (prev.get("state") or {}).get("full_refresh") or (prev.get("last_success") or "")[:10] or None
        last_stored = max((r["date"] for r in stored), default=None)
        mode, where = plan(bool(stored), full_on, last_stored, date.today())
        print(f"  {mode} download: where {where}")
        with tempfile.TemporaryDirectory() as tmp:
            built = os.path.join(tmp, "built")
            new = fetch_rows(where)
            print(f"  {len(new)} records downloaded")
            if mode == "full":
                if len(new) < 1000:
                    raise fetch.FetchError(f"only {len(new)} records")
                rows = BW.merge_days([], new)
            else:
                if not new:
                    raise fetch.FetchError("no record returned for the days after the last one stored")
                rows = BW.merge_days(stored, new)
            total, latest = len(rows), max(r["date"] for r in rows)
            print(f"  {total} records, latest {latest}")
            if prev.get("records") and total < 0.95 * prev["records"]:
                raise fetch.FetchError(f"record count {total} is below 95% of previous {prev['records']}")
            if prev.get("data_to") and latest < prev["data_to"]:
                raise fetch.FetchError(f"latest date {latest} is older than previous {prev['data_to']}")
            chk = json.load(open(CHK))
            BW.build(rows, chk, built)
            wanted = len(BW.mapped(chk))
            if len(glob.glob(os.path.join(built, "*.json"))) < max(10, 0.9 * wanted):
                raise fetch.FetchError(f"too few chokepoint series built (of {wanted} mapped)")
            # all good: replace the cache, then the data files
            BW.write_cache(rows)
            write_mirror(rows)
            os.makedirs(OUT, exist_ok=True)
            for p in glob.glob(os.path.join(built, "*.json")):
                shutil.copy2(p, os.path.join(OUT, os.path.basename(p)))
            BW.prune(OUT, chk)
            # the chokepoint cards read their traffic figures from chokepoints.json: refresh them from the new series
            BW.update_headlines()
        status.record_success(SOURCE, records=total, data_to=latest,
                              state={"full_refresh": date.today().isoformat() if mode == "full" else full_on,
                                     "mode": mode, "downloaded": len(new)})
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
