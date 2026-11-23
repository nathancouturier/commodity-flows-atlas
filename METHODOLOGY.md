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
     factor 2 of its yearly average, otherwise Peru's average of the year) is re-estimated at Peru's
     unit value. Chile reads 7,000 to 8,000 USD/t in some years against about 2,000 for Peru, as if
     its tonnage were contained copper; a tonnage declared in contained metal is the plausible
     cause, not established. The rule changes 221 rows from 2002 to 2024; in 2024, 11 rows declared
     at 4.81 Mt become 13.8 Mt (Chile → China 2.79 Mt declared, 9.27 Mt estimated). Checked against
     Cochilco's export tables of fine copper in concentrate (free tables, available to 2021 only),
     the estimated tonnage implies a steady grade of 26 to 30% copper in 2010–2021, where the declared
     tonnage implies 44 to 56% in 2010–2013 and 70% in 2021, impossible for a concentrate (check made
     by the commodity package; Cochilco's figures are not published by the atlas).
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
  more is estimated is itself labelled "Atlas estimate". In 2024, 168 rows and 76.4 Mt of the lane
  groups (0.84% of their tonnage) are estimated; the largest are crude oil United Arab Emirates →
  Thailand (24.5 Mt), wheat Russia → Egypt (11.1 Mt) and copper concentrate Chile → China (9.27 Mt).
  The share of each lane group's 2024 seaborne tonnes that is estimated is the field `est` of its
  lane file: 35.7% for copper concentrate, 8.0% for wheat, 1.8% for crude oil, 1.3% for LPG, under
  1% for every other group.
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
   Russia → China 236.2 Mt, the United States → Mexico 57.2 Mt, Mexico → the United States 10.9 Mt,
   France → Spain 2.7 Mt, China → Russia 2.6 Mt, Spain → France 0.2 Mt; by group, crude oil 108.5 Mt,
   coal 95.1 Mt, refined products 55.4 Mt, LPG 9.8 Mt, corn 9.1 Mt, iron ore 9.1 Mt.
5. **Land neighbours** (a mainland border, see below): land, unless the pair is in `SEA_NEIGHBOURS`
   for the cargo family. A landlocked end with a land border is land.
6. **Sea outlets** (`SEA_OUTLET`): a landlocked exporter whose group is listed leaves by sea through
   a foreign port, to a coastal buyer or to a landlocked one outside its overland blocs: Kazakh crude
   (CPC pipeline to Novorossiysk; 63.0 Mt in 2024), Azerbaijani crude (BTC pipeline to Ceyhan;
   23.3 Mt), Belarusian potash (3.6 Mt), Paraguayan soy and corn (Paraná–Paraguay waterway; 2.6 Mt)
   and Zambian copper (TAZARA railway to Dar es Salaam; 1.1 Mt).
7. **Two landlocked ends**: land.
8. **One landlocked end**: sea via a transit port when the two countries share no overland bloc
   (`BLOCS`), land otherwise.
9. **Default**: sea.

**Cargo families** (`FAMILY`): crude; refined products; LPG; LNG; dry bulk (iron ore, coal, bauxite,
alumina, manganese, copper, nickel and zinc ores, spodumene concentrate); grain (wheat, corn,
soybeans, soybean meal, rice, sugar, rapeseed); vegetable oils (soybean and palm oil); fertilisers
(potash, phosphate rock, DAP, urea); metals (steel, refined copper, aluminium, nickel intermediates,
ferro-nickel, and the groups that have no lanes: uranium, lithium chemicals, cobalt, rare earths,
tin, lead and zinc metal); softs (coffee, cocoa, cotton). Gold, silver and platinum-group metals
get no mode ("mode not modelled"): much of it may fly, but no source was read, so no mode is
claimed. Flows of the groups without lanes are listed with their mode, not drawn as sea routes.

**The lists** are Atlas assumptions. Each entry carries its reason and, where a page was read, its
URL, returned with the mode; an entry without a URL is an unsourced assumption. 2024 tonnage:

- `SEA_NEIGHBOURS`: 33 pairs of neighbours that trade by sea, 223.4 Mt. The largest: China–India
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

**2024 by mode** (34 lane groups, 23,853 pairs, 9,141.9 Mt): sea 7,744.2 Mt (17,489 pairs), sea via a
transit port 170.3 Mt (2,061 pairs), sea and overland 309.8 Mt (52 pairs), land 917.6 Mt (4,251
pairs). Seaborne: 7,914.5 Mt.

**Sea via a transit port.** The foreign port of a landlocked country is gateway data
(`TRANSIT` in `pipeline/freight/gateways/energy.py`), one sourced row per country and cargo family
or a default row. 23 countries have one: Austria and Czechia (crude: Trieste, Transalpine
Pipeline), Hungary and Serbia (crude: Omišalj, Adria pipeline), Kazakhstan (crude: CPC terminal,
Novorossiysk, a port in Russia), Azerbaijan (crude: Ceyhan, BTC pipeline), Chad (crude: Kribi),
South Sudan (crude: Port Sudan), Czechia (other cargo: Hamburg), Switzerland (Rotterdam), Uganda and
Rwanda (Mombasa), Zambia, Malawi, Burundi and DR Congo (Dar es Salaam), Zimbabwe (Beira), Ethiopia
(Djibouti), Burkina Faso and Mali (Abidjan), Niger (Cotonou), Nepal and Bhutan (Kolkata), and
Bosnia and Herzegovina, whose short coast has no port of its own (Ploče). Each row cites a
Wikipedia article. A transit pair is routed from or to that port and the site writes "sea via"
the port. A seaborne pair whose landlocked end has no sourced row (Belarusian potash, Paraguayan
grain, Central Asian dry bulk among them: 47.7 Mt in 2024) stays in the seaborne totals but is not
routed and has no lane.

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
soybean meal 62.5 → 61.4; rapeseed 21.0 → 20.0. Copper concentrate (28.8 → 38.8 Mt) moved because of
cleaning rule 8, not of the mode rule. The 32 groups of the earlier rule total 7,893.0 Mt before and
7,899.4 Mt now; ferro-nickel (10.1 Mt) and spodumene concentrate (5.0 Mt) are new groups.

## 3. Lanes and routes

Built by `pipeline/freight/build_lanes.py` (lanes and pairs) and `pipeline/freight/build_freight.py`
(benchmark routes), with the routing of `pipeline/freight/routing.py`.

- **Lane selection** (latest year first). For each commodity group and the latest year:
  - the **main set**: every seaborne pair at or above the group's floor, largest first, up to the
    group's cap. The floor is 0.05 Mt (0.02 Mt for coffee, cocoa, cotton, nickel intermediates,
    refined copper and zinc concentrate; 0.03 Mt for aluminium and soybean oil). The caps run from 20
    lanes (nickel ore, spodumene concentrate) to 150 (refined products, steel); they are in `CAP`.
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
  - 2024: 2,400 main seaborne lanes, 35 mixed lanes and 182 history lanes over 34 groups; the main
    lanes carry 85.4% of 2024 seaborne tonnes. The share per group is the `coverage` of each lane
    file: 90% or more for iron ore, coal, bauxite, LNG, soybeans, manganese, LPG and corn, among
    others; lowest for refined products (60.1%), aluminium (66.1%), cocoa (66.5%), steel (68.2%),
    coffee (69.9%) and potash (73.7%: Belarusian potash has no sourced transit port). Where trade is
    spread over thousands of pairs, the pairs table answers.
