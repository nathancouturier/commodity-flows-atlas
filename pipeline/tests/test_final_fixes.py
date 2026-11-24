"""Fixes of the release review GR2 (package FR1b, data side) and of the documentation review GR3: shares of the tables
whose lines add up to more than the published world total (GR2.5), the rice conversion label (GR2.8), country names in
the notes (GR2.9), no repository path or code name in a text a visitor reads (GR2.11), thousands separators in notes
(GR2.12), the tonnages of the notes under the chokepoint estimates (three significant digits) and the 1 Mt floor of the
estimates (GR3.1).

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_final_fixes.py"
The tests of the data files read the files as the builders last wrote them.
"""
import glob
import json
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities"):
    p = os.path.join(ROOT, "pipeline", sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import build_commodities as B  # noqa: E402
import build_freight as BF  # noqa: E402

DATA = os.path.join(ROOT, "data")


def load(rel):
    return load_path(os.path.join(DATA, rel))


def load_path(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def tables(d):
    """Every Ranked table of a commodity file: (path, table)."""
    out = []

    def walk(o, path):
        if isinstance(o, dict):
            if isinstance(o.get("rows"), list) and "world" in o:
                out.append((path, o))
            for k, v in o.items():
                walk(v, f"{path}/{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}/{i}")

    walk(d, "")
    return out


class LinesOverTheWorldTotal(unittest.TestCase):
    """GR2.5: where the country lines add up to more than the published world total, the shares rest on the sum."""

    def test_ranked_moves_the_shares_to_the_sum(self):
        t = B.ranked([("CHN", 60.0), ("IND", 30.0), ("USA", 12.0)], 2025, "usgs-mcs", "kt", world=100.0, n="USGS")
        self.assertEqual((t["world"], t["worldPublished"]), (102.0, 100.0))
        self.assertIn("102 kt, more than the published world total of 100 kt", t["n"])
        self.assertTrue(t["n"].startswith("USGS; "))
        self.assertAlmostEqual(sum(r["v"] / t["world"] for r in t["rows"]), 1.0)

    def test_the_source_s_other_line_is_one_of_the_lines(self):
        t = B.ranked([("CHN", 60.0), ("IND", 30.0)], 2025, "usgs-mcs", "kt", world=100.0, other=15.0)
        self.assertEqual((t["world"], t["worldPublished"]), (105.0, 100.0))
        t = B.ranked([("CHN", 60.0), ("IND", 30.0)], 2025, "usgs-mcs", "kt", world=100.0, other=10.0)  # equal: unchanged
        self.assertEqual(t["world"], 100.0)
        self.assertNotIn("worldPublished", t)

    def test_a_table_within_the_rounding_of_the_world_total_is_left_alone(self):
        t = B.ranked([("CHN", 60.0), ("IND", 40.02)], 2025, "eia-intl", "kt", world=100.0)  # 0.02% over
        self.assertEqual(t["world"], 100.0)
        self.assertNotIn("worldPublished", t)

    def test_no_table_prints_shares_above_100_percent(self):
        checked = 0
        for p in sorted(glob.glob(os.path.join(DATA, "commodities", "*.json"))):
            d = load_path(p)
            if not isinstance(d, dict):
                continue
            for path, t in tables(d):
                lines = sum(r["v"] for r in t["rows"]) + (t.get("other") or 0)
                where = (os.path.basename(p), path)
                self.assertLessEqual(lines, t["world"] * (1 + B.LINES_OVER_WORLD) + 1e-6, where)
                if "worldPublished" in t and t["world"] > t["worldPublished"]:  # the table's own lines are only the drawn ones
                    self.assertIn("shares are computed on the sum", t["n"], where)
                    checked += 1
        self.assertGreaterEqual(checked, 17)

    def test_the_reviewed_tables(self):
        mn = load("commodities/manganese.json")
        self.assertEqual((mn["reserves"]["world"], mn["reserves"]["worldPublished"]), (1798000, 1700000))
        self.assertEqual(mn["summary"]["reserves"]["v"], 1700000)  # the key figure is the published total
        for cid, sec, pub in (("pgm", "reserves", 76000), ("rare-earths", "reserves", 85000000), ("bauxite", "refinery", 150)):
            t = load(f"commodities/{cid}.json")[sec]
            self.assertEqual(t["worldPublished"], pub, (cid, sec))
            self.assertGreater(t["world"], pub, (cid, sec))


class Labels(unittest.TestCase):
    def test_the_rice_conversion_is_not_an_estimate(self):
        """GR2.8: paddy to milled equivalent at a stated factor is an Atlas conversion; the factor's source stays in the note."""
        d = load("commodities/rice.json")
        f = next(x for x in d["flows"] if (x["o"], x["d"]) == ("KHM", "VNM"))
        self.assertEqual(f["s"], "atlas")
        self.assertNotIn("est", f)
        self.assertTrue(f["n"].startswith("Atlas conversion"), f["n"])
        self.assertIn("USDA PSD milling rate", f["n"])
        # no flow of any page is sourced `atlas` with the words of an estimate and no estimate mark
        for p in glob.glob(os.path.join(DATA, "commodities", "*.json")):
            doc = load_path(p)
            for x in (doc.get("flows") or []) if isinstance(doc, dict) else []:
                if x.get("s") == "atlas" and not x.get("est"):
                    self.assertFalse(x["n"].startswith("Atlas estimate"), (os.path.basename(p), x["o"], x["d"]))
        self.assertIn("marked Atlas conversion", " ".join(d["notes"]))

    def test_notes_name_countries_not_codes(self):
        """GR2.9: "top exporters DR Congo 2.21 Mt, Chile 2.16 Mt", and no pair of codes in a discrepancy."""
        cu = load("commodities/copper.json")
        self.assertTrue(any("top exporters DR Congo 2.21 Mt, Chile 2.16 Mt" in n for n in cu["notes"]), cu["notes"])
        codes = {c["c"] for c in load("countries/index.json")}
        for p in glob.glob(os.path.join(DATA, "commodities", "*.json")):
            doc = load_path(p)
            if not isinstance(doc, dict):
                continue
            for n in (doc.get("notes") or []) + (doc.get("discrepancies") or []):
                for m in re.finditer(r"(?<![A-Za-z0-9/_.-])([A-Z]{3})(?![A-Za-z0-9_-])", n):
                    self.assertNotIn(m.group(1), codes, (os.path.basename(p), n[:120]))


# what a visitor must not read: a repository path or a code name
CODE_WORDS = re.compile(r"data/|pipeline/|\.json\b|\.py\b|\.csv|\.gz\b|vessel_rules|METHODOLOGY\.md|README\.md|\b[a-z]+_[a-z_]+\(\)")


class NoRepositoryInTheTexts(unittest.TestCase):
    """GR2.11: no repository path or code name in a text of the published data (a url is a link, not a text; the
    `access` and `use` of the registry are for DATA_SOURCES.md and are not printed by the site)."""

    def test_published_texts(self):
        bad = []
        for p in sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True) + glob.glob(os.path.join(DATA, "**", "*.geojson"), recursive=True)):
            registry = p.endswith("sources.json")

            def walk(o, path):
                if isinstance(o, str):
                    key = path.rsplit("/", 1)[-1]
                    if key in ("url", "src") or o.startswith("http") or (registry and key in ("access", "use")):
                        return
                    if CODE_WORDS.search(o):
                        bad.append((os.path.relpath(p, DATA), path[-40:], CODE_WORDS.search(o).group(0)))
                elif isinstance(o, dict):
                    for k, v in o.items():
                        walk(v, f"{path}/{k}")
                elif isinstance(o, list):
                    for i, v in enumerate(o):
                        walk(v, f"{path}/{i}")

            walk(load_path(p), "")
        self.assertEqual(bad[:10], [])

    def test_the_atlas_source_label_is_plain(self):
        atlas = next(s for s in load("sources.json") if s["id"] == "atlas")
        self.assertEqual(atlas["name"], "Commodity Flows Atlas estimate (derived; method in the About window)")

    def test_class_notes_use_plain_words(self):
        for c in load("freight/vessel-classes.json"):
            self.assertNotRegex(c["notes"], r"vessel_rules|\(\)|pipeline/", c["id"])


