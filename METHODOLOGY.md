# Methodology

How the atlas turns public statistics into flows, lanes, routes and shares. Figures computed by
the atlas (rather than copied from a publisher) are labelled **"Atlas estimate"** in the interface
and carry the source id `atlas`; the note of each says how it was computed. A rule that the atlas
sets by judgement (a typical port, a mode list, a routing threshold) is an **Atlas assumption**, and
is called one where it is shown. The figures below are those of the build from CEPII BACI V202601
(latest year 2024).

## 1. Bilateral trade flows

- **Source**: CEPII BACI, HS 1992 version (the database covers 1995–2024), which reconciles
  exporter and importer declarations from UN Comtrade. Quantities are metric tonnes, values
  thousand USD. The atlas's cache holds the years 2002 to 2024
  (`pipeline/cache/baci_flows.csv.gz`, written by `pipeline/trade/extract_baci.py`, rows below
  both 1,000 t and USD 1 million dropped); lanes and their history start in 2005. The 2.4 GB database is
  not in the repository: a new version is downloaded when CEPII publishes one, normally by hand
  (see the README).
- **Commodity groups**: HS six-digit codes are grouped per commodity in
  `pipeline/trade/hs_map.py` (e.g. coal = 2701.11 + 2701.12 + 2701.19).
