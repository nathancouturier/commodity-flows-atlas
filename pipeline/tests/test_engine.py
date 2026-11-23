"""Cross-package tests of the trade-engine plan (package E7-docs): the tests of section 12 that read the files of
several packages and that no package's own file holds, and the checks of the documentation and of the scheduled job.

- E01 one seaborne figure per group: lane file, pairs file, seaborne_totals.json and the commodity page agree.
- E02 the flow tables of the commodity pages (build_commodities.py) agree with the pairs table (build_lanes.py):
      mode, tonnage, estimate flag, lane link, transit; their caveat ids exist in data/freight/caveats.json.
- D10 (commodity part) no key "provisional" in any commodity file (the lane and pairs part is in test_lanes.py).
- W01 (data part) web/scripts/validate-data.mjs, with the freight and infrastructure validators, passes.
- E03 the annual job (pipeline/annual/update_annual.py): borders before lanes, every output of the freight builders
      in the snapshot of its step, no test and no check run by the job.
- E04 NOTICE.md lists every Wikipedia article cited by the gateway, transit, draught and mode tables;
      METHODOLOGY.md does not use the words "lower bound".

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_*.py"
A class is skipped when the files it reads are absent (a tree that has not been built, or no node on the PATH).
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from urllib.parse import quote, unquote

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("freight", "trade", "geo", "commodities", "annual"):
    p = os.path.join(ROOT, "pipeline", sub)
    if p not in sys.path:
        sys.path.insert(0, p)

DATA = os.path.join(ROOT, "data")
LANES = os.path.join(DATA, "freight", "lanes")
PAIRS = os.path.join(DATA, "freight", "pairs")
COMMOD = os.path.join(DATA, "commodities")
TOTALS = os.path.join(ROOT, "pipeline", "cache", "seaborne_totals.json")
BUILT = all(os.path.exists(p) for p in (PAIRS, LANES, TOTALS, os.path.join(DATA, "freight", "caveats.json")))
need_build = unittest.skipUnless(BUILT, "the lane and commodity builders have not written their files yet")
M_NAME = {0: "sea", 1: "sea", 2: "mixed", 3: "land"}

_cache = {}


def load_json(path):
    if path not in _cache:
        with open(path, encoding="utf-8") as f:
            _cache[path] = json.load(f)
    return _cache[path]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def lane_groups():
    return sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(PAIRS, "*.json")))


def commodity_pages():
    """(commodity id, document, lane group of its seaborne figure) for every page whose seaborne figure names a lane
    file; the flow table of such a page is that group's."""
    out = []
    for p in sorted(glob.glob(os.path.join(COMMOD, "*.json"))):
        d = load_json(p)
        sb = (d.get("summary") or {}).get("seaborne") if isinstance(d, dict) else None
        if not sb:
            continue
        g = re.findall(r"data/freight/lanes/([a-z-]+)\.json", sb.get("n", ""))
        if g:
            out.append((os.path.basename(p)[:-5], d, g[0]))
    return out


@need_build
class SeaborneFigure(unittest.TestCase):
    """E01: the seaborne tonnage of the latest year is one figure, whichever file shows it."""

    def test_lane_pairs_and_totals_agree(self):
        totals = load_json(TOTALS)
        for g in lane_groups():
            lf, pf = load_json(os.path.join(LANES, g + ".json")), load_json(os.path.join(PAIRS, g + ".json"))
            y = pf["y"]
            lane_mt = lf["seaborne"][lf["years"].index(y)]
            self.assertAlmostEqual(pf["seaborne"] / 1e3, lane_mt, delta=0.01, msg=g)
            self.assertAlmostEqual(totals[g][str(y)]["sea"] / 1e6, lane_mt, delta=0.01, msg=g)

    def test_commodity_page_shows_the_lane_figure(self):
        pages = commodity_pages()
        self.assertGreaterEqual(len(pages), 25)
        for cid, d, g in pages:
            sb = d["summary"]["seaborne"]
            lf = load_json(os.path.join(LANES, g + ".json"))
            v = lf["seaborne"][lf["years"].index(sb["y"])]
            self.assertAlmostEqual(sb["v"], v, delta=max(0.05, 0.0005 * v), msg=cid)
            self.assertEqual(sb["s"], "baci", cid)


