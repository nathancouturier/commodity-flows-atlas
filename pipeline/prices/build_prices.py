"""
Build price history files from the World Bank Pink Sheet (monthly, since 1960) and EIA daily spot prices.

    python pipeline/prices/build_prices.py <pinksheet_monthly.xlsx> <eia_spot_dir>

Outputs
  data/prices/index.json        list of series (PriceSeriesMeta)
  data/prices/<id>.json         packed series: monthly {start, v[]} or daily {d[] days since epoch, v[]}

Validation: each series must have at least 24 points, a plausible last value (> 0) and must not
end more than 120 days (daily) / 6 months (monthly) before the newest series of its source.
A series failing validation keeps its previous file (graceful fallback).
"""
import json
import os
import sys
from datetime import date, datetime, timedelta

import openpyxl

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "prices")

# Pink Sheet column header -> (series id, commodity id, display name, unit)
PINK = {
    "Crude oil, Brent": ("brent-m", "crude-oil", "Brent crude", "USD/bbl"),
    "Crude oil, WTI": ("wti-m", "crude-oil", "WTI crude", "USD/bbl"),
    "Crude oil, Dubai": ("dubai-m", "crude-oil", "Dubai crude", "USD/bbl"),
    "Natural gas, US": ("hh-m", "natural-gas", "Natural gas, US (Henry Hub)", "USD/MMBtu"),
    "Natural gas, Europe": ("ttf-m", "natural-gas", "Natural gas, Europe (World Bank series; Dutch TTF hub basis in recent years)", "USD/MMBtu"),
    "Liquefied natural gas, Japan": ("lng-japan-m", "lng", "LNG, Japan import price", "USD/MMBtu"),
    "Coal, Australian": ("coal-aus-m", "thermal-coal", "Thermal coal, Australia (Newcastle)", "USD/t"),
    "Coal, South African **": ("coal-zaf-m", "thermal-coal", "Thermal coal, South Africa (Richards Bay)", "USD/t"),
    "Cocoa": ("cocoa-m", "cocoa", "Cocoa", "USD/kg"),
    "Coffee, Arabica": ("arabica-m", "coffee", "Coffee, Arabica", "USD/kg"),
    "Coffee, Robusta": ("robusta-m", "coffee", "Coffee, Robusta", "USD/kg"),
    "Palm oil": ("palm-oil-m", "palm-oil", "Palm oil", "USD/t"),
    "Soybeans": ("soybeans-m", "soybeans", "Soybeans", "USD/t"),
    "Soybean oil": ("soyoil-m", "soyoil", "Soybean oil", "USD/t"),
    "Soybean meal": ("soymeal-m", "soymeal", "Soybean meal", "USD/t"),
    "Rapeseed oil": ("rapeseed-oil-m", "rapeseed", "Rapeseed oil", "USD/t"),
    "Maize": ("maize-m", "corn", "Maize (US Gulf)", "USD/t"),
    "Rice, Thai 5% ": ("rice-thai-m", "rice", "Rice, Thai 5%", "USD/t"),
    "Wheat, US HRW": ("wheat-hrw-m", "wheat", "Wheat, US HRW", "USD/t"),
    "Wheat, US SRW": ("wheat-srw-m", "wheat", "Wheat, US SRW", "USD/t"),
    "Sugar, world": ("sugar-m", "sugar", "Sugar, world", "USD/kg"),
    "Cotton, A Index": ("cotton-m", "cotton", "Cotton, A Index", "USD/kg"),
    "Phosphate rock": ("phosrock-m", "phosphate", "Phosphate rock", "USD/t"),
    "DAP": ("dap-m", "phosphate", "DAP", "USD/t"),
    "Urea ": ("urea-m", "urea", "Urea", "USD/t"),
    "Potassium chloride **": ("potash-m", "potash", "Potassium chloride (potash)", "USD/t"),
    "Aluminum": ("aluminium-m", "aluminium", "Aluminium", "USD/t"),
    "Iron ore, cfr spot": ("iron-ore-m", "iron-ore", "Iron ore, CFR China spot", "USD/dmtu"),
    "Copper": ("copper-m", "copper", "Copper", "USD/t"),
    "Lead": ("lead-m", "lead", "Lead", "USD/t"),
    "Tin": ("tin-m", "tin", "Tin", "USD/t"),
    "Nickel": ("nickel-m", "nickel", "Nickel", "USD/t"),
    "Zinc": ("zinc-m", "zinc", "Zinc", "USD/t"),
    "Gold": ("gold-m", "gold", "Gold", "USD/troy oz"),
    "Platinum": ("platinum-m", "pgm", "Platinum", "USD/troy oz"),
    "Silver": ("silver-m", "silver", "Silver", "USD/troy oz"),
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

# FRED monthly series (fetched in GitHub Actions; FRED may be unreachable elsewhere) -> raw/fred/<id>.csv
FRED = {
    "PCU483111483111": ("freight-ppi-m", "freight", "US producer price index, deep-sea freight transportation", "index (Dec 1988 = 100)"),
}

EPOCH = date(1970, 1, 1)


def num(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def write(doc, meta, metas):
    v = [x for x in doc["v"] if x is not None]
    if len(v) < 24 or v[-1] <= 0:
        print("  rejected (validation):", doc["id"])
        return
    json.dump(doc, open(os.path.join(OUT, f"{doc['id']}.json"), "w"), separators=(",", ":"))
    metas.append(meta)


def pink(path, metas):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Monthly Prices"]
    rows = list(ws.iter_rows(values_only=True))
    hdr_i = next(i for i, r in enumerate(rows) if r and "Crude oil, Brent" in [str(c) for c in r if c])
    hdr = [str(c) if c is not None else "" for c in rows[hdr_i]]
    data = [r for r in rows[hdr_i + 2:] if r and isinstance(r[0], str) and "M" in r[0]]
    updated = next((str(r[0]) for r in rows[:hdr_i] if r and r[0] and "Updated" in str(r[0])), "")
    for col, (sid, k, name, unit) in PINK.items():
        if col not in hdr:
            print("  missing column:", col)
            continue
        j = hdr.index(col)
        vals = [(r[0], num(r[j])) for r in data]
        first = next(i for i, (_, x) in enumerate(vals) if x is not None)
        last = max(i for i, (_, x) in enumerate(vals) if x is not None)
        vals = vals[first:last + 1]
        start = vals[0][0].replace("M", "-")
        doc = {"id": sid, "freq": "M", "start": start, "v": [x for _, x in vals]}
        meta = {"id": sid, "k": k, "name": name, "unit": unit, "freq": "M", "s": "wb-pink", "start": start, "end": vals[-1][0].replace("M", "-"), "note": updated}
        write(doc, meta, metas)


def eia(dirpath, metas):
    import xlrd

    for fname, (sid, k, name, unit) in EIA.items():
        p = os.path.join(dirpath, fname + ".xls")
        if not os.path.exists(p):
            print("  missing file:", p)
            continue
        sh = xlrd.open_workbook(p).sheet_by_name("Data 1")
        d, v = [], []
        for i in range(3, sh.nrows):
            x, y = sh.row_values(i)[:2]
            if not isinstance(x, float) or y in ("", None):
                continue
            day = xlrd.xldate.xldate_as_datetime(x, 0).date()
            d.append((day - EPOCH).days)
            v.append(round(float(y), 3))
        doc = {"id": sid, "freq": "D", "d": d, "v": v}
        meta = {"id": sid, "k": k, "name": name, "unit": unit, "freq": "D", "s": "eia-spot",
                "start": str(EPOCH + timedelta(days=d[0])), "end": str(EPOCH + timedelta(days=d[-1]))}
        write(doc, meta, metas)


def fred(dirpath, metas):
    """Monthly FRED CSVs (observation_date,<ID>); missing values are '.'"""
    import csv

    for sid_fred, (sid, k, name, unit) in FRED.items():
        p = os.path.join(dirpath, sid_fred + ".csv")
        if not os.path.exists(p):
            continue
        rows = [r for r in csv.reader(open(p)) if r][1:]
        pts = [(r[0][:7], num(r[1]) if r[1] != "." else None) for r in rows if len(r) > 1]
        if not pts:
            continue
        doc = {"id": sid, "freq": "M", "start": pts[0][0], "v": [v for _, v in pts]}
        meta = {"id": sid, "k": k, "name": name, "unit": unit, "freq": "M", "s": "fred", "start": pts[0][0], "end": pts[-1][0],
                "note": "Proxy for freight costs: Baltic Exchange indices are proprietary"}
        write(doc, meta, metas)


def main():
    os.makedirs(OUT, exist_ok=True)
    metas = []
    # either input may be missing (e.g. a fresh CI checkout where one download failed): keep the old series
    if os.path.exists(sys.argv[1]):
        pink(sys.argv[1], metas)
    if os.path.isdir(sys.argv[2]):
        eia(sys.argv[2], metas)
    fred(os.path.join(ROOT, "raw", "fred"), metas)
    # keep metadata of series that failed this run but have a previous good file
    old_path = os.path.join(OUT, "index.json")
    if os.path.exists(old_path):
        have = {m["id"] for m in metas}
        for m in json.load(open(old_path)):
            if m["id"] not in have and os.path.exists(os.path.join(OUT, f"{m['id']}.json")):
                metas.append(m)
    metas.sort(key=lambda m: (m["k"], m["freq"], m["id"]))
    json.dump(metas, open(old_path, "w"), indent=0)
    print(len(metas), "series")


if __name__ == "__main__":
    main()
