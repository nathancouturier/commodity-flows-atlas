"""Tests of the "what changed" digest (pipeline/common/changes.py): price moves, passage moves, the sources that published,
the feed entries and the Atom file, and the calendar read from the workflows.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_changes.py"
"""
import json
import os
import sys
import tempfile
import unittest
import xml.dom.minidom
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("", "common"):
    p = os.path.join(ROOT, "pipeline", sub) if sub else os.path.join(ROOT, "pipeline")
    if p not in sys.path:
        sys.path.insert(0, p)

import changes as C  # noqa: E402

EPOCH = date(1970, 1, 1)


def day(iso):
    return (date.fromisoformat(iso) - EPOCH).days


def write(folder, name, doc):
    with open(os.path.join(folder, name + ".json"), "w") as fh:
        json.dump(doc, fh)


def prices_folder(tmp, last="2026-11-17", brent=(90.0, 99.0), other=(10.0, 10.1)):
    """Two daily series ending on ``last`` (a quote a week earlier and the last one), a stale one, and a monthly series."""
    d1 = day(last)
    idx = []
    for sid, (v0, v1) in (("a-d", brent), ("b-d", other)):
        write(tmp, sid, {"id": sid, "freq": "D", "d": [d1 - 10, d1 - 7, d1 - 3, d1], "v": [v0 * 2, v0, v0 * 1.05, v1]})
        idx.append({"id": sid, "name": sid.upper(), "k": "k", "unit": "USD", "freq": "D", "s": "eia-spot", "start": "2020-01", "end": last})
    write(tmp, "old-d", {"id": "old-d", "freq": "D", "d": [d1 - 30, d1 - 20], "v": [1, 5]})  # stopped three weeks earlier: not this week's news
    idx.append({"id": "old-d", "name": "OLD", "k": "k", "unit": "USD", "freq": "D", "s": "eia-spot", "start": "2020-01", "end": "x"})
    write(tmp, "m-m", {"id": "m-m", "freq": "M", "start": "2026-01", "v": [1, 2, 3, 4, 5, 6, 7, 8, 9, 12]})
    idx.append({"id": "m-m", "name": "M", "k": "k", "unit": "USD", "freq": "M", "s": "wb-pink", "start": "2026-01", "end": "2026-10"})
    write(tmp, "y-a", {"id": "y-a", "freq": "A", "start": "1960", "v": [1, 100]})  # annual series: left out
    idx.append({"id": "y-a", "name": "Y", "k": "k", "unit": "USD", "freq": "A", "s": "wb-pink", "start": "1960", "end": "2020"})
    write(tmp, "index", idx)


class PriceMoves(unittest.TestCase):
    def test_week_and_month(self):
        with tempfile.TemporaryDirectory() as tmp:
            prices_folder(tmp)
            weekly, monthly = C.price_moves(tmp)
            self.assertEqual(weekly["to"], "2026-11-17")
            ids = [m["id"] for m in weekly["moves"]]
            self.assertEqual(ids, ["a-d", "b-d"])  # the series that stopped earlier is left out; the largest move first
            a = weekly["moves"][0]
            self.assertEqual(a["from"], "2026-11-10")  # the last quote at least 7 days before
            self.assertEqual((a["v0"], a["v1"], a["pct"]), (90.0, 99.0, 10.0))
            self.assertEqual(monthly["to"], "2026-10")
            self.assertEqual(monthly["moves"][0]["pct"], round(100 * (12 / 9 - 1), 1))  # Oct against Sep
            self.assertEqual(monthly["moves"][0]["from"], "2026-09")

    def test_a_series_without_a_quote_a_week_before_is_left_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "index", [{"id": "n-d", "name": "N", "k": "k", "unit": "USD", "freq": "D", "s": "s", "start": "x", "end": "x"}])
            write(tmp, "n-d", {"id": "n-d", "freq": "D", "d": [day("2026-11-15"), day("2026-11-17")], "v": [1, 2]})
            self.assertEqual(C.price_moves(tmp)[0]["moves"], [])


