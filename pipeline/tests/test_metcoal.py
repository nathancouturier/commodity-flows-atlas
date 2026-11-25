"""Tests of the Main flows block of the Metallurgical coal page: metallurgical coal by pair of countries, from the exporters' own statistics
(Queensland's coal sales by destination, EIA's exports of rank metallurgical of the United States), kept apart from the customs group `coal`.

1  the tracked cache (pipeline/cache/metcoal_*.csv, metcoal_meta.json) and its totals
2  the definition guard: PCI counted with the coking coals, or the series breaks in 2022
3  the meta file: the credit words, the dates, the hash of the raw file; the guard on the 2024 totals (a tolerance, not an exact figure)
4  the page: the flows of data/commodities/met-coal.json and the definitions printed under them
5  the notes of the page: every figure they print is recomputed here from the cache, and no other percentage is printed
6  the registry: the two sources, their licence texts, DATA_SOURCES.md and NOTICE.md
7  the layer is not a part of customs coal (why no builder may subtract one from the other)
8  without raw/: the reader names no path under raw/, and the extractor leaves the cache as it is
9  the web: the rules of the Main flows block are tested on fixtures in web/scripts/flow-sources.test.mjs (npm test)

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
No test reads raw/: they read the cache and the data files as the builders last wrote them.
"""
import contextlib
import csv
import io
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

