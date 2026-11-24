# Infrastructure layer

`data/infrastructure/*.geojson` holds the mines, smelters, ports, storage hubs, oil and gas fields, refineries, LNG
terminals and pipelines that the atlas draws on the map and lists on commodity and country pages.

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
| `storage.geojson` | `storage` (an inland or coastal storage hub that is not a port: Cushing, Mont Belvieu) |

The source ids these files use (`wikipedia`, `giignl-2026`, `eia-refinery-capacity`, `eia-dpr`, `eia-todayinenergy`, `operator-reports`, `port-authorities`,
`trade-press`, `usgs-myb`, `portwatch-ports`, `eia-storage-capacity`) are registered in `data/sources.json`, which is the one list of sources: the site reads it and
`DATA_SOURCES.md` is generated from it. There is no other source list in this folder. Three more ids register the
sources of a few coordinates and statuses that a note names: `openstreetmap` (ODbL; points looked up through Nominatim),
`wikidata` (CC0) and `norwegian-offshore-directorate` (its licence page could not be read, and the registry says
"terms not read"). The ids that stand for many publishers (`operator-reports`, `trade-press`, `port-authorities`)
link to this README: the page that was read is linked on each asset (its `url`).
`usgs-myb` stands for the USGS Minerals Yearbook area reports: the capacities of its table "Structure of the mineral
industry" are entered with `basis not stated` in `n`, because neither the heading nor the footnotes of any report read says
whether a capacity is the facility's total or an owner's share. A feature's `s` and `url` name the page that carries its
figures; what another page supplies (operator, status, a production figure) is named in `note` or in that figure's `n`.

## Properties of a feature

