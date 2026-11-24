"""Tests D01 to D07, D10 (count), D11, D13, D15 to D18 of the trade-engine plan (package E3-customs):
cleaning of the customs frame, the history rule, the checks and the caveats registry.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The lane and commodity-file forms of D04, D08, D09, D12 and D14 belong to later packages (E5, E6).
Checks that read raw/ are skipped when the file they need is absent.
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "commodities"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))

import pandas as pd  # noqa: E402

import caveats  # noqa: E402
import checks  # noqa: E402
import clean as C  # noqa: E402

RAW = os.path.join(ROOT, "raw")
HAS_PSD = os.path.exists(os.path.join(RAW, "usda", "psd_csv", "psd_alldata.csv"))
HAS_EIA = os.path.exists(os.path.join(RAW, "eia", "INTL.txt"))

_raw = None
_frames = {}
_findings = {}


def raw():
    global _raw
    if _raw is None:
        _raw = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
    return _raw


def frame(lpg_dedup="drop", bulk_repair="estimate"):
    key = (lpg_dedup, bulk_repair)
    if key not in _frames:
        _frames[key] = C.clean(raw(), lpg_dedup=lpg_dedup, bulk_repair=bulk_repair)
    return _frames[key]


def findings(lpg_dedup="drop"):
    if lpg_dedup not in _findings:
        _findings[lpg_dedup] = checks.run(frame(lpg_dedup), 2024)
    return _findings[lpg_dedup]


def mt(df, group, o=None, d=None, year=2024):
    m = (df.group == group) & (df.year == year)
    if o:
        m &= df.o == o
    if d:
        m &= df.d == d
    return float(df[m].t.sum()) / 1e6


def row(df, group, o, d, year):
    r = df[(df.group == group) & (df.o == o) & (df.d == d) & (df.year == year)]
    assert len(r) == 1, (group, o, d, year, len(r))
    return r.iloc[0]


class CleanTests(unittest.TestCase):
    def test_D01_iran_other_asia_is_not_taiwan(self):
        df = frame()
        for y, v in ((2019, 3.33), (2020, 24.16), (2021, 21.65), (2022, 26.23)):
            self.assertEqual(mt(df, "crude-oil", "IRN", "TWN", y), 0.0, y)
            self.assertAlmostEqual(mt(df, "crude-oil", "IRN", C.XAS, y), v, delta=0.01, msg=y)
            self.assertIn("xas", row(df, "crude-oil", "IRN", C.XAS, y).flag.split("+"))
        # Other exporters' "Other Asia" stays Taiwan (before 2019 Iran's too)
        self.assertGreater(mt(df, "crude-oil", "IRN", "TWN", 2018), 5)
        self.assertEqual(mt(df, "crude-oil", None, "S19", 2021), 0.0)

    def test_D02_taiwan_crude_imports(self):
        df = frame()
        for y, v in ((2019, 56.4), (2020, 49.0), (2021, 53.7), (2022, 57.9)):
            self.assertAlmostEqual(mt(df, "crude-oil", None, "TWN", y), v, delta=0.2, msg=y)
        self.assertAlmostEqual(mt(df, "crude-oil", "MEX", "TWN", 2021), 15.16, delta=0.01)

    def test_D03_qatar_lpg(self):
        df = frame("drop")
        for y in (2021, 2023):
            self.assertLessEqual(mt(df, "lpg", "QAT", year=y), 11, y)
        self.assertAlmostEqual(mt(df, "lpg", year=2021), 131.2, delta=1)
        self.assertAlmostEqual(mt(df, "lpg", year=2023), 135.8, delta=1)
        C.clean(raw()[raw().group == "lpg"], lpg_dedup="drop")  # LAST_DROPPED holds the rows of the last call
        dropped = pd.DataFrame(C.LAST_DROPPED)
        self.assertEqual(len(dropped[dropped.year == 2021]), 19)
        self.assertEqual(len(dropped[dropped.year == 2023]), 12)
        self.assertAlmostEqual(dropped[dropped.year == 2021].t.sum() / 1e6, 29.0, delta=0.5)
        self.assertAlmostEqual(dropped[dropped.year == 2023].t.sum() / 1e6, 26.8, delta=0.5)
        f = frame("flag")
        self.assertAlmostEqual(mt(f, "lpg", "QAT", year=2021), 39.0, delta=0.1)
        self.assertAlmostEqual(mt(f, "lpg", "QAT", year=2023), 36.9, delta=0.1)
        q = f[(f.group == "lpg") & (f.o == "QAT")]
        self.assertEqual(int((q[q.year == 2021].flag.str.contains("dup-suspect")).sum()), 19)
        self.assertEqual(int((q[q.year == 2023].flag.str.contains("dup-suspect")).sum()), 12)
        # the rule is not generalised: Malaysia's bauxite spike of 2015 is kept
        self.assertGreater(mt(df, "bauxite", "MYS", year=2015), 20)

    def test_D04_bauxite_guinea_china_2023(self):
        f = frame(bulk_repair="flag")
        r = row(f, "bauxite", "GIN", "CHN", 2023)
        self.assertAlmostEqual(r.t / 1e6, 13.79, delta=0.01)
        self.assertEqual(r.flag, "uv-suspect-t")
        self.assertFalse(r.imputed)
        e = frame(bulk_repair="estimate")
        r = row(e, "bauxite", "GIN", "CHN", 2023)
        self.assertTrue(90 <= r.t / 1e6 <= 110, r.t / 1e6)
        self.assertEqual(r.flag, "uv-repair")
        self.assertTrue(r.imputed)
        self.assertAlmostEqual(r.t0 / 1e6, 13.79, delta=0.01)
        self.assertIn("Atlas estimate", r.enote)
        self.assertIn("13.8 Mt", r.enote)  # the tonnage as reported by customs
        self.assertGreater(mt(e, "bauxite", year=2023), 150)
        self.assertEqual(C.BULK_REPAIR, "estimate")  # owner decision O3, 22 November 2026

    def test_D05_untouched_bulk_rows(self):
        for mode in ("flag", "estimate"):
            df = frame(bulk_repair=mode)
            for g, o, d, y, v in (("bauxite", "AUS", "CHN", 2024, 40.77), ("coal", "KAZ", "RUS", 2024, 17.28), ("iron-ore", "ZAF", "CHN", 2015, 23.77)):
                r = row(df, g, o, d, y)
                self.assertAlmostEqual(r.t / 1e6, v, delta=0.01, msg=(mode, g, o, d))
                self.assertFalse(r.imputed, (mode, g, o, d))
            self.assertEqual(row(df, "iron-ore", "ZAF", "CHN", 2015).flag, "uv-suspect")

    def test_D06_coal_mozambique_japan_2019(self):
        self.assertEqual(row(frame(bulk_repair="flag"), "coal", "MOZ", "JPN", 2019).flag, "uv-suspect-t")
        r = row(frame(bulk_repair="estimate"), "coal", "MOZ", "JPN", 2019)
        self.assertEqual(r.flag, "uv-repair")
        self.assertLessEqual(r.t / 1e6, 5)

    def test_D07_isolated_anomalies_count(self):
        df = frame()
        hit = df[df.flag.isin(["uv-suspect-t", "uv-suspect", "uv-repair"])]
        n = int(hit.group.isin(C.BULK).sum())
        self.assertTrue(35 <= n <= 47, n)
        # rule 7 is for the bulk groups; outside them only the rows that rules 3 and 4 keep as reported carry "uv-suspect-t" (package FNCB:
        # UV_KEPT_GROUPS and KEEP_REPORTED of clean.py)
        out = hit[~hit.group.isin(C.BULK)]
        self.assertTrue(set(out.flag) <= {"uv-suspect-t"}, set(out.flag))
        kept = out.group.isin(C.UV_KEPT_GROUPS) | pd.Series(list(zip(out.group, out.o, out.d, out.year)), index=out.index).isin(list(C.KEEP_REPORTED))
        self.assertTrue(bool(kept.all()), out[~kept][["group", "o", "d", "year"]].head())

    def test_D18_columns_and_compatibility(self):
        df = frame()
        for c in ("t", "t0", "imputed", "uvr", "uv", "flag", "uvp"):
            self.assertIn(c, df.columns)
        self.assertTrue(callable(C.despike))
        self.assertEqual(C.despike([10, 1, 10])[1], [1])
        # every row whose tonnage is estimated carries the note that says so
        self.assertTrue(df[df.imputed].enote.str.startswith("Atlas estimate").all())
        self.assertTrue(df[~df.imputed].enote.isna().all())
        # wheat RUS-EGY 2024 (tonnage missing in BACI): estimated from value, note with the declared value
        r = row(df, "wheat", "RUS", "EGY", 2024)
        self.assertTrue(r.imputed)
        self.assertAlmostEqual(r.t / 1e6, 11.056, delta=0.001)
        self.assertIn("USD 3.06 bn", r.enote)
        # defaults of the owner's decisions
        self.assertEqual(C.LPG_DEDUP, "drop")

    # ---- fixes after the review of group GE1 (package FE1)
    def test_GE1_1_a_repair_never_inflates_a_group(self):
        for mode in ("flag", "estimate"):
            df = frame(bulk_repair=mode)
            rep = df[df.t0 > 0]  # rows with a reported tonnage; a group-year of missing tonnage only has no base
            g = rep.groupby(["group", "year"]).agg(t=("t", "sum"), t0=("t0", "sum"))
            bad = g[g.t > 3 * g.t0 + 0.01e6]  # 10 kt of slack: diamonds 2003, 1 kt reported, rule 3 unchanged
            self.assertTrue(bad.empty, (mode, bad.head().to_dict()))
        df = frame()
        m = df[(df.group == "manganese") & (df.year == 2002)]
        bad = row(df, "manganese", "IND", "CHE", 2002)  # 23 Mt declared for USD 0.97 million
        self.assertIn("est-gross", bad.flag)
        others = m[m.index != bad.name]
        self.assertAlmostEqual(others.t.sum() / 1e6, others.t0.sum() / 1e6, delta=0.05)
        self.assertTrue(8 <= m.t.sum() / 1e6 <= 10, m.t.sum() / 1e6)
        self.assertEqual(int(m.imputed.sum()), 1)
        self.assertGreater(1000 * m.uv.iloc[0], 20)  # USD/t: not set by the bad row (0.04 USD/t)

    def test_GE1_3_repairs_move_towards_the_neighbours(self):
        df = frame()
        latest = int(df.year.max())
        t0 = df.set_index(["group", "o", "d", "year"]).t0
        rep = df[df.flag == "uv-repair"]
        self.assertTrue(len(rep) >= 20, len(rep))
        for r in rep.itertuples():
            yb = r.year + 1 if r.year < latest else r.year - 2
            nb = [t0[(r.group, r.o, r.d, y)] for y in (r.year - 1, yb)]
            lo, hi = min(nb), max(nb)
            if r.t0 < lo:
                self.assertTrue(r.t0 < r.t <= 2 * hi, (r.group, r.o, r.d, r.year))
            else:
                self.assertTrue(hi < r.t0 and 0.5 * lo <= r.t < r.t0, (r.group, r.o, r.d, r.year))
        # the value is the odd figure (VEN-USA), or the neighbours are no sound base (AUS-OMN): flagged only
        for g, o, d, y, v in (("iron-ore", "VEN", "USA", 2008, 0.33), ("alumina", "AUS", "OMN", 2014, 0.09)):
            r = row(df, g, o, d, y)
            self.assertEqual(r.flag, "uv-suspect", (g, o, d))
            self.assertFalse(r.imputed)
            self.assertAlmostEqual(r.t / 1e6, v, delta=0.01)

    def test_GE1_4_note_states_the_quantities_used(self):
        import re
        df = frame()
        rep = df[df.flag == "uv-repair"]
        for r in rep.itertuples():
            nums = [float(x.replace(",", "")) for x in re.findall(r"([\d,.]+) USD/t", r.enote)]
            uve, median = nums[2], nums[3]  # reported, second neighbour, the unit value used, the group median
            self.assertAlmostEqual(uve, r.uve, delta=max(0.006 * r.uve, 0.01), msg=r.enote)
            self.assertAlmostEqual(median, 1000 * r.uv, delta=max(0.006 * 1000 * r.uv, 0.01), msg=r.enote)
            ratio = float(re.search(r"\(([\d.]+) on average in", r.enote).group(1))
            self.assertAlmostEqual(ratio * 1000 * r.uv, r.uve, delta=0.002 * r.uve, msg=r.enote)
        r = row(df, "alumina", "KAZ", "RUS", 2003)
        self.assertIn("divided by 150 USD/t, the 2003 tonne-weighted median unit value of alumina (188 USD/t)", r.enote)

    def test_GE1_10_empty_frame_and_dropped_rows(self):
        e = C.clean(raw().head(0))
        self.assertEqual(len(e), 0)
        for c in ("t", "t0", "imputed", "flag", "enote"):
            self.assertIn(c, e.columns)
        full = C.clean(raw()[raw().group == "lpg"])
        C.clean(raw()[raw().group == "wheat"])  # a later call on other rows
        self.assertEqual(len(full.attrs["dropped"]), 31)
        self.assertEqual(C.LAST_DROPPED, [])
        early = raw()[raw().year <= 2005]
        c = C.clean(early)
        caveats.build(c, checks.run(c, 2005), 2005, psd=None)  # the Mexican entry starts later: no IndexError

    def test_GE1_11_no_value_is_not_estimated_to_zero(self):
        df = frame()
        nv = df[df.flag.str.contains("no-value")]
        self.assertGreaterEqual(len(nv), 3)
        self.assertFalse(nv.imputed.any())
        self.assertTrue((nv.t == nv.t0).all() and (nv.t > 0).all())
        self.assertFalse(((df.t <= 0) & df.imputed & (df.t0 > 0)).any())
        r = row(df, "corn", "NGA", "CHN", 2012)
        self.assertEqual((r.t, r.flag), (4296.0, "no-value"))


class PeerUnitValueTests(unittest.TestCase):
    """Rule 8 (audit C-034, review GR1.1): Chile's copper concentrate re-estimated at Peru's unit value times Chile's
    usual ratio to Peru, the median over the years in which Chile's declarations are in line."""

    def test_chile_china_2024(self):
        r = row(frame(), "copper-ore", "CHL", "CHN", 2024)
        self.assertAlmostEqual(r.t0 / 1e6, 2.787, delta=0.001)  # the figure of the entry, as reported
        self.assertIn("est-peer", r.flag)
        self.assertTrue(r.imputed)
        self.assertAlmostEqual(r.uvp, 7428, delta=1)
        k, ky = frame().attrs["peer"][("copper-ore", "CHL")]
        self.assertAlmostEqual(r.uve, 2234 * k, delta=1)  # Peru to China, 2024, times the usual ratio
        self.assertAlmostEqual(r.t / 1e6, 2.787 * 7428 / (2234 * k), delta=0.01)
        self.assertTrue(r.enote.startswith("Atlas estimate: CEPII BACI reports 2.79 Mt for USD 20.7 bn (7,428 USD/t)"), r.enote)
        self.assertIn("2,234 USD/t of copper concentrate from Peru to China in 2024", r.enote)
        self.assertIn(f"that unit value of Peru times {k:.3f}, the median ratio of Chile's unit value of copper concentrate to Peru's", r.enote)
        self.assertIn("plausible cause, not established here", r.enote)

    def test_usual_ratio_comes_from_the_years_in_line(self):
        k, ky = frame().attrs["peer"][("copper-ore", "CHL")]
        # in line: 2015 to 2020 and 2023 (Chile 0.93 to 1.17 times Peru); not: 2021, 2022, 2024 (about 2.7 times)
        self.assertTrue({2015, 2016, 2017, 2018, 2019, 2020, 2023} <= set(ky), ky)
        self.assertFalse({2003, 2004, 2021, 2022, 2024} & set(ky), ky)
        self.assertTrue(1.05 <= k <= 1.2, k)

    def test_years_in_gross_weight_are_untouched(self):
        df = frame()
        for y, v in ((2019, 7.73), (2020, 7.72), (2023, 7.40)):
            r = row(df, "copper-ore", "CHL", "CHN", y)
            self.assertNotIn("est-peer", r.flag, y)
            self.assertAlmostEqual(r.t / 1e6, v, delta=0.01)
        for y, v in ((2021, 2.55), (2022, 2.39)):
            r = row(df, "copper-ore", "CHL", "CHN", y)
            self.assertIn("est-peer", r.flag, y)
            self.assertAlmostEqual(r.t0 / 1e6, v, delta=0.01)
            self.assertTrue(6.5 <= r.t / 1e6 <= 8, (y, r.t))

    def test_totals_and_peer_untouched(self):
        df = frame()
        chl = df[(df.group == "copper-ore") & (df.o == "CHL") & (df.year == 2024)]
        self.assertAlmostEqual(chl.t0.sum() / 1e6, 4.96, delta=0.01)
        # no estimated year above Chile's largest year in line (12.85 Mt in 2019; 12.40 in 2020, 10.27 in 2023)
        tot = df[(df.group == "copper-ore") & (df.o == "CHL")].groupby("year").t.sum() / 1e6
        self.assertAlmostEqual(tot[2019], 12.9, delta=0.1)
        for y in (2021, 2022, 2024):
            self.assertTrue(10 <= tot[y] <= 12.85, (y, tot[y]))
        per = df[(df.group == "copper-ore") & (df.o == "PER")]
        self.assertFalse(per.flag.str.contains("est-peer").any())
        self.assertFalse(df[df.group != "copper-ore"].flag.str.contains("est-peer").any())
        self.assertAlmostEqual(mt(df, "copper-ore", o="PER"), 9.37, delta=0.01)

    def test_reference_falls_back_to_the_peer_average(self):
        rows = [  # Peru ships 1 Mt to China at 2,000 USD/t and 0.01 Mt to Bulgaria; Chile 1 Mt and 0.1 Mt at 7,000 USD/t
            (2024, "copper-ore", "PER", "CHN", 1e6, 2e6), (2024, "copper-ore", "PER", "BGR", 1e4, 2e4),
            (2024, "copper-ore", "CHL", "CHN", 1e6, 7e6), (2024, "copper-ore", "CHL", "BGR", 1e5, 7e5),
            (2024, "copper-ore", "CHL", "JPN", 1e6, 3.5e6),  # 1.75 times Peru: under the threshold
        ]
        df = C.clean(pd.DataFrame(rows, columns=["year", "group", "o", "d", "t", "usd"]))
        chn, bgr, jpn = (row(df, "copper-ore", "CHL", d, 2024) for d in ("CHN", "BGR", "JPN"))
        self.assertAlmostEqual(chn.t, 3.5e6, delta=1)  # no year in line: ratio 1
        self.assertIn("from Peru to China", chn.enote)
        self.assertIn("times 1 (no year in which Chile's declarations are in line)", chn.enote)
        self.assertAlmostEqual(bgr.uve, 2000, delta=0.5)  # Peru's average of the year: its Bulgarian flow is under 50 kt
        self.assertIn("from Peru to all destinations", bgr.enote)
        self.assertEqual(jpn.flag, "")
        self.assertEqual(jpn.t, 1e6)

    def test_usual_ratio_scales_the_reference(self):
        rows = [  # 2023: Chile in line at 1.2 times Peru; 2024: Chile at 3.5 times Peru
            (2023, "copper-ore", "PER", "CHN", 1e6, 2e6), (2023, "copper-ore", "CHL", "CHN", 1e6, 2.4e6),
            (2024, "copper-ore", "PER", "CHN", 1e6, 2e6), (2024, "copper-ore", "CHL", "CHN", 1e6, 7e6),
        ]
        df = C.clean(pd.DataFrame(rows, columns=["year", "group", "o", "d", "t", "usd"]))
        self.assertEqual(df.attrs["peer"][("copper-ore", "CHL")], (1.2, [2023]))
        r = row(df, "copper-ore", "CHL", "CHN", 2024)
        self.assertAlmostEqual(r.uve, 2400, delta=0.5)
        self.assertAlmostEqual(r.t, 7e6 / 2.4, delta=1)
        self.assertIn("times 1.200, the median ratio", r.enote)
        self.assertIn("in the 1 year in which its declarations are in line (2023)", r.enote)
        self.assertEqual(row(df, "copper-ore", "CHL", "CHN", 2023).flag, "")


