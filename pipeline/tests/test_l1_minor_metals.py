"""Package L1 (audit M-015, M-026 and the engine's follow-ups): lanes for the minor metals, the fertiliser gateways of
Russia and Belarus, transit ports for the landlocked ends that carried most of the tonnage "not routed", and the
spodumene route.

    .venv/bin/python -I -m unittest pipeline/tests/test_l1_minor_metals.py
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for p in (os.path.join(ROOT, "pipeline", "freight"), os.path.join(ROOT, "pipeline", "trade")):
    if p not in sys.path:
        sys.path.insert(0, p)

import build_lanes as BL  # noqa: E402
import modes as MD  # noqa: E402
import ports as P  # noqa: E402
import vessel_rules as VR  # noqa: E402
from gateways import energy as EN  # noqa: E402

LANES = os.path.join(ROOT, "data", "freight", "lanes")
PAIRS = os.path.join(ROOT, "data", "freight", "pairs")
NEW = ("lead-ore", "lead-metal", "zinc-metal", "tin-metal", "tin-ore", "cobalt", "lithium", "rare-earths")
BUILT = all(os.path.exists(os.path.join(LANES, g + ".json")) for g in NEW)
need_build = unittest.skipUnless(BUILT, "build_lanes.py has not written the lane files of the new groups yet")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def lane(lid):
    g = lid.split(":")[0]
    return next((x for x in load(os.path.join(LANES, g + ".json"))["lanes"] if x["id"] == lid), None)


def pair(g, o, d):
    p = load(os.path.join(PAIRS, g + ".json"))
    ci = {c: i for i, c in enumerate(p["cols"])}
    r = next((r for r in p["rows"] if r[0] == o and r[1] == d), None)
    if r is None:
        return None
    out = {c: r[i] for c, i in ci.items()}
    out["load_code"] = p["ports"][out["load"]][0] if out["load"] >= 0 else None
    out["dis_code"] = p["ports"][out["dis"]][0] if out["dis"] >= 0 else None
    return out


class Rules(unittest.TestCase):
    """Mode, gateway segment and vessel class of the new groups (no build needed)."""

    def test_groups_are_lane_groups_with_a_commodity(self):
        want = {"lead-ore": "lead", "lead-metal": "lead", "zinc-metal": "zinc", "tin-metal": "tin", "tin-ore": "tin",
                "cobalt": "cobalt", "lithium": "lithium", "rare-earths": "rare-earths"}
        for g, k in want.items():
            self.assertIn(g, BL.GROUPS, g)
            self.assertEqual(BL.COMMODITY.get(g, g), k, g)
            self.assertIn(g, BL.CAP, g)
            self.assertIn(g, BL.LABEL, g)
            self.assertEqual(MD.family_of(g), "metal", g)

    def test_one_pair_of_each_group(self):
        # (group, exporter, importer, mode, segment, first class)
        cases = [("lead-ore", "PER", "CHN", "sea", "ore", "supramax"),
                 ("lead-metal", "AUS", "GBR", "sea", "box", "container"),
                 ("zinc-metal", "KOR", "IND", "sea", "box", "container"),
                 ("tin-metal", "IDN", "CHN", "sea", "box", "container"),
                 ("tin-ore", "AUS", "CHN", "sea", "box", "container"),
                 ("cobalt", "COD", "CHN", "sea", "box", "container"),
                 ("lithium", "CHL", "CHN", "sea", "box", "container"),
                 ("rare-earths", "AUS", "MYS", "sea", "box", "container")]
        for g, o, d, kind, seg, cls in cases:
            self.assertEqual(MD.mode_of(o, d, g, 2024).kind, kind, g)
            self.assertEqual(P.segment(g), seg, g)
            self.assertEqual(VR.classes(g, o, d, 50_000, 5000)[0], cls, g)

    def test_precious_metals_stay_without_a_mode(self):
        for g in ("gold", "silver", "pgm"):
            self.assertIsNone(MD.mode_of("CHE", "IND", g))
            self.assertNotIn(g, BL.GROUPS)

    def test_site_lists_the_new_groups(self):
        with open(os.path.join(ROOT, "web", "src", "lib", "freight.ts"), encoding="utf-8") as f:
            ts = f.read()
        block = ts[ts.index("export const LANE_GROUPS"):ts.index("};", ts.index("export const LANE_GROUPS"))]
        listed = set(re.findall(r"'([a-z-]+)'", block.split("=", 1)[1]))
        self.assertEqual(set(BL.GROUPS) - listed, set(), "lane groups missing from LANE_GROUPS")


class Gateways(unittest.TestCase):
    """M-026 and the landlocked ends (no build needed)."""

    def test_russian_fertiliser_options_include_the_black_sea(self):
        codes = [c for c, _, _ in P.candidates("RUS", "urea", "load")]
        self.assertEqual(codes[:3], ["RUULU", "RUNVS", "RUTAM"])
        a = P.assign("RUS", "BRA", "urea")
        self.assertEqual(a.basis, "open")
        self.assertIn("RUNVS", {o.load for o in a.options})

    def test_belarusian_potash(self):
        m = MD.mode_of("BLR", "CHN", "potash")
        self.assertEqual(m.kind, "mixed")
        self.assertIn("rail", m.note)
        self.assertEqual(EN.transit("BLR", "fert")[0], "RULED")
        self.assertEqual(MD.mode_of("BLR", "BRA", "potash").kind, "transit")

    def test_transit_rows_of_l1(self):
        for iso3, fam, code in (("KAZ", "drybulk", "RUULU"), ("PRY", "grain", "ARUPR"), ("PRY", "vegoil", "ARUPR"),
                                ("AUT", "drybulk", "SIKOP"), ("HUN", "metal", "SIKOP"), ("SRB", "grain", "ROCND"),
                                ("BWA", "drybulk", "NAWVB")):
            t = EN.transit(iso3, fam)
            self.assertEqual(t[0], code, (iso3, fam))
            self.assertTrue(t[2].startswith("https://"), (iso3, fam))
        # family rows still win over the new default rows
        self.assertEqual(EN.transit("AUT", "crude")[0], "ITTRS")
        self.assertEqual(EN.transit("SRB", "crude")[0], "HROMI")
        # no row where the page would also cover a cargo it does not name (Slovak crude) or names nothing
        for iso3 in ("SVK", "UZB", "TKM"):
            self.assertNotIn(iso3, EN.TRANSIT)
        self.assertIsNone(EN.transit("KAZ", "products"))
        self.assertIsNone(EN.transit("PRY", "products"))


@need_build
class Lanes(unittest.TestCase):
    def test_a_lane_of_each_new_group(self):
        for lid, load_, cls in (("lead-ore:PER-CHN", "PECLL", "supramax"), ("lead-metal:AUS-GBR", "AUFRE", "container"),
                                ("zinc-metal:KOR-IND", "KRPUS", "container"), ("tin-metal:IDN-CHN", "IDTPP", "container"),
                                ("tin-ore:AUS-CHN", "AUFRE", "container"), ("cobalt:COD-CHN", "TZDAR", "container"),
                                ("lithium:CHL-CHN", "CLANF", "container"), ("rare-earths:AUS-MYS", "AUFRE", "container")):
            ln = lane(lid)
            self.assertIsNotNone(ln, lid)
            self.assertEqual(ln["set"], "main", lid)
            self.assertEqual(ln["load"][0], load_, lid)
            self.assertEqual(ln["vclass"][0], cls, lid)
            self.assertGreater(ln["flow"]["v"], 0, lid)

    def test_congolese_cobalt_goes_through_dar_es_salaam(self):
        ln = lane("cobalt:COD-CHN")
        self.assertEqual(ln["transit"]["port"], "TZDAR")
        self.assertEqual(ln["transit"]["url"], "https://en.wikipedia.org/wiki/Port_of_Dar_es_Salaam")

    def test_small_groups_keep_their_tonnage(self):
        # four decimals of Mt under 1 Mt a year: a 2 kt lane is not printed 0.002 for anything between 1.5 and 2.5 kt
        f = load(os.path.join(LANES, "tin-metal.json"))
        self.assertLess(f["seaborne"][-1], 1)
        self.assertTrue(any(round(ln["flow"]["v"], 3) != ln["flow"]["v"] for ln in f["lanes"]))
        p = load(os.path.join(PAIRS, "tin-metal.json"))
        # the pairs total is the sum of its rows (0.1 kt each): within half a kilotonne of the exact total
        self.assertAlmostEqual(f["seaborne"][-1], p["seaborne"] / 1e3, delta=0.0005)

    def test_belarusian_potash_lanes(self):
        ln = lane("potash:BLR-CHN")
        self.assertEqual(ln.get("mode"), "mixed")
        self.assertEqual(ln["transit"]["port"], "RULED")
        self.assertIsNone(ln["share"])
        r = pair("potash", "BLR", "BRA")
        self.assertEqual((r["m"], r["load_code"]), (1, "RULED"))

    def test_landlocked_pairs_now_routed(self):
        for g, o, d, end, code in (("coal", "KAZ", "MAR", "load", "RUULU"), ("soymeal", "PRY", "PER", "load", "ARUPR"),
                                   ("coal", "USA", "AUT", "dis", "SIKOP"), ("copper-ore", "SRB", "CHN", "load", "ROCND"),
                                   ("copper-ore", "BWA", "CHN", "load", "NAWVB")):
            r = pair(g, o, d)
            self.assertIsNotNone(r, (g, o, d))
            self.assertEqual(r["m"], 1, (g, o, d))
            self.assertEqual(r[end + "_code"], code, (g, o, d))
            self.assertGreater(r["nm"], 0, (g, o, d))

    def test_still_not_routed(self):
        # no page read names a port for these ends: they stay "sea, not routed"
        for g, o, d in (("refined-products", "TKM", "TUR"), ("potash", "UZB", "BRA"), ("coal", "USA", "SVK")):
            r = pair(g, o, d)
            self.assertEqual((r["m"], r["load"]), (1, -1), (g, o, d))


class SpodumeneRoute(unittest.TestCase):
    def test_route_and_lanes_agree_on_the_principal_load_port(self):
        defs = load(os.path.join(ROOT, "pipeline", "freight", "routes_def.json"))
        r = next(x for x in (defs if isinstance(defs, list) else defs["routes"]) if x["id"] == "australia-china-spodumene")
        self.assertEqual(r["from"]["ports"][0]["name"], "Bunbury")
        self.assertEqual(P.candidates("AUS", "spodumene", "load")[0][0], "AUBUY")
        self.assertEqual(P.port("AUBUY")["name"].lower(), "bunbury")


if __name__ == "__main__":
    unittest.main()
