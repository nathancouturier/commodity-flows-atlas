"""Tests of package W3E (energy pages): the gas and LNG tables, the second unit of the headline figures, the LPG
caveats and the small gas carrier class.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The tests of the data files read the files as the builders last wrote them.
"""
import glob
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))

import pandas as pd  # noqa: E402

import caveats  # noqa: E402
import vessel_rules as VR  # noqa: E402

DATA = os.path.join(ROOT, "data")
HAS_EIA = os.path.exists(os.path.join(ROOT, "raw", "eia", "INTL.txt"))


def load(rel):
    with open(os.path.join(DATA, rel), encoding="utf-8") as f:
        return json.load(f)


def lpg_frame(iran_2024):
    rows = [("IRN", "CHN", 2018, 5.6e6), ("IRN", "CHN", 2022, 8.44e6), ("IRN", "CHN", 2024, iran_2024),
            ("OMN", "CHN", 2024, 2.75e6), ("OMN", "IND", 2024, 0.44e6),
            ("ARE", "CHN", 2024, 6.98e6), ("ARE", "IND", 2024, 10.58e6)]
    return pd.DataFrame(rows, columns=["o", "d", "year", "t"]).assign(group="lpg")


class LpgCaveatTests(unittest.TestCase):
    def test_iran_and_the_pairs_are_flagged_while_iranian_exports_are_unrecorded(self):
        a = caveats.build(lpg_frame(7.7e3), [], 2024, psd=None)
        self.assertEqual(caveats.lookup(a, "lpg", "IRN", "CHN"), "lpg-irn")
        self.assertIn("0.0077 Mt of LPG exports from Iran in 2024, against 8.44 Mt in 2022", a["lpg-irn"]["text"])
        self.assertIn("not quantified", a["lpg-irn"]["text"])
        self.assertEqual(caveats.lookup(a, "lpg", "OMN", "CHN"), "lpg-omn-chn")
        self.assertEqual(caveats.lookup(a, "lpg", "ARE", "CHN"), "lpg-are-chn")
        self.assertIn("86% of its recorded exports", a["lpg-omn-chn"]["text"])
        self.assertIn("40% of its recorded exports", a["lpg-are-chn"]["text"])
        self.assertIn("may account for part", a["lpg-omn-chn"]["text"])
        self.assertIn("not established here", a["lpg-omn-chn"]["text"])
        # a pair to another destination carries no caveat
        self.assertIsNone(caveats.lookup(a, "lpg", "OMN", "IND"))

    def test_nothing_is_flagged_when_iranian_exports_are_recorded(self):
        a = caveats.build(lpg_frame(6e6), [], 2024, psd=None)
        self.assertFalse([k for k in a if k.startswith("lpg")])

    def test_russian_products_entry_is_a_hypothesis(self):
        rows = [("RUS", "TUR", 2024, 16.1e6), ("RUS", "CHN", 2024, 14.3e6)]
        df = pd.DataFrame(rows, columns=["o", "d", "year", "t"]).assign(group="refined-products")
        a = caveats.build(df, [], 2024, psd=None)
        t = a["refined-products-rus"]["text"]
        self.assertIn("30.4 Mt of refined products exports from Russia", t)
        self.assertIn("importers' declarations", t)
        self.assertIn("not established here", t)


