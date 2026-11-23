"""Baltic benchmark routes: definitions, status, index membership (audit C-054, C-055, M-029, A-032, M-035).

The definitions were read by hand in the Baltic Exchange's Guide to Market Benchmarks (version 7.09), its dry, tanker and
gas service pages and its circulars (pipeline/freight/NOTES_routes.md). These tests hold the published file to them.
"""
import json
import os
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFS = os.path.join(ROOT, "pipeline", "freight", "routes_def.json")
INDICES = os.path.join(ROOT, "pipeline", "freight", "baltic_indices.json")
ROUTES = os.path.join(ROOT, "data", "freight", "routes.json")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Definitions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.defs = {r["id"]: r for r in load(DEFS)}
        cls.bench = {k: r for k, r in cls.defs.items() if r.get("benchmark")}

    def test_every_benchmark_has_a_definition_and_a_status(self):
        self.assertEqual(len(self.bench), 90)
        for k, r in self.bench.items():
            d = r["definition"]
            self.assertIn(d["state"], ("active", "suspended", "ended"), k)
            self.assertTrue(d["stateUrl"].startswith("https://www.balticexchange.com/"), k)
            self.assertTrue(d["url"].startswith("https://www.balticexchange.com/"), k)
            self.assertEqual(d["read"], "November 2026", k)
            self.assertEqual(d["state"] == "ended", bool(r.get("discontinued")), k)

    def test_retired_capesize_codes_are_ended_and_point_to_their_successor(self):
        for old, new in (("C10_14", "C10_182"), ("C14", "C14_182")):
            d = self.bench[old]["definition"]
            self.assertEqual((d["state"], d["stateDate"], d["replacedBy"]), ("ended", "2025-12-24", new))
            self.assertIn("19/25", d["stateNote"])
            self.assertEqual(self.bench[new]["definition"]["state"], "active")
            self.assertEqual(self.bench[new]["definition"]["duration"], d["duration"])

    def test_ports_of_the_definition(self):
        """The ten routes of C-054: the drawn ports are those of the definition."""
        want = {"TD23": ("Basrah", "Lavera"), "TC15": ("Skikda", "Chiba"), "TD7": ("Hound Point", "Wilhelmshaven"),
                "TD22": ("Galveston", "Ningbo"), "TD9": ("Covenas", "Corpus Christi"), "TC14": ("Houston", "Amsterdam"),
                "TC16": ("Amsterdam", "Lome"), "TC19": ("Amsterdam", "Lagos"), "BLPG2": ("Houston", "Flushing (Vlissingen)"),
                "TC10": ("Yeosu (Yosu)", "Los Angeles")}
        for k, (a, b) in want.items():
            r = self.bench[k]
            self.assertEqual((r["from"]["ports"][0]["name"], r["to"]["ports"][0]["name"]), (a, b), k)

    def test_cargo_sizes(self):
        sizes = {"C2": 170000, "C3": 170000, "C5": 160000, "C7": 160000, "P7": 66000, "P8": 66000, "TC20": 90000,
                 "TC21": 38000, "TD33": 145000, "TD28": 80000, "TD14": 80000, "TD18": 30000, "TD21": 50000}
        for k, v in sizes.items():
            self.assertEqual(self.bench[k]["parcel"], v, k)
        self.assertEqual(self.bench["C5"]["parcelMax"], 170000)
        # every voyage benchmark (load and discharge ports, not a time-charter trip) has a cargo size
        for k, r in self.bench.items():
            if not r["definition"].get("tc"):
                self.assertTrue(r.get("parcel"), k)

    def test_durations_of_the_definition(self):
        want = {"P1A_82": "40-60 days", "P6_82": "90-105 days", "S1C_63": "50-55 days", "HS6_38": "40-45 days",
                "BLNG1": "22 days", "BLNG3": "53 days", "C14_182": "80-90 days", "C9_182": "about 65 days"}
        for k, v in want.items():
            self.assertEqual(self.bench[k]["definition"]["duration"], v, k)

    def test_intermediate_tanker_routes_of_circular_03_26(self):
        want = {"TC25": ("Rotterdam", "Thames", 15000), "TC26": ("Kaarsto", "Rotterdam", 12500),
                "TD30": ("Immingham", "Rotterdam", 15000), "TD31": ("Port Jerome", "Rotterdam", 15000)}
        for k, (a, b, q) in want.items():
            r = self.bench[k]
            self.assertEqual((r["from"]["ports"][0]["name"], r["to"]["ports"][0]["name"], r["parcel"]), (a, b, q), k)
            d = r["definition"]
            self.assertEqual((d["state"], d["stateDate"], d["doc"]), ("active", "2026-01-14", "Baltic Exchange, Circular 03/26"), k)
            self.assertIn("much larger than this", r["notes"], k)

    def test_dirty_tanker_cargo_is_what_the_definition_says(self):
        """GBR1.2: the definition gives a tonnage and no cargo name; crude oil is the atlas's reading, in cargoNote."""
        ids = ("TD2", "TD3C", "TD6", "TD7", "TD9", "TD14", "TD15", "TD17", "TD19", "TD20", "TD22", "TD23", "TD25", "TD26",
               "TD27", "TD28", "TD29", "TD33", "TD34")
        for k in ids:
            r = self.bench[k]
            self.assertRegex(r["definition"]["cargo"], r"^[0-9,]+ t \(cargo not named in the definition\)$", k)
            self.assertIn("crude-oil", r["cargoes"], k)
            self.assertIn("atlas's reading", r["cargoNote"], k)
        self.assertIn("dirty petroleum products", self.bench["TD8"]["definition"]["cargo"])
        named = [k for k, r in self.bench.items() if "crude" in (r["definition"].get("cargo") or "") and k != "TD8"]
        self.assertEqual(named, [])

    def test_no_statement_without_a_page(self):
        """GBR1.3 and GBR1.4: the trial date of TD34, the Trans Mountain clause, the Forth crude and an October 2024 launch."""
        text = json.dumps(self.defs, ensure_ascii=False)
        for w in ("26 March", "Trans Mountain", "Forth crude", "launched in October 2024"):
            self.assertNotIn(w, text, w)

    def test_no_phrase_of_the_guide(self):
        text = json.dumps(self.defs, ensure_ascii=False)
        for w in ("more or less in owner's option", "days after sailing Qingdao"):
            self.assertNotIn(w, text, w)

    def test_no_note_left_unsettled(self):
        for k, r in self.bench.items():
            for f in ("notes", "cargoNote"):
                t = (r.get(f) or "").lower()
                for w in ("status uncertain", "not re-verified", "market convention", "secondary source"):
                    self.assertNotIn(w, t, k)


