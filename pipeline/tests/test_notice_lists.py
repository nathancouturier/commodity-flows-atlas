"""The generated lists of NOTICE.md follow the data: pipeline/common/notice_lists.py would rewrite nothing."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "common"))
import notice_lists as NL  # noqa: E402


class NoticeLists(unittest.TestCase):
    def test_notice_is_up_to_date(self):
        text = open(NL.DOC, encoding="utf-8").read()
        self.assertEqual(NL.render(text), text, "NOTICE.md is out of date: run pipeline/common/notice_lists.py")

    def test_every_block_has_its_markers_once(self):
        text = open(NL.DOC, encoding="utf-8").read()
        for name in NL.BLOCKS:
            self.assertEqual(text.count(f"<!-- {name}:start -->"), 1, name)
            self.assertEqual(text.count(f"<!-- {name}:end -->"), 1, name)

    def test_a_feature_that_names_wikipedia_is_listed_by_id(self):
        block = NL.wikipedia_infra()
        for name, pr in NL.features():
            if pr.get("s") != "wikipedia" and "wikipedia" in str(pr).lower():
                self.assertIn(f"`{pr['id']}`", block)

    def test_osm_names_are_listed(self):
        block = NL.osm_points()
        for name, pr in NL.features():
            if "OpenStreetMap" in str(pr):
                self.assertIn(pr["name"].split(" (")[0], block)


if __name__ == "__main__":
    unittest.main()