- **Known limits of customs data**
  - HS codes do not separate thermal from metallurgical coal; the coal lanes cover both.
    Metallurgical coal production and trade by country come from EIA, which does split them.
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
     tonnage and is flagged `no-value` (3 rows).
  4. **Moderate inconsistencies** (unit value below 1/3 or above 3× the reference, flows over USD 50
     million) are re-estimated only for homogeneous goods (crude, products, LNG, LPG, grains,
     oilseeds, vegetable oils, softs, fertilisers). Ore and concentrate groups keep the reported
     tonnage, because their grades range from about USD 40/t (laterite nickel ore) to over
     USD 2,000/t (sulphide concentrate).
  5. **Known misclassifications** are dropped. Example: Israeli pipeline gas to Egypt and Jordan
     declared as LNG (Israel has no liquefaction plant).
  6. **Qatari LPG in 2021 and 2023** (`DROP_NEW_PAIRS`). Customs data give Qatar about 10 Mt of LPG
     exports a year from 2018 to 2024, except in 2021 and 2023, when pairs that have no LPG in either
     neighbouring year add 29.0 Mt (19 rows, reported tonnage) and 26.5 Mt (12 rows, 11 of them
     with the tonnage estimated from value). Those rows are dropped (owner's decision, 22 November
     2026) and listed in `pipeline/commodities/QA.md`: Qatar's LPG exports then read 10.1 Mt in both
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
- **Tonnage estimated from value is an Atlas estimate.** Every row whose tonnage rules 2, 3, 4, 7 or
  8 re-estimate carries a note that starts with "Atlas estimate" and gives the method, the declared
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
  more is estimated is itself labelled "Atlas estimate" (with the source id `atlas`). In 2024, 168
  rows and 74.8 Mt of the lane groups (0.82% of their tonnage) are estimated; the largest are crude
  oil United Arab Emirates → Thailand (24.5 Mt), wheat Russia → Egypt (11.1 Mt) and copper
  concentrate Chile → China (8.24 Mt). The share of each lane group's 2024 seaborne tonnes that is
  estimated is the field `est` of its lane file: 33.0% for copper concentrate, 8.0% for wheat, 1.8%
  for crude oil, 1.3% for LPG, under 1% for every other group.
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
  hubs (refined products of the Netherlands, Belgium and Singapore; Dutch crude). 25 are active for
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
   metals, the mixed pairs hold 310.2 Mt on 63 pairs in 2024. Belarus → China potash is not a mixed
   pair: package L1 had made it one, and the review of that package (fixed in package FL1) returned it
   to the seaborne pairs, because the pages bound the rail share: Kommersant, reported by Reform.news
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
alumina, manganese, copper, nickel and zinc ores, spodumene concentrate); grain (wheat, corn,
soybeans, soybean meal, rice, sugar, rapeseed); vegetable oils (soybean and palm oil); fertilisers
(potash, phosphate rock, DAP, urea); metals (steel, refined copper, aluminium, nickel intermediates,
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

**2024 by mode** (42 lane groups, 25,847 pairs, 9,154.1 Mt): sea 7,752.5 Mt (18,992 pairs), sea via a
transit port 170.8 Mt (2,182 pairs), sea and overland 310.2 Mt (63 pairs), land 920.6 Mt (4,610
pairs). Seaborne: 7,923.3 Mt. (34 groups, 23,853 pairs and 9,140.4 Mt before the eight groups of
minor metals were added; Belarusian potash to China, 2.9 Mt, is sea via a transit port.)

**Sea via a transit port.** The foreign port of a landlocked country is gateway data
(`TRANSIT` in `pipeline/freight/gateways/energy.py`), one sourced row per country and cargo (a customs
group or a cargo family) or a default row. 26 countries have one. Before package L1, 23 had one: Austria and Czechia (crude: Trieste, Transalpine
Pipeline), Hungary and Serbia (crude: Omišalj, Adria pipeline), Kazakhstan (crude: CPC terminal,
Novorossiysk, a port in Russia), Azerbaijan (crude: Ceyhan, BTC pipeline), Chad (crude: Kribi),
South Sudan (crude: Port Sudan), Czechia (other cargo: Hamburg), Switzerland (Rotterdam), Uganda and
Rwanda (Mombasa), Zambia, Malawi, Burundi and DR Congo (Dar es Salaam), Zimbabwe (Beira), Ethiopia
(Djibouti), Burkina Faso and Mali (Abidjan), Niger (Cotonou), Nepal and Bhutan (Kolkata), and
Bosnia and Herzegovina, whose short coast has no port of its own (Ploče). Each of these rows cites a
Wikipedia article. Package L1 (pages read on 23 November 2026) gave rows to three more countries,
Belarus, Paraguay and Botswana, and new cargo rows to four that had one, Austria, Hungary, Serbia and
Kazakhstan: Belarus (fertilisers: St Petersburg, for the Bronka and St Petersburg terminals, from an
OSW commentary of November 2024 and a Reform.news report of Kommersant's 2025 figures), Kazakhstan
(coal: from a Kpler note of February 2025), Paraguay (soy and corn: from a Bolsa de Comercio de
Rosario note of April 2017 on the grain coming down the Paraná–Paraguay waterway in transit in
2016), Austria and Hungary (other cargo: Koper, Port of Koper article), Serbia (other cargo:
Constanța, Port of Constanța article, Danube traffic) and Botswana (Walvis Bay, Walvis Bay article).
A row holds only what its page says (review of package L1, fixed in package FL1): the Kazakh coal row
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
2024, 47.7 Mt before package L1) stays in the seaborne
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
    steel); they are in `CAP`. A group under 1 Mt of seaborne trade a year (unwrought tin, tin concentrate,
    cobalt, lithium chemicals, rare earths) is published in kt with one decimal (the lane file's `unit`),
    as its commodity page prints it, and the lane page, the lane table, the Route finder and the
    chokepoint lists print it in kt too; its pairs file's seaborne total is the sum of its published rows.
    Where figures of several groups are compared or summed (the width of the lanes on the map, the
    lanes of a country, a commodity with groups in both units), they are taken in Mt.
    No lane from the wrong coast (review of package L1, fixed in FL1): many minor-metal ports have no page
    for the cargo, so for these eight groups a pair whose route is more than 1.8 times the great-circle
    distance of its two ports is not routed when an end's port has no page that names the cargo and
    either another port of that country in the atlas's tables reaches the other end in under 60% of the
    distance (Russian lead concentrate and cobalt for China and Korea from Novorossiysk, Saudi lead for
    the Emirates from Jeddah, Spanish and French metal for northern Europe from Valencia and Fos), or the
    port is only the country's nearest seaport (Turkish lead concentrate for China and Korea from
    Samsun): 0.6 Mt of seaborne pairs in 2024, and the 0.37 Mt mixed Russia → China lead concentrate.
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
  - 2024: 2,617 main seaborne lanes, 35 mixed lanes and 271 history lanes over 42 groups (2,400, 35
    and 182 over 34 groups before the minor metals); the main lanes carry 85.5% of 2024 seaborne
    tonnes. The share per group is the `coverage` of each lane file: 90% or more for iron ore, coal,
    bauxite, LNG, soybeans, manganese, LPG, corn and cobalt, among others; lowest for unwrought tin
    (56.9%), refined products (60.1%), unwrought zinc (62.8%), unwrought lead (64.3%), aluminium
    (66.1%), cocoa (66.5%), steel (68.2%) and coffee (69.9%); potash reads 81.2% (73.7% before the
    Belarusian transit row). Where trade is spread over thousands of pairs, the pairs table answers.
