"""Tests of the corrections after the verification review (package FNCF): the engine, the ports, the routes and the figures.

F1  the unit suite runs on a clone without raw/: a test that reads a raw download skips itself
F2  Russian grain, oilseeds and meal for France go to Fos, the port of the Black Sea partners
F3  French grain: Rouen for the partners the page names and for the Channel, the North Sea and the Baltic, La Pallice for the others
F4  Turkish scrap, pig iron and direct-reduced iron: Izmir is the second option of the Mediterranean basin; the port shares are an allocation
F5  the released routes, the cap of the generated routes, the singular of the note, the pairs of the released groups outside France
F6  a pair whose declared destination or origin is a landlocked trading centre: caveat, no corridor
F7  Mozambique's coke is left out (rule 5 of clean.py) and the coke page says so
F8  the note on tables that hold under 97% of the customs file is written for every group that a page shows as a table
F9  the transit note is built from the row of the exporters table
F10 the legacy fertiliser port is the exporter's own port only (role "load")
F11 Djibouti among the importers of the two-nutrient compounds: row note and page note built from the transit table

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The tests of the data files read the files as the builders last wrote them.
"""
import hashlib
import json
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import generated_routes as GR  # noqa: E402
import ports as P  # noqa: E402

DATA = os.path.join(ROOT, "data")
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return json.load(f)


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def pairs(group):
    p = load(DATA, "freight", "pairs", group + ".json")
    out = {}
    for r in p["rows"]:
        row = dict(zip(p["cols"], r))
        row["load_port"] = p["ports"][row["load"]][0] if row["load"] >= 0 else None
        row["dis_port"] = p["ports"][row["dis"]][0] if row["dis"] >= 0 else None
        out[(row["o"], row["d"])] = row
    return out, p


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def decoded_rows(doc, skip=("FRA",)):
    """The rows of a pairs file with ports, classes and passages by name, the pairs that touch `skip` left out, sorted. The caveat bit of the
    flags (a note on the pair) is not a change of its port, class, distance or passages."""
    ports, classes, gates = doc["ports"], doc.get("classes") or [], doc.get("gates") or []
    ix = {c: i for i, c in enumerate(doc["cols"])}
    out = []
    for r in doc["rows"]:
        if r[ix["o"]] in skip or r[ix["d"]] in skip:
            continue
        row = []
        for c, v in zip(doc["cols"], r):
            if c in ("load", "dis"):
                row.append(ports[v][0] if v >= 0 else None)
            elif c == "cls":
                row.append(classes[v] if v >= 0 else None)
            elif c == "f":
                row.append(v & ~2)
            elif c in ("via", "alt"):
                row.append([g for i, g in enumerate(gates) if (v >> i) & 1])
            else:
                row.append(v)
        out.append(row)
    return sorted(out, key=lambda x: (x[ix["o"]], x[ix["d"]]))


class F1TestsSkipWithoutRaw(unittest.TestCase):
    def test_a_test_that_opens_a_raw_download_has_a_guard(self):
        """raw/ is not tracked: CI has none. Every test file that names a file of raw/ in an open() or a read has a skip in it (review GV6B.1: test_fncb
        opened the BACI product list unguarded)."""
        here = os.path.dirname(os.path.abspath(__file__))
        for name in sorted(os.listdir(here)):
            if not (name.startswith("test_") and name.endswith(".py")) or name == "test_fncf.py":
                continue
            text = open(os.path.join(here, name), encoding="utf-8").read()
            if re.search(r'os\.path\.join\(ROOT, "raw"', text) or re.search(r'"raw", "[a-z-]+", "[^"]+\.(csv|xlsx|zip|json)"', text):
                self.assertRegex(text, r"skipTest|skipUnless|skipIf|os\.path\.exists", name)

    def test_a_build_without_the_eia_file_keeps_the_no_production_caveats(self):
        """GE5_3 of test_lanes.py failed on a clone without raw/: the K14 entries are built from the data, not listed in the registry, and keep_caveats()
        dropped them (a failed download must not remove a warning)."""
        import build_lanes as BL
        prev = {"nop-coke-ZWE": {"kind": "no-production", "group": "coke", "o": "ZWE", "d": None, "check": "K14", "text": "t"}}
        self.assertIn("nop-coke-ZWE", BL.keep_caveats({}, prev, set()))
        self.assertNotIn("nop-coke-ZWE", BL.keep_caveats({}, prev, {"K14"}))
        self.assertNotIn("nop-coke-ZWE", BL.keep_caveats({}, {"nop-x": {**prev["nop-coke-ZWE"], "group": "nothing"}}, set()))

    def test_the_wording_check_of_the_codes_skips_alone(self):
        text = read("pipeline", "tests", "test_fncb.py")
        i = text.index("def test_the_codes_are_the_intended_ones_and_in_one_group")
        body = text[i:text.index("def test_the_cache_holds_the_codes")]
        self.assertLess(body.index("hs_map.HS[g]"), body.index("skipTest"))  # the assertions on hs_map come first and always run
        self.assertIn("raw BACI product list not on disk", body)


class F2RussianGrainForFrance(unittest.TestCase):
    def test_russia_is_on_the_mediterranean_side_of_the_grain_rule_not_of_the_fertiliser_rule(self):
        """Its grain port in the atlas is Novorossiysk: Fos is 1,817 nm away, Rouen 3,469 nm (review GV6A.1)."""
        for g in ("sunflower-meal", "rapeseed-meal", "soymeal", "wheat"):
            a = P.assign("RUS", "FRA", g)
            self.assertEqual((a.main.load, a.main.discharge, a.basis, a.rule), ("RUNVS", "FRFOS", "rule", "fra-coast-grain"), g)
        self.assertEqual(P.assign("RUS", "FRA", "dap").main.discharge, "FRLEH")  # the fertilisers load at Ust-Luga, in the Baltic
        self.assertEqual(P.assign("RUS", "FRA", "steel").main.discharge, "FRFOS")

    def test_the_pairs_of_the_three_groups_end_at_fos_by_the_short_route(self):
        for g in ("sunflower-meal", "rapeseed-meal", "soymeal"):
            rows, _ = pairs(g)
            r = rows[("RUS", "FRA")]
            self.assertEqual((r["load_port"], r["dis_port"]), ("RUNVS", "FRFOS"), g)
            self.assertLess(r["nm"], 2200, g)


