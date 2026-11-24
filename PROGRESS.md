# Commodity Flows Atlas: progress

_Last updated: 2026-11-24, after the sixth release of audit fixes_

Live site: https://nathancouturier.github.io/commodity-flows-atlas/

## Where the project stands

The atlas was built, reviewed with the owner (interface), then audited in full on 22 November 2026.
The audit lists 344 points: 144 corrections, 122 completions and 78 additions. They are being
fixed in waves, the most important and most visible first. Every package of work is implemented,
checked by its implementer, reviewed by an independent reviewer and corrected before it is
released. This file is updated at each release.

| Wave | Scope | Status |
|---|---|---|
| 1 | Visible defects of the site and quick data fixes | done, released on 22 November |
| 2 | Trade-flow engine: sea or land rule, lane selection, typical ports, routing, chokepoint shares, Route finder | done, released on 23 November |
| 3 | Wrong figures per commodity (gas, LNG, copper, precious metals, lithium, nickel, steel, fertilisers, cocoa) | corrections done, released on 23 November. Left for the next release, with the sources found and the files on disk: tin (China's declared imports from Myanmar), LPG from the United States to Mexico, pig iron production, a cross-check of LNG exports, metallurgical coal by pair |
| 4 | Data already downloaded and unused | done, released on 23 November in the third and fourth releases. Left: cocoa and coffee product tables (the customs groups exist now), proved oil and gas reserves and refining capacity (not in the EIA file on disk), metals history before 2024 |
| 5 | Hand-curated layers | infrastructure, events (23 November); Baltic benchmark routes, vessel classes, ports and terminals, companies (fifth release, 24 November). Left: a page per index, refineries, pipelines, fields and processing plants still a sample, a page per company |
| 6 | Additions | search, lists by kind, CSV downloads, copy link and citation (fourth release); two long freight indicators and the freight series under its own name (fifth release). 12 commodity pages and 29 customs groups with sea lanes from data on disk (sixth release). Left: freight rates in USD per tonne (no free source may be republished), traffic per port, a voyage calculator, forecasts, the other commodities the audit names (cement, petroleum coke, salt, wood, methanol, palm kernel and coconut oils, critical minerals) |
| all | Update jobs, validator, tests before publication, documentation | fifth release: no silent failure, a staleness check, one writer at a time, a before-and-after guard, the checks run before every publication, 1,077 unit tests; 1,403 unit tests and 50 web tests at the sixth release, which all pass without the raw downloads, as on GitHub. The checks ran on GitHub for the first time when the fifth release was pushed (all green, about three minutes, then build and deployment). The scheduled update jobs have not run in their new form yet: the first are PortWatch on Wednesday 25 November at 19:17 UTC and prices the same day at 21:43 UTC |

## Sixth release (24 November 2026): what changed

Twelve commodity pages and 29 customs groups with sea lanes were added from data already on disk (audit points
M-022, M-023 and A-010), in three packages. The work went through five rounds of independent review on frozen
copies of the tree (28, 37, 13, 11 and 13 findings; 23 of the 102 important), nine fix packages and one
correction by the orchestrator. Every finding was decided: corrected, or listed below as left for later. In the
last round one reviewer found that the river leg given to Bremen was shorter than the straight line it is drawn
as (corrected), and two reviewers on the release candidate (one on the last package, one on the whole site: every
commodity page, 30 country pages, 30 passages, 60 routes and 60 lanes, 173 links followed) found nothing
important.

### New commodities

- **Fertilisers and sulphur** (M-022). Ammonia, ammonium nitrate, ammonium nitrate with limestone, UAN and
  ammonium sulphate join urea on "Urea & nitrogen"; MAP, superphosphates and phosphoric acid join phosphate rock
  and DAP on "Phosphate"; potassium sulphate joins potash. Two pages are new: Sulphur (with USGS production) and
  NPK fertilisers (compounds with three and with two nutrients). Each product has its exporters, importers and
  lanes, and the largest have a generated route.
- **Grains, oilseeds and pulses** (M-023). Four pages are new: Barley, Sorghum, Sunflower (seed, oil and meal)
  and Pulses. Rapeseed gains its oil and meal; wheat gains flour and corn its distillers' dregs (trade tables
  only). Left from the audit point: palm kernel and coconut oils, malt, oats, and a barley price after 2020
  other than the World Bank's annual average.
- **Metal bulks** (A-010). Six pages are new: Ferrous scrap, Pig iron & DRI, Chromium, Ferro-alloys
  (ferro-chromium, ferro-manganese, silico-manganese, ferro-silicon and the others), Molybdenum and Graphite.
  Coke is a product of the Metallurgical coal page. Molybdenum, graphite and the "other ferro-alloys" have
  tables and flows on the map but no sea lanes yet.
