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
    runner of the scheduled jobs; merge() then keeps the previous records of those checks.
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
"""
import json
import os
import re
import unicodedata

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
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
}
# kt per PSD unit: 1000 bales of 480 lb (1 lb = 0.45359237 kg by definition), 1000 bags of 60 kg
PSD_KT = {"(1000 480 lb. Bales)": 480 * 0.45359237 / 1000, "(1000 60 KG BAGS)": 0.06, "(1000 MT)": 1.0}

# Standard atomic weights (IUPAC): K2O content of pure potassium chloride and nitrogen content of urea
_K, _CL, _O, _C, _N, _H = 39.0983, 35.453, 15.999, 12.011, 14.007, 1.008
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
         "phosphate-rock": "phosphate rock", "soymeal": "soybean meal", "soyoil": "soybean oil"}


def label(g):
    return LABEL.get(g, g.replace("-", " "))


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
    return f"{v:,.0f} Mt" if v >= 100 else f"{v:.3g} Mt"


def _name(code):
    if not _NAMES:
        iso("x")
    n = _DISPLAY.get(code, code)
    return "the " + n if n.startswith(("United ", "Central African", "Dominican")) or n in THE else n


THE = {"Bahamas", "Comoros", "Falkland Islands", "Maldives", "Netherlands", "Philippines", "Seychelles", "Solomon Islands"}


# ---------------------------------------------------------------- readers of raw/
def psd_table(raw=RAW):
    """{(group, attribute, market year): {iso: kt}} for the PSD commodities of PSD_GROUPS, or None."""
    path = os.path.join(raw, "usda", "psd_csv", "psd_alldata.csv")
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


def eia_series(keys, raw=RAW):
    """{(series, unit): {code: {year: value}}} of annual EIA INTL series, or None without the file."""
    path = os.path.join(raw, "eia", "INTL.txt")
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


def usgs_table(raw=RAW):
    """{(group, year): ({iso: value in thousand tonnes}, set of USGS names not mapped)} for USGS_K10, or None."""
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
                        "text": f"{label(g)} {side} of {_name(c)}: {_mt(v)} in {y} against {around} in {yrs} (CEPII BACI)"})
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
                    "text": f"{label(g)} from {_name(o)} to {_name(d)}: {_mt(y)} in {year}, {text} ({_mt(x)}; CEPII BACI)"})
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
                                "text": f"{label(g)} exports of {_name(c)}: {_mt(t / 1e6)} in {year} (CEPII BACI); the country is not a listed producer in the USGS Mineral Commodity Summaries ({uy})"})
                continue
            if p > 0 and v > 1.05 * p:
                out.append({"check": "K10", "group": g, "year": year, "country": c, "kind": "above-production", "value": round(t / 1e6, 3),
                            "reference": round(p / 1e3, 3), "ratio": round(v / p, 3), "level": "flag", "usgs": fname,
                            "text": (f"{label(g)} exports of {_name(c)} in customs data ({_mt(t / 1e6)} in {year}, CEPII BACI) are {v / p:.0%} of its "
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


def detour(pairs, year, min_t=0.5e6, ratio=2.5):
    """K12. pairs: iterable of dicts with group, o, d, t (tonnes), nm (main route) and gc_nm (great-circle distance of the
    two ports), and optionally load and dis. Called by the lane builder after routing."""
    out = []
    for p in pairs:
        if p["t"] >= min_t and p.get("gc_nm") and p["nm"] > ratio * p["gc_nm"]:
            ports = f" ({p['load']} to {p['dis']})" if p.get("load") else ""
            out.append({"check": "K12", "group": p["group"], "year": year, "o": p["o"], "d": p["d"], "value": round(p["t"] / 1e6, 3),
                        "reference": p["gc_nm"], "ratio": round(p["nm"] / p["gc_nm"], 2), "level": "qa",
                        "text": (f"{label(p['group'])} from {_name(p['o'])} to {_name(p['d'])}{ports}: main route {p['nm']:,} nm, "
                                 f"{p['nm'] / p['gc_nm']:.1f} times the great-circle distance; check the gateways")})
    return out


def run(df, year, raw=None, ran=None):
    """All checks on a frame returned by clean(). raw: the raw/ folder (default: the repository's). ran: a set that
    receives the ids of the checks that ran (the others skipped for want of a file). Never raises on a finding."""
    raw = raw or RAW
    ran = set() if ran is None else ran
    out = []

    def do(cid, fn, *args):
        try:
            out.extend(fn(*args))
            ran.add(cid)
        except Exception as e:  # a check must never stop a build
            print(f"checks: {cid} skipped ({type(e).__name__}: {e})")

    psd = psd_table(raw)
    if psd:
        do("K1", k1, df, year, psd)
        do("K2", k2, df, year, psd)
    eia = eia_series([("57-1", "MT"), ("57-1", "TBPD"), ("7-4", "MT"), ("7-3", "MT")], raw)
    if eia:
        do("K3", k3, df, year, eia)
        do("K4", k4, df, year, eia)
    years = sorted(int(y) for y in df["year"].unique() if y >= 2004)
    do("K6", _continuity, df, "o", "K6", years)
    do("K7", _continuity, df, "d", "K7", years)
    do("K8", k8, df, year)
    usgs = usgs_table(raw)
    if usgs:
        do("K10", k10, df, year, usgs)
    do("K11", k11, df, year)
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
        json.dump({"year": year, "findings": recs}, f, ensure_ascii=False, indent=0)
    return recs
