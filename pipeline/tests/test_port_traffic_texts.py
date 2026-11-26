"""The words about the port traffic series (METHODOLOGY.md section 5, the registry, NOTICE.md, docs/UPDATING.md, the README and the
About window) against the code and the files they describe. Every count and every figure of request or time in those words is
recomputed here from the files of the repository, the pairing rule, the module and the script, so that the text fails the day one
of them moves; none is typed in the test as a number the text could share.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_port_traffic_texts.py"
With the saved item (a JSON file; without the variable the test does not compare the quotations with the item):
PORTWATCH_DAILY_PORTS_ITEM=<saved item_....json> .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_port_traffic_texts.py"
"""
import json
import os
import re
import sys
import unittest
from datetime import date, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("", "common", "freight", "infrastructure"):
    p = os.path.join(ROOT, "pipeline", sub) if sub else os.path.join(ROOT, "pipeline")
    if p not in sys.path:
        sys.path.insert(0, p)

import fetch_portwatch as FP  # noqa: E402
import extract_wpi as W  # noqa: E402
import fetch_portwatch_port_traffic as S  # noqa: E402
import portwatch_pairs as PP  # noqa: E402
import portwatch_ports as P  # noqa: E402

NEW = "portwatch-port-traffic"
# the sentences of the item "Daily_Ports_Data" that the texts quote, with their source and the date they were read (in the repository)
FIXTURE = os.path.join(ROOT, "pipeline", "tests", "fixtures", "portwatch_daily_ports_data_quotations.json")
# the whole text of the item as it was saved when the design was made (outside the repository: the path of the saved JSON file is the machine's own,
# given in the environment, no default; the fixture is compared with it where it is set)
ITEM = os.environ.get("PORTWATCH_DAILY_PORTS_ITEM")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def flat(text):
    return " ".join(text.split())


def fixture():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def item_text():
    """The text of the saved item, tags removed, on one line; None where the saved file is not on this machine."""
    if not ITEM or not os.path.exists(ITEM):
        return None
    import html
    with open(ITEM, encoding="utf-8") as fh:
        return flat(re.sub(r"<[^>]+>", " ", html.unescape(json.load(fh)["description"])))


def tight(text):
    """The text without the spaces that removing the tags left inside parentheses."""
    return re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", text))


def method_bullet():
    """The "Port traffic" bullet of METHODOLOGY.md section 5, on one line."""
    t = read("METHODOLOGY.md")
    i = t.index('- **Port traffic** (the "Weekly port traffic" block')
    return flat(t[i:t.index("- **Alerts**", i)])


REGISTRY = {s["id"]: s for s in json.loads(read("data", "sources.json"))}
ASSETS = PP.load_assets()
RESULTS = PP.pair_all(ASSETS, PP.load_table())
SUMMARY = PP.summary(RESULTS)


