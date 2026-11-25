"""The words about the Freight market now page (METHODOLOGY.md, NOTICE.md, the README and the registry) against the builder, the page and the
sentences they quote. Every quotation of those texts about the publishers is word for word in a fixture (the two committed ones, with their
address and the day they were read); every figure the texts give (five passages, four weeks, 52 weeks, 28 days, the rounding, the alert
threshold, the cargo limit of the page) is the constant of the code that applies it; and the texts claim for no publisher what no page read says.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_market_now_texts.py"
"""
import html
import json
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for sub in ("", "common", "freight"):
    p = os.path.join(ROOT, "pipeline", sub) if sub else os.path.join(ROOT, "pipeline")
    if p not in sys.path:
        sys.path.insert(0, p)

import build_market_now as BM  # noqa: E402
from common import status  # noqa: E402

FIXTURES = os.path.join(ROOT, "pipeline", "tests", "fixtures")
OWN = os.path.join(FIXTURES, "market_now_texts_quotations.json")
LINKS = os.path.join(FIXTURES, "link_only_sources_quotations.json")
WORK = "/tmp/claude-0/audit/work/6B"
# the pages as they were saved when the quotations were read (outside the repository: compared with the fixtures where they exist)
SAVED = {
    "portwatch-ship-categories": ("item", f"{WORK}/PORTS/samples/item_3da2b9ca97684916b75c4013f95d18ab.json"),
    "portwatch-chokepoint-trade-estimate": ("item", f"{WORK}/PORTS/samples/item_3da2b9ca97684916b75c4013f95d18ab.json"),
    "dallasfed-proxy": ("html", f"{WORK}/FNOW/critic/dl/dallasfed-igrea.html"),
    "baltic-terms-clause-5-1": ("html", f"{WORK}/VOYAGE/dl/baltic-terms.html"),
    "sse-footer": ("html", f"{WORK}/FNOW/dl/sse-home.html"),
    "ams-privacy-public-information": ("html", f"{WORK}/FNOW/critic/dl/ams-privacy.html"),
    "ams-datasets-non-copyrighted": ("html", f"{WORK}/FNOW/dl/ams-gtr-datasets.html"),
    "ams-datasets-vessel-rates-source": ("html", f"{WORK}/FNOW/dl/ams-gtr-datasets.html"),
    "agtransport-vessel-loading-attribution": ("field", f"{WORK}/FNOW/dl/views-vh5k-mnyv.json", "attribution"),
    "agtransport-vessel-rates-attribution": ("field", f"{WORK}/FNOW/dl/views-ehs5-yac3.json", "attribution"),
}
NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def flat(text):
    return " ".join(text.split())


def straight(text):
    return text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("\xa0", " ")


