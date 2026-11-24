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
        """GC1.3: every row of every table of every commodity file (the main tables and every extra table, whatever package
        added it) is a line of its country's profile, in the section its key names, with its rank."""
        have = {os.path.basename(f)[:-5] for f in glob.glob(os.path.join(DATA, "countries", "profiles", "*.json"))}
        seen = set()
        for f in sorted(glob.glob(os.path.join(DATA, "commodities", "*.json"))):
            cid = os.path.basename(f)[:-5]
            if cid in ("index", "companies", "figures"):
                continue
            d = load(f"commodities/{cid}.json")
            if not isinstance(d, dict):
                continue
            tables = [(sec, d.get(sec)) for sec in ("exports", "imports", "production", "consumption", "reserves", "refinery")]
            tables += [(P.extra_section(x["key"]), x["table"]) for x in d.get("extra") or [] if x["key"] not in P.NO_PROFILE]  # tables left out of the profiles on purpose
            for sec, t in tables:
                if not t or not isinstance(t, dict) or not t.get("rows"):
                    continue
                self.assertIsNotNone(sec, (cid, "an extra table whose key names no section"))
                sec = "production" if sec == "refinery" else sec
                seen.add(sec)
                for i, r in enumerate(t["rows"]):
                    if r["c"] not in have:
                        continue
                    lines = [e for e in prof(r["c"]).get(sec, []) if e["k"] == cid and e["v"] == r["v"]]
                    self.assertTrue(lines, (cid, sec, r["c"]))
                    if not t.get("norank"):
                        self.assertIn(i + 1, [e.get("rank") for e in lines], (cid, sec, r["c"]))
        self.assertTrue({"stocks", "capacity"} <= seen, seen)

    def test_extra_tables_from_their_own_fields(self):
        self.assertEqual(P.extra_section("refined-products-production"), "production")
        self.assertEqual(P.extra_section("motor-gasoline-consumption"), "consumption")
        self.assertEqual(P.extra_section("stocks"), "stocks")
        self.assertEqual(P.extra_section("nuclear-capacity"), "capacity")
        self.assertIsNone(P.extra_section("balance"))
        self.assertEqual(P.extra_label("Top consumers — motor gasoline, EIA 2025", "consumption"), "Motor gasoline")
        self.assertEqual(P.extra_label("Natural gas plant liquids producers, EIA 2025 (not LPG alone)", "production"), "Natural gas plant liquids")
        self.assertEqual(P.extra_label("Unwrought aluminium exporters: not alloyed (HS 760110)", "exports"), "Unwrought aluminium: not alloyed (HS 760110)")
        self.assertIsNone(P.extra_label("Ending stocks", "stocks"))
        usa = prof("USA")
        lpg = next(e for e in usa["production"] if e.get("label") == "LPG")
        self.assertEqual((lpg["y"], lpg["s"]), (2014, "eia-intl"))  # a table dated long ago says its year
        al = next(e for e in usa["exports"] if e.get("label") == "Unwrought aluminium: not alloyed (HS 760110)")
        row = next(r for x in load("commodities/aluminium.json")["extra"] if x["key"] == "760110-exports" for r in x["table"]["rows"] if r["c"] == "USA")
        self.assertAlmostEqual(al["usd"], round(row["usd"] / 1e9, 3))  # the customs table's own value of the row
        wheat = next(e for e in prof("FRA")["production"] if e["k"] == "wheat" and e.get("scope"))
        self.assertEqual(wheat["scope"], "EU member states")  # a table of part of the world keeps its scope

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
        index = {c["c"] for c in load("countries/index.json")}
        for c in index:
            self.assertTrue(os.path.exists(os.path.join(DATA, "countries", "profiles", f"{c}.json")), c)
        # GC1.9: the light index the site never read is gone
        self.assertFalse(os.path.exists(os.path.join(DATA, "countries", "profiles.json")))

    def test_aland_in_the_words_of_natural_earth(self):
        """GC1.15: TYPE 'Country' with another sovereign is not called a dependency."""
        text = prof("ALA")["none"]
        self.assertIn("as a country under the sovereignty of Finland", text)
        self.assertNotIn("dependency", text)
        self.assertIn("as a dependency of the United Kingdom", P.ne_text("SGS", "South Georgia", True))

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

    def test_no_import_dependence_over_an_apparent_consumption(self):
        """GC1.7: the atlas's apparent consumption (production + imports - exports) holds the imports: no ratio over it."""
        for f in glob.glob(os.path.join(DATA, "countries", "profiles", "*.json")):
            with open(f, encoding="utf-8") as fh:
                p = json.load(fh)
            for b in p.get("balance", []):
                if "dep" in b:
                    cons = next(e for e in p["consumption"] if e["k"] == b["k"] and e["v"] == b["dep"]["cons"])
                    self.assertFalse(cons["s"] == "atlas" or cons.get("est"), (p["c"], b["k"]))
        self.assertFalse([b for b in prof("JPN")["balance"] if b["k"] == "steel" and "dep" in b])

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
        self.assertAlmostEqual(via["malacca"]["high"], round(high["malacca"] / sea, 4), places=4)
        self.assertGreater(via["malacca"]["low"], 0.5)
        # GC1.2: where the Hormuz page caps its crude "up to" at IMF PortWatch, Japan's is not printed, "at least" stays. Since package FNCB the cap
        # applies only while the atlas's "at least" tonnage of the type is at most 85% of PortWatch's volume: Hormuz tankers are at 90% in 2024, so the page
        # prints the uncapped figure and Japan's "up to" is printed with it
        self.assertGreater(high["hormuz"], low["hormuz"])
        self.assertFalse(via["hormuz"].get("capped"))
        self.assertAlmostEqual(via["hormuz"]["high"], round(high["hormuz"] / sea, 4), places=4)
        self.assertGreater(via["hormuz"]["high"], via["hormuz"]["low"])

    def test_no_country_up_to_above_the_cap_of_its_passage_page(self):
        """GC1.2: every country "up to" for a passage and a group is within what the passage page prints for that group."""
        pages = {(c["id"], e["p"]): e["mt"] for c in load("freight/chokepoints.json") for e in c.get("estimates") or []}
        n = 0
        for f in glob.glob(os.path.join(DATA, "countries", "profiles", "*.json")):
            with open(f, encoding="utf-8") as fh:
                p = json.load(fh)
            for side in ("exports", "imports"):
                for x in (p.get("freight") or {}).get(side, []):
                    for v in x.get("via", []):
                        self.assertFalse(v.get("capped") and v["high"] != v["low"], (p["c"], x["g"], v))
                        if v["high"] > v["low"]:
                            n += 1
                            mt = pages.get((v["id"], x["g"]))
                            self.assertIsNotNone(mt, (p["c"], x["g"], v["id"], "an up to where the passage page prints none"))
                            up = v["high"] * x["seaKt"] / 1000
                            self.assertLessEqual(up, mt[1] + 0.06 + 0.001 * mt[1], (p["c"], side, x["g"], v["id"], up, mt))
                        # the engine's floor on the printed figure: 2% of the seaborne tonnes or 1 Mt
                        self.assertTrue(v["high"] >= P.PASSAGE_MIN_SHARE or v["high"] * x["seaKt"] >= P.PASSAGE_MIN_KT * 0.999, (p["c"], x["g"], v))
        self.assertGreater(n, 1000)
        # the review's cases: USA crude imports through Panama, Australia's LNG through Makassar
        for iso, side, g, gate in (("AUS", "exports", "lng", "makassar"), ("CHN", "imports", "crude-oil", "taiwan-strait")):
            x = next(x for x in prof(iso)["freight"][side] if x["g"] == g)
            v = next((v for v in x["via"] if v["id"] == gate), None)
            self.assertTrue(v is None or v["high"] == v["low"], (iso, gate, v))
        # the Panama tankers are at 97% of PortWatch's volume in 2024 (package FNCB: no cap there): the page prints an "up to" for crude oil and so does the country
        x = next(x for x in prof("USA")["freight"]["imports"] if x["g"] == "crude-oil")
        v = next(v for v in x["via"] if v["id"] == "panama")
        self.assertGreater(v["high"], v["low"])

    def test_kazakhstan_crude_leaves_through_a_foreign_port(self):
        fr = next(x for x in prof("KAZ")["freight"]["exports"] if x["g"] == "crude-oil")
        self.assertEqual(fr["ports"][0]["c"], "RUS")
        self.assertGreater(fr["modes"]["transit"], 0.5)


