"""Tests of the release identity: release.json and CHANGELOG.md.

R1  release.json has the number and the date of the published release, and CHANGELOG.md has an entry for it with the same date
R2  the entries run from the newest to release 1 with no gap, their dates never increase downwards, each has at least one bullet
R3  there is one entry per release section of PROGRESS.md, with the same date
R4  an entry is written for a visitor: it names no package, review, finding, agent, round or test count
R8  the "Report an error" form exists, sets no label, never names the label of the update jobs, and its fields are the ones the address fills
C2  data/coverage.json is what the builder makes from the files (same bytes twice, no time of day, the data validator's own keys unused)
C3  every block of every page is recounted by a second reading of the files, and the one difference between the web's lane groups and the lane files is named
C4  no page has lost a block the floor file lists
C5  the typed reasons: structure, evidence found in the cited file, no reason on a block that is present
C9  build-coverage is wired into the annual update in every place; a typed table or a failed step stops no update, and no text says the guard's floor does not

Every file read is tracked, so the tests run on GitHub without the raw downloads.
Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_governance.py"
"""
import builtins
import datetime
import functools
import glob
import importlib.util
import inspect
import json
import os
import re
import unittest
import warnings

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth", "eleventh", "twelfth"]
SUBHEADINGS = ("Added", "Changed", "Corrected", "Removed")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"])}
# the words of the work, not of the site: what a visitor reads never says how the work was done
PROCESS = re.compile(r"\b(packages?|reviews?|reviewers?|findings?|agents?|rounds?|sessions?|assistants?|claude)\b|\b\d[\d,]* (unit |web |node )?tests\b", re.I)


def drift(test):
    """Marks a test of the committed coverage matrix against the data or the typed tables. A data update can move the
    data under the file, or leave the file as it was (its step failed and kept the previous one): in the checks of a
    scheduled update (ci.yml sets COVERAGE_CHECKS=warn when it is called with soft) such a finding is a warning and keeps
    no data from being published; in every other run it fails as any test does. The one rule that refuses an update is the
    data guard's: a page that lost a block of the floor (web/scripts/guard-data.mjs)."""
    @functools.wraps(test)
    def run(self):
        try:
            return test(self)
        except Exception as e:  # noqa: BLE001 - a builder that cannot read the data is a finding of the same kind
            if os.environ.get("COVERAGE_CHECKS") != "warn":
                raise
            warnings.warn(f"{test.__name__}: {type(e).__name__}: {e}"[:600])
    return run


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def release():
    return json.loads(read("release.json"))


def iso(s):
    """Parse YYYY-MM-DD strictly (date.fromisoformat also takes other forms in recent Pythons)."""
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", s), s
    return datetime.date.fromisoformat(s)


def entries():
    """[(number, date, heading, body)] of CHANGELOG.md, in the order of the file."""
    text = read("CHANGELOG.md")
    parts = re.split(r"(?m)^## ", text)
    out = []
    for p in parts[1:]:
        heading, _, body = p.partition("\n")
        m = re.fullmatch(r"Release (\d+) \((\d{4}-\d{2}-\d{2})\)", heading.strip())
        assert m, f"the heading of an entry is '## Release <n> (<YYYY-MM-DD>)': {heading!r}"
        out.append((int(m.group(1)), iso(m.group(2)), heading.strip(), body))
    return out


def progress_sections():
    """[(number, date)] of the release sections of PROGRESS.md: '## <Ordinal> release (<d> <Month> <yyyy>)...'."""
    out = []
    for m in re.finditer(r"(?m)^## (\w+) release \((\d{1,2}) (\w+) (\d{4})\)", read("PROGRESS.md")):
        word = m.group(1).lower()
        if word not in ORDINALS or m.group(3) not in MONTHS:
            continue
        out.append((ORDINALS.index(word) + 1, datetime.date(int(m.group(4)), MONTHS[m.group(3)], int(m.group(2)))))
    return out


