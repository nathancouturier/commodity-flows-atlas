"""Tests of package NC2 (audit M-023): the grains, oilseeds and products that were missing, as new customs groups of the wheat, corn,
rapeseed pages and of four new pages (barley, sorghum, sunflower, pulses). The codes of each group, one home per code, the totals of the pages
against the cache, the engine's families and classes, the generated-route cap, the pages, their price blocks and their links, and the totals
of every group that existed before (the fertilisers of package NC1 included).

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
import metals  # noqa: E402
import modes  # noqa: E402
import ports  # noqa: E402
import vessel_rules as VR  # noqa: E402

DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz")
PRODUCT_CODES = os.path.join(ROOT, "raw", "baci", "product_codes_HS92_V202601.csv")

# group -> (HS 1992 codes, page that holds it, key stem of its tables on that page or None for the page's own, has lanes)
NEW = {
    "barley": (["100300"], "barley", None, True),
    "sorghum": (["100700"], "sorghum", None, True),
    "sunflower-seed": (["120600"], "sunflower", None, True),
    "sunflower-oil": (["151211", "151219"], "sunflower", "sunflower-oil", True),
    "sunflower-meal": (["230630"], "sunflower", "sunflower-meal", True),
    "rapeseed-oil": (["151410", "151490"], "rapeseed", "rapeseed-oil", True),
    "rapeseed-meal": (["230640"], "rapeseed", "rapeseed-meal", True),
    "pulses": (["071310", "071320", "071331", "071332", "071333", "071339", "071340", "071350", "071390"], "pulses", None, True),
    "wheat-flour": (["110100"], "wheat", "flour", False),
    "brewing-distilling-dregs": (["230330"], "corn", "dregs", False),
}
OILS = ("sunflower-oil", "rapeseed-oil")
NC3_GROUPS = tuple(f"gen-{g}-" for g in ("ferrous-scrap", "chromium-ore", "pig-iron", "dri", "coke", "ferro-chromium", "ferro-manganese",
                                         "silico-manganese", "ferro-silicon"))
LANES = [g for g, v in NEW.items() if v[3]]

# Tonnes of every group that existed before M-023 in the customs cache, the ten groups of the fertilisers of M-022 included: (all years,
# 2024), as the cache held them before the grains were added. A new group must not move any of them (the cache is extracted again from
# the same archive).
BEFORE = {
    "alumina": (778188953, 37134300),
    "aluminium": (555958370, 30394465),
    "ammonia": (427460708, 18386284),
    "ammonium-nitrate": (210748602, 8412438),
    "ammonium-sulphate": (277833751, 21343612),
    "bauxite": (1959366876, 183459438),
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
    "rapeseed": (418977117, 25004262),
    "rare-earths": (2949980, 238971),
    "refined-products": (23373609696, 1181721821),
    "rice": (1000984502, 61428044),
    "silver": (1449218, 53264),
    "soybeans": (2597546540, 171413838),
    "soymeal": (1453980628, 73814909),
    "soyoil": (272531324, 13148218),
    "spodumene": (27841330, 5039338),
    "steel": (8954583278, 382468256),
    "sugar": (1356087347, 68895223),
    "sulphur": (732905795, 45818492),
    "superphosphates": (134184936, 7840127),
    "tin-metal": (6830323, 221903),
    "tin-ore": (4402404, 123879),
    "uan": (154794671, 6718400),
    "uranium": (2515794, 89198),
    "urea": (1024459899, 56171468),
    "wheat": (4028949013, 195431249),
    "wood": (2295515354, 82247622),
    "zinc-metal": (129384987, 10056526),
    "zinc-ore": (254252648, 11424117)
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
        self.assertIn("barley", words["100300"])
        self.assertIn("grain sorghum", words["100700"])
        self.assertIn("sunflower seeds", words["120600"])
        # one code for two oils: the labels of the groups say so
        for c in ("151211", "151219"):
            self.assertIn("sunflower seed or safflower oil", words[c])
        for c in ("151410", "151490"):
            self.assertIn("rape, colza or mustard oil", words[c])
        self.assertIn("sunflower seed oils", words["230630"])
        self.assertIn("rape or colza seed oils", words["230640"])
        self.assertIn("wheat or meslin flour", words["110100"])
        self.assertIn("brewing or distilling dregs", words["230330"])  # the code of distillers' grains holds more than them: the page says so
        for c in hs_map.HS["pulses"]:
            self.assertIn("leguminous", words[c])
        import checks
        self.assertEqual(checks.label("sunflower-oil"), "sunflower and safflower oil")
        self.assertEqual(checks.label("rapeseed-oil"), "rapeseed, canola and mustard oil")
        import build_lanes as BL
        self.assertIn("safflower", BL.LABEL["sunflower-oil"])
        self.assertIn("mustard", BL.LABEL["rapeseed-oil"])

    def test_the_codes_the_pages_leave_out_are_in_no_group(self):
        loaded = {c for codes in hs_map.HS.values() for c in codes}
        for c in ("100400", "100200", "110710", "110720", "110220", "110311", "110811", "120710", "151221", "151229", "230610", "230650", "230660"):
            self.assertNotIn(c, loaded, c)

    def test_the_pulse_kinds_cover_every_code_of_the_group_once(self):
        kinds = [c for codes, _ in metals.SPLITS["pulses"].values() for c in codes]
        self.assertEqual(sorted(kinds), sorted(hs_map.HS["pulses"]))


class EngineTests(unittest.TestCase):
    def test_every_group_that_sails_has_a_mode_a_segment_and_a_page(self):
        import build_lanes as BL
        for g in LANES:
            page = NEW[g][1]
            self.assertEqual(modes.family_of(g), "vegoil" if g in OILS else "grain", g)
            self.assertEqual(ports.segment(g), "vegoil" if g in OILS else "grain", g)
            self.assertIn(g, BL.GROUPS)
            self.assertIn(g, BL.CAP)
            self.assertEqual(BL.COMMODITY.get(g, g), page, g)

    def test_the_products_in_bags_have_no_lanes(self):
        import build_lanes as BL
        for g in ("wheat-flour", "brewing-distilling-dregs"):
            self.assertNotIn(g, BL.GROUPS)
            self.assertFalse(os.path.exists(os.path.join(DATA, "freight", "lanes", g + ".json")), g)

    def test_the_vegetable_oils_sail_in_tankers_and_the_rest_in_dry_bulk(self):
        for g in OILS:
            self.assertEqual(VR.classes(g, "UKR", "IND", 1e6, 6000), ["mr", "chemical-tanker"])
        for g in ("barley", "sorghum", "sunflower-seed", "sunflower-meal", "rapeseed-meal", "pulses"):
            self.assertEqual(VR.classes(g, "UKR", "EGY", 0.5e6, 600), ["supramax", "handysize"], g)
            self.assertEqual(VR.classes(g, "AUS", "CHN", 2e6, 4000), ["kamsarmax", "supramax"], g)

    def test_the_oils_are_compared_with_the_tankers_of_the_chokepoint_estimates(self):
        import build_freight as BF
        for g in OILS:
            self.assertEqual(BF.vessel_type(g), "tanker", g)
        for g in ("barley", "pulses", "sunflower-meal"):
            self.assertEqual(BF.vessel_type(g), "dry", g)

    def test_the_classes_the_lanes_name_list_the_new_pages_among_their_cargoes(self):
        with open(os.path.join(ROOT, "pipeline", "freight", "vessel_classes.json"), encoding="utf-8") as f:
            cl = {c["id"]: c for c in json.load(f)}
        for k in ("barley", "sorghum", "sunflower", "rapeseed", "pulses"):
            self.assertIn(k, cl["supramax"]["cargoes"], k)
        for k in ("sunflower", "rapeseed"):
            self.assertIn(k, cl["mr"]["cargoes"])
            self.assertIn(k, cl["chemical-tanker"]["cargoes"])

    def test_the_new_groups_have_a_route_cap_of_their_own_of_ten(self):
        """M-023: 10 generated routes for the whole package; the corridors kept for the earlier groups do not move (generated_routes.LATER_GROUPS)."""
        mine = next((gs, cap) for gs, cap in GR.LATER_GROUPS if "barley" in gs)
        self.assertEqual(mine[1], 10)
        self.assertEqual(mine[0], frozenset(LANES))
        self.assertTrue(mine[0].isdisjoint(GR.AUDIT_GROUPS))
        for gs, _ in GR.LATER_GROUPS:
            if gs is not mine[0]:
                self.assertTrue(gs.isdisjoint(mine[0]))

    def test_the_generated_routes_of_the_package_are_at_most_ten_and_no_earlier_route_is_among_them(self):
        routes = load("freight/routes.json")
        gen = [r for r in routes if r.get("generated")]
        ids = [r["id"] for r in gen if r["id"].startswith(tuple(f"gen-{g}-" for g in LANES))]
        self.assertTrue(1 <= len(ids) <= 10, ids)
        # the 10 routes of package NC3 (A-010) and the 6 of package FNCB (ammonium nitrate with limestone, the two-nutrient compounds) have a cap of their own
        later = [r for r in gen if r["id"].startswith(NC3_GROUPS + ("gen-ammonium-nitrate-limestone-", "gen-npk-two-nutrient-"))]
        # the cap of the first package is 122 since FNCF (generated_routes.TOTAL_CAP: the two released routes that the cap of 120 gave up are back)
        self.assertEqual(len(gen) - len(later), GR.TOTAL_CAP + 20 + len(ids))
        self.assertEqual(len({r["id"] for r in routes}), len(routes))


@unittest.skipUnless(os.path.exists(CACHE), "customs cache not on disk")
class CacheTests(unittest.TestCase):
    totals = cache_totals() if os.path.exists(CACHE) else {}

    def test_the_groups_that_existed_before_have_not_moved_by_a_tonne(self):
        for g, (allyears, latest) in BEFORE.items():
            self.assertEqual(round(self.totals[g][0]), allyears, g)
            self.assertEqual(round(self.totals[g][2][2024]), latest, g)

    def test_every_new_group_is_in_the_cache_for_the_latest_year(self):
        for g in NEW:
            self.assertGreater(self.totals[g][2][2024], 5e6, g)

    def test_the_cache_holds_the_groups_before_and_the_new_ones(self):
        # the groups of the later packages (the metal bulks of NC3, A-010) are in the cache too: test_metal_bulks.py lists them
        self.assertTrue(set(BEFORE) | set(NEW) <= set(self.totals))


class PageTests(unittest.TestCase):
    def table(self, g, side):
        page, stem = NEW[g][1], NEW[g][2]
        d = load(f"commodities/{page}.json")
        if g == "pulses":
            return d[side]
        return next(x["table"] for x in d["extra"] if x["key"] == f"{stem}-{side}")

    @unittest.skipUnless(os.path.exists(CACHE), "customs cache not on disk")
    def test_the_world_total_of_a_table_is_its_group_in_the_cache(self):
        """The table is the group's flows of 2024 in the cache after the shared cleaning rules (pipeline/trade/clean.py); the raw sum of the
        cache is within 12% of it (a tonnage missing in the archive is estimated from its value). The groups whose own tables are
        USDA's (barley, sorghum, sunflower seed) are read in their lane file, which carries the same customs world total."""
        import pandas as pd
        from clean import clean
        df = pd.read_csv(CACHE)
        df = df[df["group"].isin(NEW)]
        cleaned = clean(df)
        for g, (_, page, stem, lanes) in NEW.items():
            want = cleaned[(cleaned["group"] == g) & (cleaned["year"] == 2024)]["t"].sum() / 1e6
            raw = df[(df["group"] == g) & (df["year"] == 2024)]["t"].sum() / 1e6
            self.assertLess(abs(raw - want) / want, 0.12, (g, raw, want))
            if stem or g == "pulses":
                for side in ("exports", "imports"):
                    t = self.table(g, side)
                    self.assertEqual((t["y"], t["s"]), (2024, "baci"))
                    self.assertAlmostEqual(t["world"], want, delta=max(0.0006 * want, 0.0006), msg=(g, side))
                    self.assertLessEqual(sum(r["v"] for r in t["rows"]), t["world"] * 1.0005, (g, side))
            else:
                self.assertAlmostEqual(load(f"freight/lanes/{g}.json")["world"][-1], want, delta=0.006 * want, msg=g)

    def test_the_pulse_kinds_add_up_to_the_pulses_table(self):
        d = load("commodities/pulses.json")
        kinds = {x["key"]: x["table"] for x in d["extra"]}
        for side in ("exports", "imports"):
            total = sum(kinds[f"{k}-{side}"]["world"] for k in ("peas", "chickpeas", "beans", "lentils", "other-pulses"))
            self.assertAlmostEqual(total, d[side]["world"], delta=0.01)
            for k in ("peas", "chickpeas", "beans", "lentils", "other-pulses"):
                self.assertEqual(kinds[f"{k}-{side}"]["y"], 2024)
        self.assertTrue(any(n.startswith("By kind") for n in d["notes"]))

    def test_the_pulses_page_has_no_production_table_and_says_so(self):
        d = load("commodities/pulses.json")
        self.assertNotIn("production", d)
        self.assertNotIn("consumption", d)
        self.assertNotIn("balance", d)
        self.assertTrue(any(n.startswith("No production table") for n in d["notes"]))
        self.assertNotIn("pulses", load("prices/figures.json"))

    def test_the_psd_pages_have_a_balance_and_stocks(self):
        for k in ("barley", "sorghum", "sunflower"):
            d = load(f"commodities/{k}.json")
            self.assertEqual(d["production"]["s"], "usda-psd")
            self.assertEqual({r["k"] for r in d["balance"]["rows"]} >= {"production", "begin", "use", "exports", "stocks"}, True, k)
            self.assertTrue(any(x["key"] == "stocks" for x in d["extra"]), k)

    def test_the_oil_and_the_meal_have_production_and_use_tables_from_psd(self):
        for page, stems in (("sunflower", ("sunflower-oil", "sunflower-meal")), ("rapeseed", ("rapeseed-oil", "rapeseed-meal"))):
            ex = {x["key"]: x["table"] for x in load(f"commodities/{page}.json")["extra"]}
            for s in stems:
                for kind in ("production", "consumption"):
                    self.assertEqual(ex[f"{s}-{kind}"]["s"], "usda-psd", (s, kind))

    def test_the_pages_are_in_the_index_and_say_what_they_hold(self):
        idx = {e["id"]: e for e in load("commodities/index.json")}
        for k in ("barley", "sorghum", "sunflower", "pulses"):
            e = idx[k]
            self.assertEqual((e["family"], e.get("sub")), ("softs", None), k)
            self.assertTrue(e["name"] and e["blurb"])
            self.assertFalse(any(ch.isdigit() for ch in e["blurb"]), "a blurb carries no figure")
        self.assertIn("1514", idx["rapeseed"]["hs"])
        self.assertIn("230640", idx["rapeseed"]["hs"])
        self.assertIn("110100", idx["wheat"]["hs"])
        self.assertIn("230330", idx["corn"]["hs"])
        names = [e["id"] for e in load("commodities/index.json")]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(sorted(e["rank"] for e in idx.values()), list(range(len(idx))))
        order = [e["id"] for e in sorted(idx.values(), key=lambda e: e["rank"])]
        softs = [k for k in order if idx[k]["family"] == "softs"]
        self.assertEqual(softs.index("barley"), softs.index("corn") + 1)  # the grains stay together
        fert = [k for k in softs if idx[k].get("sub") == "Fertilisers"]
        self.assertEqual(softs[-len(fert):], fert)  # the fertilisers stay last under their sub-heading

    def test_the_wheat_and_corn_pages_say_what_their_extra_tables_are(self):
        w = load("commodities/wheat.json")
        self.assertTrue(any("wheat or meslin flour" in n and "no lanes" in n for n in w["notes"]))
        c = load("commodities/corn.json")
        self.assertTrue(any("distillers' dried grains" in n and "not a DDGS" in n for n in c["notes"]))
        # FNCC (GNC2.6): the reason for no lanes is what the atlas does, not a share of bagged cargo no file gives
        self.assertTrue(any("does not tell bulk from bagged or containerised cargo" in n for n in c["notes"]))

    def test_the_oil_pages_say_that_the_codes_hold_two_oils_and_that_the_price_is_the_oils(self):
        for k, other in (("sunflower", "safflower"), ("rapeseed", "mustard")):
            d = load(f"commodities/{k}.json")
            self.assertTrue(any(other in n for n in d["notes"]), k)
            self.assertTrue(any("price series is the oil's" in n for n in d["notes"]), k)

    def test_the_links_between_pages_point_at_pages(self):
        idx = {e["id"] for e in load("commodities/index.json")}
        for k in ("sunflower", "rapeseed"):
            for s in load(f"commodities/{k}.json").get("see", []):
                self.assertIn(s["k"], idx)
                self.assertNotEqual(s["k"], k)
        self.assertEqual([s["k"] for s in load("commodities/sunflower.json")["see"]], ["rapeseed"])
        self.assertEqual([s["k"] for s in load("commodities/rapeseed.json")["see"]], ["sunflower"])


