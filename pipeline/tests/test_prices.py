"""Price series (package P1): the basis notes and breaks read from the World Bank "Description" sheet, the iron ore
split, annual values repeated over the months, the changes and 52-week position of the price board, the freshness
check and the shape check of the Pink Sheet workbook; plus checks on the data the builder wrote.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import date

import openpyxl

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "prices"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import basis as B  # noqa: E402
import build_prices as P  # noqa: E402

DATA = os.path.join(ROOT, "data", "prices")

# rows of the Description sheet, as the workbook words them
SOYBEANS = ("Soybeans, from January 2025, U.S. Soybeans, FOB U.S. Gulf ;January 2021-December 2024, U.S Gulf Yellow Soybean #2, "
            "CIF Rotterdam; December 2007 to December 2020, U.S. No. 2 yellow meal, CIF Rotterdam; previously US origin, nearest forward")
UREA = "Urea, (Ukraine), prill spot f.o.b. Middle East, beginning March 2022; previously, f.o.b. Black Sea."
POTASH = "Potassium chloride (muriate of potash), Brazil CFR granular spot price from January 2020; previously, f.o.b. Vancouver"
PALM = ("Palm oil (Malaysia), from January 2026, RBD, average export price FOB;February-December 2025, Crude, DAP; "
        "November 2024-January 2025, 5% Bulk, CIF North West Europe; January 2021 to October 2024, RBD, FOB Malaysia Ports; "
        "December 2001 to December 2020, RBD, CIF Rotterdam; previously Malaysia 5%,  c.i.f. N.W. Europe, bulk, nearest forward .")
HRW = ("Wheat (U.S.), no. 2 hard red winter Gulf export price; June 2020 backwards, no. 1, hard red winter, ordinary protein, "
       "export price delivered at the US Gulf port for prompt or 30 days shipment")
DUBAI = "Crude oil, Dubai Fateh 32` API for years 1985-present; 1960-84 refer to Saudi Arabian Light, 34` API."
SILVER = "Silver (UK), 99.9% refined, London afternoon fixing; prior to July 1976 Handy & Harman.  Grade prior to 1962 unrefined silver."
COAL_AUS = ("Coal (Australia), from February 2022, port thermal, f.o.b. Newcastle, 6000 kcal/kg futures price. From 2015 to January 2022, "
            "port thermal, f.o.b. Newcastle, 6000 kcal/kg spot price. 2002-2014, thermal GAR, f.o.b. piers, Newcastle/Port Kembla , "
            "6,300 kcal/kg (11,340 btu/lb), less than 0.8%, sulfur 13% ash; previously 6,667 kcal/kg (12,000 btu/lb), less than 1.0% sulfur, 14%  ash")
COPPER = "Copper (LME), grade A, minimum 99.9935% purity, cathodes and wire bar shapes, settlement price"
IRON = ("Iron ore, spot in US dollar/dry ton and contract in US cents/dmtu. For years 2008 (December) to present, spot, (any origin) fines, "
        "62% Fe, c.f.r. China; during 2006 to 2008 (November) spot, 63.5%Fe.  Earlier data refer to annual contract prices (Brazil for Europe,) "
        "VALE Carajas mines sinter feed, f.o.b. Ponta da Madeira during years 1987-2009; Itabira mines f.o.b. Tubarão for years 1960-86.  "
        "Unit dmtu denotes dry metric ton unit , i.e. 1% Fe-unit. ")
SA_NOTE = ("Coal (South Africa), June to November 2022, March, April, June to September, December 2023, and January-May 2024 are estimates "
           "based on similar benchmarks, December 2022 to February 2023, May, and October-November 2023 replaced with source data.")
LNG = "Liquefied natural gas (Japan), LNG, import price, cif; recent two months' averages are estimates."


def jload(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def breaks(text, first="1960-01", last="2026-10"):
    return B.basis_and_breaks(B.parse_clauses(text), first, last)


class BasisFromDescription(unittest.TestCase):
    def test_breaks_of_the_documented_changes(self):
        for text, want in [
            (SOYBEANS, ["2007-12", "2021-01", "2025-01"]),
            (UREA, ["2022-03"]),
            (POTASH, ["2020-01"]),
            (PALM, ["2001-12", "2021-01", "2024-11", "2025-02", "2026-01"]),
            (HRW, ["2020-07"]),
            (DUBAI, ["1985-01"]),
            (SILVER, ["1962-01", "1976-07"]),
            (COAL_AUS, ["2002-01", "2015-01", "2022-02"]),
            (COPPER, []),
        ]:
            self.assertEqual([b["at"] for b in breaks(text)[1]], want, text[:30])

    def test_what_each_break_replaces(self):
        _, br = breaks(SOYBEANS)
        self.assertIn("FOB U.S. Gulf", br[-1]["now"])
        self.assertIn("CIF Rotterdam", br[-1]["before"])
        self.assertEqual(breaks(UREA)[1][0]["before"], "f.o.b. Black Sea")
        # the grade was the old one until June 2020: the new basis starts in July
        self.assertIn("no. 1", breaks(HRW)[1][0]["before"])
        self.assertIn("Saudi Arabian Light", breaks(DUBAI)[1][0]["before"])

    def test_current_basis_is_the_newest_clause(self):
        self.assertEqual(breaks(SOYBEANS)[0], "Soybeans, U.S. Soybeans, FOB U.S. Gulf")
        self.assertEqual(breaks(PALM)[0], "Palm oil (Malaysia), RBD, average export price FOB")
        self.assertIn("futures price", breaks(COAL_AUS)[0])
        self.assertEqual(breaks(COPPER)[0], COPPER)

    def test_the_first_month_of_the_data_is_not_a_break(self):
        self.assertEqual([b["at"] for b in breaks(SILVER, first="1962-01")[1]], ["1976-07"])
        self.assertEqual(breaks(DUBAI, first="1985-01")[1], [])

    def test_a_row_is_found_by_its_start_and_only_one(self):
        descs = ["Soybeans, from January 2025", "Soybean oil, from January 2025", "Soybean meal, from January 2025"]
        self.assertEqual(B.find(descs, "Soybeans,"), descs[0])
        with self.assertRaises(LookupError):
            B.find(descs, "Soybean")  # three rows
        with self.assertRaises(LookupError):
            B.find(descs, "Sunflower")  # none

    def test_estimates_marked_by_the_source(self):
        self.assertEqual(B.estimate_ranges("Coal (South Africa)", [], [SA_NOTE], "2026-10"),
                         [("2022-06", "2022-11"), ("2023-03", "2023-04"), ("2023-06", "2023-09"), ("2023-12", "2024-05")])
        self.assertEqual(B.estimate_ranges("Liquefied natural gas (Japan)", [LNG], [], "2026-10"), [("2026-09", "2026-10")])
        self.assertEqual(B.estimate_ranges("Copper (LME)", [COPPER], [SA_NOTE], "2026-10"), [])


class IronOre(unittest.TestCase):
    def test_spot_starts_where_the_sheet_says(self):
        self.assertEqual(P.contract_split(IRON), "2006-01")
        with self.assertRaises(P.BuildError):
            P.contract_split("Iron ore, spot in US dollar/dry ton.")

    def test_contract_years_are_their_own_annual_series(self):
        old = [(f"{y}-{m:02d}", 10.0 + (y - 1960)) for y in range(1960, 2006) for m in range(1, 13)]
        old[(1965 - 1960) * 12 + 4] = ("1965-05", 99.0)  # one month of 1965 differs in the source
        doc, meta = P._contract_series(old, IRON, "Updated on November 03, 2026")
        self.assertEqual((doc["freq"], doc["start"], len(doc["v"])), ("A", "1960", 46))
        self.assertEqual(doc["v"][5], 15.0)  # the value of eleven months, not the odd one
        self.assertEqual(meta["unit"], "US cents/dmtu")
        self.assertTrue(meta["closed"])
        self.assertIn("May 1965 reads 99 in the source", meta["basis"])
        self.assertEqual([b["at"] for b in meta["breaks"]], ["1987-01"])
        with self.assertRaises(P.BuildError):
            bad = [(m, v) for m, v in old]
            for i in range(0, 12, 2):
                bad[i] = (bad[i][0], 1.0 + i)  # a year of real monthly variation is not an annual price
            P._contract_series(bad, IRON, "")

    def test_built_data_never_joins_the_two_bases(self):
        idx = {m["id"]: m for m in jload("index.json")}
        spot, contract = idx["iron-ore-m"], idx["iron-ore-contract-a"]
        self.assertEqual(spot["start"], "2006-01")
        self.assertEqual(spot["unit"], "USD/dry t")
        self.assertEqual((contract["freq"], contract["unit"], contract["start"], contract["end"]), ("A", "US cents/dmtu", "1960", "2005"))
        doc = jload("iron-ore-contract-a.json")
        self.assertEqual(len(doc["v"]), 46)
        self.assertEqual(doc["v"][2005 - 1960], 65.0)
        self.assertEqual(jload("iron-ore-m.json")["v"][0], 67.2)
        self.assertEqual([b["at"] for b in spot["breaks"]], ["2008-12"])  # 63.5% Fe to 62% Fe


class AnnualRuns(unittest.TestCase):
    def test_years_of_twelve_identical_values(self):
        v = [5.0] * 12 + [1.0, 2.0] * 6 + [7.0] * 12 + [7.0] * 12 + [3.0] * 5
        self.assertEqual(P.annual_runs("1990-01", v), [[1990, 1990], [1992, 1993]])

    def test_a_partial_year_is_not_a_run(self):
        self.assertEqual(P.annual_runs("1990-07", [4.0] * 18), [[1991, 1991]])

    def test_none_is_not_a_value(self):
        self.assertEqual(P.annual_runs("1990-01", [None] * 12), [])

    def test_counts_on_the_built_files(self):
        idx = {m["id"]: m for m in jload("index.json")}
        self.assertEqual(idx["urea-m"]["annual"], [[1960, 1976]])
        self.assertEqual(idx["ttf-m"]["annual"], [[1960, 1990]])
        self.assertEqual(idx["gold-m"]["annual"], [[1960, 1967]])
        self.assertNotIn("annual", idx["copper-m"])


class BoardStats(unittest.TestCase):
    def test_daily_changes_and_range(self):
        times = [date(2025, 11, 17), date(2025, 12, 31), date(2026, 8, 17), date(2026, 10, 16), date(2026, 11, 10), date(2026, 11, 17)]
        st = P.board_stats("D", times, [80, 100, 120, 140, 150, 165])
        self.assertEqual(st["last"], {"v": 165, "t": "2026-11-17"})
        self.assertEqual(st["chg"], {"m": 17.86, "q": 37.5, "ytd": 65.0, "y": 106.25, "w": 10.0})
        # the 52-week window starts after 17 Nov 2025, so the year-ago price is outside it
        self.assertEqual(st["rng"], {"lo": 100, "hi": 165, "pos": 1.0})

    def test_a_reference_too_far_back_gives_no_change(self):
        st = P.board_stats("D", [date(2026, 11, 17), date(2026, 11, 3)], [165, 150])
        self.assertNotIn("w", st.get("chg", {}))  # nothing within 7 days before 10 Nov
        self.assertEqual(P.board_stats("D", [date(2026, 11, 17)], [165])["rng"], {"lo": 165, "hi": 165})

    def test_monthly_changes_and_range(self):
        times = P.month_times("2025-10", 13)
        st = P.board_stats("M", times, [50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170])
        self.assertEqual(st["last"], {"v": 170, "t": "2026-10"})
        self.assertEqual(st["chg"], {"m": 6.25, "q": 21.43, "ytd": 142.86, "y": 240.0})
        self.assertEqual(st["rng"], {"lo": 60, "hi": 170, "pos": 1.0})

    def test_trailing_gaps_and_non_positive_references(self):
        st = P.board_stats("M", P.month_times("2026-08", 4), [0, 0, 20, None])
        self.assertEqual(st["last"]["t"], "2026-10")
        self.assertNotIn("chg", st)  # a zero reference gives no percentage
        self.assertIsNone(P.board_stats("M", P.month_times("2026-08", 2), [None, None]))

    def test_month_arithmetic_stops_at_the_end_of_a_short_month(self):
        self.assertEqual(P._add_months(date(2026, 3, 31), -1), date(2026, 2, 28))
        self.assertEqual(P._add_months(date(2026, 1, 15), -12), date(2025, 1, 15))

    def test_built_index_carries_the_board(self):
        idx = jload("index.json")
        for m in idx:
            if m["freq"] in ("D", "M"):
                self.assertIn("stats", m, m["id"])
                self.assertEqual(m["stats"]["last"]["t"][:7], m["end"][:7], m["id"])
                self.assertEqual("w" in m["stats"].get("chg", {}) or m["freq"] == "M", True, m["id"])
        wti = next(m for m in idx if m["id"] == "wti-d")
        doc = jload("wti-d.json")
        self.assertEqual(wti["stats"]["last"]["v"], doc["v"][-1])


class Freshness(unittest.TestCase):
    def meta(self, sid, freq, end, s="eia-spot", **kw):
        return {"id": sid, "freq": freq, "end": end, "s": s, **kw}

    def test_a_daily_series_that_stopped_is_reported(self):
        metas = [self.meta("a-d", "D", "2026-11-17"), self.meta("b-d", "D", "2026-09-30")]
        late = P.check_freshness(metas, date(2026, 11, 23))
        self.assertEqual([(s, i) for s, i, _ in late], [("eia-spot", "b-d")])

    def test_a_week_old_daily_series_is_not_late(self):
        self.assertEqual(P.check_freshness([self.meta("a-d", "D", "2026-11-17")], date(2026, 11, 30)), [])

    def test_a_monthly_series_is_late_when_the_next_month_is_overdue(self):
        m = [self.meta("a-m", "M", "2026-10", "wb-pink")]
        self.assertEqual(P.check_freshness(m, date(2026, 12, 14)), [])
        self.assertEqual(len(P.check_freshness(m, date(2026, 12, 16))), 1)

    def test_a_series_far_behind_its_source_is_late_even_when_the_file_is_new(self):
        metas = [self.meta("a-m", "M", "2026-10", "wb-pink"), self.meta("b-m", "M", "2026-02", "wb-pink")]
        late = P.check_freshness(metas, date(2026, 11, 23))
        self.assertEqual([i for _, i, _ in late], ["b-m"])

    def test_closed_hidden_and_annual_series_are_not_checked(self):
        metas = [self.meta("c-a", "A", "2005", "wb-pink", closed=True), self.meta("r-a", "A", "2025", "wb-pink", hidden=True),
                 self.meta("x-m", "M", "2005-12", "wb-pink", closed=True)]
        self.assertEqual(P.check_freshness(metas, date(2026, 11, 23)), [])

    def test_message_per_source(self):
        out = P.stale_by_source([self.meta("b-d", "D", "2026-09-30"), self.meta("a-m", "M", "2026-01", "wb-pink")], date(2026, 11, 23))
        self.assertEqual(sorted(out), ["eia-spot", "wb-pink"])
        self.assertIn("b-d ends 2026-09-30", out["eia-spot"])

    def test_the_built_index_has_no_late_series(self):
        idx = jload("index.json")
        # the freight proxy is optional (FRED needs a key) and the checkout date is not the build date: read the file's own end
        late = P.check_freshness([m for m in idx if m["s"] != "fred"], date(2026, 11, 23))
        self.assertEqual(late, [])


def workbook(path, header_overrides=None, drop_description=None):
    """A minimal Pink Sheet workbook with every mapped column, description row and index column."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Monthly Prices"
    cols = ["Crude oil, Brent"] + [c for c in P.PINK if c != "Crude oil, Brent"]
    header = {c: c for c in cols}
    header.update(header_overrides or {})
    ws.append(["World Bank Commodity Price Data (The Pink Sheet)"])
    ws.append(["Updated on November 03, 2026"])
    ws.append([None] + [header[c] for c in cols])
    ws.append([None] + ["($/mt)"] * len(cols))
    for y in range(1960, 2027):
        for m in range(1, 13):
            ws.append([f"{y}M{m:02d}"] + [1.0 + m] * len(cols))
    wi = wb.create_sheet("Monthly Indices")
    for _ in range(4):
        wi.append([])
    labels = {j: label for j, (_, _, label) in P.INDEX_COLS.items()}
    wi.append([None] + [labels[j] for j in range(1, 17)])
    for _ in range(3):
        wi.append([])
    wi.append(["1960M01"] + [1.0] * 16)
    wd = wb.create_sheet("Description")
    rows = list(P.PINK_DESC.values()) + [P.IRON_ORE_ROW]
    for r in rows:
        if r != drop_description:
            wd.append([None, r + " (description text of the row)", None] + [None] * 16 + ["Source"])
    wb.save(path)


