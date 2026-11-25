"""Tests of package NC3 (audit A-010): the metal bulks that were missing, as customs groups and pages: ferrous scrap, chromium (chromite),
ferro-alloys, pig iron with direct-reduced iron, coke on the metallurgical coal page, molybdenum and graphite. The codes of each group, one home per
code, the totals of the pages against the cache, the engine's families and classes, the generated-route cap, the pages and their links, and the totals
of every group that existed before (the fertilisers of NC1 and the grains of NC2 included): the steel group above all must not move.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The tests of the data files read the files as the builders last wrote them.
"""
import csv
import gzip
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))

import build_commodities as B  # noqa: E402
import generated_routes as GR  # noqa: E402
import hs_map  # noqa: E402
import modes  # noqa: E402
import ports  # noqa: E402
import vessel_rules as VR  # noqa: E402

DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz")
PRODUCT_CODES = os.path.join(ROOT, "raw", "baci", "product_codes_HS92_V202601.csv")

# group -> (HS 1992 codes, page that holds it, key stem of its tables on that page or None for the page's own, has lanes)
NEW = {
    "ferrous-scrap": (["720410", "720421", "720429", "720430", "720441", "720449", "720450"], "ferrous-scrap", None, True),
    "pig-iron": (["720110", "720120", "720130", "720140"], "pig-iron", None, True),
    "dri": (["720310", "720390"], "pig-iron", "dri", True),
    "chromium-ore": (["261000"], "chromium", None, True),
    "coke": (["270400"], "met-coal", "coke-customs", True),
    "ferro-chromium": (["720241", "720249"], "ferro-alloys", None, True),
    "ferro-manganese": (["720211", "720219"], "ferro-alloys", "ferro-manganese", True),
    "silico-manganese": (["720230"], "ferro-alloys", "silico-manganese", True),
    "ferro-silicon": (["720221", "720229"], "ferro-alloys", "ferro-silicon", True),
    "ferro-alloys-other": (["720250", "720270", "720280", "720291", "720292", "720293", "720299"], "ferro-alloys", "ferro-alloys-other", False),
    "molybdenum-ore": (["261310", "261390"], "molybdenum", None, False),
    "graphite": (["250410", "250490"], "graphite", None, False),
}
LANES = [g for g, v in NEW.items() if v[3]]
ALLOYS = ("ferro-chromium", "ferro-manganese", "silico-manganese", "ferro-silicon", "ferro-alloys-other")