class Pairing(unittest.TestCase):
    """The counts of the paragraph on which ports have a series."""

    def test_the_counts_are_the_counts_of_the_files_and_the_rule(self):
        m = method_bullet()
        reproduced = [x for x in RESULTS if x["outcome"] == "has" and x["gives"] == x["have"]]
        kept = [x for x in RESULTS if x["outcome"] == "has" and x["gives"] != x["have"]]
        r1 = sum(1 for x in reproduced if x["rule"] == "R1")
        r2 = sum(1 for x in reproduced if x["rule"] == "R2")
        self.assertEqual(r1 + r2, len(reproduced))
        self.assertEqual(SUMMARY["assets"], len(ASSETS))
        self.assertEqual(SUMMARY["with_id"], sum(1 for a in ASSETS if a["properties"].get("portwatch")))
        without = SUMMARY["assets"] - SUMMARY["with_id"]
        self.assertEqual(without, SUMMARY["unpaired"] + SUMMARY["none"] + SUMMARY["shared"])
        self.assertEqual(SUMMARY["shared"], 0, "the text says a row serves one asset and names no asset left out for sharing")
        self.assertIn(f"Of the {SUMMARY['assets']} ports, {SUMMARY['with_id']} have an id: the rule reproduces {len(reproduced)} of them "
                      f"({r1} by UN/LOCODE, {r2} by name), and the other {len(kept)} were paired", m)
        self.assertIn(f"Of the {without} without an id, {SUMMARY['unpaired']} have a row near them that the rule cannot pair and "
                      f"{SUMMARY['none']} have no PortWatch port of their country within {PP.MAX_KM:g} km", m)
        self.assertIn(f"at most {PP.MAX_KM:g} km from the port's point", m)

    def test_the_older_pairs_the_rule_does_not_give_stand_at_the_row_they_were_taken_from(self):
        """"each stands at the row's own point (0.0 km)", and the source of the point is the ports table."""
        table = {r["portid"]: r for r in PP.load_table()}
        by_id = {a["properties"]["id"]: a for a in ASSETS}
        kept = [x for x in RESULTS if x["outcome"] == "has" and x["gives"] != x["have"]]
        self.assertTrue(kept)
        for x in kept:
            a = by_id[x["id"]]
            lon, lat = a["geometry"]["coordinates"]
            row = table[x["have"]]
            km = PP.km_between(lat, lon, float(row["lat"]), float(row["lon"]))
            self.assertLess(km, 0.05, x["id"])
            self.assertEqual(a["properties"].get("s"), "portwatch-ports", x["id"])
        self.assertIn("(0.0 km)", method_bullet())

    def test_the_rule_the_text_gives_is_the_rule_of_the_code(self):
        m = method_bullet()
        self.assertEqual(PP.STOP_WORDS, r"\b(port|of|de|terminal|harbor|oil|marine|international)\b")
        self.assertIn("the words port, terminal, harbor, oil, marine, of, de and international are removed", m)
        self.assertIn("a row whose own name has a parenthesis is not offered", m)
        self.assertIn("one PortWatch port serves at most one port of the atlas in this release (a choice made without the owner, listed in `PROGRESS.md`)", m)


