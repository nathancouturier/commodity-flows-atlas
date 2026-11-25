"""Tests of the words around the figures of the LPG flow from the United States to Mexico, of the tin flow added from China's declaration and of the
LNG tables, and of the order of trade_checks.json.

Each test fails on the tree before the corrections: the pairs file of tin ore had no flag and no note on the added row, the checks read a frame that
held it, the five sentences of LPG said "computed from the declared value", the cause of the LPG error was written as a fact, a share of China's
imports read "of world", the tin page denied lanes that exist, and the findings of trade_checks.json came out in the order of the last builder.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The tests of the data files read the files as the builders last wrote them; those that need raw/ skip themselves without it.
"""
import glob
import json
import os
import random
import re
import sys
import tempfile
import unittest

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import checks as K  # noqa: E402
import clean as C  # noqa: E402
import comtrade_tin  # noqa: E402
import us_lpg  # noqa: E402

DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, "pipeline", "cache")


def load(*parts):
    with open(os.path.join(DATA, *parts), encoding="utf-8") as f:
        return json.load(f)


def baci(group):
    df = pd.read_csv(os.path.join(CACHE, "baci_flows.csv.gz"))
    return df[df["group"] == group]


def strings(o):
    """Every string of a JSON value."""
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


class TinAddedFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = baci("tin-ore")
        cls.cl = C.clean(cls.raw)

    def test_the_customs_frame_is_the_file_as_it_is(self):
        cf = C.customs_frame(self.cl)
        self.assertFalse((cf["flag"] == "added").any())
        keep = dict(comtrade_tin.ADDED_FLOWS)
        comtrade_tin.ADDED_FLOWS.clear()
        try:
            base = C.clean(self.raw)
        finally:
            comtrade_tin.ADDED_FLOWS.update(keep)
        self.assertEqual(len(cf), len(base))
        for y in comtrade_tin.years():
            self.assertAlmostEqual(float(cf[cf["year"] == y]["t"].sum()), float(base[base["year"] == y]["t"].sum()), delta=1.0)
        # the customs row that rule 11 replaced is back (161 t in 2023), and the frame of the lanes keeps the declared tonnage
        r = cf[(cf["o"] == "MMR") & (cf["d"] == "CHN") & (cf["year"] == 2023)]
        self.assertAlmostEqual(float(r["t"].iloc[0]), 161.0, delta=1.0)
        r = self.cl[(self.cl["o"] == "MMR") & (self.cl["d"] == "CHN") & (self.cl["year"] == 2023)]
        self.assertGreater(float(r["t"].iloc[0]), 1e5)

    def test_the_checks_do_not_compare_a_comtrade_figure_with_baci(self):
        with_added = [r["text"] for r in K.run(self.cl, 2024) if r["check"] == "K6" and r["group"] == "tin-ore"]
        as_is = [r["text"] for r in K.run(C.customs_frame(self.cl), 2024) if r["check"] == "K6" and r["group"] == "tin-ore"]
        # on the frame that holds the declaration the 2017 figure of UN Comtrade is quoted as a figure of CEPII BACI, and the year note of Brazil in 2020 is lost
        self.assertTrue([t for t in with_added if "Myanmar" in t and "in 2016" in t])
        self.assertFalse([t for t in as_is if "Myanmar" in t and "in 2016" in t])
        self.assertFalse([t for t in with_added if "Brazil" in t and "in 2020" in t])
        self.assertTrue([t for t in as_is if "Brazil" in t and "in 2020" in t])

    def test_the_note_says_what_the_row_is(self):
        r = self.cl[(self.cl["o"] == "MMR") & (self.cl["d"] == "CHN") & (self.cl["year"] == 2024)].iloc[0]
        self.assertTrue(r["enote"].startswith("Added from China's import declaration (UN Comtrade"))
        self.assertIn("not in the atlas's extract of CEPII BACI", r["enote"])
        r = self.cl[(self.cl["o"] == "MMR") & (self.cl["d"] == "CHN") & (self.cl["year"] == 2023)].iloc[0]
        self.assertIn("the atlas's extract of CEPII BACI has 161 t for the pair", r["enote"])  # the customs file's own figure, where it has one

    def test_the_pairs_file_flags_and_notes_the_row(self):
        doc = load("freight", "pairs", "tin-ore.json")
        row = [r for r in doc["rows"] if r[0] == "MMR" and r[1] == "CHN"][0]
        ix = {c: i for i, c in enumerate(doc["cols"])}
        self.assertTrue(row[ix["f"]] & 16)
        self.assertEqual(doc["added"], {"MMR-CHN": "comtrade"})
        self.assertIn("comtrade", {s["id"] for s in load("sources.json")})
        note = doc["notes"]["MMR-CHN"]
        self.assertTrue(note.startswith("Added from China's import declaration (UN Comtrade"))
        self.assertIn("not in the atlas's extract of CEPII BACI", note)
        # no other row of the group is flagged
        self.assertEqual([r for r in doc["rows"] if r[ix["f"]] & 16], [row])

    def test_the_lane_file_dates_the_break_of_the_series(self):
        notes = load("freight", "lanes", "tin-ore.json")["yearNotes"]
        self.assertIn("breaks between 2016 and 2017", notes["2017"])
        for y in range(2017, 2025):
            self.assertIn("from China's import declaration (UN Comtrade; not in the atlas's extract of CEPII BACI, which drops flows under 1,000 t and USD 1 million)", notes[str(y)])
            self.assertIn("All modes: includes Myanmar to China", notes[str(y)])  # the pair is overland: it is in the all-modes total, not in the seaborne figure
            self.assertIn("(overland: not in the seaborne figure)", notes[str(y)])
        self.assertNotIn("Myanmar: 0.00131 Mt in 2016", " ".join(notes.values()))  # the 2017 figure of Comtrade is no customs anomaly of BACI
        self.assertIn("Brazil: 0.00173 Mt in 2020", notes["2020"])  # the note that the world total of the added flow had hidden

    def test_the_tin_page_credits_the_totals_to_both_sources(self):
        tin = load("commodities", "tin.json")
        self.assertIn("(CEPII BACI, with Myanmar to China from UN Comtrade)", tin["notes"][0])

    def test_the_country_pages_say_it(self):
        for iso, side in (("MMR", "exports"), ("CHN", "imports")):
            x = [e for e in load("countries", "profiles", f"{iso}.json")["freight"][side] if e["g"] == "tin-ore"][0]
            self.assertEqual(x["added"]["s"], "comtrade")
            self.assertAlmostEqual(x["added"]["kt"], 76.5, places=1)
        # a country that has no such flow carries no mention of it
        x = [e for e in load("countries", "profiles", "THA.json").get("freight", {}).get("imports", []) if e["g"] == "tin-ore"]
        self.assertFalse([e for e in x if "added" in e])


