"""Tests of the release identity: release.json and CHANGELOG.md.

R1  release.json has the number and the date of the published release, and CHANGELOG.md has an entry for it with the same date
R2  the entries run from the newest to release 1 with no gap, their dates never increase downwards, each has at least one bullet
R3  there is one entry per release section of PROGRESS.md, with the same date
R4  an entry is written for a visitor: it names no package, review, finding, agent, round or test count
R8  the "Report an error" form exists, sets no label, never names the label of the update jobs, and its fields are the ones the address fills

Both files are tracked, so the tests run on GitHub without the raw downloads.
Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_governance.py"
"""
import datetime
import json
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth", "eleventh", "twelfth"]
SUBHEADINGS = ("Added", "Changed", "Corrected", "Removed")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"])}
# the words of the work, not of the site: what a visitor reads never says how the work was done
PROCESS = re.compile(r"\b(packages?|reviews?|reviewers?|findings?|agents?|rounds?|sessions?|assistants?|claude)\b|\b\d[\d,]* (unit |web |node )?tests\b", re.I)


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


if __name__ == "__main__":
    unittest.main()