class Indices(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ix = {x["id"]: x for x in load(INDICES)}
        cls.defs = {r["id"] for r in load(DEFS)}

    def test_weights_add_up(self):
        for k, x in self.ix.items():
            ws = [m.get("w") for m in x.get("members", [])]
            if ws and all(w is not None for w in ws):
                self.assertAlmostEqual(sum(ws), 100.0, places=6, msg=k)

    def test_supramax_and_capesize_averages(self):
        s11 = {m["r"]: m["w"] for m in self.ix["S11TC"]["members"]}
        self.assertEqual(s11, {"S1B_63": 5, "S1C_63": 5, "S2_63": 15, "S3_63": 15, "S4A_63": 7.5, "S4B_63": 10, "S5_63": 5,
                               "S8_63": 10, "S9_63": 7.5, "S10_63": 10, "S15_63": 10})
        self.assertTrue(set(s11) <= self.defs)
        c5 = {m["r"]: m["w"] for m in self.ix["C5TC"]["members"]}
        self.assertEqual(c5, {"C8_182": 15, "C9_182": 12.5, "C10_182": 35, "C14_182": 25, "C16_182": 12.5})
        self.assertTrue(set(c5) <= self.defs)


@unittest.skipUnless(os.path.exists(ROUTES), "data/freight/routes.json not built")
class Published(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routes = {r["id"]: r for r in load(ROUTES)}

    def test_membership_says_how_much_of_the_index_the_atlas_has(self):
        c10 = next(x for x in self.routes["C10_14"]["definition"]["index"] if x["id"] == "C5TC_180")
        self.assertEqual((c10["w"], c10["covered"]), (25, 50))
        s1b = next(x for x in self.routes["S1B_63"]["definition"]["index"] if x["id"] == "S11TC")
        self.assertEqual((s1b["w"], s1b["covered"]), (5, 100))
        bdti = next(x for x in self.routes["TD18"]["definition"]["index"] if x["id"] == "BDTI")
        self.assertTrue(bdti["equal"])
        self.assertEqual(len(bdti["members"]), 11)

    def test_a_time_charter_benchmark_without_corridor_says_why(self):
        for k in ("P4_82", "S3_63", "C16_182", "HS3_38"):
            r = self.routes[k]
            self.assertNotIn("shares", r, k)
            self.assertTrue(r["shareNa"].startswith("Time-charter benchmark"), k)

    def test_new_grain_and_tanker_routes_have_a_corridor_share(self):
        for k in ("P7", "P8", "TD14", "TD28", "TD33", "C2", "S8_63"):
            self.assertTrue(self.routes[k].get("shares"), k)
            self.assertTrue(self.routes[k].get("history"), k)

    def test_a_route_counted_on_a_generated_corridor_links_to_it(self):
        for k in ("TC11", "TC22", "TD34"):
            r = self.routes[k]
            self.assertTrue(self.routes[r["shareOn"]].get("generated"), k)
            self.assertNotIn("shares", r, k)

    def test_definitions_carry_the_year_of_their_document(self):
        self.assertEqual(self.routes["TD3C"]["definition"]["y"], 2025)
        self.assertEqual(self.routes["TC25"]["definition"]["y"], 2026)
        self.assertEqual(self.routes["TD28"]["definition"]["y"], 2025)

    def test_palm_oil_route_in_the_first_class_of_the_vessel_rules(self):
        self.assertEqual(self.routes["indo-malay-india-palm-oil"]["vclass"], "mr")

    def test_end_country_of_an_offshore_terminal(self):
        self.assertEqual(self.routes["TD23"]["ends"], ["IRQ", "FRA"])

    def test_drawn_ports_of_the_new_capesize_routes(self):
        self.assertIn("C5 (West Australia – Qingdao)", self.routes["C10_182"]["standIn"])
        self.assertEqual(self.routes["C16_182"]["drawnAs"], "typical laden leg")


if __name__ == "__main__":
    unittest.main()
