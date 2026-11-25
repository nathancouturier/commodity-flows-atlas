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
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import date, timedelta
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
from common import status  # noqa: E402

TODAY = date(2026, 11, 25)
LAST_DAY = date(2026, 11, 20)   # the table lags the date by days
RULES = os.path.join(ROOT, "web", "scripts", "port-traffic-rules.mjs")


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


def half_up(tonnes, dp=0):
    q = (Decimal(tonnes) / Decimal(1000)).quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP)
    return int(q) if dp == 0 else float(q)


def doc_matches_recount(testcase, doc, rows, dp=0):
    """Every week of ``doc`` is the recount of ``rows`` (a hole where the week is not complete), rounded half up."""
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
                    exp = want[m][k][j] if k == "calls" else half_up(want[m][k][j], dp)
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
        for pa in (mock.patch.object(S.fetch, "get_json", self.svc), mock.patch.object(S.time, "sleep", self.sleeps.append)):
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

    def test_tonnes_are_rounded_half_up_to_the_unit_of_the_file(self):
        for t, kt0, kt1 in [(0, 0, 0.0), (499, 0, 0.5), (500, 1, 0.5), (1499, 1, 1.5), (1500, 2, 1.5), (2500, 3, 2.5), (49, 0, 0.0), (50, 0, 0.1)]:
            self.assertEqual(P.kt(t, 0), kt0, t)
            self.assertEqual(P.kt(t, 0), half_up(t, 0), t)
            self.assertEqual(P.kt(t, 1), kt1, t)
            self.assertEqual(P.kt(t, 1), half_up(t, 1), t)
        self.assertIsInstance(P.kt(1500, 0), int)

    def test_the_document_equals_the_recount_at_the_unit_it_states(self):
        rows = make_table(["port9"], date(2025, 5, 7), date(2026, 2, 3))["port9"]
        for dp in (0, 1):
            doc = P.build_doc("port9", "Nine", P.weekly(rows), P.last_day(rows), dp)
            self.assertEqual((doc["u"], doc["dp"]), ("kt", dp))
            doc_matches_recount(self, doc, rows, dp)
            self.assertEqual(P.validate_doc(doc, "port9"), [])
        self.assertEqual(P.build_doc("port9", "Nine", P.weekly(rows), "2026-02-03")["dp"], P.DECIMALS)

    def test_rounding_error_is_the_difference_of_the_52_week_sums(self):
        rows = make_table(["port9"], date(2024, 1, 1), date(2026, 2, 1))["port9"]
        weeks = P.weekly(rows)
        last = sorted(weeks)[-52:]
        types = ("tanker", "dry", "container", "other")
        # the four types together, as the 52-week figure of the page is
        worst = 0.0
        for k in ("exports", "imports"):
            exact = sum(weeks[m][k][t] for m in last for t in types)
            rounded = sum(half_up(weeks[m][k][t]) for m in last for t in types) * 1000
            worst = max(worst, abs(rounded - exact) / exact)
        share, where = P.rounding_error(weeks, 0)
        self.assertAlmostEqual(share, worst)
        self.assertIn(where, ("exports", "imports"))
        # one type alone
        worst = 0.0
        for k in ("exports", "imports"):
            for t in types:
                exact = sum(weeks[m][k][t] for m in last)
                rounded = sum(half_up(weeks[m][k][t]) for m in last) * 1000
                worst = max(worst, abs(rounded - exact) / exact)
        share_t, where_t = P.rounding_error(weeks, 0, by_type=True)
        self.assertAlmostEqual(share_t, worst)
        self.assertGreaterEqual(share_t, share)
        self.assertIsNotNone(where_t)
        self.assertLess(P.rounding_error(weeks, 1, by_type=True)[0], share_t + 1e-12)
        self.assertEqual(P.rounding_error({}, 0), (0.0, None))

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
    def test_chunks_hold_at_most_twenty_ports_and_stay_under_the_address_limit_with_every_port_once(self):
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
        self.assertEqual(pl["requests"]["history"], 5 * P.pages((TODAY - date.fromisoformat(P.HISTORY_FROM)).days + 1))
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
        self.assertEqual(len(P.plan(ids, docs, none, TODAY, backfill=True)["history"]), len(ids) - 3 - 2)
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
        least, most = P.weekly_request_bounds(n, TODAY)
        self.assertLess(least, most)
        self.assertGreaterEqual(least, math.ceil(n / P.MAX_IDS))
        self.assertGreater(most - least, P.SCHEDULED_BACKFILL_CAP)     # at least the ports read in full
        self.assertEqual(P.weekly_request_bounds(n, TODAY + timedelta(weeks=1))[0] > 0, True)


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


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
        self.svc.script = [F.FetchError("HTTP 503 after 4 attempts (services9.arcgis.com)")]
        res = self.run_script("--backfill", "--max-ports", "3", today=date(2026, 11, 12))
        self.assertIn("503", res["error"])
        self.assertEqual(sorted(self.tree()), ["index.json"])         # no file, and the folder says what is still to read
        self.assertEqual(json.loads(self.tree()["index.json"]), {"checked": "2026-11-12", "none": [], "pending": self.ports})
        self.svc.script = [None, F.FetchError("HTTP 503 after 4 attempts (services9.arcgis.com)")]
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
        self.svc.script = [F.FetchError("HTTP 503 after 4 attempts (services9.arcgis.com)")]
        res = self.run_script("--backfill", "--max-ports", "2", today=date(2026, 11, 12))
        self.assertIn("503", res["error"])
        self.assertEqual(status.get(S.SOURCE)["consecutive_failures"], 0)       # a sitting that stops short is not a scheduled failure
        self.svc.script = [F.FetchError("HTTP 503 after 4 attempts (services9.arcgis.com)")]
        res = self.run_script(today=date(2026, 11, 25))
        self.assertIn("503", res["error"])
        self.assertEqual(status.get(S.SOURCE)["consecutive_failures"], 1)
        self.assertIn("503", status.get(S.SOURCE)["last_error"])


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
            ("service error body", [F.FetchError("service error: Cannot perform query")], "service error"),
            ("service down", [F.FetchError("HTTP 503 after 4 attempts (services9.arcgis.com)")], "503"),
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

    def test_the_longest_weekly_run_at_the_longest_pause_fits_the_time_the_script_gives_itself(self):
        least, most = P.weekly_request_bounds(len(P.port_ids()), TODAY)
        self.assertLess(most * FP.PAUSE_S[1], S.RUN_LIMIT_S)
        self.assertLess(S.RUN_LIMIT_S + 2 * FP.PAUSE_S[1] + 90, 15 * 60)      # the step limit of the job leaves room for the last request
        self.assertLessEqual(least, most)


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
        self.assertIn("in full: 15 ports", r.stdout)
        self.assertIn(f"a weekly run for all {n} ports asks for", r.stdout)
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


