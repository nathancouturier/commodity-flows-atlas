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
    - PSD_MY: the market year before the newest one most crops have (the newest is an early forecast).
    """
    import glob as _g
    by = int(pd.read_csv(os.path.join(CACHE, "baci_flows.csv.gz"), usecols=["year"])["year"].max())
    files = sorted(_g.glob(os.path.join(RAW, "usgs", "MCS*_Commodities_Data.csv")))
    usgs_file = files[-1] if files else os.path.join(RAW, "usgs", "MCS2026_Commodities_Data.csv")
    mcs = int(os.path.basename(usgs_file)[3:7])
    psd_path = os.path.join(RAW, "usda", "psd_csv", "psd_alldata.csv")
    my = 2025
    if os.path.exists(psd_path):
        x = pd.read_csv(psd_path, usecols=["Commodity_Description", "Market_Year"], encoding="latin-1")
        crops = ["Wheat", "Corn", "Oilseed, Soybean", "Rice, Milled", "Cotton", "Sugar, Centrifugal", "Oil, Palm"]
        newest = x[x["Commodity_Description"].isin(crops)].groupby("Commodity_Description")["Market_Year"].max()
        if len(newest):
            my = int(newest.median()) - 1
    return by, str(mcs - 1), usgs_file, my


BACI_YEAR, USGS_YEAR, USGS_FILE, PSD_MY = _latest_inputs()
PSD_LABEL = f"{PSD_MY}/{(PSD_MY + 1) % 100:02d}"
USGS_EDITION = int(USGS_YEAR) + 1
TOP = 12
NFLOWS = 20

QA_WARN = []


def warn(msg):
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
from clean import BULK, CODE_FIX, LAST_DROPPED, XAS, clean as clean_baci  # noqa: E402
import checks as K  # noqa: E402  (labels, names and the records of pipeline/cache/trade_checks.json)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "freight"))
import modes as MD  # noqa: E402  (the mode rule of the lanes: sea, transit, mixed or land)
import ports as PT  # noqa: E402  (sourced transit ports of landlocked countries)
import vessel_rules as VR  # noqa: E402

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


def fig(v, u, y, s, n=None):
    d = {"v": rnd(v), "u": u, "y": y, "s": s}
    if n:
        d["n"] = n
    return d


def ranked(rows, y, s, u, world=None, n=None, top=TOP):
    """rows: list of (iso, value[, note]); returns a Ranked dict (top N by value)."""
    acc = {}
    for r in rows:
        c, v = r[0], r[1]
        if c is None or v is None or not (v > 0):
            continue
        note = r[2] if len(r) > 2 else None
        if c in acc:
            raise SystemExit(f"duplicate row for {c} ({s} {y})")
        acc[c] = (v, note)
    srt = sorted(acc.items(), key=lambda kv: -kv[1][0])[:top]
    out = {"y": y, "s": s, "u": u}
    if world is not None:
        out["world"] = rnd(world)
    out["rows"] = [({"c": c, "v": rnd(v), **({"n": nt} if nt else {})}) for c, (v, nt) in srt]
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
        return None, None, "Customs flows add paddy (HS 1006.10) to milled rice at full weight: the paddy extract (pipeline/cache/baci_rice_forms.csv) is missing."
    f = pd.read_csv(path, dtype={"hs6": str})
    f = f[(f["year"] == BACI_YEAR) & (f["hs6"] == "100610")]
    if f.empty:
        warn(f"rice: no paddy rows for {BACI_YEAR} in baci_rice_forms.csv (run extract_rice_forms.py); flows left at customs weight")
        return None, None, f"Customs flows add paddy (HS 1006.10) to milled rice at full weight: no paddy extract for {BACI_YEAR}."
    rates, world_rate = psd.milling_rates()
    tot = {(r["o"], r["d"]): r["t"] for _, r in baci.group("rice").iterrows()}
    out = {}
    for _, r in f.iterrows():
        k = (r["o"], r["d"])
        t = tot.get(k)
        if not t or r["t"] > t * 1.001:
            continue
        iso = BACI_OVERRIDE.get(r["o"], r["o"])
        rate = rates.get(iso)
        basis = f"the USDA PSD milling rate of {cname(iso)} ({rate:.2f}, market year {PSD_LABEL})" if rate else None
        if rate is None:
            rate = world_rate
            basis = f"the world average USDA PSD milling rate ({rate:.2f}, market year {PSD_LABEL})" if rate else None
        if rate is None:
            continue
        new = t - r["t"] * (1 - rate)
        if (t - new) / t < 0.005:  # under half a percent: the customs figure stands
            continue
        out[k] = (new, f"Atlas estimate, milled equivalent: CEPII BACI {BACI_YEAR} customs weight is {_fmt(t / 1e6)} Mt, of which {_fmt(r['t'] / 1e6)} Mt "
                       f"is paddy (HS 1006.10), converted at {basis}")
    paddy = float(f["t"].sum())
    note = (f"Customs flows cover HS 1006.10 to 1006.40. Paddy ({_fmt(paddy / 1e6)} Mt in {BACI_YEAR}, CEPII BACI) is converted to milled equivalent with the "
            f"USDA PSD milling rate of the exporter, so that flows compare with the milled-basis tables; such flows are marked Atlas estimate. "
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
        rows, missing, other_sum, estimated = [], [], 0.0, False
        for _, r in cty.iterrows():
            if r["Country"] in ("World total",):
                continue
            kind, v = self.parse(r["Value"])
            if r["Country"] == "Other countries":
                if kind == "num":
                    other_sum += v * factor
                continue
            iso = iso_from_name(r["Country"], "usgs")
            if kind == "num":
                rows.append((iso, v * factor))
            elif re.search(r"\w", r["Value"]):  # blank = no figure at all (e.g. refiners that are not miners); W / ranges / words are listed
                missing.append(f"{r['Country']} ({r['Value']})")
            if isinstance(r["Notes"], str) and "Estimated" in r["Notes"]:
                estimated = True
        world, wnote = None, None
        for _, r in wrows.iterrows():
            kind, v = self.parse(r["Value"])
            if kind == "num":
                world = v * factor
            elif kind == "lb":
                world = v * factor
                wnote = f"USGS reports the world total as a lower bound (>{r['Value'].lstrip('>').strip()})"
            if isinstance(r["Notes"], str):
                extra = r["Notes"].replace("Estimated.", "").replace("--", "").strip()
                if extra and "See Appendix" not in extra:
                    wnote = (wnote + "; " if wnote else "") + extra
        return {"rows": [r for r in rows if r[0]], "world": world, "wnote": wnote, "missing": missing,
                "other": other_sum, "estimated": estimated}

    def ranked(self, commodity, detail, u, factor, label, kind="production", full=False):
        """full: list every country USGS gives, then USGS's 'Other countries' line as the field `other` (shown as the last
        row of the table). If the countries and that line add up to more than 2% below the USGS world total, the
        shares are computed on their sum and the note says so."""
        t = self.table(commodity, detail, factor=factor)
        world = t["world"]
        n = [f"USGS MCS {USGS_EDITION}, {label}"]
        if kind == "production" and t["estimated"]:
            n.append(f"{USGS_YEAR} values are USGS estimates")
        sumrows = total_of(t["rows"]) + t["other"]
        if world is None:
            world = sumrows
            n.append("world = sum of reporting countries incl. 'Other countries'")
        else:
            n.append("USGS world total is rounded")
            if sumrows > world * 1.02:
                warn(f"{commodity}/{detail}: sum of countries {sumrows:.0f} > world {world:.0f}")
                n.append("country figures add up to more than the rounded USGS world total")
            elif full and t["other"] and sumrows < world * 0.98:
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
        out = ranked(t["rows"], int(USGS_YEAR), "usgs-mcs", u, world=world, n="; ".join(n), top=max(TOP, len(t["rows"])) if full else TOP)
        if full and t["other"]:
            out["other"] = rnd(t["other"])
        return out, t


# ====================================================================== EIA
class Eia:
    NEED = {("57-1", "TBPD"), ("26-1", "BCM"), ("26-2", "BCM"), ("7-1", "MT"), ("7-2", "MT"), ("7-3", "MT"), ("7-4", "MT"),
            ("7-6", "MST"), ("130-1", "MT"), ("130-2", "MT"), ("130-3", "MT"), ("130-4", "MT"), ("5-2", "TBPD"),
            ("67-2", "MT"), ("62-2", "TBPD"), ("63-2", "TBPD"), ("65-2", "TBPD"), ("66-2", "TBPD"),
            ("14-1", "MT"), ("14-2", "MT"), ("26-4", "BCM"), ("26-3", "BCM"), ("57-1", "MT")}

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
        return ranked(rows, year, "eia-intl", u, world=world, n=n)

    def minus(self, key_total, key_sub, u, factor, label, n_extra):
        """total minus subset per country (thermal coal = all coal minus metallurgical coal)."""
        year = self.latest_year(key_total, key_sub)
        tot = dict(self.country_values(key_total, year))
        sub = {c: v for c, v in self.country_values(key_sub, year)}
        rows = []
        for c, v in tot.items():
            d = v - sub.get(c, 0.0)
            if d < -1e-6:
                warn(f"EIA thermal coal {c}: metallurgical {sub[c]:.0f} > total {v:.0f}; set to 0")
                d = 0
            rows.append((c, d * factor))
        world = (self.s[key_total]["WORL"][year] - self.s[key_sub]["WORL"][year]) * factor
        n = f"EIA International Energy Data, {label}; {n_extra}"
        return ranked(rows, year, "eia-intl", u, world=world, n=n)


# ====================================================================== USDA PSD
class Psd:
    UNITS = {  # commodity -> (unit, factor to that unit from PSD unit, conversion note)
        "Coffee, Green": ("kt", 0.06, "PSD reports 1000 60-kg bags; converted to kt (1000 bags = 60 t)"),
        "Cotton": ("kt", 0.21772434, "PSD reports 1000 480-lb bales; converted to kt (1000 bales = 217.72 t)"),
    }

    def __init__(self):
        d = pd.read_csv(os.path.join(RAW, "usda", "psd_csv", "psd_alldata.csv"), encoding="latin-1",
                        usecols=["Commodity_Description", "Country_Name", "Market_Year", "Calendar_Year", "Month",
                                 "Attribute_Description", "Unit_Description", "Value"])
        d = d[(d["Market_Year"] == PSD_MY) & d["Attribute_Description"].isin(
            ["Production", "Exports", "Imports", "Domestic Consumption", "Domestic Use", "Human Dom. Consumption", "Ending Stocks",
             "TY Exports", "TY Imports", "Milling Rate (.9999)", "Rough Production"])]
        d = d[~d["Unit_Description"].isin(["(PERCENT)"])]
        self.d = d
        self.release = self.revision(d)  # newest revision of the whole file: build log only
        self.cache = {}

    @staticmethod
    def revision(rows):
        rel = rows[["Calendar_Year", "Month"]].drop_duplicates().sort_values(["Calendar_Year", "Month"]).iloc[-1]
        return f"latest revision {int(rel['Calendar_Year'])}-{int(rel['Month']):02d}"

    def release_of(self, commodity):
        """PSD revises each commodity on its own calendar (coffee twice a year, grains monthly): the stamp
        printed with a table is the newest revision month of that commodity's rows for the market year."""
        return self.revision(self.d[self.d["Commodity_Description"] == commodity])

    def has_eu(self, commodity):
        """True when PSD carries a 'European Union' row for the commodity (cotton lists the members instead)."""
        x = self.d[self.d["Commodity_Description"] == commodity]
        return bool((x["Country_Name"] == "European Union").any())

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
        n = [f"USDA PSD, {commodity}, {what}, market year {PSD_LABEL} ({self.release_of(commodity)})"]
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
        return ranked(rows, PSD_LABEL, "usda-psd", unit, world=world, n="; ".join(n)), unit


