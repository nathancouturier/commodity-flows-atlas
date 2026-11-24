"""Tests G03, G04, G07, G08, G09, G10, G11 of the trade-engine plan (package E4b-gateways-coasts), unit form.

The unit form tests `ports.assign()` and `ports.gateway()` on the merged gateway tables. The lane-file form of
these tests (distances and `via` of the built lanes) belongs to package E5 and is not tested here.
Distances are read with `searoute` directly (no gates, no passage restrictions but `northwest`).

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
"""
import importlib
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FREIGHT = os.path.join(ROOT, "pipeline", "freight")
sys.path.insert(0, FREIGHT)

import searoute as sr  # noqa: E402

import ports  # noqa: E402
import river_legs  # noqa: E402
import vessel_rules  # noqa: E402


def nm(a, b):
    """Great-network distance in nautical miles between two port codes."""
    r = sr.searoute(ports.port(a)["at"], ports.port(b)["at"], units="naut", restrictions=["northwest"])
    return r["properties"]["length"]


def main_nm(o, d, group):
    m = ports.assign(o, d, group).main
    return nm(m.load, m.discharge)


class Loader(unittest.TestCase):
    def test_legacy_table_is_kept(self):
        self.assertIs(ports.P, ports.LEGACY_P)
        self.assertEqual(ports.LEGACY_P["SAU"]["any"], "SARTA")

    def test_missing_module_is_tolerated(self):
        loaded = ports.load_modules(("food", "coasts", "energy", "no_such_module"))
        self.assertIn("coasts", loaded)
        self.assertNotIn("no_such_module", loaded)
        ports.load_modules()

    def test_gateway_signature_and_none(self):
        self.assertTrue(ports.gateway("USA", "coal"))
        self.assertIsNone(ports.gateway("ZZZ", "coal"))
        self.assertEqual(ports.gateway("RUS", "crude-oil"), ports.gateway("RUS", "crude-oil", None))

    def test_pasir_gudang_fix(self):
        """MYPGU is the UN/LOCODE of Pasir Gudang, not of Pengerang (audit C-010)."""
        p = ports.port("MYPGU")
        self.assertIn("Pasir Gudang", p["name"])
        self.assertAlmostEqual(p["at"][0], 103.88, delta=0.1)
        self.assertAlmostEqual(p["at"][1], 1.45, delta=0.1)
        q = ports.port("MYPRG")
        self.assertEqual(q["name"], "Pengerang")
        self.assertAlmostEqual(q["at"][0], 104.13, delta=0.01)

    def test_vancouver_is_not_named_after_a_container_terminal(self):
        self.assertNotIn("Centerm", ports.port("CAVAN")["name"])
        self.assertIn("Vancouver", ports.port("CAVAN")["name"])