@need_build
class FlowTables(unittest.TestCase):
    """E02: a flow row of a commodity page and the row of the same pair in the pairs table say the same thing."""

    def test_flows_match_the_pairs_table(self):
        checked = 0
        for cid, d, g in commodity_pages():
            pf = load_json(os.path.join(PAIRS, g + ".json"))
            ci = {c: i for i, c in enumerate(pf["cols"])}
            rows = {(r[ci["o"]], r[ci["d"]]): r for r in pf["rows"]}
            for f in d.get("flows", []):
                if f.get("lane") and not f["lane"].startswith(g + ":"):
                    continue
                if "milled equivalent" in (f.get("n") or ""):
                    continue  # rice flows converted to milled equivalent: another basis than the customs tonnage
                key = (cid, f["o"], f["d"])
                r = rows.get((f["o"], f["d"]))
                self.assertIsNotNone(r, key)
                checked += 1
                self.assertEqual(f.get("mode"), M_NAME[r[ci["m"]]], key)
                kt = r[ci["kt"]]
                self.assertAlmostEqual(f["v"], kt / 1e3, delta=max(0.006 * f["v"], 0.002), msg=key)
                self.assertEqual(bool(f.get("est")), bool(r[ci["f"]] & 1), key)
                self.assertEqual(bool(f.get("lane")), bool(r[ci["f"]] & 4), key)
                if f.get("lane"):
                    self.assertEqual(f["lane"], f"{g}:{f['o']}-{f['d']}", key)
                if "transit" in f:
                    self.assertEqual(r[ci["m"]], 1, key)
        self.assertGreater(checked, 400)

    def test_flow_caveats_exist(self):
        cv = load_json(os.path.join(DATA, "freight", "caveats.json"))
        for p in glob.glob(os.path.join(COMMOD, "*.json")):
            d = load_json(p)
            for f in (d.get("flows") or []) if isinstance(d, dict) else []:
                if f.get("caveat"):
                    self.assertIn(f["caveat"], cv, (os.path.basename(p), f["o"], f["d"]))

    def test_D10_no_provisional_key_in_commodity_files(self):
        for p in glob.glob(os.path.join(COMMOD, "*.json")):
            self.assertNotIn('"provisional"', read(p), p)


NODE = shutil.which("node")


@unittest.skipUnless(NODE and BUILT, "node is not on the PATH, or the data are not built")
class DataValidator(unittest.TestCase):
    """W01, data part: the validator that guards every scheduled update passes on the published files."""

    def test_W01_validate_data(self):
        r = subprocess.run([NODE, os.path.join(ROOT, "web", "scripts", "validate-data.mjs")], cwd=ROOT,
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-2000:])


class AnnualJob(unittest.TestCase):
    """E03: the freight step of pipeline/annual/update_annual.py. Nothing is run and no file is touched: the chain is
    recorded with stand-ins for step() and run()."""

    @classmethod
    def setUpClass(cls):
        import update_annual as UA
        cls.UA = UA
        chain, cmds = [], []
        saved = (UA.step, UA.run, UA.pending)
        UA.step = lambda name, fn, paths: chain.append((name, fn, paths))
        UA.run = lambda cmd, timeout: cmds.append([os.path.relpath(c, ROOT) if os.path.isabs(c) else c for c in cmd[1:]])
        UA.pending = lambda name: False
        try:
            UA.process({"baci"})
            for name, fn, _ in chain:
                if name == "build-freight":
                    fn()
        finally:
            UA.step, UA.run, UA.pending = saved
        cls.chain = {name: paths for name, _, paths in chain}
        cls.cmds = [c[0] for c in cmds]

    def test_borders_before_lanes_before_freight(self):
        self.assertEqual(self.cmds, ["pipeline/geo/adjacency.py", "pipeline/freight/build_lanes.py",
                                     "pipeline/freight/build_freight.py"])

    def test_snapshot_covers_every_output_of_the_freight_builders(self):
        snap = [os.path.relpath(p, ROOT) for p in self.chain["build-freight"]]
        outputs = ["pipeline/cache/adjacency.json", "data/countries/places.json"]  # pipeline/geo/adjacency.py
        for script, end in (("build_lanes.py", "Method"), ("build_freight.py", "Chokepoint shares")):
            # the "Outputs" paragraph of the builder's docstring
            doc = read(os.path.join(ROOT, "pipeline", "freight", script)).split('"""')[1].split("Outputs", 1)[1].split(end)[0]
            outputs += re.findall(r"((?:data|pipeline/cache)/[\w/<>.-]+\.(?:json|csv\.gz))", doc)
            if script == "build_freight.py":  # its files are listed by name under "Outputs (data/freight/)"
                outputs += ["data/freight/" + m for m in re.findall(r"\b([\w.-]+\.json)", doc.split("\n")[0])]
        outputs = sorted(set(outputs))
        self.assertIn("pipeline/cache/route_cache.json", outputs)
        self.assertIn("pipeline/cache/mixed_flows.csv.gz", outputs)
        for o in outputs:
            self.assertTrue(any(o == s or o.startswith(s.rstrip("/") + "/") for s in snap), o)

    def test_no_test_or_check_in_the_job(self):
        src = read(os.path.join(ROOT, "pipeline", "annual", "update_annual.py"))
        for word in ("unittest", "pipeline/tests", "test_", "checks.run", "assert "):
            self.assertNotIn(word, src, word)


