"""Tests of the World Port Index as a source: the extractor (pipeline/infrastructure/extract_wpi.py) and the tracked cache it writes
(pipeline/cache/wpi_ports.csv, pipeline/cache/wpi_meta.json).

1  the matching rule, on a synthetic file written here (made-up names and positions, test data, never read from the site)
2  the review table: every port is a port of the atlas, every promotion has its reason and its row, a held port is not in the cache
3  the cache is what the extractor makes from the raw file (skipped where raw/ is not on disk: it is not tracked)
4  the guards of the extractor, each with a file that breaks it; the cache is left untouched when one stops the run
5  the maximum vessel: the plausibility check and the ports held back
6  the meta file against the code (the rule, the counts, the ports) and the terms it records
7  the cache alone (it runs where raw/ does not exist): no doubtful or absent port is published, every figure is a positive number, the header is fixed
8  the extractor downloads nothing and names no other path under raw/; without the file it exits 0 and leaves the cache byte for byte
9  the registry text of the source: terms not read, the sentence quoted with its address and date, none of the words that grant a permission
10 the data file (data/infrastructure/wpi.json) is what the builder makes from the cache alone, byte for byte, and says nothing the cache does not
11 the builder stops, and writes nothing, on a cache that is not what the extractor writes; it names no path under raw/ and runs without it
12 the largest class of each port (maxClass) does not come from the World Port Index and is what port_limits.py makes
13 the documents (METHODOLOGY, NOTICE, docs/UPDATING, the README of the infrastructure folder, the About window) say what the meta file, the data file and the
   code say: the counts and the constants they quote are read from the files, and none of them grants a permission the pages read do not

Nothing here types a count or a figure of the file: they are read from the cache, the meta file and the atlas's own files.
Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_wpi.py"
"""
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "infrastructure"))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "common"))

import extract_wpi as X  # noqa: E402
import port_limits as PL  # noqa: E402
import sources_table  # noqa: E402
import wpi_limits as W  # noqa: E402

PORTS_CSV = os.path.join(ROOT, "pipeline", "cache", "wpi_ports.csv")
META = os.path.join(ROOT, "pipeline", "cache", "wpi_meta.json")
RAW = os.path.join(ROOT, "raw", "nga", "UpdatedPub150.csv")

# the columns of the cache, typed here on purpose: a column added to the cache without the site printing it fails test 7
CACHE_HEADER = ["port", "wpi", "name", "code", "by", "km", "size", "type", "tide", "chan", "anch", "pier", "oil", "lng", "loa", "beam", "draft", "oloa",
                "obeam", "odraft", "pilot", "tide_res", "why"]
# the 23 columns of the file that are read
FILE_COLUMNS = ["World Port Index Number", "Main Port Name", "Alternate Port Name", "UN/LOCODE", "Country Code", "Latitude", "Longitude", "Tidal Range (m)",
                "Channel Depth (m)", "Anchorage Depth (m)", "Cargo Pier Depth (m)", "Oil Terminal Depth (m)", "Liquified Natural Gas Terminal Depth (m)",
                "Maximum Vessel Length (m)", "Maximum Vessel Beam (m)", "Maximum Vessel Draft (m)", "Offshore Maximum Vessel Length (m)",
                "Offshore Maximum Vessel Beam (m)", "Offshore Maximum Vessel Draft (m)", "Harbor Size", "Harbor Type", "Pilotage - Compulsory",
                "Entrance Restriction - Tide"]
FIGURE_KEYS = ["tide", "chan", "anch", "pier", "oil", "lng", "loa", "beam", "draft", "oloa", "obeam", "odraft"]


def load_json(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return json.load(f)


def read_text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def read_text_at(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def cache_rows():
    with open(PORTS_CSV, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


KM = 111.195  # kilometres in a degree of latitude, for placing the fixtures

COUNTRIES = [{"c": "AAA", "a2": "AA", "name": "Atland"}, {"c": "BBB", "a2": "BB", "name": "Bland"}]


def row(n, name, lat, lon, code="", country="Atland", alt="", **kw):
    """A row of the synthetic file, with the 23 columns that are read."""
    r = {c: "0.0" for c in FILE_COLUMNS}
    r.update({"World Port Index Number": f"{n}.0", "Main Port Name": name, "Alternate Port Name": alt or " ", "UN/LOCODE": f"{code[:2]} {code[2:]}" if code else " ",
              "Country Code": country, "Latitude": repr(lat), "Longitude": repr(lon), "Harbor Size": "Medium", "Harbor Type": "Coastal (Natural)",
              "Pilotage - Compulsory": "Yes", "Entrance Restriction - Tide": "No", "Channel Depth (m)": "14.0"})
    r.update(kw)
    return r


def csv_text(rows, header=None):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=header or (["OID_"] + FILE_COLUMNS + ["Region Name"]), extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(dict(r, **{"OID_": "0.0", "Region Name": "x"}))
    return buf.getvalue()


def atlas(pid, name, lat, lon, locode="AAXXX", c="AAA"):
    return {"id": pid, "name": name, "c": c, "locode": locode, "lat": lat, "lon": lon}


def matches(ports, rows, review=None):
    parsed = X.read_rows(csv_text(rows))
    ctry = X.Countries(COUNTRIES)
    ms = X.match(ports, parsed, ctry)
    if review is not None:
        X.apply_review(ms, parsed, review)
    return {m["id"]: m for m in ms}, parsed


def km_north(km):
    return km / KM


class Rule(unittest.TestCase):
    """1"""

    def test_a_unique_code_near_the_point_with_the_same_name_is_sure_by_code(self):
        m, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "AATST")], [row(1, "Testport", 10.0 + km_north(2), 10.0, "AATST")])
        self.assertEqual((m["testport"]["grade"], m["testport"]["by"]), ("sure", "code"))
        self.assertAlmostEqual(m["testport"]["d"], 2.0, places=1)

    def test_a_unique_code_with_another_name_is_sure_only_close_to_the_point(self):
        near, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "AATST")], [row(1, "Othername", 10.0 + km_north(X.NAMELESS_KM - 1), 10.0, "AATST")])
        far, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "AATST")], [row(1, "Othername", 10.0 + km_north(X.NAMELESS_KM + 1), 10.0, "AATST")])
        self.assertEqual(near["testport"]["grade"], "sure")
        self.assertEqual(far["testport"]["grade"], "doubtful")
        self.assertIn("names differ", far["testport"]["reasons"][0])

    def test_a_code_that_two_rows_share_is_doubtful_and_names_the_closest(self):
        m, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "AATST")],
                       [row(1, "Testport East", 10.0 + km_north(5), 10.0, "AATST"), row(2, "Testport West", 10.0 + km_north(1), 10.0, "AATST")])
        r = m["testport"]
        self.assertEqual(r["grade"], "doubtful")
        self.assertEqual(r["row"]["n"], 2)
        self.assertIn("share the code", r["reasons"][0])

    def test_a_code_row_beyond_the_radius_is_doubtful(self):
        m, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "AATST")], [row(1, "Testport", 10.0 + km_north(X.CODE_KM + 1), 10.0, "AATST")])
        self.assertEqual(m["testport"]["grade"], "doubtful")
        self.assertTrue(m["testport"].get("far_code"))

    def test_a_code_of_another_country_is_doubtful(self):
        m, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "AATST")], [row(1, "Testport", 10.0, 10.0, "BBTST", country="Bland")])
        self.assertEqual(m["testport"]["grade"], "none" if m["testport"]["grade"] == "none" else "doubtful")
        self.assertNotEqual(m["testport"]["grade"], "sure")

    def test_a_row_of_the_right_code_in_another_country_is_not_sure(self):
        m, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "AATST")], [row(1, "Testport", 10.0, 10.0, "AATST", country="Bland")])
        self.assertEqual(m["testport"]["grade"], "doubtful")
        self.assertIn("another country", m["testport"]["reasons"][0])

    def test_a_name_without_a_code_within_the_radius_is_sure_by_name(self):
        m, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "")], [row(1, "Testport", 10.0 + km_north(X.NAME_KM - 1), 10.0)])
        self.assertEqual((m["testport"]["grade"], m["testport"]["by"]), ("sure", "name"))

    def test_the_alternate_name_counts_and_the_stop_words_do_not(self):
        m, _ = matches([atlas("testport", "Port of Testport Terminal (bracket)", 10.0, 10.0, "")],
                       [row(1, "Main Other", 10.0 + km_north(3), 10.0, alt="Testport; Another")])
        self.assertEqual(m["testport"]["grade"], "sure")

    def test_a_name_found_by_two_rows_is_doubtful(self):
        m, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "")],
                       [row(1, "Testport", 10.0 + km_north(3), 10.0), row(2, "Testport", 10.0 - km_north(4), 10.0)])
        self.assertEqual(m["testport"]["grade"], "doubtful")

    def test_the_same_name_farther_than_the_radius_is_doubtful_and_not_published(self):
        m, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "")], [row(1, "Testport", 10.0 + km_north((X.NAME_KM + X.NAME_FAR_KM) / 2), 10.0)])
        self.assertEqual(m["testport"]["grade"], "doubtful")
        self.assertIn("is found", m["testport"]["reasons"][0])

    def test_position_only_is_doubtful(self):
        m, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "")], [row(1, "Unrelated Name", 10.0 + km_north(2), 10.0)])
        self.assertEqual(m["testport"]["grade"], "doubtful")
        self.assertIn("position only", m["testport"]["reasons"][0])

    def test_no_candidate_gives_none(self):
        m, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "")], [row(1, "Unrelated Name", 10.0 + km_north(X.NAMELESS_KM + 30), 10.0)])
        self.assertEqual(m["testport"]["grade"], "none")

    def test_a_country_mismatch_by_name_is_none(self):
        m, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "")], [row(1, "Testport", 10.0, 10.0, country="Bland")])
        self.assertEqual(m["testport"]["grade"], "none")

    def test_another_row_of_the_country_nearer_than_the_margin_makes_the_match_doubtful(self):
        rows = [row(1, "Testport", 10.0 + km_north(X.NEARER_MARGIN_KM + 4), 10.0, "AATST"), row(2, "Testport Terminals", 10.0 + km_north(1), 10.0, "AATSX")]
        m, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "AATST")], rows)
        self.assertEqual(m["testport"]["grade"], "doubtful")
        self.assertIn("another row of the country is nearer", m["testport"]["reasons"][0])
        self.assertEqual(m["testport"]["row"]["n"], 1)

    def test_another_row_within_the_margin_does_not_stop_a_match(self):
        rows = [row(1, "Testport", 10.0 + km_north(2), 10.0, "AATST"), row(2, "Testport Terminals", 10.0 + km_north(2 - X.NEARER_MARGIN_KM / 2), 10.0, "AATSX")]
        m, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "AATST")], rows)
        self.assertEqual(m["testport"]["grade"], "sure")

    def test_the_nearer_row_of_another_country_does_not_count(self):
        rows = [row(1, "Testport", 10.0 + km_north(X.NEARER_MARGIN_KM + 4), 10.0, "AATST"), row(2, "Elsewhere", 10.0 + km_north(0.5), 10.0, country="Bland")]
        m, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "AATST")], rows)
        self.assertEqual(m["testport"]["grade"], "sure")

    def test_a_name_match_is_also_held_by_the_nearer_row_guard(self):
        rows = [row(1, "Testport", 10.0 + km_north(X.NEARER_MARGIN_KM + 4), 10.0), row(2, "Unrelated", 10.0 + km_north(1), 10.0)]
        m, _ = matches([atlas("testport", "Testport", 10.0, 10.0, "")], rows)
        self.assertEqual(m["testport"]["grade"], "doubtful")

    def test_a_name_that_another_row_of_the_country_carries_within_the_twin_distance_makes_the_match_doubtful(self):
        # the atlas's own case: a river port 9 km away and a row "... Oil Terminal" 27 km away carry the same name once the stop words are dropped
        rows = [row(1, "Testport", 10.0 + km_north(9), 10.0), row(2, "Testport Oil Terminal", 10.0 + km_north(27), 10.0)]
        m, _ = matches([atlas("testport", "Testport terminal", 10.0, 10.0, "")], rows)
        self.assertEqual(m["testport"]["grade"], "doubtful")
        self.assertEqual(m["testport"]["row"]["n"], 1)
        self.assertEqual(m["testport"]["reasons"], ["two rows of the file carry the name within 60 km: no. 1 Testport at 9.0 km and no. 2 Testport Oil Terminal at 27.0 km"])
        # the same row on its own is sure
        m, _ = matches([atlas("testport", "Testport terminal", 10.0, 10.0, "")], rows[:1])
        self.assertEqual((m["testport"]["grade"], m["testport"]["by"]), ("sure", "name"))

    def test_the_twin_name_must_be_of_the_country_and_within_the_distance(self):
        near = row(1, "Testport", 10.0 + km_north(9), 10.0)
        for other in (row(2, "Testport Oil Terminal", 10.0 + km_north(27), 10.0, country="Bland"),
                      row(3, "Testport Oil Terminal", 10.0 + km_north(X.NAME_TWIN_KM + 5), 10.0),
                      row(4, "Different", 10.0 + km_north(27), 10.0)):
            m, _ = matches([atlas("testport", "Testport terminal", 10.0, 10.0, "")], [near, other])
            self.assertEqual(m["testport"]["grade"], "sure", other["Main Port Name"])
        m, _ = matches([atlas("testport", "Testport terminal", 10.0, 10.0, "")], [near, row(2, "Testport Oil Terminal", 10.0 + km_north(X.NAME_TWIN_KM - 3), 10.0)])
        self.assertEqual(m["testport"]["grade"], "doubtful")

    def test_a_match_by_code_does_not_look_for_a_twin_name(self):
        rows = [row(1, "Testport", 10.0 + km_north(9), 10.0, "AATST"), row(2, "Testport Oil Terminal", 10.0 + km_north(27), 10.0)]
        m, _ = matches([atlas("testport", "Testport terminal", 10.0, 10.0, "AATST")], rows)
        self.assertEqual((m["testport"]["grade"], m["testport"]["by"]), ("sure", "code"))

    def test_a_port_without_a_locode_is_matched_by_name_only(self):
        p = atlas("testport", "Testport", 10.0, 10.0, "")
        del p["locode"]
        m, _ = matches([p], [row(1, "Testport", 10.0, 10.0, "AATST")])
        self.assertEqual((m["testport"]["grade"], m["testport"]["by"]), ("sure", "name"))

    def test_the_distance_is_great_circle_kilometres(self):
        self.assertAlmostEqual(X.hav(0, 0, 1, 0), KM, delta=0.1)
        self.assertAlmostEqual(X.hav(60, 0, 60, 1), KM / 2, delta=0.2)


