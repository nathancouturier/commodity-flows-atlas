"""pipeline/common/constants.py: every physical or conventional constant of the builders has its page and its date, and no builder types one.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_constants.py"
"""
import calendar
import io
import json
import os
import re
import sys
import tokenize
import unittest
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

from common import constants as CN  # noqa: E402

INTL = os.path.join(ROOT, "raw", "eia", "INTL.txt")


def builders():
    """Every Python file of pipeline/ that is not a test and not the constants module."""
    for base, dirs, files in os.walk(os.path.join(ROOT, "pipeline")):
        dirs[:] = [d for d in dirs if d not in ("tests", "__pycache__", "cache")]
        for f in files:
            p = os.path.join(base, f)
            if f.endswith(".py") and p != os.path.join(ROOT, "pipeline", "common", "constants.py"):
                yield p


def numbers(path):
    """[(line, text)] of the numeric literals of a file's code (not its comments or strings)."""
    with open(path, encoding="utf-8") as f:
        src = f.read()
    return [(t.start[0], t.string) for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.NUMBER]


class Entries(unittest.TestCase):
    def test_every_entry_has_a_page_a_date_and_a_quote(self):
        entries = {**CN.CONSTANTS, **CN.EIA_RATIOS}
        self.assertGreaterEqual(len(entries), 20)
        for k, e in entries.items():
            self.assertRegex(e["url"], r"^https://", k)
            self.assertTrue(re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["read"]), k)
            self.assertLessEqual(date.fromisoformat(e["read"]), date.today(), k)
            self.assertIsNotNone(e["value"], k)
            self.assertTrue(e.get("quote") or e.get("what"), k)
            for u in e.get("also", []):
                self.assertRegex(u, r"^https://", k)
        self.assertRegex(CN.ATOMIC_WEIGHT_PAGE["url"], r"^https://")

    def test_the_constants_the_brief_names_are_there(self):
        for k in ("US_GALLONS_PER_BARREL", "KG_PER_LB", "LB_PER_SHORT_TON", "GRAINS_PER_TROY_OZ", "BCF_PER_MT_LNG"):
            self.assertIn(k, CN.CONSTANTS)
        for el in ("U", "O", "Li", "C", "K", "Cl", "N", "H"):
            self.assertIn("ATOMIC_WEIGHT_" + el.upper(), CN.CONSTANTS)
        self.assertEqual(sorted(CN.EIA_RATIOS), ["BARRELS_PER_TONNE_CRUDE", "BARRELS_PER_TONNE_LPG"])

    def test_the_derived_values_are_the_ones_the_builders_used_before(self):
        self.assertEqual(CN.TONNES_PER_SHORT_TON, 0.90718474)
        self.assertEqual(CN.GRAMS_PER_TROY_OZ, 31.1034768)
        self.assertEqual(CN.MT_PER_1000_COTTON_BALES, 0.00021772434)
        self.assertEqual(CN.MT_PER_1000_COFFEE_BAGS, 0.00006)
        self.assertEqual(CN.KT_PER_1000_COFFEE_BAGS, 0.06)
        self.assertAlmostEqual(CN.KT_PER_1000_COTTON_BALES, 480 * 0.45359237 / 1000)
        self.assertEqual(CN.ATOMIC_WEIGHT["U"], 238.03)  # CIAAW abridged 2024
        self.assertEqual(CN.ATOMIC_WEIGHT["K"], 39.098)
        self.assertEqual(CN.ATOMIC_WEIGHT["Cl"], 35.45)