class ReleaseFile(unittest.TestCase):
    def test_shape(self):
        r = release()
        self.assertEqual(sorted(r), ["date", "release"])
        self.assertIsInstance(r["release"], int)
        self.assertNotIsInstance(r["release"], bool)
        self.assertGreaterEqual(r["release"], 1)
        self.assertIsInstance(r["date"], str)
        iso(r["date"])

    def test_the_changelog_has_the_entry_of_that_release(self):
        r = release()
        first = entries()[0]
        self.assertEqual(first[0], r["release"], "the first entry of CHANGELOG.md is not the release of release.json")
        self.assertEqual(first[1], iso(r["date"]), "the first entry and release.json carry different dates")

    def test_the_site_reads_the_file(self):
        """vite.config.ts reads release.json and status.ts exports it for the About window."""
        self.assertIn("release.json", read("web", "vite.config.ts"))
        self.assertIn("__RELEASE_NUMBER__", read("web", "vite.config.ts"))
        self.assertIn("export const RELEASE", read("web", "src", "lib", "status.ts"))


class Changelog(unittest.TestCase):
    def test_the_entries_run_down_to_release_1(self):
        es = entries()
        self.assertTrue(es)
        self.assertEqual([e[0] for e in es], list(range(len(es), 0, -1)), "the numbers go down by one to 1, with no gap")
        for newer, older in zip(es, es[1:]):
            self.assertGreaterEqual(newer[1], older[1], f"{newer[2]} is dated before {older[2]}")
        self.assertLessEqual(es[0][1], iso(release()["date"]), "an entry is dated after release.json")

    def test_every_entry_has_a_bullet_and_only_the_known_subheadings(self):
        for n, _, heading, body in entries():
            self.assertTrue(re.search(r"(?m)^- \S", body), f"{heading} has no bullet")
            for sub in re.findall(r"(?m)^### (.*)$", body):
                self.assertIn(sub.strip(), SUBHEADINGS, f"{heading}: unknown sub-heading {sub!r}")

    def test_an_entry_has_no_word_of_the_work(self):
        for _, _, heading, body in entries():
            for m in PROCESS.finditer(body):
                self.fail(f"{heading} says how the work was done: {m.group(0)!r}")

    def test_one_entry_per_release_section_of_progress(self):
        secs = progress_sections()
        self.assertTrue(secs, "no release section found in PROGRESS.md")
        self.assertEqual(sorted(s[0] for s in secs), list(range(1, len(secs) + 1)), "the release sections of PROGRESS.md have a gap")
        es = {n: d for n, d, _, _ in entries()}
        self.assertEqual(sorted(es), sorted(s[0] for s in secs), "CHANGELOG.md and PROGRESS.md do not list the same releases")
        for n, d in secs:
            self.assertEqual(es[n], d, f"release {n}: PROGRESS.md says {d}, CHANGELOG.md says {es[n]}")


class ReportForm(unittest.TestCase):
    FORM = (".github", "ISSUE_TEMPLATE", "report-an-error.yml")

    def test_the_form_exists_and_sets_no_label(self):
        form = read(*self.FORM)
        self.assertRegex(form, r"(?m)^name: Report an error$")
        self.assertNotRegex(form, r"(?m)^\s*labels\s*:", "the repository has no label for reports and none is created: the form names none")
        self.assertNotIn("data-update", form, "data-update is the label of the update jobs' own issues")

    def test_the_labels_of_the_jobs_are_not_used_by_a_report(self):
        """The jobs find their issues by this label; a report must never carry it, in the form or in the address."""
        self.assertNotIn("data-update", read("web", "src", "lib", "report.ts"))
        for name in ("ReportLink.tsx", "DetailActions.tsx"):
            self.assertNotIn("data-update", read("web", "src", "components", name))

    def test_the_fields_of_the_address_are_ids_of_the_form(self):
        ids = re.findall(r"(?m)^\s*id:\s*(\S+)\s*$", read(*self.FORM))
        self.assertEqual(len(ids), len(set(ids)), "an id of the form is used twice")
        code = read("web", "src", "lib", "report.ts")
        fields = re.search(r"REPORT_FIELDS = \[([^\]]*)\]", code)
        self.assertTrue(fields, "report.ts does not export REPORT_FIELDS")
        names = re.findall(r"'([a-z]+)'", fields.group(1))
        self.assertTrue(names)
        for name in names:
            self.assertIn(name, ids, f"the address fills {name!r}, which the form does not have")
        self.assertIn("what", ids, "the form has no field for what is wrong")
        self.assertIn(f"REPORT_TEMPLATE = '{os.path.basename(self.FORM[-1])}'", code)

    def test_the_address_builder_stands_alone_and_sets_no_label(self):
        code = read("web", "src", "lib", "report.ts")
        self.assertNotRegex(code, r"(?m)^import\s", "report.ts has no import: the node tests run the file as it is")
        self.assertNotRegex(code, r"labels=|assignees=|projects=", "the address never sets what needs a permission")

    def test_the_repository_address_is_written_once(self):
        """web/src/lib/links.ts holds it; the About window and the report link read it from there."""
        hits = []
        for folder, _, files in os.walk(os.path.join(ROOT, "web", "src")):
            for f in files:
                if f.endswith((".ts", ".tsx")) and "github.com/nathancouturier" in read(os.path.relpath(os.path.join(folder, f), ROOT)):
                    hits.append(f)
        self.assertEqual(hits, ["links.ts"])


