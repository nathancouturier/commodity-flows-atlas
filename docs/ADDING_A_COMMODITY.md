# Adding a customs group or a commodity page

Written while the fertilisers were added (package NC1, audit M-022). A **customs group** is a set of HS 1992 codes of
`pipeline/trade/hs_map.py`; a **page** is a commodity of `data/commodities/index.json`. A group lives on one page (it may
be the page's main table, a further pair of tables of it, or the page's lanes). Commands run from the repository root with
`.venv/bin/python -I`; never run `npm install`, `vite build` or a formatter.

## 0. Decide, then look at the codes
1. Pick the page: a new group of an existing page (`FERT_EXTRA`, like ammonia on "Urea & nitrogen") or a new page
   (`sulphur`, `npk`). One HS code is in one group only; a product that matters to a second page gets one line there.
2. Read each code and its wording in `raw/baci/product_codes_HS92_V202601.csv`. The page says what the code really
   holds (HS 310310 is all superphosphates, single and triple; there is no code for TSP alone). List the codes you leave out.
3. A product that moves in bags or boxes gets tables and no lanes (leave it out of `GROUPS` of `build_lanes.py`).

## 1. Customs cache (`pipeline/trade`)
- `hs_map.py`: add the group to `HS` (comment: what the code holds, what is left out).
- Extract to a temporary file first (2 minutes), compare, then replace the tracked cache:
  `python pipeline/trade/extract_baci.py raw/baci/BACI_HS92_V202601.zip /tmp/new_flows.csv.gz 2002`; check that every
  earlier group is identical (`DataFrame.equals` on the rows of the old groups), then copy over `pipeline/cache/baci_flows.csv.gz`.
- `clean.py` `HOMOGENEOUS` only for one product priced by the product tonne (else only the gross-error rule applies);
  `checks.py` `LABEL` for a group whose name is not its id with hyphens turned into spaces ("UAN", "MAP").

## 2. Trade engine (`pipeline/freight`), for a group that sails
| File | Entry |
|---|---|
| `modes.py` | `FAMILY[group]` (the mode depends on borders and ports, not on the cargo) |
| `ports.py` | `SEGMENT[group]`; add the group to `OWN_FAMILY` when the cargo is not served by the berths that the fertiliser, grain or other rows name (liquids, sulphur): only a row that names the group counts, the fall-backs and their basis do the rest. Add no port. |
| `vessel_rules.py` | `classes()`: a group not dry bulk needs its own branch (comment the reason; METHODOLOGY section 4) |
| `vessel_classes.json` | `cargoes` of the classes the rule names (page ids), and a sentence in `notes` of a class used in a new way |
| `build_lanes.py` | `GROUPS`, `COMMODITY` (group to page id, when different), `LABEL`, `CAP`, `FLOOR` |
| `build_freight.py` | `TANKER_GROUPS` for tankers and gas carriers, `ACRONYM`; `GROUPS_OF` only for hand-written routes |
| `generated_routes.py` | `LATER_GROUPS`: the new groups with a cap of their own, so that no published route is dropped |

Check the coverage test (`test_lanes.py`, S01): a group whose main set carries under 63% of its seaborne tonnes needs a
lower `FLOOR` (and a higher `CAP`). Mirror every floor in `test_lanes.py`. Do not write hand-made routes.
Run in order: `build_lanes.py`, `build_freight.py`, `infrastructure/port_limits.py`, `infrastructure/route_assets.py`,
`freight/build_alerts.py`. The lane and pairs files of earlier groups must stay byte-identical (`cmp` against a copy).

## 3. The page (`pipeline/commodities`)
- `data/commodities/index.json`, by hand: `id, name, family, blurb (no figure), unit, hs, has, rank`, and `sub` for a
  sub-heading ("Fertilisers"). The builder reads this file and rewrites `has` and `sub`; a new id has no recipe without it.
- `build_commodities.py`: `TRADE` (page to main group), `INDEX_SUB`, `BASIS` (what each table measures, printed in titles),
  `USGS` or `PSD` for production (read the unit and measure of the file; say them in the title), `FERT_EXTRA` for extra groups
  (keys `<stem>-exports` / `<stem>-imports`, the only form that the page, the history and the country pages read), a branch of
  the chain in `main()` for a new page (trade only: copy `npk`), notes with the codes left out, `see.append({"k": page,
  "text": ...})` for a product of another page (drawn "See <page> for <text>."), `name_it()` for titles and KPI labels.