- Largest new seaborne groups in 2024 (customs data, the atlas's sea-or-land rule): ferrous scrap 67.6 Mt, sulphur 42.5 Mt, barley 29.5 Mt, coke and semi-coke 24.4 Mt, chromium ore (chromite) 18.8 Mt, pulses 18.5 Mt, ammonium sulphate 18.4 Mt, ammonia 15.9 Mt.
- A commodity is now added by following `docs/ADDING_A_COMMODITY.md`, written from these three packages and
  corrected after each review round.

### Prices

- 154 series (138 before). Barley and sorghum, whose monthly World Bank series stopped in August 2020, are shown
  to that date and continued by the World Bank's annual average.
- Ten annual prices of the USGS Mineral Commodity Summaries, each named for what the file says it is (United
  States, annual, the file's own unit and source): chromite ore, ferro-chromium, 75% ferrosilicon, heavy
  melting scrap, molybdenum (molybdic oxide), three kinds of natural graphite, sulphur and ammonia. A page no
  longer says that no free price exists when one of these is its product.

### Ports and routes

- **France has two seaboards.** Until now every French pair used Fos or Le Havre. Grain, oilseeds and meal now
  load at Rouen or La Pallice: Rouen for the eleven countries its page names and for the Channel, the North Sea
  and the Baltic, La Pallice for the other partners outside the Mediterranean, Fos for the Mediterranean and
  the Black Sea. No source gives the split, so the rule is an Atlas assumption and both ports are shown as
  options with their distances (in 2024 the rule puts 12.3 Mt of cereals at Rouen, 2.5 Mt at La Pallice and
  0.9 Mt at Fos). Fertilisers and general cargo take Le Havre on the Atlantic side and Fos on the Mediterranean
  side; ammonia lands at Montoir. Of the 25,847 pairs of the fifth release, 286 changed port, distance or
  class, all with France at one end, and 16 more changed passages only; no other pair of the earlier groups
  moved.
- **River legs.** A port far up a river gets the river added to its sea distance and days: Rouen (65 nm of the
  Seine, from the page of the port) and Bremen (30 nm, the straight line to Bremerhaven, an Atlas measure
  because no page read gives the river distance). The leg is drawn as one straight segment and the lane page
  says so.
- **A new port basis**, "page names the plant, not the cargo", for ports whose page names a steel works, a
  refinery or an alumina plant and not the cargo handled: the two Turkish steel-works ports, Vila do Conde for
  alumina and five refinery ports for the loading of refined products (Pengerang, Port Dickson, Mumbai, Vadinar,
  Siracha).
- **Turkey**: scrap, pig iron and direct-reduced iron use the ports of the two steel works a page names (Eregli
  for the Black Sea partners, Iskenderun for the others, with Izmir as an option).
- **Declarations by trading centres.** A pair that is most of a landlocked buyer's imports (sulphur from Qatar
  to Switzerland, 1.13 Mt; refined copper from Zambia to Switzerland; iron ore between Malaysia and
  Switzerland) carries a caveat that the cargo probably ends elsewhere, and no generated route is named after
  it.
- **Generated routes**: 168 (120 before). The earlier groups keep their own cap, raised from 120 to 122 so
  that the routes of the fifth release stay; the new groups have caps of their own (20, 10, 10 and 6). Of the
  253 routes of the fifth release, 251 keep their address; two ended with the French ports
  (`gen-steel-med-nw-europe`, `gen-wheat-med-waf`: their addresses open a page that says so, with a way back)
  and nine changed content. 301 routes in all; named routes cover 65.0% of seaborne tonnes.

### Figures and cleaning rules

- Mozambique's "coke" (1.63 Mt in 2024, mostly to India) is left out of the coke tables, lanes, passage
  estimates and history: the EIA series gives the country no coke production in any year since 1980 and
  6.5 Mt of metallurgical coal exports in 2025. The page says what was left out and why. Zimbabwe's (0.9 Mt)
  is kept, with a note that customs data and the EIA series disagree and that neither reading is established.
- A table that holds less than 97% of the customs file says so and names the cause (unwrought zinc: one row,
  Spain to Mexico, declared at 5 Mt for USD 61 million).
- Rows whose own price level explains a low or high unit value keep their reported tonnage (a reviewed list,
  each row with its reason); sunflower seed for sowing keeps its tonnage above the reference price only.
- Notes computed from the data, each marked "a possible reading, not established here": Mozambique's imports
  of chromium ore and ferro-chromium (transit from South Africa), Djibouti's imports of compound fertilisers
  (cargo for Ethiopia).

### Passage estimates

- 967 estimates at 20 passages (599 before). The comparison with IMF PortWatch is printed once per ship type
  above the list, no longer under every row (the file weighs 729 kB; it had grown to 883 kB).
- The cap of an "up to" figure now has three cases: where the atlas's "at least" tonnage of a ship type is at
  most 85% of PortWatch's volume, the cap is that volume less the other groups (as before); above 85%, the
  whole volume of the ship type; and where the atlas's tonnage exceeds PortWatch's volume and an alert explains
  it (the Red Sea), no cap, because the figures are tonnages of the normal route.
- Of the 599 estimates of the fifth release, 42 "at least" figures moved (the French ports: Gibraltar,
  Dover, the Danish Straits) and 89 "up to" figures (the new cap, and the new groups counted before it).
  The largest: Makassar iron ore up to 1,085 Mt (896), Hormuz crude oil up to 751 Mt or 40.1% (601 Mt, 32.1%),
  Panama crude oil up to 43.8 Mt (7.3), and Suez and Bab el-Mandeb, whose "up to" figures are printed again
  (crude oil at Bab el-Mandeb up to 223 Mt).

### Pages and search

- A cargo chip names the product when its page holds several (a route of ammonia reads "Ammonia", not "Urea &
  nitrogen"); vessel class pages list every commodity typed in the class.
- Search: trade names and abbreviations (DRI, HMS, FeCr, SiMn, AN, UAN, MAP, SOP, canola oil, sulfur and
  sulphur); a whole word in a name ranks before the beginning of another word; "fertiliser" and "fertilizer"
  give the five fertiliser pages in the order of the tonnage traded.
- The page of an address that does not exist offers a way back (routes, lanes, commodities, passages, vessel
  classes). The price window is kept when switching between nominal and real prices. A share that rounds to
  nothing reads "<0.1%", not "0.0%". Country pages say what the percentage after a port is: an allocation by
  the atlas's rules, not a count of what the port handles.

### Checks

- 1,403 unit tests (1,077 at the fifth release) and 50 web tests (9); the whole suite passes on a copy
  without the raw downloads, as on GitHub. Five browser suites pass on the production build, and the checks of
  GitHub were reproduced on a fresh clone before the push.
- Two slips of the source scouts of the next round, to know about: one request was sent to an address of
  worldsteel after its robots file had been read as disallowing everything (only a login redirect came back),
  and two PDF reports of the EIA were read under a path its robots file disallows (their figures are not
  used). The rule is in every brief: a disallowed path is not read, even once.

## Fifth release (24 November 2026): what changed

Six packages, six independent reviews (65 findings, 22 of them important), six fix packages and one more for a
source whose terms forbid its use, then a rebuild of everything together and a review of the site on the
production build (10 findings, three of them important: an internal remark shown in the Sources window, the
largest class of three ports, pages that had grown too long; all corrected, then checked by a second reviewer,
whose five remaining minor points were corrected before publication).

### Baltic benchmark routes

- 90 benchmark routes (60 before), each compared with the Baltic Exchange's Guide to Market Benchmarks (version
  7.09) and its circulars: 85 active, 5 ended. The ports of 14 routes were wrong and are corrected; 30 routes were
  missing, among them the two grain routes, all the Supramax routes of the time-charter average, the 182,000 dwt
  Capesize routes and four routes in service since January 2026.
- Each benchmark page has a definition table (vessel, cargo and quantity, load and discharge, duration, index and
  weight, status with its date and document). An ended route says when it ended and links to its successor.
- A definition says only what its document says: for 19 dirty-tanker routes the document gives a tonnage and no
  cargo, and the page says so; crude oil is the atlas's reading.
- Port names that were resolved to the wrong place are corrected and no line crosses land where one did (TD6
  across the Corinth isthmus). A line still starts at a node of the sea-lane network, up to about 90 km from
  its port.
- 253 routes in all: 90 benchmarks, 43 other routes written by hand, 120 generated corridors (their ids did not
  change). 207 have a corridor share and 213 a history; named routes cover 66.2% of seaborne tonnes.

### Vessel classes

- 20 classes (a chemical tanker class for vegetable oils). 14 have a standard vessel with its source and year:
  four dry classes from the Baltic Exchange's dry page, nine tanker and gas classes from the guide, one from
  Wikipedia. Speed and fuel a day, laden and in ballast, where the document gives them.
- A "World fleet" block per class: ships, deadweight and average age of the ship type (UNCTADstat, CC BY 3.0
  IGO), with the sentence that the fleet of a commercial class is not published for free.
- Size bands of a segment no longer overlap or leave a hole; every size has a page or is marked as an Atlas
  convention. Wherever a lane or a non-benchmark route shows a class, it says "typical".

### Ports, terminals, storage

- 190 ports (36 before) and a new type, storage hub (Cushing, Mont Belvieu). 172 of the 214 ports named by the
  routes are assets and can be clicked from the route page; most of the others open the largest lane through
  them, and a few stay plain text.
- 20 ports have published limits; 9 of them have a "largest class", derived by the atlas only when the page
  gives a dimension of a ship (never from a depth alone), and labelled as a derivation. It never contradicts the
  limit printed above it: where deadweight and draught point to different classes, both are shown.
- A commodity tag on a port rests on a page or on the atlas's own routes and lanes; 8 ports whose cargo no page
  supported were removed.

### Companies

- 403 entries for 269 companies (247 entries before), 88 with a dated figure read on the company's own report
  or filing (3 before), 357 with ownership; the year shown is the year of the fact and the month of reading is
  apart. 32 shipping companies on the class pages. No superlative without a figure; a sanction only from an
  official notice read, with its date.
- Companies are in the search. A company links to the assets it operates.

### Freight indicators

- The US series is named for what it is (a producer price index of the BLS, not a freight rate) and is fetched
  from the BLS, without a key. Two long indicators were added, each labelled "not a freight rate": the Dallas Fed
  index of global real economic activity (monthly since 1968) and the New York Fed Global Supply Chain Pressure
  Index (since 1998).
- No ocean freight rate in USD per tonne is stored: each USDA dataset credits a private firm and carries no
  licence. The four grain routes link to them. Every route page says that Baltic values are proprietary.

### Update jobs and checks

- A step that times out, crashes or is cancelled is recorded as a failure; a weekly check opens an issue for a
  source that went stale without failing; the three jobs can no longer overwrite each other's status; a refused
  push, a discarded update and a site that was not republished each open one issue.
- A guard compares each update with the last commit (a price ten times too large, a table that lost a tenth of
  its rows); replayed over 69,629 real updates it refuses five.
- The checks (type check, tests, validators, build and size) run before every publication. They do not run on a
  push to a working branch, and Dependabot pull requests are switched off, so that no e-mail is sent for work in
  progress.

## Fourth release (23 November 2026): what changed

Seven packages, seven independent reviews (85 findings, 29 of them important), seven fix packages, then a package
that put the commodity page back in order, a review of the data as a whole (two important findings, both fixed),
a review of the site on the production build (13 findings, two of them important: country pages far too tall on
a desktop, a search that accepted unrelated words; all corrected) and a second reviewer who checked those
corrections on the final build.

### Country pages

- A page for each of the 239 countries and territories of the index and one for the European Union, built from
  the full tables: every line a country has in any table, with its rank, its share and its series by year. One
  file per country, loaded when the page opens; 224 pages have figures, 16 say that no table names the country.
- Two figures that say what they are: the largest export of all goods (from an extract of the CEPII BACI archive at
  four-digit headings) and the largest raw-material export among the atlas's commodities.
- Net position, first three customers and suppliers and a concentration index per commodity; imports over
  consumption where a published consumption figure of the same unit and year exists.
- A freight block: tonnes by mode, typical ports with their basis, and the share of the country's seaborne trade
  that has to cross each passage, capped as the chokepoint pages are.
- The ten largest exports and imports of all goods. Heading names come from the six-digit descriptions of the
  CEPII BACI product list (the official heading texts of UN Comtrade may not be redistributed).
- The European Union has a page that lists its members, and each member links to it.

### Commodity pages

- **One order for every commodity.** Key figures, price and alerts; the core tables, open (production,
  consumption, exports, imports, reserves); main flows and seaborne lanes; then every other block folded to one
  line. A default page is now 0.60 to 0.89 times as tall as in the third release (ten pages measured by the
  release reviewer: copper 0.60, LNG 0.61, crude oil 0.64, sugar 0.68, cocoa 0.71, wheat and lithium 0.73, steel
  0.78, tin 0.84, LPG 0.89).
- **Energy.** Monthly crude production by producer to mid-2026 with the lowest month of 2026 against the 2025
  average, OECD imports by origin, petroleum stocks with days of cover, oil demand by month, from the EIA file. A
  month without a figure in the file is shown as "no figure", never as zero. LPG consumption includes the United
  States, converted from EIA's own series in barrels per day and labelled "Atlas conversion" wherever it is
  printed.
- **Agriculture.** USDA's 2026/27 forecast beside its 2025/26 estimate, with the month of the report; a balance
  per crop (area, yield, stocks, stocks-to-use, world excluding China); production of the 27 EU member states
  (FAOSTAT) and their customs trade split inside and outside the EU; a gap note for Russian grain that separates
  what customs data record from what the atlas estimated.
- **Metals.** Apparent consumption of refined copper, primary aluminium and crude steel (Atlas estimates, shown
  without ranks, with the large importers that have no production line named in the note); the two USGS years
  side by side; customs value and unit value; concentration figures; United States net import reliance (USGS).
- **Lanes for eight more customs groups**: lead concentrate, unwrought lead, unwrought zinc, tin metal and ore,
  cobalt, lithium, rare earths. Groups under 1 Mt a year are shown in kt everywhere. Gold, silver and
  platinum-group metals are not drawn (they move mostly by air) and the map says so.

### Engine

- 42 customs groups, 2,617 main lanes, 35 mixed, 271 history-only; 25,847 recorded pairs; main lanes carry 85.5%
  of the 7,923 Mt of 2024 seaborne trade.
- Transit rows follow their page cargo by cargo and buyer by buyer (Kazakh coal through Ust-Luga for Morocco and
  the EU only; Paraguayan soybeans and corn through Nueva Palmira, meal and oil through Rosario). No lane is drawn
  from the wrong coast of a country for the new groups. Seaborne tonnage not routed: 48.5 Mt (64.2 Mt before).
- One cleaning rule for lithium rows declared at the price of an ore, read by every file.
- 120 Atlas corridors chosen by tonnes: named routes cover 66.0% of seaborne tonnes (59.9% in the third release).
- One module holds every physical constant with the page read that gives it.

### Search, downloads, events

- A search field in the top bar (a button on a phone) over commodities, countries, routes, chokepoints, vessel
  classes, assets, ports, events and price series, with lists by kind that work from the keyboard.
- CSV downloads on tables, flows, price selections, chokepoint series and monthly series, each row with its
  source and licence; no download where the terms of a source are not confirmed (the uranium table of the World
  Nuclear Association). Copy link and Copy citation on every page; the Prices selection is in the address.
- 80 events (33 added: agricultural export restrictions, energy episodes, metals trade measures, freight
  milestones), every text read against the pages it cites; an events section per page; an alert can point to
  several events.

## Third release (23 November 2026): what changed

Every package below was implemented, reviewed by an independent reviewer who recomputed its figures from the raw
files, corrected, and rebuilt. The six reviews produced 71 findings, 27 of them important. They were fixed before the
release, except one that is outside this wave (event texts that their cited page does not support) and a few fixed
in part, all listed under "Known limits".

### Tables and history (wave 4)

- **Every country in every table.** A table shows its first 10 rows, a line "Rest of world" (with the number of
  countries it holds) so that the shares add up to 100%, the USGS "Other countries" line where the source has one,
  and "Show all (N)". The map colours every country that has a value. The 20 stored flows can all be shown.
- **History by country and year.** 38 history files hold the series behind the tables: CEPII BACI exports and
  imports 2005 to 2024, EIA annual series, USDA marketing years 2005/06 onwards, and the two years of the USGS file.
  With a History year, tables and country colours show that year where a series exists and say so where none does
  ("2025: no series for 2010"). Each row has a trend line; each table has the world total by year.
- **Rules that keep the series honest.** A year without a figure is never read as zero. The USDA "European Union"
  row is labelled for what it holds each year (with the United Kingdom up to 2015/16) and its trend line breaks at
  the change. A figure far out of line with the years around it is shown in the note with its source and is not
  ranked (four values, among them United States LPG consumption of 2021: 148 Mt against 43 Mt the year before).
  Caveats stay on a past year. The spodumene estimate starts in 2021, as its lanes do.
- **Largest changes.** A block per commodity with the five largest increases and decreases of exporters and
  importers between two years, and a sortable "Change" column in the lane table.

### Prices (wave 4)

- 136 series instead of 45: 13 more World Bank columns, 16 World Bank price indices, 46 annual real-price series
  (constant 2010 dollars, the World Bank's own deflator) behind a "Real prices" switch, 14 annual USGS prices
  (lithium, manganese, rare earths, bauxite, alumina, cobalt, palladium, rhodium), iron ore split into its spot
  series (from 2006) and the earlier annual contract prices.
- What each price measures, and the dates its basis changed, are read from the source's own description sheet and
  drawn on the chart. Years of twelve identical values, gaps in daily series and the source's own estimates are
  marked. No basis note holds a remark that the source does not make.
- A price board (last value, changes over 1 week, 1 month, 3 months, year to date and 1 year, position in the
  52-week range), the latest price on each commodity page, 14 spreads and ratios.
- A unit test proves every series against its raw file by header text.
- The weekly job runs after the EIA release (Wednesday evening, retry on Thursday), refuses a workbook whose
  columns changed, records a late series, and closes a series the publisher stopped without raising an alert for
  ever.

### Freight (wave 4)

- **120 Atlas corridors** generated from the table of recorded pairs, beside the 103 hand-written routes: named
  routes now cover 59.9% of the 2024 seaborne tonnes (45.1% before). Steel, manganese, alumina, sugar, rice and
  rapeseed have routes. A generated route takes ports, class, distance and passages from its largest pair, so the
  route page and the Route finder agree; it is drawn thinner, has its legend entry and never carries a benchmark
  code. Coverage per group is written to `pipeline/freight/QA_routes.md` at each build.
- **Chokepoint status board**: every passage with its transits and estimated tonnes over the last 28 days against
  its 2023 average (opened from any chokepoint page). A CSV of every flow that crosses a passage.
- Route pages say what the Route finder gives for the same corridor; the two stand-in Capesize traces say that
  their distance is not theirs.

### Alerts and events (wave 4)

- **Alert banners follow the data.** Severity comes from IMF PortWatch (28-day transits against the 2023 average:
  high from 60% below, medium from 25% below). Commodities and countries come from the chokepoint estimates and the
  pairs tables, with a stated addition where customs data cannot name a country (Iran, Yemen). On a commodity page
  the banner gives the share of that commodity's seaborne trade through the passage. Banners are compact; the
  detail is behind "Details".
- **Texts checked against their source.** The three alert texts and the three events they point to were read
  against the pages they cite on 23 November 2026 and rewritten where the page did not support them; a text that
  was not checked carries no date.
- **Events are linked** to commodities, countries and assets by a tested rule, listed in an "Events" section on
  commodity, country and route pages, and filtered on the timeline by the chosen commodity (general shipping events
  always stay). An event page shows the price of its commodities one and three months later.
- **PortWatch update**: only the days after the last one stored are downloaded; the daily table is a working file
  kept outside the repository. The About window has "What changed" (with an Atom feed), the freshness of each data
  family and the publication calendar of the sources.

### Infrastructure (wave 5)

- 207 assets added, 501 in all: 35 refineries, 12 fields, 28 LNG import terminals, 1 LNG export plant, 2 pipelines,
  104 mines and 25 smelters. Each figure was read on a page and re-read by a reviewer; most mines and smelters come
  from the USGS Minerals Yearbook country reports (public domain).
- 251 operating, 6 damaged, 6 suspended, 238 "not stated" (no page read says whether the asset runs).
- The trade engine reads the new LNG terminals: six countries have a sourced LNG discharge port.
- The lists of the notices that follow the data (assets adapted from Wikipedia, articles cited, points taken from
  OpenStreetMap) are generated by `pipeline/common/notice_lists.py` and checked by a test.

## Second release (23 November 2026): what changed

### Trade-flow engine (wave 2)

- **Sea, land or both.** One rule decides the mode of every recorded pair, by cargo family: sea,
  sea through a sourced port of another country (landlocked ends), mixed sea and overland (the
  split is not known: Russia to China crude and coal, for example), or overland. Mixed pairs are
  drawn dashed and stay out of seaborne totals and chokepoint shares.
- **Lanes chosen from the latest year.** 2,400 main seaborne lanes (1,334 before), 35 mixed lanes
  and 182 history-only lanes, in 34 customs groups. Main lanes carry 85.4% of the 2024 seaborne
  tonnes (63.4% before); the rest is listed per exporter as "Other destinations".
- **A table of every recorded pair.** 23,853 pairs of 2024 with mode, ports, class, distance and
  passages. The Route finder answers for any of them and says plainly when a flow is overland,
  mixed, not routed or not recorded; it can start from the destination and keeps its question in
  the link.
- **Typical ports with their basis.** Ports are given per cargo family, role and coast, each with
  the basis the reader can see: 69.7% of the pair-end tonnage rests on a page that names the cargo
  at the port, 22.4% still on the port used before with no page read ("no source page yet"), the
  rest on a general port of the country or the nearest seaport. Wrong ports were replaced (food no
  longer lands at oil terminals; Libyan crude at Ras Lanuf, Indonesian coal at Tanjung Bara,
  Mozambican coal at Beira and Nacala, United States imports at the ports of entry of the EIA file).
- **Routing.** Passages after the antimeridian are detected; draught limits apply by class; no
  routing along 50 S; Cape Horn only for the South Pacific; the Johor and Kanmon straits are closed
  to through routing. Parallel passages (Sunda, Malacca with Singapore, Lombok with Makassar;
  Taiwan Strait, Luzon) are shown as "One of"; 29 lanes whose main port option avoids such a group
  print "May also cross" for the option that does not.
- **Chokepoint shares as "at least" and "up to"**, over every recorded pair and every group (490
  estimates on 20 of the 30 chokepoint pages, 77 before), capped by IMF PortWatch volume where it
  applies, with a note where the atlas figure exceeds the traffic PortWatch counted that year. An
  estimate is kept when the figure the page prints reaches 2% of the seaborne trade or 1 Mt.
  Hormuz crude reads at least 27.2%, up to 32.1% (21.2% before); refined products 20.7% (2.4%
  before).
- **Customs data.** Iranian crude moved out of "Other Asia"; duplicated Qatari LPG rows dropped;
  isolated unit-value anomalies of bulk cargoes re-estimated from the declared value and labelled
  "Atlas estimate" (bauxite from Guinea to China in 2023, for example); twelve checks against EIA,
  USGS and USDA written to the QA file; caveats for origins that customs data record badly, worded
  as hypotheses.
- **Site.** Lane page with ports, sources, coast options, passages and alternatives; sortable lane
  table with CSV download; Suppliers and Customers tables on country pages; estimates printed
  with two significant digits and their mark.

### Commodity pages (wave 3)

- Natural gas is ranked on EIA volumes in bcm, no longer on customs tonnes.
- LNG shows the GIIGNL world total beside the customs total; LNG tables carry no world rank.
- Crude oil, gas and LNG key figures carry a second unit, labelled "Atlas conversion" with its
  factor.
- Chilean copper concentrate, declared in contained copper in some years, is re-estimated at
  Peru's unit value times the median ratio of Chile's own unit value to Peru's in its regular
  years: Chile is the first exporter (12.4 Mt in the file, printed "12 Mt, Atlas estimate")
  instead of the second.
- Gold, silver and PGM are shown in fine-metal equivalent (declared value over the annual average
  price), with the customs gross weight beside it.
- Lithium has a spodumene table (Australia, Zimbabwe, Brazil to China, Atlas estimate) and lanes;
  nickel has a ferro-nickel table and lanes, and laterite ore is no longer flagged as a misreport.
- Steel and gold tables keep the USGS "Other countries" line; cobalt is no longer labelled ore;
  bauxite and tin state their known gaps; urea production is in product tonnes (FAOSTAT) and
  potash production is converted to the unit of its trade; cocoa cites the ICCO total beside
  FAOSTAT; coffee, cocoa and cotton are in Mt everywhere.
- 17 USGS tables whose country lines sum above the published world total (rounding, or a total
  the publisher rounds down) compute their shares on the sum of the lines; the published total
  stays printed.

### Infrastructure layer (first part of wave 5)

- 294 assets on a new schema: nameplate capacity apart from dated production, exports or
  throughput, each figure with its own year ("year not stated" when the source gives none); the
  month a page was read is never shown as the year of a figure.
- A status on every asset: 212 operating, 6 damaged, 5 suspended, 71 "not stated" (no page read
  says whether the asset runs: nothing is assumed).
- Corrected at their source: seven United States refineries (EIA Refinery Capacity Report), three
  Kuwaiti refineries, LNG plants and their phases, twelve LNG export plants added, Druzhba and
  Keystone redrawn, several coordinates, operators and commodity tags.
- History mode dims an asset that was not yet open in the selected year (it stays drawn).
- A validator for the layer and its documentation in `pipeline/infrastructure/README.md`.

## First release (22 November 2026)

Price explorer (date lookup inside a month, no Brent fallback, three series); History (events to
2026, one lane width scale per commodity, pages follow the year); links, tab titles and keyboard;
About window with sources and licences; phone and tablet layouts; chokepoint pages for the 28
IMF PortWatch passages with vessels and tonnes; class shares only where their basis holds; "all
coal" wording; licence files (MIT for code, CC BY 4.0 for the atlas's own figures).

## What the atlas contains today

- **Freight (the core)**
  - 20 vessel classes (dry bulk, tankers, gas carriers, and one container class for the bagged and
    boxed cargoes), 14 with a standard vessel, each with the world fleet of its ship type.
  - 301 routes: 90 Baltic benchmarks (85 active, 5 ended) with their definition, 43 heavy
    non-benchmark routes written by hand and 168 Atlas corridors generated from customs pairs. 255 have
    a corridor share of seaborne trade and 261 a 2005 to 2024 volume history; the others say why.
  - 71 customs groups with seaborne lanes on real sea routes: 3,734 main lanes, 58 mixed lanes,
    572 history-only lanes; a table of 36,071 recorded pairs (25,922 by sea, 2,725 through a transit
    port, 109 mixed, 7,315 overland). Two ports up a river (Rouen, Bremen) carry a river leg.
  - A route finder for every recorded pair.
  - 30 chokepoint pages: the 28 passages counted by IMF PortWatch (weekly series since 2019,
    vessels and estimated cargo tonnes), plus the Singapore Strait and Cape Horn; 20 of them carry
    Atlas estimates of the cargo that has to cross or may cross (967 estimates), compared with
    IMF PortWatch's volume once per ship type; a status board of all passages.
  - 80 disruption events from 2008 to 2026, each text read against the pages it cites, linked to
    commodities, countries and assets, and three alert banners whose severity and lists follow the
    data.
  - 32 shipping companies by segment.
- **51 commodities**: production and reserves (USGS, EIA), agriculture (USDA PSD, FAOSTAT), trade
  and flows (CEPII BACI 2024), every country in every table, series by country and year, monthly
  energy series, crop balances, metals consumption estimates, 403 company entries (88 with a dated figure).
  Energy (7): Crude oil, Refined products, LNG, Natural gas, LPG, Thermal coal, Uranium.
  Metals and minerals (23): Iron ore, Metallurgical coal, Steel, Ferrous scrap, Pig iron & DRI, Copper,
  Aluminium, Bauxite & alumina, Nickel, Zinc, Lead, Tin, Lithium, Cobalt, Rare earths, Manganese, Chromium,
  Ferro-alloys, Molybdenum, Graphite, Gold, Silver, Platinum group metals.
  Agriculture and fertilisers (21): Wheat, Corn, Barley, Sorghum, Soybeans, Soybean meal, Soybean oil, Rice,
  Pulses, Sugar, Coffee, Cocoa, Cotton, Palm oil, Sunflower, Rapeseed & canola, Potash, Phosphate, Urea &
  nitrogen, Sulphur, NPK fertilisers.
- **657 infrastructure assets**: 190 ports, 175 mines, 108 LNG terminals, 68 refineries, 44 smelters,
  39 fields, 31 pipelines, 2 storage hubs.
- **Country pages** for 239 countries and territories and for the European Union (227 with figures).
- **Prices**: 154 series (World Bank monthly since 1960, annual averages and annual real prices, World
  Bank price indices, EIA daily, USGS annual, three freight indicators), a price board, lookup by date.
- **Search** over every kind of page, companies included, with trade names and abbreviations; CSV
  downloads with source and licence on each row, copy link and copy citation.
- **History**: a 2005 to 2024 timeline of flows, with events to 2026.
- **55 registered third-party sources**, every one free to read, plus the atlas's own entry for its
  estimates and conversions.

## Decisions of the owner

- Interface: all layers and all infrastructure types on by default; every asset drawn at every
  zoom, icons may overlap; Freight under "Routes by vessel class"; Controls and Legend open on
  load, each behind a button that stays in its corner; clicking a country isolates it; compact
  layout; no attribution box on the map (credits are in the About window).
- 22 November 2026: Wikipedia is an accepted source for now. When truly no free source gives a
  figure, the atlas may publish its own estimate, labelled "Atlas estimate" with its method.
  Code under MIT; the atlas's own derived figures under CC BY 4.0.
- Three visual style proposals were sent as images; the site style is unchanged until one is chosen.
- 24 November 2026:
  - **Baltic Exchange.** The facts are kept as they are (route definitions, index weights, status and standard
    vessels stated in the atlas's own words, each with a link, no index value), with attribution and without
    asking the Baltic Exchange for written consent. The owner was told that the site and the repository are
    public today.
  - **Alerts.** Issues are enabled on the repository and the owner watches it, so a failing update reaches him
    as an issue.
  - **BLS.** The owner opened the BLS copyright page in a browser and reports "Public Domain: Citation
    Requested", the terms the registry already quoted from FRED's page of the series. A free BLS key is created
    only if the keyless quota fails on GitHub (known after the first scheduled run).
  - **SEC EDGAR.** The owner accepts that a contact address is sent to the SEC, and to nobody else, when its
    filings are read. He set it himself as an environment variable (`SEC_CONTACT_EMAIL`) that the reading
    script takes its `User-Agent` from; the address is written in no file of the repository. The company
    entries without a figure will be read on sec.gov under these rules in a later round.
  - **Pace.** Several packages may run at the same time.
  - **Lines under the charts.** "Drag to zoom · double-click to reset" and the like stay under the charts of the
    passage pages and of the price drawer: the rule against hint text does not cover them.
  - The owner downloaded by hand and handed over four files that the machine could not fetch: Queensland's coal
    sales and coal production workbooks, the historical tables of Australia's Resources and Energy Quarterly
    (all CC BY 4.0) and the World Port Index of the US National Geospatial-Intelligence Agency (public domain).
    They feed the next rounds (metallurgical coal by pair, port limits).

## Choices made without the owner, to confirm

These were needed to finish the work; each is reversible.

1. Publishers whose tables are free to read but not free to copy (GIIGNL, IGU, worldsteel, World
   Gold Council, ICCO): one headline figure each is cited with publisher, year and link; no table
   is copied.
2. A refinery named by the EIA or by Wikipedia at a coastal place counts as a page for the crude
   discharge port of that country (South Korea, Japan, the Netherlands, Spain, Italy, Indonesia,
   Malaysia, Thailand).
3. Saudi crude: Yanbu, on the Red Sea, is a load option only for buyers reached westbound (Europe,
   the Mediterranean, the Atlantic side of the Americas), from the EIA country brief (a record
   18% of Saudi seaborne crude exports loaded at Yanbu in 2024). Hormuz crude therefore reads "at
   least 27.2%".
4. A passage is "may cross" only inside the listed groups of parallel passages, when only some
   port options cross it, and at the Korea Strait (south of Japan is a real choice). Elsewhere the
   shortest route under the class limits counts; the pages of Lombok, Makassar, Dover, Singapore,
   Ombai and Luzon name the route of similar length that is not counted.
5. Infrastructure: "operating" needs a page that describes the asset as running; otherwise the
   status is "not stated". In History mode an asset not yet open is dimmed, not hidden.
6. A few coordinates come from OpenStreetMap (attribution in the notices); the terms of the
   Norwegian Offshore Directorate could not be read and are recorded as "terms not read".
7. Smaller rules set during the last review, each one line to change:
   - a USGS table computes its shares on the sum of its lines only when that sum exceeds the
     published world total by more than 0.05%;
   - the floor of a chokepoint estimate (2% or 1 Mt) is tested on the figure printed after the
     PortWatch cap, which drops four small entries (soybeans at Suez and Bab el-Mandeb, soybean
     meal at Bab el-Mandeb, palm oil at Torres);
   - the container class is given a band of 0 to 24,000 TEU and a typical ship of 12,000 TEU, an
     Atlas convention (no free source gives a typical size per cargo);
   - the spodumene load ports cite a company filing (Bunbury) and trade-press pages (Esperance,
     Port Hedland, Vitoria); Beira, for Zimbabwe, is the general port of the country;
   - when the freight step of the annual job fails after a new CEPII BACI file was installed, the
     old cache is restored and the next monthly run downloads the file again (2.4 GB).
8. Third release, each reversible:
   - Generated corridors: at most 120, 12 per customs group, aiming at 70% of each group's seaborne tonnes; an end
     is named after a country when it carries 80% of the tonnes of that end.
   - Alerts: severity against the 2023 average of IMF PortWatch (high from 60% below, medium from 25% below); a
     commodity is listed from a 10% share or 50 Mt through the passage, a country from 15% of one commodity or 20 Mt
     of cargo; Iran (Hormuz) and Yemen (Red Sea) are added by hand with the reason shown. No GitHub issue is opened
     when a threshold is crossed.
   - The daily IMF PortWatch table is a working file of the weekly job, kept for 90 days as a workflow artifact and
     not in the repository (a signed-in GitHub user can download an artifact of a public repository; NOTICE.md says
     so). The alternative is to download the whole table every week, as before.
   - History: a figure far out of line with both neighbouring years is not ranked and is quoted in the note; in
     that year the shares are computed on the world total without it.
   - Prices: the two remarks that no page of the source supports (Brent before the mid-1980s, Japanese LNG
     indexation) were removed; cobalt opens on the United States spot price of the USGS; a series the publisher
     stopped is closed without an alert; overlapping dates in the source's description (Richards Bay coal) are
     quoted, not resolved.
   - Infrastructure: capacities of the USGS Minerals Yearbook are labelled "basis not stated" (the reports do not
     say whether a figure is the facility's total or an owner's share) and are ranked apart; an LNG terminal listed
     in the GIIGNL annual report is "operating" at the date of the report; two floating terminals at Port Qasim are
     drawn about 1 km apart because no page gives their positions.
   - Gold, silver and platinum-group metals move mostly by air: no air arc is drawn. Russian wheat, which customs
     data understate, gets a gap note and no fitted estimate. Every freight route stays drawn when a commodity is
     chosen.
9. Fourth release, each reversible:
   - Constants (densities, energy contents, conversion factors) live in one module, each with the page read that
     gives it. One has no page yet: 111.2 km per degree of latitude, used to measure distances.
   - Belarusian potash to China is counted as seaborne with a caveat that part of it moves by rail. A pair whose
     port no page supports is "not routed" and is not drawn (Kazakh coal to Turkey and India, 3.7 Mt).
   - A lane of the boxed cargoes and of lead concentrate may not leave from the wrong coast of a country: a pair is
     not routed when its sea route is more than 1.8 times the straight distance between its two ports, the port of
     one end has no page that names the cargo, and another port of that country reaches the other end in under 60%
     of the distance (or the port is only the country's nearest seaport).
   - Generated corridors are ranked by tonnes after each group named in the audit has its first one. Aluminium,
     refined copper, zinc concentrate, nickel intermediates and the minor metals have no generated corridor
     under the cap of 120.
   - A member state of the European Union keeps USDA's figure for the EU on agricultural trade maps (USDA does not
     publish the members); the EU page and the member tables come from FAOSTAT and customs data.
   - A month missing in the EIA import series is shown as "no figure", not as zero. The fall of Kuwaiti crude
     output in 2026 is a note on the series, not an event.
   - LPG consumption: the United States is added by converting EIA's series (barrels per day) with the density of
     propane; the world total moves from 304 to 348 Mt and every figure that includes the conversion says so.
   - A lithium customs row declared under 1,500 USD per tonne is an ore, not a chemical, and is left out of the
     lithium tables, flows and history (this also removes Canada to China in 2018).
   - Stocks-to-use is ending stocks over domestic consumption plus exports; USDA's words "estimate" and
     "forecast" are used instead of its abbreviations.
   - Heading names of the all-goods tables are derived from the six-digit descriptions of the CEPII BACI product
     list; the official texts are not redistributed.
   - Page order: consumption before exports on every commodity page, the lanes table open, no "Key
     infrastructure" block when a commodity has no asset. On a country page exports, imports and production are
     open; consumption, reserves, stocks, capacity, the balance, the freight block, the list of all goods,
     operators and companies are folded to one line with their count.
   - Search sits in the top bar, left of Prices. A typed word is matched whole or as the beginning of a word
     first; a wrong letter is accepted only when no item has the word itself, the first letter is right and
     fewer than a third of the letters differ; a number is never matched loosely. A table is offered as a CSV
     download only when the registry records a licence that allows it.
   - A text already printed higher on a page is not printed again: the later place points to it. "Copy citation"
     lists the sources of the blocks open on the page.
   - A customs group under 1 Mt a year is printed in kt with one decimal on every page. A precious-metal flow
     estimated above its customs gross weight is printed as that weight (gold, Switzerland to China: 365 t).
   - The block of an event page is titled "Impact"; a sentence that is background and not a consequence sits in
     "What happened".
10. Fifth release, each reversible:
   - Benchmark definitions are taken from the Baltic Exchange's own guide and circulars, stated as facts in the
     atlas's words with a link, never an index value (kept as they are by the owner's decision of 24 November). The Veson
     page is no longer used or linked: its terms forbid both.
   - A benchmark that would have removed a generated corridor has no corridor of its own and links to that
     corridor (TC11, TC22); the grain route P8 counts soybeans only. This keeps the 120 generated ids stable.
   - The four routes of January 2026 are filed under Handy tanker although their parcels (12,500 to 15,000 t)
     are much smaller than that class's typical ship; two of them are drawn from a nearby port (Stavanger for
     Kaarsto, Le Havre for Port Jerome).
   - Vessel classes: one class added (chemical tanker); Handymax and post-Panamax are not classes of their own
     (the Supramax band starts at 40,000 dwt and the Capesize band at 85,000 dwt); the typical sizes of Panamax
     (74,000 dwt) and Supramax (58,000 dwt) are Atlas conventions. Laden days keep the atlas's assumed service
     speed, which is lower than the speed of the standard vessel, and the page says so.
   - Largest class of a port: derived only when the page gives a dimension of a ship, never from a depth alone.
     By deadweight it is the class whose size band holds the limit ("or larger" beyond the largest band: LOOP,
     Hound Point); by dimensions it is the largest class whose standard vessel fits the draught, length and beam
     given. When the two differ, the page shows both with their basis and no single class (Port Hedland, Taman).
     A class with no standard vessel that lies between the class found and the next one ruled out is named
     beside it, since nothing rules it out ("Ultramax or Panamax" at Taman, "Capesize or Newcastlemax" at Port
     Hedland).
     Six coal ports keep a coal tag although their page does not say thermal or metallurgical.
   - Route, class and port pages fold their secondary blocks to one line, as commodity and country pages do: the
     Baltic definition, the Route finder paragraph, the freight rate and the notes of a route; the size band, the
     standard vessel, the world fleet and the shipping companies of a class; the routes, lanes and price series
     of a port. A folded block is not part of "Copy citation". A class page lists the first eight of its routes,
     the rest behind "Show all (N)".
   - "Copy citation" reads the source of every key figure that is open, including those given as text (the
     standard parcel and the duration of a Baltic definition, the typical size and size band of a class, the
     distance computed on the SeaRoute network), and a source line whose link holds a name and a site is one
     source, with its address.
   - A port of a route that is not an asset links to the largest lane through it of a cargo the route carries,
     or stays plain text.
   - Ports are drawn at every zoom like every other asset: with 190 of them the world view is crowded,
     especially on a phone. Nothing was hidden or shrunk.
   - Companies: a figure covers one commodity only (a volume that covers several is in the text); a share in
     `parent` is the one the cited page states; a former owner is not matched to an asset. Sanction marks come
     from OFAC and UK notices only.
   - Freight indicators: the published BLS series is still the copy taken earlier through FRED, because the BLS
     refused every request on the days of the work (quota without a key); its note says so and the weekly job
     replaces it as the BLS answers.
   - Update jobs: the checks do not run on a push to a working branch; Dependabot pull requests are switched off
     (`open-pull-requests-limit: 0`); the downloader identifies itself as `data-update-script/1.0
     (python-requests)`; the yearly downloads are kept between runs as a workflow artifact for 90 days; the guard
     refuses a positive price that moves beyond its own largest past move (never wider than a factor of five) and
     checks a series that crosses zero on its shape only.

11. Sixth release, each reversible:
   - **French ports.** Grain, oilseeds and meal load at Rouen or La Pallice by partner: Rouen for the countries
     its page names (China, Morocco, Algeria and eight less usual destinations) and for the Channel, the North
     Sea and the Baltic; La Pallice for the other partners outside the Mediterranean; both ports are shown as
     options, and the percentages on the France page are an allocation by this rule, not a count. The rule
     puts 2.5 Mt of cereals at La Pallice in 2024, under the 3.0 to 3.5 Mt a year of its page, and 12.3 Mt at
     Rouen. Fertilisers and general cargo: Le Havre on the Atlantic side, Fos on the Mediterranean side. Oil,
     coal and ore are unchanged.
   - **Turkey.** Scrap, pig iron and direct-reduced iron: Eregli for the Black Sea partners, Iskenderun for the
     others, Izmir as an option, in both directions. The page read names the steel works, not the cargo, and the
     lane page says so.
   - **Russian, Saudi, Canadian and Indian fertilisers** of the new groups load at the port the earlier
     fertiliser groups already used (Ust-Luga, Jubail, Vancouver, Mundra), for every destination.
   - **A river leg** is added for a port more than 50 km from the sea network: from a page that gives the
     length by river (Rouen, 120 km to Honfleur) or, where no page read gives it, the straight line between the
     port and the river's mouth, labelled an Atlas measure (Bremen, 56 km). It is drawn as one straight segment.
     Ports between 20 and 50 km (Calcutta, Ho Chi Minh City, Campana, Yangon and others) have none.
   - **The cap of an "up to" figure at a passage** has three cases (the other groups' tonnage subtracted up to
     85% of IMF PortWatch's volume for the ship type; the whole volume above; no cap under an alert that
     explains an excess). The 85% is the atlas's own threshold.
   - **Mozambique's coke** is dropped as coal declared under the coke code (no coke production in the EIA series
     in any year since 1980); **Zimbabwe's** is kept with a note that customs data and the EIA series disagree.
   - **Rows kept as reported against the value rule**: a reviewed list (18 rows, each with its reason) of pairs
     whose own price level is steady and far from the group's; sunflower seed keeps its reported tonnage above
     the reference price only (seed for sowing); coke and sunflower oil are not treated as homogeneous groups.
   - **Declarations by trading centres**: four pairs with Switzerland carry a caveat and name no generated
     route; their tonnes are still counted at the passages of the route to the declared destination.
   - **Notes that offer a reading**, each marked as not established: Mozambique's imports of chromium ore and
     ferro-chromium (transit from South Africa), Djibouti's imports of compound fertilisers (cargo for
     Ethiopia).
   - **Generated routes.** The earlier groups keep their cap (122, 120 before; wheat may have a thirteenth
     corridor) so that the routes of the fifth release stay; the new groups have their own (20 for fertilisers
     and sulphur, 10 for grains and oilseeds, 10 for metal bulks, 6 for the two fertiliser groups added by the
     review). Two routes of the fifth release ended and nine changed content, all through the French ports.
   - **Prices.** A USGS annual price is published under the product, country, unit and source that the file
     gives, never as a market benchmark; the unit of the molybdenum price is quoted as the file gives it, which
     does not say whether the kilogram is of oxide or of contained metal. Barley and sorghum continue as annual
     averages after their monthly series stopped.
   - **Search and chips.** A whole word in a name, a code or a cargo name ranks before the beginning of another
     word; "fertiliser" and "fertilizer" give the five fertiliser pages in the order of the tonnage traded
     (Urea & nitrogen, Phosphate, Potash, Sulphur, NPK). A chip names the product when its page holds several,
     except on the two coal pages and "Rapeseed & canola".
   - **Vessel class pages** list a commodity when a main lane is typed in the class first; the classes that only
     serve a cargo second are not listed.
   - A port whose page names a plant and not the cargo keeps that port, under the basis "page names the plant,
     not the cargo" (eight rows: two steel works, an alumina plant, five refineries).