class Sources(unittest.TestCase):
    """G10: every gateway row has a source id that exists, a url for Wikipedia, a known zone."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "data", "sources.json"), encoding="utf-8") as f:
            cls.sources = {s["id"] for s in json.load(f)}
        # an id added to pipeline/freight/sources_freight.json reaches data/sources.json at the next rebuild
        for name in os.listdir(FREIGHT):
            if name.startswith("sources_") and name.endswith(".json"):
                with open(os.path.join(FREIGHT, name), encoding="utf-8") as f:
                    cls.sources |= {s["id"] for s in json.load(f)}
        cls.rows = [(iso, r) for iso, rows in ports.G.items() for r in rows]

    def test_tables_are_not_empty(self):
        self.assertGreater(len(self.rows), 40)

    def test_every_row_has_a_source(self):
        for iso, r in self.rows:
            with self.subTest(iso=iso, code=r.code):
                self.assertIn(r.src, self.sources)
                if r.src.startswith("wikipedia"):
                    # the English page, or the French one where the English Wikipedia has none (FNCA: the French ports)
                    self.assertTrue(r.url and r.url.startswith(("https://en.wikipedia.org/wiki/", "https://fr.wikipedia.org/wiki/")), r)

    def test_every_row_has_a_known_zone_role_and_port(self):
        for iso, r in self.rows:
            with self.subTest(iso=iso, code=r.code):
                self.assertIn(r.zone, ports.ZONES)
                self.assertIn(r.role, ports.ROLES)
                self.assertTrue(r.families)
                ports.port(r.code)  # resolves in searoute or MANUAL

    def test_zones(self):
        self.assertGreaterEqual(len(ports.ZONES), 20)
        z = ports.zones()
        used = {r.zone for _, r in self.rows}
        self.assertTrue(used <= set(ports.ZONES))
        self.assertEqual({x["id"] for x in z}, used)  # review GE3, finding 13: no zone without a port
        self.assertGreaterEqual(len(z), 20)
        for x in z:
            self.assertTrue(x["ports"], x["id"])
            for code in x["ports"]:
                ports.port(code)

    def test_manual_extra_has_a_source_in_a_row_or_is_listed(self):
        for code in ports.MANUAL_SRC:
            self.assertIn(ports.MANUAL_SRC[code]["s"], self.sources)

    def test_every_manual_port_added_by_the_tables_is_used_by_a_row(self):
        used = {r.code for _, r in self.rows} | set(ports.MANUAL_SRC)
        mod = importlib.import_module("gateways.coasts")
        for code in getattr(mod, "MANUAL_EXTRA", {}):
            self.assertIn(code, used)


def _flows_2024():
    """{(group, iso3, role): tonnes} of the 2024 customs flows of the lane groups."""
    import pandas as pd
    df = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
    d = df[(df["year"] == 2024) & df["group"].isin(list(ports.SEGMENT))]
    out = {}
    for (g, c), t in d.groupby(["group", "o"])["t"].sum().items():
        out[(g, c, "load")] = t
    for (g, c), t in d.groupby(["group", "d"])["t"].sum().items():
        out[(g, c, "discharge")] = t
    return out


# Inland places of the searoute list that the first-stage fallback published as gateways (review GE3, finding 1)
INLAND = {"USSHN", "INBSL", "UAIEV", "DEGIE", "CNMYG", "SARYP", "GBBRA", "ESMAD", "ITMOD", "BRCMG"}
FOOD_GROUPS = ["wheat", "corn", "soybeans", "soymeal", "rice", "sugar", "rapeseed", "palm-oil", "soyoil", "potash",
               "urea", "dap", "phosphate-rock"]


class G11(unittest.TestCase):
    def test_no_port_of_another_family(self):
        """Each gateway carries its basis, and the basis holds: a row of the family (either role), the country's
        general-cargo row (food, fertiliser, metals, general cargo only), the legacy port (never a terminal of
        another cargo), or the nearest real seaport."""
        for iso, rows in ports.G.items():
            for group, seg in ports.SEGMENT.items():
                for role in ("load", "discharge", None):
                    cands = ports.candidates(iso, group, role)
                    with self.subTest(iso=iso, group=group, role=role):
                        if not cands:
                            continue
                        code, _, basis = cands[0]
                        self.assertEqual(code, ports.gateway(iso, group, role))
                        self.assertEqual(ports.basis_of(iso, group, role, code), basis)
                        fams = ports._fams(group)
                        if basis == ports.BASIS_PAGE:
                            self.assertIn(code, {r.code for r in rows if r.families & set(fams)
                                                 and (role is None or r.role in (role, "both"))})
                        elif basis == ports.BASIS_PLANT:
                            # a row of the family that is marked as naming the plant (package FNCE), in either role: the page gives no direction
                            self.assertIn(code, {r.code for r in rows if r.families & set(fams) and r.basis == ports.BASIS_PLANT})
                        elif basis == ports.BASIS_OTHER:
                            self.assertIn(code, {r.code for r in rows if r.families & set(fams)})
                            self.assertNotIn(seg, ports.ENERGY_SEGMENTS)
                        elif basis == ports.BASIS_GENERAL:
                            self.assertIn(seg, ports.GENERAL_SEGMENTS)
                            # a minor metal of the "box" segment: its box rows are general ports (review GL1.6); no row names the metal.
                            # The two oils of GENERAL_BASIS keep the vegetable-oil rows of palm and soybean oil as their ports, with this basis
                            oil_rows = {r.code for r in rows if r.families & set(fams)} if group in ports.GENERAL_BASIS - ports.BOX_GENERAL else set()
                            self.assertIn(code, {r.code for r in rows if "box" in r.families} | oil_rows)
                            named = (group,) if group in ports.GENERAL_BASIS else fams
                            self.assertFalse([r for r in rows if r.families & set(named)])
                        elif basis == ports.BASIS_LEGACY:
                            self.assertEqual(code, ports._legacy_port(iso, group))
                        else:
                            self.assertEqual(basis, ports.BASIS_NEAREST)
                            self.assertTrue(ports.is_seaport(code))
                        self.assertTrue(ports._serves(code, group), code)

    def test_first_candidate_is_a_seaport_for_every_2024_flow(self):
        """Review GE3, finding 1: no flow of 2024 gets an inland town of the searoute list as its gateway."""
        bad = []
        for (g, c, role), t in _flows_2024().items():
            cands = ports.candidates(c, g, role)
            if not cands:
                continue
            code, _, basis = cands[0]
            if code in INLAND:
                bad.append((g, c, role, code))
            elif basis == ports.BASIS_NEAREST and not ports.is_seaport(code):
                bad.append((g, c, role, code))
            elif code not in ports.MANUAL and ports.sea_km(code) > 50 and code not in river_legs.RIVER_LEGS:
                # a port far up a river must have a river leg (river_legs.py), or the router snaps it to a node on another stretch of coast
                # (Rouen, 53 km up the Seine, went to Dieppe: FNCE); Ho Chi Minh City, 44 km up the Saigon, is under the limit
                bad.append((g, c, role, code, round(ports.sea_km(code))))
        self.assertEqual(bad, [])

    def test_no_food_group_lands_on_an_energy_or_ore_terminal(self):
        """Test G01 of the plan, unit form, over every country and role with a 2024 flow."""
        g01 = {"SARTA", "IQBOT", "NGBON", "DZAZW", "TRCEY", "AUPHE", "IDBPN", "USCRP"}
        bad = []
        for (g, c, role), t in _flows_2024().items():
            if g in FOOD_GROUPS:
                hit = {code for code, _, _ in ports.candidates(c, g, role)} & g01
                if hit:
                    bad.append((g, c, role, hit))
        self.assertEqual(bad, [])

    def test_inland_towns_are_not_seaports(self):
        for code in INLAND:
            self.assertFalse(ports.is_seaport(code), code)
        for code in ("USMSY", "USHOU", "DEHAM", "NLRTM", "USKAM", "CAMTR", "INMUN", "MASFI", "PKBQM"):
            self.assertTrue(ports.is_seaport(code), code)

    def test_cases_of_the_review(self):
        """The examples of finding 1: each lands on a port of the family or of the country's general cargo."""
        self.assertEqual(ports.gateway("IND", "rice", "load"), "INMUN")      # was Bhusawal
        self.assertEqual(ports.gateway("IND", "steel", "load"), "INMUN")
        self.assertEqual(ports.gateway("UKR", "steel", "load"), "UAODS")     # was Kiev
        self.assertNotIn(ports.gateway("DEU", "potash", "load"), INLAND)     # was Giessen
        self.assertNotIn(ports.gateway("CHN", "dap", "load"), INLAND)        # was Mianyang
        self.assertNotIn(ports.gateway("USA", "bauxite", "discharge"), INLAND)  # was Shelton, Nebraska
        self.assertNotIn(ports.gateway("SAU", "rice", "discharge"), INLAND)  # was Riyadh
        self.assertEqual(ports.gateway("KOR", "corn", "discharge"), "KRPUS")
        self.assertEqual(ports.basis_of("KOR", "corn", "discharge", "KRPUS"), ports.BASIS_GENERAL)
        self.assertEqual(ports.basis_of("USA", "iron-ore", "load", ports.gateway("USA", "iron-ore", "load")), ports.BASIS_LEGACY)

    def test_saudi_wheat_is_not_ras_tanura(self):
        self.assertNotEqual(ports.gateway("SAU", "wheat"), "SARTA")
        self.assertNotEqual(ports.gateway("SAU", "wheat", "discharge"), "SARTA")