class HistoryTests(unittest.TestCase):
    def test_value_moved_with_tonnage_is_kept(self):
        s, f = C.history_flags([10.0, 1.0, 10.0], [100.0, 10.0, 100.0])
        self.assertEqual(s, [10.0, 1.0, 10.0])
        self.assertEqual(f, {1: "kept"})

    def test_unit_value_anomaly_is_blanked(self):
        s, f = C.history_flags([10.0, 1.0, 10.0], [100.0, 100.0, 100.0])
        self.assertEqual(s, [10.0, None, 10.0])
        self.assertEqual(f, {1: "suspect"})

    def test_no_record(self):
        s, f = C.history_flags([56.7, 0.0, 59.1], [100.0, 0.0, 100.0])
        self.assertEqual(s, [56.7, None, 59.1])
        self.assertEqual(f, {1: "nodata"})

    def test_estimated_years_are_marked(self):
        s, f = C.history_flags([10.0, 11.0, 30.0], [100.0, 110.0, 300.0], ["", "est-missing", "uv-repair"])
        self.assertEqual(s, [10.0, 11.0, 30.0])
        self.assertEqual(f, {1: "est", 2: "est"})

    def test_flagged_suspect_year(self):
        s, f = C.history_flags([10.0, 9.0, 10.0], [100.0, 900.0, 100.0], ["", "uv-suspect-t", ""])
        self.assertEqual(s, [10.0, None, 10.0])
        self.assertEqual(f, {1: "suspect"})

    def test_sustained_change_untouched(self):
        s, f = C.history_flags([10.0, 1.0, 1.0, 10.0], [100.0, 10.0, 10.0, 100.0])
        self.assertEqual((s, f), ([10.0, 1.0, 1.0, 10.0], {}))


