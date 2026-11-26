"""Tests of the "what changed" digest (pipeline/common/changes.py): price moves, passage moves, the sources that published,
the feed entries and the Atom file, and the calendar read from the workflows.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_changes.py"
"""
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock
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

    def test_the_feed_names_the_source_the_eia_gives_for_its_spot_prices(self):
        with tempfile.TemporaryDirectory() as tmp:
            prices_folder(tmp)
            weekly, monthly = C.price_moves(tmp)
            lines = C.lines_prices(weekly, "week")
            self.assertTrue(lines and all(l.endswith("; EIA, source: Refinitiv)") for l in lines), lines)
            self.assertFalse(any("eia-spot" in l for l in lines))
            # the monthly sources are named in words, not by their registry id
            m = C.lines_prices(monthly, "month")
            self.assertTrue(m and all(l.endswith("; World Bank)") for l in m), m)
            self.assertFalse(any("wb-pink" in l for l in m))
            # a source without a word of its own is named by its id
            self.assertTrue(C.lines_prices({"moves": [{"name": "N", "to": "2026-10", "pct": 1.0, "v0": 1, "v1": 2, "unit": "USD", "s": "x-id"}]}, "month")[0].endswith("; x-id)"))
            # every source of the weekly job that prices come from has a word the site uses
            with open(os.path.join(ROOT, "web", "src", "components", "PriceBoard.tsx"), encoding="utf-8") as fh:
                board = fh.read()
            for sid, word in (("wb-pink", "World Bank"), ("bls", "BLS"), ("dallasfed", "Dallas Fed"), ("nyfed", "New York Fed")):
                self.assertEqual(C.SOURCE_WORDS[sid], word)
                self.assertIn(f"{sid}: {{ by: '{word}'" if sid.isidentifier() else f"'{sid}': {{ by: '{word}'", board)

    def test_a_series_without_a_quote_a_week_before_is_left_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "index", [{"id": "n-d", "name": "N", "k": "k", "unit": "USD", "freq": "D", "s": "s", "start": "x", "end": "x"}])
            write(tmp, "n-d", {"id": "n-d", "freq": "D", "d": [day("2026-11-15"), day("2026-11-17")], "v": [1, 2]})
            self.assertEqual(C.price_moves(tmp)[0]["moves"], [])


    def test_a_deviation_from_a_trend_or_an_average_has_no_move_in_percent(self):
        """The price board gives no change for a series whose unit says deviation (it crosses zero): the digest lists none either."""
        with tempfile.TemporaryDirectory() as tmp:
            prices_folder(tmp)
            with open(os.path.join(tmp, "index.json")) as fh:
                idx = json.load(fh)
            d1 = day("2026-11-17")
            write(tmp, "dev-d", {"id": "dev-d", "freq": "D", "d": [d1 - 7, d1], "v": [10.0, 30.0]})
            idx.append({"id": "dev-d", "name": "DEV-D", "k": "k", "unit": "% deviation from trend", "freq": "D", "s": "eia-spot", "start": "2020-01", "end": "2026-11-17"})
            write(tmp, "dev-m", {"id": "dev-m", "freq": "M", "start": "2026-01", "v": [1, 2, 3, 4, 5, 6, 7, 8, 9, 40]})
            idx.append({"id": "dev-m", "name": "DEV-M", "k": "k", "unit": "standard deviations from average", "freq": "M", "s": "wb-pink", "start": "2026-01", "end": "2026-10"})
            write(tmp, "index", idx)
            weekly, monthly = C.price_moves(tmp)
            self.assertEqual([m["id"] for m in weekly["moves"]], ["a-d", "b-d"])
            self.assertEqual([m["id"] for m in monthly["moves"]], ["m-m"])
            self.assertEqual((weekly["refused"], monthly["refused"]), ([], []))
            # the same two series with another unit are moves, and the largest
            for row in idx:
                row["unit"] = "USD" if row["id"].startswith("dev-") else row["unit"]
            write(tmp, "index", idx)
            weekly, monthly = C.price_moves(tmp)
            self.assertEqual([m["id"] for m in weekly["moves"]][0], "dev-d")
            self.assertEqual([m["id"] for m in monthly["moves"]][0], "dev-m")

    def test_the_real_files_list_no_deviation_and_the_other_moves_are_unchanged(self):
        prices = os.path.join(ROOT, "data", "prices")
        with open(os.path.join(prices, "index.json")) as fh:
            idx = json.load(fh)
        deviations = {m["id"] for m in idx if "deviation" in m["unit"].lower() and m["freq"] in ("D", "M")}
        self.assertIn("igrea-m", deviations)         # the Dallas Fed index of global real economic activity, in % deviation from trend
        with tempfile.TemporaryDirectory() as tmp:
            for m in idx:                            # a copy of the folder whose deviations are given another unit: what the digest listed before
                os.symlink(os.path.join(prices, m["id"] + ".json"), os.path.join(tmp, m["id"] + ".json"))
            write(tmp, "index", [{**m, "unit": "index" if m["id"] in deviations else m["unit"]} for m in idx])
            old_top = C.TOP
            C.TOP = 10_000
            try:
                before = C.price_moves(tmp)
                now = C.price_moves(prices)
            finally:
                C.TOP = old_top
        for was, is_ in zip(before, now):
            self.assertEqual([m["id"] for m in is_["moves"]], [m["id"] for m in was["moves"] if m["id"] not in deviations])
            self.assertEqual(is_["moves"], [m for m in was["moves"] if m["id"] not in deviations])
            self.assertEqual(is_["refused"], [r for r in was["refused"] if r["id"] not in deviations])
        self.assertTrue({m["id"] for block in before for m in block["moves"]} & deviations, "the folder before the rule lists a deviation: the test would pass on nothing")
        self.assertFalse({m["id"] for block in now for m in block["moves"] + block["refused"]} & deviations)


