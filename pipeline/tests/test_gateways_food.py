"""Tests G01, G10 and G11 (unit part) of the trade-engine plan for package E4a-gateways-food.

The data under test is pipeline/freight/gateways/food.py: gateways for grain, vegetable oil, fertiliser and
general cargo ("box"). The module is loaded from its file, so these tests do not depend on the loader of
package E4b (ports.py). The loader tests at the end are skipped until that loader exists.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
"""
import importlib.util
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("freight", "trade", "geo"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))

import ports  # noqa: E402

FOOD_PATH = os.path.join(ROOT, "pipeline", "freight", "gateways", "food.py")
W_AQABA = "https://en.wikipedia.org/wiki/Aqaba"

# Zones of section 2.4 of the plan (gateways/coasts.py of package E4b holds the same list).
ZONES = {
    "us-gulf", "us-atlantic", "us-pnw", "us-west", "canada-east", "canada-west", "mexico-gulf", "mexico-pacific",
    "cam-caribbean", "cam-pacific", "caribbean", "ecsa", "wcsa", "nw-europe", "baltic", "med", "black-sea", "meg",
    "red-sea", "wc-india", "ec-india", "sea", "s-china", "n-china", "japan-korea", "w-australia", "e-australia",
    "waf", "s-africa", "e-africa",
    "taiwan", "gulf-of-oman",  # declared by gateways/energy.py, used by the general-cargo rows of FE4b
}
FAMILIES = {"grain", "sugar", "vegoil", "fert", "box"}
# a row may name one group of a family when its page names that cargo only (ammonia and soya meal: the Montoir rows of France, FNCA)
GROUP_FAMILIES = {"urea", "potash", "phosphate-rock", "ammonia", "soymeal"}
ROLES = {"load", "discharge", "both"}

# G01: the terminals that today receive food and fertiliser lanes although they are oil, gas or ore terminals.
ENERGY_TERMINALS = {"SARTA", "IQBOT", "NGBON", "DZAZW", "TRCEY", "AUPHE", "IDBPN", "USCRP"}
FOOD_GROUPS = ["wheat", "corn", "soybeans", "soymeal", "rice", "sugar", "rapeseed", "palm-oil", "soyoil", "potash",
               "urea", "dap", "phosphate-rock"]
# The countries named in point 4 of section 2.4 with a discharge of food or fertiliser at an energy terminal.
PRIORITY_DISCHARGE = ["IDN", "ESP", "TUR", "USA", "MYS", "DEU", "SAU", "DZA", "ITA", "IRQ", "NGA", "AUS"]


