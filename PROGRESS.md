# Commodity Flows Atlas: progress

_Last updated: 2026-11-22, end of the first wave of audit fixes_

Live site: https://nathancouturier.github.io/commodity-flows-atlas/

## Where the project stands

The atlas was built, reviewed with the owner (interface), then audited in full on 22 November 2026.
The audit lists 344 points: 144 corrections, 122 completions and 78 additions. They are being
fixed in waves, the most important and most visible first. This file is updated at the end of
each wave.

| Wave | Scope | Status |
|---|---|---|
| 1 | Visible defects of the site and quick data fixes | done, reviewed, deployed |
| 2 | Trade-flow engine: sea or land rule, lane selection, gateway ports, routing, chokepoint shares | designed, next |
| 3 | Wrong figures per commodity (gas, LNG, coal split, copper, precious metals, lithium, fertilisers) | pending |
| 4 | Data already downloaded and unused (history by country, full lists, monthly crude, prices, stocks) | pending |
| 5 | Hand-curated layers (infrastructure, companies, events, alerts, Baltic routes, vessel classes) | pending |
| 6 | Additions (freight rates, port data, search, CSV download, forecasts, new commodities) | pending |
| all | Pipeline alerts, validator, tests in CI, documentation | started (licence files, generated source table) |

## Wave 1: what changed

Each package was implemented, checked by its implementer, reviewed by an independent reviewer
and corrected. 13 important review findings were fixed before release.

- **Price explorer**: a date inside a month returns that month ("monthly average, March 2008");
  a commodity without a free price series no longer opens a Brent chart; clear answers at the
  edges of a series (before the first quote, weekend, month not yet published); statistics for
  each series; three series at most, chosen by the user; event markers can be read and opened.
- **History**: the events of 2024 to 2026 are on the timeline; every event can be reached with
  a mouse, a finger or the keyboard; lane widths use one scale per commodity for all years, with
  reference widths in the legend; lane pages and the seaborne figure follow the selected year,
  and every block that cannot follow it says which year it shows.
- **Links and keyboard**: a pasted link shows exactly the view it describes; the tab title
  follows the view; Back and Forward work inside the site; unknown ids say so; Escape closes
  the dropdowns; chokepoint markers answer to Space; a clear message replaces the black map
  when WebGL is missing.
- **About window**: sources and licences generated from `data/sources.json`, data freshness
  read from `data/_status/updates.json`, disclaimers, credits (Natural Earth, Eurostat SeaRoute),
  third-party notices; sharing metadata, icons, manifest and a 404 page.
- **Phone and tablet**: key figures are never truncated; the price chart takes most of its
  drawer; the detail sheet has a handle and three positions; landscape has its own layout;
  touch targets are at least 32 px.
- **Detail views**: a voyage strip that tells ports from chokepoints; infrastructure lists
  ranked among comparable figures, planned capacity apart, with "Show all"; one rounding rule
  for shares.
- **Chokepoints**: Malacca has its own PortWatch series; Singapore and the Danish Straits are
  labelled for what PortWatch really counts; the 14 PortWatch passages that were downloaded and
  unused have a page; traffic can be read in vessels or in estimated cargo tonnes by vessel
  type; each page lists the mapped lanes that cross it.
- **Routes and vessel classes**: the class share is shown only where its basis holds (26 routes);
  coal is no longer counted twice on the Vostochny route; a route without a meaningful share
  says "n/a" with its reason; stand-in traces are flagged; size bands and strait limits carry
  their source.
- **Commodity and country pages**: "all coal" wherever customs data cannot separate thermal
  from metallurgical coal; hard coal and lignite separated; one coal value row on country pages;
  no 8-row cut on country profiles; trade-hub warnings and the weight basis carried onto country
  rows; source and year of every USD value; rice in milled equivalent; ammonia labelled as
  nitrogen content.
