"""Tests of the last corrections before the seventh release: the Census Bureau's Public-Use Statement in the registry, the parts of an estimate that add
to their total, what the other years of the LPG pair are, what a year note of a lane file counts, the count of groups that reach the target of the generated
routes, and the words about CEPII BACI's extract.

Each test fails on the tree before the corrections. Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The tests read the files as the builders last wrote them; none needs raw/.
"""
import glob
import json
import os
import re
import sys
import unittest

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import comtrade_tin  # noqa: E402
import modes as MD  # noqa: E402
import us_lpg  # noqa: E402

DATA = os.path.join(ROOT, "data")


def load(*parts):
    with open(os.path.join(DATA, *parts), encoding="utf-8") as f:
        return json.load(f)


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def strings(v):
    """Every string of a JSON document."""
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from strings(x)


def all_data_strings():
    for f in glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True):
        if os.sep + "_status" + os.sep in f:
            continue
        with open(f, encoding="utf-8") as fh:
            for s in strings(json.load(fh)):
                yield os.path.relpath(f, DATA), s


class CensusRegistry(unittest.TestCase):
    """The text of the registry for census-exports says what the pages read says, and no more."""

    @classmethod
    def setUpClass(cls):
        cls.src = {s["id"]: s for s in load("sources.json")}["census-exports"]

    def test_the_text_quotes_the_statement_with_its_page_and_date(self):
        t = self.src["licence"]
        self.assertTrue(t.startswith("U.S. Census Bureau Public-Use Statement"))
        self.assertIn("https://www.census.gov/about/policies/citation.html", t)
        self.assertIn("page last revised 24 February 2026", t)
        self.assertIn("Data users who create their own estimates using data from disseminated tables and other data should cite the Census Bureau as the source of the original data only.", t)
        self.assertIn("Conclusions drawn from any analysis of these data are the sole responsibility of the performing party.", t)
        self.assertIn("all international trade data products previously available by subscription are now available to the public at no cost", t)  # the sentence of the data-products page
        self.assertIn("No statement of copyright was found on the pages read", t)

    def test_the_text_claims_neither_a_public_domain_nor_that_no_copyright_is_claimed(self):
        t = self.src["licence"]
        self.assertNotRegex(t, r"(?i)public domain")
        self.assertNotIn("no copyright is claimed", t)

    def test_the_text_says_what_the_site_prints_and_the_repository_keeps(self):
        t = self.src["licence"]
        self.assertIn("The site publishes no row of the Census file and offers none for download: it prints an estimate of its own made from the data and a few totals "
                      "of the file by product and country (quantity, weight by vessel), each credited to the Census Bureau, and the repository keeps a small cache of those totals.", t)
        self.assertNotIn("The atlas publishes no row", t)
        notice = " ".join(read("NOTICE.md").split())
        self.assertIn("The site publishes no row of the file and offers none for download", notice)
        self.assertIn("the repository keeps a small cache of those totals", notice)
        cache = json.loads(read("pipeline", "cache", "us_lpg_volumes.json"))  # the cache the sentence speaks of
        self.assertIn("census", cache)

    def test_no_text_of_the_repository_calls_the_census_file_public_domain(self):
        """Every file (code, tests, texts, data): no line that says "public domain" has the Census Bureau or its file in it or in the three lines above it
        (a docstring or a list item wraps over several lines). The EIA files are EIA's own (a window that names EIA is left out) and "no public domain" says the opposite."""
        census = re.compile(r"(?i)Census|EXDB|USA Trade Online")
        eia = re.compile(r"EIA|Energy Information Administration")
        negated = re.compile(r"(?i)\bno public domain")
        domain = re.compile(r"(?i)public[\s-]domain")

        def bad(text):
            lines = text.splitlines()
            return [" ".join(lines[max(0, i - 3):i + 1])[-160:] for i, ln in enumerate(lines)
                    if domain.search(negated.sub("", ln))
                    and census.search(" ".join(lines[max(0, i - 3):i + 1])) and not eia.search(" ".join(lines[max(0, i - 3):i + 1]))]
        found = []
        skip = {".git", "node_modules", "raw", ".venv", "dist"}
        me = os.path.abspath(__file__)
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in skip]
            for name in files:
                path = os.path.join(base, name)
                if os.path.abspath(path) == me or name.endswith((".gz", ".png", ".zip", ".xlsx", ".woff2", ".pbf", ".ico", ".jpg", ".lock")) or name == "licence.test.mjs":
                    continue
                try:
                    with open(path, encoding="utf-8") as fh:
                        text = fh.read()
                except (UnicodeDecodeError, OSError):
                    continue
                if name.endswith(".json"):
                    try:
                        found += [(os.path.relpath(path, ROOT), s) for v in strings(json.loads(text)) for s in bad(v)]
                    except ValueError:
                        found += [(os.path.relpath(path, ROOT), s) for s in bad(text)]
                else:
                    found += [(os.path.relpath(path, ROOT), s) for s in bad(text)]
        self.assertEqual(found, [])
        # the search finds the sentence this test was written for
        self.assertTrue(bad("  * US Census Bureau, USA Trade Online export detail file (EXDB2412.ZIP):\n    the quantity. The file gives a weight for vessel and air cargo only.\n    Public domain.\n"))

    def test_data_sources_carries_the_same_text(self):
        self.assertIn(self.src["licence"], read("DATA_SOURCES.md"))

    def test_no_row_of_the_site_has_the_census_file_as_its_own_source(self):
        """The statement covers an estimate made from the data, not a row of the file: the registry id appears only as the input of an estimate."""
        own = []

        def walk(v, where):
            if isinstance(v, dict):
                for k, x in v.items():
                    if k == "s" and x == "census-exports":
                        own.append(where)
                    else:
                        walk(x, f"{where}.{k}")
            elif isinstance(v, list):
                for i, x in enumerate(v):
                    walk(x, f"{where}[{i}]")
        for f in glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True):
            if f.endswith(os.sep + "sources.json"):
                continue
            with open(f, encoding="utf-8") as fh:
                walk(json.load(fh), os.path.relpath(f, DATA))
        self.assertEqual(own, [])

    def test_the_estimated_row_cites_the_census_bureau_as_the_source_of_the_original_data(self):
        f = next(x for x in load("commodities", "lpg.json")["flows"] if x["o"] == "USA" and x["d"] == "MEX")
        self.assertEqual(f["s"], "atlas")
        self.assertIn("the US Census Bureau's export detail file", f["n"])


