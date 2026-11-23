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
        self.assertAlmostEqual(sum(r["v"] for r in w["rows"][:10]) / w["world"], 0.388, places=3)  # 38.8% (audit SOFT-26, PV-07)
        self.assertAlmostEqual(rest_of_world(w) / w["world"], 0.612, places=3)

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
        self.assertLess(size, 3e6)

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
        self.assertEqual(cp["yl"], ["revised", "estimated"])

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