- **Licences and documents**: `LICENSE` (MIT, code), `NOTICE.md` (the atlas's own figures under
  CC BY 4.0, third-party data under each source's licence, Wikipedia material under CC BY-SA 4.0),
  `THIRD-PARTY-NOTICES.md`; `DATA_SOURCES.md` generated from the source registry; README and
  METHODOLOGY corrected against the code.

## What the atlas contains today

- **Freight (the core)**
  - 17 vessel classes.
  - 103 routes: 60 Baltic benchmarks (3 flagged discontinued, 2 drawn as stand-in traces) and 43
    heavy non-benchmark routes. 73 routes have a corridor share of seaborne trade and 75 a
    2005 to 2024 volume history; 27 have neither (time-charter baskets and four routes without a
    customs corridor); 26 carry a share of their class's tonne-miles.
  - Seaborne lanes for 32 commodity groups (1,334 lanes) on real sea routes. Known defects of
    this engine are the subject of wave 2.
  - A route finder: origin, destination, typical class, share of that trade, ports, chokepoints.
  - 30 chokepoint pages: the 28 passages counted by IMF PortWatch (weekly series since 2019,
    vessels and estimated cargo tonnes), plus the Singapore Strait and Cape Horn.
  - 45 disruption events from 2008 to 2026 and three banners written by hand.
- **39 commodities**: production and reserves (USGS, EIA), agriculture (USDA PSD), trade and
  flows (CEPII BACI 2024), 247 company entries.
- **282 infrastructure assets** (fields, refineries, LNG terminals, pipelines, mines, smelters,
  ports). 176 cite Wikipedia, which the owner accepts as a source for now.
- **Country profiles** for 148 entries.
- **Prices**: 45 series (World Bank monthly since 1960, EIA daily, one freight cost index), with
  lookup by date.
- **History**: a 2005 to 2024 timeline of flows, with events to 2026.

## Decisions of the owner

- Interface: all layers and all infrastructure types on by default; every asset drawn at every
  zoom, icons may overlap; Freight under "Routes by vessel class"; Controls and Legend open on
  load, each behind a button that stays in its corner; clicking a country isolates it; compact
  layout; no attribution box on the map (credits are in the About window).
- 22 November 2026: Wikipedia is an accepted source for now. When truly no free source gives a
  figure, the atlas may publish its own estimate, labelled "Atlas estimate" with its method.
  Code under MIT; the atlas's own derived figures under CC BY 4.0.
- Three visual style proposals were sent as images; the site style is unchanged until one is chosen.

## Known limits

- Baltic Exchange index values are proprietary and are not shown.
- Trade flows are customs data for 2024; the 2026 disruptions appear in events, banners and
  PortWatch traffic, not in the flows.
- The sea or land rule, the choice of mapped lanes, the single gateway port per country and the
  shortest-path routing produce known errors (for example Russia to China classed as overland):
  wave 2.
- Oil and gas reserves, refining, metals consumption, and a measured split of each trade by
  vessel class are not in the atlas yet.
- CEPII BACI is refreshed by hand once a year: the publisher can refuse automated downloads.

## Open questions for the owner

1. Baltic Capesize routes C10_14 and C14: the audit's verifier reported that the 180,000 dwt
   codes ended on 24 December 2025. This could not be confirmed on two public pages, so both
   routes are still shown as benchmarks with the note "status not confirmed". A look at the
   Baltic's circular would settle it.
2. Licence of the documentation files (README, METHODOLOGY, DATA_SOURCES, NOTICE): not decided.
3. Optional: a free FRED API key adds the US deep-sea freight producer price index (create it at
   https://fredaccount.stlouisfed.org/apikeys and save it as the repository secret `FRED_API_KEY`).
   Without it the series is skipped with no error.

## Update jobs

- Prices: Tuesdays. PortWatch: Wednesdays. Annual sources: the 15th of each month.
- A GitHub issue opens only after a source fails several runs in a row; no e-mail is sent.
- If `main` is ever protected, GitHub Actions must be allowed to push to it.