class PartsOfAnEstimate(unittest.TestCase):
    PAIR = re.compile(r"(\d+)% of (?:world |this )?tonnage (?:is an Atlas estimate|estimated): (\d+)% from (?:a|the) volume[^,;]*, (\d+)% from")

    def test_every_pair_of_parts_the_builders_print_adds_to_its_total_at_the_precision_printed(self):
        n = 0
        for where, s in all_data_strings():
            for m in self.PAIR.finditer(s):
                total, vol, val = (int(x) for x in m.groups())
                self.assertEqual(total, vol + val, f"{where}: {m.group(0)}")
                n += 1
        self.assertGreaterEqual(n, 3, "the LPG page prints such sentences")

    def test_the_lane_file_carries_the_shares_the_footer_computes_its_two_parts_from(self):
        f = load("freight", "lanes", "lpg.json")
        # the value part is 1.61 Mt of 129.65 Mt, 1.2%: the four-decimal shares of the latest year give it, the three-decimal ones of the year lists gave 1.3%
        i = f["years"].index(f["y"])
        self.assertAlmostEqual(f["est"] - f["estVol"], 0.0124, places=4)
        self.assertEqual(f"{(f['est'] - f['estVol']) * 100:.1f}", "1.2")
        note = f["yearNotes"][str(f["y"])]
        mt = float(re.search(r"from declared value \(([\d.]+) Mt\)", note).group(1))
        self.assertEqual(f"{mt / f['seaborne'][i] * 100:.1f}", "1.2")