def good_doc(n=60, dp=0):
    rows = make_table(["port9"], date(2025, 1, 6), date(2025, 1, 6) + timedelta(days=7 * n - 1))["port9"]
    return P.build_doc("port9", "Nine", P.weekly(rows), (date(2025, 1, 6) + timedelta(days=7 * n - 1)).isoformat(), dp)


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
        ("decimals that are not allowed", "unit", edit(lambda d: d.update(dp=5))),
        ("a block that is not four arrays", "series", edit(lambda d: d["calls"].pop("other"))),
        ("a block that is not an object", "series", edit(lambda d: d.update(exports=[1]))),
        ("arrays of unequal length", "series", edit(lambda d: d["imports"]["dry"].pop())),
        ("empty arrays", "series", edit(lambda d: [d[k][t].clear() for k in ("calls", "exports", "imports") for t in ("tanker", "dry", "container", "other")])),
        ("a negative call count", "calls", edit(lambda d: d["calls"]["dry"].__setitem__(4, -1))),
        ("a fractional call count", "calls", edit(lambda d: d["calls"]["dry"].__setitem__(4, 1.5))),
        ("a text for a call count", "calls", edit(lambda d: d["calls"]["dry"].__setitem__(4, "3"))),
        ("a boolean for a call count", "calls", edit(lambda d: d["calls"]["dry"].__setitem__(4, True))),
        ("a negative tonnage", "tonnes", edit(lambda d: d["exports"]["tanker"].__setitem__(2, -3))),
        ("a tonnage with decimals the file does not state", "tonnes", edit(lambda d: d["imports"]["other"].__setitem__(2, 1.5))),
        ("a text for a tonnage", "tonnes", edit(lambda d: d["imports"]["other"].__setitem__(2, "1"))),
        ("holes in one array only", "holes", edit(lambda d: d["exports"]["dry"].__setitem__(7, None))),
        ("holes in different places", "holes", edit(lambda d: [d["calls"]["tanker"].__setitem__(3, None), d["calls"]["dry"].__setitem__(4, None)])),
        ("a last week that ends after y", "end", edit(lambda d: d.update(y="2026-02-01"))),
    ]
    return out


@unittest.skipUnless(NODE, "node is not installed: the rules of web/scripts/port-traffic-rules.mjs cannot be run")
class OneSetOfRules(Env):
    def test_python_and_javascript_give_the_same_verdict_on_every_document(self):
        cases = [("a good document", None, good_doc()), ("a good document with a decimal", None, good_doc(dp=1)),
                 ("holes in all twelve arrays", None, edit_holes(good_doc()))]
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


def edit_holes(doc):
    for k in ("calls", "exports", "imports"):
        for t in ("tanker", "dry", "container", "other"):
            doc[k][t][5] = None
            doc[k][t][6] = None
    return doc


if __name__ == "__main__":
    unittest.main()