## Known limits

- Baltic Exchange index values are proprietary and are not shown.
- **None of the reworked update jobs has run on GitHub yet.** They were tested with simulated repositories, a
  mocked GitHub and a fresh clone under Python 3.12; the first real runs are the PortWatch job (Wednesday 25
  November 2026, 19:17 UTC) and the prices job (the same day, 21:43 UTC). What only a real run can confirm is
  listed in `docs/UPDATING.md`. Before the sixth release the price build was run as the job runs it, without
  the annual files that GitHub does not have: the 154 series came out identical, in the same order.
- The BLS freight series is still the copy taken through FRED until the BLS API answers; if the keyless quota is
  always exhausted on GitHub's shared addresses, the series stops advancing and an issue opens after three runs.
- No freight rate in USD per tonne and no Baltic value: the atlas has routes, definitions and two long
  indicators, not rates.
- Events: 37 of the 80 events still cite a Wikipedia article as one of their pages; one (the cobalt export
  suspension of the Democratic Republic of the Congo) rests on a trade-press page that asks for a free account
  after three articles.
- Infrastructure: 394 of 657 assets have no status (most of the new ports); 30 of the 190 ports have a figure and
  20 have limits; two storage hubs only; refineries, pipelines, fields, alumina refineries, steel plants and
  nitrogen plants remain a sample; 95 mines and smelters are placed on the nearest town.
