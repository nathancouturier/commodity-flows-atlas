"""Tests of the first correction package after the review of the three commodity packages (FNCA): the ports and the routes of the new groups.

A1  the fertiliser groups of OWN_FAMILY keep the legacy port of their segment (Jubail for Saudi fertiliser), not the general port (Jeddah)
A2  France has two seaboards: Rouen and La Pallice (grain), Montoir (ammonia, soya meal), Le Havre and Fos (general ports), chosen by a coast rule
A3  Turkey's steel works (Eregli, Iskenderun) take scrap, pig iron and direct-reduced iron, so that the Black Sea flows are routed
A4  the groups above 10 Mt of seaborne trade of a later package keep two generated corridors before the cap is shared by tonnes
A5  sunflower and rapeseed oil: the ports of palm and soybean oil are shown as the general port of the country
A6  the ferro-alloys keep their hyphen in the names of routes and notes

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The tests of the data files read the files as the builders last wrote them.
"""
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import checks as K  # noqa: E402
import generated_routes as GR  # noqa: E402
import ports as P  # noqa: E402

DATA = os.path.join(ROOT, "data")
LEGACY_FERT = ("ammonia", "uan", "phosphoric-acid", "sulphur")
# the groups of the three packages: the pairs of every other group are the released ones
EARLIER_UNMOVED = ("steel", "urea", "dap", "potash", "phosphate-rock", "wheat", "corn", "rapeseed", "soymeal", "sugar", "palm-oil", "soyoil")


def pairs(group):
    """The pairs file of a group, decoded: {(o, d): row as a dict} and its port table."""
    with open(os.path.join(DATA, "freight", "pairs", group + ".json"), encoding="utf-8") as f:
        p = json.load(f)
    cols = p["cols"]
    out = {}
    for r in p["rows"]:
        row = dict(zip(cols, r))
        row["load_port"] = p["ports"][row["load"]][0] if row["load"] >= 0 else None
        row["dis_port"] = p["ports"][row["dis"]][0] if row["dis"] >= 0 else None
        out[(row["o"], row["d"])] = row
    return out, p


class A1LegacyPortOfTheFertilisers(unittest.TestCase):
    def test_the_four_groups_keep_the_legacy_port_ahead_of_the_general_port(self):
        """Saudi ammonia, UAN, phosphoric acid and sulphur load at Jubail like Saudi DAP, MAP and urea, not at Jeddah on the Red Sea."""
        self.assertEqual(set(LEGACY_FERT), set(P.LEGACY_OWN_FAMILY))
        self.assertTrue(P.LEGACY_OWN_FAMILY <= P.OWN_FAMILY)
        # the legacy entry is the exporter's own port: for the role "load" only (FNCF, review GV6A.5: it landed Mexican phosphoric acid for Canada at
        # Vancouver); the discharge port of these groups is the general port of the country, as before package FNCA
        for g in LEGACY_FERT:
            self.assertEqual(P.candidates("SAU", g, "load"), [("SAJUB", None, P.BASIS_LEGACY)], g)
            self.assertNotIn("SAJUB", [c[0] for c in P.candidates("SAU", g, "discharge")], g)
        for g in ("urea", "dap", "monoammonium-phosphate"):
            self.assertEqual(P.candidates("SAU", g, "load")[0][0], "SAJUB", g)

    def test_sugar_and_coke_still_take_only_a_row_that_names_them(self):
        """Their legacy segment entry is a grain or a coal port: the exclusion of OWN_FAMILY stays for them."""
        for g in ("sugar", "coke"):
            self.assertIn(g, P.OWN_FAMILY)
            self.assertNotIn(g, P.LEGACY_OWN_FAMILY)
        self.assertNotIn("SAJUB", [c[0] for c in P.candidates("SAU", "sugar", "load")])

    def test_trinidad_is_unchanged(self):
        """No page names a port of Trinidad and Tobago for fertiliser: its legacy 'any' port serves ammonia as it serves urea and DAP."""
        for g in LEGACY_FERT + ("urea", "dap"):
            self.assertEqual([c[0] for c in P.candidates("TTO", g, "load")], ["TTPTF"], g)

    def test_no_saudi_lane_of_these_groups_loads_on_the_red_sea(self):
        for g in LEGACY_FERT:
            rows, _ = pairs(g)
            for (o, d), r in rows.items():
                if o == "SAU" and r["load"] >= 0:
                    self.assertEqual(r["load_port"], "SAJUB", (g, d))

    def test_the_hormuz_estimate_of_sulphur_counts_the_saudi_tonnes_in_its_lower_figure(self):
        """Before: at least 16.6 Mt of 42.5 Mt (the Saudi sulphur loaded at Jeddah crossed no Hormuz); the Gulf loads of Saudi Arabia are now in it."""
        with open(os.path.join(DATA, "freight", "chokepoints.json"), encoding="utf-8") as f:
            ch = json.load(f)
        h = next(c for c in ch if c["id"] == "hormuz")
        e = next(x for x in h["estimates"] if x["k"] == "sulphur")
        low = float(e["f"]["n"].split("at least ")[1].split(" Mt")[0])
        rows, _ = pairs("sulphur")
        saudi = sum(r["kt"] for (o, d), r in rows.items() if o == "SAU" and r["m"] in (0, 1) and r["load"] >= 0) / 1000
        self.assertGreater(saudi, 5)
        self.assertGreater(low, 16.6 + 0.5 * saudi)