# ====================================================================== BACI
class Baci:
    def __init__(self):
        df = pd.read_csv(os.path.join(CACHE, "baci_flows.csv.gz"))
        df = clean_baci(df)  # shared rules with build_lanes.py (pipeline/trade/clean.py)
        df["est"] = df["imputed"]
        ratio = df["uvr"]
        susp = (df["t0"] > 0) & ~df["imputed"] & df["uv"].notna() & ((ratio < 0.05) | (ratio > 20))
        df["susp"] = susp
        df["t_susp"] = df["t"].where(susp, 0.0)
        fix = df["imputed"]
        df["t_est"] = df["t"].where(fix, 0.0)
        self.df = df
        self.dropped = list(LAST_DROPPED)  # rows that clean() dropped, for QA.md
        self._modes = {}
        self.lanes = {}
        ld = os.path.join(DATA, "freight", "lanes")
        for f in os.listdir(ld):
            if f.endswith(".json"):
                j = json.load(open(os.path.join(ld, f), encoding="utf-8"))
                # flows link to the lanes of the main set only (a history lane has no latest-year flow)
                self.lanes[j["group"]] = {"ids": {l["id"] for l in j["lanes"] if l["set"] == "main"}, "seaborne": j["seaborne"],
                                          "mixed": j.get("mixed"), "est": j.get("est"), "years": j["years"], "unit": j["unit"], "y": j["y"]}
        try:
            self.caveats = json.load(open(os.path.join(DATA, "freight", "caveats.json"), encoding="utf-8"))
        except (OSError, ValueError):
            self.caveats = {}

    def mode(self, o, d, g):
        """Mode of a pair under the rule of the lanes (pipeline/freight/modes.py): (kind, transit row or None), or
        (None, None) for a group without a mode (precious metals: not modelled)."""
        k = (o, d, g)
        if k not in self._modes:
            m = MD.mode_of(o, d, g)
            tr = None
            if m and m.kind == "transit":
                end = o if not MD.coastal(o) else d
                rows = PT.TRANSIT.get(end) or {}
                row = rows.get(MD.FAMILY.get(g)) or rows.get("default")
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

    def ranked(self, g, side, u, div, what, extra=None):
        d = self.group(g)
        col = "o" if side == "exports" else "d"
        agg = d.groupby(col).agg(t=("t", "sum"), te=("t_est", "sum"), ts=("t_susp", "sum"), usd=("usd", "sum")).sort_values("t", ascending=False)
        world = agg["t"].sum() / div
        est_share = agg["te"].sum() / agg["t"].sum() if agg["t"].sum() else 0
        rows = []
        for code, r in agg.head(TOP + 5).iterrows():
            iso = None if code in EXTRA_CODES else self.iso(code)  # ranked tables (and country profiles) list countries of the index only
            es = r["te"] / r["t"] if r["t"] else 0
            note = None
            if code in BACI_OVERRIDE:
                note = f"BACI code {code} ('Other Asia, nes'), reported as Taiwan"
            if es >= 0.10:
                note = (note + "; " if note else "") + f"{es * 100:.0f}% of tonnage estimated from value"
            ss = r["ts"] / r["t"] if r["t"] else 0
            if ss >= 0.10:
                note = (note + "; " if note else "") + f"{ss * 100:.0f}% of tonnage from flows with implausible unit values (not corrected: below the 50 M USD rule)"
            rows.append((iso, r["t"] / div, note))
        n = [f"CEPII BACI HS92 {what}, {BACI_YEAR}, all transport modes, gross weight",
             "world = sum of all reported flows in the Atlas BACI extract (flows below 1,000 t and 1 M USD omitted)"]
        if est_share >= 0.01:
            n.append(f"{est_share * 100:.0f}% of world tonnage estimated from value where missing or inconsistent")
        if extra:
            n.append(extra)
        return ranked(rows, BACI_YEAR, "baci", u, world=world, n="; ".join(n)), est_share

    def flows(self, g, u, div, lane_group=None, only_exporters=None, mode_all=None, n_all=None, adjust=None):
        """adjust: {(o, d): (tonnes, note)} replaces the customs tonnage of a pair by an Atlas figure
        (source id "atlas", with the note) before the flows are ranked."""
        self.last_susp = []
        d = self.group(g)
        if only_exporters:
            d = d[d["o"].isin(only_exporters)]
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
            f = {"o": o, "d": de, "v": rnd(r["t"] / div), "u": u, "y": BACI_YEAR, "s": "baci"}
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
            elif kind == "mixed" and not mode_all:
                notes.append("customs total for all modes: this trade moves both by sea and overland and the split is not known")
            if r["est"]:
                # an Atlas estimate: the tonnage is computed from the declared value (pipeline/trade/clean.py)
                f["s"], f["est"] = "atlas", True
                notes.append(r["enote"] if isinstance(r.get("enote"), str) and r["enote"] else "Atlas estimate: tonnage estimated from declared value")
            if notes:
                f["n"] = "; ".join(notes)
            cv = self.caveat_of(g, r["o"], r["d"])
            if cv:
                f["caveat"] = cv
            if r["susp"]:
                ref = "tonne-weighted median" if g in BULK else "median"
                msg = (f"reported tonnage implies {r['usd'] * 1000 / r['t0']:,.0f} USD/t, i.e. {r['uvr']:.4f}x the {g} group-year {ref} unit value: "
                       f"possible misreport, kept because the flow is below the 50 M USD correction rule")
                f["n"] = (f["n"] + "; " if "n" in f else "") + msg
                self.last_susp.append(f"{o}->{de}: {rnd(r['t'] / div)} {u} of {g} in {BACI_YEAR} ({msg}).")
            if n_all:
                f["n"] = (f["n"] + "; " if "n" in f else "") + n_all
            if isinstance(r["adj"], str):
                f["s"] = "atlas"
                f["n"] = r["adj"] + ("; " + f["n"] if "n" in f else "")
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
        n = (f"seaborne subset of BACI flows ({g}) under the atlas's mode rule (data/freight/lanes/{g}.json): trade by sea, "
             "or by sea through a foreign port for a landlocked country")
        mx = (lg.get("mixed") or [0])[-1]
        if mx and mx >= 0.05:
            n += f"; {_fmt(mx)} Mt that move both by sea and overland (split not known) are not in it"
        if lg.get("est") and lg["est"] >= 0.01:
            n += f"; {lg['est'] * 100:.0f}% of this tonnage estimated from value"
        if label:
            n += "; " + label
        return fig(v, "Mt", lg["y"], "baci", n)

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
                world = v / 1000
                continue
            if r["area"] in FAO_AGG or m49 >= 900:
                continue
            iso = fo_override.get(m49) or codes.get(m49)
            if not iso or iso not in ISO_SET:
                iso = NAME2ISO.get(fold(r["area"])) or OVERRIDE.get(fold(r["area"]))
            if not iso or iso not in ISO_SET:
                UNKNOWN["faostat"].add(f"{r['area']} ({r['m49']})")
                continue
            rows.append((iso, v / 1000, "FAO flag: " + r["flag"] if r["flag"] in ("E", "X", "I") else None))
    n = (f"FAOSTAT QCL, cocoa beans (item 661), production, {year}; tonnes converted to kt; world total as published by FAO "
         "(note flags: E estimated, I imputed, X from international organisations; A official)")
    return ranked(rows, int(year), "faostat", "kt", world=world, n=n)