class PassageMoves(unittest.TestCase):
    def folder(self, tmp, **perday):
        write(tmp, "x", {"compare": {"to": "2026-11-15", "perDay": perday}})

    def test_ranked_by_the_furthest_average_and_small_counts_left_out(self):
        with tempfile.TemporaryDirectory() as data:
            os.makedirs(os.path.join(data, "freight", "portwatch"))
            chk = [{"id": c, "name": c.upper() + " (long name)"} for c in ("a", "b", "c", "d")]
            json.dump(chk, open(os.path.join(data, "freight", "chokepoints.json"), "w"))
            series = os.path.join(data, "freight", "portwatch")
            write(series, "a", {"compare": {"to": "2026-11-15", "perDay": {"week": 50.0, "prior28": 100.0, "prior365": 100.0}}})   # -50%
            write(series, "b", {"compare": {"to": "2026-11-15", "perDay": {"week": 100.0, "prior28": 100.0, "prior365": 130.0}}})  # -23% on the year
            write(series, "c", {"compare": {"to": "2026-11-15", "perDay": {"week": 1.0, "prior28": 0.1, "prior365": 8.0}}})        # tiny counts: left out
            write(series, "d", {"compare": {"to": "2026-11-15", "perDay": {"week": 10.0, "prior28": None, "prior365": 10.0}}})     # no 28-day figure
            saved = C.DATA
            try:
                C.DATA = data
                out = C.passage_moves(series)
            finally:
                C.DATA = saved
            self.assertEqual([m["id"] for m in out["moves"]], ["a", "b"])
            self.assertEqual(out["moves"][0]["name"], "A")
            self.assertEqual((out["moves"][0]["gap28"], out["moves"][0]["gap365"]), (-50.0, -50.0))
            self.assertEqual(out["to"], "2026-11-15")


class Sources(unittest.TestCase):
    def entry(self, data_to, sha="abc"):
        return {"last_success": "2026-11-22T12:00:00Z", "data_to": data_to, "state": {"sha256": sha * 5}}

    def test_only_a_changed_source_is_reported_and_never_an_error(self):
        reg = [{"id": "eia-spot", "name": "EIA spot"}, {"id": "usda-psd", "name": "USDA PSD"}, {"id": "faostat", "name": "FAOSTAT"}, {"id": "wna", "name": "WNA"}]
        first = {"sources": {"eia-spot": self.entry("2026-11-10"), "usda-psd": self.entry("2027", "a"), "build-lanes": self.entry(None)}}
        items, prints = C.published(first, reg, None)
        self.assertEqual(items, [])  # the first run cannot tell what is new
        self.assertEqual(set(prints), {"eia-spot", "usda-psd"})  # build steps are not sources
        second = {"sources": {"eia-spot": self.entry("2026-11-17"), "usda-psd": self.entry("2027", "a"),
                              "faostat-wna": self.entry(None, "z")}}
        second["sources"]["eia-spot"]["last_error"] = "HTTP 403 for https://secret.example/x"
        items, _ = C.published(second, reg, prints)
        self.assertEqual([i["id"] for i in items], ["eia-spot", "faostat-wna"])
        self.assertEqual(items[1]["name"], "FAOSTAT and WNA")
        self.assertNotIn("secret", json.dumps(items))
        self.assertEqual(C.published(second, reg, C.published(second, reg, None)[1])[0], [])