WIKI = re.compile(r"https?://([a-z]{2,3})\.wikipedia\.org/wiki/[^\s\"'<>]+")


def _urls(obj, out):
    if isinstance(obj, str):
        out += [m.group(0) for m in WIKI.finditer(obj)]
    elif isinstance(obj, dict):
        for v in obj.values():
            _urls(v, out)
    elif hasattr(obj, "_asdict"):
        _urls(obj._asdict(), out)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for v in obj:
            _urls(v, out)
    return out


def _norm(u):
    lang = WIKI.match(u).group(1)
    slug = u.split("/wiki/", 1)[1].split("#")[0].rstrip(".,;:")
    if slug.endswith(")") and slug.count("(") < slug.count(")"):
        slug = slug[:-1]
    return f"https://{lang}.wikipedia.org/wiki/{quote(unquote(slug), safe='_(),' + chr(39) + '-.%')}"


def cited_articles():
    """Every Wikipedia article cited by a row of the gateway, transit, draught and mode tables (the same reading as the
    list of NOTICE.md)."""
    import importlib
    sys.path.insert(0, os.path.join(ROOT, "pipeline", "freight", "gateways"))
    found = []
    for name in ("food", "coasts", "energy"):
        m = importlib.import_module(name)
        for attr in ("G", "TRANSIT", "MANUAL_EXTRA", "MANUAL_SRC"):
            _urls(getattr(m, attr, None), found)
    import modes as MD
    import vessel_rules as VR
    _urls([VR.PASSAGE_LIMIT_SRC, VR.DRAUGHT_SRC], found)
    found.append(MD.LNG_LIST_URL)
    _urls([MD.SEA_NEIGHBOURS, MD.LAND_NOTES, MD.MIXED, MD.SEA_OUTLET, MD.BLOCS, MD.FLOW_OVERRIDES, MD.LNG_PIPELINE], found)
    return sorted({_norm(u) for u in found})


class Documentation(unittest.TestCase):
    """E04: the notices and the methodology follow the tables they describe."""

    def test_notice_lists_every_cited_wikipedia_article(self):
        notice = read(os.path.join(ROOT, "NOTICE.md"))
        arts = cited_articles()
        self.assertGreater(len(arts), 100)
        missing = [u for u in arts if u not in notice]
        self.assertEqual(missing, [], f"{len(missing)} articles missing from NOTICE.md")

    def test_notice_credits_openstreetmap_for_every_point_taken_from_it(self):
        notice = read(os.path.join(ROOT, "NOTICE.md"))
        self.assertIn("© OpenStreetMap contributors", notice)
        for p in glob.glob(os.path.join(DATA, "infrastructure", "*.geojson")):
            for f in load_json(p)["features"]:
                pr = f["properties"]
                if "OpenStreetMap" in json.dumps(pr):
                    self.assertIn(pr["name"].split(" (")[0].replace(" Terminal", ""), notice, pr["id"])

    def test_methodology_wording(self):
        text = read(os.path.join(ROOT, "METHODOLOGY.md"))
        self.assertNotIn("lower bound", text.lower())
        for term in ("at least", "up to", "Atlas estimate", "Atlas assumption", "sea via a transit port"):
            self.assertIn(term, text)
        self.assertIn("pipeline/infrastructure/README.md", text)


if __name__ == "__main__":
    unittest.main()