- Benchmark routes: TD32 and TC24 are not in the atlas (their definition could not be read, or names no port);
  there is no page per index (the route page lists the index, its members and weights); a line starts up to
  about 90 km from its port; the shortest sea path between the Black Sea and the Ionian Sea still crosses the
  Corinth isthmus in the lanes and the Route finder (corrected on the benchmark line only).
- Vessel classes: six classes have no standard vessel (Newcastlemax, Panamax, Supramax, chemical tanker, mid-size
  gas carrier, container ship); the Bosporus and the Great Belt have no sourced limit; the fleet, age and
  orderbook of a commercial class are not published for free.
- Companies: 315 of 403 entries have no figure (the company publishes none, or its report was not read: sec.gov
  is not fetched); shipping has 32 companies, 7 with a fleet figure, no container line and no Greek owner; there
  is no page per company.
- Metals production by year: the USGS file on disk holds two years only; earlier editions are not downloaded.
- Metals consumption is an Atlas estimate (production plus imports minus exports of the same product) for three
  metals only; a large importer with no production line is named in the note, not ranked.
- Monthly real prices are not built (no deflator among the downloaded files); crack spreads and the soybean crush
  margin are not built (they need a conversion factor or a yield).
- Trade flows are customs data for 2024; the 2026 disruptions appear in events, banners, monthly energy series
  and PortWatch traffic, not in the flows.
