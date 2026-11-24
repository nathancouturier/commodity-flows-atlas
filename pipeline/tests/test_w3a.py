"""Tests of the four corrections of the seventh release that rest on new files: tin, LPG, steel and LNG.

A1  LPG from the United States to Mexico: the customs tonnage of 2021 to 2024 is a volume read as tonnes; clean() replaces it by the volume of the
    United States' own statistics times the density (rule 10), and the pair is cut by mode in 2024 (modes.KNOWN_SPLIT, build_lanes.split_known)
A2  tin ores and concentrates: the flow Myanmar to China is added from China's import declaration (UN Comtrade, rule 11), and the tin page prints the declaration
A3  steel: the later figure of the World Steel Association with its edition, the terms recorded in the registry, the pig iron page
A4  LNG: the exports of Australia and the United States in their own statistics beside the customs figures, the editions of the industry totals

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The tests of the caches and of the data files need neither raw/ nor a build; the tests of the data files read the files as the builders last wrote them.
"""
import copy
import json
import os
import sys
import unittest

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import aus_req_lng  # noqa: E402
import clean as C  # noqa: E402
import comtrade_tin  # noqa: E402
import modes as MD  # noqa: E402
import us_lpg  # noqa: E402

DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, "pipeline", "cache")


def load(*parts):
    with open(os.path.join(DATA, *parts), encoding="utf-8") as f:
        return json.load(f)


def baci(group):
    df = pd.read_csv(os.path.join(CACHE, "baci_flows.csv.gz"))
    return df[df["group"] == group]


def row(df, o, d, y):
    r = df[(df["o"] == o) & (df["d"] == d) & (df["year"] == y)]
    return r.iloc[0] if len(r) else None


class A1Cache(unittest.TestCase):
    def test_the_census_file_gives_the_densities_and_the_pair(self):
        c = us_lpg.load()["census"]
        self.assertEqual(c["year"], 2024)
        self.assertAlmostEqual(c["density_kg_m3"]["2711120010"], 505.5, delta=1.0)  # propane, from the file's vessel rows
        self.assertAlmostEqual(c["density_kg_m3"]["2711130000"], 582.0, delta=1.5)  # butanes
        mex = c["pairs"]["MEX"]
        self.assertGreater(sum(mex["qty_m3"].values()), 10.4e6)
        self.assertAlmostEqual(mex["total_t"] / 1e6, 5.28, places=2)
        self.assertAlmostEqual(mex["vessel_t"] / mex["total_t"], 0.72, places=2)
        for iso in ("JPN", "CHN", "KOR"):  # the three buyers of the note of the page: all by vessel
            self.assertGreater(c["pairs"][iso]["vessel_t"], 5e6)

    def test_the_eia_series_agree_with_the_census_file(self):
        """EIA's exports to Mexico in 2024 (176 thousand barrels a day of propane, in the series read) are the volume of the Census file to 1%."""
        e = us_lpg.load()["eia"]
        self.assertEqual(e["series"]["propane"]["MEX"]["2024"], 176.0)
        self.assertEqual(e["series"]["propane"]["MEX"]["2023"], 168.0)
        census = sum(us_lpg.load()["census"]["pairs"]["MEX"]["qty_m3"].values()) / 1e3  # thousand m3
        self.assertAlmostEqual(us_lpg.volume_m3("MEX", 2024)["propane"] / census, 1.0, delta=0.03)

    def test_the_estimate_of_2024_is_the_census_file_and_the_other_years_are_eia(self):
        self.assertEqual(us_lpg.estimate("MEX", 2024)["source"], "census")
        e = us_lpg.estimate("MEX", 2023)
        self.assertEqual(e["source"], "eia")
        self.assertAlmostEqual(e["t"] / 1e6, 5.06, places=2)
        self.assertIsNone(us_lpg.estimate("MEX", 2003))  # the series start in 2004


