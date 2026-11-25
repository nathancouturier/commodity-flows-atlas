# Companies layer

The atlas lists the main producers, processors and traders of each commodity, and the main shipping companies by
segment. The lists are written by hand in this folder and published by `build_companies.py`. Nobody edits the
published files.

| Source file | Holds | Published to |
|---|---|---|
| `energy.json` | crude-oil, refined-products, lng, natural-gas, lpg, thermal-coal, met-coal, uranium | `data/commodities/companies.json` |
| `metals.json` | iron-ore, steel, copper, aluminium, bauxite, nickel, cobalt, lithium, zinc, lead, tin, manganese, gold, silver, pgm, rare-earths | `data/commodities/companies.json` |
| `agri.json` | wheat, corn, soybeans, soymeal, soyoil, rapeseed, rice, sugar, coffee, cocoa, cotton, palm-oil, potash, phosphate, urea | `data/commodities/companies.json` |
| `shipping.json` | shipping companies by segment: `dry-bulk`, `tankers`, `gas`, `charterers`, `brokers`, `terminals` | `data/freight/shipping-companies.json` |

The commodity files are objects keyed by commodity id, then by group (`producers`, `processors`, `traders`), each a
list of entries. `shipping.json` is keyed by segment, each a list of entries.

## Build

From the repository root:

    .venv/bin/python -I pipeline/companies/build_companies.py           # check every entry, then write the two published files
    .venv/bin/python -I pipeline/companies/build_companies.py --check   # exit 1 if a published file is out of date

The builder checks every entry against the rules below and writes nothing while one entry breaks them; it prints
each problem with the commodity, the group, the position and the name. The published files keep the formatting of
the sources (`json.dumps(obj, indent=1, ensure_ascii=False)` and a final newline), and so must the source files.
The tests are in `pipeline/tests/test_companies.py`.

## Reading a filing on sec.gov

sec.gov asks automated clients to declare a User-Agent with a contact address (its page "Accessing EDGAR data").
The owner decided on 24 November 2026 that a contact address is sent to the SEC, and to nobody else, when its filings
are read: it is the environment variable `SEC_CONTACT_EMAIL`, set by the owner. The address is written in
no file of the repository. `sec_edgar.py` of this folder is the only script that reads the variable: it adds the
address to the shared User-Agent of the update scripts, sends nothing without it, sends it to sec.gov only (a redirect
to another host is not followed), asks one page at a time at least 2 seconds apart (sec.gov's published limit is 10
requests a second), stops at an HTTP 403 or 429 without asking again, and keeps the pages it fetched in
`pipeline/cache/sec/`, outside git (`pipeline/tests/test_sec_edgar.py`). No workflow runs it: a person reads the
figures. From the repository root:

    .venv/bin/python -I pipeline/companies/sec_edgar.py cik nutrien                 # the CIK of a filer with a ticker
    .venv/bin/python -I pipeline/companies/sec_edgar.py search "Petroleos Mexicanos" --forms 20-F   # any filer
    .venv/bin/python -I pipeline/companies/sec_edgar.py filings 1725964             # its latest annual reports
    .venv/bin/python -I pipeline/companies/sec_edgar.py index <document url>        # the exhibits of a filing
    .venv/bin/python -I pipeline/companies/sec_edgar.py find <document url> "potash production" --context 300

`find` prints the passages of the document's text that match, with their place in the text file of the cache. An
amendment (10-K/A, 20-F/A) that only replaces an exhibit, an auditor's report or a consent leaves the original
report as the one cited: read its explanatory note.

## An entry

```json
{
  "name": "Frontline",
  "hq": "CYP",
  "role": "shipowner",
  "own": "listed",
  "parent": "Hemen Holding Limited (largest shareholder)",
  "detail": "Crude and product tanker owner, Limassol",
  "fig": {"v": 80, "u": "ships", "what": "fleet owned", "y": 2025, "s": "company-reports",
          "url": "https://…", "n": "As of December 31, 2025 the company owned 80 vessels (fourth quarter 2025 report)."},
  "sanction": {"by": "OFAC", "since": "2025-10", "url": "https://home.treasury.gov/news/press-releases/…"},
  "s": "company-reports",
  "url": "https://…",
  "y": 2025,
  "read": "2026-11",
  "classes": ["vlcc", "suezmax", "aframax", "lr2"]
}
```

