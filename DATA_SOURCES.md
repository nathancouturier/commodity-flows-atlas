# Data sources

Every figure in the atlas carries a source id (the `s` field), shown in the interface with its
year. The registry the site reads is `data/sources.json`. All sources below are free. None needs
an account or an API key.

| Id | Source | Licence | Cadence | How it is fetched | Used for |
|---|---|---|---|---|---|
| `baci` | CEPII BACI, HS92 bilateral trade (1995–2024) | Etalab Open Licence 2.0 | yearly (January) | One zip (~2.4 GB) from cepii.fr, filtered to ~45 HS groups by `pipeline/trade/extract_baci.py` | Flows, exports and imports, lanes, route shares, 20-year history |
| `usgs-mcs` | USGS Mineral Commodity Summaries 2026 data release | Public domain | yearly (late January) | CSV from ScienceBase | Mine, refinery and smelter production and reserves for metals, minerals and fertilisers |
| `eia-intl` | EIA International Energy Data (bulk `INTL.zip`) | Public domain | yearly, part monthly | `https://www.eia.gov/opendata/bulk/INTL.zip` | Crude, refined products, gas and coal (including metallurgical coal) production, consumption and reserves |
| `usda-psd` | USDA FAS Production, Supply and Distribution | Public domain | monthly (WASDE day) | `psd_alldata_csv.zip` | Grains, oilseeds, meals, vegetable oils, sugar, coffee, cotton: production, consumption, exports and imports by marketing year |
| `faostat` | FAOSTAT crop production | CC BY 4.0 | yearly | FAOSTAT API | Cocoa production |
| `wna` | World Nuclear Association, World Uranium Mining Production | Free to read, facts cited | yearly | Web page | Uranium production by country |
| `wb-pink` | World Bank Commodity Price Data (Pink Sheet) | CC BY 4.0 | monthly (early in month) | `CMO-Historical-Data-Monthly.xlsx` | Monthly prices since 1960 |
| `eia-spot` | EIA petroleum and natural gas spot prices | Public domain | weekly (daily data) | `eia.gov/dnav/.../hist_xls/*.xls` | Daily Brent, WTI, Henry Hub, NY Harbor gasoline, ULSD and heating oil, US Gulf jet, Mont Belvieu propane |
| `portwatch` | IMF PortWatch daily chokepoint transits | CC BY 4.0 (IMF PortWatch) | weekly | ArcGIS feature service, paged | Chokepoint traffic by vessel type since 2019 |
| `eia-chokepoints`, `eia-tie` | EIA World Oil Transit Chokepoints; EIA Today in Energy | Public domain | irregular | Web pages | Oil and LNG flows through chokepoints |
| `pca-stats` | Panama Canal Authority statistics | Public, facts cited | yearly (fiscal year) | Web pages | Panama transits |
| `baltic`, `baltic-circulars`, `veson-baltic-defs` | Baltic Exchange route definitions, circulars and summaries | Definitions public; **index values proprietary and not shown** | as published | Web pages | Benchmark route definitions |
| `vessel-size-conventions` and similar | Industry conventions, canal authorities | Facts cited | n/a | Web pages | Vessel class sizes and limits |
| `naturalearth` | Natural Earth Admin 0 countries 1:50m | Public domain | irregular | Zip from naciscdn.org | Country shapes, borders, coastlines |
| `eurostat-searoute` | Eurostat SeaRoute network via the `searoute` package | EUPL 1.2 / Apache 2.0 | n/a | Python package | Sea-route geometry and distances |
| `gem-wiki`, `company-reports`, `wikipedia`, `operator-reports`, `giignl-*` | Global Energy Monitor wiki, company annual reports, Wikipedia, GIIGNL | CC BY 4.0 / CC BY-SA / facts cited | yearly | Web pages, cited per asset (`url`) | Infrastructure: mines, fields, refineries, LNG terminals, pipelines, smelters, ports |
| `atlas` | Commodity Flows Atlas estimates | MIT | each rebuild | Derived; see METHODOLOGY.md | Route and chokepoint shares, vessel-class tonne-mile shares |

## Sources considered and not used

- **Baltic Exchange indices** (BDI, BCI, TD3C rates and others): proprietary, not free.
- **UN Comtrade API**: free tier needs a key and has low limits. BACI already reconciles the same
  data.
- **Energy Institute Statistical Review**: free, but the download page blocks automated access
  (HTTP 403). EIA international data covers the same series.
- **FRED**: free, but it did not respond from the build machine. EIA provides the underlying
  spot series directly.
- **NGA World Port Index**: the server returned HTTP 503. Port coordinates use UN/LOCODE via
  `searoute`.

## Update schedule

See `.github/workflows/` and the "Data updates" section of the README. Each source has its own job
and cadence. A failed source keeps its last good files.
