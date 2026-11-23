"""Tests of the metal flows of audit entries C-034 to C-037 (package W3M1): Chilean copper concentrate, precious metals in
fine-metal equivalent, spodumene and lithium chemicals, nickel ore, ferro-nickel and nickel pig iron. The rule of clean.py
(rule 8) is tested in test_clean.py (PeerUnitValueTests). Expectations are the numbers of the entries.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_metal_flows.py"
"""
import json
import os
import re
import sys
import unittest

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("freight", "trade", "commodities"):
    p = os.path.join(ROOT, "pipeline", sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import caveats as CV  # noqa: E402
import hs_map  # noqa: E402
import modes  # noqa: E402
import ports  # noqa: E402

COMMOD = os.path.join(ROOT, "data", "commodities")
_cache = {}


def cache():
    if "df" not in _cache:
        _cache["df"] = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
    return _cache["df"]


def page(cid):
    with open(os.path.join(COMMOD, cid + ".json"), encoding="utf-8") as f:
        return json.load(f)


def source(name):
    with open(os.path.join(ROOT, "pipeline", "freight", name), encoding="utf-8") as f:
        return f.read()


class Groups(unittest.TestCase):
    def test_codes(self):
        exact, prefixes = hs_map.build_lookup()
        self.assertEqual(hs_map.group_of("720260", exact, prefixes), "nickel-fe")
        self.assertIsNone(hs_map.group_of("720230", exact, prefixes))  # other ferro-alloys stay out (not steel either)
        self.assertEqual(hs_map.split_group("253090", "AUS", "CHN"), "spodumene")
        self.assertEqual(hs_map.split_group("253090", "AUS", "JPN"), "minerals-nes")
        self.assertEqual(hs_map.split_group("253090", "ZAF", "CHN"), "minerals-nes")

    def test_cache_holds_the_new_groups(self):
        df = cache()
        y = df[df.year == 2024]
        mt = lambda g, o, d: y[(y.group == g) & (y.o == o) & (y.d == d)].t.sum() / 1e6
        self.assertAlmostEqual(mt("nickel-fe", "IDN", "CHN"), 8.91, delta=0.01)
        self.assertAlmostEqual(y[(y.group == "nickel-fe") & (y.o == "IDN")].t.sum() / 1e6, 9.39, delta=0.02)  # HS4 cache: 9.40 Mt of HS 7202
        self.assertAlmostEqual(mt("spodumene", "AUS", "CHN"), 3.72, delta=0.01)
        self.assertAlmostEqual(mt("spodumene", "ZWE", "CHN"), 0.98, delta=0.01)
        sp = df[df.group == "spodumene"]
        _, exporters, importers, _ = hs_map.SPLIT["253090"]
        self.assertTrue(sp.o.isin(exporters).all() and sp.d.isin(importers).all())

    def test_lane_tables(self):
        src = source("build_lanes.py")
        for g in ("nickel-fe", "spodumene"):
            for table in ("GROUPS", "COMMODITY", "LABEL", "CAP"):
                body = re.search(table + r" = \{(.*?)\n\}", src, re.S).group(1)
                self.assertIn(f'"{g}":', body, (g, table))
            self.assertIn(g, modes.FAMILY)
            self.assertIn(g, ports.SEGMENT)
        self.assertEqual(modes.mode_of("IDN", "CHN", "nickel-fe").kind, "sea")
        self.assertEqual(modes.mode_of("AUS", "CHN", "spodumene").kind, "sea")
        self.assertEqual(modes.mode_of("ZWE", "CHN", "spodumene").kind, "transit")  # landlocked exporter
        self.assertIn('"lithium": ["spodumene"]', source("build_freight.py"))

    def test_spodumene_route(self):
        r = next(x for x in json.loads(source("routes_def.json")) if x["id"] == "australia-china-spodumene")
        self.assertEqual(r["cargoes"], ["lithium"])
        self.assertEqual(r["corridor"], [{"k": "lithium", "o": ["AUS"], "d": ["CHN"]}])
        self.assertIn("Bunbury", [p["name"] for p in r["from"]["ports"]])
        self.assertNotIn("shareNa", r)
        self.assertNotIn("not in the atlas", r["notes"])


class Pages(unittest.TestCase):
    """The rebuilt commodity files (pipeline/commodities/build_commodities.py)."""

    def test_C034_copper(self):
        d = page("copper")
        ex = {r["c"]: r["v"] for r in d["exports"]["rows"]}
        self.assertEqual(d["exports"]["rows"][0]["c"], "CHL")  # was second with 4.96 Mt
        self.assertAlmostEqual(ex["CHL"], 13.97, delta=0.02)
        self.assertAlmostEqual(ex["PER"], 9.37, delta=0.01)
        f = next(f for f in d["flows"] if (f["o"], f["d"]) == ("CHL", "CHN"))
        self.assertAlmostEqual(f["v"], 9.27, delta=0.01)  # was 2.79 Mt
        self.assertTrue(f["est"] and f["s"] == "atlas" and f["n"].startswith("Atlas estimate"))
        self.assertIn("2.79 Mt", f["n"])  # the customs figure stays in the note
        imp = {r["c"]: r["v"] for r in d["imports"]["rows"]}
        self.assertTrue(27 <= imp["CHN"] <= 30, imp["CHN"])  # was 22.3 Mt
        self.assertTrue(any("Chile's copper concentrate" in n for n in d["notes"]))

    def test_C035_fine_metal(self):
        g = page("gold")
        self.assertEqual(g["summary"]["exports"]["s"], "atlas")
        self.assertTrue(6800 <= g["summary"]["exports"]["v"] <= 7300, g["summary"]["exports"]["v"])  # about 7,200 t from value
        self.assertAlmostEqual(g["summary"]["exports"]["alt"]["v"], 9468.4, delta=1)  # the customs gross weight, second
        self.assertTrue(all(f["est"] and f["s"] == "atlas" for f in g["flows"]))
        for cid in ("gold", "silver", "pgm"):
            d = page(cid)
            self.assertEqual(d["exports"]["s"], "atlas")
            self.assertTrue(d["exports"]["n"].startswith("Atlas estimate: fine-metal equivalent"), cid)
            self.assertTrue(all(r["n"].startswith("customs gross weight") for r in d["exports"]["rows"]), cid)
            self.assertFalse(any("frequently missing" in n for n in d["notes"]), cid)
        s = page("silver")
        self.assertNotIn(("RUS", "ARM"), [(f["o"], f["d"]) for f in s["flows"][:5]])  # was first with 4,990 t
        self.assertNotIn("ARM", [r["c"] for r in s["imports"]["rows"][:5]])
        p = page("pgm")
        f = next(f for f in p["flows"] if (f["o"], f["d"]) == ("ARE", "IND"))
        self.assertTrue(50 <= f["v"] <= 60, f["v"])  # was 186 t
        self.assertIn("plausible cause; it is not established here", f["n"])
        self.assertNotEqual(p["imports"]["rows"][0]["c"], "IND")

    def test_C035_caveat_is_built_from_the_data(self):
        df = cache()
        import clean
        c = clean.clean(df[df.group == "pgm"])
        a = CV.build(c, [], 2024, psd=None)
        self.assertIn("pgm-are-ind", a)
        t = a["pgm-are-ind"]["text"]
        self.assertIn("186 t", t)
        self.assertIn("30% of the 2024 average platinum price", t)
        self.assertIn("plausible cause", t)
        self.assertAlmostEqual(CV.annual_price("gold-m", 2024), 2387.58, delta=0.01)

    def test_C036_lithium(self):
        d = page("lithium")
        ex = [r["c"] for r in d["exports"]["rows"]]
        self.assertNotIn("NGA", ex)  # 8.6 kt at 286 USD/t: priced like ore
        self.assertFalse(any((f["o"], f["d"]) == ("BRA", "CHN") for f in d["flows"]))
        self.assertTrue(any("286 USD/t" in n for n in d["notes"]))  # left out, and said so
        sp = next(x["table"] for x in d["extra"] if x["key"] == "spodumene-exports")
        self.assertEqual(sp["s"], "atlas")
        self.assertEqual(sp["rows"][0]["c"], "AUS")
        self.assertAlmostEqual(sp["rows"][0]["v"], 3.72, delta=0.01)
        self.assertIn("% of the tonnage", sp["n"])
        alt = d["summary"]["production"]["alt"]
        self.assertEqual(alt["u"], "t LCE")
        self.assertAlmostEqual(alt["v"] / d["summary"]["production"]["v"], 5.323, delta=0.001)
        idx = {e["id"]: e for e in json.load(open(os.path.join(COMMOD, "index.json"), encoding="utf-8"))}
        self.assertNotIn("brine-derived", idx["lithium"]["blurb"])

    def test_C037_nickel(self):
        d = page("nickel")
        self.assertFalse(any("misreport" in x for x in d.get("discrepancies", [])))
        self.assertFalse(any("misreport" in (f.get("n") or "") for f in d["flows"]))
        f = next(f for f in d["flows"] if (f["o"], f["d"]) == ("PHL", "CHN"))
        self.assertAlmostEqual(f["v"], 34.655, delta=0.001)  # laterite ore, kept as reported
        fe = next(x["table"] for x in d["extra"] if x["key"] == "ferro-exports")
        self.assertEqual(fe["rows"][0]["c"], "IDN")
        self.assertAlmostEqual(fe["rows"][0]["v"], 9.39, delta=0.02)
        self.assertTrue(any("laterite ore" in n for n in d["notes"]))

    def test_kept_why_wording(self):
        import build_commodities as B
        self.assertIn("50 million", B._kept_why("wheat"))
        self.assertNotIn("50 million", B._kept_why("copper-ore"))


if __name__ == "__main__":
    unittest.main()