class Notes(unittest.TestCase):
    """The four pairings that carry a sentence typed on the asset, and Ras Lanuf as a known limit."""

    def setUp(self):
        self.notes = {a["properties"]["id"]: a["properties"]["portwatchNote"] for a in ASSETS if a["properties"].get("portwatchNote")}

    def test_the_text_names_the_four_ports_that_have_a_note_and_no_other(self):
        m = method_bullet()
        self.assertEqual(sorted(self.notes), ["itaqui", "ras-lanuf", "richards-bay", "rosario-up-river"])
        self.assertIn("four pairings carry a sentence typed on the asset (`portwatchNote` in `ports.geojson`) that claims only what a file gives: Rosario", m)
        self.assertIn("Richards Bay", m)
        self.assertIn("Itaqui", m)

    def test_no_sentence_says_what_portwatchs_port_covers_and_the_text_says_what_each_takes_from_a_file(self):
        """No page read says what PortWatch's boundary of a port covers: a sentence says what the asset's note says and that no page settles the rest."""
        by = {a["properties"]["id"]: a["properties"] for a in ASSETS}
        for pid in ("rosario-up-river", "richards-bay", "itaqui"):
            self.assertIn("No page read says", self.notes[pid], pid)
        for pid, note in self.notes.items():
            self.assertTrue(note.startswith("The series is that of PortWatch's port"), pid)
            self.assertNotRegex(note, r", the (whole|municipal) port\b", pid)
            self.assertLessEqual(len(note), 400, pid)
        # what a sentence takes from the note of its own asset
        self.assertIn("municipal port", by["rosario-up-river"]["note"])
        self.assertIn("far larger", by["rosario-up-river"]["note"])
        self.assertIn("far larger than the municipal port", self.notes["rosario-up-river"])
        self.assertIn("Ponta da Madeira", by["itaqui"]["note"])
        self.assertIn("sits next to", by["itaqui"]["note"])
        self.assertIn("which sits next to the public port this asset describes", self.notes["itaqui"])
        # "the public port" is the wording of the note of the terminal's own asset
        self.assertIn("public port of Itaqui", by["ponta-da-madeira"]["note"])
        self.assertIn("Coal Terminal", by["richards-bay"]["name"])
        # and the paragraph says no more than the sentences do
        m = method_bullet()
        for phrase in ("no page read says which of the two PortWatch's port covers",
                       "no page read says whether PortWatch's port is the terminal or the whole port",
                       "no page read says whether PortWatch's port includes Vale's Ponta da Madeira terminal"):
            self.assertIn(phrase, m)
        self.assertNotIn("PortWatch's port is the municipal port", m)
        self.assertNotIn("PortWatch's port is the whole port", m)

    def test_ras_lanuf_distances_are_the_ones_of_the_note_of_the_asset(self):
        """Typed once on the asset, quoted here: the two distances and the names of the two World Port Index entries."""
        note = self.notes["ras-lanuf"]
        m = method_bullet()
        for km in re.findall(r"(\d+\.\d) km", note):
            self.assertIn(f"{km} km", m)
        self.assertEqual(len(re.findall(r"(\d+\.\d) km", note)), 2)
        for name in ("Al Burayqah", "Ras Lanuf"):
            self.assertIn(f'"{name}"', note)
            self.assertIn(f'"{name}"', m)
        self.assertIn('"Al Burayqah" (also called Marsa Brega)', note)
        self.assertIn('"Al Burayqah" (also called Marsa Brega)', m)
        pair = next(a["properties"]["portwatch"] for a in ASSETS if a["properties"]["id"] == "ras-lanuf")
        row = next(r for r in PP.load_table() if r["portid"] == pair)
        self.assertIn(f'"{row["name"]}"', m)
        self.assertIn(f'The series is that of PortWatch\'s port "{row["name"]}", whose position is', note)
        self.assertNotIn("of this name", note)
        self.assertIn("a later change", m)

    def test_the_fixture_of_the_two_index_entries_names_the_copy_of_the_index_the_atlas_reads(self):
        """The node test recomputes the two distances from this fixture on every machine: its source is the copy the extraction reads."""
        with open(os.path.join(ROOT, "pipeline", "tests", "fixtures", "wpi_ras_lanuf_entries.json"), encoding="utf-8") as fh:
            fx = json.load(fh)
        self.assertEqual(next(iter(fx)), "source")
        for part in (W.CAPTURED, W.CAPTURED_FROM, W.DOWNLOADED, "UpdatedPub150.csv", "World Port Index (Publication 150)"):
            self.assertIn(part, fx["source"])
        self.assertEqual([e["name"] for e in fx["entries"]], ["Al Burayqah", "Ras Lanuf"])
        self.assertEqual(fx["entries"][0]["alternate_name"], "Marsa Brega")

    def test_the_asset_is_still_where_the_text_says_it_is_to_be_moved_from(self):
        """The text says the asset is to be moved in a later change: it is still paired with PortWatch's port of that name."""
        asset = next(a for a in ASSETS if a["properties"]["id"] == "ras-lanuf")
        self.assertTrue(asset["properties"].get("portwatch"))


class SourceLine(unittest.TestCase):
    """The source line of the block says, once for every series, whose boundary a series is, in words the item and the paragraph give."""

    def test_the_clauses_are_those_of_the_item_and_come_in_this_order(self):
        section = flat(read("web", "src", "components", "views", "PortTrafficSection.tsx"))
        clauses = ["weekly sums of daily figures",
                   "a call is a ship entering PortWatch's own boundary of the port, which is not always this asset's (PortWatch leaves out calls with a turnaround time of less than 5 hours and no change of draught between this port and the next)",
                   "tonnes are PortWatch's estimates from each ship's size and draught, not a port statistic",
                   "ships are counted from their AIS signals: PortWatch notes that"]
        at = [section.index(c) for c in clauses]
        self.assertEqual(at, sorted(at))
        # "a call is a ship entering ... the port boundary" is the item's sentence; "not always this asset's" is the atlas's caution, which the paragraph gives
        m = method_bullet()
        self.assertIn("a port call is defined when a ship enters the port boundary", m)
        self.assertIn("so every series is that of PortWatch's own boundary of the port, which the source line of the block says is not always the asset's", m)
        self.assertIn("The rule is a test of plausibility, not a proof that the PortWatch port and the asset have the same boundary", m)


