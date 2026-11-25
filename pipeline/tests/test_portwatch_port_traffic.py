"""Tests of the weekly port traffic from IMF PortWatch: the pure functions of pipeline/freight/portwatch_ports.py and the
script pipeline/freight/fetch_portwatch_port_traffic.py with a network that the tests make themselves.

Nothing here reads raw/ or a verbatim row of PortWatch: the daily rows are synthetic (calls = (day * 7 + type) % 5 and so
on), the weekly sums are recounted by a second, independent loop, and the service is a stub that answers the way the
real one was seen to (pages of 1,000 rows, `exceededTransferLimit`, a quota answer as an error body).

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_portwatch_port_traffic.py"
"""
import builtins
import contextlib
import copy
import csv
import fcntl
import io
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("", "freight"):
    p = os.path.join(ROOT, "pipeline", sub) if sub else os.path.join(ROOT, "pipeline")
    if p not in sys.path:
        sys.path.insert(0, p)

import fetch_portwatch as FP  # noqa: E402
import fetch_portwatch_port_traffic as S  # noqa: E402
import portwatch_ports as P  # noqa: E402
from common import fetch as F  # noqa: E402
from common import staleness as ST  # noqa: E402
from common import status  # noqa: E402

GET_JSON = F.get_json     # the download helper itself, before a test puts a stub in its place
TODAY = date(2026, 11, 25)
LAST_DAY = date(2026, 11, 20)   # the table lags the date by days
RULES = os.path.join(ROOT, "web", "scripts", "port-traffic-rules.mjs")


def down():
    """What a service that is down answers to each of the script's requests for one page: the helper is given one attempt."""
    return [F.FetchError("HTTP 503 after 1 attempts (services9.arcgis.com)") for _ in range(S.ATTEMPTS)]


# ------------------------------------------------------------------------------------------------ synthetic rows
def day_row(pid, d, k):
    """One synthetic daily row of the table: the fields asked for, plus the total columns the atlas must not use."""
    r = {"date": d.isoformat(), "portid": pid}
    for ti, t in enumerate(P.SOURCE_TYPES):
        r[f"portcalls_{t}"] = (k * 7 + ti) % 5
        r[f"import_{t}"] = 1000 * ((k + ti) % 13) + (k % 7)
        r[f"export_{t}"] = 1000 * ((k * 3 + ti) % 11) + 137 * (k % 5)
    return r


def make_table(pids, first, last, skip=()):
    """{port: [rows]} one row a day from ``first`` to ``last`` (dates), except the days of ``skip``."""
    table, oid = {p: [] for p in pids}, 0
    d, k = first, 0
    while d <= last:
        for p in pids:
            if d not in skip:
                oid += 1
                r = day_row(p, d, k + int(p[4:]))
                r["_oid"] = oid
                table[p].append(r)
        d += timedelta(days=1)
        k += 1
    return table


def recount(rows):
    """The weekly sums of the rows of one port by a loop of its own (ISO calendar weeks, the field names written out)."""
    by = {}
    for r in rows:
        y, w, _ = date.fromisoformat(r["date"]).isocalendar()
        by.setdefault((y, w), {})[r["date"]] = r
    out = {}
    for (y, w), days in by.items():
        if len(days) != 7:
            continue
        def s(kind, *types):
            return sum(days[d][f"{kind}_{t}"] for d in days for t in types)
        out[date.fromisocalendar(y, w, 1).isoformat()] = {
            "calls": [s("portcalls", "tanker"), s("portcalls", "dry_bulk"), s("portcalls", "container"), s("portcalls", "general_cargo", "roro")],
            "exports": [s("export", "tanker"), s("export", "dry_bulk"), s("export", "container"), s("export", "general_cargo", "roro")],
            "imports": [s("import", "tanker"), s("import", "dry_bulk"), s("import", "container"), s("import", "general_cargo", "roro")],
        }
    return out


def half_up(tonnes):
    """The rule for a weekly tonnage, written a second way: thousand tonnes with three significant figures at least and
    never finer than a tonne, so the decimals follow the number of digits of the integer tonnes (6 or more: none, 5: one,
    4: two, fewer: three), rounded half up with Decimal."""
    t = int(tonnes)
    dp = 0 if len(str(t)) >= 6 else 1 if len(str(t)) == 5 else 2 if len(str(t)) == 4 else 3
    q = (Decimal(t) / Decimal(1000)).quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP)
    return int(q) if q == q.to_integral_value() else float(q)


def doc_matches_recount(testcase, doc, rows):
    """Every week of ``doc`` is the recount of ``rows`` (a hole where the week is not complete), rounded by the rule."""
    want = recount(rows)
    start = date.fromisoformat(doc["start"])
    n = len(doc["calls"]["tanker"])
    testcase.assertEqual(min(want), doc["start"])
    testcase.assertEqual(max(want), (start + timedelta(weeks=n - 1)).isoformat())
    order = ["tanker", "dry", "container", "other"]
    for i in range(n):
        m = (start + timedelta(weeks=i)).isoformat()
        for k in ("calls", "exports", "imports"):
            for j, t in enumerate(order):
                got = doc[k][t][i]
                if m not in want:
                    testcase.assertIsNone(got, f"{m} is not a complete week: {k} {t} must be null")
                else:
                    exp = want[m][k][j] if k == "calls" else half_up(want[m][k][j])
                    testcase.assertEqual(got, exp, f"{m} {k} {t}")


# ------------------------------------------------------------------------------------------------ a service stub
class Service:
    """Answers get_json the way the service does: the ports and the day of ``where``, the order, the offset and the number of
    records asked, `exceededTransferLimit` when rows remain; only the fields asked for are returned."""

    def __init__(self, table):
        self.table = table
        self.calls = []        # (kwargs of get_json, params)
        self.script = []       # exceptions or documents to give before the table answers, in order
        self.threads = set()
        self.hook = None       # function(rows, params) -> rows, to change what the table gives

    def __call__(self, url, params=None, **kw):
        self.threads.add(threading.get_ident())
        self.calls.append((kw, params))
        if self.script:
            a = self.script.pop(0)
            if isinstance(a, Exception):
                raise a
            if a is not None:
                return a
        where = params["where"]
        ids = re.findall(r"'(port\d+)'", where.split(" AND ")[0])
        m = re.search(r"date > '(\d{4}-\d\d-\d\d)'", where)
        rows = [r for p in ids for r in self.table.get(p, []) if not m or r["date"] > m.group(1)]
        key = (lambda r: r["_oid"]) if params["orderByFields"] == "ObjectId" else (lambda r: (r["date"], r["portid"]))
        rows.sort(key=key)
        if self.hook:
            rows = self.hook(rows, params)
        off, n = params["resultOffset"], params["resultRecordCount"]
        page = rows[off:off + n]
        fields = params["outFields"].split(",")
        return {"features": [{"attributes": {k: r[k] for k in fields}} for r in page], "exceededTransferLimit": off + n < len(rows)}


