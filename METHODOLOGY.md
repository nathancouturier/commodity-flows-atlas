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
   coal 95.1 Mt, refined products 55.4 Mt, LPG 9.8 Mt, corn 9.1 Mt, iron ore 9.1 Mt. Package L1 added
   Belarus → China for fertilisers: Belarusian potash for China leaves both through Russian seaports
   and by rail (OSW, November 2024: Belaruskali redirected its shipments to Russian ports and
   negotiated deliveries to China by land; Kommersant, reported by Reform.news in March 2026: 9% of
   the potash Belarus exported through Russia in 2025 went by rail to China and the CIS countries). No
   page gives the split of the trade with China, so the 2.9 Mt of 2024 are a mixed pair, drawn dashed
   from St Petersburg, the transit port of the Belarusian row. With the minor metals, the mixed pairs
   hold 313.1 Mt on 64 pairs in 2024.
5. **Land neighbours** (a mainland border, see below): land, unless the pair is in `SEA_NEIGHBOURS`
   for the cargo family. A landlocked end with a land border is land.
6. **Sea outlets** (`SEA_OUTLET`): a landlocked exporter whose group is listed leaves by sea through
   a foreign port, to a coastal buyer or to a landlocked one outside its overland blocs: Kazakh crude
   (CPC pipeline to Novorossiysk; 63.0 Mt in 2024), Azerbaijani crude (BTC pipeline to Ceyhan;
   23.3 Mt), Belarusian potash (0.7 Mt; the 2.9 Mt for China are mixed, rule 4), Paraguayan soy and corn (Paraná–Paraguay waterway; 2.6 Mt)
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

**2024 by mode** (42 lane groups, 25,849 pairs, 9,154.1 Mt): sea 7,752.5 Mt (18,994 pairs), sea via a
transit port 167.9 Mt (2,181 pairs), sea and overland 313.1 Mt (64 pairs), land 920.6 Mt (4,610
pairs). Seaborne: 7,920.4 Mt. (34 groups, 23,853 pairs and 9,140.4 Mt before the eight groups of
minor metals were added; Belarusian potash to China, 2.9 Mt, moved from transit to sea and overland.)

**Sea via a transit port.** The foreign port of a landlocked country is gateway data
(`TRANSIT` in `pipeline/freight/gateways/energy.py`), one sourced row per country and cargo family
or a default row. 23 countries have one: Austria and Czechia (crude: Trieste, Transalpine
Pipeline), Hungary and Serbia (crude: Omišalj, Adria pipeline), Kazakhstan (crude: CPC terminal,
Novorossiysk, a port in Russia), Azerbaijan (crude: Ceyhan, BTC pipeline), Chad (crude: Kribi),
South Sudan (crude: Port Sudan), Czechia (other cargo: Hamburg), Switzerland (Rotterdam), Uganda and
Rwanda (Mombasa), Zambia, Malawi, Burundi and DR Congo (Dar es Salaam), Zimbabwe (Beira), Ethiopia
(Djibouti), Burkina Faso and Mali (Abidjan), Niger (Cotonou), Nepal and Bhutan (Kolkata), and
Bosnia and Herzegovina, whose short coast has no port of its own (Ploče). Each of these rows cites a
Wikipedia article. Seven more countries have rows since package L1 (pages read on 23 November
2026): Belarus (fertilisers: St Petersburg, for the Bronka and St Petersburg terminals, from an OSW
commentary of November 2024 and a Reform.news report of Kommersant's 2025 figures), Kazakhstan (dry
bulk: Ust-Luga, from a Kpler note of February 2025 on Kazakh coal for the EU and Morocco), Paraguay
(grain and vegetable oil: the Up-River Paraná hub of Rosario, from a Bolsa de Comercio de Rosario
note of April 2017 on the grain coming down the waterway in transit in 2016), Austria and Hungary
(other cargo: Koper, Port of Koper article), Serbia (other cargo: Constanța, Port of Constanța
article, Danube traffic) and Botswana (Walvis Bay, Walvis Bay article). A family row rests on a page
that names one cargo of the family (coal, potash, soy): the other cargoes of the family take the
same port, which the note says. Slovakia has no row although the Constanța article names it: a
default row would also send its crude imports there. A transit pair is routed from or to that port
and the site writes "sea via" the port. A seaborne pair whose landlocked end has no sourced row
(Central Asian products, potash and urea of Uzbekistan and Turkmenistan, Kazakh products, Slovak
and Bolivian trade among them: 27.4 Mt in 2024, 47.7 Mt before package L1) stays in the seaborne
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
    steel); they are in `CAP`. A group under 1 Mt of seaborne trade a year keeps four decimals of Mt
    (0.1 kt) in its lane file, and its pairs file's seaborne total is the sum of its published rows.
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
  - 2024: 2,629 main seaborne lanes, 38 mixed lanes and 276 history lanes over 42 groups (2,400, 35
    and 182 over 34 groups before the minor metals); the main lanes carry 85.5% of 2024 seaborne
    tonnes. The share per group is the `coverage` of each lane file: 90% or more for iron ore, coal,
    bauxite, LNG, soybeans, manganese, LPG, corn and cobalt, among others; lowest for unwrought tin
    (59.6%), refined products (60.1%), aluminium (66.1%), cocoa (66.5%), unwrought lead (66.8%),
    unwrought zinc (67.5%), steel (68.2%) and coffee (69.9%); potash reads 80.0% (73.7% before the
    Belarusian transit row). Where trade is spread over thousands of pairs, the pairs table answers.