_BUILDER = None
_BUILT = None


def builder():
    """pipeline/commodities/build_coverage.py, loaded by its path."""
    global _BUILDER
    if _BUILDER is None:
        spec = importlib.util.spec_from_file_location("build_coverage", os.path.join(ROOT, "pipeline", "commodities", "build_coverage.py"))
        _BUILDER = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_BUILDER)
    return _BUILDER


def built():
    """(document, warnings) of one build of the files as they are."""
    global _BUILT
    if _BUILT is None:
        w = []
        _BUILT = (builder().build(ROOT, w), w)
    return _BUILT


def jread(*parts):
    return json.loads(read(*parts))


def committed():
    return jread("data", "coverage.json")


def reasons_table():
    return jread("pipeline", "commodities", "coverage_reasons.json")


def index():
    return jread("data", "commodities", "index.json")


class CoverageFile(unittest.TestCase):
    @drift
    def test_the_file_is_what_the_builder_makes(self):
        doc, _ = built()
        self.assertEqual(read("data", "coverage.json"), builder().render(doc), "data/coverage.json is stale: run pipeline/commodities/build_coverage.py")

    def test_two_builds_give_the_same_bytes(self):
        b = builder()
        self.assertEqual(b.render(b.build(ROOT, [])), b.render(b.build(ROOT, [])))

    def test_it_carries_the_release_and_no_time_of_day(self):
        doc = committed()
        self.assertEqual(sorted(doc), ["blocks", "pages", "reasons", "release", "version", "work"])
        self.assertEqual(doc["release"], release()["release"], "run build_coverage.py after a release.json bump: the file says which release it is as of")
        self.assertNotRegex(read("data", "coverage.json"), r"\d{2}:\d{2}", "a time of day makes two runs differ")

    def test_it_reads_only_tracked_files(self):
        """Never raw/ or the caches: the scheduled job and the checks run on GitHub, where they do not exist."""
        seen = []
        real_open = builtins.open

        def spy(path, *a, **k):
            if isinstance(path, (str, bytes, os.PathLike)):
                seen.append(os.path.abspath(os.fsdecode(path)))
            return real_open(path, *a, **k)

        builtins.open = spy
        try:
            builder().build(ROOT, [])
        finally:
            builtins.open = real_open
        self.assertTrue(seen)
        allowed = [os.path.join(ROOT, "data") + os.sep, os.path.join(ROOT, "pipeline", "commodities") + os.sep, os.path.join(ROOT, "release.json")]
        for path in seen:
            self.assertTrue(any(path.startswith(a) for a in allowed), f"the builder reads {path}")

    def test_no_key_of_the_data_validator_is_used_for_something_else(self):
        """validate-data.mjs reads every `s` as a source id and checks `y`, `v`, `c` and the shares of every file."""
        reserved = {"s", "y", "v", "c", "lat", "lon", "share", "estShare", "shareDest"}
        found = []

        def walk(o, trail):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in reserved:
                        found.append(f"{trail}.{k}")
                    walk(v, f"{trail}.{k}")
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{trail}[{i}]")

        walk(committed(), "$")
        self.assertEqual(found, [])

    @drift
    def test_one_row_per_page_and_one_cell_per_block_the_page_can_have(self):
        doc = committed()
        pages = index()
        self.assertEqual([p["id"] for p in doc["pages"]], [p["id"] for p in pages], "a row for each page of commodities/index.json, in its order")
        blocks = {b["id"]: b for b in doc["blocks"]}
        self.assertEqual(list(blocks), builder().BLOCK_IDS)
        for page, row in zip(pages, doc["pages"]):
            expected = [b for b, blk in blocks.items() if "families" not in blk or page["family"] in blk["families"]]
            self.assertEqual(list(row["cells"]), expected, f"{page['id']}: the cells are the blocks of its family")
            for b, c in row["cells"].items():
                m = re.fullmatch(r"p|m|(na|nf):([a-z0-9-]+)", c)
                self.assertTrue(m, f"{page['id']}/{b}: {c!r} is not a cell")
                if m.group(2):
                    r = doc["reasons"].get(m.group(2))
                    self.assertTrue(r, f"{page['id']}/{b}: no reason {m.group(2)!r}")
                    self.assertEqual({"na": "na", "nf": "nofree"}[m.group(1)], r["st"], f"{page['id']}/{b}: the cell and its reason disagree")

    def test_the_monthly_and_balance_blocks_are_cells_of_their_family_only(self):
        doc = committed()
        fam = {p["id"]: p["family"] for p in index()}
        for row in doc["pages"]:
            self.assertEqual("monthly" in row["cells"], fam[row["id"]] == "energy", row["id"])
            self.assertEqual("balance" in row["cells"], fam[row["id"]] == "softs", row["id"])

    def test_the_reasons_are_written_whole_in_the_order_of_the_table(self):
        """A list that lost entries when the data improved would trip the update guard (a tenth of a list)."""
        doc = committed()
        entries = reasons_table()["entries"]
        self.assertEqual(list(doc["reasons"]), [e["id"] for e in entries])
        for e in entries:
            self.assertEqual(doc["reasons"][e["id"]], {"st": e["status"], "t": e["reason"]})

    def test_the_block_of_routes_says_what_it_counts(self):
        routes = {b["id"]: b for b in committed()["blocks"]}["routes"]
        self.assertEqual(routes["label"], "Routes")
        for word in ("generated", "customs pairs", "benchmark", "by hand"):
            self.assertIn(word, routes["text"])

    @drift
    def test_the_work_list_is_the_missing_cells_largest_seaborne_tonnage_first(self):
        doc = committed()
        missing = {r["id"]: [b for b, c in r["cells"].items() if c == "m"] for r in doc["pages"]}
        self.assertEqual(dict(doc["work"]), {p: m for p, m in missing.items() if m})
        tonnes = []
        for pid in doc["work"]:
            d = jread("data", "commodities", f"{pid}.json")
            s = (d.get("summary") or {}).get("seaborne")
            if s:
                t = s["v"] * {"Mt": 1, "kt": 0.001}[s["u"]]
            else:
                t = 0.0
                for p in glob.glob(os.path.join(ROOT, "data", "freight", "lanes", "*.json")):
                    f = jread(os.path.relpath(p, ROOT))
                    if f["k"] == pid and f.get("seaborne"):
                        t += f["seaborne"][-1] * {"Mt": 1, "kt": 0.001}[f["unit"]]
            tonnes.append(t)
        self.assertEqual(tonnes, sorted(tonnes, reverse=True), "the work list is ordered by seaborne tonnes, largest first")


