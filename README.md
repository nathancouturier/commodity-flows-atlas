# Commodity Flows Atlas

An interactive world atlas of raw material flows — energy, metals and minerals, softs and
agriculture — and of **freight**, the shipping that moves them.

**Live site:** https://nathancouturier.github.io/commodity-flows-atlas/

## What the atlas shows

- **Physical flows** between countries, drawn on real sea lanes and animated by volume.
- **Freight**, in the side panel under "Routes by vessel class": vessel classes (Capesize to
  Handysize, VLCC to MR, LNG and LPG carriers), Baltic Exchange benchmark routes and other
  heavy-traffic routes, chokepoints and the alternative routings used when they close, how route
  shares changed over 20 years. A **Freight market now** page gives, for tankers and for dry bulk carriers at five passages each, the vessel transits and
  the estimated cargo of the last four weeks against the same weeks a year earlier, beside two indicators that are not freight rates. A **Route finder** in the same panel gives the route and vessel
  class for a commodity and a pair of countries. Most route pages have a **Voyage calculator**
  that works out the days, the fuel, the freight that covers a hire and the time-charter equivalent from figures the visitor types.
- **Country profiles**: ranked key exports, imports and production shares, main mines,
  fields, refineries and companies.
- **Commodity pages**: production, reserves, consumption, exports, imports, main flows,
  main producers, processors and trading houses, and long price histories (**Prices**).
- **Infrastructure**: major mines, fields, refineries, LNG terminals, pipelines, smelters and ports;
  a port that has an entry in the World Port Index also shows its depths, its harbour and, where the publication gives one,
  its largest vessel.

Every figure carries its source and year (hover it, or see the detail panel).
No live vessel positions are used. Credits and licences are in the About window (Sources and
Notices tabs) and in [`NOTICE.md`](NOTICE.md).

## Repository layout

| Path | Contents |
|---|---|
| `web/` | The site: Vite + Preact + TypeScript, MapLibre GL for the map, uPlot for charts |
| `web/scripts/validate-data.mjs` | Checks the data files (source ids, shapes, references between files, ranges) before an update is kept; `guard-data.mjs` compares an update with the last commit |
| `data/` | Processed, versioned data (JSON) served by the site. The shapes are the interfaces of `web/src/types.ts`; `data/sources.json` is the source registry and `data/_status/` records every update run |
| `pipeline/` | Scripts that download and process the public sources into `data/`; `pipeline/cache/` holds the reduced BACI trade table and other tracked caches (the PortWatch daily table in `pipeline/cache/portwatch/` is an ignored working file, not published) |
| `.github/ISSUE_TEMPLATE/` | The form that the "Report an error" button opens; reports arrive as issues of the repository ([`docs/UPDATING.md`](docs/UPDATING.md), "Reports from visitors") |
| `.github/workflows/` | Site deployment, the checks (`ci.yml`) and the scheduled data refresh jobs; how they work and what is done by hand: [`docs/UPDATING.md`](docs/UPDATING.md) |
| `DATA_SOURCES.md` | Every source, its licence, update cadence and how it is fetched (generated from `data/sources.json`) |
| `METHODOLOGY.md` | How the figures are built: cleaning and checks of the customs data, sea or overland, lanes, ports and routes, shares, estimates and conversions |
| `NOTICE.md`, `THIRD-PARTY-NOTICES.md` | Licences of the data and credits; licences of the packages and fonts |
| `release.json` | The number and the date of the published release, shown in the About window; bumped at each release ([`docs/UPDATING.md`](docs/UPDATING.md), "Releasing") |
| `CHANGELOG.md` | What a visitor sees changed, release by release |
| `PROGRESS.md` | Build progress and open questions |

## Running locally

```bash
cd web && npm install && npm run dev
```

Node 22 is used by the workflows. The site reads `data/` through the symlink `web/public/data`.

To rebuild data, set up Python (3.12 in the workflows, 3.11 or later required) with the exact versions the workflows
use: `pip install -r pipeline/requirements-lock.txt` (`requirements.txt` names the direct dependencies). The raw
downloads go in `raw/`, which is not tracked. From a fresh clone, `bash pipeline/bootstrap.sh` does everything below in
order (`--dry-run` prints the steps). The usual order, from the repository root, is:

