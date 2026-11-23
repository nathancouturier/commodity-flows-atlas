# Infrastructure layer

`data/infrastructure/*.geojson` holds the mines, smelters, ports, oil and gas fields, refineries, LNG terminals and
pipelines that the atlas draws on the map and lists on commodity and country pages.

**This layer is a hand-curated sample, not an inventory.** Each asset was picked because it is large, well known or
needed to read a flow (an LNG terminal that the trade engine reads, a port that a lane starts from). The layer does not
list every mine, port or pipeline of a country, and an absent asset means nothing about whether it exists. Nothing
rebuilds these files and no scheduled job touches them: they change only when a person edits them and runs the check
below. The atlas shows each figure with the source it came from and the year it refers to, as it does everywhere else.

## Files

| File | `type` values it holds |
|---|---|
| `fields.geojson` | `field` |
| `refineries.geojson` | `refinery` |
| `lng.geojson` | `lng-export`, `lng-import` |
| `pipelines.geojson` | `pipeline` (a line; every other type is a point) |
| `mines.geojson` | `mine` |
| `smelters.geojson` | `smelter` (smelters and metal refineries) |
| `ports.geojson` | `port` |

`sources_energy_infra.json` and `sources_mining_infra.json` in this folder list the source ids the two groups of files
use; they are merged into `data/sources.json`, which is the registry the site reads.

## Properties of a feature

| Field | Type | Meaning |
|---|---|---|
| `id`, `name`, `type`, `c` | text | Never rename an id or delete a feature: routes, events and the trade engine refer to ids. `c` is the ISO3 code of the country. |
| `k` | list of commodity ids | The commodities the asset handles, the main one first. Only ids of `data/commodities/index.json`. |
| `cs` | list of ISO3 | Pipelines: every country crossed, in order. |
| `operator` | text | Operator and owners as the source states them. |
| `opened` | number | Year of first operation. |
| `capacity` | `{v, u, y?, n?, orig?}` | Nameplate or design capacity only: what the asset can do per year or per day. `y` is the year the statement refers to, left out when the source does not say (the site then prints "year not stated"). |
| `output` | `{v, u, y, what, n?, orig?}` | A dated, measured figure. `what` is `production`, `exports` or `throughput` (port traffic, pipeline flow). `y` is required and is a number; a fiscal year takes the calendar year in which it ends, with the label in `n` ("FY2024-25"). |
| `status` | text | One of the values below. Required on every feature. |
| `statusAsOf` | `"YYYY"` or `"YYYY-MM"` | When the status was true according to the page read. Required unless the status is `not-stated`. |
| `statusNote` | text | Optional short reason a reader sees next to the status ("drone strike on 14 March 2026, two units shut"). |
| `s`, `url` | source id, page | `s` is an id of `data/sources.json`; `url` is the page that supports the figures of this feature. |
| `read` | `"YYYY-MM"` | The month the page was read. It is shown once, in the source line, and never as the year of a figure. There is no feature-level `y`. |
| `coord` | `"site"` or `"approx"` | See below. |
| `note` | text | Reader-facing text only: no working notes ("via search summary", "figures were stripped", "latest on page"). |
| `product`, `length_km` | text, number | Pipelines: what they carry and their length. The site shows both. |

`n` says in a few words what a figure counts ("iron ore", "copper in concentrate", "refined copper (cathode)",
"total cargo", "100% basis", "phase 1 of 2"). When a figure was converted, `orig` keeps the source's own figure and
unit ("1 billion lb Cu/y") and `v` is rounded to the precision of the original. The site prints `v u` and shows `orig`
beside it.

A figure that is the production, exports or traffic of a year goes in `output`, not in `capacity`. A feature may have
both. When the source does not let you tell which one a figure is, keep it as `capacity` without `y` and write "as
stated by the source" in `n`.

## Units

`capacity.u` and `output.u` take one of these seven values, nothing else:

| Unit | Used for | Conversion from the usual source units |
|---|---|---|
| `kb/d` | crude oil and products: fields, refineries, oil pipelines, oil terminals | 1 mb/d = 1,000 kb/d |
| `bcm/y` | natural gas: fields, gas pipelines | Bcf/d x 10.34 = bcm/y; MMcf/d x 0.01034 = bcm/y |
| `Mtpa` | LNG liquefaction and regasification (the `type` says which) | |
| `Mt/y` | ore, coal, bauxite, potash, concentrate, port cargo | million short tons x 0.9072 = Mt |
| `kt/y` | metal contained or refined metal, spodumene and other small concentrates | billion lb x 453.6 = kt; Mt x 1,000 = kt |
| `t/y` | gold, silver, platinum-group metals | koz x 0.0311 = t |
| `tU/y` | uranium | Mlb U3O8 x 384.6 = tU; t U3O8 x 0.848 = tU |

The site ranks assets of a commodity page only among figures of the same kind (capacity with capacity, production with
production), the same unit, the same commodity and the same form (ore, concentrate, metal), planned and under-construction
assets apart. A figure that does not fit one of these units is not entered until the vocabulary is extended here, in
`web/scripts/validate-infra.mjs` and in `web/src/lib/capacity.ts`.

## Status

| Status | Use it when |
|---|---|
| `operating` | The page read says the asset runs. |
| `damaged` | The page reports damage (an attack, a fire, a storm) and the asset is not back to normal. |
| `suspended` | Work is stopped for a reason that is not damage (a strike, a licence, a sanction, force majeure). |
| `idle` | Built, able to run, and not running (care and maintenance, no supply). |
| `construction` | Being built. Put the expected year in `opened` only if the source gives one. |
| `planned` | Announced or approved and not yet being built. |
| `closed` | Permanently out of service. |
| `not-stated` | No page read says whether the asset runs. Never assume `operating`. |

`statusAsOf` is the date of the event for `damaged`, `suspended` and `closed`; for the other statuses it is the month the
page was read. The site shows it as "Damaged as of March 2026".

The History timeline reads two fields. An asset whose `opened` year is later than the selected year is drawn dimmed and
its tooltip says "opens in <year>" (it is never hidden). A status dated after the selected year is not applied: the
asset is drawn as operating, unless it was not open yet.

## Coordinates

`coord` is `site` when the point is the asset itself, and `approx` when it is a town, a centroid or a schematic
position. The
site prints "Approximate location" on those assets. A point is checked against the country `c`: it must lie inside the
country's polygon or within 60 km of it (370 km for a field, which may be offshore).

## Adding or changing an asset

1. Read the page that supports each figure, in this session. Never type a figure from memory.
2. Add the feature to the right file, following the table above. Use an existing `s`, or add the publisher to
   `data/sources.json` first (the label names the real publisher; the link a reader follows is the feature's `url`).
3. Keep each figure in the right field: capacity in `capacity`, a dated production, export or traffic figure in
   `output`, with its own year. Convert to the units above and keep the source's own figure in `orig`.
4. Give the status and its date. If the page does not say, use `not-stated`.
5. Run the check from the repository root:

   ```
   node web/scripts/validate-infra.mjs            # this layer alone
   node web/scripts/validate-data.mjs             # every data file, this layer included
   STRICT_INFRA=1 node web/scripts/validate-infra.mjs   # the same, with every warning an error
   ```

   `validate-infra.mjs` checks the required fields, the vocabularies (type, status, units, `output.what`), the numeric
   years (1850 to next year), the date formats, that `k` ids and `s` exist, that ids are unique across the seven files,
   that coordinates are in range and near the stated country, and that no note holds a working phrase. A file that
   still has the old shape (a feature-level `y`) gives warnings, not errors, unless `STRICT_INFRA=1` is set.
6. `data/sources.json` feeds `DATA_SOURCES.md`; regenerate that table with `pipeline/common/sources_table.py` after
   changing the registry.

## What is not here

- No scheduled update. A job that rewrote this layer would overwrite hand-checked statuses and notes. Statuses that
  depend on events (damage, closures) are re-read by hand, and `statusAsOf` says how old each one is.
- No live data and no vessel positions.
- Pipeline lines are drawn by hand in a few points (a sketch for the map, not a survey). Replacing them with an open
  route dataset is a separate piece of work.