| Field | Type | Meaning |
|---|---|---|
| `id`, `name`, `type`, `c` | text | Never rename an id or delete a feature: routes, events and the trade engine refer to ids. `c` is the ISO3 code of the country. An asset is identified by its `type` and its `id` together (`type:id` is unique across the eight files; the page of an asset is `sel=infra:<id>:<type>`), so a refinery and a port may both be `ras-tanura`. |
| `k` | list of commodity ids | The commodities the asset handles, the main one first. Only ids of `data/commodities/index.json`. |
| `cs` | list of ISO3 | Pipelines: every country crossed, in order. |
| `operator` | text | Operator and owners as the source states them. |
| `opened` | number | Year of first operation. |
| `capacity` | `{v, u, y?, n?, orig?, planned?}` | Nameplate or design capacity only: what the asset can do per year or per day. `y` is the year the statement refers to, left out when the source does not say (the site then prints the year the page was read: "Wikipedia · read 2026"). `planned: true` marks a planned or target capacity that the asset has not reached (a capacity "after ramp-up", "at full production", a target for a later year): the asset page says "Planned capacity" and the lists rank it with the planned and under-construction assets, not with operating ones. |
| `output` | `{v, u, y, what, n?, orig?}` | A dated, measured figure. `what` is `production`, `exports` or `throughput` (port traffic, pipeline flow). `y` is required and is a number; a fiscal year takes the calendar year in which it ends, with the label in `n` ("FY2024-25"). |
| `status` | text | One of the values below. Required on every feature. |
| `statusAsOf` | `"YYYY"` or `"YYYY-MM"` | When the status was true according to the page read. Required unless the status is `not-stated`. |
| `statusNote` | text | Optional short reason a reader sees next to the status ("drone strike on 14 March 2026, two units shut"). A reason only: a remark about the source goes in `capacity.n` or `note`. |
| `s`, `url` | source id, page | `s` is an id of `data/sources.json`; `url` is the page that supports the figures of this feature. |
| `read` | `"YYYY-MM"` | The month the page was read. It is shown once, in the source line, and never as the year of a figure. There is no feature-level `y`. |
| `coord` | `"site"` or `"approx"` | See below. |
| `note` | text | Reader-facing text only: no working notes ("via search summary", "figures were stripped", "latest on page"). |
| `product`, `length_km` | text, number | Pipelines: what they carry and their length. The site shows both. |
| `locode` | text | Ports: the code of the place in the trade engine (`pipeline/freight/ports.py`, the key of its table): the UN/LOCODE without its space ("RUPRI"), or the engine's own code for a terminal that has none. A route port, a lane port and the asset are then one place: the route page links the port to the asset, the asset page lists the lanes of its code, and the search finds the place as the asset. Where the engine does not know the place, the UN/LOCODE of the PortWatch database. |
| `portwatch` | text | Ports: the IMF PortWatch port id ("port1020"), for a later join with PortWatch's port traffic. |
| `limits` | `{draught?, loa?, beam?, dwt?, depth?, seg?, cls?, at?, n, s, url, y?}` | Ports: what a page states as the largest ship or the deepest berth, in metres (draught, length overall, beam) and deadweight tonnes. `n` says which berth or channel and at which tide when stated, `s` and `url` the page, `y` the year of the statement when the page gives one. At least one of the four figures. A water depth is entered as `draught` with `depth: true` and `n` saying "depth" (the page then labels it "Depth"). Only the page's maximum is entered: a stated minimum (the least depth of a channel) is never a limit. `seg` (`dry`, `tanker` or `gas`) when the page states the limits for one kind of berth (an oil berth of a port that also loads grain); `cls`, a class id of `data/freight/vessel-classes.json`, when the page itself names the class the berths take ("for Capesize ships"); `at`, a short name of the berth or terminal when the limits are not the whole port's ("Jurong Port bulk berths"), shown on each tile. |
| `maxClass` | `{dry?, tanker?, gas?, n}`; each segment is `{classes: [{id, orLarger?, by, basis}]}` | Ports: the class of the atlas that each segment of the port can take by its `limits`, written by `pipeline/infrastructure/port_limits.py` (never by hand). An Atlas estimate, shown as "largest class by the published limits; derived by the atlas"; `n` gives the method. Two rules. **By deadweight**: the class whose size band (`size.min` to `size.max` of `pipeline/freight/vessel_classes.json`, in dwt) holds the deadweight limit, the upper edge in and the lower edge out; above the band of the largest class of the segment it is that class "or larger" (`orLarger`); not above the smallest band, no class at all. Where bands overlap (Newcastlemax across Capesize and VLOC; Aframax and LR2 on one band) the widest band is the class, so Newcastlemax is never chosen and, on a tie, the class listed first stands. A class measured in cbm or TEU has no deadweight band. **By dimensions**: when the page gives a draught, a length or a beam (a water depth, `depth`, counts only as an upper bound of the draught), the largest class of the segment whose standard vessel (`std`) is no larger in every one of those dimensions that both give; a class whose standard vessel has none of them is not compared and `n` names it. Both rules give the same class, or only one applies: one entry, with its basis (`by` "By deadweight", "By the 14 m draught", `basis` one sentence). They disagree: two entries and no single class (Taman: VLOC by deadweight, Ultramax by the 14 m draught). A class named by the page (`limits.cls`) overrides; `limits.seg` restricts the segment; no class from a depth or a draught alone (the page must give a deadweight, a length or a beam). |
| `prices` | list of ids | The price series of `data/prices/index.json` quoted at this place (Cushing: WTI), whatever their basis (FOB, CIF or spot at a hub): the page lists them under "Price series quoted at this place". |

`n` says in a few words what a figure counts ("iron ore", "copper in concentrate", "refined copper (cathode)",
"total cargo", "100% basis", "phase 1 of 2"). When a figure was converted, `orig` keeps the source's own figure and
unit ("1 billion lb Cu/y") and `v` is rounded to the precision of the original. The site prints `v u` and shows `orig`
beside it.