class Basket(unittest.TestCase):
    def test_heading_names_come_from_all_subheadings(self):
        """GC1.4: no heading is named after its first six-digit description, and no name is typed by hand."""
        import pandas as pd
        desc = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "hs4_exports_desc.csv"), dtype=str).groupby("hs4")["description"].apply(list)
        self.assertFalse(hasattr(P, "HS4_LABEL"))
        name = lambda h: P.heading_name(desc[h])[0]  # noqa: E731
        self.assertTrue(name("8802").startswith("Helicopters; aeroplanes and other aircraft"))
        self.assertEqual(name("8703"), "Vehicles")  # not "specially designed for travelling on snow"
        self.assertEqual(name("8704"), "Vehicles: transport of goods")
        self.assertEqual(name("8708"), "Vehicles: parts")
        self.assertTrue(name("3002").startswith("Blood; vaccines; toxins"))
        self.assertTrue(name("8473").endswith("(parts and accessories)"))
        self.assertEqual(name("1001"), "Cereals: wheat")  # "other than durum" is not shared
        self.assertEqual(name("7102"), "Diamonds")  # "not mounted or set" is negated
        self.assertTrue(name("2709").startswith("Oils: petroleum oils"))  # one subheading: its own words
        for f in glob.glob(os.path.join(DATA, "countries", "profiles", "*.json")):
            with open(f, encoding="utf-8") as fh:
                p = json.load(fh)
            for side in ("exports", "imports"):
                for r in ((p.get("basket") or {}).get(side) or {}).get("rows", []):
                    subs = desc[r["hs4"]]
                    if len(subs) > 1:
                        self.assertNotIn(r["label"], subs, (p["c"], r["hs4"]))
                    self.assertNotEqual(r.get("k"), "thermal-coal")  # customs codes do not split the coals

    def test_hs4_extract_of_one_year_only(self):
        """GC1.14: the three HS4 files must hold one same year, the customs frame's."""
        import pandas as pd
        f = lambda y: pd.DataFrame({"t": [y]})  # noqa: E731
        self.assertEqual(P.hs4_year_of((f(2024), f(2024), f(2024)), 2024), 2024)
        self.assertIsNone(P.hs4_year_of((f(2024), f(2023), f(2023)), 2024))
        self.assertIsNone(P.hs4_year_of((f(2023), f(2023), f(2023)), 2024))
        with open(os.path.join(ROOT, "pipeline", "trade", "extract_hs4.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("os.replace", src)

    def test_iran_basket_says_what_it_leaves_out(self):
        """GC1.5: the all-goods basket and the key figures say that customs data do not record Iran's crude."""
        self.assertTrue([g for g in prof("IRN")["gaps"] if g["kind"] == "unrecorded" and g["k"] == "crude-oil"])
        with open(os.path.join(ROOT, "web", "src", "components", "views", "CountryBlocks.tsx"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("note={unrecordedNote(p)}", src)
        self.assertIn("the total and the shares leave them out", src)

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
            # the lines of the commodity's main production table (an extra table's line, such as coke, carries a label)
            prod = {e["k"] for e in p["production"] if not e.get("label") or e["label"] in P.PRODUCTION_LABEL.values()}
            for b in p.get("balance", []):
                if "hub" in b:
                    self.assertGreaterEqual(min(b["hub"]["exp"], b["hub"]["imp"]), P.HUB_MIN_SHARE)
                    self.assertIn(b["hub"]["prodS"], P.FULL_PRODUCTION_SOURCES)
                    self.assertNotIn(b["k"], prod)
        self.assertFalse([b for b in prof("FRA").get("balance", []) if b["k"] == "steel" and "hub" in b])  # USGS lists main producers only


class KeyFigures(unittest.TestCase):
    def test_top10_counts_the_lines_its_sources_name(self):
        """GC1.6: "World top-10 in" counts production, exports and imports, the sections whose sources it prints."""
        for f in glob.glob(os.path.join(DATA, "countries", "profiles", "*.json")):
            with open(f, encoding="utf-8") as fh:
                p = json.load(fh)
            if "none" in p:
                continue
            ks = {e["k"] for s in ("production", "exports", "imports") for e in p[s] if (e.get("rank") or 99) <= 10}
            self.assertEqual(p.get("top10", 0), len(ks), p["c"])
        self.assertNotIn("top10", prof("GRL"))  # its only top-10 line is a reserves line

    def test_two_largest_exports_each_say_what_they_are(self):
        """GC1.1: the largest export of all goods and the largest raw-material export among the atlas's commodities."""
        with open(os.path.join(ROOT, "web", "src", "components", "views", "CountryView.tsx"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('label="Largest export, all goods"', src)
        self.assertIn('label="Largest raw-material export"', src)
        self.assertNotIn("label={`Largest export`}", src)
        with open(os.path.join(ROOT, "METHODOLOGY.md"), encoding="utf-8") as fh:
            self.assertIn("Largest raw-material export", fh.read())
        twn = prof("TWN")
        self.assertEqual(twn["basket"]["exports"]["rows"][0]["hs4"], "8542")
        self.assertGreater(twn["basket"]["exports"]["rows"][0]["usd"], 200)

    def test_a_caveat_about_one_country_stays_on_its_line(self):
        """GC1.10: "The United States is converted..." (LPG) and "Kyrgyzstan: EIA raised..." (coal reserves)."""
        names = {c["c"]: c["name"] for c in load("countries/index.json")}
        t = {"caveat": "Kyrgyzstan: EIA raised its estimate"}
        self.assertTrue(P.caveat_concerns(t, "KGZ", names))
        self.assertFalse(P.caveat_concerns(t, "CHN", names))
        self.assertTrue(P.caveat_concerns({"caveat": "Gross weight of ores and compounds"}, "CHN", names))
        warns = [e.get("warn", "") for e in prof("JPN")["consumption"] + prof("GRL")["consumption"]]
        self.assertFalse([w for w in warns if w.startswith("The United States")])


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
        self.assertNotIn("years", p)  # GC1.9: the years of the series are in one file for every country
        ys = load("countries/years.json")[e["hk"]]
        self.assertEqual(len(e["hv"]), len(ys["y"]))
        self.assertEqual(e["hv"][-1], e["v"])
        self.assertIn(2010, ys["y"])


if __name__ == "__main__":
    unittest.main()