class G03(unittest.TestCase):
    """C-007: US wheat for Asia has a Pacific Northwest option; the principal gateway stays on the Gulf."""

    def test_wheat_usa_jpn(self):
        a = ports.assign("USA", "JPN", "wheat")
        self.assertEqual(a.basis, "open")
        self.assertEqual(ports.zone_of(a.main.load), "us-gulf")
        zones = {ports.zone_of(o.load) for o in a.options}
        self.assertIn("us-pnw", zones)
        self.assertTrue(all(o.w is None for o in a.options))
        dists = {o.load: nm(o.load, o.discharge) for o in a.options}
        self.assertGreater(dists[a.main.load], 7000)
        self.assertLessEqual(min(dists.values()), 4500)

    def test_principal_is_not_the_shortest(self):
        a = ports.assign("USA", "CHN", "soybeans")
        self.assertEqual(ports.zone_of(a.main.load), "us-gulf")

    def test_every_us_grain_option_loads_on_a_grain_gateway(self):
        for o in ports.assign("USA", "PHL", "corn").options:
            self.assertIn(o.load, {r.code for r in ports.G["USA"] if "grain" in r.families})


class G04(unittest.TestCase):
    """C-010: potash from Canada to Belgium is not routed from Vancouver through Panama."""

    def test_potash_can_bel(self):
        a = ports.assign("CAN", "BEL", "potash")
        self.assertNotEqual(a.main.load, "CAVAN")
        self.assertEqual(ports.zone_of(a.main.load), "canada-east")
        self.assertEqual(a.basis, "rule")
        self.assertLessEqual(main_nm("CAN", "BEL", "potash"), 3500)

    def test_canada_to_asia_loads_on_the_pacific(self):
        self.assertEqual(ports.zone_of(ports.assign("CAN", "CHN", "potash").main.load), "canada-west")
        self.assertEqual(ports.zone_of(ports.assign("CAN", "JPN", "coal").main.load), "canada-west")
        self.assertEqual(ports.zone_of(ports.assign("CAN", "NLD", "wheat").main.load), "canada-east")

    def test_canada_to_the_pacific_coast_of_south_america(self):
        self.assertEqual(ports.zone_of(ports.assign("CAN", "CHL", "wheat").main.load), "canada-west")


class G07(unittest.TestCase):
    """C-020 (reproduced): Brazil does not load everything at one port, and its alumina is not shipped from Tubarao."""

    def test_brazil_uses_several_load_ports(self):
        loads = {ports.assign("BRA", "CHN", g).main.load for g in ("iron-ore", "soybeans", "alumina", "bauxite", "sugar", "corn", "crude-oil")}
        self.assertGreaterEqual(len(loads), 3, loads)

    def test_brazilian_alumina_and_bauxite_load_in_the_north(self):
        for g in ("alumina", "bauxite"):
            m = ports.assign("BRA", "CAN", g).main
            self.assertNotEqual(m.load, "BRTUB", g)
            self.assertLess(ports.port(m.load)["at"][1], -0.5 + 1)  # north coast: Amazon mouth or Maranhao
        self.assertLess(main_nm("BRA", "CAN", "alumina"), 4000)


def _mexican_ore_rows(group):
    return [r for r in ports.G.get("MEX", ()) if group in r.families and r.role in ("load", "both")]


class G08(unittest.TestCase):
    """C-020: Mexican concentrates for Asia load on the Pacific, for each group with a sourced Pacific row. The
    Manzanillo page names copper among the principal exports; no page read names a port for zinc concentrate
    (gateways/coasts.UNSOURCED["MEX"]), so the zinc part of G08 is not met."""

    def test_copper_concentrate(self):
        self.assertTrue(_mexican_ore_rows("copper-ore"))
        for d in ("CHN", "JPN", "KOR"):
            a = ports.assign("MEX", d, "copper-ore")
            with self.subTest(d=d):
                self.assertEqual(ports.zone_of(a.main.load), "mexico-pacific")
                self.assertLess(nm(a.main.load, a.main.discharge), 8000)

    def test_copper_concentrate_for_europe_stays_on_the_gulf(self):
        a = ports.assign("MEX", "DEU", "copper-ore")
        self.assertEqual(ports.ocean_of(a.main.load), "atlantic")
        self.assertEqual(ports.basis_of("MEX", "copper-ore", "load", a.main.load), ports.BASIS_LEGACY)

    @unittest.skipUnless(_mexican_ore_rows("zinc-ore"), "no sourced gateway for Mexican zinc concentrate (not met)")
    def test_zinc_concentrate(self):
        for d in ("KOR", "JPN"):
            a = ports.assign("MEX", d, "zinc-ore")
            with self.subTest(d=d):
                self.assertEqual(ports.zone_of(a.main.load), "mexico-pacific")

    def test_manzanillo_qingdao_distance(self):
        self.assertAlmostEqual(nm("MXZLO", "CNTAO"), 6982, delta=300)