import build_commodities as B  # noqa: E402
import clean as C  # noqa: E402
import extract_metcoal as X  # noqa: E402
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
        # consistency of the cache with itself: the figures of the publisher are not typed here (a revision of the workbook changes them)
        pairs = metcoal.pairs(QLD, YEAR)
        ct = {k: sum(metcoal.coal_types(QLD, YEAR, d).get(k, 0) for d in pairs) for k in ("hard-coking", "semi-soft", "pci")}
        self.assertEqual(sum(ct.values()), sum(pairs.values()), "the metallurgical coal is the three types, nothing else")
        self.assertGreater(len(pairs), 20)
        ports = metcoal.ports(QLD, YEAR)
        self.assertEqual(sorted(ports), ["Abbot Point", "Dalrymple Bay", "Gladstone Port", "Hay Point"])
        self.assertLessEqual(abs(sum(ports.values()) - sum(pairs.values()) - metcoal.meta(QLD)["unallocated"].get(f"{YEAR}-metallurgical", 0)), len(pairs))

    def test_eia_2024(self):
        m = metcoal.meta(EIA)["totals"][f"{YEAR}-metallurgical"]
        self.assertEqual(m["tonnes"], round(m["short_tons"] * CN.TONNES_PER_SHORT_TON), "the factor of common/constants.py")
        pairs = metcoal.pairs(EIA, YEAR)
        self.assertLessEqual(abs(sum(pairs.values()) - m["tonnes"]), len(pairs))  # each row is rounded to a tonne
        ds = metcoal.ports(EIA, YEAR)
        self.assertLessEqual(abs(sum(ds.values()) - m["tonnes"]), 0.005 * m["tonnes"])
        for name in ("Norfolk, VA", "Mobile, AL", "Baltimore, MD", "Buffalo, NY", "New Orleans, LA"):
            self.assertIn(name, ds)
        self.assertGreater(ds["Norfolk, VA"], max(v for k, v in ds.items() if k != "Norfolk, VA"))
        ind, chn = metcoal.districts(EIA, YEAR, "IND"), metcoal.districts(EIA, YEAR, "CHN")
        self.assertGreater(ind["Norfolk, VA"] / sum(ind.values()), 0.5)
        self.assertGreater(chn["Baltimore, MD"] / sum(chn.values()), 0.3)

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
        self.assertEqual(m["credit"], "Source: Department of Natural Resources and Mines, Manufacturing and Regional and Rural Development (NRMMRRD)", "the About sheet's words")
        self.assertTrue(m["disclaimer_full"].endswith(m["disclaimer"]), "the whole disclaimer of the About sheet ends with the sentence on derived conclusions")
        self.assertIn("The Department is not responsible for data that is misrepresented, misinterpreted or altered in any way.", m["disclaimer_full"])
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

    def test_the_guard_on_2024_is_a_tolerance_recorded_in_the_meta_file(self):
        """The 2024 total is a guard against a changed definition, not against a revision (a new workbook may revise 2024)."""
        for src in (QLD, EIA):
            g = metcoal.meta(src)["guard_2024"]
            self.assertEqual(g["reference"], X.GUARD_2024[src])
            self.assertLessEqual(abs(g["read"] / g["reference"] - 1), X.GUARD_TOLERANCE, src)
            self.assertAlmostEqual(g["difference_pct"], (g["read"] / g["reference"] - 1) * 100, places=3)
        self.assertEqual(X.GUARD_TOLERANCE, 0.02)

    def _guard(self, qld, eia):
        """check_2024 on a cache whose 2024 totals are the given ones: returns (stops or None, meta)."""
        pairs = [(QLD, "AUS", "IND", 2024, "hard-coking", "metallurgical", qld), (EIA, "USA", "IND", 2024, "metallurgical", "metallurgical", round(eia * CN.TONNES_PER_SHORT_TON))]
        meta = {QLD: {"years": [2024]}, EIA: {"years": [2024], "tonnes_per_short_ton": CN.TONNES_PER_SHORT_TON, "totals": {"2024-metallurgical": {"short_tons": eia}}}}
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                X.check_2024(pairs, meta)
        except SystemExit as e:
            return str(e), meta
        return None, meta

    def test_a_revision_inside_the_tolerance_goes_on_and_is_written_to_the_meta_file(self):
        stop, meta = self._guard(round(X.GUARD_2024[QLD] * 1.01), round(X.GUARD_2024[EIA] * 0.985))
        self.assertIsNone(stop)
        self.assertAlmostEqual(meta[QLD]["guard_2024"]["difference_pct"], 1.0, places=1)
        self.assertAlmostEqual(meta[EIA]["guard_2024"]["difference_pct"], -1.5, places=1)
        stop, meta = self._guard(X.GUARD_2024[QLD], X.GUARD_2024[EIA])
        self.assertIsNone(stop)
        self.assertEqual(meta[QLD]["guard_2024"]["difference_pct"], 0)

    def test_a_change_beyond_the_tolerance_stops_with_what_to_look_at(self):
        stop, _ = self._guard(round(X.GUARD_2024[QLD] * 1.03), X.GUARD_2024[EIA])
        self.assertIn("qld-coal-sales", stop)
        self.assertIn("+3.0%", stop)
        self.assertIn("what the file counts as metallurgical", stop)
        self.assertIn("GUARD_2024", stop)
        stop, _ = self._guard(X.GUARD_2024[QLD], round(X.GUARD_2024[EIA] * 0.97))
        self.assertIn("eia-coal", stop)
        self.assertIn("rank codes", stop)


