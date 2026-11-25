# Changelog

What a visitor sees changed on the site, release by release, newest first. The weekly and monthly data updates are not
releases: the About window's "What changed" lists them. The full account of each release is in
[`PROGRESS.md`](PROGRESS.md).

## Release 9 (2026-11-26)

### Added
- Port pages: a block "Weekly port traffic" on the 163 ports that IMF PortWatch counts and the atlas could pair with
  it. It draws the weekly series since 2019 by ship type (tanker, dry bulk, container, other) for port calls and for
  PortWatch's estimates of the tonnes exported and imported, gives the last 52 weeks beside the 52 before, and offers
  the series as a CSV. The block names PortWatch's own port where its name differs, and prints PortWatch's own
  warning that ships can switch their transponder off; some series read very low (2 calls in a year at Odesa), and the atlas
  cannot say why.
- The About window credits IMF PortWatch for the port series, says what its weekly sums are, and lists the series
  among the sources read every week.

### Changed
- The eight daily prices from the EIA (Brent, WTI, Henry Hub, New York Harbor gasoline, diesel and heating oil, US
  Gulf Coast jet fuel, Mont Belvieu propane) are credited "EIA (source: Refinitiv)": the EIA's own pages give
  Refinitiv as their source. They are no longer offered as CSV files, because no page read says whether they may
  be redistributed; their charts are unchanged, and the monthly World Bank series keep their download.

## Release 8 (2026-11-25)

### Added
- A voyage calculator on the route pages (259 of the 301 routes: the laden voyages). From the hire, the freight, the
  bunker price and the port figures a visitor types, it gives the days and the fuel of the voyage, the freight that
  covers the hire and the time-charter equivalent of the freight. It starts from the cargo size, the distance and the
  standard vessel the atlas already shows, prints no market rate, and keeps nothing that is typed.
- Port pages: a block "World Port Index" on 138 of the 190 ports, with the depths, the largest vessel, the harbour, the
  tidal range and the pilotage that Publication 150 of the US National Geospatial-Intelligence Agency gives, beside the
  limits of the page each port cites.
- "Report an error" on every page: a button that opens a form on GitHub, filled in with the address of the page.
- The About window shows the release with a link to these notes, and a new tab, "Quality", shows which blocks each of
  the 51 commodity pages holds (362 of the 448 that apply). A commodity page lists the blocks that cannot apply to it,
  with the reason.

## Release 7 (2026-11-25)

### Added
- Metallurgical coal: the Main flows are now 63 flows of 2024 by pair of countries from the exporters' own statistics
  (31 from Queensland's coal sales, 32 from the EIA's exports of the United States), each row with its source.
- Tin: the flow of tin ores from Myanmar to China, which customs data almost miss, is added from China's own import
  declaration (UN Comtrade) for 2017 to 2024 (76.5 kt in 2024), with a table of China's declared imports by origin.
- LNG: cross-check tables of the exports of Australia and of the United States in their own statistics for 2024 (81.2
  and 90.9 Mt, against 78.7 and 73.3 Mt in customs data), and of Australia's exports by market.
- Steel: the world total cited from worldsteel is the later one, 1,848.9 Mt for 2025.

### Changed
- LPG from the United States to Mexico, 2021 to 2024: the customs tonnage looks too high against the United States' own
  statistics, so each year shows an Atlas estimate computed from the volume (4.94, 5.31, 5.06 and 5.28 Mt), with the
  customs figure beside it. For 2024 the lane is the 3.81 Mt that left by vessel (72%). The world LPG tables, the
  pages of the United States and Mexico, the passage estimates and ten LPG routes move with it.
- A route or a main lane of the last release stays while its corridor or pair is in the data.
- Search: "sulfate" and "sulphate" open the same pages. The key figure of an annual price carries its year. The
  Singapore Strait page no longer cites IMF PortWatch, which has no counter there.

### Corrected
- The parts of an estimated share are each rounded from their own value (LPG lanes: 4.2% of the 2024 seaborne tonnage
  is an Atlas estimate, 2.9% from a volume and 1.2% from the declared value).
