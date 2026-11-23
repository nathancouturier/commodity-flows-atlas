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
        # review GL1.11: the pages bound the rail share (9% of 2025 exports through Russia, to China and the CIS together),
        # so Belarus to China is a seaborne transit pair again, and the rail fact is in the caveat of the registry
        self.assertEqual(MD.mode_of("BLR", "CHN", "potash").kind, "transit")
        self.assertNotIn(("BLR", "CHN"), MD.MIXED)
        self.assertEqual(EN.transit("BLR", "fert")[0], "RULED")
        self.assertEqual(MD.mode_of("BLR", "BRA", "potash").kind, "transit")
        import caveats as CV
        entry = next(e for e in CV.REGISTRY if e[0] == "potash-blr")
        self.assertIsNone(entry[4])  # every destination of Belarus

    def test_transit_rows_of_l1(self):
        for iso3, fam, code in (("AUT", "drybulk", "SIKOP"), ("HUN", "metal", "SIKOP"), ("SRB", "grain", "ROCND"),
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
        # rows keyed by cargo since review GL1: Kazakh coal (not every dry bulk), Paraguayan soy and corn (not every grain)
        self.assertIsNone(EN.transit("KAZ", "drybulk"))
        self.assertIsNone(EN.transit("PRY", "grain"))


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
        # review GL1.9: a group under 1 Mt a year is published in kt with 0.1 kt, the unit its commodity page prints
        f = load(os.path.join(LANES, "tin-metal.json"))
        self.assertEqual(f["unit"], "kt")
        self.assertLess(f["seaborne"][-1], 1000)
        self.assertTrue(all(ln["flow"]["u"] == "kt" for ln in f["lanes"]))
        self.assertTrue(any(round(ln["flow"]["v"]) != ln["flow"]["v"] for ln in f["lanes"]))
        p = load(os.path.join(PAIRS, "tin-metal.json"))
        # the pairs total is the sum of its rows (0.1 kt each): within half a kilotonne of the exact total
        self.assertAlmostEqual(f["seaborne"][-1], p["seaborne"], delta=0.5)
        for g in NEW:
            f = load(os.path.join(LANES, g + ".json"))
            self.assertEqual(f["unit"], "kt" if load(os.path.join(PAIRS, g + ".json"))["seaborne"] < 1000 else "Mt", g)

    def test_belarusian_potash_lanes(self):
        ln = lane("potash:BLR-CHN")
        self.assertIsNone(ln.get("mode"))
        self.assertEqual(ln["transit"]["port"], "RULED")
        self.assertTrue(ln["transit"]["landlocked"])
        self.assertGreater(ln["share"], 0)
        self.assertEqual(ln.get("caveat"), "potash-blr")
        r = pair("potash", "BLR", "CHN")
        self.assertEqual((r["m"], r["load_code"]), (1, "RULED"))
        r = pair("potash", "BLR", "BRA")
        self.assertEqual((r["m"], r["load_code"]), (1, "RULED"))

    def test_landlocked_pairs_now_routed(self):
        for g, o, d, end, code in (("coal", "KAZ", "MAR", "load", "RUULU"), ("coal", "KAZ", "ITA", "load", "RUULU"),
                                   ("soymeal", "PRY", "PER", "load", "ARUPR"), ("soybeans", "PRY", "RUS", "load", "UYNVP"),
                                   ("corn", "PRY", "KOR", "load", "UYNVP"),
                                   ("coal", "USA", "AUT", "dis", "SIKOP"), ("copper-ore", "SRB", "CHN", "load", "ROCND"),
                                   ("copper-ore", "BWA", "CHN", "load", "NAWVB")):
            r = pair(g, o, d)
            self.assertIsNotNone(r, (g, o, d))
            self.assertEqual(r["m"], 1, (g, o, d))
            self.assertEqual(r[end + "_code"], code, (g, o, d))
            self.assertGreater(r["nm"], 0, (g, o, d))

    def test_still_not_routed(self):
        # no page read names a port for these ends: they stay "sea, not routed"
        for g, o, d in (("refined-products", "TKM", "TUR"), ("potash", "UZB", "BRA"), ("coal", "USA", "SVK"),
                        # review GL1.1 and GL1.2: the pages name no port for these
                        ("coal", "KAZ", "TUR"), ("coal", "KAZ", "IND"), ("coal", "KAZ", "JPN"), ("rice", "PRY", "TUR")):
            r = pair(g, o, d)
            self.assertEqual((r["m"], r["load"]), (1, -1), (g, o, d))


class ReviewGL1(unittest.TestCase):
    """Package FL1, the fixes after review GL1 (no build needed)."""

    def test_kazakh_coal_only_for_the_buyers_the_page_names(self):
        # GL1.1: Morocco from Ust-Luga, the EU as one of Ust-Luga and Novorossiysk, nobody else
        self.assertEqual(BL.transit_row("KAZ", "coal", "MAR")["ports"], ["RUULU"])
        self.assertEqual(BL.transit_row("KAZ", "coal", "ITA")["ports"], ["RUULU", "RUNVS"])
        for d in ("TUR", "ISR", "IND", "TWN", "JPN", "BIH"):
            self.assertIsNone(BL.transit_row("KAZ", "coal", d), d)
        self.assertIsNone(BL.transit_row("KAZ", "alumina", "CHN"))
        self.assertEqual(BL.transit_row("KAZ", "crude-oil", "ITA")["port"], "KZCPC")
        rec, why = BL.route_pair("KAZ", "ITA", "coal", 1e5, "transit")
        self.assertEqual((rec["basis"], [o[0] for o in rec["opts"]]), ("open", ["RUULU", "RUNVS"]))
        self.assertEqual(BL.route_pair("KAZ", "TUR", "coal", 1e5, "transit"), (None, "no sourced transit port"))

    def test_eu_list_is_the_one_of_the_commodity_builder(self):
        with open(os.path.join(ROOT, "pipeline", "commodities", "build_commodities.py"), encoding="utf-8") as f:
            src = f.read()
        m = re.search(r"EU_MEMBERS = \[([^\]]+)\]", src)
        self.assertEqual(EN.EU, frozenset(re.findall(r'"([A-Z]{3})"', m.group(1))))

    def test_paraguay_rows_by_cargo(self):
        # GL1.2: Rosario for meal and oil, Nueva Palmira for soybeans and corn, no row for wheat, rice and sugar
        self.assertEqual(BL.transit_row("PRY", "soymeal", "PER")["ports"], ["ARUPR", "UYNVP"])
        self.assertEqual(BL.transit_row("PRY", "soyoil", "CHL")["ports"], ["ARUPR"])
        self.assertEqual(BL.transit_row("PRY", "soybeans", "CHN")["ports"], ["UYNVP", "ARUPR"])
        self.assertEqual(BL.transit_row("PRY", "corn", "KOR")["ports"], ["UYNVP"])
        for g in ("wheat", "rice", "sugar"):
            self.assertIsNone(BL.transit_row("PRY", g, "TUR"), g)
        self.assertEqual(P.port("UYNVP")["c"], "URY")
        self.assertEqual(P.port_meta("UYNVP")["url"], "https://en.wikipedia.org/wiki/Nueva_Palmira")
        for g in ("soymeal", "soybeans", "corn", "soyoil"):
            self.assertIn("2016", P.TRANSIT["PRY"][g][3], g)

    def test_a_cargo_row_names_its_cargo(self):
        # GL1.13: the Belarusian row names potash; other fertilisers of Belarus take its port as a general port
        self.assertEqual(BL.transit_row("BLR", "potash", "CHN")["basis"], P.BASIS_PAGE)
        self.assertEqual(BL.transit_row("BLR", "urea", "IND")["basis"], P.BASIS_GENERAL)
        self.assertEqual(BL.transit_row("SRB", "copper-ore", "CHN")["basis"], P.BASIS_GENERAL)

    def test_box_rows_are_general_ports_for_the_minor_metals(self):
        # GL1.6: a page that names containers or general cargo does not name cobalt, tin or lithium
        for g in P.BOX_GENERAL:
            for c, _, basis in P.candidates("CHN", g, "discharge"):
                if not any(r.code == c and g in r.families for r in P.G.get("CHN", ())):
                    self.assertNotEqual(basis, P.BASIS_PAGE, (g, c))
        self.assertEqual(P.basis_of("CHN", "cobalt", "discharge", "CNTSN"), P.BASIS_GENERAL)
        # the same ports, in the same order, as for refined copper, which keeps its basis
        self.assertEqual([c for c, _, _ in P.candidates("CHN", "cobalt", "discharge")],
                         [c for c, _, _ in P.candidates("CHN", "copper-refined", "discharge")])
        self.assertEqual(P.basis_of("CHN", "copper-refined", "discharge", "CNTSN"), P.BASIS_PAGE)

    def test_no_lane_from_the_wrong_coast(self):
        # GL1.3: Russian lead concentrate and cobalt for East Asia, Turkish lead concentrate from Samsun
        for o, d, g, kind in (("RUS", "CHN", "lead-ore", "mixed"), ("RUS", "KOR", "lead-ore", "sea"), ("RUS", "CHN", "cobalt", "mixed"),
                              ("TUR", "CHN", "lead-ore", "sea"), ("NLD", "FRA", "zinc-metal", "sea")):
            rec, why = BL.route_pair(o, d, g, 1e4, kind)
            self.assertIsNone(rec, (o, d, g))
            self.assertIn(why, ("port on the other coast of the country", "only the nearest seaport, on a long detour"))
        # a long route that geography imposes stays routed (Peru has one coast), and the old groups are not touched
        self.assertIsNotNone(BL.route_pair("PER", "BRA", "zinc-metal", 1e4, "sea")[0])
        self.assertIsNotNone(BL.route_pair("RUS", "KOR", "zinc-ore", 1e4, "sea")[0])

    def test_unit_value_check_covers_the_new_groups(self):
        # GL1.10
        import checks as K
        self.assertTrue(set(NEW) <= set(K.UV_GROUPS))

    def test_no_exponent_in_a_tonnage_of_the_notes(self):
        # GL1.5
        import checks as K
        self.assertEqual(K._mt(5.9e-05), "59 t")
        self.assertEqual(K._mt(0.0077), "0.0077 Mt")
        self.assertEqual(K._mt(0), "0 Mt")
        self.assertNotRegex(K._mt(1.2e-07), "e-")


@need_build
class ReviewGL1Built(unittest.TestCase):
    def test_wording_data_of_transit_ends(self):
        # GL1.7: DR Congo has a coast, Zambia has none (adjacency data)
        self.assertFalse(lane("cobalt:COD-CHN")["transit"]["landlocked"])
        p = load(os.path.join(PAIRS, "cobalt.json"))
        self.assertNotIn("COD", p.get("landlocked", []))
        self.assertIn("ZMB", load(os.path.join(PAIRS, "copper-refined.json")).get("landlocked", []))

    def test_no_exponent_in_published_notes(self):
        bad = []
        for d in (LANES, PAIRS):
            for f in os.listdir(d):
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    txt = fh.read()
                bad += [(f, m) for m in re.findall(r'"[^"]*?\d\.?\d*e-\d+ [Mk]t[^"]*"', txt)]
        self.assertEqual(bad, [])


class SpodumeneRoute(unittest.TestCase):
    def test_route_and_lanes_agree_on_the_principal_load_port(self):
        defs = load(os.path.join(ROOT, "pipeline", "freight", "routes_def.json"))
        r = next(x for x in (defs if isinstance(defs, list) else defs["routes"]) if x["id"] == "australia-china-spodumene")
        self.assertEqual(r["from"]["ports"][0]["name"], "Bunbury")
        self.assertEqual(P.candidates("AUS", "spodumene", "load")[0][0], "AUBUY")
        self.assertEqual(P.port("AUBUY")["name"].lower(), "bunbury")
        # review GL1.12: the note says what the principal port rests on, and that the loading figure is one month
        self.assertIn("technical report", r["notes"])
        self.assertIn("one month", r["notes"])


if __name__ == "__main__":
    unittest.main()
