# Commodity Flows Atlas — Progress

_Last updated: 2026-11-22, about 5 h 30 min into the project_

Live site: https://nathancouturier.github.io/commodity-flows-atlas/

## Status overview

| Phase | Scope | Status | Complete |
|---|---|---|---|
| 1 | Foundation: stack, map engine, data model, design system, Pages deploy | done, live | 100% |
| 2 | Freight core: vessel classes, routes, shares, chokepoints, alternatives, freight cards, route finder | done, live, reviewed | 100% |
| 3 | Key energy and metals with infrastructure and country profiles | done, live, reviewed | 100% |
| 4 | Remaining commodities: other metals, softs, fertilisers | done, live, reviewed | 95% |
| 5 | History and prices: price charts with date lookup, route history by year | done, live, reviewed | 95% |
| 6 | Automation: scheduled robust updates | built; first run on GitHub being checked | 90% |
| 7 | Polish, mobile, performance, accessibility, fresh-eyes review | review fixes shipped; final fresh-eyes pass next | 75% |
| **Overall** | | | **~92%** |

## Budget

- Usage so far: roughly 75–85% of the first usage window (estimate; the meter is not visible to me).
- On track to finish within two resets: **yes**. Remaining work is review, fixes and polish.

## Done since last update (latest first)

- **Trader and UX review of the live site**: four independent reviewers (freight desk, energy
  trader, metals and agriculture trader, designer/accessibility). Fixes shipped:
  - Overland and pipeline flows now drawn: natural gas, and Canada→US crude.
  - Dated banners for active disruptions (Hormuz closure 2026, Red Sea diversions, Black Sea
    attacks) on the affected commodity, country, route and lane pages.
  - Chokepoint traffic now shows the last 28 days, e.g. Hormuz 3.5 vessels/day against 92 in
    2023, plus the typical detour when a passage is avoided.
  - Commodity pages:
    - Refined copper, nickel intermediates, alumina and refined zinc tables.
    - USDA ending stocks with marketing-year captions.
    - Corridor shares labelled as country-pair corridors.
  - Freight:
    - Vessel-class families in the filters (Panamax/Kamsarmax and others).
    - A single "Coal (thermal + met)" entry in the route finder.
    - Indonesian coal now discharges in South China.
    - Two new Capesize/VLOC routes.
  - EU27 shown on member states; a colour legend for maps coloured by country; options with no
    data are greyed out.
  - Price explorer:
    - Daily series by default.
    - Year lookup gives average, low and high with dates.
    - Index-to-100 comparison.
    - A basis note on each series (e.g. Brent before the 1980s is a posted-price proxy).
  - 48 more sourced assets: lithium, cobalt, gold, uranium, potash, rare earths, aluminium
    smelters, grain/cocoa/palm-oil ports. Company lists enriched to 247 entries.
  - Mobile and tablet layout below 1024 px, keyboard (Escape), landmarks, contrast; charts load
    only when needed.


- **Commodity data for all 39 commodities**:
  - Production and reserves: USGS 2026 for minerals, EIA for oil, gas and coal.
  - Agriculture: USDA PSD for 2025/26.
  - Trade, flows and companies: CEPII BACI 2024.
  - Cocoa: FAOSTAT. Uranium: WNA.
  - Thermal coal trade comes from EIA's thermal-only split.
- **Infrastructure**: 266 sourced assets, each with a source link:
  - 27 oil and gas fields, 33 refineries, 67 LNG terminals and 29 pipelines.
  - 43 mines, 10 smelters and 25 ports.
  - 2026 status updates include Ras Laffan damage, Golden Pass start-up, Arctic LNG 2 sanctions and Cobre Panamá.
- **Country profiles** for 139 countries:
  - Ranked exports and imports by value, production shares, assets and companies.
  - A light "country check" covers raw materials outside the main list, such as Botswana's diamonds.
- **Interface**:
  - Infrastructure layer with an icon per asset type, plus commodity and country pages.
  - Price explorer: 36 World Bank monthly series since 1960 and 8 EIA daily series since 1986. You can look up any date, such as "1986".
  - History timeline 2005–2024 with play and events.
- **Automation**:
  - Weekly price and PortWatch jobs, plus a monthly job for annual statistics that also checks for a new BACI version.
  - Retries, validation, last-good fallback; an alert issue opens only after 3 consecutive failures of a source.
- **Independent data audit**: 5 auditors, then a skeptic re-check of each issue; 24 issues confirmed and fixed:
  - Taiwan was coded "S19" in customs data and its flows were missing.
  - The tonnage repair rule distorted ore flows.
  - VLCC and Capesize lanes ran through Panama.
  - Russian load ports were wrong.
  - Some facts were stale: Shell sold its Bukom refinery, and Sime Darby Plantation is now SD Guthrie.

## Known data limits (no action needed)

- **Freight rates**: Baltic Exchange indices are proprietary and are not shown. As a free proxy, the US producer price index for deep-sea freight (FRED) is fetched by GitHub Actions, since FRED does not respond from the build machine.
- **Crude and gas reserves**: not in EIA's free bulk file, so these sections are omitted.
- **Metals consumption by country**: not freely published, so omitted.
- **Uranium reserves**: omitted.
- **Customs blind spots**: Iranian crude to China is largely undeclared since 2019, and the affected lanes are flagged. North American pipeline gas tonnage is understated in customs data, with a caveat shown.
- **Infrastructure gaps**: some assets lack a sourced capacity and are listed without one. Global Energy Monitor's wiki blocks automated reading.

## Questions and actions for you

- None blocking.
- Optional: the scheduled update jobs push data commits to `main`. If you later add branch protection to `main`, allow GitHub Actions to push, or the updates will be recorded as failures (not emailed).
