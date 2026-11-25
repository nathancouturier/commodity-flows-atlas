"""
Monthly update of the yearly/monthly sources and of the data built from them
(run by .github/workflows/update-annual.yml around the 15th, after the USDA WASDE).

    python pipeline/annual/update_annual.py [--only usda-psd,usgs-mcs,eia-intl,baci,faostat-wna]
                                            [--no-process] [--baci-check-only]

The scheduled job runs it with --baci-check-only: the BACI refresh (a 2.4 GB download from a site that has refused a
cloud runner) is done by hand on a local machine once a year (docs/UPDATING.md); the job only reads the version CEPII
lists and records it as "available" in the status of "baci", which opens a "New release available: baci" issue.

Sources (each independent; one failure never stops the others; all recorded in data/_status/updates.json)
  usda-psd   USDA PSD bulk zip (monthly)                    -> raw/usda/
  usgs-mcs   USGS Mineral Commodity Summaries data release  -> raw/usgs/   (newest release found with the
             ScienceBase search API, title "Mineral Commodity Summaries <year> Data Release")
  eia-intl   EIA bulk INTL.zip                              -> raw/eia/
  baci       CEPII BACI HS92. The newest BACI_HS92_V<yyyymm>.zip is looked up on the CEPII item/listing page
             and downloaded (2.4 GB, resumable) ONLY when newer than the version recorded in the status file;
             it is then reduced with trade/extract_baci.py into pipeline/cache/baci_flows.csv.gz, and with
             trade/extract_hs4.py into the HS4 tables of the country profiles (pipeline/cache/hs4_*).
  faostat-wna  pipeline/commodities/fetch_external.py (FAOSTAT cocoa and EU member-state crops, WNA uranium), at most every 80 days.
Each download is validated (type, size, format, row count not collapsing, the columns, commodities and series the
builders read: common/inputs.py) before it replaces the previous file; otherwise the previous good file is kept and the
failure is recorded. Each source has its own time limit (SOURCE_MIN), so that one hung download cannot use the time of
the others and of the rebuild.

Processing chain, run when the inputs it depends on changed (or when its last run failed), each step in its
own try block with a backup of its outputs that is restored on failure:
  geo/adjacency.py -> build_lanes.py -> build_freight.py ; commodities/build_commodities.py (if present) ;
  commodities/build_coverage.py (after any step above ran, or when its last run failed) ;
  build_profiles.py (if present) ; prices/build_prices.py (after a new USGS edition: its annual prices)
The coverage matrix (data/coverage.json) follows the pages and rests on two hand-typed tables, which never stop the update:
a typed reason that the data now contradict is a warning of the run (the data win), a failed step keeps the previous file, and
the file is kept only when it has its shape (web/scripts/validate-coverage.mjs). A page that lost a block it had is refused
by the guard of the finish action (web/scripts/guard-data.mjs), which "accept large moves" overrides.
When the freight step fails after a new BACI cache was installed, the old cache is put back, the version it was
built from is the one recorded again, and the two steps that depend on the lanes do not run (each is recorded as
failed, so that the next run runs it): the commodity pages never rest on a customs cache that the lanes do not.
No check result raises: checks are written to pipeline/cache/trade_checks.json and QA.md only.
Always exits 0.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import traceback
import zipfile
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

from common import fetch, inputs, status  # noqa: E402

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


def on_disk(path, digest):
    """True when ``path`` exists with this sha256. A source counts as unchanged only when the file the builders read is
    the one just downloaded, not merely when the status file says so: raw/ comes back from the artifact of an earlier
    run (restore_raw.py), which may be older than the last recorded download when an upload failed."""
    return os.path.exists(path) and sha256(path) == digest


def install(src, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(src, dest)


# Time limit of each command, in minutes. Their sum (182) stays under the workflow step's 205 minutes, so that the
# downloads keep about 30 minutes and a command that runs long is stopped here, its outputs restored by its Snapshot,
# before the workflow stops the whole step mid-write. Measured on the 2026 rebuild: build_lanes.py 943 s from cold
# caches, build_freight.py 18 s, build_commodities.py 7 s, build_profiles.py 1 s.
STEP_MIN = {"extract": 30, "rice-forms": 10, "external": 10, "adjacency": 5, "lanes": 70, "freight": 20, "commodities": 15,
            "profiles": 10, "alerts": 5, "prices": 5, "coverage": 2}


# Time limit of each source (download and checks), in minutes. A BACI download (without --baci-check-only, by hand) has none.
SOURCE_MIN = {"usda-psd": 15, "usgs-mcs": 15, "eia-intl": 15, "baci": 10, "faostat-wna": 12}


class SourceTimeout(Exception):
    """A source used up its time limit."""


class time_limit:
    """Raise SourceTimeout in the main thread after ``minutes`` (no limit when None, or where SIGALRM does not exist)."""

    def __init__(self, minutes):
        self.seconds = int(minutes * 60) if minutes and hasattr(signal, "SIGALRM") else 0

    def _fire(self, *_):
        raise SourceTimeout(f"stopped after its time limit of {self.seconds // 60} min")

    def __enter__(self):
        if self.seconds:
            self.old = signal.signal(signal.SIGALRM, self._fire)
            signal.alarm(self.seconds)
        return self

    def __exit__(self, *exc):
        if self.seconds:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, self.old)
        return False


def run(cmd, timeout, annotate=False):
    """Run a command from the repo root; raise RuntimeError (with the last output line) when it fails. With ``annotate``,
    the last lines the command wrote to stderr are shown as warnings of the run, whatever its exit status."""
    print("  $", " ".join(os.path.relpath(c, ROOT) if os.path.isabs(c) and c.startswith(ROOT) else c for c in cmd), flush=True)
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"timed out after {timeout // 60} min")
    print("\n".join(r.stdout.splitlines()[-8:]))
    if annotate:
        for line in r.stderr.splitlines()[-20:]:
            print(f"::warning::{line}")
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


# the customs caches that a new BACI version replaces, and what src_baci keeps of the old ones until the freight step
# has rebuilt the lanes from the new ones: {"snap": Snapshot of the caches, "entry": the stored status of "baci"}
BACI_CACHES = [os.path.join(CACHE, "baci_flows.csv.gz"), os.path.join(CACHE, "baci_rice_forms.csv")] + [
    os.path.join(CACHE, f) for f in ("hs4_exports.csv.gz", "hs4_imports.csv.gz", "hs4_totals.csv", "hs4_exports_desc.csv")]
BACI_FIRST_YEAR = "2002"   # first year of the committed cache (METHODOLOGY.md, section 1)
_baci_backup = {}


# ----------------------------------------------------------------------------- sources
def src_usda(opts):
    import pandas as pd

    prev = status.get("usda-psd")
    with tempfile.TemporaryDirectory() as tmp:
        z = os.path.join(tmp, "psd_alldata_csv.zip")
        fetch.download(PSD_URL, z, kind="zip", min_bytes=1_000_000)
        digest = sha256(z)
        if digest == prev.get("state", {}).get("sha256") and on_disk(os.path.join(RAW, "usda", "psd_alldata_csv.zip"), digest) \
                and os.path.exists(os.path.join(RAW, "usda", "psd_csv", "psd_alldata.csv")):
            return {"changed": False, "note": "unchanged"}
        with zipfile.ZipFile(z) as zf:
            if "psd_alldata.csv" not in zf.namelist():
                raise ValueError("psd_alldata.csv missing from the zip")
            zf.extract("psd_alldata.csv", tmp)
        csv_path = os.path.join(tmp, "psd_alldata.csv")
        inputs.csv_header(csv_path, inputs.PSD_COLUMNS, encoding="latin-1")
        df = pd.read_csv(csv_path, usecols=["Commodity_Code", "Commodity_Description", "Market_Year", "Attribute_Description",
                                            "Value"], dtype=str, encoding="latin-1")
        n = len(df)
        if n < 500_000 or (prev.get("records") and n < 0.9 * prev["records"]):
            raise ValueError(f"only {n} rows (previous {prev.get('records')})")
        inputs.psd_content(df)
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
        inputs.csv_header(p, inputs.USGS_COLUMNS, encoding="latin-1")
        df = pd.read_csv(p, encoding="latin-1", usecols=["Commodity", "Country", "Statistics", "Year", "Value"])
        n = len(df)
        same_release = prev.get("state", {}).get("item") == item_id
        if n < 2000 or (same_release and prev.get("records") and n < 0.9 * prev["records"]):
            raise ValueError(f"only {n} rows (previous {prev.get('records')})")
        if same_release and digest == prev.get("state", {}).get("sha256") and on_disk(os.path.join(RAW, "usgs", main["name"]), digest):
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
        if digest == prev.get("state", {}).get("sha256") and on_disk(os.path.join(RAW, "eia", "INTL.zip"), digest) \
                and os.path.exists(os.path.join(RAW, "eia", "INTL.txt")):
            return {"changed": False, "note": "unchanged"}
        with zipfile.ZipFile(z) as zf:
            if "INTL.txt" not in zf.namelist():
                raise ValueError("INTL.txt missing from the zip")
            zf.extract("INTL.txt", tmp)
        txt = os.path.join(tmp, "INTL.txt")
        n, last, found = 0, "", set()
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
                found |= inputs.eia_found([line])
        if n < 10_000 or (prev.get("records") and n < 0.9 * prev["records"]):
            raise ValueError(f"only {n} series (previous {prev.get('records')})")
        inputs.eia_content(found)
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
    if errors:
        # a site that refuses the pages refuses the files too: no probing around it. An archive downloaded by hand
        # into raw/baci is used instead (docs/UPDATING.md, "Yearly refresh by hand").
        local = [m.group(1) for f in glob.glob(os.path.join(RAW, "baci", "BACI_HS92_V*.zip"))
                 if (m := re.search(r"BACI_HS92_(V\d{6})\.zip$", f))]
        if local and ver_tuple(max(local, key=ver_tuple)) > ver_tuple(recorded):
            return max(local, key=ver_tuple)
        raise fetch.FetchError("CEPII pages unreachable: " + errors[0])
    # pages readable but without links: probe the next plausible versions with HEAD requests
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
    return recorded


def src_baci(opts):
    import pandas as pd

    prev = status.get("baci")
    recorded = prev.get("state", {}).get("version") or BACI_BASELINE
    latest = baci_latest(recorded)
    print(f"  BACI recorded {recorded}, latest {latest}")
    if ver_tuple(latest) <= ver_tuple(recorded):
        if not prev.get("state", {}).get("version"):  # first run: record the baseline
            return {"changed": False, "note": "baseline", "state": {"version": recorded, "available": None}}
        return {"changed": False, "note": "no newer version", "state": {"version": recorded, "available": None}}
    if opts.baci_check_only:
        # "available" opens the "New release available: baci" issue (.github/actions/finish-data-update)
        return {"changed": False, "note": f"newer version {latest} available (check only)",
                "state": {"version": recorded, "available": latest}}
    name = f"BACI_HS92_{latest}.zip"
    zpath = os.path.join(RAW, "baci", name)
    url = BACI_BASE + name
    try:
        size = int(fetch.head(url).get("Content-Length") or 0)
    except fetch.FetchError:
        if not os.path.exists(zpath):
            raise
        size = os.path.getsize(zpath)  # downloaded by hand: the checks of the archive below decide
    if not (os.path.exists(zpath) and size and os.path.getsize(zpath) == size):
        fetch.download(url, zpath, kind="zip", min_bytes=500_000_000, resume=True, timeout=(20, 120))
    with zipfile.ZipFile(zpath) as zf:
        names = zf.namelist()
    years = sorted(int(m.group(1)) for n in names if (m := re.fullmatch(r"BACI_HS92_Y(\d{4})_V\d{6}\.csv", n)))
    if len(years) < 25 or not any(n.startswith("country_codes") for n in names):
        raise ValueError(f"unexpected BACI archive layout ({len(years)} yearly files)")
    out = os.path.join(CACHE, "baci_flows.csv.gz.tmp")
    run([PY, os.path.join(ROOT, "pipeline", "trade", "extract_baci.py"), zpath, out, BACI_FIRST_YEAR], STEP_MIN["extract"] * 60)
    new = pd.read_csv(out, usecols=["year", "t"])
    old_path = os.path.join(CACHE, "baci_flows.csv.gz")
    if os.path.exists(old_path):
        old = pd.read_csv(old_path, usecols=["year", "t"])
        if len(new) < 0.9 * len(old) or new["year"].max() < old["year"].max():
            os.remove(out)
            raise ValueError(f"extract looks wrong: {len(new)} rows to {new['year'].max()} vs {len(old)} to {old['year'].max()}")
    release_baci_backup()
    _baci_backup.update(snap=Snapshot(BACI_CACHES), entry=prev)
    os.replace(out, old_path)
    # paddy and husked rice, kept apart for the milled-equivalent rice flows; a failure here leaves the old file,
    # and build_commodities.py then says that the rice flows stay at customs weight
    try:
        run([PY, os.path.join(ROOT, "pipeline", "commodities", "extract_rice_forms.py"), zpath], STEP_MIN["rice-forms"] * 60)
    except RuntimeError as e:
        print("  rice forms extract failed, rice stays at customs weight:", e)
    # exports, imports and totals by HS4 of the latest year (country profiles); a failure leaves the old tables, and
    # build_profiles.py then leaves out the basket rather than mix two years
    try:
        run([PY, os.path.join(ROOT, "pipeline", "trade", "extract_hs4.py"), zpath, CACHE], STEP_MIN["extract"] * 60)
    except RuntimeError as e:
        print("  HS4 extract failed, the country profiles keep the previous HS4 tables:", e)
    return {"changed": True, "records": int(len(new)), "data_to": str(int(new["year"].max())),
            "state": {"version": latest, "available": None}}


def src_external(opts):
    """FAOSTAT cocoa and fertiliser + WNA uranium tables used by build_commodities.py (script written by the commodities job)."""
    script = os.path.join(ROOT, "pipeline", "commodities", "fetch_external.py")
    if not os.path.exists(script):
        return {"changed": False, "note": "script absent", "skip": True}
    prev = status.get("faostat-wna")
    last = prev.get("last_success")
    if last and (datetime.now(timezone.utc) - datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).days < 80:
        return {"changed": False, "note": "checked recently", "skip": True}
    files = [os.path.join(CACHE, "wna_uranium.json"), os.path.join(CACHE, "faostat_cocoa_production.csv"), os.path.join(CACHE, "faostat_eu_crops.csv"),
             os.path.join(CACHE, "faostat_fertilizer_production.csv")]
    before = [sha256(f) if os.path.exists(f) else None for f in files]
    snap = Snapshot(files)
    try:
        run([PY, script], STEP_MIN["external"] * 60)
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
    status.begin(name)
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


# exit status of build_commodities.py when everything was written except the monthly EIA series (build_commodities.MONTHLY_FAILED): the
# commodity pages are rebuilt, data/commodities/monthly keeps its previous files, and "build-monthly" is recorded as failing
MONTHLY_FAILED = 3


def build_commodities(script):
    """Run build_commodities.py; the failure of its monthly step (exit status MONTHLY_FAILED, after every commodity file was written) is
    recorded as "build-monthly" and does not fail "build-commodities". A success is recorded only to end a series of failures."""
    try:
        run([PY, script], STEP_MIN["commodities"] * 60)
    except RuntimeError as e:
        if not str(e).startswith(f"exit {MONTHLY_FAILED}:"):
            raise
        tail = str(e).split(": ", 1)[1]
        status.record_failure("build-monthly", tail)
        print("[build-monthly] FAILED, the previous monthly files are kept:", tail)
        return
    if pending("build-monthly"):
        status.record_success("build-monthly", note="rebuilt")


def build_coverage(script):
    """Rebuild data/coverage.json. Its warnings (a typed reason on a block that is present, a page below its floor) are
    shown as warnings of the run and do not fail the step. A file that has not the shape the site reads fails it, so that
    the step restores the previous file and the data validator, which has no override, never meets a malformed one."""
    run([PY, script], STEP_MIN["coverage"] * 60, annotate=True)
    node = shutil.which("node")
    if node:
        run([node, os.path.join(ROOT, "web", "scripts", "validate-coverage.mjs")], STEP_MIN["coverage"] * 60)
    else:
        print("  node not found: the shape of data/coverage.json is left to the data validators")


def release_baci_backup():
    snap = _baci_backup.pop("snap", None)
    _baci_backup.pop("entry", None)
    if snap is not None:
        snap.close()


def take_back_baci():
    """Put the previous BACI caches back and record "baci" as it was before this run, plus one failure: the next run
    downloads the new version again."""
    snap = _baci_backup.get("snap")
    if snap is None:
        return
    snap.restore()
    status.record_failure("baci", "the lanes could not be rebuilt from the new version: previous cache restored",
                          previous=_baci_backup.get("entry"))
    print("[baci] new cache taken back")


def process(changed):
    data = os.path.join(ROOT, "data")
    sources_json = os.path.join(data, "sources.json")
    chain = []
    if "usgs-mcs" in changed or pending("build-prices"):
        # the annual USGS prices (data/prices/usgs-*-a.json) are rebuilt from the new edition; the monthly and daily
        # files are not downloaded here: the builder keeps the series of a source whose file is absent
        chain.append(("build-prices", lambda: run([PY, os.path.join(ROOT, "pipeline", "prices", "build_prices.py"),
                                                   os.path.join(RAW, "worldbank", "CMO-Historical-Data-Monthly.xlsx"),
                                                   os.path.join(RAW, "eia-spot")], STEP_MIN["prices"] * 60),
                      [os.path.join(data, "prices")]))
    if "baci" in changed or pending("build-freight"):
        def freight():
            # borders and coasts first: modes.py reads adjacency.json when build_lanes.py imports it
            run([PY, os.path.join(ROOT, "pipeline", "geo", "adjacency.py")], STEP_MIN["adjacency"] * 60)
            run([PY, os.path.join(ROOT, "pipeline", "freight", "build_lanes.py")], STEP_MIN["lanes"] * 60)
            run([PY, os.path.join(ROOT, "pipeline", "freight", "build_freight.py")], STEP_MIN["freight"] * 60)
        # data/freight holds the lanes, pairs, caveats and zones files; the caches are those the two builders write
        chain.append(("build-freight", freight, [os.path.join(data, "freight"), sources_json,
                                                os.path.join(data, "countries", "places.json"),
                                                os.path.join(CACHE, "adjacency.json"),
                                                os.path.join(CACHE, "seaborne_totals.json"), os.path.join(CACHE, "geom_cache.json"),
                                                os.path.join(CACHE, "route_cache.json"), os.path.join(CACHE, "trade_checks.json"),
                                                os.path.join(CACHE, "sea_flows.csv.gz"), os.path.join(CACHE, "mixed_flows.csv.gz"),
                                                os.path.join(ROOT, "pipeline", "freight", "QA_routes.md")]))
        # the alert banners read the chokepoint estimates and lanes that build_freight.py has just written
        chain.append(("build-alerts", lambda: run([PY, os.path.join(ROOT, "pipeline", "freight", "build_alerts.py"), "--strict"],
                                                  STEP_MIN["alerts"] * 60), [os.path.join(data, "freight", "alerts.json")]))
    commodities = os.path.join(ROOT, "pipeline", "commodities", "build_commodities.py")
    if os.path.exists(commodities) and (changed or pending("build-commodities") or pending("build-monthly")):
        # build_commodities.py also rewrites pipeline/commodities/QA.md, which the workflow commits
        chain.append(("build-commodities", lambda: build_commodities(commodities),
                      [os.path.join(data, "commodities"), sources_json, os.path.join(ROOT, "pipeline", "commodities", "QA.md")]))
    coverage = os.path.join(ROOT, "pipeline", "commodities", "build_coverage.py")
    if os.path.exists(coverage) and (chain or pending("build-coverage")):
        # the matrix reads the pages, lanes, routes, prices, assets and companies: it is rebuilt when any of them was
        chain.append(("build-coverage", lambda: build_coverage(coverage), [os.path.join(data, "coverage.json")]))
    profiles = (glob.glob(os.path.join(ROOT, "pipeline", "**", "build_profiles.py"), recursive=True) or [None])[0]
    if profiles and (changed or pending("build-profiles")):
        chain.append(("build-profiles", lambda: run([PY, profiles], STEP_MIN["profiles"] * 60),
                      [os.path.join(data, "countries"), sources_json]))
    freight_failed = False
    try:
        for name, fn, paths in chain:
            if freight_failed:
                status.record_failure(name, "not run: build-freight failed after a new BACI cache was installed")
                print(f"[{name}] not run")
                continue
            ok = step(name, fn, paths)
            if name == "build-freight" and not ok and "baci" in changed:
                freight_failed = True
                take_back_baci()
    finally:
        release_baci_backup()


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
        status.begin(sid)
        limit = None if (sid == "baci" and not opts.baci_check_only) else SOURCE_MIN.get(sid)
        try:
            with time_limit(limit):
                res = SOURCES[sid](opts)
            if res.get("skip"):
                status.end(sid)
                print("  skipped:", res.get("note"))
                continue
            status.record_success(sid, records=res.get("records"), data_to=res.get("data_to"),
                                  note=res.get("note", "updated"), state=res.get("state"))
            if res["changed"]:
                changed.add(sid)
            print("  ok:", res.get("note", "updated"))
        except Exception as e:  # noqa: BLE001
            if not isinstance(e, (fetch.FetchError, ValueError, RuntimeError, SourceTimeout)):
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
