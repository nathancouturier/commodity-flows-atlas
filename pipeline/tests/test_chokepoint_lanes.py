"""The split files of the chokepoint pages (data/freight/chokepoint-lanes/<id>.json): one for every passage of the
catalogue, and together exactly the rows of the whole table. A passage page asks for its own file and falls back to the
whole table (1.8 MB) only when that file fails to load, so a missing file is a 404 on the public site and a download for
nothing.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_chokepoint_lanes.py"
"""
import glob
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FREIGHT = os.path.join(ROOT, "data", "freight")
SPLIT = os.path.join(FREIGHT, "chokepoint-lanes")
sys.path.insert(0, os.path.join(ROOT, "pipeline", "freight"))

import build_chokepoint_lanes as BCL  # noqa: E402


def load(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return json.load(f)


class WriteSplit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.doc = {"s": "atlas", "y": 2024, "unit": "Mt", "n": "note",
                    "groups": {"a": {"k": "x"}, "b": {"k": "y"}},
                    "chokepoints": {"one": [["a", "CHN", "JPN", 5.0, 1]], "two": [["a", "CHN", "KOR", 2.0, 0], ["b", "IND", "JPN", 1.0, 1]]}}

    def files(self):
        return sorted(os.path.basename(f)[:-5] for f in glob.glob(os.path.join(self.tmp.name, "*.json")))

    def test_a_passage_without_a_lane_gets_a_file_with_no_rows(self):
        BCL.write_split(self.doc, self.tmp.name, ["one", "two", "three"])
        self.assertEqual(self.files(), ["one", "three", "two"])
        three = load(self.tmp.name, "three.json")
        self.assertEqual(three["chokepoints"], {"three": []})
        self.assertEqual(three["groups"], {})
        self.assertEqual(three["n"], "note")
        self.assertEqual(set(load(self.tmp.name, "two.json")["groups"]), {"a", "b"})

    def test_a_file_of_a_passage_that_left_the_catalogue_and_has_no_rows_is_removed(self):
        BCL.write_split(self.doc, self.tmp.name, ["one", "two", "gone"])
        BCL.write_split(self.doc, self.tmp.name, ["one", "two"])
        self.assertEqual(self.files(), ["one", "two"])


@unittest.skipUnless(os.path.isdir(SPLIT) and os.path.exists(os.path.join(FREIGHT, "chokepoint-lanes.json")),
                     "the lane files are not in this tree")
class TrackedFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.whole = load(FREIGHT, "chokepoint-lanes.json")
        cls.passages = [c["id"] for c in load(ROOT, "pipeline", "freight", "chokepoints.json")]

    def test_every_passage_of_the_catalogue_has_its_file(self):
        have = {os.path.basename(f)[:-5] for f in glob.glob(os.path.join(SPLIT, "*.json"))}
        self.assertEqual(set(self.passages) - have, set())
        self.assertEqual(have - set(self.passages), set(), "a file for a passage that is not in the catalogue")

    def test_the_files_together_hold_exactly_the_rows_of_the_whole_table(self):
        rows = {}
        for cp in self.passages:
            part = load(SPLIT, cp + ".json")
            self.assertEqual(list(part["chokepoints"]), [cp])
            self.assertIsInstance(part["chokepoints"][cp], list)
            self.assertEqual(part["n"], self.whole["n"], cp)
            # the groups of a file are those its own rows use, with the entries of the whole table
            self.assertEqual(part["groups"], {g: self.whole["groups"][g] for g in {r[0] for r in part["chokepoints"][cp]}}, cp)
            rows[cp] = part["chokepoints"][cp]
        self.assertEqual({cp: r for cp, r in rows.items() if r}, self.whole["chokepoints"])
        self.assertEqual(sum(len(r) for r in rows.values()), sum(len(r) for r in self.whole["chokepoints"].values()))


if __name__ == "__main__":
    unittest.main()