- **The pairs table** (`data/freight/pairs/<group>.json`) holds every pair of the latest year that
  the customs extract keeps (1,000 t or USD 1 million and more), whatever its mode: 25,849 pairs in
  2024. Each row gives the tonnage (kt: whole above 1 Mt, one decimal below), the mode, the two
  ports, the distance, the primary vessel class, the passages it has to cross and those it may
  cross (bit masks over the file's list of gates), and flags: tonnage estimated from value, caveat,
  main lane, check finding. A seaborne pair "not drawn on the map" is one without a main lane
  (1,149.6 Mt in 2024); a pair "not routed" has no route at all (43.9 Mt in 2024: 27.4 Mt because a
  landlocked end has no sourced transit port, 15.2 Mt because there is no sea route or it is under
  50 nm, mostly Malaysian refined products to Singapore, 1.3 Mt because an end has no gateway; 64.2
  Mt, 47.7 Mt of it for want of a transit port, before package L1).
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
  two ends, 15,841 Mt; a port keeps the weakest basis of its uses in the file, for each role, and a
  transit port is one more port): page names the cargo 69.8%, port used before 22.4%, general port
  4.0%, nearest seaport 2.2%, other direction 1.1%, no port (not routed) 0.6% (after package L1; 0.8%
  had no port before it). Most rows cite a Wikipedia article. The United States crude and
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
  routes name 45.1% of the 7,913 Mt of 2024 seaborne tonnes of the 34 customs groups. For the rest, the pairs table
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
  103). When a group list is cut, the lower-ranked corridors of the groups that have the most routes go first. The
  result for 2024 is 223 routes, and 59.9% of the seaborne tonnes named (all groups): eight of the 34 groups reach 70%
  (iron ore, bauxite, manganese, rapeseed, ferro-nickel, nickel ore, soybeans and spodumene) and 26 stay short of it,
  from coal (69.2%, one corridor left out by the cap) down to steel (23%), aluminium (21%) and refined products (34%),
  whose trade is spread over thousands of small pairs. `pipeline/freight/QA_routes.md`, written at each build, gives each
  group with its coverage, its reason when it is under the target, and the corridors the cap left out.

  A generated route is the atlas's own corridor, never a market benchmark: its id starts with `gen-` (group, exporting
  zone, importing zone or region), its name is "Cargo: zone to zone", its source is `atlas`, and its page says
  "Atlas corridor, generated from customs pairs". An end is named for a country, not a zone, when that country holds at
  least 80% of the tonnes of the end (counted at the typical ports of the corridor's pairs), unless the zone's own name
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
  port of the place it names (Qingdao) on a route that does not carry that cargo.
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
  start, the event and the passages of a banner are written by hand; the date the text was **checked
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
  "gasoline", "oil" is not "oil-fired"); a linked route or passage does not name a commodity by being
  linked. An event that names no commodity has none. The event that an alert points to is also shown
  with the alert's commodities. With a commodity chosen, the "Events" section of its page, the History
  timeline and the event markers of the price chart keep an event that names the commodity, or names no
  commodity at all (a shipping or market event), or belongs to an alert that covers it
  (`web/src/lib/events.ts`). The event page shows the change of the atlas's price series of each linked
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
(`data/countries/profiles/<ISO3>.json`, loaded when its page opens) and a light index
(`data/countries/profiles.json`).