- Notes that denied lanes the pages have (tin and lead) are gone.

## Release 6 (2026-11-24)

### Added
- Twelve commodity pages. Fertilisers and sulphur: ammonia, ammonium nitrate, UAN, ammonium sulphate, MAP,
  superphosphates, phosphoric acid and potassium sulphate on the existing pages, and new pages for Sulphur and NPK
  fertilisers. Barley, Sorghum, Sunflower and Pulses. Ferrous scrap, Pig iron & DRI, Chromium, Ferro-alloys, Molybdenum
  and Graphite. Each product has its exporters and importers, most have sea lanes (Molybdenum, Graphite and the other
  ferro-alloys have none yet), and the largest have a generated route.
- Ten annual USGS prices (chromite ore, ferro-chromium, ferrosilicon, heavy melting scrap, molybdenum, three kinds of
  natural graphite, sulphur and ammonia). Barley and sorghum, whose monthly series stopped in August 2020, continue
  with the World Bank's annual average.
- 48 more generated routes (168 in all) and 368 more estimates of the shares that cross passages (967 in all, at 20
  passages), with the comparison with IMF PortWatch printed once per ship type.
- Search finds trade names and abbreviations (DRI, HMS, FeCr, SiMn, AN, UAN, MAP, SOP, canola oil).

### Changed
- France has two seaboards for grain, oilseeds and meal (Rouen or La Pallice, and Fos for the Mediterranean and the
  Black Sea); Rouen and Bremen carry a river leg. A pair that is most of a landlocked buyer's imports carries a caveat
  that the cargo probably ends elsewhere.
- A cargo chip names the product when its page holds several. A page for an address that does not exist offers a way
  back.

### Corrected
- Mozambique's "coke" (1.63 Mt in 2024) is left out of the coke tables: the EIA series gives it no coke production.
- A table that holds less than 97% of the customs file says so and names the cause.

## Release 5 (2026-11-24)

### Added
- Baltic benchmark routes: 30 more routes (90 in all, 85 active and 5 ended), each compared with the Baltic Exchange's
  Guide to Market Benchmarks (version 7.09). Each has a definition table (vessel, cargo and quantity, load and
  discharge, index, status and document); an ended route says when it ended and links to its successor.
- Vessel classes: a chemical tanker class for vegetable oils (20 classes in all); 14 classes show a standard vessel
  with its source and year, and 16 classes show the world fleet of their ship type from UNCTADstat (ships, deadweight,
  average age).
- 154 more ports (190 in all) and a new type, storage hub (Cushing, Mont Belvieu). 20 ports have published limits, and
  a largest vessel class where a page gives a dimension of a ship.
- Companies: 156 more entries (403 for 269 companies in all), and 85 more figures dated from the company's own report
  or filing (88 in all); 32 shipping companies on the class pages. Companies are in the search, and a company links to
  the assets it operates.
- Two long freight indicators, each labelled "not a freight rate": the Dallas Fed index of global real economic
  activity and the New York Fed Global Supply Chain Pressure Index.

### Changed
- Several benchmark routes had the wrong ports: they are corrected, and no line crosses land where one did.
- The US freight series is named for what it is, a producer price index of the BLS.
- Size bands of a segment no longer overlap or leave a hole; a lane or a route that shows a class says "typical".
- No ocean freight rate in USD per tonne is published: the free USDA datasets credit a private firm and carry no
  licence, so the four grain routes link to them. Each route page says that Baltic values are proprietary.

## Release 4 (2026-11-23)

### Added
- A page for each country and territory of the index and for the European Union, built from the full tables: every line
  a country has, with its rank, its share and its series by year, the largest exports of all goods, net position,
  customers and suppliers, and a freight block with typical ports and the share of its seaborne trade that crosses each
  passage. The European Union page lists its members.
- A search field over commodities, countries, routes, chokepoints, vessel classes, assets, ports, events and price
  series; CSV downloads on tables, flows, price selections and series, each row with its source and licence; Copy link
  and Copy citation on every page.