class G09(unittest.TestCase):
    """Two-ocean countries: the gateway is on the ocean of the other end (families with rows on both coasts)."""

    def test_guatemala(self):
        self.assertEqual(ports.zone_of(ports.assign("USA", "GTM", "steel").main.discharge), "cam-caribbean")
        self.assertEqual(ports.zone_of(ports.assign("CHN", "GTM", "steel").main.discharge), "cam-pacific")
        self.assertEqual(ports.zone_of(ports.assign("ARG", "GTM", "coffee").main.discharge), "cam-caribbean")

    def test_houston_to_the_isthmus_does_not_cross_panama(self):
        for d in ("GTM", "PAN", "HND"):
            m = ports.assign("USA", d, "steel").main
            self.assertEqual(ports.ocean_of(m.discharge), "atlantic", d)
            self.assertLess(nm(m.load, m.discharge), 2500, d)

    def test_pacific_side_for_asia(self):
        for iso in ("GTM", "PAN", "MEX"):
            m = ports.assign("JPN", iso, "steel").main
            self.assertEqual(ports.ocean_of(m.discharge), "pacific", iso)
        self.assertEqual(ports.ocean_of(ports.assign("JPN", "NIC", "wheat").main.discharge), "pacific")  # Corinto, the only port

    def test_two_two_ocean_countries_trade_on_the_atlantic_side(self):
        m = ports.assign("MEX", "PAN", "steel").main
        self.assertEqual(ports.ocean_of(m.load), "atlantic")
        self.assertEqual(ports.ocean_of(m.discharge), "atlantic")
        self.assertLess(nm(m.load, m.discharge), 1500)

    def test_the_other_end_without_a_zone_is_read_from_its_coordinates(self):
        self.assertEqual(ports.zone_of(ports.assign("PER", "GTM", "steel").main.discharge), "cam-pacific")

    def test_ocean_of(self):
        self.assertEqual(ports.ocean_of("USHOU"), "atlantic")
        self.assertEqual(ports.ocean_of("USKAM"), "pacific")
        self.assertEqual(ports.ocean_of("JPCHB"), "pacific")
        self.assertEqual(ports.ocean_of("CLANF"), "pacific")
        self.assertEqual(ports.ocean_of("NLRTM"), "atlantic")
        self.assertEqual(ports.ocean_of("EGPSD"), "atlantic")  # Mediterranean
        self.assertEqual(ports.ocean_of("INMUN"), "pacific")   # Indian Ocean: Indo-Pacific side


class CoastRules(unittest.TestCase):
    """Russia and China rules moved from build_lanes.py, Saudi dry cargo."""

    def test_russia_by_destination(self):
        self.assertEqual(ports.assign("RUS", "CHN", "coal").main.load, "RUVYP")
        self.assertEqual(ports.assign("RUS", "IND", "coal").main.load, "RUVYP")
        self.assertEqual(ports.assign("RUS", "DEU", "coal").main.load, "RUULU")
        self.assertEqual(ports.assign("RUS", "TUR", "coal").main.load, "RUTAM")
        self.assertEqual(ports.assign("RUS", "KOR", "crude-oil").main.load, "RUKOZ")
        self.assertEqual(ports.assign("RUS", "TUR", "crude-oil").main.load, "RUNVS")
        self.assertEqual(ports.assign("RUS", "NLD", "crude-oil").main.load, "RUPRI")
        # Review GE3, finding 10: the Vostochny page names coal only, so wheat for Asia leaves from the grain row
        for d in ("CHN", "IDN", "KOR", "EGY", "NLD"):
            self.assertEqual(ports.assign("RUS", d, "wheat").main.load, "RUNVS", d)

    def test_russian_crude_to_india_is_open(self):
        a = ports.assign("RUS", "IND", "crude-oil")
        self.assertEqual(a.basis, "open")
        self.assertEqual(a.main.load, "RUPRI")
        self.assertIn("RUNVS", {o.load for o in a.options})

    def test_south_east_asian_coal_into_south_china(self):
        for o in ("IDN", "PHL", "VNM", "MYS"):
            self.assertEqual(ports.assign(o, "CHN", "coal").main.discharge, "CNHUA", o)  # Guangzhou since FE4b (was Zhanjiang)
        self.assertNotEqual(ports.assign("AUS", "CHN", "coal").main.discharge, "CNHUA")

    def test_saudi_dry_cargo(self):
        self.assertEqual(ports.zone_of(ports.assign("EGY", "SAU", "wheat").main.discharge), "red-sea")
        self.assertEqual(ports.zone_of(ports.assign("FRA", "SAU", "wheat").main.discharge), "red-sea")
        self.assertEqual(ports.zone_of(ports.assign("IND", "SAU", "wheat").main.discharge), "meg")
        self.assertEqual(ports.zone_of(ports.assign("AUS", "SAU", "wheat").main.discharge), "meg")

    def test_mexico_by_ocean(self):
        self.assertEqual(ports.zone_of(ports.assign("CHN", "MEX", "steel").main.discharge), "mexico-pacific")
        self.assertEqual(ports.zone_of(ports.assign("USA", "MEX", "steel").main.discharge), "mexico-gulf")

    def test_unrouted_when_an_end_has_no_gateway(self):
        a = ports.assign("KAZ", "CHN", "wheat")
        self.assertEqual(a.basis, "unrouted")
        self.assertIsNone(a.main.load)

    def test_assign_never_raises(self):
        for o in ("USA", "CAN", "BRA", "AUS", "IND", "SAU", "MEX", "COL", "RUS", "CHN", "IDN", "ZAF", "FRA", "GTM", "PAN", "XXX"):
            for d in ("JPN", "NLD", "CHN", "USA", "PAN", "SAU"):
                for g in ports.SEGMENT:
                    a = ports.assign(o, d, g)
                    self.assertIn(a.basis, ("single", "rule", "open", "unrouted"))
                    self.assertEqual(a.main, a.options[0])


class OreClass(unittest.TestCase):
    """C-020: Peru and Chile are in the Capesize ore rule only with a cited page for their loading terminals."""

    def test_big_ore_listing(self):
        for iso in ("PER", "CHL"):
            if iso in vessel_rules.BIG_ORE:
                self.assertEqual(vessel_rules.classes("iron-ore", iso, "CHN", 12e6, 10000)[0], "capesize")
        self.assertIn("BRA", vessel_rules.BIG_ORE)


