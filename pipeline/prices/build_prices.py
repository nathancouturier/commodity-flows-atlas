"""
Build price history files from the World Bank Pink Sheet (monthly, since 1960, and the annual workbook for the real
prices) and the EIA daily spot prices; the Freight family (BLS, Dallas Fed, New York Fed) through freight_indicators.py.

    python pipeline/prices/build_prices.py <pinksheet_monthly.xlsx> <eia_spot_dir> [<pinksheet_annual.xlsx>]

Outputs
  data/prices/index.json        list of series (PriceSeriesMeta), written compactly
  data/prices/figures.json      per commodity, the first series with its board figures: all the key figure on a
                                commodity page needs (the page does not load the index)
  data/prices/<id>.json         packed series: monthly {start, v[]}, daily {d[] days since epoch, v[]},
                                annual {start "YYYY", v[]}

What the builder adds to the bare numbers, all of it read from the source files
  basis, breaks   what a Pink Sheet series measures and the dates its basis changed, read from the workbook's
                  "Description" sheet (basis.py); EIA series carry the description EIA writes in the file
  annual          calendar years whose twelve monthly values are identical. That is what is observed: the source may
                  publish one price a year there, or a price that did not move (gold reads 35.00 in 1960 to 1967); only the
                  iron ore row of the Description sheet says "annual contract prices" and has its own series
  est             months the source itself marks as estimates
  stats           last value and its date, changes over 1 week (daily series), 1 month, 3 months, year to date and
                  1 year, and the position in the 52-week range (the last 12 months for monthly series), for the
                  price board; arithmetic on the published figures
  real            id of the annual real-price counterpart (constant 2010 US dollars, deflated by the World Bank's MUV
                  index, sheet "Annual Prices (Real)" of the annual workbook)

Iron ore: the Pink Sheet column mixes the Brazilian annual contract price in US cents per dmtu (before the spot
series starts) with the CFR China spot price in US dollars per dry tonne. The two never share a series: the spot
price keeps "iron-ore-m" and the contract years become "iron-ore-contract-a" (annual).

Validation: each series must have at least 24 points and a finite last value (a negative price is a price: WTI
closed at -36.98 on 20 April 2020). A series failing validation keeps its previous file (graceful fallback).
A mapped column or description row that is missing aborts the build (nothing is written): a renamed header must
fail the update, not freeze a series. check_freshness() names the series whose last observation did not advance
as fast as the cadence of its source allows; the weekly job records them in data/_status/ (fetch_prices.py).
mark_closed() marks `closed` a daily or monthly series that ends far behind the newest series of its own source
(the publisher stopped it): it is reported once, shown as closed, and no longer checked.
"""
import bisect
import json
import math
import os
import re
import sys
from datetime import date, datetime, timedelta

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import basis as B  # noqa: E402
import freight_indicators as FI  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "data", "prices")
ANNUAL_XLSX = os.path.join(ROOT, "raw", "worldbank", "CMO-Historical-Data-Annual.xlsx")

# Pink Sheet column header (without asterisks and surrounding spaces) -> (series id, commodity id, display name, unit)
PINK = {
    "Crude oil, Brent": ("brent-m", "crude-oil", "Brent crude", "USD/bbl"),
    "Crude oil, WTI": ("wti-m", "crude-oil", "WTI crude", "USD/bbl"),
    "Crude oil, Dubai": ("dubai-m", "crude-oil", "Dubai crude", "USD/bbl"),
    "Crude oil, average": ("crude-avg-m", "crude-oil", "Crude oil, average of Brent, Dubai and WTI", "USD/bbl"),
    "Natural gas, US": ("hh-m", "natural-gas", "Natural gas, US (Henry Hub)", "USD/MMBtu"),
    "Natural gas, Europe": ("ttf-m", "natural-gas", "Natural gas, Europe (World Bank series; Dutch TTF hub basis in recent years)", "USD/MMBtu"),
    "Natural gas index": ("ng-index-m", "index", "Natural gas price index (Europe, US, Japan LNG)", "index (2010 = 100)"),
    "Liquefied natural gas, Japan": ("lng-japan-m", "lng", "LNG, Japan import price", "USD/MMBtu"),
    "Coal, Australian": ("coal-aus-m", "thermal-coal", "Thermal coal, Australia (Newcastle)", "USD/t"),
    "Coal, South African": ("coal-zaf-m", "thermal-coal", "Thermal coal, South Africa (Richards Bay)", "USD/t"),
    "Cocoa": ("cocoa-m", "cocoa", "Cocoa", "USD/kg"),
    "Coffee, Arabica": ("arabica-m", "coffee", "Coffee, Arabica", "USD/kg"),
    "Coffee, Robusta": ("robusta-m", "coffee", "Coffee, Robusta", "USD/kg"),
    "Palm oil": ("palm-oil-m", "palm-oil", "Palm oil", "USD/t"),
    "Palm kernel oil": ("palm-kernel-oil-m", "palm-kernel-oil", "Palm kernel oil", "USD/t"),
    "Soybeans": ("soybeans-m", "soybeans", "Soybeans", "USD/t"),
    "Soybean oil": ("soyoil-m", "soyoil", "Soybean oil", "USD/t"),
    "Soybean meal": ("soymeal-m", "soymeal", "Soybean meal", "USD/t"),
    "Rapeseed oil": ("rapeseed-oil-m", "rapeseed", "Rapeseed oil", "USD/t"),
    "Sunflower oil": ("sunflower-oil-m", "sunflower", "Sunflower oil", "USD/t"),
    "Coconut oil": ("coconut-oil-m", "coconut-oil", "Coconut oil", "USD/t"),
    "Groundnut oil": ("groundnut-oil-m", "groundnut-oil", "Groundnut oil", "USD/t"),
    "Fish meal": ("fish-meal-m", "fish-meal", "Fish meal", "USD/t"),
    "Maize": ("maize-m", "corn", "Maize (US Gulf)", "USD/t"),
    # barley and sorghum (M-023): the Pink Sheet series stop in August 2020; they are published to that month and marked closed
    # by mark_closed(), which says so on the page
    "Barley": ("barley-m", "barley", "Barley (feed, US; Canadian before May 2012)", "USD/t"),
    "Sorghum": ("sorghum-m", "sorghum", "Sorghum (US Gulf)", "USD/t"),
    "Rice, Thai 5%": ("rice-thai-m", "rice", "Rice, Thai 5%", "USD/t"),
    "Rice, Thai 25%": ("rice-thai25-m", "rice", "Rice, Thai 25%", "USD/t"),
    "Rice, Thai A.1": ("rice-thai-a1-m", "rice", "Rice, Thai 100% broken (A.1)", "USD/t"),
    "Rice, Viet Namese 5%": ("rice-viet-m", "rice", "Rice, Vietnamese 5%", "USD/t"),
    "Wheat, US HRW": ("wheat-hrw-m", "wheat", "Wheat, US HRW", "USD/t"),
    "Wheat, US SRW": ("wheat-srw-m", "wheat", "Wheat, US SRW", "USD/t"),
    "Sugar, world": ("sugar-m", "sugar", "Sugar, world", "USD/kg"),
    "Sugar, EU": ("sugar-eu-m", "sugar", "Sugar, EU import price", "USD/kg"),
    "Sugar, US": ("sugar-us-m", "sugar", "Sugar, US", "USD/kg"),
    "Cotton, A Index": ("cotton-m", "cotton", "Cotton, A Index", "USD/kg"),
    "Phosphate rock": ("phosrock-m", "phosphate", "Phosphate rock", "USD/t"),
    "DAP": ("dap-m", "phosphate", "DAP", "USD/t"),
    "TSP": ("tsp-m", "phosphate", "TSP (triple superphosphate)", "USD/t"),
    "Urea": ("urea-m", "urea", "Urea", "USD/t"),
    "Potassium chloride": ("potash-m", "potash", "Potassium chloride (potash)", "USD/t"),
    "Aluminum": ("aluminium-m", "aluminium", "Aluminium", "USD/t"),
    "Iron ore, cfr spot": ("iron-ore-m", "iron-ore", "Iron ore, CFR China spot", "USD/dry t"),
    "Copper": ("copper-m", "copper", "Copper", "USD/t"),
    "Lead": ("lead-m", "lead", "Lead", "USD/t"),
    "Tin": ("tin-m", "tin", "Tin", "USD/t"),
    "Nickel": ("nickel-m", "nickel", "Nickel", "USD/t"),
    "Zinc": ("zinc-m", "zinc", "Zinc", "USD/t"),
    "Gold": ("gold-m", "gold", "Gold", "USD/troy oz"),
    "Platinum": ("platinum-m", "pgm", "Platinum", "USD/troy oz"),
    "Silver": ("silver-m", "silver", "Silver", "USD/troy oz"),
}

