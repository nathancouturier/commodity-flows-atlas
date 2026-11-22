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

Scheduled GitHub Actions refresh each source on its own cadence (prices monthly or
daily, annual statistics yearly). Each source is fetched with retries, validated, and
only committed if it passes checks; if a source is down, the last good data is kept.
See `DATA_SOURCES.md`.

## Licence

Code: MIT. Data: each source keeps its own licence, listed in `DATA_SOURCES.md`.