class ChecksOrder(unittest.TestCase):
    def test_the_findings_are_written_in_a_fixed_order(self):
        recs = K.load()
        self.assertTrue(len(recs) > 100)
        shuffled = list(recs)
        random.Random(7).shuffle(shuffled)
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.json"), os.path.join(d, "b.json")
            K.save(shuffled, {r["check"] for r in recs}, 2024, path=a)
            K.save(list(reversed(recs)), {r["check"] for r in recs}, 2024, path=b)
            self.assertEqual(open(a, "rb").read(), open(b, "rb").read())
            # a later builder that writes one check only (K9 by build_freight) keeps the others where they were
            k9 = [r for r in recs if r["check"] == "K9"]
            K.save(list(reversed(k9)), {"K9"}, 2024, path=a)
            self.assertEqual(open(a, "rb").read(), open(b, "rb").read())

    def test_the_checks_are_in_numeric_order_and_the_file_is_sorted(self):
        recs = K.load()
        checks = list(dict.fromkeys(r["check"] for r in recs))
        self.assertEqual(checks, sorted(checks, key=lambda c: int(c[1:])))  # K9 before K10
        self.assertEqual(recs, sorted(recs, key=K.order_key))


class LpgWording(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mex = baci("lpg")
        cls.mex = mex[(mex["o"] == "USA") & (mex["d"] == "MEX")].set_index("year")["t"]

    def test_the_customs_tonnage_is_measured_against_the_volume(self):
        want = {2021: (0.76, 1.51), 2022: (0.76, 1.48), 2023: (0.98, 1.92), 2024: (0.90, 1.77)}
        for y, (per_m3, per_t) in want.items():
            m = us_lpg.measure("MEX", y, float(self.mex[y]))
            self.assertAlmostEqual(m["per_m3"], per_m3, places=2, msg=y)
            self.assertAlmostEqual(m["per_t"], per_t, places=2, msg=y)

    def test_no_page_says_the_tonnage_equals_the_volume(self):
        bad = []
        for path in glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True):
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
            for s in strings(doc):
                if re.search(r"equals the volume|is the volume in cubic metres read as tonnes|the volume in cubic metres read as tonnes[;,)]", s):
                    bad.append((os.path.relpath(path, ROOT), s[:90]))
                # a reading of the cause is a reading: wherever "read as tonnes" is written, the sentence says it is not established
                if "read as tonnes" in s and "not established here" not in s:
                    bad.append((os.path.relpath(path, ROOT), s[:90]))
        self.assertEqual(bad, [])

    def test_the_notes_of_the_rows_and_the_years_measure_and_hedge(self):
        lane = [x for x in load("freight", "lanes", "lpg.json")["lanes"] if x["id"] == "lpg:USA-MEX"][0]
        for y, per_t in (("2021", "1.51"), ("2022", "1.48"), ("2023", "1.92"), ("2024", "1.77")):
            n = lane["histNotes"][y]
            self.assertIn(f"{per_t} times the tonnage that the United States' own volume gives at the density", n)
            self.assertIn("times that volume in cubic metres", n)
            self.assertIn("a volume in cubic metres read as tonnes, for part or all of the declarations, is a plausible cause, not established here", n)
        notes = load("freight", "lanes", "lpg.json")["yearNotes"]
        self.assertIn("0.76 times the volume in cubic metres", notes["2021"])
        page = load("commodities", "lpg.json")
        text = " ".join(page["notes"])
        self.assertRegex(text, r"the customs tonnage of the pair is 0\.76 to 0\.9\d times the volume in cubic metres")
        self.assertIn("does not name the modes of the rest", text)
        mex = [r for r in page["imports"]["rows"] if r["c"] == "MEX"][0]
        self.assertIn("plausible cause, not established here", mex["n"])

    def test_the_two_bases_of_an_estimate_are_told_apart(self):
        lf = load("freight", "lanes", "lpg.json")
        lane = [x for x in lf["lanes"] if x["id"] == "lpg:USA-MEX"][0]
        self.assertEqual(lane["histVolume"], ["2021", "2022", "2023", "2024"])
        self.assertEqual(lane["histSrc"], {"2021": "eia-exports-destination", "2022": "eia-exports-destination", "2023": "eia-exports-destination", "2024": "census-exports"})
        self.assertTrue(lane["histAll"])
        self.assertAlmostEqual(lf["estVol"], 0.0294, places=3)
        self.assertLess(lf["estVol"], lf["est"])
        self.assertEqual(lf["estVolY"][-4:], [0.0, 0.0, 0.0, lf["estVolY"][-1]])
        n2024 = lf["yearNotes"]["2024"]
        self.assertIn("tonnage estimated from a volume in the United States' own export statistics (3.81 Mt) and from declared value (1.61 Mt)", n2024)
        page = load("commodities", "lpg.json")
        seaborne = page["summary"]["seaborne"]["n"]
        self.assertIn("is an Atlas estimate: 3% from a volume in the United States' own export statistics, 1% from value", seaborne)
        self.assertNotIn("estimated from value", seaborne)
        # the pairs file marks the estimate made from a volume (bit 5 with bit 0)
        doc = load("freight", "pairs", "lpg.json")
        ix = {c: i for i, c in enumerate(doc["cols"])}
        row = [r for r in doc["rows"] if r[0] == "USA" and r[1] == "MEX"][0]
        self.assertEqual(row[ix["f"]] & 33, 33)
        flow = [f for f in page["flows"] if f["o"] == "USA" and f["d"] == "MEX"][0]
        self.assertEqual(flow["estBy"], "volume")
        # no other estimated flow of the page is marked
        self.assertFalse([f for f in page["flows"] if f.get("estBy") and not (f["o"] == "USA" and f["d"] == "MEX")])

    def test_the_series_break_is_said_where_the_seaborne_figure_is_printed(self):
        lf = load("freight", "lanes", "lpg.json")
        self.assertEqual(lf["breakNote"], "2024 includes 3.81 Mt from the United States to Mexico, read as sea (split by mode known for 2024 only: "
                                          "the earlier years hold the pair in the mixed series)")
        self.assertIn(lf["breakNote"], load("commodities", "lpg.json")["summary"]["seaborne"]["n"])
        # only the lane file of the pair has it
        others = [os.path.basename(p) for p in glob.glob(os.path.join(DATA, "freight", "lanes", "*.json")) if "breakNote" in load("freight", "lanes", os.path.basename(p))]
        self.assertEqual(others, ["lpg.json"])

    def test_the_row_of_the_main_flows_says_what_the_figure_is(self):
        flow = [f for f in load("commodities", "lpg.json")["flows"] if f["o"] == "USA" and f["d"] == "MEX"][0]
        self.assertFalse(flow["n"].startswith("customs total for all modes"))
        self.assertTrue(flow["n"].startswith("the figure is for all modes of transport, 3.81 Mt of it by sea (the lane) and 1.47 Mt read as overland"))
        self.assertIn("does not name them", flow["n"])

    def test_the_exporter_row_prints_the_two_shares(self):
        usa = [r for r in load("commodities", "lpg.json")["exports"]["rows"] if r["c"] == "USA"][0]
        self.assertIn("10% of tonnage estimated: 8% from the volume in the United States' own export statistics, 2% from value", usa["n"])

    def test_the_country_pages_tell_the_bases_apart(self):
        x = [e for e in load("countries", "profiles", "USA.json")["freight"]["exports"] if e["g"] == "lpg"][0]
        self.assertGreater(x["estVolKt"], 3800)
        self.assertLess(x["estVolKt"], x["estKt"])
        cust = [e for e in load("countries", "profiles", "USA.json")["balance"] if e["k"] == "lpg"][0]["customers"]
        self.assertGreater(cust["estVolShare"], 0.05)

    def test_the_mexico_lane_file_row_is_not_all_declared_value(self):
        # a pair estimated from value keeps the sentence of the declared value: one of the other lanes of the page
        lf = load("freight", "lanes", "lpg.json")
        others = [x for x in lf["lanes"] if x["flow"].get("est") and x["id"] != "lpg:USA-MEX"]
        for x in others:
            self.assertNotIn("histVolume", x)


