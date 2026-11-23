"""Tests of the metal pages (audit entries C-038 to C-043): the USGS tables listed in full with "Other countries", the tubes
figure of steel, the notes of the trading hubs and the unit-value flag of aluminium flows. Numbers are those of the entries.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_metal_pages.py"
A class is skipped when the files it reads are absent (raw/ is not tracked).
"""
import json
import os
import sys
import unittest

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("freight", "trade", "geo", "commodities"):
    p = os.path.join(ROOT, "pipeline", sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import build_commodities as B  # noqa: E402

COMMOD = os.path.join(ROOT, "data", "commodities")
HAS_USGS = os.path.exists(B.USGS_FILE)


@unittest.skipUnless(HAS_USGS, "raw/usgs is not on disk")
class FullTables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.us = B.Usgs()

    def test_steel_shares_on_the_sum_of_the_components(self):
        r, _ = self.us.ranked("Iron And Steel", "Raw steel", "Mt", 1.0, "raw steel production", full=True)
        self.assertEqual(len(r["rows"]), 11)
        self.assertEqual(r["other"], 230)
        self.assertEqual(r["world"], 1823)  # not the rounded 1,900 of USGS: its countries and 'Other countries' add up to 1,823
        self.assertIn("1,900", r["n"])
        self.assertIn("4.2%", r["n"])

    def test_steel_without_full_keeps_the_usgs_total(self):
        r, _ = self.us.ranked("Iron And Steel", "Raw steel", "Mt", 1.0, "raw steel production")
        self.assertEqual(r["world"], 1900)
        self.assertNotIn("other", r)

    def test_gold_lists_all_13_countries_and_other(self):
        r, _ = self.us.ranked("Gold", "Mine production", "t Au", 1.0, "gold mine production", full=True)
        self.assertEqual(len(r["rows"]), 13)
        self.assertEqual(r["other"], 1000)
        self.assertEqual(r["world"], 3300)  # within 2% of the sum of the components: the USGS total stays
        self.assertIn("BRA", [x["c"] for x in r["rows"]])

    def test_alumina_refinery_lists_all_19_countries(self):
        r, _ = self.us.ranked("Alumina", "Alumina, refinery production", "Mt", 1e-3, "alumina refinery production", full=True)
        self.assertEqual(len(r["rows"]), 19)
        self.assertEqual(r["other"], 1.3)

    def test_no_dot_semicolon_in_the_bauxite_note(self):
        r, _ = self.us.ranked("Bauxite", "Bauxite, mine production", "Mt", 1e-3, "bauxite mine production")
        self.assertNotIn(".;", r["n"])


class Tubes(unittest.TestCase):
    def test_tubes_are_35_8_mt_and_china_10_1(self):
        tb = B.hs4_exports(["7304", "7305", "7306"], 2024)
        if not tb:
            self.skipTest("the HS4 extract is not of 2024")
        self.assertAlmostEqual(sum(tb.values()) / 1e6, 35.8, delta=0.05)
        self.assertAlmostEqual(tb["CHN"] / 1e6, 10.1, delta=0.05)


class FakeBaci:
    """Just enough of Baci for metal_row_notes(): group(g, year) returns a frame of cleaned flows."""
    def __init__(self, rows):
        self.df = pd.DataFrame(rows, columns=["group", "year", "o", "d", "t", "usd"])

    def group(self, g, year=B.BACI_YEAR):
        return self.df[(self.df["group"] == g) & (self.df["year"] == year)]


def table(rows, **kw):
    return {"y": B.BACI_YEAR, "s": "baci", "u": "Mt", "rows": [{"c": c, "v": v} for c, v in rows], **kw}


class HubNotes(unittest.TestCase):
    def docs(self):
        return {
            "copper": {"extra": [{"key": "refined-imports", "table": table([("CHN", 4.5), ("CHE", 0.4959)])}]},
            "aluminium": {"production": table([("MYS", 1100.0)]), "exports": table([("MYS", 1.87), ("NLD", 1.27)]),
                          "imports": table([("NLD", 1.387)]),
                          "flows": [{"o": "USA", "d": "MYS", "v": 0.5355, "u": "Mt", "y": B.BACI_YEAR, "s": "baci"},
                                    {"o": "CAN", "d": "USA", "v": 2.745, "u": "Mt", "y": B.BACI_YEAR, "s": "baci"}]},
            "manganese": {"production": table([("ZAF", 7000.0)]), "imports": table([("CHN", 29.1), ("SGP", 0.8798)])},
            "pgm": {"production": table([("ZAF", 100.0)]), "exports": table([("ZAF", 415.0), ("ARE", 186.7)])},
            "iron-ore": {"imports": table([("MYS", 25.7)]), "exports": table([("MYS", 14.4)])},
            "cobalt": {"exports": table([("COD", 640.0), ("COG", 6.6)])},
        }

    def baci(self):
        y = B.BACI_YEAR
        return FakeBaci([
            ("copper-refined", y, "ZMB", "CHE", 490000, 4.0e6),
            ("aluminium", y, "USA", "MYS", 535511, 553676),    # 1,034 USD/t
            ("aluminium", y, "CAN", "USA", 2744771, 7.75e6),   # 2,823 USD/t
            ("aluminium", y, "NLD", "DEU", 446506, 1.17e6),
            ("cobalt", y, "COG", "MYS", 5741, 25972), ("cobalt", y, "COD", "CHN", 628589, 3020221),
        ])

    def test_notes_are_written_and_worded_as_hypotheses(self):
        docs = self.docs()
        B.metal_row_notes(docs, self.baci())
        note = lambda cid, sec, c, key=None: next(r.get("n", "") for r in ((next(x["table"] for x in docs[cid]["extra"] if x["key"] == key) if key else docs[cid][sec])["rows"]) if r["c"] == c)
        self.assertIn("0.49 Mt of it comes from Zambia", note("copper", None, "CHE", "refined-imports"))
        self.assertIn("rank 2", note("aluminium", "exports", "NLD"))
        self.assertIn("Singapore", note("manganese", "imports", "SGP"))
        self.assertIn("United Arab Emirates", note("pgm", "exports", "ARE"))
        self.assertIn("importer (rank 1, 25.7 Mt)", note("iron-ore", "imports", "MYS"))
        self.assertIn("wrong Congo", note("cobalt", "exports", "COG"))
        self.assertIn("15 October 2025", note("cobalt", "exports", "COD"))
        for cid, sec, c in (("copper", None, "CHE"), ("aluminium", "exports", "NLD"), ("manganese", "imports", "SGP"), ("pgm", "exports", "ARE")):
            self.assertIn("not established here", note(cid, sec, c, "refined-imports" if cid == "copper" else None))

    def test_no_hub_note_when_the_facts_do_not_hold(self):
        docs = self.docs()
        docs["pgm"]["production"] = table([("ZAF", 100.0), ("ARE", 5.0)])  # a listed producer: no re-export note
        docs["manganese"]["production"] = table([("SGP", 10.0)])
        B.metal_row_notes(docs, self.baci())
        self.assertEqual([r.get("n") for r in docs["pgm"]["exports"]["rows"] if r["c"] == "ARE"], [None])
        self.assertEqual([r.get("n") for r in docs["manganese"]["imports"]["rows"] if r["c"] == "SGP"], [None])

    def test_aluminium_flow_priced_under_half_the_metal_is_flagged(self):
        docs = self.docs()
        B.metal_row_notes(docs, self.baci())
        usa_mys, can_usa = docs["aluminium"]["flows"]
        self.assertIn("1,034 USD/t", usa_mys["n"])
        self.assertIn("scrap", usa_mys["n"])
        self.assertIn("not established here", usa_mys["n"])
        self.assertNotIn("n", can_usa)


class BuiltFiles(unittest.TestCase):
    """The rebuilt files (data/commodities) carry what the entries ask for."""
    def load(self, cid):
        p = os.path.join(COMMOD, cid + ".json")
        if not os.path.exists(p):
            self.skipTest(p + " is absent")
        return json.load(open(p, encoding="utf-8"))

    def test_cobalt_is_not_labelled_ore(self):
        d = self.load("cobalt")
        self.assertEqual(d["kpis"]["exports"], "World exports (intermediates and metal, gross wt)")
        self.assertNotRegex(d["kpis"]["exports"], r"\bores?\b")  # the page title no longer comes from the word "ores" of the note

    def test_index_hs_codes_follow_the_pipeline(self):
        idx = {e["id"]: e for e in json.load(open(os.path.join(COMMOD, "index.json"), encoding="utf-8"))}
        self.assertEqual(idx["cobalt"]["hs"], ["2605", "810510"])
        # HS 253090 is read for spodumene concentrate since package W3M1 (pipeline/trade/hs_map.py SPLIT)
        self.assertEqual(idx["lithium"]["hs"], ["283691", "282520", "253090"])

    def test_bauxite_has_its_two_discrepancies_and_the_importers_table(self):
        d = self.load("bauxite")
        text = " ".join(d["discrepancies"])
        self.assertIn("Guinea 2025", text)
        self.assertIn("182.8", text)
        self.assertIn("Indonesia, alumina", text)
        self.assertIn("alumina-imports", [x["key"] for x in d["extra"]])

    def test_steel_gold_tables_keep_other_countries(self):
        self.assertEqual(self.load("steel")["production"]["other"], 230)
        self.assertEqual(self.load("gold")["production"]["other"], 1000)


if __name__ == "__main__":
    unittest.main()