class OtherYearsOfTheLpgPair(unittest.TestCase):
    OLD = "The other years of this pair are customs totals for all modes, with the split not known"

    def test_years_text(self):
        self.assertEqual(MD._years_text([2021, 2022, 2023]), "2021 to 2023")
        self.assertEqual(MD._years_text([2022]), "2022")
        self.assertEqual(MD._years_text([2021, 2023]), "2021 and 2023")

    def test_the_sentence_is_built_from_the_years_the_cleaning_replaces(self):
        self.assertEqual(us_lpg.CORRECTED[("lpg", "USA", "MEX")], (2021, 2022, 2023, 2024))
        s = MD.other_years("lpg", "USA", "MEX", 2024)
        self.assertEqual(s, "The other years of this pair are for all modes: the customs total before 2021, the atlas's estimate from EIA's volume for 2021 to 2023; "
                            "in none of those years is the split by mode known")
        saved = us_lpg.CORRECTED
        try:
            us_lpg.CORRECTED = {("lpg", "USA", "MEX"): (2022, 2023, 2024)}
            self.assertIn("customs total before 2022, the atlas's estimate from EIA's volume for 2022 to 2023", MD.other_years("lpg", "USA", "MEX", 2024))
        finally:
            us_lpg.CORRECTED = saved

    def test_the_flags_of_the_lane_are_the_years_of_the_sentence(self):
        lane = next(x for x in load("freight", "lanes", "lpg.json")["lanes"] if x["id"] == "lpg:USA-MEX")
        est = sorted(int(y) for y, f in lane["histFlags"].items() if f == "est")
        self.assertEqual(est, [2021, 2022, 2023, 2024])
        for where, text in (("the note of the lane", lane["flow"]["n"]),):
            self.assertIn("the customs total before 2021, the atlas's estimate from EIA's volume for 2021 to 2023", text, where)
        # the customs years before 2021 are the customs total: no flag
        self.assertEqual([y for y in lane["histFlags"] if int(y) < 2021], [])

    def test_no_page_says_the_other_years_are_customs_totals(self):
        for where, s in all_data_strings():
            self.assertNotIn(self.OLD, s, where)
            self.assertNotIn("The other years of the pair stay customs totals for all modes", s, where)
        pair = next(x for x in load("commodities", "lpg.json")["flows"] if x["o"] == "USA" and x["d"] == "MEX")
        self.assertIn("in none of those years is the split by mode known", pair["n"])
        self.assertIn("in none of those years is the split by mode known", " ".join(load("commodities", "lpg.json")["notes"]))


class YearNotesOfTheLaneFiles(unittest.TestCase):
    def test_a_row_added_from_the_importer_says_whether_it_is_in_the_seaborne_figure(self):
        n = 0
        for f in sorted(glob.glob(os.path.join(DATA, "freight", "lanes", "*.json"))):
            group = os.path.basename(f)[:-5]
            pairs = load("freight", "pairs", f"{group}.json")
            ix = {c: i for i, c in enumerate(pairs["cols"])}
            added = pairs.get("added", {})
            lanes = load("freight", "lanes", f"{group}.json")
            for key in added:
                o, d = key.split("-")
                row = next(r for r in pairs["rows"] if r[ix["o"]] == o and r[ix["d"]] == d)
                overland = row[ix["m"]] in (2, 3)  # mixed or land: not in the seaborne figure
                for y, note in lanes["yearNotes"].items():
                    if "import declaration" not in note:
                        continue
                    n += 1
                    self.assertEqual("All modes: includes" in note, overland, f"{group} {y}")
                    if overland:
                        self.assertIn("not in the seaborne figure", note, f"{group} {y}")
        self.assertGreaterEqual(n, 8, "the tin file has one such note in each year from 2017")

    def test_the_tin_note_under_the_seaborne_figure_says_all_modes(self):
        notes = load("freight", "lanes", "tin-ore.json")["yearNotes"]
        self.assertTrue(notes["2024"].startswith("All modes: includes Myanmar to China, 0.0765 Mt (overland: not in the seaborne figure), from China's import declaration"))


