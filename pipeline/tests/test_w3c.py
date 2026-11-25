"""Tests of the small points left by the last review of the sixth release.

C2  no hint text under the monthly producers table of the crude oil page
C3  a lane whose principal port comes from a coast rule says so (lane file flag `portRule`, lane page sentence)
C4  the key figure of an annual price carries its year in its source line
C5  the price board says what it leaves out, counted from the index
C6  a passage page lists IMF PortWatch as its source only when it shows a PortWatch counter

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The tests of the data files read the files as the builders last wrote them.
"""
import glob
import json
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "freight"))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def load(*parts):
    return json.loads(read(*parts))


class C2NoHintText(unittest.TestCase):
    def test_the_producers_table_of_the_crude_oil_page_has_no_instruction(self):
        src = read("web", "src", "components", "EnergyMonthly.tsx")
        self.assertNotIn("Click a producer", src)
        self.assertIn("Latest month of each producer against its", src)  # the note stays: it says what the table is
        self.assertIn("<LatestTable", src)


class C3PortsChosenByARule(unittest.TestCase):
    def lanes(self):
        for f in sorted(glob.glob(os.path.join(ROOT, "data", "freight", "lanes", "*.json"))):
            with open(f, encoding="utf-8") as fh:
                doc = json.load(fh)
            for lane in doc["lanes"]:
                yield doc["group"], lane

    def test_the_flag_is_on_the_open_lanes_whose_principal_port_a_coast_rule_chose_and_on_no_other(self):
        import ports as P
        n = 0
        for group, lane in self.lanes():
            rule = bool(P.assign(lane["o"], lane["d"], group).rule) if lane.get("portBasis") == "open" else False
            self.assertEqual(lane.get("portRule", False), rule, lane["id"])
            n += rule
        self.assertGreater(n, 100)

    def test_methodology_counts_the_flagged_lanes(self):
        n = sum(1 for _, lane in self.lanes() if lane.get("portRule"))
        self.assertIn(f"(`portRule` in the lane file: {n} lanes)", " ".join(read("METHODOLOGY.md").split()))

    def test_the_two_lanes_of_the_review(self):
        wheat = {x["id"]: x for x in load("data", "freight", "lanes", "wheat.json")["lanes"]}["wheat:FRA-NLD"]
        scrap = {x["id"]: x for x in load("data", "freight", "lanes", "ferrous-scrap.json")["lanes"]}["ferrous-scrap:USA-TUR"]
        for lane in (wheat, scrap):
            self.assertEqual((lane["portBasis"], lane.get("portRule")), ("open", True), lane["id"])

    def test_the_lane_page_says_so_in_the_sentence_that_says_no_source_gives_the_split(self):
        src = read("web", "src", "components", "views", "LaneView.tsx")
        self.assertIn("No source says how this trade splits between ports: the first of each is the principal gateway, drawn on the map", src)
        self.assertIn("lane.portRule ? ', chosen by a coast rule of the atlas' : ''", src)


class C4AnnualPriceYear(unittest.TestCase):
    def test_the_source_line_of_an_annual_key_figure_has_the_year_of_the_series(self):
        src = read("web", "src", "components", "PriceFigure.tsx")
        self.assertIn("{shortSource(m.s)} · {when} · calendar-year average", src)
        self.assertIn("const when = annual ? st.last.t.slice(0, 4) : fmtDate(st.last.t);", src)  # `when`: the last period of the series itself


class C5BoardLine(unittest.TestCase):
    def test_the_board_counts_from_the_index_what_it_leaves_out(self):
        src = read("web", "src", "components", "PriceBoard.tsx")
        self.assertIn("idx.filter((m) => !m.hidden && m.stats && (m.closed || m.freq === 'A')).length", src)
        self.assertIn("annual series and series their publisher stopped are not listed here", src)

    def test_the_two_counts_cover_the_index(self):
        idx = load("data", "prices", "index.json")
        listed = [m for m in idx if not m.get("hidden") and not m.get("closed") and m.get("stats") and m["freq"] != "A"]
        apart = [m for m in idx if not m.get("hidden") and m.get("stats") and (m.get("closed") or m["freq"] == "A")]
        shown = [m for m in idx if not m.get("hidden") and m.get("stats")]
        self.assertEqual(len(listed) + len(apart), len(shown))
        self.assertGreaterEqual(len(apart), 16)  # the sixteen series of the sixth release, and the annual series before them


class C6PassageSource(unittest.TestCase):
    def test_a_passage_credits_portwatch_only_with_a_counter_of_its_own_or_a_borrowed_one(self):
        for where in (("pipeline", "freight", "chokepoints.json"), ("data", "freight", "chokepoints.json")):
            for c in load(*where):
                if c.get("s") == "portwatch":
                    self.assertTrue(c.get("portwatch") or c.get("seriesFrom"), (where[0], c["id"]))

    def test_singapore_shows_no_portwatch_figure_and_names_no_portwatch_source(self):
        c = {x["id"]: x for x in load("data", "freight", "chokepoints.json")}["singapore"]
        self.assertFalse(c.get("portwatch") or c.get("seriesFrom"))
        self.assertEqual(c["s"], "atlas")
        # nothing of the passage's estimates rests on a PortWatch volume (the cap would bring the source back, in the estimates' own line)
        self.assertFalse([e["k"] for e in c["estimates"] if re.search(r"capped", (e.get("hi") or {}).get("n", ""))])
        self.assertFalse(c.get("typeNotes"))


if __name__ == "__main__":
    unittest.main()