class Env(unittest.TestCase):
    """A small atlas in a temporary folder: ``self.ports`` PortWatch ports, a table of names, an empty output folder, the status
    files in the folder too, no sleep, and ``self.svc`` as the network."""

    NAMES = ["Alpha", "Böte, Port", "Caldera", "Delta Terminal", "Eastport", "Fjord", "Gulf (Oil)", "Harbour", "Isla",
             "Jetty", "Kai", "Lagoon", "Marsa"]

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.n_ports = 8
        self.sleeps = []
        self.patches = []

    def start(self, n_ports=None, first=date(2025, 11, 3), last=date(2026, 11, 8)):
        n = n_ports or self.n_ports
        shutil.rmtree(os.path.join(self.tmp, "out"), True)
        for f in ("updates.json", "log.jsonl"):
            if os.path.exists(os.path.join(self.tmp, f)):
                os.remove(os.path.join(self.tmp, f))
        self.ports = [f"port{i + 1}" for i in range(n)]
        feats = []
        for i, p in enumerate(self.ports):
            feats.append({"properties": {"id": f"asset-{i}", "portwatch": p}})
            if i == 0:
                feats.append({"properties": {"id": "second-asset-of-the-port"}})   # an asset without an id
        with open(os.path.join(self.tmp, "ports.geojson"), "w", encoding="utf-8") as fh:
            json.dump({"features": feats}, fh)
        with open(os.path.join(self.tmp, "table.csv"), "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["portid", "name", "iso3", "locode", "lat", "lon", "pageid"])
            for i, p in enumerate(self.ports):
                w.writerow([p, self.NAMES[i % len(self.NAMES)], "AUS", "", 0, 0, ""])
        self.out = os.path.join(self.tmp, "out")
        self.svc = Service(make_table(self.ports, first, last))
        for target, value in [(P, {"PORTS_GEOJSON": os.path.join(self.tmp, "ports.geojson"), "TABLE": os.path.join(self.tmp, "table.csv"),
                                   "OUT": self.out}),
                              (status, {"UPDATES": os.path.join(self.tmp, "updates.json"), "LOG": os.path.join(self.tmp, "log.jsonl"),
                                        "JOURNAL": os.path.join(self.tmp, "journal")})]:
            pa = mock.patch.multiple(target, **value)
            pa.start()
            self.addCleanup(pa.stop)
        self.lock = os.path.join(self.tmp, "lock")      # never the real lock: a sitting of the first load may be running
        for pa in (mock.patch.object(S.fetch, "get_json", self.svc), mock.patch.object(S.time, "sleep", self.sleeps.append),
                   mock.patch.object(S, "LOCK_PATH", self.lock)):
            pa.start()
            self.addCleanup(pa.stop)

    def run_script(self, *argv, today=TODAY):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            res = S.run(list(argv), today=today)
        self.output = buf.getvalue()
        return res

    def read(self, pid):
        with open(os.path.join(self.out, f"{pid}.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def tree(self):
        """{file: bytes} of the output folder."""
        out = {}
        for dp, _, fs in os.walk(self.out):
            for f in fs:
                with open(os.path.join(dp, f), "rb") as fh:
                    out[os.path.relpath(os.path.join(dp, f), self.out)] = fh.read()
        return out

    def rows(self, pid, until=None):
        return [r for r in self.svc.table[pid] if until is None or r["date"] <= until.isoformat()]


# ------------------------------------------------------------------------------------------------ the pure part
class WeeklySums(unittest.TestCase):
    def test_the_fields_asked_for_are_the_seventeen_the_build_needs(self):
        self.assertEqual(len(P.ASK_FIELDS), 17)
        self.assertEqual(P.ASK_FIELDS[:2], ["date", "portid"])
        self.assertEqual(len(set(P.ASK_FIELDS)), 17)
        self.assertFalse([f for f in P.ASK_FIELDS if f in ("portcalls", "import", "export", "portcalls_cargo", "import_cargo", "export_cargo")],
                         "the total columns of the source are never asked for")

    def test_weekly_sums_equal_an_independent_recount_and_partial_weeks_are_dropped(self):
        # starts on a Wednesday and ends on a Tuesday: a partial week at each end
        first, last = date(2025, 1, 1), date(2026, 3, 3)
        rows = make_table(["port9"], first, last)["port9"]
        weeks = P.weekly(rows)
        want = recount(rows)
        self.assertEqual(sorted(weeks), sorted(want))
        self.assertEqual(min(weeks), "2025-01-06")        # the Monday after the first day
        self.assertEqual(max(weeks), "2026-02-23")        # the last Sunday is 1 March: the week of 2 March is partial
        order = ["tanker", "dry", "container", "other"]
        for m, w in weeks.items():
            for k in ("calls", "exports", "imports"):
                self.assertEqual([w[k][t] for t in order], want[m][k], f"{m} {k}")

    def test_a_week_with_six_days_is_a_hole_in_all_twelve_arrays_not_a_zero(self):
        rows = make_table(["port9"], date(2025, 1, 6), date(2025, 3, 30), skip={date(2025, 2, 12)})["port9"]
        weeks = P.weekly(rows)
        self.assertNotIn("2025-02-10", weeks)
        doc = P.build_doc("port9", "Nine", weeks, "2025-03-30")
        i = (date(2025, 2, 10) - date(2025, 1, 6)).days // 7
        for k in ("calls", "exports", "imports"):
            for t in ("tanker", "dry", "container", "other"):
                self.assertIsNone(doc[k][t][i])
                self.assertIsNotNone(doc[k][t][i - 1])
        doc_matches_recount(self, doc, rows)
        self.assertEqual(P.validate_doc(doc, "port9"), [])

    def test_other_is_general_cargo_plus_roro_and_the_total_columns_are_not_used(self):
        rows = []
        for d in range(7):
            r = {k: 0 for k in P.ASK_FIELDS}
            r.update({"date": (date(2025, 1, 6) + timedelta(days=d)).isoformat(), "portid": "port9",
                      "portcalls_general_cargo": 1, "portcalls_roro": 2, "export_general_cargo": 400, "export_roro": 700,
                      "import_tanker": 1500, "portcalls": 99, "export": 10 ** 9, "import": 10 ** 9})   # totals that contradict the types
            rows.append(r)
        w = P.weekly(rows)["2025-01-06"]
        self.assertEqual(w["calls"]["other"], 21)
        self.assertEqual(w["exports"]["other"], 7700)
        self.assertEqual(w["imports"]["tanker"], 10500)
        self.assertEqual(sum(w["calls"].values()), 21)       # not 99 a day

    def test_a_day_that_comes_twice_counts_once(self):
        rows = make_table(["port9"], date(2025, 1, 6), date(2025, 1, 12))["port9"]
        self.assertEqual(P.weekly(rows + rows[:3]), P.weekly(rows))

    def test_tonnes_are_rounded_half_up_by_their_size_at_the_edges_of_every_size(self):
        # (tonnes, thousand tonnes stored), written by hand: whole kt from 100 kt, one decimal from 10 kt, two from 1 kt, the tonne below
        edges = [(0, 0), (1, 0.001), (999, 0.999), (1000, 1), (1004, 1), (1005, 1.01), (1006, 1.01), (9994, 9.99), (9995, 10),
                 (10000, 10), (10049, 10), (10050, 10.1), (99949, 99.9), (99950, 100), (100000, 100), (100499, 100), (100500, 101),
                 (999499, 999), (999500, 1000), (1234500, 1235), (1234499, 1234)]
        for t, want in edges:
            got = P.kt(t)
            self.assertEqual(got, want, t)
            self.assertEqual(got, half_up(t), t)
            self.assertIsInstance(got, int if want == int(want) else float, t)
            self.assertEqual(json.dumps(got), json.dumps(want), t)      # the text of the file: 9.99, 10 and not 10.0
        self.assertEqual([P.round_tonnes(t) for t in (999, 1004, 1005, 9994, 9995, 99949, 99950, 999499, 999500)],
                         [999, 1000, 1010, 9990, 10000, 99900, 100000, 999000, 1000000])

    def test_the_rule_agrees_with_the_second_way_on_a_wide_run_of_tonnages_keeps_three_figures_and_moves_a_sum_by_half_a_per_cent_at_most(self):
        import random
        rng = random.Random(20261125)
        tonnages = list(range(0, 3000)) + list(range(9900, 10100)) + list(range(99900, 100100)) + list(range(999400, 999600))
        tonnages += [rng.randrange(0, 5_000_000) for _ in range(20000)] + [int(10 ** rng.uniform(0, 7)) for _ in range(20000)]
        for t in tonnages:
            v = P.kt(t)
            self.assertEqual(v, half_up(t), t)
            self.assertTrue(P._fits_rule(v), (t, v))
            self.assertLessEqual(abs(P.round_tonnes(t) - t), 0.005 * t, t)
            self.assertGreaterEqual(Decimal(repr(v)).as_tuple().exponent, -P.MAX_DECIMALS, t)
        for _ in range(300):    # a sum of 52 weeks of one size and of mixed sizes: never further than 0.5% from the exact one
            weeks = [int(10 ** rng.uniform(0, 6.5)) for _ in range(52)]
            exact = sum(weeks)
            self.assertLessEqual(abs(sum(P.round_tonnes(t) for t in weeks) - exact) / exact, 0.005)
        with self.assertRaises(ValueError):
            P.round_tonnes(-1)

    def test_the_document_equals_the_recount_by_the_rule_and_states_the_unit_and_the_most_decimals(self):
        rows = make_table(["port9"], date(2025, 5, 7), date(2026, 2, 3))["port9"]
        doc = P.build_doc("port9", "Nine", P.weekly(rows), P.last_day(rows))
        self.assertEqual((doc["u"], doc["dp"]), ("kt", 3))
        self.assertEqual(P.MAX_DECIMALS, 3)
        doc_matches_recount(self, doc, rows)
        self.assertEqual(P.validate_doc(doc, "port9"), [])
        values = {v for k in ("exports", "imports") for t in doc[k] for v in doc[k][t] if v is not None}
        self.assertTrue(any(isinstance(v, float) for v in values) and any(isinstance(v, int) for v in values))

    def test_rounding_error_is_the_difference_of_the_52_week_sums(self):
        rows = make_table(["port9"], date(2024, 1, 1), date(2026, 2, 1))["port9"]
        weeks = P.weekly(rows)
        last = sorted(weeks)[-52:]
        types = ("tanker", "dry", "container", "other")
        # the four types together, as the 52-week figure of the page is
        worst = 0.0
        for k in ("exports", "imports"):
            exact = sum(weeks[m][k][t] for m in last for t in types)
            rounded = round(sum(half_up(weeks[m][k][t]) for m in last for t in types) * 1000)
            worst = max(worst, abs(rounded - exact) / exact)
        share, where = P.rounding_error(weeks)
        self.assertAlmostEqual(share, worst)
        self.assertIn(where, ("exports", "imports"))
        # one type alone
        worst = 0.0
        for k in ("exports", "imports"):
            for t in types:
                exact = sum(weeks[m][k][t] for m in last)
                rounded = round(sum(half_up(weeks[m][k][t]) for m in last) * 1000)
                worst = max(worst, abs(rounded - exact) / exact)
        share_t, where_t = P.rounding_error(weeks, by_type=True)
        self.assertAlmostEqual(share_t, worst)
        self.assertGreaterEqual(share_t, share)
        self.assertLessEqual(share_t, 0.005)
        self.assertIsNotNone(where_t)
        self.assertEqual(P.rounding_error({}), (0.0, None))

    def test_nothing_daily_is_in_a_document(self):
        rows = make_table(["port9"], date(2025, 1, 6), date(2025, 6, 29))["port9"]
        doc = P.build_doc("port9", "Nine", P.weekly(rows), "2025-06-29")
        self.assertEqual(list(doc), list(P.KEYS))
        self.assertLessEqual(len(doc["calls"]["tanker"]), 26)


class Rows(unittest.TestCase):
    def feats(self, rows):
        return [{"attributes": {k: r[k] for k in P.ASK_FIELDS}} for r in rows]

    def test_a_good_page_is_read_and_the_date_is_an_iso_day(self):
        rows = make_table(["port9"], date(2025, 1, 6), date(2025, 1, 8))["port9"]
        got = P.parse_rows(self.feats(rows), {"port9"})
        self.assertEqual([r["date"] for r in got], ["2025-01-06", "2025-01-07", "2025-01-08"])
        ms = [{"attributes": {**f["attributes"], "date": 1_736_121_600_000}} for f in self.feats(rows[:1])]   # 6 January 2025, UTC
        self.assertEqual(P.parse_rows(ms)[0]["date"], "2025-01-06")

    def test_a_page_that_is_not_what_the_atlas_expects_is_refused(self):
        rows = make_table(["port9"], date(2025, 1, 6), date(2025, 1, 6))["port9"]
        good = self.feats(rows)
        gone = copy.deepcopy(good)
        del gone[0]["attributes"]["export_tanker"]
        text = copy.deepcopy(good)
        text[0]["attributes"]["import_roro"] = "12"
        none = copy.deepcopy(good)
        none[0]["attributes"]["portcalls_tanker"] = None
        neg = copy.deepcopy(good)
        neg[0]["attributes"]["export_roro"] = -1
        for bad, msg in [(gone, "missing export_tanker"), (text, "not a number in import_roro"), (none, "portcalls_tanker"), (neg, "export_roro"),
                         ([{"x": 1}], "without attributes")]:
            with self.assertRaises(P.RowError, msg=msg) as cm:
                P.parse_rows(bad, {"port9"})
            self.assertIn(msg.split()[-1], str(cm.exception))
        with self.assertRaises(P.RowError):
            P.parse_rows(good, {"port1"})       # a port that was not asked for
        extra = copy.deepcopy(good)
        extra[0]["attributes"]["a_new_field"] = 5
        self.assertEqual(len(P.parse_rows(extra, {"port9"})), 1)   # new fields are ignored


class Merge(unittest.TestCase):
    def setUp(self):
        self.rows = make_table(["port9"], date(2025, 1, 6), date(2026, 3, 1))["port9"]    # whole weeks, to a Sunday
        self.doc = P.build_doc("port9", "Nine", P.weekly(self.rows), "2026-03-01")

    def later(self, upto, change=None):
        rows = [dict(r) for r in make_table(["port9"], date(2025, 1, 6), upto)["port9"]]
        for r in rows:
            if change and r["date"] in change:
                r["export_dry_bulk"] += change[r["date"]]
        return rows

    def test_weeks_before_the_window_stay_byte_identical_inside_are_replaced_and_new_weeks_are_appended(self):
        since = P.window_since(self.doc)
        self.assertEqual(since, date(2026, 2, 23) - timedelta(weeks=5))
        rows = self.later(date(2026, 3, 19), change={"2025-06-10": 5000, "2026-02-03": 7000, "2026-02-25": 90000})
        new = P.merge_weeks(self.doc, P.weekly(rows), since, "2026-03-19")
        cut = (since - date(2025, 1, 6)).days // 7
        n0 = len(self.doc["calls"]["tanker"])
        self.assertEqual(new["start"], self.doc["start"])
        self.assertEqual(len(new["calls"]["tanker"]), n0 + 2)    # the weeks of 2 and 9 March; the week of 16 March is partial
        for k in ("calls", "exports", "imports"):
            for t in ("tanker", "dry", "container", "other"):
                self.assertEqual(json.dumps(new[k][t][:cut]), json.dumps(self.doc[k][t][:cut]), "a week before the window changed")
        # the day of 2025-06-10 and of 2026-02-03 are older than the window (2026-01-19 to 2026-02-22 is inside: 2026-02-03 is inside)
        i_old = (date(2025, 6, 9) - date(2025, 1, 6)).days // 7
        self.assertEqual(new["exports"]["dry"][i_old], self.doc["exports"]["dry"][i_old])
        i_in = (date(2026, 2, 2) - date(2025, 1, 6)).days // 7
        self.assertEqual(new["exports"]["dry"][i_in], half_up(recount(rows)["2026-02-02"]["exports"][1]))
        i_edge = (date(2026, 2, 23) - date(2025, 1, 6)).days // 7
        self.assertEqual(new["exports"]["dry"][i_edge], half_up(recount(rows)["2026-02-23"]["exports"][1]))
        self.assertEqual(new["y"], "2026-03-19")
        self.assertIsNone(P.check_merge(self.doc, new, since))
        self.assertEqual(P.validate_doc(new, "port9"), [])
        # the same rows again: nothing changes
        again = P.merge_weeks(new, P.weekly(rows), since, "2026-03-19")
        self.assertEqual(json.dumps(again), json.dumps(new))

    def test_a_week_that_comes_back_incomplete_does_not_replace_the_stored_one_and_a_gap_is_filled_with_nulls(self):
        since = P.window_since(self.doc)
        rows = self.later(date(2026, 3, 29))
        rows = [r for r in rows if r["date"] not in ("2026-03-18", "2026-03-04")]   # two incomplete weeks after the file
        new = P.merge_weeks(self.doc, P.weekly(rows), since, "2026-03-29")
        n0 = len(self.doc["calls"]["tanker"])
        self.assertEqual(len(new["calls"]["tanker"]), n0 + 4)
        self.assertEqual([new["calls"][t][n0] for t in ("tanker", "dry")], [None, None])          # the week of 2 March: incomplete
        self.assertIsNotNone(new["calls"]["tanker"][n0 + 1])
        self.assertIsNone(new["calls"]["tanker"][n0 + 2])                                          # the week of 16 March: incomplete
        self.assertIsNotNone(new["calls"]["tanker"][n0 + 3])
        self.assertEqual(P.validate_doc(new, "port9"), [])

    def test_a_week_before_the_first_week_is_not_added(self):
        rows = make_table(["port9"], date(2024, 12, 2), date(2026, 3, 1))["port9"]
        new = P.merge_weeks(self.doc, P.weekly(rows), date(2024, 12, 2))
        self.assertEqual(new["start"], self.doc["start"])
        self.assertEqual(len(new["calls"]["tanker"]), len(self.doc["calls"]["tanker"]))

    def test_the_merge_is_refused_when_it_would_lose_weeks_move_the_start_or_change_an_old_week(self):
        since = P.window_since(self.doc)
        for field, edit, why in [
            ("fewer weeks", lambda d: [d[k][t].pop() for k in ("calls", "exports", "imports") for t in ("tanker", "dry", "container", "other")], "fewer weeks"),
            ("start", lambda d: d.update(start="2025-01-13"), "first week"),
            ("y", lambda d: d.update(y="2026-02-01"), "earlier"),
            ("an old week", lambda d: d["exports"]["dry"].__setitem__(3, d["exports"]["dry"][3] + 1), "would change"),
        ]:
            new = copy.deepcopy(self.doc)
            edit(new)
            self.assertIn(why, P.check_merge(self.doc, new, since), field)

    def test_the_revision_of_older_weeks_is_measured_against_the_file(self):
        since = P.deep_since(self.doc)
        before = P.window_since(self.doc)
        self.assertEqual(since, P.last_monday(self.doc) - timedelta(weeks=52))
        new = copy.deepcopy(self.doc)
        self.assertEqual(P.revision(self.doc, new, since, before), 0.0)
        i0 = (since - date.fromisoformat(self.doc["start"])).days // 7
        for k in ("exports", "imports"):
            for t in ("tanker", "dry", "container", "other"):
                new[k][t][i0 + 2] = (new[k][t][i0 + 2] or 0) * 2
        share = P.revision(self.doc, new, since, before)
        old_sum = sum(self.doc[k][t][i] for k in ("calls", "exports", "imports") for t in ("tanker", "dry", "container", "other")
                      for i in range(i0, (before - date.fromisoformat(self.doc["start"])).days // 7))
        extra = sum(self.doc[k][t][i0 + 2] for k in ("exports", "imports") for t in ("tanker", "dry", "container", "other"))
        self.assertAlmostEqual(share, extra / old_sum)
        self.assertIsNone(P.revision({**self.doc, "calls": {t: [0] * len(v) for t, v in self.doc["calls"].items()},
                                      "exports": {t: [0] * len(v) for t, v in self.doc["exports"].items()},
                                      "imports": {t: [0] * len(v) for t, v in self.doc["imports"].items()}}, new, since, before))


class Requests(unittest.TestCase):
    def test_chunks_hold_at_most_the_ports_of_one_page_of_the_window_and_stay_under_the_address_limit_with_every_port_once(self):
        ids = P.port_ids()
        self.assertEqual(len(ids), len(set(ids)))
        ch = P.chunks(ids, date(2026, 10, 5))
        self.assertEqual([i for c in ch for i in c], ids)
        for c in ch:
            self.assertLessEqual(len(c), P.MAX_IDS)
            self.assertLess(len(P.address(P.where_window(c, date(2026, 10, 5)))), P.MAX_ADDRESS)
        self.assertGreater(len(ch), len(ids) // P.MAX_IDS)

    def test_the_address_limit_splits_a_chunk_before_the_count_does(self):
        ids = [f"port{n}" for n in range(1000, 1060)]
        ch = P.chunks(ids, date(2026, 10, 5), max_chars=700)
        self.assertGreater(len(ch), 3)
        self.assertTrue(all(len(P.address(P.where_window(c, date(2026, 10, 5)))) <= 700 for c in ch))
        self.assertEqual([i for c in ch for i in c], ids)
        self.assertTrue(any(len(c) < P.MAX_IDS for c in ch[:-1]))

    def test_a_port_id_that_is_not_one_never_reaches_a_query(self):
        for bad in ("port1'; --", "x", "port", "port1 OR 1=1"):
            with self.assertRaises(ValueError):
                P.where_window([bad], date(2026, 10, 5))
            with self.assertRaises(ValueError):
                P.where_history(bad)

    def test_the_query_has_the_shape_the_service_was_seen_to_answer(self):
        w = P.where_window(["port955", "port276"], date(2026, 11, 2))
        self.assertEqual(w, "portid IN ('port955','port276') AND date > '2026-11-01'")
        self.assertEqual(P.where_history("port955"), "portid = 'port955'")
        q = P.request_params(w, 2000, "ObjectId")
        self.assertEqual((q["resultOffset"], q["resultRecordCount"], q["f"], q["returnGeometry"]), (2000, P.PAGE, "json", "false"))
        self.assertEqual(q["outFields"].split(","), P.ASK_FIELDS)

    def test_the_quarters_partition_the_ports_and_four_consecutive_weeks_read_all_of_them_also_across_a_year_with_53_weeks(self):
        n = 163
        for start in (date(2026, 11, 25), date(2026, 12, 14), date(2026, 12, 21)):      # the last crosses ISO week 53 to week 1
            seen = []
            for w in range(4):
                today = start + timedelta(weeks=w)
                seen.append({i for i in range(n) if P.quarter_of(i, today)})
            self.assertEqual(sorted(i for s in seen for i in s), list(range(n)), start)
            self.assertTrue(all(not (a & b) for k, a in enumerate(seen) for b in seen[k + 1:]))
        self.assertEqual(date(2026, 12, 28).isocalendar()[1], 53)                          # the case that the ISO week number gets wrong
        self.assertEqual(date(2027, 1, 4).isocalendar()[1], 1)
        # every day of one week is the same quarter
        self.assertEqual({P.week_index(date(2026, 11, 23) + timedelta(days=d)) for d in range(7)}, {P.week_index(date(2026, 11, 23))})

    def fake_docs(self, ids, last="2026-11-09", weeks=80):
        start = date.fromisoformat(last) - timedelta(weeks=weeks - 1)
        return {i: {"start": start.isoformat(), "calls": {"tanker": [0] * weeks}} for i in ids}

    def test_the_weekly_plan_reads_the_window_of_most_ports_the_deep_pass_of_one_quarter_and_a_few_new_ports(self):
        ids = [f"port{n}" for n in range(1000, 1100)]
        docs = self.fake_docs(ids[:90])
        pl = P.plan(ids, docs, set(), TODAY)
        q = pl["quarter"]
        deep = [p for g in pl["deep"] for p in g["ports"]]
        window = [p for g in pl["window"] for p in g["ports"]]
        self.assertEqual(deep, [i for n, i in enumerate(ids[:90]) if n % 4 == q])
        self.assertEqual(sorted(deep + window), ids[:90])
        self.assertEqual(pl["window"][0]["since"], (date(2026, 11, 9) - timedelta(weeks=5)).isoformat())
        self.assertEqual(pl["deep"][0]["since"], (date(2026, 11, 9) - timedelta(weeks=52)).isoformat())
        self.assertEqual(pl["history"], ids[90:90 + P.SCHEDULED_BACKFILL_CAP])
        self.assertEqual(len(pl["history"]), 5)
        # each port read in full counts its pages and the check that a port that ends weeks before the others is late in the service
        self.assertEqual(pl["requests"]["history"], 5 * (P.pages((TODAY - date.fromisoformat(P.HISTORY_FROM)).days + 1) + P.FIRST_READ_CHECK))
        n_pages = sum(P.pages(len(c) * g["days"]) for k in ("window", "deep") for g in pl[k] for c in g["chunks"])
        self.assertEqual(pl["requests"]["window"] + pl["requests"]["deep"], n_pages)
        for k in ("window", "deep"):
            for g in pl[k]:
                for c in g["chunks"]:
                    self.assertLessEqual(len(c), P.MAX_IDS)

    def test_ports_with_different_last_weeks_are_asked_from_their_own_window(self):
        ids = [f"port{n}" for n in range(1000, 1010)]
        docs = {**self.fake_docs(ids[:5], "2026-11-09"), **self.fake_docs(ids[5:], "2026-10-26")}
        pl = P.plan(ids, docs, set(), TODAY)
        sinces = sorted({g["since"] for k in ("window", "deep") for g in pl[k]})
        self.assertGreater(len(sinces), 1)
        for k in ("window", "deep"):
            for g in pl[k]:
                for p in g["ports"]:
                    self.assertEqual(g["since"], iso_of(P.window_since(docs[p]) if k == "window" else P.deep_since(docs[p])))

    def test_a_first_load_sitting_takes_the_next_ports_without_a_file_and_never_a_port_that_returned_nothing(self):
        ids = [f"port{n}" for n in range(1000, 1040)]
        docs = self.fake_docs(ids[:3])
        none = {ids[3], ids[5]}
        pl = P.plan(ids, docs, none, TODAY, backfill=True, max_ports=15)
        self.assertEqual(pl["history"], [i for i in ids[3:] if i not in none][:15])
        self.assertEqual(pl["window"] + pl["deep"], [])
        self.assertEqual(P.plan(ids, docs, none, TODAY, backfill=True)["history"], [i for i in ids[3:] if i not in none][:P.SITTING_MAX])
        self.assertEqual(len(P.plan(ids, docs, none, TODAY, backfill=True, max_ports=1000)["history"]), P.SITTING_MAX)
        pl = P.plan(ids, docs, none, TODAY, backfill=True, max_ports=15)
        self.assertEqual(pl["requests"]["total"], 15 * 3)

    def test_a_port_that_returned_nothing_is_asked_again_only_in_the_week_of_its_quarter_and_inside_the_cap(self):
        ids = [f"port{n}" for n in range(1000, 1025)]
        docs = self.fake_docs(ids[:20])
        none = {ids[21], ids[22], ids[23], ids[24]}      # four places in a row: one of each quarter
        hits = [i for w in range(4) for i in P.plan(ids, docs, none, TODAY + timedelta(weeks=w))["history"] if i in none]
        self.assertEqual(sorted(hits), sorted(none))
        for w in range(4):
            self.assertLessEqual(len(P.plan(ids, docs, none, TODAY + timedelta(weeks=w))["history"]), P.SCHEDULED_BACKFILL_CAP)
        # the ports that are new come first
        self.assertEqual(P.plan(ids, docs, none, TODAY)["history"][0], ids[20])

    def test_full_reads_the_ports_named_in_full_whatever_they_hold(self):
        ids = [f"port{n}" for n in range(1000, 1010)]
        docs = self.fake_docs(ids)
        pl = P.plan(ids, docs, set(), TODAY, full=[ids[4], ids[2]])
        self.assertEqual(pl["history"], [ids[2], ids[4]])
        self.assertEqual(pl["window"] + pl["deep"], [])

    def test_the_request_bounds_of_a_weekly_run_come_from_the_plan(self):
        n = len(P.port_ids())
        least, usual, most = P.weekly_request_bounds(n, TODAY, S.MAX_REQUESTS)
        self.assertLessEqual(least, usual)
        self.assertLessEqual(usual, most)
        self.assertEqual(most, S.MAX_REQUESTS)
        self.assertGreaterEqual(least, math.ceil(n / P.MAX_IDS))
        self.assertEqual((least, usual), (min(P.normal_week_requests(n, TODAY, lag) for lag in P.TABLE_LAG_DAYS),
                                          max(P.normal_week_requests(n, TODAY, lag) for lag in P.TABLE_LAG_DAYS)))
        self.assertEqual(P.weekly_request_bounds(n, TODAY + timedelta(weeks=1), S.MAX_REQUESTS)[0] > 0, True)

    def test_a_normal_week_for_any_number_of_ports_is_the_plan_of_the_state_a_chain_of_weekly_runs_leaves(self):
        """The count of the model is the plan's on rows that really exist: one page for a chunk of the window (fewer than PAGE rows, no
        request for a next page) and, for the quarter read in depth, the pages the rows fill. Recounted here from the rows of a table."""
        for n in (1, 7, 18, 19, 36, 100, 163, 164, 250):
            for week in range(4):
                today = date(2026, 12, 2) + timedelta(weeks=week)
                for lag in P.TABLE_LAG_DAYS:
                    end = today - timedelta(days=lag)
                    before = end - timedelta(days=7)               # the last day of the table at the previous run
                    last = before - timedelta(days=6) if before.weekday() == 6 else P.monday(before) - timedelta(days=7)
                    q = P.week_index(today) % P.QUARTERS
                    ids = list(range(n))
                    deep = [i for i in ids if i % P.QUARTERS == q]
                    window = [i for i in ids if i % P.QUARTERS != q]
                    want = 0
                    for group, weeks in ((window, P.WINDOW_WEEKS - 1), (deep, P.DEEP_WEEKS)):
                        days = (end - (last - timedelta(weeks=weeks))).days + 1
                        for k in range(0, len(group), P.MAX_IDS):
                            rows = len(group[k:k + P.MAX_IDS]) * days
                            want += math.ceil(rows / P.PAGE) if rows % P.PAGE else rows // P.PAGE + 1      # a page that is full is followed by one
                    self.assertEqual(P.normal_week_requests(n, today, lag), want, (n, today, lag))
        # every window of a normal week is one page: fewer rows than the page for the longest window
        longest = max((today - timedelta(days=lag) - (last - timedelta(weeks=P.WINDOW_WEEKS - 1))).days + 1
                      for today, last, lag in ((date(2026, 12, 2), date(2026, 11, 16) + timedelta(days=d), 0) for d in range(-6, 1)))
        self.assertLessEqual(P.MAX_IDS * P.WINDOW_DAYS_MAX, P.PAGE - 1)
        self.assertGreater((P.MAX_IDS + 1) * P.WINDOW_DAYS_MAX, P.PAGE - 1)
        self.assertEqual(P.WINDOW_DAYS_MAX, 55)

    def test_the_size_of_a_chunk_asks_for_the_fewest_requests_of_a_normal_week(self):
        """No size of chunk from 1 to 20 ports asks for fewer requests in a normal week, for any day the table can end on and any week of the
        rotation, than MAX_IDS does, and the sizes above it ask for more in at least one of them (the window is two pages)."""
        n = len(P.port_ids())
        sums = {}
        saved = P.chunks.__defaults__
        try:
            for size in range(1, 21):
                P.chunks.__defaults__ = (size, P.MAX_ADDRESS)
                sums[size] = [P.normal_week_requests(n, date(2026, 12, 2) + timedelta(weeks=w), lag) for w in range(4) for lag in P.TABLE_LAG_DAYS]
        finally:
            P.chunks.__defaults__ = saved
        for size in range(1, 21):
            self.assertLessEqual(max(sums[P.MAX_IDS]), max(sums[size]), f"{size} ports a request ask for fewer in the worst week")
            self.assertLessEqual(sum(sums[P.MAX_IDS]), sum(sums[size]), f"{size} ports a request ask for fewer on average")
        for size in range(P.MAX_IDS + 1, 21):
            self.assertGreater(max(sums[size]), max(sums[P.MAX_IDS]))

    def test_a_page_that_is_full_costs_one_more_request_in_the_count(self):
        self.assertEqual([P.pages(r) for r in (0, 1, 999, 1000, 1001, 1999, 2000)], [1, 1, 1, 2, 2, 2, 3])
        # a first read of a port takes three requests while the table holds fewer than three pages of days
        self.assertEqual(P.pages(P.PAGE * 3 - 1), 3)
        self.assertEqual(P.pages(P.PAGE * 3), 4)


class WeeklyBound(unittest.TestCase):
    """The plan of a scheduled run never asks for more than S.MAX_REQUESTS, whatever state the files are in, and the time that costs
    at the longest pause fits the limit the script gives itself and the step of the workflow."""

    def docs(self, ids, today, lag):
        """Files whose last week is (2 + lag(i)) weeks before the Monday of ``today``: the weeks an ordinary run leaves, and more."""
        out = {}
        for i, pid in enumerate(ids):
            last = P.monday(today) - timedelta(weeks=2 + lag(i))
            out[pid] = {"start": (last - timedelta(weeks=300)).isoformat(), "calls": {"tanker": [0] * 301}}
        return out

    def test_the_plan_keeps_to_the_bound_in_every_state_of_the_files(self):
        ids = [f"port{n}" for n in range(1, 164)]
        for weekday in range(7):
            today = date(2026, 11, 23) + timedelta(days=weekday)
            for lag_weeks in (0, 1, 3, 6, 10, 30, 100):
                for name, lag in (("all", lambda i: lag_weeks), ("spread", lambda i: i % (lag_weeks + 1)),
                                  ("a few", lambda i: lag_weeks if i % 9 == 0 else 0)):
                    docs = self.docs(ids, today, lag)
                    for missing in (0, 5, 40):
                        d = {k: v for k, v in docs.items() if int(k[4:]) > missing}
                        pl = P.plan(ids, d, set(), today, max_requests=S.MAX_REQUESTS)
                        label = f"{today} lag {lag_weeks} {name} missing {missing}"
                        self.assertLessEqual(pl["requests"]["total"], S.MAX_REQUESTS, label)
                        self.assertLessEqual(len(pl["history"]), P.SCHEDULED_BACKFILL_CAP, label)
                        read = {p for kind in ("window", "deep") for g in pl[kind] for p in g["ports"]}
                        self.assertEqual(read | set(pl["deferred"]), set(d), label)
                        self.assertFalse(read & set(pl["deferred"]), label)

    def test_the_ports_that_end_earliest_are_read_first_and_the_others_wait_for_the_next_run(self):
        ids = [f"port{n}" for n in range(1, 164)]
        today = date(2026, 11, 25)
        docs = self.docs(ids, today, lambda i: 100 if i < 20 else 0)       # twenty files two years late, the rest as usual
        pl = P.plan(ids, docs, set(), today, max_requests=12)
        read = {p for kind in ("window", "deep") for g in pl[kind] for p in g["ports"]}
        self.assertTrue(read)
        self.assertTrue(set(ids[:20]) & read, "the files that end earliest must be read first")
        self.assertTrue(pl["deferred"])
        self.assertLessEqual(pl["requests"]["total"], 12)
        # the cap does not bite in the usual state: nothing is deferred
        usual = P.plan(ids, self.docs(ids, today, lambda i: 0), set(), today, max_requests=S.MAX_REQUESTS)
        self.assertEqual(usual["deferred"], [])

    def test_a_run_that_defers_ports_reads_them_in_the_following_weeks_and_ends_with_none_late(self):
        ids = [f"port{n}" for n in range(1, 164)]
        today = date(2026, 11, 25)
        docs = self.docs(ids, today, lambda i: 40)
        for week in range(8):
            t = today + timedelta(weeks=week)
            pl = P.plan(ids, docs, set(), t, max_requests=S.MAX_REQUESTS)
            for kind in ("window", "deep"):
                for g in pl[kind]:
                    for p in g["ports"]:       # a port that was read now ends with the table
                        docs[p] = self.docs([p], t, lambda i: 0)[p]
            if not pl["deferred"]:
                break
        self.assertEqual(pl["deferred"], [])
        self.assertLess(week, 7, "ports left to the next run must be read within a few weeks")

    def test_the_longest_run_at_the_longest_pause_fits_the_limit_of_the_script_and_of_its_step(self):
        self.assertLessEqual(S.MAX_REQUESTS * (FP.PAUSE_S[1] + S.REQUEST_S), S.RUN_LIMIT_S)
        self.assertGreater((S.MAX_REQUESTS + 1) * (FP.PAUSE_S[1] + S.REQUEST_S), S.RUN_LIMIT_S)
        step = int(re.search(r"Fetch PortWatch port traffic[^\n]*\n(?:.*\n)*?\s+timeout-minutes: (\d+)", read(".github", "workflows", "update-portwatch.yml")).group(1))
        # the limit is checked before a request and before a quota wait, so the last request starts by RUN_LIMIT_S and can last a connection and a
        # read, and no wait ends after the limit
        last = S.RUN_LIMIT_S + FP.PAUSE_S[1] + F.CONNECT_TIMEOUT + F.READ_TIMEOUT
        self.assertLess(last, step * 60 - 30)

    def test_the_usual_run_of_all_the_ports_fits_the_bound(self):
        n = len(P.port_ids())
        least, usual, most = P.weekly_request_bounds(n, TODAY, S.MAX_REQUESTS)
        self.assertLessEqual(usual, most)
        self.assertGreaterEqual(most - usual, 0)

    def test_a_port_without_a_file_costs_its_pages_and_one_check_and_the_run_never_asks_for_more_than_the_bound(self):
        ids = [f"port{n}" for n in range(1, 164)]
        today = date(2026, 12, 2)
        pages = P.pages((today - date.fromisoformat(P.HISTORY_FROM)).days + 1)
        for taken in (0, 5, 40, 120):
            docs = {k: v for k, v in self.docs(ids, today, lambda i: 0).items() if int(k[4:]) > taken}
            for bound in (S.MAX_REQUESTS, 12, 20, 30, 39, 42):
                pl = P.plan(ids, docs, set(), today, max_requests=bound)
                self.assertEqual(pl["requests"]["history"], len(pl["history"]) * (pages + P.FIRST_READ_CHECK))
                self.assertLessEqual(pl["requests"]["total"], bound, (taken, bound))
        # the cap is the room that is left over what a port costs: five ports fit with their checks in exactly this room, and with one request
        # less four do (five would have fitted without the check)
        docs = self.docs(ids, today, lambda i: 0)
        for k in list(docs)[:5]:
            del docs[k]
        full = P.plan(ids, docs, set(), today, max_requests=None)
        window_deep = full["requests"]["window"] + full["requests"]["deep"]
        room = window_deep + 5 * (pages + P.FIRST_READ_CHECK)
        self.assertEqual(len(P.plan(ids, docs, set(), today, max_requests=room)["history"]), 5)
        self.assertEqual(len(P.plan(ids, docs, set(), today, max_requests=room - 1)["history"]), 4)
        self.assertLessEqual(window_deep + 5 * pages, room - 1)
        # a sitting by hand and --full count the pages only: nothing is checked against a newer port for them
        self.assertEqual(P.plan(ids, {}, set(), today, backfill=True, max_ports=15)["requests"]["history"], 15 * pages)
        self.assertEqual(P.plan(ids, docs, set(), today, full=["port1", "port2"])["requests"]["history"], 2 * pages)


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def guide_section():
    """The port traffic section of docs/UPDATING.md, on one line."""
    guide = " ".join(read("docs", "UPDATING.md").split())
    i = guide.index("### Port traffic: the weekly step")
    return guide[i:guide.index("## Releasing", i)]


def iso_of(d):
    return d.isoformat()


# ------------------------------------------------------------------------------------------------ the script
class FirstLoad(Env):
    def test_dry_run_prints_the_plan_and_asks_for_nothing_and_writes_nothing(self):
        self.start()
        res = self.run_script("--dry-run", "--backfill", "--max-ports", "3")
        self.assertEqual(self.svc.calls, [])
        self.assertEqual(res["requests"], 0)
        self.assertFalse(os.path.exists(self.out))
        self.assertFalse(os.path.exists(status.UPDATES))
        self.assertIn("in full: 3 ports (port1, port2, port3)", self.output)
        self.assertIn("addresses of", self.output)
        self.assertEqual(self.sleeps, [])

    def test_a_sitting_reads_the_next_ports_writes_a_file_for_each_and_skips_them_the_next_time(self):
        self.start()
        res = self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 12))
        self.assertIsNone(res["error"])
        self.assertEqual(sorted(res["written"]), ["port1", "port2", "port3"])
        self.assertEqual(sorted(f for f in os.listdir(self.out)), ["index.json", "port1.json", "port2.json", "port3.json"])
        self.assertEqual(res["requests"], 3)                     # a year of days is one page
        for p in res["written"]:
            doc = self.read(p)
            self.assertEqual(P.validate_doc(doc, p, {"portwatch-port-traffic"}), [])
            self.assertEqual(doc["name"], Env.NAMES[int(p[4:]) - 1])
            self.assertEqual(doc["y"], "2026-11-08")
            doc_matches_recount(self, doc, self.rows(p))
        with open(os.path.join(self.out, "index.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"checked": "2026-11-12", "none": [], "pending": ["port4", "port5", "port6", "port7", "port8"]})
        res = self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 12))
        self.assertEqual(sorted(res["written"]), ["port4", "port5", "port6"])
        self.assertEqual(json.loads(self.tree()["index.json"])["pending"], ["port7", "port8"])
        res = self.run_script("--backfill", "--max-ports", "15", today=date(2026, 11, 12))
        self.assertEqual(sorted(res["written"]), ["port7", "port8"])
        self.assertEqual(json.loads(self.tree()["index.json"]), {"checked": "2026-11-12", "none": [], "pending": []})
        res = self.run_script("--backfill", "--max-ports", "15", today=date(2026, 11, 12))
        self.assertEqual((res["written"], res["requests"]), ([], 0))

    def test_a_sitting_prints_how_far_the_rounding_moves_the_sums_and_flags_what_the_rule_cannot_give(self):
        self.start(n_ports=2)
        self.run_script("--backfill", "--max-ports", "1", today=date(2026, 11, 12))
        self.assertRegex(self.output, r"rounding moves the 52-week sum of the four types by at most 0\.\d\d% \((exports|imports)\), of one type by at most 0\.\d\d%")
        self.assertNotIn("ROUNDING OVER", self.output)
        with mock.patch.object(P, "rounding_error", return_value=(0.006, "exports")):
            self.run_script("--backfill", "--max-ports", "1", today=date(2026, 11, 12))
        self.assertIn("ROUNDING OVER 0.5%", self.output)

    def test_the_full_history_of_a_port_takes_the_pages_the_plan_counts(self):
        self.start(n_ports=1, first=date(2019, 1, 1), last=date(2026, 11, 20))
        before = len(self.svc.calls)
        pl = P.plan(["port1"], {}, set(), TODAY, backfill=True)
        res = self.run_script("--backfill")
        self.assertEqual(len(self.svc.calls) - before, pl["requests"]["history"])
        self.assertEqual(res["requests"], 3)
        doc = self.read("port1")
        doc_matches_recount(self, doc, self.rows("port1"))
        self.assertEqual(doc["start"], "2019-01-07")

    def test_a_sitting_that_stops_leaves_an_index_that_lists_the_ports_not_read_yet(self):
        self.start(n_ports=5)
        self.svc.script = down()
        res = self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 12))
        self.assertIn("503", res["error"])
        self.assertEqual(sorted(self.tree()), ["index.json"])         # no file, and the folder says what is still to read
        self.assertEqual(json.loads(self.tree()["index.json"]), {"checked": "2026-11-12", "none": [], "pending": self.ports})
        self.svc.script = [None] + down()
        res = self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 12))
        self.assertEqual(sorted(self.tree()), ["index.json", "port1.json"])
        self.assertEqual(json.loads(self.tree()["index.json"])["pending"], ["port2", "port3", "port4", "port5"])

    def test_the_index_is_the_same_for_a_part_of_the_ports_as_for_all(self):
        self.start(n_ports=5)
        self.svc.table["port5"] = []
        self.run_script("--backfill", "--max-ports", "5", today=date(2026, 11, 12))
        self.assertEqual(json.loads(self.tree()["index.json"]), {"checked": "2026-11-12", "none": ["port5"], "pending": []})
        self.run_script("--full", "port2", "--ports", "port2", "port3", today=date(2026, 11, 13))
        index = json.loads(self.tree()["index.json"])
        self.assertEqual((index["none"], index["pending"]), (["port5"], []))      # the ports not asked for stay as they were

    def test_a_run_that_reads_nothing_leaves_the_index_byte_identical(self):
        self.start(n_ports=3)
        self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 12))
        before = self.tree()
        self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 20))
        self.assertEqual(self.tree(), before)

    def test_a_port_that_returns_nothing_gets_no_file_is_listed_and_is_not_asked_again_in_the_next_sitting(self):
        self.start()
        self.svc.table["port2"] = []
        res = self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 12))
        self.assertEqual(sorted(res["written"]), ["port1", "port3"])        # the sitting's three ports were port1, port2 and port3
        self.assertEqual(res["none"], ["port2"])
        self.assertFalse(os.path.exists(os.path.join(self.out, "port2.json")))
        with open(os.path.join(self.out, "index.json"), encoding="utf-8") as fh:
            index = json.load(fh)
        self.assertEqual((index["none"], index["pending"]), (["port2"], ["port4", "port5", "port6", "port7", "port8"]))
        n = len(self.svc.calls)
        res = self.run_script("--backfill", "--max-ports", "15", today=date(2026, 11, 12))
        self.assertNotIn("port2", res["written"])
        asked = {m for _, q in self.svc.calls[n:] for m in re.findall(r"'(port\d+)'", q["where"])}
        self.assertNotIn("port2", asked)
        self.assertEqual(res["none"], ["port2"])

    def test_a_hand_sitting_records_its_success_and_not_its_failure_a_weekly_run_records_both(self):
        self.start()
        self.run_script("--backfill", "--max-ports", "2", today=date(2026, 11, 12))
        e = status.get(S.SOURCE)
        self.assertEqual((e["records"], e["data_to"], e["consecutive_failures"]), (2, "2026-11-08", 0))
        self.assertEqual(e["state"]["mode"], "hand")
        self.svc.script = down()
        res = self.run_script("--backfill", "--max-ports", "2", today=date(2026, 11, 12))
        self.assertIn("503", res["error"])
        self.assertEqual(status.get(S.SOURCE)["consecutive_failures"], 0)       # a sitting that stops short is not a scheduled failure
        # the entry of the source exists (the sittings recorded their success): a weekly run that fails is recorded although six ports have
        # no file yet, so that a port that is not read yet cannot hide the failure of the source
        self.svc.script = down()
        res = self.run_script(today=date(2026, 11, 25))
        self.assertIn("503", res["error"])
        self.assertIn("failed, the previous files are kept", self.output)
        self.assertNotIn("not recorded", self.output)
        self.assertEqual(status.get(S.SOURCE)["consecutive_failures"], 1)
        self.assertIn("503", status.get(S.SOURCE)["last_error"])
        # and so it is once every port has a file (or no rows)
        self.run_script("--backfill", "--max-ports", "6", today=date(2026, 11, 12))
        self.svc.script = down()
        res = self.run_script(today=date(2026, 11, 25))
        self.assertIn("503", res["error"])
        self.assertNotIn("not recorded", self.output)
        self.assertEqual(status.get(S.SOURCE)["consecutive_failures"], 1)       # the sitting that succeeded began the count again
        self.assertIn("503", status.get(S.SOURCE)["last_error"])

    def test_a_scheduled_failure_is_recorded_except_while_no_run_has_succeeded_and_the_first_load_is_not_finished(self):
        self.start(n_ports=4)
        self.run_script("--backfill", "--max-ports", "2", today=date(2026, 11, 12))     # two files, two ports pending
        os.remove(os.path.join(self.tmp, "updates.json"))                                 # no entry of the source: no run has succeeded
        self.assertEqual(status.get(S.SOURCE), {})
        # no entry and a port not read yet: the load is still going on, the failure is printed and recorded nowhere
        self.svc.script = down()
        res = self.run_script(today=date(2026, 11, 25))
        self.assertIn("503", res["error"])
        self.assertIn("not recorded as a failure: the first load is not finished (2 ports have no file yet)", self.output)
        self.assertEqual(status.get(S.SOURCE), {})
        self.assertFalse(os.path.exists(status.UPDATES))
        # no entry, every port accounted for: the first scheduled runs are recorded (the source is retrying until the third)
        self.run_script("--backfill", "--max-ports", "2", today=date(2026, 11, 12))
        os.remove(os.path.join(self.tmp, "updates.json"))
        self.svc.script = down()
        res = self.run_script(today=date(2026, 11, 25))
        self.assertNotIn("not recorded", self.output)
        e = status.get(S.SOURCE)
        self.assertEqual((e["consecutive_failures"], e["last_success"]), (1, None))
        # an entry that holds a success, and a port that is not read yet (an asset added since): the failure is recorded all the same
        self.run_script("--backfill", "--max-ports", "4", today=date(2026, 11, 12))
        self.assertTrue(status.get(S.SOURCE)["last_success"])
        os.remove(os.path.join(self.out, "port4.json"))
        self.svc.script = down()
        res = self.run_script(today=date(2026, 11, 25))
        self.assertIn("503", res["error"])
        self.assertNotIn("not recorded", self.output)
        self.assertEqual(status.get(S.SOURCE)["consecutive_failures"], 1)
        self.assertIn("503", status.get(S.SOURCE)["last_error"])

    def test_a_weekly_run_that_fails_before_the_first_sitting_leaves_no_entry_in_the_status(self):
        self.start()
        self.svc.script = down()
        res = self.run_script(today=date(2026, 11, 25))
        self.assertIn("503", res["error"])
        self.assertEqual(status.get(S.SOURCE), {})
        self.assertFalse(os.path.exists(status.UPDATES))
        # a port that returned no rows is accounted for: with it, the folder is complete and the failure is recorded
        self.svc.table["port1"] = []
        self.run_script("--backfill", "--max-ports", "8", today=date(2026, 11, 12))
        self.assertEqual(status.get(S.SOURCE)["state"]["none"], 1)
        self.svc.script = down()
        self.run_script(today=date(2026, 11, 25))
        self.assertEqual(status.get(S.SOURCE)["consecutive_failures"], 1)

    def test_a_first_scheduled_run_that_fails_opens_no_issue_and_shows_no_stale_row(self):
        """The entry of the source is recorded by the first scheduled run and by nothing else: here the sittings left none (the files of the
        load are in the folder, the status files were put back). The run fails; the staleness check (Mondays) and the alert step of the
        finish action see a source that is retrying."""
        self.start(n_ports=3)
        self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 12))
        for f in ("updates.json", "log.jsonl"):
            os.remove(os.path.join(self.tmp, f))
        self.assertEqual(status.get(S.SOURCE), {})
        now = datetime(2026, 11, 30, 13, 37, tzinfo=timezone.utc)      # the Monday after the Wednesday run
        self.assertEqual(ST.check(status.load(), now=now), {"stale": {}, "fresh": []})
        for n in (1, 2):
            self.svc.script = down()
            self.run_script(today=date(2026, 11, 25))
            e = status.get(S.SOURCE)
            self.assertEqual((e["consecutive_failures"], e["last_success"]), (n, None))
            self.assertEqual(status.failing(), {}, "the alert step opens its issue at the third run in a row, not before")
            self.assertEqual(ST.check(status.load(), now=now), {"stale": {}, "fresh": [S.SOURCE]}, "retrying, not stale")
        self.svc.script = down()
        self.run_script(today=date(2026, 11, 25))
        self.assertEqual(list(status.failing()), [S.SOURCE])
        self.assertIn(S.SOURCE, ST.check(status.load(), now=now)["stale"])        # and then both say so
        # a first run that fails while ports are still pending records nothing at all
        self.start(n_ports=3)
        self.run_script("--backfill", "--max-ports", "2", today=date(2026, 11, 12))
        os.remove(os.path.join(self.tmp, "updates.json"))
        self.svc.script = down()
        self.run_script(today=date(2026, 11, 25))
        self.assertEqual(status.get(S.SOURCE), {})
        self.assertEqual(ST.check(status.load(), now=now), {"stale": {}, "fresh": []})
        # the first run that succeeds records the entry, fresh
        self.svc.script = []
        self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 25))
        e = status.get(S.SOURCE)
        self.assertEqual(e["consecutive_failures"], 0)
        self.assertEqual(ST.check(status.load(), now=datetime(2026, 11, 26, tzinfo=timezone.utc))["stale"], {})


