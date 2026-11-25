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
            # the exports of the country are not in the reason since FNCF: the note computes them from the row of the exporters table (test_fncf.py F9)
            for clause in ("overland from South Africa", "first producer", "Mozambique has no line in that table"):
                self.assertIn(clause, why)
            self.assertNotIn("next to nothing", why)
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


class D6RuleFourOnTheHomogeneousGroups(unittest.TestCase):
    """The table of the fourteen groups that the three packages called homogeneous, recomputed from the cache (FNCD, D6)."""
    GROUPS = ("potassium-sulphate monoammonium-phosphate superphosphates ammonia ammonium-nitrate uan ammonium-sulphate barley sorghum "
              "sunflower-oil rapeseed-oil sunflower-meal rapeseed-meal coke").split()
    _cache = {}

    @classmethod
    def table(cls):
        """{group: (rows that rule 4 re-estimates, tonnes it adds or removes, largest change of a world total in %, steady rows, tonnes of the
        steady rows)} with rule 4 on for all fourteen groups, and the rows themselves."""
        if "t" in cls._cache:
            return cls._cache["t"]
        import pandas as pd
        import clean as C
        df = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        df = df[df["group"].isin(cls.GROUPS)]
        # rule 4 on for all fourteen groups, as before this package; the one row of KEEP_REPORTED that only rule 4 had reached (sunflower oil
        # Ukraine to Greece 2003, removed from the table because the group left the set) is held as it was
        saved, rows_saved, keep_saved = set(C.HOMOGENEOUS), dict(C.ESTIMATE_ROWS), dict(C.KEEP_REPORTED)
        try:
            C.HOMOGENEOUS.update(cls.GROUPS)
            C.ESTIMATE_ROWS.clear()
            C.KEEP_REPORTED[("sunflower-oil", "UKR", "GRC", 2003)] = "held as before FNCD"
            c = C.clean(df)
        finally:
            C.HOMOGENEOUS.clear()
            C.HOMOGENEOUS.update(saved)
            C.ESTIMATE_ROWS.update(rows_saved)
            C.KEEP_REPORTED.clear()
            C.KEEP_REPORTED.update(keep_saved)
        out, rows = {}, []
        for g in cls.GROUPS:
            x = c[c["group"] == g]
            est = x[x["flag"].str.contains("est-uv")]
            world = x.groupby("year")["t"].sum()
            delta = (est["t"] - est["t0"]).groupby(est["year"]).sum()
            off = world.reindex(delta.index) - delta
            worst = float(((delta.abs() / off) * 100).max()) if len(delta) else 0.0
            steady = []
            for r in est.itertuples():
                other = x[(x["o"] == r.o) & (x["d"] == r.d) & (x["year"] != r.year) & (x["t0"] > 0) & (x["usd"] > 0)]
                n = int((other["uvr"] > 3).sum()) if r.uvr > 3 else int((other["uvr"] < 1 / 3).sum())
                if n >= 3:
                    steady.append((r.o, r.d, int(r.year)))
                rows.append((g, r.o, r.d, int(r.year), float(r.t0), float(r.t), n >= 3))
            moved = float((est["t"] - est["t0"]).abs().sum())
            st = float(sum(abs(r[5] - r[4]) for r in rows if r[0] == g and r[6]))
            out[g] = (len(est), moved, worst, len(steady), st)
        cls._cache["t"] = (out, rows)
        return cls._cache["t"]

    def test_the_criterion_takes_coke_and_sunflower_oil_out_and_keeps_the_twelve_others(self):
        import clean as C
        out, _ = self.table()
        leaves = {g for g, (n, moved, worst, ns, st) in out.items() if moved and st > 0.1 * moved}
        self.assertEqual(leaves, {"coke", "sunflower-oil"})
        for g in self.GROUPS:
            self.assertEqual(g in C.HOMOGENEOUS, g not in leaves, g)
        # the twelve that stay have no steady pair at all, so nothing is added to KEEP_REPORTED for them
        for g in set(self.GROUPS) - leaves:
            self.assertEqual(out[g][3], 0, g)
        self.assertEqual({g: v[0] for g, v in out.items() if v[0]},
                         {"potassium-sulphate": 1, "uan": 1, "ammonium-sulphate": 1, "sorghum": 2, "sunflower-oil": 1, "rapeseed-meal": 2, "coke": 7})
        # package FNCF: Mozambique's coke (four of the eleven rows of FNCD, 92% of the tonnes) is out of the frame (clean.DROP); the three rows of China to the
        # United States, whose pair declares its own price level in at least three other years, still carry a third of the tonnes that rule 4 would move
        self.assertAlmostEqual(out["coke"][4] / out["coke"][1], 0.332, places=2)
        self.assertAlmostEqual(out["sunflower-oil"][4] / out["sunflower-oil"][1], 1.0, places=3)
        self.assertLess(out["coke"][2], 10.0)
        self.assertLess(max(v[2] for g, v in out.items() if g != "coke"), 8.0)

    def test_the_rows_that_change_are_those_of_coke_and_sunflower_oil_and_the_four_of_sunflower_seed(self):
        """Published tonnage against the state after FNCB: 11 rows of coke and sunflower oil go back to the reported tonnage, the 4 rows of
        sunflower seed (D2) go to the rule-3 estimate; the Mozambique rows of coke (2021, 2022, 2023 and the row of 2016 among them) are out of the frame
        since FNCF (clean.DROP) and no longer on the list."""
        import pandas as pd
        import clean as C
        df = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        c = C.clean(df[df["group"].isin(["coke", "sunflower-oil"])]).set_index(["group", "o", "d", "year"])
        back = [("coke", "BEL", "FRA", 2004), ("coke", "CHN", "BRA", 2009), ("coke", "CHN", "IND", 2006), ("coke", "CHN", "IND", 2007),
                ("coke", "CHN", "USA", 2002), ("coke", "CHN", "USA", 2003), ("coke", "CHN", "USA", 2005),
                ("sunflower-oil", "UKR", "NPL", 2021), ("sunflower-oil", "UKR", "GRC", 2003)]
        for k in back:
            self.assertEqual(c.loc[k, "t"], c.loc[k, "t0"], k)
            self.assertFalse(c.loc[k, "imputed"], k)
        self.assertNotIn("MOZ", set(c.reset_index()["o"][c.reset_index()["group"] == "coke"]))  # FNCF: all of Mozambique's coke is out of the frame
        self.assertEqual(C.ESTIMATE_ROWS, {})

    def test_a_listed_row_is_estimated_in_a_group_outside_the_set_and_its_neighbours_are_not(self):
        """The table is empty since FNCF (Mozambique's coke is dropped): the mechanism is tried with a row of another origin."""
        import pandas as pd
        import clean as C
        rows = [{"year": 2016, "group": "coke", "o": f"E{i:02d}", "d": f"I{i:02d}", "t": 100000.0 + i, "usd": 30000.0 + i} for i in range(40)]
        rows.append({"year": 2016, "group": "coke", "o": "ZZZ", "d": "IND", "t": 64992713.0, "usd": 245257.0})
        rows.append({"year": 2016, "group": "coke", "o": "ZZZ", "d": "CHN", "t": 64992713.0, "usd": 245257.0})  # the same row of another pair
        C.ESTIMATE_ROWS[("coke", "ZZZ", "IND", 2016)] = "a test row"
        try:
            c = C.clean(pd.DataFrame(rows))
        finally:
            del C.ESTIMATE_ROWS[("coke", "ZZZ", "IND", 2016)]
        a = c[(c["o"] == "ZZZ") & (c["d"] == "IND")].iloc[0]
        b = c[(c["o"] == "ZZZ") & (c["d"] == "CHN")].iloc[0]
        self.assertTrue(a["imputed"] and "est-uv" in a["flag"])
        self.assertFalse(b["imputed"])
        self.assertEqual(b["t"], 64992713.0)

    def test_methodology_and_comments_say_the_same(self):
        meth = read("METHODOLOGY.md")
        src = read("pipeline", "trade", "clean.py")
        for text in (meth, src):
            self.assertIn("ESTIMATE_ROWS", text)
        self.assertIn("23 rows", src)
        self.assertIn("92%", src)
        self.assertNotIn('    "coke",\n}', src)


