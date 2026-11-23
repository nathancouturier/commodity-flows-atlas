"""Tests of the generated corridor routes (pipeline/freight/generated_routes.py): the selection on a small invented pairs
table (deterministic, disjoint corridors, coverage, floors and caps), then the published files (data/freight/routes.json
against the pairs files) when they have been built.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
"""
import glob
import json
import os
import sys
import unittest
import unittest.mock
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("freight", "trade"):
    p = os.path.join(ROOT, "pipeline", sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import generated_routes as GR  # noqa: E402

FREIGHT = os.path.join(ROOT, "data", "freight")

# ---------------------------------------------------------------- a small invented table
PORTS = [  # code, name, country, zone, basis, basis
    ["AAA", "Alpha", "AAA", "z1", 0, 0], ["BBB", "Beta", "BBB", "z2", 0, 0], ["CCC", "Gamma", "CCC", "z3", 0, 0],
    ["DDD", "Delta", "DDD", "z4", 0, 0], ["EEE", "Epsilon", "EEE", None, 0, 0],
]
ZONES = [{"id": f"z{i}", "name": f"Zone {i} (note)"} for i in range(1, 5)]
AT = {"AAA": [0, 0], "BBB": [10, 0], "CCC": [20, 0], "DDD": [30, 0], "EEE": [29, 1]}


def row(o, d, t, load, dis, m=0, nm=1000, cls="supramax"):
    return {"o": o, "d": d, "t": t, "m": m, "load": load, "dis": dis, "nm": nm, "cls": cls, "via": set(), "alt": set(), "f": 0}


def table():
    rows = [row("AAA", "BBB", 40.0, 0, 1), row("AAA", "CCC", 30.0, 0, 2), row("AAA", "DDD", 8.0, 0, 3), row("AAA", "EEE", 6.0, 0, 4),
            row("BBB", "CCC", 9.0, 1, 2), row("BBB", "DDD", 0.2, 1, 3), row("CCC", "AAA", 0.1, 2, 0),
            row("CCC", "BBB", 5.0, -1, -1, m=2)]  # a mixed pair: not seaborne, never in a corridor
    seaborne = sum(r["t"] for r in rows if r["m"] in (0, 1))
    return {"k": "wheat", "y": 2024, "seaborne": seaborne, "rows": rows, "ports": PORTS}


def run(hand=None, **kw):
    pairs = {"wheat": table()}
    return GR.generate(pairs, {"wheat": PORTS}, hand or {}, ZONES, lambda c: AT[c], lambda g: ("Wheat", "wheat"), {"hand": "Hand route"},
                       lambda c: c, **kw)


class SelectionTest(unittest.TestCase):
    def test_zone_of_a_port_without_one_is_the_nearest_zoned_port(self):
        zone = GR.zone_lookup({"wheat": PORTS}, lambda c: AT[c])
        self.assertEqual(zone("EEE"), "z4")
        self.assertEqual(zone("AAA"), "z1")

    def test_largest_corridors_first_until_the_target(self):
        defs, rep = run()
        # z1 to z2 (40 Mt) and z1 to z3 (30 Mt) reach 70% of the 93.3 Mt: nothing smaller is asked for
        self.assertEqual([d["id"] for d in defs], ["gen-wheat-z1-z2", "gen-wheat-z1-z3"])
        self.assertGreaterEqual(rep["wheat"]["share"], 70)
        self.assertIsNone(rep["wheat"]["why"])

    def test_a_pair_is_in_one_corridor_only(self):
        defs, _ = run(target=0.99)
        seen = defaultdict(list)
        for d in defs:
            for c in d["corridor"]:
                for o in c["o"]:
                    for dd in c["d"]:
                        seen[(c["g"], o, dd)].append(d["id"])
        self.assertTrue(seen)
        self.assertTrue(all(len(v) == 1 for v in seen.values()), {k: v for k, v in seen.items() if len(v) > 1})

    def test_same_input_same_output(self):
        a, b = run(target=0.99), run(target=0.99)
        self.assertEqual(json.dumps(a, sort_keys=True, default=list), json.dumps(b, sort_keys=True, default=list))

    def test_ports_class_and_distance_are_the_largest_pairs(self):
        defs, _ = run()
        d = defs[0]
        self.assertEqual(d["_ports"], ("AAA", "BBB"))
        self.assertEqual(d["_pair"][:3], ("wheat", "AAA", "BBB"))
        self.assertEqual((d["vclass"], d["_nm"]), ("supramax", 1000))
        self.assertEqual(d["from"]["ports"][0]["name"], "Alpha")
        self.assertEqual(d["name"], "Wheat: AAA to BBB")  # one country holds all the tonnes of each end
        self.assertTrue(d["generated"] and not d["benchmark"] and d["s"] == "atlas")

    def test_what_a_hand_written_route_names_is_not_asked_for_again(self):
        defs, rep = run(hand={("wheat", "AAA", "BBB"): ["hand"]})
        self.assertNotIn("gen-wheat-z1-z2", [d["id"] for d in defs])
        self.assertAlmostEqual(rep["wheat"]["handShare"], 100 * 40.0 / 93.3, 1)

    def test_a_corridor_part_named_by_hand_says_so(self):
        # AAA to DDD and AAA to EEE sit in z1 to z4 (14 Mt): AAA to EEE (6 Mt) is named by a hand-written route, 8 of the 14 Mt are not
        defs, _ = run(hand={("wheat", "AAA", "EEE"): ["hand"]}, target=0.99)
        z4 = [d for d in defs if d["id"] == "gen-wheat-z1-z4"]
        self.assertTrue(z4)
        self.assertIn("Hand route", z4[0]["notes"])

    def test_floor_and_caps(self):
        defs, rep = run(target=0.999)
        # the 0.2 Mt and 0.1 Mt corridors are under the floor
        self.assertNotIn("gen-wheat-z2-z4", [d["id"] for d in defs])
        self.assertIn("each under", rep["wheat"]["why"] or "")
        defs, rep = run(target=0.999, total_cap=2)
        self.assertEqual(len(defs), 2)
        self.assertIn("cap of 2", rep["wheat"]["why"])
        # the largest corridors survive the cap
        self.assertEqual([d["id"] for d in defs], ["gen-wheat-z1-z2", "gen-wheat-z1-z3"])

    def test_corridor_entries_are_the_pairs_of_the_corridor(self):
        defs, _ = run(target=0.99)
        z4 = next(d for d in defs if d["id"] == "gen-wheat-z1-z4")
        pairs = {(o, dd) for c in z4["corridor"] for o in c["o"] for dd in c["d"]}
        self.assertEqual(pairs, {("AAA", "DDD"), ("AAA", "EEE")})


class NameTest(unittest.TestCase):
    """The name of a route says the country that holds most of the tonnes of an end (review GF1.4)."""
    PORTS2 = PORTS[:4] + [["FFF", "Phi", "FFF", "z2", 0, 0]]
    AT2 = dict(AT, FFF=[11, 0])

    def names(self, b, f, **kw):
        rows = [row("AAA", "BBB", b, 0, 1), row("AAA", "FFF", f, 0, 4)]
        p = {"k": "wheat", "y": 2024, "seaborne": b + f, "rows": rows, "ports": self.PORTS2}
        defs, _ = GR.generate({"wheat": p}, {"wheat": self.PORTS2}, {}, ZONES, lambda c: self.AT2[c], lambda g: ("Wheat", "wheat"), {},
                              lambda c: c, **kw)
        return defs

    def test_one_country_holds_most_of_an_end(self):
        defs = self.names(40.0, 5.0)  # BBB 89% of the discharge tonnes, AAA all of the loading ones
        self.assertEqual([d["name"] for d in defs], ["Wheat: AAA to BBB"])
        self.assertEqual((defs[0]["from"]["region"], defs[0]["to"]["region"]), ("AAA", "BBB"))
        # the end of the page says "Netherlands", the name "the Netherlands"
        with unittest.mock.patch.object(GR, "COUNTRY_SHARE", 0.8):
            rows = [row("AAA", "BBB", 40.0, 0, 1)]
            p = {"k": "wheat", "y": 2024, "seaborne": 40.0, "rows": rows, "ports": self.PORTS2}
            d = GR.generate({"wheat": p}, {"wheat": self.PORTS2}, {}, ZONES, lambda c: self.AT2[c], lambda g: ("Wheat", "wheat"), {},
                            lambda c: {"AAA": "the Alps", "BBB": "Bern"}[c])[0][0]
        self.assertEqual((d["name"], d["from"]["region"]), ("Wheat: the Alps to Bern", "Alps"))
        self.assertIn("AAA (loading, 100% of the tonnes) and BBB (discharge, 89% of the tonnes)", defs[0]["notes"])

    def test_below_the_threshold_the_zone_names_the_end(self):
        defs = self.names(30.0, 20.0)  # BBB 60%
        self.assertEqual([d["name"] for d in defs], ["Wheat: AAA to Zone 2"])
        self.assertEqual(defs[0]["to"]["region"], "Zone 2")

    def test_a_zone_that_says_its_country_keeps_its_name(self):
        with unittest.mock.patch.dict(GR.ZONE_SAYS, {"z1": {"AAA"}}):
            defs = self.names(40.0, 5.0)
        self.assertEqual([d["name"] for d in defs], ["Wheat: Zone 1 to BBB"])

    def test_the_zones_that_say_a_country_exist(self):
        with open(os.path.join(FREIGHT, "zones.json"), encoding="utf-8") as f:
            zones = json.load(f)
        self.assertTrue(set(GR.ZONE_SAYS) <= {z["id"] for z in zones})


class PassagesTest(unittest.TestCase):
    def test_the_pairs_own_passages_in_the_order_of_the_route(self):
        via, alt = GR.pair_passages(["danish-straits", "dover", "suez"], {"suez"}, {"suez", "danish-straits", "sunda", "malacca", "gibraltar"})
        self.assertEqual(via, ["suez"])
        self.assertEqual(alt, [["malacca", "sunda"], ["gibraltar"], ["danish-straits"]])  # the order of the pairs file's gates
        # the parallel group is one list, in the order of the mask (gates of routing.py)
        via, alt = GR.pair_passages(["panama"], set(), {"panama", "taiwan-strait", "luzon"})
        self.assertEqual((via, alt), ([], [["taiwan-strait", "luzon"], ["panama"]]))

    def test_a_certain_passage_the_drawn_route_does_not_cross_is_kept(self):
        self.assertEqual(GR.pair_passages([], {"hormuz"}, set())[0], ["hormuz"])


class QaReportTest(unittest.TestCase):
    def test_report_is_the_same_text_every_time_and_says_what_the_cap_left_out(self):
        defs, rep = run(target=0.999, total_cap=2)
        a, b = GR.qa_markdown(rep, total_cap=2), GR.qa_markdown(rep, total_cap=2)
        self.assertEqual(a, b)
        self.assertIn("| wheat | 93.3 |", a)
        self.assertIn("## Corridors the cap left out", a)
        self.assertTrue(rep["wheat"]["left"])
        self.assertIn(f"- wheat: {rep['wheat']['left'][0]['name']}", a)
        self.assertIn("groups reach the target", a)


# ---------------------------------------------------------------- the published files
BUILT = os.path.exists(os.path.join(FREIGHT, "routes.json")) and os.path.isdir(os.path.join(FREIGHT, "pairs"))


@unittest.skipUnless(BUILT, "build_freight.py has not written routes.json yet")
class PublishedRoutesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(FREIGHT, "routes.json"), encoding="utf-8") as f:
            cls.routes = json.load(f)
        cls.gen = [r for r in cls.routes if r.get("generated")]
        cls.pairs = {}
        for path in glob.glob(os.path.join(FREIGHT, "pairs", "*.json")):
            with open(path, encoding="utf-8") as f:
                p = json.load(f)
            cols = p["cols"]
            cls.pairs[p["group"]] = {(r[cols.index("o")], r[cols.index("d")]): dict(zip(cols, r)) | {"ports": p["ports"], "classes": p["classes"]}
                                    for r in p["rows"]}
            cls.pairs[p["group"]]["_sea"] = p["seaborne"] / 1e3
        cls.gates = {}
        for path in glob.glob(os.path.join(FREIGHT, "pairs", "*.json")):
            with open(path, encoding="utf-8") as f:
                p = json.load(f)
            cls.gates[p["group"]] = p["gates"]

    def test_there_are_generated_routes_and_ids_are_unique(self):
        self.assertGreater(len(self.gen), 0)
        self.assertLessEqual(len(self.gen), GR.TOTAL_CAP)
        ids = [r["id"] for r in self.routes]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(r["id"].startswith("gen-") for r in self.gen))
        self.assertFalse(any(r["id"].startswith("gen-") for r in self.routes if not r.get("generated")))

    def test_a_generated_route_is_never_a_benchmark_and_says_how_it_was_made(self):
        for r in self.gen:
            self.assertFalse(r["benchmark"], r["id"])
            self.assertEqual(r["s"], "atlas", r["id"])
            self.assertTrue(r["notes"].startswith("Atlas corridor, generated from customs pairs"), r["id"])
            self.assertIn("2024", r["notes"], r["id"])
            self.assertTrue(r.get("shares") and r.get("history"), r["id"])
            self.assertRegex(r["name"], r"^[A-Z][^:]*(: .+ to .+| within .+)$", r["id"])

    def test_no_pair_is_in_two_generated_corridors(self):
        seen = defaultdict(list)
        for r in self.gen:
            for c in r["corridor"]:
                for o in c["o"]:
                    for d in c["d"]:
                        seen[(c["g"], o, d)].append(r["id"])
        self.assertTrue(all(len(v) == 1 for v in seen.values()), {k: v for k, v in seen.items() if len(v) > 1})

    def test_distance_and_ports_are_those_of_the_largest_pair_the_finder_reads(self):
        for r in self.gen:
            g = r["corridor"][0]["g"]
            ps = self.pairs[g]
            rows = [ps[(o, d)] for c in r["corridor"] for o in c["o"] for d in c["d"] if (o, d) in ps]
            self.assertTrue(rows, r["id"])
            big = max(rows, key=lambda x: (x["kt"], x["o"], x["d"]))
            self.assertEqual(r["distanceNm"], big["nm"], r["id"])
            self.assertEqual(r["vclass"], big["classes"][big["cls"]], r["id"])
            self.assertEqual(r["from"]["ports"], [big["ports"][big["load"]][1]], r["id"])
            self.assertEqual(r["to"]["ports"], [big["ports"][big["dis"]][1]], r["id"])

    def test_passages_are_those_the_route_finder_gives_for_the_largest_pair(self):
        """Review GF1.5: the route page and the Route finder name the same passages for the same pair: the lane's when the pair has
        a main lane, else the pairs row's masks."""
        lanes = {}
        for path in glob.glob(os.path.join(FREIGHT, "lanes", "*.json")):
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            for ln in d["lanes"]:
                if ln.get("set") == "main":
                    lanes[(d["group"], ln["o"], ln["d"])] = ln
        with_lane = 0
        for r in self.gen:
            g = r["corridor"][0]["g"]
            ps = self.pairs[g]
            rows = [ps[(o, d)] for c in r["corridor"] for o in c["o"] for d in c["d"] if (o, d) in ps]
            big = max(rows, key=lambda x: (x["kt"], x["o"], x["d"]))
            ln = lanes.get((g, big["o"], big["d"]))
            if ln:
                with_lane += 1
                self.assertEqual((r["via"], r.get("viaAlt", [])), (ln["via"], ln.get("viaAlt", [])), r["id"])
            names = self.gates[g]
            via = {names[i] for i in range(len(names)) if big["via"] >> i & 1}
            alt = {names[i] for i in range(len(names)) if big["alt"] >> i & 1} - via
            self.assertEqual(set(r["via"]), via, r["id"])
            self.assertEqual({x for lst in r.get("viaAlt", []) for x in lst}, alt, r["id"])
        self.assertGreater(with_lane, 0)

    def test_a_corridor_entry_names_its_customs_groups(self):
        """Review GF1.3: an entry without `g` lists the groups of its commodity (`gs`), so that the site never matches a lane of another
        group (refined copper is not copper concentrate)."""
        import build_freight as BF
        for r in self.routes:
            for c in r.get("corridor") or []:
                self.assertTrue(c.get("g") or c.get("gs"), r["id"])
                self.assertEqual(c.get("g") and [c["g"]] or c["gs"], BF.corridor_groups(c), r["id"])
        by_id = {r["id"]: r for r in self.routes}
        for rid in ("chile-china-copper", "peru-china-copper"):
            self.assertEqual(by_id[rid]["corridor"][0]["gs"], ["copper-ore"])

    def test_names_say_the_country_that_holds_most_of_an_end(self):
        """Review GF1.4: no generated route is named after a zone when one country holds COUNTRY_SHARE of the tonnes of an end, unless the
        zone's own name says the country; names are unique."""
        names = [r["name"] for r in self.gen]
        self.assertEqual(len(names), len(set(names)))
        by_id = {r["id"]: r for r in self.routes}
        self.assertEqual(by_id["gen-phosphate-rock-waf-med"]["name"], "Phosphate rock: Morocco to the Mediterranean")
        self.assertEqual(by_id["gen-dap-waf-med"]["name"], "DAP: Morocco to the Mediterranean")
        self.assertEqual(by_id["gen-dap-waf-ec-india"]["name"], "DAP: Morocco to Bangladesh")
        for r in self.gen:
            if "The name says the country" in r["notes"]:
                self.assertIn("% of the tonnes)", r["notes"], r["id"])

    def test_qa_report_is_written_next_to_the_builder(self):
        path = os.path.join(ROOT, "pipeline", "freight", "QA_routes.md")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Corridors the cap left out", text)
        self.assertIn(f"{len(self.gen)} generated routes", text)

    def test_coverage_by_group(self):
        """The named routes (hand-written and generated) cover the target of every group, or the report gives the reason: here, the
        groups under the target are listed by the build (`build_freight.py` prints the reason of each), recomputed here from the
        published files."""
        hand = defaultdict(set)
        with open(os.path.join(ROOT, "pipeline", "freight", "routes_def.json"), encoding="utf-8") as f:
            defs = json.load(f)
        import build_freight as BF
        for r in self.routes:
            if r.get("discontinued") or not r.get("corridor"):
                continue
            for c in r["corridor"]:
                for g in BF.corridor_groups(c):
                    for o in c["o"]:
                        for d in c["d"]:
                            hand[g].add((o, d))
        under = {}
        total = covered = 0.0
        for g, ps in self.pairs.items():
            sea = ps["_sea"]
            cov = sum(v["kt"] / 1e3 for k, v in ps.items() if k != "_sea" and v["m"] in (0, 1) and k in hand[g])
            total += sea
            covered += cov
            if cov < GR.TARGET * sea:
                under[g] = round(100 * cov / sea, 1)
        self.assertGreater(len(defs), 0)
        # every group the audit names is served, and the atlas as a whole is well above the 45% of the hand-written routes
        for g in ("coal", "refined-products", "lng", "steel", "manganese", "alumina", "sugar", "rice", "rapeseed", "corn", "soymeal", "wheat",
                  "palm-oil", "urea", "dap", "potash"):
            self.assertTrue(any(c["g"] == g for r in self.gen for c in r["corridor"]), g)
        self.assertGreater(100 * covered / total, 55)
        # a group under the target is explained by the build's report (cap of the whole atlas, floor, unrouted pairs), not by a
        # missing step: the groups the hand-written routes already name above the target get no generated route
        self.assertTrue(set(under) <= set(self.pairs), under)


if __name__ == "__main__":
    unittest.main()
