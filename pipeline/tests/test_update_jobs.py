"""Tests of the scheduled update machinery: the status module (a step that stopped before it recorded anything, two
jobs that wrote the status files at the same time, the alert thresholds), the staleness check, the checks of the
downloaded inputs (a renamed column, a decorated header, a missing commodity or series), the time limit of a source
in update_annual.py, and the identification of the downloader.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_update_jobs.py"
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("", "common", "annual"):
    p = os.path.join(ROOT, "pipeline", sub) if sub else os.path.join(ROOT, "pipeline")
    if p not in sys.path:
        sys.path.insert(0, p)

import inputs as I  # noqa: E402
import staleness as S  # noqa: E402
import status  # noqa: E402


class StatusSandbox(unittest.TestCase):
    """The status module writes into a temporary folder, never into data/_status."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patch = mock.patch.multiple(status, UPDATES=os.path.join(self.tmp, "updates.json"),
                                         LOG=os.path.join(self.tmp, "log.jsonl"), JOURNAL=os.path.join(self.tmp, "journal"))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def since(self):
        time.sleep(1.05)  # the status times have a resolution of one second: what came before is an earlier run
        return status._now()


class InterruptedStep(StatusSandbox):
    SOURCES = ["usda-psd", "eia-intl", "baci", "?faostat-wna", "?build-freight", "?build-commodities"]

    def test_a_step_that_crashed_before_any_source_records_every_source_it_always_runs(self):
        status.record_success("usda-psd")  # an earlier run
        since = self.since()
        failed = status.interrupted(since, self.SOURCES, "step did not finish")
        self.assertEqual(failed, ["usda-psd", "eia-intl", "baci"])
        e = status.get("usda-psd")
        self.assertEqual(e["consecutive_failures"], 1)
        self.assertEqual(e["last_error"], "step did not finish")
        self.assertIsNotNone(e["last_success"])  # the previous good counts are kept
        self.assertNotIn("build-freight", status.load()["sources"])

    def test_a_step_killed_in_the_middle_records_only_the_source_it_was_working_on(self):
        since = self.since()
        status.begin("usda-psd")
        status.record_success("usda-psd", note="updated")
        status.begin("faostat-wna")
        status.end("faostat-wna")  # checked recently: skipped on purpose
        status.begin("eia-intl")  # killed here (timeout)
        failed = status.interrupted(since, self.SOURCES, "step did not finish")
        self.assertEqual(failed, ["eia-intl"])
        self.assertEqual(status.get("usda-psd")["consecutive_failures"], 0)
        self.assertNotIn("faostat-wna", status.load()["sources"])
        self.assertNotIn("baci", status.load()["sources"])  # not reached: the next run does it

    def test_a_build_step_killed_by_the_timeout_is_recorded_and_alerts_at_once(self):
        since = self.since()
        for s in ("usda-psd", "eia-intl", "baci"):
            status.begin(s)
            status.record_success(s)
        status.begin("build-freight")  # build_lanes.py ran past the step's time limit
        self.assertEqual(status.interrupted(since, self.SOURCES, "step did not finish"), ["build-freight"])
        self.assertIn("build-freight", status.failing())

    def test_marks_of_an_earlier_run_do_not_count(self):
        status.begin("eia-intl")
        since = self.since()
        self.assertEqual(status.interrupted(since, ["usda-psd", "?build-freight"], "x"), ["usda-psd"])

    def test_the_command_line_of_the_workflow(self):
        env = dict(os.environ, STATUS_JOURNAL=os.path.join(self.tmp, "journal"))
        # the CLI writes into the real data/_status: run it on a copy of the module rooted in the sandbox
        root = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(root, "pipeline", "common"))
        shutil.copy(os.path.join(ROOT, "pipeline", "common", "status.py"), os.path.join(root, "pipeline", "common"))
        since = "2026-01-01T00:00:00Z"
        r = subprocess.run([sys.executable, "-I", os.path.join(root, "pipeline", "common", "status.py"), "interrupted", since,
                            "update step did not finish (outcome: failure)", "wb-pink", "eia-spot"],
                           capture_output=True, text=True, env=env, cwd=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = json.load(open(os.path.join(root, "data", "_status", "updates.json")))
        self.assertEqual(sorted(doc["sources"]), ["eia-spot", "wb-pink"])
        self.assertEqual(doc["sources"]["eia-spot"]["consecutive_failures"], 1)


class Thresholds(StatusSandbox):
    def test_a_build_step_alerts_at_its_first_failure_a_monthly_source_at_its_second_a_weekly_one_at_its_third(self):
        status.record_failure("build-commodities", "KeyError")
        status.record_failure("usda-psd", "HTTP 503")
        status.record_failure("eia-spot", "HTTP 503")
        self.assertEqual(sorted(status.failing()), ["build-commodities"])
        status.record_failure("usda-psd", "HTTP 503")
        status.record_failure("eia-spot", "HTTP 503")
        self.assertEqual(sorted(status.failing()), ["build-commodities", "usda-psd"])
        status.record_failure("eia-spot", "HTTP 503")
        self.assertEqual(sorted(status.failing()), ["build-commodities", "eia-spot", "usda-psd"])
        self.assertEqual(status.get("baci").get("alert_after"), None)
        status.record_failure("baci", "CEPII pages unreachable: HTTP 403")
        self.assertEqual(status.get("baci")["alert_after"], 2)


class TwoJobsWriteTheStatus(StatusSandbox):
    """Two workflows that ran at the same time both rewrote updates.json and log.jsonl: the merge keeps everything."""

    def two_versions(self):
        status.record_success("usda-psd", records=1)
        base = (status.load(), open(status.LOG).read())
        time.sleep(1.05)
        status.record_success("wb-pink", records=802)  # the price job
        a = (status.load(), open(status.LOG).read())
        os.replace(os.path.join(self.tmp, "updates.json"), os.path.join(self.tmp, "a.json"))
        with open(status.UPDATES, "w") as fh:
            json.dump(base[0], fh)
        with open(status.LOG, "w") as fh:
            fh.write(base[1])
        status.record_success("portwatch", records=80528)  # the PortWatch job, from the same base
        status.record_failure("usda-psd", "HTTP 503")
        b = (status.load(), open(status.LOG).read())
        return a, b

    def test_no_entry_and_no_log_line_is_lost(self):
        a, b = self.two_versions()
        merged = status.merge_updates(a[0], b[0])
        self.assertEqual(sorted(merged["sources"]), ["portwatch", "usda-psd", "wb-pink"])
        self.assertEqual(merged["sources"]["usda-psd"]["consecutive_failures"], 1)  # the later attempt wins
        self.assertEqual(merged["updated"], max(a[0]["updated"], b[0]["updated"]))
        lines = status.merge_log(a[1], b[1]).splitlines()
        self.assertEqual(sorted(json.loads(x)["source"] for x in lines), ["portwatch", "usda-psd", "usda-psd", "wb-pink"])
        self.assertEqual([json.loads(x)["t"] for x in lines], sorted(json.loads(x)["t"] for x in lines))
        self.assertEqual(status.merge_updates(b[0], a[0])["sources"], merged["sources"])  # either order

    def test_the_git_merge_driver_writes_the_union_into_the_current_version(self):
        a, b = self.two_versions()
        for name, ours, theirs in (("data/_status/updates.json", json.dumps(a[0]), json.dumps(b[0])), ("data/_status/log.jsonl", a[1], b[1])):
            po, pt = os.path.join(self.tmp, "ours"), os.path.join(self.tmp, "theirs")
            open(po, "w").write(ours)
            open(pt, "w").write(theirs)
            self.assertEqual(status.merge_driver(os.devnull, po, pt, name), 0)
            text = open(po).read()
            for src in ("portwatch", "wb-pink"):
                self.assertIn(src, text)
        with open(pt, "w") as fh:
            fh.write("{broken")
        self.assertEqual(status.merge_driver(os.devnull, po, pt, "data/_status/updates.json"), 1)  # git then reports a conflict

    def test_the_log_keeps_its_last_lines_only(self):
        a = "".join(json.dumps({"t": f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}Z", "source": "a"}) + "\n" for i in range(400))
        b = "".join(json.dumps({"t": f"2026-01-02T00:{i // 60:02d}:{i % 60:02d}Z", "source": "b"}) + "\n" for i in range(400))
        lines = status.merge_log(a, b).splitlines()
        self.assertEqual(len(lines), status.LOG_KEEP)
        self.assertEqual(json.loads(lines[-1])["source"], "b")

    def test_the_workflows_declare_the_driver_and_share_one_concurrency_group(self):
        attrs = open(os.path.join(ROOT, ".gitattributes")).read()
        for f in ("data/_status/updates.json", "data/_status/log.jsonl"):
            self.assertIn(f"{f} merge=status-union", attrs)
        push = open(os.path.join(ROOT, ".github", "actions", "finish-data-update", "push.sh")).read()
        self.assertIn("status.py merge-driver %O %A %B %P", push)
        self.assertNotIn("-X theirs", push + open(os.path.join(ROOT, ".github", "actions", "finish-data-update", "action.yml")).read())
        for name in ("update-prices", "update-portwatch", "update-annual"):
            wf = open(os.path.join(ROOT, ".github", "workflows", name + ".yml")).read()
            self.assertIn("concurrency:\n  group: data-update\n  cancel-in-progress: false", wf, name)
            self.assertIn("since: ${{ steps.start.outputs.t }}", wf, name)
            self.assertNotIn('paths: "data ', wf, name)  # only the folders the job writes
            self.assertNotIn("FRED_API_KEY", wf, name)


class Staleness(unittest.TestCase):
    NOW = datetime(2026, 12, 20, tzinfo=timezone.utc)

    def doc(self, **entries):
        return {"sources": entries}

    def test_fresh_sources(self):
        r = S.check(self.doc(**{
            "eia-spot": {"last_success": "2026-12-17T21:50:00Z", "data_to": "2026-12-15"},
            "wb-pink": {"last_success": "2026-12-17T21:50:00Z", "data_to": "2026-11"},
            "usgs-mcs": {"last_success": "2026-12-15T22:30:00Z", "data_to": "2026"},
            "baci": {"last_success": "2026-12-15T22:30:00Z", "data_to": "2024", "state": {"version": "V202601"}},
        }), now=self.NOW)
        self.assertEqual(r["stale"], {})
        self.assertEqual(sorted(r["fresh"]), ["baci", "eia-spot", "usgs-mcs", "wb-pink"])

    def test_a_source_that_stopped_without_failing_is_stale(self):
        r = S.check(self.doc(**{
            # a workflow disabled by GitHub: no failure, no success either
            "eia-spot": {"last_success": "2026-11-18T21:50:00Z", "data_to": "2026-11-17", "consecutive_failures": 0},
            # the job runs but the publisher serves the same file
            "portwatch": {"last_success": "2026-12-16T19:30:00Z", "data_to": "2026-11-20"},
            "wb-pink": {"last_success": "2026-12-17T21:50:00Z", "data_to": "2026-09"},
            "usda-psd": {"last_success": "2026-10-15T22:30:00Z"},
        }), now=self.NOW)
        self.assertEqual(sorted(r["stale"]), ["eia-spot", "portwatch", "usda-psd", "wb-pink"])
        self.assertIn("no successful check for 31 days", r["stale"]["eia-spot"])
        self.assertIn("2026-11-20", r["stale"]["portwatch"])

    def test_yearly_releases_are_stale_after_their_month_plus_a_margin(self):
        april = datetime(2027, 4, 10, tzinfo=timezone.utc)
        doc = self.doc(**{"usgs-mcs": {"last_success": "2027-03-15T22:30:00Z", "data_to": "2026"},
                          "baci": {"last_success": None, "consecutive_failures": 4, "data_to": "2024", "state": {"version": "V202601"}}})
        r = S.check(doc, now=april)
        self.assertEqual(sorted(r["stale"]), ["baci", "usgs-mcs"])
        self.assertIn("docs/UPDATING.md", r["stale"]["baci"])
        self.assertEqual(S.check(doc, now=datetime(2027, 3, 1, tzinfo=timezone.utc))["stale"], {})


class DownloadedInputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def csv(self, header, rows=("1,2,3,4,5,6,7,8,9",)):
        p = os.path.join(self.tmp, "x.csv")
        with open(p, "w", newline="") as fh:
            fh.write(header + "\n" + "\n".join(rows) + "\n")
        return p

    def test_a_renamed_column_fails_the_download(self):
        cols = list(I.PSD_COLUMNS)
        cols[cols.index("Attribute_Description")] = "Attribute_Name"
        with self.assertRaises(ValueError) as e:
            I.csv_header(self.csv(",".join(cols)), I.PSD_COLUMNS)
        self.assertIn("Attribute_Description", str(e.exception))

    def test_a_header_decorated_with_spaces_and_asterisks_is_matched_and_rewritten(self):
        cols = [c + " **" if i % 2 else " " + c for i, c in enumerate(I.PSD_COLUMNS)]
        p = self.csv(",".join(f'"{c}"' for c in cols))
        self.assertEqual(I.csv_header(p, I.PSD_COLUMNS), I.PSD_COLUMNS)
        with open(p) as fh:
            self.assertEqual(fh.readline().strip(), ",".join(I.PSD_COLUMNS))
            self.assertEqual(fh.readline().strip(), "1,2,3,4,5,6,7,8,9")
        self.assertEqual(I.norm_header("Potassium chloride ** "), "Potassium chloride")

    def test_a_missing_commodity_or_attribute_of_the_pages_fails(self):
        import pandas as pd
        rows = [(c, a) for c in I.PSD_COMMODITIES for a in I.PSD_ATTRIBUTES]
        df = pd.DataFrame(rows, columns=["Commodity_Description", "Attribute_Description"])
        I.psd_content(df)
        with self.assertRaises(ValueError) as e:
            I.psd_content(df[df["Commodity_Description"] != "Oil, Palm"])
        self.assertIn("Oil, Palm", str(e.exception))

    def test_the_expected_eia_series_are_those_of_the_builder_and_a_missing_one_fails(self):
        need = I.eia_expected()
        self.assertIn(("57-1", "TBPD"), need)
        self.assertGreater(len(need), 20)
        lines = ['{"series_id":"INTL.%s-USA-%s.A","name":"x"}' % (f, u) for f, u in need]
        I.eia_content(I.eia_found(lines), need)
        with self.assertRaises(ValueError) as e:
            I.eia_content(I.eia_found(lines[1:]), need)
        self.assertIn("expected EIA series missing", str(e.exception))
        self.assertEqual(I.eia_found(['{"series_id":"INTL.57-1-USA-TBPD.M","name":"monthly"}']), set())


class SourceTimeLimit(unittest.TestCase):
    def test_a_hung_source_is_stopped_and_recorded_as_failed_while_the_others_run(self):
        import update_annual as UA

        def hung(opts):
            time.sleep(5)

        calls = []
        with mock.patch.dict(UA.SOURCES, {"usda-psd": hung, "eia-intl": lambda o: {"changed": False, "note": "unchanged"}}, clear=True), \
                mock.patch.dict(UA.SOURCE_MIN, {"usda-psd": 1 / 60}), \
                mock.patch.object(UA.status, "record_failure", lambda s, e, previous=None: calls.append(("fail", s, str(e)))), \
                mock.patch.object(UA.status, "record_success", lambda s, **k: calls.append(("ok", s))), \
                mock.patch.object(UA.status, "begin", lambda s: None), mock.patch.object(UA, "process", lambda c: None), \
                mock.patch.object(sys, "argv", ["update_annual.py", "--no-process"]):
            t0 = time.monotonic()
            UA.main()
        self.assertLess(time.monotonic() - t0, 4)
        self.assertEqual(calls[0][:2], ("fail", "usda-psd"))
        self.assertIn("time limit", calls[0][2])
        self.assertEqual(calls[1], ("ok", "eia-intl"))


class Vintage(unittest.TestCase):
    """The years and editions the published pages name are those of the inputs loaded (common/vintage.py): after a new
    USGS edition, BACI version or PSD market year, a label left on the old one fails here."""

    @classmethod
    def setUpClass(cls):
        import vintage as V
        cls.V = V
        cls.edition, cls.baci, cls.my = V.usgs_edition(), V.baci_year(), V.psd_market_year()
        cls.words, cls.years = {}, {}
        for folder in ("commodities", "countries/profiles"):
            for f in sorted(os.listdir(os.path.join(ROOT, "data", folder))):
                if not f.endswith(".json"):
                    continue
                text = open(os.path.join(ROOT, "data", folder, f), encoding="utf-8").read()
                for m in __import__("re").finditer(r"(MCS|BACI) (\d{4})\b|market year (\d{4})/\d{2}", text):
                    key = m.group(1) or "PSD"
                    cls.words.setdefault(key, set()).add(int(m.group(2) or m.group(3)))
                if folder == "commodities":
                    def visit(o):
                        if isinstance(o, list):
                            for x in o:
                                visit(x)
                        elif isinstance(o, dict):
                            if o.get("s") in ("usgs-mcs", "baci", "usda-psd") and o.get("y") is not None:
                                m = __import__("re").match(r"\d{4}", str(o["y"]))
                                if m:
                                    cls.years.setdefault(o["s"], set()).add(int(m.group(0)))
                            for v in o.values():
                                visit(v)
                    visit(json.loads(text))

    def test_the_usgs_edition_named_is_the_one_loaded(self):
        self.assertEqual(self.words.get("MCS", {self.edition}), {self.edition})
        self.assertEqual(max(self.years["usgs-mcs"]), self.edition - 1)  # an edition reports the year before it

    def test_the_baci_year_named_is_the_one_loaded(self):
        self.assertEqual(max(self.words.get("BACI", {self.baci})), self.baci)
        self.assertEqual(max(self.years["baci"]), self.baci)

    def test_the_psd_market_years_named_are_the_forecast_and_the_estimate_loaded(self):
        self.assertLessEqual(self.words.get("PSD", set()), {self.my, self.my - 1})
        self.assertEqual(max(self.years["usda-psd"]), self.my)

    def test_the_builder_takes_its_years_from_the_vintage_module(self):
        src = open(os.path.join(ROOT, "pipeline", "commodities", "build_commodities.py"), encoding="utf-8").read()
        self.assertIn("from common import vintage as V", src)
        self.assertNotRegex(src, r'"MCS20\d\d_Commodities_Data\.csv"')
        self.assertNotRegex(src, r"\n    my = 20\d\d\n")

    def test_a_clone_without_raw_reads_the_same_years(self):
        with mock.patch.object(self.V, "RAW", os.path.join(ROOT, "no-raw-here")), \
                mock.patch.object(self.V, "PSD_FILE", os.path.join(ROOT, "no-raw-here", "psd.csv")):
            self.assertEqual(self.V.usgs_edition(), self.edition)
            self.assertEqual(self.V.psd_market_year(), self.my)


class ReleaseWatcher(unittest.TestCase):
    def test_a_new_date_or_header_is_reported_and_an_unreadable_page_is_an_error_not_a_release(self):
        import watch_releases as W
        entries = [{"id": "page", "name": "A page", "url": "https://example.invalid/page", "rule": "text",
                    "pattern": r"Last Updated:</strong>\s*([A-Z][a-z]+ \d{1,2}, \d{4})", "known": "March 3, 2026", "todo": ["read it"]},
                   {"id": "pdf", "name": "A report", "url": "https://example.invalid/r.pdf", "rule": "header", "known": "Wed, 10 Jun 2026 09:19:49 GMT"}]
        same = W.check(entries, get_text=lambda u: "<p><strong>Last Updated:</strong> March 3, 2026</p>",
                       head=lambda u: {"Last-Modified": "Wed, 10 Jun 2026 09:19:49 GMT"})
        self.assertEqual((same["changed"], sorted(same["same"]), same["errors"]), ({}, ["page", "pdf"], {}))
        new = W.check(entries, get_text=lambda u: "<p><strong>Last Updated:</strong> February 27, 2027</p>",
                      head=lambda u: {"ETag": '"abc"'})
        self.assertEqual(new["changed"]["page"]["now"], "February 27, 2027")
        self.assertEqual(new["changed"]["pdf"]["now"], '"abc"')
        broken = W.check(entries[:1], get_text=lambda u: "<p>a new layout</p>")
        self.assertEqual(list(broken["errors"]), ["page"])

    def test_the_watch_list_is_complete(self):
        entries = json.load(open(os.path.join(ROOT, "pipeline", "common", "release_watch.json")))
        registry = {s["id"] for s in json.load(open(os.path.join(ROOT, "data", "sources.json")))}
        for e in entries:
            self.assertIn(e["id"], registry)
            self.assertIn(e["rule"], ("text", "header"))
            self.assertTrue(e["known"] and e["todo"] and e["url"].startswith("https://"), e["id"])


class Downloader(unittest.TestCase):
    def test_the_user_agent_is_plain_and_truthful(self):
        import fetch
        ua = fetch.USER_AGENT
        self.assertEqual(ua, "data-update-script/1.0 (python-requests)")
        for word in ("Mozilla", "Chrome", "Safari", "@", "github", "http"):
            self.assertNotIn(word.lower(), ua.lower())

    def test_every_update_script_downloads_through_the_shared_downloader(self):
        for dirpath, _, files in os.walk(os.path.join(ROOT, "pipeline")):
            if "tests" in dirpath or "__pycache__" in dirpath:
                continue
            for f in files:
                if f.endswith(".py") and f != "fetch.py":
                    text = open(os.path.join(dirpath, f), encoding="utf-8").read()
                    for bad in ("urllib.request", "urlopen(", "requests.get(", "requests.Session("):
                        self.assertNotIn(bad, text, f"{f} downloads without common/fetch.py")


if __name__ == "__main__":
    unittest.main()
