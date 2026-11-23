"""Tests of the last data fixes before the fourth release (review GR4D, findings 1 to 8 and 10).

GR4D.1  the lithium ore-price rule is rule 9 of clean(): one frame for lanes, pairs, pages, chokepoints and profiles
GR4D.2  no scientific notation in any published text
GR4D.3  the pairs file gives the unrounded seaborne sum, as the lanes file
GR4D.4  every net balance carries its note, and holds as many digits as its lines
GR4D.5  a group that is an Atlas estimate as a whole is marked and credited so in the freight block of a country
GR4D.6  one rule for a rank: the rank of the latest year of a series is the rank printed on the line
GR4D.7  the two sides of a customs group set the same gap of the world aside
GR4D.8  the totals of the documentation are those of the files
GR4D.10 the ports index holds every port a lane page names

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_release_gr4d.py"
The tests of the data files read the files as the builders last wrote them.
"""
import glob
import json
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities"):
    p = os.path.join(ROOT, "pipeline", sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd  # noqa: E402

import build_commodities as B  # noqa: E402
import build_port_index as BPI  # noqa: E402
import build_profiles as P  # noqa: E402
import clean as C  # noqa: E402
import history as H  # noqa: E402

DATA = os.path.join(ROOT, "data")


def load(rel):
    with open(os.path.join(DATA, rel), encoding="utf-8") as f:
        return json.load(f)


def profiles():
    return {os.path.basename(f)[:-5]: json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(DATA, "countries", "profiles", "*.json")))}


def flows(rows):
    """A customs frame: (group, o, d, year, tonnes, thousand USD)."""
    return pd.DataFrame(rows, columns=["group", "o", "d", "year", "t", "usd"]).astype({"year": "int64", "t": "float64", "usd": "float64"})


