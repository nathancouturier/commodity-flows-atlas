"""
Fetch the price sources and rebuild data/prices (run weekly by .github/workflows/update-prices.yml).

    python pipeline/prices/fetch_prices.py

Sources (each recorded separately in data/_status/updates.json)
  wb-pink   World Bank Pink Sheet, monthly xlsx. The current link is scraped from
            https://www.worldbank.org/en/research/commodity-markets ("CMO-Historical-Data-Monthly.xlsx");
            the last known URL in raw/DOWNLOAD_REPORT.md is the fallback.
  eia-spot  EIA daily spot prices, 8 xls files (the ones build_prices.py reads).
  bls       BLS producer price index for deep-sea freight, public API version 1 without a key, cached in
            pipeline/cache/bls (freight_indicators.fetch_bls: the current window every week, the history once).
  dallasfed Dallas Fed index of global real economic activity, igrea.xlsx -> raw/dallasfed.
  nyfed     New York Fed Global Supply Chain Pressure Index, gscpi_data -> raw/nyfed.

Validation before a downloaded file replaces the previous one in raw/:
  Pink Sheet: opens, has the "Monthly Prices", "Monthly Indices" and "Description" sheets, EVERY column the
  builder maps is there (matched without the asterisks and spaces of the header) and every description row it
  reads can be found; latest month is not older than the previous run's. EIA: opens, has "Data 1", latest day is
  not older than before.
Then build_prices.py is run; if it fails data/prices is restored from a backup.
After the build, a series whose last observation did not advance as fast as its cadence allows (build_prices.
check_freshness) is recorded as a failure of its source in data/_status/updates.json, whatever the download
said: the data are still published, and after three runs in a row the owner is alerted (a frozen series never
passes as a success). A series its publisher stopped (it ends more than 6 months, or 120 days for a daily series,
behind the newest series of its source) is marked `closed` by the build: it is not late, it is recorded once in the
status of its source (state "closed": {series: last period}, and the note of that run) and the alert never fires for it.

Always exits 0: a failure is recorded in the status file and the previous good files are kept.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "prices"))

from common import fetch, status  # noqa: E402
import freight_indicators as FI  # noqa: E402

PINK_PAGE = "https://www.worldbank.org/en/research/commodity-markets"
PINK_NAME = "CMO-Historical-Data-Monthly.xlsx"
PINK_LAST_KNOWN = ("https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/"
                   "related/CMO-Historical-Data-Monthly.xlsx")
EIA_BASE = {"pet": "https://www.eia.gov/dnav/pet/hist_xls/", "ng": "https://www.eia.gov/dnav/ng/hist_xls/"}
RAW_WB = os.path.join(ROOT, "raw", "worldbank")
RAW_EIA = os.path.join(ROOT, "raw", "eia-spot")
DATA_PRICES = os.path.join(ROOT, "data", "prices")


def pink_candidates():
    """Candidate URLs, newest first: scraped from the World Bank page, then from DOWNLOAD_REPORT.md, then a constant."""
    urls = []
    try:
        html = fetch.get_text(PINK_PAGE)
        for m in re.finditer(r"""(?:href=["']?)([^"'\s>]*%s)""" % re.escape(PINK_NAME), html):
            u = m.group(1).replace("&amp;", "&")
            if u.startswith("//"):
                u = "https:" + u
            elif u.startswith("/"):
                u = "https://www.worldbank.org" + u
            urls.append(u)
    except fetch.FetchError as e:
        print("  page scrape failed:", e)
    try:
        report = open(os.path.join(ROOT, "raw", "DOWNLOAD_REPORT.md"), encoding="utf-8").read()
        urls += re.findall(r"https://\S*%s" % re.escape(PINK_NAME), report)
    except OSError:
        pass
    urls.append(PINK_LAST_KNOWN)
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def check_pink(path):
    """Return (latest 'YYYY-MM', month count) or raise ValueError."""
    from build_prices import BuildError, Pink

    try:
        p = Pink(path)
    except BuildError as e:
        raise ValueError(str(e))
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"workbook does not open ({e.__class__.__name__})")
    problems = p.check()
    if problems:
        raise ValueError(f"{len(problems)} expected columns or description rows missing (e.g. {problems[0]})")
    months = [r[0].strip() for r in p.data]
    if len(months) < 600:
        raise ValueError(f"only {len(months)} months")
    return months[-1].replace("M", "-"), len(months)


def check_eia(path):
    """Return (latest 'YYYY-MM-DD', observations) or raise ValueError."""
    import xlrd

    try:
        sh = xlrd.open_workbook(path).sheet_by_name("Data 1")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"xls does not open ({e.__class__.__name__})")
    days = [xlrd.xldate.xldate_as_datetime(r[0], 0).date() for r in (sh.row_values(i) for i in range(3, sh.nrows))
            if isinstance(r[0], float) and r[1] not in ("", None)]
    if len(days) < 1000:
        raise ValueError(f"only {len(days)} observations")
    return str(max(days)), len(days)


