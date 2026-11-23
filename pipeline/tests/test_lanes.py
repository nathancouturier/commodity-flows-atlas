"""Data tests of the trade-engine plan for package E5-lanes: lane selection (S01 to S08), the pairs table (P01 to
P08), and the lane form of the mode (M01, M03, M04, M08), gateway (G01 to G10), customs (D04, D08, D09, D12, D14)
and caveat (V01, V03) tests. They read the files written by pipeline/freight/build_lanes.py.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
Each test is skipped when the files of the build are absent (a tree on which build_lanes.py has not run yet).
"""
import gzip
import importlib
import json
import math
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("freight", "trade", "geo", "commodities"):
    p = os.path.join(ROOT, "pipeline", sub)
    if p not in sys.path:
        sys.path.insert(0, p)

LANES = os.path.join(ROOT, "data", "freight", "lanes")
PAIRS = os.path.join(ROOT, "data", "freight", "pairs")
YEAR = 2024
FOOD = ("wheat", "corn", "soybeans", "soymeal", "rice", "sugar", "rapeseed", "palm-oil", "soyoil", "potash", "urea",
        "dap", "phosphate-rock")
FLOOR = {"coffee": 0.02, "cocoa": 0.02, "cotton": 0.02, "nickel-int": 0.02, "copper-refined": 0.02, "zinc-ore": 0.02,
         "aluminium": 0.03, "soyoil": 0.03}
BUILT = os.path.isdir(PAIRS) and os.path.exists(os.path.join(ROOT, "data", "freight", "caveats.json"))
need_build = unittest.skipUnless(BUILT, "build_lanes.py has not written the pairs files yet")

_cache = {}


def load_json(path):
    if path not in _cache:
        with open(path, encoding="utf-8") as f:
            _cache[path] = json.load(f)
    return _cache[path]


def lane_file(group):
    return load_json(os.path.join(LANES, group + ".json"))


def pairs_file(group):
    return load_json(os.path.join(PAIRS, group + ".json"))


def groups():
    return sorted(f[:-5] for f in os.listdir(LANES) if f.endswith(".json"))


def lane(lid):
    group = lid.split(":")[0]
    for ln in lane_file(group)["lanes"]:
        if ln["id"] == lid:
            return ln
    return None


def main_lanes(group):
    return [ln for ln in lane_file(group)["lanes"] if ln["set"] == "main"]


def row(group, o, d):
    p = pairs_file(group)
    c = p["cols"]
    for r in p["rows"]:
        if r[0] == o and r[1] == d:
            return dict(zip(c, r))
    return None


def mask_gates(p, mask):
    return {g for i, g in enumerate(p["gates"]) if mask >> i & 1}


def seaborne(group, year=YEAR):
    f = lane_file(group)
    return f["seaborne"][f["years"].index(year)]


def hist(ln, year):
    f = lane_file(ln["p"])
    return ln["hist"][f["years"].index(year)]


def gc_km(a, b):
    p = math.pi / 180
    return 6371 * 2 * math.asin(math.sqrt(math.sin((b[1] - a[1]) * p / 2) ** 2
                                          + math.cos(a[1] * p) * math.cos(b[1] * p) * math.sin((b[0] - a[0]) * p / 2) ** 2))