class TableLabels(unittest.TestCase):
    def test_a_table_whose_total_is_not_the_world_says_so(self):
        tin = load("commodities", "tin.json")
        t = {e["key"]: e["table"] for e in tin["extra"]}["tin-china-declared"]
        self.assertEqual(t["shareOf"], "China's declared imports")
        lng = {e["key"]: e["table"] for e in load("commodities", "lng.json")["extra"]}
        self.assertEqual(lng["lng-australia-markets"]["shareOf"], "Australia's exports")
        spod = {e["key"]: e["table"] for e in load("commodities", "lithium.json")["extra"]}["spodumene-exports"]
        self.assertTrue(spod["shareOf"])
        # no table of the pages that is a share of the world carries the label
        for path in glob.glob(os.path.join(DATA, "commodities", "*.json")):
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
            for sec in ("production", "reserves", "exports", "imports"):
                if isinstance(doc, dict) and isinstance(doc.get(sec), dict):
                    self.assertNotIn("shareOf", doc[sec], (path, sec))

    def test_each_row_of_the_first_lng_table_has_its_own_source(self):
        own = {e["key"]: e["table"] for e in load("commodities", "lng.json")["extra"]}["lng-own-statistics"]
        by = {r["c"]: r for r in own["rows"]}
        self.assertEqual(by["AUS"]["s"], "disr-req")  # the department's own figure, not an estimate
        self.assertFalse(by["AUS"].get("conv"))
        self.assertEqual(by["USA"]["s"], "eia-ng")  # the atlas's conversion of EIA's volume
        self.assertTrue(by["USA"]["conv"])
        self.assertEqual(own["srcs"], ["disr-req", "eia-ng"])
        self.assertNotEqual(own["s"], "atlas")
        ids = {s["id"] for s in load("sources.json")}
        self.assertTrue({"disr-req", "eia-ng"} <= ids)


