"""
Checks of the cleaned customs frame (pipeline/trade/clean.py) against the references on disk.
Trade-engine plan, section 2.7 (G5, G6); METHODOLOGY.md §1.

    import checks
    findings = checks.run(clean(df), 2024)

One record per finding: check, group, year, country (or o and d), value, reference, ratio, text, level
("flag" above the threshold; "watch" for the listed band below it; "qa" for QA.md only).
Values are in Mt unless the record says otherwise.

Rules
  * No check changes a tonnage and no check raises: the scheduled job must never stop on a finding.
  * Checks that read raw/ (K1, K2, K3, K4, K10) skip quietly when their file is absent, as on the
    runner of the scheduled jobs, or cannot be read (another layout), or holds none of their series;
    such a check is not run, and merge() then keeps its previous records.
  * Single writer: build_lanes.py calls run() once and writes pipeline/cache/trade_checks.json;
    build_freight.py adds K9; build_commodities.py only reads the file and renders QA.md.

Checks
  K1  trader totals of crops against USDA PSD (marketing years Y-1 and Y straddle calendar Y)
  K2  a bilateral flow above the importer's total imports in USDA PSD, every year
  K3  crude exports against EIA production (series 57-1, thousand barrels per day, converted with the
      barrels-per-tonne ratio of EIA's own series in both units)
  K4  coal exports and imports against EIA (series 7-4 and 7-3, 1000 metric tons)
  K5  gas: not run. EIA gives gas trade in volume and energy units only (bcm, TJ, Mtoe) and customs
      give tonnes; no file on disk states a conversion for each trader's gas, so the units do not
      reconcile (comparison printed by the E3 package report).
  K6  exporter continuity (a gap or a spike against both neighbouring years), BACI only
  K7  importer continuity, BACI only
  K8  pairs of the latest year that lost more than half or more than doubled against Y-1, BACI only
  K9  passages against IMF PortWatch: written by build_freight.py
  K10 exports above production (USGS Mineral Commodity Summaries)
  K11 physical plausibility against the atlas's own infrastructure layers (QA only: the layers are
      hand-built and incomplete)
  K12 detour of a pair's main route against the great-circle distance: detour(), called by the
      lane builder once the pairs are routed
  K13 a pair of one metal product declared at under half the usual unit value of that product
"""
import json
import os
import re
import sys
import unicodedata

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from common import constants as CN  # noqa: E402  (physical and conventional constants, with the page that gives each)
RAW = os.path.join(ROOT, "raw")
DATA = os.path.join(ROOT, "data")
TRADE_CHECKS = os.path.join(ROOT, "pipeline", "cache", "trade_checks.json")
RAW_CHECKS = {"K1", "K2", "K3", "K4", "K10"}

EU27 = set("AUT BEL BGR HRV CYP CZE DNK EST FIN FRA DEU GRC HUN IRL ITA LVA LTU LUX MLT NLD POL PRT ROU SVK SVN ESP SWE".split())

# lane group -> USDA PSD commodity
PSD_GROUPS = {
    "wheat": "Wheat", "corn": "Corn", "soybeans": "Oilseed, Soybean", "soymeal": "Meal, Soybean", "soyoil": "Oil, Soybean",
    "rice": "Rice, Milled", "palm-oil": "Oil, Palm", "rapeseed": "Oilseed, Rapeseed", "cotton": "Cotton",
    "sugar": "Sugar, Centrifugal", "coffee": "Coffee, Green",
    # the grains, oilseeds and products added with M-023 (HS 1512 and 1514 also hold safflower and mustard oil; PSD does not)
    "barley": "Barley", "sorghum": "Sorghum", "sunflower-seed": "Oilseed, Sunflowerseed", "sunflower-oil": "Oil, Sunflowerseed",
    "sunflower-meal": "Meal, Sunflowerseed", "rapeseed-oil": "Oil, Rapeseed", "rapeseed-meal": "Meal, Rapeseed",
}
# kt per PSD unit: 1000 bales of 480 lb, 1000 bags of 60 kg (pipeline/common/constants.py)
PSD_KT = {"(1000 480 lb. Bales)": CN.KT_PER_1000_COTTON_BALES, "(1000 60 KG BAGS)": CN.KT_PER_1000_COFFEE_BAGS, "(1000 MT)": 1.0}

