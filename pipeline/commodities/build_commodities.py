"""
Build data/commodities/<id>.json (CommodityData, see web/src/types.ts) for every commodity of
data/commodities/index.json, update the `has` array of the index, add the new sources to
data/sources.json and write pipeline/commodities/QA.md.

    .venv/bin/python -I pipeline/commodities/build_commodities.py

Inputs (raw/ is read-only, untrusted data: it is only ever parsed, never executed)
  raw/usgs/MCS2026_Commodities_Data.csv      USGS Mineral Commodity Summaries 2026      (source "usgs-mcs")
  raw/eia/INTL.txt                           EIA International Energy Data               (source "eia-intl")
  raw/usda/psd_csv/psd_alldata.csv           USDA PSD                                    (source "usda-psd")
  pipeline/cache/baci_flows.csv.gz           CEPII BACI HS92 bilateral trade             (source "baci")
  pipeline/freight/modes.py, ports.py        mode of every flow (sea, sea via a transit port, mixed, land), as the lanes
  data/freight/caveats.json                  active caveats of pipeline/trade/caveats.py (build_lanes.py)
  pipeline/cache/trade_checks.json           findings of the trade checks K1 to K12, rendered in QA.md (read only)
  pipeline/cache/baci_rice_forms.csv         paddy and husked rice per pair (extract_rice_forms.py), to put paddy on a milled basis
  data/freight/lanes/<group>.json            lane ids and seaborne totals
  pipeline/cache/wna_uranium.json            World Nuclear Association (fetch_external.py)   (source "wna")
  pipeline/cache/faostat_cocoa_production.csv  FAOSTAT QCL cocoa beans (fetch_external.py) (source "faostat")
  raw/baci/country_codes_V202601.csv         M49 -> ISO3 for FAOSTAT area codes

Rules
  * no number is invented: every figure is read from one of the files above and carries source id + year;
  * country names are mapped to ISO3 via data/countries/index.json plus the explicit override tables below;
    an unknown name raises an error (true aggregates are skipped explicitly);
  * BACI tonnage fixes follow pipeline/freight/build_lanes.py (missing tonnage, or unit value < 1/3 or > 3x
    the group-year median for flows > 50 M USD, is re-estimated from value and flagged).
"""
import csv
import json
import math
import os
import re
import sys
import unicodedata
from collections import defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RAW = os.path.join(ROOT, "raw")
CACHE = os.path.join(ROOT, "pipeline", "cache")
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "commodities")

def _latest_inputs():
    """Years and file names derived from the inputs, so the monthly job keeps working when sources roll over.

    - BACI_YEAR: latest year in the BACI cache.
    - USGS file: the newest MCS<yyyy>_Commodities_Data.csv; its tables report year yyyy-1 (estimates).
    - PSD_MY: the newest market year most crops have: USDA's forecast of the year in progress (the file holds no later year;
      PSD adds the next one in May). The year before it, PSD_MY - 1, is USDA's estimate (the PSD_EST of the comparisons with
      customs data). The year rule lives here only: tables, key figures, history files and country colours follow it.
    """
    # the rules live in common/vintage.py, with the fallbacks of a clone without raw/ (no year written here)
    sys.path.insert(0, os.path.join(HERE, ".."))
    from common import vintage as V
    usgs_file = V.usgs_file()
    return V.baci_year(), str(V.usgs_edition() - 1), usgs_file, V.psd_market_year()


BACI_YEAR, USGS_YEAR, USGS_FILE, PSD_MY = _latest_inputs()
PSD_LABEL = f"{PSD_MY}/{(PSD_MY + 1) % 100:02d}"  # the forecast year
PSD_EST = PSD_MY - 1  # the estimate year, the latest complete one: what customs data of the year before are compared with
PSD_EST_LABEL = f"{PSD_EST}/{PSD_MY % 100:02d}"
USGS_EDITION = int(USGS_YEAR) + 1
# every table lists every country that has a value; the page draws the first SHOWN_ROWS and a "Rest of world" line
SHOWN_ROWS = 10  # rows the commodity page draws before "Rest of world" and "Other countries" (RankedBars, web/src/components/ui.tsx)
NFLOWS = 20
HIST_FROM = 2005  # first year of the series by country (data/commodities/history, history.py)
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

# exit status of the builder when everything was written except the monthly series (update_annual.py records it as "build-monthly" failing)
MONTHLY_FAILED = 3
QA_WARN = []
QUIET = [False]  # True while the past years of the series are built (history.py): the page shows the latest year


def warn(msg):
    if QUIET[0]:
        return
    QA_WARN.append(msg)
    print("WARN:", msg)


# ====================================================================== country names
def fold(s):
    s = s.replace("\x92", "'").replace("’", "'")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().lower()


COUNTRIES = json.load(open(os.path.join(DATA, "countries", "index.json"), encoding="utf-8"))
ISO_SET = {c["c"] for c in COUNTRIES}
ISO_OF_A2 = {c["a2"]: c["c"] for c in COUNTRIES if c.get("a2")}
NAME2ISO = {fold(c["name"]): c["c"] for c in COUNTRIES}

# odd names -> ISO3 (USGS / PSD / WNA / FAO spellings that differ from data/countries/index.json)
OVERRIDE = {
    "burma": "MMR",
    "congo (kinshasa)": "COD",
    "congo (brazzaville)": "COG",
    "korea, republic of": "KOR",
    "korea, south": "KOR",
    "korea, north": "PRK",
    "bahamas, the": "BHS",
    "gambia, the": "GMB",
    "czech republic": "CZE",
    "central african republic": "CAF",
    "dominican republic": "DOM",
    "hong kong": "HKG",
    "macau": "MAC",
    "vanuatu/new hebrides": "VUT",
    "kosovo": "KOS",
    "usa": "USA",
    "turkiye": "TUR",
    "cote d'ivoire": "CIV",
    "belgium-luxembourg": "BEL",  # PSD legacy combined entity; only tiny cotton volumes
    "south sudan": "SSD",
    "sao tome and principe": "STP",
    "european union": "EU27",
    "eu-25": "EU27",  # PSD sugar, market year 2005/06: the EU entity of that year (its "European Union" row is 0)
}
# true aggregates / entities without an ISO3 in the Atlas country list: skipped on purpose
AGGREGATE = {
    "other countries", "world total", "others", "other", "world", "french west indies",
    "netherlands antilles", "serbia and montenegro",
}
# EIA geography codes that are regions / dissolved states / territories without a country entry
EIA_SKIP = {
    "WORL", "AFRC", "ASOC", "CSAM", "EURA", "EURO", "EU27", "MIDE", "NOAM", "NOEC", "OECD", "OEAO", "OEEU", "OENA",
    "OPAF", "OPEC", "OPNO", "OPSA", "PERG", "NLDA", "HITZ", "USIQ", "SUN", "CSK", "DDR", "YUG", "SCG", "DEUW", "WAK",
    "GLP", "GUF", "MTQ", "REU", "ATA", "ESH", "GIB",
}
EIA_SKIP_RE = re.compile(r"^WP\d\d$")
EIA_OVERRIDE = {"XKS": "KOS"}
# BACI exporter/importer codes without a country entry
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trade"))
from clean import BULK, CODE_FIX, DROP, HOMOGENEOUS, LAST_DROPPED, LITHIUM_MIN_UV, PEER_RATIO, XAS, clean as clean_baci, year_list  # noqa: E402
import caveats as CV  # noqa: E402  (the registry of caveats, for the groups that have no lanes)
from hs_map import SPLIT as HS_SPLIT, SPLIT_NOT_READ as HS_NOT_READ  # noqa: E402  (HS 253090, read as spodumene for some pairs)
import checks as K  # noqa: E402  (labels, names and the records of pipeline/cache/trade_checks.json)
sys.path.insert(0, os.path.join(HERE, ".."))
from common import constants as CN  # noqa: E402  (physical and conventional constants, each with the page that gives it)
sys.path.insert(0, HERE)
import history as HI  # noqa: E402  (series by country and year, data/commodities/history)
import metals as MET  # noqa: E402  (metals pages: apparent consumption, concentration, value, six-digit split)
import monthly as MO  # noqa: E402  (monthly EIA series of the energy pages, data/commodities/monthly)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "freight"))
import modes as MD  # noqa: E402  (the mode rule of the lanes: sea, transit, mixed or land)
import us_lpg  # noqa: E402  (United States LPG exports to Mexico and Canada: EIA volumes and the Census Bureau's export file)
import aus_req_lng  # noqa: E402  (Australia's LNG exports by market, Resources and Energy Quarterly: the LNG page's cross-check)
import comtrade_tin  # noqa: E402  (China's declared imports of tin ores and concentrates, UN Comtrade: the tin page's table)
import metcoal  # noqa: E402  (metallurgical coal by pair from the exporters' own statistics: the Metallurgical coal page's Main flows)
import ports as PT  # noqa: E402  (sourced transit ports of landlocked countries)
import vessel_rules as VR  # noqa: E402
from build_lanes import FIRST_YEAR as LANE_FIRST_YEAR  # noqa: E402  (first year a page supports the reading of a group, with the reason)

BACI_OVERRIDE = CODE_FIX  # BACI "Other Asia, nes" = Taiwan (one mapping, pipeline/trade/clean.py)
# codes that are not countries of the index: territories without a polygon and the pseudo-place XAS
try:
    EXTRA_CODES = {p["c"] for p in json.load(open(os.path.join(ROOT, "pipeline", "geo", "places_extra.json"), encoding="utf-8"))}
except (OSError, ValueError, KeyError, TypeError):
    EXTRA_CODES = set()
EXTRA_CODES.add(XAS)
UNKNOWN = defaultdict(set)


def iso_from_name(name, source):
    k = fold(name)
    if k in AGGREGATE:
        return None
    if k in OVERRIDE:
        return OVERRIDE[k]
    if k in NAME2ISO:
        return NAME2ISO[k]
    UNKNOWN[source].add(name)
    return None


def check_unknown():
    if UNKNOWN:
        msg = "; ".join(f"{s}: {sorted(v)}" for s, v in UNKNOWN.items())
        raise SystemExit(f"UNKNOWN COUNTRY NAMES (add to OVERRIDE / AGGREGATE): {msg}")


# ====================================================================== helpers
def rnd(v):
    a = abs(v)
    if a >= 1000:
        return round(v, 1)
    if a >= 100:
        return round(v, 2)
    if a >= 1:
        return round(v, 3)
    return round(v, 4)


def sig(v, digits=3):
    """A figure the atlas estimated or converted keeps `digits` significant digits and no more (GW3.2)."""
    if not v:
        return v
    r = round(v, digits - 1 - int(math.floor(math.log10(abs(v)))))
    return int(r) if abs(r) >= 10 ** (digits - 1) else r


def joinn(a, b):
    """Two notes joined with "; ": the full stop that ends a sentence of `a` is dropped, so that no ".;" is written (GW3.8)."""
    if not a:
        return b
    return (a[:-1] if a.endswith(".") and not a.endswith("..") else a) + "; " + b


# The tonnage that moves both by sea and overland (split not known) is said beside the seaborne figure from this size, in Mt: the note below,
# the line and the year note of the commodity panel share it (web/src/lib/mixedShown.ts, MIXED_MIN_MT; a test ties the two constants)
MIXED_MIN_MT = 0.005


def fig(v, u, y, s, n=None):
    d = {"v": rnd(v), "u": u, "y": y, "s": s}
    if n:
        d["n"] = n
    return d


# the lines of a table may exceed the published (rounded) world total by this share before the shares move to the sum
LINES_OVER_WORLD = 5e-4


def ranked(rows, y, s, u, world=None, n=None, top=None, digits=None, other=0):
    """rows: list of (iso, value[, note[, est]]); returns a Ranked dict, every row with a value, largest first (the
    first `top` only when it is given).
    est: the row is mostly an Atlas estimate (`est: true`, value kept to 3 significant digits). digits: every value of the
    table, the world total included, is rounded to that many significant digits (a table of estimates or conversions).
    other: the source's own "Other countries" line, part of the lines but not of `rows`. When every line of the table
    adds up to more than the published world total (a rounded figure), the shares are computed on that sum, `world`
    holds it and `worldPublished` keeps the published total; the note says so (GR2.5)."""
    acc = {}
    for r in rows:
        c, v = r[0], r[1]
        if c is None or v is None or not (v > 0):
            continue
        note = r[2] if len(r) > 2 else None
        est = bool(r[3]) if len(r) > 3 else False
        if c in acc:
            raise SystemExit(f"duplicate row for {c} ({s} {y})")
        acc[c] = (v, note, est)
    srt = sorted(acc.items(), key=lambda kv: -kv[1][0])[:top]  # top None: every row
    out = {"y": y, "s": s, "u": u}
    if world is not None:
        lines = sum(v for v, _, _ in acc.values()) + (other or 0)
        published = None
        if world > 0 and lines > world * (1 + LINES_OVER_WORLD):
            published, world = world, lines
            n = (n + "; " if n else "") + (f"the country lines of the source add up to {_nf(lines)} {u}, more than the published world total of "
                                           f"{_nf(published)} {u}: shares are computed on the sum")
        out["world"] = sig(world, digits) if digits else rnd(world)
        if published is not None:
            out["worldPublished"] = sig(published, digits) if digits else rnd(published)
    out["rows"] = [({"c": c, "v": sig(v, digits or 3) if digits or est else rnd(v), **({"n": nt} if nt else {}), **({"est": True, "s": "atlas", "y": y} if est else {})})
                   for c, (v, nt, est) in srt]
    out["rows"] = [r for r in out["rows"] if r["v"]]  # a value that rounds to 0 in the table's unit is left to the world total
    if n:
        out["n"] = n
    return out


def total_of(rows):
    return sum(r[1] for r in rows if r[1] is not None and r[1] > 0)


def set_basis(t, basis):
    """Short qualifier of what a table measures ("gross weight", "contained copper"). build_profiles.py
    copies it onto the country-profile rows, where a tonnage would otherwise read as the finished commodity."""
    if t is not None and basis:
        t["basis"] = basis
    return t


def add_caveat(t, text):
    """A warning that belongs to a whole table: shown with the table note and copied to country-profile rows."""
    t["n"] = (t.get("n", "") + " · " if t.get("n") else "") + text
    t["caveat"] = (t["caveat"] + " " if t.get("caveat") else "") + text


COUNTRY_NAME = {}


def cname(iso):
    if not COUNTRY_NAME:
        COUNTRY_NAME.update({c["c"]: c["name"] for c in COUNTRIES})
    return COUNTRY_NAME.get(iso, iso)


def rice_adjust(psd, baci):
    """Paddy (HS 1006.10) is traded in the husk; the USDA tables of the rice page are milled basis. Each
    pair's paddy tonnage is converted with the USDA PSD milling rate of the exporter (world average where
    PSD has none). Husked rice (HS 1006.20) stays at customs weight: PSD gives no factor for it.
    Returns ({(o, d): (tonnes, note)}, paddy world tonnes, note for the page) or (None, None, note)."""
    path = os.path.join(CACHE, "baci_rice_forms.csv")
    if not os.path.exists(path):
        return None, None, "Customs flows add paddy (HS 1006.10) to milled rice at full weight: the paddy extract of the customs data is missing."
    f = pd.read_csv(path, dtype={"hs6": str})
    f = f[(f["year"] == BACI_YEAR) & (f["hs6"] == "100610")]
    if f.empty:
        warn(f"rice: no paddy rows for {BACI_YEAR} in baci_rice_forms.csv (run extract_rice_forms.py); flows left at customs weight")
        return None, None, f"Customs flows add paddy (HS 1006.10) to milled rice at full weight: no paddy extract for {BACI_YEAR}."
    rates, world_rate = psd.at(PSD_EST).milling_rates()  # the estimate year, as before the forecast year was shown
    tot = {(r["o"], r["d"]): r["t"] for _, r in baci.group("rice").iterrows()}
    out = {}
    for _, r in f.iterrows():
        k = (r["o"], r["d"])
        t = tot.get(k)
        if not t or r["t"] > t * 1.001:
            continue
        iso = BACI_OVERRIDE.get(r["o"], r["o"])
        rate = rates.get(iso)
        basis = f"the USDA PSD milling rate of {cname(iso)} ({rate:.2f}, market year {PSD_EST_LABEL})" if rate else None
        if rate is None:
            rate = world_rate
            basis = f"the world average USDA PSD milling rate ({rate:.2f}, market year {PSD_EST_LABEL})" if rate else None
        if rate is None:
            continue
        new = t - r["t"] * (1 - rate)
        if (t - new) / t < 0.005:  # under half a percent: the customs figure stands
            continue
        out[k] = (new, f"Atlas conversion, milled equivalent: CEPII BACI {BACI_YEAR} customs weight is {_fmt(t / 1e6)} Mt, of which {_fmt(r['t'] / 1e6)} Mt "
                       f"is paddy (HS 1006.10), converted at {basis}")
    paddy = float(f["t"].sum())
    note = (f"Customs flows cover HS 1006.10 to 1006.40. Paddy ({_fmt(paddy / 1e6)} Mt in {BACI_YEAR}, CEPII BACI) is converted to milled equivalent with the "
            f"USDA PSD milling rate of the exporter, so that flows compare with the milled-basis tables; such flows are marked Atlas conversion. "
            f"Husked rice (HS 1006.20) stays at customs weight. The seaborne total and the map lanes still use customs weight.")
    return out, paddy, note


# ====================================================================== USGS
class Usgs:
    def __init__(self):
        d = pd.read_csv(USGS_FILE, encoding="latin-1", dtype=str)
        d = d[d["Section"].str.startswith("World") & d["Statistics"].isin(["Production", "Reserves"])]
        d["Value"] = d["Value"].fillna("").str.strip()
        d["Country"] = d["Country"].str.strip()
        self.d = d

    @staticmethod
    def parse(v):
        v2 = v.replace(",", "")
        if re.fullmatch(r"\d+(\.\d+)?", v2):
            return "num", float(v2)
        m = re.fullmatch(r">\s*(\d+(\.\d+)?)", v2)
        if m:
            return "lb", float(m.group(1))
        return "skip", v

    def table(self, commodity, detail, year=USGS_YEAR, factor=1.0):
        """-> dict(rows=[(iso, value)], world, world_note, missing=[names], notes=set)"""
        d = self.d
        base = d[(d["Commodity"].str.startswith(commodity)) & (d["Year"] == year)]
        cty = base[base["Statistics_detail"] == detail]
        wrows = base[base["Statistics_detail"].isin([detail + ": rounded", detail + ", rounded", detail])
                     & (base["Country"] == "World total")]
        if cty.empty:
            raise SystemExit(f"USGS: no rows for {commodity} / {detail} / {year}")
        rows, missing, other_sum, estimated, est_isos, other_est = [], [], 0.0, False, set(), False
        for _, r in cty.iterrows():
            if r["Country"] in ("World total",):
                continue
            kind, v = self.parse(r["Value"])
            if r["Country"] == "Other countries":
                if kind == "num":
                    other_sum += v * factor
                    other_est = other_est or (isinstance(r["Notes"], str) and "Estimated" in r["Notes"])
                continue
            iso = iso_from_name(r["Country"], "usgs")
            if kind == "num":
                rows.append((iso, v * factor))
            elif re.search(r"\w", r["Value"]):  # blank = no figure at all (e.g. refiners that are not miners); W / ranges / words are listed
                missing.append(f"{r['Country']} ({r['Value']})")
            if isinstance(r["Notes"], str) and "Estimated" in r["Notes"]:
                estimated = True
                if iso and kind == "num":
                    est_isos.add(iso)  # the value is a USGS estimate ("Estimated." in the notes of the file), not the atlas's
        world, wnote = None, None
        for _, r in wrows.iterrows():
            kind, v = self.parse(r["Value"])
            if kind == "num":
                world = v * factor
            elif kind == "lb":
                world = v * factor
                wnote = f"USGS reports the world total as a minimum (>{r['Value'].lstrip('>').strip()})"
            if isinstance(r["Notes"], str):
                extra = r["Notes"].replace("Estimated.", "").replace("--", "").strip()
                if extra and "See Appendix" not in extra:
                    wnote = (wnote + "; " if wnote else "") + extra
        return {"rows": [r for r in rows if r[0]], "world": world, "wnote": wnote, "missing": missing,
                "other": other_sum, "estimated": estimated, "est_isos": est_isos, "other_est": other_est}

    def ranked(self, commodity, detail, u, factor, label, kind="production", full=False, year=USGS_YEAR):
        """Every country USGS gives, and USGS's 'Other countries' line as the field `other` (its own row of the table).
        full: if the countries and that line add up to more than 2% below the USGS world total, the shares are computed
        on their sum and the note says so. year: another year of the file (the series by country, history.py)."""
        t = self.table(commodity, detail, year=year, factor=factor)
        world = t["world"]
        n = [f"USGS MCS {USGS_EDITION}, {label}"]
        if kind == "production" and t["estimated"]:
            n.append(f"{USGS_YEAR} values are USGS estimates")
        sumrows = total_of(t["rows"]) + t["other"]
        published = world
        if world is None:
            world = sumrows
            n.append("world = sum of reporting countries incl. 'Other countries'")
        else:
            n.append("USGS world total is rounded")
            if sumrows > world * 1.02:
                warn(f"{commodity}/{detail}: sum of countries {sumrows:.0f} > world {world:.0f}")  # ranked() moves the shares to the sum
            elif t["other"] and sumrows < world * (1 - LINES_OVER_WORLD):  # "Other countries" covers every other producer: the lines are the whole
                n.append(f"the countries and USGS 'Other countries' add up to {_nf(sumrows)} {u}, while the rounded "
                         f"world total of {_nf(world)} {u} is {world / sumrows - 1:.1%} above that sum: shares are computed on the sum")
                world = sumrows
        if full and t["other"]:
            n.append(f"'Other countries' is the USGS line for the producers it does not list ({_nf(t['other'])} {u})")
        if t["wnote"]:
            n.append(t["wnote"].rstrip(". "))
        if t["missing"]:
            names = sorted(set(t["missing"]))
            n.append("not given as a number by USGS (W = withheld): " + ", ".join(names[:8]) + ("..." if len(names) > 8 else ""))
        out = ranked(t["rows"], int(year), "usgs-mcs", u, world=world, n="; ".join(n), other=t["other"])
        if t["other"]:
            out["other"] = rnd(t["other"])  # USGS's own "Other countries" line, as published
            hid = out["rows"][SHOWN_ROWS:]
            if hid:  # countries USGS names in the table that the page does not draw as a row of their own (GW3.5)
                out["hidden"] = {"v": rnd(sum(r["v"] for r in hid)), "k": len(hid), "from": SHOWN_ROWS,
                                 "n": f"{len(hid)} further countr{'y' if len(hid) == 1 else 'ies'} named by USGS ({_and([cname(r['c']) for r in hid])}), "
                                      "listed after the first rows; not part of USGS's 'Other countries' line"}
            if published is not None and world != published:
                out["worldPublished"] = rnd(published)  # the USGS world total as published; `world` is the sum the shares are computed on
        out["_srcest"] = t["est_isos"]
        out["_otherest"] = t["other_est"]  # the "Other countries" line is itself marked "Estimated." in the file

        def at(y):
            r, _ = self.ranked(commodity, detail, u, factor, label, kind, full, year=str(y))
            return r
        # the file holds the year before the edition's own year too: the series by country has both. The file marks values
        # "Estimated." one by one (srcEst); it gives no word such as "revised" for a year as a whole
        out["_hist"] = ([int(USGS_YEAR) - 1, int(USGS_YEAR)], at)
        out["_yl"] = {int(USGS_YEAR) - 1: f"as published in USGS MCS {USGS_EDITION}",
                      int(USGS_YEAR): f"as published in USGS MCS {USGS_EDITION}; the values it marks 'Estimated.' are its estimates"}
        return out, t


