"""The notice about the map's boundaries (About window, README, METHODOLOGY.md) and the words around it, tied to each other and to the files.

The About window's list item "Boundaries and names" is the one place the notice is written; the README paragraph and the METHODOLOGY.md
section "The map: boundaries and territories" must carry it character for character once the JSX tags are removed and all white space is
collapsed to one space. The version it names is the one of the registry entry `naturalearth`; the two sentences of Natural Earth that the
section quotes are kept, with their address, in fixtures/naturalearth_boundaries_quotations.json. Nothing here needs raw/: the tests that
compare with the version file of raw/ or with the saved pages of the day they were read skip when those files are absent (GitHub's machines).
The class Table keeps the table of the section (what the country shapes of the map do with the points of Natural Earth's disputed areas) in line with
the shapes the site serves, with fixtures/border_probes.json and with the customs codes; it reads no polygon of the disputed areas.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_borders.py"
"""
import ast
import csv
import html
import json
import math
import os
import re
import struct
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIXTURE = os.path.join(ROOT, "pipeline", "tests", "fixtures", "naturalearth_boundaries_quotations.json")
VERSION_FILE = os.path.join(ROOT, "raw", "naturalearth", "ne_50m", "ne_50m_admin_0_countries.VERSION.txt")
SAVED_PAGES = {
    "https://www.naturalearthdata.com/downloads/50m-cultural-vectors/": "/tmp/claude-0/audit/work/7A/BORD/dl/ne_50m_cultural.html",
    "https://www.naturalearthdata.com/downloads/50m-cultural-vectors/50m-admin-0-countries-2/":
        "/tmp/claude-0/audit/work/7A/BORD/dl/ne_50m_countries_about.html",
}
TITLE = "The map: boundaries and territories"
READ = "read 25 November 2026"
VERSION = r"\d+\.\d+\.\d+"
HINT_WORDS = ("click", "hover", "tap", "drag", "choose", "select", "press")
OLD_SENTENCES = ("imply any opinion", "Boundaries and names on the map come from")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def load(*parts):
    return json.loads(read(*parts))


def flat(text):
    return " ".join(text.split())


def jsx_text(source):
    """The text of a piece of JSX: tags removed, the apostrophe forms resolved, white space collapsed."""
    source = source.replace("&apos;", "'").replace("&#39;", "'").replace('{"\'"}', "'").replace("{'\\''}", "'").replace("{' '}", " ")
    return flat(html.unescape(re.sub(r"<[^>]+>", " ", source)).replace(" ,", ",").replace(" .", "."))


def about_item(lead, end="</li>"):
    """The list item of AboutDialog.tsx that starts with `lead` (inside its <li>), up to its closing tag."""
    src = read("web", "src", "components", "AboutDialog.tsx")
    i = src.index(lead)
    li = src.rindex("<li>", 0, i)
    return src[li + len("<li>"):src.index(end, i)]


def about_notice():
    item = about_item("<b>Boundaries and names.</b>")
    return jsx_text(item.replace("<b>Boundaries and names.</b>", "", 1))


def known_limits_bullet():
    return jsx_text(about_item("The map follows Natural Earth's default boundaries;"))


def section(text, title=TITLE):
    """The lines of METHODOLOGY.md from the heading `## <n>. <title>` to the next `## ` heading or the end."""
    m = re.search(r"^## \d+\. " + re.escape(title) + r"$", text, re.M)
    assert m, f"no section {title!r}"
    nxt = re.search(r"^## ", text[m.end():], re.M)
    return text[m.start():m.end() + nxt.start()] if nxt else text[m.start():]


def paragraphs(text):
    return [flat(p) for p in re.split(r"\n\s*\n", text) if p.strip()]


def readme_paragraph():
    disclaimer = read("README.md").split("\n## Disclaimer", 1)[1]
    found = [p for p in paragraphs(disclaimer) if p.startswith("Country shapes are Natural Earth's default view")]
    assert len(found) == 1, found
    return found[0]