class WorkbookShape(unittest.TestCase):
    def check(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "w.xlsx")
            workbook(p, **kw)
            return P.Pink(p).check()

    def test_a_complete_workbook_has_no_problem(self):
        self.assertEqual(self.check(), [])

    def test_decorations_of_the_header_do_not_matter(self):
        self.assertEqual(self.check(header_overrides={"Urea": "Urea ", "Potassium chloride": "Potassium chloride **", "Coal, South African": "Coal, South African **"}), [])
        self.assertEqual(P.norm("Rice, Thai 5% "), "Rice, Thai 5%")

    def test_one_renamed_column_is_a_problem(self):
        problems = self.check(header_overrides={"Urea": "Urea (prill)"})
        self.assertEqual(problems, ["column 'Urea' missing"])

    def test_one_missing_description_row_is_a_problem(self):
        problems = self.check(drop_description="Sunflower oil")
        self.assertEqual(len(problems), 1)
        self.assertIn("Sunflower oil", problems[0])

    def test_the_download_check_refuses_it(self):
        import fetch_prices  # noqa: F401  (pipeline/prices on the path)

        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "w.xlsx")
            workbook(p, header_overrides={"Urea": "Urea (prill)"})
            with self.assertRaises(ValueError) as e:
                fetch_prices.check_pink(p)
            self.assertIn("missing", str(e.exception))

    def test_every_column_of_the_real_workbook_is_mapped_or_left_out_on_purpose(self):
        path = os.path.join(ROOT, "raw", "worldbank", "CMO-Historical-Data-Monthly.xlsx")
        if not os.path.exists(path):
            self.skipTest("raw/ is not tracked: the workbook is not on this machine")
        p = P.Pink(path)
        self.assertEqual(p.check(), [])
        unknown = [c for c in p.header if c not in P.PINK and c not in P.PINK_LEFT_OUT]
        self.assertEqual(unknown, [])


