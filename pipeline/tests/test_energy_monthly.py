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
        """C-025: customs data recorded 7.40, 9.61, 8.76, 8.58 and 9.01 Mt of Kuwaiti crude to Vietnam in 2019 to 2023 (0.54 and 4.73 Mt in 2017 and 2018) and none in 2024 (read from the cache; GE1.10 corrects the first wording of this note)."""
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


# ---------------------------------------------------------------------------------------------------------------- package FE1
# Review GE1: the imports by origin, the labelling of the converted United States LPG figure, the monthly step that must not stop the
# commodity build, and the Kuwait caveat. The expectations are read from raw/eia/INTL.txt and pipeline/cache/baci_flows.csv.gz.


class GapStats(unittest.TestCase):
    """GE1.1 and GE1.2: EIA leaves a month out when it has no figure; neither its file nor its documentation says that it is a zero (it
    publishes zeros), so the atlas shows no figure, and drops no origin for a missing month."""

    def series(self, skip=(), base=10.0, cur=5.0, to="2026-08"):
        v = {f"2025-{m:02d}": base for m in range(1, 13)}
        v.update({f"2026-{m:02d}": cur for m in range(1, int(to[5:]) + 1)})
        for m in skip:
            v.pop(m, None)
        return v

    def test_a_series_without_gaps_has_its_lowest_month_and_its_average(self):
        r, bm = MO.gap_stats(self.series(), "2026-08")
        self.assertEqual(r["b"], 10.0)
        self.assertEqual(r["lo"], {"v": 5.0, "m": "2026-01"})
        self.assertEqual(r["la"], {"v": 5.0, "m": "2026-08"})
        self.assertEqual(r["p"], -50.0)
        self.assertNotIn("miss", r)
        self.assertNotIn("nb", r)

    def test_a_missing_month_of_the_year_prints_no_lowest_month_and_no_zero(self):
        r, bm = MO.gap_stats(self.series(skip=("2026-04", "2026-05")), "2026-08")
        self.assertIsNone(r["lo"])  # no "lowest month" is printed for an origin with months missing in the year
        self.assertEqual(r["miss"], 2)
        self.assertEqual(r["la"], {"v": 5.0, "m": "2026-08"})
        ax = MO.axis("2026-08")
        self.assertIsNone(r["v"][ax.index("2026-04")])  # the series carries no zero for it
        self.assertNotIn(0, [x for x in r["v"] if x is not None])

    def test_a_missing_month_of_the_baseline_year_keeps_the_origin_without_an_average(self):
        r, bm = MO.gap_stats(self.series(skip=("2025-03",)), "2026-08")
        self.assertIsNotNone(r)  # the origin is not dropped
        self.assertIsNone(r["b"])
        self.assertEqual(r["nb"], 11)
        self.assertNotIn("p", r)
        self.assertAlmostEqual(bm, 10.0)  # only the filter reads it

    def test_the_table_month_without_a_figure_is_not_filled_with_an_older_one(self):
        v = self.series(to="2026-03")
        r, _ = MO.gap_stats(v, "2026-08")
        self.assertIsNone(r["la"])  # never an older figure under the header of another month
        self.assertEqual(r["last"], {"v": 5.0, "m": "2026-03"})
        self.assertEqual(r["miss"], 5)
        self.assertNotIn("p", r)

    def test_a_series_with_no_figure_in_the_baseline_year_and_none_since_is_not_a_row(self):
        self.assertEqual(MO.gap_stats({"2019-05": 4.0}, "2026-08"), (None, None))


