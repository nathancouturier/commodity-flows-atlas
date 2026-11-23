"""Country profiles built from the full data (audit C-097, C-098, C-108, M-083, M-084, M-092, M-093, M-096, A-063, C-105,
M-094, C-136): pipeline/commodities/build_profiles.py and pipeline/trade/extract_hs4.py."""
import glob
import json
import os
import struct
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities"):
    p = os.path.join(ROOT, "pipeline", sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import build_profiles as P  # noqa: E402

DATA = os.path.join(ROOT, "data")


def load(rel):
    with open(os.path.join(DATA, rel), encoding="utf-8") as f:
        return json.load(f)


def prof(iso):
    return load(f"countries/profiles/{iso}.json")


def largest_export(p):
    rows = [e for e in p["exports"] if e.get("usd") is not None]
    return max(rows, key=lambda e: e["usd"]) if rows else None


class FullLines(unittest.TestCase):
    def test_guyana_largest_export_is_crude_oil(self):
        top = largest_export(prof("GUY"))
        self.assertEqual(top["k"], "crude-oil")
        self.assertGreater(top["usd"], 10)  # bn USD, CEPII BACI 2024 (rice, 0.27 bn, was shown before)

    def test_every_table_row_is_a_line(self):
        """Every row of every main table of every commodity is a line of its country's profile, with its rank."""
        light = load("countries/profiles.json")
        for f in sorted(glob.glob(os.path.join(DATA, "commodities", "*.json"))):
            cid = os.path.basename(f)[:-5]
            if cid in ("index", "companies"):
                continue
            d = load(f"commodities/{cid}.json")
            for sec in ("exports", "imports", "production", "consumption", "reserves"):
                t = d.get(sec)
                if not t or not isinstance(t, dict):
                    continue
                for i, r in enumerate(t["rows"]):
                    if r["c"] not in light:
                        continue
                    lines = [e for e in prof(r["c"])[sec] if e["k"] == cid and e["v"] == r["v"]]
                    self.assertTrue(lines, (cid, sec, r["c"]))
                    if not t.get("norank"):
                        self.assertIn(i + 1, [e.get("rank") for e in lines], (cid, sec, r["c"]))

    def test_iran_shows_the_caveat_and_invents_no_crude(self):
        p = prof("IRN")
        self.assertFalse([e for e in p["exports"] if e["k"] == "crude-oil"])
        gap = next(g for g in p["gaps"] if g["id"] == "crude-irn")
        self.assertEqual(gap["text"], load("freight/caveats.json")["crude-irn"]["text"])

    def test_chile_has_iron_ore_and_imports(self):
        p = prof("CHL")
        self.assertTrue([e for e in p["exports"] if e["k"] == "iron-ore"])
        self.assertGreater(len(p["imports"]), 5)

    def test_taiwan_and_mozambique(self):
        self.assertGreater(len(prof("TWN")["exports"]), 5)
        ks = {e["k"] for e in prof("MOZ")["exports"]}
        self.assertTrue({"aluminium", "lng", "natural-gas", "thermal-coal"} <= ks, ks)

    def test_kuwait_lists_its_crude(self):
        self.assertEqual(largest_export(prof("KWT"))["k"], "crude-oil")

    def test_reserves_and_consumption(self):
        p = prof("GIN")
        bx = next(e for e in p["reserves"] if e["k"] == "bauxite")
        prod = next(e for e in p["production"] if e["k"] == "bauxite" and e.get("label") == "Bauxite")
        self.assertAlmostEqual(bx["rp"], round(bx["v"] / prod["v"], 1))
        self.assertTrue([e for e in prof("IND")["consumption"] if e["k"] == "thermal-coal"])


class EveryCountry(unittest.TestCase):
    def test_every_index_entry_has_a_file(self):
        light = load("countries/profiles.json")
        index = {c["c"] for c in load("countries/index.json")}
        self.assertEqual(index - set(light), set())
        for c in index:
            self.assertTrue(os.path.exists(os.path.join(DATA, "countries", "profiles", f"{c}.json")), c)

    def test_libya_has_its_crude_and_its_assets(self):
        p = prof("LBY")
        self.assertEqual(largest_export(p)["k"], "crude-oil")
        self.assertIn("pipeline:greenstream", p["infra"])

    def test_three_non_state_polygons_say_what_they_are(self):
        expect = {"KAS": "claimed by Pakistan and India", "SOL": "self-administered and claimed by Somalia",
                  "CYN": "self-administered and claimed by Cyprus"}
        for iso, words in expect.items():
            p = prof(iso)
            self.assertEqual(set(p), {"c", "none"})
            self.assertIn(words, p["none"])
            self.assertIn("no code of their own", p["none"])

    def test_natural_earth_words_match_the_base_map(self):
        dbf = os.path.join(ROOT, "raw", "naturalearth", "ne_50m", "ne_50m_admin_0_countries.dbf")
        if not os.path.exists(dbf):
            self.skipTest("raw/naturalearth not on disk")
        with open(dbf, "rb") as f:
            hdr = f.read(32)
            n, hl, rl = struct.unpack("<I", hdr[4:8])[0], struct.unpack("<H", hdr[8:10])[0], struct.unpack("<H", hdr[10:12])[0]
            fields = []
            while True:
                d = f.read(32)
                if d[0] == 0x0D:
                    break
                fields.append((d[:11].split(b"\0")[0].decode(), d[16]))
            f.seek(hl)
            seen = {}
            for _ in range(n):
                rec, pos, r = f.read(rl), 1, {}
                for name, ln in fields:
                    r[name] = rec[pos:pos + ln].decode("utf8", errors="replace").strip(" \0")
                    pos += ln
                c = r["ISO_A3_EH"] if r["ISO_A3_EH"] not in ("", "-99") else r["ADM0_A3"]
                seen[c] = (r["TYPE"], r["SOVEREIGNT"], r["NOTE_BRK"])
        for iso, st in P.NE_STATUS.items():
            self.assertEqual(seen[iso], st, iso)

    def test_eu_members_and_aggregate_link(self):
        self.assertEqual(prof("FRA")["eu"], "EU27")
        self.assertIn("FRA", prof("EU27")["members"])
        with open(os.path.join(ROOT, "web", "src", "map", "modules", "choropleth.ts"), encoding="utf-8") as f:
            src = f.read()
        block = src[src.index("export const EU27"):]
        block = block[:block.index("]")]
        self.assertEqual(sorted(P.EU27), sorted(x.strip(" '\n,") for x in block.split("[", 1)[1].split(",") if x.strip(" '\n,")))


class Partners(unittest.TestCase):
    def test_herfindahl_on_a_fixed_sample(self):
        self.assertEqual(P.hhi([1.0]), 10000)
        self.assertEqual(P.hhi([0.5, 0.5]), 5000)
        self.assertEqual(P.hhi([0.6, 0.3, 0.1]), 4600)
        rows = [("AUS", 60.0, False), ("MYS", 30.0, True), ("QAT", 10.0, False), ("USA", 0.0, False)]
        out = P.partner_rows(rows)
        self.assertEqual(out["hhi"], 4600)
        self.assertEqual([r["c"] for r in out["rows"]], ["AUS", "MYS", "QAT"])
        self.assertEqual(out["rows"][1], {"c": "MYS", "share": 0.3, "est": True})
        self.assertEqual(out["estShare"], 0.3)

    def test_japan_lng_suppliers_from_the_pairs_table(self):
        b = next(x for x in prof("JPN")["balance"] if x["k"] == "lng")
        pf = load("freight/pairs/lng.json")
        rows = [dict(zip(pf["cols"], r)) for r in pf["rows"]]
        mine = sorted((r for r in rows if r["d"] == "JPN"), key=lambda r: -r["kt"])
        tot = sum(r["kt"] for r in mine)
        self.assertEqual(b["suppliers"]["rows"][0]["c"], mine[0]["o"])
        self.assertAlmostEqual(b["suppliers"]["rows"][0]["share"], round(mine[0]["kt"] / tot, 4))
        self.assertEqual(b["suppliers"]["hhi"], round(sum((r["kt"] / tot) ** 2 for r in mine) * 10000))

    def test_import_dependence_only_with_the_same_unit_and_year(self):
        for iso in ("JPN", "EGY", "IND"):
            for b in prof(iso).get("balance", []):
                if "dep" in b:
                    self.assertNotEqual(b["k"], "crude-oil")  # imports in Mt (customs 2024), consumption in kb/d (EIA 2025)


class Freight(unittest.TestCase):
    def test_japan_crude_through_hormuz_and_malacca_by_hand(self):
        pf = load("freight/pairs/crude-oil.json")
        gates = pf["gates"]
        sea, low, high = 0.0, {"hormuz": 0.0, "malacca": 0.0}, {"hormuz": 0.0, "malacca": 0.0}
        for r in pf["rows"]:
            x = dict(zip(pf["cols"], r))
            if x["d"] != "JPN" or x["m"] not in (0, 1):
                continue
            sea += x["kt"]
            for g in low:
                bit = 1 << gates.index(g)
                if x["via"] & bit:
                    low[g] += x["kt"]
                    high[g] += x["kt"]
                elif x["alt"] & bit:
                    high[g] += x["kt"]
        fr = next(x for x in prof("JPN")["freight"]["imports"] if x["g"] == "crude-oil")
        via = {v["id"]: v for v in fr["via"]}
        for g in ("hormuz", "malacca"):
            self.assertAlmostEqual(via[g]["low"], round(low[g] / sea, 4), places=4)
            self.assertAlmostEqual(via[g]["high"], round(high[g] / sea, 4), places=4)
        self.assertGreater(via["malacca"]["low"], 0.5)
        self.assertGreater(via["hormuz"]["high"], via["hormuz"]["low"])

    def test_kazakhstan_crude_leaves_through_a_foreign_port(self):
        fr = next(x for x in prof("KAZ")["freight"]["exports"] if x["g"] == "crude-oil")
        self.assertEqual(fr["ports"][0]["c"], "RUS")
        self.assertGreater(fr["modes"]["transit"], 0.5)


class Basket(unittest.TestCase):
    def test_basket_shares_and_year(self):
        import pandas as pd
        tot = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "hs4_totals.csv"))
        baci_year = int(pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"), usecols=["year"])["year"].max())
        self.assertEqual(int(tot["t"].max()), baci_year)
        b = prof("FRA")["basket"]
        self.assertEqual(b["y"], baci_year)
        total = float(tot.loc[tot["c"] == "FRA", "exports"].iloc[0]) / 1e6
        self.assertAlmostEqual(b["exports"]["total"], round(total, 3))
        for r in b["exports"]["rows"]:
            self.assertAlmostEqual(r["share"], round(r["usd"] / b["exports"]["total"], 4), delta=2e-4)
        self.assertEqual(len(b["imports"]["rows"]), 10)

    def test_the_annual_job_rebuilds_the_hs4_tables(self):
        with open(os.path.join(ROOT, "pipeline", "annual", "update_annual.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"extract_hs4.py"', src)
        for f in ("hs4_exports.csv.gz", "hs4_imports.csv.gz", "hs4_totals.csv"):
            self.assertIn(f'"{f}"', src)
        self.assertFalse(os.path.exists(os.path.join(ROOT, "pipeline", "trade", "extract_hs4_exports.py")))
        with open(os.path.join(ROOT, "pipeline", "trade", "extract_hs4.py"), encoding="utf-8") as f:
            self.assertNotIn("V202601", f.read())


class CompaniesAndHubs(unittest.TestCase):
    def test_a_company_is_listed_under_every_commodity(self):
        glencore = next(c for c in prof("CHE")["companies"] if c["name"] == "Glencore")
        self.assertTrue({"copper", "thermal-coal", "zinc"} <= set(glencore["k"]))
        names = {c["name"] for c in prof("USA")["companies"]}
        self.assertTrue({"Cargill", "ADM", "Mosaic", "MP Materials"} <= names, names)

    def test_hub_is_derived_from_the_atlas_data(self):
        for iso in ("NLD", "SGP", "BEL"):
            p = prof(iso)
            prod = {e["k"] for e in p["production"]}
            for b in p.get("balance", []):
                if "hub" in b:
                    self.assertGreaterEqual(min(b["hub"]["exp"], b["hub"]["imp"]), P.HUB_MIN_SHARE)
                    self.assertIn(b["hub"]["prodS"], P.FULL_PRODUCTION_SOURCES)
                    self.assertNotIn(b["k"], prod)
        self.assertFalse([b for b in prof("FRA").get("balance", []) if b["k"] == "steel" and "hub" in b])  # USGS lists main producers only


class History(unittest.TestCase):
    def test_rank_of_a_year_follows_the_past_table_rule(self):
        h = {"years": [2020, 2021, 2022], "world": [10.0, 20.0, 10.0],
             "c": {"AAA": [5.0, 5.0, 5.0], "BBB": [3.0, 12.0, 3.0], "CCC": [2.0, 3.0, None]}, "out": {"BBB": [1]}}
        ser, worlds = P.series_at(h, "AAA")
        self.assertEqual(ser["hr"], [1, 1, 1])  # BBB's 2021 figure is out of line: not ranked above AAA
        self.assertEqual(worlds, [10.0, 8.0, 10.0])  # and the world of 2021 leaves it out
        ser, _ = P.series_at(h, "CCC")
        self.assertEqual(ser["hr"], [3, 2, None])
        self.assertEqual(P.series_at(h, "BBB")[0]["hout"], [1])

    def test_lines_carry_their_series(self):
        p = prof("CHN")
        e = next(x for x in p["imports"] if x["k"] == "iron-ore")
        ys = p["years"][e["hk"]]
        self.assertEqual(len(e["hv"]), len(ys["y"]))
        self.assertEqual(e["hv"][-1], e["v"])
        self.assertIn(2010, ys["y"])


if __name__ == "__main__":
    unittest.main()