- **The pairs table** (`data/freight/pairs/<group>.json`) holds every pair of the latest year that
  the customs extract keeps (1,000 t or USD 1 million and more), whatever its mode: 23,853 pairs in
  2024. Each row gives the tonnage (kt: whole above 1 Mt, one decimal below), the mode, the two
  ports, the distance, the primary vessel class, the passages it has to cross and those it may
  cross (bit masks over the file's list of gates), and flags: tonnage estimated from value, caveat,
  main lane, check finding. A seaborne pair "not drawn on the map" is one without a main lane
  (1,153.7 Mt in 2024); a pair "not routed" has no route at all (64.2 Mt in 2024: 47.7 Mt because a
  landlocked end has no sourced transit port, 15.2 Mt because there is no sea route or it is under
  50 nm, mostly Malaysian refined products to Singapore, 1.3 Mt because an end has no gateway). The
  Route finder reads this table, so it never says "no flow" for a pair that customs data record.
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
  - "nearest seaport".

  Share of 2024 pair-end tonnage (each seaborne pair counted at its two ends, 15,829 Mt): page names
  the cargo 70.2% (plus 0.7% on a transit row that names the cargo), port used before 22.1%, general
  port 2.7% (plus 0.2% on a transit country's default row), nearest seaport 2.2%, other direction
  1.1%, no port (not routed) 0.8%. Most rows cite a Wikipedia article. The United States crude and
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
  Elsewhere the main route's passages are certain. Applied to every passage, the same test would
  turn most of the "at least" tonnage of Lombok, Makassar and Ombai, and part of Dover's and
  Singapore's, into "may cross", through ways round the network offers (the Alas Strait, the
  Banda Sea, north of Scotland, the Durian Strait) that are not how these ships sail, against
  PortWatch's 950 and 1,085 Mt of dry cargo at Lombok and Makassar in 2024; the measurements are in
  the comment of `ROUTE_AROUND`, and `routing.classify(..., around=GATES)` gives that reading. The
  chokepoint pages name the routes of similar length that the atlas does not count as a choice
  (`parallelNote`). `QA.md` also prints
  the "at least" and "up to" tonnage of Malacca, Sunda, Lombok, the Taiwan Strait and Luzon at 3% or
  150 nm, 5% or 300 nm and 10% or 500 nm.
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
  lanes takes about 8 minutes on the development machine, a warm one under a minute.
- **Laden days** are distance ÷ typical laden speed for the class (`SPEED` in
  `pipeline/freight/vessel_rules.py`): 11 kn for Capesize, Newcastlemax and VLOC; 12 kn for
  Panamax, Kamsarmax, Supramax and Ultramax; 11.5 kn for Handysize; 12.5 kn for VLCC, MR and
  handy tankers; 13 kn for Suezmax, Aframax, LR1 and LR2; 15.5 kn for VLGCs; 12 kn for mid-size gas
  carriers; and 17 kn for LNG carriers and container ships. These are Atlas assumptions, published
  with each class (`vessel-classes.json`, source id `atlas`).
- **Curated tables.** Some rules are entered by hand and are Atlas judgements, not figures from a
  dataset: the mode lists (`modes.py`), the gateway rows and coast rules (`gateways/*.py`), the
  transit ports (`gateways/energy.py`), the vessel class rules and the draught tables
  (`vessel_rules.py`), the gates and routing constants (`routing.py`), the benchmark route
  definitions (`routes_def.json`) and the vessel size ranges (`vessel_classes.json`). Each entry
  gives its reason and, where a page was read, the page. The size ranges are conventional industry
  ranges, not a single authoritative table, and several benchmark route definitions are marked
  uncertain in `pipeline/freight/NOTES_routes.md`.

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

These are labelled "typical" in the interface. They are not measured shares of each class.

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
    routed tonnes. Where the two agree, one figure is shown. An entry is written when "up to" is at
    least 2% of the group or 1 Mt: 494 entries over 20 passages in 2024 (Hormuz: 20 groups).
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
    atlas's Red Sea alert). Both figures are estimates, and the note names both ("IMF PortWatch,
    data adapted").
  - **Check K9** writes, for every passage with a counter, "at least" and "up to" by vessel type
    beside PortWatch's volume of the same year and of its best full year since 2019 (table in
    `QA.md`). A passage is flagged when "at least" is above 110% of the best year (the assumed ports
    or routes probably overstate it) or above the same year's volume. The Danish Straits are not
    compared: PortWatch counts the Oresund only. The check is a report; it never stops a build.
  - **Sunda**: the routing network sends little traffic through the Sunda Strait by itself, so its
    "at least" figure is a floor of the model (1.9 Mt of all groups in 2024, against 443 Mt of all
    ships in PortWatch), not a statement about traffic; its "up to" figures carry the cargo that may
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
    use".