class F3FrenchGrainPorts(unittest.TestCase):
    # the eleven partners of the Rouen page (FNCI: China, Morocco, Algeria and the eight "less common destinations")
    NAMED = ("CHN", "MAR", "DZA", "MRT", "MEX", "THA", "IND", "COL", "MDG", "USA", "ZAF")
    SEAS = ("GBR", "IRL", "BEL", "NLD", "DEU", "DNK", "NOR", "SWE", "FIN", "ISL", "POL", "LTU", "LVA", "EST")
    OTHER = ("PRT", "SEN", "NGA", "BRA", "ARG", "SAU", "JPN", "KOR", "AUS", "KEN", "CAN", "VEN", "GHA", "VNM")

    def test_the_principal_port_is_chosen_by_the_partner_and_the_other_port_is_an_option_of_every_partner(self):
        """FNCH H1: no page gives the split between the two ports, so no partner outside the Mediterranean side is given one port only."""
        for g in ("wheat", "barley", "corn", "rapeseed", "soymeal", "rapeseed-meal"):
            for c in self.NAMED + self.SEAS:
                a = P.assign("FRA", c, g)
                self.assertEqual((a.main.load, {o.load for o in a.options}, a.basis), ("FRURO", {"FRURO", "FRLPE"}, "open"), (g, c))
            for c in self.OTHER:
                a = P.assign("FRA", c, g)
                self.assertEqual((a.main.load, {o.load for o in a.options}, a.basis), ("FRLPE", {"FRURO", "FRLPE"}, "open"), (g, c))  # the rule of the other end (Mexico's coast) may name the pair
        for c in ("ITA", "ESP", "GRC", "EGY", "TUR", "RUS"):  # the Mediterranean side keeps Fos, with no option
            a = P.assign("FRA", c, "wheat")
            self.assertEqual((a.main.load, {o.load for o in a.options}), ("FRFOS", {"FRFOS"}), c)
        self.assertEqual({o.load for o in P.assign("FRA", "SAU", "wheat").options}, {"FRURO", "FRLPE"})  # a partner left open keeps both ports

    def test_the_eleven_partners_of_the_rouen_page_are_read_before_the_basin_of_la_pallice(self):
        """FNCI (GV8A.1): the United States, Mexico and Colombia are in the basin of La Pallice; the named set must come first in the rule, and none of
        the eleven may be on the Mediterranean side."""
        rule = next(r for r in P.COAST_RULES if r["id"] == "fra-grain-ports")
        order = list(rule["basins"])
        self.assertLess(order.index("rouen-named"), order.index("la-pallice"))
        self.assertLess(order.index("med"), order.index("rouen-named"))
        self.assertEqual(set(self.NAMED), set(rule["basins"]["rouen-named"]))
        for c in self.NAMED:
            self.assertNotIn(c, rule["basins"]["med"], c)
            first = next(b for b, members in rule["basins"].items() if c in members)
            self.assertEqual(first, "rouen-named", c)
            self.assertEqual(P._apply_rule(rule, "FRA", "wheat", "load", c, None, False), ("ports", ["FRURO", "FRLPE"]), c)
        self.assertEqual(len(set(self.NAMED)), 11)
        # the page's sentence is in the reason, and the page's tonnages are said to be the whole port's
        for word in ("Mauritania", "Mexico", "Thailand", "India", "Colombia", "Madagascar", "the United States", "South Africa", "not of grain"):
            self.assertIn(word, rule["reason"], word)
        self.assertNotIn("names China, Morocco and Algeria as its main destinations", rule["reason"])

    def test_the_lane_pages_of_the_partners_of_the_two_ports_print_both_distances_and_the_principal_is_the_one_of_the_rule(self):
        seen = {}
        for g in ("wheat", "barley", "corn", "rapeseed", "sunflower-seed", "rapeseed-meal"):
            for lane in load(DATA, "freight", "lanes", g + ".json")["lanes"]:
                if lane["id"].split(":")[1].startswith("FRA-") and lane["load"][0] in ("FRURO", "FRLPE"):
                    c = lane["id"].split("-")[-1]
                    other = {"FRURO": "FRLPE", "FRLPE": "FRURO"}[lane["load"][0]]
                    self.assertEqual(lane["portBasis"], "open", lane["id"])
                    self.assertIn(other, {o["load"] for o in lane["opts"]}, lane["id"])  # a distance from the other port (a lane with several discharge ports also lists those of the main port)
                    self.assertEqual(lane["load"][0], "FRURO" if c in self.NAMED + self.SEAS else "FRLPE", lane["id"])
                    seen[lane["id"]] = 1
        self.assertGreater(len(seen), 10, seen)

    def test_sugar_and_the_imports_are_not_touched_by_the_rule(self):
        self.assertIn(P.assign("FRA", "BRA", "sugar").main.load, ("FRLEH", "FRFOS"))  # no page names sugar at a grain port
        self.assertEqual(P.assign("BRA", "FRA", "soymeal").main.discharge, "FRMTX")  # the Montoir row of the soya meal imports
        rule = next(r for r in P.COAST_RULES if r["id"] == "fra-grain-ports")
        self.assertEqual(rule["role"], "load")
        self.assertNotIn("sugar", rule["groups"])

    def test_the_rule_says_it_is_an_assumption_and_why(self):
        rule = next(r for r in P.COAST_RULES if r["id"] == "fra-grain-ports")
        for word in ("Atlas assumption", "no page gives the split", "China, Morocco and Algeria", "first European port for cereals", "second French port"):
            self.assertIn(word, rule["reason"])
        every = next(r for r in P.COAST_RULES if r["id"] == "fra-coast-grain")["reason"]
        # the old text said that Spain and Portugal were "left open"; the rule gives Spain Fos and Portugal the Atlantic ports
        self.assertNotIn("Spain, Portugal, Morocco and Algeria are left", every)
        self.assertIn("Portugal is on the Atlantic side", every)

    def test_both_ports_are_the_principal_port_of_lanes_and_the_shares_follow_the_pages(self):
        tot = {"FRURO": 0.0, "FRLPE": 0.0}
        for g in ("wheat", "barley", "corn", "sorghum", "rice"):
            rows, _ = pairs(g)
            for (o, d), r in rows.items():
                if o == "FRA" and r["m"] in (0, 1) and r["load_port"] in tot:
                    tot[r["load_port"]] += r["kt"]
        self.assertGreater(tot["FRLPE"], 0)
        self.assertGreater(tot["FRURO"], tot["FRLPE"])
        # the pages: 12.7 Mt of cereals at Rouen in 2023 for the whole port, 3.0 to 3.5 Mt a year at La Pallice: the atlas does not exceed the first
        # and stays in the range of the second (the split is the atlas's rule, not a measured share)
        self.assertLess(tot["FRURO"] / 1000, 12.7)
        # FNCI (GV8A.1): the eight "less common destinations" of the Rouen page took 0.93 Mt from La Pallice, which now loads under the range of its page
        # (the other port stays an option of every pair, and no page gives the split): METHODOLOGY says so, with these figures
        self.assertLess(tot["FRLPE"] / 1000, 3.0, tot)
        self.assertTrue(2.0 <= tot["FRLPE"] / 1000, tot)

    def test_no_french_grain_route_leaves_a_port_other_than_the_three(self):
        for g in ("wheat", "barley", "corn", "rapeseed", "soymeal", "sunflower-meal", "rapeseed-meal"):
            rows, _ = pairs(g)
            self.assertLessEqual({r["load_port"] for (o, d), r in rows.items() if o == "FRA" and r["load_port"]}, {"FRURO", "FRLPE", "FRFOS"}, g)

    def test_the_river_leg_is_for_rouen_only(self):
        """FNCE's leg of the Seine applies to Rouen: a lane that loads at La Pallice carries none."""
        seen = 0
        for g in ("wheat", "barley", "corn", "rapeseed", "sorghum", "pulses", "soybeans", "soymeal", "rapeseed-meal", "sunflower-seed"):
            _, p = pairs(g)
            self.assertEqual(set(p.get("rivers") or {}) & {"FRLPE", "FRFOS"}, set(), g)
            seen += "FRLPE" in [x[0] for x in p["ports"]]
        self.assertGreater(seen, 5)

    def test_methodology_says_what_the_pages_give_and_that_the_split_is_the_rule(self):
        text = " ".join(read("METHODOLOGY.md").split())
        for word in ("fra-grain-ports", "12.7 Mt", "3.0 to 3.5 Mt", "not a measured share", "the eleven partners", "Mauritania, Mexico, Thailand, India, Colombia, Madagascar, the United States and",
                     "not of grain", "the page names the partner at a port, so that port"):
            self.assertIn(word, text)
        self.assertNotIn("the partners that the Rouen page names (China, Morocco, Algeria)", text)
        self.assertNotIn("the principal port of no pair changed", text)

    def test_methodology_figures_of_the_french_grain_ports_are_the_files(self):
        """FNCI (GV8A.1): the tonnes by port, the lanes and the eight partners' pairs, recomputed from the pairs and lanes files as the text says."""
        text = " ".join(read("METHODOLOGY.md").split())
        tot = {"FRURO": 0.0, "FRLPE": 0.0, "FRFOS": 0.0}
        eight = {"MRT", "MEX", "THA", "IND", "COL", "MDG", "USA", "ZAF"}
        P_GRAIN = ("wheat", "barley", "corn", "sorghum", "rice", "pulses", "rapeseed", "soybeans", "sunflower-seed", "soymeal", "sunflower-meal", "rapeseed-meal")
        moved, kt = 0, 0.0
        for g in ("wheat", "barley", "corn", "sorghum", "rice"):
            rows, _ = pairs(g)
            for (o, d), r in rows.items():
                if o == "FRA" and r["m"] in (0, 1) and r["load_port"] in tot:
                    tot[r["load_port"]] += r["kt"]
        for g in P_GRAIN:
            rows, _ = pairs(g)
            for (o, d), r in rows.items():
                if o == "FRA" and d in eight and r["m"] in (0, 1):
                    self.assertEqual(r["load_port"], "FRURO", (g, d))
                    moved += 1
                    kt += r["kt"]
        self.assertIn(f"loads {tot['FRURO'] / 1000:.1f} Mt of French wheat, barley, corn, sorghum and rice by sea at Rouen, {tot['FRLPE'] / 1000:.1f} Mt at La Pallice and {tot['FRFOS'] / 1000:.1f} Mt at Fos", text)
        self.assertIn(f"moved the principal port of {moved} of the", text)
        self.assertIn(f"{kt / 1000:.2f} Mt in all", text)
        n = {"FRURO": 0, "FRLPE": 0}
        for g in P_GRAIN:
            for lane in load(DATA, "freight", "lanes", g + ".json")["lanes"]:
                if lane["id"].split(":")[1].startswith("FRA-") and lane["load"][0] in n:
                    n[lane["load"][0]] += 1
        self.assertIn(f"(24 of the 24 lanes of French grain, oilseeds and meal that load at Rouen or La Pallice, {n['FRURO']} and {n['FRLPE']}, carry the other port as an option", text)
        self.assertEqual(sum(n.values()), 24)