@unittest.skipUnless(HAS_EIA, "raw/eia/INTL.txt is not on this machine")
class ImportsByOrigin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = load("monthly/crude-oil.json")
        cls.imp = {i["id"]: i for i in cls.f["imports"]["importers"]}

    def row(self, importer, code):
        return next(r for r in self.imp[importer]["rows"] if r["o"] == code)

    def months(self, importer, code):
        i = self.imp[importer]
        r = self.row(importer, code)
        ax = MO.axis(i["to"], len(r["v"]))
        return dict(zip(ax, r["v"]))

    def test_the_united_states_from_libya_is_there_with_eleven_months_of_2025(self):
        r = self.row("USA", "LBY")
        raw = raw_series("INTL.787-3-LBY-TBPD.M")
        self.assertEqual(sum(1 for m in raw if m.startswith("2025")), 11)
        self.assertIsNone(r["b"])
        self.assertEqual(r["nb"], 11)
        self.assertEqual(r["la"]["m"], "2026-08")
        self.assertAlmostEqual(r["la"]["v"], raw["202608"], places=3)

    def test_japan_from_kuwait_has_no_lowest_month_and_two_months_without_a_figure(self):
        r = self.row("JPN", "KWT")
        raw = raw_series("INTL.785-3-KWT-TBPD.M")
        self.assertNotIn("202604", raw)
        self.assertNotIn("202605", raw)
        self.assertIsNone(r["lo"])
        self.assertEqual(r["miss"], 2)
        m = self.months("JPN", "KWT")
        self.assertIsNone(m["2026-04"])
        self.assertIsNone(m["2026-05"])
        self.assertAlmostEqual(r["la"]["v"], raw["202608"], places=3)
        self.assertEqual(r["la"]["m"], self.imp["JPN"]["to"])

    def test_germany_from_kuwait_does_not_show_an_old_month_as_the_latest(self):
        r = self.row("DEU", "KWT")
        self.assertIsNone(r["la"])
        raw = raw_series("INTL.783-3-KWT-TBPD.M")
        last = max(raw)
        self.assertEqual(r["last"]["m"], f"{last[:4]}-{last[4:]}")
        self.assertLess(r["last"]["m"], self.imp["DEU"]["to"])

    def test_no_origin_that_averages_above_one_kb_d_is_dropped(self):
        """Every origin of the file (a group, or a country of the index) whose months of 2025 that have a figure average above 1 kb/d is a row."""
        import json as _json
        pat = re.compile(r'^\{"series_id":"INTL\.(78\d?)-3-([A-Z0-9]+)-TBPD\.M"')
        have = {(i, r["o"]) for i, imp in self.imp.items() for r in imp["rows"]}
        ids = {"78": "OECD", "781": "OEEU", "782": "FRA", "783": "DEU", "784": "ITA", "785": "JPN", "786": "KOR", "787": "USA", "788": "CAN", "789": "GBR"}
        want = set()
        with open(INTL, encoding="utf-8") as f:
            for line in f:
                m = pat.match(line)
                if not m or m.group(1) not in ids:
                    continue
                o = _json.loads(line)
                got = {p: v for p, v in o["data"] if isinstance(v, (int, float)) and p.startswith("2025")}
                if not got:
                    continue
                days = {p: calendar.monthrange(2025, int(p[4:]))[1] for p in got}
                avg = sum(got[p] * days[p] for p in got) / sum(days.values())
                code = m.group(2)
                if avg > 1 and (code in ("PERG", "OPEC") or code in COUNTRY_CODES):
                    want.add((ids[m.group(1)], code))
        self.assertGreater(len(want), 100)
        self.assertEqual(sorted(want - have), [])

    def test_the_validator_rule_is_in_the_data(self):
        """lo is null exactly when a month of the year has no figure; b is null exactly when a month of the baseline year has none."""
        for i in self.imp.values():
            for r in i["rows"]:
                m = dict(zip(MO.axis(i["to"], len(r["v"])), r["v"]))
                miss = [k for k in MO.axis(i["to"])[-int(i["to"][5:]):] if m.get(k) is None]
                self.assertEqual(r["lo"] is None, bool(miss), (i["id"], r["o"]))
                self.assertEqual(r.get("miss", 0), len(miss), (i["id"], r["o"]))
                self.assertEqual(r["b"] is None, "nb" in r, (i["id"], r["o"]))
                self.assertEqual(r["la"] is None, m.get(i["to"]) is None, (i["id"], r["o"]))


def _country_codes():
    with open(os.path.join(ROOT, "data", "countries", "index.json"), encoding="utf-8") as f:
        d = json.load(f)
    return {c["c"] if isinstance(c, dict) else c for c in (d if isinstance(d, list) else d.get("countries", d))}


COUNTRY_CODES = _country_codes() - {"XKS"}


