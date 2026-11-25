"""Tests of the scheduled update machinery: the status module (a step that stopped before it recorded anything, two
jobs that wrote the status files at the same time, the alert thresholds), the staleness check, the checks of the
downloaded inputs (a renamed column, a decorated header, a missing commodity or series), the time limit of a source
in update_annual.py, and the identification of the downloader.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_update_jobs.py"
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
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


class RawArtifact(unittest.TestCase):
    """The downloads of the annual job kept between runs as a workflow artifact (restore_raw.py, update-annual.yml)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def zip(self, members):
        import zipfile
        p = os.path.join(self.tmp, "a.zip")
        with zipfile.ZipFile(p, "w") as z:
            for name, text in members.items():
                z.writestr(name, text)
        return p

    def test_the_three_folders_are_restored_and_nothing_else(self):
        import restore_raw as RR
        raw = os.path.join(self.tmp, "raw")
        os.makedirs(os.path.join(raw, "usgs"))
        open(os.path.join(raw, "usgs", "kept.csv"), "w").write("on disk")
        p = self.zip({"usda/psd_csv/psd_alldata.csv": "a", "usda/psd_alldata_csv.zip": "z", "raw/eia/INTL.txt": "b",
                      "usgs/other.csv": "c", "../evil.txt": "x", "worldbank/x.xlsx": "y", "usda/../../evil2.txt": "x"})
        work = os.path.join(self.tmp, "work")
        os.makedirs(work)
        moved = RR.install(p, raw, work)
        self.assertEqual(moved, {"usda": 2, "eia": 1})
        self.assertEqual(open(os.path.join(raw, "usda", "psd_csv", "psd_alldata.csv")).read(), "a")
        self.assertEqual(open(os.path.join(raw, "eia", "INTL.txt")).read(), "b")
        self.assertEqual(os.listdir(os.path.join(raw, "usgs")), ["kept.csv"])  # a folder already on disk is not replaced
        self.assertEqual(sorted(os.listdir(raw)), ["eia", "usda", "usgs"])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "evil.txt")) or os.path.exists(os.path.join(self.tmp, "evil2.txt")))

    def test_an_empty_or_corrupt_artifact_changes_nothing(self):
        import zipfile
        import restore_raw as RR
        raw = os.path.join(self.tmp, "raw")
        with self.assertRaises(ValueError):
            RR.install(self.zip({"other/x": "y"}), raw, os.path.join(self.tmp, "w1"))
        bad = os.path.join(self.tmp, "bad.zip")
        open(bad, "wb").write(b"PK\x03\x04 not a zip")
        with self.assertRaises(zipfile.BadZipFile):
            RR.install(bad, raw, os.path.join(self.tmp, "w2"))
        self.assertFalse(os.path.exists(raw))

    def test_the_newest_unexpired_artifact_of_its_name_is_chosen(self):
        import restore_raw as RR
        now = datetime(2026, 12, 15, 22, 30, tzinfo=timezone.utc)
        art = lambda i, made, name="raw-annual", expired=False: {"id": i, "name": name, "expired": expired, "created_at": made}  # noqa: E731
        listing = {"artifacts": [art(1, "2026-10-15T23:00:00Z"), art(2, "2026-11-15T23:00:00Z"), art(3, "2026-12-01T00:00:00Z", "portwatch-daily"),
                                 art(4, "2026-12-10T00:00:00Z", expired=True)]}
        pick = RR.RP.newest_usable(listing, now, max_age_days=RR.MAX_AGE_DAYS, name=RR.NAME)
        self.assertEqual(pick["id"], 2)  # two months old is still usable: the job is monthly
        self.assertEqual(RR.RP.newest_usable(listing, now)["id"] if RR.RP.newest_usable(listing, now) else None, 3)

    def test_off_github_the_script_does_nothing(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "pipeline", "annual", "restore_raw.py")], capture_output=True,
                           text=True, env={k: v for k, v in os.environ.items() if k != "GITHUB_REPOSITORY"}, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertIn("nothing to restore", r.stdout)

    def test_a_source_is_unchanged_only_when_the_file_on_disk_is_the_one_downloaded(self):
        import update_annual as UA
        raw = os.path.join(self.tmp, "raw")
        os.makedirs(os.path.join(raw, "usda", "psd_csv"))
        open(os.path.join(raw, "usda", "psd_csv", "psd_alldata.csv"), "w").write("older")
        new_zip = b"PK new release"

        def download(url, path, **k):
            open(path, "wb").write(new_zip)

        import hashlib
        digest = hashlib.sha256(new_zip).hexdigest()
        with mock.patch.object(UA, "RAW", raw), mock.patch.object(UA.fetch, "download", download), \
                mock.patch.object(UA.status, "get", lambda s: {"state": {"sha256": digest}}):
            # the status file records the new release, but raw/ holds an older one (an artifact of an earlier run)
            open(os.path.join(raw, "usda", "psd_alldata_csv.zip"), "wb").write(b"PK older release")
            with self.assertRaises(Exception):  # not "unchanged": the new zip is opened (and is no zip here)
                UA.src_usda(None)
            open(os.path.join(raw, "usda", "psd_alldata_csv.zip"), "wb").write(new_zip)
            self.assertEqual(UA.src_usda(None), {"changed": False, "note": "unchanged"})

    def test_the_workflow_keeps_raw_as_an_artifact_of_90_days(self):
        wf = open(os.path.join(ROOT, ".github", "workflows", "update-annual.yml")).read()
        self.assertNotIn("actions/cache@", wf)
        self.assertIn("run: python pipeline/annual/restore_raw.py", wf)
        self.assertIn("actions: read", wf)
        self.assertIn("name: raw-annual", wf)
        self.assertIn("retention-days: 90", wf)
        for p in ("raw/usda", "raw/eia", "raw/usgs"):
            self.assertIn(p, wf)


