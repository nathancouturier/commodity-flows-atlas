"""
United States LPG exports to Mexico and Canada, from two US government files, and the correction of the customs tonnage of
those pairs (METHODOLOGY.md §1, rule 10 of clean.py).

    python pipeline/trade/us_lpg.py            # read raw/ and write pipeline/cache/us_lpg_volumes.json
    import us_lpg; us_lpg.estimate("MEX", 2023)   # -> {"t": tonnes, "note": ..., ...} from the cache only

What the cache holds (only what the pages print):
  * EIA, "Exports by Destination" (propane, normal butane, isobutane), annual, thousand barrels per day, Mexico and Canada, every year
    of the series: the volume of the pair in all modes of transport, from the Census Bureau's customs data. Public domain.
  * US Census Bureau, USA Trade Online export detail file (EXDB2412.ZIP, December 2024: the year-to-date fields are calendar 2024):
    for the pairs of PAIRS, the quantity in cubic metres of each Schedule B code of LPG (271112, 271113), the shipping weight of the
    cargo that went by vessel and the value. The file gives a weight for vessel and air cargo only, and no total weight. Public domain.

CEPII BACI reports the tonnage of the pair United States to Mexico in 2021 to 2024 at 0.76 to 0.98 times the volume in cubic metres of the
United States' own statistics (measure() gives each year), 1.5 to 1.9 times the tonnage that this volume gives at the density of the cargo,
and its unit value falls to 0.39 to 0.56 of the group's. A volume read as tonnes, for part or all of the declarations, is a plausible
cause of such a tonnage (CAUSE): it is not established here. Before 2021 the tonnage is in line with the volume at the density (0.7 to 1.2
times the tonnage the volume gives). The correction replaces the tonnage of those years by the volume times the density, an Atlas estimate
(CORRECTED).
"""
import csv
import html
import io
import json
import os
import re
import sys
import zipfile
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CACHE_FILE = os.path.join(ROOT, "pipeline", "cache", "us_lpg_volumes.json")
RAW_EIA = os.path.join(ROOT, "raw", "eia", "lpg-destination")
RAW_CENSUS = os.path.join(ROOT, "raw", "census", "exdb2412", "EXDB2412.ZIP")

BBL_M3 = 0.158987  # cubic metres in a US barrel (42 US gallons, exact by definition)
EIA_RELEASE = "2026-10-30"
EIA_URL = "https://www.eia.gov/dnav/pet/pet_move_expc_a_EPLLPA_EEX_mbblpd_a.htm"
# the EIA series read (thousand barrels per day, annual): product -> {country: series id of the "history" page}
EIA_SERIES = {
    "propane": {"MEX": "MPAEX_NUS-NMX_2", "CAN": "MPAEX_NUS-NCA_2"},
    "normal-butane": {"MEX": "MBUEX_NUS-NMX_2", "CAN": "MBUEX_NUS-NCA_2"},
    "isobutane": {"MEX": "M_EPLLBAI_EEX_NUS-NMX_2", "CAN": "M_EPLLBAI_EEX_NUS-NCA_2"},
}
# Census country codes (COUNTRY.TXT) of the pairs read, and the codes of LPG (Schedule B) with the product of each
PAIRS = {"MEX": "2010", "CAN": "1220", "JPN": "5880", "CHN": "5700", "KOR": "5800"}
CODES = {"2711120010": "propane", "2711120020": "propane", "2711130000": "butanes"}
CENSUS_YEAR = 2024
# the registry id (data/sources.json) of the volume behind an estimate, by the "source" that estimate() returns
SOURCE_ID = {"census": "census-exports", "eia": "eia-exports-destination"}
# the reading of the error as the pages print it: a reading, not a finding
CAUSE = "a volume in cubic metres read as tonnes, for part or all of the declarations, is a plausible cause, not established here"

# Corrections of the customs tonnage (rule 10 of clean.py): (group, exporter, importer) -> years. The tonnage of these pair-years
# is replaced by the all-modes volume of the United States' own statistics, at the density of the cargo.
CORRECTED = {("lpg", "USA", "MEX"): (2021, 2022, 2023, 2024)}
# the pairs checked and left as they are, with the reason in the words of the page: United States to Canada (the volume of EIA and of
# the Census file agree with each other, 0.58 million m3 in 2024; the customs tonnage 0.9 times that volume, 1.6 times the volume
# at the density; its unit value is under half the group's from 2015 on, but the series has no break to date a correction from)
CHECKED_NOT_CORRECTED = {("lpg", "USA", "CAN")}


