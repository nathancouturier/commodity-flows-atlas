"""Tests of package W3A (agriculture and fertiliser pages): urea production in product tonnes, the potash unit, the cocoa
world total against the ICCO's, the unit of coffee, cocoa and cotton, and the Myanmar gateway.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The tests of the data files read the files as the builders last wrote them.
"""
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))

import build_commodities as B  # noqa: E402
import checks as K  # noqa: E402
import ports  # noqa: E402

DATA = os.path.join(ROOT, "data")


def load(rel):
    with open(os.path.join(DATA, rel), encoding="utf-8") as f:
        return json.load(f)


class FertiliserYearTests(unittest.TestCase):
    def test_a_year_without_the_big_producers_is_not_the_table_year(self):
        # the shape of FAOSTAT urea: the latest year has 20 small reporters, no China
        by = {2021: {"CHN": (57e6, "A"), "IND": (28e6, "A")}, 2022: {"CHN": (57e6, "A"), "IND": (28e6, "A")},
              2023: {"CHN": (62e6, "A"), "IND": (31e6, "A")}, 2024: {"IND": (30e6, "A"), "RUS": (10e6, "A")}}
        self.assertEqual(B.fertilizer_year(by), 2023)

    def test_the_latest_year_is_kept_when_it_is_complete(self):
        by = {2022: {"CHN": (57e6, "A")}, 2023: {"CHN": (62e6, "A")}, 2024: {"CHN": (60e6, "A")}}
        self.assertEqual(B.fertilizer_year(by), 2024)

    def test_urea_production_of_the_cache(self):
        by = B.faostat_fertilizer("4001")
        y = B.fertilizer_year(by)
        self.assertEqual(y, 2023)
        self.assertAlmostEqual(by[2023]["CHN"][0] / 1e6, 62.915, places=3)
        self.assertNotIn("CHN", by[2024])  # the reason why 2024 is not used


class UreaPageTests(unittest.TestCase):
    d = load("commodities/urea.json")

    def test_the_ammonia_block_is_named_for_what_it_is(self):
        self.assertEqual(self.d["kpis"]["production"], "Ammonia production (Mt N)")
        self.assertIn("Mt of nitrogen", self.d["labels"]["production"])
        self.assertEqual(self.d["summary"]["production"]["u"], "Mt N")

    def test_urea_production_is_in_product_tonnes_with_its_source(self):
        t = next(x for x in self.d["extra"] if x["key"] == "urea-production")
        self.assertIn("product weight", t["title"])
        self.assertEqual((t["table"]["s"], t["table"]["u"], t["table"]["y"]), ("faostat-rfb", "Mt", 2023))
        self.assertEqual(t["table"]["rows"][0], {"c": "CHN", "v": 62.915})
        self.assertNotIn("world", t["table"])  # FAOSTAT has no world total: none is invented
        sources = {s["id"]: s for s in load("sources.json")}
        self.assertEqual(sources["faostat-rfb"]["licence"][:8], "CC BY 4.")

    def test_the_gaps_of_the_source_are_written(self):
        text = " ".join(self.d["notes"])
        self.assertIn("FAOSTAT has no 2023 urea production figure for", text)
        self.assertIn("2024 urea table is not used", text)
        self.assertNotIn("not in the loaded sources", text)


class PotashPageTests(unittest.TestCase):
    d = load("commodities/potash.json")

    def test_production_is_in_the_unit_of_the_trade_tables(self):
        p, k2o = self.d["production"], next(x for x in self.d["extra"] if x["key"] == "k2o-production")["table"]
        self.assertEqual((p["s"], p["u"]), ("atlas", "Mt KCl"))
        self.assertTrue(p["n"].startswith("Atlas conversion:"))
        can_k2o = next(r["v"] for r in k2o["rows"] if r["c"] == "CAN")
        can_kcl = next(r["v"] for r in p["rows"] if r["c"] == "CAN")
        self.assertAlmostEqual(can_kcl, can_k2o / K.K2O_IN_KCL, places=2)
        self.assertEqual(k2o["u"], "Mt K2O")

    def test_every_title_and_kpi_carries_its_unit(self):
        for k, v in self.d["labels"].items():
            self.assertIn("Mt", v, k)
        for k, v in self.d["kpis"].items():
            self.assertIn("Mt", v, k)

    def test_canada_exports_are_within_20_percent_of_its_production_in_the_same_unit(self):
        # before: 26.6 Mt of potassium chloride exported against 15.0 Mt K2O produced (+77%)
        can_kcl = next(r["v"] for r in self.d["production"]["rows"] if r["c"] == "CAN")
        can_exp = next(r["v"] for r in self.d["exports"]["rows"] if r["c"] == "CAN")
        self.assertLess(can_exp / can_kcl, 1.2)


class CocoaPageTests(unittest.TestCase):
    d = load("commodities/cocoa.json")

    def test_the_world_total_is_set_beside_the_icco_with_its_crop_year(self):
        text = " ".join(self.d["discrepancies"])
        self.assertIn("4,362 kt for the 2023/24 crop year", text)
        self.assertIn("20% above", text)
        self.assertIn("icco.org", text)
        self.assertIn("20%", self.d["production"]["caveat"])
        self.assertIn("icco", {s["id"] for s in load("sources.json")})

    def test_indonesia_carries_a_note(self):
        row = next(r for r in self.d["production"]["rows"] if r["c"] == "IDN")
        self.assertIn("same value for 2021 and 2022", row["n"])
        self.assertIn("not free", row["n"])

    def test_no_icco_table_is_copied(self):
        self.assertNotIn("icco", {self.d["production"]["s"]})
        self.assertEqual(len(self.d["discrepancies"]), 1)


class UnitTests(unittest.TestCase):
    def test_coffee_cocoa_and_cotton_are_in_mt_like_their_seaborne_figure(self):
        for cid in ("coffee", "cocoa", "cotton"):
            d = load(f"commodities/{cid}.json")
            self.assertEqual(d["summary"]["production"]["u"], "Mt", cid)
            self.assertEqual(d["summary"]["seaborne"]["u"], "Mt", cid)
            self.assertEqual(d["exports"]["u"], "Mt", cid)
            self.assertEqual(d["flows"][0]["u"], "Mt", cid)
        idx = {e["id"]: e for e in load("commodities/index.json")}
        self.assertEqual([idx[c]["unit"] for c in ("coffee", "cocoa", "cotton")], ["Mt"] * 3)
        self.assertEqual(round(load("commodities/coffee.json")["summary"]["production"]["v"], 1), 10.7)  # was 10,730 kt


class MyanmarGatewayTests(unittest.TestCase):
    def test_imports_of_palm_oil_and_rice_go_to_yangon_not_sittwe(self):
        for g in ("palm-oil", "rice", "urea"):
            code, _, basis = ports.candidates("MMR", g, "discharge")[0]
            self.assertEqual(code, "MMRGN", g)
            self.assertEqual(basis, "general port of the country")
        self.assertEqual(ports.port("MMRGN")["name"], "Yangon")

    def test_pasir_gudang_keeps_its_name(self):
        self.assertEqual(ports.port("MYPGU")["name"], "Pasir Gudang")


if __name__ == "__main__":
    unittest.main()
