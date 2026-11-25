"""Tests of the digest of the freight market page (pipeline/freight/build_market_now.py, data/freight/market-now.json) and of its
step in the weekly PortWatch job.

The first half runs on small series written to a temporary folder (the window, the ranking, every refusal, the status record);
the second half reads the published files: the digest equals the digest of the weekly series as they are, it agrees with the
28-day comparison of the alert banners, and the workflow, the status thresholds and the documentation name the step. Nothing
here reads raw/, the daily table or chokepoints.json, and nothing is typed from the data: a figure is read from a file.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_market_now.py"
"""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("", "common", "freight"):
    p = os.path.join(ROOT, "pipeline", sub) if sub else os.path.join(ROOT, "pipeline")
    if p not in sys.path:
        sys.path.insert(0, p)

import build_market_now as BM  # noqa: E402
from common import status  # noqa: E402  (the module the script imports: the one the tests redirect)
from test_update_jobs import workflow_steps  # noqa: E402

FREIGHT = os.path.join(ROOT, "data", "freight")
SERIES = os.path.join(FREIGHT, "portwatch")
PUBLISHED = os.path.join(FREIGHT, "market-now.json")
START = date(2018, 12, 31)   # a Monday, as the first week of the published series


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def slurp(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def week_values(pid, kind, weeks, fn=None):
    """The values of one list of a small series: ``fn(week)`` or a gentle ramp that differs by passage and by list."""
    seed = sum(ord(c) for c in pid) % 7 + 1
    base = {"tanker": 3.0, "dry": 2.0, "vol.tanker": 0.05, "vol.dry": 0.03}[kind]
    return [round(fn(i) if fn else base * seed * (1 + (i % 5) / 10), 4) for i in range(weeks)]


def series_doc(pid, weeks=120, last_day=None, **lists):
    """A weekly file as build_portwatch.py writes it, with the lists the digest reads (and nothing else it does not need)."""
    last = last_day or START + timedelta(days=7 * weeks - 1)
    doc = {"id": pid, "s": "portwatch", "y": str(last), "start": str(START), "step": "week",
           "tanker": week_values(pid, "tanker", weeks), "dry": week_values(pid, "dry", weeks),
           "vol": {"unit": "Mt/day (weekly average)", "tanker": week_values(pid, "vol.tanker", weeks), "dry": week_values(pid, "vol.dry", weeks)}}
    for k, v in lists.items():
        if k.startswith("vol_"):
            doc["vol"][k[4:]] = v
        else:
            doc[k] = v
    return doc


class Folder(unittest.TestCase):
    """A temporary data/freight/portwatch folder, an output path, and a status file that is not the real one."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dir = os.path.join(self.tmp, "portwatch")
        os.makedirs(self.dir)
        self.out = os.path.join(self.tmp, "market-now.json")
        self.patch = mock.patch.multiple(status, UPDATES=os.path.join(self.tmp, "updates.json"),
                                         LOG=os.path.join(self.tmp, "log.jsonl"), JOURNAL=os.path.join(self.tmp, "journal"))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def main(self):
        """Run the script's main on the small folder; what it prints is part of the job's log, not of the test's."""
        with contextlib.redirect_stdout(io.StringIO()) as out:
            BM.main(self.dir, self.out)
        return out.getvalue()

    def put(self, doc, name=None):
        with open(os.path.join(self.dir, (name or doc["id"]) + ".json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    def seven(self, **kw):
        for pid in ("aa", "bb", "cc", "dd", "ee", "ff", "gg"):
            self.put(series_doc(pid, **kw))

    def rows(self, t):
        doc, _ = BM.build(self.dir)
        return {r["id"]: r for r in doc["types"][t]}


class TheWindows(Folder):
    def test_the_window_is_the_four_weeks_that_end_on_the_last_sunday_and_the_same_four_weeks_364_days_earlier(self):
        weeks = 120
        self.put(series_doc("aa", weeks, tanker=[float(i + 1) for i in range(weeks)]))
        for pid in ("bb", "cc", "dd", "ee", "ff"):
            self.put(series_doc(pid, weeks))
        doc, rows = BM.build(self.dir)
        last = START + timedelta(days=7 * weeks - 1)
        self.assertEqual(doc["to"], str(last))
        self.assertEqual(date.fromisoformat(doc["to"]).weekday(), 6)
        self.assertEqual(doc["yearAgoTo"], str(last - timedelta(days=364)))
        self.assertEqual((doc["weeks"], doc["days"], doc["rankWeeks"], rows), (4, 28, 52, 10))
        r = {x["id"]: x for x in doc["types"]["tanker"]}["aa"]
        # weekly means 117..120, the same four weeks 52 weeks back are 65..68: each week is 7 days of its mean
        self.assertEqual(r["now"], 7 * (117 + 118 + 119 + 120))
        self.assertEqual(r["ago"], 7 * (65 + 66 + 67 + 68))

    def row(self, t, pid):
        doc, _ = BM.build(self.dir)
        return {r["id"]: r for r in doc["types"][t]}[pid]

    def test_the_vessels_are_whole_and_half_a_vessel_goes_up(self):
        w = 120
        tenths = [0.4, 0.4, 0.4, 0.3]          # 7 x 1.5 = 10.5 vessels: banker's rounding of a float would say 10
        self.put(series_doc("aa", w, tanker=[0.0] * (w - 4) + tenths))
        for pid in ("bb", "cc", "dd", "ee", "ff"):
            self.put(series_doc(pid, w))
        self.assertEqual(self.row("tanker", "aa")["now"], 11)
        self.assertIsInstance(self.row("tanker", "aa")["now"], int)

    def test_the_cargo_has_three_significant_figures_and_whole_tonnes_stay_whole(self):
        w = 120
        self.put(series_doc("aa", w, vol_tanker=[1.0] * (w - 4) + [0.0098] * 4))     # 4 weeks x 7 x 0.0098 = 0.2744 Mt now, 28 Mt a year back
        self.put(series_doc("bb", w, vol_tanker=[12.3456] * w))    # 345.6768 Mt
        for pid in ("cc", "dd", "ee", "ff"):
            self.put(series_doc(pid, w))
        a = self.row("tanker", "aa")
        self.assertEqual((a["mt"]["now"], a["mt"]["ago"]), (0.274, 28))
        self.assertEqual(self.row("tanker", "bb")["mt"]["now"], 346)
        self.assertIsInstance(self.row("tanker", "bb")["mt"]["now"], int)
        # the ranking figure: 52 weeks x 7 x 12.3456 = 4493.6 Mt, three figures
        self.assertEqual(self.row("tanker", "bb")["rankMt"], 4490)

    def test_the_last_week_is_dropped_when_the_last_day_is_not_a_sunday(self):
        w = 120
        wednesday = START + timedelta(days=7 * w + 2)           # three days of week 121
        for pid in ("aa", "bb", "cc", "dd", "ee", "ff"):
            doc = series_doc(pid, w)
            for k in ("tanker", "dry"):
                doc[k].append(9999.0)
            for k in ("tanker", "dry"):
                doc["vol"][k].append(999.0)
            doc["y"] = str(wednesday)
            self.put(doc)
        doc, _ = BM.build(self.dir)
        self.assertEqual(doc["to"], str(START + timedelta(days=7 * w - 1)))
        self.assertTrue(all(r["now"] < 9999 and r["mt"]["now"] < 999 for t in doc["types"].values() for r in t))

    def test_a_file_that_ends_a_week_earlier_sets_the_date_and_every_window_is_taken_by_date(self):
        w = 120
        self.seven(weeks=w)
        # one passage whose data stop a week before the others: the digest ends on that week, for every passage
        self.put(series_doc("gg", w - 1))
        doc, _ = BM.build(self.dir)
        self.assertEqual(doc["to"], str(START + timedelta(days=7 * (w - 1) - 1)))
        # the same digest as when every file stops on that week: the window of the others moved with it, not their last values
        ref = tempfile.mkdtemp()
        try:
            for pid in ("aa", "bb", "cc", "dd", "ee", "ff", "gg"):
                with open(os.path.join(ref, pid + ".json"), "w") as fh:
                    json.dump(series_doc(pid, w - 1), fh)
            self.assertEqual(BM.build(ref)[0]["types"]["tanker"], doc["types"]["tanker"])
        finally:
            shutil.rmtree(ref)


class TheRanking(Folder):
    def test_the_five_passages_are_the_largest_cargo_a_year_back_ties_by_id_and_a_collapse_this_year_does_not_remove_one(self):
        w = 120
        # cargo of the 52 weeks that end a year back (weeks 16..67 of 120), then the last four weeks
        ids = ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"]
        big = {"p1": 5.0, "p2": 4.0, "p3": 3.0, "p4": 3.0, "p5": 2.0, "p6": 1.9, "p7": 9.0, "p8": 0.1}
        for pid in ids:
            v = [big[pid] if i < w - 52 else 0.0 for i in range(w)]       # up to a year back, then nothing
            if pid == "p7":
                v = [0.0] * (w - 52 - 52) + [big[pid]] * 52 + [0.0] * 52   # busy before the year-back window ends, then not at all
            self.put(series_doc(pid, w, vol_tanker=v))
        rows = BM.build(self.dir)[0]["types"]["tanker"]
        self.assertEqual([r["id"] for r in rows], ["p7", "p1", "p2", "p3", "p4"])      # p3 before p4: the same cargo, the id decides
        self.assertEqual(len({r["rankMt"] for r in rows}), 4)
        self.assertEqual(rows[3]["rankMt"], rows[4]["rankMt"])
        self.assertTrue(all(rows[i]["rankMt"] >= rows[i + 1]["rankMt"] for i in range(4)))
        # nothing carried now: the passages are still there, with their year-earlier figures
        self.assertTrue(all(r["mt"]["now"] == 0 and r["mt"]["ago"] > 0 for r in rows))

    def test_a_passage_may_rank_in_both_lists_and_the_two_lists_are_ranked_apart(self):
        self.seven(weeks=120)
        doc = BM.build(self.dir)[0]
        self.assertEqual(sorted(doc["types"]), ["dry", "tanker"])
        self.assertEqual([len(v) for v in doc["types"].values()], [5, 5])
        both = {r["id"] for r in doc["types"]["tanker"]} & {r["id"] for r in doc["types"]["dry"]}
        self.assertTrue(both, "the small series are built so that a passage ranks in both lists")

    def test_the_file_holds_no_name_and_no_gas_class(self):
        self.seven(weeks=120)
        doc = BM.build(self.dir)[0]
        text = json.dumps(doc)
        self.assertNotIn('"name"', text)
        self.assertNotIn("gas", text.lower())
        self.assertEqual(set(doc), {"s", "to", "yearAgoTo", "weeks", "days", "rankWeeks", "unit", "mtUnit", "types"})
        for r in doc["types"]["dry"]:
            self.assertEqual(set(r), {"id", "now", "ago", "mt", "rankMt"})


class Refusals(Folder):
    """Each way the weekly files can disagree with the digest's reading is refused; ``main`` keeps the file, records the failure, returns."""

    def refused(self, fragment):
        with self.assertRaises(ValueError) as cm:
            BM.build(self.dir)
        self.assertIn(fragment, str(cm.exception))

    def test_a_week_that_went_missing_is_refused_and_not_read_by_position(self):
        """build_portwatch.py drops a week with no row: every later value then belongs to the week before the one its position says."""
        self.seven(weeks=120)
        doc = series_doc("gg", 120)
        for k in ("tanker", "dry"):
            del doc[k][60]
        for k in ("tanker", "dry"):
            del doc["vol"][k][60]
        self.put(doc)
        self.refused("a week is missing or extra")

    def test_an_extra_week_is_refused_too(self):
        self.seven(weeks=120)
        doc = series_doc("gg", 120)
        for k in ("tanker", "dry"):
            doc[k].append(1.0)
        for k in ("tanker", "dry"):
            doc["vol"][k].append(0.1)
        self.put(doc)
        self.refused("a week is missing or extra")

    def test_a_series_that_stops_before_the_digest_can_look_back_is_refused(self):
        self.seven(weeks=120)
        self.put(series_doc("gg", 100))
        self.refused("no week ends on")

    def test_lists_of_different_lengths_a_missing_vol_a_missing_list_and_a_start_that_is_not_a_monday_are_refused(self):
        self.seven(weeks=120)
        doc = series_doc("gg", 120)
        doc["dry"].pop()
        self.put(doc)
        self.refused("different lengths")
        doc = series_doc("gg", 120)
        del doc["vol"]
        self.put(doc)
        self.refused("no vol block")
        doc = series_doc("gg", 120)
        del doc["vol"]["dry"]
        self.put(doc)
        self.refused("no vol.dry list")
        doc = series_doc("gg", 120)
        del doc["tanker"]
        self.put(doc)
        self.refused("no tanker list")
        doc = series_doc("gg", 120)
        doc["start"] = str(START + timedelta(days=1))
        self.put(doc)
        self.refused("not a Monday")
        doc = series_doc("gg", 120)
        doc["y"] = "not a date"
        self.put(doc)
        self.refused("start and y must be dates")

    def test_a_series_that_is_not_the_one_its_file_name_says_is_refused(self):
        self.seven(weeks=120)
        self.put(series_doc("hh", 120), name="gg")
        self.refused("not the series of gg")

    def test_a_value_that_is_not_a_finite_number_or_is_negative_is_refused(self):
        self.seven(weeks=120)
        for bad, fragment in ((-0.1, "negative"), ("3", "not a number"), (None, "not a number"), (True, "not a number"),
                              (float("nan"), "not a finite number"), (float("inf"), "not a finite number")):
            for where in ("tanker", "vol_dry"):
                lst = week_values("gg", "tanker" if where == "tanker" else "vol.dry", 120)
                lst[7] = bad
                self.put(series_doc("gg", 120, **{where: lst}))
                self.refused(fragment)
        self.put(series_doc("gg", 120))
        BM.build(self.dir)   # the same folder with a good file is read

    def test_fewer_than_five_series_are_refused_and_a_series_that_cannot_be_read_stops_the_digest(self):
        for pid in ("aa", "bb", "cc", "dd"):
            self.put(series_doc(pid))
        self.refused("at least 5 are needed")
        self.put(series_doc("ee"))
        BM.build(self.dir)
        with open(os.path.join(self.dir, "ff.json"), "w") as fh:
            fh.write('{"id":"ff",')
        with self.assertRaises(ValueError):
            BM.build(self.dir)

    def test_main_keeps_the_file_records_the_failure_and_returns(self):
        self.seven(weeks=120)
        self.main()
        with open(self.out, encoding="utf-8") as fh:
            kept = fh.read()
        self.assertEqual(status.get("build-market-now")["consecutive_failures"], 0)
        self.assertEqual(status.get("build-market-now")["records"], 10)
        # a series that lost a week
        doc = series_doc("gg", 120)
        for k in ("tanker", "dry"):
            del doc[k][60]
        for k in ("tanker", "dry"):
            del doc["vol"][k][60]
        self.put(doc)
        self.main()                    # returns: the job goes on
        with open(self.out, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), kept)
        e = status.get("build-market-now")
        self.assertEqual(e["consecutive_failures"], 1)
        self.assertIn("a week is missing or extra", e["last_error"])
        self.assertEqual(e["data_to"], json.loads(kept)["to"])   # the record keeps the date of the file that stays
        self.assertEqual(e["alert_after"], 3)

    def test_a_digest_that_ends_earlier_than_the_one_published_is_refused(self):
        self.seven(weeks=120)
        self.main()
        with open(self.out, encoding="utf-8") as fh:
            before = fh.read()
        self.seven(weeks=119)                           # a rebuild from older files
        self.main()
        with open(self.out, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)
        self.assertEqual(status.get("build-market-now")["consecutive_failures"], 1)
        self.assertIn("earlier than the one published", status.get("build-market-now")["last_error"])
        # a later one is taken, and an unreadable published file does not stop a build
        self.seven(weeks=121)
        self.main()
        with open(self.out, encoding="utf-8") as fh:
            self.assertEqual(json.loads(fh.read())["to"], str(START + timedelta(days=7 * 121 - 1)))
        with open(self.out, "w") as fh:
            fh.write("not json")
        self.main()
        self.assertEqual(status.get("build-market-now")["consecutive_failures"], 0)

    def test_an_error_that_is_none_of_the_expected_ones_is_recorded_too_and_does_not_escape(self):
        self.seven(weeks=120)
        with mock.patch.object(BM, "build", side_effect=ZeroDivisionError("boom")), mock.patch("traceback.print_exc"):
            self.main()
        self.assertEqual(status.get("build-market-now")["consecutive_failures"], 1)
        self.assertFalse(os.path.exists(self.out))


class Rewriting(Folder):
    def test_an_identical_rebuild_does_not_rewrite_the_file_and_a_different_one_does(self):
        self.seven(weeks=120)
        self.main()
        first = os.stat(self.out).st_mtime_ns
        time.sleep(0.05)
        self.main()
        self.assertEqual(os.stat(self.out).st_mtime_ns, first)
        self.assertEqual(status.get("build-market-now")["consecutive_failures"], 0)
        self.assertFalse(os.path.exists(self.out + ".tmp"))
        doc = series_doc("aa", 120, tanker=[1.0] * 120)
        self.put(doc)
        self.main()
        self.assertNotEqual(os.stat(self.out).st_mtime_ns, first)

    def test_the_file_is_compact_and_ends_with_a_newline(self):
        self.seven(weeks=120)
        self.main()
        with open(self.out, encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.endswith("}\n"))
        self.assertNotIn("\n", text[:-1])
        self.assertNotIn(": ", text)


class AsAScript(unittest.TestCase):
    """The script as the job runs it, in a copy of the tree that has no raw/ and no pipeline/cache/portwatch."""

    def tree(self, tmp, series_from=SERIES):
        os.makedirs(os.path.join(tmp, "pipeline", "freight"))
        os.makedirs(os.path.join(tmp, "pipeline", "common"))
        shutil.copy(os.path.join(ROOT, "pipeline", "freight", "build_market_now.py"), os.path.join(tmp, "pipeline", "freight"))
        shutil.copy(os.path.join(ROOT, "pipeline", "common", "status.py"), os.path.join(tmp, "pipeline", "common"))
        shutil.copytree(series_from, os.path.join(tmp, "data", "freight", "portwatch"))

    def run_script(self, tmp):
        return subprocess.run([sys.executable, "-I", os.path.join(tmp, "pipeline", "freight", "build_market_now.py")], cwd=tmp,
                              capture_output=True, text=True)

    @unittest.skipUnless(os.path.exists(PUBLISHED), "no published digest yet")
    def test_in_a_copy_of_the_tree_without_raw_and_the_daily_table_the_script_gives_the_published_file(self):
        tmp = tempfile.mkdtemp()
        try:
            self.tree(tmp)
            self.assertFalse(os.path.exists(os.path.join(tmp, "raw")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "pipeline", "cache")))
            r = self.run_script(tmp)
            self.assertEqual(r.returncode, 0, r.stderr)
            made = slurp(tmp, "data", "freight", "market-now.json")
            if json.loads(made)["to"] != json.loads(read("data", "freight", "market-now.json"))["to"]:
                self.skipTest("the published digest is of an earlier week than the weekly files (its step failed: the failure is recorded and alerted)")
            self.assertEqual(made, read("data", "freight", "market-now.json"))
            st = json.loads(slurp(tmp, "data", "_status", "updates.json"))["sources"]["build-market-now"]
            self.assertEqual((st["consecutive_failures"], st["records"]), (0, 10))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @unittest.skipUnless(os.path.exists(PUBLISHED), "no published digest yet")
    def test_a_copy_with_a_series_that_lost_a_week_keeps_the_old_file_records_the_failure_and_exits_0(self):
        tmp = tempfile.mkdtemp()
        try:
            self.tree(tmp)
            old = '{"to":"2026-01-04","old":true}\n'
            with open(os.path.join(tmp, "data", "freight", "market-now.json"), "w", encoding="utf-8") as fh:
                fh.write(old)
            path = os.path.join(tmp, "data", "freight", "portwatch", "malacca.json")
            doc = json.loads(slurp(path))
            for k in ("tanker", "dry", "container", "other", "total"):
                del doc[k][100]
            for k in ("tanker", "dry", "container", "other", "total"):
                del doc["vol"][k][100]
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            r = self.run_script(tmp)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("previous file kept", r.stdout)
            self.assertEqual(slurp(tmp, "data", "freight", "market-now.json"), old)
            st = json.loads(slurp(tmp, "data", "_status", "updates.json"))["sources"]["build-market-now"]
            self.assertEqual(st["consecutive_failures"], 1)
            self.assertIn("a week is missing or extra", st["last_error"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipUnless(os.path.exists(PUBLISHED), "no published digest yet")
class ThePublishedDigest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(read("data", "freight", "market-now.json"))
        cls.built, _ = BM.build(SERIES)
        cls.series = {}
        for f in os.listdir(SERIES):
            if f.endswith(".json"):
                with open(os.path.join(SERIES, f), encoding="utf-8") as fh:
                    cls.series[os.path.splitext(f)[0]] = json.load(fh)

    def current(self):
        if self.doc["to"] != self.built["to"]:
            self.skipTest("the published digest is of an earlier week than the weekly files: its step failed, which is recorded and alerted")

    def test_the_published_file_is_the_digest_of_the_weekly_files_as_they_are(self):
        self.current()
        self.assertEqual(read("data", "freight", "market-now.json"), BM.text_of(self.built))

    def test_the_shape_the_page_reads(self):
        d = self.doc
        self.assertEqual((d["s"], d["weeks"], d["days"], d["rankWeeks"]), ("portwatch", 4, 28, 52))
        self.assertEqual(date.fromisoformat(d["to"]) - date.fromisoformat(d["yearAgoTo"]), timedelta(days=364))
        self.assertEqual(date.fromisoformat(d["to"]).weekday(), 6)
        self.assertEqual((d["unit"], d["mtUnit"]), (BM.UNIT, BM.MT_UNIT))
        self.assertEqual(sorted(d["types"]), ["dry", "tanker"])
        for t, rows in d["types"].items():
            self.assertEqual(len(rows), 5, t)
            self.assertEqual(len({r["id"] for r in rows}), 5, t)
            self.assertTrue(all(r["id"] in self.series for r in rows), t)
            self.assertTrue(all(rows[i]["rankMt"] >= rows[i + 1]["rankMt"] for i in range(4)), t)
            for r in rows:
                self.assertEqual(set(r), {"id", "now", "ago", "mt", "rankMt"})
                self.assertIsInstance(r["now"], int)
        self.assertNotIn('"name"', read("data", "freight", "market-now.json"))

    def test_each_figure_is_the_weekly_means_of_its_file_times_seven(self):
        """Recomputed here by position, which is right on the published files because each one has every week (a test above refuses one that has not)."""
        self.current()
        for t, rows in self.doc["types"].items():
            for r in rows:
                s = self.series[r["id"]]
                n = len(s[t])
                self.assertEqual(n, (date.fromisoformat(s["y"]) - date.fromisoformat(s["start"])).days // 7 + 1, r["id"])
                last = n - 1 if date.fromisoformat(s["y"]).weekday() == 6 else n - 2
                end = date.fromisoformat(s["start"]) + timedelta(days=7 * last + 6)
                self.assertEqual(str(end), self.doc["to"], r["id"])
                now, ago = last - 3, last - 3 - 52
                self.assertAlmostEqual(r["now"], 7 * sum(s[t][now:now + 4]), delta=0.5 + 1e-6, msg=r["id"])
                self.assertAlmostEqual(r["ago"], 7 * sum(s[t][ago:ago + 4]), delta=0.5 + 1e-6, msg=r["id"])
                for key, lo in (("now", now), ("ago", ago)):
                    exact = 7 * sum(s["vol"][t][lo:lo + 4])
                    self.assertAlmostEqual(r["mt"][key], exact, delta=max(abs(exact) * 0.0051, 1e-9), msg=(r["id"], key))
                rk = last - 52 - 51
                exact = 7 * sum(s["vol"][t][rk:rk + 52])
                self.assertAlmostEqual(r["rankMt"], exact, delta=max(exact * 0.0051, 1e-9), msg=r["id"])
        # and no passage outside the five carries more of that type a year back than the fifth
        for t, rows in self.doc["types"].items():
            fifth = rows[-1]["rankMt"]
            for pid, s in self.series.items():
                last = len(s[t]) - 1 if date.fromisoformat(s["y"]).weekday() == 6 else len(s[t]) - 2
                rk = last - 52 - 51
                if pid not in {r["id"] for r in rows}:
                    self.assertLessEqual(7 * sum(s["vol"][t][rk:rk + 52]), fifth * 1.0051, (t, pid))

    def test_the_four_weeks_agree_with_the_28_days_of_the_alert_banners_within_the_rounding_of_the_weekly_means(self):
        """The banners' ``compare`` is summed from the daily table, the digest from weekly means rounded to 0.1 vessels a day (4 weeks x 7 days
        x 0.05 = 1.4 vessels at most) and, for the cargo, to four decimals. Read on all ships: ``compare`` has no ship type."""
        self.current()
        checked = 0
        for pid, s in self.series.items():
            c = s["compare"]
            if c["to"] != self.doc["to"]:
                continue
            n = len(s["total"]) - (0 if date.fromisoformat(s["y"]).weekday() == 6 else 1)
            for lo, key in ((n - 4, "now"), (n - 56, "yearAgo")):
                self.assertAlmostEqual(7 * sum(s["total"][lo:lo + 4]), c["transits"][key], delta=1.4, msg=(pid, key))
                self.assertAlmostEqual(7 * sum(s["vol"]["total"][lo:lo + 4]), c["mt"][key], delta=0.01, msg=(pid, key))
            self.assertEqual(c["yearAgoTo"], self.doc["yearAgoTo"], pid)
            checked += 1
        self.assertGreaterEqual(checked, 5)


class TheStepInTheJob(unittest.TestCase):
    """The step is in every place that follows the alert banners in the weekly job; it alerts after three failed runs, as a weekly source."""

    @classmethod
    def setUpClass(cls):
        cls.wf = read(".github", "workflows", "update-portwatch.yml")

    def test_the_step_runs_the_script_after_the_alert_banners_and_before_the_digest_of_changes(self):
        names = re.findall(r"^      - name: (.+)$", self.wf, re.M)
        i = names.index("Rebuild the freight market digest from the new series")
        self.assertEqual(names[i - 1], "Rebuild the alert banners from the new series")
        self.assertEqual(names[i + 1], 'Update the "what changed" digest and feed')
        block = self.wf[self.wf.index("Rebuild the freight market digest"):self.wf.index('Update the "what changed"')]
        self.assertIn("id: market", block)
        self.assertIn("continue-on-error: true", block)
        self.assertIn("timeout-minutes: 5", block)
        self.assertIn("run: python pipeline/freight/build_market_now.py\n", block)
        self.assertNotIn("--", block.split("run:")[1])

    def test_the_finish_step_records_validates_and_commits_it_with_the_other_sources(self):
        self.assertIn('sources: "portwatch portwatch-port-traffic build-alerts build-market-now build-changes"', self.wf)
        self.assertIn("${{ steps.market.outcome }} build-market-now", self.wf)
        paths = re.search(r'^\s+paths: "([^"]+)"', self.wf, re.M).group(1).split()
        self.assertIn("data/freight/market-now.json", paths)
        # nothing else of data/freight is added: the series, the port series and the alerts keep their own paths
        self.assertIn("data/freight/alerts.json", paths)

    def test_a_job_with_the_step_still_ends_green_every_script_step_continues_on_error_and_the_limits_add_up(self):
        steps, job_limit = workflow_steps(self.wf)
        for x in steps:
            if x.get("run") and "timeout-minutes" in x:
                self.assertEqual(x.get("continue-on-error"), "true", x.get("name"))
        limits = [int(x["timeout-minutes"]) for x in steps if "timeout-minutes" in x]
        self.assertEqual(sum(limits), 10 + 5 + 25 + 15 + 1 + 5 + 5 + 5)
        self.assertGreaterEqual(job_limit, sum(limits) + 15)

    def test_the_header_of_the_workflow_names_the_step_and_its_alert_threshold(self):
        head = self.wf.split("name: Update PortWatch")[0]
        self.assertIn("freight market digest (data/freight/market-now.json", head)
        self.assertIn("after the banners and after the", head)
        self.assertIn("at the first failure of the alert banners; the digest, whose inputs change every week, waits for three like a source", head)
        self.assertIn("71 minutes (10 + 5 + 25 + 15 + 1 + 5 + 5 + 5)", self.wf)

    def test_the_step_is_a_build_step_that_alerts_after_three_runs_like_a_weekly_source_not_at_its_first_failure(self):
        self.assertIn("build-market-now", status.BUILD_STEPS)
        self.assertEqual(status.ALERT_AFTER_SOURCE.get("build-market-now", status.ALERT_AFTER), 3)
        self.assertEqual(status.ALERT_AFTER_SOURCE["build-alerts"], 1)      # the neighbour keeps its first-failure rule
        tmp = tempfile.mkdtemp()
        try:
            with mock.patch.multiple(status, UPDATES=os.path.join(tmp, "u.json"), LOG=os.path.join(tmp, "l.jsonl")):
                status.record_failure("build-market-now", "ValueError: x")
                self.assertNotIn("build-market-now", status.failing())
                status.record_failure("build-market-now", "ValueError: x")
                self.assertNotIn("build-market-now", status.failing())
                status.record_failure("build-market-now", "ValueError: x")
                self.assertIn("build-market-now", status.failing())
                self.assertEqual(status.get("build-market-now")["alert_after"], 3)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_script_uses_no_network_and_reads_nothing_it_does_not_need(self):
        src = read("pipeline", "freight", "build_market_now.py")
        imports = set(re.findall(r"^(?:import|from) ([\w.]+)", src, re.M))
        self.assertFalse(imports & {"requests", "urllib", "urllib3", "http", "socket", "ftplib", "fetch", "pandas"}, imports)
        # the paths it opens: the weekly series and its own file, nothing else
        opened = set(re.findall(r'os\.path\.join\(([^)]*)\)', src))
        for what in ('"raw"', '"cache"', "chokepoints", "alerts", "port-traffic"):
            self.assertFalse([o for o in opened if what in o], what)

    def test_the_annual_job_has_no_step_for_it(self):
        """The digest reads the weekly series and nothing of chokepoints.json, so the annual rebuild of chokepoints.json cannot make it stale."""
        self.assertNotIn("build-market-now", read(".github", "workflows", "update-annual.yml"))
        self.assertNotIn("build_market_now", read("pipeline", "annual", "update_annual.py"))

    def test_the_documentation_says_what_the_step_does_when_it_fails_and_that_it_uses_no_network(self):
        doc = read("docs", "UPDATING.md")
        self.assertIn("build_market_now.py", doc)
        self.assertIn("build-market-now", doc)
        row = next(ln for ln in doc.splitlines() if ln.startswith("| `update-portwatch.yml`"))
        self.assertIn("freight market digest", row)


if __name__ == "__main__":
    unittest.main()
