"""Tests of the fixes after the independent review of the commodity pages (findings GW3.2 to GW3.12 and B1 to B3, builder side):
figures the atlas estimated or converted keep three significant digits and reproduce from the factor that is printed, rows that are
mostly an Atlas estimate say so, the "Other countries" row, short caveats on profile rows, no ".;" in a note, sources with a
link and an id, the spodumene exporters, and the label helper of the caveats.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_commodity_review.py"
The tests of the data files read the files as the builders last wrote them.
"""
import json
import math
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("trade", "freight", "commodities"):
    p = os.path.join(ROOT, "pipeline", sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd  # noqa: E402

import build_commodities as B  # noqa: E402
import caveats as CV  # noqa: E402
import checks as K  # noqa: E402
import hs_map  # noqa: E402

DATA = os.path.join(ROOT, "data")


def load(rel):
    with open(os.path.join(DATA, rel), encoding="utf-8") as f:
        return json.load(f)


def sig_digits(v):
    """Number of significant digits a printed figure can have: 14.0 -> 3, 1360 -> at most 3 (trailing zeros are not counted)."""
    s = f"{abs(v):.10g}".replace(".", "").lstrip("0").rstrip("0")
    return len(s)


class Helpers(unittest.TestCase):
    def test_sig_keeps_three_digits(self):
        self.assertEqual(B.sig(1543769.5), 1540000)
        self.assertEqual(B.sig(13.972), 14.0)
        self.assertEqual(B.sig(0.97583), 0.976)
        self.assertEqual(B.sig(582.08), 582)
        self.assertEqual(B.sig(77.57), 77.6)
        self.assertEqual(B.sig(7079.4), 7080)
        self.assertEqual(B.sig(0), 0)

    def test_ranked_rounds_estimated_rows_and_tables(self):
        t = B.ranked([("CHL", 13.972, "n", True), ("PER", 9.372, None, False)], 2024, "baci", "Mt", world=44.231)
        self.assertEqual([r["v"] for r in t["rows"]], [14.0, 9.372])  # the customs row keeps its digits
        self.assertTrue(t["rows"][0]["est"])
        self.assertNotIn("est", t["rows"][1])
        t = B.ranked([("AUS", 1356.34), ("CHE", 754.08)], 2024, "atlas", "t", world=7079.4, digits=3)
        self.assertEqual([r["v"] for r in t["rows"]], [1360, 754])
        self.assertEqual(t["world"], 7080)

    def test_joinn_drops_the_full_stop_before_the_semicolon(self):
        self.assertEqual(B.joinn("A sentence.", "next"), "A sentence; next")
        self.assertEqual(B.joinn("no stop", "next"), "no stop; next")
        self.assertEqual(B.joinn(None, "next"), "next")
        self.assertEqual(B.joinn("", "next"), "next")


class Conversions(unittest.TestCase):
    """The printed factor reproduces the printed figure (GW3.2)."""

    def test_potash_in_potassium_chloride(self):
        d = load("commodities/potash.json")
        f = round(K.K2O_IN_KCL, 4)
        self.assertIn(f"{f:.4f}", d["production"]["n"])
        k2o = next(x["table"] for x in d["extra"] if x["key"] == "k2o-production")
        self.assertEqual(d["production"]["world"], B.sig(k2o["world"] / f))
        for a, b in zip(k2o["rows"], d["production"]["rows"]):
            self.assertEqual(b["v"], B.sig(a["v"] / f), a["c"])
            self.assertLessEqual(sig_digits(b["v"]), 3)
        kpi = d["summary"]["production"]
        self.assertEqual((kpi["s"], kpi["v"]), ("atlas", d["production"]["world"]))
        self.assertLessEqual(sig_digits(kpi["v"]), 3)
        self.assertIn(f"{f:.4f}", kpi["n"])

    def test_lithium_carbonate_equivalent(self):
        d = load("commodities/lithium.json")
        pr = d["summary"]["production"]
        self.assertEqual(pr["alt"]["u"], "Mt LCE")
        self.assertIn(f"{B.LCE_PER_LI:.3f}", pr["alt"]["n"])
        self.assertEqual(pr["alt"]["v"], B.sig(pr["v"] * B.LCE_PER_LI / 1e6))
        self.assertLessEqual(sig_digits(pr["alt"]["v"]), 3)

    def test_lng_in_bcm_and_gas_in_lng_tonnes(self):
        d = load("commodities/lng.json")
        for k in ("exports", "seaborne"):
            f = d["summary"][k]
            self.assertEqual(f["alt"]["v"], B.sig(f["v"] * 1.36), k)
            self.assertIn("1.36 bcm", f["alt"]["n"])
        g = load("commodities/natural-gas.json")["summary"]
        self.assertEqual(g["exports"]["alt"]["v"], B.sig(g["exports"]["v"] / 1.36))
        self.assertEqual(g["exports"]["alt"]["u"], "Mt LNG equivalent")
        self.assertNotIn("alt", g["production"])  # not LNG output
        self.assertNotIn("alt", g["consumption"])

    def test_crude_conversions_reproduce_from_the_printed_factor(self):
        d = load("commodities/crude-oil.json")["summary"]
        p, x = d["production"], d["exports"]
        bpt = 7.33
        self.assertEqual(p["alt"]["v"], B.sig(p["v"] * 1e3 * (366 if B._isleap(p["y"]) else 365) / bpt / 1e6))
        self.assertEqual(x["alt"]["v"], B.sig(x["v"] * 1e6 * bpt / (366 if B._isleap(x["y"]) else 365) / 1e3))
        self.assertNotIn("world average", p["alt"]["n"])  # GW3.9: the ratio is EIA's United States series, not a world average
        self.assertIn("United States crude oil production", p["alt"]["n"])
        self.assertIn("other grades and other countries differ", p["alt"]["n"])

    def test_fine_metal_tables_have_three_digits_and_are_atlas(self):
        for cid in ("gold", "silver", "pgm"):
            d = load(f"commodities/{cid}.json")
            for sec in ("exports", "imports"):
                t = d[sec]
                self.assertEqual(t["s"], "atlas", (cid, sec))
                self.assertLessEqual(sig_digits(t["world"]), 3, (cid, sec))
                for r in t["rows"]:
                    self.assertLessEqual(sig_digits(r["v"]), 3, (cid, sec, r["c"]))
            k = d["summary"]["exports"]
            self.assertTrue(k["est"] and k["s"] == "atlas", cid)
            self.assertLessEqual(sig_digits(k["v"]), 3, cid)
            self.assertIn("Atlas estimate", k["n"], cid)  # the caveat follows the method note, it does not replace it
            for f in d["flows"]:
                self.assertLessEqual(sig_digits(f["v"]), 3, (cid, f["o"], f["d"]))


class EstimatedRows(unittest.TestCase):
    """A row that is mostly an Atlas estimate says so and is credited to the atlas (GW3.3)."""

    def test_chilean_concentrate(self):
        d = load("commodities/copper.json")
        r = d["exports"]["rows"][0]
        self.assertEqual(r["c"], "CHL")
        self.assertTrue(r["est"])
        self.assertTrue(r["n"].startswith("Atlas estimate:"))
        self.assertLessEqual(sig_digits(r["v"]), 3)
        self.assertIn("estimated from the declared value", r["n"])
        # a total of which a tenth or more is estimated says the share
        k = d["summary"]["exports"]
        self.assertIn("includes an Atlas estimate", k["n"])
        self.assertRegex(k["n"], r"\d+% of world tonnage is estimated")
        self.assertLessEqual(sig_digits(d["exports"]["world"]), 3)

    def test_every_row_above_half_estimated_is_marked_in_every_file(self):
        for f in os.listdir(os.path.join(DATA, "commodities")):
            if f in ("index.json", "companies.json"):
                continue
            d = load("commodities/" + f)
            tabs = [d.get(s) for s in ("production", "reserves", "consumption", "exports", "imports", "refinery")] + [x["table"] for x in d.get("extra") or []]
            for t in tabs:
                for r in (t or {}).get("rows", []):
                    m = re.match(r"(?:.*; )?(\d+)% of tonnage estimated from value", r.get("n", ""))
                    if m:
                        self.assertLess(int(m.group(1)), 50, (f, r["c"]))  # a mostly estimated row has the other wording and est

    def test_profile_row_follows(self):
        p = load("countries/profiles.json")["CHL"]
        e = next(x for x in p["exports"] if x["k"] == "copper" and x.get("label") == "Copper concentrate")
        self.assertEqual((e["s"], e["est"]), ("atlas", True))
        self.assertTrue(e["n"].startswith("Atlas estimate:"))
        # an ordinary customs row is not marked
        swiss = load("countries/profiles.json")["CHE"]
        self.assertTrue(all(not x.get("est") for x in swiss["exports"] if x["k"] == "wheat"))


class OtherCountries(unittest.TestCase):
    """USGS's own line stays in `other`, the countries the table names beyond the drawn rows are given apart (GW3.5)."""

    def test_steel(self):
        d = load("commodities/steel.json")
        t = d["production"]
        self.assertEqual(t["other"], 230)
        self.assertEqual(t["hidden"]["k"], len(t["rows"]) - B.SHOWN_ROWS)
        self.assertEqual(t["hidden"]["v"], round(sum(r["v"] for r in t["rows"][B.SHOWN_ROWS:]), 1))
        self.assertIn("Vietnam", t["hidden"]["n"])
        self.assertEqual(t["worldPublished"], 1900)
        self.assertEqual(t["world"], 1823)  # the shares rest on the sum of the lines
        k = d["summary"]["production"]
        self.assertEqual((k["v"], k["s"]), (1900, "usgs-mcs"))  # the key figure is the published total
        self.assertIn("1,823", k["n"])

    def test_gold_and_alumina(self):
        g = load("commodities/gold.json")["production"]
        self.assertEqual(g["other"], 1000)
        self.assertEqual(g["hidden"]["k"], 3)
        self.assertNotIn("worldPublished", g)
        self.assertNotIn("hidden", load("commodities/bauxite.json")["production"])  # not a full table

    def test_no_country_named_from_memory(self):
        txt = " ".join(load("commodities/steel.json")["notes"] + load("commodities/gold.json")["notes"])
        for name in ("Italy", "Mali", "Burkina Faso", "Tanzania", "Papua"):
            self.assertNotIn(name, txt)


class Notes(unittest.TestCase):
    def test_no_full_stop_before_a_semicolon(self):
        bad = []
        for f in os.listdir(os.path.join(DATA, "commodities")):
            with open(os.path.join(DATA, "commodities", f), encoding="utf-8") as fh:
                if re.search(r"\.; ", fh.read()):
                    bad.append(f)
        with open(os.path.join(DATA, "countries", "profiles.json"), encoding="utf-8") as fh:
            if re.search(r"\.; ", fh.read()):
                bad.append("profiles.json")
        self.assertEqual(bad, [])

    def test_lng_profile_rows_carry_the_short_caveat(self):
        lng = load("commodities/lng.json")
        self.assertGreater(len(lng["exports"]["caveat"]), 300)  # the page keeps the long one
        short = lng["exports"]["caveatShort"]
        self.assertLess(len(short), 100)
        rows = [e for p in load("countries/profiles.json").values() for sec in ("exports", "imports") for e in p[sec] if e["k"] == "lng"]
        self.assertTrue(rows)
        for e in rows:
            self.assertLess(len(e.get("warn", "")), 100)

    def test_natural_gas_does_not_say_the_same_thing_twice(self):
        t = load("commodities/natural-gas.json")["exports"]
        self.assertNotEqual(t["n"].count("LNG"), 0)
        self.assertNotIn("Pipeline gas and LNG together, as EIA", t["n"])
        self.assertIn("no LNG split by country", t["n"])

    def test_references_carry_their_link(self):
        lng = load("commodities/lng.json")
        text = lng["summary"]["exports"]["n"]
        self.assertIn("https://igu.org/igu-reports/2025-world-lng-report", text)
        self.assertIn("worldlngsummit.com", text)
        ru = " ".join(load("commodities/refined-products.json")["notes"])
        self.assertIn("https://www.eia.gov/international/analysis/country/RUS", ru)

    def test_sources_exist_and_say_what_they_allow(self):
        src = {s["id"]: s for s in load("sources.json")}
        igu = src["igu-lng-report-2025"]
        self.assertEqual(igu["url"], "https://igu.org/igu-reports/2025-world-lng-report")
        self.assertIn("terms to be confirmed", igu["licence"])  # the page states no terms: none is guessed
        self.assertIn("World LNG trade", src["giignl-2026"]["use"])
        # every source id of a commodity file is in the registry
        for f in os.listdir(os.path.join(DATA, "commodities")):
            if f in ("index.json", "companies.json"):
                continue
            ids = set(re.findall(r'"(?:s|usdS)": "([^"]+)"', open(os.path.join(DATA, "commodities", f), encoding="utf-8").read()))
            self.assertLessEqual(ids, set(src), (f, ids - set(src)))

    def test_russia_to_the_emirates_is_worded_for_the_extract(self):
        ru = " ".join(load("commodities/refined-products.json")["notes"])
        self.assertNotIn("Customs data record no flow from Russia", ru)
        self.assertIn("1,000 t or more", ru)

    def test_hub_caveats_are_hypotheses(self):
        for cid, secs in (("gold", ("exports", "imports")), ("silver", ("exports",)), ("pgm", ("exports", "imports")), ("refined-products", ("exports", "imports"))):
            d = load(f"commodities/{cid}.json")
            for sec in secs:
                self.assertIn("may rank high", d[sec]["caveat"], (cid, sec))
                self.assertNotIn("Includes", d[sec]["caveat"], (cid, sec))


class Spodumene(unittest.TestCase):
    def test_only_the_exporters_a_page_supports(self):
        _, exporters, importers, rest = hs_map.SPLIT["253090"]
        self.assertEqual(set(exporters), set(B.SPODUMENE_PAGES) | {"AUS"})  # a page is named for each (Australia: the ABS page)
        for c in exporters:
            self.assertIn("http", B.SPODUMENE_PAGES[c][2] if c != "AUS" else B.ABS_LITHIUM)
        d = load("commodities/lithium.json")
        t = next(x["table"] for x in d["extra"] if x["key"] == "spodumene-exports")
        self.assertEqual(sorted(r["c"] for r in t["rows"]), sorted(exporters))
        self.assertEqual(t["s"], "atlas")
        for r in t["rows"]:
            self.assertLessEqual(sig_digits(r["v"]), 3)
        notes = " ".join(d["notes"])
        for c, name in (("NGA", "Nigeria"), ("CAN", "Canada")):
            self.assertIn(name, notes.split("Not read as spodumene")[1])
        self.assertIn("Mali (no 2024 row)", notes)
        for url in ("kitco.com", "diariodocomercio.com.br", "news.metal.com"):
            self.assertIn(url, notes)

    def test_the_builder_splits_a_wider_cache_again(self):
        b = B.Baci()
        sp = b.group("spodumene")
        self.assertTrue(len(sp))
        self.assertTrue(sp["o"].isin(hs_map.SPLIT["253090"][1]).all())
        rest = b.group("minerals-nes")
        self.assertTrue(rest["o"].isin(("NGA", "MLI", "CAN")).any())  # the dropped exporters went to the rest of the code


class Labels(unittest.TestCase):
    def test_caveat_sentences_start_with_the_label_helper(self):
        self.assertEqual(K.cap_label("lpg"), "LPG")
        self.assertEqual(K.cap_label("lng"), "LNG")
        self.assertEqual(K.cap_label("dap"), "DAP")
        src = open(CV.__file__, encoding="utf-8").read()
        self.assertNotIn(".capitalize()", src)  # "Lpg", "Lng" or "Dap" at the start of a sentence

    def test_break_caveat_for_a_group_named_by_an_acronym(self):
        df = pd.DataFrame([("IRN", "TUR", y, t) for y, t in ((2022, 1.0e6), (2023, 0.9e6), (2024, 0.1e6))], columns=["o", "d", "year", "t"]).assign(group="lpg")
        c = CV.Ctx(df, [], 2024, None)
        text = CV._break("lpg", "IRN")(c)
        self.assertTrue(text.startswith("LPG exports of"), text)

    def test_profile_labels_of_cobalt_and_tin(self):
        import build_profiles as P
        self.assertEqual(P.TRADE_LABEL["cobalt"], "Cobalt intermediates and metal")
        self.assertEqual(P.TRADE_LABEL["tin"], "Tin (unwrought)")
        p = load("countries/profiles.json")
        seen = [e for pr in p.values() for sec in ("exports", "imports") for e in pr[sec] if e["k"] in ("cobalt", "tin")]
        self.assertTrue(seen)
        self.assertTrue(all(e.get("label") for e in seen))


class Armenia(unittest.TestCase):
    def test_a_country_without_a_profile_is_handled_by_the_page(self):
        """GW3.14: a country whose last row went keeps no entry; the country view shows its placeholder (CountryView.tsx reads
        `all?.[id] ?? null`, and null renders "No commodity in the atlas catalogue is significant for this country yet")."""
        profiles = load("countries/profiles.json")
        index = {c["c"] for c in load("countries/index.json")}
        self.assertIn("ARM", index)
        self.assertNotIn("ARM", profiles)
        self.assertGreater(len(index - set(profiles)), 50)  # most small countries have none: the page already copes
        src = open(os.path.join(ROOT, "web", "src", "components", "views", "CountryView.tsx"), encoding="utf-8").read()
        self.assertIn("all?.[id] ?? null", src)
        self.assertIn("No commodity in the atlas catalogue is significant for this country yet", src)


if __name__ == "__main__":
    unittest.main()
