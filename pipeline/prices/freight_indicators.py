"""
Freight indicators of the "Freight" price family, each taken from its own publisher (never through FRED).

    from freight_indicators import fetch_bls, fetch_dallasfed, fetch_nyfed     # fetch_prices.py, weekly
    from freight_indicators import bls_series, dallasfed_series, nyfed_series  # build_prices.py

  bls        US producer price index for deep-sea freight transportation (BLS series PCU483111483111), from the BLS
             public API version 1, which answers without a key or a registration: ten years per request and a small
             daily quota per address. The history is fetched once and kept in pipeline/cache/bls/<series>.json; a
             weekly run asks only for the current window (this year and the two before, which the BLS revises), and
             for at most HISTORY_REQUESTS_PER_RUN older ten-year windows until every year has come from the BLS. A
             refused request (quota reached, network, a changed answer) keeps the cache as it is and is recorded.
  dallasfed  Federal Reserve Bank of Dallas, Index of global real economic activity (Kilian), monthly since 1968:
             igrea.xlsx -> raw/dallasfed/igrea.xlsx
  nyfed      Federal Reserve Bank of New York, Global Supply Chain Pressure Index, monthly since 1998:
             gscpi_data.xls -> raw/nyfed/gscpi_data.xls

None of the three is a freight rate: the notes and the basis written into data/prices/index.json say what each one
measures. Freight rates themselves (Baltic Exchange, Shanghai Shipping Exchange, Clarksons, Platts, Argus) are
proprietary and never stored; the USDA grain rates credit private firms or foreign institutes and are only linked
(see METHODOLOGY.md).
"""
import json
import os
import re
import sys
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

from common import fetch  # noqa: E402

# ---------------------------------------------------------------- BLS

BLS_API = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
BLS_SERIES = "PCU483111483111"
BLS_CACHE_DIR = os.path.join(ROOT, "pipeline", "cache", "bls")
BLS_WINDOW_YEARS = 10           # the version 1 API returns at most ten years per request
BLS_CURRENT_YEARS = 3           # this year and the two before: the window the BLS still revises
HISTORY_REQUESTS_PER_RUN = 3    # older windows asked for in one run (the daily quota is shared by the address)
BLS_FIRST_YEAR = 1988           # the index starts in June 1988 (= 100)


def bls_cache_path(series=BLS_SERIES, cache_dir=None):
    return os.path.join(cache_dir or BLS_CACHE_DIR, series + ".json")


def load_bls_cache(series=BLS_SERIES, cache_dir=None):
    try:
        with open(bls_cache_path(series, cache_dir), encoding="utf-8") as f:
            doc = json.load(f)
        if isinstance(doc.get("obs"), dict):
            return doc
    except (OSError, ValueError):
        pass
    return {"series": series, "obs": {}, "prelim": [], "bls_years": [], "seed": None}