class UsgsPrices(unittest.TestCase):
    HEAD = "MCS chapter,Section,Commodity,Country,Statistics,Statistics_detail,Unit,Year,Value,Notes,Is critical mineral 2025,Other notes\n"

    def csv(self, rows):
        body = ""
        for com, stat, detail, year, value, notes in rows:
            body += f'X,Salient Statistics\u2014United States,{com},United States,{stat},"{detail}",dollars per metric ton,{year},"{value}","{notes}",No,"(Data)"\n'
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "MCS2026_Commodities_Data.csv")
            with open(p, "wb") as f:
                f.write((self.HEAD + body).encode("cp1252"))
            return P.usgs_series(p)

    def test_annual_prices_keep_the_files_unit_and_mark_the_estimated_year(self):
        detail = "Price, annual average-real, battery-grade lithium carbonate, dollars per metric ton"
        rows = [("Lithium", "Price", detail, y, v, n) for y, v, n in
                [(2021, "11,700", "Source: Benchmark."), (2022, "63,700", "Source: Benchmark."), (2023, "39,000", "Source: Benchmark."),
                 (2024, "11,800", "Source: Benchmark."), (2025, "9,000", "Estimated. -- Source: Benchmark.")]]
        rows.append(("Lithium", "Production", "Production", 2021, "1", ""))  # not a price
        found, missing = self.csv(rows)
        doc, meta = next((d, m) for d, m in found if m["id"] == "usgs-lithium-carbonate-a")
        self.assertEqual((doc["freq"], doc["start"], doc["v"]), ("A", "2021", [11700.0, 63700.0, 39000.0, 11800.0, 9000.0]))
        self.assertEqual((meta["unit"], meta["s"], meta["est"]), ("USD/t", "usgs-mcs", [["2025-01", "2025-12"]]))
        self.assertIn("battery-grade lithium carbonate", meta["basis"])
        self.assertNotIn("Estimated", meta["basis"])
        self.assertIn("usgs-manganese-ore-a", missing)  # no rows for it in this file: said, not skipped silently

    def test_a_series_with_a_hole_in_its_years_is_refused(self):
        detail = "Price, average, dollars per kilogram: Dysprosium oxide, 99.5% minimum"
        rows = [("Dysprosium", "Price", detail, y, "5", "") for y in (2021, 2022, 2024)]
        found, missing = self.csv(rows)
        self.assertIn("usgs-dy-oxide-a", missing)

    def test_annual_board_figures(self):
        st = P.board_stats("A", [date(2023, 1, 1), date(2024, 1, 1), date(2025, 1, 1)], [100.0, 120.0, 90.0])
        self.assertEqual(st, {"last": {"v": 90.0, "t": "2025"}, "chg": {"y": -25.0}})

    def test_built_files(self):
        idx = {m["id"]: m for m in jload("index.json")}
        with open(os.path.join(ROOT, "data", "commodities", "index.json"), encoding="utf-8") as f:
            commodities = {c["id"] for c in json.load(f)}
        usgs = [m for m in idx.values() if m["s"] == "usgs-mcs"]
        self.assertEqual(len(usgs), len(P.USGS_PRICES))
        for m in usgs:
            self.assertIn(m["k"], commodities, m["id"])  # a page to link to
            self.assertEqual(m["freq"], "A")
            self.assertEqual([m["start"], m["end"]], ["2021", "2025"])
        self.assertEqual(jload("usgs-lithium-carbonate-a.json")["v"], [11700.0, 63700.0, 39000.0, 11800.0, 9000.0])
        self.assertEqual(jload("usgs-alumina-import-a.json")["v"][0], 462.0)
        self.assertEqual({m["k"] for m in usgs}, {"lithium", "manganese", "rare-earths", "bauxite", "cobalt", "pgm"})