class F4TurkishScrap(unittest.TestCase):
    def test_the_mediterranean_basin_has_two_options_and_the_black_sea_one(self):
        for g in ("ferrous-scrap", "pig-iron", "dri"):
            a = P.assign("USA", "TUR", g)
            self.assertEqual((a.basis, a.rule, a.main.discharge), ("open", "tur-coast", "TRISK"), g)
            self.assertEqual({o.discharge for o in a.options}, {"TRISK", "TRIZM"}, g)
            b = P.assign("UKR", "TUR", g)
            self.assertEqual((b.basis, b.main.discharge, len(b.options)), ("rule", "TRERE", 1), g)
            c = P.assign("TUR", "ITA", g)
            self.assertEqual({o.load for o in c.options}, {"TRISK", "TRIZM"}, g)

    def test_the_lane_page_says_that_no_source_gives_the_split(self):
        rows, p = pairs("ferrous-scrap")
        r = rows[("USA", "TUR")]
        self.assertEqual(r["dis_port"], "TRISK")
        lanes = load(DATA, "freight", "lanes", "ferrous-scrap.json")["lanes"]
        lane = next(ln for ln in lanes if ln["id"] == "ferrous-scrap:USA-TUR")
        self.assertEqual((lane["discharge"], lane["portBasis"]), (["TRISK"], "open"))  # the lane page reads "no source says how this trade splits between ports"
        self.assertIn("TRIZM", [o["discharge"] for o in lane["opts"]])

    def test_every_profile_with_a_freight_block_says_what_a_port_share_is(self):
        """The block's heading note must say before the figures that the percentage after a port is an allocation by the atlas's rules (FNCG: the
        component prints `freight.note`)."""
        n = 0
        for name in ("TUR", "FRA", "DEU", "CHN", "USA"):
            fr = load(DATA, "countries", "profiles", name + ".json").get("freight")
            self.assertTrue(fr, name)
            self.assertIn("allocates to that typical port by its rules", fr["note"])
            self.assertIn("an allocation, not a count of what the port handles", fr["note"])
            n += 1
        self.assertEqual(n, 5)

    def test_the_turkey_page_keeps_the_principal_port_and_its_share_is_the_allocation(self):
        """The share printed for a port is the share of the atlas's tonnes that its typical port carries: Izmir is an option, never the principal port, so it
        carries none of them; the sentence that says so is `freight.note`."""
        fr = load(DATA, "countries", "profiles", "TUR.json")["freight"]
        scrap = next(x for x in fr["imports"] if x["g"] == "ferrous-scrap")
        self.assertEqual(scrap["ports"][0]["name"], "Iskenderun")
        self.assertNotIn("Izmir", [p["name"] for p in scrap["ports"]])
        self.assertIn("allocation", fr["note"])


