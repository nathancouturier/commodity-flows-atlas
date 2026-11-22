# Data sources

Every figure in the atlas carries a source id (the `s` field), shown in the interface with its
year. The registry the site reads is `data/sources.json`; the table below is generated from it
(`python pipeline/common/sources_table.py`), so the two always agree. Licences and credits are
explained in `NOTICE.md`.

<!-- sources:start -->
<!-- Generated from data/sources.json by pipeline/common/sources_table.py. Do not edit by hand. -->

31 sources are registered. Every one is free to read.

Accounts and keys:
- `fred`: Free FRED API key, created by the project owner and stored as the GitHub secret FRED_API_KEY; without it the series is skipped.

| Id | Source | Licence | Cadence | How it is fetched | Used for |
|---|---|---|---|---|---|
| `naturalearth` | [Natural Earth Admin 0 Countries 1:50m](https://www.naturalearthdata.com/downloads/50m-cultural-vectors/), Natural Earth | Public domain (no credit required) | irregular | Zip from naciscdn.org, read once by pipeline/geo/build_countries.mjs; not refreshed by a workflow | Country shapes, borders, coastlines and the basemap |
| `usgs-mcs` | [USGS Mineral Commodity Summaries](https://pubs.usgs.gov/periodicals/mcs2026/), U.S. Geological Survey | Public domain (US Government) | annual (late January) | Data release (CSV) found through the ScienceBase search API, monthly check | Mine, refinery and smelter production and reserves of metals, minerals and fertilisers |
| `baci` | [CEPII BACI bilateral trade database](https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=37), CEPII | Etalab Open Licence 2.0 | annual (January) | One zip (about 2.4 GB) from cepii.fr, reduced by pipeline/trade/extract_baci.py to pipeline/cache/baci_flows.csv.gz (years from 2000). The monthly job downloads it only when a newer version exists; CEPII can refuse cloud runners, so the refresh is normally run locally | Flows, exports and imports, lanes (from 2005), route shares, 20-year history |
| `wb-pink` | [World Bank Commodity Price Data (Pink Sheet)](https://www.worldbank.org/en/research/commodity-markets), World Bank | CC BY 4.0 | monthly (2nd business day) | CMO-Historical-Data-Monthly.xlsx, weekly check | Monthly prices since 1960 |
| `fred` | [FRED, Federal Reserve Bank of St. Louis](https://fred.stlouisfed.org/), Federal Reserve Bank of St. Louis | Per series. The series used is a U.S. Bureau of Labor Statistics series: public domain, citation requested (Source: BLS via FRED). Other FRED series can be copyrighted | daily / monthly | FRED API (api.stlouisfed.org), needs a free API key stored as the FRED_API_KEY secret; without it the series is skipped | One series: US producer price index for deep-sea freight (BLS series PCU483111483111) |
| `usda-psd` | [USDA Production, Supply and Distribution (PSD)](https://apps.fas.usda.gov/psdonline/), USDA Foreign Agricultural Service | Public domain (US Government) | monthly (WASDE day) | psd_alldata_csv.zip, monthly | Grains, oilseeds, meals, vegetable oils, sugar, coffee, cotton: production, consumption, exports and imports |
| `portwatch` | [IMF PortWatch chokepoint transits (Atlas weekly averages of IMF PortWatch daily counts)](https://portwatch.imf.org/), IMF and University of Oxford | IMF terms of use for statistical data: attribution to the IMF, transformations stated, commercial reuse needs IMF permission; no Creative Commons licence stated. Credit: IMF PortWatch (IMF and University of Oxford), data adapted | weekly | ArcGIS feature service Daily_Chokepoints_Data, paged, weekly | Chokepoint transit counts and trade volume estimates since 2019, as weekly averages and a 28-day average |
| `nga-wpi` | [World Port Index (Pub. 150)](https://msi.nga.mil/Publications/WPI), US National Geospatial-Intelligence Agency | Public domain (US Government) | irregular | Not used: the server did not respond | Nothing; port coordinates come from UN/LOCODE through searoute |
| `baltic` | [Baltic Exchange route definitions](https://www.balticexchange.com/en/data-services/market-information0/indices.html), The Baltic Exchange | Route names and definitions are public facts; index values are proprietary and not shown; not affiliated with the Baltic Exchange | n/a | Web pages, read by hand | Names and definitions of the benchmark routes; no index value |
| `eurostat-searoute` | [SeaRoute maritime network (Eurostat), via the searoute Python package](https://github.com/genthalili/searoute-py), Eurostat (SeaRoute) / searoute-py | Package searoute-py: Apache 2.0. Eurostat SeaRoute network: EUPL 1.2, built on the Oak Ridge National Laboratory Global Shipping Lane Network (terms to be confirmed) | n/a | Python package searoute 1.6.0 (pip), which bundles the network | Sea-route geometry and distances |
| `atlas` | [Commodity Flows Atlas estimate (derived; see METHODOLOGY.md)](https://github.com/nathancouturier/commodity-flows-atlas/blob/main/METHODOLOGY.md), Commodity Flows Atlas | CC BY 4.0 (attribution: Commodity Flows Atlas) | rebuilt with each data refresh | Computed by the pipeline builders at each rebuild; method in METHODOLOGY.md | Route and chokepoint shares, vessel-class tonne-mile shares, laden days, lane and route geometry |
| `eia-chokepoints` | [World Oil Transit Chokepoints](https://www.eia.gov/international/analysis/special-topics/World_Oil_Transit_Chokepoints), U.S. Energy Information Administration | Public domain (US Government) | irregular (last updated 3 March 2026) | Web page, read by hand | Oil and LNG flows through chokepoints |
| `eia-tie` | [Today in Energy and STEO chokepoint articles](https://www.eia.gov/todayinenergy/detail.php?id=68485), U.S. Energy Information Administration | Public domain (US Government) | quarterly chokepoint updates | Web pages, read by hand | Oil and LNG flows through chokepoints |
| `pca-stats` | [Panama Canal Authority fiscal-year statistics and results](https://pancanal.com/en/panama-canal-maintains-operational-and-financial-strength/), Autoridad del Canal de Panama | No licence stated; facts cited with attribution (terms to be confirmed) | annual (fiscal year ends 30 Sep) | Web pages, read by hand | Panama Canal transits |
| `veson-baltic-defs` | [Baltic Exchange time-series/route definitions (Veson VesselsValue help)](https://help.veson.com/vesselsvalue/baltic-timeseries-definitions), Veson Nautical (summarising Baltic Exchange) | Public web page; facts cited (terms to be confirmed) | irregular | Web page, read by hand | Benchmark route definitions |
| `baltic-circulars` | [Baltic Exchange circulars and service pages (TD27, TD2/TD17/TC9 cessation, BLNG-174, BSI 63.5, C5TC 182)](https://www.balticexchange.com/en/data-services/Circulars/), The Baltic Exchange | Route names and definitions are public facts; index values are proprietary and not shown; not affiliated with the Baltic Exchange | as published | Web pages, read by hand | Benchmark route changes and cessations |
| `pca-vessel-requirements` | [Panama Canal vessel size limits (Panamax/Neopanamax)](https://pancanal.com/en/panama-canal-extends-maximum-length-overall-and-increases-draft-for-neopanamax-locks/), Panama Canal Authority (via PCA news release and Wikipedia Panamax) | No licence stated; facts cited with attribution (terms to be confirmed) | irregular | Web page, read by hand | Panama Canal vessel size limits |
| `sca-rules` | [Suez Canal transit limits (20.1 m draft, 1,006 m2 wetted area, 50 m beam)](https://www.eia.gov/todayinenergy/detail.php?id=18011), Suez Canal Authority (via Wikipedia Suezmax and EIA) | No licence stated; facts cited with attribution (terms to be confirmed) | irregular | Web page, read by hand | Suez Canal transit limits |
| `vessel-size-conventions` | [Conventional vessel class size ranges (industry convention, Baltic reference vessels, Wikipedia bulk carrier)](https://en.wikipedia.org/wiki/Bulk_carrier), Various | Industry convention; facts cited (Wikipedia text is CC BY-SA 4.0) | irregular | Web pages, read by hand | Vessel class size ranges |
| `simandou-news` | [First commercial shipment from Simandou departs for China](https://gmk.center/en/news/the-first-commercial-shipment-of-iron-ore-from-simandou-has-departed-for-china/), GMK Center / Caixin / Argus (press) | Press article; facts cited with a link (terms to be confirmed) | n/a | Web page, read by hand | One dated event: the first Simandou shipment |
| `eia-spot` | [EIA spot prices (petroleum and natural gas)](https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm), U.S. Energy Information Administration | Public domain (US Government) | weekly (daily data) | eia.gov/dnav/.../hist_xls/*.xls, weekly check | Daily Brent, WTI, Henry Hub, New York Harbor gasoline, ULSD and heating oil, US Gulf jet, Mont Belvieu propane |
| `eia-intl` | [EIA International Energy Data](https://www.eia.gov/international/data/world), U.S. Energy Information Administration | Public domain (US Government) | annual, partial monthly | Bulk file INTL.zip, monthly check | Production and consumption of crude, products, gas and coal; coal reserves |
| `faostat` | [FAOSTAT Crops and livestock products (QCL)](https://www.fao.org/faostat/en/data/QCL), Food and Agriculture Organization of the United Nations | CC BY 4.0 (FAO statistical database terms of use also apply) | annual | Bulk zip Production_Crops_Livestock_E_All_Data_(Normalized).zip, at most every 80 days (the API was unreachable) | Cocoa production |
| `wna` | [World Nuclear Association: World Uranium Mining Production](https://world-nuclear.org/information-library/nuclear-fuel-cycle/mining-of-uranium/world-uranium-mining-production), World Nuclear Association | Copyright World Nuclear Association; figures cited with attribution (terms to be confirmed) | annual | Web page, scraped, at most every 80 days | Uranium production by country |
| `company-reports` | [Company annual and production reports](https://www.vitol.com/), Individual companies | Per company; facts cited with a link (terms to be confirmed) | annual | Web pages, cited per entry (url) | Producers and traders: production and capacity figures |
| `trade-press` | [Trade press citing company data](https://www.reuters.com/markets/commodities/), Various | Press articles; facts cited with a link (terms to be confirmed) | continuous | Web pages, cited per entry (url) | Company figures not found in reports |
| `wikipedia` | [Wikipedia articles (infrastructure, companies, events)](https://en.wikipedia.org/), Wikimedia Foundation (text by Wikipedia contributors) | CC BY-SA 4.0 (adapted; each item links its article; see NOTICE.md) | continuous | Articles read by hand, cited per entry (url) | Infrastructure assets, companies, events and vessel and canal facts |
| `port-authorities` | [Port authority and government port statistics (Pilbara Ports, Queensland TMR, MPA Singapore, Port of Rotterdam, PCCA, Santos, Portos do Parana, RBCT via press)](https://www.pilbaraports.com.au/), various port authorities | No licence stated; statistics cited with attribution (terms to be confirmed) | annual | Web pages, cited per asset (url) | Port throughput |
| `giignl-2026` | [GIIGNL Annual Report 2026 (2025 data): liquefaction and regasification tables, market and project narrative](https://www.worldlngsummit.com/media/5stjrkng/2026-giignl-annual-report.pdf), GIIGNL (International Group of LNG Importers) | Public PDF, (c) GIIGNL; a few facts cited with attribution, nothing redistributed (terms to be confirmed) | Annual (2026 edition covers calendar 2025, with some 2026 events) | Public PDF report, read by hand | LNG liquefaction and regasification capacities |
| `eia-briefs` | [EIA Today in Energy: US LNG export capacity and project status (2026 items)](https://www.eia.gov/todayinenergy/), U.S. Energy Information Administration | US Government public domain | Continuous | Web pages, read by hand | US LNG export capacity and project status |
| `press-2026` | [2026 Gulf conflict status reporting (Bloomberg list via gCaptain, 11 Apr 2026; Cyprus Mail 12 Oct 2026)](https://gcaptain.com/heres-a-list-of-gulf-energy-infrastructure-damaged-in-iran-war/), Bloomberg / gCaptain / Cyprus Mail | Proprietary press; short facts cited with a link | Point-in-time (Apr and Oct 2026); status needs re-check | Web pages, read by hand | Status of Gulf energy infrastructure in 2026 |
<!-- sources:end -->

Sources read by hand (web pages, reports) are cited per figure or per asset with their own link; they
are not refreshed by a scheduled job.

## Sources considered and not used

- **Baltic Exchange indices** (BDI, BCI, TD3C rates and others): proprietary, not free.
- **UN Comtrade API**: free tier needs a key and has low limits. BACI already reconciles the same
  data.
- **Energy Institute Statistical Review**: free, but the download page blocks automated access
  (HTTP 403). EIA international data covers the same series.
- **NGA World Port Index**: the server returned HTTP 503, so it is registered (`nga-wpi`) but not used.
  Port coordinates use UN/LOCODE via `searoute`.
- **Global Energy Monitor trackers**: free, but the download is behind a form and its conditions are to be confirmed. Not used yet.

## Update schedule

Three scheduled workflows in `.github/workflows/` refresh the data (details in the "Data updates" section of the
README):

- `update-prices.yml`, weekly: World Bank Pink Sheet, EIA spot prices and, with the `FRED_API_KEY` secret, the FRED
  freight price index.
- `update-portwatch.yml`, weekly: IMF PortWatch chokepoint transits.
- `update-annual.yml`, monthly: USDA PSD, USGS, EIA INTL, FAOSTAT and WNA (at most every 80 days), CEPII BACI, and the
  rebuilds that depend on them. BACI is downloaded only when a newer version exists, and CEPII can refuse cloud
  runners: the BACI refresh is normally run locally (`python pipeline/annual/update_annual.py --only baci`) and the
  result in `pipeline/cache/` committed.

A failed source keeps its last good files. Sources read by hand (Baltic route definitions, canal authorities, port
authorities, company reports, press, GIIGNL, Wikipedia) have no schedule.
