"""The sec.gov reader of the companies layer (pipeline/companies/sec_edgar.py).

The owner's decision of 24 November 2026: a contact address is sent to the SEC, and to nobody else, when its filings are
read; it is the environment variable SEC_CONTACT_EMAIL, written in no file of the repository. These tests fail when a
request could leave without the address or for another host, when a redirect could carry the header away from sec.gov,
when the script could print the address, when two requests could follow each other faster than the pause, when a refusal
of sec.gov is asked again, or when the cache of the filings could be committed. No test sends a request.
"""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "companies"))

import sec_edgar as S  # noqa: E402
from common import fetch as F  # noqa: E402

ADDR = "someone.test@example.org"   # a placeholder, not the owner's address


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class FakeResponse:
    def __init__(self, status=200, body=b"{}", location=None):
        self.status_code = status
        self.content = body
        self.headers = {"Location": location} if location else {}

    def close(self):
        pass


class FakeSession:
    """Records each request (url, headers, allow_redirects) and answers from a list."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def get(self, url, headers=None, timeout=None, allow_redirects=True):
        self.calls.append((url, dict(headers or {}), allow_redirects))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def monotonic(self):
        return self.t

    def time(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


@contextlib.contextmanager
def env(value):
    saved = os.environ.get(S.ENV)
    if value is None:
        os.environ.pop(S.ENV, None)
    else:
        os.environ[S.ENV] = value
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop(S.ENV, None)
        else:
            os.environ[S.ENV] = saved


@contextlib.contextmanager
def fake(answers):
    """The script with a fake session and a fake clock; yields (session, clock)."""
    sess, clock = FakeSession(answers), Clock()
    saved = (S._session, S._last[0], S.time.monotonic, S.time.sleep, S.random.uniform)
    S._session, S._last[0] = sess, 0.0
    S.time.monotonic, S.time.sleep, S.random.uniform = clock.monotonic, clock.sleep, (lambda a, b: 0.0)
    try:
        yield sess, clock
    finally:
        S._session, S._last[0], S.time.monotonic, S.time.sleep, S.random.uniform = saved


class TheAddress(unittest.TestCase):
    def test_no_request_without_the_variable(self):
        with env(None), fake([FakeResponse()]) as (sess, _):
            with self.assertRaises(S.SecError) as cm:
                S.request("https://www.sec.gov/files/company_tickers.json")
            self.assertEqual(sess.calls, [])
            self.assertIn(S.ENV, str(cm.exception))

    def test_no_request_with_a_value_that_is_not_one_address(self):
        for bad in ("", "   ", "not-an-address", "a@b", "one@example.org two@example.org", "x@example.org\r\nX-Other: 1"):
            with env(bad), fake([FakeResponse()]) as (sess, _):
                with self.assertRaises(S.SecError) as cm:
                    S.request("https://www.sec.gov/files/company_tickers.json")
                self.assertEqual(sess.calls, [], bad)
                if bad.strip():
                    self.assertNotIn(bad.strip(), str(cm.exception))

    def test_the_header_is_the_shared_user_agent_and_the_address(self):
        with env(ADDR), fake([FakeResponse()]) as (sess, _):
            S.request("https://data.sec.gov/submissions/CIK0000093410.json")
        url, headers, follow = sess.calls[0]
        self.assertEqual(headers["User-Agent"], f"{F.USER_AGENT} {ADDR}")
        self.assertFalse(follow, "requests must not follow redirects itself: it would send the header to any host")

    def test_the_shared_user_agent_of_the_other_scripts_carries_no_address(self):
        self.assertNotIn("@", F.USER_AGENT)
        self.assertNotIn(S.ENV, read(F.__file__))

    def test_the_variable_is_read_by_this_script_only(self):
        """No other script of the pipeline reads the variable, so the address cannot reach another host through one."""
        readers = []
        for base, dirs, files in os.walk(os.path.join(ROOT, "pipeline")):
            dirs[:] = [d for d in dirs if d not in ("cache", "__pycache__", "tests")]
            for name in files:
                if name.endswith(".py"):
                    path = os.path.join(base, name)
                    if S.ENV in read(path):
                        readers.append(os.path.relpath(path, ROOT))
        self.assertEqual(readers, [os.path.join("pipeline", "companies", "sec_edgar.py")])


class OnlySecGov(unittest.TestCase):
    def test_other_hosts_are_refused_before_any_request(self):
        for url in ("https://example.org/x", "https://www.sec.gov.example.org/x", "https://www.sec.gov@example.org/x",
                    "http://www.sec.gov/x", "https://sec.gov.evil/x", "https://www.sec.gov:8443/x", "ftp://www.sec.gov/x"):
            with env(ADDR), fake([FakeResponse()]) as (sess, _):
                with self.assertRaises(S.SecError, msg=url):
                    S.request(url)
                self.assertEqual(sess.calls, [], url)

    def test_the_three_hosts_of_the_sec_are_allowed(self):
        for url in ("https://www.sec.gov/Archives/edgar/data/1/000000000000000001/x.htm",
                    "https://data.sec.gov/submissions/CIK0000000001.json",
                    "https://efts.sec.gov/LATEST/search-index?q=%22x%22"):
            self.assertTrue(S.host_ok(url), url)

    def test_a_redirect_to_another_host_is_not_followed(self):
        with env(ADDR), fake([FakeResponse(302, location="https://example.org/elsewhere"), FakeResponse()]) as (sess, _):
            with self.assertRaises(S.SecError) as cm:
                S.request("https://www.sec.gov/cgi-bin/x")
        self.assertEqual(len(sess.calls), 1)
        self.assertNotIn(ADDR, str(cm.exception))

    def test_a_redirect_inside_sec_gov_is_followed_with_the_same_header(self):
        with env(ADDR), fake([FakeResponse(301, location="/Archives/new.htm"), FakeResponse(200, b"ok")]) as (sess, _):
            r = S.request("https://www.sec.gov/Archives/old.htm")
        self.assertEqual(r.content, b"ok")
        self.assertEqual([c[0] for c in sess.calls], ["https://www.sec.gov/Archives/old.htm", "https://www.sec.gov/Archives/new.htm"])


class Pace(unittest.TestCase):
    def test_two_requests_are_at_least_the_pause_apart(self):
        self.assertGreaterEqual(S.MIN_INTERVAL, 0.1)   # sec.gov's published limit: 10 requests a second
        with env(ADDR), fake([FakeResponse(), FakeResponse(), FakeResponse()]) as (sess, clock):
            starts = []
            orig = sess.get

            def timed(*a, **k):
                starts.append(clock.t)
                return orig(*a, **k)

            sess.get = timed
            for _ in range(3):
                S.request("https://data.sec.gov/submissions/CIK0000093410.json")
        self.assertEqual(len(starts), 3)
        for a, b in zip(starts, starts[1:]):
            self.assertGreaterEqual(b - a, S.MIN_INTERVAL)

    def test_a_refusal_stops_the_run_without_asking_again(self):
        for code in S.STOP_STATUS:
            with env(ADDR), fake([FakeResponse(code), FakeResponse()]) as (sess, _):
                with self.assertRaises(S.SecError):
                    S.request("https://www.sec.gov/files/company_tickers.json")
            self.assertEqual(len(sess.calls), 1, code)

    def test_a_server_error_is_asked_again_after_a_pause_a_few_times_only(self):
        with env(ADDR), fake([FakeResponse(503)] * S.ATTEMPTS + [FakeResponse()]) as (sess, clock):
            with self.assertRaises(S.SecError):
                S.request("https://www.sec.gov/files/company_tickers.json")
        self.assertEqual(len(sess.calls), S.ATTEMPTS)
        self.assertTrue(all(s >= S.BACKOFF for s in clock.sleeps if s > S.MIN_INTERVAL))


class NothingPrintedOrKept(unittest.TestCase):
    def test_the_commands_never_print_the_address(self):
        body = b'{"0": {"cik_str": 93410, "ticker": "CVX", "title": "CHEVRON CORP"}}'
        out, err = io.StringIO(), io.StringIO()
        saved_cache = S.CACHE
        try:
            S.CACHE = tempfile.mkdtemp(prefix="sec-edgar-test-")
            with env(ADDR), fake([FakeResponse(200, body), FakeResponse(403)]) as _, \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                S.main(["cik", "chevron"])
                S.main(["filings", "93410"])
        finally:
            shutil.rmtree(S.CACHE, ignore_errors=True)
            S.CACHE = saved_cache
        self.assertIn("CHEVRON", out.getvalue())
        self.assertIn("HTTP 403", err.getvalue())
        self.assertNotIn(ADDR, out.getvalue() + err.getvalue())

    def test_the_cache_of_the_filings_is_not_committed(self):
        probe = os.path.relpath(os.path.join(S.CACHE, "www.sec.gov", "probe.htm"), ROOT)
        r = subprocess.run(["git", "check-ignore", "-q", probe], cwd=ROOT)
        self.assertEqual(r.returncode, 0, f"{probe} is not ignored by git")

    def test_the_address_set_here_is_in_no_tracked_file(self):
        """Where the variable is set (the owner's environment), no file of the repository holds its value. The message
        names the file, never the address."""
        addr = os.environ.get(S.ENV, "").strip()
        if not addr:
            self.skipTest(f"{S.ENV} is not set here")
        files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.split(b"\0")
        needle = addr.lower().encode()
        found = []
        for name in filter(None, files):
            path = os.path.join(ROOT, name.decode())
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    if needle in f.read().lower():
                        found.append(name.decode())
        self.assertEqual(found, [], "the contact address is written in these tracked files")


class Text(unittest.TestCase):
    def test_tables_hidden_facts_and_entities(self):
        page = (b"<html><head><style>p{}</style></head><body><div style='display:none'><ix:header>hidden 999"
                b"</ix:header></div><p>Net production &amp; sales</p><table><tr><td>Copper</td><td>1,234</td>"
                b"<td></td></tr><tr><td>Gold&nbsp;(koz)</td><td>56</td></tr></table><p>end</p></body></html>")
        text = S.html_text(page)
        self.assertNotIn("999", text)
        self.assertIn("Net production & sales", text)
        self.assertIn("Copper | 1,234", text)
        self.assertIn("Gold (koz) | 56", text)

    def test_cache_paths_stay_under_the_cache(self):
        for url in ("https://www.sec.gov/Archives/edgar/data/1/2/x.htm", "https://www.sec.gov/../../etc/passwd",
                    "https://efts.sec.gov/LATEST/search-index?q=%22a/../b%22"):
            self.assertTrue(os.path.abspath(S.cache_path(url)).startswith(os.path.abspath(S.CACHE) + os.sep), url)


if __name__ == "__main__":
    unittest.main()