# Pink Sheet columns left out, and why (M-066): tea, rubber, timber, meat, bananas, oranges, shrimp, tobacco and
# groundnuts belong to no commodity or product of the atlas. Barley and sorghum stop in August 2020 and were left out
# for that; they are published, closed, since M-023 gave them a page.
PINK_LEFT_OUT = {
    "Groundnuts": "no atlas commodity or close product",
    "Tea, avg 3 auctions": "no atlas commodity",
    "Tea, Colombo": "no atlas commodity",
    "Tea, Kolkata": "no atlas commodity",
    "Tea, Mombasa": "no atlas commodity",
    "Banana, Europe": "no atlas commodity",
    "Banana, US": "no atlas commodity",
    "Orange": "no atlas commodity",
    "Beef": "no atlas commodity",
    "Chicken": "no atlas commodity",
    "Lamb": "no atlas commodity",
    "Shrimps, Mexican": "no atlas commodity; the series stops in October 2023",
    "Tobacco, US import u.v.": "no atlas commodity",
    "Logs, Cameroon": "no atlas commodity",
    "Logs, Malaysian": "no atlas commodity",
    "Sawnwood, Cameroon": "no atlas commodity",
    "Sawnwood, Malaysian": "no atlas commodity",
    "Plywood": "no atlas commodity",
    "Rubber, TSR20": "no atlas commodity",
    "Rubber, RSS3": "no atlas commodity",
}

# Commodity ids of the series that have no page in the atlas: listed in the series picker and on the price board,
# not linked to a page. Value: the family they are grouped with.
NO_PAGE = {
    "index": "index",
    "coconut-oil": "softs",
    "palm-kernel-oil": "softs",
    "groundnut-oil": "softs",
    "fish-meal": "softs",
}

# Pink Sheet column -> start(s) of the "Description" rows that describe it (the first one gives the current basis)
PINK_DESC = {
    "Crude oil, Brent": "Crude oil, UK Brent",
    "Crude oil, WTI": "Crude oil, US, West Texas",
    "Crude oil, Dubai": "Crude oil, Dubai Fateh",
    "Crude oil, average": "Crude oil, average spot",
    "Natural gas, US": "Natural Gas (U.S.)",
    "Natural gas, Europe": "Natural Gas (Europe)",
    "Natural gas index": "Natural gas index",
    "Liquefied natural gas, Japan": "Liquefied natural gas (Japan)",
    "Coal, Australian": "Coal (Australia)",
    "Coal, South African": "Coal (South Africa)",
    "Cocoa": "Cocoa (ICCO)",
    "Coffee, Arabica": "Coffee, Arabica (ICO)",
    "Coffee, Robusta": "Coffee, Robusta (ICO)",
    "Palm oil": "Palm oil (Malaysia)",
    "Palm kernel oil": "Palmkernel oil",
    "Soybeans": "Soybeans,",
    "Soybean oil": "Soybean oil,",
    "Soybean meal": "Soybean meal,",
    "Rapeseed oil": "Rapeseed Oil",
    "Sunflower oil": "Sunflower oil",
    "Coconut oil": "Coconut oil",
    "Groundnut oil": "Peanut (Groundnut) oil",
    "Fish meal": "Fish meal",
    "Maize": "Maize (U.S.)",
    "Barley": "Barley (U.S.)",
    "Sorghum": "Sorghum (US)",
    "Rice, Thai 5%": "Rice (Thailand), 5% broken",
    "Rice, Thai 25%": "Rice (Thailand), 25% broken",
    "Rice, Thai A.1": "Rice (Thailand), 100% broken",
    "Rice, Viet Namese 5%": "Rice (Vietnam)",
    "Wheat, US HRW": "Wheat (U.S.), no. 2 hard red winter",
    "Wheat, US SRW": "Wheat (U.S.), no. 2, soft red winter",
    "Sugar, world": "Sugar (World)",
    "Sugar, EU": "Sugar (EU)",
    "Sugar, US": "Sugar (U.S.)",
    "Cotton, A Index": "Cotton (Cotton Outlook",
    "Phosphate rock": "Phosphate rock",
    "DAP": "DAP (diammonium",
    "TSP": "TSP (triple",
    "Urea": "Urea,",
    "Potassium chloride": "Potassium chloride (muriate",
    "Aluminum": "Aluminum (LME)",
    "Iron ore, cfr spot": "Iron ore (any origin) fines",
    "Copper": "Copper (LME)",
    "Lead": "Lead (LME)",
    "Tin": "Tin (LME)",
    "Nickel": "Nickel (LME)",
    "Zinc": "Zinc (LME)",
    "Gold": "Gold, spot",
    "Platinum": "Platinum,",
    "Silver": "Silver (UK)",
}
IRON_ORE_ROW = "Iron ore, spot in US dollar"  # the row that dates the end of the annual contract prices

# Monthly Indices sheet: the column's header text (the sheet spreads it over four rows) -> (series id, name)
INDEX_SERIES = {
    "Total Index": ("idx-total-m", "World Bank commodity price index, total"),
    "Energy": ("idx-energy-m", "World Bank energy price index"),
    "Non-energy": ("idx-nonenergy-m", "World Bank non-energy price index"),
    "Agriculture": ("idx-agriculture-m", "World Bank agriculture price index"),
    "Beverages": ("idx-beverages-m", "World Bank beverages price index"),
    "Food": ("idx-food-m", "World Bank food price index"),
    "Oils & Meals": ("idx-oils-meals-m", "World Bank oils and meals price index"),
    "Grains": ("idx-grains-m", "World Bank grains price index"),
    "Other Food": ("idx-other-food-m", "World Bank other food price index"),
    "Raw Materials": ("idx-raw-materials-m", "World Bank raw materials price index"),
    "Timber": ("idx-timber-m", "World Bank timber price index"),
    "Other Raw Mat.": ("idx-other-raw-m", "World Bank other raw materials price index"),
    "Fertilizers": ("idx-fertilizers-m", "World Bank fertilizers price index"),
    "Metals & Minerals": ("idx-metals-m", "World Bank metals and minerals price index"),
    "Base Metals (ex. iron ore)": ("idx-base-metals-m", "World Bank base metals price index (excluding iron ore)"),
    "Precious Metals": ("idx-precious-m", "World Bank precious metals price index"),
}

