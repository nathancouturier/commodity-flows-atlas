"""The registry entries of the three PortWatch sources and the status tables the port series joins.

The port series (registry id `portwatch-port-traffic`) is read by the same weekly job as the chokepoint series: its entry
carries the same permission text, the pace in its texts is the one of the code, and it is tracked by the staleness check and
by the "Data freshness" table of the About window without being reported as failing or stale before its first load has
recorded it.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_portwatch_sources.py"
"""
import json
import os
import re
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("", "common", "freight", "infrastructure"):
    p = os.path.join(ROOT, "pipeline", sub) if sub else os.path.join(ROOT, "pipeline")
    if p not in sys.path:
        sys.path.insert(0, p)

import changes as C  # noqa: E402
import fetch_portwatch as FP  # noqa: E402
import fetch_portwatch_ports as FPP  # noqa: E402
import staleness as S  # noqa: E402

NEW = "portwatch-port-traffic"
PORTWATCH = ("portwatch", "portwatch-ports", NEW)


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def flat(text):
    return " ".join(text.split())


REGISTRY = {s["id"]: s for s in json.loads(read("data", "sources.json"))}


def at(iso):
    return datetime.strptime(iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def stamp(iso):
    return iso + "T19:30:00Z"


def the_workflow_reads_the_port_series():
    """True when the workflow of the PortWatch job has a step that runs the script of the port series."""
    return "fetch_portwatch_port_traffic" in read(".github", "workflows", "update-portwatch.yml")


class Registry(unittest.TestCase):
    def test_the_port_series_has_an_entry_with_the_dataset_name_and_the_address_of_its_item(self):
        s = REGISTRY[NEW]
        self.assertEqual(s["publisher"], "IMF and University of Oxford")
        self.assertIn("Daily_Ports_Data", s["name"])
        # the item the licence field was read on: its address is the one the service answered to on 25 November 2026
        self.assertIn("83b1bbc7b3354c5fb1f40673bb8f852e", s["url"])
        self.assertIn("83b1bbc7b3354c5fb1f40673bb8f852e", s["access"])
        self.assertIn("Daily_Ports_Data/FeatureServer", s["access"])
        for field in ("name", "publisher", "url", "licence", "update", "access", "use"):
            self.assertTrue(str(s.get(field) or "").strip(), field)

    def test_the_texts_say_weekly_only_when_a_scheduled_step_reads_the_port_series_and_say_what_is_true_today_before(self):
        """The weekly wording comes back with the step that makes it true, and not before: the Sources window shows `update`."""
        s = REGISTRY[NEW]
        notice = flat(read("NOTICE.md"))
        i = notice.index("Port traffic. For the ports of the infrastructure layer")
        para = notice[i:notice.index("Ports database. The ports of the infrastructure layer", i)]
        if the_workflow_reads_the_port_series():
            self.assertEqual(s["update"], "weekly")
            self.assertIn("weekly run", s["access"])
            return
        self.assertNotEqual(s["update"], "weekly")
        self.assertTrue(s["update"].startswith("by hand for now"), s["update"])
        self.assertIn("no scheduled job reads this table yet", s["update"])
        self.assertIn("The first load is made by hand in sittings of a few ports; no scheduled job reads this table yet.", s["access"])
        self.assertIn("The files are being loaded and no page of the site shows them yet", s["use"])
        for field in ("update", "access", "use"):
            self.assertIsNone(re.search(r"weekly run|each week|every week|updated weekly|updates weekly", s[field], re.I), field)
        self.assertNotIn("each weekly run", para)
        self.assertIn("the weekly step that will follow reads only recent weeks", para)
        self.assertIn("that the weekly step will read back", para)
        self.assertIn("The CSV of a port series will be offered", para)
        self.assertIn("no page of the site shows the series yet", para)
        # the update guide says the same: no job, no page, the weekly step not in place, and no pointer to a section that is not there
        guide = flat(read("docs", "UPDATING.md"))
        j = guide.index("### Port traffic: the first load in sittings")
        section = guide[j:guide.index("## Releasing", j)]
        self.assertIn("no scheduled job runs the script", section)
        self.assertIn("The weekly step is not in place", section)
        self.assertNotIn("METHODOLOGY.md", section)

    def test_the_use_says_what_is_published_and_how_it_is_transformed(self):
        use = REGISTRY[NEW]["use"]
        for word in ("weekly sums", "Monday to Sunday", "complete weeks", "tanker", "dry bulk", "container", "general cargo and ro-ro",
                     "total columns", "rounded"):
            self.assertIn(word, use)
        self.assertNotIn("estimate of the atlas", use.lower())
        self.assertNotIn("Atlas estimate", use)

    def test_no_daily_row_is_kept(self):
        self.assertIn("No daily row is kept in the repository, in a cache or as a workflow artifact", REGISTRY[NEW]["access"])

    def test_the_three_licence_texts_start_with_the_same_words_and_none_calls_the_data_free(self):
        for sid in PORTWATCH:
            lic = REGISTRY[sid]["licence"]
            self.assertTrue(lic.startswith("IMF terms of use for statistical data"), sid)
            self.assertIn("commercial reuse needs IMF permission", lic, sid)
            self.assertIn("no creative commons licence stated", lic.lower(), sid)
            self.assertIn("IMF PortWatch (IMF and University of Oxford)", lic, sid)
            self.assertIsNone(re.search(r"public domain|open licen[cs]e|\bCC BY|\bCC0\b|free to reuse", lic, re.I), sid)

    def test_the_port_series_says_what_was_read_and_what_is_the_atlas_reading(self):
        lic = REGISTRY[NEW]["licence"]
        self.assertIn("https://www.imf.org/en/About/Copyright-and-Terms, read 25 November 2026", lic)
        self.assertIn('"published statistical data produced or curated by the IMF"', lic)
        self.assertIn("does not name PortWatch", lic)
        self.assertIn("the atlas's reading, not a sentence of the page", lic)
        self.assertIn('"prohibits bulk download of information by automated technology without explicit permission"', lic)
        self.assertIn("slowly, in small pieces, one request at a time", lic)
        # the item's own recommended citation, as read on the item
        self.assertIn("Sources: UN Global Platform; IMF PortWatch (portwatch.imf.org)", lic)

    def test_the_pace_in_the_texts_is_the_pace_of_the_code(self):
        lo, hi = FP.PAUSE_S
        pace = f"{lo:g} to {hi:g} seconds apart"
        self.assertIn(pace, REGISTRY["portwatch"]["access"])
        self.assertIn(pace, REGISTRY[NEW]["access"])
        self.assertIn(f"at least {FPP.MIN_INTERVAL_S:g} seconds apart", REGISTRY["portwatch-ports"]["access"])
        self.assertEqual(FPP.MIN_INTERVAL_S, lo)
        for sid in PORTWATCH:
            self.assertIn("the script's reading of the owner's rule of 25 November 2026", REGISTRY[sid]["access"], sid)
        notice = flat(read("NOTICE.md"))
        self.assertIn(f"one request at a time with a pause of {lo:g} to {hi:g} seconds before the next (the script's reading of the owner's rule of 25 November 2026, not his figure)",
                      notice)

    def test_the_notice_names_what_the_atlas_publishes_of_the_port_table_and_what_it_does_not_keep(self):
        notice = flat(read("NOTICE.md"))
        i = notice.index("Port traffic. For the ports of the infrastructure layer")
        para = notice[i:notice.index("Ports database. The ports of the infrastructure layer", i)]
        for text in ("`portwatch-port-traffic`", "weekly sums, Monday to Sunday and complete weeks only", "by ship type (tanker, dry bulk, container, and other",
                     "IMF PortWatch (IMF and University of Oxford), data adapted", "Sources: UN Global Platform; IMF PortWatch (portwatch.imf.org)",
                     "does not use the table's own total columns", "no daily row", "or as a workflow artifact",
                     "a choice made without the owner, listed in PROGRESS.md"):
            self.assertIn(text, para)
        self.assertIsNone(re.search(r"public domain|open licen[cs]e|free to reuse", para, re.I))
        # the ports database paragraph links only the assets whose cited page is their PortWatch page, with no figure to go stale
        db = notice[notice.index("Ports database. The ports of the infrastructure layer"):]
        self.assertNotIn("links each port asset to its PortWatch page", db)
        self.assertIn("a port asset whose cited page is its PortWatch page links to it, the others cite another page", db)
        # the paragraph on the terms and on the owner's decision is still there, untouched
        self.assertIn("The owner's decision of 25 November 2026: the atlas keeps reading PortWatch as a person would", notice)

    def test_data_sources_md_carries_the_row_of_the_registry_entry(self):
        import sources_table as T
        row = [line for line in T.render([REGISTRY[NEW]]).splitlines() if line.startswith("| `")][0]
        self.assertIn(row, read("DATA_SOURCES.md"))


class StatusTables(unittest.TestCase):
    def web_rows(self):
        text = read("web", "src", "lib", "status.ts")
        block = text[text.index("const TRACKED: Tracked[] = ["):]
        block = block[:block.index("];")]
        rows = re.findall(r"\{ key: '([^']+)', sources: \[([^\]]*)\], kind: '([\w-]+)', maxAge: ([\w +]+?)(?:,|\s*\})", block)
        return {k: ([x.strip(" '") for x in srcs.split(",")], kind) for k, srcs, kind, _ in rows}

    def test_the_port_series_is_tracked_like_the_chokepoint_series(self):
        self.assertEqual(S.TRACKED[NEW], S.TRACKED["portwatch"])
        self.assertEqual(S.TRACKED[NEW], ("day", S.WEEKLY))
        rows = self.web_rows()
        self.assertEqual(rows[NEW], ([NEW], "day"))
        self.assertEqual(rows["portwatch"], (["portwatch"], "day"))
        self.assertIn(f"{{ key: '{NEW}', sources: ['{NEW}'], kind: 'day', maxAge: WEEKLY }}", read("web", "src", "lib", "status.ts"))

    def test_the_staleness_check_and_the_freshness_table_track_the_same_sources(self):
        self.assertEqual(set(self.web_rows()), set(S.TRACKED))

    def test_every_tracked_source_is_in_the_registry(self):
        for key in S.TRACKED:
            for sid in C.SOURCES_OF.get(key, [key]):
                self.assertIn(sid, REGISTRY, key)

    def test_a_source_with_no_entry_in_the_status_file_is_neither_stale_nor_fresh(self):
        """Before the first load the status file has no entry for the port series: the check says nothing about it, as it says
        nothing about any tracked source the file does not yet hold."""
        doc = {"sources": {"portwatch": {"last_success": stamp("2026-11-22"), "data_to": "2026-11-15", "consecutive_failures": 0}}}
        r = S.check(doc, now=at("2026-11-25"))
        self.assertNotIn(NEW, r["stale"])
        self.assertNotIn(NEW, r["fresh"])
        self.assertEqual(r["fresh"], ["portwatch"])
        # the status file of the repository, as it stands
        real = json.loads(read("data", "_status", "updates.json"))
        out = S.check(real, now=at("2026-11-25"))
        if NEW not in real["sources"]:
            self.assertNotIn(NEW, out["stale"])
            self.assertNotIn(NEW, out["fresh"])

    def test_once_recorded_the_port_series_is_judged_like_the_chokepoint_series(self):
        good = {"last_success": stamp("2026-11-25"), "data_to": "2026-11-20", "consecutive_failures": 0}
        r = S.check({"sources": {NEW: good}}, now=at("2026-11-26"))
        self.assertEqual((r["stale"], r["fresh"]), ({}, [NEW]))
        old_data = dict(good, data_to="2026-10-20")
        r = S.check({"sources": {NEW: old_data}}, now=at("2026-11-26"))
        self.assertIn("more than 21 days old", r["stale"][NEW])
        old_check = dict(good, last_success=stamp("2026-11-01"))
        r = S.check({"sources": {NEW: old_check}}, now=at("2026-11-26"))
        self.assertIn("no successful check for 24 days", r["stale"][NEW])

    def test_the_freshness_table_skips_a_tracked_source_the_status_file_does_not_hold(self):
        text = read("web", "src", "lib", "status.ts")
        self.assertIn("if (!src[t.key] || typeof src[t.key] !== 'object') continue;", text)

    def test_the_calendar_jobs_are_the_sources_their_workflow_finishes(self):
        """changes.JOBS says which job reads each registry source: it must list exactly the sources of the `sources:` of the
        workflow's finish step (the status keys of the build steps left out), so that a source is never shown as read by a job
        that does not read it, nor as entered by hand when a job reads it."""
        for job, listed in C.JOBS.items():
            wf = read(".github", "workflows", job + ".yml")
            m = re.search(r'^\s*sources:\s*"([^"]+)"', wf, re.M)
            self.assertIsNotNone(m, job)
            read_by_job = {sid for key in m.group(1).split() if not key.startswith("build-") for sid in C.SOURCES_OF.get(key, [key])}
            self.assertEqual(read_by_job, set(listed), job)


if __name__ == "__main__":
    unittest.main()