class LpgVesselRuleTests(unittest.TestCase):
    def test_short_hauls_go_to_mid_size_carriers(self):
        self.assertEqual(VR.classes("lpg", "NOR", "SWE", 0.63e6, 392), ["mgc"])  # 0.63 Mt, 392 nm
        self.assertEqual(VR.classes("lpg", "DZA", "ESP", 0.3e6, 273), ["mgc"])
        # 9.33 Mt over 718 nm is above one VLGC parcel a week: VLGCs second
        self.assertEqual(VR.classes("lpg", "USA", "MEX", 9.33e6, 718), ["mgc", "vlgc"])

    def test_medium_hauls_of_small_lanes_have_mid_size_first_and_vlgc_second(self):
        self.assertEqual(VR.classes("lpg", "USA", "ECU", 1.36e6, 2061), ["mgc", "vlgc"])

    def test_the_gulf_to_india_trade_keeps_the_vlgc(self):
        self.assertEqual(VR.classes("lpg", "ARE", "IND", 8.97e6, 1014), ["vlgc"])  # a Baltic VLGC benchmark route
        self.assertEqual(VR.classes("lpg", "KWT", "IND", 3.6e6, 1297), ["vlgc"])

    def test_long_hauls_stay_on_vlgc(self):
        self.assertEqual(VR.classes("lpg", "USA", "CHN", 18e6, 9500), ["vlgc"])
        self.assertEqual(VR.classes("lpg", "ARE", "CHN", 6.98e6, 4000), ["vlgc"])
        self.assertEqual(VR.classes("lpg", "USA", "CHN", 18e6, 5000), ["vlgc"])  # the first pass of the lane builder uses 5,000 nm

    def test_the_weekly_parcel_threshold_is_the_baltic_parcel(self):
        self.assertAlmostEqual(VR.VLGC_WEEKLY_MT, 2.288, places=3)  # 44 kt x 52 weeks
        self.assertEqual(VR.classes("lpg", "X", "Y", 2.2e6, 800), ["mgc"])
        self.assertEqual(VR.classes("lpg", "X", "Y", 2.3e6, 800), ["mgc", "vlgc"])

    def test_the_class_is_described_with_a_source(self):
        with open(os.path.join(ROOT, "pipeline", "freight", "vessel_classes.json"), encoding="utf-8") as f:
            classes = {c["id"]: c for c in json.load(f)}
        c = classes["mgc"]
        self.assertEqual((c["size"]["min"], c["size"]["max"], c["size"]["u"]), (25000, 50000, "cbm"))
        self.assertEqual(c["cargoes"], ["lpg", "urea"])  # and ammonia, on the page "Urea & nitrogen" (package NC1)
        with open(os.path.join(DATA, "sources.json"), encoding="utf-8") as f:
            self.assertIn(c["s"], {s["id"] for s in json.load(f)})
        # the class sits below the VLGC band
        self.assertLessEqual(c["size"]["max"], classes["vlgc"]["size"]["min"])


@unittest.skipUnless(HAS_EIA, "raw/eia/INTL.txt absent")
class BuilderHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build_commodities as B
        cls.B = B

    def test_lng_factor_is_the_published_one(self):
        self.assertEqual(round(self.B.BCM_PER_MT_LNG, 2), 1.36)
        self.assertAlmostEqual(self.B.BCF_PER_MT_LNG, 48.0279467)

    def test_second_unit_of_a_figure(self):
        f = {"v": 100.0, "u": "kb/d", "y": 2025, "s": "eia-intl"}
        self.B.alt_fig(f, 5.5, "Mt/yr", "7.33 barrels per tonne")
        self.assertEqual(f["alt"], {"v": 5.5, "u": "Mt/yr", "s": "atlas", "y": 2025, "n": "Atlas conversion: 7.33 barrels per tonne"})

    def test_pipeline_pairs_come_from_the_atlas_layer(self):
        pairs, n = self.B.gas_pipeline_pairs()
        self.assertGreater(n, 10)
        self.assertIn(("NOR", "GBR"), pairs)  # Langeled, a subsea pipeline
        self.assertNotIn(("BEL", "FRA"), pairs)  # no pipeline of the layer between them
        self.assertNotIn(("GBR", "NOR"), pairs)  # the first country of a pipeline is its origin


class GasPageTests(unittest.TestCase):
    def setUp(self):
        self.d = load("commodities/natural-gas.json")

    def test_countries_are_ranked_on_eia_volumes(self):
        for sec in ("exports", "imports"):
            t = self.d[sec]
            self.assertEqual((t["u"], t["s"]), ("bcm", "eia-intl"))
            self.assertIn("no LNG split by country", t["n"])
        self.assertEqual([r["c"] for r in self.d["exports"]["rows"][:3]], ["USA", "RUS", "QAT"])
        # Belgium (transit) and Morocco (0.89 bcm in EIA) are out of the first twelve
        self.assertNotIn("BEL", [r["c"] for r in self.d["exports"]["rows"][:12]])  # the tables list every country
        self.assertNotIn("MAR", [r["c"] for r in self.d["imports"]["rows"][:12]])
        self.assertGreater(self.d["exports"]["rows"][0]["v"], 200)  # United States, bcm
        self.assertEqual(self.d["summary"]["exports"]["u"], "bcm")

    def test_flows_are_pipeline_pairs_of_the_layer(self):
        with open(os.path.join(DATA, "infrastructure", "pipelines.geojson"), encoding="utf-8") as f:
            gas = [x["properties"] for x in json.load(f)["features"] if x["properties"].get("product") == "gas"]
        linked = {(cs[i], cs[j]) for p in gas for cs in [p["cs"]] for i in range(len(cs)) for j in range(i + 1, len(cs))}
        self.assertTrue(self.d["flows"])
        for fl in self.d["flows"]:
            self.assertIn((fl["o"], fl["d"]), linked)
            self.assertEqual((fl["mode"], fl["u"], fl["s"]), ("pipeline", "Mt", "baci"))
            self.assertIn("pipeline of the atlas layer", fl["n"])
        self.assertNotIn(("BEL", "FRA"), {(f["o"], f["d"]) for f in self.d["flows"]})
        self.assertIn("customs tonnes", self.d["labels"]["flows"])

    def test_second_unit_and_factor(self):
        # only the trade figure carries one (GW3.10): a producer's gas in LNG tonnes would read as LNG output
        for k in ("production", "consumption"):
            self.assertNotIn("alt", self.d["summary"][k])
        f = self.d["summary"]["exports"]
        self.assertEqual(f["alt"]["u"], "Mt LNG equivalent")
        self.assertAlmostEqual(f["alt"]["v"], f["v"] / 1.36, delta=0.005 * f["v"])
        self.assertTrue(f["alt"]["n"].startswith("Atlas conversion:"))
        self.assertIn("not LNG trade", f["alt"]["n"])


