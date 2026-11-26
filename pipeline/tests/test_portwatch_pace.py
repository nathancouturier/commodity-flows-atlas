"""The pace of the PortWatch download.

The owner's rule of 25 November 2026 for PortWatch: read it as a person would, in small pieces, one request at a time and
slowly. The IMF's terms page says that it "prohibits bulk download of information by automated technology without explicit
permission" (NOTICE.md quotes it). The pause in seconds is the script's reading of "slowly". These tests fail when the
script is made faster, when a pause is dropped or when two requests could run at once, and they tie the figures of the
texts to the constants of the code.
"""
import json
import math
import os
import re
import sys
import threading
import unittest
import warnings
from datetime import date, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "freight"))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "infrastructure"))

import fetch_portwatch as FP  # noqa: E402
from common import fetch as F  # noqa: E402


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def flat(text):
    return " ".join(text.split())


class Pace(unittest.TestCase):
    def test_the_pause_between_two_pages_is_at_least_eight_seconds(self):
        lo, hi = FP.PAUSE_S
        self.assertGreaterEqual(lo, 8.0)
        self.assertGreater(hi, lo)

    def test_pages_are_asked_one_after_the_other_with_the_pause_between_them(self):
        """Three pages: request, pause, request, pause, request, in that order, on one thread, never two requests at once,
        and the download helper is given the least interval so that a repeated request waits as long as any other."""
        row = {k: 0 for k in FP.NEEDED}
        pages = [{"features": [{"attributes": dict(row)}] * 2, "exceededTransferLimit": True},
                 {"features": [{"attributes": dict(row)}] * 2, "exceededTransferLimit": True},
                 {"features": [{"attributes": dict(row)}], "exceededTransferLimit": False}]
        events, flying, main = [], [0], threading.get_ident()

        def fake_get_json(url, params=None, **kw):
            self.assertEqual(threading.get_ident(), main, "a request left the main thread")
            self.assertEqual(flying[0], 0, "two requests at once")
            flying[0] += 1
            events.append(("get", params["resultOffset"], kw.get("min_interval")))
            flying[0] -= 1
            return pages[sum(1 for e in events if e[0] == "get") - 1]

        def fake_sleep(s):
            self.assertEqual(threading.get_ident(), main, "a pause left the main thread: the next request would not wait for it")
            events.append(("sleep", s))

        saved = (FP.fetch.get_json, FP.time.sleep)
        try:
            FP.fetch.get_json, FP.time.sleep = fake_get_json, fake_sleep
            rows = FP.fetch_rows("1=1")
        finally:
            FP.fetch.get_json, FP.time.sleep = saved
        self.assertEqual(len(rows), 5)
        self.assertEqual([e[0] for e in events], ["get", "sleep", "get", "sleep", "get"])   # a pause between two pages, none after the last
        self.assertEqual([e[1] for e in events if e[0] == "get"], [0, 2, 4])
        for e in events:
            if e[0] == "get":
                self.assertEqual(e[2], FP.PAUSE_S[0])
            else:
                self.assertGreaterEqual(e[1], FP.PAUSE_S[0])
                self.assertLessEqual(e[1], FP.PAUSE_S[1])

    def test_a_request_repeated_after_an_error_starts_no_sooner_than_any_other(self):
        """The download helper itself, on a clock of the test: a page answered 503 twice and then 200. With the least interval that
        fetch_rows passes, each attempt starts at least PAUSE_S[0] seconds after the one before (the helper's own waits are shorter)."""
        clock, starts = [1000.0], []

        class Resp:
            def __init__(self, code):
                self.status_code = code
                self.content = b'{"features": []}'

            def json(self):
                return {"features": []}

            def close(self):
                pass

        class Session:
            def __init__(self):
                self.codes = [503, 503, 200]

            def request(self, *a, **kw):
                starts.append(clock[0])
                clock[0] += 0.5   # the time of an answer
                return Resp(self.codes.pop(0))

        session = Session()
        saved = (F._sess, F.time.sleep, F.time.monotonic, dict(F._last_hit), F.random.uniform)
        try:
            F._sess = lambda: session
            F.time.sleep = lambda s: clock.__setitem__(0, clock[0] + max(0.0, s))
            F.time.monotonic = lambda: clock[0]
            F.random.uniform = lambda a, b: a   # the shortest wait the helper can draw
            F._last_hit.clear()
            doc = F.get_json(FP.URL, params={"f": "json"}, min_interval=FP.PAUSE_S[0])
        finally:
            F._sess, F.time.sleep, F.time.monotonic, F.random.uniform = saved[0], saved[1], saved[2], saved[4]
            F._last_hit.clear()
            F._last_hit.update(saved[3])
        self.assertEqual(doc, {"features": []})
        self.assertEqual(len(starts), 3)
        for a, b in zip(starts, starts[1:]):
            self.assertGreaterEqual(b - a, FP.PAUSE_S[0])
        # and without the least interval the helper would have come back sooner: the parameter is what makes the difference
        self.assertLess(F.BACKOFF_BASE, FP.PAUSE_S[0])

    def test_a_weekly_run_asks_for_the_last_days_and_the_days_portwatch_may_revise(self):
        last, today = date(2026, 11, 18), date(2026, 11, 25)
        mode, where = FP.plan(True, (today - timedelta(days=5)).isoformat(), last.isoformat(), today)
        self.assertEqual(mode, "incremental")
        self.assertIn(f"date > '{(last - timedelta(days=FP.OVERLAP_DAYS)).isoformat()}'", where)
        # that is one page: the rows of a day (one per passage; the atlas has at least as many passages as the table) times the days asked for
        with open(os.path.join(ROOT, "data", "freight", "chokepoints.json"), encoding="utf-8") as fh:
            passages = len(json.load(fh))
        self.assertLess((7 + FP.OVERLAP_DAYS) * passages, FP.PAGE)
        # the whole table is asked for again only after FULL_EVERY_DAYS days, or with no working table
        self.assertEqual(FP.plan(True, (today - timedelta(days=FP.FULL_EVERY_DAYS)).isoformat(), last.isoformat(), today)[0], "full")
        self.assertEqual(FP.plan(False, None, None, today)[0], "full")

    def _records(self):
        """The rows of the table at the last update, as the status file records them (None when it records none)."""
        with open(os.path.join(ROOT, "data", "_status", "updates.json"), encoding="utf-8") as fh:
            st = json.load(fh)
        src = st.get("sources", st).get(FP.SOURCE) if isinstance(st, dict) else None
        n = (src or {}).get("records")
        return n if isinstance(n, int) else None

    # "41 pages for the 80,724 rows of 26 November 2026": the figure of a text is true for the table it names, which no weekly run moves
    NAMED = re.compile(r"(\d+) (?:pages|requests) for the ([\d,]+) rows of (\d{1,2} [A-Z][a-z]+ \d{4})")

    def _named(self, text):
        found = {m.groups() for m in self.NAMED.finditer(text)}
        self.assertEqual(len(found), 1, f"the text names one table, with its date: {found}")
        pages, rows, day = found.pop()
        return int(pages), int(rows.replace(",", "")), day

    def test_the_whole_table_fits_the_step_of_the_job_at_this_pace(self):
        """The table the texts name, a tenth larger, at the longest pause and five seconds an answer, stays within three
        quarters of the step's limit. The status file is not read for this: its record grows every week and must not stop
        a week's republication; a table that has outgrown the step is a warning, with the room that is left."""
        wf = read(".github", "workflows", "update-portwatch.yml")
        step = re.search(r"- name: Fetch PortWatch and rebuild chokepoint series\n(?:.*\n)*?\s+timeout-minutes: (\d+)", wf)
        self.assertIsNotNone(step)
        limit_s = int(step.group(1)) * 60
        _, rows, _ = self._named(flat(read("NOTICE.md")))
        self.assertLess(math.ceil(rows * 1.1 / FP.PAGE) * (FP.PAUSE_S[1] + 5), limit_s * 0.75)
        room = int(limit_s * 0.75 / (FP.PAUSE_S[1] + 5)) * FP.PAGE / 1.1
        now = self._records()
        if now is not None and now > room:
            warnings.warn(f"the PortWatch table ({now} rows) is larger than the step's timeout allows ({int(room)} rows): raise the timeout of the step")

    def test_the_texts_give_the_rule_and_the_figure_of_the_table_they_name(self):
        lo, hi = int(FP.PAUSE_S[0]), int(FP.PAUSE_S[1])
        self.assertEqual(FP.PAGE, 2000)
        notice = flat(read("NOTICE.md"))
        self.assertIn("prohibits bulk download of information by automated technology without explicit permission", notice)
        self.assertIn("Copying or downloading IMF Content in any systematic way", notice)
        self.assertIn("one request at a time and slowly", notice)
        self.assertIn(f"it waits {lo} to {hi} seconds between two pages", notice)
        self.assertIn(f"starts less than {lo} seconds after the one before", notice)
        self.assertIn(f"the {FP.OVERLAP_DAYS} days before it", notice)
        self.assertEqual(FP.FULL_EVERY_DAYS, 28)
        self.assertIn("once every four weeks", notice)
        self.assertIn("The figures in seconds are the script's, not the owner's", notice)
        wf = flat(read(".github", "workflows", "update-portwatch.yml").replace("#", " "))
        self.assertIn(f"at least {lo} seconds apart", wf)
        doc = flat(FP.__doc__)
        self.assertIn(f"PAUSE_S seconds ({lo} to {hi}) between two pages", doc)
        self.assertIn('this script\'s reading of "slowly", not a figure of the owner', doc)
        # the rule, and the figure for the table each text names: one page for every PAGE rows, rounded up
        for where, text in (("NOTICE.md", notice), ("the workflow", wf), ("fetch_portwatch.py", doc)):
            pages, rows, day = self._named(text)
            self.assertEqual(pages, math.ceil(rows / FP.PAGE), where)
            self.assertIn("2,000 rows", text, where)
        figures = {self._named(t) for t in (notice, wf, doc)}
        self.assertEqual(len(figures), 1, f"the three texts name the same table: {figures}")
        self.assertIn("one more for every 2,000 rows", notice)
        self.assertIn("one more for every 2,000 rows", wf)
        self.assertIn("one page for every 2,000 rows", doc)
        self.assertIn(f"the verbatim daily table ({figures.pop()[1]:,} rows on", notice)

    def test_the_other_script_that_reads_portwatch_keeps_the_same_least_interval(self):
        import fetch_portwatch_ports as PP
        self.assertGreaterEqual(PP.MIN_INTERVAL_S, FP.PAUSE_S[0])
        self.assertIn("min_interval=MIN_INTERVAL_S", read("pipeline", "infrastructure", "fetch_portwatch_ports.py"))


if __name__ == "__main__":
    unittest.main()