class WeeklyJobRecordsFrozenSeries(unittest.TestCase):
    """fetch_prices.main() with the network and the build stubbed: what it records in data/_status for a series that froze."""

    class FakeStatus:
        def __init__(self):
            self.calls = []

        def get(self, source):
            return {}

        def record_success(self, source, **kw):
            self.calls.append(("ok", source))

        def record_failure(self, source, error, **kw):
            self.calls.append(("fail", source, str(error)))

    def run_job(self, late, build_error=None):
        import fetch_prices as F

        fake = self.FakeStatus()
        saved = {k: getattr(F, k) for k in ("status", "fetch_pink", "fetch_eia", "fetch_fred", "rebuild", "late_series")}
        try:
            F.status = fake
            F.fetch_pink = lambda stage: ({"records": 800, "data_to": "2026-10", "state": {}}, None)
            F.fetch_eia = lambda stage: ({"records": 9, "data_to": "2026-11-17", "state": {"last": {}}}, None, 8)
            F.fetch_fred = lambda stage: (None, None, 0)
            F.late_series = lambda: late

            def rebuild():
                if build_error:
                    raise RuntimeError(build_error)

            F.rebuild = rebuild
            with open(os.devnull, "w") as dn, __import__("contextlib").redirect_stdout(dn):
                F.main()
        finally:
            for k, v in saved.items():
                setattr(F, k, v)
        return fake.calls

    def test_nothing_late_is_a_success(self):
        self.assertEqual(self.run_job({}), [("ok", "wb-pink"), ("ok", "eia-spot")])

    def test_a_frozen_eia_series_is_a_failure_even_though_the_download_worked(self):
        calls = self.run_job({"eia-spot": "late series: wti-d ends 2026-09-30, 54 days ago"})
        self.assertEqual(calls[0], ("ok", "wb-pink"))
        self.assertEqual(calls[1][:2], ("fail", "eia-spot"))
        self.assertIn("wti-d", calls[1][2])

    def test_a_frozen_pink_series_is_a_failure(self):
        calls = self.run_job({"wb-pink": "late series: copper-m ends 2026-01"})
        self.assertEqual(calls[0][:2], ("fail", "wb-pink"))
        self.assertIn("copper-m", calls[0][2])

    def test_a_failed_build_is_recorded_for_both_sources(self):
        calls = self.run_job({}, build_error="build_prices failed: pink sheet does not have the expected shape")
        self.assertEqual([c[:2] for c in calls], [("fail", "wb-pink"), ("fail", "eia-spot")])
        self.assertIn("expected shape", calls[0][2])

    def test_late_series_reads_the_index_and_ignores_the_optional_fred_source(self):
        import fetch_prices as F

        with tempfile.TemporaryDirectory() as d:
            idx = [{"id": "x-d", "freq": "D", "s": "eia-spot", "end": "2020-01-01", "k": "k"},
                   {"id": "freight-ppi-m", "freq": "M", "s": "fred", "end": "2020-01", "k": "freight"}]
            with open(os.path.join(d, "index.json"), "w") as f:
                json.dump(idx, f)
            saved = F.DATA_PRICES
            F.DATA_PRICES = d
            try:
                with open(os.devnull, "w") as dn, __import__("contextlib").redirect_stdout(dn):
                    late = F.late_series()
            finally:
                F.DATA_PRICES = saved
        self.assertEqual(list(late), ["eia-spot"])


