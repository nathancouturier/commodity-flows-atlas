"""Unit tests of the energy gateways (pipeline/freight/gateways/energy.py).

Tests G02, G05, G06, G09 (crude part), M08 (transit ports resolve) and the unit part of G10 of the engine plan.
The data module is loaded by its path, so these tests do not depend on the loader of ports.py. The tests that
need the sea router skip when routing.py is not importable.
"""
import importlib.util
import json
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "freight"))

FAMILIES = {"crude", "products", "lpg", "lng"}
ROLES = {"load", "discharge", "both"}
# freight zones of the plan (2.4) and the ones energy.py adds itself (EXTRA_ZONES)
PLAN_ZONES = {
    "us-gulf", "us-atlantic", "us-pnw", "us-west", "canada-east", "canada-west", "mexico-gulf", "mexico-pacific",
    "cam-caribbean", "cam-pacific", "caribbean", "ecsa", "wcsa", "nw-europe", "baltic", "med", "black-sea", "meg",
    "red-sea", "wc-india", "ec-india", "sea", "s-china", "n-china", "japan-korea", "w-australia", "e-australia",
    "waf", "s-africa", "e-africa",
}


# zones that gateways/coasts.py defines and energy.py uses (Ningbo is in "e-china")
COASTS_ZONES = {"e-china"}


