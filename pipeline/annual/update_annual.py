"""
Monthly update of the yearly/monthly sources and of the data built from them
(run by .github/workflows/update-annual.yml around the 15th, after the USDA WASDE).

    python pipeline/annual/update_annual.py [--only usda-psd,usgs-mcs,eia-intl,baci,faostat-wna]
                                            [--no-process] [--baci-check-only]

Sources (each independent; one failure never stops the others; all recorded in data/_status/updates.json)
  usda-psd   USDA PSD bulk zip (monthly)                    -> raw/usda/
  usgs-mcs   USGS Mineral Commodity Summaries data release  -> raw/usgs/   (newest release found with the
             ScienceBase search API, title "Mineral Commodity Summaries <year> Data Release")
  eia-intl   EIA bulk INTL.zip                              -> raw/eia/
  baci       CEPII BACI HS92. The newest BACI_HS92_V<yyyymm>.zip is looked up on the CEPII item/listing page
             and downloaded (2.4 GB, resumable) ONLY when newer than the version recorded in the status file;
             it is then reduced with trade/extract_baci.py into pipeline/cache/baci_flows.csv.gz.
  faostat-wna  pipeline/commodities/fetch_external.py (FAOSTAT cocoa, WNA uranium), at most every 80 days.
Each download is validated (type, size, format, row count not collapsing) before it replaces the previous
file; otherwise the previous good file is kept and the failure is recorded.

Processing chain, run when the inputs it depends on changed (or when its last run failed), each step in its
own try block with a backup of its outputs that is restored on failure:
  build_lanes.py -> build_freight.py ; commodities/build_commodities.py (if present) ; build_profiles.py (if present)
Always exits 0.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import zipfile
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

from common import fetch, status  # noqa: E402

RAW = os.path.join(ROOT, "raw")
CACHE = os.path.join(ROOT, "pipeline", "cache")
PY = sys.executable

PSD_URL = "https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip"
INTL_URL = "https://www.eia.gov/opendata/bulk/INTL.zip"
SB_SEARCH = "https://www.sciencebase.gov/catalog/items"
SB_ITEM = "https://www.sciencebase.gov/catalog/item/"
BACI_BASE = "https://www.cepii.fr/DATA_DOWNLOAD/baci/data/"
BACI_PAGES = ["https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=37", BACI_BASE]
BACI_BASELINE = "V202601"   # version the committed data was built from; assumed when the status file has none
USGS_TITLE = re.compile(r"^(?:U\.S\. Geological Survey )?Mineral Commodity Summaries (\d{4}) Data Release(?: \(ver\.[^)]*\))?$")


# ----------------------------------------------------------------------------- helpers
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def install(src, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(src, dest)


def run(cmd, timeout):
    """Run a command from the repo root; raise RuntimeError (with the last output line) when it fails."""
    print("  $", " ".join(os.path.relpath(c, ROOT) if os.path.isabs(c) and c.startswith(ROOT) else c for c in cmd), flush=True)
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"timed out after {timeout // 60} min")
    print("\n".join(r.stdout.splitlines()[-8:]))
    if r.returncode != 0:
        tail = (r.stderr.strip().splitlines() or r.stdout.strip().splitlines() or ["?"])[-1]
        raise RuntimeError(f"exit {r.returncode}: {tail}"[:200])


class Snapshot:
    """Copy files/folders aside; ``restore()`` puts them back (used when a build step fails)."""

    def __init__(self, paths):
        self.tmp = tempfile.mkdtemp(prefix="snap-")
        self.items = []
        for i, p in enumerate(paths):
            if os.path.exists(p):
                dst = os.path.join(self.tmp, str(i))
                shutil.copytree(p, dst) if os.path.isdir(p) else shutil.copy2(p, dst)
                self.items.append((p, dst))
            else:
                self.items.append((p, None))

    def restore(self):
        for p, dst in self.items:
            if os.path.isdir(p):
                shutil.rmtree(p)
            elif os.path.exists(p):
                os.remove(p)
            if dst is not None:
                shutil.copytree(dst, p) if os.path.isdir(dst) else shutil.copy2(dst, p)

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def ver_tuple(v):
    return int(v.lstrip("V"))


# ----------------------------------------------------------------------------- sources
def src_usda(opts):
    import pandas as pd

    prev = status.get("usda-psd")
    with tempfile.TemporaryDirectory() as tmp:
        z = os.path.join(tmp, "psd_alldata_csv.zip")
        fetch.download(PSD_URL, z, kind="zip", min_bytes=1_000_000)
        digest = sha256(z)
        if digest == prev.get("state", {}).get("sha256") and os.path.exists(os.path.join(RAW, "usda", "psd_csv", "psd_alldata.csv")):
            return {"changed": False, "note": "unchanged"}
        with zipfile.ZipFile(z) as zf:
            if "psd_alldata.csv" not in zf.namelist():
                raise ValueError("psd_alldata.csv missing from the zip")
            zf.extract("psd_alldata.csv", tmp)
        csv_path = os.path.join(tmp, "psd_alldata.csv")
        df = pd.read_csv(csv_path, usecols=["Commodity_Code", "Market_Year", "Value"], dtype=str)
        n = len(df)
        if n < 500_000 or (prev.get("records") and n < 0.9 * prev["records"]):
            raise ValueError(f"only {n} rows (previous {prev.get('records')})")
        to = str(int(pd.to_numeric(df["Market_Year"], errors="coerce").max()))
        install(z, os.path.join(RAW, "usda", "psd_alldata_csv.zip"))
        install(csv_path, os.path.join(RAW, "usda", "psd_csv", "psd_alldata.csv"))
    return {"changed": True, "records": n, "data_to": to, "state": {"sha256": digest}}


def src_usgs(opts):
    import pandas as pd

    prev = status.get("usgs-mcs")
    this_year = datetime.now(timezone.utc).year
    found = None
    for y in range(this_year + 1, 2024, -1):
        doc = fetch.get_json(SB_SEARCH, params={"q": f'"Mineral Commodity Summaries {y} Data Release"', "format": "json",
                                                "max": 20, "fields": "title"})
        hits = [i for i in doc.get("items", []) if (m := USGS_TITLE.match(i.get("title", ""))) and int(m.group(1)) == y]
        if hits:
            found = (y, hits[0]["id"])
            break
    if not found:
        raise ValueError("no 'Mineral Commodity Summaries <year> Data Release' item found")
    year, item_id = found
    item = fetch.get_json(SB_ITEM + item_id, params={"format": "json"})
    files = [f for f in item.get("files", []) if f.get("name", "").lower().endswith(".csv") and f.get("url")]
    main = next((f for f in files if f["name"].endswith("Commodities_Data.csv")), None)
    if not main:
        raise ValueError(f"MCS{year} Commodities_Data.csv not listed in the ScienceBase item")
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, main["name"])
        fetch.download(main["url"], p, kind="csv", min_bytes=100_000)
        digest = sha256(p)
        df = pd.read_csv(p, encoding="latin-1", usecols=["Commodity", "Country", "Statistics", "Year", "Value"])
        n = len(df)
        same_release = prev.get("state", {}).get("item") == item_id
        if n < 2000 or (same_release and prev.get("records") and n < 0.9 * prev["records"]):
            raise ValueError(f"only {n} rows (previous {prev.get('records')})")
        if same_release and digest == prev.get("state", {}).get("sha256") and os.path.exists(os.path.join(RAW, "usgs", main["name"])):
            return {"changed": False, "note": "unchanged"}
        to = str(int(pd.to_numeric(df["Year"], errors="coerce").max()))
        install(p, os.path.join(RAW, "usgs", main["name"]))
        for f in files:  # the small companion tables; failures here are not fatal
            if f is main:
                continue
            try:
                q = os.path.join(tmp, f["name"])
                fetch.download(f["url"], q, kind="csv", min_bytes=10)
                install(q, os.path.join(RAW, "usgs", f["name"]))
            except fetch.FetchError as e:
                print("  companion file skipped:", f["name"], e)
    return {"changed": True, "records": n, "data_to": str(year), "state": {"sha256": digest, "item": item_id, "year": year, "values_to": to}}


def src_eia(opts):
    prev = status.get("eia-intl")
    with tempfile.TemporaryDirectory() as tmp:
        z = os.path.join(tmp, "INTL.zip")
        fetch.download(INTL_URL, z, kind="zip", min_bytes=1_000_000)
        digest = sha256(z)
        if digest == prev.get("state", {}).get("sha256") and os.path.exists(os.path.join(RAW, "eia", "INTL.txt")):
            return {"changed": False, "note": "unchanged"}
        with zipfile.ZipFile(z) as zf:
            if "INTL.txt" not in zf.namelist():
                raise ValueError("INTL.txt missing from the zip")
            zf.extract("INTL.txt", tmp)
        txt = os.path.join(tmp, "INTL.txt")
        n, last = 0, ""
        with open(txt, encoding="utf-8") as fh:
            first = json.loads(fh.readline())
            if "series_id" not in first:
                raise ValueError("first line is not a series record")
            fh.seek(0)
            for line in fh:
                n += 1
                m = re.search(r'"last_updated":"(\d{4}-\d{2}-\d{2})', line)
                if m and m.group(1) > last:
                    last = m.group(1)
        if n < 10_000 or (prev.get("records") and n < 0.9 * prev["records"]):
            raise ValueError(f"only {n} series (previous {prev.get('records')})")
        install(z, os.path.join(RAW, "eia", "INTL.zip"))
        install(txt, os.path.join(RAW, "eia", "INTL.txt"))
    return {"changed": True, "records": n, "data_to": last or None, "state": {"sha256": digest}}


def baci_latest(recorded):
    """Newest BACI HS92 version on the CEPII pages ('V202601'), probing likely names when the pages fail."""
    versions, errors = set(), []
    for page in BACI_PAGES:
        try:
            versions |= set(re.findall(r"BACI_HS92_(V\d{6})\.zip", fetch.get_text(page)))
        except fetch.FetchError as e:
            errors.append(str(e))
    if versions:
        return max(versions, key=ver_tuple)
    # pages unreadable or without links: probe the next plausible versions with HEAD requests
    year = datetime.now(timezone.utc).year
    found = []
    for y in (year, year + 1):
        for mth in range(1, 13):
            v = f"V{y}{mth:02d}"
            if ver_tuple(v) <= ver_tuple(recorded):
                continue
            try:
                fetch.head(BACI_BASE + f"BACI_HS92_{v}.zip", attempts=1)
                found.append(v)
            except fetch.FetchError:
                pass
    if found:
        return max(found, key=ver_tuple)
    if errors:
        raise fetch.FetchError("CEPII pages unreachable: " + errors[0])
    return recorded


def src_baci(opts):
    import pandas as pd

    prev = status.get("baci")
    recorded = prev.get("state", {}).get("version") or BACI_BASELINE
    latest = baci_latest(recorded)
    print(f"  BACI recorded {recorded}, latest {latest}")
    if ver_tuple(latest) <= ver_tuple(recorded):
        if not prev.get("state", {}).get("version"):  # first run: record the baseline
            return {"changed": False, "note": "baseline", "state": {"version": recorded}}
        return {"changed": False, "note": "no newer version", "state": {"version": recorded}}
    if opts.baci_check_only:
        return {"changed": False, "note": f"newer version {latest} available (check only)"}
    name = f"BACI_HS92_{latest}.zip"
    zpath = os.path.join(RAW, "baci", name)
    url = BACI_BASE + name
    size = int(fetch.head(url).get("Content-Length") or 0)
    if not (os.path.exists(zpath) and size and os.path.getsize(zpath) == size):
        fetch.download(url, zpath, kind="zip", min_bytes=500_000_000, resume=True, timeout=(20, 120))
    with zipfile.ZipFile(zpath) as zf:
        names = zf.namelist()
    years = sorted(int(m.group(1)) for n in names if (m := re.fullmatch(r"BACI_HS92_Y(\d{4})_V\d{6}\.csv", n)))
    if len(years) < 25 or not any(n.startswith("country_codes") for n in names):
        raise ValueError(f"unexpected BACI archive layout ({len(years)} yearly files)")
    out = os.path.join(CACHE, "baci_flows.csv.gz.tmp")
    run([PY, os.path.join(ROOT, "pipeline", "trade", "extract_baci.py"), zpath, out, "2000"], 3 * 3600)
    new = pd.read_csv(out, usecols=["year", "t"])
    old_path = os.path.join(CACHE, "baci_flows.csv.gz")
    if os.path.exists(old_path):
        old = pd.read_csv(old_path, usecols=["year", "t"])
        if len(new) < 0.9 * len(old) or new["year"].max() < old["year"].max():
            os.remove(out)
            raise ValueError(f"extract looks wrong: {len(new)} rows to {new['year'].max()} vs {len(old)} to {old['year'].max()}")
    os.replace(out, old_path)
    # paddy and husked rice, kept apart for the milled-equivalent rice flows; a failure here leaves the old file,
    # and build_commodities.py then says that the rice flows stay at customs weight
    try:
        run([PY, os.path.join(ROOT, "pipeline", "commodities", "extract_rice_forms.py"), zpath], 3600)
    except RuntimeError as e:
        print("  rice forms extract failed, rice stays at customs weight:", e)
    return {"changed": True, "records": int(len(new)), "data_to": str(int(new["year"].max())), "state": {"version": latest}}


def src_external(opts):
    """FAOSTAT cocoa and fertiliser + WNA uranium tables used by build_commodities.py (script written by the commodities job)."""
    script = os.path.join(ROOT, "pipeline", "commodities", "fetch_external.py")
    if not os.path.exists(script):
        return {"changed": False, "note": "script absent", "skip": True}
    prev = status.get("faostat-wna")
    last = prev.get("last_success")
    if last and (datetime.now(timezone.utc) - datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).days < 80:
        return {"changed": False, "note": "checked recently", "skip": True}
    files = [os.path.join(CACHE, "wna_uranium.json"), os.path.join(CACHE, "faostat_cocoa_production.csv"), os.path.join(CACHE, "faostat_fertilizer_production.csv")]
    before = [sha256(f) if os.path.exists(f) else None for f in files]
    snap = Snapshot(files)
    try:
        run([PY, script], 1800)
        for f in files:
            if not os.path.exists(f) or os.path.getsize(f) < 200:
                raise ValueError(f"{os.path.basename(f)} missing or empty")
    except Exception:
        snap.restore()
        raise
    finally:
        snap.close()
    after = [sha256(f) for f in files]
    return {"changed": before != after, "note": "updated" if before != after else "unchanged"}


SOURCES = {"usda-psd": src_usda, "usgs-mcs": src_usgs, "eia-intl": src_eia, "baci": src_baci, "faostat-wna": src_external}


# ----------------------------------------------------------------------------- processing chain
def step(name, fn, snapshot_paths):
    """Run one build step with backup/restore and status recording; returns True on success."""
    snap = Snapshot(snapshot_paths)
    try:
        fn()
        status.record_success(name, note="rebuilt")
        print(f"[{name}] ok")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[{name}] FAILED, restoring previous outputs:", e)
        snap.restore()
        status.record_failure(name, str(e) if str(e) else e.__class__.__name__)
        return False
    finally:
        snap.close()


def pending(name):
    return int(status.get(name).get("consecutive_failures") or 0) > 0


def process(changed):
    data = os.path.join(ROOT, "data")
    sources_json = os.path.join(data, "sources.json")
    chain = []
    if "baci" in changed or pending("build-freight"):
        def freight():
            run([PY, os.path.join(ROOT, "pipeline", "freight", "build_lanes.py")], 3 * 3600)
            run([PY, os.path.join(ROOT, "pipeline", "freight", "build_freight.py")], 3600)
        chain.append(("build-freight", freight, [os.path.join(data, "freight"), sources_json,
                                                os.path.join(CACHE, "seaborne_totals.json"), os.path.join(CACHE, "geom_cache.json"),
                                                os.path.join(CACHE, "sea_flows.csv.gz")]))
    commodities = os.path.join(ROOT, "pipeline", "commodities", "build_commodities.py")
    if os.path.exists(commodities) and (changed or pending("build-commodities")):
        chain.append(("build-commodities", lambda: run([PY, commodities], 3600),
                      [os.path.join(data, "commodities"), sources_json]))
    profiles = (glob.glob(os.path.join(ROOT, "pipeline", "**", "build_profiles.py"), recursive=True) or [None])[0]
    if profiles and (changed or pending("build-profiles")):
        chain.append(("build-profiles", lambda: run([PY, profiles], 3600),
                      [os.path.join(data, "countries"), sources_json]))
    for name, fn, paths in chain:
        step(name, fn, paths)


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--only", default="", help="comma-separated source ids")
    ap.add_argument("--no-process", action="store_true", help="download only, do not rebuild")
    ap.add_argument("--baci-check-only", action="store_true", help="look for a newer BACI version but do not download")
    opts = ap.parse_args()
    wanted = [s for s in SOURCES if not opts.only or s in opts.only.split(",")]
    changed = set()
    for sid in wanted:
        print(f"== {sid}", flush=True)
        try:
            res = SOURCES[sid](opts)
            if res.get("skip"):
                print("  skipped:", res.get("note"))
                continue
            status.record_success(sid, records=res.get("records"), data_to=res.get("data_to"),
                                  note=res.get("note", "updated"), state=res.get("state"))
            if res["changed"]:
                changed.add(sid)
            print("  ok:", res.get("note", "updated"))
        except Exception as e:  # noqa: BLE001
            if not isinstance(e, (fetch.FetchError, ValueError, RuntimeError)):
                traceback.print_exc()
            status.record_failure(sid, str(e) or e.__class__.__name__)
            print("  FAILED, previous files kept:", e)
    if not opts.no_process:
        try:
            process(changed)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    print("changed:", sorted(changed) or "nothing")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        pass
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    sys.exit(0)