class Requests(unittest.TestCase):
    """The figures of request, time and size of the paragraph, from the module and the script."""

    def test_the_weeks_the_quarter_and_the_sitting(self):
        m = method_bullet()
        self.assertIn(f"reads again the last {P.WINDOW_WEEKS} weeks of every port that has a file", m)
        self.assertEqual(P.QUARTERS, 4)
        self.assertIn(f"the last {P.DEEP_WEEKS} weeks, so that every port is re-read over a year once every four weeks", m)
        self.assertIn("for a quarter of the ports in turn", m)
        self.assertIn(f"sittings of at most {P.SITTING_MAX} ports ({P.SITTING_MAX * P.pages((date(2026, 11, 25) - date.fromisoformat(P.HISTORY_FROM)).days + 1)} requests)", m)
        self.assertIn(f"fills in at most {P.SCHEDULED_BACKFILL_CAP} ports a run", m)
        self.assertIn(f"three requests while the table holds under {3 * P.PAGE:,} days of it", m)
        self.assertEqual(P.pages(3 * P.PAGE - 1), 3)

    def test_the_requests_of_a_weekly_run_and_the_pace(self):
        m = method_bullet()
        n = len(P.port_ids())
        today = date(2026, 11, 25)
        bounds = [P.weekly_request_bounds(n, today + timedelta(weeks=w), S.MAX_REQUESTS) for w in range(4)]
        least, most = min(b[0] for b in bounds), max(b[1] for b in bounds)
        self.assertEqual(least, most, "the paragraph says one figure for a normal week: change the text with the code")
        self.assertIn(f"A normal weekly run asks for {least} requests and never more than {S.MAX_REQUESTS}", m)
        self.assertIn("not counting a request repeated after an error", m)
        self.assertIn("also waits one such pause before its first request, because the chokepoint step before it asks the same host", m)
        lo, hi = FP.PAUSE_S
        self.assertIn(f"with a pause of {lo:g} to {hi:g} seconds before the next", m)
        self.assertIn(f"never more than the {S.RUN_LIMIT_S // 60} minutes after which the script stops asking", m)
        self.assertLessEqual(S.MAX_REQUESTS * (hi + S.REQUEST_S), S.RUN_LIMIT_S)
        # the pace is the chokepoint script's, imported: one place
        self.assertIs(S.PAUSE_S, FP.PAUSE_S)

    def test_the_owners_words_are_the_ones_the_notice_and_the_progress_file_record(self):
        m = method_bullet()
        words = "behave like a human, download little by little, move slowly on the page, one request at a time, and we will mention them"
        self.assertIn(f'"{words}"', m)
        self.assertIn("the seconds are the script's reading of \"slowly\", not the owner's figure", m)
        notice = flat(read("NOTICE.md"))
        self.assertIn("The owner's decision of 25 November 2026: the atlas keeps reading PortWatch as a person would, in small pieces, one request at a time and slowly", notice)

    def test_the_rounding_the_text_gives_is_the_rounding_of_the_module(self):
        m = method_bullet()
        self.assertIn("three significant figures at least and never finer than a tonne", m)
        # a value of 100 t or more is rounded by at most 0.5% of itself, whatever its size
        for t in list(range(100, 3000)) + [9_995, 10_049, 99_949, 99_950, 100_499, 1_234_567, 98_765_432]:
            self.assertLessEqual(abs(P.round_tonnes(t) - t) / t, 0.005 + 1e-12, t)
        for t in range(0, 100):
            self.assertLessEqual(abs(P.round_tonnes(t) - t), 0.5, t)
        self.assertIn("a value of 100 t or more is rounded by at most 0.5% of itself, a smaller one by at most half a tonne", m)
        self.assertIn("flags a port where it is over 0.5%", m)
        self.assertIn("ROUNDING OVER 0.5%", read("pipeline", "freight", "fetch_portwatch_port_traffic.py"))
        self.assertEqual((P.UNIT, P.MAX_DECIMALS), ("kt", 3))
        self.assertIn("Tonnes are stored in thousand tonnes", m)

    def test_a_deep_pass_that_finds_much_changed_is_refused_as_the_text_says(self):
        m = method_bullet()
        self.assertIn("more than a tenth of the ports changed by more than a quarter", m)
        self.assertEqual((P.REVISED_PORTS, P.REVISED_SHARE), (0.1, 0.25))
        self.assertIn('"history revised"', m)
        self.assertIn("history revised", read("pipeline", "freight", "fetch_portwatch_port_traffic.py") + read("pipeline", "freight", "portwatch_ports.py"))