- A page with no free production table says so in a note (`No production table: ...`); no price series: nothing to write,
  the page shows "No free price series" by itself. Prices only from the World Bank file (`build_prices.py` `PINK`, `NO_PAGE`,
  `ADDED`); `PRICE_COVERAGE_NOTE` in `web/src/lib/prices.ts` says which products of a page have a series.
- `build_profiles.py`: `EXTRA_SIDE` (key to side, customs group, label) for each extra table, `PRODUCTS` (net and partners),
  `TRADE_LABEL` for the main line of a page that now holds several products.
- Run `build_prices.py raw/worldbank/CMO-Historical-Data-Monthly.xlsx raw/eia-spot`, `build_commodities.py`,
  `build_profiles.py`; the other commodity files must not change (compare with a copy of `data/` taken before you start).

## 4. Web (`web/src`)
`lib/freight.ts` (`LANE_GROUPS` per page, `GROUP_LABEL` per group of a page that has several), `lib/search.ts`
(`COMMODITY_ALIASES`: the trade names a page is found by), `lib/prices.ts` (coverage note). Colour and dot come from the
family; the list takes the entry from the index, under its `sub`. No count of commodities is written by hand in the About
window, README or METHODOLOGY (checked in package NC1). `npx tsc --noEmit` from `web/`.

## 5. Tests, documentation
- A test file for the package (`test_fertilisers.py`): codes, one home per code, the page's world total against the cleaned
  cache, the totals of every earlier group (`BEFORE`: all years and 2024 tonnes, computed from the cache before the change),
  the vessel rules, the links between pages. Tests that count the whole atlas change with it: `test_lanes.py` (P01 rows, P05
  size, S08 lanes), `test_modes.py` M10 (tonnes by mode), `test_final_fixes.py` (number of chokepoint estimates),
  `test_shares.py` `TANKER`, `test_generated_routes.py` (cap), `test_release_gr4d.py` (METHODOLOGY section 2 and 3 numbers
  and the "N pairs files" sentence of `build_port_index.py`).
- METHODOLOGY.md: section 2 (families), 3 (generated corridors, counts), 4 (vessel rules), 10 (what the group holds, basis,
  limits). DATA_SOURCES.md and NOTICE.md lists are written by `common/sources_table.py` and `common/notice_lists.py`.

## 6. Rebuild and checks
Builders in this order: `geo/adjacency.py`, `freight/build_lanes.py`, `freight/build_freight.py`, `infrastructure/port_limits.py`,
`infrastructure/route_assets.py`, `freight/build_alerts.py`, `prices/build_prices.py`, `companies/build_companies.py`,
`commodities/build_commodities.py`, `commodities/build_profiles.py`, `common/sources_table.py`, `common/notice_lists.py`; then
`node web/scripts/validate-data.mjs`, `validate-freight.mjs`, `validate-infra.mjs`, `npm test --prefix web`,
`python -m unittest discover -s pipeline/tests -p "test_*.py"` (about 3 minutes), `npx tsc --noEmit` in `web/`.
After any builder: `git checkout -- data/_status`. Look at `git status --short data/` and `du -sk data` (budget in
`web/scripts/check-size.mjs`; the series by year of `data/commodities/history` have a 3 MB budget in `validate-data.mjs`).
Browser: `cd web && npx vite --port <port> --strictPort`; open each new page at 1440 and 390 px, the country pages that gain
lines, the search, the price drawer; no "undefined", "NaN", empty block or console error.

## Traps met
- Wikipedia refuses the research client with a 429: write the class of a lane as an Atlas assumption, say no page was read.
- Adding groups to `AUDIT_GROUPS` of `generated_routes.py` shares the 120-route cap and drops published routes: use `LATER_GROUPS`.
- `GROUPS_OF` in `build_freight.py` also sums the volumes of the hand-written routes: leave the new groups out of it.
- The "up to" figures of the chokepoint estimates of earlier groups move a little when a group is added (PortWatch caps are
  shared); this is expected, and so are the alert lists and the country profiles. Nothing else of an earlier group may move.
- An extra table key that does not end with `-exports`, `-imports`, `-production` is left out of the country pages.
- Rows below 1,000 t and 1 million USD are not in the cache; a table's world total is the cleaned cache, 2 to 10% from the
  archive's own sum for products with many small flows or missing tonnage (estimated from value, said in the note).
- The USGS year of the file is the edition year minus one: read the rows, not the title, before you name a year.
- A liquid or a chemical is not "fertiliser berth" cargo: a page that names fertilisers says nothing of an ammonia terminal.