@need_build
class Selection(unittest.TestCase):
    def test_S01_coverage_per_group(self):
        want = {"crude-oil": 0.78, "refined-products": 0.58, "steel": 0.65, "wheat": 0.78, "lng": 0.88, "lpg": 0.87,
                "coal": 0.93, "iron-ore": 0.93, "urea": 0.79, "rice": 0.73, "corn": 0.89, "soybeans": 0.93, "dap": 0.83}
        low = {}
        for g in groups():
            f = lane_file(g)
            cov = f["coverage"]["share"]
            s = sum(ln["flow"]["v"] for ln in main_lanes(g) if ln.get("mode") != "mixed") / seaborne(g)
            self.assertAlmostEqual(cov, s, delta=0.002, msg=g)
            if cov < want.get(g, 0.63):
                low[g] = round(cov, 3)
        self.assertEqual(low, {}, "groups below their coverage floor")

    def test_S02_coverage_all_groups(self):
        on = sum(ln["flow"]["v"] for g in groups() for ln in main_lanes(g) if ln.get("mode") != "mixed")
        tot = sum(seaborne(g) for g in groups())
        self.assertGreaterEqual(on / tot, 0.83)

    def test_S03_floor(self):
        under = [ln["id"] for g in groups() for ln in main_lanes(g) if ln["flow"]["v"] < FLOOR.get(g, 0.05) - 1e-9]
        self.assertEqual(under, [])

    def test_S04_large_pairs_in_main_set(self):
        want = [("crude-oil:USA-GBR", 16.94), ("crude-oil:SAU-TWN", 14.40), ("crude-oil:KAZ-ITA", 15.38),
                ("crude-oil:COL-PAN", 8.11), ("refined-products:RUS-BRA", 9.10), ("refined-products:IND-NLD", 8.33),
                ("refined-products:MYS-CHN", 8.26), ("refined-products:ITA-GIB", 3.84), ("lng:USA-IND", 4.72),
                ("lng:USA-DEU", 3.20), ("lng:RUS-CHN", 8.28), ("urea:OMN-BRA", 1.61), ("urea:NGA-BRA", 1.59),
                ("iron-ore:BRA-OMN", 12.41), ("iron-ore:AUS-IDN", 9.82), ("iron-ore:IND-CHN", 35.24),
                ("wheat:ROU-SAU", 2.40), ("steel:CHN-ARE", 4.74), ("coal:USA-CHN", 12.09), ("coal:CAN-CHN", 9.53),
                ("coal:MOZ-IND", 8.03)]
        missing = []
        for lid, v in want:
            ln = lane(lid)
            if not ln or ln["set"] != "main":
                missing.append(lid)
                continue
            self.assertAlmostEqual(ln["flow"]["v"], v, delta=0.01, msg=lid)
        self.assertEqual(missing, [])
        # potash UZB-BRA: only when a transit port is sourced for Uzbekistan
        import ports
        if "UZB" in ports.TRANSIT:
            self.assertIsNotNone(lane("potash:UZB-BRA"))

    def test_S05_no_zero_lane(self):
        self.assertIsNone(lane("soybeans:PRY-CYM"))
        zero = [ln["id"] for g in groups() for ln in main_lanes(g) if ln["flow"]["v"] <= 0]
        self.assertEqual(zero, [])

    def test_S06_main_lanes_plus_rest_equal_seaborne(self):
        for g in groups():
            f = lane_file(g)
            s = sum(ln["flow"]["v"] for ln in main_lanes(g) if ln.get("mode") != "mixed") + sum(r["v"] for r in f["rest"])
            self.assertAlmostEqual(s, seaborne(g), delta=max(0.005 * seaborne(g), 0.01), msg=g)
            for r in f["rest"]:
                self.assertIn(set(r), ({"o", "v", "n"}, {"o", "v", "n", "est"}))
                if "est" in r:  # Mt of the remainder estimated by the atlas (review GE5, finding 2)
                    self.assertTrue(0 < r["est"] <= r["v"] + 0.001, (g, r))

    def test_S07_ids_sets_caps(self):
        import build_lanes as BL
        for g in groups():
            ls = lane_file(g)["lanes"]
            ids = [ln["id"] for ln in ls]
            self.assertEqual(len(ids), len(set(ids)), g)
            self.assertTrue(all(ln["set"] in ("main", "history") for ln in ls), g)
            self.assertLessEqual(len([ln for ln in main_lanes(g) if ln.get("mode") != "mixed"]), BL.CAP[g], g)
            self.assertLessEqual(len(ls), BL.CAP[g] + 80, g)

    def test_S08_totals(self):
        main = sum(1 for g in groups() for ln in main_lanes(g) if ln.get("mode") != "mixed")
        hist_ = sum(1 for g in groups() for ln in lane_file(g)["lanes"] if ln["set"] == "history")
        mixed = sum(1 for g in groups() for ln in main_lanes(g) if ln.get("mode") == "mixed")
        print(f"\nS08: main seaborne lanes {main}, history-only {hist_}, mixed {mixed}")
        self.assertTrue(2300 <= main <= 2450, main)
        self.assertTrue(150 <= hist_ <= 220, hist_)
        self.assertTrue(30 <= mixed <= 40, mixed)