class TheExtractOfBaci(unittest.TestCase):
    def test_no_note_says_baci_has_no_row_where_the_atlas_extract_has_none(self):
        for where, s in all_data_strings():
            self.assertNotIn("not in CEPII BACI", s, where)
            self.assertNotRegex(s, r"(?<!extract of )CEPII BACI has no row for the pair", where)
            self.assertNotRegex(s, r"no row in 20\d\d\)", where)

    def test_the_pair_note_names_the_extract_and_its_threshold(self):
        note = load("freight", "pairs", "tin-ore.json")["notes"]["MMR-CHN"]
        self.assertIn("not in the atlas's extract of CEPII BACI", note)
        self.assertIn("the atlas's extract of CEPII BACI has no row for the pair (the extract drops flows under 1,000 t and USD 1 million)", note)
        self.assertEqual(comtrade_tin.note(2024, None).count("the atlas's extract of CEPII BACI"), 2)

    def test_the_break_note_says_the_extract_has_no_row_in_2016(self):
        n = load("freight", "lanes", "tin-ore.json")["yearNotes"]["2017"]
        self.assertIn("the pair is the atlas's extract of CEPII BACI up to 2016 (no row in the extract in 2016)", n)

    def test_each_year_note_says_what_the_extract_holds_for_the_pair_that_year(self):
        """The clause of the tin year notes is built from the row the declaration replaces: its tonnes, or that the extract has no row."""
        extract = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        t = extract[(extract["group"] == "tin-ore") & (extract["o"] == "MMR") & (extract["d"] == "CHN")].groupby("year")["t"].sum()
        notes = load("freight", "lanes", "tin-ore.json")["yearNotes"]
        with_row = no_row = 0
        for y in range(2017, 2025):
            note = notes[str(y)]
            if y in t.index:
                with_row += 1
                self.assertIn(f"the atlas's extract of CEPII BACI has {t[y]:,.0f} t for the pair in {y}, which the declaration replaces", note, y)
                self.assertNotIn("has no row for the pair", note, y)
            else:
                no_row += 1
                self.assertIn(f"the atlas's extract of CEPII BACI has no row for the pair in {y} (the extract drops flows under 1,000 t and USD 1 million)", note, y)
                self.assertNotIn("t for the pair in", note, y)
            self.assertNotIn("not in the atlas's extract", note, y)
        self.assertGreater(with_row, 0)
        self.assertGreater(no_row, 0)

    def test_the_route_finder_makes_no_claim_on_the_extract(self):
        src = read("web", "src", "components", "RouteFinder.tsx")
        self.assertNotIn("not in the atlas's extract", src)

    def test_the_comtrade_text_says_what_the_extract_and_the_file_hold(self):
        """The registry text, DATA_SOURCES.md and the heading of rule 11 give the extract's rows of the pair (at under 2 kt a year; no row in some years)."""
        extract = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        t = extract[(extract["group"] == "tin-ore") & (extract["o"] == "MMR") & (extract["d"] == "CHN") & (extract["year"] >= 2017)].groupby("year")["t"].sum()
        self.assertLess(t.max(), 2000)
        self.assertGreaterEqual(t.max(), 1000)  # "under 2 kt" and not "under 1 kt"
        gone = sorted(set(range(2017, 2025)) - set(t.index))
        self.assertEqual(gone, [2021, 2022, 2024])
        want = "that CEPII BACI records at under 2 kt a year (the atlas's extract has no row for it in 2021, 2022 and 2024"
        use = [s["use"] for s in load("sources.json") if s["id"] == "comtrade"][0]
        self.assertIn(want, use)
        self.assertNotIn("BACI lacks", use)
        self.assertIn(want, " ".join(read("DATA_SOURCES.md").split()))
        self.assertNotIn("BACI lacks", read("DATA_SOURCES.md"))
        heading = [ln for ln in read("METHODOLOGY.md").splitlines() if "tin ores and concentrates from Myanmar to China**" in ln]
        self.assertEqual(len(heading), 1)
        self.assertIn("CEPII BACI records at under 2 kt a year (the atlas's extract has no row for the pair in 2021, 2022 and 2024)", heading[0])

    def test_the_cleaning_rule_gives_what_the_cache_holds(self):
        """The docstring of clean.py rule 11 gives the range of the extract's tonnes for the pair in 2017 to 2024."""
        raw = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        t = raw[(raw["group"] == "tin-ore") & (raw["o"] == "MMR") & (raw["d"] == "CHN") & (raw["year"] >= 2017)].set_index("year")["t"]
        doc = " ".join(read("pipeline", "trade", "clean.py").split())
        self.assertIn(f"has {t.min():,.0f} to {t.max():,.0f} t a year for the pair in 2017 to 2024", doc)
        self.assertIn("no row in " + ", ".join(str(y) for y in (2021, 2022)) + " and 2024", doc)
        self.assertEqual(sorted(set(range(2017, 2025)) - set(t.index)), [2021, 2022, 2024])


class SeaShareOfAKnownSplit(unittest.TestCase):
    """A flow of mode mixed carries the share by sea (`seaShare`) only where the pairs file knows the split of its pair, and the share is the one its note prints."""

    def test_the_field_is_the_share_of_the_note_and_exists_only_for_a_pair_the_pairs_file_cuts(self):
        seen = []
        for path in sorted(glob.glob(os.path.join(DATA, "commodities", "*.json"))):
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            for f in (doc.get("flows") or []) if isinstance(doc, dict) else []:
                group = f["lane"].split(":")[0] if f.get("lane") else None
                rest = set()
                if group and os.path.exists(os.path.join(DATA, "freight", "pairs", f"{group}.json")):
                    rest = {(o, d) for o, d, _ in load("freight", "pairs", f"{group}.json").get("rest", [])}
                cut = (f["o"], f["d"]) in rest
                self.assertEqual("seaShare" in f, cut, f"{os.path.basename(path)} {f['o']}-{f['d']}")
                if cut:
                    seen.append((os.path.basename(path), f["o"], f["d"]))
                    self.assertEqual(f["mode"], "mixed")
                    self.assertIn(f"{f['seaShare']:.0%} of the pair's", f["n"])  # the sentence of the split note
                    self.assertGreater(f["seaShare"], 0)
                    self.assertLess(f["seaShare"], 1)
        self.assertEqual(seen, [("lpg.json", "USA", "MEX")])

    def test_the_other_mixed_flows_have_no_share(self):
        mixed = [f for f in load("commodities", "lpg.json")["flows"] if f.get("mode") == "mixed" and f["o"] != "USA"]
        self.assertTrue(all("seaShare" not in f for f in mixed))