class RefusedMoves(unittest.TestCase):
    def test_a_move_beyond_the_bound_is_refused_and_listed_not_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            prices_folder(tmp, brent=(90.0, 90.0 * C.MAX_RATIO * 1.01), other=(10.0, 10.0 / C.MAX_RATIO / 1.01))
            weekly, _ = C.price_moves(tmp)
            self.assertEqual(weekly["moves"], [])
            self.assertEqual([r["id"] for r in weekly["refused"]], ["a-d", "b-d"])
            self.assertIn("beyond a factor", weekly["refused"][0]["why"])

    def test_the_bound_itself_is_allowed_and_a_real_large_move_is_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            prices_folder(tmp, brent=(90.0, 90.0 * 1.7), other=(10.0, 10.0 * C.MAX_RATIO))  # +70% (Brent in March 2026); exactly at the bound
            weekly, _ = C.price_moves(tmp)
            self.assertEqual([m["id"] for m in weekly["moves"]], ["b-d", "a-d"])
            self.assertEqual(weekly["refused"], [])

    def test_a_series_that_repeats_another_under_another_name_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            prices_folder(tmp)
            idx = json.load(open(os.path.join(tmp, "index.json")))
            # a copy of the monthly series under another name and unit (a duplicated column), and an honest twin with the same name and unit
            write(tmp, "m2-m", {"id": "m2-m", "freq": "M", "start": "2026-01", "v": [1, 2, 3, 4, 5, 6, 7, 8, 9, 12]})
            idx.append({"id": "m2-m", "name": "Another index", "k": "k", "unit": "index (2010 = 100)", "freq": "M", "s": "wb-pink", "start": "2026-01", "end": "2026-10"})
            write(tmp, "index", idx)
            _, monthly = C.price_moves(tmp)
            self.assertEqual(monthly["moves"], [])
            self.assertEqual([r["id"] for r in monthly["refused"]], ["m-m", "m2-m"])
            self.assertIn("same two figures as m2-m", monthly["refused"][0]["why"])

    def test_the_status_of_the_job_says_what_was_refused(self):
        calls = []

        class Status:
            @staticmethod
            def record_success(source, records=None, data_to=None, note="updated", state=None):
                calls.append((source, note, state))

            @staticmethod
            def record_failure(*a, **k):
                raise AssertionError("failed")

        with tempfile.TemporaryDirectory() as tmp:
            saved = (C.status, C.CHANGES, C.FEED, C.DATA, C.build)
            prices = os.path.join(tmp, "prices")
            os.makedirs(prices)
            prices_folder(prices, brent=(90.0, 900.0))
            try:
                C.status, C.CHANGES, C.FEED = Status, os.path.join(tmp, "changes.json"), os.path.join(tmp, "changes.atom")
                orig = saved[4]
                C.build = lambda previous=None: orig(prices_dir=prices, series_dir=tmp, previous=previous, updates={"sources": {}}, registry=[])
                C.main()
            finally:
                C.status, C.CHANGES, C.FEED, C.DATA, C.build = saved
            self.assertEqual(calls[0][0], "build-changes")
            self.assertIn("refused", calls[0][1])
            self.assertEqual([r["id"] for r in calls[0][2]["refused"]], ["a-d"])
            doc = json.load(open(os.path.join(tmp, "changes.json")))
            self.assertNotIn("a-d", json.dumps(doc["entries"]))  # not published in the feed either


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

    def test_two_runs_on_one_day_keep_the_sources_of_the_first(self):
        """The PortWatch job (Wednesday 19:17) and the prices job (21:43) run on the same UTC day."""
        reg = [{"id": "portwatch", "name": "IMF PortWatch"}, {"id": "eia-spot", "name": "EIA spot"}]
        with tempfile.TemporaryDirectory() as tmp:
            prices = os.path.join(tmp, "prices")
            os.makedirs(prices)
            prices_folder(prices)
            empty = os.path.join(tmp, "none")
            os.makedirs(empty)

            def entry(to, at):
                return {"last_success": at, "data_to": to, "state": {}}

            quiet = {"sources": {"portwatch": entry("2026-11-08", "2026-11-18T19:20:00Z"), "eia-spot": entry("2026-11-10", "2026-11-18T21:50:00Z")}}
            base, _ = C.build(prices_dir=prices, series_dir=empty, now=datetime(2026, 11, 18, 22, 0, tzinfo=timezone.utc), previous={}, updates=quiet, registry=reg)
            day1 = datetime(2026, 11, 25, 19, 30, tzinfo=timezone.utc)
            run1 = {"sources": {"portwatch": entry("2026-11-22", "2026-11-25T19:20:00Z"), "eia-spot": entry("2026-11-10", "2026-11-18T21:50:00Z")}}
            doc1, _ = C.build(prices_dir=prices, series_dir=empty, now=day1, previous=base, updates=run1, registry=reg)
            self.assertEqual([i["id"] for i in doc1["sources"]], ["portwatch"])
            run2 = {"sources": {"portwatch": entry("2026-11-22", "2026-11-25T19:20:00Z"), "eia-spot": entry("2026-11-24", "2026-11-25T21:50:00Z")}}
            doc2, _ = C.build(prices_dir=prices, series_dir=empty, now=day1 + timedelta(hours=2, minutes=15), previous=doc1, updates=run2, registry=reg)
            self.assertEqual(sorted(i["id"] for i in doc2["sources"]), ["eia-spot", "portwatch"])  # the first run's source is still there
            entry_ = next(e for e in doc2["entries"] if e["id"] == "2026-11-25-sources")
            self.assertEqual(len(entry_["lines"]), 2)
            self.assertTrue(any("IMF PortWatch" in l for l in entry_["lines"]) and any("EIA spot" in l for l in entry_["lines"]))
            # a run on the next day does not carry yesterday's sources over
            run3 = {"sources": {"portwatch": entry("2026-11-29", "2026-12-02T19:20:00Z"), "eia-spot": entry("2026-11-24", "2026-11-25T21:50:00Z")}}
            doc3, _ = C.build(prices_dir=prices, series_dir=empty, now=day1 + timedelta(days=7), previous=doc2, updates=run3, registry=reg)
            self.assertEqual([i["id"] for i in doc3["sources"]], ["portwatch"])

    def test_a_line_carried_over_is_written_with_the_words_of_its_source(self):
        """An entry stored with the id of its source ("; eia-spot)") comes out of a rebuild with the words, in the digest and in the feed."""
        with tempfile.TemporaryDirectory() as tmp:
            prices = os.path.join(tmp, "prices")
            os.makedirs(prices)
            prices_folder(prices)
            empty = os.path.join(tmp, "none")
            os.makedirs(empty)
            old = {"generated": "2026-11-18T22:00:00Z", "seen": {"weekly": "2026-11-17", "monthly": "2026-10", "passages": None, "sources": {}}, "entries": [
                {"id": "2026-11-18-prices", "kind": "prices", "t": "2026-11-18T22:00:00Z", "title": "Price moves, week to 17 Nov 2026",
                 "lines": ["Brent: +3.1% in the week to 17 Nov 2026 (90.16 to 92.94 USD/bbl; eia-spot)", "Copper: -1.0% in the week to 17 Nov 2026 (5 to 4.95 USD/t; x-id)"]},
                {"id": "2026-11-18-monthly", "kind": "monthly", "t": "2026-11-18T22:00:00Z", "title": "Monthly prices for Oct 2026",
                 "lines": ["Pink: +1.0% in Oct 2026 (1 to 1.01 USD; wb-pink)", "Index: +2.0% in Oct 2026 (1 to 1.02 USD; EIA, source: Refinitiv)"]},
                {"id": "2026-11-18-passages", "kind": "passages", "t": "2026-11-18T22:00:00Z", "title": "Chokepoint traffic to 15 Nov 2026",
                 "lines": ["Suez Canal: 40.0 vessels a day in the last week, +5% on the 4 weeks before and +2% on the 365 days before (IMF PortWatch, to 15 Nov 2026)"]}]}
            now = datetime(2026, 11, 25, 18, 0, tzinfo=timezone.utc)
            doc, _ = C.build(prices_dir=prices, series_dir=empty, now=now, previous=old, updates={"sources": {}}, registry=[])
            lines = {e["id"]: e["lines"] for e in doc["entries"]}
            self.assertEqual(lines["2026-11-18-prices"], ["Brent: +3.1% in the week to 17 Nov 2026 (90.16 to 92.94 USD/bbl; EIA, source: Refinitiv)",
                                                          "Copper: -1.0% in the week to 17 Nov 2026 (5 to 4.95 USD/t; x-id)"])     # a source without words keeps its id
            self.assertEqual(lines["2026-11-18-monthly"], ["Pink: +1.0% in Oct 2026 (1 to 1.01 USD; World Bank)",
                                                           "Index: +2.0% in Oct 2026 (1 to 1.02 USD; EIA, source: Refinitiv)"])    # a line already in words is unchanged
            self.assertEqual(lines["2026-11-18-passages"], old["entries"][2]["lines"])
            feed = C.atom(doc)
            self.assertIn("; EIA, source: Refinitiv)", feed)
            self.assertIn("; World Bank)", feed)
            self.assertNotIn("eia-spot)", feed)
            self.assertNotIn("wb-pink)", feed)
            # a second pass changes nothing
            again, _ = C.build(prices_dir=prices, series_dir=empty, now=now, previous=doc, updates={"sources": {}}, registry=[])
            self.assertEqual(again["entries"], doc["entries"])
            self.assertEqual(C.atom(again), feed)
            for sid, word in C.SOURCE_WORDS.items():
                self.assertEqual(C.reword(f"N: +1.0% in Oct 2026 (1 to 2 USD; {sid})"), f"N: +1.0% in Oct 2026 (1 to 2 USD; {word})")
                self.assertEqual(C.reword(f"N: +1.0% in Oct 2026 (1 to 2 USD; {word})"), f"N: +1.0% in Oct 2026 (1 to 2 USD; {word})")

    def test_a_source_renamed_in_the_registry_is_renamed_where_its_name_was_stored(self):
        """The digest stores the name of a source with the date it published, and a line of the feed starts with it: both follow a
        new name of the registry at the next run, a source the registry no longer holds keeps its stored name, and no other line moves."""
        with tempfile.TemporaryDirectory() as tmp:
            prices = os.path.join(tmp, "prices")
            os.makedirs(prices)
            prices_folder(prices)
            empty = os.path.join(tmp, "none")
            os.makedirs(empty)
            old = {"generated": "2026-11-25T22:00:00Z", "sourcesOn": "2026-11-25",
                   "seen": {"weekly": "2026-11-17", "monthly": "2026-10", "passages": None, "sources": {}},
                   "sources": [{"id": "dallasfed", "name": "Index of activity", "data_to": "2026-10", "t": "2026-11-25T20:38:17Z"},
                               {"id": "gone", "name": "A source of before", "data_to": None, "t": "2026-11-25T20:38:17Z"},
                               {"id": "faostat-wna", "name": "FAO and WNA of before", "data_to": "2024", "t": "2026-11-25T20:38:17Z"}],
                   "entries": [
                       {"id": "2026-11-25-sources", "kind": "sources", "t": "2026-11-25T22:00:00Z", "title": "Sources that published new data",
                        "lines": ["Index of activity: data to Oct 2026, checked on 25 Nov 2026", "A source of before: new release, checked on 25 Nov 2026",
                                  "FAO and WNA of before: data to 2024, checked on 25 Nov 2026"]},
                       {"id": "2026-11-18-prices", "kind": "prices", "t": "2026-11-18T22:00:00Z", "title": "Price moves, week to 17 Nov 2026",
                        "lines": ["Index of activity: +3.1% in the week to 17 Nov 2026 (90.16 to 92.94 USD/bbl; x-id)"]}]}
            reg = [{"id": "dallasfed", "name": "The Bank, index of activity"}, {"id": "faostat", "name": "FAO"}, {"id": "wna", "name": "WNA"}]
            now = datetime(2026, 11, 26, 3, 0, tzinfo=timezone.utc)
            doc, added = C.build(prices_dir=prices, series_dir=empty, now=now, previous=old, updates={"sources": {}}, registry=reg)
            self.assertFalse(added)                                     # a new name is not news: no entry is added
            self.assertEqual([i["name"] for i in doc["sources"]], ["The Bank, index of activity", "A source of before", "FAO and WNA"])
            lines = {e["id"]: e["lines"] for e in doc["entries"]}
            self.assertEqual(lines["2026-11-25-sources"], ["The Bank, index of activity: data to Oct 2026, checked on 25 Nov 2026",
                                                           "A source of before: new release, checked on 25 Nov 2026",
                                                           "FAO and WNA: data to 2024, checked on 25 Nov 2026"])
            self.assertEqual(lines["2026-11-18-prices"], old["entries"][1]["lines"])   # a line of another kind is not a source's line
            self.assertEqual(doc["generated"], old["generated"])
            feed = C.atom(doc)
            self.assertIn("The Bank, index of activity: data to Oct 2026", feed)
            self.assertNotIn("\nIndex of activity: data to", feed)
            again, _ = C.build(prices_dir=prices, series_dir=empty, now=now, previous=doc, updates={"sources": {}}, registry=reg)
            self.assertEqual({k: v for k, v in again.items()}, {k: v for k, v in doc.items()})   # a second pass changes nothing
            # without the registry (or with an empty one) nothing is renamed
            bare, _ = C.build(prices_dir=prices, series_dir=empty, now=now, previous=old, updates={"sources": {}}, registry=[])
            self.assertEqual(bare["sources"], old["sources"])
            self.assertEqual(bare["entries"][0]["lines"], old["entries"][0]["lines"])

    def test_a_source_renamed_while_it_is_not_in_the_last_block_keeps_its_old_name_in_the_older_entries(self):
        """The limit of the rule, as it is: the names followed are those of the sources of the previous file's block, the last run that reported
        sources. A line of an older "sources" entry about a source that is not in that block keeps the name it was written with, whatever the
        registry says now; it leaves the feed, which keeps KEEP entries, as newer ones arrive."""
        with tempfile.TemporaryDirectory() as tmp:
            prices = os.path.join(tmp, "prices")
            os.makedirs(prices)
            prices_folder(prices)
            empty = os.path.join(tmp, "none")
            os.makedirs(empty)
            old = {"generated": "2026-11-25T22:00:00Z", "sourcesOn": "2026-11-25",
                   "seen": {"weekly": "2026-11-17", "monthly": "2026-10", "passages": None, "sources": {}},
                   # the last run reported one source: the other one was only in the run of the week before
                   "sources": [{"id": "dallasfed", "name": "Index of activity", "data_to": "2026-10", "t": "2026-11-25T20:38:17Z"}],
                   "entries": [
                       {"id": "2026-11-25-sources", "kind": "sources", "t": "2026-11-25T22:00:00Z", "title": "Sources that published new data",
                        "lines": ["Index of activity: data to Oct 2026, checked on 25 Nov 2026"]},
                       {"id": "2026-11-18-sources", "kind": "sources", "t": "2026-11-18T22:00:00Z", "title": "Sources that published new data",
                        "lines": ["Index of activity: data to Sep 2026, checked on 18 Nov 2026", "Old name of the bank: new release, checked on 18 Nov 2026"]}]}
            # the registry has a new name for both sources
            reg = [{"id": "dallasfed", "name": "The Bank, index of activity"}, {"id": "bls", "name": "New name of the bank"}]
            now = datetime(2026, 11, 26, 3, 0, tzinfo=timezone.utc)
            doc, _ = C.build(prices_dir=prices, series_dir=empty, now=now, previous=old, updates={"sources": {}}, registry=reg)
            lines = {e["id"]: e["lines"] for e in doc["entries"]}
            self.assertEqual(lines["2026-11-25-sources"], ["The Bank, index of activity: data to Oct 2026, checked on 25 Nov 2026"])
            # the source of the last block is followed in every entry that holds its old name, the one that is not in the block is not
            self.assertEqual(lines["2026-11-18-sources"], ["The Bank, index of activity: data to Sep 2026, checked on 18 Nov 2026",
                                                           "Old name of the bank: new release, checked on 18 Nov 2026"])
            self.assertEqual(C.renamed_names(old["sources"], reg), {"Index of activity": "The Bank, index of activity"})
        # what the docstring and the comment of build() say
        doc_of = C.renamed_names.__doc__
        self.assertIn("only for a source that is in that block", doc_of)
        self.assertIn("keeps its old name in the older entries", doc_of)
        with open(os.path.join(ROOT, "pipeline", "common", "changes.py"), encoding="utf-8") as fh:
            self.assertIn("Only\n    # the sources of the previous run's block are followed", fh.read())

    def test_a_former_name_is_followed_in_every_entry_whatever_the_last_block_holds(self):
        """A job that runs between the renaming of a source and the rebuild of the digest moves the source out of the block of the last
        run (it happened on 26 November 2026: the port step reported alone): the names of FORMER_NAMES are followed all the same."""
        with tempfile.TemporaryDirectory() as tmp:
            prices = os.path.join(tmp, "prices")
            os.makedirs(prices)
            prices_folder(prices)
            empty = os.path.join(tmp, "none")
            os.makedirs(empty)
            old = {"generated": "2026-11-26T02:20:00Z", "sourcesOn": "2026-11-26",
                   "seen": {"weekly": "2026-11-17", "monthly": "2026-10", "passages": None, "sources": {}},
                   "sources": [{"id": "ports", "name": "Port calls", "data_to": "2026-11-22", "t": "2026-11-26T02:20:00Z"}],
                   "entries": [
                       {"id": "2026-11-26-sources", "kind": "sources", "t": "2026-11-26T02:20:00Z", "title": "Sources that published new data",
                        "lines": ["Port calls: data to 22 Nov 2026, checked on 26 Nov 2026"]},
                       {"id": "2026-11-25-sources", "kind": "sources", "t": "2026-11-25T22:00:00Z", "title": "Sources that published new data",
                        "lines": ["Name of before: data to Oct 2026, checked on 25 Nov 2026", "Another of before: new release, checked on 25 Nov 2026"]},
                       {"id": "2026-11-25-prices", "kind": "prices", "t": "2026-11-25T21:00:00Z", "title": "Price moves",
                        "lines": ["Name of before: +3.1% in the week to 17 Nov 2026 (90.16 to 92.94 USD/bbl; x-id)"]}]}
            reg = [{"id": "ports", "name": "Port calls"}, {"id": "idx", "name": "The Bank, name of today"}, {"id": "other", "name": "Another of before"}]
            now = datetime(2026, 11, 26, 6, 0, tzinfo=timezone.utc)
            with mock.patch.dict(C.FORMER_NAMES, {"Name of before": "idx", "Never used": "gone", "Another of before": "other"}, clear=True):
                doc, added = C.build(prices_dir=prices, series_dir=empty, now=now, previous=old, updates={"sources": {}}, registry=reg)
                again, _ = C.build(prices_dir=prices, series_dir=empty, now=now, previous=doc, updates={"sources": {}}, registry=reg)
            self.assertFalse(added)
            lines = {e["id"]: e["lines"] for e in doc["entries"]}
            self.assertEqual(lines["2026-11-25-sources"], ["The Bank, name of today: data to Oct 2026, checked on 25 Nov 2026",
                                                           "Another of before: new release, checked on 25 Nov 2026"])   # a name that is still the registry's is left
            self.assertEqual(lines["2026-11-26-sources"], old["entries"][0]["lines"])
            self.assertEqual(lines["2026-11-25-prices"], old["entries"][2]["lines"])                                   # a line of another kind is not a source's line
            self.assertEqual(again, doc)                                                                               # a second pass changes nothing

    def test_the_former_names_are_names_the_registry_no_longer_gives(self):
        with open(os.path.join(ROOT, "data", "sources.json"), encoding="utf-8") as fh:
            names = {s["id"]: s["name"] for s in json.load(fh)}
        for was, sid in C.FORMER_NAMES.items():
            self.assertIn(sid, names, was)
            self.assertNotEqual(names[sid], was, sid)
            self.assertNotIn(was, names.values(), was)      # no other source carries a former name: a line could not be told apart

    def test_every_line_of_the_committed_digest_about_a_source_starts_with_a_name_of_the_registry(self):
        """In every entry, not only the last block: a source renamed in the registry is followed by a rebuild of the digest (and, when a job has
        run in between, by its former name in FORMER_NAMES) before the change is published."""
        with open(os.path.join(ROOT, "data", "sources.json"), encoding="utf-8") as fh:
            names = {s["id"]: s["name"] for s in json.load(fh)}
        with open(os.path.join(ROOT, "data", "_status", "changes.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
        known = set(names.values()) | {" and ".join(names[s] for s in ids) for ids in C.SOURCES_OF.values() if all(s in names for s in ids)}
        for e in doc["entries"]:
            if e["kind"] != "sources":
                continue
            for line in e["lines"]:
                self.assertTrue(any(line.startswith(n + ": ") for n in known), (e["id"], line))
        with open(os.path.join(ROOT, "web", "public", "changes.atom"), encoding="utf-8") as fh:
            feed = fh.read()
        for was in C.FORMER_NAMES:
            self.assertNotIn("\n" + was + ": ", feed)
            self.assertNotIn(">" + was + ": ", feed)

    def test_the_committed_digest_names_its_sources_as_the_registry_does(self):
        """After a source is renamed in the registry the digest is rebuilt (pipeline/common/changes.py) before the change is published."""
        with open(os.path.join(ROOT, "data", "sources.json"), encoding="utf-8") as fh:
            reg = json.load(fh)
        with open(os.path.join(ROOT, "data", "_status", "changes.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertEqual(C.renamed_names(doc.get("sources"), reg), {})
        names = {s["id"]: s["name"] for s in reg}
        for i in doc.get("sources") or []:
            ids = C.SOURCES_OF.get(i["id"], [i["id"]])
            if all(s in names for s in ids):
                want = " and ".join(names[s] for s in ids)
                for e in doc["entries"]:
                    if e["kind"] == "sources" and e["t"][:10] == doc.get("sourcesOn"):
                        self.assertTrue(any(l.startswith(want + ": ") for l in e["lines"]), (i["id"], e["lines"]))

    def test_no_line_of_the_feed_built_from_the_committed_digest_ends_with_the_id_of_a_source_that_has_words(self):
        """The feed is rebuilt from changes.json at the release: whatever ids the committed file holds, the feed it makes has none (nothing is written)."""
        with open(os.path.join(ROOT, "data", "_status", "changes.json"), encoding="utf-8") as fh:
            committed = json.load(fh)
        doc, _ = C.build(previous=committed)
        ids = "|".join(C.SOURCE_WORDS)
        for text in (C.atom(doc), json.dumps(doc["entries"], indent=0)):
            self.assertEqual([l for l in text.splitlines() if re.search(rf"; ({ids})\)\W*$", l)], [])
        self.assertTrue(doc["entries"])

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