# what the web names for a page and what the lane files say of it: the one place where they differ
KNOWN_LANE_GROUP_DIFFERENCE = {"met-coal": ({"coal"}, set())}


def lane_groups_of_the_web():
    """LANE_GROUPS of web/src/lib/freight.ts, read as text."""
    ts = read("web", "src", "lib", "freight.ts")
    start = ts.index("export const LANE_GROUPS")
    out = {}
    for m in re.finditer(r"(?m)^\s*(?:'([\w-]+)'|([\w-]+)):\s*\[([^\]]*)\],?\s*$", ts[start:ts.index("\n};", start)]):
        out[m.group(1) or m.group(2)] = re.findall(r"'([^']+)'", m.group(3))
    return out


def lane_group_differences(web, files):
    """{page: (groups only the web names, groups only the lane files give it)} for the pages where they differ."""
    out = {}
    for page in set(web) | set(files):
        a, b = set(web.get(page, [])), set(files.get(page, []))
        if a != b:
            out[page] = (a - b, b - a)
    return out


class CoverageRecount(unittest.TestCase):
    """A second reading of the files, written apart from the builder: every block of every page."""

    @classmethod
    def setUpClass(cls):
        data = os.path.join(ROOT, "data")
        cls.pages = index()
        cls.lane_files = {}
        for p in glob.glob(os.path.join(data, "freight", "lanes", "*.json")):
            with open(p, encoding="utf-8") as f:
                cls.lane_files[os.path.basename(p)[:-5]] = json.load(f)
        cls.web_groups = lane_groups_of_the_web()
        cls.routes = jread("data", "freight", "routes.json")
        cls.prices = jread("data", "prices", "index.json")
        cls.assets = {}
        for p in glob.glob(os.path.join(data, "infrastructure", "*.geojson")):
            with open(p, encoding="utf-8") as f:
                for feat in json.load(f)["features"]:
                    for k in feat["properties"].get("k") or []:
                        cls.assets[k] = cls.assets.get(k, 0) + 1
        cls.companies = jread("data", "commodities", "companies.json")
        cls.monthly = {}
        for p in glob.glob(os.path.join(data, "commodities", "monthly", "*.json")):
            with open(p, encoding="utf-8") as f:
                cls.monthly[os.path.basename(p)[:-5]] = json.load(f)

    @staticmethod
    def table_rows(d):
        t = {k: d.get(k) for k in ("production", "refinery", "reserves", "consumption", "exports", "imports")}
        t.update({x["key"]: x["table"] for x in d.get("extra") or []})
        return {k: len(v["rows"]) for k, v in t.items() if isinstance(v, dict) and v.get("rows")}

    def recount(self, page):
        d = jread("data", "commodities", f"{page}.json")
        n = self.table_rows(d)
        lanes = sum(len(self.lane_files[g]["lanes"]) for g in self.web_groups.get(page, []) if g in self.lane_files)
        series = self.monthly.get(page, {})
        return {
            "production": any(k in ("production", "refinery") or (k.endswith("-production") and not k.startswith("eu-")) for k in n),
            "reserves": any(k == "reserves" or k.endswith("-reserves") for k in n),
            "consumption": any(k == "consumption" or k.endswith("-consumption") for k in n),
            "trade": "exports" in n and "imports" in n,
            "lanes": lanes > 0,
            "routes": any(page in r["cargoes"] for r in self.routes),
            "price": any(m["k"] == page and not m.get("hidden") for m in self.prices),
            "assets": self.assets.get(page, 0) > 0,
            "companies": sum(len(v) for v in self.companies.get(page, {}).values()) > 0,
            "monthly": any(v for k, v in series.items() if k not in ("id", "s", "gaps")),
            "balance": bool((d.get("balance") or {}).get("rows")),
        }

    @drift
    def test_every_block_of_every_page_agrees_with_the_recount(self):
        doc = committed()
        cells = {r["id"]: r["cells"] for r in doc["pages"]}
        wrong = []
        for page in self.pages:
            seen = self.recount(page["id"])
            for block, cell in cells[page["id"]].items():
                if (cell == "p") != seen[block]:
                    wrong.append(f"{page['id']}/{block}: the file says {cell!r}, the files say {'present' if seen[block] else 'absent'}")
        self.assertEqual(wrong, [])

    @drift
    def test_the_web_and_the_lane_files_differ_in_one_place_only(self):
        """Metallurgical coal: the web lists the group 'coal' (whose lanes are the thermal coal page's: k is
        thermal-coal) beside 'coke'; the lane files give the page only 'coke'. The presence of lanes agrees. A second
        difference would mean the builder (it reads the lane files' k) and the site have drifted."""
        files = {}
        for group, f in self.lane_files.items():
            files.setdefault(f["k"], []).append(group)
        self.assertEqual(lane_group_differences(self.web_groups, files), KNOWN_LANE_GROUP_DIFFERENCE)
        listed = {g for gs in self.web_groups.values() for g in gs}
        self.assertEqual(set(self.lane_files) - listed, set(), "a lane file that no page of the web lists")
        self.assertEqual(listed - set(self.lane_files), set(), "a lane group of the web with no file")

    def test_a_second_difference_is_caught(self):
        files = {}
        for group, f in self.lane_files.items():
            files.setdefault(f["k"], []).append(group)
        web = {k: list(v) for k, v in self.web_groups.items()}
        web["wheat"] = web["wheat"] + ["corn"]
        self.assertNotEqual(lane_group_differences(web, files), KNOWN_LANE_GROUP_DIFFERENCE)
        web = {k: list(v) for k, v in self.web_groups.items()}
        del web["met-coal"]
        self.assertNotEqual(lane_group_differences(web, files), KNOWN_LANE_GROUP_DIFFERENCE)

    @drift
    def test_a_file_of_monthly_gaps_is_not_a_series(self):
        """LNG's monthly file holds a sentence about what is missing: a plain 'file exists' test would call it present."""
        for page, doc in self.monthly.items():
            has = any(v for k, v in doc.items() if k not in ("id", "s", "gaps"))
            cell = {r["id"]: r["cells"] for r in committed()["pages"]}[page]["monthly"]
            self.assertEqual(cell == "p", has, page)