class PartOfThePorts(Env):
    def test_a_run_on_a_few_ports_writes_their_files_and_sets_no_count_in_the_status(self):
        self.start(n_ports=6)
        res = self.run_script("--backfill", "--ports", "port2", "port3", today=date(2026, 11, 12))
        self.assertEqual(sorted(res["written"]), ["port2", "port3"])
        self.assertFalse(os.path.exists(status.UPDATES))
        res = self.run_script("--backfill", "--limit", "1", today=date(2026, 11, 12))
        self.assertEqual(res["written"], ["port1"])
        self.assertFalse(os.path.exists(status.UPDATES))
        res = self.run_script("--ports", "port99", today=date(2026, 11, 12))
        self.assertEqual(res["error"], "unknown port")


class WeeklyRun(Env):
    def setUp(self):
        super().setUp()
        self.start(n_ports=8)
        self.run_script("--backfill", "--max-ports", "8", today=date(2026, 11, 12))
        self.before = self.tree()
        self.assertEqual(len(self.read("port1")["calls"]["tanker"]) > 40, True)

    def extend(self, last, change=None, deep_only=None):
        """The table grows to ``last``; ``change`` {date: tonnes} revises dry-bulk exports of every port."""
        table = make_table(self.ports, date(2025, 11, 3), last)
        oid = 10 ** 6
        for p, rows in table.items():
            for r in rows:
                if change and r["date"] in change:
                    r["export_dry_bulk"] += change[r["date"]]
                oid += 1
                r["_oid"] = oid
        self.svc.table = table

    def test_the_weekly_run_reads_recent_weeks_extends_the_files_and_leaves_older_weeks_alone(self):
        today = date(2026, 11, 25)
        pl = P.plan(self.ports, {p: self.read(p) for p in self.ports}, set(), today)
        deep = {p for g in pl["deep"] for p in g["ports"]}
        window = {p for g in pl["window"] for p in g["ports"]}
        self.assertTrue(deep and window)
        # revised: a day inside the six weeks (all ports) and a day far older (only the deep pass can see it)
        self.extend(date(2026, 11, 20), change={"2026-10-21": 9000, "2026-03-04": 9000})
        asked = len(self.svc.calls)
        res = self.run_script(today=today)
        self.assertIsNone(res["error"])
        self.assertEqual(sorted(res["written"]), self.ports)
        self.assertEqual(res["requests"], len(self.svc.calls) - asked)
        for p in self.ports:
            old, doc = json.loads(self.before[f"{p}.json"]), self.read(p)
            rows = self.rows(p)
            self.assertEqual(len(doc["calls"]["tanker"]), len(old["calls"]["tanker"]) + 1)     # the week of 9 November (the 16th is partial)
            self.assertEqual(doc["y"], "2026-11-20")
            self.assertEqual(doc["start"], old["start"])
            i_in = (date(2026, 10, 19) - date.fromisoformat(doc["start"])).days // 7
            i_old = (date(2026, 3, 2) - date.fromisoformat(doc["start"])).days // 7
            self.assertEqual(doc["exports"]["dry"][i_in], half_up(recount(rows)["2026-10-19"]["exports"][1]))
            self.assertNotEqual(doc["exports"]["dry"][i_in], old["exports"]["dry"][i_in], "the revision inside the window must be taken")
            if p in deep:
                self.assertEqual(doc["exports"]["dry"][i_old], half_up(recount(rows)["2026-03-02"]["exports"][1]))
            else:
                self.assertEqual(doc["exports"]["dry"][i_old], old["exports"]["dry"][i_old], "a week older than the window changed")
            cut = (P.window_since(old) - date.fromisoformat(old["start"])).days // 7
            if p not in deep:
                for k in ("calls", "exports", "imports"):
                    for t in ("tanker", "dry", "container", "other"):
                        self.assertEqual(json.dumps(doc[k][t][:cut]), json.dumps(old[k][t][:cut]))
            self.assertEqual(P.validate_doc(doc, p, {"portwatch-port-traffic"}), [])
        self.assertEqual(status.get(S.SOURCE)["data_to"], "2026-11-20")
        self.assertEqual(status.get(S.SOURCE)["state"]["mode"], "weekly")

    def test_what_a_weekly_run_writes_passes_the_data_guard_of_the_job_and_is_the_most_it_may_change(self):
        """The guard (web/scripts/guard-data.mjs) compares the job's files with the last commit: the weeks that a run rewrites (the window and the
        deep pass of the quarter) are inside what it lets through, and one week more than the deep pass reads is not."""
        if not NODE:
            self.skipTest("node is not installed")
        today = date(2026, 11, 25)
        self.start(n_ports=4, first=date(2024, 1, 1))                   # two and a half years of weeks: older than the deep pass reads
        self.run_script("--backfill", "--max-ports", "4", today=date(2026, 11, 12))
        self.before = self.tree()
        table = make_table(self.ports, date(2024, 1, 1), date(2026, 11, 20))
        for rows in table.values():
            for r in rows:
                if r["date"] in ("2026-10-21", "2026-03-04"):
                    r["export_dry_bulk"] += 9000
        self.svc.table = table
        res = self.run_script(today=today)
        self.assertIsNone(res["error"])
        after = self.tree()
        self.assertNotEqual(after, self.before)
        repo = os.path.join(self.tmp, "repo")
        git = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)   # noqa: E731
        os.makedirs(os.path.join(repo, "data", "freight", "port-traffic"))
        os.makedirs(os.path.join(repo, "web", "scripts"))
        shutil.copy(os.path.join(ROOT, "web", "scripts", "guard-data.mjs"), os.path.join(repo, "web", "scripts", "guard-data.mjs"))
        git("init", "-q")
        git("config", "user.email", "t@example.invalid")
        git("config", "user.name", "t")
        git("config", "commit.gpgsign", "false")

        def put(tree):
            for f, b in tree.items():
                with open(os.path.join(repo, "data", "freight", "port-traffic", f), "wb") as fh:
                    fh.write(b)

        def guard(*env):
            return subprocess.run([NODE, os.path.join(repo, "web", "scripts", "guard-data.mjs"), "data/freight/port-traffic"], cwd=repo,
                                  capture_output=True, text=True)
        put(self.before)
        git("add", "-A")
        git("commit", "-q", "-m", "first load")
        put(after)
        r = guard()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # a run that rewrote one week older than the deep pass reads is refused
        doc = json.loads(after["port1.json"])
        old = json.loads(self.before["port1.json"])
        cut = (P.deep_since(old) - date.fromisoformat(old["start"])).days // 7
        self.assertGreater(cut, 3)
        doc["calls"]["tanker"][cut - 1] += 1
        put({"port1.json": json.dumps(doc, separators=(",", ":")).encode()})
        r = guard()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("port1.json", r.stderr)
        self.assertIn("older than the 52 weeks", r.stderr)

    def test_the_weeks_the_guard_lets_a_run_rewrite_are_the_weeks_the_script_reads(self):
        guard = read("web", "scripts", "guard-data.mjs")
        self.assertIn(f"PORT_DEEP_WEEKS = {P.DEEP_WEEKS};", guard)

    def test_a_second_run_leaves_every_file_byte_identical(self):
        today = date(2026, 11, 25)
        self.extend(date(2026, 11, 20))
        self.run_script(today=today)
        first = self.tree()
        res = self.run_script(today=today)
        self.assertEqual(res["written"], [])
        self.assertEqual(sorted(res["unchanged"]), self.ports)
        self.assertEqual(self.tree(), first)

    def test_the_requests_follow_the_plan_in_chunks_and_pages(self):
        today = date(2026, 11, 25)
        self.extend(date(2026, 11, 20))
        docs = {p: self.read(p) for p in self.ports}
        pl = P.plan(self.ports, docs, set(), today)
        n = len(self.svc.calls)
        res = self.run_script(today=today)
        self.assertEqual(res["requests"], len(self.svc.calls) - n)
        self.assertLessEqual(res["requests"], pl["requests"]["total"])
        # one request for the window ports, and one for each page of the deep ports (the rows of a year come on one page of 1,000
        # only for a few ports)
        asked = [q["where"] for _, q in self.svc.calls[n:]]
        self.assertEqual(sum(1 for w in asked if w.startswith("portid IN")), res["requests"])
        for _, q in self.svc.calls[n:]:
            self.assertLessEqual(len(P.address(q["where"])), P.MAX_ADDRESS)

    def test_one_port_that_returns_nothing_is_kept_and_counted_and_two_of_twelve_stop_the_run(self):
        self.start(n_ports=12)
        self.run_script("--backfill", "--max-ports", "12", today=date(2026, 11, 12))
        before = self.tree()
        self.extend(date(2026, 11, 20))
        self.svc.table["port5"] = []
        res = self.run_script(today=date(2026, 11, 25))
        self.assertIsNone(res["error"])
        self.assertEqual([p for p, _ in res["skipped"]], ["port5"])
        self.assertEqual(json.loads(before["port5.json"]), self.read("port5"))
        self.assertEqual(status.get(S.SOURCE)["state"]["skipped"], 1)
        self.svc.table["port6"] = []
        snapshot = self.tree()
        res = self.run_script(today=date(2026, 11, 25))
        self.assertIsNotNone(res["error"])          # two ports with no rows are also more than a tenth of the rows missing
        self.assertEqual(self.tree(), snapshot)

    def test_more_than_a_tenth_of_the_ports_skipped_for_any_reason_stops_the_run(self):
        self.start(n_ports=12)
        self.run_script("--backfill", "--max-ports", "12", today=date(2026, 11, 12))
        self.extend(date(2026, 11, 20))
        real = P.check_merge
        snapshot = self.tree()
        with mock.patch.object(P, "check_merge", lambda old, new, since: "forced" if old["id"] in ("port5", "port6") else real(old, new, since)):
            res = self.run_script(today=date(2026, 11, 25))
        self.assertIn("2 of 12 ports skipped", res["error"])
        self.assertEqual(self.tree(), snapshot)
        with mock.patch.object(P, "check_merge", lambda old, new, since: "forced" if old["id"] == "port5" else real(old, new, since)):
            res = self.run_script(today=date(2026, 11, 25))
        self.assertIsNone(res["error"])
        self.assertEqual(res["skipped"], [("port5", "forced")])

    def test_each_refusal_leaves_the_files_byte_identical_records_a_failure_and_exits_without_raising(self):
        today = date(2026, 11, 25)
        self.extend(date(2026, 11, 20))
        features = {"features": [{"attributes": {k: 0 for k in P.ASK_FIELDS}}]}
        broken = {"features": [{"attributes": {k: 0 for k in P.ASK_FIELDS if k != "export_tanker"}}]}
        text = {"features": [{"attributes": {**{k: 0 for k in P.ASK_FIELDS}, "import_roro": "12"}}]}
        cases = [
            ("service error body", [F.FetchError("service error: Cannot perform query")] * S.ATTEMPTS, "service error"),
            ("service down", down(), "503"),
            ("quota twice", [F.FetchError("service error: API calls quota exceeded (10446 request units). Retry after 60 sec."),
                             F.FetchError("service error: API calls quota exceeded (10446 request units). Retry after 60 sec.")], "quota"),
            ("a page without features", [{"error": None}], "page without features"),
            ("a missing field", [broken], "missing export_tanker"),
            ("a value that is not a number", [text], "not a number in import_roro"),
            ("a row of a port not asked for", [{"features": [{"attributes": {**{k: 0 for k in P.ASK_FIELDS}, "portid": "port99"}}]}], "not asked for"),
        ]
        self.assertTrue(features)
        for name, script, msg in cases:
            n_fail = status.get(S.SOURCE).get("consecutive_failures", 0)
            self.svc.script = list(script)
            self.sleeps.clear()
            snapshot = self.tree()
            res = self.run_script(today=today)
            self.assertIsNotNone(res["error"], name)
            self.assertIn(msg, res["error"], name)
            self.assertEqual(self.tree(), snapshot, f"{name}: a file changed")
            self.assertEqual(status.get(S.SOURCE)["consecutive_failures"], n_fail + 1, name)
            self.assertIn(msg, status.get(S.SOURCE)["last_error"], name)

    def test_a_quota_answer_is_waited_out_once_and_the_request_is_repeated(self):
        today = date(2026, 11, 25)
        self.extend(date(2026, 11, 20))
        self.svc.script = [F.FetchError("service error: API calls quota exceeded (10446 request units). Retry after 60 sec.")]
        res = self.run_script(today=today)
        self.assertIsNone(res["error"])
        self.assertIn(S.QUOTA_WAIT_S, self.sleeps)
        self.assertEqual(self.sleeps.count(S.QUOTA_WAIT_S), 1)
        self.assertGreaterEqual(S.QUOTA_WAIT_S, 60)
        w = [q["where"] for _, q in self.svc.calls[-res["requests"] - 1:]]
        self.assertEqual(w[0], w[1])         # the refused request, asked again
        self.assertEqual(len(res["written"]), 8)

    def test_fewer_rows_than_ninety_per_cent_of_what_is_expected_refuses_the_whole_run(self):
        self.extend(date(2026, 11, 20))
        self.svc.hook = lambda rows, q: [r for i, r in enumerate(rows) if i % 3]
        snapshot = self.tree()
        res = self.run_script(today=date(2026, 11, 25))
        self.assertIn("rows of the", res["error"])
        self.assertEqual(self.tree(), snapshot)

    def test_a_table_that_ends_earlier_than_at_the_last_run_is_refused(self):
        self.extend(date(2026, 11, 20))
        self.run_script(today=date(2026, 11, 25))
        self.assertEqual(status.get(S.SOURCE)["data_to"], "2026-11-20")
        self.extend(date(2026, 11, 15))
        snapshot = self.tree()
        res = self.run_script(today=date(2026, 11, 25))
        self.assertIn("earlier than at the last run", res["error"])
        self.assertEqual(self.tree(), snapshot)

    def test_history_that_PortWatch_re_estimated_is_refused_and_says_to_run_full(self):
        today = date(2026, 11, 25)
        self.extend(date(2026, 11, 20))
        old_rows = self.svc.table

        def doubled(rows, q):
            return [{**r, **{f: r[f] * 2 for f in P.ASK_FIELDS[2:] if f.startswith("export_") or f.startswith("import_")}}
                    if r["date"] < "2026-09-01" else r for r in rows]
        self.svc.hook = doubled
        snapshot = self.tree()
        res = self.run_script(today=today)
        self.assertIn("history revised", res["error"])
        self.assertIn("run --full", res["error"])
        self.assertEqual(self.tree(), snapshot)
        self.assertTrue(old_rows)
        # a revision of the recent days only is the ordinary case and goes through
        self.svc.hook = lambda rows, q: [{**r, "export_dry_bulk": r["export_dry_bulk"] + 5000} if r["date"] >= "2026-10-05" else r for r in rows]
        self.assertIsNone(self.run_script(today=today)["error"])

    def test_a_weekly_run_stops_when_it_has_used_its_time_and_a_hand_sitting_does_not(self):
        self.extend(date(2026, 11, 20))
        clock = [0.0]

        def tick():
            clock[0] += S.RUN_LIMIT_S * 0.6
            return clock[0]
        snapshot = self.tree()
        with mock.patch.object(S.time, "monotonic", tick):
            res = self.run_script(today=date(2026, 11, 25))
        self.assertIn("seconds", res["error"])
        self.assertEqual(self.tree(), snapshot)
        clock[0] = 0.0
        with mock.patch.object(S.time, "monotonic", tick):
            res = self.run_script("--ports", "port1", "port2", today=date(2026, 11, 25))
        self.assertIsNone(res["error"])

    def test_a_folder_over_the_size_stop_is_refused(self):
        self.extend(date(2026, 11, 20))
        snapshot = self.tree()
        with mock.patch.object(P, "SIZE_STOP_KB", 1):
            res = self.run_script(today=date(2026, 11, 25))
        self.assertIn("over the 1 kB stop", res["error"])
        self.assertEqual(self.tree(), snapshot)

    def test_a_sitting_stops_at_the_size_stop_and_keeps_the_files_it_has(self):
        self.start(n_ports=8)
        self.run_script("--backfill", "--max-ports", "1", today=date(2026, 11, 12))
        one = os.path.getsize(os.path.join(self.out, "port1.json"))
        with mock.patch.object(P, "SIZE_STOP_KB", math.ceil(one * 2.5 / 1000)):
            res = self.run_script("--backfill", "--max-ports", "8", today=date(2026, 11, 12))
        self.assertIn("kB stop", res["stopped"])
        self.assertEqual(len([f for f in os.listdir(self.out) if f.startswith("port")]), 2)

    def test_full_replaces_a_file_with_the_history_read_again(self):
        self.svc.table["port3"] = [dict(r, export_dry_bulk=r["export_dry_bulk"] + 50_000) for r in self.svc.table["port3"]]
        res = self.run_script("--full", "port3", today=date(2026, 11, 12))
        self.assertEqual(res["written"], ["port3"])
        doc_matches_recount(self, self.read("port3"), self.rows("port3"))
        self.assertEqual(self.read("port4"), json.loads(self.before["port4.json"]))
        res = self.run_script("--full", "port99", today=date(2026, 11, 12))
        self.assertEqual(res["error"], "unknown port")

    def test_a_file_that_is_not_valid_is_read_again_in_full(self):
        with open(os.path.join(self.out, "port2.json"), "w") as fh:
            fh.write('{"id":"port2"}')
        res = self.run_script(today=date(2026, 11, 12))
        self.assertIn("port2.json is not a valid port file", self.output)
        self.assertIn("port2", res["written"])
        self.assertEqual(P.validate_doc(self.read("port2"), "port2"), [])


