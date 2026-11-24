"""Data tests of the trade-engine plan for package E6-shares: chokepoint shares (C01 to C11), flow tables and caveats
(V02, V04 to V07), the commodity part of D14 and D17, and the outputs the web packages read (routes planned with
routing.plan(), vessel-class speeds). They read the files written by build_freight.py and build_commodities.py.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
Each class is skipped when the files it reads are absent. Tolerances are the plan's (section 12), not today's numbers.
"""
import ast
import glob
import json
import os
import re
import sys
import unittest
from collections import defaultdict
from datetime import date, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("freight", "trade", "geo", "commodities"):
    p = os.path.join(ROOT, "pipeline", sub)
    if p not in sys.path:
        sys.path.insert(0, p)

FREIGHT = os.path.join(ROOT, "data", "freight")
PAIRS = os.path.join(FREIGHT, "pairs")
COMMOD = os.path.join(ROOT, "data", "commodities")
CHECKS = os.path.join(ROOT, "pipeline", "cache", "trade_checks.json")
RAW_PW = os.path.join(ROOT, "raw", "portwatch")
# the PortWatch caps are checked to 0.05 Mt against the daily table; the weekly series rebuilt from data/ (a fresh clone,
# the CI) is not that precise
HAS_PW_DAILY = bool(glob.glob(os.path.join(RAW_PW, "chokepoints_daily_page*.json")))
YEAR = 2024
TANKER = {"crude-oil", "refined-products", "lng", "lpg", "palm-oil", "soyoil",
          # package NC1: ammonia (gas carriers), UAN solution and phosphoric acid (chemical tankers)
          "ammonia", "uan", "phosphoric-acid",
          # package NC2: the sunflower and rapeseed oils (chemical tankers, as soybean and palm oil)
          "sunflower-oil", "rapeseed-oil"}
# general cargo: compared with PortWatch's container, general-cargo and ro-ro ships (review GE6, finding 7)
CARGO = {"steel", "copper-refined", "aluminium", "coffee", "cocoa", "cotton",
         # package L1: the minor metals that sail as general cargo
         "lead-metal", "zinc-metal", "tin-metal", "tin-ore", "cobalt", "lithium", "rare-earths",
         # package NC3: the ferro-alloys that sail as general cargo (scrap, chromite, pig iron, DRI and coke are dry bulk)
         "ferro-chromium", "ferro-manganese", "silico-manganese", "ferro-silicon"}


def vtype(g):
    return "tanker" if g in TANKER else "cargo" if g in CARGO else "dry"

BUILT = os.path.isdir(PAIRS) and os.path.exists(os.path.join(FREIGHT, "chokepoints.json"))
need_build = unittest.skipUnless(BUILT, "build_lanes.py and build_freight.py have not written their files yet")

_cache = {}


def load_json(path):
    if path not in _cache:
        with open(path, encoding="utf-8") as f:
            _cache[path] = json.load(f)
    return _cache[path]


def chokepoint(cid):
    return next(c for c in load_json(os.path.join(FREIGHT, "chokepoints.json")) if c["id"] == cid)


def estimate(cid, group):
    return next((e for e in chokepoint(cid).get("estimates", []) if e.get("p") == group), None)


def pairs_groups():
    return sorted(f[:-5] for f in os.listdir(PAIRS) if f.endswith(".json"))


def tonnage(cid):
    """low and high Mt through a gate, by group and by vessel type, recomputed from the pairs files (seaborne rows)."""
    low, high = defaultdict(float), defaultdict(float)
    for g in pairs_groups():
        p = load_json(os.path.join(PAIRS, g + ".json"))
        if cid not in p["gates"]:
            continue
        b = 1 << p["gates"].index(cid)
        for r in p["rows"]:
            if r[3] not in (0, 1):
                continue
            if r[8] & b:
                low[g] += r[2] / 1e3
            if (r[8] | r[9]) & b:
                high[g] += r[2] / 1e3
    return low, high


def by_type(per_group):
    out = defaultdict(float)
    for g, v in per_group.items():
        out[vtype(g)] += v
        out["all"] += v
    return out