# EIA daily spot files -> (series id, commodity id, name, unit)
EIA = {
    "RBRTEd": ("brent-d", "crude-oil", "Brent crude, daily spot (FOB)", "USD/bbl"),
    "RWTCd": ("wti-d", "crude-oil", "WTI crude, daily spot (Cushing)", "USD/bbl"),
    "RNGWHHDd": ("hh-d", "natural-gas", "Henry Hub natural gas, daily spot", "USD/MMBtu"),
    "EER_EPMRU_PF4_Y35NY_DPGd": ("nyh-gasoline-d", "refined-products", "Gasoline, New York Harbor, daily spot", "USD/gal"),
    "EER_EPD2DXL0_PF4_Y35NY_DPGd": ("nyh-ulsd-d", "refined-products", "Ultra-low sulphur diesel, New York Harbor, daily spot", "USD/gal"),
    "EER_EPD2F_PF4_Y35NY_DPGd": ("nyh-heatingoil-d", "refined-products", "No. 2 heating oil, New York Harbor, daily spot", "USD/gal"),
    "EER_EPJK_PF4_RGC_DPGd": ("usgc-jet-d", "refined-products", "Jet fuel (kerosene), US Gulf Coast, daily spot", "USD/gal"),
    "EER_EPLLPA_PF4_Y44MB_DPGd": ("propane-mb-d", "lpg", "Propane, Mont Belvieu, daily spot", "USD/gal"),
}
# The series a commodity page, its price figure and the price drawer open on: the first series of the commodity in
# data/prices/index.json. Daily before monthly before annual decides first (a commodity that has a daily or a monthly
# series never opens on an annual one); this table decides between series of the same frequency, and every
# commodity with more than one series is named in it (a test fails for one that is not, so that a series added later
# is a choice and not the alphabetical order of the ids).
OPENS_ON = {
    "crude-oil": "brent-d",  # the daily spot benchmark of the commodity
    "natural-gas": "hh-d",  # the daily spot benchmark of the commodity
    "refined-products": "nyh-gasoline-d",  # the first of four daily New York Harbor and Gulf Coast spot series
    "coffee": "arabica-m",
    "rice": "rice-thai-m",  # the 5% broken grade, the benchmark column of the sheet; the other grades follow it
    "sugar": "sugar-m",  # the world price; the EU and US prices follow it
    "phosphate": "dap-m",
    "thermal-coal": "coal-aus-m",
    "wheat": "wheat-hrw-m",
    "iron-ore": "iron-ore-m",  # the spot series; the annual contract series before 2006 is closed
    "pgm": "platinum-m",  # monthly (World Bank); palladium and rhodium are annual (USGS) and follow it
    "bauxite": "usgs-bauxite-import-a",  # bauxite itself, not alumina, a product made from it
    "rare-earths": "usgs-ndpr-oxide-a",  # NdPr oxide, the price of the oxide the magnet industry buys; the others are single elements
    # cobalt: the US spot price of cathode (refined metal, S&P Global Platts Metals Week). Of the two cobalt rows of the
    # USGS file it is the one that names its product and its source; the LME cash row names neither.
    "cobalt": "usgs-cobalt-spot-a",
    # barley and sorghum: the closed monthly series, then the annual average that goes on after it (review GNC2.1)
    "barley": "barley-m",
    "sorghum": "sorghum-m",
    "graphite": "usgs-graphite-flake-a",  # flake, the grade the page's flake and powder code mostly holds; the other grades follow
    "urea": "urea-m",  # the Pink Sheet's urea; the USGS annual price of ammonia (FNCD) is a second product of the page and follows it
    "ferro-alloys": "usgs-ferrochromium-a",  # ferro-chromium, the alloy the page opens on; the 75% ferrosilicon follows it
}

# Pink Sheet series added after the first release (M-066): listed after the original benchmark of their commodity
ADDED = {"crude-avg-m", "ng-index-m", "palm-kernel-oil-m", "sunflower-oil-m", "coconut-oil-m", "groundnut-oil-m", "fish-meal-m",
         "rice-thai25-m", "rice-thai-a1-m", "rice-viet-m", "sugar-eu-m", "sugar-us-m", "tsp-m"}

# daily series -> the Pink Sheet monthly series of the same benchmark: it covers a month the daily file only partly
# has, and its real annual counterpart is the real price of the daily series
REAL_OF_DAILY = {"brent-d": "brent-m", "wti-d": "wti-m", "hh-d": "hh-m"}

# The "Freight" family (freight_indicators.py): the BLS producer price index for deep-sea freight from the cache of the
# BLS API (pipeline/cache/bls), the Dallas Fed and New York Fed indices from raw/dallasfed and raw/nyfed. None is a rate.
# A deviation from a trend or from an average crosses zero: a change in percent means nothing there, the board gets none.
DEVIATION_UNITS = ("% deviation from trend", "standard deviations from average")

EPOCH = date(1970, 1, 1)
# Cadences (see check_freshness): the jobs run weekly; the Pink Sheet is published in the first days of the month
DAILY_LATE_DAYS = 21  # a daily series more than three weeks behind today
DAILY_BEHIND_SOURCE_DAYS = 120  # or more than 120 days before the newest series of its source
MONTHLY_BEHIND_SOURCE_MONTHS = 6


class BuildError(Exception):
    """The inputs do not have the shape the builder maps: abort before anything is written."""


def norm(h):
    """A column header without the asterisks and spaces the workbook decorates it with."""
    return re.sub(r"\s+", " ", str(h).replace("*", " ")).strip()


def num(x):
    if x is None:
        return None
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x) if math.isfinite(x) else None
    s = str(x).strip().replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


# ---------------------------------------------------------------- statistics for the price board

def _add_months(d, n):
    k = d.year * 12 + d.month - 1 + n
    y, m = divmod(k, 12)
    m += 1
    last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day
    return date(y, m, min(d.day, last))


def board_stats(freq, times, values):
    """Last value and changes of one series, from its published figures.

    times: dates (monthly observations stamped on the first of the month, annual ones on 1 January); values: numbers
    or None. An annual series gets only the last value and the change on the previous year.
    chg keys: w (1 week, daily series only), m (1 month), q (3 months), ytd (since the last observation of the
    previous year), y (1 year), all in percent. A reference is the last observation on or before the target date,
    at most 7 days before it for a daily series, exactly that month for a monthly one; no reference, no figure.
    rng: lowest and highest value of the last 52 weeks (the last 12 months for a monthly series) and the position
    of the last value inside it, 0 to 1.
    """
    pts = [(t, v) for t, v in zip(times, values) if v is not None]
    if not pts:
        return None
    ts = [t for t, _ in pts]
    vs = [v for _, v in pts]
    tl, vl = ts[-1], vs[-1]
    daily = freq == "D"

    def ref(target):
        i = bisect.bisect_right(ts, target) - 1
        if i < 0:
            return None
        if daily:
            return vs[i] if (target - ts[i]).days <= 7 else None
        return vs[i] if (ts[i].year, ts[i].month) == (target.year, target.month) else None

    annual = freq == "A"
    if annual:  # one value a year: only the change on the previous year
        targets = {"y": _add_months(tl, -12)}
    else:
        targets = {"m": _add_months(tl, -1), "q": _add_months(tl, -3), "ytd": date(tl.year - 1, 12, 31 if daily else 1), "y": _add_months(tl, -12)}
    if daily:
        targets["w"] = tl - timedelta(days=7)
    chg = {}
    for k, target in targets.items():
        r = ref(target)
        if r is not None and r > 0 and vl >= 0:
            chg[k] = round((vl / r - 1) * 100, 2)
    out = {"last": {"v": vl, "t": tl.isoformat()[:4] if annual else tl.isoformat() if daily else tl.isoformat()[:7]}}
    if chg:
        out["chg"] = chg
    if annual:
        return out
    start = tl - timedelta(days=365) if daily else _add_months(tl, -11)
    win = [v for t, v in pts if t > start] if daily else [v for t, v in pts if t >= start]
    lo, hi = min(win), max(win)
    rng = {"lo": lo, "hi": hi}
    if hi > lo:
        rng["pos"] = round((vl - lo) / (hi - lo), 3)
    out["rng"] = rng
    return out