def load_food():
    spec = importlib.util.spec_from_file_location("gateways_food", FOOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_json(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return json.load(f)


def rows_of(food):
    return [(iso, i, r) for iso, rows in food.G.items() for i, r in enumerate(rows)]


def principal(food, iso3, family, roles):
    """Code of the first row of a country that carries the family in one of the roles."""
    for r in food.G.get(iso3, []):
        if family in r[2] and r[3] in roles:
            return r[0]
    return None


class FoodGateways(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.food = load_food()
        cls.sources = {s["id"] for s in load_json("data", "sources.json")}
        cls.a2 = {c["c"]: c["a2"] for c in load_json("data", "countries", "index.json")}

    # ------------------------------------------------------------------ G10: form, sources, codes
    def test_g10_rows_have_seven_fields_and_valid_values(self):
        for iso, i, r in rows_of(self.food):
            where = f"{iso}[{i}] {r[:1]}"
            self.assertIsInstance(r, tuple, where)
            self.assertEqual(len(r), 7, where)
            code, zone, fam, role, src, url, note = r
            self.assertIn(iso, self.a2, where)
            self.assertIn(zone, ZONES, where)
            self.assertTrue(fam and set(fam) <= FAMILIES | GROUP_FAMILIES, where)
            self.assertIn(role, ROLES, where)
            self.assertTrue(note and note.strip(), f"{where}: a row carries a note with what the page says")

    def test_g10_every_row_has_a_source_that_exists(self):
        for iso, i, r in rows_of(self.food):
            code, zone, fam, role, src, url, note = r
            where = f"{iso}[{i}] {code}"
            self.assertIn(src, self.sources, where)
            self.assertTrue(url and url.startswith("https://"), f"{where}: the page read")
            if src == "wikipedia":
                # the English page, or the French one where the English Wikipedia has none (the French ports of FNCA: Rouen, La Rochelle, Nantes-Saint-Nazaire)
                self.assertTrue(url.startswith(("https://en.wikipedia.org/wiki/", "https://fr.wikipedia.org/wiki/")), where)

    def test_g10_codes_resolve_and_belong_to_their_country(self):
        extra = self.food.MANUAL_EXTRA
        for iso, i, r in rows_of(self.food):
            code = r[0]
            where = f"{iso}[{i}] {code}"
            known = code in ports._sr or code in ports.MANUAL or code in extra
            self.assertTrue(known, f"{where}: not in searoute, ports.MANUAL or MANUAL_EXTRA")
            if (iso, code) == ("BIH", "HRPLE"):
                # a coast with no port of its own: Ploce, in Croatia, is its outlet (the page says it mostly serves it)
                continue
            self.assertEqual(code[:2], self.a2[iso], f"{where}: the LOCODE prefix is the country's alpha-2 code")

    def test_g10_manual_extra_entries_are_new_and_used(self):
        used = {r[0] for _, _, r in rows_of(self.food)}
        for code, entry in self.food.MANUAL_EXTRA.items():
            self.assertNotIn(code, ports._sr, f"{code} exists in searoute: not an extra")
            # The loader of package E4b copies MANUAL_EXTRA into ports.MANUAL: it may be there, with the same entry.
            self.assertIn(ports.MANUAL.get(code, entry), (entry,), f"{code} is in ports.MANUAL with another entry")
            self.assertEqual(len(entry), 4, code)
            name, iso3, lon, lat = entry
            self.assertTrue(name and iso3 in self.a2, code)
            self.assertEqual(code[:2], self.a2[iso3], code)
            self.assertTrue(-180 <= lon <= 180 and -90 <= lat <= 90, code)
            self.assertIn(code, used, f"{code} is defined but no row uses it")

    def test_g10_no_duplicate_rows(self):
        seen = set()
        for iso, i, r in rows_of(self.food):
            key = (iso, r[0], r[2], r[3])
            self.assertNotIn(key, seen, f"{iso} {r[0]} appears twice")
            seen.add(key)

    # ------------------------------------------------------------------ G01: no food at an energy terminal
    def test_g01_no_row_at_an_energy_terminal(self):
        for iso, i, r in rows_of(self.food):
            self.assertNotIn(r[0], ENERGY_TERMINALS, f"{iso}: {r[0]} is an oil, gas or ore terminal")

    def test_g01_principal_discharge_of_priority_countries(self):
        """Each country of point 4 either has a sourced food discharge gateway or is listed as not committed."""
        for iso in PRIORITY_DISCHARGE:
            if iso in self.food.G:
                found = [principal(self.food, iso, f, {"discharge", "both"}) for f in ("grain", "fert", "vegoil", "box")]
                self.assertTrue(any(found), iso)
                for code in found:
                    self.assertNotIn(code, ENERGY_TERMINALS, iso)
            else:
                self.assertIn(iso, self.food.UNSOURCED, f"{iso} has neither rows nor an entry in UNSOURCED")

    def test_g01_saudi_food_goes_to_the_red_sea_first(self):
        # The corn "through Hormuz" estimate of the audit came from Saudi grain sent to Ras Tanura. The Jeddah page
        # names containers only (review GE3, finding 4), so Saudi food has no row of its own and takes the general
        # cargo row, Red Sea first.
        self.assertEqual(principal(self.food, "SAU", "box", {"discharge", "both"}), "SAJED")
        for fam in ("grain", "vegoil", "fert"):
            self.assertIsNone(principal(self.food, "SAU", fam, {"discharge", "both"}), fam)
            self.assertIn("SAU", self.food.UNSOURCED)

    def test_g01_pinned_principals(self):
        pins = [
            ("TUR", "grain", "TRMER"), ("DEU", "grain", "DEHAM"), ("AUS", "fert", "AUKWI"), ("EGY", "grain", "EGALY"),
            ("PER", "grain", "PECLL"), ("ESP", "fert", "ESSAG"), ("IDN", "box", "IDTPP"), ("MYS", "box", "MYPKG"),
            ("NGA", "box", "NGAPP"), ("MEX", "box", "MXZLO"),
        ]
        for iso, fam, code in pins:
            self.assertEqual(principal(self.food, iso, fam, {"discharge", "both"}), code, f"{iso} {fam}")
        # Review GE3: rows whose page names no cargo of the family are gone (bulk alone names no grain)
        for iso, fam in (("IDN", "grain"), ("MYS", "grain"), ("NGA", "grain"), ("ITA", "grain"), ("ESP", "grain"),
                         ("CHN", "grain"), ("MEX", "grain"), ("MEX", "fert")):
            self.assertIsNone(principal(self.food, iso, fam, {"discharge", "both"}), f"{iso} {fam}")
        # The Agrium report names urea only; Canpotex names Vancouver for potash
        self.assertEqual(principal(self.food, "USA", "urea", {"discharge", "both"}), "USMSY")
        self.assertIsNone(principal(self.food, "USA", "fert", {"discharge", "both"}))
        self.assertEqual(principal(self.food, "CAN", "potash", {"load", "both"}), "CAVAN")
        self.assertEqual(principal(self.food, "AUS", "sugar", {"load", "both"}), "AUTSV")
        # Loading side: Brazil no longer has a single port, and Argentina loads at the up-river hub.
        self.assertEqual(principal(self.food, "USA", "grain", {"load", "both"}), "USMSY")
        self.assertEqual(principal(self.food, "ARG", "grain", {"load", "both"}), "ARUPR")
        self.assertEqual(principal(self.food, "MYS", "vegoil", {"load", "both"}), "MYPGU")

    def test_g01_brazil_has_several_load_ports(self):
        ports_used = {r[0] for r in self.food.G["BRA"] if r[3] in ("load", "both")}
        self.assertGreaterEqual(len(ports_used), 3, ports_used)
        self.assertIn("BRSSZ", ports_used)

    def test_g01_two_coast_countries_carry_both_coasts(self):
        zones = lambda iso: {r[1] for r in self.food.G[iso]}  # noqa: E731
        self.assertTrue({"canada-west", "canada-east"} <= zones("CAN"))
        self.assertTrue({"w-australia", "e-australia"} <= zones("AUS"))
        self.assertTrue({"black-sea", "baltic"} <= zones("RUS"))

    # ------------------------------------------------------------------ coverage of the largest traders
    def test_coverage_of_the_largest_traders(self):
        """Every one of the 40 largest importers and exporters is covered, or listed in UNSOURCED with its candidates."""
        import pandas as pd
        df = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        d = df[(df["year"] == df["year"].max()) & df["group"].isin(FOOD_GROUPS + ["steel", "copper-refined", "aluminium",
                                                                                 "coffee", "cocoa", "cotton"])]
        tot = d.groupby("d")["t"].sum().add(d.groupby("o")["t"].sum(), fill_value=0)
        top = [c for c in tot.sort_values(ascending=False).index if c in self.a2][:40]
        self.assertEqual(len(top), 40)
        missing = [c for c in top if c not in self.food.G and c not in self.food.UNSOURCED]
        self.assertEqual(missing, [], "countries with neither rows nor an UNSOURCED entry")
        for iso, why in self.food.UNSOURCED.items():  # a country with rows is listed for the families it still lacks
            self.assertIn(iso, self.a2, iso)
            self.assertTrue(why and why.strip(), iso)
        self.assertGreaterEqual(len(self.food.G), 30, "number of countries with sourced rows")

    # ------------------------------------------------------------------ G11 and G01 against the loader of package E4b
    @unittest.skipUnless(hasattr(ports, "assign"), "the loader of package E4b (ports.assign) has not landed")
    def test_g11_gateway_never_returns_an_energy_terminal_for_food(self):
        """For every country that has rows, gateway() answers with a port of the family, else the country's
        general-cargo port, else its legacy port (never an energy terminal), else the nearest seaport."""
        groups = FOOD_GROUPS + ["steel", "copper-refined", "aluminium", "coffee", "cocoa", "cotton"]
        for iso in self.food.G:
            for g in groups:
                for role in ("load", "discharge", None):
                    code = ports.gateway(iso, g, role)
                    self.assertNotIn(code, ENERGY_TERMINALS, f"{iso} {g}")
                    if code is None:
                        continue
                    fams = set(ports._fams(g))
                    family = {r.code for r in ports.G.get(iso, ()) if r.families & fams}
                    box = {r.code for r in ports.G.get(iso, ()) if "box" in r.families}
                    own = ports.LEGACY_P.get(iso, {}).get(ports.segment(g)) if g not in ports.OWN_FAMILY else None
                    if family:
                        self.assertIn(code, family, f"{iso} {g}: {code} is not a port of the family")
                    elif box:
                        self.assertIn(code, box | {own}, f"{iso} {g}: {code} is not the general-cargo port")

    @unittest.skipUnless(hasattr(ports, "assign"), "the loader of package E4b (ports.assign) has not landed")
    def test_g11_countries_without_rows_keep_the_legacy_port(self):
        """Not committed is not hidden: the countries of UNSOURCED still answer from the legacy table, except where
        it gives an oil, gas or ore terminal (Arzew, Basrah Oil Terminal): then the nearest seaport answers."""
        for iso in self.food.UNSOURCED:
            if iso in ports.G:
                continue
            legacy = ports._legacy(iso, "wheat")
            code = ports.gateway(iso, "wheat")
            if legacy in ports.TERMINALS:
                self.assertNotEqual(code, legacy, iso)
                self.assertEqual(ports.basis_of(iso, "wheat", None, code), ports.BASIS_NEAREST, iso)
            else:
                self.assertEqual(code, legacy, iso)

    @unittest.skipUnless(hasattr(ports, "assign"), "the loader of package E4b (ports.assign) has not landed")
    def test_g11_saudi_wheat_is_not_at_ras_tanura(self):
        self.assertNotEqual(ports.gateway("SAU", "wheat"), "SARTA")
        self.assertEqual(ports.gateway("SAU", "wheat"), "SAJED")
        self.assertEqual(ports.basis_of("SAU", "wheat", "discharge", "SAJED"), ports.BASIS_GENERAL)

    # ------------------------------------------------------------------ package FE4c
    def test_fe4c_bosnian_grain_and_jordanian_phosphate(self):
        """L2: the Ploce page names a grain terminal for cereals and oilseeds; GE4.6: the Aqaba page names phosphate
        carried to the port (the railway is history)."""
        self.assertEqual(principal(self.food, "BIH", "grain", {"discharge", "both"}), "HRPLE")
        row = [r for r in self.food.G["BIH"] if "grain" in r[2]][0]
        self.assertTrue(row[5].endswith("Port_of_Plo%C4%8De"))
        self.assertIn("cereals and oilseeds", row[6])
        jo = [r for r in self.food.G["JOR"] if "phosphate-rock" in r[2]][0]
        self.assertEqual((jo[0], jo[3], jo[5]), ("JOAQB", "load", W_AQABA))
        self.assertIn("railway which transported phosphate", jo[6])
        self.assertIn("history", jo[6])

    # ------------------------------------------------------------------ sourcing pass FE4b
    def test_fe4b_rows(self):
        """The general-cargo rows and the grain, fertiliser and phosphate rows added on 23 November 2026."""
        pins = [("JPN", "box", "JPYOK"), ("TWN", "box", "TWKHH"), ("VNM", "box", "VNCMT"), ("THA", "box", "THLCH"),
                ("PHL", "box", "PHMNL"), ("PHL", "grain", "PHSFS"), ("PHL", "fert", "PHSFS"), ("SGP", "box", "SGSIN"),
                ("HKG", "box", "HKHKG"), ("ARE", "box", "AEJEA"), ("OMN", "grain", "OMSOH"), ("OMN", "box", "OMSOH"),
                ("JOR", "phosphate-rock", "JOAQB"), ("NLD", "box", "NLRTM"), ("SWE", "box", "SEGOT"), ("FRA", "box", "FRFOS")]
        for iso, fam, code in pins:
            self.assertEqual(principal(self.food, iso, fam, {"discharge", "both", "load"}), code, f"{iso} {fam}")
        # a family that no page names stays off the rows
        for iso, fam in (("PHL", "vegoil"), ("OMN", "fert"), ("JOR", "fert"), ("JOR", "potash"), ("NLD", "grain")):
            self.assertIsNone(principal(self.food, iso, fam, {"discharge", "both", "load"}), f"{iso} {fam}")
        # Jordan: phosphate rock is on the row, DAP and potash keep the legacy port and say so
        self.assertEqual(ports.basis_of("JOR", "phosphate-rock", "load", "JOAQB"), ports.BASIS_PAGE)
        self.assertEqual(ports.basis_of("JOR", "potash", "load", "JOAQB"), ports.BASIS_LEGACY)
        self.assertEqual(ports.basis_of("JOR", "dap", "load", "JOAQB"), ports.BASIS_LEGACY)


if __name__ == "__main__":
    unittest.main()