@unittest.skipUnless(HAS_EIA, "raw/eia/INTL.txt is not on this machine")
class LpgConversionIsLabelled(unittest.TestCase):
    """GE1.3: the converted United States figure, and the totals that hold it, say 'Atlas conversion' wherever they are printed (the data side:
    the row, the table, the key figure, the history; the page side is read in the Playwright checks of the package report)."""

    @classmethod
    def setUpClass(cls):
        cls.d = load("lpg.json")
        cls.t = cls.d["consumption"]

    def test_the_row_the_table_and_the_key_figure_are_marked(self):
        usa = next(r for r in self.t["rows"] if r["c"] == "USA")
        self.assertIs(usa["conv"], True)
        self.assertEqual([r["c"] for r in self.t["rows"] if r.get("conv")], ["USA"])
        self.assertEqual(self.t["conv"], "United States and world total")
        self.assertIs(self.t["convWorld"], True)
        k = self.d["summary"]["consumption"]
        self.assertEqual(k["s"], "atlas")  # the page prints 'Atlas conversion' for a figure of source atlas that is not an estimate
        self.assertTrue(k["n"].startswith("Atlas conversion of EIA International Energy Data"))

    def test_the_world_total_is_eias_own_series_in_barrels_per_day_and_the_note_says_what_eias_total_in_tonnes_is(self):
        days = 365
        w_bd = raw_series("INTL.67-2-WORL-TBPD.A")["2025"]
        self.assertAlmostEqual(self.t["world"], w_bd * days / 11.6 / 1000, places=2)  # 347.98
        eia_mt = raw_series("INTL.67-2-WORL-MT.A")["2025"] / 1000
        self.assertIn(f"EIA's own total in tonnes is {eia_mt:,.2f} Mt", self.t["n"])  # 303.66
        self.assertIn("world series in barrels per day", self.t["n"])
        self.assertNotIn("world total as published by EIA (all countries)", self.t["n"])
        self.assertIn(f"EIA's own world total in tonnes is {eia_mt:,.2f} Mt", self.d["summary"]["consumption"]["n"])

    def test_the_history_marks_the_converted_years(self):
        h = load("history/lpg.json")["t"]["consumption"]
        self.assertEqual([h["years"][i] for i in h["conv"]["USA"]], [2021, 2022, 2023, 2024, 2025])
        self.assertEqual([h["years"][i] for i in h["convWorld"]], [2021, 2022, 2023, 2024, 2025])
        self.assertNotIn("conv", {k for k in h["conv"] if k != "USA"})