class Review(unittest.TestCase):
    """2"""

    def setUp(self):
        self.ports = [atlas("testport", "Testport", 10.0, 10.0, "AATST")]
        self.rows = [row(1, "Testport Alt Spelling", 10.0 + km_north(X.NAMELESS_KM + 20), 10.0, "AAZZZ"), row(2, "Unrelated Name", 10.0 + km_north(3), 10.0)]

    def promote(self, **kw):
        e = {"action": "promote", "wpi": 2, "name": "Unrelated Name", "evidence": "The two names are one place."}
        e.update(kw)
        return {"testport": e}

    def test_a_promotion_makes_the_match_sure_by_review_with_its_reason_and_the_two_positions(self):
        m, _ = matches(self.ports, self.rows, self.promote())
        r = m["testport"]
        self.assertEqual((r["grade"], r["by"], r["row"]["n"]), ("sure", "review", 2))
        self.assertIn("The two names are one place.", r["why"])
        self.assertIn("10.00 N", r["why"])
        self.assertIn("Unrelated Name", r["why"])

    def test_a_promotion_without_a_reason_stops(self):
        with self.assertRaisesRegex(X.Stop, "without a reason"):
            matches(self.ports, self.rows, self.promote(evidence="  "))

    def test_a_promotion_of_a_row_the_file_does_not_have_stops(self):
        with self.assertRaisesRegex(X.Stop, "no longer has"):
            matches(self.ports, self.rows, self.promote(wpi=99))
        with self.assertRaisesRegex(X.Stop, "no longer has"):
            matches(self.ports, self.rows, self.promote(name="Another Name"))

    def test_a_promotion_cannot_pass_the_nearer_row_guard(self):
        rows = [row(1, "Far Spelling", 10.0 + km_north(X.NEARER_MARGIN_KM + 5), 10.0), row(2, "Near Other", 10.0 + km_north(1), 10.0)]
        with self.assertRaisesRegex(X.Stop, "nearer"):
            matches(self.ports, rows, self.promote(wpi=1, name="Far Spelling"))

    def test_a_port_that_is_not_in_the_atlas_stops(self):
        with self.assertRaisesRegex(X.Stop, "not a port of the atlas"):
            matches(self.ports, self.rows, {"nowhere": {"action": "hold", "why": "x"}})

    def test_a_hold_makes_a_sure_match_doubtful_with_its_reason(self):
        m, _ = matches(self.ports, [row(1, "Testport", 10.0, 10.0, "AATST")], {"testport": {"action": "hold", "why": "two harbours"}})
        self.assertEqual(m["testport"]["grade"], "doubtful")
        self.assertEqual(m["testport"]["reasons"], ["two harbours"])

    def test_the_review_table_of_the_extractor(self):
        ids = {f["properties"]["id"] for f in load_json("data", "infrastructure", "ports.geojson")["features"]}
        self.assertTrue(X.REVIEW)
        for pid, e in X.REVIEW.items():
            self.assertIn(pid, ids)
            self.assertIn(e["action"], ("promote", "hold"))
            if e["action"] == "promote":
                self.assertIsInstance(e["wpi"], int)
                self.assertTrue(e["name"].strip())
                self.assertGreater(len(e["evidence"].strip()), 40, pid)
            else:
                self.assertGreater(len(e["why"].strip()), 40, pid)

    def test_promoted_ports_are_in_the_cache_with_their_reason_and_held_ports_are_not(self):
        meta, rows = load_json("pipeline", "cache", "wpi_meta.json"), {r["port"]: r for r in cache_rows()}
        for pid, e in X.REVIEW.items():
            if e["action"] == "promote":
                self.assertIn(pid, rows)
                self.assertEqual(rows[pid]["by"], "review")
                self.assertEqual(rows[pid]["wpi"], str(e["wpi"]))
                self.assertEqual(rows[pid]["name"], e["name"])
                self.assertIn(e["evidence"], rows[pid]["why"])
                self.assertEqual(meta["review"][pid]["why"], rows[pid]["why"])
            else:
                self.assertNotIn(pid, rows)
                self.assertIn(pid, {d["id"] for d in meta["doubtful"]})
                self.assertEqual(meta["review"][pid]["why"], e["why"])


@unittest.skipUnless(os.path.exists(RAW), "raw/ is not tracked: the cache is not recomputed from the raw file")
class FromRaw(unittest.TestCase):
    """3"""

    @classmethod
    def setUpClass(cls):
        cls.out = X.extract(RAW, X.atlas_ports(), load_json("data", "countries", "index.json"), X.REVIEW)

    def test_the_cache_is_what_the_extractor_makes(self):
        csv_text_, meta, _ = self.out
        with open(PORTS_CSV, encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), csv_text_)
        with open(META, encoding="utf-8") as f:
            self.assertEqual(f.read(), X.meta_text(meta))

    def test_the_raw_file_is_the_one_the_meta_records(self):
        meta = load_json("pipeline", "cache", "wpi_meta.json")
        self.assertEqual(X.sha256(RAW), meta["file"]["sha256"])
        self.assertEqual(os.path.getsize(RAW), meta["file"]["bytes"])
        with open(RAW, encoding="utf-8-sig", newline="") as f:
            text = f.read()
        self.assertEqual(len(X.read_rows(text)), meta["file"]["rows"])
        self.assertEqual(len(next(csv.reader(io.StringIO(text)))), meta["file"]["columns"])

    def test_no_published_port_has_another_row_of_its_country_nearer_to_the_atlas_point_by_more_than_the_margin(self):
        with open(RAW, encoding="utf-8-sig", newline="") as f:
            rows = X.read_rows(f.read())
        ctry = X.Countries(load_json("data", "countries", "index.json"))
        for r in rows:
            r["cty"] = ctry.of_row(r)
        by_n = {(r["n"], r["name"]): r for r in rows}
        ports = {p["id"]: p for p in X.atlas_ports()}
        for c in cache_rows():
            p, w = ports[c["port"]], by_n[(int(c["wpi"]), c["name"])]
            d = X.hav(p["lat"], p["lon"], w["lat"], w["lon"])
            self.assertEqual(w["cty"], p["c"], c["port"])
            for x in rows:
                if x is not w and x["cty"] == p["c"]:
                    self.assertGreaterEqual(X.hav(p["lat"], p["lon"], x["lat"], x["lon"]), d - X.NEARER_MARGIN_KM, f"{c['port']}: no. {x['n']} {x['name']}")

    def test_no_published_match_by_name_has_another_row_of_the_name_within_the_twin_distance(self):
        with open(RAW, encoding="utf-8-sig", newline="") as f:
            rows = X.read_rows(f.read())
        ctry = X.Countries(load_json("data", "countries", "index.json"))
        for r in rows:
            r["cty"], r["names"] = ctry.of_row(r), X.row_names(r)
        ports = {p["id"]: p for p in X.atlas_ports()}
        for c in cache_rows():
            if c["by"] != "name":
                continue
            p, heads = ports[c["port"]], X.atlas_heads(ports[c["port"]]["name"])
            for x in rows:
                if x["cty"] == p["c"] and heads & x["names"] and (x["n"], x["name"]) != (int(c["wpi"]), c["name"]):
                    self.assertGreater(X.hav(p["lat"], p["lon"], x["lat"], x["lon"]), X.NAME_TWIN_KM, f"{c['port']}: no. {x['n']} {x['name']}")

    def test_the_grades_of_the_ports_that_the_twin_rule_changed_are_forcados_only(self):
        # the ports whose grade changes when the twin distance is taken to zero are the ports the rule holds back: one
        with open(RAW, encoding="utf-8-sig", newline="") as f:
            text = f.read()

        def grades():
            return {m["id"]: m["grade"] for m in X.build(X.atlas_ports(), X.read_rows(text), X.Countries(load_json("data", "countries", "index.json")), X.REVIEW)[2]}

        saved = X.NAME_TWIN_KM
        try:
            X.NAME_TWIN_KM = 0.0
            without = grades()
        finally:
            X.NAME_TWIN_KM = saved
        now = grades()
        self.assertEqual({k for k in now if now[k] != without[k]}, {"forcados"})
        self.assertEqual((without["forcados"], now["forcados"]), ("sure", "doubtful"))

    def test_the_lng_depths_of_the_file_are_not_on_the_floors_of_the_key_as_the_four_others_are(self):
        floors = {float(f) for f in re.findall(r"\{ code: '[a-z]', from: ([\d.]+), to: [\d.]+ \}", read_text("web", "src", "lib", "wpi.ts"))} | {23.2}
        floors.discard(0.0)
        with open(RAW, encoding="utf-8-sig", newline="") as f:
            rows = X.read_rows(f.read())
        share = lambda k: sum(1 for w in rows if w[k] in floors) / sum(1 for w in rows if w[k])  # noqa: E731
        for k in ("chan", "anch", "pier", "oil"):
            self.assertGreater(share(k), 0.85, k)
        self.assertLess(share("lng"), 0.1)
        self.assertEqual(sum(1 for w in rows if w["lng"]), 22)
        self.assertEqual(sum(1 for w in rows if w["lng"] in floors), 1)

    def test_the_file_matches_the_atlas_at_the_distances_the_meta_gives(self):
        meta = load_json("pipeline", "cache", "wpi_meta.json")
        kept = max((float(r["km"]), r["port"]) for r in cache_rows() if r["by"] == "code")
        self.assertEqual(meta["rule_basis"]["farthest_kept"], {"id": kept[1], "km": kept[0]})
        self.assertLessEqual(kept[0], X.CODE_KM)
        self.assertGreater(meta["rule_basis"]["nearest_refused"]["km"], X.CODE_KM)


