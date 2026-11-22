"""Tests M01 to M14 of the trade-engine plan (package E1-modes): the sea / transit / mixed / land rule.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The lane and pairs forms of M01, M03, M04, M08 (port part) belong to later packages and are not tested here.
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("freight", "trade", "geo"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))

import pandas as pd  # noqa: E402

import modes  # noqa: E402
from clean import clean  # noqa: E402



def load_json(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return json.load(f)


with open(os.path.join(ROOT, "pipeline", "freight", "build_lanes.py"), encoding="utf-8") as _f:
    SOURCE = _f.read()
LANE_GROUPS = set(re.findall(r'"([a-z\-]+)":', re.search(r"GROUPS = \{(.*?)\n\}", SOURCE, re.S).group(1)))

_frame = None


def frame():
    """The 32 lane groups after clean(), with the mode of every row (computed once)."""
    global _frame
    if _frame is None:
        df = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        df = clean(df[df["group"].isin(LANE_GROUPS)])
        df["kind"] = [modes.mode_of(o, d, g).kind for o, d, g in zip(df["o"], df["d"], df["group"])]
        _frame = df
    return _frame


def mt(group, o, d, year=2024):
    df = frame()
    r = df[(df.group == group) & (df.o == o) & (df.d == d) & (df.year == year)]
    return float(r.t.sum()) / 1e6


def kind(o, d, group):
    return modes.mode_of(o, d, group).kind


class ModeTests(unittest.TestCase):
    def assertMt(self, group, o, d, expected, tol=0.05, year=2024):
        self.assertAlmostEqual(mt(group, o, d, year), expected, delta=tol, msg=f"{group} {o}-{d} {year}")

    def test_M01_india_china_iron_ore_is_sea(self):
        self.assertEqual(kind("IND", "CHN", "iron-ore"), "sea")
        self.assertMt("iron-ore", "IND", "CHN", 35.243, 0.01)

    def test_M02_lng(self):
        df = frame()
        y = df[(df.group == "lng") & (df.year == 2024)]
        for o, d in (("RUS", "CHN"), ("NOR", "FIN"), ("MYS", "THA")):
            self.assertEqual(kind(o, d, "lng"), "sea", (o, d))
        self.assertMt("lng", "RUS", "CHN", 8.284, 0.01)
        for o, d in (("IRN", "TUR"), ("IRN", "IRQ"), ("MMR", "THA"), ("GBR", "IRL")):
            self.assertEqual(kind(o, d, "lng"), "land", (o, d))
        # two coastal countries that are not land neighbours: never land
        for o, d in set(zip(y.o, y.d)):
            if o in modes.NEIGHBOURS.get(d, ()) or not modes.coastal(o) or not modes.coastal(d):
                continue
            self.assertNotEqual(kind(o, d, "lng"), "land", (o, d))
        self.assertLessEqual(y[y.kind == "land"].t.sum() / 1e6, 2.2)
        for year, expected in ((2021, 357.6), (2024, 369.9)):
            s = df[(df.group == "lng") & (df.year == year) & df.kind.isin(["sea", "transit"])].t.sum() / 1e6
            self.assertAlmostEqual(s, expected, delta=3, msg=f"seaborne LNG {year}")

    def test_M03_benelux_rhine_land(self):
        for g, o, d, v in (("crude-oil", "NLD", "BEL", 29.52), ("refined-products", "NLD", "DEU", 17.06),
                           ("wheat", "FRA", "BEL", 2.54), ("steel", "DEU", "POL", 3.03)):
            self.assertEqual(kind(o, d, g), "land", (g, o, d))
            self.assertMt(g, o, d, v, 0.02)

    def test_M04_russia_china_mixed(self):
        self.assertEqual(kind("RUS", "CHN", "crude-oil"), "mixed")
        self.assertEqual(kind("RUS", "CHN", "coal"), "mixed")
        self.assertMt("crude-oil", "RUS", "CHN", 108.47, 0.05)
        self.assertMt("coal", "RUS", "CHN", 95.07, 0.1)
        df = frame()
        coal = df[(df.group == "coal") & (df.year == 2024)]
        sea = coal[coal.kind.isin(["sea", "transit"])].t.sum() / 1e6
        self.assertTrue(1370 <= sea <= 1380, sea)

    def test_M05_usa_mexico_by_family(self):
        self.assertEqual(kind("MEX", "USA", "crude-oil"), "sea")
        self.assertEqual(kind("USA", "MEX", "crude-oil"), "sea")
        for g in ("refined-products", "lpg", "corn"):
            self.assertEqual(kind("USA", "MEX", g), "mixed", g)
        self.assertEqual(kind("USA", "MEX", "steel"), "land")
        self.assertMt("crude-oil", "MEX", "USA", 26.50)
        self.assertMt("refined-products", "USA", "MEX", 30.10)
        self.assertMt("lpg", "USA", "MEX", 9.33)
        self.assertMt("corn", "USA", "MEX", 7.77)
        self.assertMt("steel", "USA", "MEX", 3.92)

    def test_M06_french_guiana(self):
        adj = load_json("pipeline", "cache", "adjacency.json")
        self.assertNotIn("BRA", adj["neighbours"]["FRA"])
        self.assertNotIn("SUR", adj["neighbours"]["FRA"])
        self.assertNotIn("FRA", adj["neighbours"].get("BRA", []))
        self.assertNotIn("FRA", adj["neighbours"].get("SUR", []))
        self.assertEqual(sorted(sorted(p) for p in adj["overseas"]), [["BRA", "FRA"], ["FRA", "SUR"]])
        self.assertEqual(kind("BRA", "FRA", "soymeal"), "sea")
        self.assertMt("soymeal", "BRA", "FRA", 1.73, 0.01)

    def test_M07_territories_without_polygon(self):
        self.assertTrue(modes.coastal("GIB"))
        self.assertEqual(kind("ITA", "GIB", "refined-products"), "sea")
        self.assertMt("refined-products", "ITA", "GIB", 3.838, 0.01)
        places = load_json("data", "countries", "places.json")
        self.assertEqual({p["c"] for p in places}, {"GIB", "BES", "CXR", "TKL", "XAS"})
        for p in places:
            self.assertTrue(p["name"])
        index = load_json("data", "countries", "index.json")
        self.assertEqual(len(index), 239)
        self.assertFalse({p["c"] for p in places} & {c["c"] for c in index})

    def test_M08_transit(self):
        for g, o, d in (("crude-oil", "KAZ", "ITA"), ("potash", "UZB", "BRA"),
                        ("copper-ore", "SRB", "CHN"), ("coffee", "UGA", "ITA")):
            m = modes.mode_of(o, d, g)
            self.assertEqual(m.kind, "transit", (g, o, d))
        self.assertMt("crude-oil", "KAZ", "ITA", 15.38, 0.01)
        self.assertMt("potash", "UZB", "BRA", 1.41, 0.01)

    def test_M09_land_unchanged(self):
        for g, o, d, v in (("coal", "MNG", "CHN", 82.91), ("crude-oil", "KAZ", "CHN", 2.79),
                           ("soybeans", "PRY", "ARG", 6.83), ("wheat", "KAZ", "AFG", 0.25)):
            self.assertEqual(kind(o, d, g), "land", (g, o, d))
            self.assertMt(g, o, d, v, 0.01)

    def test_M10_totals_by_mode(self):
        y = frame()[lambda d: d.year == 2024]
        tot = y.groupby("kind").t.sum() / 1e6
        self.assertAlmostEqual(tot.get("sea", 0) + tot.get("transit", 0), 7873, delta=40)
        self.assertAlmostEqual(tot.get("mixed", 0), 309.8, delta=5)
        self.assertAlmostEqual(tot.get("land", 0), 935, delta=40)
        self.assertAlmostEqual(tot.sum(), 9117.8, delta=1)
        self.assertEqual(set(tot.index), {"sea", "transit", "mixed", "land"})

    def test_M11_seaborne_by_group(self):
        y = frame()[lambda d: d.year == 2024]
        sb = y[y.kind.isin(["sea", "transit"])].groupby("group").t.sum() / 1e6
        self.assertGreaterEqual(sb["iron-ore"], 1630)
        self.assertTrue(365 <= sb["lng"] <= 375, sb["lng"])
        self.assertLessEqual(sb["wheat"], 170)
        self.assertLessEqual(sb["steel"], 290)
        self.assertTrue(940 <= sb["refined-products"] <= 975, sb["refined-products"])
        self.assertTrue(120 <= sb["lpg"] <= 130, sb["lpg"])

    def test_M12_sea_neighbours(self):
        for g, o, d, v in (("crude-oil", "COL", "PAN", 8.11), ("crude-oil", "NOR", "FIN", 6.70),
                           ("coal", "COL", "BRA", 3.21), ("phosphate-rock", "PER", "BRA", 1.16)):
            self.assertEqual(kind(o, d, g), "sea", (g, o, d))
            self.assertMt(g, o, d, v, 0.01)

    def test_M13_families_outside_the_lane_model(self):
        self.assertEqual(kind("KAZ", "RUS", "uranium"), "land")
        self.assertEqual(kind("KAZ", "CHN", "uranium"), "land")
        for g in ("gold", "silver", "pgm"):
            self.assertIsNone(modes.family_of(g), g)
            self.assertIsNone(modes.mode_of("CHE", "USA", g), g)
        # every lane group has a family, and so do the other metals of M-100
        for g in LANE_GROUPS | {"uranium", "lithium", "cobalt", "rare-earths", "tin-ore", "tin-metal", "lead-ore",
                                "lead-metal", "zinc-metal"}:
            self.assertIsNotNone(modes.family_of(g), g)

    def test_M14_every_list_entry_has_a_reason(self):
        for name in ("SEA_NEIGHBOURS", "MIXED", "FLOW_OVERRIDES", "OVERSEAS_BORDERS"):
            table = getattr(modes, name)
            self.assertTrue(table, name)
            items = table.items() if isinstance(table, dict) else [(e[0], e) for e in table]
            for key, entry in items:
                self.assertTrue(entry.reason and entry.reason.strip(), (name, key))

    # ---- additional checks on the rule itself
    def test_two_landlocked_ends_are_land(self):
        self.assertEqual(kind("AUT", "CZE", "steel"), "land")
        self.assertEqual(kind("KAZ", "UZB", "wheat"), "land")

    def test_pseudo_place_is_seaborne_not_land(self):
        self.assertEqual(kind("IRN", "XAS", "crude-oil"), "sea")

    def test_mode_has_basis(self):
        self.assertEqual(modes.mode_of("RUS", "CHN", "crude-oil").basis, "pair")
        self.assertEqual(modes.mode_of("MNG", "CHN", "coal").kind, "land")
        self.assertIn(modes.mode_of("IND", "CHN", "iron-ore").basis, ("pair", "flow", "product"))
        self.assertEqual(modes.mode_of("BRA", "ARG", "iron-ore").kind, "land")

    def test_places_extra_matches_adjacency(self):
        adj = load_json("pipeline", "cache", "adjacency.json")
        extra = load_json("pipeline", "geo", "places_extra.json")
        self.assertEqual({p["c"] for p in adj["extra"]}, {p["c"] for p in extra})
        for p in extra:
            self.assertEqual(p["c"] in adj["coastal"], bool(p["coastal"]), p["c"])


if __name__ == "__main__":
    unittest.main()