class StaleDenials(unittest.TestCase):
    """A note that says a page lacks something (lanes, a production table, a price) is checked against the files of the page."""

    def pages(self):
        for path in sorted(glob.glob(os.path.join(DATA, "commodities", "*.json"))):
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
            if isinstance(doc, dict) and "summary" in doc and "notes" in doc:
                yield os.path.basename(path)[:-5], doc

    def test_no_lanes_is_not_written_for_a_page_that_has_lanes(self):
        has_lanes = {load("freight", "lanes", os.path.basename(p))["k"] for p in glob.glob(os.path.join(DATA, "freight", "lanes", "*.json"))}
        denial = re.compile(r"(^|\. )No lanes:|No [\w -]+ lanes exist|\(no seaborne figure\)")
        bad = [(k, n[:80]) for k, doc in self.pages() for n in doc["notes"] if denial.search(n) and k in has_lanes]
        self.assertEqual(bad, [])
        # and the notes still say it where it is true
        self.assertTrue([1 for k, doc in self.pages() for n in doc["notes"] if n.startswith("No lanes:") and k not in has_lanes])

    def test_no_production_table_is_not_written_for_a_page_that_has_one(self):
        bad = [k for k, doc in self.pages() for n in doc["notes"] if re.search(r"(^|\. )No production table:", n) and (doc.get("production") or {}).get("rows")]
        self.assertEqual(bad, [])

    def test_the_only_price_is_the_only_price(self):
        idx = load("prices", "index.json")
        bad = []
        for k, doc in self.pages():
            for n in doc["notes"]:
                series = [s for s in idx if s["k"] == k and not s.get("hidden")]
                if "The only price on the page" in n and len(series) > 1:
                    bad.append((k, len(series)))
                if "The only prices on the page" in n and len(series) < 2:
                    bad.append((k, len(series)))
        self.assertEqual(bad, [])