class A1Clean(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = baci("lpg")
        cls.cl = C.clean(cls.raw)

    def test_the_four_years_are_replaced(self):
        for y, mt in ((2021, 4.94), (2022, 5.31), (2023, 5.06), (2024, 5.28)):
            r = row(self.cl, "USA", "MEX", y)
            self.assertEqual(r.flag, "est-volume", y)
            self.assertTrue(r.imputed)
            self.assertAlmostEqual(r.t / 1e6, mt, places=2, msg=y)
            self.assertGreater(r.t0, 1.4 * r.t)  # the customs tonnage is the volume: 1.5 to 2 times it
            self.assertTrue(r.enote.startswith("Atlas estimate: CEPII BACI reports"), y)
            self.assertIn("not established here", r.enote)  # a cause is worded as a hypothesis

    def test_the_years_before_are_as_reported(self):
        for y in range(2002, 2021):
            r = row(self.cl, "USA", "MEX", y)
            self.assertEqual(r.t, r.t0, y)
            self.assertNotIn("est-volume", r.flag)

    def test_the_corrected_unit_value_is_in_the_range_of_the_group(self):
        """USD per tonne of the pair against the group's median: 0.39 to 0.56 as reported, 0.6 to 1.0 once corrected, as in 2017 to 2020."""
        for y in (2021, 2022, 2023, 2024):
            r = row(self.cl, "USA", "MEX", y)
            self.assertLess(r.usd * 1000 / r.t0 / (r.uv * 1000), 0.6)
            self.assertGreater(r.usd * 1000 / r.t / (r.uv * 1000), 0.6)

    def test_canada_is_checked_and_left_as_reported(self):
        self.assertTrue((self.cl[(self.cl["o"] == "USA") & (self.cl["d"] == "CAN")]["flag"] != "est-volume").all())
        self.assertEqual(row(self.cl, "USA", "CAN", 2024).t, 523304.0)

    def test_no_other_row_of_the_group_changes(self):
        a = self.cl[~((self.cl["o"] == "USA") & (self.cl["d"] == "MEX") & (self.cl["year"] >= 2021))]
        self.assertTrue((a["t"] == a["t0"])[~a["imputed"]].all())
        self.assertEqual(int((self.cl["flag"] == "est-volume").sum()), 4)

    def test_without_the_table_the_rows_are_as_reported(self):
        keep = dict(us_lpg.CORRECTED)
        us_lpg.CORRECTED.clear()
        try:
            r = row(C.clean(self.raw), "USA", "MEX", 2023)
        finally:
            us_lpg.CORRECTED.update(keep)
        self.assertEqual(r.t, 9742085.0)
        self.assertFalse(r.imputed)


class A1Mode(unittest.TestCase):
    def test_the_split_is_known_for_2024_only(self):
        self.assertAlmostEqual(MD.known_split("USA", "MEX", "lpg", 2024)[0], 0.72, places=2)
        self.assertIsNone(MD.known_split("USA", "MEX", "lpg", 2023))
        self.assertIsNone(MD.known_split("MEX", "USA", "lpg", 2024))
        self.assertIsNone(MD.known_split("USA", "CAN", "lpg", 2024))
        self.assertEqual(MD.mode_of("USA", "MEX", "lpg", 2024).kind, "mixed")
        self.assertIsNone(MD.mode_of("USA", "MEX", "lpg", 2023).share)
        self.assertAlmostEqual(MD.mode_of("USA", "MEX", "lpg", 2024).share, 0.72, places=2)

    def test_split_known_cuts_the_pair_in_two_rows_that_add_up(self):
        import build_lanes as BL
        df = pd.DataFrame({"year": [2023, 2024, 2024], "group": ["lpg"] * 3, "o": ["USA", "USA", "USA"], "d": ["MEX", "MEX", "CAN"],
                           "t": [5.0e6, 5.28e6, 3.5e5], "usd": [2.5e6, 2.35e6, 1.7e5], "mode": ["mixed", "mixed", "land"]})
        out = BL.split_known(df)
        x = out[(out["year"] == 2024) & (out["d"] == "MEX")]
        self.assertEqual(sorted(x["split"]), ["rest", "sea"])
        self.assertEqual(set(x["mode"]), {"sea", "land"})
        self.assertAlmostEqual(x["t"].sum(), 5.28e6)
        self.assertAlmostEqual(x["usd"].sum(), 2.35e6)
        self.assertAlmostEqual(float(x[x["split"] == "sea"]["t"].iloc[0]) / 5.28e6, MD.known_split("USA", "MEX", "lpg", 2024)[0])
        self.assertEqual(out[(out["year"] == 2023)]["mode"].iloc[0], "mixed")  # the other years of the pair are untouched
        self.assertEqual(out[(out["d"] == "CAN")]["split"].iloc[0], "")
        self.assertAlmostEqual(out["t"].sum(), df["t"].sum())


class A1Data(unittest.TestCase):
    def test_the_lane_is_a_sea_lane_with_the_share_by_sea(self):
        lanes = [ln for ln in load("freight", "lanes", "lpg.json")["lanes"] if ln["id"] == "lpg:USA-MEX"]
        self.assertEqual(len(lanes), 1)
        ln = lanes[0]
        self.assertNotEqual(ln.get("mode"), "mixed")
        self.assertAlmostEqual(ln["flow"]["v"], 3.81, places=2)
        self.assertIn("72% of the pair's 5.28 Mt in all modes went by sea", ln["flow"]["n"])
        self.assertEqual(ln["hist"][-1], 5.284)  # the history is the customs total for all modes, as in the years before
        self.assertAlmostEqual(ln["hist"][-2], 5.063, places=3)
        self.assertGreater(ln["share"], 0.02)

    def test_the_pairs_file_has_one_row_for_the_part_by_sea_and_lists_the_rest(self):
        doc = load("freight", "pairs", "lpg.json")
        rows = [r for r in doc["rows"] if r[0] == "USA" and r[1] == "MEX"]
        self.assertEqual([(r[2], r[3]) for r in rows], [(3810, 0)])  # one row per pair, the part by sea, mode sea
        self.assertEqual(doc["rest"], [["USA", "MEX", 1473]])  # the overland part: the country pages count it as land
        self.assertAlmostEqual(3810 + 1473, 5284, delta=2)

    def test_the_world_total_and_the_seaborne_total_follow(self):
        lf = load("freight", "lanes", "lpg.json")
        self.assertAlmostEqual(lf["world"][-1], 140.76, places=1)  # was 144.81 with the customs tonnage of the pair
        self.assertGreater(lf["seaborne"][-1], 129.0)
        page = load("commodities", "lpg.json")
        text = " ".join(page["notes"])
        for s in ("United States to Mexico: 2021 7.44 Mt in CEPII BACI, 4.94 Mt here", "2024 9.33 Mt in CEPII BACI, 5.28 Mt here",
                  "United States to Canada: checked and not corrected", "United States to Japan, China and South Korea"):
            self.assertIn(s, text)
        f = [f for f in page["flows"] if f["o"] == "USA" and f["d"] == "MEX"][0]
        self.assertIn("72% of the pair's 5.28 Mt", f["n"])
        self.assertNotIn("estimated from value", f["n"])  # the estimate is from a volume, not from the declared value


class A2Added(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = baci("tin-ore")
        cls.cl = C.clean(cls.raw)

    def test_the_cache_holds_what_the_page_prints(self):
        d = comtrade_tin.load()
        self.assertEqual(d["source"], "UN Comtrade")
        ys = comtrade_tin.years()
        self.assertEqual(ys, list(range(ys[0], 2025)))  # no hole
        for y in ys:
            x = d["years"][str(y)]
            self.assertEqual(len(x["top"]), 5)
            self.assertEqual(x["top"][0]["c"], "MMR")  # the first origin in every year
            self.assertLessEqual(x["myanmar"]["t"], x["world"]["t"])
        m = comtrade_tin.declared(2024)
        self.assertAlmostEqual(m["t"], 76459.38, places=1)
        self.assertAlmostEqual(d["years"]["2024"]["world"]["t"], 158490.691, places=1)
        self.assertTrue(d["years"]["2024"]["world"]["est"])  # the flags the answer carries
        self.assertIn("2016", d["no_net_weight"])  # an answer without net weight is not used
        self.assertNotIn("2016", d["years"])

    def test_the_flow_is_added_in_every_year_of_the_cache(self):
        for y in comtrade_tin.years():
            r = row(self.cl, "MMR", "CHN", y)
            self.assertEqual(r.flag, "added", y)
            self.assertFalse(r.imputed)  # a declared figure, not an estimate
            self.assertAlmostEqual(r.t, comtrade_tin.declared(y)["t"], places=2)
            self.assertIn("UN Comtrade", r.enote)
            self.assertIn("not in CEPII BACI" if row(self.raw, "MMR", "CHN", y) is None else "CEPII BACI has", r.enote)
        self.assertIn("161 t", row(self.cl, "MMR", "CHN", 2023).enote)  # the one year in which the customs file has a row, replaced

    def test_the_years_before_the_cache_are_as_reported(self):
        y0 = comtrade_tin.years()[0]
        before = self.cl[(self.cl["o"] == "MMR") & (self.cl["d"] == "CHN") & (self.cl["year"] < y0)]
        self.assertTrue((before["flag"] != "added").all())

    def test_nothing_else_of_the_group_changes(self):
        keep = dict(comtrade_tin.ADDED_FLOWS)
        comtrade_tin.ADDED_FLOWS.clear()
        try:
            base = C.clean(self.raw)
        finally:
            comtrade_tin.ADDED_FLOWS.update(keep)

        def is_pair(x):
            return (x["o"] == "MMR") & (x["d"] == "CHN") & x["year"].isin(comtrade_tin.years())
        a, b = self.cl[~is_pair(self.cl)], base[~is_pair(base)]
        self.assertEqual(len(a), len(b))
        self.assertAlmostEqual(float(a["t"].sum()), float(b["t"].sum()), delta=1.0)
        self.assertEqual(int((self.cl["flag"] == "added").sum()), len(comtrade_tin.years()))
        # the world total of 2024 gains the declared tonnage of the pair, which the customs file does not have that year
        gain = self.cl[self.cl["year"] == 2024]["t"].sum() - base[base["year"] == 2024]["t"].sum()
        self.assertAlmostEqual(float(gain), comtrade_tin.declared(2024)["t"], delta=1.0)

    def test_a_row_of_the_customs_file_above_a_tenth_is_kept(self):
        keep = copy.deepcopy(comtrade_tin._DOC)
        try:
            comtrade_tin.load()["years"]["2024"]["myanmar"]["t"] = 100.0  # the customs file would hold 71 t of 100: in line
            rows = pd.DataFrame({"year": [2024, 2024], "group": ["tin-ore"] * 2, "o": ["MMR", "AUS"], "d": ["CHN", "CHN"], "t": [90.0, 9000.0], "usd": [800.0, 150000.0]})
            out = C.clean(rows)
            self.assertEqual(row(out, "MMR", "CHN", 2024).t, 90.0)
        finally:
            comtrade_tin._DOC.clear()
            comtrade_tin._DOC.update(keep)

    def test_the_pair_moves_overland(self):
        self.assertEqual(MD.mode_of("MMR", "CHN", "tin-ore", 2024).kind, "land")

    def test_the_page_prints_the_declaration(self):
        tin = load("commodities", "tin.json")
        x = {e["key"]: e for e in tin["extra"]}["tin-china-declared"]
        self.assertEqual(x["title"], "China's declared imports of tin ores and concentrates by origin (UN Comtrade)")
        t = x["table"]
        self.assertEqual(t["s"], "comtrade")
        self.assertEqual(t["rows"][0]["c"], "MMR")
        self.assertAlmostEqual(t["world"], 158.49, places=2)
        self.assertIn("Source: UN Comtrade", t["n"])
        text = " ".join(tin["notes"])
        self.assertIn("China declares 76.5 kt from Myanmar in 2024", text)
        self.assertNotIn("needs an API key", " ".join(tin["discrepancies"]))
        self.assertFalse([e for e in tin["discrepancies"] if "SMM" in e])  # the trade publication's figures are replaced by the declaration
        hist = load("commodities", "history", "tin.json")["t"]["tin-china-declared"]
        self.assertEqual(hist["years"][-1], 2024)
        self.assertEqual(hist["c"]["MMR"][-1], 76.459)
        self.assertEqual(hist["world"][-1], 158.49)

    def test_the_country_profiles_do_not_take_the_origins_of_chinas_imports_for_exporters(self):
        prof = load("countries", "profiles.json") if os.path.exists(os.path.join(DATA, "countries", "profiles.json")) else None
        if prof is None:
            self.skipTest("no profiles file")
        mm = prof.get("MMR") or {}
        self.assertFalse([e for e in (mm.get("imports") or []) if e.get("k") == "tin" and e.get("s") == "comtrade"])


class A3Steel(unittest.TestCase):
    def test_the_later_figure_is_cited_with_its_edition(self):
        steel = load("commodities", "steel.json")
        text = " ".join(steel["discrepancies"])
        self.assertIn("1,848.9 Mt", text)
        self.assertIn("World Steel in Figures 2026", text)
        self.assertIn("data finalised 8 June 2026", text)
        self.assertIn("https://worldsteel.org/data/world-steel-in-figures/world-steel-in-figures-2026/", text)
        self.assertIn("country table is not reproduced, because its terms of use do not allow it", text)
        self.assertIn("1,848.9 Mt", steel["summary"]["production"]["n"])
        self.assertNotIn("1,849.4 Mt in 2025;", steel["summary"]["production"]["n"])

    def test_the_registry_records_the_clause(self):
        w = {s["id"]: s for s in load("sources.json")}["worldsteel"]
        self.assertIn("without the prior written consent", w["licence"])
        self.assertIn("cannot be shared with a third party", w["licence"])
        self.assertIn("world-steel-in-figures-2026", w["url"])

    def test_pig_iron_has_its_production_table_and_says_why_not_dri(self):
        pig = load("commodities", "pig-iron.json")
        p = pig["production"]
        self.assertEqual((p["y"], p["u"], p["s"]), (2025, "Mt", "usgs-mcs"))
        self.assertEqual(len(p["rows"]), 11)  # the 11 countries that USGS names (the page draws the first ten and lists Iran after them)
        self.assertEqual(p["other"], 61.0)  # the "other countries" line is kept
        self.assertAlmostEqual(p["world"], sum(r["v"] for r in p["rows"]) + p["other"], places=1)  # the shares are on the sum of the lines
        text = " ".join(pig["notes"])
        self.assertIn("direct-reduced iron by country has no source that the atlas may reproduce", text)
        self.assertIn("do not allow its tables to be reproduced without written consent", text)


class A4Lng(unittest.TestCase):
    def test_the_workbook_cache(self):
        a = aus_req_lng.load()
        self.assertEqual((a["year"], a["unit"], a["licence"]), (2024, "Mt", "CC BY 4.0"))
        self.assertAlmostEqual(a["total"], 81.2415, places=3)
        self.assertEqual({k: round(v, 2) for k, v in a["markets"].items()},
                         {"CHN": 26.74, "JPN": 25.52, "KOR": 11.57, "TWN": 8.07, "IND": 0.12})
        self.assertEqual(a["attribution"], "Department of Industry, Science, and Resources, Commonwealth of Australia Resources and Energy Quarterly, December 2025.")
        self.assertIn("estimates", a["total_note"])

    def test_the_tables_of_the_page(self):
        lng = load("commodities", "lng.json")
        ex = {e["key"]: e for e in lng["extra"]}
        own = ex["lng-own-statistics"]["table"]
        rows = {r["c"]: r for r in own["rows"]}
        self.assertEqual(round(rows["AUS"]["v"], 1), 81.2)
        self.assertEqual(round(rows["USA"]["v"], 1), 90.9)  # EIA's 4,367 bcf at 48.03 bcf per Mt
        self.assertTrue(rows["USA"]["conv"])  # the atlas's conversion, marked
        self.assertIn("Customs data (CEPII BACI): 78.7 Mt", rows["AUS"]["n"])
        self.assertIn("Customs data (CEPII BACI): 73.3 Mt", rows["USA"]["n"])
        self.assertTrue(own["norank"])
        self.assertIn("not a ranking", own["n"])
        self.assertIn("no open source for the other exporters", own["n"])
        by = ex["lng-australia-markets"]["table"]
        self.assertEqual([r["c"] for r in by["rows"]], ["CHN", "JPN", "KOR", "TWN", "IND"])
        self.assertEqual(by["s"], "disr-req")
        self.assertIn("Attribution: Department of Industry, Science, and Resources", by["n"])
        self.assertEqual(round(lng["exports"]["world"], 2), 371.32)  # the customs tables are as they were

    def test_the_industry_totals_are_the_latest_editions(self):
        lng = load("commodities", "lng.json")
        head = lng["discrepancies"][0]
        self.assertIn("World LNG Report 2026 edition, https://igu.org/igu-reports/2026-world-lng-report): 437 Mt in 2025", head)
        self.assertIn("428 Mt in 2025 and 406 Mt in 2024", head)
        self.assertNotIn("411.24", head)

    def test_the_registry_records_the_terms_and_the_new_sources(self):
        src = {s["id"]: s for s in load("sources.json")}
        self.assertNotIn("igu-lng-report-2025", src)
        self.assertIn("without the prior permission of the copyright owner", src["igu-lng-report-2026"]["licence"])
        self.assertIn("Reproduction of the contents of this publication in any manner whatsoever is prohibited", src["giignl-2026"]["licence"])
        self.assertIn("CC BY 4.0" if "CC BY 4.0" in src["disr-req"]["licence"] else "Creative Commons Attribution 4.0", src["disr-req"]["licence"])
        self.assertIn("Resources and Energy Quarterly, December 2025.", src["disr-req"]["licence"])
        for i in ("comtrade", "census-exports", "eia-exports-destination"):
            self.assertIn(i, src)
        self.assertIn("Source: UN Comtrade", src["comtrade"]["licence"])


class ReadersSkipWithoutRaw(unittest.TestCase):
    """The readers of the raw files rebuild the caches; where raw/ is absent (the checks of GitHub) they are not run."""

    def test_the_cache_of_the_census_file_rebuilds(self):
        if not os.path.exists(us_lpg.RAW_CENSUS):
            self.skipTest("raw/ is not here")
        before = json.load(open(us_lpg.CACHE_FILE, encoding="utf-8"))["census"]
        self.assertEqual(us_lpg._census(us_lpg.RAW_CENSUS), before)

    def test_the_cache_of_the_workbook_rebuilds(self):
        if not os.path.exists(aus_req_lng.RAW):
            self.skipTest("raw/ is not here")
        before = json.load(open(aus_req_lng.CACHE_FILE, encoding="utf-8"))
        self.assertEqual(aus_req_lng.build(), before)


if __name__ == "__main__":
    unittest.main()
