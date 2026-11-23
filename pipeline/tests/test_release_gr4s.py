"""Checks of the fixes of the fourth release review (GR4S) on the published files of data/."""
import glob
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data")


def load(rel):
    with open(os.path.join(DATA, rel), encoding="utf-8") as f:
        return json.load(f)


def texts(o, skip=("url", "src", "access")):
    """Every string of a JSON document, the addresses left out."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k not in skip:
                yield from texts(v, skip)
    elif isinstance(o, list):
        for v in o:
            yield from texts(v, skip)
    elif isinstance(o, str):
        yield o


class VisitorWords(unittest.TestCase):
    """GR4S.3: what the site prints from data/ speaks a visitor's words."""

    DEV = re.compile(r"on disk|the file on disk|\bbuilder\b|\bcache\b|\bscript\b|\.py\b|INTL\.txt|the file lists|EIA file|USGS file", re.I)

    def test_commodity_texts(self):
        for p in glob.glob(os.path.join(DATA, "commodities", "**", "*.json"), recursive=True):
            for t in texts(load(os.path.relpath(p, DATA))):
                self.assertIsNone(self.DEV.search(t), (os.path.relpath(p, DATA), t[:120]))

    def test_monthly_gaps_are_in_the_notes(self):
        for cid in ("lng", "lpg", "refined-products"):
            gaps = load(f"commodities/monthly/{cid}.json").get("gaps") or []
            self.assertTrue(gaps, cid)
            notes = load(f"commodities/{cid}.json").get("notes") or []
            for g in gaps:
                self.assertIn(g, notes, cid)


class LngNote(unittest.TestCase):
    """GR4S.6: the GIIGNL address once in the headline note; the discrepancy is the head of that note, word for word."""

    def test_one_address_per_publication(self):
        d = load("commodities/lng.json")
        n = d["summary"]["exports"]["n"]
        self.assertEqual(n.count("2026-giignl-annual-report.pdf"), 1, n)
        self.assertIn("428 Mt in 2025 and 406 Mt in 2024", n)
        for x in d["discrepancies"]:
            self.assertIn(x, n)


class ChokepointFloors(unittest.TestCase):
    """GR4S.7: no "at least" in front of a zero."""

    def test_no_at_least_zero(self):
        for c in load("freight/chokepoints.json"):
            for e in c.get("estimates", []):
                n = e["f"]["n"]
                self.assertNotRegex(n, r"^at least (0 Mt|0\.0 kt|under 0\.1 kt)", (c["id"], e["p"]))
                if e["mt"][0] == 0:
                    self.assertTrue(n.startswith("no cargo has to cross it"), (c["id"], e["p"]))
                    if "hi" in e:
                        self.assertRegex(e["hi"]["n"], r"^up to [\d.,]+ (Mt|kt) may cross it", (c["id"], e["p"]))


class CappedFlows(unittest.TestCase):
    """GR4S.12: an estimate capped at the customs gross weight carries the flag, and its figure is the cap."""

    def test_cap_is_the_gross_weight(self):
        seen = 0
        for cid in ("gold", "silver", "pgm"):
            for f in load(f"commodities/{cid}.json")["flows"]:
                capped = "capped at the customs gross weight" in f.get("n", "")
                self.assertEqual(bool(f.get("cap")), capped, (cid, f["o"], f["d"]))
                if capped:
                    seen += 1
                    gross = float(re.search(r"customs gross weight ([\d,.]+) t", f["n"]).group(1).replace(",", ""))
                    self.assertAlmostEqual(f["v"], gross, delta=0.051 + 0.0005 * gross, msg=(cid, f["o"], f["d"]))
        self.assertGreater(seen, 0)
        che = next(f for f in load("commodities/gold.json")["flows"] if f["o"] == "CHE" and f["d"] == "CHN")
        self.assertEqual(che["v"], 365)


class FreightEstimatedPart(unittest.TestCase):
    """GR4S.12: a country's freight group with an estimated part says how much of it is estimated."""

    def test_est_kt(self):
        n = 0
        for p in glob.glob(os.path.join(DATA, "countries", "profiles", "*.json")):
            fr = load(os.path.relpath(p, DATA)).get("freight") or {}
            for x in fr.get("exports", []) + fr.get("imports", []):
                if x.get("estKt") is not None:
                    n += 1
                    self.assertTrue(x.get("est") and x.get("s") != "atlas", (p, x["g"]))
                    self.assertLessEqual(x["estKt"], x["kt"] + 0.05, (p, x["g"]))
                elif x.get("est"):
                    self.assertEqual(x.get("s"), "atlas", (p, x["g"]))
        self.assertGreater(n, 0)


class EventImpact(unittest.TestCase):
    """GR4S.8: background sentences of the new events are in their summary, word for word; the impact keeps the consequences."""

    MOVED = {
        "bdi-low-2016": "The index is a composite of the Capesize, Panamax and Supramax time-charter averages",
        "us-copper-tariff-2025": "a single foreign country controls over 50 percent of global copper smelting capacity",
        "oil-collapse-2014-2016": "Wikipedia attributes the surplus of crude oil to oversupply",
        "stellar-daisy-2017": "as the largest ship lost at sea",
        "russia-wheat-quota-2022": "the quota for the same period of 2021 was 17.5 million tonnes",
        "us-russian-energy-ban-2022": "nearly 700,000 barrels a day",
        "us-china-deal-2025": "The United States committed to remove 10 percentage points",
        "black-sea-tankers-2025": "the CPC handles more than one per cent of global oil",
        "cosco-dalian-2019": "not to its parent COSCO Shipping Corporation",
        "venezuela-oil-blockade-2025": "the Venezuelan economy is heavily reliant on oil exports",
    }

    def test_moved_to_summary(self):
        ev = {e["id"]: e for e in load("freight/events.json")}
        for eid, words in self.MOVED.items():
            self.assertIn(words, ev[eid]["summary"], eid)
            self.assertNotIn(words, ev[eid].get("impact", ""), eid)
        self.assertIn("deleted from the list on 31 January 2020", ev["cosco-dalian-2019"]["impact"])
        self.assertIn("Hezbollah", ev["venezuela-oil-blockade-2025"]["impact"])


if __name__ == "__main__":
    unittest.main()