class PriceTests(unittest.TestCase):
    def test_barley_and_sorghum_are_published_with_their_last_month(self):
        idx = {m["id"]: m for m in load("prices/index.json")}
        fig = load("prices/figures.json")
        for k in ("barley", "sorghum"):
            m = idx[f"{k}-m"]
            self.assertEqual((m["k"], m["end"], m["freq"], m["s"], m["closed"]), (k, "2020-08", "M", "wb-pink", True))
            # FNCC (GNC2.1): the key figure of the page is the annual average that goes on after the closed monthly series
            self.assertNotIn("closed", fig[k])
            self.assertEqual((fig[k]["id"], fig[k]["freq"], fig[k]["stats"]["last"]["t"]), (f"{k}-a", "A", "2025"))
            d = load(f"commodities/{k}.json")
            self.assertTrue(any("stops in August 2020" in n for n in d["notes"]), k)

    def test_the_sunflower_oil_series_is_on_the_sunflower_page_and_the_rapeseed_one_stays(self):
        idx = {m["id"]: m for m in load("prices/index.json")}
        self.assertEqual(idx["sunflower-oil-m"]["k"], "sunflower")
        self.assertNotIn("fam", idx["sunflower-oil-m"])
        self.assertEqual(idx["rapeseed-oil-m"]["k"], "rapeseed")
        fig = load("prices/figures.json")
        self.assertEqual((fig["sunflower"]["id"], fig["rapeseed"]["id"]), ("sunflower-oil-m", "rapeseed-oil-m"))
        self.assertNotIn("sunflower-oil", {m["k"] for m in idx.values()})