- **Every line.** A country has a line for every row it has in any table of any commodity: production
  (with refinery output and the extra production tables), consumption, reserves, exports and imports
  (with the second trade tables such as refined copper or alumina). Its rank and share are those of
  the full table, of the same source and year. Nothing is cut: the page shows the first eight lines of
  each section and the rest behind "Show all".
- **Order and "Largest export".** Exports and imports are ordered by customs value (CEPII BACI, latest
  year, whatever the source and year of the tonnage on the same line; the line names both); "Largest
  export" is the largest of them in value. Production, consumption and reserves are ordered by share of
  the world total. Exports that customs data do not record are not estimated: the caveat the engine
  writes for that origin is shown under the exports (Iranian crude oil, for example).
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
  and year ("none recorded" where the country has no line on one side). Customers and suppliers: the
  first three partners of the latest customs year with their shares (tonnes; declared value for gold,
  silver and platinum-group metals), from the pairs tables of the trade-flow engine, or from the
  cleaned customs frame for the groups that have no lanes; an Atlas estimate among them keeps its mark.
  Concentration is the Herfindahl index of all partner shares, from 0 to 10,000 (10,000: one partner),
  also given as the number of equal partners it corresponds to (10,000 divided by the index). Imports
  over consumption is printed only where both are lines of the same unit and year; it is not the share
  of consumption that is imported (imports can be re-exported or stocked).
- **Trading or refining hub** is a derived label: exports and imports of the same product each at least
  1% of the world total, and no line for the country in a production table that lists every producing
  country (EIA, USDA PSD, FAOSTAT). USGS tables list the main producers only: no label is derived from
  them.
- **Freight** is read from the pairs tables of the engine (section 5) for the latest customs year: the
  share of the country's tonnes by mode (sea, sea through a port of another country, sea and overland
  with the split not known, overland), the typical ports of its seaborne pairs with their basis (an
  Atlas assumption), and for each passage the share of its seaborne tonnes whose assumed route has to
  cross it ("at least") or may cross it ("up to"), with the routing rules of the chokepoint estimates.
  A passage is listed from 2% of the seaborne tonnes. These shares are Atlas estimates.
- **All goods.** The ten largest exports and imports by value at HS4, every chapter, with their share
  of the country's total merchandise exports or imports, from `pipeline/cache/hs4_*`, written by
  `pipeline/trade/extract_hs4.py` in one pass over the latest year of the CEPII BACI archive (also run
  by the annual job after a new BACI version). A heading is named with the first six-digit description
  under it in the archive's product list. If that table and the customs frame are not of the same year,
  the basket is left out. Up to five raw-material headings outside the catalogue are listed apart, each
  at least 5% of the country's raw-material exports (countries with USD 200 million of them or more).
