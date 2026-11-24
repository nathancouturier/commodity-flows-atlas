"""Tests of the port assets: the asset each route port is (pipeline/infrastructure/route_assets.py), the largest class a
port's limits allow (pipeline/infrastructure/port_limits.py) and the asset of a port of the lane index
(pipeline/freight/build_port_index.py), each on fixtures."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "infrastructure"))
sys.path.insert(0, os.path.join(HERE, "..", "freight"))
import route_assets as RA  # noqa: E402
import port_limits as PL  # noqa: E402
import build_port_index as BPI  # noqa: E402


def point(type_, id_, name, c, **extra):
    return {"type": "Feature", "properties": {"id": id_, "name": name, "type": type_, "c": c, "k": ["iron-ore"], **extra},
            "geometry": {"type": "Point", "coordinates": [0, 0]}}


def write(path, feats):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": feats}, fh)


class RoutePorts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        write(os.path.join(d, "ports.geojson"), [
            point("port", "tubarao", "Tubarao (Vitoria)", "BRA"),
            point("port", "novorossiysk", "Novorossiysk", "RUS"),
            point("port", "cpc-terminal", "CPC terminal (Novorossiysk)", "RUS"),
            point("port", "los-angeles-long-beach", "Los Angeles / Long Beach", "USA"),
            point("port", "shanghai", "Shanghai", "CHN"),
        ])
        write(os.path.join(d, "lng.geojson"), [point("lng-export", "sabine-pass-lng", "Sabine Pass LNG (Cheniere)", "USA")])
        self.feats = RA.load_assets(d)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_port_is_the_asset_of_its_name_and_country(self):
        self.assertEqual(RA.asset_of("Tubarao", "BRA", ["iron-ore"], self.feats), "port:tubarao")
        self.assertEqual(RA.asset_of("Long Beach", "USA", ["crude-oil"], self.feats), "port:los-angeles-long-beach")
        self.assertIsNone(RA.asset_of("Tubarao", "ARG", ["iron-ore"], self.feats))  # another country
        self.assertIsNone(RA.asset_of("Boke", "GIN", ["bauxite"], self.feats))

    def test_the_name_itself_wins_over_a_word_in_brackets(self):
        self.assertEqual(RA.asset_of("Novorossiysk", "RUS", ["wheat"], self.feats), "port:novorossiysk")

    def test_an_alias_points_to_an_asset_that_exists_only(self):
        self.assertEqual(RA.asset_of("Sabine Pass", "USA", ["lng"], self.feats), "lng-export:sabine-pass-lng")
        self.assertIsNone(RA.asset_of("Ningbo", "CHN", ["crude-oil"], self.feats))  # its alias names no asset of the fixture

    def test_the_assets_of_one_end_follow_its_ports(self):
        side = {"region": "x", "ports": [{"name": "Shanghai", "c": "CHN"}, {"name": "Nowhere", "c": "CHN"}]}
        self.assertEqual(RA.route_port_assets(side, ["lng"], self.tmp.name), ["port:shanghai", None])

    def test_every_alias_of_the_real_layer_exists(self):
        feats = RA.load_assets()
        for key, asset in RA.ALIAS.items():
            t, _, i = asset.partition(":")
            self.assertIn((t, i), feats, f"{key} -> {asset}")


class PortLimits(unittest.TestCase):
    # the classes of pipeline/freight/vessel_classes.json as they stood in November 2026 (size band, std and typical size)
    CLASSES = [
        {"id": "capesize", "name": "Capesize", "segment": "dry", "std": {"dwt": 182000, "loa": 292, "beam": 45, "draught": 18.2},
         "size": {"min": 85000, "max": 200000, "typical": 182000, "u": "dwt"}},
        {"id": "newcastlemax", "name": "Newcastlemax", "segment": "dry", "std": None,
         "size": {"min": 185000, "max": 210000, "typical": 185000, "u": "dwt"}},
        {"id": "vloc", "name": "VLOC", "segment": "dry", "std": {"dwt": 400000, "loa": 360, "beam": 65, "draught": 22},
         "size": {"min": 200000, "max": 400000, "typical": 400000, "u": "dwt"}},
        {"id": "panamax", "name": "Panamax", "segment": "dry", "std": None, "size": {"min": 65000, "max": 80000, "typical": 74000, "u": "dwt"}},
        {"id": "kamsarmax", "name": "Kamsarmax", "segment": "dry", "std": {"dwt": 82500, "loa": 229, "beam": 32.25, "draught": 14.43},
         "size": {"min": 80000, "max": 85000, "typical": 82500, "u": "dwt"}},
        {"id": "ultramax", "name": "Ultramax", "segment": "dry", "std": {"dwt": 63500, "loa": 199.98, "beam": 32.24, "draught": 13.418},
         "size": {"min": 60000, "max": 65000, "typical": 63500, "u": "dwt"}},
        {"id": "handysize", "name": "Handysize", "segment": "dry", "std": {"dwt": 38200, "loa": 180, "beam": 29.8, "draught": 10.538},
         "size": {"min": 10000, "max": 40000, "typical": 38200, "u": "dwt"}},
        {"id": "vlcc", "name": "VLCC", "segment": "tanker", "std": {"dwt": 300000}, "size": {"min": 200000, "max": 320000, "typical": 300000, "u": "dwt"}},
        {"id": "suezmax", "name": "Suezmax", "segment": "tanker", "std": {"dwt": 160000, "beam": 48},
         "size": {"min": 120000, "max": 200000, "typical": 160000, "u": "dwt"}},
        {"id": "aframax", "name": "Aframax", "segment": "tanker", "std": {"dwt": 115000}, "size": {"min": 80000, "max": 120000, "typical": 115000, "u": "dwt"}},
        {"id": "lr2", "name": "LR2", "segment": "tanker", "std": {"dwt": 115000}, "size": {"min": 80000, "max": 120000, "typical": 115000, "u": "dwt"}},
        {"id": "lng", "name": "LNG carrier", "segment": "gas", "std": {"dwt": 93500, "loa": 295, "beam": 47}, "size": {"min": 140000, "max": 266000, "typical": 174000, "u": "cbm"}},
    ]

    def port(self, k, **lim):
        return {"id": "p", "type": "port", "k": k, "limits": {**lim, "n": "berth 1", "s": "wikipedia", "url": "https://x"}}

    def result(self, k, **lim):
        """{segment: [(class, or larger)]} of a port, {} when it has none."""
        m = PL.max_class(self.port(k, **lim), self.CLASSES)
        return {s: [(e["id"], bool(e.get("orLarger"))) for e in v["classes"]] for s, v in (m or {}).items() if s != "n"}

    def entries(self, k, **lim):
        return PL.max_class(self.port(k, **lim), self.CLASSES)

    def test_a_limit_above_the_largest_band_is_that_class_or_larger(self):
        # LOOP: single buoy moorings for ships of up to 635,000 t; Hound Point: 350,000 dwt. The VLCC band ends at 320,000
        self.assertEqual(self.result(["crude-oil"], dwt=635000), {"tanker": [("vlcc", True)]})
        m = self.entries(["crude-oil"], dwt=350000)
        self.assertEqual([(e["id"], e.get("orLarger")) for e in m["tanker"]["classes"]], [("vlcc", True)])
        self.assertIn("is above the VLCC band (200,000 to 320,000 dwt)", m["tanker"]["classes"][0]["basis"])
        self.assertEqual(m["tanker"]["classes"][0]["by"], "By deadweight")

    def test_the_class_is_the_band_that_holds_the_deadweight_limit(self):
        # Novorossiysk: Sheskharis oil berth 1, 250,000 dwt and 19 m (no tanker standard vessel gives a draught): VLCC, not Suezmax
        m = self.entries(["crude-oil", "refined-products", "wheat"], draught=19, dwt=250000, seg="tanker")
        self.assertEqual({s: [e["id"] for e in v["classes"]] for s, v in m.items() if s != "n"}, {"tanker": ["vlcc"]})
        self.assertIn("The 250,000 dwt limit is in the VLCC band", m["tanker"]["classes"][0]["basis"])
        self.assertIn("tanker berths", m["n"])
        # the edge of a band belongs to the lower class: 80,000 dwt is Panamax, 200,000 dwt Capesize
        self.assertEqual(self.result(["iron-ore"], dwt=80000), {"dry": [("panamax", False)]})
        self.assertEqual(self.result(["iron-ore"], dwt=200000), {"dry": [("capesize", False)]})
        # nesting: Newcastlemax (185,000 to 210,000) lies across Capesize and VLOC and is never chosen; the widest band wins
        for dwt, want in ((190000, "capesize"), (205000, "vloc")):
            self.assertEqual(self.result(["iron-ore"], dwt=dwt), {"dry": [(want, False)]}, dwt)
        # Aframax and LR2 share one band: the class listed first
        self.assertEqual(self.result(["crude-oil"], dwt=100000), {"tanker": [("aframax", False)]})
        # below the smallest band: none
        self.assertEqual(self.result(["iron-ore"], dwt=9000), {})

    def test_by_dimensions_the_largest_class_whose_standard_vessel_fits(self):
        # Kandla: cargo berths of 14.5 m maximum draft for ships of up to 255 m (the 13 m channel is a minimum)
        m = self.entries(["thermal-coal", "palm-oil"], draught=14.5, loa=255, seg="dry")
        self.assertEqual([(e["id"], e["by"]) for e in m["dry"]["classes"]], [("kamsarmax", "By the 14.5 m draught and the 255 m length")])
        # classes without a draught, length or beam of their standard vessel are not compared, and the note says so
        self.assertIn("Not compared by dimensions", m["n"])
        self.assertIn("Newcastlemax, Panamax", m["n"])

    def test_two_rules_that_disagree_give_both_classes_and_no_single_one(self):
        # Taman: 220,000 dwt, 300 m, 50 m and a 14 m draught: VLOC by deadweight, Ultramax by the draught (Kamsarmax needs 14.43 m)
        m = self.entries(["iron-ore"], draught=14, loa=300, beam=50, dwt=220000)
        self.assertEqual([(e["id"], e["by"]) for e in m["dry"]["classes"]],
                         [("vloc", "By deadweight"), ("ultramax", "By the 14 m draught")])
        self.assertIn("Kamsarmax", m["dry"]["classes"][1]["basis"])
        # Panamax (no standard vessel) lies between Ultramax and the Kamsarmax ruled out: named beside Ultramax, not left out
        self.assertEqual(m["dry"]["classes"][1].get("also"), ["panamax"])
        self.assertIn("Panamax, between the two in size, has no standard vessel in the atlas and cannot be ruled out",
                      m["dry"]["classes"][1]["basis"])
        self.assertNotIn("also", m["dry"]["classes"][0])
        # Port Hedland: a depth of 19.8 m (the VLOC standard vessel needs 22 m) and ships of up to 320,000 dwt
        m = self.entries(["iron-ore"], draught=19.8, depth=True, dwt=320000)
        self.assertEqual([(e["id"], e["by"]) for e in m["dry"]["classes"]],
                         [("vloc", "By deadweight"), ("capesize", "By the 19.8 m depth")])
        self.assertEqual(m["dry"]["classes"][1].get("also"), ["newcastlemax"])
        # with no larger class ruled out, nothing bounds the list and none is added (the largest class compared fits)
        m = self.entries(["iron-ore"], draught=23, loa=365, beam=66, seg="dry")
        self.assertEqual([e["id"] for e in m["dry"]["classes"]], ["vloc"])
        self.assertTrue(all("also" not in e for e in m["dry"]["classes"]))
        # Kandla: Panamax is smaller than the Kamsarmax found, Newcastlemax larger than the Capesize ruled out: neither is between
        m = self.entries(["thermal-coal"], draught=14.5, loa=255, seg="dry")
        self.assertTrue(all("also" not in e for e in m["dry"]["classes"]))

    def test_two_rules_that_agree_give_one_class_with_both_bases(self):
        # Primorsk: 150,000 dwt, 55 m beam; the Suezmax standard vessel (48 m beam) is the only tanker with a dimension
        m = self.entries(["crude-oil"], draught=15.5, loa=307, beam=55, dwt=150000)
        (e,) = m["tanker"]["classes"]
        self.assertEqual((e["id"], e["by"]), ("suezmax", "By deadweight and the 55 m beam"))
        self.assertIn("120,000 to 200,000 dwt", e["basis"])

    def test_no_class_from_a_depth_alone(self):
        # Cape Lambert: a water depth of 22.0 m and no size of ship
        self.assertEqual(self.result(["iron-ore"], draught=22.0, depth=True), {})
        self.assertEqual(self.result(["crude-oil"], draught=21), {})
        self.assertIsNone(PL.max_class({"id": "p", "type": "port", "k": ["iron-ore"]}, self.CLASSES))

    def test_a_deadweight_below_the_smallest_band_gives_no_class_whatever_the_dimensions(self):
        self.assertEqual(self.result(["iron-ore"], dwt=9000, loa=150), {})

    def test_a_class_the_page_names_is_the_class(self):
        # Tanjung Bara: wharves of 17.25 m depth "for Capesize ships"; Paradip: "Capesize vessels up to 118,000 dwt"
        self.assertEqual(self.result(["thermal-coal"], draught=17.25, depth=True, cls="capesize"), {"dry": [("capesize", False)]})
        m = PL.max_class(self.port(["met-coal", "crude-oil"], draught=14.5, loa=300, beam=48, dwt=118000, seg="dry", cls="capesize"), self.CLASSES)
        self.assertEqual({s: [e["id"] for e in v["classes"]] for s, v in m.items() if s != "n"}, {"dry": ["capesize"]})
        self.assertEqual(m["dry"]["classes"][0]["by"], "Named by the page")
        self.assertIn("The page itself names this class", m["dry"]["classes"][0]["basis"])

    def test_a_class_measured_in_cubic_metres_has_no_deadweight_band(self):
        # LNG carriers: the band is in cbm, so a deadweight limit gives no class; the standard vessel is compared by length and beam
        self.assertEqual(self.result(["lng"], dwt=200000), {})
        self.assertEqual(self.result(["lng"], loa=350, beam=50), {"gas": [("lng", False)]})

    def test_apply_writes_the_class_after_the_limits_and_removes_a_stale_one(self):
        with tempfile.TemporaryDirectory() as d:
            cp, pp = os.path.join(d, "classes.json"), os.path.join(d, "ports.geojson")
            with open(cp, "w") as fh:
                json.dump(self.CLASSES, fh)
            write(pp, [point("port", "a", "A", "AUS", limits={"draught": 19.8, "dwt": 320000, "depth": True, "n": "x", "s": "wikipedia", "url": "https://x"}, read="2026-11"),
                       point("port", "b", "B", "AUS", maxClass={"dry": "vloc", "n": "old"})])
            PL.apply(pp, cp)
            with open(pp) as fh:
                feats = [f["properties"] for f in json.load(fh)["features"]]
        self.assertEqual(list(feats[0])[-2:], ["maxClass", "read"])
        self.assertEqual([e["id"] for e in feats[0]["maxClass"]["dry"]["classes"]], ["vloc", "capesize"])
        self.assertNotIn("maxClass", feats[1])

    def test_the_real_layer_never_contradicts_its_own_limit(self):
        """GR5S.2: whatever the page shows as a class, the limit printed above it must not exclude it."""
        with open(PL.CLASSES, encoding="utf-8") as fh:
            classes = {c["id"]: c for c in json.load(fh)}
        with open(PL.PORTS, encoding="utf-8") as fh:
            ports = [f["properties"] for f in json.load(fh)["features"]]
        n = 0
        for p in ports:
            m, lim = p.get("maxClass"), p.get("limits") or {}
            for seg, v in (m or {}).items():
                if seg == "n":
                    continue
                for e in v["classes"]:
                    n += 1
                    c = classes[e["id"]]
                    if e["by"] == "Named by the page":
                        continue
                    if e["by"].startswith("By deadweight") and not e.get("orLarger"):
                        self.assertGreater(lim["dwt"], c["size"]["min"], p["id"])
                        self.assertLessEqual(lim["dwt"], c["size"]["max"], p["id"])
                    if e["by"] != "By deadweight":  # a rule by dimensions: the standard vessel is within every figure given
                        for d in ("draught", "loa", "beam"):
                            if isinstance(c["std"].get(d), (int, float)) and isinstance(lim.get(d), (int, float)):
                                self.assertLessEqual(c["std"][d], lim[d], f"{p['id']} {d}")
        self.assertGreater(n, 8)


class PortIndexAsset(unittest.TestCase):
    def test_a_lane_port_whose_code_is_an_asset_carries_it(self):
        COLS = ["o", "d", "kt", "m", "load", "dis", "nm", "cls", "via", "alt", "f"]
        pairs = {"group": "crude-oil", "k": "crude-oil", "y": 2024, "s": "baci", "unit": "kt", "cols": COLS,
                 "ports": [["RUPRI", "Primorsk", "RUS", "baltic", 0, None], ["INSIK", "Sikka", "IND", "wc-india", 0, None]],
                 "rows": [["RUS", "IND", 500, 0, 0, 1, 6000, 0, 0, 0, 4], ["RUS", "CHN", 200, 0, 0, -1, 9000, 0, 0, 0, 4]]}
        with tempfile.TemporaryDirectory() as d:
            for sub in ("pairs", "lanes"):
                os.mkdir(os.path.join(d, sub))
            with open(os.path.join(d, "pairs", "crude-oil.json"), "w") as fh:
                json.dump(pairs, fh)
            infra = os.path.join(d, "ports.geojson")
            write(infra, [point("port", "primorsk", "Primorsk", "RUS", locode="RUPRI")])
            doc = BPI.build(pairs_dir=os.path.join(d, "pairs"), out=os.path.join(d, "p.json"), infra_ports=infra)
        ports = {p["id"]: p for p in doc["ports"]}
        self.assertEqual(ports["RUPRI"]["asset"], "port:primorsk")
        self.assertEqual(ports["RUPRI"]["lanes"], ["crude-oil:RUS-IND", "crude-oil:RUS-CHN"])
        self.assertNotIn("asset", ports["INSIK"])

    def test_a_row_that_is_an_asset_lists_the_other_names_of_the_place(self):
        COLS = ["o", "d", "kt", "m", "load", "dis", "nm", "cls", "via", "alt", "f"]
        pairs = {"group": "corn", "k": "corn", "y": 2024, "s": "baci", "unit": "kt", "cols": COLS,
                 "ports": [["BRSSZ", "Santos", "BRA", "ecsa", 0, None], ["KRPUS", "Pusan", "KOR", "korea", 0, None]],
                 "rows": [["BRA", "KOR", 500, 0, 0, 1, 11000, 0, 0, 0, 4]]}
        with tempfile.TemporaryDirectory() as d:
            for sub in ("pairs", "lanes"):
                os.mkdir(os.path.join(d, sub))
            with open(os.path.join(d, "pairs", "corn.json"), "w") as fh:
                json.dump(pairs, fh)
            infra = os.path.join(d, "ports.geojson")
            write(infra, [point("port", "busan", "Busan", "KOR", locode="KRPUS"),
                          point("port", "santos", "Santos", "BRA", locode="BRSSZ")])
            defs = os.path.join(d, "routes_def.json")
            with open(defs, "w") as fh:
                json.dump([{"id": "x", "cargoes": ["corn"], "from": {"region": "a", "ports": [{"name": "Santos", "c": "BRA"}]},
                            "to": {"region": "b", "ports": [{"name": "Pusan", "c": "KOR"}]}}], fh)
            doc = BPI.build(pairs_dir=os.path.join(d, "pairs"), out=os.path.join(d, "p.json"), infra_ports=infra, routes_def=defs)
        ports = {p["id"]: p for p in doc["ports"]}
        self.assertEqual(ports["KRPUS"]["aka"], ["Pusan"])  # the engine's and the route's name for port:busan
        self.assertNotIn("aka", ports["BRSSZ"])  # the asset's own name is not repeated


if __name__ == "__main__":
    unittest.main()