def _released_routes():
    return load(FIXTURES, "released_routes_digest.json")


class F5ReleasedRoutes(unittest.TestCase):
    # the released routes that end, with the reason: the corridor of each was a French one, and the French ports changed it
    # (the seventh release) gen-sugar-sea-sea leaves the cap of 122 generated routes: the LPG seaborne total grows by 3.8 Mt (the part by sea of the United States to
    # Mexico pair), the generated LPG corridors that reach the target share of it are one more (gen-lpg-med-med), and the cap takes the last route of the list
    ENDED = {
        "gen-sugar-sea-sea": "the cap of 122 generated routes: one more LPG corridor is needed to reach the target share of the larger LPG seaborne total (gen-lpg-med-med)",
        "gen-steel-med-nw-europe": "its corridor was French steel from the Mediterranean to North-West Europe: France loads steel at Le Havre for North-West Europe",
        "gen-wheat-med-waf": "its corridor was French wheat from the Mediterranean to West Africa: France loads wheat at Rouen or La Pallice for West Africa",
    }

    def test_every_released_route_is_there_but_the_two_that_ended_with_the_french_ports(self):
        now = {r["id"]: r for r in load(DATA, "freight", "routes.json")}
        for rid, e in _released_routes().items():
            if rid in self.ENDED:
                self.assertNotIn(rid, now, rid)
            else:
                self.assertIn(rid, now, rid)
        self.assertEqual(set(self.ENDED) & set(_released_routes()), set(self.ENDED))

    def test_the_hand_written_routes_are_identical_field_by_field(self):
        now = {r["id"]: r for r in load(DATA, "freight", "routes.json")}
        n = 0
        for rid, e in _released_routes().items():
            if not e["generated"]:
                self.assertEqual(digest(now[rid]), e["sha256"], rid)
                n += 1
        self.assertGreater(n, 100)

    def test_the_cap_of_the_first_package_gives_back_what_the_cap_of_120_took(self):
        self.assertEqual(GR.TOTAL_CAP, 122)
        self.assertEqual(GR.GROUP_CAP_MORE, {"wheat": 13})
        now = {r["id"] for r in load(DATA, "freight", "routes.json")}
        self.assertNotIn("gen-sugar-sea-sea", now)  # see ENDED
        self.assertIn("gen-lpg-med-med", now)
        self.assertIn("gen-wheat-canada-west-r-east-asia", now)
        later = set().union(*(gs for gs, _ in GR.LATER_GROUPS))
        gen = [r for r in load(DATA, "freight", "routes.json") if r.get("generated") and r["cargoes"][0] not in later]
        self.assertEqual(len(gen) - sum(1 for r in gen if re.match(r"gen-(" + "|".join(sorted(later)) + r")-", r["id"])), GR.TOTAL_CAP)

    def test_the_cap_order_is_the_same_below_the_cap(self):
        """The first corridors of the groups are kept first and the others by their tonnes: a larger cap only adds the next ones."""
        per = {"a": [{"new": 5.0}, {"new": 1.0}], "b": [{"new": 3.0}, {"new": 2.0}]}
        small, large = GR.cap_order(per, 3, first=frozenset({"a"})), GR.cap_order(per, 4, first=frozenset({"a"}))
        self.assertEqual(large[:3], small)

    def test_a_pair_that_carries_no_corridor_is_left_out(self):
        rows = [{"o": "AAA", "d": "BBB", "t": 2.0, "m": 0, "load": 0, "dis": 1, "nm": 1000, "cls": 1}, {"o": "CCC", "d": "BBB", "t": 2.0, "m": 0, "load": 0, "dis": 1, "nm": 1000, "cls": 1}]
        p = {"seaborne": 4.0, "rows": rows}
        ports = [["PA", "A"], ["PB", "B"]]
        zone = lambda code: "z-" + code  # noqa: E731
        every = GR.select_group("g", p, ports, {}, zone)
        self.assertEqual(sum(len(c["rows"]) for c in every), 2)
        left = GR.select_group("g", p, ports, {}, zone, excluded={("g", "AAA", "BBB")})
        self.assertEqual([r["o"] for c in left for r in c["rows"]], ["CCC"])

    def test_the_note_says_pair_in_the_singular_for_one_pair(self):
        n = 0
        for r in load(DATA, "freight", "routes.json"):
            m = re.search(r"the (\d+) recorded seaborne .+? pairs? whose typical ports", r.get("notes") or "")
            if r.get("generated"):
                self.assertTrue(m, r["id"])
                self.assertEqual(" pair whose" in m.group(0), m.group(1) == "1", r["id"])
                n += m.group(1) == "1"
        self.assertGreater(n, 5)

    def test_no_pair_of_a_released_group_outside_france_differs_from_the_released_pairs(self):
        """A digest of the released pairs files (65b007f) without the pairs that touch France: port, class, distance and passages of every other pair
        are the released ones (the Canadian, Mexican, Russian and Turkish rules changed no pair of a released group)."""
        fixture = load(FIXTURES, "released_pairs_digest.json")
        self.assertEqual(len(fixture), 42)
        for g, h in fixture.items():
            self.assertEqual(digest(decoded_rows(load(DATA, "freight", "pairs", g + ".json"))), h, g)

    def test_methodology_no_longer_says_that_no_earlier_route_moved(self):
        text = " ".join(read("METHODOLOGY.md").split())
        self.assertNotIn("so that no earlier route moved", text)
        for word in ("gen-steel-med-nw-europe", "gen-wheat-med-waf", "gen-sugar-sea-sea", "gen-wheat-canada-west-r-east-asia"):
            self.assertIn(word, text)


