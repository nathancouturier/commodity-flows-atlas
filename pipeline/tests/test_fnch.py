"""Tests of the last short package before the sixth release (FNCH).

H1  French grain: the other port is an option of every partner outside the Mediterranean side, the principal port of no pair changed (tests in test_fncf.py, F3)
H2  Bremen has a river leg (tests in test_fnce.py, E1)
H4  the note of the seaborne figure says the tonnage that moves both by sea and overland from the threshold of the panel (0.005 Mt), in three significant digits
H5  the four refinery rows of products loading carry the plant basis (tests in test_fnce.py, E2)
H6  the sentence of Rouen's leg says what the second figure of its page is (tests in test_fnce.py, E1)
H7  the README gives the time of the unit suite as the last run measured it

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The tests of the data files read the files as the builders last wrote them.
"""
import glob
import json
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import build_commodities as B  # noqa: E402

DATA = os.path.join(ROOT, "data")


def load(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return json.load(f)


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class H4MixedTonnageNote(unittest.TestCase):
    def test_the_threshold_of_the_builder_is_the_one_of_the_web(self):
        web = float(re.search(r"MIXED_MIN_MT = ([\d.]+);", read("web", "src", "lib", "mixedShown.ts")).group(1))
        self.assertEqual(B.MIXED_MIN_MT, web)
        self.assertEqual(B.MIXED_MIN_MT, 0.005)

    def test_the_figure_keeps_three_significant_digits_where_two_decimals_would_lose_them(self):
        self.assertEqual(B._fmts(0.0102, "Mt", under=0.05), "0.0102 Mt")  # two decimals would write 0.01
        self.assertEqual(B._fmts(0.0167, "Mt", under=0.05), "0.0167 Mt")  # ... 0.02
        self.assertEqual(B._fmts(0.049, "Mt", under=0.05), "0.049 Mt")
        self.assertEqual(B._fmts(0.07, "Mt", under=0.05), "0.07 Mt")  # from 0.05 Mt, where the note started before, nothing changes
        self.assertEqual(B._fmts(5.71, "kt", under=0.05), "5.71 kt")
        self.assertEqual(B._fmts(0.0004, "Mt"), "0.4 kt")  # the other callers are as before

    def test_every_file_that_moves_the_tonnage_says_it_from_the_threshold_and_not_below(self):
        """The note of the seaborne figure of each catalogue page, read from data/commodities: the sentence is there when the lane file's mixed
        tonnage is at least 0.005 Mt (5 kt in a kt file), and not otherwise."""
        said = missing = checked = 0
        for f in sorted(glob.glob(os.path.join(DATA, "freight", "lanes", "*.json"))):
            lg = load(f)
            mx = (lg.get("mixed") or [0])[-1]
            u = lg.get("unit") or "Mt"
            thr = 0.005 * (1000 if u == "kt" else 1)
            page = os.path.join(DATA, "commodities", lg["group"] + ".json")
            if not os.path.exists(page):
                continue
            n = (load(page).get("seaborne") or {}).get("n") or ""
            checked += 1
            if mx and mx >= thr:
                self.assertIn("that move both by sea and overland (split not known) are not in it", n, lg["group"])
                m = re.search(r"; ([\d.,]+) (Mt|kt) that move both", n)
                self.assertEqual(m.group(2), u, lg["group"])
                self.assertAlmostEqual(float(m.group(1).replace(",", "")), mx, delta=max(mx * 0.005, 0.00005), msg=lg["group"])  # three significant digits
                said += 1
            else:
                self.assertNotIn("move both by sea and overland", n, lg["group"])
                missing += 1
        self.assertGreater(checked, 40)
        self.assertGreater(said, 10)
        self.assertGreater(missing, 5)

    def test_the_groups_below_the_old_threshold_now_have_the_sentence(self):
        """Twelve groups were between 0.005 and 0.05 Mt (5 and 50 kt): their page says it now."""
        for g, expected in (("palm-oil", "0.0102 Mt"), ("ammonium-sulphate", "0.0167 Mt"), ("cobalt", "5.71 kt")):
            n = load(DATA, "commodities", g + ".json")["seaborne"]["n"]
            self.assertIn(f"; {expected} that move both by sea and overland (split not known) are not in it", n, g)


class H7Readme(unittest.TestCase):
    def test_the_times_of_the_suite_and_of_the_recipe_are_the_measured_ones(self):
        text = " ".join(read("README.md").split())
        self.assertRegex(text, r"discover -s pipeline/tests -p \"test_\*\.py\"` \(about \d+ minutes\)")
        self.assertNotIn("about a minute)", text)