class Notice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notice = about_notice()
        cls.methodology = read("METHODOLOGY.md")

    def test_the_notice_of_the_about_window_is_found_as_it_is_in_the_readme_paragraph(self):
        self.assertTrue(self.notice.startswith("Country shapes are Natural Earth's default view (version "), self.notice)
        # the paragraph is the notice and the line that says where else the text is
        self.assertEqual(readme_paragraph(), self.notice + " The same text is in the About window of the site.")

    def test_the_notice_is_a_paragraph_of_its_own_in_the_methodology_section(self):
        self.assertIn(self.notice, paragraphs(section(self.methodology)))

    def test_the_old_sentences_are_gone_from_the_documents_and_the_page(self):
        for name in ("README.md", "METHODOLOGY.md", "NOTICE.md", "DATA_SOURCES.md"):
            text = flat(read(*name.split("/")))
            for old in OLD_SENTENCES:
                self.assertNotIn(old, text, name)
        about = flat(read("web", "src", "components", "AboutDialog.tsx"))
        for old in OLD_SENTENCES:
            self.assertNotIn(old, about)

    def test_the_notice_holds_no_digit_but_its_version_and_names_no_body_nor_a_licence(self):
        self.assertEqual(len(re.findall(VERSION, self.notice)), 1)
        self.assertFalse(re.search(r"\d", re.sub(VERSION, "", self.notice)), self.notice)
        low = self.notice.lower()
        for word in ("united nations", "public domain", "open licence", "open license", "free to reuse"):
            self.assertNotIn(word, low)

    def test_the_notice_says_what_natural_earth_does_not_do_and_what_the_atlas_does_not(self):
        for part in ("does not apply one rule to every disputed or self-administered territory",
                     "draws some as shapes of their own and keeps others inside the country that claims them",
                     "do not imply official endorsement or acceptance",
                     "the atlas takes no position on the status of any territory"):
            self.assertIn(part, self.notice)


class HintWords(unittest.TestCase):
    """The strings added to web/src tell the visitor nothing to do (the registry's text and the documents are not scanned)."""

    def test_the_about_item_and_the_known_limits_bullet_hold_no_instruction_word(self):
        for label, text in (("Boundaries and names", about_notice()), ("Known limits", known_limits_bullet())):
            for word in HINT_WORDS:
                self.assertIsNone(re.search(r"\b" + word + r"\b", text, re.I), f"{label}: {word}")


