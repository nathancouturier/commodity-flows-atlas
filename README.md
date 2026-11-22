# Commodity Flows Atlas

An interactive world atlas of raw material flows — energy, metals and minerals, softs and
agriculture — and of **freight**, the shipping that moves them.

**Live site:** https://nathancouturier.github.io/commodity-flows-atlas/

## What the atlas shows

- **Physical flows** between countries, drawn on real sea lanes and animated by volume.
- **Freight**: vessel classes (Capesize to Handysize, VLCC to MR, LNG and LPG carriers),
  Baltic Exchange benchmark routes and other heavy-traffic routes, chokepoints and the
  alternative routings used when they close, and how route shares changed over 20 years.
- **Country profiles**: ranked key exports, imports and production shares, main mines,
  fields, refineries and companies.
- **Commodity pages**: production, reserves, consumption, exports, imports, main flows,
  main producers, processors and trading houses, and long price histories.
- **Infrastructure**: major mines, fields, refineries, LNG terminals, pipelines, smelters and ports.

Every figure carries its source and year (hover it, or see the detail panel).
No live vessel positions are used.

## Repository layout

| Path | Contents |
|---|---|
| `web/` | The site: Vite + Preact + TypeScript, MapLibre GL for the map, uPlot for charts |
| `data/` | Processed, versioned data (JSON) served by the site — see `docs/DATA_MODEL.md` |
| `pipeline/` | Scripts that download and process the public sources into `data/` |
| `.github/workflows/` | Site deployment and scheduled data refresh jobs |
| `DATA_SOURCES.md` | Every source, its licence, update cadence and how it is fetched |
| `METHODOLOGY.md` | How derived figures (route shares, vessel class estimates) are computed |
| `PROGRESS.md` | Build progress and open questions |

## Running locally

```bash
cd web && npm install && npm run dev
```

## Data updates

Three scheduled GitHub Actions workflows refresh the data. Each can also be started by hand
(Actions tab, "Run workflow").

| Workflow | Schedule (UTC) | Sources |
|---|---|---|
| `update-prices.yml` | Tuesdays 17:43 | World Bank Pink Sheet (monthly file, checked weekly) and the 8 EIA daily spot-price files |
| `update-portwatch.yml` | Wednesdays 19:17 | IMF PortWatch daily chokepoint transits |
| `update-annual.yml` | the 15th, 22:17 | USDA PSD, USGS Mineral Commodity Summaries, EIA INTL, CEPII BACI (downloaded, 2.4 GB, only when a newer version exists), then the dependent rebuilds (`build_lanes`, `build_freight`, `build_commodities` and `build_profiles` when present) |

**Robustness.** Downloads (`pipeline/common/fetch.py`) use retries with exponential backoff and jitter,
timeouts, a pause between requests to one host, resumable large files, atomic writes, and reject an HTML
page where a CSV/XLSX/ZIP is expected. Every source is checked before it replaces the previous file (it opens,
has the expected sheet or columns, the record count has not collapsed, the latest date has not moved
backwards). On any failure the previous good files stay in place and the run still finishes green. After the
scripts, `web/scripts/validate-data.mjs` runs; if it fails the whole update is discarded. Valid changes are
committed by `github-actions[bot]` and pushed to `main` (with retry), and the site is redeployed.

**Status and alerting.** `data/_status/updates.json` records, per source, the last attempt and success,
consecutive failures, the last error, the record count and the latest date covered (`data_to`);
`data/_status/log.jsonl` keeps the last 500 runs. When a source has failed 3 runs in a row, the workflow opens
(or updates) one issue titled `Data update failing: <source>` with the label `data-update`, and closes it
when the source succeeds again. Issues must be enabled for the repository.

Run a script locally from the repository root, for example `python pipeline/prices/fetch_prices.py`
(Python 3.12, `pip install -r pipeline/requirements.txt`). See `DATA_SOURCES.md` for every source.

## Licence

Code: MIT. Data: each source keeps its own licence, listed in `DATA_SOURCES.md`.