class Quotes(unittest.TestCase):
    """What PortWatch says its figures are: quoted from the item's text, word for word."""

    def test_the_fixture_says_what_it_is_and_where_its_sentences_were_read(self):
        fx = fixture()
        self.assertEqual(next(iter(fx)), "about", "the first field says what the file holds")
        self.assertIn("Quotations of a few sentences, with their source", fx["about"])
        self.assertIn("Nothing else of the item is copied", fx["about"])
        self.assertEqual(fx["item"], f"https://www.arcgis.com/sharing/rest/content/items/{fx['item_id']}?f=json")
        self.assertRegex(fx["read"], r"^2026-11-25$")
        self.assertIn(fx["item_id"], REGISTRY[NEW]["access"])
        self.assertEqual(sorted(fx["quotations"]), ["manual_entry", "port_call", "trade_estimates", "transponder", "transponder_cargo", "transponder_limited"])
        self.assertIn(f"the item's recommended citation is \"{fx['recommended_citation'].rstrip('.')}\"", REGISTRY[NEW]["licence"])

    def test_every_sentence_in_quotation_marks_that_comes_from_the_item_is_a_sentence_of_the_fixture(self):
        """On every machine: the sentences the paragraph quotes from the item are those of the fixture, and the fixture holds no other."""
        m = method_bullet()
        quotations = list(fixture()["quotations"].values())
        quoted = [q for q in re.findall(r'"([^"]{40,})"', m) if "behave like a human" not in q]
        self.assertGreaterEqual(len(quoted), 3)
        from_item = [q for q in quoted if (q.startswith("a port call is defined") or q.startswith("we use the vessel information")
                                           or "entered manually" in q or "turn off their AIS transponder" in q
                                           or q.startswith("mostly limited to") or q.startswith("not common for container"))]
        self.assertEqual(len(from_item), len(quotations))
        for q in from_item:
            self.assertIn(q.rstrip("."), [x.rstrip(".") for x in quotations], q)
        for x in quotations:
            self.assertIn(x, m, "a sentence of the fixture that the paragraph does not quote")

    def test_the_fixture_is_the_text_of_the_saved_item_where_that_file_exists(self):
        text = item_text()
        if text is None:
            self.skipTest("PORTWATCH_DAILY_PORTS_ITEM does not name the saved item")
        fx = fixture()
        for key, x in fx["quotations"].items():
            self.assertIn(x.rstrip("."), text, key)
        self.assertIn(fx["recommended_citation"], tight(text))

    def test_the_quotes_are_in_the_paragraph(self):
        m = method_bullet()
        for q in fixture()["quotations"].values():
            self.assertIn(q, m)

    def test_the_block_prints_the_warning_of_portwatch_on_ships_that_send_no_signal_and_its_bound(self):
        """A port where ships switch their transponder off reads low in PortWatch: the block says so in PortWatch's own words, with the
        bound PortWatch puts on it, under every series; and METHODOLOGY gives the two halves, and the bound's other sentence."""
        q = "ships can turn off their AIS transponder to avoid being detected"
        cargo = "not common for container and other cargo ships"
        section = flat(read("web", "src", "components", "views", "PortTrafficSection.tsx"))
        self.assertIn(f'PortWatch notes that "{q}" and calls it "{cargo}" entering a port', section)
        m = method_bullet()
        limited = fixture()["quotations"]["transponder_limited"]
        self.assertIn(q, m)
        self.assertIn(f'it says that this is "{limited}" and "{cargo}" entering a port', m)
        self.assertEqual(q, fixture()["quotations"]["transponder"])
        self.assertEqual(cargo, fixture()["quotations"]["transponder_cargo"])
        if item_text() is not None:
            for x in (q, limited, cargo):
                self.assertIn(x, item_text())
            # the quotation of the block stops before the parenthesis that follows it in the item
            self.assertIn(f"It is {cargo} (which is the focus of our study) entering a country\u2019s port", item_text())

    def test_the_block_says_the_short_calls_are_left_out_as_the_item_does(self):
        """The source line says in its own words what the quotation of the paragraph says, and no less: a turnaround time of less than 5 hours
        and no change of draught between the port and the next one."""
        fixture_text = fixture()["quotations"]["port_call"]
        self.assertIn("Port calls with a turnaround time of less than 5 hours and no draft change between the current and next port are excluded", fixture_text)
        self.assertIn("(PortWatch leaves out calls with a turnaround time of less than 5 hours and no change of draught between this port and the next)",
                      flat(read("web", "src", "components", "views", "PortTrafficSection.tsx")))
        self.assertIn("and the exclusion of short calls, under every series", method_bullet())