class Page(unittest.TestCase):
    """4"""

    @classmethod
    def setUpClass(cls):
        cls.d = page()
        cls.fl = cls.d["flows"]

    def test_every_flow_is_an_exporter_statistic(self):
        listed = lambda src: sum(1 for t in metcoal.pairs(src, YEAR).values() if t >= B.MET_FLOW_MIN)  # noqa: E731
        self.assertEqual(len(self.fl), listed(QLD) + listed(EIA))
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
        for src, o in ((QLD, "AUS"), (EIA, "USA")):
            for d, t in metcoal.pairs(src, YEAR).items():
                if t >= B.MET_FLOW_MIN:
                    self.assertEqual(by[(o, d)]["v"], B.rnd(t / 1e6), (o, d))
        self.assertEqual(self.fl, sorted(self.fl, key=lambda f: -f["v"]))

    def test_flows_add_to_the_cache_totals_less_the_rows_under_1000_tonnes(self):
        for src, o in ((QLD, "AUS"), (EIA, "USA")):
            kept = sum(t for t in metcoal.pairs(src, YEAR).values() if t >= 1000)
            self.assertAlmostEqual(sum(f["v"] for f in self.fl if f["s"] == src), kept / 1e6, delta=0.0005 * len(metcoal.pairs(src, YEAR)))
            self.assertEqual(sum(1 for f in self.fl if f["s"] == src), sum(1 for t in metcoal.pairs(src, YEAR).values() if t >= 1000))

    def test_title_mode_and_year(self):
        self.assertEqual(self.d["labels"]["flows"], f"Main flows — metallurgical coal, exporters' statistics {YEAR}")
        us_ca = next(f for f in self.fl if f["o"] == "USA" and f["d"] == "CAN")
        self.assertEqual(us_ca["mode"], "land")
        self.assertIn("Buffalo, NY", us_ca["n"])
        self.assertTrue(all(f.get("mode") for f in self.fl))

    def test_the_canada_row_says_that_its_districts_include_lake_ports_and_that_the_overland_arc_is_a_reading(self):
        us_ca = next(f for f in self.fl if f["o"] == "USA" and f["d"] == "CAN")
        districts = metcoal.districts(EIA, YEAR, "CAN")
        for k in B.MET_LAKE_DISTRICTS:
            self.assertIn(k, districts, "the lake ports the note names are districts of the file")
            self.assertIn(k, us_ca["n"])
        self.assertIn("ports of the Great Lakes", us_ca["n"])
        self.assertIn("the file does not say by which mode", us_ca["n"])
        self.assertIn("reads the pair as overland", us_ca["n"])
        # a row of another destination does not carry the sentence
        self.assertFalse([f for f in self.fl if f["d"] != "CAN" and "Great Lakes" in f.get("n", "")])

    def test_the_definitions_are_printed_under_the_block_from_the_page_file(self):
        defs = self.d["flowDefs"]
        self.assertEqual(len(defs), 2, "one short sentence per source")
        self.assertIn("Queensland only", defs[0])
        for k in ("hard coking", "semi-soft coking", "PCI", "first destination"):
            self.assertIn(k, defs[0])
        self.assertIn("rank metallurgical as declared", defs[1])
        self.assertIn("first destination", defs[1])
        self.assertLess(len(" ".join(defs)), 300, "the block stays compact")
        # the view prints them: from the page file, not from its own text
        view = read("web", "src", "components", "views", "CommodityView.tsx")
        self.assertIn("props.defs", view)
        self.assertNotIn("Queensland only", view)

    def test_the_exporters_without_a_source_by_destination_are_found_where_the_note_says(self):
        """Note of the coverage: for each exporter it names, the place it gives for its coal by pair exists in the files (a flow of the
        Thermal coal page, or the customs lanes of all coal), and no list of metallurgical coal holds it."""
        self.assertFalse({f["o"] for f in self.fl} - {"AUS", "USA"})
        th = load("commodities", "thermal-coal.json")
        self.assertEqual({f["s"] for f in th["flows"]}, {"baci"})
        self.assertEqual(th["labels"]["flows"], f"Main flows — all coal, customs data {YEAR}")
        lanes = [ln for ln in load("freight", "lanes", "coal.json")["lanes"] if ln["set"] == "main"]
        self.assertEqual(load("freight", "lanes", "coal.json")["label"], "Coal (all types)")
        text = next(n for n in self.d["notes"] if n.startswith("What these flows cover"))
        tail = text.split("list the customs lanes by sea. ")[1].rstrip(".")
        named = {c: seg for c, seg in (x.split(": ", 1) for x in tail.split("; "))}
        iso = {"Mongolia": "MNG", "Russia": "RUS", "Canada": "CAN", "Mozambique": "MOZ"}
        self.assertEqual(set(named), set(iso), "the four exporters of the table with no source by destination")
        for name, seg in named.items():
            flows = [f for f in th["flows"] if f["o"] == iso[name]]
            ln = [x for x in lanes if x["o"] == iso[name]]
            m = re.search(r"(\d+) of the (\d+) Main flows of the Thermal coal page", seg)
            self.assertEqual(bool(m), bool(flows), f"{name}: the note names the Thermal coal page exactly when it has a flow there")
            if m:
                self.assertEqual((int(m.group(1)), int(m.group(2))), (len(flows), len(th["flows"])), name)
                for f in flows[:3]:
                    self.assertIn(f"{B.cname(f['d'])} {B._fmt(f['v'])} Mt", seg, name)
            m = re.search(r"(\d+) lanes of the lane tables of both coal pages", seg)
            self.assertEqual(bool(m), bool(ln), f"{name}: the note names the lane tables exactly when it has a main lane there")
            if m:
                self.assertEqual(int(m.group(1)), len(ln), name)
            self.assertTrue(m or flows, f"{name}: the note names a place")
        # METHODOLOGY says the same of the four, in words: Mongolia and Russia have a Main flows row on the Thermal coal page, Canada and Mozambique the lanes only
        method = " ".join(read("METHODOLOGY.md").split())
        sentence = method[method.index("no list of metallurgical coal holds their coal by pair"):][:900]
        for name in ("Mongolia", "Russia", "Canada", "Mozambique"):
            self.assertIn(name, sentence)
        self.assertEqual({f["o"] for f in th["flows"]} & {"MNG", "RUS"}, {"MNG", "RUS"})
        self.assertFalse({f["o"] for f in th["flows"]} & {"CAN", "MOZ"})
        self.assertTrue({x["o"] for x in lanes} >= {"RUS", "CAN", "MOZ"})
        self.assertIn("Canada and Mozambique have no Main flows row", sentence)
        # the two pages whose lane table the note names: the Seaborne lanes of both read the coal file
        freight = read("web", "src", "lib", "freight.ts")
        self.assertRegex(freight, r"'thermal-coal': \['coal'\]")
        self.assertRegex(freight, r"'met-coal': \['coal', 'coke'\]")