def _eia_series(path):
    """{year: thousand barrels per day} of an EIA 'history' page (decades in rows, years in columns)."""
    text = open(path, encoding="latin-1").read()
    out = {}
    for dec, body in re.findall(r"<td class='B4'>&nbsp;&nbsp;(\d{4})'s</td>(.*?)</tr>", text, re.S):
        for k, v in enumerate(re.findall(r"class='B3'>([^<]*)<", body)):
            v = html.unescape(v).strip().replace(",", "")
            if re.fullmatch(r"\d+(\.\d+)?", v):
                out[int(dec) + k] = float(v)
    title = re.search(r"<title>(.*?)</title>", text, re.S).group(1).strip()
    return out, title


def _census(zpath):
    """Quantity (m3), vessel shipping weight (kg) and value (USD) of the LPG codes by country, calendar 2024, summed over districts and over
    domestic and foreign exports; and the density of each code (kg per m3: vessel weight over quantity, over the rows whose whole value
    goes by vessel, as the file gives no total weight). Layout: https://www.census.gov/foreign-trade/reference/products/layouts/exdb.html
    (EXP_DETL, positions 1-based; the year-to-date block is the calendar year of the December file)."""
    sl = lambda l, a, b: l[a - 1:b]  # noqa: E731
    by_cty = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    dens = defaultdict(lambda: [0, 0])
    wanted = set(PAIRS.values())
    z = zipfile.ZipFile(zpath)
    unit = {}
    for line in io.TextIOWrapper(z.open("CONCORD.txt"), encoding="latin-1"):
        if line[0:10] in CODES:
            unit[line[0:10]] = line[210:213].strip()
    assert set(unit) == set(CODES) and set(unit.values()) == {"M3"}, unit  # quantity 1 is in cubic metres for these codes
    names = {}
    for line in io.TextIOWrapper(z.open("COUNTRY.txt"), encoding="latin-1"):
        if len(line.strip()) >= 5:
            names[line[0:4]] = line[11:61].strip()
    years = set()
    with z.open("EXP_DETL.txt") as fh:
        for raw in fh:
            line = raw.decode("ascii")
            code = sl(line, 2, 11)
            if code not in CODES:
                continue
            years.add((sl(line, 18, 21), sl(line, 22, 23)))
            qty, val, ves_val, ves_wgt = int(sl(line, 189, 203)), int(sl(line, 219, 233)), int(sl(line, 264, 278)), int(sl(line, 279, 293))
            assert ves_val <= val, "vessel value above total value: the field order of the layout page is wrong"
            if ves_val == val and val > 0:
                dens[code][0] += ves_wgt
                dens[code][1] += qty
            cty = sl(line, 12, 15)
            if cty in wanted:
                a = by_cty[cty][code]
                a["qty_m3"] += qty
                a["vessel_kg"] += ves_wgt
                a["usd"] += val
                a["vessel_usd"] += ves_val
    assert years == {(str(CENSUS_YEAR), "12")}, years
    density = {c: dens[c][0] / dens[c][1] for c in CODES}
    out = {}
    for iso, cc in PAIRS.items():
        codes = by_cty[cc]
        total_t = sum(a["qty_m3"] * density[c] for c, a in codes.items()) / 1e3
        vessel_t = sum(a["vessel_kg"] for a in codes.values()) / 1e3
        out[iso] = {"census_country": names[cc], "qty_m3": {c: a["qty_m3"] for c, a in sorted(codes.items())},
                    "vessel_t": round(vessel_t, 1), "total_t": round(total_t, 1),
                    "usd": sum(a["usd"] for a in codes.values()), "vessel_usd": sum(a["vessel_usd"] for a in codes.values())}
    return {"year": CENSUS_YEAR, "density_kg_m3": {c: round(d, 1) for c, d in density.items()}, "pairs": out}


