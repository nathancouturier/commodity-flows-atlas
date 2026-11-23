"""Tests of the data-driven alerts (build_alerts.py), the incremental PortWatch update (fetch_portwatch.py and the cache of
build_portwatch.py) and the links of the events (pipeline/freight/events.json).

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_alerts_events.py"
The tests on the published files are skipped when those files are absent.
"""
import glob
import gzip
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("", "freight"):
    p = os.path.join(ROOT, "pipeline", sub) if sub else os.path.join(ROOT, "pipeline")
    if p not in sys.path:
        sys.path.insert(0, p)

import build_alerts as BA  # noqa: E402
import build_portwatch as BW  # noqa: E402
import event_links as EL  # noqa: E402
import fetch_portwatch as FP  # noqa: E402
import restore_portwatch as RP  # noqa: E402

FREIGHT = os.path.join(ROOT, "data", "freight")
HAVE_DATA = all(os.path.exists(os.path.join(FREIGHT, f)) for f in ("chokepoints.json", "chokepoint-lanes.json", "alerts.json"))


def load(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return json.load(fh)


def daily(values, last="2026-11-15"):
    """A daily frame ending on ``last``: n_total = the values (oldest first), capacity = 1e6 tonnes a transit."""
    idx = pd.date_range(end=last, periods=len(values), freq="D")
    return pd.DataFrame({"n_total": values, "capacity": [v * 1e6 for v in values]}, index=idx)


class Severity(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(BA.severity_of(-96.2), "high")
        self.assertEqual(BA.severity_of(-60.0), "high")
        self.assertEqual(BA.severity_of(-59.9), "medium")
        self.assertEqual(BA.severity_of(-25.0), "medium")
        self.assertEqual(BA.severity_of(-24.9), "low")
        self.assertEqual(BA.severity_of(12.0), "low")
        self.assertIsNone(BA.severity_of(None))

    def test_gap_needs_a_reference(self):
        self.assertEqual(BA.gap_pct(50, 100), -50.0)
        self.assertIsNone(BA.gap_pct(50, 0))
        self.assertIsNone(BA.gap_pct(None, 100))

    def test_compare_on_a_fixed_series(self):
        """3 years of 100 transits a day, then 28 days of 4: the gap is -96% against the year earlier and the 2023 average."""
        idx = pd.date_range("2022-12-01", "2026-11-15", freq="D")
        n = pd.Series(100, index=idx)
        n[n.index > pd.Timestamp("2026-11-15") - pd.Timedelta(days=28)] = 4
        day = pd.DataFrame({"n_total": n, "capacity": n * 1e6})
        c = BW.compare(day)
        self.assertEqual(c["to"], "2026-11-15")
        self.assertEqual(c["transits"]["now"], 4 * 28)
        self.assertEqual(c["transits"]["yearAgo"], 100 * 28)
        self.assertEqual(c["transits"]["avg2023"], 100 * 28)
        self.assertEqual(c["mt"]["now"], 112.0)
        self.assertEqual(c["yearAgoTo"], "2025-11-16")  # 364 days back: the same weekdays
        gap = BA.gap_pct(c["transits"]["now"], c["transits"]["avg2023"])
        self.assertEqual(gap, -96.0)
        self.assertEqual(BA.severity_of(gap), "high")

    def test_compare_leaves_a_missing_window_empty(self):
        day = daily([10] * 100)  # no year earlier, no 2023
        c = BW.compare(day)
        self.assertEqual(c["transits"]["now"], 280)
        self.assertIsNone(c["transits"]["yearAgo"])
        self.assertIsNone(c["transits"]["avg2023"])
        short = BW.compare(daily([10] * 20))
        self.assertIsNone(short["transits"]["now"])  # fewer than 28 days: no figure rather than a partial one

    def test_week_against_prior_averages(self):
        day = daily([10] * 400 + [20] * 7)
        c = BW.compare(day)["perDay"]
        self.assertEqual(c["week"], 20.0)
        self.assertEqual(c["prior28"], 10.0)
        self.assertEqual(c["prior365"], 10.0)

    def test_worst_passage_decides(self):
        with tempfile.TemporaryDirectory() as tmp:
            for cid, gap_now in (("a", 70), ("b", 40)):
                doc = {"compare": {"to": "2026-11-15", "days": 28, "yearAgoTo": "2025-11-16", "refYear": 2023,
                                   "transits": {"now": gap_now, "yearAgo": 100, "avg2023": 100}, "mt": {"now": 1, "yearAgo": 2, "avg2023": 2}}}
                json.dump(doc, open(os.path.join(tmp, cid + ".json"), "w"))
            chk = [{"id": "a", "name": "A", "estimates": []}, {"id": "b", "name": "B", "estimates": []}]
            hand = {"id": "x", "title": "t", "since": "2026-01", "text": "x", "event": "e", "chokepoints": ["a", "b"], "checked": "2026-11-23"}
            out = BA.build_alert(hand, {"e": {"src": "https://example.org"}}, {c["id"]: c for c in chk}, {"groups": {}, "chokepoints": {}, "y": 2024}, tmp)
            self.assertEqual(out["measures"][0]["gap2023"], -30.0)  # a alone would be medium
            self.assertEqual(out["measures"][1]["gap2023"], -60.0)
            self.assertEqual(out["severity"], "high")  # b, 60% below, decides

    def test_a_text_without_a_check_carries_no_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            json.dump({"compare": {"to": "2026-11-15", "days": 28, "yearAgoTo": "x", "refYear": 2023, "transits": {"now": 1, "yearAgo": 1, "avg2023": 1},
                                   "mt": {"now": 1, "yearAgo": 1, "avg2023": 1}}}, open(os.path.join(tmp, "a.json"), "w"))
            hand = {"id": "x", "title": "t", "since": "2026-01", "text": "x", "event": "e", "chokepoints": ["a"]}
            out = BA.build_alert(hand, {"e": {"src": "u", "also": [{"label": "L", "url": "https://example.org"}]}}, {"a": {"id": "a", "name": "A"}},
                                 {"groups": {}, "chokepoints": {}, "y": 2024}, tmp)
            self.assertNotIn("checked", out)
            self.assertEqual(out["also"], [{"label": "L", "url": "https://example.org"}])
            hand["checked"] = "2026-11-23"
            self.assertEqual(BA.build_alert(hand, {"e": {"src": "u"}}, {"a": {"id": "a", "name": "A"}}, {"groups": {}, "chokepoints": {}, "y": 2024}, tmp)["checked"], "2026-11-23")

    def test_a_country_with_enough_cargo_is_in_whatever_the_commodity(self):
        lanes = {"groups": {"g": {"k": "k1"}, "h": {"k": "k2"}},
                 "chokepoints": {"a": [["g", "AAA", "BBB", 100.0, 1], ["h", "CCC", "BBB", BA.COUNTRY_MT_MIN, 1], ["h", "DDD", "EEE", BA.COUNTRY_MT_MIN - 0.1, 1],
                                       ["h", "FFF", "GGG", 90.0, 0]],
                         "b": [["g", "AAA", "BBB", 100.0, 1]]}}
        heavy = BA.heavy_countries(lanes, ["a", "b"])
        self.assertEqual([c for c, _ in heavy], ["BBB", "AAA", "CCC"])  # a pair that only may cross is left out; one that crosses both counts once
        self.assertEqual(dict(heavy)["BBB"], 100.0 + BA.COUNTRY_MT_MIN)

    def test_add_countries_appends_to_the_derived_list_with_its_reason(self):
        chk = {"a": {"id": "a", "name": "A", "estimates": []}}
        lanes = {"groups": {"g": {"k": "k1"}}, "chokepoints": {"a": [["g", "AAA", "BBB", 30.0, 1]]}, "y": 2024}
        hand = {"id": "x", "title": "t", "since": "2026-01", "text": "x", "event": "e", "chokepoints": ["a"],
                "override": {"addCountries": ["ZZZ", "AAA"], "reason": "named by the event"}}
        with tempfile.TemporaryDirectory() as tmp:
            json.dump({"compare": {"to": "2026-11-15", "days": 28, "yearAgoTo": "x", "refYear": 2023, "transits": {"now": 1, "yearAgo": 1, "avg2023": 1},
                                   "mt": {"now": 1, "yearAgo": 1, "avg2023": 1}}}, open(os.path.join(tmp, "a.json"), "w"))
            out = BA.build_alert(hand, {"e": {"src": "u"}}, chk, lanes, tmp)
            self.assertEqual(out["countries"], ["AAA", "BBB", "ZZZ"])  # the derived ones first, the added one once
            self.assertEqual(out["override"], {"addCountries": ["ZZZ", "AAA"], "reason": "named by the event"})
            hand["override"].pop("reason")
            with self.assertRaises(ValueError):
                BA.build_alert(hand, {"e": {"src": "u"}}, chk, lanes, tmp)

    def test_override_needs_a_reason(self):
        hand = {"id": "x", "title": "t", "since": "2026-01", "text": "x", "event": "e", "chokepoints": ["a"], "checked": "2026-11-23",
                "override": {"commodities": ["lng"]}}
        with tempfile.TemporaryDirectory() as tmp:
            json.dump({"compare": {"to": "2026-11-15", "days": 28, "yearAgoTo": "x", "refYear": 2023, "transits": {"now": 1, "yearAgo": 1, "avg2023": 1},
                                   "mt": {"now": 1, "yearAgo": 1, "avg2023": 1}}}, open(os.path.join(tmp, "a.json"), "w"))
            with self.assertRaises(ValueError):
                BA.build_alert(hand, {"e": {"src": "u"}}, {"a": {"id": "a", "name": "A"}}, {"groups": {}, "chokepoints": {}, "y": 2024}, tmp)
            hand["override"]["reason"] = "because"
            out = BA.build_alert(hand, {"e": {"src": "u"}}, {"a": {"id": "a", "name": "A"}}, {"groups": {}, "chokepoints": {}, "y": 2024}, tmp)
            self.assertEqual(out["commodities"], ["lng"])
            self.assertEqual(out["override"]["reason"], "because")


@unittest.skipUnless(HAVE_DATA, "the freight files are not built")
class Derived(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chk = {c["id"]: c for c in load(FREIGHT, "chokepoints.json")}
        cls.lanes = load(FREIGHT, "chokepoint-lanes.json")

    def test_hormuz_commodities_and_countries(self):
        ks = [x[0] for x in BA.exposed_commodities(self.chk, ["hormuz"])]
        for k in ("crude-oil", "lng", "lpg", "urea", "refined-products", "phosphate", "aluminium"):
            self.assertIn(k, ks)
        for k in ("wheat", "iron-ore", "thermal-coal"):
            self.assertNotIn(k, ks)
        exp, imp = BA.exposed_countries(self.lanes, ["hormuz"], set(ks))
        for c in ("SAU", "IRQ", "QAT", "ARE", "KWT"):
            self.assertIn(c, exp)
        for c in ("CHN", "IND"):
            self.assertIn(c, imp)

    def test_bab_el_mandeb_commodities_and_countries(self):
        ks = [x[0] for x in BA.exposed_commodities(self.chk, ["bab-el-mandeb"])]
        # the commodities the audit found missing from the hand-written list
        for k in ("phosphate", "potash", "palm-oil", "rice"):
            self.assertIn(k, ks)
        exp, _ = BA.exposed_countries(self.lanes, ["bab-el-mandeb"], set(ks))
        self.assertIn("JOR", exp)  # Jordan: the largest phosphate-rock lane

    def test_a_commodity_needs_the_share_or_the_tonnage(self):
        chk = {"p": {"estimates": [
            {"k": "small", "f": {"v": 2.0}, "mt": [5.0, 5.0]},
            {"k": "share", "f": {"v": 10.0}, "mt": [5.0, 5.0]},
            {"k": "tonnes", "f": {"v": 2.0}, "mt": [50.0, 50.0]},
        ]}}
        self.assertEqual({x[0] for x in BA.exposed_commodities(chk, ["p"])}, {"share", "tonnes"})

    def test_the_countries_of_the_published_alerts(self):
        """The countries the audit found missing (the lanes carry at least COUNTRY_MT_MIN Mt for them) and the two added by hand."""
        alerts = {a["id"]: a for a in load(FREIGHT, "alerts.json")}
        for c in ("JPN", "TWN", "SGP", "IRN"):
            self.assertIn(c, alerts["hormuz-2026"]["countries"], c)
        for c in ("EGY", "KOR", "NLD", "IRQ", "YEM"):
            self.assertIn(c, alerts["red-sea-2023"]["countries"], c)
        self.assertIn("TUR", alerts["black-sea-2026"]["countries"])
        for a in alerts.values():
            for c, _ in BA.heavy_countries(self.lanes, a["chokepoints"]):
                self.assertIn(c, a["countries"], (a["id"], c))
        # what an override adds is explained to the reader
        self.assertIn("crude-irn", alerts["hormuz-2026"]["override"]["reason"])
        self.assertIn("YEM", alerts["red-sea-2023"]["override"]["addCountries"])

    def test_pairs_through_two_passages_count_once(self):
        lanes = {"groups": {"g": {"k": "k1"}}, "chokepoints": {"a": [["g", "AAA", "BBB", 14.0, 1], ["g", "CCC", "DDD", 86.0, 1]],
                                                                "b": [["g", "AAA", "BBB", 14.0, 1], ["g", "EEE", "FFF", 50.0, 0]]}}
        exp, imp = BA.exposed_countries(lanes, ["a", "b"], {"k1"})
        # AAA to BBB is 14 of 100 Mt, below 15% (counted twice it would be 28 of 114 and be listed); a pair that only may cross is left out
        self.assertEqual(exp, ["CCC"])
        self.assertEqual(imp, ["DDD"])

    def test_published_alerts_are_what_the_builder_gives(self):
        hand = load(ROOT, "pipeline", "freight", "alerts.json")
        events = load(ROOT, "pipeline", "freight", "events.json")
        out = BA.build(hand, events, list(self.chk.values()), self.lanes, os.path.join(FREIGHT, "portwatch"))
        self.assertEqual(out, load(FREIGHT, "alerts.json"))
        for a in out:
            self.assertIn(a["severity"], ("low", "medium", "high"))
            self.assertNotIn("reviewed", a)  # only a text read against its source carries a date, and it is called "checked"
            if "checked" in a:
                self.assertRegex(a["checked"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertEqual(a["decidedBy"]["gap"], min(m["gap2023"] for m in a["measures"]))
            for m in a["measures"]:
                self.assertEqual(m["s"], "portwatch")
                self.assertRegex(m["to"], r"^\d{4}-\d{2}-\d{2}$")

    def test_build_freight_no_longer_writes_the_alerts(self):
        with open(os.path.join(ROOT, "pipeline", "freight", "build_freight.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn('"alerts.json"), "w"', src)


class IncrementalFetch(unittest.TestCase):
    def row(self, d, pid="chokepoint1", n=10):
        r = {k: 1 for k in BW.FIELDS}
        r.update({"date": d, "portid": pid, "portname": "Suez Canal", "n_total": n})
        return r

    def test_plan(self):
        today = date(2026, 11, 25)
        self.assertEqual(FP.plan(False, "2026-11-22", "2026-11-15", today), ("full", "1=1"))
        self.assertEqual(FP.plan(True, None, "2026-11-15", today), ("full", "1=1"))
        mode, where = FP.plan(True, "2026-11-22", "2026-11-15", today)
        self.assertEqual(mode, "incremental")
        self.assertEqual(where, "date > '2026-11-01'")  # the last day stored less the overlap
        # a month after the last full download: the whole table again
        self.assertEqual(FP.plan(True, "2026-10-28", "2026-11-15", today)[0], "full")
        self.assertEqual(FP.plan(True, "2026-10-29", "2026-11-15", today)[0], "incremental")

    def test_merge_has_no_duplicate_day_and_the_newer_row_wins(self):
        old = [self.row("2026-11-01", n=1), self.row("2026-11-02", n=2), self.row("2026-11-03", n=3)]
        new = [self.row("2026-11-03", n=33), self.row("2026-11-04", n=4)]
        out = BW.merge_days(old, new)
        keys = [(r["date"], r["portid"]) for r in out]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual([r["n_total"] for r in out], [1, 2, 33, 4])
        self.assertEqual(BW.merge_days(out, new), out)  # merging the same days again changes nothing

    def test_cache_round_trip_is_byte_identical(self):
        rows = [self.row("2025-12-31"), self.row("2026-01-01", pid="chokepoint2"), self.row("2026-01-01")]
        with tempfile.TemporaryDirectory() as tmp:
            BW.write_cache(rows, tmp)
            self.assertEqual(sorted(os.path.basename(p) for p in glob.glob(os.path.join(tmp, "*"))), ["daily_2025.csv.gz", "daily_2026.csv.gz"])
            first = {p: open(p, "rb").read() for p in glob.glob(os.path.join(tmp, "*"))}
            back = BW.read_cache(tmp)
            self.assertEqual(back, BW.merge_days([], rows))
            BW.write_cache(back, tmp)
            self.assertEqual(first, {p: open(p, "rb").read() for p in glob.glob(os.path.join(tmp, "*"))})
            with gzip.open(os.path.join(tmp, "daily_2026.csv.gz"), "rt") as fh:
                self.assertEqual(fh.readline().strip().split(",")[:3], ["date", "portid", "portname"])

    def test_run_downloads_only_the_new_days(self):
        """A full run builds the cache; the next run asks for the days after the last one stored and merges them."""
        ports = [f"chokepoint{i}" for i in range(1, 13)]
        chk = [{"id": f"cp{i}", "portwatch": p} for i, p in enumerate(ports, 1)]
        start = date(2025, 1, 1)
        table = [self.row((start + timedelta(days=i)).isoformat(), pid=p, n=10) for i in range(500) for p in ports]
        asked = []

        def fake_fetch(where):
            asked.append(where)
            if where == "1=1":
                return [dict(r) for r in table]
            since = where.split("'")[1]
            new_day = (start + timedelta(days=500)).isoformat()
            return [{**r, "n_total": 11} for r in table if r["date"] > since] + [self.row(new_day, pid=p, n=12) for p in ports]

        statuses = {}

        class Status:
            @staticmethod
            def get(source):
                return dict(statuses.get(source, {}))

            @staticmethod
            def record_success(source, records=None, data_to=None, note="updated", state=None):
                st = dict((statuses.get(source, {}).get("state")) or {})
                st.update(state or {})
                statuses[source] = {"records": records, "data_to": data_to, "state": st, "last_success": date.today().isoformat() + "T00:00:00Z"}

            @staticmethod
            def record_failure(source, error, previous=None):
                statuses[source] = {**statuses.get(source, {}), "failed": str(error)}

        with tempfile.TemporaryDirectory() as tmp:
            saved = (FP.fetch_rows, FP.status, FP.OUT, FP.RAW, FP.CHK, BW.read_cache.__defaults__, BW.write_cache.__defaults__, BW.update_headlines)
            try:
                json.dump(chk, open(os.path.join(tmp, "chk.json"), "w"))
                cache = os.path.join(tmp, "cache")
                FP.fetch_rows, FP.status, FP.CHK = fake_fetch, Status, os.path.join(tmp, "chk.json")
                FP.OUT, FP.RAW = os.path.join(tmp, "out"), os.path.join(tmp, "no-raw")
                BW.read_cache.__defaults__, BW.write_cache.__defaults__ = (cache,), (cache,)
                BW.update_headlines = lambda *a, **k: 0
                FP.main()
                self.assertEqual(asked, ["1=1"])
                self.assertEqual(statuses["portwatch"]["records"], 500 * 12)
                self.assertEqual(statuses["portwatch"]["state"]["mode"], "full")
                self.assertEqual(len(glob.glob(os.path.join(tmp, "out", "*.json"))), 12)
                FP.main()
                self.assertEqual(len(asked), 2)
                self.assertTrue(asked[1].startswith("date > '"), asked)
                self.assertEqual(statuses["portwatch"]["state"]["mode"], "incremental")
                rows = BW.read_cache(cache)
                self.assertEqual(len(rows), 501 * 12)  # one new day; the revised overlap replaced, not added
                self.assertEqual(len({(r["date"], r["portid"]) for r in rows}), 501 * 12)
                self.assertEqual(rows[-1]["n_total"], 12)
                self.assertEqual(rows[-20]["n_total"], 11)  # a day inside the overlap was revised
                self.assertEqual(rows[0]["n_total"], 10)    # a day before it was kept as stored
                self.assertEqual(statuses["portwatch"]["data_to"], (start + timedelta(days=500)).isoformat())
                doc = json.load(open(os.path.join(tmp, "out", "cp1.json")))
                self.assertEqual(doc["y"], (start + timedelta(days=500)).isoformat())
                self.assertIn("compare", doc)
            finally:
                (FP.fetch_rows, FP.status, FP.OUT, FP.RAW, FP.CHK, BW.read_cache.__defaults__, BW.write_cache.__defaults__, BW.update_headlines) = saved

    def test_a_shrinking_table_is_refused(self):
        statuses = {"portwatch": {"records": 1000, "data_to": "2026-01-01", "state": {"full_refresh": date.today().isoformat()}}}
        rows = [self.row("2026-01-01")]
        with tempfile.TemporaryDirectory() as tmp:
            saved = (FP.fetch_rows, FP.status, BW.read_cache.__defaults__, BW.write_cache.__defaults__)

            class Status:
                @staticmethod
                def get(source):
                    return statuses[source]

                @staticmethod
                def record_success(*a, **k):
                    raise AssertionError("recorded as a success")

                @staticmethod
                def record_failure(source, error, previous=None):
                    statuses[source] = {**statuses[source], "failed": str(error)}

            try:
                BW.write_cache(rows, tmp)
                BW.read_cache.__defaults__, BW.write_cache.__defaults__ = (tmp,), (tmp,)
                FP.fetch_rows, FP.status = lambda where: [self.row("2026-01-02")], Status
                FP.main()
            finally:
                FP.fetch_rows, FP.status, BW.read_cache.__defaults__, BW.write_cache.__defaults__ = saved
            self.assertIn("below 95%", statuses["portwatch"]["failed"])
            self.assertEqual(len(BW.read_cache(tmp)), 1)  # the previous cache is kept


def ev(**kw):
    return {"id": "e", "date": "2026-01", "title": "T", "kind": "conflict", "summary": "", "src": "https://example.org", **kw}


class EventLinkRule(unittest.TestCase):
    """The rule of pipeline/freight/event_links.py on small texts: whole words, no guess."""

    def test_whole_words_only(self):
        self.assertEqual(EL.named_commodities("Shipping of tinplate, gasoline and oil-fired plants"), ["refined-products"])
        self.assertEqual(EL.named_commodities("tin and cobalt"), ["cobalt", "tin"])
        self.assertEqual(EL.named_commodities("a gas turbine"), [])
        self.assertEqual(EL.named_commodities("fuel oil and bunker costs"), ["refined-products"])  # fuel oil is a product, not crude
        self.assertEqual(EL.named_commodities("Brent and crude"), ["crude-oil"])
        self.assertEqual(EL.named_commodities("liquefied natural gas and natural gas"), ["lng", "natural-gas"])
        self.assertEqual(EL.named_commodities("coking coal"), ["met-coal"])
        self.assertEqual(EL.named_commodities("thermal and coking coal"), ["met-coal", "thermal-coal"])
        self.assertEqual(EL.named_commodities("Houthi attacks: many tankers and LNG carriers diverted"), ["lng"])

    def test_an_event_that_names_none_has_none(self):
        self.assertEqual(EL.derive(ev(summary="Container ships queued for days", impact="Hundreds of ships diverted via the Cape")), [])

    def test_the_name_of_a_linked_asset_counts(self):
        self.assertEqual(EL.derive(ev(summary="The terminal shut for months", assets=["freeport-lng"])), ["lng"])

    def test_a_linked_route_or_passage_does_not_name_a_commodity(self):
        self.assertEqual(EL.derive(ev(summary="Traffic fell", routes=["russia-baltic-india-crude"], chokepoints=["hormuz"])), [])

    def test_countries_by_name_and_demonym_but_not_a_sea(self):
        countries = [{"c": "OMN", "name": "Oman"}, {"c": "IND", "name": "India"}, {"c": "BRA", "name": "Brazil"}, {"c": "CHN", "name": "China"}]
        self.assertEqual(EL.named_countries("Tankers in the Gulf of Oman and the Indian Ocean", countries), [])
        self.assertEqual(EL.named_countries("Brazil-China ore flows and Indian refiners", countries), ["BRA", "CHN", "IND"])


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, "pipeline", "freight", "events.json")), "no events file")
class EventLinks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = load(ROOT, "pipeline", "freight", "events.json")
        cls.by_id = {e["id"]: e for e in cls.events}
        cls.commodities = {c["id"] for c in load(ROOT, "data", "commodities", "index.json")}
        cls.countries_index = load(ROOT, "data", "countries", "index.json")
        cls.countries = {c["c"] for c in cls.countries_index}
        cls.assets = set()
        for f in glob.glob(os.path.join(ROOT, "data", "infrastructure", "*.geojson")):
            cls.assets |= {x["properties"]["id"] for x in load(f)["features"]}
        cls.prices = {m["id"]: m["k"] for m in load(ROOT, "data", "prices", "index.json")}

    def test_every_link_is_an_id_of_the_atlas(self):
        for e in self.events:
            for key, known in (("commodities", self.commodities), ("countries", self.countries), ("assets", self.assets)):
                for v in e.get(key, []):
                    self.assertIn(v, known, (e["id"], key))
                self.assertEqual(len(e.get(key, [])), len(set(e.get(key, []))), (e["id"], key))

    def test_the_commodities_are_what_the_rule_gives(self):
        """Every event links to exactly the commodities its own text names (whole words, rule in event_links.py): none is guessed,
        none that the text names is missing."""
        for e in self.events:
            self.assertEqual(sorted(e.get("commodities", [])), EL.derive(e), e["id"])

    def test_the_countries_and_assets_are_named_in_the_text(self):
        for e in self.events:
            names = [w for a in e.get("assets", []) for w in EL.ASSET_WORDS.get(a, [])]
            text = EL.text_of(e, names)
            self.assertEqual(sorted(e.get("countries", [])), EL.named_countries(text, self.countries_index), e["id"])
            self.assertEqual(sorted(e.get("assets", [])), EL.named_assets(text), e["id"])

    def test_the_cases_of_the_review(self):
        # the Black Sea event names tankers and the oil exports of Kazakhstan; the Red Sea event names LNG carriers; the Hormuz event
        # names oil, LNG and petroleum products
        self.assertIn("crude-oil", self.by_id["black-sea-attacks-2026"]["commodities"])
        self.assertIn("lng", self.by_id["red-sea-houthi-2023"]["commodities"])
        self.assertTrue({"crude-oil", "lng", "refined-products"} <= set(self.by_id["iran-war-hormuz-2026"]["commodities"]))
        # a text that names no commodity at all gets none (and the site shows it with every commodity)
        for k in ("gaza-ceasefire-2025", "suez-return-2026", "somali-piracy-2008-2011"):
            self.assertNotIn("commodities", self.by_id[k])

    def test_an_event_alert_pair_takes_the_commodities_of_the_alert(self):
        """What the site does (web/src/lib/events.ts): the event of an alert is shown with the alert's commodities."""
        alerts = load(FREIGHT, "alerts.json")
        for a in alerts:
            self.assertIn(a["event"], self.by_id)
        hormuz = next(a for a in alerts if a["event"] == "iran-war-hormuz-2026")
        self.assertIn("lng", hormuz["commodities"])
        self.assertIn("lng", self.by_id["iran-war-hormuz-2026"]["commodities"])

    def test_price_series_of_an_event_are_series_of_its_commodity(self):
        for e in self.events:
            for k, sid in e.get("series", {}).items():
                self.assertEqual(self.prices.get(sid), k, (e["id"], k, sid))

    def test_only_a_checked_text_carries_a_date_and_every_other_source_is_a_link(self):
        for e in self.events:
            if "checked" in e:
                self.assertRegex(e["checked"], r"^\d{4}-\d{2}-\d{2}$", e["id"])
            for x in e.get("also", []):
                self.assertTrue(x["label"] and x["url"].startswith("https://"), e["id"])
        # the three events that the alerts point to were read against their sources
        for k in ("iran-war-hormuz-2026", "red-sea-houthi-2023", "black-sea-attacks-2026"):
            self.assertEqual(self.by_id[k]["checked"], "2026-11-23")

    def test_published_events_are_the_sorted_file(self):
        self.assertEqual(load(FREIGHT, "events.json"), sorted(self.events, key=lambda e: e["date"]))


class WorkingTable(unittest.TestCase):
    """The daily PortWatch table is a working file kept between runs outside git (restored from the artifact of the workflow)."""

    def test_the_table_is_ignored_by_git(self):
        with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
            self.assertIn("pipeline/cache/portwatch/", fh.read().split())

    def test_the_published_weekly_series_do_not_need_it(self):
        # build_portwatch reads the table only through read_cache / read_pages; with neither the build says so instead of failing
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(BW.read_cache(tmp), [])
            self.assertEqual(BW.read_pages(tmp), [])

    def test_the_newest_unexpired_artifact_is_chosen(self):
        now = datetime(2026, 11, 25, 19, 30, tzinfo=timezone.utc)

        def art(i, made, name="portwatch-daily", expired=False):
            return {"id": i, "name": name, "expired": expired, "created_at": made}

        listing = {"artifacts": [art(5, "2026-11-18T19:40:00Z"), art(4, "2026-11-11T19:40:00Z"), art(9, "2026-11-24T09:00:00Z", name="other"),
                                 art(8, "2026-11-23T09:00:00Z", expired=True)]}
        self.assertEqual(RP.newest_usable(listing, now)["id"], 5)
        self.assertIsNone(RP.newest_usable({"artifacts": [art(1, "2026-10-01T19:40:00Z")]}, now))  # older than the monthly refresh
        self.assertIsNone(RP.newest_usable({"artifacts": []}, now))
        self.assertIsNone(RP.newest_usable({}, now))
        self.assertIsNone(RP.newest_usable({"artifacts": [{"id": 2, "name": "portwatch-daily", "expired": False, "created_at": "garbage"}]}, now))

    def test_a_good_artifact_is_installed_and_a_corrupt_one_is_not(self):
        import zipfile

        rows = [{k: 1 for k in BW.FIELDS} | {"date": f"2026-01-{d:02d}", "portid": f"chokepoint{p}", "portname": "x"} for d in range(1, 29) for p in range(1, 41)]
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            BW.write_cache(rows, src)
            good = os.path.join(tmp, "good.zip")
            with zipfile.ZipFile(good, "w") as z:
                for f in os.listdir(src):
                    z.write(os.path.join(src, f), f)
            dest = os.path.join(tmp, "dest")
            work = os.path.join(tmp, "work")
            os.makedirs(work)
            self.assertEqual(RP.install(good, dest, work), len(rows))
            self.assertEqual(len(BW.read_cache(dest)), len(rows))
            # a corrupt archive (a daily file that is not gzip) leaves the folder as it was
            bad = os.path.join(tmp, "bad.zip")
            with zipfile.ZipFile(bad, "w") as z:
                z.writestr("daily_2026.csv.gz", b"not a gzip file")
            work2 = os.path.join(tmp, "work2")
            os.makedirs(work2)
            with self.assertRaises(ValueError):
                RP.install(bad, dest, work2)
            self.assertEqual(len(BW.read_cache(dest)), len(rows))
            # a table that is far too small is refused as well
            tiny = os.path.join(tmp, "tiny.zip")
            BW.write_cache(rows[:10], os.path.join(tmp, "t"))
            with zipfile.ZipFile(tiny, "w") as z:
                z.write(os.path.join(tmp, "t", "daily_2026.csv.gz"), "daily_2026.csv.gz")
            work3 = os.path.join(tmp, "work3")
            os.makedirs(work3)
            with self.assertRaises(ValueError):
                RP.install(tiny, dest, work3)
            self.assertEqual(len(BW.read_cache(dest)), len(rows))

    def test_restore_exits_quietly_off_github(self):
        saved = os.environ.pop("GITHUB_REPOSITORY", None)
        try:
            RP.main()  # no GITHUB_REPOSITORY: nothing to restore, no exception
        finally:
            if saved is not None:
                os.environ["GITHUB_REPOSITORY"] = saved


class FullRefreshFallback(unittest.TestCase):
    def test_a_failed_monthly_download_falls_back_to_the_incremental_update_and_is_recorded(self):
        ports = [f"chokepoint{i}" for i in range(1, 13)]
        chk = [{"id": f"cp{i}", "portwatch": p} for i, p in enumerate(ports, 1)]
        start = date(2025, 1, 1)

        def row(d, pid, n):
            r = {k: 1 for k in BW.FIELDS}
            r.update({"date": d, "portid": pid, "portname": "x", "n_total": n})
            return r

        stored = [row((start + timedelta(days=i)).isoformat(), p, 10) for i in range(500) for p in ports]
        asked = []

        def fake_fetch(where):
            asked.append(where)
            if where == "1=1":
                raise FP.fetch.FetchError("HTTP 503")
            new_day = (start + timedelta(days=500)).isoformat()
            return [row(new_day, p, 12) for p in ports]

        statuses = {"portwatch": {"records": len(stored), "data_to": (start + timedelta(days=499)).isoformat(),
                                  "state": {"full_refresh": (date.today() - timedelta(days=40)).isoformat()}}}

        class Status:
            @staticmethod
            def get(source):
                return dict(statuses.get(source, {}))

            @staticmethod
            def record_success(source, records=None, data_to=None, note="updated", state=None):
                statuses[source] = {"records": records, "data_to": data_to, "state": dict(state or {}), "note": note}

            @staticmethod
            def record_failure(source, error, previous=None):
                statuses[source] = {**statuses.get(source, {}), "failed": str(error)}

        with tempfile.TemporaryDirectory() as tmp:
            saved = (FP.fetch_rows, FP.status, FP.OUT, FP.RAW, FP.CHK, BW.read_cache.__defaults__, BW.write_cache.__defaults__, BW.update_headlines)
            try:
                json.dump(chk, open(os.path.join(tmp, "chk.json"), "w"))
                cache = os.path.join(tmp, "cache")
                BW.write_cache(stored, cache)
                FP.fetch_rows, FP.status, FP.CHK = fake_fetch, Status, os.path.join(tmp, "chk.json")
                FP.OUT, FP.RAW = os.path.join(tmp, "out"), os.path.join(tmp, "no-raw")
                BW.read_cache.__defaults__, BW.write_cache.__defaults__ = (cache,), (cache,)
                BW.update_headlines = lambda *a, **k: 0
                FP.main()
                self.assertEqual(asked[0], "1=1")  # the monthly full download was tried first
                self.assertTrue(asked[1].startswith("date > '"), asked)  # then the incremental one, in the same run
                st = statuses["portwatch"]
                self.assertNotIn("failed", st)
                self.assertEqual(st["state"]["mode"], "incremental")
                self.assertEqual(st["state"]["full_refresh"], (date.today() - timedelta(days=40)).isoformat())  # still due: tried again next week
                self.assertEqual(st["state"]["full_refresh_failed"]["count"], 1)
                self.assertIn("503", st["state"]["full_refresh_failed"]["error"])
                self.assertIn("failed", st["note"])
                self.assertEqual(st["data_to"], (start + timedelta(days=500)).isoformat())
                self.assertEqual(len(BW.read_cache(cache)), 501 * 12)
            finally:
                (FP.fetch_rows, FP.status, FP.OUT, FP.RAW, FP.CHK, BW.read_cache.__defaults__, BW.write_cache.__defaults__, BW.update_headlines) = saved

    def test_a_truncated_working_table_is_replaced_by_the_whole_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "cache"))
            with open(os.path.join(tmp, "cache", "daily_2026.csv.gz"), "wb") as fh:
                fh.write(b"\x1f\x8b\x08\x00truncated")
            with self.assertRaises(Exception):
                BW.read_cache(os.path.join(tmp, "cache"))  # the reader fails ...
            # ... and fetch_portwatch.main() catches it and plans a full download (the plan of an empty cache)
            self.assertEqual(FP.plan(False, "2026-11-22", None, date(2026, 11, 25)), ("full", "1=1"))


if __name__ == "__main__":
    unittest.main()