class WorkflowSignals(unittest.TestCase):
    """What the workflows say when something goes wrong: the shape of the YAML, read as text and as data."""

    def read(self, *p):
        with open(os.path.join(ROOT, ".github", *p), encoding="utf-8") as fh:
            return fh.read()

    def test_the_watchers_set_up_python_with_the_pinned_action_and_report_their_own_failure(self):
        pinned = "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0"
        self.assertIn(pinned, self.read("workflows", "update-prices.yml"))
        for name in ("watch-releases.yml", "check-staleness.yml"):
            wf = self.read("workflows", name)
            self.assertIn(pinned, wf, name)
            self.assertLess(wf.index(pinned), wf.index("run: python pipeline/common/"), name)
            self.assertNotIn("python3 pipeline", wf, name)
            self.assertIn("Watcher failing: ${context.workflow}", wf, name)
            self.assertIn("shell: bash\n", wf, name)  # pipefail through tee

    def test_the_deploy_reports_an_unpublished_site_and_data_jobs_grant_it(self):
        wf = self.read("workflows", "deploy.yml")
        self.assertIn("'Site not republished: a check failed'", wf)
        self.assertIn("needs: [checks, build, deploy]", wf)
        self.assertEqual(wf.count("continue-on-error: ${{ inputs.soft == true }}"), 5)  # install, validate, build, upload, deploy-pages
        self.assertIn("failed: ${{ steps.verdict.outputs.failed }}", self.read("workflows", "ci.yml"))
        for name in ("update-prices", "update-portwatch", "update-annual"):
            self.assertIn("issues: write   # the issue \"Site not republished", self.read("workflows", name + ".yml"), name)

    def test_the_discard_reverts_path_by_path_and_a_push_that_failed_is_recorded(self):
        action = self.read("actions", "finish-data-update", "action.yml")
        self.assertIn('for p in $PATHS; do\n          git checkout -- "$p" 2> /dev/null || true', action)
        self.assertIn("if: steps.validate.outcome != 'failure' || steps.discard.outputs.clean == 'true'", action)
        self.assertIn("const pTitle = 'Data update not pushed';", action)
        push = self.read("actions", "finish-data-update", "push.sh")
        self.assertIn('status.py fail "$s" "update not pushed: $reason"', push)
        self.assertNotIn("push -f", push)
        self.assertNotIn("--force", push)