class Documents(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(ROOT, name), encoding="utf-8") as f:
            return " ".join(f.read().split())

    def test_methodology_and_the_page_give_one_range_of_the_ratio(self):
        page = " ".join(load("commodities", "lpg.json")["notes"])
        m = re.search(r"From 2004 to 2020 the customs tonnage is (\d\.\d) to (\d\.\d) times", page)
        self.assertTrue(m)
        self.assertIn(f"from 2004 to 2020 the customs tonnage of the pair is {m.group(1)} to {m.group(2)} times", self.read("METHODOLOGY.md"))

    def test_methodology_gives_the_census_quantity_by_code(self):
        """The quantities of rule 10 are the cache's (which sum the domestic and the foreign exports of a code), and the paragraph says for each code
        whether the figure holds the foreign exports (the domestic part is read from the file in raw/, which the tests do not read)."""
        text = self.read("METHODOLOGY.md")
        c = us_lpg.load()["census"]["pairs"]["MEX"]["qty_m3"]
        for code, words in (("2711120010", "under code 2711120010"), ("2711120020", "under 2711120020"), ("2711130000", "of butanes under 2711130000")):
            self.assertIn(f"{c[code] / 1e6:.2f} million m3 {words}", text)
        self.assertIn(f"{(c['2711120010'] + c['2711120020']) / 1e6:.2f} million m3 of propane and {sum(c.values()) / 1e6:.2f} million m3 of propane and butanes, each with the foreign exports", text)
        self.assertNotIn("9.36 million m3 under code 2711120010", text)  # it was the domestic part only, which 0.88 and 10.26 are not
        for s in ("of domestic exports and", "of foreign exports", "domestic exports; the file has no foreign export of this code to Mexico", "a plausible cause: it is not established here"):
            self.assertIn(s, text)
        self.assertNotIn("is the volume in cubic metres read as tonnes", text)

    def test_data_sources_say_what_is_used_of_comtrade(self):
        text = self.read("DATA_SOURCES.md")
        self.assertNotIn("UN Comtrade API**: free tier needs a key and has low limits. BACI already reconciles the same data.", text)
        self.assertIn("public preview", text.split("Sources considered and not used")[1])
        self.assertIn("`comtrade`", text.split("Sources considered and not used")[1])

    def test_notice_has_the_credit_each_new_source_asks_for(self):
        text = self.read("NOTICE.md")
        for s in ("Department of Industry, Science, and Resources, Commonwealth of Australia Resources and Energy Quarterly, December 2025.",
                  '"Source: UN Comtrade."', "US Census Bureau", "us_lpg_volumes.json", "comtrade_tin_china.json", "aus_req_lng.json"):
            self.assertIn(s, text)


if __name__ == "__main__":
    unittest.main()