class CheckTests(unittest.TestCase):
    def of(self, check, lpg_dedup="drop"):
        return [r for r in findings(lpg_dedup) if r["check"] == check]

    def test_D10_latest_year_check(self):
        k8 = self.of("K8")
        self.assertTrue(40 <= len(k8) <= 100, len(k8))
        corn = [r for r in k8 if r["group"] == "corn" and r["o"] == "USA" and r["d"] == "MEX"]
        self.assertEqual(len(corn), 1)
        self.assertIn("56% below 2023", corn[0]["text"])
        for r in findings():
            self.assertNotIn("provisional", " ".join(str(v) for v in r.values()).lower())

    @unittest.skipUnless(HAS_PSD, "raw/usda/psd_csv/psd_alldata.csv absent")
    def test_D11_psd_trader_totals(self):
        k1 = {(r["group"], r["side"], r["country"]): r for r in self.of("K1")}
        r = k1[("corn", "imports", "MEX")]
        self.assertAlmostEqual(r["value"], 7.80, delta=0.02)
        self.assertAlmostEqual(r["reference"][0], 24.22, delta=0.01)
        self.assertAlmostEqual(r["reference"][1], 25.93, delta=0.01)
        r = k1[("wheat", "exports", "TUR")]
        self.assertAlmostEqual(r["value"], 1.76, delta=0.02)
        self.assertAlmostEqual(r["reference"][0], 7.28, delta=0.01)
        self.assertAlmostEqual(r["reference"][1], 9.95, delta=0.01)

    @unittest.skipUnless(HAS_PSD, "raw/usda/psd_csv/psd_alldata.csv absent")
    def test_K2_bilateral_above_importer_total(self):
        k2 = {(r["group"], r["o"], r["d"], r["year"]): r for r in self.of("K2")}
        r = k2[("wheat", "RUS", "EGY", 2018)]
        self.assertAlmostEqual(r["value"], 17.56, delta=0.02)
        self.assertAlmostEqual(r["reference"], 12.41, delta=0.02)

    @unittest.skipUnless(HAS_EIA, "raw/eia/INTL.txt absent")
    def test_D13_crude_exports_against_production(self):
        k3 = {r["country"]: r for r in self.of("K3")}
        self.assertGreaterEqual(k3["MYS"]["ratio"], 2.2)
        self.assertAlmostEqual(k3["MYS"]["value"], 54.2, delta=0.1)
        self.assertAlmostEqual(k3["MYS"]["reference"], 23.9, delta=0.2)
        self.assertEqual(k3["MYS"]["level"], "flag")
        self.assertIn("ARE", k3)
        self.assertGreaterEqual(k3["ARE"]["ratio"], 0.95)

    def test_D15_exporter_spikes(self):
        k6 = {(r["group"], r["country"], r["year"]): r for r in self.of("K6", "flag") if r["kind"] == "spike"}
        for y in (2021, 2023):
            r = k6[("lpg", "QAT", y)]
            self.assertAlmostEqual(r["value"], {2021: 39.0, 2023: 36.9}[y], delta=0.1)
        r = k6[("bauxite", "MYS", 2015)]
        self.assertAlmostEqual(r["value"], 25.5, delta=0.1)
        # after the Qatari rule, the LPG spikes are gone
        k6d = {(r["group"], r["country"], r["year"]) for r in self.of("K6") if r["kind"] == "spike"}
        self.assertNotIn(("lpg", "QAT", 2021), k6d)

    def test_D16_no_raw_folder(self):
        with tempfile.TemporaryDirectory() as empty:
            ran = set()
            out = checks.run(frame(), 2024, raw=empty, ran=ran)
        # K13 (unit values far below the others of a product) reads the frame only, like K6 to K8: it needs no raw file
        self.assertTrue({r["check"] for r in out} <= {"K6", "K7", "K8", "K11", "K13"})
        self.assertTrue({"K6", "K7", "K8"} <= ran)
        self.assertFalse({"K1", "K2", "K3", "K4", "K10"} & ran)
        # previous records of the checks that did not run are kept by merge()
        prev = [{"check": "K1", "text": "old"}, {"check": "K8", "text": "old"}]
        merged = checks.merge(prev, out, ran)
        self.assertIn({"check": "K1", "text": "old"}, merged)
        self.assertNotIn({"check": "K8", "text": "old"}, merged)

    def test_GE1_5_run_never_raises(self):
        import json
        import numpy as np
        small = frame()[frame().year >= 2020]
        layouts = {"psd": {"usda/psd_csv/psd_alldata.csv": "a,b\n1,2\n"},
                   "mcs": {"usgs/MCS2026_Commodities_Data.csv": "x\n"},
                   "intl": {"eia/INTL.txt": 'hello\n{"series_id": "INTL.1-2-USA-X.A", "data": []}\n'}}
        for name, files in layouts.items():
            with tempfile.TemporaryDirectory() as d:
                for rel, text in files.items():
                    os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True)
                    with open(os.path.join(d, rel), "w") as f:
                        f.write(text)
                ran = set()
                out = checks.run(small, np.int64(2024), raw=d, ran=ran)
                self.assertFalse(ran & checks.RAW_CHECKS, name)  # a file it could not use: not run
                self.assertTrue({"K6", "K7", "K8"} <= ran, name)
                path = os.path.join(d, "trade_checks.json")
                checks.save(out, ran, np.int64(2024), path=path)
                with open(path, encoding="utf-8") as f:
                    self.assertEqual(json.load(f)["year"], 2024)
        # the readers resolve raw/ when called, so that patching checks.RAW hides it
        saved = checks.RAW
        with tempfile.TemporaryDirectory() as d:
            checks.RAW = d
            try:
                self.assertIsNone(checks.psd_table())
                self.assertIsNone(checks.eia_series([("57-1", "MT")]))
                self.assertIsNone(checks.usgs_table())
            finally:
                checks.RAW = saved

    def test_K7_taiwan_after_G1(self):
        self.assertFalse([r for r in self.of("K7") if r["group"] == "crude-oil" and r["country"] == "TWN"])

    def test_checks_never_change_the_frame(self):
        df = frame()
        before = (len(df), float(df.t.sum()))
        checks.run(df, 2024)
        self.assertEqual(before, (len(df), float(df.t.sum())))


