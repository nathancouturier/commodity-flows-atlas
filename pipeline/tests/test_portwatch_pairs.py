"""Tests of the pairing of the port assets with the IMF PortWatch ports table (pipeline/infrastructure/portwatch_pairs.py):
the rule on small fixtures, the insertion of the ids into the text of ports.geojson, and the published pairs against the
rule. Every count is read from data/infrastructure/ports.geojson and pipeline/cache/portwatch_ports.csv."""
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "infrastructure"))
import portwatch_pairs as PP  # noqa: E402


def asset(id_, name, c, lon, lat, locode=None, **extra):
    p = {"id": id_, "name": name, "type": "port", "c": c, "k": ["iron-ore"], **extra}
    if locode:
        p["locode"] = locode
    return {"type": "Feature", "properties": p, "geometry": {"type": "Point", "coordinates": [lon, lat]}}


def row(portid, name, iso3, locode, lon, lat):
    return {"portid": portid, "name": name, "iso3": iso3, "locode": locode, "lat": str(lat), "lon": str(lon), "pageid": "x"}


def east(km):
    """Longitude offset of `km` kilometres due east on the equator."""
    return km / 111.195


class Rule(unittest.TestCase):
    def test_distance_function(self):
        self.assertAlmostEqual(PP.km_between(0, 0, 0, 1), 111.195, places=2)
        self.assertEqual(PP.km_between(10, 20, 10, 20), 0)

    def test_r1_locode_within_15_km(self):
        a = asset("a", "Alpha", "AUS", 0, 0, "AUAAA")
        got = PP.rule(a, [row("port1", "Other name", "AUS", "AUAAA", east(14.5), 0)])
        self.assertEqual((got["rule"], got["row"]["portid"]), ("R1", "port1"))
        self.assertAlmostEqual(got["km"], 14.5, places=1)

    def test_row_at_16_km_is_refused(self):
        a = asset("a", "Alpha", "AUS", 0, 0, "AUAAA")
        self.assertIsNone(PP.rule(a, [row("port1", "Alpha", "AUS", "AUAAA", east(16), 0)]))

    def test_other_country_is_refused(self):
        a = asset("a", "Alpha", "AUS", 0, 0, "AUAAA")
        self.assertIsNone(PP.rule(a, [row("port1", "Alpha", "NZL", "AUAAA", 0, 0)]))

    def test_offshore_terminal_rows_are_not_offered(self):
        a = asset("a", "Alpha", "AUS", 0, 0, "AUAAA")
        self.assertIsNone(PP.rule(a, [row("fso1", "Alpha", "AUS", "AUAAA", 0, 0)]))

    def test_r1_two_rows_share_a_locode_nearest_wins(self):
        a = asset("a", "Alpha", "AUS", 0, 0, "AUAAA")
        rows = [row("port1", "Far", "AUS", "AUAAA", east(9), 0), row("port2", "Near", "AUS", "AUAAA", east(2), 0)]
        self.assertEqual(PP.rule(a, rows)["row"]["portid"], "port2")

    def test_r1_beats_a_nearer_row_of_the_same_name(self):
        a = asset("a", "Alpha", "AUS", 0, 0, "AUAAA")
        rows = [row("port1", "Alpha", "AUS", "AUBBB", east(1), 0), row("port2", "Other", "AUS", "AUAAA", east(8), 0)]
        got = PP.rule(a, rows)
        self.assertEqual((got["rule"], got["row"]["portid"]), ("R1", "port2"))

    def test_r2_name_with_a_parenthesis_and_generic_words(self):
        a = asset("a", "Port of Tubarao (Vitoria) terminal", "BRA", 0, 0, None)
        got = PP.rule(a, [row("port1", "Tubarao", "BRA", "", east(3), 0)])
        self.assertEqual((got["rule"], got["row"]["portid"]), ("R2", "port1"))

    def test_r2_needs_the_same_name_not_a_nearer_port(self):
        a = asset("a", "Valdez", "USA", 0, 0, None)
        self.assertIsNone(PP.rule(a, [row("port1", "Swanport", "USA", "", east(0.1), 0)]))

    def test_r2_refuses_a_row_whose_own_name_has_a_parenthesis(self):
        a = asset("a", "Skikda", "DZA", 0, 0, "DZSKI")
        self.assertIsNone(PP.rule(a, [row("port1", "Skikda (Port Methanier)", "DZA", "DZSKM", east(2), 0)]))

    def test_r2_needs_a_name_left_after_stripping(self):
        a = asset("a", "Port terminal", "AUS", 0, 0, None)
        self.assertIsNone(PP.rule(a, [row("port1", "Harbor", "AUS", "", 0, 0)]))

    def test_norm(self):
        self.assertEqual(PP.norm("Paranaguá"), "paranagua")
        self.assertEqual(PP.norm("Port of Rotterdam Marine Terminal (Europoort)"), "rotterdam")
        self.assertEqual(PP.norm("Houston (US-TX)"), "houston")


