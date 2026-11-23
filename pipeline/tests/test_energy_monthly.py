"""Tests of package E1b: the monthly files of the energy pages (data/commodities/monthly), the United States in the LPG consumption
table, and what the EIA file does not hold (oil and gas reserves, refinery capacity).

The expectations are read from raw/eia/INTL.txt itself (the figures the audit quotes: Saudi Arabia 10,760 kb/d in February 2026, 6,600
in April and 7,980 in July; the world low of 73,868 in May; Japan's imports from the Persian Gulf 2,752, 796 and 1,618 kb/d) and
compared with the files as the builder last wrote them.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
"""
import calendar
import json
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "commodities"))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "trade"))

import monthly as MO  # noqa: E402

INTL = os.path.join(ROOT, "raw", "eia", "INTL.txt")
HAS_EIA = os.path.exists(INTL)
DATA = os.path.join(ROOT, "data", "commodities")


def load(rel):
    with open(os.path.join(DATA, rel), encoding="utf-8") as f:
        return json.load(f)


def raw_series(sid):
    """{period: value} of one series of the EIA file, read line by line (not through monthly.py)."""
    key = f'"series_id":"{sid}"'
    with open(INTL, encoding="utf-8") as f:
        for line in f:
            if key in line[:80]:
                return {p: v for p, v in json.loads(line)["data"]}
    raise KeyError(sid)


class Helpers(unittest.TestCase):
    def test_axis_runs_back_over_a_year_end(self):
        self.assertEqual(MO.axis("2026-02", 4), ["2025-11", "2025-12", "2026-01", "2026-02"])

    def test_year_average_weights_the_months_by_their_days(self):
        vals = {f"2024-{m:02d}": 100.0 for m in range(1, 13)}
        vals["2024-02"] = 200.0  # 29 days in 2024
        want = (100.0 * (366 - 29) + 200.0 * 29) / 366
        self.assertAlmostEqual(MO.avg_year(vals, 2024), want)
        del vals["2024-05"]
        self.assertIsNone(MO.avg_year(vals, 2024))  # a missing month is not filled

    def test_stats_lowest_and_latest_month(self):
        vals = {f"2025-{m:02d}": 10.0 for m in range(1, 13)}
        vals.update({"2026-01": 9.0, "2026-02": 4.0, "2026-03": 6.0})
        s = MO.stats(vals, "2026-03")
        self.assertEqual(s["lo"], {"v": 4.0, "m": "2026-02"})
        self.assertEqual(s["la"], {"v": 6.0, "m": "2026-03"})
        self.assertEqual(s["b"], 10.0)
        self.assertEqual(s["p"], -40.0)
        self.assertEqual(len(s["v"]), MO.MONTHS_KEPT)
        self.assertEqual(s["v"][-3:], [9.0, 4.0, 6.0])
        self.assertIsNone(s["v"][0])  # before the first month of the series

    def test_a_series_that_stopped_has_no_latest_month(self):
        self.assertIsNone(MO.stats({"2018-11": 5.0}, "2026-08"))


