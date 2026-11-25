"""The pace of the PortWatch download: the owner's rule of 25 November 2026 (in small pieces, one request at a time, slowly).

The IMF's terms page says that it "prohibits bulk download of information by automated technology without explicit
permission" (NOTICE.md quotes it). The update script may not be made faster or parallel by mistake: these tests fail first.
"""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "freight"))

import fetch_portwatch as FP  # noqa: E402


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


class Pace(unittest.TestCase):
    def test_the_pause_between_two_pages_is_at_least_eight_seconds(self):
        lo, hi = FP.PAUSE_S
        self.assertGreaterEqual(lo, 8.0)
        self.assertGreater(hi, lo)

    def test_pages_are_asked_one_after_the_other_with_the_pause_between_them(self):
        """Three pages: three requests in order, a pause of PAUSE_S after each page but the last, and nothing in parallel."""
        row = {k: 0 for k in FP.NEEDED}
        pages = [{"features": [{"attributes": dict(row)}] * 2, "exceededTransferLimit": True},
                 {"features": [{"attributes": dict(row)}] * 2, "exceededTransferLimit": True},
                 {"features": [{"attributes": dict(row)}], "exceededTransferLimit": False}]
        calls, sleeps = [], []

        def fake_get_json(url, params=None, **kw):
            calls.append(params["resultOffset"])
            return pages[len(calls) - 1]

        saved = (FP.fetch.get_json, FP.time.sleep)
        try:
            FP.fetch.get_json, FP.time.sleep = fake_get_json, sleeps.append
            rows = FP.fetch_rows("1=1")
        finally:
            FP.fetch.get_json, FP.time.sleep = saved
        self.assertEqual(len(rows), 5)
        self.assertEqual(calls, [0, 2, 4])            # one request at a time, each after the one before
        self.assertEqual(len(sleeps), 2)              # a pause between two pages, none after the last
        for s in sleeps:
            self.assertGreaterEqual(s, FP.PAUSE_S[0])
            self.assertLessEqual(s, FP.PAUSE_S[1])

    def test_a_weekly_run_asks_for_the_days_since_the_last_one_stored_only(self):
        from datetime import date
        mode, where = FP.plan(True, "2026-11-20", "2026-11-18", date(2026, 11, 25))
        self.assertEqual(mode, "incremental")
        self.assertIn("date > '2026-11-04'", where)   # the last day stored less the days PortWatch may revise

    def test_the_whole_table_fits_the_step_of_the_job_at_this_pace(self):
        """About 80,000 rows by pages of PAGE at the slowest pause must stay well inside the 25 minutes of the workflow's step."""
        import re
        wf = read(".github", "workflows", "update-portwatch.yml")
        step = re.search(r"- name: Fetch PortWatch and rebuild chokepoint series\n(?:.*\n)*?\s+timeout-minutes: (\d+)", wf)
        self.assertIsNotNone(step)
        limit_s = int(step.group(1)) * 60
        pages = -(-90000 // FP.PAGE)                   # a table a little larger than today's
        worst = pages * (FP.PAUSE_S[1] + 5)            # the longest pause and five seconds for each answer
        self.assertLess(worst, limit_s * 0.75)

    def test_the_notice_quotes_the_terms_and_gives_the_rule(self):
        notice = " ".join(read("NOTICE.md").split())
        self.assertIn("prohibits bulk download of information by automated technology without explicit permission", notice)
        self.assertIn("one request at a time and slowly", notice)
        self.assertIn(f"waits {int(FP.PAUSE_S[0])} to {int(FP.PAUSE_S[1])} seconds between two requests", notice)


if __name__ == "__main__":
    unittest.main()
