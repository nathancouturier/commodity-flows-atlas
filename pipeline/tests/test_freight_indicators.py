"""The Freight family of the prices (package RT1): the BLS producer price index fetched from the BLS API without a key
and cached, the Dallas Fed and New York Fed indices read from their publishers' files, what the weekly job records
when one of them fails, and the series as written in data/prices.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
"""
import contextlib
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "prices"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import build_prices as P  # noqa: E402
import freight_indicators as FI  # noqa: E402
from common import fetch  # noqa: E402

DATA = os.path.join(ROOT, "data", "prices")


def jload(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def answer(years, base=100.0, prelim=(), annual=True):
    """An answer of the BLS API for the given years (the API lists the newest month first)."""
    data = []
    for y in sorted(years, reverse=True):
        if annual:
            data.append({"year": str(y), "period": "M13", "periodName": "Annual", "value": "999", "footnotes": [{}]})
        for m in range(12, 0, -1):
            fn = [{"code": "P", "text": "preliminary"}] if f"{y}-{m:02d}" in prelim else [{}]
            data.append({"year": str(y), "period": f"M{m:02d}", "periodName": "", "value": f"{base + y + m / 100:.3f}", "footnotes": fn})
    return {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"seriesID": FI.BLS_SERIES, "data": data}]}}


REFUSED = {"status": "REQUEST_NOT_PROCESSED", "message": ["Request could not be serviced, as the daily threshold for total number of requests allocated to the user with registration key  has been reached."], "Results": {}}


class BlsAnswer(unittest.TestCase):
    def test_monthly_values_and_preliminary_months_the_annual_average_left_out(self):
        obs, prelim = FI.parse_bls(answer([2025, 2026], prelim={"2026-10"}))
        self.assertEqual(len(obs), 24)
        self.assertNotIn("2026-13", obs)
        self.assertEqual(obs["2026-10"], 100.0 + 2026 + 0.10)
        self.assertEqual(prelim, ["2026-10"])

    def test_a_refused_request_says_why(self):
        with self.assertRaises(ValueError) as cm:
            FI.parse_bls(REFUSED)
        self.assertIn("daily threshold", str(cm.exception))

    def test_history_windows_are_ten_years_at_most(self):
        self.assertEqual(FI.history_windows([], 1988, 2023), [(1988, 1997), (1998, 2007), (2008, 2017), (2018, 2023)])
        self.assertEqual(FI.history_windows(range(1988, 2010), 1988, 2023), [(2010, 2019), (2020, 2023)])
        self.assertEqual(FI.history_windows(range(1988, 2024), 1988, 2023), [])


