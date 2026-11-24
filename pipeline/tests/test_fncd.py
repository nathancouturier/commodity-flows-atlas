"""Tests of the last figure and note corrections before the sixth release (package FNCD).

D1  the cap of the "up to" figures at a passage: tests in test_fncb.py B1 (the rule is the one of that point)
D2  sunflower seed: rule 3 applies below the group reference, the exemption is for rows above it
D3  the transit note is printed for the reviewed rows only; the detected others are in QA.md
D4  coke in the customs data: exporters with no coke production in the EIA table, and the K13 wording by group
D5  the USGS annual prices of sulphur and ammonia, and the sweep of the other pages that deny a price
D6  rule 4 on the groups of the three packages: the table of the fourteen groups
D7  the two sentences of METHODOLOGY

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The tests of the data files read the files as the builders last wrote them.
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities", "prices"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

DATA = os.path.join(ROOT, "data")


def load(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return json.load(f)


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class D2SunflowerSeedBelowTheReference(unittest.TestCase):
    @staticmethod
    def frame(o, d, t, usd, year=2024, uv=1300.0):
        import pandas as pd
        rows = [{"year": year, "group": "sunflower-seed", "o": f"E{i:02d}", "d": f"I{i:02d}", "t": 10000.0 + i, "usd": (10000.0 + i) * uv / 1000} for i in range(30)]
        rows.append({"year": year, "group": "sunflower-seed", "o": o, "d": d, "t": t, "usd": usd})
        return pd.DataFrame(rows)

    def row(self, *args, **kw):
        import clean as C
        c = C.clean(self.frame(*args, **kw))
        return c[(c["o"] == args[0]) & (c["d"] == args[1])].iloc[0]

    def test_a_row_far_below_the_reference_is_an_estimate_again(self):
        """GNC2.3 follow-up: 19 kt at under 13 USD/t (Canada to Trinidad and Tobago 2010) and 37 kt at 7 USD/t (Kazakhstan to Russia 2012) are errors
        of tonnage or value that rule 3 corrects; the exemption of FNCB kept them as reported."""
        r = self.row("CAN", "TTO", 19024.0, 240.0, year=2010)  # 12.6 USD/t against a reference of 1,300
        self.assertTrue(r["imputed"])
        self.assertIn("est-gross", r["flag"])
        self.assertNotIn("uv-suspect-t", r["flag"])
        self.assertLess(r["t"], 1000)
        r = self.row("KAZ", "RUS", 37424.0, 262.0, year=2012)  # 7 USD/t
        self.assertTrue(r["imputed"])
        self.assertIn("est-gross", r["flag"])

    def test_a_row_far_above_the_reference_keeps_its_tonnage(self):
        r = self.row("FRA", "RUS", 292.0, 112313.0)  # 385,000 USD/t
        self.assertEqual(r["t"], 292.0)
        self.assertFalse(r["imputed"])
        self.assertIn("uv-suspect-t", r["flag"])

    def test_the_moderate_cases_are_untouched(self):
        """Rule 4 never applied to the group; a row between 1/100 and 100 times the reference is as reported, flagged or not."""
        r = self.row("FRA", "ROU", 3177.0, 38428.0)  # 12,100 USD/t, 9 times the reference
        self.assertFalse(r["imputed"])
        self.assertEqual(r["t"], 3177.0)
        self.assertEqual(r["flag"], "")
        r = self.row("FRA", "ESP", 195364.0, 20000.0)  # 100 USD/t, 1/13 of the reference
        self.assertFalse(r["imputed"])

    def test_the_rows_of_the_cache(self):
        import pandas as pd
        import clean as C
        df = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        c = C.clean(df[df["group"] == "sunflower-seed"]).set_index(["o", "d", "year"])
        for k in (("CAN", "TTO", 2010), ("KAZ", "RUS", 2012), ("TZA", "KEN", 2020), ("UGA", "KEN", 2017)):
            self.assertTrue(c.loc[k, "imputed"], k)
            self.assertIn("est-gross", c.loc[k, "flag"], k)
            self.assertLess(c.loc[k, "t"], 1000, k)
        fr = c.loc[("FRA", "RUS", 2024)]
        self.assertEqual((fr["t"], bool(fr["imputed"])), (292.0, False))
        self.assertIn("uv-suspect-t", fr["flag"])

    def test_the_published_sunflower_seed_world_total_of_2010_and_2012(self):
        """The world series of the page (tonnes of the cleaned cache, 2010 and 2012 without the two kept rows)."""
        import pandas as pd
        import clean as C
        df = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        c = C.clean(df[df["group"] == "sunflower-seed"])
        t = c.groupby("year")["t"].sum() / 1e6
        self.assertAlmostEqual(t[2010], 3.739, delta=0.001)
        self.assertAlmostEqual(t[2012], 4.251, delta=0.001)
        self.assertAlmostEqual(t[2024], 5.326, delta=0.001)

    def test_methodology_and_comment_say_what_the_file_gives(self):
        """The two price levels written in clean.py and METHODOLOGY are those of the cache for 2024: the group's median unit value, the French
        exports as a whole (tonne-weighted, rows the rule kept) and the three French pairs at 10,900 to 13,900 USD/t."""
        import pandas as pd
        import clean as C
        df = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        c = C.clean(df[df["group"] == "sunflower-seed"])
        y = c[c["year"] == 2024]
        self.assertEqual(round(float(y["uv"].iloc[0]) * 1000), 1289)
        fr = y[(y["o"] == "FRA") & ~y["imputed"]]
        self.assertEqual(round(float(fr["usd"].sum() * 1000 / fr["t"].sum())), 1021)
        hi = fr[fr["d"].isin(["ROU", "HUN", "UKR"])]
        self.assertEqual(sorted(round(float(v), -2) for v in hi["uvp"]), [10900, 12100, 13900])
        meth, src = read("METHODOLOGY.md"), read("pipeline", "trade", "clean.py")
        for text in (meth, src):
            for n in ("1,289", "1,021", "10,900", "13,900"):
                self.assertIn(n, text)
        self.assertNotIn("about USD 12,000 a tonne", meth + src)


class D3TransitNoteOnReviewedRowsOnly(unittest.TestCase):
    PHRASE = "may be cargo in transit to a port"

    def test_the_reviewed_table_is_the_two_mozambique_rows(self):
        import metals as MET
        self.assertEqual(set(MET.TRANSIT_REVIEWED), {("chromium", "imports", "MOZ"), ("ferro-alloys", "imports", "MOZ")})
        for why in MET.TRANSIT_REVIEWED.values():
            for clause in ("overland from South Africa", "first producer", "Mozambique has no line in that table", "exports", "next to nothing"):
                self.assertIn(clause, why)
            self.assertNotRegex(why, r"\d")

    def test_the_note_is_on_the_two_rows_their_pages_and_their_profile_lines_and_nowhere_else(self):
        import glob
        where = []
        for f in sorted(glob.glob(os.path.join(DATA, "commodities", "*.json"))):
            if f.endswith(("index.json", "companies.json")):
                continue
            text = json.dumps(load(f))
            name = os.path.basename(f)[:-5]
            d = load(f)
            tabs = [(k, d[k]) for k in ("exports", "imports") if isinstance(d.get(k), dict)] + [(x["key"], x["table"]) for x in d.get("extra") or []]
            for key, t in tabs:
                for r in t.get("rows", []):
                    if self.PHRASE in (r.get("n") or ""):
                        where.append((name, key, r["c"], "row"))
            for n in d.get("notes", []):
                if self.PHRASE in n:
                    where.append((name, "notes", n.split(" ")[0], "page"))
            self.assertEqual(text.count(self.PHRASE), sum(1 for w in where if w[0] == name) if name in ("chromium", "ferro-alloys") else 0, name)
        self.assertEqual(sorted(where), [("chromium", "imports", "MOZ", "row"), ("chromium", "notes", "Mozambique", "page"),
                                         ("ferro-alloys", "imports", "MOZ", "row"), ("ferro-alloys", "notes", "Mozambique", "page")])
        hits = []
        for f in sorted(glob.glob(os.path.join(DATA, "countries", "profiles", "*.json"))):
            p = load(f)
            for side in ("exports", "imports"):
                for e in p.get(side) or []:
                    if self.PHRASE in (e.get("n") or ""):
                        hits.append((os.path.basename(f)[:-5], side, e["k"]))
        self.assertEqual(sorted(hits), [("MOZ", "imports", "chromium"), ("MOZ", "imports", "ferro-alloys")])

    def test_the_two_rows_say_why(self):
        for page, key in (("chromium", "imports"), ("ferro-alloys", "imports")):
            d = load(DATA, "commodities", page + ".json")
            r = next(x for x in d[key]["rows"] if x["c"] == "MOZ")
            self.assertIn("a possible reading, not established here", r["n"])
            self.assertIn("comes overland from South Africa, the first producer", r["n"])
            self.assertTrue(any(self.PHRASE in n and "comes overland from South Africa" in n for n in d["notes"]), page)

    def test_every_clause_of_the_reason_holds_in_the_files(self):
        """Each clause, read in the built files: South Africa is the first row of the USGS production table of the Chromium page; Mozambique has no
        line in it (nor in the reserves); the pairs files record the imports of both products from South Africa overland; Mozambique's exports of
        both are under 1% of the world's and under 2% of its own imports."""
        cr = load(DATA, "commodities", "chromium.json")
        self.assertEqual(cr["production"]["rows"][0]["c"], "ZAF")
        self.assertEqual(cr["production"]["s"], "usgs-mcs")
        self.assertNotIn("MOZ", [r["c"] for r in cr["production"]["rows"]])
        self.assertNotIn("MOZ", [r["c"] for r in cr["reserves"]["rows"]])
        fa = load(DATA, "commodities", "ferro-alloys.json")
        self.assertNotIn("production", fa)  # the second clause is about the table of the Chromium page
        for page, group in (("chromium", "chromium-ore"), ("ferro-alloys", "ferro-chromium")):
            d = load(DATA, "commodities", page + ".json")
            imp = next(r for r in d["imports"]["rows"] if r["c"] == "MOZ")["v"]
            exp = next((r["v"] for r in d["exports"]["rows"] if r["c"] == "MOZ"), 0.0)
            self.assertLess(exp / d["exports"]["world"], 0.01, page)
            self.assertLess(exp / imp, 0.02, page)
            pairs = load(DATA, "freight", "pairs", group + ".json")
            rows = [dict(zip(pairs["cols"], r)) for r in pairs["rows"] if r[1] == "MOZ"]
            tot = sum(r["kt"] for r in rows)
            zaf = sum(r["kt"] for r in rows if r["o"] == "ZAF" and r["m"] == 3)
            self.assertGreater(zaf / tot, 0.9, page)

    def test_the_detected_rows_outside_the_table_are_in_qa(self):
        qa = read("pipeline", "commodities", "QA.md")
        sec = qa[qa.index("## Importers in transit"):]
        sec = sec[:sec.index("\n## ", 5)]
        for key in ("pig-iron/dri-imports/SAU", "phosphate/map-imports/CAN"):
            line = next(x for x in sec.splitlines() if x.startswith(f"- {key}:"))
            self.assertIn("detected, no note", line)
            self.assertIn("overland delivery to a neighbour that uses the product is the plain reading", line)
        for key in ("chromium/imports/MOZ", "ferro-alloys/imports/MOZ"):
            self.assertIn("note printed (reviewed row)", next(x for x in sec.splitlines() if x.startswith(f"- {key}:")))

    def test_a_detected_row_outside_the_table_gets_no_note(self):
        import tempfile
        import metals as MET
        from test_fncc import FakeBuilder
        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, "freight", "pairs"))
        with open(os.path.join(tmp, "freight", "pairs", "chromium-ore.json"), "w") as f:
            json.dump({"cols": ["o", "d", "kt", "m"], "rows": [["ZAF", "MOZ", 8000, 3], ["OMN", "SAU", 5000, 3]]}, f)
        B = FakeBuilder(tmp)
        B.cname = lambda iso: {"MOZ": "Mozambique", "SAU": "Saudi Arabia", "OMN": "Oman"}.get(iso, iso)
        def table(rows):
            return {"s": "baci", "u": "Mt", "world": sum(v for _, v in rows), "rows": [{"c": c, "v": v} for c, v in rows]}
        d = {"imports": table([("CHN", 15.0), ("SAU", 8.0), ("MOZ", 7.0)]), "exports": table([("ZAF", 23.0), ("TUR", 1.4)]), "production": {"rows": []}}
        self.assertEqual(MET.transit_notes(B, {"chromium": d}), ["chromium/imports/MOZ"])
        self.assertEqual([(k, noted) for k, _, noted in MET.TRANSIT_REPORT], [("chromium/imports/SAU", False), ("chromium/imports/MOZ", True)])
        self.assertNotIn("n", d["imports"]["rows"][1])  # Saudi Arabia: detected, no note
        self.assertIn("n", d["imports"]["rows"][2])
        self.assertEqual(len(d["notes"]), 1)
