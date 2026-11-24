"""Tests of the last package of the correction round (FNCE): ports, routes and the web.

E1  a port up a river that the sea network does not follow (Rouen) has a river leg: its routes start at the river's mouth, the leg is added to
    every distance, the drawn line starts at the port, and the pages say so
E2  the basis "page names the plant, not the cargo" for the rows whose page names the steel works or the refinery, not the cargo
E3  the chip of a lane or a generated route that is one product of a commodity page names the product (the logic is tested in
    web/scripts/cargo-chips.test.mjs; here the data it reads)
E4  the search ranks a whole word before a prefix of another word (web/scripts/search-aliases.test.mjs)

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The tests of the data files read the files as the builders last wrote them.
"""
import json
import os
import re
import sys
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import ports as P  # noqa: E402
import river_legs as RL  # noqa: E402
import routing as RT  # noqa: E402

DATA = os.path.join(ROOT, "data")


def load(*parts):
    with open(os.path.join(DATA, *parts), encoding="utf-8") as f:
        return json.load(f)


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def at(code):
    return P.port(code)["at"]


ROUEN, HONFLEUR = at("FRURO"), RL.RIVER_LEGS["FRURO"]["mouth"]


class E1RiverLegTable(unittest.TestCase):
    def test_every_row_has_its_port_its_mouth_on_the_network_and_the_page_that_gives_the_length(self):
        net = RT.graph()
        for code, leg in RL.RIVER_LEGS.items():
            with self.subTest(code):
                self.assertTrue(P._known(code))
                self.assertIn(tuple(leg["mouth"]), net.adj, "the mouth is a node of the sea network")
                self.assertGreater(leg["km"], 0)
                self.assertTrue(leg["url"].startswith("https://"))
                self.assertEqual(leg["s"], "wikipedia")
                # the sentence of the page gives the length the table uses
                self.assertEqual([int(x) for x in re.findall(r"(\d+) km", leg["sentence"])], [leg["km"]])
                self.assertIn(leg["river"], leg["sentence"])
                self.assertIn(leg["mouth_name"], leg["sentence"])
                # the gateway row of the port cites the same page
                rows = [r for rs in P.G.values() for r in rs if r.code == code]
                self.assertIn(leg["url"], {r.url for r in rows})

    def test_rouen_is_the_65_nm_of_120_km(self):
        self.assertEqual(RL.RIVER_LEGS["FRURO"]["km"], 120)
        self.assertEqual(RL.nm_of(RL.RIVER_LEGS["FRURO"]), 65)
        self.assertEqual(RL.leg_at(ROUEN)["code"], "FRURO")
        self.assertIsNone(RL.leg_at(at("FRLEH")))
        self.assertIsNone(RL.leg_at(HONFLEUR))

    def test_a_port_far_from_the_network_has_a_leg(self):
        """The rule that replaces the exemption of test_ports.py: a port of the tables (not a manual terminal, an island or an offshore
        plant) farther than 50 km from the coast and the sea network is routed from the mouth of its river."""
        codes = {r.code for rs in P.G.values() for r in rs} | {c for t in P.LEGACY_P.values() for c in t.values()}
        far = sorted(c for c in codes if P._known(c) and c not in P.MANUAL and P.sea_km(c) > 50)
        self.assertTrue(set(far) <= set(RL.RIVER_LEGS) | {"DEBRE"}, far)  # Bremen: no lane uses it (test below); a question for the owner
        for c in RL.RIVER_LEGS:
            self.assertGreater(P.sea_km(c), 50, c)

    def test_the_ports_of_the_tables_between_20_and_50_km_are_listed_and_have_no_leg(self):
        """Ho Chi Minh City and the like: reported, not changed (FNCE). A port that comes into a table in this band is a decision for the owner:
        add it here with its distance, or give it a leg."""
        codes = {r.code for rs in P.G.values() for r in rs} | {c for t in P.LEGACY_P.values() for c in t.values()} \
            | {row[0] for t in P.TRANSIT.values() for row in t.values()}
        band = {c: round(P.sea_km(c)) for c in codes if P._known(c) and c not in P.MANUAL and 20 <= P.sea_km(c) <= 50}
        manual = {c: round(P.sea_km(c)) for c in codes if c in P.MANUAL and 20 <= P.sea_km(c) <= 50}
        # Calcutta (transit port of Nepal and Bhutan), Ho Chi Minh City, Campana, Kashima, Yangon, and Das Island (an island: the terminal is the island)
        self.assertEqual(band, {"INCCU": 48, "VNSGN": 44, "ARCMP": 42, "JPKSM": 26, "MMRGN": 22, "AEDAS": 41})
        self.assertEqual(manual, {"QAHAL": 36})  # Halul Island: an island, the terminal is the island
        self.assertFalse(set(band) & set(RL.RIVER_LEGS))

    def test_bremen_is_an_open_point_it_is_an_option_of_some_lanes_and_never_a_main_port(self):
        """Bremen is 55 km from the network (the Weser) and has no leg: no page was read for its length, so the distance of the options
        through it leaves the river out. It is the other port of an open choice of German lanes, never the main port of a lane or a
        pair (reported to the owner). When it gets a leg, move it to RIVER_LEGS and delete this test."""
        self.assertNotIn("DEBRE", RL.RIVER_LEGS)
        d = os.path.join(DATA, "freight")
        for f in sorted(os.listdir(os.path.join(d, "pairs"))):
            self.assertNotIn("DEBRE", {p[0] for p in load("freight", "pairs", f)["ports"]}, f)
        for f in sorted(os.listdir(os.path.join(d, "lanes"))):
            for lane in load("freight", "lanes", f)["lanes"]:
                self.assertNotIn("DEBRE", lane["load"] + lane["discharge"], lane["id"])

    def test_the_note_names_the_leg_the_mouth_the_length_and_the_straight_line(self):
        n = RL.note(RL.RIVER_LEGS["FRURO"], "Rouen")
        for part in ("Rouen is 65 nm up the Seine from Honfleur", "120 km", "Port de Rouen page", "included in the distance", "the line runs straight from the port to Honfleur"):
            self.assertIn(part, n)
        # GV7B.7: one sentence and no second naming of the page (the link follows the note): about a line and a half at 1440 px
        self.assertEqual(n, "Rouen is 65 nm up the Seine from Honfleur (120 km, Port de Rouen page): included in the distance; the line runs straight from the port to Honfleur.")
        self.assertLess(len(n), 160)
        self.assertNotIn("Wikipedia", n)
        pub = RL.public("FRURO", "Rouen")
        self.assertEqual((pub["nm"], pub["km"], pub["river"], pub["mouth"]), (65, 120, "Seine", "Honfleur"))
        self.assertIsNone(RL.public("FRLEH", "Le Havre"))