class Digest(unittest.TestCase):
    def run_build(self, prices, prev, now, updates, series):
        reg = [{"id": "eia-spot", "name": "EIA spot"}]
        return C.build(prices_dir=prices, series_dir=series, now=now, previous=prev, updates=updates, registry=reg)

    def test_entries_are_added_once_and_only_when_news_arrive(self):
        with tempfile.TemporaryDirectory() as tmp:
            prices = os.path.join(tmp, "prices")
            os.makedirs(prices)
            prices_folder(prices)
            empty = os.path.join(tmp, "none")
            os.makedirs(empty)
            t1 = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)
            upd = {"sources": {"eia-spot": {"last_success": "2026-11-24T17:50:00Z", "data_to": "2026-11-17", "state": {}}}}
            doc, changed = self.run_build(prices, {}, t1, upd, empty)
            self.assertTrue(changed)
            self.assertEqual({e["kind"] for e in doc["entries"]}, {"prices", "monthly"})
            n = len(doc["entries"])
            # the same data on the same day: nothing is added and nothing is replaced
            again, changed = self.run_build(prices, doc, t1 + timedelta(hours=1), upd, empty)
            self.assertFalse(changed)
            self.assertEqual(again["entries"], doc["entries"])
            # the next week: the daily series run to a later day and eia-spot has a new data end
            prices2 = os.path.join(tmp, "prices2")
            os.makedirs(prices2)
            prices_folder(prices2, last="2026-11-24", brent=(99.0, 95.0))
            upd2 = {"sources": {"eia-spot": {"last_success": "2026-12-01T17:50:00Z", "data_to": "2026-11-24", "state": {}}}}
            doc2, changed = self.run_build(prices2, doc, t1 + timedelta(days=7), upd2, empty)
            self.assertTrue(changed)
            kinds = [e["kind"] for e in doc2["entries"][:2]]
            self.assertEqual(set(kinds), {"prices", "sources"})
            self.assertEqual(len(doc2["entries"]), n + 2)  # prices and sources; the monthly series did not move
            self.assertEqual(doc2["entries"][0]["t"] >= doc2["entries"][-1]["t"], True)
            self.assertEqual(len({e["id"] for e in doc2["entries"]}), len(doc2["entries"]))
            self.assertIn("eia-spot", {s["id"] for s in doc2["sources"]})

    def test_feed_is_valid_atom(self):
        doc = {"generated": "2026-11-24T18:00:00Z", "entries": [
            {"id": "2026-11-24-prices", "kind": "prices", "t": "2026-11-24T18:00:00Z", "title": "Price moves & more <week>", "lines": ["A: +1.0% <b>", "B & C"]}]}
        parsed = xml_parse(C.atom(doc))
        self.assertEqual(parsed.documentElement.tagName, "feed")
        self.assertEqual(parsed.getElementsByTagName("entry").length, 1)
        self.assertEqual(parsed.getElementsByTagName("title")[1].firstChild.data, "Price moves & more <week>")
        self.assertIn("<b>", parsed.getElementsByTagName("content")[0].firstChild.data)

    def test_the_published_feed_is_valid_xml(self):
        path = os.path.join(ROOT, "web", "public", "changes.atom")
        if not os.path.exists(path):
            self.skipTest("no feed yet")
        parsed = xml.dom.minidom.parse(path)
        self.assertEqual(parsed.documentElement.getAttribute("xmlns"), "http://www.w3.org/2005/Atom")
        changes = json.load(open(os.path.join(ROOT, "data", "_status", "changes.json")))
        self.assertEqual(parsed.getElementsByTagName("entry").length, len(changes["entries"]))
        self.assertNotIn("last_error", json.dumps(changes))


def xml_parse(text):
    return xml.dom.minidom.parseString(text.encode("utf-8"))


class Calendar(unittest.TestCase):
    def test_cron_forms(self):
        self.assertEqual(C.parse_cron("17 19 * * 3")["text"], "every Wednesday at 19:17 UTC")
        self.assertEqual(C.parse_cron("17 22 15 * *")["text"], "the 15th of each month at 22:17 UTC")
        self.assertEqual(C.parse_cron("0 */4 * * *"), None)

    def test_jobs_are_read_from_the_workflows_and_cover_every_scheduled_source(self):
        jobs = C.jobs()
        self.assertEqual({j["id"] for j in jobs}, set(C.JOBS))
        registry = {s["id"] for s in json.load(open(os.path.join(ROOT, "data", "sources.json")))}
        for j in jobs:
            self.assertTrue(j["runs"], j["id"])
            for s in j["sources"]:
                self.assertIn(s, registry)
        # the job names are the workflow names
        with open(os.path.join(ROOT, ".github", "workflows", "update-portwatch.yml")) as fh:
            self.assertIn("name: " + next(j for j in jobs if j["id"] == "update-portwatch")["name"], fh.read())

    def test_every_scheduled_workflow_runs_the_digest_and_commits_the_feed(self):
        for name in ("update-prices", "update-portwatch", "update-annual"):
            with open(os.path.join(ROOT, ".github", "workflows", name + ".yml")) as fh:
                text = fh.read()
            self.assertIn("python pipeline/common/changes.py", text, name)
            self.assertIn("web/public/changes.atom", text, name)


if __name__ == "__main__":
    unittest.main()