class LithiumRule(unittest.TestCase):
    def test_a_lithium_flow_under_the_threshold_is_dropped_in_every_year(self):
        usd = C.LITHIUM_MIN_UV  # one tonne costs LITHIUM_MIN_UV USD: thousand USD = t * LITHIUM_MIN_UV / 1000
        rows = [("lithium", "CHL", "CHN", y, 100_000, 100_000 * usd * 4 / 1000) for y in (2023, 2024)]  # 4 times the threshold
        rows += [("lithium", "NGA", "CHN", y, 8_000, 8_000 * 286 / 1000) for y in (2023, 2024)]  # ore price
        rows += [("lithium", "BRA", "CHN", 2024, 6_000, 6_000 * (usd - 1) / 1000)]  # just under
        rows += [("lithium", "ARG", "CHN", 2024, 5_000, 5_000 * usd / 1000)]  # at the threshold: kept
        rows += [("wheat", "NGA", "CHN", 2024, 8_000, 8_000 * 286 / 1000)]  # another group: the rule is not its own
        df = C.clean(flows(rows))
        got = {(r.group, r.o, r.year) for r in df.itertuples()}
        self.assertNotIn(("lithium", "NGA", 2023), got)
        self.assertNotIn(("lithium", "NGA", 2024), got)
        self.assertNotIn(("lithium", "BRA", 2024), got)
        self.assertIn(("lithium", "ARG", 2024), got)
        self.assertIn(("lithium", "CHL", 2024), got)
        self.assertIn(("wheat", "NGA", 2024), got)
        low = [r for r in df.attrs["dropped"] if r["rule"] == "low-uv"]
        self.assertEqual(sorted((r["o"], r["year"]) for r in low), [("BRA", 2024), ("NGA", 2023), ("NGA", 2024)])
        self.assertEqual(C.LAST_DROPPED, df.attrs["dropped"])
        for r in low:
            self.assertLess(r["uvp"], C.LITHIUM_MIN_UV)
            self.assertIn("DROP_LOW_UV", r["reason"])

    def test_a_row_whose_tonnage_the_atlas_estimated_is_kept(self):
        # no tonnage: estimated from value at the group's median unit value, whatever the reported unit value
        rows = [("lithium", "CHL", "CHN", 2024, 100_000, 100_000 * 6000 / 1000), ("lithium", "ARG", "KOR", 2024, 0, 50_000)]
        df = C.clean(flows(rows))
        self.assertEqual(len(df), 2)
        self.assertTrue(df[df.o == "ARG"].imputed.iloc[0])

    def test_the_frame_of_the_cache_has_no_ore_priced_lithium(self):
        raw = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        df = C.clean(raw[raw.group == "lithium"])
        self.assertFalse(((df.uvp < C.LITHIUM_MIN_UV) & ~df.imputed).any())
        self.assertEqual(len(df[(df.year == 2024) & (df.o == "NGA") & (df.d == "CHN")]), 0)
        self.assertGreater(len([r for r in df.attrs["dropped"] if r["rule"] == "low-uv"]), 0)

    def test_an_empty_frame_is_still_cleaned(self):
        self.assertEqual(len(C.clean(flows([]))), 0)

    def test_the_builder_reads_the_threshold_of_the_cleaning(self):
        self.assertIs(B.LITHIUM_MIN_UV, C.LITHIUM_MIN_UV)

    def test_every_published_file_agrees_on_lithium(self):
        lanes, page, pairs = load("freight/lanes/lithium.json"), load("commodities/lithium.json"), load("freight/pairs/lithium.json")
        exports, seaborne = page["exports"]["world"], page["summary"]["seaborne"]["v"]
        self.assertLessEqual(seaborne, exports)
        self.assertAlmostEqual(lanes["world"][-1], exports, delta=0.06)
        self.assertEqual(seaborne, lanes["seaborne"][-1])
        self.assertEqual(pairs["seaborne"], lanes["seaborne"][-1])
        ids = {ln["id"] for ln in lanes["lanes"]}
        self.assertFalse({"lithium:NGA-CHN", "lithium:BRA-CHN"} & ids)
        self.assertFalse([r for r in pairs["rows"] if (r[0], r[1]) in (("NGA", "CHN"), ("BRA", "CHN"))])
        # the page note still says which flows are left out and why, in the words of a hypothesis
        note = " ".join(page.get("notes") or [])
        self.assertIn("leaves them out", note)
        self.assertIn("not established", note)
        # the country files read the same frame: China's freight imports of lithium are its imports line
        chn = load("countries/profiles/CHN.json")
        line = next(e for e in chn["imports"] if e["k"] == "lithium" and e["s"] == "baci" and not e.get("scope"))
        fr = next(x for x in chn["freight"]["imports"] if x["g"] == "lithium")
        self.assertAlmostEqual(fr["kt"], line["v"] * (1000 if line["u"] == "Mt" else 1), delta=1.5)

    def test_qa_lists_the_rows_of_the_rule(self):
        out = "\n".join(B.qa_dropped(type("X", (), {"dropped": [
            {"group": "lithium", "o": "NGA", "d": "CHN", "year": 2024, "usd": 2463.0, "t": 8604.0, "est": False, "uvp": 286.26, "rule": "low-uv"},
            {"group": "lpg", "o": "QAT", "d": "ITA", "year": 2021, "usd": 2.254e6, "t": 4.81e6, "est": False, "rule": "new-pair"}]})()))
        self.assertIn("Rule 9 (DROP_LOW_UV)", out)
        self.assertIn("lithium 2024, Nigeria to China: 8.60 kt, USD 2.46 million, 286 USD/t", out)
        self.assertIn("lithium 2024: 1 row, 8.60 kt", out)
        self.assertIn("LPG 2021, Qatar to Italy: 4.81 Mt", out)


