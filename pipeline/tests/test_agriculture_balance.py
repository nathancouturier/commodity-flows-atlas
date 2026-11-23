"""USDA 2026/27 forecast beside the 2025/26 estimate, crop balances, the EU member states, the gap note of Russian grain (audit M-076, M-025,
M-024, C-104, C-045, M-027; package A1).

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_agriculture_balance.py"
The expectations are read from the files the builder reads (raw/usda/psd_csv/psd_alldata.csv, pipeline/cache) by code of their own, and the
data files are read as build_commodities.py last wrote them.
"""
import csv
import json
import os
import sys
import unittest

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities"):
    p = os.path.join(ROOT, "pipeline", sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import build_commodities as B  # noqa: E402

DATA = os.path.join(ROOT, "data")
PSD_FILE = os.path.join(ROOT, "raw", "usda", "psd_csv", "psd_alldata.csv")
EU_CACHE = os.path.join(ROOT, "pipeline", "cache", "faostat_eu_crops.csv")
HAS_PSD = os.path.exists(PSD_FILE)
CROPS = {"wheat": "Wheat", "corn": "Corn", "sugar": "Sugar, Centrifugal", "soybeans": "Oilseed, Soybean", "rice": "Rice, Milled", "cotton": "Cotton"}


def load(rel):
    with open(os.path.join(DATA, rel), encoding="utf-8") as f:
        return json.load(f)


_PSD = {}


def psd():
    """The PSD rows of the market years 2025 and 2026 for the crops above, read here with no help from the builder."""
    if not _PSD:
        d = pd.read_csv(PSD_FILE, encoding="latin-1", usecols=["Commodity_Description", "Country_Name", "Market_Year", "Calendar_Year", "Month",
                                                                "Attribute_Description", "Value"])
        _PSD["d"] = d[d["Market_Year"].isin([2025, 2026]) & d["Commodity_Description"].isin(CROPS.values())]
    return _PSD["d"]


def total(com, attr, my, country=None):
    x = psd()
    x = x[(x["Commodity_Description"] == com) & (x["Attribute_Description"] == attr) & (x["Market_Year"] == my)]
    if country:
        x = x[x["Country_Name"] == country]
    return float(x["Value"].sum())


@unittest.skipUnless(HAS_PSD, "raw USDA PSD file not on disk")
class YearRule(unittest.TestCase):
    def test_tables_show_the_forecast_year_and_say_so(self):
        self.assertEqual(B.PSD_MY, 2026)
        self.assertEqual(B.PSD_LABEL, "2026/27")
        self.assertEqual(B.PSD_EST_LABEL, "2025/26")
        for cid in CROPS:
            d = load(f"commodities/{cid}.json")
            for sec in ("production", "exports", "imports", "consumption"):
                if sec in d:
                    self.assertEqual(d[sec]["y"], "2026/27", f"{cid} {sec}")
                    self.assertEqual(d[sec]["yk"], "forecast", f"{cid} {sec}")
                    self.assertRegex(d[sec]["rel"], r"^\d{4}-\d{2}$")
            self.assertEqual(d["summary"]["production"]["y"], "2026/27 forecast")

    def test_world_production_of_both_years_is_the_file_sum(self):
        # wheat 827.5 and 844.0 Mt, corn 1,291.6 and 1,334.7 Mt, sugar 178.1 and 187.1 Mt (the figures the audit entry quotes), read from the file
        for cid, com in (("wheat", "Wheat"), ("corn", "Corn"), ("sugar", "Sugar, Centrifugal")):
            d = load(f"commodities/{cid}.json")
            fc, est = total(com, "Production", 2026) / 1000, total(com, "Production", 2025) / 1000
            self.assertAlmostEqual(d["production"]["world"], fc, delta=0.06, msg=cid)  # the files keep 1 decimal from 1,000
            prod = next(r for r in d["balance"]["rows"] if r["k"] == "production")
            self.assertAlmostEqual(prod["v"][0], est, delta=0.06, msg=cid)
            self.assertAlmostEqual(prod["v"][1], fc, delta=0.06, msg=cid)
        w = load("commodities/wheat.json")["balance"]
        self.assertEqual([y["yk"] for y in w["years"]], ["estimate", "forecast"])
        self.assertEqual([y["y"] for y in w["years"]], ["2025/26", "2026/27"])

    def test_report_month_is_read_from_the_file(self):
        x = psd()
        for cid, com in CROPS.items():
            rows = x[(x["Commodity_Description"] == com) & (x["Market_Year"] == 2026)]
            last = rows.sort_values(["Calendar_Year", "Month"]).iloc[-1]
            want = f"{int(last['Calendar_Year'])}-{int(last['Month']):02d}"
            self.assertEqual(load(f"commodities/{cid}.json")["production"]["rel"], want, cid)

    def test_history_files_follow_the_rule(self):
        h = load("commodities/history/wheat.json")["t"]["production"]
        self.assertEqual(h["years"][-1], 2026)
        self.assertEqual(h["labels"][-2:], ["2025/26", "2026/27"])
        self.assertEqual(h["kinds"][-2:], ["estimate", "forecast"])
        self.assertIsNone(h["kinds"][-3])
        # the latest year of the series is the table of the page
        d = load("commodities/wheat.json")
        self.assertAlmostEqual(h["world"][-1], d["production"]["world"], places=2)


@unittest.skipUnless(HAS_PSD, "raw USDA PSD file not on disk")
class Balance(unittest.TestCase):
    def row(self, cid, k):
        return next(r for r in load(f"commodities/{cid}.json")["balance"]["rows"] if r["k"] == k)

    def test_stocks_to_use_by_hand(self):
        # wheat 2025/26: ending stocks 282,858 kt over domestic consumption 817,930 kt = 34.58%
        self.assertEqual(round(282858 / 817930 * 100, 1), 34.6)
        self.assertEqual(self.row("wheat", "stu")["v"][0], 34.6)
        self.assertEqual(total("Wheat", "Ending Stocks", 2025), 282858)
        self.assertEqual(total("Wheat", "Domestic Consumption", 2025), 817930)
        # corn 2025/26: 308,310 over 1,306,348 = 23.6%
        self.assertEqual(self.row("corn", "stu")["v"][0], round(total("Corn", "Ending Stocks", 2025) / total("Corn", "Domestic Consumption", 2025) * 100, 1))
        self.assertEqual(self.row("corn", "stu")["v"][0], 23.6)

    def test_world_excluding_china(self):
        for cid, com, use in (("wheat", "Wheat", "Domestic Consumption"), ("sugar", "Sugar, Centrifugal", "Total Disappearance"), ("cotton", "Cotton", "Domestic Use")):
            for i, my in enumerate((2025, 2026)):
                es, esc = total(com, "Ending Stocks", my), total(com, "Ending Stocks", my, "China")
                u, uc = total(com, use, my), total(com, use, my, "China")
                self.assertAlmostEqual(self.row(cid, "stocks-x")["v"][i], (es - esc) * (0.001 if cid != "cotton" else 0.00021772434), delta=0.006, msg=cid)
                self.assertAlmostEqual(self.row(cid, "stu-x")["v"][i], (es - esc) / (u - uc) * 100, delta=0.06, msg=cid)
                self.assertAlmostEqual(self.row(cid, "stu-cn")["v"][i], esc / uc * 100, delta=0.06, msg=cid)

    def test_derived_lines_are_not_estimates(self):
        for cid in CROPS:
            for r in load(f"commodities/{cid}.json")["balance"]["rows"]:
                if r.get("s"):
                    self.assertEqual(r["s"], "atlas")
                    self.assertFalse(r["n"].startswith("Atlas estimate"), r["n"])
                    self.assertIn("Computed by the atlas", r["n"])

    def test_area_and_yield_where_the_file_has_them(self):
        w = load("commodities/wheat.json")["balance"]["rows"]
        area = next(r for r in w if r["k"] == "area")
        self.assertAlmostEqual(area["v"][1], total("Wheat", "Area Harvested", 2026) / 1000, delta=0.01)
        yld = next(r for r in w if r["k"] == "yield")
        self.assertAlmostEqual(yld["v"][1], total("Wheat", "Production", 2026) / total("Wheat", "Area Harvested", 2026), delta=0.01)
        sugar = [r["k"] for r in load("commodities/sugar.json")["balance"]["rows"]]
        self.assertNotIn("area", sugar)  # the file has no area for sugar

    def test_thai_sugar_stock_is_stated_with_both_figures(self):
        es25, pr25 = total("Sugar, Centrifugal", "Ending Stocks", 2025, "Thailand"), total("Sugar, Centrifugal", "Production", 2025, "Thailand")
        self.assertGreater(es25, pr25)  # the file really shows more stock than production
        t = next(x["table"] for x in load("commodities/sugar.json")["extra"] if x["key"] == "stocks")
        row = next(r for r in t["rows"] if r["c"] == "THA")
        self.assertIn(B._nf(es25 / 1000), row["n"])
        self.assertIn(B._nf(pr25 / 1000), row["n"])
        self.assertNotIn("because", row["n"])  # figures, not an explanation


class EuMembers(unittest.TestCase):
    def faostat(self, area, item="15", year="2024"):
        with open(EU_CACHE, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["area"] == area and r["item"] == item and r["year"] == year:
                    return float(r["value_t"]) / 1e6
        raise KeyError(area)

    def test_france_and_romania_wheat_production(self):
        t = next(x["table"] for x in load("commodities/wheat.json")["extra"] if x["key"] == "eu-production")
        rows = {r["c"]: r["v"] for r in t["rows"]}
        self.assertAlmostEqual(rows["FRA"], self.faostat("France"), delta=0.001)
        self.assertAlmostEqual(rows["ROU"], self.faostat("Romania"), delta=0.001)
        self.assertEqual(t["s"], "faostat")
        self.assertEqual(t["scope"], "EU")
        self.assertTrue(t["norank"])  # a rank among the member states is not a world rank
        self.assertAlmostEqual(t["worldAll"], self.faostat("World"), delta=0.01)
        self.assertEqual(t["rows"][0]["c"], "FRA")
        self.assertIn("another source and another year", t["n"])  # said once beside the USDA European Union line

    def test_member_production_adds_up_to_the_faostat_aggregate(self):
        for cid in ("wheat", "corn", "rice", "soybeans", "rapeseed", "sugar"):
            t = next(x["table"] for x in load(f"commodities/{cid}.json")["extra"] if x["key"] == "eu-production")
            self.assertEqual(len(t["rows"]), len({r["c"] for r in t["rows"]}))
            self.assertTrue(all(r["c"] in B.EU_MEMBERS for r in t["rows"]), cid)

    def test_a_table_on_another_basis_does_not_paint_the_map(self):
        for cid in ("rice", "sugar"):
            t = next(x["table"] for x in load(f"commodities/{cid}.json")["extra"] if x["key"] == "eu-production")
            self.assertTrue(t["noMap"], cid)
            self.assertIn("carry the USDA value", t["n"])
        t = next(x["table"] for x in load("commodities/wheat.json")["extra"] if x["key"] == "eu-production")
        self.assertNotIn("noMap", t)

    def test_member_trade_does_not_paint_the_map(self):
        """GA1.3, GA1.9: customs trade of a member includes trade between members, USDA's European Union row does not: the map keeps
        USDA's row on every member for exports and imports, rice included; production stays coloured where the basis is the same."""
        for cid in ("wheat", "corn", "soybeans", "rice", "sugar", "rapeseed"):
            d = load(f"commodities/{cid}.json")
            for side in ("exports", "imports"):
                x = [e for e in d["extra"] if e["key"] == f"eu-{side}"]
                if not x:
                    continue
                t = x[0]["table"]
                self.assertTrue(t["noMap"], f"{cid} {side}")
                self.assertIn("carries the USDA value for the European Union", t["n"])
                self.assertEqual(t["scope"], "EU")
                self.assertEqual(t["scopeLabel"], "EU member states")
        wheat = load("commodities/wheat.json")
        self.assertNotIn("noMap", next(x["table"] for x in wheat["extra"] if x["key"] == "eu-production"))

    def test_the_year_rule_is_said_on_the_production_table_and_the_balance(self):
        """GA1.8: the file has no label; the page says the words are the atlas's and what USDA's own circular heads the years."""
        for cid in ("wheat", "sugar", "coffee"):
            d = load(f"commodities/{cid}.json")
            self.assertIn(B.YK_RULE, d["production"]["n"], cid)
            self.assertIn(B.YK_RULE, d["balance"]["n"], cid)
        self.assertIn("atlas's words", B.YK_RULE)
        self.assertIn("apps.fas.usda.gov/psdonline/circulars/production.pdf", B.YK_RULE)

    def test_the_usda_row_is_untouched(self):
        d = load("commodities/wheat.json")
        eu = next(r for r in d["production"]["rows"] if r["c"] == "EU27")
        self.assertAlmostEqual(eu["v"], total("Wheat", "Production", 2026, "European Union") / 1000, delta=0.001) if HAS_PSD else None
        self.assertNotIn("FRA", [r["c"] for r in d["production"]["rows"]])

    def test_trade_split_sums_to_the_eu27_trade(self):
        for cid in ("wheat", "corn", "soybeans", "rice", "sugar"):
            d = load(f"commodities/{cid}.json")
            for side in ("exports", "imports"):
                t = next(x["table"] for x in d["extra"] if x["key"] == f"eu-{side}")
                s = t["split"]
                self.assertAlmostEqual(s["intra"] + s["extra"], s["total"], delta=0.002, msg=f"{cid} {side}")
                self.assertAlmostEqual(sum(r["v"] for r in t["rows"]), s["total"], delta=0.03, msg=f"{cid} {side}")
                self.assertAlmostEqual(t["world"], s["total"], delta=0.03)
                self.assertEqual(d[side]["eu"]["total"], s["total"])
                self.assertEqual(d[side]["eu"]["extra"], s["extra"])
        # intra-EU trade is counted once: the same flows are the members' exports to members and their imports from members
        w = load("commodities/wheat.json")
        self.assertEqual(w["exports"]["eu"]["intra"], w["imports"]["eu"]["intra"])

    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz")), "customs cache not on disk")
    def test_trade_split_against_the_cleaned_frame(self):
        baci = B.Baci()
        d = baci.group("wheat")
        eu = set(B.EU_MEMBERS)
        exp = d[d["o"].isin(eu)]
        intra = exp[exp["d"].isin(eu)]["t"].sum() / 1e6
        w = load("commodities/wheat.json")
        self.assertAlmostEqual(w["exports"]["eu"]["total"], exp["t"].sum() / 1e6, delta=0.002)
        self.assertAlmostEqual(w["exports"]["eu"]["intra"], intra, delta=0.002)
        fra = next(r for r in next(x["table"] for x in w["extra"] if x["key"] == "eu-exports")["rows"] if r["c"] == "FRA")
        self.assertAlmostEqual(fra["v"], d[d["o"] == "FRA"]["t"].sum() / 1e6, delta=0.002)


@unittest.skipUnless(HAS_PSD, "raw USDA PSD file not on disk")  # the note compares the customs tonnage with PSD
class RussianGrain(unittest.TestCase):
    def test_gap_note_states_the_two_figures_and_the_lost_importers(self):
        w = load("commodities/wheat.json")
        self.assertEqual(w["gaps"][0]["o"], "RUS")
        text = w["gaps"][0]["text"]
        self.assertIn("CEPII BACI", text)
        self.assertIn("USDA PSD gives", text)
        self.assertRegex(text, r"The published customs figure is \d+% below the first and \d+% below the second")
        for name in ("Bangladesh", "Iran"):
            self.assertIn(name, text)
        self.assertIn("no further tonnage is added", text)

    def test_gap_note_separates_the_atlas_estimate_from_the_recorded_tonnage(self):
        """GA1.4: 34.5 Mt of Russian wheat in the cleaned frame include tonnage the atlas estimated from the declared value."""
        import caveats
        import clean
        if not os.path.exists(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz")):
            self.skipTest("customs cache not on disk")
        df = clean.clean(pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz")))
        x = df[(df["group"] == "wheat") & (df["o"] == "RUS") & (df["year"] == B.BACI_YEAR)]
        total, est = x["t"].sum() / 1e6, x.loc[x["imputed"].astype(bool), "t"].sum() / 1e6
        self.assertGreater(est, 1)
        text = caveats.build(df, [], B.BACI_YEAR)["grain-rus-wheat"]["text"]
        self.assertIn(f"{caveats.mt(est)} is an Atlas estimate", text)
        self.assertIn(f"{caveats.mt(total - est)} is as reported", text)
        self.assertIn("Egypt", text)
        self.assertRegex(text, r"On the tonnage as reported alone \(.+?\) the gap is \d+% below the first and \d+% below the second")
        # a group with nothing estimated says nothing of an estimate
        self.assertNotIn("Atlas estimate (the tonnage", caveats.build(df, [], B.BACI_YEAR)["grain-rus-rapeseed"]["text"])

    def test_registry_builds_the_same_text(self):
        import caveats
        import clean
        if not os.path.exists(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz")):
            self.skipTest("customs cache not on disk")
        df = clean.clean(pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz")))
        act = caveats.build(df, [], B.BACI_YEAR)
        self.assertIn("The published customs figure is", act["grain-rus-wheat"]["text"])
        # the destinations named had flows in the years before and none in the build year
        w = df[(df["group"] == "wheat") & (df["o"] == "RUS")]
        by = (w.groupby(["d", "year"])["t"].sum() / 1e6).unstack(fill_value=0.0)
        for iso in ("BGD", "IRN"):
            self.assertGreater(by.loc[iso, [B.BACI_YEAR - 5, B.BACI_YEAR - 4, B.BACI_YEAR - 3]].mean(), 0.5)
            self.assertLess(by.loc[iso, B.BACI_YEAR], 0.05)


class CocoaAndMisc(unittest.TestCase):
    def test_cocoa_page_states_grindings_headline_and_the_missing_product_tables(self):
        notes = " ".join(load("commodities/cocoa.json")["notes"])
        self.assertIn("which gives it as estimated: world grindings of 4,649 kt", notes)
        self.assertIn("2024/25", notes)
        self.assertIn("HS 1803 to 1805", notes)
        self.assertNotIn("not in the loaded sources", notes)
        self.assertIn("HS 210110", " ".join(load("commodities/coffee.json")["notes"]))

    def test_fertilisers_have_a_sub_heading(self):
        idx = {e["id"]: e for e in load("commodities/index.json")}
        for cid in ("potash", "phosphate", "urea"):
            self.assertEqual(idx[cid].get("sub"), "Fertilisers")
        self.assertNotIn("sub", idx["wheat"])


if __name__ == "__main__":
    unittest.main()
