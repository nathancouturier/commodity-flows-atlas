# Commodity Flows Atlas

An interactive world atlas of raw material flows — energy, metals and minerals, softs and
agriculture — and of **freight**, the shipping that moves them.

**Live site:** https://nathancouturier.github.io/commodity-flows-atlas/

## What the atlas shows

- **Physical flows** between countries, drawn on real sea lanes and animated by volume.
- **Freight**, in the side panel under "Routes by vessel class": vessel classes (Capesize to
  Handysize, VLCC to MR, LNG and LPG carriers), Baltic Exchange benchmark routes and other
  heavy-traffic routes, chokepoints and the alternative routings used when they close, how route
  shares changed over 20 years. A **Route finder** in the same panel gives the route and vessel
  class for a commodity and a pair of countries.
- **Country profiles**: ranked key exports, imports and production shares, main mines,
  fields, refineries and companies.
- **Commodity pages**: production, reserves, consumption, exports, imports, main flows,
  main producers, processors and trading houses, and long price histories (**Prices**).
- **Infrastructure**: major mines, fields, refineries, LNG terminals, pipelines, smelters and ports.

Every figure carries its source and year (hover it, or see the detail panel).
No live vessel positions are used. Credits and licences are in the About window (Sources and
Notices tabs) and in [`NOTICE.md`](NOTICE.md).

## Repository layout

| Path | Contents |
|---|---|
| `web/` | The site: Vite + Preact + TypeScript, MapLibre GL for the map, uPlot for charts |
| `web/scripts/validate-data.mjs` | Checks the data files (source ids, shape) before an update is kept |
| `data/` | Processed, versioned data (JSON) served by the site. The shapes are the interfaces of `web/src/types.ts`; `data/sources.json` is the source registry and `data/_status/` records every update run |
| `pipeline/` | Scripts that download and process the public sources into `data/`; `pipeline/cache/` holds the reduced BACI trade table and other tracked caches |
| `.github/workflows/` | Site deployment and scheduled data refresh jobs |
| `DATA_SOURCES.md` | Every source, its licence, update cadence and how it is fetched (generated from `data/sources.json`) |
| `METHODOLOGY.md` | How derived figures (route shares, vessel class estimates) are computed |
| `NOTICE.md`, `THIRD-PARTY-NOTICES.md` | Licences of the data and credits; licences of the packages and fonts |
| `PROGRESS.md` | Build progress and open questions |

## Running locally

```bash
cd web && npm install && npm run dev
```

Node 22 is used by the workflows. The site reads `data/` through the symlink `web/public/data`.

To rebuild data, set up Python (3.12 in the workflows, 3.11 or later required):
`pip install -r pipeline/requirements.txt`. The raw downloads go in `raw/`, which is not tracked.
The usual order, from the repository root, is:

1. `python pipeline/prices/fetch_prices.py` (prices) and `python pipeline/freight/fetch_portwatch.py` (chokepoint traffic);
2. `python pipeline/annual/update_annual.py` downloads the yearly sources, then rebuilds what depends on
   them: `pipeline/freight/build_lanes.py` and `pipeline/freight/build_freight.py` run when CEPII BACI has a new
   version (or the previous run left them pending), and `pipeline/commodities/build_commodities.py` and
   `pipeline/commodities/build_profiles.py` run when any annual source changed;
3. `node web/scripts/validate-data.mjs` checks the result.

The CEPII BACI trade database is a 2.4 GB download, reduced to `pipeline/cache/baci_flows.csv.gz` by
`pipeline/trade/extract_baci.py` (years from 2000). The cache is tracked, so rebuilding the lanes and
commodity pages does not need the download. CEPII can refuse the cloud runners, so a new BACI version
is normally fetched locally with `python pipeline/annual/update_annual.py --only baci`, and the updated
cache committed.

The infrastructure assets (`data/infrastructure/`) and the company lists
(`data/commodities/companies.json`) are written by hand from their cited sources; no script rebuilds them.

## Data updates

Three scheduled GitHub Actions workflows refresh the data. Each can also be started by hand
(Actions tab, "Run workflow").