# Tonnes of every group that existed before A-010 in the customs cache, the fertiliser groups of NC1 and the grain groups of NC2 included:
# (all years, 2024), as the cache held them before the metal bulks were added. A new group must not move any of them (the cache is extracted
# again from the same archive). "steel" is chapter 72 without headings 7201 to 7205.
BEFORE = {
    "alumina": (778188953, 37134300),
    "aluminium": (555958370, 30394465),
    "ammonia": (427460708, 18386284),
    "ammonium-nitrate": (210748602, 8412438),
    "ammonium-sulphate": (277833751, 21343612),
    "barley": (735955557, 38895827),
    "bauxite": (1959366876, 183459438),
    "brewing-distilling-dregs": (225699805, 15078584),
    "chocolate": (114952816, 6647520),
    "coal": (29362411247, 1608522209),
    "cobalt": (9532268, 726498),
    "cocoa": (77920473, 3235311),
    "cocoa-butter": (19252455, 1179584),
    "cocoa-paste": (19658801, 1250162),
    "cocoa-powder": (16957965, 1062616),
    "coffee": (152142325, 7691801),
    "coffee-roasted": (20696190, 1325795),
    "coffee-soluble": (19634381, 1257940),
    "copper-ore": (705695221, 35208748),
    "copper-refined": (251461601, 12081479),
    "corn": (3171583690, 183683046),
    "cotton": (194596151, 8632286),
    "crude-oil": (49742865044, 2387545727),
    "dap": (339353288, 18489565),
    "diamonds": (28444, 41),
    "gold": (316970, 9566),
    "iron-ore": (28685363848, 1707219754),
    "lead-metal": (68147334, 3714416),
    "lead-ore": (68813515, 3171678),
    "lithium": (3743479, 504329),
    "lng": (6316373531, 378970438),
    "lpg": (2189094496, 143181624),
    "manganese": (673440759, 43331907),
    "minerals-nes": (225675983, 12312362),
    "monoammonium-phosphate": (211854491, 14145820),
    "natural-gas": (9144031568, 330536312),
    "nickel-fe": (57706923, 10071642),
    "nickel-int": (42576057, 3423960),
    "nickel-ore": (968571886, 52855170),
    "npk": (359703067, 17038452),
    "palm-oil": (892371157, 42945320),
    "pgm": (38321, 1454),
    "phosphate-rock": (782705033, 35843109),
    "phosphoric-acid": (146850968, 7134829),
    "potash": (1085904984, 62663307),
    "potassium-sulphate": (42758452, 1603136),
    "pulses": (344500986, 24015353),
    "rapeseed": (418977117, 25004262),
    "rapeseed-meal": (220574422, 14474686),
    "rapeseed-oil": (145909698, 10392992),
    "rare-earths": (2949980, 238971),
    "refined-products": (23373609696, 1181721821),
    "rice": (1000984502, 61428044),
    "silver": (1449218, 53264),
    "sorghum": (171707216, 10057843),
    "soybeans": (2597546540, 171413838),
    "soymeal": (1453980628, 73814909),
    "soyoil": (272531324, 13148218),
    "spodumene": (27841330, 5039338),
    "steel": (8954583278, 382468256),
    "sugar": (1356087347, 68895223),
    "sulphur": (732905795, 45818492),
    "sunflower-meal": (166595315, 11500772),
    "sunflower-oil": (217014053, 17698466),
    "sunflower-seed": (107793420, 5323228),
    "superphosphates": (134184936, 7840127),
    "tin-metal": (6830323, 221903),
    "tin-ore": (4402404, 123879),
    "uan": (154794671, 6718400),
    "uranium": (2515794, 89198),
    "urea": (1024459899, 56171468),
    "wheat": (4028949013, 195431249),
    "wheat-flour": (263182003, 13073548),
    "wood": (2295515354, 82247622),
    "zinc-metal": (129384987, 10056526),
    "zinc-ore": (254252648, 11424117),
}


def load(rel):
    with open(os.path.join(DATA, rel), encoding="utf-8") as f:
        return json.load(f)