class NoExponent(unittest.TestCase):
    def test_the_number_helper_prints_no_exponent(self):
        for v in (7.3e-05, 5.9e-05, 1e-9, -2e-5, 0.0009):
            self.assertNotRegex(B._nf(v), r"[eE][+-]?\d")
            self.assertNotRegex(B._nfu(v, "Mt"), r"[eE][+-]?\d")
        self.assertEqual(B._nf(7.3e-05), "under 0.001")
        self.assertEqual(B._nf(0), "0")
        self.assertEqual(B._nf(230.4), "230")
        self.assertEqual(B._nf(1823.2), "1,823")
        self.assertEqual(B._nf(1.34), "1.34")

    def test_a_small_figure_moves_to_the_smaller_unit(self):
        self.assertEqual(B._nfu(7.3e-05, "Mt"), "73 t")
        self.assertEqual(B._nfu(0.0005, "Mt"), "0.5 kt")
        self.assertEqual(B._nfu(0.05, "Mt"), "0.05 Mt")
        self.assertEqual(B._nfu(0, "Mt"), "0 Mt")
        self.assertEqual(B._nfu(12.5, "Mt"), "12.5 Mt")
        self.assertEqual(B._nfu(0.02, "t Sn"), "0.02 t Sn")

    def test_no_published_text_has_scientific_notation(self):
        """The scan of the reviewer: every string of every JSON file of data/ (the geometry and the PortWatch series are not texts)."""
        sci = re.compile(r"(?<![\w.])\d+(?:\.\d+)?[eE][+-]?\d+(?![\w])")
        hits = []

        def walk(o, path, rel):
            if isinstance(o, dict):
                for k, v in o.items():
                    walk(v, f"{path}/{k}", rel)
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{path}[{i}]", rel)
            elif isinstance(o, str) and sci.search(o):
                hits.append((rel, path, sci.search(o).group(0)))
        for f in sorted(glob.glob(os.path.join(DATA, "**", "*.json"), recursive=True)):
            rel = os.path.relpath(f, DATA)
            if rel.startswith("freight/portwatch") or rel.endswith(".geo.json") or rel.startswith("geo/"):
                continue
            with open(f, encoding="utf-8") as fh:
                walk(json.load(fh), "", rel)
        self.assertEqual(hits, [])

    def test_the_eu_split_of_a_small_trade_is_in_the_smaller_unit(self):
        tr = {"exports": {"CZE": (6.0e-05, 5.9e-05)}, "imports": {}, "ex": (6.0e-05, 5.9e-05, 1e-6), "im": (0, 0, 0), "world": {"exports": 7.0, "imports": 7.0}}
        t = B.eu_trade_table("exports", tr, "coffee", "Mt")
        text = t["rows"][0]["n"] + t["n"]
        self.assertNotRegex(text, r"\de-\d\d")
        self.assertIn("59 t to other member states", text)


class PairsSeaborne(unittest.TestCase):
    def test_the_pairs_file_gives_the_seaborne_figure_of_the_lanes_file(self):
        for f in sorted(glob.glob(os.path.join(DATA, "freight", "pairs", "*.json"))):
            p = json.load(open(f, encoding="utf-8"))
            lanes = load(f"freight/lanes/{p['group']}.json")
            want = lanes["seaborne"][-1]
            if lanes["unit"] == "kt":
                self.assertEqual(p["seaborne"], want, p["group"])  # the groups in kt: the unrounded sum, one decimal
            else:
                self.assertAlmostEqual(p["seaborne"] / 1e3, want, delta=0.006, msg=p["group"])