@need_build
class Pairs(unittest.TestCase):
    def test_P01_one_row_per_pair(self):
        sys.path.insert(0, os.path.join(ROOT, "pipeline", "tests"))
        import test_modes
        df = test_modes.frame()
        y = df[df.year == YEAR]
        n = 0
        for g in groups():
            p = pairs_file(g)
            keys = [(r[0], r[1]) for r in p["rows"]]
            self.assertEqual(len(keys), len(set(keys)), g)
            self.assertEqual(set(keys), set(zip(y[y.group == g].o, y[y.group == g].d)), g)
            n += len(keys)
        print(f"\nP01: {n} rows")
        # 34 groups since the ferro-nickel and spodumene groups were added (23,739 rows with the first 32)
        self.assertTrue(23700 <= n <= 24100, n)

    def test_P02_seaborne_rows_routed(self):
        for g, o, d, kt, m in (("coal", "USA", "CHN", 12092, None), ("coal", "CAN", "CHN", 9529, None),
                               ("coal", "MOZ", "IND", 8026, None), ("crude-oil", "USA", "CHN", 10598, None),
                               ("refined-products", "IND", "NLD", 8331, None), ("lng", "USA", "DEU", 3205, None),
                               ("crude-oil", "KAZ", "ITA", 15377, 1)):
            r = row(g, o, d)
            self.assertIsNotNone(r, (g, o, d))
            self.assertIn(r["m"], (0, 1))
            if m is not None:
                self.assertEqual(r["m"], m)
            self.assertGreater(r["nm"], 0)
            self.assertGreaterEqual(r["cls"], 0)
            self.assertAlmostEqual(r["kt"], kt, delta=50, msg=(g, o, d))

    def test_P03_mixed_and_land_rows(self):
        r = row("coal", "RUS", "CHN")
        self.assertEqual(r["m"], 2)
        self.assertAlmostEqual(r["kt"], 95074, delta=50)
        r = row("coal", "MNG", "CHN")
        self.assertEqual((r["m"], r["nm"], r["load"]), (3, 0, -1))
        self.assertAlmostEqual(r["kt"], 82911, delta=50)

    def test_P04_seaborne_sum(self):
        for g in groups():
            p = pairs_file(g)
            s = sum(r[2] for r in p["rows"] if r[3] in (0, 1))
            self.assertAlmostEqual(s, p["seaborne"], delta=max(0.001 * p["seaborne"], 2), msg=g)
            self.assertAlmostEqual(p["seaborne"] / 1e3, seaborne(g), delta=0.01, msg=g)

    def test_P05_size(self):
        raw = gz = big = 0
        for g in groups():
            with open(os.path.join(PAIRS, g + ".json"), "rb") as f:
                b = f.read()
            raw += len(b)
            gz += len(gzip.compress(b, 9))
            big = max(big, len(b))
        print(f"\nP05: pairs folder {raw / 1024:.0f} KB raw, {gz / 1024:.0f} KB gzip, largest file {big / 1024:.0f} KB")
        self.assertLessEqual(raw, 1.5 * 1024 * 1024)
        self.assertLessEqual(big, 230 * 1024)
        self.assertLessEqual(gz, 380 * 1024)

    def test_P06_indexes_and_masks(self):
        cps = {c["id"] for c in load_json(os.path.join(ROOT, "data", "freight", "chokepoints.json"))}
        for g in groups():
            p = pairs_file(g)
            self.assertLessEqual(len(p["gates"]), 31)
            self.assertTrue(set(p["gates"]) <= cps, set(p["gates"]) - cps)
            self.assertEqual(p["cols"], ["o", "d", "kt", "m", "load", "dis", "nm", "cls", "via", "alt", "f"])
            n, nc, top = len(p["ports"]), len(p["classes"]), 2 ** len(p["gates"])
            for r in p["rows"]:
                self.assertTrue(-1 <= r[4] < n and -1 <= r[5] < n and -1 <= r[7] < nc, r)
                self.assertTrue(0 <= r[8] < top and 0 <= r[9] < top, r)
                self.assertIn(r[3], (0, 1, 2, 3), r)
                self.assertEqual(r[8] & r[9], 0, r)

    def test_P07_main_lanes_match_their_rows(self):
        for g in groups():
            p = pairs_file(g)
            for ln in main_lanes(g):
                r = row(g, ln["o"], ln["d"])
                self.assertIsNotNone(r, ln["id"])
                self.assertTrue(r["f"] & 4, ln["id"])
                # rows of 1 Mt or more are whole kt, lane flows are rounded to 1 kt: they agree within 1 kt
                self.assertAlmostEqual(r["kt"] / 1e3, ln["flow"]["v"], delta=0.0011, msg=ln["id"])
                self.assertEqual(r["nm"], ln["distanceNm"], ln["id"])
                self.assertEqual(mask_gates(p, r["via"]), set(ln["via"]), ln["id"])
                self.assertEqual(mask_gates(p, r["alt"]), {x for lst in ln.get("viaAlt", []) for x in lst}, ln["id"])
                self.assertEqual(p["ports"][r["load"]][0], ln["load"][0], ln["id"])
                self.assertEqual(p["ports"][r["dis"]][0], ln["discharge"][0], ln["id"])
            lanes = {(ln["o"], ln["d"]) for ln in main_lanes(g)}
            for r in p["rows"]:
                self.assertEqual(bool(r[10] & 4), (r[0], r[1]) in lanes, (g, r[0], r[1]))

    def test_P08_us_soybeans_philippines(self):
        import ports
        if len({c for c, z in ports._cands("USA", "soybeans", "load")}) < 2:
            self.skipTest("the United States has one grain gateway")
        p = pairs_file("soybeans")
        r = row("soybeans", "USA", "PHL")
        self.assertIsNotNone(r)
        self.assertNotIn("panama", mask_gates(p, r["via"]))
        self.assertIn("panama", mask_gates(p, r["alt"]))


