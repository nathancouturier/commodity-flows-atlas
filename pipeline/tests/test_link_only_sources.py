"""The registry entries of the two publishers whose figures the atlas links to and never shows (data/sources.json: `sse`, the Shanghai
Shipping Exchange, and `usda-ams`, the USDA Agricultural Marketing Service), tied to the sentences they quote.

The sentences were read on the publishers' pages on 25 November 2026 and are kept, with their address, in
fixtures/link_only_sources_quotations.json, so that they are typed once: the registry text must hold each of them word for word, with its
address and the day it was read, and must not say what no page read says (public domain, open, free to reuse). Whether the licence text is a
permission to offer a download is decided by web/src/lib/licence.ts and checked by web/scripts/licence.test.mjs, which refuses both entries.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_link_only_sources.py"
"""
import json
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIXTURE = os.path.join(ROOT, "pipeline", "tests", "fixtures", "link_only_sources_quotations.json")
REGISTRY = os.path.join(ROOT, "data", "sources.json")
READ = "read 25 November 2026"


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class LinkOnlySources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load(FIXTURE)
        cls.registry = {s["id"]: s for s in load(REGISTRY)}

    def test_the_fixture_says_what_it_is_and_when_the_pages_were_read(self):
        self.assertTrue(self.fixture["about"].startswith("Quotations of a few sentences, with their address"))
        self.assertEqual(self.fixture["read"], "2026-11-25")
        self.assertEqual(READ, "read 25 November 2026")
        keys = [q["key"] for q in self.fixture["quotations"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual({q["registry"] for q in self.fixture["quotations"]}, {"sse", "usda-ams"})
        for q in self.fixture["quotations"]:
            self.assertRegex(q["address"], r"^https://", q["key"])
            self.assertTrue(q["quotation"].strip(), q["key"])
            self.assertEqual(q["quotation"], " ".join(q["quotation"].split()), f"{q['key']}: spacing is normalised")

    def test_each_licence_text_holds_every_quotation_of_its_entry_with_its_address_and_the_day_it_was_read(self):
        for q in self.fixture["quotations"]:
            licence = self.registry[q["registry"]]["licence"]
            self.assertIn(f'"{q["quotation"]}"', licence, q["key"])
            i = licence.index(f'"{q["quotation"]}"')
            # the address and the day are in the bracket after the quotation, or, for a second sentence of the same page, in the one before it
            near = licence[max(0, i - 330):i + len(q["quotation"]) + 330]
            self.assertIn(q["address"], near, f"{q['key']}: the address of the page is next to the quotation")
            self.assertIn(READ, near, f"{q['key']}: the day the page was read is next to the quotation")

    def test_a_metadata_field_is_given_with_the_statement_that_the_table_has_no_licence_field(self):
        for q in (x for x in self.fixture["quotations"] if x["kind"] == "metadata field"):
            self.assertEqual(q["absent_field"], "license")
            self.assertIn("no licence field", self.registry[q["registry"]]["licence"], q["key"])

    def test_the_entries_are_link_only_nothing_is_fetched_and_no_value_is_shown(self):
        for sid in ("sse", "usda-ams"):
            e = self.registry[sid]
            self.assertTrue(e["url"].startswith("https://www.ams.usda.gov/") or e["url"] == "https://en.sse.net.cn/", sid)
            self.assertIn("nothing is fetched", e["access"], sid)
            self.assertIn("no value is stored or shown", e["use"], sid)
            self.assertIn("it offers no download of this material", e["licence"], sid)
            # the words the licence rule reads as a refusal: no download is offered whatever else the text quotes
            self.assertRegex(e["licence"], r"[Nn]o licen[cs]e (is )?stated", sid)
            self.assertEqual(e["update"], "n/a", sid)
        self.assertEqual(self.registry["sse"]["publisher"], "Shanghai Shipping Exchange")
        self.assertEqual(self.registry["usda-ams"]["publisher"], "USDA Agricultural Marketing Service")

    def test_no_text_of_the_two_entries_calls_the_data_public_domain_open_or_free_to_reuse(self):
        for sid in ("sse", "usda-ams"):
            e = self.registry[sid]
            for field in ("name", "licence", "access", "use"):
                text = e[field]
                # the one sentence of the AMS page that says "public information" is quoted whole; strip every quotation, then look
                for q in (x["quotation"] for x in self.fixture["quotations"]):
                    text = text.replace(f'"{q}"', "")
                self.assertNotRegex(text, r"(?i)public domain|\bopen\b|open licen[cs]e|free to reuse|free to use|\bfree\b", f"{sid} {field}")

    def test_the_licence_text_does_not_say_that_anybody_decided_anything(self):
        for sid in ("sse", "usda-ams"):
            self.assertNotRegex(self.registry[sid]["licence"], r"(?i)decided|accepted|approved", sid)

    def test_the_two_entries_are_in_the_generated_table(self):
        with open(os.path.join(ROOT, "DATA_SOURCES.md"), encoding="utf-8") as fh:
            doc = fh.read()
        for sid in ("sse", "usda-ams"):
            self.assertRegex(doc, rf"(?m)^\| `{sid}` \|", sid)

    def test_the_portwatch_use_names_the_digest_and_the_licence_of_portwatch_is_unchanged(self):
        pw = self.registry["portwatch"]
        self.assertIn("data/freight/market-now.json", pw["use"])
        self.assertIn("five passages", pw["use"])
        self.assertTrue(pw["licence"].startswith("IMF terms of use for statistical data"))
        self.assertTrue(re.search(r"data adapted$", pw["licence"]))


if __name__ == "__main__":
    unittest.main()