- **Chokepoint traffic** is IMF PortWatch's daily count of tankers, dry bulk, container, general
  cargo and ro-ro vessels, and PortWatch's estimate of the trade volume they carry (tonnes of
  cargo, not deadweight). Both are shown as weekly averages (calendar weeks starting on Monday,
  `pipeline/freight/build_portwatch.py`) and as the average of the last 28 days. These averages
  are a transformation of PortWatch's daily data ("Atlas weekly averages of IMF PortWatch daily
  counts"); the counts are aggregated, no vessel position or track is used. PortWatch counts the Oresund but not the Great Belt, so the Danish Straits series is
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
- Freight cost proxy: the US producer price index for deep-sea freight transportation
  (series PCU483111483111, U.S. Bureau of Labor Statistics, index June 1988 = 100, not seasonally
  adjusted), monthly, fetched through FRED when the owner's free `FRED_API_KEY` is set.
- Each series carries a note on what it measures (for example, the Brent series is a posted-price
  proxy before the mid-1980s). A series with fewer than 24 values is rejected.
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
    standard atomic weights of CIAAW).
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
  which each row's note gives. Platinum-group metals are valued at the platinum price, so a flow
  rich in palladium or rhodium is overstated or understated. These groups get no transport mode.
- **Copper concentrate**: Chilean rows re-estimated at Peru's unit value (cleaning rule 8, section 1).
- **Spodumene concentrate** has no customs code of its own. It is read from HS 253090 ("mineral
  substances not elsewhere specified"), keeping only the rows to China from Australia, Zimbabwe and
  Brazil, the exporters for which a page read says that they ship lithium concentrate to China:
  30% of the code's tonnage and 67% of its value in 2024 (5.04 Mt). It is labelled an Atlas estimate,
  shown in its own table and not added to the lithium chemicals tables. A flow of the lithium
  chemicals codes declared under 1,500 USD per tonne, the price of ore rather than of a chemical,
  is left out of those tables and listed in a note.
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
  are counted in a separate line, not in "Other countries". Where USGS's rounded world total differs
  from the sum of its rows, shares are computed on the sum.
- **Publishers cited for a headline figure only**: GIIGNL and IGU (world LNG trade), the World Steel
  Association (world crude steel production, 1,849.4 Mt in 2025), the World Gold Council (world mine
  production) and the International Cocoa Organization (world cocoa bean production per crop
  year). Each figure carries its publisher, year and link and stands beside the atlas's table; their
  tables are not copied.

## 11. Infrastructure layer

The mines, smelters, ports, fields, refineries, LNG terminals and pipelines of
`data/infrastructure/` are a hand-curated sample, not an inventory: each asset was picked because it
is large, well known or needed to read a flow, and an absent asset means nothing about whether it
exists. No script rebuilds the files. Capacity (nameplate) and output (a measured figure of a year)
are separate fields, each with its own year; a capacity whose source gives no year is shown with
"year not stated". The status of an asset is "operating" only when a dated page says it runs, and
"not stated" when no page read says so; it is never assumed. The rules, units and sources are in
[`pipeline/infrastructure/README.md`](pipeline/infrastructure/README.md).
