"""Fixes of the release review GR1 (package FR1) on the built data: the spodumene group (sourced ports, source id
"atlas", history from 2021), the route and chokepoint notes, the PortWatch note from 85% and the annual job limits.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("freight", "trade", "annual"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))

DATA = os.path.join(ROOT, "data", "freight")


def load(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return json.load(f)


class Spodumene(unittest.TestCase):
    def test_ports_rest_on_pages(self):
        import ports as P
        loads = P.candidates("AUS", "spodumene", "load")
        self.assertEqual([c[0] for c in loads], ["AUBUY", "AUPHE", "AUEPR"])  # Bunbury, Port Hedland, Esperance
        self.assertTrue(all(c[2] == P.BASIS_PAGE for c in loads))
        self.assertEqual(P.candidates("BRA", "spodumene", "load")[0][:1], ("BRVIX",))
        self.assertIn("ZWE", __import__("gateways.coasts", fromlist=["UNSOURCED"]).UNSOURCED)
        # the spodumene rows do not change the iron-ore gateway of Port Hedland
        self.assertEqual([c[0] for c in P.candidates("AUS", "iron-ore", "load")], ["AUPHE"])

    def test_lane_file(self):
        f = load(DATA, "lanes", "spodumene.json")
        self.assertEqual(f["s"], "atlas")
        self.assertTrue(f["n"].startswith("Atlas estimate"))
        i0 = f["years"].index(2021)
        self.assertTrue(all(v is None for v in f["seaborne"][:i0] + f["world"][:i0]))
        self.assertTrue(all(v is not None for v in f["seaborne"][i0:]))
        lane = next(x for x in f["lanes"] if x["id"] == "spodumene:AUS-CHN")
        self.assertEqual(lane["load"], ["AUBUY"])
        self.assertEqual(f["ports"]["AUBUY"]["basis"], "page names the cargo")
        self.assertEqual(lane["flow"]["s"], "atlas")
        self.assertTrue(lane["flow"]["n"].startswith("Atlas estimate: spodumene concentrate has no customs code"))
        self.assertEqual({o["load"] for o in lane["opts"]}, {"AUPHE", "AUEPR"})
        for x in f["lanes"]:
            self.assertTrue(all(v is None for v in x["hist"][:i0]), x["id"])
            self.assertEqual({x["histFlags"][str(y)] for y in f["years"][:i0]}, {"nodata"}, x["id"])
            self.assertTrue(x["histNote"].startswith("Not read as spodumene before 2021"), x["id"])
            self.assertNotIn("No customs record", x["histNote"])

    def test_pairs_file(self):
        p = load(DATA, "pairs", "spodumene.json")
        self.assertEqual(p["s"], "atlas")
        self.assertTrue(p["n"].startswith("Atlas estimate"))
        self.assertNotIn("AUTHE", [x[0] for x in p["ports"]])

    def test_route_history_starts_in_2021(self):
        r = next(x for x in load(DATA, "routes.json") if x["id"] == "australia-china-spodumene")
        self.assertEqual(r["history"][0]["y"], 2021)
        self.assertEqual(r["historySrc"], "atlas")
        self.assertTrue(r["historyNote"].startswith("Not read as spodumene before 2021"))
        self.assertNotIn("Geraldton", r["from"]["ports"])


class Notes(unittest.TestCase):
    WORK = re.compile(r"to be checked|not confirmed|not independently|not verified|re-verified|in this research|TODO|via search",
                      re.I)

    def test_route_notes_are_statements(self):
        for r in load(DATA, "routes.json"):
            self.assertIsNone(self.WORK.search(r.get("notes") or ""), r["id"])

    def test_bab_el_mandeb_note_states_no_cause(self):
        c = next(x for x in load(DATA, "chokepoints.json") if x["id"] == "bab-el-mandeb")
        self.assertNotIn("because", c["shares"][0]["f"]["n"])

    def test_portwatch_note_from_85_percent(self):
        import build_freight as BF
        self.assertEqual(BF.PW_NEAR, 0.85)
        c = next(x for x in load(DATA, "chokepoints.json") if x["id"] == "panama")
        lpg = next(e for e in c["estimates"] if e["p"] == "lpg")
        # since FNCG (GV6D.1) the note of the ship type is written once on the passage record, not in each estimate
        self.assertRegex(c["typeNotes"]["tanker"]["line"], r"is 9\d% of IMF PortWatch's \d+ Mt for all tanker ships in 2024")
        self.assertNotIn("PortWatch's", lpg["f"]["n"])
        # the K9 record keeps its level: under the volume of the year, a report only
        k9 = [r for r in load(ROOT, "pipeline", "cache", "trade_checks.json")["findings"]
              if r["check"] == "K9" and r.get("kind") == "passage" and r["chokepoint"] == "panama" and r["type"] == "tanker"]
        self.assertEqual([r["level"] for r in k9], ["qa"])


class AnnualJob(unittest.TestCase):
    def test_step_limits_fit_the_workflow_step(self):
        import update_annual as UA
        with open(os.path.join(ROOT, ".github", "workflows", "update-annual.yml"), encoding="utf-8") as f:
            wf = f.read()
        step = int(re.search(r"timeout-minutes: (\d+)\n\s+run: python pipeline/annual/update_annual.py", wf).group(1))
        self.assertLessEqual(sum(UA.STEP_MIN.values()), step - 20)  # room left for the downloads
        self.assertIn("pipeline/commodities/QA.md", re.search(r'paths: "([^"]+)"', wf).group(1).split())


if __name__ == "__main__":
    unittest.main()
