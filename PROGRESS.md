# Commodity Flows Atlas: progress

_Last updated: 2026-11-23, after the second release of audit fixes_

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
| 4 | Data already downloaded and unused (history by country, full lists, monthly crude, prices, stocks) | pending |
| 5 | Hand-curated layers | infrastructure done and released on 23 November; companies, events, alerts, Baltic routes and vessel classes pending |
| 6 | Additions (freight rates, port data, search, forecasts, new commodities) | pending |
| all | Pipeline alerts, validator, tests in CI, documentation | in progress: 441 unit tests, three data validators, methodology rewritten for the engine |

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
  Taiwan Strait, Luzon) are shown as "One of".
- **Chokepoint shares as "at least" and "up to"**, over every recorded pair and every group (494
  estimates on 30 pages, 77 before), capped by IMF PortWatch volume where it applies, with a note
  where the atlas figure exceeds the traffic PortWatch counted that year. Hormuz crude reads at
  least 27.2%, up to 32.1% (21.2% before); refined products 20.7% (2.4% before).
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
  Peru's unit value: Chile is the first exporter (14 Mt, Atlas estimate) instead of the second.
- Gold, silver and PGM are shown in fine-metal equivalent (declared value over the annual average
  price), with the customs gross weight beside it.
- Lithium has a spodumene table (Australia, Zimbabwe, Brazil to China, Atlas estimate) and lanes;
  nickel has a ferro-nickel table and lanes, and laterite ore is no longer flagged as a misreport.
- Steel and gold tables keep the USGS "Other countries" line; cobalt is no longer labelled ore;
  bauxite and tin state their known gaps; urea production is in product tonnes (FAOSTAT) and
  potash production is converted to the unit of its trade; cocoa cites the ICCO total beside
  FAOSTAT; coffee, cocoa and cotton are in Mt everywhere.

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
  - 18 vessel classes.
  - 103 routes: 60 Baltic benchmarks and 43 heavy non-benchmark routes. 74 have a corridor share
    of seaborne trade and 77 a 2005 to 2024 volume history; 29 say why they have none; 26 carry a
    share of their class's tonne-miles.
  - 34 customs groups with seaborne lanes on real sea routes: 2,400 main lanes, 35 mixed lanes,
    182 history-only lanes; a table of 23,853 recorded pairs.
  - A route finder for every recorded pair.
  - 30 chokepoint pages: the 28 passages counted by IMF PortWatch (weekly series since 2019,
    vessels and estimated cargo tonnes), plus the Singapore Strait and Cape Horn, with 494 Atlas
    estimates of the cargo that has to cross or may cross.
  - 47 disruption events from 2008 to 2026 and three banners written by hand.
- **39 commodities**: production and reserves (USGS, EIA), agriculture (USDA PSD, FAOSTAT), trade
  and flows (CEPII BACI 2024), 247 company entries.
- **294 infrastructure assets** (fields, refineries, LNG terminals, pipelines, mines, smelters,
  ports).
- **Country profiles** for 147 countries.
- **Prices**: 45 series (World Bank monthly since 1960, EIA daily, one freight cost index), with
  lookup by date.
- **History**: a 2005 to 2024 timeline of flows, with events to 2026.
- **46 registered sources**, every one free to read.

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

## Known limits

- Baltic Exchange index values are proprietary and are not shown.
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
4. The six choices listed above.

## Update jobs

- Prices: Tuesdays. PortWatch: Wednesdays. Annual sources: the 15th of each month.
- A GitHub issue opens only after a source fails several runs in a row; no e-mail is sent.
- If `main` is ever protected, GitHub Actions must be allowed to push to it.