# ====================================================================== EIA
class Eia:
    NEED = {("57-1", "TBPD"), ("26-1", "BCM"), ("26-2", "BCM"), ("7-1", "MT"), ("7-2", "MT"), ("7-3", "MT"), ("7-4", "MT"),
            ("7-6", "MST"), ("130-1", "MT"), ("130-2", "MT"), ("130-3", "MT"), ("130-4", "MT"), ("5-2", "TBPD"),
            ("67-2", "MT"), ("62-2", "TBPD"), ("63-2", "TBPD"), ("65-2", "TBPD"), ("66-2", "TBPD"),
            ("14-1", "MT"), ("14-2", "MT"), ("26-4", "BCM"), ("26-3", "BCM"), ("57-1", "MT"),
            # refined products and LPG by country, natural gas plant liquids, nuclear capacity, coke, coal by rank (E1b)
            ("54-1", "TBPD"), ("67-1", "TBPD"), ("67-2", "TBPD"), ("58-1", "TBPD"), ("27-7", "MK"),
            ("21-1", "MT"), ("21-3", "MT"), ("21-4", "MT"), ("11-1", "MT"), ("12-1", "MT"), ("119-1", "MT")}

    def __init__(self):
        self.s = defaultdict(dict)  # (prefix, unit) -> code -> {year: value}
        with open(os.path.join(RAW, "eia", "INTL.txt"), encoding="utf-8") as f:
            for line in f:
                if '"series_id"' not in line or '.A"' not in line[:60]:
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                sid = o["series_id"]
                if not sid.endswith(".A"):
                    continue
                parts = sid[5:-2].split("-")
                if len(parts) != 4:
                    continue
                key = (parts[0] + "-" + parts[1], parts[3])
                if key not in self.NEED:
                    continue
                vals = {}
                for y, v in o["data"]:
                    if isinstance(v, (int, float)):
                        vals[int(y)] = float(v)
                self.s[key][parts[2]] = vals
        self.lpg_us = self._fill_lpg_us()

    def _fill_lpg_us(self):
        """EIA's LPG consumption in tonnes has no United States value after 2021, and its world total in tonnes leaves the country
        out from 2022 (the sum of the countries equals it), although the same series exist in thousand barrels per day for every year.
        The tonnes of 2021 break from the barrels per day of the same series (3.4 barrels per tonne against 11.6 in every year from
        1980 to 2019). Those years are the barrels per day figure converted at the ratio of EIA's own US series in both units.
        The world total of such a year is EIA's own world series in barrels per day converted at the same ratio when that agrees within
        1% with EIA's tonnes plus the United States; otherwise EIA's total with the United States put back, and only while EIA's total
        leaves it out (it equals the sum of the other countries within 0.5%: a corrected file is not counted twice).
        Returns {'ratio', 'from', 'to' (the run of years with that ratio), 'years': {year: (kb/d, Mt, EIA's own Mt or None)},
        'world': {year: {'how': 'bd' | 'added' | 'kept', 'eia': EIA's own world total in Mt, 'bd': its world kb/d or None}}}."""
        mt, bd = self.s[("67-2", "MT")], self.s[("67-2", "TBPD")]
        us_mt, us_bd = mt.get("USA", {}), bd.get("USA", {})
        days = lambda y: 366 if _isleap(y) else 365  # noqa: E731
        both = sorted(y for y in us_mt if y in us_bd and us_mt[y])
        ratios = sorted(us_bd[y] * days(y) / us_mt[y] for y in both)
        if not ratios:
            return None
        ratio = round(ratios[len(ratios) // 2], 2)
        same = sorted(y for y in both if abs(us_bd[y] * days(y) / us_mt[y] / ratio - 1) <= 0.005)
        if len(same) < 5:
            return None
        first = last = same[-1]
        while first - 1 in same:
            first -= 1
        if last - first < 4:  # a ratio that is not the series' own over a few years: no conversion
            return None
        years, worlds = {}, {}
        for y in sorted(us_bd):
            if y <= last or y not in mt.get("WORL", {}):
                continue
            own = us_mt.get(y)
            if own is not None and abs(us_bd[y] * days(y) / own / ratio - 1) < 0.25:  # a few per cent off (2020): EIA's own figure stands
                continue
            v = us_bd[y] * days(y) / ratio  # thousand barrels per day x days / barrels per tonne = thousand tonnes
            world = mt["WORL"][y]
            others = sum(x for iso, x in self.country_values(("67-2", "MT"), y) if iso != "USA")  # the countries, without the United States
            # EIA's total leaves the country out when it equals the sum of the others, and holds EIA's own figure when it equals that sum plus it
            holds = abs(others + (own or 0.0) - world) <= 0.005 * world
            new = world + v - (own or 0.0) if holds else world
            how = "added" if holds else "kept"
            w_bd = bd.get("WORL", {}).get(y)
            if holds and w_bd and abs(w_bd * days(y) / ratio / new - 1) <= 0.01:  # EIA's own world series in barrels per day supports it
                new, how = w_bd * days(y) / ratio, "bd"
            worlds[y] = {"how": how, "eia": world * 1e-3, "bd": w_bd, "incl": not holds and abs(others + v - world) <= 0.005 * world}
            mt["WORL"][y] = new
            us_mt[y] = v
            years[y] = (us_bd[y], v * 1e-3, None if own is None else own * 1e-3)
        mt["USA"] = us_mt
        return {"ratio": ratio, "from": first, "to": last, "years": years, "world": worlds}

    def latest_year(self, *keys):
        yrs = None
        for k in keys:
            w = self.s[k].get("WORL", {})
            ys = set(w)
            yrs = ys if yrs is None else yrs & ys
        return max(yrs)

    def country_values(self, key, year):
        out = []
        for code, vals in self.s[key].items():
            if year not in vals or vals[year] <= 0:
                continue
            if code in EIA_SKIP or EIA_SKIP_RE.match(code):
                continue
            iso = EIA_OVERRIDE.get(code, code)
            if iso not in ISO_SET:
                UNKNOWN["eia"].add(code)
                continue
            out.append((iso, vals[year]))
        return out

    def ranked(self, key, u, factor, label, year=None, n_extra=None):
        year = year or self.latest_year(key)
        rows = [(c, v * factor) for c, v in self.country_values(key, year)]
        world = self.s[key]["WORL"][year] * factor
        n = f"EIA International Energy Data, {label}; world total as published by EIA (all countries)"
        if n_extra:
            n += "; " + n_extra
        s = sum(v for _, v in rows)
        if s > world * 1.02:
            warn(f"EIA {key}: sum countries {s:.0f} > world {world:.0f}")
        out = ranked(rows, year, "eia-intl", u, world=world, n=n)
        if key == ("67-2", "MT") and self.lpg_us and year in self.lpg_us["years"]:
            kbd, _, own = self.lpg_us["years"][year]
            r_ = self.lpg_us["ratio"]
            if own is None:
                conv = f"EIA gives no tonnes for {year}"
            else:
                conv = (f"EIA gives {own:,.1f} Mt for {year}, {kbd * (366 if _isleap(year) else 365) / (own * 1e3):.1f} barrels per tonne of its own "
                        f"barrels per day against {r_:.2f} in every year from {self.lpg_us['from']} to {self.lpg_us['to']}, so it is not used")
            conv += (f": {kbd:,.0f} thousand barrels per day (EIA, the same series) at {r_:.2f} barrels per tonne, the ratio of its own "
                     "United States series in both units (Atlas conversion)")
            for r in out["rows"]:
                if r["c"] == "USA":
                    r["n"] = joinn(r.get("n"), conv)
                    r["conv"] = True  # the row is an Atlas conversion: the page marks it
            w = self.lpg_us["world"][year]
            out["n"] = out["n"].replace("world total as published by EIA (all countries)", self.lpg_world_note(year))
            out["conv"] = "United States and world total" if w["how"] != "kept" else "United States"
            if w["how"] != "kept":
                out["convWorld"] = True
        out["_hist"] = (list(range(HIST_FROM, year + 1)), lambda y: self.ranked(key, u, factor, label, year=y, n_extra=n_extra))
        return out

    def lpg_world_note(self, year, lead=True):
        """How the world total of the LPG consumption table of `year` is made, and what EIA's own total in tonnes is; `lead`: the
        sentence on the converted United States before it."""
        w, r_ = self.lpg_us["world"][year], self.lpg_us["ratio"]
        eia = f"EIA's own total in tonnes is {w['eia']:,.2f} Mt"
        us = "United States converted from barrels per day (Atlas conversion); " if lead else ""
        if w["how"] == "bd":
            return (f"{us}world total: EIA's world series in barrels per day ({w['bd']:,.0f} thousand) converted at {r_:.2f} barrels per tonne "
                    f"(Atlas conversion), which agrees within 1% with EIA's tonnes plus the United States ({eia}, which leaves the United States out "
                    "or holds a figure out of line for it)")
        if w["how"] == "added":
            return (f"{us}world total: EIA's tonnes ({eia}, which leave the United States out or hold a figure out of line for it) plus the "
                    "United States (Atlas conversion)")
        what = ("it already includes the United States (it equals the sum of its other countries plus the converted figure)" if w["incl"] else
                "it is not the sum of its other countries with or without the United States")
        return f"{us}world total as published by EIA ({eia}): {what}, so it is not changed"

    def minus(self, key_total, key_sub, u, factor, label, n_extra, year=None):
        """total minus subset per country (thermal coal = all coal minus metallurgical coal)."""
        latest = year is None
        year = year or self.latest_year(key_total, key_sub)
        tot = dict(self.country_values(key_total, year))
        sub = {c: v for c, v in self.country_values(key_sub, year)}
        rows = []
        for c, v in tot.items():
            d = v - sub.get(c, 0.0)
            if d < -1e-6:
                if latest:  # a past year of the series is not warned about: the page shows the latest year
                    warn(f"EIA thermal coal {c}: metallurgical {sub[c]:.0f} > total {v:.0f}; set to 0")
                d = 0
            rows.append((c, d * factor))
        world = (self.s[key_total]["WORL"][year] - self.s[key_sub]["WORL"][year]) * factor
        n = f"EIA International Energy Data, {label}; {n_extra}"
        out = ranked(rows, year, "eia-intl", u, world=world, n=n)
        out["_hist"] = (list(range(HIST_FROM, year + 1)), lambda y: self.minus(key_total, key_sub, u, factor, label, n_extra, year=y))
        return out


# ====================================================================== USDA PSD
# The rule behind the words "forecast" and "estimate" of a USDA table, said on the page (review GA1.8). The PSD file has no label column; USDA's
# World Agricultural Production circular (https://apps.fas.usda.gov/psdonline/circulars/production.pdf, read on 23 November 2026, issue WAP 11-26)
# heads the same two years "Prel." (2025/26) and "Proj." (2026/27) in its tables and writes "forecasts" and "estimates" in its text.
YK_RULE = ("The PSD file carries no label: the atlas calls the newest marketing year the forecast and the one before it the estimate (the atlas's words, while "
           "USDA's World Agricultural Production circular, https://apps.fas.usda.gov/psdonline/circulars/production.pdf, heads the same two years "
           "'Prel.' and 'Proj.' in its tables)")


class Psd:
    UNITS = {  # commodity -> (unit, factor to that unit from PSD unit, conversion note)
        "Coffee, Green": ("Mt", CN.MT_PER_1000_COFFEE_BAGS, "PSD reports 1000 60-kg bags; converted to Mt (1000 bags = 60 t)"),
        "Cotton": ("Mt", CN.MT_PER_1000_COTTON_BALES, "PSD reports 1000 480-lb bales; converted to Mt (1000 bales = 217.72 t)"),
    }

    ATTRS = ["Production", "Exports", "Imports", "Domestic Consumption", "Domestic Use", "Human Dom. Consumption", "Ending Stocks",
             "TY Exports", "TY Imports", "Milling Rate (.9999)", "Rough Production",
             # the balance of a crop page (Psd.balance)
             "Area Harvested", "Beginning Stocks", "Total Disappearance", "Crush", "Feed Dom. Consumption", "Feed Waste Dom. Cons.",
             "FSI Consumption", "Food Use Dom. Cons.", "Industrial Dom. Cons.", "Arabica Production", "Robusta Production",
             "Cane Sugar Production", "Beet Sugar Production", "Other Disappearance"]

    @staticmethod
    def read(first, last):
        d = pd.read_csv(os.path.join(RAW, "usda", "psd_csv", "psd_alldata.csv"), encoding="latin-1",
                        usecols=["Commodity_Description", "Country_Name", "Market_Year", "Calendar_Year", "Month",
                                 "Attribute_Description", "Unit_Description", "Value"])
        d = d[d["Market_Year"].between(first, last) & d["Attribute_Description"].isin(Psd.ATTRS)]
        return d[~d["Unit_Description"].isin(["(PERCENT)"])]

    def __init__(self, d=None, my=PSD_MY):
        """d: the rows of market year `my` (another market year of the file: the series by country, history.py)."""
        self.my = my
        self.label = f"{my}/{(my + 1) % 100:02d}"  # PSD_LABEL for the latest market year
        if d is None:
            d = self.read(my, my)
        self.d = d
        self.release = self.revision(d)  # newest revision of the whole file: build log only
        self.cache = {}
        self._years = None
        self.top = self  # the reader of the latest market year (at() sets it on the readers of earlier years)

    def at(self, my):
        """The table reader for another market year (the file is read once for every year from HIST_FROM to PSD_MY)."""
        if my == self.my:
            return self
        if self._years is None:
            allyears = self.read(HIST_FROM, PSD_MY)
            self._years = {int(y): Psd(x, int(y)) for y, x in allyears.groupby("Market_Year")}
            for p in self._years.values():
                p.top = self
        if my not in self._years:
            raise KeyError(my)
        return self._years[my]

    @staticmethod
    def revision(rows):
        rel = rows[["Calendar_Year", "Month"]].drop_duplicates().sort_values(["Calendar_Year", "Month"]).iloc[-1]
        return f"latest revision {int(rel['Calendar_Year'])}-{int(rel['Month']):02d}"

    def release_of(self, commodity):
        """PSD revises each commodity on its own calendar (coffee twice a year, grains monthly): the stamp
        printed with a table is the newest revision month of that commodity's rows for the market year."""
        return self.revision(self.d[self.d["Commodity_Description"] == commodity])

    def report_of(self, commodity):
        """The month of the USDA report that last revised the commodity's rows of this market year, read from the file's own
        Calendar_Year and Month columns: ("2026-11", "November 2026")."""
        x = self.d[self.d["Commodity_Description"] == commodity]
        rel = x[["Calendar_Year", "Month"]].drop_duplicates().sort_values(["Calendar_Year", "Month"]).iloc[-1]
        cy, m = int(rel["Calendar_Year"]), int(rel["Month"])
        return f"{cy}-{m:02d}", f"{MONTHS[m - 1]} {cy}"

    def kind(self):
        """What USDA calls this market year: the newest of the file is its forecast, the one before it its estimate (the file
        itself carries no label column); older years are its revised figures, with no label."""
        top = self.top.my
        return "forecast" if self.my == top else "estimate" if self.my == top - 1 else None

    def has_eu(self, commodity):
        """True when PSD carries a 'European Union' row for the commodity (cotton lists the members instead)."""
        x = self.d[self.d["Commodity_Description"] == commodity]
        return bool((x["Country_Name"] == "European Union").any())

    def has_uk(self, commodity):
        """True when PSD has a United Kingdom row for the commodity in this market year (from 2016/17 for most commodities)."""
        x = self.d[self.d["Commodity_Description"] == commodity]
        return bool((x["Country_Name"] == "United Kingdom").any())

    def trade_year_world(self, commodity, attr):
        """World total of the PSD trade-year attribute ('TY Exports' / 'TY Imports'), where PSD has one."""
        x = self.d[(self.d["Commodity_Description"] == commodity) & (self.d["Attribute_Description"] == "TY " + attr)]
        v = x["Value"].sum()
        return float(v) if len(x) and v > 0 else None

    def milling_rates(self):
        """Rice milling rate (milled / rough) per country, and the world average, from PSD 'Rice, Milled'."""
        x = self.d[self.d["Commodity_Description"] == "Rice, Milled"]
        rates = {}
        for _, r in x[x["Attribute_Description"] == "Milling Rate (.9999)"].iterrows():
            iso = iso_from_name(r["Country_Name"], "psd")
            if iso and r["Value"] > 0:
                rates[iso] = float(r["Value"]) / 10000.0
        rough = x[x["Attribute_Description"] == "Rough Production"]
        milled = x[(x["Attribute_Description"] == "Production") & x["Country_Name"].isin(set(rough[rough["Value"] > 0]["Country_Name"]))]
        world = float(milled["Value"].sum() / rough["Value"].sum()) if rough["Value"].sum() > 0 else None
        return rates, world

    def table(self, commodity, attr, myear=PSD_MY):
        x = self.d if myear == PSD_MY else None
        if x is None:
            raise ValueError
        x = x[(x["Commodity_Description"] == commodity) & (x["Attribute_Description"] == attr)]
        if x.empty:
            raise SystemExit(f"PSD: no rows for {commodity} {attr}")
        unit, factor, conv = self.UNITS.get(commodity, ("Mt", 0.001, None))
        rows = []
        for _, r in x.iterrows():
            v = r["Value"]
            if pd.isna(v) or v <= 0:
                continue
            iso = iso_from_name(r["Country_Name"], "psd")
            rows.append((iso, float(v) * factor, r["Country_Name"]))
        world = sum(r[1] for r in rows)  # includes the "Other" group (iso None)
        merged = defaultdict(float)  # e.g. legacy "Belgium-Luxembourg" is merged into BEL
        for c, v, _ in rows:
            if c:
                merged[c] += v
        return unit, conv, list(merged.items()), world

    def ranked(self, commodity, attr, what, extra=None):
        unit, conv, rows, world = self.table(commodity, attr)
        trade = attr in ("Exports", "Imports")
        k = self.kind()
        rel, rel_text = self.report_of(commodity)
        n = [f"USDA PSD, {commodity}, {what}, market year {self.label}{', ' + k if k else ''} (USDA report of {rel_text})"]
        if trade and self.has_eu(commodity):
            n.append("world = sum of reporting countries; EU counted as one entity (intra-EU trade excluded)")
        elif trade:
            n.append("world = sum of reporting countries; PSD lists the EU members one by one for this commodity")
        else:
            n.append("world = sum of reporting countries")
        if trade:
            n.append("local marketing years, which start in different months by country")
            ty = self.trade_year_world(commodity, attr)
            if ty:
                factor = self.UNITS.get(commodity, ("Mt", 0.001, None))[1]
                n.append(f"on the trade-year basis (PSD 'TY {attr}') the world total is {_fmt(ty * factor)} {unit}")
        if conv:
            n.append(conv)
        if extra:
            n.append(extra)
        if k and attr == "Production":  # said once on the first table of the page, and again with the balance
            n.append(YK_RULE)
        out = ranked(rows, self.label, "usda-psd", unit, world=world, n="; ".join(n))
        out["rel"] = rel
        if k:
            out["yk"] = k
        # PSD's European Union row is its own entity, whose membership changes: the name of each year, as the file shows it
        if any(r["c"] == "EU27" for r in out["rows"]):
            x = self.d[(self.d["Commodity_Description"] == commodity) & (self.d["Attribute_Description"] == attr) & (self.d["Value"] > 0)]
            if (x["Country_Name"] == "EU-25").any():
                out["_cl"] = {"EU27": "EU-25"}
            elif self.top.has_uk(commodity) and not self.has_uk(commodity):
                out["_cl"] = {"EU27": "European Union with the UK"}
            out["_clname"] = {"EU27": "European Union"}
            out["_clwhy"] = {"European Union with the UK": "until USDA PSD lists the United Kingdom as a row of its own"}
            out["_clleave"] = {"European Union with the UK": "GBR"}
        # what each market year of the series is, in USDA's words, and the month of the report that last revised it
        if self is self.top:
            words = {"forecast": "are USDA's forecast", "estimate": "are USDA's estimate"}
            yl = {}
            for my in range(HIST_FROM, PSD_MY + 1):
                try:
                    p = self.at(my)
                    yl[my] = f"{words.get(p.kind(), "are USDA's figures")}, last revised in the USDA report of {p.report_of(commodity)[1]}"
                except (KeyError, IndexError):
                    pass
            out["_yl"] = yl
        # market years HIST_FROM/.. to the latest one the tables show (PSD_MY, set in _latest_inputs only)
        out["_hist"] = (list(range(HIST_FROM, PSD_MY + 1)), lambda my: self.at(my).ranked(commodity, attr, what, extra)[0])
        return out, unit

    # What a balance line reads: (label, PSD attribute, line it hangs under). Lines of an attribute the crop does not have are left out.
    BALANCE_USES = [("Human consumption", "Human Dom. Consumption"), ("Other disappearance", "Other Disappearance"), ("Crush", "Crush"), ("Feed use", "Feed Dom. Consumption"), ("Feed and waste use", "Feed Waste Dom. Cons."),
                    ("Food, seed and industrial use", "FSI Consumption"), ("Food use", "Food Use Dom. Cons."),
                    ("Industrial use", "Industrial Dom. Cons.")]
    BALANCE_PARTS = [("Arabica", "Arabica Production"), ("Robusta", "Robusta Production"), ("Cane sugar", "Cane Sugar Production"),
                     ("Beet sugar", "Beet Sugar Production")]

    def _sum(self, commodity, attr, country=None):
        """Sum of an attribute over the countries of the file for this market year (the file has no world row), or of one country; None when there is no row."""
        x = self.d[(self.d["Commodity_Description"] == commodity) & (self.d["Attribute_Description"] == attr)]
        if country:
            x = x[x["Country_Name"] == country]
        return float(x["Value"].sum()) if len(x) else None

    def balance(self, commodity, use_attr):
        """The balance of a crop for the estimate year and the forecast year side by side: world sums of USDA PSD, China, the world
        without China, harvested area, yield, uses, ending stocks and the stocks-to-use ratio. Every line is a USDA figure except the
        yield and the ratios, which are arithmetic on two USDA figures of the same year (source `atlas`, not an estimate).
        Returns None when the file lacks a year."""
        years = [PSD_EST, PSD_MY]
        try:
            ps = [self.at(y) for y in years]
        except KeyError:
            return None
        unit, factor, _ = self.UNITS.get(commodity, ("Mt", 0.001, None))

        def get(attr, country=None, f=factor):
            v = [p._sum(commodity, attr, country) for p in ps]
            return None if any(x is None for x in v) else [x * f for x in v]

        rows = []

        def add(k, label, u, v, sub=False, derived=None):
            if v is None or not any(v):
                return
            r = {"k": k, "label": label, "u": u, "v": [rnd(x) for x in v]}
            if sub:
                r["sub"] = True
            if derived:
                r["s"], r["y"], r["n"] = "atlas", f"{ps[0].label} and {ps[1].label}", derived
            rows.append(r)

        area = get("Area Harvested", f=0.001)
        prod = get("Production")
        add("area", "Harvested area", "Mha", area)
        if area and prod and all(area):
            add("yield", "Yield", "t/ha", [round(a / b, 2) for a, b in zip(prod, area)], derived="Computed by the atlas: world production divided by world harvested area, both as USDA PSD publishes them")
        add("production", "Production", unit, prod)
        for label, attr in self.BALANCE_PARTS:
            add("part-" + attr, label, unit, get(attr), sub=True)
        add("begin", "Beginning stocks", unit, get("Beginning Stocks"))
        use = get(use_attr)
        add("use", "Domestic use", unit, use)
        for label, attr in self.BALANCE_USES:
            if attr != use_attr:
                add("use-" + attr, label, unit, get(attr), sub=True)
        add("exports", "Exports", unit, get("Exports"))
        es = get("Ending Stocks")
        add("stocks", "Ending stocks", unit, es)
        ratio_n = "Computed by the atlas: USDA PSD ending stocks divided by domestic use of the same market year (two published figures; not an estimate)"
        if es and use:
            add("stu", "Stocks-to-use", "%", [round(a / b * 100, 1) for a, b in zip(es, use)], derived=ratio_n)
        esc, usc = get("Ending Stocks", "China"), get(use_attr, "China")
        if esc is not None:
            add("stocks-cn", "Ending stocks, China", unit, esc, sub=True)
            if es:
                add("stocks-x", "Ending stocks, world excluding China", unit, [a - b for a, b in zip(es, esc)], sub=True, derived="Computed by the atlas: the world sum minus China, both USDA PSD figures of the same market year")
            if usc:
                add("stu-cn", "Stocks-to-use, China", "%", [round(a / b * 100, 1) for a, b in zip(esc, usc)], sub=True, derived=ratio_n)
                if es and use:
                    add("stu-x", "Stocks-to-use, world excluding China", "%", [round((a - b) / (c - d) * 100, 1) for a, b, c, d in zip(es, esc, use, usc)], sub=True,
                        derived=ratio_n + "; China's stocks and use taken out of both")
        # the world has no row in the file: it is the sum of the countries; a crop whose year lacks a China row has no China lines
        return {
            "s": "usda-psd",
            "years": [{"y": p.label, "yk": p.kind(), "rel": p.report_of(commodity)[0]} for p in ps],
            "rows": rows,
            "n": (f"USDA PSD, {commodity}: the world is the sum of the countries USDA lists (it gives no world row); domestic use is the PSD "
                  f"attribute '{use_attr}'. Stocks-to-use is ending stocks divided by domestic use, exports not counted"
                  + ("; USDA's own Stocks-to-Use attribute of a cotton country divides by domestic use plus exports" if commodity == "Cotton" else "")
                  + f". {YK_RULE}"),
        }


# ====================================================================== BACI
# Groups whose grades differ by more than the factor 20 of the unit-value flag, so that a low unit value is not a sign of a
# misreport: nickel ore is laterite at tens of USD per tonne and sulphide concentrate at over a thousand (audit C-037)
MIXED_GRADES = {"nickel-ore"}


def _kept_why(g):
    """Why a flow with an implausible unit value is left as reported (pipeline/trade/clean.py, rule 4)."""
    if g in HOMOGENEOUS:
        return "kept because the flow is below the USD 50 million correction rule"
    return "kept as reported: only gross errors (a unit value over 100 times off) are corrected outside the homogeneous groups"


class Baci:
    def __init__(self):
        df = pd.read_csv(os.path.join(CACHE, "baci_flows.csv.gz"))
        df = clean_baci(df)  # shared rules with build_lanes.py (pipeline/trade/clean.py)
        for _, (sg, sx, _, rest) in HS_SPLIT.items():  # a cache extracted under a wider exporter list is split again here (GW3.11)
            df.loc[(df["group"] == sg) & ~df["o"].isin(sx), "group"] = rest
        df["est"] = df["imputed"]
        ratio = df["uvr"]
        susp = (df["t0"] > 0) & ~df["imputed"] & df["uv"].notna() & ((ratio < 0.05) | (ratio > 20))
        susp &= ~df["group"].isin(MIXED_GRADES)
        df["susp"] = susp
        df["t_susp"] = df["t"].where(susp, 0.0)
        fix = df["imputed"]
        df["t_est"] = df["t"].where(fix, 0.0)
        df["t0_est"] = df["t0"].where(fix, 0.0)  # what the customs data declared for the rows the atlas re-estimated
        df["t_vol"] = df["t"].where(df["flag"] == "est-volume", 0.0)  # the part of it that is a volume of the United States' own statistics (rule 10)
        self.df = df
        self.dropped = list(LAST_DROPPED)  # rows that clean() dropped, for QA.md
        self.peer = dict(PEER_RATIO)  # rule 8: usual ratio of an exporter to its peer, for the page notes
        self._modes = {}
        self.lanes = {}
        ld = os.path.join(DATA, "freight", "lanes")
        for f in os.listdir(ld):
            if f.endswith(".json"):
                j = json.load(open(os.path.join(ld, f), encoding="utf-8"))
                # flows link to the lanes of the main set only (a history lane has no latest-year flow)
                self.lanes[j["group"]] = {"ids": {l["id"] for l in j["lanes"] if l["set"] == "main"}, "seaborne": j["seaborne"],
                                          "mixed": j.get("mixed"), "est": j.get("est"), "estVol": j.get("estVol"), "breakNote": j.get("breakNote"), "years": j["years"], "unit": j["unit"], "y": j["y"]}
        try:
            self.caveats = json.load(open(os.path.join(DATA, "freight", "caveats.json"), encoding="utf-8"))
        except (OSError, ValueError):
            self.caveats = {}
        self.file_caveats = set(self.caveats)
        # build_lanes.py writes the caveats of the lane groups only: those of the other groups come from the registry here
        for cid, e in CV.build(df[~df["group"].isin(self.lanes)], [], BACI_YEAR, psd=None).items():
            if e["group"] not in self.lanes:
                self.caveats.setdefault(cid, e)
        # pairs far below the usual unit value of their product (check K13), for the groups with lanes too: build_lanes.py writes them to
        # the file at its next run, and until then their text goes with the flow
        for cid, e in {**CV.unit_value_entries(df, BACI_YEAR), **CV.no_production_entries(df, BACI_YEAR)}.items():
            self.caveats.setdefault(cid, e)
        # entries of the registry that build_lanes.py has not written to the file yet, for the groups with lanes (a new entry waits for its next
        # run): their text goes with the row and the flows until then. Only the entries that need no check of the lanes' run (no `check`)
        for cid, e in CV.build(df[df["group"].isin(self.lanes)], [], BACI_YEAR, psd=None).items():
            if not e.get("check"):
                self.caveats.setdefault(cid, e)

    def mode(self, o, d, g):
        """Mode of a pair under the rule of the lanes (pipeline/freight/modes.py): (kind, transit row or None), or
        (None, None) for a group without a mode (precious metals: not modelled)."""
        k = (o, d, g)
        if k not in self._modes:
            m = MD.mode_of(o, d, g)
            tr = None
            if m and m.kind == "transit":
                end = o if not MD.coastal(o) else d
                # the lanes' lookup (pipeline/freight/ports.py): a row of the group, then of its family, for this partner
                row = PT.transit_for(end, MD.FAMILY.get(g), g, d if end == o else o)
                if row:
                    code = row[0]
                    c = PT.MANUAL[code][1] if code in PT.MANUAL else ISO_OF_A2.get(code[:2])
                    tr = {"port": code, "c": c, "s": row[1], **({"url": row[2]} if row[2] else {})}
            self._modes[k] = (m.kind if m else None, tr)
        return self._modes[k]

    def iso(self, code):
        code = BACI_OVERRIDE.get(code, code)
        if code in ISO_SET or code in EXTRA_CODES:
            return code
        UNKNOWN["baci"].add(code)
        return None

    def group(self, g, year=BACI_YEAR):
        return self.df[(self.df["group"] == g) & (self.df["year"] == year)]

    def ranked(self, g, side, u, div, what, extra=None, digits=None, year=BACI_YEAR):
        """year: another year of the cleaned frame, same rules and the same estimate marks (the series by country, history.py)."""
        d = self.group(g, year)
        col = "o" if side == "exports" else "d"
        agg = d.groupby(col).agg(t=("t", "sum"), te=("t_est", "sum"), tv=("t_vol", "sum"), t0e=("t0_est", "sum"), ts=("t_susp", "sum"),
                                 usd=("usd", "sum")).sort_values("t", ascending=False)
        world = agg["t"].sum() / div
        est_share = agg["te"].sum() / agg["t"].sum() if agg["t"].sum() else 0
        vol_share = agg["tv"].sum() / agg["t"].sum() if agg["t"].sum() else 0  # estimated from a volume (rule 10), not from the declared value
        rows, usd_by, es_by, t_by = [], {}, {}, {}
        for code, r in agg.iterrows():
            iso = None if code in EXTRA_CODES else self.iso(code)  # ranked tables (and country profiles) list countries of the index only
            if iso:
                usd_by[iso] = float(r["usd"])
                t_by[iso] = float(r["t"])
            es = r["te"] / r["t"] if r["t"] else 0
            if iso:
                es_by[iso] = float(es)
            note = None
            if code in BACI_OVERRIDE:
                note = f"BACI code {code} ('Other Asia, nes'), reported as Taiwan"
            mostly = es >= 0.5
            by_volume = bool(r["t"]) and r["tv"] / r["t"] >= es / 2  # most of the estimate is a volume of the United States' own statistics
            if mostly and by_volume:
                note = (note + "; " if note else "") + (f"Atlas estimate: {es * 100:.0f}% of this tonnage is estimated from the volume in the United States' own export statistics "
                                                        f"(customs declared {_fmts(r['t0e'] / div, u)} for these flows: {us_lpg.CAUSE}; see the notes of the page)")
            elif mostly:  # most of the tonnage is the atlas's own estimate (GW3.3): said first, with the method in a few words
                note = (note + "; " if note else "") + (f"Atlas estimate: {es * 100:.0f}% of this tonnage is estimated from the declared value "
                                                        f"(customs declared {_fmts(r['t0e'] / div, u)} for these flows; declared value divided by a reference unit value, see the notes of the page)")
            elif es >= 0.10:
                vs_row = r["tv"] / r["t"] if r["t"] else 0  # the part estimated from a volume (rule 10), the rest from the declared value
                note = (note + "; " if note else "") + (f"{es * 100:.0f}% of tonnage estimated: {vs_row * 100:.0f}% from the volume in the United States' own export statistics"
                                                        + (f", {(es - vs_row) * 100:.0f}% from value" if es - vs_row >= 0.005 else "") if vs_row >= 0.005
                                                        else f"{es * 100:.0f}% of tonnage estimated from value")
            ss = r["ts"] / r["t"] if r["t"] else 0
            if ss >= 0.10:
                note = (note + "; " if note else "") + f"{ss * 100:.0f}% of tonnage from flows with implausible unit values ({_kept_why(g)})"
            rows.append((iso, r["t"] / div, note, mostly))
        n = [f"CEPII BACI HS92 {what}, {year}, all transport modes, gross weight",
             "world = sum of all reported flows in the Atlas BACI extract (flows below 1,000 t and 1 M USD omitted)"]
        val_share = est_share - vol_share
        if est_share >= 0.10:  # a total that holds a tenth or more of estimated tonnage says so, and keeps three digits
            n.append(f"includes an Atlas estimate: {est_share * 100:.0f}% of world tonnage is estimated "
                     + ("from the declared value where the reported tonnage is missing or inconsistent" if vol_share < 0.01 else
                        f"({vol_share * 100:.0f}% from the volume in the United States' own export statistics, the rest from the declared value)") + " (world total rounded)")
        elif vol_share >= 0.01:
            n.append(f"{est_share * 100:.0f}% of world tonnage estimated: {vol_share * 100:.0f}% from the volume in the United States' own export statistics"
                     + (f", {val_share * 100:.0f}% from value where missing or inconsistent" if val_share >= 0.005 else ""))
        elif est_share >= 0.01:
            n.append(f"{est_share * 100:.0f}% of world tonnage estimated from value where missing or inconsistent")
        if extra:
            n.append(extra)
        t = ranked(rows, year, "baci", u, world=world, n="; ".join(n), digits=digits)
        if est_share >= 0.10:
            t["world"] = sig(world)
            t["_west"] = True  # the world total holds a tenth or more of Atlas estimates
        # declared value by country: the series by year keeps a jump of tonnage whose value moved with it (history.out_of_line)
        t["_usd"] = usd_by
        t["_es"], t["_usdw"] = es_by, float(agg["usd"].sum())  # the share of each row's tonnage that is estimated, and the world value (metals.add_values)
        t["_t"], t["_tw"] = t_by, float(agg["t"].sum())  # the unrounded tonnes, for the unit value (a row of 100 t is 0.0001 Mt in the table)
        if year == BACI_YEAR:
            # a group read from a code only from the year a page supports it (the lanes' FIRST_YEAR): the series starts there too
            first = LANE_FIRST_YEAR.get(g)
            t["_hist"] = ([y for y in self.years() if not first or y >= first[0]], lambda y: self.ranked(g, side, u, div, what, extra, digits, year=y)[0])
            if first:
                t["_hn"] = [first[1] + "."]
        return t, est_share

    def years(self):
        """Years of the series by country: HIST_FROM to the latest year of the cache."""
        return sorted(int(y) for y in self.df["year"].unique() if HIST_FROM <= y <= BACI_YEAR)

    def flows(self, g, u, div, lane_group=None, only_exporters=None, mode_all=None, n_all=None, adjust=None, only_pairs=None):
        """adjust: {(o, d): (tonnes, note)} replaces the customs tonnage of a pair by an Atlas figure
        (source id "atlas", with the note) before the flows are ranked. only_pairs: {(o, d)} keeps those pairs."""
        self.last_susp = []
        d = self.group(g)
        if only_exporters:
            d = d[d["o"].isin(only_exporters)]
        if only_pairs is not None:
            d = d[[k in only_pairs for k in zip(d["o"], d["d"])]]
        d = d.assign(adj=None)
        if adjust:
            keys = list(zip(d["o"], d["d"]))
            ok = [k in adjust and not imp for k, imp in zip(keys, d["imputed"])]  # tonnage already re-estimated from value: left alone
            d["t"] = [adjust[k][0] if a else t for k, a, t in zip(keys, ok, d["t"])]
            d["adj"] = [adjust[k][1] if a else None for k, a in zip(keys, ok)]
        d = d.sort_values("t", ascending=False).head(NFLOWS)
        lg = self.lanes.get(lane_group or g)
        out = []
        for _, r in d.iterrows():
            o, de = self.iso(r["o"]), self.iso(r["d"])
            if not o or not de:
                raise SystemExit(f"flow with unmapped country {r['o']}-{r['d']} in {g}")
            f = {"o": o, "d": de, "v": sig(r["t"] / div) if r["est"] or isinstance(r["adj"], str) else rnd(r["t"] / div), "u": u, "y": BACI_YEAR, "s": "baci"}
            f["usd"] = round(float(r["usd"]) * 1000)  # declared customs value, USD
            uv = MET.unit_value(r["usd"], r["t"], 1.0 if r["est"] or isinstance(r["adj"], str) else 0.0)  # none where the tonnage was computed from the value
            if uv:
                f["uv"] = uv
            kind, transit = self.mode(r["o"], r["d"], g)
            if mode_all:
                f["mode"] = mode_all
            elif kind:  # precious metals carry no mode: "mode not modelled"
                f["mode"] = "sea" if kind == "transit" else kind
                if transit:
                    f["transit"] = transit
            lid = f"{lane_group or g}:{r['o']}-{r['d']}"
            if lg and lid in lg["ids"]:
                f["lane"] = lid
            notes = []
            if kind == "transit" and not transit and not mode_all:
                notes.append("sea through a foreign port (not specified)")
            elif kind == "mixed" and not mode_all and MD.known_split(r["o"], r["d"], g, BACI_YEAR):
                ks = MD.known_split(r["o"], r["d"], g, BACI_YEAR)
                f["seaShare"] = round(ks[0], 2)  # the share the note below prints
                # the figure of the row is the pair in all modes; its lane is the part by sea (the other part is read as overland)
                notes.append(f"the figure is for all modes of transport, {_fmts(r['t'] * ks[0] / div, u)} of it by sea (the lane) and {_fmts(r['t'] * (1 - ks[0]) / div, u)} read as overland. "
                             + MD.split_note(ks[0], ks[1], BACI_YEAR, _fmts(r["t"] / div, u), (g, r["o"], r["d"])))
            elif kind == "mixed" and not mode_all:
                notes.append("customs total for all modes: this trade moves both by sea and overland and the split is not known")
            if r["est"]:
                # an Atlas estimate: the tonnage is computed from the declared value (pipeline/trade/clean.py)
                f["s"], f["est"] = "atlas", True
                if "est-volume" in str(r.get("flag") or ""):
                    f["estBy"] = "volume"  # made from a volume in the United States' own export statistics, not from the declared value (rule 10)
                if r.get("capped") is True or r.get("capped") == True:  # noqa: E712 (a missing value of another group is NaN)
                    f["cap"], f["v"] = True, rnd(r["t"] / div)
                notes.append(r["enote"] if isinstance(r.get("enote"), str) and r["enote"] else "Atlas estimate: tonnage estimated from declared value")
            if notes:
                f["n"] = "; ".join(notes)
            cv = self.caveat_of(g, r["o"], r["d"])
            if cv in self.file_caveats:
                f["caveat"] = cv
            elif cv:  # a caveat of a group without lanes is not in data/freight/caveats.json: its text goes with the flow
                f["n"] = joinn(f.get("n"), self.caveats[cv]["text"])
            if r["susp"]:
                ref = "tonne-weighted median" if g in BULK else "median"
                msg = (f"reported tonnage implies {r['usd'] * 1000 / r['t0']:,.0f} USD/t, i.e. {r['uvr']:.4f}x the {g} group-year {ref} unit value: "
                       f"possible misreport, {_kept_why(g)}")
                f["n"] = joinn(f.get("n"), msg)
                self.last_susp.append(f"{cname(o)} to {cname(de)}: {rnd(r['t'] / div)} {u} of {g} in {BACI_YEAR} ({msg}).")
            if n_all:
                f["n"] = joinn(f.get("n"), n_all)
            if isinstance(r["adj"], str):
                f["s"] = "atlas"
                f["n"] = joinn(r["adj"], f["n"]) if "n" in f else r["adj"]
            out.append(f)
        return out

    def caveat_of(self, g, o, d):
        """Id of the caveat of data/freight/caveats.json that applies to a pair (one for the pair wins)."""
        best = None
        for cid, e in self.caveats.items():
            if e["group"] == g and e["o"] == o and e.get("d") in (None, d):
                if e.get("d") == d:
                    return cid
                best = best or cid
        return best

    def seaborne(self, g, label=None):
        lg = self.lanes.get(g)
        if not lg:
            return None
        v = lg["seaborne"][-1]
        n = (f"seaborne subset of BACI flows ({g}) under the atlas's mode rule (method in the About window): trade by sea, "
             "or by sea through a foreign port for a landlocked country")
        u = lg.get("unit") or "Mt"  # a group under 1 Mt a year is published in kt by the lanes builder
        mx = (lg.get("mixed") or [0])[-1]
        if mx and mx >= MIXED_MIN_MT * (1000 if u == "kt" else 1):
            n += f"; {_fmts(mx, u, under=0.05)} that move both by sea and overland (split not known) are not in it"
        if lg.get("est") and lg["est"] >= 0.01:
            vol = lg.get("estVol") or 0  # the part made from a volume in the United States' own export statistics (rule 10)
            n += (f"; {lg['est'] * 100:.0f}% of this tonnage is an Atlas estimate: {vol * 100:.0f}% from a volume in the United States' own export statistics"
                  + (f", {(lg['est'] - vol) * 100:.0f}% from value" if lg["est"] - vol >= 0.005 else "") if vol >= 0.005
                  else f"; {lg['est'] * 100:.0f}% of this tonnage estimated from value")
        if lg.get("breakNote"):
            n += "; " + lg["breakNote"]
        if label:
            n += "; " + label
        return fig(v, u, lg["y"], "baci", n)

    def totals(self, g, side):
        d = self.group(g)
        col = "o" if side == "exports" else "d"
        return (d.groupby(col)["t"].sum() / 1e6).to_dict()


# ====================================================================== external: WNA, FAOSTAT
def wna_uranium():
    j = json.load(open(os.path.join(CACHE, "wna_uranium.json"), encoding="utf-8"))
    yi = j["years"].index(max(j["years"]))
    y = j["years"][yi]
    rows = []
    for name, vals in j["rows"].items():
        if name in ("World total tU", "Others"):
            continue
        est = "(est.)" in name
        clean = name.replace("(est.)", "").strip()
        iso = iso_from_name(clean, "wna")
        v = vals[yi]
        if iso and v:
            rows.append((iso, v, "WNA estimate" if est else None))
    world = j["rows"]["World total tU"][yi]
    n = (f"World Nuclear Association, 'World Uranium Mining Production' (page updated {j['updated']}); mine production, tonnes U; "
         "figures are liable to change; world total as published (includes 'Others')")
    return ranked(rows, y, "wna", "tU", world=world, n=n)


def faostat_cocoa():
    codes = {}
    with open(os.path.join(CACHE, "baci_country_codes.csv"), encoding="utf-8") as f:  # committed copy of the BACI table
        for r in csv.DictReader(f):
            codes[int(r["country_code"])] = r["country_iso3"]
    fo_override = {}  # FAO M49 code -> ISO3 where it differs from the BACI numeric code
    rows = []
    world = None
    with open(os.path.join(CACHE, "faostat_cocoa_production.csv"), encoding="utf-8") as f:  # latest year with a world total
        year = max(r["year"] for r in csv.DictReader(f) if r["area"] == "World" and r["value_t"].strip())
    with open(os.path.join(CACHE, "faostat_cocoa_production.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["year"] != year:
                continue
            if not r["value_t"].strip():
                continue
            v = float(r["value_t"])
            m49 = int(r["m49"])
            if r["area"] == "World":
                world = v / 1e6
                continue
            if r["area"] in FAO_AGG or m49 >= 900:
                continue
            iso = fo_override.get(m49) or codes.get(m49)
            if not iso or iso not in ISO_SET:
                iso = NAME2ISO.get(fold(r["area"])) or OVERRIDE.get(fold(r["area"]))
            if not iso or iso not in ISO_SET:
                UNKNOWN["faostat"].add(f"{r['area']} ({r['m49']})")
                continue
            rows.append((iso, v / 1e6, "FAO flag: " + r["flag"] if r["flag"] in ("E", "X", "I") else None))
    n = (f"FAOSTAT QCL, cocoa beans (item 661), production, {year}; tonnes converted to Mt; world total as published by FAO "
         "(note flags: E estimated, I imputed, X from international organisations; A official)")
    return ranked(rows, int(year), "faostat", "Mt", world=world, n=n)


# International Cocoa Organization (ICCO): world gross production of cocoa beans per crop year (October to September), read on
# the news pages of its Quarterly Bulletin of Cocoa Statistics; the country tables are sold by subscription and are not copied.
# (crop year, thousand tonnes, issue read, page)
ICCO_COCOA = [
    ("2023/24", 4362, "May 2026 issue", "https://www.icco.org/may-2026-quarterly-bulletin-of-cocoa-statistics/"),
    ("2024/25", 4733, "August 2026 issue", "https://www.icco.org/august-2026-quarterly-bulletin-of-cocoa-statistics/"),
]


# The ICCO's world grindings of the latest crop year it gives, one headline figure read on the same news pages (the August 2026 issue says:
# "World Grindings fell by 3.3% year-on-year to 4.649 million tonnes"); the grindings by country are sold by subscription and are not copied.
# (crop year, thousand tonnes, change on the year before in percent, issue read, page, how the page calls the figure: that page introduces the
# 2024/25 data with "data for the 2024/25 season are estimated as:")
ICCO_GRINDINGS = ("2024/25", 4649, -3.3, "August 2026 issue", "https://www.icco.org/august-2026-quarterly-bulletin-of-cocoa-statistics/", "estimated")


def cocoa_vs_icco(d):
    """The FAOSTAT cocoa production table against the ICCO's world totals: (discrepancy text, table warning, Indonesia row note)."""
    t = d["production"]
    fao = t["world"] * 1000  # kt
    (cy, cv, issue, url), (cy2, cv2, issue2, url2) = ICCO_COCOA
    gap = fao / cv - 1
    text = (f"World cocoa bean production: FAOSTAT gives {_nf(fao)} kt for calendar year {t['y']} (the table above). The International Cocoa Organization "
            f"(ICCO) estimates {_nf(cv)} kt for the {cy} crop year, October to September ({issue} of its Quarterly Bulletin of Cocoa Statistics, {url}) and "
            f"{_nf(cv2)} kt for {cy2} ({issue2}, {url2}); the FAOSTAT total is {gap:.0%} above the first and {fao / cv2 - 1:.0%} above the second. "
            "The two series differ in period (calendar year against crop year); the cause of the gap is not established here. The ICCO's country tables are sold by "
            "subscription: they are not copied or compared here.")
    warn = f"World total {gap:.0%} above the ICCO's estimate for the {cy} crop year ({_nf(cv)} kt): see the discrepancies."
    short = f"ICCO: {_nf(cv)} kt for the {cy} crop year (see the discrepancies)"
    idn = None
    path = os.path.join(CACHE, "faostat_cocoa_production.csv")
    with open(path, encoding="utf-8") as f:
        ser = {r["year"]: (r["value_t"], r["flag"]) for r in csv.DictReader(f) if r["area"] == "Indonesia"}
    row = next((r for r in t["rows"] if r["c"] == "IDN"), None)
    if row:
        idn = "Official national figure carried by FAO (flag " + ser.get(str(t["y"]), ("", "?"))[1] + ")"
        ys = sorted(ser)
        same = [(a, y) for a, y in zip(ys, ys[1:]) if ser[a][0] == ser[y][0]]
        if same:
            idn += f"; FAOSTAT carries the same value for {same[0][0]} and {same[0][1]}"
        idn += ". Not checked against the ICCO's country table, which is not free; see the discrepancies."
    return text, warn, idn, short


FAO_AGG = {"Africa", "Americas", "Asia", "Europe", "Oceania", "Eastern Africa", "Middle Africa", "Western Africa", "Southern Africa",
           "Northern Africa", "Central America", "Caribbean", "South America", "Northern America", "Central Asia", "Eastern Asia",
           "Southern Asia", "South-eastern Asia", "Western Asia", "Eastern Europe", "Northern Europe", "Southern Europe",
           "Western Europe", "Melanesia", "Micronesia", "Polynesia", "Australia and New Zealand", "European Union (27)",
           "Land Locked Developing Countries (LLDCs)", "Least Developed Countries (LDCs)", "Small Island Developing States (SIDS)",
           "Low Income Food Deficit Countries (LIFDCs)", "Net Food Importing Developing Countries (NFIDCs)"}


_FAO_CODES = {}


def fao_iso(m49, area):
    """ISO3 of a FAOSTAT area: its M49 code through the BACI table, else its name. None for an aggregate; an unknown name is recorded in UNKNOWN."""
    if not _FAO_CODES:
        with open(os.path.join(CACHE, "baci_country_codes.csv"), encoding="utf-8") as f:
            _FAO_CODES.update({int(r["country_code"]): r["country_iso3"] for r in csv.DictReader(f)})
    m = int(m49)
    if area in FAO_AGG or m >= 900 or area == "Faroe Islands":  # a territory the atlas has no country for
        return None
    iso = {840: "USA", 158: "TWN"}.get(m) or _FAO_CODES.get(m)  # BACI numbers the United States 842 and Taiwan 490
    if not iso or iso not in ISO_SET:
        iso = NAME2ISO.get(fold(area)) or OVERRIDE.get(fold(area))
    if not iso or iso not in ISO_SET:
        UNKNOWN["faostat-rfb"].add(f"{area} ({m49})")
        return None
    return iso


def faostat_fertilizer(item):
    """Production of one fertiliser in tonnes of product, {year: {iso: (tonnes, flag)}}, from pipeline/cache/faostat_fertilizer_production.csv
    (FAOSTAT Fertilizers by Product; item 4001 urea, 4016 potassium chloride)."""
    out = defaultdict(dict)
    with open(os.path.join(CACHE, "faostat_fertilizer_production.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["item"] != item:
                continue
            iso = fao_iso(r["m49"], r["area"])
            if not iso:
                continue
            y = int(r["year"])
            if iso in out[y]:
                raise SystemExit(f"FAOSTAT fertilizer {item}: two areas for {iso} in {y}")
            out[y][iso] = (float(r["value_t"]), r["flag"])
    return out


def fertilizer_year(by):
    """FAOSTAT gives no world row and the countries that report change from year to year (its 2024 urea table has no China): the
    year of a table is the latest of the five most recent years whose reported total is at least 80% of the best of the five."""
    ys = sorted(by)[-5:]
    tot = {y: sum(v for v, _ in by[y].values()) for y in ys}
    best = max(tot.values())
    return max(y for y in ys if tot[y] >= 0.8 * best)


def faostat_urea(baci):
    """Urea production in tonnes of product, FAOSTAT (reporting countries only, no world total), and the notes on what is missing."""
    by = faostat_fertilizer("4001")
    y = fertilizer_year(by)
    rows = [(iso, v / 1e6, f"FAO flag: {fl}" if fl in ("E", "X", "I") else None) for iso, (v, fl) in by[y].items()]
    n = (f"FAOSTAT Fertilizers by Product (RFB), urea, production in tonnes of product, {y}, converted to Mt; reporting countries only, no world total "
         "(note flags: E estimated, I imputed, X from international organisations; A official)")
    t = set_basis(ranked(rows, y, "faostat-rfb", "Mt", n=n), "urea, product weight")
    notes = []
    exp = baci.totals("urea", "exports")
    gone = sorted(((c, v) for c, v in exp.items() if v >= 1 and c not in by[y]), key=lambda kv: -kv[1])
    if gone:
        names = [cname(c) for c, _ in gone[:6]] + ([f"{len(gone) - 6} other countries"] if len(gone) > 6 else [])
        txt = (f"FAOSTAT has no {y} urea production figure for {_and(names)}, which each exported more than 1 Mt of urea "
               f"in the customs data for {BACI_YEAR} (the largest exporters first): the urea producers table lists reporting countries only and gives no world total.")
        earlier = [(c, by[y - 1][c][0] / 1e6) for c, _ in gone if c in by.get(y - 1, {}) and by[y - 1][c][0] >= 1e6]
        if earlier:
            txt += f" For {y - 1} it gives {_and([f'{cname(c)} {_nf(v)} Mt' for c, v in earlier])}."
        notes.append(txt)
    late = max(by)
    if late != y:
        top = [c for c, _ in sorted(by[y].items(), key=lambda kv: -kv[1][0])[:3] if c not in by[late]]
        notes.append(f"FAOSTAT's {late} urea table is not used: it lists {len(by[late])} countries against {len(by[y])} for {y}"
                     + (f" and has no figure for {_and([cname(c) for c in top])}" if top else "") + ".")
    return t, notes


def faostat_potash_note(baci, k2o):
    """FAOSTAT production of potassium chloride in product tonnes beside the customs exports of the same countries: a check on the unit
    conversion of the production table, not a table (the countries that report change from year to year)."""
    by = faostat_fertilizer("4016")
    y = fertilizer_year(by)
    exp = baci.totals("potash", "exports")
    have = [r["c"] for r in k2o["rows"] if r["c"] in by[y] and by[y][r["c"]][0] >= 1e6][:2]
    if not have:
        return None
    gone = [r["c"] for r in k2o["rows"][:5] if r["c"] not in by[y]]
    txt = (f"FAOSTAT (Fertilizers by Product, RFB) gives {y} production of potassium chloride in tonnes of product: "
           + _and([f"{cname(c)} {_nf(by[y][c][0] / 1e6)} Mt (customs exports in {BACI_YEAR}: {_nf(exp.get(c, 0))} Mt)" for c in have]) + f". It lists {len(by[y])} countries"
           + (f", with no figure for {_and([cname(c) for c in gone])}," if gone else "") + " so it is not used for the table.")
    return txt


# ====================================================================== commodity specs
# trade group per commodity (BACI group of pipeline/trade/hs_map.py), unit and divisor from tonnes
MT, KT, T = ("Mt", 1e6), ("kt", 1e3), ("t", 1.0)

TRADE = {
    # id: (group, (unit, div), what)
    "crude-oil": ("crude-oil", MT, "crude oil (HS 2709)"),
    "refined-products": ("refined-products", MT, "refined petroleum products (HS 2710)"),
    "lng": ("lng", MT, "LNG (HS 271111)"),
    "natural-gas": ("natural-gas", MT, "natural gas in gaseous state (HS 271121, pipeline)"),
    "lpg": ("lpg", MT, "LPG: propane and butanes (HS 271112, 271113)"),
    "thermal-coal": ("coal", MT, "coal and lignite, thermal and metallurgical together (HS 270111, 270112, 270119, 270210, 270220)"),
    "uranium": ("uranium", KT, "uranium ores and natural uranium compounds (HS 261210, 284410)"),
    "iron-ore": ("iron-ore", MT, "iron ore (HS 260111, 260112)"),
    "steel": ("steel", MT, "steel products (HS 72 excl. 7201-7205)"),
    "copper": ("copper-ore", MT, "copper ores and concentrates (HS 2603)"),
    "aluminium": ("aluminium", MT, "unwrought aluminium (HS 7601)"),
    "bauxite": ("bauxite", MT, "bauxite (HS 2606)"),
    "nickel": ("nickel-ore", MT, "nickel ores and concentrates (HS 2604)"),
    "zinc": ("zinc-ore", MT, "zinc ores and concentrates (HS 2608)"),
    "lead": ("lead-ore", MT, "lead ores and concentrates (HS 2607)"),
    "tin": ("tin-metal", KT, "unwrought tin (HS 8001)"),
    "lithium": ("lithium", KT, "lithium carbonate, oxide and hydroxide (HS 283691, 282520)"),
    "cobalt": ("cobalt", KT, "cobalt intermediates, unwrought cobalt, scrap and powders (HS 810510), with ores and concentrates (HS 260500)"),
    "rare-earths": ("rare-earths", KT, "rare-earth metals and compounds (HS 280530, 284610, 284690)"),
    "manganese": ("manganese", MT, "manganese ores (HS 2602)"),
    "gold": ("gold", T, "non-monetary gold (HS 710811-710813)"),
    "silver": ("silver", T, "silver (HS 710610, 710691, 710692)"),
    "pgm": ("pgm", T, "platinum-group metals (HS 7110)"),
    "wheat": ("wheat", MT, "wheat (HS 1001)"),
    "corn": ("corn", MT, "maize (HS 100590)"),
    "soybeans": ("soybeans", MT, "soybeans (HS 120100)"),
    "soymeal": ("soymeal", MT, "soybean meal (HS 230400)"),
    "soyoil": ("soyoil", MT, "soybean oil (HS 1507)"),
    "rice": ("rice", MT, "rice (HS 1006)"),
    "sugar": ("sugar", MT, "cane and beet sugar (HS 1701)"),
    "coffee": ("coffee", MT, "green coffee (HS 090111, 090112)"),
    "cocoa": ("cocoa", MT, "cocoa beans (HS 1801)"),
    "cotton": ("cotton", MT, "raw cotton (HS 5201)"),
    "palm-oil": ("palm-oil", MT, "palm oil (HS 1511)"),
    "rapeseed": ("rapeseed", MT, "rapeseed (HS 1205)"),
    "potash": ("potash", MT, "potassium chloride (HS 310420)"),
    "phosphate": ("phosphate-rock", MT, "natural phosphates (HS 2510)"),
    "urea": ("urea", MT, "urea (HS 310210)"),
    "npk": ("npk", MT, "NPK compound fertilisers (HS 310520)"),
    "sulphur": ("sulphur", MT, "sulphur: crude or unrefined, sublimed, precipitated and colloidal (HS 250310, 250390, 280200)"),
    # the grains, oilseeds and pulses added with M-023 (barley, sorghum and the sunflower seed have PSD balances; pulses have none)
    "barley": ("barley", MT, "barley (HS 100300)"),
    "sorghum": ("sorghum", MT, "grain sorghum (HS 100700)"),
    "sunflower": ("sunflower-seed", MT, "sunflower seed (HS 120600)"),
    "pulses": ("pulses", MT, "dried pulses, shelled (HS 0713)"),
    # the metal bulks added with A-010. The ferro-alloys page opens on ferro-chromium, the largest of its alloys, the others follow as extra tables
    "ferrous-scrap": ("ferrous-scrap", MT, "ferrous waste and scrap (HS 7204)"),
    "pig-iron": ("pig-iron", MT, "pig iron, alloy pig iron and spiegeleisen (HS 7201)"),
    "chromium": ("chromium-ore", MT, "chromium ores and concentrates (HS 2610)"),
    "ferro-alloys": ("ferro-chromium", MT, "ferro-chromium (HS 720241, 720249)"),
    "molybdenum": ("molybdenum-ore", KT, "molybdenum ores and concentrates, roasted or not (HS 261310, 261390)"),
    "graphite": ("graphite", KT, "natural graphite, in powder or flakes and in other forms (HS 250410, 250490)"),
}

PSD = {  # id -> PSD commodity, domestic-consumption attribute, exports attr
    "wheat": ("Wheat", "Domestic Consumption", "Exports", "Imports"),
    "corn": ("Corn", "Domestic Consumption", "Exports", "Imports"),
    "soybeans": ("Oilseed, Soybean", "Domestic Consumption", "Exports", "Imports"),
    "soymeal": ("Meal, Soybean", "Domestic Consumption", "Exports", "Imports"),
    "soyoil": ("Oil, Soybean", "Domestic Consumption", "Exports", "Imports"),
    "rice": ("Rice, Milled", "Domestic Consumption", "Exports", "Imports"),
    "sugar": ("Sugar, Centrifugal", "Human Dom. Consumption", "Exports", "Imports"),
    "coffee": ("Coffee, Green", "Domestic Consumption", "Exports", "Imports"),
    "cotton": ("Cotton", "Domestic Use", "Exports", "Imports"),
    "palm-oil": ("Oil, Palm", "Domestic Consumption", "Exports", "Imports"),
    "rapeseed": ("Oilseed, Rapeseed", "Domestic Consumption", "Exports", "Imports"),
    "barley": ("Barley", "Domestic Consumption", "Exports", "Imports"),
    "sorghum": ("Sorghum", "Domestic Consumption", "Exports", "Imports"),
    "sunflower": ("Oilseed, Sunflowerseed", "Domestic Consumption", "Exports", "Imports"),
}
# sub-heading of the commodity list under "Softs & agriculture" (index.json `sub`, shown by SidePanel.tsx before the first commodity that has it)
INDEX_SUB = {"potash": "Fertilisers", "phosphate": "Fertilisers", "urea": "Fertilisers", "npk": "Fertilisers", "sulphur": "Fertilisers"}

# Customs groups that are a further pair of trade tables of a page (the fertilisers, audit M-022; the products of the grains and oilseeds,
# M-023): page id -> [(customs group, stem of the table keys, name in the table titles, what the code holds)]. The keys are "<stem>-exports"
# and "<stem>-imports": the page lists them under its exporters and importers, the country pages draw a line from each, and
# build_profiles.py EXTRA_SIDE names the customs group of the line. Each code belongs to one group and each group to one page
# (pipeline/trade/hs_map.py); a page that needs a product of another page links to it.
EXTRA_GROUPS = {
    "urea": [
        ("ammonia", "ammonia", "Ammonia", "anhydrous ammonia (HS 281410)"),
        ("ammonium-nitrate", "ammonium-nitrate", "Ammonium nitrate", "ammonium nitrate, solid or in solution (HS 310230)"),
        ("ammonium-nitrate-limestone", "an-limestone", "Ammonium nitrate with limestone",
         "ammonium nitrate mixed with calcium carbonate or other inorganic substances that carry no fertilising element, such as calcium ammonium nitrate (HS 310240)"),
        ("uan", "uan", "UAN solution", "urea and ammonium nitrate mixtures in aqueous or ammoniacal solution, UAN (HS 310280)"),
        ("ammonium-sulphate", "ammonium-sulphate", "Ammonium sulphate", "ammonium sulphate (HS 310221)"),
    ],
    "phosphate": [
        ("dap", "dap", "DAP", "diammonium phosphate, DAP (HS 310530)"),
        ("monoammonium-phosphate", "map", "MAP", "monoammonium phosphate, MAP, and its mixtures with DAP (HS 310540)"),
        ("superphosphates", "superphosphates", "Superphosphate", "superphosphates, single and triple (HS 310310)"),
        ("phosphoric-acid", "phosphoric-acid", "Phosphoric acid", "phosphoric acid and polyphosphoric acids (HS 280920)"),
    ],
    "potash": [
        ("potassium-sulphate", "sop", "Potassium sulphate (SOP)", "potassium sulphate, SOP (HS 310430)"),
    ],
    # the compounds with two of the three nutrients; the page's main table is the three-nutrient grades (HS 310520)
    "npk": [
        ("npk-two-nutrient", "two-nutrient", "Two-nutrient compound fertilisers",
         "compound fertilisers with two of the three nutrients: nitrates and phosphates (HS 310551), nitrogen and phosphorus other than those (HS 310559), "
         "phosphorus and potassium (HS 310560)"),
    ],
    # wheat flour and the dregs are tables only: bagged or boxed for a large part, so no lanes (pipeline/freight/build_lanes.py GROUPS)
    "wheat": [
        ("wheat-flour", "flour", "Wheat flour", "wheat or meslin flour (HS 110100)"),
    ],
    "corn": [
        ("brewing-distilling-dregs", "dregs", "Brewing and distilling dregs", "brewing or distilling dregs and waste, the code of distillers' dried grains (HS 230330)"),
    ],
    "sunflower": [
        ("sunflower-oil", "sunflower-oil", "Sunflower and safflower oil", "sunflower-seed or safflower oil, crude and other (HS 151211, 151219)"),
        ("sunflower-meal", "sunflower-meal", "Sunflower meal", "oil-cake and other solid residues of sunflower seed oil extraction (HS 230630)"),
    ],
    "rapeseed": [
        ("rapeseed-oil", "rapeseed-oil", "Rapeseed, canola and mustard oil", "rape, colza or mustard oil, crude and other (HS 151410, 151490)"),
        ("rapeseed-meal", "rapeseed-meal", "Rapeseed meal", "oil-cake and other solid residues of rape or colza seed oil extraction (HS 230640)"),
    ],
    # the metal bulks (A-010). Direct-reduced iron is the second group of the pig iron page; coke (HS 270400, customs data) is a group of the
    # metallurgical coal page, beside the EIA tables of metallurgical coke (stem "coke-customs": the keys "coke-exports" and "coke-imports" are EIA's);
    # the ferro-alloys other than ferro-chromium, which opens the page, are the four further pairs of its tables. Ferro-nickel (HS 720260) stays on the
    # nickel page, where its group already is
    "pig-iron": [
        ("dri", "dri", "Direct-reduced iron", "direct-reduced iron and other spongy ferrous products (HS 7203)"),
    ],
    "met-coal": [
        ("coke", "coke-customs", "Coke and semi-coke (customs data)", "coke and semi-coke of coal, lignite or peat (HS 270400)"),
    ],
    "ferro-alloys": [
        ("ferro-manganese", "ferro-manganese", "Ferro-manganese", "ferro-manganese (HS 720211, 720219)"),
        ("silico-manganese", "silico-manganese", "Silico-manganese", "ferro-silico-manganese (HS 720230)"),
        ("ferro-silicon", "ferro-silicon", "Ferro-silicon", "ferro-silicon (HS 720221, 720229)"),
        ("ferro-alloys-other", "ferro-alloys-other", "Other ferro-alloys", "the other ferro-alloys of heading 7202: ferro-silico-chromium, ferro-molybdenum, "
                                                                          "ferro-tungsten and ferro-silico-tungsten, ferro-titanium and ferro-silico-titanium, ferro-vanadium, "
                                                                          "ferro-niobium and the ferro-alloys not elsewhere specified (HS 720250, 720270, 720280, 720291, 720292, 720293, 720299)"),
    ],
}
# USDA PSD production and use of the oil and the meal of a seed page (M-023): page id -> [(PSD commodity, stem of the keys, name in the titles,
# what the table counts)]; keys "<stem>-production" and "<stem>-consumption", the stems of EXTRA_GROUPS. The seed is the page's main PSD table.
PSD_EXTRA = {
    "sunflower": [("Oil, Sunflowerseed", "sunflower-oil", "Sunflower oil", "sunflower oil"),
                  ("Meal, Sunflowerseed", "sunflower-meal", "Sunflower meal", "sunflower meal")],
    "rapeseed": [("Oil, Rapeseed", "rapeseed-oil", "Rapeseed oil", "rapeseed oil"),
                 ("Meal, Rapeseed", "rapeseed-meal", "Rapeseed meal", "rapeseed meal")],
}
# the title of an extra table says what its code holds where the product's name would promise more (review GNC1.4): ammonium nitrate is the
# pure salt and its solutions, the mixtures with limestone are the next table
TITLE_NOTE = {"ammonium-nitrate": " (HS 310230, not mixed with limestone)"}
PSD_WHAT = {
    "wheat": "wheat", "corn": "corn", "soybeans": "soybeans", "soymeal": "soybean meal", "soyoil": "soybean oil",
    "rice": "milled rice", "sugar": "centrifugal sugar (raw value)", "coffee": "green coffee (all forms, green-bean equivalent)",
    "cotton": "cotton", "palm-oil": "palm oil", "rapeseed": "rapeseed", "barley": "barley", "sorghum": "sorghum", "sunflower": "sunflower seed",
}

# What a table measures when its tonnage is not the finished commodity, or when production and trade
# are on different bases: id -> (production basis, trade basis). Printed in the section titles of the
# commodity page and carried onto the country-profile rows by build_profiles.py.
BASIS = {
    "copper": ("contained copper", "ores and concentrates, gross weight"),
    "nickel": ("contained nickel", "ores and concentrates, gross weight"),
    "zinc": ("contained zinc", "ores and concentrates, gross weight"),
    "lead": ("contained lead", "ores and concentrates, gross weight"),
    "bauxite": ("dry tonnes", "bauxite, gross weight"),
    "tin": ("contained tin", "unwrought metal, gross weight"),
    "lithium": ("contained lithium", "carbonate, oxide and hydroxide, gross weight"),
    "gold": ("contained gold", "fine-metal equivalent (Atlas estimate)"),
    "silver": ("contained silver", "fine-metal equivalent (Atlas estimate)"),
    "pgm": ("platinum and palladium content", "fine-metal equivalent at the platinum price (Atlas estimate)"),
    "cobalt": ("contained cobalt", "intermediates and metal, gross weight"),
    "rare-earths": ("REO equivalent", "metals and compounds, gross weight"),
    "manganese": ("manganese content", "ore, gross weight"),
    "uranium": ("contained uranium", "ores and compounds, gross weight"),
    "potash": ("potassium chloride equivalent", "potassium chloride, product weight"),
    "urea": ("ammonia, nitrogen content", "urea, product weight"),
    "phosphate": ("marketable phosphate rock", "phosphate rock, gross weight"),
    "sulphur": ("sulphur content, all forms", "sulphur, gross weight"),
    "npk": (None, "compound fertilisers, product weight"),
    # the metal bulks (A-010): the trade of ores and scrap is gross weight; USGS gives the mine production of chromite in gross weight too
    "ferrous-scrap": (None, "ferrous waste and scrap, gross weight"),
    "pig-iron": ("pig iron, product weight", "pig iron, gross weight"),
    "chromium": ("chromite ore, gross weight", "ore, gross weight"),
    "ferro-alloys": (None, "ferro-alloys, gross weight"),
    "molybdenum": ("contained molybdenum", "ores and concentrates, gross weight"),
    "graphite": ("natural graphite, as USGS states it", "natural graphite, gross weight"),
}
# second trade tables (key prefix -> basis); their titles already name the product
EXTRA_BASIS = {"refined": "gross weight", "int": "gross weight", "alumina": "gross weight", "metal": "gross weight", "ferro": "gross weight"}

# Lithium (audit C-036): the unit-value rule that leaves ore-priced flows out of the chemicals group is rule 9 of clean()
# (pipeline/trade/clean.py, LITHIUM_MIN_UV), read by every builder.
# Lithium carbonate equivalent: tonnes of Li2CO3 per tonne of lithium, from the abridged standard atomic weights of CIAAW
# (pipeline/common/constants.py)
CIAAW_URL = CN.ATOMIC_WEIGHT_PAGE["url"]
_AW = CN.ATOMIC_WEIGHT
LCE_PER_LI = round((2 * _AW["Li"] + _AW["C"] + 3 * _AW["O"]) / (2 * _AW["Li"]), 3)  # as printed: the converted figure reproduces from it
# Uranium oxide equivalent: tonnes of U3O8 per tonne of uranium, from the abridged standard atomic weights of uranium and oxygen (CIAAW),
# and pounds per tonne from the definition of the pound (CN.KG_PER_LB, exact): the unit of the uranium market is the pound of U3O8
U3O8_PER_U = round((3 * _AW["U"] + 8 * _AW["O"]) / (3 * _AW["U"]), 4)
LB_U3O8_PER_TU = round(U3O8_PER_U * 1000 / CN.KG_PER_LB)
ABS_LITHIUM = ("Australian Bureau of Statistics, Insights into Australian Exports of Lithium, 4 August 2022, CC BY 4.0, "
               "https://www.abs.gov.au/articles/insights-australian-exports-lithium")

# USGS: id -> dict(section -> (commodity prefix, detail, unit, factor, label))
USGS = {
    "iron-ore": dict(production=("Iron Ore", "Mine production: Usable ore", "Mt", 1e-3, "iron ore, usable ore (gross weight)"),
                     reserves=("Iron Ore", "Reserves (million metric tons): Crude ore", "Mt", 1.0, "iron ore reserves, crude ore")),
    "steel": dict(production=("Iron And Steel", "Raw steel", "Mt", 1.0, "raw steel production")),
    "copper": dict(production=("Copper", "Mine production", "kt Cu", 1.0, "copper mine production, contained copper"),
                   refinery=("Copper", "Refinery production", "kt Cu", 1.0, "refined copper production (primary and secondary)"),
                   reserves=("Copper", "Reserves", "kt Cu", 1.0, "copper reserves, contained copper")),
    "aluminium": dict(production=("Aluminum", "Smelter production", "kt", 1.0, "primary aluminium smelter production (metal)")),
    "bauxite": dict(production=("Bauxite", "Bauxite, mine production", "Mt", 1e-3, "bauxite mine production, dry tonnes"),
                    refinery=("Alumina", "Alumina, refinery production", "Mt", 1e-3, "alumina refinery production, dry tonnes"),
                    reserves=("Bauxite", "Bauxite reserves", "Mt", 1e-3, "bauxite reserves, dry tonnes")),
    "nickel": dict(production=("Nickel", "Mine production", "kt Ni", 1e-3, "nickel mine production, contained nickel"),
                   reserves=("Nickel", "Reserves", "kt Ni", 1e-3, "nickel reserves, contained nickel")),
    "zinc": dict(production=("Zinc", "Mine production", "kt Zn", 1.0, "zinc mine production, contained zinc"),
                 reserves=("Zinc", "Reserves", "kt Zn", 1.0, "zinc reserves, contained zinc")),
    "lead": dict(production=("Lead", "Mine production", "kt Pb", 1.0, "lead mine production, contained lead"),
                 reserves=("Lead", "Reserves", "kt Pb", 1.0, "lead reserves, contained lead")),
    "tin": dict(production=("Tin", "Mine production", "t Sn", 1.0, "tin mine production, contained tin"),
                reserves=("Tin", "Reserves", "t Sn", 1.0, "tin reserves, contained tin")),
    "lithium": dict(production=("Lithium", "Mine production", "t Li", 1.0, "lithium mine production, contained lithium"),
                    reserves=("Lithium", "Reserves", "t Li", 1.0, "lithium reserves, contained lithium")),
    "cobalt": dict(production=("Cobalt", "Mine production", "t Co", 1.0, "cobalt mine production, contained cobalt"),
                   reserves=("Cobalt", "Reserves", "t Co", 1.0, "cobalt reserves, contained cobalt")),
    "rare-earths": dict(production=("Rare Earths", "Mine production", "t REO", 1.0, "rare-earth mine production, REO equivalent"),
                        reserves=("Rare Earths", "Reserves", "t REO", 1.0, "rare-earth reserves, REO equivalent")),
    "manganese": dict(production=("Manganese", "Mine production", "kt Mn", 1.0,
                                  "manganese mine production, section titled 'manganese content' (chapter header says gross weight; unit as USGS table)"),
                      reserves=("Manganese", "Reserves", "kt Mn", 1.0, "manganese reserves, section titled 'manganese content'")),
    "gold": dict(production=("Gold", "Mine production", "t Au", 1.0, "gold mine production, contained gold"),
                 reserves=("Gold", "Reserves", "t Au", 1.0, "gold reserves, contained gold")),
    "silver": dict(production=("Silver", "Mine production", "t Ag", 1.0, "silver mine production, contained silver"),
                   reserves=("Silver", "Reserves", "t Ag", 1.0, "silver reserves, contained silver")),
    "potash": dict(production=("Potash", "Mine production", "Mt K2O", 1e-3, "potash mine production, K2O equivalent"),
                   reserves=("Potash", "Reserves: K2O equivalent", "Mt K2O", 1e-3, "potash reserves, K2O equivalent")),
    "phosphate": dict(production=("Phosphate Rock", "Mine production", "Mt", 1e-3, "phosphate rock mine production, marketable product"),
                      reserves=("Phosphate Rock", "Reserves", "Mt", 1e-3, "phosphate rock reserves")),
    "urea": dict(production=("Nitrogen", "Plant production", "Mt N", 1e-3, "ammonia plant production, nitrogen content (urea feedstock; not urea output)")),
    "sulphur": dict(production=("Sulfur", "Production, all forms", "Mt S", 1e-3, "sulphur production, all forms, in sulphur content")),
    # the metal bulks (A-010). Chromium: the file's world table gives mine production in gross weight (thousand metric tons) and reserves twice: in
    # ore (for 2024, an older year than the rest of the table) and in Cr2O3 content (2025); the reserves shown are the Cr2O3 content, the year of the
    # production. Pig iron: the world table of "Iron And Steel" (million metric tons, by country). Molybdenum and graphite: mine production and reserves
    "chromium": dict(production=("Chromium", "Mine production", "Mt", 1e-3, "chromite mine production, gross weight"),
                     reserves=("Chromium", "Reserves: Cr2O3 content", "Mt Cr2O3", 1e-3, "chromium reserves, Cr2O3 content")),
    "pig-iron": dict(production=("Iron And Steel", "Pig iron", "Mt", 1.0, "pig iron production")),
    "molybdenum": dict(production=("Molybdenum", "Mine production", "kt Mo", 1e-3, "molybdenum mine production, contained molybdenum"),
                       reserves=("Molybdenum", "Reserves (thousand metric tons)", "kt Mo", 1.0, "molybdenum reserves, contained molybdenum")),
    "graphite": dict(production=("Graphite (Natural)", "Mine production", "kt", 1e-3, "natural graphite mine production"),
                     reserves=("Graphite (Natural)", "Reserves", "kt", 1e-3, "natural graphite reserves")),
}


# USGS tables listed in full, with the line "Other countries" as the last row: (commodity id, section)
# The groups that a page shows as a table through its own code instead of TRADE and EXTRA_GROUPS (the "second trade tables" of main(), built with
# baci.ranked): the completeness note of _gap_note is written for these too (FNCF, review GV6B.2). test_fncf.py reads the source for every
# group that main() ranks and finds it in TRADE, EXTRA_GROUPS or here.
HAND_GROUPS = {
    "copper": [("copper-refined", "refined and blister copper (HS 7402, 7403)")],
    "nickel": [("nickel-int", "nickel mattes, intermediates and unwrought nickel (HS 7501, 7502)"), ("nickel-fe", "ferro-nickel (HS 720260)")],
    "bauxite": [("alumina", "alumina (HS 281820)")],
    "zinc": [("zinc-metal", "unwrought zinc (HS 7901)")],
}
# the stem of the keys of the extra tables of a hand group ("refined-exports"): the key of an EXTRA_GROUPS entry is its own second element
HAND_STEMS = {"copper-refined": "refined", "nickel-int": "int", "nickel-fe": "ferro", "alumina": "alumina", "zinc-metal": "metal"}
FULL_TABLE = {("steel", "production"), ("gold", "production"), ("bauxite", "refinery"), ("pig-iron", "production")}

# Headline figures of publishers whose tables are not free to copy: one world total each, cited with publisher, year and link
# (publisher, publication, figure, unit, year, page read, id in data/sources.json)
WORLDSTEEL = ("World Steel Association", "World Steel in Figures 2026, data finalised 8 June 2026", 1848.9, "Mt", 2025,
              "https://worldsteel.org/data/world-steel-in-figures/world-steel-in-figures-2026/", "worldsteel")
WGC_MINE = ("World Gold Council", "Gold Demand Trends, full year 2025 (supply)", 3671.6, "t", 2025,
            "https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-full-year-2025/supply", "wgc")
# Official or press figures read on a page, quoted in a discrepancy note: Guinea's exports
GUINEA_EXPORTS = ("official data seen by Reuters, in Hellenic Shipping News, January 2026", 182.8, 2025,
                  "https://www.hellenicshippingnews.com/guineas-bauxite-exports-jump-25-to-183-million-tons-in-2025-on-chinese-demand/")
# Pages read for the exporters whose HS 253090 rows are read as spodumene concentrate shipped to China (GW3.11): exporter -> (what
# the page says, publisher and date, link). The ABS page is ABS_LITHIUM.
SPODUMENE_PAGES = {
    "ZWE": ("\"Most of the concentrate is exported to China for further processing\"", "Reuters, 3 February 2026, republished by Kitco",
            "https://www.kitco.com/news/off-the-wire/2026-02-03/zimbabwe-spodumene-exports-11-2025-revenue-flat-soft-prices"),
    "BRA": ("Sigma Lithium's lithium concentrate shipped to the port of Vitoria, Espirito Santo, bound for China (the page calls it green lithium concentrate) "
            "and a cargo of lithium concentrate scheduled for Zhangjiagang, China", "Diario do Comercio, 6 February 2024, and SMM (Shanghai Metals Market), 18 July 2024",
            "https://diariodocomercio.com.br/economia/sigma-exporta-maior-carregamento-litio-minas/ and https://news.metal.com/en/newscontent/102856969"),
}
BENCHMARK_COBALT = "https://source.benchmarkminerals.com/article/drc-to-lift-cobalt-export-ban-and-impose-quotas-through-2027"

_HS4 = {}


# ---------------------------------------------------------------------- the European Union's member states (audit M-024, C-104)
# USDA PSD counts the EU as one entity (trade between members left out), so a member state has no row of its own in the crop
# tables. The member lines come from two other sources, each labelled with its own year: FAOSTAT crop production (pipeline/cache/
# faostat_eu_crops.csv, fetch_external.py) and the customs frame (CEPII BACI), with the split between trade inside the EU and outside it.
EU_MEMBERS = ["AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU", "LUX",
              "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE"]
# commodity page -> (FAOSTAT item code, what the item is, what a table of it measures when it is not the commodity's own unit)
FAO_EU_ITEMS = {"wheat": ("15", "wheat", None), "corn": ("56", "maize (corn)", None), "rice": ("27", "rice (paddy)", "paddy rice, not milled"),
                "soybeans": ("236", "soya beans", None), "rapeseed": ("270", "rape or colza seed", None),
                "sugar": ("157", "sugar beet", "sugar beet, crop weight, not sugar")}
EU_SCOPE_NOTE = ("the shares are of the total of the 27 member states, not of the world")


def faostat_eu_production(cid):
    """Production of the 27 member states, FAOSTAT crop production (item of FAO_EU_ITEMS), latest year with a world total, in Mt.
    scope 'EU': the shares are of the EU total; worldAll is the FAOSTAT world total, the base of the map colours. None for a crop
    FAOSTAT table is not used for."""
    if cid not in FAO_EU_ITEMS:
        return None
    item, what, basis = FAO_EU_ITEMS[cid]
    by = defaultdict(dict)  # year -> area -> (tonnes, flag)
    with open(os.path.join(CACHE, "faostat_eu_crops.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["item"] == item and r["value_t"].strip():
                by[int(r["year"])][r["area"]] = (float(r["value_t"]), r["flag"], r["m49"])
    year = max(y for y, a in by.items() if "World" in a and "European Union (27)" in a)
    rows, notes = [], []
    world = by[year]["World"][0] / 1e6
    for area, (v, fl, m49) in by[year].items():
        if area in ("World", "European Union (27)"):
            continue
        iso = fao_iso(m49, area)
        if not iso or iso not in EU_MEMBERS:
            continue
        note = f"{_pct1(v / 1e6 / world)} of the FAOSTAT world total ({_nf(world)} Mt)"
        if fl in ("E", "X", "I"):
            note += f"; FAO flag: {fl}"
        rows.append((iso, v / 1e6, note))
    total = sum(r[1] for r in rows)
    agg = by[year]["European Union (27)"][0] / 1e6
    if abs(total / agg - 1) > 0.005:
        warn(f"FAOSTAT {what} {year}: the 27 member states add up to {total:.3f} Mt, the FAOSTAT aggregate gives {agg:.3f} Mt")
    n = (f"FAOSTAT crop production (QCL), {what}, calendar year {year}, the 27 member states, tonnes converted to Mt; {EU_SCOPE_NOTE}: {_nf(total)} Mt "
         f"(the world total of FAOSTAT is {_nf(world)} Mt). The USDA row 'European Union' in the production table above is another source and another year "
         "(a marketing year, with USDA's own definition of the crop): the two are not added up and need not agree. ")
    if basis:  # another basis than the USDA table: its shares would not be comparable with the colours of the other countries
        n += f"This table is {basis}, not the basis of the USDA table: on the map the member states carry the USDA value for the European Union"
    else:
        n += "On the map each member state is coloured with its own figure from this table, as its share of the FAOSTAT world total"
    t = ranked(rows, year, "faostat", "Mt", world=total, n=n)
    t["scope"] = "EU"
    t["scopeLabel"] = "EU member states"
    t["norank"] = True  # the order is a ranking among the member states, not a world ranking
    t["worldAll"] = rnd(world)
    if basis:
        t["noMap"] = True
    return set_basis(t, basis)


def eu_trade(baci, g, div):
    """Customs trade of the 27 member states in the latest year of the cleaned frame, split into trade between members (`intra`, counted
    once) and with the rest of the world: {"exports": {iso: (total, intra)}, "imports": {iso: (total, intra)}, "world": {side: tonnes}, and the
    sums "ex" / "im": (total, intra, extra)}, all in the table's unit. intra + extra = total by construction."""
    d = baci.group(g)
    eu = set(EU_MEMBERS)
    out = {"exports": {}, "imports": {}}
    for side, col, other in (("exports", "o", "d"), ("imports", "d", "o")):
        x = d[d[col].isin(eu)]
        for iso, part in x.groupby(col):
            out[side][iso] = (float(part["t"].sum()) / div, float(part[part[other].isin(eu)]["t"].sum()) / div)
    out["world"] = {"exports": float(d["t"].sum()) / div, "imports": float(d["t"].sum()) / div}
    for k, side in (("ex", "exports"), ("im", "imports")):
        tot = sum(v[0] for v in out[side].values())
        intra = sum(v[1] for v in out[side].values())
        out[k] = (tot, intra, tot - intra)
    return out


def eu_trade_table(side, tr, what, u):
    """The ranked table of the member states' exports or imports (customs, trade between members included), scope 'EU'."""
    rows = []
    for iso, (tot, intra) in tr[side].items():
        if tot <= 0:
            continue
        way = "to" if side == "exports" else "from"
        rows.append((iso, tot, f"of which {_nfu(intra, u)} {way} other member states and {_nfu(tot - intra, u)} {way} countries outside the EU"))
    tot, intra, extra = tr["ex" if side == "exports" else "im"]
    word = "exports" if side == "exports" else "imports"
    n = (f"CEPII BACI {BACI_YEAR}, {what}: customs {word} of the 27 member states, all destinations, trade between members included; {EU_SCOPE_NOTE}: "
         f"{_nfu(tot, u)}, of which {_nfu(intra, u)} {'to' if side == 'exports' else 'from'} other member states and {_nfu(extra, u)} "
         f"{'to' if side == 'exports' else 'from'} countries outside the EU. USDA's 'European Union' row of the table above counts trade outside the EU only "
         "(and is a marketing year of its own). On the map each member state carries the USDA value for the European Union, not a figure of this table: "
         f"customs figures that include trade between members would stand beside USDA's, on one scale, as if they measured the same thing (the customs world total is {_nfu(tr['world'][side], u)})")
    t = ranked(rows, BACI_YEAR, "baci", u, world=sum(r[1] for r in rows), n=n)
    t["scope"] = "EU"
    t["scopeLabel"] = "EU member states"
    t["norank"] = True
    t["noMap"] = True  # the map keeps USDA's row for the European Union on every member (one source, one year, one definition of trade)
    t["worldAll"] = rnd(tr["world"][side])
    t["split"] = {"total": rnd(tot), "intra": rnd(intra), "extra": rnd(extra)}
    return t


def eu_split_note(tr, side, u):
    """The sentence on the EU27 line of a USDA trade table: what the customs data say of the 27 members, inside and outside the EU."""
    tot, intra, extra = tr["ex" if side == "exports" else "im"]
    return (f"Customs data (CEPII BACI {BACI_YEAR}), the 27 member states together: {_nfu(tot, u)} of {side}, of which {_nfu(intra, u)} "
            f"{'to' if side == 'exports' else 'from'} other member states and {_nfu(extra, u)} {'to' if side == 'exports' else 'from'} countries outside the EU; "
            "the USDA row counts trade outside the EU only")


def hs4_exports(prefixes, year=BACI_YEAR):
    """Exports in tonnes by exporter of the HS4 headings starting with `prefixes`, from the extract
    pipeline/cache/hs4_exports.csv.gz (CEPII BACI as downloaded: none of the cleaning rules is applied).
    {} if the extract is not of `year`."""
    if "df" not in _HS4:
        _HS4["df"] = pd.read_csv(os.path.join(CACHE, "hs4_exports.csv.gz"), dtype={"hs4": str})
    h = _HS4["df"]
    h = h[(h["t"] == year) & h["hs4"].str.startswith(tuple(prefixes)) & h["o"].notna()]
    out = defaultdict(float)
    for o, t in zip(h["o"], h["tonnes"]):
        if t == t:  # a row without a quantity (NaN) adds nothing: BACI leaves the quantity out for some small flows
            out[BACI_OVERRIDE.get(o, o)] += float(t)
    return dict(out)


def main():
    out_dir = OUT
    os.makedirs(out_dir, exist_ok=True)
    index = json.load(open(os.path.join(OUT, "index.json"), encoding="utf-8"))
    ids = [e["id"] for e in index]
    print("commodities:", len(ids))

    us, eia, psd, baci = Usgs(), Eia(), Psd(), Baci()
    print("loaded: usgs, eia, psd, baci; PSD release", psd.release)

    docs = {}
    qa = {}

    def start(cid):
        d = {"id": cid, "summary": {}}
        notes, disc = [], []
        return d, notes, disc

    def add_baci_trade(d, cid, notes, disc, group=None, flows=True, exports=True, imports=True, extra=None):
        g, (u, div), what = TRADE[cid]
        if group:
            g = group
        ex = im = None
        if exports:
            d["exports"], est = baci.ranked(g, "exports", u, div, what, extra)
        if imports:
            d["imports"], _ = baci.ranked(g, "imports", u, div, what, extra)
        if flows:
            d["flows"] = baci.flows(g, u, div)
            disc.extend(baci.last_susp)
        return g

    def summ(d, key, r, label=None):
        """Fig from the world total of a Ranked: the published one when the shares of the table rest on the sum of its lines."""
        if r is None or r.get("world") is None:
            return
        d["summary"][key] = fig(r.get("worldPublished", r["world"]), r["u"], f"{r['y']} {r['yk']}" if r.get("yk") else r["y"], r["s"], (label or r.get("n")))

    def seaborne(d, g, label=None):
        f = baci.seaborne(g, label)
        if f:
            d["summary"]["seaborne"] = f

    def name_it(d, key, title=None, kpi=None):
        """Section title / KPI label of the commodity page where the default wording would mislead."""
        if title:
            d.setdefault("labels", {})[key] = title
        if kpi:
            d.setdefault("kpis", {})[key] = kpi

    def oil_demand(d):
        t = eia.ranked(("5-2", "TBPD"), "kb/d", 1.0, "petroleum and other liquids consumption: total oil demand, all liquids "
                       "(the EIA series 'refined petroleum products consumption' carries the same values)")
        d["consumption"] = set_basis(t, "oil demand, all liquids")
        summ(d, "consumption", t, "Total oil demand (EIA petroleum and other liquids consumption): all liquids, not crude or refined products alone.")
        name_it(d, "consumption", "Top consumers — oil demand, all liquids", "Oil demand (all liquids)")

    for cid in ids:
        d, notes, disc = start(cid)
        extra_first = []  # extra tables decided inside the recipe (shown before the generic ones)
        see = []  # one line per product that is on another page: {k: that page, text}, drawn with a link (CommodityView.tsx)

        # ------------------------------------------------------------ energy
        if cid == "crude-oil":
            d["production"] = eia.ranked(("57-1", "TBPD"), "kb/d", 1.0, "crude oil including lease condensate production")
            g = add_baci_trade(d, cid, notes, disc)
            summ(d, "production", d["production"], "EIA crude oil including lease condensate, world")
            summ(d, "exports", d["exports"], "sum of all BACI crude oil flows, tonnes (all modes)")
            oil_demand(d)
            seaborne(d, g)
            bpt = round(K.barrels_per_tonne(eia.s), 2)  # the factor as printed: every converted figure reproduces from it
            conv = (f"{bpt:.2f} barrels per tonne, the ratio of EIA's series for United States crude oil production in thousand "
                    "barrels per day and in thousand metric tons (1980 to 1999); other grades and other countries differ")
            p, x = d["summary"]["production"], d["summary"]["exports"]
            alt_fig(p, p["v"] * 1e3 * (366 if _isleap(p["y"]) else 365) / bpt / 1e6, "Mt/yr", conv)
            alt_fig(x, x["v"] * 1e6 * bpt / (366 if _isleap(x["y"]) else 365) / 1e3, "kb/d", conv)
            notes += [
                f"Production is in kb/d (EIA) and trade in Mt per year (BACI tonnage); the figures above carry the other unit in brackets. Atlas conversion: {conv}.",
                "Oil demand is EIA petroleum and other liquids consumption: all liquids, not crude alone. The same table is shown under refined products.",
                "The EIA international data the atlas uses have no proved-reserves series.",
            ]
        elif cid == "refined-products":
            oil_demand(d)
            g = add_baci_trade(d, cid, notes, disc)
            summ(d, "exports", d["exports"], "sum of all BACI refined-product flows (HS 2710), tonnes, all modes")
            seaborne(d, g)
            y = d["consumption"]["y"]
            parts = []
            for key, nm in [(("65-2", "TBPD"), "distillate fuel oil"), (("62-2", "TBPD"), "motor gasoline"),
                            (("63-2", "TBPD"), "jet fuel"), (("66-2", "TBPD"), "residual fuel oil")]:
                parts.append(f"{nm} {eia.s[key]['WORL'][y] / 1000:.1f} mb/d")
            notes.append(f"World consumption by product, {y} (EIA, eia-intl): " + ", ".join(parts) + ". The four products do not add up to total oil demand: the other liquids are not listed.")
            # production by country: EIA's series end in 2014, so the table is that year's and says so; consumption by product, every country
            pt = eia.ranked(("54-1", "TBPD"), "kb/d", 1.0, "refined petroleum products production",
                            n_extra=f"EIA's refined-product production series end in {eia.latest_year(('54-1', 'TBPD'))}")
            # an extra table, not `production`: the map would colour countries by a 2014 figure as soon as the commodity is chosen
            extra_first.append({"key": "refined-products-production", "title": f"Top producers — refined petroleum products, EIA {pt['y']}", "table": pt})
            for key, nm in [(("62-2", "TBPD"), "motor gasoline"), (("65-2", "TBPD"), "distillate fuel oil"),
                            (("63-2", "TBPD"), "jet fuel"), (("66-2", "TBPD"), "residual fuel oil")]:
                t = eia.ranked(key, "kb/d", 1.0, f"{nm} consumption")
                extra_first.append({"key": nm.replace(" ", "-") + "-consumption", "title": f"Top consumers — {nm}, EIA {t['y']}", "table": t})
            notes.append(f"Production by country is EIA's refined petroleum products production for {pt['y']}, the last year of its series; consumption by product is shown "
                         "for gasoline, distillates, jet fuel and residual fuel oil (the other products are in total oil demand only).")
            # Russia's exports as customs data show them, beside what the EIA says (its own unit and year: no conversion)
            ru = baci.df[(baci.df["group"] == g) & (baci.df["o"] == "RUS") & (baci.df["d"] == "ARE")].groupby("year")["t"].sum() / 1e6
            gone = [(yr, v) for yr, v in ru.items() if yr < BACI_YEAR and v > 0.05] if ru.get(BACI_YEAR, 0) == 0 else []
            sh = EIA_RUSSIA["shares"]
            notes.append(
                f"Russia: the exports above rest on what importers declare (see the note on Russia). The U.S. Energy Information Administration "
                f"(Country Analysis Brief: Russia, last updated 24 July 2025, public domain, {EIA_RUSSIA_URL}) puts Russia as the world's {EIA_RUSSIA['rank']} petroleum "
                f"product exporter in {EIA_RUSSIA['total_year']}, with {EIA_RUSSIA['total_mbd']} million b/d, and says that in {EIA_RUSSIA['share_year']} "
                f"{sh[0][0]} received {sh[0][1]}% of Russia's product exports, {sh[1][0]} {sh[1][1]}%, and "
                + ", ".join(n for n, _ in sh[2:-1]) + f" and {sh[-1][0]} {sh[-1][1]}% each. The units differ, so no ratio is computed."
                + (f" The Atlas customs extract holds no flow of 1,000 t or more (and 1 million USD or more) from Russia to the United Arab Emirates in {BACI_YEAR}"
                   f" ({_fmt(gone[-1][1])} Mt in {gone[-1][0]}); smaller flows are not in the extract." if gone else ""))
        elif cid == "lng":
            g = add_baci_trade(d, cid, notes, disc)
            for sec in ("exports", "imports"):
                d[sec]["norank"] = True  # customs tonnage misses cargoes of some countries: an order, not a ranking
            # the headline world total is the industry's (publisher and year beside it); the customs total is in the caveat
            gw = max((r for r in LNG_REFERENCE if r[0] == "GIIGNL" and r[5] == "world LNG trade"), key=lambda r: r[4])
            d["summary"]["exports"] = fig(gw[2], gw[3], gw[4], "giignl-2026", f"{gw[0]} {gw[1]}: world LNG trade")
            name_it(d, "exports", kpi=f"World LNG trade ({gw[0]})")
            seaborne(d, g)
            alt_fig(d["summary"]["exports"], gw[2] * BCM_PER_MT_LNG, "bcm", GAS_FACTOR)
            if "seaborne" in d["summary"]:
                alt_fig(d["summary"]["seaborne"], d["summary"]["seaborne"]["v"] * BCM_PER_MT_LNG, "bcm", GAS_FACTOR)
            chk = lng_importer_check(baci, eia, BACI_YEAR)
            low = [r for r in chk if r[3] < 0.5]
            same = [r for r in chk if 0.9 <= r[3] <= 1.1]
            if low and same:
                add_caveat(d["imports"], (
                    "Customs data can miss LNG that an importer receives. Where no pipeline gas is involved (no gas pipeline of the atlas layer ends "
                    "in the country, pipeline gas is under 1% of the customs LNG, no neighbour exports gas in EIA), customs LNG converted to bcm agrees with EIA's total "
                    f"gas imports for {_and([cname(r[0]) for r in same])} (within 10%), but not for "
                    + "; ".join(f"{cname(r[0])}: {_fmt(r[1])} Mt ({_fmt(r[1] * BCM_PER_MT_LNG)} bcm) in customs data against {_fmt(r[2])} bcm in EIA" for r in low)
                    + f" ({BACI_YEAR}). Incomplete declarations by importers are a plausible cause; it is not established here. Atlas conversion: {GAS_FACTOR}."))
            notes += [f"LNG volumes are in Mt, with bcm in brackets on the headline figures. Atlas conversion: {GAS_FACTOR}. "
                      "No production table: liquefaction output is not in the loaded sources."]
            own_tables, own_notes = lng_own_statistics(baci)
            d["extra"] = d.get("extra", []) + own_tables
            notes += own_notes
        elif cid == "natural-gas":
            d["production"] = eia.ranked(("26-1", "BCM"), "bcm", 1.0, "dry natural gas production")
            d["consumption"] = eia.ranked(("26-2", "BCM"), "bcm", 1.0, "dry natural gas consumption")
            # countries are ranked on EIA volumes: customs tonnage of pipeline gas does not reconcile with them (see the notes)
            via = "re-exports included; EIA gives no LNG split by country, so none is subtracted"
            d["exports"] = eia.ranked(("26-4", "BCM"), "bcm", 1.0, "dry natural gas exports", n_extra=via)
            d["imports"] = eia.ranked(("26-3", "BCM"), "bcm", 1.0, "dry natural gas imports", n_extra=via)
            for sec in ("exports", "imports"):
                add_caveat(d[sec], "Pipeline gas and LNG together: LNG is also listed on the LNG page.")
            g, (u, div), _ = TRADE[cid]
            pairs, npipes = gas_pipeline_pairs()
            d["flows"] = baci.flows(g, u, div, only_pairs=set(pairs))
            disc.extend(baci.last_susp)
            for f in d["flows"]:
                f["mode"] = "pipeline"
                f["n"] = (f["n"] + "; " if f.get("n") else "") + "customs tonnage of gas in gaseous state; pipeline of the atlas layer: " + ", ".join(pairs[(f["o"], f["d"])])
            name_it(d, "flows", f"Pipeline pairs — customs tonnes, {BACI_YEAR}")
            for key in ("production", "consumption", "exports"):
                summ(d, key, d[key], "EIA dry natural gas exports, world total: pipeline and LNG together" if key == "exports" else None)
            # only the trade figure carries a second unit: a producer's gas expressed in LNG tonnes would read as LNG output
            alt_fig(d["summary"]["exports"], d["summary"]["exports"]["v"] / BCM_PER_MT_LNG, "Mt LNG equivalent",
                    GAS_FACTOR + "; gas volume expressed in tonnes of LNG, pipeline gas included, not LNG trade")
            ce, ci = baci.totals(g, "exports"), baci.totals(g, "imports")
            ee, ei = dict(eia.country_values(("26-4", "BCM"), BACI_YEAR)), dict(eia.country_values(("26-3", "BCM"), BACI_YEAR))
            notes += [
                f"Top exporters and importers rank EIA dry natural gas trade in bcm ({d['exports']['y']}): pipeline and LNG together, re-exports included. "
                "EIA gives no LNG split by country, so LNG is not subtracted; LNG by pair is on the LNG page.",
                f"Customs tonnage of gas in gaseous state (BACI HS 271121, Mt) does not reconcile with EIA volumes and is not used to rank countries. In {BACI_YEAR} "
                f"customs data show {_fmt(ce['CAN'])} Mt of exports from Canada against {_fmt(ee['CAN'])} bcm in EIA, {_fmt(ce['BEL'])} Mt from Belgium against "
                f"{_fmt(ee['BEL'])} bcm (counting gas in transit twice, or tonnage estimated from value, are plausible causes; not established here), and "
                f"{_fmt(ci['MAR'])} Mt of imports by Morocco against {_fmt(ei['MAR'])} bcm.",
                f"The flow list keeps only the country pairs joined by a gas pipeline of the atlas's own layer ({npipes} pipelines, a selection of major ones, not a "
                "complete register): a pair appears only if the layer has a pipeline between its countries. Figures are customs tonnes (Mt), not bcm.",
                "The EIA international data the atlas uses have no proved-reserves series."]
        elif cid == "lpg":
            d["consumption"] = eia.ranked(("67-2", "MT"), "Mt", 1e-3, "liquefied petroleum gases consumption (1000 metric tons converted to Mt)")
            g = add_baci_trade(d, cid, notes, disc)
            summ(d, "consumption", d["consumption"])
            if d["consumption"].get("conv") and eia.lpg_us:
                # the world total holds the converted United States (or is EIA's own series in barrels per day converted): the figure is the atlas's
                # conversion of an EIA figure, and says so where it is printed
                cs = d["summary"]["consumption"]
                cs["s"] = "atlas"
                cs["n"] = ("Atlas conversion of EIA International Energy Data, liquefied petroleum gases consumption (1000 metric tons converted to Mt). "
                           f"EIA's own world total in tonnes is {eia.lpg_us['world'][int(cs['y'])]['eia']:,.2f} Mt.")
            summ(d, "exports", d["exports"])
            seaborne(d, g)
            notes += lpg_us_notes(baci)
            # production: EIA's LPG series end in 2014, so that table is dated; natural gas plant liquids (ethane, propane, butanes and heavier
            # liquids recovered from gas) run to the latest year and are LPG's main supply, but are not LPG alone
            lt = eia.ranked(("67-1", "TBPD"), "kb/d", 1.0, "liquefied petroleum gases production",
                            n_extra=f"EIA's LPG production series end in {eia.latest_year(('67-1', 'TBPD'))}")
            extra_first.append({"key": "lpg-production", "title": f"Top producers — LPG, EIA {lt['y']}", "table": lt})  # an extra table: see refined products
            nt = eia.ranked(("58-1", "TBPD"), "kb/d", 1.0, "natural gas plant liquids production",
                            n_extra="ethane, propane, butanes and heavier liquids recovered from natural gas: LPG's supply, not LPG alone")
            extra_first.append({"key": "ngl-production", "title": f"Natural gas plant liquids producers, EIA {nt['y']} (not LPG alone)", "table": nt})
            if eia.lpg_us:
                # a second unit for the headline: the barrels-per-tonne ratio is EIA's own, read from its United States series in both units
                bpt, cs = eia.lpg_us["ratio"], d["summary"]["consumption"]
                conv = (f"{bpt:.2f} barrels per tonne, the ratio of EIA's series for United States LPG consumption in thousand barrels per day and in "
                        f"thousand metric tons (the same in every year from {eia.lpg_us['from']} to {eia.lpg_us['to']}); other countries differ slightly")
                alt_fig(cs, cs["v"] * 1e6 * bpt / (366 if _isleap(cs["y"]) else 365) / 1e3, "kb/d", conv)
                notes.append(f"LPG production is in kb/d (EIA; {lt['y']} is the last year of its series) and consumption and trade in Mt; the headline consumption carries kb/d in brackets (Atlas conversion: {conv}). "
                             f"Prices on the atlas are in USD per US gallon: at that ratio and {CN.US_GALLONS_PER_BARREL} US gallons per barrel (EIA, units and calculators) one tonne of LPG is "
                             f"{bpt * CN.US_GALLONS_PER_BARREL:,.0f} US gallons, so a price per gallon times {bpt * CN.US_GALLONS_PER_BARREL:,.0f} is a price per tonne (Atlas conversion).")
        elif cid == "thermal-coal":
            d["production"] = eia.minus(("7-1", "MT"), ("130-1", "MT"), "Mt", 1e-3, "coal production",
                                        "all coal minus metallurgical coal (EIA), per country; 1000 metric tons converted to Mt")
            d["consumption"] = eia.minus(("7-2", "MT"), ("130-2", "MT"), "Mt", 1e-3, "coal consumption",
                                         "all coal minus metallurgical coal (EIA), per country; 1000 metric tons converted to Mt")
            # Lignite is a rank of non-metallurgical coal in the EIA series, so it sits inside these two tables
            # (Germany's and most of Turkey's output). It is shown apart: per row, and as its own table.
            for sec, key, word in (("production", ("14-1", "MT"), "production"), ("consumption", ("14-2", "MT"), "consumption")):
                t = d[sec]
                ly = t["y"]
                lw = eia.s[key]["WORL"].get(ly)
                for r in t["rows"]:
                    lv = eia.s[key].get(_iso_to_eia(r["c"]), {}).get(ly, 0.0) * 1e-3
                    if lv >= 0.01 * r["v"]:
                        r["n"] = f"of which lignite {_fmts(lv, 'Mt')} ({min(lv / r['v'], 1):.0%})"
                if lw:
                    t["n"] += f"; includes lignite: {_fmt(lw * 1e-3)} Mt of the world total ({lw * 1e-3 / t['world']:.0%}, EIA lignite {word})"
                set_basis(t, "incl. lignite")
            py = d["production"]["y"]
            lig = eia.ranked(("14-1", "MT"), "Mt", 1e-3, "lignite production; 1000 metric tons converted to Mt", year=py,
                             n_extra="these tonnages are included in the thermal coal production table")
            extra_first.append({"key": "lignite-production", "title": f"Lignite producers, EIA {py} (included above)", "table": lig})
            tr = eia.ranked(("7-6", "MST"), "Mt", CN.TONNES_PER_SHORT_TON, "coal reserves (all ranks, not split thermal/metallurgical); million short tons converted to Mt")
            # EIA repeats a reserve estimate every year until it is revised: date the table by its last revision
            # (the year since which the world total is unchanged) and say so for rows that are older still.
            ser, y = eia.s[("7-6", "MST")], tr["y"]

            def since(code):
                v, s0 = ser[code], y
                while (s0 - 1) in v and abs(v[s0 - 1] - v[y]) < 1e-6:
                    s0 -= 1
                return s0

            rev = since("WORL")
            flags = []
            for i, r in enumerate(tr["rows"]):
                code = _iso_to_eia(r["c"])
                s0 = since(code)
                if s0 < rev:
                    r["n"] = f"EIA value unchanged since {s0}"
                prev = ser[code].get(s0 - 1)
                if prev and ser[code][s0] / prev >= 10:  # one revision multiplied the estimate tenfold or more
                    flag = (f"{cname(r['c'])}: EIA raised its estimate from {_fmt(prev * CN.TONNES_PER_SHORT_TON)} Mt to {_fmt(ser[code][s0] * CN.TONNES_PER_SHORT_TON)} Mt in {s0}, "
                            f"a {ser[code][s0] / prev:.0f}-fold step, and has not changed it since; treat this rank with caution")
                    r["n"] = flag.split(": ", 1)[1]
                    if i < SHOWN_ROWS:  # the table's warning names the ranks drawn first; every flagged row keeps its own note
                        flags.append(flag)
            tr["y"] = rev
            tr["n"] += f"; last revised by EIA in {rev} and repeated unchanged to {y} (reserve estimates are not revised every year)"
            for flag in flags:
                add_caveat(tr, flag + ".")
            if flags:  # the warning is about the years since the revision it names
                tr["caveatYears"] = list(range(min(since(_iso_to_eia(r["c"])) for r in tr["rows"][:SHOWN_ROWS] if r.get("n", "").startswith("EIA raised")), y + 1))
            d["reserves"] = tr
            g = add_baci_trade(d, cid, notes, disc, extra="HS 2701 and 2702 do not separate thermal from metallurgical coal: figures cover all coal")
            allcoal = {"exports": d["exports"], "imports": d["imports"]}  # customs tables, all coal: same basis as flows and lanes
            for f in d["flows"]:
                f["n"] = joinn(f.get("n"), "all coal (HS 2701, 2702): thermal and metallurgical not separated")
            for sec, key in (("production", ("14-1", "MT")), ("consumption", ("14-2", "MT"))):
                t = d[sec]
                lw = eia.s[key]["WORL"].get(t["y"])
                summ(d, sec, t, "All coal minus metallurgical coal (EIA)" + (f", so lignite is included: {_fmt(lw * 1e-3)} Mt, {lw * 1e-3 / t['world']:.0%} of the total." if lw else "."))
            summ(d, "reserves", d["reserves"], f"All coal, not split thermal/metallurgical. EIA estimates last revised in {rev}.")
            # Thermal-only trade tables from EIA (all coal minus metallurgical coal, per country); BACI
            # customs data cannot split them, so BACI is kept for the bilateral flows only.
            d["exports"] = eia.minus(("7-4", "MT"), ("130-4", "MT"), "Mt", 1e-3, "coal exports",
                                     "all coal exports minus metallurgical coal exports (EIA), per country; 1000 metric tons converted to Mt")
            d["imports"] = eia.minus(("7-3", "MT"), ("130-3", "MT"), "Mt", 1e-3, "coal imports",
                                     "all coal imports minus metallurgical coal imports (EIA), per country; 1000 metric tons converted to Mt")
            summ(d, "exports", d["exports"], "Thermal coal only (EIA: all coal minus metallurgical coal). Not the basis of the seaborne figure, which is all coal.")
            seaborne(d, g, "all coal (thermal and metallurgical)")
            sb = d["summary"]["seaborne"]
            cmp_ = f"Customs data give {math.floor(allcoal['exports']['world'] + 0.5):,} Mt of all-coal trade by all modes in {allcoal['exports']['y']}"
            ew = eia.s[("7-4", "MT")]["WORL"].get(sb["y"]) if isinstance(sb["y"], int) else None
            if ew:
                cmp_ += f"; EIA puts world exports of all coal at {_fmt(ew * 1e-3)} Mt in {sb['y']}"
            sb["n"] = ("All coal, thermal and metallurgical: customs codes do not separate them, so this is not comparable with the thermal-only exports figure. "
                       + cmp_ + ". " + sb["n"][0].upper() + sb["n"][1:] + ".")
            ey = d["exports"]["y"]
            name_it(d, "production", f"Top producers — thermal coal incl. lignite, EIA {py}", "World production (incl. lignite)")
            name_it(d, "consumption", f"Top consumers — thermal coal incl. lignite, EIA {d['consumption']['y']}", "World consumption (incl. lignite)")
            name_it(d, "exports", f"Top exporters — thermal coal, EIA {ey}", "World exports (thermal coal)")
            name_it(d, "imports", f"Top importers — thermal coal, EIA {d['imports']['y']}")
            name_it(d, "reserves", f"Reserves — all coal, EIA, last revised {rev}", "World reserves (all coal)")
            name_it(d, "flows", f"Main flows — all coal, customs data {BACI_YEAR}")
            name_it(d, "seaborne", kpi="Seaborne trade (all coal)")
            for side in ("exports", "imports"):
                extra_first.append({"key": f"allcoal-{side}", "title": f"All coal {side[:-1]}ers, customs data {BACI_YEAR}",
                                    "table": set_basis(allcoal[side], "thermal and metallurgical, customs data")})
            notes += ["Export and import rankings are thermal coal only (EIA). Bilateral flows, the all-coal tables and seaborne lanes are customs data (HS 2701/2702), which cover all coal including metallurgical coal.",
                      "Production and consumption are all coal minus metallurgical coal (EIA), computed country by country, and so include lignite; reserves are for all coal."]
            ry, rk = d["production"]["y"], {"bituminous": ("12-1", "MT"), "subbituminous": ("119-1", "MT"), "lignite": ("14-1", "MT"), "anthracite": ("11-1", "MT")}
            if all(ry in eia.s[k].get("WORL", {}) for k in rk.values()):
                parts_ = sum(eia.s[k]["WORL"][ry] for k in rk.values()) + eia.s[("130-1", "MT")]["WORL"][ry]
                add_ = (f"; with metallurgical coal ({_fmt(eia.s[('130-1', 'MT')]['WORL'][ry] * 1e-3)} Mt) they make the world total of "
                        f"{_fmt(eia.s[('7-1', 'MT')]['WORL'][ry] * 1e-3)} Mt" if abs(parts_ / eia.s[("7-1", "MT")]["WORL"][ry] - 1) < 0.005 else "")
                notes.append(f"World coal production by rank, {ry} (EIA, eia-intl): " + ", ".join(f"{n} {_fmt(eia.s[k]['WORL'][ry] * 1e-3)} Mt" for n, k in rk.items()) + add_ + ".")
            # EIA vs BACI exports
            disc += _compare("exports", eia, ("7-4", "MT"), 1e-3, baci, "coal", 1e6, "Mt", "EIA coal exports", BACI_YEAR)
        elif cid == "met-coal":
            d["production"] = eia.ranked(("130-1", "MT"), "Mt", 1e-3, "metallurgical coal production; 1000 metric tons converted to Mt")
            d["consumption"] = eia.ranked(("130-2", "MT"), "Mt", 1e-3, "metallurgical coal consumption; 1000 metric tons converted to Mt")
            d["exports"] = eia.ranked(("130-4", "MT"), "Mt", 1e-3, "metallurgical coal exports; 1000 metric tons converted to Mt")
            d["imports"] = eia.ranked(("130-3", "MT"), "Mt", 1e-3, "metallurgical coal imports; 1000 metric tons converted to Mt")
            d["flows"], flow_notes, d["flowDefs"] = met_coal_flows(baci, eia, d["exports"]["y"])
            summ(d, "production", d["production"])
            summ(d, "consumption", d["consumption"])
            summ(d, "exports", d["exports"])
            for sec, word in (("production", "Top producers"), ("consumption", "Top consumers"), ("exports", "Top exporters"), ("imports", "Top importers")):
                name_it(d, sec, f"{word} — metallurgical coal, EIA {d[sec]['y']}")
            # metallurgical coke, the product of the coal: production and trade by country (EIA, thousand metric tons)
            for sec, key in (("production", ("21-1", "MT")), ("exports", ("21-4", "MT")), ("imports", ("21-3", "MT"))):
                t = eia.ranked(key, "Mt", 1e-3, f"metallurgical coke {sec}; 1000 metric tons converted to Mt")
                extra_first.append({"key": f"coke-{sec}", "title": f"Metallurgical coke {'producers' if sec == 'production' else sec[:-1] + 'ers'}, EIA {t['y']}", "table": t})
            name_it(d, "flows", f"Main flows — metallurgical coal, exporters' statistics {BACI_YEAR}")
            notes.append(_note_group(baci, "coke", "Coke and semi-coke (HS 270400, customs data)") + " The tables of customs coke follow the EIA tables of metallurgical coke: the two sources "
                         "differ in what they count (EIA's coke is metallurgical coke by country; HS 2704 is every coke and semi-coke of coal, lignite or peat) and are not added. "
                         "Customs coke is not in the coal tables above, whose code list is the coal codes only, and the coal lanes do not hold it: the coke lanes are listed apart.")
            left_out = _left_out_note(baci, "coke")
            if left_out:
                notes.append(left_out)
            notes += flow_notes + ["Exports/imports tables are EIA metallurgical coal (not BACI)."]
        elif cid == "uranium":
            d["production"] = wna_uranium()
            g = add_baci_trade(d, cid, notes, disc)
            summ(d, "production", d["production"])
            summ(d, "exports", d["exports"], "uranium ores and natural uranium compounds (HS 261210, 284410), gross weight")
            pu = d["summary"]["production"]
            alt_fig(pu, pu["v"] * LB_U3O8_PER_TU / 1e6, "Mlb U3O8", f"1 t of uranium = {U3O8_PER_U} t of U3O8 = {LB_U3O8_PER_TU:,} lb of U3O8, from the "
                    f"standard atomic weights of uranium and oxygen (CIAAW, {CIAAW_URL}) and the definition of the pound; the pound of U3O8 is the unit of the uranium market")
            nc = eia.ranked(("27-7", "MK"), "GW", 1.0, "nuclear electricity installed capacity (million kilowatts, that is gigawatts)")
            extra_first.append({"key": "nuclear-capacity", "title": f"Nuclear generating capacity — GW, EIA {nc['y']}", "table": nc})
            notes += ["Trade is gross weight of uranium ores and natural uranium compounds in kt, not tonnes of contained uranium; enriched uranium and fuel are not covered. "
                      "The two cannot be converted into each other: the headline production carries pounds of U3O8 in brackets (Atlas conversion), the trade tables do not.",
                      f"Nuclear generating capacity by country (EIA, {nc['y']}) is the demand side shown here: reactor uranium requirements and reserves are not in the loaded sources."]
        # ------------------------------------------------------------ minerals (USGS)
        elif cid in USGS:
            spec = USGS[cid]
            tabs = {}
            for sec, (com, det, u, fac, label) in spec.items():
                r, t = us.ranked(com, det, u, fac, label, kind="production" if sec != "reserves" else "reserves",
                                 full=(cid, sec) in FULL_TABLE)
                tabs[sec] = r
            for sec in ("production", "reserves", "refinery"):
                if sec in tabs:
                    d[sec] = tabs[sec]
            g = add_baci_trade(d, cid, notes, disc)
            summ(d, "production", d["production"])
            wp_ = d["production"].get("worldPublished")
            if wp_:  # the key figure is the world total USGS publishes; the table's shares rest on the sum of its lines (said in the note)
                kp = d["summary"]["production"]
                kp["v"] = wp_
                kp["n"] = (f"USGS MCS {USGS_EDITION}, world total as published (rounded); the countries it names and its 'Other countries' line add up to "
                           f"{_nf(d['production']['world'])} {d['production']['u']}, on which the shares of the table are computed")
            if "reserves" in d:
                summ(d, "reserves", d["reserves"])
            summ(d, "exports", d["exports"])
            seaborne(d, g, f"main bulk group used: {g}" if cid in ("copper", "nickel", "zinc", "bauxite", "phosphate") else None)
        elif cid == "pgm":
            _pgm(d, us, baci, notes, summ, seaborne, add_baci_trade, disc, cid)
        elif cid == "npk":
            # trade only: no free file on disk gives the production of compound fertilisers (audit M-022)
            g = add_baci_trade(d, cid, notes, disc)
            summ(d, "exports", d["exports"], "NPK compound fertilisers (HS 310520), BACI, product weight")
            seaborne(d, g)
        elif cid == "pulses":
            # trade only: the USDA PSD file has no pulses and no other file on disk gives their production (audit M-023)
            g = add_baci_trade(d, cid, notes, disc)
            summ(d, "exports", d["exports"], "dried pulses, shelled (HS 0713), BACI, gross weight")
            seaborne(d, g)
        elif cid in ("ferrous-scrap", "ferro-alloys"):
            # trade only: the USGS file has no world table by country for ferrous scrap (United States figures only) nor for the ferro-alloys (A-010)
            g = add_baci_trade(d, cid, notes, disc)
            summ(d, "exports", d["exports"], f"{TRADE[cid][2]}, BACI, gross weight")
            seaborne(d, g)
        # ------------------------------------------------------------ softs
        elif cid == "cocoa":
            d["production"] = faostat_cocoa()
            g = add_baci_trade(d, cid, notes, disc)
            summ(d, "production", d["production"])
            summ(d, "exports", d["exports"], "cocoa beans (HS 1801), BACI")
            seaborne(d, g)
            notes += [f"Cocoa is not in USDA PSD: exports and imports are BACI cocoa beans (calendar {BACI_YEAR}); production is FAOSTAT {d['production']['y']}.",
                      "No consumption or grindings table: the ICCO's grindings by country are sold by subscription and are not copied, and the quarterly "
                      "grindings of the European, North American and Asian cocoa associations are press releases that the atlas has not read. "
                      f"One headline figure from the ICCO, which gives it as {ICCO_GRINDINGS[5]}: world grindings of {_nf(ICCO_GRINDINGS[1])} kt in the {ICCO_GRINDINGS[0]} crop year, "
                      f"{abs(ICCO_GRINDINGS[2]):.1f}% {'below' if ICCO_GRINDINGS[2] < 0 else 'above'} the year before ({ICCO_GRINDINGS[3]} of its Quarterly Bulletin of Cocoa Statistics, {ICCO_GRINDINGS[4]}).",
                      "Trade covers cocoa beans only (HS 1801): cocoa paste, butter and powder (HS 1803 to 1805) are not among the customs groups of the atlas, "
                      "so no table of cocoa products is shown yet."]
            icco, icco_warn, idn, short = cocoa_vs_icco(d)  # not `warn`: that name is the function that main() calls further down
            disc.append(icco)
            add_caveat(d["production"], icco_warn)
            if idn:
                next(r for r in d["production"]["rows"] if r["c"] == "IDN")["n"] = idn
            d["summary"]["production"]["n"] = joinn(d["summary"]["production"]["n"], short)
        elif cid in PSD:
            com, cons_attr, ex_attr, im_attr = PSD[cid]
            what = PSD_WHAT[cid]
            d["production"], pu = psd.ranked(com, "Production", f"{what} production")
            d["consumption"], _ = psd.ranked(com, cons_attr, f"{what} domestic consumption/use")
            d["exports"], _ = psd.ranked(com, ex_attr, f"{what} exports")
            d["imports"], _ = psd.ranked(com, im_attr, f"{what} imports")
            g, (bu, bdiv), bwhat = TRADE[cid]
            adjust = rice_note = None
            if cid == "rice":
                adjust, _, rice_note = rice_adjust(psd, baci)
            d["flows"] = baci.flows(g, bu, bdiv, adjust=adjust)
            disc.extend(baci.last_susp)
            summ(d, "production", d["production"])
            summ(d, "consumption", d["consumption"])
            summ(d, "exports", d["exports"])
            seaborne(d, g)
            if cid == "rice" and "seaborne" in d["summary"]:
                sb = d["summary"]["seaborne"]
                sb["n"] = "Customs gross weight: paddy and husked rice count at full weight, unlike the milled-basis tables. " + sb["n"][0].upper() + sb["n"][1:] + "."
            notes.append(f"Flows are BACI calendar-{BACI_YEAR} customs flows; ranked trade tables are USDA PSD market year {PSD_LABEL}, a forecast (trader reference). Years differ.")
            if cid == "coffee":
                notes.append("PSD coffee exports/imports include roasted and soluble coffee in green-bean equivalent; BACI flows are green beans only (HS 0901.11/12).")
                notes.append("Trade of roasted coffee (HS 090121, 090122) and of coffee extracts and soluble coffee (HS 210110) is not among the customs groups of the atlas, "
                             "so no table of processed coffee is shown yet.")
            if cid == "rice":
                notes.append("PSD rice is on a milled basis; PSD 'Exports' are market-year (not trade-year) figures.")
                notes.append(rice_note)
                name_it(d, "flows", "Main flows — paddy converted to milled equivalent" if adjust else "Main flows — customs weight, paddy included")
            if cid == "sugar":
                notes.append("PSD sugar is centrifugal sugar in raw value (cane and beet); consumption is PSD 'Human Dom. Consumption'.")
            if cid == "soybeans":
                notes.append(f"PSD domestic consumption = crush + food + feed/waste; production is for the market year starting in {PSD_MY} "
                             f"(Brazil/Argentina harvest early {PSD_MY + 1}, US harvest autumn {PSD_MY}).")
            disc += _psd_vs_baci(psd, baci, cid, com, ex_attr, g)
            bal = psd.balance(com, "Total Disappearance" if cid == "sugar" else cons_attr)
            if bal:
                d["balance"] = bal
            # the 27 member states: FAOSTAT production and customs trade, beside the USDA row for the EU as one entity (audit M-024, C-104)
            fao = faostat_eu_production(cid)
            if fao:
                basis = FAO_EU_ITEMS[cid][2]
                extra_first.append({"key": "eu-production", "title": f"EU member states, production{', ' + basis if basis else ''} (FAOSTAT)", "table": fao})
            if any(r["c"] == "EU27" for sec in ("exports", "imports") for r in d[sec]["rows"]):
                tr = eu_trade(baci, g, bdiv)
                for side in ("exports", "imports"):
                    extra_first.append({"key": f"eu-{side}", "title": f"EU member states, {side} (customs data)", "table": eu_trade_table(side, tr, bwhat, bu)})
                    row = next((r for r in d[side]["rows"] if r["c"] == "EU27"), None)
                    if row:
                        text = eu_split_note(tr, side, bu)
                        row["n"] = joinn(row.get("n"), text)
                        d[side]["n"] = joinn(d[side]["n"], text)
                        d[side]["eu"] = {"y": BACI_YEAR, "s": "baci", "u": bu, **dict(zip(("total", "intra", "extra"), (rnd(x) for x in tr["ex" if side == "exports" else "im"])))}
        else:
            raise SystemExit(f"no recipe for commodity {cid}")

        # second trade tables for metals traded mainly as refined/intermediate products,
        # and ending stocks for the PSD crops (rendered by the commodity page as extra sections)
        extra = list(extra_first)
        if cid == "copper":
            for side, title in (("exports", "Refined and blister copper exporters"), ("imports", "Refined and blister copper importers")):
                t, _ = baci.ranked("copper-refined", side, *MT, "refined and blister copper (HS 7402, 7403), gross weight")
                extra.append({"key": f"refined-{side}", "title": title, "table": t})
        elif cid == "nickel":
            for side, title in (("exports", "Nickel intermediates and metal exporters"), ("imports", "Nickel intermediates and metal importers")):
                t, _ = baci.ranked("nickel-int", side, *MT, "nickel mattes, intermediates and unwrought nickel (HS 7501, 7502), gross weight")
                extra.append({"key": f"int-{side}", "title": title, "table": t})
            if len(baci.group("nickel-fe")):
                for side, title in (("exports", "Ferro-nickel and nickel pig iron exporters"), ("imports", "Ferro-nickel and nickel pig iron importers")):
                    t, _ = baci.ranked("nickel-fe", side, *MT, "ferro-nickel (HS 720260), which includes nickel pig iron, gross weight, not contained nickel")
                    extra.append({"key": f"ferro-{side}", "title": title, "table": t})
        elif cid == "bauxite":
            t, _ = baci.ranked("alumina", "exports", *MT, "alumina (HS 281820)")
            extra.append({"key": "alumina-exports", "title": "Alumina exporters", "table": t})
            t, _ = baci.ranked("alumina", "imports", *MT, "alumina (HS 281820)")
            extra.append({"key": "alumina-imports", "title": "Alumina importers", "table": t})
        elif cid == "zinc":
            t, _ = baci.ranked("zinc-metal", "exports", *MT, "unwrought zinc (HS 7901)")
            extra.append({"key": "metal-exports", "title": "Refined zinc exporters", "table": t})
        elif cid == "steel":
            tb = hs4_exports(["7304", "7305", "7306"])
            if tb:
                t = ranked([(c if c in ISO_SET else None, v / 1e6) for c, v in tb.items()], BACI_YEAR, "baci", "Mt", world=sum(tb.values()) / 1e6,
                           n=f"CEPII BACI HS92 tubes, pipes and hollow profiles of iron or steel (HS 7304 to 7306), {BACI_YEAR}, all transport modes, gross weight; "
                             "from the four-digit customs extract, without the cleaning rules of the other trade tables; not part of the steel totals above")
                extra.append({"key": "tubes-exports", "title": "Tube and pipe exporters (HS 7304 to 7306, not in the totals above)", "table": set_basis(t, "gross weight")})
        for g2, stem, nm, what2 in EXTRA_GROUPS.get(cid, []):
            for side, word in (("exports", "exporters"), ("imports", "importers")):
                t, _ = baci.ranked(g2, side, *MT, what2)
                extra.append({"key": f"{stem}-{side}", "title": f"{nm} {word}{TITLE_NOTE.get(g2, '')}", "table": set_basis(t, "gross weight")})
        for com2, stem, nm, what2 in PSD_EXTRA.get(cid, []):
            for attr, key, word in (("Production", "production", "producers"), ("Domestic Consumption", "consumption", "consumers")):
                t, _ = psd.ranked(com2, attr, f"{what2} {'production' if key == 'production' else 'domestic consumption'}")
                extra.append({"key": f"{stem}-{key}", "title": f"{nm} {word}", "table": t})
        if cid in PSD:
            com = PSD[cid][0]
            try:
                t, _ = psd.ranked(com, "Ending Stocks", f"{PSD_WHAT[cid]} ending stocks")
                if cid == "sugar":
                    thai_stocks_note(psd, t)
                extra.append({"key": "stocks", "title": "Ending stocks", "table": t})
            except SystemExit:
                pass
        if extra:
            d["extra"] = extra

        # lead/tin/refined copper etc: side notes with BACI trade of the second group
        if cid == "copper":
            notes.append(_note_group(baci, "copper-refined", "Refined copper (HS 7403, 7402)"))
            cu = baci.group("copper-ore")
            chl = cu[cu["o"] == "CHL"]
            pe = chl[chl["flag"].str.contains("est-peer", na=False)]
            if len(pe):
                cn = chl[chl["d"] == "CHN"]
                k, ky = baci.peer[("copper-ore", "CHL")]
                usual = (f"times {k:.3f}, the median ratio of Chile's unit value to Peru's in the {len(ky)} years in which Chile's declarations are in "
                         f"line ({year_list(ky)})" if ky else "(no year in which Chile's declarations are in line gives a usual ratio)")
                notes.append(f"Chile's copper concentrate: customs data declare some of it at {pe['uvp'].min():,.0f} to {pe['uvp'].max():,.0f} USD per tonne in "
                             f"{BACI_YEAR}, against about {pe['uve'].median() / k:,.0f} for Peru's concentrate to the same destinations; a tonnage declared in "
                             "contained copper rather than gross weight is a plausible cause, not established here. Where Chile's unit value is more than "
                             "1.8 times Peru's (to the same destination when Peru ships 50 kt or more there, otherwise Peru's average of the year), the tonnage "
                             f"is an Atlas estimate: the declared value divided by Peru's unit value {usual}. Chile then exports {chl['t'].sum() / 1e6:.2f} Mt instead of the {chl['t0'].sum() / 1e6:.2f} Mt declared, and Chile to "
                             f"China {cn['t'].sum() / 1e6:.2f} Mt instead of {cn['t0'].sum() / 1e6:.2f} Mt. Importers' own declarations (UN Comtrade) would "
                             "measure it; the atlas has no access key for them.")
            notes.append("Trade tables are copper ores and concentrates in gross weight (Mt), not contained copper; USGS production is contained copper (kt Cu). The refinery table is USGS refined copper production (primary and secondary).")
        elif cid == "bauxite":
            notes.append(_note_group(baci, "alumina", "Alumina (HS 281820)"))
            notes.append("USGS production and reserves are dry tonnes; the refinery table is USGS alumina refinery production in calcined-equivalent weight (Mt), "
                         "listed for every country USGS names.")
            gin = next((r["v"] for r in d["production"]["rows"] if r["c"] == "GIN"), None)
            if gin:
                gp, gv, gy, gurl = GUINEA_EXPORTS
                disc.append(f"Guinea {gy}: the USGS estimate of bauxite mined is {_nf(gin)} Mt, {gin / d['production']['world']:.0%} of the world total, but Guinea's exports alone "
                            f"were reported at {gv} Mt for {gy} ({gp}: {gurl}), more than USGS estimates Guinea mined; the same article gives 74% of the shipments to China "
                            "(Chinese customs data). The USGS production figure and Guinea's share of the world total are therefore probably understated.")
            idn_prod = dict(us.table("Alumina", "Alumina, refinery production", year=str(BACI_YEAR), factor=1e-3)["rows"]).get("IDN")
            idn_exp = baci.totals("alumina", "exports").get("IDN")
            if idn_prod and idn_exp and idn_exp > idn_prod:
                disc.append(f"Indonesia, alumina {BACI_YEAR}: customs data (BACI, HS 281820, gross weight) record {idn_exp:.2f} Mt of exports (rank "
                            f"{1 + sum(1 for v in baci.totals('alumina', 'exports').values() if v > idn_exp)} among exporters), against a USGS alumina refinery output of {idn_prod:.2f} Mt "
                            f"(calcined-equivalent weight) for {BACI_YEAR}. The two may be on different bases; the cause is not established here; "
                            "the exporters table follows customs data.")
        elif cid == "nickel":
            notes.append(_note_group(baci, "nickel-int", "Nickel intermediates and unwrought nickel (HS 7501, 7502)"))
            if len(baci.group("nickel-fe")):
                notes.append(_note_group(baci, "nickel-fe", "Ferro-nickel, including nickel pig iron declared as ferro-nickel (HS 720260)"))
            notes.append("Trade tables are nickel ores and concentrates in gross weight (Mt); production and reserves are contained nickel (kt Ni).")
            see.append({"k": "ferro-alloys", "text": "the other ferro-alloys of HS 7202 (ferro-chromium, ferro-manganese, silico-manganese, ferro-silicon and the rest); ferro-nickel is on this page"})
            ore = baci.group("nickel-ore")
            ore = ore[ore["t0"] > 0]
            lat, sul = ore[ore["uvp"] < 300], ore[ore["uvp"] >= 300]
            if len(lat) and len(sul):
                uv = lambda x: x["usd"].sum() * 1e3 / x["t"].sum()
                notes.append(f"The ore tables mix two products: laterite ore, {lat['t'].sum() / 1e6:.1f} Mt in {BACI_YEAR} at {uv(lat):,.0f} USD per tonne on average "
                             f"(by unit value, flows under 300 USD per tonne), and sulphide concentrate, {sul['t'].sum() / 1e6:.2f} Mt at {uv(sul):,.0f} USD per tonne. "
                             "A low unit value is normal for laterite ore, so no ore flow is flagged for it.")
        elif cid == "zinc":
            notes.append(_note_group(baci, "zinc-metal", "Unwrought zinc (HS 7901)"))
            notes.append("Trade tables are zinc ores and concentrates in gross weight (Mt); production and reserves are contained zinc (kt Zn).")
        elif cid == "lead":
            notes.append(_note_group(baci, "lead-metal", "Unwrought lead (HS 7801)"))
            notes.append("Trade tables are lead ores and concentrates in gross weight (Mt); production and reserves are contained lead (kt Pb).")
        elif cid == "tin":
            notes.append(_note_group(baci, "tin-ore", "Tin ores and concentrates (HS 2609)"))
            notes.append("Trade tables are unwrought tin (HS 8001, alloyed or not; waste and scrap, HS 8002, are not included) in kt; production and reserves are contained tin (t Sn).")
            ranks = [r["c"] for r in d["production"]["rows"]]
            if "MMR" in ranks:
                mmr = d["production"]["rows"][ranks.index("MMR")]["v"]
                notes.append(f"Myanmar ranks {ranks.index('MMR') + 1} in the USGS production table ({_nf(mmr)} t Sn in {d['production']['y']}); "
                             "mining in Wa State, its main tin area, was suspended from 1 August 2023 (see the events).")
            tt, tnotes = tin_china_declared(baci)
            d["extra"] = d.get("extra", []) + [{"key": "tin-china-declared", "title": f"China's declared imports of tin ores and concentrates by origin ({comtrade_tin.load()['source']})",
                                                "table": tt}]
            notes += tnotes
            tin = baci.group("tin-ore", 2024)
            cog = tin[tin["o"] == "COG"]
            cod = tin[tin["o"] == "COD"]
            listed = {r[0] for r in us.table("Tin", "Mine production")["rows"]}
            if len(cog) and len(cod) and "COG" not in listed:
                notes.append(f"Republic of the Congo is recorded as an exporter of tin concentrate ({cog['t'].sum() / 1e3:.1f} kt in 2024, "
                             f"{cog['usd'].sum() * 1e3 / cog['t'].sum():,.0f} USD/t) but is not a tin producer in the USGS table, while DR Congo is "
                             f"({cod['usd'].sum() * 1e3 / cod['t'].sum():,.0f} USD/t). Relabelling of DR Congo material is a possible cause; it is not established here.")
        elif cid == "phosphate":
            notes.append("The main trade tables are natural phosphates (HS 2510), gross weight; USGS production is marketable phosphate rock. "
                         "The tables under them are the phosphate fertilisers and the acid, each its own customs code, gross weight, and none is in the totals of another.")
            for g2, _, _, what2 in EXTRA_GROUPS[cid]:
                notes.append(_note_group(baci, g2, what2[0].upper() + what2[1:]))
            notes.append("HS 310310 holds all the superphosphates, single and triple, in one code; TSP, the triple grade, has no code of its own. The Pink Sheet's TSP price is the price "
                         "of triple superphosphate only: it is not a price of the whole group. HS 310540 holds MAP and its mixtures with DAP. "
                         "HS 280920 is the acid, a liquid, which the lanes treat as chemical-tanker cargo: the typical class is an Atlas assumption, as for every lane. "
                         "Other phosphatic fertilisers (HS 310320, 310390) are not loaded; the compound fertilisers, with two or three nutrients, are on the NPK page.")
            see.append({"k": "npk", "text": "the compound fertilisers that carry nitrogen, phosphorus and potassium"})
            see.append({"k": "sulphur", "text": "sulphur, its production and trade"})
        elif cid == "lithium":
            # rule 9 of clean() (pipeline/trade/clean.py) has already left these flows out of every table, lane and country figure
            lows = [r for r in baci.dropped if r["rule"] == "low-uv" and r["group"] == "lithium" and r["year"] == BACI_YEAR]
            if lows:
                notes.append(f"{len(lows)} flows of the lithium chemicals codes ({_fmt(sum(r['t'] for r in lows) / 1e3)} kt in {BACI_YEAR}) are declared under "
                             f"{LITHIUM_MIN_UV:,} USD per tonne, the price of ore or concentrate rather than of a lithium chemical. The atlas leaves them out of "
                             "the trade tables, the lanes, the chokepoint estimates and the country figures; the cause (a product or a weight misdeclared, for "
                             "instance) is not established here: " + "; ".join(f"{cname(r['o'])} to {cname(r['d'])} {_fmt(r['t'] / 1e3)} kt at {r['uvp']:,.0f} USD/t" for r in lows[:6])
                             + (f"; and {len(lows) - 6} smaller" if len(lows) > 6 else "") + ".")
            notes.append("Trade tables and flows are lithium carbonate and hydroxide/oxide (HS 283691, 282520) in gross weight (kt), not lithium content. "
                         "USGS production is contained lithium (t Li), so units differ.")
            sp = baci.group("spodumene")
            if len(sp):
                code, (_, exporters, importers, rest) = next(iter(HS_SPLIT.items()))
                allc = baci.df[(baci.df["group"].isin(["spodumene", rest])) & (baci.df["year"] == BACI_YEAR)]
                st, sv = sp["t"].sum() / allc["t"].sum(), sp["usd"].sum() / allc["usd"].sum()
                t, _ = baci.ranked("spodumene", "exports", *MT, f"HS {code} rows to China only", digits=3)
                t["s"] = "atlas"
                t["shareOf"] = "these exports to China"  # the total is the rows of the table, not the world's exports of the code
                pages = [f"{cname(c)}: {ABS_LITHIUM}" if c == "AUS" else f"{cname(c)}: {SPODUMENE_PAGES[c][0]} ({SPODUMENE_PAGES[c][1]}, {SPODUMENE_PAGES[c][2]})"
                         for c in exporters]
                t["n"] = (f"Atlas estimate: spodumene concentrate has no customs code of its own; it is read from HS {code} ('mineral substances not elsewhere "
                          f"specified'), keeping only the rows from {_and([cname(c) for c in exporters])} to {_and([cname(c) for c in importers])}, the exporters for "
                          f"which a page read by the atlas says they ship lithium concentrate to China (the pages are in the notes of the page): {st:.0%} of the tonnage and {sv:.0%} of the "
                          f"value of the code in {BACI_YEAR}. These rows may still hold other minerals. "
                          "Customs gross weight of concentrate, not lithium content. " + t["n"])
                extra = d.setdefault("extra", [])
                extra.append({"key": "spodumene-exports", "title": f"Spodumene concentrate to China, {BACI_YEAR} (Atlas estimate)",
                              "table": set_basis(t, "concentrate, gross weight")})
                uv = sp["usd"].sum() * 1e3 / sp["t"].sum()
                notes.append(f"Spodumene concentrate, the ore concentrate of hard-rock lithium mines, is shown in its own table (Atlas estimate from HS {code}, "
                             f"{sig(sp['t'].sum() / 1e6)} Mt to China in {BACI_YEAR} at {sig(uv)} USD per tonne on average); it is not added to the chemicals "
                             "tables, whose tonnes are of another product. Australia declares its spodumene concentrate under this code: its statistics office "
                             f"created the national subheading 25309011 'Lithium concentrates' for it in January 2021 ({ABS_LITHIUM}). The spodumene "
                             "lanes and their route show its history from 2021 only: no page read says what the code held from these exporters before.")
                notes.append("Pages read for the exporters of the spodumene table: " + "; ".join(pages) + ".")
                skipped = allc[(allc["group"] == rest) & allc["o"].isin(HS_NOT_READ[code]) & allc["d"].isin(importers)].groupby("o")["t"].sum()
                names = [f"{cname(c)} {skipped.get(c, 0) / 1e6:.2f} Mt" if skipped.get(c, 0) else f"{cname(c)} (no {BACI_YEAR} row)" for c in HS_NOT_READ[code]]
                notes.append(f"Not read as spodumene: HS {code} rows to {_and([cname(c) for c in importers])} from {_and(names)} in {BACI_YEAR}. They may hold lithium "
                             "concentrate, but the atlas found no page that says so for these exporters, so they stay out of the spodumene table.")
            pr = d["summary"].get("production")
            if pr and pr["u"] == "t Li":
                alt_fig(pr, pr["v"] * LCE_PER_LI / 1e6, "Mt LCE", f"{LCE_PER_LI:.3f} t of lithium carbonate (Li2CO3) per t of lithium, from the standard "
                        f"atomic weights of lithium, carbon and oxygen (CIAAW, {CIAAW_URL}); lithium carbonate equivalent is a unit, not a product traded")
        elif cid == "cobalt":
            ore, mat = hs4_exports(["2605"]), hs4_exports(["8105"])
            if ore and mat:
                notes.append(f"Trade is in gross weight (kt), mostly HS 8105 (mattes, intermediate products such as crude hydroxide, unwrought cobalt, scrap and powders): "
                             f"ores and concentrates (HS 2605) are only {sum(ore.values()) / 1e3:.0f} kt of the {sum(ore.values()) / 1e3 + sum(mat.values()) / 1e3:.0f} kt "
                             f"({sum(ore.values()) / (sum(ore.values()) + sum(mat.values())):.0%}) that the HS4 extract gives for both headings in {BACI_YEAR}, before the cleaning rules. USGS production is contained cobalt (t Co), so the two are not comparable.")
            cb = baci.group("cobalt")
            cn_ = cb[(cb["o"] == "COD") & (cb["d"] == "CHN")]
            if len(cn_):
                rest = cb.drop(cn_.index)
                notes.append(f"DR Congo to China is the main flow ({cn_['t'].sum() / 1e3:.0f} kt, declared at {cn_['usd'].sum() * 1e3 / cn_['t'].sum():,.0f} USD per tonne, against "
                             f"{rest['usd'].sum() * 1e3 / rest['t'].sum():,.0f} USD per tonne for all other flows): by its unit value it is mostly intermediate products rather than metal; "
                             "customs data do not say so.")
            notes.append("DR Congo suspended its cobalt exports until 15 October 2025 and, from 16 October 2025, caps them by quota: 18,125 t for the rest of 2025 and "
                         f"96,600 t a year for 2026 and 2027, set by its regulator ARECOMS ({BENCHMARK_COBALT}). The {BACI_YEAR} flows shown here predate these measures; "
                         "the basis of the quotas (contained or gross weight) is not compared with the tables.")
            name_it(d, "exports", kpi="World exports (intermediates and metal, gross wt)")
        elif cid == "rare-earths":
            notes.append("Trade covers rare-earth metals and compounds (HS 280530, 284610, 284690) in gross weight (kt); USGS production is REO equivalent (t REO).")
        elif cid == "aluminium":
            notes.append("Trade is unwrought aluminium (HS 7601); USGS production is primary smelter output. Bauxite reserves are under 'bauxite'.")
        elif cid == "steel":
            tb = hs4_exports(["7304", "7305", "7306"])
            tube = (f" Tubes, pipes and hollow profiles (HS 7304 to 7306, chapter 73) are not included: all countries exported {sum(tb.values()) / 1e6:.1f} Mt of them "
                    f"in {BACI_YEAR}, {tb.get('CHN', 0) / 1e6:.1f} Mt by China (see the table of tube exporters)." if tb else "")
            notes.append("Trade is steel products, gross weight: HS 72 (iron and steel) without pig iron, ferro-alloys and scrap (HS 7201 to 7205)." + tube
                         + " The world total adds up the exports of every country, so it includes trade between EU member states. USGS production is raw steel.")
            pr = d["production"]
            notes.append(f"USGS names {len(pr['rows'])} producing countries; every other producer is in its 'Other countries' line ({_nf(pr['other'])} {pr['u']}), "
                         "which the page shows apart from the countries it names but does not draw as rows.")
            wp, wdoc, wv, wu, wy, wurl, _ = WORLDSTEEL
            disc.append(f"Crude steel production {wy}: the USGS estimate is {_nf(pr['world'])} {pr['u']} for the listed countries and 'Other countries' "
                        f"(USGS rounds its world total to {_nf(us.table('Iron And Steel', 'Raw steel')['world'])} {pr['u']}); the {wp} reports {wv:,} {wu} of world crude steel "
                        f"production for {wy} ({wdoc}, {wurl}; its press release of 23 January 2026 gave 1,849.4 {wu} before the revision). The table shows the USGS figures, which come by country: "
                        f"the {wp}'s country table is not reproduced, because its terms of use do not allow it (see the registry of sources).")
            d["summary"]["production"]["n"] += f"; {wp}: {wv:,} {wu} in {wy} (see the discrepancies)"
        elif cid in ("gold", "silver"):
            if _fine_metal(d, baci, cid, disc):
                notes.append(FINE_NOTE)
            else:
                notes.append("Trade tonnage is customs gross weight (CEPII BACI): dore and alloys count with the base metal they contain; treat flows as indicative.")
            disc.append(_prec_disc(d, cid))
            if cid == "gold":
                pr = d["production"]
                wp, wdoc, wv, wu, wy, wurl, _ = WGC_MINE
                disc.append(f"World mine production {wy}: the USGS estimate is {_nf(pr['world'])} {wu} (rounded); the {wp} reports {wv:,} {wu} ({wdoc}, {wurl}), "
                            f"so the USGS total is {1 - pr['world'] / wv:.0%} lower. The {wp} describes its {wy} figure as subject to revision; its own tables are not copied.")
                notes.append(f"The table lists the {len(pr['rows'])} countries USGS names; its 'Other countries' line ({_nf(pr['other'])} {pr['u'].split()[0]}, "
                             f"{pr['other'] / pr['world']:.0%} of the total) covers every other producer.")
        elif cid == "iron-ore":
            notes.append("USGS production is usable ore (gross weight); reserves are crude ore. Iron-content figures (Australia ~600 Mt Fe in 2025) are in the USGS data but not shown.")
        elif cid == "manganese":
            notes.append("Trade is manganese ore (HS 2602), gross weight (Mt); USGS production is shown in kt as in the USGS table.")
            see.append({"k": "ferro-alloys", "text": "ferro-manganese and silico-manganese, the manganese alloys"})
        elif cid == "urea":
            ut, unotes = faostat_urea(baci)
            d["extra"] = d.get("extra", []) + [{"key": "urea-production", "title": "Urea producers — Mt of urea, product weight", "table": ut}]
            notes.append("Two production tables on two bases: ammonia plant output in tonnes of nitrogen (USGS), the feedstock of urea and of the other nitrogen "
                         f"fertilisers, and urea production in tonnes of product (FAOSTAT), the basis of the urea trade tables (HS 310210). Urea holds {K.N_IN_UREA:.1%} nitrogen "
                         "(from molar masses), so tonnes of nitrogen and tonnes of urea are not interchangeable.")
            notes += unotes
            notes.append("The main trade tables are urea (HS 310210). The tables under them are ammonia, ammonium nitrate, ammonium nitrate with limestone, UAN and ammonium sulphate, each its own customs code, "
                         "gross weight (product tonnes, not tonnes of nitrogen), and none is in the totals of another. The ammonia producers table above is plant output "
                         "in tonnes of nitrogen: it is not the ammonia trade in tonnes of product.")
            for g2, _, _, what2 in EXTRA_GROUPS[cid]:
                notes.append(_note_group(baci, g2, what2[0].upper() + what2[1:]))
            notes.append("Ammonia is carried refrigerated in gas carriers and UAN solution as a liquid in chemical tankers: they are not dry bulk, and the lanes give them "
                         "the typical classes of those ships (an Atlas assumption, no page read for it); their ports are the general port of the country unless a page names the cargo. "
                         "HS 310230 is ammonium nitrate alone, solid or in solution; HS 310240 is ammonium nitrate mixed with calcium carbonate or other inorganic substances that carry no "
                         "fertilising element (calcium ammonium nitrate and the like): two tables, and a tonne is in one of them only. "
                         "HS 281420 (ammonia in solution), 310229, 310250, 310260, 310270 and 310290 (the other nitrogen fertilisers) are not loaded.")
            notes.append("Price: the World Bank Pink Sheet gives urea monthly. The one other product of the page with a free price is ammonia: the annual average, free on board "
                         "Gulf Coast, in US dollars per short ton as USGS gives it (United States salient statistics, source Green Markets), not converted. "
                         "No free price was found for ammonium nitrate, UAN or ammonium sulphate.")
            see.append({"k": "npk", "text": "the compound fertilisers that carry nitrogen, phosphorus and potassium"})
        elif cid == "potash":
            k2o, f = d["production"], round(K.K2O_IN_KCL, 4)  # the factor as printed: each converted figure reproduces from it, to 3 digits
            kcl = {"y": k2o["y"], "s": "atlas", "u": "Mt KCl", "world": sig(k2o["world"] / f), "rows": [{**r, "v": sig(r["v"] / f)} for r in k2o["rows"]],
                   "n": (f"Atlas conversion: {k2o['n']}, divided by {f:.4f}, the K2O content of pure potassium chloride (from molar masses), to give tonnes of potassium "
                         "chloride comparable with the trade tables, shown to three significant digits; real products hold less K2O than pure potassium chloride, "
                         "so their weight is somewhat higher. The K2O figures as published are in the table below")}
            d["production"] = kcl
            d["extra"] = d.get("extra", []) + [{"key": "k2o-production", "title": "Top producers — Mt of K2O content, as published by USGS", "table": set_basis(k2o, "K2O content")}]
            d["summary"]["production"] = {"v": kcl["world"], "u": kcl["u"], "y": kcl["y"], "s": "atlas",
                                          "n": f"Atlas conversion of the USGS world total of potash mine production, {_nf(k2o['world'])} Mt K2O, at {f:.4f} t of K2O per tonne of potassium chloride, to three significant digits"}
            notes.append("Units: trade is potassium chloride (HS 310420), product weight. USGS production is in K2O equivalent; the production table converts it to potassium "
                         f"chloride at {f:.4f} (Atlas conversion) so that it reads beside trade, and the K2O figures as published follow it. Reserves stay in K2O content.")
            fn = faostat_potash_note(baci, k2o)
            if fn:
                notes.append(fn)
            for g2, _, _, what2 in EXTRA_GROUPS[cid]:
                notes.append(_note_group(baci, g2, what2[0].upper() + what2[1:]))
            notes.append("The tables for potassium sulphate (SOP, HS 310430) are a second product with its own customs code, gross weight, in none of the totals above. "
                         "Crude natural potassium salts (HS 310410) and the other potassic fertilisers (HS 310490) are not loaded.")
            see.append({"k": "npk", "text": "the compound fertilisers that carry nitrogen, phosphorus and potassium"})
        elif cid == "npk":
            notes.append("The main trade tables are HS 310520, fertilisers containing the three fertilising elements nitrogen, phosphorus and potassium, product weight. The tables "
                         "under them are the compound fertilisers with two of the three nutrients: nitrates and phosphates (HS 310551), nitrogen and phosphorus other than "
                         "those (HS 310559) and phosphorus and potassium (HS 310560), also product weight; each customs code is in one group, and none is in the totals of the "
                         "other. The grade of each flow (the shares of the nutrients) is not in customs data. The tablets and small packages (HS 310510) and the rest of "
                         "heading 3105 (HS 310590) are not loaded.")
            notes.append("No production table: no free file loaded by the atlas gives the production of compound fertilisers (FAOSTAT's fertiliser tables by nutrient are not loaded yet).")
            see.append({"k": "urea", "text": "urea, ammonia, ammonium nitrate, UAN and ammonium sulphate"})
            see.append({"k": "phosphate", "text": "phosphate rock, DAP, MAP, superphosphates and phosphoric acid"})
            see.append({"k": "potash", "text": "potassium chloride and potassium sulphate"})
        elif cid == "sulphur":
            notes.append("Trade is sulphur gross weight: crude or unrefined sulphur (HS 250310) with sublimed, precipitated and colloidal sulphur (HS 280200); HS 250390 (other "
                         "sulphur) is in the group but holds no flow in the customs file. Sulphuric acid and sulphur compounds are not covered.")
            notes.append("USGS production is sulphur content in all forms (elemental sulphur and the sulphur in sulphuric acid, by country), in tonnes of sulphur: "
                         "the trade tables are tonnes of the product shipped, so the two are not on one basis.")
            notes.append("Price: the World Bank Pink Sheet has no sulphur series. The only price on the page is the USGS annual average unit value of elemental sulphur, "
                         "free on board mine or plant, in US dollars per metric ton (United States salient statistics); no monthly series was loaded.")
            see.append({"k": "phosphate", "text": "phosphate rock, the phosphate fertilisers and phosphoric acid"})
        elif cid == "wheat":
            notes.append("The tables under the USDA tables are wheat or meslin flour (HS 110100), customs gross weight (CEPII BACI), a product of its own: they are not added to "
                         "the grain tables above, and the flour is not converted to wheat. " + _note_group(baci, "wheat-flour", "Wheat flour (HS 110100)") +
                         " Customs gross weight does not tell bulk from bagged or boxed cargo and no free source gives the split, so the atlas draws no lanes for flour. Semolina and groats (HS 1103), starch (HS 1108) and gluten (HS 1109) are not loaded.")
        elif cid == "corn":
            notes.append("The tables under the USDA tables are brewing or distilling dregs and waste (HS 230330), customs gross weight (CEPII BACI). This one code holds distillers' dried grains "
                         "(DDGS, the residue of grain ethanol and spirits) with brewers' grains and other dregs and waste: customs data do not tell them apart, so the tables are not a DDGS "
                         "series. They are not added to the grain tables above. " + _note_group(baci, "brewing-distilling-dregs", "Brewing and distilling dregs and waste (HS 230330)") +
                         " Customs gross weight does not tell bulk from bagged or containerised cargo and no free source gives the split, so the atlas draws no lanes for the dregs. Corn gluten feed and meal and the other residues of starch manufacture (HS 230310) are not loaded.")
        elif cid in ("barley", "sorghum"):
            kind = "barley" if cid == "barley" else "grain sorghum"
            code = "100300" if cid == "barley" else "100700"
            notes.append(f"Trade is {kind} (HS {code}), customs gross weight. USDA PSD gives production, use, trade and stocks of marketing years; the customs table is a calendar year. "
                         + ("Malting and feed barley are not told apart in the customs code; malt (HS 1107), barley flours and worked barley grains (HS 1104) are not loaded." if cid == "barley"
                            else "Sweet sorghum, broomcorn and forage sorghum are not in the code or are not told apart; sorghum flour and groats are not loaded."))
            end = _price_end(f"{cid}-m")
            annual = _price_span(f"{cid}-a")
            if end and annual:
                notes.append(f"Price: the World Bank Pink Sheet has a monthly {kind} series that stops in {end}; it is published to that month and marked closed. "
                             f"After it the price is the annual average of the World Bank's annual workbook, {annual[0]} to {annual[1]}, a series of its own (nominal US dollars a tonne). "
                             "The workbook does not say how its annual values after the monthly series are built. No monthly series after the Pink Sheet's was loaded.")
            elif end:
                notes.append(f"Price: the only free price file the atlas loads, the World Bank Pink Sheet, has a {kind} series that stops in {end}; it is published to that month and marked closed. "
                             "No annual series after it was loaded.")
            else:
                notes.append(f"No free price series: the World Bank Pink Sheet, the only price file the atlas loads, has no current {kind} series, and no other free one was found.")
        elif cid in ("sunflower", "rapeseed"):
            sun = cid == "sunflower"
            seed, oil, meal = ("sunflower seed (HS 120600)", "sunflower-seed or safflower oil (HS 151211, 151219)", "sunflower-seed oil-cake and other solid residues (HS 230630)") if sun else (
                "rapeseed (HS 120500)", "rape, colza or mustard oil (HS 151410, 151490)", "rape or colza seed oil-cake and other solid residues (HS 230640)")
            go, gm = ("sunflower-oil", "sunflower-meal") if sun else ("rapeseed-oil", "rapeseed-meal")
            notes.append(f"The tables of the seed are USDA PSD (marketing years); its flows and seaborne figure are customs data for {seed}, gross weight (CEPII BACI); oil seed, "
                         "seed for sowing and snack seed are not told apart in the code. " if sun else
                         f"The tables of the seed are USDA PSD (marketing years); its flows and seaborne figure are customs data for {seed}, gross weight (CEPII BACI). ")
            notes.append(f"The oil and the meal are two more customs groups, each its own code, gross weight, in none of the totals of another: {oil}, and {meal}. "
                         + ("Safflower oil is in the oil code with sunflower oil and customs data do not separate them; the USDA oil table is sunflower oil only."
                            if sun else "Mustard oil is in the oil code with rapeseed and canola oil and customs data do not separate them; the USDA oil table is rapeseed oil only."))
            notes.append(_note_group(baci, go, ("Sunflower and safflower oil" if sun else "Rapeseed, canola and mustard oil") + (" (HS 151211, 151219)" if sun else " (HS 151410, 151490)")))
            notes.append(_note_group(baci, gm, ("Sunflower meal" if sun else "Rapeseed meal") + (" (HS 230630)" if sun else " (HS 230640)")))
            notes.append("Production and domestic use of the oil and the meal are USDA PSD tables of marketing years (the Oil and Meal commodities of the file), shown under the seed's; "
                         "the world balance (area, stocks) is the seed's. Customs tonnage of the oil and the meal is a calendar year, so the two sources differ in year and basis.")
            notes.append("The price series is the oil's, not the seed's or the meal's: the Pink Sheet gives "
                         + ("sunflower oil" if sun else "rapeseed oil") + " only; there is no free series for the seed or the meal.")
            see.append({"k": "rapeseed" if sun else "sunflower", "text": "the " + ("rapeseed and canola seed, oil and meal" if sun else "sunflower seed, oil and meal")})
        elif cid == "pulses":
            notes.append("Trade is the dried leguminous vegetables of HS 0713, shelled, customs gross weight: peas (HS 071310), chickpeas (HS 071320), beans (HS 071331 to 071339 and the broad "
                         "and horse beans of HS 071350), lentils (HS 071340) and the other pulses of HS 071390 (pigeon peas and every pulse the code does not name). Each pair of the main "
                         "tables is split between the kinds in proportion to the six-digit rows of the same pair (CEPII BACI). The kinds exist from 2019, the first year of those rows, "
                         "and the tables of each kind show the latest year only; they follow the main tables.")
            notes.append("No production table: the USDA PSD file has no pulses, and no other file loaded by the atlas gives the production of dried pulses.")
        elif cid == "ferrous-scrap":
            notes.append("Trade is HS 7204, the whole heading of ferrous waste and scrap, customs gross weight: cast iron (HS 720410), stainless steel (HS 720421), other alloy steel (HS 720429), "
                         "tinned iron or steel (HS 720430), turnings, shavings and the like (HS 720441), remelting scrap ingots (HS 720450) and the scrap that no other code names (HS 720449). "
                         "The grades are not told apart in the tables. Scrap of the other metals and the granules and powders of HS 7205 are not loaded; the steel page leaves out HS 7201 to 7205 too.")
            notes.append("No production table: USGS gives ferrous scrap for the United States only (the block below), and no other free file loaded by the atlas gives the "
                         "scrap generated or consumed by country. The industry's yearly reviews of scrap trade and use are not loaded (their terms are not settled).")
            notes.append("Price: the World Bank Pink Sheet has no ferrous scrap series. The only price on the page is the USGS annual average of No. 1 heavy melting scrap, delivered, "
                         "a United States composite price and one grade of the scrap the tables count; no monthly series was loaded.")
            see.append({"k": "steel", "text": "steel products, and the steel production that scrap feeds"})
            see.append({"k": "pig-iron", "text": "pig iron and direct-reduced iron, the other iron units of the steel industry"})
        elif cid == "pig-iron":
            notes.append("Trade is pig iron (HS 7201: non-alloy pig iron in two classes of phosphorus content, alloy pig iron and spiegeleisen), customs gross weight. USGS production is pig iron "
                         "by country in Mt, as USGS states it (the countries it names and its 'Other countries' line).")
            notes.append("The tables for direct-reduced iron (HS 7203: iron ore reduced in lumps, pellets or similar forms, with the spongy ferrous products and iron of 99.94% purity or more) are a second "
                         "product with its own customs code, in none of the totals above. No production table for it: direct-reduced iron by country has no source that the atlas may reproduce. USGS gives pig iron and raw steel "
                         "only; the World Steel Association publishes it by country, but its terms of use do not allow its tables to be reproduced without written consent, and Midrex's "
                         "statistics book states no terms of reuse, so neither is copied.")
            notes.append(_note_group(baci, "dri", "Direct-reduced iron and spongy iron (HS 7203)"))
            notes.append("Nickel pig iron has no code of its own: it is declared as ferro-nickel (HS 720260), which is on the nickel page.")
            notes.append("No free price series: the World Bank Pink Sheet, the only price file the atlas loads, has none for pig iron or direct-reduced iron, and no other free one was loaded.")
            see.append({"k": "steel", "text": "steel products"})
            see.append({"k": "ferrous-scrap", "text": "ferrous scrap, the other raw material of the furnaces"})
            see.append({"k": "iron-ore", "text": "iron ore, which pig iron and direct-reduced iron are made from"})
        elif cid == "chromium":
            notes.append("Trade is chromium ores and concentrates (HS 2610), customs gross weight, the chromite of the steel and chemical industries. USGS mine production is in the same gross weight "
                         "(thousand metric tons in the file, shown in Mt); USGS reserves are in Cr2O3 content, not in ore: USGS also gives reserves in ore, but for 2024, an earlier year than the rest of "
                         "the table, and the page does not show them.")
            notes.append("Ferro-chromium (HS 720241, 720249) and ferro-silico-chromium are alloys of the ferro-alloys page, not of this one; chromium metal and chromium chemicals are not loaded.")
            notes.append("Price: the World Bank Pink Sheet has no chromium series. The only price on the page is the USGS annual average of chromite ore, gross weight "
                         "(United States salient statistics); no monthly series was loaded.")
            see.append({"k": "ferro-alloys", "text": "ferro-chromium, the alloy that most chromite is smelted into"})
        elif cid == "ferro-alloys":
            tot = sum(sum(baci.totals(g2, "exports").values()) for g2 in ["ferro-chromium"] + [x[0] for x in EXTRA_GROUPS[cid]])
            notes.append(f"Trade is the ferro-alloys of HS 7202 other than ferro-nickel, customs gross weight, by alloy, {_nf(tot)} Mt of exports in {BACI_YEAR} in all. The page opens on "
                         "ferro-chromium, the largest alloy, and its key figure is that alloy's; ferro-manganese, silico-manganese, ferro-silicon and the other ferro-alloys together "
                         "follow as tables of their own. The tables are not added to each other in any total of the page, and the figures are the weight of the alloy, not of the metal it holds.")
            for g2, _, _, what2 in [("ferro-chromium", None, None, TRADE[cid][2])] + EXTRA_GROUPS[cid]:
                notes.append(_note_group(baci, g2, what2[0].upper() + what2[1:]))
            notes.append("Ferro-nickel and nickel pig iron (HS 720260) are on the nickel page, where their group already was: no tonne is counted twice. The steel page leaves out HS 7201 to 7205.")
            notes.append("No production table: USGS has no world table of the ferro-alloys. Price: the World Bank Pink Sheet has none for them. The only prices on the page are the USGS "
                         "annual averages of ferro-chromium, per pound of chromium content, and of 75% ferrosilicon, in US cents per pound of silicon (United States salient statistics); "
                         "no price series for the other alloys was loaded.")
            see.append({"k": "nickel", "text": "ferro-nickel and nickel pig iron (HS 720260)"})
            see.append({"k": "chromium", "text": "chromium ore, the raw material of ferro-chromium"})
            see.append({"k": "manganese", "text": "manganese ore, the raw material of ferro-manganese and silico-manganese"})
        elif cid in ("molybdenum", "graphite"):
            ex = d["exports"]
            notes.append(f"No lanes: the atlas shows the customs trade of this product as tables only ({_nf(ex['world'])} {ex['u']} of exports in {BACI_YEAR}).")
            if cid == "molybdenum":
                notes.append("Trade is molybdenum ores and concentrates, roasted (HS 261310) and not roasted (HS 261390), customs gross weight (kt): the tonnes of concentrate, not of the "
                             "molybdenum in it, which is what USGS production and reserves count (kt Mo). Molybdenum oxides, ferro-molybdenum (in the ferro-alloys page) and the metal are not loaded.")
                see.append({"k": "ferro-alloys", "text": "ferro-molybdenum, in the group of the other ferro-alloys"})
            else:
                notes.append("Trade is natural graphite, in powder or flakes (HS 250410) and in other forms (HS 250490), customs gross weight (kt). USGS production and reserves are "
                             "natural graphite as USGS states it, in the file's metric tons (shown in kt). Artificial graphite and graphite articles are not loaded.")
            notes.append("Price: the World Bank Pink Sheet has none for " + ("molybdenum. The only price on the page is the USGS annual average price of US molybdic oxide (MoO3, 57% molybdenum content), "
                                                                          "in dollars per kilogram: the file does not say whether the kilogram is of the oxide or of the molybdenum in it. The oxide is "
                                                                          "a product made from the concentrates of the tables, not their own price." if cid == "molybdenum" else
                                                                          "graphite. The only prices on the page are the USGS annual average import unit values of three kinds of natural graphite (flake, "
                                                                          "lump and chip, amorphous), United States imports.") + " No monthly series was loaded.")

        for g2, what2 in ([(TRADE[cid][0], TRADE[cid][2])] if cid in TRADE else []) + [(x[0], x[3]) for x in EXTRA_GROUPS.get(cid, [])] + HAND_GROUPS.get(cid, []):
            gap = _gap_note(baci, g2, what2)
            if gap:
                notes.append(gap)
        if cid in BASIS:
            pb, tb = BASIS[cid]
            for sec in ("production", "reserves"):
                set_basis(d.get(sec), pb)
            for sec in ("exports", "imports"):
                set_basis(d.get(sec), tb)
            for x in d.get("extra") or []:
                set_basis(x["table"], EXTRA_BASIS.get(x["key"].split("-")[0]))
            # nutrient tonnes next to product tonnes: the unit is in every title and KPI of the page
            if cid == "urea":
                name_it(d, "production", "Ammonia producers — Mt of nitrogen (ammonia plant output)", "Ammonia production (Mt N)")
                name_it(d, "exports", "Top exporters — Mt of urea, product weight", "World exports (Mt of urea)")
                name_it(d, "imports", "Top importers — Mt of urea, product weight")
            elif cid == "phosphate":
                name_it(d, "exports", "Top exporters — Mt of phosphate rock, gross weight", "World exports (Mt of phosphate rock)")
                name_it(d, "imports", "Top importers — Mt of phosphate rock, gross weight")
            elif cid == "sulphur":
                name_it(d, "production", "Top producers — Mt of sulphur content, all forms", "World production (Mt S)")
                name_it(d, "exports", "Top exporters — Mt of sulphur, gross weight", "World exports (Mt of sulphur)")
                name_it(d, "imports", "Top importers — Mt of sulphur, gross weight")
            elif cid == "npk":
                name_it(d, "exports", "Top exporters — Mt of NPK fertilisers (three nutrients, HS 310520), product weight", "World exports (Mt of NPK)")
                name_it(d, "imports", "Top importers — Mt of NPK fertilisers (three nutrients, HS 310520), product weight")
            elif cid == "ferrous-scrap":
                name_it(d, "exports", "Top exporters — Mt of ferrous scrap, gross weight", "World exports (Mt of scrap)")
                name_it(d, "imports", "Top importers — Mt of ferrous scrap, gross weight")
            elif cid == "pig-iron":
                name_it(d, "production", "Top producers — Mt of pig iron", "World production (Mt of pig iron)")
                name_it(d, "exports", "Top exporters — Mt of pig iron, gross weight", "World exports (Mt of pig iron)")
                name_it(d, "imports", "Top importers — Mt of pig iron, gross weight")
            elif cid == "chromium":
                set_basis(d["reserves"], "Cr2O3 content")
                name_it(d, "production", "Top producers — Mt of chromite ore, gross weight", "World production (Mt of ore)")
                name_it(d, "reserves", "Reserves — Mt of Cr2O3 content", "World reserves (Mt Cr2O3)")
                name_it(d, "exports", "Top exporters — Mt of chromium ore, gross weight", "World exports (Mt of ore)")
                name_it(d, "imports", "Top importers — Mt of chromium ore, gross weight")
            elif cid == "ferro-alloys":
                name_it(d, "exports", "Top exporters — Mt of ferro-chromium, gross weight", "World exports (Mt of ferro-chromium)")
                name_it(d, "imports", "Top importers — Mt of ferro-chromium, gross weight")
            elif cid in ("molybdenum", "graphite"):
                what = "contained molybdenum" if cid == "molybdenum" else "natural graphite"
                name_it(d, "production", f"Top producers — kt of {what}", f"World production (kt of {what})")
                name_it(d, "reserves", f"Reserves — kt of {what}", f"World reserves (kt of {what})")
                ore = "molybdenum ores and concentrates" if cid == "molybdenum" else "natural graphite"
                name_it(d, "exports", f"Top exporters — kt of {ore}, gross weight", f"World exports (kt of {ore})")
                name_it(d, "imports", f"Top importers — kt of {ore}, gross weight")
            elif cid == "potash":
                set_basis(d["reserves"], "K2O content")
                name_it(d, "production", "Top producers — Mt of potassium chloride equivalent (Atlas conversion)", "World production (Mt KCl equivalent)")
                name_it(d, "reserves", "Reserves — Mt of K2O content", "World reserves (Mt K2O)")
                name_it(d, "exports", "Top exporters — Mt of potassium chloride, product weight", "World exports (Mt of KCl)")
                name_it(d, "imports", "Top importers — Mt of potassium chloride, product weight")

        notes = [n for n in notes if n]
        if notes:
            d["notes"] = notes
        if see:
            d["see"] = see
        if disc:
            d["discrepancies"] = disc
        docs[cid] = d

    check_unknown()

    # ------------------------------------------------------------ editorial caveats (from the data audit)
    annotate(docs, eia)
    registry_caveats(docs, baci)
    no_production_notes(docs, baci)
    landlocked_centre_notes(docs, baci)
    transit_port_notes(docs, baci)
    metal_row_notes(docs, baci)
    print("metals:", MET.metal_pages(sys.modules[__name__], docs, us, baci, index))
    # a country profile row carries the short caveat (`caveatShort`), the commodity page the long one (`caveat`) (GW3.7)
    for sec, short in (("exports", "Customs tonnage: the order is not a world ranking (see the LNG page)."),
                       ("imports", "Customs tonnage, which can miss LNG that an importer receives (see the LNG page).")):
        if docs["lng"].get(sec, {}).get("caveat"):
            docs["lng"][sec]["caveatShort"] = short

    # ------------------------------------------------------------ series by country and year
    known = {k: set(v) for k, v in UNKNOWN.items()}
    QUIET[0] = True
    try:
        hist_qa, hist_bad = HI.write_all(docs, os.path.join(OUT, "history"), name=cname)
    finally:
        QUIET[0] = False
    for bad in hist_bad:
        warn(f"history: the latest year of the series differs from the table: {bad}")
    gone = {k: sorted(v - known.get(k, set())) for k, v in UNKNOWN.items() if v - known.get(k, set())}
    for k, v in gone.items():  # codes of earlier years that are not countries of the index: in the world total, not in a series
        hist_qa.append(f"Codes of earlier years without a country of the index ({k}), counted in the world total only: {', '.join(v)}.")
    print("history:", hist_qa[0])

    # ------------------------------------------------------------ monthly series of the energy pages (loaded on demand by the page)
    # a failure here (EIA renamed or dropped a series: monthly.py raises on it by design) must not stop the commodity pages: the monthly files
    # keep their previous content (write_all writes nothing unless every file was built) and the run ends with MONTHLY_FAILED
    monthly_error = None
    try:
        for line in MO.write_all(os.path.join(RAW, "eia", "INTL.txt"), os.path.join(OUT, "monthly"), eia_country):
            print(line)
    except Exception as e:  # noqa: BLE001
        monthly_error = f"{e.__class__.__name__}: {e}"[:300]
        warn(f"monthly series NOT rebuilt, the files of data/commodities/monthly keep their previous content: {monthly_error}")

    # what the monthly series of an energy page lack is said in the Notes of the page (the monthly file keeps the same list); read from the
    # files written, so the notes follow the monthly series the page shows even when this run could not rebuild them
    for cid, d in docs.items():
        mf = os.path.join(OUT, "monthly", cid + ".json")
        if os.path.exists(mf):
            with open(mf, encoding="utf-8") as f:
                gaps = json.load(f).get("gaps") or []
            if gaps:
                d["notes"] = (d.get("notes") or []) + gaps

    # ------------------------------------------------------------ write
    HAS = ["production", "reserves", "consumption", "exports", "imports", "flows"]
    for e in index:
        d = docs[e["id"]]
        for k in ("production", "reserves", "consumption", "exports", "imports", "flows"):
            if k in d and not d[k]:
                raise SystemExit(f"{e['id']}: empty {k}")
        for t in [d[k] for k in ("production", "refinery", "reserves", "consumption", "exports", "imports") if isinstance(d.get(k), dict)] + [x["table"] for x in d.get("extra") or []]:
            for k in [k for k in t if k.startswith("_")]:  # the recipes of the series (history.py) are not published
                del t[k]
        mine = [k for k in HAS if k in d]
        e["has"] = mine + [h for h in e.get("has", []) if h not in HAS]
        if e["id"] in INDEX_SUB:
            e["sub"] = INDEX_SUB[e["id"]]
        # field order
        order = ["id", "summary", "kpis", "labels", "production", "refinery", "reserves", "consumption", "exports", "imports", "extra", "balance", "gaps", "flows", "flowDefs", "us", "concentration", "see", "notes", "discrepancies"]
        dd = {k: d[k] for k in order if k in d}
        with open(os.path.join(OUT, e["id"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(dd, f, indent=1, ensure_ascii=False)
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1, ensure_ascii=False)
    update_sources()
    write_qa(index, docs, baci, hist_qa)
    print("wrote", len(docs), "commodity files")
    if monthly_error:
        print(f"!! MONTHLY SERIES NOT REBUILT ({monthly_error}): data/commodities/monthly is the previous build; exit status {MONTHLY_FAILED}", file=sys.stderr)
        return MONTHLY_FAILED


def eia_country(code):
    """ISO3 of an EIA geography code that is a country of the index, else None (a region, a dissolved state or a territory
    without a polygon: the monthly series carry a few more of these than the annual ones, which check_unknown reports)."""
    if code in EIA_SKIP or EIA_SKIP_RE.match(code):
        return None
    iso = EIA_OVERRIDE.get(code, code)
    return iso if iso in ISO_SET else None


def _iso_to_eia(iso):
    return "XKS" if iso == "KOS" else iso


def _price_end(sid):
    """The last month of a price series as the atlas published it ("August 2020"), from data/prices/index.json, or None."""
    try:
        with open(os.path.join(DATA, "prices", "index.json"), encoding="utf-8") as f:
            m = next((x for x in json.load(f) if x["id"] == sid), None)
    except (OSError, ValueError):
        return None
    return f"{MONTHS[int(m['end'][5:7]) - 1]} {m['end'][:4]}" if m else None


def _price_span(sid):
    """(first year, last year) of a price series as the atlas published it, from data/prices/index.json, or None."""
    try:
        with open(os.path.join(DATA, "prices", "index.json"), encoding="utf-8") as f:
            m = next((x for x in json.load(f) if x["id"] == sid), None)
    except (OSError, ValueError):
        return None
    return (m["start"][:4], m["end"][:4]) if m else None


COVERAGE_MIN = 0.97  # a page says how much the customs file holds that its tables do not, below this share of the file's total
GROUP_TOTALS = os.path.join(CACHE, "baci_group_totals.csv")  # pipeline/trade/extract_baci.py: the file's totals before its 1,000 t / USD 1 million threshold


def _gap_note(baci, g, label):
    """For a group whose tables hold under COVERAGE_MIN of the customs file's total in the latest year: the two figures and where the difference comes from
    (review GNC3.6). The extract keeps only the pairs of 1,000 t or USD 1 million and more, and the tables are the cleaned frame (tonnage re-estimated from
    value, flows left out), so a product traded in many small flows has tables smaller than its file. None when the totals file is missing or the group is covered."""
    try:
        tot = pd.read_csv(GROUP_TOTALS)
    except OSError:
        return None
    r = tot[(tot["group"] == g) & (tot["year"] == BACI_YEAR)]
    if r.empty or not r["t"].iloc[0] > 0:
        return None
    file_mt, kept_mt = r["t"].iloc[0] / 1e6, r["t_kept"].iloc[0] / 1e6
    pairs, kept = int(r["pairs"].iloc[0]), int(r["kept"].iloc[0])
    held = sum(baci.totals(g, "exports").values())
    if held >= COVERAGE_MIN * file_mt:
        return None
    parts = [f"{_nf(file_mt - kept_mt)} Mt are pairs under the threshold of the extract (1,000 t and USD 1 million; {kept:,} of the {pairs:,} pairs of the file are kept)"]
    # rows that rule 5 of clean() drops as misclassified are named apart (the coke exports of Mozambique, FNCF): they are in the file and in no table
    out = [r for r in baci.dropped if r["rule"] == "misclassified" and r["group"] == g and r["year"] == BACI_YEAR]
    out_mt = sum(r["t"] for r in out) / 1e6
    if out_mt >= 0.005 * file_mt:
        who = " and ".join(cname(c) for c in sorted({r["o"] for r in out}))
        parts.append(f"{_nf(out_mt)} Mt are the exports of {who}, left out as a misclassification (rule 5 of the cleaning rules: {out[0]['reason']})")
    else:
        out_mt = 0.0
    rest = kept_mt - out_mt - held
    if abs(rest) >= 0.005 * file_mt:
        what = f"{_nf(abs(rest))} Mt are {'taken out' if rest > 0 else 'added'} by the cleaning rules (tonnage re-estimated from value, or flows left out)"
        # a single row that holds most of it is named (unwrought zinc, Spain to Mexico: 5 Mt reported for USD 61 million)
        x = baci.group(g)
        cut = (x["t0"].fillna(x["t"]) - x["t"]).clip(lower=0) if rest > 0 else None
        if cut is not None and len(x) and cut.max() >= 0.5 * rest * 1e6:
            r = x.loc[cut.idxmax()]
            what += f"; most of it is one row, {cname(r['o'])} to {cname(r['d'])}: {_nf(r['t0'] / 1e6)} Mt reported for USD {r['usd'] / 1e3:,.0f} million, {_nf(r['t'] / 1e6)} Mt after the rule"
        parts.append(what)
    return (f"{label[:1].upper()}{label[1:]}: the tables hold {_nf(held)} Mt, {held / file_mt:.0%} of the {_nf(file_mt)} Mt that the customs file records for these "
            f"codes in {BACI_YEAR} (gross weight). The difference: " + "; ".join(parts) + ".")


def _left_out_note(baci, g):
    """What clean() leaves out of a group as a misclassification (rule 5, the DROP table), in the words of the page that shows the group: who, how
    much in the customs file of the latest year, in which years, why, and that the rows are not counted. None when nothing is left out. For coke the
    EIA series that the K14 check reads is quoted with its years, with the series of the coke exports and with the metallurgical coal exports of the
    last year of the country, from the file (FNCF, FNCI). The rows are out of the coke tables, lanes, passage estimates, history and totals of the
    commodity pages and of the commodity blocks of the country pages; the all-goods list of a country page, which is the customs value by heading of
    the unfiltered file, still shows the heading as declared, and the note says so."""
    rows = [r for r in baci.dropped if r["rule"] == "misclassified" and r["group"] == g]
    if not rows:
        return None
    out = []
    for o in sorted({r["o"] for r in rows}):
        mine = [r for r in rows if r["o"] == o]
        latest = [r for r in mine if r["year"] == BACI_YEAR]
        years = sorted({r["year"] for r in mine})
        s = f"{cname(o)}'s exports under this code are left out of the coke tables, lanes, passage estimates, history and totals of the commodity pages and of the commodity blocks of the country pages, in each of the {len(years)} years {years[0]} to {years[-1]} in which the customs file records them"
        if latest:
            s += f" ({_nf(sum(r['t'] for r in latest) / 1e6)} Mt in {BACI_YEAR}, {len({r['d'] for r in latest})} destinations)"
        s += f": {mine[0]['reason']}"
        if g == "coke":
            eia = K._eia_k14()
            ser = ((eia or {}).get(K.NO_PRODUCTION[g][0]) or {}).get(o)
            coal = ((eia or {}).get(K.NO_PRODUCTION[g][2]) or {}).get(o)
            xser = ((eia or {}).get(K.NO_PRODUCTION[g][3]) or {}).get(o)
            if ser and not any(v > 0 for v in ser.values()):
                s += f" (EIA International Energy Data: its coke production series reads 0 in every year from {min(ser)} to {max(ser)}"
                if xser:
                    # the series of the coke exports (21-4) is not the production series (21-1): it can read above 0 where production reads 0
                    up = sorted(y for y, v in xser.items() if v > 0)
                    if not up:
                        s += f" (its coke export series reads 0 in every year from {min(xser)} to {max(xser)} too)"
                    elif len(up) <= 3:
                        s += f" (its coke export series reads {', '.join(f'{xser[y]:,.0f} kt in {y}' for y in up)} and 0 in the other years)"
                    else:
                        s += f" (its coke export series is above 0 in {len(up)} years, last {xser[up[-1]]:,.0f} kt in {up[-1]})"
                if coal and coal[max(coal)] > 0:
                    s += f"; the same file gives it {coal[max(coal)] / 1e3:.3g} Mt of metallurgical coal exports in {max(coal)}"
                s += ")"
            s += f". The all-goods list of the country page of {cname(o)} shows the customs value of heading 2704 as declared"
        out.append(s + ". These rows are not counted: the tables and totals of this group are the customs file less them.")
    return " ".join(out)


def _note_group(baci, g, label):
    ex = baci.totals(g, "exports")
    top = sorted(ex.items(), key=lambda kv: -kv[1])[:3]
    world = sum(ex.values())
    unit_n = "Mt"
    names = ", ".join(f"{cname(baci.iso(c))} {v:.2f} Mt" for c, v in top)
    grp = baci.group(g)
    added = grp[grp["flag"] == "added"]  # flows the atlas takes from the importer's declaration (rule 11 of clean.py)
    src = "CEPII BACI" + "".join(f", with {cname(baci.iso(r.o))} to {cname(baci.iso(r.d))} from UN Comtrade" for r in added.itertuples())
    return (f"{label}, {BACI_YEAR} ({src}): world {world:.2f} Mt gross weight; top exporters {names}.")


def _compare(kind, eia, key, factor, baci, group, div, unit, label, year, tol=0.10):
    """Compare EIA country values with BACI for the same year; return discrepancy lines."""
    bt = baci.totals(group, kind)
    top = sorted(bt.items(), key=lambda kv: -kv[1])[:3]
    out = []
    for code, bv in top:
        iso = baci.iso(code)
        ev = eia.s[key].get(_iso_to_eia(iso), {}).get(year)
        if ev is None:
            continue
        ev *= factor
        if bv > 0 and abs(ev / bv - 1) > tol:
            out.append(f"{iso} {kind} {year}: BACI {bv:.1f} {unit} vs {label} {ev:.1f} {unit} ({(ev / bv - 1) * 100:+.0f}%); table uses BACI (customs tonnage, all coal incl. coking).")
    return out


def thai_stocks_note(psd, t):
    """Thailand holds the largest sugar stock in the USDA file, more than its production of the same year (audit M-025): a neutral note
    with the two figures of each of the two years, no explanation. Written only where the file shows stocks above production."""
    row = next((r for r in t["rows"] if r["c"] == "THA"), None)
    if not row:
        return
    got = []
    for my in (PSD_MY, PSD_EST):
        p = psd.at(my)
        es, pr = p._sum("Sugar, Centrifugal", "Ending Stocks", "Thailand"), p._sum("Sugar, Centrifugal", "Production", "Thailand")
        if es is None or pr is None:
            return
        got.append((p.label, es / 1000, pr / 1000))
    if not any(es > pr for _, es, pr in got):
        return
    text = "; ".join(f"{lab}: ending stocks {_nf(es)} Mt, production {_nf(pr)} Mt" for lab, es, pr in got)
    text = f"Thailand, as USDA PSD gives it ({text})"
    row["n"] = text
    t["n"] = joinn(t["n"], text)


def _psd_vs_baci(psd_obj, baci, cid, com, ex_attr, group):
    """Compare the PSD estimate year (PSD_EST, the latest complete one) with BACI 2024 at the world level."""
    out = []
    unit, conv, rows, world = psd_obj.at(PSD_EST).table(com, ex_attr)
    div = {"kt": 1e3, "Mt": 1e6}[unit]
    bw = baci.group(group)["t"].sum() / div
    if bw and abs(world / bw - 1) > 0.15:
        eu = psd_obj.has_eu(com)
        out.append(f"World exports: USDA PSD {PSD_EST_LABEL} {world:.1f} {unit} (sum of reporting countries{', EU excl. intra-trade' if eu else ''}) vs BACI {BACI_YEAR} {bw:.1f} {unit} "
                   f"({(world / bw - 1) * 100:+.0f}%); different year and basis (marketing year vs calendar year{'; BACI includes intra-EU trade, PSD does not' if eu else ''}); the tables show USDA PSD.")
    return out


def _prec_disc(d, cid):
    ex, pr = d["exports"], d["production"]
    what = "World exports in fine-metal equivalent (Atlas estimate from customs values)" if ex["s"] == "atlas" else "BACI world exports"
    return (f"{what} {ex['world']:,.0f} {ex['u']} ({BACI_YEAR}) are {ex['world'] / pr['world']:.1f}x USGS world mine production "
            f"{pr['world']:,.0f} {pr['u']} ({pr['y']}): customs trade can count refined or recycled metal, and metal re-exported from one country to another, more than once, so it is not "
            "comparable with mine output (the atlas does not measure how much); USGS is used for production, BACI for trade.")


# Precious metals (audit C-035): customs tonnage is the gross weight of dore, alloys and the base metal in them, so the trade
# tables are in fine-metal equivalent, the declared value divided by the year's average price of the metal. id -> (price
# series of data/prices, metal named in the notes)
FINE_PRICE = {"gold": ("gold-m", "gold"), "silver": ("silver-m", "silver"), "pgm": ("platinum-m", "platinum")}


def _name_it(d, key, title=None, kpi=None):
    """Section title / KPI label of a commodity page (the same as name_it() of main())."""
    if title:
        d.setdefault("labels", {})[key] = title
    if kpi:
        d.setdefault("kpis", {})[key] = kpi


def _fine_metal(d, baci, cid, disc):
    """Replace the trade tables, the flows and the exports figure of a precious metal by fine-metal equivalents (an Atlas
    estimate, never above the customs gross weight, which stays in the notes). False when the price is missing."""
    g, (u, div), what = TRADE[cid]
    series, metal = FINE_PRICE[cid]
    price = CV.annual_price(series, BACI_YEAR)
    if not price:
        warn(f"{cid}: no {BACI_YEAR} price in data/prices/{series}.json; trade left in customs gross weight")
        return False
    per_t = price * 1e6 / CN.GRAMS_PER_TROY_OZ  # USD per tonne
    x = baci.group(g).copy()
    fine = x["usd"] * 1000 / per_t
    # gross weight as declared; where it is missing or implausible (rule 2 or 3 of clean.py), the atlas's estimate from value
    gross = x["t"].where(~x["imputed"])
    capped = gross.notna() & (fine > gross)
    x["t0"], x["t"] = x["t"], fine.where(~capped, gross)
    how = (f"declared value divided by {price:,.0f} USD per troy ounce, the {BACI_YEAR} average {metal} price (World Bank Pink Sheet), "
           f"i.e. {per_t / 1e6:.1f} million USD per tonne at {CN.GRAMS_PER_TROY_OZ} g per troy ounce")

    def usd(k):
        v = k * 1000
        return f"USD {v / 1e9:.2f} bn" if v >= 1e9 else f"USD {v / 1e6:,.1f} million"

    x["enote"] = [f"Atlas estimate: fine-metal equivalent, {usd(v)} of {how}; "
                  + (f"customs gross weight {_fmt(t0 / div)} {u}" if not im else "gross weight missing or implausible in customs data")
                  + ("; capped at the customs gross weight" if cp else "") for v, t0, im, cp in zip(x["usd"], x["t0"], x["imputed"], capped)]
    fg = g + "-fine"
    x["group"], x["imputed"], x["est"], x["susp"], x["t_susp"], x["flag"] = fg, True, True, False, 0.0, "est-fine"
    x["capped"] = capped  # the flow's figure is the cap, the customs gross weight: the page prints it as it is (GR4S.12)
    x["t_est"] = x["t"]
    baci.df = pd.concat([baci.df[baci.df["group"] != fg], x], ignore_index=True)
    world_gross = x["t0"].sum() / div
    n = (f"Atlas estimate: fine-metal equivalent of every flow of {what} in CEPII BACI HS92, {BACI_YEAR}, all transport modes: {how}; "
         f"never above the customs gross weight, which each row's note gives (world: {_fmt(world_gross)} {u} gross weight); "
         "values rounded")
    if cid == "pgm":
        n += ("; valued at the platinum price, as palladium, rhodium and the other platinum-group metals have prices of their own that "
              "are not in the loaded sources: a flow rich in them is overstated or understated")
    for side, col in (("exports", "o"), ("imports", "d")):
        agg = x.groupby(col).agg(t=("t", "sum"), t0=("t0", "sum")).sort_values("t", ascending=False)
        rows = [(None if c in EXTRA_CODES else baci.iso(c), r["t"] / div, f"customs gross weight {_fmt(r['t0'] / div)} {u}")
                for c, r in agg.iterrows()]
        d[side] = ranked(rows, BACI_YEAR, "atlas", u, world=x["t"].sum() / div, n=n, digits=3)  # an estimate: three significant digits
        # the declared value of each country is a customs figure, not an estimate (metals.add_values shows it; no unit value for an estimated tonnage)
        d[side]["_usd"] = {baci.iso(c): float(v) for c, v in x.groupby(col)["usd"].sum().items() if c not in EXTRA_CODES and baci.iso(c)}
        d[side]["_usdw"] = float(x["usd"].sum())
        _name_it(d, side, f"Top {side[:-1]}ers — fine-metal equivalent (Atlas estimate)")
    for m in baci.last_susp:  # the discrepancies of the gross-weight flows replaced below
        if m in disc:
            disc.remove(m)
    d["flows"] = baci.flows(fg, u, div)
    for f in d["flows"]:
        cv = baci.caveat_of(g, f["o"], f["d"])
        if cv and baci.caveats[cv]["text"] not in f.get("n", ""):
            f["n"] = joinn(f.get("n"), baci.caveats[cv]["text"])
    _name_it(d, "flows", f"Main flows — fine-metal equivalent (Atlas estimate), {BACI_YEAR}")
    d["summary"]["exports"] = {"v": sig(x["t"].sum() / div), "u": u, "y": BACI_YEAR, "s": "atlas", "est": True, "n": n}
    d["summary"]["exports"]["alt"] = {"v": rnd(world_gross), "u": f"{u} gross weight", "s": "baci", "y": BACI_YEAR,
                                      "n": "customs gross weight (CEPII BACI), estimated from value where it is missing or implausible"}
    _name_it(d, "exports", kpi="World exports (fine-metal equivalent)")
    return True


FINE_NOTE = ("Trade tables and flows are in fine-metal equivalent, an Atlas estimate: the declared value of each flow (CEPII BACI) divided by the "
             "year's average price of the metal (World Bank Pink Sheet), never above the customs gross weight. Customs gross weight counts dore, "
             "alloys and the base metal they contain, and some declared quantities are wrong; it is given in the note of each row and in brackets "
             "after the world exports figure.")


def _pgm(d, us, baci, notes, summ, seaborne, add_baci_trade, disc, cid):
    pt = us.table("Platinum", "Mine production: Platinum", factor=1e-3)
    pdl = us.table("Palladium", "Mine production: Palladium", factor=1e-3)
    ptd, pdd = dict(pt["rows"]), dict(pdl["rows"])
    rows = []
    for c in sorted(set(ptd) | set(pdd)):
        a, b = ptd.get(c, 0.0), pdd.get(c, 0.0)
        rows.append((c, a + b, f"platinum {rnd(a)} t + palladium {rnd(b)} t"))
    world = pt["world"] + pdl["world"]
    n = (f"USGS MCS {USGS_EDITION}, platinum plus palladium mine production, PGM content (kg converted to t); {USGS_YEAR} values are USGS estimates; "
         "world = sum of the USGS rounded world totals for platinum and palladium; excludes rhodium, ruthenium, iridium and osmium")
    if total_of(rows) + pt["other"] + pdl["other"] > world * 1.05:
        warn("pgm: country sum above world")
    d["production"] = ranked(rows, int(USGS_YEAR), "usgs-mcs", "t", world=world, n=n, other=pt["other"] + pdl["other"])
    res = us.table("Platinum-Group Metals", "PGM reserves", factor=1e-3)
    rn = f"USGS MCS {USGS_EDITION}, platinum-group metals reserves, PGM content (kg converted to t); USGS world total is rounded"
    if res["wnote"]:
        rn += "; " + res["wnote"]
    d["reserves"] = ranked(res["rows"], int(USGS_YEAR), "usgs-mcs", "t", world=res["world"] if res["world"] else total_of(res["rows"]) + res["other"], n=rn,
                         other=res["other"])
    g = add_baci_trade(d, cid, notes, disc)
    summ(d, "production", d["production"])
    summ(d, "reserves", d["reserves"])
    summ(d, "exports", d["exports"])
    seaborne(d, g)
    if _fine_metal(d, baci, cid, disc):
        notes.append(FINE_NOTE + " Platinum-group metals are valued at the platinum price, the only one of them in the loaded sources.")
    else:
        notes.append("Trade tonnage is customs gross weight (CEPII BACI): dore and alloys count with the base metal they contain; treat flows as indicative.")
    disc.append(_prec_disc(d, cid))
    notes.append("Production is platinum plus palladium only (USGS gives no rhodium/ruthenium/iridium/osmium by country); the index unit (kg) is shown here in t.")


# ====================================================================== sources, QA
# GIIGNL and IGU: the sentences of their reports that keep their country tables out of the atlas (read on 24 November 2026)
GIIGNL_LICENCE = ("Public PDF, (c) GIIGNL; one world total and the order the report gives are cited, with attribution, and none of its country tables is "
                  "copied. Page 2 of the report: \"Reproduction of the contents of this publication in any manner whatsoever is prohibited without prior "
                  "consent of the copyright owners.\"")
IGU_LICENCE = ("Copyright International Gas Union; one world total is cited, with attribution, and none of its tables is copied. Page 1 of the report: "
               "\"No part of this publication may be reproduced, stored in retrieval systems or transmitted in any form or by any means [...] without "
               "the prior permission of the copyright owner.\"")

# the Public-Use Statement is the permission the registry quotes (web/src/lib/licence.ts): the atlas publishes an estimate of its own made from the data
CENSUS_LICENCE = ("U.S. Census Bureau Public-Use Statement (own estimates from the data, with the Census Bureau cited as the source of the original data). "
                  "The statement, on \"Citing our Data, Tools, Technical Documents and Research\" (https://www.census.gov/about/policies/citation.html, "
                  "page last revised 24 February 2026), reads: \"Data users who create their own estimates using data from disseminated tables and other data "
                  "should cite the Census Bureau as the source of the original data only.\" and \"Conclusions drawn from any analysis of these data are the sole "
                  "responsibility of the performing party.\" The data-products page says that all international trade data products previously available by "
                  "subscription are now available to the public at no cost. No statement of copyright was found on the pages read (that page and \"Policies and "
                  "Notices\"). The site publishes no row of the Census file and offers none for download: it prints an estimate of its own made from the data and a few totals of the file by product and country (quantity, weight by vessel), each credited to the Census Bureau, and the repository keeps a small cache of those totals. Not endorsed or certified by the Census Bureau")
DISR_LICENCE = ("CC BY 4.0 (Creative Commons Attribution 4.0 International, as the About sheet of the workbook states); attribution as it asks: \"Department of "
                "Industry, Science, and Resources, Commonwealth of Australia Resources and Energy Quarterly, December 2025.\"")

QLD_COAL_LICENCE = ("CC BY 4.0 (Creative Commons Attribution 4.0, as the dataset page states); credit as the workbook's About sheet gives it: \"Source: Department of Natural "
                    "Resources and Mines, Manufacturing and Regional and Rural Development (NRMMRRD)\"; the sheet adds that the data may be revised and that derived "
                    "conclusions and analysis are not attributable to the Department")

# worldsteel: the clause that keeps its country tables out of the atlas (terms of use, full version, read on 24 November 2026)
WORLDSTEEL_LICENCE = ("Copyright World Steel Association; one world total is cited, with its edition, and none of its tables is copied. Article 6.1 of the "
                      "worldsteel Terms of Use: its websites and components \"may not be reproduced, used or distributed without the prior written consent "
                      "of worldsteel\"; for its data subscriptions: \"The data can be used internally but cannot be shared with a third party.\"; "
                      "World Steel in Figures 2026 states no licence and no attribution wording")


def update_sources():
    p = os.path.join(DATA, "sources.json")
    src = json.load(open(p, encoding="utf-8"))
    have = {s["id"] for s in src}
    new = [
        {"id": "eia-intl", "name": "EIA International Energy Data", "publisher": "U.S. Energy Information Administration",
         "url": "https://www.eia.gov/international/data/world", "licence": "Public domain (US Government)", "update": "annual, partial monthly"},
        {"id": "faostat", "name": "FAOSTAT Crops and livestock products (QCL)", "publisher": "Food and Agriculture Organization of the United Nations",
         "url": "https://www.fao.org/faostat/en/data/QCL", "licence": "CC BY 4.0", "update": "annual"},
        {"id": "faostat-rfb", "name": "FAOSTAT Fertilizers by Product (RFB)", "publisher": "Food and Agriculture Organization of the United Nations",
         "url": "https://www.fao.org/faostat/en/data/RFB", "licence": "CC BY 4.0 (FAO statistical database terms of use also apply)", "update": "annual",
         "access": "Bulk zip Inputs_FertilizersProduct_E_All_Data_(Normalized).zip, at most every 80 days (pipeline/commodities/fetch_external.py)",
         "use": "Urea production in tonnes of product; potassium chloride production as a check on the potash units"},
        {"id": "icco", "name": "ICCO Quarterly Bulletin of Cocoa Statistics (news pages)", "publisher": "International Cocoa Organization",
         "url": "https://www.icco.org/statistics/", "licence": "Copyright ICCO; only the world total of production is cited, with attribution, and none of its tables is copied (its country tables are sold by subscription)",
         "update": "quarterly", "access": "Web pages, read by hand", "use": "World cocoa production per crop year, beside the FAOSTAT table, and the world grindings of the latest crop year"},
        {"id": "wna", "name": "World Nuclear Association: World Uranium Mining Production", "publisher": "World Nuclear Association",
         "url": "https://world-nuclear.org/information-library/nuclear-fuel-cycle/mining-of-uranium/world-uranium-mining-production",
         "licence": "Copyright World Nuclear Association; figures cited with attribution (see website terms of use)", "update": "annual"},
        {"id": "worldsteel", "name": "worldsteel: World Steel in Figures and crude steel production press releases", "publisher": "World Steel Association",
         "url": "https://worldsteel.org/data/world-steel-in-figures/world-steel-in-figures-2026/", "licence": WORLDSTEEL_LICENCE,
         "update": "annual (World Steel in Figures, June); monthly (press releases)"},
        {"id": "wgc", "name": "World Gold Council: Gold Demand Trends", "publisher": "World Gold Council",
         "url": "https://www.gold.org/goldhub/research/gold-demand-trends", "licence": "Copyright World Gold Council; only the world total of mine production is cited, with attribution, and none of its tables is copied",
         "update": "quarterly"},
        {"id": "eia-ng", "name": "EIA Natural Gas data: liquefied U.S. natural gas exports", "publisher": "U.S. Energy Information Administration",
         "url": "https://www.eia.gov/opendata/bulk/NG.zip", "licence": "Public domain (US Government)", "update": "monthly, annual series",
         "access": "Bulk file NG.zip, series NG.N9133US2.A read by hand", "use": "United States LNG exports, as a check on the LNG tables"},
        {"id": "eia-cab-russia", "name": "EIA Country Analysis Brief: Russia", "publisher": "U.S. Energy Information Administration",
         "url": "https://www.eia.gov/international/analysis/country/RUS", "licence": "Public domain (US Government)", "update": "irregular (last updated 24 July 2025)",
         "access": "Web page, read by hand", "use": "Russia's petroleum product exports and their destinations, beside the customs figures"},
        {"id": "nrcan-units", "name": "Conversion factors and common units to be used for North American Cooperation on Energy Information",
         "publisher": "Natural Resources Canada", "url": UNITS_URL, "licence": "Government of Canada web content; a conversion factor is cited with attribution (reuse terms to be confirmed)",
         "update": "irregular (page dated 16 January 2025)", "access": "Web page, read by hand", "use": "Atlas conversion of LNG tonnes to cubic metres of gas"},
        {"id": "igu-lng-report-2026", "name": "IGU World LNG Report 2026 (2025 data)", "publisher": "International Gas Union",
         "url": "https://igu.org/igu-reports/2026-world-lng-report", "licence": IGU_LICENCE, "update": "annual (2026 edition posted 7 July 2026)",
         "access": "Web page and PDF, read by hand", "use": "World LNG trade in 2025 (437.0 Mt), beside the customs total of the LNG page"},
        {"id": "disr-req", "name": "Resources and Energy Quarterly, December 2025: principal markets for Australia's commodity exports (table 41)",
         "publisher": "Department of Industry, Science and Resources, Commonwealth of Australia",
         "url": "https://www.industry.gov.au/sites/default/files/2025-12/resources-and-energy-quarterly-december-2025-historical-data.xlsx",
         "licence": DISR_LICENCE,
         "update": "quarterly (the workbook of December 2025: calendar years to 2024)",
         "access": "Historical data workbook downloaded by hand (the site refuses scripted downloads); table 41 read by pipeline/trade/aus_req_lng.py into a small cache, never by a scheduled job",
         "use": "Australia's LNG exports in 2024 by principal market, beside the customs figures of the LNG page"},
        {"id": "comtrade", "name": "UN Comtrade (public preview): China's imports of tin ores and concentrates, HS 260900",
         "publisher": "United Nations Statistics Division, UN Comtrade", "url": "https://comtradeapi.un.org/public/v1/preview/C/A/HS",
         "licence": "UN Comtrade's policy on re-dissemination (https://uncomtrade.org/docs/re-dissemination-of-data/): permission is not required for the "
                    "\"Publication of limited amounts of UN Comtrade data in a few tables, graphs, visualization in printed or digital platform\"; attribution: "
                    "\"Source: UN Comtrade.\" The answers are not published as files",
         "update": "annual (one call per year)",
         "access": "Public preview endpoint, no key, one call per year, two minutes apart, by hand; the few figures the page prints are kept in "
                   "pipeline/cache/comtrade_tin_china.json, the answers stay in raw/ and are never fetched by a scheduled job",
         "use": "China's declared imports of tin ores and concentrates by origin (the tin page), and the flow Myanmar to China that CEPII BACI records at under 2 kt a year (the atlas's extract has no row for it in 2021, 2022 and 2024)"},
        {"id": "census-exports", "name": "US Census Bureau, USA Trade Online: export detail file (EXDB), December 2024",
         "publisher": "U.S. Census Bureau, Foreign Trade Division", "url": "https://www.census.gov/foreign-trade/data/dataproducts.html",
         "licence": CENSUS_LICENCE,
         "update": "monthly (the December file holds the calendar year)",
         "access": "EXDB2412.ZIP downloaded by hand; only the LPG codes are read, by pipeline/trade/us_lpg.py, into a small cache",
         "use": "Quantity and vessel shipping weight of United States LPG exports in 2024: the tonnage of the pair United States to Mexico and its share by sea"},
        {"id": "eia-exports-destination", "name": "EIA Exports by Destination: propane, normal butane and isobutane (annual, thousand barrels per day)",
         "publisher": "U.S. Energy Information Administration", "url": "https://www.eia.gov/dnav/pet/pet_move_expc_a_EPLLPA_EEX_mbblpd_a.htm",
         "licence": "Public domain (US Government)", "update": "annual (release of 30 October 2026)",
         "access": "Web pages read by hand, the history page of each series; a small cache holds the series of Mexico and Canada (pipeline/trade/us_lpg.py)",
         "use": "Volume of United States LPG exports to Mexico and Canada, 2004 to 2025, to date the break in the customs tonnage of the pair United States to Mexico"},
        {"id": "qld-coal-sales", "name": "Quarterly coal reports: Quarterly Coal Sales (Queensland coal exports by destination, by port and by coal type)",
         "publisher": "Queensland Government, Department of Natural Resources and Mines, Manufacturing and Regional and Rural Development",
         "url": "https://www.data.qld.gov.au/dataset/quarterly-coal-reports", "licence": QLD_COAL_LICENCE,
         "update": f"quarterly (the workbook read: {_lc(metcoal.meta('qld-coal-sales')['data_through'])}, {_lc(metcoal.meta('qld-coal-sales')['current_as_at'])})",
         "access": f"Workbook {metcoal.meta('qld-coal-sales')['file']['name']} downloaded by hand (the site refuses scripted downloads); read by pipeline/trade/extract_metcoal.py into small "
                   "tracked files in pipeline/cache, never by a scheduled job",
         "use": "Metallurgical coal (hard coking, semi-soft coking and PCI) sold to export by Queensland producers, by destination as the file gives it and by port, on the Metallurgical coal page"},
        {"id": "eia-coal", "name": "EIA Coal data: U.S. coal exports by rank, destination and customs district (bulk file COAL.zip)",
         "publisher": "U.S. Energy Information Administration",
         "url": "https://www.eia.gov/opendata/bulk/COAL.zip", "licence": "Public domain (US Government); acknowledgment: \"Source: U.S. Energy Information Administration\"",
         "update": f"quarterly and annual (the file read is dated {_iso_date(metcoal.meta('eia-coal')['file_date'])})",
         "access": "Bulk file COAL.zip downloaded by hand, series COAL.EXPORT_QTY read by pipeline/trade/extract_metcoal.py into small tracked files in pipeline/cache, "
                   "never by a scheduled job",
         "use": "Exports of metallurgical coal of the United States by destination and customs district, on the Metallurgical coal page"},
        {"id": "wilhelmsen-lpg-sizes", "name": "Wilhelmsen: LPG vessel management (size categories of LPG carriers)", "publisher": "Wilh. Wilhelmsen",
         "url": "https://wilhelmsen.com/ship-management/technical-management/lpg-vessel-management", "licence": "Public web page; a size band is cited with attribution (terms to be confirmed)",
         "update": "irregular", "access": "Web page, read by hand", "use": "Size band of the mid-size gas carrier class"},
    ]
    # fields of an existing entry that the builder corrects (the registry is otherwise only added to)
    fixes = {"faostat": {"use": "Cocoa production; production of wheat, maize, rice, soya beans, rape or colza seed and sugar beet of the 27 member states of the European Union",
                         "access": "Bulk zip Production_Crops_Livestock_E_All_Data_(Normalized).zip, one download at most every 80 days; the cocoa rows and the "
                                   "EU member-state crop rows are kept in pipeline/cache (pipeline/commodities/fetch_external.py --only crops)"},
             "icco": {"use": "World cocoa production per crop year, beside the FAOSTAT table, and the world grindings of the latest crop year",
                      "licence": "Copyright ICCO; only the world totals of production and of grindings are cited, with attribution, and none of its tables is copied (its country tables are sold by subscription)"},
             "worldsteel": {"name": "worldsteel: World Steel in Figures and crude steel production press releases",
                            "url": "https://worldsteel.org/data/world-steel-in-figures/world-steel-in-figures-2026/", "licence": WORLDSTEEL_LICENCE,
                            "update": "annual (World Steel in Figures, June); monthly (press releases)",
                            "use": "World crude steel production in 2025 (1,848.9 Mt, World Steel in Figures 2026), beside the USGS table of the steel page"},
             "giignl-2026": {"use": "World LNG trade in 2025 and 2024, the United States as the largest exporter, and LNG liquefaction and regasification capacities",
                             "licence": GIIGNL_LICENCE},
             "disr-req": {"licence": DISR_LICENCE},
             "census-exports": {"licence": CENSUS_LICENCE}}
    retired = {"igu-lng-report-2025": "the 2026 edition of the IGU report (igu-lng-report-2026) is the one the LNG page cites"}
    changed = False
    for s in new:
        if s["id"] not in have:
            src.append(s)
            changed = True
    if any(s["id"] in retired for s in src):
        src[:] = [s for s in src if s["id"] not in retired]
        changed = True
    # the two sources of the Metallurgical coal page are described from their meta files (the dates, the file name): a refreshed file changes the text
    built = {s["id"]: s for s in new if s["id"] in ("qld-coal-sales", "eia-coal")}
    for s in src:
        if s["id"] in built:
            fixes.setdefault(s["id"], {}).update({k: built[s["id"]][k] for k in ("update", "access", "use")})
        for k, v in fixes.get(s["id"], {}).items():
            if s.get(k) != v:
                s[k] = v
                changed = True
    if changed:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(src, f, indent=1, ensure_ascii=False)


def _fmt(v):
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    if abs(v) >= 10:
        return f"{v:.1f}"
    return f"{v:.2f}"


def _fmts(v, u, under=0.0):
    """`_fmt` with its unit, but a figure that two decimals would write "0.00" (a small row beside a large one) keeps three significant digits,
    in the smaller unit under 0.001 Mt: "0.00 Mt" is not a figure (GV6C.11). `under`: the same for every figure below it ("0.01 Mt" for 0.0102
    is 2% off, "0.02 Mt" for 0.0167 is 20%: the note of the mixed tonnage starts at 0.005 Mt; above 0.05 Mt, where it started before, it is written as before)."""
    if not v:
        return f"0 {u}"
    return _nfu(v, u) if round(v, 2) == 0 or abs(v) < under else f"{_fmt(v)} {u}"


def _pct1(x):
    """A share (0 to 1) with one decimal, "<0.1%" where it rounds to nothing: "0.0%" beside a non-zero figure reads as an error (GV6C.11)."""
    return "0%" if not x else f"{x:.1%}" if x >= 0.0005 else "<0.1%"


def _nf(v):
    """A figure of the source without invented decimals: 230, 1,823, 1.3. Never an exponent: .3g prints "7.3e-05" under 0.0001, so a
    figure under 0.001 is "under 0.001" (a caller that knows the unit uses _nfu, which prints it in the smaller unit)."""
    if v and abs(v) < 0.001:
        return "under 0.001"
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.3g}"


def _nfu(v, u):
    """_nf with its unit; a small figure in Mt or kt moves to the smaller unit (0.000073 Mt is 73 t), a figure of another unit keeps it."""
    for big, small in (("Mt", "kt"), ("kt", "t")):
        if u == big and v and abs(v) < (0.001 if big == "Mt" else 0.1):
            v, u = v * 1e3, small
    return f"{_nf(v)} {u}"


CHECK_TITLES = {
    "K1": "trader totals of crops against USDA PSD", "K2": "a bilateral flow above the importer's total imports in USDA PSD",
    "K3": "crude oil exports against EIA production", "K4": "coal exports and imports against EIA",
    "K6": "exporter continuity", "K7": "importer continuity", "K8": "pairs of the latest year that halved or more than doubled",
    "K10": "exports above USGS mine production", "K11": "physical plausibility against the atlas's own layers (QA only)",
    "K12": "main route against the great-circle distance of its ports (QA only)",
    "K13": "pairs declared far below the usual unit value of their product", "K14": "exporters with no production in the EIA table",
}


def qa_checks():
    """Sections of QA.md rendered from pipeline/cache/trade_checks.json (build_lanes.py writes K1 to K12 except K9,
    build_freight.py adds K9). This builder only reads the file."""
    recs = K.load()
    out = ["", "## Trade checks", "",
           "Findings of `pipeline/trade/checks.py`, read from `pipeline/cache/trade_checks.json`. No check changes a figure; "
           "a finding marked flag is above the check's threshold and feeds the notes of lanes and tables, watch is the band "
           "below it, qa is for this file only. K5 (gas against EIA) is not run: the units do not reconcile.", ""]
    if not recs:
        return out + ["- trade_checks.json not found or empty", ""]
    by = defaultdict(list)
    for r in recs:
        by[r["check"]].append(r)
    for cid in sorted(by, key=lambda c: int(c[1:])):
        if cid == "K9":
            continue
        rs = sorted(by[cid], key=lambda r: (-(r.get("year") or 0), r.get("group") or "", -(r.get("value") or 0)))
        out += [f"### {cid}: {CHECK_TITLES.get(cid, '')} ({len(rs)})", ""]
        out += [f"- {r.get('level')}: {r['text']}" for r in rs] + [""]
    k9 = by.get("K9", [])
    out += ["## Passages against IMF PortWatch (K9)", "",
            "'At least' and 'up to' tonnage of every lane group's recorded seaborne pairs (chokepoint shares of the atlas) by vessel "
            "type (dry bulk; tanker; container, general cargo and ro-ro), against IMF PortWatch's estimated volume of all ships of that "
            "type (IMF PortWatch, data adapted). A passage is flagged when 'at least' is above 110% of PortWatch's best full year "
            "since 2019, or above PortWatch's volume of the same year (the atlas routes cargo on the normal itinerary); the Danish "
            "Straits counter is the Oresund only. Written by `build_freight.py`; never a failure of the build.", "",
            "| passage | type | at least (Mt) | up to (Mt) | PortWatch, latest year (Mt) | best year (Mt) | at least / best | level |",
            "|---|---|---|---|---|---|---|---|"]
    for r in sorted((r for r in k9 if r.get("kind") == "passage"), key=lambda r: (r["chokepoint"], r["type"])):
        ref = "-" if r.get("reference") is None else _fmt(r["reference"])
        out.append(f"| {r['chokepoint']} | {r['type']} | {_fmt(r['value'])} | {_fmt(r['high'])} | {ref} | {_fmt(r['best'])} ({r['bestYear']}) "
                   f"| {r['ratio']:.2f} | {r['level']} |")
    out += [""] + [f"- {r['text']}" for r in k9 if r.get("kind") == "passage" and r["level"] == "flag"]
    passage_names = {r["chokepoint"]: r["text"].split(",")[0] for r in k9 if r.get("kind") == "passage"}
    par =[r for r in k9 if r.get("kind") == "parallel"]
    skipped = max((r.get("skipped") or 0 for r in par), default=0)
    if skipped:
        intro = (f"Incomplete: {_fmt(skipped)} Mt of pairs were not recomputed (their plan was not cached), so every figure of the "
                 f"table may be short by up to {_fmt(skipped)} Mt and the 5% or 300 nm column is not an exact reproduction of the "
                 "published figures.")
    else:
        intro = "The published figures use 5% or 300 nm."
    out += ["", "### Parallel passages under other thresholds of the parallel rule (K9)", "",
            "Recomputed with `routing.classify()` from the option distances cached by `build_lanes.py` (no routing). " + intro,
            "", "| passage | 3% or 150 nm | 5% or 300 nm | 10% or 500 nm |", "|---|---|---|---|"]
    for c in dict.fromkeys(r["chokepoint"] for r in par):
        cells = [f"{_fmt(r['value'])} to {_fmt(r['high'])}" for r in sorted((r for r in par if r["chokepoint"] == c), key=lambda r: r["pct"])]
        out.append(f"| {passage_names.get(c, c)} | " + " | ".join(cells) + " |")
    if par and par[0].get("skipped"):
        out.append(f"\nPairs skipped because their plan was not cached: {_fmt(par[0]['skipped'])} Mt.")
    if not par:
        out.append("\n- not computed (route cache empty or of another version)")
    eia_rows = [r for r in k9 if r.get("kind") == "eia"]
    if eia_rows:
        out += ["", "### EIA beside the atlas (crude oil)", ""] + [f"- {r['text']}" for r in eia_rows]
    return out + [""]


def _label(g):
    return {"lpg": "LPG", "lng": "LNG", "dap": "DAP"}.get(g) or K.label(g)


def qa_dropped(baci):
    out = ["## Rows dropped by the cleaning rules", "",
           "Rows that `clean()` (`pipeline/trade/clean.py`) removes before any table is built. Rule 6 (DROP_NEW_PAIRS): Qatari LPG pairs with no flow in "
           "either neighbouring year; several equal the LNG row of the same pair and year, which suggests "
           "LNG cargoes recorded a second time under the LPG code; this is a hypothesis, not established. "
           "Rule 5 (DROP): the exports of a product that the country cannot have made, left out in every year: " + "; ".join(
               f"{_label(g)} from {K._name(o)}{' to ' + K._name(d) if d else ''} ({why})" for (g, o, d), why in DROP.items()) + ". "
           f"Rule 9 (DROP_LOW_UV): rows of the lithium chemicals group declared under {LITHIUM_MIN_UV:,} USD per tonne in any year, a price of ore or "
           "concentrate rather than of a lithium chemical (hypothesis: a product or a weight misdeclared); rows whose tonnage the atlas estimated are kept.", ""]
    rows = sorted(baci.dropped, key=lambda r: (r["group"], r["year"], -r["t"]))

    def mass(t):
        return f"{_fmt(t / 1e6)} Mt" if t >= 1e6 else f"{_fmt(t / 1e3)} kt"
    for (g, y), grp in pd.DataFrame(rows).groupby(["group", "year"]) if rows else []:
        out.append(f"- {_label(g)} {y}: {len(grp)} row{'s' if len(grp) != 1 else ''}, {mass(grp['t'].sum())}")
    out.append("")
    for r in rows:
        est = " (tonnage estimated from value)" if r.get("est") else ""
        uv = f", {r['uvp']:,.0f} USD/t" if r.get("rule") == "low-uv" else ""
        m = r["usd"] / 1e3  # `usd` is in thousand USD
        value = f"USD {m:,.0f} million" if m >= 100 else f"USD {m:.3g} million" if m >= 1 else f"USD {r['usd']:,.0f} thousand"
        out.append(f"- {_label(r['group'])} {r['year']}, {K._name(r['o'])} to {K._name(r['d'])}: {mass(r['t'])}{est}, {value}{uv}")
    return out + [""] if rows else out + ["- none", ""]


def qa_transit():
    """The rows that the importer-in-transit detector (metals.transit_notes) found, with what the page prints for each."""
    out = ["## Importers in transit", "",
           "Rows that fit the detector of `metals.transit_notes` (an importer of at least 10% of the table's world imports with no production line, no "
           "export line of note, and most of its imports overland). A note is printed only for the rows of the reviewed table `TRANSIT_REVIEWED`; "
           "the other rows are \"detected, no note\": an overland delivery to a neighbour that uses the product is the plain reading, and nothing in the "
           "tables on disk tells such a row from Mozambique's.", ""]
    for key, what, noted in MET.TRANSIT_REPORT:
        out.append(f"- {key}: {what}; " + ("note printed (reviewed row)" if noted else "detected, no note (an overland delivery to a neighbour that uses the product is the plain reading)"))
    return out + ([""] if MET.TRANSIT_REPORT else ["- none", ""])


def qa_draughts():
    have = sorted(VR.DRAUGHT_M)
    none = sorted(set(VR.SPEED) - set(VR.DRAUGHT_M))
    return ["## Vessel classes without a sourced draught", "",
            "The draught rule of the routing (`vessel_rules.avoids()`) restricts a class only where a sourced laden draught exceeds a "
            "sourced passage limit. Classes with a sourced draught: " + ", ".join(f"{c} {VR.DRAUGHT_M[c]:g} m" for c in have) +
            "; passage limits: " + ", ".join(f"{p} {v:g} m" for p, v in sorted(VR.PASSAGE_LIMIT_M.items())) +
            " (Wikipedia, CC BY-SA 4.0; sources in `pipeline/freight/vessel_rules.py`).", "",
            "Not restricted by any strait for want of a sourced draught: " + ", ".join(none) + ".", ""]


def write_qa(index, docs, baci=None, hist=None):
    lines = ["# Commodity data QA", "",
             "Generated by `pipeline/commodities/build_commodities.py`. Top producers use the `production` table, "
             "top exporters the `exports` table; the world total is the published/summed figure in the same table.", "",
             "| commodity | unit (prod / trade) | production: year, top 5 (world) | exports: year, top 3 (world) | missing sections |",
             "|---|---|---|---|---|"]
    allsec = ["production", "reserves", "consumption", "exports", "imports", "flows"]
    for e in index:
        d = docs[e["id"]]
        p, x = d.get("production"), d.get("exports")
        ps = "-" if not p else f"{p['y']} ({p['s']}): " + ", ".join(f"{r['c']} {_fmt(r['v'])}" for r in p["rows"][:5]) + f" (world {_fmt(p['world'])} {p['u']})"
        xs = "-" if not x else f"{x['y']} ({x['s']}): " + ", ".join(f"{r['c']} {_fmt(r['v'])}" for r in x["rows"][:3]) + f" (world {_fmt(x['world'])} {x['u']})"
        units = f"{p['u'] if p else '-'} / {x['u'] if x else '-'}"
        miss = ", ".join(k for k in allsec if k not in d) or "none"
        lines.append(f"| {e['id']} | {units} | {ps} | {xs} | {miss} |")
    lines += ["", "## Other sections (first rows)", ""]
    for e in index:
        d = docs[e["id"]]
        for k in ("consumption", "imports", "reserves", "refinery"):
            if k in d:
                r = d[k]
                lines.append(f"- {e['id']} {k}: {r['y']} ({r['s']}) " + ", ".join(f"{x['c']} {_fmt(x['v'])}" for x in r["rows"][:3]) + (f" (world {_fmt(r['world'])} {r['u']})" if r.get("world") else f" ({r['u']}, no world total)"))
    lines += ["", "## Seaborne summary figures", ""]
    for e in index:
        s = docs[e["id"]]["summary"].get("seaborne")
        if s:
            lines.append(f"- {e['id']}: {s['v']} {s['u']} ({s['y']})")
    lines += ["", "## Discrepancies", ""]
    for e in index:
        for t in docs[e["id"]].get("discrepancies", []):
            lines.append(f"- {e['id']}: {t}")
    lines += qa_checks()
    lines += qa_transit()
    if baci is not None:
        lines += qa_dropped(baci)
    lines += qa_draughts()
    if hist:
        lines += ["## Series by country and year (data/commodities/history)", "", hist[0], ""] + [f"- {h}" for h in hist[1:]] + [""]
    lines += ["## Build warnings", ""] + ([f"- {w}" for w in QA_WARN] or ["- none"])
    with open(os.path.join(HERE, "QA.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# Figures quoted from publications. Each carries its publisher and year and is printed with them; the world
# totals stand beside the customs total of the LNG page, none is used in a table of countries. GIIGNL: read in the
# 2026 edition of its annual report (source id "giignl-2026"), which gives 2025 and, as the year before, 2024.
# IGU: the 2026 edition of its World LNG Report, which gives 2025 (source id "igu-lng-report-2026"); neither publisher's country table is copied
LNG_URL = {"GIIGNL": "https://www.worldlngsummit.com/media/5stjrkng/2026-giignl-annual-report.pdf",
           "IGU": "https://igu.org/igu-reports/2026-world-lng-report"}
LNG_REFERENCE = [
    # (publisher, publication, figure, unit, year, what)
    ("GIIGNL", "Annual Report 2026 edition", 428, "Mt", 2025, "world LNG trade"),
    ("GIIGNL", "Annual Report 2026 edition", 406, "Mt", 2024, "world LNG trade"),
    ("IGU", "World LNG Report 2026 edition", 437.0, "Mt", 2025, "world LNG trade"),
    ("GIIGNL", "Annual Report 2026 edition", 109, "Mt", 2025, "exports of the United States, which the report calls the world's dominant LNG exporter"),
]
# U.S. Energy Information Administration, "Liquefied U.S. Natural Gas Exports, Annual" (series NG.N9133US2.A of the
# natural-gas bulk file https://www.eia.gov/opendata/bulk/NG.zip, public domain, read in November 2026), million cubic feet.
EIA_US_LNG = {"series": "N9133US2", "year": 2024, "mmcf": 4367170}
# Natural Resources Canada, "Conversion factors and common units to be used for North American Cooperation on Energy
# Information" (page dated 2025-01-16): 1 million tonnes of LNG = 48.0279467 billion cubic feet of natural gas.
BCF_PER_MT_LNG = CN.BCF_PER_MT_LNG
# the cubic foot is CN.FOOT_M ** 3 m3 by definition: 1.36 bcm, the factor as printed (every converted figure reproduces from it)
BCM_PER_MT_LNG = round(BCF_PER_MT_LNG * CN.FOOT_M ** 3, 2)
UNITS_URL = "https://natural-resources.canada.ca/climate-change/conversion-factors-common-units-used-north-american-cooperation-energy-information"
GAS_FACTOR = (f"1 Mt of LNG = {BCF_PER_MT_LNG:.2f} bcf = {BCM_PER_MT_LNG:.2f} bcm of gas (Natural Resources Canada, conversion "
              "factors for North American energy information, 2025); it assumes a typical LNG composition")
# U.S. Energy Information Administration, Country Analysis Brief: Russia (last updated 24 July 2025,
# https://www.eia.gov/international/analysis/country/RUS), public domain, read in November 2026.
EIA_RUSSIA_URL = "https://www.eia.gov/international/analysis/country/RUS"
EIA_RUSSIA = {"rank": "fourth-largest", "total_year": 2023, "total_mbd": 1.9, "share_year": 2024,
              "shares": [("Türkiye", 17), ("China", 11), ("Singapore", 8), ("the United Arab Emirates", 8), ("India", 8), ("Brazil", 8)]}


MET_FLOW_MIN = 1000  # tonnes: a pair below it is not a flow of the page (the threshold of the customs extract)
MET_TYPE_NAME = {"hard-coking": "hard coking", "semi-soft": "semi-soft coking", "pci": "PCI"}
MET_SOURCE_LABEL = {"qld-coal-sales": "Queensland", "eia-coal": "the United States"}
MET_LAKE_DISTRICTS = ("Cleveland, OH", "Detroit, MI")  # customs districts of the EIA file that are ports of the Great Lakes
MET_INTL_MIN_MT = 5  # a producing exporter of this page's EIA table, at least this many Mt in the year, with no source by destination: named in the note


def _lc(s):
    """The words of the workbook's About sheet inside a sentence: "Data through to 30 June 2026" -> "data through to 30 June 2026"."""
    return s[:1].lower() + s[1:]


def _iso_date(s):
    """2026-10-01 -> 1 October 2026"""
    y, m, d = (int(x) for x in s.split("-"))
    return f"{d} {MONTHS[m - 1]} {y}"


def _by_destination(meta):
    """How a metallurgical coal source's file says its figures are cut by destination ("by destination country", "by destination as the file gives it"),
    taken from the definition in its meta file (pipeline/cache/metcoal_meta.json), not typed."""
    m = re.search(r"by destination(?: country| as the file gives it)", meta["definition"])
    if not m:
        raise SystemExit(f"met-coal: the definition of {meta['id']} does not say how its figures are cut by destination: {meta['definition']}")
    return m.group(0)


def met_coal_flows(baci, eia, intl_year):
    """The Main flows block of the Metallurgical coal page: metallurgical coal by pair of countries from the exporters' own statistics, not from
    customs data (whose coal group is all coal and is not touched): Queensland's sales to export by destination (Australia) and the exports
    of rank metallurgical in the Census Bureau's declarations as EIA publishes them (the United States), the year of the customs data. One row per
    destination of at least MET_FLOW_MIN tonnes, each row with its own source. Nothing is added across the two sources and nothing is subtracted
    from the customs coal. Returns (flows, notes, defs): defs are the sentences printed in the footer of the block, one per source, so that the
    definition of a figure is read where the figure is met."""
    y = BACI_YEAR
    qld, us = "qld-coal-sales", "eia-coal"
    pq, pu = metcoal.pairs(qld, y), metcoal.pairs(us, y)
    mq, mu = metcoal.meta(qld), metcoal.meta(us)
    flows = []
    for src, o, pr in ((qld, "AUS", pq), (us, "USA", pu)):
        for dest, t in pr.items():
            if t < MET_FLOW_MIN:
                continue
            kind, transit = baci.mode(o, dest, "coal")
            f = {"o": o, "d": dest, "v": rnd(t / 1e6), "u": "Mt", "y": y, "s": src}
            if kind:
                f["mode"] = "sea" if kind == "transit" else kind
                if transit:
                    f["transit"] = transit
            if src == qld:
                ct = metcoal.coal_types(src, y, dest)
                n = (f"Queensland producers' sales to export of metallurgical coal, {_by_destination(mq)}: "
                     + ", ".join(f"{MET_TYPE_NAME[k]} {_fmts(ct[k] / 1e6, 'Mt')}" for k in MET_TYPE_NAME if ct.get(k)))
            else:
                ds = sorted(metcoal.districts(src, y, dest).items(), key=lambda kv: -kv[1])
                n = "exports of rank metallurgical as declared at export (U.S. Census Bureau, through EIA)"
                if ds:
                    n += "; loaded in the customs districts of " + ", ".join(f"{k} {_fmts(v / 1e6, 'Mt')}" for k, v in ds[:4]) + (f" and {len(ds) - 4} more" if len(ds) > 4 else "")
                lakes = [k for k, _ in ds if k in MET_LAKE_DISTRICTS]
                if lakes and kind == "land":
                    n += (f"; the districts of this pair include {_and(lakes)}, ports of the Great Lakes: the file does not say by which mode each district's coal left, "
                          "and the arc of the map reads the pair as overland")
            if kind == "transit" and not transit:
                n += "; sea through a foreign port (not specified)"
            elif kind == "mixed":
                n += "; this trade moves both by sea and overland and the split is not known"
            f["n"] = n
            flows.append(f)
    flows.sort(key=lambda f: -f["v"])
    tq, tu = sum(pq.values()), sum(pu.values())
    shown = lambda src: sum(f["v"] for f in flows if f["s"] == src)  # noqa: E731
    n_q, n_u = sum(1 for f in flows if f["s"] == qld), sum(1 for f in flows if f["s"] == us)
    ct = {k: sum(metcoal.coal_types(qld, y, d).get(k, 0) for d in pq) for k in MET_TYPE_NAME}
    notes = []
    # 1. Australia
    ally = mq["totals"][f"{y + 1}-metallurgical"] if f"{y + 1}-metallurgical" in mq["totals"] else None
    notes.append(
        f"Australia, {y}: Queensland producers' sales to export of metallurgical coal {_by_destination(mq)}, {_fmt(tq / 1e6)} Mt to {len(pq)} countries"
        + " ("
        + ", ".join(f"{MET_TYPE_NAME[k]} {_fmt(v / 1e6)} Mt" for k, v in ct.items()) + f"), the sum of the four quarters of {y}"
        + (f"; {n_q} of the {len(pq)} countries have at least {MET_FLOW_MIN:,} t and are listed above" if n_q != len(pq) else "")
        + ", from the Queensland Government's "
        f"Quarterly Coal Sales (CC BY 4.0). Credit as the workbook's About sheet gives it: \"{mq['credit']}\". PCI, pulverised coal for "
        "injection, is counted as metallurgical; before 2022 the file holds it inside semi-soft coking coal. The workbook is downloaded by hand and is not refreshed "
        f"by the scheduled updates: it reads \"{mq['data_through']}\" and \"{mq['current_as_at']}\", and its About sheet says that the data may be revised. "
        f"The figures are the atlas's sums of the quarters. The disclaimer of the About sheet reads: \"{mq['disclaimer_full']}\""
        + (f" Queensland's total of {y + 1}: {_fmt(ally / 1e6)} Mt." if ally else ""))
    # 2. Queensland ports
    pp = sorted(metcoal.ports(qld, y).items(), key=lambda kv: -kv[1])
    notes.append(f"Queensland loads this coal at {_and([f'{k} {_fmt(v / 1e6)} Mt' for k, v in pp])} in {y} (the file names Hay Point and Dalrymple Bay as two ports). "
                 "The Queensland file gives the port of loading in total and the destination in total: it has no port by destination.")
    # 3. United States
    st = mu["totals"][f"{y}-metallurgical"]["short_tons"]
    du = sorted(metcoal.ports(us, y).items(), key=lambda kv: -kv[1])
    can = metcoal.districts(us, y, "CAN")
    notes.append(
        f"United States, {y}: exports of rank metallurgical as declared at export (U.S. Census Bureau, Monthly Report EM 545) to {len(pu)} countries"
        + f", {_fmt(tu / 1e6)} Mt "
        f"({st / 1e6:.2f} million short tons at {CN.TONNES_PER_SHORT_TON} t per short ton), from EIA's file of coal exports"
        + (f"; {n_u} of the {len(pu)} countries have at least {MET_FLOW_MIN:,} t and are listed above" if n_u != len(pu) else "")
        + ". The file does not define the rank. By customs district, as the file names them: "
        + ", ".join(f"{k} {_fmt(v / 1e6)} Mt" for k, v in du[:5])
        + (f"; of the {_fmt(pu.get('CAN', 0) / 1e6)} Mt to Canada, {_fmt(can.get('Buffalo, NY', 0) / 1e6)} Mt left through Buffalo, NY"
           + (f", and the districts of this pair include {_and([k for k in can if k in MET_LAKE_DISTRICTS])}, ports of the Great Lakes (the file does not say by which mode each district's coal left)"
              if any(k in can for k in MET_LAKE_DISTRICTS) else "") if can.get("Buffalo, NY") else "")
        + f". The file is dated {_iso_date(mu['file_date'])}; its description says that the figures of the latest period are preliminary estimates, final by the fall that follows the year "
        f"(the file's latest year is {max(mu['years'])}). Source: U.S. Energy Information Administration.")
    # 4. the destination of an exporter's statistics is not the country where customs data record the coal
    cu = baci.group("coal").groupby(["o", "d"])["t"].sum()
    above = []
    for o, pr in (("AUS", pq), ("USA", pu)):
        for dest, t in pr.items():
            if t >= MET_FLOW_MIN and t > float(cu.get((o, dest), 0)):
                above.append((o, dest, t, float(cu.get((o, dest), 0))))
    big = max(above, key=lambda r: r[2] - r[3])
    iq, cq = pq.get("IND", 0), float(cu.get(("AUS", "IND"), 0))
    notes.append(
        f"A destination of the exporter's statistics is not always the country where customs data record the coal: {sum(1 for r in above if r[0] == 'AUS')} of the {n_q} Queensland pairs and {sum(1 for r in above if r[0] == 'USA')} of the {n_u} "
        f"United States pairs are above the customs record of all coal for the same pair in {y}; the largest gap is {cname(big[0])} to {cname(big[1])}, {_fmt(big[2] / 1e6)} Mt "
        f"against {_fmt(big[3] / 1e6)} Mt in customs data. The flows above are not a part of the customs flows of the Thermal coal page and are not subtracted from them: "
        f"for Australia to India the customs data record {_fmt(cq / 1e6)} Mt of all coal and Queensland {_fmt(iq / 1e6)} Mt of metallurgical coal, and the difference "
        f"({_fmt((cq - iq) / 1e6)} Mt) is not the thermal coal of that pair.")
    # 5. what is covered, each exporter against EIA International's own figure
    intl = eia.s[("130-4", "MT")]
    mt = lambda g: intl[g][y] / 1e3  # noqa: E731
    prod = eia.s[("130-1", "MT")]  # an exporter that mines it: the Netherlands re-exports and has no production
    others = sorted(((g, mt(g)) for g in intl if g not in ("WORL", "AUS", "USA") and intl[g].get(y, 0) / 1e3 >= MET_INTL_MIN_MT and cname(g) != g
                     and prod.get(g, {}).get(y, 0) > 0), key=lambda r: -r[1])
    # the exporters of this table with no source by destination: where their coal by pair can be read (customs data, all types together)
    thermal = cu.sort_values(ascending=False).head(NFLOWS)  # the Main flows of the Thermal coal page: the twenty largest pairs
    thermal_rows = [(baci.iso(o), baci.iso(dd), t) for (o, dd), t in thermal.items()]
    lanes = baci.lanes["coal"]["ids"]
    where = []
    for g, _ in others:
        fl = [(dd, t) for o, dd, t in thermal_rows if o == g]
        ln = sorted(i for i in lanes if i.startswith(f"coal:{g}-"))
        bits = []
        if fl:
            bits.append(f"{len(fl)} of the {NFLOWS} Main flows of the Thermal coal page ({', '.join(f'{cname(dd)} {_fmt(t / 1e6)} Mt' for dd, t in fl[:3])}"
                        + (f" and {len(fl) - 3} more" if len(fl) > 3 else "") + ")")
        if ln:
            bits.append(f"{len(ln)} lanes of the lane tables of both coal pages")
        where.append(f"{cname(g)}: " + (_and(bits) if bits else "no flow of the Thermal coal page and no lane"))
    notes.append(
        f"What these flows cover, {y}: EIA International gives metallurgical coal exports of {_fmt(mt('AUS'))} Mt for Australia and {_fmt(mt('USA'))} Mt for the United States, of "
        f"{_fmt(mt('WORL'))} Mt in the world. The Queensland rows are {shown(qld) / mt('AUS'):.0%} of the Australian figure (New South Wales has no destinations in the Queensland file), "
        f"the EIA rows {shown(us) / mt('USA'):.0%} of the United States figure. No free source loaded gives destinations for "
        + _and([f"{cname(g)} ({_fmt(v)} Mt)" for g, v in others]) + ", and no list of metallurgical coal of the atlas holds their coal by pair. "
        f"Customs data give it for all types of coal together, in the places below: the flows of the Thermal coal page are the {NFLOWS} largest customs pairs, and the "
        "lane tables of both coal pages (Seaborne lanes, group \"Coal (all types)\") list the customs lanes by sea. "
        + "; ".join(where) + ".")
    # 6. definitions and years
    notes.append(
        f"Three definitions of metallurgical coal are on this page and are not added to one another: the tables above are EIA International, {intl_year}, whole countries, all destinations; "
        f"the Queensland rows are sales by Queensland producers with PCI included; the United States rows are exports by rank as declared. The flows are those of {y}, the year of the "
        f"customs data, beside tables of {intl_year}.")
    # 7. the lanes
    notes.append("The seaborne lanes of this page are customs data for all coal, and coke: they are not the flows above.")
    # the words of each source's own file (the meta files), and the evidence that a destination of these statistics is not the country of the customs data
    defs = [f"Australia rows are Queensland only: producers' sales to export of {_and(list(MET_TYPE_NAME.values()))} coal together, {_by_destination(mq)}.",
            f"United States rows are exports of rank metallurgical as declared, {_by_destination(mu)}.",
            f"A destination here is not always where customs data record the coal: {cname(big[0])} to {cname(big[1])} is {_fmt(big[2] / 1e6)} Mt here and "
            f"{_fmt(big[3] / 1e6)} Mt of all coal in customs data."]
    return flows, notes, defs


def lng_own_statistics(baci):
    """The LNG page's cross-check: the exports of the two exporters whose own statistics are open, beside the customs figure of each, and the
    exports of Australia by market. Returns (extra tables, notes). Not a ranking, and not used by any other table of the page."""
    a = aus_req_lng.load()
    y = a["year"]
    if y != BACI_YEAR or EIA_US_LNG["year"] != y:
        raise SystemExit(f"LNG own statistics: Australia {y}, EIA {EIA_US_LNG['year']} and the customs year {BACI_YEAR} are not the same year")
    exp = baci.totals("lng", "exports")
    pair = baci.group("lng", y).groupby(["o", "d"])["t"].sum() / 1e6
    us_mt = EIA_US_LNG["mmcf"] / 1e3 / BCF_PER_MT_LNG
    share = lambda own, cust: f"{cust / own:.0%} of the exporter's own figure"  # noqa: E731
    r_aus = ("AUS", a["total"], f"{a['source']}, {a['edition']}, calendar year {y}: the department's estimate (footnote n of its table 41). "
             f"Customs data (CEPII BACI): {_fmt(exp['AUS'])} Mt, {share(a['total'], exp['AUS'])}.")
    r_us = ("USA", us_mt, f"EIA, liquefied U.S. natural gas exports (series {EIA_US_LNG['series']}, public domain): {EIA_US_LNG['mmcf'] / 1e3:,.0f} bcf in {y}, "
            f"converted at {BCF_PER_MT_LNG:.2f} bcf per Mt (Atlas conversion). Customs data (CEPII BACI): {_fmt(exp['USA'])} Mt, {share(us_mt, exp['USA'])}.")
    own = ranked([r_aus, r_us], y, "disr-req", "Mt", digits=3,
                 n=("Exports of LNG as the exporting country's own statistics give them, beside the customs figure of each (CEPII BACI): Australia's "
                    "Resources and Energy Quarterly, and the United States' EIA series converted to tonnes. A cross-check of the customs tables, not a ranking: "
                    "the atlas has found no open source for the other exporters. The definitions differ (the customs figures are the reconciled declarations of "
                    "the exporter and the importer), and the customs tables of this page stay as they are"))
    own["norank"] = True
    # each row has its own source: the department's figure for Australia; for the United States the atlas's conversion of EIA's volume, EIA being the source of the volume
    own["srcs"] = ["disr-req", "eia-ng"]
    for r in own["rows"]:
        r["s"], r["y"] = ("eia-ng" if r["c"] == "USA" else "disr-req"), y
        if r["c"] == "USA":
            r["conv"] = True
    own["conv"] = "the United States row is an Atlas conversion of EIA's volume of gas in billion cubic feet, at the factor named in its note"
    mk = ranked([(c, v, f"Customs data (CEPII BACI), Australia to {cname(c)}: {_fmt(float(pair.get(('AUS', c), 0)))} Mt")
                 for c, v in a["markets"].items()], y, "disr-req", "Mt", world=a["total"],
                n=(f"Resources and Energy Quarterly, {a['edition']}, table 41 (calendar year {y}, volume): the five principal markets that the table lists for LNG "
                   f"(fixed, not re-ranked each year); the other markets are not given by the source. {a['total_note'].replace('n ', 'Footnote n: ', 1)} "
                   f"{a['table_source']} Attribution: {a['attribution']}"))
    mk["norank"] = True
    mk["shareOf"] = "Australia's exports"  # the total is Australia's exports, not the world's
    tables = [{"key": "lng-own-statistics", "title": f"Exports in the exporting country's own statistics, {y} (a cross-check, not a ranking)", "table": own},
              {"key": "lng-australia-markets", "title": f"Australia's LNG exports by market, {y} (Resources and Energy Quarterly)", "table": mk}]
    notes = [f"Own statistics against customs: Australia's Resources and Energy Quarterly gives {_fmt(a['total'])} Mt of LNG exports in {y} against {_fmt(exp['AUS'])} Mt in the customs "
             f"table, and EIA's series for the United States {_fmt(us_mt)} Mt (Atlas conversion) against {_fmt(exp['USA'])} Mt. No open source for the other exporters is loaded, so "
             "the customs tables stay the atlas's figures for them. " + a["attribution"] + " The workbook is downloaded by hand (the department's site refuses scripted downloads) "
             f"and is not refreshed by the scheduled updates: the page reads the {a['edition']} edition until a newer workbook is downloaded."]
    return tables, notes


def tin_china_declared(baci):
    """China's declared imports of tin ores and concentrates (UN Comtrade) by origin in the latest year of its cache, with the series of each year
    in the history, and the notes on the flow Myanmar to China that the atlas adds to the customs table (rule 11 of clean.py). Returns (table, notes)."""
    c = comtrade_tin.load()
    ys = comtrade_tin.years()
    y = ys[-1]

    def table(yr):
        x = c["years"][str(yr)]
        top = list(x["top"])
        if x["myanmar"] and all(r["c"] != "MMR" for r in top):
            top.append(x["myanmar"])
        rows = [(r["c"], r["t"] / 1e3, ("UN Comtrade estimated the net weight of this row" if r["est"] else None)) for r in top]
        t = ranked(rows, yr, "comtrade", "kt", world=x["world"]["t"] / 1e3,
                   n=(f"UN Comtrade (public preview), China as reporter, imports of HS 260900 (tin ores and concentrates), {yr}: net weight as China declares it, "
                      f"from {x['world']['origins']} origins; the table lists the five largest and Myanmar"
                      + ("; Comtrade's total for the year is an estimate (the origins add up to it)" if x["world"]["est"] else "") + ". Source: UN Comtrade"))
        t["norank"] = True
        t["shareOf"] = "China's declared imports"  # the total is China's imports, not the world's
        return set_basis(t, "ores and concentrates, net weight declared by China")

    t = table(y)
    t["_hist"] = (ys, table)
    first = ys[0]
    mm = {yr: c["years"][str(yr)]["myanmar"] for yr in ys}
    raw = pd.read_csv(os.path.join(CACHE, "baci_flows.csv.gz"))
    raw = raw[(raw["group"] == "tin-ore") & (raw["o"] == "MMR") & (raw["d"] == "CHN")].set_index("year")["t"]
    # the years in which the customs file has no row of the pair, or one under a tenth of the declared tonnage (the rows rule 11 adds or replaces)
    moved = [yr for yr in ys if raw.get(yr, 0) < comtrade_tin.REPLACE_BELOW * mm[yr]["t"]]
    first_all = all(c["years"][str(yr)]["top"][0]["c"] == "MMR" for yr in ys)
    notes = [f"Tin ores and concentrates (HS 260900): China declares {_fmt(mm[y]['t'] / 1e3)} kt from Myanmar in {y}, {_fmt(mm[y - 1]['t'] / 1e3)} kt in {y - 1} and "
             f"{_fmt(mm[y - 2]['t'] / 1e3)} kt in {y - 2} ({mm[y]['t'] / c['years'][str(y)]['world']['t']:.0%} of its imports in {y}"
             + (f", the first origin in every year from {ys[0]} to {y}" if first_all else "") + "), where the reconciled customs file the atlas uses, CEPII BACI, has "
             f"at most {_fmt(max(raw.get(yr, 0) for yr in moved) / 1e3)} kt a year of this pair in {_years(moved)} (its extract drops flows under 1,000 t and USD 1 million, so "
             f"{_years([yr for yr in moved if yr not in raw.index])} have no row there). The atlas therefore adds "
             f"the flow from China's import declaration (UN Comtrade) to its customs table in {_years(moved)}: a listed correction, pair by pair "
             "(the Methodology, section 1, cleaning rule 11), flagged on each row. The flow moves overland: no sea lane, no passage. "
             f"The declared figures are net weight and a CIF value, not BACI's reconciled figures, and the series of the customs tables starts from the declaration in "
             f"{ys[0]}: the years before keep BACI's figures, so the series breaks between {ys[0] - 1} and {ys[0]}"
             + "".join(f". UN Comtrade's answer for {nw} carries no net weight, only a quantity that it estimated ({_fmt(v['estimated_quantity_t'] / 1e3)} kt, of which "
                       f"{_fmt(v['myanmar_estimated_quantity_t'] / 1e3)} kt from Myanmar) and a value, so it is not used" for nw, v in c.get("no_net_weight", {}).items())
             + f"; the years before {min([ys[0]] + [int(k) for k in c.get('no_net_weight', {})])} are not loaded.",
             "The table of China's declared imports shows the five largest origins and Myanmar for the year, and its history the same countries in each year. "
             "Its total is China's, not the world's, and Comtrade's total of some years is an estimate. It is a small part of the declaration, printed with "
             "the attribution Source: UN Comtrade; the answers are not published as files."]
    return t, notes


def lpg_us_notes(baci):
    """Notes of the LPG page on the United States' exports to Mexico and Canada, and on its three Asian buyers (rule 10 of clean.py), from the
    cache of pipeline/trade/us_lpg.py and the cleaned frame."""
    df, c = baci.df, us_lpg.load()["census"]
    lp = df[(df["group"] == "lpg") & (df["o"] == "USA")]

    def row(d, y):
        r = lp[(lp["d"] == d) & (lp["year"] == y)]
        return r.iloc[0] if len(r) else None

    fixed = sorted(int(y) for y in lp[(lp["d"] == "MEX") & (lp["flag"] == "est-volume")]["year"])
    ok = [y for y in range(2004, min(fixed)) if row("MEX", y) is not None and us_lpg.estimate("MEX", y)]
    ratio = [row("MEX", y)["t0"] / us_lpg.estimate("MEX", y)["t"] for y in ok]
    meas = {y: us_lpg.measure("MEX", y, row("MEX", y)["t0"]) for y in fixed}
    per_m3, per_t = {y: m["per_m3"] for y, m in meas.items()}, {y: m["per_t"] for y, m in meas.items()}
    notes = [
        "United States to Mexico: " + "; ".join(f"{y} {_fmt(row('MEX', y)['t0'] / 1e6)} Mt in CEPII BACI, {_fmt(row('MEX', y)['t'] / 1e6)} Mt here" for y in fixed)
        + f". From {fixed[0]} the customs tonnage of the pair is {min(per_m3.values()):.2f} to {max(per_m3.values()):.2f} times the volume in cubic metres of the United States' own "
        f"statistics ({', '.join(f'{y} {v:.2f}' for y, v in per_m3.items())}) and {min(per_t.values()):.1f} to {max(per_t.values()):.1f} times the tonnage that this volume gives at the "
        f"density of the cargo (the volume is EIA's exports of propane and butanes to Mexico, {_fmt(us_lpg.estimate('MEX', max(fixed) - 1)['m3'] / 1e3)} million m3 in {max(fixed) - 1}, and the "
        f"US Census Bureau's export detail file, {_fmt(sum(c['pairs']['MEX']['qty_m3'].values()) / 1e6)} million m3 in {c['year']}). Its unit value "
        f"({row('MEX', max(fixed))['uvp']:,.0f} USD/t in {max(fixed)}) is {row('MEX', max(fixed))['uvp'] / (row('MEX', max(fixed))['uv'] * 1000):.2f} times the group's median unit value. "
        f"{us_lpg.CAUSE[0].upper() + us_lpg.CAUSE[1:]}. "
        "The tonnage of these years is the volume of the United States' own statistics (EIA's propane, normal butane and isobutane exports, which come from the Census Bureau's "
        f"customs data) times the density of the cargo in the Census file ({c['density_kg_m3']['2711120010']:.0f} kg/m3 for propane, {c['density_kg_m3']['2711130000']:.0f} for butanes), an Atlas estimate; "
        f"in {c['year']} it is the Census file's own quantity. From 2004 to {min(fixed) - 1} the customs tonnage is {min(ratio):.1f} to {max(ratio):.1f} times the tonnage from EIA's volumes: "
        "it is left as reported. 2002 and 2003 cannot be checked (EIA's series start in 2004) and are left as reported.",
        f"United States to Mexico, mode: in {c['year']} the Census file gives a shipping weight for the cargo that went by vessel only, {_fmt(c['pairs']['MEX']['vessel_t'] / 1e6)} Mt, "
        f"{c['pairs']['MEX']['vessel_t'] / c['pairs']['MEX']['total_t']:.0%} of the pair's {_fmt(c['pairs']['MEX']['total_t'] / 1e6)} Mt (the file gives no total weight: the total is its "
        "quantity times its density); the file does not name the modes of the rest, and the atlas reads it as overland (rail, road and pipeline), so the lane of the pair is the share by sea. "
        + MD.other_years("lpg", "USA", "MEX", c["year"]) + ".",
    ]
    can = [(y, row("CAN", y)) for y in range(2004, BACI_YEAR + 1) if row("CAN", y) is not None and us_lpg.estimate("CAN", y)]
    r_before = [r["t0"] / us_lpg.estimate("CAN", y)["t"] for y, r in can if y < 2015]
    r_after = [r["t0"] / us_lpg.estimate("CAN", y)["t"] for y, r in can if y >= 2015]
    cn = c["pairs"]["CAN"]
    r24 = row("CAN", c["year"])
    notes.append(
        f"United States to Canada: checked and not corrected. CEPII BACI gives {_fmt(r24['t0'] / 1e3)} kt in {c['year']}; the Census file's quantity of propane and butanes "
        f"({_fmt(sum(cn['qty_m3'].values()) / 1e6)} million m3, the same as EIA's) is about {_fmt(cn['total_t'] / 1e3)} kt at the file's densities. From 2015 the customs tonnage is "
        f"{min(r_after):.1f} to {max(r_after):.1f} times the tonnage from EIA's volumes (against {min(r_before):.1f} to {max(r_before):.1f} from 2004 to 2014) and its unit value is under two thirds "
        "of the group's, as in Mexico's case, but EIA's figures for Canada are small whole numbers of thousand barrels a day and the years do not all leave the range of the earlier ones, "
        "so no year is replaced.")
    jp = {i: c["pairs"][i]["vessel_t"] for i in ("JPN", "CHN", "KOR")}
    cu = {i: float(row(i, c["year"])["t"]) for i in jp}
    notes.append(
        f"LPG from the United States to Japan, China and South Korea, {c['year']}: the US Census Bureau's export file gives vessel shipping weights of {_fmt(jp['JPN'] / 1e6)}, "
        f"{_fmt(jp['CHN'] / 1e6)} and {_fmt(jp['KOR'] / 1e6)} Mt ({_fmt(sum(jp.values()) / 1e6)} Mt together); CEPII BACI gives {_fmt(cu['JPN'] / 1e6)}, {_fmt(cu['CHN'] / 1e6)} and "
        f"{_fmt(cu['KOR'] / 1e6)} Mt ({_fmt(sum(cu.values()) / 1e6)} Mt together, {abs(sum(cu.values()) / sum(jp.values()) - 1):.0%} apart). The two sources split the cargo among the three "
        "buyers differently; the atlas keeps CEPII BACI's pairs.")
    return notes


def _and(names):
    return ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1]


def _isleap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _years(ys):
    """[2021, 2022, 2023, 2025] -> "2021 to 2023 and 2025"."""
    runs, ys = [], sorted(ys)
    for y in ys:
        if runs and y == runs[-1][1] + 1:
            runs[-1][1] = y
        else:
            runs.append([y, y])
    return _and([str(a) if a == b else f"{a} to {b}" for a, b in runs])


def alt_fig(f, v, u, text):
    """Second unit of a headline figure, printed in brackets by the site: an Atlas conversion with its factor, kept to three
    significant digits (the stated factor reproduces the printed figure)."""
    f["alt"] = {"v": sig(v), "u": u, "s": "atlas", "y": f["y"], "n": "Atlas conversion: " + text}


def gas_pipeline_pairs():
    """({(origin, destination): [pipeline names]}, number of gas pipelines): the ordered pairs of countries along the
    countries listed for each gas pipeline of the atlas's own layer, the first country being the origin."""
    path = os.path.join(DATA, "infrastructure", "pipelines.geojson")
    pairs, n = {}, 0
    for f in json.load(open(path, encoding="utf-8"))["features"]:
        p = f["properties"]
        if p.get("product") != "gas":
            continue
        n += 1
        cs = p.get("cs") or []
        for i, a in enumerate(cs):
            for b in cs[i + 1:]:
                pairs.setdefault((a, b), []).append(p["name"])
    return pairs, n


def lng_importer_check(baci, eia, year, min_bcm=5.0):
    """Customs LNG imports against EIA total gas imports, for the importers where the two measure the same gas: no gas
    pipeline of the atlas layer ends there, customs data record no pipeline gas for them, and no neighbouring
    country exports gas in EIA. Returns [(iso, customs LNG in Mt, EIA imports in bcm, customs/EIA)] by EIA volume."""
    pairs, _ = gas_pipeline_pairs()
    on_pipeline = {c for pr in pairs for c in pr}
    nb = json.load(open(os.path.join(CACHE, "adjacency.json"), encoding="utf-8"))["neighbours"]
    imp, exp = dict(eia.country_values(("26-3", "BCM"), year)), dict(eia.country_values(("26-4", "BCM"), year))
    lng, pipe = baci.totals("lng", "imports"), baci.totals("natural-gas", "imports")
    out = []
    for code, v in lng.items():
        iso = baci.iso(code)
        if not iso or imp.get(iso, 0) < min_bcm or iso in on_pipeline or pipe.get(code, 0) >= 0.01 * v:
            continue
        if any(exp.get(n, 0) > 0 for n in nb.get(iso, [])):
            continue
        out.append((iso, v, imp[iso], v * BCM_PER_MT_LNG / imp[iso]))
    return sorted(out, key=lambda r: -r[2])


def caveats(docs, eia):
    """Known source limitations found by the data audit; shown with the tables they affect.

    Every number in these sentences is read from a table of the atlas or from a source file at build
    time, or comes from LNG_REFERENCE with its publisher and year. No year is typed in the text.
    """
    out = {}

    # LPG: the EIA series for the United States stops early
    us = eia.s[("67-2", "MT")].get("USA", {})
    c = docs["lpg"]["consumption"]
    if eia.lpg_us and c["y"] in eia.lpg_us["years"]:
        # EIA's tonnes for the country are missing after 2021 and out of line in 2021 while its barrels per day are not: the United
        # States is in the table, converted (Eia.ranked), and the caveat says how
        ly = eia.lpg_us["years"]
        miss, bad = sorted(y for y, v in ly.items() if v[2] is None), sorted(y for y, v in ly.items() if v[2] is not None)
        what = (f"EIA's tonnes for the country are missing from {min(miss)}" + (f" and out of line with its barrels per day in {_and([str(y) for y in bad])}" if bad else ""))
        wl = eia.lpg_us["world"]
        how = {k: sorted(y for y, w in wl.items() if w["how"] == k) for k in ("bd", "added", "kept")}
        parts = []
        if how["bd"]:
            parts.append(f"EIA's own world series in barrels per day converted at the same ratio ({_years(how['bd'])})")
        if how["added"]:
            parts.append(f"EIA's world total in tonnes with the United States added ({_years(how['added'])})")
        if how["kept"]:
            parts.append(f"EIA's own world total in tonnes ({_years(how['kept'])})")
        out["lpg"] = {"consumption": (f"The United States is converted from EIA's barrels per day at {eia.lpg_us['ratio']:.2f} barrels per tonne "
                                      f"(Atlas conversion): {what}. The world total of the table is {_and(parts)}, because EIA's own total in tonnes leaves the "
                                      "country out or holds the figure out of line."),
                      "caveatYears": {"consumption": sorted(ly)}}
    elif c["y"] not in us:
        last = max(us) if us else None
        # last value in line with the year before it (the final US point of the EIA file is three times the previous one)
        ref = next((y for y in sorted(us, reverse=True) if y - 1 in us and 0.5 <= us[y] / us[y - 1] <= 2), None)
        t = f"Excludes the United States: the EIA series for US LPG consumption ends in {last}"
        if ref:
            t += f" (EIA gives {_fmt(us[ref] * 1e-3)} Mt for {ref})"
        out["lpg"] = {"consumption": t + ", so the world total is understated.",
                      "notes": [f"EIA's {c['y']} LPG consumption table has no United States value; the world total excludes it."],
                      # the years of the series that have no US value: a past-year table keeps the caveat in those years only
                      "caveatYears": {"consumption": [y for y in range(HIST_FROM, int(c["y"]) + 1) if y not in us]}}

    # LNG: the customs tables against the industry's world totals and the order its publisher gives
    lx = docs["lng"]["exports"]
    lw, ly = lx["world"], lx["y"]
    # one mention of each publication and its address, with every year it gives
    pubs = {}
    for pub, doc, v, u, y, what in LNG_REFERENCE:
        if what == "world LNG trade":
            pubs.setdefault((pub, doc), []).append(f"{v:g} {u} in {y}")
    refs = "; ".join(f"{pub} ({doc}, {LNG_URL[pub]}): {' and '.join(xs)}" for (pub, doc), xs in pubs.items())
    head = f"The country tables and their order are customs tonnage (CEPII BACI, {lw:.2f} Mt of world trade in {ly}), below the industry totals. {refs}."
    text = head
    us = next((r for r in LNG_REFERENCE if r[0] == "GIIGNL" and r[5].startswith("exports of the United States")), None)
    rows = lx["rows"]
    pos = next((i + 1 for i, r in enumerate(rows) if r["c"] == "USA"), None)
    if us and rows[0]["c"] != "USA" and pos:
        text += (f" {us[0]} ({us[1]}) calls the United States the world's dominant LNG exporter ({us[2]:g} Mt in {us[4]}); in the customs table "
                 f"{cname(rows[0]['c'])} comes first ({_fmt(rows[0]['v'])} Mt) and the United States {({2: 'second', 3: 'third'}).get(pos, '#' + str(pos))} "
                 f"({_fmt(rows[pos - 1]['v'])} Mt), so the order of the first rows is not the publisher's.")
    if pos:
        bcf = EIA_US_LNG["mmcf"] / 1e3
        text += (f" EIA (U.S. liquefied natural gas exports, series {EIA_US_LNG['series']}, public domain) gives {bcf:,.0f} bcf in {EIA_US_LNG['year']}, "
                 f"about {bcf / BCF_PER_MT_LNG:.1f} Mt (Atlas conversion at {BCF_PER_MT_LNG:.2f} bcf per Mt), against {_fmt(rows[pos - 1]['v'])} Mt in the customs table.")
    text += " Country profiles show no world rank for LNG."
    # the discrepancy is the head of the caveat, word for word: the page prints it once, with the key figure (CommodityView seenAbove)
    out["lng"] = {"exports": text, "discrepancies": [head],
                  # both caveats compare the customs figures of the latest year: a past-year table shows the short caveat (`caveatShort`)
                  "caveatYears": {"exports": [ly], "imports": [ly]}}

    out["gold"] = {"exports": "This ranks customs trade, not mine supply: countries that refine, trade or vault gold may rank high through re-exports, which the atlas does not measure.",
                   "imports": "Customs trade, not final demand: countries that refine or vault gold may rank high through re-exports, which the atlas does not measure."}
    out["silver"] = {"exports": "This ranks customs trade, not mine supply: countries that refine or trade silver may rank high through re-exports, which the atlas does not measure."}
    out["pgm"] = {"exports": "This ranks customs trade, not mine supply: countries that refine or trade platinum-group metals may rank high through re-exports, and some "
                             "metal may be declared under another code; the atlas does not measure either.",
                  "imports": "Customs trade, not final demand: countries that refine or trade these metals may rank high through re-exports, which the atlas does not measure."}
    out["refined-products"] = {"exports": "This ranks customs trade, not refinery output: countries that store, blend and re-export products may rank high, which the atlas does not measure.",
                               "imports": "Customs trade, not final demand: countries that store, blend and re-export products may rank high, which the atlas does not measure."}
    out["uranium"] = {"exports": "Gross weight of ores and compounds, not contained uranium; Namibia and Niger tonnage exceeds their mine output, so treat as indicative.",
                      "notes": ["Trade tonnage is the gross weight of uranium ores and compounds, not uranium content."],
                      # the comparison with mine output was made for the latest year; the unit holds for every year
                      "caveatYears": {"exports": [BACI_YEAR]}, "caveatPast": {"exports": "Gross weight of ores and compounds, not contained uranium."}}
    out["cobalt"] = {"exports": "Gross weight of cobalt intermediate products and metal (ores are a small part): not comparable with mine production, which is in tonnes of contained cobalt.",
                     "imports": "Gross weight of cobalt intermediate products and metal, not contained cobalt."}
    out["potash"] = {"exports": "Product weight of potassium chloride. The production table is converted to the same unit (Atlas conversion); reserves are in K2O content.",
                     "imports": "Product weight of potassium chloride, not K2O content."}
    out["urea"] = {"production": "Ammonia plant output in tonnes of nitrogen, not urea: not comparable with the urea trade tables, which are in product weight."}
    return out


def registry_caveats(docs, baci):
    """Caveats of the registry (pipeline/trade/caveats.py, active entries in data/freight/caveats.json): the text goes to
    the page notes and to the row of the origin (and, for a pair, of the destination) in the trade tables, so that a
    country profile shows it on that country's row only; flow rows carry the caveat id."""
    by_group = defaultdict(list)
    for cid, (g, _, _) in TRADE.items():
        by_group[g].append(cid)
    for e in baci.caveats.values():
        for cid in by_group.get(e["group"], []):
            d = docs.get(cid)
            if not d:
                continue
            d.setdefault("notes", [])
            if e["text"] not in d["notes"]:
                d["notes"].append(e["text"])
            # the customs record of a crop exporter that is below USDA's figure (Russian grain, C-045): its own visible block on the page
            if e["kind"] == "mirror" and cid in PSD and not any(x["o"] == e["o"] for x in d.get("gaps", [])):
                d.setdefault("gaps", []).append({"o": e["o"], "text": e["text"], "s": "baci", "y": BACI_YEAR})
            for sec, c in (("exports", e["o"]), ("imports", e.get("d"))):
                for r in (d.get(sec) or {}).get("rows", []):
                    if c and r["c"] == c and e["text"] not in r.get("n", ""):
                        r["n"] = joinn(r.get("n"), e["text"])
            # an origin whose recorded exports fell to nothing has no row to carry its note: the table says so (C-025). A country
            # profile shows the short form on every row of the table, so it must hold for any country.
            t = d.get("exports")
            if e["kind"] == "unrecorded" and not e.get("d") and t and not any(r["c"] == e["o"] for r in t["rows"]) and e["text"] not in t.get("caveat", ""):
                add_caveat(t, f"{cname(e['o'])} has no row. {e['text']}")
                t["caveatYears"] = [t["y"]]
                t["caveatShort"] = "Customs tonnage: some origins are recorded badly (see the notes on the commodity page)."


def no_production_notes(docs, baci):
    """The exporters of the customs coke table that the EIA table of coke production of the same page gives no production (check K14, FNCD):
    the registry text goes to the row of the country in the customs table and to the notes of the page, as every caveat of the registry does."""
    d = docs.get("met-coal")
    for e in baci.caveats.values():
        if e["kind"] != "no-production" or not d:
            continue
        t = next((x["table"] for x in d.get("extra") or [] if x["key"] == f"{e['group']}-customs-exports"), None)
        r = next((r for r in (t or {}).get("rows", []) if r["c"] == e["o"]), None)
        if r is None:
            continue
        r["n"] = joinn(r.get("n"), e["text"])
        d.setdefault("notes", [])
        if e["text"] not in d["notes"]:
            d["notes"].append(e["text"])


def landlocked_centre_notes(docs, baci):
    """The pairs whose declared destination or origin is a landlocked trading centre (caveat kind "landlocked-centre", FNCF): the registry text goes to
    the rows of the two countries in the customs tables and to the notes of the page. A group that is the main group of a page is handled by
    registry_caveats(); here the groups that a page holds as an extra table (refined copper), whose tables the registry does not know."""
    for e in baci.caveats.values():
        if e["kind"] != "landlocked-centre":
            continue
        groups = [(cid, g2, stem) for cid, xs in EXTRA_GROUPS.items() for g2, stem, *_ in xs] + \
                 [(cid, g2, HAND_STEMS[g2]) for cid, xs in HAND_GROUPS.items() for g2, _ in xs]
        for cid, g2, stem in groups:
            d = docs.get(cid)
            if g2 != e["group"] or not d:
                continue
            found = False
            for sec, c in (("exports", e["o"]), ("imports", e["d"])):
                t = next((x["table"] for x in d.get("extra") or [] if x["key"] == f"{stem}-{sec}"), None)
                r = next((r for r in (t or {}).get("rows", []) if r["c"] == c), None)
                if r is not None:
                    r["n"] = joinn(r.get("n"), e["text"])
                    found = True
            d.setdefault("notes", [])
            if found and e["text"] not in d["notes"]:
                d["notes"].append(e["text"])


# An importer that is the transit port of a landlocked country in the engine's transit tables (pipeline/freight/gateways/energy.py TRANSIT), where the
# customs record of the importer reads like the landlocked country's own trade: (page, key of the importers table, importer, group of the table,
# the landlocked country). The note is built from that entry (FNCF, review GV6B: Djibouti, 1.64 Mt of two-nutrient compounds in 2024, second importer).
TRANSIT_PORT_ROWS = [("npk", "two-nutrient-imports", "DJI", "npk-two-nutrient", "ETH")]


def transit_port_notes(docs, baci):
    """A row note and a page note for an importer that is the transit port of a landlocked country by a sourced entry of the engine's transit tables:
    what the customs data record (tonnes, rank, share of the world, the same importer ten years earlier, the landlocked country's own recorded
    imports), the entry and its source, and the reading that the tonnes may be that country's cargo declared at the port, which no source here
    establishes. Written only while the engine's entry gives that port for that country."""
    for cid, key, iso, g, land in TRANSIT_PORT_ROWS:
        d = docs.get(cid)
        t = next((x["table"] for x in (d or {}).get("extra") or [] if x["key"] == key), None)
        tr = PT.transit_for(land, PT.segment(g), g)
        if not t or not tr or PT.port(tr[0])["name"] != cname(iso):
            continue
        i = next((k for k, r in enumerate(t["rows"]) if r["c"] == iso), None)
        if i is None:
            continue
        row = t["rows"][i]
        y0 = BACI_YEAR - 9
        before = baci.group(g, y0)
        v0 = before[before["d"] == iso]["t"].sum() / 1e6
        own = baci.group(g, BACI_YEAR)
        own = own[own["d"] == land]["t"].sum() / 1e6
        prev = baci.group(g, BACI_YEAR - 1)
        prev = prev[prev["d"] == land]["t"].sum() / 1e6
        own_text = (f"{cname(land)}'s own recorded imports of this product are {own:.2f} Mt in {BACI_YEAR}" if own >= 0.005 else
                    f"no import of this product by {cname(land)} is recorded in {BACI_YEAR}" + (f", against {prev:.2f} Mt in {BACI_YEAR - 1}" if prev >= 0.005 else ""))
        what = next((w for gg, _, _, w in EXTRA_GROUPS.get(cid, []) if gg == g), g)
        text = (f"Customs data record {row['v']:.2f} Mt of {what} imported by {cname(iso)} in {BACI_YEAR} (rank {i + 1}, {row['v'] / t['world']:.1%} of the world imports), "
                f"against {v0:.2f} Mt in {y0}. {cname(iso)} is the port that the atlas's transit tables give {cname(land)}, which has no coast ({tr[3]}: {'Wikipedia' if tr[1] == 'wikipedia' else tr[1]}, {tr[2]}), "
                f"and {own_text}: some of these tonnes may be cargo for {cname(land)} declared at the port, "
                "a possible reading, not established here")
        row["n"] = joinn(row.get("n"), text)
        d.setdefault("notes", [])
        if text not in d["notes"]:
            d["notes"].append(text + ".")


def metal_row_notes(docs, baci):
    """Notes on single rows of the metal pages (audit C-038 to C-043): trading hubs and re-exporters in the rankings, the republic
    of the Congo, the DR Congo export quotas, and flows priced far below the metal. The cause of a hub effect is a hypothesis, worded
    as one; every number is read from the tables and the customs frame at build time, and a note is written only while its facts hold."""

    def table(cid, sec, key=None):
        d = docs.get(cid) or {}
        if key:
            return next((x["table"] for x in d.get("extra") or [] if x["key"] == key), None)
        return d.get(sec)

    def find(cid, sec, iso, key=None):
        t = table(cid, sec, key)
        rows = (t or {}).get("rows", [])
        i = next((k for k, r in enumerate(rows) if r["c"] == iso), None)
        return (rows[i], i + 1) if i is not None else (None, None)

    def put(cid, sec, iso, text, key=None):
        r, _ = find(cid, sec, iso, key)
        if r is not None:
            r["n"] = joinn(r.get("n"), text)

    def pair(g, o, d, year=BACI_YEAR):
        x = baci.group(g, year)
        return x[(x["o"] == o) & (x["d"] == d)]["t"].sum() / 1e6

    hint = "a possible reading, not established here"
    # copper: Switzerland among the importers of refined copper
    r, k = find("copper", None, "CHE", "refined-imports")
    zm = pair("copper-refined", "ZMB", "CHE")
    # the registry caveat of the pair (landlocked_centre_notes) says it with the shares of both countries: this note stays only without it
    if r and zm >= 0.5 * r["v"] and "copper-refined-zmb-che" not in getattr(baci, "caveats", {}):
        put("copper", None, "CHE", f"rank {k}: {zm:.2f} Mt of it comes from Zambia. Switzerland is a commodity-trading centre, so this may be metal bought by traders "
            f"based there rather than metal used there ({hint})", "refined-imports")
    # aluminium: the Netherlands and Malaysia among the exporters
    r, k = find("aluminium", "exports", "NLD")
    ri, ki = find("aluminium", "imports", "NLD")
    if r and ri:
        put("aluminium", "exports", "NLD", f"rank {k}, and it is also rank {ki} among importers ({ri['v']:.2f} Mt), with {pair('aluminium', 'NLD', 'DEU'):.2f} Mt sent on to Germany: "
            f"part of its exports may be re-exported metal that passed through Dutch ports and warehouses ({hint})")
    r, k = find("aluminium", "exports", "MYS")
    pm = next((x["v"] for x in (table("aluminium", "production") or {}).get("rows", []) if x["c"] == "MYS"), None)
    if r and pm and r["v"] * 1e3 > pm:
        put("aluminium", "exports", "MYS", f"rank {k}: exports ({r['v']:.2f} Mt) are above its smelter output in the USGS table ({pm / 1e3:.2f} Mt). HS 7601 includes alloy ingot, "
            f"which can be made from scrap, and Malaysia receives {pair('aluminium', 'USA', 'MYS'):.2f} Mt from the United States ({hint})")
    # manganese ore: Singapore
    r, k = find("manganese", "imports", "SGP")
    if r and "SGP" not in {x["c"] for x in (table("manganese", "production") or {}).get("rows", [])}:
        put("manganese", "imports", "SGP", f"rank {k}: Singapore is not a manganese producer; it is a trading and transshipment centre, so part of these imports may be ore "
            f"bought or stored there and sold on ({hint})")
    # iron ore: Malaysia and Oman import and export similar tonnages
    for iso, name in (("MYS", "Malaysia"), ("OMN", "Oman")):
        ri, ki = find("iron-ore", "imports", iso)
        re_, ke = find("iron-ore", "exports", iso)
        if ri and re_:
            text = (f"{name} is both an importer (rank {ki}, {ri['v']:.1f} Mt) and an exporter (rank {ke}, {re_['v']:.1f} Mt) of iron ore: ore may be transshipped, stored or "
                    f"blended there and shipped on, which counts the same ore in two countries' trade ({hint})")
            put("iron-ore", "imports", iso, text)
            put("iron-ore", "exports", iso, text)
    # platinum-group metals: the United Arab Emirates
    r, k = find("pgm", "exports", "ARE")
    if r and "ARE" not in {x["c"] for x in (table("pgm", "production") or {}).get("rows", [])}:
        put("pgm", "exports", "ARE", f"rank {k}: the United Arab Emirates is not in the USGS list of platinum-group producers; its exports may be re-exports of metal "
            f"traded and refined there ({hint})")
    # Republic of the Congo: exports of cobalt, priced like DR Congo's
    cb = baci.group("cobalt")
    cog, cod = cb[cb["o"] == "COG"], cb[cb["o"] == "COD"]
    if len(cog) and len(cod):
        uv = lambda x: x["usd"].sum() * 1e3 / x["t"].sum()
        put("cobalt", "exports", "COG", f"{cog['t'].sum() / 1e3:.1f} kt at {uv(cog):,.0f} USD/t, close to DR Congo's {uv(cod):,.0f} USD/t; the Republic of the Congo is not a cobalt producer "
            f"in the USGS table, so some of it may be DR Congo material recorded under the wrong Congo ({hint})")
    # DR Congo: export suspension and quotas
    put("cobalt", "exports", "COD", f"{BACI_YEAR} figure: DR Congo suspended exports until 15 October 2025 and has capped them by quota since 16 October 2025 (see the notes)")
    # flows priced far below the others of their product (USA to Malaysia, 'aluminium'): check K13, wired through the caveat registry


def annotate(docs, eia):
    for cid, c in caveats(docs, eia).items():
        d = docs.get(cid)
        if not d:
            continue
        for sec, text in c.items():
            if sec in ("caveatYears", "caveatPast"):
                continue
            if sec in ("notes", "discrepancies"):
                d.setdefault(sec, [])
                d[sec] += [t for t in text if t not in d[sec]]
            elif d.get(sec):
                add_caveat(d[sec], text)
                if sec in d.get("summary", {}):
                    kf = d["summary"][sec]
                    # a key figure that holds an Atlas estimate keeps the note that says so, and the caveat follows it
                    kf["n"] = joinn(kf.get("n"), text) if kf.get("est") or "Atlas estimate" in kf.get("n", "") or kf.get("n", "").startswith("Atlas conversion of EIA") else text
        # a caveat that holds in some years only (the others hold for every year of the table's series): a past-year table
        # shows it in those years, and `caveatPast` (else `caveatShort`) in the others (web/src/lib/tableYears.ts)
        for key in ("caveatYears", "caveatPast"):
            for sec, v in (c.get(key) or {}).items():
                if (d.get(sec) or {}).get("caveat"):
                    d[sec][key] = v


if __name__ == "__main__":
    sys.exit(main())
