"""Tests of the second correction package after the review of the three commodity packages (FNCB): the figures and estimates of the new groups.

B1  the "up to" figure of a chokepoint estimate: PortWatch's volume less the other groups while the atlas's "at least" tonnage of the vessel
    type is at most PW_NEAR of it, PortWatch's whole volume of the type above that, no cap under an explaining alert (FNCD, D1); the
    estimates of the released site are all still published
B2  the value rules of clean.py keep the reported tonnage of a sowing-seed flow, and the estimates of the new groups are listed one by one
B3  coke is one product priced by the tonne: the Mozambique to India row of 2016 is repaired as a flagged Atlas estimate
B4  ammonium nitrate with limestone (HS 310240) and the two-nutrient compounds (310551, 310559, 310560) are loaded
B5  the extract keeps the totals by group and year before the small-flow threshold, and a page note says the gap
B6  the "mixed" tonnage of a lanes file keeps three significant digits
B7  the three size budgets are the measured size plus a fifth
B8  the tables with an out-of-line year are named

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
The tests of the data files read the files as the builders last wrote them.
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities"):
    sys.path.insert(0, os.path.join(ROOT, "pipeline", sub))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

DATA = os.path.join(ROOT, "data")


def load(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return json.load(f)


# B1: the (passage, group) estimates of the released site (commit 65b007f, data/freight/chokepoints.json: 599 entries)
RELEASED_ESTIMATES = {
    "hormuz": """
    alumina aluminium coal copper-refined corn crude-oil dap iron-ore lead-metal lng lpg palm-oil rapeseed
    refined-products rice soybeans soymeal steel sugar urea wheat zinc-metal""",
    "malacca": """
    alumina aluminium bauxite coal cobalt cocoa coffee copper-ore copper-refined corn cotton crude-oil dap
    iron-ore lead-metal lead-ore lithium lng lpg manganese nickel-fe nickel-int nickel-ore palm-oil
    phosphate-rock potash rapeseed rare-earths refined-products rice soybeans soymeal soyoil spodumene steel
    sugar tin-metal tin-ore urea wheat zinc-metal zinc-ore""",
    "singapore": """
    alumina aluminium bauxite coal cobalt cocoa coffee copper-ore copper-refined corn cotton crude-oil dap
    iron-ore lead-metal lead-ore lithium lng lpg manganese nickel-fe nickel-int nickel-ore palm-oil
    phosphate-rock potash rapeseed rare-earths refined-products rice soybeans soymeal soyoil spodumene steel
    sugar tin-metal tin-ore urea wheat zinc-metal zinc-ore""",
    "sunda": """
    alumina aluminium bauxite coal cobalt cocoa coffee copper-ore copper-refined corn cotton crude-oil iron-ore
    lead-metal lead-ore lithium lng lpg manganese nickel-int nickel-ore palm-oil phosphate-rock potash
    rare-earths refined-products rice soybeans soymeal soyoil spodumene steel sugar tin-metal tin-ore urea wheat
    zinc-metal zinc-ore""",
    "lombok": """
    alumina aluminium bauxite coal cocoa coffee copper-refined corn cotton crude-oil iron-ore lead-metal
    lead-ore lithium lng lpg manganese nickel-int potash rapeseed rare-earths refined-products soybeans soymeal
    soyoil spodumene steel sugar tin-metal tin-ore urea wheat zinc-metal""",
    "suez": """
    alumina aluminium bauxite coal cobalt cocoa coffee copper-ore copper-refined corn cotton crude-oil dap
    iron-ore lead-metal lead-ore lng lpg nickel-int palm-oil phosphate-rock potash rapeseed rare-earths
    refined-products rice soymeal soyoil steel sugar tin-metal urea wheat zinc-metal zinc-ore""",
    "bab-el-mandeb": """
    alumina aluminium bauxite coal cobalt cocoa coffee copper-ore copper-refined corn cotton crude-oil dap
    iron-ore lead-metal lead-ore lng lpg nickel-int palm-oil phosphate-rock potash rapeseed rare-earths
    refined-products rice soyoil steel sugar tin-metal urea wheat zinc-metal zinc-ore""",
    "panama": """
    alumina aluminium coal cocoa coffee copper-ore copper-refined corn cotton crude-oil iron-ore lead-metal
    lead-ore lithium lng lpg phosphate-rock potash rapeseed rare-earths refined-products rice soybeans soymeal
    steel tin-metal urea wheat zinc-metal zinc-ore""",
    "bosphorus": """
    alumina aluminium bauxite coal coffee copper-ore copper-refined corn crude-oil dap iron-ore lead-ore
    nickel-int phosphate-rock potash rapeseed refined-products soybeans soyoil steel urea wheat zinc-ore""",
    "danish-straits": """
    aluminium coal copper-ore copper-refined corn crude-oil dap iron-ore lead-metal lead-ore lng lpg nickel-int
    phosphate-rock potash rapeseed rare-earths refined-products soymeal steel tin-metal urea wheat zinc-metal
    zinc-ore""",
    "gibraltar": """
    alumina aluminium bauxite coal cobalt cocoa coffee copper-ore copper-refined corn cotton crude-oil dap
    iron-ore lead-metal lead-ore lithium lng lpg nickel-int palm-oil phosphate-rock potash rapeseed rare-earths
    refined-products rice soybeans soymeal soyoil steel sugar tin-metal urea wheat zinc-metal zinc-ore""",
    "dover": """
    alumina aluminium bauxite coal cocoa coffee copper-ore copper-refined corn crude-oil dap iron-ore lead-metal
    lead-ore lithium lng lpg manganese nickel-int palm-oil phosphate-rock potash rapeseed rare-earths
    refined-products rice soybeans soymeal soyoil steel sugar tin-metal urea wheat zinc-metal zinc-ore""",
    "cape-good-hope": """
    aluminium bauxite coal cocoa coffee copper-ore corn cotton crude-oil iron-ore lead-ore lithium lng lpg
    manganese nickel-ore palm-oil phosphate-rock refined-products rice soybeans soymeal soyoil spodumene steel
    sugar tin-ore urea wheat zinc-metal""",
    "cape-horn": """
    coal copper-refined corn crude-oil phosphate-rock soymeal soyoil""",
    "taiwan-strait": """
    aluminium bauxite coal cobalt coffee copper-ore copper-refined corn cotton crude-oil dap iron-ore lead-metal
    lead-ore lithium lng lpg manganese nickel-int nickel-ore palm-oil phosphate-rock potash rapeseed rare-earths
    refined-products rice soybeans soymeal soyoil spodumene steel sugar tin-metal tin-ore urea wheat zinc-metal
    zinc-ore""",
    "korea-strait": """
    aluminium coal coffee copper-ore copper-refined corn cotton crude-oil dap iron-ore lead-metal lead-ore
    lithium lng lpg nickel-fe nickel-int nickel-ore phosphate-rock potash rapeseed rare-earths refined-products
    soybeans soymeal soyoil steel sugar tin-metal wheat zinc-metal zinc-ore""",
    "makassar": """
    aluminium bauxite coal coffee copper-refined corn cotton crude-oil dap iron-ore lead-metal lead-ore lithium
    lng lpg manganese potash rapeseed refined-products soybeans soymeal soyoil spodumene steel sugar tin-metal
    tin-ore wheat zinc-metal""",
    "luzon": """
    aluminium bauxite coal cobalt coffee copper-ore copper-refined corn cotton crude-oil dap iron-ore lead-metal
    lead-ore lithium lng lpg manganese nickel-int nickel-ore palm-oil phosphate-rock potash rapeseed rare-earths
    refined-products rice soybeans soymeal soyoil spodumene steel sugar tin-metal tin-ore urea wheat zinc-metal
    zinc-ore""",
    "ombai": """
    alumina coal cotton iron-ore lead-metal""",
    "torres": """
    alumina aluminium coal cocoa copper-ore cotton crude-oil iron-ore lead-metal lead-ore lng nickel-int
    rare-earths refined-products soybeans steel sugar tin-ore zinc-metal zinc-ore""",
}


class B1CapAgainstPortWatch(unittest.TestCase):
    def test_every_estimate_of_the_released_site_is_still_published(self):
        """GNC3.1: three estimates of the released site (Bosphorus DAP, urea, potash) had gone with no trace because the new dry-bulk groups
        took the atlas's "at least" tonnage above PortWatch's volume and the cap then emptied every "up to" figure."""
        want = {(cp, g) for cp, gs in RELEASED_ESTIMATES.items() for g in gs.split()}
        self.assertEqual(len(want), 599)
        have = {(c["id"], e["p"]) for c in load(DATA, "freight", "chokepoints.json") for e in c.get("estimates") or []}
        self.assertEqual(sorted(want - have), [])
        # the five that vanished or lost more than half of their "up to" figure
        chk = {c["id"]: {e["p"]: e for e in c.get("estimates") or []} for c in load(DATA, "freight", "chokepoints.json")}
        for g in ("dap", "urea", "potash"):
            self.assertIn(g, chk["bosphorus"])
        for g, low_max in (("potash", 8.0), ("urea", 7.0)):
            e = chk["gibraltar"][g]
            self.assertLess(e["mt"][0], low_max)
            self.assertGreater(e["mt"][1], 2 * e["mt"][0], (g, e["mt"]))  # "up to" is well above "at least", not equal to it

    def test_the_regime_of_every_passage_and_type_in_the_files(self):
        """In the files (FNCD, D1): at most PW_NEAR of PortWatch's volume the cap is by subtraction; above it no "up to" figure of the type
        exceeds PortWatch's whole volume of the type, and the note says so; where the atlas is above PortWatch's volume and an alert explains
        it, there is no cap and the note says that."""
        import build_freight as BF
        k9 = {(r["chokepoint"], r["type"]): r for r in load(ROOT, "pipeline", "cache", "trade_checks.json")["findings"]
              if r["check"] == "K9" and r.get("kind") == "passage"}
        alerts = load(DATA, "freight", "alerts.json")
        seen = {"sub": 0, "whole": 0, "none": 0}
        for c in load(DATA, "freight", "chokepoints.json"):
            if not c.get("portwatch") or c.get("portwatchLabel"):
                continue
            for e in c.get("estimates") or []:
                typ = BF.vessel_type(e["p"])
                r = k9.get((c["id"], typ))
                if not r or not r["reference"]:
                    continue
                regime = BF.cap_regime(r["value"], r["reference"], BF.alert_reason(alerts, c["id"], r["year"]))
                seen[regime] += 1
                where = (c["id"], e["p"], regime)
                self.assertNotIn("not capped at PortWatch's volume here", e["f"]["n"] if regime != "none" else "", where)
                if regime == "sub":
                    self.assertNotIn("capped at the whole of PortWatch's volume", e["f"]["n"], where)
                elif regime == "whole":
                    self.assertIn("capped at the whole of PortWatch's volume", e["f"]["n"], where)
                    self.assertNotIn("less the 'at least' tonnage", (e.get("hi") or {}).get("n", ""), where)
                    # a group cannot exceed the whole volume of its ship type (rounded as the file prints it), nor go under its own "at least"
                    self.assertLessEqual(e["mt"][1], max(e["mt"][0], r["reference"] + 0.0006 * r["reference"]), where)
                else:
                    self.assertIn("not capped at PortWatch's volume here", e["f"]["n"], where)
                    self.assertNotIn("capped at IMF", (e.get("hi") or {}).get("n", ""), where)
        self.assertGreater(seen["sub"], 10)
        self.assertGreater(seen["whole"], 50)
        self.assertGreater(seen["none"], 50)

    def test_the_twelve_passages_and_types_above_the_threshold(self):
        """The passages and vessel types above PW_NEAR of PortWatch's volume in the files, and the regime of each."""
        import build_freight as BF
        alerts = load(DATA, "freight", "alerts.json")
        chk = {c["id"]: c for c in load(DATA, "freight", "chokepoints.json")}
        got = {}
        for r in load(ROOT, "pipeline", "cache", "trade_checks.json")["findings"]:
            if r["check"] == "K9" and r.get("kind") == "passage" and r["reference"]:
                c = chk[r["chokepoint"]]
                if c.get("portwatch") and not c.get("portwatchLabel") and r["value"] > BF.PW_NEAR * r["reference"]:
                    got[(r["chokepoint"], r["type"])] = BF.cap_regime(r["value"], r["reference"], BF.alert_reason(alerts, r["chokepoint"], r["year"]))
        self.assertEqual(got, {("bab-el-mandeb", "dry"): "none", ("suez", "dry"): "none", ("bab-el-mandeb", "tanker"): "none",
                               ("suez", "tanker"): "none", ("bab-el-mandeb", "cargo"): "none", ("gibraltar", "dry"): "whole",
                               ("bosphorus", "dry"): "whole", ("torres", "tanker"): "whole", ("panama", "tanker"): "whole",
                               ("makassar", "dry"): "whole", ("hormuz", "tanker"): "whole", ("lombok", "dry"): "whole"})

    def test_the_four_released_estimates_that_exceeded_their_ship_type(self):
        """FNCB published Lombok and Makassar iron ore and Torres LNG and refined products above PortWatch's whole volume of the ship type."""
        chk = {c["id"]: {e["p"]: e for e in c.get("estimates") or []} for c in load(DATA, "freight", "chokepoints.json")}
        self.assertEqual(chk["lombok"]["iron-ore"]["mt"][1], 950.3)
        self.assertEqual(chk["makassar"]["iron-ore"]["mt"][1], 1084.7)
        self.assertEqual(chk["torres"]["lng"]["mt"][1], 13.5)
        self.assertEqual(chk["torres"]["refined-products"]["mt"][1], 13.5)
        self.assertEqual(chk["hormuz"]["crude-oil"]["mt"][1], 750.7)  # not touched by the whole-volume cap (it is under 915 Mt)
        self.assertEqual(chk["panama"]["crude-oil"]["mt"][1], 43.8)
        self.assertIn("capped at IMF PortWatch's estimate", chk["lombok"]["iron-ore"]["hi"]["n"])
        self.assertNotIn("other", chk["lombok"]["iron-ore"]["hi"]["n"].split("without the cap")[0])

    def test_the_tag_of_the_web_shows_exactly_where_a_figure_is_capped(self):
        """ChokepointView tags a figure whose `hi` note matches /capped/i: that must be the figures whose published "up to" is under the
        uncapped sum (and only those)."""
        import build_freight as BF
        pairs = BF.load_pairs()
        n = 0
        for c in load(DATA, "freight", "chokepoints.json"):
            if c["id"] not in BF.RT.GATES:
                continue
            for e in c.get("estimates") or []:
                rows = [r for r in pairs[e["p"]]["rows"] if r["m"] in (0, 1)]
                low = sum(r["t"] for r in rows if c["id"] in r["via"])
                alt = {}
                for r in rows:
                    if c["id"] in r["alt"]:
                        alt[r["o"]] = alt.get(r["o"], 0.0) + r["t"]
                high = low + sum(alt.values())
                digits = 1 if high >= 10 else 3
                cut = e["mt"][1] < round(high, digits) - 0.0006 * max(1.0, high)
                tagged = bool(re.search("capped", (e.get("hi") or {}).get("n", ""), re.I))
                self.assertEqual(tagged, cut, (c["id"], e["p"], e["mt"], round(high, 3)))
                n += cut
        self.assertGreater(n, 10)

    def _shares(self, pw_dry, alerts=None):
        """chokepoint_shares of two dry groups at the Bosphorus: wheat 40 Mt at least and 30 Mt that may cross, corn 50 Mt at least."""
        import build_freight as BF
        def row(o, d, t, via=(), alt=()):
            return {"m": 0, "t": t, "via": set(via), "alt": set(alt), "o": o, "d": d, "load": 0}
        pairs = {"wheat": {"seaborne": 200.0, "rows": [row("UKR", "EGY", 40.0, via=["bosphorus"]), row("RUS", "TUR", 30.0, alt=["bosphorus"])]},
                 "corn": {"seaborne": 200.0, "rows": [row("UKR", "ESP", 50.0, via=["bosphorus"])]}}
        chk = [{"id": "bosphorus", "name": "Turkish Straits", "portwatch": True}]
        year = {"dry": pw_dry, "tanker": 500.0, "cargo": 500.0}
        pw = {"bosphorus": {2024: year, 2023: dict(year, dry=200.0)}}  # the best year is far above the atlas's tonnage: no K9 flag
        BF.chokepoint_shares(chk, pairs, pw, {}, {}, 2024, alerts)
        return {e["p"]: e for e in chk[0]["estimates"]}, BF

    def test_rule_below_and_above_the_threshold(self):
        # 90 Mt at least in all: PW_NEAR x 100 = 85 Mt, so above the threshold at 100 Mt; at 110 Mt (93.5) the subtraction applies
        above, BF = self._shares(100.0)
        self.assertEqual(above["wheat"]["mt"], [40.0, 70.0])  # the whole volume (100 Mt) is above the 70 Mt: the cap does not bite
        self.assertNotIn("capped at", above["wheat"]["hi"]["n"])
        self.assertIn("capped at the whole of PortWatch's volume", above["wheat"]["f"]["n"])
        self.assertNotIn("not capped at PortWatch's volume here", above["wheat"]["f"]["n"])
        below, _ = self._shares(110.0)
        self.assertEqual(below["wheat"]["mt"], [40.0, 60.0])  # 110 less the 50 Mt of corn
        self.assertIn("capped at IMF PortWatch's estimate", below["wheat"]["hi"]["n"])
        self.assertIn("less the 'at least' tonnage of the atlas's other dry bulk groups", below["wheat"]["hi"]["n"])
        self.assertNotIn("capped at the whole", below["wheat"]["f"]["n"])
        # on the line: at exactly PW_NEAR the subtraction still applies (the rule is "at most")
        edge, _ = self._shares(90.0 / BF.PW_NEAR)
        self.assertLess(edge["wheat"]["mt"][1], 70.0)

    def test_the_whole_volume_cap_above_the_threshold(self):
        """Above PW_NEAR the cap is PortWatch's whole volume of the type, never below the group's own "at least"; the subtraction is not used
        and the note does not speak of the other groups."""
        whole, _ = self._shares(60.0)  # 90 Mt at least against 60 Mt: the atlas is above PortWatch and no alert explains it
        self.assertEqual(whole["wheat"]["mt"], [40.0, 60.0])  # not 60 less the 50 Mt of corn, which would be under the 40 Mt at least
        self.assertEqual(whole["corn"]["mt"], [50.0, 50.0])  # no "up to" above its "at least" to cap
        n = whole["wheat"]["hi"]["n"]
        self.assertIn("capped at IMF PortWatch's estimate of the cargo of all dry bulk ships through the passage in 2024", n)
        self.assertIn("which this cargo cannot exceed; without the cap, 70", n)
        self.assertNotIn("less the", n)
        self.assertNotIn("other dry bulk groups", n)
        self.assertIn("capped at the whole of PortWatch's volume of these ships", whole["wheat"]["f"]["n"])
        # a volume under the group's own "at least": the group keeps its "at least" and has no "up to"
        under, _ = self._shares(30.0)
        self.assertEqual(under["wheat"]["mt"], [40.0, 40.0])
        self.assertNotIn("hi", under["wheat"])

    def test_no_cap_where_an_alert_explains_a_tonnage_above_portwatch(self):
        alert = [{"chokepoints": ["bosphorus"], "since": "2023", "title": "A diversion", "text": "Ships sailed around. More.", "src": None}]
        shares, BF = self._shares(60.0, alerts=alert)
        self.assertEqual(shares["wheat"]["mt"], [40.0, 70.0])
        self.assertNotIn("capped at", shares["wheat"]["hi"]["n"])
        n = shares["wheat"]["f"]["n"]
        self.assertIn("not capped at PortWatch's volume here", n)
        self.assertIn("normal route", n)
        # the alert counts only when the atlas is above PortWatch's volume: between PW_NEAR and the volume the whole-volume cap applies
        near, _ = self._shares(100.0, alerts=alert)
        self.assertIn("capped at the whole of PortWatch's volume", near["wheat"]["f"]["n"])
        self.assertEqual(BF.cap_regime(90.0, 100.0, "an alert"), "whole")
        self.assertEqual(BF.cap_regime(110.0, 100.0, "an alert"), "none")
        self.assertEqual(BF.cap_regime(110.0, 100.0, None), "whole")
        self.assertEqual(BF.cap_regime(85.0, 100.0, None), "sub")
        self.assertIsNone(BF.cap_regime(85.0, None, None))

    def test_the_floor_uses_the_published_figure(self):
        """Wheat has no "at least" tonnage and 30 Mt that may cross; corn has 5.2 Mt at least. With 6 Mt of PortWatch for the type (corn is
        above 85% of it: the whole volume is the cap) wheat is capped at 6 Mt and is published; with 7 Mt (5.95) it is capped at 7 less 5.2;
        with 6 Mt and 5.05 Mt of corn the cap leaves 0.95 Mt, under the floor of 1 Mt and 2%: no entry; with 0.9 Mt of PortWatch for the type
        and no other cargo the cap is 0.9 Mt, under the floor too."""
        import build_freight as BF
        def row(o, d, t, via=(), alt=()):
            return {"m": 0, "t": t, "via": set(via), "alt": set(alt), "o": o, "d": d, "load": 0}
        def run(corn, pw_dry):
            pairs = {"wheat": {"seaborne": 100.0, "rows": [row("RUS", "TUR", 30.0, alt=["bosphorus"])]},
                     "corn": {"seaborne": 200.0, "rows": [row("UKR", "ESP", corn, via=["bosphorus"])]}}
            chk = [{"id": "bosphorus", "name": "Turkish Straits", "portwatch": True}]
            BF.chokepoint_shares(chk, pairs, {"bosphorus": {2024: {"dry": pw_dry, "tanker": 500.0, "cargo": 500.0}}}, {}, {}, 2024, None)
            return {e["p"]: e for e in chk[0].get("estimates", [])}
        self.assertEqual(run(5.2, 6.0)["wheat"]["mt"], [0.0, 6.0])
        self.assertEqual(run(5.2, 5.5)["wheat"]["mt"], [0.0, 5.5])
        self.assertEqual(run(5.2, 7.0)["wheat"]["mt"], [0.0, 1.8])
        self.assertNotIn("wheat", run(5.05, 6.0))
        self.assertNotIn("wheat", run(0.0, 0.9))
        self.assertIn("corn", run(5.05, 6.0))

    def test_note_of_a_type_above_portwatch(self):
        """No alert explains it: the note says the assumed ports, routes or ship types probably overstate it, not "the tonnage of the normal
        route". An alert on the passage keeps the existing wording."""
        no_alert, _ = self._shares(80.0)
        n = no_alert["wheat"]["f"]["n"]
        self.assertIn("probably overstate it", n)
        self.assertIn("ports, routes or ship types", n)
        self.assertNotIn("tonnage of the normal route", n)
        alert = [{"chokepoints": ["bosphorus"], "since": "2023", "title": "A diversion", "text": "Ships sailed around. More.", "src": None}]
        with_alert, _ = self._shares(80.0, alerts=alert)
        n = with_alert["wheat"]["f"]["n"]
        self.assertIn("tonnage of the normal route, not the 2024 traffic", n)
        self.assertIn("A diversion", n)

    def test_the_published_notes_of_the_passages_above_portwatch(self):
        """Bosphorus and Gibraltar (dry bulk, above PortWatch's volume, no alert) say probably overstate; Suez and Bab el-Mandeb keep the
        Red Sea wording."""
        chk = {c["id"]: c for c in load(DATA, "freight", "chokepoints.json")}
        for cp in ("bosphorus", "gibraltar"):
            n = next(e for e in chk[cp]["estimates"] if e["p"] == "wheat")["f"]["n"]
            self.assertIn("no alert explains it", n, cp)
            self.assertNotIn("tonnage of the normal route", n, cp)
        n = next(e for e in chk["suez"]["estimates"] if e["p"] == "wheat")["f"]["n"]
        self.assertIn("tonnage of the normal route", n)
        self.assertIn("Red Sea diversions", n)

    def test_methodology_counts_the_entries_of_the_file(self):
        """The count of estimates in METHODOLOGY is the count of the file, and the rule of the cap is written there."""
        n = sum(len(c.get("estimates") or []) for c in load(DATA, "freight", "chokepoints.json"))
        passages = sum(bool(c.get("estimates")) for c in load(DATA, "freight", "chokepoints.json"))
        with open(os.path.join(ROOT, "METHODOLOGY.md"), encoding="utf-8") as f:
            text = f.read()
        hormuz = len(next(c for c in load(DATA, "freight", "chokepoints.json") if c["id"] == "hormuz")["estimates"])
        self.assertIn(f"{n}\n    entries over {passages} passages in 2024 (Hormuz: {hormuz} groups)", text)
        self.assertIn("only while the 'at least' tonnage of the type is at most 85%", text)