- **Companies** are listed under the country of their headquarters, with every commodity they are
  listed for; the operators of the infrastructure assets in the country are listed apart.
- **EU.** USDA PSD gives one row for the European Union: its page lists the member states, and each
  member's page links to it.
- **No data.** A country of the index with no line, trade, lane or asset says what it is, in the words
  of the base map (Natural Earth), and that the customs data have no code of their own for it.
- **"World top-10 in N commodities"** counts the catalogue commodities for which the country is in the
  top 10 of at least one table.
- **Warnings** of a commodity table (trade hubs that re-export, gross weight against contained metal)
  are repeated on the lines built from it.

## 7. Prices

- Monthly prices: World Bank Commodity Price Data (Pink Sheet), nominal USD, 1960 to the latest
  month.
- Daily prices: EIA spot series (Brent, WTI, Henry Hub, New York Harbor gasoline, ULSD and heating
  oil, US Gulf jet fuel, Mont Belvieu propane).
- Freight cost proxy: the US producer price index for deep-sea freight transportation
  (series PCU483111483111, U.S. Bureau of Labor Statistics, index June 1988 = 100, not seasonally
  adjusted), monthly, fetched through FRED when the owner's free `FRED_API_KEY` is set.
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
  chart an event that names commodities is shown when one of them is charted, and an event that names
  none is always shown. `web/scripts/validate-data.mjs` checks that the series files agree with the index.
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
    barrel (by definition) one tonne is 487 gallons, which the page note gives.
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
  from the sum of its rows, shares are computed on the sum. This holds for every table whose country
  lines (with USGS's "Other countries" line, drawn or not) add up to more than the published world
  total by over 0.05% (`LINES_OVER_WORLD` in `build_commodities.py`): 17 tables in the 2026 release,
  from manganese reserves (1,798,000 against a published 1,700,000 kt Mn) to silver reserves
  (610,400 against 610,000 t). The table keeps the published total as `worldPublished` and says so
  in its note, and the key figure of the page stays the published total.
- **Rice** flows are converted from paddy (HS 100610) to milled equivalent at the USDA PSD milling
  rate of the exporter (the world average where PSD has none), the factor and its market year being
  written in each row's note. Such a row is an Atlas conversion, not an estimate: its note starts
  "Atlas conversion", it carries no estimate mark, and its tonnage keeps three significant digits.
- **Metals pages** (`pipeline/commodities/metals.py`; tests in `pipeline/tests/test_metals.py`):
  - **Shares on the sum of the lines.** Every USGS table that has an "Other countries" line has its
    shares computed on the sum of its countries and that line, whatever the gap to the rounded
    published total (zinc: 12,540 kt against a published 13,000; gold production: 3,250 against
    3,300 t). The published total stays as `worldPublished`. A table without that line (nickel
    reserves, lithium production) keeps the published total, and its "Rest of world" is what the
    source does not list.
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
    (no conversion is read on a page). A country is listed when USGS gives its production and the
    customs tables have its imports and exports; a country with one of the three terms missing, or a
    negative result, is left out and the note counts and names them. A country that trades but has
    no USGS production figure is not in the table. Stock changes are not known. The world total is
    the USGS world production of the same year (trade nets out in the world), on which the shares
    and "Rest of world" are computed; the order is not a world ranking (`norank`). Rows carry the
    source id `atlas`, three significant digits in the file and two on the page, and their three
    inputs in the note. The United States apparent consumption that USGS states (a different
    definition for each product, given beside it) and its net import reliance (Fig2 of the Mineral
    Commodity Summaries, with the main sources of 2021 to 2024) are shown as published figures, apart
    from the estimate. worldsteel's tables are not copied.
  - **Value and unit value.** Rows of the customs tables and the flows of the metals pages carry the
    declared value (`usd`, USD) and the unit value (`uv`, USD per tonne, three significant digits).
    A row with 10% or more of its tonnage estimated from the declared value, and every flow whose
    tonnage is an Atlas estimate, has no unit value: the value was used to estimate the tonnage.
    The fine-metal tables of gold, silver and platinum-group metals show the value only.
  - **Concentration.** For every table with a world total: the share of the first country, of the
    first three, and the Herfindahl index (the sum of the squares of the countries' shares in
    percent, from near 0 to 10,000), computed on the countries the table lists. Where USGS's "Other
    countries" line is large the countries cover less than the whole and the index is a lower bound.
    It is arithmetic on published figures and carries the estimate mark only where a row is an
    estimate.
  - **Notes on trading places.** A country that both imports and exports the same product in
    similar tonnages (each at least 1.5% of its table, the smaller at least half of the larger) and
    that USGS does not name as a producer gets a note on both rows, worded as a possible reading.
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
    (the newest year, the one before it), and the table, the key figure, the history file and the map colours all follow the
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
    comparable with USDA's. The map colours a member state with its own figure when the crop has a table of the member states for the
    measure being shown (production, exports, imports; the latest year only, these tables have no series by year), as its share of
    the world total of that source and year, and with the USDA European Union value otherwise; the legend and the tooltip say which.
  - *Russian grain*: Russia has not published its customs data since 2022, so its flows rest on what importers declare. The caveat
    registry (`pipeline/trade/caveats.py`, `_grain_gap`) states, for wheat, maize, soya beans, rapeseed, soybean meal and oil, the
    customs figure against the two USDA marketing years that overlap the customs year, the percentage by which it is below
    them, and the importers that took the grain in the three years 2019 to 2021 (0.5 Mt a year or more) and have none recorded in the
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
    not crude alone; the Persian Gulf and OPEC are EIA's own groups), petroleum stocks and, for the refined
    products page, oil demand, and for the LPG page natural gas plant liquids. Every series carries three
    figures, each with its month, and a change: the average of the year before the latest month (the twelve
    months weighted by their days, which equals EIA's own annual figure: the validator and the tests check it),
    the lowest month of the latest year, the latest month, and the latest month against the average in per cent.
    These are arithmetic on published figures, not estimates. A month that EIA gives as withheld ("w"), not
    available or absent stays empty and nothing is filled in; a series whose last month is more than a year old has
    stopped and is left out. The Gulf total adds Saudi Arabia, Iraq, Kuwait, Qatar, the United Arab Emirates, Iran
    and Bahrain month by month, only for months in which all seven have a figure.
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
    ratio of EIA's own United States series in both units (the same in every year from 1980 to 2019), and
    EIA's world total gets the figure added. The tonnes of 2021 (148 Mt against 43 Mt the year before, 3.4 barrels
    per tonne against 11.6) are replaced the same way, and the world total of 2021 is corrected by the difference.
    Each such row says so ("Atlas conversion"); 2020, 5% off the ratio, stands as published.
  - *Other tables from the file*: consumption of motor gasoline, distillate fuel oil, jet fuel and residual fuel
    oil by country (refined products), nuclear generating capacity (uranium), metallurgical coke production and
    trade (metallurgical coal), and in a note the world coal production by rank (the four ranks and metallurgical
    coal add up to EIA's world total).

## 11. Infrastructure layer

The mines, smelters, ports, fields, refineries, LNG terminals and pipelines of
`data/infrastructure/` are a hand-curated sample, not an inventory: each asset was picked because it
is large, well known or needed to read a flow, and an absent asset means nothing about whether it
exists. No script rebuilds the files. Capacity (nameplate) and output (a measured figure of a year)
are separate fields, each with its own year; a capacity whose source gives no year is shown with
"year not stated". The status of an asset is "operating" only when a dated page says it runs, and
"not stated" when no page read says so; it is never assumed. The rules, units and sources are in
[`pipeline/infrastructure/README.md`](pipeline/infrastructure/README.md).
