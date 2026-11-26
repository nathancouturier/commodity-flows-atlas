"""The sources table of DATA_SOURCES.md (pipeline/common/sources_table.py): generated from the registry, and its introduction says only what the
registry supports: every figure shown comes from a source that is free to read, and the entries that are only linked show no value.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_sources_table.py"
"""
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "common"))

import sources_table as T  # noqa: E402


def registry():
    with open(os.path.join(ROOT, "data", "sources.json"), encoding="utf-8") as fh:
        return json.load(fh)


def intro(sources):
    return T.render(sources).split("\n\n")[1]


def entry(i, use="Used for something"):
    return {"id": i, "name": f"Source {i}", "publisher": "Publisher", "url": f"https://example.org/{i}", "licence": "CC BY 4.0", "update": "yearly", "access": "download", "use": use}


class Introduction(unittest.TestCase):
    def test_the_published_table_is_the_registrys(self):
        with open(os.path.join(ROOT, "DATA_SOURCES.md"), encoding="utf-8") as fh:
            doc = fh.read()
        self.assertEqual(doc[doc.index(T.START):doc.index(T.END) + len(T.END)], T.render(registry()))

    def test_the_two_link_only_entries_are_named_by_their_ids_read_from_the_registry(self):
        sources = registry()
        self.assertEqual(T.link_only(sources), ["sse", "usda-ams"])
        text = intro(sources)
        self.assertIn("Every figure shown comes from a source that is free to read.", text)
        self.assertIn("The entries that are only linked (`sse`, `usda-ams`) show no value.", text)
        self.assertNotIn("Every one is free to read", T.render(sources))

    def test_an_entry_that_shows_a_value_is_not_called_link_only_and_a_registry_without_link_only_entries_names_none(self):
        shown = [entry("a"), entry("b", use="Prices of tin; the atlas shows no index value")]
        self.assertEqual(T.link_only(shown), [])
        self.assertEqual(intro(shown), "2 sources are registered. Every figure shown comes from a source that is free to read.")
        mixed = shown + [entry("c", use="Named as a source of rates; no value is stored or shown")]
        self.assertEqual(T.link_only(mixed), ["c"])
        self.assertIn("(`c`) show no value.", intro(mixed))

    def test_a_name_that_starts_with_its_publisher_does_not_name_it_twice_in_a_row(self):
        e = entry("a")
        e["name"], e["publisher"] = "Federal Reserve Bank of Dallas, index of something", "Federal Reserve Bank of Dallas"
        row = [ln for ln in T.render([e]).splitlines() if ln.startswith("| `a`")][0]
        self.assertIn("| [Federal Reserve Bank of Dallas, index of something](https://example.org/a) |", row)
        self.assertEqual(row.count("Federal Reserve Bank of Dallas"), 1)
        # any other entry keeps its publisher after the name
        self.assertIn("[Source b](https://example.org/b), Publisher |", T.render([entry("b")]))
        reg = {s["id"]: s for s in registry()}
        self.assertTrue(reg["dallasfed"]["name"].startswith(reg["dallasfed"]["publisher"]))

    def test_a_link_only_entry_stays_in_the_table(self):
        text = T.render([entry("a"), entry("c", use="no value is stored or shown")])
        self.assertIn("| `c` |", text)


if __name__ == "__main__":
    unittest.main()