@need_build
class ModeLanes(unittest.TestCase):
    def test_M01_india_china_iron_ore(self):
        ln = lane("iron-ore:IND-CHN")
        self.assertIsNotNone(ln)
        self.assertEqual(ln["set"], "main")
        self.assertAlmostEqual(ln["flow"]["v"], 35.243, delta=0.01)

    def test_M03_land_pairs(self):
        for g, o, d, kt in (("crude-oil", "NLD", "BEL", 29520), ("refined-products", "NLD", "DEU", 17060),
                            ("wheat", "FRA", "BEL", 2540), ("steel", "DEU", "POL", 3030)):
            r = row(g, o, d)
            self.assertEqual(r["m"], 3, (g, o, d))
            self.assertAlmostEqual(r["kt"], kt, delta=20, msg=(g, o, d))
            self.assertIsNone(lane(f"{g}:{o}-{d}"))

    def test_M04_mixed_lanes(self):
        for lid, v in (("crude-oil:RUS-CHN", 108.47), ("coal:RUS-CHN", 95.07)):
            ln = lane(lid)
            self.assertIsNotNone(ln, lid)
            self.assertEqual(ln.get("mode"), "mixed", lid)
            self.assertIsNone(ln["share"], lid)
            self.assertEqual(ln["set"], "main")
            self.assertAlmostEqual(ln["flow"]["v"], v, delta=0.05, msg=lid)
        f = lane_file("coal")
        i = f["years"].index(YEAR)
        self.assertTrue(1370 <= f["seaborne"][i] <= 1380, f["seaborne"][i])
        self.assertAlmostEqual(f["mixed"][i], 95.07, delta=0.1)

    def test_M08_transit(self):
        ln = lane("crude-oil:KAZ-ITA")
        self.assertIsNotNone(ln)
        self.assertEqual(ln["transit"]["port"], "KZCPC")
        self.assertEqual(ln["transit"]["c"], "RUS")
        self.assertTrue(ln["transit"]["s"])
        self.assertNotIn("mode", ln)
        self.assertEqual(row("crude-oil", "KAZ", "ITA")["m"], 1)
        for g in groups():
            for x in lane_file(g)["lanes"]:
                if "transit" in x:
                    self.assertTrue(x["transit"].get("s") and x["transit"].get("url"), x["id"])