class D7TwoSentencesOfMethodology(unittest.TestCase):
    def test_the_annual_workbook_is_read_as_published_and_the_sentence_is_tied_to_its_cover_sheet(self):
        meth = read("METHODOLOGY.md")
        self.assertIn("last saved by the publisher on 3 November 2026", meth)
        self.assertIn("reads the workbook as\n  published", meth)
        path = os.path.join(ROOT, "raw", "worldbank", "CMO-Historical-Data-Annual.xlsx")
        if not os.path.exists(path):
            self.skipTest("raw/ is not tracked in git: the workbook is not on this machine")
        import zipfile
        import openpyxl
        with zipfile.ZipFile(path) as z:
            self.assertIn("2026-11-03", z.read("docProps/core.xml").decode("utf-8"))
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        cover = " ".join(str(c) for r in wb["Cover"].iter_rows(values_only=True) for c in r if c)
        self.assertIn("exact comparison against", cover)  # "a comparison of the real annual prices against an earlier copy"
        self.assertIn("9 remaining exact value mismatches", cover)  # "nine values that differ"
        self.assertIn("nine values that differ", meth)

    def test_other_ferro_alloys_sentence_is_the_cleaned_frame(self):
        """0.58 Mt over 396 sea and transit pairs (0.69 Mt over 483 pairs in all modes), from the cleaned 2024 frame with the mode rule of the other
        ferro-alloys (the group has no lanes and no pairs file); FNCC read 393 pairs in the uncleaned cache."""
        import pandas as pd
        import clean as C
        import modes as MD
        df = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        x = C.clean(df)
        x = x[(x["group"] == "ferro-alloys-other") & (x["year"] == 2024)]
        kinds = x.apply(lambda r: (lambda m: m.kind if m else None)(MD.mode_of(r["o"], r["d"], "ferro-silicon")), axis=1)
        sea = x[kinds.isin(["sea", "transit"])]
        self.assertEqual((len(sea), round(sea["t"].sum() / 1e6, 2), len(x), round(x["t"].sum() / 1e6, 2)), (396, 0.58, 483, 0.69))
        meth, lanes = read("METHODOLOGY.md"), read("pipeline", "freight", "build_lanes.py")
        self.assertIn("0.58 Mt by sea or via a transit port over 396 pairs, of 0.69 Mt over 483 pairs in all modes", meth)
        self.assertIn("0.58 Mt over 396 sea and transit pairs", lanes)
        self.assertNotIn("0.6 Mt by sea over 396 pairs", meth)


