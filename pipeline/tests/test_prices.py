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
COAL_ZAF = ("Coal (South Africa), from January 2015, f.o.b. Richards Bay, NAR, 6,000 kcal/kg, sulfur less than 1%, forward month 1; "
            "from February 13, 2017 to December 2017, thermal NAR netback assessment f.o.b. Richards Bay 6,000 kcal/kg; "
            "during 2006-February 10, 2017 thermal NAR; during 2002-2005 6,200 kcal/kg (11,200 btu/lb), less than 1.0%, sulfur 16% ash; "
            "years 1990-2001 6390 kcal/kg (11,500 btu/lb)")
COCONUT = ("Coconut oil, from January 2025, CFR Europe; (Philippines/Indonesia) from November 2024, bulk, CIF Rotterdam; "
           "January 2021 to October 2024, crude, CIF Rotterdam; January 1999 to December 2020, crude, CIF NW Europe; previously, bulk, c.i.f. Rotterdam")
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


class OverlappingClauses(unittest.TestCase):
    """GP1.5: the source's own periods overlap in the Richards Bay row; they are not chained."""

    def test_richards_bay_breaks_are_in_date_order_and_chained(self):
        cur, br = breaks(COAL_ZAF)
        self.assertEqual([b["at"] for b in br], ["1990-01", "2002-01", "2006-01", "2017-02"])
        self.assertNotIn("2015-01", [b["at"] for b in br])
        for prev, b in zip(br, br[1:]):
            self.assertEqual(b["before"], prev["now"], b["at"])
        last = br[-1]
        self.assertEqual((last["now"], last["before"], last["to"]), ("thermal NAR netback assessment f.o.b. Richards Bay 6,000 kcal/kg", "thermal NAR", "2017-12"))
        self.assertIn("forward month 1", cur)  # the current basis stays the source's first clause

    def test_the_overlap_is_found_and_quoted_from_the_source(self):
        clauses = B.parse_clauses(COAL_ZAF)
        clash, dropped = B.overlapping(clauses)
        self.assertEqual([c["from"] for c in dropped], ["2015-01"])
        note = P.basis_note(breaks(COAL_ZAF)[0], clauses)
        self.assertIn("The dates in the source overlap", note)
        self.assertIn("\u201cCoal (South Africa), from January 2015, f.o.b. Richards Bay", note)
        self.assertIn("\u201cduring 2006-February 10, 2017 thermal NAR\u201d", note)

    def test_a_row_without_overlap_has_no_such_note(self):
        for text in (SOYBEANS, UREA, PALM, COCONUT, COAL_AUS, DUBAI, SILVER, HRW):
            self.assertEqual(B.overlapping(B.parse_clauses(text))[0], [], text[:25])
            self.assertNotIn("overlap", P.basis_note(breaks(text)[0], B.parse_clauses(text)))

    def test_periods_that_meet_in_one_month_do_not_overlap(self):
        # "February 10, 2017" ends a period and "February 13, 2017" starts the next one: the same month
        a = {"from": "2006-01", "to": "2017-02", "before": False}
        b = {"from": "2017-02", "to": "2017-12", "before": False}
        self.assertFalse(B._overlap(a, b))
        self.assertTrue(B._overlap(a, {"from": "2016-12", "to": None, "before": False}))

    def test_a_from_clause_runs_until_the_next_one_starts(self):
        # coconut oil: "from January 2025" and "from November 2024" are not an overlap
        self.assertEqual([b["at"] for b in breaks(COCONUT)[1]], ["1999-01", "2021-01", "2024-11", "2025-01"])

    def test_two_earlier_prior_clauses_chain_into_each_other(self):
        # silver: unrefined before 1962, Handy & Harman before July 1976, then the London fixing
        _, br = breaks(SILVER)
        self.assertEqual([(b["at"], b["before"], b["now"]) for b in br],
                         [("1962-01", "unrefined silver", "Handy & Harman"), ("1976-07", "Handy & Harman", "Silver (UK), 99.9% refined, London afternoon fixing")])

    def test_every_series_of_the_real_workbook_chains(self):
        path = os.path.join(ROOT, "raw", "worldbank", "CMO-Historical-Data-Monthly.xlsx")
        if not os.path.exists(path):
            self.skipTest("raw/ is not tracked: the workbook is not on this machine")
        p = P.Pink(path)
        overlapping = []
        for col, prefix in P.PINK_DESC.items():
            clauses = B.parse_clauses(B.find(p.descs, prefix))
            if B.overlapping(clauses)[0]:
                overlapping.append(col)
            br = B.basis_and_breaks(clauses, "1960-01", "2026-10")[1]
            self.assertEqual([b["at"] for b in br], sorted(b["at"] for b in br), col)
            for prev, b in zip(br, br[1:]):
                self.assertEqual(b["before"], prev["now"], f"{col} {b['at']}")
        # the rows whose own dates overlap: the coal row, and the barley row since M-023 published it ("from May 2012 onwards; during
        # 1980 - 2012 April Canadian ...": the atlas draws no break from the clause that starts inside another period)
        self.assertEqual(overlapping, ["Coal, South African", "Barley"])

    def test_every_built_series_chains(self):
        for m in jload("index.json"):
            br = m.get("breaks", [])
            self.assertEqual([b["at"] for b in br], sorted(b["at"] for b in br), m["id"])
            for prev, b in zip(br, br[1:]):
                self.assertEqual(b["before"], prev["now"], f"{m['id']} {b['at']}")
        coal = {m["id"]: m for m in jload("index.json")}["coal-zaf-m"]
        self.assertIn("overlap", coal["basis"])
        self.assertEqual([b["at"] for b in coal["breaks"]], ["1990-01", "2002-01", "2006-01", "2017-02"])


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
        # the checkout date is not the build date: a fixed date
        late = P.check_freshness(idx, date(2026, 11, 23))
        self.assertEqual(late, [])