def load_energy():
    path = os.path.join(ROOT, "pipeline", "freight", "gateways", "energy.py")
    spec = importlib.util.spec_from_file_location("atlas_gateways_energy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EN = load_energy()


def searoute_ports():
    import searoute
    p = os.path.join(os.path.dirname(searoute.__file__), "data", "ports.geojson")
    with open(p, encoding="utf-8-sig") as f:
        return {x["properties"]["port"]: x["geometry"]["coordinates"] for x in json.load(f)["features"]}


SR = searoute_ports()


def known_sources():
    """The ids of data/sources.json and of the source lists that the freight builder merges into it (a new id is in
    pipeline/freight/sources_freight.json until the next rebuild of the data)."""
    import glob
    with open(os.path.join(ROOT, "data", "sources.json"), encoding="utf-8") as f:
        ids = {s["id"] for s in json.load(f)}
    for path in glob.glob(os.path.join(ROOT, "pipeline", "freight", "sources_*.json")):
        with open(path, encoding="utf-8") as f:
            ids |= {s["id"] for s in json.load(f)}
    return ids


def a2_to_iso3():
    with open(os.path.join(ROOT, "data", "countries", "index.json"), encoding="utf-8") as f:
        return {c["a2"]: c["c"] for c in json.load(f)}


def manual_ports():
    """MANUAL of ports.py plus the ports added by energy.py."""
    import ports
    m = dict(ports.MANUAL)
    m.update(EN.MANUAL_EXTRA)
    return m


def coords(code):
    m = manual_ports()
    if code in m:
        return (m[code][2], m[code][3])
    return tuple(SR[code])


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def rows(iso3, family, roles=("load", "discharge", "both")):
    return [r for r in EN.G.get(iso3, []) if family in r[2] and r[3] in roles]


def principal(iso3, family, role):
    """First row of the family that serves the role (a 'both' row serves either)."""
    r = rows(iso3, family, (role, "both"))
    return r[0] if r else None


def lng_layer():
    with open(os.path.join(ROOT, "data", "infrastructure", "lng.geojson"), encoding="utf-8") as f:
        feats = json.load(f)["features"]
    out = {"lng-export": {}, "lng-import": {}}
    for ft in feats:
        p = ft["properties"]
        out[p["type"]].setdefault(p["c"], []).append((p["name"], tuple(ft["geometry"]["coordinates"])))
    return out


class G10Rows(unittest.TestCase):
    def test_row_shape(self):
        for iso3, lst in EN.G.items():
            for r in lst:
                self.assertEqual(len(r), 7, (iso3, r))
                code, zone, fams, role, src, url, note = r
                self.assertTrue(set(fams) and set(fams) <= FAMILIES, (iso3, r))
                self.assertIn(role, ROLES, (iso3, r))
                self.assertIn(zone, PLAN_ZONES | set(EN.EXTRA_ZONES) | COASTS_ZONES, (iso3, r))

    def test_every_port_resolves_and_belongs_to_the_country(self):
        m = manual_ports()
        a2 = a2_to_iso3()
        for iso3, lst in EN.G.items():
            for r in lst:
                code = r[0]
                self.assertTrue(code in m or code in SR, (iso3, code))
                owner = m[code][1] if code in m else a2.get(code[:2])
                if owner != iso3:
                    # a pipeline terminal that is the country's outlet (CPC for Kazakhstan, Ceyhan for Azerbaijan),
                    # Ploce for Bosnia and Herzegovina (the engine treats its 20 km of coast as a coast with no port),
                    # or the port of the country's TRANSIT row (a landlocked end of a pair)
                    foreign = {("KAZ", "KZCPC"), ("AZE", "TRCEY"), ("BIH", "HRPLE")}
                    via_transit = any(EN.transit(iso3, f) and EN.transit(iso3, f)[0] == code for f in r[2])
                    self.assertTrue((iso3, code) in foreign or via_transit, (iso3, code, owner))

    def test_every_row_is_sourced(self):
        ids = known_sources()
        lists = [r for lst in EN.G.values() for r in lst]
        for r in lists:
            self.assertIn(r[4], ids, r)
            self.assertTrue(r[5] and r[5].startswith("https://"), r)
            if r[4] == "wikipedia":
                self.assertTrue(r[5].startswith("https://en.wikipedia.org/wiki/"), r)
        for code, (name, iso3, lon, lat) in EN.MANUAL_EXTRA.items():
            meta = EN.MANUAL_SRC[code]
            self.assertIn(meta["s"], ids, code)
            self.assertTrue(meta["url"].startswith("https://"), code)
            self.assertIn(meta["zone"], PLAN_ZONES | set(EN.EXTRA_ZONES), code)

    def test_no_duplicate_row(self):
        for iso3, lst in EN.G.items():
            keys = [(r[0], r[3], tuple(sorted(r[2]))) for r in lst]
            self.assertEqual(len(keys), len(set(keys)), iso3)


class G02Lng(unittest.TestCase):
    def test_lng_rows_are_within_50_km_of_a_terminal_of_the_layer(self):
        layer = lng_layer()
        checked = 0
        for iso3, lst in EN.G.items():
            for r in lst:
                if "lng" not in r[2]:
                    continue
                for role, kind in (("load", "lng-export"), ("discharge", "lng-import")):
                    if r[3] not in (role, "both") or iso3 not in layer[kind]:
                        continue
                    d = min(km(coords(r[0]), t[1]) for t in layer[kind][iso3])
                    self.assertLessEqual(d, 50, (iso3, r[0], role, round(d)))
                    checked += 1
        self.assertGreater(checked, 40)

    def test_every_country_of_the_layer_has_a_row_of_its_role(self):
        layer = lng_layer()
        for kind, role in (("lng-export", "load"), ("lng-import", "discharge")):
            for iso3 in layer[kind]:
                self.assertIsNotNone(principal(iso3, "lng", role), (iso3, role))

    def test_known_bad_cases_are_gone(self):
        # audit C-010: US LNG to Southampton, Qatar LNG to Augusta, Qatar LNG to Antwerp, all China at Tianjin
        self.assertNotIn(principal("GBR", "lng", "discharge")[0], ("GBSOU",))
        self.assertNotIn(principal("BEL", "lng", "discharge")[0], ("BEANR",))
        self.assertNotEqual(principal("ITA", "lng", "discharge")[0], "ITAUG")
        zones = {r[1] for r in rows("CHN", "lng", ("discharge", "both"))}
        self.assertIn("s-china", zones)
        self.assertIn("n-china", zones)
        self.assertNotEqual(principal("CHN", "lng", "discharge")[0], "CNTSN")


class G05UaeCrude(unittest.TestCase):
    def test_two_load_options_one_inside_the_gulf(self):
        r = rows("ARE", "crude", ("load", "both"))
        self.assertGreaterEqual(len(r), 2)
        self.assertEqual(r[0][0], "AEFJR")
        self.assertEqual(r[0][1], "gulf-of-oman")
        inside = [x for x in r if x[1] == "meg"]
        self.assertTrue(inside)
        self.assertEqual(inside[0][0], "AEDAS")  # Das Island: the page says it exports crude from the Gulf

    def test_hormuz_only_on_the_gulf_option(self):
        try:
            import routing as RT
            RT.route
        except Exception as e:  # routing.py not delivered yet
            self.skipTest("routing.py not available: %s" % e)
        r = rows("ARE", "crude", ("load", "both"))
        jp = coords("JPCHB")
        out = RT.route(coords(r[0][0]), jp, ("southern-ocean",))
        self.assertNotIn("hormuz", out.via)
        inside = [x for x in r if x[1] == "meg"][0]
        out = RT.route(coords(inside[0]), jp, ("southern-ocean",))
        self.assertIn("hormuz", out.via)


class G06Products(unittest.TestCase):
    def test_australia_and_indonesia_do_not_discharge_at_the_wrong_port(self):
        for iso3, bad in (("AUS", "AUPHE"), ("IDN", "IDBPN")):
            r = rows(iso3, "products", ("discharge", "both"))
            self.assertTrue(r, iso3)
            self.assertNotIn(bad, [x[0] for x in r], iso3)
        # Port Hedland is an iron-ore port and Balikpapan a refinery: neither is a products gateway
        self.assertEqual(principal("AUS", "products", "discharge")[1], "e-australia")

    def test_no_products_row_at_a_crude_only_terminal(self):
        for iso3 in EN.G:
            for r in rows(iso3, "products"):
                self.assertNotIn(r[0], ("TRCEY", "NGBON", "CAVAN", "CACXP"), (iso3, r[0]))


class G09Crude(unittest.TestCase):
    def test_canada_crude_is_received_on_the_atlantic(self):
        r = principal("CAN", "crude", "discharge")
        self.assertIsNotNone(r)
        self.assertEqual(r[1], "canada-east")

    def test_panama_crude_has_a_row_on_each_ocean(self):
        zones = {r[1] for r in rows("PAN", "crude", ("discharge", "both"))}
        self.assertIn("cam-caribbean", zones)
        self.assertIn("cam-pacific", zones)
        self.assertEqual(principal("PAN", "crude", "discharge")[1], "cam-caribbean")

    def test_no_panama_nor_cape_horn_for_the_atlantic_pairs(self):
        try:
            import routing as RT
            RT.route
        except Exception as e:
            self.skipTest("routing.py not available: %s" % e)
        origins = {"NGA": "NGBON", "AGO": "AOCAB", "COL": "COCTG", "GUY": "GYGEO"}
        for o, d in (("NGA", "CAN"), ("AGO", "CAN"), ("COL", "PAN"), ("GUY", "PAN")):
            a = coords(origins[o])
            b = coords(principal(d, "crude", "discharge")[0])
            out = RT.route(a, b, ("southern-ocean",))
            self.assertNotIn("panama", out.via, (o, d))
            self.assertNotIn("cape-horn", out.via, (o, d))


class LoaderIntegration(unittest.TestCase):
    """The rows as ports.py serves them (the loader merges the data modules)."""

    @classmethod
    def setUpClass(cls):
        import ports
        cls.ports = ports
        ports.load_modules()

    def test_present_oil_port_is_kept_for_the_families_without_a_row(self):
        # Norway has an LNG row only: crude, products and LPG keep Mongstad, not the nearest port of the label point
        for g in ("crude-oil", "refined-products", "lpg"):
            self.assertEqual(self.ports.gateway("NOR", g, "load"), "NOMON", g)
        self.assertEqual(self.ports.gateway("KOR", "crude-oil", "discharge"), "KRUSN")
        self.assertEqual(self.ports.gateway("NLD", "lpg", "discharge"), "NLRTM")

    def test_principal_gateways(self):
        P = self.ports
        self.assertEqual(P.gateway("ARE", "crude-oil", "load"), "AEFJR")
        self.assertEqual(P.gateway("AUS", "refined-products", "discharge"), "AUBTB")
        self.assertEqual(P.gateway("IDN", "refined-products", "discharge"), "IDTPP")
        self.assertEqual(P.gateway("GBR", "lng", "discharge"), "GBPEM")
        self.assertEqual(P.gateway("BEL", "lng", "discharge"), "BEZEE")
        self.assertEqual(P.gateway("CAN", "crude-oil", "discharge"), "CASJB")

    def test_uae_crude_assignment_has_both_options(self):
        a = self.ports.assign("ARE", "JPN", "crude-oil")
        self.assertEqual(a.basis, "open")
        self.assertEqual({o.load for o in a.options}, {"AEFJR", "AEDAS"})
        self.assertEqual(a.main.load, "AEFJR")

    def test_atlantic_crude_pairs_stay_off_panama_and_cape_horn(self):
        try:
            import routing as RT
            RT.route
        except Exception as e:
            self.skipTest("routing.py not available: %s" % e)
        for o, d in (("NGA", "CAN"), ("AGO", "CAN"), ("COL", "PAN"), ("GUY", "PAN")):
            a = self.ports.assign(o, d, "crude-oil")
            for opt in a.options:
                out = RT.route(coords(opt.load), coords(opt.discharge), ("southern-ocean",))
                self.assertNotIn("panama", out.via, (o, d, opt))
                self.assertNotIn("cape-horn", out.via, (o, d, opt))


class M08Transit(unittest.TestCase):
    def test_every_transit_port_resolves(self):
        m = manual_ports()
        ids = known_sources()
        for iso3, d in EN.TRANSIT.items():
            self.assertIn("default", d.keys() | {"default"})
            for fam, t in d.items():
                code, src, url = t[:3]
                self.assertTrue(code in m or code in SR, (iso3, fam, code))
                self.assertIn(src, ids, (iso3, fam))
                self.assertTrue(url.startswith("https://"), (iso3, fam))
                if src == "wikipedia":
                    self.assertTrue(url.startswith("https://en.wikipedia.org/wiki/"), (iso3, fam))

    def test_kazakh_crude_goes_through_the_cpc_terminal_in_russia(self):
        m = manual_ports()
        t = EN.transit("KAZ", "crude")
        self.assertEqual(t[0], "KZCPC")
        self.assertEqual(m["KZCPC"][1], "RUS")

    def test_the_cases_of_the_plan(self):
        # crude KAZ-ITA and coffee UGA-ITA have a transit port; potash UZB-BRA and copper concentrate SRB-CHN have
        # none (the Poti page names neither Uzbekistan nor Poti as its outlet, review GE3 finding 12; no page read for
        # Serbia's non-crude cargo): they stay listed in UNSOURCED with the reason
        self.assertIsNotNone(EN.transit("UGA", "soft"))
        for iso3 in ("UZB", "TKM", "SVK"):
            self.assertIsNone(EN.transit(iso3, "fert"), iso3)
            self.assertIn(iso3, EN.UNSOURCED)
        self.assertEqual(EN.transit("SRB", "crude")[0], "HROMI")
        self.assertIsNone(EN.transit("SRB", "drybulk"))
        self.assertIn("SRB", EN.UNSOURCED)

    def test_unsourced_countries_have_no_transit_row_for_every_family(self):
        for iso3, why in EN.UNSOURCED.items():
            self.assertTrue(why)
            if iso3 not in EN.TRANSIT:
                self.assertIsNone(EN.transit(iso3, "soft"), iso3)

    def test_family_row_wins_over_default(self):
        self.assertEqual(EN.transit("AZE", "crude")[0], "TRCEY")


class FE4aSourcedGateways(unittest.TestCase):
    """Sourcing pass FE4a: the principal gateway of the largest (country, family, role) ends is the port a page names
    for the cargo, and the loader says so."""

    @classmethod
    def setUpClass(cls):
        import ports
        cls.ports = ports
        ports.load_modules()

    # (country, group, role) -> principal port, every one with the basis "page names the cargo"
    PRINCIPAL = {
        ("CHN", "crude-oil", "discharge"): "CNNGB",   # Port of Ningbo-Zhoushan: crude oil terminal
        ("SAU", "crude-oil", "load"): "SARTA",        # Ras Tanura: largest crude oil export terminal
        ("IND", "crude-oil", "discharge"): "INVAD",   # Vadinar crude oil terminal (Paradip is the east-coast option)
        ("USA", "crude-oil", "load"): "USCRP",        # Port of Corpus Christi: largest gateway for crude exports
        ("USA", "crude-oil", "discharge"): "USHOU",   # EIA company-level imports 2024: Houston, the largest seaport of entry
        ("USA", "refined-products", "discharge"): "USEWR",   # same file: Newark (New York Harbor) enters the most products
        ("TWN", "crude-oil", "discharge"): "TWMAL",   # EIA country brief: Mai Liao 55% of Taiwan's crude imports in 2025
        ("LBY", "refined-products", "load"): "LYRLA",  # the Ras Lanuf page: loading crude oil and oil products
        ("USA", "lpg", "load"): "USHOU",              # Enterprise Products NGL export terminals, Houston Ship Channel
        ("IRQ", "crude-oil", "load"): "IQBOT",
        ("JPN", "crude-oil", "discharge"): "JPCHB",   # Port of Chiba imports crude petroleum and oil products
        ("JPN", "refined-products", "discharge"): "JPCHB",
        ("BRA", "crude-oil", "load"): "BRADR",        # Angra dos Reis, not Santos
        ("NOR", "crude-oil", "load"): "NOMON",
        ("NGA", "crude-oil", "load"): "NGBON",
        ("DEU", "crude-oil", "discharge"): "DEWVN",
        ("KAZ", "crude-oil", "load"): "KZCPC",
        ("AZE", "crude-oil", "load"): "TRCEY",
        ("AGO", "crude-oil", "load"): "AOCAB",
        ("MEX", "crude-oil", "load"): "MXDBT",
        ("QAT", "crude-oil", "load"): "QAHAL",       # Halul Island loading terminal, not Mesaieed
        ("GBR", "crude-oil", "load"): "GBSCU",
        ("GBR", "refined-products", "discharge"): "GBFAW",
        ("GBR", "refined-products", "load"): "GBFAW",
        ("POL", "crude-oil", "discharge"): "PLGDN",
        ("LBY", "crude-oil", "load"): "LYRLA",       # Ras Lanuf, not Tripoli
        ("VEN", "crude-oil", "load"): "VEPJO",
        ("VEN", "refined-products", "load"): "VEPJO",
        ("SGP", "crude-oil", "discharge"): "SGSIN",
        ("SGP", "refined-products", "load"): "SGSIN",
        ("RUS", "refined-products", "load"): "RUPRI",
        ("FRA", "refined-products", "discharge"): "FRLEH",
        ("DEU", "refined-products", "discharge"): "DEWVN",
        ("BIH", "refined-products", "discharge"): "HRPLE",
        ("AUT", "crude-oil", "discharge"): "ITTRS",
        ("CZE", "crude-oil", "discharge"): "ITTRS",
        ("HUN", "crude-oil", "discharge"): "HROMI",
        ("SRB", "crude-oil", "discharge"): "HROMI",
    }

    def test_principal_gateway_and_basis(self):
        for (iso3, group, role), code in self.PRINCIPAL.items():
            c = self.ports.candidates(iso3, group, role)
            self.assertTrue(c, (iso3, group, role))
            self.assertEqual(c[0][0], code, (iso3, group, role))
            self.assertEqual(c[0][2], self.ports.BASIS_PAGE, (iso3, group, role))
            self.assertEqual(self.ports.basis_of(iso3, group, role, code), self.ports.BASIS_PAGE)

    def test_coast_options(self):
        # Saudi Arabia: Gulf first, Red Sea second; India: west coast first, east coast second
        self.assertEqual([c[0] for c in self.ports.candidates("SAU", "crude-oil", "load")], ["SARTA", "SAYNB"])
        self.assertEqual([c[0] for c in self.ports.candidates("IND", "crude-oil", "discharge")], ["INVAD", "INPRT"])
        self.assertEqual([c[0] for c in self.ports.candidates("RUS", "refined-products", "load")], ["RUPRI", "RUNJK"])
        # United States (EIA company-level imports, 2024): Gulf first, then the Pacific and the Atlantic coast
        self.assertEqual([c[0] for c in self.ports.candidates("USA", "crude-oil", "discharge")], ["USHOU", "USLGB", "USEWR"])
        self.assertEqual([c[0] for c in self.ports.candidates("USA", "refined-products", "discharge")], ["USEWR", "USHOU", "USLAX"])
        self.assertEqual([c[0] for c in self.ports.candidates("TWN", "crude-oil", "discharge")], ["TWMAL", "TWKHH"])

    def test_legacy_ports_replaced_by_a_sourced_port(self):
        # Libyan crude no longer loads at Tripoli, Brazilian crude at Santos, Qatari crude at Mesaieed, US crude
        # imports at Corpus Christi (and, since FE4c, Italian crude at Trieste, a port of the Transalpine pipeline)
        for (iso3, group, role), old in {("LBY", "crude-oil", "load"): "LYTIP", ("BRA", "crude-oil", "load"): "BRSSZ",
                                          ("QAT", "crude-oil", "load"): "QAMES", ("USA", "crude-oil", "discharge"): "USCRP",
                                          ("IND", "crude-oil", "discharge"): "INSIK", ("GBR", "refined-products", "load"): "GBSOU"}.items():
            self.assertNotIn(old, [c[0] for c in self.ports.candidates(iso3, group, role)], (iso3, group, role))
        self.assertNotIn("ITTRS", [c[0] for c in self.ports.candidates("ITA", "crude-oil", "discharge")])

    def test_every_new_port_is_a_seaport(self):
        P = self.ports
        new = set(self.PRINCIPAL.values()) | {"SAYNB", "INPRT", "RUNJK", "HRPLE", "SDPZU", "DEHAM", "USLGB", "USLAX", "TWKHH"}
        for code in sorted(new):
            if code in EN.OFFSHORE:
                self.assertLessEqual(P.sea_km(code), 40, code)   # open water: the test of is_seaport does not apply
            else:
                self.assertTrue(P.is_seaport(code), code)

    def test_offshore_terminals_have_the_coordinates_of_their_page(self):
        # infobox: Halul Island 25.67500 N 52.41139 E (the LOOP row went in FE4c: the EIA file of imports names Houston)
        for code, (lon, lat) in {"QAHAL": (52.41139, 25.675)}.items():
            m = EN.MANUAL_EXTRA[code]
            self.assertLess(km((m[2], m[3]), (lon, lat)), 1.0, code)
            self.assertIn(code, EN.OFFSHORE)
            self.assertEqual(EN.MANUAL_SRC[code]["s"], "wikipedia")

    def test_pairs_between_landlocked_countries_get_a_port_at_both_ends(self):
        # Kazakh crude to Austria, Azerbaijani crude to Czechia: the sea outlet of the seller (build_lanes puts the
        # TRANSIT port there) and the port of the buyer's pipeline
        for o, d, ld, ds in (("KAZ", "AUT", "KZCPC", "ITTRS"), ("AZE", "CZE", "TRCEY", "ITTRS"), ("KAZ", "SRB", "KZCPC", "HROMI")):
            a = self.ports.assign(o, d, "crude-oil")
            self.assertEqual((a.main.load, a.main.discharge), (ld, ds), (o, d))
        # a landlocked buyer's port is its TRANSIT port
        for iso3 in ("AUT", "CZE", "HUN", "SRB"):
            self.assertEqual(self.ports.candidates(iso3, "crude-oil", "discharge")[0][0], EN.transit(iso3, "crude")[0], iso3)

    def test_new_transit_rows(self):
        # Batumi is no products row (review GE4, finding 3): its page names crude going to refining there, no product
        self.assertIsNone(EN.transit("KAZ", "products"))
        self.assertIsNone(EN.transit("AZE", "products"))
        self.assertEqual(EN.transit("KAZ", "crude")[0], "KZCPC")        # a family row still wins over nothing else
        self.assertIsNone(EN.transit("KAZ", "drybulk"))                  # no page names a sea outlet for Kazakh coal
        self.assertEqual(EN.transit("CZE", "drybulk")[0], "DEHAM")
        self.assertEqual(EN.transit("CZE", "crude")[0], "ITTRS")         # the family row wins over the default
        self.assertEqual(EN.transit("SSD", "crude")[0], "SDPZU")
        self.assertIsNone(EN.transit("SSD", "metal"))

    def test_unsourced_ports_are_listed_with_what_is_missing(self):
        fams = {"crude", "products", "lpg", "lng"}
        roles = {"load", "discharge"}
        for key, why in EN.UNSOURCED_PORTS.items():
            iso3, fam, role = key.split("/")
            self.assertIn(fam, fams, key)
            self.assertIn(role, roles, key)
            self.assertTrue(why, key)
            # a case listed as unsourced must not also have a sourced row of its family and role
            self.assertIsNone(principal(iso3, fam, role), key)


class FE4cGateways(unittest.TestCase):
    """Package FE4c: the fixes after the second review (GE4) and the leads it left."""

    @classmethod
    def setUpClass(cls):
        import ports
        cls.ports = ports
        ports.load_modules()

    def test_italian_crude_is_not_drawn_into_trieste(self):
        # GE4.1: Trieste's crude is the Transalpine pipeline's (Austria, Germany, Czechia); Italy's refineries are elsewhere
        self.assertFalse([r for r in EN.G["ITA"] if r[0] == "ITTRS"])
        # FE4d: the refineries of the Wikipedia list of oil refineries are rows (Priolo, Taranto, Augusta), not the pipeline's port
        c = self.ports.candidates("ITA", "crude-oil", "discharge")
        self.assertEqual([x[0] for x in c], ["ITPRI", "ITTAR", "ITAUG"])
        self.assertEqual({x[2] for x in c}, {self.ports.BASIS_PAGE})
        self.assertNotIn("ITA/crude/discharge", EN.UNSOURCED_PORTS)
        # the landlocked buyers of the pipeline keep the port their page documents
        for iso3 in ("AUT", "CZE"):
            self.assertEqual(self.ports.candidates(iso3, "crude-oil", "discharge")[0][0], "ITTRS", iso3)
        a = self.ports.assign("LBY", "ITA", "crude-oil")
        self.assertNotEqual(a.main.discharge, "ITTRS")

    def test_batumi_is_no_products_row(self):
        # GE4.3: the page names crude going to refining at Batumi, no refined product
        for iso3, d in EN.TRANSIT.items():
            for fam, t in d.items():
                self.assertNotEqual(t[0], "GEBUS", (iso3, fam))
        for iso3 in ("KAZ", "AZE"):
            self.assertIn("Batumi", EN.UNSOURCED[iso3])
            self.assertIsNone(EN.transit(iso3, "products"))
        self.assertEqual(self.ports.assign("KAZ", "NLD", "refined-products").basis, "unrouted")

    def test_rows_that_rested_on_history_or_existence_are_gone(self):
        # GE4.6: Mina al-Ahmadi (first export in 1946), Esmeraldas (a pipeline terminus): the port used before answers
        for iso3, role, code in (("KWT", "load", "KWMEA"), ("ECU", "load", "ECESM")):
            self.assertFalse([r for r in EN.G.get(iso3, []) if r[0] == code and "crude" in r[2]], iso3)
            self.assertIn(iso3 + "/crude/" + role, EN.UNSOURCED_PORTS)
            c = self.ports.candidates(iso3, "crude-oil", role)
            self.assertEqual((c[0][0], c[0][2]), (code, self.ports.BASIS_LEGACY), iso3)

    def test_ras_lanuf_page_names_crude_and_products(self):
        r = [x for x in EN.G["LBY"] if x[0] == "LYRLA"][0]
        self.assertEqual(r[2], {"crude", "products"})
        self.assertIn("loading crude oil and oil products", r[6])
        self.assertEqual(self.ports.candidates("LBY", "refined-products", "load")[0], ("LYRLA", "med", self.ports.BASIS_PAGE))

    def test_singapore_products_rest_on_the_eia_brief(self):
        r = [x for x in EN.G["SGP"] if "products" in x[2] and x[3] == "load"][0]
        self.assertEqual((r[0], r[4]), ("SGSIN", "eia-cab"))
        self.assertTrue(r[5].startswith("https://www.eia.gov/international/analysis/country/"))
        self.assertEqual(self.ports.source_of("SGP", "refined-products", "load", "SGSIN"), (r[4], r[5]))

    def test_notes_say_what_their_page_says(self):
        # GE4.6: the Adria branch to Hungary does not pass through Serbia; Primorsk's page gives products tonnages
        for iso3 in ("HUN", "SRB"):
            for r in EN.G[iso3]:
                self.assertNotIn("through Croatia and Serbia", r[6], iso3)
            self.assertNotIn("Serbia to Hungary", EN.transit(iso3, "crude")[3])
        self.assertIn("Gola", EN.G["HUN"][0][6])
        self.assertIn("Pancevo", EN.G["SRB"][0][6])
        primorsk = [x for x in EN.G["RUS"] if x[0] == "RUPRI" and "products" in x[2]][0]
        self.assertIn("13.5", primorsk[6])

    def test_united_states_ports_of_entry_come_from_the_eia_file(self):
        # GE4.8: Houston is the largest seaport of entry of 2024; LOOP is no port of entry of the file
        for fam in ("crude", "products"):
            rows = [x for x in EN.G["USA"] if fam in x[2] and x[3] == "discharge"]
            self.assertTrue(rows, fam)
            for r in rows:
                self.assertEqual(r[4], "eia-company-imports", r)
                self.assertEqual(r[5], "https://www.eia.gov/petroleum/imports/companylevel/")
        self.assertNotIn("USLOP", EN.MANUAL_EXTRA)
        self.assertEqual({x[1] for x in EN.G["USA"] if "crude" in x[2] and x[3] == "discharge"}, {"us-gulf", "us-west", "us-atlantic"})
        # the principal stays on the Gulf: an Atlantic or Gulf origin has no Pacific option, a Pacific origin has one
        a = self.ports.assign("SAU", "USA", "crude-oil")
        self.assertEqual(a.main.discharge, "USHOU")
        self.assertEqual({o.discharge for o in a.options}, {"USHOU", "USEWR"})
        a = self.ports.assign("ECU", "USA", "crude-oil")
        self.assertEqual(a.main.discharge, "USHOU")
        self.assertIn("USLGB", {o.discharge for o in a.options})
        self.assertIn("USA/products/load", EN.UNSOURCED_PORTS)

    def test_taiwan_crude_ports_are_the_two_of_the_brief_that_the_list_has(self):
        rows = [x for x in EN.G["TWN"] if "crude" in x[2]]
        self.assertEqual([x[0] for x in rows], ["TWMAL", "TWKHH"])
        for x in rows:
            self.assertEqual((x[3], x[4]), ("discharge", "eia-cab"))
        self.assertIn("55%", rows[0][6])
        self.assertNotIn("TWN/crude/discharge", EN.UNSOURCED_PORTS)

    def test_indonesian_refineries_are_the_crude_rows_and_products_stay_unsourced(self):
        # GE6.3, answered in FE4d: a refinery is evidence (the EIA brief lists the refineries by place and capacity); the brief
        # says nothing of exports of products or of LPG at a port
        self.assertNotIn("IDN/crude/discharge", EN.UNSOURCED_PORTS)
        for key in ("IDN/products/load", "IDN/lpg/discharge"):
            self.assertIn(key, EN.UNSOURCED_PORTS)

    def test_fujairah_products_row_is_gone(self):
        # GE6.6: the Fujairah page names a bunkering hub and crude storage, not UAE refined products loaded for export
        self.assertFalse([x for x in EN.G["ARE"] if x[0] == "AEFJR" and "products" in x[2]])
        c = self.ports.candidates("ARE", "refined-products", "load")
        self.assertEqual(c[0][0], "AERUW")
        self.assertNotIn("AEFJR", [x[0] for x in c])

    def test_every_lng_exporter_of_the_layer_has_a_row_at_its_terminal(self):
        # L1: Brunei, Cameroon, Equatorial Guinea, Peru, Yemen, Mexico, and the Qingdao row on the terminal's new point
        layer = lng_layer()
        for iso3 in ("BRN", "CMR", "GNQ", "PER", "YEM", "MEX"):
            self.assertIn(iso3, layer["lng-export"], iso3)
            r = principal(iso3, "lng", "load")
            self.assertIsNotNone(r, iso3)
            self.assertEqual(r[4], "giignl-2026")
            self.assertTrue(r[5].startswith("https://www.worldlngsummit.com/"), r)
            d = min(km(coords(r[0]), t[1]) for t in layer["lng-export"][iso3])
            self.assertLess(d, 50, (iso3, r[0], round(d)))
            self.assertEqual(self.ports.candidates(iso3, "lng", "load")[0][0], r[0])
            self.assertTrue(self.ports.is_seaport(r[0]), r[0])
        self.assertEqual(principal("CMR", "lng", "load")[0], "CMKBI")
        self.assertEqual(principal("MEX", "lng", "load")[0], "MXATM")
        self.assertEqual(principal("YEM", "lng", "load")[0], "YEBAL")
        # a manual port at the terminal where the searoute list has none within 100 km (Balhaf, Dongjiakou)
        for code, iso3, name in (("YEBAL", "YEM", "Yemen LNG (Balhaf)"), ("CNDJK", "CHN", "Qingdao LNG Terminal")):
            kind = "lng-export" if iso3 == "YEM" else "lng-import"
            t = [x for x in layer[kind][iso3] if x[0] == name][0][1]
            self.assertLess(km(coords(code), t), 1.0, code)
            self.assertIn(EN.MANUAL_SRC[code]["s"], known_sources())
        qd = [r for r in EN.G["CHN"] if "lng" in r[2] and r[1] == "n-china"]
        self.assertEqual(qd[0][0], "CNDJK")
        self.assertNotIn("CNTAO", [r[0] for r in EN.G["CHN"] if "lng" in r[2]])

    def test_the_mexican_gulf_row_does_not_displace_dos_bocas(self):
        self.assertEqual(self.ports.candidates("MEX", "crude-oil", "load")[0][0], "MXDBT")


class FE4dRefineries(unittest.TestCase):
    """Package FE4d: a refinery at a coastal place, with its capacity, on an EIA country brief (source id eia-cab) or on the
    Wikipedia list of oil refineries supports a crude discharge row at that place's port, and a products load row when the
    page says that the country exports products. The principal port is the place of the largest refinery of the page's own
    table (capacities in thousand barrels a day, as the pages give them)."""

    @classmethod
    def setUpClass(cls):
        import ports
        cls.ports = ports
        ports.load_modules()

    # (country, family, role) -> the ports in the order of the page's table, and the capacity of each place
    TABLES = {
        ("IDN", "crude", "discharge"): (["IDBPN", "IDCXP", "IDDUM", "IDBAL"], [360, 348, 170, 150]),      # EIA Indonesia, 2025
        ("KOR", "crude", "discharge"): (["KRUSN", "KRTSN", "KRYOS", "KRINC"], [1383, 809, 744, 349]),     # EIA South Korea, 2023
        ("NLD", "crude", "discharge"): (["NLRTM", "NLVLI"], [994, 190]),                                    # Wikipedia list
        ("ESP", "crude", "discharge"): (["ESBIO", "ESCAR", "ESTAR"], [240, 220, 206]),                      # Wikipedia list
        ("ITA", "crude", "discharge"): (["ITPRI", "ITTAR", "ITAUG"], [220, 120, 100]),                      # Wikipedia list
        ("MYS", "crude", "discharge"): (["MYPEN", "MYPDI"], [300, 241]),                                    # EIA Malaysia, 2024
        ("MYS", "products", "load"): (["MYPEN", "MYPDI"], [300, 241]),
        ("THA", "crude", "discharge"): (["THSRI"], [177]),                                                  # Wikipedia list
        ("THA", "products", "load"): (["THSRI"], [177]),
        ("IND", "products", "load"): (["INSIK", "INBOM", "INVAD"], [1437, 431, 404]),                       # EIA India, 2025
    }

    def test_each_country_lists_its_places_in_the_order_of_the_table(self):
        for (iso3, fam, role), (codes, caps) in self.TABLES.items():
            self.assertEqual(caps, sorted(caps, reverse=True), (iso3, fam))
            rows = [r for r in EN.G[iso3] if fam in r[2] and r[3] == role and r[4] in ("eia-cab", "wikipedia")
                    and r[0] in codes and r[5].startswith(("https://www.eia.gov/", "https://en.wikipedia.org/wiki/"))]
            self.assertEqual([r[0] for r in rows], codes, (iso3, fam, role))
            c = self.ports.candidates(iso3, "crude-oil" if fam == "crude" else "refined-products", role)
            self.assertEqual([x[0] for x in c][:len(codes)], codes, (iso3, fam, role))
            self.assertEqual({x[2] for x in c}, {self.ports.BASIS_PAGE}, (iso3, fam, role))

    def test_the_largest_place_is_the_principal_port(self):
        self.assertEqual(principal("IDN", "crude", "discharge")[0], "IDBPN")   # Balikpapan 360 against Cilacap 348
        self.assertEqual(principal("KOR", "crude", "discharge")[0], "KRUSN")
        self.assertEqual(principal("IND", "products", "load")[0], "INSIK")
        self.assertEqual(principal("MYS", "crude", "discharge")[0], "MYPEN")
        self.assertEqual(principal("NLD", "crude", "discharge")[0], "NLRTM")

    def test_every_row_says_that_the_page_names_the_refinery_not_the_berth(self):
        for iso3 in ("IDN", "KOR", "NLD", "ESP", "ITA", "MYS", "THA", "IND", "JPN"):
            for r in EN.G[iso3]:
                if r[4] in ("eia-cab", "wikipedia") and ("refiner" in r[6] or "Refiner" in r[6]) and r[0] not in ("JPCHB", "INPRT", "INVAD"):
                    self.assertTrue("not the berth" in r[6] or "neither page names the berth" in r[6] or "names the berth" in r[6], (iso3, r[0]))
        # the capacities in the notes are the pages' own, with their unit
        self.assertIn("360 thousand barrels a day", EN.G["IDN"][3][6])
        self.assertIn("348 thousand barrels a day", EN.G["IDN"][4][6])

    def test_products_rows_exist_only_where_the_page_says_the_country_exports_products(self):
        for iso3 in ("KOR", "NLD", "IDN", "ITA", "ESP", "JPN"):
            rows = [r for r in EN.G[iso3] if "products" in r[2] and r[3] == "load" and r[4] in ("eia-cab", "wikipedia")]
            self.assertFalse(rows, iso3)
        for iso3, text in (("MYS", "exported 1.3 million b/d of petroleum products"), ("THA", "net exporter of petroleum products"),
                           ("IND", "exports petroleum products")):
            rows = [r for r in EN.G[iso3] if "products" in r[2] and r[3] == "load"]
            self.assertTrue(rows, iso3)
            self.assertTrue(any(text in r[6] for r in rows), iso3)

    def test_pengerang_is_a_manual_port_at_the_coordinates_of_its_page(self):
        code = "MYPEN"
        name, iso3, lon, lat = EN.MANUAL_EXTRA[code]
        self.assertEqual((iso3, lon, lat), ("MYS", 104.117, 1.367))   # Pengerang: 1 22 N 104 07 E
        self.assertEqual(EN.MANUAL_SRC[code]["url"], "https://en.wikipedia.org/wiki/Pengerang")
        self.assertTrue(self.ports.is_seaport(code))

    def test_cilacap_is_the_searoute_point_tanjung_intan(self):
        # the Cilacap page gives 7 44 S, 109 0 E; the searoute point is under 3 km from it
        lon, lat = coords("IDCXP")
        self.assertLess(km((lon, lat), (109.0, -(7 + 44 / 60))), 3)
        self.assertIn("Tanjung Intan", [r for r in EN.G["IDN"] if r[0] == "IDCXP"][0][6])
        self.assertTrue(self.ports.is_seaport("IDCXP"))

    def test_indonesian_crude_no_longer_crosses_the_makassar_strait_on_every_option(self):
        import routing
        a = self.ports.assign("NGA", "IDN", "crude-oil")
        self.assertEqual(a.main.discharge, "IDBPN")
        self.assertIn("IDCXP", {o.discharge for o in a.options})
        # Cilacap is reached from the Cape without the strait; Balikpapan is not
        via = {o.discharge: set(routing.route(coords(o.load), coords(o.discharge), ()).via) for o in a.options}
        self.assertIn("makassar", via["IDBPN"])
        self.assertNotIn("makassar", via["IDCXP"])

    def test_the_uae_rows_name_why_both_load_ports_stay_options(self):
        rows = {r[0]: r for r in EN.G["ARE"] if "crude" in r[2]}
        self.assertIn("1.8 million b/d", rows["AEFJR"][6])
        self.assertIn("no share loaded at Fujairah", rows["AEFJR"][6])
        self.assertIn("so both ports stay options", rows["AEDAS"][6])
        # the text that the "up to" note of Hormuz can quote
        self.assertIn("not the share loaded at each port", EN.OPEN_REASONS[("ARE", "crude")])
        self.assertIn("18%", EN.OPEN_REASONS[("SAU", "crude")])


if __name__ == "__main__":
    unittest.main()