def install(tmp, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    os.replace(tmp, dest)


def fetch_pink(stage):
    prev = status.get("wb-pink")
    last_err = "no candidate URL"
    for url in pink_candidates():
        tmp = os.path.join(stage, PINK_NAME)
        try:
            size = fetch.download(url, tmp, kind="xlsx", min_bytes=100_000)
            latest, n = check_pink(tmp)
        except (fetch.FetchError, ValueError) as e:
            last_err = f"{e}"
            print("  candidate failed:", url, "->", e)
            continue
        if prev.get("data_to") and latest < prev["data_to"]:
            last_err = f"latest month {latest} is older than previous {prev['data_to']}"
            print("  rejected:", last_err)
            continue
        install(tmp, os.path.join(RAW_WB, PINK_NAME))
        print(f"  Pink Sheet {latest}, {n} months, {size} bytes from {url}")
        return {"records": n, "data_to": latest, "state": {"url": url}}, None
    return None, last_err


def fetch_eia(stage):
    from build_prices import EIA

    prev = status.get("eia-spot").get("state", {}).get("last", {})
    last, total, errors, updated = dict(prev), 0, [], 0
    for code in EIA:
        base = EIA_BASE["ng"] if code.startswith("RNG") else EIA_BASE["pet"]
        tmp = os.path.join(stage, code + ".xls")
        try:
            fetch.download(base + code + ".xls", tmp, kind="xls", min_bytes=20_000)
            latest, n = check_eia(tmp)
            if code in prev and latest < prev[code]:
                raise ValueError(f"latest day {latest} older than previous {prev[code]}")
        except (fetch.FetchError, ValueError) as e:
            errors.append(f"{code}: {e}")
            print("  EIA", code, "failed:", e)
            continue
        install(tmp, os.path.join(RAW_EIA, code + ".xls"))
        last[code], total, updated = latest, total + n, updated + 1
        print("  EIA", code, latest, n)
    info = {"records": total or None, "data_to": min(last.values()) if len(last) == len(EIA) else None,
            "state": {"last": last}}
    return info, ("; ".join(errors)[:200] if errors else None), updated


FREIGHT_SOURCES = ("bls", "dallasfed", "nyfed")


def fetch_freight(stage):
    """The three sources of the Freight family: {source: (info, error, updated)}. info is None when nothing usable
    came; a failure keeps the previous cache or raw file."""
    out = {}
    try:
        info, err, changed = FI.fetch_bls()
        out["bls"] = (info if not err else None, err, changed)
    except Exception as e:  # noqa: BLE001
        out["bls"] = (None, f"unexpected {e.__class__.__name__}: {e}", False)
    for src, fn in (("dallasfed", FI.fetch_dallasfed), ("nyfed", FI.fetch_nyfed)):
        try:
            info, err = fn(stage, prev_to=status.get(src).get("data_to"))
            out[src] = (info, err, info is not None)
        except Exception as e:  # noqa: BLE001
            out[src] = (None, f"unexpected {e.__class__.__name__}: {e}", False)
    return out


def rebuild():
    """Run build_prices.py against raw/; restore data/prices from a backup when it fails."""
    with tempfile.TemporaryDirectory() as bk:
        backup = os.path.join(bk, "prices")
        if os.path.isdir(DATA_PRICES):
            shutil.copytree(DATA_PRICES, backup)
        pink = os.path.join(RAW_WB, PINK_NAME)
        cmd = [sys.executable, os.path.join(ROOT, "pipeline", "prices", "build_prices.py"), pink, RAW_EIA]
        try:
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900)
            print(r.stdout[-1500:])
            if r.returncode != 0:
                raise RuntimeError("build_prices failed: " + (r.stderr.strip().splitlines() or ["?"])[-1])
            if not os.path.exists(os.path.join(DATA_PRICES, "index.json")):
                raise RuntimeError("build_prices produced no index.json")
        except Exception:
            if os.path.isdir(backup):
                shutil.rmtree(DATA_PRICES, ignore_errors=True)
                shutil.copytree(backup, DATA_PRICES)
            raise