FAO_AGG = {"Africa", "Americas", "Asia", "Europe", "Oceania", "Eastern Africa", "Middle Africa", "Western Africa", "Southern Africa",
           "Northern Africa", "Central America", "Caribbean", "South America", "Northern America", "Central Asia", "Eastern Asia",
           "Southern Asia", "South-eastern Asia", "Western Asia", "Eastern Europe", "Northern Europe", "Southern Europe",
           "Western Europe", "Melanesia", "Micronesia", "Polynesia", "Australia and New Zealand", "European Union (27)",
           "Land Locked Developing Countries (LLDCs)", "Least Developed Countries (LDCs)", "Small Island Developing States (SIDS)",
           "Low Income Food Deficit Countries (LIFDCs)", "Net Food Importing Developing Countries (NFIDCs)"}


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
    "coffee": ("coffee", KT, "green coffee (HS 090111, 090112)"),
    "cocoa": ("cocoa", KT, "cocoa beans (HS 1801)"),
    "cotton": ("cotton", KT, "raw cotton (HS 5201)"),
    "palm-oil": ("palm-oil", MT, "palm oil (HS 1511)"),
    "rapeseed": ("rapeseed", MT, "rapeseed (HS 1205)"),
    "potash": ("potash", MT, "potassium chloride (HS 310420)"),
    "phosphate": ("phosphate-rock", MT, "natural phosphates (HS 2510)"),
    "urea": ("urea", MT, "urea (HS 310210)"),
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
}
PSD_WHAT = {
    "wheat": "wheat", "corn": "corn", "soybeans": "soybeans", "soymeal": "soybean meal", "soyoil": "soybean oil",
    "rice": "milled rice", "sugar": "centrifugal sugar (raw value)", "coffee": "green coffee (all forms, green-bean equivalent)",
    "cotton": "cotton", "palm-oil": "palm oil", "rapeseed": "rapeseed",
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
    "cobalt": ("contained cobalt", "intermediates and metal, gross weight"),
    "rare-earths": ("REO equivalent", "metals and compounds, gross weight"),
    "manganese": ("manganese content", "ore, gross weight"),
    "uranium": ("contained uranium", "ores and compounds, gross weight"),
    "potash": ("K2O content", "potassium chloride, product weight"),
    "urea": ("ammonia, nitrogen content", "urea, product weight"),
}
# second trade tables (key prefix -> basis); their titles already name the product
EXTRA_BASIS = {"refined": "gross weight", "int": "gross weight", "alumina": "gross weight", "metal": "gross weight"}

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
}


# USGS tables listed in full, with the line "Other countries" as the last row: (commodity id, section)
FULL_TABLE = {("steel", "production"), ("gold", "production"), ("bauxite", "refinery")}