def price_value(col, m):
    """The value of Monthly Prices column `col` (0-based among the mapped columns) in month number m: distinct per column."""
    return 100.0 * (col + 1) + m * 0.01


def index_value(label, m):
    """The value of the Monthly Indices column `label` in month number m: distinct per column and from every price."""
    known = list(P.INDEX_SERIES)
    return 90000.0 + 1000.0 * (known.index(label) if label in known else len(known)) + m * 0.01


def workbook(path, header_overrides=None, drop_description=None, index_order=None, index_months=None, index_title=None):
    """A minimal Pink Sheet workbook with every mapped column, description row and index column. Every column of
    every sheet holds its own numbers, so a series read from the wrong column or the wrong sheet is seen. The header
    of Monthly Indices is spread over four rows, as in the real workbook (a column is named by the text above it)."""
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
    n = 0
    for y in range(1960, 2027):
        for m in range(1, 13):
            # iron ore repeats one value over the twelve months of a year, as its contract years do in the sheet
            ws.append([f"{y}M{m:02d}"] + [price_value(j, n // 12 * 12 if cols[j] == "Iron ore, cfr spot" else n) for j in range(len(cols))])
            n += 1
    wi = wb.create_sheet("Monthly Indices")
    labels = list(index_order or P.INDEX_SERIES)
    wi.append(["World Bank Commodity Price Data (The Pink Sheet)"])
    wi.append([index_title or "monthly indices based on nominal US dollars, 2010=100, 1960 to present"])
    wi.append(["(monthly series are available only in nominal US dollar terms)"])
    wi.append(["Updated on November 03, 2026"])
    for level in range(4):  # the label of column j sits on the row of its level: the header is a staircase
        wi.append([None] + [(label + (" **" if level == 0 else "") if k % 4 == level else None) for k, label in enumerate(labels)])
    n = 0
    for y in range(1960, 2027):
        for m in range(1, 13):
            if index_months is None or n < index_months:
                wi.append([f"{y}M{m:02d}"] + [index_value(label, n) for label in labels])
            n += 1
    wd = wb.create_sheet("Description")
    rows = list(P.PINK_DESC.values()) + [P.IRON_ORE_ROW]
    for r in rows:
        if r != drop_description:
            wd.append([None, (IRON if r == P.IRON_ORE_ROW else r + " (description text of the row)"), None] + [None] * 16 + ["Source"])
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
        saved = {k: getattr(F, k) for k in ("status", "fetch_pink", "fetch_eia", "fetch_freight", "rebuild", "late_series")}
        try:
            F.status = fake
            F.fetch_pink = lambda stage: ({"records": 800, "data_to": "2026-10", "state": {}}, None)
            F.fetch_eia = lambda stage: ({"records": 9, "data_to": "2026-11-17", "state": {"last": {}}}, None, 8)
            F.fetch_freight = lambda stage: {s: (None, None, False) for s in F.FREIGHT_SOURCES}
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
        return [c for c in fake.calls if c[1] in ("wb-pink", "eia-spot")]  # the freight sources: test_freight_indicators.py

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

    def test_late_series_reads_the_index_and_alerts_the_freight_sources_too(self):
        import fetch_prices as F

        with tempfile.TemporaryDirectory() as d:
            idx = [{"id": "x-d", "freq": "D", "s": "eia-spot", "end": "2020-01-01", "k": "k"},
                   {"id": "freight-ppi-m", "freq": "M", "s": "bls", "end": "2020-01", "k": "freight"},
                   {"id": "other-m", "freq": "M", "s": "elsewhere", "end": "2020-01", "k": "k"}]
            with open(os.path.join(d, "index.json"), "w") as f:
                json.dump(idx, f)
            saved = F.DATA_PRICES
            F.DATA_PRICES = d
            try:
                with open(os.devnull, "w") as dn, __import__("contextlib").redirect_stdout(dn):
                    late = F.late_series()
            finally:
                F.DATA_PRICES = saved
        self.assertEqual(sorted(late), ["bls", "eia-spot"])


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
        # sunflower oil had no page in the atlas (grouped, not linked: family "softs"); the sunflower page (M-023) now holds it
        self.assertEqual(self.by["sunflower-oil-m"]["k"], "sunflower")
        self.assertNotIn("fam", self.by["sunflower-oil-m"])
        self.assertNotIn("fam", self.by["copper-m"])

    def test_the_series_that_existed_keep_their_numbers(self):
        # the other 44 files of the first build are unchanged; only iron ore was cut at the start of the spot series
        doc = jload("copper-m.json")
        self.assertEqual((doc["start"], len(doc["v"])), ("1960-01", 802))


class IndexColumnsAreRead(unittest.TestCase):
    """GP1.1: the 16 index series hold the columns of 'Monthly Indices', found by the text above them."""

    def build(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "w.xlsx")
            workbook(path, **kw)
            p = P.Pink(path)
            problems = p.check()
            if problems:  # main() refuses such a workbook before it writes anything (test below)
                return p, problems, {}
            return p, problems, {m["id"]: (doc, m) for doc, m in P.pink_series(p)}

    def test_each_index_series_is_its_own_column_of_the_index_sheet(self):
        _, problems, built = self.build()
        self.assertEqual(problems, [])
        for k, (label, (sid, _)) in enumerate(P.INDEX_SERIES.items()):
            doc, meta = built[sid]
            self.assertEqual(len(doc["v"]), 67 * 12, sid)
            self.assertEqual(doc["start"], "1960-01", sid)
            self.assertEqual(doc["v"][0], index_value(label, 0), sid)
            self.assertEqual(doc["v"][-1], index_value(label, 67 * 12 - 1), sid)
            self.assertEqual(meta["unit"], "index (2010 = 100)")
            # never the 'Monthly Prices' column of the same position
            self.assertNotEqual(doc["v"][0], price_value(k + 1, 0), sid)

    def test_a_column_is_found_by_its_header_not_by_its_position(self):
        order = list(reversed(list(P.INDEX_SERIES)))
        _, problems, built = self.build(index_order=order)
        self.assertEqual(problems, [])
        for label, (sid, _) in P.INDEX_SERIES.items():
            self.assertEqual(built[sid][0]["v"][0], index_value(label, 0), sid)  # index_value is keyed by the label

    def test_the_header_of_the_four_rows_is_read_as_one_name_per_column(self):
        p, _, _ = self.build()
        names = p.index_headers()
        self.assertEqual(sorted(names.values()), sorted(P.INDEX_SERIES))
        self.assertEqual(len(names), 16)

    def test_a_renamed_or_missing_index_column_refuses_the_workbook(self):
        order = list(P.INDEX_SERIES)
        order[3] = "Agricultural products"
        _, problems, _ = self.build(index_order=order)
        self.assertEqual(problems, ["Monthly Indices column 'Agriculture' missing"])

    def test_an_index_sheet_that_covers_other_months_than_the_price_sheet_is_refused(self):
        _, problems, _ = self.build(index_months=100)
        self.assertEqual(problems, ["Monthly Indices and Monthly Prices do not cover the same months"])

    def test_a_change_of_base_is_refused(self):
        _, problems, _ = self.build(index_title="monthly indices based on nominal US dollars, 2015=100")
        self.assertEqual(problems, ["Monthly Indices is no longer a 2010 = 100 index"])

    def test_the_build_exits_before_writing_anything(self):
        with tempfile.TemporaryDirectory() as d:
            path, out = os.path.join(d, "w.xlsx"), os.path.join(d, "out")
            workbook(path, index_months=100)
            saved = (P.OUT, sys.argv)
            P.OUT, sys.argv = out, ["build_prices.py", path, os.path.join(d, "no-eia")]
            try:
                with self.assertRaises(SystemExit) as e:
                    P.main()
            finally:
                P.OUT, sys.argv = saved
            self.assertIn("do not cover the same months", str(e.exception))
            self.assertEqual(os.listdir(out), [])

    def test_the_built_indices_are_on_the_base_the_atlas_says(self):
        for m in jload("index.json"):
            if m["id"].startswith("idx-") or m["id"] == "ng-index-m":
                doc = jload(m["id"] + ".json")
                base = [v for i, v in enumerate(doc["v"]) if P.month_times(doc["start"], len(doc["v"]))[i].year == 2010]
                self.assertEqual(len(base), 12, m["id"])
                self.assertAlmostEqual(sum(base) / 12, 100.0, delta=0.5, msg=m["id"])
        muv = jload("muv-a.json")
        self.assertEqual(muv["v"][2010 - int(muv["start"])], 100)


class OpeningSeries(unittest.TestCase):
    """GP1.2: the series a commodity opens on is chosen, and a commodity with a monthly or daily series never opens on an annual one."""

    def setUp(self):
        self.idx = jload("index.json")

    def first(self):
        out = {}
        for m in self.idx:
            if not m.get("hidden"):
                out.setdefault(m["k"], m)
        return out

    def test_the_commodities_that_were_opening_on_the_wrong_series(self):
        first = self.first()
        self.assertEqual(first["bauxite"]["id"], "usgs-bauxite-import-a")  # bauxite, not alumina (a product)
        self.assertEqual(first["rare-earths"]["id"], "usgs-ndpr-oxide-a")  # NdPr oxide, not dysprosium
        self.assertEqual(first["cobalt"]["id"], "usgs-cobalt-spot-a")  # the cathode row names its product and its source

    def test_every_commodity_with_more_than_one_series_has_its_choice_and_it_is_applied(self):
        count = {}
        for m in self.idx:
            if not m.get("hidden") and m["k"] not in ("index", "freight"):
                count[m["k"]] = count.get(m["k"], 0) + 1
        many = sorted(k for k, n in count.items() if n > 1)
        self.assertEqual(sorted(P.OPENS_ON), many, "OPENS_ON names exactly the commodities that have more than one series")
        first = self.first()
        for k in many:
            with self.subTest(k):
                self.assertEqual(first[k]["id"], P.OPENS_ON[k], k)
        self.assertEqual(P.opening_problems(self.idx), [])

    def test_the_choice_never_opens_on_an_annual_series_when_a_faster_one_exists(self):
        for k, sid in P.OPENS_ON.items():
            series = [m for m in self.idx if m["k"] == k and not m.get("hidden")]
            best = min("DMA".index(m["freq"]) for m in series)
            self.assertEqual("DMA".index(next(m for m in series if m["id"] == sid)["freq"]), best, k)

    def test_a_series_added_later_without_a_choice_is_reported(self):
        metas = [{"id": "a-m", "k": "x", "freq": "M"}, {"id": "b-m", "k": "x", "freq": "M"}, {"id": "c-a", "k": "y", "freq": "A"}]
        self.assertEqual(P.opening_problems(metas), [("x", "2 series and no entry in OPENS_ON")])
        self.assertEqual(P.opening_problems([{"id": "usgs-alumina-import-a", "k": "bauxite", "freq": "A"}, {"id": "usgs-bauxite-import-a", "k": "bauxite", "freq": "A"}]),
                         [("bauxite", "opens on usgs-alumina-import-a, not on usgs-bauxite-import-a")])

    def test_the_order_of_the_builder(self):
        metas = [{"id": "usgs-alumina-import-a", "k": "bauxite", "freq": "A"}, {"id": "usgs-bauxite-import-a", "k": "bauxite", "freq": "A"},
                 {"id": "z-m", "k": "crude-oil", "freq": "M"}, {"id": "wti-d", "k": "crude-oil", "freq": "D"}, {"id": "brent-d", "k": "crude-oil", "freq": "D"}]
        metas.sort(key=P.order_key)
        self.assertEqual([m["id"] for m in metas], ["usgs-bauxite-import-a", "usgs-alumina-import-a", "brent-d", "wti-d", "z-m"])


class ClosedSeries(unittest.TestCase):
    """GP1.4: a series its publisher stopped is closed once, not a failure for ever."""

    def meta(self, sid, end, freq="M", s="wb-pink", **kw):
        return {"id": sid, "freq": freq, "end": end, "s": s, **kw}

    def test_a_monthly_series_seven_months_behind_its_source_is_closed(self):
        metas = [self.meta("a-m", "2026-10"), self.meta("tin-m", "2026-03"), self.meta("late-m", "2026-04")]
        self.assertEqual(P.mark_closed(metas), ["tin-m"])  # 7 months behind; 6 months behind is only late
        self.assertTrue(metas[1]["closed"])
        self.assertNotIn("closed", metas[2])

    def test_the_closed_series_no_longer_raises_the_freeze_alert_but_a_late_one_does(self):
        metas = [self.meta("a-m", "2026-10"), self.meta("tin-m", "2026-02"), self.meta("late-m", "2026-05")]
        today = date(2026, 11, 23)
        self.assertEqual([i for _, i, _ in P.check_freshness(metas, today)], ["tin-m", "late-m"])  # before the closing
        P.mark_closed(metas)
        self.assertEqual([i for _, i, _ in P.check_freshness(metas, today)], ["late-m"])  # a late series keeps its alert
        later = [i for _, i, _ in P.check_freshness(metas, date(2028, 1, 1))]
        self.assertIn("late-m", later)
        self.assertNotIn("tin-m", later)  # still not reported in a year
        self.assertEqual(P.stale_by_source(metas, today).keys(), {"wb-pink"})

    def test_a_source_that_is_late_as_a_whole_closes_nothing(self):
        metas = [self.meta("a-m", "2026-01"), self.meta("b-m", "2026-02")]  # the whole Pink Sheet is old
        self.assertEqual(P.mark_closed(metas), [])
        self.assertEqual(len(P.check_freshness(metas, date(2026, 11, 23))), 2)

    def test_a_daily_series_is_closed_after_120_days_behind_its_source(self):
        metas = [self.meta("a-d", "2026-11-17", "D", "eia-spot"), self.meta("b-d", "2026-07-20", "D", "eia-spot"), self.meta("c-d", "2026-07-10", "D", "eia-spot")]
        self.assertEqual(P.mark_closed(metas), ["c-d"])

    def test_annual_hidden_and_other_sources_are_left_alone(self):
        metas = [self.meta("a-m", "2026-10"), self.meta("x-a", "2005", "A", closed=True), self.meta("r-a", "2020", "A", hidden=True),
                 self.meta("f-m", "2020-01", s="fred")]
        self.assertEqual(P.mark_closed(metas), [])
        self.assertTrue(metas[1]["closed"])

    def test_a_series_that_resumes_is_no_longer_closed(self):
        metas = [self.meta("a-m", "2026-10"), self.meta("tin-m", "2026-10", closed=True)]
        P.mark_closed(metas)
        self.assertNotIn("closed", metas[1])

    def test_the_weekly_job_reports_the_closing_once(self):
        import fetch_prices as F

        class Status:
            def __init__(self):
                self.entries, self.calls = {}, []

            def get(self, source):
                return self.entries.get(source, {})

            def record_success(self, source, records=None, data_to=None, note="updated", state=None):
                self.calls.append(("ok", source, note))
                self.entries[source] = {"state": {**(self.entries.get(source, {}).get("state") or {}), **(state or {})}}

            def record_failure(self, source, error, **kw):
                self.calls.append(("fail", source, str(error)))

        fake = Status()
        saved = {k: getattr(F, k) for k in ("status", "fetch_pink", "fetch_eia", "fetch_freight", "rebuild", "late_series", "closed_series")}
        try:
            F.status = fake
            F.fetch_pink = lambda stage: ({"records": 800, "data_to": "2026-10", "state": {}}, None)
            F.fetch_eia = lambda stage: ({"records": 9, "data_to": "2026-11-17", "state": {"last": {}}}, None, 8)
            F.fetch_freight = lambda stage: {s: (None, None, False) for s in F.FREIGHT_SOURCES}
            F.rebuild = lambda: None
            F.late_series = lambda: {}  # a closed series is not late
            F.closed_series = lambda: {"wb-pink": {"tin-m": "2026-02"}}
            for _ in range(2):
                with open(os.devnull, "w") as dn, __import__("contextlib").redirect_stdout(dn):
                    F.main()
        finally:
            for k, v in saved.items():
                setattr(F, k, v)
        pink = [c for c in fake.calls if c[1] == "wb-pink"]
        self.assertEqual([c[0] for c in pink], ["ok", "ok"])  # never a failure
        self.assertEqual(pink[0][2], "updated; closed: tin-m (last period 2026-02)")
        self.assertEqual(pink[1][2], "updated")  # the second run does not report it again
        self.assertEqual(fake.entries["wb-pink"]["state"]["closed"], {"tin-m": "2026-02"})

    def test_the_built_index_has_none_closed_among_live_series_and_the_contract_series_is(self):
        idx = {m["id"]: m for m in jload("index.json")}
        self.assertTrue(idx["iron-ore-contract-a"]["closed"])
        # barley and sorghum (M-023): the World Bank stopped both in August 2020; they are published, closed, with their last month
        self.assertEqual([m["id"] for m in idx.values() if m.get("closed") and m["freq"] != "A"], ["barley-m", "sorghum-m"])
        for sid in ("barley-m", "sorghum-m"):
            self.assertEqual(idx[sid]["end"], "2020-08")


class AnnualJobRebuildsThePrices(unittest.TestCase):
    """The annual job rebuilds the prices after a new USGS edition (their annual series come from it)."""

    def run_process(self, changed, pending=()):
        sys.path.insert(0, os.path.join(ROOT, "pipeline", "annual"))
        import update_annual as U

        steps, commands = [], []
        saved = {k: getattr(U, k) for k in ("step", "run", "pending", "take_back_baci", "release_baci_backup")}
        try:
            U.step = lambda name, fn, paths: (steps.append((name, [os.path.relpath(p, ROOT) for p in paths])), fn(), True)[-1]
            U.run = lambda cmd, timeout: commands.append((os.path.basename(cmd[1]), timeout))
            U.pending = lambda name: name in pending
            U.take_back_baci = U.release_baci_backup = lambda: None
            U.process(changed)
        finally:
            for k, v in saved.items():
                setattr(U, k, v)
        return steps, commands

    def test_a_new_usgs_edition_rebuilds_the_prices(self):
        steps, commands = self.run_process({"usgs-mcs"})
        self.assertIn(("build-prices", [os.path.join("data", "prices")]), steps)
        self.assertIn(("build_prices.py", 300), commands)

    def test_other_sources_and_a_quiet_month_do_not(self):
        self.assertNotIn("build-prices", [n for n, _ in self.run_process({"eia-intl"})[0]])
        self.assertNotIn("build-prices", [n for n, _ in self.run_process(set())[0]])

    def test_a_failed_rebuild_is_run_again_next_time(self):
        self.assertIn("build-prices", [n for n, _ in self.run_process(set(), pending=("build-prices",))[0]])


class WhatIsNotInTheSource(unittest.TestCase):
    """GP1.6 and GP1.7: no remark of the atlas inside a basis note; twelve identical values are described as observed."""

    def test_no_unsourced_remark_in_a_basis_note(self):
        for m in jload("index.json"):
            basis = m.get("basis", "")
            self.assertNotIn("posted-price", basis, m["id"])
            self.assertNotIn("oil-indexed", basis, m["id"])
        by = {m["id"]: m for m in jload("index.json")}
        self.assertEqual(by["brent-m"]["basis"], "Crude oil, UK Brent 38` API.")
        self.assertEqual(by["lng-japan-m"]["basis"], "Liquefied natural gas (Japan), LNG, import price, cif.")

    def test_the_deflator_is_quoted_as_the_sheet_words_it(self):
        by = {m["id"]: m for m in jload("index.json")}
        self.assertIn("The sheet \u201cDefinitions\u201d says: \u201cConstant prices are prices which are deflated by the Manufacturers Unit Value Index (MUV).", by["muv-a"]["basis"])
        self.assertIn("Pailand", by["muv-a"]["basis"])  # the source's own spelling, quoted as it is
        self.assertIn("Annual average in constant 2010 US dollars. The sheet", by["copper-real-a"]["basis"])

    def test_gold_before_1968_is_twelve_identical_values_nothing_more(self):
        by = {m["id"]: m for m in jload("index.json")}
        self.assertEqual(by["gold-m"]["annual"], [[1960, 1967]])
        self.assertNotIn("annual", by["gold-m"]["basis"].lower())


class FiguresFile(unittest.TestCase):
    """GP1.10: a commodity page loads a small file, and the index is written compactly."""

    def test_the_index_is_written_without_indentation(self):
        with open(os.path.join(DATA, "index.json"), encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(text.count("\n"), 0)
        self.assertNotIn('", "', text[:2000])

    def test_one_figure_per_commodity_page_and_it_is_the_first_live_series(self):
        figures = jload("figures.json")
        idx = jload("index.json")
        self.assertLess(os.path.getsize(os.path.join(DATA, "figures.json")), 20000)
        self.assertLess(os.path.getsize(os.path.join(DATA, "figures.json")), os.path.getsize(os.path.join(DATA, "index.json")) / 4)
        first = {}
        # a closed series gives way to a live one of its commodity; barley and sorghum have no other (M-023)
        for closed in (False, True):
            for m in idx:
                if not (m.get("hidden") or bool(m.get("closed")) != closed or m["k"] in P.NO_PAGE or m["k"] == "freight"):
                    first.setdefault(m["k"], m)
        self.assertEqual(sorted(figures), sorted(first))
        self.assertTrue(figures["barley"]["closed"] and figures["sorghum"]["closed"])
        for k, f in figures.items():
            m = first[k]
            self.assertEqual({a: b for a, b in f.items()}, {a: m[a] for a in f})
            self.assertEqual(f["id"], m["id"])
            self.assertIn("stats", f)
            for dropped in ("breaks", "annual", "note", "real"):
                self.assertNotIn(dropped, f)
        for k in ("bauxite", "rare-earths", "cobalt"):
            self.assertEqual(figures[k]["id"], P.OPENS_ON[k])
            self.assertEqual(figures[k]["freq"], "A")


if __name__ == "__main__":
    unittest.main()