class BlsCache(unittest.TestCase):
    """The cache starts from the values already published (seed) and is replaced year by year by the BLS's answers."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        seed = os.path.join(self.dir, "seed.json")
        with open(seed, "w") as f:
            json.dump({"id": "freight-ppi-m", "freq": "M", "start": "1988-06", "v": [100.0] + [1.0] * (2026 * 12 + 9 - (1988 * 12 + 5))}, f)
        FI.seed_bls_cache(seed, "values of the previous release", cache_dir=self.dir)
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.dir)

    def run_fetch(self, request):
        def req(series, a, b):
            self.calls.append((a, b))
            return request(a, b)

        with open(os.devnull, "w") as dn, contextlib.redirect_stdout(dn):
            return FI.fetch_bls(cache_dir=self.dir, today=date(2026, 11, 23), request=req)

    def test_the_current_window_first_then_three_older_ones(self):
        info, err, changed = self.run_fetch(lambda a, b: answer(range(max(a, 1988), b + 1)))
        self.assertIsNone(err)
        self.assertTrue(changed)
        self.assertEqual(self.calls, [(2024, 2026), (1988, 1997), (1998, 2007), (2008, 2017)])
        doc = FI.load_bls_cache(cache_dir=self.dir)
        self.assertEqual(doc["obs"]["2008-05"], 100.0 + 2008 + 0.05)  # a seeded value replaced by the BLS's
        self.assertEqual(doc["bls_years"], list(range(1988, 2018)) + [2024, 2025, 2026])
        self.assertTrue(doc["seed"])
        self.assertIn("older years still to fetch: 2018-2023", info["note"])
        # the next week: the last older window, then the seed is gone
        self.calls = []
        info, err, _ = self.run_fetch(lambda a, b: answer(range(a, b + 1)))
        self.assertEqual(self.calls, [(2024, 2026), (2018, 2023)])
        doc = FI.load_bls_cache(cache_dir=self.dir)
        self.assertIsNone(doc["seed"])
        self.assertEqual(info["note"], "")

    def test_a_refused_current_window_asks_for_nothing_else_and_keeps_the_cache(self):
        before = FI.load_bls_cache(cache_dir=self.dir)
        info, err, changed = self.run_fetch(lambda a, b: REFUSED)
        self.assertEqual(self.calls, [(2024, 2026)])
        self.assertIn("daily threshold", err)
        self.assertFalse(changed)
        self.assertEqual(FI.load_bls_cache(cache_dir=self.dir), before)
        self.assertEqual(info["data_to"], "2026-10")

    def test_a_network_failure_is_a_refusal_too(self):
        def down(a, b):
            raise fetch.FetchError("ConnectionError after 2 attempts (api.bls.gov)")

        info, err, changed = self.run_fetch(down)
        self.assertIn("ConnectionError", err)
        self.assertFalse(changed)

    def test_an_answer_that_ignores_the_years_asked_for_is_not_taken_for_history(self):
        # the API returns the last three years whatever was asked: the current window is fine, the older ones are not
        info, err, changed = self.run_fetch(lambda a, b: answer([2024, 2025, 2026]))
        self.assertIsNone(err)
        doc = FI.load_bls_cache(cache_dir=self.dir)
        self.assertEqual(doc["bls_years"], [2024, 2025, 2026])
        self.assertIn("were not taken into account", info["note"])

    def test_an_identical_answer_leaves_the_cache_file_alone(self):
        self.run_fetch(lambda a, b: answer(range(max(a, 1988), b + 1)))
        path = FI.bls_cache_path(cache_dir=self.dir)
        with open(path, "rb") as f:
            first = f.read()
        self.calls = []
        # the same answer for the current window, and a refusal for the last older one: nothing to write
        info, err, changed = self.run_fetch(lambda a, b: answer(range(a, b + 1)) if a == 2024 else REFUSED)
        self.assertEqual(self.calls, [(2024, 2026), (2018, 2023)])
        self.assertIsNone(err)
        self.assertFalse(changed)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), first)
        # a revised value is written
        info, err, changed = self.run_fetch(lambda a, b: answer(range(a, b + 1), base=101.0) if a == 2024 else REFUSED)
        self.assertTrue(changed)
        self.assertEqual(FI.load_bls_cache(cache_dir=self.dir)["obs"]["2026-10"], 101.0 + 2026 + 0.10)

    def test_seeded_years_are_named_as_the_runs_they_are(self):
        # 1998-2007 refused, the windows before and after answered: the note must not claim 1998 to 2023 in one run
        self.run_fetch(lambda a, b: REFUSED if a == 1998 else answer(range(max(a, 1988), b + 1)))
        (doc, meta), = FI.bls_series(self.dir, meta_of=P.meta_of)
        self.assertIn(". 1998 to 2007 and 2018 to 2023: values of the previous release", meta["note"])
        self.assertNotIn("latest months may be preliminary", meta["note"])  # the current years came from the BLS
        self.assertEqual(FI.year_runs([1988, 1989, 2001, 2005, 2006]), "1988 to 1989, 2001 and 2005 to 2006")

    def test_while_the_seed_holds_the_latest_months_they_may_be_preliminary(self):
        (doc, meta), = FI.bls_series(self.dir, meta_of=P.meta_of)
        self.assertTrue(meta["note"].endswith(". 1988 to 2026: values of the previous release; the latest months may be preliminary"))

    def test_preliminary_months_are_named_in_the_note(self):
        self.run_fetch(lambda a, b: answer(range(max(a, 1988), b + 1), prelim={"2026-07", "2026-08", "2026-09", "2026-10"}))
        (doc, meta), = FI.bls_series(self.dir, meta_of=P.meta_of)
        self.assertIn("the BLS marks 2026-07 to 2026-10 as preliminary", meta["note"])
        self.assertIn("2018 to 2023: values of the previous release", meta["note"])
        self.assertEqual(meta["s"], "bls")
        self.assertEqual(doc["start"], "1988-01")  # the answers above have January to May 1988 too


class PublishedSeries(unittest.TestCase):
    """What data/prices holds for the Freight family."""

    @classmethod
    def setUpClass(cls):
        cls.idx = {m["id"]: m for m in jload(os.path.join(DATA, "index.json"))}

    def test_three_series_none_from_fred_none_called_a_rate_proxy(self):
        fam = sorted(i for i, m in self.idx.items() if m["k"] == "freight")
        self.assertEqual(fam, ["freight-ppi-m", "gscpi-m", "igrea-m"])
        self.assertEqual({self.idx[i]["s"] for i in fam}, {"bls", "dallasfed", "nyfed"})
        for i in fam:
            self.assertIn("not a freight rate", self.idx[i]["note"])
            self.assertNotIn("proxy for freight costs", self.idx[i]["note"].lower())
        self.assertNotIn("fred", {m["s"] for m in self.idx.values()})

    def test_every_source_is_in_the_registry(self):
        reg = {s["id"] for s in jload(os.path.join(ROOT, "data", "sources.json"))}
        self.assertLessEqual({"bls", "dallasfed", "nyfed"}, reg)
        self.assertNotIn("fred", reg)

    def test_the_bls_file_is_the_cache(self):
        doc = jload(os.path.join(DATA, "freight-ppi-m.json"))
        cache = FI.load_bls_cache()
        self.assertEqual(doc["start"], min(cache["obs"]))
        self.assertEqual(len(doc["v"]), len(cache["obs"]))
        self.assertEqual(doc["v"][-1], cache["obs"][max(cache["obs"])])
        m = self.idx["freight-ppi-m"]
        self.assertEqual(m["name"], "US deep-sea freight services, producer price index (BLS)")
        self.assertEqual(m["unit"], "index (Jun 1988 = 100)")
        # the figures of the basis on 2008 are the series' own
        v = dict(zip(range(len(doc["v"])), doc["v"]))
        i = lambda ym: (int(ym[:4]) - 1988) * 12 + int(ym[5:]) - 6  # noqa: E731
        self.assertEqual((v[i("2008-05")], v[i("2008-12")]), (256.5, 258.2))
        self.assertEqual((v[i("2008-09")], v[i("2009-05")]), (284.4, 208.8))
        self.assertEqual(max(v[k] for k in range(i("2008-01"), i("2009-12") + 1)), 284.4)
        self.assertEqual(round((258.2 / 256.5 - 1) * 100, 1), 0.7)
        self.assertEqual(round((208.8 / 284.4 - 1) * 100), -27)
        self.assertIn("+0.7% from May to December 2008 (256.5 to 258.2)", m["basis"])
        self.assertIn("a fall of 27% from September 2008 (284.4) to May 2009 (208.8)", m["basis"])
        self.assertNotIn("barely", m["basis"])

    def test_no_text_claims_a_copy_through_fred_once_the_seed_is_gone(self):
        """The years not yet returned by the BLS are the copy taken through FRED, which the About window, the registry,
        NOTICE.md, METHODOLOGY.md and DATA_SOURCES.md say (conditionally). Once the cache holds no seed, every year
        comes from the BLS: this test fails until those sentences are removed."""
        texts = {}
        for name in ("NOTICE.md", "METHODOLOGY.md", "DATA_SOURCES.md", os.path.join("web", "src", "components", "AboutDialog.tsx")):
            with open(os.path.join(ROOT, name), encoding="utf-8") as f:
                texts[name] = f.read()
        bls = next(s for s in jload(os.path.join(ROOT, "data", "sources.json")) if s["id"] == "bls")
        texts["data/sources.json (bls)"] = json.dumps(bls)
        texts["data/prices/index.json (note)"] = self.idx["freight-ppi-m"]["note"]
        claims = sorted(n for n, t in texts.items() if re.search(r"through (the )?FRED", t))
        if FI.load_bls_cache().get("seed"):
            self.assertEqual(claims, sorted(texts), "while the seed is in use, every text says where the older years come from")
        else:
            self.assertEqual(claims, [], "the BLS has returned every year: remove the sentence on the copy taken through FRED")

    def test_deviation_series_have_no_percent_change_on_the_board(self):
        for i in ("igrea-m", "gscpi-m"):
            self.assertIn("last", self.idx[i]["stats"])
            self.assertNotIn("chg", self.idx[i]["stats"])
        self.assertIn("chg", self.idx["freight-ppi-m"]["stats"])

    def test_no_late_freight_series(self):
        late = [x for x in P.check_freshness(list(self.idx.values()), date(2026, 11, 23)) if x[0] in ("bls", "dallasfed", "nyfed")]
        self.assertEqual(late, [])

    def test_a_freight_series_that_stops_advancing_is_late(self):
        metas = [dict(self.idx["igrea-m"], end="2026-08")]
        self.assertEqual([x[:2] for x in P.check_freshness(metas, date(2026, 11, 23))], [("dallasfed", "igrea-m")])


@unittest.skipUnless(os.path.exists(FI.DALLASFED_FILE) and os.path.exists(FI.NYFED_FILE), "raw/ is not tracked: the Dallas Fed and New York Fed files are not on this machine")
class PublishersFiles(unittest.TestCase):
    """The published series are the publishers' files, month by month."""

    def check(self, sid, reader, path):
        start, vals = reader(path)
        doc = jload(os.path.join(DATA, f"{sid}.json"))
        self.assertEqual(doc["start"], start)
        self.assertEqual(doc["v"], vals)
        FI.check_monthly(start, vals, 300)  # no missing month

    def test_igrea(self):
        self.check("igrea-m", FI.read_igrea, FI.DALLASFED_FILE)
        start, vals = FI.read_igrea(FI.DALLASFED_FILE)
        self.assertEqual(start, "1968-01")

    def test_gscpi(self):
        self.check("gscpi-m", FI.read_gscpi, FI.NYFED_FILE)
        self.assertEqual(FI.read_gscpi(FI.NYFED_FILE)[0], "1998-01")

    def test_a_failed_download_keeps_the_previous_file(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "igrea.xlsx")
            shutil.copy(FI.DALLASFED_FILE, dest)
            before = open(dest, "rb").read()
            saved = fetch.download

            def down(*a, **k):
                raise fetch.FetchError("ConnectionError after 4 attempts (www.dallasfed.org)")

            fetch.download = down
            try:
                with open(os.devnull, "w") as dn, contextlib.redirect_stdout(dn):
                    info, err = FI.fetch_dallasfed(d, dest=dest)
            finally:
                fetch.download = saved
            self.assertIsNone(info)
            self.assertIn("ConnectionError", err)
            self.assertEqual(open(dest, "rb").read(), before)

    def test_an_older_file_is_refused(self):
        start, vals = FI.read_gscpi(FI.NYFED_FILE)
        with self.assertRaises(ValueError):
            FI.check_monthly(start, vals[:-2], 300, prev_to=FI._end(start, len(vals)))