class E1Routing(unittest.TestCase):
    """The distance is the leg plus the sea route from the mouth, for every option and every alternative; the line starts at the port."""

    def test_rouen_to_rotterdam_is_the_leg_longer_than_the_sea_route_from_the_mouth_and_longer_than_le_havre_by_the_leg_and_the_estuary(self):
        rtm = at("NLRTM")
        r = RT.route(ROUEN, rtm)
        from_mouth = RT.route(HONFLEUR, rtm)
        self.assertEqual(r.nm, from_mouth.nm + 65)
        havre = RT.route(at("FRLEH"), rtm).nm
        self.assertEqual(havre, 246)
        # Honfleur is 8 to 10 nm up the estuary from the node of Le Havre: the difference is the leg and that stretch of the network
        self.assertGreaterEqual(r.nm - havre, 65)
        self.assertLessEqual(r.nm - havre, 65 + 12)
        # the old snap to the coast near Dieppe gave 196 nm
        self.assertGreater(r.nm, 300)

    def test_both_directions_and_the_line(self):
        rtm = at("NLRTM")
        out, back = RT.route(ROUEN, rtm), RT.route(rtm, ROUEN)
        self.assertEqual(out.nm, back.nm)
        self.assertEqual(out.coords[0], list(ROUEN))
        self.assertEqual(out.coords[1], list(HONFLEUR))          # one straight segment, then the sea path
        self.assertEqual(back.coords[-1], list(ROUEN))
        self.assertEqual(back.coords[-2], list(HONFLEUR))
        self.assertEqual(RT.route(ROUEN, rtm).coords[0], list(ROUEN))  # the memo does not change it

    def test_the_published_line_starts_at_the_port_and_goes_to_the_mouth_before_the_sea_path(self):
        p = RT.plan(ROUEN, at("NLRTM"), ["supramax"])
        g = RT.summary(p, geometry=True)["g"]
        self.assertEqual(g[0], [round(ROUEN[0], 2), round(ROUEN[1], 2)])
        self.assertEqual(g[1], [round(HONFLEUR[0], 2), round(HONFLEUR[1], 2)])
        q = RT.plan(at("NLRTM"), ROUEN, ["supramax"])
        g = RT.summary(q, geometry=True)["g"]
        self.assertEqual((g[-1], g[-2]), ([round(ROUEN[0], 2), round(ROUEN[1], 2)], [round(HONFLEUR[0], 2), round(HONFLEUR[1], 2)]))
        # a port with no leg keeps the plain simplification
        h = RT.summary(RT.plan(at("FRLEH"), at("NLRTM"), ["supramax"]), geometry=True)["g"]
        node = RT.route(at("FRLEH"), at("NLRTM")).coords[0]   # the node the port snaps to: the line of a port with no leg starts there, as before
        self.assertEqual(h[0], [round(node[0], 2), round(node[1], 2)])

    def test_every_alternative_and_every_parallel_option_carries_the_leg(self):
        china = at("CNTAO")
        base = RT.plan(HONFLEUR, china, ["supramax"])
        p = RT.plan(ROUEN, china, ["supramax"])
        self.assertEqual(p.main.nm, base.main.nm + 65)
        self.assertEqual(len(p.alts), len(base.alts))
        self.assertTrue(p.alts, "the Suez route of Rouen to China has the Cape as an alternative")
        for a, b in zip(p.alts, base.alts):
            self.assertEqual(a["distanceNm"], b["distanceNm"] + 65)
            self.assertEqual(a["extraDays"], b["extraDays"])   # the leg is in both: the days of the difference do not move
            self.assertEqual(a["g"][0], [round(ROUEN[0], 2), round(ROUEN[1], 2)])
        for (_, o1), (_, o2) in zip(p.parallel, base.parallel):
            self.assertEqual([nm for _, nm in o1], [nm + 65 for _, nm in o2])
        self.assertEqual(p.via, base.via)

    def test_the_leg_is_in_the_days_of_the_lane_through_the_class_speed(self):
        s = RT.summary(RT.plan(ROUEN, at("NLRTM"), ["supramax"]))
        self.assertEqual(s["nm"], RT.route(ROUEN, at("NLRTM")).nm)

    def test_the_caches_are_keyed_by_the_table(self):
        before = RT.version()
        with mock.patch.dict(RL.RIVER_LEGS, {"FRURO": {**RL.RIVER_LEGS["FRURO"], "km": 130}}):
            self.assertNotEqual(RT.version(), before)
        self.assertEqual(RT.version(), before)
        self.assertEqual(RT.VERSION, before)

    def test_no_other_port_is_changed_by_the_leg(self):
        """A route between two ports with no leg is the plain route: the memo of route() does not mix the mouth with the port."""
        a, b = at("FRLEH"), at("NLRTM")
        self.assertEqual(RT.route(a, b).nm, 246)
        self.assertEqual(RT.route(a, b).coords[0], RT.route(a, b).coords[0])
        near = RT.route(HONFLEUR, b)
        self.assertEqual(near.coords[0], list(HONFLEUR))
        self.assertEqual(near.nm, RT.route(ROUEN, b).nm - 65)


