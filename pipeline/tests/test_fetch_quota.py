"""The download helper (pipeline/common/fetch.py) and a service that names a delay.

A service that answers a quota ("API calls quota exceeded ... Retry after 60 sec" in an ArcGIS error body, or HTTP 429 with a
``Retry-After`` header) must not be asked again sooner than it said: the helper waits that delay plus QUOTA_MARGIN before the
next attempt, and a second such answer ends the attempts. Every update script downloads through the helper, so these tests
run it on a session and a clock of their own (nothing is asked of any site, nothing sleeps): the PortWatch chokepoint script,
which has no code of its own for it, is run through it too.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_fetch_quota.py"
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("", "freight"):
    p = os.path.join(ROOT, "pipeline", sub) if sub else os.path.join(ROOT, "pipeline")
    if p not in sys.path:
        sys.path.insert(0, p)

import fetch_portwatch as FP  # noqa: E402
from common import fetch as F  # noqa: E402

URL = "https://service.example.invalid/query"
BODY = {"error": {"code": 429, "message": "API calls quota exceeded! maximum admitted 20 per 60 sec. Retry after 60 sec"}}
GOOD = {"features": [], "exceededTransferLimit": False}


class Resp:
    def __init__(self, code=200, body=None, headers=None, content=b"{}"):
        self.status_code = code
        self.body = GOOD if body is None else body
        self.headers = headers or {}
        self.content = content

    def json(self):
        return self.body

    def close(self):
        pass

    def iter_content(self, chunk):
        yield self.content


class Clock(unittest.TestCase):
    """The helper on a virtual clock: ``answer(n)`` is the n-th response (from 1); ``self.starts`` the time each request began."""

    def run_on_clock(self, answer, call):
        clock, self.starts = [1000.0], []

        class Session:
            def request(_, *a, **kw):
                self.starts.append(clock[0])
                clock[0] += 0.5
                return answer(len(self.starts))
        saved = (F._sess, dict(F._last_hit), F.random.uniform)
        try:
            F._sess = lambda: Session()
            F._last_hit.clear()
            F.random.uniform = lambda a, b: a      # the shortest backoff the helper can draw
            with mock.patch.object(F.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + max(0.0, s))), \
                    mock.patch.object(F.time, "monotonic", lambda: clock[0]):
                try:
                    return call()
                except F.FetchError as e:
                    return e
        finally:
            F._sess = saved[0]
            F.random.uniform = saved[2]
            F._last_hit.clear()
            F._last_hit.update(saved[1])

    def gaps(self):
        return [b - a for a, b in zip(self.starts, self.starts[1:])]


class QuotaBody(Clock):
    def test_the_next_attempt_waits_the_delay_the_body_names_plus_the_margin(self):
        out = self.run_on_clock(lambda n: Resp(200, BODY if n == 1 else GOOD), lambda: F.get_json(URL, min_interval=8.0))
        self.assertEqual(out, GOOD)
        self.assertEqual(len(self.starts), 2)
        self.assertGreaterEqual(self.gaps()[0], 60 + F.QUOTA_MARGIN)

    def test_a_second_quota_answer_ends_the_attempts_with_the_delay_in_the_error(self):
        out = self.run_on_clock(lambda n: Resp(200, BODY), lambda: F.get_json(URL, min_interval=8.0))
        self.assertIsInstance(out, F.FetchError)
        self.assertEqual(len(self.starts), 2, "a service that asked for 60 seconds was asked again and again")
        self.assertGreaterEqual(self.gaps()[0], 60 + F.QUOTA_MARGIN)
        self.assertEqual(out.retry_after, 60)
        self.assertIn("quota", str(out))

    def test_with_one_attempt_the_helper_does_not_wait_and_says_what_was_asked(self):
        out = self.run_on_clock(lambda n: Resp(200, BODY), lambda: F.get_json(URL, attempts=1))
        self.assertEqual((len(self.starts), out.retry_after), (1, 60))
        self.assertIn("quota", str(out))

    def test_an_error_body_that_names_no_delay_keeps_the_backoff_and_all_its_attempts(self):
        out = self.run_on_clock(lambda n: Resp(200, {"error": {"message": "Cannot perform query"}}), lambda: F.get_json(URL))
        self.assertIsInstance(out, F.FetchError)
        self.assertIsNone(out.retry_after)
        self.assertEqual(len(self.starts), F.ATTEMPTS)
        for g in self.gaps():
            self.assertLess(g, 60)

    def test_a_delay_longer_than_the_most_a_job_waits_is_not_waited_for(self):
        body = {"error": {"message": f"too many calls. Retry after {int(F.QUOTA_MAX_WAIT)} sec"}}
        out = self.run_on_clock(lambda n: Resp(200, body), lambda: F.get_json(URL))
        self.assertEqual(len(self.starts), 1)
        self.assertEqual(out.retry_after, F.QUOTA_MAX_WAIT)

    def test_the_chokepoint_script_is_asked_nothing_sooner_than_the_service_said_with_no_code_of_its_own(self):
        out = self.run_on_clock(lambda n: Resp(200, BODY if n == 1 else GOOD), lambda: FP.fetch_rows("1=1"))
        self.assertEqual(out, [])
        self.assertEqual(len(self.starts), 2)
        self.assertGreaterEqual(self.gaps()[0], 60 + F.QUOTA_MARGIN)
        out = self.run_on_clock(lambda n: Resp(200, BODY), lambda: FP.fetch_rows("1=1"))
        self.assertIsInstance(out, F.FetchError)
        self.assertEqual(len(self.starts), 2)


class Http429(Clock):
    def test_a_retry_after_header_is_waited_out_plus_the_margin(self):
        out = self.run_on_clock(lambda n: Resp(429, headers={"Retry-After": "60"}) if n == 1 else Resp(200, GOOD),
                                lambda: F.get_json(URL, min_interval=8.0))
        self.assertEqual(out, GOOD)
        self.assertEqual(len(self.starts), 2)
        self.assertGreaterEqual(self.gaps()[0], 60 + F.QUOTA_MARGIN)

    def test_a_second_429_with_a_delay_ends_the_attempts(self):
        out = self.run_on_clock(lambda n: Resp(429, headers={"Retry-After": "60"}), lambda: F.request(URL))
        self.assertIsInstance(out, F.FetchError)
        self.assertEqual(len(self.starts), 2)
        self.assertGreaterEqual(self.gaps()[0], 65)
        self.assertEqual(out.retry_after, 60)
        self.assertIn("HTTP 429", str(out))

    def test_a_429_with_no_header_keeps_the_backoff_and_all_its_attempts(self):
        out = self.run_on_clock(lambda n: Resp(429), lambda: F.request(URL))
        self.assertEqual(len(self.starts), F.ATTEMPTS)
        self.assertIsNone(out.retry_after)
        self.assertIn("HTTP 429", str(out))
        for g in self.gaps():
            self.assertLess(g, 60)

    def test_a_503_keeps_the_backoff_whatever_header_it_carries(self):
        out = self.run_on_clock(lambda n: Resp(503, headers={"Retry-After": "120"}), lambda: F.request(URL))
        self.assertEqual(len(self.starts), F.ATTEMPTS)
        for g in self.gaps():
            self.assertLess(g, 60)

    def test_a_download_waits_as_well_and_stops_at_the_second_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "x.json")
            out = self.run_on_clock(lambda n: Resp(429, headers={"Retry-After": "30"}), lambda: F.download(URL, dest))
            self.assertIsInstance(out, F.FetchError)
            self.assertEqual(len(self.starts), 2)
            self.assertGreaterEqual(self.gaps()[0], 30 + F.QUOTA_MARGIN)
            out = self.run_on_clock(lambda n: Resp(429, headers={"Retry-After": "30"}) if n == 1 else Resp(200, content=b"{}"),
                                    lambda: F.download(URL, dest))
            self.assertEqual(out, 2)
            self.assertEqual(len(self.starts), 2)
            self.assertGreaterEqual(self.gaps()[0], 30 + F.QUOTA_MARGIN)
            self.assertFalse(os.path.exists(dest + ".part"))


class Headers(unittest.TestCase):
    def test_the_header_is_read_as_seconds_or_as_a_date_and_anything_else_names_no_delay(self):
        self.assertEqual(F.retry_after_header("60"), 60)
        self.assertEqual(F.retry_after_header(" 2.5 "), 2.5)
        self.assertEqual(F.retry_after_header("Thu, 01 Jan 1970 00:02:00 GMT", now=60), 60)
        self.assertEqual(F.retry_after_header("Thu, 01 Jan 1970 00:00:10 GMT", now=60), 0)
        for bad in (None, "", "soon", "-5"):
            self.assertIsNone(F.retry_after_header(bad), bad)

    def test_the_body_is_read_for_its_delay(self):
        self.assertEqual(F.retry_after_body(BODY["error"]["message"]), 60)
        self.assertEqual(F.retry_after_body("retry after 7 SEC"), 7)
        self.assertIsNone(F.retry_after_body("Cannot perform query"))
        self.assertIsNone(F.retry_after_body(None))


if __name__ == "__main__":
    unittest.main()