class Words(unittest.TestCase):
    """5"""

    @classmethod
    def setUpClass(cls):
        d = page()
        cls.notes = d["notes"]
        cls.text = "\n".join(cls.notes)
        # the notes the flows block writes: from the Australian note to the one on the lanes
        i = next(k for k, n in enumerate(cls.notes) if n.startswith("Australia, "))
        j = next(k for k, n in enumerate(cls.notes) if n.startswith("The seaborne lanes of this page"))
        cls.flow_text = "\n".join(cls.notes[i:j + 1])
        cls.shown = {src: sum(f["v"] for f in d["flows"] if f["s"] == src) for src in (QLD, EIA)}
        t = load("commodities", "history", "met-coal.json")["t"]["exports"]
        k = t["years"].index(YEAR)
        cls.cover = {QLD: cls.shown[QLD] / t["c"]["AUS"][k], EIA: cls.shown[EIA] / t["c"]["USA"][k]}
        raw = pd.read_csv(os.path.join(CACHE, "baci_flows.csv.gz"))
        cl = C.clean(raw)
        cls.cu = cl[(cl["group"] == "coal") & (cl["year"] == YEAR)].groupby(["o", "d"])["t"].sum()

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

    def test_no_sum_of_the_two_exporters(self):
        both = (sum(metcoal.pairs(QLD, YEAR).values()) + sum(metcoal.pairs(EIA, YEAR).values())) / 1e6
        for s in (f"{both:.1f}", f"{both:,.0f} Mt", B._fmt(both)):
            self.assertNotIn(s, self.text)

    def test_no_percentage_but_the_two_coverages_the_builder_computes_from_the_cache(self):
        """The rule: a percentage in the notes of the flows is one the builder computes from the cache, and each is recomputed here."""
        got = re.findall(r"\d+(?:\.\d+)?%", self.flow_text)
        self.assertEqual(sorted(got), sorted(f"{self.cover[k]:.0%}" for k in (QLD, EIA)), "the coverage of each exporter against EIA International, and nothing else")

    def test_the_coverage_against_eia_international(self):
        """EIA International's exports of metallurgical coal, the figures of the notes: read from the tracked series by year."""
        t = load("commodities", "history", "met-coal.json")["t"]["exports"]
        i = t["years"].index(YEAR)
        aus, usa, world = t["c"]["AUS"][i], t["c"]["USA"][i], t["world"][i]
        n = next(n for n in self.notes if n.startswith("What these flows cover"))
        self.assertIn(f"exports of {B._fmt(aus)} Mt for Australia and {B._fmt(usa)} Mt for the United States, of {B._fmt(world)} Mt in the world", n)
        self.assertEqual(self.cover[QLD], self.shown[QLD] / aus, "recomputed with the builder's arithmetic: the rows listed over the figure of EIA")
        self.assertIn(f"The Queensland rows are {self.cover[QLD]:.0%} of the Australian figure", n)
        self.assertIn(f"the EIA rows {self.cover[EIA]:.0%} of the United States figure", n)
        # the exporters named with their figure are exporters of this table of EIA with at least B.MET_INTL_MIN_MT, in order of size
        big = {B.cname(c): v[i] for c, v in t["c"].items() if c not in ("AUS", "USA") and (v[i] or 0) >= B.MET_INTL_MIN_MT and B.cname(c) != c}
        named = n.split("No free source loaded gives destinations for ")[1].split(", and no list of metallurgical coal")[0]
        items = re.findall(r"([A-Z][A-Za-z ]+?) \(([\d.,]+) Mt\)", named)
        self.assertEqual({c for c, _ in items}, {"Mongolia", "Russia", "Canada", "Mozambique"})
        for c, v in items:
            self.assertEqual(v, B._fmt(big[c]), c)
        self.assertEqual([v for _, v in items], sorted((v for _, v in items), key=lambda x: -float(x.replace(",", ""))), "largest first")

    def test_the_counts_of_countries_and_the_queensland_total_of_the_next_year(self):
        q = next(n for n in self.notes if n.startswith("Australia, "))
        u = next(n for n in self.notes if n.startswith("United States, "))
        for n, src in ((q, QLD), (u, EIA)):
            allc, listed = len(metcoal.pairs(src, YEAR)), sum(1 for t in metcoal.pairs(src, YEAR).values() if t >= B.MET_FLOW_MIN)
            self.assertIn(f"to {allc} countries", n)
            sentence = f"{listed} of the {allc} countries have at least {B.MET_FLOW_MIN:,} t and are listed above"
            (self.assertIn if listed != allc else self.assertNotIn)(sentence, n)
        self.assertIn("34 countries", u)
        self.assertIn("32 of the 34 countries", u, "the block lists 32 rows of the 34 countries: the two numbers and why")
        total = metcoal.meta(QLD)["totals"][f"{YEAR + 1}-metallurgical"]
        self.assertIn(f"Queensland's total of {YEAR + 1}: {B._fmt(total / 1e6)} Mt.", q)
        self.assertEqual(total, sum(metcoal.pairs(QLD, YEAR + 1).values()))

    def test_the_districts_of_the_notes_are_the_file_s_and_no_source_is_claimed_for_hampton_roads(self):
        u = next(n for n in self.notes if n.startswith("United States, "))
        du = sorted(metcoal.ports(EIA, YEAR).items(), key=lambda kv: -kv[1])
        self.assertIn("By customs district, as the file names them: " + ", ".join(f"{k} {B._fmt(v / 1e6)} Mt" for k, v in du[:5]), u)
        can = metcoal.districts(EIA, YEAR, "CAN")
        self.assertIn(f"of the {B._fmt(metcoal.pairs(EIA, YEAR)['CAN'] / 1e6)} Mt to Canada, {B._fmt(can['Buffalo, NY'] / 1e6)} Mt left through Buffalo, NY", u)
        self.assertIn("Cleveland, OH and Detroit, MI, ports of the Great Lakes", u)
        self.assertNotIn("Hampton Roads", self.text, "no file on disk states it: only the district's name is printed")

    def test_queensland_credit_and_disclaimer_in_the_publisher_s_words(self):
        q = next(n for n in self.notes if n.startswith("Australia, "))
        m = metcoal.meta(QLD)
        self.assertIn(f'Credit as the workbook\'s About sheet gives it: "{m["credit"]}"', q)
        self.assertIn(f'The disclaimer of the About sheet reads: "{m["disclaimer_full"]}"', q)
        self.assertIn("(CC BY 4.0)", q)

    def test_the_examples_of_the_first_destination_note_are_the_cache_s_figures(self):
        """The India and Singapore examples, the largest gap and the counts of pairs above the customs record: the builder's arithmetic, here from the cache."""
        n = next(n for n in self.notes if n.startswith("First destination is not always the buyer"))
        above = [(o, d, t, float(self.cu.get((o, d), 0))) for o, src in (("AUS", QLD), ("USA", EIA)) for d, t in metcoal.pairs(src, YEAR).items()
                 if t >= B.MET_FLOW_MIN and t > float(self.cu.get((o, d), 0))]
        nq, nu = (sum(1 for t in metcoal.pairs(src, YEAR).values() if t >= B.MET_FLOW_MIN) for src in (QLD, EIA))
        self.assertIn(f"{sum(1 for r in above if r[0] == 'AUS')} of the {nq} Queensland pairs and {sum(1 for r in above if r[0] == 'USA')} of the {nu} United States pairs", n)
        big = max(above, key=lambda r: r[2] - r[3])
        self.assertIn(f"the largest gap is {B.cname(big[0])} to {B.cname(big[1])}, {B._fmt(big[2] / 1e6)} Mt against {B._fmt(big[3] / 1e6)} Mt in customs data", n)
        ind = metcoal.pairs(QLD, YEAR)["IND"]
        cq = float(self.cu[("AUS", "IND")])
        self.assertIn(f"customs data record {B._fmt(cq / 1e6)} Mt of all coal and Queensland {B._fmt(ind / 1e6)} Mt of metallurgical coal, and the difference ({B._fmt((cq - ind) / 1e6)} Mt)", n)
        self.assertEqual(big[1], "SGP", "Singapore: the largest gap")

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


    def test_no_page_prints_a_date_the_files_do_not_have(self):
        """The dates of the two files are in the meta file (written by the extractor from the workbook's About sheet and from EIA_FILE_DATE). The registry's
        update texts are built from it; NOTICE.md and METHODOLOGY quote them: a refresh that forgets one of them fails here."""
        mq, me = metcoal.meta(QLD), metcoal.meta(EIA)
        src = {s["id"]: s for s in load("sources.json")}
        self.assertIn(mq["data_through"][0].lower() + mq["data_through"][1:], src[QLD]["update"])
        self.assertIn(mq["current_as_at"][0].lower() + mq["current_as_at"][1:], src[QLD]["update"])
        d, m, y = (int(x) for x in me["file_date"].split("-")[::-1])
        eia_date = f"{d} {B.MONTHS[m - 1]} {y}"
        self.assertIn(eia_date, src[EIA]["update"])
        notice, method = " ".join(read("NOTICE.md").split()), " ".join(read("METHODOLOGY.md").split())
        for text in (notice, method):
            self.assertIn(f'"{mq["data_through"]}" and "{mq["current_as_at"]}"', text)
        self.assertIn(f"file dated {eia_date}", notice)
        self.assertEqual(X.EIA_FILE_DATE, me["file_date"], "the constant of the extractor is what the meta file holds")
        self.assertIn(eia_date, " ".join(page()["notes"]))


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


if __name__ == "__main__":
    unittest.main()