# the 34 customs groups added by packages NC1, NC2, NC3 and FNCB (the released site has none of them)
NEW_GROUPS = set("""
    ammonia ammonium-nitrate ammonium-nitrate-limestone ammonium-sulphate barley brewing-distilling-dregs chromium-ore coke dri
    ferro-alloys-other ferro-chromium ferro-manganese ferro-silicon ferrous-scrap graphite molybdenum-ore
    monoammonium-phosphate npk npk-two-nutrient phosphoric-acid pig-iron potassium-sulphate pulses rapeseed-meal rapeseed-oil
    silico-manganese sorghum sulphur sunflower-meal sunflower-oil sunflower-seed superphosphates uan wheat-flour
""".split())

# B2: the rows that rules 3 and 4 of clean.py re-estimate to more than 50 kt and to more than five times the pair's median of the other
# years, in the groups added by the three packages (all years): 27 rows, 20 kept as reported (clean.KEEP_REPORTED and the sunflower seed
# group) and 7 re-estimated, each for the reason given here
ESTIMATE_RIGHT = {
    ("sulphur", "CHE", "ZMB", 2012): "the pair's declared value is steady (USD 37, 45, 41 and 28 million in 2011 to 2014) while the tonnage is missing or under 2 kt; "
                                     "the estimate (206 kt) follows Zambia's imports of 226, 402, 445 and 374 kt",
    ("dri", "MYS", "TWN", 2003): "the estimate (131 kt) is the tonnage of 2002 (129 kt) for the same value, and Taiwan's imports are 162 and 161 kt in 2002 and 2003",
    ("sulphur", "USA", "CHL", 2004): "the value (USD 5.3 million) is that of 2003 (5.4 million, 61 kt); the estimate (59 kt) puts Chile's imports at 62 kt, against 80 and 24 kt in the years around",
    ("coke", "CHN", "USA", 2002): "coke is homogeneous (B3): the value (USD 110 million) is of the order of 2004 and 2006 (USD 690 and 430 million, 1.7 and 2.4 Mt); the estimate (1.1 Mt) is in line with them",
    ("coke", "CHN", "USA", 2003): "same pair and reason: USD 107 million for 117 kt reported, 0.9 Mt estimated, between 2002 and 2004",
    ("coke", "CHN", "USA", 2005): "USD 410 million for 175 kt reported (2,343 USD/t, ten times the group median); the estimate (1.8 Mt) lies between 2004 (1.7 Mt) and 2006 (2.4 Mt)",
    ("sulphur", "SAU", "PNG", 2019): "the estimate (87 kt) puts Papua New Guinea's imports at 159 kt, against 134, 130 and 123 kt in 2021 to 2023",
}


