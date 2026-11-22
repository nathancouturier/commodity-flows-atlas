# Commodity Flows Atlas — Progress

_Last updated: 2026-11-22, end of the build (about 6 h 30 min of work)_

Live site: https://nathancouturier.github.io/commodity-flows-atlas/

## Status overview

| Phase | Scope | Status | Complete |
|---|---|---|---|
| 1 | Foundation: stack, map engine, data model, design system, Pages deploy | done | 100% |
| 2 | Freight core: vessel classes, routes, shares, chokepoints, alternatives, freight cards, route finder | done, reviewed | 100% |
| 3 | Key energy and metals with infrastructure and country profiles | done, reviewed | 100% |
| 4 | Remaining commodities: other metals, softs, fertilisers | done, reviewed | 100% |
| 5 | History and prices: price charts with date lookup, route history by year | done, reviewed | 100% |
| 6 | Automation: scheduled robust updates | done; price job proven on GitHub, PortWatch and annual jobs test-run | 95% |
| 7 | Polish, mobile, performance, accessibility, fresh-eyes review | done | 100% |
| **Overall** | | | **~99%** |

## Budget

- Finished within the first usage window (estimate: about 90% of it used; the meter is not
  visible to me). No second reset was needed.
- Heavy work ran on Sonnet subagents and one Haiku downloader. Architecture, data model,
  pipelines and final integration stayed in the main session.

## What the atlas contains

- **Freight (the core)**:
  - 17 vessel classes.
  - 103 routes: 60 Baltic benchmarks and 43 heavy non-benchmark routes. Each has distance, laden
    days, chokepoints, Cape/Suez/Panama alternatives, corridor share of seaborne trade, estimated
    share of the class's tonne-miles, and 2005–2024 history.
  - Seaborne lanes for 32 commodity groups on real sea routes.
  - A route finder: origin → destination → typical class, share of that trade, ports,
    chokepoints, disruption notes.
  - 16 chokepoints with IMF PortWatch transits (last 28 days, weekly chart since 2019), EIA oil
    flows and typical detours.
  - 45 disruption events from 2008 to 2026, and live banners for the Hormuz closure, Red Sea
    diversions and Black Sea attacks.
- **39 commodities**:
  - Production and reserves: USGS 2026 for minerals, EIA for energy (thermal and metallurgical
    coal split).
  - Agriculture: USDA PSD 2025/26, including ending stocks.
  - Trade and flows: CEPII BACI 2024, including overland and pipeline flows.
  - Refined copper and nickel-intermediate tables.
  - 247 company entries: producers, processors and trading houses.
- **282 infrastructure assets**, each with a source link and status: fields, refineries, LNG
  export and import terminals, pipelines, mines, smelters and ports.
- **146 country profiles**:
  - Ranked exports and imports by value, production shares, assets, companies and lanes.
  - A light check for raw materials outside the list, such as Botswana's diamonds.
- **Prices**:
  - 36 World Bank monthly series since 1960 and 8 EIA daily series since 1986, with basis notes.
  - Look up any date or year ("1986", "Mar 2008").
  - Compare up to three series, with index-to-100.
- **History**: a 2005–2024 timeline that redraws flows year by year, with events.

## Quality checks done

1. Independent data audit: 5 auditors, then a skeptic re-check of each issue; 24 confirmed
   issues fixed.
2. Trader review of the live site: freight desk, energy, metals and agriculture, plus a
   designer/accessibility reviewer. About 45 findings, the important ones fixed.
3. Final fresh-eyes review: scores 6–8/10 by area; the concrete issues it found were fixed.

## Known data limits

- **Freight rates**: Baltic Exchange indices are proprietary and are not shown.
- **Not freely available, so omitted**:
  - Crude and gas reserves (not in EIA's free bulk file).
  - Metals consumption by country.
  - Uranium reserves.
  - A measured split of each trade by vessel class (classes are shown as "typical").
- **Customs blind spots** are flagged on the site: undeclared Iranian crude to China, North
  American pipeline gas tonnage.

## Questions and actions for you

1. **Optional, 2 minutes: freight-cost price series.** FRED's free API needs a key. Without it,
   that one series is skipped with no error and no alert.
   - Create a free account at https://fredaccount.stlouisfed.org/ and request an API key at
     https://fredaccount.stlouisfed.org/apikeys
   - In GitHub, open https://github.com/nathancouturier/commodity-flows-atlas/settings/secrets/actions,
     choose **New repository secret**, set Name `FRED_API_KEY` and paste the key as the Value.
   - The next weekly price update (Tuesdays) then adds "US producer price index, deep-sea freight
     transportation" to the price explorer.
2. **No other action is needed.** Update jobs run on their own:
   - Prices: Tuesdays.
   - PortWatch: Wednesdays.
   - Annual sources: the 15th of each month.
   - Alerts: a GitHub issue opens only after a source fails 3 runs in a row.
3. If you later protect the `main` branch, allow GitHub Actions to push to it. Otherwise the update
   jobs will record failures, which are not emailed.
