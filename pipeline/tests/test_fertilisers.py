"""Tests of package NC1 (audit M-022): the fertilisers that were missing, as new customs groups of the nitrogen, phosphate and potash
pages and the two new pages, sulphur and NPK. The codes of each group, one home per code, the totals of the pages against the cache,
the engine's rules for the liquids (ammonia, UAN, phosphoric acid), the pages and their links, and the totals of every earlier group.

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

# group -> (HS 1992 codes, page that holds it, key stem of its tables on that page or None for the page's own tables)
NEW = {
    "ammonia": (["281410"], "urea", "ammonia"),
    "ammonium-nitrate": (["310230"], "urea", "ammonium-nitrate"),
    "uan": (["310280"], "urea", "uan"),
    "ammonium-sulphate": (["310221"], "urea", "ammonium-sulphate"),
    "monoammonium-phosphate": (["310540"], "phosphate", "map"),
    "superphosphates": (["310310"], "phosphate", "superphosphates"),
    "phosphoric-acid": (["280920"], "phosphate", "phosphoric-acid"),
    "potassium-sulphate": (["310430"], "potash", "sop"),
    "npk": (["310520"], "npk", None),
    "sulphur": (["250310", "250390", "280200"], "sulphur", None),
}
LIQUIDS = ("ammonia", "uan", "phosphoric-acid")

# Tonnes of every group that existed before M-022 in the customs cache: (all years, 2024), as the cache held them before the
# fertilisers were added. A new group must not move any of them (the cache is extracted again from the same archive).
BEFORE = {
    "alumina": (778188953, 37134300),
    "aluminium": (555958370, 30394465),
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
    "natural-gas": (9144031568, 330536312),
    "nickel-fe": (57706923, 10071642),
    "nickel-int": (42576057, 3423960),
    "nickel-ore": (968571886, 52855170),
    "palm-oil": (892371157, 42945320),
    "pgm": (38321, 1454),
    "phosphate-rock": (782705033, 35843109),
    "potash": (1085904984, 62663307),
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
    "tin-metal": (6830323, 221903),
    "tin-ore": (4402404, 123879),
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
        for g, (codes, _, _) in NEW.items():
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
            words = {r["code"].zfill(6): r["description"] for r in csv.DictReader(f)}
        for g, (codes, _, _) in NEW.items():
            for c in codes:
                self.assertIn(c, words, (g, c))
        self.assertIn("monoammonium phosphate", words["310540"])
        self.assertIn("superphosphates", words["310310"])  # one code for single and triple: the page says so
        self.assertIn("Ammonia: anhydrous", words["281410"])
        self.assertIn("mixtures of urea and ammonium nitrate", words["310280"])
        self.assertIn("potassium sulphate", words["310430"])

    def test_the_codes_the_pages_leave_out_are_in_no_group(self):
        loaded = {c for codes in hs_map.HS.values() for c in codes}
        # 310240 (ammonium nitrate with limestone) and 310551, 310559, 310560 (the two-nutrient compounds) are loaded since package FNCB
        for c in ("281420", "310229", "310250", "310260", "310270", "310290", "310320", "310390", "310410", "310490", "310510", "310590"):
            self.assertNotIn(c, loaded, c)
        for c in ("310240", "310551", "310559", "310560"):
            self.assertIn(c, loaded, c)


class EngineTests(unittest.TestCase):
    def test_every_group_has_a_mode_a_segment_and_a_page(self):
        import build_lanes as BL
        for g, (_, page, _) in NEW.items():
            self.assertEqual(modes.family_of(g), "fert", g)
            self.assertEqual(ports.segment(g), "fert", g)
            self.assertIn(g, BL.GROUPS)
            self.assertIn(g, BL.CAP)
            self.assertEqual(BL.COMMODITY.get(g, g), page, g)

    def test_the_liquids_and_sulphur_take_no_port_of_a_page_that_names_fertilisers(self):
        for g in LIQUIDS + ("sulphur",):
            self.assertIn(g, ports.OWN_FAMILY)
        for g in ("npk", "monoammonium-phosphate", "superphosphates", "ammonium-sulphate", "ammonium-nitrate", "potassium-sulphate"):
            self.assertNotIn(g, ports.OWN_FAMILY)
        # a fertiliser berth that a page names for fertilisers is no ammonia terminal: Ust-Luga (a "fert" row of Russia)
        self.assertEqual(ports.candidates("RUS", "urea", "load")[0][2], ports.BASIS_PAGE)
        self.assertNotEqual(ports.candidates("RUS", "ammonia", "load")[0][2], ports.BASIS_PAGE)

    def test_ammonia_is_not_dry_bulk(self):
        for o, d in (("TTO", "USA"), ("SAU", "IND"), ("RUS", "TUR")):
            for t, nm in ((0.2e6, 300), (1.5e6, 9000)):
                self.assertEqual(VR.classes("ammonia", o, d, t, nm), ["mgc", "vlgc"])
        self.assertEqual(VR.classes("uan", "RUS", "USA", 1e6, 5000), ["chemical-tanker", "handy-tanker"])
        self.assertEqual(VR.classes("phosphoric-acid", "MAR", "IND", 1e6, 5000), ["chemical-tanker", "handy-tanker"])
        for g in ("monoammonium-phosphate", "superphosphates", "npk", "ammonium-sulphate", "ammonium-nitrate", "potassium-sulphate", "sulphur"):
            self.assertEqual(VR.classes(g, "MAR", "BRA", 1e6, 5000), ["supramax", "handysize"], g)

    def test_the_classes_exist_in_the_vessel_catalogue(self):
        with open(os.path.join(ROOT, "pipeline", "freight", "vessel_classes.json"), encoding="utf-8") as f:
            ids = {c["id"] for c in json.load(f)}
        for c in ("mgc", "vlgc", "chemical-tanker", "handy-tanker"):
            self.assertIn(c, ids)

    def test_the_liquids_are_compared_with_the_tankers_of_the_chokepoint_estimates(self):
        import build_freight as BF
        for g in LIQUIDS:
            self.assertEqual(BF.vessel_type(g), "tanker", g)
        self.assertEqual(BF.vessel_type("sulphur"), "dry")

    def test_the_new_groups_have_a_route_cap_of_their_own(self):
        """The corridors kept for the earlier groups do not move when the fertilisers are added (generated_routes.LATER_GROUPS)."""
        later = set().union(*(gs for gs, _ in GR.LATER_GROUPS))
        self.assertTrue(set(NEW) <= later)
        self.assertTrue(later.isdisjoint(GR.AUDIT_GROUPS))


@unittest.skipUnless(os.path.exists(CACHE), "customs cache not on disk")
class CacheTests(unittest.TestCase):
    totals = cache_totals() if os.path.exists(CACHE) else {}

    def test_the_groups_that_existed_before_have_not_moved_by_a_tonne(self):
        for g, (allyears, latest) in BEFORE.items():
            self.assertEqual(round(self.totals[g][0]), allyears, g)
            self.assertEqual(round(self.totals[g][2][2024]), latest, g)

    def test_every_new_group_is_in_the_cache_for_the_latest_year(self):
        for g in NEW:
            self.assertGreater(self.totals[g][2][2024], 1e6, g)


class PageTests(unittest.TestCase):
    def table(self, page, g, side):
        d = load(f"commodities/{page}.json")
        stem = NEW[g][2]
        if stem is None:
            return d[side]
        return next(x["table"] for x in d["extra"] if x["key"] == f"{stem}-{side}")

    @unittest.skipUnless(os.path.exists(CACHE), "customs cache not on disk")
    def test_the_world_total_of_a_table_is_its_group_in_the_cache(self):
        """The table is the group's flows of 2024 in the cache after the shared cleaning rules (pipeline/trade/clean.py); the raw sum of the
        cache is within 12% of it (a tonnage missing in the archive is estimated from its value)."""
        import pandas as pd
        from clean import clean
        df = pd.read_csv(CACHE)
        df = df[df["group"].isin(NEW)]
        cleaned = clean(df)
        for g, (_, page, _) in NEW.items():
            want = cleaned[(cleaned["group"] == g) & (cleaned["year"] == 2024)]["t"].sum() / 1e6
            raw = df[(df["group"] == g) & (df["year"] == 2024)]["t"].sum() / 1e6
            self.assertLess(abs(raw - want) / want, 0.12, (g, raw, want))
            for side in ("exports", "imports"):
                t = self.table(page, g, side)
                self.assertEqual(t["y"], 2024)
                self.assertAlmostEqual(t["world"], want, delta=max(0.0006 * want, 0.0006), msg=(g, side))

    def test_a_table_keeps_the_rows_inside_its_world_total(self):
        for g, (_, page, _) in NEW.items():
            for side in ("exports", "imports"):
                t = self.table(page, g, side)
                self.assertLessEqual(sum(r["v"] for r in t["rows"]), t["world"] * 1.0005, (g, side))
                self.assertEqual(t["s"], "baci")

    def test_the_new_pages_are_in_the_index_under_fertilisers(self):
        idx = {e["id"]: e for e in load("commodities/index.json")}
        for k in ("npk", "sulphur"):
            self.assertEqual((idx[k]["family"], idx[k]["sub"]), ("softs", "Fertilisers"), k)
            self.assertTrue(idx[k]["name"] and idx[k]["blurb"])
            self.assertFalse(any(ch.isdigit() for ch in idx[k]["blurb"]), "a blurb carries no figure")
        names = [e["id"] for e in load("commodities/index.json")]
        self.assertEqual(len(names), len(set(names)))

    def test_the_pages_that_hold_several_products_say_which_one_the_main_table_is(self):
        self.assertIn("phosphate rock", load("commodities/phosphate.json")["labels"]["exports"])
        self.assertIn("urea", load("commodities/urea.json")["labels"]["exports"])
        self.assertIn("potassium chloride", load("commodities/potash.json")["labels"]["exports"])

    def test_the_ammonia_producers_table_is_plant_output_in_nitrogen(self):
        d = load("commodities/urea.json")
        self.assertIn("nitrogen", d["labels"]["production"])
        self.assertEqual(d["summary"]["production"]["u"], "Mt N")
        self.assertTrue(any("not the ammonia trade" in n for n in d["notes"]))

    def test_the_links_between_pages_point_at_pages(self):
        idx = {e["id"] for e in load("commodities/index.json")}
        for k in ("urea", "phosphate", "potash", "npk", "sulphur"):
            for s in load(f"commodities/{k}.json").get("see", []):
                self.assertIn(s["k"], idx)
                self.assertNotEqual(s["k"], k)
        self.assertEqual({s["k"] for s in load("commodities/npk.json")["see"]}, {"urea", "phosphate", "potash"})

    def test_sulphur_says_what_its_production_table_measures_and_that_it_has_no_price(self):
        d = load("commodities/sulphur.json")
        self.assertEqual(d["summary"]["production"]["u"], "Mt S")
        self.assertIn("sulphur content", d["labels"]["production"])
        self.assertTrue(any("No free price series" in n for n in d["notes"]))
        self.assertNotIn("sulphur", load("prices/figures.json"))

    def test_npk_has_no_production_table_and_says_so(self):
        d = load("commodities/npk.json")
        self.assertNotIn("production", d)
        self.assertTrue(any(n.startswith("No production table") for n in d["notes"]))

    def test_the_tsp_price_is_on_the_phosphate_page(self):
        idx = {e["id"]: e for e in load("prices/index.json")}
        self.assertEqual(idx["tsp-m"]["k"], "phosphate")


class LaneAndProfileTests(unittest.TestCase):
    def test_every_new_group_has_lanes_under_its_page(self):
        for g, (_, page, _) in NEW.items():
            f = load(f"freight/lanes/{g}.json")
            self.assertEqual(f["k"], page, g)
            self.assertTrue(f["lanes"], g)
            self.assertTrue(os.path.exists(os.path.join(DATA, "freight", "pairs", g + ".json")), g)

    def test_the_lanes_of_the_liquids_are_not_carried_by_dry_bulk_ships(self):
        dry = {"supramax", "handysize", "panamax", "ultramax", "kamsarmax", "capesize"}
        for g in LIQUIDS:
            for lane in load(f"freight/lanes/{g}.json")["lanes"]:
                self.assertFalse(set(lane["vclass"]) & dry, (g, lane["id"]))

    def test_brazil_imports_map_and_the_other_new_products(self):
        bra = load("countries/profiles/BRA.json")
        lines = {(e["k"], e.get("label")): e for e in bra["imports"]}
        self.assertIn(("phosphate", "MAP"), lines)
        self.assertGreater(lines[("phosphate", "MAP")]["v"], 1.0)
        self.assertEqual(lines[("phosphate", "MAP")]["rank"], 1)
        self.assertIn(("urea", "Ammonium sulphate"), lines)
        self.assertIn(("npk", None), lines)

    def test_morocco_exports_the_phosphate_products(self):
        mar = load("countries/profiles/MAR.json")
        labels = {e.get("label") for e in mar["exports"] if e["k"] == "phosphate"}
        self.assertTrue({"DAP", "MAP", "Superphosphates", "Phosphoric acid", "Phosphate rock"} <= labels)


if __name__ == "__main__":
    unittest.main()