# Standard atomic weights (CIAAW, pipeline/common/constants.py): K2O content of pure potassium chloride and nitrogen content of urea
_K, _CL, _O, _C, _N, _H = (CN.ATOMIC_WEIGHT[e] for e in ("K", "Cl", "O", "C", "N", "H"))
K2O_IN_KCL = (2 * _K + _O) / (2 * (_K + _CL))
N_IN_UREA = 2 * _N / (_C + _O + 2 * _N + 4 * _H)

# lane group -> (USGS MCS chapter, statistic, factor from product weight to the USGS basis, basis note)
USGS_K10 = {
    "potash": ("POTASH", "Mine production", K2O_IN_KCL,
               f"exports converted to K2O with the K2O content of pure potassium chloride ({K2O_IN_KCL:.3f}, from molar masses)"),
    "bauxite": ("BAUXITE AND ALUMINA", "Bauxite, mine production", 1.0, "customs gross weight against USGS dry tonnes"),
    "phosphate-rock": ("PHOSPHATE ROCK", "Mine production", 1.0, "customs gross weight against USGS marketable production"),
    "urea": ("NITROGEN (FIXED) AMMONIA", "Plant production", N_IN_UREA,
             f"urea exports converted to nitrogen with the nitrogen content of urea ({N_IN_UREA:.4f}, from molar masses), against ammonia production in nitrogen content"),
}

USGS_UNIT = {"potash": " K2O", "urea": " of nitrogen"}

LABEL = {"crude-oil": "crude oil", "refined-products": "refined products", "palm-oil": "palm oil", "iron-ore": "iron ore",
         "phosphate-rock": "phosphate rock", "soymeal": "soybean meal", "soyoil": "soybean oil", "lng": "LNG", "lpg": "LPG",
         "dap": "DAP", "nickel-int": "nickel intermediates", "uan": "UAN", "npk": "NPK",
         "monoammonium-phosphate": "MAP", "potassium-sulphate": "potassium sulphate (SOP)",
         # what the code holds in HS 1992 (M-023): two oils in each oil code, every dried pulse in the pulses code
         "sunflower-oil": "sunflower and safflower oil", "rapeseed-oil": "rapeseed, canola and mustard oil", "pulses": "dried pulses",
         # the metal bulks of A-010: the group id is not the product's name
         "dri": "direct-reduced iron", "chromium-ore": "chromium ore", "coke": "coke and semi-coke", "ferro-alloys-other": "other ferro-alloys"}


def label(g):
    """Display name of a group inside a sentence ("crude oil", "LNG")."""
    return LABEL.get(g, g.replace("-", " "))


def cap_label(g):
    """Display name of a group at the start of a sentence: only its first letter is raised ("Crude oil", "LNG")."""
    s = label(g)
    return s[:1].upper() + s[1:]


def _json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- country names
def _fold(s):
    s = unicodedata.normalize("NFKD", str(s).replace("\x92", "'").replace("’", "'"))
    return re.sub(r"\s+", " ", "".join(ch for ch in s if not unicodedata.combining(ch))).strip().lower()


_NAMES = {}
_DISPLAY = {"EU27": "the EU27", "XAS": "Asia, not specified"}
NAME_OVERRIDE = {
    "burma": "MMR", "congo (kinshasa)": "COD", "congo (brazzaville)": "COG", "korea, south": "KOR", "korea, north": "PRK",
    "bahamas, the": "BHS", "gambia, the": "GMB", "czech republic": "CZE", "czechia": "CZE", "hong kong": "HKG", "macau": "MAC",
    "united states": "USA", "russia": "RUS", "vietnam": "VNM", "turkey": "TUR", "turkiye": "TUR", "iran": "IRN", "syria": "SYR",
    "venezuela": "VEN", "bolivia": "BOL", "tanzania": "TZA", "laos": "LAO", "taiwan": "TWN", "egypt": "EGY", "china": "CHN",
    "cote d'ivoire": "CIV", "european union": "EU27", "south sudan": "SSD", "brunei": "BRN", "moldova": "MDA",
    "united kingdom": "GBR", "netherlands": "NLD", "eswatini": "SWZ", "cabo verde": "CPV",
}