@unittest.skipUnless(HAS_EIA, "raw/eia/INTL.txt is not on this machine")
class CrudeMonthly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = load("monthly/crude-oil.json")
        cls.p = cls.f["production"]
        cls.row = {r["c"]: r for r in cls.p["rows"]}

    def month(self, r, m):
        return r["v"][MO.axis(self.p["to"], len(r["v"])).index(m)]

    def test_saudi_arabia_february_april_and_july_2026(self):
        raw = raw_series("INTL.57-1-SAU-TBPD.M")
        sa = self.row["SAU"]
        for m, v in (("2026-02", 10760), ("2026-04", 6600), ("2026-07", 7980)):
            self.assertEqual(raw[m.replace("-", "")], v)  # what the audit quotes is in the file
            self.assertEqual(self.month(sa, m), v)  # and in the page's file
        self.assertEqual(sa["lo"], {"v": 6600, "m": "2026-04"})
        self.assertEqual(sa["la"], {"v": 7980, "m": "2026-07"})
        self.assertAlmostEqual(sa["p"], (7980 / sa["b"] - 1) * 100, places=1)

    def test_iraq_kuwait_and_the_world(self):
        self.assertEqual((self.month(self.row["IRQ"], "2026-02"), self.p["rows"][0] and self.row["IRQ"]["lo"]), (4461, {"v": 1320, "m": "2026-05"}))
        self.assertEqual(self.row["KWT"]["lo"], {"v": 570, "m": "2026-04"})
        w = self.p["world"]
        self.assertEqual(self.month(w, "2026-02") // 1, 86795)  # 86,795.8 kb/d
        self.assertEqual(w["lo"]["m"], "2026-05")
        self.assertEqual(round(w["lo"]["v"]), 73868)
        self.assertEqual(w["la"]["m"], "2026-07")
        self.assertEqual(round(w["la"]["v"]), 80344)

    def test_baseline_average_is_the_annual_figure_of_the_same_file(self):
        """The months of 2025 weighted by their days give EIA's own annual figure (the page says so)."""
        annual = raw_series("INTL.57-1-SAU-TBPD.A")
        self.assertAlmostEqual(self.row["SAU"]["b"], annual["2025"], delta=0.01)
        self.assertAlmostEqual(self.p["world"]["b"], raw_series("INTL.57-1-WORL-TBPD.A")["2025"], delta=0.01)
        table = load("crude-oil.json")["production"]
        self.assertEqual(table["y"], self.p["baseYear"])
        for r in table["rows"]:
            if r["c"] in self.row:
                self.assertAlmostEqual(self.row[r["c"]]["b"], r["v"], delta=max(0.002, r["v"] * 2e-3), msg=r["c"])

    def test_every_producer_of_the_table_has_a_row(self):
        table = load("crude-oil.json")["production"]
        missing = [r["c"] for r in table["rows"] if r["c"] not in self.row and r["v"] >= 0.1]
        self.assertEqual(missing, [])
        self.assertGreaterEqual(len(self.p["rows"]), 90)

    def test_gulf_total_adds_the_seven_producers_month_by_month(self):
        g = self.p["gulf"]
        self.assertEqual(sorted(g["members"]), sorted(MO.GULF))
        i = len(g["v"]) - 1
        self.assertAlmostEqual(g["v"][i], sum(self.row[c]["v"][i] for c in g["members"]), places=2)
        self.assertEqual(g["lo"]["m"], "2026-05")

    def test_at_least_36_months_and_the_latest_month_is_named(self):
        self.assertGreaterEqual(len(self.row["SAU"]["v"]), 36)
        self.assertEqual(self.p["to"], "2026-07")
        for r in self.p["rows"]:
            self.assertRegex(r["la"]["m"], r"^\d{4}-\d{2}$")

    def test_japan_from_the_persian_gulf(self):
        jp = next(i for i in self.f["imports"]["importers"] if i["id"] == "JPN")
        row = next(r for r in jp["rows"] if r["o"] == "PERG")
        raw = raw_series("INTL.785-3-PERG-TBPD.M")
        ax = MO.axis(jp["to"], len(row["v"]))
        for m, v in (("2026-02", 2752), ("2026-04", 796), ("2026-08", 1618)):
            self.assertEqual(round(raw[m.replace("-", "")]), v)
            self.assertEqual(round(row["v"][ax.index(m)]), v)
        self.assertEqual(row["name"], "Persian Gulf")

    def test_importer_names_follow_the_series(self):
        """The product code of each importer (78x) is EIA's: the builder refuses a series whose name does not start with the importer."""
        names = {i["id"]: i["name"] for i in self.f["imports"]["importers"]}
        self.assertEqual(names["JPN"], "Japan")
        self.assertEqual(names["OECD"], "OECD")


@unittest.skipUnless(HAS_EIA, "raw/eia/INTL.txt is not on this machine")
class Stocks(unittest.TestCase):
    def test_oecd_and_united_states_stocks_with_days_of_cover(self):
        for cid in ("crude-oil", "refined-products"):
            st = load(f"monthly/{cid}.json")["stocks"]
            self.assertEqual(st["to"], "2026-08")
            rows = {r["c"]: r for r in st["rows"]}
            oecd = raw_series("INTL.5-5-OECD-MBBL.M")["202608"]
            self.assertEqual(rows["OECD"]["la"], {"v": round(oecd, 3), "m": "2026-08"})
            self.assertEqual(round(rows["OECD"]["la"]["v"]), 3825)
            self.assertEqual(round(rows["USA"]["la"]["v"]), 1530)
            cons = raw_series("INTL.54-2-OECD-TBPD.M")["202608"]
            self.assertAlmostEqual(rows["OECD"]["cover"], oecd * 1000 / cons, places=1)  # arithmetic on two figures of the same file and month
            self.assertEqual(rows["OECD"]["end"]["m"], "2025-12")
            self.assertTrue(set(MO.STOCK_ORDER) >= {r["c"] for r in st["rows"]})

    def test_countries_whose_figures_are_withheld_are_listed_not_shown(self):
        st = load("monthly/crude-oil.json")["stocks"]
        self.assertIn("BEL", st["withheld"])
        self.assertNotIn("BEL", {r["c"] for r in st["rows"]})
        self.assertEqual(raw_series("INTL.5-5-BEL-MBBL.M")["202608"], "w")


@unittest.skipUnless(HAS_EIA, "raw/eia/INTL.txt is not on this machine")
class OtherMonthlyBlocks(unittest.TestCase):
    def test_refined_products_demand_and_the_gaps(self):
        f = load("monthly/refined-products.json")
        usa = next(r for r in f["consumption"]["rows"] if r["c"] == "USA")
        self.assertEqual(usa["la"]["v"], round(raw_series("INTL.54-2-USA-TBPD.M")["202608"], 3))
        self.assertTrue(any("production" in g and "2014" in g for g in f["gaps"]))

    def test_lpg_has_natural_gas_plant_liquids_by_month_and_says_what_it_lacks(self):
        f = load("monthly/lpg.json")
        usa = next(r for r in f["ngl"]["rows"] if r["c"] == "USA")
        self.assertEqual(usa["la"]["v"], round(raw_series("INTL.58-1-USA-TBPD.M")["202607"], 3))
        self.assertTrue(f["gaps"])

    def test_lng_has_no_monthly_series_in_the_file(self):
        fam, _ = MO.scan(INTL)
        monthly = [n for (p, fr), n in fam.items() if fr == "M"]
        self.assertFalse([n for n in monthly if re.search(r"\bLNG\b|liquefied natural gas", n, re.I)])
        self.assertTrue(load("monthly/lng.json")["gaps"])


@unittest.skipUnless(HAS_EIA, "raw/eia/INTL.txt is not on this machine")
class WhatTheFileDoesNotHold(unittest.TestCase):
    """The search of package E1b (M-005, M-006): the EIA file has no proved reserves of oil or gas and no refinery capacity or throughput,
    so the atlas shows none (and no other source is used). The test fails if a later file has them, so that the tables get built."""

    @classmethod
    def setUpClass(cls):
        cls.fam, cls.ends = MO.scan(INTL)

    def test_the_only_reserves_series_is_coal(self):
        reserves = {n for (p, f), n in self.fam.items() if re.search(r"reserve", n, re.I)}
        self.assertEqual(reserves, {"Coal reserves"})

    def test_no_refinery_capacity_or_throughput(self):
        names = {n for (p, f), n in self.fam.items() if re.search(r"capacity|throughput|refinery|runs|distillation", n, re.I) and not re.search(r"electricity", n, re.I)}
        # what the search finds is a processing gain and refinery or non-refinery production of LPG and ethane: no capacity, no runs
        self.assertEqual(names, {"Refinery processing gain", "LPG and ethane refinery production", "LPG non-refinery production", "Ethane non-refinery production"})

    def test_refined_product_production_ends_before_the_demand_series(self):
        self.assertEqual(self.ends[("54-1", "TBPD")], 2014)
        self.assertEqual(self.ends[("67-1", "TBPD")], 2014)


@unittest.skipUnless(HAS_EIA, "raw/eia/INTL.txt is not on this machine")
class LpgUnitedStates(unittest.TestCase):
    def test_the_united_states_is_in_the_table_converted_from_barrels_per_day(self):
        d = load("lpg.json")["consumption"]
        usa = next(r for r in d["rows"] if r["c"] == "USA")
        bd = raw_series("INTL.67-2-USA-TBPD.A")["2025"]
        days = 366 if calendar.isleap(2025) else 365
        self.assertAlmostEqual(usa["v"], bd * days / 11.6 / 1000, places=2)  # 1,408 kb/d at 11.60 barrels per tonne
        self.assertIn("Atlas conversion", usa["n"])
        self.assertIn("United States converted", d["n"])
        eia_world = raw_series("INTL.67-2-WORL-MT.A")["2025"] / 1000
        self.assertAlmostEqual(d["world"], eia_world + usa["v"], places=1)  # EIA's world leaves the country out: the table puts it back
        # the countries add up to the world total, and the total agrees with EIA's own world in barrels per day
        self.assertAlmostEqual(sum(r["v"] for r in d["rows"]), d["world"], delta=d["world"] * 0.002)
        world_bd = raw_series("INTL.67-2-WORL-TBPD.A")["2025"]
        self.assertAlmostEqual(d["world"], world_bd * days / 11.6 / 1000, delta=d["world"] * 0.005)
        self.assertNotIn("Excludes the United States", d.get("caveat", ""))

    def test_the_tonnes_of_2021_that_break_from_the_barrels_are_not_used(self):
        h = load("history/lpg.json")["t"]["consumption"]
        i = h["years"].index(2021)
        self.assertEqual(raw_series("INTL.67-2-USA-MT.A")["2021"], 148277.9596)  # EIA's tonnes: 3.4 barrels per tonne against 11.6 before
        self.assertLess(h["c"]["USA"][i], 45)
        self.assertEqual(h["c"]["USA"][i], round(raw_series("INTL.67-2-USA-TBPD.A")["2021"] * 365 / 11.6 / 1000, 3))
        self.assertTrue(all(v is not None for v in h["c"]["USA"][i:]))
        self.assertNotIn("out", h)

    def test_the_second_unit_of_the_headline_and_the_price_conversion(self):
        d = load("lpg.json")
        alt = d["summary"]["consumption"]["alt"]
        self.assertEqual(alt["u"], "kb/d")
        self.assertAlmostEqual(alt["v"], d["summary"]["consumption"]["v"] * 1e6 * 11.6 / 365 / 1e3, delta=alt["v"] * 0.005)
        self.assertIn("11.60 barrels per tonne", alt["n"])
        self.assertTrue(any("487 US gallons" in n for n in d["notes"]))  # 11.6 x 42


class RegistryEntry(unittest.TestCase):
    def test_kuwait_to_vietnam_is_a_hypothesis_while_the_flow_is_unrecorded(self):
        """C-025: customs data recorded 8.6 to 9.6 Mt of Kuwaiti crude to Vietnam in 2018 to 2023 and none in 2024 (read from the cache)."""
        import caveats
        import pandas as pd

        rows = [("KWT", "VNM", 2022, 8.58e6), ("KWT", "VNM", 2023, 9.01e6), ("KWT", "CHN", 2024, 15.97e6)]
        df = pd.DataFrame(rows, columns=["o", "d", "year", "t"]).assign(group="crude-oil", usd=lambda x: x["t"] * 0.5)  # 500 USD a tonne
        a = caveats.build(df, [], 2024, psd=None)
        t = a["crude-kwt-vnm"]["text"]
        self.assertIn("No crude oil from Kuwait to Vietnam is recorded in customs data for 2024 (9.01 Mt in 2023", t)
        self.assertIn("may be the cause; it is not established here", t)
        self.assertEqual(caveats.lookup(a, "crude-oil", "KWT", "VNM"), "crude-kwt-vnm")
        self.assertIsNone(caveats.lookup(a, "crude-oil", "KWT", "CHN"))
        # recorded again: no entry
        df2 = pd.concat([df, pd.DataFrame([("KWT", "VNM", 2024, 7e6)], columns=["o", "d", "year", "t"]).assign(group="crude-oil", usd=3.5e6)])
        self.assertNotIn("crude-kwt-vnm", caveats.build(df2, [], 2024, psd=None))


class UraniumAndCaveats(unittest.TestCase):
    def test_uranium_headline_carries_pounds_of_u3o8(self):
        d = load("uranium.json")
        p = d["summary"]["production"]
        self.assertEqual(p["alt"]["u"], "Mlb U3O8")
        self.assertAlmostEqual(p["alt"]["v"], p["v"] * 2600 / 1e6, delta=p["alt"]["v"] * 0.005)
        self.assertIn("1.1792 t of U3O8", p["alt"]["n"])
        self.assertTrue(any(x["key"] == "nuclear-capacity" for x in d["extra"]))

    def test_iran_has_no_row_and_the_crude_exports_table_says_so(self):
        d = load("crude-oil.json")["exports"]
        self.assertNotIn("IRN", [r["c"] for r in d["rows"]])
        self.assertIn("Iran has no row", d["caveat"])
        self.assertIn("is not established here", d["caveat"])  # worded as a hypothesis
        self.assertEqual(d["caveatYears"], [d["y"]])
        self.assertTrue(d["caveatShort"])


if __name__ == "__main__":
    unittest.main()
