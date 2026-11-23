"""Vessel classes (audit M-033, M-034, C-058): every band and standard vessel has a page and a year, the bands of a
segment follow each other, the lane rules name classes that exist, and the world fleet comes from UNCTADstat.

    python -m unittest discover -s pipeline/tests -p "test_vessel_classes.py"
"""
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FREIGHT = os.path.join(ROOT, "pipeline", "freight")
sys.path.insert(0, FREIGHT)
import fleet  # noqa: E402
import vessel_rules as VR  # noqa: E402


def load(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return json.load(f)


CLASSES = {c["id"]: c for c in load("pipeline", "freight", "vessel_classes.json")}
SOURCES = {s["id"]: s for s in load("data", "sources.json")}

# size steps of a segment, smallest first: each band ends where the next starts (classes defined by a port or a cargo,
# Newcastlemax, LR2 and the chemical tanker, sit inside these steps on purpose and are checked apart)
DRY = ["handysize", "supramax", "ultramax", "panamax", "kamsarmax", "capesize", "vloc"]
TANKER = ["handy-tanker", "mr", "lr1", "aframax", "suezmax", "vlcc"]


class Bands(unittest.TestCase):
    def test_every_band_and_typical_size_has_a_source_and_a_year(self):
        for cid, c in CLASSES.items():
            z = c["size"]
            self.assertIn(z["s"], SOURCES, cid)
            self.assertIsInstance(z["y"], int, cid)
            self.assertTrue(z["n"], cid)
            self.assertIn(z["typicalS"], SOURCES, cid)
            self.assertIsInstance(z["typicalY"], int, cid)
            self.assertLessEqual(z["min"], z["typical"], cid)
            self.assertLessEqual(z["typical"], z["max"], cid)
            if z["s"] == "wikipedia":
                self.assertTrue(z["url"].startswith("https://en.wikipedia.org/wiki/"), cid)

    def test_no_catch_all_source(self):
        self.assertNotIn("vessel-size-conventions", SOURCES)
        self.assertFalse([s for s in SOURCES.values() if s.get("publisher") == "Various"])
        for cid, c in CLASSES.items():
            self.assertIn(c["s"], SOURCES, cid)

    def test_steps_of_a_segment_neither_overlap_nor_leave_a_gap(self):
        for chain in (DRY, TANKER):
            for a, b in zip(chain, chain[1:]):
                self.assertEqual(CLASSES[a]["size"]["max"], CLASSES[b]["size"]["min"], f"{a} -> {b}")

    def test_classes_defined_by_a_port_or_a_cargo_sit_inside_the_steps(self):
        nc, lr2, ch = CLASSES["newcastlemax"]["size"], CLASSES["lr2"]["size"], CLASSES["chemical-tanker"]["size"]
        self.assertTrue(CLASSES["capesize"]["size"]["min"] <= nc["min"] < nc["max"] <= CLASSES["vloc"]["size"]["max"])
        self.assertEqual((lr2["min"], lr2["max"]), (CLASSES["aframax"]["size"]["min"], CLASSES["aframax"]["size"]["max"]))
        self.assertGreaterEqual(ch["min"], 0)
        self.assertLessEqual(ch["max"], CLASSES["mr"]["size"]["max"])

    def test_suezmax_has_a_typical_ship_not_the_canal_limits(self):
        c = CLASSES["suezmax"]
        self.assertNotIn("dims", c)
        self.assertEqual((c["std"]["dwt"], c["std"]["beam"]), (160000, 48))
        self.assertNotIn("draught", c["std"])  # the 20.1 m of the canal is a limit, not a ship's draught


class StandardVessel(unittest.TestCase):
    def test_shape(self):
        for cid, c in CLASSES.items():
            s = c.get("std")
            if not s:
                continue
            self.assertIn(s["s"], SOURCES, cid)
            self.assertIsInstance(s["y"], int, cid)
            self.assertTrue(s["n"] and s["url"], cid)
            for k in ("dwt", "loa", "beam", "draught", "cubic"):
                if k in s:
                    self.assertIsInstance(s[k], (int, float), (cid, k))
            for k in ("speed", "cons"):
                if k in s:
                    self.assertLessEqual(set(s[k]), {"laden", "ballast"}, (cid, k))

    def test_baltic_dry_vessels(self):
        """The four Baltic dry standard vessels, as the Baltic Exchange's dry services page gives them (2026)."""
        want = {"capesize": (182000, 292, 45, 18.2), "kamsarmax": (82500, 229, 32.25, 14.43),
                "ultramax": (63500, 199.98, 32.24, 13.418), "handysize": (38200, 180, 29.8, 10.538)}
        for cid, (dwt, loa, beam, draught) in want.items():
            s = CLASSES[cid]["std"]
            self.assertEqual((s["dwt"], s["loa"], s["beam"], s["draught"], s["s"]), (dwt, loa, beam, draught, "baltic"), cid)
            self.assertEqual(CLASSES[cid]["size"]["typical"], dwt, cid)

    def test_baltic_tanker_and_gas_vessels(self):
        """The Baltic standard tankers and gas carriers of the Guide to Market Benchmarks (version 7.09, December 2025):
        deadweight in tonnes, speed and fuel laden and in ballast; the typical size is the guide's (cbm for gas)."""
        gmb = "https://www.balticexchange.com/content/dam/balticexchange/consumer/data-services-/documents-/ocean-bulk/GMB.pdf"
        want = {"vlcc": (300000, 300000, (13, 12), (57.3, 39.5)), "suezmax": (160000, 160000, (13, 12), (38.5, 28.5)),
                "aframax": (115000, 115000, (13, 12), (35.3, 25.3)), "lr2": (115000, 115000, (13, 12), (35.3, 25.3)),
                "lr1": (75000, 75000, (13, 12), (30.5, 24.5)), "mr": (50000, 50000, (13, 12), (23.3, 17)),
                "handy-tanker": (37800, 37800, (13, 12), (21.3, 16.8)),
                "vlgc": (54500, 84000, (16, 16), (48, 43)), "lng": (93500, 174000, (17, 17), (69, 66))}
        for cid, (dwt, typical, speed, cons) in want.items():
            c = CLASSES[cid]
            s = c["std"]
            self.assertEqual((s["s"], s["url"], s["y"], s["dwt"]), ("baltic", gmb, 2025, dwt), cid)
            self.assertEqual((s["speed"]["laden"], s["speed"]["ballast"]), speed, cid)
            self.assertEqual((s["cons"]["laden"], s["cons"]["ballast"]), cons, cid)
            self.assertEqual(c["size"]["typical"], typical, cid)
        self.assertEqual({k: CLASSES["vlgc"]["std"][k] for k in ("loa", "beam", "draught", "cubic")},
                         {"loa": 225, "beam": 36.5, "draught": 12, "cubic": 84000})
        self.assertEqual({k: CLASSES["lng"]["std"][k] for k in ("loa", "beam", "cubic")}, {"loa": 295, "beam": 47, "cubic": 174000})

    def test_classes_without_benchmarks_point_to_the_class_that_has_them(self):
        for cid, other in (("panamax", "kamsarmax"), ("supramax", "ultramax"), ("newcastlemax", "capesize")):
            self.assertEqual(CLASSES[cid]["bench"]["id"], other)
        for c in CLASSES.values():
            if "bench" in c:
                self.assertIn(c["bench"]["id"], CLASSES)

    def test_baltic_notes_are_the_atlas_own_words(self):
        """The Baltic Exchange's site terms restrict copying (registry entry `baltic`): a standard vessel taken from its
        page keeps the figures and one sentence of the atlas's own, never the page's description."""
        for cid, c in CLASSES.items():
            s = c.get("std")
            if not s or s["s"] != "baltic":
                continue
            for phrase in ("non-scrubber", "salt-water", "maximum age", "bale", "cranes", "the page also gives"):
                self.assertNotIn(phrase, s["n"], cid)
            self.assertLessEqual(len(s["n"]), 220, cid)
        for sid in ("baltic", "baltic-circulars"):
            self.assertIn("verdict pending", SOURCES[sid]["licence"], sid)
        for sid in ("baltic", "baltic-circulars"):
            self.assertIn("without the prior written consent of the Baltic", SOURCES[sid]["licence"], sid)


class TypicalSize(unittest.TestCase):
    def test_a_typical_size_from_a_page_links_the_page(self):
        """The ports read the typical deadweight of a class without a standard vessel: a page's figure has its page."""
        for cid, c in CLASSES.items():
            z = c["size"]
            if z["typicalS"] != "atlas":
                self.assertTrue(z.get("typicalUrl", "").startswith("https://"), cid)

    def test_port_and_benchmark_sizes(self):
        nc, pmx = CLASSES["newcastlemax"]["size"], CLASSES["panamax"]["size"]
        # Wikipedia (Bulk carrier): the largest vessel able to enter Newcastle, about 185,000 dwt
        self.assertEqual((nc["typical"], nc["typicalS"]), (185000, "wikipedia"))
        # the size in the name of the Baltic's Panamax 74 average (P4TC): the guide describes no such vessel
        self.assertEqual((pmx["typical"], pmx["typicalS"]), (74000, "atlas"))

    def test_every_page_of_a_class_is_a_page_the_atlas_may_cite(self):
        """The summary of the Baltic definitions on a third-party site (see NOTES_routes.md) is no longer cited: the
        Baltic's own guide and pages, Wikipedia and the LPG ship manager's page are."""
        hosts = ("https://en.wikipedia.org/", "https://www.balticexchange.com/", "https://wilhelmsen.com/")
        for cid, c in CLASSES.items():
            for part in (c["size"], c.get("std") or {}):
                for k in ("url", "typicalUrl"):
                    if part.get(k):
                        self.assertTrue(part[k].startswith(hosts), (cid, k, part[k]))


class RoutesOfAClass(unittest.TestCase):
    def test_a_route_the_class_also_serves_exists_and_the_vegetable_oil_route_is_not_handy(self):
        built = {r["id"]: r for r in load("data", "freight", "routes.json")}
        for cid, c in CLASSES.items():
            for rid in c["routes"]:
                self.assertIn(rid, built, (cid, rid))
        self.assertIn("indo-malay-india-palm-oil", CLASSES["chemical-tanker"]["routes"])
        self.assertNotIn("indo-malay-india-palm-oil", CLASSES["handy-tanker"]["routes"])
        self.assertNotEqual(built["indo-malay-india-palm-oil"]["vclass"], "handy-tanker")


class Rules(unittest.TestCase):
    GROUPS = ["iron-ore", "bauxite", "coal", "manganese", "copper-ore", "wheat", "rice", "potash", "palm-oil", "soyoil",
              "steel", "coffee", "lng", "lpg", "crude-oil", "refined-products", "other"]

    def test_every_class_a_rule_gives_exists(self):
        for g in self.GROUPS:
            for o, d in (("AUS", "CHN"), ("BRA", "CHN"), ("SAU", "JPN"), ("USA", "MEX"), ("IDN", "IND"), ("RUS", "NLD")):
                for t, nm in ((0.2e6, 300), (4e6, 2500), (12e6, 9000)):
                    for c in VR.classes(g, o, d, t, nm):
                        self.assertIn(c, CLASSES, (g, o, d, c))

    def test_vegetable_oils(self):
        """Vegetable oils move in chemical tankers; the MR first (a 40,000 t Baltic parcel), the chemical tanker second."""
        self.assertEqual(VR.classes("palm-oil", "IDN", "IND", 4.4e6, 2758), ["mr", "chemical-tanker"])
        self.assertEqual(VR.classes("soyoil", "ARG", "IND", 2e6, 8500), ["mr", "chemical-tanker"])
        self.assertIn("palm-oil", CLASSES["chemical-tanker"]["cargoes"])
        self.assertIn("palm-oil", CLASSES["mr"]["cargoes"])
        self.assertNotIn("palm-oil", CLASSES["handy-tanker"]["cargoes"])


class WorldFleet(unittest.TestCase):
    def test_fleet_file(self):
        doc = load("data", "freight", "fleet.json")
        self.assertEqual(doc["s"], "unctadstat-fleet")
        self.assertIn(doc["s"], SOURCES)
        names = {t["name"]: t for t in doc["types"]}
        for cid, c in CLASSES.items():
            if c.get("fleetType"):
                self.assertIn(c["fleetType"], names, cid)
        for t in names.values():
            for k in ("ships", "dwt", "age"):
                if t[k]:
                    self.assertEqual((t[k]["y"], t[k]["s"]), (doc["y"], doc["s"]))
            self.assertEqual(t["hist"]["years"][-1], doc["y"])

    def test_the_file_is_the_cache(self):
        """data/freight/fleet.json is what fleet.py builds from the tracked cache."""
        self.assertEqual(fleet.build(fleet.load_cache()), load("data", "freight", "fleet.json"))


if __name__ == "__main__":
    unittest.main()
