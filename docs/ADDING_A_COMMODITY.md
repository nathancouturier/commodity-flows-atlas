# Adding a customs group or a commodity page

Written while the fertilisers were added (audit point M-022), corrected and extended with the grains and oilseeds (audit point
M-023) and with the metal bulks (audit point A-010), and corrected after each review round of the sixth release. A **customs group** is a set of HS 1992 codes of
`pipeline/trade/hs_map.py`; a **page** is a commodity of `data/commodities/index.json`. A group lives on one page (it may
be the page's main table, a further pair of tables of it, or the page's lanes). Commands run from the repository root with
`.venv/bin/python -I`; never run `npm install`, `vite build` or a formatter.

## 0. Decide, then look at the codes
1. Pick the page: a new group of an existing page (`EXTRA_GROUPS`, like ammonia on "Urea & nitrogen" or wheat flour on "Wheat") or a new
   page (`sulphur`, `npk`, `barley`). One HS code is in one group only; a product that matters to a second page gets one line there.
   A page whose products are the kinds of one customs code (the pulses of HS 0713) is one group; the kinds are read from the six-digit
   rows (section 3, "kinds").
2. Read each code and its wording in `raw/baci/product_codes_HS92_V202601.csv`. The page says what the code really
   holds (HS 310310 is all superphosphates, single and triple; there is no code for TSP alone). List the codes you leave out.
3. A product that moves in bags or boxes gets tables and no lanes (leave it out of `GROUPS` of `build_lanes.py`: wheat flour and the brewing
   and distilling dregs). The label of a group says what its code holds (one code for two oils, one for all dregs): `LABEL` of `build_lanes.py`
   and of `checks.py`, the titles of the tables, the notes.

