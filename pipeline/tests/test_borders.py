"""The notice about the map's boundaries (About window, README, METHODOLOGY.md) and the words around it, tied to each other and to the files.

The About window's list item "Boundaries and names" is the one place the notice is written; the README paragraph and the METHODOLOGY.md
section "The map: boundaries and territories" must carry it character for character once the JSX tags are removed and all white space is
collapsed to one space. The version it names is the one of the registry entry `naturalearth`; the two sentences of Natural Earth that the
section quotes are kept, with their address, in fixtures/naturalearth_boundaries_quotations.json. Nothing here needs raw/: the tests that
compare with the version file of raw/ or with the saved pages of the day they were read skip when those files are absent (GitHub's machines).
The class Table keeps the table of the section (what the country shapes of the map do with the points of every area of Natural Earth's disputed-areas
layer) in line with the shapes the site serves, with fixtures/border_probes.json and with the customs codes. Where raw/naturalearth/ne_10m_disputed
(the unzipped layer) or raw/naturalearth/ne_50m (the countries file) is on the machine, the fixture, the rows and the points the text names are also
compared with those files; the tests that need them skip otherwise.

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
import unicodedata
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
OLD_SENTENCES = ("imply any opinion", "Boundaries and names on the map come from", "keeps others inside the country that claims them")
NOTICE = ("Country shapes are Natural Earth's default view (version {version}). Natural Earth does not apply one rule to every disputed or "
          "self-administered territory: it draws some as shapes of their own and keeps others inside another country, for some the country "
          "that claims them and for others the country that administers them. The boundaries, names and designations on the map do not "
          "imply official endorsement or acceptance, and the atlas takes no position on the status of any territory.")
BULLET = ("The map follows Natural Earth's default boundaries; trade figures follow the customs codes of CEPII BACI and do not change with "
          "the map. A territory that the customs data have no code for has no customs trade flow under its own name.")


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


def read_dbf(path):
    """The records of a .dbf file as dicts of strings (white space and a leading byte order mark dropped), in the file's order."""
    with open(path, "rb") as f:
        hdr = f.read(32)
        n, hl, rl = struct.unpack("<I", hdr[4:8])[0], struct.unpack("<H", hdr[8:10])[0], struct.unpack("<H", hdr[10:12])[0]
        fields = []
        while True:
            d = f.read(32)
            if d[0] == 0x0D:
                break
            fields.append((d[:11].split(b"\0")[0].decode(), d[16]))
        f.seek(hl)
        out = []
        for _ in range(n):
            rec, pos, r = f.read(rl), 1, {}
            for name, ln in fields:
                r[name] = rec[pos:pos + ln].decode("utf8", errors="replace").strip(" \0﻿")
                pos += ln
            out.append(r)
    return out


def read_polygons(path):
    """One shapely geometry per record of a polygon .shp file (outer rings and holes, by the even-odd rule), None for an empty record."""
    from shapely.geometry import Polygon
    with open(path, "rb") as f:
        data = f.read()
    pos, out = 100, []
    while pos < len(data):
        _, clen = struct.unpack(">ii", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + clen * 2]
        pos += 8 + clen * 2
        kind = struct.unpack("<i", body[:4])[0]
        if kind == 0:
            out.append(None)
            continue
        assert kind == 5, kind
        nparts, npts = struct.unpack("<ii", body[36:44])
        parts = list(struct.unpack(f"<{nparts}i", body[44:44 + 4 * nparts])) + [npts]
        off = 44 + 4 * nparts
        pts = [struct.unpack("<dd", body[off + 16 * i:off + 16 * i + 16]) for i in range(npts)]
        shape = None
        for i in range(nparts):
            ring = pts[parts[i]:parts[i + 1]]
            if len(ring) >= 4:
                piece = Polygon(ring).buffer(0)
                shape = piece if shape is None else shape.symmetric_difference(piece)
        out.append(shape)
    return out