class ChokepointNotes(unittest.TestCase):
    def test_thousands_separators(self):
        """GR2.12: a total of 1,000 or more is printed with the separator, in the route notes and elsewhere."""
        for rel in ("freight/routes.json", "freight/chokepoints.json"):
            txt = json.dumps(load(rel), ensure_ascii=False)
            self.assertEqual(re.findall(r"(?<![\d,.])\d{4,}(?:\.\d+)? Mt\b", txt)[:5], [], rel)
        routes = load("freight/routes.json")
        self.assertTrue(any("of 1,874 Mt seaborne crude oil" in json.dumps(r) for r in routes))

    def test_tonnages_of_the_notes_have_three_significant_digits(self):
        self.assertEqual([BF.mtn(v) for v in (40.64, 126.4, 0.906, 6.272, 1874.37, 9.999, 22.14)],
                         ["40.6 Mt", "126 Mt", "0.906 Mt", "6.27 Mt", "1,874 Mt", "10 Mt", "22.1 Mt"])
        chk = {c["id"]: c for c in load("freight/chokepoints.json")}
        lpg = next(e for e in chk["hormuz"]["estimates"] if e["p"] == "lpg")
        self.assertTrue(lpg["f"]["n"].startswith("at least 40.6 Mt of 126 Mt of seaborne LPG"), lpg["f"]["n"][:80])
        self.assertEqual(lpg["mt"][0], 40.6)  # the page prints the same figure

    def test_the_floor_applies_to_the_up_to_figure_the_page_prints(self):
        """GR3.1: an entry has 2% of its group or 1 Mt, on the "up to" figure after the PortWatch cap. The unit was
        right (Mt against Mt): four entries passed on the uncapped sum and were then capped under the floor."""
        n = passages = 0
        for c in load("freight/chokepoints.json"):
            for e in c.get("estimates") or []:
                up = e.get("hi", e["f"])["v"]  # share of the group, %
                self.assertTrue(e["mt"][1] >= BF.EST_MIN_MT or up >= 100 * BF.EST_MIN_SHARE - 0.05, (c["id"], e["p"], e["mt"], up))
                n += 1
            passages += bool(c.get("estimates"))
        # 490 entries before package L1; its eight groups of minor metals add 108 and its transit rows one (copper
        # concentrate at the Cape of Good Hope), under the same floor; the ten groups of fertilisers and sulphur of package NC1 add 122
        # package NC2: the eight groups of grains, oilseeds and pulses add 101 (822)
        # package NC3: the nine groups of metal bulks add 114 (936)
        # package FNCA: the Saudi and Russian fertiliser and sulphur lanes load at their legacy ports and Turkey's scrap, pig iron and DRI reach its steel works
        # (the Bosphorus entries of sulphur, ammonia and UAN went under the floor; the other estimates moved), and France loads on the Channel: 935
        # package FNCB: the cap of the "up to" figure is applied only below PW_NEAR (85%) of PortWatch's volume of the type, so the estimates that the new dry-bulk
        # groups had taken under the floor are back, and the two fertiliser groups (ammonium nitrate with limestone, two-nutrient compounds) add their own: 968
        self.assertEqual((n, passages), (968, 20))
        # These four were under the floor on the released site because the PortWatch cap had emptied their "up to" figure (Suez and Bab el-Mandeb
        # dry bulk and tankers, Torres Strait tankers: the atlas's "at least" tonnage is above PortWatch's volume there). Since package FNCB the cap is
        # not applied above 85% of PortWatch's volume and the floor reads the figure that is published, so they are published, with their note.
        back = {("suez", "soybeans"), ("bab-el-mandeb", "soybeans"), ("bab-el-mandeb", "soymeal"), ("torres", "palm-oil")}
        have = {(c["id"], e["p"]) for c in load("freight/chokepoints.json") for e in c.get("estimates") or []}
        self.assertEqual(back & have, back)
        self.assertEqual(BF.EST_MIN_MT, 1.0)  # Mt: the pairs table is read in Mt (kt / 1e3)


if __name__ == "__main__":
    unittest.main()