4. A page whose products are alloys or grades of one family (the ferro-alloys) is one page with one customs group for each product that
   has lanes or its own table; the page opens on its largest group (`TRADE`: its key figure and its first table are that group's) and the
   others are `EXTRA_GROUPS`. Heading 7202 minus ferro-nickel is five groups; ferro-nickel stays in its group of the nickel page, and each
   page names the other by a `see` line.
5. Check that the stem of an extra group is free: the metallurgical coal page already holds the EIA tables `coke-production`, `coke-exports` and
   `coke-imports`, so the customs coke group takes the stem `coke-customs` (a key is read by its last word and a table of the same key would hide
   the other).

## 1. Customs cache (`pipeline/trade`)
- `hs_map.py`: add the group to `HS` (comment: what the code holds, what is left out).
- Extract to a temporary file first (5 minutes), compare, then replace the tracked cache (the extract also writes `baci_group_totals.csv`, the totals of each group and year before the 1,000 t / USD 1 million
  threshold, beside the output; copy it too: a page note says so when its tables hold under 97% of the file's total):
  `python pipeline/trade/extract_baci.py raw/baci/BACI_HS92_V202601.zip /tmp/new_flows.csv.gz 2002`; check that every
  earlier group is identical (`DataFrame.equals` on the rows of the old groups), then copy over `pipeline/cache/baci_flows.csv.gz`.
- `clean.py` `HOMOGENEOUS` only for one product priced by the product tonne (else only the gross-error rule applies), and only if the pairs that declare their own price level do not carry more than a tenth of the tonnes that rule 4 adds or removes (list the rows that rule 4 re-estimates, and for each the other years of its pair that lie beyond the factor 3 on the same side: `test_fncd.py` D6 does it for the fourteen groups added with the fertilisers, the grains and the metal bulks; coke and sunflower oil failed it). A single bad row of a group outside the set goes in `ESTIMATE_ROWS` (empty since the sixth release); the exports of a country under a code for a product it cannot have made (Mozambique's coke: the EIA series of coke production gives it none, and its tonnes are probably coal declared as coke) go in `DROP`, which `clean()` lists in `LAST_DROPPED` and `QA.md`, and the page of the group says what was left out and that the rows are not counted. A group priced by kinds that lie
  ten times apart (sunflower seed: some French pairs at 11,000 to 14,000 USD/t, the group median at 1,300) goes in `UV_KEPT_GROUPS`: rules 3 and 4 leave the reported tonnage of a row whose
  unit value is above the group reference and flag it `uv-suspect-t`; below the reference rule 3 applies as everywhere. After the first cleaning run list the rows that rules 3 and 4 re-estimate to more than 50 kt and five times the pair's median of the other years (the test
  `test_fncb.py` B2 does it): decide each one, keep the reported tonnage through `KEEP_REPORTED` (one row, one reason) or say in the test why the estimate is right;
  `checks.py` `LABEL` for a group whose name is not its id with hyphens turned into spaces ("UAN", "MAP"), and `PSD_GROUPS` of `checks.py`
  for a group that has a USDA PSD commodity (the customs-against-USDA checks).
- Six-digit kinds of one code: add the group to `GROUPS` of `extract_hs6_detail.py`, run it the same way (to a temporary file, check that the
  rows of the earlier groups are identical, copy), and list the kinds in `SPLITS` of `pipeline/commodities/metals.py` (a function like
  `pulse_tables` writes the tables of each kind from the derived groups).

## 2. Trade engine (`pipeline/freight`), for a group that sails
| File | Entry |
|---|---|
| `modes.py` | `FAMILY[group]` (the mode depends on borders and ports, not on the cargo: `grain` for dry food cargo, `vegoil` for the oils) |
| `ports.py` | `SEGMENT[group]` (a group that sails in bulk must not be in segment `box`: `build_freight.py` compares every `box` group with PortWatch's container, general-cargo and ro-ro ships, so chromite is `ore` and coke `coal`, and scrap, pig iron and DRI are `box` for their ports (the general port of the country, as steel has: the `ore` fall-backs would send Turkey's scrap to Samsun on the Black Sea, the nearest seaport of a country with no ore row; a country whose general port is on one coast needs a row for the other coast, as Turkey's steel works have, or the wrong-coast check of `build_lanes.py` leaves the flows from that coast unrouted) with `DRY_BOX` of `build_freight.py` keeping them in the dry-bulk comparison; the ferro-alloys, which are general cargo, are `box` too; all are in `BOX_GENERAL` so that their basis reads "general port of the country". Read the ports of the biggest lanes of a new group before you accept its segment); add the group to `OWN_FAMILY` when the cargo is not served by the berths that the fertiliser, grain or other rows name (liquids, sulphur): only a row that names the group counts, the fall-backs and their basis do the rest; a fertiliser group of `OWN_FAMILY` that sails from the same exporters as the other fertilisers goes in `LEGACY_OWN_FAMILY` too, so that the port used before for fertiliser (Jubail for Saudi Arabia) comes ahead of the general port of the country (Jeddah); a group that takes the rows of another group of its family (the sunflower and rapeseed oils take the rows of palm and soybean oil) goes in `GENERAL_BASIS`, so that its ports read "general port of the country". Add no port. |
| `vessel_rules.py` | `classes()`: a group not dry bulk needs its own branch (comment the reason; METHODOLOGY section 4); a group that falls in an existing family joins that branch's tuple (the grains and oilseeds, the vegetable oils) |
| `vessel_classes.json` | `cargoes` of the classes the rule names (page ids), `cargoLabels` where only one group of a page sails in the class (the chip then names the product, "Ammonia" on a gas carrier, and still opens the page), and a sentence in `notes` of a class used in a new way (keep the file's own layout: `json.dumps(indent=1, ensure_ascii=False)` rewrites it byte for byte) |
| `build_lanes.py` | `GROUPS`, `COMMODITY` (group to page id, when different), `LABEL`, `CAP`, `FLOOR` |
| `web/scripts/validate-freight.mjs` | `FLOOR` (the same table as `build_lanes.py` and `test_lanes.py`: a main lane under its group's floor fails the validator; `test_fncc.py` C10 compares the three) |
| `build_freight.py` | `TANKER_GROUPS` for tankers and gas carriers, `ACRONYM`; `GROUPS_OF` only for hand-written routes |
| `generated_routes.py` | `LATER_GROUPS`: one entry (groups, cap) for each package, so that the corridors of a new batch of groups do not take the places of the others; its first corridors come first. A route of the last release is never put out by a cap (`pipeline/freight/released_ids.json`, see "At each release" in `UPDATING.md`) |

A group dropped from `GROUPS` after a run leaves its lane and pairs files behind (`build_lanes.py` writes, never deletes): remove them.
A group whose pairs are spread over hundreds of small flows (the other ferro-alloys: 0.6 Mt over 396 pairs) reaches 63% only with dozens of lanes: give it
tables and no lanes rather than a floor of a few hundred tonnes, and say so in the page's notes and METHODOLOGY.
Check the coverage test (`test_lanes.py`, S01): a group whose main set carries under 63% of its seaborne tonnes needs a
lower `FLOOR` (a tonnage in Mt, not a share) and a higher `CAP`. Mirror every floor in `test_lanes.py` and in `web/scripts/validate-freight.mjs`.
Do not write hand-made routes.
Run in order: `build_lanes.py`, `build_freight.py`, `infrastructure/port_limits.py`, `infrastructure/route_assets.py`,
`freight/build_alerts.py`. The lane and pairs files of earlier groups must stay byte-identical (`cmp` against a copy).

## 3. The page (`pipeline/commodities`)
- `data/commodities/index.json`, by hand: `id, name, family, blurb (no figure), unit, hs, has, rank`, and `sub` for a
  sub-heading ("Fertilisers"). The builder reads this file and rewrites `has` and `sub`; a new id has no recipe without it.
  `rank` is the position in the list (0 to n-1, each once, a test checks it) and the list is in that order: put the page where it
  belongs (the grains together, the fertilisers last under their sub-heading) and renumber. Name in a blurb only what the page's own
  table shows (the countries that lead its exports) and write no figure. `hs` lists the codes the page loads, a heading when every code
  of the heading is loaded and the six-digit codes when only some are (1512 also holds cottonseed oil).
- `build_commodities.py`: `TRADE` (page to main group), `INDEX_SUB`, `BASIS` (what each table measures, printed in titles),
  `USGS` or `PSD` for production (read the unit and measure of the file; say them in the title; `PSD_WHAT` names the crop in the
  table notes), `EXTRA_GROUPS` for extra groups (keys `<stem>-exports` / `<stem>-imports`, the only form that the page, the history and
  the country pages read; it was `FERT_EXTRA` when only the fertilisers used it), `PSD_EXTRA` for the USDA production and use of the oil and the meal of a
  seed page (keys `<stem>-production` / `<stem>-consumption`: the page lists them under production and consumption, the country pages draw
  a line from each), a branch of the chain in `main()` for a new page (trade only: copy `npk` or `pulses`; a PSD crop needs only its
  `TRADE`, `PSD` and `PSD_WHAT` entries), notes with the codes left out, `see.append({"k": page,
  "text": ...})` for a product of another page (drawn "See <page> for <text>."), `name_it()` for titles and KPI labels.
- A page with no free production table says so in a note (`No production table: ...`). Prices: look before you write that a page has none. A Pink Sheet series that is
  already published without a page (`NO_PAGE` of `build_prices.py`: its keys are the page keys of the series, here `palm-kernel-oil`, and its values the family that the series
  is listed under, `softs`; so adding its customs groups to the Palm oil page does not attach it) is attached by changing its page key, the second element of its tuple in `PINK`,
  to the page's id, and deleting its entry of `NO_PAGE` (the key of `PINK` itself is the World Bank column name, `"Palm kernel oil"`, which the header check reads: leave it); the page's `PRICE_COVERAGE_NOTE` then says which
  products of the page the series prices, and METHODOLOGY section 7 (prices) lists it. With no series at all there is nothing to write: the page shows "No free price series" by
  itself. Prices only from the World Bank file (`build_prices.py` `PINK` with its `PINK_DESC`
  row, `NO_PAGE`, `ADDED`; `PINK_LEFT_OUT` lists the columns the atlas leaves out) and from the USGS file on disk: look first in the price rows of
  `raw/usgs/MCS*_Commodities_Data.csv` (`USGS_PRICES` of `build_prices.py`: one entry for each annual series, with the file's own wording of the statistic, a name that says
  what the file says it is, `OPENS_ON` when a page has several) before you write "no free price series" on a page (a review found five pages whose notes said none while the file
  had a price). `PRICE_COVERAGE_NOTE` in `web/src/lib/prices.ts` says which
  products of a page have a series (the ferro-alloys page has ferro-chromium and 75% ferrosilicon and no series for the other alloys; the sulphur page has the USGS price of elemental
  sulphur; the urea page has the Pink Sheet's urea and the USGS price of ammonia, in the file's unit, US dollars per short ton). A USGS row names its unit and its basis in its own words: copy them, and where the
  row does not say what its unit is a unit of (molybdenum: "dollars per kilogram", of oxide or of contained molybdenum), say so in `UNIT_UNSAID` of `build_prices.py` and in the page's note
  (`test_fncg.py` G7 checks every label against its row). A year is marked estimated only where its own Notes carry the segment "Estimated.". A series that stopped (barley and sorghum, August 2020) is published as it is: `mark_closed()` marks it
  `closed`, `figures_of()` keeps it for a page that has no other series, the page shows "Last price ... series closed", and the page's note
  (`_price_end()`) says the last month from the published index; run `build_prices.py` before `build_commodities.py` (the rebuild script does). The
  annual workbook goes on after a closed monthly series: `ANNUAL_NOMINAL` publishes the years after its last month as an annual series of its own (`barley-a`), which
  the page's key figure shows ("Annual average 2025") and the drawer opens beside the closed series; a closed price must not be the only price a page shows when the
  workbook has a later one.
- A group with tables and no lanes (the other ferro-alloys, molybdenum ore, graphite) needs `GROUP_K` of `build_profiles.py` (customs group to page), and
  `MAIN_GROUP`, `VALUE_GROUPS` and `TRADE_LABEL` when the page id is not its group's (chromium, molybdenum); a page of a USGS commodity takes its
  production and reserves from `USGS` (read the rows first: chromium reserves are given in two measures for two different years, and the page shows the
  one of the year of the production). The United States figures of the USGS file go to the page by `US_NAMES` in `metals.py` (ferrous scrap has no other).
- `build_profiles.py`: `EXTRA_SIDE` (key to side, customs group, label) for each extra table, `PRODUCTS` (net and partners; the customs group
  of a product with no lanes needs `GROUP_K`, which makes the builder read its cleaned frame), `MAIN_GROUP` and `VALUE_GROUPS` when the page's
  main customs group is not its id (`sunflower` is read from `sunflower-seed`), `TRADE_LABEL` for the main line of a page that now holds
  several products. The country page shows the first eight lines of each section: a product of rank 28 is under "Show all".
- A product that a country receives overland and neither makes nor sells (Mozambique's chromite and ferro-chromium) gets the note of `transit_notes()` in `metals.py` where the
  pairs file of its group says the imports are overland (the hub rule needs the country in the export table too); read which rows it fires on after a new group, and list them.
- A large flow whose declared destination or origin is a landlocked trading centre (Switzerland: Qatar's sulphur, Zambia's refined copper, Malaysia's iron ore) gets an entry of kind `landlocked-centre` in the `REGISTRY` of `caveats.py` (the text is computed from the data): the lane page,
  the rows of the two countries and the notes of the page carry it, the tonnes stay in the tables and in the estimates of the passages, and `build_freight.py` leaves the pair out of the generated corridors. Look for such a pair
  after a new group: a pair that is most of a landlocked buyer's imports and a large share of the exporter's exports.
- Kinds of one code (`pulse_tables()` in `metals.py`): the tables of each kind are extra tables of the page (`peas-exports`...), without a
  series by year (the six-digit rows start in 2019).
- Run `build_prices.py raw/worldbank/CMO-Historical-Data-Monthly.xlsx raw/eia-spot`, `build_commodities.py`,
  `build_profiles.py`; the other commodity files must not change (compare with a copy of `data/` taken before you start).

## 4. Web (`web/src`)
`lib/freight.ts` (`LANE_GROUPS` per page, in the order of the commodity list: the Route finder sorts its list by the index's `rank` all the same, `GROUP_LABEL` per group of a page that has several), `lib/search.ts`
(`COMMODITY_ALIASES`: the trade names a page is found by: "DDGS", "lentils", "canola", "HMS", "HBI"; no alias holds a word that is the beginning of a code another page is found by: "dried" would answer "DRI"), `lib/prices.ts` (coverage note), and
`PriceFigure.tsx` (a closed series). Colour and dot come from the
family; the list takes the entry from the index, under its `sub`. No count of commodities is written by hand in the About
window, README or METHODOLOGY (checked when the fertilisers were added). `npx tsc --noEmit` from `web/`.

## 5. Tests, documentation
- A test file for the package (`test_fertilisers.py`, `test_grains.py`): codes, one home per code, the page's world total against the
  cleaned cache, the totals of every earlier group (`BEFORE`: all years and 2024 tonnes, computed from the cache before the change; a
  package's file lists the groups of the packages before it too), the vessel rules, the links between pages, the price blocks. Tests that
  count the whole atlas change with it: `test_lanes.py` (P01 rows, P05 size, S08 lanes, the `FLOOR` mirror), `test_modes.py` M10 (tonnes by
  mode), `test_final_fixes.py` (number of chokepoint estimates), `test_shares.py` `TANKER`, `test_generated_routes.py` (cap),
  `test_release_gr4d.py` (METHODOLOGY section 2 and 3 numbers and the "N pairs files" sentence of `build_port_index.py`),
  `test_history.py` (how many tables of the series by year carry an out-of-line year), and for a price series that changes the
  tests of `test_prices.py` (closed series, figures, the rows whose dates overlap) and the `PINK_HEADER` table of `test_prices_raw.py`.
- The coverage matrix (`data/coverage.json`): a new page gets its row when `pipeline/commodities/build_coverage.py` runs after
  `build_commodities.py` (the annual job runs it too). Every block the page does not have yet is "missing" and appears on
  the work list; type a reason in `pipeline/commodities/coverage_reasons.json` only for a block that cannot apply to the page
  (with the text it rests on), never for one that is merely not loaded yet. Then run
  `.venv/bin/python -I pipeline/commodities/build_coverage.py --raise-floor` so that the blocks the page has are protected
  against a later loss, and commit the three files (`data/coverage.json`, the floor, the reasons if changed) with the page.
  The reasons are tested against the files (`pipeline/tests/test_governance.py`).
- METHODOLOGY.md: section 2 (families), 3 (generated corridors, counts), 4 (vessel rules), 5 (the chokepoint estimates and their PortWatch cap: a group moves them, and
  `typeNotes` is the note of a ship type), 7 (prices: a series attached, a unit, a note), 10 (what the group holds, basis,
  limits). Every number a sentence gives about the groups, the lanes, the routes, the pairs and the estimated rows is read from the files by a test (`test_fncg.py` G9, `test_release_gr4d.py`). DATA_SOURCES.md and NOTICE.md lists are written by `common/sources_table.py` and `common/notice_lists.py`.

Tests of the whole atlas that a new group moves (the metal bulks moved them all): `test_shares.py` (`CARGO` and `TANKER` sets: the vessel type of a group), `test_final_fixes.py` (the
number of chokepoint estimates), `test_history.py` (size of the series by year, 3.9 MB since the sixth release, and the number of tables with an out-of-line year), `test_modes.py` M10,
`test_lanes.py` (P01, P05, S08 and the `FLOOR` mirror), `test_release_gr4d.py` (METHODOLOGY: the groups and Mt of "2024 by mode" and "Generated corridors"; the count of pairs
files in `build_port_index.py`), `test_release_gr4s.py` (the words a visitor reads: no "USGS file", "builder", "cache" in a page text), `test_metal_flows.py` (`group_of`
of a ferro-alloy code), and `test_grains.py` / `test_fertilisers.py` (the cache holds the groups before and the new ones: a later package adds groups; the number of
generated routes).

## 6. Rebuild and checks
Builders in this order: `geo/adjacency.py`, `freight/build_lanes.py`, `freight/build_freight.py`, `infrastructure/port_limits.py`,
`infrastructure/route_assets.py`, `freight/build_alerts.py`, `prices/build_prices.py`, `companies/build_companies.py`,
`commodities/build_commodities.py`, `commodities/build_coverage.py`, `commodities/build_profiles.py`, `common/sources_table.py`, `common/notice_lists.py`; then
`node web/scripts/validate-data.mjs`, `validate-freight.mjs`, `validate-infra.mjs`, `npm test --prefix web`,
`python -m unittest discover -s pipeline/tests -p "test_*.py"` (about 4 minutes), `npx tsc --noEmit` in `web/`.
After any builder: `git checkout -- data/_status`. Look at `git status --short data/` and `du -sk data` (budget in
`web/scripts/check-size.mjs`; the series by year of `data/commodities/history` have a 3 MB budget in `validate-data.mjs`).
Browser: `cd web && npx vite --port <port> --strictPort`; open each new page at 1440 and 390 px, the country pages that gain
lines, the search, the price drawer; no "undefined", "NaN", empty block or console error.

## 7. What the review rounds of the sixth release added
A new group meets these, in the order of the files above:
- **Caveats** (`pipeline/trade/caveats.py`, `data/freight/caveats.json`, 35 entries): the kinds are `mirror`, `unrecorded`, `break`, `hub`, `landlocked-centre`, `above-production`,
  `declaration`, `origin-unchecked`, `destination`, `fall` and `no-production`. The entries of `REGISTRY` are written by hand with their text; `landlocked-centre` (a large flow
  whose declared destination or origin is a landlocked trading centre) and `no-production` (check K14, an exporter with no production in the EIA table) are computed from the data, so a build without `raw/`
  keeps them (`keep_caveats` of `build_lanes.py`). Look for a pair that is most of a landlocked buyer's imports; the pair is left out of the generated corridors, its tonnes stay in the estimates of the passages.
- **Dropped origins** (`DROP` of `clean.py`): the exports of a country under a code for a product it cannot have made (Mozambique's coke) are left out by rule 5, listed in `LAST_DROPPED` and in
  `QA.md`; the page says how much was left out (`_left_out_note`, and the note of a table that holds under 97% of the file) and that the rows are not counted. Read the EIA series of every large exporter of a new group.
- **The river leg** (`pipeline/freight/river_legs.py`): a port of a flow's gateway farther than 50 km from the sea network needs a row; its note is one sentence and one link.
- **The port basis "page names the plant, not the cargo"** (an eighth element `"plant"` of a gateway row) for a steel works or a refinery of alumina; a country with two coasts needs a coast rule (`fra-grain-ports`
  is the rule of French grain: Rouen and La Pallice by partner, an Atlas assumption, with Fos for the Mediterranean side), and the Turkish scrap, pig iron and DRI have Iskenderun as principal and Izmir as the option.
- **Labels of cargo chips** (`cargoLabels` of the class pages; `web/src/lib/cargoChips.ts`): a lane or a route of one group of a page that has several groups carries the group's own name ("Urea",
  "Ammonia", "Ferro-chromium") and still opens the page; the group that stands for the whole page (coal of the two coal pages, the seed of "Rapeseed & canola": `WHOLE_PAGE`) keeps the page's name.
  Every page with a main lane typed in a class (the class that comes first in the lane's `vclass`) is among that class's `cargoes` (`test_fncg.py` G6): add the page to the class when a new group's lanes are typed in it.
- **The rows that keep their reported tonnage** (`KEEP_REPORTED` of `clean.py`, one reason for each row, and `ESTIMATE_RIGHT` of `test_fncb.py`, the rows that rule 3 or 4 re-estimates and
  that the estimate is right for; `test_fncb.py` B2 fails on a new row that is in neither): a reason names the other years of the pair and the unit values of the row.
- **Notes under many tables** (`web/src/lib/commodityTables.ts`, `coverText`): a note that stands under several tables of a page says which tables it covers by their kinds (exporters, importers, production), names the EU member
  states and the ending stocks, and never calls a further table a "kind"; `web/scripts/table-covers.test.mjs` reads every page.
- **The passage page** (`typeNotes` of `chokepoints.json`): the comparison with PortWatch's volume is written once on the passage; the notes of the estimates do not repeat it, and the tonnage a note and the page both
  print is the same figure (`web/scripts/chokepoint-notes.test.mjs`).
- **Search** (`COMMODITY_ALIASES`): the trade abbreviations a buyer writes ("FeCr", "FeMn", "SiMn", "FeSi", "FeMo", "AN") and both spellings of "fertiliser" on every fertiliser page; no alias that is a country code ("CAN") and no
  alias with a common word ("and") that other pages are found by. A whole word counts as a promotion only in an item's names, codes and cargo names, not in its ports or regions.

## 8. A pair or a year that another source corrects (since November 2026)
Three listed tables of the trade layer move a customs figure on the evidence of another free source; each is explicit, pair by pair, and each row says so in its note.
- **Tonnage replaced** (`us_lpg.CORRECTED`, cleaning rule 10): a pair-year whose customs tonnage is far above the volume of the exporter's own statistics (LPG, United States to Mexico; a volume read as tonnes is a plausible cause, never stated as established). Read the
  other source's series for every year first (`pipeline/trade/us_lpg.py`: its cache holds only what the page prints), correct only the years where the tonnage and
  the unit value both leave the range of the years before, and say in the page which years are corrected and which could not be checked. A pair checked and left
  alone (Canada) gets its note too.
- **Flow added** (`comtrade_tin.ADDED_FLOWS`, cleaning rule 11): a flow that the importer declares and the reconciled file lacks (tin concentrate, Myanmar to China). The
  row is flagged `added`, is not an estimate, carries the source's attribution in its note and moves with the mode rules (overland: no lane). A figure of UN
  Comtrade is printed in a few small tables only, with "Source: UN Comtrade"; its answers stay in raw/. Every place that carries the pair says what it is: bit 4 of `f` and the
  `added` list of the pairs file (the Route finder and the country pages read them), the lane file's year notes, the commodity page's notes (`_note_group`), and the checks
  read `clean.customs_frame` (the file as the customs source has it), never the frame with the added rows. A table whose total is not the world's carries `shareOf`.
- **Split known** (`modes.KNOWN_SPLIT`): a mixed pair-year whose share by sea a source measures. `modes.mode_of(o, d, group, year)` returns the share for that year;
  `build_lanes.split_known` cuts the row into a sea row and an overland row after the checks, in `build_lanes.py` and in `build_freight.frame()`, so that the lane, the
  seaborne totals, the passage estimates and the country pages read the share; the page's flow note says it (`modes.split_note`).
For a table of figures that another country's own statistics give beside the customs tables (the LNG page), keep the customs tables as they are, put the
cross-check in an extra table that the country profiles leave out (`build_profiles.NO_PROFILE`), and cite the edition and the attribution the publisher asks for.

## Traps met
- A product whose first customs group has most of its tonnage in a mixed code (scrap: HS 720449 holds three quarters of heading 7204) is shown as the whole code; say it in
  the notes instead of splitting it with a six-digit table the page cannot support for every year.
- Raising a size budget (`web/scripts/check-size.mjs`, the 3.9 MB of the series by year in `validate-data.mjs`) is part of the package: measure the data folder in bytes after your rebuild
  (the budget sums file sizes, `du -sk` counts blocks) and set each budget to that measure plus a fifth of the total, not of the increase (a review found that the budgets set with the metal bulks
  left 3 to 5% of room), rounded, with the measure in the comment.
- Wikipedia refuses the research client with a 429: write the class of a lane as an Atlas assumption, say no page was read. It answers again after a minute or two: one page at a time, slowly, and the API (`api.php`) stays refused, so read the pages themselves; the French pages (`fr.wikipedia.org`, CC BY-SA 4.0) are accepted as rows where the English one does not exist (Rouen, La Rochelle, Nantes-Saint-Nazaire).
- A country with two coasts needs a coast rule (`COAST_RULES` of `gateways/coasts.py`, kind `basin`: Canada, France, Turkey) and a row of its general-cargo ports on each coast, or every lane of the country loads or discharges at the first row (France: Fos for NW Europe, Turkey: Mersin for the Black Sea). A rule limited to some segments or groups leaves the others on the first row.
- A port more than 50 km from the coast and the sea network (a port up an estuary: Rouen, 53 km up the Seine) is snapped by the router to the
  nearest node, which can be on another stretch of coast, and every lane through it reads short and starts at sea. Give it a row in
  `RIVER_LEGS` of `pipeline/freight/river_legs.py` (the node of the network at the river's mouth, the length of the leg in km and the page that
  gives it, with its sentence; where no page read gives the length by river, `"measure": "straight"` and the straight line between the port and
  the mouth, which a test recomputes: Bremen): `routing.route()` then starts the route at the mouth, adds the leg to every distance and draws the first
  segment straight, and the lane, route and Route finder pages say so. `test_ports.py` fails for a port of a flow's gateway that is farther than 50 km and has no leg.
- A gateway row whose page names the plant that the port serves (a steel works, a refinery of alumina) and not the cargo takes an eighth element,
  `"plant"`: its basis reads "page names the plant, not the cargo" in both directions, and the source link stays. Read the note of every row you add:
  a row whose own note says the page names no cargo is such a row.
- Adding groups to `AUDIT_GROUPS` of `generated_routes.py` shares the cap of the first batch with the groups already there and leaves the new groups with the places that the published routes do not hold: use `LATER_GROUPS`, a cap of their own.
- `GROUPS_OF` in `build_freight.py` also sums the volumes of the hand-written routes: leave the new groups out of it.
- The "up to" figures of the chokepoint estimates of earlier groups move a little when a group is added (PortWatch caps are
  shared); this is expected, and so are the alert lists and the country profiles. Nothing else of an earlier group may move.
  The cap of the "up to" figure is by subtraction (PortWatch's volume less the "at least" tonnage of the other groups) only while the "at least" tonnage of the vessel type is at most 85% of
  PortWatch's volume (`PW_NEAR`); above that it is PortWatch's whole volume of the type, never below the group's own "at least"; and there is no cap where the type is above PortWatch's
  volume and an alert on the passage explains it (`cap_regime` in `build_freight.py`). A group added to a type that is near the volume can no longer empty the "up to" figures of
  the others, nor exceed its ship type, and `test_fncb.py` B1 lists the 599 estimates of the released site that must stay.
- An extra table key that does not end with `-exports`, `-imports`, `-production` is left out of the country pages.
- Rows below 1,000 t and 1 million USD are not in the cache; a table's world total is the cleaned cache, 2 to 10% from the
  archive's own sum for products with many small flows or missing tonnage (estimated from value, said in the note).
- The USGS year of the file is the edition year minus one: read the rows, not the title, before you name a year.
- A liquid or a chemical is not "fertiliser berth" cargo: a page that names fertilisers says nothing of an ammonia terminal.
- A new family member can use a port row written for another cargo of its family: the sunflower and rapeseed oils take the "vegoil" rows of
  palm and soybean oil (a Malaysian palm-oil terminal can be the port of a sunflower-oil import). Say so, or put the group in `OWN_FAMILY`.
- `figures_of()` leaves out closed series; a page whose only series is closed needs the exception (and `validate-data.mjs` the same), or it
  reads "No free price series" beside a series that exists.
- `data/commodities/index.json` is rewritten by the builder for `has` and `sub` only: new entries need `"has": []` and every `rank` of the
  list changes when a page is inserted in the middle.
