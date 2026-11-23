"""Route ports and the ends of the drawn lines (review GBR1, findings 6 and 13).

A route port name resolves to the engine port of that place (an explicit entry where a name match goes wrong), and the
drawn line of a hand-written route ends within REACH_KM of its ports: a line starts at a node of the sea network, and
where that node is farther, a straight segment that crosses no land joins it to the port.
"""
import json
import math
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "freight"))
ROUTES = os.path.join(ROOT, "data", "freight", "routes.json")
GEO = os.path.join(ROOT, "data", "freight", "routes.geo.json")


def km(a, b):
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


class PortNames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build_freight as BF
        cls.BF = BF

    def test_names_that_a_name_match_resolved_to_another_place(self):
        want = {("Portland", "USA"): "port:portland-oregon", ("Huelva", "ESP"): "port:huelva", ("Acu", "BRA"): "port:acu",
                ("Dongying", "CHN"): "port:dongying", ("Majishan", "CHN"): "port:majishan",
                ("Dalrymple Bay", "AUS"): "AUHPT", ("Busan", "KOR"): "KRPUS", ("St Petersburg", "RUS"): "RULED",
                ("Novorossiysk", "RUS"): "RUNVS", ("Port Klang", "MYS"): "MYPKG"}
        for (name, c), code in want.items():
            self.assertEqual(self.BF.find_port(name, c, "coal"), code, name)

    def test_an_asset_port_takes_the_asset_position(self):
        p = self.BF.route_port("port:acu")
        self.assertEqual((p["name"], p["c"]), ("Acu", "BRA"))
        self.assertEqual(len(p["at"]), 2)

    def test_document_year(self):
        self.assertEqual(self.BF.doc_year("Baltic Exchange, Guide to Market Benchmarks, version 7.09 (December 2025), appendix 2"), 2025)
        self.assertEqual(self.BF.doc_year("Baltic Exchange, Circular 03/26"), 2026)


@unittest.skipUnless(os.path.exists(ROUTES) and os.path.exists(GEO), "data/freight/routes.json not built")
class Lines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(ROUTES, encoding="utf-8") as f:
            cls.routes = {r["id"]: r for r in json.load(f)}
        with open(GEO, encoding="utf-8") as f:
            cls.lines = {x["properties"]["id"]: x["geometry"]["coordinates"] for x in json.load(f)["features"]
                         if x["properties"]["kind"] == "route"}

    def end(self, rid, i):
        c = self.lines[rid][i]
        return [c[0] - 360 * round(c[0] / 360), c[1]]

    def test_hand_written_lines_end_near_their_ports(self):
        far = []
        for rid, r in self.routes.items():
            if r.get("generated"):
                continue
            for i, k in ((0, "a"), (-1, "b")):
                d = km(self.end(rid, i), r[k])
                if d > 100:
                    far.append((rid, k, round(d)))
        self.assertEqual(far, [])

    def test_s8_63_ends_at_paradip(self):
        self.assertLess(km(self.end("S8_63", -1), self.routes["S8_63"]["b"]), 20)

    def test_td6_rounds_the_peloponnese(self):
        # no point of the line in the Gulf of Corinth, and one south of the peninsula
        pts = self.lines["TD6"]
        self.assertFalse([p for p in pts if 21.8 < p[0] < 23.1 and 37.8 < p[1] < 38.5])
        self.assertTrue([p for p in pts if p[1] < 36.2 and 21.5 < p[0] < 23.5])


if __name__ == "__main__":
    unittest.main()
