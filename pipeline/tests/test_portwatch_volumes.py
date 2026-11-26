"""The yearly IMF PortWatch volumes of build_freight.py (pw_volumes): one reading, the tracked weekly series, on every
machine, whether or not the daily table is there to rebuild those series first.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_portwatch_volumes.py"
The made-up series are written to a temporary folder; the test of the tracked files asserts only what holds for every state
the weekly job can leave (no figure of today's data).
"""
import ast
import glob
import inspect
import json
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("freight", "common"):
    p = os.path.join(ROOT, "pipeline", sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import build_freight as BF  # noqa: E402
import build_portwatch as BW  # noqa: E402

SERIES = os.path.join(ROOT, "data", "freight", "portwatch")
TYPES = ("tanker", "dry", "container", "other", "total")


def write_series(folder, cid, start, last, weeks, pid="chokepoint9"):
    """A weekly series file of ``weeks["n"]`` weeks: the other keys of ``weeks`` map a week index to its value (Mt/day, the
    same for every type), 1.0 elsewhere."""
    vals = [weeks.get(i, 1.0) for i in range(weeks["n"])]
    doc = {"id": cid, "portwatch": pid, "start": start, "y": last, "vol": {k: list(vals) for k in TYPES}}
    with open(os.path.join(folder, cid + ".json"), "w") as f:
        json.dump(doc, f)
    return [{"id": cid, "portwatch": pid}]


class Volumes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def read(self, chk):
        return BF.pw_volumes(chk, self.tmp.name)

    def test_each_day_of_a_week_counts_at_the_weeks_mean(self):
        # week 0 starts on Monday 2018-12-31; week 52 is 2019-12-30 .. 2020-01-05 and straddles the turn of the year
        chk = write_series(self.tmp.name, "x", "2018-12-31", "2020-12-31", {"n": 105, 0: 2.0, 52: 3.0})
        v = self.read(chk)["x"]
        # 2019: 6 days of week 0 at 2, 2 days of week 52 at 3, the other 357 days at 1
        self.assertAlmostEqual(v[2019]["all"], 6 * 2 + 2 * 3 + 357, places=9)
        # 2020: 5 days of week 52 at 3, the other 361 days at 1
        self.assertAlmostEqual(v[2020]["all"], 5 * 3 + 361, places=9)
        for t in ("dry", "tanker", "cargo", "all"):
            self.assertIn(t, v[2019])
        # cargo is the container series and the "other" series (general cargo and ro-ro) together
        self.assertAlmostEqual(v[2019]["cargo"], 2 * v[2019]["dry"], places=9)

    def test_a_full_year_has_every_day_inside_the_series(self):
        chk = write_series(self.tmp.name, "x", "2018-12-31", "2020-12-31", {"n": 105})
        self.assertEqual(sorted(self.read(chk)["x"]), [2019, 2020])  # 2018 starts before the series, 2021 after it
        chk = write_series(self.tmp.name, "x", "2018-12-31", "2020-12-30", {"n": 105})
        self.assertEqual(sorted(self.read(chk)["x"]), [2019])  # the data stop on 30 December 2020
        # the series is shorter than the date it declares: the days beyond its last week are not inside it
        chk = write_series(self.tmp.name, "x", "2018-12-31", "2022-06-01", {"n": 105})
        self.assertEqual(sorted(self.read(chk)["x"]), [2019, 2020])
        # a series that starts in the middle of a year has no full year before the next 1 January
        chk = write_series(self.tmp.name, "x", "2019-03-04", "2021-12-30", {"n": 148})
        self.assertEqual(sorted(self.read(chk)["x"]), [2020])
        self.assertAlmostEqual(self.read(chk)["x"][2020]["all"], 366.0, places=9)

    def test_a_record_without_a_counter_or_without_a_file_has_no_volume(self):
        chk = write_series(self.tmp.name, "x", "2018-12-31", "2020-12-31", {"n": 105})
        chk += [{"id": "y", "portwatch": "chokepoint8"}, {"id": "z"}]
        write_series(self.tmp.name, "z", "2018-12-31", "2020-12-31", {"n": 105})
        self.assertEqual(sorted(self.read(chk)), ["x"])

    def test_a_daily_table_changes_nothing(self):
        """The yearly volumes come from the weekly files only: the daily rows, which disagree with them on purpose, are not
        an input (the builder rebuilds the weekly files from them before it reads the volumes)."""
        self.assertEqual(list(inspect.signature(BF.pw_volumes).parameters), ["chk", "series_dir"])
        chk = write_series(self.tmp.name, "x", "2018-12-31", "2020-12-31", {"n": 105})
        before = self.read(chk)
        made_up = [{"date": "2019-01-01", "portid": "chokepoint9", "capacity": 9e12, "capacity_tanker": 9e12}] * 400
        with mock.patch.object(BW, "read_rows", return_value=made_up), mock.patch.object(BW, "read_cache", return_value=made_up), \
                mock.patch.object(BW, "read_pages", return_value=made_up):
            self.assertEqual(self.read(chk), before)

    def test_the_builder_rebuilds_the_weekly_files_before_it_reads_them(self):
        with open(BF.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        calls = {"build": [], "volumes": []}
        for n in ast.walk(main):
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Attribute) and f.attr == "build" and isinstance(f.value, ast.Name) and f.value.id == "BW":
                    calls["build"].append(n.lineno)
                if isinstance(f, ast.Name) and f.id == "pw_volumes":
                    calls["volumes"].append(n.lineno)
        self.assertEqual(len(calls["build"]), 1)
        self.assertEqual(len(calls["volumes"]), 1)
        self.assertLess(calls["build"][0], calls["volumes"][0])


@unittest.skipUnless(glob.glob(os.path.join(SERIES, "*.json")), "the weekly series are not in this tree")
class TrackedSeries(unittest.TestCase):
    """What holds for every state the weekly job can leave of the tracked series."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "data", "freight", "chokepoints.json"), encoding="utf-8") as f:
            cls.chk = json.load(f)
        cls.vol = BF.pw_volumes(cls.chk)

    def test_every_passage_with_a_series_file_is_read(self):
        for c in self.chk:
            if c.get("portwatch") and os.path.exists(os.path.join(SERIES, c["id"] + ".json")):
                self.assertIn(c["id"], self.vol, c["id"])

    def test_years_are_consecutive_and_the_types_add_up_to_the_total(self):
        for cid, years in self.vol.items():
            ys = sorted(years)
            self.assertEqual(ys, list(range(ys[0], ys[-1] + 1)), cid)
            for y, v in years.items():
                # a weekly value is stored to four decimals of Mt/day: the sum of a year differs by far less than 0.1 Mt
                self.assertAlmostEqual(v["all"], v["dry"] + v["tanker"] + v["cargo"], delta=0.1, msg=(cid, y))

    def test_a_year_is_full_only_inside_the_series(self):
        for cid, years in self.vol.items():
            with open(os.path.join(SERIES, cid + ".json"), encoding="utf-8") as f:
                s = json.load(f)
            self.assertGreaterEqual(min(years), int(s["start"][:4]), cid)
            self.assertLessEqual(max(years), int(s["y"][:4]), cid)
            # the series are weeks without a gap: the last week reaches the last day of the data
            n = len(s["vol"]["total"])
            end = date.fromisoformat(s["start"]) + timedelta(days=7 * n - 1)
            self.assertGreaterEqual(end, date.fromisoformat(s["y"]), cid)


if __name__ == "__main__":
    unittest.main()