def _text(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as fh:
        return fh.read()


def workflow_steps(text, job="update"):
    """[{name, id, continue-on-error, timeout-minutes, run, uses}] of the steps of ``job``, and the job's own timeout (minutes), read as
    text (the shape of these workflow files; no YAML library is a dependency of the pipeline)."""
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln == f"  {job}:")
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^  \S", lines[i])), len(lines))
    block = lines[start:end]
    job_limit = next((int(m.group(1)) for ln in block if (m := re.match(r"^    timeout-minutes: (\d+)", ln))), None)
    steps, cur = [], None
    for ln in block[next(i for i, x in enumerate(block) if x == "    steps:") + 1:]:
        if ln.startswith("      - "):
            cur = {}
            steps.append(cur)
            ln = "        " + ln[8:]
        if cur is not None and (m := re.match(r"^        ([\w-]+): ?(.*)$", ln)):
            cur[m.group(1)] = m.group(2)
    return steps, job_limit


def run_block(text, step_name):
    """The shell of the ``run: |`` of the step ``step_name`` of a workflow or an action file, dedented."""
    lines = text.splitlines()
    i = next(k for k, ln in enumerate(lines) if ln.strip() == f"- name: {step_name}")
    indent = len(lines[i]) - len(lines[i].lstrip())
    for k in range(i + 1, len(lines)):
        ln = lines[k]
        if ln.strip().startswith("- name:") and len(ln) - len(ln.lstrip()) == indent:
            break
        if ln.strip() == "run: |":
            base = len(ln) - len(ln.lstrip()) + 2
            out = []
            for m in lines[k + 1:]:
                if m.strip() and len(m) - len(m.lstrip()) < base:
                    break
                out.append(m[base:] if m.strip() else "")
            return "\n".join(out)
    raise KeyError(step_name)


class JobLimits(unittest.TestCase):
    """A job that reaches its own limit is cancelled before its last step can record anything: a red run, and an e-mail. Each update job
    therefore holds the limits of its steps and fifteen minutes more, for the steps that have none (checkout, the set-up of Python
    and Node, the finish action)."""

    def test_every_update_job_holds_the_limits_of_its_steps_and_fifteen_minutes_more(self):
        for name in ("update-prices.yml", "update-portwatch.yml", "update-annual.yml"):
            steps, job_limit = workflow_steps(_text(".github", "workflows", name))
            limits = [int(x["timeout-minutes"]) for x in steps if "timeout-minutes" in x]
            self.assertTrue(limits, name)
            self.assertIsNotNone(job_limit, name)
            self.assertGreaterEqual(job_limit, sum(limits) + 15, f"{name}: the job stops at {job_limit} minutes, its steps may take {sum(limits)}")