def iso(name):
    if not _NAMES:
        for c in _json(os.path.join(DATA, "countries", "index.json")):
            _NAMES[_fold(c["name"])] = c["c"]
            _DISPLAY.setdefault(c["c"], c["name"])
    f = _fold(name)
    return NAME_OVERRIDE.get(f) or _NAMES.get(f)


def _mt(v):
    # under 100 t, {:.3g} would print an exponent ("5.9e-05 Mt", review GL1.5): tonnes then
    return f"{v:,.0f} Mt" if v >= 100 else f"{v:.3g} Mt" if v >= 1e-4 or v <= 0 else f"{v * 1e6:,.0f} t"


def _name(code):
    if not _NAMES:
        iso("x")
    n = _DISPLAY.get(code, code)
    return "the " + n if n.startswith(("United ", "Central African", "Dominican")) or n in THE else n


THE = {"Bahamas", "Comoros", "Falkland Islands", "Maldives", "Netherlands", "Philippines", "Seychelles", "Solomon Islands"}


# ---------------------------------------------------------------- readers of raw/
def psd_table(raw=None):
    """{(group, attribute, market year): {iso: kt}} for the PSD commodities of PSD_GROUPS, or None.
    raw: the raw/ folder, read at call time (default: RAW)."""
    path = os.path.join(raw or RAW, "usda", "psd_csv", "psd_alldata.csv")
    if not os.path.exists(path):
        return None
    p = pd.read_csv(path, encoding="latin-1", usecols=["Commodity_Description", "Country_Name", "Market_Year",
                                                       "Attribute_Description", "Unit_Description", "Value"])
    p = p[p["Commodity_Description"].isin(PSD_GROUPS.values()) & p["Attribute_Description"].isin(["Exports", "Imports"])]
    back = {v: k for k, v in PSD_GROUPS.items()}
    out = {}
    for r in p.itertuples(index=False):
        code, f = iso(r.Country_Name), PSD_KT.get(r.Unit_Description)
        if code and f:
            out.setdefault((back[r.Commodity_Description], r.Attribute_Description, int(r.Market_Year)), {})[code] = r.Value * f
    return out


def eia_series(keys, raw=None):
    """{(series, unit): {code: {year: value}}} of annual EIA INTL series, or None without the file."""
    path = os.path.join(raw or RAW, "eia", "INTL.txt")
    if not os.path.exists(path):
        return None
    out = {k: {} for k in keys}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if '"series_id"' not in line or '.A"' not in line[:60]:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            parts = o["series_id"][5:-2].split("-")
            if len(parts) != 4 or (parts[0] + "-" + parts[1], parts[3]) not in out:
                continue
            out[(parts[0] + "-" + parts[1], parts[3])][parts[2]] = {int(y): float(v) for y, v in o["data"] if isinstance(v, (int, float))}
    return out


def _letters(s):
    return re.sub(r"[^A-Z]", "", s.upper())  # the chapter names carry a dash that the file's encoding garbles