class CoverageFloor(unittest.TestCase):
    def floor(self):
        return jread("pipeline", "commodities", "coverage_floor.json")

    def test_the_floor_names_pages_and_blocks_that_exist(self):
        f = self.floor()
        self.assertEqual(sorted(f), ["present", "version"])
        cells = {r["id"]: r["cells"] for r in committed()["pages"]}
        for page, blocks in f["present"].items():
            self.assertIn(page, cells, f"the floor names {page}, which is not a page")
            self.assertEqual(blocks, [b for b in builder().BLOCK_IDS if b in blocks], f"{page}: blocks listed twice or out of order")
            for b in blocks:
                self.assertIn(b, cells[page], f"{page}: the floor lists {b}, which is not a block of that page")

    @drift
    def test_no_page_has_lost_a_block(self):
        lost = builder().below_floor(committed(), self.floor()["present"])
        self.assertEqual(lost, [], "; ".join(f"page {p} lost block {b}" for p, b in lost)
                         + ". If the loss is real and accepted, lower pipeline/commodities/coverage_floor.json by hand, in a commit that says why.")

    def test_the_check_sees_a_loss(self):
        doc = committed()
        lost = json.loads(json.dumps(doc))
        for row in lost["pages"]:
            if row["id"] == "copper":
                row["cells"]["price"] = "m"
        floor = {"copper": ["price"]}
        self.assertEqual(builder().below_floor(doc, floor), [])
        self.assertEqual(builder().below_floor(lost, floor), [("copper", "price")])

    def test_raising_only_adds(self):
        """A block that the floor lists and the data no longer show stays in the floor (and the check says so)."""
        doc = committed()
        lost = json.loads(json.dumps(doc))
        for row in lost["pages"]:
            if row["id"] == "copper":
                row["cells"]["price"] = "m"
        before = self.floor()["present"]
        after = builder().raised(before, lost)
        self.assertEqual(after["copper"], before["copper"])
        self.assertEqual(builder().raised({}, doc)["wheat"], [b for b in builder().BLOCK_IDS if committed_cells("wheat").get(b) == "p"])


