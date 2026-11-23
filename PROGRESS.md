# Commodity Flows Atlas: progress

_Last updated: 2026-11-23, after the third release of audit fixes_

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
| 3 | Wrong figures per commodity (gas, LNG, copper, precious metals, lithium, nickel, steel, fertilisers, cocoa) | corrections done, released on 23 November |
| 4 | Data already downloaded and unused | first part released on 23 November (third release): full country tables and history by year, price series and price board, generated freight corridors, chokepoint board, alerts and event links. Pending: country profiles, monthly crude and energy stocks, USDA 2026/27, metals pages, lanes for the metals that have none |
| 5 | Hand-curated layers | infrastructure schema, statuses and 207 added assets released on 23 November; ports, companies, event sources, Baltic routes and vessel classes pending |
| 6 | Additions (freight rates, port data, search, forecasts, new commodities) | pending |
| all | Pipeline alerts, validator, tests in CI, documentation | in progress: 697 unit tests, three data validators, generated notices, methodology rewritten for the engine |

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
  - 19 vessel classes (dry bulk, tankers, gas carriers, and one container class for the bagged and
    boxed cargoes: cotton, coffee, cocoa, refined metals).
  - 223 routes: 60 Baltic benchmarks, 43 heavy non-benchmark routes written by hand and 120 Atlas
    corridors generated from customs pairs. 194 have a corridor share of seaborne trade and 197 a
    2005 to 2024 volume history; 29 say why they have none.
  - 34 customs groups with seaborne lanes on real sea routes: 2,400 main lanes, 35 mixed lanes,
    182 history-only lanes; a table of 23,853 recorded pairs.
  - A route finder for every recorded pair.
  - 30 chokepoint pages: the 28 passages counted by IMF PortWatch (weekly series since 2019,
    vessels and estimated cargo tonnes), plus the Singapore Strait and Cape Horn; 20 of them carry
    Atlas estimates of the cargo that has to cross or may cross; a status board of all passages.
  - 47 disruption events from 2008 to 2026, linked to commodities, countries and assets, and three
    alert banners whose severity and lists follow the data.
- **39 commodities**: production and reserves (USGS, EIA), agriculture (USDA PSD, FAOSTAT), trade
  and flows (CEPII BACI 2024), every country in every table, series by country and year, 247
  company entries.
- **501 infrastructure assets** (fields, refineries, LNG terminals, pipelines, mines, smelters,
  ports).
- **Country profiles** for 147 countries.
- **Prices**: 136 series (World Bank monthly since 1960 and annual real prices, World Bank price
  indices, EIA daily, USGS annual, one freight cost index), a price board, lookup by date.
- **History**: a 2005 to 2024 timeline of flows, with events to 2026.
- **48 registered third-party sources**, every one free to read, plus the atlas's own entry for its
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

## Known limits

- Baltic Exchange index values are proprietary and are not shown.
- Event texts: the three alert texts and their three events were checked against the pages they cite; the other
  44 events were not, and a reviewer found several whose cited page does not support every sentence (the return to
  Suez in 2026, the Houthi blockade of July 2026, the Gaza ceasefire of 2025, the collapse of Hormuz traffic). They
  are the next thing to re-source.
- The new mechanism of the weekly PortWatch job (restore the daily table from the last run's artifact, download
  only the new days) was tested with a simulated GitHub; its first real run is Wednesday 25 November 2026.
- Infrastructure: 238 of 501 assets have no status; 95 of the 129 new mines and smelters are placed on the nearest
  town; the potash figures of Qarhan and the Dead Sea Works do not say whether they are KCl or K2O and are listed
  with the K2O figures; alumina refineries, steel plants and nitrogen plants have no asset type yet; two assets at
  Kolwezi share one point.
- Metals production by year: the USGS file on disk holds two years only; earlier editions are not downloaded.
- Monthly real prices are not built (no deflator among the downloaded files); crack spreads and the soybean crush
  margin are not built (they need a conversion factor or a yield).
- Trade flows are customs data for 2024; the 2026 disruptions appear in events, banners and
  PortWatch traffic, not in the flows.
- Typical ports are assumptions: 22.4% of the pair-end tonnage still uses a port with no page
  read, the largest being Japanese and South Korean coal and ore ports, products at Houston and
  Singapore, and Chinese concentrates.
- 64 Mt of 2024 seaborne tonnage is not routed, most of it between a landlocked country without a
  sourced transit port and its overseas partners (Belarusian potash, Paraguayan grain, Central
  Asian dry bulk).
- No measured split of a country's trade between its coasts or ports, and none of a trade between
  vessel classes: these are options and typical classes, not shares.
- Oil and gas reserves, refining, metals consumption and freight rates are not in the atlas yet.
- CEPII BACI is refreshed by hand once a year: the publisher can refuse automated downloads.

## Open questions for the owner

1. Free accounts that would replace estimates with measured figures, if the owner creates them:
   UN Comtrade (importer-side quantities for Chilean copper, tin and lithium; key stored as the
   repository secret `COMTRADE_API_KEY`), US Census USA Trade Online (LPG from the United States
   to Mexico by transport mode), FRED (the US deep-sea freight producer price index, secret
   `FRED_API_KEY`).
2. Baltic Capesize routes C10_14 and C14: reported as ended on 24 December 2025, not confirmed on
   two public pages; both are shown with the note "status not confirmed".
3. Licence of the documentation files (README, METHODOLOGY, DATA_SOURCES, NOTICE): not decided.
4. The choices listed above.
5. Global Energy Monitor publishes asset inventories under CC BY 4.0 (refineries, coal mines, steel plants, LNG
   terminals, with coordinates, capacity and status). Their download needs a short form with an e-mail address: if
   the owner downloads the files, the infrastructure layer can move from a sample to an inventory.
6. Where should a second entry point to the chokepoint status board go (it opens from any chokepoint page)? The top
   bar and the Controls panel were left as the owner fixed them.
7. The raw World Bank workbooks contain a sheet the publisher probably did not mean to ship ("Mismatch Details", a
   comparison of barley and sorghum cells): the atlas does not read it; mentioned for the record.

## Update jobs

- Prices: Wednesdays at 21:43 UTC, after the EIA's weekly release, with a retry on Thursdays at 09:43 UTC.
  PortWatch: Wednesdays at 19:17 UTC. Annual sources: the 15th of each month. Each job also writes the "What
  changed" digest and its Atom feed.
- A GitHub issue opens only after a source fails several runs in a row; no e-mail is sent.
- If `main` is ever protected, GitHub Actions must be allowed to push to it.