class WeeklyCap(Env):
    """The script gives the plan its bound: a run whose files are late asks for no more than that, leaves the rest to the next run, and says so."""

    def test_a_run_over_files_that_are_late_keeps_to_the_bound_and_the_next_runs_catch_up(self):
        self.start(n_ports=8, first=date(2024, 1, 1), last=date(2026, 3, 1))
        self.run_script("--backfill", "--max-ports", "8", today=date(2026, 3, 9))           # the files end in the last week of February
        self.svc.table = make_table(self.ports, date(2024, 1, 1), date(2026, 11, 20))
        before = {p: self.read(p)["y"] for p in self.ports}
        asked, deferred = [], []
        with mock.patch.object(S, "MAX_REQUESTS", 3), mock.patch.object(P.chunks, "__defaults__", (3, P.MAX_ADDRESS)):
            for week in range(8):
                n = len(self.svc.calls)
                res = self.run_script(today=date(2026, 11, 25) + timedelta(weeks=week))
                self.assertIsNone(res["error"])
                asked.append(len(self.svc.calls) - n)
                deferred.append(len(res["deferred"]))
                self.assertEqual(status.get(S.SOURCE)["state"]["deferred"], len(res["deferred"]))
                if not res["deferred"]:
                    break
        self.assertTrue(all(a <= 3 for a in asked), asked)
        self.assertGreater(deferred[0], 0, "the first run could not read every file in three requests")
        self.assertEqual(deferred[-1], 0, f"the ports left to the next run are read within a few weeks: {deferred}")
        for p in self.ports:
            self.assertGreater(self.read(p)["y"], before[p])


