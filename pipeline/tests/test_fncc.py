"""Tests of the third correction package after the review of the three commodity packages (FNCC): the pages, texts, prices and search of the new commodities.

C1  barley and sorghum: the annual average goes on after the closed monthly series, as a series of its own, and the page says so
C2  a large importer with no production and no export line that receives the product overland carries a note (Mozambique: chromite, ferro-chromium)
C3  the USGS annual prices of chromite, ferro-chromium, heavy melting scrap, molybdenum and natural graphite are published and attached to their pages
C4  the TSP price is the price of triple superphosphate only, and the notes say so
C5  the coverage figures METHODOLOGY gives for the lanes of the new groups are the ones of the lane files
C6  a vessel class whose cargo is one group of a page names the product on its chip
C7  the search finds the trade names of the new commodities; the finder follows the commodity list; the "See" link is not in capitals
C8  a small line of a country page keeps its value (three significant digits under one billion)
C9  the notes of the pulses, flour and dregs say what the atlas does, no more
C10 the floors of the lanes are the same in the three files that hold them, and the recipe lists the files

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The tests of the data files read the files as the builders last wrote them.
"""
import glob
import json
import os
import re
import sys
import tempfile
import types
import unittest

import openpyxl

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("prices", "trade", "freight", "commodities"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import build_prices as P  # noqa: E402
import metals as MET  # noqa: E402

DATA = os.path.join(ROOT, "data")
RAW = os.path.join(ROOT, "raw")
ANNUAL = os.path.join(RAW, "worldbank", "CMO-Historical-Data-Annual.xlsx")
USGS_GLOB = os.path.join(RAW, "usgs", "MCS*_Commodities_Data.csv")


def load(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return json.load(f)


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def price_index():
    return {m["id"]: m for m in load(DATA, "prices", "index.json")}


class C1AnnualAfterTheClosedSeries(unittest.TestCase):
    def workbook(self, rows):
        """An annual workbook of the shape the builder reads: title lines, the header row, the unit row, one row a year."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Annual Prices (Nominal)"
        ws.append(["World Bank Commodity Price Data (The Pink Sheet)"])
        ws.append(["annual prices, 1960 to present, nominal US dollars"])
        ws.append([])
        ws.append(["Updated on September 02, 2026"])
        ws.append([])
        ws.append([])
        ws.append([None, "Crude oil, Brent", "Barley", "Sorghum"])
        ws.append([None, "($/bbl)", "($/mt)", "($/mt)"])
        for r in rows:
            ws.append(list(r))
        path = os.path.join(tempfile.mkdtemp(), "annual.xlsx")
        wb.save(path)
        return path

    def monthly(self, end="2020-08"):
        return [{"id": "barley-m", "k": "barley", "name": "Barley (feed, US)", "unit": "USD/t", "freq": "M", "s": "wb-pink", "start": "1960-01",
                 "end": end, "basis": "Barley (U.S.) feed, No. 2."},
                {"id": "sorghum-m", "k": "sorghum", "name": "Sorghum (US Gulf)", "unit": "USD/t", "freq": "M", "s": "wb-pink", "start": "1960-01",
                 "end": end, "basis": "Sorghum (US), no. 2 milo yellow."}]

    def test_only_the_years_after_the_last_month_are_published_and_labelled_annual(self):
        path = self.workbook([(y, 50.0, 100.0 + y - 2018, 200.0 + y - 2018) for y in range(2018, 2026)])
        out = P.annual_nominal_series(path, self.monthly())
        by = {m["id"]: (d, m) for d, m in out}
        doc, meta = by["barley-a"]
        self.assertEqual((doc["freq"], doc["start"], doc["v"]), ("A", "2021", [103.0 + i for i in range(5)]))  # 2021 to 2025: not 2020, the year the months cover
        self.assertEqual((meta["freq"], meta["unit"], meta["s"], meta["k"], meta["start"], meta["end"]), ("A", "USD/t", "wb-pink", "barley", "2021", "2025"))
        self.assertTrue(meta["name"].endswith(", annual average"))
        self.assertIn("2020-08", meta["basis"])
        self.assertIn("does not say how its values after 2020 are built", meta["basis"])
        self.assertIn("Annual Prices (Nominal)", meta["note"])
        self.assertEqual(by["sorghum-a"][0]["v"], [203.0 + i for i in range(5)])

    def test_a_monthly_series_that_is_not_closed_has_no_annual_twin(self):
        path = self.workbook([(y, 50.0, 100.0, 200.0) for y in range(2018, 2026)])
        self.assertEqual(P.annual_nominal_series(path, self.monthly("2025-12")), [])  # nothing after 2025

    def test_a_unit_that_is_not_dollars_a_tonne_aborts_the_build(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Annual Prices (Nominal)"
        ws.append([None, "Crude oil, Brent", "Barley", "Sorghum"])
        ws.append([None, "($/bbl)", "($/kg)", "($/mt)"])
        ws.append([2021, 1, 2, 3])
        path = os.path.join(tempfile.mkdtemp(), "bad.xlsx")
        wb.save(path)
        with self.assertRaises(P.BuildError):
            P.annual_nominal_series(path, self.monthly())

    @unittest.skipUnless(os.path.exists(ANNUAL), "raw/ is not tracked in git: the World Bank annual workbook is not on this machine")
    def test_the_published_series_are_the_workbook_rows(self):
        wb = openpyxl.load_workbook(ANNUAL, read_only=True, data_only=True)
        rows = list(wb["Annual Prices (Nominal)"].iter_rows(values_only=True))
        hi = next(i for i, r in enumerate(rows) if r and "Crude oil, Brent" in [str(c) for c in r if c])
        cols = {str(c).replace("*", "").strip(): j for j, c in enumerate(rows[hi]) if c}
        idx = price_index()
        for col, sid in (("Barley", "barley-a"), ("Sorghum", "sorghum-a")):
            with self.subTest(sid):
                want = [(int(r[0]), float(r[cols[col]])) for r in rows[hi + 2:] if r and isinstance(r[0], (int, float)) and int(r[0]) > 2020 and r[cols[col]] is not None]
                doc = load(DATA, "prices", sid + ".json")
                self.assertEqual((int(doc["start"]), doc["v"]), (want[0][0], [v for _, v in want]))
                self.assertEqual((idx[sid]["end"], idx[sid]["freq"]), (str(want[-1][0]), "A"))
                self.assertEqual(idx[sid]["real"], sid.replace("-a", "-real-a"))  # the real twin of the monthly series is the one of the annual average

    def test_the_closed_monthly_series_stays_closed_and_the_page_shows_the_annual_average(self):
        idx = price_index()
        for k in ("barley", "sorghum"):
            self.assertTrue(idx[f"{k}-m"]["closed"])
            self.assertEqual(idx[f"{k}-m"]["end"], "2020-08")
            fig = load(DATA, "prices", "figures.json")[k]
            self.assertEqual((fig["id"], fig["freq"], fig.get("closed")), (f"{k}-a", "A", None))  # the key figure is the annual average, never the closed month
            self.assertEqual(idx[f"{k}-m"]["real"], f"{k}-real-a")
            self.assertEqual(idx[f"{k}-real-a"]["end"], "2025")
        self.assertEqual(P.OPENS_ON["barley"], "barley-m")  # the monthly history stays first; the annual average follows it
        self.assertEqual(P.opening_problems(list(idx.values())), [])

    def test_the_commodity_notes_say_where_the_price_goes_on(self):
        for k in ("barley", "sorghum"):
            txt = " ".join(load(DATA, "commodities", k + ".json")["notes"])
            self.assertIn("stops in August 2020", txt)
            self.assertIn("annual average", txt)
            self.assertIn("2021 to 2025", txt)
            self.assertNotIn("No free series after it was found", txt)

    def test_the_drawer_opens_a_closed_series_with_its_live_successor_and_loads_one_real_twin(self):
        prices = read("web", "src", "lib", "prices.ts")
        self.assertIn("l[0].closed ? l.find((m) => !m.closed && m.unit === l[0].unit)", prices)
        drawer = read("web", "src", "components", "PriceDrawer.tsx")
        self.assertIn("[...new Set(ids.map((id) => findMeta(id)!.real!))]", drawer)
        # the window of the nominal series is not the window of its real twin: the toggle opens it afresh (the real chart read 2001 to 2020 under "annual 1960 to 2025")
        self.assertRegex(drawer, r"useEffect\(\(\) => \{\s*resetView\.current = true;\s*\}, \[realOn\]\);")


class FakeBuilder:
    """What metals.transit_notes reads of build_commodities."""

    def __init__(self, pairs_dir):
        self.TRADE = {"chromium": ("chromium-ore", None, "chromium ores and concentrates (HS 2610)")}
        self.EXTRA_GROUPS = {"urea": [("ammonia", "ammonia", "Ammonia", "anhydrous ammonia (HS 281410)")]}
        self.DATA = pairs_dir
        self.joinn = lambda a, b: f"{a}; {b}" if a else b
        self.cname = lambda iso: {"MOZ": "Mozambique", "JPN": "Japan", "ZAF": "South Africa"}.get(iso, iso)


class C2TransitImporter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "freight", "pairs"))
        self.B = FakeBuilder(self.tmp)

    def pairs(self, group, rows):
        doc = {"group": group, "cols": ["o", "d", "kt", "m"], "rows": rows}
        with open(os.path.join(self.tmp, "freight", "pairs", group + ".json"), "w") as f:
            json.dump(doc, f)

    def doc(self, imports, exports, production=()):
        def table(rows):
            return {"s": "baci", "u": "Mt", "world": sum(v for _, v in rows) or 1.0, "rows": [{"c": c, "v": v} for c, v in rows]}
        return {"imports": table(imports), "exports": table(exports), "production": {"rows": [{"c": c, "v": 1.0} for c in production]}}

    def test_an_importer_with_no_production_and_no_export_line_that_receives_overland_is_noted(self):
        self.pairs("chromium-ore", [["ZAF", "MOZ", 8000, 3], ["ZWE", "MOZ", 500, 3], ["ZAF", "CHN", 12000, 0]])
        d = self.doc([("CHN", 15.0), ("MOZ", 8.8), ("IDN", 1.4)], [("ZAF", 23.0), ("MOZ", 0.04), ("TUR", 1.4)], production=("ZAF", "TUR"))
        fired = MET.transit_notes(self.B, {"chromium": d})
        self.assertEqual(fired, ["chromium/imports/MOZ"])
        note = d["imports"]["rows"][1]["n"]
        self.assertIn("may be cargo in transit to a port", note)
        self.assertIn("not the country's own use", note)
        self.assertIn("a possible reading, not established here", note)
        self.assertIn("Mozambique", note)
        # FNCF (review GV6C.1): the row says what its own exports are, from the table: 0.04 Mt of 24.44 Mt of the world's, and of its 8.8 Mt of imports
        self.assertIn("has no production line in the tables of this page and exports of 40 kt (0.16% of the world exports, 0.45% of its own imports)", note)
        self.assertNotIn("not a producer or an exporter", note)
        page = d["notes"][-1]  # the row note is a tooltip: the page says it too, with the product of the table
        self.assertIn("importers of chromium ores and concentrates (HS 2610)", page)
        self.assertIn("a possible reading, not established here", page)
        self.assertNotIn("n", d["imports"]["rows"][0])  # China, 54% of the world, receives its ore by sea: no note

    def test_a_producer_a_material_exporter_a_small_share_or_a_sea_importer_is_left_alone(self):
        self.pairs("chromium-ore", [["ZAF", "MOZ", 8000, 3], ["ZAF", "JPN", 5000, 0], ["ZAF", "CHN", 12000, 0]])
        cases = {
            "producer": self.doc([("CHN", 15.0), ("MOZ", 8.8)], [("ZAF", 23.0)], production=("MOZ",)),
            "exporter": self.doc([("CHN", 15.0), ("MOZ", 8.8)], [("ZAF", 23.0), ("MOZ", 2.0)]),  # exports above a tenth of its imports
            "small": self.doc([("CHN", 80.0), ("MOZ", 4.0)], [("ZAF", 23.0)]),  # under a tenth of the world
            "sea": self.doc([("CHN", 15.0), ("JPN", 8.8)], [("ZAF", 23.0)]),  # Japan: its pairs are not overland
        }
        for name, d in cases.items():
            with self.subTest(name):
                self.assertEqual(MET.transit_notes(self.B, {"chromium": d}), [])

    def test_a_group_without_a_pairs_file_has_no_overland_test_and_no_note(self):
        d = self.doc([("CHN", 15.0), ("MOZ", 8.8)], [("ZAF", 23.0)])
        self.assertEqual(MET.transit_notes(self.B, {"chromium": d}), [])

    def test_a_row_that_has_a_reading_already_is_not_given_a_second_one(self):
        self.pairs("chromium-ore", [["ZAF", "MOZ", 8000, 3]])
        d = self.doc([("CHN", 15.0), ("MOZ", 8.8)], [("ZAF", 23.0)])
        d["imports"]["rows"][1]["n"] = "a possible reading of its own"
        self.assertEqual(MET.transit_notes(self.B, {"chromium": d}), [])

    def test_extra_tables_of_the_extended_pages_are_read_by_their_stem(self):
        self.pairs("ammonia", [["ZAF", "MOZ", 800, 3]])
        d = {"ammonia-imports": None, "extra": [{"key": "ammonia-imports", "table": self.doc([("CHN", 15.0), ("MOZ", 8.8)], [("ZAF", 2.0)])["imports"]},
                                                  {"key": "ammonia-exports", "table": self.doc([("ZAF", 2.0)], [("ZAF", 23.0)])["exports"]}]}
        # package FNCD (D3): the rule detects the row, and a note is printed only for the rows of the reviewed table
        self.assertEqual(MET.transit_notes(self.B, {"urea": d}), [])
        self.assertEqual([k for k, _, noted in MET.TRANSIT_REPORT], ["urea/ammonia-imports/MOZ"])
        MET.TRANSIT_REVIEWED[("urea", "ammonia-imports", "MOZ")] = "a reason"
        try:
            self.assertEqual(MET.transit_notes(self.B, {"urea": d}), ["urea/ammonia-imports/MOZ"])
        finally:
            del MET.TRANSIT_REVIEWED[("urea", "ammonia-imports", "MOZ")]

    def test_the_built_pages_carry_it_for_mozambique_and_the_rows_it_fires_on_are_these(self):
        fired = []
        for f in sorted(glob.glob(os.path.join(DATA, "commodities", "*.json"))):
            if f.endswith(("index.json", "companies.json")):
                continue
            d = load(f)
            tabs = [(k, d[k]) for k in ("exports", "imports") if isinstance(d.get(k), dict)] + [(x["key"], x["table"]) for x in d.get("extra") or []]
            for key, t in tabs:
                for r in t.get("rows", []):
                    if "may be cargo in transit to a port" in (r.get("n") or ""):
                        fired.append(f"{os.path.basename(f)[:-5]}/{key}/{r['c']}")
        # package FNCD (D3): the detector finds four rows, the note is printed on the two reviewed ones (test_fncd.py D3)
        self.assertEqual(sorted(fired), ["chromium/imports/MOZ", "ferro-alloys/imports/MOZ"])
        moz = load(DATA, "countries", "profiles", "MOZ.json")
        lines = [e for e in moz["imports"] if e["k"] in ("chromium", "ferro-alloys")]
        self.assertEqual(len(lines), 2)
        for e in lines:
            self.assertIn("may be cargo in transit to a port", e.get("n", ""))


class C3UsgsPrices(unittest.TestCase):
    NEW = {
        "usgs-chromite-ore-a": ("chromium", "Chromium", "Price: Chromite ore (gross weight)", "USD/t"),
        "usgs-ferrochromium-a": ("ferro-alloys", "Chromium", "Price: Ferrochromium (chromium content)", "USD/lb"),
        "usgs-heavy-melting-scrap-a": ("ferrous-scrap", "Iron And Steel Scrap", "Price, average, delivered, No. 1 heavy melting composite price", "USD/t"),
        "usgs-molybdenum-a": ("molybdenum", "Molybdenum", "Price, average, dollars per kilogram", "USD/kg"),
        "usgs-graphite-flake-a": ("graphite", "Graphite (Natural)", "Price, average unit value of imports, dollars per metric ton at foreign ports: Flake", "USD/t"),
        "usgs-graphite-lump-a": ("graphite", "Graphite (Natural)", "Price, average unit value of imports, dollars per metric ton at foreign ports: Lump and chip", "USD/t"),
        "usgs-graphite-amorphous-a": ("graphite", "Graphite (Natural)", "Price, average unit value of imports, dollars per metric ton at foreign ports: Amorphous", "USD/t"),
    }

    def test_the_series_are_declared_with_their_page_and_unit(self):
        declared = {row[0]: row for row in P.USGS_PRICES}
        for sid, (page, com, detail, unit) in self.NEW.items():
            with self.subTest(sid):
                self.assertEqual((declared[sid][1], declared[sid][3], declared[sid][4]), (page, unit, com))
                self.assertTrue(declared[sid][5].startswith(detail[:40]))

    @unittest.skipUnless(glob.glob(USGS_GLOB), "raw/ is not tracked in git: the USGS file is not on this machine")
    def test_each_series_is_its_rows_in_the_us_salient_statistics(self):
        import csv

        path = sorted(glob.glob(USGS_GLOB))[-1]
        with open(path, encoding="cp1252", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["Statistics"] == "Price"]
        idx = price_index()
        for sid, (page, com, detail, unit) in self.NEW.items():
            with self.subTest(sid):
                mine = [r for r in rows if r["Commodity"] == com and r["Statistics_detail"].startswith(detail)]
                self.assertEqual({r["Country"] for r in mine}, {"United States"})  # what the names "US" rest on
                self.assertEqual(len({r["Statistics_detail"] for r in mine}), 1)
                by = {int(r["Year"]): float(r["Value"].replace(",", "")) for r in mine}
                doc = load(DATA, "prices", sid + ".json")
                self.assertEqual(doc["v"], [by[y] for y in sorted(by)])
                m = idx[sid]
                self.assertEqual((m["k"], m["unit"], m["freq"], m["s"]), (page, unit, "A", "usgs-mcs"))
                self.assertEqual((m["start"], m["end"]), (str(min(by)), str(max(by))))
                self.assertTrue(m["basis"].startswith(mine[0]["Statistics_detail"].rstrip(".")))  # what the file says it is: product, market, unit

    def test_the_pages_have_a_price_and_say_what_it_is_the_price_of(self):
        fig = load(DATA, "prices", "figures.json")
        for page in ("chromium", "ferro-alloys", "ferrous-scrap", "molybdenum", "graphite"):
            with self.subTest(page):
                self.assertIn(page, fig)
                self.assertEqual(fig[page]["freq"], "A")  # an annual average, never shown as a current price
                notes = " ".join(load(DATA, "commodities", page + ".json")["notes"])
                self.assertIn("USGS", notes)
                self.assertNotIn("No free price series", notes)
                self.assertRegex(read("web", "src", "lib", "prices.ts"), rf"['\"]?{re.escape(page)}['\"]?: '[^']*USGS")
        self.assertEqual(fig["ferro-alloys"]["id"], "usgs-ferrochromium-a")  # the page opens on ferro-chromium: its key figure is that alloy's
        self.assertEqual(P.OPENS_ON["graphite"], "usgs-graphite-flake-a")
        self.assertEqual(P.opening_problems(list(price_index().values())), [])

    def test_a_page_with_no_free_series_keeps_its_wording(self):
        fig = load(DATA, "prices", "figures.json")
        # sulphur has a USGS price since package FNCD (D5)
        for page in ("pig-iron", "met-coal", "npk", "pulses"):
            with self.subTest(page):
                self.assertNotIn(page, fig)
        notes = " ".join(load(DATA, "commodities", "pig-iron.json")["notes"])
        self.assertIn("No free price series", notes)


class C4Superphosphate(unittest.TestCase):
    def test_the_tsp_price_is_not_the_price_of_the_group(self):
        prices = read("web", "src", "lib", "prices.ts")
        self.assertIn("TSP (triple superphosphate only; the superphosphate tables hold single and triple together, HS 310310)", prices)
        txt = " ".join(load(DATA, "commodities", "phosphate.json")["notes"])
        self.assertIn("TSP, the triple grade, has no code of its own", txt)
        self.assertIn("the price of triple superphosphate only", txt)
        self.assertNotIn("single and triple (TSP)", txt)


class C5CoverageFigures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lanes = {os.path.basename(f)[:-5]: load(f) for f in glob.glob(os.path.join(DATA, "freight", "lanes", "*.json"))}
        cls.meth = read("METHODOLOGY.md")

    def share(self, group):
        return self.lanes[group]["coverage"]["share"]

    def test_the_sop_sentence_gives_the_figure_of_its_lane_file(self):
        m = re.search(r"its lanes cover (\d+)% of its seaborne tonnes", self.meth)
        self.assertIsNotNone(m, "the SOP sentence gives its coverage")
        self.assertEqual(int(m.group(1)), round(self.share("potassium-sulphate") * 100))
        self.assertNotIn("about a fifth", self.meth)
        self.assertEqual(self.lanes["potassium-sulphate"]["coverage"]["share"] > 0.63, True)

    def test_the_lowest_coverages_listed_are_the_lowest_of_the_files(self):
        m = re.search(r"lowest for (.+?); potash reads (\d+\.\d)%", self.meth, re.S)
        self.assertIsNotNone(m)
        listed = [(n.lower(), v) for n, v in re.findall(r"([a-z][a-z -]+?) \((\d+\.\d)%\)", re.sub(r"\s+", " ", m.group(1)), re.I)]
        names = {"unwrought tin": "tin-metal", "refined products": "refined-products", "unwrought lead": "lead-metal", "unwrought zinc": "zinc-metal", "aluminium": "aluminium",
                 "cocoa": "cocoa", "npk": "npk", "silico-manganese": "silico-manganese", "ferro-silicon": "ferro-silicon", "dried pulses": "pulses",
                 "ferro-chromium": "ferro-chromium", "steel": "steel", "ammonium nitrate": "ammonium-nitrate", "potassium sulphate": "potassium-sulphate",
                 "ferro-manganese": "ferro-manganese", "and coffee": "coffee"}
        self.assertEqual(len(listed), len(names))
        for name, pct in listed:
            with self.subTest(name):
                self.assertAlmostEqual(self.share(names[name.strip()]) * 100, float(pct), delta=0.051)
        # and they are the groups under 70%
        under = sorted(g for g, d in self.lanes.items() if d["coverage"]["share"] < 0.70)
        self.assertEqual(under, sorted(names.values()))
        self.assertAlmostEqual(self.share("potash") * 100, float(m.group(2)), delta=0.051)

    def test_the_ferro_alloys_reach_the_coverage_their_floors_were_set_for(self):
        for g in ("ferro-manganese", "silico-manganese", "ferro-silicon", "ferro-chromium"):
            self.assertGreaterEqual(self.share(g), 0.63, g)

    def test_the_counts_of_the_lanes_and_the_share_of_the_seaborne_tonnes_are_the_files(self):
        m = re.search(r"2024: ([\d,]+) main seaborne lanes, (\d+) mixed lanes and (\d+) history lanes over (\d+) groups", self.meth)
        main = mixed = hist = 0
        for d in self.lanes.values():
            for ln in d["lanes"]:
                if ln["set"] == "history":
                    hist += 1
                elif ln.get("mode") == "mixed":
                    mixed += 1
                else:
                    main += 1
        self.assertEqual((int(m.group(1).replace(",", "")), int(m.group(2)), int(m.group(3)), int(m.group(4))), (main, mixed, hist, len(self.lanes)))
        # the share of the seaborne tonnes the main lanes carry, from the pairs files (sea and transit pairs; a lane is a pair)
        main_pairs = {(g, ln["o"], ln["d"]) for g, d in self.lanes.items() for ln in d["lanes"] if ln["set"] == "main" and ln.get("mode") != "mixed"}
        sea = carried = 0.0
        for f in glob.glob(os.path.join(DATA, "freight", "pairs", "*.json")):
            p = load(f)
            ix = {c: j for j, c in enumerate(p["cols"])}
            for r in p["rows"]:
                if r[ix["m"]] in (0, 1):
                    sea += r[ix["kt"]]
                    if (p["group"], r[ix["o"]], r[ix["d"]]) in main_pairs:
                        carried += r[ix["kt"]]
        said = float(re.search(r"the main lanes carry (\d+\.\d)% of 2024 seaborne", self.meth).group(1))
        self.assertAlmostEqual(carried / sea * 100, said, delta=0.051)


class C6CargoLabels(unittest.TestCase):
    def test_the_gas_carriers_and_tankers_name_the_product_on_the_chip(self):
        classes = {v["id"]: v for v in load(DATA, "freight", "vessel-classes.json")}
        want = {"mgc": {"urea": "Ammonia"}, "vlgc": {"urea": "Ammonia"},
                "chemical-tanker": {"urea": "UAN solution", "phosphate": "Phosphoric acid", "sunflower": "Sunflower oil", "rapeseed": "Rapeseed oil"},
                "handy-tanker": {"urea": "UAN solution", "phosphate": "Phosphoric acid"}, "mr": {"sunflower": "Sunflower oil", "rapeseed": "Rapeseed oil"}}
        for cid, labels in want.items():
            with self.subTest(cid):
                self.assertEqual(classes[cid]["cargoLabels"], labels)
                self.assertTrue(set(labels) <= set(classes[cid]["cargoes"]))  # a label is for a chip that is there

    def test_no_class_labels_a_page_it_does_not_list_and_the_dry_classes_label_only_coke(self):
        for v in load(DATA, "freight", "vessel-classes.json"):
            self.assertTrue(set(v.get("cargoLabels", {})) <= set(v["cargoes"]), v["id"])
            if v["id"] in ("supramax", "handysize"):
                self.assertEqual(v["cargoLabels"], {"met-coal": "Coke"})  # the Metallurgical coal page is on these classes for its coke group

    def test_the_view_prints_the_label_and_the_chip_still_opens_the_page(self):
        shared = read("web", "src", "components", "views", "shared.tsx")
        self.assertIn("const label = props.labels?.[k];", shared)
        self.assertIn("onClick={() => openCommodity(k)}", shared)
        self.assertIn("<CommodityChips ids={v.cargoes} labels={v.cargoLabels} />", read("web", "src", "components", "views", "VesselView.tsx"))
        self.assertIn("cargoLabels?: Record<string, string>;", read("web", "src", "types.ts"))


class C7SearchAndLists(unittest.TestCase):
    def test_the_trade_names_are_aliases_of_their_pages(self):
        search = read("web", "src", "lib", "search.ts")
        block = search[search.index("const COMMODITY_ALIASES"): search.index("const cap =")]

        def aliases(page):
            m = re.search(rf"['\"]?{re.escape(page)}['\"]?: \[(.*?)\],\n", block)
            return [a.strip().strip("'") for a in re.findall(r"'[^']*'", m.group(1))]

        self.assertIn("fertiliser", aliases("sulphur"))
        self.assertIn("fertilizer", aliases("sulphur"))
        for a in ("HMS", "heavy melting scrap", "shredded scrap"):
            self.assertIn(a, aliases("ferrous-scrap"))
        for a in ("HBI", "hot briquetted iron", "DRI"):
            self.assertIn(a, aliases("pig-iron"))
        for page in ("pulses", "corn"):  # "DRI" is a prefix of "dried": no alias of another page holds the word
            self.assertFalse([a for a in aliases(page) if re.search(r"\bdried\b", a, re.I)], page)

    def test_the_finder_and_the_lane_groups_follow_the_commodity_list(self):
        freight = read("web", "src", "lib", "freight.ts")
        self.assertLess(freight.index("  sulphur: ['sulphur'],"), freight.index("  npk: ['npk', 'npk-two-nutrient'],"))
        index = {c["id"]: c["rank"] for c in load(DATA, "commodities", "index.json")}
        self.assertLess(index["sulphur"], index["npk"])
        finder = read("web", "src", "components", "RouteFinder.tsx")
        self.assertIn("inListOrder(OPTIONS).map(", finder)
        self.assertIn("commodityMeta('thermal-coal')?.rank", finder)

    def test_the_see_link_is_not_in_capitals(self):
        self.assertIn('class="link-btn link-inline"', read("web", "src", "components", "views", "CommodityView.tsx"))
        self.assertRegex(read("web", "src", "styles", "views.css"), r"\.link-btn\.link-inline \{ text-transform: none;")


class C8SmallValues(unittest.TestCase):
    def test_bn_keeps_three_decimals_from_a_billion_and_three_significant_digits_below(self):
        import build_profiles as BP

        self.assertEqual(BP.bn(1234.5678), 1234.568)
        self.assertEqual(BP.bn(1.0), 1.0)
        self.assertEqual(BP.bn(0.00034), 0.00034)  # USD 340,000 is not 0.0
        self.assertEqual(BP.bn(0.0123456), 0.0123)
        self.assertEqual(BP.bn(0.4567), 0.457)

    def test_no_profile_line_with_a_value_prints_zero(self):
        n = zero = 0
        for f in glob.glob(os.path.join(DATA, "countries", "profiles", "*.json")):
            stack = [load(f)]
            while stack:
                o = stack.pop()
                if isinstance(o, dict):
                    for k, v in o.items():
                        if k == "usd" and isinstance(v, (int, float)):
                            n += 1
                            zero += v == 0
                        stack.append(v)
                elif isinstance(o, list):
                    stack.extend(o)
        self.assertGreater(n, 10000)
        self.assertEqual(zero, 0)


class C9PulsesFlourDregs(unittest.TestCase):
    def test_cowpeas_are_not_put_in_the_code_of_the_other_pulses(self):
        self.assertNotIn("cowpea", read("pipeline", "trade", "hs_map.py").lower())
        self.assertNotIn("cowpea", read("pipeline", "commodities", "build_commodities.py").lower())
        notes = " ".join(load(DATA, "commodities", "pulses.json")["notes"])
        self.assertIn("pigeon peas and every pulse the code does not name", notes)
        self.assertNotIn("cowpea", notes.lower())

    def test_the_by_kind_tables_say_from_when_and_which_year(self):
        notes = " ".join(load(DATA, "commodities", "pulses.json")["notes"])
        self.assertIn("The kinds exist from 2019", notes)
        self.assertIn("the tables of each kind show the latest year only", notes)

    def test_the_run_on_list_of_tables_is_said_once(self):
        view = read("web", "src", "components", "views", "CommodityView.tsx")
        self.assertIn("return `${collapsed} ${listText(words)}${byKind ? ', in total and by kind' : ''}`;", view)
        self.assertIn("${covers(clauses.get(c)!, 'In the tables of', 'Tables of')}", view)
        self.assertIn("${covers(series.get(n)!, 'Series by year of', 'Series by year of')}", view)
        self.assertIn("if (ts.length <= 3) return `${lead} ${listText(ts.map(label))}`;", view)  # up to three tables are named, more are said by kind

    def test_flour_and_dregs_say_what_the_atlas_does_and_assert_no_share(self):
        for page, word in (("wheat", "flour"), ("corn", "dregs")):
            txt = " ".join(load(DATA, "commodities", page + ".json")["notes"])
            self.assertIn(f"no free source gives the split, so the atlas draws no lanes for {'flour' if word == 'flour' else 'the dregs'}", txt)
            self.assertNotIn("large part", txt)
        self.assertNotIn("a large part of this trade moves in bags", read("METHODOLOGY.md"))
        self.assertIn("customs gross weight does not tell bulk from bagged,", read("METHODOLOGY.md"))


class C10Recipe(unittest.TestCase):
    def floors(self):
        py = read("pipeline", "freight", "build_lanes.py")
        build = dict(re.findall(r'"([a-z-]+)": (0\.\d+)', py[py.index("FLOOR = {"): py.index("FLOOR_DEFAULT")]))
        t = read("pipeline", "tests", "test_lanes.py")
        test = dict(re.findall(r'"([a-z-]+)": (0\.\d+)', t[t.index("FLOOR = {"): t.index("BUILT = ")]))
        j = read("web", "scripts", "validate-freight.mjs")
        js = dict(re.findall(r"'?([a-z-]+)'?: (0\.\d+)", j[j.index("const FLOOR = {"): j.index("const floorOf")]))
        return build, test, js

    def test_the_floors_of_the_builder_the_unit_test_and_the_validator_are_the_same(self):
        build, test, js = self.floors()
        self.assertGreater(len(build), 20)
        self.assertEqual({k: float(v) for k, v in build.items()}, {k: float(v) for k, v in test.items()})
        self.assertEqual({k: float(v) for k, v in build.items()}, {k: float(v) for k, v in js.items()})

    def test_the_recipe_names_the_validator_and_what_the_two_fix_packages_added(self):
        doc = read("docs", "ADDING_A_COMMODITY.md")
        self.assertIn("`web/scripts/validate-freight.mjs`", doc.split("## 3.")[0].split("## 2.")[1])  # in the table of section 2, where the floors are
        for word in ("PW_NEAR", "KEEP_REPORTED", "UV_KEPT_GROUPS", "baci_group_totals.csv", "COAST_RULES", "cargoLabels", "USGS_PRICES", "ANNUAL_NOMINAL", "transit_notes"):
            self.assertIn(word, doc, word)


if __name__ == "__main__":
    unittest.main()