- **The pairs table** (`data/freight/pairs/<group>.json`) holds every pair of the latest year that
  the customs extract keeps (1,000 t or USD 1 million and more), whatever its mode: 25,847 pairs in
  2024. Each row gives the tonnage (kt: whole above 1 Mt, one decimal below), the mode, the two
  ports, the distance, the primary vessel class, the passages it has to cross and those it may
  cross (bit masks over the file's list of gates), and flags: tonnage estimated from value, caveat,
  main lane, check finding. A seaborne pair "not drawn on the map" is one without a main lane
  (1,150.3 Mt in 2024); a pair "not routed" has no route at all (48.5 Mt in 2024: 31.4 Mt because a
  landlocked end has no sourced transit port, 15.2 Mt because there is no sea route or it is under
  50 nm, mostly Malaysian refined products to Singapore, 1.3 Mt because an end has no gateway, 0.6 Mt
  of minor metals from the wrong coast; 64.2 Mt, 47.7 Mt of it for want of a transit port, before
  package L1).
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
  - "general port of the country";
  - "port used before, no page read" (the earlier table; shown as "no source page yet");
  - "nearest seaport" (also shown as "no source page yet").

  Share of 2024 pair-end tonnage as published in the pairs files (each seaborne pair counted at its
  two ends, 15,847 Mt; a port keeps the weakest basis of its uses in the file, for each role, and a
  transit port is one more port): page names the cargo 69.7%, port used before 22.4%, general port
  4.1%, nearest seaport 2.2%, other direction 1.1%, no port (not routed) 0.6% (after package FL1; 0.8%
  had no port before package L1). Most rows cite a Wikipedia article. The United States crude and
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
  Central American isthmus by the ocean of the other end. A rule that needs a product distinction
  that customs data do not make is not written (HS codes do not separate coking from thermal coal).
- **Coast options**. Where neither a single gateway nor a rule decides, a pair keeps up to three
  options per end. The main option is the principal gateway, not the shortest route ("nearest
  coast" would send every US soybean cargo for China to the Pacific Northwest); the others are
  listed with their distances ("9,251 nm from New Orleans, or 4,352 nm from Kalama"), with no
  weight. No measured split is loaded (`pipeline/freight/splits/` is empty). Freight zones: 36, in
  `data/freight/zones.json`.
- **Geometry**: shortest sea path on Eurostat's SeaRoute maritime network, using the `searoute`
  package (version pinned at 1.6.0). Port coordinates come from the UN/LOCODE list bundled with the
  package, with terminals added by hand from their pages. Always avoided: the Northwest Passage,
  and the network's lane along 50 S that no cargo ship uses between South America and Asia (every
  edge with a point south of 42 S between 55 W and 140 E). Two passages are closed to every route:
  the Johor Strait, blocked by the Johor–Singapore Causeway, and the Kanmon Strait between Honshu
  and Kyushu (fairway 12 m deep in 2016, Japanese Wikipedia; too shallow for the bulk carriers and
  tankers the atlas routes).
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
- **Generated corridors** (`pipeline/freight/generated_routes.py`, called by `build_freight.py`). The 103 hand-written
  routes name 45.1% of the 7,923 Mt of 2024 seaborne tonnes of the 42 customs groups. For the rest, the pairs table
  is grouped, for each group, into corridors: the freight zone of the typical loading port and the zone of the typical
  discharge port of each routed seaborne pair (a port with no zone in the pairs file takes the zone of the nearest port
  that has one, the same country first: only the name of a corridor depends on it). The corridors that no hand-written
  corridor names are ranked by the tonnes outside the hand-written corridors, and the largest become routes until the
  group reaches the target of 70% of its seaborne tonnes (hand-written routes counted), or has 12 generated routes. A
  corridor needs at least 0.5 Mt and 2% of its group outside the hand-written corridors, and at least half of its own
  tonnes outside them. What the zone-to-zone corridors leave out is grouped again with the importing zones merged into
  regions (Europe, East Asia, and so on: an Atlas grouping listed in the code). Unrouted pairs (no gateway, no sea
  route) are in no corridor. The cap on the whole atlas is 120 generated routes: the map draws every route, and a larger
  number made the world view unreadable even with the generated lines drawn thinner (about 120 more lines on top of the
  hand-written ones, 133 in November 2026). When the lists exceed it, the first corridor of each group that the audit's entries on named routes name is
  kept first (crude oil, iron ore, coal, refined products, LNG, steel, manganese, alumina, sugar, rice, rapeseed,
  coffee, cocoa, cotton, phosphate rock, DAP, urea, soybean meal, palm oil, corn, wheat, potash, soybeans), then the
  corridors are taken by their tonnes across groups, each group's in its own order, so that no corridor is left out
  for a smaller one of another group (package FL1; before, the first corridor of every group came first, and three
  corridors of 1.1 to 1.5 Mt gave way to corridors of 0.5 Mt of the minor metals). The result for 2024 is 120
  generated routes over 42 groups beside 133 hand-written ones (253 routes), and 66.2% of the seaborne tonnes named (all
  groups; 45.5% by the hand-written routes alone): ten of the 42 groups reach 70% (iron
  ore, coal, crude oil, LPG, corn, soybeans, bauxite, ferro-nickel, nickel ore and spodumene); the others stay short of
  it, among them steel (45%) and refined products (53%), whose trade is spread over thousands of small pairs, and the
  groups whose corridors are all smaller than those kept (aluminium, refined copper, zinc concentrate, the minor
  metals: no generated route). `pipeline/freight/QA_routes.md`, written at each build, gives each
  group with its coverage, its reason when it is under the target, and the corridors the cap left out.

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
  port time, no canal wait, no ballast leg; the route page shows the duration of the definition beside it when the
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
  size of the MR2 benchmark cargoes (37,000 to 40,000 t) and more than the largest chemical tanker of the Wikipedia
  scale (35,000 dwt), which is why the MR comes first.

These are labelled "typical" in the interface (lane and route tooltips, the route list, the lane table and its CSV
column `typical_vessel_class`); a benchmark's class is the class of its definition and is not called typical. They are not measured shares of each class: no free source measures how
a trade splits between vessel classes (that would take ship-by-ship tracking, which the atlas does not use), so the
class of a lane, a country pair or a route is a rule, not a measurement.

Class pages. Each size band names the page that supports it and the year of that page (Wikipedia's ship-size
articles, the Wilhelmsen page of LPG carrier sizes); where the Atlas sets a bound itself, so that the bands of one
segment neither overlap nor leave a gap, the band is labelled "Atlas convention" and its note says which page gives
what. Classes defined by a port or a cargo (Newcastlemax, Kamsarmax, LR2, chemical tanker) sit inside or beside the
size steps on purpose; large gas carriers (50,000 to 70,000 cbm) are left out because no lane rule uses them. The
typical size is a page's figure where one is given (a Baltic Exchange reference ship, the Veson page of Baltic
definitions, a Wikipedia article: Newcastlemax takes the article's 185,000 dwt, Panamax the Baltic Panamax 74 of
74,000 dwt), else an Atlas convention, labelled so. The standard vessel gives the figures of the Baltic Exchange's
reference ship of its timecharter routes (dry bulk), stated as facts in the atlas's words with a link to the page (the
Baltic Exchange's site terms restrict copying; see the `baltic` entry of DATA_SOURCES.md), or, for a class without
one, the typical ship of its Wikipedia article. Laden days use the assumed laden service speed of the class, not the
standard vessel's speed. A class page lists the routes of its class, ended benchmarks last, then, under "Also served
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
    that the page prints (after the PortWatch cap below) is at least 2% of the group or 1 Mt: 490
    entries over 20 passages in 2024 (Hormuz: 20 groups).
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
    in 2024). Where the "at least" tonnage of a type is itself above PortWatch's volume of the year,
    the shares of that type say so; for Suez and Bab el-Mandeb in 2024 this is because the atlas
    routes cargo on the normal itinerary while most ships avoided the Red Sea (the note quotes the
    atlas's Red Sea alert). From 85% of that volume (`PW_NEAR` in `build_freight.py`), the shares of
    the type say how close the "at least" tonnage is to it, since the atlas's groups are not all the
    cargo of those ships (Panama, tankers, 2024: 97%, 104 Mt against 107 Mt; the assumed ports or
    routes may overstate it). Both figures are estimates, and the note names both ("IMF PortWatch,
    data adapted").
  - **Without the raw PortWatch rows** (the scheduled job has none), the volumes by vessel type are
    read from the tracked weekly series (Mt a day times the days of each week inside the year)
    instead of the daily rows that the committed files come from. For the 20 passages that carry an
    estimate the two readings differ by under 0.5% in 2024 (largest: Makassar tankers, 21.2 against
    21.1 Mt), so such a build can move a capped figure or a K9 reference by under 1 Mt (Hormuz crude
    oil "up to": 601.4 or 601.7 Mt).
  - **Check K9** writes, for every passage with a counter, "at least" and "up to" by vessel type
    beside PortWatch's volume of the same year and of its best full year since 2019 (table in
    `QA.md`). A passage is flagged when "at least" is above 110% of the best year (the assumed ports
    or routes probably overstate it) or above the same year's volume. The Danish Straits are not
    compared: PortWatch counts the Oresund only. The check is a report; it never stops a build.
  - **Sunda**: the routing network sends little traffic through the Sunda Strait by itself, so its
    "at least" figure is a floor of the model (1.9 Mt of all groups in 2024: 1.63 Mt of dry bulk, 0.13
    of tankers and 0.13 of container and general cargo, against 443 Mt of all ships in PortWatch; the
    table of `QA.md` rounds each type to 0.1 Mt), not a statement about traffic; its "up to" figures carry the cargo that may
    use it.
  - **Published figures first**: where EIA publishes a flow for the passage (oil through Hormuz,
    Malacca, Suez and others), it is the headline and the atlas's range is shown below it. `QA.md`
    gives the ratio of the two for crude oil, at 7.33 barrels per tonne: 0.70 for Hormuz and Malacca
    in 2024, 1.24 for Suez and 1.37 for Bab el-Mandeb (where the atlas keeps the normal itinerary).
  - 2024 examples: Hormuz crude oil at least 27.2% (509 Mt) and up to 32.1% (601 Mt, capped; Saudi
    crude for westbound buyers and Emirati crude may load outside the strait); Hormuz LPG 32.3%;
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
  table of the commodity file, whichever package added it. The section of an extra table is the last
  word of its key (`coke-production`, `motor-gasoline-consumption`, `fe-reserves`, `760110-exports`;
  `stocks` gives the ending stocks of USDA PSD, `nuclear-capacity` the capacity of EIA), its line is
  named from the table's title, and a customs table (CEPII BACI) gives the line the USD value of its own
  row. A table of part of the world (the EU member states) says so on the line, and a table of an old
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
  Comtrade Data Use" (read 23 November 2026), which allows internal use only and no re-dissemination
  without UNSD's permission. A heading is therefore named, with its code, from the six-digit
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
  month.
- Daily prices: EIA spot series (Brent, WTI, Henry Hub, New York Harbor gasoline, ULSD and heating
  oil, US Gulf jet fuel, Mont Belvieu propane).
- Freight (the "Freight" family of the price drawer and the board): no freight rate is shown, because
  none is both free and republishable. Three indicators are, each taken from its publisher and each
  labelled for what it is (`pipeline/prices/freight_indicators.py`):
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
  none). A series that stops advancing raises the "late series" failure of its source.
