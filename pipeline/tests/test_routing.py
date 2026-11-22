"""Unit tests of the sea router (pipeline/freight/routing.py) and of the draught rule of vessel_rules.py.

Tests R01 to R13 of the engine plan. Ports are taken at their ports.port() coordinates; "SO" means the
southern-ocean region is forbidden, as plan() always does.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "freight"))

import ports as P  # noqa: E402
import routing as RT  # noqa: E402
import vessel_rules as VR  # noqa: E402

SO = ("southern-ocean",)


def at(code):
    return P.port(code)["at"]


class R01Crossings(unittest.TestCase):
    def test_unwrapped_longitudes(self):
        self.assertEqual(RT.crossings([[280.1, 8.9], [280.5, 9.3]]), ["panama"])

    def test_vertex_on_gate_counts_once(self):
        self.assertEqual(RT.crossings([[19.0, -40.0], [20.03, -40.0], [21.0, -40.0]]), ["cape-good-hope"])
        self.assertEqual(RT.crossings([[21.0, -40.0], [20.03, -40.0], [19.0, -40.0]]), ["cape-good-hope"])

    def test_touch_and_turn_back(self):
        self.assertEqual(RT.crossings([[19.0, -40.0], [20.03, -40.0], [19.5, -41.0]]), [])
        self.assertEqual(RT.crossings([[21.0, -40.0], [20.03, -40.0], [21.5, -41.0]]), [])

    def test_order_and_antimeridian(self):
        # across the antimeridian (179 -> -179) and then through Panama, in either longitude form
        line = [[170.0, 10.0], [-179.0, 10.0], [-80.0, 8.0], [-79.5, 9.5]]
        self.assertEqual(RT.crossings(line), ["panama"])
        self.assertEqual(RT.crossings([[100.5, 2.0], [100.8, 3.0], [103.0, 1.2], [104.5, 1.1]]), ["malacca", "singapore"])


class R02Gates(unittest.TestCase):
    def test_every_gate_is_crossed_and_no_node_on_a_gate(self):
        M = RT.graph()
        counts = RT.gate_edge_counts()
        for gid in RT.GATES:
            self.assertGreaterEqual(counts.get(gid, 0), 1, gid)
        self.assertEqual(RT.nodes_on_gates(M), [])


class R03CapeOfGoodHope(unittest.TestCase):
    def test_santos_fremantle(self):
        r = RT.route(at("BRSSZ"), at("AUFRE"), SO)
        self.assertIn("cape-good-hope", r.via)
        self.assertAlmostEqual(r.nm, 8215, delta=100)

    def test_cape_town_auckland(self):
        r = RT.route(at("ZACPT"), at("NZAKL"), SO)
        self.assertIn("cape-good-hope", r.via)
        self.assertAlmostEqual(r.nm, 7670, delta=100)


class R04Restrictions(unittest.TestCase):
    def test_tubarao_qingdao(self):
        a, b = at("BRTUB"), at("CNTAO")
        free = RT.route(a, b)
        self.assertAlmostEqual(free.nm, 11137, delta=60)
        no_sunda = RT.route(a, b, ("sunda",))
        self.assertAlmostEqual(no_sunda.nm, 11313, delta=60)
        self.assertNotIn("sunda", no_sunda.via)
        no_west = RT.route(a, b, ("sunda", "malacca", "singapore"))
        self.assertAlmostEqual(no_west.nm, 11690, delta=60)
        self.assertTrue({"lombok", "makassar"} <= set(no_west.via))
        no_taiwan = RT.route(a, b, ("taiwan-strait",))
        self.assertAlmostEqual(no_taiwan.nm - free.nm, 99, delta=60)
        self.assertNotIn("taiwan-strait", no_taiwan.via)

    def test_forbidden_in_both_directions(self):
        # the package stores one attribute dictionary per direction: both must be forbidden
        a, b = at("BRTUB"), at("CNTAO")
        self.assertNotIn("sunda", RT.route(b, a, ("sunda",)).via)

    def test_tags_are_restored(self):
        a, b = at("BRTUB"), at("CNTAO")
        RT.route(a, b, ("sunda",))
        self.assertIn("sunda", RT.route(a, b).via)


class R05CapeHorn(unittest.TestCase):
    def test_horn_rule(self):
        self.assertFalse(RT.horn_allowed(at("BRSSZ"), at("JPCHB")))
        self.assertFalse(RT.horn_allowed(at("BRSSZ"), at("SAJED")))
        self.assertTrue(RT.horn_allowed(at("USHOU"), at("CLANF")))
        self.assertTrue(RT.horn_allowed(at("PECLL"), at("GRPIR")))
        self.assertTrue(RT.horn_allowed(at("PECLL"), at("RUNVS")))

    def test_santos_chiba(self):
        p = RT.plan(at("BRSSZ"), at("JPCHB"), ["kamsarmax", "supramax"])
        self.assertIn("cape-good-hope", p.main.via)
        self.assertNotIn("cape-horn", p.main.via)
        self.assertAlmostEqual(p.main.nm, 11822, delta=150)


class R06SuezAlternative(unittest.TestCase):
    def test_pivdennyi_qingdao(self):
        p = RT.plan(at("UAPIV"), at("CNTAO"), ["supramax"])
        for g in ("bosphorus", "suez", "bab-el-mandeb", "malacca", "singapore"):
            self.assertIn(g, p.main.via)
        self.assertAlmostEqual(p.main.nm, 8676, delta=200)
        self.assertTrue(p.alts)
        alt = p.alts[0]
        self.assertIn("cape-good-hope", alt["via"])
        self.assertNotIn("panama", alt["via"])
        self.assertAlmostEqual(alt["distanceNm"], 15221, delta=200)


class R07PanamaAlternatives(unittest.TestCase):
    def test_new_orleans_chiba(self):
        p = RT.plan(at("USMSY"), at("JPCHB"), ["kamsarmax"])
        self.assertIn("panama", p.main.via)
        self.assertAlmostEqual(p.main.nm, 9251, delta=150)
        self.assertEqual(len(p.alts), 2)
        self.assertIn("suez", p.alts[0]["via"])
        self.assertAlmostEqual(p.alts[0]["distanceNm"], 14503, delta=150)
        self.assertIn("cape-good-hope", p.alts[1]["via"])
        self.assertNotIn("suez", p.alts[1]["via"])
        self.assertAlmostEqual(p.alts[1]["distanceNm"], 15709, delta=150)
        self.assertTrue(p.alts[0].get("redSea"))


class R08Americas(unittest.TestCase):
    def test_houston_antofagasta(self):
        p = RT.plan(at("USHOU"), at("CLANF"), ["mr"])
        self.assertIn("panama", p.main.via)
        self.assertTrue(p.alts)
        self.assertIn("cape-horn", p.alts[0]["via"])
        self.assertAlmostEqual(p.alts[0]["distanceNm"], 9703, delta=150)
        self.assertIsNone(p.alt_note)

    def test_houston_puerto_quetzal(self):
        p = RT.plan(at("USHOU"), at("GTPRQ"), ["mr"])
        self.assertIn("panama", p.main.via)
        self.assertEqual(p.alts, [])
        self.assertTrue(p.alt_note)

    def test_no_suez_for_two_ports_of_the_americas(self):
        for a, b in (("USHOU", "CLANF"), ("USHOU", "GTPRQ"), ("USMSY", "PECLL")):
            p = RT.plan(at(a), at(b), ["mr"])
            for alt in p.alts:
                self.assertNotIn("suez", alt["via"], (a, b))


class R09SouthernOcean(unittest.TestCase):
    def test_rosario_ho_chi_minh(self):
        p = RT.plan(at("ARUPR"), at("VNSGN"), ["kamsarmax", "supramax"])
        low = min(y for _, y in p.main.coords)
        self.assertGreater(low, -42.5)
        self.assertAlmostEqual(p.main.nm, 10118, delta=100)


class R10Parallel(unittest.TestCase):
    def test_tubarao_qingdao(self):
        p = RT.plan(at("BRTUB"), at("CNTAO"), ["vloc", "capesize"])
        self.assertEqual(p.via, ["cape-good-hope"])
        self.assertEqual(len(p.via_alt), 2)
        self.assertTrue({"sunda", "malacca", "lombok"} <= set(p.via_alt[0]))
        self.assertEqual(set(p.via_alt[1]), {"taiwan-strait", "luzon"})

    def test_ras_tanura_ningbo(self):
        p = RT.plan(at("SARTA"), at("CNNGB"), ["vlcc", "suezmax"])
        for g in ("hormuz", "malacca", "singapore"):
            self.assertIn(g, p.via)
        self.assertEqual([set(x) for x in p.via_alt], [{"taiwan-strait", "luzon"}])

    def test_port_hedland_qingdao(self):
        p = RT.plan(at("AUPHE"), at("CNTAO"), ["capesize"])
        self.assertIn("lombok", p.via)
        self.assertIn("makassar", p.via)

    def test_samarinda_paradip(self):
        p = RT.plan(at("IDSRI"), at("INPRT"), ["supramax"])
        self.assertIn("malacca", p.via)
        self.assertEqual(p.via_alt, [])

    def test_vloc_main_route_respects_draught(self):
        p = RT.plan(at("BRTUB"), at("CNTAO"), ["vloc", "capesize"])
        self.assertFalse({"sunda", "malacca", "singapore", "torres"} & set(p.main.via))

    def test_thresholds_are_parameters(self):
        p = RT.plan(at("SARTA"), at("CNNGB"), ["vlcc", "suezmax"])
        via, via_alt = RT.classify(p.main.via, p.parallel, p.classes, 0.0, 0)
        self.assertIn("taiwan-strait", via)
        self.assertEqual(via_alt, [])


class R11Draught(unittest.TestCase):
    def test_avoids(self):
        self.assertTrue({"malacca", "singapore", "sunda", "torres"} <= VR.avoids("vloc"))
        self.assertIn("torres", VR.avoids("capesize"))
        self.assertNotIn("sunda", VR.avoids("capesize"))
        self.assertEqual(VR.avoids("no-such-class"), set())

    def test_sources(self):
        for table, src in ((VR.DRAUGHT_M, VR.DRAUGHT_SRC), (VR.PASSAGE_LIMIT_M, VR.PASSAGE_LIMIT_SRC)):
            self.assertEqual(set(table), set(src))
            for k in table:
                self.assertTrue(isinstance(src[k], str) and src[k].startswith("https://"), k)

    def test_limits_are_gates(self):
        self.assertLessEqual(set(VR.PASSAGE_LIMIT_M), set(RT.GATES))

    def test_malacca_in_step_with_chokepoint_text(self):
        root = os.path.join(HERE, "..", "freight", "chokepoints.json")
        text = next(c.get("limits", "") for c in json.load(open(root)) if c["id"] == "malacca")
        self.assertIn(f"{VR.PASSAGE_LIMIT_M['malacca']} m", text)


class R12CacheVersion(unittest.TestCase):
    def test_stale_cache_is_ignored_and_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "route_cache.json")
            json.dump({"_v": "old", "a|b": {"nm": 1}}, open(path, "w"))
            data = RT.load_cache(path)
            self.assertEqual(data, {"_v": RT.VERSION})
            data["c|d"] = {"nm": 2}
            RT.save_cache(path, data)
            again = json.load(open(path))
            self.assertEqual(again["_v"], RT.VERSION)
            self.assertEqual(RT.load_cache(path)["c|d"], {"nm": 2})

    def test_missing_or_broken_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(RT.load_cache(os.path.join(tmp, "none.json")), {"_v": RT.VERSION})
            bad = os.path.join(tmp, "bad.json")
            open(bad, "w").write("{")
            self.assertEqual(RT.load_cache(bad), {"_v": RT.VERSION})

    def test_version_follows_the_tables(self):
        self.assertEqual(RT.VERSION, RT.version())
        old = VR.DRAUGHT_M.get("capesize")
        VR.DRAUGHT_M["capesize"] = 99.0
        try:
            self.assertNotEqual(RT.version(), RT.VERSION)
        finally:
            VR.DRAUGHT_M["capesize"] = old


class R13NoPath(unittest.TestCase):
    def test_silent_none(self):
        out, err = io.StringIO(), io.StringIO()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                r = RT.route(at("SARTA"), at("CNNGB"), ("hormuz",))
        self.assertIsNone(r)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(w, [])

    def test_plan_falls_back(self):
        # a VLOC cannot reach Singapore under the draught rule: plan() drops the last restriction instead
        p = RT.plan(at("BRTUB"), at("SGSIN"), ["vloc"])
        self.assertIsNotNone(p)
        self.assertGreater(p.main.nm, 0)


if __name__ == "__main__":
    unittest.main()