class NetBalances(unittest.TestCase):
    def test_the_note_says_what_is_subtracted_and_when_it_is_an_estimate(self):
        self.assertEqual(P.net_note(False, True, True), "Exports minus imports, computed by the atlas; not an estimate")
        n = P.net_note(True, False, True)
        self.assertIn("Exports minus imports", n)
        self.assertIn("no exports line, taken as 0", n)
        self.assertIn("Atlas estimate", n)
        self.assertIn("no imports line", P.net_note(False, True, False))

    def test_every_net_balance_has_its_note_and_the_digits_of_its_lines(self):
        seen = 0
        for iso, p in profiles().items():
            for b in p.get("balance", []):
                net = b.get("net")
                if not net:
                    continue
                seen += 1
                self.assertTrue(net.get("n"), (iso, b["k"]))
                self.assertEqual("Atlas estimate" in net["n"], bool(net.get("est")), (iso, b["k"]))
                if net.get("est"):
                    self.assertEqual(net["v"], float(f"{net['v']:.3g}"), (iso, b["k"], net["v"]))
        self.assertGreater(seen, 1000)

    def test_an_estimated_net_is_rounded_as_the_lines_are(self):
        rus = profiles()["RUS"]
        b = next(x for x in rus["balance"] if x["k"] == "pgm")
        self.assertEqual(b["net"]["v"], 115)


class FreightEstimate(unittest.TestCase):
    def test_spodumene_is_an_estimate_credited_to_the_atlas_in_every_country(self):
        seen = 0
        for iso, p in profiles().items():
            for side in ("exports", "imports"):
                for x in (p.get("freight") or {}).get(side, []):
                    if x["g"] == "spodumene":
                        seen += 1
                        self.assertTrue(x.get("est"), (iso, side))
                        self.assertEqual(x.get("s"), "atlas", (iso, side))
                    else:
                        self.assertNotEqual(x.get("s"), "atlas", (iso, side, x["g"]))
        self.assertGreaterEqual(seen, 4)  # Australia, Zimbabwe, Brazil and China


class Ranks(unittest.TestCase):
    def test_a_rank_is_a_position_and_ties_follow_the_order_of_the_file(self):
        h = {"years": [2020, 2021], "world": [10.0, 10.0], "c": {"CCC": [3.0, 3.0], "BBB": [3.0, 3.0], "AAA": [5.0, 3.0], "DDD": [1.0, 1.0]}}
        # 2020: AAA 5, then CCC and BBB tied at 3 in the order of the file; 2021: CCC, BBB and AAA tied at 3 in that order
        self.assertEqual(P.series_at(h, "AAA")[0]["hr"], [1, 3])
        self.assertEqual(P.series_at(h, "CCC")[0]["hr"], [2, 1])
        self.assertEqual(P.series_at(h, "BBB")[0]["hr"], [3, 2])
        self.assertEqual(P.series_at(h, "DDD")[0]["hr"], [4, 4])

    def test_the_latest_year_takes_the_rank_of_the_line(self):
        h = {"years": [2020, 2021], "world": [10.0, 10.0], "c": {"AAA": [3.0, 3.0], "BBB": [3.0, 3.0]}}
        self.assertEqual(P.series_at(h, "BBB", last_rank=1)[0]["hr"], [2, 1])

    def test_the_rank_of_the_latest_year_equals_the_rank_of_the_line(self):
        n = 0
        for iso, p in profiles().items():
            for sec in ("production", "consumption", "reserves", "stocks", "capacity", "exports", "imports"):
                for e in p.get(sec, []):
                    if e.get("hr") and e.get("rank") is not None and e["hr"][-1] is not None:
                        n += 1
                        self.assertEqual(e["hr"][-1], e["rank"], (iso, sec, e["k"], e.get("hk")))
        self.assertGreater(n, 5000)