def build():
    eia = {}
    for product, by in EIA_SERIES.items():
        for iso, sid in by.items():
            s, title = _eia_series(os.path.join(RAW_EIA, f"hist_{sid}.html"))
            assert title.startswith("U.S. Exports to ") and "(Thousand Barrels per Day)" in title, title
            eia.setdefault(product, {})[iso] = {str(y): v for y, v in sorted(s.items())}
    doc = {
        "eia": {"unit": "thousand barrels per day", "release": EIA_RELEASE, "url": EIA_URL, "m3_per_barrel": BBL_M3, "series": eia},
        "census": _census(RAW_CENSUS),
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    return doc


_DOC = {}


def load():
    if not _DOC:
        with open(CACHE_FILE, encoding="utf-8") as f:
            _DOC.update(json.load(f))
    return _DOC


def _days(y):
    return 366 if (y % 4 == 0 and y % 100 != 0) or y % 400 == 0 else 365


def volume_m3(iso, year):
    """{product: thousand m3} of EIA's exports of the year to the country, or None when a series of the three has no year."""
    eia = load()["eia"]
    out = {}
    for p, by in eia["series"].items():
        v = by[iso].get(str(year))
        if v is None:
            if p == "isobutane" and year < 2015:  # the series starts in 2015; its volume to Mexico and Canada is a few thousand barrels a day
                v = 0.0
            else:
                return None
        out[p] = v * _days(year) * eia["m3_per_barrel"]
    return out


def density(product):
    """kg per m3 of a product of the EIA series (the butanes: the density of code 2711130000)."""
    d = load()["census"]["density_kg_m3"]
    return d["2711120010"] if product == "propane" else d["2711130000"]


def estimate(iso, year):
    """The all-modes tonnage of the pair United States to `iso` in `year` from EIA's volumes at the file's densities (propane at that of
    code 2711120010, the butanes at that of 2711130000), as {"t": tonnes, "m3": thousand m3, "by": {product: tonnes}}; in the year of the
    Census file, the quantities and densities of the file itself. None when the year has no figure."""
    c = load()["census"]
    if year == c["year"] and iso in c["pairs"]:
        p = c["pairs"][iso]
        return {"t": p["total_t"], "m3": sum(p["qty_m3"].values()) / 1e3, "source": "census"}
    v = volume_m3(iso, year)
    if v is None:
        return None
    by = {p: m3 * 1e3 * density(p) / 1e3 for p, m3 in v.items()}  # thousand m3 x kg/m3 = tonnes
    return {"t": sum(by.values()), "m3": sum(v.values()), "by": by, "source": "eia"}


def sea_share(iso, year):
    """Share of the pair's tonnage that went by vessel, in the year of the Census file: vessel shipping weight over the quantity times
    the file's density. None for another year."""
    c = load()["census"]
    if year != c["year"] or iso not in c["pairs"]:
        return None
    p = c["pairs"][iso]
    return p["vessel_t"] / p["total_t"]


def measure(iso, year, reported_t):
    """What the customs tonnage is against the volume of the United States' own statistics: `per_m3`, the tonnes of the customs figure per
    cubic metre of the volume, and `per_t`, the customs tonnage over the tonnage that the volume gives at the density of the cargo. `m3`:
    the volume, thousand m3."""
    e = estimate(iso, year)
    return {"per_m3": reported_t / (e["m3"] * 1e3), "per_t": reported_t / e["t"], "m3": e["m3"], "source": e["source"]}


def note(iso, year, reported_t, usd, ref_uv):
    """Text of `enote` of a corrected row. ref_uv: the group's median unit value of the year, USD per tonne."""
    e = estimate(iso, year)
    m = measure(iso, year, reported_t)
    c = load()["census"]
    dens = f"{c['density_kg_m3']['2711120010']:.0f} kg/m3 for propane and {c['density_kg_m3']['2711130000']:.0f} for butanes"
    if e["source"] == "census":
        src = (f"the quantity of propane and butanes in the US Census Bureau's export detail file for {year} ({e['m3'] / 1e3:.2f} million m3, "
               f"all modes of transport) times the density of that file's own vessel rows ({dens})")
    else:
        src = (f"the volume of the United States' propane and butane exports in {year} ({e['m3'] / 1e3:.2f} million m3, all modes of transport; "
               f"EIA, Exports by Destination, from US Census Bureau data) times the density of the cargo in the US Census Bureau's export "
               f"detail file for {c['year']} ({dens})")
    uv = usd / reported_t
    return (f"Atlas estimate: CEPII BACI reports {reported_t / 1e6:.2f} Mt for USD {usd / 1e6:,.0f} million ({uv:,.0f} USD/t, {uv / ref_uv:.2f} times the "
            f"{year} median unit value of LPG); this customs tonnage is {m['per_t']:.2f} times the tonnage that the United States' own volume gives at the "
            f"density of the cargo and {m['per_m3']:.2f} times that volume in cubic metres ({CAUSE}); tonnage = {src}")


if __name__ == "__main__":
    d = build()
    print("wrote", os.path.relpath(CACHE_FILE, ROOT))
    for iso, p in d["census"]["pairs"].items():
        print(iso, p["census_country"], "total_t", p["total_t"], "vessel_t", p["vessel_t"], "share", round(p["vessel_t"] / p["total_t"], 4))
    print("density", d["census"]["density_kg_m3"])
