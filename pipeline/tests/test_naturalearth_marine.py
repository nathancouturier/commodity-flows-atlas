"""The registry entry of the marine areas of Natural Earth (data/sources.json: `naturalearth-marine`) and the notice that quotes the terms,
tied to the sentences they quote.

The sentences were read on Natural Earth's terms of use page and in the README of the marine areas zip on 25 November 2026 and are kept, with
their address, in fixtures/naturalearth_terms_quotations.json, so that they are typed once: NOTICE.md must hold each of them word for word, next
to its address and the day it was read. Where the saved copy of the page is on the machine, each sentence of the page is also looked up in its text;
where the unzipped README is under raw/, the sentence of the README is looked up in it (the test skips those two comparisons elsewhere, as on GitHub's
machines). The data file itself is tied to its builder by web/scripts/seas.test.mjs and to its rules by web/scripts/validate-labels.mjs.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_naturalearth_marine.py"
"""
import html
import json
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIXTURE = os.path.join(ROOT, "pipeline", "tests", "fixtures", "naturalearth_terms_quotations.json")
REGISTRY = os.path.join(ROOT, "data", "sources.json")
NOTICE = os.path.join(ROOT, "NOTICE.md")
SAVED_TERMS_PAGE = "/tmp/claude-0/audit/work/7A/MAPL/dl/ne_terms.html"
RAW_README = os.path.join(ROOT, "raw", "naturalearth", "ne_50m_marine", "ne_50m_geography_marine_polys.README.html")
READ = "read 25 November 2026"
TERMS_ADDRESS = "https://www.naturalearthdata.com/about/terms-of-use/"
REFUSED = ("free to reuse", "open licence", "open license")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def squash(text):
    return " ".join(text.split())


def page_text(raw):
    raw = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", raw)
    return squash(html.unescape(re.sub(r"<[^>]+>", " ", raw)))


class NaturalEarthMarine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load(FIXTURE)
        cls.registry = {s["id"]: s for s in load(REGISTRY)}
        with open(NOTICE, encoding="utf-8") as fh:
            cls.notice = squash(fh.read())

    def test_the_fixture_says_what_it_is_and_when_the_pages_were_read(self):
        self.assertTrue(self.fixture["about"].startswith("Quotations of a few sentences, with their address"))
        self.assertEqual(self.fixture["read"], "2026-11-25")
        self.assertEqual(READ, "read 25 November 2026")
        keys = [q["key"] for q in self.fixture["quotations"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertGreaterEqual(len(keys), 8)
        for q in self.fixture["quotations"]:
            self.assertRegex(q["address"], r"^https://", q["key"])
            self.assertTrue(q["quotation"].strip(), q["key"])
            self.assertEqual(q["quotation"], squash(q["quotation"]), f"{q['key']}: spacing is normalised")

    def test_the_notice_holds_every_sentence_word_for_word_next_to_its_address_and_the_day_it_was_read(self):
        for q in self.fixture["quotations"]:
            quoted = f'"{q["quotation"]}"'
            self.assertIn(quoted, self.notice, q["key"])
            i = self.notice.index(quoted)
            near = self.notice[max(0, i - 450):i + len(quoted) + 450]
            self.assertIn(q["address"], near, f"{q['key']}: the address of the page is next to the quotation")
            self.assertIn(READ, near, f"{q['key']}: the day the page was read is next to the quotation")

    def test_every_sentence_of_the_terms_page_is_in_the_saved_copy_of_the_page(self):
        if not os.path.exists(SAVED_TERMS_PAGE):
            self.skipTest("the saved copy of the terms page is not on this machine")
        with open(SAVED_TERMS_PAGE, encoding="utf-8", errors="replace") as fh:
            text = page_text(fh.read())
        terms = [q for q in self.fixture["quotations"] if q["address"] == TERMS_ADDRESS]
        self.assertGreaterEqual(len(terms), 7)
        for q in terms:
            self.assertIn(q["quotation"], text, q["key"])

    def test_the_sentence_of_the_readme_is_in_the_readme_of_the_zip(self):
        if not os.path.exists(RAW_README):
            self.skipTest("raw/naturalearth/ne_50m_marine is not on this machine")
        with open(RAW_README, encoding="utf-8", errors="replace") as fh:
            text = page_text(fh.read())
        readme = [q for q in self.fixture["quotations"] if q["address"] != TERMS_ADDRESS]
        self.assertTrue(readme)
        for q in readme:
            self.assertIn(q["quotation"], text, q["key"])

    def test_the_registry_entry_exists_and_names_what_it_is_used_for(self):
        e = self.registry["naturalearth-marine"]
        self.assertEqual(e["publisher"], "Natural Earth")
        self.assertEqual(e["url"], "https://www.naturalearthdata.com/downloads/50m-physical-vectors/")
        self.assertIn("marine areas 1:50m", e["name"])
        self.assertIn("oceans, seas, bays and gulfs", e["use"])
        self.assertIn("names", e["use"].lower())
        self.assertIn("build_seas.mjs", e["access"])
        self.assertIn("not refreshed by a workflow", e["access"])
        self.assertEqual(e["update"], "irregular")
        self.assertIn("country names on the map", self.registry["naturalearth"]["use"])

    def test_the_registry_text_says_no_more_than_the_page_does(self):
        for sid in ("naturalearth", "naturalearth-marine"):
            for field in ("name", "licence", "access", "use"):
                text = self.registry[sid][field].lower()
                for words in REFUSED:
                    self.assertNotIn(words, text, f"{sid}.{field}")

    def test_the_two_entries_agree_on_the_licence_sentence_and_the_notice_holds_the_sentences_it_rests_on(self):
        self.assertEqual(self.registry["naturalearth-marine"]["licence"], self.registry["naturalearth"]["licence"])
        by_key = {q["key"]: q["quotation"] for q in self.fixture["quotations"]}
        self.assertIn("are in the public domain", by_key["public-domain"])
        self.assertIn("Crediting the authors is unnecessary", by_key["no-permission"])

    def test_the_notice_says_public_domain_of_the_marine_areas_only_inside_a_quotation(self):
        i = self.notice.index("- **Natural Earth** (basemap")
        bullet = self.notice[i:self.notice.index("- **World Bank Pink Sheet**", i)]
        outside = re.sub(r'"[^"]*"', "", bullet)
        self.assertNotRegex(outside, r"(?i)public domain|open licen|free to reuse")


if __name__ == "__main__":
    unittest.main()