def usgs_table(raw=None):
    """({(group, year): {iso: value in thousand tonnes}}, file name) for USGS_K10, or None."""
    raw = raw or RAW
    files = sorted(f for f in (os.listdir(os.path.join(raw, "usgs")) if os.path.isdir(os.path.join(raw, "usgs")) else [])
                   if re.fullmatch(r"MCS\d{4}_Commodities_Data\.csv", f))
    if not files:
        return None
    u = pd.read_csv(os.path.join(raw, "usgs", files[-1]), encoding="latin-1", dtype=str)
    u = u[u["Section"].fillna("").str.startswith("World") & (u["Statistics"] == "Production")]
    out = {}
    for g, (chapter, detail, _, _) in USGS_K10.items():
        x = u[(u["MCS chapter"].fillna("").map(_letters) == _letters(chapter)) & (u["Statistics_detail"] == detail)]
        for r in x.itertuples(index=False):
            v = str(r.Value).replace(",", "").strip()
            if not re.fullmatch(r"\d+(\.\d+)?", v) or r.Country in ("World total", "Other countries"):
                continue
            code = iso(r.Country)
            if code:
                out.setdefault((g, int(r.Year)), {})[code] = float(v)
    return out, files[-1]


# ---------------------------------------------------------------- checks
def _eu(s):
    return s.where(~s.isin(EU27), "EU27")


def k1(df, year, psd):
    out = []
    for g in PSD_GROUPS:
        x = df[(df["group"] == g) & (df["year"] == year)]
        x = x.assign(oo=_eu(x["o"]), dd=_eu(x["d"]))
        x = x[~((x["oo"] == "EU27") & (x["dd"] == "EU27"))]
        for side, attr, col in (("exports", "Exports", "oo"), ("imports", "Imports", "dd")):
            a, b = psd.get((g, attr, year - 1), {}), psd.get((g, attr, year), {})
            tot = x.groupby(col)["t"].sum() / 1e3
            for c, v in tot.sort_values(ascending=False).head(12).items():
                if c not in a or c not in b or max(a[c], b[c]) <= 0:
                    continue
                lo, hi = min(a[c], b[c]), max(a[c], b[c])
                if not (v < 0.75 * lo or (v > 1.25 * hi and v - hi > 500)):
                    continue
                my = f"{year - 1}/{year % 100:02d}", f"{year}/{(year + 1) % 100:02d}"
                out.append({"check": "K1", "group": g, "year": year, "side": side, "country": c, "value": round(v / 1e3, 3),
                            "reference": [round(lo / 1e3, 3), round(hi / 1e3, 3)], "ratio": round(v / (lo if v < lo else hi), 3),
                            "psd": {my[0]: round(a[c] / 1e3, 3), my[1]: round(b[c] / 1e3, 3)}, "level": "flag",
                            "text": (f"CEPII BACI {year}: {_mt(v / 1e3)} of {label(g)} {side} for {_name(c)}; USDA PSD: "
                                     f"{_mt(a[c] / 1e3)} ({my[0]}) and {_mt(b[c] / 1e3)} ({my[1]})")})
    return out


def k2(df, year, psd):
    out = []
    x = df[df["group"].isin(PSD_GROUPS) & (df["t"] >= 1e6) & (df["year"] <= year) & ~df["d"].isin(EU27)]
    for r in x.itertuples(index=False):
        a, b = psd.get((r.group, "Imports", r.year - 1), {}).get(r.d), psd.get((r.group, "Imports", r.year), {}).get(r.d)
        if a is None or b is None:
            continue
        hi = max(a, b)
        v = r.t / 1e3
        if v > 1.25 * hi and v - hi > 500:
            out.append({"check": "K2", "group": r.group, "year": int(r.year), "o": r.o, "d": r.d, "value": round(v / 1e3, 3),
                        "reference": round(hi / 1e3, 3), "ratio": round(v / hi, 3) if hi else None, "est": bool(r.imputed), "level": "flag",
                        "text": (f"{_mt(v / 1e3)} recorded from {_name(r.o)} to {_name(r.d)} in {r.year} (CEPII BACI), above "
                                 f"{_name(r.d)}'s total {label(r.group)} imports in USDA PSD ({_mt(hi / 1e3)} at most in "
                                 f"{r.year - 1}/{r.year % 100:02d} and {r.year}/{(r.year + 1) % 100:02d})")})
    return out