- 33 more events (80 in all), each text read against the page it cites, with an events section on the pages they
  concern.
- Energy: monthly crude production by producer, OECD imports by origin, petroleum stocks with days of cover and oil
  demand by month. Agriculture: USDA's 2026/27 forecast beside its 2025/26 estimate and a balance per crop. Metals:
  apparent consumption of refined copper, primary aluminium and crude steel (Atlas estimates) and US net import
  reliance.
- Sea lanes for eight more customs groups: lead, zinc, tin, cobalt, lithium and rare earths among them.

### Changed
- One order for every commodity page: key figures, price and alerts; the core tables open; main flows and seaborne
  lanes; every other block folded to one line. Pages are much shorter.
- Gold, silver and platinum-group metals are not drawn, since they move mostly by air, and the map says so.
- A month without a figure in a source file shows as "no figure", never as zero.

## Release 3 (2026-11-23)

### Added
- Every country in every table: the first 10 rows, a line "Rest of world" so that shares add up to 100%, and "Show
  all". The map colours every country that has a value.
- History by country and year behind the tables, with a History year that tables and country colours follow, a trend
  line on each row and the world total by year. A block of the largest changes between two years.
- Prices: many more series (World Bank columns and indices, annual real prices behind a "Real prices" switch, annual
  USGS prices), a price board with changes over a week, a month, three months, the year and one year, the latest
  price on each commodity page, and spreads and ratios. What each price measures, and the dates its basis changed, are
  drawn on the chart.
- Atlas corridors generated from the table of recorded pairs, so that steel, manganese, alumina, sugar, rice and
  rapeseed have routes; a chokepoint status board with transits and estimated tonnes against the 2023 average.
- Alert banners follow the data (severity from IMF PortWatch transits), and events are linked to commodities, countries
  and assets. "What changed" and the publication calendar of the sources are in the About window, with an Atom feed.
- Infrastructure: many more refineries, fields, LNG import terminals, pipelines, mines and smelters, each with a
  status where a page gives one.

### Changed
- A year without a figure is never read as zero; a figure far out of line with the years around it is shown in the
  note, with its source, and is not ranked.

## Release 2 (2026-11-23)

### Added
- A rule that decides, for every recorded pair of countries, whether it goes by sea, by land or both. Mixed pairs are
  drawn dashed and stay out of seaborne totals. Main lanes are chosen from the latest year; the rest is listed per
  exporter as "Other destinations".
- A table of every recorded pair with its mode, ports, class, distance and passages, which the Route finder answers
  from; it says plainly when a flow is overland, mixed, not routed or not recorded.
- Typical ports given per cargo family, role and coast, each with the basis the reader can see.
- Chokepoint shares as "at least" and "up to", capped by IMF PortWatch volume where it applies.
- A lane page with ports, sources, coast options, passages and alternatives, and a sortable lane table with a CSV
  download.
- Infrastructure on a new schema: nameplate capacity apart from dated production or throughput, each figure with its
  own year, and a status on every asset (operating, damaged, suspended, or "not stated"). History mode dims an asset
  that was not yet open in the selected year.

### Changed
- Natural gas is ranked on EIA volumes in bcm; LNG shows the GIIGNL world total beside the customs total. Crude oil,
  gas and LNG key figures carry a second unit, labelled "Atlas conversion" with its factor.
- Gold, silver and PGM are shown in fine-metal equivalent, with the customs gross weight beside it.

### Corrected
- Wrong ports were replaced (food no longer lands at oil terminals; Libyan crude at Ras Lanuf, Indonesian coal at
  Tanjung Bara), and Iranian crude moved out of "Other Asia".
- Isolated unit-value anomalies of bulk cargoes are re-estimated from the declared value and labelled "Atlas estimate".

## Release 1 (2026-11-22)

- The first public release: the map of physical flows and freight, the commodity, country and chokepoint pages with
  vessels and tonnes for the passages IMF PortWatch covers, the price explorer, History with events to 2026, links, tab
  titles and keyboard use, an About window with sources and licences, and layouts for phones and tablets.