def customs_codes():
    """The ids of the shapes that have a customs code in CEPII BACI (by the code list or by CODE_FIX), and the CODE_FIX table."""
    with open(os.path.join(ROOT, "pipeline", "cache", "baci_country_codes.csv"), encoding="utf-8", newline="") as fh:
        baci = {row["country_iso3"] for row in csv.DictReader(fh)}
    clean = ast.parse(read("pipeline", "trade", "clean.py"))
    code_fix = next(ast.literal_eval(n.value) for n in clean.body
                    if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "CODE_FIX" for t in n.targets))
    with_code = set(baci) | {target for code, target in code_fix.items() if code in baci}
    return baci, code_fix, with_code


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
                     "draws some as shapes of their own and keeps others inside another country, for some the country that claims them "
                     "and for others the country that administers them",
                     "do not imply official endorsement or acceptance",
                     "the atlas takes no position on the status of any territory"):
            self.assertIn(part, self.notice)

    def test_the_notice_is_the_exact_text_with_the_version_of_the_registry(self):
        version = re.search(r"\(version (" + VERSION + r")\)", {s["id"]: s for s in load("data", "sources.json")}["naturalearth"]["access"]).group(1)
        self.assertEqual(self.notice, NOTICE.format(version=version))


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

    def test_the_generated_list_of_sources_names_the_same_version(self):
        line = next(ln for ln in read("DATA_SOURCES.md").splitlines() if ln.startswith("| `naturalearth` |"))
        self.assertEqual(re.findall(r"\(version (" + VERSION + r")\)", line), [self.registry_version])

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
        self.assertEqual(bullet, BULLET, "both sentences of the bullet, as written")
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

    def test_no_shape_without_a_customs_code_has_a_customs_flow_or_row_under_its_own_name(self):
        _, _, with_code = customs_codes()
        index = {e["c"]: e["name"] for e in load("data", "countries", "index.json")}
        without = {c for c in index if c not in with_code}
        self.assertTrue(without, "the second sentence of the bullet is about shapes that exist")
        # the shapes the section names as drawn apart have no code
        for iso in ("KOS", "ESH", "SOL", "CYN", "KAS"):
            self.assertIn(iso, without)
        found = []

        def walk(node, where):
            if isinstance(node, dict):
                if node.get("s") == "baci":
                    for key in ("o", "d", "c"):
                        if isinstance(node.get(key), str) and node[key] in without:
                            found.append((where, key, node[key]))
                    for row in node.get("rows", []) if isinstance(node.get("rows"), list) else []:
                        if isinstance(row, dict) and row.get("c") in without:
                            found.append((where, "row", row["c"]))
                for v in node.values():
                    walk(v, where)
            elif isinstance(node, list):
                for v in node:
                    walk(v, where)

        folder = os.path.join(ROOT, "data", "commodities")
        for dirpath, _, files in os.walk(folder):
            for name in files:
                if name.endswith(".json"):
                    path = os.path.join(dirpath, name)
                    walk(load(*os.path.relpath(path, ROOT).split(os.sep)), os.path.relpath(path, ROOT))
        self.assertEqual(found, [])


class Registry(unittest.TestCase):
    def test_the_licence_is_unchanged_and_the_use_names_the_default_view(self):
        entry = {s["id"]: s for s in load("data", "sources.json")}["naturalearth"]
        self.assertEqual(entry["licence"], "Public domain (no credit required)")
        self.assertIn("default view", entry["use"])
        self.assertIn("not refreshed by a workflow", entry["access"])