class B2ValueRulesKeepSowingSeed(unittest.TestCase):
    @staticmethod
    def frame(group, o="FRA", d="RUS", t=292.0, usd=112313.0, uv=1300.0):
        import pandas as pd
        rows = [{"year": 2024, "group": group, "o": f"E{i:02d}", "d": f"I{i:02d}", "t": 10000.0 + i, "usd": (10000.0 + i) * uv / 1000} for i in range(30)]
        rows.append({"year": 2024, "group": group, "o": o, "d": d, "t": t, "usd": usd})
        return pd.DataFrame(rows)

    def test_france_to_russia_sunflower_seed_keeps_its_reported_tonnage(self):
        """GNC2.3: 292 t for USD 112 million (385,000 USD/t) was turned into 87 kt by rule 3, a main flow and a lane of 2024."""
        import clean as C
        c = C.clean(self.frame("sunflower-seed"))
        r = c[(c["o"] == "FRA") & (c["d"] == "RUS")].iloc[0]
        self.assertEqual(r["t"], 292.0)
        self.assertFalse(r["imputed"])
        self.assertIn("uv-suspect-t", r["flag"])
        # the control: a group priced by one product tonne is re-estimated by the same rule
        x = C.clean(self.frame("pulses"))
        r = x[(x["o"] == "FRA") & (x["d"] == "RUS")].iloc[0]
        self.assertTrue(r["imputed"])
        self.assertIn("est-gross", r["flag"])
        self.assertGreater(r["t"], 80_000)

    def test_a_row_of_the_table_keeps_its_tonnage_and_the_others_do_not(self):
        import clean as C
        c = C.clean(self.frame("coke", "ZWE", "COD", 27326.0, 679517.0, uv=190.0).assign(year=2006))
        r = c[(c["o"] == "ZWE") & (c["d"] == "COD")].iloc[0]
        self.assertEqual((r["t"], r["imputed"]), (27326.0, False))
        self.assertIn("uv-suspect-t", r["flag"])
        c = C.clean(self.frame("coke", "ZWE", "COG", 27326.0, 679517.0, uv=190.0).assign(year=2006))  # another pair: re-estimated
        r = c[(c["o"] == "ZWE") & (c["d"] == "COG")].iloc[0]
        self.assertTrue(r["imputed"])

    def test_the_table_is_of_the_new_groups_and_each_row_has_a_reason(self):
        import clean as C
        new = NEW_GROUPS
        self.assertEqual(len(C.KEEP_REPORTED), 19)
        for (g, o, d, y), why in C.KEEP_REPORTED.items():
            self.assertIn(g, new, (g, o, d, y))
            self.assertGreater(len(why), 40, (g, o, d, y))
        self.assertTrue(C.UV_KEPT_GROUPS <= new)

    def test_every_large_jump_of_the_new_groups_is_decided_one_by_one(self):
        """Rules 3 and 4 re-estimate no row of the new groups to more than 50 kt and five times the pair's median of the other years
        unless it is listed as right (ESTIMATE_RIGHT above); a new such row fails here and must be decided."""
        import pandas as pd
        import clean as C
        new = NEW_GROUPS
        df = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        # as the rules stood before the table (nothing kept): which rows would be re-estimated that far
        keep, groups = dict(C.KEEP_REPORTED), set(C.UV_KEPT_GROUPS)
        try:
            C.KEEP_REPORTED.clear()
            C.UV_KEPT_GROUPS.clear()
            raw = C.clean(df)
        finally:
            C.KEEP_REPORTED.update(keep)
            C.UV_KEPT_GROUPS.update(groups)
        raw = raw[raw["group"].isin(new)]
        est = raw[raw["imputed"] & (raw["flag"].str.contains("est-gross") | raw["flag"].str.contains("est-uv"))]
        far = set()
        for r in est.itertuples():
            if r.t <= 50_000:
                continue
            others = [t for t, y in zip(*[raw[(raw["group"] == r.group) & (raw["o"] == r.o) & (raw["d"] == r.d)][c].tolist() for c in ("t", "year")]) if y != r.year]
            if not others or r.t > 5 * float(pd.Series(others).median()):
                far.add((r.group, r.o, r.d, int(r.year)))
        self.assertEqual(len(far), 27)
        self.assertEqual(far, set(keep) | set(ESTIMATE_RIGHT) | {("sunflower-seed", "FRA", "RUS", 2024)})
        # the cleaned frame of the package: the 20 rows keep their tonnage, the 7 are estimates
        now = C.clean(df)
        now = now[now["group"].isin(new)].set_index(["group", "o", "d", "year"])
        for k in keep:
            self.assertFalse(now.loc[k, "imputed"], k)
            self.assertEqual(now.loc[k, "t"], now.loc[k, "t0"], k)
        for k in ESTIMATE_RIGHT:
            self.assertTrue(now.loc[k, "imputed"], k)
        self.assertEqual(now.loc[("sunflower-seed", "FRA", "RUS", 2024), "t"], 292.0)

    def test_the_published_pair_is_the_reported_tonnage(self):
        d = load(DATA, "freight", "pairs", "sunflower-seed.json")
        cols = d["cols"]
        rows = [dict(zip(cols, r)) for r in d["rows"]]
        r = next(x for x in rows if x["o"] == "FRA" and x["d"] == "RUS")
        self.assertLess(r["kt"], 1.0)