class A2France(unittest.TestCase):
    NW = {"NLD", "BEL", "GBR", "IRL", "DEU", "DNK", "NOR", "SWE", "POL", "LTU", "FIN", "EST"}

    def test_france_has_the_ports_its_cargoes_use(self):
        codes = {r.code for r in P.G["FRA"]}
        self.assertTrue({"FRFOS", "FRURO", "FRLPE", "FRMTX", "FRLEH"} <= codes)
        for r in P.G["FRA"]:
            self.assertTrue(P._known(r.code), r.code)
            if r.code in ("FRURO", "FRLPE", "FRMTX", "FRLEH") and r.src != "giignl-2026":
                self.assertEqual(r.src, "wikipedia", r)
                self.assertTrue(r.url.startswith(("https://fr.wikipedia.org/wiki/", "https://en.wikipedia.org/wiki/")), r)
        by = {(r.code, tuple(sorted(r.families))): r.role for r in P.G["FRA"]}
        self.assertEqual(by[("FRURO", ("grain",))], "load")
        self.assertEqual(by[("FRMTX", ("ammonia",))], "both")

    def test_the_coast_rules_choose_the_port_by_the_partner(self):
        a = P.assign
        self.assertEqual((a("FRA", "NLD", "barley").main.load, a("FRA", "NLD", "barley").rule), ("FRURO", "fra-grain-ports"))
        self.assertEqual(a("FRA", "ITA", "wheat").main.load, "FRFOS")
        self.assertEqual(a("FRA", "CHN", "wheat").main.load, "FRURO")  # the Rouen page names China among its destinations
        self.assertEqual(a("FRA", "DZA", "wheat").main.load, "FRURO")  # ... and Algeria and Morocco (rule fra-grain-ports, FNCF: both ports stay options)
        self.assertEqual(a("NLD", "FRA", "uan").main.discharge, "FRLEH")
        self.assertEqual(a("ITA", "FRA", "uan").main.discharge, "FRFOS")
        self.assertEqual(a("FRA", "BEL", "sunflower-oil").main.load, "FRLEH")
        self.assertEqual(a("FRA", "NLD", "ammonia").main.load, "FRMTX")
        self.assertEqual(a("BRA", "FRA", "soymeal").main.discharge, "FRMTX")
        self.assertEqual(a("FRA", "NLD", "steel").main.load, "FRLEH")
        self.assertEqual(a("FRA", "JPN", "steel").main.load, "FRFOS")
        self.assertEqual(a("RUS", "FRA", "steel").main.discharge, "FRFOS")  # Russia's general port is Novorossiysk
        self.assertEqual(a("RUS", "FRA", "dap").main.discharge, "FRLEH")    # its fertiliser port is Ust-Luga, in the Baltic

    def test_the_rules_are_written_for_a_known_port_in_each_zone(self):
        ids = {r["id"] for r in P.COAST_RULES if r["country"] == "FRA"}
        self.assertEqual(ids, {"fra-grain-ports", "fra-coast-grain", "fra-coast", "fra-coast-box"})  # fra-grain-ports: FNCF, exports of grain by port
        for r in P.COAST_RULES:
            if r["country"] == "FRA":
                for zones in r["zones"].values():
                    for z in zones:
                        self.assertIn(z, P.ZONES)

    def test_no_french_lane_of_a_group_with_a_french_port_to_north_west_europe_loads_at_fos(self):
        for g in ("barley", "wheat", "corn", "rapeseed", "rapeseed-meal", "sunflower-oil", "rapeseed-oil", "uan", "ammonium-nitrate", "npk",
                  "urea", "dap", "potash", "steel", "aluminium"):
            rows, _ = pairs(g)
            for (o, d), r in rows.items():
                if o == "FRA" and d in self.NW and r["load"] >= 0:
                    self.assertNotEqual(r["load_port"], "FRFOS", (g, d))
                if d == "FRA" and o in self.NW and r["dis"] >= 0:
                    self.assertNotEqual(r["dis_port"], "FRFOS", (g, o))

    def test_barley_to_the_netherlands_is_drawn_from_rouen_by_the_direct_route(self):
        rows, _ = pairs("barley")
        r = rows[("FRA", "NLD")]
        self.assertEqual((r["load_port"], r["dis_port"]), ("FRURO", "NLRTM"))
        self.assertLess(r["nm"], 400)  # 4.1 times the direct distance from Fos

    def test_only_french_pairs_of_the_earlier_groups_moved(self):
        """Every lane of the released groups that touches a country other than France is the one the coast rules of Canada, Mexico, Russia and Turkey gave before."""
        for g in EARLIER_UNMOVED:
            rows, _ = pairs(g)
            for (o, d), r in rows.items():
                if "FRA" not in (o, d) and r["load"] >= 0 and "TUR" not in (o, d):
                    self.assertNotIn("FRURO", (r["load_port"], r["dis_port"]))
                    self.assertNotIn("FRLEH", (r["load_port"], r["dis_port"]))