class ReviewGE3(unittest.TestCase):
    """Regression tests of the independent review of the first stage (group GE3)."""

    def test_2_us_grain_to_mexico_does_not_cross_panama(self):
        for g in ("corn", "wheat", "soybeans", "soymeal", "rice", "urea", "dap"):
            a = ports.assign("USA", "MEX", g)
            with self.subTest(g=g):
                self.assertEqual(ports.zone_of(a.main.discharge), "mexico-gulf")
                self.assertLess(main_nm("USA", "MEX", g), 2000)
        m = ports.assign("MEX", "CHN", "steel").main
        self.assertEqual(ports.zone_of(m.load), "mexico-pacific")  # Manzanillo general cargo serves both roles

    def test_3_chinese_soybeans_are_not_on_a_bulk_reading(self):
        self.assertFalse([r for r in ports.G["CHN"] if r.code == "CNTSN" and r.families & {"grain", "fert", "vegoil"}])
        # FE4b: the Guangzhou and Lianyungang pages name grain, so soybeans no longer rest on the Tianjin general row;
        # review GE4 (finding 2): the northern port is first, Guangzhou the option, since no page ranks them
        code = ports.gateway("CHN", "soybeans", "discharge")
        self.assertEqual(code, "CNLYG")
        self.assertEqual(ports.basis_of("CHN", "soybeans", "discharge", code), ports.BASIS_PAGE)
        self.assertEqual(ports.basis_of("CHN", "potash", "discharge", "CNTSN"), ports.BASIS_GENERAL)

    def test_4_no_family_rests_on_bulk_alone(self):
        """Rows that the review found naming a cargo their page does not name."""
        dropped = [("IDN", "IDTPP", "grain"), ("MYS", "MYPKG", "grain"), ("IND", "INKDL", "grain"), ("PAK", "PKKHI", "fert"),
                   ("SAU", "SAJED", "grain"), ("ITA", "ITRAN", "grain"), ("NGA", "NGAPP", "grain"), ("CAN", "CAVAN", "fert"),
                   ("NIC", "NICIO", "grain"), ("ESP", "ESVLC", "fert"), ("ESP", "ESTAR", "grain"), ("IND", "INPRT", "coal"),
                   ("BRA", "BRVLC", "bauxite"), ("BRA", "BRITQ", "bauxite"), ("BRA", "BRITQ", "alumina"), ("ZAF", "ZARCB", "alumina")]
        for iso, code, fam in dropped:
            self.assertFalse([r for r in ports.G.get(iso, ()) if r.code == code and fam in r.families], (iso, code, fam))

    def test_5_australian_sugar_loads_in_queensland(self):
        self.assertEqual(ports.gateway("AUS", "sugar", "load"), "AUTSV")
        self.assertEqual(ports.gateway("AUS", "wheat", "load"), "AUKWI")
        for iso in ports.G:  # a grain row is no sugar gateway
            for code, _, basis in ports.candidates(iso, "sugar", "load"):
                if basis == ports.BASIS_PAGE:
                    self.assertTrue([r for r in ports.G[iso] if r.code == code and "sugar" in r.families], (iso, code))

    def test_6_us_fertiliser_row_is_urea_only(self):
        self.assertEqual(ports.gateway("USA", "urea", "discharge"), "USMSY")
        for g in ("potash", "phosphate-rock", "dap"):
            self.assertNotIn("USMSY", {c for c, _, _ in ports.candidates("USA", g, "discharge")}, g)

    def test_7_algeria_and_iraq_food_is_never_on_an_oil_terminal(self):
        for iso in ("DZA", "IRQ"):
            for g in FOOD_GROUPS:
                code = ports.gateway(iso, g, "discharge")
                self.assertNotIn(code, {"DZAZW", "IQBOT"}, (iso, g))
                self.assertTrue(ports.is_seaport(code), (iso, g, code))
        self.assertEqual(ports.gateway("IRQ", "crude-oil", "load"), "IQBOT")  # the oil terminal keeps its own cargo

    def test_8_options_of_a_two_ocean_end_pair_with_the_right_ocean(self):
        a = ports.assign("CAN", "SAU", "potash")
        pairs = {(o.load, o.discharge) for o in a.options}
        self.assertIn(("CAMTR", "SAJED"), pairs)
        for o in a.options:  # rule sau-dry-cargo: Red Sea for the Atlantic side, the Gulf for the rest
            self.assertEqual(ports.zone_of(o.discharge), "red-sea" if ports.ocean_of(o.load) == "atlantic" else "meg", o)
        self.assertNotIn("panama", _via(a.main.load, a.main.discharge))
        a = ports.assign("USA", "SAU", "wheat")
        self.assertEqual((a.main.load, a.main.discharge), ("USMSY", "SAJED"))
        self.assertIn(("USKAM", "SADMM"), {(o.load, o.discharge) for o in a.options})

    def test_9_kalama_is_not_an_option_for_atlantic_destinations(self):
        for d in ("DEU", "BRA", "EGY", "GBR", "NLD", "ZAF", "KEN", "ARE"):
            loads = {o.load for o in ports.assign("USA", d, "wheat").options}
            self.assertNotIn("USKAM", loads, d)
        for d in ("JPN", "CHN", "KOR", "PHL"):
            self.assertIn("USKAM", {o.load for o in ports.assign("USA", d, "wheat").options}, d)

    def test_10_rule_ports_without_a_row_are_legacy_choices(self):
        self.assertEqual(ports.basis_of("RUS", "crude-oil", "load", "RUKOZ"), ports.BASIS_LEGACY)
        self.assertEqual(ports.basis_of("RUS", "coal", "load", "RUVYP"), ports.BASIS_PAGE)

    def test_11_colon_terminal_is_at_its_page_coordinates(self):
        x, y = ports.port("PAMIT")["at"]
        self.assertLess(ports._km(x, y, -79.882, 9.362), 5)

    def test_12_transit_rows_need_a_page_naming_the_country(self):
        for iso in ("UZB", "TKM", "SVK"):
            self.assertNotIn(iso, ports.TRANSIT)

    def test_basis_values(self):
        for iso in ("USA", "IND", "KOR", "DZA", "GTM", "XXX"):
            for g in ports.SEGMENT:
                for role in ("load", "discharge"):
                    for code, _, basis in ports.candidates(iso, g, role):
                        self.assertIn(basis, ports.BASES)


