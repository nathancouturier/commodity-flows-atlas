# Commodity Flows Atlas — Progress

_Last updated: 2026-11-22, about 1 h 30 min into the project_

Live site: https://nathancouturier.github.io/commodity-flows-atlas/

## Status overview

| Phase | Scope | Status | Complete |
|---|---|---|---|
| 1 | Foundation: stack, map engine, data model, design system, Pages deploy | done, live | 100% |
| 2 | Freight core: vessel classes, routes, shares, chokepoints, alternatives, freight cards | data done, interface in progress | 65% |
| 3 | Key energy and metals: crude, products, LNG, coal, iron ore, copper + infrastructure + country profiles | data sources secured, starting | 10% |
| 4 | Remaining commodities: other metals, softs, fertilisers | trade lanes already built for all | 10% |
| 5 | History and prices: price charts with date selection, route history by year | route history data done (2005–2024) | 15% |
| 6 | Automation: robust scheduled updates | not started | 0% |
| 7 | Polish and fresh-eyes review | not started | 0% |
| **Overall** | | | **~30%** |

## Budget

- Usage so far: roughly 15–20% of the first usage window (estimate; I cannot read the exact meter).
- Heavy work is delegated to Sonnet subagents (coding, research) and Haiku (downloads).
- On track to finish within two resets: **yes**, if phases 3–4 keep company and infrastructure
  coverage focused on the assets that move markets.

## Done since last update

- **Phase 1 shipped**: Vite + Preact + TypeScript + MapLibre GL app, own Natural Earth base map
  (no third-party tiles or keys), "Abyssal" dark design system, data model with source + year on
  every figure, data validator in CI, GitHub Pages deploy (skips cleanly instead of failing).
- **Freight data (Phase 2)**:
  - CEPII BACI bilateral trade 2002–2024 extracted for 45 commodity groups (HS codes).
  - Seaborne lanes for 32 commodity groups on real sea routes (searoute/Eurostat network), with
    chokepoints crossed, Suez/Panama/Cape alternatives, typical vessel classes, 2005–2024 history.
  - 101 freight routes: 60 Baltic Exchange benchmarks + 41 heavy non-benchmark routes, with share of
    seaborne trade, estimated share of the vessel class's tonne-miles, alternative routing.
  - 17 vessel classes with size, cargoes, draft and canal constraints.
  - 16 chokepoints with IMF PortWatch weekly transits (2019 → 15 Nov 2026), EIA oil flows,
    alternatives; 45 disruption events 2008–2026 (incl. the 2026 Hormuz closure and Red Sea).
- Data quality fixes: Indonesian coal (HS 2701.19) included; tonnage re-estimated from value where
  customs-reported tonnage is inconsistent (e.g. a 152 Mt UAE→Thailand crude record).

## Notes on data limits (no action needed)

- Baltic Exchange index **values** (freight rates) are proprietary and are not shown; route
  definitions are public. Freight rate history will rely on free proxies (see Phase 5).
- The Baltic Exchange website blocks automated reading, so route definitions were verified from
  secondary sources (Veson, Baltic circulars quoted in the press, CFTC filings). Marked in the data.
- FRED and the NGA World Port Index did not respond from this machine today; FRED will be fetched by
  GitHub Actions instead, and ports use the UN/LOCODE list bundled with the searoute package.

## Questions and actions for you

- None blocking right now. GitHub Pages is enabled and deploying.
