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
        cls.rows = [(iso, r) for iso, rows in ports.G.items() for r in rows]

    def test_tables_are_not_empty(self):
        self.assertGreater(len(self.rows), 40)

    def test_every_row_has_a_source(self):
        for iso, r in self.rows:
            with self.subTest(iso=iso, code=r.code):
                self.assertIn(r.src, self.sources)
                if r.src.startswith("wikipedia"):
                    self.assertTrue(r.url and r.url.startswith("https://en.wikipedia.org/wiki/"), r)

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
        self.assertEqual({x["id"] for x in z}, set(ports.ZONES))
        used = {r.zone for _, r in self.rows}
        self.assertTrue(used <= set(ports.ZONES))
        for x in z:
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


class G11(unittest.TestCase):
    def test_no_port_of_another_family(self):
        """A country that has rows in the new tables never gets a port of another family from gateway()."""
        for iso, rows in ports.G.items():
            for group, seg in ports.SEGMENT.items():
                code = ports.gateway(iso, group)
                if code is None:
                    continue
                ok = {r.code for r in rows if group in r.families or seg in r.families}
                legacy = ports.LEGACY_P.get(iso, {})
                ok |= {legacy[k] for k in (seg, "ore") if k in legacy and (k == seg or seg in ("bauxite", "alumina", "manganese", "nickel"))}
                if seg in ports.ENERGY_SEGMENTS and "any" in legacy:
                    ok.add(legacy["any"])  # the present oil and gas port of the country, kept until a page is read
                with self.subTest(iso=iso, group=group):
                    self.assertIn(code, ok)

    def test_saudi_wheat_is_not_ras_tanura(self):
        self.assertNotEqual(ports.gateway("SAU", "wheat"), "SARTA")
        self.assertNotEqual(ports.gateway("SAU", "wheat", "discharge"), "SARTA")

    def test_role_picks_a_row_of_that_role(self):
        for iso, rows in ports.G.items():
            for r in rows:
                if r.role in ("load", "discharge"):
                    fam = next(iter(r.families))
                    group = next((g for g, s in ports.SEGMENT.items() if g == fam or s == fam), None)
                    if group is None:
                        continue
                    other = "discharge" if r.role == "load" else "load"
                    only = [x for x in ports._rows(iso, group, None)]
                    if all(x.role == r.role for x in only):
                        self.assertIsNone(ports._rows(iso, group, other) or None)


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


class G08(unittest.TestCase):
    """C-020: Mexican concentrates for Asia load on the Pacific."""

    def test_copper_and_zinc_concentrate(self):
        for g, d in (("copper-ore", "CHN"), ("zinc-ore", "KOR"), ("zinc-ore", "JPN"), ("copper-ore", "JPN")):
            a = ports.assign("MEX", d, g)
            with self.subTest(g=g, d=d):
                self.assertEqual(ports.zone_of(a.main.load), "mexico-pacific")
                self.assertLess(nm(a.main.load, a.main.discharge), 8000)

    def test_manzanillo_qingdao(self):
        self.assertAlmostEqual(nm("MXZLO", "CNTAO"), 6982, delta=300)


class G09(unittest.TestCase):
    """Two-ocean countries: the gateway is on the ocean of the other end."""

    def test_guatemala(self):
        self.assertEqual(ports.zone_of(ports.assign("USA", "GTM", "wheat").main.discharge), "cam-caribbean")
        self.assertEqual(ports.zone_of(ports.assign("CHN", "GTM", "steel").main.discharge), "cam-pacific")
        self.assertEqual(ports.zone_of(ports.assign("ARG", "GTM", "soymeal").main.discharge), "cam-caribbean")

    def test_houston_to_central_america_does_not_cross_panama(self):
        for d in ("GTM", "HND", "CRI"):
            m = ports.assign("USA", d, "corn").main
            self.assertEqual(ports.ocean_of(m.discharge), "atlantic", d)
            self.assertLess(nm(m.load, m.discharge), 2500, d)

    def test_colombia_panama_stays_on_the_caribbean(self):
        for g in ("coal", "steel"):
            m = ports.assign("COL", "PAN", g).main
            self.assertEqual(ports.ocean_of(m.load), "atlantic", g)
            self.assertEqual(ports.ocean_of(m.discharge), "atlantic", g)
            self.assertLess(nm(m.load, m.discharge), 1500, g)

    def test_pacific_side_for_asia(self):
        for iso in ("GTM", "HND", "NIC", "CRI", "PAN", "COL", "MEX"):
            m = ports.assign("JPN", iso, "steel").main
            self.assertEqual(ports.ocean_of(m.discharge), "pacific", iso)

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
        self.assertEqual(ports.assign("RUS", "CHN", "wheat").main.load, "RUVYP")

    def test_russian_crude_to_india_is_open(self):
        a = ports.assign("RUS", "IND", "crude-oil")
        self.assertEqual(a.basis, "open")
        self.assertEqual(a.main.load, "RUPRI")
        self.assertIn("RUNVS", {o.load for o in a.options})

    def test_south_east_asian_coal_into_south_china(self):
        for o in ("IDN", "PHL", "VNM", "MYS"):
            self.assertEqual(ports.assign(o, "CHN", "coal").main.discharge, "CNZHA", o)
        self.assertNotEqual(ports.assign("AUS", "CHN", "coal").main.discharge, "CNZHA")

    def test_saudi_dry_cargo(self):
        self.assertEqual(ports.zone_of(ports.assign("EGY", "SAU", "wheat").main.discharge), "red-sea")
        self.assertEqual(ports.zone_of(ports.assign("FRA", "SAU", "wheat").main.discharge), "red-sea")
        self.assertEqual(ports.zone_of(ports.assign("IND", "SAU", "wheat").main.discharge), "meg")
        self.assertEqual(ports.zone_of(ports.assign("AUS", "SAU", "wheat").main.discharge), "meg")

    def test_mexico_by_ocean(self):
        self.assertEqual(ports.zone_of(ports.assign("MEX", "CHN", "zinc-ore").main.load), "mexico-pacific")

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


if __name__ == "__main__":
    unittest.main()