def cache_totals():
    out = {}
    with gzip.open(CACHE, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            g, y, t = r["group"], int(r["year"]), float(r["t"] or 0)
            a = out.setdefault(g, [0.0, 0.0, {}])
            a[0] += t
            a[2][y] = a[2].get(y, 0.0) + t
    return out


class CodesTests(unittest.TestCase):
    def test_each_group_holds_the_intended_codes(self):
        for g, (codes, _, _, _) in NEW.items():
            self.assertEqual(hs_map.HS[g], codes, g)

    def test_no_code_is_in_two_groups(self):
        seen = {}
        for g, codes in hs_map.HS.items():
            for c in codes:
                if c.endswith("*"):
                    continue
                self.assertNotIn(c, seen, f"{c} is in {seen.get(c)} and {g}")
                seen[c] = g

    @unittest.skipUnless(os.path.exists(PRODUCT_CODES), "the HS 1992 product list is not on disk")
    def test_every_code_is_in_the_official_list_with_the_wording_the_pages_use(self):
        with open(PRODUCT_CODES, encoding="utf-8") as f:
            words = {r["code"].zfill(6): r["description"].lower() for r in csv.DictReader(f)}
        for g, (codes, _, _, _) in NEW.items():
            for c in codes:
                self.assertIn(c, words, (g, c))
        for c in hs_map.HS["ferrous-scrap"]:
            self.assertTrue("ferrous waste and scrap" in words[c] or "remelting scrap ingots" in words[c], c)  # 720450 is in heading 7204
        for c in hs_map.HS["pig-iron"]:
            self.assertIn("pig iron" if c != "720140" else "spiegeleisen", words[c], c)
        for c in hs_map.HS["dri"]:
            self.assertTrue("direct reduction" in words[c] or "spongy ferrous" in words[c], c)  # 720390 is not only direct-reduced iron: the page says so
        self.assertIn("chromium ores", words["261000"])
        self.assertIn("coke and semi-coke", words["270400"])
        for c in hs_map.HS["molybdenum-ore"]:
            self.assertIn("molybdenum ores", words[c], c)
        for c in hs_map.HS["graphite"]:
            self.assertIn("graphite: natural", words[c], c)
        self.assertIn("ferro-nickel", words["720260"])

    @unittest.skipUnless(os.path.exists(PRODUCT_CODES), "the HS 1992 product list is not on disk")
    def test_a_whole_heading_is_loaded_where_the_group_says_so(self):
        """Heading 7204 and 7201 are loaded whole; heading 7202 is loaded whole except ferro-nickel, which stays in nickel-fe; 7203 whole."""
        with open(PRODUCT_CODES, encoding="utf-8") as f:
            codes = [r["code"].zfill(6) for r in csv.DictReader(f)]
        loaded = {c: g for g, cs in hs_map.HS.items() for c in cs}
        for head, groups in (("7201", {"pig-iron"}), ("7203", {"dri"}), ("7204", {"ferrous-scrap"})):
            for c in (c for c in codes if c.startswith(head)):
                self.assertIn(loaded.get(c), groups, c)
        for c in (c for c in codes if c.startswith("7202")):
            self.assertEqual(loaded.get(c), "nickel-fe" if c == "720260" else loaded.get(c), c)
            self.assertIn(loaded.get(c), set(ALLOYS) | {"nickel-fe"}, c)
        self.assertEqual(hs_map.HS["nickel-fe"], ["720260"])

    def test_the_steel_group_still_leaves_out_headings_7201_to_7205(self):
        exact, prefixes = hs_map.build_lookup()
        for c in ("720110", "720241", "720310", "720449", "720510", "720529"):
            self.assertNotEqual(hs_map.group_of(c, exact, prefixes), "steel", c)
        self.assertEqual(hs_map.group_of("720510", exact, prefixes), None)
        self.assertEqual(hs_map.group_of("720421", exact, prefixes), "ferrous-scrap")
        self.assertEqual(hs_map.group_of("720260", exact, prefixes), "nickel-fe")
        self.assertEqual(hs_map.group_of("720610", exact, prefixes), "steel")

    def test_the_labels_say_what_the_code_holds(self):
        import build_lanes as BL
        import checks
        self.assertIn("spongy", BL.LABEL["dri"].lower())
        self.assertEqual(checks.label("dri"), "direct-reduced iron")
        self.assertEqual(BL.LABEL["coke"], "Coke and semi-coke")
        self.assertIn("chromite", BL.LABEL["chromium-ore"])


class EngineTests(unittest.TestCase):
    FAMILY = {"chromium-ore": "drybulk", "coke": "drybulk", "ferrous-scrap": "metal", "pig-iron": "metal", "dri": "metal",
              "ferro-chromium": "metal", "ferro-manganese": "metal", "silico-manganese": "metal", "ferro-silicon": "metal"}
    SEGMENT = {"chromium-ore": "ore", "ferrous-scrap": "box", "pig-iron": "box", "dri": "box", "coke": "coal",
               "ferro-chromium": "box", "ferro-manganese": "box", "silico-manganese": "box", "ferro-silicon": "box"}

    def test_every_group_that_sails_has_a_mode_a_segment_and_a_page(self):
        import build_lanes as BL
        for g in LANES:
            self.assertEqual(modes.family_of(g), self.FAMILY[g], g)
            self.assertEqual(ports.segment(g), self.SEGMENT[g], g)
            self.assertIn(g, BL.GROUPS)
            self.assertIn(g, BL.CAP)
            self.assertEqual(BL.COMMODITY.get(g, g), NEW[g][1], g)

    def test_the_groups_without_lanes_are_in_no_lane_table(self):
        import build_lanes as BL
        for g in ("ferro-alloys-other", "molybdenum-ore", "graphite"):
            self.assertNotIn(g, BL.GROUPS)
            self.assertNotIn(g, modes.FAMILY)
            self.assertFalse(os.path.exists(os.path.join(DATA, "freight", "lanes", g + ".json")), g)
            self.assertFalse(os.path.exists(os.path.join(DATA, "freight", "pairs", g + ".json")), g)

    def test_the_bulks_sail_in_handy_bulk_carriers_and_the_ferro_alloys_in_boxes(self):
        for g in ("ferrous-scrap", "chromium-ore", "pig-iron", "dri", "coke"):
            self.assertEqual(VR.classes(g, "ZAF", "CHN", 1e6, 7000), ["supramax", "handysize"], g)
        for g in ("ferro-chromium", "ferro-manganese", "silico-manganese", "ferro-silicon"):
            self.assertEqual(VR.classes(g, "NOR", "USA", 0.1e6, 3500), ["container", "handysize"], g)

    def test_the_ports_are_the_engines_own_fall_backs(self):
        """No port was attached to these cargoes: coke takes only a row that names it, the box rows of scrap, pig iron, DRI and the ferro-alloys are the
        general port of the country (Turkey's scrap goes to Izmir, not to the Black Sea)."""
        self.assertIn("coke", ports.OWN_FAMILY)
        for g in ("ferrous-scrap", "pig-iron", "dri", "ferro-chromium", "ferro-manganese", "silico-manganese", "ferro-silicon"):
            self.assertIn(g, ports.BOX_GENERAL)
        for iso, rows in ports.G.items():
            for r in rows:
                if iso == "TUR" and r.code in ("TRERE", "TRISK"):
                    # FNCA (review GNC3.2): the two steel works of Turkey, named by the Erdemir page, are rows of the three steel-input groups only
                    self.assertEqual(set(r.families), {"ferrous-scrap", "pig-iron", "dri"}, r)
                    continue
                self.assertFalse(r.families & set(NEW), r)

    def test_the_vessel_type_of_the_chokepoint_estimates(self):
        import build_freight as BF
        for g in ("ferrous-scrap", "chromium-ore", "pig-iron", "dri", "coke"):
            self.assertEqual(BF.vessel_type(g), "dry", g)
        for g in ("ferro-chromium", "ferro-silicon"):
            self.assertEqual(BF.vessel_type(g), "cargo", g)
        self.assertTrue(BF.DRY_BOX <= {g for g, s in ports.SEGMENT.items() if s == "box"})

    def test_the_classes_the_lanes_name_list_the_new_pages_among_their_cargoes(self):
        with open(os.path.join(ROOT, "pipeline", "freight", "vessel_classes.json"), encoding="utf-8") as f:
            cl = {c["id"]: c for c in json.load(f)}
        for k in ("ferrous-scrap", "chromium", "pig-iron", "met-coal"):
            self.assertIn(k, cl["supramax"]["cargoes"], k)
            self.assertIn(k, cl["handysize"]["cargoes"], k)
        self.assertIn("ferro-alloys", cl["container"]["cargoes"])

    def test_the_new_groups_have_a_route_cap_of_their_own_of_ten(self):
        """A-010: 10 generated routes for the whole package; the corridors kept for the earlier groups do not move (generated_routes.LATER_GROUPS)."""
        mine = next((gs, cap) for gs, cap in GR.LATER_GROUPS if "ferrous-scrap" in gs)
        self.assertEqual(mine[1], 10)
        self.assertEqual(mine[0], frozenset(LANES) - {"ferro-alloys-other"})
        self.assertTrue(mine[0].isdisjoint(GR.AUDIT_GROUPS))
        for gs, _ in GR.LATER_GROUPS:
            if gs is not mine[0]:
                self.assertTrue(gs.isdisjoint(mine[0]))

    def test_the_generated_routes_of_the_package_are_at_most_ten_and_no_earlier_route_is_among_them(self):
        routes = load("freight/routes.json")
        gen = [r for r in routes if r.get("generated")]
        ids = [r["id"] for r in gen if r["id"].startswith(tuple(f"gen-{g}-" for g in LANES))]
        self.assertTrue(1 <= len(ids) <= 10, ids)
        # the first package: the cap of 120, or the routes of the last release when they are more (they stay whatever the cap: generated_routes.select_group);
        # + the 6 routes of package FNCB (ammonium nitrate with limestone, the two-nutrient compounds)
        first = max(GR.TOTAL_CAP, len([i for i in GR.released_routes() if not GR.is_later_route(i)]))
        self.assertEqual(len(gen), first + 20 + 10 + len(ids) + 6)
        self.assertEqual(len({r["id"] for r in routes}), len(routes))


@unittest.skipUnless(os.path.exists(CACHE), "customs cache not on disk")
class CacheTests(unittest.TestCase):
    totals = cache_totals() if os.path.exists(CACHE) else {}

    def test_the_groups_that_existed_before_have_not_moved_by_a_tonne(self):
        for g, (allyears, latest) in BEFORE.items():
            self.assertEqual(round(self.totals[g][0]), allyears, g)
            self.assertEqual(round(self.totals[g][2][2024]), latest, g)

    def test_steel_has_not_moved_by_a_tonne(self):
        self.assertEqual(round(self.totals["steel"][0]), 8954583278)
        self.assertEqual(round(self.totals["steel"][2][2024]), 382468256)

    def test_every_new_group_is_in_the_cache_for_the_latest_year(self):
        for g in NEW:
            self.assertGreater(self.totals[g][2][2024], 3e5, g)

    def test_the_cache_holds_the_groups_before_and_the_new_ones_only(self):
        # + the two fertiliser groups of package FNCB (review GNC1.4)
        self.assertEqual(set(self.totals), set(BEFORE) | set(NEW) | {"ammonium-nitrate-limestone", "npk-two-nutrient"})


class PageTests(unittest.TestCase):
    def table(self, g, side):
        page, stem = NEW[g][1], NEW[g][2]
        d = load(f"commodities/{page}.json")
        if stem is None:
            return d[side]
        return next(x["table"] for x in d["extra"] if x["key"] == f"{stem}-{side}")

    @unittest.skipUnless(os.path.exists(CACHE), "customs cache not on disk")
    def test_the_world_total_of_a_table_is_its_group_in_the_cache(self):
        """The table is the group's flows of 2024 in the cache after the shared cleaning rules (pipeline/trade/clean.py); the raw sum of the
        cache is within 3% of it (a tonnage missing in the archive is estimated from its value)."""
        import pandas as pd
        from clean import clean
        from clean import DROP
        df = pd.read_csv(CACHE)
        df = df[df["group"].isin(NEW)]
        cleaned = clean(df)
        for g in NEW:
            want = cleaned[(cleaned["group"] == g) & (cleaned["year"] == 2024)]["t"].sum() / 1e6
            # the rows that clean() drops as misclassified (Mozambique's coke, FNCF) are in the cache and in no table
            out = pd.Series(False, index=df.index)
            for (dg, do, dd), _ in DROP.items():
                out |= (df["group"] == dg) & (df["o"] == do) & ((df["d"] == dd) if dd else True)
            kept = df[~out]
            raw = kept[(kept["group"] == g) & (kept["year"] == 2024)]["t"].sum() / 1e6
            self.assertLess(abs(raw - want) / want, 0.03, (g, raw, want))
            for side in ("exports", "imports"):
                t = self.table(g, side)
                self.assertEqual((t["y"], t["s"]), (2024, "baci"))
                div = 1e3 if t["u"] == "kt" else 1.0
                self.assertAlmostEqual(t["world"] / div, want, delta=max(0.0006 * want, 0.0006), msg=(g, side))
                self.assertLessEqual(sum(r["v"] for r in t["rows"]), t["world"] * 1.0005, (g, side))

    def test_the_ferro_alloys_page_holds_every_code_of_heading_7202_but_ferro_nickel_once(self):
        d = load("commodities/ferro-alloys.json")
        tot = sum(self.table(g, "exports")["world"] for g in ALLOYS)
        want = sum(load(f"freight/lanes/{g}.json")["world"][-1] for g in ALLOYS if g != "ferro-alloys-other") + self.table("ferro-alloys-other", "exports")["world"]
        self.assertAlmostEqual(tot, want, delta=0.02)  # lane files and tables round their world totals to the thousandth of a Mt
        nickel = load("commodities/nickel.json")
        self.assertTrue(any(x["key"] == "ferro-exports" for x in nickel["extra"]))
        keys = {x["key"] for x in d["extra"]}
        self.assertFalse(any("nickel" in k for k in keys))
        self.assertTrue(any("HS 7202 other than ferro-nickel" in n for n in d["notes"]))
        self.assertEqual(len([x for x in d["extra"] if x["key"].endswith("-exports")]), 4)

    def test_the_chromium_page_has_the_usgs_tables_with_their_measures(self):
        d = load("commodities/chromium.json")
        self.assertEqual((d["production"]["s"], d["production"]["u"], d["production"]["y"]), ("usgs-mcs", "Mt", 2025))
        self.assertEqual(d["production"]["basis"], "chromite ore, gross weight")
        self.assertEqual((d["reserves"]["u"], d["reserves"]["basis"]), ("Mt Cr2O3", "Cr2O3 content"))
        self.assertTrue(any("Cr2O3 content" in n and "2024" in n for n in d["notes"]))
        self.assertEqual(d["exports"]["rows"][0]["c"], "ZAF")

    def test_the_pig_iron_page_has_the_usgs_table_and_the_dri_tables_beside_it(self):
        d = load("commodities/pig-iron.json")
        self.assertEqual((d["production"]["s"], d["production"]["u"]), ("usgs-mcs", "Mt"))
        self.assertEqual(d["production"]["rows"][0]["c"], "CHN")
        self.assertEqual({x["key"] for x in d["extra"]}, {"dri-exports", "dri-imports"})
        self.assertTrue(any("No production table for it" in n for n in d["notes"]))

    def test_the_scrap_page_has_no_production_table_and_says_so(self):
        d = load("commodities/ferrous-scrap.json")
        self.assertNotIn("production", d)
        self.assertTrue(any(n.startswith("No production table") for n in d["notes"]))
        self.assertEqual(d["us"]["s"], "usgs-mcs")  # the one figure of the file: the United States

    def test_the_molybdenum_and_graphite_pages_have_usgs_tables_and_no_lanes(self):
        for k, u in (("molybdenum", "kt Mo"), ("graphite", "kt")):
            d = load(f"commodities/{k}.json")
            self.assertEqual((d["production"]["s"], d["production"]["u"]), ("usgs-mcs", u))
            self.assertIn("reserves", d)
            self.assertTrue(any(n.startswith("No lanes") for n in d["notes"]), k)

    def test_coke_is_a_group_of_the_metallurgical_coal_page_and_coal_did_not_move(self):
        d = load("commodities/met-coal.json")
        keys = {x["key"] for x in d["extra"]}
        self.assertTrue({"coke-customs-exports", "coke-customs-imports", "coke-production", "coke-exports", "coke-imports"} <= keys)
        t = next(x["table"] for x in d["extra"] if x["key"] == "coke-customs-exports")
        self.assertEqual(t["s"], "baci")
        self.assertEqual(load("freight/lanes/coal.json")["group"], "coal")
        self.assertEqual(round(CacheTests.totals["coal"][2][2024]), BEFORE["coal"][1])

    def test_the_pages_are_in_the_index_and_say_what_they_hold(self):
        idx = {e["id"]: e for e in load("commodities/index.json")}
        for k in ("ferrous-scrap", "pig-iron", "chromium", "ferro-alloys", "molybdenum", "graphite"):
            e = idx[k]
            self.assertEqual((e["family"], e.get("sub")), ("metals", None), k)
            self.assertTrue(e["name"] and e["blurb"])
            self.assertFalse(any(ch.isdigit() for ch in e["blurb"]), "a blurb carries no figure")
        self.assertIn("2704", idx["met-coal"]["hs"])
        self.assertNotIn("720260", idx["ferro-alloys"]["hs"])
        self.assertIn("720260", idx["nickel"]["hs"])
        self.assertEqual(sorted(e["rank"] for e in idx.values()), list(range(len(idx))))
        order = [e["id"] for e in sorted(idx.values(), key=lambda e: e["rank"])]
        metals = [k for k in order if idx[k]["family"] == "metals"]
        self.assertEqual(metals.index("ferrous-scrap"), metals.index("steel") + 1)
        self.assertEqual(metals.index("ferro-alloys"), metals.index("chromium") + 1)

    def test_the_links_between_pages_point_at_pages(self):
        idx = {e["id"] for e in load("commodities/index.json")}
        want = {"chromium": "ferro-alloys", "manganese": "ferro-alloys", "nickel": "ferro-alloys"}
        for k, to in want.items():
            see = load(f"commodities/{k}.json").get("see", [])
            self.assertEqual([s["k"] for s in see if s["k"] == to], [to], k)
        for k in ("ferro-alloys", "ferrous-scrap", "pig-iron", "chromium", "molybdenum"):
            for s in load(f"commodities/{k}.json").get("see", []):
                self.assertIn(s["k"], idx)
                self.assertNotEqual(s["k"], k)
        self.assertIn("nickel", [s["k"] for s in load("commodities/ferro-alloys.json")["see"]])

    def test_the_new_pages_have_a_price_only_where_the_usgs_file_has_one_and_the_others_say_so(self):
        # FNCC (GNC3.5): the USGS annual prices of five of the pages are published (test_fncc.py C3); pig iron has none
        fig = load("prices/figures.json")
        for k in ("ferrous-scrap", "chromium", "ferro-alloys", "molybdenum", "graphite"):
            self.assertEqual(fig[k]["s"], "usgs-mcs", k)
            d = load(f"commodities/{k}.json")
            self.assertFalse(any("No free price series" in n for n in d["notes"]), k)
        self.assertNotIn("pig-iron", fig)
        self.assertTrue(any("No free price series" in n for n in load("commodities/pig-iron.json")["notes"]))


class LaneAndProfileTests(unittest.TestCase):
    def test_every_group_that_sails_has_lanes_under_its_page(self):
        for g in LANES:
            f = load(f"freight/lanes/{g}.json")
            self.assertEqual(f["k"], NEW[g][1], g)
            self.assertTrue(f["lanes"], g)
            self.assertGreaterEqual(f["coverage"]["share"], 0.63, g)
            self.assertTrue(os.path.exists(os.path.join(DATA, "freight", "pairs", g + ".json")), g)

    def test_the_lanes_of_the_bulks_are_carried_by_dry_bulk_ships_and_the_alloys_by_container_ships(self):
        for g in ("ferrous-scrap", "pig-iron", "dri", "chromium-ore", "coke"):
            for lane in load(f"freight/lanes/{g}.json")["lanes"]:
                self.assertEqual(lane["vclass"], ["supramax", "handysize"], (g, lane["id"]))
        for g in ("ferro-chromium", "ferro-silicon"):
            for lane in load(f"freight/lanes/{g}.json")["lanes"]:
                self.assertEqual(lane["vclass"], ["container", "handysize"], (g, lane["id"]))

    def test_the_scrap_that_turkey_imports_goes_to_the_steel_works_not_to_samsun(self):
        """The first importer of scrap: the "ore" fall-backs had sent it to Samsun by the Bosphorus; the general port of the country (Mersin) refused
        the Black Sea flows (FNCA, review GNC3.2). Since FNCA the cargo of the Black Sea partners goes to Karadeniz Eregli, where the page names the
        steel works, and the cargo of the others to Iskenderun, the other steel works: no lane crosses the Bosphorus and none goes to Samsun."""
        f = load("freight/lanes/ferrous-scrap.json")
        turkish = [ln for ln in f["lanes"] if ln["d"] == "TUR"]
        self.assertTrue(turkish)
        for ln in turkish:
            self.assertNotIn("bosphorus", ln["via"], ln["id"])
            port = ln["discharge"][0]
            self.assertNotEqual(port, "TRSSX", ln["id"])
            self.assertEqual(port, "TRERE" if ln["o"] in ("RUS", "UKR", "ROU", "BGR", "GEO", "MDA") else "TRISK", ln["id"])
            # the page names the steel works, not the cargo (package FNCE: the basis says so, the source link stays)
            self.assertEqual(f["ports"][port]["basis"], "page names the plant, not the cargo", ln["id"])
            self.assertEqual(f["ports"][port]["s"], "wikipedia", ln["id"])

    def test_south_africa_exports_chromite_and_ferro_chromium_first(self):
        zaf = load("countries/profiles/ZAF.json")
        lines = {(e["k"], e.get("label")): e for e in zaf["exports"]}
        self.assertEqual(lines[("chromium", "Chromium ore")]["rank"], 1)
        self.assertEqual(lines[("ferro-alloys", "Ferro-chromium")]["rank"], 1)

    def test_turkey_is_the_first_importer_of_scrap_and_india_of_coke(self):
        tur = load("countries/profiles/TUR.json")
        self.assertEqual({(e["k"]): e for e in tur["imports"]}["ferrous-scrap"]["rank"], 1)
        ind = load("countries/profiles/IND.json")
        coke = [e for e in ind["imports"] if e["k"] == "met-coal" and e.get("label") == "Coke and semi-coke (customs data)"]
        self.assertEqual(len(coke), 1)
        self.assertEqual(coke[0]["rank"], 1)


if __name__ == "__main__":
    unittest.main()
