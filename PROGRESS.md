# Commodity Flows Atlas — Progress

_Last updated: 2026-11-22, about 4 hours into the project_

Live site: https://nathancouturier.github.io/commodity-flows-atlas/

## Status overview

| Phase | Scope | Status | Complete |
|---|---|---|---|
| 1 | Foundation: stack, map engine, data model, design system, Pages deploy | done, live | 100% |
| 2 | Freight core: vessel classes, routes, shares, chokepoints, alternatives, freight cards, route finder | done, live | 95% |
| 3 | Key energy and metals with infrastructure and country profiles | done, live; trader review pending | 85% |
| 4 | Remaining commodities: other metals, softs, fertilisers | data and pages live for all 39 commodities | 80% |
| 5 | History and prices: price charts with date lookup, route history by year | done, live | 85% |
| 6 | Automation: scheduled robust updates | built and tested locally; first scheduled runs pending | 80% |
| 7 | Polish, mobile, performance, accessibility, fresh-eyes review | starting | 10% |
| **Overall** | | | **~80%** |

## Budget

- Usage so far: roughly 45–55% of the first usage window (estimate).
- On track to finish within two resets: **yes**. Remaining work is review, fixes and polish.

## Done since last update

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