class LngPageTests(unittest.TestCase):
    def setUp(self):
        self.d = load("commodities/lng.json")

    def test_headline_total_is_the_industry_one_with_publisher_and_year(self):
        f = self.d["summary"]["exports"]
        self.assertEqual((f["v"], f["u"], f["y"], f["s"]), (428, "Mt", 2025, "giignl-2026"))
        self.assertIn("406 Mt in 2024", f["n"])
        self.assertIn("371.32 Mt", f["n"])  # the customs total beside it
        self.assertNotIn("about 411", f["n"])
        self.assertEqual(self.d["kpis"]["exports"], "World LNG trade (GIIGNL)")

    def test_second_unit_is_bcm(self):
        for k in ("exports", "seaborne"):
            f = self.d["summary"][k]
            self.assertEqual(f["alt"]["u"], "bcm")
            self.assertAlmostEqual(f["alt"]["v"], f["v"] * 1.36, delta=0.005 * f["v"])

    def test_customs_tables_say_their_order_is_not_the_publishers(self):
        t = self.d["exports"]
        self.assertTrue(t["norank"])
        self.assertTrue(self.d["imports"]["norank"])
        self.assertIn("dominant LNG exporter", t["caveat"])
        self.assertIn("not the publisher's", t["caveat"])

    def test_importers_the_customs_data_miss(self):
        c = self.d["imports"]["caveat"]
        self.assertIn("Kuwait", c)
        self.assertIn("plausible cause", c)

    def test_country_profiles_print_no_lng_rank(self):
        rows = [p for p in (load(f"countries/profiles/{os.path.basename(f)}") for f in glob.glob(os.path.join(DATA, "countries", "profiles", "*.json"))) if "none" not in p]
        seen = 0
        for p in rows:
            for sec in ("exports", "imports"):
                for e in p[sec]:
                    if e["k"] == "lng":
                        seen += 1
                        self.assertNotIn("rank", e, p["c"])
        self.assertGreater(seen, 5)


class UnitPageTests(unittest.TestCase):
    def test_crude_oil_carries_both_units(self):
        d = load("commodities/crude-oil.json")
        p, x = d["summary"]["production"], d["summary"]["exports"]
        self.assertEqual((p["u"], p["alt"]["u"]), ("kb/d", "Mt/yr"))
        self.assertEqual((x["u"], x["alt"]["u"]), ("Mt", "kb/d"))
        bpt = 7.33
        self.assertAlmostEqual(p["alt"]["v"], p["v"] * 1e3 * 365 / bpt / 1e6, delta=0.01 * p["alt"]["v"])
        self.assertAlmostEqual(x["alt"]["v"], x["v"] * 1e6 * bpt / 366 / 1e3, delta=0.01 * x["alt"]["v"])  # 2024 is a leap year
        self.assertIn("7.33 barrels per tonne", p["alt"]["n"])
        self.assertTrue(p["alt"]["n"].startswith("Atlas conversion:"))

    def test_refined_products_russia_note(self):
        d = load("commodities/refined-products.json")
        n = " ".join(d["notes"])
        self.assertIn("Country Analysis Brief: Russia", n)
        self.assertIn("The units differ, so no ratio is computed", n)


if __name__ == "__main__":
    unittest.main()