class WeeklyJob(unittest.TestCase):
    """fetch_prices.main(): each freight source is recorded on its own; a refusal is a failure, never a crash."""

    def test_a_refused_bls_request_is_a_failure_of_bls_only(self):
        import fetch_prices as F

        calls = []

        class Status:
            def get(self, source):
                return {}

            def record_success(self, source, records=None, data_to=None, note="updated", state=None):
                calls.append(("ok", source, note))

            def record_failure(self, source, error, **kw):
                calls.append(("fail", source, str(error)))

        saved = {k: getattr(F, k) for k in ("status", "fetch_pink", "fetch_eia", "fetch_freight", "rebuild", "late_series", "closed_series")}
        try:
            F.status = Status()
            F.fetch_pink = lambda stage: (None, "not tested here")
            F.fetch_eia = lambda stage: (None, "not tested here", 0)
            F.fetch_freight = lambda stage: {"bls": (None, "2024-2026: BLS did not process the request: daily threshold", False),
                                             "dallasfed": ({"records": 706, "data_to": "2026-10"}, None, True),
                                             "nyfed": ({"records": 346, "data_to": "2026-10"}, None, True)}
            F.rebuild = lambda: None
            F.late_series = lambda: {}
            F.closed_series = lambda: {}
            with open(os.devnull, "w") as dn, contextlib.redirect_stdout(dn):
                F.main()
        finally:
            for k, v in saved.items():
                setattr(F, k, v)
        mine = {c[1]: c for c in calls if c[1] in F.FREIGHT_SOURCES}
        self.assertEqual(mine["bls"][0], "fail")
        self.assertIn("daily threshold", mine["bls"][2])
        self.assertEqual((mine["dallasfed"][0], mine["nyfed"][0]), ("ok", "ok"))


if __name__ == "__main__":
    unittest.main()