def save_bls_cache(doc, series=BLS_SERIES, cache_dir=None):
    path = bls_cache_path(series, cache_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc["obs"] = dict(sorted(doc["obs"].items()))
    doc["prelim"] = sorted(set(doc.get("prelim") or []))
    doc["bls_years"] = sorted(set(doc.get("bls_years") or []))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def _content(doc):
    """What the cache holds, without the time of the last fetch: the file is rewritten only when this changes."""
    return json.dumps([dict(sorted(doc["obs"].items())), sorted(set(doc.get("prelim") or [])),
                       sorted(set(doc.get("bls_years") or [])), doc.get("seed")])


def year_runs(years):
    """[1988, 1989, 1990, 2005] -> "1988 to 1990 and 2005": the years as the runs they are."""
    runs = []
    for y in sorted(set(years)):
        if runs and y == runs[-1][1] + 1:
            runs[-1][1] = y
        else:
            runs.append([y, y])
    parts = [f"{a} to {b}" if b > a else str(a) for a, b in runs]
    return " and ".join(parts) if len(parts) < 3 else ", ".join(parts[:-1]) + " and " + parts[-1]


def parse_bls(doc, series=BLS_SERIES):
    """The monthly observations of one series in an answer of the BLS API: ({"YYYY-MM": value}, [preliminary months]).
    Raises ValueError when the BLS did not process the request (its message is kept: a reached quota says so)."""
    if not isinstance(doc, dict):
        raise ValueError("answer is not a JSON object")
    if doc.get("status") != "REQUEST_SUCCEEDED":
        msg = " ".join(doc.get("message") or []) or str(doc.get("status"))
        raise ValueError(f"BLS did not process the request: {msg[:160]}")
    found = [s for s in (doc.get("Results") or {}).get("series") or [] if s.get("seriesID") == series]
    if not found:
        raise ValueError(f"series {series} not in the answer")
    obs, prelim = {}, []
    for row in found[0].get("data") or []:
        period = str(row.get("period", ""))
        if not re.fullmatch(r"M(0[1-9]|1[0-2])", period):  # M13 is the annual average
            continue
        try:
            v = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
        month = f"{int(row['year']):04d}-{period[1:]}"
        obs[month] = v
        if any((f or {}).get("code") == "P" for f in row.get("footnotes") or []):
            prelim.append(month)
    return obs, prelim


def bls_request(series, start=None, end=None, attempts=2):
    """One request to the version 1 API, no key. Without years it returns the last three years."""
    params = {"startyear": str(start), "endyear": str(end)} if start else None
    return fetch.get_json(BLS_API + series, params=params, attempts=attempts, min_interval=5)


def history_windows(have_years, first_year, last_year, size=BLS_WINDOW_YEARS):
    """Ten-year windows (start, end), oldest first, that cover the years not yet fetched from the BLS."""
    missing = [y for y in range(first_year, last_year + 1) if y not in set(have_years)]
    out = []
    for y in missing:
        if out and y <= out[-1][0] + size - 1:
            out[-1] = (out[-1][0], y)
        else:
            out.append((y, y))
    return out


def fetch_bls(series=BLS_SERIES, cache_dir=None, today=None, request=bls_request):
    """Update the cache of a BLS series. Returns (info, error, changed): info {"records", "data_to", "note"} once the
    cache holds the series; error a short message when the current window was refused (that is the failure of the run:
    a refused older window is only named in the note, and asked for again next week); changed True when the cache was
    rewritten, which happens only when a value, a preliminary flag or the years fetched changed (no weekly commit for
    an identical answer). The current window comes first: when it is refused, no older window is asked for in that run."""
    today = today or date.today()
    doc = load_bls_cache(series, cache_dir)
    before = _content(doc)
    errors, older = [], []
    cur_from = today.year - BLS_CURRENT_YEARS + 1
    plan = [(cur_from, today.year)]
    have = set(doc.get("bls_years") or [])
    plan += history_windows(have, BLS_FIRST_YEAR, cur_from - 1)[:HISTORY_REQUESTS_PER_RUN]
    for i, (a, b) in enumerate(plan):
        try:
            obs, prelim = parse_bls(request(series, a, b), series)
            got = {int(m[:4]) for m in obs}
            if not got:
                raise ValueError(f"no monthly value for {a}-{b}")
            if i == 0 and max(got) < today.year - 1:
                raise ValueError(f"latest year {max(got)} is too old")
            if not got <= set(range(a, b + 1)):
                raise ValueError(f"asked for {a}-{b}, got {min(got)}-{max(got)}: the years were not taken into account")
        except (fetch.FetchError, ValueError) as e:
            (errors if i == 0 else older).append(f"{a}-{b}: {e}")
            print("  BLS", series, a, b, "failed:", e)
            if i == 0:
                break
            continue
        old_prelim = set(doc.get("prelim") or [])
        doc["obs"].update(obs)
        span = {f"{y:04d}-{m:02d}" for y in got for m in range(1, 13)}
        doc["prelim"] = sorted((old_prelim - span) | set(prelim))
        have |= set(range(a, b + 1))  # every year of an answered window, the empty ones before 1988 included
        doc["bls_years"] = sorted(have)
    if doc.get("seed") and doc["obs"] and all(int(m[:4]) in have for m in doc["obs"]):
        doc["seed"] = None  # every year now comes from the BLS
    changed = _content(doc) != before
    if changed:
        doc["fetched"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        save_bls_cache(doc, series, cache_dir)
    left = history_windows(have, BLS_FIRST_YEAR, cur_from - 1)
    note = ("; older years still to fetch: " + ", ".join(f"{a}-{b}" for a, b in left) if left else "") + ("; refused: " + "; ".join(older) if older else "")
    info = {"records": len(doc["obs"]), "data_to": max(doc["obs"]), "note": note[:200]} if doc["obs"] else None
    return info, ("; ".join(errors)[:200] if errors else None), changed


def seed_bls_cache(release_path, note, series=BLS_SERIES, cache_dir=None):
    """Start the cache from the values the atlas already published (packed monthly file), until the BLS answers for
    every year. The note says where those values came from; bls_years stays empty, so all of them are asked for."""
    with open(release_path, encoding="utf-8") as f:
        packed = json.load(f)
    y, m = int(packed["start"][:4]), int(packed["start"][5:7])
    obs = {}
    for i, v in enumerate(packed["v"]):
        k = y * 12 + m - 1 + i
        if v is not None:
            obs[f"{k // 12:04d}-{k % 12 + 1:02d}"] = v
    doc = {"series": series, "obs": obs, "prelim": [], "bls_years": [], "seed": note}
    save_bls_cache(doc, series, cache_dir)
    return doc


BLS_NAME = "US deep-sea freight services, producer price index (BLS)"
BLS_BASIS = ("US Bureau of Labor Statistics, producer price index by industry, deep sea freight transportation (NAICS "
             "483111), series PCU483111483111, not seasonally adjusted, June 1988 = 100. It measures the change in the "
             "prices US-based deep-sea carriers receive for their freight services. It is not a spot freight rate and "
             "moves far less than the Baltic indices: +0.7% from May to December 2008 (256.5 to 258.2) while dry bulk "
             "rates collapsed, then a fall of 27% from September 2008 (284.4) to May 2009 (208.8).")


def bls_series(cache_dir=None, series=BLS_SERIES, sid="freight-ppi-m", meta_of=None):
    """[(doc, meta)] of the BLS producer price index from the cache (empty when there is no cache)."""
    doc = load_bls_cache(series, cache_dir)
    if not doc["obs"]:
        return []
    months = sorted(doc["obs"])
    y, m = int(months[0][:4]), int(months[0][5:7])
    ly, lm = int(months[-1][:4]), int(months[-1][5:7])
    n = (ly - y) * 12 + lm - m + 1
    vals = []
    for i in range(n):
        k = y * 12 + m - 1 + i
        vals.append(doc["obs"].get(f"{k // 12:04d}-{k % 12 + 1:02d}"))
    unit = "index"
    base = next((mo for mo in months if abs(doc["obs"][mo] - 100.0) < 1e-9), None)
    if base:
        unit = f"index ({date(int(base[:4]), int(base[5:7]), 1):%b %Y} = 100)"
    note = "Producer price index: not a freight rate"
    prelim = [p for p in doc.get("prelim") or [] if p in doc["obs"]]
    if prelim:
        note += f"; the BLS marks {prelim[0]} to {prelim[-1]} as preliminary" if len(prelim) > 1 else f"; the BLS marks {prelim[0]} as preliminary"
    if doc.get("seed"):
        seeded = {int(mo[:4]) for mo in months} - {int(x) for x in doc.get("bls_years") or []}
        if seeded:
            note += f". {year_runs(seeded)}: {doc['seed']}"
            # the copy carries no preliminary flag, which the BLS gives its last months
            if int(months[-1][:4]) in seeded:
                note += "; the latest months may be preliminary"
    packed = {"id": sid, "freq": "M", "start": months[0], "v": vals}
    meta = meta_of(sid, "freight", BLS_NAME, unit, "M", "bls", months[0], months[-1], note=note, basis=BLS_BASIS)
    return [(packed, meta)]


# ---------------------------------------------------------------- Dallas Fed and New York Fed

DALLASFED_URL = "https://www.dallasfed.org/-/media/Documents/research/igrea/igrea.xlsx"
DALLASFED_FILE = os.path.join(ROOT, "raw", "dallasfed", "igrea.xlsx")
# the file is named .xlsx but is an .xls (BIFF) workbook: its type is not checked on download, the reader opens either
NYFED_URL = "https://www.newyorkfed.org/medialibrary/research/interactives/gscpi/downloads/gscpi_data.xlsx"
NYFED_FILE = os.path.join(ROOT, "raw", "nyfed", "gscpi_data.xls")


def _months(pairs):
    """[(date or datetime, value)] -> (first 'YYYY-MM', consecutive values with None in the gaps). One value a month:
    the Dallas Fed stamps some months on the 26th, the New York Fed on the last day."""
    by = {}
    for d, v in pairs:
        by[(d.year, d.month)] = v
    if not by:
        return None, []
    keys = sorted(by)
    (y, m), (ly, lm) = keys[0], keys[-1]
    out = []
    for i in range((ly - y) * 12 + lm - m + 1):
        k = y * 12 + m - 1 + i
        out.append(by.get((k // 12, k % 12 + 1)))
    return f"{y:04d}-{m:02d}", out


def read_igrea(path):
    """('YYYY-MM', values) of the sheet "Kilian Index" (first column a date, second the index)."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Kilian Index"] if "Kilian Index" in wb.sheetnames else wb.worksheets[0]
    pairs = []
    for r in ws.iter_rows(values_only=True):
        if r and isinstance(r[0], datetime) and isinstance(r[1], (int, float)):
            pairs.append((r[0], round(float(r[1]), 6)))
    return _months(pairs)


def read_gscpi(path):
    """('YYYY-MM', values) of the sheet "GSCPI Monthly Data" (dates written "31-Jan-1998"). The file is an .xls
    workbook; an .xlsx one is read too, in case the New York Fed changes the format."""
    rows = []
    try:
        import xlrd

        sh = xlrd.open_workbook(path).sheet_by_index(0)
        rows = [sh.row_values(i)[:2] for i in range(sh.nrows)]
    except Exception:  # noqa: BLE001  not an .xls workbook
        import openpyxl

        rows = [list(r[:2]) for r in openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True)]
    pairs = []
    for d, v in rows:
        if isinstance(d, str):
            try:
                d = datetime.strptime(d.strip(), "%d-%b-%Y")
            except ValueError:
                continue
        if isinstance(d, datetime) and isinstance(v, (int, float)):
            pairs.append((d, round(float(v), 6)))
    return _months(pairs)


def check_monthly(start, values, min_months, prev_to=None):
    """(latest 'YYYY-MM', months) or ValueError: enough months, no gap, not older than the previous file."""
    if not start or len(values) < min_months:
        raise ValueError(f"only {len(values)} months")
    if any(v is None for v in values):
        raise ValueError("a month is missing inside the series")
    y, m = int(start[:4]), int(start[5:7])
    k = y * 12 + m - 1 + len(values) - 1
    latest = f"{k // 12:04d}-{k % 12 + 1:02d}"
    if prev_to and latest < prev_to:
        raise ValueError(f"latest month {latest} is older than previous {prev_to}")
    return latest, len(values)


def _fetch_file(stage, urls, dest, reader, min_months, prev_to):
    last = "no URL"
    for url, k in urls:
        tmp = os.path.join(stage, os.path.basename(dest))
        try:
            fetch.download(url, tmp, kind=k, min_bytes=10_000)
            latest, n = check_monthly(*reader(tmp), min_months, prev_to)
        except (fetch.FetchError, ValueError) as e:
            last = str(e)
            print("  candidate failed:", url, "->", e)
            continue
        except Exception as e:  # noqa: BLE001  a workbook that does not open
            last = f"file does not open ({e.__class__.__name__})"
            print("  candidate failed:", url, "->", last)
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        os.replace(tmp, dest)
        print(f"  {os.path.basename(dest)}: {n} months to {latest} from {url}")
        return {"records": n, "data_to": latest}, None
    return None, last


def fetch_dallasfed(stage, prev_to=None, dest=DALLASFED_FILE):
    return _fetch_file(stage, [(DALLASFED_URL, "xlsx")], dest, read_igrea, 600, prev_to)


def fetch_nyfed(stage, prev_to=None, dest=NYFED_FILE):
    return _fetch_file(stage, [(NYFED_URL, None)], dest, read_gscpi, 300, prev_to)


IGREA_NAME = "Index of global real economic activity (Dallas Fed, Kilian)"
IGREA_BASIS = ("Federal Reserve Bank of Dallas: “Updated index of global real economic activity in industrial commodity "
               "markets, as proposed in Kilian (2009), with the correction discussed in Kilian (2019). This business-cycle "
               "index is expressed in percent deviations from trend. It is derived from a panel of dollar-denominated global "
               "bulk dry cargo shipping rates and may be viewed as a proxy for the volume of shipping in global industrial "
               "commodity markets.” Kilian, L. (2009), American Economic Review 99(3), doi:10.1257/aer.99.3.1053; "
               "Kilian, L. (2019), Economics Letters 178, doi:10.1016/j.econlet.2019.03.001.")
GSCPI_NAME = "Global Supply Chain Pressure Index (New York Fed)"
GSCPI_BASIS = ("Federal Reserve Bank of New York: the index combines transport costs (the Baltic Dry Index, the Harpex "
               "container index and the BLS air freight cost indices) with supply-chain components of manufacturing PMI "
               "surveys in seven economies; readings are standard deviations from the index's historical average, and the "
               "last months are revised as data come in. Cite as: Federal Reserve Bank of New York, Global Supply Chain "
               "Pressure Index, https://www.newyorkfed.org/research/policy/gscpi. The GSCPI is not an official estimate of "
               "the Federal Reserve Bank of New York, its President, the Federal Reserve System, or the Federal Open Market "
               "Committee.")


def dallasfed_series(path=DALLASFED_FILE, meta_of=None):
    if not os.path.exists(path):
        return []
    start, vals = read_igrea(path)
    if not start:
        return []
    end = _end(start, len(vals))
    doc = {"id": "igrea-m", "freq": "M", "start": start, "v": vals}
    meta = meta_of("igrea-m", "freight", IGREA_NAME, "% deviation from trend", "M", "dallasfed", start, end,
                   note="Deflated, detrended index built on dry bulk freight rates: not a freight rate", basis=IGREA_BASIS)
    return [(doc, meta)]


def nyfed_series(path=NYFED_FILE, meta_of=None):
    if not os.path.exists(path):
        return []
    start, vals = read_gscpi(path)
    if not start:
        return []
    end = _end(start, len(vals))
    doc = {"id": "gscpi-m", "freq": "M", "start": start, "v": vals}
    meta = meta_of("gscpi-m", "freight", GSCPI_NAME, "standard deviations from average", "M", "nyfed", start, end,
                   note="Supply-chain pressure, partly built on freight indices: not a freight rate", basis=GSCPI_BASIS)
    return [(doc, meta)]


def _end(start, n):
    k = int(start[:4]) * 12 + int(start[5:7]) - 1 + n - 1
    return f"{k // 12:04d}-{k % 12 + 1:02d}"