- Typical ports are assumptions: 22.5% of the pair-end tonnage still uses a port with no page
  read, the largest being Japanese and South Korean coal and ore ports, products at Houston and
  Singapore, and Chinese concentrates; 0.5% uses a port whose page names a plant and not the cargo.
- 61.2 Mt of 2024 seaborne tonnage is not routed: 40.6 Mt between a landlocked country without a sourced
  transit port and its overseas partners, 15.2 Mt with no sea route or one under 50 nm (mostly Malaysian
  refined products to Singapore), 5.5 Mt for which no page supports a port on the right coast.
- Named routes cover 65.0% of seaborne tonnes; eleven of the 71 customs groups reach the 70% aimed at.
- **The atlas's assumptions overstate two passages.** Its "at least" tonnage of dry bulk is above IMF PortWatch's
  whole dry bulk volume at Gibraltar (394 Mt against 384 Mt) and at the Bosphorus (207 Mt against 203 Mt), and the pages say so.
  The first suspects: ferrous scrap to Turkey, typed as dry bulk and sent through Gibraltar from the United
  States and north-west Europe; Moroccan sulphur and phosphate fertilisers; Black Sea barley and sunflower
  meal; Turkish chromium ore sent through Samsun.
- Russian fertilisers of every kind leave from Ust-Luga whatever the destination; French oil, coal and ore
  still use the general ports of the country; Trinidad's ammonia has no port page; a river leg exists for two
  ports only, Bremen's being a straight line because no page read gives the river distance.