class CheckoutWithoutTheOtherDownloads(unittest.TestCase):
    """CI has no raw/ at the start: the annual workbook and the USGS file are absent, and the build keeps the series
    it cannot rebuild (real prices, USGS prices) from the previous files instead of dropping them."""

    def test_old_series_survive_and_stay_linked(self):
        import shutil

        pink = os.path.join(ROOT, "raw", "worldbank", "CMO-Historical-Data-Monthly.xlsx")
        eia = os.path.join(ROOT, "raw", "eia-spot")
        if not (os.path.exists(pink) and os.path.isdir(eia)):
            self.skipTest("raw/ is not tracked: the downloads are not on this machine")
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "prices")
            shutil.copytree(DATA, out)
            before = {m["id"]: m for m in jload("index.json")}
            saved = (P.OUT, P.usgs_file, sys.argv)
            P.OUT, P.usgs_file, sys.argv = out, (lambda _d: None), ["build_prices.py", pink, eia, os.path.join(d, "no-annual.xlsx")]
            try:
                with open(os.devnull, "w") as dn, __import__("contextlib").redirect_stdout(dn):
                    P.main()
            finally:
                P.OUT, P.usgs_file, sys.argv = saved
            with open(os.path.join(out, "index.json"), encoding="utf-8") as f:
                after = {m["id"]: m for m in json.load(f)}
        self.assertEqual(sorted(after), sorted(before))
        self.assertEqual(after["copper-m"]["real"], "copper-real-a")
        self.assertEqual(after["brent-d"]["real"], "brent-real-a")
        self.assertEqual(after["usgs-lithium-carbonate-a"]["stats"], before["usgs-lithium-carbonate-a"]["stats"])
        self.assertEqual(after["copper-m"], before["copper-m"])