@need_build
class GatewayLanes(unittest.TestCase):
    def test_G01_no_food_on_oil_terminals(self):
        bad = {"SARTA", "IQBOT", "NGBON", "DZAZW", "TRCEY", "AUPHE", "IDBPN", "USCRP"}
        hits = {}
        for g in FOOD:
            for ln in lane_file(g)["lanes"]:
                for code in bad & set(ln["load"] + ln["discharge"]):
                    hits.setdefault(ln["o"] if code in ln["load"] else ln["d"], set()).add(ln["id"])
        # Algeria and Iraq: no page naming their food import ports was read (UNSOURCED of gateways/food.py), so they keep
        # their present port. Any other country is a regression.
        import gateways.food as food
        known = {c for c in hits if c in food.UNSOURCED}
        print(f"\nG01: food lanes still at an oil terminal, for want of a sourced row: "
              f"{ {c: len(v) for c, v in hits.items() if c in known} }")
        self.assertEqual({c: sorted(v) for c, v in hits.items() if c not in known}, {})

    def test_G02_lng_terminals(self):
        feats = load_json(os.path.join(ROOT, "data", "infrastructure", "lng.geojson"))["features"]
        term = {}
        for f in feats:
            term.setdefault((f["properties"]["c"], f["properties"]["type"]), []).append(f["geometry"]["coordinates"])
        f = lane_file("lng")
        far = []
        for ln in f["lanes"]:
            for code, c, kind in ((ln["load"][0], ln["o"], "lng-export"), (ln["discharge"][0], ln["d"], "lng-import")):
                pts = term.get((c, kind))
                if not pts:
                    continue
                at = f["ports"][code]["at"]
                if min(gc_km(at, p) for p in pts) > 50:
                    far.append((ln["id"], code))
        self.assertEqual(far, [])

    def test_G03_us_wheat_japan(self):
        import ports
        ln = lane("wheat:USA-JPN")
        self.assertIsNotNone(ln)
        self.assertEqual(ln["load"][0], ports.gateway("USA", "wheat", "load"))
        self.assertAlmostEqual(ln["distanceNm"], 9251, delta=150)
        self.assertTrue(any(o["nm"] <= 4500 for o in ln.get("opts", [])), ln.get("opts"))
        self.assertNotIn("panama", ln["via"])
        self.assertIn("panama", {x for lst in ln.get("viaAlt", []) for x in lst})

    def test_G04_canadian_potash_belgium(self):
        ln = lane("potash:CAN-BEL")
        self.assertIsNotNone(ln)
        self.assertLessEqual(ln["distanceNm"], 3500)
        self.assertNotIn("panama", ln["via"])

    def test_G05_uae_crude_japan(self):
        ln = lane("crude-oil:ARE-JPN")
        self.assertIsNotNone(ln)
        loads = {ln["load"][0]} | {o["load"] for o in ln.get("opts", [])}
        self.assertGreaterEqual(len(loads), 2, loads)
        zones = {lane_file("crude-oil")["ports"].get(c, {}).get("zone") for c in loads}
        self.assertIn("meg", zones)
        self.assertIn("hormuz", {x for lst in ln.get("viaAlt", []) for x in lst})
        self.assertIn("iran-war-hormuz-2026", {s["event"] for s in ln.get("status", [])})

    def test_G06_products_into_australia_and_indonesia(self):
        for lid, port in (("refined-products:KOR-AUS", "AUPHE"), ("refined-products:SGP-AUS", "AUPHE"),
                          ("refined-products:SGP-IDN", "IDBPN")):
            ln = lane(lid)
            if ln:
                self.assertNotEqual(ln["discharge"][0], port, lid)

    def test_G07_brazilian_load_ports(self):
        loads = {ln["load"][0] for g in groups() for ln in lane_file(g)["lanes"] if ln["o"] == "BRA"}
        self.assertGreaterEqual(len(loads), 3, loads)
        import ports
        if ports.gateway("BRA", "alumina", "load") != "BRTUB":
            for g in ("alumina", "bauxite"):
                for ln in lane_file(g)["lanes"]:
                    if ln["o"] == "BRA":
                        self.assertNotEqual(ln["load"][0], "BRTUB", ln["id"])

    def test_G08_mexican_concentrates(self):
        import ports
        sourced = [g for g in ("copper-ore", "zinc-ore") if ports.ocean_of(ports.gateway("MEX", g, "load") or "") == "pacific"]
        if not sourced:
            self.skipTest("no sourced Pacific gateway for Mexican concentrates (package E4b)")
        for g in sourced:  # a group without a sourced Pacific row keeps its present port
            for d in ("CHN", "JPN", "KOR"):
                ln = lane(f"{g}:MEX-{d}")
                if ln:
                    self.assertNotIn("panama", ln["via"], ln["id"])

    def test_G09_two_oceans(self):
        bad = []
        import ports
        ln = lane("refined-products:USA-GTM")
        # Guatemala has no sourced Caribbean gateway for refined products yet (package E4b report): skip until it has
        if ln and "panama" in ln["via"] and ports.ocean_of(ports.gateway("GTM", "refined-products", "discharge") or "") == "atlantic":
            bad.append(ln["id"])
        for lid in ("crude-oil:COL-PAN", "crude-oil:GUY-PAN", "crude-oil:NGA-CAN", "crude-oil:AGO-CAN"):
            ln = lane(lid)
            if ln and {"panama", "cape-horn"} & set(ln["via"]):
                bad.append(lid)
        # The bound of 25 Mt predates the reviewed rule that opens Cape Horn to the South Pacific (routing.horn_allowed):
        # a pair with an end on the South Pacific is left out, the bound holds for the rest.
        import routing
        horn = horn_sp = 0.0
        for g in groups():
            p = pairs_file(g)
            if "cape-horn" not in p["gates"]:
                continue
            bit = 1 << p["gates"].index("cape-horn")
            for r in p["rows"]:
                if r[3] in (0, 1) and r[8] & bit:
                    ends = (ports.port(p["ports"][r[4]][0])["at"], ports.port(p["ports"][r[5]][0])["at"])
                    if any(routing.south_pacific(a) for a in ends):
                        horn_sp += r[2] / 1e3
                    else:
                        horn += r[2] / 1e3
        print(f"\nG09: seaborne tonnage with cape-horn in via: {horn:.1f} Mt, plus {horn_sp:.1f} Mt with an end on the "
              f"South Pacific; lanes still crossing: {bad}")
        self.assertEqual(bad, [])
        self.assertLessEqual(horn, 25)

    def test_G10_port_tables_and_zones(self):
        sources = {s["id"] for s in load_json(os.path.join(ROOT, "data", "sources.json"))}
        zones = load_json(os.path.join(ROOT, "data", "freight", "zones.json"))
        zid = {z["id"] for z in zones}
        self.assertGreaterEqual(len(zid), 20)
        import ports
        for rows in ports.G.values():
            for r in rows:
                self.assertIn(r.zone, zid, r)
        unsourced = set()
        for g in groups():
            for code, p in lane_file(g)["ports"].items():
                self.assertIn("zone", p, code)
                self.assertIn("s", p, code)
                if p["s"]:
                    self.assertIn(p["s"], sources, code)
                    if p["s"] == "wikipedia":
                        self.assertTrue(p.get("url"), code)
                else:
                    unsourced.add(code)
                if p["zone"]:
                    self.assertIn(p["zone"], zid, code)
        print(f"\nG10: {len(unsourced)} lane ports come from the legacy table and carry no source yet")