- New pages without everything the others have: molybdenum, graphite and the "other ferro-alloys" have no sea
  lanes; wheat flour and distillers' dregs are trade tables only; NPK, pig iron and DRI, coke and the alloys
  other than ferro-chromium and ferrosilicon have no free price; the USGS prices are annual and for the United
  States.
- METHODOLOGY.md still names the work packages and reviews of this release (FNCA to FNCI, GV6 and so on) and
  keeps figures of intermediate states that were never published: an editing pass is planned. The sentence that
  defines "at least" is repeated under each of the 967 passage estimates.
- Left from the last review round of the sixth release, all minor: the search for "sulfate" opens "Urea &
  nitrogen" first while "sulphate" opens Potash; a lane whose principal port comes from a coast rule and that
  has an option no longer says that a rule chose it; the price board lists the daily and monthly series that
  are still published (the sixteen new series, annual or closed, open from their commodity page and from the
  search); the year of an annual price is in the label of its key figure, not in its source line; the
  Singapore Strait page cites IMF PortWatch although it has no counter of its own; the Crude oil page carries
  one hint sentence ("Click a producer to open its page"), to be removed.
- No measured split of a country's trade between its coasts or ports, and none of a trade between
  vessel classes: these are options and typical classes, not shares.
- Proved oil and gas reserves and refining capacity are not in the atlas yet (the publishers whose tables are
  free to read do not allow them to be copied; another source is needed).