def fixture(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def saved_text(spec):
    """The text of a saved page (tags removed, quotes straightened, spacing normalised), or None where the page is not on this machine."""
    if not os.path.exists(spec[1]):
        return None
    with open(spec[1], encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    if spec[0] == "field":
        return flat(json.loads(raw)[spec[2]])
    if spec[0] == "item":
        raw = json.loads(raw)["description"]
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    return flat(straight(html.unescape(re.sub(r"<[^>]+>", " ", raw))))


# ---- the passages of the texts that are about the page

METHOD = read("METHODOLOGY.md")
NOTICE = read("NOTICE.md")


def between(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def passages():
    """name -> the passage, on one line."""
    m = between(METHOD, "- **Freight market now** (the page", "- **Events** carry")
    links = m[m.index("  - **Links, no value.**"):]
    n_digest = between(NOTICE, "Freight market now. The page of that name", "\n\n")
    n_links = between(NOTICE, "### Shanghai Shipping Exchange and USDA", "### Canal authorities")
    n_baltic = between(NOTICE, 'The "Freight market now" page links to the Baltic Exchange', "\n")
    n_dallas = between(NOTICE, "- **Federal Reserve Bank of Dallas**", "- **Federal Reserve Bank of New York**")
    rows = [ln for ln in NOTICE.splitlines() if ln.startswith(("| Shanghai Shipping Exchange indices |", "| USDA Agricultural Marketing Service ("))]
    return {
        "method": flat(m),
        "method-links": flat(links),
        "notice-digest": flat(n_digest),
        "notice-links": flat(n_links),
        "notice-baltic": flat(n_baltic),
        "notice-dallas": flat(n_dallas),
        "notice-rows": flat(" ".join(rows)),
    }


P = passages()
OWN_FX = fixture(OWN)
LINK_FX = fixture(LINKS)
QUOTES = {q["key"]: q for q in OWN_FX["quotations"] + LINK_FX["quotations"]}
REGISTRY = {s["id"]: s for s in json.loads(read("data", "sources.json"))}
WEB = {n: read("web", "src", *p) for n, p in {
    "view": ("components", "views", "FreightNowView.tsx"),
    "lib": ("lib", "marketNow.ts"),
    "ind": ("lib", "freightIndicators.ts"),
    "side": ("components", "SidePanel.tsx"),
}.items()}
LINK_ONLY_PASSAGES = ("method-links", "notice-links", "notice-baltic", "notice-rows")


def quoted(text):
    return re.findall(r'"([^"]+)"', text)


def outside_text():
    """METHODOLOGY.md and NOTICE.md without the passages above: what the other sections of the same files already say."""
    t = METHOD + NOTICE
    for name, p in passages_raw().items():
        t = t.replace(p, "")
    return flat(t)


def passages_raw():
    m = between(METHOD, "- **Freight market now** (the page", "- **Events** carry")
    return {"m": m, "nd": between(NOTICE, "Freight market now. The page of that name", "\n\n"),
            "nl": between(NOTICE, "### Shanghai Shipping Exchange and USDA", "### Canal authorities")}


class Quotations(unittest.TestCase):
    def test_the_fixture_says_what_it_is_and_every_quotation_has_its_address_and_normalised_spacing(self):
        self.assertTrue(OWN_FX["about"].startswith("Quotations of a few sentences, with their address and the day they were read"))
        self.assertEqual(OWN_FX["read"], "2026-11-25")
        keys = [q["key"] for q in OWN_FX["quotations"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertFalse(set(keys) & {q["key"] for q in LINK_FX["quotations"]})
        for q in OWN_FX["quotations"]:
            self.assertRegex(q["address"], r"^https://", q["key"])
            self.assertIn(q["registry"], REGISTRY, q["key"])
            self.assertEqual(q["quotation"], flat(q["quotation"]), f"{q['key']}: spacing is normalised")
            self.assertEqual(q["quotation"], straight(q["quotation"]), f"{q['key']}: typographic quotes are written straight")

    def test_every_fixture_quotation_is_word_for_word_in_the_page_it_was_read_on_where_the_saved_page_is_here(self):
        found = 0
        for key, spec in SAVED.items():
            text = saved_text(spec)
            if text is None:
                continue
            found += 1
            self.assertIn(QUOTES[key]["quotation"], text, f"{key}: not in {spec[1]}")
        self.assertEqual(set(SAVED), set(QUOTES), "every quotation of the two fixtures has a saved page to be compared with")
        if not found:
            self.skipTest("the saved pages are not on this machine")

    def test_the_saved_item_names_five_classes_defines_none_and_does_not_mention_gas_carriers(self):
        text = saved_text(SAVED["portwatch-ship-categories"])
        if text is None:
            self.skipTest("the saved item is not on this machine")
        self.assertNotRegex(text, r"(?i)\b(gas|lng|lpg)\b")
        self.assertNotRegex(text, r"(?i)\btankers? (are|is|means|include)")
        self.assertIn("Ship Categories: all the indicators are available by 5 main ship categories", text)

    def test_every_quoted_string_of_the_passages_is_a_fixture_quotation_or_a_label_the_code_or_the_registry_holds(self):
        fixtures = [q["quotation"] for q in QUOTES.values()] + [OWN_FX["item_name"]]
        outside = outside_text()
        tiny = re.search(r"TINY_MT = ([0-9.]+)", WEB["lib"]).group(1)
        for name, text in P.items():
            for s in quoted(text):
                if any(s in f for f in fixtures):
                    continue
                if s == f"under {tiny} Mt" or (s == "down more than N%" and "down more than" in WEB["lib"]) or (s == "late" and " · late" in WEB["view"]):
                    continue
                if s in WEB["view"] or s in WEB["lib"] or s in WEB["side"] or s in WEB["ind"] or s in outside or s in json.dumps(REGISTRY["portwatch"]):
                    continue
                self.fail(f"{name}: the quoted words {s!r} are in no fixture, no page text of the code and no other part of the two texts")

    def test_each_publisher_quotation_the_page_relies_on_is_in_its_passages_with_its_address(self):
        wanted = {
            "method-links": ["baltic-terms-clause-5-1", "sse-footer", "ams-privacy-public-information", "ams-datasets-non-copyrighted",
                             "ams-datasets-vessel-rates-source", "agtransport-vessel-loading-attribution", "agtransport-vessel-rates-attribution"],
            "notice-links": ["sse-footer", "ams-privacy-public-information", "ams-datasets-non-copyrighted", "ams-datasets-vessel-rates-source",
                             "agtransport-vessel-loading-attribution", "agtransport-vessel-rates-attribution"],
            "method": ["portwatch-ship-categories", "portwatch-chokepoint-trade-estimate", "dallasfed-proxy"],
            "notice-dallas": ["dallasfed-proxy"],
        }
        for name, keys in wanted.items():
            for k in keys:
                q = QUOTES[k]
                text = P[name]
                if name == "notice-dallas":
                    # NOTICE gives the part of the sentence that says what the index is a proxy for
                    self.assertIn("may be viewed as a proxy for the volume of shipping in global industrial commodity markets", text)
                    self.assertIn("may be viewed as a proxy for the volume of shipping in global industrial commodity markets", q["quotation"])
                else:
                    self.assertIn(f'"{q["quotation"]}"', text, f"{name}: {k}")
                self.assertIn(q["address"], text, f"{name}: {k}: the address of the page")
        self.assertIn("read on 25 November 2026", P["method-links"])
        self.assertIn("read on 25 November 2026", P["notice-links"])
        self.assertIn("read 25 November 2026", P["method"])

    def test_the_quoted_dates_are_the_dates_the_fixtures_give(self):
        self.assertEqual(LINK_FX["read"], OWN_FX["read"])
        self.assertEqual(OWN_FX["read"], "2026-11-25")


class NoClaimThatNoPageMakes(unittest.TestCase):
    def test_no_passage_about_a_publisher_calls_its_data_public_domain_open_or_free_to_reuse(self):
        for name in LINK_ONLY_PASSAGES:
            text = P[name]
            for s in quoted(text):  # the AMS sentence says "public information", which is its own wording
                text = text.replace(f'"{s}"', "")
            self.assertNotRegex(text, r"(?i)public domain|open data|open licen[cs]e|\bopen\b|free to reuse|free of charge|freely (usable|reusable)", name)
        # the passage on the Dallas Fed and BLS and the passage on PortWatch keep to their own terms: none says "public domain" of USDA or SSE
        for name in ("method", "notice-digest", "notice-dallas"):
            self.assertNotRegex(P[name], r"(?i)free to reuse|open licen[cs]e|open data", name)
        for sid in ("sse", "usda-ams"):
            e = REGISTRY[sid]
            self.assertNotRegex(" ".join(e[f] for f in ("name", "licence", "access", "use")).replace(LINK_FX["quotations"][1]["quotation"], ""),
                                r"(?i)public domain|open data|open licen[cs]e|free to reuse", sid)

    def test_no_universal_negative_about_freight_rates(self):
        pat = re.compile(r"(?i)\bno free (source|series|rate|index)|none (of them )?(is|are) (both )?free|not free\b|nobody publishes|"
                         r"no (source|series) (exists|gives)|there is no (free )?(source|series)|free source gives no|no free")
        for name, text in P.items():
            self.assertIsNone(pat.search(text), f"{name}: {pat.search(text) and pat.search(text).group(0)}")
        # the sentence about the atlas, not about the world, is the page's
        self.assertIn("the atlas shows no spot rate for tankers or gas carriers and no Baltic Exchange index value", WEB["view"])
        self.assertNotRegex(WEB["view"] + WEB["lib"] + WEB["ind"], r"(?i)no free (source|series)")

    def test_the_passages_name_no_package_review_or_state_that_was_never_published(self):
        for name, text in P.items():
            self.assertNotRegex(text, r"\bFN\d|\bpackage\b|critique|critic\b|\breviewer\b|\bdesign(er)?\b|\bgated\b|waits for the owner", name)

    def test_the_text_says_it_is_a_choice_made_without_the_owner_and_does_not_say_the_owner_decided_it(self):
        self.assertIn("a choice made without the owner, listed in `PROGRESS.md`", P["method"])
        self.assertNotRegex(P["method"], r"(?i)the owner (decided|accepted|chose|approved)")
        # the one decision of the owner that NOTICE names for PortWatch is the one it already quotes, of 25 November 2026, about how it is read
        self.assertIn("The owner's decision of 25 November 2026", NOTICE)
        self.assertNotRegex(P["notice-digest"], r"(?i)the owner (accepted|approved|chose)")


class TheFiguresAreTheConstantsOfTheCode(unittest.TestCase):
    def test_five_passages_four_weeks_52_weeks_28_days_and_364_days_are_the_builders(self):
        m = P["method"]
        self.assertEqual((BM.PASSAGES, BM.WEEKS, BM.YEAR_BACK, BM.RANK_WEEKS), (5, 4, 52, 52))
        self.assertIn(f"{NUMBER_WORDS[BM.PASSAGES]} passages each", m)
        self.assertIn(f"the last {NUMBER_WORDS[BM.WEEKS]} complete weeks ({7 * BM.WEEKS} days)", m)
        self.assertIn(f"the same {NUMBER_WORDS[BM.WEEKS]} weeks a year earlier", m)
        self.assertIn(f"{BM.YEAR_BACK} weeks ({7 * BM.YEAR_BACK} days", m)
        self.assertIn(f"over the {BM.RANK_WEEKS} weeks that end with the year-earlier window", m)
        self.assertIn(f"The {NUMBER_WORDS[BM.WEEKS]} weeks that end on `to` ({7 * BM.WEEKS} days", m)
        self.assertIn(f"Five passages, {NUMBER_WORDS[BM.WEEKS]} weeks and {BM.RANK_WEEKS} weeks are the atlas's choices", m)
        self.assertIn(f"times {7} and summed over the {NUMBER_WORDS[BM.WEEKS]} weeks", m)
        self.assertIn(f"the {NUMBER_WORDS[BM.PASSAGES]} passages of each ship type are the {NUMBER_WORDS[BM.PASSAGES]} with the most estimated cargo of that type over the {BM.RANK_WEEKS} weeks", P["notice-digest"])
        self.assertIn(f"over the last {NUMBER_WORDS[BM.WEEKS]} complete weeks ({7 * BM.WEEKS} days) and over the same {NUMBER_WORDS[BM.WEEKS]} weeks a year earlier", P["notice-digest"])
        self.assertIn(f"{NUMBER_WORDS[BM.WEEKS]} complete weeks ({7 * BM.WEEKS} days)", P["notice-digest"])
        self.assertEqual(BM.TYPES, ("tanker", "dry"))

    def test_the_rounding_and_the_significant_figures_are_those_of_the_builders(self):
        m = P["method"]
        self.assertEqual(BM.SIG3.prec, 3)
        self.assertIn("written to three significant figures", m)
        self.assertIn("three significant figures", P["notice-digest"])
        # the weekly means: one decimal for the vessels and four for the cargo, as build_portwatch.py writes them
        src = read("pipeline", "freight", "build_portwatch.py")
        self.assertIn("[round(x, 1) for x in wk[col]]", src)
        self.assertIn("round(x / 1e6, 4)", src)
        self.assertIn("which `build_portwatch.py` rounds to 0.1", m)
        self.assertIn("weekly means to four decimals", m)
        self.assertIn("vessels a day, one decimal; Mt a day", P["notice-digest"])
        self.assertIn("with a half rounded up", m)
        self.assertEqual(BM.ROUND_HALF_UP, "ROUND_HALF_UP")

    def test_the_page_rule_for_a_small_cargo_and_a_fall_to_nearly_nothing_is_the_pages(self):
        tiny = re.search(r"TINY_MT = ([0-9.]+)", WEB["lib"]).group(1)
        self.assertIn(f"A cargo under {tiny} Mt, the status board's limit, is printed \"under {tiny} Mt\"", P["method"])
        self.assertIn("body = '99.9'", WEB["lib"])
        self.assertIn("reads −99.9%", P["method"])
        self.assertIn("down more than ${", WEB["lib"])
        # the status board's own limit is the same number
        board = read("web", "src", "components", "views", "BoardView.tsx")
        self.assertIn(f"TINY_MT = {tiny}", board)

    def test_the_alert_threshold_is_three_runs_and_the_step_is_not_a_first_failure_step(self):
        self.assertEqual(status.ALERT_AFTER, 3)
        self.assertNotIn("build-market-now", status.ALERT_AFTER_SOURCE)
        self.assertIn("build-market-now", status.BUILD_STEPS)
        self.assertIn(f"alerts after {NUMBER_WORDS[status.ALERT_AFTER]} failed runs in a row", P["method"])
        self.assertIn(f"`{BM.SOURCE}`", P["method"])

    def test_the_files_and_the_status_source_named_are_the_builders(self):
        m = P["method"]
        self.assertTrue(os.path.exists(BM.OUT))
        self.assertIn("`data/freight/market-now.json`", m)
        self.assertEqual(os.path.relpath(BM.OUT, ROOT), os.path.join("data", "freight", "market-now.json"))
        self.assertIn("`pipeline/freight/build_market_now.py`", m)
        self.assertTrue(os.path.exists(os.path.join(ROOT, "pipeline", "freight", "build_market_now.py")))
        self.assertIn("`data/freight/portwatch/<passage>.json`", m)
        self.assertEqual(os.path.relpath(BM.SERIES, ROOT), os.path.join("data", "freight", "portwatch"))
        # the digest stores no name and no gas key, as the text says
        doc = json.loads(read("data", "freight", "market-now.json"))
        self.assertEqual(sorted(doc["types"]), ["dry", "tanker"])
        for rows in doc["types"].values():
            for r in rows:
                self.assertNotIn("name", r)
        self.assertEqual((doc["weeks"], doc["days"], doc["rankWeeks"]), (BM.WEEKS, 7 * BM.WEEKS, BM.RANK_WEEKS))
        self.assertEqual(doc["s"], "portwatch")

    def test_the_refusals_the_text_lists_are_the_builders(self):
        m = P["method"]
        src = read("pipeline", "freight", "build_market_now.py")
        for words, code in (
            ("is not the series its name says", "not the series of"),
            ("has no estimated cargo", "no vol block"),
            ("is not a Monday", "which is not a Monday"),
            ("is not a finite number or is negative", "is not a finite number"),
            ("a week is missing or extra", "a week is missing or extra"),
            ("earlier than the one published", "earlier than the one published"),
        ):
            self.assertIn(code, src)
            # the text words it in its own way: the key words
        for fragment in ("a file is not the series its name says or has no estimated cargo", "its first week is not a Monday",
                         "a value is not a finite number or is negative", "a week is missing or extra", "fewer than five series exist",
                         "`to` is earlier than the one published", "a series does not reach back far enough"):
            self.assertIn(fragment, m)
        self.assertIn("at least {PASSAGES} are needed to name {PASSAGES} passages", src)
        self.assertIn(f"fewer than {NUMBER_WORDS[BM.PASSAGES]} series exist", m)
        self.assertIn("exit code 0", m)
        self.assertIn("The file is not rewritten when its content is the same", m)

    def test_the_text_says_where_the_step_runs_as_the_workflow_has_it(self):
        wf = read(".github", "workflows", "update-portwatch.yml")
        self.assertIn("python pipeline/freight/build_market_now.py", wf)
        self.assertIn("data/freight/market-now.json", wf)
        self.assertIn("the last build step of the weekly PortWatch job", P["method"])
        # the annual job rebuilds neither the weekly series nor this file
        self.assertNotIn("build_market_now", read(".github", "workflows", "update-annual.yml"))
        self.assertIn("the annual job rebuilds neither the weekly series nor this file", P["method"])


class ThePageSaysWhatTheTextSays(unittest.TestCase):
    def test_the_sentences_of_the_page_that_the_text_gives_are_the_pages(self):
        self.assertIn("No traffic figures are available.", WEB["view"])
        self.assertIn('"No traffic figures are available."', P["method"])
        self.assertIn("weekly averages of PortWatch's daily counts, times 7 and summed over the four weeks", WEB["view"])
        # the page takes names from chokepoints.json and prints the id, with no link, for a passage the catalogue lacks
        self.assertIn("loadChokepoints", WEB["view"])
        self.assertIn("name ?? row.id", WEB["view"])
        # the page keeps the indicators and the links when the digest is missing
        self.assertIn("keeps the indicators and the links", P["method"])
        # the page states how the five are chosen, and that the rule is the atlas's
        self.assertIn("a rule of the atlas, not of PortWatch", WEB["view"])
        # a link is not cited: no data-src on a link row
        link_row = WEB["view"][WEB["view"].index("function LinkRow"):WEB["view"].index("export default function")]
        self.assertNotIn("data-src", link_row)
        self.assertNotIn("SourceLine", link_row)
        self.assertIn("A link is not cited: it has no source line and no date", P["method-links"])

    def test_the_gas_carrier_wording_is_the_pages(self):
        self.assertIn("PortWatch lists five ship classes (container, dry bulk, general cargo, ro-ro and tanker) and defines none", WEB["view"])
        self.assertIn("the atlas cannot say whether gas carriers are in its tanker class", WEB["view"])
        self.assertIn("The atlas shows no separate gas carrier figure.", WEB["view"])
        self.assertIn("the atlas cannot tell whether gas carriers are in PortWatch's tanker class", P["method"])
        self.assertIn("shows no gas carrier figure", P["method"])
        self.assertIn("section 4", P["method"])
        self.assertRegex(METHOD, r"The three liquids are compared with the tankers of IMF PortWatch in the chokepoint\s+estimates")

    def test_the_links_the_page_gives_are_in_the_text_with_their_address_and_name_their_registry_entry(self):
        hrefs = re.findall(r"href: '([^']+)'", WEB["ind"])
        self.assertEqual(len(hrefs), 2)
        for h in hrefs:
            self.assertIn(h, P["method-links"])
            self.assertIn(h, REGISTRY["sse"]["licence"], "the registry names the pages read")
        for sid in ("baltic", "usda-ams"):
            self.assertIn(REGISTRY[sid]["url"], P["method-links"], sid)
        self.assertIn("(registry `baltic`)", P["method-links"])
        self.assertIn("(`sse`)", P["method-links"])
        self.assertIn("(`usda-ams`)", P["method-links"])
        for name in re.findall(r"name: '([^']+)'", WEB["ind"]):
            if name.startswith(("Baltic", "China Import")):
                self.assertIn(name, P["method-links"] if name.startswith("China") else METHOD)
        self.assertIn("weekly grain vessel line-up", P["method-links"])
        self.assertIn("grain ocean freight rates", P["method-links"])

    def test_the_two_indicators_are_the_ones_the_page_shows_and_the_registry_has_them(self):
        ids = re.findall(r"id: '([^']+)', segment", WEB["ind"])
        self.assertEqual(ids, ["igrea-m", "freight-ppi-m"])
        for i in ids:
            self.assertIn(f"`{i}`", P["method"])
        index = {s["id"]: s for s in json.loads(read("data", "prices", "index.json"))}
        self.assertEqual(index["igrea-m"]["s"], "dallasfed")
        self.assertEqual(index["freight-ppi-m"]["s"], "bls")
        # the mark "late" the text describes is the price board's rule
        prices = read("web", "src", "lib", "prices.ts")
        self.assertRegex(prices, r"15")
        self.assertIn("the 15th of the second month after its last month", P["method"])
        # the Dallas Fed index is described as the Bank does, and the page cites Kilian twice
        self.assertIn("Kilian (2009) with the correction of Kilian (2019)", P["method"])
        self.assertIn("Kilian 2009, with the correction discussed in Kilian 2019", P["notice-dallas"])
        self.assertIn("as proposed in Kilian (2009), with the correction discussed in Kilian (2019)", WEB["ind"])


class TheOtherTexts(unittest.TestCase):
    def test_the_registry_names_the_digest_and_the_two_publishers(self):
        self.assertIn("data/freight/market-now.json", REGISTRY["portwatch"]["use"])
        for sid in ("sse", "usda-ams"):
            self.assertIn("no value is stored or shown", REGISTRY[sid]["use"], sid)
        self.assertIn("no index value", REGISTRY["baltic"]["use"])

    def test_the_readme_and_the_section_7_pointers_name_the_page(self):
        self.assertIn("**Freight market now** page", read("README.md"))
        self.assertIn("The Freight market now page (section 5) shows the first two", METHOD)
        self.assertIn('under\n  "Freight market now".', METHOD)

    def test_the_notice_rows_say_no_value_is_stored_or_shown_and_the_digest_adds_no_request(self):
        r = P["notice-rows"]
        self.assertEqual(r.count("no value is stored or shown"), 2)
        self.assertIn("All Rights Reserved", r)
        d = P["notice-digest"]
        self.assertIn("with no request to PortWatch or to any other site", d)
        self.assertIn("**IMF PortWatch (IMF and University of Oxford), data adapted**", d)
        self.assertIn("CC BY 4.0 release does not extend IMF's rights", d)
        # the credit line of NOTICE is the registry's
        self.assertIn("IMF PortWatch (IMF and University of Oxford), data adapted", REGISTRY["portwatch"]["licence"])


if __name__ == "__main__":
    unittest.main()