class Guards(unittest.TestCase):
    """4"""

    def base_rows(self, n=30):
        return [row(i, f"Place{chr(97 + i % 26)}{chr(97 + i // 26)}", 10.0 + i * 0.5, 10.0, f"AAP{chr(65 + i % 26)}{chr(65 + i // 26)}"[:5]) for i in range(1, n + 1)]

    def ports_for(self, rows):
        return [atlas(f"p{r['World Port Index Number'][:-2]}", r["Main Port Name"], float(r["Latitude"]), 10.0, r["UN/LOCODE"].replace(" ", "")) for r in rows]

    def run_extract(self, rows, ports=None, prev=None, accept=False, review=None, header=None, tmp=None, dates=None):
        """A run of the extractor on a fixture file. After a previous run (`prev`) the dates are typed anew, as a refresh does, unless `dates` says
        which (downloaded, captured) the run has."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "raw.csv")
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(csv_text(rows, header))
            saved = (X.DOWNLOADED, X.CAPTURED)
            if dates is not None:
                X.DOWNLOADED, X.CAPTURED = dates
            elif prev:
                X.DOWNLOADED, X.CAPTURED = "2099-01-01", "2099-01-02"
            try:
                return X.extract(path, ports or self.ports_for(rows), COUNTRIES, review or {}, *(prev or (None, None)), accept=accept)
            finally:
                X.DOWNLOADED, X.CAPTURED = saved

    def previous(self, rows, **kw):
        text, meta, _ = self.run_extract(rows, **kw)
        return text, meta

    def test_the_fixture_file_reads_and_publishes_every_port(self):
        rows = self.base_rows()
        text, meta, _ = self.run_extract(rows)
        self.assertEqual(meta["published"], len(rows))
        self.assertEqual(len(X.read_cache_csv(text)), len(rows))

    def test_a_new_unrelated_column_is_ignored(self):
        self.run_extract(self.base_rows(), header=["OID_"] + FILE_COLUMNS + ["Region Name", "A New Column"])

    def test_a_missing_column_stops_and_names_it(self):
        for col in FILE_COLUMNS:
            with self.assertRaises(X.Stop) as cm:
                self.run_extract(self.base_rows(3), header=["OID_"] + [c for c in FILE_COLUMNS if c != col])
            self.assertIn(col, str(cm.exception))

    def test_a_value_that_is_not_a_number_stops(self):
        rows = self.base_rows(3)
        rows[1]["Channel Depth (m)"] = "deep"
        with self.assertRaisesRegex(X.Stop, "not a number"):
            self.run_extract(rows)

    def test_a_negative_value_stops(self):
        rows = self.base_rows(3)
        rows[1]["Maximum Vessel Length (m)"] = "-5.0"
        with self.assertRaisesRegex(X.Stop, "Maximum Vessel Length"):
            self.run_extract(rows)

    def test_a_position_off_the_globe_stops(self):
        rows = self.base_rows(3)
        rows[1]["Latitude"] = "123.4"
        with self.assertRaisesRegex(X.Stop, "not on the globe"):
            self.run_extract(rows)

    def test_a_class_the_atlas_does_not_know_stops(self):
        rows = self.base_rows(3)
        rows[1]["Harbor Size"] = "Enormous"
        with self.assertRaisesRegex(X.Stop, "class the atlas does not know"):
            self.run_extract(rows)
        rows[1]["Harbor Size"] = "Medium"
        rows[1]["Pilotage - Compulsory"] = "Maybe"
        with self.assertRaisesRegex(X.Stop, "not Yes, No or Unknown"):
            self.run_extract(rows)

    def test_a_port_whose_row_is_of_another_country_stops(self):
        rows = [row(1, "Testport", 10.0, 10.0, "AATST", country="Bland"), row(2, "Unrelated", 10.5, 10.0)]
        ports = [atlas("testport", "Testport", 10.0, 10.0, "AATST")]
        with self.assertRaisesRegex(X.Stop, "not of the port's country"):
            self.run_extract(rows, ports=ports, review={"testport": {"action": "promote", "wpi": 1, "name": "Testport", "evidence": "x" * 50}})

    def test_a_row_of_the_review_table_that_the_file_lost_stops(self):
        rows = self.base_rows(3)
        with self.assertRaisesRegex(X.Stop, "no longer has"):
            self.run_extract(rows, review={"p1": {"action": "promote", "wpi": 999, "name": "Gone", "evidence": "x" * 50}})

    def test_fewer_rows_than_before_stops_unless_accepted(self):
        rows = self.base_rows(40)
        prev = self.previous(rows)
        few = rows[: int(len(rows) * X.ROWS_MIN) - 1]
        with self.assertRaisesRegex(X.Stop, "rows against"):
            self.run_extract(few, ports=self.ports_for(rows), prev=prev)
        text, meta, _ = self.run_extract(few, ports=self.ports_for(rows), prev=prev, accept=True)
        self.assertEqual(meta["file"]["rows"], len(few))

    def test_a_small_loss_of_rows_passes(self):
        rows = self.base_rows(40)
        prev = self.previous(rows)
        self.run_extract(rows[:-1], ports=self.ports_for(rows), prev=prev)

    def test_fewer_published_ports_than_before_stops_unless_accepted(self):
        rows = self.base_rows(40)
        ports = self.ports_for(rows)
        prev = self.previous(rows)
        broken = [dict(r) for r in rows]
        for r in broken[: X.PUBLISHED_DROP + 1]:
            r["Main Port Name"] = "Renamed Elsewhere"
            r["UN/LOCODE"] = "AA 000"
            r["Latitude"] = "-60.0"
        keep = len(rows)  # same number of rows: only the matches fail
        with self.assertRaisesRegex(X.Stop, "ports are published against"):
            self.run_extract(broken, ports=ports, prev=prev)
        _, meta, _ = self.run_extract(broken, ports=ports, prev=prev, accept=True)
        self.assertEqual(meta["file"]["rows"], keep)

    def test_a_loss_of_exactly_the_tolerance_passes(self):
        rows = self.base_rows(40)
        ports = self.ports_for(rows)
        prev = self.previous(rows)
        broken = [dict(r) for r in rows]
        for r in broken[: X.PUBLISHED_DROP]:
            r["Latitude"] = "-60.0"
        self.run_extract(broken, ports=ports, prev=prev)

    def test_a_rescaled_column_stops_unless_accepted(self):
        rows = self.base_rows(40)
        ports = self.ports_for(rows)
        prev = self.previous(rows)
        scaled = [dict(r, **{"Channel Depth (m)": "30.0"}) for r in rows]
        with self.assertRaisesRegex(X.Stop, "moved by more than"):
            self.run_extract(scaled, ports=ports, prev=prev)
        self.run_extract(scaled, ports=ports, prev=prev, accept=True)

    def test_a_few_figures_that_move_pass(self):
        rows = self.base_rows(40)
        ports = self.ports_for(rows)
        prev = self.previous(rows)
        moved = [dict(r) for r in rows]
        for r in moved[: int(len(rows) * X.CHANGED_SHARE) - 1]:
            r["Channel Depth (m)"] = "30.0"
        self.run_extract(moved, ports=ports, prev=prev)

    def test_accept_does_not_pass_a_bad_value_or_a_missing_column(self):
        rows = self.base_rows(3)
        rows[0]["Channel Depth (m)"] = "-1.0"
        with self.assertRaises(X.Stop):
            self.run_extract(rows, accept=True)
        with self.assertRaises(X.Stop):
            self.run_extract(self.base_rows(3), header=["OID_"] + FILE_COLUMNS[1:], accept=True)

    def test_a_new_file_with_the_dates_of_the_last_one_stops_unless_accepted(self):
        rows = self.base_rows(10)
        prev = self.previous(rows)
        other = [dict(r, **{"Channel Depth (m)": "12.5"}) for r in rows]
        same = (prev[1]["downloaded"], prev[1]["captured"])
        self.assertIsNotNone(same[1], "the fixture run has the extractor's capture date")
        with self.assertRaisesRegex(X.Stop, r"the file changed but DOWNLOADED and CAPTURED were not edited"):
            self.run_extract(other, prev=prev, dates=same)
        text, meta, _ = self.run_extract(other, prev=prev, dates=same, accept=True)
        self.assertEqual(meta["downloaded"], same[0])

    def test_a_new_file_with_one_date_typed_and_the_other_forgotten_stops_naming_it(self):
        rows = self.base_rows(10)
        prev = self.previous(rows)
        other = [dict(r, **{"Channel Depth (m)": "12.5"}) for r in rows]
        d, c = prev[1]["downloaded"], prev[1]["captured"]
        with self.assertRaisesRegex(X.Stop, r"the file changed but DOWNLOADED was not edited"):
            self.run_extract(other, prev=prev, dates=(d, "2099-01-02"))
        with self.assertRaisesRegex(X.Stop, r"the file changed but CAPTURED was not edited"):
            self.run_extract(other, prev=prev, dates=("2099-01-01", c))

    def test_a_new_file_with_both_dates_typed_passes_and_so_does_one_from_the_publisher(self):
        rows = self.base_rows(10)
        prev = self.previous(rows)
        other = [dict(r, **{"Channel Depth (m)": "12.5"}) for r in rows]
        text, meta, _ = self.run_extract(other, prev=prev)
        self.assertEqual((meta["downloaded"], meta["captured"]), ("2099-01-01", "2099-01-02"))
        # a file from the publisher itself has no capture date, and None again is not a date that was forgotten
        first = self.run_extract(rows, prev=prev, dates=("2099-01-01", None))
        self.assertIsNone(first[1]["captured"])
        self.assertIsNone(first[1]["captured_from"])
        later = self.run_extract(other, prev=(first[0], first[1]), dates=("2099-02-01", None))
        self.assertEqual(later[1]["downloaded"], "2099-02-01")
        with self.assertRaisesRegex(X.Stop, r"the file changed but DOWNLOADED was not edited"):
            self.run_extract(other, prev=(first[0], first[1]), dates=("2099-01-01", None))

    def test_the_same_file_read_again_needs_no_new_date(self):
        rows = self.base_rows(10)
        prev = self.previous(rows)
        text, meta, _ = self.run_extract(rows, prev=prev, dates=(prev[1]["downloaded"], prev[1]["captured"]))
        self.assertEqual(meta["downloaded"], prev[1]["downloaded"])

    def test_a_stopped_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, cache_csv, cache_meta = (os.path.join(tmp, n) for n in ("raw.csv", "wpi_ports.csv", "wpi_meta.json"))
            rows = self.base_rows(3)
            rows[1]["Channel Depth (m)"] = "deep"
            with open(raw, "w", encoding="utf-8", newline="") as f:
                f.write(csv_text(rows))
            with open(cache_csv, "w", encoding="utf-8") as f:
                f.write("kept\n")
            with open(cache_meta, "w", encoding="utf-8") as f:
                f.write("{}")
            saved = (X.RAW, X.PORTS_CSV, X.META, X.REVIEW)
            X.RAW, X.PORTS_CSV, X.META, X.REVIEW = raw, cache_csv, cache_meta, {}
            try:
                err = io.StringIO()
                with redirect_stderr(err), redirect_stdout(io.StringIO()):
                    code = X.main([])
            finally:
                X.RAW, X.PORTS_CSV, X.META, X.REVIEW = saved
            self.assertEqual(code, 1)
            self.assertIn("the table was not replaced", err.getvalue())
            self.assertEqual(read_bytes(cache_csv), b"kept\n")
            self.assertEqual(read_bytes(cache_meta), b"{}")
            self.assertEqual(sorted(os.listdir(tmp)), ["raw.csv", "wpi_meta.json", "wpi_ports.csv"])

    def test_a_good_run_writes_both_files_and_a_second_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, cache_csv, cache_meta = (os.path.join(tmp, n) for n in ("raw.csv", "wpi_ports.csv", "wpi_meta.json"))
            with open(raw, "w", encoding="utf-8", newline="") as f:
                f.write(csv_text(self.base_rows(5)))
            saved = (X.RAW, X.PORTS_CSV, X.META, X.REVIEW, X.atlas_ports)
            X.RAW, X.PORTS_CSV, X.META, X.REVIEW = raw, cache_csv, cache_meta, {}
            X.atlas_ports = lambda path=None: self.ports_for(self.base_rows(5))
            try:
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(X.main([]), 0)
                    first = (read_bytes(cache_csv), read_bytes(cache_meta))
                    self.assertEqual(X.main([]), 0)
                    second = (read_bytes(cache_csv), read_bytes(cache_meta))
            finally:
                X.RAW, X.PORTS_CSV, X.META, X.REVIEW, X.atlas_ports = saved
            self.assertEqual(first, second)
            self.assertEqual(sorted(os.listdir(tmp)), ["raw.csv", "wpi_meta.json", "wpi_ports.csv"])


class Vessel(unittest.TestCase):
    """5"""

    def test_the_plausibility_check(self):
        self.assertIsNone(X.plausible(300.0, 50.0))
        self.assertIsNone(X.plausible(300.0, 0.0))
        self.assertIsNone(X.plausible(0.0, 0.0))
        self.assertIn("of the length", X.plausible(100.0, 100.0 * X.BEAM_MAX_RATIO + 1))
        self.assertIsNone(X.plausible(100.0, 100.0 * X.BEAM_MAX_RATIO))
        self.assertIn("m", X.plausible(1000.0, X.BEAM_MAX_M + 1))
        self.assertIsNone(X.plausible(1000.0, X.BEAM_MAX_M))
        self.assertIn("no length", X.plausible(0.0, 40.0))

    def test_the_draught_may_not_be_above_its_share_of_the_length(self):
        self.assertIsNone(X.plausible(300.0, 0.0, 300.0 * X.DRAFT_MAX_RATIO))
        self.assertEqual(X.plausible(300.0, 0.0, 300.0 * X.DRAFT_MAX_RATIO + 0.1), f"the draught is above {X.DRAFT_MAX_RATIO:.0%} of the length")
        self.assertEqual(X.plausible(275.0, 0.0, 275.0), f"the draught is above {X.DRAFT_MAX_RATIO:.0%} of the length")
        self.assertIsNone(X.plausible(300.0, 50.0, 15.0))
        self.assertIsNone(X.plausible(0.0, 0.0, 15.0), "a draught with no length cannot be compared and passes: it is no beam")
        self.assertIsNone(X.plausible(300.0, 50.0))
        self.assertIn("beam", X.plausible(100.0, 90.0, 9.0), "the beam is judged first")

    def test_a_draught_as_long_as_the_ship_holds_back_its_group_only(self):
        rows = [row(1, "Testport", 10.0, 10.0, "AATST", **{"Maximum Vessel Length (m)": "366.5", "Maximum Vessel Beam (m)": "51.2", "Maximum Vessel Draft (m)": "16.0",
                                                           "Offshore Maximum Vessel Length (m)": "275.0", "Offshore Maximum Vessel Draft (m)": "275.0"})]
        p = [atlas("testport", "Testport", 10.0, 10.0, "AATST")]
        out, held, _ = X.build(p, X.read_rows(csv_text(rows)), X.Countries(COUNTRIES), {})
        r = out[0]
        self.assertEqual((r["loa"], r["beam"], r["draft"]), ("366.5", "51.2", "16"))
        self.assertEqual((r["oloa"], r["obeam"], r["odraft"]), ("", "", ""))
        self.assertEqual(held, [{"id": "testport", "group": "offshore", "reason": f"the draught is above {X.DRAFT_MAX_RATIO:.0%} of the length"}])

    def test_the_draught_ratio_is_read_from_the_file_the_meta_records(self):
        rows = [row(i, f"Place{i}", 10.0 + i, 10.0, f"AAP{i:02d}"[:5], **{"Maximum Vessel Length (m)": "200.0", "Maximum Vessel Draft (m)": str(10.0 * i)}) for i in range(1, 6)]
        rows.append(row(9, "Twin", 30.0, 10.0, "AATWN", **{"Offshore Maximum Vessel Length (m)": "100.0", "Offshore Maximum Vessel Draft (m)": "100.0"}))
        b = X.draft_basis(X.read_rows(csv_text(rows)))
        self.assertEqual(b["pairs"], 6)
        self.assertEqual(b["median"], 0.175)
        self.assertEqual(b["largest_kept"], {"wpi": 5, "name": "Place5", "group": "maximum", "ratio": 0.25})
        self.assertEqual(b["above"], [{"wpi": 9, "name": "Twin", "group": "offshore", "ratio": 1.0}])

    def test_an_implausible_group_is_emptied_whole_and_listed_and_the_depths_stay(self):
        rows = [row(1, "Testport", 10.0, 10.0, "AATST", **{"Maximum Vessel Length (m)": "100.0", "Maximum Vessel Beam (m)": "90.0", "Maximum Vessel Draft (m)": "9.0",
                                                           "Offshore Maximum Vessel Length (m)": "300.0", "Offshore Maximum Vessel Beam (m)": "50.0"})]
        ms, parsed = matches([atlas("testport", "Testport", 10.0, 10.0, "AATST")], rows)
        out, held, _ = X.build([atlas("testport", "Testport", 10.0, 10.0, "AATST")], parsed, X.Countries(COUNTRIES), {})
        r = out[0]
        self.assertEqual((r["loa"], r["beam"], r["draft"]), ("", "", ""))
        self.assertEqual((r["oloa"], r["obeam"]), ("300", "50"))
        self.assertEqual(r["chan"], "14")
        self.assertEqual([(h["id"], h["group"]) for h in held], [("testport", "maximum")])

    def test_a_row_with_nothing_left_is_not_published(self):
        rows = [row(1, "Testport", 10.0, 10.0, "AATST", **{"Channel Depth (m)": "0.0", "Maximum Vessel Beam (m)": "30.0", "Tidal Range (m)": "2.0"})]
        p = [atlas("testport", "Testport", 10.0, 10.0, "AATST")]
        parsed = X.read_rows(csv_text(rows))
        out, held, ms = X.build(p, parsed, X.Countries(COUNTRIES), {})
        self.assertEqual(out, [])
        self.assertEqual(ms[0]["grade"], "doubtful")

    def test_the_cache_holds_no_implausible_vessel_and_every_held_port_is_empty(self):
        meta, rows = load_json("pipeline", "cache", "wpi_meta.json"), {r["port"]: r for r in cache_rows()}
        for r in rows.values():
            loa, beam, draft = float(r["loa"] or 0), float(r["beam"] or 0), float(r["draft"] or 0)
            self.assertIsNone(X.plausible(loa, beam, draft), r["port"])
            self.assertIsNone(X.plausible(float(r["oloa"] or 0), float(r["obeam"] or 0), float(r["odraft"] or 0)), r["port"])
        for h in meta["held_vessel"]:
            self.assertIn(h["id"], rows)
            keys = ("loa", "beam", "draft") if h["group"] == "maximum" else ("oloa", "obeam", "odraft")
            self.assertEqual([rows[h["id"]][k] for k in keys], ["", "", ""])
            self.assertTrue(h["reason"])
        self.assertEqual(len({(h["id"], h["group"]) for h in meta["held_vessel"]}), len(meta["held_vessel"]))


class Meta(unittest.TestCase):
    """6"""

    @classmethod
    def setUpClass(cls):
        cls.meta = load_json("pipeline", "cache", "wpi_meta.json")
        cls.rows = cache_rows()
        cls.ports = [f["properties"] for f in load_json("data", "infrastructure", "ports.geojson")["features"]]

    def test_the_rule_is_the_extractors(self):
        self.assertEqual(self.meta["rule"], json.loads(json.dumps(X.RULE)))
        self.assertEqual(self.meta["rule"]["nearer_margin_km"], X.NEARER_MARGIN_KM)

    def test_the_counts_come_out_of_the_cache(self):
        c = self.meta["counts"]
        for by, key in (("code", "sure_code"), ("name", "sure_name"), ("review", "sure_review")):
            self.assertEqual(c[key], sum(1 for r in self.rows if r["by"] == by), key)
        self.assertEqual(self.meta["published"], len(self.rows))
        self.assertEqual(c["doubtful"], len(self.meta["doubtful"]))
        self.assertEqual(c["none"], len(self.meta["none"]))
        self.assertEqual(c["ports"], len(self.ports))
        self.assertEqual(c["sure_code"] + c["sure_name"] + c["sure_review"] + c["doubtful"] + c["none"], len(self.ports))

    def test_every_port_has_one_grade_and_only_ports_of_the_atlas_are_named(self):
        ids = {p["id"] for p in self.ports}
        sure = {r["port"] for r in self.rows}
        doubtful = {d["id"] for d in self.meta["doubtful"]}
        none = {d["id"] for d in self.meta["none"]}
        self.assertEqual(len(sure) + len(doubtful) + len(none), len(ids))
        self.assertEqual(sure | doubtful | none, ids)
        self.assertFalse(sure & doubtful or sure & none or doubtful & none)
        for d in self.meta["doubtful"] + self.meta["none"]:
            self.assertTrue(d["reason"].strip(), d["id"])

    def test_the_columns_used_are_the_file_columns_that_are_read(self):
        self.assertEqual(self.meta["columns_used"], FILE_COLUMNS)

    def test_the_terms_that_were_read_are_recorded_with_their_page_and_date(self):
        m = self.meta
        self.assertEqual(m["terms_quote"], "© COPYRIGHT 2017 BY THE UNITED STATES GOVERNMENT / NO COPYRIGHT CLAIMED UNDER TITLE 17 U.S.C.")
        self.assertTrue(m["terms_page"].startswith("https://web.archive.org/web/"))
        self.assertTrue(m["terms_page"].endswith("Pub150bk.pdf"))
        self.assertEqual(m["terms_read_on"], "2026-11-25")
        self.assertEqual(m["terms_scope"], "2017 PDF, 26th edition")
        self.assertEqual(m["source"], "nga-wpi")
        self.assertIn(m["source"], {s["id"] for s in load_json("data", "sources.json")})

    def test_the_archived_copy_is_recorded_with_its_day_and_its_address(self):
        m = self.meta
        self.assertEqual((m["captured"], m["captured_from"]), (X.CAPTURED, X.CAPTURED_FROM))
        self.assertEqual(m["captured"], "2026-09-29")
        # the address is the archive's capture of that day of the publisher's download address, and the day is the one in the address
        self.assertRegex(m["captured_from"], r"^https://web\.archive\.org/web/20260929\d{6}id_/https://msi\.nga\.mil/api/publications/download\?")
        self.assertIn(m["captured"].replace("-", ""), m["captured_from"])
        self.assertLess(m["captured"], m["downloaded"])

    def test_the_basis_of_the_draught_ratio_is_in_the_meta_and_holds_back_one_group(self):
        b = self.meta["rule_basis"]["draft_max_ratio"]
        self.assertEqual(self.meta["rule"]["draft_max_ratio"], X.DRAFT_MAX_RATIO)
        self.assertGreater(b["pairs"], 800)
        self.assertLess(b["median"], 0.1)
        self.assertLessEqual(b["largest_kept"]["ratio"], X.DRAFT_MAX_RATIO)
        self.assertLess(b["largest_kept"]["ratio"], X.DRAFT_MAX_RATIO * 0.8, "the ratio sits well above the largest one kept")
        self.assertEqual([(a["name"], a["group"]) for a in b["above"]], [("Tema", "offshore")])
        self.assertTrue(all(a["ratio"] > X.DRAFT_MAX_RATIO for a in b["above"]))
        held = [h for h in self.meta["held_vessel"] if "draught" in h["reason"]]
        self.assertEqual([(h["id"], h["group"]) for h in held], [("tema", "offshore")])

    def test_the_download_date_is_the_owners_and_the_edition_is_not_made_up(self):
        self.assertEqual(self.meta["downloaded"], "2026-11-24")
        self.assertEqual(self.meta["edition"], X.EDITION)
        self.assertEqual(self.meta["edition_page"], X.EDITION_PAGE)
        if self.meta["edition"] is None:
            self.assertIsNone(self.meta["edition_page"])

    def test_the_meta_text_is_what_the_extractor_writes(self):
        with open(META, encoding="utf-8") as f:
            self.assertEqual(f.read(), X.meta_text(self.meta))


class CacheAlone(unittest.TestCase):
    """7: runs without raw/"""

    @classmethod
    def setUpClass(cls):
        cls.meta = load_json("pipeline", "cache", "wpi_meta.json")
        cls.rows = cache_rows()
        cls.ports = {f["properties"]["id"]: f["properties"] for f in load_json("data", "infrastructure", "ports.geojson")["features"]}
        cls.countries = {c["c"]: c for c in load_json("data", "countries", "index.json")}

    def test_the_header_is_the_fixed_list(self):
        with open(PORTS_CSV, encoding="utf-8", newline="") as f:
            self.assertEqual(next(csv.reader(f)), CACHE_HEADER)
        self.assertEqual(X.HEADER, CACHE_HEADER)

    def test_the_file_is_utf8_with_unix_line_ends_and_sorted_by_port(self):
        raw = read_bytes(PORTS_CSV)
        self.assertNotIn(b"\r", raw)
        self.assertNotIn(b"\xef\xbb\xbf", raw[:3])
        raw.decode("utf-8")
        ids = [r["port"] for r in self.rows]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_port_of_the_cache_is_a_port_of_the_atlas_and_none_is_doubtful_or_absent(self):
        bad = {d["id"] for d in self.meta["doubtful"]} | {d["id"] for d in self.meta["none"]}
        for r in self.rows:
            self.assertIn(r["port"], self.ports)
            self.assertNotIn(r["port"], bad)

    def test_the_way_of_each_row(self):
        for r in self.rows:
            self.assertIn(r["by"], ("code", "name", "review"))
            self.assertEqual(bool(r["why"].strip()), r["by"] == "review", r["port"])
            self.assertGreater(float(r["km"]), -1)
            if r["by"] == "code":
                self.assertEqual(r["code"], self.ports[r["port"]]["locode"], r["port"])
                self.assertEqual(r["code"][:2], self.countries[self.ports[r["port"]]["c"]]["a2"], r["port"])
                self.assertLessEqual(float(r["km"]), X.CODE_KM, r["port"])
            if r["by"] == "name":
                self.assertLessEqual(float(r["km"]), X.NAME_KM, r["port"])
                self.assertFalse(r["code"] and r["code"] == self.ports[r["port"]].get("locode"), r["port"])

    def test_no_code_is_carried_by_two_published_rows(self):
        codes = [r["code"] for r in self.rows if r["code"]]
        self.assertEqual(len(codes), len(set(codes)), sorted(c for c in set(codes) if codes.count(c) > 1))

    def test_a_row_of_the_file_serves_one_port_only_unless_the_atlas_has_two_ports_there(self):
        keys = [(r["wpi"], r["name"]) for r in self.rows]
        dup = sorted(k for k in set(keys) if keys.count(k) > 1)
        self.assertEqual(dup, [], "two atlas ports with the same row")

    def test_every_figure_is_a_positive_number_and_none_is_zero(self):
        for r in self.rows:
            for k in FIGURE_KEYS:
                if r[k] != "":
                    self.assertRegex(r[k], r"^\d+(\.\d+)?$", f"{r['port']} {k}")
                    self.assertGreater(float(r[k]), 0, f"{r['port']} {k}")
                    self.assertNotEqual(r[k], "0.0")
            self.assertTrue(any(r[k] != "" for k in X.LIMITS), f"{r['port']} has no depth or maximum vessel figure")
            self.assertIn(r["pilot"], ("", "Yes", "No"))
            self.assertIn(r["tide_res"], ("", "Yes", "No"))
            self.assertIn(r["size"], ("", "Very Small", "Small", "Medium", "Large"))
            self.assertTrue(int(r["wpi"]) > 0 and r["name"].strip() and r["name"] == re.sub(r"\s+", " ", r["name"]).strip())

    def test_no_value_stands_for_not_stated(self):
        for r in self.rows:
            for k in FIGURE_KEYS + ["size", "type", "pilot", "tide_res"]:
                self.assertNotIn(r[k], ("0", "0.0", "Unknown", " "), f"{r['port']} {k}")

    def test_the_cache_is_small(self):
        self.assertLess(os.path.getsize(PORTS_CSV), 40_000)
        self.assertLess(os.path.getsize(META), 40_000)


class WithoutRaw(unittest.TestCase):
    """8"""

    def test_the_extractor_downloads_nothing(self):
        src = read_text("pipeline", "infrastructure", "extract_wpi.py")
        for word in ("urllib", "requests", "http.client", "socket", "curl", "wget", "urlopen"):
            self.assertNotIn(word, src)

    def test_the_readers_name_no_path_under_raw(self):
        import inspect
        for fn in (X.read_rows, X.extract, X.build, X.match, X.compare, X.atlas_ports):
            self.assertNotIn('"raw"', inspect.getsource(fn), fn.__name__)
        self.assertEqual(os.path.relpath(X.RAW, ROOT), os.path.join("raw", "nga", "UpdatedPub150.csv"))

    def test_without_the_file_the_extractor_exits_cleanly_and_leaves_the_cache_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            rels = ("pipeline/infrastructure/extract_wpi.py", "pipeline/cache/wpi_ports.csv", "pipeline/cache/wpi_meta.json")
            for rel in rels:
                os.makedirs(os.path.dirname(os.path.join(tmp, rel)), exist_ok=True)
                shutil.copy(os.path.join(ROOT, rel), os.path.join(tmp, rel))
            before = {rel: read_bytes(os.path.join(tmp, rel)) for rel in rels[1:]}
            r = subprocess.run([sys.executable, "-I", "-B", os.path.join(tmp, rels[0])], capture_output=True, text=True, cwd=tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("is not here", r.stdout)
            for rel, b in before.items():
                self.assertEqual(read_bytes(os.path.join(tmp, rel)), b, rel)
                self.assertEqual(read_bytes(os.path.join(ROOT, rel)), b, "the copy is the tracked cache")
            self.assertEqual(sorted(os.listdir(os.path.join(tmp, "pipeline", "cache"))), ["wpi_meta.json", "wpi_ports.csv"])


class Registry(unittest.TestCase):
    """9"""

    @classmethod
    def setUpClass(cls):
        cls.src = next(s for s in load_json("data", "sources.json") if s["id"] == "nga-wpi")
        cls.meta = load_json("pipeline", "cache", "wpi_meta.json")

    def test_the_licence_text_says_the_terms_of_the_file_were_not_read_and_are_to_be_confirmed(self):
        t = self.src["licence"]
        self.assertRegex(t, r"not read")
        self.assertIn("terms to be confirmed", t)
        self.assertIn("edition of the file used is not stated", t)
        self.assertIn("twenty-sixth edition (2017)", t)

    def test_the_licence_says_the_file_is_an_archived_copy_and_claims_no_terms_of_the_archive(self):
        t = self.src["licence"]
        self.assertIn(f"the Internet Archive's copy, captured on {long_date(X.CAPTURED)}, of the publisher's download address", t)
        self.assertIn("no terms of the Internet Archive's own for that file were read (none is claimed)", t)
        self.assertIn("terms to be confirmed", t)
        a = self.src["access"]
        self.assertIn(X.CAPTURED_FROM, a)
        self.assertIn(f"captured on {long_date(X.CAPTURED)}", a)
        self.assertNotRegex(a, r"(?i)downloaded by a person from msi\.nga\.mil")

    def test_the_sentence_is_quoted_as_the_meta_records_it_with_its_address_and_date(self):
        t = self.src["licence"]
        self.assertIn(self.meta["terms_quote"], t)
        self.assertIn(self.meta["terms_page"], t)
        self.assertIn("read 25 November 2026", t)
        self.assertEqual(self.meta["terms_read_on"], "2026-11-25")

    def test_no_word_grants_a_permission(self):
        for field in ("licence", "update", "access", "use"):
            self.assertNotRegex(self.src[field], r"(?i)public domain|open licen[cs]e|free to reuse|free to use", field)
        doc = read_text("DATA_SOURCES.md")
        for line in doc.splitlines():
            if "nga-wpi" in line or "World Port Index" in line:
                self.assertNotRegex(line, r"(?i)public domain|open licen[cs]e|free to reuse", line)

    def test_the_access_text_quotes_the_columns_the_meta_counts(self):
        a = self.src["access"]
        self.assertIn(f"{len(self.meta['columns_used'])} of the {self.meta['file']['columns']} columns", a)
        self.assertIn("pipeline/infrastructure/extract_wpi.py", a)
        self.assertIn("pipeline/cache/wpi_ports.csv", a)
        self.assertIn("never by a scheduled job", a)

    def test_the_data_sources_table_is_the_registrys(self):
        doc = read_text("DATA_SOURCES.md")
        start, end = doc.index(sources_table.START), doc.index(sources_table.END) + len(sources_table.END)
        self.assertEqual(doc[start:end], sources_table.render(load_json("data", "sources.json")))

    def test_no_workflow_runs_the_extractor(self):
        wf = os.path.join(ROOT, ".github", "workflows")
        for name in os.listdir(wf):
            self.assertNotIn("extract_wpi", read_text(".github", "workflows", name), name)


# ------------------------------------------------------------------------------------------------------------------------------ the data file
def fixture_cache(rows):
    """The text of a cache with these rows (dicts; a missing column is empty)."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(W.HEADER)
    for r in rows:
        w.writerow([r.get(k, "") for k in W.HEADER])
    return buf.getvalue()