- Cocoa and coffee have no product tables yet (beans, butter, powder, roasted), although the customs groups
  exist.
- CEPII BACI is refreshed by hand once a year: the publisher can refuse automated downloads; a monthly check
  opens an issue when a newer version exists.
- The country files weigh 9 MB in the repository (one per country, loaded one at a time by the site).
- Left from the review of the fourth release, all minor: the search for "iran war" finds two of the seven events
  of the 2026 war; a typo that fits two names equally lists them in alphabetical order; the long method sentence
  of the gold, silver and platinum tables is printed under the key figure and again under each table; the title
  of a selected event is cut beside an open panel at about 1,100 px (the full title is in the tooltip).

## Open questions for the owner

Decisions that weigh most, first. (The questions on the Baltic Exchange's terms, on GitHub issues, on the BLS
copyright page and on SEC EDGAR were answered on 24 November 2026: see "Decisions of the owner".)

1. **The BLS key.** If the keyless quota of the BLS API stays exhausted on GitHub's shared addresses, the
   freight producer price series needs a free BLS registration key, which only the owner can create. The first
   scheduled run (Wednesday 25 November 2026, 21:43 UTC) will tell.
2. **Russian fertilisers leave from the Baltic for every destination.** Russian urea, DAP and potash of the
   earlier releases, and now ammonia, UAN, phosphoric acid and sulphur, load at Ust-Luga whatever the buyer
   (Russian sulphur to China is drawn round Europe and through Suez, 12,300 nm). A coast rule (Black Sea ports
   for the Mediterranean, Africa and Asia; Far East ports for China) needs pages that name the cargo at those
   ports and moves published lanes of three large groups. Do it next?
