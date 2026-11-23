# Freight reference data: verification notes

## Benchmark definitions (read on 23 November 2026)
Pages read in full, one request at a time, for the 86 benchmarks of `routes_def.json` (`definition` of each route):
- Baltic Exchange, Guide to Market Benchmarks, version 7.09 (December 2025), appendix 2 (index specifications):
  https://www.balticexchange.com/content/dam/balticexchange/consumer/data-services-/documents-/ocean-bulk/GMB.pdf
  The main source of codes, cargoes, quantities, ports, ranges and durations. The site's robots.txt allows these pages
  (crawl delay 1 s).
- Baltic Exchange dry, tanker and gas service pages (`/en/data-services/market-information0/dry-services.html`,
  `tankers-services.html`, `gas-services.html`): the routes listed now (status "active"), the Capesize, Panamax, Supramax
  and Handysize averages and the tanker indices and baskets with their weights.
- Baltic Exchange circulars: 19/25 (180,000 dwt Capesize routes ceased on 24 December 2025; 182,000 dwt standard from
  2 January 2026), 32/24 (BCI182 routes on public trial from 21 October 2024), 40/25 and 41/25 (C5TC(182) weights and BDI),
  15/24 (TD2 ceased 1 August 2024), 35/25 (TD17, TD24, TC9 ceased from 24 December 2025), 22/25 (TD28, TD29 live
  4 August 2025), 02/26 and 08/26 (TD33 trial 12 January, live 10 February 2026), 30/26 (TD34 live 5 May 2026).
- Veson VesselsValue summary of Baltic definitions (https://help.veson.com/vesselsvalue/baltic-timeseries-definitions):
  read in full; it is older than the guide (Supramax routes as _58, the 180,000 dwt Capesize average, C2 in long tons,
  C3 at 160,000 or 170,000 t, C7 at 150,000 or 160,000 t). Where the two differ the guide is followed.
- Riviera Maritime Media (2025) for the location of the Pacific Area Lightering zone of TD29 (off California).
The extraction (code, description, vessel, cargo, quantity, load and discharge, duration, weight) is kept outside the
repository with the saved pages. Index values are proprietary: none is stored or shown.

## What the pages settled
- Ports: TD23 Basrah-Lavera, TC15 Skikda-Chiba, TD7 Hound Point-Wilhelmshaven, TD22 Galveston offshore lightering-Ningbo,
  TC10 Yeosu-Los Angeles, TD9 Covenas-Corpus Christi, TC14 Houston-Amsterdam, TC16 Amsterdam-offshore Lome, TC19
  Amsterdam-Lagos, BLPG2 Houston-Flushing, TD17 Primorsk-Wilhelmshaven, TC9 Primorsk-Le Havre, TC20 Jubail-Rotterdam
  (90,000 t), TC21 Houston-Pozos Colorados (38,000 t). Yeosu is "Yosu" in the port table, Flushing is Vlissingen.
- Status: C10_14 and C14 ended on 24 December 2025 and point to C10_182 and C14_182; TD2, TD17 and TC9 are ended with
  their dates. TD1 (ceased 22 December 2023, Circular 29/23), TD12 (ceased in 2022, Circular 08/22) and TD24 (ceased from 24 December 2025)
  were not added: they are no longer published. C8_14, C9_14 and C16 were not added for the same reason.
- Routes added (26): C2, C8_182, C9_182, C10_182, C14_182, C16_182, P4_82, P5_82, P7, P8, S1B_63, S3_63, S4B_63, S5_63,
  S8_63, S9_63, S15_63, TD14, TD18, TD21, TD28, TD29, TD33, TC11, TC22, TC23.
- Index membership and weights: `baltic_indices.json` (C5TC 182 and 180, P5TC, S11TC, BES Asia, HS7TC, BDTI, BCTI,
  VLCC, Suezmax and Aframax time-charter equivalents, MR Atlantic and Pacific baskets, BLPG, BLNG; BDI of indices).

## What no page settled
- Time-charter routes name delivery and redelivery areas, not ports or cargoes. Their line is either the trace of
  another route (`standIn`) or a laden leg chosen by the atlas (`ROUTE_PORTS` in `build_freight.py`); their cargo tags
  are typical of the class (`cargoNote`) and they have no corridor. P6_82 names no cargo and no loading area: it keeps
  no corridor (the audit's guess of an east coast South America grain round voyage is not in the definition).
- TC23 names ranges (ARA to UK-Continent); it is drawn Amsterdam-Le Havre, the ports of its time-charter equivalent.
  TC24 (38,000 t US Gulf to west coast South America) names no port and is not added.
- TD29 discharges in an offshore zone: drawn to Long Beach. The customs table counts Canadian crude to the US as
  overland, so TD29 has no share.
- TD21 is assessed on the Baltic standard Panamax tanker (75,000 dwt); the atlas has no Panamax tanker class and draws
  it in the LR1 class, the same size.
- The guide and the tanker page still list TD2 in the BDTI formula although Circular 15/24 ended it.
- Not added, to check later: TD32 (cross north-west Europe, live 2026 per circular 21/26 title), the Baltic
  Intermediate Tanker routes (TC25, TC26, TD30, TD31, live January 2026 per circular 03/26 title) and TC24.
- Corridors kept off to leave the 120 generated corridors unchanged: TC11 (South Korea to Singapore) and TC22 (South
  Korea to Australia) are counted on generated corridors, TD34 (Oman to China) too, and P8 counts soybeans only.
- Other choices: TD25 and TD33 share a corridor; TC5 holds the Gulf-Japan products corridor (TC1 none);
  middle-east-europe-diesel holds TC8 and TC20; guyana-europe-crude has none (TD27 holds it).
- Lithium (spodumene) is not in the atlas commodity list: that route has empty cargoes/corridor.
- Several non-benchmark country lists (e.g. Argentina soymeal/corn destinations, Black Sea wheat destinations,
  Vancouver potash destinations) are editorial selections and should be replaced by customs-derived shares later.
- Gas: BLNG1-3 are the 174,000 cbm series (the 160,000 cbm series ceased, guide version 7.09). BLPG parcel 44,000 t;
  its time-charter equivalent is on the VLGC84.

## Canal limits (discrepancies)
- **Panama**: Panamax locks LOA 289.56 m (950 ft); 294.13 m applies only to container/passenger ships (Wikipedia citing PCA), whereas the brief gave 294.13 m for all. Beam 32.31 m and TFW draft 12.04 m confirmed. Neopanamax: beam 51.25 m (raised from 49 m in 2018), draft 15.24 m, and **LOA 370.33 m since May 2021** (PCA news), not 366 m (original). The live PCA "Vessel Requirements" page returned 404, so these come from the PCA news page plus Wikipedia.
- **Suez**: 20.1 m (66 ft) draft for beam up to 50 m with a 1,006 m2 wetted-area cap (Wikipedia/EIA citing SCA). SCA tables not fetched directly.

## Vessel class size ranges
Min/max/typical values are conventional industry ranges plus Baltic reference vessels (Capesize 182k, Kamsarmax/"Panamax" 82k, Ultramax 63.5k, Supramax 58k, Handysize 38k, VLCC 300k, Suezmax 160k, Aframax 105k, LR1 75k, MR 47k per Veson). They are not from a single authoritative table. Newcastlemax (185-210k), VLOC (230-400k), handy tanker 37k, LR2, and LNG Q-Flex/Q-Max ranges are unverified. `dims` only where sourced: Suezmax draft/beam (SCA limits), Newcastlemax maxima (Wikipedia), Kamsarmax 229 m LOA.