class FE4b(unittest.TestCase):
    """Sourcing pass FE4b (23 November 2026): ports that a page names for the cargo, in dry bulk, metals, food and
    general cargo. Each line is (country, group, role, principal port): the principal gateway is the port of the
    row, its basis is "page names the cargo", and the port is a real seaport."""

    SOURCED = [
        ("CHN", "iron-ore", "discharge", "CNTAO"), ("CHN", "bauxite", "discharge", "CNRZH"),
        ("CHN", "coal", "discharge", "CNCFD"), ("CHN", "soybeans", "discharge", "CNLYG"),
        ("IDN", "coal", "load", "IDTBA"), ("GIN", "bauxite", "load", "GNKMS"), ("CAN", "iron-ore", "load", "CASEI"),
        ("ZAF", "iron-ore", "load", "ZASDB"), ("ZAF", "manganese", "load", "ZAZBA"), ("IND", "iron-ore", "load", "INDHA"),
        ("IND", "manganese", "discharge", "INVTZ"), ("PER", "iron-ore", "load", "PESNX"), ("SWE", "iron-ore", "load", "SELLA"),
        ("NLD", "iron-ore", "discharge", "NLRTM"), ("NLD", "coal", "discharge", "NLRTM"), ("DEU", "coal", "discharge", "DEWVN"),
        ("MOZ", "coal", "load", "MZBEW"), ("PAK", "coal", "discharge", "PKBQM"), ("SLE", "iron-ore", "load", "SLPEP"),
        ("MRT", "iron-ore", "load", "MRNDB"), ("EGY", "coal", "discharge", "EGALY"),
        ("JPN", "steel", "load", "JPYOK"), ("TWN", "steel", "load", "TWKHH"), ("VNM", "steel", "discharge", "VNCMT"),
        ("THA", "steel", "discharge", "THLCH"), ("PHL", "wheat", "discharge", "PHSFS"), ("PHL", "steel", "discharge", "PHMNL"),
        ("ARE", "steel", "discharge", "AEJEA"), ("OMN", "wheat", "discharge", "OMSOH"), ("JOR", "phosphate-rock", "load", "JOAQB"),
        ("SWE", "steel", "load", "SEGOT"), ("FRA", "steel", "load", "FRFOS"), ("SGP", "steel", "discharge", "SGSIN"),
        ("HKG", "steel", "discharge", "HKHKG"), ("NLD", "steel", "discharge", "NLRTM"),
    ]

    def test_principal_gateway_is_the_sourced_port(self):
        for iso, group, role, code in self.SOURCED:
            with self.subTest(iso=iso, group=group, role=role):
                self.assertEqual(ports.gateway(iso, group, role), code)
                self.assertEqual(ports.basis_of(iso, group, role, code), ports.BASIS_PAGE)
                self.assertTrue(ports.is_seaport(code), code)
                self.assertTrue(ports.port(code)["name"])
                rows = [r for r in ports.G[iso] if r.code == code and r.families & set(ports._fams(group))]
                self.assertTrue(rows)
                self.assertTrue(rows[0].url.startswith("https://en.wikipedia.org/wiki/"))
                self.assertTrue(rows[0].note)

    def test_new_ports_sit_at_the_coordinates_of_their_page(self):
        # code -> (lon, lat) printed on the page of the row
        page = {"IDTBA": (117.7037, 0.5860), "INDHA": (86.9628, 20.8233), "CNHUA": (113.434, 23.094)}
        for code, (lon, lat) in page.items():
            x, y = ports.port(code)["at"]
            with self.subTest(code=code):
                self.assertLess(abs(x - lon) + abs(y - lat), 0.02)
        mod = importlib.import_module("gateways.coasts")
        for code in mod.MANUAL_EXTRA:
            with self.subTest(extra=code):
                self.assertTrue(ports.is_seaport(code))
                self.assertLess(ports.sea_km(code), 10)

    def test_replaced_ports(self):
        # Samarinda, Zhanjiang, Paradip, Port Elizabeth and Callao stay in the legacy table but no longer answer
        # for the cargo that a page now places elsewhere
        self.assertNotEqual(ports.gateway("IDN", "coal", "load"), "IDSRI")
        self.assertNotEqual(ports.assign("IDN", "CHN", "coal").main.discharge, "CNZHA")
        self.assertNotEqual(ports.gateway("IND", "iron-ore", "load"), "INPRT")
        self.assertNotEqual(ports.gateway("ZAF", "manganese", "load"), "ZAPLZ")
        self.assertNotEqual(ports.gateway("PER", "iron-ore", "load"), "PECLL")
        # a cargo that no page places keeps the legacy port, and says so
        self.assertEqual(ports.gateway("PER", "copper-ore", "load"), "PECLL")
        self.assertEqual(ports.basis_of("PER", "copper-ore", "load", "PECLL"), ports.BASIS_LEGACY)
        self.assertEqual(ports.basis_of("CHN", "nickel-ore", "discharge", "CNTAO"), ports.BASIS_LEGACY)
        self.assertEqual(ports.basis_of("JPN", "coal", "discharge", "JPKSM"), ports.BASIS_LEGACY)

    def test_indian_iron_ore_has_three_gateways_and_no_ranking(self):
        a = ports.assign("IND", "CHN", "iron-ore")
        self.assertEqual(a.basis, "open")
        self.assertEqual({o.load for o in a.options} - {"INDHA", "INVTZ", "INMRM"}, set())
        self.assertGreaterEqual(len({o.load for o in a.options}), 2)

    def test_chinese_grain_and_coal_options(self):
        a = ports.assign("BRA", "CHN", "soybeans")
        self.assertEqual({o.discharge for o in a.options}, {"CNHUA", "CNLYG"})
        for o in ("AUS", "RUS"):
            self.assertEqual(ports.assign(o, "CHN", "coal").main.discharge, "CNCFD")

    def test_indonesian_coal_imports_do_not_land_at_the_loading_terminal(self):
        # no page names an Indonesian coal import port: the loader would take the load row (Tanjung Bara) otherwise
        for o in ("AUS", "RUS", "ZAF", "USA"):
            a = ports.assign(o, "IDN", "coal")
            self.assertEqual(a.main.discharge, "IDSRI", o)
            self.assertEqual(ports.basis_of("IDN", "coal", "discharge", a.main.discharge), ports.BASIS_LEGACY)
        self.assertEqual(ports.assign("IDN", "IND", "coal").main.load, "IDTBA")

    def test_ngqura_is_named_after_its_page(self):
        self.assertIn("Ngqura", ports.port("ZAZBA")["name"])