1. `python pipeline/prices/fetch_prices.py` (prices) and `python pipeline/freight/fetch_portwatch.py` (chokepoint traffic);
2. `python pipeline/annual/update_annual.py` downloads the yearly sources, then rebuilds what depends on
   them: `pipeline/geo/adjacency.py`, `pipeline/freight/build_lanes.py` and `pipeline/freight/build_freight.py` run
   when CEPII BACI has a new version (or the previous run left them pending), and
   `pipeline/commodities/build_commodities.py` and `pipeline/commodities/build_profiles.py` run when any annual
   source changed;
3. `node web/scripts/validate-data.mjs` checks the result.

To rebuild the trade engine by hand, run the builders in this order, from the repository root (each reads what the
one before wrote):

| # | Command | What it writes |
|---|---|---|
| 1 | `python pipeline/geo/adjacency.py` | borders and coasts: `pipeline/cache/adjacency.json`, `data/countries/places.json` (seconds) |
| 2 | `python pipeline/freight/build_lanes.py` | lanes, pairs, caveats and zones under `data/freight/`; the caches `sea_flows.csv.gz`, `mixed_flows.csv.gz`, `seaborne_totals.json`, `route_cache.json`, `geom_cache.json`, `trade_checks.json` (about 20 minutes cold, under 2 minutes with warm route caches) |
| 3 | `python pipeline/freight/build_freight.py` | routes, chokepoints and their shares, chokepoint cargo tables, PortWatch series, vessel classes; check K9 in `trade_checks.json` |
| 4 | `python pipeline/commodities/build_commodities.py`, then `python pipeline/commodities/build_profiles.py` | `data/commodities/*.json`, `pipeline/commodities/QA.md`, `data/countries/profiles/*.json`, `data/countries/years.json` |
| 5 | `node web/scripts/validate-data.mjs` | nothing: checks the data files |

`pipeline/geo/adjacency.py` only needs rerunning when the base map or `pipeline/geo/places_extra.json` changes, and
`build_lanes.py` when the customs cache, the cleaning rules, the mode rules, the gateway tables or the routing change.
A change to `pipeline/freight/routing.py` or to the draught tables discards the route caches (they carry a version
key), so the next lane build is a cold one. The methods are in [`METHODOLOGY.md`](METHODOLOGY.md).

**Tests.** The pipeline has unit and data tests under `pipeline/tests/` (Python `unittest`, no extra dependency).
Run them from the repository root with
`python -m unittest discover -s pipeline/tests -p "test_*.py"` (about 4 minutes); a test that needs a file of `raw/`
or a built file that is absent is skipped. The data tests read the built files, so run them after the builders. The
site's checks are `node web/scripts/validate-data.mjs`, its own tests `node web/scripts/validate-freight.test.mjs` and
`node web/scripts/validate-infra.test.mjs` (all of them: `cd web && npm test`), and `cd web && npx tsc --noEmit`. The
workflow `ci.yml` runs all of them, a production build and its size budget (`web/scripts/check-size.mjs`) on every pull
request, by hand, and before each publication (the deploy calls it); a push to a working branch runs nothing. The
scheduled data jobs rely on `validate-data.mjs` and the before-and-after guard `guard-data.mjs`, which discard an
invalid update.

The CEPII BACI trade database is a 2.4 GB download, reduced to `pipeline/cache/baci_flows.csv.gz` by
`pipeline/trade/extract_baci.py` (years from 2002). The cache is tracked, so rebuilding the lanes and
commodity pages does not need the download. A new BACI version is fetched by hand on a local machine once a year
(`python pipeline/annual/update_annual.py --only baci`, then commit `pipeline/cache` and `data`); the monthly job only
checks the version CEPII lists and opens an issue when a newer one exists. The steps are in
[`docs/UPDATING.md`](docs/UPDATING.md).

The infrastructure assets (`data/infrastructure/`) and the company lists
(`data/commodities/companies.json`) are written by hand from their cited sources; no script rebuilds them.

## Data updates

Three scheduled GitHub Actions workflows refresh the data. Each can also be started by hand
(Actions tab, "Run workflow").

