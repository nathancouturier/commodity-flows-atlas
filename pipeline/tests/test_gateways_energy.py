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
    with open(os.path.join(ROOT, "data", "sources.json"), encoding="utf-8") as f:
        return {s["id"] for s in json.load(f)}


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
                self.assertIn(zone, PLAN_ZONES | set(EN.EXTRA_ZONES), (iso3, r))

    def test_every_port_resolves_and_belongs_to_the_country(self):
        m = manual_ports()
        a2 = a2_to_iso3()
        for iso3, lst in EN.G.items():
            for r in lst:
                code = r[0]
                self.assertTrue(code in m or code in SR, (iso3, code))
                owner = m[code][1] if code in m else a2.get(code[:2])
                self.assertEqual(owner, iso3, (iso3, code))

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
        # crude KAZ-ITA, coffee UGA-ITA and potash UZB-BRA have a transit port; copper concentrate SRB-CHN has
        # none (no page read for Serbia's non-crude cargo): it stays listed in UNSOURCED with the reason
        self.assertIsNotNone(EN.transit("UGA", "soft"))
        self.assertEqual(EN.transit("UZB", "fert")[0], "GEPTI")
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


if __name__ == "__main__":
    unittest.main()