_pw = {}


def portwatch(cid):
    """IMF PortWatch estimated volume by vessel type and full year (Mt): raw/portwatch daily files when present,
    otherwise the weekly series of data/freight/portwatch/<id>.json (Mt/day x days of each week in the year)."""
    if cid in _pw:
        return _pw[cid]
    c = chokepoint(cid)
    out = defaultdict(dict)
    pages = glob.glob(os.path.join(RAW_PW, "chokepoints_daily_page*.json"))
    if pages and c.get("portwatch"):
        days = defaultdict(int)
        for pg in pages:
            for f in load_json(pg)["features"]:
                a = f["attributes"]
                if a["portid"] != c["portwatch"]:
                    continue
                y = int(a["year"])
                days[y] += 1
                for t, col in (("dry", "capacity_dry_bulk"), ("tanker", "capacity_tanker"), ("cargo", "capacity_container"),
                               ("cargo", "capacity_general_cargo"), ("cargo", "capacity_roro"), ("all", "capacity")):
                    out[y][t] = out[y].get(t, 0.0) + (a[col] or 0) / 1e6
        out = {y: v for y, v in out.items() if days[y] >= 365}
    else:
        path = os.path.join(FREIGHT, "portwatch", cid + ".json")
        if not os.path.exists(path):
            _pw[cid] = {}
            return {}
        s = load_json(path)
        start = date.fromisoformat(s["start"])
        for i in range(len(s["vol"]["tanker"])):
            w0 = start + timedelta(days=7 * i)
            for k in range(7):
                dd = w0 + timedelta(days=k)
                for t, key in (("dry", "dry"), ("tanker", "tanker"), ("cargo", "container"), ("cargo", "other"), ("all", "total")):
                    out[dd.year][t] = out[dd.year].get(t, 0.0) + s["vol"][key][i]
        last = date.fromisoformat(s["y"])
        out = {y: v for y, v in out.items() if y >= start.year + (start.month > 1 or start.day > 1) and date(y, 12, 31) <= last}
    _pw[cid] = out
    return out


def k9():
    return [r for r in load_json(CHECKS)["findings"] if r["check"] == "K9"]


