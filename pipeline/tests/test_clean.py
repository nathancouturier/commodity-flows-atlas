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
        n = int(df.flag.isin(["uv-suspect-t", "uv-suspect", "uv-repair"]).sum())
        self.assertTrue(35 <= n <= 47, n)
        self.assertTrue(set(df[df.flag.isin(["uv-suspect-t", "uv-suspect", "uv-repair"])].group) <= C.BULK)

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
        self.assertTrue({r["check"] for r in out} <= {"K6", "K7", "K8", "K11"})
        self.assertTrue({"K6", "K7", "K8"} <= ran)
        self.assertFalse({"K1", "K2", "K3", "K4", "K10"} & ran)
        # previous records of the checks that did not run are kept by merge()
        prev = [{"check": "K1", "text": "old"}, {"check": "K8", "text": "old"}]
        merged = checks.merge(prev, out, ran)
        self.assertIn({"check": "K1", "text": "old"}, merged)
        self.assertNotIn({"check": "K8", "text": "old"}, merged)

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
        src = open(caveats.__file__, encoding="utf-8").read()
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
            src = open(os.path.join(ROOT, "pipeline", "commodities", name), encoding="utf-8").read()
            self.assertNotIn('"S19"', src, name)
        import build_profiles  # noqa: F401


if __name__ == "__main__":
    unittest.main()