One basis per figure of a commodity. A figure is on a 100% basis: where a page gives an owner's share and the percentage, `v`
holds the 100% figure (the share divided by the percentage), `orig` keeps the reported share ("129,026 kt at BHP interest
85%") and `n` says "100% basis computed from BHP's 85% share". Where only a share is known, or the page does not say which
basis it uses, keep the figure and write "share only" or "basis not stated" in `n`: the lists rank such figures apart,
under "share or basis not stated", not with 100% figures. US "tons" are converted to tonnes (x 0.9072) only where a page of
the publisher or of the EIA says its figure is in short tons (`n` names that page), with the reported figure in `orig`;
otherwise the figure stays as reported and `n` says "tons as reported".

A figure that is the production, exports or traffic of a year goes in `output`, not in `capacity`. A feature may have
both. When the source does not let you tell which one a figure is, keep it as `capacity` without `y` and write "as
stated by the source" in `n`.

## Units

`capacity.u` and `output.u` take one of these eight values, nothing else:

| Unit | Used for | Conversion from the usual source units |
|---|---|---|
| `kb/d` | crude oil and products: fields, refineries, oil pipelines, oil terminals | 1 mb/d = 1,000 kb/d |
| `bcm/y` | natural gas: fields, gas pipelines | Bcf/d x 10.34 = bcm/y; MMcf/d x 0.01034 = bcm/y |
| `Mtpa` | LNG liquefaction and regasification (the `type` says which) | |
| `Mt/y` | ore, coal, bauxite, potash, concentrate, port cargo | million short tons x 0.9072 = Mt |
| `kt/y` | metal contained or refined metal, spodumene and other small concentrates | billion lb x 453.6 = kt; Mt x 1,000 = kt |
| `t/y` | gold, silver, platinum-group metals | koz x 0.0311 = t |
| `tU/y` | uranium | Mlb U3O8 x 384.6 = tU; t U3O8 x 0.848 = tU |
| `Mb` | storage capacity of crude oil, products and liquefied gases (a stock, not a flow): storage hubs and port tank farms | thousand barrels / 1,000 = Mb; `n` says working or shell capacity |

The site ranks assets of a commodity page only among figures of the same kind (capacity with capacity, production with
production), the same unit, the same commodity and the same form (ore, concentrate, metal), planned and under-construction
assets apart (a capacity flagged `planned` counts as planned), and figures of an unknown or partial basis apart. A figure that does not fit one of these units is not entered until the vocabulary is extended here, in
`web/scripts/validate-infra.mjs` and in `web/src/lib/capacity.ts`.

## Status

| Status | Use it when |
|---|---|
| `operating` | A dated page says the asset runs. The month the page was read is its date when the page describes the asset as running today. An asset that runs at a reduced rate after damage is `operating`, and `statusNote` says so ("operating at 80% after an attack"). |
| `damaged` | The asset is shut, or a substantial part of it is shut, because of damage (an attack, a fire, a storm) at the date given. A page that reports damage without saying that anything stopped does not make it `damaged`. |
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
asset is drawn as operating, unless it was not open yet. `opened` is filled in from the article or report the asset
already cites, where it gives a start year. An asset without `opened` (the oil and gas basins, most ports and
smelters, and the assets whose page gives no start year) stays drawn as open at every year of the History timeline:
the atlas does not guess a year.

## Coordinates

`coord` is `site` when the point is the asset itself, and `approx` when it is a town, a centroid or a schematic
position. The
site prints "Approximate location" on those assets. A port is `site` only when it is one terminal (one loading or
discharging installation of one operator: an oil or bulk terminal, an island terminal, a mooring) and the point stands
on it. A port of several terminals, berths of several operators or port areas shown as one point is `approx`, whatever
the source of the point: a database point (the port's point in the IMF PortWatch ports database, or a town in
OpenStreetMap) stands for the whole port, not for a berth. A point is checked against the country `c`: it must lie inside the
country's polygon or within 60 km of it. A field, an LNG terminal or a port may stand at sea (an offshore field, a
floating plant such as Prelude, an island terminal such as Das Island or Halul Island, an offshore port such as LOOP):
it may lie up to 370 km (200 nautical miles) from `c`, provided no other country is nearer to the point, so a point in
the wrong country is still caught.

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
   node web/scripts/validate-infra.test.mjs       # the tests of the validator
   ```

   `validate-infra.mjs` checks the required fields, the vocabularies (type, status, units, `output.what`), the numeric
   years (1800 to next year), the date formats, that `k` ids and `s` exist, that ids are unique across the eight files,
   that coordinates are in range and near the stated country, that `coord` is given, that a pipeline has `cs` starting with
   its country, that a feature sits in the file of its type and uses a unit that fits it (refinery kb/d, LNG Mtpa, ...), that a
   `not-stated` status has no `statusAsOf`, that `planned` is `true` on a capacity only, that a port's `locode`,
   `portwatch`, `limits`, `maxClass` and `prices` have their shape (a class id of `data/freight/vessel-classes.json`, a
   price id of `data/prices/index.json`), and that no note, status note or `n`
   holds a working phrase ("via search summary", "could not be re-read"). Every finding is
   an error. Only `INFRA_OLD_SHAPE=1` turns the findings about a file that still has the old shape (a feature-level `y`)
   into warnings, for a migration that goes one file at a time.
6. `data/sources.json` feeds `DATA_SOURCES.md`; regenerate that table with `pipeline/common/sources_table.py` after
   changing the registry.
7. After changing a port's `limits`, or after a change of the standard vessels (`std`) or typical sizes
   (`size.typical`) of `pipeline/freight/vessel_classes.json`, run `python pipeline/infrastructure/port_limits.py`: it
   rewrites `maxClass`.
8. A port's commodities `k` rest on a page: the page of its `url`, or an article named in `note` ("Commodity:
   Wikipedia, Ras Tanura (the Ju'aymah crude terminal)"), or a route or a lane of the atlas that uses the port for that
   cargo (said in `note`). A database that gives a position (PortWatch, OpenStreetMap) states no cargo. A port whose
   cargo no page read states is not added.

## Ports and the freight routes

Most ports that the routes of `pipeline/freight/routes_def.json` name are assets; `route_assets.py` lists those that are
not (Boke, Guinea, names the river terminals of the Boke region rather than one port). `pipeline/infrastructure/route_assets.py` finds the asset of
each route port (same country, same name, or a name of its `ALIAS` table, which also holds the trade engine's spellings
that the generated routes use: "Pusan" is Busan); `build_freight.py` publishes it on each route (`from.assets`,
`to.assets`, "type:id" or null) and the route page links the port to its page. A port of a generated route that is not
an asset is a port of the lane index (`data/freight/ports.json`): the route page links it to the largest lane through it
of a customs group the route carries (a steel route never opens a coal lane; the index row lists the five largest lanes of
the port), or to the asset its index row names; a port in neither, or with no such lane, stays plain text. The search
still opens the largest lane through the port, whatever its commodity. No asset is added for a route port alone. Run `python pipeline/infrastructure/route_assets.py`
to list the route ports, of the hand-written and of the generated routes (the published `data/freight/routes.json`),
that are not assets. The index row of a port that is an asset lists in `aka` the other names the engine and the routes
give it, for the search.

Positions and UN/LOCODEs come from the IMF PortWatch ports database (`pipeline/cache/portwatch_ports.csv`, downloaded
once by `pipeline/infrastructure/fetch_portwatch_ports.py`; IMF terms, credited in NOTICE.md); a port that PortWatch
does not list takes its position from OpenStreetMap or from the Wikipedia article of the terminal, and its note says
which. The NGA World Port Index, which would give the limits of most ports, could not be downloaded (HTTP 503 in
November 2026); the limits of a port come from the page its `limits.url` names.

## What is not here

- No scheduled update. A job that rewrote this layer would overwrite hand-checked statuses and notes. Statuses that
  depend on events (damage, closures) are re-read by hand, and `statusAsOf` says how old each one is.
- No live data and no vessel positions.
- Pipeline lines are drawn by hand in a few points (a sketch for the map, not a survey). Replacing them with an open
  route dataset is a separate piece of work.
