"""Full country tables, "Rest of world" and the series by country and year (audit M-098, M-077, A-060; package H1).

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_history.py"
The tests of the data files read the files as build_commodities.py last wrote them.
"""
import glob
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities"):
    p = os.path.join(ROOT, "pipeline", sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import build_commodities as B  # noqa: E402
import history as H  # noqa: E402

DATA = os.path.join(ROOT, "data")
COMMOD = os.path.join(DATA, "commodities")
HAS_BACI = os.path.exists(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))


def load(rel):
    with open(os.path.join(DATA, rel), encoding="utf-8") as f:
        return json.load(f)


def docs():
    for p in sorted(glob.glob(os.path.join(COMMOD, "*.json"))):
        name = os.path.basename(p)[:-5]
        if name in ("index", "companies"):
            continue
        with open(p, encoding="utf-8") as f:
            yield name, json.load(f)


def tables(d):
    for k in ("production", "refinery", "reserves", "consumption", "exports", "imports"):
        if isinstance(d.get(k), dict):
            yield k, d[k]
    for x in d.get("extra") or []:
        yield x["key"], x["table"]


def rest_of_world(t, shown=B.SHOWN_ROWS):
    """The line the page draws under the first rows (RankedBars, web/src/components/ui.tsx): the world total minus the rows
    drawn and the source's own 'Other countries' line."""
    return t["world"] - sum(r["v"] for r in t["rows"][:shown]) - (t.get("other") or 0)


class FullLists(unittest.TestCase):
    def test_ranked_keeps_every_row(self):
        rows = [(f"C{i:02d}", float(40 - i)) for i in range(30)]
        t = B.ranked(rows, 2024, "baci", "Mt", world=sum(v for _, v in rows))
        self.assertEqual(len(t["rows"]), 30)
        self.assertEqual([r["c"] for r in t["rows"]][:3], ["C00", "C01", "C02"])
        self.assertAlmostEqual(sum(r["v"] for r in t["rows"]), t["world"])
        self.assertEqual(len(B.ranked(rows, 2024, "baci", "Mt", top=5)["rows"]), 5)  # `top` still cuts when it is asked for

    def test_a_value_that_rounds_to_zero_is_not_a_row(self):
        t = B.ranked([("AAA", 5.0), ("BBB", 0.00001)], 2024, "eia-intl", "Mt", world=5.00001)
        self.assertEqual([r["c"] for r in t["rows"]], ["AAA"])

    def test_tables_hold_more_than_twelve_rows(self):
        d = dict(docs())
        self.assertGreater(len(d["wheat"]["imports"]["rows"]), 100)  # USDA PSD
        self.assertGreater(len(d["crude-oil"]["production"]["rows"]), 80)  # EIA
        self.assertGreater(len(d["steel"]["imports"]["rows"]), 150)  # CEPII BACI
        self.assertEqual(len(d["crude-oil"]["flows"]), B.NFLOWS)

    def test_full_lists_sum_to_the_world_within_rounding(self):
        """Where the world total is the sum of the source's entries (USDA PSD, CEPII BACI), the listed countries hold all of
        it but entries that are not countries of the atlas; nowhere do the lines exceed the world total."""
        n = 0
        for cid, d in docs():
            for k, t in tables(d):
                if not t.get("world"):
                    continue
                lines = sum(r["v"] for r in t["rows"]) + (t.get("other") or 0)
                self.assertLessEqual(lines, t["world"] * (1 + B.LINES_OVER_WORLD) + 1e-6, (cid, k))
                if t["s"] in ("baci", "usda-psd"):
                    self.assertGreater(lines / t["world"], 0.97, (cid, k))
                    n += 1
        self.assertGreater(n, 100)

    def test_rest_of_world_makes_the_shares_add_up(self):
        for cid, d in docs():
            for k, t in tables(d):
                if not t.get("world") or len(t["rows"]) <= B.SHOWN_ROWS:
                    continue
                rest = rest_of_world(t)
                self.assertGreaterEqual(rest, -t["world"] * B.LINES_OVER_WORLD - 1e-6, (cid, k))
                shares = sum(r["v"] for r in t["rows"][:B.SHOWN_ROWS]) + rest + (t.get("other") or 0)
                self.assertAlmostEqual(shares / t["world"], 1.0, places=9)
                # the remainder is the countries after the tenth and what the source does not give by country
                self.assertGreaterEqual(rest + 1e-6, sum(r["v"] for r in t["rows"][B.SHOWN_ROWS:]) - t["world"] * B.LINES_OVER_WORLD, (cid, k))

    def test_the_quoted_tables(self):
        d = dict(docs())
        w = d["wheat"]["imports"]
        # the table is USDA's 2026/27 forecast since package A1: 38.3% (the audit's 38.8% was the 2025/26 table, below)
        self.assertAlmostEqual(sum(r["v"] for r in w["rows"][:10]) / w["world"], 0.383, places=3)
        self.assertAlmostEqual(rest_of_world(w) / w["world"], 0.617, places=3)
        h = load("commodities/history/wheat.json")["t"]["imports"]
        i = h["years"].index(2025)  # 2025/26, the estimate: 38.8% (audit SOFT-26, PV-07)
        top = sorted((v[i] for v in h["c"].values() if v[i]), reverse=True)[:10]
        self.assertAlmostEqual(sum(top) / h["world"][i], 0.388, places=3)

    def test_usgs_other_countries_stays_its_own_line(self):
        d = dict(docs())
        st = d["steel"]["production"]
        self.assertEqual(st["other"], 230)
        self.assertEqual(st["hidden"]["k"], len(st["rows"]) - B.SHOWN_ROWS)
        mn = d["manganese"]["production"]
        self.assertEqual(mn["other"], 1300)  # USGS 'Other countries', 2025
        self.assertAlmostEqual((sum(r["v"] for r in mn["rows"]) + mn["other"]) / mn["world"], 1.0)

    def test_manganese_reserve_shares_add_up_to_100(self):
        """M-098: the reserve lines exceed the rounded USGS total (105.8% of it): the shares rest on the sum of the lines."""
        r = dict(docs())["manganese"]["reserves"]
        self.assertEqual((r["world"], r["worldPublished"]), (1798000, 1700000))
        self.assertAlmostEqual(sum(x["v"] for x in r["rows"]) / r["world"], 1.0)

    def test_no_recipe_is_published(self):
        for cid, d in docs():
            for k, t in tables(d):
                self.assertFalse([x for x in t if x.startswith("_")], (cid, k))


