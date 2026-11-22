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
  pipeline/cache/sea_flows.csv.gz            seaborne subset of BACI (pipeline/freight/build_lanes.py)
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

BACI_YEAR = 2024
USGS_YEAR = "2025"
PSD_MY = 2025
PSD_LABEL = "2025/26"
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
BACI_OVERRIDE = {"S19": "TWN"}  # BACI "Other Asia, nes" = Taiwan
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


# ====================================================================== USGS
class Usgs:
    def __init__(self):
        d = pd.read_csv(os.path.join(RAW, "usgs", "MCS2026_Commodities_Data.csv"), encoding="latin-1", dtype=str)
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
            else:
                missing.append(r["Country"])
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

    def ranked(self, commodity, detail, u, factor, label, kind="production"):
        t = self.table(commodity, detail, factor=factor)
        world = t["world"]
        n = [f"USGS MCS 2026, {label}"]
        if kind == "production" and t["estimated"]:
            n.append("2025 values are USGS estimates")
        sumrows = total_of(t["rows"]) + t["other"]
        if world is None:
            world = sumrows
            n.append("world = sum of reporting countries incl. 'Other countries'")
        else:
            n.append("USGS world total is rounded")
            if sumrows > world * 1.05:
                warn(f"{commodity}/{detail}: sum of countries {sumrows:.0f} > world {world:.0f}")
        if t["wnote"]:
            n.append(t["wnote"])
        if t["missing"]:
            names = sorted(set(t["missing"]))
            n.append("not published (withheld, range or qualitative): " + ", ".join(names[:8]) + ("..." if len(names) > 8 else ""))
        return ranked(t["rows"], int(USGS_YEAR), "usgs-mcs", u, world=world, n="; ".join(n)), t


# ====================================================================== EIA
class Eia:
    NEED = {("57-1", "TBPD"), ("26-1", "BCM"), ("26-2", "BCM"), ("7-1", "MT"), ("7-2", "MT"), ("7-3", "MT"), ("7-4", "MT"),
            ("7-6", "MST"), ("130-1", "MT"), ("130-2", "MT"), ("130-3", "MT"), ("130-4", "MT"), ("54-2", "TBPD"),
            ("67-2", "MT"), ("62-2", "TBPD"), ("63-2", "TBPD"), ("65-2", "TBPD"), ("66-2", "TBPD")}

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
            ["Production", "Exports", "Imports", "Domestic Consumption", "Domestic Use", "Human Dom. Consumption"])]
        d = d[~d["Unit_Description"].isin(["(PERCENT)"])]
        self.d = d
        rel = d[["Calendar_Year", "Month"]].drop_duplicates().sort_values(["Calendar_Year", "Month"]).iloc[-1]
        self.release = f"latest revision {int(rel['Calendar_Year'])}-{int(rel['Month']):02d}"
        self.cache = {}

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
        n = [f"USDA PSD, {commodity}, {what}, market year {PSD_LABEL} ({self.release})",
             "world = sum of reporting countries; EU counted as one entity (intra-EU trade excluded)" if attr in ("Exports", "Imports")
             else "world = sum of reporting countries"]
        if conv:
            n.append(conv)
        if extra:
            n.append(extra)
        return ranked(rows, PSD_LABEL, "usda-psd", unit, world=world, n="; ".join(n)), unit