- Freight rates that are not stored. Baltic Exchange, Shanghai Shipping Exchange, Clarksons, Platts,
  Argus and Ship & Bunker values are proprietary. The USDA Agricultural Marketing Service publishes
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
  Every route page says that Baltic assessments are proprietary and links to the Baltic Exchange.
- Annual prices: USGS Mineral Commodity Summaries 2026, rows "Price" of the Salient Statistics
  (lithium carbonate, manganese ore CIF China, rare-earth oxides, bauxite and alumina "average unit
  value of imports, free alongside ship (f.a.s.)", cobalt, palladium, rhodium): one value a year,
  2021 to 2025, in the unit and with the basis the file states, in its own words; the last year is
  USGS's own estimate and is marked as such. The commodity page shows such a value as "annual average
  2025", with the decimals the file gives (9,000, not 9,000.00), and its change on the previous year;
  it is never presented as a current price. Monthly series for
  these commodities exist in the IMF Primary Commodity Prices (in other forms: lithium metal,
  electrolytic manganese, rare-earth carbonate); they are not used, because the terms of use for
  scripted downloads are not confirmed.
- Real prices: the annual workbook of the Pink Sheet (sheet "Annual Prices (Real)", constant 2010 US
  dollars, deflated by the Manufactures Unit Value (MUV) index, column "MUV Index"; the "Definitions"
  sheet gives the deflator). They are annual averages from 1960, shown by the "Real prices" switch of
  the price drawer for the series that have one (the Pink Sheet series, and Brent, WTI and Henry Hub
  daily through their monthly benchmark). No monthly real price is built: that would need a consumer
  price index that is not among the downloaded files.
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
  keeps raising its alert. The annual job rebuilds the prices after a new USGS edition. On a price
  chart an event that names commodities is shown when one of them is charted, or when an alert that covers
  one points to it, and an event that names none is always shown (the rule of the timeline). `web/scripts/validate-data.mjs` checks that the series files agree with the index.
- Baltic Exchange freight indices are proprietary and are not shown.

## 8. Discrepancies

When sources disagree (for example USGS and EIA, or USDA PSD and customs data), the official or
primary source is shown and the difference is noted in the commodity file's `discrepancies` field.

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
  trade 428 Mt in 2025 and 406 Mt in 2024; IGU World LNG Report 2025: 411.24 Mt in 2024), with
  publisher and year beside it. The country tables are customs tonnage (371.32 Mt in 2024), below
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
    aluminium, refined copper, zinc, lead, tin, alumina) is flagged by check K13
    (`pipeline/trade/checks.py`) and worded as a hypothesis through the caveat registry
    (`caveats.py`), with the metal's Pink Sheet price beside it where the repository has one.
    Unwrought aluminium is shown by code, HS 760110 (not alloyed) and HS 760120 (alloys).
  - **Iron content** of iron ore (production and reserves) is the USGS table as published.
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
  Association (world crude steel production, 1,849.4 Mt in 2025), the World Gold Council (world mine
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

## 11. Infrastructure layer

The mines, smelters, ports, storage hubs, fields, refineries, LNG terminals and pipelines of
`data/infrastructure/` are a hand-curated sample, not an inventory: each asset was picked because it
is large, well known or needed to read a flow, and an absent asset means nothing about whether it
exists. No script rebuilds the files. Capacity (nameplate) and output (a measured figure of a year)
are separate fields, each with its own year; a capacity whose source gives no year is shown with
"year not stated". The status of an asset is "operating" only when a dated page says it runs, and
"not stated" when no page read says so; it is never assumed. The rules, units and sources are in
[`pipeline/infrastructure/README.md`](pipeline/infrastructure/README.md).

Ports. Most ports that the hand-written freight routes name are assets (Boke, Guinea, stands for the river
terminals of a region and is none). Each port carries the code of the same place in the trade engine (`locode`), so a route
port, a lane port and the asset are one place: the route page links its ports to their pages, and a port's page
lists the routes that name it and the largest lanes that load or discharge there. The generated routes name the
ports of the trade engine, in its spellings ("Pusan", "Odessa"): the alias table of
`pipeline/infrastructure/route_assets.py` links them to the asset; a port of a generated route that is no asset
links, as the search does, to the largest lane through it, and a port that is neither stays plain text. Positions
come from the IMF PortWatch ports database (IMF terms of use; no vessel count or traffic figure is taken from it), or,
for a place it does not list, from OpenStreetMap or Wikipedia; a database point stands for the whole port, so a port
of several terminals is marked "Approximate location", and only a single terminal is placed on its site. A port's
commodities rest on a page read (its own page, or an article named in its note) or on a route or lane of the atlas
that uses it for that cargo: a database that gives a position states no cargo. A throughput or capacity is entered
only from a page read; outside the United States, a terminal's capacity is the operator's or the page's figure, and
its `n` says so.

Largest class by the published limits (Atlas estimate). Where a page gives the limits of a port (the deepest
berth, or the largest ship by draught, length, beam or deadweight), `pipeline/infrastructure/port_limits.py`
derives the largest class of `pipeline/freight/vessel_classes.json` that each segment of the port (dry bulk,
tankers, gas) can take, on four rules. (1) No class from a depth alone: a class is derived only when the page gives
a size of ship (deadweight, length or beam); a channel or berth depth is shown as a limit ("Depth") and gives no
class. (2) A limit stated for one kind of berth (an oil berth) is compared for that segment only. (3) A class with a
standard vessel (`std`) fits when that vessel is no larger than every limit given; a class without one is compared
by its typical deadweight (`size.typical`) with the port's deadweight limit, and is never placed above a smaller
class whose standard vessel does not fit; a class measured in cubic metres is compared only through a standard
vessel. The note of the result says, for each class shown, on which basis it was compared. (4) Only the page's
maximum is a limit, never a stated minimum, and where the page itself names the class the berths take ("for
Capesize ships"), the class is that statement. The result is never presented as the port's own statement: a larger
ship may call part-laden, with the tide or at another berth.

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
