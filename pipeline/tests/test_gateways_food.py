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

# Zones of section 2.4 of the plan (gateways/coasts.py of package E4b holds the same list).
ZONES = {
    "us-gulf", "us-atlantic", "us-pnw", "us-west", "canada-east", "canada-west", "mexico-gulf", "mexico-pacific",
    "cam-caribbean", "cam-pacific", "caribbean", "ecsa", "wcsa", "nw-europe", "baltic", "med", "black-sea", "meg",
    "red-sea", "wc-india", "ec-india", "sea", "s-china", "n-china", "japan-korea", "w-australia", "e-australia",
    "waf", "s-africa", "e-africa",
}
FAMILIES = {"grain", "vegoil", "fert", "box"}
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
            self.assertTrue(fam and set(fam) <= FAMILIES, where)
            self.assertIn(role, ROLES, where)
            self.assertTrue(note and note.strip(), f"{where}: a row carries a note with what the page says")

    def test_g10_every_row_has_a_source_that_exists(self):
        for iso, i, r in rows_of(self.food):
            code, zone, fam, role, src, url, note = r
            where = f"{iso}[{i}] {code}"
            self.assertIn(src, self.sources, where)
            self.assertTrue(url and url.startswith("https://"), f"{where}: the page read")
            if src == "wikipedia":
                self.assertTrue(url.startswith("https://en.wikipedia.org/wiki/"), where)

    def test_g10_codes_resolve_and_belong_to_their_country(self):
        extra = self.food.MANUAL_EXTRA
        for iso, i, r in rows_of(self.food):
            code = r[0]
            where = f"{iso}[{i}] {code}"
            known = code in ports._sr or code in ports.MANUAL or code in extra
            self.assertTrue(known, f"{where}: not in searoute, ports.MANUAL or MANUAL_EXTRA")
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
        # The corn "through Hormuz" estimate of the audit came from Saudi grain sent to Ras Tanura.
        for fam in ("grain", "vegoil", "fert", "box"):
            self.assertEqual(principal(self.food, "SAU", fam, {"discharge", "both"}), "SAJED", fam)

    def test_g01_pinned_principals(self):
        pins = [
            ("IDN", "grain", "IDTPP"), ("ESP", "grain", "ESTAR"), ("TUR", "grain", "TRMER"), ("MYS", "grain", "MYPKG"),
            ("DEU", "grain", "DEHAM"), ("NGA", "grain", "NGAPP"), ("ITA", "grain", "ITRAN"), ("AUS", "fert", "AUKWI"),
            ("EGY", "grain", "EGALY"), ("PER", "grain", "PECLL"), ("MEX", "fert", "MXZLO"),
        ]
        for iso, fam, code in pins:
            self.assertEqual(principal(self.food, iso, fam, {"discharge", "both"}), code, f"{iso} {fam}")
        self.assertEqual(principal(self.food, "USA", "fert", {"discharge", "both"}), "USMSY")
        # A lookup without a role takes the first row: it must be the dominant direction (imports for US fertiliser,
        # exports for Canadian potash).
        self.assertEqual(principal(self.food, "USA", "fert", {"load", "discharge", "both"}), "USMSY")
        self.assertEqual(principal(self.food, "CAN", "fert", {"load", "discharge", "both"}), "CAVAN")
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
        for iso, why in self.food.UNSOURCED.items():
            self.assertIn(iso, self.a2, iso)
            self.assertTrue(why and why.strip(), iso)
            self.assertNotIn(iso, self.food.G, f"{iso} is in both G and UNSOURCED")
        self.assertGreaterEqual(len(self.food.G), 30, "number of countries with sourced rows")

    # ------------------------------------------------------------------ G11 and G01 against the loader of package E4b
    @unittest.skipUnless(hasattr(ports, "assign"), "the loader of package E4b (ports.assign) has not landed")
    def test_g11_gateway_never_returns_an_energy_terminal_for_food(self):
        """For every country that has rows, gateway() answers with a port of the family (or its own legacy entry)."""
        groups = FOOD_GROUPS + ["steel", "copper-refined", "aluminium", "coffee", "cocoa", "cotton"]
        for iso in self.food.G:
            for g in groups:
                code = ports.gateway(iso, g)
                self.assertNotIn(code, ENERGY_TERMINALS, f"{iso} {g}")
                if code is None:
                    continue
                seg = ports.segment(g)
                allowed = {r.code for r in ports.G.get(iso, ()) if g in r.families or seg in r.families}
                allowed.add(ports._legacy_strict(iso, g))
                self.assertIn(code, allowed, f"{iso} {g}: {code} is not a port of the family")

    @unittest.skipUnless(hasattr(ports, "assign"), "the loader of package E4b (ports.assign) has not landed")
    def test_g11_countries_without_rows_keep_the_legacy_port(self):
        """Not committed is not hidden: the countries of UNSOURCED still answer from the legacy table."""
        for iso in self.food.UNSOURCED:
            if iso in ports.G:
                continue
            self.assertEqual(ports.gateway(iso, "wheat"), ports._legacy(iso, "wheat"), iso)

    @unittest.skipUnless(hasattr(ports, "assign"), "the loader of package E4b (ports.assign) has not landed")
    def test_g11_saudi_wheat_is_not_at_ras_tanura(self):
        self.assertNotEqual(ports.gateway("SAU", "wheat"), "SARTA")
        self.assertEqual(ports.gateway("SAU", "wheat"), "SAJED")


if __name__ == "__main__":
    unittest.main()