class Table(unittest.TestCase):
    """The table "What the map draws, area by area" of the section, tested against the shapes the site serves (against the polygons of the areas
    only where the layer is on the machine)."""
    LEAD = "**What the map draws, area by area.**"
    HEADER = ["Area of Natural Earth (its id)", "Its note", "Points tested that it holds", "Shape of the map that holds them",
              "Shape has a customs code in CEPII BACI"]
    NO_SHAPE = " (in no shape)"
    NO_CODE = "-"
    KINDS = ("place", "interior", "by hand")
    # the probes that no area of the layer holds (the test of the polygons, where the layer is on the machine, checks it)
    HELD_BY_NO_AREA = ("Mariupol",)
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
        cls.baci, cls.code_fix, _ = customs_codes()
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
        if row[3] == self.NO_SHAPE.strip():
            return []
        return [re.fullmatch(r"(.+) \(([A-Za-z0-9]{3})\)", c).groups() for c in row[3].split(", ")]

    @staticmethod
    def sort_name(name):
        """The name without accents, capitals and small letters alike."""
        return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()

    def sorted_areas(self):
        return sorted(self.fixture["areas"], key=lambda a: (self.sort_name(a["BRK_NAME"]), a["BRK_A3"]))

    # the fixture
    def test_the_fixture_says_what_it_is_and_its_points_and_areas_are_sound(self):
        fx = self.fixture
        self.assertTrue(fx["about"].startswith("Points tested against the country shapes of the map, and the areas they belong to."), fx["about"])
        for part in ("every record of Natural Earth's 1:10m layer of breakaway and disputed areas",
                     "a point inside its polygon that the atlas computed from the layer", "two points that the atlas chose by hand"):
            self.assertIn(part, fx["about"])
        self.assertNotIn("Natural Earth's own points", fx["about"])
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
            # what each point is: a place of the populated-places file, a point computed inside an area, or a point chosen by hand
            self.assertIn(p["kind"], self.KINDS, p["label"])
            self.assertEqual(bool(self.PLACE.match(p["src"])), p["kind"] == "place", p["label"])
            self.assertEqual(bool(self.INTERIOR.match(p["src"])), p["kind"] == "interior", p["label"])
            self.assertEqual(p["src"].startswith("point chosen by hand ("), p["kind"] == "by hand", p["label"])
            self.assertNotIn("audit", (p["label"] + p["src"] + p["why"]).lower(), "the points chosen by hand are named for what they are")
        by_hand = [p["label"] for p in fx["probes"] if p["kind"] == "by hand"]
        self.assertTrue(by_hand)
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
        self.assertEqual(len(self.prose), 4, "the introduction, the sentence on the code column, the sentences on the points, the simplification")
        self.assertTrue(self.prose[0].startswith(self.LEAD))
        intro = self.prose[0]
        self.assertIn("version " + self.fixture["sources"]["disputed"]["version"], intro)
        for part in ("The table lists every area of Natural Earth's layer of breakaway and disputed areas", "which the atlas does not read or draw",
                     "in the order of the names of the layer (letters without accents, capitals and small letters alike), then of its ids",
                     "where the country shapes of the map put the points tested for it",
                     "places of Natural Earth's populated-places file",
                     "a point inside its polygon that the atlas computed from the layer (inside one part, for an area of several parts)",
                     "two points that the atlas chose by hand",
                     'A point that lies in no shape of the map is followed by "(in no shape)"',
                     'an area whose points all lie in no shape has "(in no shape)" for its shape',
                     "Natural Earth's words, as its file spells them, not the atlas's", "pipeline/tests/fixtures/border_probes.json"):
            self.assertIn(part, intro)
        self.assertNotIn("Natural Earth's own points", intro)
        # the two points chosen by hand are named in the introduction as the fixture and the rows name them
        by_hand = [p["label"] for p in self.fixture["probes"] if p["kind"] == "by hand"]
        self.assertEqual(re.findall(r'"(Point chosen [^"]+)"', intro), by_hand)
        # the numbers that the layer holds are not typed: the table has the rows of the layer
        self.assertEqual(len(self.rows), len(self.fixture["areas"]))

    def test_the_header_is_the_one_of_the_brief_and_every_row_has_five_cells(self):
        self.assertEqual(self.header, self.HEADER)
        self.assertRegex(self.separator, r"^\|(\s*:?-{3,}:?\s*\|){5}$")
        for row in self.rows:
            self.assertEqual(len(row), 5, row)

    def test_there_is_one_row_per_area_of_the_fixture_sorted_by_name_without_accents_then_id_and_no_other(self):
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
            own = self.shape_of(self.own_label(a["BRK_A3"]))
            if own:
                self.assertEqual(listed[0], own, f"{a['BRK_A3']}: the first shape holds the interior point")
            if not listed:
                self.assertEqual(row[3], "(in no shape)", a["BRK_A3"])
                self.assertTrue(all(suffixed for _, suffixed in self.listed(row)), a["BRK_A3"])

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
            want = ", ".join(self.customs(iso) for _, iso in self.shapes_of_row(row)) or self.NO_CODE
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
        outside = [p["label"] for p in self.fixture["probes"] if p["kind"] == "place" and self.shape_of(p["label"]) is None]
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

    def test_every_point_of_the_fixture_is_listed_in_a_row_or_is_in_the_short_list_of_points_that_no_area_holds(self):
        listed = {label for row in self.rows for label, _ in self.listed(row)}
        unlisted = [p["label"] for p in self.fixture["probes"] if p["label"] not in listed]
        self.assertEqual(sorted(unlisted), sorted(self.HELD_BY_NO_AREA))
        for label in self.HELD_BY_NO_AREA:
            self.assertEqual(self.probes[label]["kind"], "place", label)
        by_hand = {p["label"] for p in self.fixture["probes"] if p["kind"] == "by hand"}
        self.assertTrue(by_hand <= listed, "the points chosen by hand are in rows")

    # what the paragraph on the simplification says
    SIMPLIFICATION = ("The shapes of the map are Natural Earth's 1:50m shapes, simplified by the atlas for the site (`-simplify` with "
                      "`keep-shapes`, in `pipeline/geo/build_countries.mjs`), so a point near an edge can lie in another shape of the map "
                      "than in Natural Earth's own 1:50m file of countries. The points for which the two differ are these: ")
    ITEM = re.compile(r'^(?:"(?P<place>[^"]+)" \(adm0 (?P<adm0>\w{3})\)|the interior point of (?P<area>.+) \((?P<id>\w\d\d)\))'
                      r": (?P<raw>no shape|the shape of (?P<rawname>.+) \((?P<rawiso>\w{3})\)) in Natural Earth's file, "
                      r"(?P<map>no shape|the shape of (?P<mapname>.+?) \((?P<mapiso>\w{3})\)) in the map$")

    def simplification_items(self):
        """The points that the paragraph names: (label, shape in Natural Earth's file or None, shape in the map or None), in the order named."""
        text = self.prose[3]
        self.assertTrue(text.startswith(self.SIMPLIFICATION), text[:300])
        self.assertTrue(text.endswith("."))
        out = []
        for item in text[len(self.SIMPLIFICATION):-1].split("; "):
            m = self.ITEM.match(item)
            self.assertIsNotNone(m, item)
            if m.group("place"):
                label = next(p["label"] for p in self.fixture["probes"]
                             if (found := self.PLACE.match(p["src"])) and found.groups() == (m.group("place"), m.group("adm0")))
            else:
                area = next(a for a in self.fixture["areas"] if a["BRK_A3"] == m.group("id"))
                self.assertEqual(area["BRK_NAME"], m.group("area"), item)
                label = self.own_label(area["BRK_A3"])
            for side, iso, name in (("raw", m.group("rawiso"), m.group("rawname")), ("map", m.group("mapiso"), m.group("mapname"))):
                if iso:
                    self.assertEqual(self.index[iso], name, item)
            out.append((label, m.group("rawiso"), m.group("mapiso")))
        return out

    def test_the_paragraph_on_the_simplification_names_the_command_and_what_the_map_does_with_each_point(self):
        build = read("pipeline", "geo", "build_countries.mjs")
        self.assertIn("-simplify", build)
        self.assertIn("keep-shapes", build)
        items = self.simplification_items()
        self.assertEqual(len({label for label, _, _ in items}), len(items), "each point once")
        for label, raw, served in items:
            self.assertEqual(served, self.shape_of(label), label)
            self.assertNotEqual(raw, served, label)
        # the point whose absence from the map the sentence on W. Sahara states is one of them
        named = {label for label, _, _ in items}
        for p in self.fixture["probes"]:
            if p["kind"] == "place" and self.shape_of(p["label"]) is None:
                self.assertIn(p["label"], named)

    # what the convention paragraph and the notice say about the rows
    ALIASES = {"Azer.": "AZE", "U.K.": "GBR", "U.S.A.": "USA", "UAE": "ARE", "the United States": "USA", "the Philippines": "PHL",
               "the Seychelles": "SYC"}
    # every form of note that the layer has, as its file spells them; a clause of none of these forms is not read
    NOTE_FORMS = (("administered", r"Admin\.? [Bb]y (?P<who>.+)"), ("self", r"Self admin\."), ("claimed", r"Claimed by (?P<who>.+)"),
                  ("leased", r"Leased to .+ by .+"), ("ceded", r"Ceded to .+ by .+"), ("between", r"Between .+ and .+"),
                  ("patrolled", r"UN Patrolled Zone in .+|Since 1953 .+"), ("survey", r"under survey"))

    def resolve(self, name):
        """The id of the shape that a country of a note names, or None where the name is not one the test can read."""
        if name in self.ALIASES:
            return self.ALIASES[name]
        ids = [c for c, n in self.index.items() if n == name]
        return ids[0] if len(ids) == 1 else None

    def read_note(self, note):
        out = {"administrator": None, "self": False, "claimants": set(), "forms": []}
        for clause in [c for c in note.split("; ") if c]:
            form = next(((k, re.fullmatch(rx, clause)) for k, rx in self.NOTE_FORMS if re.fullmatch(rx, clause)), None)
            self.assertIsNotNone(form, f"a form of note that the test does not list: {clause!r}")
            kind, m = form
            out["forms"].append(kind)
            if kind == "self":
                out["self"] = True
            elif kind == "administered":
                out["administrator"] = self.resolve(m.group("who"))
            elif kind == "claimed":
                out["claimants"] |= {i for i in (self.resolve(w) for w in re.split(r", and |, | and ", m.group("who"))) if i}
        return out

    def kind_of(self, area):
        """Where the map puts the interior point of the area, read against the area's own note."""
        note = self.read_note(area["NOTE_BRK"])
        shape = self.shape_of(self.own_label(area["BRK_A3"]))
        if shape is None:
            return "in no shape"
        if shape == note["administrator"] and note["claimants"] - {shape}:
            return "inside the country that administers it while another claims it"
        if shape in note["claimants"] and shape != note["administrator"]:
            return "inside a country that claims it and is not said to administer it"
        if note["self"] and shape not in note["claimants"]:
            return "a shape of its own"
        return "other"

    def kinds(self):
        out = {}
        for a in self.sorted_areas():
            out.setdefault(self.kind_of(a), []).append(f"{a['BRK_NAME']} ({a['BRK_A3']})")
        return out

    def test_the_convention_and_the_notice_say_only_what_the_notes_and_the_shapes_of_the_rows_show(self):
        kinds = self.kinds()
        for kind in ("inside a country that claims it and is not said to administer it",
                     "inside the country that administers it while another claims it", "a shape of its own"):
            self.assertTrue(kinds.get(kind), f"no area is {kind}: {sorted(kinds)}")
        para = next(p for p in paragraphs(section(read("METHODOLOGY.md"))) if p.startswith("**Convention.**"))
        self.assertIn("a point inside some of them falls in a shape of their own and a point inside others falls in the shape of the country "
                      "that claims them, or of the country that administers them", para)
        self.assertIn("at places of Natural Earth's populated-places file, at points that the atlas computed inside the polygons of Natural "
                      "Earth's disputed-areas layer, and at two points that the atlas chose by hand", para)
        self.assertNotIn("own populated-places and disputed-areas files", para)

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
        records = [{k: r[k] for k in ("BRK_A3", "BRK_NAME", "NOTE_BRK")} for r in read_dbf(self.layer() + ".dbf")]
        self.assertEqual(len(records), len(self.fixture["areas"]), "every record of the layer is an area of the fixture, and no other")
        self.assertEqual(len({r["BRK_A3"] for r in records}), len(records), "the ids of the layer are unique")
        by_id = {r["BRK_A3"]: r for r in records}
        for a in self.fixture["areas"]:
            self.assertEqual(by_id.get(a["BRK_A3"]), a, a["BRK_A3"])
        self.assertEqual(len(self.rows), len(records), "one row per record of the layer")

    LAYER = os.path.join(ROOT, "raw", "naturalearth", "ne_10m_disputed", "ne_10m_admin_0_disputed_areas")
    COUNTRIES = os.path.join(ROOT, "raw", "naturalearth", "ne_50m", "ne_50m_admin_0_countries")

    def layer(self):
        if not os.path.exists(self.LAYER + ".dbf") or not os.path.exists(self.LAYER + ".shp"):
            self.skipTest("raw/naturalearth/ne_10m_disputed is not on this machine")
        return self.LAYER

    def test_each_row_holds_the_points_that_lie_in_the_polygon_of_its_area_and_no_other_where_the_layer_is_on_this_machine(self):
        from shapely.geometry import Point
        records = read_dbf(self.layer() + ".dbf")
        polygons = {r["BRK_A3"]: g for r, g in zip(records, read_polygons(self.layer() + ".shp"))}
        rows = {a["BRK_A3"]: {label for label, _ in self.listed(row)} for a, row in zip(self.sorted_areas(), self.rows)}
        for p in self.fixture["probes"]:
            pt = Point(p["lon"], p["lat"])
            inside = {i for i, g in polygons.items() if g is not None and g.contains(pt)}
            held = {i for i, labels in rows.items() if p["label"] in labels}
            self.assertEqual(held, inside, f"{p['label']}: listed in {sorted(held)}, inside the polygon of {sorted(inside)}")
        for label in self.HELD_BY_NO_AREA:
            self.assertFalse(any(g is not None and g.contains(Point(self.probes[label]["lon"], self.probes[label]["lat"]))
                                 for g in polygons.values()), label)

    def test_the_points_that_the_simplification_moves_are_those_the_text_names_where_the_countries_file_is_on_this_machine(self):
        if not os.path.exists(self.COUNTRIES + ".shp"):
            self.skipTest("raw/naturalearth/ne_50m is not on this machine")
        from shapely.geometry import Point
        from shapely.ops import unary_union
        records = read_dbf(self.COUNTRIES + ".dbf")
        by_code = {}
        for r, g in zip(records, read_polygons(self.COUNTRIES + ".shp")):
            code = r["ISO_A3_EH"] if r["ISO_A3_EH"] not in ("", "-99") else r["ADM0_A3"]   # the rule of build_countries.mjs
            if code != "ATA" and g is not None:
                by_code.setdefault(code, []).append(g)
        raw = {code: unary_union(parts) for code, parts in by_code.items()}
        self.assertEqual(set(raw), set(self.codes), "the shapes of the file and the shapes of the map are the same countries")
        differing = {}
        for p in self.fixture["probes"]:
            pt = Point(p["lon"], p["lat"])
            in_file = [c for c, g in raw.items() if g.contains(pt)]
            self.assertLessEqual(len(in_file), 1, p["label"])
            if (in_file[0] if in_file else None) != self.shape_of(p["label"]):
                differing[p["label"]] = (in_file[0] if in_file else None, self.shape_of(p["label"]))
        self.assertEqual(differing, {label: (raw_iso, served) for label, raw_iso, served in self.simplification_items()})


if __name__ == "__main__":
    unittest.main()
