"""The words about the Freight market now page (METHODOLOGY.md, NOTICE.md, the README and the registry) against the builder, the page and the
sentences they quote. Every quotation of those texts about the publishers is word for word in a fixture (the two committed ones, with their
address and the day they were read); every figure the texts give (five passages, four weeks, 52 weeks, 28 days, the rounding, the alert
threshold, the cargo limit of the page) is the constant of the code that applies it; and the texts claim for no publisher what no page read says.

Run: .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_market_now_texts.py"
With the pages as they were saved (MARKET_NOW_PAGES names the folder that holds the saved files at the paths of SAVED below; without it the
test does not compare the quotations with the pages): MARKET_NOW_PAGES=<folder> .venv/bin/python -I -m unittest discover -s pipeline/tests -p "test_market_now_texts.py"
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
from common import sources_table, status  # noqa: E402

FIXTURES = os.path.join(ROOT, "pipeline", "tests", "fixtures")
OWN = os.path.join(FIXTURES, "market_now_texts_quotations.json")
LINKS = os.path.join(FIXTURES, "link_only_sources_quotations.json")
# the folder of the pages as they were saved when the quotations were read (outside the repository; the machine's own, given in the environment, no
# default): the quotations are compared with the pages where it is set
WORK = os.environ.get("MARKET_NOW_PAGES")
SAVED = {
    "portwatch-ship-categories": ("item", "PORTS/samples/item_3da2b9ca97684916b75c4013f95d18ab.json"),
    "portwatch-chokepoint-trade-estimate": ("item", "PORTS/samples/item_3da2b9ca97684916b75c4013f95d18ab.json"),
    "dallasfed-proxy": ("html", "FNOW/critic/dl/dallasfed-igrea.html"),
    "baltic-terms-clause-5-1": ("html", "VOYAGE/dl/baltic-terms.html"),
    "sse-footer": ("html", "FNOW/dl/sse-home.html"),
    "ams-privacy-public-information": ("html", "FNOW/critic/dl/ams-privacy.html"),
    "ams-datasets-non-copyrighted": ("html", "FNOW/dl/ams-gtr-datasets.html"),
    "ams-datasets-vessel-activity-table": ("html", "FNOW/dl/ams-gtr-datasets.html"),
    "ams-datasets-vessel-activity-counts": ("html", "FNOW/dl/ams-gtr-datasets.html"),
    "ams-datasets-vessel-rates-source": ("html", "FNOW/dl/ams-gtr-datasets.html"),
    "agtransport-vessel-loading-attribution": ("field", "FNOW/dl/views-vh5k-mnyv.json", "attribution"),
    "agtransport-vessel-rates-attribution": ("field", "FNOW/dl/views-ehs5-yac3.json", "attribution"),
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
    if not WORK or not os.path.exists(os.path.join(WORK, spec[1])):
        return None
    with open(os.path.join(WORK, spec[1]), encoding="utf-8", errors="replace") as fh:
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
            self.skipTest("MARKET_NOW_PAGES does not name the folder of the saved pages")

    def test_the_saved_item_names_five_classes_does_not_say_what_each_holds_and_does_not_mention_gas_carriers(self):
        text = saved_text(SAVED["portwatch-ship-categories"])
        if text is None:
            self.skipTest("MARKET_NOW_PAGES does not name the folder of the saved pages")
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
                             "ams-datasets-vessel-activity-table", "ams-datasets-vessel-activity-counts", "ams-datasets-vessel-rates-source", "agtransport-vessel-loading-attribution", "agtransport-vessel-rates-attribution"],
            "notice-links": ["sse-footer", "ams-privacy-public-information", "ams-datasets-non-copyrighted",
                             "ams-datasets-vessel-activity-table", "ams-datasets-vessel-activity-counts", "ams-datasets-vessel-rates-source",
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
        self.assertIn("the atlas shows no spot rate for tankers or gas carriers and no Baltic Exchange index value", WEB["lib"])
        self.assertNotRegex(WEB["view"] + WEB["lib"] + WEB["ind"], r"(?i)no free (source|series)")

    def test_the_freight_family_of_the_prices_claims_no_more_than_the_pages_read(self):
        text = flat(METHOD)
        self.assertIn("the atlas shows no freight rate: for none of the sources it has read has it established that the rates may be republished "
                      "(see \"Freight rates that are not stored\" below)", text)
        self.assertNotRegex(text, r"(?i)is both free and open to republication|none of the sources it has read is")
        self.assertIn("- Freight rates that are not stored.", METHOD)

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

    def test_the_paragraph_of_the_notice_gives_the_same_constants_as_the_method_and_every_count_in_both_is_the_builders(self):
        n, m = P["notice-digest"], P["method"]
        self.assertIn(f"for tankers and for dry bulk carriers at {NUMBER_WORDS[BM.PASSAGES]} passages each", n)
        self.assertIn(f"lists {NUMBER_WORDS[BM.PASSAGES]} passages each", m)
        self.assertIn(f"over the {BM.RANK_WEEKS} weeks that end with the year-earlier window", n)
        self.assertIn(f"{NUMBER_WORDS[BM.WEEKS]} complete weeks ({7 * BM.WEEKS} days) and over the same {NUMBER_WORDS[BM.WEEKS]} weeks a year earlier", n)
        self.assertIn(f"multiplied by 7 and added over the {NUMBER_WORDS[BM.WEEKS]} weeks", n)
        # every count of days, weeks and passages of the two passages is one of the builder's (what a quotation says of the pages of others is not)
        days = {str(7 * BM.WEEKS), str(7 * BM.YEAR_BACK)}
        for name, text in (("method", m), ("notice-digest", n)):
            text = re.sub(r'"[^"]*"', " ", text)
            self.assertLessEqual(set(re.findall(r"\b(\d+) days?\b", text)), days, f"{name}: days")
            self.assertLessEqual(set(re.findall(r"\b(\d+) weeks?\b", text)), {str(BM.RANK_WEEKS)}, f"{name}: weeks in figures")
            self.assertLessEqual(set(re.findall(r"\b(one|two|three|four|five|six|seven|eight) weeks\b", text)), {NUMBER_WORDS[BM.WEEKS]}, f"{name}: weeks in words")
            self.assertLessEqual(set(re.findall(r"\b(\w+) passages each\b", text)), {NUMBER_WORDS[BM.PASSAGES]}, f"{name}: passages a list")

    def test_no_total_is_made_and_the_ship_classes_are_the_ones_the_item_lists(self):
        n, m = P["notice-digest"], P["method"]
        self.assertIn("a ship that crosses several passages is counted at each of them, and no total is made", n)
        self.assertIn("it has no world total", m)
        self.assertIn("no gas carrier figure, and no world total", m)
        # the classes, in the item's own words and order, in the passage of the method (a quotation) and in the notice
        classes = "container, dry bulk, general cargo, ro-ro and tanker"
        self.assertIn(classes, QUOTES["portwatch-ship-categories"]["quotation"])
        self.assertIn(f"({classes})", n)
        self.assertIn(f"lists five ({classes}) and does not say what each holds", n)
        self.assertIn(f"({classes}) and does not say what each holds", WEB["lib"])
        for text in (m, n):
            self.assertNotRegex(text, r"(?i)(ro-ro,? tanker and gas|and gas carriers? (class|are a class))")

    def test_the_ranking_is_on_the_unrounded_sum_in_the_method_and_in_the_notice_and_only_an_exact_tie_goes_by_id(self):
        m, n = P["method"], P["notice-digest"]
        self.assertIn("ranked on the sum before rounding; `rankMt` is that sum in Mt to three significant figures, so two passages can show the same figure; only an exact tie of the sums goes by id", m)
        self.assertIn("ranked on the sum before rounding, a rule of the atlas and not of PortWatch", n)
        for text in (m, n):
            self.assertNotRegex(text, r"(?i)a tie goes by (id|name)|tie[s]? (is|are)? ?broken by name|ties? by name")
        # the builder and the page do what the text says
        src = read("pipeline", "freight", "build_market_now.py")
        self.assertIn("key=lambda r: (-r[0], r[1])", src)  # the unrounded sum, then the id
        self.assertIn("b.sum - a.sum || (a.s.id < b.s.id ? -1 : 1)", WEB["lib"])

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
        self.assertIn(f"\"under {tiny} Mt\", the status board's limit, when it is above zero and under {tiny} Mt", P["method"])
        self.assertIn(f"the year-earlier cargo is above zero and under {tiny} Mt, whatever was stored", P["method"])
        self.assertIn(f"the cargo of the last four weeks is above zero and under {tiny} Mt", P["method"])
        self.assertIn(f"100 x (year earlier - {tiny}) / year earlier", P["method"])
        self.assertIn("TINY_AGO_TITLE", WEB["lib"])
        # the −99.9 is stored by the builder, which is where the rule is: the page prints what it is given
        self.assertIn("r = -999", read("pipeline", "freight", "build_market_now.py"))
        self.assertIn("r = -999", WEB["lib"])
        self.assertIn("`−99.9%`: a fall that one decimal would round to 100% while something is left in the window", P["method"])
        self.assertIn("`−100%` is printed only when the stored change is exactly −100", P["method"])
        # the cases the page no longer prints are not in the code
        self.assertNotIn("<0.1", WEB["lib"])
        self.assertNotIn("Math.max(-99.9", WEB["lib"])
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
            ("has more decimals than the weekly files carry", "has more than {decimals} decimals"),
            ("a week is missing or extra", "a week is missing or extra"),
            ("earlier than the one published", "earlier than the one published"),
        ):
            self.assertIn(code, src)
            # the text words it in its own way: the key words
        for fragment in ("a file is not the series its name says or has no estimated cargo", "its first week is not a Monday",
                         "a value is not a finite number, is negative or has more decimals than the weekly files carry (one for a vessel count, four for the cargo in Mt a day",
                         "a week is missing or extra", "fewer than five series exist",
                         "`to` is earlier than the one published", "fewer than five can be ranked"):
            self.assertIn(fragment, m)
        self.assertIn("at least {PASSAGES} are needed to name {PASSAGES} passages", src)
        self.assertIn(f"fewer than {NUMBER_WORDS[BM.PASSAGES]} series exist", m)
        self.assertIn("exit code 0", m)
        self.assertIn("The file is not rewritten when its content is the same", m)

    def test_the_text_says_where_the_step_runs_as_the_workflow_has_it(self):
        wf = read(".github", "workflows", "update-portwatch.yml")
        self.assertIn("python pipeline/freight/build_market_now.py", wf)
        self.assertIn("data/freight/market-now.json", wf)
        self.assertIn("follows the alert banners in the weekly PortWatch job and comes before the digest of changes", P["method"])
        self.assertNotIn("last build step", P["method"])
        self.assertNotIn("last build step", read("docs", "UPDATING.md"))
        self.assertIn("### Freight market digest: a build step of the PortWatch job", read("docs", "UPDATING.md"))
        # the order the text gives is the workflow's: alert banners, then the market digest, then the digest of changes
        self.assertLess(wf.index("python pipeline/freight/build_alerts.py"), wf.index("python pipeline/freight/build_market_now.py"))
        self.assertLess(wf.index("python pipeline/freight/build_market_now.py"), wf.index("python pipeline/common/changes.py"))
        # the annual job rebuilds neither the weekly series nor this file
        self.assertNotIn("build_market_now", read(".github", "workflows", "update-annual.yml"))
        self.assertIn("the annual job rebuilds neither the weekly series nor this file", P["method"])


class TheRulesOfTheDigestAreSaidAsTheyAre(unittest.TestCase):
    """The sentences of METHODOLOGY.md and docs/UPDATING.md about what the builder stores, refuses and says: each is pinned whole, so that a
    sentence turned into its opposite fails a test."""

    def test_the_stored_minus_99_9_and_the_printed_minus_100_are_the_rules_of_the_code(self):
        self.assertIn("`−99.9%`: a fall that one decimal would round to 100% while something is left in the window. The builder stores −99.9 and the page prints it as it is; "
                      "`−100%` is printed only when the stored change is exactly −100, that is when nothing is left.", P["method"])
        # the builder stores it: a fall that rounds to −100.0 while something is left
        D = BM.Decimal
        self.assertEqual(BM.pct(D("0.1"), D("100000")), -99.9)
        self.assertEqual(BM.pct(D("0"), D("7")), -100.0)

    def test_a_series_that_lags_dates_the_digest_earlier_and_a_date_that_would_go_back_is_a_refusal(self):
        m = P["method"]
        self.assertIn("a series that lags dates the digest earlier, it does not stop it", m)
        self.assertIn("When that date would be earlier than the stored digest's, the run is refused (see the paragraph on refusals below).", m)
        self.assertIn("or `to` is earlier than the one published", m)
        # and the builder refuses it
        self.assertIn("earlier than the one published", read("pipeline", "freight", "build_market_now.py"))

    def test_a_series_too_short_to_rank_is_left_out_with_a_line_and_the_digest_is_built_from_the_others(self):
        m = P["method"]
        self.assertIn("A weekly file that starts after the first of those 52 weeks (a passage mapped lately) cannot be ranked: it is left out of the ranking, "
                      "with a line in the builder's output, and the digest is built from the others.", m)
        self.assertIn("(a series that does not reach back far enough is only left out of the ranking, see the paragraph on the five passages above)", m)
        self.assertNotRegex(m, r"(?i)a series that does not reach back far enough is refused|too short[^.]* is refused")
        # the builder's line, which the text and UPDATING.md quote
        notes = BM.Notes()
        notes.left_out = [("newpass", "2026-01-05")]
        self.assertEqual(notes.lines(), [f"left out of the ranking: newpass.json starts on 2026-01-05, after the first of the {BM.RANK_WEEKS} ranking weeks"])
        self.assertIn("left out of the ranking: <passage>.json starts on", flat(read("docs", "UPDATING.md")))

    def test_updating_says_what_the_output_and_what_the_status_note_say_of_a_series_that_lags(self):
        u = flat(read("docs", "UPDATING.md"))
        self.assertIn("one series that lags holds the digest's date back for every passage and the figures of every row are those of the earlier week, without any failure", u)
        self.assertIn("the output of the step names the series the digest waits for", u)
        self.assertIn("the note of its status record", u)
        self.assertIn("gives the count and the date", u)
        self.assertIn("without naming any", u)
        self.assertIn("the new date would be earlier than the file published and the run is refused", u)
        self.assertNotRegex(u, r"output of the step and the note of its status record")
        # what the builder does: the output names the series, the note gives the count and the date and names none
        notes = BM.Notes()
        notes.ahead = (6, "2026-11-29", ["gg", "hh"], "2026-11-22")
        out = " ".join(notes.lines())
        self.assertIn("6 series end later than the digest, on 2026-11-29", out)
        self.assertIn("the last complete week of gg, hh", out)
        self.assertEqual(notes.note(), "; 6 series end later than 2026-11-22 (on 2026-11-29)")
        self.assertNotIn("gg", notes.note())

    def test_the_bound_applies_only_when_the_year_earlier_cargo_is_not_under_it_and_the_dashes_come_first(self):
        tiny = re.search(r"TINY_MT = ([0-9.]+)", WEB["lib"]).group(1)
        m = P["method"]
        self.assertIn(f"the cargo of the last four weeks is above zero and under {tiny} Mt and the year-earlier cargo is not under {tiny} Mt "
                      "(the dashes above come first: a row with nothing a year earlier, or with both cargoes under it, prints a dash)", m)
        # the page decides in that order: a stored null, then a year-earlier cargo under the bound, then the bound
        body = WEB["lib"][WEB["lib"].index("export function mtChangeText"):WEB["lib"].index("/** What a row prints")]
        self.assertLess(body.index("pct == null || tinyMt(ago)"), body.index("tinyMt(now)"))


class TheAboutWindowAgreesWithItself(unittest.TestCase):
    """The Sources tab and the Method tab of the About window say the same of the figures the atlas computes, and the introduction of the Sources
    tab claims no more than its table lists."""

    ABOUT = flat(read("web", "src", "components", "AboutDialog.tsx"))

    def test_the_introduction_of_the_sources_tab_says_every_figure_comes_from_a_free_public_source_and_names_the_publishers_only_linked(self):
        a = self.ABOUT
        self.assertIn("Every figure the atlas shows comes from a free, public source. Each figure on the site names its source and its year; this table lists every "
                      "source with its licence{linkOnlyClause(linked)}.", a)
        self.assertNotIn("The atlas uses free, public sources only. Each figure on the site", a)
        # the number is read from the registry as sources_table.py reads it: an entry whose use says that no value is stored or shown
        self.assertIn("const linked = list.filter(isLinkOnly).length;", a)
        lib = read("web", "src", "lib", "linkOnly.ts")
        self.assertIn(f"LINK_ONLY_MARK = '{sources_table.LINK_ONLY_MARK}'", lib)
        self.assertEqual(sources_table.link_only(list(REGISTRY.values())), ["sse", "usda-ams"])
        self.assertIn("of which it shows no value", lib)
        # the credits paragraph counts the publishers that give a value, not those that are only linked
        self.assertIn("s.id !== 'atlas' && !isLinkOnly(s)", a)

    def test_the_two_tabs_name_the_same_rule_for_the_figures_the_atlas_computes(self):
        a = self.ABOUT
        sources_tab = 'marks an estimate computed by the atlas; sums and ratios of one source\'s own published figures keep that source\'s credit and say "data adapted" (see the Method tab).'
        self.assertIn('"Atlas estimate" ' + sources_tab, a)
        self.assertNotIn("marks a figure computed by the atlas", a)
        method_tab = ("Sums and ratios of one source's own published figures, such as the weekly averages and the changes against a year earlier of IMF PortWatch's traffic, "
                      'are not estimates: they keep the source\'s credit and say "data adapted".')
        self.assertIn(method_tab, a)
        self.assertIn('Estimates computed by the atlas, such as route and chokepoint shares, are labelled "Atlas estimate".', a)
        # both tabs: sums and ratios of one source's own published figures, the source's credit, "data adapted"; and the tab the sentence points to exists
        for text in (sources_tab, method_tab):
            self.assertRegex(text, r"(?i)sums and ratios of one source's own published figures")
            self.assertRegex(text, r"credit and say \"data adapted\"")
        self.assertIn("{ id: 'method', label: 'Method' }", a)
        # METHODOLOGY gives the reason for the digest the same way: sums and ratios of PortWatch's own figures, not an estimate, its source id and "data adapted"
        self.assertIn("sums and ratios of PortWatch's own published figures, not an estimate of the atlas, so they carry PortWatch's source id and the words \"data adapted\"", P["method"])

    def test_the_sentence_that_says_the_atlas_uses_free_public_sources_is_about_what_it_uses(self):
        # the "What it does not do" list: the atlas takes no value from a publisher it only links to, so the claim there stays true; it is not a claim about the table
        self.assertIn("No Baltic Exchange index values and no other paid data: the atlas uses free, public sources only.", self.ABOUT)


class NoWordThePageNeverUses(unittest.TestCase):
    def test_the_table_of_the_usda_is_named_as_the_page_names_it_everywhere_the_atlas_describes_it(self):
        pattern = r"(?i)\bline[- ]?up\b"
        for name, text in (("registry", json.dumps(REGISTRY)), ("NOTICE.md", NOTICE), ("METHODOLOGY.md", METHOD), ("DATA_SOURCES.md", read("DATA_SOURCES.md")),
                           ("README.md", read("README.md")), ("page", WEB["view"]), ("library", WEB["lib"]), ("indicators", WEB["ind"])):
            self.assertIsNone(re.search(pattern, text), name)
        self.assertEqual(REGISTRY["usda-ams"]["name"], "USDA Agricultural Marketing Service, Grain Transportation Report datasets (weekly port region grain ocean vessel activity, grain ocean freight rates)")
        self.assertIn("Weekly port region grain ocean vessel activity (number of vessels)", QUOTES["ams-datasets-vessel-activity-table"]["quotation"])
        self.assertIn("weekly port region grain ocean vessel activity", NOTICE)
        # in running text: the weekly count of grain vessels
        self.assertIn("the weekly count of grain vessels", P["method-links"])
        self.assertIn("the weekly count of grain vessels", P["notice-links"])


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
        lib = WEB["lib"]
        self.assertIn("The description of PortWatch's passage data that the atlas read lists five ship classes (container, dry bulk, general cargo, ro-ro and tanker) and does not say what each holds", lib)
        self.assertIn("the atlas cannot say whether gas carriers are in its tanker class: the tanker figures may include them or not", lib)
        self.assertIn("The atlas shows no separate gas carrier figure.", lib)
        # no text of the repository says that PortWatch "defines none" of its classes: the atlas read one description
        for text in (WEB["view"], lib, WEB["ind"], METHOD, NOTICE):
            self.assertNotRegex(text, r"(?i)defines none|does not define any of them|and does not define\b")
        # shown under the tanker list only when it has rows, and the lead counts the indicators the page has
        self.assertIn("type === 'tanker' && rows.length > 0", lib)
        self.assertIn("leadText(indicators?.length ?? 0)", WEB["view"])
        self.assertIn("it is the one description read, and\n    other PortWatch documents may say more", METHOD)
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
        self.assertIn("weekly count of grain vessels", P["method-links"])
        # the page's line for the vessel count is the table's own name and says what the table counts, Vancouver included
        self.assertIn(f"name: '{QUOTES['ams-datasets-vessel-activity-table']['quotation']}'", WEB["ind"])
        self.assertIn("in the Gulf, the Pacific Northwest and Vancouver, B.C.", WEB["ind"])
        self.assertIn("Vancouver, B.C.", REGISTRY["usda-ams"]["use"])
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