@unittest.skipUnless(os.path.exists(INTL), "raw/eia/INTL.txt is not on this machine")
class EiaRatios(unittest.TestCase):
    """The two ratios are read in EIA's own data: the value of the module is the one the file gives."""

    @staticmethod
    def read(prefix):
        pat = re.compile(rf'^\{{"series_id":"INTL\.{prefix}-USA-(TBPD|MT)\.A"')
        out = {}
        with open(INTL, encoding="utf-8") as f:
            for line in f:
                m = pat.match(line)
                if m:
                    out[m.group(1)] = {int(y): v for y, v in json.loads(line)["data"] if isinstance(v, (int, float))}
        return out

    def ratio(self, prefix, years):
        s = self.read(prefix)
        r = sorted(s["TBPD"][y] * (366 if calendar.isleap(y) else 365) / s["MT"][y] for y in years if y in s["TBPD"] and s["MT"].get(y))
        return r[len(r) // 2]

    def test_crude_oil_7_33(self):
        self.assertAlmostEqual(self.ratio("57-1", range(1980, 2000)), CN.EIA_RATIOS["BARRELS_PER_TONNE_CRUDE"]["value"], places=2)

    def test_lpg_11_6(self):
        self.assertAlmostEqual(self.ratio("67-2", range(1980, 2020)), CN.EIA_RATIOS["BARRELS_PER_TONNE_LPG"]["value"], places=2)

    def test_the_builders_read_the_same_ratio(self):
        sys.path.insert(0, os.path.join(ROOT, "pipeline", "trade"))
        import checks as K

        eia = K.eia_series([("57-1", "TBPD"), ("57-1", "MT")])
        self.assertAlmostEqual(K.barrels_per_tonne(eia), CN.EIA_RATIOS["BARRELS_PER_TONNE_CRUDE"]["value"], places=2)


class NoBuilderTypesAConstant(unittest.TestCase):
    def banned(self):
        v = [CN.KG_PER_LB, CN.GRAMS_PER_TROY_OZ, CN.TONNES_PER_SHORT_TON, CN.BCF_PER_MT_LNG, CN.FOOT_M, CN.KM_PER_NAUTICAL_MILE, CN.EARTH_RADIUS_KM,
             CN.GRAIN_G, CN.MT_PER_1000_COTTON_BALES, CN.MT_PER_1000_COFFEE_BAGS, *CN.ATOMIC_WEIGHT.values(),
             39.0983, 35.453,  # the atomic weights of potassium and chlorine as the builders typed them before the page was read
             CN.EIA_RATIOS["BARRELS_PER_TONNE_CRUDE"]["value"], CN.EIA_RATIOS["BARRELS_PER_TONNE_LPG"]["value"]]
        return {float(x) for x in v}

    def test_no_numeric_literal_of_a_constant_in_a_builder(self):
        banned, found = self.banned(), []
        for p in builders():
            for line, text in numbers(p):
                try:
                    x = float(text.replace("_", ""))
                except ValueError:
                    continue
                if x in banned:
                    found.append(f"{os.path.relpath(p, ROOT)}:{line}: {text}")
        self.assertEqual(found, [])

    def test_the_42_gallons_are_not_typed_next_to_a_barrel(self):
        found = []
        for p in builders():
            with open(p, encoding="utf-8") as f:
                lines = f.read().splitlines()
            for line, text in numbers(p):
                if text in ("42", "42.0") and re.search(r"gallon|barrel|bbl", lines[line - 1], re.I):
                    found.append(f"{os.path.relpath(p, ROOT)}:{line}")
        self.assertEqual(found, [])

    def test_the_builders_import_the_module(self):
        for rel in ("commodities/build_commodities.py", "trade/checks.py", "trade/caveats.py", "freight/build_lanes.py", "freight/ports.py"):
            with open(os.path.join(ROOT, "pipeline", rel), encoding="utf-8") as f:
                self.assertIn("from common import constants as CN", f.read(), rel)

    def test_the_figures_that_reproduce_from_the_constants_are_unchanged(self):
        sys.path.insert(0, os.path.join(ROOT, "pipeline", "commodities"))
        import build_commodities as B

        self.assertEqual(B.U3O8_PER_U, 1.1792)  # 1.1792 t of U3O8 per tonne of uranium, printed on the uranium page
        self.assertEqual(B.LB_U3O8_PER_TU, 2600)
        self.assertEqual(B.LCE_PER_LI, 5.323)
        self.assertEqual(B.BCM_PER_MT_LNG, 1.36)
        self.assertEqual(B.psd_units()["Cotton"][1] if hasattr(B, "psd_units") else B.Psd.UNITS["Cotton"][1], 0.00021772434)


if __name__ == "__main__":
    unittest.main()