class LpgWorldTotalRule(unittest.TestCase):
    """GE1.8: the United States is added to EIA's world total only while that total leaves it out (it equals the sum of the other countries)."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(ROOT, "pipeline", "commodities"))
        import build_commodities as B
        cls.B = B

    def eia(self, world, usa_bd=1000.0, world_bd=None, us_mt=None):
        """An Eia object with only the LPG series: the United States at 11.6 barrels per tonne 1980 to 2019, then the year 2022."""
        B = self.B
        e = object.__new__(B.Eia)
        days = lambda y: 366 if y % 4 == 0 else 365  # noqa: E731
        us_bd = {y: usa_bd for y in range(1980, 2020)}
        mt = {"USA": {y: usa_bd * days(y) / 11.6 for y in range(1980, 2020)}, "FRA": {2022: 100000.0}, "DEU": {2022: 200000.0}, "WORL": {2022: world}}
        if us_mt is not None:
            mt["USA"][2022] = us_mt
        us_bd[2022] = usa_bd
        bd = {"USA": us_bd, "WORL": {2022: world_bd} if world_bd else {}}
        e.s = {("67-2", "MT"): mt, ("67-2", "TBPD"): bd}
        e.country_values = lambda key, year: [(c, v[year]) for c, v in e.s[key].items() if c not in ("WORL",) and year in v and v[year] > 0]
        return e

    def test_the_country_is_added_while_the_total_leaves_it_out(self):
        e = self.eia(world=300000.0)  # equals FRA + DEU
        r = e._fill_lpg_us()
        us = 1000.0 * 365 / 11.6
        self.assertEqual(r["world"][2022]["how"], "added")
        self.assertAlmostEqual(e.s[("67-2", "MT")]["WORL"][2022], 300000.0 + us)

    def test_a_corrected_file_is_not_counted_twice(self):
        us = 1000.0 * 365 / 11.6
        e = self.eia(world=300000.0 + us)  # EIA fixed its total: it holds the United States
        r = e._fill_lpg_us()
        self.assertEqual(r["world"][2022]["how"], "kept")
        self.assertTrue(r["world"][2022]["incl"])
        self.assertEqual(e.s[("67-2", "MT")]["WORL"][2022], 300000.0 + us)  # unchanged

    def test_eias_world_in_barrels_per_day_is_taken_when_it_supports_the_total(self):
        us = 1000.0 * 365 / 11.6
        wb = (300000.0 + us) * 11.6 / 365 * 1.002  # within 1%
        e = self.eia(world=300000.0, world_bd=wb)
        r = e._fill_lpg_us()
        self.assertEqual(r["world"][2022]["how"], "bd")
        self.assertAlmostEqual(e.s[("67-2", "MT")]["WORL"][2022], wb * 365 / 11.6)
        e = self.eia(world=300000.0, world_bd=wb * 1.2)  # 20% off: not used
        self.assertEqual(e._fill_lpg_us()["world"][2022]["how"], "added")


class MonthlyStepDoesNotStopTheBuild(unittest.TestCase):
    """GE1.7: a failure of the monthly step keeps the previous monthly files, is said loudly and ends the run with the status that
    update_annual.py records as "build-monthly"; the commodity files are written all the same."""

    def test_write_all_writes_nothing_when_a_series_is_missing(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            old = os.path.join(tmp, "crude-oil.json")
            with open(old, "w", encoding="utf-8") as f:
                f.write('{"previous":true}')
            empty = os.path.join(tmp, "INTL.txt")
            with open(empty, "w", encoding="utf-8") as f:
                f.write('{"series_id":"INTL.1-1-WORL-TBPD.M","name":"x","data":[["202601",1]]}\n')
            with self.assertRaises(KeyError):
                MO.write_all(empty, tmp, lambda code: None)
            with open(old, encoding="utf-8") as f:
                self.assertEqual(f.read(), '{"previous":true}')
            self.assertEqual(sorted(os.listdir(tmp)), ["INTL.txt", "crude-oil.json"])  # no temporary file left

    def test_the_builder_exits_with_the_status_the_annual_job_records(self):
        sys.path.insert(0, os.path.join(ROOT, "pipeline", "annual"))
        import update_annual as UA

        self.assertEqual(UA.MONTHLY_FAILED, 3)
        src = open(os.path.join(ROOT, "pipeline", "commodities", "build_commodities.py"), encoding="utf-8").read()
        self.assertIn("MONTHLY_FAILED = 3", src)
        self.assertIn("sys.exit(main())", src)

    def test_the_annual_job_records_the_monthly_failure_apart_and_keeps_the_commodity_step_successful(self):
        sys.path.insert(0, os.path.join(ROOT, "pipeline", "annual"))
        import update_annual as UA

        calls, mode = [], {"run": None, "pending": False}

        def run(cmd, timeout):
            if mode["run"]:
                raise RuntimeError(mode["run"])

        saved = (UA.run, UA.pending, UA.status.record_failure, UA.status.record_success)
        try:
            UA.run = run
            UA.pending = lambda name: mode["pending"]
            UA.status.record_failure = lambda source, error, previous=None: calls.append(("fail", source, error))
            UA.status.record_success = lambda source, **kw: calls.append(("ok", source))
            mode["run"] = "exit 3: !! MONTHLY SERIES NOT REBUILT (KeyError: ('57-1', 'TBPD'))"
            UA.build_commodities("build_commodities.py")  # returns: the step "build-commodities" is a success
            mode["run"] = None
            UA.build_commodities("build_commodities.py")  # a success is not written while nothing failed before (no needless write of the status file)
            mode["pending"] = True
            UA.build_commodities("build_commodities.py")  # and it ends a series of failures
            mode["run"] = "exit 1: Traceback"
            with self.assertRaises(RuntimeError):  # any other failure is the commodity step's own
                UA.build_commodities("build_commodities.py")
        finally:
            UA.run, UA.pending, UA.status.record_failure, UA.status.record_success = saved
        self.assertEqual(calls, [("fail", "build-monthly", "!! MONTHLY SERIES NOT REBUILT (KeyError: ('57-1', 'TBPD'))"), ("ok", "build-monthly")])

    def test_main_keeps_writing_the_commodity_files_and_returns_the_status(self):
        """B.main() with a monthly step that raises: every commodity file is still written (to a temporary folder here), the monthly files are not
        touched, and main() returns MONTHLY_FAILED."""
        import shutil
        import tempfile

        sys.path.insert(0, os.path.join(ROOT, "pipeline", "commodities"))
        import build_commodities as B

        if not (HAS_EIA and os.path.exists(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))):
            self.skipTest("raw files are not on this machine")
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(os.path.join(DATA, "index.json"), os.path.join(tmp, "index.json"))
            saved = (B.OUT, B.update_sources, B.write_qa, MO.write_all)
            calls = []

            def boom(*a, **k):
                calls.append("monthly")
                raise ValueError("EIA series renamed")
            try:
                B.OUT, B.update_sources, B.write_qa, MO.write_all = tmp, lambda: None, lambda *a, **k: None, boom
                qa_before = len(B.QA_WARN)
                status = B.main()
            finally:
                B.OUT, B.update_sources, B.write_qa, MO.write_all = saved
            self.assertEqual(status, B.MONTHLY_FAILED)
            self.assertEqual(calls, ["monthly"])
            self.assertTrue(os.path.exists(os.path.join(tmp, "crude-oil.json")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "lpg.json")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "monthly")))  # nothing of the monthly step was written
            self.assertTrue(any("monthly series NOT rebuilt" in w for w in B.QA_WARN[qa_before:]))


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz")), "BACI cache is not on this machine")
@unittest.skipUnless(HAS_EIA, "raw/eia/INTL.txt is not on this machine")  # the production side is read from the EIA file
class KuwaitFall(unittest.TestCase):
    """GE1.11: Kuwait's customs crude exports fall to about half their level of the three years before in 2024 while its production in the EIA
    file does not: a registry entry worded as a hypothesis, on the row and (once the lanes are rebuilt) on the lanes of the origin."""

    @classmethod
    def setUpClass(cls):
        import pandas as pd

        sys.path.insert(0, os.path.join(ROOT, "pipeline", "trade"))
        import caveats
        import clean as C

        raw = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        cls.k = raw[(raw["group"] == "crude-oil") & (raw["o"] == "KWT")].groupby("year")["t"].sum() / 1e6
        cls.caveats = caveats
        cls.active = caveats.build(C.clean(raw), [], 2024, psd=None)

    def test_the_entry_is_active_and_worded_as_a_hypothesis(self):
        e = self.active["crude-kwt"]
        self.assertEqual((e["group"], e["o"], e["d"], e["kind"]), ("crude-oil", "KWT", None, "fall"))
        self.assertIn("49.4 Mt", e["text"])
        self.assertIn("Vietnam (9.01 Mt)", e["text"])
        self.assertIn("is a plausible cause; it is not established here.", e["text"])
        self.assertIn("thousand barrels a day in 2024 against", e["text"])  # EIA production of both years
        self.assertEqual(self.caveats.lookup(self.active, "crude-oil", "KWT", "CHN"), "crude-kwt")  # the origin's lanes
        self.assertEqual(self.caveats.lookup(self.active, "crude-oil", "KWT", "VNM"), "crude-kwt-vnm")  # the pair entry still wins

    def test_the_fall_is_in_the_customs_cache_and_not_in_production(self):
        self.assertLess(self.k[2024], 0.6 * self.k.loc[2021:2023].mean() * 1.2)
        self.assertGreater(self.k[2023], 95)  # raw cache: 101.85 Mt in 2023 (the atlas's cleaned figure is 81.05 Mt)
        ser = raw_series("INTL.57-1-KWT-TBPD.A")
        self.assertGreater(ser["2024"], 0.9 * ser["2023"])

    def test_the_entry_does_not_widen_the_estimates_of_the_passages(self):
        """Kind 'fall' is text only: build_freight.unrecorded_through reads 'unrecorded' and 'break'."""
        src = open(os.path.join(ROOT, "pipeline", "freight", "build_freight.py"), encoding="utf-8").read()
        self.assertIn('e["kind"] not in ("unrecorded", "break")', src)

    def test_the_row_of_the_crude_exports_table_carries_it(self):
        d = load("crude-oil.json")
        row = next(r for r in d["exports"]["rows"] if r["c"] == "KWT")
        self.assertIn("is a plausible cause; it is not established here", row["n"])
        self.assertIn("against an average of", row["n"])