| Workflow | Schedule (UTC) | Sources |
|---|---|---|
| `update-prices.yml` | Tuesdays 17:43 | World Bank Pink Sheet (monthly file, checked weekly), the 8 EIA daily spot-price files, and (optional, with a free `FRED_API_KEY` secret created by the owner) the US deep-sea freight producer price index (a BLS series, via FRED) |
| `update-portwatch.yml` | Wednesdays 19:17 | IMF PortWatch daily chokepoint transits |
| `update-annual.yml` | the 15th, 22:17 | USDA PSD, USGS Mineral Commodity Summaries, EIA INTL, FAOSTAT and WNA (at most every 80 days), CEPII BACI (2.4 GB, downloaded only when a newer version exists; see the note above on running it locally), then the dependent rebuilds (`build_lanes` and `build_freight` only when BACI has a new version; `build_commodities` and `build_profiles` when any annual source changed) |

**Robustness.** Downloads (`pipeline/common/fetch.py`) use retries with exponential backoff and jitter,
timeouts, a pause between requests to one host, resumable large files, atomic writes, and reject an HTML
page where a CSV/XLSX/ZIP is expected. Every source is checked before it replaces the previous file (it opens,
has the expected sheet or columns, the record count has not collapsed, the latest date has not moved
backwards). On any failure the previous good files stay in place and the run still finishes green. After the
scripts, `web/scripts/validate-data.mjs` runs; if it fails the whole update is discarded. Valid changes are
committed by `github-actions[bot]` and pushed to `main` (with retry), and the site is redeployed.

**Status and alerting.** `data/_status/updates.json` records, per source, the last attempt and success,
consecutive failures, the last error, the record count and the latest date covered (`data_to`);
yearly sources checked monthly (CEPII BACI, FAOSTAT/WNA) alert after 6 failed runs instead of 3;
`data/_status/log.jsonl` keeps the last 500 runs. When a source has failed 3 runs in a row, the workflow opens
(or updates) one issue titled `Data update failing: <source>` with the label `data-update`, and closes it
when the source succeeds again. Issues must be enabled for the repository.

Run a script locally from the repository root, for example `python pipeline/prices/fetch_prices.py`
(`pip install -r pipeline/requirements.txt`). See `DATA_SOURCES.md` for every source.

After any change to `data/sources.json`, regenerate the table of `DATA_SOURCES.md` with
`python pipeline/common/sources_table.py` (`--check` exits 1 when the file is out of date). The check is not part of
the deploy, so a stale table never blocks a release.

**Search engines.** The site is served under a project path (`/commodity-flows-atlas/`), where crawlers do not read a
`robots.txt`, so none is published (everything may be indexed). `web/public/sitemap.xml` is found only if it is
submitted in the search engines' webmaster tools (for example Google Search Console). `404.html` finds the site root
from the address it is served on, so it also works on a custom domain.

## Licence

- **Code**: MIT, see [`LICENSE`](LICENSE). It covers the source code (the files under `web/src` and `web/scripts`,
  `pipeline/**/*.py` and `.github/`); it does not cover data files. Curated data files under `pipeline/` (definition
  files with third-party or Wikipedia-derived content) and the caches in `pipeline/cache/` follow the data terms of
  [`NOTICE.md`](NOTICE.md).
- **The atlas's own derived figures** (source id `atlas`: shares, estimates, computed totals, lane and route
  geometry): CC BY 4.0. Attribution: "Commodity Flows Atlas".
- **Material adapted from Wikipedia** (the infrastructure files, `data/commodities/companies.json`, the
  Wikipedia-sourced events, vessel-class and chokepoint notes; the list is in [`NOTICE.md`](NOTICE.md)): CC BY-SA 4.0,
  shared under the same licence.
- **Each third-party dataset keeps the licence of its source**, listed in `DATA_SOURCES.md`. Details, credits and the
  position on material that is cited rather than redistributed are in [`NOTICE.md`](NOTICE.md); the licences of the
  software packages and fonts are in [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).

## Disclaimer

- **Not investment advice.** The atlas is general information. Nothing in it is a recommendation to buy, sell or hold
  anything, or a basis for a trading decision.
- **Not for navigation.** Routes, lanes and distances are schematic. They are computed on a simplified sea network and
  must not be used to plan a voyage.
- **No warranty.** The data come from third parties and from the atlas's own estimates. They may contain errors or be
  out of date, and are provided as is, without warranty of any kind.

Boundaries and names on the map come from Natural Earth and do not imply any opinion on the status of a territory.
The same text is in the About window of the site.