class TwoSides(unittest.TestCase):
    def test_a_gap_of_the_world_is_set_aside_on_both_sides_of_a_group(self):
        world = [100.0, 100.0, 40.0, 100.0, 100.0]
        vals = {"AAA": [60.0, 60.0, 21.0, 60.0, 60.0], "BBB": [40.0, 40.0, 19.0, 40.0, 40.0]}  # a fall of 2.8 times: under OUT_ROW
        self.assertEqual(H.out_of_line(world, vals), {})
        self.assertEqual(H.out_of_line(world, vals, pair_years=[2]), {"AAA": [2]})
        # a declared value that moved with the tonnage keeps the row on its own side; on the second side the first side's verdict stands
        usd = {"AAA": [60.0, 60.0, 25.0, 60.0, 60.0]}
        self.assertEqual(H.out_of_line(world, vals, usd), {})
        self.assertEqual(H.out_of_line(world, vals, usd, pair_years=[2]), {"AAA": [2]})
        # the other years of the series are not affected
        self.assertEqual(H.out_of_line(world, vals, usd, pair_years=[3]), {})

    def test_the_history_files_agree_on_both_sides(self):
        n = 0
        for f in sorted(glob.glob(os.path.join(DATA, "commodities", "history", "*.json"))):
            t = json.load(open(f, encoding="utf-8"))["t"]
            for k, a in t.items():
                other = H._other_side(k)
                b = t.get(other) if other and k.endswith("exports") else None
                if not b or a["years"] != b["years"]:
                    continue
                for i in range(len(a["years"])):
                    if a["world"][i] == b["world"][i]:
                        n += 1
                        self.assertEqual(i in (a.get("worldOut") or []), i in (b.get("worldOut") or []), (os.path.basename(f), k, a["years"][i]))
        self.assertGreater(n, 100)

    def test_cobalt_2016(self):
        t = json.load(open(os.path.join(DATA, "commodities", "history", "cobalt.json"), encoding="utf-8"))["t"]
        i = t["exports"]["years"].index(2016)
        self.assertEqual(t["exports"]["out"], {"COD": [i]})
        self.assertEqual(t["imports"]["out"], {"CHN": [i]})
        self.assertEqual(t["exports"]["worldOut"], [i])
        self.assertEqual(t["imports"]["worldOut"], [i])

    def test_the_other_side_of_a_key(self):
        self.assertEqual(H._other_side("exports"), "imports")
        self.assertEqual(H._other_side("refined-imports"), "refined-exports")
        self.assertIsNone(H._other_side("production"))


def count_groups():
    """(groups, seaborne Mt of the latest year) from the pairs files: the rows by sea or through a transit port."""
    n, tot = 0, 0.0
    for f in glob.glob(os.path.join(DATA, "freight", "pairs", "*.json")):
        p = json.load(open(f, encoding="utf-8"))
        ix = {c: i for i, c in enumerate(p["cols"])}
        n += 1
        tot += sum(r[ix["kt"]] for r in p["rows"] if r[ix["m"]] in (0, 1)) / 1e3
    return n, tot


