# Methodology

How the atlas turns public statistics into flows, lanes, routes and shares. Figures that the atlas
estimates (rather than copying them from a publisher, or computing sums and ratios of one publisher's
own figures, which keep that publisher's credit and say "data adapted") are labelled **"Atlas
estimate"** in the interface and carry the source id `atlas`; the note of each says how it was computed. A rule that the atlas
sets by judgement (a typical port, a mode list, a routing threshold) is an **Atlas assumption**, and
is called one where it is shown. The figures below are those of the build from CEPII BACI V202601
(latest year 2024).

## 1. Bilateral trade flows

- **Source**: CEPII BACI, HS 1992 version (the database covers 1995–2024), which reconciles
  exporter and importer declarations from UN Comtrade. Quantities are metric tonnes, values
  thousand USD. The atlas's cache holds the years 2002 to 2024
  (`pipeline/cache/baci_flows.csv.gz`, written by `pipeline/trade/extract_baci.py`, rows below
  both 1,000 t and USD 1 million dropped; the totals of every group and year before that threshold are kept in
  `pipeline/cache/baci_group_totals.csv`, and a commodity page whose tables hold under 97% of the customs file's total in the latest year says so
  in its notes, with both figures and the part due to the threshold and the part due to the cleaning rules (in the 2024 build: natural graphite, three of
  the ferro-alloy groups, rare-earth metals, lithium, silver, unwrought tin, crude oil, coke and unwrought zinc; since the sixth release the note is written for every group that a page shows as a table,
  the groups built by hand on a page included: unwrought zinc holds 5.06 Mt of the 10.1 Mt of the file, one row, Spain to Mexico, 5.02 Mt for
  USD 61 million, being estimated at 0.021 Mt by rule 3, and coke 32.9 Mt of 34.6 Mt, 1.63 Mt being Mozambique's); lanes and their history start in 2005. The 2.4 GB database is
  not in the repository: a new version is downloaded when CEPII publishes one, normally by hand
  (see the README).
- **Commodity groups**: HS six-digit codes are grouped per commodity in
  `pipeline/trade/hs_map.py` (e.g. coal = 2701.11 + 2701.12 + 2701.19).
- **Known limits of customs data**
  - HS codes do not separate thermal from metallurgical coal; the coal lanes and the customs flows of both coal pages
    cover both. Metallurgical coal production and trade by country come from EIA, which does split them, and the
    Metallurgical coal page's Main flows come from two exporters' own statistics, not from customs data (section 10).
  - HS 1992 has a single code for all refined petroleum products (2710.00).
  - Copper concentrate tonnage is reported inconsistently (gross weight or copper content): see
    rule 8 below.
  - Origins are as declared. A cargo may be recorded under the country it was last shipped from,
    or not recorded at all; where the atlas's own figures show this, a caveat says so (below).
  - Domestic coastal trade is not covered. Customs data record trade between countries only, and
    the cleaning drops every row whose origin and destination are the same country.
- **Cleaning rules** (`pipeline/trade/clean.py`, shared by every builder so that lanes, pairs,
  rankings and flows agree). In order:
  1. **"Other Asia, not elsewhere specified".** BACI has no code for Taiwan; its code S19 is read
     as Taiwan (176.3 Mt of 2024 imports in the lane groups). The exception is crude oil from Iran
     from 2019 (`S19_UNSPECIFIED`): 3.33, 24.16, 21.65 and 26.23 Mt in 2019 to 2022 (the first three
     estimated from value) stay under BACI's own label and are shown as "Asia, not specified"
     (pseudo-place `XAS`, named in `data/countries/places.json`). They count as seaborne, are never
     routed and are not in Taiwan's imports, which then read 56.4, 49.0, 53.6 and 57.9 Mt of crude in
     2019 to 2022. This restores a label; it computes no tonnage. Mexican crude recorded under S19
     (2.78 Mt in 2018, then 13.1, 12.7, 15.2, 9.99, 8.43 and 7.88 Mt in 2019 to 2024) stays as Taiwan
     with the caveat `crude-mex-s19`, because no source read confirms its destination.
  2. **Missing tonnage** with a declared value: tonnage = value ÷ the reference unit value of the
     group and year (the median; for the bulk groups of rule 7, the tonne-weighted median).
  3. **Gross unit errors** (unit value below 1/100 or above 100× the reference, any size) are
     re-estimated the same way; for a bulk group, a row that fails against either the plain or
     the tonne-weighted median is one (coal Mozambique → Poland 2019: 201 Mt declared at 0.94 USD/t).
     Example: rare earths Turkey → Benin. A row with a tonnage and no declared value keeps its
     tonnage and is flagged `no-value` (3 rows). In the groups of `UV_KEPT_GROUPS` (sunflower seed: in 2024 the group's median
     is USD 1,289 a tonne and France's exports as a whole USD 1,021, but France → Romania, Hungary and Ukraine declare USD 10,900 to
     13,900, which the atlas reads as seed for sowing under the same code, a hypothesis since the code does not separate them, so the
     group median is no reference for such a pair) a row whose unit value is above the group reference keeps its reported tonnage
     and is flagged `uv-suspect-t`; below the reference rule 3 applies as for every group (Canada → Trinidad and Tobago 2010 at under
     USD 13 a tonne, Kazakhstan → Russia 2012 at USD 7, Tanzania → Kenya 2020 and Uganda → Kenya 2017 are errors of tonnage or value).
     The rows of `KEEP_REPORTED` keep their reported tonnage too: France → Russia sunflower seed 2024
     (292 t for USD 112 million) was an 87 kt estimate, a main flow and a lane of the headline year. `KEEP_REPORTED` is the one table
     of the rows of the new groups that rules 3 and 4 would re-estimate to more than 50 kt and five times the pair's own median of the other
     years (23 rows in all years: 19 kept as reported, the 18 of the table and France → Russia sunflower seed, and 4 re-estimated, each
     for the reason written in `test_fncb.py`, which lists the rows one by one and fails when a row that the two rules would re-estimate is
     missing from the list), each kept row with its reason beside it.
  4. **Moderate inconsistencies** (unit value below 1/3 or above 3× the reference, flows over USD 50
     million) are re-estimated only for the homogeneous goods listed in `HOMOGENEOUS` (`clean.py`): crude oil, refined products,
     LNG, LPG, wheat, corn, soybeans, soybean meal and oil, rice, sugar, palm oil, rapeseed, coffee, cocoa, cotton, urea, potash
     and DAP, and, of the groups added in the sixth release, the fertilisers and the grains that are one product each (potassium
     sulphate, monoammonium phosphate, superphosphates, ammonia, ammonium nitrate, UAN, ammonium sulphate, barley, sorghum, rapeseed
     oil, rapeseed meal and sunflower meal). Ore and concentrate groups, and every group of the metal bulks (ferrous scrap,
     chromium ore, pig iron, direct-reduced iron, coke and the ferro-alloys), keep the reported tonnage, because their grades range
     from about USD 40/t (laterite nickel ore) to over USD 2,000/t (sulphide concentrate). Among the other groups added in the sixth
     release, NPK, phosphoric acid, sulphur, ammonium nitrate with limestone, the two-nutrient compounds, sunflower seed, sunflower
     oil and pulses are not in the set either (a mix of grades, a price by the tonne of acid or of P2O5, crude and sublimed sulphur,
     seed of different uses; where the code gives a reason it is in the comments of `HOMOGENEOUS`). Two of the one-product groups that would otherwise
     qualify, coke and sunflower oil, are out for a reason of their own: the pairs that declare their own price level carry more
     than a tenth of the tonnes that rule 4 would add or remove over all years (a re-estimated row whose pair declares, in at least
     three other years, a unit value beyond the same factor 3 on the same side: the estimate would erase the pair's own level; below,
     section on the new groups). A row of `ESTIMATE_ROWS` is treated as rule 4 treats a homogeneous group, whatever its group; the
     table is empty since the sixth release (it held one row in the fifth, Mozambique → India 2016 in coke, which rule 5 now drops
     with the rest of Mozambique's coke).
  5. **Known misclassifications** are dropped (`DROP`, listed in `pipeline/commodities/QA.md`). Examples: Israeli pipeline gas to Egypt and Jordan
     declared as LNG (Israel has no liquefaction plant), and all of Mozambique's exports under the coke code, in every year and to every destination
     (since the sixth release): the EIA series of coke production (International Energy Data, series 21-1, the one that check K14 reads) gives Mozambique zero in every
     year of the file (from 1980 to 2025; its coke export series, 21-4, reads 33 kt in 2023 and 0 in the other years), so the tonnes are probably coal declared under the coke code,
     a hypothesis that no source establishes. The coke page says what was left out (1.63 Mt in the customs file of 2024, 16 years from 2005) and that these rows are not counted.
     They are out of the coke tables, lanes, passage estimates, history and totals of the commodity pages and of the commodity blocks of the country pages; the all-goods list of
     a country page is the customs value by heading of the unfiltered file, so that Mozambique's page still shows heading 2704 as declared (USD 0.257 billion in 2024), and the note says so.
  6. **Qatari LPG in 2021 and 2023** (`DROP_NEW_PAIRS`). Customs data give Qatar about 10 Mt of LPG
     exports a year from 2018 to 2024, except in 2021 and 2023, when pairs that have no LPG in either
     neighbouring year add 29.0 Mt (19 rows, reported tonnage) and 26.5 Mt (12 rows, 11 of them
     with the tonnage estimated from value). Those rows are dropped (a choice made without the owner at the
     second release) and listed in `pipeline/commodities/QA.md`: Qatar's LPG exports then read 10.1 Mt in both
     years, and world LPG 131.3 and 135.8 Mt. Several of the rows equal the LNG row of the same
     pair and year (Qatar → Italy 2021: 4.81 Mt of "LPG", 4.84 Mt of LNG), which suggests LNG cargoes
     recorded a second time under the LPG code. That cause is a hypothesis; no source states it.
     The rule is not generalised to every spike: the same test also finds Malaysia's bauxite
     exports of 2015 (25.5 Mt against 3.4 Mt in 2014 and 2016), which were real.
  7. **Unit-value anomalies of the bulk groups** (iron ore, coal, bauxite, manganese, alumina). Their
     reference unit value is the tonne-weighted median of the group and year, not the plain
     median: thousands of small, expensive parcels set the plain median (bauxite 2024: 151.7 USD/t
     against 68.9 USD/t tonne-weighted). Rows that are gross errors against the plain median are
     left out of that median, so that one bad row cannot set it (manganese India → Switzerland 2002).
     A pair-year is an isolated anomaly when its value is USD 50 million or more, the pair has data
     in the year before and after (for the latest year, the two years before), the two neighbours
     agree within a factor 2, and the pair's unit value is more than 3× or under 1/3 of both. When
     the reported tonnage is itself the odd figure (below 35% of both neighbours for a high unit
     value, or above 2.8× both for a low one) and the neighbours' unit values lie within 1/5 to 5×
     the group reference, the tonnage is re-estimated: declared value ÷ (the group reference of the
     year × the geometric mean of the pair's ratios to the reference in the two neighbouring years). The estimate therefore
     always moves towards the neighbouring years. It is an Atlas estimate (owner's decision of
     22 November 2026, flag `uv-repair`) and its note gives the tonnage customs reported. The other
     anomalies keep their tonnage and are flagged `uv-suspect` (iron ore South Africa → China 2015,
     23.8 Mt, where the value is the odd figure). On the 2002–2024 cache: 41 anomalies, 24
     re-estimated and 17 flagged. Examples: bauxite Guinea → China 2023, 13.8 Mt declared for
     USD 6.39 bn (464 USD/t, against 64 and 68.9 USD/t in 2022 and 2024), estimated at 100.6 Mt, so
     that world bauxite trade in 2023 reads 162.1 Mt instead of 75.3 Mt; coal Mozambique → Japan 2019,
     101.35 Mt declared at about 2 USD/t, estimated at 1.52 Mt; coal Indonesia → Taiwan 2014, 5.03 Mt
     declared, estimated at 23.4 Mt.
  8. **Peer unit value** (`PEER_UV`): Chilean copper concentrate. A Chilean row whose unit value is
     more than 1.8× that of Peruvian copper concentrate to the same destination and year (Peru's
     unit value to that destination when it shipped at least 50 kt there at a unit value within a
     factor 2 of its yearly average, otherwise Peru's average of the year) is re-estimated at that
     unit value of Peru times Chile's usual ratio to Peru: the median, over the years in which
     Chile's declarations are in line, of Chile's unit value of the year over Peru's. A year is in
     line when Chile's rows above the 1.8× threshold hold under 20% of its declared value
     (`PEER_CLEAN`); the ratio is computed from the data at each build (1.125 on the 2002–2024
     cache, from 2002, 2009, 2014 to 2020 and 2023), because in those years Chile's concentrate
     reads above Peru's (0.93 to 1.17 times in 2015–2020 and 2023), so Peru's unit value alone would
     overstate Chile's tonnage. Chile reads 7,000 to 8,000 USD/t in some years against about 2,000
     for Peru, as if its tonnage were contained copper; a tonnage declared in contained metal is the
     plausible cause, not established. The rule changes 221 rows from 2002 to 2024; in 2024, 11 rows
     declared at 4.81 Mt become 12.3 Mt, and Chile's exports read 12.4 Mt (Chile → China 2.79 Mt
     declared, 8.24 Mt estimated), against 12.85 Mt in 2019, 12.40 Mt in 2020 and 10.27 Mt in 2023,
     years in which Chile's declarations are in line and nothing is estimated for its large flows;
     2021 reads 11.4 Mt and 2022 10.0 Mt. Checked against
     Cochilco's export tables of fine copper in concentrate (free tables, available to 2021 only),
     the estimated tonnage implies a steady grade of 29 to 32% copper in 2010–2013 and 29% in 2021,
     next to 27 to 30% in 2014–2020, where the declared tonnage implies 44 to 56% in 2010–2013 and
     70% in 2021, impossible for a concentrate (Cochilco's figures are not published by the atlas).
  9. **Ore price in the lithium chemicals group** (`DROP_LOW_UV`, threshold `LITHIUM_MIN_UV`: 1,500 USD per tonne). Lithium
     carbonate and hydroxide (HS 283691, 282520) trade at thousands of USD per tonne. A row of the group
     whose reported unit value is under that threshold is dropped, in every year, unless its tonnage was
     estimated from value by the rules above. The flows are priced like ore or concentrate (in 2024:
     Nigeria → China, 8.60 kt at 286 USD/t; Brazil → China, 6.48 kt at 1,110 USD/t); that they hold a
     product or a weight declared under the wrong code is a hypothesis, no source states it. The rule
     works on the frame after the other rules, with their reference unit values, so that no other row
     changes. It sits here, and not in the commodity builder as before, so that the lanes, the pairs,
     the commodity page, the chokepoint estimates and the country profiles read one frame: the page
     and the lane file give the same world exports. The rows are listed in
     `pipeline/commodities/QA.md` with the rows of rule 6, and the lithium page and the lane file's year
     notes say which flows are left out and why. On the 2002–2024 cache the rule drops 33 rows in 15 years;
     in 2024 the two flows above, 15.1 kt of the 504.3 kt of the group.
  10. **A tonnage far above the volume: LPG from the United States to Mexico** (`us_lpg.CORRECTED`, flag `est-volume`). CEPII BACI gives
     9.33 Mt for this pair in 2024 at 252 USD/t, 0.39 times the group's median unit value. The US Census Bureau's export detail file
     (EXDB, December 2024) gives, for exports to Mexico in 2024, 9.38 million m3 under code 2711120010 (propane of 90% purity or more: 9.36 million m3 of
     domestic exports and 0.01 million m3 of foreign exports), 0.88 million m3 under 2711120020 (other propane: 0.46 million m3 of domestic and 0.42 million m3 of
     foreign exports) and 0.17 million m3 of butanes under 2711130000 (domestic exports; the file has no foreign export of this code to Mexico): 10.26 million m3 of
     propane and 10.43 million m3 of propane and butanes, each with the foreign exports (the quantities of `pipeline/cache/us_lpg_volumes.json`, which sum the domestic and
     the foreign exports of a code; the split into the two is read from the file in `raw/`). The customs tonnage is 0.76 (2021), 0.76 (2022), 0.98 (2023)
     and 0.90 (2024) times the volume in cubic metres of the United States' own statistics (EIA's exports by destination for the first three
     years, 9.75, 10.33 and 9.98 million m3 of propane and butanes; the Census quantity of 10.43 million m3 for 2024), and 1.51, 1.48, 1.92 and
     1.77 times the tonnage that this volume gives at the density of the cargo. A volume in cubic metres read as tonnes, for part or all of the
     declarations, is a plausible cause: it is not established here. EIA's exports by destination (propane, normal butane, isobutane, in thousand barrels a day, from the Census Bureau's
     customs data) run from 2004: from 2004 to 2020 the customs tonnage of the pair is 0.7 to 1.2 times the tonnage of EIA's volumes at the density
     of the cargo, and its unit value 0.5 to 1.4 times the group's; in 2021 to 2024 it is 1.5 to 1.9 times and 0.39 to 0.56 times. The tonnage of
     2021, 2022, 2023 and 2024 is therefore replaced by the volume of the United States' own statistics times the density of the cargo (an Atlas
     estimate, source id `atlas`, the note of the row gives both figures): EIA's volumes for 2021 to 2023, the Census file's own quantity for
     2024, at the densities of the Census file (the shipping weight of the cargo that went wholly by vessel over its quantity: 505.5 kg/m3 for
     propane, 582 for the butanes). The pair reads 4.94, 5.31, 5.06 and 5.28 Mt in 2021 to 2024 (customs 7.44, 7.87, 9.74 and 9.33 Mt), and world LPG
     trade 128.8, 138.8, 131.1 and 140.8 Mt (customs 131.3, 141.3, 135.8 and 144.8 Mt in the released file). The years 2004 to 2020 are as
     reported; 2002 and 2003 cannot be checked (EIA's series start in 2004). The same check was made for the United States to Canada: from 2015 the
     customs tonnage is 1.1 to 2.0 times the tonnage of EIA's volumes, against 0.5 to 1.2 before, and the unit value falls under two thirds of the
     group's, but EIA's figures for Canada are whole numbers of thousand barrels a day that are small, and three of the ten years stay inside the
     earlier range: no year is replaced, and the LPG page says so. The Census file also gives the three Asian buyers a vessel tonnage
     (Japan 14.6 Mt, China 10.3 Mt, South Korea 5.30 Mt) that differs from CEPII BACI's pairs (6.17, 18.0 and 7.18 Mt) while the sums agree within
     4%: those pairs are not changed, and the page says so. The estimate is made after the other rules, with their reference unit values,
     before rule 9; the cache is `pipeline/cache/us_lpg_volumes.json` (what `pipeline/trade/us_lpg.py` reads from raw/census and raw/eia). The Census file
     (a 78 MB zip) and the EIA pages are downloaded by hand and no scheduled job fetches them: the data are for the calendar year 2024 and the EIA
     release of 30 October 2026, and a later year is read by putting the new file in raw/ and running the script again.
  11. **Flows that the importer declares and CEPII BACI records at under 2 kt a year in 2017 to 2024 (the atlas's extract has no row for the pair in 2021, 2022 and 2024): tin ores and concentrates from Myanmar to China**
     (`comtrade_tin.ADDED_FLOWS`, flag `added`). China declares 76 to 293 kt of tin ores and concentrates (HS 260900) from Myanmar in each of
     2017 to 2024 (UN Comtrade, public preview, China as reporter, imports; net weight), the first origin every year and 48% to 99% of its
     imports; CEPII BACI, in the extract the atlas reads (flows under 1,000 t and USD 1 million are dropped), has at most 1.6 kt a year of this pair in those
     years (161 t in 2023, no row in 2021, 2022 and 2024).
     The cause of the gap is not established. The atlas takes the flow from China's declaration, year by year, pair by pair: a year in which the
     customs file holds under a tenth of the declared tonnage has its row added or replaced (2023: 161 t replaced by 180.5 kt), the value being
     the CIF value that China declares, and each row says in its note that it comes from China's import declaration, UN Comtrade, and not from CEPII
     BACI. The row is flagged in the pairs file (bit 4 of `f`, the source id in `added`), the Route finder, the country pages of Myanmar and China and the year
     notes of the lane file say where it comes from, and the checks of `pipeline/trade/checks.py` read the customs file as BACI has it (the added rows left
     out and the rows they replaced put back), so that no note compares a figure of UN Comtrade with BACI's neighbouring years as if it were BACI's.
     It is a declared figure, not an estimate (`imputed` false, no "Atlas estimate" mark). Only this pair is listed; every other cell where
     the two sources differ (Brazil in 2023 and 2024, DR Congo's value in 2022, Bolivia) is left as BACI has it. The years before 2017 keep
     BACI's figures: the answer of 2016 carries no net weight, and the years before were not loaded, so the series of the pair breaks between 2016
     and 2017. Myanmar to China moves overland (the countries share a border and neither is landlocked): no sea lane and no passage. Myanmar's
     own export declaration was not loaded. The cache `pipeline/cache/comtrade_tin_china.json` holds, for each year, China's declared total, the
     Myanmar figure and the five largest origins, with the flag of an estimated net weight; the answers stay in raw/, under UN Comtrade's terms. The calls
     (one per year, two minutes apart, no key) are made by hand; no scheduled job makes them, and a year is added by fetching it and running
     `pipeline/trade/comtrade_tin.py` again.
- **Tonnage estimated from value is an Atlas estimate.** Every row whose tonnage rules 2, 3, 4, 7, 8 or
  10 re-estimate carries a note that starts with "Atlas estimate" and gives the method, the declared
  value and the tonnage customs reported. Where such a figure is shown on its own (a lane's flow, a
  row of a flow table) it has the source id `atlas` and `est: true`, the site prints "Atlas
  estimate" beside it and rounds it to two significant digits at display (the data keep full
  precision, so that lane files, pairs files and totals still add up); no share of the
  destination's imports is written for it. Past years estimated from value are marked on the lane
  chart. Totals that include estimated rows keep the source of the data (`baci`) and say how much
  is estimated: a lane file's year note when it is 0.5% or more of the year's seaborne tonnes (the
  file's `estY` gives that share for every year), a
  ranked table's note when it is 1% or more of world tonnage (from 10%, "includes an Atlas
  estimate", and the world total keeps three significant digits); a country row of which half or
  more is estimated is itself labelled "Atlas estimate" (with the source id `atlas`). In 2024, 196
  rows and 78.2 Mt of the lane groups (0.94% of their 8,298 Mt) are estimated (the sea and transit pairs of the pairs files with the flag "estimated from value"); the largest are crude
  oil United Arab Emirates → Thailand (24.5 Mt), wheat Russia → Egypt (11.1 Mt) and copper
  concentrate Chile → China (8.24 Mt). The share of each lane group's 2024 seaborne tonnes that is
  estimated is the field `est` of its lane file: 33.0% for copper concentrate, 10.8% for potassium sulphate, 8.0% for wheat, 4.2% for LPG (1.3% in the
  released file: the part by sea of the United States → Mexico pair, an estimate from a volume, is now in the seaborne tonnes), 2.0% for
  sulphur, 1.8% for crude oil, 1.2% for direct-reduced iron, under 1% for every other group.
- **History rule** (`clean.history_flags`). A year of a pair's 2005–2024 series is blanked only on
  evidence: when rule 7 flagged it, or when it is a sharp one-year change (below 35% or above 2.8×
  both neighbouring years, by more than 2 Mt) whose unit value is off by more than 2.5 times against
  the neighbours. Its chart then says "suspect". A sharp change whose declared value moved with the
  tonnage is kept as reported ("kept"), and a year with no record at all stays empty with "no
  customs record" ("nodata"). Sustained changes (two years or more) are never touched: China's
  2021–22 ban on Australian coal, for example, spans two years. A year that a check finds in
  conflict with another source (check K2) carries its note ("check").
- **Checks** (`pipeline/trade/checks.py`) compare the cleaned customs data with the other sources
  on disk. They never change a figure and never stop a build: their findings go to
  `pipeline/cache/trade_checks.json`, to `pipeline/commodities/QA.md`, and, where stated below, to
  a note beside the figure. A check whose file is missing (as on the runner of the scheduled jobs)
  does not run, and its previous findings are kept.

  | Check | Against | Finding |
  |---|---|---|
  | K1 | USDA PSD exports and imports, marketing years Y-1 and Y (EU27 as one trader) | a top-12 trader of a crop below 75% of the smaller PSD figure, or above 125% of the larger by 0.5 Mt or more |
  | K2 | USDA PSD imports of the importer, the same two marketing years | a pair of 1 Mt or more above 125% of the larger PSD figure, by 0.5 Mt or more (note on the lane year) |
  | K3 | EIA crude production (series 57-1, thousand barrels a day), converted at 7.33 barrels per tonne, EIA's own ratio between its US series in barrels and in tonnes | exports above 105% of production; 95% to 105% listed |
  | K4 | EIA coal exports and imports (series 7-4, 7-3) | a top-15 trader differing by more than 25% |
  | K5 | EIA gas trade | not run: EIA gives gas in volume and energy units, customs in tonnes, and no file on disk gives a conversion for each trader's gas |
  | K6 | BACI itself | an exporter with 2% or more of the group in both neighbouring years and under 25% of their mean (a gap), or above 2.5× both and 3 Mt more (a spike) |
  | K7 | BACI itself | an importer above 1.5× both neighbouring years, 3 Mt more, and 2% or more of the group |
  | K8 | BACI itself | a pair of the latest year that was 2 Mt or more the year before and lost more than half, or that more than doubled by 2 Mt or more (worded as a change against the year before) |
  | K9 | IMF PortWatch | the passages, section 5 |
  | K10 | USGS Mineral Commodity Summaries | exports above 105% of mine or plant production (potash converted to K2O at 0.632, urea to nitrogen at 0.4665, both from molar masses), or an exporter of 0.5 Mt or more that USGS does not list as a producer |
  | K11 | the atlas's own infrastructure layers | an LNG exporter with no export terminal in the layer, a crude importer of 1 Mt or more with no refinery in it (QA file only: the layers are hand-built and incomplete) |
  | K12 | the gateways | a pair of 0.5 Mt or more whose main route is more than 2.5× the great-circle distance of its ports (QA file only: it points at a wrong gateway) |
  | K13 | the usual unit value of the product (tonne-weighted median of the group-year) | a pair of one product (unwrought metals, alumina, coke, pig iron, direct-reduced iron...) declared under half of it, 10 kt or more and 1% of the group; the caveat names the cheaper product that may be declared under the code: scrap or alloy by default, coal for coke, iron ore or scrap for pig iron and direct-reduced iron |
  | K14 | EIA production of the product (coke: series 21-1, with the metallurgical coal series 130-1, production, and 130-4, exports, of the Metallurgical coal page, not all coal, series 7-4; the coke export series 21-4 is read for the note on what a page leaves out) | an exporter of 1% or more of the group's recorded exports that has a series in the EIA file and no production in its latest year (it finds Zimbabwe, 0.893 Mt, of coke in 2024; Mozambique's coke, 1.63 Mt, is dropped by rule 5 of section 1 and is no longer a finding); a country with no series is not reported. The note on the row, the page and the lanes says what the customs data record and what the EIA series reads, and that the tonnes may be another product declared under the code (metallurgical coal where the page's EIA tables show the country as a producer or exporter of it). Where the series has production in an earlier year the note quotes its last two years with production (Zimbabwe: 399 kt in 2022 and 5 kt in 2023) and gives two readings the same weight, that the series no longer covers the country's plants (a series that falls to nothing may be a series that stopped) or that part of the tonnes is another product declared under the code; neither is established here. Where the series reads 0 in every year, the second reading only |

- **No "provisional" label on the latest year.** Neither CEPII's BACI page nor the readme of the
  release says that the latest year is provisional or will be revised, and the pairs that halve
  from one year to the next are no more frequent in 2024 than before: 62 of the 659 pairs of 2 Mt
  or more in 2023, against 50 to 85 of 631 to 673 in each year from 2019 to 2023. What is
  established is narrower: some pairs of the latest year are incomplete. Check K8 marks them (bit 3
  of the pairs table, a note on the flow) and checks K1 and K2 put the USDA figure beside them (corn
  United States → Mexico: 7.80 Mt in customs data for 2024 against 24.2 and 25.9 Mt of Mexican
  corn imports in USDA PSD for 2023/24 and 2024/25). Nothing is replaced.
- **Caveats** (`pipeline/trade/caveats.py`, written to `data/freight/caveats.json`) are the
  warnings attached to an origin, a pair or a group whose customs figures are known to be
  incomplete or doubtful: unrecorded exports (Iran, Venezuela, Russian crude to Turkey, Iranian
  LPG), exports above production (Malaysian and Emirati crude, Omani urea), breaks in a series
  (Iranian urea, Belarusian, Uzbek and Turkmen potash), flows that rest on importers' declarations
  (Russian grain and refined products, with the USDA export figures beside), unchecked origins
  (LPG from Oman and the United Arab Emirates to China), the Mexican S19 destination, and re-export
  hubs (refined products of the Netherlands, Belgium and Singapore; Dutch crude), and the declared destination or origin that is a landlocked trading centre
  (kind `landlocked-centre`: Qatar → Switzerland sulphur, 1.13 Mt, 23.5% of Qatar's exports and 98.8% of Switzerland's imports; Zambia → Switzerland refined
  copper; Malaysia → Switzerland and Switzerland → Malaysia iron ore; the cargo probably ends, or started, elsewhere, a possible reading; the tonnes stay in the
  tables and are counted at the passages of the route to the declared country, and no generated route is built from the pair). 35 are active for
  2024. They are shown on the lane, the flow rows, the commodity tables, the country profiles, the
  Route finder and the notes of the chokepoint shares. Rules of writing: every number in a caveat
  is filled by the builder from the data (none is typed in the registry); a cause is worded as a
  hypothesis ("a plausible cause; it is not established here") unless a cited source states it; an
  entry tied to a check is shown only while the check fires; an external figure keeps its own
  source and year and is never mixed into a table.
- **Pipeline gas tonnage** in customs data is often estimated from value. North American flows
  (Canada → US, US → Mexico) are understated about fivefold, so EIA bcm figures are used for
  production and consumption.

## 2. Seaborne or overland

Customs data do not say how a cargo travelled. Every pair of every year gets a mode from a rule,
`modes.mode_of(origin, destination, group, year)` in `pipeline/freight/modes.py`:

- **sea**: the pair trades by sea;
- **sea via a transit port** (`transit`): one end is landlocked and its cargo uses a foreign
  seaport (Kazakh crude through the CPC terminal at Novorossiysk, Zambian copper through Dar es
  Salaam);
- **sea and overland** (`mixed`): the trade moves both by sea and overland and no free source gives
  the split;
- **land**: overland, by pipeline, rail, road or river.

**Seaborne** means sea plus transit. Mixed and land pairs are not seaborne: they are outside the
seaborne totals, the lane shares and the chokepoint shares.

**The rules, in order** (the first that matches wins):

1. **Single flows** (`FLOW_OVERRIDES`): iron ore Brazil → Argentina is land (Corumbá ore by barge on
   the Paraguay–Paraná waterway; 3.84 Mt in 2024).
2. **Pseudo-places**: a pair with "Asia, not specified" at one end is seaborne by assumption and is
   never routed.
3. **LNG** (a product rule): an end without a coast is land. Between two coastal countries that are
   not land neighbours, LNG is sea. Between two coastal neighbours it is sea only when the exporter
   has a liquefaction terminal and the importer a regasification terminal (the atlas's own layer,
   `data/infrastructure/lng.geojson`, counted from each terminal's opening year; for the importers
   the layer lacks, the terminals named on the Wikipedia "List of LNG terminals"); otherwise it is
   read as pipeline gas declared under the LNG code, and is land. In 2024 Russia → China (8.28 Mt),
   Malaysia → Thailand (1.68 Mt) and Norway → Finland (1.01 Mt) are sea; 2.16 Mt of LNG-coded trade is
   land, among it Mozambique → South Africa (0.70 Mt, gas piped from Mozambique to Sasol's
   Sasolburg plant), the United Kingdom → Ireland and Vietnam → Cambodia (0.31 Mt each).
4. **Sea and overland** (`MIXED`, by ordered pair and cargo family): Russia → China for every family
   but LNG and softs, China → Russia for dry bulk and metals, the United States → Mexico for refined
   products, LPG, grain, vegetable oils and fertilisers, Mexico → the United States for refined
   products and LPG, and grain between Spain and France both ways. 309.8 Mt in 2024 on 52 pairs:
   Russia → China 236.2 Mt, the United States → Mexico 57.1 Mt, Mexico → the United States 10.9 Mt,
   France → Spain 2.7 Mt, China → Russia 2.6 Mt, Spain → France 0.2 Mt; by group, crude oil 108.5 Mt,
   coal 95.1 Mt, refined products 55.4 Mt, LPG 9.8 Mt, corn 9.1 Mt, iron ore 9.1 Mt. With the minor
   metals, the mixed pairs hold 310.2 Mt on 63 pairs in 2024. Since November 2026 the 2024 LPG pair United States → Mexico is no longer mixed: its 9.33 Mt reported are 5.28 Mt,
   of which 3.81 Mt by sea and 1.47 Mt overland (`KNOWN_SPLIT`, below). Belarus → China potash is not a mixed
   pair: it is a seaborne pair, because the pages bound the rail share: Kommersant, reported by Reform.news
   in March 2026, gives 9% of the 11.6 Mt Belarus exported through Russia in 2025 as rail to China and
   the CIS countries together. The rail fact is in the Belarusian caveat (`potash-blr`), with its
   source and year; nothing is subtracted from the 2.9 Mt of 2024.
5. **Land neighbours** (a mainland border, see below): land, unless the pair is in `SEA_NEIGHBOURS`
   for the cargo family. A landlocked end with a land border is land.
6. **Sea outlets** (`SEA_OUTLET`): a landlocked exporter whose group is listed leaves by sea through
   a foreign port, to a coastal buyer or to a landlocked one outside its overland blocs: Kazakh crude
   (CPC pipeline to Novorossiysk; 63.0 Mt in 2024), Azerbaijani crude (BTC pipeline to Ceyhan;
   23.3 Mt), Belarusian potash (3.6 Mt, China included), Paraguayan soy and corn (Paraná–Paraguay waterway; 2.6 Mt)
   and Zambian copper (TAZARA railway to Dar es Salaam; 1.1 Mt).
7. **Two landlocked ends**: land.
8. **One landlocked end**: sea via a transit port when the two countries share no overland bloc
   (`BLOCS`), land otherwise.
9. **Default**: sea.

**Cargo families** (`FAMILY`): crude; refined products; LPG; LNG; dry bulk (iron ore, coal, bauxite,
alumina, manganese, copper, nickel and zinc ores, spodumene concentrate, and, since the sixth release, chromium ore and coke); grain (wheat, corn,
soybeans, soybean meal, rice, sugar, rapeseed, and, since the sixth release, barley, sorghum, sunflower seed, sunflower
meal, rapeseed meal and dried pulses); vegetable oils (soybean, palm, sunflower and rapeseed oil); fertilisers
(potash, potassium sulphate, phosphate rock, DAP, MAP, superphosphates, phosphoric acid, urea, ammonia, ammonium
nitrate and ammonium nitrate with limestone, UAN, ammonium sulphate, NPK, the two-nutrient compounds and sulphur: the mode of a pair depends on the borders and the ports, not on
whether the cargo is a solid or a liquid); metals (steel, ferrous scrap, pig iron and direct-reduced iron, the
ferro-chromium, ferro-manganese, silico-manganese and ferro-silicon (added in the sixth release), refined copper, aluminium, nickel intermediates,
ferro-nickel, lead concentrate, unwrought lead, zinc and tin, tin concentrate, cobalt, lithium
carbonate and hydroxide, rare earths, and uranium, which has no lanes); softs (coffee, cocoa,
cotton). Gold, silver and platinum-group metals get no mode ("mode not modelled"): much of it may
fly, but no source was read, so no mode is claimed. Their flows are listed in the tables, and the
map says that the atlas draws sea and overland lanes only. Uranium flows are listed with their
mode, not drawn as sea routes.

**The lists** are Atlas assumptions. Each entry carries its reason and, where a page was read, its
URL, returned with the mode; an entry without a URL is an unsourced assumption. 2024 tonnage:

- `SEA_NEIGHBOURS`: 33 pairs of neighbours that trade by sea, 223.4 Mt (the list holds one more entry,
  Malaysia–Singapore, which is not a neighbour pair in the base map and so never applies). The largest: China–India
  40.7 Mt (Himalayan border; Indian iron ore sails from the east coast), Indonesia–Malaysia 38.7 Mt,
  Mexico → United States crude 26.5 Mt (crude only), China–Vietnam 16.8 Mt, Norway–Sweden 12.6 Mt,
  China–Hong Kong 10.4 Mt, Colombia–Panama 8.3 Mt (no road crosses the Darién gap). Some entries are
  limited to a family: Ecuador–Peru to crude, the United States–Mexico to crude, Spain–France and
  Spain–Portugal to crude, refined products and LPG.
- Land neighbours with a stated reason (`LAND_NOTES`): Netherlands–Belgium 56.4 Mt (pipeline and
  Scheldt barges), Netherlands–Germany 35.2 Mt (Rhine barges and pipelines), France–Belgium 16.3 Mt,
  Germany–Poland 12.5 Mt, Canada–United States crude and refined products 265.2 Mt (pipelines and
  rail; part may sail from the Trans Mountain pipeline's Westridge terminal, in a share not known),
  India → Bangladesh refined products 1.8 Mt (India–Bangladesh Friendship Pipeline).
- `MIXED` and `SEA_OUTLET`: rules 4 and 6 above.
- A mixed pair-year whose split a source measures (`KNOWN_SPLIT`): the United States → Mexico LPG pair in 2024, 72% by sea. The US Census
  Bureau's export detail file gives a shipping weight for the cargo that went by vessel only (3.81 Mt) and no weight for the other modes, which it
  does not name; the total tonnage of the pair is its quantity (10.43 million m3) times its density (cleaning rule 10), 5.28 Mt, so the share by
  sea is 72% (by value, 72%: the file's vessel value over its total value, which does not need the density). `mode_of(o, d, group, year)` returns it
  for that year only; the lane builders cut the pair into two rows that add up to its tonnage, 3.81 Mt by sea (mode sea: the lane, the seaborne totals,
  the chokepoint estimates, the corridor volumes and the country pages read it) and 1.47 Mt overland (mode land), after the checks and the caveats,
  which read the pair as one row. The lane keeps its history in all modes, as the years before (its chart, its change on the year and a past year's figure say "all modes"), and its note
  says the share, its source and what the other years are, from the flags of the row (the customs total for all modes before 2021, the atlas's estimate for all modes
  from EIA's volume for 2021 to 2023, and in none of those years the split by mode). Because the split is known for 2024 only, the seaborne LPG
  series breaks between 2023 and 2024 (3.81 Mt of the rise from 117.0 to 129.7 Mt is this pair moving from the mixed series to the sea series): the lane
  file's `breakNote`, built from the data, says so where the seaborne figure and the lane table's footer are printed. The estimated share of the seaborne
  tonnage tells the two bases apart (`estVol`, from a volume in the United States' own export statistics, against the rest, from the declared value), as
  the history chart's notes do (`histVolume`) and as the source line under it, which names the Census Bureau and EIA for the years of the estimate (`histSrc`). The rest is read as overland; the file does not say which mode carried it.
  The pairs file keeps one row for the pair, the part by sea, and lists the overland part (`rest`), which the country pages count as land and, like the row of its pair, as an Atlas estimate (the freight block and the balance block of a country page give the same estimated tonnes of the same total). The flow of the Main flows table carries the share by sea (`seaShare`), which the row, its tooltip and the CSV print in the mode; the other mixed flows keep "split not known". The sea part raises the 2024
  seaborne LPG total from 125.8 to 129.6 Mt: the corridor shares of the LPG routes and the shares of the 13 LPG passage estimates fall by 0.1 to 1.0 points (Panama
  33.1% to 32.1%, Malacca 15.2% to 14.8%) with the tonnages unchanged. The one more generated LPG corridor (Mediterranean) that the larger total would need to reach the target share is not generated: the caps are
  full of routes of the last release, which stay (`gen-sugar-sea-sea` is one of them), and the smallest main LPG lane (Qatar → Philippines) stays in the main set: a published
  route or lane is never put out by a cap (section 3, "Lane selection" and "Generated corridors").
- Overland blocs (`BLOCS`): Europe (with Russia, Belarus, Ukraine, Moldova and Turkey), the
  1520 mm broad-gauge rail network (the former Soviet Union, Finland, Mongolia, and Poland as an
  assumption), Southern, East and West Africa, South America, South Asia, mainland Southeast Asia,
  and Mongolia with China and Russia. Two countries in one bloc trade overland by default.

**Borders and coasts** come from the Natural Earth country topology (`pipeline/geo/adjacency.py`):
an arc shared by two countries is a border, an arc used by one country is coast, and a Caspian
coastline does not count as ocean access. Only mainland borders count: French Guiana's borders
with Brazil and Suriname are listed as overseas borders and do not make France their neighbour.
Places that BACI reports but the base map has no polygon for are listed in
`pipeline/geo/places_extra.json`: Gibraltar, Bonaire, Sint Eustatius and Saba, Christmas Island,
Tokelau, the former Netherlands Antilles, Serbia and Montenegro, Mayotte and the Cocos (Keeling)
Islands, all coastal, and the pseudo-place "Asia, not specified". The site names them from
`data/countries/places.json` and shows them as plain text, not as country pages.

**2024 by mode** (71 lane groups, 36,072 pairs, 9,659.0 Mt): sea 8,108.5 Mt (25,922 pairs), sea via a
transit port 185.5 Mt (2,725 pairs), sea and overland 317.5 Mt (109 pairs), land 1,047.5 Mt (7,315
pairs). Seaborne: 8,297.8 Mt. (In the fifth release: 42 groups, 25,847 pairs, 9,154.1 Mt and 7,923.3 Mt seaborne, before the groups of the sixth release were added:
ten of fertilisers and sulphur, eight of grains, oilseeds and pulses, nine of metal bulks and two more fertiliser groups
(ammonium nitrate with limestone and the two-nutrient compounds). Belarusian potash to China, 2.9 Mt, is sea via a transit port.
Since the sixth release 1.6 Mt of Mozambique's coke is out of the 2024 frame.)

**Sea via a transit port.** The foreign port of a landlocked country is gateway data
(`TRANSIT` in `pipeline/freight/gateways/energy.py`), one sourced row per country and cargo (a customs
group or a cargo family) or a default row. 26 countries have one. 23 of them were in the first list: Austria and Czechia (crude: Trieste, Transalpine
Pipeline), Hungary and Serbia (crude: Omišalj, Adria pipeline), Kazakhstan (crude: CPC terminal,
Novorossiysk, a port in Russia), Azerbaijan (crude: Ceyhan, BTC pipeline), Chad (crude: Kribi),
South Sudan (crude: Port Sudan), Czechia (other cargo: Hamburg), Switzerland (Rotterdam), Uganda and
Rwanda (Mombasa), Zambia, Malawi, Burundi and DR Congo (Dar es Salaam), Zimbabwe (Beira), Ethiopia
(Djibouti), Burkina Faso and Mali (Abidjan), Niger (Cotonou), Nepal and Bhutan (Kolkata), and
Bosnia and Herzegovina, whose short coast has no port of its own (Ploče). Each of these rows cites a
Wikipedia article. Pages read on 23 November 2026 gave rows to three more countries,
Belarus, Paraguay and Botswana, and new cargo rows to four that had one, Austria, Hungary, Serbia and
Kazakhstan: Belarus (fertilisers: St Petersburg, for the Bronka and St Petersburg terminals, from an
OSW commentary of November 2024 and a Reform.news report of Kommersant's 2025 figures), Kazakhstan
(coal: from a Kpler note of February 2025), Paraguay (soy and corn: from a Bolsa de Comercio de
Rosario note of April 2017 on the grain coming down the Paraná–Paraguay waterway in transit in
2016), Austria and Hungary (other cargo: Koper, Port of Koper article), Serbia (other cargo:
Constanța, Port of Constanța article, Danube traffic) and Botswana (Walvis Bay, Walvis Bay article).
A row holds only what its page says: the Kazakh coal row
names the two buyers of the page, Morocco (Ust-Luga) and the member states of the EU (one of Ust-Luga
and Novorossiysk, the page's chart of the EU trade naming both, no split), so Kazakh coal for Turkey,
Israel, India, Taiwan, Japan and the other buyers, and the other dry bulk of Kazakhstan, have no row.
The Paraguayan rows follow the cargo the page counts at each outlet, with its 2016 figures: soybean
meal at Rosario (1.30 Mt) or Nueva Palmira in Uruguay (about 722,000 t of Paraguay and Bolivia), drawn
at Rosario; soybeans at Nueva Palmira (nearly 1.7 Mt of Paraguay and Bolivia) or Rosario (767,000 t),
drawn at Nueva Palmira; corn at Nueva Palmira (294,000 t); soybean oil at Rosario (590,000 t). Wheat,
rice and sugar of Paraguay are on no page and have no row. Nueva Palmira is placed at the coordinates
of its Wikipedia page. The Belarusian row names potash: for the other fertilisers of Belarus its port
is published as a general port of the country, not as a page that names the cargo, and so are the
default rows. Slovakia has no row although the Constanța article names it: a
default row would also send its crude imports there. A transit pair is routed from or to that port
and the site writes "sea via" the port. A seaborne pair whose landlocked end has no sourced row
(Central Asian products, potash and urea of Uzbekistan and Turkmenistan, Kazakh products, Slovak
and Bolivian trade, and Kazakh coal for the buyers the Kpler page does not name, among them: 31.4 Mt in
2024, 47.7 Mt before the rows read on 23 November 2026) stays in the seaborne
totals but is not routed and has no lane.

**Sea and overland.** A mixed pair's tonnage is the customs total for all modes. It is kept out of
the seaborne totals and the chokepoint shares; the lane files publish it per year in `mixed`, and a
mixed pair at or above the floor of its group is drawn as a dashed lane on its sea route, with no
share of seaborne trade (a total of all modes over a sea total would mix two bases). The commodity
page says, for example, "95.1 Mt that move both by sea and overland (split not known) are not in
it" under the seaborne coal figure.

**Change from the earlier rule.** The earlier rule classed every pair of coastal non-neighbours as
sea, every pair of neighbours as land unless it was one of 24 sea-neighbour pairs valid for every
cargo, and every landlocked end as land except five sea outlets. Seaborne 2024 tonnage by group,
earlier rule then current, for the groups that moved by 1 Mt or more (Mt): iron ore 1,594.7 →
1,635.5; crude oil 1,861.2 → 1,874.4; coal 1,364.4 → 1,377.3; LNG 360.0 → 369.2; potash 39.1 → 41.9;
phosphate rock 32.4 → 34.3; DAP 16.3 → 17.5; urea 47.4 → 48.6; refined products 1,007.4 → 960.6; steel
299.0 → 287.0; corn 159.3 → 149.4; LPG 135.0 → 125.8; wheat 175.0 → 167.3; soybeans 159.7 → 157.2;
soybean meal 62.5 → 61.4; rapeseed 21.0 → 20.0. Copper concentrate (28.8 → 37.2 Mt) moved because of
cleaning rule 8, not of the mode rule. The 32 groups of the earlier rule total 7,893.0 Mt before and
7,897.9 Mt now; ferro-nickel (10.1 Mt) and spodumene concentrate (5.0 Mt) are new groups.

## 3. Lanes and routes

Built by `pipeline/freight/build_lanes.py` (lanes and pairs) and `pipeline/freight/build_freight.py`
(benchmark routes), with the routing of `pipeline/freight/routing.py`.

- **Lane selection** (latest year first). For each commodity group and the latest year:
  - the **main set**: every seaborne pair at or above the group's floor, largest first, up to the
    group's cap. The floor is 0.05 Mt (0.02 Mt for coffee, cocoa, cotton, nickel intermediates,
    refined copper, zinc and lead concentrate; 0.03 Mt for aluminium and soybean oil; 0.015 Mt for
    unwrought zinc and 0.01 Mt for unwrought lead, spread over hundreds of small pairs; 0.005 Mt for
    lithium carbonate and hydroxide, 0.002 Mt for tin concentrate, cobalt and rare earths and 0.001 Mt
    for unwrought tin, which trade in parcels of a few thousand tonnes). The caps run from 20
    lanes (nickel ore, spodumene concentrate, tin concentrate, cobalt) to 150 (refined products,
    steel); they are in `CAP`. A main lane of the last release stays in the main set while its pair is still a routed seaborne
    pair at or above the floor, whatever the cap: the ids of the main lanes of the last release are in `pipeline/freight/released_ids.json`
    (written at each release by `pipeline/freight/release_ids.py`, from the published lane files), the cap counts them, and the other
    pairs take the places that are left, largest first. Without that rule a pair that moved from the mixed lanes, which the cap does not count,
    to the sea lanes could push the last lane of its group out although nothing on that lane's side had moved. A group under 1 Mt of seaborne trade a year (unwrought tin, tin concentrate,
    cobalt, lithium chemicals, rare earths) is published in kt with one decimal (the lane file's `unit`),
    as its commodity page prints it, and the lane page, the lane table, the Route finder and the
    chokepoint lists print it in kt too; its pairs file's seaborne total is the sum of its published rows.
    Where figures of several groups are compared or summed (the width of the lanes on the map, the
    lanes of a country, a commodity with groups in both units), they are taken in Mt.
    No lane from the wrong coast: many minor-metal ports have no page
    for the cargo, so for these eight groups a pair whose route is more than 1.8 times the great-circle
    distance of its two ports is not routed when an end's port has no page that names the cargo and
    either another port of that country in the atlas's tables reaches the other end in under 60% of the
    distance (Russian lead concentrate and cobalt for China and Korea from Novorossiysk, Saudi lead for
    the Emirates from Jeddah, Spanish metal for northern Europe from Valencia; French metal now has Le Havre), or the
    port is only the country's nearest seaport (Turkish lead concentrate for China and Korea from
    Samsun): 0.5 Mt of seaborne pairs in 2024 (0.6 Mt before France had a Channel port), and the 0.37 Mt mixed Russia → China lead concentrate.
    For the general-cargo minor metals, a row that names containers or general cargo at a port is a
    general port of the country, not a page that names the cargo; a row that names the metal keeps it.
    The minor metals (lead, zinc and tin metal, tin concentrate, cobalt, lithium chemicals, rare
    earths) sail as general cargo: container first, Handysize second, like refined copper; lead
    concentrate takes the classes of zinc concentrate (Supramax, Handysize).
    The mixed pairs at or above the floor are added outside the cap, drawn dashed;
  - the **history set**: for 2005, 2010, 2015, 2019 and the three years before the latest, the 10
    largest seaborne pairs of that year that are not in the main set and hold at least 1% of the
    year's seaborne tonnes, so that a past year shows the lanes that later shrank (Russia to Europe);
  - the **remainder** (`rest`): per exporter, the seaborne tonnes of the latest year that are on no
    main lane, with the number of pairs, shown as the last rows of the lane table ("Other
    destinations").
  - A pair without two gateways, whose gateways are the same port, or whose route is under 50 nm
    gets no lane; it stays in the pairs table.
  - The map draws the main set when no year is chosen, and every lane with a figure in a chosen
    past year. The Route finder, the lane table, the lane counters and the country pages use the
    main set.
  - 2024: 3,735 main seaborne lanes, 57 mixed lanes and 572 history lanes over 71 groups (2,617, 35 and 271 over the 42
    groups of the fifth release); the main lanes carry 85.3% of 2024 seaborne
    tonnes. The share per group is the `coverage` of each lane file: 90% or more for iron ore, coal,
    bauxite, LNG, soybeans, manganese, LPG, corn and cobalt, among others; lowest for unwrought tin
    (56.9%), refined products (60.1%), unwrought lead (64.3%), unwrought zinc (65.0%), aluminium
    (66.1%), cocoa (66.5%), NPK (66.9%), silico-manganese (67.0%), ferro-silicon (67.2%), dried pulses (68.2%),
    ferro-chromium (68.2%), steel (68.2%), ammonium nitrate (68.9%), potassium sulphate (69.3%), ferro-manganese (69.7%)
    and coffee (69.9%); potash reads 81.2% (73.7% before the
    Belarusian transit row). The ferro-alloys, which trade in parcels of a few thousand tonnes over hundreds of pairs, have a
    lower floor than the default 0.05 Mt (0.02 Mt for ferro-manganese and silico-manganese, 0.005 Mt for ferro-silicon, `FLOOR` of
    `build_lanes.py`) so that their main set reaches 63% of their seaborne tonnes; the other ferro-alloys (the alloys of seven
    customs codes, 0.58 Mt by sea or via a transit port over 396 pairs, of 0.69 Mt over 483 pairs in all modes: from the cleaned frame that the lane builder reads, with the mode rule of the other ferro-alloys, since this group has no pairs file) would need more than sixty lanes for 63% and have tables and no lanes. Where trade is spread over thousands of pairs, the pairs table answers.
- **The pairs table** (`data/freight/pairs/<group>.json`) holds every pair of the latest year that
  the customs extract keeps (1,000 t or USD 1 million and more), whatever its mode: 36,072 pairs in
  2024. Each row gives the tonnage (kt: whole above 1 Mt, one decimal below), the mode, the two
  ports, the distance, the primary vessel class, the passages it has to cross and those it may
  cross (bit masks over the file's list of gates), and flags: tonnage estimated from value, caveat,
  main lane, check finding. A seaborne pair "not drawn on the map" is one without a main lane
  (1,222.3 Mt in 2024); a pair "not routed" has no route at all (61.2 Mt in 2024: 40.6 Mt because a
  landlocked end has no sourced transit port, 15.2 Mt because there is no sea route or it is under
  50 nm, mostly Malaysian refined products to Singapore, 1.4 Mt because an end has no gateway, 4.1 Mt
  because the general port of a country is on the other coast from its partner or only the nearest seaport, on a long detour, is left:
  2.5 Mt of ferrous scrap, 0.4 Mt each of pig iron and direct-reduced iron, 0.4 Mt of the four ferro-alloys and 0.5 Mt of the eight
  minor-metal groups). The atlas gives Turkey the ports of its two steel works for scrap, pig iron and direct-reduced iron (below), not
  its general port Mersin alone, which is on the other coast from the Black Sea: so the Black Sea flows to Turkey (Russian pig iron 937 kt,
  Romanian scrap 910 kt, Russian scrap 614 kt and direct-reduced iron 506 kt, among others) are routed, not refused as "port on the other
  coast"; 64.2 Mt, 47.7 Mt of it for want of a transit port, before the rows read on 23 November 2026).
- **The Route finder** reads the pairs files of the commodity's groups, so it never says "no flow" for
  a pair that customs data record. It can start from the origin or from the destination, and
  answers in one of six ways: a drawn lane (with its ports, passages, alternatives and caveat); a
  sea pair not drawn on the map (below the lanes shown for the commodity); a pair that moves by sea
  and overland with the split not known; an overland or pipeline pair; a sea pair with no route
  modelled; or no trade recorded (flows under 1,000 t and USD 1 million are not kept). The question
  is kept in the address (`rf=` in the hash), nothing in the browser's storage.
- **Typical ports (Atlas assumption)**. A pair is given a load and a discharge port per cargo family,
  role and coast (`pipeline/freight/ports.py`, with the rows of `pipeline/freight/gateways/food.py`,
  `coasts.py` and `energy.py`). Every row has a port, a freight zone, the cargo families, the role
  (load, discharge or both), a source id and the page read, and a note of what the page says. The
  first row of a family and role is the country's principal gateway. When a country has no row for
  the cargo, the loader falls back, in this order, to a row of the same family for the other role
  (never for oil and gas terminals), the port of the earlier table for that family, the country's
  general-cargo row (food, fertiliser, metals), the earlier table's port, and the searoute port
  nearest the country's label point. Each port is published with its basis:
  - "page names the cargo" (a row whose page names this cargo at the port; it includes rows whose
    note records that the page does not give the direction or the period);
  - "page names the cargo in the other direction";
  - "page names the plant, not the cargo" (a row whose page names the steel works, the alumina refinery or another plant
    that the port serves, and not the cargo of the berth; the page gives no direction, so the row is one basis in both; the
    source link stays; Karadeniz Eregli and Iskenderun for scrap, pig iron and direct-reduced iron, and the
    port of Barcarena for alumina; the loading of refined products at Pengerang, Port Dickson, Mumbai and
    Vadinar, whose EIA brief names the refineries by town and does not say which of them exports, and at Si Racha, whose note says the same: it loads
    33 pairs of Thailand's refined-products exports, 6.23 Mt in 2024; since the sixth release these ports carry this label, on the lane Thailand to Singapore, the page of Thailand and the pairs file, and no tonne and no route moved);
  - "general port of the country";
  - "port used before, no page read" (the earlier table; shown as "no source page yet");
  - "nearest seaport" (also shown as "no source page yet").

  Share of 2024 pair-end tonnage as published in the pairs files (each seaborne pair counted at its
  two ends, 16,596 Mt; a port keeps the weakest basis of its uses in the file, for each role, and a
  transit port is one more port): page names the cargo 67.3%, port used before 22.5%, general port
  5.7%, nearest seaport 2.2%, other direction 1.1%, page names the plant 0.5%, no port (not routed) 0.7% (in the fifth release, which had no plant basis: page names the cargo 69.7%, port used before 22.4%, general port
  4.1%, nearest seaport 2.2%, other direction 1.1% and no port 0.6% of 15,847 Mt). Most rows cite a Wikipedia article. The United States crude and
  products ports of entry come from the EIA company-level imports file (2024); the crude discharge
  ports of Indonesia, Malaysia, Japan, South Korea and India and the products load ports of
  Malaysia, India and Thailand are the refinery towns of the EIA country briefs (a refinery is the
  evidence; the brief names the refinery, not the berth); Taiwan's crude ports are the two named by
  its EIA brief; the Netherlands' crude ports come from the Wikipedia list of oil refineries. LNG
  rows are the terminals of the atlas's own layer (GIIGNL annual report). A row for which no page
  was read is not added; the candidates are listed in the `UNSOURCED` tables of the three files.
- **Coast rules** (`COAST_RULES`, Atlas assumptions with their reason) choose a gateway from the
  other end of the pair: Russia by destination basin (Far East for East Asia, Black Sea for the
  Mediterranean, Baltic otherwise; crude for India may load on the Baltic or the Black Sea); Saudi
  crude loads at Ras Tanura, with Yanbu on the Red Sea as an option only for the buyers it reaches
  westbound through the Red Sea (from the EIA brief on Saudi Arabia: a record 18% of seaborne
  crude exports loaded at Yanbu in the second quarter of 2024; in the 2024 pairs 57.5 Mt of Saudi
  seaborne crude, 18.6%, is on the westbound side and 251.7 Mt on the other); South-East Asian coal
  into South China; Indonesian coal imports; Canada by ocean (Pacific gateways for Asia, Oceania and
  the Pacific coast of the Americas, St Lawrence and Atlantic otherwise); Saudi dry-cargo imports
  (Red Sea from west of Suez, the Gulf otherwise); Mexico, Colombia and the five countries of the
  Central American isthmus by the ocean of the other end; France by basin of the other end (the
  Mediterranean and the Black Sea take Fos, the countries of the Atlantic, the North Sea, the Baltic and
  the Americas take the Channel and Atlantic ports named by pages, Rouen and La Pallice for grain, Montoir
  for ammonia and soya meal, and Le Havre as the general port; Asia, the Gulf, East Africa and Oceania take the
  grain ports of Rouen and La Pallice and Fos for the other cargoes; four rules, for the grain exports by port (`fra-grain-ports`: see the
  grain paragraph of the new groups below), for the other grain flows, for the oils and fertilisers, and for general cargo); Turkey for scrap, pig iron and direct-reduced iron
  (Karadeniz Eregli for the partners of the Black Sea, Iskenderun and Izmir, the general port of the country on the Aegean, for the others, the page naming the
  steel works and not where scrap lands: Iskenderun is the principal port and Izmir the option of every pair of the Mediterranean basin, so that the lane
  page says that no source gives the split; both rows serve the two directions, since the page gives none, so that Turkish exports of the
  three groups to the Mediterranean load at Iskenderun and, since the sixth release, no longer at Izmir alone: 14 pairs). A rule that needs a product distinction
  that customs data do not make is not written (HS codes do not separate coking from thermal coal).
- **Coast options**. Where neither a single gateway nor a rule decides, a pair keeps up to three
  options per end. The main option is the principal gateway, not the shortest route ("nearest
  coast" would send every US soybean cargo for China to the Pacific Northwest); the others are
  listed with their distances ("9,251 nm from New Orleans, or 4,352 nm from Kalama"), with no
  weight. When a coast rule chose the principal port of such a lane, the lane page says so in the same sentence (`portRule` in the lane file: 181 lanes). No measured split is loaded (`pipeline/freight/splits/` is empty). Freight zones: 36, in
  `data/freight/zones.json`.
- **Geometry**: shortest sea path on Eurostat's SeaRoute maritime network, using the `searoute`
  package (version pinned at 1.6.0). Port coordinates come from the UN/LOCODE list bundled with the
  package, with terminals added by hand from their pages. Always avoided: the Northwest Passage,
  and the network's lane along 50 S that no cargo ship uses between South America and Asia (every
  edge with a point south of 42 S between 55 W and 140 E). Two passages are closed to every route:
  the Johor Strait, blocked by the Johor–Singapore Causeway, and the Kanmon Strait between Honshu
  and Kyushu (fairway 12 m deep in 2016, Japanese Wikipedia; too shallow for the bulk carriers and
  tankers the atlas routes).
- **River legs** (`pipeline/freight/river_legs.py`). The sea network ends on the coast, and a port far up a
  river has no node near it: Rouen is 53 km from the network, and snapped to a node on the coast near Dieppe, every lane from
  Rouen would start at sea and leave the Seine out of its distance (barley from France to the Netherlands would read
  196 nm, less than Le Havre to Rotterdam, 246 nm). A port of the table `RIVER_LEGS` (port, river, the node of the
  network at the river's mouth, the length of the leg in km, the page and its sentence) is routed from that node, and the leg
  is added to the distance of the main route and of every alternative and parallel option (`routing.route()`, which every
  plan goes through, so the days follow). The drawn line starts at the port's own point and runs to the mouth in one straight
  segment, not along the river; the lane, route and Route finder pages say so, with the page. Rouen: French Wikipedia, Port
  de Rouen, "L'activité portuaire se répartit tout au long de la Seine entre Rouen et Honfleur sur environ 120 km", read on
  24 November 2026: 120 km, 65 nm; the mouth is the node of the network nearest to Honfleur, which is 8 to 10 nm up the
  estuary from the node of Le Havre, so a route from Rouen is longer than the same route from Le Havre by the leg and that
  stretch. The same page gives another figure, "à 80 km de l'estuaire par le fleuve et à 6 heures de navigation": the 80 km are
  to the estuary, the 120 km are to Honfleur, at the far end of the estuary, where the network's node is; the leg is the 120 km,
  and the days of a lane count it at the lane's speed. Bremen, since the sixth release: 55 km from the network, it is the other
  port of an open choice of German lanes and never the principal port of a pair. No page read gives the length of the Weser between Bremen
  and Bremerhaven: the English Wikipedia page of the river, read on 24 November 2026, says "It passes through the Hanseatic city of Bremen.
  Its mouth is 50 km (31 mi) further north opposite the ports of Bremerhaven and Nordenham", a distance to the north that is shorter than
  the straight line between Bremen and the node of Bremerhaven, the one the router already used for Bremen (56.5 km), so it cannot be the
  length by river between these two points. The leg is that straight line, 56.5 km, 30 nm: an Atlas measure, the segment the map draws,
  and shorter than the river (the row says `"measure": "straight"`; a test recomputes it from the two points and requires every leg to
  be at least as long as the straight line between its ends). The caches of routes (`route_cache.json`, `geom_cache.json`) are keyed by the table. A test
  (`test_ports.py`) requires a leg for every port of a flow's gateway that is more than 50 km from the coast and the network;
  the other ports of the tables at 20 to 50 km from the network (estuary and river ports, and islands) are listed in
  `test_fnce.py`, which reads the port tables and fails when a port at that distance that is not on its list comes into one, and are not changed.
- **Passages crossed** are found geometrically. A gate is a short line drawn across a strait,
  canal or cape, both ends on land: 20 gates (`GATES`), the two capes as meridians 0.03 degree off
  20 E and 69 W so that no network node lies on them ("Cape Horn" includes the Strait of
  Magellan). A route crosses a gate when one of its segments intersects it under a half-open
  orientation test and the number of crossings is odd (a route that touches the line and turns back
  has not passed); longitudes are normalised, so crossings after the antimeridian are seen. The same
  gates forbid a passage when a route must avoid it.
- **Cape Horn rule**: a route may use Cape Horn or the Strait of Magellan unless one of its ports is
  on the Indian Ocean or Asian side: east of 20 E, outside the Mediterranean, the Black Sea and the
  Baltic (north of 30 N and west of 45 E), and not in the South Pacific (south of the equator and
  east of 140 E: eastern Australia, New Zealand, the Pacific islands may use the Horn). South
  Atlantic cargo for Asia therefore goes round the Cape of Good Hope. An alternative through the
  gate is named "Magellan Strait" or "Cape Horn" by where it crosses.
- **Canal limits**: classes that cannot transit laden are routed around the canal.
  - Panama: VLCC, Suezmax, Capesize, Newcastlemax and VLOC. Neopanamax locks allow 51.25 m beam
    and 15.24 m draft.
  - Suez: VLCC and VLOC. Draft is limited to 20.1 m.
- **Draught rule for straits** (`vessel_rules.py`): a class avoids a strait only when its laden
  draught, read on a cited page, exceeds the strait's limit, read on a cited page. Limits: Malacca
  and Singapore 20.5 m (the Malaccamax draught, the figure also quoted on the Malacca page of the
  atlas), Sunda 20.0 m (a minimum depth, used with no under-keel margin), Torres 12.2 m (ships of
  12.2 m static draught or less may transit). Draughts: VLOC 22.0 m (Valemax, lower figure of
  22 to 23 m loaded), Capesize 18.0 m, Handysize 10.0 m (Wikipedia, read in November 2026). So a VLOC
  avoids Malacca, Singapore, Sunda and Torres, and a Capesize avoids Torres. A class without a
  sourced draught is not restricted: Panamax and LNG carriers (their pages give a canal's maximum
  draft or the draft of the largest ships, not a laden draught of the class), Newcastlemax,
  Kamsarmax, Supramax, Ultramax, VLCC, Suezmax, Aframax, LR2, LR1, MR, handy tankers, VLGCs and
  container ships (no page figure). The list is repeated in `QA.md`.
- **Carrier practice**: Capesize, Newcastlemax, VLOC and VLCC voyages use the Cape of Good Hope
  instead of Suez when the Cape costs four extra days or fewer, because of canal tolls and draft
  limits. Suez is then shown as the shorter alternative.
- **Main route** = the shortest route under these rules for the lane's primary class.
- **Passages a cargo has to cross, and passages it may cross.** Customs data do not say which of
  two near-equal passages a ship took. Two groups of passages are treated as substitutes: Sunda,
  Malacca and Singapore, and Lombok and Makassar between the Indian Ocean and the South China Sea
  or the Pacific; and the Taiwan Strait and the Luzon Strait. For each group that the main route
  touches, the best route through each member is computed, and for each vessel class of the lane
  the members it may use under the draught rule and within 5% or 300 nm of its best one are kept
  (`PARALLEL_PCT`, `PARALLEL_NM`). A passage that every kept option crosses is one the cargo **has
  to cross** (`via`); otherwise the members are passages of which the cargo **may use one**
  (`viaAlt`, shown as "One of"). The same holds for coast options: a passage that only some port
  options cross goes to `viaAlt` ("May also cross"). The Korea Strait is also tested against the
  best route around it under the same limits (`ROUTE_AROUND`): from the Pacific to the Yellow Sea, a
  route south of Japan through the Osumi Strait is 1 to 4.5% longer than the network's route by the
  Tsugaru Strait and the Sea of Japan, so such cargo may cross it. "Has to cross" therefore means:
  no route of similar length (5% or 300 nm, per class, under the same limits) avoids the passage,
  among the parallel members, the port options and, for the Korea Strait, the route around it.
  Elsewhere the main route's passages are certain. Where no tonnage has to cross a passage (the "at
  least" figure rounds to nothing at the precision printed), the pages say so in words ("no cargo has
  to cross it", "none has to cross, up to 12% may") rather than print "at least 0". Applied to every passage, the same test would
  turn most of the "at least" tonnage of Lombok, Makassar and Ombai, and part of Dover's and
  Singapore's, into "may cross", through ways round the network offers (the Alas Strait, the
  Banda Sea, north of Scotland, the Durian Strait) that are not how these ships sail, against
  PortWatch's 950 and 1,085 Mt of dry cargo at Lombok and Makassar in 2024; the measurements are in
  the comment of `ROUTE_AROUND`, and `routing.classify(..., around=GATES)` gives that reading. The
  chokepoint pages name the routes of similar length that the atlas does not count as a choice
  (`parallelNote`). `QA.md` also prints
  the "at least" and "up to" tonnage of Malacca, Sunda, Lombok, the Taiwan Strait and Luzon at 3% or
  150 nm, 5% or 300 nm and 10% or 500 nm, recomputed from the cached option distances; the table
  says "Incomplete" and gives the tonnage left out when some pairs could not be recomputed.
- **Alternatives**: when the main route passes Suez or Bab el-Mandeb, the alternative avoids Suez,
  Bab el-Mandeb and Panama (so that "avoiding Suez" never goes through Panama). When it passes
  Panama, the alternative avoids Panama; when that one goes through Suez, a second one avoids Suez
  and Bab el-Mandeb too, labelled by the cape it rounds. Each carries its distance and extra laden
  days, and a Red Sea alternative carries the Red Sea status note. An alternative more than 3.0
  times as long as the main route is not shown; the lane then says "No practical sea alternative".
  A route through Hormuz has no sea alternative and none is invented.
- **Caches.** `pipeline/cache/route_cache.json` (every routed pair, no geometry) and
  `geom_cache.json` (lanes and routes with geometry) carry a version key computed from the gates,
  the parallel groups, the draught tables, the speeds, the rule constants, the routing code and the
  `searoute` release: a cache built under other rules is discarded at load. A cold build of the
  lanes takes about 15 minutes (943 s and 921 s measured in November 2026), a warm one under a minute.
- **Laden days** are distance ÷ typical laden speed for the class (`SPEED` in
  `pipeline/freight/vessel_rules.py`): 11 kn for Capesize, Newcastlemax and VLOC; 12 kn for
  Panamax, Kamsarmax, Supramax and Ultramax; 11.5 kn for Handysize; 12.5 kn for VLCC, MR and
  handy tankers; 13 kn for Suezmax, Aframax, LR1 and LR2; 15.5 kn for VLGCs; 12 kn for mid-size gas
  carriers; and 17 kn for LNG carriers and container ships. These are Atlas assumptions, published
  with each class (`vessel-classes.json`, source id `atlas`).
- **Generated corridors** (`pipeline/freight/generated_routes.py`, called by `build_freight.py`). The 133 hand-written
  routes name 43.5% of the 8,298 Mt of 2024 seaborne tonnes of the 71 customs groups. For the rest, the pairs table
  is grouped, for each group, into corridors: the freight zone of the typical loading port and the zone of the typical
  discharge port of each routed seaborne pair (a port with no zone in the pairs file takes the zone of the nearest port
  that has one, the same country first: only the name of a corridor depends on it). The corridors that no hand-written
  corridor names are ranked by the tonnes outside the hand-written corridors, and the largest become routes until the
  group reaches the target of 70% of its seaborne tonnes (hand-written routes counted), or has 12 generated routes. A
  corridor needs at least 0.5 Mt and 2% of its group outside the hand-written corridors, and at least half of its own
  tonnes outside them. What the zone-to-zone corridors leave out is grouped again with the importing zones merged into
  regions (Europe, East Asia, and so on: an Atlas grouping listed in the code). Unrouted pairs (no gateway, no sea
  route) are in no corridor, and neither is a pair that carries a caveat of the kind `landlocked-centre` (a declared destination or origin that is a landlocked
  trading centre: Qatar → Switzerland sulphur makes no corridor and no route "Sulphur: Qatar to Switzerland"; the next sulphur corridor, from the
  US Gulf to the east coast of South America, takes its place in the 20 routes of the fertilisers and sulphur). The cap on the whole atlas is 120 generated routes for the groups of the first batch, which the routes of the last release may exceed (a published route stays, see below): the map draws every route, and a larger
  number made the world view unreadable even with the generated lines drawn thinner (about 120 more lines on top of the
  hand-written ones, 133 in November 2026). When the lists exceed it, the first corridor of each group that the audit's entries on named routes name is
  kept first (crude oil, iron ore, coal, refined products, LNG, steel, manganese, alumina, sugar, rice, rapeseed,
  coffee, cocoa, cotton, phosphate rock, DAP, urea, soybean meal, palm oil, corn, wheat, potash, soybeans), then the
  corridors are taken by their tonnes across groups, each group's in its own order, so that no corridor is left out
  for a smaller one of another group (before this rule, the first corridor of every group came first, and three
  corridors of 1.1 to 1.5 Mt gave way to corridors of 0.5 Mt of the minor metals). The groups added after this rule was
  set have a cap of routes of their own for each batch of groups added together, their first corridors first, so that no earlier route is dropped
  when a group is added (`LATER_GROUPS`; a group above 10 Mt of seaborne trade keeps its two largest corridors before the rest of the
  batch's cap is shared by tonnes, so that the tonnes alone do not give one group ten routes and another one: sulphur ten and ammonia one, if the ten
  groups of fertilisers and sulphur shared their 20 routes that way): 20 routes for the fertilisers and sulphur, 10 for the eight groups
  of grains, oilseeds and pulses, 10 for the nine groups of metal bulks (ferrous scrap, chromium
  ore, pig iron, direct-reduced iron, coke and four ferro-alloys), and 6 for ammonium nitrate with limestone and the two-nutrient compounds. The result for 2024 is 168
  generated routes (122, 20, 10, 10 and 6) over 71 groups beside 133 hand-written ones (301 routes), and 65.0% of the seaborne tonnes named (all
  groups; 43.5% by the hand-written routes alone): ten of the 71 groups reach 70% (iron
  ore, coal, crude oil, corn, soybeans, bauxite, chromium ore, ferro-nickel, nickel ore and spodumene); the others stay short of
  it, among them LPG (69.0%: the Mediterranean corridor that would take it past 70% has no place left under the cap, see the LPG paragraph of section 1),
  steel (45%) and refined products (53%), whose trade is spread over thousands of small pairs, and the
  groups whose corridors are all smaller than those kept (aluminium, refined copper, zinc concentrate, the minor
  metals: no generated route). `pipeline/freight/QA_routes.md`, written at each build, gives each
  group with its coverage, its reason when it is under the target, and the corridors the cap left out.
  **A generated route of the last release stays while its corridor exists.** The ids of the generated routes of the last release are in
  `pipeline/freight/released_ids.json`, written at each release by `pipeline/freight/release_ids.py` from the published `routes.json` (`docs/UPDATING.md`).
  A route of that list is generated again, whatever the caps and the other floors (the share of the group's tonnes, the share of the corridor that no
  hand-written route names, the target), as long as the routed seaborne pairs between its two ends (the zone of the loading ports, and the zone or region of the discharge
  ports) still add up to the floor of 0.5 Mt (`FLOOR_MT`); its pairs are taken first, so no new corridor shares one. The caps count these routes and the new
  corridors take the places that are left under them: a cap never puts a published route out, and a new corridor enters only while a cap is not full. A route
  whose corridor no longer exists is listed with its reason in `QA_routes.md` and leaves the atlas. The caps are 12 routes per group and 120 for the groups of
  the first batch (the sixth release published 122 of them, which therefore all stay, and no new corridor of that batch enters), and the batches of later groups keep
  their own caps. No raised cap and no exception for a group (wheat had a thirteenth corridor for that purpose) is needed to keep a published route.
  The corridors are made from the zone of each pair's ports, so since France has its Channel and Atlantic ports (sixth release) the
  corridors of the earlier groups that hold French pairs moved with them: of the 120 generated routes of the fifth release, nine
  changed in their tonnes, pairs and history (cocoa, coffee, soybeans, two of soymeal, two of steel, sugar from East Coast South America to the Mediterranean, and wheat within the Mediterranean, `gen-wheat-med-med`,
  which is now French wheat to Egypt: Fos to Alexandria, 1,451 nm, instead of France to Algeria, 539 nm) and two are no longer generated, both because their corridor was French and
  French steel and wheat load at other ports now: `gen-steel-med-nw-europe` (steel from the Mediterranean to North-West Europe) and `gen-wheat-med-waf` (wheat from the Mediterranean to
  West Africa). Two routes of the fifth release, `gen-sugar-sea-sea` (sugar within South-East Asia, 2.3 Mt) and
  `gen-wheat-canada-west-r-east-asia` (wheat from West Canada to East Asia, 3.8 Mt), would have been pushed out by the cap of 120 and by the cap of 12 routes of the wheat group, not by anything on their side: a route is never put out by a cap (below).
  The four new corridors of the earlier groups are wheat from North-West Europe to West Africa and within North-West Europe, steel from
  the Black Sea to the Mediterranean and rapeseed from Western Australia to North-West Europe. The 133 hand-written routes are identical to those of the fifth release, field by field, and no pair of a
  group of the fifth release that has no French end differs from the pairs files of the fifth release in its ports, class, distance or passages (`test_fncf.py` compares each hand-written route
  and each pairs file with a digest of the fifth release's); the notes of the 11 generated routes
  built on a single pair now say "pair" in the singular. Two kinds of pair of the groups of the fifth release moved with France's ports without being a
  French grain or oilseed pair: the three Russian pairs of DAP, potash and urea to France changed their discharge port from Fos to Le Havre (3,267 to 1,422 nm: the
  fertiliser rule puts Russia on the Atlantic side, for Ust-Luga), and sixteen pairs of sugar (Mauritius, Thailand, Morocco, Algeria, El Salvador, the United Arab
  Emirates, the Philippines and others, with France, both ways) changed their list of passages with the same ports and the same distance: an open pair now has two
  French options, Fos and Le Havre, and a passage that only one of them crosses (Gibraltar for most of them, the Cape of Good Hope for France to South Africa) is a
  passage the pair "may cross" and no longer one it "has to cross". The "at least" tonnes of the sugar of the fifth release at Suez, Bab el-Mandeb and Gibraltar move by a few kt for this
  reason (`test_fncg.py` G9 lists the sixteen and compares them with the pairs files of the fifth release). A link to a route that ended shows "This route is not in the atlas catalogue" and a
  button to the Freight view, the list of routes by vessel class.

  A generated route is the atlas's own corridor, never a market benchmark: its id starts with `gen-` (group, exporting
  zone, importing zone or region), its name is "Cargo: zone to zone", its source is `atlas`, and its page says
  "Atlas corridor, generated from customs pairs". An end is named for a country, not a zone, when that country holds at
  least 80% of the tonnes of the end (counted by the customs country of the corridor's pairs, not by the country of
  their port: Belarusian potash loads at St Petersburg and its corridor is "Potash: Belarus to North China"), unless the zone's own name
  already says the country ("Eastern Australia", "US Gulf"): "West Africa" would send a reader to Nigeria or Ghana for
  cargo that loads in Morocco, so the corridor is "Phosphate rock: Morocco to the Mediterranean" and the note gives the
  shares. The name depends on the data only, so it is the same from run to run. Its ports, vessel class, distance and passages are those of the
  largest pair of its corridor, planned with the same call and the same class list as the lanes and the Route finder
  (`build_lanes._classes_and_plan`), so that the Route finder gives the same ports, distance and passages for that
  pair: the passages are the pair's own (those of its lane, or of its pairs row: the passages that every port option
  crosses, and those that some option or a parallel passage may cross), not those of the drawn line, which is the main
  port option's and may cross more. A test compares them over all generated routes. Its corridor lists exactly the pairs it holds (one entry per exporter), so a pair belongs to one generated
  corridor only; its share of the group's seaborne tonnes, its 2005 to 2024 volume history and, for the classes whose
  cargo base the atlas covers, its share of the class's tonne-miles follow the rules of the hand-written routes. When a
  hand-written route already names some of its pairs, the note says which and how many Mt. The note also says that the
  ports are the atlas's typical ports (an assumption): the route stands for the corridor, not for each pair.

  A hand-written route has ports of its own (a benchmark's named ports, or the terminals its editor chose), which are
  often not the typical ports of the Route finder. Where the largest pair of its corridor runs between other ports, the
  route page says so with that pair's ports and distance ("In the Route finder"); the page says that its own distance is
  for its own ports and that the share, the history and the tonne-miles count every port of the countries of the corridor.
  A corridor entry that does not name a customs group lists the groups of its commodity (`gs`), and a lane or a Route
  finder answer lists a route only when its group is one of them (refined copper is not copper concentrate). The name of a port in `routes_def.json`
  is matched to the port tables; a terminal named for a cargo (the Dongjiakou LNG terminal) is no longer taken for the
  port of the place it names (Qingdao) on a route that does not carry that cargo. Where the match went to another place
  (Portland, Maine for Portland, Oregon; Bilbao for Huelva; Angra dos Reis for Acu; the CPC terminal for the port of
  Novorossiysk; and others), an explicit entry (`PORT_CODE` in `build_freight.py`) names the port; a port the engine's
  table lacks, or places far from the port (Dos Bocas, Kashima), takes the sourced position of the atlas's port asset.
  A drawn line starts and ends at a node of the sea-lane network, not at the port: most lines end within about 100 km of
  their port (up to 94 km, at Saldanha Bay, Antofagasta and Richards Bay), because the network has no node nearer. Where
  the nearest node is more than 100 km away (TD9 at Covenas, TD14 at Seria, S8_63 at Paradip, the Kamsar and Acu
  routes), the line is joined to the port by a straight segment that crosses no land of the base map, from the nearest
  node that allows one, and the segment's length is added to the distance. TD6 is routed round the Peloponnese: the
  network's shortest path crosses the Corinth isthmus. The end country of a route (country isolation) is the country of
  its terminal where the port table or the asset records it (the Basrah Oil Terminal is Iraqi although its point is
  nearer the Iranian coast), else the country of the nearest land.
- **Benchmark routes.** Each Baltic Exchange benchmark carries its published definition (`definition` in
  `routes_def.json`): code, vessel, cargo and quantity, load and discharge ports (delivery and redelivery areas for a
  time-charter trip), duration, status with its date and page, and the page and month it was read (the Guide to
  Market Benchmarks, version 7.09, the Baltic Exchange's dry, tanker and gas service pages and its circulars, read in
  November 2026). An ended benchmark stays in the atlas, marked discontinued with its date and the route that replaced
  it. The indices and averages a benchmark weighs in come from `baltic_indices.json` (members and weights as
  published); the route page lists the members and, when the atlas lacks some of them, the share of the weight it has.
  No index value is stored or shown. "Laden days" is the drawn distance divided by the class's assumed laden speed: no
  port time, no canal wait, no ballast leg (the voyage calculator of a route page counts its sea days at the standard
  vessel's speed, with the fuel of that speed; see "Voyage calculator" below); the route page shows the duration of the definition beside it when the
  definition gives one (time-charter trips and round voyages). A time-charter benchmark whose definition names no
  cargo has no corridor and says so; its line is a laden leg chosen by the atlas or the trace of another route (a
  "stand-in"), and its note says which. The definition says only what the document says: most dirty-tanker
  definitions give a tonnage and no cargo name, so the table reads "cargo not named in the definition", and the cargo
  tag "crude oil" is the atlas's reading, said in the route's note on its cargo. The parcel and the duration tiles carry
  the year of their document; the three LNG benchmarks give the capacity of their standard carrier, shown as "Vessel
  size", not a cargo size. The Baltic Exchange's website terms restrict copying its content: the atlas states each
  definition as facts (ports, quantities, durations, weights, dates) in its own words with a link to the document, and
  every benchmark page says that the definition is the Baltic Exchange's, that the atlas is not affiliated with it and
  that index values are proprietary and not shown. In November 2026 the atlas has 90 benchmarks (85 active, 5 ended):
  56 give a cargo size, 54 have a corridor of customs pairs, 48 a corridor share and 53 a volume history. Every
  benchmark without a share says why; TC11, TC22 and TD34, whose flows a generated corridor counts, link to it.
- **Curated tables.** Some rules are entered by hand and are Atlas judgements, not figures from a
  dataset: the mode lists (`modes.py`), the gateway rows and coast rules (`gateways/*.py`), the
  transit ports (`gateways/energy.py`), the vessel class rules and the draught tables
  (`vessel_rules.py`), the gates and routing constants (`routing.py`), the benchmark route
  definitions (`routes_def.json`) and the vessel size ranges (`vessel_classes.json`). Each entry
  gives its reason and, where a page was read, the page. The size ranges are conventional industry
  ranges, not a single authoritative table; `pipeline/freight/NOTES_routes.md` lists the pages read for the
  benchmark definitions and what they could not settle.

### Voyage calculator

A route page that describes a laden voyage has a folded block "Voyage calculator" (`web/src/components/views/RouteVoyage.tsx`,
the arithmetic in `web/src/lib/voyage.ts`). It is a calculation on figures the visitor types. It is not a market rate, not a
quote and not a Baltic Exchange assessment, and the atlas stores and publishes no result of it. It runs in the visitor's
browser on files the page has already loaded: it adds no request, no data file and no scheduled job. What the visitor types
stays in the memory of the page, by route, until the page is reloaded; it is written neither to the address of the page nor
to the browser's storage, so a copied link carries none of it. It gives two results: the freight, in USD a tonne, that covers
a hire the visitor types, and the time-charter equivalent, in USD a day, of a freight the visitor types.

The formulas, with Q the cargo (t), Dl and Db the laden and ballast distances (nm), vl and vb the speeds (kn), cl and cb the
fuel a day (t), P the port and canal days, Fp the port fuel (t), p the bunker price (USD/t), H the hire (USD/day) and F the
freight (USD/t). One knot is one nautical mile an hour.

```
Sl = Dl / (24 * vl)             laden sea days
Sb = Db / (24 * vb)             ballast sea days (0 when Db is 0)
T = Sl + Sb + P                 round-voyage days
M = cl * Sl + cb * Sb + Fp      tonnes of fuel
B = M * p                       bunker cost, USD
X = tolls + portcosts           canal tolls and port costs, USD
freight = (H * T + B + X) / Q   the freight that covers the hire H, USD/t
TCE = (F * Q - B - X) / T       the time-charter equivalent of the freight F, USD/day
```

A result is empty when one of its inputs is empty or is not a number above zero. A ballast distance of 0 needs no ballast speed
and no ballast fuel. Port and canal days, port fuel, canal tolls and port costs may be zero. A time-charter equivalent below
zero is shown with a minus sign. Without a cargo size the two results are empty and the days, the fuel and the bunker cost are
still given; without a bunker price the results are empty and the days and the fuel are still given.

Which routes have the block. A route has none when it is: a round-voyage benchmark; a time-charter trip, a benchmark defined
from delivery to redelivery with a duration; a trip drawn as its laden leg; a stand-in trace or an ended benchmark; a container
route (freight is per TEU, with no standard vessel). For the first four the distance of the page is not the voyage the
benchmark defines, or the benchmark no longer exists, and the calculator would answer another question than the page asks.
The number of routes that have a block is not written here: it moves with the routes, and a test compares the reasons with the
code.

What each field starts from. Every default has its source and its year beside it in the block, and a field that no file holds
and the atlas does not supply starts empty.
- Cargo, t: the parcel of the benchmark definition, when the definition gives it in tonnes (source and year of the definition;
  the smaller one, and the line says so, when the definition allows two sizes, as C5 does); else empty (a route whose definition gives the capacity of its carrier, not a cargo, has none).
- Laden distance, nm: the distance of the routing chosen, as the Distance tile shows it (the SeaRoute network, no year). The
  routing is the main one or an alternative that has a distance of its own; the parallel passages listed beside a route have
  none and are not offered. The distance is shown, not typed.
- Ballast distance, nm: the laden distance of the routing chosen, an Atlas estimate (source id `atlas`, no year): the ship is
  taken to return in ballast by the same routing. The benchmark definitions give no ballast leg. It is wrong for a backhaul and
  differs from the Baltic's own time-charter equivalent, which counts a ballast leg from a named starting place to the loading
  port. The visitor types another distance, or 0.
- Speeds and fuel, kn and t a day: the speed and the fuel of the Baltic Exchange's standard vessel of the class, laden and in
  ballast, as the class page states them (`std` in `vessel-classes.json`: source, year and page there). The figures are those of
  the speed shown: nothing is scaled when the visitor changes a speed, because the atlas holds one speed and one fuel line for
  each standard vessel; a visitor who types another speed types the fuel that goes with it. Only the fuel-oil figure is used.
  A class that has no standard vessel of its own takes that of the class its benchmark names (Supramax: Ultramax; Panamax:
  Kamsarmax; Newcastlemax: Capesize), and the block says which. A class with none (the mid-size gas carrier, the chemical
  tanker) takes the laden speed assumed for the class, the one the page's laden days use (Atlas assumption), the same speed in
  ballast (Atlas estimate), and no fuel. The LNG carrier takes its speed but no fuel: the benchmarks the atlas shows, BLNG1-174 to
  BLNG3-174, are defined for a carrier "burning LNG fuel" (Guide to Market Benchmarks, version 7.09; the older BLNG1 to BLNG3
  say "burning marine fuel oil to reposition"). The guide gives two figures for the same ship, tonnes of marine fuel oil and
  cubic metres of LNG a day; the atlas holds the fuel-oil figure only, and a fuel-oil figure would not describe a ship that
  burns LNG: the standard vessel of the class is the Baltic's LNG carrier of 174,000 cbm, whose benchmarks are defined
  "burning LNG fuel", so the fuel fields start empty.
  All of these figures are read through one function (`standardVessel`), so that a single line switches them off.
- No default: port and canal days, port fuel, bunker price, port costs, canal tolls, hire, freight. They are typed. The
  atlas stores no bunker price and no rate: the sources of the kind are proprietary (see "Freight rates that are not stored",
  section 7).

The sea days of the block (distance over the standard vessel's speed) differ on purpose from the "Laden days" of the page
(distance over the speed assumed for the class): the first goes with the fuel figure of the standard vessel, the second is a
class assumption, and each says which it is.

Counted as zero when empty: port and canal days, port fuel, canal tolls, port costs. The block names the ones that are empty.
Not counted, unless the visitor puts them into the port costs: a weather allowance, commissions, insurance, demurrage and
despatch, off-hire, charges for emissions or ballast water, dues of passages other than the two canals (the Turkish straits,
for example, which some routes cross), and any gas oil that a standard vessel's description adds to its fuel oil. Port fuel is typed in tonnes and counted at the bunker price. The Baltic Exchange's own time-charter equivalent
(Guide to Market Benchmarks, Appendix 3) counts fuel burned in port, a weather allowance and commissions, with the port costs
and the voyage costs it lists; this calculator counts only what is typed, and its result is not that value, whatever it is named.
A standard vessel is the Baltic's reference ship, not the ship of any real voyage.

Canal tolls. The field "Canal tolls, round voyage, USD" appears when the routing chosen crosses the Suez or the Panama Canal
(the routing chosen, not the parallel passages listed beside it), and the visitor types the tolls of the whole round voyage.
No toll figure is held or copied. The Panama Canal Authority's tariff
(https://pancanal.com/en/maritime-services/maritime-tariff/) depends on the size category of the vessel and the locks used,
and differs for a vessel in ballast. The Suez Canal Authority's tolls table
(https://www.suezcanal.gov.eg/English/Navigation/Tolls/Pages/TollsTable.aspx) loads its rows for a chosen category and dates,
says that the rates apply "according to the vessel's actual condition upon transit", and lists periodical circulars that renew
the rates of categories of vessel. The atlas holds neither a size category nor the circulars in force. Neither site states that its tariff may be republished: the
Panama Canal Authority's Terms of Use (https://pancanal.com/en/terms-of-use/, read on 25 November 2026) say that "their
copying, distribution, transmission, reproduction or publication for commercial or lucrative purposes is prohibited" and that
their use for such purposes "requires prior express authorization from the Panama Canal Authority"; the Suez Canal Authority's
pages carry the line "Copyright 2017 | All Right Reserved Suez Canal Authority" (read on 25 November 2026), and no page read
states terms of reuse. The atlas links the two pages from the field and credits them in NOTICE.md; they are linked, not copied, and they are
not entries of the registry of sources, which lists the sources of figures.

The Baltic Exchange's terms and this use. The calculator computes, in the visitor's browser, with the speed and the fuel of the
Baltic standard vessels that the class pages already state; the atlas stores no figure derived from them, shows no index value
and offers no download. It is a new use of figures the atlas already states as facts, and the decision of 24 November 2026 on
the Baltic Exchange's facts covers the facts shown on the site, not a computation with them: this use is a choice made without
the owner, listed in PROGRESS.md. What the Baltic's pages say, read on 25 November 2026: clause 5.1 of its Terms and Conditions
(https://www.balticexchange.com/en/site-services/terms-and-conditions.html) says that no part of the website or its content "may
be copied or reproduced (except for your personal use), shared with third parties, reverse engineered, reverse assembled, or used
to create any derivative work (whether in physical or electronic form) without the prior written consent of the Baltic except to
the extent specifically permitted under the terms of the level of your subscription for Baltic Data as set out in the Baltic Data
Policy". The Data Policy (https://www.balticexchange.com/en/site-services/data-policy.html) says that its subscribers "have access
to a range of indices and other market data produced by the Baltic" (clause 1.2), and that the holder of a licence shall not
"display Baltic Data on any intranet or public website" and shall not "use ... Baltic Data to create derived data, including
pricing data or other information that would be created in whole or in part from Baltic Data" (clause 2.2.3, a Restricted Baltic Data
Licence; clauses 2.3.3 and 4.2 are close in wording, for a Full Baltic Data Licence and for a client of a channel partner).
Neither page says whether the descriptions of the standard vessels are Baltic Data, or whether a reader without a licence is bound
by the policy: that is not settled. If the owner answers that the calculator may not use them, one line (`standardVessel`) leaves
the speed and fuel fields empty. The `baltic` entry of the registry names this use.
- The block says "not a Baltic Exchange assessment", and its tiles are named "Freight to cover the hire" and "Time-charter
  equivalent" of the figure typed; they cite no source because they are calculations.

## 4. Vessel classes per lane

Typical classes follow standard practice: cargo size, loading and discharge port draft, and canal
limits. The rules are in `pipeline/freight/vessel_rules.py`. Examples:

- Pilbara and Brazil iron ore to China: Capesize, with Valemax-type VLOCs for Brazil.
- Indonesian coal: Supramax and Panamax (shallow loading, barge transhipment).
- Black Sea wheat to the Mediterranean and Middle East: Supramax and Handysize.
- Middle East Gulf crude to Asia: VLCC.
- LPG: a VLGC parcel is 44 kt (the Baltic BLPG reference vessel), so a lane that loads less than one
  parcel a week (2.29 Mt a year) does not keep a VLGC busy. Short hauls (under 1,000 nm) are served
  by mid-size gas carriers (25,000 to 50,000 cbm), with the VLGC second when the lane is large;
  medium hauls (under 3,000 nm) of small lanes by mid-size carriers, then VLGCs; long hauls and
  large lanes by VLGCs. The two distances are Atlas assumptions.
- Palm oil and soybean oil: MR first, chemical tanker second. Vegetable oils move in chemical tankers, and the Baltic
  Exchange assesses their freight basis 40,000 t shipments (Baltic Chemical and Agricultural Oil Assessments), the
  size of the MR benchmark cargoes (37,000 to 40,000 t) and more than the largest chemical tanker of the Wikipedia
  scale (35,000 dwt), which is why the MR comes first.
- Ammonia, UAN solution and phosphoric acid are not dry bulk. Anhydrous ammonia is a
  refrigerated liquid and goes in gas carriers like LPG: the mid-size gas carrier first, the VLGC second. UAN solution and
  phosphoric acid are liquids and go in chemical tankers: the chemical tanker first, the Handy tanker second. These
  classes are an Atlas assumption: no page was read for the class of these three cargoes, and the lane, route and
  country pages call them "typical" like every other. The other new fertilisers (MAP, superphosphates, NPK and the two-nutrient compounds, ammonium sulphate,
  ammonium nitrate and ammonium nitrate with limestone, potassium sulphate) and sulphur take the class of urea, DAP and potash: Supramax first, Handysize
  second. The three liquids are compared with the tankers of IMF PortWatch in the chokepoint estimates, the others
  with its dry bulk ships.
- The grains, oilseeds and pulses added in the sixth release fall in the families that exist. Barley, sorghum, sunflower
  seed, sunflower meal, rapeseed meal and dried pulses are dry cargo like wheat, corn and soybean meal and take their rule
  (Supramax and Handysize, with Kamsarmax first for a lane of more than 1 Mt from the United States, Brazil, Argentina,
  Canada or Australia). Sunflower oil and rapeseed oil (with the safflower and mustard oil of the same codes) are vegetable
  oils and take the rule of palm oil and soybean oil: MR first, chemical tanker second, and the tanker comparison of the
  chokepoint estimates. No new rule was written; the classes are Atlas assumptions as for every lane, and the vessel
  catalogue lists the sunflower and rapeseed pages among the cargoes of the classes concerned.
- The metal bulks added in the sixth release fall in the rules that exist. Ferrous scrap, chromium ore, pig iron,
  direct-reduced iron and coke take the rule of steel: Supramax first, Handysize second (parcels of a few tens of thousands
  of tonnes in geared handy bulk carriers); the four ferro-alloys with lanes (ferro-chromium, ferro-manganese,
  silico-manganese, ferro-silicon) take the rule of the minor metals that sail in bags and boxes: container ship first,
  Handysize second, and are compared with the container, general-cargo and ro-ro ships of PortWatch in the chokepoint
  estimates, the others with its dry-bulk ships. These classes are Atlas assumptions: no page was read for the class of
  these lanes. The vessel catalogue lists the new pages (and the metallurgical coal page, for coke) among the cargoes of the
  classes concerned.
- Where only one group of a page sails in a class, the class page names the product on the cargo chip and the chip still opens the page
  (`cargoLabels` of `vessel_classes.json`): the Urea & nitrogen page is "Ammonia" on the gas carriers and "UAN solution" on the
  chemical and handy tankers, the Phosphate page "Phosphoric acid" on the tankers, the Sunflower and Rapeseed pages the oils on the tankers, and the
  Metallurgical coal page "Coke" on the Supramax and Handysize.

These are labelled "typical" in the interface (lane and route tooltips, the route list, the lane table and its CSV
column `typical_vessel_class`); a benchmark's class is the class of its definition and is not called typical. They are not measured shares of each class: no free source measures how
a trade splits between vessel classes (that would take ship-by-ship tracking, which the atlas does not use), so the
class of a lane, a country pair or a route is a rule, not a measurement.

Class pages. Each size band names the page that supports it and the year of that page (Wikipedia's ship-size
articles, the Wilhelmsen page of LPG carrier sizes); where the Atlas sets a bound itself, so that the bands of one
segment neither overlap nor leave a gap, the band is labelled "Atlas convention" and its note says which page gives
what. Classes defined by a port or a cargo (Newcastlemax, Kamsarmax, LR2, chemical tanker) sit inside or beside the
size steps on purpose; large gas carriers (50,000 to 70,000 cbm) are left out because no lane rule uses them. The
typical size is a page's figure where one is given (a Baltic Exchange standard vessel, a Wikipedia article:
Newcastlemax takes the article's 185,000 dwt), else an Atlas convention, labelled so (Panamax 74,000 dwt and Supramax
58,000 dwt, the sizes in the names of the Baltic's derived P4TC and S10TC averages, for which the Baltic describes no
vessel). The standard vessel gives the figures of the Baltic Exchange's standard ship of its time-charter routes:
for dry bulk from its dry services page, for tankers and gas carriers from its Guide to Market Benchmarks (version
7.09, December 2025), stated as facts in the atlas's words with a link to the page (the Baltic Exchange's site terms
restrict copying; see the `baltic` entry of DATA_SOURCES.md). The Suezmax adds the beam of Wikipedia's typical ship;
the VLOC, which has no Baltic standard vessel, shows the typical ship of its Wikipedia article. Laden days use the assumed laden service speed of the class, not the
standard vessel's speed; the voyage calculator of the route pages takes the standard vessel's speed with its fuel figure ("Voyage calculator" in section 3). A class page lists the routes of its class, ended benchmarks last, then, under "Also served
by", routes of another class that it also serves (the Kamsarmax benchmarks on the Panamax page, the palm oil route on
the chemical tanker page); choosing a class in the side panel shows both. The world fleet is UNCTADstat's count by ship type
(oil tankers, bulk carriers, container ships), rebuilt by `pipeline/freight/fleet.py`: it covers every ship of the
type, not one commercial class, whose fleet, age and orderbook are not published for free.

## 5. Shares

- **Route share of a commodity's seaborne trade** = corridor volume ÷ world seaborne volume of
  that commodity, both from BACI for the latest year. The corridor is the set of origin and
  destination countries the route represents, listed per route in `routes_def.json`. It is a
  country-pair volume (all ports and vessel sizes, not the route's own ports), so routes that share
  a country pair show the same tonnes and must not be added up.
  - A customs group is counted once per country pair and route (thermal and metallurgical coal
    are one group, "coal").
  - Pairs that move both by sea and overland are not counted; the note gives their tonnage. A
    corridor with no seaborne tonnage at all but a mixed one (Russian crude to China, route
    `kozmino-china-espo`: 108.5 Mt in 2024, all modes) gets no share: its page gives the all-modes
    volume, and its history is labelled "All modes".
  - A share that rounds to 0.0% is not shown: the route page says "n/a" with the reason (corridor
    too small, no seaborne flow, or no corridor for that benchmark).
- **Route share of vessel-class activity** (Atlas estimate) = corridor tonne-miles ÷ total
  tonne-miles of all routed seaborne pairs of the latest year whose typical primary class belongs to
  the same size family (for example Capesize, Newcastlemax and VLOC together). Tonne-miles are the
  pair's tonnes × the routed distance of its main port option (pairs table).
  - It is published only for Capesize (with Newcastlemax and VLOC), VLCC, LNG carriers and VLGC,
    where the atlas's commodity list covers nearly all of the class's cargo. For the other
    classes (Handysize, Supramax, Panamax, the smaller tankers) the main cargoes are outside the
    atlas, so no share is shown.
  - Routes that share a corridor (C3 and the Valemax route, for example) count the same tonnes.
- **Lane share of seaborne trade** = lane volume ÷ the group's seaborne tonnes. A mixed lane has
  none (its tonnage is for all modes).
- **Lane share of destination imports** = lane volume ÷ the destination's total imports of that
  commodity group (all modes). It is not written when the lane's tonnage is an Atlas estimate.
- **Chokepoint commodity share** (Atlas estimate, `estimates` of `data/freight/chokepoints.json`).
  One definition, over every recorded seaborne pair of the latest year (sea and sea via a transit
  port, lanes or not, routed as in section 3) and every lane group:
  - **at least**: the customs tonnage of every recorded seaborne pair whose assumed route has to
    cross this passage. Pairs that can use a parallel passage of similar length, pairs split
    between coasts, mixed sea-and-land pairs and trades that customs data do not record are not in
    it;
  - **up to**: adds the pairs that may cross it, or a parallel passage of similar length, or may
    load or discharge on another coast (the note names the largest origins);
  - both are shares of the group's seaborne tonnes, the figure of the commodity page, not of the
    routed tonnes. Where the two agree, one figure is shown. An entry is written when the "up to" figure
    that the page prints (after the PortWatch cap below) is at least 2% of the group or 1 Mt: 967
    entries over 20 passages in 2024 (Hormuz: 37 groups).
  - **What is missing**, stated in each note: the seaborne tonnage of the group that could not be
    routed, the mixed pairs that would cross the passage by sea (not counted), and the origins
    whose exports customs data do not record or record only in part (caveats), named when the
    routes to their main buyers (every buyer with 10% or more of the origin's exports in the
    reference year) cross the passage or may cross it.
  - **PortWatch cap**: IMF PortWatch estimates the cargo of all ships through a passage by vessel
    type. The groups are compared by type: tankers (crude, refined products, LNG, LPG, vegetable
    oils), container, general cargo and ro-ro ships (steel, refined copper, aluminium, coffee, cocoa,
    cotton), dry bulk (the rest). Where the passage has its own counter, the published "up to"
    figure of a group is capped at PortWatch's volume of its type in the same year less the "at
    least" tonnage of the other groups of that type, and never below the group's own "at least"
    (Taiwan Strait iron ore: at least 3.0%, up to 64.9%, capped at PortWatch's 1,061 Mt of dry bulk
    in 2024). That subtraction is used only while the 'at least' tonnage of the type is at most 85% of
    PortWatch's volume (`PW_NEAR` in `build_freight.py`). Above that the two sides are too close
    to compare: the atlas's groups are not all the cargo these ships carry, and with the two sides this
    close the room left for each group is only the margin of the assumed ports and routes (the groups
    added in 2026 took the dry-bulk 'at least' tonnage at the Bosphorus from 88% of PortWatch's
    volume (179 against 203 Mt) to 102% (207 against 203 Mt) and at Gibraltar from 85% to 103% (394 against 384 Mt), which had emptied the 'up to' figure of every dry
    group there and removed three estimates of the fifth release). The rule is then one of two:
    - **Whole volume** (`cap_regime` "whole" in `build_freight.py`): the 'up to' figure of a group is
      capped at PortWatch's whole volume of the type in the year, never below the group's own 'at
      least', without subtracting the other groups. A group cannot exceed the whole volume of its
      ship type. In 2024 this is the rule at the Bosphorus, Gibraltar, Hormuz, Panama and Torres
      Strait (tankers or dry bulk, at 90% to 103% of PortWatch's volume), and at Lombok and Makassar
      (dry bulk, 89% and 94%). It binds on four groups of 138 estimates: iron ore at Lombok (up to 950.3 Mt, the
      whole of PortWatch's dry bulk there) and at Makassar (1,084.7 Mt), LNG and refined products
      at the Torres Strait (13.5 Mt, the whole of PortWatch's tankers there). The note of such a
      figure says "capped at IMF PortWatch's estimate of the cargo of all ... ships ..., which this
      cargo cannot exceed" and does not speak of the other groups; the note of the ship type, on the passage, says the rule (a group's
      'up to' cannot exceed the whole of PortWatch's volume of these ships, N Mt) and on how many groups of the type it binds, the
      ones the interface tags.
    - **No cap** ("none"): where the 'at least' tonnage of the type is itself above PortWatch's
      volume of the year and an alert on the passage explains it. This is Suez and Bab el-Mandeb
      in 2024 (dry bulk, tankers and, at Bab el-Mandeb, general cargo): the atlas routes cargo on
      the normal itinerary while most ships avoided the Red Sea, so the figures are tonnages of
      the normal route and the year's traffic is not a ceiling for them. The note says so.
    The floor test (2% of the group or 1 Mt) uses the figure that is published.
    **The note of a ship type** is written once on the passage record (`typeNotes` of `chokepoints.json`, one object by ship type that has
    something to say: the 'at least' sum of the type, PortWatch's volume of the year and its best year, the regime of the cap, the number of groups of
    the type and of those that the cap cuts, a line `line` and its reason `n`), and not in the note of each estimate, where it had been repeated (the same
    paragraph on 31 rows at the Bosphorus, 38 at Gibraltar and 48 at Suez; the file was 882,538 bytes and is 728,891). The passage page prints the line above the
    list of estimates, and the reason folds. A type has a note where its 'at least' tonnage is above PortWatch's volume of the year, or from 85% of it. PortWatch's
    volume is an estimate made from ship movements, and the atlas's groups are not all the cargo these ships carry: where the atlas's own sum is above it, the ports,
    routes or ship types the atlas assumes probably overstate the passage (Bosphorus and Gibraltar dry bulk, Torres Strait tankers: 207 against 203 Mt, 394 against 384 Mt,
    13.6 against 13.5 Mt); for Suez and Bab el-Mandeb in 2024 the note quotes the atlas's Red Sea alert instead; from 85% of that volume the note says how close the sum is
    (Panama, tankers, 2024: 97%, 104 Mt against 107 Mt; the assumed ports or routes may overstate it). The interface tags a figure "capped at PortWatch volume" exactly where
    its note says it was capped (a figure whose cap is its own 'at least' has no 'up to' to tag). A tonnage that a note and the page both print is the same figure: the
    note is written from the figure the file stores, to three significant digits with a half rounded up (5.865 Mt is 5.87 in the headline and in the note). Both figures are
    estimates, and the note names both ("IMF PortWatch, data adapted").
  - **Without the raw PortWatch rows** (the scheduled job has none), the volumes by vessel type are
    read from the tracked weekly series (Mt a day times the days of each week inside the year)
    instead of the daily rows that the committed files come from. For the 17 passages that carry an
    estimate and a PortWatch counter of their own (20 passages carry estimates; Singapore and Cape Horn have no counter, and the counter of the
    Danish Straits is the Oresund only) the two readings differ by under 0.5% in 2024 (largest: Makassar tankers, 21.2 against
    21.1 Mt, and Ombai dry bulk, 134.2 against 134.8 Mt), so such a build can move a capped figure or a K9 reference by under 1 Mt (Lombok
    iron ore "up to": 950.3 Mt from the daily rows, 949.9 Mt from the weekly series).
  - **Check K9** writes, for every passage with a counter, "at least" and "up to" by vessel type
    beside PortWatch's volume of the same year and of its best full year since 2019 (table in
    `QA.md`). A passage is flagged when "at least" is above 110% of the best year (the assumed ports
    or routes probably overstate it) or above the same year's volume. The Danish Straits are not
    compared: PortWatch counts the Oresund only. The check is a report; it never stops a build.
  - **Sunda**: the routing network sends little traffic through the Sunda Strait by itself, so its
    "at least" figure is a floor of the model (3.2 Mt of all groups in 2024: 2.42 Mt of dry bulk, 0.16
    of tankers and 0.60 of container and general cargo, against 443 Mt of all ships in PortWatch; the
    table of `QA.md` rounds each type to 0.1 Mt), not a statement about traffic; its "up to" figures carry the cargo that may
    use it.
  - **Published figures first**: where EIA publishes a flow for the passage (oil through Hormuz,
    Malacca, Suez and others), it is the headline and the atlas's range is shown below it. `QA.md`
    gives the ratio of the two for crude oil, at 7.33 barrels per tonne: 0.70 for Hormuz and Malacca
    in 2024, 1.24 for Suez and 1.37 for Bab el-Mandeb (where the atlas keeps the normal itinerary).
  - 2024 examples: Hormuz crude oil at least 27.2% (509 Mt) and up to 40.1% (751 Mt, not capped: it is under PortWatch's 915 Mt of tankers; Saudi
    crude for westbound buyers and Emirati crude may load outside the strait); Hormuz LPG 31.3% (32.3% in the released file: its 40.6 Mt are the same, the seaborne LPG total grows by 3.8 Mt);
    Malacca crude 31.0% to 41.9%.
  - The cargo table of a chokepoint page lists these pairs one by one (commodity, origin,
    destination, Mt), from the pairs files, with the pairs that may use the passage marked "may
    use" (one file per passage, `data/freight/chokepoint-lanes/<id>.json`).
- **Chokepoint traffic** is IMF PortWatch's daily count of tankers, dry bulk, container, general
  cargo and ro-ro vessels, and PortWatch's estimate of the trade volume they carry (tonnes of
  cargo, not deadweight). Both are shown as weekly averages (calendar weeks starting on Monday,
  `pipeline/freight/build_portwatch.py`) and as the average of the last 28 days. These averages
  are a transformation of PortWatch's daily data ("Atlas weekly averages of IMF PortWatch daily
  counts"); the counts are aggregated, no vessel position or track is used. PortWatch counts the Oresund but not the Great Belt, so the Danish Straits series is
  labelled as Oresund only; it has no counter for the Singapore Strait or for Cape Horn, whose
  page shows the Magellan Strait counter under its own name.
- **Incremental update of the traffic**: the weekly job keeps the daily table as a working file,
  `pipeline/cache/portwatch/daily_<year>.csv.gz`, which is **not in git** (the atlas publishes only its
  own weekly averages and comparisons: NOTICE.md, "IMF PortWatch"). On GitHub the job restores it at its
  start from the newest artifact `portwatch-daily` of the same workflow (`restore_portwatch.py`; the
  artifact is uploaded after each successful update and kept 90 days) and asks the service only for
  the days after the last one stored, less 14 days that PortWatch may revise (one page of 2,000 records
  instead of 41); every 28 days it downloads the whole table again, which also picks up older revisions.
  With no usable artifact (first run, expired, older than 28 days, unreadable) the job downloads the whole
  table; when the monthly download fails it falls back to the incremental update in the same run and
  records the failure in the status file (`full_refresh_failed`). A table with fewer than 95% of the
  previous run's records, or ending earlier, is refused and the previous files are kept. The annual job
  has no table on its runner: `build_freight.py` then reads the annual PortWatch tonnages from the weekly
  series and does not rebuild them.
- **Port traffic** (the "Weekly port traffic" block of a port page; `data/freight/port-traffic/`,
  `pipeline/freight/portwatch_ports.py`, `pipeline/freight/fetch_portwatch_port_traffic.py`). The block draws, for a port that
  has a PortWatch port, IMF PortWatch's weekly port calls and PortWatch's estimate of the tonnes exported and imported through
  the port, by ship type (tanker, dry bulk, container, and Other, which is general cargo and ro-ro together, as on the chokepoint
  pages), under the buttons Calls, Exports and Imports; under the chart a table gives the sums of the last 52 weeks and of the
  52 weeks before them, and a CSV file offers the whole weekly series with its source and licence. The block opens on Exports
  when the exports of the last 52 weeks are at least the imports, on Imports when they are less, and on Calls when both are zero.
  - **What PortWatch says its figures are**, in the words of the text of its item "Daily_Ports_Data" (read on 25 November 2026):
    "a port call is defined when a ship enters the port boundary. Port calls with a turnaround time of less than 5 hours and no
    draft change between the current and next port are excluded to filter out vessels in transit"; and, of the tonnes, "we use the
    vessel information (length, width, draft, capacity, block coefficient) to estimate the payload (or utilization rate) of the
    vessel when entering and leaving the port boundary. The change in the vessel payload (in percentage points) multiplied by the
    vessel’s deadweight tonnage (the maximum carrying capacity) in metric tons is the resulting trade flow (either import or export)
    in metric tons." The same text warns that some of the ship signals it rests on are "entered manually and, hence, may have human
    errors", and that "ships can turn off their AIS transponder to avoid being detected"; it says that this is "mostly limited to
    fishing vessels conducting illegal fishing or oil tankers circumventing international sanctions, usually in international waters"
    and "not common for container and other cargo ships" entering a port. The atlas reads from these words that a ship which
    sends no signal at a port is not counted there, so the series of a port where ships do so reads low (the known limits of
    `PROGRESS.md` name the terminals whose series read lowest); the block prints these words of PortWatch, and the exclusion of
    short calls, under every series and corrects nothing. The tonnes are therefore PortWatch's estimates: the block says so wherever they appear ("Exports (est.)", "kt/week,
    estimate") and never labels them "Atlas estimate". They are not customs flows and not a port authority's statistic, and the
    atlas does not add them to, compare them with or reconcile them with the figure of the same port in its own tile (for
    example "Throughput"), which counts another period and another scope; that figure keeps its own source.
  - **The weekly sum** is made by the atlas from the daily rows of the table: a week runs from Monday to Sunday (the table's dates
    are UTC), is stored only when the table has all seven of its days, and the last, partial week is not stored. A week that is
    missing inside a series is empty in every array of the file, drawn as a gap and shown as a dash, never as a zero; a real zero
    is a zero. The atlas adds the ship types itself and does not use the table's own total columns, which on the rows of Port
    Hedland read when the method was designed differ from the sum of the types by a tonne or two on some days. Tonnes are stored in thousand tonnes, each value with three significant figures at
    least and never finer than a tonne (a value of 100 t or more is rounded by at most 0.5% of itself, a smaller one by at most half
    a tonne); for each port it reads in full the script prints how far the rounding moves the 52-week sums of the four types and of
    each type, and flags a port where it is over 0.5%. The "52 weeks to" sums of the table are sums of weekly values ending on the Sunday of the
    last stored week, not calendar years.
  - **Which ports have a series, and how they were paired** (`pipeline/infrastructure/portwatch_pairs.py`, which prints the pair
    of every port with `--report`). A port of the atlas has a series when its `portwatch` id names a row of the PortWatch ports
    table (`pipeline/cache/portwatch_ports.csv`) of its own country. The rule: the row is at most 15 km from the port's point and
    either has the port's UN/LOCODE (R1; the nearest row when several share it) or, where none does, has the same name once
    accents, parentheses and the words port, terminal, harbor, oil, marine, of, de and international are removed (R2; a row whose
    own name has a parenthesis is not offered). Nothing else pairs a port: a nearer row of another name is not evidence, and one
    PortWatch port serves at most one port of the atlas in this release (a choice made without the owner, listed in
    `PROGRESS.md`). Of the 190 ports, 163 have an id: the rule reproduces 146 of them (116 by UN/LOCODE, 30 by name), and the other
    17 were paired when their position was taken from the row of the ports table, so each stands at the row's own point
    (0.0 km). Of the 27 without an id, 18 have a row near them that the rule cannot pair and 9 have no PortWatch port of their
    country within 15 km; they show no block and no sentence. The rule is a test of plausibility, not a proof that the PortWatch
    port and the asset have the same boundary.
  - **The scope of a PortWatch port is not always the scope of the asset.** PortWatch counts a call when a ship enters "the port
    boundary" and no page read says what that boundary covers, so every series is that of PortWatch's own boundary of the port,
    which the source line of the block says is not always the asset's. The block names PortWatch's own port ("PortWatch port:
    Surigao City") wherever its name differs from the asset's, and four pairings carry a sentence typed on the asset
    (`portwatchNote` in `ports.geojson`) that claims only what a file gives: Rosario (the asset is the up-river complex, which its
    note says is far larger than the municipal port; no page read says which of the two PortWatch's port covers), Richards Bay (the
    asset is its coal terminal; no page read says whether PortWatch's port is the terminal or the whole port), Itaqui (no page
    read says whether PortWatch's port includes Vale's Ponta da Madeira terminal, which sits next to the public port the asset
    describes) and Ras Lanuf. Ras Lanuf is a known limit: the asset stands at the point of PortWatch's port "Ras Lanuf (Al
    Burayqah)", whose position is 1.1 km from the World Port Index's entry "Al Burayqah" (also called Marsa Brega) and 99.6 km
    east of its entry "Ras Lanuf", so the series is of a port that stands next to the index's Al Burayqah, not next to its Ras Lanuf; the asset is to be
    moved to Ras Lanuf's own position, and its pairing then dropped, in a later change. A port that
    PortWatch shows with few or no calls in recent weeks is drawn as PortWatch publishes it, with its date: the atlas does not say
    why, which may be the boundary or the coverage as much as the traffic.
  - **Revisions.** PortWatch revises its recent days. Each weekly run reads again the last 6 weeks of every port that has a file
    and, for a quarter of the ports in turn (the ports in a fixed order, the quarter chosen by the week number), the last 52 weeks,
    so that every port is re-read over a year once every four weeks and never all at once; older weeks are kept as published. A
    revision older than that is not seen; a deep pass that finds the older weeks of more than a tenth of the ports changed by more
    than a quarter is refused as "history revised" and the ports are read in full again by hand (`--full`, which `docs/UPDATING.md`
    describes). A port is read in full (three requests while the table holds under 3,000 days of it) when it has no file: the first
    load was made by hand in sittings of at most 15 ports (45 requests), and a weekly run fills in at most 5 ports a run.
  - **No vessel is read.** The table holds one row per port and day with counts and tonnes by ship type, published by
    PortWatch; no ship name or number, no position or track, no time finer than a day and no signal is read, stored or shown, and
    no daily row is kept in the repository, in a cache or as a workflow artifact: the published weekly files are the only state the
    weekly step reads back.
  - **Pace** (the owner's decision of 25 November 2026, in his words, translated: "behave like a human, download little by little,
    move slowly on the page, one request at a time, and we will mention them"). The script asks one request at a time, with a pause
    of 8 to 14 seconds before the next (the chokepoint script's figures, read from its code; the seconds are the script's reading of
    "slowly", not the owner's figure), and waits out a quota answer of the service for the delay it names. The weekly run of the job
    also waits one such pause before its first request, because the chokepoint step before it asks the same host from another
    process. A normal weekly run asks for 23 requests and never more than 42 (not counting a request repeated after an error), which
    at that pace is a few minutes and never more than the 12 minutes after which the script stops asking. IMF PortWatch is credited on the block, in the CSV, in the registry, in `NOTICE.md` and in the
    About window; the IMF's terms, and the open points on them, are in `NOTICE.md`.
  - **Assumptions.** (1) A PortWatch port stands for the atlas port it is paired with, and the page names PortWatch's port. (2) A
    week with seven daily rows is complete. (3) The table has one row per port and day: a missing day makes its week a gap. (4) The
    recent weeks that PortWatch revises are those the weekly run reads again. (5) The rounding above does not move the 52-week sum of a
    port by more than 0.5% (the script flags a port where it does).
- **Alerts** (`pipeline/freight/build_alerts.py`, `data/freight/alerts.json`). The title, the text, the
  start, the event (or the list of events: the main one first, the banner opens each) and the passages of a banner are written by hand; the date the text was **checked
  against its source** (`checked`) is set only when someone has read the page it cites and kept the
  sentences and dates that page supports, and the banner says so ("Text checked against its source
  on ..."; a check older than 90 days is shown as such; a text that was not checked carries no date). Everything else is computed:
  for each passage, the transits and PortWatch's estimated tonnes over the last 28 days, over the same 28 days a year earlier (364 days back, the same
  weekdays) and the 2023 average scaled to 28 days (2023 is the last full year before every
  disruption listed), with the gap in per cent and the date of the last observation; these are
  arithmetic on a published series, credited to IMF PortWatch without the "Atlas estimate" mark. The
  **severity** comes from the gap of the transits against the 2023 average at the worst passage of
  the alert: **high** at 60% or more below, **medium** at 25% or more below, **low** otherwise (the
  thresholds are `SEVERITY_LEVELS` in `build_alerts.py`; the banner shows the rule applied in visible
  text, "High: 64% below 2023", and the whole rule behind "Details"). The **commodities** of an alert
  are those whose "at least" share of seaborne trade through one of its passages is 10% or more
  (`SHARE_MIN`), or whose "at least" tonnage is 50 Mt or more (`TONNES_MIN`; the estimates above).
  The **countries** are, for each of those commodities, the exporters and the importers that carry
  15% or more of its "at least" tonnage through the passages (`COUNTRY_MIN`), and every country with
  20 Mt or more of cargo, of any commodity, that has to cross the passages (`COUNTRY_MT_MIN`); a pair
  that crosses two passages counts once. An alert may keep an `override` with a reason taken from the
  atlas's own files: `addCountries` appends countries to the derived list (so it follows the data
  when they change). Today Iran is added to the Hormuz alert (customs data record no Iranian crude
  oil exports in 2024, caveat `crude-irn`, so the lanes cannot name the country at the centre of
  the event) and Yemen to the Red Sea alert (the coastal state at Bab el-Mandeb, named by the event).
  The derivation, and the reason of an override, are shown to the reader behind the banner's
  "Details". On a commodity page the banner adds the commodity's own estimate for the passage
  ("at least 27%, up to 32% of seaborne crude oil crossed the Strait of Hormuz in 2024", two
  significant digits, "Atlas estimate"); the estimates for the alert's other passages are behind
  "Details", with the note that the passages are on the same routes and the shares are not additive. The weekly job runs the builder after the PortWatch update and the annual job after the
  freight build. A threshold is never a reason to open an issue: the severity changes on the banner
  and the build prints the change.
- **Freight market now** (the page `#sel=board:freight-now`, opened from the row of that name under "Routes by vessel class" while the
  Freight view is open; `pipeline/freight/build_market_now.py`, `data/freight/market-now.json`). For dry bulk carriers and for tankers the page
  lists five passages each, with the vessel transits and IMF PortWatch's estimate of the cargo over the last four complete weeks (28 days)
  against the same four weeks a year earlier, and the change; below them it shows two indicators from the price files and five links. It
  shows no freight rate, no Baltic Exchange value and no gas carrier figure, and no world total. The digest is arithmetic on the weekly chokepoint series
  of IMF PortWatch, credited to it (source id `portwatch`, "data adapted") and not marked "Atlas estimate": the totals and the changes are sums and ratios of PortWatch's own
  published figures, not an estimate of the atlas, so they carry PortWatch's source id and the words "data adapted", as the alert banners and the status board do. The method below is the atlas's
  own, a choice made without the owner, listed in `PROGRESS.md`. The assumptions, in the order the builder applies them:
  - **Input.** Only the weekly files `data/freight/portwatch/<passage>.json` that `build_portwatch.py` writes: no network, no daily table, nothing
    under `raw/` or `pipeline/cache/`. The digest holds no name: the page takes the atlas's name of each passage from `chokepoints.json` and,
    for a passage the catalogue lacks, prints its id and no link.
  - **Weeks are taken by date, never by position.** A weekly file gives its first week (`start`, a Monday) and one value a week: the date of
    each week is rebuilt from it, and a file whose number of values does not match its dates (a week that went missing would move every later
    value by one week) is refused. A week is the calendar week from Monday to Sunday, as in the weekly series.
  - **The last complete week.** For a file it is the week that ends on the last Sunday not after the file's last day, so the partial week at the
    end is left out. `to`, the date the page prints, is the earliest of those Sundays over all the files: a series that lags dates the digest
    earlier, it does not stop it. The builder says so, in its output and in the note of its status record, when some series end later than `to`:
    how many, and the date they end on. When that date would be earlier than the stored digest's, the run is refused (see the paragraph on refusals below).
  - **The windows.** The four weeks that end on `to` (28 days, the window of the alert banners), and the same four weeks 52 weeks (364 days,
    the same weekdays) earlier, which end on `yearAgoTo`.
  - **The totals.** For a passage and a ship type the weekly means (vessels a day, which `build_portwatch.py` rounds to 0.1) times 7, summed over
    the four weeks, as whole vessels with a half rounded up; and the same on PortWatch's estimate of the cargo (Mt a day, weekly means to four
    decimals), written to three significant figures. The arithmetic is in decimals, so that a half is never decided by a binary rounding. The totals
    agree with the 28-day comparison of the alert banners (all ships) except for the rounding of the weekly means to 0.1 vessels a day;
    a test holds the gap to a bound. The change in per cent, (now - year earlier) / year earlier, is computed by the builder on these sums before any
    rounding, stored (`pct` for the transits, `mt.pct` for the cargo) to one decimal with a half rounded away from zero, and printed as it is stored: a
    figure worked out on the whole vessels or on the three-figure cargo could differ from the one worked out on the weekly files by more than the last
    digit. It is null where the year-earlier sum is zero, and −99.9 where a fall that one decimal would round to −100.0 leaves something.
  - **Which five.** The five passages with the most estimated cargo of the ship type over the 52 weeks that end with the year-earlier window
    (ranked on the sum before rounding; `rankMt` is that sum in Mt to three significant figures, so two passages can show the same figure;
    only an exact tie of the sums goes by id). They are ranked a year back so that a collapse this year does not remove the
    passage that explains the market. This is a rule of the atlas, not of PortWatch, and the page says so above each list; a
    passage that matters this year and carried little a year ago is not shown; one passage can be in both lists. Five passages, four weeks and
    52 weeks are the atlas's choices. A weekly file that starts after the first of those 52 weeks (a passage mapped lately) cannot be ranked: it is left out
    of the ranking, with a line in the builder's output, and the digest is built from the others.
  - **Counting.** A ship that crosses several passages is counted at each of them: the rows are not added, the page says so, and it has no
    world total (the weekly series hold none).
  - **Ship classes.** The description of PortWatch's chokepoint table that the atlas read (the text of the ArcGIS item "Daily_Chokepoints_Data",
    https://www.arcgis.com/sharing/rest/content/items/3da2b9ca97684916b75c4013f95d18ab?f=json, read 25 November 2026; it is the one description read, and
    other PortWatch documents may say more) says that "all the
    indicators are available by 5 main ship categories: container, dry bulk, general cargo, ro-ro and tanker". It does not say what each class holds
    and does not mention gas, LNG or LPG carriers. The page therefore says that the atlas cannot tell whether gas carriers are in PortWatch's tanker
    class, that the tanker figures may include them or not, and shows no gas carrier figure. That sentence is printed under the tanker list only when the list has rows. The atlas's own convention of comparing LNG and LPG carriers with
    the tankers of PortWatch in its passage estimates (section 4) is its assumption, not a statement of PortWatch. The cargo is what PortWatch says
    it is: "we use the vessel information (length, width, draft, capacity, block coefficient) to estimate the payload (or utilization rate) of the
    vessel when transiting through the chokepoint" (same text), an estimate and not a customs statistic.
  - **What the page prints.** Each passage has two lines, one for the transits and one for the cargo: the figure of the last four weeks, the figure of
    the same four weeks a year earlier, and the change between them. A count has thousands separators. A cargo is in Mt to three significant figures
    (up to four decimals); it reads `0 Mt` when it is zero and "under 0.05 Mt", the status board's limit, when it is above zero and under 0.05 Mt. The
    change is the one the builder stored (see the paragraph on the totals above), printed with its sign, one decimal and a true minus; the page works out
    no change, except the bound below. The cases, each with when it applies:
    - a sign and one decimal (`+12.4%`, `−13.7%`): the stored change is a number; `0.0%` when it is zero, which is no change.
    - `−99.9%`: a fall that one decimal would round to 100% while something is left in the window. The builder stores −99.9 and the page prints it as
      it is; `−100%` is printed only when the stored change is exactly −100, that is when nothing is left.
    - a dash, for the transits or the cargo: the stored change is null, which is nothing a year earlier (the year-earlier sum is zero). Its hover text says so.
    - a dash, for the cargo only: the year-earlier cargo is above zero and under 0.05 Mt, whatever was stored. A cargo that small is the length of a rounding
      error, so there is nothing to compare it with; the hover text says that the year-earlier cargo is under the bound.
    - a bound, for the cargo only ("down more than N%"): the cargo of the last four weeks is above zero and under 0.05 Mt and the year-earlier cargo is not
      under 0.05 Mt (the dashes above come first: a row with nothing a year earlier, or with both cargoes under it, prints a dash), so its figure is a bound
      and not a measure. N is the whole number of per cent below 100 x (year earlier - 0.05) / year earlier, worked out from the bound and the year-earlier
      figure the row prints (the stored change is not used: it is the change of the unrounded sums). It is the one figure the page works out.
    - every other row: the stored change as it is. The page prints no `<0.1%` (a stored change is a multiple of 0.1), no `+100%` or `0%` without a
      decimal, and does not clamp a fall to −99.9 itself.

    A digest in which a row has no stored change (`pct` or `mt.pct` missing: an older file) cannot be read as a whole, and the page prints the line for a missing
    digest (see the paragraph on refusals below). The page prints the dates of both windows, the unit words of the status board
    and the source line of IMF PortWatch with the transformation, "weekly averages of PortWatch's daily counts, times 7 and summed over the four weeks".
  - **Refusals.** The builder keeps the previous file, records the failure as `build-market-now` and ends with exit code 0, so a data job never
    fails because of it, when: a file is not the series its name says or has no estimated cargo; its lists are missing or of different lengths;
    its first week is not a Monday; a value is not a finite number or is negative; a week is missing or extra (wherever the series would rank);
    fewer than five series exist, or fewer than five can be ranked (a series that does not reach back far enough is only left out of the ranking, see the paragraph on the five passages above); or `to` is earlier than the one published. The file is not rewritten when its content is the same, so a week
    without new data makes no commit. The step alerts after three failed runs in a row, as a weekly source does: it runs on inputs that change every week,
    and a short PortWatch week heals with the next one. The validator of the data checks the shape only (keys, five rows a type, finite numbers
    that are not negative, the two changes a number or null, two dates 364 days apart, the ranking figure not increasing) and reads no other file, so that it is never stricter than the
    builder. The step follows the alert banners in the weekly PortWatch job and comes before the digest of changes; the annual job rebuilds neither the weekly series nor this file. The digest
    has no freshness entry of its own: it follows `portwatch`, and its own date is `to`. With the file missing or unreadable the page prints
    one line, "No traffic figures are available.", and keeps the indicators and the links.
  - **The two indicators** are series of the price files shown as they are (`igrea-m` and `freight-ppi-m`, section 7), and neither is a freight
    rate. The index of global real economic activity (Federal Reserve Bank of Dallas, for dry bulk) is, in the Bank's words on its page of the
    index (https://www.dallasfed.org/research/igrea, read 25 November 2026), "derived from a panel of dollar-denominated global bulk dry cargo
    shipping rates and may be viewed as a proxy for the volume of shipping in global industrial commodity markets": a deflated, detrended measure
    of activity in percent deviation from trend, built on rates. The page cites Kilian (2009) with the correction of Kilian (2019), as the Bank does.
    The producer price index of deep-sea freight (U.S. Bureau of Labor Statistics, June 1988 = 100; the page labels it "US deep-sea carriers", as the series' basis says) measures the prices that US
    deep-sea carriers receive, not a spot rate. The value of the same month a year earlier is found by its date; the change on one year is the
    price board's own figure for the series and a deviation from a trend has none; the mark "late" is the price board's (a monthly series is late
    from the 15th of the second month after its last month). The Global Supply Chain Pressure Index is not shown: its own description says that it
    combines the Baltic Dry Index, the Harpex index and air freight costs with survey components (section 7).
  - **Links, no value.** The page links to, and shows no value of, the Baltic Exchange indices (registry `baltic`), the China Import Dry Bulk Freight Index
    and the China Import Crude Oil Tanker Freight Index of the Shanghai Shipping Exchange (`sse`) and the weekly count of grain vessels and the grain
    ocean freight rates of the USDA Agricultural Marketing Service (`usda-ams`). A link is not cited: it has no source line and no date. What the pages
    say, read on 25 November 2026. Baltic Exchange, clause 5.1 of its Terms and Conditions
    (https://www.balticexchange.com/en/site-services/terms-and-conditions.html): no part of the website or its content "may be copied or reproduced
    (except for your personal use), shared with third parties, reverse engineered, reverse assembled, or used to create any derivative work (whether in
    physical or electronic form) without the prior written consent of the Baltic"; the link is to its page of indices (https://www.balticexchange.com/en/data-services/market-information0/indices.html). Shanghai Shipping Exchange:
    the only statement read on its pages is the footer "© 2001-2026 Shanghai Shipping Exchange Institute(Prep.) All Rights Reserved." (https://en.sse.net.cn/,
    spacing normalised), which the list of indices and the two index pages (https://en.sse.net.cn/indices/cdfinew2.jsp and
    https://en.sse.net.cn/indices/ctfinew2.jsp) carry too; the home page has a block headed laws that links to a page of laws and regulations, which was not read, and no page of terms was read.
    The index pages fill their tables by script, so no value was read; both indices measure freight into China only. USDA Agricultural Marketing Service: its privacy page (https://www.ams.usda.gov/about-ams/privacy) says "Information
    presented on the AMS web site is considered public information and may be distributed or copied. Use of appropriate byline/photo/image credits is
    requested." It names the AMS web site, not the AgTransport host (agtransport.usda.gov) whose tables carry the vessel count and the rates, and those
    tables state the attribution "USDA Agricultural Marketing Service" (vessel count) and "O'Neil Commodity Consulting" (rates) and no licence field
    (https://agtransport.usda.gov/api/views/vh5k-mnyv.json and https://agtransport.usda.gov/api/views/ehs5-yac3.json). The page of the datasets
    (https://www.ams.usda.gov/services/transportation-analysis/gtr-datasets) says "These data series are aggregated from non-confidential and
    non-copyrighted sources."; it names the table of the vessel count "Weekly port region grain ocean vessel activity (number of vessels)" and says that it
    holds the "Weekly number of grain vessels loaded during the week and expected to be loaded within the next 10 days in the Gulf, PNW, and Vancouver, B.C."; and it gives "SOURCE: O'Neil Commodity Consulting" for the grain vessel rates, U.S. to Japan. The page's line for the table uses
    that name and says what it counts, Vancouver included. The atlas does not read the
    privacy sentence as covering rates credited to a private firm, and it shows neither series: the vessel count and the rates are links, to the AMS page of the datasets.
- **Events** carry `commodities`, `countries` and `assets` when their own text (title, summary,
  impact, and the names of the assets they link to) names them, by whole words (`pipeline/freight/event_links.py`
  is the rule; the tests check every event against it: "tin" is not "tinplate", "gas" is not
  "gasoline", "oil" is not "oil-fired", and a currency such as "US dollars" does not name the
  country); a linked route or passage does not name a commodity by being
  linked. An event that names no commodity has none. The events that an alert points to (`events` in
  `pipeline/freight/alerts.json`: one or several, the main one first, which gives the banner its source)
  are also shown with the alert's commodities. With a commodity chosen, the History timeline and the
  event markers of the price chart keep an event that names the commodity, or names no commodity at all
  (a shipping or market event), or belongs to an alert that covers it (`web/src/lib/events.ts`). The
  "Events" section of a page lists first the events that name the page's commodity, country or route
  (newest first, three shown, "Show all"), and on a commodity page, behind one more line, the general
  shipping and market events that name no commodity; the count in its title is of the page's own events. The event page shows the change of the atlas's price series of each linked
  commodity one and three months after the event: from the series the event names (`series`, where the
  catalogue has several markets: a European gas event reads the TTF), else the commodity's first
  daily or monthly series, with its name in the line. A monthly series gives month averages (the first
  figure is the average of the month of the event) and a figure that is the same observation as the
  first is left out; an annual series gives none. It is arithmetic on the published prices, not an
  estimate of the effect.
  Every event is written by hand from pages that were read: `src` is the page the sentences come
  from (the regulator, ministry, port or canal authority, EIA, FAO or the company where a free page
  exists, otherwise the Wikipedia article about the event), `also` lists the other pages that support
  the text, and `checked` is the day the text was read against them (all events carry it; the site
  shows it on the event page). A sentence that no page read supports is not written: an event is cut
  down to what the pages say, and a date is the one a page gives (a month where the page gives only a
  month). A traffic figure computed from the atlas's own IMF PortWatch series is marked as an atlas
  calculation. A paid service is not cited, not even at second hand. The timeline carries the energy
  episodes (price collapses, producer decisions, sanctions, embargoes and pipeline cuts), the export
  restrictions and trade measures on food, fertiliser and metals, the milestones of the freight market
  (rate indices, bankruptcies, sanctions on tanker owners, the rules of the IMO and the EU), and the
  accidents and weather that stopped a route or a mine. The links follow the rule above: the tests read
  the commodity, country and asset ids of every event back from its text.
- **What changed**: after each update `pipeline/common/changes.py` writes `data/_status/changes.json`
  (the five largest weekly moves of the daily price series, the five largest monthly moves, the five
  passages furthest from their 4-week and 365-day averages with at least 3 vessels a day, the sources
  whose data or release changed since the previous run) and `web/public/changes.atom`, the same items
  as an Atom feed. A price move beyond a factor of 5 in a week or a month (`MAX_RATIO`), and a series
  that carries the same two figures as another series of another name or unit, are not published:
  the job lists them in its status (`refused`). Two runs on one day (the PortWatch job at 19:17 and
  the prices job at 21:43 on Wednesday) keep the sources that the first reported.

## 6. Country profiles

Profiles are built by `pipeline/commodities/build_profiles.py`, one file per country of the index
(`data/countries/profiles/<ISO3>.json`, loaded when its page opens). The years, year labels and world
totals of the series by year are the same for every country: they are in one file,
`data/countries/years.json`, loaded once with the first profile.

- **Every line.** A country has a line for every row it has in any table of any commodity: the main
  tables (production with refinery output, consumption, reserves, exports, imports) and every extra
  table of the commodity file. The section of an extra table is the last
  word of its key (`coke-production`, `motor-gasoline-consumption`, `fe-reserves`, `760110-exports`;
  `stocks` gives the ending stocks of USDA PSD, `nuclear-capacity` the capacity of EIA), its line is
  named from the table's title, and a customs table (CEPII BACI) gives the line the USD value of its own
  row (in billions of US dollars, three decimals from one billion and three significant digits below it, so that a line of USD 340,000 reads
  0.00034 and not 0.0). A table of part of the world (the EU member states) says so on the line, and a table of an old
  year (EIA's LPG production, 2014) prints its year. The `balance` block of a crop file is a world
  balance sheet with no country row and gives no line. Its rank and share are those of the full table,
  of the same source and year. Nothing is cut: the page shows the first eight lines of each section and
  the rest behind "Show all".
- **Order and the two largest exports.** Exports and imports are ordered by customs value (CEPII BACI,
  latest year, whatever the source and year of the tonnage on the same line; the line names both).
  The page prints two key figures. **"Largest export, all goods"** is the first heading of the basket
  below (four-digit HS, every chapter), with its share of the country's merchandise exports.
  **"Largest raw-material export"** is the largest of the export lines, among the atlas's commodities
  only. Production, consumption and reserves are ordered by share of the world total. Exports that
  customs data do not record are not estimated: the caveat the engine writes for that origin is shown
  under the exports (Iranian crude oil, for example), and the basket and both key figures say that
  their totals and shares leave those exports out.
- **Coal.** Customs codes do not separate thermal from metallurgical coal, so the value of coal is shown
  on one line, "Coal (all types)", with the customs tonnage of all coal; the thermal and metallurgical
  lines carry EIA tonnage and no value.
- **Reserves** carry the number of years of production they equal, where reserves and production are
  lines of the same source and unit (USGS).
- **History year and trend.** Each line carries the country's series from the history files
  (`data/commodities/history`), with its rank in each year under the rules of the past-year table of the
  commodity page: a figure far out of line with the years around it is not ranked, and that year's
  world total leaves it out. With a History year, a line shows that year where its series has it and
  says so where it has none; the customs values, partners, freight and basket stay of the latest year.
- **Trade balance and partners** (arithmetic on published figures, credited to their sources). Net
  exporter or importer: exports minus imports of the same product, only where both tables share unit
  and year ("none in the table" where the country has no line on one side: a flow below the threshold
  of a customs table, 1,000 t and USD 1 million, is not in it). Customers and suppliers: the
  first three partners of the latest customs year with their shares (tonnes; declared value for gold,
  silver and platinum-group metals), from the pairs tables of the trade-flow engine, or from the
  cleaned customs frame for the groups that have no lanes; an Atlas estimate among them keeps its mark.
  Concentration is the Herfindahl index of all partner shares, from 0 to 10,000 (10,000: one partner),
  also given as the number of equal partners it corresponds to (10,000 divided by the index). Imports
  over consumption is printed only where both are lines of the same unit and year, and only against a
  consumption figure that a source publishes: the atlas's apparent consumption (steel: production plus
  imports minus exports) holds the imports already and gives no ratio. It is not the share of
  consumption that is imported (imports can be re-exported or stocked).
- **Trading or refining hub** is a derived label: exports and imports of the same product each at least
  1% of the world total, and no line for the country in a production table that lists every producing
  country (EIA, USDA PSD, FAOSTAT). USGS tables list the main producers only: no label is derived from
  them.
- **Freight** is read from the pairs tables of the engine (section 5) for the latest customs year: the
  share of the country's tonnes by mode (sea, sea through a port of another country, sea and overland
  with the split not known, overland), the typical ports of its seaborne pairs with their basis (an
  Atlas assumption), and for each passage the share of its seaborne tonnes whose assumed route has to
  cross it ("at least") or may cross it ("up to"), with the routing rules of the chokepoint estimates.
  The "up to" follows the chokepoint page: where the page caps its own "up to" for that cargo at IMF
  PortWatch's count of all ships through the passage (section 5), or prints no figure for that cargo,
  the country's "up to" is not printed and only "at least" is, with a sentence that says why. A passage
  is listed, as on the chokepoint pages, when the printed figure reaches 2% of the country's seaborne
  tonnes or 1 Mt. These shares are Atlas estimates.
- **All goods.** The ten largest exports and imports by value at HS4, every chapter, with their share
  of the country's total merchandise exports or imports, from `pipeline/cache/hs4_*`, written by
  `pipeline/trade/extract_hs4.py` in one pass over the latest year of the CEPII BACI archive (also run
  by the annual job after a new BACI version; it writes its four files under temporary names and renames
  them together). If the exports, imports and totals are not all of one year, the year of the customs
  frame, the basket is left out. *Names of the headings*: the atlas does not reuse the HS heading texts.
  The free list read for them, UN Comtrade's reference tables, is under UN Comtrade's "Policy on
  Comtrade Data Use" (read 23 November 2026 and again 24 November 2026), which provides the data for internal use and no re-dissemination without UNSD's permission,
  except, by its page on re-dissemination, "limited amounts of UN Comtrade data in a few tables, graphs, visualization", with the attribution "Source:
  UN Comtrade": a list of all the headings is more than that, and is not copied (the tin page prints a few figures under the same exemption). A heading is therefore named, with its code, from the six-digit
  descriptions under it in CEPII BACI's product list (Etalab Open Licence 2.0), never from one of them
  alone: one subheading gives its own words; subheadings that share their first part give that part
  with the words they all share after it ("Vehicles: transport of goods", HS 8704), or the kinds they
  list in a word or two ("Metals: platinum, palladium, rhodium, iridium", HS 7110); subheadings that
  start differently give all their first parts ("Helicopters; aeroplanes and other aircraft;
  spacecraft", HS 8802), with the words they all share in brackets. A word that a description negates
  ("other than durum") is not taken as shared. Such a name can be vague ("Vehicles" for HS 8703,
  whose subheadings share no other word). Up to five headings of the raw-material chapters (HS 1 to 27,
  40, 41, 44, 47, 51 to 53 and 71 to 81) outside the catalogue are listed apart, each at least 5% of the
  country's exports from these chapters (countries with USD 200 million of them or more); the chapters
  hold articles too (tyres, screws, jewellery), and the block is named "Other goods of the raw-material
  chapters".
- **Companies** are listed under the country of their headquarters, with every commodity they are
  listed for. The operators of the infrastructure assets in the country are listed apart, as the
  operator field of each asset reads (it can name several owners with their shares), with the assets
  that carry it; the field is not split into companies or counted as such.
- **EU.** USDA PSD gives one row for the European Union. It is an entry of the site's country list,
  "European Union (27)", region Europe, with no polygon of its own: its page lists the member states,
  each member's page links to it, and the search finds it.
- **No data.** A country of the index with no line, trade, lane or asset says what it is, in the words
  of the base map (Natural Earth: its TYPE, SOVEREIGNT and NOTE_BRK attributes; a "Country" under
  another sovereign, such as Åland, is "a country under the sovereignty of" it), and that the customs
  data have no code of their own for it.
- **"World top-10 in N commodities"** counts the catalogue commodities for which the country is in the
  top 10 of a production (with refinery output), export or import table: the same lines whose sources
  and years are printed under it. Consumption, reserves and stocks are not counted.
- **Warnings** of a commodity table (trade hubs that re-export, gross weight against contained metal)
  are repeated on the lines built from it, except a warning about one country ("The United States is
  converted...", "Kyrgyzstan: EIA raised its estimate..."), which stays on that country's line.

## 7. Prices

- Monthly prices: World Bank Commodity Price Data (Pink Sheet), nominal USD, 1960 to the latest
  month. Two series stopped in August 2020, barley and sorghum: since the sixth release they are published to that
  month, marked closed by the builder (a monthly series that ends more than six months before the newest series of its
  source), and their pages say when they stop. Since the sixth release the price after them is the annual average of the
  World Bank's annual workbook (sheet "Annual Prices (Nominal)", `barley-a` and `sorghum-a`, nominal USD a tonne, from the year after the last
  month to the last year of the workbook): a series of its own, labelled annual, which the page's key figure shows as "annual average"
  with its year, and which the price drawer opens beside the closed monthly series (`defaultSeriesIds` in `prices.ts`: a closed series is
  never opened alone). The workbook does not say how its annual values after August 2020 are built, and the series says so. Both series have the
  same real twin, and the "Real prices" switch opens the real series on its own window (to 2025), not on the window of the monthly series. The
  monthly series of the IMF, which has both, is not loaded (a new source: an open question for the owner). Sunflower oil, which had no page, is on the
  sunflower page; the rapeseed page keeps the rapeseed oil series, and both pages say that the price is the oil's.
- Daily prices: EIA spot series (Brent, WTI, Henry Hub, New York Harbor gasoline, ULSD and heating
  oil, US Gulf jet fuel, Mont Belvieu propane). The EIA's table page of the petroleum spot prices reads "Source: Refinitiv" under
  the table and its natural gas definitions page gives "Spot Price: Refinitiv, an LSEG business." (read on 25 November 2026); no
  page read says whether these prices may be redistributed, whatever the EIA's sentence on its own publications. The atlas
  therefore credits them as "EIA (source: Refinitiv)" and offers no download of them: the files `data/prices/*-d.json` that the charts
  read are served with the site, and no button offers a CSV file or a copy of them (the owner decided on 25 November 2026 to
  keep these series, saying where they come from: see "Decisions of the owner" in PROGRESS.md); the quotations and the
  addresses are in the registry entry `eia-spot` (terms to be confirmed).
- Freight (the "Freight" family of the price drawer and the board): the atlas shows no freight rate: for none
  of the sources it has read has it established that the rates may be republished (see "Freight rates that are not stored" below). Three indicators are shown, each taken
  from its publisher and each labelled for what it is (`pipeline/prices/freight_indicators.py`):
  - US deep-sea freight services, producer price index (U.S. Bureau of Labor Statistics, series
    PCU483111483111, June 1988 = 100, not seasonally adjusted, monthly). It measures the prices US
    deep-sea carriers receive; it is not a spot rate and moves far less than the Baltic indices: +0.7%
    from May to December 2008 (256.5 to 258.2) while dry bulk rates collapsed, then a fall of 27% from
    September 2008 (284.4) to May 2009 (208.8). It is fetched from the BLS public API version 1,
    which needs no key: ten years per request and a small daily quota per address. The history is kept
    in `pipeline/cache/bls/PCU483111483111.json`; each weekly run asks for the last three years (the
    window the BLS revises; its last months are marked preliminary and the note says which) and for at
    most three older ten-year windows until every year has come from the BLS. Until then the older years
    are the values the atlas took earlier through FRED, the St. Louis Fed's copy of the same series, and
    the note of the series names those years (as the runs they are); that copy carries no preliminary
    flag, so while it holds the current year the note says that the latest months may be preliminary.
    A refused request (the quota is shared by the address) keeps the cache, is recorded as a failure of
    `bls`, and alerts after three runs like any source. The cache file is rewritten only when a value,
    a preliminary flag or the years fetched changed.
  - Index of global real economic activity (Federal Reserve Bank of Dallas; Kilian 2009, with the
    correction of Kilian 2019), monthly from 1968, in percent deviation from trend: a deflated,
    detrended index built on dollar-denominated dry bulk freight rates. Route pages of dry bulk routes
    point to it.
  - Global Supply Chain Pressure Index (Federal Reserve Bank of New York), monthly from 1998, in
    standard deviations from its average: it combines the Baltic Dry Index, the Harpex container index
    and BLS air freight costs with PMI supply-chain components. Its last months are revised.
  The board shows no change in percent for the two deviation measures (a value that crosses zero has
  none). A series that stops advancing raises the "late series" failure of its source. The Freight market now page (section 5) shows the first two
  of these three, with the value of the same month a year earlier, and says that neither is a freight rate.
- Freight rates that are not stored. The atlas stores no value of the Baltic Exchange (its terms restrict
  the copying of its content: NOTICE.md), of the Shanghai Shipping Exchange (the pages read say "All Rights
  Reserved" and state no licence) or of Clarksons, Platts, Argus and Ship & Bunker, for which it has read no
  terms that allow republication. The USDA Agricultural Marketing Service publishes
  free grain ocean rates on its AgTransport platform: US Gulf and Pacific Northwest to Japan (dataset
  ehs5-yac3, source "O'Neil Commodity Consulting"), Brazilian ports to Shanghai and Hamburg (j6ns-hzra,
  source University of São Paulo ESALQ and USDA), Ukrainian ports to Egypt and other buyers (2n8s-739j,
  source Centre for Transport Strategies, Kyiv, and USDA), and the weekly cost indicators built on the
  same Gulf and PNW rates (8uye-ieij). None of these datasets carries a licence, and each credits a
  private firm or a foreign institute for the rates, so the atlas does not copy them: the route pages
  of `usgulf-china-grain`, `uspnw-asia-grain`, `brazil-china-soybeans` and `blacksea-egypt-wheat`
  link to them with one sentence on what they hold. The Bank of Japan's services producer price
  indices for ocean freight are not stored either: the Bank's copyright page covers its main site, and
  the API of its time-series site asks every service that uses it to notify the Bank by e-mail; the
  dry bulk and tanker route pages link to them ("Ocean freight transportation (except Ocean tankers)",
  "Ocean tankers").
  Every route page says that Baltic assessments are proprietary and links to the Baltic Exchange. The voyage calculator
  of the route pages stores no rate either: its freight and hire are typed by the visitor and are not kept (section 3). The Freight market now page
  links to the Baltic Exchange indices, to the two China import indices of the Shanghai Shipping Exchange and to the weekly count of grain vessels and the grain
  ocean freight rates of the USDA Agricultural Marketing Service, and shows no value of them; the sentences read on their pages are in section 5, under
  "Freight market now".
- Annual prices: USGS Mineral Commodity Summaries 2026, rows "Price" of the Salient Statistics
  (lithium carbonate, manganese ore CIF China, rare-earth oxides, bauxite and alumina "average unit
  value of imports, free alongside ship (f.a.s.)", cobalt, palladium, rhodium): one value a year,
  2021 to 2025, in the unit and with the basis the file states, in its own words; the last year is
  USGS's own estimate and is marked as such. The commodity page shows such a value as "annual average
  2025", with the decimals the file gives (9,000, not 9,000.00), and its change on the previous year;
  it is never presented as a current price. Since the sixth release the same file gives the prices of the metal bulks: chromite ore
  (gross weight), ferro-chromium (per pound of chromium content), No. 1 heavy melting scrap (delivered composite price), molybdenum (the price of US
  molybdic oxide, 57% molybdenum content) and the three kinds of natural graphite (flake, lump and chip, amorphous: average unit values of imports), all in the file's section
  of United States salient statistics, which the series names say ("US"). Each is attached to its page, and a note under the price button says which
  product of the page it is the price of (the ferro-alloys page: ferro-chromium and 75% ferrosilicon, no series for the other alloys). Three
  more rows of the same file, added in the sixth release, are each the price of one product of its page and in the file's own unit: elemental sulphur (US dollars per metric ton, "free on board,
  mine and (or) plant", the sulphur page), ammonia (US dollars per short ton, "free on board Gulf Coast", source Green Markets: no conversion to the metric ton; the
  urea page, whose own price is the Pink Sheet's urea) and ferrosilicon with 75% silicon (US cents per pound of silicon, source S&P Global Platts Metals Week, mean import
  prices based on monthly averages; the ferro-alloys page, after ferro-chromium). A year is marked estimated only where its own row's Notes carry the segment
  "Estimated." (2025 in all of these series): a note that quotes the estimated year of another row is not a mark. Each name and unit is that of its row (checked
  against `raw/usgs/MCS2026_Commodities_Data.csv` row by row by `test_fncg.py` G7: chromite ore, "dollars per metric ton", gross weight; ferro-chromium, "dollars per
  pound", chromium content, excluding ferrosilicon chromium; heavy melting scrap, "dollars per metric ton", delivered, Fast Markets AMM; the three graphites, import unit
  values "dollars per metric ton at foreign ports", flake, lump and chip (Sri Lanka) and amorphous; sulphur, ammonia and ferrosilicon as above). One row does not say what
  its unit is a unit of: molybdenum's reads "dollars per kilogram", names the product ("U.S. molybdic oxide (MoO3) price, 57% molybdenum content") and sits under a chapter
  header that reads "Data in metric tons, molybdenum content, unless otherwise specified". The series, its basis and the page's note give the file's words and say that the file
  does not say whether the kilogram is of the oxide or of the contained molybdenum. Monthly series for
  these commodities exist in the IMF Primary Commodity Prices (in other forms: lithium metal,
  electrolytic manganese, rare-earth carbonate); they are not used, because the terms of use for
  scripted downloads are not confirmed.
- Real prices: the annual workbook of the Pink Sheet (sheet "Annual Prices (Real)", constant 2010 US
  dollars, deflated by the Manufactures Unit Value (MUV) index, column "MUV Index"; the "Definitions"
  sheet gives the deflator). They are annual averages from 1960, shown by the "Real prices" switch of
  the price drawer for the series that have one (the Pink Sheet series, and Brent, WTI and Henry Hub
  daily through their monthly benchmark). No monthly real price is built: that would need a consumer
  price index that is not among the downloaded files. The annual workbook (downloaded from the World Bank's address listed in
  `raw/DOWNLOAD_REPORT.md`, last saved by the publisher on 3 November 2026) opens on a cover sheet that calls itself a comparison of
  the real annual prices against an earlier copy of the file and speaks of nine values that differ; the atlas reads the workbook as
  published, for the real annual prices and for the annual nominal series of barley and sorghum above, and has checked neither against another copy.
- Price indices: the 16 indices of the sheet "Monthly Indices" (World Bank, nominal US dollars,
  2010 = 100), the natural gas index and the MUV index. The header of that sheet is spread over four
  rows, so a column is found by the text above it, never by its position, and the builder refuses a
  workbook whose index sheet does not cover the same months as the price sheet or is no longer 2010 = 100.
  `pipeline/tests/test_prices_raw.py` proves every series of `data/prices/index.json` against its raw
  file when the workbooks are on disk (column found by its header text, unit, first and last value,
  number of observations and every value), and the data validator checks that each index averages 100
  over 2010.
- **What a price measures.** The basis note and the dates of the basis changes of every Pink Sheet
  series are read by the builder (`pipeline/prices/basis.py`) from the workbook's own "Description"
  sheet: grade, delivery term (FOB, CFR, CIF), place, and each "from <month>", "<month> to <month>",
  "beginning", "prior to" or "<month> backwards" in the text. The drawer draws a thin line at each
  change and lists them, with what they replace, under "What the price measures". The months the
  source itself marks as estimates (the last two months of Japanese LNG, the estimated months of
  South African coal) are tinted. EIA series carry the description EIA writes in the file. A basis
  note holds nothing but the source's words: the atlas's earlier remarks on Brent before the
  mid-1980s and on Japanese LNG indexation were removed because no page of the source supports them.
  The breaks of a series are in date order and each one replaces what the previous one introduced.
  Where the dates of the source's own clauses overlap (only the Richards Bay coal row: "from January
  2015" against "during 2006-February 10, 2017"), the atlas keeps the clauses that do not overlap, quotes
  the others verbatim in the note and says that the source's dates overlap. The deflator of the real
  prices is quoted in the same way, typos of the source included ("Pailand").
- **Years of twelve identical monthly values.** A calendar year whose twelve monthly values are one
  and the same number is not twelve observations of a moving price: the builder lists those years
  (`annual`), the chart tints them, and the date lookup says what is observed, "1965 value, unchanged
  all year", with the year the values start to differ. The source may publish one price a year there
  or a price that was not moving (gold reads 35.00 USD/oz in every month of 1960 to 1967); the atlas does not say which. Only the
  iron ore row of the sheet says "annual contract prices", and those years are their own annual series
  (below), whose values are called "annual contract price". 244 series-years in 22
  series (260 series-years in 19 series before the iron ore split).
- **Iron ore.** The Pink Sheet column joins the Brazilian annual contract price in US cents per dmtu
  (to 2005; FOB Ponta da Madeira, Itabira mines before 1987) and the spot price in US dollars per dry
  tonne (from January 2006: 63.5% Fe to November 2008, 62% Fe CFR China after). They are two series:
  `iron-ore-m` (spot, USD/dry t, 2006 on) and `iron-ore-contract-a` (annual, US cents/dmtu, 1960 to
  2005). One month of 1965 reads 15.3 in the source against 10.2 in the eleven others; the annual
  value kept is 10.2 and the note says so.
- **Gaps.** An EIA daily file has days missing before 2007 to 2008 (Henry Hub: 58 to 99 quotes a year
  from 1998 to 2006 against about 250). The chart does not join over more than seven days without a
  quote, a lone quote is drawn as a dot, and an average over a period names how many quotes it holds
  ("only 2 of about 21 trading days") and offers the monthly average of the same benchmark. Nothing is
  interpolated. The missing days are not recovered: ALFRED vintages need a key and their republication
  terms are not confirmed.
- **Which series a commodity opens on.** The first series of a commodity in `data/prices/index.json`
  is the one its page, its price figure and the price drawer open on. A commodity with a daily or a
  monthly series never opens on an annual one, and `OPENS_ON` in `pipeline/prices/build_prices.py`
  names the series for every commodity that has more than one (bauxite opens on bauxite and not on
  alumina, rare earths on NdPr oxide, cobalt on the US spot price of cathode, the row of the USGS
  file that names its product and its source); a test fails for a commodity with several series and
  no entry. The commodity pages load `data/prices/figures.json` (one entry per commodity, the first
  series with its board figures) and not the whole index.
- **Price board.** For every price series the builder precomputes the last value and its date, the
  change over 1 week (daily series), 1 month, 3 months, since the last observation of the previous
  year and 1 year, and the position of the last value between the lowest and highest of the last 52
  weeks (the last 12 months for a monthly series). A reference is the last observation on or before
  the same date one week, month, quarter or year earlier (at most 7 days before it for a daily series,
  the same month for a monthly one); without one there is no figure. These are arithmetic on the
  published values, credited to their source, not Atlas estimates. The commodity pages show the last
  price and its one-year change from the same figures.
- **Spreads and ratios** are computed in the browser from two published series of the same frequency
  and unit, wherever both have a value, and are labelled as arithmetic on the two named series: Brent
  minus WTI (daily and monthly), Brent minus Dubai, European gas minus Henry Hub, Japan LNG minus
  European gas, Newcastle minus Richards Bay coal, gold to silver and platinum to gold, wheat HRW
  minus SRW and minus maize, Arabica minus Robusta, palm oil minus soybean oil, urea to maize and DAP
  to wheat. The legs' basis changes carry over (the soybean complex changed basis in January 2025).
  Crack spreads (USD per gallon against USD per barrel) and the soybean crush margin need a
  conversion factor or a yield, and are not built.
- Each series carries a note on what it measures. A series with fewer than 24 values (10 for an annual
  series, 5 for a USGS one) is rejected; a negative last price is a price (WTI, 20 April 2020).
- **Freshness.** The weekly job (Wednesday evening, with a second try on Thursday morning: EIA
  publishes the daily files on Wednesday with data to Tuesday) rejects a Pink Sheet workbook in which
  a mapped column, a description row or an index column is missing (headers are matched without their
  asterisks and spaces), and after each build records in `data/_status/updates.json` every series
  whose last observation did not advance as fast as its cadence allows: a daily series more than 21
  days old or 120 days behind the newest of its source, a monthly series once the next month is overdue
  or 6 months behind the newest of its source. A late series is also marked "late" in the drawer and on
  the board. A series that its publisher stopped (a daily or monthly series that ends more than 6
  months, or 120 days for a daily one, behind the newest series of its own source) is marked
  `closed` by the build: it is recorded once in the status of its source (state `closed`, with its last
  period), listed as closed, hidden from the board and no longer checked; a series that is only late
  keeps raising its alert. In the "Data freshness" table of the About window, a source that has never succeeded and has failed fewer runs
  than its alert threshold (three for a weekly source) shows the badge "Retrying", with the note that the last check did not complete, and
  its family line says "retrying"; at the threshold the badge reads "Check failing". The annual job rebuilds the prices after a new USGS edition. On a price
  chart an event that names commodities is shown when one of them is charted, or when an alert that covers
  one points to it, and an event that names none is always shown (the rule of the timeline). `web/scripts/validate-data.mjs` checks that the series files agree with the index.
- Baltic Exchange freight indices are proprietary and are not shown.

## 8. Discrepancies

When sources disagree (for example USGS and EIA, or USDA PSD and customs data), the official or
primary source is shown and the difference is noted in the commodity file's `discrepancies` field.
For the limits of a port, the page cited and the World Port Index are both shown, each under its own source, and the
two measures are named (section 11).

## 9. Licences of derived figures

Figures computed by the atlas (source id `atlas`) are released under CC BY 4.0; the third-party
datasets they are computed from keep their own licences, and material adapted from Wikipedia is CC BY-SA 4.0.
See `NOTICE.md`.

- The rows of the gateway, transit-port, draught and mode tables that cite a Wikipedia article
  (`pipeline/freight/gateways/*.py`, `vessel_rules.py`, `modes.py`) are adapted from Wikipedia and are
  CC BY-SA 4.0; each keeps the article's URL, which the lane files publish beside the port, and
  `NOTICE.md` lists the articles.
- Figures compared with or capped by IMF PortWatch (the chokepoint shares and check K9) carry
  "IMF PortWatch, data adapted" and stay subject to the IMF's terms.
- The weekly port traffic sums (section 5) are PortWatch's figures added into weeks and keep the source id
  `portwatch-port-traffic`, as the chokepoint weekly averages keep `portwatch`, not `atlas`: they carry "IMF PortWatch
  (IMF and University of Oxford), data adapted", are never labelled "Atlas estimate" and stay subject to the IMF's terms.
- A few coordinates of the infrastructure layer come from OpenStreetMap (ODbL 1.0, "© OpenStreetMap
  contributors"); `NOTICE.md` lists them.

## 10. Commodity pages: units, conversions and estimates

Built by `pipeline/commodities/build_commodities.py`. Each table keeps the unit and basis of its
source; where the atlas converts a figure or estimates it, the figure says so.

- **Atlas conversions**, printed in brackets beside a headline figure with their factor (source id
  `atlas`), each factor written as it is used, so that every converted figure reproduces from it:
  - crude oil, **7.33 barrels per tonne**: the ratio of EIA's own series for United States crude
    production in thousand barrels a day and in thousand metric tons (1980 to 1999); other grades
    and other countries differ;
  - LNG, **1.36 bcm of gas per Mt of LNG** (48.03 bcf, Natural Resources Canada's conversion factors
    for North American energy information, 2025; it assumes a typical LNG composition);
  - potash, **0.6318 t of K2O per tonne of potassium chloride** (the K2O content of pure potassium
    chloride, from molar masses): USGS production in K2O is converted to potassium chloride so that it
    reads beside trade, which is potassium chloride (HS 310420), and the K2O figures as published
    follow it; real products hold less K2O, so their weight is somewhat higher;
  - lithium, **5.323 t of lithium carbonate equivalent per tonne of lithium** (from the abridged
    standard atomic weights of CIAAW);
  - uranium, **1 t of uranium = 1.1792 t of U3O8 = 2,600 lb of U3O8** (from the abridged standard atomic
    weights of uranium and oxygen, CIAAW, and the definition of the pound): the headline mine production
    carries million pounds of U3O8, the unit of the uranium market. Trade is gross weight of ores and
    compounds, which cannot be converted to contained uranium, so the trade tables carry no second unit;
  - LPG, **11.60 barrels per tonne**: the ratio of EIA's own series for United States LPG consumption in
    thousand barrels a day and in thousand metric tons, the same in every year from 1980 to 2019; the
    headline consumption carries kb/d in brackets. Prices are in USD per US gallon: at 42 US gallons per
    barrel (EIA, units and calculators) one tonne is 487 gallons, which the page note gives.
  - every constant behind these factors (the pound, the short ton, the troy ounce, the foot and the
    nautical mile, the atomic weights, the gallons in a barrel, the bcf per Mt of LNG, the PSD bag and bale,
    the Earth radius) is read from `pipeline/common/constants.py`, which gives for each its value, what it
    is, the page it was read on and the date; a test checks that every entry has a page and a date and that
    no builder types one of the values. The two barrels-per-tonne ratios are not constants of nature: they
    are read in EIA's own data and the module says which series.
- **Rounding**: the data keep full precision; a figure the atlas estimated or converted is
  published with three significant digits, and an estimated figure is shown with two at display
  (section 1).
- **Natural gas** is ranked on EIA's dry natural gas exports and imports in bcm (pipeline and LNG
  together), not on customs tonnes, which are unreliable for pipeline gas.
- **LNG**: the headline world total is the industry's (GIIGNL annual report, 2026 edition: world LNG
  trade 428 Mt in 2025 and 406 Mt in 2024; IGU World LNG Report, 2026 edition: 437.0 Mt in 2025), with
  publisher and year beside it. The two reports forbid reproducing their tables (GIIGNL: "Reproduction of the contents of this publication in any
  manner whatsoever is prohibited without prior consent of the copyright owners"; IGU: "No part of this publication may be reproduced [...]
  without the prior permission of the copyright owner"; the registry quotes both): their country tables are not copied. Two tables beside the
  customs tables give the exports of the two exporters whose own statistics are open, with the customs figure of each in its note: Australia, 81.24 Mt in
  2024 (Australian Government, Resources and Energy Quarterly, December 2025, table 41, CC BY 4.0, the department's estimate), and the United States,
  90.9 Mt (EIA's 4,367 bcf, converted at 48.03 bcf per Mt, an Atlas conversion), against 78.7 Mt and 73.3 Mt in the customs data; and Australia's
  five principal markets of the workbook (China 26.74, Japan 25.52, South Korea 11.57, Taiwan 8.07, India 0.12 Mt) beside the customs figure of each
  pair. It is a cross-check, not a ranking, and the customs tables stay as they are: no open source for the other exporters is loaded. The workbook is
  downloaded by hand (no scheduled job fetches it): a newer edition put in `raw/australia/disr-req` and `pipeline/trade/aus_req_lng.py` run again
  refresh the small cache, and the page says the edition it reads. The country tables are customs tonnage (371.32 Mt in 2024), below
  the industry totals because customs data miss the cargoes of some countries, so they are shown
  as an order, with no rank (`norank`); the country profiles print no rank for them either.
- **Precious metals** (gold, silver, platinum-group metals): trade is shown in fine-metal equivalent,
  an Atlas estimate: declared value ÷ the year's average price (World Bank Pink Sheet; gold
  2,388 USD per troy ounce in 2024, at 31.1034768 g per ounce), never above the customs gross weight,
  which each row's note gives. A flow whose estimate is above it is capped there (`cap: true`): its
  figure is the customs gross weight, printed as customs publish it, not rounded to two digits. Platinum-group metals are valued at the platinum price, so a flow
  rich in palladium or rhodium is overstated or understated. These groups get no transport mode.
- **Copper concentrate**: Chilean rows re-estimated at Peru's unit value (cleaning rule 8, section 1).
- **Spodumene concentrate** has no customs code of its own. It is read from HS 253090 ("mineral
  substances not elsewhere specified"), keeping only the rows to China from Australia, Zimbabwe and
  Brazil, the exporters for which a page read says that they ship lithium concentrate to China:
  30% of the code's tonnage and 67% of its value in 2024 (5.04 Mt). It is labelled an Atlas estimate,
  shown in its own table and not added to the lithium chemicals tables. Its lanes, lane file and
  pairs file carry the source id `atlas` and the method in their note (`EST_GROUP` in
  `build_lanes.py`). Its history starts in 2021: the Australian Bureau of Statistics created the
  national subheading 25309011 "Lithium concentrates" in January 2021, and no page read says what
  the code held from these exporters before, so the years 2005–2020 are published as null points
  (flag `nodata`, with the note; `FIRST_YEAR`), and the route Western Australia – China spodumene
  starts its history in 2021 too. Its ports are rows of `gateways/coasts.py` whose pages name the
  cargo at the port: Bunbury (Greenbushes technical report summary, SEC filing), Port Hedland
  (Mining Technology, Argus) and Esperance (Argus) for Australia, as options in the order of the
  Argus loadings of September 2025, and Vitoria for Brazil (Diario do Comercio). Zimbabwe's
  concentrate takes the general transit row of Zimbabwe (Beira): no page read documents its
  corridor. A flow of the lithium
  chemicals codes declared under 1,500 USD per tonne, the price of ore rather than of a chemical,
  is left out (cleaning rule 9) of the tables, the lanes and the country figures, and listed in a note.
- **Nickel**: ferro-nickel and nickel pig iron declared as ferro-nickel (HS 720260) have their own
  tables (gross weight, not contained nickel). The ore tables mix laterite ore (tens of USD per
  tonne) and sulphide concentrate (over 2,000 USD per tonne), so a low unit value is normal for
  laterite and no ore flow is flagged for it.
- **Urea production** is FAOSTAT's (Fertilizers by Product), in tonnes of product, the basis of
  the trade tables. FAOSTAT gives no world total and its reporting countries change from year to
  year, so the table lists reporting countries only and uses the latest of the five most recent
  years whose reported total is at least 80% of the best of the five (2023 in this release: the
  2024 table has no China), and it names the large exporters it lacks. USGS ammonia production in tonnes of nitrogen is shown as a
  second basis; urea holds 46.6% nitrogen.
- **Fertilisers and sulphur** (sixth release). The nitrogen, phosphate and potash pages hold several customs
  groups each, and two pages are new (NPK, sulphur). Every HS 1992 code is in one group and every group on one page
  (`pipeline/trade/hs_map.py`); the groups, with the wording of the official list of CEPII BACI
  (`product_codes_HS92_V202601.csv`), are: urea (310210); ammonia, anhydrous (281410: ammonia in solution, 281420, is not
  loaded); ammonium nitrate whether or not in solution (310230); ammonium nitrate mixed with calcium carbonate or other inorganic
  substances without a fertilising element, calcium ammonium nitrate and the like (310240); UAN, the urea and ammonium nitrate mixtures in aqueous
  or ammoniacal solution (310280); ammonium sulphate (310221); phosphate rock (2510); DAP (310530); MAP and its mixtures
  with DAP (310540); superphosphates (310310: one code for single and triple superphosphate, so TSP has no code of its
  own); phosphoric acid and polyphosphoric acids (280920); potassium chloride (310420); potassium sulphate, SOP
  (310430); the compound fertilisers with the three nutrients (310520, NPK) and those with two of them as the second
  group of the NPK page (310551 nitrates and phosphates, 310559 nitrogen and phosphorus other than those, 310560 phosphorus and potassium); and sulphur (250310 crude or unrefined, 280200
  sublimed, precipitated and colloidal; 250390 is in the group and holds no flow). Left out: the calcium nitrate
  mixtures (310260), the other nitrogen and phosphatic fertilisers (310229,
  310250, 310270, 310290, 310320, 310390), the crude potassium salts and the other potassic fertilisers (310410, 310490),
  the tablets and small packages and the rest of heading 3105 (310510, 310590).
  The customs tonnage is the gross weight of the product as declared, not tonnes of nutrient; the tables of the
  extra groups are in none of the totals of another (no tonne is counted twice, in a total, on a country page or in a
  chokepoint estimate), and the main trade table of each of the three pages keeps its own product (phosphate rock,
  urea, potassium chloride) and is named so. The shared cleaning rules (`clean.py`) treat ammonia, ammonium nitrate, UAN,
  ammonium sulphate, MAP, superphosphates and potassium sulphate as homogeneous groups, like urea, DAP and potash (rule 4 re-estimates a flow
  of 50 million USD or more whose unit value is off by a factor of three); NPK and the two-nutrient compounds (mixes of grades), ammonium nitrate with
  limestone (its pairs keep their own unit values: twelve flows between Belgium, the Netherlands and France declare 700 to 1,900 USD/t in 2006 to 2010
  against a group median of 180 to 370, and rule 4 would have trebled their tonnage), phosphoric acid
  (declared by the tonne of acid or of P2O5) and sulphur (crude and sublimed sulphur at very different prices) only get
  the gross-error rule. The sulphur page has the USGS table "Production, all forms", in tonnes of sulphur content
  (elemental sulphur and the sulphur in sulphuric acid): it is not the tonnage of the traded product. NPK has no production
  table: no free file loaded by the atlas gives it (FAOSTAT's fertiliser tables by nutrient are not loaded yet). The
  World Bank Pink Sheet has prices for phosphate rock, DAP, TSP, urea and potassium chloride only; the pages say that
  there is no free series for the other products, NPK included (the sulphur page has the USGS annual price of elemental sulphur and the urea page
  the USGS annual price of ammonia, section 7). A product that matters to a second page has
  one line on that page that names the first and links to it (`see` in the page file).
  Ports of the liquids and of sulphur: only a gateway row that names the group counts as "page names the cargo", so a
  fertiliser berth is not an ammonia terminal; the engine's fall-backs (the port used before for fertiliser, the general
  port of the country, the nearest seaport) give the port, each with its basis, and no port was added for these cargoes
  (`OWN_FAMILY` in `ports.py`). Ammonia, UAN, phosphoric acid and sulphur keep the port used before for the fertilisers of the same
  country ahead of the general port (`LEGACY_OWN_FAMILY`): Saudi ammonia and sulphur load at Jubail, as
  Saudi DAP, MAP and urea do, not at Jeddah on the Red Sea, from where four of the 20 generated corridors would otherwise be drawn; the lanes of Russia (Ust-Luga),
  Canada (Vancouver) and India (Mundra) follow the same rule for the loading end only (the discharge port of these four groups is the general port of the country, so that Mexican phosphoric acid for Canada lands at Montreal and no longer at Vancouver through Panama), and the basis printed is "port used before, no page read". Trinidad and Tobago has no
  such entry: its ammonia and UAN load at Point Fortin, the port that its urea and DAP use too. For France, one page names ammonia
  (Montoir-de-Bretagne, "a berth reserved for liquid bulk lets acids, ammonia, molasses, diester and carbon dioxide transit"); no page read names UAN,
  phosphoric acid, sulphur, vegetable oils or dry fertiliser at a French port, so the general ports answer, Fos and Le Havre, by the coast rule. The groups have lanes under their page (`COMMODITY` in `build_lanes.py`); SOP, whose trade is spread over
  193 small seaborne pairs, has a lower floor (0.01 Mt, `FLOOR` of `build_lanes.py`): its lanes cover 69% of its seaborne tonnes (the `coverage` of its lane file;
  the default floor of 0.05 Mt kept 21%). Generated corridors: the new groups have a cap of their own, 20
  routes (`LATER_GROUPS` in `generated_routes.py`), so that the routes of the earlier groups do not depend on them (since the sixth release the ports of
  France have changed nine of the routes of the fifth release and ended two: see the generated corridors, section 3).
- **Grains, oilseeds and pulses** (sixth release). Four pages are new (barley, sorghum, sunflower, pulses) and the
  wheat, corn and rapeseed pages hold more products. Every HS 1992 code is in one group and every group on one page
  (`pipeline/trade/hs_map.py`); the groups, with the wording of the official list of CEPII BACI, are: barley (100300; malting
  and feed barley are not told apart); grain sorghum (100700); sunflower seeds (120600; oil seed, seed for sowing and snack seed
  are not told apart); sunflower-seed or safflower oil, crude and other (151211, 151219: one code holds two oils, so the group is
  "Sunflower and safflower oil"); rape, colza or mustard oil, crude and other (151410, 151490: "Rapeseed, canola and mustard
  oil"); the oil-cake and other solid residues of sunflower seed oil extraction (230630) and of rape or colza seed oil extraction
  (230640), here "meal"; wheat or meslin flour (110100); brewing or distilling dregs and waste (230330: the code of distillers' dried
  grains, which it holds with brewers' grains and other dregs, so the tables are not a DDGS series); and the dried leguminous
  vegetables, shelled (071310 peas, 071320 chickpeas, 071331 to 071339 beans, 071340 lentils, 071350 broad and horse beans,
  071390 other). Left out: malt (1107), oats (1004), rye (1002), the other flours, groats and starches (1102 to 1109), the other
  oilseeds, oils and meals (1207, 1512 other than sunflower, 2306 other than sunflower and rape), fresh pulses. The customs tonnage
  is the gross weight as declared; the tables of a product are in none of the totals of another. Pulses are one customs group for
  the main tables and the lanes; the kinds are read from the six-digit rows of the same pair and year
  (`pipeline/cache/baci_hs6_detail.csv.gz`, from 2019; the main tables' tonnage is split by the shares of the raw rows, so the
  cleaning rules are kept), as the two codes of unwrought aluminium are (`SPLITS` in `metals.py`). Barley, sorghum and sunflower
  seed have the USDA PSD tables and balance of a grain page; the sunflower and rapeseed pages add the PSD production and domestic use of the oil and the
  meal (the Oil and Meal commodities of the PSD file), and USDA's oil is sunflower oil only or rapeseed oil only, while the customs
  codes hold safflower and mustard oil too. The pulses page has no production table: the PSD file has no pulses and no other file
  on disk gives them. Wheat flour and the dregs are trade tables only and have no lanes: customs gross weight does not tell bulk from bagged,
  boxed or containerised cargo, and no free source gives the split. The shared cleaning rules treat barley, sorghum, sunflower oil, rapeseed oil and the two meals as homogeneous groups
  (rule 4), and sunflower seed, pulses, wheat flour and the dregs get only the gross-error rule. The World Bank Pink Sheet gives
  the price of sunflower oil and of rapeseed oil (the pages say that the price is the oil's), and barley and sorghum monthly to August 2020, then as the annual average of the annual workbook (section 7);
  there is no free series for the seed, the meals, the flour, the dregs or the pulses. Ports: the engine's own fall-backs
  (page names the cargo, the general port of the country, the port used before, the nearest seaport) give each lane's ports with
  their basis; no port was attached to these cargoes, and the sunflower and rapeseed oils take the rows written for palm and soybean
  oil (a "vegoil" gateway row), so that a palm-oil terminal can be the port of an import of sunflower oil; these two
  oils show such a port with the basis "general port of the country", as no page read names either oil there (`GENERAL_BASIS` in `ports.py`; no port changed).
  France has Rouen and La Pallice for grain, oilseeds and meal (French Wikipedia: Rouen "the first European port for cereals", 12.7 Mt in 2023, with China,
  Morocco and Algeria as its main trading partners and eight "less common destinations"; La Rochelle "second French port for cereal exports") and Montoir for soya meal, chosen against Fos by the
  partner (coast rules `fra-grain-ports` and `fra-coast-grain`): barley from France to the Netherlands is 321 nm from Rouen (65 nm of the Seine included; snapped to the coast near Dieppe, Rouen would read 196 nm), not 2,092 nm from Fos.
  The two pages give figures for the ports and none for the split between them: Rouen "12.7 Mt in 2023 (50% of French exports)" of cereals for the whole port, La Pallice 3.0 to 3.5 Mt a year of
  cereals in 2023 to 2025. The principal port is chosen by rule, an Atlas assumption with its reason in the rule: Rouen for the eleven partners
  that the Rouen page names (China, Morocco and Algeria, then, as destinations "less common" in 2023, Mauritania, Mexico, Thailand, India, Colombia, Madagascar, the United States and
  South Africa: the principle of the engine is that the page names the partner at a port, so that port) and for those of the Channel, the North Sea and the Baltic (the United Kingdom, Ireland, Belgium, the Netherlands,
  Germany, the Nordic and Baltic countries, Poland), La Pallice for every other partner outside the Mediterranean and the Black Sea (the Atlantic coast of Europe, the rest of Africa
  outside the Mediterranean, the Americas other than Mexico, Colombia and the United States, the Middle East, the rest of Asia and Oceania); and Fos stays the port
  of the Mediterranean and Black Sea partners, Russia included (its grain port, Novorossiysk, is on the Black Sea). No page says that a partner is served by
  one of the two ports only, so the other port is an option of every one of these partners: the lane page prints both distances and says that no source gives the
  split (24 of the 24 lanes of French grain, oilseeds and meal that load at Rouen or La Pallice, 17 and 7, carry the other port as an option;
  fifteen of them have a partner near the Channel or the Atlantic such as the Netherlands, the United Kingdom, Portugal or Senegal: these fifteen lanes gained the option, and no
  passage and no estimate changed with it, the two ports being on the same seaboard). The page's tonnages for China, Morocco and Algeria (2.48, 2.07 and 1.15 Mt) are those of the whole port's trade with each country, not of grain,
  and the atlas does not use them: the eight "less common destinations" have no tonnage on the page, and what is assumed is the principal port of their pairs, not a quantity. Adding the eight to the named set moved the principal port of 11 of the 202 pairs with France as exporter in these twelve groups
  (barley to Colombia, India, Mexico and South Africa; pulses and rapeseed to the United States; wheat to Madagascar, Mexico, Mauritania, Thailand and the United States) from La Pallice to Rouen, 0.93 Mt in all
  (the distances are 52 to 282 nm longer; no passage, no class and no estimate changed, and no pair without France as its exporter moved). The split between the two
  ports is the atlas's rule, not a measured share. In 2024 the atlas loads 12.3 Mt of French wheat, barley, corn, sorghum and rice by sea at Rouen, 2.5 Mt at La Pallice and 0.9 Mt
  at Fos (Rouen's page gives 12.7 Mt of cereals for the whole port, and the page of La Pallice 3.0 to 3.5 Mt a year,
  so that the atlas's principal-port tonnage of La Pallice is now below the range of its page: the other port of every pair stays an option, and the page gives no split); the lanes of La Pallice carry
  no river leg (the leg of the Seine is for Rouen). Generated corridors: the eight groups of lanes share a cap of
  10 routes (`LATER_GROUPS`).
- **Metal bulks** (sixth release). Six pages are new (ferrous scrap, pig iron and DRI, chromium, ferro-alloys,
  molybdenum, graphite) and the metallurgical coal page holds the customs tables and lanes of coke. Every HS 1992 code is in
  one group and every group on one page (`pipeline/trade/hs_map.py`); the groups, with the wording of the official list of
  CEPII BACI, are: ferrous waste and scrap, the whole of heading 7204 (cast iron 720410, stainless steel 720421, other alloy
  steel 720429, tinned iron or steel 720430, turnings, shavings and the like 720441, other scrap 720449, which holds most of
  the heading, and remelting scrap ingots 720450; the grades are not told apart); pig iron, alloy pig iron and spiegeleisen
  (7201); direct-reduced iron (7203: 720310 in lumps, pellets or similar forms, and 720390, spongy ferrous products and iron of
  99.94% purity or more, which is not only direct-reduced iron); chromium ores and concentrates (261000); coke and semi-coke of
  coal, lignite or peat (270400); molybdenum ores and concentrates, roasted and not (261310, 261390); natural graphite in powder or
  flakes and in other forms (250410, 250490); and the ferro-alloys of heading 7202 other than ferro-nickel, in five groups:
  ferro-chromium (720241, 720249), ferro-manganese (720211, 720219), ferro-silico-manganese (720230), ferro-silicon (720221,
  720229) and the other ferro-alloys together (ferro-silico-chromium 720250, ferro-molybdenum 720270, ferro-tungsten 720280,
  ferro-titanium 720291, ferro-vanadium 720292, ferro-niobium 720293 and the ferro-alloys not elsewhere specified 720299).
  Ferro-nickel (720260, which holds nickel pig iron) stays in its group of the nickel page. Heading 7202 as a whole is 26.3 Mt
  of exports in the 2024 customs file, 10.1 Mt of it ferro-nickel: the page holds the other 16.2 Mt (15.8 Mt in its tables, the
  flows under 1,000 t and USD 1 million being left out). The steel group is still chapter 72 without headings 7201 to 7205 (the
  granules and powders of 7205 are in no group): its totals are the same to the tonne (the test `test_metal_bulks.py`). The
  customs tonnage is the gross weight as declared; the tables of a product are in none of the totals of another, and each page
  names the product that lives on another one by a "See" line (chromium, manganese and nickel point to the ferro-alloys page, and
  it points back to them). The ferro-alloys page opens on ferro-chromium, its largest alloy, and the four other tables follow;
  its key figure is that alloy's. Production: USGS (Mineral Commodity Summaries) gives chromite mine production in gross weight
  and reserves in Cr2O3 content (the file also gives reserves in ore, for 2024, an earlier year than the rest of the table: not
  shown), pig iron production by country (Iron And Steel, world production), and molybdenum (contained molybdenum) and natural
  graphite mine production and reserves; it gives ferrous scrap for the United States only (the United States block of the
  scrap page), and no world table of the ferro-alloys or of direct-reduced iron: those pages say "No production table". The
  figures of the steel industry's associations are not loaded (their terms are not settled). The World Bank Pink Sheet has no
  series for any of these products (its steel series is an index of steel products). The USGS annual prices of chromite, ferro-chromium,
  heavy melting scrap, molybdenum and natural graphite are on their pages (section 7), each with a note saying which product of the page it is the price of; the
  pig iron and direct-reduced iron page and coke have no free price series and say so, and the ferro-alloys page has ferro-chromium and 75%
  ferrosilicon, and no series for the other alloys. Ports: the engine's own fall-backs, with their basis; no port was attached to these cargoes. Chromium ore takes the ore rows and
  the port used before, coke only a row that names it (then the port used before for coal), and scrap, pig iron, direct-reduced iron and
  the ferro-alloys the general port of the country, as steel does (the ore fall-backs would have sent the 20 Mt of Turkish scrap
  imports to the nearest seaport of Turkey, Samsun on the Black Sea, by the Bosphorus). The atlas gives Turkey, for scrap, pig iron and
  direct-reduced iron, the ports of its two steel works named by the Erdemir page (Karadeniz Eregli on the Black Sea, Iskenderun on the Mediterranean; the page names
  the works and the port of Eregli, not the cargo, and the basis printed is "page names the plant, not the cargo"), chosen by the partner (coast rule `tur-coast`: the Black
  Sea partners take Eregli, the others Iskenderun, with the general port of Izmir as the second option), because Mersin, the only other general port, is on the far coast from the Black Sea partners. Turkish chromite keeps Samsun
  (no page read names a chromite port: 1.5 Mt at the Bosphorus), and the ferro-alloys the general port; the Aegean and Marmara have no row of their own (the Aliaga page names
  no steel works and the Derince page names vehicles). The Erdemir page names the steel works and not where scrap lands, so the share that the Turkey page prints for a
  port (Iskenderun 89.9% of the scrap imports) is the share of the atlas's tonnes that its typical port carries, an allocation by rule, and the freight block says so before its figures
  (`freight.note` of the profile). Scrap, pig iron and
  direct-reduced iron sail in bulk carriers all the same, and the chokepoint estimates compare them with the dry-bulk ships of PortWatch. Molybdenum and graphite are tables only, without lanes. The shared cleaning rules apply only the
  gross-error rule to these groups (rule 3 of section 1): none is a single graded product, except coke (HS 2704), one product priced by the tonne. Mozambique →
  India 2016, 65 Mt declared for USD 245 million (4 USD/t), would triple the world and seaborne series of that year (91.8 and 83.3 Mt against 31.6 and 22.9 Mt in
  2015). Rule 4 can repair such a row as a flagged Atlas estimate (1.3 Mt), so coke was tried in it; rule 4 is checked on the
  fourteen groups of the three batches that it covers, with one criterion: where the pairs that rule 4 would re-estimate declare, in at least three other years,
  a unit value beyond the factor 3 on the same side, and carry more than a tenth of the tonnes that rule 4 adds or removes over all years, the group leaves the
  set. Rule 4 re-estimates 15 rows in 7 of the 14 groups (potassium sulphate 1, UAN 1, ammonium sulphate 1, sorghum 2, sunflower oil 1, rapeseed meal 2, coke 7) and
  none in the 7 others (the largest change of a world total of a year is 8.0%, sorghum 2019); no re-estimated row of the 5 groups that stay belongs to such a pair.
  For coke 3 of the 7 rows do (33% of the tonnes: China → United States 2002, 2003 and 2005), and for sunflower oil the one row (Ukraine → Nepal 2021), so both
  groups leave the set and keep the reported tonnage of their rows (coke: Belgium → France 2004, China → Brazil 2009, China → India 2006 and 2007, China → United States 2002, 2003
  and 2005; sunflower oil Ukraine → Nepal 2021). China → Brazil 2009, 108 kt declared at 825 USD/t, is one of them: the pair's own unit value is 467 to 518 USD/t in 2008 and
  2010 to 2012, the years of the Chinese export tax, so the criterion keeps the reported tonnage rather than the 340 kt that rule 4 would estimate.
  Since the sixth release (a choice made without the owner, listed in PROGRESS.md) the atlas drops all of Mozambique's coke by rule 5 of section 1 (`DROP`): the EIA series of coke production gives
  Mozambique none in any year, and its exports under the code (16 years, 2005 to 2024: 65.2 Mt in 2016, 65.0 Mt of it to India at 4 USD/t, 3.8 and 8.7 Mt at 26 and 56 USD/t to India in 2021
  and 2022, 1.63 Mt in 2024) are probably coal declared under the coke code, a hypothesis that no source establishes. The world coke series reads
  26.6 Mt in 2016 (was 28.1), 28.3 in 2017 (39.8), 32.2 in 2021 (38.6), 31.5 in 2022 (41.5) and
  32.9 in 2024 (34.5), and India's coke imports of 2024 5.4 Mt (6.5). The coke page says what was left out (1.63 Mt in the customs file of 2024) and that these rows
  are not counted, and its note on the tables that hold under 97% of the file agrees with it. After the rule the customs series of the page is above the EIA export table of the same page
  in 17 of the 20 years 2005 to 2024 (below it in 2006, 2007 and 2016), and more than 10% above it in 2008, 2009, 2010, 2011, 2012, 2019, 2022 and 2023: the two sources count different things
  (HS 2704 is every coke and semi-coke of coal, lignite or peat; EIA's table is metallurgical coke by country) and the atlas does not reconcile them. Coke, pig iron and direct-reduced iron are in the unit-value check K13. Generated corridors: the nine
  groups with lanes share a cap of 10 routes (`LATER_GROUPS`).
- **"Other countries"**: where USGS lists producers in full, its own "Other countries" line is shown
  as the last row, apart from the countries it names; countries it names beyond the first ten rows
  are counted in a separate line, not in "Other countries". **Shares on the sum of the lines**
  (one rule, in `ranked()` and `Usgs.ranked` of `build_commodities.py`): where the country lines
  (with USGS's "Other countries" line, drawn or not) differ from USGS's rounded world total by more
  than 0.05% (`LINES_OVER_WORLD`), above it or below it, the shares are computed on the sum of the
  lines. Below it only counts for a table that has an "Other countries" line, which covers every
  producer the table does not name, so that the lines are the whole (zinc: 12,540 kt against a
  published 13,000; gold production: 3,250 against 3,300 t); above it counts for every table
  (17 tables in the 2026 release, from manganese reserves, 1,798,000 against a published
  1,700,000 kt Mn, to silver reserves, 610,400 against 610,000 t). A table without that line whose
  lines fall short of the published total (nickel reserves, lithium production) keeps the published
  total, and its "Rest of world" is what the source does not list. The table keeps the published
  total as `worldPublished` and says so in its note, and the key figure of the page stays the
  published total.
- **Rice** flows are converted from paddy (HS 100610) to milled equivalent at the USDA PSD milling
  rate of the exporter (the world average where PSD has none), the factor and its market year being
  written in each row's note. Such a row is an Atlas conversion, not an estimate: its note starts
  "Atlas conversion", it carries no estimate mark, and its tonnage keeps three significant digits.
- **Metals pages** (`pipeline/commodities/metals.py`; tests in `pipeline/tests/test_metals.py`):
  - **Shares on the sum of the lines**: the rule of the "Other countries" paragraph above, which
    holds for every USGS table of these pages.
  - **Two USGS years.** The USGS file holds two columns, 2024 and 2025. Both are shown side by side
    on the page, from the series by year, in the words the file supports: values it marks
    "Estimated." are USGS's own estimates, shown with an "e". The file does not call either year
    "revised".
  - **Apparent consumption** of refined copper, primary aluminium and crude steel is an Atlas
    estimate: production plus imports minus exports, by country, for 2024, the year of both the
    USGS column and the customs data. Production is USGS refinery output (copper), smelter output
    (aluminium) or raw steel; trade is refined copper HS 7403 only (HS 7402, unrefined copper and
    anodes, is left out: the six-digit split comes from `pipeline/cache/baci_hs6_detail.csv.gz`,
    written by `pipeline/trade/extract_hs6_detail.py`), unwrought aluminium HS 7601, and steel
    products HS 72 without 7201 to 7205 in product weight, not converted to crude-steel equivalent
    (no conversion is read on a page). Imports and exports are summed from the cleaned customs frame
    before any rounding (a flow of 22 t is not lost to a table in Mt). A country is listed when USGS
    gives its production and the customs extract has its imports and its exports; one with no import
    or no export row (the extract omits flows below 1,000 t and 1 million USD) or with a negative
    result is left out, and the note says which row is missing: it is not counted as zero, and it is
    not a gap in USGS production. A country that trades but has no USGS production line is not in the
    table, which is therefore not a ranking of the world's consumers: no rank is printed (`norank`),
    the remainder is "Countries not listed", and the note names the largest of those countries by
    customs net imports (imports minus exports, arithmetic on the customs figures): their apparent
    consumption is that plus their own production, which is not known and is not counted as zero. Stock
    changes are not known. The world total is the USGS world production of the same year (trade nets
    out in the world), on which the shares and "Countries not listed" are computed. Rows carry the
    source id `atlas`, three significant digits in the file and two on the page, and their three
    inputs in the note. The United States apparent consumption that USGS states (a different
    definition for each product, given beside it) and its net import reliance (Fig2 of the Mineral
    Commodity Summaries, with the main sources of its period) are shown as published figures, their year
    and period read from the names of the file's columns, apart
    from the estimate. worldsteel's tables are not copied.
  - **Value and unit value.** Rows of the customs tables and the flows of the metals pages carry the
    declared value (`usd`, USD) and the unit value (`uv`, USD per tonne, three significant digits at
    most). The unit value is the quotient of the unrounded value and tonnage, in the tables as in the
    flows, so that the two agree; customs give whole tonnes and whole thousands of USD, so a row of
    22 t or of 5 thousand USD carries fewer digits and shows fewer.
    A row with 10% or more of its tonnage estimated from the declared value, and every flow whose
    tonnage is an Atlas estimate, has no unit value: the value was used to estimate the tonnage.
    The fine-metal tables of gold, silver and platinum-group metals show the value only.
  - **Concentration.** For every table with a world total: the share of the first country, of the
    first three, and the Herfindahl index (the sum of the squares of the countries' shares in
    percent, from near 0 to 10,000), computed on the countries the table lists. Where USGS's "Other
    countries" line is large the countries cover less than the whole: the index of the whole market is
    at least the figure shown. Only tables of the world are counted: the tables of the 27 member
    states of the EU (`scope` "EU"), whose shares are of the EU total, have none.
    It is arithmetic on published figures and carries the estimate mark only where a row is an
    estimate.
  - **Notes on trading places.** A country that both imports and exports the same product in
    similar tonnages (each at least 1.5% of its table, the smaller at least half of the larger) and
    that the page's USGS tables do not name as a producer gets a note on both rows, worded as a
    possible reading and fitted to what the table counts (ore or concentrate "bought, blended or
    shipped on", metal "bought, stored or shipped on"). A smelting or refining country that USGS
    does not name (Thailand for tin) carries the note too.
    A flow declared at under half of the tonne-weighted median unit value of its product (unwrought
    aluminium, refined copper, zinc, lead, tin, alumina, coke, pig iron and direct-reduced iron) is flagged by check K13
    (`pipeline/trade/checks.py`) and worded as a hypothesis through the caveat registry
    (`caveats.py`), with the metal's Pink Sheet price beside it where the repository has one.
    Unwrought aluminium is shown by code, HS 760110 (not alloyed) and HS 760120 (alloys).
  - **Iron content** of iron ore (production and reserves) is the USGS table as published.
  - **Importer in transit** (`transit_notes` in `metals.py`). The hub rule above needs the country in the export table too, so
    it never fired for Mozambique, which customs data record as the second importer of chromium ore and of ferro-chromium (South African ore and alloy,
    received overland) with no production and no material export. A row of an import table gets a note when the country has at least 10% of the
    table's world imports, no line in the page's production tables, no export line of note (under 1.5% of the world exports and under a tenth of its own
    imports) and most of its imports are overland in the pairs file of the group (`m` = land). The rule is a detector: it prints a note only for the rows of
    a reviewed table (`TRANSIT_REVIEWED`), because it cannot tell from the tables on disk a transit country from a neighbour that uses the product. It
    finds four rows in this release. Two are reviewed: Mozambique's imports of chromium ore (Chromium page) and of ferro-chromium (Ferro-alloys page).
    The note says what the customs data record, that these tonnes may be cargo in transit to a port and not the country's own use, as a reading and not as a
    finding, and why the row was kept: the ore and the alloy come overland from South Africa, the first producer in the USGS table of the Chromium page;
    Mozambique has no line in that table (each clause is checked against the built pages by `test_fncd.py`). The note computes what the country's own
    exports are from its row of the exporters table, never "not an exporter": "has no production line in the tables of this page and exports of
    41 kt (0.15% of the world exports, 0.47% of its own imports)" for the chromium ore, 21 kt (0.27%, 1.8%) for the ferro-chromium. The page repeats it in its notes (a row note is a tooltip) and the country profile line
    carries it. The other two rows (Saudi Arabia's imports of direct-reduced iron from Oman and Canada's imports of MAP from the United States) are an
    overland delivery to a neighbour that uses the product, the plain reading: they get no note and are listed in `pipeline/commodities/QA.md` as "detected,
    no note". The overland test keeps the rule off the importers that consume the product and receive it by sea (Japan's coking coal, Morocco's ammonia and
    sulphur). It reads the main table of the pages in `TRANSIT_NEW_PAGES` (sulphur, NPK, barley, sorghum, sunflower, pulses, rapeseed, ferrous scrap, pig iron, chromium, ferro-alloys, molybdenum and graphite) and the further tables of the pages that list several customs groups (`EXTRA_GROUPS`: the urea, phosphate, potash, NPK, wheat, corn, sunflower, rapeseed, pig iron, metallurgical coal and ferro-alloys pages); the main table of every other page is not read. Three pages were read for a statement that South African chromite
    is shipped through Maputo: the Port of Maputo article says that its record volumes of 2023 came largely from South African mines and that transit
    cargo is a large part of the traffic of the ports of Mozambique, and does not name chromite, so no source is cited and the wording stays a possible
    reading.
    The same kind of note is written for an importer that is the transit port of a landlocked country in the engine's transit tables (`TRANSIT` of
    `gateways/energy.py`), where the customs figure reads like that country's own trade: Djibouti, second importer of the two-nutrient compound
    fertilisers in 2024 (1.64 Mt, 0.04 Mt in 2015), is the port that the transit table gives Ethiopia ("Principal maritime outlet for Ethiopia's trade", Wikipedia, Port
    of Djibouti), and no import of the product by Ethiopia is recorded in 2024 (0.96 Mt in 2023); the row and the page say that some of these tonnes may be Ethiopian cargo declared
    at the port, a possible reading, not established here.
- **USDA crops: forecast, estimate, balances, EU member states, Russian grain** (audit M-076, M-025, M-024, C-104, C-045).
  - *Year rule*, in `_latest_inputs()` of `build_commodities.py` and nowhere else: the page shows the newest marketing year the PSD
    file holds (`PSD_MY`, 2026/27 in the November 2026 file), which USDA publishes as its forecast of the year in progress, and
    beside it the year before (2025/26), USDA's estimate. The file has no column for either word: they are given by position
    (the newest year, the one before it), the atlas's own words, and the production table and the Balance block say so in one
    sentence (`YK_RULE`; USDA's World Agricultural Production circular heads the same two years "Prel." and "Proj." in its
    tables and writes "estimates" and "forecasts" in its text). With a History year the USDA tables follow that year (the slider stops
    at 2024, so 2024/25 at most) and the page says that the estimate and the forecast are shown when History is closed. The table, the key figure, the history file and the map colours all follow the
    same year. The month of the report is the file's own `Calendar_Year` and `Month` of the newest revision of the commodity's rows
    for that year (coffee is revised twice a year, the grains monthly); it is printed on each table ("USDA report of November 2026").
    PSD adds the next year in May, and the rule moves on with it. Comparisons with customs data (the checks K1 and K2, the
    discrepancy lines, the rice milling rates) keep the marketing years of the customs year (`PSD_EST`, the estimate year).
  - *Balance of a crop* (`Psd.balance`, `data/commodities/<id>.json` key `balance`, page block "Balance"): harvested area, yield, production,
    beginning stocks, domestic use with its parts the file gives (crush, feed, food, industrial; for sugar, human consumption and other
    disappearance), exports and ending stocks for the estimate year and the forecast year side by side, and the same stocks for China
    and for the world without China. The world is the sum of the countries the file lists (it has no world row). Stocks-to-use is
    ending stocks divided by domestic use of the same market year (total disappearance for sugar), exports not counted; USDA's own
    `Stocks-to-Use` attribute of a cotton country divides by domestic use plus exports, so the two differ a little. Yield (production
    over harvested area), the world without China and the ratios are arithmetic on two USDA figures of the same year: source `atlas`, a
    note that says how, no "Atlas estimate" mark, printed in italics. The Thai sugar stock, which the file puts above the year's
    production, carries a note with the two figures of each year, not an explanation.
  - *EU member states*: USDA PSD counts the European Union as one entity, trade between members left out, and its row stays
    as it is. The member states have their own tables beside it, each with its own source and year, which are not added to the USDA row
    and need not agree with it: production from FAOSTAT crop production (`pipeline/cache/faostat_eu_crops.csv`, calendar year, wheat, maize,
    rice as paddy, soya beans, rapeseed, sugar beet as crop weight; shares are of the EU total, the FAOSTAT world total is kept as `worldAll`), and
    customs exports and imports from the cleaned CEPII BACI frame, trade between members included, each member's total split into the part
    with other members and the part with countries outside the EU. For the European Union as a whole, the same split is written on the
    USDA row (`eu` of the exports and imports tables): intra and extra add up to the members' total, and the extra part is the figure
    comparable with USDA's. The tables of the member states carry `scope: "EU"`, `scopeLabel` ("EU member states"), `world` (the total of
    the 27, the base of their shares) and `worldAll` (the world total of the same source and year). On the map, exports and imports
    keep USDA's European Union value on every member state (one source, one year, one definition of trade: customs figures that
    include trade between members would stand beside USDA's on one scale; those tables are `noMap`, rice included), and the tooltip
    of a member says that USDA gives the European Union as one entity and names the table that holds the member's own trade.
    Production is coloured with the member's own FAOSTAT figure, as its share of the FAOSTAT world total, when the table is on the
    basis of the USDA table (the latest year only, it has no series by year); the legend names both sources and years. Rice (paddy)
    and sugar (beet) production stay on the USDA value.
  - *Russian grain*: Russia has not published its customs data since 2022, so its flows rest on what importers declare. The caveat
    registry (`pipeline/trade/caveats.py`, `_grain_gap`) states, for wheat, maize, soya beans, rapeseed, soybean meal and oil, the
    customs figure against the two USDA marketing years that overlap the customs year, the percentage by which it is below
    them, how much of the customs tonnage is the atlas's own estimate from the declared value (cleaning rules; wheat 2024: 11.6 Mt of
    34.5 Mt, mostly Egypt) and the gap on the tonnage as reported alone, and the importers that took the grain in the three years 2019 to 2021 (0.5 Mt a year or more) and have none recorded in the
    build year, whose flows and lanes therefore show 0. The page shows it once, above the flows (`gaps` of the commodity file). The
    atlas does not scale the flows or lanes to the USDA total.
- **Publishers cited for a headline figure only**: GIIGNL and IGU (world LNG trade), the World Steel
  Association (world crude steel production, 1,848.9 Mt in 2025, World Steel in Figures 2026, data finalised 8 June 2026, which revised the 1,849.4 Mt of its press release of 23 January 2026; its terms of use do not allow its country table to be reproduced without written consent, a clause that the registry records, so the steel page keeps the USGS table), the World Gold Council (world mine
  production) and the International Cocoa Organization (world cocoa bean production and world grindings per crop
  year). Each figure carries its publisher, year and link and stands beside the atlas's table; their
  tables are not copied.
- **Full lists and "Rest of world"**: every table stores every country the source gives a value for
  (a value that rounds to 0 in the table's unit is left to the world total). The page draws the
  first ten rows, then "Rest of world": the world total minus the rows drawn and the source's own
  "Other countries" line, with the number of countries it holds and, when the world total holds
  amounts the source does not give by country (codes that are not countries of the atlas, regions,
  rounding), the words "and amounts not given by country". "Show all (N)" opens the full list.
  Aggregates are never counted as countries; the one aggregate row is USDA PSD's European Union
  (printed "European Union", plain text, no country page), and no member state is listed in the same table: the crop pages
  have tables of the member states from other sources (see "USDA crops").
- **Series by country and year** (`pipeline/commodities/history.py`, `data/commodities/history/<id>.json`):
  each year is rebuilt by the same table writer as the latest table (same reader, cleaning rules,
  world total and estimate marks), so the latest year of a series is the table of the page (the
  builder, the validator and the tests check it). Years: CEPII BACI 2005 to its latest year, EIA
  2005 to the year of each table, USDA PSD marketing years 2005/06 to the latest, USGS the two years
  of the edition, labelled only "as published in USGS MCS 2026" (USGS marks single values
  "Estimated.", shown as the source's estimates; the file gives no word such as "revised" for a
  year). With a History year, a table that has the year shows its ranking with the shares on that
  year's world total; a table without it stays the latest and says "no series for" the year. A
  past-year table keeps the caveats of its table, except a caveat written for some years only
  (`caveatYears`: the LNG comparisons with the industry totals and the uranium comparison with mine
  output are for the latest year, the LPG caveat for the years in which the United States is
  converted from barrels per day, the coal reserves caveat from 2014, and the crude oil caveat on
  Iran, which has no row, for the latest year), which gives way to its short or general form (`caveatShort`,
  `caveatPast`) in the other years; an Atlas-estimate table keeps its method note. Rules of the
  series, each stated in the series note on the page:
  - a group read from a customs code only from a given year (spodumene, `FIRST_YEAR` of
    `build_lanes.py`) has its series start that year, with the same sentence as the lanes;
  - a value far out of line with the years around it is kept in the file with a flag (`out`), not
    ranked and not drawn: the world total of that year is 1.3 times above or below both neighbouring
    years, one country is 3 times above or below both its neighbours (or 3 times above its one
    neighbour where its series starts or stops) and carries half or more of the world's departure,
    and, where the source gives a declared value (CEPII BACI), that value did not move with the
    tonnage (a unit value within a factor 2 of the neighbouring years means a real change, kept).
    In this release it flags Namibia's uranium exports and Canada's uranium imports of 2009 and
    China's cobalt imports of 2016 (EIA's United States LPG consumption of 2021 is no longer
    flagged: it is replaced, see "Energy pages from the EIA file" below); the past-year table
    gives the figure, says it is out of line and computes the shares on the world total without it.
    Falls and rises spread over many countries (2009, 2020, 2022), Libya's crude oil exports of 2020,
    Russia's wheat exports of 2010 and Malaysia's bauxite exports of 2015 (whose declared value moved
    with the tonnage) are not flagged;
  - USDA PSD's European Union row is the source's own entity: it is "EU-25" in sugar 2005/06 and
    holds the United Kingdom until the file gives the United Kingdom a row of its own (2016/17 for
    most commodities). The row is named for what it is each year, its trend line breaks where it
    changes, and no change is computed across the break; the atlas does not add or remove members;
  - a country that split or changed code inside the period (Sudan and South Sudan, Serbia and
    Montenegro, the Netherlands Antilles; the last year of each old code is read from the CEPII
    country list) gets one sentence in the series where the new country's figures start, and no
    change is computed across that year;
  - a country that held 5% or more of the world total and has no figure after a given year is named,
    with its share, because the world totals of the later years leave it out.
  "Largest changes" lists the five largest increases and decreases from the year before to the year
  shown (the latest year without a History year; nothing to compare with in the first year of a
  series). A country with no figure on one side counts as 0 there and shows "none in" that year
  instead of a percentage; a country under 0.1% of the world total the year before shows no
  percentage either. The lane table's "Change" column follows the same rules on the lane series: no
  change against a year without a customs record or with a hidden figure (flags `nodata`,
  `suspect`), a mark on a change with a flagged year (`est`, `check`).
- **Energy pages from the EIA file** (`raw/eia/INTL.txt`, EIA International Energy Data, public domain; the
  families of series it holds are listed by `pipeline/commodities/monthly.py`'s `scan`).
  - *Monthly blocks* (`pipeline/commodities/monthly.py`, `data/commodities/monthly/<id>.json`, loaded on demand
    by `EnergyMonthly.tsx`): the last 60 months of EIA's monthly series. Crude oil production by producer (every
    producer with 0.1 kb/d or more in the baseline year), OECD imports by origin (petroleum and other liquids,
    not crude alone; the Persian Gulf and OPEC are EIA's own groups, which overlap: Qatar is in the first and
    not in the second), petroleum stocks and, for the refined
    products page, oil demand, and for the LPG page natural gas plant liquids. Every series carries three
    figures, each with its month, and a change: the average of the year before the latest month (the twelve
    months weighted by their days, which equals EIA's own annual figure: the validator and the tests check it),
    the lowest month of the latest year, the latest month, and the latest month against the average in per cent.
    These are arithmetic on published figures, not estimates. A month that EIA gives as withheld ("w"), not
    available or absent stays empty and nothing is filled in; a series whose last month is more than a year old has
    stopped and is left out. The Gulf total adds Saudi Arabia, Iraq, Kuwait, Qatar, the United Arab Emirates, Iran
    and Bahrain month by month, only for months in which all seven have a figure. The block of the year so far
    against the year before ("Monthly production in 2026 against the 2025 average") is shown only once the year has
    three months.
  - *Months without a figure in the imports by origin*: EIA leaves a month out of an origin's series when it has no
    figure (the file has the other markers "--", "NA", "w" and "ie" too, and publishes zeros as 0: 1,716 zero months
    in these series). Neither the file nor the EIA Open Data documentation read on 23 November 2026 says that an
    absent month is a month without imports, so the atlas does not fill it: the month is shown as "no figure", the
    average of the year before is shown only when its twelve months have a figure, no lowest month is printed for an
    origin with a month missing in the year, a latest month that has no figure is not replaced by an older one
    (the last figure is named with its month), and the note under the table counts the months missing. An origin
    is left out only when the months of the year before that have a figure average under 1 kb/d; never for an
    absent month.
  - *A failure of the monthly step* (EIA renames or drops a series: `monthly.py` refuses a changed series name) does
    not stop the commodity build: nothing of the monthly files is written, they keep their previous content, the
    builder says so in its output and in QA.md and ends with exit status 3, which the annual job
    (`pipeline/annual/update_annual.py`) records as the source `build-monthly` failing (the commodity step itself
    is recorded as a success), so that the next run tries again and the usual alert after three failures applies.
  - *Stocks*: EIA gives monthly petroleum stocks (crude oil and products together, not split) with a figure for the
    OECD, OECD Europe and eight countries (the United States, Japan, Germany, South Korea, Canada, France, Italy,
    the United Kingdom); it marks the others withheld, and the atlas shows none for them. Days of cover are the
    stock of a month over the oil demand of the same month, both from the same file: arithmetic on two published
    figures, labelled as such.
  - *No monthly series*: the file has none for LNG, none for refined-product or LPG production and trade
    (the production series end in 2014); the pages say so and the atlas estimates none.
  - *Reserves and refining*: the only reserves series of the file is coal; it has no proved reserves of crude oil
    or natural gas, and no refinery capacity, throughput or runs (the series with "refinery" in the name are a
    processing gain and LPG and ethane production). The search is repeated by a test, which fails the day the
    file holds them. The "Reserves" colouring therefore stays off for those two commodities.
  - *Production by country that EIA stopped publishing* is shown with its year and says that the series end:
    refined petroleum products and LPG production, 2014. Natural gas plant liquids (ethane, propane, butanes and
    heavier liquids recovered from gas) run to the latest year and are shown as their own table, "not LPG alone".
  - *United States LPG consumption*: EIA's tonnes have no United States value after 2021, and its world total in
    tonnes leaves the country out from 2022 (the sum of the countries equals it); the same series exist in thousand
    barrels per day for every year. The missing years are that figure converted at 11.60 barrels per tonne, the
    ratio of EIA's own United States series in both units (the same in every year from 1980 to 2019). The world
    total of such a year is EIA's own world series in barrels per day converted at the same ratio, when that agrees
    within 1% with EIA's tonnes plus the United States (it does for 2021 to 2025: 347.98 Mt in 2025 against 303.66 Mt
    in EIA's own tonnes, which leave the United States out); otherwise EIA's tonnes with the figure added, and only
    while EIA's total equals the sum of the other countries within 0.5% (a corrected file is not counted twice).
    The tonnes of 2021 (148 Mt against 43 Mt the year before, 3.4 barrels per tonne against 11.6) are replaced the
    same way. The United States row, the table, the key figure, the map legend, the CSV, the history and the
    country profile line all say "Atlas conversion"; 2020, 5% off the ratio, stands as published.
  - *Other tables from the file*: consumption of motor gasoline, distillate fuel oil, jet fuel and residual fuel
    oil by country (refined products), nuclear generating capacity (uranium), metallurgical coke production and
    trade (metallurgical coal), and in a note the world coal production by rank (the four ranks and metallurgical
    coal add up to EIA's world total).
  - *Metallurgical coal by pair of countries* (the "Main flows" block of the Metallurgical coal page). The customs group
    `coal` holds every kind of coal (HS 2701) and is not split, reduced or renamed. The block used to list that
    group for five exporters (Australia to Japan 108.97 Mt, Russia to China 95.07 Mt, Australia to China 83.82 Mt,
    Mongolia to China 82.91 Mt) and called it all coal; since November 2026 it lists metallurgical coal from the two
    exporters whose own statistics give it by destination, each row with its source, in the year of the customs data
    (2024): **Queensland** (Australia), the producers' sales to export of hard coking, semi-soft coking and PCI coal by
    destination as the file gives it (the sheet "Export by country and coal type"), summed from the four quarters of the workbook "Quarterly Coal Sales" of the Queensland
    Government (136.99 Mt to 31 countries in 2024; CC BY 4.0, credit and disclaimer in the page's note and in
    `NOTICE.md`); and the **United States**, the exports of rank "metallurgical" as declared to the Census Bureau, as
    EIA's bulk file COAL.zip publishes them in short tons, by destination country, converted at `TONNES_PER_SHORT_TON` (51.33 Mt to 34
    countries in 2024, public domain). The words by which the page and the footer of the block describe each source are those of its file's definition (`pipeline/cache/metcoal_meta.json`). A row is a destination of at least 1,000 t: 63 rows, 31 of Queensland and 32 of the United States (two of its 34 destinations are under 1,000 t). The United
    States rows carry their customs districts of loading. The rule that PCI (pulverised coal for injection) is
    metallurgical is the atlas's: the Queensland workbook has no such column, holds PCI inside semi-soft coking
    coal before 2022 and reports it apart from 2022, so only the sum of the three types is continuous across the
    change (136.4 Mt to the named destinations in 2022 against 141.9 Mt in 2021, whereas semi-soft coking alone falls from
    40.9 to 12.5 Mt); the cache keeps the coal types apart. EIA's file does not define the rank. The two exporters count differently from each other,
    from EIA International (the tables of the page: Australia 171.1 Mt and the United States 51.3 Mt in 2024) and
    from customs data, so the flows of the two are never added to one another, and the page prints no total of
    them. They are **not a part of the customs flows** of the Thermal coal page and are not subtracted from them: a
    destination of an exporter's statistics is not always the country where customs data record the coal (Queensland sells 1.66 Mt to Singapore against
    0.14 Mt of customs coal; 7 of its 31 pairs and 7 of the 32 United States pairs exceed the customs record of
    all coal), and customs coal less the exporter's metallurgical figure is not the exporter's thermal coal: for
    Australia to India customs data record 58.24 Mt of all coal, Queensland sold 35.42 Mt of metallurgical coal, and
    the difference, 22.82 Mt, is six times Australia's own figure for thermal coal to India in the Resources and
    Energy Quarterly of December 2025 (3.78 Mt in calendar 2024, table 41, principal markets by volume). The Queensland rows are 80% of EIA International's Australian figure (New
    South Wales has no destinations in the file) and the EIA rows 100% of its United States figure. Mongolia,
    Russia, Canada and Mozambique, which export metallurgical coal, have no source by destination among those the
    atlas has read, and no list of metallurgical coal holds their coal by pair. It is read in customs data, all types
    of coal together: Mongolia to China and pairs of Russia are among the twenty largest customs pairs that
    make the Main flows of the Thermal coal page (each row tagged "all coal"), and the customs lanes by sea of
    Russia, Canada and Mozambique are in the lane tables of both coal pages (Seaborne lanes, group "Coal (all
    types)"); Canada and Mozambique have no Main flows row, their pairs being smaller than the twentieth. The rows no longer open a lane page, because the lanes of the page are customs data for all coal and
    coke (a lane of the layer is a later piece of work). The cache is `pipeline/cache/metcoal_pairs.csv`,
    `metcoal_ports.csv` and `metcoal_meta.json`, written by `pipeline/trade/extract_metcoal.py` from the two files in
    `raw/` (checks that stop it: Queensland's country and port sheets equal to the tonne in 2022 to 2025; EIA's
    destinations and districts within 0.5% of its world row in every year kept, 2010 to 2025; a 2024 total more than 2%
    from the one the notes of the page were written for, which is a guard against a changed definition and not against a revision: a
    smaller difference is printed and written to the meta file), and read by `pipeline/trade/metcoal.py`, which raises for a year the cache does not hold. Both files are
    downloaded by hand and refreshed by hand (`docs/UPDATING.md`): no scheduled job reads them, and the page says the
    dates of the Queensland file ("Data through to 30 June 2026" and "Current as at October 2026") and of EIA's (1 October 2026).

## 11. Infrastructure layer

The mines, smelters, ports, storage hubs, fields, refineries, LNG terminals and pipelines of
`data/infrastructure/` are a hand-curated sample, not an inventory: each asset was picked because it
is large, well known or needed to read a flow, and an absent asset means nothing about whether it
exists. No script rebuilds the files. Capacity (nameplate) and output (a measured figure of a year)
are separate fields, each with its own year; a figure whose source gives no year is shown with the
year the page was read, as such ("Wikipedia · read 2026"), never as the year of the figure. The status of an asset is "operating" only when a dated page says it runs, and
"not stated" when no page read says so; it is never assumed. The rules, units and sources are in
[`pipeline/infrastructure/README.md`](pipeline/infrastructure/README.md).

Ports. Most ports that the hand-written freight routes name are assets (Boke, Guinea, stands for the river
terminals of a region and is none). Each port carries the code of the same place in the trade engine (`locode`), so a route
port, a lane port and the asset are one place: the route page links its ports to their pages, and a port's page
lists the routes that name it and the largest lanes that load or discharge there. The generated routes name the
ports of the trade engine, in its spellings ("Pusan", "Odessa"): the alias table of
`pipeline/infrastructure/route_assets.py` links them to the asset; a port of a generated route that is no asset
links to the largest lane through it of a commodity the route carries (a steel route does not open a coal lane),
and a port that is neither, or that has no such lane, stays plain text. Positions
come from the IMF PortWatch ports database (IMF terms of use; no vessel count or traffic figure is taken from it: the port traffic
of a port's page comes from the daily table, section 5), or,
for a place it does not list, from OpenStreetMap or Wikipedia; a database point stands for the whole port, so a port
of several terminals is marked "Approximate location", and only a single terminal is placed on its site. A port's
commodities rest on a page read (its own page, or an article named in its note) or on a route or lane of the atlas
that uses it for that cargo: a database that gives a position states no cargo. A throughput or capacity is entered
only from a page read; outside the United States, a terminal's capacity is the operator's or the page's figure, and
its `n` says so.

Largest class by the published limits (Atlas estimate). Where a page gives the limits of a port (the deepest
berth, or the largest ship by draught, length, beam or deadweight), `pipeline/infrastructure/port_limits.py`
derives the class of `pipeline/freight/vessel_classes.json` that each segment of the port (dry bulk, tankers, gas)
can take, with two rules that the page of the port shows with their basis. (1) By deadweight: the class whose size
band (`size.min` to `size.max`, in dwt) holds the port's deadweight limit; above the band of the largest class of the
segment, that class "or larger"; not above the smallest band, no class. Where bands overlap (Newcastlemax lies across
the Capesize and VLOC bands; Aframax and LR2 share one) the widest band stands for the class, so a nested class is
never chosen. (2) By dimensions: when the page gives a draught, a length or a beam, the largest class whose standard
vessel (`std`) is no larger in every one of those dimensions that both give; a class whose standard vessel has none of
them is not compared, and the note names it. A class not compared whose size lies between the class found and the
next larger class ruled out (Panamax between Ultramax and Kamsarmax) is named beside the class found ("Ultramax or
Panamax"), since nothing rules it out. When the two rules give the same class, or only one applies, the page
shows that class and its basis; when they differ it shows both with their basis ("By deadweight: VLOC. By the 14 m
draught: Ultramax.") and no single class. No class comes from a depth alone: a class needs a deadweight, a length or
a beam, and a channel or berth depth is shown as a limit ("Depth") that can only rule a class out. A limit stated
for one kind of berth (an oil berth) is compared for that segment only; only the page's maximum is a limit, never a
stated minimum; and where the page itself names the class the berths take ("for Capesize ships"), the class is that
statement. The result is never presented as the port's own statement: a larger ship may call part-laden, with the
tide or at another berth.

World Port Index (port panel). The page of a port carries a block "World Port Index" when the atlas matched the port to
a row of Publication 150 of the US National Geospatial-Intelligence Agency (NGA, as the page names it). The block prints the
publication's own figures, in its own words and under its own source ("World Port Index (Pub. 150), NGA", with a link,
and the month the atlas read the file): the depth of the channel, of the anchorage, of the cargo pier and of the oil
terminal, and of the LNG terminal where there is one; the largest vessel the publication states for the port (length,
beam, draught) and, where it states one, for its offshore berths; the tidal range; the class and type of harbour; and
whether pilotage is compulsory and the tide restricts the entrance. A figure the file does not state has no row. These are
not Atlas estimates and carry no such label. A person took the file (a CSV of 3,807 rows and 109 columns) on 24 November 2026 from the
Internet Archive's copy, captured on 29 September 2026, of the publisher's download address, because the publisher's site was
in maintenance; no script downloads it and no scheduled job reads it. The atlas keeps 23 of the 109
columns, for the ports that match, in `pipeline/cache/wpi_ports.csv`, and the file the site reads,
`data/infrastructure/wpi.json`, is built from that cache alone. The file holds neither an edition nor a date inside it: the copy read was
captured on 29 September 2026, and the page's source line says so ("Internet Archive copy of 29 Sep 2026"), which is not the
date of the figures (Assumption A6). The terms of use of the file are not settled, and no terms of the Internet Archive's own
for it were read (`NOTICE.md`): the block gives the publication's name, the entry's name and number and a link, offers no
download of the figures, and is a choice made without the owner, listed in `PROGRESS.md`.

The match. Each of the 190 ports of the atlas is compared with the rows of the file, and a match is sure in two cases.
By code: exactly one row carries the port's UN/LOCODE, the code's country is the port's, the row lies within 15 km of the
atlas point, and its name shares a form with the atlas name or it lies within 10 km. By name: no row carries the code and
exactly one row of the same country has a main or alternate name equal to the atlas name within 15 km. Either way the
match is sure only if no other row of the same country lies nearer to the atlas point than the matched row by more than
2 km: a port of several terminals, a city harbour and its terminal rows, would otherwise take the figures of the wrong
entry. Doubtful, and never shown: a code that several rows share, a row of another country, a row too far, a name that
several rows carry or that is found between 15 and 40 km away, a nearer row, a match by name when another row of the same
country carries an equal name within 60 km (the atlas's Forcados terminal is an offshore crude terminal; the file has a river
port Forcados 9.1 km away and a row Forcados Oil Terminal 27.5 km away, which carry the same name once its stop words are
dropped, so the row found by name may be either and neither is shown), or a row within 10 km with no code or name in common. The distances are constants of `pipeline/infrastructure/extract_wpi.py`; the meta file
`pipeline/cache/wpi_meta.json` writes them with the counts, the reason of every doubtful port and the farthest match kept
and the nearest refused for its distance, which is how the radius by code was chosen. Of the 190 ports, 138 have an entry
(115 by code, 18 by name and 5 by review), 36 are doubtful and 16 have no match; the 52 without an entry have no block
and nothing in its place. Among the doubtful, 7 ports have another row of their country nearer to the atlas point than the
matched one. A short table of the extractor, written by a person who opened the two rows, promotes a doubtful match or
holds a sure one, each with a sentence that says why (Assumption A7); nothing is promoted without it. A sure match is the
same place, not necessarily the same scope of berths, which is why the block names the entry (its name and number).

Depths. The publication does not give a depth in metres: it gives a band. Its own words, from the explanation of the data
columns of the twenty-sixth edition (2017): "Depth information is generalized into 5-foot units, with the equivalents in
meters" and "Depths refer to chart datum"; a code "means a least depth of 31 feet (9.5 meters) or greater, but not as
great as 36 feet (11.0 meters)". What each depth is: for the channel, "The controlling depth of the principal or deepest
channel at chart datum is given"; for the anchorage, "the least depth in the best or principal anchorage"; for the cargo
pier, "The greatest depth at chart datum alongside the respective wharf/pier is given", the deepest pier where there are
several; for the oil terminal, "The greatest depth at chart datum will be shown"; for the LNG terminal, the
same words ("The greatest depth at chart datum will be shown": sub-item e of item 11, whose lead sentence names the four
other depths only, and the printed table of that edition has no LNG column). The LNG depths of the file are not on the
key's grid (one of the 22 the file gives sits on a floor of the key, against 88 to 92 in a hundred of each of the four other
depths): the page prints them as the file gives them, never as a band. For the four depths, the page prints a
value that is the lower edge of a band of the key as that band ("14.0 to 15.2 m"), the top band, which has no upper edge,
as "23.2 m or more", and a value off the edges as it is given ("16.1 m"); it never prints a zero. The sixteen bands are
typed once, in `web/src/lib/wpi.ts`, with the address of the archived copy of the publication they were read in and the
date. That sentence on chart datum belongs here, not on the page.

Assumptions of the block. The atlas names them as such; none is a figure of a source.
- **A1.** A value of 0.0 in the file means "not stated", never a measured zero; the key's lowest band (0 to 1.5 m) has
  the same look, so a depth of that band is never printed either.
- **A2.** The key read is the twenty-sixth edition's (2017), an archived copy of the publication. The edition of the CSV
  is not stated. Most of its depths sit on the lower edges of that key, with a heap on the top band, which is evidence
  that it is the same key and not proof (`web/scripts/wpi.test.mjs` counts them); a value off the edges is a newer,
  finer figure.
- **A3.** The maximum vessel columns are limits the publication states for a berth or the port, on a basis and a date
  that the file does not give. They are printed as stated and never turned into a class (see below).
- **A4.** A match by code or by name is the same place, not the same scope: the atlas port may be a group of terminals
  and the entry one harbour or one terminal. The entry's own name is printed so that the difference stays visible.
- **A5.** An oil terminal depth above 100 m is the water depth of an offshore field terminal. No ceiling is applied to
  the figures; none of the published entries has such a depth.
- **A6.** The day the Internet Archive captured the address the file is a copy of stands for the date, since the file has none;
  for a file taken from the publisher itself it would be the month the atlas read it ("read November 2026"). When an edition is
  typed in the extractor, the page prints it in the name of the source.
- **A7.** The review table is a person's judgment, recorded with a reason; it is not computed.

A plausibility check on the maximum vessel. A port's maximum vessel, or its offshore one, is left out when its beam is
more than 40% of its length or more than 70 m, when a beam is given with no length to compare it with, or when its draught
is more than 25% of its length: it holds back the maximum vessel of 7 ports, listed with the group and the reason in the meta
file (`held_vessel`), and their depths stay; a port's berth figures and its offshore figures are judged apart (Tema's offshore
berths, a 275 m length with a 275 m draught, are held and its berth figures stay). The 25% is read from the file: of the
846 groups of its rows that give a length and a draught, the median is 0.049 of the length and the largest is 0.182 apart from
Tema's 1.00 (the meta file's `rule_basis` has them). It is a check on the publication's figures, not an estimate: the atlas
does not correct a figure that passes it, and some figures that pass it disagree with others of the same entry. In 4 ports a
maximum vessel's draught is above the deepest depth printed for the port plus its tidal range (the upper edge of a band
counts as printed; the top band has none), and the page shows them as the publication gives them.

Two sources side by side. A port that also has "Limits" (the page the atlas cites, Wikipedia) shows the two blocks one
under the other, each under its own source, never merged, averaged or reconciled, and with no sentence about which is
right. They differ because they measure different things and sometimes different places. The page of Port Hedland gives
a draft depth of 19.8 m (an infobox figure); the file gives a controlling channel depth, the band 14.0 to 15.2 m, and
the draught of the largest vessel its entry states. The limits of Rotterdam are those of an ore quay of the Maasvlakte;
the file's row named Rotterdam is the city harbour, far from the atlas point, and Europoort and Hoek van Holland are
other rows nearer to it, so the atlas shows no entry for Rotterdam. A difference of measure or of scope is not a
contradiction between two sources.

No class from this publication. The "Largest class" line under "Limits" is derived from the page's limits only, and
no class is derived from the World Port Index in this release: its depths are bands, and a depth alone gives no class;
its maximum vessel figures are limits of unknown basis, and applying the rule above to them gave classes that
contradict the page's for most of the ports that have both. Whether to derive one is a question for the owner, in `PROGRESS.md`.

Storage hubs. Cushing (Oklahoma) and Mont Belvieu (Texas), the delivery points of the atlas's WTI and propane
prices, are assets of their own type. Cushing's figure is the EIA's working storage capacity of 31 March 2024, in
million barrels (`Mb`, a stock: it is never ranked with a flow).

## 12. Companies layer

The company lists (`pipeline/companies/*.json`, published by `pipeline/companies/build_companies.py`) name the main
producers, processors and traders of each commodity and the main shipping companies by segment. They are a
hand-curated selection, not a ranking: a company absent from a list says nothing about its size. The rules, the
vocabulary and the review routine are in [`pipeline/companies/README.md`](pipeline/companies/README.md).

- **Figures.** A company carries at most one figure per commodity, from its own report or filing (or a page that
  states it), with the year it refers to and the page. The atlas computes nothing: the only arithmetic is a change
  of unit, written in the figure's note with the stated number and the factor. Gas volumes in cubic feet are
  converted at 0.0283168 cubic metres per cubic foot and, for a daily rate, 365 days a year; a yearly volume in
  barrels is divided by 365 days to give barrels a day; uranium in pounds of U3O8 at 0.45359 kg per pound and
  0.848 kg of uranium per kg of U3O8. A volume that covers several commodities (crude oil and products together, a
  segment's grain merchandising) is not a figure: it is written in the line of text with what it covers.
- **Order.** Within a group, rows whose figures count the same thing in the same unit (liquids production in kb/d,
  LNG sold in Mt, a fleet in ships) form a block ordered by value; each other kind of figure forms its own block;
  rows without a figure follow in the order of the file. Bases differ inside a block (attributable, 100%, a
  company's share), and each row says which; fleets are blocked by their basis too (owned, chartered-in, leased,
  managed, with ships on order), and a fleet of several kinds of ship is written in the text, not ranked.
- **Ownership and sanctions.** Ownership is the page's statement: state-owned, state-controlled and listed,
  listed, private or cooperative. A parent's share is the share a page states (the entry's Wikipedia article, or
  the page linked for it), with its date when the page dates it. A sanction mark names the authority and the month
  of the designation in the notice or list read ("OFAC designation of October 2020", which may not be the first)
  and links the authority's own notice or list (US Treasury OFAC, the UK sanctions list on GOV.UK); a lifted
  sanction is removed.
- **Years.** The year shown with a fact is the year of the fact. The month a page was read is shown apart ("read in
  November 2026") and is never the year of a fact.
- **Company and assets.** A company's row lists the assets of the infrastructure layer whose operator field names
  it, as operator or as an owner with a share (the name, a name in brackets, or the name without "Energy",
  "Group"…). A former owner does not count: a name preceded in the same clause by "sold by", "ex-", "formerly",
  "previously" or "bought (from)" ("Aster…; sold by Shell in April 2025" is not a Shell asset), nor a name that
  begins another listed company's ("Gazprom" in "Gazprom Neft"). The operator field is not otherwise split.
- **Country pages and search.** A country page lists the companies headquartered there, the shipping companies with
  their segment. The search finds a company by its name and opens the commodity page of its first commodity, or the
  vessel class page of its first class, with the companies unfolded on its row.

## 13. Reports, releases, review and coverage

- **Reports.** The "Report an error" button in the header of each page, and the link of the same name in the About
  window, open the new-issue form of the repository (`.github/ISSUE_TEMPLATE/report-an-error.yml`). The browser fills
  it in with the address of the page, what is selected on it (its kind and id, as the address writes them), the
  page's heading and the release and build running; nothing is sent to GitHub before the click and the site stores
  nothing. A GitHub account is needed to submit, which is GitHub's rule, and a report is a public issue. The form
  puts no label on the issue: the address never carries one, because GitHub refuses the address of a visitor who may
  not label, and the label `data-update` is used only by the update jobs for their own issues. The atlas states no
  time of answer; the owner of the repository closes the reports. The address is capped at 2,000 characters, an
  Atlas assumption (GitHub gives no figure): past it, the page address keeps only the keys that define the page
  (family, commodity, colouring, year, selection, company, route finder) and is cut if that is still too long.

- **Coverage.** `data/coverage.json` lists, for every commodity page, which of eleven blocks it has: production, reserves,
  consumption, trade, sea lanes, routes, price, assets, companies, and, for the pages of the families that have them,
  the monthly series (energy) and the crop balance (softs). A block a family cannot have is not a cell of its pages and
  is not counted. A block is present when the files hold at least one row, lane, route, series, asset or company for
  the page: present means there is something, not that it is complete. The routes block counts the corridors that the
  atlas generates from customs pairs as well as the benchmark routes and those written by hand, and says so. The
  file is read from the files of `data/` only (never from the raw downloads), carries the number of the release it was
  built at and no time of day, and is rebuilt by the annual update after the pages. A cell that is not present is one
  of three states. **Not applicable**: the nature of the commodity rules the block out (a crop is grown again every year,
  so it has no reserves); the reason is typed by hand, once, with the sentence of the repository it rests on, and a test
  finds that sentence in its file. **Not available for free**: a publisher's own page, read in a stated month, says
  the series is not offered free, and the alternatives looked at are named with why each fails; a cell without both is
  not given this state. **Missing**: everything else, including a block that "no free file loaded by the atlas yet"
  gives, which is the atlas's gap and not a refusal of a publisher; the missing cells are the work list, largest
  seaborne tonnage first. A reason never hides a block: when the data hold a block that carries a typed reason, the data
  win, the cell is present and the build warns that the reason is stale. A page does not lose a block it has had: the
  blocks present at the last accepted state are listed in a floor file, a rebuild that takes one from a page is refused
  by the update guard, which discards the whole update of that run (a stale reason or a failed coverage step stops
  nothing), and a real loss is accepted by hand (docs/UPDATING.md). The floor is raised by a command and
  lowered by a hand edit; no job changes either hand-typed table.