def _via(a, b):
    import routing
    return routing.route(ports.port(a)["at"], ports.port(b)["at"]).via


class FE4c(unittest.TestCase):
    """Package FE4c: the fixes of the second review (GE4) in the coast and food tables."""

    def test_chinese_grain_stays_on_the_northern_coast(self):
        # GE4.2: all Chinese grain (about 120 Mt) on the south coast was a visible error: no page ranks the ports
        c = ports.candidates("CHN", "soybeans", "discharge")
        self.assertEqual([x[0] for x in c], ["CNLYG", "CNHUA"])
        self.assertEqual({x[2] for x in c}, {ports.BASIS_PAGE})
        self.assertEqual([ports.zone_of(x[0]) for x in c], ["n-china", "s-china"])
        for g in ("soybeans", "wheat", "corn"):
            a = ports.assign("USA", "CHN", g)
            self.assertEqual(a.main.discharge, "CNLYG", g)
            self.assertEqual({o.discharge for o in a.options}, {"CNLYG", "CNHUA"}, g)
        # the sea of the main route does not change with the order of the two rows: still the north China coast
        self.assertEqual(ports.ocean_of("CNLYG"), "pacific")

    def test_us_soybeans_to_china_keep_the_korea_strait(self):
        import routing
        a = ports.assign("USA", "CHN", "soybeans").main
        self.assertIn("korea-strait", routing.route(ports.port(a.load)["at"], ports.port(a.discharge)["at"]).via)

    def test_mozambican_coal_loads_at_the_ports_the_pages_name(self):
        # GE4.4: Beira (Sena railway from Moatize) and Nacala (Nacala railway, coal terminal at Nacala-a-Velha)
        c = ports.candidates("MOZ", "coal", "load")
        self.assertEqual([(x[0], x[2]) for x in c], [("MZBEW", ports.BASIS_PAGE), ("MZMNC", ports.BASIS_PAGE)])
        self.assertEqual([ports.zone_of(x[0]) for x in c], ["e-africa", "e-africa"])
        self.assertNotIn("MZMAP", [x[0] for x in c])
        # searoute codes and coordinates: Beira 34.835 E 19.833 S, Nacala 40.691 E 14.512 S
        self.assertAlmostEqual(ports.port("MZBEW")["at"][0], 34.835, delta=0.01)
        self.assertAlmostEqual(ports.port("MZMNC")["at"][1], -14.512, delta=0.01)
        for code in ("MZBEW", "MZMNC"):
            self.assertTrue(ports.is_seaport(code), code)
        a = ports.assign("MOZ", "IND", "coal")
        self.assertEqual(a.main.load, "MZBEW")
        self.assertEqual({o.load for o in a.options}, {"MZBEW", "MZMNC"})
        for row in [r for r in ports.G["MOZ"] if "coal" in r.families]:
            self.assertTrue(row.url.endswith("/Moatize"))

    def test_sept_iles_note_does_not_turn_history_into_the_present(self):
        row = [r for r in ports.G["CAN"] if r.code == "CASEI"][0]
        self.assertNotIn("the Sept-Iles deep-water seaport was second in Canada", row.note)
        self.assertIn("1950s to 1981", row.note)

    def test_bosnian_rows_of_the_ploce_page(self):
        # L2: coal, iron ore and cereals at Ploce, 'mostly serving Bosnia and Herzegovina'
        for g, fam in (("coal", "coal"), ("iron-ore", "iron-ore"), ("wheat", "grain"), ("soybeans", "grain")):
            c = ports.candidates("BIH", g, "discharge")
            self.assertEqual((c[0][0], c[0][2]), ("HRPLE", ports.BASIS_PAGE), g)
            rows = [r for r in ports.G["BIH"] if r.code == "HRPLE" and fam in r.families and r.role in ("discharge", "both")]
            self.assertTrue(rows and rows[0].url.endswith("Port_of_Plo%C4%8De"), g)
        # bauxite: the page gives it as an export of 1945 only, no row
        self.assertFalse([r for r in ports.G["BIH"] if "bauxite" in r.families])
        self.assertEqual(ports.candidates("BIH", "bauxite", "load"), [])  # the TRANSIT row of the country answers (HRPLE)


class Builders(unittest.TestCase):
    def test_existing_builders_still_import(self):
        for p in (os.path.join(ROOT, "pipeline", "trade"), os.path.join(ROOT, "pipeline", "commodities")):
            if p not in sys.path:
                sys.path.insert(0, p)
        for name in ("build_lanes", "build_freight"):
            mod = importlib.import_module(name)
            self.assertTrue(hasattr(mod, "main"))
        bl = sys.modules["build_lanes"]
        for n in ("A2", "CACHE", "COMMODITY", "DISRUPTIONS", "LATEST_MIN_YEAR", "ROOT", "despike", "gateway", "km", "routing", "save_geom_cache"):
            self.assertTrue(hasattr(bl, n), n)

    def test_build_freight_uses_manual_and_sr(self):
        for code, v in ports.MANUAL.items():
            self.assertEqual(len(v), 4, code)  # (name, iso3, lon, lat): build_freight unpacks four
        self.assertTrue(ports._sr)