class ReleaseNote(unittest.TestCase):
    def test_the_release_note_says_what_the_atlas_cannot_say_and_its_figure_is_the_one_of_the_file(self):
        """The note gives the calls of the last 52 weeks of the port paired with the asset `odesa`, read from its file, and claims no cause."""
        note = flat(read("CHANGELOG.md"))
        i = note.index("## Release 9")
        entry = note[i:note.index("## Release 8", i)]
        pair = next(a["properties"]["portwatch"] for a in ASSETS if a["properties"]["id"] == "odesa")
        with open(os.path.join(P.OUT, f"{pair}.json"), encoding="utf-8") as fh:
            calls = json.load(fh)["calls"]
        in_a_year = sum(v or 0 for series in calls.values() for v in series[-P.DEEP_WEEKS:])
        self.assertIn(f"some series read very low ({in_a_year} calls in a year at Odesa), and the atlas cannot say why", entry)
        self.assertIn("prints PortWatch's own warning that ships can switch their transponder off", entry)
        self.assertNotIn("real traffic", entry)


class WhatIsNotSaid(unittest.TestCase):
    def test_no_text_about_the_port_series_calls_the_data_free_or_the_tonnes_the_atlas_own(self):
        texts = {"METHODOLOGY bullet": method_bullet(), "registry": json.dumps(REGISTRY[NEW]), "NOTICE.md": flat(read("NOTICE.md"))[
            flat(read("NOTICE.md")).index("Port traffic. For the ports of the infrastructure layer"):flat(read("NOTICE.md")).index("Ports database. The ports")]}
        for where, t in texts.items():
            self.assertIsNone(re.search(r"public domain|open licen[cs]e|free to reuse|\bCC BY\b", t, re.I), where)
        m = method_bullet()
        # "Atlas estimate" appears once, as the label the block never puts on the tonnes
        self.assertEqual(m.count("Atlas estimate"), 1)
        self.assertIn('never labels them "Atlas estimate"', m)
        self.assertNotIn("live", re.sub(r"deliver|alive|believe|olive", "", m))

    def test_the_paragraph_says_what_is_not_read_and_what_is_not_kept(self):
        m = method_bullet()
        self.assertIn("no ship name or number, no position or track, no time finer than a day and no signal is read, stored or shown", m)
        self.assertIn("no daily row is kept in the repository, in a cache or as a workflow artifact", m)
        # and the code agrees: the files of the folder hold weekly sums and nothing daily
        self.assertEqual(P.KEYS, ("id", "name", "s", "y", "start", "step", "u", "dp", "calls", "exports", "imports"))
        self.assertIn("No daily row is kept in the repository, in a cache or as a workflow artifact", REGISTRY[NEW]["access"])

    def test_the_owner_is_not_said_to_have_decided_what_he_was_not_asked(self):
        m = method_bullet()
        self.assertNotIn("the owner decided", m)
        self.assertNotIn("the owner accepted", m)
        self.assertEqual(m.count("a choice made without the owner, listed in `PROGRESS.md`"), 1)

    def test_the_source_id_of_the_weekly_sums_is_the_one_the_licence_section_says(self):
        t = flat(read("METHODOLOGY.md"))
        self.assertIn("keep the source id `portwatch-port-traffic`, as the chokepoint weekly averages keep `portwatch`, not `atlas`", t)
        self.assertEqual(P.SOURCE, NEW)
        for f in os.listdir(P.OUT):
            if f.startswith("port") and f.endswith(".json"):
                self.assertEqual(json.load(open(os.path.join(P.OUT, f)))["s"], NEW, f)
                break


