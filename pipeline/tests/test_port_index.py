"""Tests of the port index of the search field (pipeline/freight/build_port_index.py), built from fixture pairs files.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_port_index.py"
"""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "freight"))

import build_port_index as BPI  # noqa: E402

COLS = ["o", "d", "kt", "m", "load", "dis", "nm", "cls", "via", "alt", "f"]


def pairs_file(group, ports, rows, y=2024):
    return {"group": group, "k": group, "y": y, "s": "baci", "unit": "kt", "ports": ports, "cols": COLS, "rows": rows}


def row(o, d, kt, load, dis, flag):
    return [o, d, kt, 0, load, dis, 1000, 0, 0, 0, flag]


class PortIndex(unittest.TestCase):
    def build(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            pdir = os.path.join(tmp, "pairs")
            os.mkdir(pdir)
            for name, doc in files.items():
                with open(os.path.join(pdir, f"{name}.json"), "w", encoding="utf-8") as fh:
                    json.dump(doc, fh)
            out = os.path.join(tmp, "ports.json")
            doc = BPI.build(pairs_dir=pdir, out=out)
            with open(out, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), doc)
            return {p["id"]: p for p in doc["ports"]}

    def test_counts_groups_and_largest_lane(self):
        wheat = pairs_file(
            "wheat",
            [["UAODS", "Odessa", "UKR", "bs", 0, None], ["EGALY", "Alexandria", "EGY", "med", None, 1]],
            [row("UKR", "EGY", 500, 0, 1, 4), row("UKR", "EGY", 900, 0, 1, 0)],
        )
        corn = pairs_file(
            "corn",
            [["UAODS", "Odessa", "UKR", "bs", 0, None], ["ESBCN", "Barcelona", "ESP", "med", None, 1]],
            [row("UKR", "ESP", 700, 0, 1, 4)],
        )
        p = self.build({"wheat": wheat, "corn": corn})
        self.assertEqual(set(p), {"UAODS", "EGALY", "ESBCN"})
        odessa = p["UAODS"]
        # n: the pairs that use the port, over every file; g: its groups, the largest tonnage first
        self.assertEqual(odessa["n"], 3)
        self.assertEqual(odessa["g"], ["wheat", "corn"])
        # the largest pair that has a lane page (flag 4): 700 kt of corn, not the 900 kt pair without one
        self.assertEqual(odessa["lane"], "corn:UKR-ESP")
        self.assertEqual(p["EGALY"]["lane"], "wheat:UKR-EGY")

    def test_a_port_with_no_lane_page_has_none(self):
        steel = pairs_file("steel", [["ANKRA", "Kralendijk", "ANT", "car", None, 0]], [row("CHN", "ANT", 10, None, 0, 0)])
        self.assertIsNone(self.build({"steel": steel})["ANKRA"]["lane"])

    def test_a_port_the_pairs_no_longer_use_is_not_kept(self):
        before = pairs_file("lpg", [["QAHLL", "Halul", "QAT", "g", 0, None]], [row("QAT", "CHN", 50, 0, None, 4)])
        after = pairs_file("lpg", [["QAHLL", "Halul", "QAT", "g", 0, None]], [row("QAT", "CHN", 50, None, None, 4)])
        self.assertIn("QAHLL", self.build({"lpg": before}))
        self.assertNotIn("QAHLL", self.build({"lpg": after}))

    def test_years_and_note(self):
        a = pairs_file("a", [["XX1", "One", "AAA", "z", 0, None]], [row("AAA", "BBB", 1, 0, None, 4)], y=2023)
        b = pairs_file("b", [["XX2", "Two", "BBB", "z", None, 0]], [row("AAA", "BBB", 1, None, 0, 4)], y=2024)
        with tempfile.TemporaryDirectory() as tmp:
            os.mkdir(os.path.join(tmp, "pairs"))
            for n, d in (("a", a), ("b", b)):
                with open(os.path.join(tmp, "pairs", f"{n}.json"), "w") as fh:
                    json.dump(d, fh)
            doc = BPI.build(pairs_dir=os.path.join(tmp, "pairs"), out=os.path.join(tmp, "p.json"))
        self.assertEqual(doc["y"], "2023-2024")
        self.assertEqual(doc["s"], "atlas")


if __name__ == "__main__":
    unittest.main()