| Workflow | Schedule (UTC) | Sources |
|---|---|---|
| `update-prices.yml` | Wednesdays 21:43 and Thursdays 09:43 (EIA publishes on Wednesday) | World Bank Pink Sheet (monthly file, checked weekly), the 8 EIA daily spot-price files, and the Freight family: the US deep-sea freight producer price index from the BLS public API (no key; history cached in `pipeline/cache/bls`), the Dallas Fed index of global real economic activity and the New York Fed Global Supply Chain Pressure Index |
| `update-portwatch.yml` | Wednesdays 19:17 | IMF PortWatch daily chokepoint transits: only the days after the last one stored, the whole table once a month. The daily table is a working file kept between runs as a workflow artifact, not in git; only the atlas's weekly averages and comparisons are published (NOTICE.md). A second step of the same job reads the recent weeks of the daily port table for the ports of the infrastructure layer (a longer stretch of a quarter of the ports each week) and publishes only weekly sums, `data/freight/port-traffic/`; no daily row is kept (`docs/UPDATING.md`, "Port traffic") |
| `update-annual.yml` | the 15th, 22:17 | USDA PSD, USGS Mineral Commodity Summaries, EIA INTL, FAOSTAT and WNA (at most every 80 days), a check of the CEPII BACI version (the refresh itself is done by hand, see above), then the dependent rebuilds (`build_commodities` and `build_profiles` when any annual source changed) |
| `check-staleness.yml`, `watch-releases.yml` | Mondays 13:37; the 3rd, 14:41 | issues "Data stale: <source>" for a source that stopped updating without failing, and "New release available: <id>" for the yearly pages read by hand (`pipeline/common/release_watch.json`) |

**Robustness.** Downloads (`pipeline/common/fetch.py`) use retries with exponential backoff and jitter,
timeouts, a pause between requests to one host, resumable large files, atomic writes, and reject an HTML
page where a CSV/XLSX/ZIP is expected; they identify themselves plainly (`data-update-script/1.0 (python-requests)`).
Every source is checked before it replaces the previous file (it opens, has the expected sheet, columns, commodities
and series, the record count has not collapsed, the latest date has not moved backwards), and has its own time limit.
On any failure the previous good files stay in place and the run still finishes green. After the scripts,
`web/scripts/validate-data.mjs` (shapes, references between files, ranges) and `web/scripts/guard-data.mjs` (against
the last commit: a table that lost more than a tenth of its rows, a file that shrank by half, a price series whose
shape broke or that moved in one step further than its own history allows) run; if either fails the whole update is
discarded. Valid changes to the paths the job owns are committed by `github-actions[bot]` and pushed to `main`; the
three jobs share one concurrency group and never overwrite each other's status entries (an update that cannot be
pushed is dropped and recorded as a failure). The deploy then runs the checks and republishes the site; when it
cannot, the data stays on `main` and one issue "Site not republished: a check failed" says so.

**Status and alerting.** `data/_status/updates.json` records, per source, the last attempt and success,
consecutive failures, the last error, the record count and the latest date covered (`data_to`);
`data/_status/log.jsonl` keeps the last 500 runs. A step that timed out or crashed is recorded as failed too. When a
weekly source has failed 3 runs in a row, a monthly one 2, or a build step once, the workflow opens (or updates) one
issue titled `Data update failing: <source>` with the label `data-update`, and closes it when the source succeeds
again. A discarded update, an update that could not be pushed, a site not republished and a watcher that cannot run
each open one issue of their own. Issues must be enabled for the repository. What each failure does, what GitHub e-mails (nothing for a data job
in the normal course), how the schedules stay enabled and the steps done by hand are in
[`docs/UPDATING.md`](docs/UPDATING.md).

Run a script locally from the repository root, for example `python pipeline/prices/fetch_prices.py`
(`pip install -r pipeline/requirements-lock.txt`). See `DATA_SOURCES.md` for every source.

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

Country shapes are Natural Earth's default view (version 5.1.1). Natural Earth does not apply one rule to every
disputed or self-administered territory: it draws some as shapes of their own and keeps others inside the shape of a
country, for most of them the country that claims them or the country that administers them; some lie in no shape of the map. The boundaries, names and
designations on the map do not imply official endorsement or acceptance, and the atlas takes no position on the status of
any territory.
The same text is in the About window of the site.
