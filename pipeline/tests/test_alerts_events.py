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
from datetime import date, timedelta

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("", "freight"):
    p = os.path.join(ROOT, "pipeline", sub) if sub else os.path.join(ROOT, "pipeline")
    if p not in sys.path:
        sys.path.insert(0, p)

import build_alerts as BA  # noqa: E402
import build_portwatch as BW  # noqa: E402
import fetch_portwatch as FP  # noqa: E402

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
            hand = {"id": "x", "title": "t", "since": "2026-01", "text": "x", "event": "e", "chokepoints": ["a", "b"], "reviewed": "2026-11-23"}
            out = BA.build_alert(hand, {"e": {"src": "https://example.org"}}, {c["id"]: c for c in chk}, {"groups": {}, "chokepoints": {}, "y": 2024}, tmp)
            self.assertEqual(out["measures"][0]["gap2023"], -30.0)  # a alone would be medium
            self.assertEqual(out["measures"][1]["gap2023"], -60.0)
            self.assertEqual(out["severity"], "high")  # b, 60% below, decides

    def test_override_needs_a_reason(self):
        hand = {"id": "x", "title": "t", "since": "2026-01", "text": "x", "event": "e", "chokepoints": ["a"], "reviewed": "2026-11-23",
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
            self.assertRegex(a["reviewed"], r"^\d{4}-\d{2}-\d{2}$")
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


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, "pipeline", "freight", "events.json")), "no events file")
class EventLinks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = load(ROOT, "pipeline", "freight", "events.json")
        cls.commodities = {c["id"] for c in load(ROOT, "data", "commodities", "index.json")}
        cls.countries = {c["c"] for c in load(ROOT, "data", "countries", "index.json")}
        cls.assets = set()
        for f in glob.glob(os.path.join(ROOT, "data", "infrastructure", "*.geojson")):
            cls.assets |= {x["properties"]["id"] for x in load(f)["features"]}

    def test_every_link_is_an_id_of_the_atlas(self):
        for e in self.events:
            for key, known in (("commodities", self.commodities), ("countries", self.countries), ("assets", self.assets)):
                for v in e.get(key, []):
                    self.assertIn(v, known, (e["id"], key))
                self.assertEqual(len(e.get(key, [])), len(set(e.get(key, []))), (e["id"], key))

    def test_the_links_follow_the_text(self):
        """No guess: every link is backed by a word of the event's own text (or its source address)."""
        words = {
            "crude-oil": ("crude", "oil"), "lng": ("lng",), "lpg": ("lpg",), "thermal-coal": ("coal",), "met-coal": ("coking", "coal"),
            "natural-gas": ("gas",), "refined-products": ("product", "gasoline", "diesel", "fuel oil"), "iron-ore": ("iron ore",),
            "nickel": ("nickel",), "bauxite": ("bauxite",), "tin": ("tin",), "cobalt": ("cobalt",), "wheat": ("wheat",), "corn": ("corn",),
            "soybeans": ("soybean",),
        }
        for e in self.events:
            text = " ".join([e["title"], e["summary"], e.get("impact", "")]).lower()
            for k in e.get("commodities", []):
                self.assertTrue(any(w in text for w in words[k]), (e["id"], k))

    def test_an_event_without_a_commodity_in_its_text_has_none(self):
        for e in self.events:
            if e["id"] in ("ever-given-2021", "red-sea-houthi-2023", "eu-ets-shipping-2024", "gaza-ceasefire-2025", "suez-return-2026"):
                self.assertNotIn("commodities", e)

    def test_published_events_are_the_sorted_file(self):
        self.assertEqual(load(FREIGHT, "events.json"), sorted(self.events, key=lambda e: e["date"]))


if __name__ == "__main__":
    unittest.main()