class D4CokeExportersWithoutProduction(unittest.TestCase):
    def caveats(self):
        return load(DATA, "freight", "caveats.json")

    def test_k14_finds_zimbabwe_in_the_customs_table_and_only_it(self):
        """The exporters of the customs coke table with at least 1% of its world total that have no coke production in the EIA table of the page.
        FNCD found Mozambique and Zimbabwe; since FNCF Mozambique's coke is out of the frame (clean.DROP) and K14 finds Zimbabwe only."""
        met = load(DATA, "commodities", "met-coal.json")
        ex = {x["key"]: x["table"] for x in met["extra"]}
        cust, prod = ex["coke-customs-exports"], ex["coke-production"]
        have = {r["c"] for r in prod["rows"]}
        big = [r["c"] for r in cust["rows"] if r["v"] >= 0.01 * cust["world"]]
        self.assertEqual([c for c in big if c not in have], ["ZWE"])
        first15 = [r["c"] for r in cust["rows"][:15]]
        self.assertEqual([c for c in first15 if c not in have], ["ZWE"])  # every other exporter of the first fifteen has production
        self.assertNotIn("MOZ", [r["c"] for r in cust["rows"]])
        found = [r for r in load(ROOT, "pipeline", "cache", "trade_checks.json")["findings"] if r["check"] == "K14"]
        self.assertEqual(sorted(r["o"] for r in found), ["ZWE"])
        for r in found:
            row = next(x for x in cust["rows"] if x["c"] == r["o"])
            self.assertAlmostEqual(r["value"], row["v"], places=2)
            self.assertAlmostEqual(r["share"], row["v"] / cust["world"], places=3)
            self.assertGreaterEqual(r["share"], 0.01)

    def test_the_file_supports_no_production_only_where_the_series_exists(self):
        """A country with no series in the EIA file is not reported: the file cannot support "no production" for it."""
        import pandas as pd
        import checks as K
        df = pd.DataFrame([{"year": 2024, "group": "coke", "o": o, "d": "IND", "t": t, "usd": t * 0.3, "imputed": False}
                           for o, t in (("AAA", 5e6), ("BBB", 4e6), ("CCC", 3e6), ("DDD", 1e6), ("EEE", 2e6))])
        series = {"WORL": {2025: 100.0}, "AAA": {2025: 50.0}, "BBB": {2025: 0.0, 2020: 40.0}, "CCC": {2025: 0.0}, "EEE": {2025: 0.0, 2023: 5.0, 2022: 399.0, 2021: 330.0}}  # DDD: no series at all
        eia = {("21-1", "MT"): series, ("130-1", "MT"): {"CCC": {2025: 1200.0}}, ("130-4", "MT"): {"CCC": {2025: 800.0}}}
        out = K.k14(df, 2024, eia=eia)
        self.assertEqual([r["o"] for r in out], ["BBB", "CCC", "EEE"])
        self.assertEqual((out[0]["lastYear"], out[0]["lastKt"], out[0]["coalKt"]), (2020, 40.0, 0.0))
        self.assertEqual((out[1]["lastYear"], out[1]["coalKt"], out[1]["coalExportKt"]), (None, 1200.0, 800.0))
        # FNCI (GV8A.3): the year with production before the last one is in the finding (a series that falls from 399 kt to 5 kt and to nothing)
        self.assertEqual((out[0]["priorYear"], out[0]["priorKt"]), (None, None))
        self.assertEqual((out[1]["priorYear"], out[1]["priorKt"]), (None, None))
        self.assertEqual((out[2]["lastYear"], out[2]["lastKt"], out[2]["priorYear"], out[2]["priorKt"]), (2023, 5.0, 2022, 399.0))

    def test_the_wording_depends_on_what_the_series_has_before(self):
        """FNCI (GV8A.3): a series with production in an earlier year gives two readings with the same weight and the last two years with production;
        a series that reads 0 in every year keeps the wording of the second reading only; one year with production quotes that year."""
        import caveats as CV
        base = {"group": "coke", "o": "ZWE", "year": 2024, "value": 0.893, "share": 0.0271, "eiaYear": 2025, "firstYear": 1980, "coalKt": 1248.5, "coalExportKt": 0.0}
        two = CV._no_production(dict(base, lastYear=2023, lastKt=4.96, priorYear=2022, priorKt=398.64))
        self.assertIn("(its series reads 0 in 2025, and its last two years with production are 399 kt in 2022 and 5 kt in 2023; EIA International Energy Data)", two)
        self.assertIn("a series that falls from 399 kt to 5 kt and then to nothing may be a series that stopped", two)
        self.assertEqual(two.count("not established"), 0)
        self.assertTrue(two.endswith("Neither is established here."))
        one = CV._no_production(dict(base, lastYear=2020, lastKt=40.0, priorYear=None, priorKt=None))
        self.assertIn("its last year with production is 40 kt in 2020", one)
        self.assertIn("a series that ends at 40 kt and then reads nothing may be a series that stopped", one)
        none = CV._no_production(dict(base, lastYear=None, lastKt=None, priorYear=None, priorKt=None))
        self.assertIn("its series reads 0 in every year from 1980 to 2025", none)
        self.assertTrue(none.endswith("a possible reading, not established here."))
        self.assertNotIn("Two readings fit", none)
        for t in (two, one, none):
            self.assertIn("metallurgical coal for instance", t)

    def test_the_finding_of_zimbabwe_carries_the_two_years_and_they_are_the_series_of_the_file(self):
        f = next(r for r in load(ROOT, "pipeline", "cache", "trade_checks.json")["findings"] if r["check"] == "K14")
        self.assertEqual((f["o"], f["lastYear"], f["priorYear"]), ("ZWE", 2023, 2022))
        self.assertAlmostEqual(f["lastKt"], 5.0, delta=0.05)
        self.assertAlmostEqual(f["priorKt"], 398.6, delta=0.05)
        eia = os.path.join(ROOT, "raw", "eia", "INTL.txt")
        if os.path.exists(eia):
            with open(eia, encoding="utf-8") as fh:
                for line in fh:
                    if '"INTL.21-1-ZWE-MT.A"' in line:
                        ser = {int(y): v for y, v in json.loads(line)["data"] if v}
                        pos = sorted(ser)
                        self.assertEqual((pos[-2], round(ser[pos[-2]], 1), pos[-1], round(ser[pos[-1]], 1)), (f["priorYear"], f["priorKt"], f["lastYear"], f["lastKt"]))
                        break
                else:
                    self.fail("series 21-1 of Zimbabwe not in the file")

    def test_the_row_note_the_page_note_the_lane_caveat_and_the_country_page_say_it(self):
        cv = self.caveats()
        met = load(DATA, "commodities", "met-coal.json")
        cust = next(x["table"] for x in met["extra"] if x["key"] == "coke-customs-exports")
        self.assertNotIn("nop-coke-MOZ", cv)
        for iso, coal in (("ZWE", "give Zimbabwe a production of"),):
            e = cv[f"nop-coke-{iso}"]
            self.assertEqual((e["kind"], e["group"], e["o"], e["d"]), ("no-production", "coke", iso, None))
            for part in ("Customs data record", "of coke and semi-coke exported from", "(CEPII BACI, HS 2704)", "gives", "no coke production in 2025",
                         "EIA International Energy Data", "another product declared under the coke code", coal, "established here"):
                self.assertIn(part, e["text"], (iso, part))
            row = next(r for r in cust["rows"] if r["c"] == iso)
            self.assertIn(e["text"], row["n"])
            self.assertIn(e["text"], met["notes"])
            prof = load(DATA, "countries", "profiles", iso + ".json")
            self.assertTrue(any(g["id"] == f"nop-coke-{iso}" for g in prof["gaps"]), iso)
        t = cv["nop-coke-ZWE"]["text"]
        self.assertNotIn("last reads 5 kt in 2023", t)
        # FNCI (GV8A.3): the last two years with production, the two readings with the same weight, and the coal of the series 130-1 named for what it is
        self.assertIn("its last two years with production are 399 kt in 2022 and 5 kt in 2023", t)
        self.assertIn("Two readings fit, with the same weight: the EIA series no longer covers the country's coke plants (a series that falls from 399 kt to 5 kt and then to nothing may be a series that stopped), "
                      "or part of these tonnes is another product declared under the coke code, metallurgical coal for instance", t)
        self.assertTrue(t.endswith("Neither is established here."))
        self.assertIn("1.25 Mt in 2025 and no exports", t)
        self.assertNotIn(", coal for instance", t)
        self.assertIn("metallurgical coal for instance", t)
        # no other exporter of the table has the note
        notes = [r["c"] for r in cust["rows"] if "no coke production" in (r.get("n") or "")]
        self.assertEqual(sorted(notes), ["ZWE"])

    def test_the_lanes_of_the_exporters_carry_the_caveat(self):
        """Mozambique has no coke lane since FNCF (its coke is out of the frame). Zimbabwe has none either: its tonnes go overland (South Africa,
        Zambia, Congo DR), so its note is on the page and the country page."""
        lanes = load(DATA, "freight", "lanes", "coke.json")["lanes"]
        self.assertEqual([ln for ln in lanes if ln["o"] in ("MOZ", "ZWE")], [])
        # no lane of the group carries the caveat of an origin without production
        self.assertFalse(any((ln.get("caveat") or "").startswith("nop-") for ln in lanes))

    def test_the_wording_of_the_low_unit_value_caveat_depends_on_the_group(self):
        cv = self.caveats()
        import caveats as CV
        # the one coke pair of the file was Mozambique to the United Arab Emirates, out of the frame since FNCF: the wording is tried on a made-up finding
        coke = CV._low_unit_value({"group": "coke", "text": "Coke from A to B: 1 Mt", "year": 2024, "unitValue": 70.0})
        dri, alu = cv["uv-dri-DZA-DEU"]["text"], cv["uv-aluminium-USA-MYS"]["text"]
        self.assertIn("Material priced like coal, or another cheaper product, declared under this code is a plausible cause; it is not established here.", coke)
        self.assertNotIn("scrap or alloy", coke)
        self.assertIn("Material priced like iron ore or scrap, or another cheaper product, declared under this code", dri)
        self.assertNotIn("scrap or alloy", dri)
        self.assertIn("Material priced like scrap or alloy, or another cheaper product, declared under this code", alu)  # the groups that had the words keep them
        for cid, e in cv.items():
            if cid.startswith("uv-") and e["group"] not in ("coke", "pig-iron", "dri"):
                self.assertIn("priced like scrap or alloy", e["text"], cid)


