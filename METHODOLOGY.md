# Methodology

How the atlas turns public statistics into flows, lanes, routes and shares. Figures computed by
the atlas (rather than copied from a publisher) are labelled **"Atlas estimate"** in the interface
and carry the source id `atlas`.

## 1. Bilateral trade flows

- **Source**: CEPII BACI, HS 1992 version (1995–2024), which reconciles exporter and importer
  declarations from UN Comtrade. Quantities are metric tonnes, values thousand USD.
- **Commodity groups**: HS six-digit codes are grouped per commodity in
  `pipeline/trade/hs_map.py` (e.g. coal = 2701.11 + 2701.12 + 2701.19).
- **Known limits of customs data**
  - HS codes do not separate thermal from metallurgical coal; the coal lanes cover both.
    Metallurgical coal production and trade by country come from EIA, which does split them.
  - HS 1992 has a single code for all refined petroleum products (2710.00).
  - Copper concentrate tonnage is reported inconsistently (gross weight or copper content).
  - Origins are as declared. For example, sanctioned Iranian or Venezuelan crude often appears
    under a transhipment origin such as Malaysia.
- **Cleaning rules** (`pipeline/trade/clean.py`, shared by every builder so lanes, rankings and
  flows agree):
  - BACI reports Taiwan as "S19" (Other Asia, n.e.s.); it is mapped to TWN.
  - Missing tonnage with a value: tonnage = value ÷ median unit value of the group and year.
  - Gross unit errors (unit value below 1/100 or above 100× the median, any size) are re-estimated
    the same way. Example: rare earths Turkey → Benin.
  - Moderate inconsistencies (unit value below 1/3 or above 3× the median, flows over USD 50
    million) are re-estimated only for homogeneous goods (crude, products, LNG, LPG, grains,
    oilseeds, softs, fertilisers). Ore and concentrate groups keep the reported tonnage, because
    their grades range from about USD 40/t (laterite nickel ore) to over USD 2,000/t (sulphide
    concentrate).
  - Known misclassifications are dropped. Example: Israeli pipeline gas to Egypt declared as LNG.
  - Re-estimated flows are flagged "tonnage estimated from value".
  - In history series, isolated one-year spikes or dips are removed and noted on the chart. A
    removed point is below 35% or above 2.8× both neighbouring years. Sustained changes are kept:
    China's 2021–22 ban on Australian coal, for example, spans two years.
- **Known reporting gaps** are flagged on the affected lanes. Since 2019, Iranian crude to China
  is mostly declared under other origins or not recorded, and sanctioned Venezuelan crude often
  is too.
- **Pipeline gas tonnage** in customs data is often estimated from value. North American flows
  (Canada → US, US → Mexico) are understated about fivefold, so EIA bcm figures are used for
  production and consumption.

## 2. Seaborne or overland

A flow counts as seaborne when both countries have an ocean coastline and they do not share a
land border. Exceptions:

- Neighbours that trade mainly by sea (e.g. Indonesia–Malaysia, Argentina–Brazil, USA–Mexico) are
  listed in `SEA_NEIGHBOURS` in `pipeline/freight/build_lanes.py`.
- Landlocked producers with a recognised sea outlet: Kazakh crude via the CPC terminal at
  Novorossiysk, Azerbaijani crude via Ceyhan, Zambian copper via Dar es Salaam, Belarusian potash
  via Russian Baltic ports, Paraguayan soy via the Paraná river ports.
- Caspian coastlines do not count as ocean access.

Coastlines and land borders come from the Natural Earth country topology: an arc shared by two
countries is a border, an arc used by one country is coast.

Neighbours that trade partly by sea and partly by pipeline or rail (for example Russia–China crude
and coal) are left out of seaborne totals, because customs data cannot split them. Seaborne totals
are therefore slightly understated for those pairs.

## 3. Lanes and routes

- **Gateway ports**: every country has a main port per cargo segment (ore, coal, grain, crude,
  products, LNG, LPG, vegetable oils, fertiliser, containers). These are set in
  `pipeline/freight/ports.py`. Port coordinates come from the UN/LOCODE list bundled with the
  `searoute` package, with a few terminals added by hand.
- **Geometry**: shortest sea path on Eurostat's SeaRoute maritime network, using the `searoute`
  package. The Northwest Passage is excluded.
- **Canal limits**: classes that cannot transit laden are routed around the canal.
  - Panama: VLCC, Suezmax, Capesize, Newcastlemax and VLOC. Neopanamax locks allow 51.25 m beam
    and 15.24 m draft.
  - Suez: VLCC and VLOC. Draft is limited to 20.1 m.
- **Multi-coast exporters**: Russian cargoes load where the trade really goes.
  - Coal: Vostochny for Asia, Taman for the Mediterranean and Turkey, Ust-Luga for Europe.
  - Crude: Kozmino, Novorossiysk or Primorsk.
  - LNG: Sakhalin-2 for Asia, Yamal (Sabetta) for Europe.
- **Carrier practice**: Capesize, VLOC and VLCC voyages use the Cape of Good Hope instead of Suez
  when the Cape costs four extra days or fewer, because of canal tolls and draft limits. Suez is
  then shown as the shorter alternative.