class Registry(unittest.TestCase):
    def test_the_link_of_the_series_opens_the_portwatch_site_and_the_item_stays_in_the_access_text(self):
        s = REGISTRY[NEW]
        self.assertEqual(s["url"], "https://portwatch.imf.org/")
        self.assertEqual(s["url"], REGISTRY["portwatch"]["url"])
        self.assertIn("item 83b1bbc7b3354c5fb1f40673bb8f852e", s["access"])
        self.assertIn("https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer", s["access"])
        self.assertNotIn("?f=json", s["url"])

    def test_the_credit_the_about_window_prints_is_the_one_the_registry_gives(self):
        lic = REGISTRY[NEW]["licence"]
        credit = re.search(r"Credit: (.+)$", lic, re.S).group(1)
        self.assertIn("IMF PortWatch (IMF and University of Oxford), data adapted", credit)
        self.assertIn('"Sources: UN Global Platform; IMF PortWatch (portwatch.imf.org)"', credit)
        about = flat(read("web", "src", "components", "AboutDialog.tsx"))
        self.assertIn("const credit = (id: string) => /Credit: (.+)$/s.exec(lic(id) ?? '')?.[1];", about)
        self.assertIn("<b>Port traffic.</b> The daily port table of IMF PortWatch,", about)
        self.assertIn("credit('portwatch-port-traffic')", about)
        # the sentence about the weekly sums says what the registry's use says, and the tonnes are PortWatch's
        for text in ("added into weeks (Monday to Sunday, complete weeks only)", "the ship types added by the atlas", "the tonnes rounded",
                     "The tonnes are PortWatch's estimates", "no daily figure, vessel or position is kept"):
            self.assertIn(text, about)
        self.assertNotIn("Atlas estimate", about[about.index("<b>Port traffic.</b>"):about.index("<b>Wikipedia.</b>")])
        for text in ("Monday to Sunday", "complete weeks only", "by ship type"):
            self.assertIn(text, REGISTRY[NEW]["use"])

    def test_the_freshness_tab_names_the_series_with_the_weekly_jobs(self):
        about = flat(read("web", "src", "components", "AboutDialog.tsx"))
        self.assertIn("prices, chokepoint traffic and port traffic every week", about)
        fresh = read("web", "src", "components", "AboutFresh.tsx")
        self.assertIn("{ name: 'Port traffic', keys: ['portwatch-port-traffic'] },", fresh)
        status = read("web", "src", "lib", "status.ts")
        self.assertIn("{ key: 'portwatch-port-traffic', sources: ['portwatch-port-traffic'], kind: 'day', maxAge: WEEKLY },", status)
        # the label the family sentence prints for the source
        self.assertIn("'portwatch-port-traffic': 'IMF PortWatch'", read("web", "src", "components", "ui.tsx"))

    def test_the_publication_calendar_says_what_both_sides_do(self):
        """"Published" is the publisher's rhythm and "Read by" is the atlas's job: the registry says so on both sides."""
        s = REGISTRY[NEW]
        self.assertEqual(s["update"], "daily rows; rhythm not stated by the publisher; read weekly by the atlas")
        import changes as C
        self.assertIn(NEW, C.JOBS["update-portwatch"])

    def test_the_status_entry_is_the_first_scheduled_runs_to_write(self):
        guide = flat(read("docs", "UPDATING.md"))
        self.assertIn("The first scheduled run of the step is the one that writes the status entry of the source into `data/_status/updates.json`", guide)
        # and the tree before that run holds none (a sitting by hand leaves its entry out of the commits)
        status = json.loads(read("data", "_status", "updates.json"))
        if NEW in status.get("sources", {}):
            self.skipTest("the first scheduled run has written the entry")