class D5UsgsPricesOfSulphurAmmoniaAndFerrosilicon(unittest.TestCase):
    NEW = {
        "usgs-sulphur-a": ("sulphur", "Sulfur", "Price, average unit value, free on board, mine and (or) plant, dollars per metric ton of elemental sulfur", "USD/t"),
        "usgs-ammonia-a": ("urea", "Nitrogen (Fixed)—Ammonia", "Price, average, free on board Gulf Coast, dollars per short ton", "USD/short ton"),
        "usgs-ferrosilicon-75-a": ("ferro-alloys", "Silicon", "Price, average, cents per pound of silicon: Ferrosilicon, 75% silicon", "US cents/lb"),
    }

    def test_each_series_is_its_rows_in_the_file_with_the_files_unit_and_basis(self):
        import csv
        import glob
        files = sorted(glob.glob(os.path.join(ROOT, "raw", "usgs", "MCS*_Commodities_Data.csv")))
        if not files:
            self.skipTest("raw/ is not tracked in git: the USGS file is not on this machine")
        with open(files[-1], encoding="cp1252", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["Statistics"] == "Price"]
        idx = {m["id"]: m for m in load(DATA, "prices", "index.json")}
        for sid, (page, com, detail, unit) in self.NEW.items():
            with self.subTest(sid):
                mine = [r for r in rows if r["Commodity"] == com and r["Statistics_detail"].startswith(detail) and r["Value"] != "NA"]
                self.assertEqual({r["Country"] for r in mine}, {"United States"})
                by = {int(r["Year"]): float(r["Value"].replace(",", "")) for r in mine}
                self.assertEqual(sorted(by), [2021, 2022, 2023, 2024, 2025])
                self.assertEqual(load(DATA, "prices", sid + ".json")["v"], [by[y] for y in sorted(by)])  # each series equals its rows, no conversion
                m = idx[sid]
                self.assertEqual((m["k"], m["unit"], m["freq"], m["s"], m["start"], m["end"]), (page, unit, "A", "usgs-mcs", "2021", "2025"))
                self.assertTrue(m["basis"].startswith(mine[0]["Statistics_detail"].rstrip(".")))
                self.assertEqual(m["est"], [["2025-01", "2025-12"]])  # estimated for 2025 only
                self.assertTrue(any(w in m["name"] for w in ("US", "United States")) and "annual" in m["name"])
        self.assertIn("Source: Green Markets.", idx["usgs-ammonia-a"]["basis"])
        self.assertIn("short ton", idx["usgs-ammonia-a"]["basis"])
        self.assertEqual([v for v in load(DATA, "prices", "usgs-ammonia-a.json")["v"]], [578.0, 1070.0, 470.0, 440.0, 450.0])
        self.assertIn("Source: S&P Global Platts Metals Week", idx["usgs-ferrosilicon-75-a"]["basis"])

    def test_the_pages_no_longer_deny_the_prices_and_the_series_open_as_before(self):
        import build_prices as P
        sul = " ".join(load(DATA, "commodities", "sulphur.json")["notes"])
        self.assertNotIn("No free price series", sul)
        self.assertNotIn("no other free one was found", sul)
        self.assertIn("USGS annual average unit value of elemental sulphur", sul)
        ure = " ".join(load(DATA, "commodities", "urea.json")["notes"])
        self.assertIn("ammonia: the annual average, free on board Gulf Coast, in US dollars per short ton", ure)
        fer = " ".join(load(DATA, "commodities", "ferro-alloys.json")["notes"])
        self.assertIn("75% ferrosilicon", fer)
        prices = read("web", "src", "lib", "prices.ts")
        self.assertIn("No free series for ammonium nitrate, UAN or ammonium sulphate.", prices)
        self.assertNotIn("No free series for ammonia", prices)
        self.assertRegex(prices, r"sulphur: 'Annual average price of elemental sulphur[^']*USGS")
        fig = load(DATA, "prices", "figures.json")
        self.assertEqual(fig["sulphur"]["id"], "usgs-sulphur-a")
        self.assertEqual(fig["urea"]["id"], "urea-m")  # the monthly urea stays the key figure of its page
        self.assertEqual(fig["ferro-alloys"]["id"], "usgs-ferrochromium-a")
        meta = [m for m in load(DATA, "prices", "index.json")]
        self.assertEqual(P.opening_problems(meta), [])

    def test_the_sweep_the_other_pages_that_say_no_free_price_keep_their_wording_with_the_reason(self):
        """Pages that still print 'No free price series': pig iron and direct-reduced iron. The USGS file has no price row of either (its Iron and Steel
        row is a producer price index of steel mill products, not a price of pig iron or direct-reduced iron). The other pages without a series (uranium,
        steel, metallurgical coal, pulses, NPK) say so in their own words, and the file has no row for their product."""
        import csv
        import glob
        deny = []
        for p in glob.glob(os.path.join(DATA, "commodities", "*.json")):
            if p.endswith(("index.json", "companies.json")):
                continue
            d = load(p)
            if any("No free price series" in n for n in d.get("notes", [])):
                deny.append(os.path.basename(p)[:-5])
        self.assertEqual(deny, ["pig-iron"])
        files = sorted(glob.glob(os.path.join(ROOT, "raw", "usgs", "MCS*_Commodities_Data.csv")))
        if not files:
            self.skipTest("raw/ is not tracked in git: the USGS file is not on this machine")
        with open(files[-1], encoding="cp1252", newline="") as f:
            price = {(r["Commodity"], r["Statistics_detail"]) for r in csv.DictReader(f) if r["Statistics"] == "Price"}
        steel = [d for c, d in price if c == "Iron And Steel"]
        self.assertEqual(steel, ["Producer price index, steel mill products (1982=100)"])
        names = {c.lower() for c, _ in price}
        for product in ("pig iron", "direct-reduced iron", "uranium", "pulses", "npk", "coke", "peas", "lentils", "metallurgical coal"):
            self.assertNotIn(product, names)
        # the potash price rows are of K2O in all products (MOP, SOP, SOPM): not the price of potassium sulphate, which the page keeps saying has none
        self.assertTrue(any(c == "Potash" and "All products" in d for c, d in price))
        self.assertIn("No free series for potassium sulphate", read("web", "src", "lib", "prices.ts"))


class D4Documentation(unittest.TestCase):
    def test_methodology_names_k14_with_the_figures_of_the_files(self):
        meth = read("METHODOLOGY.md")
        found = {r["o"]: r for r in load(ROOT, "pipeline", "cache", "trade_checks.json")["findings"] if r["check"] == "K14"}
        # FNCD found Mozambique and Zimbabwe; since FNCF Mozambique's coke is dropped by rule 5 and the check finds Zimbabwe only (the Mozambique figure of the
        # sentence is the history of the check, 1.63 Mt of the customs file, and no longer a figure of the finding)
        self.assertEqual(sorted(found), ["ZWE"])
        self.assertIn(f"Zimbabwe, {found['ZWE']['value']:.3g} Mt, of coke in 2024", meth)
        self.assertIn("Mozambique's coke, 1.63 Mt, is dropped by rule 5 of section 1 and is no longer a finding", meth)
        self.assertIn("coal for coke, iron ore or scrap for pig iron and direct-reduced iron", meth)