class Version(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        registry = {s["id"]: s for s in load("data", "sources.json")}
        cls.entry = registry["naturalearth"]
        cls.registry_version = re.search(r"\(version (" + VERSION + r")\)", cls.entry["access"]).group(1)

    def test_the_notice_the_notice_sentence_the_methodology_and_the_registry_agree(self):
        self.assertEqual(re.search(r"\(version (" + VERSION + r")\)", about_notice()).group(1), self.registry_version)
        notice_md = flat(read("NOTICE.md"))
        sentence = re.search(r"The country shapes are the default view of version (" + VERSION + r");", notice_md)
        self.assertIsNotNone(sentence, "the sentence at the end of the Natural Earth bullet of NOTICE.md")
        self.assertEqual(sentence.group(1), self.registry_version)
        text = flat(section(read("METHODOLOGY.md")))
        versions = set(re.findall(r"version (" + VERSION + r")", text))
        self.assertEqual(versions, {self.registry_version})
        self.assertIn("`ne_50m_admin_0_countries`, version " + self.registry_version, text)
        self.assertEqual(set(re.findall(r"version (" + VERSION + r")", flat(readme_paragraph()))), {self.registry_version})

    def test_the_version_file_of_the_download_reads_the_same_where_it_exists(self):
        if not os.path.exists(VERSION_FILE):
            self.skipTest("raw/naturalearth/ne_50m is not on this machine")
        with open(VERSION_FILE, encoding="utf-8") as fh:
            self.assertEqual(fh.read().strip(), self.registry_version)


class Quotations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load("pipeline", "tests", "fixtures", "naturalearth_boundaries_quotations.json")
        cls.section = flat(section(read("METHODOLOGY.md")))

    def test_the_fixture_says_what_it_is_and_when_the_pages_were_read(self):
        self.assertTrue(self.fixture["about"].startswith("Quotations of two sentences, with their page address"))
        self.assertEqual(self.fixture["read"], "2026-11-25")
        self.assertEqual(READ, "read 25 November 2026")
        keys = [q["key"] for q in self.fixture["quotations"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(keys), 2)
        for q in self.fixture["quotations"]:
            self.assertRegex(q["address"], r"^https://www\.naturalearthdata\.com/", q["key"])
            self.assertEqual(q["read"], "2026-11-25")
            self.assertEqual(q["quotation"], flat(q["quotation"]), f"{q['key']}: spacing is normalised")

    def test_each_sentence_is_in_the_section_word_for_word_next_to_its_address_and_the_day(self):
        for q in self.fixture["quotations"]:
            self.assertIn('"' + q["quotation"] + '"', self.section, q["key"])
            i = self.section.index('"' + q["quotation"] + '"')
            near = self.section[i:i + len(q["quotation"]) + 260]
            self.assertIn(q["address"], near, f"{q['key']}: the address is next to the quotation")
            self.assertIn(READ, near, f"{q['key']}: the day is next to the quotation")

    def test_each_sentence_is_in_the_saved_page_where_the_page_is_on_this_machine(self):
        saved = [(q, SAVED_PAGES[q["address"]]) for q in self.fixture["quotations"] if os.path.exists(SAVED_PAGES.get(q["address"], ""))]
        if not saved:
            self.skipTest("the saved pages are not on this machine")
        for q, path in saved:
            with open(path, encoding="utf-8", errors="replace") as fh:
                page = fh.read()
            page = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", page)
            page = flat(html.unescape(re.sub(r"<[^>]+>", " ", page)))
            self.assertIn(q["quotation"], page, q["key"])


class SectionOfTheMethodology(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read("METHODOLOGY.md")
        cls.section = section(cls.text)

    def test_the_heading_appears_once_as_a_numbered_section_after_the_reports_section(self):
        self.assertEqual(len(re.findall(r"^## .*" + re.escape(TITLE) + r"\s*$", self.text, re.M)), 1)
        numbers = {re.match(r"## (\d+)\. (.*)", h).groups()[1]: int(re.match(r"## (\d+)\.", h).group(1))
                   for h in re.findall(r"^## \d+\. .*$", self.text, re.M)}
        self.assertGreater(numbers[TITLE], numbers["Reports, releases, review and coverage"])

    def test_the_three_assumptions_are_named_as_assumptions(self):
        for a in ("A1", "A2", "A3"):
            self.assertEqual(flat(self.section).count(f"*Atlas assumption {a}*"), 1, a)

    def test_no_document_or_page_refers_to_the_section_by_its_number(self):
        n = int(re.search(r"^## (\d+)\. " + re.escape(TITLE), self.text, re.M).group(1))
        for parts in (("README.md",), ("NOTICE.md",), ("web", "src", "components", "AboutDialog.tsx")):
            self.assertIsNone(re.search(rf"[Ss]ections? {n}\b", read(*parts)), parts[-1])
        # the references that do exist name the section by its title
        self.assertIn(f'"{TITLE}"', flat(read("NOTICE.md")))
        self.assertIn(f'"{TITLE}"', flat(self.text.split("**Borders and coasts**", 1)[1].split("**2024 by mode**", 1)[0]))

    def test_the_section_says_what_the_map_does_not_do_and_claims_no_provenance_nor_authority(self):
        flat_section = flat(self.section)
        for part in ("follows no other convention and names no organisation as the authority for a boundary",
                     "no point-of-view switch", "draws no claim line", "draws no maritime claim", "a new version is read by hand"):
            self.assertIn(part, flat_section)
        low = flat_section.lower()
        for word in ("united nations", "the usual form", "is filed under the code", "its trade is filed"):
            self.assertNotIn(word, low)


class BordersAndCoasts(unittest.TestCase):
    SENTENCE = ('These are the borders of the map\'s default view (see "' + TITLE + '" below): a territory that the base map draws as a '
                "shape of its own (Kosovo, Somaliland, Northern Cyprus) has neighbours of its own and so changes the neighbours of the "
                "countries around it.")

    def test_the_sentence_closes_the_paragraph(self):
        text = read("METHODOLOGY.md")
        para = [p for p in paragraphs(text) if p.startswith("**Borders and coasts**")]
        self.assertEqual(len(para), 1)
        self.assertTrue(para[0].endswith(self.SENTENCE), para[0][-400:])

    def test_the_three_territories_have_neighbours_of_their_own_and_appear_in_theirs(self):
        index = {e["c"]: e for e in load("data", "countries", "index.json")}
        for iso, shown in (("KOS", "Kosovo"), ("SOL", "Somaliland"), ("CYN", "N. Cyprus")):
            self.assertEqual(index[iso]["name"], shown)
        neighbours = load("pipeline", "cache", "adjacency.json")["neighbours"]
        for iso in ("KOS", "SOL", "CYN"):
            self.assertTrue(neighbours.get(iso), iso)
            for other in neighbours[iso]:
                self.assertIn(iso, neighbours.get(other, []), f"{iso} is not in the list of its neighbour {other}")


class KnownLimits(unittest.TestCase):
    def test_the_bullet_is_in_the_about_window_names_the_customs_source_and_lists_no_territory(self):
        bullet = known_limits_bullet()
        self.assertIn("CEPII BACI", bullet)
        self.assertIn("trade figures follow the customs codes of CEPII BACI and do not change with the map", bullet)
        index = {e["c"]: e["name"] for e in load("data", "countries", "index.json")}
        for iso in ("KOS", "ESH", "SOL", "CYN"):
            self.assertNotIn(index[iso], bullet, iso)
        self.assertNotIn("Cyprus", bullet)
        # it is one of the "Known limits" of the Method tab
        src = read("web", "src", "components", "AboutDialog.tsx")
        limits = src[src.index("<h3>Known limits</h3>"):]
        self.assertIn("The map follows Natural Earth's default boundaries;", limits[:limits.index("</ul>")])


class Registry(unittest.TestCase):
    def test_the_licence_is_unchanged_and_the_use_names_the_default_view(self):
        entry = {s["id"]: s for s in load("data", "sources.json")}["naturalearth"]
        self.assertEqual(entry["licence"], "Public domain (no credit required)")
        self.assertIn("default view", entry["use"])
        self.assertIn("not refreshed by a workflow", entry["access"])


class Table(unittest.TestCase):
    """The table "What the map draws, area by area" of the section, tested against the shapes the site serves (not against the polygons of the areas)."""
    LEAD = "**What the map draws, area by area.**"
    HEADER = ["Area of Natural Earth (its id)", "Its note", "Points of Natural Earth that it holds", "Shape of the map that holds them",
              "Shape has a customs code in CEPII BACI"]
    NO_SHAPE = " (in no shape)"
    INTERIOR = re.compile(r'^NE 10m disputed areas (\S+) \("(.*)"\) interior point$')
    PLACE = re.compile(r'^NE 10m populated places "(.*)" \(adm0 (\S+)\)$')

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(ROOT, "pipeline", "freight"))
        import route_countries
        cls.shapes, cls.codes = route_countries._country_shapes()
        cls.fixture = load("pipeline", "tests", "fixtures", "border_probes.json")
        cls.probes = {p["label"]: p for p in cls.fixture["probes"]}
        cls.index = {e["c"]: e["name"] for e in load("data", "countries", "index.json")}
        with open(os.path.join(ROOT, "pipeline", "cache", "baci_country_codes.csv"), encoding="utf-8", newline="") as fh:
            cls.baci = {row["country_iso3"] for row in csv.DictReader(fh)}
        clean = ast.parse(read("pipeline", "trade", "clean.py"))
        cls.code_fix = next(ast.literal_eval(n.value) for n in clean.body
                            if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "CODE_FIX" for t in n.targets))
        blocks = re.split(r"\n\s*\n", section(read("METHODOLOGY.md")))
        starts = [i for i, b in enumerate(blocks) if b.startswith(cls.LEAD)]
        assert len(starts) == 1, f"the block {cls.LEAD!r} is not in the section exactly once"
        start = starts[0]
        end = next((i for i in range(start + 1, len(blocks)) if blocks[i].startswith("**")), len(blocks))
        cls.block = blocks[start:end]
        cls.table = [b for b in cls.block if b.lstrip().startswith("|")]
        cls.prose = [flat(b) for b in cls.block if not b.lstrip().startswith("|")]
        cls.rows = []
        if len(cls.table) == 1:
            lines = [ln.strip() for ln in cls.table[0].strip().splitlines()]
            cls.header = [c.strip() for c in lines[0].strip("|").split("|")]
            cls.separator = lines[1]
            cls.rows = [[c.strip() for c in ln.strip("|").split("|")] for ln in lines[2:]]

    # what the served shapes do
    def shape_of(self, label):
        from shapely.geometry import Point
        p = self.probes[label]
        pt = Point(p["lon"], p["lat"])
        for shape, code in zip(self.shapes, self.codes):
            if shape.contains(pt):
                return code
        return None

    def own_label(self, area_id):
        """The label of the probe that is the interior point of the area."""
        for p in self.fixture["probes"]:
            m = self.INTERIOR.match(p["src"])
            if m and m.group(1) == area_id:
                return p["label"]
        raise AssertionError(area_id)

    def customs(self, iso):
        if iso in self.baci:
            return "yes"
        for code, target in self.code_fix.items():
            if target == iso and code in self.baci:
                return f"{code}, read as {self.index[iso]}"
        return "no"

    def listed(self, row):
        """The labels of a row, with whether each carries the suffix."""
        out = []
        for cell in row[2].split("; "):
            suffixed = cell.endswith(self.NO_SHAPE)
            out.append((cell[:-len(self.NO_SHAPE)] if suffixed else cell, suffixed))
        return out

    def shapes_of_row(self, row):
        return [re.fullmatch(r"(.+) \(([A-Za-z0-9]{3})\)", c).groups() for c in row[3].split(", ")]

    def sorted_areas(self):
        return sorted(self.fixture["areas"], key=lambda a: (a["BRK_NAME"], a["BRK_A3"]))

    # the fixture
    def test_the_fixture_says_what_it_is_and_its_points_and_areas_are_sound(self):
        fx = self.fixture
        self.assertTrue(fx["about"].startswith("Points of Natural Earth's own files"), fx["about"])
        self.assertEqual(fx["read"], "2026-11-25")
        self.assertEqual(set(fx["sources"]), {"populated", "disputed"})
        for key, src in fx["sources"].items():
            self.assertRegex(src["address"], r"^https://naciscdn\.org/naturalearth/10m/cultural/ne_10m_.*\.zip$", key)
            self.assertRegex(src["version"], "^" + VERSION + "$", key)
            self.assertRegex(src["sha256"], r"^[0-9a-f]{64}$", key)
            self.assertGreater(src["bytes"], 0, key)
        labels = [p["label"] for p in fx["probes"]]
        self.assertEqual(len(labels), len(set(labels)), "labels are unique")
        for p in fx["probes"]:
            self.assertTrue(p["src"].strip(), p["label"])
            self.assertTrue(math.isfinite(p["lon"]) and math.isfinite(p["lat"]), p["label"])
            self.assertTrue(-180 <= p["lon"] <= 180 and -90 <= p["lat"] <= 90, p["label"])
            self.assertNotIn("; ", p["label"])
            self.assertNotIn("|", p["label"])
            self.assertFalse(p["label"].endswith(self.NO_SHAPE), p["label"])
        ids = [a["BRK_A3"] for a in fx["areas"]]
        self.assertEqual(len(ids), len(set(ids)), "area ids are unique")
        interior = {m.group(1) for m in (self.INTERIOR.match(p["src"]) for p in fx["probes"]) if m}
        self.assertEqual(set(ids), interior, "each area is the area of an interior-point probe and each such probe has its area")
        for a in fx["areas"]:
            self.assertEqual(set(a), {"BRK_A3", "BRK_NAME", "NOTE_BRK"})
            self.assertTrue(a["BRK_NAME"], a["BRK_A3"])
            self.assertNotIn("|", a["NOTE_BRK"])
            src = next(p["src"] for p in fx["probes"] if p["label"] == self.own_label(a["BRK_A3"]))
            self.assertEqual(self.INTERIOR.match(src).group(2), a["BRK_NAME"], "the src names the area as the fixture does")

    # the block of the section
    def test_the_block_is_an_introduction_a_table_and_the_sentences_under_it(self):
        self.assertEqual(len(self.table), 1, "one table")
        self.assertEqual(len(self.prose), 3, "the introduction, the sentence on the code column, the sentences on the points")
        self.assertTrue(self.prose[0].startswith(self.LEAD))
        intro = self.prose[0]
        self.assertIn("version " + self.fixture["sources"]["disputed"]["version"], intro)
        for part in ("layer of breakaway and disputed areas", "which the atlas does not read or draw",
                     "the table says where the country shapes of the map put the points of each area",
                     "Natural Earth's words, as its file spells them, not the atlas's", "pipeline/tests/fixtures/border_probes.json"):
            self.assertIn(part, intro)

    def test_the_header_is_the_one_of_the_brief_and_every_row_has_five_cells(self):
        self.assertEqual(self.header, self.HEADER)
        self.assertRegex(self.separator, r"^\|(\s*:?-{3,}:?\s*\|){5}$")
        for row in self.rows:
            self.assertEqual(len(row), 5, row)

    def test_there_is_one_row_per_area_of_the_fixture_sorted_by_name_then_id_and_no_other(self):
        self.assertEqual([r[0] for r in self.rows], [f"{a['BRK_NAME']} ({a['BRK_A3']})" for a in self.sorted_areas()])

    def test_each_note_is_the_note_of_the_fixture_in_quotation_marks_or_no_note_where_it_is_empty(self):
        for a, row in zip(self.sorted_areas(), self.rows):
            want = '"' + a["NOTE_BRK"] + '"' if a["NOTE_BRK"] else "no note"
            self.assertEqual(row[1], want, a["BRK_A3"])

    def test_the_points_are_probes_of_the_fixture_listed_once_and_each_row_lists_its_own_interior_point(self):
        seen = {}
        for a, row in zip(self.sorted_areas(), self.rows):
            labels = [label for label, _ in self.listed(row)]
            self.assertEqual(len(labels), len(set(labels)), a["BRK_A3"])
            self.assertIn(self.own_label(a["BRK_A3"]), labels, a["BRK_A3"])
            self.assertEqual(labels[0], self.own_label(a["BRK_A3"]), "the interior point comes first")
            for label in labels:
                self.assertIn(label, self.probes, label)
                self.assertNotIn(label, seen, f"{label} is listed in {a['BRK_A3']} and in {seen.get(label)}")
                seen[label] = a["BRK_A3"]

    def test_each_listed_point_lies_in_a_shape_listed_in_its_row_or_in_none_where_the_suffix_says_so(self):
        for a, row in zip(self.sorted_areas(), self.rows):
            listed = [iso for _, iso in self.shapes_of_row(row)]
            for label, suffixed in self.listed(row):
                shape = self.shape_of(label)
                if suffixed:
                    self.assertIsNone(shape, f"{label} carries the suffix and lies in {shape}")
                else:
                    self.assertIsNotNone(shape, f"{label} lies in no shape and has no suffix")
                    self.assertIn(shape, listed, label)
            self.assertEqual(listed[0], self.shape_of(self.own_label(a["BRK_A3"])), f"{a['BRK_A3']}: the first shape holds the interior point")

    def test_every_shape_listed_holds_a_listed_point_once_and_its_name_is_the_one_of_the_index(self):
        for a, row in zip(self.sorted_areas(), self.rows):
            held = []
            for label, _ in self.listed(row):
                shape = self.shape_of(label)
                if shape and shape not in held:
                    held.append(shape)
            shapes = self.shapes_of_row(row)
            self.assertEqual([iso for _, iso in shapes], held, a["BRK_A3"])
            for name, iso in shapes:
                self.assertIn(iso, self.index, iso)
                self.assertEqual(name, self.index[iso], iso)

    def test_the_customs_cell_of_each_shape_agrees_with_the_code_list_and_the_code_fix(self):
        for a, row in zip(self.sorted_areas(), self.rows):
            want = ", ".join(self.customs(iso) for _, iso in self.shapes_of_row(row))
            self.assertEqual(row[4], want, a["BRK_A3"])

    # the sentences
    def test_the_sentence_on_the_code_column_says_what_yes_says_and_does_not_say(self):
        text = self.prose[1]
        for part in ('"yes" says that the shape has a code', "not where a reporter files the trade of a territory drawn inside it",
                     "which the atlas does not know", "Atlas assumption A2"):
            self.assertIn(part, text)

    def test_the_points_of_populated_places_that_carry_another_countrys_code_are_named_as_they_are(self):
        text = self.prose[2]
        pairs = []
        for p in self.fixture["probes"]:
            m = self.PLACE.match(p["src"])
            shape = self.shape_of(p["label"])
            if m and m.group(2) in self.index and shape and shape != m.group(2):
                pairs.append((m.group(1), m.group(2), shape))
        self.assertTrue(pairs)
        for name, adm0, shape in pairs:
            self.assertIn(f'its "{name}" (adm0 {adm0}) falls in the shape of {self.index[shape]} ({shape})', text)
        outside = [p["label"] for p in self.fixture["probes"] if self.shape_of(p["label"]) is None]
        self.assertTrue(outside)
        for label in outside:
            m = self.PLACE.match(self.probes[label]["src"])
            self.assertIn(f'point "{m.group(1)}" (adm0 {m.group(2)}) lies in no shape of the map', text)
            row = next(r for r in self.rows if label in [x for x, _ in self.listed(r)])
            others = {self.shape_of(x) for x, _ in self.listed(row) if x != label}
            self.assertEqual(len(others), 1, others)
            iso = others.pop()
            self.assertIn(f"falls in the shape of {self.index[iso]} ({iso})", text.split("lies in no shape of the map", 1)[1])
            self.assertIn(row[0], text)
        self.assertEqual(text.count("(adm0 "), len(pairs) + len(outside))

    def test_the_block_names_no_filing_of_trade_no_body_no_licence_and_no_figure_outside_the_table(self):
        low = " ".join(self.prose).lower()
        for word in ("trade is filed", "filed under", "reported under", "united nations", "public domain", "open licence", "free to reuse"):
            self.assertNotIn(word, low)
        rest = " ".join(self.prose)
        rest = re.sub(VERSION, "", rest)                  # the version of the layer
        rest = re.sub(r"1:\d+m", "", rest)                # the scales of the files
        rest = re.sub(r"\bA\d\b", "", rest)               # the number of an Atlas assumption
        rest = re.sub(r"\badm0\b", "", rest)              # the name of a column of Natural Earth's files
        rest = re.sub(r"\b[A-Z]\d\d\b", "", rest)         # the id of an area of Natural Earth
        self.assertFalse(re.search(r"\d", rest), rest)   # counts are the file's: none is typed

    # the layer of Natural Earth, where it is on the machine
    def test_the_fixture_areas_equal_the_records_of_the_layer_where_the_layer_is_on_this_machine(self):
        dbf = os.path.join(ROOT, "raw", "naturalearth", "ne_10m_disputed", "ne_10m_admin_0_disputed_areas.dbf")
        if not os.path.exists(dbf):
            self.skipTest("raw/naturalearth/ne_10m_disputed is not on this machine")
        with open(dbf, "rb") as f:
            hdr = f.read(32)
            n, hl, rl = struct.unpack("<I", hdr[4:8])[0], struct.unpack("<H", hdr[8:10])[0], struct.unpack("<H", hdr[10:12])[0]
            fields = []
            while True:
                d = f.read(32)
                if d[0] == 0x0D:
                    break
                fields.append((d[:11].split(b"\0")[0].decode(), d[16]))
            f.seek(hl)
            records = {}
            for _ in range(n):
                rec, pos, r = f.read(rl), 1, {}
                for name, ln in fields:
                    r[name] = rec[pos:pos + ln].decode("utf8", errors="replace").strip(" \0")
                    pos += ln
                records.setdefault(r["BRK_A3"], []).append({k: r[k] for k in ("BRK_A3", "BRK_NAME", "NOTE_BRK")})
        for a in self.fixture["areas"]:
            self.assertEqual(records.get(a["BRK_A3"]), [a], a["BRK_A3"])


if __name__ == "__main__":
    unittest.main()