class Documentation(unittest.TestCase):
    def test_the_generated_corridor_basis_is_that_of_the_files(self):
        with open(os.path.join(ROOT, "METHODOLOGY.md"), encoding="utf-8") as f:
            text = " ".join(f.read().split())
        m = re.search(r"hand-written routes name [\d.]+% of the ([\d,]+) Mt of \d{4} seaborne tonnes of the (\d+) customs groups", text)
        self.assertTrue(m)
        groups, total = count_groups()
        self.assertEqual(int(m.group(2)), groups)
        self.assertAlmostEqual(float(m.group(1).replace(",", "")), total, delta=1.0)
        qa = open(os.path.join(ROOT, "pipeline", "freight", "QA_routes.md"), encoding="utf-8").read()
        m2 = re.search(r"over (\d+) groups, ([\d,]+) Mt of seaborne trade", qa)
        self.assertEqual((int(m2.group(1)), int(m2.group(2).replace(",", ""))), (int(m.group(2)), int(m.group(1).replace(",", ""))))

    def test_the_seaborne_total_of_the_mode_paragraph_is_that_of_the_files(self):
        with open(os.path.join(ROOT, "METHODOLOGY.md"), encoding="utf-8") as f:
            text = " ".join(f.read().split())
        m = re.search(r"Seaborne: ([\d,]+\.\d) Mt\. \((\d+) groups", text)
        self.assertTrue(m)
        self.assertAlmostEqual(float(m.group(1).replace(",", "")), count_groups()[1], delta=0.06)

    def test_no_docstring_counts_the_pairs_files_wrongly(self):
        with open(os.path.join(ROOT, "pipeline", "freight", "build_port_index.py"), encoding="utf-8") as f:
            src = " ".join(f.read().split())
        n = len(glob.glob(os.path.join(DATA, "freight", "pairs", "*.json")))
        self.assertIn(f"download the {n} pairs files", src)

    def test_the_cleaning_rule_is_documented(self):
        with open(os.path.join(ROOT, "METHODOLOGY.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("`DROP_LOW_UV`", text)
        self.assertIn(f"{C.LITHIUM_MIN_UV:,} USD per tonne", text)


class PortIndex(unittest.TestCase):
    def test_a_port_only_a_lane_page_names_is_listed(self):
        COLS = ["o", "d", "kt", "m", "load", "dis", "nm", "cls", "via", "alt", "f"]
        pairs = {"group": "wheat", "k": "wheat", "y": 2024, "s": "baci", "unit": "kt", "ports": [["UAODS", "Odessa", "UKR", "bs", 0, None]], "cols": COLS,
                 "rows": [["UKR", "EGY", 500, 0, 0, None, 1000, 0, 0, 0, 4]]}
        lane = {"group": "wheat", "unit": "Mt", "ports": {"UAODS": {"id": "UAODS", "name": "Odessa", "c": "UKR"}, "UAPIV": {"id": "UAPIV", "name": "Pivdennyi", "c": "UKR"},
                                                          "EGALY": {"id": "EGALY", "name": "Alexandria", "c": "EGY"}, "EGDAM": {"id": "EGDAM", "name": "Damietta", "c": "EGY"}},
                "lanes": [{"id": "wheat:UKR-EGY", "set": "main", "flow": {"v": 0.5, "u": "Mt"}, "load": ["UAODS"], "discharge": ["EGALY"],
                           "opts": [{"load": "UAPIV", "discharge": "EGALY"}]},
                          {"id": "wheat:UKR-XXX", "set": "history", "flow": {"v": 9.0, "u": "Mt"}, "load": ["UAODS"], "discharge": ["EGDAM"]}]}
        with tempfile.TemporaryDirectory() as tmp:
            for sub, name, doc in (("pairs", "wheat", pairs), ("lanes", "wheat", lane)):
                os.mkdir(os.path.join(tmp, sub))
                with open(os.path.join(tmp, sub, f"{name}.json"), "w", encoding="utf-8") as fh:
                    json.dump(doc, fh)
            doc = BPI.build(pairs_dir=os.path.join(tmp, "pairs"), out=os.path.join(tmp, "p.json"))
        ports = {p["id"]: p for p in doc["ports"]}
        self.assertEqual(set(ports), {"UAODS", "UAPIV", "EGALY"})  # Damietta is named by a history lane only: no page
        self.assertEqual(ports["UAODS"]["n"], 1)  # the pairs that use it, as before
        self.assertEqual(ports["UAPIV"]["lane"], "wheat:UKR-EGY")
        self.assertEqual(ports["UAPIV"]["g"], ["wheat"])
        self.assertEqual(ports["EGALY"]["lane"], "wheat:UKR-EGY")

    def test_the_index_holds_every_port_of_every_lane_page(self):
        index = {p["id"] for p in load("freight/ports.json")["ports"]}
        missing = set()
        for f in glob.glob(os.path.join(DATA, "freight", "lanes", "*.json")):
            d = json.load(open(f, encoding="utf-8"))
            for ln in d["lanes"]:
                if ln["set"] != "main":
                    continue
                for part in (ln, *(ln.get("opts") or [])):
                    for col in ("load", "discharge"):
                        v = part.get(col) or []
                        missing |= {x for x in ([v] if isinstance(v, str) else v) if x not in index}
        self.assertEqual(missing, set())
        self.assertIn("CNYTN", index)


if __name__ == "__main__":
    unittest.main()