# Headline figures of publishers whose tables are not free to copy: one world total each, cited with publisher, year and link
# (publisher, publication, figure, unit, year, page read, id in data/sources.json)
WORLDSTEEL = ("World Steel Association", "press release of 23 January 2026", 1849.4, "Mt", 2025,
              "https://worldsteel.org/media/press-releases/2026/december-2025-crude-steel-production-2025-global-crude-steel-production/", "worldsteel")
WGC_MINE = ("World Gold Council", "Gold Demand Trends, full year 2025 (supply)", 3671.6, "t", 2025,
            "https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-full-year-2025/supply", "wgc")
# Official or press figures read on a page, quoted in a discrepancy note: Guinea's exports and China's imports of tin concentrate
GUINEA_EXPORTS = ("Reuters, from official Guinean data (Hellenic Shipping News, 26 January 2026)", 182.8, 2025,
                  "https://www.hellenicshippingnews.com/guineas-bauxite-exports-jump-25-to-183-million-tons-in-2025-on-chinese-demand/")
CHINA_TIN_ORE = ("SMM (Shanghai Metals Market), 23 December 2024, quoting China's General Administration of Customs", 150.8, 75.3,
                 "https://news.metal.com/en/newscontent/103438801")
BENCHMARK_COBALT = "https://source.benchmarkminerals.com/article/drc-to-lift-cobalt-export-ban-and-impose-quotas-through-2027"

