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
    CLASSES = [
        {"id": "vloc", "segment": "dry", "std": {"dwt": 400000, "loa": 360, "beam": 65, "draught": 22}},
        {"id": "capesize", "segment": "dry", "std": {"dwt": 182000, "loa": 292, "beam": 45, "draught": 18.2}},
        {"id": "panamax", "segment": "dry", "std": None},
        {"id": "kamsarmax", "segment": "dry", "std": {"dwt": 82500, "loa": 229, "beam": 32.25, "draught": 14.43}},
        {"id": "suezmax", "segment": "tanker", "std": {"dwt": 160000, "beam": 48}},
        {"id": "vlcc", "segment": "tanker", "std": None},
    ]

    def port(self, k, **lim):
        return {"id": "p", "type": "port", "k": k, "limits": {**lim, "n": "berth 1", "s": "wikipedia", "url": "https://x"}}

    def test_the_largest_class_that_fits_every_given_dimension(self):
        self.assertEqual(PL.max_class(self.port(["iron-ore"], draught=19.8, dwt=320000), self.CLASSES)["dry"], "capesize")
        self.assertEqual(PL.max_class(self.port(["iron-ore"], draught=23), self.CLASSES)["dry"], "vloc")
        self.assertEqual(PL.max_class(self.port(["thermal-coal"], draught=16.2), self.CLASSES)["dry"], "kamsarmax")

    def test_a_segment_per_commodity_and_classes_without_a_standard_vessel_are_skipped(self):
        m = PL.max_class(self.port(["crude-oil", "iron-ore"], dwt=350000), self.CLASSES)
        self.assertEqual((m["tanker"], m["dry"]), ("suezmax", "capesize"))  # 400,000 dwt is above the limit
        self.assertIn("vlcc", m["n"])  # named as not compared
        self.assertIn("Atlas estimate", m["n"])

    def test_no_class_when_nothing_fits_or_nothing_compares(self):
        self.assertIsNone(PL.max_class(self.port(["iron-ore"], draught=9), self.CLASSES))
        self.assertIsNone(PL.max_class(self.port(["crude-oil"], draught=21), self.CLASSES))  # Suezmax gives no draught
        self.assertIsNone(PL.max_class({"id": "p", "type": "port", "k": ["iron-ore"]}, self.CLASSES))

    def test_apply_writes_the_class_after_the_limits_and_removes_a_stale_one(self):
        with tempfile.TemporaryDirectory() as d:
            cp, pp = os.path.join(d, "classes.json"), os.path.join(d, "ports.geojson")
            with open(cp, "w") as fh:
                json.dump(self.CLASSES, fh)
            write(pp, [point("port", "a", "A", "AUS", limits={"draught": 19.8, "n": "x", "s": "wikipedia", "url": "https://x"}, read="2026-11"),
                       point("port", "b", "B", "AUS", maxClass={"dry": "vloc", "n": "old"})])
            PL.apply(pp, cp)
            with open(pp) as fh:
                feats = [f["properties"] for f in json.load(fh)["features"]]
        self.assertEqual(list(feats[0])[-2:], ["maxClass", "read"])
        self.assertEqual(feats[0]["maxClass"]["dry"], "capesize")
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


if __name__ == "__main__":
    unittest.main()