class B3Coke(unittest.TestCase):
    def test_coke_is_homogeneous_and_pig_iron_and_dri_are_not(self):
        import clean as C
        self.assertIn("coke", C.HOMOGENEOUS)
        self.assertNotIn("pig-iron", C.HOMOGENEOUS)
        self.assertNotIn("dri", C.HOMOGENEOUS)

    def test_unit_value_check_covers_coke_pig_iron_and_dri(self):
        import checks as K
        for g in ("coke", "pig-iron", "dri"):
            self.assertIn(g, K.UV_GROUPS)

    def test_a_coke_row_at_four_dollars_a_tonne_is_a_flagged_estimate(self):
        """GNC3.8: Mozambique to India 2016, 65 Mt for USD 245 million, tripled the 2016 coke series."""
        import pandas as pd
        import clean as C
        rows = [{"year": 2016, "group": "coke", "o": f"E{i:02d}", "d": f"I{i:02d}", "t": 100000.0 + i, "usd": 30000.0 + i} for i in range(40)]  # 300 USD/t
        rows.append({"year": 2016, "group": "coke", "o": "MOZ", "d": "IND", "t": 64992713.0, "usd": 245257.0})
        c = C.clean(pd.DataFrame(rows))
        r = c[(c["o"] == "MOZ") & (c["d"] == "IND")].iloc[0]
        self.assertTrue(r["imputed"])
        self.assertIn("est-uv", r["flag"])
        self.assertTrue(r["enote"].startswith("Atlas estimate"))
        self.assertLess(r["t"], 2e6)
        self.assertEqual(r["t0"], 64992713.0)

    def test_the_published_coke_series_has_no_spike_in_2016(self):
        d = load(DATA, "freight", "lanes", "coke.json")
        i = d["years"].index(2016)
        for key in ("world", "seaborne"):
            around = [d[key][d["years"].index(y)] for y in (2015, 2017)]
            self.assertLess(d[key][i], 1.5 * max(around), (key, d[key][i], around))