class FirstLoadInAWeeklyRun(Env):
    """Ports without a file that the weekly run reads in full and finds late: the requests of the run stay inside the bound the plan was given."""

    def late_ports(self):
        """Fourteen ports, the first nine of the fixed order (the ids as text) loaded by a sitting, the last five late in the service itself."""
        self.start(n_ports=14, first=date(2019, 1, 1))        # a port holds three pages of rows, as the plan counts a first read
        self.order = sorted(self.ports)
        self.run_script("--backfill", "--max-ports", "9", today=date(2026, 11, 12))
        for p in self.order[9:]:         # five ports whose rows end five weeks before the others
            self.svc.table[p] = [r for r in self.svc.table[p] if r["date"] <= "2026-10-04"]

    def cut_first_read(self, port, last_day):
        self.svc.hook = lambda rows, params: rows if " AND date >" in params["where"] else [
            r for r in rows if r["portid"] != port or r["date"] <= last_day]

    def test_five_late_ports_to_load_in_a_scheduled_run_ask_for_no_more_than_the_plan_was_given(self):
        self.late_ports()
        today = date(2026, 11, 12)
        have = {p: self.read(p) for p in self.order[:9]}
        kept = P.plan(self.order[:9], have, set(), today)["requests"]
        pages = P.pages((today - date.fromisoformat(P.HISTORY_FROM)).days + 1)
        bound = kept["window"] + kept["deep"] + 5 * pages + 4           # five ports and their pages fit, five ports and their checks do not
        with mock.patch.object(S, "MAX_REQUESTS", bound):
            res = self.run_script(today=today)
        self.assertIsNone(res["error"])
        loaded = [p for p in res["written"] if p in self.order[9:]]
        self.assertEqual(len(loaded), 4, "the plan counts the check of each port: four fit")
        self.assertEqual(res["requests"], kept["window"] + kept["deep"] + 4 * (pages + 1))
        self.assertLessEqual(res["requests"], bound)
        self.assertEqual(self.output.count("the service has no row of this port"), 4)
        # with the room of five ports and their checks, five are read, and the run asks for exactly the bound
        self.late_ports()
        with mock.patch.object(S, "MAX_REQUESTS", bound + 1):
            res = self.run_script(today=today)
        self.assertEqual(len([p for p in res["written"] if p in self.order[9:]]), 5)
        self.assertEqual(res["requests"], bound + 1)

    def test_the_check_of_a_late_port_is_one_request_whatever_the_service_answers(self):
        self.late_ports()
        # the service holds many rows after the day the first read stopped: the check still asks one page
        reader = S.Reader()
        self.svc.table["port10"] = make_table(["port10"], date(2026, 10, 5), date(2026, 10, 5) + timedelta(days=2 * P.PAGE))["port10"]
        before = len(self.svc.calls)
        self.assertFalse(S.ends_here(reader, "port10", "2026-10-04"))
        self.assertEqual(len(self.svc.calls) - before, 1)
        self.assertTrue(S.ends_here(reader, "port5", "2026-10-04"))
        self.assertEqual(len(self.svc.calls) - before, 2)

    def test_a_port_written_before_a_newer_one_and_not_judged_in_time_is_taken_back_and_the_port_stays_where_it_was(self):
        # a new port: the folder ends as it was before the port was read, the port pending
        self.start(n_ports=3)
        self.cut_first_read("port1", "2026-10-11")
        before = self.tree()
        with mock.patch.object(S, "ends_here", side_effect=S.TimeUp("the run used its 720 seconds")):
            res = self.run_script(today=date(2026, 11, 12))
        self.assertEqual(res["written"], ["port2", "port3"])
        self.assertIn("720 seconds", res["stopped"])
        self.assertEqual(sorted(f for f in os.listdir(self.out)), ["index.json", "port2.json", "port3.json"])
        self.assertEqual(json.loads(self.tree()["index.json"])["pending"], ["port1"])
        self.assertIn("port1 Alpha: its last week starts 2026-10-05, the newest 2026-11-02, and it could not be checked: its file is removed, "
                      "the port stays pending", self.output)
        self.assertNotIn("port1.json.tmp", " ".join(os.listdir(self.out)))
        # the run is not a failure: the next one reads the port again
        self.svc.hook = None
        res = self.run_script(today=date(2026, 11, 19))
        self.assertIn("port1", res["written"])
        self.assertEqual(json.loads(self.tree()["index.json"])["pending"], [])

    def test_a_port_that_returned_no_rows_and_is_read_again_goes_back_to_the_list_of_those_when_it_is_taken_back(self):
        self.start(n_ports=5)
        for p in self.ports:
            self.svc.table[p] = []
        self.run_script("--backfill", "--max-ports", "5", today=date(2026, 11, 12))
        self.assertEqual(json.loads(self.tree()["index.json"])["none"], self.ports)
        full = make_table(self.ports, date(2025, 11, 3), date(2026, 11, 8))
        self.svc.table = {**full, "port1": [r for r in full["port1"] if r["date"] <= "2026-10-11"]}
        today = next(date(2026, 11, 12) + timedelta(weeks=w) for w in range(4) if P.week_index(date(2026, 11, 12) + timedelta(weeks=w)) % P.QUARTERS == 0)
        # ports 1 and 5 are asked again in this week of the quarter: port 1 is read first, port 5 is the newer
        self.svc.hook = lambda rows, params: rows if " AND date >" in params["where"] else [r for r in rows if r["portid"] != "port1" or r["date"] <= "2026-10-11"]
        with mock.patch.object(S, "ends_here", side_effect=S.TimeUp("the run used its 720 seconds")):
            res = self.run_script(today=today)
        self.assertEqual(res["written"], ["port5"])
        index = json.loads(self.tree()["index.json"])
        self.assertEqual((index["none"], index["pending"]), (["port1", "port2", "port3", "port4"], []))
        self.assertEqual(sorted(f for f in os.listdir(self.out)), ["index.json", "port5.json"])
        self.assertIn("the port stays in the list of the ports with no rows", self.output)


class SizeStop(Env):
    """The size stop is the owner's figure; the run says plainly, from 90% of it, how near it is and when it would be reached."""

    def setUp(self):
        super().setUp()
        self.start(n_ports=8)
        self.run_script("--backfill", "--max-ports", "8", today=date(2026, 11, 12))
        self.svc.table = make_table(self.ports, date(2025, 11, 3), date(2026, 11, 20))
        self.total = sum(len(b) for f, b in self.tree().items() if f.startswith("port"))

    def stop_for(self, share):
        """The stop in kB that makes the folder as it now is ``share`` of it."""
        return self.total / 1000 / share

    def test_below_ninety_per_cent_the_summary_says_nothing_of_the_stop(self):
        with mock.patch.object(P, "SIZE_STOP_KB", self.stop_for(0.85)):
            res = self.run_script(today=date(2026, 11, 25))
        self.assertIsNone(res["error"])
        self.assertIsNone(res["size_warning"])
        self.assertNotIn("WARNING", self.output)
        self.assertNotIn("stop is reached", self.output)
        self.assertNotIn("; the folder", status.get(S.SOURCE)["last_error"] or "")
        self.assertIn("size_kb", status.get(S.SOURCE)["state"])

    def test_from_ninety_per_cent_the_run_warns_in_its_summary_and_in_the_status_and_still_writes(self):
        with mock.patch.object(P, "SIZE_STOP_KB", self.stop_for(0.93)):
            res = self.run_script(today=date(2026, 11, 25))
        self.assertIsNone(res["error"])
        self.assertTrue(res["written"])
        w = res["size_warning"]
        self.assertRegex(w, r"^the folder of the port files holds \d+ kB, 9\d% of its \d+ kB stop; it grows by about [\d.]+ kB a week, "
                            r"so the stop is reached in about \d+ weeks \(the week of 20\d\d-\d\d-\d\d\); from there a weekly run refuses everything")
        self.assertIn("WARNING: " + w, self.output)
        e = status.get(S.SOURCE)
        self.assertIsNone(e["last_error"])
        self.assertEqual(e["consecutive_failures"], 0)
        with open(status.LOG, encoding="utf-8") as fh:
            self.assertIn("the stop is reached in about", fh.read().splitlines()[-1])
        # as a GitHub warning when the run is one
        with mock.patch.object(P, "SIZE_STOP_KB", self.stop_for(0.93)), mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            self.run_script(today=date(2026, 11, 25))
        self.assertIn("::warning::the folder of the port files holds", self.output)

    def test_the_weeks_left_are_the_room_over_the_growth_of_a_week(self):
        docs = {p: self.read(p) for p in self.ports}
        total = sum(len(b) for f, b in self.tree().items() if f.startswith("port"))
        weeks = sum(len(d["calls"]["tanker"]) for d in docs.values())
        a_week = total / weeks * len(docs)
        stop_kb = total / 0.95 / 1000
        share, msg = P.size_note(total, docs, date(2026, 11, 25), stop_kb)
        self.assertAlmostEqual(share, 0.95, places=3)
        n = math.ceil((stop_kb * 1000 - total) / a_week)
        self.assertIn(f"in about {n} weeks (the week of {(P.monday(date(2026, 11, 25)) + timedelta(weeks=n)).isoformat()})", msg)
        self.assertIn(f"it grows by about {a_week / 1000:.1f} kB a week", msg)
        # at and over the stop: it says so and gives no date
        share, msg = P.size_note(total, docs, date(2026, 11, 25), total / 1000)
        self.assertIn("and the stop is reached; from there", msg)

    def test_at_the_stop_a_weekly_run_still_refuses_everything_and_records_a_failure(self):
        before = self.tree()
        with mock.patch.object(P, "SIZE_STOP_KB", self.stop_for(1.0) - 1):
            res = self.run_script(today=date(2026, 11, 25))
        self.assertIn("kB stop", res["error"])
        self.assertEqual(self.tree(), before)
        self.assertEqual(status.get(S.SOURCE)["consecutive_failures"], 1)

    def test_the_stop_and_the_share_are_the_ones_the_documentation_gives(self):
        self.assertEqual((P.SIZE_STOP_KB, P.SIZE_WARN_SHARE), (3500, 0.9))
        section = guide_section()
        self.assertIn(f"The folder may not exceed {P.SIZE_STOP_KB:,} kB", section)
        self.assertIn(f"From {int(P.SIZE_WARN_SHARE * 100)}% of it ({int(P.SIZE_STOP_KB * P.SIZE_WARN_SHARE):,} kB)", section)


class WindowMergeBySize(Env):
    """Six ports whose weekly tonnages are of every size the rule knows (from a few tonnes to hundreds of thousands), loaded
    in full, then a weekly run that reads the window again: the older weeks are the same bytes, the weeks of the window and the
    new ones are what the rule gives their size, the file never carries a precision of its own for a later week to inherit."""

    FACTORS = [0.0005, 0.005, 0.05, 0.5, 5, 50]

    def table(self, last, change=None):
        table = make_table(self.ports, date(2025, 11, 3), last)
        for f, (p, rows) in zip(self.FACTORS, table.items()):
            for r in rows:
                for k in P.ASK_FIELDS[2:]:
                    if k.startswith(("import_", "export_")):
                        r[k] = round(r[k] * f)
                if change and r["date"] in change:
                    r["export_dry_bulk"] += round(change[r["date"]] * f)
        return table

    def test_the_window_merge_keeps_older_weeks_byte_for_byte_and_gives_the_weeks_of_the_window_the_rule(self):
        self.start(n_ports=6)
        self.svc.table = self.table(date(2026, 11, 8))
        self.run_script("--backfill", "--max-ports", "6", today=date(2026, 11, 12))
        before = {p: self.read(p) for p in self.ports}
        sizes = {p: {len(repr(v).split(".")[-1]) if isinstance(v, float) else 0 for k in ("exports", "imports") for t in d[k] for v in d[k][t] if v}
                 for p, d in before.items()}
        self.assertEqual([max(sizes[p]) for p in self.ports], [3, 3, 2, 1, 0, 0])   # to the tonne for the smallest port, whole kt for the largest
        for p, d in before.items():
            doc_matches_recount(self, d, self.rows(p))
            self.assertEqual(P.validate_doc(d, p), [])
        self.svc.table = self.table(date(2026, 11, 20), change={"2026-10-21": 90000, "2026-03-04": 90000})
        pl = P.plan(self.ports, before, set(), date(2026, 11, 25))
        deep = {p for g in pl["deep"] for p in g["ports"]}
        self.assertTrue(deep and len(deep) < 6)
        res = self.run_script(today=date(2026, 11, 25))
        self.assertIsNone(res["error"])
        for p in self.ports:
            old, doc = before[p], self.read(p)
            cut = ((P.deep_since if p in deep else P.window_since)(old) - date.fromisoformat(old["start"])).days // 7
            for k in ("calls", "exports", "imports"):
                for t in ("tanker", "dry", "container", "other"):
                    self.assertEqual(json.dumps(doc[k][t][:cut]), json.dumps(old[k][t][:cut]), f"{p} {k} {t}: a week before the window changed")
            self.assertEqual(len(doc["calls"]["tanker"]), len(old["calls"]["tanker"]) + 1)
            want = recount(self.rows(p))
            start = date.fromisoformat(doc["start"])
            for i in range(cut, len(doc["calls"]["tanker"])):
                m = (start + timedelta(weeks=i)).isoformat()
                for j, t in enumerate(("tanker", "dry", "container", "other")):
                    for k in ("exports", "imports"):
                        self.assertEqual(doc[k][t][i], half_up(want[m][k][j]), f"{p} {m} {k} {t}")
            self.assertEqual(doc["dp"], P.MAX_DECIMALS)
            self.assertEqual(P.validate_doc(doc, p, {"portwatch-port-traffic"}), [])
        # a file that still says whole thousand tonnes (dp 0, as the first load wrote it) is not merged into: it is read in full again
        old = json.loads(json.dumps(before["port4"]))
        old["dp"] = 0
        self.assertTrue(P.validate_doc(old, "port4"))
        docs, bad, _ = S.read_state(self.out, ["port4"])
        self.assertEqual((docs, bad), ({"port4": self.read("port4")}, []))
        with open(os.path.join(self.out, "port4.json"), "w", encoding="utf-8") as fh:
            fh.write(S.dump(old))
        docs, bad, _ = S.read_state(self.out, ["port4"])
        self.assertEqual((docs, bad), ({}, ["port4"]))


class Pace(Env):
    def test_the_requests_go_one_after_the_other_with_the_pause_between_them_on_one_thread(self):
        self.start(n_ports=3)
        events, main = [], threading.get_ident()
        real = self.svc

        def get(url, params=None, **kw):
            self.assertEqual(threading.get_ident(), main, "a request left the main thread")
            events.append(("get", kw.get("min_interval"), params["where"]))
            return real(url, params=params, **kw)

        def sleep(s):
            self.assertEqual(threading.get_ident(), main, "a pause left the main thread")
            events.append(("sleep", s))
        with mock.patch.object(S.fetch, "get_json", get), mock.patch.object(S.time, "sleep", sleep):
            self.run_script("--backfill", today=date(2026, 11, 12))
        kinds = [e[0] for e in events]
        self.assertEqual(kinds, ["get", "sleep", "get", "sleep", "get"])            # none before the first, none after the last
        self.assertEqual(real.threads, {main})
        for e in events:
            if e[0] == "get":
                self.assertEqual(e[1], FP.PAUSE_S[0])
            else:
                self.assertGreaterEqual(e[1], FP.PAUSE_S[0])
                self.assertLessEqual(e[1], FP.PAUSE_S[1])

    def test_pages_of_one_port_are_asked_in_order_with_the_pause_between_them(self):
        self.start(n_ports=1, first=date(2019, 1, 1), last=date(2026, 11, 20))
        events = []
        real = self.svc

        def get(url, params=None, **kw):
            events.append(("get", params["resultOffset"]))
            return real(url, params=params, **kw)
        with mock.patch.object(S.fetch, "get_json", get), mock.patch.object(S.time, "sleep", lambda s: events.append(("sleep", s))):
            self.run_script("--backfill", today=date(2026, 11, 25))
        self.assertEqual([e[0] for e in events], ["get", "sleep", "get", "sleep", "get"])
        self.assertEqual([e[1] for e in events if e[0] == "get"], [0, 1000, 2000])

    def test_a_request_repeated_after_an_error_starts_no_sooner_than_any_other(self):
        """The download helper itself, on a clock of the test: this script's request answered 503 twice and then 200. With the
        least interval that the script passes, each attempt starts at least PAUSE_S[0] seconds after the one before."""
        clock, starts = [1000.0], []

        class Resp:
            def __init__(self, code):
                self.status_code = code
                self.content = b"{}"

            def json(self):
                return {"features": [], "exceededTransferLimit": False}

            def close(self):
                pass

        class Session:
            def __init__(self):
                self.codes = [503, 503, 200]

            def request(self, *a, **kw):
                starts.append(clock[0])
                clock[0] += 0.5
                return Resp(self.codes.pop(0))
        session = Session()
        saved = (F._sess, F.time.sleep, F.time.monotonic, dict(F._last_hit), F.random.uniform)
        try:
            F._sess = lambda: session
            F.time.sleep = lambda s: clock.__setitem__(0, clock[0] + max(0.0, s))
            F.time.monotonic = lambda: clock[0]
            F.random.uniform = lambda a, b: a
            F._last_hit.clear()
            rows, more, n = S.Reader().page(P.where_history("port1"), 0, "date", {"port1"})
        finally:
            F._sess, F.time.sleep, F.time.monotonic, F.random.uniform = saved[0], saved[1], saved[2], saved[4]
            F._last_hit.clear()
            F._last_hit.update(saved[3])
        self.assertEqual((rows, more, n), ([], False, 0))
        self.assertEqual(len(starts), 3)
        for a, b in zip(starts, starts[1:]):
            self.assertGreaterEqual(b - a, FP.PAUSE_S[0])

    def test_the_pace_is_the_one_of_the_chokepoint_script_and_the_texts_give_its_figures(self):
        self.assertIs(S.PAUSE_S, FP.PAUSE_S)
        lo, hi = int(FP.PAUSE_S[0]), int(FP.PAUSE_S[1])
        doc = " ".join(S.__doc__.split())
        self.assertIn(f"(8 to 14 seconds today)".replace("8", str(lo)).replace("14", str(hi)), doc)
        self.assertIn('not a figure of the owner', doc)
        self.assertIn("one request at a time and slowly", doc)
        code = read("pipeline", "freight", "fetch_portwatch_port_traffic.py")
        self.assertIn("min_interval=PAUSE_S[0]", code)
        for word in ("threading", "concurrent", "multiprocessing", "asyncio", "Pool("):
            self.assertNotIn(word, code)

    def test_the_figures_the_documentation_of_the_script_gives_are_those_of_the_constants(self):
        doc = " ".join(S.__doc__.split())
        pages = P.pages((TODAY - date.fromisoformat(P.HISTORY_FROM)).days + 1)
        self.assertIn(f"read in full ({pages} requests each", doc)
        self.assertEqual((P.MIN_ROW_SHARE, P.MAX_SKIPPED_SHARE, P.REVISED_SHARE, P.REVISED_PORTS), (0.9, 0.1, 0.25, 0.1))
        for text in ("under 90% of the rows it expects", "skip more than 10% of the ports",
                     "more than a tenth of the ports changed by more than a quarter"):
            self.assertIn(text, doc)

    def test_a_first_load_sitting_of_fifteen_ports_is_forty_five_requests_of_about_ten_minutes(self):
        n = len(P.port_ids())
        pl = P.plan(P.port_ids(), {}, set(), TODAY, backfill=True, max_ports=15)
        self.assertEqual(pl["requests"]["total"], 45)
        self.assertLess(45 * FP.PAUSE_S[1], 12 * 60)
        self.assertGreater(45 * FP.PAUSE_S[0], 5 * 60)
        self.assertGreater(n, 15)