class Series(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hist = {}
        for p in sorted(glob.glob(os.path.join(COMMOD, "history", "*.json"))):
            with open(p, encoding="utf-8") as f:
                cls.hist[os.path.basename(p)[:-5]] = json.load(f)
        cls.docs = dict(docs())

    def test_files_and_size(self):
        self.assertGreaterEqual(len(self.hist), 35)
        size = sum(os.path.getsize(p) for p in glob.glob(os.path.join(COMMOD, "history", "*.json")))
        self.assertLess(size, 3.9e6)  # 3 MB until package NC3 (A-010: six new pages, 3.16 MB with them), 3.4 MB until FNCB: 3.22 MB measured plus a fifth

    def test_the_latest_year_is_the_table_of_the_page(self):
        n = 0
        for cid, h in self.hist.items():
            tabs = dict(tables(self.docs[cid]))
            for k, s in h["t"].items():
                t = tabs[k]
                self.assertEqual(H.check(t, s), [], (cid, k))
                self.assertEqual((s["u"], s["s"]), (t["u"], t["s"]), (cid, k))
                n += 1
        self.assertGreater(n, 100)

    def test_years_by_source(self):
        cu = self.hist["crude-oil"]["t"]
        self.assertEqual(cu["exports"]["years"][0], B.HIST_FROM)
        self.assertEqual(cu["exports"]["years"][-1], B.BACI_YEAR)
        self.assertEqual(cu["production"]["years"][-1], self.docs["crude-oil"]["production"]["y"])  # EIA
        wh = self.hist["wheat"]["t"]["imports"]
        self.assertEqual((wh["years"][0], wh["years"][-1]), (B.HIST_FROM, B.PSD_MY))  # the one year rule of _latest_inputs
        self.assertEqual(wh["labels"][-1], B.PSD_LABEL)
        cp = self.hist["copper"]["t"]["production"]
        self.assertEqual(cp["years"], [int(B.USGS_YEAR) - 1, int(B.USGS_YEAR)])
        # the file marks values "Estimated." one by one and gives no word such as "revised" for a year (GH1.2)
        self.assertEqual(cp["yl"][0], f"as published in USGS MCS {B.USGS_EDITION}")
        self.assertNotIn("revised", " ".join(cp["yl"]))

    def test_one_value_per_year(self):
        for cid, h in self.hist.items():
            for k, s in h["t"].items():
                n = len(s["years"])
                self.assertEqual(len(s["world"]), n)
                for c, v in s["c"].items():
                    self.assertEqual(len(v), n, (cid, k, c))
                    self.assertTrue(all(x is None or x > 0 for x in v), (cid, k, c))

    def test_estimated_years_are_flagged(self):
        """A row that is mostly an Atlas estimate in the table is flagged in the latest year of its series, and only then."""
        flagged = 0
        for cid, h in self.hist.items():
            tabs = dict(tables(self.docs[cid]))
            for k, s in h["t"].items():
                last = len(s["years"]) - 1
                est = {c for c, ix in (s.get("est") or {}).items() if last in ix}
                self.assertEqual(est, {r["c"] for r in tabs[k]["rows"] if r.get("est")}, (cid, k))
                flagged += sum(len(ix) for ix in (s.get("est") or {}).values())
        self.assertGreater(flagged, 50)
        # USGS marks its own estimates value by value: the source's estimate, not the atlas's
        cp = self.hist["copper"]["t"]["production"]
        self.assertIn(1, cp["srcEst"]["CHL"])
        self.assertNotIn("est", cp)

    def test_eu_entity_of_2005_is_the_eu_row(self):
        su = self.hist["sugar"]["t"]["production"]
        self.assertIsNotNone(su["c"]["EU27"][0])  # PSD names it "EU-25" in market year 2005/06

    def test_eu_row_is_labelled_for_what_it_is_each_year(self):
        """USDA PSD's European Union row holds the United Kingdom until the file gives the United Kingdom a row of its own
        (2016/17), and is EU-25 in 2005/06 sugar: the row is named so, its line breaks, the note says it (GH1.4)."""
        wi = self.hist["wheat"]["t"]["imports"]
        i16 = wi["years"].index(2016)
        cl = wi["cl"]["EU27"]
        self.assertTrue(all(x == "European Union with the UK" for x in cl[:i16]))
        self.assertTrue(all(x is None for x in cl[i16:]))
        self.assertIsNone(wi["c"]["GBR"][i16 - 1])
        self.assertIsNotNone(wi["c"]["GBR"][i16])
        self.assertIn(i16, wi["brk"]["EU27"])
        self.assertIn(i16, wi["brk"]["GBR"])  # the United Kingdom leaving the row is not a new trade
        note = next(n for n in wi["n"] if n.startswith("The European Union row"))
        self.assertIn("2005/06 to 2015/16", note)
        self.assertIn("from 2016/17", note)
        su = self.hist["sugar"]["t"]["production"]
        self.assertEqual(su["cl"]["EU27"][0], "EU-25")
        self.assertEqual(su["brk"]["EU27"], [1, su["years"].index(2016)])
        # no rebuilt aggregate: the row is the file's own value
        self.assertEqual(wi["c"]["EU27"][-1], next(r["v"] for r in self.docs["wheat"]["imports"]["rows"] if r["c"] == "EU27"))

    def test_out_of_line_rule(self):
        """A value far out of line with both its neighbours, which carries the jump of the world total, is flagged; a shock
        spread over many countries, a fall where a series stops, and a jump whose declared value moved with it are not."""
        w = [100.0, 102.0, 300.0, 101.0, 99.0]
        vals = {"AAA": [10.0, 11.0, 210.0, 10.0, 9.0], "BBB": [90.0, 91.0, 90.0, 91.0, 90.0]}
        self.assertEqual(H.out_of_line(w, vals), {"AAA": [2]})
        # the declared value moved with the tonnage: a real change of trade
        usd = {"AAA": [100.0, 110.0, 2100.0, 100.0, 90.0]}
        self.assertEqual(H.out_of_line(w, vals, usd), {})
        # a shock spread over many countries moves the world without one country carrying the jump
        spread = {k: [10.0, 10.0, 5.0, 10.0, 10.0] for k in "ABCDEFGHIJ"}
        self.assertEqual(H.out_of_line([100.0, 100.0, 50.0, 100.0, 100.0], spread), {})
        # a country whose series stops after a big fall (an export ban) is not a break
        self.assertEqual(H.out_of_line([100.0, 100.0, 60.0, 62.0], {"AAA": [50.0, 50.0, 5.0, None], "BBB": [50.0, 50.0, 55.0, 62.0]}), {})
        # a jump on the last year of a series that stops, carrying the world's jump (the EIA's US LPG of 2021)
        self.assertEqual(H.out_of_line([300.0, 310.0, 420.0, 290.0], {"USA": [43.0, 43.0, 148.0, None], "CHN": [70.0, 72.0, 74.0, 76.0]}), {"USA": [2]})

    def test_out_of_line_on_the_real_series(self):
        lp = self.hist["lpg"]["t"]["consumption"]
        i21 = lp["years"].index(2021)
        # the US LPG tonnes of 2021 (148 Mt against 43 Mt) are replaced by EIA's barrels per day converted, and the years after 2021 are
        # converted too (E1b): nothing is left to flag, and no coverage break either
        self.assertNotIn("out", lp)
        self.assertLess(lp["c"]["USA"][i21], 1.5 * lp["c"]["USA"][i21 - 1])
        self.assertTrue(all(v is not None for v in lp["c"]["USA"][i21:]))
        self.assertFalse(any(n.startswith("United States has no figure after") for n in lp["n"]))
        # real shocks survive: Libya's crude oil exports of 2020, Russia's wheat exports of 2010, Malaysia's bauxite exports of
        # 2015 (its declared value moved with the tonnage), and the fall of 2009 spread over every potash trader
        for cid, k, c, y in (("crude-oil", "exports", "LBY", 2020), ("wheat", "exports", "RUS", 2010), ("bauxite", "exports", "MYS", 2015)):
            s = self.hist[cid]["t"][k]
            self.assertNotIn(s["years"].index(y), (s.get("out") or {}).get(c, []), (cid, k, c, y))
        self.assertNotIn("out", self.hist["potash"]["t"]["exports"])
        flagged = {(cid, k) for cid, h in self.hist.items() for k, s in h["t"].items() if s.get("out")}
        # a rule for breaks, not for the ups and downs of trade: nine tables, each named. Four are older (cobalt and uranium trade: Congo's cobalt
        # exports and China's cobalt imports of 2016, Namibia's uranium exports and Canada's uranium imports of 2009); the PSD and customs tables of
        # package NC2 add three, real swings of one country in the source's own figures (M-023: China's and the EU's sorghum imports, Ukraine's sunflower seed
        # exports and stocks); the metal bulks add two (A-010): North Korea's graphite exports and China's graphite imports, each one year (2016). Mozambique's
        # coke exports and India's coke imports of 2016 (A-010, 65 Mt at 4 USD per tonne) were flagged too until package FNCB made coke a homogeneous group:
        # the row is now a flagged Atlas estimate and the series has no break
        self.assertEqual(flagged, {("cobalt", "exports"), ("cobalt", "imports"), ("uranium", "exports"), ("uranium", "imports"),
                                   ("sorghum", "imports"), ("sunflower", "exports"), ("sunflower", "stocks"),
                                   ("graphite", "exports"), ("graphite", "imports")})
        self.assertNotIn("met-coal", {cid for cid, _ in flagged})

    def test_spodumene_series_starts_with_the_lanes(self):
        """The spodumene estimate is not extended to years its rule does not cover: the series starts in the lanes' first year,
        with the same sentence (GH1.6)."""
        import build_lanes as BL
        first, why = BL.FIRST_YEAR["spodumene"]
        sp = self.hist["lithium"]["t"]["spodumene-exports"]
        self.assertEqual(sp["years"][0], first)
        self.assertEqual(sp["n"][0], why + ".")

    def test_caveats_of_some_years_only(self):
        """A past-year table keeps the caveats of its table; one that speaks of some years only names them (GH1.3)."""
        d = self.docs
        lp = d["lpg"]["consumption"]
        s = self.hist["lpg"]["t"]["consumption"]
        # the United States is converted from barrels per day in the years EIA's tonnes are missing or broken (E1b)
        self.assertEqual(lp["caveatYears"], [y for y in s["years"] if y >= 2021])
        self.assertEqual(d["lng"]["exports"]["caveatYears"], [B.BACI_YEAR])
        self.assertTrue(d["lng"]["exports"]["caveatShort"])  # shown in the other years
        self.assertTrue(d["uranium"]["exports"]["caveat"].startswith(d["uranium"]["exports"]["caveatPast"][:-1]))
        kg = d["thermal-coal"]["reserves"]
        self.assertEqual(kg["caveatYears"][0], 2014)
        # scope caveats hold for every year: no years named
        for cid, k in (("refined-products", "exports"), ("refined-products", "imports"), ("natural-gas", "exports"), ("cobalt", "exports"), ("potash", "imports")):
            self.assertTrue(d[cid][k]["caveat"], (cid, k))
            self.assertNotIn("caveatYears", d[cid][k], (cid, k))
        for cid, doc in d.items():
            for k, t in tables(doc):
                if "caveatYears" in t:
                    self.assertTrue(t.get("caveat"), (cid, k))
                    self.assertIn(k, self.hist[cid]["t"], (cid, k))

    def test_countries_that_split_are_noted(self):
        """Sudan and South Sudan, Serbia and Montenegro, the Netherlands Antilles: one sentence where the series holds the
        break, with the years read from the files (GH1.10)."""
        cp = self.hist["crude-oil"]["t"]["production"]
        i12 = cp["years"].index(2012)
        self.assertIn("South Sudan has figures of its own from 2012: the source's Sudan up to 2011 covers it too.", cp["n"])
        self.assertIn(i12, cp["brk"]["SDN"])
        self.assertIsNone(cp["c"]["SSD"][i12 - 1])
        ends = H.code_ends()
        self.assertEqual({c: e[1] for c, e in ends.items()}, {"SCG": 2005, "ANT": 2010, "SDN": 2011})
        notes = [n for h in self.hist.values() for s in h["t"].values() for n in s.get("n", [])]
        self.assertTrue(any("Serbia" in n and "Serbia and Montenegro as one entity" in n for n in notes))
        self.assertTrue(any("Curaçao" in n and "Netherlands Antilles" in n for n in notes))
        # South Sudan starting in a series where Sudan has no figure is not a split of Sudan's figures
        self.assertFalse(any("South Sudan" in n for n in self.hist["corn"]["t"]["production"].get("n", [])))

    @unittest.skipUnless(HAS_BACI, "pipeline/cache/baci_flows.csv.gz is not on disk")
    def test_a_past_estimated_year_matches_the_cleaned_frame(self):
        baci = B.Baci()
        s = self.hist["crude-oil"]["t"]["exports"]
        c, ix = next((c, ix) for c, ix in s["est"].items() if ix and ix[0] < len(s["years"]) - 1)
        y = s["years"][ix[0]]
        x = baci.df[(baci.df["group"] == "crude-oil") & (baci.df["year"] == y) & (baci.df["o"] == c)]
        self.assertGreaterEqual(x["t_est"].sum() / x["t"].sum(), 0.5)
        t, _ = baci.ranked("crude-oil", "exports", "Mt", 1e6, "crude oil", year=y)
        self.assertTrue(next(r for r in t["rows"] if r["c"] == c).get("est"))


if __name__ == "__main__":
    unittest.main()
