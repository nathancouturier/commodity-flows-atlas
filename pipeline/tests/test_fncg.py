"""Tests of the corrections after the verification review (package FNCG): the passage pages, the web and the texts.

G1  the note of a ship type against IMF PortWatch is written once on the passage record (`typeNotes`), the figure of a note is the figure of the page
G6  every page with a main lane typed in a class is among that class's cargoes
G8  country pages: a small share or a small sub-line is never printed as "0.0%" or "0.00 Mt"
G9  METHODOLOGY: the numbers of estimated rows, of hand-written routes and the other counts of the files, recomputed
G13 METHODOLOGY and the recipe: the prices that the atlas publishes

The web tests of the package are in web/scripts (chokepoint-notes, table-covers, price-window, mixed-shown, search-aliases, cargo-chips).

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The tests of the data files read the files as the builders last wrote them.
"""
import glob
import json
import os
import re
import sys
import unittest
from decimal import ROUND_HALF_UP, Decimal

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities", "prices"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import build_freight as BF  # noqa: E402

DATA = os.path.join(ROOT, "data")


def load(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return json.load(f)


def page3(v):
    """The figure of the page: Intl.NumberFormat with three significant digits (half up on the decimal figure), as ChokepointView prints it."""
    d = Decimal(repr(float(v)))
    return float(d.quantize(Decimal(1).scaleb(d.adjusted() - 2), rounding=ROUND_HALF_UP)) if d else 0.0


class G1PassageNotes(unittest.TestCase):
    def test_the_rounding_of_a_note_is_the_one_of_the_page(self):
        """GV6D.9: the page prints the stored figure (5.865 Mt) as 5.87; the note was written from the unrounded tonnage (5.8649 Mt, "5.86")."""
        self.assertEqual(f"{5.8649:.3g}", "5.86")  # what the note said
        self.assertEqual(BF.sig3(5.865), 5.87)
        self.assertEqual(BF.mtp(5.865), "5.87 Mt")
        self.assertEqual(BF.mtp(1084.7), "1,080 Mt")  # three digits, as the page prints a figure of 1,000 Mt or more
        self.assertEqual(BF.mtn(1084.7), "1,085 Mt")  # a total of a note keeps its integer digits
        self.assertEqual([BF.sig3(v) for v in (0.0123, 9.995, 10.05, 203.5, 99.95, 0.0)], [0.0123, 10.0, 10.1, 204.0, 100.0, 0.0])
        self.assertEqual(BF.ktn(0.0123), "12.3 kt")
        self.assertEqual(BF.ktn(0.00004), "under 0.1 kt")

    def test_the_near_line_never_says_100_percent_while_the_tonnage_is_below(self):
        """FNCI (GV8B.7): {low / ref:.0%} printed "100%" for a ratio of 99.5% to 100%; the share is floored."""
        self.assertEqual([BF.pct_floor(v, 1000.0) for v in (997.0, 995.0, 999.9, 1000.0, 904.0, 936.7, 970.1)], ["99%", "99%", "99%", "100%", "90%", "93%", "97%"])
        n = BF.passage_type_note("dry", "near", 997.0, 1000.0, 1100.0, 2023, 2024, "", "whole", 0, 3)
        self.assertIn("is 99% of IMF PortWatch's 1,000 Mt for all dry bulk ships in 2024", n["line"])
        self.assertNotIn("100%", n["line"])
        self.assertEqual(n["cmp"], "near")
        # the lines of the file are those of the function: Makassar dry bulk, 1,016.1 of 1,084.7 Mt, is 93.7% and reads 93%
        mak = next(c for c in load(DATA, "freight", "chokepoints.json") if c["id"] == "makassar")["typeNotes"]["dry"]
        self.assertIn(f"is {BF.pct_floor(mak['low'], mak['ref'])} of IMF PortWatch's", mak["line"])
        for c in load(DATA, "freight", "chokepoints.json"):
            for tn in (c.get("typeNotes") or {}).values():
                if tn["cmp"] == "near":
                    self.assertIn(f"is {BF.pct_floor(tn['low'], tn['ref'])} of ", tn["line"], c["id"])

    def test_a_note_is_written_from_the_figure_that_is_stored(self):
        """The rounding twice (the file stores 5.865, the page prints 5.87) is the case of the review: the note says 5.87, from the stored figure."""
        def row(o, d, t, via=()):
            return {"m": 0, "t": t, "via": set(via), "alt": set(), "o": o, "d": d, "load": 0}
        pairs = {"sunflower-meal": {"seaborne": 7.92, "rows": [row("UKR", "CHN", 5.8649, via=["bosphorus"])]},
                 "corn": {"seaborne": 12.0, "rows": [row("UKR", "EGY", 9.9951, via=["bosphorus"])]}}  # 9.9951 is stored as 9.995 and printed 9.99 or 10
        chk = [{"id": "bosphorus", "name": "Turkish Straits", "portwatch": True}]
        BF.chokepoint_shares(chk, pairs, {"bosphorus": {2024: {"dry": 500.0, "tanker": 500.0, "cargo": 500.0}}}, {}, {}, 2024, None)
        e = {x["p"]: x for x in chk[0]["estimates"]}
        self.assertEqual(e["sunflower-meal"]["mt"][0], 5.865)
        self.assertTrue(e["sunflower-meal"]["f"]["n"].startswith("at least 5.87 Mt of "), e["sunflower-meal"]["f"]["n"][:40])
        self.assertEqual(e["corn"]["mt"][0], 9.995)
        self.assertEqual(page3(9.995), 10.0)
        self.assertTrue(e["corn"]["f"]["n"].startswith("at least 10 Mt of "), e["corn"]["f"]["n"][:40])

    def test_the_figure_of_every_note_is_the_figure_of_the_page(self):
        n = 0
        for c in load(DATA, "freight", "chokepoints.json"):
            for e in c.get("estimates") or []:
                small = bool(re.search(r"[\d.,]+ kt of seaborne", e["f"]["n"]))
                shown = lambda v: f"{BF.ktn(v)}" if small else f"{page3(v):,.10g} Mt"  # noqa: E731
                m = re.match(r"at least ([\d,.]+ (?:Mt|kt)) of ", e["f"]["n"])
                if m:
                    self.assertEqual(m.group(1), shown(e["mt"][0]), (c["id"], e["p"]))
                    n += 1
                if e.get("hi"):
                    m = re.match(r"up to ([\d,.]+ (?:Mt|kt))", e["hi"]["n"])
                    self.assertTrue(m, (c["id"], e["p"], e["hi"]["n"][:60]))
                    self.assertEqual(m.group(1), shown(e["mt"][1]), (c["id"], e["p"]))
                    n += 1
        self.assertGreater(n, 800)
        bos = next(c for c in load(DATA, "freight", "chokepoints.json") if c["id"] == "bosphorus")
        e = next(e for e in bos["estimates"] if e["p"] == "sunflower-meal")
        self.assertEqual(e["mt"][0], 5.865)
        self.assertTrue(e["f"]["n"].startswith("at least 5.87 Mt of "), e["f"]["n"][:50])

    def test_the_note_of_a_ship_type_is_written_once_on_the_passage(self):
        chk = load(DATA, "freight", "chokepoints.json")
        k9 = {(r["chokepoint"], r["type"]): r for r in load(ROOT, "pipeline", "cache", "trade_checks.json")["findings"]
              if r["check"] == "K9" and r.get("kind") == "passage"}
        noted = {(c["id"], t) for c in chk for t in c.get("typeNotes") or {}}
        self.assertGreaterEqual(len(noted), 10)
        for c in chk:
            for e in c.get("estimates") or []:
                self.assertNotRegex(e["f"]["n"], r"PortWatch's (volume|estimate)", (c["id"], e["p"]))
                self.assertNotIn("best full year", e["f"]["n"], (c["id"], e["p"]))
            for t, tn in (c.get("typeNotes") or {}).items():
                r = k9[(c["id"], t)]
                self.assertEqual(tn["low"], r["value"], (c["id"], t))  # the figure of the note is the one of the K9 check
                self.assertEqual(tn["ref"], r["reference"], (c["id"], t))
                self.assertEqual(tn["groups"], sum(BF.vessel_type(e["p"]) == t for e in c["estimates"]), (c["id"], t))
        # the two passages of the review
        for cp, ref in (("bosphorus", 203), ("gibraltar", 384)):
            tn = next(c for c in chk if c["id"] == cp)["typeNotes"]["dry"]
            self.assertGreater(tn["low"], tn["ref"])
            self.assertLess(abs(tn["ref"] - ref), 1)
            self.assertEqual(tn["regime"], "whole")
            self.assertIn("probably overstate the passage", tn["line"])
            self.assertLess(len(tn["line"]), 220)

    def test_where_the_cap_binds_the_note_says_so(self):
        """GV7A.4: in the whole-volume regime the note of the type is a rule and says on how many groups the cap binds; the groups are those tagged."""
        capped = 0
        for c in load(DATA, "freight", "chokepoints.json"):
            for t, tn in (c.get("typeNotes") or {}).items():
                if tn["regime"] != "whole":
                    self.assertNotIn("cannot exceed the whole of PortWatch's volume", tn["n"], (c["id"], t))
                    continue
                self.assertIn("cannot exceed the whole of PortWatch's volume of these ships", tn["n"], (c["id"], t))
                self.assertIn("The cap binds only where a figure is tagged 'capped at PortWatch volume'", tn["n"], (c["id"], t))
                tagged = [e for e in c["estimates"] if BF.vessel_type(e["p"]) == t and "capped at" in (e.get("hi") or {}).get("n", "")]
                self.assertEqual(tn["capped"], len(tagged), (c["id"], t))
                capped += len(tagged)
                self.assertNotIn("The 'up to' figures of these groups are capped at the whole", tn["n"])
        self.assertEqual(capped, 4)  # Lombok and Makassar iron ore, Torres LNG and refined products

    def test_the_size_of_the_passage_file(self):
        """GV6D.1: the file no longer holds the same paragraph a hundred times (882,538 bytes before, 517,061 on the released site)."""
        size = os.path.getsize(os.path.join(DATA, "freight", "chokepoints.json"))
        self.assertLess(size, 760_000)

    def test_wording_of_the_three_regimes(self):
        """FNCD's wording of the regimes is kept: the whole volume, the normal itinerary (an alert), and the line of PortWatch being an estimate."""
        chk = {c["id"]: c for c in load(DATA, "freight", "chokepoints.json")}
        self.assertIn("not capped at PortWatch's volume here", chk["suez"]["typeNotes"]["dry"]["n"])
        self.assertIn("Red Sea diversions", chk["suez"]["typeNotes"]["dry"]["n"])
        self.assertEqual(chk["suez"]["typeNotes"]["dry"]["regime"], "none")
        self.assertEqual(chk["hormuz"]["typeNotes"]["tanker"]["cmp"], "near")
        for c in chk.values():
            for tn in (c.get("typeNotes") or {}).values():
                self.assertIn("is an estimate made from ship movements", tn["n"])
                self.assertIn("not all the cargo these ships carry", tn["n"])


class G6ClassCargoes(unittest.TestCase):
    def test_every_page_with_a_main_lane_typed_in_a_class_is_among_its_cargoes(self):
        """GV6C.7: the Kamsarmax page had no chip for pulses, rapeseed and soybean meal although their lanes are typed Kamsarmax. A lane is typed
        in the class that comes first in its `vclass` (the typical class: the second one is the class that also serves it)."""
        classes = {c["id"]: c for c in load(ROOT, "pipeline", "freight", "vessel_classes.json")}
        published = {c["id"]: c for c in load(DATA, "freight", "vessel-classes.json")}
        used = {}
        for f in sorted(glob.glob(os.path.join(DATA, "freight", "lanes", "*.json"))):
            for lane in load(f)["lanes"]:
                if lane.get("set") == "main" and lane.get("vclass"):
                    used.setdefault(lane["vclass"][0], set()).add(lane["k"])
        self.assertGreater(len(used), 10)
        for cid, pages in used.items():
            self.assertEqual(sorted(pages - set(classes[cid]["cargoes"])), [], cid)
            self.assertEqual(published[cid]["cargoes"], classes[cid]["cargoes"], cid)
        for k in ("pulses", "rapeseed", "soymeal", "sugar"):
            self.assertIn(k, classes["kamsarmax"]["cargoes"], k)

    def test_a_label_is_for_a_chip_that_is_there(self):
        for c in load(ROOT, "pipeline", "freight", "vessel_classes.json"):
            self.assertLessEqual(set(c.get("cargoLabels", {})), set(c["cargoes"]), c["id"])


class G8SmallFigures(unittest.TestCase):
    def test_the_helpers(self):
        import build_commodities as BC

        self.assertEqual(BC._pct1(0.0001), "<0.1%")
        self.assertEqual(BC._pct1(0.0004), "<0.1%")
        self.assertEqual(BC._pct1(0.0005), "0.1%")
        self.assertEqual(BC._pct1(0.0123), "1.2%")
        self.assertEqual(BC._pct1(0), "0%")
        self.assertEqual(BC._fmts(0.0004, "Mt"), "0.4 kt")  # three significant digits, in the smaller unit under 0.001 Mt
        self.assertEqual(BC._fmts(0.0036, "Mt"), "0.0036 Mt")
        self.assertEqual(BC._fmts(0.004, "kt"), "4 t")
        self.assertEqual((BC._fmts(0.45, "Mt"), BC._fmts(12.34, "Mt"), BC._fmts(1234.5, "Mt")), ("0.45 Mt", "12.3 Mt", "1,234 Mt"))  # the other figures keep their form
        self.assertEqual(BC._fmts(0, "Mt"), "0 Mt")

    def test_no_line_of_a_profile_or_a_page_reads_0_0_percent_or_0_00_mt(self):
        """GV6C.11: France's rice row ("0.0% of the FAOSTAT world total"), Saudi Arabia's lignite ("of which lignite 0.00 Mt (1%)") and the notes of
        the estimated tonnages ("customs declared 0.00 Mt")."""
        bad = re.compile(r"(?<![\d.])0\.0%|(?<![\d.])0\.00 (?:Mt|kt|t)\b")
        found = []
        for sub in (("countries", "profiles"), ("commodities",)):
            for f in sorted(glob.glob(os.path.join(DATA, *sub, "*.json"))):
                text = open(f, encoding="utf-8").read()
                for m in bad.finditer(text):
                    found.append((os.path.basename(f), text[max(0, m.start() - 50):m.end() + 20]))
        self.assertEqual(found[:5], [])

    def test_the_rows_of_the_review(self):
        fra = load(DATA, "countries", "profiles", "FRA.json")
        text = json.dumps(fra, ensure_ascii=False)
        self.assertIn("of the FAOSTAT world total (820 Mt)", text)
        self.assertNotIn("0.0% of the FAOSTAT world total", text)
        sau = json.dumps(load(DATA, "commodities", "thermal-coal.json"), ensure_ascii=False)
        self.assertNotRegex(sau, r"of which lignite 0\.00 Mt")
        self.assertRegex(sau, r"of which lignite [\d.,]+ (?:Mt|kt|t) \(\d+%\)")


USGS = sorted(glob.glob(os.path.join(ROOT, "raw", "usgs", "MCS*_Commodities_Data.csv")))
# the unit of each series of FNCC and FNCD, in the words of the file's row
USGS_LABELS = {
    "usgs-molybdenum-a": "dollars per kilogram", "usgs-chromite-ore-a": "dollars per metric ton", "usgs-ferrochromium-a": "dollars per pound",
    "usgs-heavy-melting-scrap-a": "dollars per metric ton", "usgs-graphite-flake-a": "dollars per metric ton", "usgs-graphite-lump-a": "dollars per metric ton",
    "usgs-graphite-amorphous-a": "dollars per metric ton", "usgs-sulphur-a": "dollars per metric ton", "usgs-ammonia-a": "dollars per short ton",
    "usgs-ferrosilicon-75-a": "cents per pound",
}
UNIT_WORDS = {"dollars per kilogram": "USD/kg", "dollars per metric ton": "USD/t", "dollars per pound": "USD/lb", "dollars per short ton": "USD/short ton",
              "cents per pound": "US cents/lb"}


class G7UsgsLabels(unittest.TestCase):
    def test_the_molybdenum_series_says_what_the_file_says_and_nothing_more(self):
        """GV6C.9: the row says "dollars per kilogram" under a header about molybdenum content and names the oxide; it does not say what the kilogram is of."""
        m = next(x for x in load(DATA, "prices", "index.json") if x["id"] == "usgs-molybdenum-a")
        self.assertNotIn("USD/kg of", m["name"])
        self.assertNotRegex(m["name"], r"molybdic oxide \(57% Mo\)")  # read as "kilogram of oxide"
        self.assertIn("57% molybdenum content", m["name"])
        self.assertEqual(m["unit"], "USD/kg")
        self.assertIn("The file does not say whether the kilogram is of molybdic oxide or of contained molybdenum", m["basis"])
        self.assertIn("Data in metric tons, molybdenum content, unless otherwise specified", m["basis"])
        self.assertIn("U.S. molybdic oxide (MoO3) price, 57% molybdenum content", m["basis"])
        page = " ".join(load(DATA, "commodities", "molybdenum.json")["notes"])
        self.assertIn("the file does not say whether the kilogram is of the oxide or of the molybdenum in it", page)
        with open(os.path.join(ROOT, "web", "src", "lib", "prices.ts"), encoding="utf-8") as f:
            self.assertIn("USGS does not say whether the kilogram is of the oxide or of the molybdenum in it", f.read())
        # no other series claims a basis that its row does not give
        others = [x for x in load(DATA, "prices", "index.json") if x["s"] == "usgs-mcs" and x["id"] != "usgs-molybdenum-a"]
        self.assertTrue(others)
        for x in others:
            self.assertNotIn("does not say", x["basis"], x["id"])

    @unittest.skipUnless(USGS, "raw/ is not tracked in git: the USGS file is not on this machine")
    def test_every_label_against_its_row(self):
        import csv

        with open(USGS[-1], encoding="cp1252", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["Statistics"] == "Price"]
        idx = {x["id"]: x for x in load(DATA, "prices", "index.json")}
        for sid, unit_words in USGS_LABELS.items():
            m = idx[sid]
            mine = [r for r in rows if r["Statistics_detail"].startswith(m["basis"].split(". ")[0].rstrip("."))]
            self.assertTrue(mine, sid)
            self.assertEqual({r["Unit"] for r in mine}, {unit_words}, sid)  # the unit of the label is the unit of the row
            self.assertEqual(UNIT_WORDS[unit_words], m["unit"], sid)
            self.assertEqual({r["Country"] for r in mine}, {"United States"}, sid)  # "US" in the names
            # the basis is the row's own words: its detail and each segment of its notes
            for seg in [n.strip() for n in (mine[0]["Notes"] or "").split(" -- ") if n.strip() and n.strip() != "Estimated."]:
                self.assertIn(seg.rstrip("."), m["basis"], (sid, seg))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def flat(text):
    """A text with its line breaks and indentation as one space: a sentence of the markdown files wraps."""
    return re.sub(r"\s+", " ", text)


class G9Methodology(unittest.TestCase):
    """The numbers that METHODOLOGY writes in a sentence about the groups, the lanes, the routes and the pairs, read from the files."""

    def setUp(self):
        self.text = flat(read("METHODOLOGY.md"))

    def test_the_estimated_rows_are_the_rows_of_the_pairs_files(self):
        rows, mt, sea = [], 0.0, 0.0
        for f in sorted(glob.glob(os.path.join(DATA, "freight", "pairs", "*.json"))):
            d = load(f)
            ix = {c: i for i, c in enumerate(d["cols"])}
            sea += d["seaborne"] / 1e3
            for r in d["rows"]:
                if r[ix["m"]] in (0, 1) and r[ix["f"]] & 1:
                    rows.append((r[ix["kt"]] / 1e3, d["group"], r[ix["o"]], r[ix["d"]]))
                    mt += r[ix["kt"]] / 1e3
        m = re.search(r"In 2024, (\d+) rows and ([\d.]+) Mt of the lane groups \(([\d.]+)% of their ([\d,]+) Mt\) are estimated", self.text)
        self.assertTrue(m, "the sentence of the estimated rows")
        self.assertEqual(int(m.group(1)), len(rows))
        self.assertEqual(m.group(2), f"{mt:.1f}")
        self.assertEqual(m.group(3), f"{100 * mt / sea:.2f}")
        self.assertEqual(int(m.group(4).replace(",", "")), round(sea))
        big = sorted(rows, reverse=True)[:3]
        self.assertEqual([x[1] for x in big], ["crude-oil", "wheat", "copper-ore"])
        for (t, g, o, d), want in zip(big, ("24.5 Mt", "11.1 Mt", "8.24 Mt")):
            self.assertIn(want, self.text)
        # the share of each group's seaborne tonnes that is estimated (`est` of its lane file): the groups the sentence names, and under 1% for the others
        est = {}
        for f in glob.glob(os.path.join(DATA, "freight", "lanes", "*.json")):
            d = load(f)
            est[d["group"]] = 100 * (d.get("est") or 0)
        named = {"copper-ore": "33.0%", "potassium-sulphate": "10.8%", "wheat": "8.0%", "sulphur": "2.0%", "crude-oil": "1.8%", "lpg": "1.3%", "dri": "1.2%"}
        for g, share in named.items():
            self.assertEqual(f"{est[g]:.1f}%", share, g)
            self.assertIn(share, self.text)
        self.assertEqual(sorted(g for g, v in est.items() if v >= 1.0), sorted(named))

    def test_the_counts_of_the_lanes_the_pairs_and_the_modes(self):
        pairs = sorted(glob.glob(os.path.join(DATA, "freight", "pairs", "*.json")))
        n = sum(len(load(f)["rows"]) for f in pairs)
        self.assertIn(f"({len(pairs)} lane groups, {n:,} pairs,", self.text)
        self.assertIn(f"whatever its mode: {n:,} pairs in 2024", self.text)
        main = mixed = hist = 0
        for f in glob.glob(os.path.join(DATA, "freight", "lanes", "*.json")):
            for lane in load(f)["lanes"]:
                if lane.get("set") == "history":
                    hist += 1
                elif lane.get("mode") == "mixed":
                    mixed += 1
                else:
                    main += 1
        self.assertIn(f"2024: {main:,} main seaborne lanes, {mixed} mixed lanes and {hist} history lanes over {len(pairs)} groups", self.text)

    def test_the_routes_by_hand_and_generated(self):
        routes = load(DATA, "freight", "routes.json")
        gen = [r for r in routes if r.get("generated")]
        hand = len(routes) - len(gen)
        # the one count of the hand-written routes, and no other ("103 hand-written routes" contradicted "133" a few lines below)
        self.assertEqual(sorted(set(re.findall(r"(?:The|beside) (\d+) hand-written", self.text))), [str(hand)])
        self.assertNotIn("103 hand-written", self.text)
        qa = flat(read("pipeline", "freight", "QA_routes.md"))
        m = re.search(r"(\d+) generated routes over (\d+) groups, ([\d,]+) Mt of seaborne trade. Named by hand-written routes: ([\d.]+)%. With the generated routes: ([\d.]+)%", qa)
        self.assertTrue(m)
        self.assertEqual(int(m.group(1)), len(gen))
        self.assertIn(f"{hand} hand-written routes name {m.group(4)}% of the {m.group(3)} Mt of 2024 seaborne tonnes of the {m.group(2)} customs groups", self.text)
        self.assertIn(f"{len(gen)} generated routes (122, 20, 10, 10 and 6) over {m.group(2)} groups beside {hand} hand-written ones ({len(routes)} routes), and {m.group(5)}% of the seaborne tonnes named", self.text)

    @unittest.skipUnless(os.system("git -C '%s' cat-file -e 65b007f 2>/dev/null" % ROOT) == 0, "the released commit is not in this checkout")
    def test_the_sixteen_pairs_that_changed_their_passages_with_the_same_ports(self):
        """GV6A.6: sixteen pairs of the released groups changed their list of passages with no change of port or distance, all of sugar with a French end; the three
        Russian pairs of DAP, potash and urea to France changed their port (Fos to Le Havre)."""
        import subprocess

        def rows(d):
            ix = {c: i for i, c in enumerate(d["cols"])}
            ports = [p[0] for p in d["ports"]]
            out = {}
            for r in d["rows"]:
                if r[ix["m"]] in (0, 1):
                    out[(r[ix["o"]], r[ix["d"]])] = (ports[r[ix["load"]]] if r[ix["load"]] >= 0 else None, ports[r[ix["dis"]]] if r[ix["dis"]] >= 0 else None,
                                                     r[ix["nm"]], r[ix["via"]], r[ix["alt"]], d["gates"])
            return out
        same_ports = []
        for f in sorted(glob.glob(os.path.join(DATA, "freight", "pairs", "*.json"))):
            g = os.path.basename(f)[:-5]
            old = subprocess.run(["git", "-C", ROOT, "show", f"65b007f:data/freight/pairs/{g}.json"], capture_output=True, text=True)
            if old.returncode:
                continue  # a group of the later packages
            a, b = rows(json.loads(old.stdout)), rows(load(f))
            for k, o in a.items():
                n = b.get(k)
                if n and o[:3] == n[:3]:
                    names = lambda t: ({x for i, x in enumerate(t[5]) if t[3] >> i & 1}, {x for i, x in enumerate(t[5]) if t[4] >> i & 1} - {x for i, x in enumerate(t[5]) if t[3] >> i & 1})  # noqa: E731
                    if names(o) != names(n):
                        same_ports.append((g, k))
        self.assertEqual(len(same_ports), 16)
        self.assertEqual({g for g, _ in same_ports}, {"sugar"})
        self.assertTrue(all("FRA" in k for _, k in same_ports))
        text = self.text
        self.assertIn("sixteen pairs of sugar", text)
        self.assertIn("the three Russian pairs of DAP, potash and urea to France changed their discharge port from Fos to Le Havre", text)
        for g in ("dap", "potash", "urea"):
            self.assertEqual(rows(load(DATA, "freight", "pairs", g + ".json"))[("RUS", "FRA")][1], "FRLEH")

    def test_section_5_gives_the_figures_of_the_files(self):
        k9 = {(r["chokepoint"], r["type"]): r for r in load(ROOT, "pipeline", "cache", "trade_checks.json")["findings"] if r["check"] == "K9" and r.get("kind") == "passage"}
        gib, bos = k9[("gibraltar", "dry")], k9[("bosphorus", "dry")]
        self.assertEqual(f"{100 * gib['value'] / gib['reference']:.0f}%", "103%")  # 102.7%: the text said 104%
        self.assertIn("at Gibraltar from 85% to 103% (394 against 384 Mt)", self.text)
        self.assertEqual(f"{100 * bos['value'] / bos['reference']:.0f}%", "102%")
        self.assertIn("from 88% of PortWatch's volume (179 against 203 Mt) to 102% (207 against 203 Mt)", self.text)
        self.assertNotIn("Hormuz crude oil \"up to\": 601.4 or 601.7 Mt", self.text)
        chk = {c["id"]: c for c in load(DATA, "freight", "chokepoints.json")}
        hormuz = next(e for e in chk["hormuz"]["estimates"] if e["p"] == "crude-oil")
        self.assertNotIn("capped", hormuz["hi"]["n"])  # the example of the weekly reading is a figure that the reading moves: Lombok iron ore
        self.assertIn("up to 40.1% (751 Mt, not capped", self.text)
        lombok = next(e for e in chk["lombok"]["estimates"] if e["p"] == "iron-ore")
        self.assertEqual(lombok["mt"][1], 950.3)
        self.assertIn('Lombok iron ore "up to": 950.3 Mt from the daily rows, 949.9 Mt from the weekly series', self.text)
        self.assertIn("It binds on four groups of 138 estimates", self.text)
        whole = sum(len(c["estimates"]) for c in chk.values() if any(t["regime"] == "whole" for t in (c.get("typeNotes") or {}).values()))
        self.assertGreater(whole, 100)  # the 138 of the review: the estimates of the types under the whole-volume regime
        size = os.path.getsize(os.path.join(DATA, "freight", "chokepoints.json"))
        self.assertIn(f"was 882,538 bytes and is {size:,}", self.text)
        # FNCI (GV8B.3): "the 18 passages that carry an estimate and a PortWatch counter of their own" were 17 by the builder's own test (`own` of
        # chokepoint_shares: a counter of the passage, not of a part of it); 20 passages carry estimates; Singapore and Cape Horn have no counter
        with_est = [c for c in chk.values() if c.get("estimates")]
        own = [c["id"] for c in with_est if c.get("portwatch") and not c.get("portwatchLabel")]
        self.assertEqual((len(with_est), len(own)), (20, 17))
        self.assertEqual(sorted(c["id"] for c in with_est if c["id"] not in own), ["cape-horn", "danish-straits", "singapore"])
        self.assertTrue(all(not c.get("portwatch") for c in chk.values() if c["id"] in ("singapore", "cape-horn")))
        self.assertIn("Oresund", chk["danish-straits"]["portwatchLabel"])
        self.assertIn(f"For the {len(own)} passages that carry an estimate and a PortWatch counter of their own ({len(with_est)} passages carry estimates; Singapore and Cape Horn have no counter, "
                      "and the counter of the Danish Straits is the Oresund only)", self.text)
        self.assertNotIn("For the 18 passages", self.text)


class G13Prices(unittest.TestCase):
    def test_the_texts_no_longer_deny_the_prices_that_are_published(self):
        meth, recipe = flat(read("METHODOLOGY.md")), flat(read("docs", "ADDING_A_COMMODITY.md"))
        for text in (meth, recipe):
            self.assertNotIn("there is no free series for the other products, sulphur and NPK included", text)
            self.assertNotIn("the ferro-alloys page: ferro-chromium only", text)
            self.assertNotIn("the ferro-alloys page has ferro-chromium only", text)
            self.assertNotIn("coke and the other ferro-alloys have no free price series", text)
        idx = {m["id"]: m for m in load(DATA, "prices", "index.json")}
        # what section 7 says of the three series of FNCD, from the series files
        self.assertEqual((idx["usgs-sulphur-a"]["unit"], idx["usgs-ammonia-a"]["unit"], idx["usgs-ferrosilicon-75-a"]["unit"]), ("USD/t", "USD/short ton", "US cents/lb"))
        self.assertIn("free on board, mine and (or) plant", idx["usgs-sulphur-a"]["basis"])
        self.assertIn("free on board Gulf Coast", idx["usgs-ammonia-a"]["basis"])
        self.assertIn("Green Markets", idx["usgs-ammonia-a"]["basis"])
        self.assertIn("S&P Global Platts Metals Week", idx["usgs-ferrosilicon-75-a"]["basis"])
        for needle in ("elemental sulphur (US dollars per metric ton", "ammonia (US dollars per short ton", "ferrosilicon with 75% silicon (US cents per pound of silicon",
                       'Notes carry the segment "Estimated."', "ferro-chromium and 75% ferrosilicon, no series for the other alloys"):
            self.assertIn(needle, meth)
        self.assertIn("ferro-chromium and 75% ferrosilicon and no series for the other alloys", recipe)
        # a year is marked estimated only where its own Notes say so: 2025 in every USGS series, no other year
        for m in idx.values():
            if m["s"] == "usgs-mcs":
                self.assertEqual(m["est"], [["2025-01", "2025-12"]], m["id"])


class G10Recipe(unittest.TestCase):
    def test_the_recipe_has_the_price_paragraph_and_section_7_and_the_later_rounds(self):
        recipe = flat(read("docs", "ADDING_A_COMMODITY.md"))
        self.assertIn("Pink Sheet series that is already published without a page (`NO_PAGE` of `build_prices.py`", recipe)
        self.assertNotIn("is attached by changing its key in `PINK`", recipe)
        self.assertNotIn("palm kernel oil is there under the key `softs`", recipe)
        self.assertIn("is attached by changing its page key, the second element of its tuple in `PINK`, to the page's id, and deleting its entry of `NO_PAGE`", recipe)
        self.assertIn("(the key of `PINK` itself is the World Bank column name, `\"Palm kernel oil\"`, which the header check reads: leave it)", recipe)
        self.assertIn("7 (prices: a series attached, a unit, a note)", recipe)
        self.assertIn("## 7. What the review rounds after the first three packages added (FNCD to FNCG)", read("docs", "ADDING_A_COMMODITY.md"))
        # the caveat kinds of the recipe are the kinds of the file
        kinds = {v["kind"] for v in load(DATA, "freight", "caveats.json").values()}
        for k in kinds:
            self.assertIn(f"`{k}`", recipe, k)
        for needle in ("`DROP` of `clean.py`", "`LAST_DROPPED`", "river_legs.py", "page names the plant, not the cargo", "`WHOLE_PAGE`", "`KEEP_REPORTED` of `clean.py`", "`typeNotes`", "`coverText`"):
            self.assertIn(needle, recipe, needle)
        import river_legs  # noqa: F401  (the table the recipe names)
        self.assertTrue(hasattr(river_legs, "RIVER_LEGS"))
        import clean as C

        self.assertTrue(hasattr(C, "DROP") and hasattr(C, "KEEP_REPORTED"))
        import caveats as CV

        self.assertTrue(hasattr(CV, "REGISTRY"))
        NO_PAGE = __import__("build_prices").NO_PAGE
        self.assertIn("palm-kernel-oil", NO_PAGE)  # the example of the recipe
        # FNCI (GV8B.2): what the recipe says of the two tables, read from build_prices.py: the key of NO_PAGE is the series' page key and its value the family;
        # the key of PINK is the World Bank column, which the header check reads, and the page key is the second element of the tuple
        BP = __import__("build_prices")
        self.assertEqual(NO_PAGE["palm-kernel-oil"], "softs")
        self.assertEqual(BP.PINK["Palm kernel oil"][1], "palm-kernel-oil")
        self.assertIn("palm-kernel-oil", {v[1] for v in BP.PINK.values()})
        self.assertNotIn("palm-kernel-oil", BP.PINK)  # the key of PINK is not a page key
        self.assertIn("`palm-kernel-oil`", recipe)
        self.assertIn("`softs`", recipe)


if __name__ == "__main__":
    unittest.main()