class F6LandlockedTradingCentre(unittest.TestCase):
    ENTRIES = {"sulphur-qat-che": ("sulphur", "QAT", "CHE"), "copper-refined-zmb-che": ("copper-refined", "ZMB", "CHE"),
               "iron-ore-mys-che": ("iron-ore", "MYS", "CHE"), "iron-ore-che-mys": ("iron-ore", "CHE", "MYS")}

    def test_the_four_pairs_have_a_caveat_with_figures_from_the_data(self):
        cv = load(DATA, "freight", "caveats.json")
        for cid, (g, o, d) in self.ENTRIES.items():
            e = cv[cid]
            self.assertEqual((e["kind"], e["group"], e["o"], e["d"]), ("landlocked-centre", g, o, d))
            t = e["text"]
            for part in ("Customs data record", "recorded exports", "recorded imports", "CEPII BACI", "no coast",
                         "a possible reading, not established here", "The tonnes stay in the tables and are counted at the passages of the route",
                         "no generated route is built from this pair"):
                self.assertIn(part, t, (cid, part))
        t = cv["sulphur-qat-che"]["text"]
        self.assertIn("1.13 Mt of sulphur from Qatar to Switzerland", t)
        self.assertIn("98.8% of Switzerland's recorded imports", t)
        self.assertRegex(t, r"23\.\d% of Qatar's recorded exports")
        self.assertIn("probably ends elsewhere", t)
        self.assertIn("probably started elsewhere", cv["iron-ore-che-mys"]["text"])
        self.assertIn("refined copper from Zambia", cv["copper-refined-zmb-che"]["text"])

    def test_the_shares_are_those_of_the_pairs_file(self):
        rows, p = pairs("sulphur")
        r = rows[("QAT", "CHE")]
        self.assertAlmostEqual(r["kt"], 1130, delta=2)
        qat = sum(x["kt"] for (o, d), x in rows.items() if o == "QAT")
        che = sum(x["kt"] for (o, d), x in rows.items() if d == "CHE")
        txt = load(DATA, "freight", "caveats.json")["sulphur-qat-che"]["text"]
        self.assertIn(f"{100 * r['kt'] / che:.1f}% of Switzerland's recorded imports", txt)
        self.assertGreater(qat, r["kt"])

    def test_the_tonnes_stay_in_the_pairs_and_the_lane_carries_the_caveat(self):
        rows, _ = pairs("sulphur")
        self.assertEqual(rows[("QAT", "CHE")]["dis_port"], "NLRTM")  # still drawn to Rotterdam, the general port of a landlocked country
        self.assertTrue(rows[("QAT", "CHE")]["f"] & 2)  # the caveat bit of the pair
        lane = next(ln for ln in load(DATA, "freight", "lanes", "sulphur.json")["lanes"] if ln["id"] == "sulphur:QAT-CHE")
        self.assertEqual(lane["caveat"], "sulphur-qat-che")

    def test_no_route_is_generated_from_the_pair(self):
        routes = load(DATA, "freight", "routes.json")
        self.assertNotIn("gen-sulphur-meg-nw-europe", {r["id"] for r in routes})
        self.assertFalse([r["name"] for r in routes if r["name"] == "Sulphur: Qatar to Switzerland"])
        for r in routes:
            for c in r.get("corridor") or []:
                for cid, (g, o, d) in self.ENTRIES.items():
                    if r.get("generated") and c.get("g") == g and o in c["o"] and d in c["d"]:
                        self.fail((r["id"], cid))

    def test_the_released_routes_hold_none_of_them(self):
        for rid, e in _released_routes().items():
            self.assertNotEqual(rid, "gen-sulphur-meg-nw-europe")

    def test_the_package_cap_gives_the_slot_to_another_corridor(self):
        """The sulphur corridor of the package NC1 cap of 20 is not generated: the next corridor of the package takes its place, the cap is still full."""
        gs, cap = next((gs, cap) for gs, cap in GR.LATER_GROUPS if "sulphur" in gs)
        two = ("gen-npk-two-nutrient-", "gen-ammonium-nitrate-limestone-")  # the groups of package FNCB share a prefix with npk and ammonium nitrate
        ids = [r["id"] for r in load(DATA, "freight", "routes.json") if r.get("generated") and not r["id"].startswith(two)
               and any(r["id"].startswith(f"gen-{g}-") for g in gs)]
        self.assertEqual((len(ids), cap), (20, 20))
        self.assertNotIn("gen-sulphur-meg-nw-europe", ids)
        self.assertIn("gen-sulphur-us-gulf-ecsa", ids)  # the next corridor of the package: sulphur from the US Gulf to the east coast of South America

    def test_the_pages_carry_the_row_and_the_page_notes(self):
        def row(d, key, iso):
            t = d.get(key) if isinstance(d.get(key), dict) else next(x["table"] for x in d["extra"] if x["key"] == key)
            return next(r for r in t["rows"] if r["c"] == iso)
        cv = load(DATA, "freight", "caveats.json")
        sul, ore, cu = (load(DATA, "commodities", f"{p}.json") for p in ("sulphur", "iron-ore", "copper"))
        self.assertIn(cv["sulphur-qat-che"]["text"], row(sul, "exports", "QAT")["n"])
        self.assertIn(cv["sulphur-qat-che"]["text"], row(sul, "imports", "CHE")["n"])
        self.assertIn(cv["sulphur-qat-che"]["text"], sul["notes"])
        # joined to a note that the row has already, the full stop that ends the caveat goes (build_commodities.joinn)
        self.assertIn(cv["iron-ore-mys-che"]["text"].rstrip("."), row(ore, "exports", "MYS")["n"])
        self.assertIn(cv["iron-ore-che-mys"]["text"].rstrip("."), row(ore, "imports", "MYS")["n"])
        self.assertIn(cv["iron-ore-che-mys"]["text"], ore["notes"])
        self.assertIn(cv["copper-refined-zmb-che"]["text"].rstrip("."), row(cu, "refined-imports", "CHE")["n"])
        self.assertIn(cv["copper-refined-zmb-che"]["text"].rstrip("."), row(cu, "refined-exports", "ZMB")["n"])
        self.assertIn(cv["copper-refined-zmb-che"]["text"], cu["notes"])
        # one note on the copper row, not the old hand-written one beside the new
        self.assertEqual(row(cu, "refined-imports", "CHE")["n"].count("commodity-trading centre"), 0)
        # no figure of the page moved: the tonnes of the pair are in the tables
        self.assertGreater(row(sul, "imports", "CHE")["v"], 1.0)


