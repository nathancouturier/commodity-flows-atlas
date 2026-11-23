"""Every series of data/prices/index.json against its raw file (review GP1, finding GP1.1).

The 16 monthly indices once held the columns of the wrong sheet and nothing noticed: the builder's own checks read the
same cells the same way. This proof does not reuse the builder's readers. For each series it finds the column of the
raw file by the TEXT of its header (the sheet "Monthly Indices" spreads a header over four rows, so a column is named
by what is written above it, never counted), checks the unit the file states, and compares the first value, the last
value, the number of observations and every value in between.

It runs on the real downloads in raw/ (not tracked in git) and is skipped, saying so, when they are not on disk.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
"""
import csv
import glob
import json
import os
import re
import unittest
from datetime import date, timedelta

import openpyxl

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "data", "prices")
RAW = os.path.join(ROOT, "raw")
MONTHLY = os.path.join(RAW, "worldbank", "CMO-Historical-Data-Monthly.xlsx")
ANNUAL = os.path.join(RAW, "worldbank", "CMO-Historical-Data-Annual.xlsx")
EIA_DIR = os.path.join(RAW, "eia-spot")
USGS_DIR = os.path.join(RAW, "usgs")

# series id -> header text of its column in "Monthly Prices" (written here, not taken from the builder's table)
PINK_HEADER = {
    "brent-m": "Crude oil, Brent", "wti-m": "Crude oil, WTI", "dubai-m": "Crude oil, Dubai", "crude-avg-m": "Crude oil, average",
    "hh-m": "Natural gas, US", "ttf-m": "Natural gas, Europe", "ng-index-m": "Natural gas index", "lng-japan-m": "Liquefied natural gas, Japan",
    "coal-aus-m": "Coal, Australian", "coal-zaf-m": "Coal, South African", "cocoa-m": "Cocoa", "arabica-m": "Coffee, Arabica",
    "robusta-m": "Coffee, Robusta", "palm-oil-m": "Palm oil", "palm-kernel-oil-m": "Palm kernel oil", "soybeans-m": "Soybeans",
    "soyoil-m": "Soybean oil", "soymeal-m": "Soybean meal", "rapeseed-oil-m": "Rapeseed oil", "sunflower-oil-m": "Sunflower oil",
    "coconut-oil-m": "Coconut oil", "groundnut-oil-m": "Groundnut oil", "fish-meal-m": "Fish meal", "maize-m": "Maize",
    "rice-thai-m": "Rice, Thai 5%", "rice-thai25-m": "Rice, Thai 25%", "rice-thai-a1-m": "Rice, Thai A.1", "rice-viet-m": "Rice, Viet Namese 5%",
    "wheat-hrw-m": "Wheat, US HRW", "wheat-srw-m": "Wheat, US SRW", "sugar-m": "Sugar, world", "sugar-eu-m": "Sugar, EU",
    "sugar-us-m": "Sugar, US", "cotton-m": "Cotton, A Index", "phosrock-m": "Phosphate rock", "dap-m": "DAP", "tsp-m": "TSP",
    "urea-m": "Urea", "potash-m": "Potassium chloride", "aluminium-m": "Aluminum", "iron-ore-m": "Iron ore, cfr spot",
    "copper-m": "Copper", "lead-m": "Lead", "tin-m": "Tin", "nickel-m": "Nickel", "zinc-m": "Zinc", "gold-m": "Gold",
    "platinum-m": "Platinum", "silver-m": "Silver",
}
# series id -> header text of its column in "Monthly Indices" (the text above the column, whatever row it is on)
INDEX_HEADER = {
    "idx-total-m": "Total Index", "idx-energy-m": "Energy", "idx-nonenergy-m": "Non-energy", "idx-agriculture-m": "Agriculture",
    "idx-beverages-m": "Beverages", "idx-food-m": "Food", "idx-oils-meals-m": "Oils & Meals", "idx-grains-m": "Grains",
    "idx-other-food-m": "Other Food", "idx-raw-materials-m": "Raw Materials", "idx-timber-m": "Timber",
    "idx-other-raw-m": "Other Raw Mat.", "idx-fertilizers-m": "Fertilizers", "idx-metals-m": "Metals & Minerals",
    "idx-base-metals-m": "Base Metals (ex. iron ore)", "idx-precious-m": "Precious Metals",
}
# the unit the sheets print under a header -> the unit of the atlas
SHEET_UNIT = {"($/bbl)": "USD/bbl", "($/mt)": "USD/t", "($/mmbtu)": "USD/MMBtu", "($/kg)": "USD/kg", "($/troy oz)": "USD/troy oz",
              "(2010=100)": "index (2010 = 100)"}