class FE5Basis(unittest.TestCase):
    """Package FE5: the fallback to a row of the other role has its own basis (F10), and the source of a gateway is
    the row that makes it a candidate for that cargo and role (F9)."""

    def test_other_direction_has_its_own_basis(self):
        # Rosario's page names Argentine grain exports; an Argentine grain import there rests on the export row
        self.assertEqual(ports.basis_of("ARG", "wheat", "load", "ARUPR"), ports.BASIS_PAGE)
        self.assertEqual(ports.candidates("ARG", "wheat", "discharge")[0], ("ARUPR", "ecsa", ports.BASIS_OTHER))
        self.assertEqual(ports.basis_of("ARG", "wheat", "discharge", "ARUPR"), ports.BASIS_OTHER)
        self.assertEqual(ports.BASES.index(ports.BASIS_OTHER), 1)
        # never for oil and gas terminals
        for iso, rows in ports.G.items():
            for g in ("crude-oil", "refined-products", "lpg", "lng"):
                for role in ("load", "discharge"):
                    self.assertNotIn(ports.BASIS_OTHER, {b for _, _, b in ports.candidates(iso, g, role)}, (iso, g, role))

    def test_source_of_is_the_row_of_that_cargo(self):
        self.assertEqual(ports.source_of("CHN", "soybeans", "discharge", "CNLYG"),
                         ("wikipedia", "https://en.wikipedia.org/wiki/Port_of_Lianyungang"))
        self.assertEqual(ports.source_of("CHN", "soybeans", "discharge", "CNHUA"),
                         ("wikipedia", "https://en.wikipedia.org/wiki/Port_of_Guangzhou"))
        self.assertEqual(ports.source_of("ARG", "wheat", "discharge", "ARUPR"),
                         ("wikipedia", "https://en.wikipedia.org/wiki/Port_of_Rosario"))
        self.assertEqual(ports.source_of("CHN", "potash", "discharge", "CNTSN")[0], "wikipedia")
        # no page read for the cargo: no source, whatever row of another cargo names the port
        code = ports.gateway("USA", "iron-ore", "load")
        self.assertEqual(ports.basis_of("USA", "iron-ore", "load", code), ports.BASIS_LEGACY)
        self.assertEqual(ports.source_of("USA", "iron-ore", "load", code), (None, None))
        for iso in ("JPN", "CHN"):
            for g in ("wheat", "iron-ore"):
                code = ports.gateway(iso, g, "discharge")
                s, url = ports.source_of(iso, g, "discharge", code)
                self.assertFalse(url and "giignl" in url, (iso, g, code, url))


class FE4d(unittest.TestCase):
    """Package FE4d: Saudi crude loads at Ras Tanura, and at Yanbu only for the buyers Yanbu reaches westbound."""

    WEST = ("NLD", "ITA", "ESP", "POL", "USA", "BRA", "EGY")
    ELSEWHERE = ("CHN", "KOR", "JPN", "IND", "SGP", "AUS", "KEN", "ZAF")

    def loads(self, o, d, group="crude-oil"):
        return {x.load for x in ports.assign(o, d, group).options}

    def test_westbound_buyers_keep_both_load_ports(self):
        for d in self.WEST:
            a = ports.assign("SAU", d, "crude-oil")
            self.assertEqual(a.main.load, "SARTA", d)
            self.assertEqual({x.load for x in a.options}, {"SARTA", "SAYNB"}, d)
            self.assertEqual(a.basis, "open", d)
            self.assertEqual(a.rule, "sau-crude-red-sea", d)
            self.assertTrue(all(x.w is None for x in a.options), d)   # no weight, no split of the tonnage

    def test_every_other_buyer_loads_at_ras_tanura_only(self):
        for d in self.ELSEWHERE:
            a = ports.assign("SAU", d, "crude-oil")
            self.assertEqual({x.load for x in a.options}, {"SARTA"}, d)
            self.assertEqual(a.main.load, "SARTA", d)
            self.assertEqual(a.rule, "sau-crude-red-sea", d)

    def test_a_landlocked_european_buyer_is_on_the_westbound_side(self):
        self.assertEqual(self.loads("SAU", "AUT"), {"SARTA", "SAYNB"})

    def test_the_principal_port_and_the_basis(self):
        c = ports.candidates("SAU", "crude-oil", "load")
        self.assertEqual([x[0] for x in c], ["SARTA", "SAYNB"])
        for code in ("SARTA", "SAYNB"):
            self.assertEqual(ports.basis_of("SAU", "crude-oil", "load", code), ports.BASIS_PAGE, code)
            self.assertEqual(ports.source_of("SAU", "crude-oil", "load", code)[0], "wikipedia", code)

    def test_the_rule_is_for_saudi_crude_exports_only(self):
        # products and LPG, and Saudi Arabia as a buyer, are left alone
        for g in ("refined-products", "lpg", "lng", "wheat"):
            self.assertNotEqual(ports.assign("SAU", "CHN", g).rule, "sau-crude-red-sea", g)
        self.assertNotEqual(ports.assign("USA", "SAU", "crude-oil").rule, "sau-crude-red-sea")
        self.assertNotEqual(ports.assign("KWT", "CHN", "crude-oil").rule, "sau-crude-red-sea")

    def test_the_rule_states_its_assumption_its_page_and_its_tonnage(self):
        rule = next(r for r in ports.COAST_RULES if r["id"] == "sau-crude-red-sea")
        self.assertTrue(rule["reason"].startswith("Atlas assumption"))
        self.assertIn("https://www.eia.gov/international/content/analysis/countries_long/Saudi_Arabia/", rule["reason"])
        self.assertEqual(rule["url"], "https://www.eia.gov/international/content/analysis/countries_long/Saudi_Arabia/")
        for text in ("record 18%", "Yanbu", "Europe", "Mt", "no weight"):
            self.assertIn(text, rule["reason"])
        for west in ("NLD", "USA"):
            self.assertIn(("crude-oil", west), rule["open"])
        for east in ("CHN", "IND", "KEN"):
            self.assertNotIn(("crude-oil", east), rule["open"])

    def test_emirati_crude_keeps_both_options_for_every_buyer(self):
        # the EIA brief on the UAE gives a pipeline capacity and the exports, no share loaded at Fujairah: no rule
        self.assertFalse([r for r in ports.COAST_RULES if r["country"] == "ARE"])
        for d in ("CHN", "JPN", "IND", "NLD", "USA"):
            a = ports.assign("ARE", d, "crude-oil")
            self.assertEqual(a.main.load, "AEFJR", d)
            self.assertEqual({x.load for x in a.options}, {"AEFJR", "AEDAS"}, d)


if __name__ == "__main__":
    unittest.main()
