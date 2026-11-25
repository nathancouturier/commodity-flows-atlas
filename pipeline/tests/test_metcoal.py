"""Tests of the Main flows block of the Metallurgical coal page: metallurgical coal by pair of countries, from the exporters' own statistics
(Queensland's coal sales by destination, EIA's exports of rank metallurgical of the United States), kept apart from the customs group `coal`.

1  the tracked cache (pipeline/cache/metcoal_*.csv, metcoal_meta.json) and its totals
2  the definition guard: PCI counted with the coking coals, or the series breaks in 2022
3  the meta file: the credit words, the dates, the hash of the raw file
4  the page: the flows of data/commodities/met-coal.json
5  the notes of the page
6  the registry: the two sources, their licence texts, DATA_SOURCES.md and NOTICE.md
7  the layer is not a part of customs coal (why no builder may subtract one from the other)
8  without raw/: the reader names no path under raw/, and the extractor leaves the cache as it is
9  the web: the tag "all coal" on the Thermal coal page only, the sources of a list with several sources

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
No test reads raw/: they read the cache and the data files as the builders last wrote them.
"""
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import clean as C  # noqa: E402
import metcoal  # noqa: E402
from common import constants as CN  # noqa: E402

DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, "pipeline", "cache")
QLD, EIA = "qld-coal-sales", "eia-coal"
YEAR = 2024


def load(*parts):
    with open(os.path.join(DATA, *parts), encoding="utf-8") as f:
        return json.load(f)


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def open_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def page():
    return load("commodities", "met-coal.json")


class Cache(unittest.TestCase):
    """1"""

    def test_the_three_files_and_their_columns(self):
        for name in ("metcoal_pairs.csv", "metcoal_ports.csv", "metcoal_meta.json"):
            self.assertTrue(os.path.exists(os.path.join(CACHE, name)), name)
        head = lambda n: read("pipeline", "cache", n).splitlines()[0]  # noqa: E731
        self.assertEqual(head("metcoal_pairs.csv"), "src,o,d,year,coal_type,kind,tonnes")
        self.assertEqual(head("metcoal_ports.csv"), "src,year,d,port,kind,tonnes")

    def test_sources_kinds_and_countries(self):
        iso = {c["c"] for c in load("countries", "index.json")} | {p["c"] for p in json.loads(read("pipeline", "geo", "places_extra.json"))}
        d = metcoal.load()
        self.assertEqual({r[0] for r in d["pairs"]}, {QLD, EIA})
        self.assertEqual({r[5] for r in d["pairs"]}, {"metallurgical", "thermal"})
        self.assertEqual({(r[0], r[1]) for r in d["pairs"]}, {(QLD, "AUS"), (EIA, "USA")})
        for r in d["pairs"]:
            self.assertIn(r[2], iso, r)  # no aggregate, no "Unknown", no world row
            self.assertGreater(r[6], 0, r)
        self.assertEqual({(r[0], r[4]) for r in d["pairs"]},
                         {(QLD, "hard-coking"), (QLD, "semi-soft"), (QLD, "pci"), (QLD, "thermal"), (EIA, "metallurgical"), (EIA, "steam")})
        self.assertEqual(len({(r[0], r[1], r[2], r[3], r[4]) for r in d["pairs"]}), len(d["pairs"]), "one row per source, destination, year and coal type")

    def test_queensland_2024(self):
        self.assertEqual(sum(metcoal.pairs(QLD, YEAR).values()), 136985537)
        self.assertEqual(len(metcoal.pairs(QLD, YEAR)), 31)
        ct = {k: sum(metcoal.coal_types(QLD, YEAR, d).get(k, 0) for d in metcoal.pairs(QLD, YEAR)) for k in ("hard-coking", "semi-soft", "pci")}
        for k, mt in (("hard-coking", 91.927), ("pci", 34.583), ("semi-soft", 10.475)):
            self.assertAlmostEqual(ct[k] / 1e6, mt, places=3)
        ports = metcoal.ports(QLD, YEAR)
        for name, mt in (("Dalrymple Bay", 41.564), ("Hay Point", 36.899), ("Gladstone Port", 43.331), ("Abbot Point", 15.192)):
            self.assertAlmostEqual(ports[name] / 1e6, mt, places=3, msg=name)

    def test_eia_2024(self):
        m = metcoal.meta(EIA)["totals"][f"{YEAR}-metallurgical"]
        self.assertEqual(m["short_tons"], 56586866)
        self.assertEqual(m["tonnes"], 51334741)
        self.assertEqual(m["tonnes"], round(m["short_tons"] * CN.TONNES_PER_SHORT_TON), "the factor of common/constants.py")
        pairs = metcoal.pairs(EIA, YEAR)
        self.assertEqual(len(pairs), 34)
        self.assertLessEqual(abs(sum(pairs.values()) - m["tonnes"]), len(pairs))  # each row is rounded to a tonne
        self.assertEqual(sum(1 for t in pairs.values() if t >= 1000), 32)
        ds = metcoal.ports(EIA, YEAR)
        for name, mt in (("Norfolk, VA", 30.128), ("Mobile, AL", 8.764), ("Baltimore, MD", 8.696), ("Buffalo, NY", 2.180), ("New Orleans, LA", 1.182)):
            self.assertAlmostEqual(ds[name] / 1e6, mt, places=3, msg=name)
        ind, chn = metcoal.districts(EIA, YEAR, "IND"), metcoal.districts(EIA, YEAR, "CHN")
        self.assertAlmostEqual(ind["Norfolk, VA"] / sum(ind.values()), 0.88, delta=0.01)
        self.assertAlmostEqual(chn["Baltimore, MD"] / sum(chn.values()), 0.52, delta=0.01)

    def test_queensland_ports_add_to_the_pairs_2022_to_2025(self):
        for y in (2022, 2023, 2024, 2025):
            for kind in ("metallurgical", "thermal"):
                pairs = sum(metcoal.pairs(QLD, y, kind).values()) + metcoal.meta(QLD)["unallocated"].get(f"{y}-{kind}", 0)
                self.assertLessEqual(abs(pairs - sum(metcoal.ports(QLD, y, kind).values())), 3, f"{y} {kind}")  # one tonne of rounding per row

    def test_eia_districts_add_to_the_destinations(self):
        for kind in ("metallurgical", "thermal"):
            self.assertLessEqual(abs(sum(metcoal.pairs(EIA, YEAR, kind).values()) - sum(metcoal.ports(EIA, YEAR, kind).values())), 0.005 * 5e7, kind)
        # the destination-by-district rows of one destination add to the pair
        rows = [r for r in metcoal.load()["ports"] if r[0] == EIA and r[1] == YEAR and r[2] == "IND" and r[4] == "metallurgical"]
        self.assertAlmostEqual(sum(r[5] for r in rows), metcoal.pairs(EIA, YEAR)["IND"], delta=len(rows))

    def test_a_year_the_cache_does_not_hold_raises(self):
        with self.assertRaises(ValueError) as cm:
            metcoal.pairs(QLD, 2031)
        self.assertIn("extract_metcoal.py", str(cm.exception))
        with self.assertRaises(ValueError):
            metcoal.pairs(EIA, 2031)