# iron ore: the column prints "($/dmtu)" but the Description sheet says what the cells hold: spot in dollars per dry
# tonne, the older contract prices in US cents per dmtu (this is asserted on the Description text below)
IRON_ORE_UNITS = ("USD/dry t", "US cents/dmtu")

EIA_FILES = {
    "brent-d": ("RBRTEd", "Dollars per Barrel", "USD/bbl"), "wti-d": ("RWTCd", "Dollars per Barrel", "USD/bbl"),
    "hh-d": ("RNGWHHDd", "Dollars per Million Btu", "USD/MMBtu"),
    "nyh-gasoline-d": ("EER_EPMRU_PF4_Y35NY_DPGd", "Dollars per Gallon", "USD/gal"),
    "nyh-ulsd-d": ("EER_EPD2DXL0_PF4_Y35NY_DPGd", "Dollars per Gallon", "USD/gal"),
    "nyh-heatingoil-d": ("EER_EPD2F_PF4_Y35NY_DPGd", "Dollars per Gallon", "USD/gal"),
    "usgc-jet-d": ("EER_EPJK_PF4_RGC_DPGd", "Dollars per Gallon", "USD/gal"),
    "propane-mb-d": ("EER_EPLLPA_PF4_Y44MB_DPGd", "Dollars per Gallon", "USD/gal"),
}
# series id -> (USGS commodity, text its Statistics_detail holds, the unit of the atlas); Statistics = "Price"
USGS_ROWS = {
    "usgs-lithium-carbonate-a": ("Lithium", "battery-grade lithium carbonate", "USD/t"),
    "usgs-manganese-ore-a": ("Manganese", "cost, insurance, and freight, China", "USD/mtu"),
    "usgs-ndpr-oxide-a": ("Rare Earths", "Neodymium-praseodymium (NdPr) oxide", "USD/kg"),
    "usgs-mischmetal-a": ("Rare Earths", "Mischmetal", "USD/kg"),
    "usgs-nd-oxide-a": ("Neodymium", "Neodymium oxide", "USD/kg"),
    "usgs-pr-oxide-a": ("Praseodymium", "Praseodymium oxide", "USD/kg"),
    "usgs-dy-oxide-a": ("Dysprosium", "Dysprosium oxide", "USD/kg"),
    "usgs-tb-oxide-a": ("Terbium", "Terbium oxide", "USD/kg"),
    "usgs-bauxite-import-a": ("Bauxite", "average unit value of imports", "USD/t"),
    "usgs-alumina-import-a": ("Alumina", "average unit value of imports", "USD/t"),
    "usgs-cobalt-spot-a": ("Cobalt", "U.S. spot, cathode", "USD/lb"),
    "usgs-cobalt-lme-a": ("Cobalt", "London Metal Exchange (LME), cash", "USD/lb"),
    "usgs-palladium-a": ("Palladium", "Palladium", "USD/troy oz"),
    "usgs-rhodium-a": ("Rhodium", "Rhodium", "USD/troy oz"),
}
# series the raw files on disk cannot prove: FRED is fetched only in GitHub Actions, with a key
NOT_ON_DISK = {"freight-ppi-m"}