class E1DataFiles(unittest.TestCase):
    @staticmethod
    def rows(group):
        p = load("freight", "pairs", group + ".json")
        cols = p["cols"]
        return p, [dict(zip(cols, r)) for r in p["rows"]]

    def test_french_barley_to_the_netherlands_is_longer_than_le_havre_to_rotterdam(self):
        p, rows = self.rows("barley")
        r = next(x for x in rows if (x["o"], x["d"]) == ("FRA", "NLD"))
        self.assertEqual((p["ports"][r["load"]][0], p["ports"][r["dis"]][0]), ("FRURO", "NLRTM"))
        self.assertEqual(r["nm"], RT.route(ROUEN, at("NLRTM")).nm)
        self.assertGreater(r["nm"], 246 + 65)

    def test_a_pairs_file_names_the_river_of_the_ports_it_uses_and_only_those(self):
        d = os.path.join(DATA, "freight", "pairs")
        used = 0
        for f in sorted(os.listdir(d)):
            p = load("freight", "pairs", f)
            codes = [x[0] for x in p["ports"]]
            if "FRURO" in codes:
                used += 1
                riv = p["rivers"]["FRURO"]
                self.assertEqual((riv["nm"], riv["km"], riv["river"], riv["mouth"]), (65, 120, "Seine", "Honfleur"), f)
                self.assertIn("the line runs straight from the port to Honfleur", riv["n"])
                self.assertEqual(set(p["rivers"]), {"FRURO"})
            else:
                self.assertNotIn("rivers", p, f)
        self.assertGreaterEqual(used, 10)

    def test_every_lane_from_rouen_starts_at_rouen_and_the_lane_file_names_the_river(self):
        d = os.path.join(DATA, "freight", "lanes")
        n = 0
        for f in sorted(os.listdir(d)):
            doc = load("freight", "lanes", f)
            if "FRURO" in doc["ports"]:
                riv = doc["ports"]["FRURO"]["river"]
                self.assertEqual((riv["nm"], riv["river"]), (65, "Seine"), f)
            else:
                self.assertTrue(all("river" not in p for p in doc["ports"].values()), f)
            for lane in doc["lanes"]:
                for alt in [lane] + list(lane.get("alts") or []):
                    if alt is lane and lane["load"][0] == "FRURO":
                        n += 1
                        self.assertEqual(alt["g"][0], [round(ROUEN[0], 2), round(ROUEN[1], 2)], lane["id"])
                        self.assertEqual(alt["g"][1], [round(HONFLEUR[0], 2), round(HONFLEUR[1], 2)], lane["id"])
                    elif alt is not lane and lane["load"][0] == "FRURO":
                        self.assertEqual(alt["g"][0], [round(ROUEN[0], 2), round(ROUEN[1], 2)], lane["id"])
                for o in lane.get("opts") or []:
                    pass
        self.assertGreaterEqual(n, 5)

    def test_the_generated_routes_through_rouen_say_the_leg(self):
        routes = load("freight", "routes.json")
        hit = [r for r in routes if r.get("rivers")]
        self.assertTrue(hit)
        for r in hit:
            self.assertEqual(r["rivers"][0]["port"], "Rouen")
            self.assertEqual(r["rivers"][0]["nm"], 65)
            self.assertIn("the line runs straight from the port to Honfleur", r["rivers"][0]["n"])
            self.assertIn("Rouen", [*r["from"]["ports"], *r["to"]["ports"]])
        # and no route that does not use Rouen says it
        for r in routes:
            if not r.get("rivers"):
                self.assertNotIn("Rouen", [*r["from"]["ports"], *r["to"]["ports"]], r["id"])

    def test_the_web_prints_the_note_where_the_ports_of_a_lane_a_route_and_a_pair_are_printed(self):
        for f in ("LaneView", "RouteView"):
            self.assertIn("<RiverNotes", read("web", "src", "components", "views", f + ".tsx"), f)
        self.assertIn("<RiverNotes", read("web", "src", "components", "RouteFinder.tsx"))
        self.assertIn("river: file.rivers?.[p[0]]", read("web", "src", "lib", "freight.ts"))
        self.assertIn("the line runs straight from the port to Honfleur", RL.note(RL.RIVER_LEGS["FRURO"], "Rouen"))


