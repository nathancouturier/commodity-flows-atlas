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
    # the classes of pipeline/freight/vessel_classes.json as they stood in November 2026 (std and typical size)
    CLASSES = [
        {"id": "capesize", "name": "Capesize", "segment": "dry", "std": {"dwt": 182000, "loa": 292, "beam": 45, "draught": 18.2},
         "size": {"typical": 182000, "u": "dwt"}},
        {"id": "newcastlemax", "name": "Newcastlemax", "segment": "dry", "std": None, "size": {"typical": 185000, "u": "dwt"}},
        {"id": "vloc", "name": "VLOC", "segment": "dry", "std": {"dwt": 400000, "loa": 360, "beam": 65, "draught": 22},
         "size": {"typical": 400000, "u": "dwt"}},
        {"id": "panamax", "name": "Panamax", "segment": "dry", "std": None, "size": {"typical": 74000, "u": "dwt"}},
        {"id": "kamsarmax", "name": "Kamsarmax", "segment": "dry", "std": {"dwt": 82500, "loa": 229, "beam": 32.25, "draught": 14.43},
         "size": {"typical": 82500, "u": "dwt"}},
        {"id": "handysize", "name": "Handysize", "segment": "dry", "std": {"dwt": 38200, "loa": 180, "beam": 29.8, "draught": 10.538},
         "size": {"typical": 38200, "u": "dwt"}},
        {"id": "vlcc", "name": "VLCC", "segment": "tanker", "std": None, "size": {"typical": 300000, "u": "dwt"}},
        {"id": "suezmax", "name": "Suezmax", "segment": "tanker", "std": {"dwt": 160000, "beam": 48}, "size": {"typical": 160000, "u": "dwt"}},
        {"id": "aframax", "name": "Aframax", "segment": "tanker", "std": None, "size": {"typical": 105000, "u": "dwt"}},
        {"id": "lng", "name": "LNG carrier", "segment": "gas", "std": None, "size": {"typical": 174000, "u": "cbm"}},
    ]

    def port(self, k, **lim):
        return {"id": "p", "type": "port", "k": k, "limits": {**lim, "n": "berth 1", "s": "wikipedia", "url": "https://x"}}

    def classes(self, k, **lim):
        m = PL.max_class(self.port(k, **lim), self.CLASSES)
        return {s: c for s, c in (m or {}).items() if s != "n"}

    def test_a_class_without_a_standard_vessel_is_compared_by_its_typical_deadweight(self):
        # LOOP: single buoy moorings for ships of up to 635,000 t; Hound Point: 350,000 dwt. Not "Suezmax".
        self.assertEqual(self.classes(["crude-oil"], dwt=635000), {"tanker": "vlcc"})
        m = PL.max_class(self.port(["crude-oil"], dwt=350000), self.CLASSES)
        self.assertEqual(m["tanker"], "vlcc")
        self.assertIn("VLCC, compared by its typical deadweight (300,000 dwt)", m["n"])
        # Port Hedland: depth 19.8 m and ships of up to 320,000 dwt; the VLOC standard vessel (400,000 dwt) does not fit
        m = PL.max_class(self.port(["iron-ore"], draught=19.8, depth=True, dwt=320000), self.CLASSES)
        self.assertEqual(m["dry"], "newcastlemax")
        self.assertIn("Atlas estimate", m["n"])

    def test_no_class_from_a_depth_alone(self):
        # Cape Lambert: a water depth of 22.0 m and no size of ship
        self.assertEqual(self.classes(["iron-ore"], draught=22.0, depth=True), {})
        self.assertEqual(self.classes(["crude-oil"], draught=21), {})
        self.assertIsNone(PL.max_class({"id": "p", "type": "port", "k": ["iron-ore"]}, self.CLASSES))

    def test_limits_of_one_kind_of_berth_give_that_segment_only(self):
        # Novorossiysk: Sheskharis oil berth 1, 250,000 dwt and 19 m; the port also loads wheat
        m = PL.max_class(self.port(["crude-oil", "refined-products", "wheat"], draught=19, dwt=250000, seg="tanker"), self.CLASSES)
        self.assertEqual({s: c for s, c in m.items() if s != "n"}, {"tanker": "suezmax"})
        self.assertIn("compared by its standard vessel (160,000 dwt)", m["n"])
        self.assertIn("tanker berths", m["n"])
        # without `seg` the same figures would also give a dry class
        self.assertIn("dry", self.classes(["crude-oil", "wheat"], draught=19, dwt=250000))

    def test_the_page_maximum_and_never_a_minimum(self):
        # Kandla: cargo berths of 14.5 m maximum draft for ships of up to 255 m (the 13 m channel is a minimum)
        self.assertEqual(self.classes(["thermal-coal", "palm-oil"], draught=14.5, loa=255, seg="dry"), {"dry": "kamsarmax"})
        # a larger class without a standard vessel is not placed above a smaller one that does not fit
        self.assertEqual(self.classes(["iron-ore"], draught=14, loa=300, beam=50, dwt=220000), {"dry": "panamax"})

    def test_a_class_the_page_names_is_the_class(self):
        # Tanjung Bara: wharves of 17.25 m depth "for Capesize ships"; Paradip: "Capesize vessels up to 118,000 dwt"
        self.assertEqual(self.classes(["thermal-coal"], draught=17.25, depth=True, cls="capesize"), {"dry": "capesize"})
        m = PL.max_class(self.port(["met-coal", "crude-oil"], draught=14.5, loa=300, beam=48, dwt=118000, seg="dry", cls="capesize"), self.CLASSES)
        self.assertEqual({s: c for s, c in m.items() if s != "n"}, {"dry": "capesize"})
        self.assertIn("the class the page itself names", m["n"])

    def test_a_class_measured_in_cubic_metres_is_compared_only_with_a_standard_vessel(self):
        self.assertEqual(self.classes(["lng"], dwt=200000, loa=350), {})

    def test_apply_writes_the_class_after_the_limits_and_removes_a_stale_one(self):
        with tempfile.TemporaryDirectory() as d:
            cp, pp = os.path.join(d, "classes.json"), os.path.join(d, "ports.geojson")
            with open(cp, "w") as fh:
                json.dump(self.CLASSES, fh)
            write(pp, [point("port", "a", "A", "AUS", limits={"draught": 19.8, "dwt": 320000, "n": "x", "s": "wikipedia", "url": "https://x"}, read="2026-11"),
                       point("port", "b", "B", "AUS", maxClass={"dry": "vloc", "n": "old"})])
            PL.apply(pp, cp)
            with open(pp) as fh:
                feats = [f["properties"] for f in json.load(fh)["features"]]
        self.assertEqual(list(feats[0])[-2:], ["maxClass", "read"])
        self.assertEqual(feats[0]["maxClass"]["dry"], "newcastlemax")
        self.assertNotIn("maxClass", feats[1])


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