MONTH_ID = re.compile(r"\d{4}M\d{2}")


def jload(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def norm(h):
    return re.sub(r"\s+", " ", str(h).replace("*", " ")).strip()


def decimals(x):
    s = repr(float(x))
    return len(s.split(".")[1]) if "." in s and not s.endswith(".0") else 0


def number(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def trim(pairs):
    """[(key, value or None)] without the empty ends."""
    ok = [i for i, (_, v) in enumerate(pairs) if v is not None]
    return pairs[ok[0]: ok[-1] + 1] if ok else []


def month_after(ym, n):
    k = int(ym[:4]) * 12 + int(ym[5:7]) - 1 + n
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


def read_sheet_rows(wb, name):
    return list(wb[name].iter_rows(values_only=True))


def monthly_table(rows):
    """Header of 'Monthly Prices': {normalised header: column}, the unit under each header, the data rows."""
    hi = next(i for i, r in enumerate(rows) if r and "Crude oil, average" in [norm(c) for c in r if c])
    cols = {norm(c): j for j, c in enumerate(rows[hi]) if c and norm(c)}
    units = {j: str(rows[hi + 1][j]).strip() for j in cols.values()}
    data = [r for r in rows[hi + 2:] if r and isinstance(r[0], str) and MONTH_ID.fullmatch(r[0].strip())]
    return cols, units, data


def index_table(rows):
    """'Monthly Indices': the name of a column is the text written above it, on whichever of the header rows."""
    first = next(i for i, r in enumerate(rows) if r and isinstance(r[0], str) and MONTH_ID.fullmatch(r[0].strip()))
    names = {}
    for r in rows[:first]:
        for j, c in enumerate(r):
            if j and isinstance(c, str) and norm(c):
                names.setdefault(j, []).append(norm(c))
    cols = {}
    for j, texts in names.items():
        cols.setdefault(" ".join(texts), j)
    data = [r for r in rows[first:] if r and isinstance(r[0], str) and MONTH_ID.fullmatch(r[0].strip())]
    title = " ".join(str(r[0]) for r in rows[:first] if r and r[0])
    return cols, data, title


def annual_table(rows):
    hi = next(i for i, r in enumerate(rows) if r and "Crude oil, Brent" in [norm(c) for c in r if c])
    cols = {norm(c): j for j, c in enumerate(rows[hi]) if c and norm(c)}
    units = {j: str(rows[hi + 1][j]).strip() for j in cols.values()}
    data = {int(r[0]): r for r in rows[hi + 2:] if r and isinstance(r[0], (int, float)) and 1900 < r[0] < 2100}
    return cols, units, data


def column_of(data, j, first_col=0):
    return trim([(r[first_col].strip().replace("M", "-") if isinstance(r[first_col], str) else r[first_col], number(r[j])) for r in data])


@unittest.skipUnless(os.path.exists(MONTHLY), "raw/ is not tracked in git: the World Bank monthly workbook is not on this machine, so the series are not proved against it")
class PinkSheetMonthly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        wb = openpyxl.load_workbook(MONTHLY, read_only=True, data_only=True)
        cls.cols, cls.units, cls.data = monthly_table(read_sheet_rows(wb, "Monthly Prices"))
        cls.icols, cls.idata, cls.ititle = index_table(read_sheet_rows(wb, "Monthly Indices"))
        cls.desc = [str(r[1]) for r in wb["Description"].iter_rows(values_only=True) if len(r) > 1 and isinstance(r[1], str)]
        cls.idx = {m["id"]: m for m in jload("index.json")}

    def same(self, sid, expected, meta=None):
        """The series file holds exactly `expected` [(YYYY-MM, value)], and its entry in index.json says the same."""
        meta = meta or self.idx[sid]
        doc = jload(sid + ".json")
        self.assertEqual(len(expected), len(doc["v"]), f"{sid}: number of observations")
        self.assertEqual(expected[0][0], doc["start"], f"{sid}: first month")
        self.assertEqual(expected[-1][0], meta["end"], f"{sid}: last month in the index")
        self.assertEqual(month_after(doc["start"], len(doc["v"]) - 1), expected[-1][0], f"{sid}: last month of the file")
        self.assertEqual(expected[0][1], doc["v"][0], f"{sid}: first value")
        self.assertEqual(expected[-1][1], doc["v"][-1], f"{sid}: last value")
        self.assertEqual([v for _, v in expected], doc["v"], f"{sid}: values")
        self.assertEqual(meta["start"], doc["start"], sid)
        self.assertEqual(meta["stats"]["last"]["v"], doc["v"][-1], f"{sid}: board value")

    def test_every_price_column_is_the_one_its_header_names(self):
        for sid, header in PINK_HEADER.items():
            with self.subTest(sid):
                self.assertIn(header, self.cols, f"no column '{header}' in Monthly Prices")
                j = self.cols[header]
                expected = column_of(self.data, j)
                if sid == "iron-ore-m":
                    self.assertTrue(any("spot in US dollar/dry ton and contract in US cents/dmtu" in d for d in self.desc))
                    self.assertEqual(self.idx[sid]["unit"], IRON_ORE_UNITS[0])
                    expected = [(m, v) for m, v in expected if m >= self.idx[sid]["start"]]
                else:
                    self.assertEqual(self.idx[sid]["unit"], SHEET_UNIT[self.units[j]], f"{sid}: the sheet's unit is {self.units[j]}")
                self.same(sid, expected)

    def test_iron_ore_contract_years_are_the_annual_price_the_months_repeat(self):
        j = self.cols["Iron ore, cfr spot"]
        meta = self.idx["iron-ore-contract-a"]
        doc = jload("iron-ore-contract-a.json")
        self.assertEqual((meta["freq"], meta["unit"]), ("A", IRON_ORE_UNITS[1]))
        years = {}
        for m, v in column_of(self.data, j):
            if m < self.idx["iron-ore-m"]["start"]:
                years.setdefault(int(m[:4]), []).append(v)
        self.assertEqual(int(doc["start"]), min(years))
        self.assertEqual(len(doc["v"]), len(years))
        for y, vals in years.items():
            mode = max(set(vals), key=vals.count)
            self.assertGreaterEqual(vals.count(mode), 11, y)  # one price a year (1965 has one odd month)
            self.assertEqual(doc["v"][y - int(doc["start"])], mode, y)
        self.assertEqual(meta["end"], str(max(years)))

    def test_every_index_column_is_the_one_its_header_names(self):
        self.assertIn("2010=100", self.ititle.replace(" ", ""))
        prices_months = [r[0].strip() for r in self.data]
        self.assertEqual([r[0].strip() for r in self.idata], prices_months, "the two sheets cover the same months")
        for sid, header in INDEX_HEADER.items():
            with self.subTest(sid):
                self.assertIn(header, self.icols, f"no column '{header}' in Monthly Indices")
                j = self.icols[header]
                expected = column_of(self.idata, j)
                self.assertEqual(self.idx[sid]["unit"], "index (2010 = 100)")
                self.same(sid, expected)
                # an index is 100 on average in its base year (rounded to one decimal in the sheet)
                base = [v for m, v in expected if m.startswith("2010-")]
                self.assertEqual(len(base), 12, sid)
                self.assertAlmostEqual(sum(base) / 12, 100.0, delta=0.5, msg=f"{sid}: 2010 mean")

    def test_no_index_series_holds_a_price_column(self):
        for sid, header in INDEX_HEADER.items():
            doc = jload(sid + ".json")
            for ph, pj in self.cols.items():
                col = [v for _, v in column_of(self.data, pj)]
                if len(col) == len(doc["v"]) and col == doc["v"]:
                    self.fail(f"{sid} holds the 'Monthly Prices' column '{ph}'")

    def test_the_natural_gas_index_is_on_the_same_base(self):
        base = [v for m, v in column_of(self.data, self.cols["Natural gas index"]) if m.startswith("2010-")]
        self.assertAlmostEqual(sum(base) / len(base), 100.0, delta=0.5)

    def test_every_series_of_the_index_is_proved_by_one_of_the_classes_of_this_file(self):
        proved = (set(PINK_HEADER) | set(INDEX_HEADER) | {"iron-ore-contract-a", "muv-a"} | set(EIA_FILES) | set(USGS_ROWS) | NOT_ON_DISK
                  | {m["id"] for m in self.idx.values() if m.get("realOf")})
        self.assertEqual(sorted(set(self.idx) - proved), [], "series that no raw file proves")
        self.assertEqual(sorted(proved - set(self.idx)), [], "proofs of series that are not in the index")


@unittest.skipUnless(os.path.exists(ANNUAL) and os.path.exists(MONTHLY), "raw/ is not tracked in git: the World Bank annual workbook is not on this machine")
class PinkSheetAnnual(unittest.TestCase):
    """The annual workbook: the real twins and the MUV deflator come from 'Annual Prices (Real)'. The other annual
    sheets are not read by the builder; they are used here to prove that the real columns pair with the right
    nominal ones (real = nominal x 100 / MUV) and that the index sheets are on the base the atlas says."""

    @classmethod
    def setUpClass(cls):
        wb = openpyxl.load_workbook(ANNUAL, read_only=True, data_only=True)
        cls.real = annual_table(read_sheet_rows(wb, "Annual Prices (Real)"))
        cls.nominal = annual_table(read_sheet_rows(wb, "Annual Prices (Nominal)"))
        cls.idx = {m["id"]: m for m in jload("index.json")}
        cls.sheet_names = wb.sheetnames
        cls.nominal_idx = index_table_annual(read_sheet_rows(wb, "Annual Indices (Nominal)"))
        cls.real_idx = index_table_annual(read_sheet_rows(wb, "Annual Indices (Real)"))

    def test_every_real_twin_is_the_column_its_header_names(self):
        cols, units, data = self.real
        twins = [m for m in self.idx.values() if m.get("realOf")]
        self.assertGreaterEqual(len(twins), 40)
        for m in twins:
            with self.subTest(m["id"]):
                nominal = self.idx[m["realOf"]]
                header = PINK_HEADER[m["realOf"]]
                self.assertIn(header, cols, f"no column '{header}' in Annual Prices (Real)")
                j = cols[header]
                self.assertEqual(self.idx[m["realOf"]]["real"], m["id"])
                self.assertEqual(m["unit"], f"{nominal['unit']} (2010 dollars)")
                if m["realOf"] != "iron-ore-m":
                    self.assertEqual(SHEET_UNIT[units[j]], nominal["unit"], "the real sheet states the unit of the nominal series")
                expected = trim([(y, number(r[j])) for y, r in sorted(data.items())])
                if m["realOf"] == "iron-ore-m":  # the contract years are not deflated into the spot series
                    expected = [(y, v) for y, v in expected if y >= int(nominal["start"][:4])]
                doc = jload(m["id"] + ".json")
                self.assertEqual((expected[0][0], expected[-1][0], len(expected)), (int(doc["start"]), int(m["end"]), len(doc["v"])))
                self.assertEqual([v for _, v in expected], doc["v"])
                self.assertEqual(m["stats"] if "stats" in m else None, None)  # hidden series are not on the board

    def test_the_deflator_is_the_muv_column(self):
        cols, units, data = self.real
        self.assertEqual(units[cols["MUV Index"]], "(2010=100)")
        expected = trim([(y, number(r[cols["MUV Index"]])) for y, r in sorted(data.items())])
        doc = jload("muv-a.json")
        self.assertEqual((int(doc["start"]), len(doc["v"])), (expected[0][0], len(expected)))
        self.assertEqual([v for _, v in expected], doc["v"])
        self.assertEqual(data[2010][cols["MUV Index"]], 100)
        self.assertEqual(self.idx["muv-a"]["unit"], "index (2010 = 100)")

    def test_real_columns_pair_with_the_nominal_columns_of_the_same_header(self):
        """real = nominal x 100 / MUV, within the rounding of the three printed numbers. A real column read from
        the wrong place breaks this for its header."""
        rcols, runits, rdata = self.real
        ncols, nunits, ndata = self.nominal
        muv = rcols["MUV Index"]
        checked = 0
        for header, j in rcols.items():
            if header == "MUV Index" or header not in ncols:
                continue
            for y, r in rdata.items():
                real, nom, deflator = number(r[j]), number(ndata.get(y, [None] * 200)[ncols[header]]), number(r[muv])
                if None in (real, nom, deflator) or not deflator:
                    continue
                want = nom * 100 / deflator
                tol = 0.5 * 10 ** -decimals(nom) * 100 / deflator + 0.5 * 10 ** -decimals(real) + abs(want) * 0.05 / deflator + 1e-9
                self.assertLessEqual(abs(want - real), tol, f"{header} {y}: nominal {nom}, MUV {deflator}, real {real}")
                checked += 1
        self.assertGreater(checked, 3000)

    def test_the_headers_of_both_price_sheets_carry_the_same_units(self):
        rcols, runits, _ = self.real
        ncols, nunits, _ = self.nominal
        for header, j in rcols.items():
            if header in ncols and header != "Plywood":  # Plywood: cents/sheet printed as ¢/sheet
                self.assertEqual(runits[j], nunits[ncols[header]], header)

    def test_the_annual_index_sheets_are_2010_equals_100(self):
        for name, (cols, data) in (("nominal", self.nominal_idx), ("real", self.real_idx)):
            for header, j in cols.items():
                v = number(data[2010][j])
                if v is not None:
                    self.assertAlmostEqual(v, 100.0, delta=0.5, msg=f"annual {name} index '{header}' in 2010")

    def test_the_annual_nominal_index_matches_the_monthly_index_year_mean(self):
        """The annual and the monthly index sheets describe the same indices: the annual value of a year is the mean
        of its twelve monthly values (within 0.1 or 2%: the two workbooks are revised separately, the largest gap is 1.4% in 2018)."""
        wb = openpyxl.load_workbook(MONTHLY, read_only=True, data_only=True)
        icols, idata, _ = index_table(read_sheet_rows(wb, "Monthly Indices"))
        acols, adata = self.nominal_idx
        total = 0
        for header, j in icols.items():
            canon = header.replace("Total Index", "World Bank Commodity Price Index")
            aj = next((c for h, c in acols.items() if h == canon or h.replace(" ", "") == canon.replace(" ", "")), None)
            self.assertIsNotNone(aj, f"no column for '{header}' in Annual Indices (Nominal)")
            for y in range(1960, 2026):
                vals = [number(r[j]) for r in idata if r[0].startswith(str(y))]
                a = number(adata[y][aj])
                if a is None or None in vals or len(vals) != 12:
                    continue
                self.assertAlmostEqual(sum(vals) / 12, a, delta=max(0.1, 0.02 * a), msg=f"{header} {y}")
                total += 1
        self.assertGreater(total, 900)


def index_table_annual(rows):
    """'Annual Indices': the text above a column, over the stacked header rows."""
    first = next(i for i, r in enumerate(rows) if r and isinstance(r[0], (int, float)) and 1900 < r[0] < 2100)
    names = {}
    for r in rows[:first]:
        for j, c in enumerate(r):
            if j and isinstance(c, str) and norm(c):
                names.setdefault(j, []).append(norm(c))
    cols = {" ".join(t): j for j, t in names.items()}
    data = {int(r[0]): r for r in rows[first:first + 80] if r and isinstance(r[0], (int, float)) and 1900 < r[0] < 2100}
    return cols, data


@unittest.skipUnless(os.path.isdir(EIA_DIR) and glob.glob(os.path.join(EIA_DIR, "*.xls")), "raw/ is not tracked in git: the EIA spot files are not on this machine")
class EiaDaily(unittest.TestCase):
    def test_every_daily_series_is_its_file(self):
        import xlrd

        idx = {m["id"]: m for m in jload("index.json")}
        epoch = date(1970, 1, 1)
        for sid, (fname, unit_text, unit) in EIA_FILES.items():
            with self.subTest(sid):
                sh = xlrd.open_workbook(os.path.join(EIA_DIR, fname + ".xls")).sheet_by_name("Data 1")
                self.assertIn(f"({unit_text})", sh.row_values(2)[1], "the unit the file states")
                self.assertEqual(idx[sid]["unit"], unit)
                pts = []
                for i in range(3, sh.nrows):
                    x, y = sh.row_values(i)[:2]
                    if isinstance(x, float) and y not in ("", None):
                        pts.append(((xlrd.xldate.xldate_as_datetime(x, 0).date() - epoch).days, round(float(y), 3)))
                doc = jload(sid + ".json")
                self.assertEqual(len(pts), len(doc["v"]), "number of observations")
                self.assertEqual([d for d, _ in pts], doc["d"])
                self.assertEqual([v for _, v in pts], doc["v"])
                self.assertEqual(idx[sid]["start"], str(epoch + timedelta(days=pts[0][0])))
                self.assertEqual(idx[sid]["end"], str(epoch + timedelta(days=pts[-1][0])))
                self.assertEqual(idx[sid]["stats"]["last"]["v"], pts[-1][1])


@unittest.skipUnless(glob.glob(os.path.join(USGS_DIR, "MCS*_Commodities_Data.csv")), "raw/ is not tracked in git: the USGS file is not on this machine")
class UsgsAnnual(unittest.TestCase):
    def test_every_annual_series_is_its_rows(self):
        path = sorted(glob.glob(os.path.join(USGS_DIR, "MCS*_Commodities_Data.csv")))[-1]
        with open(path, encoding="cp1252", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["Statistics"] == "Price"]
        idx = {m["id"]: m for m in jload("index.json")}
        for sid, (commodity, text, unit) in USGS_ROWS.items():
            with self.subTest(sid):
                mine = [r for r in rows if r["Commodity"] == commodity and text in r["Statistics_detail"]]
                details = {r["Statistics_detail"] for r in mine}
                self.assertEqual(len(details), 1, f"{sid}: the rows are not one statistic: {details}")
                by = {int(r["Year"]): float(r["Value"].replace(",", "")) for r in mine}
                years = sorted(by)
                doc = jload(sid + ".json")
                self.assertEqual((int(doc["start"]), len(doc["v"])), (years[0], len(years)))
                self.assertEqual(doc["v"], [by[y] for y in years])
                self.assertEqual((idx[sid]["start"], idx[sid]["end"]), (str(years[0]), str(years[-1])))
                self.assertEqual(idx[sid]["unit"], unit)
                self.assertEqual(idx[sid]["stats"]["last"], {"v": by[years[-1]], "t": str(years[-1])})
                # the unit written in the file's own words
                words = mine[0]["Unit"] + " " + mine[0]["Statistics_detail"]
                self.assertIn({"USD/t": "per metric ton", "USD/mtu": "per metric ton unit", "USD/kg": "per kilogram", "USD/lb": "per pound",
                               "USD/troy oz": "per troy ounce"}[unit], words)


if __name__ == "__main__":
    unittest.main()