class TheTwoBlocksOfACountryPage(unittest.TestCase):
    """The freight block of a country page counts as an estimate what the balance block does, for the same total (every mode)."""

    def test_the_estimated_tonnes_of_the_freight_block_are_the_estimated_share_of_the_balance_block_times_its_total(self):
        checked = 0
        for path in sorted(glob.glob(os.path.join(DATA, "countries", "profiles", "*.json"))):
            doc = json.load(open(path, encoding="utf-8"))
            for side, part in (("exports", "customers"), ("imports", "suppliers")):
                for x in (doc.get("freight") or {}).get(side, []):
                    for b in doc.get("balance") or []:
                        p = b.get(part)
                        if not p or p.get("g") != x["g"]:
                            continue
                        checked += 1
                        tol = x["kt"] * 1e-4 + 0.5  # the share is rounded to four decimals, the tonnes to 0.1 kt
                        where = f"{os.path.basename(path)} {side} {x['g']}"
                        self.assertAlmostEqual(x.get("estKt", 0), p.get("estShare", 0) * x["kt"], delta=tol, msg=where)
                        self.assertAlmostEqual(x.get("estVolKt", 0), p.get("estVolShare", 0) * x["kt"], delta=tol, msg=where)
        self.assertGreater(checked, 1000)

    def test_the_two_pages_of_the_lpg_pair_count_the_overland_part(self):
        rest = {(o, d): kt for o, d, kt in load("freight", "pairs", "lpg.json")["rest"]}
        kt = rest[("USA", "MEX")]
        usa = next(x for x in load("countries", "profiles", "USA.json")["freight"]["exports"] if x["g"] == "lpg")
        mex = next(x for x in load("countries", "profiles", "MEX.json")["freight"]["imports"] if x["g"] == "lpg")
        pair = next(r for r in load("freight", "pairs", "lpg.json")["rows"] if r[0] == "USA" and r[1] == "MEX")
        self.assertAlmostEqual(mex["estKt"], pair[2] + kt, delta=0.1)  # the pair in all modes: the part by sea and the part read as overland
        self.assertAlmostEqual(mex["estVolKt"], mex["estKt"], delta=0.1)
        self.assertGreater(usa["estKt"], usa["estVolKt"])  # the part from the declared value is still told apart


class RoutesTarget(unittest.TestCase):
    """The count and the names of the groups that reach the target of the generated routes, as METHODOLOGY writes them, are the ones of QA_routes.md."""

    NUMBERS = {"nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13}

    @classmethod
    def setUpClass(cls):
        qa = read("pipeline", "freight", "QA_routes.md")
        cls.rows = {}
        for line in qa.splitlines():
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(c) == 6 and re.fullmatch(r"[a-z][a-z0-9-]*", c[0]):
                cls.rows[c[0]] = c
        cls.header = re.search(r"(\d+) of (\d+) groups reach the target", qa)
        cls.method = " ".join(read("METHODOLOGY.md").split())

    def test_the_count_and_the_names(self):
        reach = {g for g, c in self.rows.items() if not c[5]}
        self.assertEqual(len(reach), int(self.header.group(1)))
        self.assertEqual(len(self.rows), int(self.header.group(2)))
        m = re.search(r"(\w+) of the (\d+) groups reach 70% \(([^)]*)\)", self.method)
        self.assertTrue(m, "METHODOLOGY says how many groups reach 70% and which")
        self.assertEqual(self.NUMBERS[m.group(1)], len(reach))
        self.assertEqual(int(m.group(2)), len(self.rows))
        names = [x.strip() for x in re.split(r",| and ", m.group(3)) if x.strip()]
        ids = {"ferro-nickel": "nickel-fe"}
        self.assertEqual({ids.get(n, n.replace(" ", "-")) for n in names}, reach)

    def test_a_group_under_the_target_is_not_named_among_those_that_reach_it(self):
        m = re.search(r"it, among them LPG \((\d+\.\d)%", self.method)
        self.assertTrue(m)
        self.assertEqual(m.group(1), self.rows["lpg"][3])
        self.assertTrue(self.rows["lpg"][5], "LPG has a reason: it is under the target")
        self.assertLess(float(self.rows["lpg"][3]), 70)


if __name__ == "__main__":
    unittest.main()