def late_series():
    """{source: message} for the sources with a series that stopped advancing."""
    import build_prices

    try:
        with open(os.path.join(DATA_PRICES, "index.json"), encoding="utf-8") as f:
            metas = json.load(f)
        late = build_prices.stale_by_source(metas)
    except (OSError, ValueError, KeyError) as e:
        print("  freshness check skipped:", e)
        return {}
    for s, msg in late.items():
        print("  ", s, msg)
    return {s: m for s, m in late.items() if s in ("wb-pink", "eia-spot") + FREIGHT_SOURCES}


def closed_series():
    """{source: {series id: last period}} of the series the publisher stopped (build_prices.mark_closed marks them in
    the index): a stopped series is history, not a failure, and it is recorded in the source's status."""
    try:
        with open(os.path.join(DATA_PRICES, "index.json"), encoding="utf-8") as f:
            metas = json.load(f)
    except (OSError, ValueError) as e:
        print("  closed series skipped:", e)
        return {}
    out = {}
    for m in metas:
        if m.get("closed") and m["freq"] in ("D", "M") and not m.get("hidden"):
            out.setdefault(m["s"], {})[m["id"]] = m["end"]
    return out


def closed_state(source, closed):
    """(state to record, note) for a source: the closed series, and a note naming those closed since the last run, so
    that the change is reported once."""
    now = closed.get(source, {})
    before = (status.get(source).get("state") or {}).get("closed") or {}
    new = [f"{i} (last period {e})" for i, e in now.items() if i not in before]
    return {"closed": now}, ("; closed: " + ", ".join(new) if new else "")


def main():
    with tempfile.TemporaryDirectory() as stage:
        try:
            pink, pink_err = fetch_pink(stage)
        except Exception as e:  # noqa: BLE001
            pink, pink_err = None, f"unexpected {e.__class__.__name__}: {e}"
            traceback.print_exc()
        try:
            eia, eia_err, eia_updated = fetch_eia(stage)
        except Exception as e:  # noqa: BLE001
            eia, eia_err, eia_updated = None, f"unexpected {e.__class__.__name__}: {e}", 0
            traceback.print_exc()

        freight = fetch_freight(stage)

    build_err = None
    stale, closed = {}, {}
    if pink or eia_updated or any(u for _, _, u in freight.values()):
        try:
            rebuild()
        except Exception as e:  # noqa: BLE001
            build_err = str(e)
            print("  rebuild failed:", build_err)
    if not build_err:
        stale = late_series()
        closed = closed_series()
    # record
    if pink and not build_err and not stale.get("wb-pink"):
        state, note = closed_state("wb-pink", closed)
        status.record_success("wb-pink", records=pink["records"], data_to=pink["data_to"], state={**pink["state"], **state}, note="updated" + note)
    else:
        status.record_failure("wb-pink", build_err or stale.get("wb-pink") or pink_err)
    if eia is not None and eia_updated and not build_err and not eia_err and not stale.get("eia-spot"):
        state, note = closed_state("eia-spot", closed)
        status.record_success("eia-spot", records=eia["records"], data_to=eia["data_to"], state={**eia["state"], **state}, note="updated" + note)
    elif eia is not None and eia_updated and not build_err:
        status.record_failure("eia-spot", eia_err or stale.get("eia-spot"))  # partial: some files updated, some failed
    else:
        status.record_failure("eia-spot", build_err or eia_err or stale.get("eia-spot") or "no EIA file updated")
    for src in FREIGHT_SOURCES:
        info, err, _ = freight[src]
        if info and not build_err and not stale.get(src):
            status.record_success(src, records=info["records"], data_to=info["data_to"], note="updated" + info.get("note", ""))
        else:
            status.record_failure(src, build_err or err or stale.get(src) or "no data")
    print("done")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001  never fail the workflow
        traceback.print_exc()
    sys.exit(0)