_HS4 = {}


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
        """Fig from the world total of a Ranked."""
        if r is None or r.get("world") is None:
            return
        d["summary"][key] = fig(r["world"], r["u"], r["y"], r["s"], (label or r.get("n")))

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

        # ------------------------------------------------------------ energy
        if cid == "crude-oil":
            d["production"] = eia.ranked(("57-1", "TBPD"), "kb/d", 1.0, "crude oil including lease condensate production")
            g = add_baci_trade(d, cid, notes, disc)
            summ(d, "production", d["production"], "EIA crude oil including lease condensate, world")
            summ(d, "exports", d["exports"], "sum of all BACI crude oil flows, tonnes (all modes)")
            oil_demand(d)
            seaborne(d, g)
            notes += [
                "Production is in kb/d (EIA); trade tables are in Mt/year (BACI tonnage). Conversion depends on grade, so none is applied.",
                "Oil demand is EIA petroleum and other liquids consumption: all liquids, not crude alone. The same table is shown under refined products.",
                "No proved-reserves series exists in the EIA bulk file used (INTL.txt).",
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
            notes.append("EIA refined-product production series end in 2014 and are not used; no production table.")
        elif cid == "lng":
            g = add_baci_trade(d, cid, notes, disc)
            summ(d, "exports", d["exports"], "sum of all BACI LNG flows (HS 271111), tonnes")
            seaborne(d, g)
            notes += ["LNG volumes are in Mt (1 Mt LNG is about 1.36 bcm of gas); no production table: liquefaction output is not in the loaded sources."]
        elif cid == "natural-gas":
            d["production"] = eia.ranked(("26-1", "BCM"), "bcm", 1.0, "dry natural gas production")
            d["consumption"] = eia.ranked(("26-2", "BCM"), "bcm", 1.0, "dry natural gas consumption")
            g = add_baci_trade(d, cid, notes, disc)
            for f in d["flows"]:
                f["mode"] = "pipeline"
            summ(d, "production", d["production"])
            summ(d, "consumption", d["consumption"])
            summ(d, "exports", d["exports"], "sum of all BACI gaseous natural gas flows (HS 271121), tonnes; excludes LNG")
            notes += ["Trade tables cover gas in gaseous state (HS 271121: pipeline) in Mt; LNG is under 'lng'. Flows are shown as pipeline mode.",
                      "No proved-reserves series exists in the EIA bulk file used (INTL.txt)."]
        elif cid == "lpg":
            d["consumption"] = eia.ranked(("67-2", "MT"), "Mt", 1e-3, "liquefied petroleum gases consumption (1000 metric tons converted to Mt)")
            g = add_baci_trade(d, cid, notes, disc)
            summ(d, "consumption", d["consumption"])
            summ(d, "exports", d["exports"])
            seaborne(d, g)
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
                        r["n"] = f"of which lignite {_fmt(lv)} Mt ({min(lv / r['v'], 1):.0%})"
                if lw:
                    t["n"] += f"; includes lignite: {_fmt(lw * 1e-3)} Mt of the world total ({lw * 1e-3 / t['world']:.0%}, EIA lignite {word})"
                set_basis(t, "incl. lignite")
            py = d["production"]["y"]
            lig = eia.ranked(("14-1", "MT"), "Mt", 1e-3, "lignite production; 1000 metric tons converted to Mt", year=py,
                             n_extra="these tonnages are included in the thermal coal production table")
            extra_first.append({"key": "lignite-production", "title": f"Lignite producers, EIA {py} (included above)", "table": lig})
            tr = eia.ranked(("7-6", "MST"), "Mt", 0.90718474, "coal reserves (all ranks, not split thermal/metallurgical); million short tons converted to Mt")
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
            for r in tr["rows"]:
                code = _iso_to_eia(r["c"])
                s0 = since(code)
                if s0 < rev:
                    r["n"] = f"EIA value unchanged since {s0}"
                prev = ser[code].get(s0 - 1)
                if prev and ser[code][s0] / prev >= 10:  # one revision multiplied the estimate tenfold or more
                    flag = (f"{cname(r['c'])}: EIA raised its estimate from {_fmt(prev * 0.90718474)} Mt to {_fmt(ser[code][s0] * 0.90718474)} Mt in {s0}, "
                            f"a {ser[code][s0] / prev:.0f}-fold step, and has not changed it since; treat this rank with caution")
                    r["n"] = flag.split(": ", 1)[1]
                    flags.append(flag)
            tr["y"] = rev
            tr["n"] += f"; last revised by EIA in {rev} and repeated unchanged to {y} (reserve estimates are not revised every year)"
            for flag in flags:
                add_caveat(tr, flag + ".")
            d["reserves"] = tr
            g = add_baci_trade(d, cid, notes, disc, extra="HS 2701 and 2702 do not separate thermal from metallurgical coal: figures cover all coal")
            allcoal = {"exports": d["exports"], "imports": d["imports"]}  # customs tables, all coal: same basis as flows and lanes
            for f in d["flows"]:
                f["n"] = (f["n"] + "; " if "n" in f else "") + "all coal (HS 2701, 2702): thermal and metallurgical not separated"
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
            # EIA vs BACI exports
            disc += _compare("exports", eia, ("7-4", "MT"), 1e-3, baci, "coal", 1e6, "Mt", "EIA coal exports", BACI_YEAR)
        elif cid == "met-coal":
            d["production"] = eia.ranked(("130-1", "MT"), "Mt", 1e-3, "metallurgical coal production; 1000 metric tons converted to Mt")
            d["consumption"] = eia.ranked(("130-2", "MT"), "Mt", 1e-3, "metallurgical coal consumption; 1000 metric tons converted to Mt")
            d["exports"] = eia.ranked(("130-4", "MT"), "Mt", 1e-3, "metallurgical coal exports; 1000 metric tons converted to Mt")
            d["imports"] = eia.ranked(("130-3", "MT"), "Mt", 1e-3, "metallurgical coal imports; 1000 metric tons converted to Mt")
            d["flows"] = baci.flows("coal", "Mt", 1e6, only_exporters=["AUS", "USA", "CAN", "MNG", "RUS"],
                                    n_all="all coal (HS 2701) from a main metallurgical-coal exporter; thermal and metallurgical not separated")
            disc.extend(baci.last_susp)
            summ(d, "production", d["production"])
            summ(d, "consumption", d["consumption"])
            summ(d, "exports", d["exports"])
            for sec, word in (("production", "Top producers"), ("consumption", "Top consumers"), ("exports", "Top exporters"), ("imports", "Top importers")):
                name_it(d, sec, f"{word} — metallurgical coal, EIA {d[sec]['y']}")
            name_it(d, "flows", f"Main flows — all coal, customs data {BACI_YEAR}")
            notes += ["Flows are BACI coal flows (HS 2701) from AUS, USA, CAN, MNG and RUS: HS 2701 does not separate thermal from metallurgical coal, so the volumes include thermal coal.",
                      "Seaborne total omitted: the lane file covers all coal and cannot be split.",
                      "Exports/imports tables are EIA metallurgical coal (not BACI)."]
        elif cid == "uranium":
            d["production"] = wna_uranium()
            g = add_baci_trade(d, cid, notes, disc)
            summ(d, "production", d["production"])
            summ(d, "exports", d["exports"], "uranium ores and natural uranium compounds (HS 261210, 284410), gross weight")
            notes += ["Trade is gross weight of uranium ores and natural uranium compounds in kt, not tonnes of contained uranium; enriched uranium and fuel are not covered.",
                      "No reserves or consumption table: neither is in the loaded sources."]
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
            if "reserves" in d:
                summ(d, "reserves", d["reserves"])
            summ(d, "exports", d["exports"])
            seaborne(d, g, f"main bulk group used: {g}" if cid in ("copper", "nickel", "zinc", "bauxite", "phosphate") else None)
        elif cid == "pgm":
            _pgm(d, us, baci, notes, summ, seaborne, add_baci_trade, disc, cid)
        # ------------------------------------------------------------ softs
        elif cid == "cocoa":
            d["production"] = faostat_cocoa()
            g = add_baci_trade(d, cid, notes, disc)
            summ(d, "production", d["production"])
            summ(d, "exports", d["exports"], "cocoa beans (HS 1801), BACI")
            seaborne(d, g)
            notes += [f"Cocoa is not in USDA PSD: exports and imports are BACI cocoa beans (calendar {BACI_YEAR}); production is FAOSTAT {d['production']['y']}.",
                      "No consumption table: grindings data are not in the loaded sources."]
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
            notes.append(f"Flows are BACI calendar-{BACI_YEAR} customs flows; ranked trade tables are USDA PSD market-year {PSD_LABEL} (trader reference). Years differ.")
            if cid == "coffee":
                notes.append("PSD coffee exports/imports include roasted and soluble coffee in green-bean equivalent; BACI flows are green beans only (HS 0901.11/12).")
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
                             "from the HS4 extract (pipeline/cache/hs4_exports.csv.gz), without the cleaning rules of the other trade tables; not part of the steel totals above")
                extra.append({"key": "tubes-exports", "title": "Tube and pipe exporters (HS 7304 to 7306, not in the totals above)", "table": set_basis(t, "gross weight")})
        if cid in PSD:
            com = PSD[cid][0]
            try:
                t, _ = psd.ranked(com, "Ending Stocks", f"{PSD_WHAT[cid]} ending stocks")
                extra.append({"key": "stocks", "title": "Ending stocks", "table": t})
            except SystemExit:
                pass
        if extra:
            d["extra"] = extra

        # lead/tin/refined copper etc: side notes with BACI trade of the second group
        if cid == "copper":
            notes.append(_note_group(baci, "copper-refined", "Refined copper (HS 7403, 7402)"))
            notes.append("Trade tables are copper ores and concentrates in gross weight (Mt), not contained copper; USGS production is contained copper (kt Cu). 'refinery' is an extra field: USGS refined copper production.")
        elif cid == "bauxite":
            notes.append(_note_group(baci, "alumina", "Alumina (HS 281820)"))
            notes.append("USGS production and reserves are dry tonnes; the refinery table is USGS alumina refinery production in calcined-equivalent weight (Mt), "
                         "listed for every country USGS names.")
            gin = next((r["v"] for r in d["production"]["rows"] if r["c"] == "GIN"), None)
            if gin:
                gp, gv, gy, gurl = GUINEA_EXPORTS
                disc.append(f"Guinea {gy}: the USGS estimate of bauxite mined is {_nf(gin)} Mt, {gin / d['production']['world']:.0%} of the world total, but Guinea's exports alone "
                            f"were reported at {gv} Mt for {gy} ({gp}, {gurl}), which is more than USGS estimates it mined. The USGS production figure and Guinea's "
                            f"share of the world total are therefore probably understated.")
            idn_prod = dict(us.table("Alumina", "Alumina, refinery production", year=str(BACI_YEAR))["rows"]).get("IDN")
            idn_exp = baci.totals("alumina", "exports").get("IDN")
            if idn_prod and idn_exp and idn_exp > idn_prod:
                disc.append(f"Indonesia, alumina {BACI_YEAR}: customs data (BACI, HS 281820, gross weight) record {idn_exp:.2f} Mt of exports (rank "
                            f"{1 + sum(1 for v in baci.totals('alumina', 'exports').values() if v > idn_exp)} among exporters), against a USGS alumina refinery output of {idn_prod:.2f} Mt "
                            f"(calcined-equivalent weight) for {BACI_YEAR}. The two sources are on different bases and the cause is not established here; "
                            "the exporters table follows customs data.")
        elif cid == "nickel":
            notes.append(_note_group(baci, "nickel-int", "Nickel intermediates and unwrought nickel (HS 7501, 7502)"))
            notes.append("Trade tables are nickel ores and concentrates in gross weight (Mt); production and reserves are contained nickel (kt Ni).")
        elif cid == "zinc":
            notes.append(_note_group(baci, "zinc-metal", "Unwrought zinc (HS 7901)"))
            notes.append("Trade tables are zinc ores and concentrates in gross weight (Mt); production and reserves are contained zinc (kt Zn).")
        elif cid == "lead":
            notes.append(_note_group(baci, "lead-metal", "Unwrought lead (HS 7801)"))
            notes.append("Trade tables are lead ores and concentrates in gross weight (Mt); production and reserves are contained lead (kt Pb). No lead lanes exist (no seaborne figure).")
        elif cid == "tin":
            notes.append(_note_group(baci, "tin-ore", "Tin ores and concentrates (HS 2609)"))
            notes.append("Trade tables are unwrought tin (HS 8001, alloyed or not; waste and scrap, HS 8002, are not included) in kt; production and reserves are contained tin (t Sn). "
                         "No tin lanes exist (no seaborne figure).")
            ranks = [r["c"] for r in d["production"]["rows"]]
            if "MMR" in ranks:
                mmr = d["production"]["rows"][ranks.index("MMR")]["v"]
                notes.append(f"Myanmar ranks {ranks.index('MMR') + 1} in the USGS production table ({_nf(mmr)} t Sn in {d['production']['y']}); "
                             "mining in Wa State, its main tin area, was suspended from 1 August 2023 (see the events).")
            tin = baci.group("tin-ore", 2024)
            mm = tin[(tin["o"] == "MMR") & (tin["d"] == "CHN")]["t"].sum() / 1e3
            cn = tin[tin["d"] == "CHN"]["t"].sum() / 1e3
            sp, sworld, smmr, surl = CHINA_TIN_ORE
            if cn and mm < 0.1 * smmr:
                disc.append(f"Tin concentrate from Myanmar to China, 2024: customs data (BACI, HS 2609) record {mm:.1f} kt from Myanmar and {cn:.1f} kt for China's imports from all origins. "
                            f"Chinese customs figures reported by {sp}, give about {sworld} kt of tin ores and concentrates imported in January to November 2024, {smmr} kt of it from Myanmar "
                            f"({surl}). The Myanmar flow is missing from the BACI extract and the world figure for tin concentrate is probably too low; the cause is not established here. "
                            "Comparing with China's own import declarations (UN Comtrade) needs an API key that the atlas does not have.")
            cog = tin[tin["o"] == "COG"]
            cod = tin[tin["o"] == "COD"]
            listed = {r[0] for r in us.table("Tin", "Mine production")["rows"]}
            if len(cog) and len(cod) and "COG" not in listed:
                notes.append(f"Republic of the Congo is recorded as an exporter of tin concentrate ({cog['t'].sum() / 1e3:.1f} kt in 2024, "
                             f"{cog['usd'].sum() * 1e3 / cog['t'].sum():,.0f} USD/t) but is not a tin producer in the USGS table, while DR Congo is "
                             f"({cod['usd'].sum() * 1e3 / cod['t'].sum():,.0f} USD/t). Relabelling of DR Congo material is a possible cause; it is not established here.")
        elif cid == "phosphate":
            notes.append(_note_group(baci, "dap", "DAP (HS 310530)"))
            notes.append("Trade tables are natural phosphates (HS 2510), gross weight; USGS production is marketable phosphate rock.")
        elif cid == "lithium":
            notes.append("Trade is lithium carbonate and hydroxide/oxide in gross weight (kt); spodumene concentrate has no HS6 code. USGS production is contained lithium (t Li), so units differ.")
        elif cid == "cobalt":
            ore, mat = hs4_exports(["2605"]), hs4_exports(["8105"])
            if ore and mat:
                notes.append(f"Trade is in gross weight (kt), mostly HS 8105 (mattes, intermediate products such as crude hydroxide, unwrought cobalt, scrap and powders): "
                             f"ores and concentrates (HS 2605) are only {sum(ore.values()) / 1e3:.0f} kt of the {sum(ore.values()) / 1e3 + sum(mat.values()) / 1e3:.0f} kt exported by all countries "
                             f"in {BACI_YEAR} (HS4 extract). USGS production is contained cobalt (t Co), so the two are not comparable.")
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
            notes.append(f"USGS lists {len(pr['rows'])} producing countries; Italy, Taiwan, Mexico, Indonesia, Canada, France and Spain, among others, are in its 'Other countries' line.")
            wp, wdoc, wv, wu, wy, wurl, _ = WORLDSTEEL
            disc.append(f"Crude steel production {wy}: the USGS estimate is {_nf(pr['world'])} {pr['u']} for the listed countries and 'Other countries' "
                        f"(USGS rounds its world total to {_nf(us.table('Iron And Steel', 'Raw steel')['world'])} {pr['u']}); the {wp} reports {wv:,} {wu} of world crude steel "
                        f"production for {wy} ({wdoc}, {wurl}). The table shows the USGS figures, which come by country; the {wp}'s own tables are not copied.")
            d["summary"]["production"]["n"] += f"; {wp}: {wv:,} {wu} in {wy} (see the discrepancies)"
        elif cid in ("gold", "silver"):
            disc.append(_prec_disc(d, cid))
            notes.append("Trade tonnage in BACI is frequently missing for precious metals and is estimated from value (see percentage in the table note); treat flows as indicative.")
            if cid == "gold":
                pr = d["production"]
                wp, wdoc, wv, wu, wy, wurl, _ = WGC_MINE
                disc.append(f"World mine production {wy}: the USGS estimate is {_nf(pr['world'])} {wu} (rounded); the {wp} reports {wv:,} {wu} ({wdoc}, {wurl}), "
                            f"so the USGS total is {1 - pr['world'] / wv:.0%} lower. The {wp} describes its {wy} figure as subject to revision; its own tables are not copied.")
                notes.append(f"The table lists the {len(pr['rows'])} countries USGS names; its 'Other countries' line ({_nf(pr['other'])} {pr['u'].split()[0]}, "
                             f"{pr['other'] / pr['world']:.0%} of the total) covers the rest, for instance Mali, Burkina Faso, Tanzania, Colombia and Papua New Guinea.")
        elif cid == "iron-ore":
            notes.append("USGS production is usable ore (gross weight); reserves are crude ore. Iron-content figures (Australia ~600 Mt Fe in 2025) are in the USGS file but not shown.")
        elif cid == "manganese":
            notes.append("Trade is manganese ore (HS 2602), gross weight (Mt); USGS production is shown in kt as in the USGS table.")
        elif cid == "urea":
            notes.append("Production proxy is ammonia plant output in nitrogen content (USGS); urea output is not in the loaded sources. Trade is urea (HS 310210), product weight.")
        elif cid == "potash":
            notes.append("USGS production/reserves are K2O equivalent; trade is potassium chloride (HS 310420), product weight.")

        if cid in BASIS:
            pb, tb = BASIS[cid]
            for sec in ("production", "reserves"):
                set_basis(d.get(sec), pb)
            for sec in ("exports", "imports"):
                set_basis(d.get(sec), tb)
            for x in d.get("extra") or []:
                set_basis(x["table"], EXTRA_BASIS.get(x["key"].split("-")[0]))
            if cid in ("potash", "urea"):
                # nutrient tonnes next to product tonnes: say so in every title and KPI of the page
                what = "Ammonia producers" if cid == "urea" else "Top producers"
                name_it(d, "production", f"{what} — {pb.split(', ')[-1]}", f"{'Ammonia' if cid == 'urea' else 'World'} production ({pb.split(', ')[-1]})")
                if "reserves" in d:
                    name_it(d, "reserves", f"Reserves — {pb}", f"World reserves ({pb})")
                name_it(d, "exports", f"Top exporters — {tb}", f"World exports ({tb.split(', ')[-1]})")
                name_it(d, "imports", f"Top importers — {tb}")

        notes = [n for n in notes if n]
        if notes:
            d["notes"] = notes
        if disc:
            d["discrepancies"] = disc
        docs[cid] = d

    check_unknown()

    # ------------------------------------------------------------ editorial caveats (from the data audit)
    annotate(docs, eia)
    registry_caveats(docs, baci)

    # ------------------------------------------------------------ write
    HAS = ["production", "reserves", "consumption", "exports", "imports", "flows"]
    for e in index:
        d = docs[e["id"]]
        for k in ("production", "reserves", "consumption", "exports", "imports", "flows"):
            if k in d and not d[k]:
                raise SystemExit(f"{e['id']}: empty {k}")
        mine = [k for k in HAS if k in d]
        e["has"] = mine + [h for h in e.get("has", []) if h not in HAS]
        # field order
        order = ["id", "summary", "kpis", "labels", "production", "refinery", "reserves", "consumption", "exports", "imports", "extra", "flows", "notes", "discrepancies"]
        dd = {k: d[k] for k in order if k in d}
        with open(os.path.join(OUT, e["id"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(dd, f, indent=1, ensure_ascii=False)
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1, ensure_ascii=False)
    update_sources()
    write_qa(index, docs, baci)
    print("wrote", len(docs), "commodity files")


def _iso_to_eia(iso):
    return "XKS" if iso == "KOS" else iso


def _note_group(baci, g, label):
    ex = baci.totals(g, "exports")
    top = sorted(ex.items(), key=lambda kv: -kv[1])[:3]
    world = sum(ex.values())
    unit_n = "Mt"
    names = ", ".join(f"{baci.iso(c)} {v:.2f} Mt" for c, v in top)
    return (f"{label}, {BACI_YEAR} (BACI, baci): world {world:.2f} Mt gross weight; top exporters {names}.")


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


def _psd_vs_baci(psd_obj, baci, cid, com, ex_attr, group):
    """PSD market year 2024/25 isn't loaded (only 2025/26); compare the 2025/26 PSD with BACI 2024 only at the world level."""
    out = []
    unit, conv, rows, world = psd_obj.table(com, ex_attr)
    div = {"kt": 1e3, "Mt": 1e6}[unit]
    bw = baci.group(group)["t"].sum() / div
    if bw and abs(world / bw - 1) > 0.15:
        eu = psd_obj.has_eu(com)
        out.append(f"World exports: USDA PSD {PSD_LABEL} {world:.1f} {unit} (sum of reporting countries{', EU excl. intra-trade' if eu else ''}) vs BACI {BACI_YEAR} {bw:.1f} {unit} "
                   f"({(world / bw - 1) * 100:+.0f}%); different year and basis (marketing year vs calendar year{'; BACI includes intra-EU trade, PSD does not' if eu else ''}); PSD shown in the table.")
    return out


def _prec_disc(d, cid):
    ex, pr = d["exports"], d["production"]
    return (f"BACI world exports {ex['world']:,.0f} {ex['u']} ({BACI_YEAR}) are {ex['world'] / pr['world']:.1f}x USGS world mine production "
            f"{pr['world']:,.0f} {pr['u']} ({pr['y']}): trade counts refined/recycled metal and re-exports between hubs several times and is not comparable with mine output; "
            "USGS used for production, BACI for trade.")


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
    d["production"] = ranked(rows, int(USGS_YEAR), "usgs-mcs", "t", world=world, n=n)
    res = us.table("Platinum-Group Metals", "PGM reserves", factor=1e-3)
    rn = f"USGS MCS {USGS_EDITION}, platinum-group metals reserves, PGM content (kg converted to t); USGS world total is rounded"
    if res["wnote"]:
        rn += "; " + res["wnote"]
    d["reserves"] = ranked(res["rows"], int(USGS_YEAR), "usgs-mcs", "t", world=res["world"] if res["world"] else total_of(res["rows"]) + res["other"], n=rn)
    g = add_baci_trade(d, cid, notes, disc)
    summ(d, "production", d["production"])
    summ(d, "reserves", d["reserves"])
    summ(d, "exports", d["exports"])
    seaborne(d, g)
    disc.append(_prec_disc(d, cid))
    notes.append("Trade tonnage in BACI is frequently missing for precious metals and is estimated from value (see percentage in the table note); treat flows as indicative.")
    notes.append("Production is platinum plus palladium only (USGS gives no rhodium/ruthenium/iridium/osmium by country); the index unit (kg) is shown here in t.")


# ====================================================================== sources, QA
def update_sources():
    p = os.path.join(DATA, "sources.json")
    src = json.load(open(p, encoding="utf-8"))
    have = {s["id"] for s in src}
    new = [
        {"id": "eia-intl", "name": "EIA International Energy Data", "publisher": "U.S. Energy Information Administration",
         "url": "https://www.eia.gov/international/data/world", "licence": "Public domain (US Government)", "update": "annual, partial monthly"},
        {"id": "faostat", "name": "FAOSTAT Crops and livestock products (QCL)", "publisher": "Food and Agriculture Organization of the United Nations",
         "url": "https://www.fao.org/faostat/en/data/QCL", "licence": "CC BY 4.0", "update": "annual"},
        {"id": "wna", "name": "World Nuclear Association: World Uranium Mining Production", "publisher": "World Nuclear Association",
         "url": "https://world-nuclear.org/information-library/nuclear-fuel-cycle/mining-of-uranium/world-uranium-mining-production",
         "licence": "Copyright World Nuclear Association; figures cited with attribution (see website terms of use)", "update": "annual"},
    ]
    changed = False
    for s in new:
        if s["id"] not in have:
            src.append(s)
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


def _nf(v):
    """A figure of the source without invented decimals: 230, 1,823, 1.3."""
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.3g}"


CHECK_TITLES = {
    "K1": "trader totals of crops against USDA PSD", "K2": "a bilateral flow above the importer's total imports in USDA PSD",
    "K3": "crude oil exports against EIA production", "K4": "coal exports and imports against EIA",
    "K6": "exporter continuity", "K7": "importer continuity", "K8": "pairs of the latest year that halved or more than doubled",
    "K10": "exports above USGS mine production", "K11": "physical plausibility against the atlas's own layers (QA only)",
    "K12": "main route against the great-circle distance of its ports (QA only)",
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
            "type, against IMF PortWatch's estimated volume of all ships of that type (IMF PortWatch, data adapted). A passage is "
            "flagged when 'at least' is above 110% of PortWatch's best full year since 2019; the Danish Straits counter is the "
            "Oresund only. Written by `build_freight.py`; never a failure of the build.", "",
            "| passage | type | at least (Mt) | up to (Mt) | PortWatch, latest year (Mt) | best year (Mt) | at least / best | level |",
            "|---|---|---|---|---|---|---|---|"]
    for r in sorted((r for r in k9 if r.get("kind") == "passage"), key=lambda r: (r["chokepoint"], r["type"])):
        ref = "-" if r.get("reference") is None else _fmt(r["reference"])
        out.append(f"| {r['chokepoint']} | {r['type']} | {_fmt(r['value'])} | {_fmt(r['high'])} | {ref} | {_fmt(r['best'])} ({r['bestYear']}) "
                   f"| {r['ratio']:.2f} | {r['level']} |")
    out += [""] + [f"- {r['text']}" for r in k9 if r.get("kind") == "passage" and r["level"] == "flag"]
    passage_names = {r["chokepoint"]: r["text"].split(",")[0] for r in k9 if r.get("kind") == "passage"}
    par =[r for r in k9 if r.get("kind") == "parallel"]
    out += ["", "### Parallel passages under other thresholds of the parallel rule (K9)", "",
            "Recomputed with `routing.classify()` from the option distances cached by `build_lanes.py` (no routing). The published "
            "figures use 5% or 300 nm.", "", "| passage | 3% or 150 nm | 5% or 300 nm | 10% or 500 nm |", "|---|---|---|---|"]
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
           "Rows that `clean()` (`pipeline/trade/clean.py`) removes before any table is built. Qatari LPG pairs with no flow in "
           "either neighbouring year (rule DROP_NEW_PAIRS): several equal the LNG row of the same pair and year, which suggests "
           "LNG cargoes recorded a second time under the LPG code; this is a hypothesis, not established.", ""]
    rows = sorted(baci.dropped, key=lambda r: (r["group"], r["year"], -r["t"]))
    for (g, y), grp in pd.DataFrame(rows).groupby(["group", "year"]) if rows else []:
        out.append(f"- {_label(g)} {y}: {len(grp)} rows, {_fmt(grp['t'].sum() / 1e6)} Mt")
    out.append("")
    for r in rows:
        est = " (tonnage estimated from value)" if r.get("est") else ""
        out.append(f"- {_label(r['group'])} {r['year']}, {K._name(r['o'])} to {K._name(r['d'])}: {_fmt(r['t'] / 1e6)} Mt{est}, "
                   f"USD {r['usd'] / 1e3:,.0f} million")
    return out + [""] if rows else out + ["- none", ""]