def fixture_row(port, **kw):
    return {"port": port, "wpi": "100", "name": "Testport", "code": "AAXXX", "by": "code", "km": "1.5", "size": "Medium", "type": "River (Natural)",
            "tide": "3", "chan": "14", "anch": "4.9", "pier": "17.1", "pilot": "Yes", "tide_res": "No", **kw}


def fixture_meta(**kw):
    return {"source": "nga-wpi", "downloaded": "2026-11-24", "edition": None, "doubtful": [{"id": "dd"}], "none": [{"id": "nn"}],
            "held_vessel": [{"id": "hh", "group": "maximum", "reason": "x"}], "published": 2, **kw}


FIXTURE_PORTS = {"aa", "bb", "hh", "dd", "nn"}


class DataFile(unittest.TestCase):
    """10: runs without raw/"""

    @classmethod
    def setUpClass(cls):
        cls.meta = load_json("pipeline", "cache", "wpi_meta.json")
        cls.rows = cache_rows()
        cls.text = read_text("data", "infrastructure", "wpi.json")
        cls.doc = json.loads(cls.text)
        cls.port_ids = W.port_ids()
        cls.countries = {c["c"]: c for c in load_json("data", "countries", "index.json")}
        cls.atlas = {f["properties"]["id"]: f["properties"] for f in load_json("data", "infrastructure", "ports.geojson")["features"]}

    def test_the_file_is_what_the_builder_makes_from_the_two_cache_files(self):
        doc = W.build(read_text("pipeline", "cache", "wpi_ports.csv"), self.meta, self.port_ids)
        self.assertEqual(doc, self.doc)
        self.assertEqual(W.render(doc), self.text)
        self.assertEqual(read_bytes(os.path.join(ROOT, "data", "infrastructure", "wpi.json")), W.render(doc).encode("utf-8"))

    def test_two_runs_give_the_same_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            outs = []
            for i in (1, 2):
                out = os.path.join(tmp, f"wpi{i}.json")
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(W.main(out_path=out), 0)
                outs.append(read_bytes(out))
            self.assertEqual(outs[0], outs[1])
            self.assertEqual(outs[0], read_bytes(os.path.join(ROOT, "data", "infrastructure", "wpi.json")))
            self.assertEqual(sorted(os.listdir(tmp)), ["wpi1.json", "wpi2.json"], "no temporary file is left")

    def test_the_columns_the_builder_knows_are_the_extractors_and_the_fixed_list(self):
        self.assertEqual(W.HEADER, X.HEADER)
        self.assertEqual(W.HEADER, CACHE_HEADER)
        self.assertEqual(W.FIGURES, X.FIGURES)
        self.assertEqual(W.FIGURES, FIGURE_KEYS)
        self.assertEqual(W.LIMITS, X.LIMITS)
        self.assertEqual(sorted(col for _, col in W.KEYS), sorted(c for c in CACHE_HEADER if c != "port"))

    def test_the_top_level_is_the_source_the_month_and_the_edition(self):
        self.assertEqual(list(self.doc), ["s", "read", "captured", "edition", "ports"])
        self.assertEqual(self.doc["s"], self.meta["source"])
        self.assertEqual(self.doc["captured"], self.meta["captured"])
        self.assertRegex(self.doc["captured"], r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
        self.assertIn(self.doc["s"], {s["id"] for s in load_json("data", "sources.json")})
        self.assertEqual(self.doc["read"], self.meta["downloaded"][:7])
        self.assertRegex(self.doc["read"], r"^\d{4}-(0[1-9]|1[0-2])$")
        self.assertEqual(self.doc["edition"], self.meta["edition"])

    def test_the_ports_are_the_published_rows_of_the_cache_and_none_other(self):
        self.assertEqual(list(self.doc["ports"]), [r["port"] for r in self.rows])
        self.assertEqual(len(self.doc["ports"]), self.meta["published"])
        gone = {d["id"] for d in self.meta["doubtful"]} | {d["id"] for d in self.meta["none"]}
        self.assertEqual(gone & set(self.doc["ports"]), set())
        for pid in self.doc["ports"]:
            self.assertEqual(self.atlas[pid]["type"], "port", pid)

    def test_each_entry_says_what_the_cache_says_and_nothing_it_does_not(self):
        for r in self.rows:
            e = self.doc["ports"][r["port"]]
            for key, col in W.KEYS:
                if r[col] == "":
                    self.assertNotIn(key, e, f"{r['port']} {key}")
                elif col in FIGURE_KEYS or key in ("n", "km"):
                    self.assertEqual(e[key], float(r[col]), f"{r['port']} {key}")
                    self.assertNotIsInstance(e[key], bool)
                else:
                    self.assertEqual(e[key], r[col], f"{r['port']} {key}")
            self.assertEqual(set(e), {key for key, col in W.KEYS if r[col] != ""}, r["port"])

    def test_no_entry_has_a_key_the_data_check_would_read_as_a_source_or_a_figure(self):
        for pid, e in self.doc["ports"].items():
            for k in ("s", "y", "v"):
                self.assertNotIn(k, e, pid)

    def test_no_value_is_zero_null_or_empty(self):
        for pid, e in self.doc["ports"].items():
            for k, v in e.items():
                self.assertIsNotNone(v, f"{pid} {k}")
                self.assertNotEqual(v, "", f"{pid} {k}")
                if isinstance(v, (int, float)):
                    self.assertGreater(v, 0, f"{pid} {k}") if k != "km" else self.assertGreaterEqual(v, 0)
                    if isinstance(v, float):
                        self.assertFalse(v.is_integer(), f"{pid} {k} is written as a float with no fraction")

    def test_the_way_of_each_entry_follows_the_meta_and_the_atlas(self):
        for pid, e in self.doc["ports"].items():
            self.assertIn(e["by"], ("code", "name", "review"))
            self.assertEqual("why" in e, e["by"] == "review", pid)
            if e["by"] == "review":
                self.assertEqual(e["why"], next(r["why"] for r in self.rows if r["port"] == pid))
            if e["by"] == "code":
                self.assertEqual(e["lc"], self.atlas[pid]["locode"], pid)
                self.assertEqual(e["lc"][:2], self.countries[self.atlas[pid]["c"]]["a2"], pid)

    def test_every_entry_has_a_depth_or_a_maximum_vessel(self):
        for pid, e in self.doc["ports"].items():
            self.assertTrue(any(k in e for k in W.LIMITS), pid)

    def test_the_ports_held_back_for_their_maximum_vessel_have_none(self):
        held = [h for h in self.meta["held_vessel"] if h["group"] == "maximum"]
        self.assertTrue(held)
        for h in held:
            e = self.doc["ports"].get(h["id"])
            self.assertIsNotNone(e, f"{h['id']} is held for its maximum vessel and keeps its depths")
            for k in ("loa", "beam", "draft"):
                self.assertNotIn(k, e, h["id"])
        for group, keys in (("maximum", ("loa", "beam", "draft")), ("offshore", ("oloa", "obeam", "odraft"))):
            for h in (h for h in self.meta["held_vessel"] if h["group"] == group):
                for k in keys:
                    self.assertNotIn(k, self.doc["ports"][h["id"]], h["id"])

    def test_no_port_shows_a_beam_the_check_refuses(self):
        for pid, e in self.doc["ports"].items():
            for length, beam in (("loa", "beam"), ("oloa", "obeam")):
                if beam in e:
                    self.assertIn(length, e, pid)
                    self.assertIsNone(X.plausible(e[length], e[beam]), pid)

    def test_no_port_shows_a_draught_the_check_refuses(self):
        for pid, e in self.doc["ports"].items():
            for length, beam, draft in (("loa", "beam", "draft"), ("oloa", "obeam", "odraft")):
                self.assertIsNone(X.plausible(e.get(length, 0), e.get(beam, 0), e.get(draft, 0)), pid)

    def test_tema_keeps_its_berth_figures_and_loses_its_offshore_group_and_forcados_has_no_entry(self):
        tema = self.doc["ports"]["tema"]
        self.assertTrue(all(k in tema for k in ("loa", "beam", "draft")))
        self.assertFalse(any(k in tema for k in ("oloa", "obeam", "odraft")))
        self.assertIn({"id": "tema", "group": "offshore", "reason": f"the draught is above {X.DRAFT_MAX_RATIO:.0%} of the length"}, self.meta["held_vessel"])
        self.assertNotIn({"id": "tema", "group": "maximum"}, [{k: h[k] for k in ("id", "group")} for h in self.meta["held_vessel"]])
        self.assertNotIn("forcados", self.doc["ports"])
        d = next(x for x in self.meta["doubtful"] if x["id"] == "forcados")
        self.assertRegex(d["reason"], r"^two rows of the file carry the name within 60 km: no\. \d+ Forcados at 9\.1 km and no\. \d+ Forcados Oil Terminal at 27\.5 km$")

    def test_the_file_is_small_and_measured(self):
        n = os.path.getsize(os.path.join(ROOT, "data", "infrastructure", "wpi.json"))
        self.assertLess(n, 60_000)
        self.assertGreater(n, 10_000)


class BuilderStops(unittest.TestCase):
    """11: each way the cache can be wrong stops the build; nothing is written"""

    def build(self, rows, meta=None, ports=None, text=None):
        return W.build(text if text is not None else fixture_cache(rows), meta or fixture_meta(), FIXTURE_PORTS if ports is None else ports)

    def good_rows(self):
        return [fixture_row("aa"), fixture_row("bb", wpi="200", by="review", why="a sentence", code="", chan="", loa="300", beam="45", draft="11.8")]

    def test_a_good_cache_builds_and_the_entries_say_what_the_rows_say(self):
        doc = self.build(self.good_rows())
        self.assertEqual(doc["s"], "nga-wpi")
        self.assertEqual(doc["read"], "2026-11")
        self.assertIsNone(doc["edition"])
        self.assertEqual(doc["ports"]["aa"], {"n": 100, "name": "Testport", "lc": "AAXXX", "by": "code", "km": 1.5, "size": "Medium", "type": "River (Natural)",
                                              "tide": 3, "chan": 14, "anch": 4.9, "pier": 17.1, "pilot": "Yes", "tideRes": "No"})
        self.assertEqual(doc["ports"]["bb"], {"n": 200, "name": "Testport", "by": "review", "km": 1.5, "why": "a sentence", "size": "Medium",
                                              "type": "River (Natural)", "tide": 3, "anch": 4.9, "pier": 17.1, "loa": 300, "beam": 45, "draft": 11.8,
                                              "pilot": "Yes", "tideRes": "No"})
        self.assertEqual(list(doc["ports"]["bb"])[:5], ["n", "name", "by", "km", "why"])

    def test_the_edition_typed_in_the_meta_goes_through_and_the_month_is_the_download_months(self):
        doc = self.build(self.good_rows(), fixture_meta(edition="a typed edition", downloaded="2027-01-31"))
        self.assertEqual((doc["edition"], doc["read"]), ("a typed edition", "2027-01"))

    def test_the_capture_day_of_an_archived_copy_goes_through_beside_the_month_and_a_file_from_the_publisher_has_none(self):
        doc = self.build(self.good_rows(), fixture_meta(captured="2026-09-29"))
        self.assertEqual(list(doc), ["s", "read", "captured", "edition", "ports"])
        self.assertEqual((doc["read"], doc["captured"]), ("2026-11", "2026-09-29"))
        for meta in (fixture_meta(), fixture_meta(captured=None)):
            self.assertNotIn("captured", self.build(self.good_rows(), meta))
        for bad in ("2026-09", "2026-13-01", "29 September 2026", ""):
            with self.assertRaisesRegex(W.Stop, "captured"):
                self.build(self.good_rows(), fixture_meta(captured=bad))

    def stops(self, pattern, rows=None, **kw):
        with self.assertRaisesRegex(W.Stop, pattern):
            self.build(rows if rows is not None else self.good_rows(), **kw)

    def test_a_changed_header_stops_the_build(self):
        text = fixture_cache(self.good_rows()).replace("tide_res", "tide_restriction", 1)
        self.stops("header", text=text)
        self.stops("header", text="")
        self.stops("header", text=fixture_cache(self.good_rows()).replace(",why\n", ",why,extra\n", 1))

    def test_a_row_of_the_wrong_length_stops_the_build(self):
        self.stops("wrong number of cells", text=fixture_cache(self.good_rows()) + "cc,1\n")

    def test_a_port_the_atlas_lacks_stops_the_build(self):
        self.stops("not a port asset", ports={"aa"})

    def test_a_port_the_match_left_out_stops_the_build(self):
        rows = self.good_rows()
        rows[1]["port"] = "dd"
        self.stops("doubtful or without a match", rows)
        rows[1]["port"] = "nn"
        self.stops("doubtful or without a match", rows)

    def test_the_count_must_be_the_metas(self):
        self.stops("meta says 3", meta=fixture_meta(published=3))

    def test_the_rows_must_be_sorted_and_unique(self):
        self.stops("sorted by port", list(reversed(self.good_rows())))
        self.stops("sorted by port", [fixture_row("aa"), fixture_row("aa")])

    def test_a_figure_that_is_not_a_positive_number_stops_the_build(self):
        for bad in ("0", "0.0", "-3", "abc", "1e3", "14 m", "1,5", " 4"):
            rows = self.good_rows()
            rows[0]["chan"] = bad
            self.stops("not a number|not positive", rows)

    def test_an_entry_number_or_distance_that_is_not_a_number_stops_the_build(self):
        for col, bad in (("wpi", "0"), ("wpi", "12.5"), ("wpi", "x"), ("km", "-1"), ("km", "near")):
            rows = self.good_rows()
            rows[0][col] = bad
            self.stops("entry number|km", rows)

    def test_a_match_that_is_neither_code_name_nor_review_stops_the_build(self):
        rows = self.good_rows()
        rows[0]["by"] = "position"
        self.stops("by is", rows)

    def test_a_reason_goes_with_a_review_and_only_with_one(self):
        rows = self.good_rows()
        rows[0]["why"] = "a sentence"
        self.stops("if and only if", rows)
        rows = self.good_rows()
        rows[1]["why"] = " "
        self.stops("if and only if", rows)

    def test_a_class_or_flag_the_site_does_not_know_stops_the_build(self):
        for col, bad in (("size", "Huge"), ("pilot", "Unknown"), ("tide_res", "true")):
            rows = self.good_rows()
            rows[0][col] = bad
            self.stops(col, rows)

    def test_an_entry_with_no_depth_and_no_maximum_vessel_stops_the_build(self):
        rows = self.good_rows()
        for k in ("chan", "anch", "pier"):
            rows[0][k] = ""
        self.stops("no depth and no maximum vessel", rows)

    def test_a_held_port_with_a_maximum_vessel_figure_in_the_cache_stops_the_build(self):
        rows = [fixture_row("aa"), fixture_row("hh", loa="300")]
        self.stops("held back for its maximum vessel", rows, meta=fixture_meta())
        self.assertEqual(self.build([fixture_row("aa"), fixture_row("hh")])["ports"]["hh"]["chan"], 14)

    def test_a_stopped_run_writes_nothing_and_leaves_the_file_as_it_was(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, meta_path, ports_path, out = (os.path.join(tmp, n) for n in ("c.csv", "m.json", "p.geojson", "wpi.json"))
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                f.write(fixture_cache(self.good_rows()).replace("tide_res", "x", 1))
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(fixture_meta(), f)
            with open(ports_path, "w", encoding="utf-8") as f:
                json.dump({"type": "FeatureCollection", "features": [{"properties": {"id": i, "type": "port"}} for i in sorted(FIXTURE_PORTS)]}, f)
            with open(out, "w", encoding="utf-8") as f:
                f.write("the last file")
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(W.main(csv_path, meta_path, ports_path, out), 1)
            self.assertIn("nothing written", err.getvalue())
            self.assertEqual(read_text_at(out), "the last file")
            self.assertEqual(sorted(os.listdir(tmp)), ["c.csv", "m.json", "p.geojson", "wpi.json"])
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                f.write(fixture_cache(self.good_rows()))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(W.main(csv_path, meta_path, ports_path, out), 0)
            self.assertEqual(sorted(json.loads(read_text_at(out))["ports"]), ["aa", "bb"])

    def test_only_a_port_feature_is_a_port_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "p.geojson")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"features": [{"properties": {"id": "a", "type": "port"}}, {"properties": {"id": "b", "type": "mine"}}]}, f)
            self.assertEqual(W.port_ids(p), {"a"})