class PortStepInTheJob(unittest.TestCase):
    """The PortWatch job has a second step for the port series. Its shape is read from the workflow; what the finish action does with
    each way that step can end is run on a copy of the data in a temporary repository (the shell of the action as it is in action.yml:
    record, validate, discard, commit and push to a local remote); the two update steps are replaced by their effects."""

    WF = ".github/workflows/update-portwatch.yml"
    PORTS = "portwatch-port-traffic"

    @classmethod
    def setUpClass(cls):
        cls.wf = _text(".github", "workflows", "update-portwatch.yml")
        cls.action = _text(".github", "actions", "finish-data-update", "action.yml")
        cls.steps, cls.job_limit = workflow_steps(cls.wf)

    # ------------------------------------------------------------------------------------------ the shape of the job
    def step(self, step_id):
        return next(x for x in self.steps if x.get("id") == step_id)

    def test_the_limit_of_the_job_holds_the_limits_of_its_steps_and_fifteen_minutes_more(self):
        limits = [int(x["timeout-minutes"]) for x in self.steps if "timeout-minutes" in x]
        self.assertGreaterEqual(len(limits), 7)
        self.assertEqual(sum(limits), 10 + 5 + 25 + 15 + 1 + 5 + 5 + 5)
        self.assertGreaterEqual(self.job_limit, sum(limits) + 15, "a job limit that is hit is a red run and an e-mail")
        # the other PortWatch step of the job keeps the limit it had
        self.assertEqual(self.step("fetch")["timeout-minutes"], "25")

    def test_the_port_step_follows_the_chokepoint_step_cannot_turn_the_job_red_and_is_stopped_by_its_limit(self):
        order = [x.get("id") or x.get("name") for x in self.steps]
        self.assertLess(order.index("fetch"), order.index("ports"))
        self.assertLess(order.index("ports"), order.index("alerts"))
        port = self.step("ports")
        self.assertEqual(port["continue-on-error"], "true")
        self.assertEqual(port["timeout-minutes"], "15")
        self.assertEqual(port["run"], "python pipeline/freight/fetch_portwatch_port_traffic.py")
        self.assertNotIn("--", port["run"], "the scheduled step takes no option: the weekly run")
        self.assertEqual(self.step("fetch")["continue-on-error"], "true")
        self.assertNotIn("if", port, "the step runs whatever the chokepoint step did")
        # no step of the job can turn it red: every step that runs a script is continue-on-error
        for x in self.steps:
            if x.get("run") and "timeout-minutes" in x:
                self.assertEqual(x.get("continue-on-error"), "true", x.get("name"))

    def test_the_finish_step_records_commits_and_validates_the_port_series_with_the_other_sources(self):
        self.assertIn('sources: "portwatch portwatch-port-traffic build-alerts build-market-now build-changes"', self.wf)
        paths = re.search(r'^\s+paths: "([^"]+)"', self.wf, re.M).group(1).split()
        self.assertIn("data/freight/port-traffic", paths)
        self.assertIn("data/freight/portwatch", paths)
        self.assertIn("data/_status", paths)
        steps_arg = re.search(r"steps: \|\n((?:\s+\$\{\{.*\n)+)", self.wf).group(1).split("\n")
        lines = [ln.strip() for ln in steps_arg if ln.strip()]
        self.assertIn("${{ steps.ports.outcome }} portwatch-port-traffic", lines)
        self.assertIn("${{ steps.fetch.outcome }} portwatch", lines)
        # every step that has an id has its outcome line: a step that does not finish is recorded as failed
        self.assertEqual(sorted(re.search(r"steps\.(\w+)\.outcome", ln).group(1) for ln in lines),
                         sorted(x["id"] for x in self.steps if x.get("id") in ("fetch", "ports", "alerts", "market", "changes")))
        # the calendar of the About window names the sources of the job as the finish step does
        import changes
        self.assertEqual(set(changes.JOBS["update-portwatch"]), {"portwatch", "portwatch-port-traffic"})

    def test_no_restore_step_and_no_artifact_for_the_ports(self):
        self.assertEqual(len(re.findall(r"restore_", self.wf)), 1)
        self.assertEqual(self.wf.count("upload-artifact"), 1)
        artifact = self.wf[self.wf.index("upload-artifact"):]
        self.assertIn("name: portwatch-daily", artifact)
        self.assertIn("path: pipeline/cache/portwatch\n", artifact)
        self.assertNotIn("port-traffic", artifact)
        self.assertNotIn("port-traffic", "\n".join(x.get("run", "") for x in self.steps if x.get("id") != "ports" and "rm -f" not in x.get("run", "")))

    def test_a_port_file_left_half_written_by_a_killed_step_is_removed_before_the_checks(self):
        names = [x.get("name") for x in self.steps]
        i = names.index("Remove a port file left half written")
        self.assertEqual(names[i - 1], "Fetch PortWatch port traffic and rebuild the port series")
        self.assertEqual(self.steps[i]["run"], "rm -f data/freight/port-traffic/*.tmp")
        self.assertEqual(self.steps[i]["continue-on-error"], "true")

    def test_the_schedule_is_the_one_it_was(self):
        self.assertIn('cron: "17 19 * * 3"', self.wf)
        self.assertEqual(self.wf.count("cron:"), 1)

    # ------------------------------------------------------------------------------------------ the job, simulated
    @classmethod
    def sandbox(cls):
        """A temporary repository with a copy of data/, the data checks, status.py and push.sh, and a bare remote it pushes to."""
        if getattr(cls, "_box", None):
            return cls._box
        box = tempfile.mkdtemp()
        cls._box = box
        repo, remote, bin_ = os.path.join(box, "repo"), os.path.join(box, "origin.git"), os.path.join(box, "bin")
        os.makedirs(os.path.join(repo, "web", "scripts"))
        os.makedirs(os.path.join(repo, "pipeline", "common"))
        os.makedirs(os.path.join(repo, ".github", "actions", "finish-data-update"))
        os.makedirs(bin_)
        os.symlink(sys.executable, os.path.join(bin_, "python"))
        shutil.copytree(os.path.join(ROOT, "data"), os.path.join(repo, "data"))
        for f in os.listdir(os.path.join(ROOT, "web", "scripts")):
            if f.endswith(".mjs") and not f.endswith(".test.mjs"):
                shutil.copy(os.path.join(ROOT, "web", "scripts", f), os.path.join(repo, "web", "scripts", f))
        shutil.copy(os.path.join(ROOT, "pipeline", "common", "status.py"), os.path.join(repo, "pipeline", "common", "status.py"))
        shutil.copy(os.path.join(ROOT, ".github", "actions", "finish-data-update", "push.sh"),
                    os.path.join(repo, ".github", "actions", "finish-data-update", "push.sh"))
        shutil.copy(os.path.join(ROOT, ".gitattributes"), os.path.join(repo, ".gitattributes"))
        for ln in (["git", "init", "-q", "-b", "main"], ["git", "config", "user.email", "t@example.invalid"], ["git", "config", "user.name", "t"],
                   ["git", "config", "commit.gpgsign", "false"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "base"]):
            subprocess.run(ln, cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", remote], check=True, capture_output=True)
        subprocess.run(["git", "remote", "add", "origin", remote], cwd=repo, check=True)
        subprocess.run(["git", "push", "-q", "origin", "main"], cwd=repo, check=True, capture_output=True)
        cls.base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
        return box

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "_box", None):
            shutil.rmtree(cls._box, ignore_errors=True)

    def setUp(self):
        box = self.sandbox()
        self.repo, self.remote = os.path.join(box, "repo"), os.path.join(box, "origin.git")
        self.env = dict(os.environ, PATH=os.path.join(box, "bin") + os.pathsep + os.environ["PATH"], RUNNER_TEMP=box,
                        GITHUB_OUTPUT=os.path.join(box, "out.txt"), PYTHON=sys.executable)
        for k in ("GITHUB_ACTIONS", "DATA_GUARD", "STATUS_JOURNAL"):
            self.env.pop(k, None)
        self.env["STATUS_JOURNAL"] = os.path.join(box, "journal")
        for ln in (["git", "reset", "-q", "--hard", self.base], ["git", "clean", "-fdq"], ["git", "push", "-q", "-f", "origin", f"{self.base}:main"]):
            subprocess.run(ln, cwd=self.repo, check=True, capture_output=True)
        for f in ("out.txt", "journal", "data-validation.log"):
            if os.path.exists(os.path.join(box, f)):
                os.remove(os.path.join(box, f))
        self.since = "2026-11-25T19:17:00Z"

    def sh(self, script, **env):
        r = subprocess.run(["bash", "-c", script], cwd=self.repo, env={**self.env, **env}, capture_output=True, text=True)
        return r

    def py(self, code):
        r = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, 'pipeline/common'); import status\n" + code], cwd=self.repo,
                           env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def status(self):
        with open(os.path.join(self.repo, "data", "_status", "updates.json"), encoding="utf-8") as fh:
            return json.load(fh)["sources"]

    def chokepoint_update(self):
        """What the chokepoint step leaves: a changed series file and its success in the status file. Returns (path, new text)."""
        d = os.path.join(self.repo, "data", "freight", "portwatch")
        name = sorted(f for f in os.listdir(d) if f.endswith(".json"))[0]
        path = os.path.join(d, name)
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["updated_by_the_test"] = True
        text = json.dumps(doc, separators=(",", ":"))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.py("status.record_success('portwatch', records=80600, data_to='2026-11-20', note='updated')")
        return path, text

    def finish(self, outcomes, paths=None):
        """Run the finish action's shell: record, validate, discard, commit. ``outcomes`` {step id: outcome}. Returns what it decided."""
        steps_arg = re.search(r"steps: \|\n((?:\s+\$\{\{.*\n)+)", self.wf).group(1)
        steps_arg = re.sub(r"\$\{\{ steps\.(\w+)\.outcome \}\}", lambda m: outcomes.get(m.group(1), "success"), steps_arg)
        steps_arg = "\n".join(ln.strip() for ln in steps_arg.split("\n"))
        sources = re.search(r'^\s+sources: "([^"]+)"', self.wf, re.M).group(1)
        paths = paths or re.search(r'^\s+paths: "([^"]+)"', self.wf, re.M).group(1)
        res = {}
        self.sh(run_block(self.action, "Record a failure for an update step that did not finish"), STEPS=steps_arg, SINCE=self.since)
        v = self.sh(run_block(self.action, "Validate data"))
        res["validate"] = v.returncode
        res["validation"] = v.stdout + v.stderr
        out = os.path.join(self.env["RUNNER_TEMP"], "out.txt")
        if v.returncode != 0:
            d = self.sh(run_block(self.action, "Discard invalid data"), PATHS=paths, SOURCES=sources)
            res["discard"] = d.stdout + d.stderr
            res["clean"] = "clean=true" in open(out).read() if os.path.exists(out) else None
        if v.returncode == 0 or res.get("clean"):
            c = self.sh(run_block(self.action, "Commit and push"), MESSAGE="data: update PortWatch", DEFAULT_BRANCH="main", PATHS=paths,
                        SOURCES=sources, GITHUB_ACTION_PATH=os.path.join(self.repo, ".github", "actions", "finish-data-update"))
            res["push"] = c.stdout + c.stderr
        return res

    def remote_file(self, rel):
        r = subprocess.run(["git", "--git-dir", self.remote, "show", f"main:{rel}"], capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None

    def remote_changed(self):
        r = subprocess.run(["git", "--git-dir", self.remote, "diff", "--name-only", self.base, "main"], capture_output=True, text=True)
        return [x for x in r.stdout.split("\n") if x]

    def a_port_file(self):
        d = os.path.join(self.repo, "data", "freight", "port-traffic")
        name = sorted(f for f in os.listdir(d) if re.match(r"port\d+\.json$", f))[0]
        return os.path.join(d, name)

    def test_the_base_of_the_simulation_passes_the_checks_of_the_job(self):
        v = self.sh("node web/scripts/validate-data.mjs && node web/scripts/guard-data.mjs")
        self.assertEqual(v.returncode, 0, v.stdout + v.stderr)

    def test_a_port_step_that_fails_costs_the_chokepoint_update_nothing(self):
        """The script ends with exit 0 and a failure recorded (the service was down): the step succeeds, the files are as they were."""
        path, text = self.chokepoint_update()
        self.py(f"status.record_failure({self.PORTS!r}, 'HTTP 503 after 4 attempts (services9.arcgis.com)')")
        res = self.finish({"fetch": "success", "ports": "success", "alerts": "success", "changes": "success"})
        self.assertEqual(res["validate"], 0, res["validation"])
        self.assertEqual(self.remote_file(os.path.relpath(path, self.repo)), text)
        self.assertIn("data/_status/updates.json", self.remote_changed())
        self.assertFalse([x for x in self.remote_changed() if "port-traffic" in x])
        st = json.loads(self.remote_file("data/_status/updates.json"))["sources"]
        self.assertEqual((st["portwatch"]["consecutive_failures"], st[self.PORTS]["consecutive_failures"]), (0, 1))
        self.assertIsNone(st[self.PORTS]["last_success"])

    def test_a_port_step_killed_by_its_limit_is_recorded_as_failed_and_the_chokepoint_update_is_committed(self):
        path, text = self.chokepoint_update()
        # GitHub reports a step stopped by its timeout-minutes as a failure (continue-on-error keeps the job going); nothing was recorded
        res = self.finish({"fetch": "success", "ports": "failure", "alerts": "success", "changes": "success"})
        self.assertEqual(res["validate"], 0, res["validation"])
        self.assertEqual(self.remote_file(os.path.relpath(path, self.repo)), text)
        st = json.loads(self.remote_file("data/_status/updates.json"))["sources"]
        self.assertEqual(st["portwatch"]["consecutive_failures"], 0)
        self.assertEqual(st[self.PORTS]["consecutive_failures"], 1)
        self.assertIn("timed out, crashed or cancelled", st[self.PORTS]["last_error"])
        # and the alert step opens its issue at the third run, not before
        report = json.loads(self.sh("python pipeline/common/status.py report").stdout)
        self.assertNotIn(self.PORTS, report["failing"])
        self.assertIn(self.PORTS, report["all"])

    def test_a_port_file_left_half_written_is_refused_by_the_checks_unless_the_step_that_removes_it_ran(self):
        path, text = self.chokepoint_update()
        tmp = os.path.join(os.path.dirname(self.a_port_file()), "port1.json.tmp")
        with open(tmp, "w") as fh:
            fh.write('{"id":"port1"')
        removed = self.sh(self.steps_run("Remove a port file left half written"))
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse(os.path.exists(tmp))
        res = self.finish({"fetch": "success", "ports": "failure", "alerts": "success", "changes": "success"})
        self.assertEqual(res["validate"], 0, res["validation"])
        self.assertEqual(self.remote_file(os.path.relpath(path, self.repo)), text)
        # without that step the checks refuse the folder and discard the whole update
        subprocess.run(["git", "reset", "-q", "--hard", self.base], cwd=self.repo, check=True)
        subprocess.run(["git", "clean", "-fdq"], cwd=self.repo, check=True)
        subprocess.run(["git", "push", "-q", "-f", "origin", f"{self.base}:main"], cwd=self.repo, check=True, capture_output=True)
        path, text = self.chokepoint_update()
        with open(tmp, "w") as fh:
            fh.write('{"id":"port1"')
        res = self.finish({"fetch": "success", "ports": "failure", "alerts": "success", "changes": "success"})
        self.assertNotEqual(res["validate"], 0)
        self.assertIn("port1.json.tmp: not a port file", res["validation"])

    def steps_run(self, name):
        return next(x["run"] for x in self.steps if x.get("name") == name)

    def test_when_the_checks_refuse_a_port_file_the_whole_update_is_discarded_the_chokepoint_series_with_it(self):
        """The coupling that the script exists to avoid (it writes nothing that the checks refuse): when it does happen, every path of the job
        is put back to the last commit and a failure is recorded for each source of the job."""
        path, text = self.chokepoint_update()
        port = self.a_port_file()
        with open(port, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["calls"]["tanker"] = doc["calls"]["tanker"][:-1]          # the twelve arrays no longer have one length
        with open(port, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, separators=(",", ":"))
        res = self.finish({"fetch": "success", "ports": "success", "alerts": "success", "changes": "success"})
        self.assertNotEqual(res["validate"], 0)
        self.assertIn("freight/port-traffic/", res["validation"])
        self.assertTrue(res["clean"], res["discard"])
        self.assertEqual(self.remote_changed(), ["data/_status/log.jsonl", "data/_status/updates.json"])      # only the record of the failure
        with open(path, encoding="utf-8") as fh:
            self.assertNotIn("updated_by_the_test", fh.read(), "the chokepoint update was discarded with the rest")
        st = json.loads(self.remote_file("data/_status/updates.json"))["sources"]
        for source in ("portwatch", self.PORTS, "build-alerts", "build-market-now", "build-changes"):
            self.assertEqual(st[source]["consecutive_failures"], 1, source)
            self.assertTrue(st[source]["last_error"].startswith("update discarded: data validation failed"), source)

    def test_a_port_file_that_lost_weeks_is_refused_by_the_guard_in_the_same_way(self):
        path, text = self.chokepoint_update()
        port = self.a_port_file()
        with open(port, encoding="utf-8") as fh:
            doc = json.load(fh)
        for k in ("calls", "exports", "imports"):
            for t in doc[k]:
                doc[k][t] = doc[k][t][:-5]
        doc["y"] = (datetime.strptime(doc["y"], "%Y-%m-%d") - timedelta(days=35)).strftime("%Y-%m-%d")
        with open(port, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, separators=(",", ":"))
        res = self.finish({"fetch": "success", "ports": "success", "alerts": "success", "changes": "success"})
        self.assertNotEqual(res["validate"], 0)
        self.assertIn("lost weeks", res["validation"])
        self.assertTrue(res["clean"], res["discard"])
        with open(path, encoding="utf-8") as fh:
            self.assertNotIn("updated_by_the_test", fh.read())
        self.assertFalse([x for x in self.remote_changed() if "port-traffic" in x])
        # the same files, a hand reading accepted on purpose: the override lets the guard through (the validators have nothing to say)
        guard = self.sh("node web/scripts/guard-data.mjs data/freight/port-traffic", DATA_GUARD="off")
        self.assertEqual(guard.returncode, 0, guard.stdout + guard.stderr)


if __name__ == "__main__":
    unittest.main()