class Definition(unittest.TestCase):
    """2"""

    def test_pci_with_the_coking_coals_is_continuous_across_2022_and_semi_soft_alone_is_not(self):
        def tot(y, types):
            return sum(metcoal.coal_types(QLD, y, d).get(k, 0) for d in metcoal.pairs(QLD, y) for k in types)
        whole = tot(2022, ("hard-coking", "semi-soft", "pci")) / tot(2021, ("hard-coking", "semi-soft", "pci")) - 1
        semi = tot(2022, ("semi-soft",)) / tot(2021, ("semi-soft",)) - 1
        self.assertLess(abs(whole), 0.06, "the three metallurgical types together move by less than 6% from 2021 to 2022")
        self.assertGreater(abs(semi), 0.20, "semi-soft coking alone breaks in 2022: PCI was inside it before")
        self.assertEqual(tot(2021, ("pci",)), 0, "PCI is reported apart from 2022 only")
        self.assertGreater(tot(2022, ("pci",)), 0)


class Meta(unittest.TestCase):
    """3"""

    def test_queensland_credit_and_dates(self):
        m = metcoal.meta(QLD)
        self.assertIn("Department of Natural Resources and Mines, Manufacturing and Regional and Rural Development (NRMMRRD)", m["credit"])
        self.assertEqual(m["current_as_at"], "Current as at October 2026")
        self.assertIn("30 June 2026", m["data_through"])
        self.assertIn("may be revised", m["revised"])
        self.assertIn("not to be considered attributable to the Department", m["disclaimer"])
        self.assertRegex(m["file"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(m["file"]["name"], "coal-sales-data-2010-2026.xlsx")
        self.assertEqual(m["excluded_years"], [2026], "2026 has two quarters: not a calendar year")
        self.assertIn("PCI", m["definition"])
        self.assertIn("New South Wales", m["definition"])

    def test_eia_definition_and_file(self):
        m = metcoal.meta(EIA)
        self.assertRegex(m["file"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(m["file_date"], "2026-10-01")
        self.assertEqual(m["tonnes_per_short_ton"], CN.TONNES_PER_SHORT_TON)
        self.assertIn("does not define the rank", m["definition"])
        self.assertEqual(m["credit"], "Source: U.S. Energy Information Administration")
        self.assertEqual(m["years"], list(range(2010, 2026)))
        for k, v in m["checks"].items():  # the checks of the extractor, for every year kept
            self.assertLessEqual(abs(v["destinations_gap"]) / v["world_short_tons"], 0.005, k)
            self.assertLessEqual(abs(v["districts_gap"]) / v["world_short_tons"], 0.005, k)


class Page(unittest.TestCase):
    """4"""

    @classmethod
    def setUpClass(cls):
        cls.d = page()
        cls.fl = cls.d["flows"]

    def test_every_flow_is_an_exporter_statistic(self):
        self.assertEqual(len(self.fl), 63)
        for f in self.fl:
            self.assertIn(f["s"], (QLD, EIA), f)
            self.assertIn(f["o"], ("AUS", "USA"), f)
            self.assertEqual(f["y"], YEAR)
            self.assertEqual(f["u"], "Mt")
            self.assertNotIn("usd", f, "no customs value: these are not customs data")
            self.assertNotIn("lane", f, "no lane of the layer yet: the rows open the page of the origin")
            self.assertNotEqual(f["s"], "baci")
            self.assertEqual((f["s"] == QLD), (f["o"] == "AUS"))

    def test_figures(self):
        by = {(f["o"], f["d"]): f for f in self.fl}
        self.assertEqual(by[("AUS", "IND")]["v"], 35.419)
        self.assertEqual(by[("USA", "IND")]["v"], 9.292)
        self.assertEqual(by[("AUS", "JPN")]["v"], 29.658)
        self.assertEqual(max(self.fl, key=lambda f: f["v"])["d"], "IND")

    def test_flows_add_to_the_cache_totals_less_the_rows_under_1000_tonnes(self):
        for src, o in ((QLD, "AUS"), (EIA, "USA")):
            kept = sum(t for t in metcoal.pairs(src, YEAR).values() if t >= 1000)
            self.assertAlmostEqual(sum(f["v"] for f in self.fl if f["s"] == src), kept / 1e6, delta=0.0005 * len(metcoal.pairs(src, YEAR)))
        self.assertEqual(sum(1 for f in self.fl if f["s"] == QLD), 31)
        self.assertEqual(sum(1 for f in self.fl if f["s"] == EIA), 32)

    def test_title_mode_and_year(self):
        self.assertEqual(self.d["labels"]["flows"], f"Main flows — metallurgical coal, exporters' statistics {YEAR}")
        us_ca = next(f for f in self.fl if f["o"] == "USA" and f["d"] == "CAN")
        self.assertEqual(us_ca["mode"], "land")
        self.assertIn("Buffalo, NY", us_ca["n"])
        self.assertTrue(all(f.get("mode") for f in self.fl))

    def test_the_rows_of_the_other_exporters_left_the_page_and_stay_on_the_thermal_coal_page(self):
        self.assertFalse({f["o"] for f in self.fl} - {"AUS", "USA"})
        th = load("commodities", "thermal-coal.json")
        self.assertEqual({f["s"] for f in th["flows"]}, {"baci"})
        self.assertEqual(th["labels"]["flows"], f"Main flows — all coal, customs data {YEAR}")
        self.assertTrue({"MNG", "RUS"} <= {f["o"] for f in th["flows"]})


class Words(unittest.TestCase):
    """5"""

    @classmethod
    def setUpClass(cls):
        cls.notes = page()["notes"]
        cls.text = "\n".join(cls.notes)

    def test_definitions_dates_and_disclaimers(self):
        t = self.text
        self.assertIn("Queensland producers' sales to export of metallurgical coal", t)
        self.assertIn("exports of rank metallurgical as declared at export", t)
        self.assertIn("Data through to 30 June 2026", t)
        self.assertIn("Current as at October 2026", t)
        self.assertIn("may be revised", t)
        self.assertIn("not to be considered attributable to the Department", t)
        self.assertIn("The file does not define the rank", t)
        self.assertIn("Source: U.S. Energy Information Administration", t)
        self.assertIn("not subtracted", t)
        self.assertIn("1 October 2026", t)

    def test_ports_and_exporters_without_a_source_by_destination(self):
        ports = metcoal.ports(QLD, YEAR)
        for name in ("Hay Point", "Gladstone Port", "Abbot Point", "Dalrymple Bay"):
            self.assertIn(f"{name} {ports[name] / 1e6:.1f} Mt", self.text)
        for c in ("Mongolia", "Russia", "Canada", "Mozambique"):
            self.assertIn(c, self.text.split("No free source loaded gives destinations for")[1])
        self.assertNotIn("Netherlands (", self.text.split("No free source loaded gives destinations for")[1], "the Netherlands re-exports: it mines nothing")

    def test_no_sum_of_the_two_exporters_and_no_share_of_it(self):
        both = (sum(metcoal.pairs(QLD, YEAR).values()) + sum(metcoal.pairs(EIA, YEAR).values())) / 1e6
        self.assertAlmostEqual(both, 188.3, places=1)
        for s in (f"{both:.1f}", f"{both:,.0f} Mt", "188"):
            self.assertNotIn(s, self.text)
        self.assertNotRegex(self.text, r"\b(60|59|58|55)(\.\d)?%")

    def test_a_visitor_reads_no_pipeline_words(self):
        for w in ("cache", "builder", "raw", "extractor", "package"):
            self.assertIsNone(re.search(rf"\b{w}\b", self.text, re.I), w)

    def test_the_old_notes_are_gone(self):
        self.assertNotIn("Flows are BACI coal flows", self.text)
        self.assertNotIn("Seaborne total omitted", self.text)
        self.assertIn("Exports/imports tables are EIA metallurgical coal (not BACI).", self.notes)
        self.assertIn("The seaborne lanes of this page are customs data for all coal, and coke: they are not the flows above.", self.notes)


class Registry(unittest.TestCase):
    """6"""

    def test_sources(self):
        src = {s["id"]: s for s in load("sources.json")}
        for i in (QLD, EIA):
            self.assertIn(i, src)
            for k in ("name", "publisher", "url", "licence", "update", "access", "use"):
                self.assertTrue(src[i].get(k), (i, k))
        self.assertIn("CC BY 4.0", src[QLD]["licence"])
        self.assertIn("Source: Department of Natural Resources and Mines, Manufacturing and Regional and Rural Development (NRMMRRD)", src[QLD]["licence"])
        self.assertIn("not attributable to the Department", src[QLD]["licence"])
        self.assertIn("Public domain", src[EIA]["licence"])
        self.assertIn("Source: U.S. Energy Information Administration", src[EIA]["licence"])
        self.assertNotIn("terms to be confirmed", src[QLD]["licence"] + src[EIA]["licence"])
        table = read("DATA_SOURCES.md")
        for i in (QLD, EIA):
            self.assertIn(i, table)

    def test_the_licence_rule_of_the_site_accepts_them(self):
        lic = read("web", "scripts", "licence.test.mjs")
        self.assertRegex(lic, r"'qld-coal-sales'.*'eia-coal'|'eia-coal'.*'qld-coal-sales'", "the list of sources the rule must allow")

    def test_notice_carries_the_credit_and_the_cache_files(self):
        n = " ".join(read("NOTICE.md").split())  # the file is wrapped at 120 columns
        self.assertIn("Department of Natural Resources and Mines, Manufacturing and Regional and Rural Development", n)
        self.assertIn("Quarterly Coal Sales", n)
        self.assertIn("metcoal_pairs.csv", n)
        self.assertIn("Source: U.S. Energy Information Administration", n)
        self.assertIn("COAL.zip", n)


class NotAPartOfCustomsCoal(unittest.TestCase):
    """7: why no builder may subtract one of these figures from the customs coal: the difference is a figure with no definition."""

    @classmethod
    def setUpClass(cls):
        raw = pd.read_csv(os.path.join(CACHE, "baci_flows.csv.gz"))
        cl = C.clean(raw)
        cls.cu = cl[(cl["group"] == "coal") & (cl["year"] == YEAR)].groupby(["o", "d"])["t"].sum()

    def test_many_pairs_of_the_layer_exceed_the_customs_pair(self):
        n = 0
        for src, o in ((QLD, "AUS"), (EIA, "USA")):
            for d, t in metcoal.pairs(src, YEAR).items():
                if t >= 1000 and t > float(self.cu.get((o, d), 0)):
                    n += 1
        self.assertGreaterEqual(n, 10, "the exporter's first destination is not the customs partner: a flow of the layer can exceed the whole customs coal of its pair")
        self.assertGreater(float(self.cu[("AUS", "SGP")]) , 0)
        self.assertGreater(metcoal.pairs(QLD, YEAR)["SGP"], 10 * float(self.cu[("AUS", "SGP")]), "Singapore: 1.66 Mt of Queensland coal against 0.14 Mt in customs data")

    def test_customs_coal_less_the_layer_is_not_the_thermal_coal_of_the_pair(self):
        diff = float(self.cu[("AUS", "IND")]) - metcoal.pairs(QLD, YEAR)["IND"]
        self.assertGreater(diff / 1e6, 15, "Australia to India: customs all coal less Queensland metallurgical coal is 22.8 Mt; Australia's own thermal figure to India is 3.8 Mt")

    def test_the_customs_group_is_not_touched(self):
        self.assertEqual(load("freight", "lanes", "coal.json")["seaborne"][-1], 1377.28)
        for sub in ("lanes", "pairs"):
            self.assertFalse([f for f in os.listdir(os.path.join(DATA, "freight", sub)) if "metcoal" in f or "met-coal" in f], sub)


class WithoutRaw(unittest.TestCase):
    """8"""

    def test_the_reader_names_no_path_under_raw(self):
        src = read("pipeline", "trade", "metcoal.py")
        self.assertNotIn('"raw"', src)
        self.assertNotRegex(src, r"import (extract_metcoal|openpyxl)|from extract_metcoal")
        self.assertNotIn("openpyxl", src)

    def test_the_builder_reads_the_cache_not_the_workbooks(self):
        b = read("pipeline", "commodities", "build_commodities.py")
        self.assertIn("import metcoal", b)
        self.assertNotIn("import extract_metcoal", b)
        self.assertNotRegex(b, r'RAW, "australia"|os\.path\.join\(RAW, "eia", "coal"')

    def test_the_extractor_without_raw_exits_cleanly_and_leaves_the_cache_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            for rel in ("pipeline/trade/extract_metcoal.py", "pipeline/common/constants.py", "pipeline/cache/metcoal_pairs.csv", "pipeline/cache/metcoal_ports.csv",
                        "pipeline/cache/metcoal_meta.json"):
                os.makedirs(os.path.dirname(os.path.join(tmp, rel)), exist_ok=True)
                shutil.copy(os.path.join(ROOT, rel), os.path.join(tmp, rel))
            cached = lambda base, n: open_bytes(os.path.join(base, n))  # noqa: E731
            before = {n: cached(os.path.join(tmp, "pipeline", "cache"), n) for n in ("metcoal_pairs.csv", "metcoal_ports.csv", "metcoal_meta.json")}
            r = subprocess.run([sys.executable, "-I", "-B", os.path.join(tmp, "pipeline", "trade", "extract_metcoal.py")], capture_output=True, text=True, cwd=tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("is not here", r.stdout)
            for n, b in before.items():
                self.assertEqual(cached(os.path.join(tmp, "pipeline", "cache"), n), b, n)
                self.assertEqual(cached(CACHE, n), b, "the copy is the tracked cache")


class Web(unittest.TestCase):
    """9: read from the source, as test_fncc.py does"""

    @classmethod
    def setUpClass(cls):
        cls.view = read("web", "src", "components", "views", "CommodityView.tsx")

    def test_the_tag_all_coal_is_the_thermal_coal_page_only(self):
        self.assertIn("const isAllCoal = (id: string) => id === 'thermal-coal';", self.view)
        self.assertIn("tag={isAllCoal(id) ? 'all coal' : undefined}", self.view)
        self.assertNotIn("isCoal(", self.view)

    def test_a_list_with_several_sources_names_them(self):
        self.assertRegex(self.view, r"const several = new Set\(props\.flows\.filter\(\(f\) => f\.s !== 'atlas'\)\.map\(\(f\) => f\.s\)\)\.size > 1;")
        self.assertIn("{several && <SourcesLine items={props.flows}", self.view)
        self.assertIn("{!several && first && <SourceLine", self.view, "one source: the footer is as before")
        self.assertIn("(f.s === 'atlas' ? f.s !== first.s : several)", self.view)
        self.assertIn("'qld-coal-sales': 'Queensland Government'", read("web", "src", "components", "ui.tsx"))

    def test_the_map_label_of_an_overland_arc_says_customs_only_for_a_customs_flow(self):
        src = read("web", "src", "map", "modules", "landflows.ts")
        self.assertIn("${f.usd != null ? ' (customs)' : ''}", src)
        self.assertNotIn("'overland'} (customs)", src)


if __name__ == "__main__":
    unittest.main()