class WeeklyPace(Env):
    """The weekly run (window, deep and a scheduled backfill, in several chunks) is asked one request at a time with a pause between
    two requests, like a sitting of the first load."""

    def setUp(self):
        super().setUp()
        self.start(n_ports=10)
        self.run_script("--backfill", "--max-ports", "8", today=date(2026, 11, 12))       # eight files, two ports still pending
        self.svc.table = make_table(self.ports, date(2025, 11, 3), date(2026, 11, 20))

    def watched(self, today=date(2026, 11, 25)):
        events, main = [], threading.get_ident()
        real = self.svc

        def get(url, params=None, **kw):
            self.assertEqual(threading.get_ident(), main, "a request left the main thread")
            events.append(("get", kw, params["where"]))
            return real(url, params=params, **kw)

        def sleep(s):
            self.assertEqual(threading.get_ident(), main, "a pause left the main thread")
            events.append(("sleep", s))
        with mock.patch.object(S.fetch, "get_json", get), mock.patch.object(S.time, "sleep", sleep), \
                mock.patch.object(P.chunks, "__defaults__", (3, P.MAX_ADDRESS)):
            res = self.run_script(today=today)
        return res, events

    def test_the_requests_of_a_weekly_run_go_one_after_the_other_with_the_pause_between_them_on_one_thread(self):
        res, events = self.watched()
        self.assertIsNone(res["error"])
        kinds = [e[0] for e in events]
        gets = kinds.count("get")
        self.assertEqual(res["requests"], gets)
        self.assertGreaterEqual(gets, 5, "the run must have several chunks, a deep pass and a backfill")
        self.assertEqual(kinds, ["sleep", "get"] * gets)            # a scheduled run waits before every request, the first included
        self.assertEqual(self.svc.threads, {threading.get_ident()})
        for e in events:
            if e[0] == "get":
                self.assertEqual(e[1], {"min_interval": FP.PAUSE_S[0], "attempts": 1})
            else:
                self.assertGreaterEqual(e[1], FP.PAUSE_S[0])
                self.assertLessEqual(e[1], FP.PAUSE_S[1])

    def test_a_scheduled_run_waits_a_pause_before_its_first_request_and_a_run_by_hand_does_not(self):
        """The step before this one in the job asks the same host from another process: nothing paces the first request but this wait."""
        res, events = self.watched()
        self.assertEqual([e[0] for e in events][:2], ["sleep", "get"])
        self.assertGreaterEqual(events[0][1], FP.PAUSE_S[0])
        self.assertLessEqual(events[0][1], FP.PAUSE_S[1])
        for options in (("--ports", "port1", "port2"), ("--limit", "3"), ("--full", "port1")):
            self.svc.calls.clear()
            events = []
            real = self.svc

            def get(url, params=None, **kw):
                events.append("get")
                return real(url, params=params, **kw)
            with mock.patch.object(S.fetch, "get_json", get), mock.patch.object(S.time, "sleep", lambda s: events.append("sleep")):
                self.run_script(*options, today=date(2026, 11, 25))
            self.assertEqual(events[0], "get", options)
        # a dry run asks for nothing and waits for nothing
        slept = []
        with mock.patch.object(S.time, "sleep", slept.append):
            self.run_script("--dry-run", today=date(2026, 11, 25))
        self.assertEqual(slept, [])

    def test_the_wait_before_the_first_request_comes_out_of_the_time_of_the_run(self):
        clock, asked = [1000.0], len(self.svc.calls)
        real = self.svc

        def get(url, params=None, **kw):
            return real(url, params=params, **kw)

        def sleep(s):
            clock[0] += s
        with mock.patch.object(S.fetch, "get_json", get), mock.patch.object(S.time, "sleep", sleep), \
                mock.patch.object(S.time, "monotonic", lambda: clock[0]), mock.patch.object(S, "RUN_LIMIT_S", 5):
            res = self.run_script(today=date(2026, 11, 25))
        self.assertIn("5 seconds", res["error"])          # the pause (8 to 14 s) is longer than the 5 s the run is given: no request follows it
        self.assertEqual(len(self.svc.calls), asked)

    def test_a_weekly_run_asks_the_window_in_chunks_then_the_deep_pass_then_the_ports_without_a_file(self):
        res, events = self.watched()
        asked = [e[2] for e in events if e[0] == "get"]
        windows = [w for w in asked if " AND date >" in w]
        history = [w for w in asked if " AND date >" not in w]
        self.assertGreaterEqual(len({w.split(" AND ")[0] for w in windows}), 3)       # three ports a chunk: more than one chunk of each kind
        self.assertEqual(len(history), 2)                                              # port9 and port10, one page each
        self.assertEqual(asked, windows + history)
        for w in windows:
            self.assertLessEqual(w.split(" AND ")[0].count("'port") , 3)
        self.assertEqual(sorted(res["written"]), sorted(self.ports))

    def test_a_request_of_a_weekly_run_repeated_after_an_error_waits_as_long_as_any_other(self):
        self.svc.script = [None, F.FetchError("HTTP 503 after 1 attempts (services9.arcgis.com)")]
        res, events = self.watched()
        self.assertIsNone(res["error"])
        gets = [i for i, e in enumerate(events) if e[0] == "get"]
        self.assertGreater(len(gets), 3)
        for a, b in zip(gets, gets[1:]):
            self.assertEqual(b - a, 2, "a pause between every two requests, the repeated one included")
            self.assertGreaterEqual(events[a + 1][1], FP.PAUSE_S[0])


class Retries(Env):
    """The script's own retries, on the real download helper with a session and a clock of the test: the helper is given one
    attempt, so that no request follows a quota answer sooner than QUOTA_WAIT_S and no request follows another sooner than
    the least pause."""

    QUOTA_BODY = {"error": {"message": "API calls quota exceeded! maximum admitted 20 per 60 sec. Retry after 60 sec"}}
    GOOD = {"features": [], "exceededTransferLimit": False}

    class Resp:
        def __init__(self, code, body=None, headers=None):
            self.status_code = code
            self.content = b"{}"
            self.body = body
            self.headers = headers or {}
            self.text = ""

        def json(self):
            return self.body

        def close(self):
            pass

    def on_clock(self, answer, limit_s=None, pause_first=False, pages=1, carry_on=False):
        """``pages`` calls of ``Reader.page`` (the last outcome is returned; the loop stops at the first exception) whose n-th request
        (from 1) is answered by ``answer(n)`` (a Resp). Returns (outcome, starts): the rows or the exception, and the time each
        request started on the virtual clock; ``self.clock_at_end`` is the clock when the calls ended. With ``carry_on`` a failed call is
        followed by the next one (the take-back loop of a run asks for every port that is left, whatever happened to the one before)."""
        clock, starts = [1000.0], []

        class Session:
            def request(self, *a, **kw):
                starts.append(clock[0])
                clock[0] += 0.5
                return answer(len(starts))
        saved = (F._sess, dict(F._last_hit))
        try:
            F._sess = lambda: Session()
            F._last_hit.clear()
            with mock.patch.object(S.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + max(0.0, s))), \
                    mock.patch.object(S.time, "monotonic", lambda: clock[0]), mock.patch.object(S.fetch, "get_json", GET_JSON), \
                    contextlib.redirect_stdout(io.StringIO()):
                reader = S.Reader(limit_s, pause_first=pause_first)
                for _ in range(pages):
                    try:
                        out = reader.page(P.where_history("port1"), 0, "date", {"port1"})
                    except F.FetchError as e:
                        out = e
                        if not carry_on:
                            break
                self.clock_at_end = clock[0]
        finally:
            F._sess = saved[0]
            F._last_hit.clear()
            F._last_hit.update(saved[1])
        return out, starts

    def gaps(self, starts):
        return [b - a for a, b in zip(starts, starts[1:])]

    def test_after_a_quota_body_the_next_request_starts_at_least_the_wait_later_and_a_second_refusal_stops_the_run(self):
        self.start(n_ports=1)
        out, starts = self.on_clock(lambda n: self.Resp(200, self.QUOTA_BODY))
        self.assertIsInstance(out, F.FetchError)
        self.assertIn("quota", str(out))
        self.assertEqual(len(starts), 2)
        self.assertGreaterEqual(starts[1] - starts[0], S.QUOTA_WAIT_S)
        # a single refusal is waited out and the page is read
        out, starts = self.on_clock(lambda n: self.Resp(200, self.QUOTA_BODY if n == 1 else self.GOOD))
        self.assertEqual(out, ([], False, 0))
        self.assertEqual(len(starts), 2)
        self.assertGreaterEqual(starts[1] - starts[0], S.QUOTA_WAIT_S)

    def test_after_an_http_429_the_next_request_starts_at_least_the_wait_later_and_a_second_refusal_stops_the_run(self):
        self.start(n_ports=1)
        out, starts = self.on_clock(lambda n: self.Resp(429))
        self.assertIsInstance(out, F.FetchError)
        self.assertIn("429", str(out))
        self.assertEqual(len(starts), 2)
        self.assertGreaterEqual(starts[1] - starts[0], S.QUOTA_WAIT_S)
        out, starts = self.on_clock(lambda n: self.Resp(429) if n == 1 else self.Resp(200, self.GOOD))
        self.assertEqual(out, ([], False, 0))
        self.assertEqual(len(starts), 2)
        self.assertGreaterEqual(starts[1] - starts[0], S.QUOTA_WAIT_S)

    def test_after_a_quota_answer_that_names_a_longer_delay_the_wait_is_that_delay_plus_the_margin(self):
        self.start(n_ports=1)
        delay = 120
        body = {"error": {"message": f"API calls quota exceeded! maximum admitted 20 per 60 sec. Retry after {delay} sec"}}
        as_body = lambda n: self.Resp(200, body)
        as_header = lambda n: self.Resp(429, headers={"Retry-After": str(delay)})
        as_http_body = lambda n: self.Resp(429, body)
        for name, quota in (("an error body", as_body), ("an HTTP 429 with the header", as_header), ("an HTTP 429 with the delay in its body", as_http_body)):
            out, starts = self.on_clock(lambda n: quota(n) if n == 1 else self.Resp(200, self.GOOD))
            self.assertEqual(out, ([], False, 0), name)
            self.assertEqual(len(starts), 2, name)
            self.assertGreaterEqual(starts[1] - starts[0], delay + F.QUOTA_MARGIN, name)
            self.assertGreater(delay + F.QUOTA_MARGIN, S.QUOTA_WAIT_S)
            # the second answer stops the run: no request is made 65 s after the first
            out, starts = self.on_clock(quota)
            self.assertIsInstance(out, F.FetchError, name)
            self.assertEqual(len(starts), 2, name)
            self.assertGreaterEqual(starts[1] - starts[0], delay + F.QUOTA_MARGIN, name)
        # a delay shorter than the fixed wait keeps the fixed wait
        out, starts = self.on_clock(lambda n: self.Resp(200, {"error": {"message": "quota exceeded. Retry after 10 sec"}}) if n == 1 else self.Resp(200, self.GOOD))
        self.assertEqual(len(starts), 2)
        self.assertGreaterEqual(starts[1] - starts[0], S.QUOTA_WAIT_S)
        # a delay that the helper does not wait for stops the run at once, however it is given
        long = int(F.QUOTA_MAX_WAIT)
        for quota in (lambda n: self.Resp(200, {"error": {"message": f"quota exceeded. Retry after {long} sec"}}),
                      lambda n: self.Resp(429, headers={"Retry-After": str(long)})):
            out, starts = self.on_clock(quota)
            self.assertIsInstance(out, F.FetchError)
            self.assertEqual(len(starts), 1)
            self.assertEqual(out.retry_after, long)
        # and a wait that would end after the time of the run is not begun: the run ends there, at the time of the first answer and
        # not after the wait (the virtual clock at the end of the call is below the limit)
        out, starts = self.on_clock(as_body, limit_s=delay)
        self.assertIsInstance(out, S.TimeUp)
        self.assertEqual(len(starts), 1)
        self.assertLess(self.clock_at_end - 1000.0, delay)

    def test_a_delay_the_service_names_in_other_words_than_quota_is_a_quota_answer(self):
        """A body that says "Too many requests. Retry after 90 sec." carries a delay: it is waited out, not asked again after a pause."""
        self.start(n_ports=1)
        for message in ("Too many requests. Retry after 90 sec.", "Rate limit exceeded. Retry after 90 sec."):
            body = {"error": {"message": message}}
            self.assertNotIn("quota", message.lower())
            out, starts = self.on_clock(lambda n: self.Resp(200, body) if n == 1 else self.Resp(200, self.GOOD))
            self.assertEqual(out, ([], False, 0), message)
            self.assertEqual(len(starts), 2, message)
            self.assertGreaterEqual(starts[1] - starts[0], 90 + F.QUOTA_MARGIN, message)
            # a second such answer stops the run: two requests, not ATTEMPTS of them
            out, starts = self.on_clock(lambda n: self.Resp(200, body))
            self.assertIsInstance(out, F.FetchError, message)
            self.assertEqual(len(starts), 2, message)
            self.assertGreaterEqual(starts[1] - starts[0], 90 + F.QUOTA_MARGIN, message)
        # an error that names no delay and no quota is an ordinary failure, asked again after a pause
        out, starts = self.on_clock(lambda n: self.Resp(200, {"error": {"message": "Too many requests."}}))
        self.assertEqual(len(starts), S.ATTEMPTS)

    def test_the_boundary_of_the_longest_quota_wait_is_the_helpers_own(self):
        """The script waits a delay of QUOTA_MAX_WAIT - QUOTA_MARGIN seconds (plus the margin: the longest wait the helper accepts)
        and stops at once on one second more, with the delay kept."""
        self.start(n_ports=1)
        edge = int(F.QUOTA_MAX_WAIT - F.QUOTA_MARGIN)
        quota = lambda delay: {"error": {"message": f"quota exceeded. Retry after {delay} sec"}}
        out, starts = self.on_clock(lambda n: self.Resp(200, quota(edge)) if n == 1 else self.Resp(200, self.GOOD))
        self.assertEqual(out, ([], False, 0))
        self.assertEqual(len(starts), 2)
        self.assertGreaterEqual(starts[1] - starts[0], F.QUOTA_MAX_WAIT)
        out, starts = self.on_clock(lambda n: self.Resp(200, quota(edge + 1)))
        self.assertIsInstance(out, F.FetchError)
        self.assertEqual(len(starts), 1)
        self.assertEqual(out.retry_after, edge + 1)

    def test_no_pause_begins_after_the_time_limit(self):
        """Once the limit has passed, the checks that follow (the take-back loop asks for page after page) fail at once: no request and
        no pause. The run ends within one pause of the limit."""
        self.start(n_ports=1)
        limit = 30
        with mock.patch.object(S.random, "uniform", lambda a, b: b):      # the longest pauses
            out, starts = self.on_clock(lambda n: self.Resp(200, self.GOOD), limit_s=limit, pages=10, carry_on=True)
        self.assertIsInstance(out, S.TimeUp)
        self.assertTrue(starts)
        self.assertLessEqual(max(starts) - 1000.0, limit, "no request follows the limit")
        self.assertLessEqual(self.clock_at_end - 1000.0, limit + FP.PAUSE_S[1] + 1, "ten calls, and the run ends within one pause of the limit")
        # a run that has gone over the limit does not sleep again
        out, starts = self.on_clock(lambda n: self.Resp(200, self.GOOD), limit_s=0, pages=2, carry_on=True)
        self.assertIsInstance(out, S.TimeUp)
        self.assertLessEqual(self.clock_at_end - 1000.0, FP.PAUSE_S[1] + 1)

    def test_a_service_that_fails_otherwise_is_asked_four_times_never_less_than_the_least_pause_apart(self):
        self.start(n_ports=1)
        def not_json(n):
            r = self.Resp(200)
            r.json = lambda: (_ for _ in ()).throw(ValueError("not json"))
            return r
        for name, answer in (("HTTP 503", lambda n: self.Resp(503)), ("a body that is not JSON", not_json),
                             ("a service error", lambda n: self.Resp(200, {"error": {"message": "Cannot perform query"}}))):
            out, starts = self.on_clock(answer)
            self.assertIsInstance(out, F.FetchError, name)
            self.assertEqual(len(starts), S.ATTEMPTS, name)
            self.assertIn(f"after {S.ATTEMPTS} attempts", str(out), name)
            for g in self.gaps(starts):
                self.assertGreaterEqual(g, FP.PAUSE_S[0], name)
                self.assertLess(g, FP.PAUSE_S[1] + 1, name)       # a pause, not the quota wait
        out, starts = self.on_clock(lambda n: self.Resp(503) if n < 3 else self.Resp(200, self.GOOD))
        self.assertEqual((out, len(starts)), (([], False, 0), 3))

    def test_every_request_gives_the_helper_one_attempt_and_the_least_interval(self):
        self.start(n_ports=2)
        self.run_script("--backfill", "--max-ports", "2", today=date(2026, 11, 12))
        self.assertTrue(self.svc.calls)
        for kw, _ in self.svc.calls:
            self.assertEqual(kw, {"min_interval": FP.PAUSE_S[0], "attempts": 1})

    def test_the_run_time_limit_stops_the_retries_of_a_weekly_run(self):
        self.start(n_ports=1)
        with mock.patch.object(S.random, "uniform", lambda a, b: a):      # the shortest pauses: three of them are 24 s
            out, starts = self.on_clock(lambda n: self.Resp(503), limit_s=20)
        self.assertIsInstance(out, S.TimeUp)
        self.assertLess(len(starts), S.ATTEMPTS)
        # a quota answer is not waited out past the limit either
        out, starts = self.on_clock(lambda n: self.Resp(200, self.QUOTA_BODY), limit_s=S.QUOTA_WAIT_S - 5)
        self.assertIsInstance(out, S.TimeUp)
        self.assertEqual(len(starts), 1)
        # the pause before the first request of a scheduled run is inside the time of the run
        out, starts = self.on_clock(lambda n: self.Resp(200, self.GOOD), limit_s=FP.PAUSE_S[0] - 1, pause_first=True)
        self.assertIsInstance(out, S.TimeUp)
        self.assertEqual(starts, [])
        # a hand sitting has no limit
        out, starts = self.on_clock(lambda n: self.Resp(503), limit_s=None)
        self.assertEqual(len(starts), S.ATTEMPTS)