class F7MozambiqueCoke(unittest.TestCase):
    def frame(self):
        import pandas as pd
        rows = [{"year": y, "group": "coke", "o": o, "d": d, "t": t, "usd": t * 0.3} for y in (2016, 2024) for o, d, t in
                (("CHN", "IND", 3e6), ("POL", "DEU", 2e6), ("MOZ", "IND", 6e6), ("MOZ", "ARE", 4e5))]
        rows.append({"year": 2024, "group": "coal", "o": "MOZ", "d": "IND", "t": 5e6, "usd": 5e5})  # Mozambique's coal is not touched
        return pd.DataFrame(rows)

    def test_every_row_of_mozambique_under_the_coke_group_is_out_in_every_year(self):
        import clean as C
        c = C.clean(self.frame())
        self.assertEqual(sorted(set(c[c["group"] == "coke"]["o"])), ["CHN", "POL"])
        self.assertEqual(len(c[c["group"] == "coal"]), 1)
        self.assertEqual(len(c[c["group"] == "coke"]), 4)
        gone = [r for r in C.LAST_DROPPED if r["rule"] == "misclassified"]
        self.assertEqual(sorted((r["year"], r["d"]) for r in gone), [(2016, "ARE"), (2016, "IND"), (2024, "ARE"), (2024, "IND")])
        self.assertIn("EIA series of coke production", gone[0]["reason"])
        self.assertEqual(C.ESTIMATE_ROWS, {})

    def test_the_cache_series_without_mozambique(self):
        import pandas as pd
        import clean as C
        df = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        df = df[df["group"] == "coke"]
        c = C.clean(df)
        self.assertNotIn("MOZ", set(c["o"]))
        self.assertGreater(len(df[df["o"] == "MOZ"]), 0)
        year = c[c["year"] == 2024]
        self.assertAlmostEqual(year["t"].sum() / 1e6, 32.916, delta=0.01)
        # China to Brazil 2009: rule 4 does not reach coke (the group is out of the set, D6 of FNCD, still true without Mozambique): the reported tonnage stays
        r = c[(c["o"] == "CHN") & (c["d"] == "BRA") & (c["year"] == 2009)].iloc[0]
        self.assertEqual((r["t"], r["imputed"]), (108190.0, False))

    def test_k14_finds_zimbabwe_only_and_the_caveat_of_mozambique_is_gone(self):
        cv = load(DATA, "freight", "caveats.json")
        self.assertNotIn("nop-coke-MOZ", cv)
        self.assertIn("nop-coke-ZWE", cv)
        found = [r["o"] for r in load(ROOT, "pipeline", "cache", "trade_checks.json")["findings"] if r["check"] == "K14"]
        self.assertEqual(found, ["ZWE"])
        prof = load(DATA, "countries", "profiles", "MOZ.json")
        self.assertFalse([g for g in prof.get("gaps", []) if g["g"] == "coke"])

    def test_the_coke_page_says_what_was_left_out_and_why(self):
        met = load(DATA, "commodities", "met-coal.json")
        tabs = {x["key"]: x["table"] for x in met["extra"]}
        self.assertNotIn("MOZ", [r["c"] for r in tabs["coke-customs-exports"]["rows"]])
        note = next(n for n in met["notes"] if n.startswith("Mozambique's exports under this code are left out"))
        for part in ("left out of the coke tables, lanes, passage estimates, history and totals of the commodity pages and of the commodity blocks of the country pages",
                     "in each of the 16 years 2005 to 2024", "1.63 Mt in 2024", "EIA series of coke production gives Mozambique none",
                     "a hypothesis, not established", "its coke production series reads 0 in every year from 1980 to 2025 (its coke export series reads 33 kt in 2023 and 0 in the other years)",
                     "6.5 Mt of metallurgical coal exports in 2025", "The all-goods list of the country page of Mozambique shows the customs value of heading 2704 as declared",
                     "These rows are not counted"):
            self.assertIn(part, note)
        self.assertNotIn("every table, lane and total of the atlas", note)
        self.assertNotIn("of coal exports in 2025", note)
        gap = next(n for n in met["notes"] if n.startswith("Coke and semi-coke of coal, lignite or peat (HS 270400): the tables hold"))
        for part in ("95% of the 34.6 Mt", "1.63 Mt are the exports of Mozambique, left out as a misclassification (rule 5 of the cleaning rules", "pairs under the threshold"):
            self.assertIn(part, gap)
        self.assertTrue(gap.endswith("."))
        self.assertAlmostEqual(tabs["coke-customs-exports"]["world"], 32.916, delta=0.01)

    def test_the_country_page_of_mozambique_has_the_heading_only_in_its_all_goods_list(self):
        """FNCI (GV8A.4): what the note says is true: the customs value of heading 2704 is in the list of all goods (the unfiltered file), and nowhere else on the page
        as a coke export; the coke balance takes no exports line."""
        prof = load(DATA, "countries", "profiles", "MOZ.json")
        row = next(r for r in prof["basket"]["exports"]["rows"] if r.get("hs4") == "2704")
        self.assertEqual(row["usd"], 0.257)
        self.assertIn("(USD 0.257 billion in 2024)", " ".join(read("METHODOLOGY.md").split()))
        self.assertFalse([k for k in prof.get("exports", []) if "coke" in (k.get("label") or "").lower()])
        bal = next(b for b in prof["balance"] if b.get("t") == "coke-customs-exports")
        self.assertIsNone(bal["net"]["exp"])
        self.assertIn("no exports line, taken as 0", bal["net"]["n"])

    def test_the_two_notes_quote_the_eia_series_for_what_they_are(self):
        """FNCI (GV8A.3): the series 130-1 and 130-4 are metallurgical coal, not all coal (7-4); the coke export series 21-4 is read for the note."""
        import checks as K
        self.assertEqual(K.NO_PRODUCTION["coke"][1:4], (("130-1", "MT"), ("130-4", "MT"), ("21-4", "MT")))
        met = load(DATA, "commodities", "met-coal.json")
        for n in met["notes"]:
            if n.startswith(("Mozambique's exports", "Customs data record")):
                self.assertNotRegex(n, r"(?<!metallurgical )coal exports in 20\d\d", n[:40])
                self.assertNotRegex(n, r", coal for instance", n[:40])
        text = " ".join(read("METHODOLOGY.md").split())
        self.assertIn("the metallurgical coal series 130-1, production, and 130-4, exports, of the Metallurgical coal page, not all coal, series 7-4", text)
        self.assertNotIn("with the coal series 130-1 and 130-4", text)
        self.assertIn("metallurgical coal where the page's EIA tables show the country as a producer or exporter of it", text)
        self.assertIn("Zimbabwe: 399 kt in 2022 and 5 kt in 2023", text)
        self.assertIn("its coke export series, 21-4, reads 33 kt in 2023 and 0 in the other years", text)

    def test_qa_lists_the_dropped_rows(self):
        qa = read("pipeline", "commodities", "QA.md")
        self.assertIn("Rule 5 (DROP)", qa)
        self.assertRegex(qa, r"coke 2024, Mozambique to [A-Za-z ]+: ")

    def test_methodology_names_the_rule_the_series_and_the_years_above_eia(self):
        """The coke paragraph names rule 5, Mozambique's coke, and the years where the customs series stays above the EIA export table of the page,
        recomputed from the history file of the page."""
        text = " ".join(read("METHODOLOGY.md").split())
        for word in ("(`DROP`)", "drops all of Mozambique's coke by rule 5"):
            self.assertIn(word, text)
        t = load(DATA, "commodities", "history", "met-coal.json")["t"]
        eia, cus = t["coke-exports"], t["coke-customs-exports"]
        e, c = dict(zip(eia["years"], eia["world"])), dict(zip(cus["years"], cus["world"]))
        common = sorted(y for y in c if y in e)
        above = [y for y in common if c[y] > e[y]]
        big = [y for y in common if c[y] > 1.1 * e[y]]

        def lst(ys):
            ys = [str(y) for y in ys]
            return ", ".join(ys[:-1]) + " and " + ys[-1]
        self.assertIn(f"is above the EIA export table of the same page in {len(above)} of the {len(common)} years {common[0]} to {common[-1]}", text)
        self.assertIn(f"and more than 10% above it in {lst(big)}", text)
        self.assertIn(f"(below it in {lst([y for y in common if y not in above])})", text)

    def test_the_estimate_reasons_agree_with_the_cache(self):
        """GV6B.4: the figures of the reasons that were looser than the cache, now read from it."""
        import clean as C
        why = C.KEEP_REPORTED
        self.assertIn("382 and 145 times the USD 1.8 and 4.7 million", why[("coke", "ZWE", "COD", 2006)])
        self.assertIn("45 to 201 times theirs", why[("ammonium-nitrate", "FRA", "OMN", 2010)])  # 77.548 / 1.709 and / 0.385 (review GV9B.3)
        self.assertIn("in the 23 years of the cache (2002 to 2024)", why[("coke", "LBY", "USA", 2004)])
        self.assertIn("0.7 to 7.3 kt", why[("graphite", "JPN", "MEX", 2002)])
        self.assertIn("81 times", why[("ammonium-sulphate", "UKR", "DZA", 2015)])
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import test_fncb
        self.assertIn("2.0 kt in 2011 (kept as reported", test_fncb.ESTIMATE_RIGHT[("sulphur", "CHE", "ZMB", 2012)])

    def test_a_range_of_values_quoted_in_a_reason_is_the_range_of_the_cache(self):
        """FNCI (GV8A.2): "every other year (USD 4.5 to 39.7 million)" was USD 3.1 to 39.6 million in the cache. Both bounds of every range of values that a
        reason gives for the other years of the pair are the cache's, at the precision written."""
        import pandas as pd
        import clean as C
        df = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        n = 0
        for (g, o, d, y), why in C.KEEP_REPORTED.items():
            for m in re.finditer(r"USD ([\d.]+) to ([\d.]+) million\)", why):
                if "other year" not in why:
                    continue
                other = df[(df["group"] == g) & (df["o"] == o) & (df["d"] == d) & (df["year"] != y)]["usd"] / 1e3  # the cache gives thousands of USD
                for quoted, value in ((m.group(1), other.min()), (m.group(2), other.max())):
                    dec = len(quoted.split(".")[1]) if "." in quoted else 0
                    self.assertEqual(quoted, f"{value:.{dec}f}", (g, o, d, y, why))
                n += 1
        self.assertGreaterEqual(n, 2)
        self.assertIn("USD 3.1 to 39.6 million", C.KEEP_REPORTED[("dri", "CHN", "SAU", 2018)])