def barrels_per_tonne(eia):
    """EIA's own conversion: its crude production series for the United States exist both in thousand barrels per day
    and in thousand metric tons (1980 to 1999) and their ratio is constant. Read from the file, not typed."""
    bd, mt = eia[("57-1", "TBPD")].get("USA", {}), eia[("57-1", "MT")].get("USA", {})
    r = sorted(bd[y] * (366 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 365) / mt[y] for y in set(bd) & set(mt) if mt[y])
    return r[len(r) // 2] if r else None


def k3(df, year, eia):
    bpt = barrels_per_tonne(eia)
    if not bpt:
        raise ValueError("no barrels-per-tonne ratio in the EIA file")
    days = 366 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 365
    prod = eia[("57-1", "TBPD")]
    x = df[(df["group"] == "crude-oil") & (df["year"] == year)]
    exp = x.groupby("o")["t"].sum().sort_values(ascending=False).head(40) / 1e6
    est = x[x["imputed"]].groupby("o")["t"].sum() / 1e6
    out = []
    for c, v in exp.items():
        p = prod.get(c, {}).get(year)
        if not p or p <= 0:
            continue
        p = p * days / bpt / 1e3
        r = v / p
        if r < 0.95:
            continue
        out.append({"check": "K3", "group": "crude-oil", "year": year, "country": c, "value": round(v, 3), "reference": round(p, 3),
                    "ratio": round(r, 3), "est": round(float(est.get(c, 0.0)), 3), "level": "flag" if r > 1.05 else "watch",
                    "text": (f"crude oil exports of {_name(c)} in customs data ({_mt(v)} in {year}, CEPII BACI) are {r:.0%} of its "
                             f"production ({_mt(p)}, EIA International Energy Data, converted at {bpt:.2f} barrels per tonne, EIA's own ratio)")})
    return out


def k4(df, year, eia):
    out = []
    x = df[(df["group"] == "coal") & (df["year"] == year)]
    for side, key, col in (("exports", ("7-4", "MT"), "o"), ("imports", ("7-3", "MT"), "d")):
        for c, v in (x.groupby(col)["t"].sum().sort_values(ascending=False).head(15) / 1e6).items():
            e = eia[key].get(c, {}).get(year)
            if not e or e <= 0:
                continue
            e /= 1e3
            if abs(v / e - 1) > 0.25:
                out.append({"check": "K4", "group": "coal", "year": year, "side": side, "country": c, "value": round(v, 3),
                            "reference": round(e, 3), "ratio": round(v / e, 3), "level": "flag",
                            "text": f"coal {side} of {_name(c)} in {year}: {_mt(v)} in customs data (CEPII BACI), {_mt(e)} in EIA International Energy Data"})
    return out


def _continuity(df, col, check, years):
    out = []
    e = df.groupby(["group", col, "year"])["t"].sum().unstack().reindex(columns=years, fill_value=0).fillna(0) / 1e6
    tot = df.groupby(["group", "year"])["t"].sum().unstack().reindex(columns=years, fill_value=0) / 1e6
    side = "exports" if col == "o" else "imports"
    for (g, c), r in e.iterrows():
        for i, y in enumerate(years):
            a = r[years[i - 1]] if i > 0 else None
            b = r[years[i + 1]] if i + 1 < len(years) else None
            v = r[y]
            if a is None:
                continue
            share = lambda yy, val: val >= 0.02 * tot.loc[g, yy]  # noqa: E731
            if check == "K6":
                if b is not None and share(years[i - 1], a) and share(years[i + 1], b) and v < 0.25 * (a + b) / 2:
                    kind, ref = "gap", [round(a, 3), round(b, 3)]
                elif b is None and share(years[i - 1], a) and v < 0.25 * a:
                    kind, ref = "gap", [round(a, 3)]
                elif b is not None and min(a, b) > 0 and v > 2.5 * max(a, b) and v - max(a, b) >= 3:
                    kind, ref = "spike", [round(a, 3), round(b, 3)]
                else:
                    continue
            else:
                if b is not None and min(a, b) > 0 and v > 1.5 * max(a, b) and v - max(a, b) >= 3 and share(y, v):
                    kind, ref = "spike", [round(a, 3), round(b, 3)]
                else:
                    continue
            around = " and ".join(_mt(x) for x in ref)
            yrs = f"{years[i - 1]}" + (f" and {years[i + 1]}" if b is not None else "")
            out.append({"check": check, "group": g, "year": int(y), "side": side, "country": c, "kind": kind, "value": round(v, 3),
                        "reference": ref, "level": "flag",
                        "text": f"{cap_label(g)} {side} of {_name(c)}: {_mt(v)} in {y} against {around} in {yrs} (CEPII BACI)"})
    return out


def k8(df, year):
    p = df[df["year"].isin([year - 1, year])].groupby(["group", "o", "d", "year"])["t"].sum().unstack().reindex(columns=[year - 1, year]).fillna(0) / 1e6
    a, b = p[year - 1], p[year]
    out = []
    for (g, o, d), x, y in zip(p.index, a, b):
        if x >= 2 and y < 0.5 * x:
            kind, text = "fall", f"{1 - y / x:.0%} below {year - 1}"
        elif y > 2 * x and y - x >= 2:
            kind, text = "rise", (f"{y / x:.1f} times {year - 1}" if x > 0 else f"no record in {year - 1}")
        else:
            continue
        out.append({"check": "K8", "group": g, "year": year, "o": o, "d": d, "kind": kind, "value": round(y, 3), "reference": round(x, 3),
                    "ratio": round(y / x, 3) if x else None, "level": "flag",
                    "text": f"{cap_label(g)} from {_name(o)} to {_name(d)}: {_mt(y)} in {year}, {text} ({_mt(x)}; CEPII BACI)"})
    return out


def k10(df, year, usgs):
    table, fname = usgs
    out = []
    for g, (_, _, factor, basis) in USGS_K10.items():
        uy = year if (g, year) in table else max((yy for gg, yy in table if gg == g), default=None)
        if uy is None:
            continue
        prod = table[(g, uy)]
        x = df[(df["group"] == g) & (df["year"] == year)]
        for c, t in x.groupby("o")["t"].sum().sort_values(ascending=False).head(15).items():
            v = t * factor / 1e3  # thousand tonnes on the USGS basis
            p = prod.get(c)
            if p is None:
                if t >= 0.5e6:
                    out.append({"check": "K10", "group": g, "year": year, "country": c, "kind": "unlisted", "value": round(t / 1e6, 3),
                                "reference": None, "ratio": None, "level": "flag", "usgs": fname,
                                "text": f"{cap_label(g)} exports of {_name(c)}: {_mt(t / 1e6)} in {year} (CEPII BACI); the country is not a listed producer in the USGS Mineral Commodity Summaries ({uy})"})
                continue
            if p > 0 and v > 1.05 * p:
                out.append({"check": "K10", "group": g, "year": year, "country": c, "kind": "above-production", "value": round(t / 1e6, 3),
                            "reference": round(p / 1e3, 3), "ratio": round(v / p, 3), "level": "flag", "usgs": fname,
                            "text": (f"{cap_label(g)} exports of {_name(c)} in customs data ({_mt(t / 1e6)} in {year}, CEPII BACI) are {v / p:.0%} of its "
                                     f"production in the USGS Mineral Commodity Summaries ({_mt(p / 1e3)}{USGS_UNIT.get(g, '')} in {uy}); {basis}")})
    return out


def k11(df, year):
    """QA only: LNG exporters without an export terminal and crude importers of 1 Mt or more without a refinery in the layers."""
    out = []
    try:
        lng = _json(os.path.join(DATA, "infrastructure", "lng.geojson"))["features"]
        ref = _json(os.path.join(DATA, "infrastructure", "refineries.geojson"))["features"]
    except (OSError, ValueError, KeyError):
        return out
    term = {f["properties"].get("c") for f in lng if f["properties"].get("type") == "lng-export"}
    refc = {f["properties"].get("c") for f in ref}
    x = df[df["year"] == year]
    for c, v in (x[x["group"] == "lng"].groupby("o")["t"].sum() / 1e6).items():
        if v >= 0.5 and c not in term:
            out.append({"check": "K11", "group": "lng", "year": year, "country": c, "kind": "no-lng-terminal", "value": round(v, 3), "level": "qa",
                        "text": f"LNG exports of {_name(c)}: {_mt(v)} in {year}, no LNG export terminal for it in data/infrastructure/lng.geojson"})
    for c, v in (x[x["group"] == "crude-oil"].groupby("d")["t"].sum() / 1e6).items():
        if v >= 1 and c not in refc:
            out.append({"check": "K11", "group": "crude-oil", "year": year, "country": c, "kind": "no-refinery", "value": round(v, 3), "level": "qa",
                        "text": f"crude oil imports of {_name(c)}: {_mt(v)} in {year}, no refinery for it in data/infrastructure/refineries.geojson"})
    return out


# groups of one product, whose pairs should be priced alike (a grade difference is small beside a factor 2): refined copper
# (HS 7402, 7403), unwrought aluminium, refined zinc, lead and tin, alumina. Ores and intermediates mix grades and are left out.
UV_GROUPS = {"aluminium": "unwrought aluminium (HS 7601)", "copper-refined": "refined and blister copper (HS 7402, 7403)",
             "zinc-metal": "unwrought zinc (HS 7901)", "lead-metal": "unwrought lead (HS 7801)", "tin-metal": "unwrought tin (HS 8001)",
             "alumina": "alumina (HS 281820)",
             # the other groups with lanes of package L1 (review GL1.10): concentrates and compounds mix grades, so a pair found here
             # is worded as a hypothesis by its caveat, like the others
             "lead-ore": "lead ores and concentrates (HS 2607)", "tin-ore": "tin ores and concentrates (HS 2609)",
             "cobalt": "cobalt ores, intermediates and unwrought cobalt (HS 2605, 810510)",
             "lithium": "lithium carbonate and lithium oxide and hydroxide (HS 283691, 282520)",
             "rare-earths": "rare-earth metals and compounds (HS 280530, 284610, 284690)"}
UV_RATIO = 0.5   # a pair declared below this share of the group's usual unit value
UV_SHARE = 0.01  # and carrying at least this share of the group's tonnage ...
UV_MIN_T = 10e3  # ... and at least this many tonnes


def k13(df, year):
    """K13. Pairs of one product declared far below the other flows of that product (audit C-043: 0.54 Mt of 'aluminium' from the
    United States to Malaysia at 1,034 USD per tonne, when the other flows average about 2,500). The reference is the
    tonne-weighted median unit value of the group-year, without the pairs whose tonnage the atlas re-estimated from their value.
    Nothing is changed: the pair is reported, and the caveat registry words it as a hypothesis."""
    out = []
    if "usd" not in df.columns:  # a frame without the declared value has nothing to compare
        return out
    for g in UV_GROUPS:
        x = df[(df["group"] == g) & (df["year"] == year) & (df["t"] > 0) & (df["usd"] > 0)]
        if "imputed" in x:
            x = x[~x["imputed"]]
        if x.empty:
            continue
        uv = x["usd"] * 1000 / x["t"]
        order = uv.argsort().to_numpy()
        cum = x["t"].to_numpy()[order].cumsum()
        ref = float(uv.to_numpy()[order][int(cum.searchsorted(cum[-1] / 2))])
        total = float(x["t"].sum())
        low = x[(uv < UV_RATIO * ref) & (x["t"] >= max(UV_MIN_T, UV_SHARE * total))]
        for r in low.sort_values("t", ascending=False).itertuples():
            v = r.usd * 1000 / r.t
            out.append({"check": "K13", "group": g, "year": year, "o": r.o, "d": r.d, "value": round(r.t / 1e6, 3), "reference": round(ref),
                        "unitValue": round(v), "ratio": round(v / ref, 3), "level": "flag",
                        "text": (f"{UV_GROUPS[g][:1].upper()}{UV_GROUPS[g][1:]} from {_name(r.o)} to {_name(r.d)}: {_mt(r.t / 1e6)} in {year} (CEPII BACI), declared at {v:,.0f} USD per tonne, "
                                 f"{v / ref:.0%} of the tonne-weighted median of the group ({ref:,.0f})")})
    return out


def detour(pairs, year, min_t=0.5e6, ratio=2.5):
    """K12. pairs: iterable of dicts with group, o, d, t (tonnes), nm (main route) and gc_nm (great-circle distance of the
    two ports), and optionally load and dis. Called by the lane builder after routing."""
    out = []
    for p in pairs:
        if p["t"] >= min_t and p.get("gc_nm") and p["nm"] > ratio * p["gc_nm"]:
            ports = f" ({p['load']} to {p['dis']})" if p.get("load") else ""
            out.append({"check": "K12", "group": p["group"], "year": year, "o": p["o"], "d": p["d"], "value": round(p["t"] / 1e6, 3),
                        "reference": p["gc_nm"], "ratio": round(p["nm"] / p["gc_nm"], 2), "level": "qa",
                        "text": (f"{cap_label(p['group'])} from {_name(p['o'])} to {_name(p['d'])}{ports}: main route {p['nm']:,} nm, "
                                 f"{p['nm'] / p['gc_nm']:.1f} times the great-circle distance; check the gateways")})
    return out


def run(df, year, raw=None, ran=None):
    """All checks on a frame returned by clean(). raw: the raw/ folder (default: the repository's). ran: a set that
    receives the ids of the checks that ran (the others skipped for want of a readable file). Never raises."""
    raw = raw or RAW
    ran = set() if ran is None else ran
    out = []
    try:
        year = int(year)  # a numpy integer would not serialise in save()
    except (TypeError, ValueError) as e:
        print(f"checks: none run (year {year!r}: {e})")
        return out

    def do(cid, fn, *args):
        try:
            out.extend(fn(*args))
            ran.add(cid)
        except Exception as e:  # a check must never stop a build
            print(f"checks: {cid} skipped ({type(e).__name__}: {e})")

    def read(what, fn, *args):
        """A reader of raw/ that fails (a file with another layout) leaves its checks not run, as an absent file does."""
        try:
            return fn(*args)
        except Exception as e:
            print(f"checks: {what} not read ({type(e).__name__}: {e})")
            return None

    psd = read("USDA PSD", psd_table, raw)
    if psd:
        do("K1", k1, df, year, psd)
        do("K2", k2, df, year, psd)
    eia = read("EIA INTL", eia_series, [("57-1", "MT"), ("57-1", "TBPD"), ("7-4", "MT"), ("7-3", "MT")], raw) or {}
    # a file that holds none of a check's series has not checked anything: the check is not run
    if eia.get(("57-1", "MT")) and eia.get(("57-1", "TBPD")):
        do("K3", k3, df, year, eia)
    if eia.get(("7-4", "MT")) or eia.get(("7-3", "MT")):
        do("K4", k4, df, year, eia)
    years = read("years", lambda: sorted(int(y) for y in df["year"].unique() if y >= 2004))
    if years is not None:
        do("K6", _continuity, df, "o", "K6", years)
        do("K7", _continuity, df, "d", "K7", years)
    do("K8", k8, df, year)
    usgs = read("USGS MCS", usgs_table, raw)
    if usgs and usgs[0]:
        do("K10", k10, df, year, usgs)
    do("K11", k11, df, year)
    do("K13", k13, df, year)
    return out


def merge(previous, new, ran):
    """Records to write: the new ones, plus the previous records of the checks that did not run this time."""
    return [r for r in previous if r.get("check") not in ran] + list(new)


def load(path=TRADE_CHECKS):
    try:
        return _json(path).get("findings", [])
    except (OSError, ValueError, AttributeError):
        return []


def save(records, ran, year, path=TRADE_CHECKS):
    """Writes trade_checks.json, keeping the previous records of the checks that did not run (single writer: build_lanes.py)."""
    recs = merge(load(path), records, ran)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"year": int(year), "findings": recs}, f, ensure_ascii=False, indent=0)
    return recs