class CaveatTests(unittest.TestCase):
    def active(self):
        if not hasattr(self.__class__, "_active"):
            self.__class__._active = caveats.build(frame(), findings(), 2024)
        return self.__class__._active

    @unittest.skipUnless(HAS_EIA, "raw/eia/INTL.txt absent")
    def test_malaysia_crude(self):
        cid = caveats.lookup(self.active(), "crude-oil", "MYS", "CHN")
        self.assertEqual(cid, "crude-mys")
        text = self.active()[cid]["text"]
        self.assertIn("54.2 Mt", text)
        self.assertIn("23.9 Mt", text)
        self.assertIn("plausible", text)

    def test_registry_entries(self):
        a = self.active()
        self.assertIn("crude-irn", a)
        self.assertIn("2018", a["crude-irn"]["text"])
        self.assertEqual(caveats.lookup(a, "wheat", "RUS", "EGY"), "grain-rus-wheat")
        self.assertEqual(caveats.lookup(a, "potash", "BLR", "BRA"), "potash-blr")
        self.assertEqual(caveats.lookup(a, "potash", "UZB", "BRA"), "potash-uzb")
        self.assertEqual(caveats.lookup(a, "urea", "IRN", "TUR"), "urea-irn")
        self.assertEqual(caveats.lookup(a, "crude-oil", "MEX", "TWN"), "crude-mex-s19")
        self.assertEqual(caveats.lookup(a, "crude-oil", "RUS", "TUR"), "crude-rus-tur")
        self.assertIsNone(caveats.lookup(a, "crude-oil", "NOR", "GBR"))

    def test_V06_causes_worded_as_hypotheses(self):
        for cid, e in self.active().items():
            for sentence in e["text"].split(". "):
                s = sentence.lower()
                if any(p in s for p in ("relabel", "declared under other origins", "ship-to-ship", "re-export")):
                    self.assertTrue("plausible" in s or "may" in s, (cid, sentence))
            self.assertTrue(e["kind"] and e["text"], cid)

    def test_no_number_typed_in_the_registry(self):
        import re
        with open(caveats.__file__, encoding="utf-8") as f:
            src = f.read()
        texts = re.findall(r'"([^"]*)"', src)
        typed = [t for t in texts if re.search(r"(?<![\w.:{])\d+(\.\d+)? ?(Mt|%|kb/d)", t)]  # not a format spec such as {x:.0%}
        self.assertEqual(typed, [])


class BuilderTests(unittest.TestCase):
    def test_D17_codes_and_single_mapping(self):
        import build_commodities as B
        baci = B.Baci.__new__(B.Baci)
        self.assertEqual(baci.iso("XAS"), "XAS")
        if os.path.exists(os.path.join(ROOT, "pipeline", "geo", "places_extra.json")):
            self.assertEqual(baci.iso("GIB"), "GIB")
        self.assertEqual(baci.iso("S19"), "TWN")
        for name in ("build_commodities.py", "build_profiles.py"):
            with open(os.path.join(ROOT, "pipeline", "commodities", name), encoding="utf-8") as f:
                src = f.read()
            self.assertNotIn('"S19"', src, name)
        import build_profiles  # noqa: F401


if __name__ == "__main__":
    unittest.main()