class Pairing(unittest.TestCase):
    def test_two_assets_for_one_row_take_none(self):
        table = [row("port1", "Alpha", "AUS", "AUAAA", 0, 0)]
        assets = [asset("a", "Alpha", "AUS", 0, 0, "AUAAA"), asset("b", "Alpha 2", "AUS", east(2), 0, "AUAAA")]
        res = {x["id"]: x for x in PP.pair_all(assets, table)}
        self.assertEqual([res["a"]["outcome"], res["b"]["outcome"]], ["shared", "shared"])
        self.assertIn("b", res["a"]["why"])

    def test_a_row_held_by_an_existing_id_is_not_given_again(self):
        table = [row("port1", "Alpha", "AUS", "AUAAA", 0, 0)]
        assets = [asset("a", "Alpha", "AUS", 0, 0, "AUAAA", portwatch="port1"), asset("b", "Beta", "AUS", east(2), 0, "AUAAA")]
        res = {x["id"]: x for x in PP.pair_all(assets, table)}
        self.assertEqual((res["a"]["outcome"], res["b"]["outcome"]), ("has", "shared"))

    def test_an_existing_id_is_kept_even_if_the_rule_disagrees(self):
        table = [row("port1", "Guaiba", "BRA", "", 0, 0), row("port2", "Itaguai", "BRA", "", east(3.5), 0)]
        assets = [asset("itaguai", "Itaguai", "BRA", 0, 0, None, portwatch="port1")]
        x = PP.pair_all(assets, table)[0]
        self.assertEqual((x["outcome"], x["have"], x["gives"]), ("has", "port1", "port2"))

    def test_unpaired_and_no_row(self):
        table = [row("port1", "Swanport", "USA", "", east(0.1), 0), row("port2", "Faraway", "USA", "", east(50), 0)]
        assets = [asset("valdez", "Valdez", "USA", 0, 0, None), asset("loop", "LOOP", "USA", east(200), 0, None)]
        res = {x["id"]: x for x in PP.pair_all(assets, table)}
        self.assertEqual(res["valdez"]["outcome"], "unpaired")
        self.assertEqual(res["loop"]["outcome"], "none")

    def test_summary_counts(self):
        table = [row("port1", "Alpha", "AUS", "AUAAA", 0, 0)]
        assets = [asset("a", "Alpha", "AUS", 0, 0, "AUAAA"), asset("b", "Beta", "AUS", east(100), 0, None)]
        s = PP.summary(PP.pair_all(assets, table))
        self.assertEqual((s["assets"], s["have"], s["new"], s["with_id"], s["none"]), (2, 0, 1, 1, 1))


class Insertion(unittest.TestCase):
    TEXT = ('{\n "type": "FeatureCollection",\n "features": [\n'
            '  {\n   "type": "Feature",\n   "properties": {\n    "id": "a",\n    "name": "Alpha",\n    "type": "port",\n'
            '    "c": "AUS",\n    "locode": "AUAAA",\n    "status": "not-stated"\n   },\n   "geometry": {"type": "Point", "coordinates": [0, 0]}\n  },\n'
            '  {\n   "type": "Feature",\n   "properties": {\n    "id": "b",\n    "name": "Beta",\n    "type": "port",\n'
            '    "c": "AUS",\n    "status": "not-stated"\n   },\n   "geometry": {"type": "Point", "coordinates": [0, 0]}\n  }\n ]\n}')

    def test_ids_are_inserted_as_whole_lines_and_nothing_else_changes(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ports.geojson")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.TEXT)
            assets = PP.load_assets(path)
            table = [row("port1", "Alpha", "AUS", "AUAAA", 0, 0), row("port2", "Beta", "AUS", "", east(1), 0)]
            results = PP.pair_all(assets, table)
            self.assertEqual(PP.apply(results, assets, path), 2)
            with open(path, encoding="utf-8") as fh:
                after = fh.read()
            old, new = self.TEXT.split("\n"), after.split("\n")
            self.assertEqual([l for l in new if l not in old], ['    "portwatch": "port1",', '    "portwatch": "port2",'])
            self.assertEqual([l for l in old if l not in new], [])
            feats = json.loads(after)["features"]
            self.assertEqual([f["properties"]["portwatch"] for f in feats], ["port1", "port2"])
            # the id of a port with a locode follows the locode, one without follows its country
            self.assertEqual(new[new.index('    "locode": "AUAAA",') + 1], '    "portwatch": "port1",')
            self.assertEqual(new[new.index('    "portwatch": "port2",') - 1], '    "c": "AUS",')
            # a second run adds nothing
            again = PP.pair_all(PP.load_assets(path), table)
            self.assertEqual(PP.apply(again, PP.load_assets(path), path), 0)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), after)