class Sittings(Env):
    """A sitting is at most SITTING_MAX ports and one at a time, by the code."""

    def test_the_size_of_a_sitting_is_fifteen_ports(self):
        self.assertEqual(P.SITTING_MAX, 15)

    def test_max_ports_refuses_a_number_under_one_or_over_the_size_of_a_sitting(self):
        self.start(n_ports=3)
        for value in ("0", "-3", str(P.SITTING_MAX + 1), "1000"):
            for extra in ((), ("--backfill",), ("--dry-run", "--backfill")):
                res = self.run_script(*extra, "--max-ports", value)
                self.assertEqual(res["error"], "max-ports out of range", (value, extra))
                self.assertIn(f"from 1 to {P.SITTING_MAX}", self.output)
        self.assertEqual(self.svc.calls, [])
        self.assertFalse(os.path.exists(self.out))
        res = self.run_script("--backfill", "--max-ports", str(P.SITTING_MAX), today=date(2026, 11, 12))
        self.assertIsNone(res["error"])

    def test_backfill_without_max_ports_reads_one_sitting_not_every_port(self):
        self.start(n_ports=P.SITTING_MAX + 5)
        res = self.run_script("--backfill", today=date(2026, 11, 12))
        self.assertIsNone(res["error"])
        self.assertEqual(len(res["written"]), P.SITTING_MAX)
        self.assertEqual(len(self.svc.calls), P.SITTING_MAX)
        pending = json.loads(self.tree()["index.json"])["pending"]
        self.assertEqual(sorted(pending + res["written"]), sorted(self.ports))
        self.assertEqual(len(pending), 5)
        self.run_script("--backfill", today=date(2026, 11, 12))
        self.assertEqual(json.loads(self.tree()["index.json"])["pending"], [])
        self.assertEqual(len(self.svc.calls), P.SITTING_MAX + 5)

    def test_full_refuses_more_than_a_sitting_in_one_run(self):
        self.start(n_ports=P.SITTING_MAX + 1)
        res = self.run_script("--full", *self.ports)
        self.assertEqual(res["error"], "too many ports")
        self.assertEqual(self.svc.calls, [])
        self.assertFalse(os.path.exists(self.out))
        res = self.run_script("--dry-run", "--full", *self.ports[:P.SITTING_MAX])
        self.assertIsNone(res["error"])
        self.assertIn(f"in full: {P.SITTING_MAX} ports", self.output)

    def hold(self):
        fh = open(self.lock, "a", encoding="utf-8")
        self.addCleanup(fh.close)
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fh

    def test_a_second_copy_prints_one_line_and_asks_for_nothing_while_the_first_holds_the_lock(self):
        self.start(n_ports=3)
        first = self.hold()
        for argv in ((), ("--backfill", "--max-ports", "2"), ("--full", "port1")):
            res = self.run_script(*argv, today=date(2026, 11, 12))
            self.assertEqual((res["error"], res["requests"], res["written"]), (None, 0, []), argv)
            self.assertEqual(self.output.strip().splitlines()[-1], "port traffic: another copy of this script is running; nothing asked")
        self.assertEqual(self.svc.calls, [])
        self.assertEqual(self.sleeps, [])
        self.assertFalse(os.path.exists(self.out))
        self.assertFalse(os.path.exists(status.UPDATES))
        # a dry run takes no lock: it prints its plan while the lock is held
        res = self.run_script("--dry-run", "--backfill", "--max-ports", "2", today=date(2026, 11, 12))
        self.assertIn("in full: 2 ports", self.output)
        self.assertNotIn("another copy", self.output)
        first.close()
        res = self.run_script("--backfill", "--max-ports", "2", today=date(2026, 11, 12))
        self.assertEqual(len(res["written"]), 2)

    def test_the_lock_is_released_whatever_the_way_out_of_a_run(self):
        self.start(n_ports=3)
        self.svc.script = down()
        res = self.run_script("--backfill", "--max-ports", "2", today=date(2026, 11, 12))
        self.assertIsNotNone(res["error"])
        res = self.run_script("--backfill", "--max-ports", "2", today=date(2026, 11, 12))      # a failed run leaves no lock
        self.assertEqual((res["error"], len(res["written"])), (None, 2))
        with mock.patch.object(S, "_run", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                S.run(["--backfill"], today=date(2026, 11, 12))
        again = S.take_lock()
        self.assertIsNotNone(again)
        again.close()

    def test_the_lock_is_in_the_system_temporary_folder_and_never_in_the_data_folder(self):
        src = read("pipeline", "freight", "fetch_portwatch_port_traffic.py")
        self.assertIn('LOCK_PATH = os.path.join(tempfile.gettempdir(), "portwatch-port-traffic.lock")', src)
        self.assertNotIn(os.path.join("data", "freight"), tempfile.gettempdir())
        self.assertFalse(os.path.abspath(tempfile.gettempdir()).startswith(os.path.join(ROOT, "data")))


class ThePageThatDoesNotSayItIsTheLast(Env):
    """A page of PAGE rows without ``exceededTransferLimit``, and a first-load port whose rows stop weeks before the others."""

    def without_flag(self):
        real = self.svc

        def get(url, params=None, **kw):
            doc = real(url, params=params, **kw)
            doc.pop("exceededTransferLimit", None)
            return doc
        return get

    def test_a_full_page_without_the_flag_is_followed_by_the_next_page(self):
        self.start(n_ports=1, first=date(2019, 1, 1), last=date(2026, 11, 20))
        self.assertGreater(len(self.svc.table["port1"]), 2 * P.PAGE)
        with mock.patch.object(S.fetch, "get_json", self.without_flag()):
            res = self.run_script("--backfill", today=date(2026, 11, 25))
        self.assertIsNone(res["error"])
        self.assertEqual(res["requests"], 3)
        doc = self.read("port1")
        self.assertEqual(doc["y"], "2026-11-20")
        doc_matches_recount(self, doc, self.rows("port1"))

    def test_rows_that_are_an_exact_multiple_of_the_page_cost_one_request_more_and_no_row_is_lost(self):
        first = date(2019, 1, 1)
        self.start(n_ports=1, first=first, last=first + timedelta(days=2 * P.PAGE - 1))
        self.assertEqual(len(self.svc.table["port1"]), 2 * P.PAGE)
        with mock.patch.object(S.fetch, "get_json", self.without_flag()):
            res = self.run_script("--backfill", today=date(2026, 11, 25))
        self.assertEqual(res["requests"], 3)         # the third page is empty and ends the port
        doc_matches_recount(self, self.read("port1"), self.rows("port1"))
        # the service that says it: the same count, the page that is not full ends it at once
        self.start(n_ports=1, first=first, last=first + timedelta(days=P.PAGE + 99))
        res = self.run_script("--backfill", today=date(2026, 11, 25))
        self.assertEqual(res["requests"], 2)

    def cut_first_read(self, port, last_day):
        """The service stops a port's first read (the query with no lower date) at ``last_day`` and still holds the later rows: a read
        that stopped short. The query that asks for the rows after a day gets them."""
        def hook(rows, params):
            if " AND date >" not in params["where"]:
                return [r for r in rows if r["portid"] != port or r["date"] <= last_day]
            return rows
        self.svc.hook = hook

    def test_a_first_load_port_that_ends_weeks_before_the_newest_and_has_later_rows_in_the_service_is_not_written(self):
        self.start(n_ports=3)
        self.cut_first_read("port2", "2026-10-11")        # last week starts 2026-10-05
        res = self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 12))
        self.assertIsNone(res["error"])
        self.assertEqual(sorted(res["written"]), ["port1", "port3"])
        self.assertEqual(sorted(f for f in os.listdir(self.out)), ["index.json", "port1.json", "port3.json"])
        self.assertEqual(json.loads(self.tree()["index.json"])["pending"], ["port2"])
        self.assertIn("port2 Böte, Port: its last week starts 2026-10-05, the newest 2026-11-02, and the service has rows after "
                      "2026-10-11: not written, the port stays pending", self.output)
        self.assertEqual(res["requests"], 4)               # one page for each of the three ports, and one more for the late one

    def test_a_first_load_port_that_really_ends_early_in_the_service_is_written_after_one_more_request(self):
        self.start(n_ports=3)
        self.svc.table["port2"] = [r for r in self.svc.table["port2"] if r["date"] <= "2026-10-11"]
        res = self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 12))
        self.assertIsNone(res["error"])
        self.assertEqual(sorted(res["written"]), ["port1", "port2", "port3"])
        self.assertEqual(self.read("port2")["y"], "2026-10-11")
        self.assertEqual(json.loads(self.tree()["index.json"])["pending"], [])
        self.assertIn("port2 Böte, Port: its last week starts 2026-10-05, the newest 2026-11-02; the service has no row of this port "
                      "after 2026-10-11: written as it is", self.output)
        self.assertEqual(res["requests"], 4)
        # three weeks behind is the lag of an ordinary table: written with no further request
        self.start(n_ports=3)
        self.svc.table["port2"] = [r for r in self.svc.table["port2"] if r["date"] <= "2026-10-18"]    # last week starts 2026-10-12
        res = self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 12))
        self.assertEqual((sorted(res["written"]), res["requests"]), (["port1", "port2", "port3"], 3))

    def test_a_port_read_before_the_newest_one_of_the_sitting_is_judged_when_the_sitting_ends(self):
        self.start(n_ports=3)
        self.cut_first_read("port1", "2026-10-11")
        res = self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 12))
        self.assertEqual(sorted(res["written"]), ["port2", "port3"])
        self.assertEqual(sorted(f for f in os.listdir(self.out)), ["index.json", "port2.json", "port3.json"])
        self.assertEqual(json.loads(self.tree()["index.json"])["pending"], ["port1"])
        self.assertIn("port1 Alpha: its last week starts 2026-10-05, the newest 2026-11-02, and the service has rows after it: its file "
                      "is removed, the port stays pending", self.output)
        # the next sitting reads it again
        self.svc.hook = None
        res = self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 12))
        self.assertEqual(res["written"], ["port1"])
        # a port that really ends there is kept
        self.start(n_ports=3)
        self.svc.table["port1"] = [r for r in self.svc.table["port1"] if r["date"] <= "2026-10-11"]
        res = self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 12))
        self.assertEqual(sorted(res["written"]), ["port1", "port2", "port3"])
        self.assertIn("port1 Alpha: its last week starts 2026-10-05, the newest 2026-11-02; the service has no row of this port after "
                      "2026-10-11: kept as it is", self.output)

    def test_a_port_is_judged_against_the_newest_file_already_in_the_folder_whatever_way_the_sitting_ends(self):
        self.start(n_ports=3)
        self.run_script("--backfill", "--max-ports", "2", today=date(2026, 11, 12))       # port1 and port2, newest week 2026-11-02
        before = self.tree()
        self.cut_first_read("port3", "2026-10-11")
        res = self.run_script("--backfill", "--max-ports", "1", today=date(2026, 11, 12))     # a sitting of one port: no newer port in it
        self.assertEqual(res["written"], [])
        self.assertEqual(self.tree(), before)
        self.assertIn("the service has rows after 2026-10-11: not written", self.output)
        # a sitting that stops on an error after its first port leaves that port judged all the same
        self.svc.script = [None] + down()
        res = self.run_script("--backfill", "--max-ports", "2", today=date(2026, 11, 12))
        self.assertEqual(res["written"], [])
        self.assertTrue(res["error"])

    def test_a_port_that_is_late_in_the_service_ends_with_a_file_and_the_load_ends(self):
        self.start(n_ports=6)
        self.svc.table["port1"] = [r for r in self.svc.table["port1"] if r["date"] <= "2026-10-04"]     # four weeks later than the others
        sittings, asked = 0, 0
        while json.loads(self.tree().get("index.json", b'{"pending":[1]}'))["pending"] and sittings < 6:
            res = self.run_script("--backfill", "--max-ports", "2", today=date(2026, 11, 12))
            sittings += 1
            asked += res["requests"]
            self.assertIsNone(res["error"])
        self.assertLessEqual(sittings, 3)                          # two ports a sitting: three sittings for six ports
        self.assertEqual(sorted(f for f in os.listdir(self.out) if f.startswith("port")), [f"port{i}.json" for i in range(1, 7)])
        self.assertEqual(self.read("port1")["y"], "2026-10-04")
        self.assertEqual(asked, 6 + 1)                             # a page each, and one for the port that is late

    def test_a_scheduled_backfill_is_judged_like_a_sitting(self):
        self.start(n_ports=9)
        self.run_script("--backfill", "--max-ports", "8", today=date(2026, 11, 12))
        self.cut_first_read("port9", "2026-10-11")
        res = self.run_script(today=date(2026, 11, 12))
        self.assertIsNone(res["error"])
        self.assertNotIn("port9", res["written"])
        self.assertFalse(os.path.exists(os.path.join(self.out, "port9.json")))
        self.assertIn("port9", json.loads(self.tree()["index.json"])["pending"])
        self.svc.hook = None
        res = self.run_script(today=date(2026, 11, 12))
        self.assertIn("port9", res["written"])

    def test_a_full_read_of_a_port_is_not_judged_against_the_sitting(self):
        self.start(n_ports=2)
        self.run_script("--backfill", "--max-ports", "2", today=date(2026, 11, 12))
        res = self.run_script("--full", "port1", today=date(2026, 11, 12))
        self.assertEqual(res["written"], ["port1"])


class TheTextsGiveTheFiguresOfTheCode(Env):
    """docs/UPDATING.md quotes counts, minutes and limits: each is recomputed from the plan and the constants, so that the text fails the day
    a constant moves."""

    def setUp(self):
        super().setUp()
        self.section = guide_section()

    def test_the_requests_and_the_minutes_of_a_normal_run_and_of_the_worst_one(self):
        n = len(P.port_ids())
        bounds = [P.weekly_request_bounds(n, TODAY + timedelta(weeks=w), S.MAX_REQUESTS) for w in range(4)]
        least, most = min(b[0] for b in bounds), max(b[1] for b in bounds)
        self.assertEqual((least, most), (23, 23), "the figure of the guide is 23, whatever the quarter and the day the table ends on, for a table that gains one complete week: change the text with the code")
        self.assertIn(f"**{least} requests** in a normal week", self.section)
        self.assertIn(f"**never more than {S.MAX_REQUESTS}**, not counting a request repeated after an error", self.section)
        self.assertEqual(S.REQUEST_S, 3)
        self.assertIn(f"{S.MAX_REQUESTS} is the figure for the pace: at {int(FP.PAUSE_S[1])} seconds a pause and three seconds an answer, "
                      f"{S.MAX_REQUESTS} requests fill the {S.RUN_LIMIT_S // 60} minutes after which the script stops asking", self.section)
        lo, hi = FP.PAUSE_S
        # a run of the job waits before each request, the first included: as many pauses as requests
        self.assertIn(f"a normal run of {most} requests is {most} pauses, {most * lo / 60:.1f} to {most * hi / 60:.1f} minutes", self.section)
        self.assertIn(f"the worst run, {S.MAX_REQUESTS} requests, is {S.MAX_REQUESTS} pauses, {S.MAX_REQUESTS * lo / 60:.1f} to "
                      f"{S.MAX_REQUESTS * hi / 60:.1f} minutes", self.section)
        # minutes in all, rounded to the minute: the pauses and an answer of about a second (the worst run: up to REQUEST_S seconds)
        in_all = [tuple(int(x) for x in m) for m in re.findall(r"(\d+) to (\d+) minutes in all", self.section)]
        self.assertEqual(len(in_all), 2)
        for (a, b), (n_req, answer_hi) in zip(in_all, ((most, 1), (S.MAX_REQUESTS, S.REQUEST_S))):
            self.assertLessEqual(abs(a - n_req * (lo + 1) / 60), 0.6)
            self.assertLessEqual(abs(b - n_req * (hi + answer_hi) / 60), 0.6)
            self.assertGreaterEqual(b, n_req * (hi + answer_hi) / 60 - 0.3)
        self.assertLessEqual(S.MAX_REQUESTS * (hi + S.REQUEST_S) / 60, S.RUN_LIMIT_S / 60)
        self.assertIn(f"the {S.RUN_LIMIT_S // 60} minutes are the limit of the script", self.section)
        self.assertIn(f"{P.WINDOW_DAYS_MAX} days", self.section)
        self.assertIn("waits one pause of 8 to 14 seconds before its first request, a sitting by hand does not", " ".join(self.section.split()))

    def test_the_requests_of_a_run_after_a_table_that_gained_more_than_a_week_are_the_plans(self):
        """23 is the count of a table that gains one complete week between two runs. The guide gives what a longer gain asks for (a window
        that is more than one page), and what the first scheduled run asks for, from the plan on a state the test builds."""
        n = len(P.port_ids())

        def last_week(table_end):
            """The Monday of the last complete week of a table that ends on ``table_end``."""
            return table_end - timedelta(days=6) if table_end.weekday() == 6 else P.monday(table_end) - timedelta(days=7)

        def asked(today, files_last_monday, lag):
            ids = [f"port{k}" for k in range(n)]
            docs = {i: {"start": P.iso(files_last_monday - timedelta(weeks=300)), "calls": {"tanker": [0] * 301}} for i in ids}
            return P.plan(ids, docs, set(), today, end=today - timedelta(days=lag))["requests"]["total"]

        def after(today, weeks_since, lag_before, lag_now):
            before = today - timedelta(weeks=weeks_since)
            return asked(today, last_week(before - timedelta(days=lag_before)), lag_now)

        first = date(2026, 12, 2)                      # the first scheduled run: a Wednesday
        runs = [first + timedelta(weeks=w) for w in range(4)]            # the four quarters
        lags = range(10)                                                 # the table ends 0 to 9 days before the run
        normal = {after(t, 1, lag, lag) for t in runs for lag in lags}
        self.assertEqual(normal, {23}, "23: the table gained one complete week, whatever the day it ends on")
        # a table that moved on by ten days (it ended 4 days before the run before and ends 1 day before this one: Saturday, then Tuesday)
        moved = after(first, 1, 4, 1)
        self.assertEqual((first - timedelta(days=1)) - (first - timedelta(weeks=1) - timedelta(days=4)), timedelta(days=10))
        self.assertGreater(moved, 23)
        self.assertIn(f"the run asks for {moved} requests;", self.section)
        # it is the same whenever a table that ended on a Saturday or earlier ends on a Sunday or later (lags 4 to 9, then 0 to 3)
        self.assertEqual({after(t, 1, a, b) for t in runs for a in range(4, 10) for b in range(4)}, {moved})
        # and one, two, three missed weeks (the run before was two, three, four weeks earlier)
        for missed, weeks in (("one missed week", 2), ("two", 3), ("three", 4)):
            got = {after(t, weeks, lag, lag) for t in runs for lag in lags}
            lo, hi = min(got), max(got)
            self.assertIn(f"{missed} {lo} to {hi}", self.section, missed)
            self.assertLessEqual(hi, S.MAX_REQUESTS)
        # the first scheduled run: the files end with the week of 9 to 15 November 2026
        files = date(2026, 11, 9)
        by_end = {first - timedelta(days=lag): asked(first, files, lag) for lag in range(1, 8)}
        self.assertEqual(set(by_end.values()), {23, moved})
        last_23 = max(d for d, c in by_end.items() if c == 23)
        first_29 = min(d for d, c in by_end.items() if c == moved)
        self.assertEqual(first_29, last_23 + timedelta(days=1), "one day tells the two apart")
        self.assertEqual((last_23.strftime("%A %-d %B %Y"), first_29.strftime("%A %-d %B %Y")), ("Saturday 28 November 2026", "Sunday 29 November 2026"))
        self.assertIn("The first scheduled run (Wednesday 2 December 2026, the files ending with the week of 9 to 15 November 2026) asks for "
                      f"23 requests if the table then ends on or before {last_23.strftime('%A %-d %B')}, {moved} if it ends on {first_29.strftime('%A %-d %B')} or later",
                      self.section)
        self.assertEqual(files.strftime("%A"), "Monday")
        self.assertIn("a normal week (every port has a file", self.section)
        self.assertNotIn("whatever the day it ends on", self.section)

    def test_the_other_figures_of_the_section_are_the_constants(self):
        sec = self.section
        self.assertEqual((P.WINDOW_WEEKS, P.DEEP_WEEKS), (6, 52))
        self.assertIn("the last six weeks of every port that has a file", sec)
        self.assertIn(f"the last {P.DEEP_WEEKS} weeks of one quarter of the ports", sec)
        self.assertIn(f"at most {['zero', 'one', 'two', 'three', 'four', 'five'][P.SCHEDULED_BACKFILL_CAP]} ports without a file", sec)
        self.assertIn(f"{P.MAX_IDS} ports at a time, in pages of {P.PAGE:,} rows", sec)
        self.assertEqual(P.pages(P.PAGE * 3 - 1), 3)
        self.assertIn(f"(3 requests: the table holds fewer than {3 * P.PAGE:,} days of a port", sec)
        self.assertIn(f"{S.QUOTA_WAIT_S} seconds once per page", sec)
        self.assertIn(f"{int(FP.PAUSE_S[0])} to {int(FP.PAUSE_S[1])} between two requests", sec)
        self.assertIn(f"{int(P.MIN_ROW_SHARE * 100)}% of the rows", sec)
        self.assertIn(f"more than {int(P.MAX_SKIPPED_SHARE * 100)}% of the ports", sec)
        # 45 requests of a sitting by hand are 44 pauses (no wait before the first), from the shortest pause to the longest
        self.assertIn("first-load sitting of 15 ports is 45 requests (6 to 10 minutes of pauses)", sec)
        self.assertEqual((round(44 * FP.PAUSE_S[0] / 60, 1), round(44 * FP.PAUSE_S[1] / 60, 1)), (5.9, 10.3))
        self.assertEqual((P.SITTING_MAX, P.pages((TODAY - date.fromisoformat(P.HISTORY_FROM)).days + 1) * P.SITTING_MAX), (15, 45))
        self.assertIn(f"{S.FIRST_LOAD_LAG_DAYS} days before the newest last week", sec)
        self.assertIn("(`continue-on-error`, 15 minutes;", sec)
        self.assertIn("more than 16 days or a latest day of data more than 21 days old", sec)
        self.assertEqual((ST.WEEKLY, ST.DAY_LAG), (16, 21))

    def test_the_minutes_the_plan_prints_are_the_pauses_at_the_shortest_and_the_longest_pace(self):
        def printed(total, by_hand):
            pl = {"quarter": 1, "window": [], "deep": [], "history": [], "deferred": [],
                  "requests": {"total": total, "window": total, "deep": 0, "history": 0}}
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                S.print_plan(pl, TODAY, by_hand)
            return buf.getvalue()
        # a sitting by hand of 45 requests has 44 pauses: 44 x 8 s = 5.9 and 44 x 14 s = 10.3 minutes
        self.assertIn("requests: 45 at most", printed(45, True))
        self.assertIn("6 to 10 minutes of pauses", printed(45, True))
        # a run of the job waits before its first request too: 23 requests are 23 pauses, 3.1 to 5.4 minutes
        self.assertIn("3 to 5 minutes of pauses", printed(23, False))
        self.assertIn("0 to 0 minutes of pauses", printed(0, True))

    def test_the_docstring_of_the_script_names_the_bound_and_the_pages_of_a_first_read(self):
        doc = " ".join(S.__doc__.split())
        self.assertIn(f"read in full (3 requests each while a port has fewer than {3 * P.PAGE:,} days of rows, one more from then on;", doc)
        self.assertIn("MAX_REQUESTS", doc)

    def test_the_step_of_the_workflow_runs_this_script_and_its_limit_holds_the_run_limit(self):
        wf = read(".github", "workflows", "update-portwatch.yml")
        self.assertIn("run: python pipeline/freight/fetch_portwatch_port_traffic.py\n", wf)
        step = int(re.search(r"id: ports\n\s+continue-on-error: true\n(?:\s+#.*\n)*\s+timeout-minutes: (\d+)", wf).group(1))
        self.assertEqual(step, 15)
        self.assertLess(S.RUN_LIMIT_S, step * 60)