| Field | Rule |
|---|---|
| `name` | The name the company uses today. A former name goes in `detail` ("formerly …") while readers still use it. |
| `hq` | ISO3 code of the head office as the page states it (a code of `data/countries/index.json`). |
| `role` | Free text: producer, refiner, trader, shipowner, operator, charterer, shipbroker, terminal operator, state buyer… No superlative. |
| `own` | One of `state`, `state-listed` (state-controlled and listed), `listed`, `private`, `cooperative`. Leave it out when no page read says. A state that is the largest shareholder without control does not make a company `state-listed`: the shareholder goes in `parent` with its share. |
| `parent` | The controlling shareholder or parent, as the page states it. Optional. A share ("(82.36%)") is the share the page states, with its date when the page dates it ("44.6% in January 2015"); otherwise no percentage. No superlative, apart from "largest shareholder". |
| `parentUrl` | The page that states the share in `parent`. Required for a percentage unless the entry's `s` is `wikipedia` (the article is then the page); it may be the entry's own `url`. The site links it when it is another page. |
| `detail` | One line. No superlative ("largest", "leading", "top"…) unless the same entry carries the dated figure that supports it and the page makes the claim for that year. Dated facts carry their date ("in November 2025"). |
| `fig` | One comparable figure for the commodity (or, for a shipping company, its fleet): `v` a number; `u` a unit only, one of `Mt`, `kt`, `t`, `kb/d`, `Mboe/d`, `bcm`, `Mtpa`, `Mt/y`, `ships`, `Mdwt`, `Mcbm`, `TEU`; `what` says what is counted and on which basis ("liquids production (crude oil, condensate, NGL)", "LNG sold", "fleet, owned and chartered-in"); `y` the year the figure refers to (a fiscal year takes the calendar year in which it ends, and `n` says so); `s` and `url` the page that states it; `n` optional, the stated number and the factor of any conversion. Never a figure from memory and never a figure the page does not state. A figure that covers several commodities ("oil and gas production", "crude and products traded") is not a `fig`: write it in `detail` with its date and what it covers. The page of a figure is a dated document: a generic page ("about us", "investors") is refused, as its text changes every year. |
| `sanction` | Only from the authority's own notice or list, read in the session that adds it: `by` (`OFAC`, `EU`, `UK`), `since` (`YYYY` or `YYYY-MM`), `url`. A list of such objects when several authorities designate the company. `since` is the date of the designation in the notice or list read, which may not be the first one: the site writes "OFAC designation of October 2020". A sanction that was lifted is removed. "Sanctioned" is never written outside this field. |
| `s`, `url` | `s` is an id of `data/sources.json`; `url` is the dated document or page that supports the entry (an annual report, a results release, a filing, the Wikipedia article). A home page is refused, and so is a Wikipedia special, talk or disambiguation page. |
| `y` | The year the entry's facts refer to, equal to `fig.y` when there is a figure. Never the year of reading. Left out when the page gives no date. |
| `read` | `YYYY-MM`, the month the page was read, not later than the current month. Required. |
| `classes` | Shipping companies only: ids of `pipeline/freight/vessel_classes.json` that the page read names for the company's fleet. Left out when the page names none (the class page then lists the company among the others of its segment, "classes not stated"). |

One company, one identity: where a company stands under several commodities or segments, its `name`, `hq`, `own`,
`parent`, `parentUrl` and `sanction` must be the same everywhere. The `fig` belongs to the commodity it stands under.

## Sources

- A company's own annual report, production report or results release: `company-reports`, with the document's
  address in `url` (infrastructure assets also cite this id with their own page).
- Annual reports filed with the US Securities and Exchange Commission (10-K, 20-F, 40-F, and the exhibits of a 40-F
  that hold the annual report): `sec-edgar`, with the document's sec.gov address in `url`. They are read on sec.gov
  (see "Reading a filing on sec.gov" below). Where that cannot be done, the same report is read on the company's
  investor pages and may still be cited by its EDGAR address.
- Wikipedia (CC BY-SA 4.0): `wikipedia`, with the article address. Accepted for now; a company's own report is
  preferred whenever it gives the fact.
- Sanctions: `ofac` (US Treasury press releases on designations), `uk-sanctions` (GOV.UK announcements and the UK
  sanctions list, whose entry gives the date designated); `eu-sanctions` is the id for the EU's Official Journal if an
  EU designation is added (register it first, from the Official Journal text read).
- Single figures of a public body: `cochilco` (Codelco's production).
- Not used: Equasis, Clarksons Research, Kpler, S&P and other paid or restricted data; association ranking tables
  (worldsteel, GIIGNL, World Nuclear Association, ICCO) are not copied: the company's own report gives its figure.

## On the site

A commodity page lists the companies by group. Rows whose figures count the same thing in the same unit form a block
ordered by value; other figures form their own blocks, and rows without a figure follow in the order of the file.
Each row shows the figure with its year and a link to its page, the conversion note, the ownership, a sanction mark
with the authority and the month, and the assets of the infrastructure layer whose operator field names the company
(as operator or as an owner with a share). A former owner does not count: a name preceded, in the same clause of the
operator field (up to a semicolon, a comma or a bracket), by "sold by", "ex-", "formerly", "previously" or "bought
(from)"; nor does a name that begins another company of the lists ("Gazprom" in "Gazprom Neft"). A country page lists
the companies headquartered there, the shipping companies with their segment. A vessel-class page lists the shipping
companies whose `classes` name it, and those of its segment whose page names no class; a class whose segment has no
company (container ships) has no list. Fleets counted on different bases (owned, chartered-in, leased, managed, with
ships on order) are separate blocks. The search finds a company by its name and opens the page that lists it, its row
shown (`co=<name>` in the link). The
source line under each list says when the pages were read; the year of each fact is on its row.

## Adding or changing an entry

1. Read the page that states the fact (a dated document, not a home page). Note its address and the month.
2. Write the entry in the right file and group, with `read` set to that month. Copy the identity fields from the
   company's other entries if it already stands elsewhere.
3. For a figure, copy the number as the page gives it; convert only units (pounds, short tons, cubic feet, barrels a
   year), and put the stated number and the factor in `n`.
4. Run the builder; fix every problem it prints; run `pipeline/tests/test_companies.py`.
5. Do not edit `data/commodities/companies.json` or `data/freight/shipping-companies.json` by hand.

## Review routine

Once a year, after the annual reports (March to May): re-read each entry with a figure, update `fig`, `y` and
`read`, and look again at each sanction notice (remove a lifted sanction). An entry whose `read` is more than two
years old is read again or removed.