def qa_draughts():
    have = sorted(VR.DRAUGHT_M)
    none = sorted(set(VR.SPEED) - set(VR.DRAUGHT_M))
    return ["## Vessel classes without a sourced draught", "",
            "The draught rule of the routing (`vessel_rules.avoids()`) restricts a class only where a sourced laden draught exceeds a "
            "sourced passage limit. Classes with a sourced draught: " + ", ".join(f"{c} {VR.DRAUGHT_M[c]:g} m" for c in have) +
            "; passage limits: " + ", ".join(f"{p} {v:g} m" for p, v in sorted(VR.PASSAGE_LIMIT_M.items())) +
            " (Wikipedia, CC BY-SA 4.0; sources in `pipeline/freight/vessel_rules.py`).", "",
            "Not restricted by any strait for want of a sourced draught: " + ", ".join(none) + ".", ""]


def write_qa(index, docs, baci=None):
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
                lines.append(f"- {e['id']} {k}: {r['y']} ({r['s']}) " + ", ".join(f"{x['c']} {_fmt(x['v'])}" for x in r["rows"][:3]) + f" (world {_fmt(r['world'])} {r['u']})")
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
    if baci is not None:
        lines += qa_dropped(baci)
    lines += qa_draughts()
    lines += ["## Build warnings", ""] + ([f"- {w}" for w in QA_WARN] or ["- none"])
    with open(os.path.join(HERE, "QA.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# Figures quoted in caveats from publications that are not atlas sources. Each carries its publisher and
# year and is printed with them; none is used in a table.
LNG_REFERENCE = [
    # (publisher, publication, figure, unit, year, what)
    ("GIIGNL", "Annual Report 2025", 406.24, "Mt", 2024, "world LNG trade"),
    ("IGU", "World LNG Report 2025", 411.24, "Mt", 2024, "world LNG trade"),
]


def caveats(docs, eia):
    """Known source limitations found by the data audit; shown with the tables they affect.

    Every number in these sentences is read from a table of the atlas or from a source file at build
    time, or comes from LNG_REFERENCE with its publisher and year. No year is typed in the text.
    """
    out = {}

    # LPG: the EIA series for the United States stops early
    us = eia.s[("67-2", "MT")].get("USA", {})
    c = docs["lpg"]["consumption"]
    if c["y"] not in us:
        last = max(us) if us else None
        # last value in line with the year before it (the final US point of the EIA file is three times the previous one)
        ref = next((y for y in sorted(us, reverse=True) if y - 1 in us and 0.5 <= us[y] / us[y - 1] <= 2), None)
        t = f"Excludes the United States: the EIA series for US LPG consumption ends in {last}"
        if ref:
            t += f" (EIA gives {_fmt(us[ref] * 1e-3)} Mt for {ref})"
        out["lpg"] = {"consumption": t + ", so the world total is understated.",
                      "notes": [f"EIA's {c['y']} LPG consumption table has no United States value; the world total excludes it."]}

    # pipeline gas: customs tonnage against EIA volumes, same year
    ng = docs["natural-gas"]["exports"]
    by = ng["y"]
    can_b = next((r["v"] for r in ng["rows"] if r["c"] == "CAN"), None)
    can_e = eia.s[("26-4", "BCM")].get("CAN", {}).get(by)
    t = "Pipeline-gas tonnage in customs data is often estimated from value and is far too low for North America"
    if can_b and can_e:
        t += f": customs data show {_fmt(can_b)} Mt of Canadian exports in {by}, EIA {_fmt(can_e)} bcm"
    out["natural-gas"] = {"exports": t + ". Use the EIA production and consumption tables (bcm) for volumes.",
                          "imports": "Pipeline-gas tonnage in customs data is often estimated from value and is far too low for North America (see the exporters table).",
                          "notes": ["Customs tonnage for pipeline gas is unreliable for North America, where it is estimated from value; use EIA bcm figures for production and consumption."]}

    # LNG: customs total against the two industry surveys
    lx = docs["lng"]["exports"]
    lw = lx["world"]
    refs = "; ".join(f"{pub} ({doc}): {v:g} {u} of {what} in {y}" for pub, doc, v, u, y, what in LNG_REFERENCE)
    out["lng"] = {"exports": f"Customs (BACI) tonnage, {lw:.2f} Mt in {lx['y']}, is below the industry surveys. {refs}.",
                  "discrepancies": [f"BACI LNG exporter tonnage ({lw:.2f} Mt in {lx['y']}) is below the industry surveys: {refs}."]}

    out["gold"] = {"exports": "Includes refining, trading and vaulting hubs (e.g. Switzerland, UAE, Hong Kong) that re-export gold: this ranks trade, not mine supply.",
                   "imports": "Includes refining and vaulting hubs; not a measure of final demand."}
    out["silver"] = {"exports": "Includes refining and trading hubs that re-export silver: this ranks trade, not mine supply."}
    out["refined-products"] = {"exports": "Includes storage and blending hubs that re-export products (e.g. the Netherlands, Singapore, Belgium): this ranks trade, not refinery output.",
                               "imports": "Includes storage and blending hubs that re-export what they import; not a measure of final demand."}
    out["uranium"] = {"exports": "Gross weight of ores and compounds, not contained uranium; Namibia and Niger tonnage exceeds their mine output, so treat as indicative.",
                      "notes": ["Trade tonnage is the gross weight of uranium ores and compounds, not uranium content."]}
    out["cobalt"] = {"exports": "Gross weight of ores and unwrought cobalt: not comparable with mine production, which is in tonnes of contained cobalt.",
                     "imports": "Gross weight of ores and unwrought cobalt, not contained cobalt."}
    out["potash"] = {"exports": "Product weight of potassium chloride: not comparable tonne for tonne with production and reserves, which are in K2O content.",
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
            for sec, c in (("exports", e["o"]), ("imports", e.get("d"))):
                for r in (d.get(sec) or {}).get("rows", []):
                    if c and r["c"] == c and e["text"] not in r.get("n", ""):
                        r["n"] = (r["n"] + "; " if r.get("n") else "") + e["text"]


def annotate(docs, eia):
    for cid, c in caveats(docs, eia).items():
        d = docs.get(cid)
        if not d:
            continue
        for sec, text in c.items():
            if sec in ("notes", "discrepancies"):
                d.setdefault(sec, [])
                d[sec] += [t for t in text if t not in d[sec]]
            elif d.get(sec):
                add_caveat(d[sec], text)
                if sec in d.get("summary", {}):
                    d["summary"][sec]["n"] = text


if __name__ == "__main__":
    main()