class B4TwoMoreFertiliserGroups(unittest.TestCase):
    GROUPS = {"ammonium-nitrate-limestone": (["310240"], "urea", "an-limestone"),
              "npk-two-nutrient": (["310551", "310559", "310560"], "npk", "two-nutrient")}

    def test_neither_group_is_homogeneous(self):
        """Rule 4 would have trebled twelve flows of ammonium nitrate with limestone between Belgium, the Netherlands and France in 2006 to 2010 (their own
        unit values are 700 to 1,900 USD/t against a group median of 180 to 370): the two groups only get the gross-error rule."""
        import clean as C
        self.assertNotIn("ammonium-nitrate-limestone", C.HOMOGENEOUS)
        self.assertNotIn("npk-two-nutrient", C.HOMOGENEOUS)

    def test_the_codes_are_the_intended_ones_and_in_one_group(self):
        import hs_map
        for g, (codes, _, _) in self.GROUPS.items():
            self.assertEqual(hs_map.HS[g], codes)
        seen = {}
        for g, cs in hs_map.HS.items():
            for c in cs:
                self.assertNotIn(c, seen, (c, g, seen.get(c)))
                seen[c] = g
        # the official wording of the codes (CEPII BACI product list)
        with open(os.path.join(ROOT, "raw", "baci", "product_codes_HS92_V202601.csv"), encoding="utf-8") as f:
            words = {r.split(",", 1)[0]: r.split(",", 1)[1] for r in f.read().splitlines()[1:]}
        self.assertIn("ammonium nitrate with calcium carbonate", words["310240"])
        self.assertIn("nitrates and phosphates", words["310551"])
        self.assertIn("nitrogen and phosphorus", words["310559"])
        self.assertIn("phosphorus and potassium", words["310560"])

    def test_the_cache_holds_the_codes_and_the_page_total_is_their_sum(self):
        import pandas as pd
        cache = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
        for g, (_, page, stem) in self.GROUPS.items():
            x = cache[(cache["group"] == g) & (cache["year"] == 2024)]
            self.assertGreater(len(x), 250, g)
            doc = load(DATA, "commodities", page + ".json")
            table = next(e["table"] for e in doc["extra"] if e["key"] == stem + "-exports")
            # the page's world total is the cleaned cache (missing tonnage estimated, gross errors repaired): within 2% of the raw sum
            self.assertAlmostEqual(table["world"], x["t"].sum() / 1e6, delta=0.02 * x["t"].sum() / 1e6, msg=g)

    def test_pages_name_what_their_codes_hold(self):
        index = {e["id"]: e for e in load(DATA, "commodities", "index.json")}
        self.assertIn("310240", index["urea"]["hs"])
        self.assertEqual({"310520", "310551", "310559", "310560"}, set(index["npk"]["hs"]))
        self.assertNotIn("carry nitrogen, phosphorus and potassium in one product", index["npk"]["blurb"])
        self.assertIn("two of them", index["npk"]["blurb"])
        urea, npk = load(DATA, "commodities", "urea.json"), load(DATA, "commodities", "npk.json")
        titles = {e["key"]: e["title"] for e in urea["extra"]}
        self.assertIn("not mixed with limestone", titles["ammonium-nitrate-exports"])
        self.assertTrue(titles["an-limestone-exports"].startswith("Ammonium nitrate with limestone"))
        self.assertIn("three nutrients", npk["labels"]["exports"])
        self.assertIn("three nutrients", npk["labels"]["imports"])
        self.assertEqual({e["key"] for e in npk["extra"]}, {"two-nutrient-exports", "two-nutrient-imports"})
        text = " ".join(urea["notes"] + npk["notes"])
        self.assertIn("HS 310240 is ammonium nitrate mixed with calcium carbonate", text)
        self.assertNotIn("310240 (ammonium nitrate with limestone), 310250", text)  # no longer listed as left out
        self.assertNotIn("(HS 310551, 310559, 310560) are not loaded", text)

    def test_lanes_and_pairs_exist_and_belong_to_their_pages(self):
        for g, (_, page, _) in self.GROUPS.items():
            lane = load(DATA, "freight", "lanes", g + ".json")
            self.assertEqual(lane["k"], page)
            self.assertGreaterEqual(lane["coverage"]["share"], 0.63, g)
            self.assertTrue(os.path.exists(os.path.join(DATA, "freight", "pairs", g + ".json")), g)

    def test_the_web_lists_the_groups(self):
        with open(os.path.join(ROOT, "web", "src", "lib", "freight.ts"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("'ammonium-nitrate-limestone'", src)
        self.assertRegex(src, r"npk: \['npk', 'npk-two-nutrient'\]")


class B5GroupTotalsBeforeTheThreshold(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pandas as pd
        cls.tot = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_group_totals.csv"))
        cls.cache = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))

    def test_the_totals_are_tied_to_the_cache(self):
        """The pairs kept and their tonnes of the totals file are the rows and tonnes of the flows cache, for every group and year; the file's total is
        never below what was kept."""
        k = self.cache.groupby(["year", "group"]).agg(rows=("t", "size"), t=("t", "sum")).reset_index().merge(self.tot, on=["year", "group"], suffixes=("", "_tot"))
        self.assertEqual(len(k), len(self.tot))
        self.assertTrue((k["rows"] == k["kept"]).all())
        # the cache rounds each row to a tonne: half a tonne per row at most
        self.assertTrue(((k["t"] - k["t_kept"]).abs() <= 0.5 * k["rows"] + 1).all())
        self.assertTrue((self.tot["t"] + 1 >= self.tot["t_kept"]).all())
        self.assertTrue((self.tot["pairs"] >= self.tot["kept"]).all())

    def test_graphite_is_the_reviewers_case(self):
        """GNC3.6: natural graphite 2024, 499,864 t in the customs file and 449,049 t in 92 of 1,396 pairs kept."""
        r = self.tot[(self.tot["group"] == "graphite") & (self.tot["year"] == 2024)].iloc[0]
        self.assertEqual((round(r["t"]), round(r["t_kept"]), int(r["kept"]), int(r["pairs"])), (499864, 449049, 92, 1396))

    def test_a_page_says_so_when_its_tables_hold_under_97_percent(self):
        import glob
        said = {}
        for f in glob.glob(os.path.join(DATA, "commodities", "*.json")):
            if f.endswith("index.json"):
                continue
            for n in load(f).get("notes", []):
                if "that the customs file records for these codes" in n:
                    said.setdefault(os.path.basename(f)[:-5], []).append(n)
        graphite = " ".join(said["graphite"])
        self.assertIn("the tables hold 0.449 Mt, 90% of the 0.5 Mt", graphite)
        self.assertIn("92 of the 1,396 pairs", graphite)
        self.assertIn("under the threshold of the extract (1,000 t and USD 1 million", graphite)
        ferro = " ".join(said["ferro-alloys"])
        for part in ("Ferro-silicon", "Ferro-manganese", "The other ferro-alloys"):
            self.assertIn(part, ferro)
        self.assertNotRegex(" ".join(sum(said.values(), [])), r"\de[+-]\d")

    def test_the_other_ferro_alloys_difference_is_one_rule_3_row(self):
        """GNC3.6: 695.6 kt in the cache, 693.5 kt on the page: Kazakhstan to Latvia 2024, 2,106 t for USD 137,000 (65 USD/t, under a hundredth of the group's
        median), re-estimated to 8 t by rule 3; the same pair declared 6,267 t for USD 533,000 in 2022."""
        import clean as C
        import pandas as pd
        x = self.cache[(self.cache["group"] == "ferro-alloys-other") & (self.cache["year"] == 2024)]
        self.assertEqual(round(x["t"].sum()), 695578)
        doc = load(DATA, "commodities", "ferro-alloys.json")
        table = next(e["table"] for e in doc["extra"] if e["key"] == "ferro-alloys-other-exports")
        self.assertAlmostEqual(table["world"], 0.6935, places=3)
        row = x[(x["o"] == "KAZ") & (x["d"] == "LVA")].iloc[0]
        self.assertEqual((row["t"], row["usd"]), (2106.0, 137.0))
        c = C.clean(self.cache[self.cache["group"] == "ferro-alloys-other"])
        r = c[(c["year"] == 2024) & (c["o"] == "KAZ") & (c["d"] == "LVA")].iloc[0]
        self.assertIn("est-gross", r["flag"])
        self.assertAlmostEqual(c[c["year"] == 2024]["t"].sum(), table["world"] * 1e6, delta=600)


class B6MixedKeepsThreeDigits(unittest.TestCase):
    def test_every_mixed_figure_has_at_most_three_significant_digits(self):
        import glob
        n = 0
        for f in glob.glob(os.path.join(DATA, "freight", "lanes", "*.json")):
            for v in load(f)["mixed"]:
                if v:
                    n += 1
                    self.assertEqual(float(f"{v:.3g}"), v, (os.path.basename(f), v))
        self.assertGreater(n, 100)

    def test_dap_mixed_24_kt_reads_0_0238(self):
        """GNC1.9: 23,849 t of DAP from the United States to Mexico read "Plus 0.020 Mt"."""
        d = load(DATA, "freight", "lanes", "dap.json")
        self.assertEqual(d["unit"], "Mt")
        self.assertEqual(d["mixed"][d["years"].index(2024)], 0.0238)


if __name__ == "__main__":
    unittest.main()
