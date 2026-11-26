"""The registry entry `sec-edgar` (data/sources.json) and its row of NOTICE.md, tied to the sentences of the SEC's pages that they quote.

The sentences were read on sec.gov on 26 November 2026 and are kept, with their address, in fixtures/sec_edgar_terms_quotations.json, so that
they are typed once: each text must hold the quotations of its field word for word, with the address and the day they were read, and must not
say what no page read says ("public domain", "open licence"). The program that reads the filings is described by the `access` field: it
must name it, and the file must exist.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_sec_edgar_terms.py"
"""
import json
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIXTURE = os.path.join(ROOT, "pipeline", "tests", "fixtures", "sec_edgar_terms_quotations.json")
REGISTRY = os.path.join(ROOT, "data", "sources.json")
NOTICE = os.path.join(ROOT, "NOTICE.md")
READ = "read 26 November 2026"


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class SecEdgarTerms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load(FIXTURE)
        cls.entry = {s["id"]: s for s in load(REGISTRY)}["sec-edgar"]
        with open(NOTICE, encoding="utf-8") as fh:
            cls.notice = fh.read()

    def test_the_fixture_says_what_it_is_and_when_the_pages_were_read(self):
        self.assertTrue(self.fixture["about"].startswith("Quotations of a few sentences, with their address"))
        self.assertEqual(self.fixture["read"], "2026-11-26")
        self.assertEqual(READ, "read 26 November 2026")
        keys = [q["key"] for q in self.fixture["quotations"]]
        self.assertEqual(len(keys), len(set(keys)))
        for q in self.fixture["quotations"]:
            self.assertEqual(q["registry"], "sec-edgar")
            self.assertIn(q["field"], ("licence", "access"))
            self.assertRegex(q["address"], r"^https://www\.sec\.gov/", q["key"])
            self.assertEqual(q["quotation"], " ".join(q["quotation"].split()), f"{q['key']}: spacing is normalised")

    def test_each_field_holds_its_quotations_with_their_address_and_the_day_they_were_read(self):
        for q in self.fixture["quotations"]:
            text = self.entry[q["field"]]
            self.assertIn(f'"{q["quotation"]}"', text, q["key"])
            i = text.index(f'"{q["quotation"]}"')
            near = text[max(0, i - 120):i + len(q["quotation"]) + 200]
            self.assertIn(q["address"], near, f"{q['key']}: the address of the page is next to the quotation")
            self.assertIn(READ, near, f"{q['key']}: the day the page was read is next to the quotation")

    def test_the_notice_holds_the_dissemination_sentence_and_its_address(self):
        q = next(x for x in self.fixture["quotations"] if x["key"] == "sec-website-dissemination")
        row = next(line for line in self.notice.splitlines() if line.startswith("| SEC EDGAR filings"))
        self.assertIn(f'"{q["quotation"]}"', row)
        self.assertIn(q["address"], row)
        self.assertIn(READ, row)
        self.assertIn("Not affiliated with the SEC", row)

    def test_the_licence_says_what_the_pages_do_not_say(self):
        licence = self.entry["licence"]
        for words in ("public domain", "open licence", "free to reuse", "no restriction", "not copyrighted"):
            self.assertNotIn(words, licence.lower())
        self.assertIn("says nothing of the rights a company may hold in the text of its own report", licence)
        self.assertNotIn("were not read", licence)

    def test_the_access_field_names_the_program_and_never_an_address(self):
        access = self.entry["access"]
        self.assertIn("pipeline/companies/sec_get.py", access)
        self.assertTrue(os.path.exists(os.path.join(ROOT, "pipeline", "companies", "sec_get.py")))
        for text in (self.entry["licence"], access):
            self.assertEqual(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text), [])


if __name__ == "__main__":
    unittest.main()