def month_times(start, n):
    y, m = int(start[:4]), int(start[5:7])
    return [date(y + (m - 1 + i) // 12, (m - 1 + i) % 12 + 1, 1) for i in range(n)]


# ---------------------------------------------------------------- years with twelve identical monthly values

def annual_runs(start, values):
    """[[first year, last year], ...] of the calendar years whose twelve monthly values are one and the same number.
    The key of the index is still `annual`; it records what is observed, not what the source says it publishes."""
    y0, m0 = int(start[:4]), int(start[5:7])
    by = {}
    for i, v in enumerate(values):
        by.setdefault(y0 + (m0 - 1 + i) // 12, []).append(v)
    flat = sorted(y for y, l in by.items() if len(l) == 12 and l[0] is not None and len(set(l)) == 1)
    runs = []
    for y in flat:
        if runs and runs[-1][1] == y - 1:
            runs[-1][1] = y
        else:
            runs.append([y, y])
    return runs


# ---------------------------------------------------------------- freshness

def _newest(metas):
    out = {}
    for m in metas:
        out[m["s"]] = max(out.get(m["s"], m["end"]), m["end"])
    return out


def _end_date(m):
    e = m["end"]
    if m["freq"] == "D":
        return date.fromisoformat(e)
    y, mo = int(e[:4]), int(e[5:7])
    return _add_months(date(y, mo, 1), 1) - timedelta(days=1)


def check_freshness(metas, today=None):
    """Series whose last observation did not advance as fast as their cadence allows. Returns [(source, id, why)].

    A daily series is late when it ends more than 21 days before today (the jobs are weekly and EIA publishes
    weekly), or more than 120 days before the newest series of its source. A monthly series is late once the month
    after its last one should have been published (mid-month, two months on), or when it ends more than 6 months
    before the newest series of its source. Annual series and series the source has closed are not checked."""
    today = today or date.today()
    newest = _newest([m for m in metas if m["freq"] in ("D", "M") and not m.get("closed") and not m.get("hidden")])
    out = []
    for m in metas:
        if m["freq"] not in ("D", "M") or m.get("closed") or m.get("hidden"):
            continue
        e = _end_date(m)
        ref = newest.get(m["s"])
        if m["freq"] == "D":
            if (today - e).days > DAILY_LATE_DAYS:
                out.append((m["s"], m["id"], f"ends {m['end']}, {(today - e).days} days ago"))
            elif ref and (date.fromisoformat(ref) - e).days > DAILY_BEHIND_SOURCE_DAYS:
                out.append((m["s"], m["id"], f"ends {m['end']}, {(date.fromisoformat(ref) - e).days} days before the newest series of its source"))
        else:
            first_missing = _add_months(date(e.year, e.month, 1), 1)  # the month that should follow
            if today > _add_months(first_missing, 1).replace(day=15):
                out.append((m["s"], m["id"], f"ends {m['end']}"))
            elif ref and (int(ref[:4]) * 12 + int(ref[5:7])) - (int(m["end"][:4]) * 12 + int(m["end"][5:7])) > MONTHLY_BEHIND_SOURCE_MONTHS:
                out.append((m["s"], m["id"], f"ends {m['end']}, more than {MONTHLY_BEHIND_SOURCE_MONTHS} months before the newest series of its source"))
    return out


def stale_by_source(metas, today=None):
    """{source id: "id ends ..., id ends ..."} for the sources that have late series."""
    out = {}
    for s, i, why in check_freshness(metas, today):
        out.setdefault(s, []).append(f"{i} {why}")
    return {s: "late series: " + "; ".join(l[:4]) + (f" (+{len(l) - 4})" if len(l) > 4 else "") for s, l in out.items()}


# ---------------------------------------------------------------- reading the Pink Sheet workbooks

class Pink:
    """The tables of a Pink Sheet monthly workbook that the builder uses."""

    def __init__(self, path):
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for name in ("Monthly Prices", "Monthly Indices", "Description"):
            if name not in wb.sheetnames:
                raise BuildError(f"no '{name}' sheet")
        rows = list(wb["Monthly Prices"].iter_rows(values_only=True))
        hi = next((i for i, r in enumerate(rows) if r and "Crude oil, Brent" in [str(c) for c in r if c]), None)
        if hi is None:
            raise BuildError("header row with 'Crude oil, Brent' not found")
        self.header = {norm(c): j for j, c in enumerate(rows[hi]) if c}
        self.data = [r for r in rows[hi + 2:] if r and isinstance(r[0], str) and re.fullmatch(r"\d{4}M\d{2}", r[0].strip())]
        self.updated = next((str(r[0]) for r in rows[:hi] if r and r[0] and "Updated" in str(r[0])), "")
        self.index_rows = list(wb["Monthly Indices"].iter_rows(values_only=True))
        # the index values are read from their own sheet: its rows, not those of 'Monthly Prices'
        self.index_data = [r for r in self.index_rows if r and isinstance(r[0], str) and re.fullmatch(r"\d{4}M\d{2}", r[0].strip())]
        self.index_title = " ".join(str(r[0]) for r in self.index_rows[:4] if r and r[0])
        self.descs, self.notes = B.read_description(wb["Description"].iter_rows(values_only=True))

    def check(self):
        """Problems that make the workbook unusable: missing columns, description rows, index columns."""
        out = [f"column '{c}' missing" for c in PINK if c not in self.header]
        for col, prefix in PINK_DESC.items():
            try:
                B.find(self.descs, prefix)
            except LookupError as e:
                out.append(str(e))
        try:
            B.find(self.descs, IRON_ORE_ROW)
        except LookupError as e:
            out.append(str(e))
        hdr = self.index_headers()
        names = set(hdr.values())
        out += [f"Monthly Indices column '{label}' missing" for label in INDEX_SERIES if label not in names]
        if "2010=100" not in self.index_title.replace(" ", ""):
            out.append("Monthly Indices is no longer a 2010 = 100 index")
        if [r[0].strip() for r in self.index_data] != [r[0].strip() for r in self.data]:
            out.append("Monthly Indices and Monthly Prices do not cover the same months")
        return out

    def index_headers(self):
        """column -> its header text. The sheet spreads the header over four rows (each name sits on the row of its
        level in the hierarchy), so the name of a column is the text found in it above the first month."""
        out = {}
        first = next((i for i, r in enumerate(self.index_rows) if r and isinstance(r[0], str) and re.fullmatch(r"\d{4}M\d{2}", r[0].strip())), 0)
        for r in self.index_rows[:first]:
            for j, c in enumerate(r):
                if j and isinstance(c, str) and norm(c):
                    out[j] = f"{out[j]} {norm(c)}" if j in out else norm(c)
        return out

    def column(self, j, rows=None):
        """[(month 'YYYY-MM', value or None)] of column j of the given rows (default: Monthly Prices), with the empty
        ends trimmed."""
        vals = [(r[0].strip().replace("M", "-"), num(r[j]) if j < len(r) else None) for r in (self.data if rows is None else rows)]
        ok = [i for i, (_, x) in enumerate(vals) if x is not None]
        if not ok:
            return []
        return vals[ok[0]: ok[-1] + 1]


def basis_note(basis_text, clauses):
    """The basis note of a series: the current basis as the source words it, and, where the dates of the source's own
    clauses overlap, the clauses quoted verbatim with the statement that they overlap (the atlas does not chain them)."""
    note = basis_text.rstrip(".") + "." if basis_text else ""
    clash, _ = B.overlapping(clauses)
    if clash:
        quoted = "; ".join(f"\u201c{c['raw']}\u201d" for c in clash)
        note += (f" The dates in the source overlap: {quoted}. The atlas draws no break from the clause that starts inside another"
                 " period and does not chain them.")
    return note


def contract_split(desc_row):
    """First month of the spot series in the iron ore row: the row names it ("during 2006 to 2008 (November) spot")."""
    text = B.clean(desc_row)
    m = re.search(r"(?:during|from)\s+((?:19|20)\d{2})(?:\s*(?:to|-)\s*[A-Za-z0-9 ()]+?)?\s+spot\b", text)
    if not m:
        raise BuildError("iron ore: the Description sheet no longer says when the spot series starts")
    return f"{m.group(1)}-01"


def contract_basis(desc_row):
    """The clauses of the iron ore row about the annual contract prices, and the breaks between them."""
    text = B.clean(desc_row)
    m = re.search(r"Earlier data refer to (.*?)(?:\. Unit|$)", text)
    if not m:
        raise BuildError("iron ore: the Description sheet no longer describes the annual contract prices")
    clauses = B.parse_clauses(m.group(1))
    for c in clauses:
        if c["from"] == max(d["from"] for d in clauses if d["from"]):
            c["to"] = None  # "during years 1987-2009": the contract prices stop where the spot series starts, not there
    cur, breaks = B.basis_and_breaks(clauses, "1960-01")
    return cur[:1].upper() + cur[1:], breaks


# ---------------------------------------------------------------- series

def meta_of(sid, k, name, unit, freq, s, start, end, **extra):
    m = {"id": sid, "k": k, "name": name, "unit": unit, "freq": freq, "s": s, "start": start, "end": end}
    if k in NO_PAGE:
        m["fam"] = NO_PAGE[k]
    m.update({a: b for a, b in extra.items() if b not in (None, [], {}, "")})
    return m


def valid(values, freq="M"):
    v = [x for x in values if x is not None]
    return len(v) >= (5 if freq == "A" else 24) and math.isfinite(v[-1])


def pink_series(p, today=None):
    """All Pink Sheet series (prices, iron ore contract years, indices) as [(doc, meta)]."""
    out = []
    note = p.updated
    for col, (sid, k, name, unit) in PINK.items():
        vals = p.column(p.header[col])
        if not vals:
            raise BuildError(f"column '{col}' has no values")
        prefix = PINK_DESC[col]
        text = B.find(p.descs, prefix)
        first = vals[0][0]
        last = vals[-1][0]
        clauses = B.parse_clauses(text)
        basis_text, breaks = B.basis_and_breaks(clauses, first, last)
        est = B.estimate_ranges(prefix, p.descs, p.notes, last)
        if col == "Iron ore, cfr spot":
            row1 = B.find(p.descs, IRON_ORE_ROW)
            spot = contract_split(row1)
            old = [(mo, v) for mo, v in vals if mo < spot]
            vals = [(mo, v) for mo, v in vals if mo >= spot]
            # the contract years are their own series: the spot series keeps the breaks inside its own period
            breaks = [b for b in breaks if b["at"] > spot]
            out += [_contract_series(old, row1, note)]
            first = vals[0][0]
        v = [x for _, x in vals]
        doc = {"id": sid, "freq": "M", "start": first, "v": v}
        meta = meta_of(sid, k, name, unit, "M", "wb-pink", first, last, note=note, basis=basis_note(basis_text, clauses),
                       breaks=breaks, annual=annual_runs(first, v), est=[[a, b] for a, b in est if a >= first])
        out.append((doc, meta))
    cols = {label: j for j, label in p.index_headers().items()}
    for label, (sid, name) in INDEX_SERIES.items():
        if label not in cols:
            raise BuildError(f"Monthly Indices has no column '{label}'")
        vals = p.column(cols[label], p.index_data)
        if not vals:
            raise BuildError(f"index column '{label}' has no values")
        v = [x for _, x in vals]
        doc = {"id": sid, "freq": "M", "start": vals[0][0], "v": v}
        meta = meta_of(sid, "index", name, "index (2010 = 100)", "M", "wb-pink", vals[0][0], vals[-1][0], note=note,
                       basis="World Bank Laspeyres price index, nominal US dollars, 2010 = 100 (sheet 'Monthly Indices'; weights in sheet 'Index Weights').")
        out.append((doc, meta))
    return out


def _contract_series(old, row1, note):
    """Annual Brazilian contract prices before the spot series: one value a year (the value of the months)."""
    by = {}
    for mo, v in old:
        by.setdefault(int(mo[:4]), []).append((mo, v))
    years, vals, exceptions = [], [], []
    for y in sorted(by):
        l = [v for _, v in by[y] if v is not None]
        mode = max(set(l), key=l.count)
        if l.count(mode) < len(l) - 1:
            raise BuildError(f"iron ore {y}: the pre-spot months are not one annual price")
        years.append(y)
        vals.append(mode)
        for mo, v in by[y]:
            if v is not None and v != mode:
                exceptions.append(f"{B.MONTHS[int(mo[5:7]) - 1][:3]} {y} reads {v:g} in the source against {mode:g} in the other months: the annual value is {mode:g}")
    basis_text, breaks = contract_basis(row1)
    first, last = str(years[0]), str(years[-1])
    doc = {"id": "iron-ore-contract-a", "freq": "A", "start": first, "v": vals}
    text = [basis_text + " (dmtu = dry metric ton unit, 1% Fe). One price a year: the Pink Sheet's monthly sheet repeats it over twelve months.",
            "The series ends where the CFR China spot series starts."] + [f"{e[:1].upper()}{e[1:]}." for e in exceptions]
    meta = meta_of("iron-ore-contract-a", "iron-ore", "Iron ore, Brazil annual contract price", "US cents/dmtu", "A", "wb-pink", first, last,
                   note=note, basis=" ".join(text), breaks=[b for b in breaks if b["at"][:4] <= last], closed=True)
    return doc, meta


def eia_series(dirpath):
    import xlrd

    out = []
    for fname, (sid, k, name, unit) in EIA.items():
        p = os.path.join(dirpath, fname + ".xls")
        if not os.path.exists(p):
            print("  missing file:", p)
            continue
        wb = xlrd.open_workbook(p)
        sh = wb.sheet_by_name("Data 1")
        d, v = [], []
        for i in range(3, sh.nrows):
            x, y = sh.row_values(i)[:2]
            if not isinstance(x, float) or y in ("", None):
                continue
            day = xlrd.xldate.xldate_as_datetime(x, 0).date()
            d.append((day - EPOCH).days)
            v.append(round(float(y), 3))
        desc = sh.row_values(2)[1] if sh.ncols > 1 else ""
        key = sh.row_values(1)[1] if sh.ncols > 1 else ""
        doc = {"id": sid, "freq": "D", "d": d, "v": v}
        meta = meta_of(sid, k, name, unit, "D", "eia-spot", str(EPOCH + timedelta(days=d[0])), str(EPOCH + timedelta(days=d[-1])),
                       basis=f"EIA series {key}: {desc}" if desc else "")
        out.append((doc, meta))
    return out


def freight_series(cache_dir=None, dallas=None, nyfed=None):
    """The series of the Freight family that their inputs allow; a missing input keeps the previous file."""
    return (FI.bls_series(cache_dir, meta_of=meta_of) + FI.dallasfed_series(dallas or FI.DALLASFED_FILE, meta_of=meta_of)
            + FI.nyfed_series(nyfed or FI.NYFED_FILE, meta_of=meta_of))


# ---------------------------------------------------------------- annual prices of the USGS Mineral Commodity Summaries

# (series id, commodity id, name, unit, USGS commodity, start of the Statistics_detail text). The USGS file gives
# annual average prices, with the unit and the basis in its own words; the last year is marked "Estimated".
USGS_PRICES = [
    ("usgs-lithium-carbonate-a", "lithium", "Lithium carbonate, battery grade, annual average", "USD/t", "Lithium", "Price, annual average-real, battery-grade lithium carbonate"),
    ("usgs-manganese-ore-a", "manganese", "Manganese ore, CIF China, annual average", "USD/mtu", "Manganese", "Price, average, manganese content, cost, insurance, and freight, China"),
    ("usgs-ndpr-oxide-a", "rare-earths", "NdPr oxide, annual average", "USD/kg", "Rare Earths", "Price, average, dollars per kilogram: Neodymium-praseodymium (NdPr) oxide"),
    ("usgs-mischmetal-a", "rare-earths", "Mischmetal (65% Ce, 35% La), annual average", "USD/kg", "Rare Earths", "Price, average, dollars per kilogram: Mischmetal"),
    ("usgs-nd-oxide-a", "rare-earths", "Neodymium oxide, annual average", "USD/kg", "Neodymium", "Price, average, dollars per kilogram: Neodymium oxide"),
    ("usgs-pr-oxide-a", "rare-earths", "Praseodymium oxide, annual average", "USD/kg", "Praseodymium", "Price, average, dollars per kilogram: Praseodymium oxide"),
    ("usgs-dy-oxide-a", "rare-earths", "Dysprosium oxide, annual average", "USD/kg", "Dysprosium", "Price, average, dollars per kilogram: Dysprosium oxide"),
    ("usgs-tb-oxide-a", "rare-earths", "Terbium oxide, annual average", "USD/kg", "Terbium", "Price, average, dollars per kilogram: Terbium oxide"),
    ("usgs-bauxite-import-a", "bauxite", "Bauxite, US import unit value, annual average", "USD/t", "Bauxite", "Price, average unit value of imports"),
    ("usgs-alumina-import-a", "bauxite", "Alumina, US import unit value, annual average", "USD/t", "Alumina", "Price, average unit value of imports"),
    ("usgs-cobalt-spot-a", "cobalt", "Cobalt cathode, US spot, annual average", "USD/lb", "Cobalt", "Price, average, dollars per pound: U.S. spot, cathode"),
    ("usgs-cobalt-lme-a", "cobalt", "Cobalt, LME cash, annual average", "USD/lb", "Cobalt", "Price, average, dollars per pound: London Metal Exchange"),
    ("usgs-palladium-a", "pgm", "Palladium, annual average", "USD/troy oz", "Palladium", "Price, dollars per troy ounce: Palladium"),
    ("usgs-rhodium-a", "pgm", "Rhodium, annual average", "USD/troy oz", "Rhodium", "Price, dollars per troy ounce: Rhodium"),
    # the metals pages of the third commodity package (review GNC3.5). Every row of these is in the file's section "Salient
    # Statistics - United States" (country "United States"): the names say so where the row itself does not name its market.
    ("usgs-chromite-ore-a", "chromium", "Chromite ore, US salient statistics, annual average", "USD/t", "Chromium", "Price: Chromite ore (gross weight)"),
    ("usgs-ferrochromium-a", "ferro-alloys", "Ferro-chromium (chromium content), US salient statistics, annual average", "USD/lb", "Chromium", "Price: Ferrochromium (chromium content)"),
    ("usgs-heavy-melting-scrap-a", "ferrous-scrap", "Ferrous scrap, No. 1 heavy melting composite, delivered, US, annual average", "USD/t", "Iron And Steel Scrap", "Price, average, delivered, No. 1 heavy melting composite price"),
    ("usgs-molybdenum-a", "molybdenum", "Molybdenum, US molybdic oxide (57% Mo), annual average", "USD/kg", "Molybdenum", "Price, average, dollars per kilogram"),
    ("usgs-graphite-flake-a", "graphite", "Natural graphite, flake, US import unit value, annual average", "USD/t", "Graphite (Natural)", "Price, average unit value of imports, dollars per metric ton at foreign ports: Flake"),
    ("usgs-graphite-lump-a", "graphite", "Natural graphite, lump and chip (Sri Lanka), US import unit value, annual average", "USD/t", "Graphite (Natural)", "Price, average unit value of imports, dollars per metric ton at foreign ports: Lump and chip"),
    ("usgs-graphite-amorphous-a", "graphite", "Natural graphite, amorphous, US import unit value, annual average", "USD/t", "Graphite (Natural)", "Price, average unit value of imports, dollars per metric ton at foreign ports: Amorphous"),
    # the rows that the pages of the fertilisers, sulphur and ferro-alloys denied (FNCD, D5): each is a product of the page, in the file's own unit.
    # The ammonia unit is the file's (dollars per short ton, nitrogen chapter): no conversion. Sulphur is elemental sulphur.
    ("usgs-sulphur-a", "sulphur", "Sulphur (elemental), US mine or plant unit value, annual average", "USD/t", "Sulfur", "Price, average unit value, free on board, mine and (or) plant"),
    ("usgs-ammonia-a", "urea", "Ammonia, US Gulf Coast, annual average", "USD/short ton", "Nitrogen (Fixed)\u2014Ammonia", "Price, average, free on board Gulf Coast"),
    ("usgs-ferrosilicon-75-a", "ferro-alloys", "Ferrosilicon (75% silicon), US salient statistics, annual average", "US cents/lb", "Silicon", "Price, average, cents per pound of silicon: Ferrosilicon, 75% silicon"),
]


def usgs_file(dirpath):
    """The newest MCS<year>_Commodities_Data.csv of raw/usgs, or None."""
    import glob

    found = sorted(glob.glob(os.path.join(dirpath, "MCS*_Commodities_Data.csv")))
    return found[-1] if found else None


def usgs_series(path):
    """[(doc, meta)] and the list of series whose rows were not found. Rows: Statistics = "Price"."""
    import csv

    with open(path, encoding="cp1252", newline="") as f:  # the file is Windows-1252 (em dashes in the section names)
        rows = [r for r in csv.DictReader(f) if r.get("Statistics") == "Price"]
    edition = re.search(r"MCS(\d{4})", os.path.basename(path))
    edition = edition.group(1) if edition else ""
    out, missing = [], []
    for sid, k, name, unit, com, detail in USGS_PRICES:
        mine = [r for r in rows if r["Commodity"] == com and r["Statistics_detail"].startswith(detail)]
        by = {}
        for r in mine:
            v = num(r["Value"])
            if v is not None and r["Year"].isdigit():
                by[int(r["Year"])] = (v, "Estimated." in [n.strip() for n in (r.get("Notes") or "").split(" -- ")], r)
        years = sorted(by)
        if len(years) < 3 or years != list(range(years[0], years[-1] + 1)):
            missing.append(sid)
            continue
        first = by[years[0]][2]
        notes = [n.strip() for n in re.split(r" -- ", first.get("Notes") or "") if n.strip() and n.strip() != "Estimated."]
        est = [y for y in years if by[y][1]]  # a row whose own notes start "Estimated." (a note that quotes the estimated year of another row is not one)
        doc = {"id": sid, "freq": "A", "start": str(years[0]), "v": [by[y][0] for y in years]}
        meta = meta_of(sid, k, name, unit, "A", "usgs-mcs", str(years[0]), str(years[-1]),
                       note=f"USGS Mineral Commodity Summaries {edition}, Salient Statistics, statistic 'Price'",
                       basis=" ".join([first["Statistics_detail"].rstrip(".") + "."] + [n if n.endswith(".") else n + "." for n in notes]),
                       est=[[f"{y}-01", f"{y}-12"] for y in est])
        out.append((doc, meta))
    return out, missing


# ---------------------------------------------------------------- annual nominal prices after a monthly series closed (annual workbook)

# Pink Sheet column -> (id of the annual series, id of the monthly series it continues). The Pink Sheet stopped both
# monthly series in August 2020, while the annual workbook goes on to the year of its last update (review GNC2.1): the
# annual average of the years after the last month of the monthly series is published as a series of its own, labelled
# annual. A year the monthly series covers in part (2020) is not repeated, so no annual value ever stands for a month
# that has its own.
ANNUAL_NOMINAL = {"Barley": ("barley-a", "barley-m"), "Sorghum": ("sorghum-a", "sorghum-m")}
ANNUAL_TWIN = {a: m[:-2] + "-real-a" for a, m in ANNUAL_NOMINAL.values()}  # annual series id -> id of the real twin


def annual_nominal_series(path, nominal_metas):
    """[(doc, meta)] of ANNUAL_NOMINAL, read from the sheet "Annual Prices (Nominal)" of the annual workbook: the years
    after the last month of the monthly series, with the unit the sheet prints under the header. Nothing is computed."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if "Annual Prices (Nominal)" not in wb.sheetnames:
        raise BuildError("annual workbook: no 'Annual Prices (Nominal)' sheet")
    rows = list(wb["Annual Prices (Nominal)"].iter_rows(values_only=True))
    hi = next((i for i, r in enumerate(rows) if r and "Crude oil, Brent" in [str(c) for c in r if c]), None)
    if hi is None:
        raise BuildError("annual workbook: header row of the nominal sheet not found")
    header = {norm(c): j for j, c in enumerate(rows[hi]) if c}
    updated = next((str(r[0]) for r in rows[:hi] if r and r[0] and "Updated" in str(r[0])), "")
    data = [r for r in rows[hi + 2:] if r and isinstance(r[0], (int, float)) and 1900 < r[0] < 2100]
    by_id = {m["id"]: m for m in nominal_metas}
    out = []
    for col, (sid, monthly) in ANNUAL_NOMINAL.items():
        m = by_id.get(monthly)
        if m is None:
            continue
        if col not in header:
            raise BuildError(f"annual workbook: no column '{col}' in the nominal sheet")
        j = header[col]
        unit_cell = norm(rows[hi + 1][j])
        if unit_cell != "($/mt)" or m["unit"] != "USD/t":
            raise BuildError(f"annual workbook: '{col}' is printed in {unit_cell}, not in dollars per tonne")
        last = int(m["end"][:4])
        pts = [(int(r[0]), num(r[j])) for r in data if int(r[0]) > last]
        pts = [(y, v) for y, v in pts if v is not None]
        if not pts or [y for y, _ in pts] != list(range(pts[0][0], pts[-1][0] + 1)):
            continue
        doc = {"id": sid, "freq": "A", "start": str(pts[0][0]), "v": [v for _, v in pts]}
        basis = (f"Annual average in nominal US dollars per tonne, for the years after the last month of the monthly series ({m['end']}), which the Pink Sheet stopped. "
                 f"The workbook does not say how its values after {last} are built. Definition of the monthly series in the workbook: {m.get('basis', '').strip()}")
        meta = meta_of(sid, m["k"], f"{col}, annual average", m["unit"], "A", "wb-pink", str(pts[0][0]), str(pts[-1][0]),
                       note=f"Sheet 'Annual Prices (Nominal)' of the annual workbook. {updated}".strip(), basis=basis)
        out.append((doc, meta))
    return out


# ---------------------------------------------------------------- real prices (annual workbook)

def real_series(path, nominal_metas):
    """Annual real prices (constant 2010 US dollars) of the series built from the monthly sheet, plus the MUV index
    that deflates them. Read from "Annual Prices (Real)"; the definition of the deflator is quoted from the
    "Definitions" sheet. Nothing is computed here."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    for name in ("Annual Prices (Real)", "Definitions"):
        if name not in wb.sheetnames:
            raise BuildError(f"annual workbook: no '{name}' sheet")
    rows = list(wb["Annual Prices (Real)"].iter_rows(values_only=True))
    hi = next((i for i, r in enumerate(rows) if r and "Crude oil, Brent" in [str(c) for c in r if c]), None)
    if hi is None:
        raise BuildError("annual workbook: header row not found")
    header = {norm(c): j for j, c in enumerate(rows[hi]) if c}
    if "MUV Index" not in header:
        raise BuildError("annual workbook: no 'MUV Index' column, so no deflator")
    data = [r for r in rows[hi + 2:] if r and isinstance(r[0], (int, float)) and 1900 < r[0] < 2100]
    updated = next((str(r[0]) for r in rows[:hi] if r and r[0] and "Updated" in str(r[0])), "")
    definition = next((B.clean(r[0]) for r in wb["Definitions"].iter_rows(values_only=True) if r and isinstance(r[0], str) and r[0].startswith("Constant prices")), "")
    defin_muv = next((B.clean(r[0]) for r in wb["Definitions"].iter_rows(values_only=True) if r and isinstance(r[0], str) and r[0].startswith("MUV is")), "")
    if not definition:
        raise BuildError("annual workbook: the Definitions sheet no longer defines constant prices")
    out = []
    by_id = {m["id"]: m for m in nominal_metas}
    # quoted as the sheet "Definitions" words it, typos of the source included
    deflator = f"{definition} {defin_muv}".strip()
    quoted = f"The sheet \u201cDefinitions\u201d says: \u201c{deflator}\u201d"
    for col, (sid, k, name, unit) in PINK.items():
        if not unit.startswith("USD") or col not in header or sid not in by_id:
            continue
        j = header[col]
        pts = [(int(r[0]), num(r[j])) for r in data]
        if sid == "iron-ore-m":  # the annual real column deflates the contract prices too: keep the spot years
            pts = [(y, v) for y, v in pts if y >= int(by_id[sid]["start"][:4])]
        ok = [i for i, (_, v) in enumerate(pts) if v is not None]
        if not ok:
            continue
        pts = pts[ok[0]: ok[-1] + 1]
        rid = sid[:-2] + "-real-a"
        doc = {"id": rid, "freq": "A", "start": str(pts[0][0]), "v": [v for _, v in pts]}
        meta = meta_of(rid, k, f"{name}, real", f"{unit} (2010 dollars)", "A", "wb-pink", str(pts[0][0]), str(pts[-1][0]),
                       note=f"Sheet 'Annual Prices (Real)' of the annual workbook. {updated}".strip(),
                       basis=f"Annual average in constant 2010 US dollars. {quoted}", hidden=True, realOf=sid)
        out.append((doc, meta))
    j = header["MUV Index"]
    pts = [(int(r[0]), num(r[j])) for r in data if num(r[j]) is not None]
    doc = {"id": "muv-a", "freq": "A", "start": str(pts[0][0]), "v": [v for _, v in pts]}
    meta = meta_of("muv-a", "index", "Manufactures unit value index (MUV), the deflator of the real prices", "index (2010 = 100)", "A", "wb-pink",
                   str(pts[0][0]), str(pts[-1][0]), note=f"Column 'MUV Index' of the sheet 'Annual Prices (Real)'. {updated}".strip(), basis=quoted)
    out.append((doc, meta))
    return out


# ---------------------------------------------------------------- assembling

def stats_of(doc, meta):
    if doc["freq"] == "D":
        times = [EPOCH + timedelta(days=x) for x in doc["d"]]
    elif doc["freq"] == "M":
        times = month_times(doc["start"], len(doc["v"]))
    elif meta.get("hidden"):
        return None
    else:
        times = [date(int(doc["start"]) + i, 1, 1) for i in range(len(doc["v"]))]
    st = board_stats(doc["freq"], times, doc["v"])
    if st and meta.get("unit") in DEVIATION_UNITS:
        st.pop("chg", None)
    return st


def order_key(m):
    """Order of data/prices/index.json: by commodity, then daily, monthly, annual; inside a frequency the series the
    commodity opens on, then the series that were there from the first release, then the added ones, then by id."""
    return (m["k"], "DMA".index(m["freq"]), m["id"] != OPENS_ON.get(m["k"]), m["id"] in ADDED, m["id"])


def opening_problems(metas):
    """Commodities with more than one series (hidden real-price twins and the price indices do not count) whose
    first series was not chosen: [(commodity, why)]. The series of a commodity are in the order of order_key()."""
    first, count = {}, {}
    for m in metas:
        if m.get("hidden") or m["k"] in ("index", "freight"):
            continue
        first.setdefault(m["k"], m)
        count[m["k"]] = count.get(m["k"], 0) + 1
    out = []
    for k, n in count.items():
        want = OPENS_ON.get(k)
        if n > 1 and not want:
            out.append((k, f"{n} series and no entry in OPENS_ON"))
        elif want and first[k]["id"] != want:
            out.append((k, f"opens on {first[k]['id']}, not on {want}"))
        elif want and n > 1 and first[k]["freq"] == "A" and any(x["freq"] != "A" for x in metas if x["k"] == k and not x.get("hidden")):
            out.append((k, "opens on an annual series although it has a monthly or daily one"))
    return out


def figures_of(metas):
    """What the key figure on a commodity page needs, one entry per commodity: the board figures and the label of its
    first series (the one the page opens on). The page loads this small file and not the whole index."""
    out = {}
    # a closed series gives way to a live one of its commodity; a commodity whose only series is closed (barley and sorghum, M-023) keeps it,
    # with `closed` set, so that its page says when the series stops instead of saying that there is none
    for closed in (False, True):
        for m in metas:
            if (m.get("hidden") or bool(m.get("closed")) != closed or m["k"] in NO_PAGE or m["k"] == "freight" or m["k"] in out
                    or "stats" not in m):
                continue
            out[m["k"]] = {k: v for k, v in m.items() if k in ("id", "k", "name", "unit", "freq", "s", "start", "end", "basis", "est", "stats", "closed")}
    return out


def mark_closed(metas):
    """A daily or monthly series that ends far behind the newest series of its source, while that source goes on
    publishing, has been stopped by its publisher: it is marked `closed` (its `end` is its last period). It stays
    available as history, the board hides it, and check_freshness() no longer reports it. A series that is only
    late (the source itself has not published) is not closed: it keeps raising its alert."""
    live = [m for m in metas if m["freq"] in ("D", "M") and not m.get("hidden")]
    newest = _newest(live)
    for m in live:
        ref = newest[m["s"]]
        if m["freq"] == "D":
            behind = (date.fromisoformat(ref) - date.fromisoformat(m["end"])).days > DAILY_BEHIND_SOURCE_DAYS
        else:
            behind = (int(ref[:4]) * 12 + int(ref[5:7])) - (int(m["end"][:4]) * 12 + int(m["end"][5:7])) > MONTHLY_BEHIND_SOURCE_MONTHS
        if behind:
            m["closed"] = True
        else:
            m.pop("closed", None)
    return [m["id"] for m in live if m.get("closed")]


def write(doc, meta, metas, out_dir=None):
    out_dir = out_dir or OUT
    if not valid(doc["v"], doc["freq"]):
        print("  rejected (validation):", doc["id"])
        return False
    st = stats_of(doc, meta)
    if st:
        meta["stats"] = st
    with open(os.path.join(out_dir, f"{doc['id']}.json"), "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    metas.append(meta)
    return True


def main():
    os.makedirs(OUT, exist_ok=True)
    pink_path, eia_dir = sys.argv[1], sys.argv[2]
    annual_path = sys.argv[3] if len(sys.argv) > 3 else ANNUAL_XLSX
    produced = []
    # either input may be missing (e.g. a fresh CI checkout where one download failed): the series of the missing
    # source keep their previous file and check_freshness() says when they stop advancing
    if os.path.exists(pink_path):
        p = Pink(pink_path)
        problems = p.check()
        if problems:
            sys.exit("pink sheet does not have the expected shape: " + "; ".join(problems[:6]))
        produced += pink_series(p)
        if os.path.exists(annual_path):
            produced += real_series(annual_path, [m for _, m in produced])
            produced += annual_nominal_series(annual_path, [m for _, m in produced])
    if os.path.isdir(eia_dir):
        produced += eia_series(eia_dir)
    produced += freight_series()
    usgs = usgs_file(os.path.join(ROOT, "raw", "usgs"))
    if usgs:
        found, missing = usgs_series(usgs)
        produced += found
        for sid in missing:
            print("  USGS price not found in", os.path.basename(usgs) + ":", sid)
    metas = []
    for doc, meta in produced:
        write(doc, meta, metas)
    # keep metadata of series that failed this run but have a previous good file
    old_path = os.path.join(OUT, "index.json")
    if os.path.exists(old_path):
        have = {m["id"] for m in metas}
        with open(old_path) as f:
            old = json.load(f)
        for m in old:
            if m["id"] not in have and os.path.exists(os.path.join(OUT, f"{m['id']}.json")):
                if "stats" not in m and m["freq"] in ("D", "M"):
                    with open(os.path.join(OUT, f"{m['id']}.json")) as f:
                        st = stats_of(json.load(f), m)
                    if st:
                        m["stats"] = st
                metas.append(m)
    ids = {m["id"] for m in metas}
    for m in metas:
        if m["id"] in REAL_OF_DAILY and REAL_OF_DAILY[m["id"]] in ids:
            m["monthly"] = REAL_OF_DAILY[m["id"]]
        if m["id"] in REAL_OF_DAILY and REAL_OF_DAILY[m["id"]][:-2] + "-real-a" in ids:
            m["real"] = REAL_OF_DAILY[m["id"]][:-2] + "-real-a"
        elif m["id"][:-2] + "-real-a" in ids and m["freq"] == "M" and not m.get("hidden"):
            m["real"] = m["id"][:-2] + "-real-a"
        elif m["id"] in ANNUAL_TWIN and ANNUAL_TWIN[m["id"]] in ids:
            m["real"] = ANNUAL_TWIN[m["id"]]  # the annual average that goes on after a closed monthly series has the real twin of that series
    # the first series of a commodity (daily before monthly) is the one its page and the event pages open: a series added
    # later never takes that place from the original benchmark
    metas.sort(key=order_key)
    mark_closed(metas)
    with open(old_path, "w") as f:
        json.dump(metas, f, separators=(",", ":"))
    with open(os.path.join(OUT, "figures.json"), "w") as f:
        json.dump(figures_of(metas), f, separators=(",", ":"))
    print(len(metas), "series")
    for s, i, why in check_freshness(metas):
        print("  late:", s, i, why)


if __name__ == "__main__":
    main()