@need_build
class CustomsLanes(unittest.TestCase):
    def test_D04_bauxite_guinea_china_2023_estimate(self):
        import clean
        ln = lane("bauxite:GIN-CHN")
        if clean.BULK_REPAIR == "estimate":
            self.assertTrue(90 <= hist(ln, 2023) <= 110, hist(ln, 2023))
            self.assertEqual(ln["histFlags"]["2023"], "est")
            self.assertIn("Atlas estimate", ln["histNotes"]["2023"])
            self.assertGreaterEqual(seaborne("bauxite", 2023), 150)
        else:
            self.assertIsNone(hist(ln, 2023))
            self.assertEqual(ln["histFlags"]["2023"], "suspect")
            self.assertTrue(74 <= seaborne("bauxite", 2023) <= 76)
        self.assertIn("2023", lane_file("bauxite")["yearNotes"])

    def test_D08_history_kept(self):
        for lid, year, v in (("crude-oil:LBY-ITA", 2011, 4.85), ("crude-oil:LBY-ITA", 2020, 3.50),
                             ("iron-ore:UKR-CHN", 2023, 0.66), ("lng:USA-BRA", 2021, 5.76)):
            ln = lane(lid)
            if not ln:
                continue
            self.assertAlmostEqual(hist(ln, year), v, delta=0.01, msg=(lid, year))
            self.assertEqual(ln["histFlags"].get(str(year)), "kept", (lid, year))

    def test_D09_no_record(self):
        ln = lane("crude-oil:SAU-JPN")
        self.assertIsNone(hist(ln, 2015))
        self.assertEqual(ln["histFlags"]["2015"], "nodata")

    def test_D10_no_provisional_key(self):
        for g in groups():
            for path in (os.path.join(LANES, g + ".json"), os.path.join(PAIRS, g + ".json")):
                with open(path, encoding="utf-8") as f:
                    self.assertNotIn('"provisional"', f.read(), path)
        p = pairs_file("corn")
        r = row("corn", "USA", "MEX")
        self.assertTrue(r["f"] & 8)

    def test_D12_k2_on_the_lane(self):
        ln = lane("wheat:RUS-EGY")
        self.assertEqual(ln["histFlags"].get("2018"), "check")
        self.assertIn("USDA PSD", ln["histNotes"]["2018"])

    def test_D14_estimated_flow(self):
        ln = lane("wheat:RUS-EGY")
        fl = ln["flow"]
        self.assertTrue(fl.get("est"))
        self.assertEqual(fl["s"], "atlas")
        self.assertAlmostEqual(fl["v"], 11.056, delta=0.001)
        self.assertIn("Atlas estimate", fl["n"])
        self.assertIn("USD", fl["n"])
        self.assertNotIn("shareDest", ln)
        self.assertEqual(ln["histFlags"].get("2023"), "est")
        self.assertEqual(ln["histFlags"].get("2024"), "est")
        # `est` is a share of seaborne tonnes (plan 2.2); the plan's 0.064 is the share of all wheat tonnage (2.7 G7),
        # and the seaborne share of the same rows is 0.080
        self.assertTrue(0.05 <= lane_file("wheat")["est"] <= 0.09, lane_file("wheat")["est"])
        p = pairs_file("wheat")
        self.assertTrue(row("wheat", "RUS", "EGY")["f"] & 1)
        # every estimated flow says so, and only estimated flows carry "est"; a group that is an Atlas estimate by
        # construction (spodumene, review GR1.2) has the source id "atlas" and its method on every flow
        import build_lanes as BL
        for g in groups():
            for x in lane_file(g)["lanes"]:
                if x["flow"].get("est") or g in BL.EST_GROUP:
                    self.assertEqual(x["flow"]["s"], "atlas", x["id"])
                    self.assertTrue(x["flow"]["n"].startswith("Atlas estimate"), x["id"])
                else:
                    self.assertEqual(x["flow"]["s"], "baci", x["id"])


@need_build
class CaveatLanes(unittest.TestCase):
    def caveats(self):
        return load_json(os.path.join(ROOT, "data", "freight", "caveats.json"))

    def test_V01_malaysia_crude(self):
        ln = lane("crude-oil:MYS-CHN")
        self.assertAlmostEqual(ln["flow"]["v"], 41.503, delta=0.01)
        text = self.caveats()[ln["caveat"]]["text"]
        self.assertIn("54.2", text)
        self.assertIn("23.9", text)
        self.assertIn("plausible", text)

    def test_V03_caveated_origins(self):
        seen = set()
        for g, o in (("wheat", "RUS"), ("urea", "OMN"), ("potash", "BLR"), ("potash", "UZB"), ("potash", "TKM")):
            for ln in lane_file(g)["lanes"]:
                if ln["o"] == o:
                    self.assertIn(ln.get("caveat"), self.caveats(), ln["id"])
                    seen.add((g, o))
        self.assertTrue({("wheat", "RUS"), ("urea", "OMN")} <= seen, seen)

    def test_caveat_ids_and_pair_bit(self):
        cv = self.caveats()
        for g in groups():
            p = pairs_file(g)
            for ln in lane_file(g)["lanes"]:
                if "caveat" in ln:
                    self.assertIn(ln["caveat"], cv, ln["id"])
                    r = row(g, ln["o"], ln["d"])  # a history lane may have no row in the latest year
                    if r:
                        self.assertTrue(r["f"] & 2, ln["id"])