# ====================================================================== BACI
class Baci:
    def __init__(self):
        df = pd.read_csv(os.path.join(CACHE, "baci_flows.csv.gz"))
        df = df[df["o"].notna() & df["d"].notna() & (df["o"] != df["d"])].copy()
        has_t = df["t"] > 0
        uv = (df[has_t & (df["usd"] > 0)].assign(u=lambda x: x["usd"] / x["t"]).groupby(["group", "year"])["u"].median())
        df = df.join(uv.rename("uv"), on=["group", "year"])
        miss = ~has_t & (df["usd"] > 0) & df["uv"].notna()
        ratio = (df["usd"] / df["t"].where(has_t)) / df["uv"]
        bad = has_t & (df["usd"] > 50_000) & ((ratio < 1 / 3) | (ratio > 3)) & df["uv"].notna()
        fix = miss | bad
        df["t0"] = df["t"]
        df.loc[fix, "t"] = df.loc[fix, "usd"] / df.loc[fix, "uv"]
        df["est"] = fix
        df["t_est"] = df["t"].where(fix, 0.0)
        self.df = df
        sea = pd.read_csv(os.path.join(CACHE, "sea_flows.csv.gz"))
        self.sea = set(zip(sea["year"], sea["group"], sea["o"], sea["d"]))
        self.lanes = {}
        ld = os.path.join(DATA, "freight", "lanes")
        for f in os.listdir(ld):
            if f.endswith(".json"):
                j = json.load(open(os.path.join(ld, f), encoding="utf-8"))
                self.lanes[j["group"]] = {"ids": {l["id"] for l in j["lanes"]}, "seaborne": j["seaborne"], "years": j["years"],
                                          "unit": j["unit"], "y": j["y"]}

    def iso(self, code):
        code = BACI_OVERRIDE.get(code, code)
        if code in ISO_SET:
            return code
        UNKNOWN["baci"].add(code)
        return None

    def group(self, g, year=BACI_YEAR):
        return self.df[(self.df["group"] == g) & (self.df["year"] == year)]

    def ranked(self, g, side, u, div, what, extra=None):
        d = self.group(g)
        col = "o" if side == "exports" else "d"
        agg = d.groupby(col).agg(t=("t", "sum"), te=("t_est", "sum"), usd=("usd", "sum")).sort_values("t", ascending=False)
        world = agg["t"].sum() / div
        est_share = agg["te"].sum() / agg["t"].sum() if agg["t"].sum() else 0
        rows = []
        for code, r in agg.head(TOP + 5).iterrows():
            iso = self.iso(code)
            es = r["te"] / r["t"] if r["t"] else 0
            note = None
            if code in BACI_OVERRIDE:
                note = f"BACI code {code} ('Other Asia, nes'), reported as Taiwan"
            if es >= 0.10:
                note = (note + "; " if note else "") + f"{es * 100:.0f}% of tonnage estimated from value"
            rows.append((iso, r["t"] / div, note))
        n = [f"CEPII BACI HS92 {what}, {BACI_YEAR}, all transport modes, gross weight",
             "world = sum of all reported flows in the Atlas BACI extract (flows below 1,000 t and 1 M USD omitted)"]
        if est_share >= 0.01:
            n.append(f"{est_share * 100:.0f}% of world tonnage estimated from value where missing or inconsistent")
        if extra:
            n.append(extra)
        return ranked(rows, BACI_YEAR, "baci", u, world=world, n="; ".join(n)), est_share

    def flows(self, g, u, div, lane_group=None, only_exporters=None, mode_all=None, n_all=None):
        d = self.group(g)
        if only_exporters:
            d = d[d["o"].isin(only_exporters)]
        d = d.sort_values("t", ascending=False).head(NFLOWS)
        lg = self.lanes.get(lane_group or g)
        out = []
        for _, r in d.iterrows():
            o, de = self.iso(r["o"]), self.iso(r["d"])
            if not o or not de:
                raise SystemExit(f"flow with unmapped country {r['o']}-{r['d']} in {g}")
            f = {"o": o, "d": de, "v": rnd(r["t"] / div), "u": u, "y": BACI_YEAR, "s": "baci"}
            sea = (BACI_YEAR, g, r["o"], r["d"]) in self.sea
            f["mode"] = mode_all or ("sea" if sea else "land")
            lid = f"{lane_group or g}:{r['o']}-{r['d']}"
            if lg and lid in lg["ids"]:
                f["lane"] = lid
            if r["est"]:
                f["n"] = "tonnage estimated from value"
            if n_all:
                f["n"] = (f["n"] + "; " if "n" in f else "") + n_all
            out.append(f)
        return out

    def seaborne(self, g, label=None):
        lg = self.lanes.get(g)
        if not lg:
            return None
        v = lg["seaborne"][-1]
        n = (f"seaborne subset of BACI flows ({g}) under the Atlas lane method (data/freight/lanes/{g}.json); "
             "both countries need a sea gateway and must not be land neighbours")
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
    with open(os.path.join(RAW, "baci", "country_codes_V202601.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            codes[int(r["country_code"])] = r["country_iso3"]
    fo_override = {}  # FAO M49 code -> ISO3 where it differs from the BACI numeric code
    rows = []
    world = None
    with open(os.path.join(CACHE, "faostat_cocoa_production.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["year"] != "2024":
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
    n = ("FAOSTAT QCL, cocoa beans (item 661), production, 2024; tonnes converted to kt; world total as published by FAO "
         "(note flags: E estimated, I imputed, X from international organisations; A official)")
    return ranked(rows, 2024, "faostat", "kt", world=world, n=n)


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
    "thermal-coal": ("coal", MT, "coal (HS 270111, 270112, 270119)"),
    "uranium": ("uranium", KT, "uranium ores and natural uranium compounds (HS 261210, 284410)"),
    "iron-ore": ("iron-ore", MT, "iron ore (HS 260111, 260112)"),
    "steel": ("steel", MT, "steel products (HS 72 excl. 7201-7205)"),
    "copper": ("copper-ore", MT, "copper ores and concentrates (HS 2603)"),
    "aluminium": ("aluminium", MT, "unwrought aluminium (HS 7601)"),
    "bauxite": ("bauxite", MT, "bauxite (HS 2606)"),
    "nickel": ("nickel-ore", MT, "nickel ores and concentrates (HS 2604)"),
    "zinc": ("zinc-ore", MT, "zinc ores and concentrates (HS 2608)"),
    "lead": ("lead-ore", MT, "lead ores and concentrates (HS 2607)"),
    "tin": ("tin-metal", KT, "unwrought tin and tin waste (HS 8001)"),
    "lithium": ("lithium", KT, "lithium carbonate, oxide and hydroxide (HS 283691, 282520)"),
    "cobalt": ("cobalt", KT, "cobalt ores and unwrought cobalt (HS 260500, 810510)"),
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

    for cid in ids:
        d, notes, disc = start(cid)

        # ------------------------------------------------------------ energy
        if cid == "crude-oil":
            d["production"] = eia.ranked(("57-1", "TBPD"), "kb/d", 1.0, "crude oil including lease condensate production")
            g = add_baci_trade(d, cid, notes, disc)
            summ(d, "production", d["production"], "EIA crude oil including lease condensate, world")
            summ(d, "exports", d["exports"], "sum of all BACI crude oil flows, tonnes (all modes)")
            seaborne(d, g)
            notes += [
                "Production is in kb/d (EIA); trade tables are in Mt/year (BACI tonnage). Conversion depends on grade, so none is applied.",
                "No proved-reserves or crude-specific consumption series exists in the EIA bulk file used (INTL.txt); refined-product demand is under 'refined-products'.",
            ]
        elif cid == "refined-products":
            d["consumption"] = eia.ranked(("54-2", "TBPD"), "kb/d", 1.0, "refined petroleum products consumption")
            g = add_baci_trade(d, cid, notes, disc)
            summ(d, "consumption", d["consumption"])
            summ(d, "exports", d["exports"], "sum of all BACI refined-product flows (HS 2710), tonnes, all modes")
            seaborne(d, g)
            y = d["consumption"]["y"]
            parts = []
            for key, nm in [(("65-2", "TBPD"), "distillate fuel oil"), (("62-2", "TBPD"), "motor gasoline"),
                            (("63-2", "TBPD"), "jet fuel"), (("66-2", "TBPD"), "residual fuel oil")]:
                parts.append(f"{nm} {eia.s[key]['WORL'][y] / 1000:.1f} mb/d")
            notes.append(f"World consumption by product, {y} (EIA, eia-intl): " + ", ".join(parts) + ". Products do not add up to the total (other products excluded).")
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
            tr = eia.ranked(("7-6", "MST"), "Mt", 0.90718474, "coal reserves (all ranks, not split thermal/metallurgical); million short tons converted to Mt")
            # reserves are stable estimates: say how many listed countries are unchanged over 5 years
            y = tr["y"]
            same = sum(1 for r in tr["rows"] if all(abs(eia.s[("7-6", "MST")][_iso_to_eia(r["c"])].get(y - k, -1) - eia.s[("7-6", "MST")][_iso_to_eia(r["c"])][y]) < 1e-6 for k in range(1, 6)))
            tr["n"] += f"; {same} of {len(tr['rows'])} listed countries report an unchanged value over the last 5 years (reserve estimates are not revised annually)"
            d["reserves"] = tr
            g = add_baci_trade(d, cid, notes, disc, extra="HS 2701 does not separate thermal from metallurgical coal: figures cover all coal")
            summ(d, "production", d["production"])
            summ(d, "consumption", d["consumption"])
            summ(d, "reserves", d["reserves"], "EIA coal reserves, all coal (not split thermal/metallurgical)")
            summ(d, "exports", d["exports"], "all coal (HS 2701) incl. metallurgical coal, BACI")
            seaborne(d, g, "all coal (thermal and metallurgical)")
            notes += ["HS 2701 does not separate thermal from metallurgical coal: trade tables and flows cover all coal.",
                      "Production and consumption are all coal minus metallurgical coal (EIA), computed country by country; reserves are for all coal."]
            # EIA vs BACI exports
            disc += _compare("exports", eia, ("7-4", "MT"), 1e-3, baci, "coal", 1e6, "Mt", "EIA coal exports", BACI_YEAR)
        elif cid == "met-coal":
            d["production"] = eia.ranked(("130-1", "MT"), "Mt", 1e-3, "metallurgical coal production; 1000 metric tons converted to Mt")
            d["consumption"] = eia.ranked(("130-2", "MT"), "Mt", 1e-3, "metallurgical coal consumption; 1000 metric tons converted to Mt")
            d["exports"] = eia.ranked(("130-4", "MT"), "Mt", 1e-3, "metallurgical coal exports; 1000 metric tons converted to Mt")
            d["imports"] = eia.ranked(("130-3", "MT"), "Mt", 1e-3, "metallurgical coal imports; 1000 metric tons converted to Mt")
            d["flows"] = baci.flows("coal", "Mt", 1e6, only_exporters=["AUS", "USA", "CAN", "MNG", "RUS"],
                                    n_all="all coal (HS 2701) from a main metallurgical-coal exporter; thermal and metallurgical not separated")
            summ(d, "production", d["production"])
            summ(d, "consumption", d["consumption"])
            summ(d, "exports", d["exports"])
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
                r, t = us.ranked(com, det, u, fac, label, kind="production" if sec != "reserves" else "reserves")
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
            notes += ["Cocoa is not in USDA PSD: exports and imports are BACI cocoa beans (calendar 2024); production is FAOSTAT 2024.",
                      "No consumption table: grindings data are not in the loaded sources."]
        elif cid in PSD:
            com, cons_attr, ex_attr, im_attr = PSD[cid]
            what = PSD_WHAT[cid]
            d["production"], pu = psd.ranked(com, "Production", f"{what} production")
            d["consumption"], _ = psd.ranked(com, cons_attr, f"{what} domestic consumption/use")
            d["exports"], _ = psd.ranked(com, ex_attr, f"{what} exports (market-year trade)")
            d["imports"], _ = psd.ranked(com, im_attr, f"{what} imports (market-year trade)")
            g, (bu, bdiv), bwhat = TRADE[cid]
            d["flows"] = baci.flows(g, bu, bdiv)
            summ(d, "production", d["production"])
            summ(d, "consumption", d["consumption"])
            summ(d, "exports", d["exports"])
            seaborne(d, g)
            notes.append("Flows are BACI calendar-2024 customs flows; ranked trade tables are USDA PSD market-year 2025/26 (trader reference). Years differ.")
            if cid == "coffee":
                notes.append("PSD coffee exports/imports include roasted and soluble coffee in green-bean equivalent; BACI flows are green beans only (HS 0901.11/12).")
            if cid == "rice":
                notes.append("PSD rice is on a milled basis; PSD 'Exports' are market-year (not trade-year) figures.")
            if cid == "sugar":
                notes.append("PSD sugar is centrifugal sugar in raw value (cane and beet).")
            if cid == "soybeans":
                notes.append("PSD domestic consumption = crush + food + feed/waste; production is for the market year starting in 2025 (Brazil/Argentina harvest early 2026, US harvest autumn 2025).")
            disc += _psd_vs_baci(psd, baci, cid, com, ex_attr, g)
        else:
            raise SystemExit(f"no recipe for commodity {cid}")

        # lead/tin/refined copper etc: side notes with BACI trade of the second group
        if cid == "copper":
            notes.append(_note_group(baci, "copper-refined", "Refined copper (HS 7403, 7402)"))
            notes.append("Trade tables are copper ores and concentrates in gross weight (Mt), not contained copper; USGS production is contained copper (kt Cu). 'refinery' is an extra field: USGS refined copper production.")
        elif cid == "bauxite":
            notes.append(_note_group(baci, "alumina", "Alumina (HS 281820)"))
            notes.append("USGS production/reserves are dry tonnes; 'refinery' is an extra field: USGS alumina refinery production (Mt).")
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
            notes.append("Trade tables are unwrought tin metal (HS 8001) in kt; production and reserves are contained tin (t Sn). No tin lanes exist (no seaborne figure).")
        elif cid == "phosphate":
            notes.append(_note_group(baci, "dap", "DAP (HS 310530)"))
            notes.append("Trade tables are natural phosphates (HS 2510), gross weight; USGS production is marketable phosphate rock.")
        elif cid == "lithium":
            notes.append("Trade is lithium carbonate and hydroxide/oxide in gross weight (kt); spodumene concentrate has no HS6 code. USGS production is contained lithium (t Li), so units differ.")
        elif cid == "cobalt":
            notes.append("Trade covers cobalt ores and unwrought cobalt in gross weight (kt); USGS production is contained cobalt (t Co).")
        elif cid == "rare-earths":
            notes.append("Trade covers rare-earth metals and compounds (HS 280530, 284610, 284690) in gross weight (kt); USGS production is REO equivalent (t REO).")
        elif cid == "aluminium":
            notes.append("Trade is unwrought aluminium (HS 7601); USGS production is primary smelter output. Bauxite reserves are under 'bauxite'.")
        elif cid == "steel":
            notes.append("Trade is steel products (HS 72 excluding pig iron, ferro-alloys and scrap), gross weight; USGS production is raw steel.")
        elif cid in ("gold", "silver"):
            notes.append("Trade tonnage in BACI is frequently missing for precious metals and is estimated from value (see percentage in the table note); treat flows as indicative.")
        elif cid == "iron-ore":
            notes.append("USGS production is usable ore (gross weight); reserves are crude ore. Iron-content figures (Australia ~600 Mt Fe in 2025) are in the USGS file but not shown.")
        elif cid == "manganese":
            notes.append("Trade is manganese ore (HS 2602), gross weight (Mt); USGS production is shown in kt as in the USGS table.")
        elif cid == "urea":
            notes.append("Production proxy is ammonia plant output in nitrogen content (USGS); urea output is not in the loaded sources. Trade is urea (HS 310210), product weight.")
        elif cid == "potash":
            notes.append("USGS production/reserves are K2O equivalent; trade is potassium chloride (HS 310420), product weight.")

        notes = [n for n in notes if n]
        if notes:
            d["notes"] = notes
        if disc:
            d["discrepancies"] = disc
        docs[cid] = d

    check_unknown()

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
        order = ["id", "summary", "production", "refinery", "reserves", "consumption", "exports", "imports", "flows", "notes", "discrepancies"]
        dd = {k: d[k] for k in order if k in d}
        with open(os.path.join(OUT, e["id"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(dd, f, indent=1, ensure_ascii=False)
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1, ensure_ascii=False)
    update_sources()
    write_qa(index, docs)
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
        out.append(f"World exports: USDA PSD {PSD_LABEL} {world:.1f} {unit} (sum of reporting countries, EU excl. intra-trade) vs BACI {BACI_YEAR} {bw:.1f} {unit} "
                   f"({(world / bw - 1) * 100:+.0f}%); different year and basis (market year vs calendar year, product scope); PSD shown in the table.")
    return out


def _pgm(d, us, baci, notes, summ, seaborne, add_baci_trade, disc, cid):
    pt = us.table("Platinum", "Mine production: Platinum", factor=1e-3)
    pdl = us.table("Palladium", "Mine production: Palladium", factor=1e-3)
    ptd, pdd = dict(pt["rows"]), dict(pdl["rows"])
    rows = []
    for c in sorted(set(ptd) | set(pdd)):
        a, b = ptd.get(c, 0.0), pdd.get(c, 0.0)
        rows.append((c, a + b, f"platinum {rnd(a)} t + palladium {rnd(b)} t"))
    world = pt["world"] + pdl["world"]
    n = ("USGS MCS 2026, platinum plus palladium mine production, PGM content (kg converted to t); 2025 values are USGS estimates; "
         "world = sum of the USGS rounded world totals for platinum and palladium; excludes rhodium, ruthenium, iridium and osmium")
    if total_of(rows) + pt["other"] + pdl["other"] > world * 1.05:
        warn("pgm: country sum above world")
    d["production"] = ranked(rows, int(USGS_YEAR), "usgs-mcs", "t", world=world, n=n)
    res = us.table("Platinum-Group Metals", "PGM reserves", factor=1e-3)
    rn = "USGS MCS 2026, platinum-group metals reserves, PGM content (kg converted to t); USGS world total is rounded"
    if res["wnote"]:
        rn += "; " + res["wnote"]
    d["reserves"] = ranked(res["rows"], int(USGS_YEAR), "usgs-mcs", "t", world=res["world"] if res["world"] else total_of(res["rows"]) + res["other"], n=rn)
    g = add_baci_trade(d, cid, notes, disc)
    summ(d, "production", d["production"])
    summ(d, "reserves", d["reserves"])
    summ(d, "exports", d["exports"])
    seaborne(d, g)
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


def write_qa(index, docs):
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
    lines += ["", "## Build warnings", ""] + ([f"- {w}" for w in QA_WARN] or ["- none"])
    with open(os.path.join(HERE, "QA.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