def committed_cells(page):
    return {r["id"]: r["cells"] for r in committed()["pages"]}[page]


class CoverageReasons(unittest.TestCase):
    def check(self, table):
        return builder().check_table(table, index())

    def fresh(self):
        return json.loads(json.dumps(reasons_table()))

    def entry(self, **over):
        e = {"id": "scratch", "blocks": ["reserves"], "pages": ["wheat"], "status": "na",
             "reason": "A reason of more than twenty characters.", "evidence": [{"file": "PROGRESS.md", "text": "x"}]}
        e.update(over)
        return e

    def test_the_table_passes_its_own_rules(self):
        cells = self.check(reasons_table())
        self.assertTrue(cells)

    def test_the_text_cited_for_a_reason_is_in_the_file_cited(self):
        for e in reasons_table()["entries"]:
            if e["status"] != "na":
                continue
            for ev in e["evidence"]:
                path = os.path.join(ROOT, ev["file"])
                self.assertTrue(os.path.exists(path), f"{e['id']}: no file {ev['file']}")
                self.assertIn(ev["text"], read(ev["file"]), f"{e['id']}: {ev['file']} does not say {ev['text']!r}")

    @drift
    def test_no_reason_sits_on_a_block_that_is_present(self):
        """In a scheduled run the data win: the builder writes the cell as present and warns. A hand edit that leaves
        a stale reason fails here; the checks of a data update only warn (COVERAGE_CHECKS=warn), so that a table
        that improved never blocks the publication of unrelated data."""
        stale = [w for w in built()[1] if w.startswith("stale reason")]
        self.assertEqual(stale, [], "the block exists: remove the reason from pipeline/commodities/coverage_reasons.json")

    def test_the_data_win_when_a_typed_block_becomes_present(self):
        table = self.fresh()
        table["entries"].append(self.entry(id="stale", blocks=["production"], pages=["wheat"]))
        w = []
        doc = builder().build(ROOT, w, table)
        cell = {r["id"]: r["cells"] for r in doc["pages"]}["wheat"]["production"]
        self.assertEqual(cell, "p")
        self.assertTrue(any("wheat/production" in x and "stale" in x for x in w), w)

    def test_a_reason_is_never_typed_for_a_missing_block(self):
        self.assertRaises(builder().CoverageError, self.check, {"version": 1, "entries": [self.entry(status="missing")]})

    def test_structure_errors_are_hard(self):
        bad = {
            "a repeated id": [self.entry(), self.entry(pages=["corn"])],
            "two reasons for one cell": [self.entry(), self.entry(id="other")],
            "no such page": [self.entry(pages=["unobtainium"])],
            "no such block": [self.entry(blocks=["weather"])],
            "a block the page cannot have": [self.entry(blocks=["monthly"], pages=["gold"])],
            "a reason too short": [self.entry(reason="too short")],
            "no evidence for a not-applicable reason": [self.entry(evidence=[])],
            "the atlas's own gap as a reason": [self.entry(reason="No free file loaded by the atlas gives the reserves of wheat.")],
            "an unknown key": [self.entry(owner="x")],
        }
        for what, entries in bad.items():
            with self.assertRaises(builder().CoverageError, msg=what):
                self.check({"version": 1, "entries": entries})

    def nofree(self, **over):
        ev = {"page": "https://publisher.example/terms", "month": "2026-11",
              "alternatives": [{"what": "the national statistics office", "why": "publishes totals only"}]}
        ev.update(over)
        return self.entry(status="nofree", reason="The publisher sells this series and no other free source gives it.", evidence=ev)

    def test_not_available_for_free_needs_the_page_read_and_the_alternatives(self):
        self.assertTrue(self.check({"version": 1, "entries": [self.nofree()]}))
        bad = {
            "registry ids only": self.entry(status="nofree", reason="The publisher sells this series and no other free source.", evidence={"sources": ["icco"]}),
            "no month": self.nofree(month="November"),
            "an impossible month": self.nofree(month="2026-13"),
            "no alternatives": self.nofree(alternatives=[]),
            "an alternative without its reason": self.nofree(alternatives=[{"what": "the statistics office"}]),
            "no address": self.nofree(page="publisher terms"),
        }
        for what, e in bad.items():
            with self.assertRaises(builder().CoverageError, msg=what):
                self.check({"version": 1, "entries": [e]})