3. **French ports for oil, coal and ore** are still the country's general ports (Le Havre, Fos); grain,
   fertilisers and general cargo now follow a rule by partner. The same work for the three bulk families needs
   a page per terminal (Dunkirk, Fos, Le Havre, Donges).
4. **Zimbabwe's coke.** Customs data record 0.9 Mt of coke exported by Zimbabwe in 2024 while the EIA series
   of its coke production reads 399 kt in 2022, 5 kt in 2023 and nothing since. The tonnes are kept, with a
   note that the two sources disagree; Mozambique's, with no production in any year of the EIA series and
   large coal exports, were dropped as coal declared under the coke code. Keep the two treatments?
5. **The map with 190 ports.** Every asset is drawn at every zoom and every type is on by default, as the owner
   decided; the world view is crowded, most of all on a phone. One option inside those decisions: draw the
   port icons smaller at the lowest zooms. Nothing was changed.
6. **Dependabot pull requests** are switched off (each one is a notification e-mail). Turn them on (one grouped
   pull request a month per ecosystem)? Branch protection of `main`, required checks and Dependabot security
   updates are repository settings only the owner can change.
7. **Identification of the scheduled downloads.** The downloader sends a plain client name. The audit (C-140)
   suggests naming the project with the repository address as a contact, which puts the owner's account name in
   every request: one line to change if wanted.
8. **Freight rates.** (a) USDA's grain ocean rates credit private firms (O'Neil Commodity Consulting; ESALQ/USP
   for Brazil; CFTS Kyiv for Ukraine) and carry no licence: ask USDA (GTRContactUs@usda.gov) whether they may be
   republished? (b) The Bank of Japan asks to be notified by e-mail of a service that uses its series: would the
   owner send that notice? (c) Realised time-charter earnings per day, published each quarter by listed
   shipowners, would give a rate history by class without any Baltic value, but only by hand: is a quarterly
   manual entry acceptable?
9. **Tables that need a publisher's written consent.** worldsteel (crude steel, pig iron and direct-reduced iron
   by country), GIIGNL and the IGU (LNG by country) publish tables that are free to read and that their terms
   forbid to copy. The atlas cites one total each beside its own customs table. A country table would need a
   written request from the owner to each publisher (addresses and wording are in the notes of the source
   scouts); nothing is asked unless the owner wants it.
10. **Free accounts and keys**, none needed today: UN Comtrade's public preview answers without a key (slowly,
    a few calls a minute), the US Census monthly export file is a free download, and the EIA bulk files cover
    what the API would. A free Comtrade key or EIA key would only make the downloads faster. The `FRED_API_KEY`
    secret is no longer read and can be deleted.
11. **Files the owner could download by hand**: Global Energy Monitor's inventories (CC BY 4.0, behind a form
    with an e-mail address) to move the infrastructure layer from a sample to an inventory; the Energy
    Institute's Statistical Review workbook and its terms of use (the site refuses automated readers), for
    reserves and LNG by country.
12. The IMF PortWatch ports table (names, positions, codes of about 2,000 ports) is kept in the repository under
    the IMF's terms of use, with credit; commercial reuse would need the IMF's permission. Accept?
13. Benchmark routes: give TC11 and TC22 their own corridor (two generated corridors would disappear and their
    addresses with them)? Add TD32 and TC24 once their definition can be read? A page per index?
14. Companies: also show EU designations and OFAC's sectoral lists as sanction marks? Accept "cargoes" or "TBtu"
    as units (Cheniere and Venture Global publish LNG that way)? Ask Cochilco for its terms of reuse (one figure
    is cited with a link)?
15. Containers: still neither in scope nor declared out of scope (audit point C-056); the class page says what it
    is.
16. Licence of the documentation files (README, METHODOLOGY, DATA_SOURCES, NOTICE): not decided.
17. Where should a second entry point to the chokepoint status board go (it opens from any chokepoint page)?
18. Official names of the four-digit customs headings: the texts of UN Comtrade are for internal use only; the
    atlas derives its names from the CEPII BACI product list.
19. Should a commodity filter the freight routes drawn on the map (audit point A-070)? Every route stays drawn
    today, as the owner set it.
20. A new kind of event, "trade measure" (export bans, quotas, tariffs), would separate the 33 events added in
    the fourth release from the disruptions of passages.
21. The choices listed above, each reversible.

## Update jobs

- Prices (World Bank, EIA, the three freight indicators): Wednesdays at 21:43 UTC, after the EIA's weekly
  release, with a retry on Thursdays at 09:43 UTC. PortWatch: Wednesdays at 19:17 UTC. Yearly sources and the
  check of the CEPII BACI version: the 15th of each month at 22:17 UTC. Each job also writes the "What changed"
  digest and its Atom feed.
- Data freshness check: Mondays at 13:37 UTC. Watcher of the yearly pages read by hand: the 3rd of each month.
- The three update jobs share one queue and commit only the paths they write; the checks run before each
  publication; a data job always ends green.
- Signals, all as GitHub issues, never an e-mail from a failed run of a data job: "Data update failing: <source>"
  (after one, two or three runs according to the source), "Data update discarded by the data checks", "Data
  update not pushed", "Site not republished: a check failed", "Data stale: <source>", "Watcher failing:
  <workflow>", "New release available: <source>". A push to `main` whose checks or deployment fail is red and
  GitHub e-mails the person who pushed, as for any repository.
- `docs/UPDATING.md` describes each job, the yearly refresh of CEPII BACI by hand, and what to look at.
- If `main` is ever protected, GitHub Actions must be allowed to push to it.