- **Alternatives**: when a lane or route passes Suez/Bab el-Mandeb or Panama, the alternative path
  avoiding them is computed, with its extra distance and laden days.
- **Chokepoints crossed** are detected geometrically: the path passes within a set radius of the
  strait or canal.
- **Laden days** are distance ÷ typical laden speed for the class: about 11 kn for Capesize,
  Newcastlemax and VLOC, 12 kn for other dry bulk,
  12.5–13 kn for tankers, 15.5 kn for VLGCs and 17 kn for LNG carriers. These are Atlas assumptions.
- **Lane selection**: per commodity group, the largest seaborne pairs covering 80% of volume (at
  most 22 pairs) in each of 2005, 2010, 2015, 2019, 2021, 2022, 2023 and 2024. The union of those
  pairs is kept, at most 45, so the history view shows lanes that later shrank, such as Russia to
  Europe.

## 4. Vessel classes per lane

Typical classes follow standard practice: cargo size, loading and discharge port draft, and canal
limits. The rules are in `pipeline/freight/vessel_rules.py`. Examples:

- Pilbara and Brazil iron ore to China: Capesize, with Valemax-type VLOCs for Brazil.
- Indonesian coal: Supramax and Panamax (shallow loading, barge transhipment).
- Black Sea wheat to the Mediterranean and Middle East: Supramax and Handysize.
- Middle East Gulf crude to Asia: VLCC.

These are labelled "typical" in the interface. They are not measured shares of each class.

## 5. Shares

- **Route share of a commodity's seaborne trade** = corridor volume ÷ world seaborne volume of
  that commodity, both from BACI for the latest year. The corridor is the set of origin and
  destination countries the route represents, listed per route in `routes_def.json`.
- **Route share of vessel-class activity** (Atlas estimate) = corridor tonne-miles ÷ total
  tonne-miles of all seaborne flows whose typical primary class belongs to the same size family
  (for example Capesize, Newcastlemax and VLOC together).
  - Routed lanes use their sea-route distance.
  - Other pairs use the great-circle distance between gateway ports × 1.3.
  - Overlapping routes (C5 and the C10_14 round voyage, for example) share the same corridor.
- **Lane share of destination imports** = lane volume ÷ the destination's total imports of that
  commodity group (all modes).
- **Chokepoint commodity share** (Atlas estimate) = seaborne volume on mapped lanes crossing the
  chokepoint ÷ world seaborne volume. This is a lower bound, because unmapped smaller flows are
  not routed. Published figures (EIA oil flows, canal authority statistics) are shown separately
  and take precedence.
  - The cargo table of a chokepoint page lists the same mapped lanes one by one (commodity,
    origin, destination, Mt, share of the commodity's seaborne trade). Lanes with no flow in the
    latest year are left out.
- **Chokepoint traffic** is IMF PortWatch's daily count of tankers, dry bulk, container, general
  cargo and ro-ro vessels, and PortWatch's estimate of the trade volume they carry (tonnes of
  cargo, not deadweight). Both are shown as weekly averages and as the average of the last 28
  days. PortWatch counts the Oresund but not the Great Belt, so the Danish Straits series is
  labelled as Oresund only; it has no counter for the Singapore Strait or for Cape Horn, whose
  page shows the Magellan Strait counter under its own name.

## 6. Country profiles

Profiles are built by `pipeline/commodities/build_profiles.py` from the ranked tables of the
commodity pages (production, exports, imports, and the second trade tables such as refined copper
or alumina).

- **Which rows appear.** A row enters a country's profile when one of these holds:
  - the country ranks in the world top 10 of the table;
  - it holds at least 3% of the table's world total;
  - the row is worth at least 10% of the country's own export (or import) value across the atlas
    commodities.
- **Limit.** Each commodity table keeps its 12 largest countries, so a country below rank 12 has
  no row for that commodity, whatever its share of its own trade.
- **Nothing is cut.** Every row that passes is published. The page shows the first eight rows of
  each section and the rest behind "Show all".
- **Order.** Exports and imports are ordered by trade value, production by share of the world
  total.
- **Shares** are against the world total of the same table, so of the same source and year.
- **Trade value** (bn USD) always comes from CEPII BACI for its latest year, whatever the source
  and year of the tonnage on the same row; the row names both.
- **Coal.** Customs codes do not separate thermal from metallurgical coal, so the value of coal
  is shown on one row, "Coal (all types)", with the customs tonnage of all coal. The thermal and
  metallurgical rows below it carry EIA tonnage and no value.
- **"World top-10 in N commodities"** counts the catalogue commodities for which the country is in
  the top 10 of at least one table. It is counted on the full tables.
- **Warnings** of a commodity table (trade hubs that re-export, gross weight against contained
  metal) are repeated on the country rows built from it.

## 7. Prices

- Monthly prices: World Bank Commodity Price Data (Pink Sheet), nominal USD, 1960 to the latest
  month.
- Daily prices: EIA spot series (Brent, WTI, Henry Hub, New York Harbor gasoline, ULSD and heating
  oil, US Gulf jet fuel, Mont Belvieu propane).
- Baltic Exchange freight indices are proprietary and are not shown.

## 8. Discrepancies

When sources disagree (for example USGS and EIA, or USDA PSD and customs data), the official or
primary source is shown and the difference is noted in the commodity file's `discrepancies` field.