class Published(unittest.TestCase):
    """The pairs of data/infrastructure/ports.geojson against the table and the rule."""

    @classmethod
    def setUpClass(cls):
        cls.assets = PP.load_assets()
        cls.table = PP.load_table()
        cls.by_id = {r["portid"]: r for r in cls.table}
        cls.results = PP.pair_all(cls.assets, cls.table)
        cls.paired = [a for a in cls.assets if a["properties"].get("portwatch")]

    def test_every_id_is_in_the_table_in_the_assets_country(self):
        for a in self.paired:
            p = a["properties"]
            self.assertIn(p["portwatch"], self.by_id, p["id"])
            self.assertEqual(self.by_id[p["portwatch"]]["iso3"], p["c"], p["id"])

    def test_no_id_is_used_twice(self):
        ids = [a["properties"]["portwatch"] for a in self.paired]
        self.assertEqual(len(ids), len(set(ids)), sorted(i for i in set(ids) if ids.count(i) > 1))

    def test_the_counts_are_the_files_counts(self):
        s = PP.summary(self.results)
        self.assertEqual(s["assets"], len(self.assets))
        self.assertEqual(s["with_id"], len(self.paired))
        # the ids of the file are the ids the rule keeps or gives: nothing is left for --apply to add
        self.assertEqual(s["new"], 0, [x["id"] for x in self.results if x["outcome"] == "new"])
        self.assertEqual(s["have"] + s["new"] + s["shared"] + s["unpaired"] + s["none"], len(self.assets))

    def test_the_rule_gives_every_new_pair_and_the_old_ones_it_can_reproduce(self):
        reproduced = [x for x in self.results if x["outcome"] == "has" and x["gives"] == x["have"]]
        others = [x for x in self.results if x["outcome"] == "has" and x["gives"] != x["have"]]
        self.assertEqual(len(reproduced) + len(others), len(self.paired))
        self.assertGreater(len(reproduced), len(others))
        for x in reproduced:
            self.assertLessEqual(x["km"], PP.MAX_KM, x["id"])

    def test_the_other_existing_pairs_sit_at_0_km_from_their_row_with_the_source_of_the_table(self):
        assets = {a["properties"]["id"]: a for a in self.assets}
        others = [x for x in self.results if x["outcome"] == "has" and x["gives"] != x["have"]]
        self.assertTrue(others)
        for x in others:
            a = assets[x["id"]]
            lon, lat = a["geometry"]["coordinates"]
            r = self.by_id[x["have"]]
            self.assertAlmostEqual(PP.km_between(lat, lon, float(r["lat"]), float(r["lon"])), 0.0, places=1, msg=x["id"])
            self.assertEqual(a["properties"]["s"], "portwatch-ports", x["id"])

    def test_a_port_without_an_id_is_one_the_rule_cannot_pair(self):
        for x in self.results:
            if x["outcome"] in ("unpaired", "none"):
                self.assertIsNone(x["gives"], x["id"])
            self.assertNotEqual(x["outcome"], "new", x["id"])

    def test_the_rule_does_not_pair_a_port_that_another_asset_holds(self):
        held = {a["properties"]["portwatch"]: a["properties"]["id"] for a in self.paired}
        for x in self.results:
            if not x["have"] and x["gives"]:
                self.assertNotIn(x["gives"], held, x["id"])

    def test_the_report_lists_the_ports_without_a_pair(self):
        out = io.StringIO()
        PP.report(self.results, out)
        text = out.getvalue()
        for outcome in ("unpaired", "none"):
            for x in self.results:
                if x["outcome"] == outcome:
                    self.assertIn(x["id"], text)
        s = PP.summary(self.results)
        self.assertIn("%d ports: %d carry an id" % (s["assets"], s["have"]), text)


if __name__ == "__main__":
    unittest.main()
