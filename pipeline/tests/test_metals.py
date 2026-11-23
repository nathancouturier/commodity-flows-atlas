"""Tests of the metals pages (audit M-017, M-018, A-013, A-014, C-043): apparent consumption, concentration, unit value, the
six-digit split, the unit-value check K13 and the files that were built.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_metals.py"
The classes that read the data files are skipped when they are absent.
"""
import json
import os
import sys
import unittest

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("commodities", "trade"):
    p = os.path.join(ROOT, "pipeline", sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import metals as M  # noqa: E402
import checks as K  # noqa: E402

COMMOD = os.path.join(ROOT, "data", "commodities")


class ApparentConsumption(unittest.TestCase):
    """production + imports - exports, worked by hand; a country with a missing term or a negative result is dropped and counted."""

    def test_refined_copper(self):
        # kt of refined copper: Japan 1,570 + 8 - 607 = 971; Germany 597 + 441 - 123 = 915
        rows, missing, negative = M.apparent_consumption({"JPN": 1570.0, "DEU": 597.0}, {"JPN": 8.0, "DEU": 441.0}, {"JPN": 607.0, "DEU": 123.0})
        self.assertEqual([(c, v) for c, v, _ in rows], [("JPN", 971.0), ("DEU", 915.0)])
        self.assertEqual((missing, negative), ([], []))

    def test_primary_aluminium(self):
        # kt: India 4,200 + 394 - 1,950 = 2,644
        rows, _, _ = M.apparent_consumption({"IND": 4200.0}, {"IND": 394.0}, {"IND": 1950.0})
        self.assertEqual(rows[0][0], "IND")
        self.assertAlmostEqual(rows[0][1], 2644.0)
        self.assertEqual(rows[0][2], (4200.0, 394.0, 1950.0))  # the three inputs travel with the row, for its note

    def test_crude_steel(self):
        # Mt: United States 79.5 + 23.9 - 7.2 = 96.2
        rows, _, _ = M.apparent_consumption({"USA": 79.5}, {"USA": 23.9}, {"USA": 7.2})
        self.assertAlmostEqual(rows[0][1], 96.2)

    def test_a_country_with_a_missing_term_or_a_negative_result_is_dropped(self):
        prod = {"AAA": 10.0, "BBB": 10.0, "CCC": 10.0, "DDD": 10.0}
        imp = {"AAA": 1.0, "BBB": 1.0, "DDD": 0.0}  # CCC has no import row
        exp = {"AAA": 2.0, "BBB": 30.0, "CCC": 1.0, "DDD": 0.0}
        rows, missing, negative = M.apparent_consumption(prod, imp, exp)
        self.assertEqual([c for c, _, _ in rows], ["DDD", "AAA"])  # 10 + 0 - 0 = 10; 10 + 1 - 2 = 9
        self.assertEqual(missing, ["CCC"])
        self.assertEqual(negative, ["BBB"])

    def test_a_trading_country_without_production_is_not_listed(self):
        rows, missing, negative = M.apparent_consumption({"AAA": 5.0}, {"AAA": 1.0, "ZZZ": 4.0}, {"AAA": 0.5, "ZZZ": 0.0})
        self.assertEqual([c for c, _, _ in rows], ["AAA"])
        self.assertEqual(missing + negative, [])


class Concentration(unittest.TestCase):
    def test_herfindahl_on_a_fixed_sample(self):
        # shares 50%, 30%, 20%: 2,500 + 900 + 400 = 3,800; one country: 10,000; four equal countries: 2,500
        self.assertAlmostEqual(M.herfindahl([0.5, 0.3, 0.2]), 3800.0)
        self.assertAlmostEqual(M.herfindahl([1.0]), 10000.0)
        self.assertAlmostEqual(M.herfindahl([0.25] * 4), 2500.0)

    def test_concentration_of_a_table(self):
        t = {"rows": [{"c": "AAA", "v": 50.0}, {"c": "BBB", "v": 30.0}, {"c": "CCC", "v": 10.0}, {"c": "DDD", "v": 5.0}], "world": 100.0, "s": "baci"}
        c = M.concentration(t)
        self.assertEqual(c["top1"], {"c": "AAA", "p": 0.5})
        self.assertAlmostEqual(c["top3"], 0.9)
        self.assertEqual(c["hhi"], round(2500 + 900 + 100 + 25))
        self.assertAlmostEqual(c["cov"], 0.95)  # 5% of the world is not in a listed country (the index is a lower bound)
        self.assertNotIn("est", c)

    def test_an_estimate_in_a_table_marks_its_concentration(self):
        t = {"rows": [{"c": "AAA", "v": 60.0, "est": True}, {"c": "BBB", "v": 40.0}], "world": 100.0, "s": "baci"}
        self.assertTrue(M.concentration(t)["est"])

    def test_no_world_total_no_concentration(self):
        self.assertIsNone(M.concentration({"rows": [{"c": "AAA", "v": 1.0}]}))


class UnitValue(unittest.TestCase):
    def test_usd_per_tonne(self):
        # 553,676 thousand USD for 535,511 t: 1,034 USD per tonne (USA to Malaysia, aluminium, 2024)
        self.assertEqual(M.unit_value(553676, 535511), 1030)

    def test_unit_value_is_hidden_on_an_estimated_row(self):
        self.assertIsNone(M.unit_value(553676, 535511, est_share=0.5))
        self.assertIsNone(M.unit_value(553676, 535511, est_share=0.10))
        self.assertIsNotNone(M.unit_value(553676, 535511, est_share=0.09))

    def test_no_value_or_no_tonnage_no_unit_value(self):
        self.assertIsNone(M.unit_value(0, 100))
        self.assertIsNone(M.unit_value(100, 0))


class HubNotes(unittest.TestCase):
    class B:
        cname = staticmethod(lambda c: {"BEL": "Belgium", "CHN": "China"}.get(c, c))
        joinn = staticmethod(lambda a, b: b if not a else f"{a}; {b}")

    def docs(self):
        t = lambda rows: {"u": "Mt", "world": 10.0, "rows": [{"c": c, "v": v} for c, v in rows]}
        return {"tin": {"production": t([("CHN", 1.0)]), "exports": t([("CHN", 0.9), ("BEL", 0.5)]), "imports": t([("CHN", 0.9), ("BEL", 0.6)])}}

    def test_a_country_that_imports_and_exports_alike_and_is_no_listed_producer_gets_a_note(self):
        d = self.docs()
        done = M.hub_notes(self.B, d)
        self.assertEqual(done, ["tin/exports/BEL"])
        note = d["tin"]["exports"]["rows"][1]["n"]
        self.assertIn("exporter (rank 2", note)
        self.assertIn("not established here", note)
        self.assertEqual(d["tin"]["imports"]["rows"][1]["n"], note)  # both rows carry it
        self.assertNotIn("n", d["tin"]["exports"]["rows"][0])  # China is a listed producer: no note

    def test_no_note_when_the_tonnages_differ(self):
        d = self.docs()
        d["tin"]["imports"]["rows"][1]["v"] = 0.1
        self.assertEqual(M.hub_notes(self.B, d), [])


class K13(unittest.TestCase):
    def frame(self):
        rows = [("aluminium", 2024, "AAA", "BBB", 1e6, 2.6e6), ("aluminium", 2024, "CCC", "DDD", 1e6, 2.4e6), ("aluminium", 2024, "EEE", "FFF", 0.5e6, 0.5e6),
                ("aluminium", 2024, "GGG", "HHH", 1e3, 1.0)]
        df = pd.DataFrame(rows, columns=["group", "year", "o", "d", "t", "usd"])
        df["imputed"] = False
        return df

    def test_a_pair_far_below_the_others_is_flagged(self):
        f = K.k13(self.frame(), 2024)
        self.assertEqual([(r["o"], r["d"]) for r in f], [("EEE", "FFF")])  # 1,000 USD/t against a median of about 2,500
        self.assertEqual(f[0]["unitValue"], 1000)

    def test_an_estimated_pair_is_not_a_reference_and_is_not_flagged(self):
        df = self.frame()
        df.loc[df["o"] == "EEE", "imputed"] = True
        self.assertEqual(K.k13(df, 2024), [])


class SixDigitSplit(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(M.HS6_DETAIL), "the six-digit extract is absent")
    def test_the_detail_adds_up_to_the_main_extract(self):
        c = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        h = pd.read_csv(M.HS6_DETAIL, dtype={"hs6": str})
        for g in M.SPLITS:
            a = c[(c["group"] == g) & (c["year"] == 2024)]["t"].sum()
            b = h[(h["group"] == g) & (h["year"] == 2024)]["t"].sum()
            self.assertAlmostEqual(a / b, 1.0, places=3)


@unittest.skipUnless(os.path.exists(os.path.join(COMMOD, "copper.json")), "data/commodities is absent")
class BuiltFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = {c: json.load(open(os.path.join(COMMOD, c + ".json"), encoding="utf-8")) for c in ("copper", "aluminium", "steel", "zinc", "gold", "iron-ore")}

    def test_consumption_tables_are_atlas_estimates_with_their_three_inputs(self):
        for cid in ("copper", "aluminium", "steel"):
            t = self.d[cid]["consumption"]
            self.assertEqual((t["s"], t["y"], t["est"]), ("atlas", 2024, True))
            self.assertTrue(t["n"].startswith("Atlas estimate"))
            for r in t["rows"]:
                self.assertTrue(r["est"] and r["s"] == "atlas")
                self.assertIn("production", r["n"])
                self.assertIn("imports", r["n"])
                self.assertIn("exports", r["n"])

    def test_one_row_reproduces_by_hand_from_the_tables_of_the_same_year(self):
        # steel, Japan: the USGS 2024 production + imports - exports of the page's own tables
        d = self.d["steel"]
        j = next(r for r in d["consumption"]["rows"] if r["c"] == "JPN")
        imp = next(r["v"] for r in d["imports"]["rows"] if r["c"] == "JPN")
        exp = next(r["v"] for r in d["exports"]["rows"] if r["c"] == "JPN")
        prod = float(j["n"].split("production ")[1].split(" Mt")[0].replace(",", ""))
        self.assertAlmostEqual(j["v"], prod + imp - exp, delta=0.02 * j["v"])

    def test_the_table_says_how_many_countries_were_dropped(self):
        n = self.d["copper"]["consumption"]["n"]
        self.assertIn("left out because one of the three terms is missing", n)
        self.assertIn("because the result is negative", n)
        self.assertIn("refined copper (HS 7403)", n)  # refined metal against refined metal, not HS 7402

    def test_every_usgs_table_with_an_other_line_has_shares_on_the_sum_of_its_lines(self):
        for cid in ("zinc", "gold", "steel"):
            t = self.d[cid]["production"]
            lines = sum(r["v"] for r in t["rows"]) + t["other"]
            self.assertAlmostEqual(lines, t["world"], delta=1e-9 * t["world"] + 0.05)

    def test_trade_rows_carry_value_and_unit_value_and_estimated_rows_no_unit_value(self):
        for cid in ("aluminium", "copper", "gold"):
            for sec in ("exports", "imports"):
                t = self.d[cid][sec]
                self.assertTrue(all("usd" in r for r in t["rows"]), (cid, sec))
                for r in t["rows"]:
                    if r.get("est"):
                        self.assertNotIn("uv", r, (cid, sec, r["c"]))
        al = self.d["aluminium"]["exports"]["rows"][0]
        self.assertAlmostEqual(al["uv"], al["usd"] / (al["v"] * 1e6), delta=0.01 * al["uv"])

    def test_flows_carry_value(self):
        f = next(f for f in self.d["aluminium"]["flows"] if f["o"] == "USA" and f["d"] == "MYS")
        self.assertEqual(f["uv"], 1030)
        # the K13 flag, worded as a hypothesis: its text is in the flow's note, or in data/freight/caveats.json once build_lanes.py has run
        text = f.get("n") or json.load(open(os.path.join(ROOT, "data", "freight", "caveats.json"), encoding="utf-8"))[f["caveat"]]["text"]
        self.assertIn("tonne-weighted median", text)
        self.assertIn("not established here", text)

    def test_aluminium_is_split_between_its_two_codes(self):
        keys = {x["key"] for x in self.d["aluminium"]["extra"]}
        self.assertTrue({"760110-exports", "760120-exports", "760110-imports", "760120-imports"} <= keys)
        tot = self.d["aluminium"]["exports"]["world"]
        parts = sum(x["table"]["world"] for x in self.d["aluminium"]["extra"] if x["key"].endswith("-exports"))
        self.assertAlmostEqual(parts, tot, delta=0.01 * tot)

    def test_concentration_is_computed_for_each_table_with_a_world_total(self):
        c = self.d["copper"]["concentration"]
        self.assertIn("production", c)
        self.assertIn("refinery", c)
        self.assertEqual(c["refinery"]["top1"]["c"], "CHN")

    def test_united_states_figures_are_published_ones(self):
        u = self.d["copper"]["us"]
        self.assertEqual(u["s"], "usgs-mcs")
        self.assertEqual([v["v"] for v in u["consumption"][0]["vals"]], [1860.0, 2200.0])
        self.assertEqual(u["reliance"][0]["pct"], "57")

    def test_iron_content_tables_are_published_figures(self):
        keys = {x["key"]: x["table"] for x in self.d["iron-ore"]["extra"]}
        self.assertEqual(keys["fe-production"]["u"], "Mt Fe")
        self.assertEqual(keys["fe-production"]["s"], "usgs-mcs")


if __name__ == "__main__":
    unittest.main()