# ------------------------------------------------------------------ chokepoint shares
@need_build
class Shares(unittest.TestCase):
    def test_C01_hormuz_groups(self):
        est = {e["p"]: e for e in chokepoint("hormuz")["estimates"]}
        print(f"\nC01: Hormuz estimates for {len(est)} groups")
        self.assertGreaterEqual(len(est), 15)
        for g in ("urea", "dap", "alumina", "aluminium", "lpg", "lng"):
            self.assertIn(g, est)
        for g, want in (("urea", 26.0), ("dap", 21.7), ("alumina", 20.9)):
            self.assertAlmostEqual(est[g]["f"]["v"], want, delta=4, msg=g)

    def test_C02_hormuz_crude(self):
        e = estimate("hormuz", "crude-oil")
        print(f"\nC02: Hormuz crude at least {e['f']['v']}%, {e['mt'][0]} Mt; up to {e.get('hi', {}).get('v')}%")
        # The plan's 29.5% and 564 Mt assumed that every Saudi cargo loads inside the Gulf. The EIA country brief gives
        # Yanbu, on the Red Sea, a record 18% of Saudi seaborne crude exports in 2024: under the coast rule
        # sau-crude-red-sea the westbound Saudi cargoes (57.5 Mt) may load at Yanbu and are "may cross" pairs.
        self.assertGreaterEqual(e["f"]["v"], 26.0)
        self.assertAlmostEqual(e["mt"][0], 509, delta=20)
        # the plan's 38 to 42 is the uncapped figure; where PortWatch's tanker volume less the other tanker groups' "at
        # least" tonnage caps it (review GE6, finding 8), the UAE crude still adds to the figure and the note says so
        if "capped" in e["hi"]["n"]:
            self.assertTrue(e["f"]["v"] + 1 <= e["hi"]["v"] <= 42, e["hi"]["v"])
            self.assertIn("United Arab Emirates", e["hi"]["n"])
        else:
            self.assertTrue(38 <= e["hi"]["v"] <= 42, e["hi"]["v"])

    def test_C03_hormuz_products(self):
        """UAE products have two load options (inside and outside the strait), so the honest figure is a range: the
        plan's "at least 18%" assumed every Emirati cargo loads inside the strait."""
        e = estimate("hormuz", "refined-products")
        print(f"\nC03: Hormuz refined products at least {e['f']['v']}% ({e['mt'][0]} Mt), up to {e.get('hi', {}).get('v')}%")
        self.assertGreaterEqual(e.get("hi", e["f"])["v"], 18)
        self.assertGreaterEqual(e["f"]["v"], 12)

    def test_C04_sunda_taiwan_below_portwatch(self):
        for cid in ("sunda", "taiwan-strait"):
            low, _ = tonnage(cid)
            t = by_type(low)
            pw = portwatch(cid)[YEAR]
            print(f"\nC04: {cid} low {t['all']:.1f} Mt (dry {t['dry']:.1f}); PortWatch {pw['all']:.1f} (dry {pw['dry']:.1f})")
            self.assertLessEqual(t["all"], pw["all"], cid)
            self.assertLessEqual(t["dry"], pw["dry"], cid)
        low, _ = tonnage("taiwan-strait")
        self.assertLessEqual(low["iron-ore"], portwatch("taiwan-strait")[YEAR]["dry"])

    def test_C05_two_sided(self):
        out = {}
        for cid in ("hormuz", "korea-strait", "cape-good-hope", "gibraltar", "bosphorus", "dover"):
            low, _ = tonnage(cid)
            t, pw = by_type(low), portwatch(cid)[YEAR]
            out[cid] = (round(t["dry"] / pw["dry"], 2), round(t["tanker"] / pw["tanker"], 2))
        print("\nC05: low over PortWatch 2024 (dry, tanker):", out)
        # The Korea Strait has a lower floor: cargo from the Americas for northern China can go south of Japan
        # (routing.ROUTE_AROUND), and South Korean crude has refinery ports on both sides of the strait, so both are
        # "may cross" pairs and leave the "at least" figure.
        floor = {"korea-strait": 0.3}
        bad = {c: v for c, v in out.items() if not all(floor.get(c, 0.4) <= x <= 1.1 for x in v)}
        self.assertEqual(bad, {})

    def test_C06_k9_within_best_year(self):
        above = {}
        for r in k9():
            if r.get("kind") != "passage" or r["chokepoint"] == "danish-straits":
                continue
            if r["value"] > 1.1 * r["best"]:
                above[(r["chokepoint"], r["type"])] = round(r["value"] / r["best"], 2)
        print("\nC06: passages above 110% of PortWatch's best year:", above)
        self.assertEqual(above, {})

    def test_C06_above_is_reported(self):
        """A passage still above PortWatch's best year carries a K9 flag with its cause and a note on its shares."""
        recs = [r for r in k9() if r.get("kind") == "passage"]
        self.assertTrue(recs)
        for r in recs:
            if r["chokepoint"] == "danish-straits" or r["value"] <= 1.1 * r["best"]:
                continue
            self.assertEqual(r["level"], "flag", r)
            self.assertIn("PortWatch", r["text"])
            for e in chokepoint(r["chokepoint"]).get("estimates", []):
                if vtype(e["p"]) == r["type"]:
                    self.assertIn("PortWatch", e["f"]["n"], (r["chokepoint"], e["p"]))

    @unittest.skipUnless(HAS_PW_DAILY, "raw/portwatch daily files are not on this machine")
    def test_C07_low_high_wording_cap(self):
        for c in load_json(os.path.join(FREIGHT, "chokepoints.json")):
            for e in c.get("estimates", []):
                hi = e.get("hi", e["f"])
                self.assertLessEqual(e["f"]["v"], hi["v"], (c["id"], e["p"]))
                self.assertLessEqual(e["mt"][0], e["mt"][1], (c["id"], e["p"]))
                # GR4S.7: a floor that rounds to nothing is said in words, not "at least 0"
                self.assertTrue(e["f"]["n"].startswith("no cargo has to cross it" if e["mt"][0] == 0 else "at least"), (c["id"], e["p"]))
                if "hi" in e:
                    self.assertTrue(e["hi"]["n"].startswith("up to"), (c["id"], e["p"]))
                self.assertEqual(e["f"]["s"], "atlas")
                if c.get("portwatch") and not c.get("portwatchLabel"):
                    pw = portwatch(c["id"]).get(YEAR, {}).get(vtype(e["p"]))
                    # package FNCB: not where the type's "at least" tonnage is above PW_NEAR of PortWatch's volume (no cap there)
                    if pw is not None and e["mt"][0] <= pw and by_type(tonnage(c["id"])[0])[vtype(e["p"])] <= 0.85 * pw:
                        self.assertLessEqual(e["mt"][1], pw + 0.05, (c["id"], e["p"]))
        for name in ("chokepoints.json", "chokepoint-lanes.json"):
            with open(os.path.join(FREIGHT, name), encoding="utf-8") as f:
                self.assertNotIn("lower bound", f.read().lower(), name)

    def test_C07_every_group_and_threshold(self):
        """Every lane group is computed (M-036): an entry exists exactly where high is at least 2% or 1 Mt."""
        for cid in ("hormuz", "malacca", "cape-good-hope"):
            low, high = tonnage(cid)
            want = set()
            for g, v in high.items():
                sea = load_json(os.path.join(PAIRS, g + ".json"))["seaborne"] / 1e3
                if v >= 1 or v / sea >= 0.02:
                    want.add(g)
            have = {e["p"] for e in chokepoint(cid).get("estimates", [])}
            self.assertEqual(have, want, cid)

    def test_C08_chokepoint_lanes_from_pairs(self):
        cl = load_json(os.path.join(FREIGHT, "chokepoint-lanes.json"))
        rows = cl["chokepoints"]["hormuz"]
        s = sum(r[3] for r in rows if r[0] == "crude-oil" and r[4] == 1)
        self.assertAlmostEqual(s, estimate("hormuz", "crude-oil")["mt"][0], delta=0.5)
        self.assertTrue(all(len(r) == 5 and r[4] in (0, 1) for rs in cl["chokepoints"].values() for r in rs))
        self.assertTrue(any(r[4] == 0 for r in rows))

    def test_C09_kozmino_and_denominators(self):
        # review GE6, finding 4: a corridor with no seaborne tonnage gets no share (its numerator would be all modes
        # over a seaborne total) but a shareNa with the all-modes volume; the history stays, labelled all modes
        r = next(x for x in load_json(os.path.join(FREIGHT, "routes.json")) if x["id"] == "kozmino-china-espo")
        self.assertNotIn("shares", r)
        self.assertNotIn("shareCommodity", r)
        v = next(h["v"] for h in r["history"] if h["y"] == YEAR)
        self.assertAlmostEqual(v, 108.5, delta=0.5)
        self.assertRegex(r["shareNa"], r"split (is )?not known")
        self.assertIn("all modes", r["shareNa"])
        self.assertIn(f"{v:.1f} Mt", r["shareNa"])
        self.assertIn("only if all of it went by sea", r["shareNa"])
        self.assertIn("All modes", r["historyNote"])
        for x in load_json(os.path.join(FREIGHT, "routes.json")):
            for s in x.get("shares", []):
                self.assertNotIn("all modes", s["f"]["n"], x["id"])
        for c in load_json(os.path.join(FREIGHT, "chokepoints.json")):
            for e in c.get("estimates", []):
                sea = load_json(os.path.join(PAIRS, e["p"] + ".json"))["seaborne"] / 1e3
                # rounding of f.v (0.1 point) and of mt (0.1 Mt from 10 Mt)
                self.assertAlmostEqual(e["f"]["v"], 100 * e["mt"][0] / sea, delta=0.051 + 5 / sea, msg=(c["id"], e["p"]))

    def test_C10_no_exception_on_checks(self):
        for name in ("build_freight.py", "build_lanes.py"):
            with open(os.path.join(ROOT, "pipeline", "freight", name), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.Raise, ast.Assert)):
                    src = ast.unparse(node)
                    self.assertFalse(re.search(r"\bK\d|finding|check|ratio|portwatch|best", src, re.I), (name, src))
        self.assertTrue(k9())
        self.assertTrue(all(r["level"] in ("flag", "qa") for r in k9()))

    def test_C11_alert_and_bypass_note(self):
        # the commodities of an alert are derived from the chokepoint estimates (build_alerts.py), not written by hand
        a = next(x for x in load_json(os.path.join(FREIGHT, "alerts.json")) if x["id"] == "hormuz-2026")
        self.assertIn("phosphate", a["commodities"])
        notes = " ".join(x.get("note", "") for x in chokepoint("hormuz")["alternatives"])
        self.assertNotIn("4.7 mb/d", notes)
        self.assertIn("7,000 kb/d", notes)
        self.assertIn("1,500 kb/d", notes)

    def test_GE6_1_above_same_year_portwatch_is_noted(self):
        """Review GE6, finding 1: where the "at least" tonnage of a vessel type is above PortWatch's volume of the same
        type and year, every share of that type says so and gives PortWatch's figures, and the K9 record is a flag.
        For Suez and Bab el-Mandeb the reason is the curated Red Sea alert, quoted."""
        seen = set()
        for r in k9():
            if r.get("kind") != "passage" or r["chokepoint"] in ("danish-straits",) or r.get("reference") is None:
                continue
            if r["value"] <= r["reference"] + 0.05:
                continue
            seen.add((r["chokepoint"], r["type"]))
            self.assertEqual(r["level"], "flag", r)
            for e in chokepoint(r["chokepoint"]).get("estimates", []):
                if vtype(e["p"]) == r["type"]:
                    self.assertIn("IMF PortWatch's estimate for all", e["f"]["n"], (r["chokepoint"], e["p"]))
                    self.assertRegex(e["f"]["n"], r"normal itinerary|probably overstate", (r["chokepoint"], e["p"]))
                    if r["chokepoint"] in ("suez", "bab-el-mandeb") and r["value"] <= 1.1 * r["best"]:
                        self.assertIn("Red Sea diversions", e["f"]["n"], (r["chokepoint"], e["p"]))
        print("\nGE6.1: passages above PortWatch's volume of the same year:", sorted(seen))
        self.assertIn(("suez", "tanker"), seen)
        self.assertIn(("bab-el-mandeb", "dry"), seen)

    def test_GE6_2_unrecorded_origins_beyond_largest_buyer(self):
        """Review GE6, finding 2: the note on missing exports reads every main buyer (via and viaAlt) and the "break"
        caveats of a fall, not only the origin's largest buyer."""
        cv = load_json(os.path.join(FREIGHT, "caveats.json"))
        if "crude-irn" in cv:
            self.assertIn("Iran", estimate("malacca", "crude-oil")["f"]["n"])
            self.assertIn("Iran", estimate("hormuz", "crude-oil")["f"]["n"])
        if "urea-irn" in cv and estimate("hormuz", "urea"):
            self.assertIn("Iran", estimate("hormuz", "urea")["f"]["n"])
        for e in chokepoint("hormuz")["estimates"]:
            if "are missing:" in e["f"]["n"]:
                self.assertIn("record only in part", e["f"]["n"])

    def test_GE6_7_general_cargo_type(self):
        """Review GE6, finding 7: steel, refined copper, aluminium, coffee, cocoa and cotton are compared with PortWatch's
        container, general-cargo and ro-ro ships, not with its dry bulk."""
        import build_freight as BF
        self.assertEqual(BF.CARGO_GROUPS & set(pairs_groups()), CARGO & set(pairs_groups()))
        recs = {(r["chokepoint"], r["type"]): r for r in k9() if r.get("kind") == "passage"}
        self.assertIn(("suez", "cargo"), recs)
        low, _ = tonnage("suez")
        self.assertAlmostEqual(recs[("suez", "cargo")]["value"], by_type(low)["cargo"], delta=0.2)
        self.assertAlmostEqual(recs[("suez", "dry")]["value"], by_type(low)["dry"], delta=0.2)
        self.assertAlmostEqual(recs[("suez", "cargo")]["reference"], portwatch("suez")[YEAR]["cargo"], delta=0.5)

    @unittest.skipUnless(HAS_PW_DAILY, "raw/portwatch daily files are not on this machine")
    def test_GE6_8_cap_leaves_room_for_other_groups(self):
        """Review GE6, finding 8: the upper figure is capped at PortWatch's volume of the type less the "at least"
        tonnage of the other groups of that type, never below the group's own "at least". Package FNCB: only while the type's
        "at least" tonnage is at most PW_NEAR of PortWatch's volume; above it the upper figure is not capped."""
        import build_freight as BF
        n = 0
        for c in load_json(os.path.join(FREIGHT, "chokepoints.json")):
            if not c.get("portwatch") or c.get("portwatchLabel") or not c.get("estimates"):
                continue
            pw = portwatch(c["id"]).get(YEAR)
            if not pw:
                continue
            low, _ = tonnage(c["id"])
            t = by_type(low)
            for e in c["estimates"]:
                typ = vtype(e["p"])
                room = max(low[e["p"]], pw[typ] - (t[typ] - low[e["p"]]))
                if t[typ] > BF.PW_NEAR * pw[typ] + 0.05:
                    self.assertFalse("hi" in e and "capped at" in e["hi"]["n"], (c["id"], e["p"]))
                    continue
                self.assertLessEqual(e["mt"][1], room + 0.15, (c["id"], e["p"], room))
                if "hi" in e and "capped" in e["hi"]["n"]:
                    n += 1
                    self.assertAlmostEqual(e["mt"][1], room, delta=0.15, msg=(c["id"], e["p"]))
        print(f"\nGE6.8: {n} capped upper figures")

    def test_GE6_10_split_lane_files(self):
        """Review GE6, finding 10: one file per passage, same note and rows as the single file."""
        one = load_json(os.path.join(FREIGHT, "chokepoint-lanes.json"))
        d = os.path.join(FREIGHT, "chokepoint-lanes")
        self.assertEqual(sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json")), sorted(one["chokepoints"]))
        for cp, rows in one["chokepoints"].items():
            part = load_json(os.path.join(d, cp + ".json"))
            self.assertEqual(part["n"], one["n"])
            self.assertEqual(list(part["chokepoints"]), [cp])
            self.assertEqual(part["chokepoints"][cp], rows)
            self.assertEqual(set(part["groups"]), {r[0] for r in rows})

    def test_GE6_5_parallel_table_says_when_incomplete(self):
        """Review GE6, finding 5: with pairs skipped, the parallel-threshold table says it is incomplete and does not
        claim to reproduce the published figures."""
        import build_commodities as BC
        rec = {"check": "K9", "kind": "parallel", "group": None, "year": YEAR, "chokepoint": "malacca", "pct": 0.05, "nm": 300,
               "value": 818.0, "high": 1986.3, "level": "qa", "text": "malacca: ..."}
        real = BC.K.load
        try:
            for skipped, want, unwanted in ((298.5, "Incomplete: 298.5 Mt", "The published figures use"),
                                            (0.0, "The published figures use 5% or 300 nm", "Incomplete")):
                BC.K.load = lambda s=skipped: [dict(rec, skipped=s, complete=not s)]
                text = "\n".join(BC.qa_checks())
                self.assertIn(want, text)
                self.assertNotIn(unwanted, text)
        finally:
            BC.K.load = real
        for r in k9():
            if r.get("kind") == "parallel":
                self.assertEqual(r["complete"], not r["skipped"], r)

    def test_detour_from_main_lanes(self):
        for c in load_json(os.path.join(FREIGHT, "chokepoints.json")):
            if "detour" in c:
                self.assertGreaterEqual(c["detour"]["lanes"], 3)
                self.assertGreater(c["detour"]["nm"], 0, c["id"])


# ------------------------------------------------------------------ routes planned with routing.plan()
@need_build
class Routes(unittest.TestCase):
    def routes(self):
        return {r["id"]: r for r in load_json(os.path.join(FREIGHT, "routes.json"))}

    def test_routes_use_plan(self):
        rs = self.routes()
        # the 133 hand-written routes of routes_def.json, then the generated corridors (generated_routes.py, test_generated_routes.py)
        self.assertEqual(sum(1 for r in rs.values() if not r.get("generated")), 133)
        c3 = rs["C3"]
        self.assertIn("cape-good-hope", c3["via"])
        self.assertNotIn("sunda", c3["via"])
        self.assertTrue(any("sunda" in lst for lst in c3["viaAlt"]))
        for r in rs.values():
            self.assertIn("viaAlt", r)
            for a in r.get("alts", []):
                self.assertNotIn("panama", a["via"] if "suez" in a.get("avoids", []) else [])
            if r.get("alt"):
                self.assertEqual(r["alt"]["distanceNm"], r["alts"][0]["distanceNm"])

    def test_tc15_alternative_via_cape(self):
        r = self.routes()["TC15"]
        self.assertIn("cape-good-hope", r["alt"]["via"])

    def test_class_share_basis(self):
        rs = self.routes()
        with_class = [r for r in rs.values() if r.get("shareClass")]
        self.assertTrue(with_class)
        for r in with_class:
            self.assertIn("routed distance", r["shareClass"]["n"])

    def test_vessel_class_speeds(self):
        import vessel_rules as VR
        vc = load_json(os.path.join(FREIGHT, "vessel-classes.json"))
        for c in vc:
            self.assertEqual(c["speedKn"], VR.speed(c["id"]), c["id"])
            self.assertIn("Atlas assumption", c["speedNote"])
            # review GE6, finding 9: an assumed figure with source id atlas, a year, and a note on what it is
            self.assertEqual({k: c["speed"][k] for k in ("v", "u", "s")}, {"v": c["speedKn"], "u": "kn", "s": "atlas"}, c["id"])
            self.assertIsInstance(c["speed"]["y"], int)
            self.assertIn("not a measured speed", c["speed"]["n"])


# ------------------------------------------------------------------ flow tables and caveats
COMM_BUILT = os.path.exists(os.path.join(COMMOD, "crude-oil.json")) and BUILT
need_comm = unittest.skipUnless(COMM_BUILT, "build_commodities.py has not run yet")


def commodity(cid):
    return load_json(os.path.join(COMMOD, cid + ".json"))


def commodities():
    return sorted(f[:-5] for f in os.listdir(COMMOD) if f.endswith(".json") and f != "index.json")


def flow(cid, o, d):
    return next((f for f in commodity(cid).get("flows", []) if f["o"] == o and f["d"] == d), None)


@need_comm
class Flows(unittest.TestCase):
    def test_V02_iran_and_malaysia(self):
        cv = load_json(os.path.join(FREIGHT, "caveats.json"))
        self.assertIn("crude-irn", cv)
        d = commodity("crude-oil")
        text = d["exports"].get("caveat", "") + " " + " ".join(d.get("notes", []))
        self.assertIn("Iran", text)
        self.assertIn("Malaysia", text)

    def test_V04_uranium_modes(self):
        fl = commodity("uranium")["flows"]
        print(f"\nV04: {len(fl)} uranium flows")
        self.assertTrue(fl)
        self.assertTrue(all("mode" in f for f in fl))
        self.assertEqual(flow("uranium", "KAZ", "RUS")["mode"], "land")
        self.assertEqual(flow("uranium", "KAZ", "CHN")["mode"], "land")
        self.assertTrue(all("mode" not in f for f in commodity("gold")["flows"]))

    def test_V05_mode_values(self):
        for cid in commodities():
            for f in commodity(cid).get("flows", []):
                if "mode" in f:
                    self.assertIn(f["mode"], ("sea", "land", "mixed", "pipeline"), (cid, f["o"], f["d"]))
                if "transit" in f:
                    self.assertEqual(f["mode"], "sea", (cid, f["o"], f["d"]))
                    self.assertEqual(set(f["transit"]) - {"url"}, {"port", "c", "s"})

    def test_V05_engine_modes(self):
        self.assertEqual(flow("crude-oil", "RUS", "CHN")["mode"], "mixed")
        self.assertEqual(flow("iron-ore", "IND", "CHN")["mode"], "sea")
        f = flow("uranium", "NER", "FRA")  # landlocked exporter with a sourced transit port (Cotonou)
        self.assertEqual(f["mode"], "sea")
        self.assertEqual(f["transit"]["c"], "BEN")
        self.assertEqual(flow("crude-oil", "CAN", "USA")["mode"], "land")

    def test_flow_lanes_are_main(self):
        for cid in commodities():
            for f in commodity(cid).get("flows", []):
                if "lane" not in f:
                    continue
                g = f["lane"].split(":")[0]
                ln = next((x for x in load_json(os.path.join(FREIGHT, "lanes", g + ".json"))["lanes"] if x["id"] == f["lane"]), None)
                self.assertIsNotNone(ln, f["lane"])
                self.assertEqual(ln["set"], "main", f["lane"])

    def test_V06_hypothesis_wording(self):
        pat = re.compile(r"is relabelled|has been declared under other origins|after ship-to-ship transfer", re.I)
        texts = [e["text"] for e in load_json(os.path.join(FREIGHT, "caveats.json")).values()]
        for cid in commodities():
            d = commodity(cid)
            for k in ("exports", "imports"):
                if d.get(k):
                    texts.append(d[k].get("caveat", ""))
            texts += [f.get("n", "") for f in d.get("flows", [])]
        for t in texts:
            for sentence in re.split(r"(?<=\.)\s", t):
                if pat.search(sentence):
                    self.assertRegex(sentence, r"plausible|may", sentence)

    def test_V07_qa_sections(self):
        with open(os.path.join(ROOT, "pipeline", "commodities", "QA.md"), encoding="utf-8") as f:
            qa = f.read()
        missing = [t for t in ("## Trade checks", "## Passages against IMF PortWatch (K9)", "## Rows dropped by the cleaning rules",
                               "## Vessel classes without a sourced draught") if t not in qa]
        self.assertEqual(missing, [])
        self.assertTrue("### K8" in qa and re.search(r"\| hormuz \| tanker \|", qa), "no K8 section or no Hormuz tanker row in QA.md")

    def test_D14_estimated_flow(self):
        f = flow("wheat", "RUS", "EGY")
        self.assertTrue(f["est"])
        self.assertEqual(f["s"], "atlas")
        self.assertIn("Atlas estimate", f["n"])
        for cid in commodities():
            for x in commodity(cid).get("flows", []):
                if x.get("est"):
                    self.assertEqual(x["s"], "atlas", (cid, x["o"], x["d"]))

    def test_D17_extra_codes_and_one_s19_mapping(self):
        import build_commodities as BC
        self.assertEqual(BC.Baci.iso(None, "XAS"), "XAS")
        self.assertEqual(BC.Baci.iso(None, "GIB"), "GIB")
        for name in ("build_commodities.py", "build_profiles.py"):
            with open(os.path.join(ROOT, "pipeline", "commodities", name), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            lits = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and "S19" in n.value]
            self.assertEqual(lits, [], name)

    def test_GE6_12_no_lower_bound_wording(self):
        """Review GE6, finding 12: the USGS world-reserves note says "a minimum", not "lower bound"."""
        with open(os.path.join(ROOT, "pipeline", "commodities", "build_commodities.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        lits = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and "lower bound" in n.value.lower()]
        self.assertEqual(lits, [])

    def test_profiles_have_index_codes_only(self):
        idx = {c["c"] for c in load_json(os.path.join(ROOT, "data", "countries", "index.json"))}
        # one file per country (data/countries/profiles/<ISO3>.json); the light index profiles.json is gone (review GC1.9)
        keys = {os.path.basename(f)[:-5] for f in glob.glob(os.path.join(ROOT, "data", "countries", "profiles", "*.json"))}
        self.assertEqual(keys - idx - {"EU27"}, set())  # EU27: USDA PSD reports the Union as one trader


if __name__ == "__main__":
    unittest.main()