class Files(Env):
    def test_the_script_opens_no_file_outside_the_folder_of_the_files_the_inputs_and_the_status(self):
        self.start(n_ports=3)
        opened = []
        real_open, real_replace = builtins.open, os.replace

        def spy_open(f, mode="r", *a, **kw):
            if isinstance(f, (str, os.PathLike)):
                opened.append((os.path.abspath(f), mode))
            return real_open(f, mode, *a, **kw)

        def spy_replace(a, b, *args, **kw):
            opened.append((os.path.abspath(b), "replace"))
            return real_replace(a, b, *args, **kw)
        with mock.patch.object(builtins, "open", spy_open), mock.patch.object(os, "replace", spy_replace):
            self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 12))
            self.run_script(today=date(2026, 11, 25))
        allowed_in = {os.path.abspath(P.PORTS_GEOJSON), os.path.abspath(P.TABLE)}
        out = os.path.abspath(self.out) + os.sep
        status_files = {os.path.abspath(p) for p in (status.UPDATES, status.LOG)}
        for path, mode in opened:
            if path in allowed_in:
                self.assertIn("r", mode)
            elif path.startswith(out):
                continue
            elif path == os.path.abspath(self.lock):
                self.assertFalse(path.startswith(out))      # the lock is never in the folder of the files
            else:
                self.assertTrue(any(path.startswith(s) for s in status_files), f"opened {path} ({mode})")
        self.assertTrue(any(p.startswith(out) and m != "r" for p, m in opened))
        # nothing daily on disk: the folder holds the port files and the index, each port file only the keys of a weekly series
        self.assertEqual(sorted(os.listdir(self.out)), ["index.json", "port1.json", "port2.json", "port3.json"])
        for p in ("port1", "port2", "port3"):
            self.assertEqual(list(self.read(p)), list(P.KEYS))

    def test_the_folder_of_the_repository_is_not_touched_by_a_run_with_out_and_no_status_is_recorded(self):
        self.start(n_ports=2)
        elsewhere = os.path.join(self.tmp, "elsewhere")
        res = self.run_script("--backfill", "--out", elsewhere, today=date(2026, 11, 12))
        self.assertEqual(sorted(res["written"]), ["port1", "port2"])
        self.assertFalse(os.path.exists(self.out))
        self.assertFalse(os.path.exists(status.UPDATES))
        self.assertTrue(os.path.exists(os.path.join(elsewhere, "port1.json")))

    def test_the_default_folder_and_the_registry_ids_are_the_published_ones(self):
        src = read("pipeline", "freight", "portwatch_ports.py")
        self.assertIn('"data", "freight", "port-traffic"', src)
        with open(os.path.join(ROOT, "data", "sources.json"), encoding="utf-8") as fh:
            self.assertIn(S.SOURCE, {s["id"] for s in json.load(fh)})


class AsTheWorkflowCallsIt(unittest.TestCase):
    """The script itself, as a process: always exit code 0, and a dry run on the real files asks for nothing."""

    def call(self, *argv):
        return subprocess.run([sys.executable, "-I", os.path.join(ROOT, "pipeline", "freight", "fetch_portwatch_port_traffic.py"), *argv],
                              capture_output=True, text=True, timeout=120, cwd=tempfile.gettempdir())

    def test_a_dry_run_on_the_real_files_exits_zero_and_prints_the_plan_from_the_files(self):
        r = self.call("--dry-run", "--backfill", "--max-ports", "15")
        self.assertEqual(r.returncode, 0, r.stderr)
        n = len(P.port_ids())
        self.assertIn(f"port traffic: {n} ports", r.stdout)
        # the sitting planned is what the folder still lacks, 15 ports at most: nothing once the first load is complete
        with open(os.path.join(ROOT, "data", "freight", "port-traffic", "index.json"), encoding="utf-8") as fh:
            pending = len(json.load(fh).get("pending") or [])
        if pending:
            self.assertIn(f"in full: {min(pending, 15)} ports", r.stdout)
        else:
            self.assertNotIn("in full: 15 ports", r.stdout)
            self.assertRegex(r.stdout, r"in full 0\b|in full: 0 ports|nothing to read|no port without a file")
        self.assertIn(f"a normal weekly run for all {n} ports asks for", r.stdout)
        self.assertIn("not counting a request repeated after an error", r.stdout)
        # the line is true in every mode: a sitting by hand counts pages only, so the bound it prints is that of a weekly run of the job
        self.assertIn(f"a weekly run of the job never asks for more than {S.MAX_REQUESTS}, not counting a request repeated after an error", r.stdout)
        self.assertNotIn("a run never asks for more", r.stdout)
        self.assertEqual(r.stderr, "")

    def test_a_wrong_option_does_not_make_the_step_fail(self):
        r = self.call("--no-such-option")
        self.assertEqual(r.returncode, 0)
        self.assertIn("unrecognized arguments", r.stderr)


# ------------------------------------------------------------------------------------------------ one set of rules
NODE = shutil.which("node")


def node_codes(cases):
    """Run web/scripts/port-traffic-rules.mjs on the cases: [{kind, doc, opts}] -> [[codes]]."""
    code = (
        "import fs from 'node:fs';"
        f"import {{ portTrafficProblems, portTrafficIndexProblems, problemCodes }} from {json.dumps('file://' + RULES)};"
        "const input = JSON.parse(fs.readFileSync(0, 'utf8'));"
        "const out = input.map((c) => problemCodes(c.kind === 'index' ? portTrafficIndexProblems(c.doc, c.opts)"
        " : portTrafficProblems(c.doc, { id: c.opts?.id, sources: c.opts?.sources ? new Set(c.opts.sources) : undefined })));"
        "console.log(JSON.stringify(out));"
    )
    r = subprocess.run([NODE, "--input-type=module", "-e", code], input=json.dumps(cases), capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def py_codes(doc, port_id=None, sources=None):
    return sorted({p.split(":")[0] for p in P.validate_doc(doc, port_id, sources)})


def good_doc(n=60):
    rows = make_table(["port9"], date(2025, 1, 6), date(2025, 1, 6) + timedelta(days=7 * n - 1))["port9"]
    return P.build_doc("port9", "Nine", P.weekly(rows), (date(2025, 1, 6) + timedelta(days=7 * n - 1)).isoformat())


def broken_docs():
    """(name, expected code, document) of a document that breaks one rule."""
    def edit(fn, **kw):
        d = good_doc(**kw)
        fn(d)
        return d
    out = [
        ("an extra key (a daily array)", "shape", edit(lambda d: d.update(daily=[1]))),
        ("a missing key", "shape", edit(lambda d: d.pop("step"))),
        ("not an object", "shape", [1, 2]),
        ("an id that is not the file's", "id", edit(lambda d: d.update(id="port10"))),
        ("an id that is not an id", "id", edit(lambda d: d.update(id="harbour"))),
        ("an empty name", "name", edit(lambda d: d.update(name=" "))),
        ("another source", "source", edit(lambda d: d.update(s="portwatch"))),
        ("a y that is not a date", "date", edit(lambda d: d.update(y="2026-02-30"))),
        ("a start that is not a date", "date", edit(lambda d: d.update(start="soon"))),
        ("a start that is not a Monday", "monday", edit(lambda d: d.update(start="2025-01-07", y="2026-03-30"))),
        ("a step that is not a week", "step", edit(lambda d: d.update(step="day"))),
        ("another unit", "unit", edit(lambda d: d.update(u="t"))),
        ("a dp that is not the most decimals of the rule", "unit", edit(lambda d: d.update(dp=5))),
        ("the dp of whole thousand tonnes", "unit", edit(lambda d: d.update(dp=0))),
        ("a text for dp", "unit", edit(lambda d: d.update(dp="3"))),
        ("a block that is not four arrays", "series", edit(lambda d: d["calls"].pop("other"))),
        ("a block that is not an object", "series", edit(lambda d: d.update(exports=[1]))),
        ("arrays of unequal length", "series", edit(lambda d: d["imports"]["dry"].pop())),
        ("empty arrays", "series", edit(lambda d: [d[k][t].clear() for k in ("calls", "exports", "imports") for t in ("tanker", "dry", "container", "other")])),
        ("a negative call count", "calls", edit(lambda d: d["calls"]["dry"].__setitem__(4, -1))),
        ("a fractional call count", "calls", edit(lambda d: d["calls"]["dry"].__setitem__(4, 1.5))),
        ("a text for a call count", "calls", edit(lambda d: d["calls"]["dry"].__setitem__(4, "3"))),
        ("a boolean for a call count", "calls", edit(lambda d: d["calls"]["dry"].__setitem__(4, True))),
        ("a negative tonnage", "tonnes", edit(lambda d: d["exports"]["tanker"].__setitem__(2, -3))),
        ("a tonnage of 100 or more with a decimal", "tonnes", edit(lambda d: d["imports"]["other"].__setitem__(2, 100.5))),
        ("a tonnage of 10 or more with two decimals", "tonnes", edit(lambda d: d["imports"]["other"].__setitem__(2, 10.25))),
        ("a tonnage of 1 or more with three decimals", "tonnes", edit(lambda d: d["imports"]["other"].__setitem__(2, 1.005))),
        ("a tonnage finer than a tonne", "tonnes", edit(lambda d: d["imports"]["other"].__setitem__(2, 0.0005))),
        ("99.95, which the rule makes 100", "tonnes", edit(lambda d: d["imports"]["other"].__setitem__(2, 99.95))),
        ("a text for a tonnage", "tonnes", edit(lambda d: d["imports"]["other"].__setitem__(2, "1"))),
        ("holes in one array only", "holes", edit(lambda d: d["exports"]["dry"].__setitem__(7, None))),
        ("holes in different places", "holes", edit(lambda d: [d["calls"]["tanker"].__setitem__(3, None), d["calls"]["dry"].__setitem__(4, None)])),
        ("a last week that ends after y", "end", edit(lambda d: d.update(y="2026-02-01"))),
    ]
    return out


@unittest.skipUnless(NODE, "node is not installed: the rules of web/scripts/port-traffic-rules.mjs cannot be run")
class OneSetOfRules(Env):
    def test_python_and_javascript_give_the_same_verdict_on_every_document(self):
        cases = [("a good document", None, good_doc()), ("holes in all twelve arrays", None, edit_holes(good_doc())),
                 ("every size of value", None, every_size(good_doc()))]
        cases += broken_docs()
        opts = {"id": "port9", "sources": ["portwatch-port-traffic"]}
        want = node_codes([{"kind": "doc", "doc": d, "opts": opts} for _, _, d in cases])
        for (name, code, d), js in zip(cases, want):
            py = py_codes(d, "port9", {"portwatch-port-traffic"})
            if code is None:
                self.assertEqual((py, js), ([], []), name)
            else:
                self.assertIn(code, py, name)
                self.assertEqual(py, js, f"{name}: Python says {py}, JavaScript says {js}")

    def test_the_id_of_the_file_and_the_registry_are_what_the_caller_says(self):
        d = good_doc()
        self.assertEqual(py_codes(d, "port9", {"portwatch-port-traffic"}), node_codes([{"kind": "doc", "doc": d, "opts": {"id": "port9", "sources": ["portwatch-port-traffic"]}}])[0])
        self.assertEqual(py_codes(d, "port9", set()), ["source"])
        self.assertEqual(node_codes([{"kind": "doc", "doc": d, "opts": {"id": "port9", "sources": []}}])[0], ["source"])
        self.assertEqual(py_codes(d, "port1"), ["id"])
        self.assertEqual(node_codes([{"kind": "doc", "doc": d, "opts": {"id": "port1"}}])[0], ["id"])

    def test_every_file_the_script_writes_passes_the_rules_of_the_site(self):
        self.start(n_ports=6)
        self.rows_with_holes()
        self.run_script("--backfill", "--max-ports", "6", today=date(2026, 11, 12))
        self.svc.table = make_table(self.ports, date(2025, 11, 3), date(2026, 11, 20))
        self.run_script(today=date(2026, 11, 25))
        files = sorted(f for f in os.listdir(self.out) if f.startswith("port"))
        self.assertEqual(len(files), 6)
        cases = []
        for f in files:
            with open(os.path.join(self.out, f), encoding="utf-8") as fh:
                cases.append({"kind": "doc", "doc": json.load(fh), "opts": {"id": f[:-5], "sources": ["portwatch-port-traffic"]}})
        self.assertEqual(node_codes(cases), [[]] * 6)
        index = json.loads(self.tree()["index.json"])
        self.assertEqual(node_codes([{"kind": "index", "doc": index, "opts": {"ids": self.ports, "files": [f[:-5] for f in files]}}]), [[]])

    def rows_with_holes(self):
        """One day of one port is missing: its week is a hole and the file still passes."""
        self.svc.table["port2"] = [r for r in self.svc.table["port2"] if r["date"] != "2026-03-11"]

    def test_the_index_rules_are_those_of_the_validator(self):
        ids = ["port1", "port2", "port3"]
        cases = [
            ("good", {"checked": "2026-11-25", "none": ["port3"]}, ["port1", "port2"], []),
            ("an id with neither", {"checked": "2026-11-25", "none": []}, ["port1", "port2"], ["index-missing"]),
            ("a file and none", {"checked": "2026-11-25", "none": ["port2", "port3"]}, ["port1", "port2"], ["index-both"]),
            ("a none that no asset carries", {"checked": "2026-11-25", "none": ["port3", "port9"]}, ["port1", "port2"], ["index-orphan"]),
            ("a file that no asset carries", {"checked": "2026-11-25", "none": []}, ["port1", "port2", "port3", "port9"], ["index-orphan"]),
            ("not sorted", {"checked": "2026-11-25", "none": ["port3", "port2"]}, ["port1"], ["index-none"]),
            ("no date", {"checked": "yesterday", "none": ["port3"]}, ["port1", "port2"], ["index-date"]),
            ("another shape", {"none": []}, ["port1", "port2", "port3"], ["index-shape"]),
            ("pending, none and a file", {"checked": "2026-11-25", "none": ["port3"], "pending": ["port2"]}, ["port1"], []),
            ("pending left out", {"checked": "2026-11-25", "none": ["port3"]}, ["port1", "port2"], []),
            ("an id in neither", {"checked": "2026-11-25", "none": [], "pending": ["port3"]}, ["port1"], ["index-missing"]),
            ("a file and pending", {"checked": "2026-11-25", "none": [], "pending": ["port2"]}, ["port1", "port2", "port3"], ["index-both"]),
            ("none and pending", {"checked": "2026-11-25", "none": ["port3"], "pending": ["port3"]}, ["port1", "port2"], ["index-both"]),
            ("a pending that no asset carries", {"checked": "2026-11-25", "none": [], "pending": ["port3", "port9"]}, ["port1", "port2"], ["index-orphan"]),
            ("pending not sorted", {"checked": "2026-11-25", "none": [], "pending": ["port3", "port2"]}, ["port1"], ["index-pending"]),
        ]
        got = node_codes([{"kind": "index", "doc": d, "opts": {"ids": ids, "files": f}} for _, d, f, _ in cases])
        for (name, _, _, want), g in zip(cases, got):
            self.assertEqual(g, want, name)
        self.assertEqual(P.index_doc({"port3", "port2"}, "2026-11-25", ["port9", "port4"]),
                         {"checked": "2026-11-25", "none": ["port2", "port3"], "pending": ["port4", "port9"]})
        self.assertEqual(P.index_doc([], "2026-11-25"), {"checked": "2026-11-25", "none": [], "pending": []})


def every_size(doc):
    """One value of each size the rule knows, as the rule writes it: 0.999, 1, 1.01, 9.99, 10, 10.1, 99.9, 100, 1234."""
    for i, v in enumerate((0, 0.001, 0.999, 1, 1.01, 9.99, 10, 10.1, 99.9, 100, 999, 1235)):
        doc["exports"]["tanker"][i] = v
    return doc


def edit_holes(doc):
    for k in ("calls", "exports", "imports"):
        for t in ("tanker", "dry", "container", "other"):
            doc[k][t][5] = None
            doc[k][t][6] = None
    return doc


if __name__ == "__main__":
    unittest.main()