class A3Turkey(unittest.TestCase):
    def test_the_steel_works_ports_are_rows_of_the_three_groups(self):
        rows = {r.code: r for r in P.G["TUR"] if r.code in ("TRERE", "TRISK")}
        self.assertEqual(set(rows), {"TRERE", "TRISK"})
        for r in rows.values():
            self.assertEqual(set(r.families), {"ferrous-scrap", "pig-iron", "dri"})
            self.assertTrue(r.url.startswith("https://en.wikipedia.org/wiki/"), r.url)
        # FNCE: the page gives no direction, so Iskenderun is a row for both roles, as Eregli (it was a discharge row, and the exports of scrap and
        # pig iron to the Mediterranean loaded at Izmir, the general port)
        self.assertEqual(rows["TRISK"].role, "both")
        self.assertEqual(rows["TRERE"].role, "both")

    def test_the_black_sea_partners_take_eregli_and_the_others_iskenderun(self):
        for g in ("ferrous-scrap", "pig-iron", "dri"):
            self.assertEqual(P.assign("RUS", "TUR", g).main.discharge, "TRERE", g)
            self.assertEqual(P.assign("ROU", "TUR", g).main.discharge, "TRERE", g)
            self.assertEqual(P.assign("GBR", "TUR", g).main.discharge, "TRISK", g)
        for g in ("ferro-silicon", "chromium-ore"):  # no page: nothing changes for them
            self.assertNotIn(P.assign("RUS", "TUR", g).main.discharge, ("TRERE", "TRISK"), g)

    def test_the_largest_black_sea_flows_to_turkey_are_routed(self):
        for g, o in (("pig-iron", "RUS"), ("ferrous-scrap", "ROU"), ("ferrous-scrap", "RUS"), ("dri", "RUS"), ("pig-iron", "UKR")):
            rows, _ = pairs(g)
            r = rows[(o, "TUR")]
            self.assertGreaterEqual(r["load"], 0, (g, o))
            self.assertEqual(r["dis_port"], "TRERE", (g, o))
            self.assertLess(r["nm"], 600, (g, o))
            self.assertEqual(r["via"], 0, (g, o))  # no tracked chokepoint: Eregli is west of the Bosphorus on the Black Sea

    def test_the_chromite_of_turkey_still_loads_at_the_nearest_seaport(self):
        """No page read names a Turkish chromite port: left as it was, and said so in the gateway table."""
        rows, _ = pairs("chromium-ore")
        self.assertEqual(rows[("TUR", "CHN")]["load_port"], "TRSSX")
        from gateways import coasts
        self.assertIn("Chromite: no page read names a Turkish chromite port", coasts.UNSOURCED["TUR"])