class Documents(unittest.TestCase):
    def test_the_sentences_that_the_series_was_not_shown_are_gone_everywhere(self):
        for name in ("NOTICE.md", "docs/UPDATING.md", "README.md", "DATA_SOURCES.md", "METHODOLOGY.md", "data/sources.json",
                     "pipeline/infrastructure/README.md"):
            t = flat(read(*name.split("/")))
            for gone in ("no page of the site shows the series yet", "no page of the site shows them yet", "no page offers it yet",
                         "will be offered as the CSV", "The weekly step is not in place", "no scheduled job runs the script",
                         "no scheduled job reads this table yet"):
                self.assertNotIn(gone, t, name)

    def test_the_weekly_step_is_named_where_the_workflows_are_listed(self):
        wf = read(".github", "workflows", "update-portwatch.yml")
        self.assertIn("fetch_portwatch_port_traffic.py", wf)
        readme = flat(read("README.md"))
        self.assertIn("A second step of the same job reads the recent weeks of the daily port table", readme)
        sources = flat(read("DATA_SOURCES.md"))
        self.assertIn("then, as a second step of the same job, the weekly port traffic", sources)
        self.assertIn("`data/freight/port-traffic/`", sources)

    def test_the_docstring_of_the_ports_database_script_points_to_the_script_of_the_traffic(self):
        doc = flat(read("pipeline", "infrastructure", "fetch_portwatch_ports.py").split('"""')[1])
        self.assertIn("The traffic of a port comes from another table, the daily one, read by pipeline/freight/fetch_portwatch_port_traffic.py", doc)
        self.assertIn("Only the identity and the position of each port are kept: no vessel count and no traffic figure.", doc)
        self.assertTrue(os.path.exists(os.path.join(ROOT, "pipeline", "freight", "fetch_portwatch_port_traffic.py")))
        self.assertTrue(os.path.exists(os.path.join(ROOT, "pipeline", "infrastructure", "portwatch_pairs.py")))

    def test_the_section_the_text_describes_exists_with_the_words_it_quotes(self):
        section = read("web", "src", "components", "views", "PortTrafficSection.tsx")
        for text in ("const TITLE = 'Weekly port traffic';", "Exports (est.)", "Imports (est.)", "kt/week, estimate",
                     "PortWatch port: {doc.name}", "'Calls'", "Exports", "Imports"):
            self.assertIn(text, section)
        t = read("web", "src", "lib", "portTraffic.ts")
        self.assertIn("YEAR_WEEKS = 52", t)

    def test_the_methodology_section_is_where_the_other_texts_point(self):
        self.assertIn('section 5, "Port traffic"', flat(read("docs", "UPDATING.md")))
        t = read("METHODOLOGY.md")
        self.assertIn("## 5. Shares", t)
        self.assertLess(t.index("## 5. Shares"), t.index('- **Port traffic** (the "Weekly port traffic" block'))
        self.assertLess(t.index('- **Port traffic** (the "Weekly port traffic" block'), t.index("## 6. Country profiles"))
        self.assertIn("the port traffic\nof a port's page comes from the daily table, section 5", t)


if __name__ == "__main__":
    unittest.main()
