"""pipeline/companies/sec_get.py, the only program that talks to sec.gov: its refusals, its pause, what it saves and where the
contact address goes. No test makes a request: urllib.request.urlopen is replaced, time.sleep and time.time are patched, the cache is a
temporary folder, and the address used here is made up (it is set inside the tests only, and the tests need no variable and no network).

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_sec_get.py"
"""
import contextlib
import importlib.util
import io
import os
import re
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "companies"))
import sec_get  # noqa: E402

CONTACT = "someone@example.org"
PAGE = "https://www.sec.gov/Archives/edgar/data/1/000000000026000001/x-20251231.htm"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK0000000001.json"
ROBOTS = "https://www.sec.gov/robots.txt"


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


class Response:
    def __init__(self, body=b"<html>ok</html>", status=200):
        self.body, self.status = body, status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


class SecGet(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = os.path.join(self.tmp.name, "cache")
        patches = [
            mock.patch.object(sec_get, "CACHE", self.cache),
            mock.patch.object(sec_get, "STAMP", os.path.join(self.cache, ".last_request")),
            mock.patch.object(sec_get, "STOP", os.path.join(self.cache, "STOPPED")),
            mock.patch.object(sec_get, "INDEX", os.path.join(self.cache, "index.tsv")),
            mock.patch.object(sec_get, "LOCK", os.path.join(self.cache, ".lock")),
            mock.patch.dict(os.environ, {"SEC_CONTACT_EMAIL": CONTACT}),
            mock.patch.object(sec_get.time, "sleep"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.sleep = sec_get.time.sleep
        os.makedirs(self.cache)

    # a robots file already in the cache, so that no request is needed for it
    def robots(self, text="User-agent: *\nDisallow: /cgi-bin/\n"):
        with open(sec_get.cache_path(ROBOTS), "w", encoding="utf-8") as f:
            f.write(text)
        with open(sec_get.INDEX, "a", encoding="utf-8") as f:
            f.write(f"2026-11-26T00:00:00Z\t200\t{len(text)}\t{ROBOTS}\n")

    def run_main(self, urls, urlopen=None):
        out = io.StringIO()
        urlopen = urlopen or mock.Mock(side_effect=AssertionError("no request expected"))
        with mock.patch.object(sec_get.urllib.request, "urlopen", urlopen), contextlib.redirect_stdout(out):
            rc = sec_get.main(urls)
        return rc, out.getvalue(), urlopen

    def index_lines(self):
        try:
            return read(sec_get.INDEX).splitlines()
        except OSError:
            return []

    # ---------------------------------------------------------------- where it keeps things
    def test_the_cache_is_raw_sec_edgar_at_the_repository_root(self):
        spec = importlib.util.spec_from_file_location("sec_get_fresh", os.path.join(ROOT, "pipeline", "companies", "sec_get.py"))
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)  # only constants are defined at import: nothing runs
        self.assertEqual(fresh.CACHE, os.path.join(ROOT, "raw", "sec-edgar"))
        self.assertEqual(fresh.INDEX, os.path.join(ROOT, "raw", "sec-edgar", "index.tsv"))

    def test_the_source_holds_no_address(self):
        source = read(os.path.join(ROOT, "pipeline", "companies", "sec_get.py"))
        self.assertEqual(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", source), [])

    def test_only_the_two_sec_hosts(self):
        self.assertEqual(sec_get.HOSTS, {"www.sec.gov", "data.sec.gov"})
        self.assertEqual(sec_get.PAUSE, 3.0)
        self.assertLessEqual(sec_get.MAX_REQUESTS, 700)

    def test_no_job_and_no_script_calls_the_program(self):
        callers = []
        for base in (os.path.join(ROOT, ".github", "workflows"), os.path.join(ROOT, "pipeline")):
            for folder, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if d not in ("__pycache__", "tests")]
                for name in files:
                    if name in ("sec_get.py", "README.md") or not name.endswith((".py", ".yml", ".yaml", ".sh")):
                        continue
                    if "sec_get" in read(os.path.join(folder, name)):
                        callers.append(os.path.join(folder, name))
        self.assertEqual(callers, [], "a job or a script calls sec_get.py: it is run by hand only")

    # ---------------------------------------------------------------- refusals
    def test_another_host_and_http_are_refused_without_a_request(self):
        for url in ("https://example.org/x", "https://efts.sec.gov/LATEST/search-index?q=oil", "http://www.sec.gov/robots.txt",
                    "https://www.sec.gov.example.org/x", "ftp://www.sec.gov/x"):
            rc, out, urlopen = self.run_main([url])
            self.assertEqual(rc, 1, url)
            self.assertIn("REFUSED (host not allowed)", out, url)
            urlopen.assert_not_called()
        self.assertEqual(self.index_lines(), [])

    def test_without_the_variable_nothing_is_fetched(self):
        for value in (None, "", "   "):
            env = {k: v for k, v in os.environ.items() if k != "SEC_CONTACT_EMAIL"}
            if value is not None:
                env["SEC_CONTACT_EMAIL"] = value
            with mock.patch.dict(os.environ, env, clear=True):
                rc, out, urlopen = self.run_main([PAGE])
            self.assertEqual(rc, 2)
            self.assertIn("SEC_CONTACT_EMAIL is not set", out)
            urlopen.assert_not_called()

    def test_a_value_that_is_not_one_address_is_refused(self):
        for value in ("no-at-sign", "two words@example.org", "a@example.org b@example.org"):
            with mock.patch.dict(os.environ, {"SEC_CONTACT_EMAIL": value}):
                rc, out, urlopen = self.run_main([PAGE])
            self.assertEqual(rc, 2, value)
            self.assertIn("does not look like one address", out)
            self.assertNotIn(value, out)
            urlopen.assert_not_called()

    def test_the_contact_may_not_be_in_a_url(self):
        for url in (f"https://www.sec.gov/Archives/?q={CONTACT}", f"https://www.sec.gov/{CONTACT.upper()}/x"):
            rc, out, urlopen = self.run_main([url])
            self.assertEqual(rc, 1)
            self.assertIn("REFUSED (the contact may not be in a URL)", out)
            self.assertNotIn(CONTACT, out)
            urlopen.assert_not_called()

    def test_a_stop_file_stops_everything(self):
        with open(sec_get.STOP, "w") as f:
            f.write("403 on https://www.sec.gov/x\n")
        rc, out, urlopen = self.run_main([PAGE, SUBMISSIONS])
        self.assertEqual(rc, 3)
        self.assertIn("STOPPED earlier", out)
        urlopen.assert_not_called()

    def test_a_spent_budget_stops_the_fetching(self):
        self.robots()
        with mock.patch.object(sec_get, "MAX_REQUESTS", 1):
            rc, out, urlopen = self.run_main([PAGE])
        self.assertEqual(rc, 4)
        self.assertIn("BUDGET SPENT", out)
        urlopen.assert_not_called()
        self.assertFalse(os.path.exists(sec_get.cache_path(PAGE)))

    def test_a_path_that_robots_disallows_is_refused(self):
        self.robots("User-agent: *\nDisallow: /cgi-bin/\nDisallow: /private/\n")
        for url in ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany", "https://www.sec.gov/private/file.htm"):
            rc, out, urlopen = self.run_main([url])
            self.assertEqual(rc, 1, url)
            self.assertIn("REFUSED (robots.txt disallows the path)", out)
            urlopen.assert_not_called()

    def test_robots_is_fetched_once_per_host_and_kept(self):
        robots = Response(b"User-agent: *\nDisallow: /cgi-bin/\n")
        page = Response(b"<html>a</html>")
        urlopen = mock.Mock(side_effect=[robots, page])
        rc, out, _ = self.run_main([PAGE], urlopen)
        self.assertEqual(rc, 0)
        self.assertEqual([c.args[0].full_url for c in urlopen.call_args_list], [ROBOTS, PAGE])
        # a second run asks neither for the robots file nor for the page again
        rc, out, again = self.run_main([PAGE])
        self.assertEqual(rc, 0)
        self.assertIn("200 (cache)", out)
        again.assert_not_called()

    # ---------------------------------------------------------------- the pause
    def test_two_requests_are_at_least_three_seconds_apart(self):
        self.robots()
        with open(sec_get.STAMP, "w") as f:
            f.write("100.0")
        urlopen = mock.Mock(side_effect=[Response(), Response(), Response()])
        # the clock stands still at 101.0: the first request waits for the 3 seconds after the stamp at 100.0,
        # the second for 3 seconds after the first (and the robots file of the other host is a request too)
        with mock.patch.object(sec_get.time, "time", return_value=101.0):
            self.run_main([PAGE, SUBMISSIONS], urlopen)
        waits = [c.args[0] for c in self.sleep.call_args_list]
        self.assertEqual(waits, [2.0, 3.0, 3.0])
        self.assertEqual(urlopen.call_count, 3)

    def test_no_pause_when_the_last_request_is_old_enough(self):
        self.robots()
        with open(sec_get.STAMP, "w") as f:
            f.write("100.0")
        with mock.patch.object(sec_get.time, "time", return_value=500.0):
            self.run_main([PAGE], mock.Mock(side_effect=[Response()]))
        self.sleep.assert_not_called()

    # ---------------------------------------------------------------- what is saved
    def test_a_body_is_saved_only_on_a_200(self):
        self.robots()
        ok = Response(b"<html>filing</html>")
        rc, out, _ = self.run_main([PAGE], mock.Mock(side_effect=[ok]))
        self.assertEqual(rc, 0)
        self.assertEqual(read(sec_get.cache_path(PAGE), "rb"), b"<html>filing</html>")
        self.assertTrue(self.index_lines()[-1].endswith(f"\t200\t19\t{PAGE}"))
        missing = urllib.error.HTTPError(SUBMISSIONS, 404, "Not Found", {}, None)
        rc, out, _ = self.run_main([SUBMISSIONS], mock.Mock(side_effect=missing))
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(sec_get.cache_path(SUBMISSIONS)))
        self.assertIn("\t404\t", self.index_lines()[-1])
        self.assertTrue(out.startswith("404\t0\t-\t"))
        down = urllib.error.URLError("no network")
        self.run_main([PAGE.replace("x-2025", "y-2025")], mock.Mock(side_effect=down))
        self.assertIn("\t-1\t", self.index_lines()[-1])
        self.assertFalse(os.path.exists(sec_get.cache_path(PAGE.replace("x-2025", "y-2025"))))

    def test_a_403_or_a_429_writes_the_stop_file_and_no_other_request_follows(self):
        for code in (403, 429):
            if os.path.exists(sec_get.STOP):
                os.remove(sec_get.STOP)
            self.robots()
            refused = urllib.error.HTTPError(PAGE, code, "refused", {}, None)
            urlopen = mock.Mock(side_effect=[refused])
            rc, out, _ = self.run_main([PAGE, SUBMISSIONS], urlopen)
            self.assertEqual(rc, 3)
            self.assertIn("STOPPED: the SEC refused", out)
            self.assertEqual(urlopen.call_count, 1)
            self.assertTrue(os.path.exists(sec_get.STOP))
            self.assertIn(str(code), read(sec_get.STOP))
            self.assertFalse(os.path.exists(sec_get.cache_path(PAGE)))
            rc, out, again = self.run_main([PAGE])
            self.assertEqual(rc, 3)
            again.assert_not_called()

    # ---------------------------------------------------------------- the contact
    def test_the_contact_goes_in_the_user_agent_header_and_nowhere_else(self):
        self.robots()
        seen = []

        def urlopen(req, timeout=None):
            seen.append(req)
            return Response(b"<html>filing</html>")

        rc, out, _ = self.run_main([PAGE, SUBMISSIONS], mock.Mock(side_effect=urlopen))
        self.assertEqual(rc, 0)
        self.assertEqual(len(seen), 3)  # the page, the robots file of data.sec.gov, the submissions file
        for req in seen:
            self.assertEqual(req.get_header("User-agent"), f"research-script/1.0 {CONTACT}")
            self.assertNotIn(CONTACT, req.full_url)
            self.assertIsNone(req.data)
            others = {k: v for k, v in req.header_items() if k.lower() != "user-agent"}
            self.assertNotIn(CONTACT, " ".join(others.values()))
        self.assertNotIn(CONTACT, out)
        for folder, _, files in os.walk(self.tmp.name):
            for name in files:
                path = os.path.join(folder, name)
                self.assertNotIn(CONTACT.encode(), read(path, "rb"), path)
                self.assertNotIn(CONTACT, name)
        self.assertGreaterEqual(len(os.listdir(self.cache)), 4)

    def test_every_run_ends_with_nothing_printed_but_the_answers(self):
        self.robots()
        rc, out, _ = self.run_main([PAGE, "https://example.org/x"], mock.Mock(side_effect=[Response()]))
        self.assertEqual(rc, 1)
        self.assertEqual(len(out.splitlines()), 2)
        self.assertNotIn(CONTACT, out)


if __name__ == "__main__":
    unittest.main()