class F8GapNote(unittest.TestCase):
    def groups(self):
        import build_commodities as B
        main = {g for g, *_ in B.TRADE.values()}
        extra = {x[0] for xs in B.EXTRA_GROUPS.values() for x in xs}
        hand = {x[0] for xs in B.HAND_GROUPS.values() for x in xs}
        return B, main, extra, hand

    def test_every_group_that_main_ranks_by_hand_is_in_the_table_of_hand_groups(self):
        B, main, extra, hand = self.groups()
        src = read("pipeline", "commodities", "build_commodities.py")
        ranked = set(re.findall(r'baci\.ranked\("([a-z-]+)"', src))
        self.assertTrue(ranked)
        self.assertLessEqual(ranked - {"spodumene"}, main | extra | hand, ranked - main - extra - hand)

    def test_every_group_of_a_page_under_97_percent_of_the_file_has_the_note_and_it_ends_with_a_full_stop(self):
        import pandas as pd
        import clean as C
        B, main, extra, hand = self.groups()
        tot = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_group_totals.csv"))
        tot = tot[tot["year"] == 2024].set_index("group")
        c = C.clean(pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz")))
        held = c[c["year"] == 2024].groupby("group")["t"].sum()
        low = sorted(g for g in main | extra | hand if g in tot.index and held.get(g, 0) < 0.97 * tot.loc[g, "t"])
        self.assertIn("zinc-metal", low)
        self.assertIn("coke", low)
        notes = []
        for f in os.listdir(os.path.join(DATA, "commodities")):
            if f.endswith(".json") and f not in ("index.json", "companies.json"):
                d = load(DATA, "commodities", f)
                if isinstance(d, dict):
                    notes += [n for n in d.get("notes") or [] if "the tables hold" in n]
        self.assertTrue(all(n.endswith(".") for n in notes))
        # one note per group under the threshold that a page shows as a table (the two pages that hold a group twice do not exist)
        self.assertEqual(len(notes), len(low), (len(notes), low))
        zinc = next(n for n in notes if n.startswith("Unwrought zinc (HS 7901): the tables hold 5.06 Mt, 50% of the 10.1 Mt"))
        self.assertIn("most of it is one row, Spain to Mexico: 5.02 Mt reported for USD 61 million, 0.021 Mt after the rule", zinc)

    def test_methodology_lists_the_groups_of_the_build(self):
        text = " ".join(read("METHODOLOGY.md").split())
        i = text.index("in the 2024 build:")
        listed = text[i:i + 400]
        for word in ("unwrought zinc", "coke", "crude oil", "natural graphite", "unwrought tin", "rare-earth metals", "lithium", "silver"):
            self.assertIn(word, listed)


class F9TransitNote(unittest.TestCase):
    def test_the_note_is_built_from_the_row_of_the_exporters_table(self):
        for page, share in (("chromium", None), ("ferro-alloys", None)):
            d = load(DATA, "commodities", page + ".json")
            row = next(r for r in d["imports"]["rows"] if r["c"] == "MOZ")
            ex = next(r for r in d["exports"]["rows"] if r["c"] == "MOZ")
            kt = ex["v"] * 1000
            self.assertIn(f"has no production line in the tables of this page and exports of {kt:,.0f} kt", row["n"])
            self.assertIn(f"{100 * ex['v'] / d['exports']['world']:.2f}% of the world exports", row["n"])
            own = ex["v"] / row["v"]
            self.assertIn(f"{100 * own:.2f}% of its own imports" if own < 0.01 else f"{100 * own:.1f}% of its own imports", row["n"])
            self.assertTrue(any("although it has no production line" in n and f"exports of {kt:,.0f} kt" in n for n in d["notes"]), page)

    def test_the_note_never_denies_an_export_to_a_country_of_the_exporters_table(self):
        import glob
        n = 0
        for f in glob.glob(os.path.join(DATA, "commodities", "*.json")):
            if f.endswith(("index.json", "companies.json")):
                continue
            d = load(f)
            if not isinstance(d, dict):
                continue
            tabs = [(k, d[k]) for k in ("exports", "imports") if isinstance(d.get(k), dict)] + [(x["key"], x["table"]) for x in d.get("extra") or []]
            for key, t in tabs:
                stem = key[:-len("imports")] if key.endswith("imports") else None
                ex = next((tt for kk, tt in tabs if stem is not None and kk == stem + "exports"), d.get("exports") if key == "imports" else None)
                exporters = {r["c"] for r in (ex or {}).get("rows", [])}
                for r in t.get("rows", []):
                    txt = r.get("n") or ""
                    if "cargo in transit to a port" in txt:
                        n += 1
                        self.assertNotRegex(txt, r"not (a|an) (producer or an )?exporter|neither a producer nor an exporter", (f, key, r["c"]))
                        self.assertIn(r["c"], exporters)
            for note in d.get("notes") or []:
                if "cargo in transit to a port" in note:
                    self.assertNotRegex(note, r"neither a producer nor an exporter|not a producer or an exporter")
        self.assertEqual(n, 2)

    def test_a_country_with_no_export_line_says_so(self):
        import metals as MET
        e = {"u": "Mt", "world": 20.0, "rows": []}
        self.assertEqual(MET._export_clause(e, 0.0, 8.8), "no export line")
        self.assertEqual(MET._export_clause({"u": "Mt", "world": 28.0}, 0.0413, 8.8), "exports of 41 kt (0.15% of the world exports, 0.47% of its own imports)")
        self.assertEqual(MET._export_clause({"u": "Mt", "world": 28.0}, 0.0051, 8.8), "exports of 5.1 kt (0.02% of the world exports, 0.06% of its own imports)")


class F10LegacyFertiliserPortOfTheExporterOnly(unittest.TestCase):
    GROUPS = ("ammonia", "uan", "phosphoric-acid", "sulphur")

    def test_the_legacy_port_serves_the_role_load_only(self):
        for g in self.GROUPS:
            self.assertEqual([c[0] for c in P.candidates("CAN", g, "load")], ["CAVAN"], g)
            self.assertEqual(P.candidates("CAN", g, "discharge")[0][2], P.BASIS_GENERAL, g)
            self.assertNotIn("CAVAN", [c[0] for c in P.candidates("CAN", g, "discharge")], g)

    def test_mexican_phosphoric_acid_for_canada_lands_at_montreal(self):
        for g in ("phosphoric-acid", "ammonia"):
            self.assertNotEqual(P.assign("MEX", "CAN", g).main.discharge, "CAVAN", g)
        self.assertEqual(P.assign("MEX", "CAN", "phosphoric-acid").main.discharge, "CAMTR")
        rows, _ = pairs("phosphoric-acid")
        r = rows[("MEX", "CAN")]
        self.assertEqual((r["load_port"], r["dis_port"]), ("MXVER", "CAMTR"))
        self.assertLess(r["nm"], 4500)  # 3,375 nm, not 5,679 through Panama

    def test_other_importers_of_the_four_groups_are_unaffected(self):
        for g in self.GROUPS:
            rows, _ = pairs(g)
            for (o, d), r in rows.items():
                if d == "CAN" and o in ("BEL", "LTU"):
                    self.assertEqual(r["dis_port"], "CAMTR", (g, o))

    def test_the_exporters_keep_their_legacy_port(self):
        for g in self.GROUPS:
            self.assertEqual(P.candidates("SAU", g, "load"), [("SAJUB", None, P.BASIS_LEGACY)], g)


class F11TransitPortOfALandlockedCountry(unittest.TestCase):
    def test_djibouti_among_the_importers_of_the_two_nutrient_compounds_has_a_row_note_and_a_page_note(self):
        d = load(DATA, "commodities", "npk.json")
        t = next(x["table"] for x in d["extra"] if x["key"] == "two-nutrient-imports")
        i, row = next((k, r) for k, r in enumerate(t["rows"]) if r["c"] == "DJI")
        note = row["n"]
        self.assertIn(f"Customs data record {row['v']:.2f} Mt of ", note)
        self.assertIn(f"imported by Djibouti in 2024 (rank {i + 1}, {100 * row['v'] / t['world']:.1f}% of the world imports), against 0.04 Mt in 2015", note)
        self.assertIn("Djibouti is the port that the atlas's transit tables give Ethiopia, which has no coast", note)
        self.assertIn("Principal maritime outlet for Ethiopia's trade: Wikipedia, https://en.wikipedia.org/wiki/Port_of_Djibouti", note)
        self.assertIn("no import of this product by Ethiopia is recorded in 2024, against 0.96 Mt in 2023", note)
        self.assertTrue(note.endswith("a possible reading, not established here"))
        self.assertIn(note + ".", d["notes"])

    def test_the_note_is_built_from_the_entry_of_the_transit_table(self):
        self.assertEqual(P.transit_for("ETH", P.segment("npk-two-nutrient"), "npk-two-nutrient")[0], "DJJIB")
        self.assertEqual(P.port("DJJIB")["name"], "Djibouti")
        import build_commodities as B
        self.assertEqual(B.TRANSIT_PORT_ROWS, [("npk", "two-nutrient-imports", "DJI", "npk-two-nutrient", "ETH")])

    def test_no_other_importer_has_the_note(self):
        d = load(DATA, "commodities", "npk.json")
        for x in d["extra"]:
            for r in x["table"].get("rows", []):
                if r["c"] != "DJI":
                    self.assertNotIn("transit tables give", r.get("n", ""))


if __name__ == "__main__":
    unittest.main()