class A4TwoCorridorsForTheBigGroups(unittest.TestCase):
    def test_cap_order_gives_the_second_corridor_of_the_groups_named(self):
        def c(x):
            return {"new": x}
        per = {"big": [c(9), c(8), c(1)], "small": [c(5), c(4)], "other": [c(3), c(2.5), c(2)]}
        # without `second`, the tonnes decide after the first corridors: the 8 Mt corridor of "big", then the 4 Mt one of "small"
        self.assertEqual(GR.cap_order(per, 5, first=set(per)), [(0, "big"), (0, "other"), (0, "small"), (1, "big"), (1, "small")])
        # with `second`, "other" keeps its second corridor (2.5 Mt) before the tonnes decide
        self.assertEqual(GR.cap_order(per, 5, first=set(per), second={"other"}),
                         [(0, "big"), (0, "other"), (0, "small"), (1, "other"), (1, "big")])
        # a group with one corridor has no second one to keep
        self.assertEqual(GR.cap_order({"a": [c(9)], "b": [c(2), c(1)]}, 3, first={"a", "b"}, second={"a", "b"}), [(0, "a"), (0, "b"), (1, "b")])

    def test_the_threshold_is_ten_mt(self):
        self.assertEqual(GR.TWO_ROUTES_ABOVE_MT, 10)

    def test_every_big_group_of_the_first_package_has_two_routes(self):
        first = next(gs for gs, cap in GR.LATER_GROUPS if "ammonia" in gs)
        with open(os.path.join(DATA, "freight", "routes.json"), encoding="utf-8") as f:
            routes = json.load(f)
        count = {}
        every = set().union(*[gs for gs, _ in GR.LATER_GROUPS])
        for r in routes:
            if r.get("generated"):
                g = r["id"].split("-", 1)[1]
                # the longest group name that starts the id: "ammonium-nitrate-limestone" (package FNCB) is not "ammonium-nitrate"
                grp = max((x for x in every if g.startswith(x + "-")), key=len, default=None)
                if grp in first:
                    count[grp] = count.get(grp, 0) + 1
        sea = {}
        for g in first:
            _, p = pairs(g)
            sea[g] = p["seaborne"] / 1000
        for g in first:
            if sea[g] > GR.TWO_ROUTES_ABOVE_MT:
                self.assertGreaterEqual(count.get(g, 0), 2, g)
        self.assertEqual(sum(count.values()), 20)


class A5TheOilsCarryTheBasisOfAGeneralPort(unittest.TestCase):
    def test_no_port_of_the_two_oils_is_said_to_name_the_oil(self):
        self.assertIn("sunflower-oil", P.GENERAL_BASIS)
        self.assertIn("rapeseed-oil", P.GENERAL_BASIS)
        self.assertNotIn("sunflower-oil", P.BOX_GENERAL)  # they are not under the wrong-coast check of the lane builder
        for g in ("sunflower-oil", "rapeseed-oil"):
            for iso in ("MYS", "IDN", "UKR", "RUS", "ARG", "IND", "CHN", "FRA", "NLD"):
                for role in ("load", "discharge"):
                    for c in P.candidates(iso, g, role):
                        self.assertNotEqual(c[2], P.BASIS_PAGE, (g, iso, role, c))

    def test_the_ports_are_those_of_the_family(self):
        """No port changes: the sunflower oil of Malaysia still loads at Pasir Gudang, as palm oil does."""
        self.assertEqual(P.candidates("MYS", "sunflower-oil", "load")[0][:2], P.candidates("MYS", "palm-oil", "load")[0][:2])
        self.assertEqual(P.candidates("MYS", "sunflower-oil", "load")[0][2], P.BASIS_GENERAL)
        self.assertEqual(P.candidates("MYS", "palm-oil", "load")[0][2], P.BASIS_PAGE)
        self.assertEqual(P.candidates("IND", "rapeseed-oil", "discharge")[0][:2], P.candidates("IND", "soyoil", "discharge")[0][:2])

    def test_the_lane_files_say_the_same(self):
        for g in ("sunflower-oil", "rapeseed-oil"):
            with open(os.path.join(DATA, "freight", "lanes", g + ".json"), encoding="utf-8") as f:
                lanes = json.load(f)
            for code, p in lanes["ports"].items():
                self.assertNotEqual(p["basis"], P.BASIS_PAGE, (g, code))
        with open(os.path.join(DATA, "freight", "lanes", "palm-oil.json"), encoding="utf-8") as f:
            palm = json.load(f)
        self.assertIn(P.BASIS_PAGE, {p["basis"] for p in palm["ports"].values()})  # palm oil is untouched


class A6TheFerroAlloysKeepTheirHyphen(unittest.TestCase):
    def test_the_labels(self):
        for g in ("ferro-chromium", "ferro-manganese", "silico-manganese", "ferro-silicon"):
            self.assertEqual(K.label(g), g)
            self.assertEqual(K.cap_label(g), g[0].upper() + g[1:])

    def test_the_names_of_the_routes_and_the_notes(self):
        with open(os.path.join(DATA, "freight", "routes.json"), encoding="utf-8") as f:
            routes = json.load(f)
        for r in routes:
            if r["id"].startswith(("gen-ferro-", "gen-silico-")):
                self.assertTrue(r["name"].startswith(("Ferro-chromium", "Ferro-manganese", "Ferro-silicon", "Silico-manganese")), r["name"])
        for g in ("ferro-chromium", "ferro-manganese", "silico-manganese", "ferro-silicon"):
            with open(os.path.join(DATA, "freight", "lanes", g + ".json"), encoding="utf-8") as f:
                text = f.read()
            for bad in ("Ferro chromium", "Ferro manganese", "Ferro silicon", "Silico manganese", "ferro chromium", "ferro manganese", "ferro silicon", "silico manganese"):
                self.assertNotIn(bad, text, (g, bad))


if __name__ == "__main__":
    unittest.main()