class BuilderOffline(unittest.TestCase):
    """11: the builder reads the tracked cache and the atlas's ports, never raw/"""

    def test_the_builder_names_no_path_under_raw_and_downloads_nothing(self):
        src = read_text("pipeline", "infrastructure", "wpi_limits.py")
        code = src.split('"""', 2)[2]  # what follows the module docstring
        self.assertNotRegex(code, r"raw")
        self.assertNotIn("UpdatedPub150", code)
        for word in ("urllib", "requests", "http.client", "socket", "curl", "wget", "urlopen", "extract_wpi", "subprocess"):
            self.assertNotIn(word, code)
        self.assertEqual({os.path.relpath(p, ROOT) for p in (W.PORTS_CSV, W.META, W.PORTS, W.OUT)},
                         {os.path.join("pipeline", "cache", "wpi_ports.csv"), os.path.join("pipeline", "cache", "wpi_meta.json"),
                          os.path.join("data", "infrastructure", "ports.geojson"), os.path.join("data", "infrastructure", "wpi.json")})

    def test_in_a_copy_without_raw_the_builder_gives_the_tracked_file_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            rels = ("pipeline/infrastructure/wpi_limits.py", "pipeline/cache/wpi_ports.csv", "pipeline/cache/wpi_meta.json", "data/infrastructure/ports.geojson")
            for rel in rels:
                os.makedirs(os.path.dirname(os.path.join(tmp, rel)), exist_ok=True)
                shutil.copy(os.path.join(ROOT, rel), os.path.join(tmp, rel))
            self.assertFalse(os.path.exists(os.path.join(tmp, "raw")))
            r = subprocess.run([sys.executable, "-I", "-B", os.path.join(tmp, rels[0])], capture_output=True, text=True, cwd=tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            made = read_bytes(os.path.join(tmp, "data", "infrastructure", "wpi.json"))
            self.assertEqual(made, read_bytes(os.path.join(ROOT, "data", "infrastructure", "wpi.json")))
            first = made
            subprocess.run([sys.executable, "-I", "-B", os.path.join(tmp, rels[0])], capture_output=True, text=True, cwd=tmp, check=True)
            self.assertEqual(read_bytes(os.path.join(tmp, "data", "infrastructure", "wpi.json")), first)
            self.assertFalse(os.path.exists(os.path.join(tmp, "raw")))

    def test_the_bootstrap_runs_the_builder_after_the_class_step_and_no_workflow_runs_it(self):
        boot = read_text("pipeline", "bootstrap.sh")
        self.assertLess(boot.index("infrastructure/port_limits.py"), boot.index("infrastructure/wpi_limits.py"))
        self.assertNotIn("extract_wpi", boot)
        wf = os.path.join(ROOT, ".github", "workflows")
        for name in os.listdir(wf):
            self.assertNotIn("wpi_limits", read_text(".github", "workflows", name), name)


class MaxClassUntouched(unittest.TestCase):
    """12"""

    @classmethod
    def setUpClass(cls):
        cls.ports = [f["properties"] for f in load_json("data", "infrastructure", "ports.geojson")["features"]]
        cls.classes = load_json("pipeline", "freight", "vessel_classes.json")

    def test_the_stored_class_of_every_port_is_what_port_limits_makes_from_its_limits(self):
        n = 0
        for p in self.ports:
            made = PL.max_class(p, self.classes)
            self.assertEqual(made, p.get("maxClass"), p["id"])
            n += made is not None
        self.assertGreater(n, 5)

    def test_no_limit_of_the_atlas_is_the_world_port_index_and_no_class_names_it(self):
        for p in self.ports:
            self.assertNotEqual((p.get("limits") or {}).get("s"), "nga-wpi", p["id"])
            self.assertNotRegex(json.dumps(p.get("maxClass") or {}), r"(?i)world port index|nga-wpi|wpi", p["id"])
            self.assertNotRegex(json.dumps(p.get("limits") or {}), r"(?i)world port index|nga-wpi", p["id"])

    def test_the_class_step_does_not_read_the_world_port_index(self):
        src = read_text("pipeline", "infrastructure", "port_limits.py")
        for word in ("wpi", "World Port Index", "nga-wpi"):
            self.assertNotIn(word, src)

    def test_the_builder_writes_only_wpi_json(self):
        code = read_text("pipeline", "infrastructure", "wpi_limits.py").split('"""', 2)[2]
        writes = [line.strip() for line in code.splitlines() if re.search(r"open\(.*[\"']w[\"']", line)]
        self.assertEqual(len(writes), 1, writes)
        self.assertIn("tmp", writes[0])
        self.assertIn("out_path", code)
        self.assertNotRegex(code, r"open\((PORTS|ports_path)[^)]*[\"']w")


# ------------------------------------------------------------------------------------------------------------------------------ the documents
PERMISSION = r"(?i)public domain|open licen[cs]e|free to reuse|free to use|freely (?:re)?us"


def flat(text):
    return re.sub(r"\s+", " ", text)


def methodology_block():
    """The paragraphs of METHODOLOGY.md, section 11, on the World Port Index: from 'World Port Index (port panel).' to the next run-in heading."""
    t = read_text("METHODOLOGY.md")
    a = t.index("World Port Index (port panel).")
    return t[a:t.index("Storage hubs.", a)]


def blocks_naming_the_source(text, by_line=False):
    """Every paragraph or list item (or, for a table, every line) of a text that names the World Port Index."""
    parts = text.splitlines() if by_line else re.split(r"\n\s*\n|\n(?=- |\* |### |## )", text)
    return [flat(x) for x in parts if re.search(r"World Port Index|nga-wpi", x)]


def updating_block():
    t = read_text("docs", "UPDATING.md")
    a = t.index("### World Port Index (by hand")
    return t[a:t.index("\n## ", a)]


def long_date(day):
    y, m, d = day.split("-")
    return f"{int(d)} {['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'][int(m) - 1]} {y}"


def about_text():
    return flat(read_text("web", "src", "components", "AboutDialog.tsx"))


class Documents(unittest.TestCase):
    """13"""

    @classmethod
    def setUpClass(cls):
        cls.meta = load_json("pipeline", "cache", "wpi_meta.json")
        cls.wpi = load_json("data", "infrastructure", "wpi.json")
        cls.ports = {f["properties"]["id"]: f["properties"] for f in load_json("data", "infrastructure", "ports.geojson")["features"]}
        cls.m = flat(methodology_block())

    # --- METHODOLOGY, section 11
    def test_the_counts_the_methodology_quotes_are_the_meta_files(self):
        c = self.meta["counts"]
        m = re.search(r"Of the (\d+) ports, (\d+) have an entry \((\d+) by code, (\d+) by name and (\d+) by review\), (\d+) are doubtful and (\d+) have "
                      r"no match; the (\d+) without an entry", self.m)
        self.assertIsNotNone(m, "the sentence on the counts is not there")
        got = tuple(int(x) for x in m.groups())
        self.assertEqual(got, (c["ports"], self.meta["published"], c["sure_code"], c["sure_name"], c["sure_review"], c["doubtful"], c["none"],
                               c["doubtful"] + c["none"]))
        self.assertEqual(c["sure_code"] + c["sure_name"] + c["sure_review"], self.meta["published"])
        self.assertEqual(len(self.wpi["ports"]), self.meta["published"])
        self.assertEqual(int(re.search(r"Each of the (\d+) ports of the atlas", self.m).group(1)), c["ports"])

    def test_the_nearer_row_and_held_back_counts_are_the_meta_files(self):
        nearer = [d for d in self.meta["doubtful"] if d["reason"].startswith("another row of the country is nearer")]
        self.assertEqual(int(re.search(r"Among the doubtful, (\d+) ports have another row", self.m).group(1)), len(nearer))
        held = {h["id"] for h in self.meta["held_vessel"]}
        self.assertEqual(int(re.search(r"holds back the maximum vessel of (\d+) ports", self.m).group(1)), len(held))
        self.assertGreater(len(nearer), 0)
        self.assertGreater(len(held), 0)

    def test_the_file_and_its_columns_are_the_meta_files(self):
        f = self.meta["file"]
        self.assertIn(f"a CSV of {f['rows']:,} rows and {f['columns']} columns", self.m)
        self.assertIn(f"keeps {len(self.meta['columns_used'])} of the {f['columns']} columns", self.m)
        y, mth, d = self.meta["downloaded"].split("-")
        month = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][int(mth) - 1]
        self.assertIn(f"on {int(d)} {month} {y}", self.m)

    def test_the_distances_and_the_check_are_the_constants_of_the_extractor(self):
        r = self.meta["rule"]
        self.assertEqual(r, X.RULE)
        g = lambda v: f"{v:g}"  # noqa: E731
        m = self.m
        self.assertIn(f"within {g(r['code_km'])} km of the atlas point", m)
        self.assertIn(f"or it lies within {g(r['nameless_km'])} km", m)
        self.assertIn(f"equal to the atlas name within {g(r['name_km'])} km", m)
        self.assertIn(f"by more than {g(r['nearer_margin_km'])} km: a port of several terminals", m)
        self.assertIn(f"between {g(r['name_km'])} and {g(r['name_far_km'])} km away", m)
        self.assertIn(f"more than {g(r['beam_max_ratio'] * 100)}% of its length or more than {g(r['beam_max_m'])} m", m)
        self.assertIn(f"its draught is more than {g(r['draft_max_ratio'] * 100)}% of its length", m)
        self.assertIn(f"carries an equal name within {g(r['name_twin_km'])} km", m)
        self.assertNotIn("it looks at the beam only", m)

    def test_the_basis_of_the_draught_ratio_is_the_meta_files(self):
        b = self.meta["rule_basis"]["draft_max_ratio"]
        self.assertIn(f"of the {b['pairs']} groups of its rows that give a length and a draught, the median is {b['median']} of the length and the largest "
                      f"is {b['largest_kept']['ratio']} apart from Tema's {b['above'][0]['ratio']:.2f}", self.m)
        self.assertEqual([a["name"] for a in b["above"]], ["Tema"])

    def test_the_example_of_forcados_is_the_meta_file(self):
        d = next(x for x in self.meta["doubtful"] if x["id"] == "forcados")
        km = re.findall(r"at (\d+\.\d) km", d["reason"])
        self.assertEqual(len(km), 2)
        self.assertIn(f"a river port Forcados {km[0]} km away and a row Forcados Oil Terminal {km[1]} km away", self.m)
        self.assertNotIn("forcados", self.wpi["ports"])

    def test_the_disagreeing_figures_are_counted_by_the_rule_the_methodology_states(self):
        key = {float(a): (float(b) if b != "null" else None) for a, b in re.findall(r"from: ([\d.]+), to: ([\d.]+|null)", read_text("web", "src", "lib", "wpi.ts"))}
        ports = set()
        for pid, e in self.wpi["ports"].items():
            printed = [(key[e[k]] if e[k] in key and key[e[k]] is not None else (float("inf") if e[k] in key and key[e[k]] is None and e[k] > 0 else e[k]))
                       for k in ("chan", "anch", "pier", "oil") if k in e] + ([e["lng"]] if "lng" in e else [])
            if printed and any(k in e and e[k] > max(printed) + e.get("tide", 0) for k in ("draft", "odraft")):
                ports.add(pid)
        self.assertEqual(int(re.search(r"In (\d+) ports a maximum vessel's draught is above the deepest depth printed", self.m).group(1)), len(ports))
        self.assertGreater(len(ports), 0)
        self.assertIn("the upper edge of a band counts as printed; the top band has none", self.m)

    def test_the_lng_depth_is_no_band_in_the_methodology(self):
        self.assertIn("The LNG terminal depth is a column of the CSV that the 2017 edition does not have", self.m)
        self.assertIn("one of the 22 the file gives sits on a floor of the key", self.m)
        self.assertIn("never as a band", self.m)
        self.assertNotIn("for the oil terminal and the LNG terminal", self.m)
        self.assertIn('for the oil terminal, "The greatest depth at chart datum will be shown"', self.m)

    def test_every_text_that_tells_where_the_file_came_from_says_it_is_the_archived_copy(self):
        day = long_date(X.CAPTURED)
        self.assertIsNotNone(X.CAPTURED)
        self.assertEqual(self.meta["captured"], X.CAPTURED)
        texts = {"METHODOLOGY.md": self.m, "NOTICE.md": next(b for b in blocks_naming_the_source(read_text("NOTICE.md")) if b.startswith("- **World Port Index (Pub. 150)")),
                 "docs/UPDATING.md": flat(updating_block()), "pipeline/infrastructure/README.md": flat(read_text("pipeline", "infrastructure", "README.md")),
                 "DATA_SOURCES.md": next(x for x in flat(read_text("DATA_SOURCES.md")).split(" - **") if x.startswith("NGA World Port Index")),
                 "extract_wpi.py": flat(X.__doc__)}
        for name, t in texts.items():
            self.assertIn(day, t, name)
            self.assertIn("Internet Archive", t, name)
        self.assertIn(X.CAPTURED_FROM, flat(read_text("NOTICE.md")))
        # no document says the file was downloaded from the publisher's page while the file is the archive's copy
        for name in ("METHODOLOGY.md", "NOTICE.md", "docs/UPDATING.md", "pipeline/infrastructure/README.md", "DATA_SOURCES.md", "data/sources.json"):
            text = read_text(*name.split("/"))
            for b in blocks_naming_the_source(text, by_line=name == "DATA_SOURCES.md"):
                self.assertNotRegex(b, r"(?i)\bdownloaded?s?\b[^.;]{0,90}\bfrom (?:the )?(?:<?(?:https://)?msi\.nga\.mil|publisher'?s? page)", f"{name}: {b[:120]}")
        for name in ("METHODOLOGY.md", "docs/UPDATING.md", "pipeline/infrastructure/README.md"):
            self.assertRegex(texts[name], r"(?i)neither an edition nor a date inside it|no edition and no date inside it|holds no date inside it", name)
        src = read_text("pipeline", "infrastructure", "extract_wpi.py")
        comment = next(line for line in src.splitlines() if line.startswith("DOWNLOADED ="))
        self.assertIn("Internet Archive", comment)
        self.assertNotIn("the file holds no date", comment)

    def test_the_sixteen_bands_are_the_formatters(self):
        key = read_text("web", "src", "lib", "wpi.ts")
        n = len(re.findall(r"\{ code: '[a-z]', from: [\d.]+, to: (?:[\d.]+|null) \}", key))
        words = {16: "sixteen"}
        self.assertEqual(self.m.count(f"The {words[n]} bands are typed once, in `web/src/lib/wpi.ts`"), 1, n)
        self.assertIn("with the address of the archived copy", self.m)
        self.assertIn(self.meta["terms_page"].split("/web/")[1].split("if_/")[1], key.replace("\n * ", ""))  # the key cites the same archived PDF

    def test_the_example_of_port_hedland_is_the_data(self):
        lim = self.ports["port-hedland"]["limits"]
        self.assertEqual(lim["draught"], 19.8)
        self.assertIn(f"a draft depth of {lim['draught']} m", self.m)
        chan = self.wpi["ports"]["port-hedland"]["chan"]
        key = read_text("web", "src", "lib", "wpi.ts")
        band = re.search(rf"\{{ code: '[a-z]', from: {chan:.1f}, to: ([\d.]+) \}}", key)
        self.assertIsNotNone(band, "the channel depth of the entry is not the floor of a band")
        self.assertIn(f"the band {chan:.1f} to {band.group(1)} m", self.m)

    def test_the_example_of_rotterdam_is_the_meta_file(self):
        d = next(x for x in self.meta["doubtful"] if x["id"] == "rotterdam")
        self.assertEqual(d["candidate"]["name"], "Rotterdam")
        self.assertNotIn("rotterdam", self.wpi["ports"])
        self.assertIn("the atlas shows no entry for Rotterdam", self.m)
        self.assertIn("EECV ore quay", self.ports["rotterdam"]["limits"]["n"])
        self.assertIn("ore quay of the Maasvlakte", self.m)

    def test_the_seven_assumptions_are_named_and_the_five_of_the_design_come_first(self):
        found = re.findall(r"^- \*\*A(\d)\.\*\* ", methodology_block(), flags=re.M)
        self.assertEqual(found, [str(i) for i in range(1, 8)])
        self.assertIn("**A1.** A value of 0.0 in the file means \"not stated\"", methodology_block())
        self.assertIn("is the twenty-sixth edition's (2017)", self.m)
        self.assertIn("The edition of the CSV is not stated", self.m)

    def test_the_hundred_metre_assumption_holds_in_the_data(self):
        for pid, e in self.wpi["ports"].items():
            for k in ("chan", "anch", "pier", "oil", "lng"):
                self.assertLess(e.get(k, 0), 100, f"{pid} {k}")

    def test_the_methodology_derives_no_class_and_names_the_choice_made_without_the_owner(self):
        self.assertIn("no class is derived from the World Port Index in this release", self.m)
        self.assertIn("a choice made without the owner, listed in `PROGRESS.md`", self.m)
        self.assertIn("never merged, averaged or reconciled", self.m)
        self.assertIn("not Atlas estimates", self.m)
        sec8 = read_text("METHODOLOGY.md").split("## 8. Discrepancies")[1].split("## 9.")[0]
        self.assertIn("page cited and the World Port Index are both shown", flat(sec8))

    def test_the_key_is_quoted_as_the_publication_words_it(self):
        for q in ("Depth information is generalized into 5-foot units, with the equivalents in meters", "Depths refer to chart datum",
                  "means a least depth of 31 feet (9.5 meters) or greater, but not as great as 36 feet (11.0 meters)",
                  "The controlling depth of the principal or deepest channel at chart datum is given",
                  "the least depth in the best or principal anchorage",
                  "The greatest depth at chart datum alongside the respective wharf/pier is given",
                  "The greatest depth at chart datum will be shown"):
            self.assertIn(f'"{q}"', self.m)

    # --- the terms, in every document
    def test_no_document_grants_a_permission_for_the_publication(self):
        docs = {"METHODOLOGY.md": read_text("METHODOLOGY.md"), "NOTICE.md": read_text("NOTICE.md"), "docs/UPDATING.md": read_text("docs", "UPDATING.md"),
                "pipeline/infrastructure/README.md": read_text("pipeline", "infrastructure", "README.md"), "README.md": read_text("README.md"),
                "DATA_SOURCES.md": read_text("DATA_SOURCES.md")}
        n = 0
        for name, text in docs.items():
            for b in blocks_naming_the_source(text, by_line=name == "DATA_SOURCES.md"):
                n += 1
                self.assertNotRegex(b, PERMISSION, f"{name}: {b[:120]}")
        self.assertGreater(n, 8)

    def test_the_notice_quotes_the_terms_the_meta_records_and_the_disclaimers(self):
        bullet = next(b for b in blocks_naming_the_source(read_text("NOTICE.md")) if b.startswith("- **World Port Index (Pub. 150)"))
        self.assertIn(self.meta["terms_quote"], bullet)
        self.assertIn(self.meta["terms_page"], bullet)
        self.assertIn("read 25 November 2026", bullet)
        self.assertEqual(self.meta["terms_read_on"], "2026-11-25")
        self.assertIn("(terms to be confirmed)", bullet)
        self.assertIn("Terms of the file used: not read", bullet)
        self.assertIn(f"for {self.meta['published']} ports", bullet)
        self.assertIn(f"{len(self.meta['columns_used'])} of its {self.meta['file']['columns']} columns", bullet)
        self.assertIn("a statement on that edition and not on the file used", bullet)
        for q in ("makes any warranty, express or implied, including the warranties of merchantability and fitness for a particular purpose",
                  "or assumes any legal liability or responsibility for the accuracy, completeness, or usefulness of any information",
                  "does not necessarily constitute or imply its endorsement, recommendation, or favoring by the United States Government or the "
                  "National Geospatial-Intelligence Agency",
                  "Federal law prohibits the use of the National Geospatial-Intelligence Agency's name, seal, initials, or any colorable imitation thereof, "
                  "to convey the impression of commercial endorsement by the Secretary of Defense, without written permission from the Secretary of Defense"):
            self.assertIn(q, bullet)
        self.assertIn("web.archive.org/web/20190721092351/https://msi.nga.mil/NGAPortal/MSI.portal", bullet)
        self.assertIn("they are not endorsed by NGA or by the United States Government", bullet)
        self.assertIn("The terms of use, and the edition, of the World Port Index file used", flat(read_text("NOTICE.md").split("## Questions of terms still open")[1]))

    def test_the_quoted_sentence_is_one_the_registry_the_meta_and_the_extractor_share(self):
        src = next(s for s in load_json("data", "sources.json") if s["id"] == "nga-wpi")
        self.assertEqual(self.meta["terms_quote"], X.TERMS_QUOTE)
        self.assertEqual(self.meta["terms_page"], X.TERMS_PAGE)
        self.assertEqual(self.meta["terms_read_on"], X.TERMS_READ_ON)
        self.assertIn(X.TERMS_QUOTE, src["licence"])
        self.assertIn(X.TERMS_PAGE, src["licence"])

    # --- docs/UPDATING.md
    def test_the_updating_section_names_the_constants_the_guards_and_the_three_files(self):
        u = flat(updating_block())
        for name in ("DOWNLOADED", "CAPTURED", "CAPTURED_FROM", "EDITION", "EDITION_PAGE", "TERMS_QUOTE", "TERMS_PAGE", "TERMS_READ_ON", "TERMS_SCOPE"):
            self.assertTrue(hasattr(X, name), name)
            self.assertIn(f"`{name}`", u)
        for path in ("pipeline/infrastructure/extract_wpi.py", "pipeline/infrastructure/wpi_limits.py", "pipeline/cache/wpi_ports.csv",
                     "pipeline/cache/wpi_meta.json", "data/infrastructure/wpi.json", "raw/nga/UpdatedPub150.csv"):
            self.assertIn(path, u)
            if not path.startswith("raw/"):
                self.assertTrue(os.path.exists(os.path.join(ROOT, path)), path)
        self.assertIn("--accept", u)
        self.assertIn(f"{len(X.COLUMNS)} it reads", u)
        self.assertIn(f"fewer than {X.ROWS_MIN:.0%} of the rows", u)
        self.assertIn(f"more than {X.PUBLISHED_DROP} ports fewer", u)
        self.assertIn(f"more than {X.CHANGED_SHARE:.0%} of the ports kept show a figure that moved by more than {X.CHANGED_BY:.0%}", u)
        self.assertIn("committed together", u)
        self.assertIn("the match rule, the review table and the equality of the cache with the raw file are not tested", u)
        self.assertIn("EDITION", u)
        self.assertNotRegex(u, PERMISSION)

    def test_the_updating_section_says_no_job_refreshes_it_and_no_workflow_does(self):
        u = flat(updating_block())
        self.assertIn("No scheduled job refreshes them", u)
        wf = os.path.join(ROOT, ".github", "workflows")
        for name in os.listdir(wf):
            text = read_text(".github", "workflows", name)
            for word in ("extract_wpi", "wpi_limits", "wpi.json", "wpi_meta"):
                self.assertNotIn(word, text, name)

    # --- the README of the infrastructure folder
    def test_the_readme_types_no_count_and_points_to_the_documents(self):
        t = read_text("pipeline", "infrastructure", "README.md")
        a = t.index("## World Port Index entries")
        sec = flat(t[a:t.index("\n## ", a + 5)])
        self.assertNotRegex(sec, r"\b\d+ (?:by code|by name|by review|doubtful)\b")
        for n in self.meta["counts"].values():
            self.assertNotRegex(sec, rf"\b{n} (?:ports|entries|rows)\b")
        for ref in ("docs/UPDATING.md", "METHODOLOGY.md", "NOTICE.md", "Documents", "test_wpi.py", "wpi_meta.json"):
            self.assertIn(ref, sec)
        self.assertIn("offered for no download", sec)
        self.assertIn("terms to be confirmed", sec)

    # --- the About window
    def test_the_about_credit_names_the_publisher_and_suggests_no_endorsement(self):
        t = about_text()
        i = t.index("<b>Port facts.</b>")
        credit = t[i:t.index("</li>", i)]
        for w in ("National Geospatial-Intelligence Agency", "no warranty", "not for navigation", "to be confirmed", "offers no download"):
            self.assertIn(w, credit)
        self.assertNotRegex(credit, PERMISSION)
        self.assertNotRegex(credit, r"(?i)endorsed by|approved by|certified by|in partnership|in cooperation|official")
        j = t.index("<b>No endorsement.</b>")
        no = t[j:t.index("</li>", j)]
        self.assertIn("National Geospatial-Intelligence Agency or any other publisher", no)
        self.assertIn("never used to suggest that the agency or the United States Government endorses the atlas", no)

    def test_the_about_window_types_no_count_of_the_block(self):
        t = about_text()
        i = t.index("<b>Port facts.</b>")
        credit = t[i:t.index("</li>", i)]
        self.assertNotRegex(credit, r"\b\d{2,3}\b ports")


if __name__ == "__main__":
    unittest.main()