class LaneAndProfileTests(unittest.TestCase):
    def test_every_group_that_sails_has_lanes_under_its_page(self):
        for g in LANES:
            f = load(f"freight/lanes/{g}.json")
            self.assertEqual(f["k"], NEW[g][1], g)
            self.assertTrue(f["lanes"], g)
            self.assertTrue(os.path.exists(os.path.join(DATA, "freight", "pairs", g + ".json")), g)

    def test_the_lanes_of_the_oils_are_not_carried_by_dry_bulk_ships(self):
        dry = {"supramax", "handysize", "panamax", "ultramax", "kamsarmax", "capesize"}
        for g in OILS:
            for lane in load(f"freight/lanes/{g}.json")["lanes"]:
                self.assertFalse(set(lane["vclass"]) & dry, (g, lane["id"]))

    def test_ukraine_exports_sunflower_oil_and_meal_first(self):
        ukr = load("countries/profiles/UKR.json")
        lines = {(e["k"], e.get("label")): e for e in ukr["exports"]}
        self.assertEqual(lines[("sunflower", "Sunflower and safflower oil")]["rank"], 1)
        self.assertEqual(lines[("sunflower", "Sunflower meal")]["rank"], 1)
        self.assertIn(("wheat", "Wheat flour"), lines)
        self.assertIn(("corn", "Brewing and distilling dregs"), lines)

    def test_canada_exports_pulses_and_the_rapeseed_products(self):
        can = load("countries/profiles/CAN.json")
        lines = {(e["k"], e.get("label")): e for e in can["exports"]}
        self.assertEqual(lines[("pulses", None)]["rank"], 1)
        self.assertEqual(lines[("rapeseed", "Rapeseed, canola and mustard oil")]["rank"], 1)
        self.assertEqual(lines[("rapeseed", "Rapeseed meal")]["rank"], 1)
        self.assertTrue(any(k == "pulses" and lab and "peas" in lab.lower() for k, lab in lines))

    def test_australia_exports_barley_and_pulses(self):
        aus = load("countries/profiles/AUS.json")
        ks = {e["k"] for e in aus["exports"]}
        self.assertTrue({"barley", "pulses"} <= ks)


if __name__ == "__main__":
    unittest.main()