@need_build
class ReviewGE5(unittest.TestCase):
    """Regression tests of the independent review of the lane builder (group GE5) and of its follow-ups (package FE5)."""

    def test_GE5_1_one_of_lists_are_parallel_passages(self):
        import routing
        par = [set().union(*grp) for grp in routing.PARALLEL]
        bad = [(ln["id"], lst) for g in groups() for ln in lane_file(g)["lanes"] for lst in ln.get("viaAlt", [])
               if len(lst) > 1 and not any(set(lst) <= p for p in par)]
        self.assertEqual(bad, [])
        ln = lane("soybeans:USA-IDN")
        if ln:
            for gate in ("gibraltar", "suez", "panama"):
                if gate in {x for lst in ln["viaAlt"] for x in lst}:
                    self.assertIn([gate], ln["viaAlt"], gate)

    def test_GE5_1_combine(self):
        import build_lanes as BL
        a = {"via": ["gibraltar", "suez", "bab-el-mandeb", "sunda"], "viaAlt": [["sunda", "malacca"]]}
        b = {"via": ["panama", "torres"], "viaAlt": []}
        via, lists = BL.combine([a, b])
        self.assertEqual(via, [])
        self.assertIn(["sunda", "malacca"], lists)
        for gate in ("gibraltar", "suez", "bab-el-mandeb", "panama", "torres"):
            self.assertIn([gate], lists)

    def test_GE5_2_estimates_in_the_totals_are_marked(self):
        import build_lanes as BL
        for g in groups():
            f = lane_file(g)
            self.assertEqual(len(f["estY"]), len(f["years"]), g)
            first = BL.FIRST_YEAR.get(g, (f["years"][0],))[0]
            for y, s in zip(f["years"], f["estY"]):
                if y < first:  # a group whose reading starts late (spodumene, review GR1.2) has no figure before
                    self.assertIsNone(s, (g, y))
                    continue
                self.assertTrue(0 <= s <= 1, (g, y, s))
                if s >= BL.EST_NOTE_MIN:
                    self.assertIn("of Atlas estimates (", f["yearNotes"].get(str(y), ""), (g, y))
            i = f["years"].index(f["y"])
            self.assertAlmostEqual(f["estY"][i], f["est"], delta=0.0006, msg=g)
        w = lane_file("wheat")
        self.assertTrue(0.06 <= w["estY"][w["years"].index(2023)] <= 0.07)
        self.assertIn("Includes 11 Mt of Atlas estimates", w["yearNotes"]["2023"])
        self.assertTrue(any("est" in r for g in groups() for r in lane_file(g)["rest"]))

    def test_GE5_3_caveats_survive_a_missing_raw_folder(self):
        import tempfile
        import build_lanes as BL
        import caveats as CV
        import checks as K
        sys.path.insert(0, os.path.join(ROOT, "pipeline", "tests"))
        import test_modes
        df = test_modes.frame()
        previous = load_json(os.path.join(ROOT, "data", "freight", "caveats.json"))
        with tempfile.TemporaryDirectory() as empty:
            ran = set()
            findings = K.run(df, YEAR, raw=empty, ran=ran)
            self.assertFalse(ran & K.RAW_CHECKS)
            fresh = CV.build(df, findings, YEAR, psd=None)
            kept = BL.keep_caveats(fresh, previous, ran)
            self.assertEqual(BL.previous_caveats(os.path.join(empty, "caveats.json")), {})
        for cid, e in previous.items():
            if e.get("check") in K.RAW_CHECKS:
                self.assertIn(cid, kept, cid)
                self.assertEqual(kept[cid], e)
        self.assertTrue(set(fresh) <= set(kept))
        # with every check run, nothing is kept from the previous file
        self.assertEqual(BL.keep_caveats(fresh, previous, set(K.RAW_CHECKS)), fresh)

    def test_GE5_4_mozambique_south_africa_is_pipeline_gas(self):
        self.assertIsNone(lane("lng:MOZ-ZAF"))
        r = row("lng", "MOZ", "ZAF")
        if r:
            self.assertEqual(r["m"], 3)

    def test_GE5_6_F9_port_sources_follow_the_cargo(self):
        import ports
        weak = {ports.BASIS_LEGACY, ports.BASIS_NEAREST}
        for g in groups():
            f = lane_file(g)
            for code, p in f["ports"].items():
                self.assertIn(p["basis"], ports.BASES, (g, code))
                if p["basis"] in weak:
                    self.assertIsNone(p["s"], (g, code))
                    self.assertNotIn("url", p, (g, code))
                if g != "lng":
                    self.assertFalse("giignl" in (p.get("url") or ""), (g, code))
            for ln in f["lanes"]:
                for key in ("transit", "transit2"):
                    t = ln.get(key)
                    if t and f["ports"][t["port"]]["basis"] not in weak:
                        self.assertTrue(f["ports"][t["port"]]["s"], (ln["id"], key))

    def test_GE5_7_history_years_follow_the_latest_year(self):
        import build_lanes as BL
        self.assertEqual(BL.hist_years(2024), (2005, 2010, 2015, 2019, 2021, 2022, 2023))
        self.assertEqual(BL.hist_years(2025)[-3:], (2022, 2023, 2024))

    def test_GE5_8_display_names(self):
        import checks as K
        self.assertEqual((K.label("lpg"), K.cap_label("lng"), K.cap_label("crude-oil")), ("LPG", "LNG", "Crude oil"))
        for g in ("lpg", "lng"):
            text = json.dumps(lane_file(g), ensure_ascii=False)
            for bad in ("Lpg", "Lng", "of lpg", "of lng"):
                self.assertNotIn(bad, text, (g, bad))

    def test_GE5_9_F8_two_landlocked_ends(self):
        import build_lanes as BL
        ln = lane("crude-oil:KAZ-AUT")
        if ln:
            self.assertEqual(ln["transit"]["port"], "KZCPC")
            self.assertEqual(ln["transit2"]["port"], "ITTRS")
            self.assertTrue(ln["transit2"]["s"] and ln["transit2"]["url"])
        rec, why = BL.route_pair("ZMB", "CHE", "copper-refined", 4.9e5, "transit")
        self.assertIsNone(why)
        self.assertEqual((rec["transit"]["port"], rec["transit2"]["port"]), ("TZDAR", "NLRTM"))
        self.assertEqual(rec["opts"][0], ("TZDAR", "NLRTM"))
        # a landlocked end with no sourced transit port stays unrouted
        self.assertEqual(BL.route_pair("AZE", "SVK", "crude-oil", 1.7e5, "transit"), (None, "no sourced transit port"))
        # a coast with no port of its own goes through its TRANSIT port (Bosnia and Herzegovina, Ploce)
        rec, why = BL.route_pair("USA", "BIH", "coal", 6.9e5, "sea")
        self.assertIsNone(why)
        self.assertEqual(rec["opts"][0][1], "HRPLE")
        self.assertEqual(rec["transit"]["port"], "HRPLE")
        self.assertIsNone(rec["transit2"])
        r = row("coal", "USA", "BIH")
        self.assertGreaterEqual(r["load"], 0)
        self.assertEqual(pairs_file("coal")["ports"][r["dis"]][0], "HRPLE")

    def test_F1_modes_by_year(self):
        # LNG between neighbours counts as seaborne only from the year both terminals exist (Map Ta Phut, 2011)
        sys.path.insert(0, os.path.join(ROOT, "pipeline", "tests"))
        import modes
        import test_modes
        df = test_modes.frame()
        z = df[df.group == "lng"]
        f = lane_file("lng")
        for y in (2008, 2010, 2019, 2024):
            q = z[z.year == y]
            kinds = [modes.mode_of(o, d, "lng", y).kind for o, d in zip(q.o, q.d)]
            s = q.t[[k in ("sea", "transit") for k in kinds]].sum() / 1e6
            self.assertAlmostEqual(f["seaborne"][f["years"].index(y)], s, delta=0.01, msg=y)

    def test_F2_pairs_ports_carry_their_basis(self):
        import ports
        for g in groups():
            p = pairs_file(g)
            self.assertEqual(p["bases"], list(ports.BASES), g)
            for e in p["ports"]:
                # [code, name, country, zone, basis as a loading port, basis as a discharging port]
                self.assertEqual(len(e), 6, (g, e))
                self.assertTrue(e[4] is not None or e[5] is not None, (g, e))
                for b in e[4:6]:
                    self.assertTrue(b is None or 0 <= b < len(p["bases"]), (g, e))

    def test_F3_no_alt_on_lanes(self):
        self.assertEqual([ln["id"] for g in groups() for ln in lane_file(g)["lanes"] if "alt" in ln], [])

    def test_F7_notes_of_pairs_without_a_lane(self):
        n = 0
        for g in groups():
            p = pairs_file(g)
            notes = p.get("notes", {})
            keys = {f"{r[0]}-{r[1]}": r for r in p["rows"]}
            for k, text in notes.items():
                r = keys[k]
                self.assertTrue(r[10] & 9 and not r[10] & 4, (g, k))
                self.assertTrue(text, (g, k))
            for k, r in keys.items():
                if r[10] & 1 and not r[10] & 4:
                    self.assertTrue(notes.get(k, "").startswith("Atlas estimate"), (g, k))
                    n += 1
                if r[10] & 8 and not r[10] & 4:
                    self.assertIn(k, notes, (g, k))
        self.assertGreater(n, 100)