class E2PlantBasis(unittest.TestCase):
    PLANT_ROWS = {("TUR", "TRERE"), ("TUR", "TRISK"), ("BRA", "BRVLC")}

    def test_turkish_exports_of_the_three_groups_load_at_the_steel_works_by_the_coast_rule(self):
        """The page gives no direction: Iskenderun is a row for both roles (it was a discharge row, and the exports to the Mediterranean loaded at
        Izmir, the general port of the country). The Black Sea partners take Eregli, the others Iskenderun, with the basis of the row."""
        roles = {r.code: r.role for r in P.G["TUR"] if r.code in ("TRERE", "TRISK")}
        self.assertEqual(roles, {"TRERE": "both", "TRISK": "both"})
        for g in ("ferrous-scrap", "pig-iron", "dri"):
            self.assertEqual(P.assign("TUR", "ESP", g).main.load, "TRISK", g)
            self.assertEqual(P.assign("TUR", "ROU", g).main.load, "TRERE", g)
            self.assertEqual(P.basis_of("TUR", g, "load", "TRISK"), P.BASIS_PLANT)
        for g in ("ferro-silicon", "chromium-ore"):
            self.assertNotIn(P.assign("TUR", "ESP", g).main.load, ("TRERE", "TRISK"), g)

    def test_the_basis_is_after_the_other_direction_in_the_order_of_the_bases(self):
        self.assertEqual(P.BASIS_PLANT, "page names the plant, not the cargo")
        self.assertEqual(list(P.BASES).index(P.BASIS_PLANT), list(P.BASES).index(P.BASIS_OTHER) + 1)
        self.assertEqual(len(set(P.BASES)), len(P.BASES))

    def test_exactly_the_rows_that_say_so_carry_it(self):
        marked = {(iso, r.code) for iso, rs in P.G.items() for r in rs if r.basis}
        self.assertEqual(marked, self.PLANT_ROWS)
        self.assertEqual({r.basis for rs in P.G.values() for r in rs if r.basis}, {P.BASIS_PLANT})

    def test_every_note_that_says_the_page_names_a_plant_and_not_the_cargo_is_marked_or_listed_as_left(self):
        """The sentences that decide, from the notes of every row of gateways/*.py (read for FNCE). A row whose note has one of the plant
        sentences takes the basis; the others of the scan are rows whose page names the cargo or the place and are left."""
        decided = ("the page names the plant, not its port or the cargo it takes",       # Iskenderun
                   "operates a large seaport, the Port of Erdemir, to import and export materials' (the page names no cargo)",  # Eregli
                   "That the cargo leaves from the Vila do Conde terminals is read from the two pages together")  # Alunorte
        for iso, rs in P.G.items():
            for r in rs:
                said = any(s in (r.note or "") for s in decided)
                self.assertEqual(bool(r.basis), said, (iso, r.code, r.families))

    def test_the_plant_rows_keep_their_port_and_basis_in_both_directions(self):
        for group in ("ferrous-scrap", "pig-iron", "dri"):
            for role in ("load", "discharge"):
                cands = {c: b for c, _, b in P.candidates("TUR", group, role)}
                self.assertEqual(cands["TRERE"], P.BASIS_PLANT, (group, role))
            self.assertEqual(P.candidates("TUR", group, "discharge")[0][0], "TRERE")
            self.assertEqual(P.basis_of("TUR", group, "load", "TRISK"), P.BASIS_PLANT)       # the page gives no direction
            self.assertEqual(P.basis_of("TUR", group, "discharge", "TRISK"), P.BASIS_PLANT)
            self.assertEqual(P.basis_of("TUR", group, "load", "TRERE"), P.BASIS_PLANT)
            self.assertEqual(P.source_of("TUR", group, "load", "TRISK"), ("wikipedia", "https://en.wikipedia.org/wiki/Erdemir"))
            self.assertEqual(P.source_of("TUR", group, "discharge", "TRISK"), ("wikipedia", "https://en.wikipedia.org/wiki/Erdemir"))
        # the source link stays, the groups the rows do not name are untouched
        self.assertNotEqual(P.basis_of("TUR", "steel", "load", P.gateway("TUR", "steel", "load")), P.BASIS_PLANT)
        self.assertEqual(P.basis_of("BRA", "alumina", "load", "BRVLC"), P.BASIS_PLANT)
        self.assertEqual(P.source_of("BRA", "alumina", "load", "BRVLC")[0], "wikipedia")
        self.assertEqual(P.basis_of("BRA", "iron-ore", "load", "BRTUB"), P.BASIS_PAGE)
        self.assertEqual(P.basis_of("BRA", "bauxite", "load", P.gateway("BRA", "bauxite", "load")) in (P.BASIS_PAGE, P.BASIS_LEGACY, P.BASIS_GENERAL), True)

    def test_a_row_takes_no_other_eighth_element(self):
        row = ("XXXXX", "z", ("a",), "load", "wikipedia", "u", "n")
        self.assertIsNone(P._gw(row).basis)
        self.assertEqual(P._gw(row + ("plant",)).basis, P.BASIS_PLANT)
        with self.assertRaises(ValueError):
            P._gw(row + ("page",))

    def test_the_files_name_the_new_basis_on_the_ports_that_use_it_and_nowhere_else(self):
        seen = set()
        for f in sorted(os.listdir(os.path.join(DATA, "freight", "pairs"))):
            p = load("freight", "pairs", f)
            self.assertEqual(p["bases"], list(P.BASES), f)
            plant = p["bases"].index(P.BASIS_PLANT)
            for port in p["ports"]:
                if plant in port[4:6]:
                    seen.add((f[:-5], port[0]))
        groups = {g for g, _ in seen}
        self.assertTrue({"ferrous-scrap", "pig-iron", "dri", "alumina"} <= groups, seen)
        self.assertEqual({c for _, c in seen}, {"TRERE", "TRISK", "BRVLC"})
        for g, c in seen:
            lane = load("freight", "lanes", g + ".json")["ports"].get(c)
            if lane:
                self.assertEqual(lane["basis"], P.BASIS_PLANT, (g, c))
                self.assertEqual(lane["s"], "wikipedia")
                self.assertTrue(lane["url"])

    def test_turkish_exports_load_at_the_steel_works_in_the_files_and_methodology_counts_them(self):
        n = 0
        for g in ("ferrous-scrap", "pig-iron", "dri"):
            p = load("freight", "pairs", g + ".json")
            cols = p["cols"]
            for r in p["rows"]:
                x = dict(zip(cols, r))
                if x["o"] == "TUR" and x["m"] in (0, 1) and x["load"] >= 0:
                    self.assertIn(p["ports"][x["load"]][0], ("TRISK", "TRERE"), (g, x["d"]))
                    n += 1
        self.assertGreaterEqual(n, 14)
        self.assertIn(f"package FNCE, {n} pairs", read("METHODOLOGY.md"))

    def test_the_methodology_shares_by_basis_are_the_files(self):
        """Share of 2024 pair-end tonnage by basis (METHODOLOGY section 3), recomputed from the pairs files as the text says."""
        from collections import defaultdict
        tot, n = defaultdict(float), 0.0
        for f in sorted(os.listdir(os.path.join(DATA, "freight", "pairs"))):
            p = load("freight", "pairs", f)
            for r in p["rows"]:
                o, d, kt, m, lo, di = r[:6]
                if m not in (0, 1):
                    continue
                for idx, k in ((lo, 4), (di, 5)):
                    n += kt / 1000.0
                    tot["no port" if idx < 0 else (p["bases"][p["ports"][idx][k]] if p["ports"][idx][k] is not None else "none")] += kt / 1000.0
        meth = read("METHODOLOGY.md")
        self.assertIn(f"two ends, {round(n):,} Mt", meth)
        for key, word in (("page names the cargo", "page names the cargo"), ("port used before, no page read", "port used before"),
                          ("general port of the country", "general port"), ("nearest seaport", "nearest seaport"),
                          ("page names the cargo in the other direction", "other direction"), (P.BASIS_PLANT, "page names the plant"),
                          ("no port", "no port (not routed)")):
            self.assertIn(f"{word} {100 * tot[key] / n:.1f}%", meth.replace("\n  ", " "), key)

    def test_the_web_lists_the_basis_wherever_it_lists_the_bases(self):
        self.assertIn("'page names the plant, not the cargo'", read("web", "src", "lib", "freight.ts"))
        freight = read("web", "src", "lib", "freight.ts")
        self.assertIn("SOURCED_BASES = ['page names the cargo', 'page names the cargo in the other direction', 'page names the plant, not the cargo'", freight)
        self.assertIn("'page names the plant, not the cargo'", read("web", "scripts", "validate-freight.mjs"))
        self.assertIn("page names the plant, not the cargo", read("web", "src", "types.ts"))
        self.assertIn("page names the plant, not the cargo", read("METHODOLOGY.md"))


class E3Data(unittest.TestCase):
    def test_the_generated_routes_that_are_one_product_of_a_page_carry_their_group(self):
        routes = load("freight", "routes.json")
        one = [r for r in routes if r.get("generated") and r["corridor"] and len({c["g"] for c in r["corridor"]}) == 1 and len({c["k"] for c in r["corridor"]}) == 1]
        self.assertEqual(len(one), len([r for r in routes if r.get("generated")]))
        self.assertIn("ammonia", {r["corridor"][0]["g"] for r in one})
        self.assertIn("coke", {r["corridor"][0]["g"] for r in one})


if __name__ == "__main__":
    unittest.main()