class Validation(unittest.TestCase):
    def test_a_negative_last_price_is_a_price(self):
        self.assertTrue(P.valid([1.0] * 30 + [-36.98], "D"))

    def test_too_short_or_not_a_number_is_rejected(self):
        self.assertFalse(P.valid([1.0] * 10, "M"))
        self.assertFalse(P.valid([1.0] * 30 + [float("nan")], "M"))
        self.assertTrue(P.valid([1.0] * 12, "A"))

    def test_numbers_in_cells(self):
        self.assertEqual(P.num("1,234.5"), 1234.5)
        self.assertIsNone(P.num("…"))
        self.assertIsNone(P.num(".."))
        self.assertIsNone(P.num(True))


class BuiltData(unittest.TestCase):
    def setUp(self):
        self.idx = jload("index.json")
        self.by = {m["id"]: m for m in self.idx}

    def test_every_listed_series_has_a_file_of_the_same_range(self):
        for m in self.idx:
            doc = jload(m["id"] + ".json")
            self.assertEqual(doc["freq"], m["freq"], m["id"])
            if m["freq"] == "D":
                self.assertEqual(doc["d"], sorted(set(doc["d"])), m["id"])
                self.assertEqual(len(doc["d"]), len(doc["v"]), m["id"])
            elif m["freq"] == "M":
                self.assertEqual(doc["start"], m["start"], m["id"])
                y, mo = int(m["start"][:4]), int(m["start"][5:7])
                n = len(doc["v"]) - 1
                self.assertEqual(f"{y + (mo - 1 + n) // 12}-{(mo - 1 + n) % 12 + 1:02d}", m["end"], m["id"])
            else:
                self.assertEqual(int(m["end"]) - int(m["start"]) + 1, len(doc["v"]), m["id"])

    def test_the_documented_basis_changes_are_there(self):
        at = lambda sid: [b["at"] for b in self.by[sid].get("breaks", [])]  # noqa: E731
        self.assertIn("2020-01", at("potash-m"))
        self.assertIn("2022-03", at("urea-m"))
        self.assertIn("2025-01", at("soybeans-m"))
        self.assertIn("2025-01", at("soymeal-m"))
        self.assertIn("2025-01", at("soyoil-m"))
        self.assertEqual(at("palm-oil-m")[-4:], ["2021-01", "2024-11", "2025-02", "2026-01"])
        self.assertIn("2025-06", at("gold-m"))
        self.assertIn("2020-07", at("wheat-hrw-m"))
        self.assertIn("2022-02", at("coal-aus-m"))
        self.assertIn("1985-01", at("dubai-m"))

    def test_every_pink_series_has_a_basis(self):
        for m in self.idx:
            if m["s"] == "wb-pink" and not m.get("hidden"):
                self.assertTrue(m.get("basis"), m["id"])
            if m["s"] == "eia-spot":
                self.assertIn("EIA series", m["basis"], m["id"])

    def test_estimates_of_the_source_are_kept(self):
        self.assertEqual(self.by["coal-zaf-m"]["est"][0], ["2022-06", "2022-11"])
        self.assertEqual(self.by["lng-japan-m"]["est"], [["2026-09", "2026-10"]])

    def test_real_prices_name_their_deflator(self):
        reals = [m for m in self.idx if m.get("hidden")]
        self.assertGreater(len(reals), 30)
        for m in reals:
            self.assertEqual(m["freq"], "A")
            self.assertIn("2010", m["unit"])
            self.assertIn("Manufacturers Unit Value Index", m["basis"])
            self.assertIn(m["realOf"] + "", self.by)
            self.assertEqual(self.by[m["realOf"]]["real"], m["id"])
        self.assertIn("muv-a", self.by)
        self.assertEqual(self.by["iron-ore-real-a"]["start"], "2006")  # the contract years are not deflated into the spot series

    def test_a_commodity_still_opens_on_its_original_benchmark(self):
        # the pages and the event pages open the first series of a commodity: added series come after it
        first = {}
        for m in self.idx:
            if not m.get("hidden"):
                first.setdefault(m["k"], m["id"])
        for k, sid in [("crude-oil", "brent-d"), ("natural-gas", "hh-d"), ("rice", "rice-thai-m"), ("sugar", "sugar-m"), ("phosphate", "dap-m"),
                       ("iron-ore", "iron-ore-m"), ("pgm", "platinum-m"), ("coffee", "arabica-m"), ("thermal-coal", "coal-aus-m")]:
            self.assertEqual(first[k], sid, k)

    def test_indices_and_new_series(self):
        self.assertEqual(len([m for m in self.idx if m["id"].startswith("idx-")]), 16)
        for sid in ("rice-thai25-m", "rice-viet-m", "sunflower-oil-m", "tsp-m", "sugar-eu-m", "sugar-us-m", "crude-avg-m"):
            self.assertIn(sid, self.by)
        self.assertEqual(self.by["sunflower-oil-m"]["fam"], "softs")  # no page in the atlas: grouped, not linked
        self.assertNotIn("fam", self.by["copper-m"])

    def test_the_series_that_existed_keep_their_numbers(self):
        # the other 44 files of the first build are unchanged; only iron ore was cut at the start of the spot series
        doc = jload("copper-m.json")
        self.assertEqual((doc["start"], len(doc["v"])), ("1960-01", 802))


if __name__ == "__main__":
    unittest.main()
