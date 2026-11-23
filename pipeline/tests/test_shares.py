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
YEAR = 2024
TANKER = {"crude-oil", "refined-products", "lng", "lpg", "palm-oil", "soyoil"}

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
        out["tanker" if g in TANKER else "dry"] += v
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
                for t, col in (("dry", "capacity_dry_bulk"), ("tanker", "capacity_tanker"), ("all", "capacity")):
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
                for t, key in (("dry", "dry"), ("tanker", "tanker"), ("all", "total")):
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
        self.assertGreaterEqual(e["f"]["v"], 29.5)
        self.assertAlmostEqual(e["mt"][0], 564, delta=15)
        self.assertTrue(38 <= e["hi"]["v"] <= 42, e["hi"]["v"])

    def test_C03_hormuz_products(self):
        e = estimate("hormuz", "refined-products")
        print(f"\nC03: Hormuz refined products at least {e['f']['v']}% ({e['mt'][0]} Mt), up to {e.get('hi', {}).get('v')}%")
        self.assertGreaterEqual(e["f"]["v"], 18)

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
        bad = {c: v for c, v in out.items() if not all(0.4 <= x <= 1.1 for x in v)}
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
                if ("tanker" if e["p"] in TANKER else "dry") == r["type"]:
                    self.assertIn("PortWatch", e["f"]["n"], (r["chokepoint"], e["p"]))

    def test_C07_low_high_wording_cap(self):
        for c in load_json(os.path.join(FREIGHT, "chokepoints.json")):
            for e in c.get("estimates", []):
                hi = e.get("hi", e["f"])
                self.assertLessEqual(e["f"]["v"], hi["v"], (c["id"], e["p"]))
                self.assertLessEqual(e["mt"][0], e["mt"][1], (c["id"], e["p"]))
                self.assertTrue(e["f"]["n"].startswith("at least"), (c["id"], e["p"]))
                if "hi" in e:
                    self.assertTrue(e["hi"]["n"].startswith("up to"), (c["id"], e["p"]))
                self.assertEqual(e["f"]["s"], "atlas")
                if c.get("portwatch") and not c.get("portwatchLabel"):
                    pw = portwatch(c["id"]).get(YEAR, {}).get("tanker" if e["p"] in TANKER else "dry")
                    if pw is not None and e["mt"][0] <= pw:
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
        r = next(x for x in load_json(os.path.join(FREIGHT, "routes.json")) if x["id"] == "kozmino-china-espo")
        self.assertNotIn("shareNa", r)
        v = next(h["v"] for h in r["history"] if h["y"] == YEAR)
        self.assertAlmostEqual(v, 108.5, delta=0.5)
        sea = load_json(os.path.join(PAIRS, "crude-oil.json"))["seaborne"] / 1e3
        self.assertAlmostEqual(r["shares"][0]["f"]["v"], 100 * v / sea, delta=0.06)
        self.assertRegex(r["shares"][0]["f"]["n"], r"split (is )?not known")
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
        for path in (os.path.join(ROOT, "pipeline", "freight", "alerts.json"), os.path.join(FREIGHT, "alerts.json")):
            a = next(x for x in load_json(path) if x["id"] == "hormuz-2026")
            self.assertIn("phosphate", a["commodities"])
        notes = " ".join(x.get("note", "") for x in chokepoint("hormuz")["alternatives"])
        self.assertNotIn("4.7 mb/d", notes)
        self.assertIn("7,000 kb/d", notes)
        self.assertIn("1,500 kb/d", notes)

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
        self.assertEqual(len(rs), 103)
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

    def test_profiles_have_index_codes_only(self):
        idx = {c["c"] for c in load_json(os.path.join(ROOT, "data", "countries", "index.json"))}
        prof = load_json(os.path.join(ROOT, "data", "countries", "profiles.json"))
        keys = set(prof) if isinstance(prof, dict) else {p["c"] for p in prof}
        self.assertEqual(keys - idx - {"EU27"}, set())  # EU27: USDA PSD reports the Union as one trader


if __name__ == "__main__":
    unittest.main()