class Compatibility(unittest.TestCase):
    def test_builders_import(self):
        import build_lanes as BL
        for n in ("A2", "CACHE", "COMMODITY", "DISRUPTIONS", "LATEST_MIN_YEAR", "ROOT", "despike", "gateway", "km",
                  "routing", "save_geom_cache", "mode_of", "GROUPS"):
            self.assertTrue(hasattr(BL, n), n)
        self.assertEqual(BL.mode_of("KAZ", "ITA", "crude-oil"), "sea")
        self.assertEqual(BL.mode_of("NLD", "BEL", "crude-oil"), "land")
        self.assertEqual(BL.mode_of("RUS", "CHN", "coal"), "land")
        for name in ("build_freight", "build_commodities"):
            self.assertTrue(hasattr(importlib.import_module(name), "main"), name)
        self.assertFalse(hasattr(BL, "KNOWN_GAPS"))

    def test_routing_wrapper(self):
        import build_lanes as BL
        import ports
        a, b = ports.port("BRTUB")["at"], ports.port("CNTAO")["at"]
        coords, nm, via, alt = BL.routing(a, b, "vloc", 11.0)
        self.assertGreater(nm, 10000)
        self.assertIn("cape-good-hope", via)
        self.assertTrue(len(coords) > 5)
        # via = certain gates plus the first member of each "one of" list
        self.assertTrue({"sunda", "malacca", "lombok"} & set(via))


if __name__ == "__main__":
    unittest.main()
