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

    def test_every_page_says_the_tonnage_from_the_threshold_and_not_below(self):
        """The note of the seaborne figure of each catalogue page (data/commodities/*.json, summary.seaborne), against the mixed tonnage of the lane
        file of its group: the sentence is there when the tonnage is at least 0.005 Mt (5 kt in a kt file), and not otherwise."""
        said = silent = 0
        for f in sorted(glob.glob(os.path.join(DATA, "commodities", "*.json"))):
            doc = load(f)
            sb = ((doc.get("summary") or {}).get("seaborne")) if isinstance(doc, dict) else None
            m = re.search(r"seaborne subset of BACI flows \(([\w-]+)\)", (sb or {}).get("n") or "")
            if not m:
                continue
            lg = load(DATA, "freight", "lanes", m.group(1) + ".json")
            mx = (lg.get("mixed") or [0])[-1]
            u = lg.get("unit") or "Mt"
            n = sb["n"]
            if mx and mx >= 0.005 * (1000 if u == "kt" else 1):
                self.assertIn("that move both by sea and overland (split not known) are not in it", n, f)
                x = re.search(r"; ([\d.,]+) (Mt|kt) that move both", n)
                self.assertEqual(x.group(2), u, f)
                # three significant digits under the old threshold (0.05 Mt, 50 kt), the figures of the note as they were above it
                self.assertEqual(x.group(1), B._fmts(mx, u, under=0.05).split(" ")[0], f)
                if mx < 0.05 * (1000 if u == "kt" else 1):
                    self.assertAlmostEqual(float(x.group(1)), mx, delta=mx * 0.005, msg=f)
                said += 1
            else:
                self.assertNotIn("move both by sea and overland", n, f)
                silent += 1
        self.assertGreater(said, 20)
        self.assertGreater(silent, 5)

    def test_the_pages_below_the_old_threshold_have_the_sentence_now(self):
        """Six pages had a mixed tonnage between 0.005 and 0.05 Mt (5 and 50 kt) and said nothing: chromium, cobalt, ferro-alloys, manganese, palm oil, urea."""
        for k, expected in (("palm-oil", "0.0102 Mt"), ("urea", "0.0385 Mt"), ("cobalt", "5.71 kt"), ("chromium", "0.0196 Mt"), ("ferro-alloys", "0.0242 Mt"),
                            ("manganese", "0.047 Mt")):
            n = load(DATA, "commodities", k + ".json")["summary"]["seaborne"]["n"]
            self.assertIn(f"; {expected} that move both by sea and overland (split not known) are not in it", n, k)


class H3FreightNote(unittest.TestCase):
    def test_the_freight_block_prints_the_sentence_of_the_profile_in_its_note(self):
        """The sentence that says what the percentage after a port is is written in every profile (freight.note) and printed in the note of the block."""
        src = read("web", "src", "components", "views", "CountryBlocks.tsx")
        self.assertIn("{fr.note ??", src)
        self.assertEqual(src.count("cp-fr-note"), 1)
        for iso in ("FRA", "TUR", "MYS"):
            note = load(DATA, "countries", "profiles", iso + ".json")["freight"]["note"]
            self.assertIn("The percentage after a port is the share of the seaborne tonnes", note)


class H7Readme(unittest.TestCase):
    def test_the_times_of_the_suite_and_of_the_recipe_are_the_measured_ones(self):
        text = " ".join(read("README.md").split())
        self.assertRegex(text, r"discover -s pipeline/tests -p \"test_\*\.py\"` \(about \d+ minutes\)")
        self.assertNotIn("about a minute)", text)