class UpdateJobs(unittest.TestCase):
    """The step is in every place the annual update needs; a typed table or a failed step stops no update, and the one rule
    that refuses one is the guard's floor."""

    def test_build_coverage_is_wired_into_the_annual_update_in_every_place(self):
        status = read("pipeline", "common", "status.py")
        workflow = read(".github", "workflows", "update-annual.yml")
        annual = read("pipeline", "annual", "update_annual.py")
        steps = re.search(r"BUILD_STEPS = \(([^)]*)\)", status).group(1)
        places = {
            "BUILD_STEPS of pipeline/common/status.py": '"build-coverage"' in steps,
            "sources of update-annual.yml": bool(re.search(r'sources: "[^"]*\bbuild-coverage\b', workflow)),
            "steps of update-annual.yml": "?build-coverage" in workflow,
            "paths of update-annual.yml": bool(re.search(r'paths: "[^"]*\bdata/coverage\.json\b', workflow)),
            "the chain of update_annual.py": 'chain.append(("build-coverage"' in annual,
            "STEP_MIN of update_annual.py": '"coverage":' in annual,
        }
        missing = [k for k, v in places.items() if not v]
        self.assertEqual(missing, [], f"build-coverage is not in {missing}")
        self.assertTrue(os.path.exists(os.path.join(ROOT, "pipeline", "commodities", "build_coverage.py")))

    def test_the_step_comes_after_the_pages_and_before_the_profiles(self):
        annual = read("pipeline", "annual", "update_annual.py")
        order = [annual.index(f'chain.append(("{n}"') for n in ("build-commodities", "build-coverage", "build-profiles")]
        self.assertEqual(order, sorted(order))

    def test_the_bootstrap_builds_the_matrix_after_the_pages_and_before_the_profiles(self):
        boot = read("pipeline", "bootstrap.sh")
        order = [boot.index(f"commodities/{n}.py") for n in ("build_commodities", "build_coverage", "build_profiles")]
        self.assertEqual(order, sorted(order))

    def test_the_checks_of_a_scheduled_update_only_warn_on_the_matrix(self):
        """ci.yml is called with soft by the update workflows: the Python suite then runs with COVERAGE_CHECKS=warn."""
        ci = read(".github", "workflows", "ci.yml")
        self.assertRegex(ci, r"COVERAGE_CHECKS: \$\{\{ inputs\.soft == true && 'warn' \|\| 'fail' \}\}")
        step = ci[ci.index("name: Python unit suite"):ci.index("name: Production build")]
        self.assertIn("COVERAGE_CHECKS", step)

    def test_the_floor_is_the_guards_and_not_the_validators(self):
        """The validator has no override and a failure of it discards every path of a job; the guard has one."""
        self.assertIn("coverage_floor.json", read("web", "scripts", "guard-data.mjs"))
        self.assertNotIn("coverage_floor", read("web", "scripts", "validate-data.mjs"))
        self.assertNotIn("coverage_floor", read("web", "scripts", "validate-coverage.mjs"))

    def test_no_text_says_that_the_coverage_tables_never_stop_an_update(self):
        """The guard refuses an update in which a page loses a block of the floor, and every path of the job is then
        discarded: the texts that speak of it must not say that nothing can stop an update. Each of the four texts
        below held a sentence of this pattern before it was corrected; the METHODOLOGY paragraph never did, so it is
        held to what it must say instead."""
        wrong = re.compile(r"neither table can stop|never keeps? data from being published|no hand-typed table can stop"
                           r"|tables,? which never stops? the update", re.I)
        coverage = re.search(r"- \*\*Coverage\.\*\*.*?(?:\n\n|\Z)", read("METHODOLOGY.md"), re.S)
        self.assertTrue(coverage, "the coverage paragraph of section 13 is not found")
        texts = {
            "docs/UPDATING.md": read("docs", "UPDATING.md"),
            ".github/workflows/ci.yml": read(".github", "workflows", "ci.yml"),
            "drift() of test_governance.py": inspect.getdoc(drift),
            "pipeline/annual/update_annual.py": read("pipeline", "annual", "update_annual.py"),
        }
        for name, text in texts.items():
            self.assertIsNone(wrong.search(text), f"{name} says that nothing can stop an update")
        self.assertIn("guard", texts["drift() of test_governance.py"])
        self.assertIn("the floor can refuse one, through the guard", texts["pipeline/annual/update_annual.py"])
        self.assertIsNone(wrong.search(coverage.group(0)))
        self.assertIn("refused by the update guard", " ".join(coverage.group(0).split()))
        # the pattern does catch the sentences it was written for
        for old in ("Neither table can stop an update", "a file of metadata never keeps data from being published",
                    "rests on two hand-typed tables, which never stop the update"):
            self.assertTrue(wrong.search(old), old)
        self.assertIsNone(wrong.search("two hand-typed tables: a typed reason never stops the update, and the floor can refuse one"))


if __name__ == "__main__":
    unittest.main()
