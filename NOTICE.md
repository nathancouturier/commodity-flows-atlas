# Notice: licences and attributions

This file says under which terms each part of the repository and of the published data may be used, and how the
third-party material the atlas relies on is credited. The list of every source, with its licence, is in
[DATA_SOURCES.md](DATA_SOURCES.md), generated from `data/sources.json`. The licences of the software packages and
fonts used by the site are in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

## At a glance

| What | Terms |
|---|---|
| Source code (`web/src`, `web/scripts`, `pipeline/**/*.py`, `.github/`) | MIT, see [LICENSE](LICENSE) and "Source code" below |
| Figures computed by the atlas (source id `atlas`) and its lane and route geometry | CC BY 4.0, see below |
| Files adapted from Wikipedia (infrastructure, companies, events, vessel classes, typical ports and others) | CC BY-SA 4.0, see below |
| Points of a few infrastructure assets taken from OpenStreetMap | ODbL 1.0, © OpenStreetMap contributors, see below |
| Each third-party dataset, and the caches and definition files that hold it | The licence of its own source, see [DATA_SOURCES.md](DATA_SOURCES.md) |
| Third-party material cited, not redistributed | Not licensed by the atlas, see "Cited, not redistributed" |
| Software packages and fonts | Their own licences, see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) |

## Source code: MIT

The MIT licence in [LICENSE](LICENSE) covers the source code: the files under `web/src` and `web/scripts` (with the
build and configuration files of `web/`), the Python scripts `pipeline/**/*.py`, and `.github/` (workflows and actions).

It does not cover data. Data files kept in the repository follow the terms of this notice, wherever they sit:

- `data/` (the published files), as described in the sections below;
- the curated definition files under `pipeline/`, which carry third-party or Wikipedia-derived content:
  `pipeline/freight/events.json`, `alerts.json`, `chokepoints.json`, `vessel_classes.json`, `routes_def.json`,
  `sources_freight.json`, `sources_chokepoints.json`, `pipeline/freight/NOTES_routes.md` and
  `pipeline/companies/sources_companies.json`. The Wikipedia-derived parts of them are CC BY-SA 4.0 (see below);
- the data rows held in Python files: the gateway and transit-port rows of `pipeline/freight/gateways/*.py`, the draught
  tables of `pipeline/freight/vessel_rules.py` and the list entries of `pipeline/freight/modes.py`. The code of these
  files is MIT; the rows that cite a Wikipedia article (their `url` or source string) are adapted from it and are
  CC BY-SA 4.0 (the list of articles is below), and the rows that cite another publisher keep that publisher's terms;
- the caches in `pipeline/cache/`: `baci_flows.csv.gz`, `hs4_exports.csv.gz`, `hs4_imports.csv.gz`, `hs4_totals.csv`,
  `hs4_exports_desc.csv`,
  `sea_flows.csv.gz`, `mixed_flows.csv.gz`, `seaborne_totals.json`, `baci_rice_forms.csv` and `baci_country_codes.csv` are
  derived from CEPII BACI (Etalab Open Licence 2.0); `faostat_cocoa_production.csv`, `faostat_eu_crops.csv` (crop production
  of the 27 member states of the European Union and the world, FAOSTAT QCL) and
  `faostat_fertilizer_production.csv` are FAOSTAT data (CC BY 4.0); `metcoal_pairs.csv`, `metcoal_ports.csv` and `metcoal_meta.json` hold the Queensland
  Government's coal sales (CC BY 4.0) and EIA's exports of United States coal (public domain), credited below; `us_lpg_volumes.json` holds figures of
  the US Census Bureau's export detail file (its Public-Use Statement, credited below) and of EIA's exports by destination (public domain), `comtrade_tin_china.json` the few figures of UN Comtrade that
  the tin page prints ("Source: UN Comtrade", no answer of the service is published) and `aus_req_lng.json` one table of the Australian Department of
  Industry, Science and Resources' Resources and Energy Quarterly (CC BY 4.0), all three credited below; `wna_uranium.json` is World Nuclear Association data
  (terms to be confirmed); `adjacency.json` is derived from Natural Earth (public domain); `geom_cache.json` and
  `route_cache.json` hold computed routes (see the next section); `trade_checks.json` holds the findings of the atlas's
  checks, which quote CEPII BACI, USDA PSD, EIA, USGS and IMF PortWatch figures under the terms of each.

## The atlas's own figures: CC BY 4.0

Figures that the atlas computes itself carry the source id `atlas` (and the label "Atlas estimate" where they are
estimates): shares of seaborne trade, vessel-class tonne-mile shares, totals computed from several sources, laden days and alternative
routings, estimates written in the notes, and the geometry of the lanes and routes (`data/freight/`). The owner of
the project releases them under the Creative Commons Attribution 4.0 International licence
(<https://creativecommons.org/licenses/by/4.0/>).

Attribution line to use: **Commodity Flows Atlas** (<https://nathancouturier.github.io/commodity-flows-atlas/>).

What this release does not do:

- It does not change the licence of the datasets the figures are computed from. A figure derived from a third-party
  dataset keeps the credit and the conditions of that dataset (see the section below and
  [DATA_SOURCES.md](DATA_SOURCES.md)). Chokepoint traffic computed from IMF PortWatch is the case that needs the most
  care: see "IMF PortWatch".
- It does not cover the lane and route geometry beyond what the atlas itself adds. The geometry is computed on the
  Eurostat SeaRoute network (EUPL 1.2, built on the Oak Ridge National Laboratory Global Shipping Lane Network,
  whose terms are to be confirmed). Whether that derivation carries the EUPL conditions has not been established.

## Material adapted from Wikipedia: CC BY-SA 4.0

The following files contain material adapted from English Wikipedia (text of the notes and facts taken from the
articles and their infoboxes):

<!-- wikipedia-infra:start -->
- `data/infrastructure/`, files `fields.geojson`, `mines.geojson`, `pipelines.geojson`, `ports.geojson`,
  `refineries.geojson`, `smelters.geojson` and `storage.geojson`: 182 assets whose source id is `wikipedia`, each with
  the `url` of its article;
- the other infrastructure features whose text names Wikipedia as the origin of a fact (a coordinate, a capacity, an
  opening year, a length, an operator), although their source id is another one: 96 features, covered here by their `id`
  and not edited in the files: `fields.geojson`: `west-qurna`, `stabroek`, `permian-basin`, `marcellus`, `haynesville`,
  `vaca-muerta`, `bakken`; `lng.geojson`: `ras-laffan-lng`, `cove-point-lng`, `yamal-lng`, `brunei-lng`, `eg-lng`,
  `kribi-flng`, `damietta-lng`, `elba-island-lng`, `vysotsk-lng`, `yemen-lng`; `mines.geojson`: `kiruna`, `sishen`,
  `cerrejon`, `elga`, `tavan-tolgoi`, `cerro-verde`, `los-pelambres`, `greenbushes`, `mutanda`, `mcarthur-river`,
  `olympic-dam`, `rocanville`, `belaruskali-soligorsk`, `uralkali-berezniki`, `mountain-pass`, `bayan-obo`, `red-dog`,
  `san-rafael-tin`, `cloudbreak-christmas-creek`, `mount-arthur`, `blackwater-coal`, `fording-river`, `elkview`,
  `inkai`, `akbastau`, `rhenish-lignite-rwe`; `pipelines.geojson`: `power-of-siberia`; `ports.geojson`: `port-hedland`,
  `newcastle`, `gladstone`, `rotterdam`, `basrah-oil-terminal`, `fujairah`, `singapore`, `houston`, `santos`,
  `paranagua`, `vancouver`, `hound-point`, `primorsk`, `kharg-island`, `juaymah`, `zhanjiang`, `taman`, `valdez`,
  `westridge`, `sidi-kerir`, `es-sider`, `ras-lanuf`, `forcados`, `qua-iboe`, `arzew`, `zirku-island`, `jask`,
  `murmansk`, `nederland`, `port-arthur`, `texas-city`, `lake-charles`, `cape-lambert`, `itaguai`, `port-cartier`,
  `ijmuiden`, `qinhuangdao`, `roberts-bank`, `hampton-roads`; `refineries.geojson`: `port-arthur-motiva`,
  `baytown-exxon`, `garyville-mpc`, `galveston-bay-mpc`, `whiting-bp`, `mina-al-ahmadi`, `mina-abdullah`,
  `rabigh-aramco`, `replan-petrobras`, `salina-cruz-pemex`; `smelters.geojson`: `aurubis-hamburg`, `kghm-glogow`,
  `boliden-ronnskar`. Their `url` is the page of their own source; the text of the feature names Wikipedia where a fact
  comes from it;
<!-- wikipedia-infra:end -->
- `data/commodities/companies.json` and `data/freight/shipping-companies.json` (and their sources in
  `pipeline/companies/`): 287 and 28 company entries whose source id is `wikipedia`, each with the `url` of its article;
- the lines of `data/countries/profiles/*.json` whose source id is `wikipedia` (they repeat figures of the files above);
- the events of `data/freight/events.json` and `data/freight/alerts.json` whose `src` is a Wikipedia article;
- `data/freight/vessel-classes.json`: the size ranges, typical ships and notes whose source id is
  `wikipedia-vessel-classes` or `wikipedia` (articles Bulk carrier, Capesize, Valemax, Chinamax, Panamax, Handymax,
  Handysize, Oil tanker, Suezmax, Aframax, Chemical tanker, LNG carrier, Q-Max, Q-Flex, Malaccamax, Container ship);
- `data/freight/chokepoints.json`: the `limits` texts whose `limitsS` is `wikipedia-vessel-classes` (articles Malaccamax,
  Sunda Strait, Lombok Strait, Drogden, Strait of Dover);
- the notes of `data/freight/routes.json` that say they take a fact from a Wikipedia article (Handysize);
- the port tables of `data/freight/lanes/*.json` (the typical ports, transit ports and their notes whose source id is
  `wikipedia`, each with the `url` of its article) and the same ports in `data/freight/pairs/*.json`;
- the matching definition files under `pipeline/freight/` (see "Source code: MIT"), among them the rows of the
  gateway, transit-port, draught and mode tables listed below.

The text was written by Wikipedia contributors and is licensed under the Creative Commons Attribution-ShareAlike 4.0
International licence (<https://creativecommons.org/licenses/by-sa/4.0/>).

**Changes were made.** Passages were shortened and rewritten, figures were taken from the article text and infoboxes
and converted to the atlas's units, coordinates were located or approximated, and the entries were combined with
figures from other sources.

**Credit.** Every Wikipedia-sourced asset and company keeps the `url` of the article it comes from (the data
validators check it); the infrastructure panel links it from the source line of the asset. Every Wikipedia-sourced
port of a lane file keeps the `url` of its article, which the lane page links beside the port. The history tab of each
article lists its authors. Event entries keep the article link in `src`; vessel-class, chokepoint and route notes name
the article in their text. The other infrastructure features listed above keep the `url` of their own source: for them the credit
is this list, the mention of Wikipedia in the feature and the article of the asset (named in the text for five
refineries, otherwise the article under the asset's name), whose history tab lists its authors.

**Share-alike.** The files listed above are shared under CC BY-SA 4.0, with the credit above. A figure in them that
comes from another source keeps its own source id, and that source's terms.

Wikipedia is an accepted source for now; better sources will be looked for later. When a Wikipedia-sourced entry is
replaced by one from another source, it leaves this notice.

### Articles cited by the gateway, transit-port, draught and mode tables

<!-- wikipedia-articles:start -->
The articles below are cited by rows of the trade engine's tables (English Wikipedia unless stated). The list is
  generated from the rows themselves (the `url` of every gateway, transit and manual-port row, the source strings of the
  draught tables, the URL of every mode-list entry) by `pipeline/common/notice_lists.py`, not typed, and
  `pipeline/tests/test_engine.py` checks that it is complete. 197 distinct articles:

- Gateway ports for grain, vegetable oil, fertiliser and general cargo (`pipeline/freight/gateways/food.py`, 71):
  [Apapa](https://en.wikipedia.org/wiki/Apapa); [Aqaba](https://en.wikipedia.org/wiki/Aqaba); [Bandar Imam
  Khomeini](https://en.wikipedia.org/wiki/Bandar_Imam_Khomeini); [Cai Mep](https://en.wikipedia.org/wiki/Cai_Mep);
  [Canpotex](https://en.wikipedia.org/wiki/Canpotex); [Deendayal Port](https://en.wikipedia.org/wiki/Deendayal_Port);
  [Fos-sur-Mer](https://en.wikipedia.org/wiki/Fos-sur-Mer); [Fremantle
  Harbour](https://en.wikipedia.org/wiki/Fremantle_Harbour); [Jebel Ali](https://en.wikipedia.org/wiki/Jebel_Ali); [Jorf
  Lasfar](https://en.wikipedia.org/wiki/Jorf_Lasfar); [King Abdulaziz
  Port](https://en.wikipedia.org/wiki/King_Abdulaziz_Port); [Laem Chabang
  Port](https://en.wikipedia.org/wiki/Laem_Chabang_Port); [Mundra Port](https://en.wikipedia.org/wiki/Mundra_Port);
  [Pasir Gudang](https://en.wikipedia.org/wiki/Pasir_Gudang); [Port Klang](https://en.wikipedia.org/wiki/Port_Klang);
  [Port of Aden](https://en.wikipedia.org/wiki/Port_of_Aden); [Port of
  Alexandria](https://en.wikipedia.org/wiki/Port_of_Alexandria); [Port of
  Bremerhaven](https://en.wikipedia.org/wiki/Port_of_Bremerhaven); [Port of
  Brisbane](https://en.wikipedia.org/wiki/Port_of_Brisbane); [Port of Buenos
  Aires](https://en.wikipedia.org/wiki/Port_of_Buenos_Aires); [Port of
  Busan](https://en.wikipedia.org/wiki/Port_of_Busan); [Port of Callao](https://en.wikipedia.org/wiki/Port_of_Callao);
  [Port of Casablanca](https://en.wikipedia.org/wiki/Port_of_Casablanca); [Port of
  Chittagong](https://en.wikipedia.org/wiki/Port_of_Chittagong); [Port of
  Constanța](https://en.wikipedia.org/wiki/Port_of_Constan%C8%9Ba); [Port of
  Gdańsk](https://en.wikipedia.org/wiki/Port_of_Gda%C5%84sk); [Port of
  Genoa](https://en.wikipedia.org/wiki/Port_of_Genoa); [Port of
  Gothenburg](https://en.wikipedia.org/wiki/Port_of_Gothenburg); [Port of
  Haifa](https://en.wikipedia.org/wiki/Port_of_Haifa); [Port of Hamburg](https://en.wikipedia.org/wiki/Port_of_Hamburg);
  [Port of Hong Kong](https://en.wikipedia.org/wiki/Port_of_Hong_Kong); [Port of
  Houston](https://en.wikipedia.org/wiki/Port_of_Houston); [Port of
  Itaqui](https://en.wikipedia.org/wiki/Port_of_Itaqui); [Port of
  İzmir](https://en.wikipedia.org/wiki/Port_of_%C4%B0zmir); [Port of
  Jeddah](https://en.wikipedia.org/wiki/Port_of_Jeddah); [Port of
  Kaohsiung](https://en.wikipedia.org/wiki/Port_of_Kaohsiung); [Port of
  Karachi](https://en.wikipedia.org/wiki/Port_of_Karachi); [Port of Le
  Havre](https://en.wikipedia.org/wiki/Port_of_Le_Havre); [Port of
  Liverpool](https://en.wikipedia.org/wiki/Port_of_Liverpool); [Port of
  Manila](https://en.wikipedia.org/wiki/Port_of_Manila); [Port of
  Manzanillo](https://en.wikipedia.org/wiki/Port_of_Manzanillo); [Port of
  Mersin](https://en.wikipedia.org/wiki/Port_of_Mersin); [Port of
  Montreal](https://en.wikipedia.org/wiki/Port_of_Montreal); [Port of New
  Orleans](https://en.wikipedia.org/wiki/Port_of_New_Orleans); [Port of
  Novorossiysk](https://en.wikipedia.org/wiki/Port_of_Novorossiysk); [Port of
  Odesa](https://en.wikipedia.org/wiki/Port_of_Odesa); [Port of
  Paranaguá](https://en.wikipedia.org/wiki/Port_of_Paranagu%C3%A1); [Port of
  Ploče](https://en.wikipedia.org/wiki/Port_of_Plo%C4%8De); [Port of Rio
  Grande](https://en.wikipedia.org/wiki/Port_of_Rio_Grande); [Port of
  Rosario](https://en.wikipedia.org/wiki/Port_of_Rosario); [Port of
  Rotterdam](https://en.wikipedia.org/wiki/Port_of_Rotterdam); [Port of
  Santos](https://en.wikipedia.org/wiki/Port_of_Santos); [Port of
  Singapore](https://en.wikipedia.org/wiki/Port_of_Singapore); [Port of
  Sohar](https://en.wikipedia.org/wiki/Port_of_Sohar); [Port of South
  Louisiana](https://en.wikipedia.org/wiki/Port_of_South_Louisiana); [Port of Subic
  Bay](https://en.wikipedia.org/wiki/Port_of_Subic_Bay); [Port of Tampa](https://en.wikipedia.org/wiki/Port_of_Tampa);
  [Port of Tanjung Perak](https://en.wikipedia.org/wiki/Port_of_Tanjung_Perak); [Port of Tanjung
  Priok](https://en.wikipedia.org/wiki/Port_of_Tanjung_Priok); [Port of
  Tianjin](https://en.wikipedia.org/wiki/Port_of_Tianjin); [Port of
  Townsville](https://en.wikipedia.org/wiki/Port_of_Townsville); [Port of
  Ust-Luga](https://en.wikipedia.org/wiki/Port_of_Ust-Luga); [Port of
  Valencia](https://en.wikipedia.org/wiki/Port_of_Valencia); [Port of
  Vancouver](https://en.wikipedia.org/wiki/Port_of_Vancouver); [Port of
  Varna](https://en.wikipedia.org/wiki/Port_of_Varna); [Port of
  Veracruz](https://en.wikipedia.org/wiki/Port_of_Veracruz); [Port of
  Yangon](https://en.wikipedia.org/wiki/Port_of_Yangon); [Port of
  Yokohama](https://en.wikipedia.org/wiki/Port_of_Yokohama); [Grand port maritime de La
  Rochelle](https://fr.wikipedia.org/wiki/Grand_port_maritime_de_La_Rochelle) (French Wikipedia); [Port de
  Nantes-Saint-Nazaire](https://fr.wikipedia.org/wiki/Port_de_Nantes-Saint-Nazaire) (French Wikipedia); [Port de
  Rouen](https://fr.wikipedia.org/wiki/Port_de_Rouen) (French Wikipedia).
- Gateway ports for dry bulk and metals, and the coast rules (`pipeline/freight/gateways/coasts.py`, 57): [Balboa,
  Panama](https://en.wikipedia.org/wiki/Balboa,_Panama); [Barcarena,
  Pará](https://en.wikipedia.org/wiki/Barcarena,_Par%C3%A1); [Caofeidian](https://en.wikipedia.org/wiki/Caofeidian);
  [Cerrejón](https://en.wikipedia.org/wiki/Cerrej%C3%B3n); [Compañía Minera del
  Pacífico](https://en.wikipedia.org/wiki/Compa%C3%B1%C3%ADa_Minera_del_Pac%C3%ADfico); [Corinto,
  Nicaragua](https://en.wikipedia.org/wiki/Corinto,_Nicaragua); [Dhamra
  Port](https://en.wikipedia.org/wiki/Dhamra_Port); [Erdemir](https://en.wikipedia.org/wiki/Erdemir);
  [Europoort](https://en.wikipedia.org/wiki/Europoort); [Grasberg mine](https://en.wikipedia.org/wiki/Grasberg_mine);
  [Hampton Roads](https://en.wikipedia.org/wiki/Hampton_Roads); [Hay Point,
  Queensland](https://en.wikipedia.org/wiki/Hay_Point,_Queensland); [Kalama,
  Washington](https://en.wikipedia.org/wiki/Kalama,_Washington); [Kamsar](https://en.wikipedia.org/wiki/Kamsar);
  [Krishnapatnam Port](https://en.wikipedia.org/wiki/Krishnapatnam_Port);
  [Luleå](https://en.wikipedia.org/wiki/Lule%C3%A5); [Manzanillo International
  Terminal](https://en.wikipedia.org/wiki/Manzanillo_International_Terminal); [Mineral industry of
  Peru](https://en.wikipedia.org/wiki/Mineral_industry_of_Peru); [Moatize](https://en.wikipedia.org/wiki/Moatize);
  [Mormugao Port](https://en.wikipedia.org/wiki/Mormugao_Port); [Mundra
  Port](https://en.wikipedia.org/wiki/Mundra_Port); [Nouadhibou](https://en.wikipedia.org/wiki/Nouadhibou);
  [Novorossiysk](https://en.wikipedia.org/wiki/Novorossiysk); [Pepel](https://en.wikipedia.org/wiki/Pepel); [Ponta da
  Madeira](https://en.wikipedia.org/wiki/Ponta_da_Madeira); [Port Hedland](https://en.wikipedia.org/wiki/Port_Hedland);
  [Port of Alexandria](https://en.wikipedia.org/wiki/Port_of_Alexandria); [Port of
  Baltimore](https://en.wikipedia.org/wiki/Port_of_Baltimore); [Port of
  Gladstone](https://en.wikipedia.org/wiki/Port_of_Gladstone); [Port of
  Guangzhou](https://en.wikipedia.org/wiki/Port_of_Guangzhou); [Port of
  Lianyungang](https://en.wikipedia.org/wiki/Port_of_Lianyungang); [Port of
  Manzanillo](https://en.wikipedia.org/wiki/Port_of_Manzanillo); [Port of
  Mobile](https://en.wikipedia.org/wiki/Port_of_Mobile); [Port of
  Newcastle](https://en.wikipedia.org/wiki/Port_of_Newcastle); [Port of
  Ngqura](https://en.wikipedia.org/wiki/Port_of_Ngqura); [Port of
  Ploče](https://en.wikipedia.org/wiki/Port_of_Plo%C4%8De); [Port of
  Qingdao](https://en.wikipedia.org/wiki/Port_of_Qingdao); [Port of Richards
  Bay](https://en.wikipedia.org/wiki/Port_of_Richards_Bay); [Port of
  Taman](https://en.wikipedia.org/wiki/Port_of_Taman); [Port of
  Townsville](https://en.wikipedia.org/wiki/Port_of_Townsville); [Port of
  Tubarão](https://en.wikipedia.org/wiki/Port_of_Tubar%C3%A3o); [Port Qasim](https://en.wikipedia.org/wiki/Port_Qasim);
  [Primorsk, Leningrad Oblast](https://en.wikipedia.org/wiki/Primorsk,_Leningrad_Oblast); [Puerto
  Cortés](https://en.wikipedia.org/wiki/Puerto_Cort%C3%A9s); [Puerto
  Quetzal](https://en.wikipedia.org/wiki/Puerto_Quetzal); [Rizhao](https://en.wikipedia.org/wiki/Rizhao); [Roberts Bank
  Superport](https://en.wikipedia.org/wiki/Roberts_Bank_Superport); [Saldanha
  Bay](https://en.wikipedia.org/wiki/Saldanha_Bay); [San Juan de
  Marcona](https://en.wikipedia.org/wiki/San_Juan_de_Marcona); [Santo Tomás de
  Castilla](https://en.wikipedia.org/wiki/Santo_Tom%C3%A1s_de_Castilla); [Sept-Îles,
  Quebec](https://en.wikipedia.org/wiki/Sept-%C3%8Eles,_Quebec); [Tanjung
  Bara](https://en.wikipedia.org/wiki/Tanjung_Bara); [Ust-Luga](https://en.wikipedia.org/wiki/Ust-Luga); [Visakhapatnam
  Port](https://en.wikipedia.org/wiki/Visakhapatnam_Port); [Vostochny
  Port](https://en.wikipedia.org/wiki/Vostochny_Port); [Weipa](https://en.wikipedia.org/wiki/Weipa);
  [Wilhelmshaven](https://en.wikipedia.org/wiki/Wilhelmshaven).
- Gateway ports for crude oil, refined products, LPG and LNG, and the transit ports of landlocked countries
  (`pipeline/freight/gateways/energy.py`, 65): [Adria oil pipeline](https://en.wikipedia.org/wiki/Adria_oil_pipeline);
  [Al Başrah Oil Terminal](https://en.wikipedia.org/wiki/Al_Ba%C5%9Frah_Oil_Terminal); [Angra dos
  Reis](https://en.wikipedia.org/wiki/Angra_dos_Reis); [Apapa](https://en.wikipedia.org/wiki/Apapa);
  [Baku–Tbilisi–Ceyhan pipeline](https://en.wikipedia.org/wiki/Baku%E2%80%93Tbilisi%E2%80%93Ceyhan_pipeline); [Cabinda
  (city)](https://en.wikipedia.org/wiki/Cabinda_(city)); [Caspian Pipeline
  Consortium](https://en.wikipedia.org/wiki/Caspian_Pipeline_Consortium);
  [Ceyhan](https://en.wikipedia.org/wiki/Ceyhan); [Chad–Cameroon Petroleum Development and Pipeline
  Project](https://en.wikipedia.org/wiki/Chad%E2%80%93Cameroon_Petroleum_Development_and_Pipeline_Project);
  [Coveñas](https://en.wikipedia.org/wiki/Cove%C3%B1as); [Das Island](https://en.wikipedia.org/wiki/Das_Island); [Dos
  Bocas, Tabasco](https://en.wikipedia.org/wiki/Dos_Bocas,_Tabasco); [Enterprise
  Products](https://en.wikipedia.org/wiki/Enterprise_Products); [Fawley
  Refinery](https://en.wikipedia.org/wiki/Fawley_Refinery); [Grangemouth
  Refinery](https://en.wikipedia.org/wiki/Grangemouth_Refinery); [Greater Nile Oil
  Pipeline](https://en.wikipedia.org/wiki/Greater_Nile_Oil_Pipeline); [Halul
  Island](https://en.wikipedia.org/wiki/Halul_Island); [Irving Oil
  Refinery](https://en.wikipedia.org/wiki/Irving_Oil_Refinery); [Jamnagar
  Refinery](https://en.wikipedia.org/wiki/Jamnagar_Refinery); [Kilindini
  Harbour](https://en.wikipedia.org/wiki/Kilindini_Harbour); [Kralendijk](https://en.wikipedia.org/wiki/Kralendijk);
  [Kurnell Refinery](https://en.wikipedia.org/wiki/Kurnell_Refinery); [List of LNG
  terminals](https://en.wikipedia.org/wiki/List_of_LNG_terminals); [List of oil
  refineries](https://en.wikipedia.org/wiki/List_of_oil_refineries); [Mina Al
  Fahal](https://en.wikipedia.org/wiki/Mina_Al_Fahal); [Mongstad](https://en.wikipedia.org/wiki/Mongstad);
  [Naftoport](https://en.wikipedia.org/wiki/Naftoport); [Nueva Palmira](https://en.wikipedia.org/wiki/Nueva_Palmira);
  [Paradip Port](https://en.wikipedia.org/wiki/Paradip_Port); [Pengerang](https://en.wikipedia.org/wiki/Pengerang);
  [Petroleum industry in Nigeria](https://en.wikipedia.org/wiki/Petroleum_industry_in_Nigeria); [Port of
  Beira](https://en.wikipedia.org/wiki/Port_of_Beira); [Port of Chiba](https://en.wikipedia.org/wiki/Port_of_Chiba);
  [Port of Constanța](https://en.wikipedia.org/wiki/Port_of_Constan%C8%9Ba); [Port of Corpus
  Christi](https://en.wikipedia.org/wiki/Port_of_Corpus_Christi); [Port of Dar es
  Salaam](https://en.wikipedia.org/wiki/Port_of_Dar_es_Salaam); [Port of
  Djibouti](https://en.wikipedia.org/wiki/Port_of_Djibouti); [Port of
  Fujairah](https://en.wikipedia.org/wiki/Port_of_Fujairah); [Port of
  Hamburg](https://en.wikipedia.org/wiki/Port_of_Hamburg); [Port of
  Kolkata](https://en.wikipedia.org/wiki/Port_of_Kolkata); [Port of Koper](https://en.wikipedia.org/wiki/Port_of_Koper);
  [Port of Le Havre](https://en.wikipedia.org/wiki/Port_of_Le_Havre); [Port of
  Melbourne](https://en.wikipedia.org/wiki/Port_of_Melbourne); [Port of
  Mersin](https://en.wikipedia.org/wiki/Port_of_Mersin); [Port of
  Nakhodka](https://en.wikipedia.org/wiki/Port_of_Nakhodka); [Port of
  Ningbo-Zhoushan](https://en.wikipedia.org/wiki/Port_of_Ningbo-Zhoushan); [Port of
  Ploče](https://en.wikipedia.org/wiki/Port_of_Plo%C4%8De); [Port of
  Primorsk](https://en.wikipedia.org/wiki/Port_of_Primorsk); [Port of
  Singapore](https://en.wikipedia.org/wiki/Port_of_Singapore); [Port of Tanjung
  Priok](https://en.wikipedia.org/wiki/Port_of_Tanjung_Priok); [Puerto
  José](https://en.wikipedia.org/wiki/Puerto_Jos%C3%A9); [Ras Lanuf](https://en.wikipedia.org/wiki/Ras_Lanuf); [Ras
  Tanura](https://en.wikipedia.org/wiki/Ras_Tanura); [Rotterdam](https://en.wikipedia.org/wiki/Rotterdam);
  [Ruwais](https://en.wikipedia.org/wiki/Ruwais); [Sullom Voe
  Terminal](https://en.wikipedia.org/wiki/Sullom_Voe_Terminal); [Trans-Panama
  Pipeline](https://en.wikipedia.org/wiki/Trans-Panama_Pipeline); [Transalpine
  Pipeline](https://en.wikipedia.org/wiki/Transalpine_Pipeline); [Transport in Burkina
  Faso](https://en.wikipedia.org/wiki/Transport_in_Burkina_Faso); [Transport in
  Mali](https://en.wikipedia.org/wiki/Transport_in_Mali); [Transport in
  Niger](https://en.wikipedia.org/wiki/Transport_in_Niger); [Vadinar](https://en.wikipedia.org/wiki/Vadinar); [Walvis
  Bay](https://en.wikipedia.org/wiki/Walvis_Bay); [Wilhelmshaven](https://en.wikipedia.org/wiki/Wilhelmshaven);
  [Yanbu](https://en.wikipedia.org/wiki/Yanbu).
- Draught limits of straits and laden draughts of vessel classes (the draught rule) (`pipeline/freight/vessel_rules.py`,
  7): [Capesize](https://en.wikipedia.org/wiki/Capesize); [Handysize](https://en.wikipedia.org/wiki/Handysize);
  [Malaccamax](https://en.wikipedia.org/wiki/Malaccamax); [Singapore
  Strait](https://en.wikipedia.org/wiki/Singapore_Strait); [Sunda Strait](https://en.wikipedia.org/wiki/Sunda_Strait);
  [Torres Strait](https://en.wikipedia.org/wiki/Torres_Strait); [Valemax](https://en.wikipedia.org/wiki/Valemax).
- Sea, transit, mixed and land rules (sea neighbours, sea outlets, overland blocs, LNG terminals)
  (`pipeline/freight/modes.py`, 12): [Baku–Tbilisi–Ceyhan
  pipeline](https://en.wikipedia.org/wiki/Baku%E2%80%93Tbilisi%E2%80%93Ceyhan_pipeline);
  [Belaruskali](https://en.wikipedia.org/wiki/Belaruskali); [Caspian Pipeline
  Consortium](https://en.wikipedia.org/wiki/Caspian_Pipeline_Consortium); [China–India
  border](https://en.wikipedia.org/wiki/China%E2%80%93India_border); [Eastern Siberia–Pacific Ocean oil
  pipeline](https://en.wikipedia.org/wiki/Eastern_Siberia%E2%80%93Pacific_Ocean_oil_pipeline); [India–Bangladesh
  Friendship Pipeline](https://en.wikipedia.org/wiki/India%E2%80%93Bangladesh_Friendship_Pipeline); [List of LNG
  terminals](https://en.wikipedia.org/wiki/List_of_LNG_terminals); [Paraná–Paraguay
  Waterway](https://en.wikipedia.org/wiki/Paran%C3%A1%E2%80%93Paraguay_Waterway); [Russian
  gauge](https://en.wikipedia.org/wiki/Russian_gauge); [Sasol](https://en.wikipedia.org/wiki/Sasol); [TAZARA
  Railway](https://en.wikipedia.org/wiki/TAZARA_Railway); [Trans Mountain
  pipeline](https://en.wikipedia.org/wiki/Trans_Mountain_pipeline).
- Passages closed to the routing (Kanmon Strait) (`pipeline/freight/routing.py`, 1):
  [関門海峡](https://ja.wikipedia.org/wiki/%E9%96%A2%E9%96%80%E6%B5%B7%E5%B3%A1) (Japanese Wikipedia).
- River legs of the ports up a river that the sea network does not follow (Rouen, Bremen)
  (`pipeline/freight/river_legs.py`, 2): [Weser](https://en.wikipedia.org/wiki/Weser); [Port de
  Rouen](https://fr.wikipedia.org/wiki/Port_de_Rouen) (French Wikipedia).
<!-- wikipedia-articles:end -->

## Points taken from OpenStreetMap: ODbL 1.0

<!-- osm-points:start -->
The coordinates of 207 assets of the infrastructure layer were looked up in OpenStreetMap (through its Nominatim search)
  and the note of each feature says so: in `data/infrastructure/`, in `fields.geojson`, Ku-Maloob-Zaap and South Pars;
  in `lng.geojson`, Alexandroupolis FSRU, Altamira FLNG, Altamira LNG Terminal, Bahia Blanca GasPort, Canaport LNG,
  Cartagena LNG Terminal, Chita LNG Terminal, Damietta LNG, Donggi-Senoro LNG, Energia Costa Azul LNG,
  Engro Port Qasim terminal, Escobar LNG, FGEN Batangas LNG, GNL Quintero, Guanabara Bay LNG,
  Higashi-Ohgishima LNG Terminal, Jurong Island LNG Terminal, Kochi LNG Terminal, Krk LNG Terminal,
  Map Ta Phut LNG Terminal 1, Mundra LNG Terminal, Ningbo LNG Terminal, Nusantara Regas Satu FSRU, OLT Toscana,
  Panigaglia LNG Terminal, Pecem LNG Terminal, Portovaya LNG, Port Qasim GasPort, Qingdao LNG Terminal,
  Revithoussa LNG Terminal, Rovigo LNG Terminal, Sergipe LNG and Zhuhai LNG Terminal; in `mines.geojson`, Abu Tartur,
  Ahafo, Aktogay, Allan, Almalyk mines, Al Jalamid, Ambatovy, Anning phosphate mines, Antapaccay, Batu Hijau, Bayóvar,
  Belle Plaine, Blackwater, Bloom Lake, Boddington-Worsley bauxite mine, Boké bauxite mine, Borneo Indobara, Bozshakol,
  Buenavista del Cobre, Cadia Valley, Canadian Malartic, Cannington, Cory, Dead Sea Works, Dexing, Dugald River, Débélé,
  Elkview, Erdenet, Esterhazy, Fording River, Fresnillo mine, Gejiu, Gol Gohar mines, Huize, Hunter Valley Operations,
  Husab, Inhulets mine, Jinchuan nickel-copper mine, Jordan Phosphate Mines, K+S potash mines, KATCO, Kaltim Prima Coal,
  Karatau, Ketapang bauxite mines, Khibiny apatite mines, Kideco, Langer Heinrich, Lanigan, Las Bambas, La Loma,
  Lebedinsky, Lovozero rare-earth mines, Majdanpek, McArthur River, Minas-Rio, Moanda, Moatize, Moa Nickel, Mogalakwena,
  Mont-Wright and Fire Lake, Moolarben, Mount Isa mines, Mount Marion, Mount Tom Price, Murrin Murrin, Nsuta-Wassaw,
  PT Timah mines, Pannawonica, Paragominas, Peñasquito, Pitinga, Poltava GOK, Porto Trombetas, Qarhan salt lake,
  Rampura Agucha, Ramu NiCo, Renison Bell, Rio Tuba, Roan Tailings Retreatment, Rössing, SOMAIR,
  Salar del Hombre Muerto, Salar de Olaroz, Salobo, Sangaredi, Sicomines, Sorowako mine, Tabang mine, Taganito mine,
  Tianshan Uranium, Toquepala, Tshipi Borwa, Vale Ontario operations, Vanscoy, Voisey's Bay, Weda Bay, West Angelas,
  Wodgina, Yanacocha and Yichun lithium mines; in `pipelines.geojson`, Enbridge Mainline and
  Goreh-Jask crude oil pipeline; in `ports.geojson`, CPC terminal, Caofeidian, Dongying, Es Sider, Forcados terminal,
  Halul Island, Lavera, Majishan, Mamonal, Mina al-Fahal, Pozos Colorados, Qua Iboe terminal, Roberts Bank, San Lorenzo,
  Seria, Skikda, Tubay, Vadinar, Valdez Marine Terminal and Westridge Marine Terminal; in `refineries.geojson`,
  Balikpapan, Baton Rouge, Chiba, Daesan, Deer Park, Fawley, Isfahan, Mizushima, Negishi, Yokohama, Olmeca, Pascagoula,
  Pengerang, Persian Gulf Star, Priolo, Rotterdam, SATORP, Jubail, STAR, Salina Cruz, Schwedt, Sitra, Szazhalombatta and
  Zhenhai; in `smelters.geojson`, Albras smelter, Alouette smelter, Balkhash copper smelter and refinery,
  Birla Copper smelter, Bor smelter and refinery, Caletones smelter, Chanderiya smelter, Hindalco Aditya smelter,
  Hydro aluminium smelters, Ilo smelter and refinery, Inalum Kuala Tanjung smelter,
  Kazzinc Ust-Kamenogorsk metallurgical complex, Kitimat smelter, Ma'aden Aluminium smelter, Mentok smelter,
  Met-Mex Peñoles refinery, NALCO Angul smelter, Port Pirie smelter, Ridder zinc refinery,
  Sayanogorsk aluminium smelter, Sorowako smelter, Tomago smelter, Tongling smelter and refinery,
  Trail smelter and refinery and Vedanta Jharsuguda smelter; in `storage.geojson`, Cushing and Mont Belvieu. Only a
  single point per asset is taken; no other OpenStreetMap data is used.
<!-- osm-points:end -->

Credit: **© OpenStreetMap contributors**. The data is available under the Open Database License 1.0
(<https://www.openstreetmap.org/copyright>). Source id `openstreetmap` in `data/sources.json`.

## Third-party datasets

Each dataset keeps the licence of its source. The credits the sources ask for:

- **CEPII BACI**: Etalab Open Licence 2.0. Gaulier, G. and Zignago, S. (2010) BACI: International Trade Database at
  the Product-Level. The 1994-2007 Version. CEPII Working Paper N°2010-23. The atlas filters and cleans the data
  (METHODOLOGY.md, section 1); it does not republish the database.
- **Natural Earth** (basemap, country names, and the names of oceans, seas, bays and gulfs): the countries 1:50m and the
  marine areas 1:50m (version 5.1.0, used for the names and positions of oceans, seas, bays and gulfs on the map). Its terms of use
  (<https://www.naturalearthdata.com/about/terms-of-use/>, read 25 November 2026) say: "All versions of Natural Earth raster + vector map data
  found on this website are in the public domain. You may use the maps in any manner, including modifying the content and design, electronic
  dissemination, and offset printing." and "No permission is needed to use Natural Earth. Crediting the authors is unnecessary." "Made with
  Natural Earth" is shown as a courtesy. The same page (<https://www.naturalearthdata.com/about/terms-of-use/>, read 25 November 2026) also
  reproduces four third-party releases, each licensed to Natural Earth "for the sole purpose of creating a world base map": the page names a
  theme for three of them (rivers and lakes of Europe, roads of North America, time zones) and none for the first, "The authors used data from
  The Washington Post, here is their release:". On the same page (<https://www.naturalearthdata.com/about/terms-of-use/>, read 25 November
  2026): "The authors’ used name data for more than 20 languages from Wikidata which is under a CC0 (public domain) license."; the names of the
  seas, bays and gulfs take the `name_en` attribute of the marine areas file (the oceans take `name`), and the page does not say which attributes
  these name data fill. The footer of the page (<https://www.naturalearthdata.com/about/terms-of-use/>, read 25 November 2026), after its
  copyright line "© 2009 - 2026. Natural Earth.", reads "All rights reserved."; the page says of its downloads (<https://www.naturalearthdata.com/about/terms-of-use/>,
  read 25 November 2026): "Our data downloads are generously hosted by Amazon Web Services since 2021 and previously Florida State
  University." The atlas's copy of the marine areas zip was fetched from naciscdn.org, an address that the page does not name. The README of the marine areas zip (offered at
  <https://www.naturalearthdata.com/downloads/50m-physical-vectors/>, read 25 November 2026) says: "The boundaries of physical regions should be
  taken with a grain of salt." The country shapes are the default view of version 5.1.1; what that means for the map is in METHODOLOGY.md,
  "The map: boundaries and territories".
- **Place-name font** (the lettering of the names on the map): Inter Medium, SIL Open Font License 1.1, from the Debian package `fonts-inter`
  4.0+ds-1 (file `Inter-Medium.otf`, version "Version 4.000;git-a52131595", read with the `fontkit` library). The font file's own copyright line is
  "Copyright 2016 The Inter Project Authors", and its licence string is "This Font Software is licensed under the SIL Open Font License, Version 1.1.
  This license is available with a FAQ at: http://scripts.sil.org/OFL"; it declares no Reserved Font Name and carries the line "Inter UI and Inter is a
  trademark of rsms." The file `web/public/glyphs/inter-medium/0-255.pbf` is a Modified Version of it (a change of format: 24 px signed-distance
  bitmaps of the characters the map writes; the outlines are unchanged) and carries the licence text next to it, in
  `web/public/glyphs/inter-medium/LICENSE.txt`. The font software stays entirely under the SIL Open Font License (`THIRD-PARTY-NOTICES.md` has the text);
  the repository's MIT licence does not apply to it. The interface itself is set in Inter Tight (see `THIRD-PARTY-NOTICES.md`).
- **World Bank Pink Sheet**, **FAOSTAT**: CC BY 4.0. FAOSTAT is also subject to the FAO statistical database terms of
  use (no endorsement by FAO, no promotion of a commercial product).
- **U.S. Energy Information Administration, USGS, USDA**: U.S. Government publications, public domain; EIA asks for an
  acknowledgment ("Source: U.S. Energy Information Administration"). The EIA material used includes the International
  Energy Data, the country analysis briefs (refinery towns and ports of entry of the gateway tables, the Saudi coast
  rule), the company-level crude and products imports, the refinery capacity report and the natural gas data.
  The EIA's daily spot prices (Brent, WTI, Henry Hub and the five other series of the price drawer) are not covered by this line:
  the EIA's pages give Refinitiv, an LSEG business, as their source, and no page read says whether they may be redistributed. The
  eight series are published in full in `data/prices/*-d.json`, which the charts read. They are shown with the credit "EIA (source:
  Refinitiv)" on the commodity pages, the price drawer and the price board, and as a few figures of the weekly digest and its feed.
  No button offers a CSV file or a copy of them, and no text of the atlas calls them public domain. The owner decided on 25 November
  2026 to keep them, saying where they come from. Terms to be confirmed; the pages read, with their quotations, are in the registry
  entry `eia-spot` and in DATA_SOURCES.md.
- **Queensland Government** (the Metallurgical coal page): the dataset "Quarterly coal reports", workbook "Quarterly Coal Sales" (exports by country and
  by port), CC BY 4.0. Credit as the workbook gives it: "Source: Department of Natural Resources and Mines, Manufacturing and Regional and Rural
  Development (NRMMRRD)". The workbook reads "Data through to 30 June 2026" and "Current as at October 2026", and says that the data may be revised and
  that "Derived conclusions and analysis generated from this data are not to be considered attributable to the Department": the figures of the page are the
  atlas's sums of its quarters. The workbook is downloaded by hand (the site refuses scripts) and is not refreshed by the scheduled updates.
- **EIA coal exports** (the Metallurgical coal page): the bulk file COAL.zip (exports by rank, destination and customs district; underlying source: U.S.
  Census Bureau, Monthly Report EM 545), public domain. "Source: U.S. Energy Information Administration", file dated 1 October 2026.
- **Department of Industry, Science and Resources, Commonwealth of Australia** (the LNG page): table 41 of the historical data workbook of the Resources and Energy
  Quarterly, December 2025, CC BY 4.0 as the About sheet of the workbook states. Credit as the department asks: "Department of Industry, Science, and
  Resources, Commonwealth of Australia Resources and Energy Quarterly, December 2025." The workbook is downloaded by hand (the site refuses scripts) and is not
  refreshed by the scheduled updates.
- **UN Comtrade** (the tin page, and the flow of tin ores from Myanmar to China): China's imports of tin ores and concentrates (HS 260900), read from the public
  preview of the service. Credit: "Source: UN Comtrade." UN Comtrade's policy on re-dissemination allows the publication of limited amounts of its data in a few
  tables, graphs and visualisations without permission; the atlas prints a few figures with that credit and publishes none of the answers as a file.
- **US Census Bureau** (the LPG page): the USA Trade Online export detail file (EXDB, December 2024), for the quantity and the vessel shipping weight of LPG
  exports to Mexico, Canada and three Asian buyers. The Census Bureau's Public-Use Statement (https://www.census.gov/about/policies/citation.html, page last revised
  24 February 2026) says that "Data users who create their own estimates using data from disseminated tables and other data should cite the Census Bureau as the source of the
  original data only." The site publishes no row of the file and offers none for download: it prints an estimate of its own made from the data, citing the Census Bureau as the source of the original data, and a few totals of the file by product and country (quantity, weight by vessel), each credited to the Census Bureau, and the repository keeps a small cache of those totals; the pages
  read state no copyright and no public domain. The figures derived from it are the atlas's and are not endorsed or certified by the Census Bureau. EIA's exports by destination (propane and butanes, public domain) give the volumes of the years before.
- **Wikidata** (points of a few assets): CC0 1.0, no credit required.
- **Australian Bureau of Statistics** (the article on Australian lithium exports cited on the lithium page): CC BY 4.0.
- **U.S. Bureau of Labor Statistics**: the deep-sea freight producer price index (series PCU483111483111), public domain
  with citation requested ("Public Domain: Citation Requested" on FRED's page of the series). It is fetched from the BLS
  API. Until the BLS has returned every year, the older years are the copy the atlas took earlier through the FRED API
  (the note of the series names them), which is not endorsed or certified by the Federal Reserve Bank of St. Louis.
- **Federal Reserve Bank of Dallas**: Index of global real economic activity (Kilian 2009, 2019), reproduced under the
  Bank's terms of use ("may be made without limitation as to quantity, provided it is not distributed for the purpose
  of private gain and is appropriately credited to the Bank"). The "Freight market now" page prints it with the Bank's credit, the citation the Bank's page of the index gives
  (Kilian 2009, with the correction discussed in Kilian 2019) and the Bank's own words that the index "may be viewed as a proxy for the volume of shipping in global industrial
  commodity markets" (https://www.dallasfed.org/research/igrea, read 25 November 2026), and says that it is not a freight rate.
- **Federal Reserve Bank of New York**: Federal Reserve Bank of New York, Global Supply Chain Pressure Index,
  https://www.newyorkfed.org/research/policy/gscpi. Content from the New York Fed subject to the Terms of Use at
  newyorkfed.org. The GSCPI is not an official estimate of the Federal Reserve Bank of New York, its President, the
  Federal Reserve System, or the Federal Open Market Committee.
- **World Port Index (Pub. 150), US National Geospatial-Intelligence Agency (NGA)** (the "World Port Index" block of the port
  pages): depths, maximum vessel size, harbour size and type, tidal range and pilotage of the entry that matches a port, shown
  with the publication's name, the entry's name and number and a link. A person took the CSV (UpdatedPub150.csv) on 24 November 2026 from the Internet Archive's copy, captured on 29 September 2026,
  of the publisher's download address
  (<https://web.archive.org/web/20260929232408id_/https://msi.nga.mil/api/publications/download?type=view&key=16920959%2FSFH00000%2FUpdatedPub150.csv>),
  the publisher's page being <https://msi.nga.mil/Publications/WPI>; the repository keeps 23 of its 109 columns, for 138 ports, in
  `pipeline/cache/wpi_ports.csv` and `data/infrastructure/wpi.json`, and offers no file of the figures for download. Terms of
  the file used: not read; the file is an archived copy, and no terms of the Internet Archive's own for it were read (none is
  claimed). The publisher's site was in maintenance on 24 and 25 November 2026 and its page of the publication
  holds no text in the archived copies; the edition of the file is not stated and the file holds no date inside it (terms to be
  confirmed). What was read is the
  title page of the twenty-sixth edition (2017) of the publication, "© COPYRIGHT 2017 BY THE UNITED STATES GOVERNMENT / NO
  COPYRIGHT CLAIMED UNDER TITLE 17 U.S.C." (archived PDF,
  <https://web.archive.org/web/20170829062601if_/http://msi.nga.mil/MSISiteContent/StaticFiles/NAV_PUBS/WPI/Pub150bk.pdf>,
  read 25 November 2026). That is a statement on that edition and not on the file used, and the atlas draws no conclusion
  from it about the file. The server's disclaimers, read in an archived copy of its page
  (<https://web.archive.org/web/20190721092351/https://msi.nga.mil/NGAPortal/MSI.portal?_nfpb=true&_st=&_pageLabel=msi_portal_page_148>,
  capture of 21 July 2019, read 25 November 2026), say: "neither the United States Government nor the National
  Geospatial-Intelligence Agency Agency nor any of their employees, makes any warranty, express or implied, including the
  warranties of merchantability and fitness for a particular purpose, or assumes any legal liability or responsibility for the
  accuracy, completeness, or usefulness of any information"; "does not necessarily constitute or imply its endorsement,
  recommendation, or favoring by the United States Government or the National Geospatial-Intelligence Agency"; and "Federal
  law prohibits the use of the National Geospatial-Intelligence Agency's name, seal, initials, or any colorable imitation
  thereof, to convey the impression of commercial endorsement by the Secretary of Defense, without written permission from the
  Secretary of Defense." The atlas gives no warranty on these figures either, and they are not for navigation; they are not
  endorsed by NGA or by the United States Government, and the atlas uses neither NGA's seal nor its name to suggest otherwise
  (its name only names the publisher).
- **SeaRoute**: the `searoute` Python package is under Apache 2.0; the maritime network of Eurostat's SeaRoute is
  under EUPL 1.2.

The use of data from the U.S. Bureau of Labor Statistics, the IMF, the FAO or any other publisher does not mean that
they endorse the atlas.

## Cited, not redistributed

Some third-party material is cited rather than copied. For each, the position the atlas takes; the owner can change a
verdict (redistribute, cite a few facts, link only).

| Source | Position |
|---|---|
| IMF PortWatch | Only the atlas's own weekly averages and comparisons are published, with credit (and, for the ports, weekly sums, see below); the daily rows are a working file kept out of git. The identity and position of about 2,000 ports (ports database) are kept and used with credit. See below. |
| Baltic Exchange route names and definitions | Names and codes of the benchmark routes and their public definitions are used as facts. No index value or rate is shown. Not affiliated with the Baltic Exchange. |
| Shanghai Shipping Exchange indices | Two index pages are linked from the "Freight market now" page; no value is stored or shown. The only statement read on its pages is the footer "All Rights Reserved". See below. |
| USDA Agricultural Marketing Service (weekly port region grain ocean vessel activity, grain ocean freight rates) | The datasets page is linked from the "Freight market now" page; no value is stored or shown. The sentences read are quoted below. |
| GIIGNL and other association reports | A few cited figures with attribution. No table, text or file is redistributed. |
| World Steel Association, World Gold Council, International Cocoa Organization, International Gas Union | One world total each (crude steel production, gold mine production, cocoa bean production, LNG trade), with publisher, year and link, beside the atlas's own table. Their tables are not copied. |
| Natural Resources Canada (conversion factors), Wilhelmsen (LPG carrier sizes) | A conversion factor and a size band, cited with attribution. Reuse terms to be confirmed. |
| Norwegian Offshore Directorate (FactMaps) | The outline and status of two fields, cited with attribution. Its licence page could not be read: terms not read. |
| Cochilco (Chilean copper export tables) | Used only to check the atlas's estimate of Chilean copper concentrate (METHODOLOGY.md, section 1); none of its figures is published. Licence not confirmed. |
| Press reports (Bloomberg via gCaptain, Cyprus Mail, GMK Center and others) | Short facts with a link to the article. No article text is copied. |
| Panama Canal Authority, Suez Canal Authority, port authorities | Published statistics and transit limits are cited as facts with attribution. No licence is stated on the pages; terms to be confirmed. Their toll tariffs are linked from the voyage calculator of the route pages and not copied (see below). |
| Company reports | Facts cited with a link to the report. |
| World Nuclear Association | Annual uranium production figures cited with attribution. Terms to be confirmed. |

### IMF PortWatch

Credit line: **IMF PortWatch (IMF and University of Oxford), data adapted.**

What the atlas publishes: weekly averages of PortWatch's daily counts of chokepoint transits and of its estimates of the
trade volume carried, a 28-day average, and the comparisons built from them (the last 28 days against the same days a
year earlier and against the 2023 average, on the alert banners and in the "What changed" digest). They are a
transformation of the daily data, and are described as such in `data/sources.json` and METHODOLOGY.md: "Atlas weekly
averages of IMF PortWatch daily counts". Nothing else leaves the atlas: the daily rows are not in the repository.

Freight market now. The page of that name and its file, `data/freight/market-now.json`, add one more transformation of the same weekly
averages, built each week by the PortWatch job from the weekly files already published, with no request to PortWatch or to any other site.
What it publishes, for tankers and for dry bulk carriers at five passages each: the vessel transits and PortWatch's estimate of the cargo over the last
four complete weeks (28 days) and over the same four weeks a year earlier, and the change between them. The transformation, stated as the IMF's terms
ask: the weekly means of the atlas's weekly series (vessels a day, one decimal; Mt a day) are multiplied by 7 and added over the four weeks, as whole
vessels and to three significant figures; the change between the two windows is computed on those sums before that rounding and stored to one decimal; the five passages of each ship type are the five with the most estimated cargo of that type over the 52 weeks that end
with the year-earlier window, ranked on the sum before rounding, a rule of the atlas and not of PortWatch; a ship that crosses several passages is counted at each of them, and no total is made. The ship classes are
PortWatch's own: the description of its item "Daily_Chokepoints_Data" that the atlas read lists five (container, dry bulk, general cargo, ro-ro and tanker) and does not say what each holds, so the atlas does not say whether gas carriers
are among the tankers and shows no gas carrier figure. The credit line is the one above, **IMF PortWatch (IMF and University of Oxford), data adapted**, and each list of the page
carries it in the registry's name of the source with the dates of the two windows. The owner's decision of 25 November 2026 quoted below
concerns how PortWatch is read; this page adds no reading of it. The CC BY 4.0 release does not extend IMF's rights to these figures either. The method is in METHODOLOGY.md,
section 5, "Freight market now".

What the atlas keeps and does not publish: the verbatim daily table (about 80,000 rows, fifteen fields of the PortWatch
table) is a working file, `pipeline/cache/portwatch/daily_<year>.csv.gz`, ignored by git. It is there so that each weekly
run asks the service only for the days after the last one stored. On GitHub the weekly workflow keeps it between runs as
the workflow artifact `portwatch-daily` (90 days; the next run restores it, or downloads the whole table when there is
none). The artifact is not a publication of the atlas and the CC BY 4.0 release does not cover it; like every artifact of a
public repository it can be downloaded from the Actions tab by a signed-in GitHub user, and the IMF conditions below apply
to it.

Terms, as read on 22 November 2026: the PortWatch dataset (ArcGIS item "Daily_Chokepoints_Data") points to the IMF
terms of use (<https://www.imf.org/external/terms.htm>). The IMF's "Special Terms for Statistical Data"
(<https://www.imf.org/en/About/Copyright-and-Terms>) allow users to download, copy, create derivative works and
distribute IMF statistical data with attribution to the IMF as the source and an explicit statement of any
transformation, without altering the nature or accuracy of the data; commercial reuse needs IMF permission
(copyright@imf.org). No Creative Commons licence is stated by PortWatch or the IMF: the atlas registry no longer says
"CC BY 4.0". PortWatch's own page on data and methodology shows no licence text. PortWatch is built from vessel
tracking signals; the atlas shows only aggregated counts and volumes, never a position or a track.

Read again on 25 November 2026, the same page defines the statistical data of these special terms as "published
statistical data produced or curated by the IMF", with a list of examples that does not name PortWatch: the atlas
takes PortWatch's tables to be such data, which no page read says in so many words. The page also says: "The IMF
prohibits bulk download of information by automated technology without explicit permission and reserves the right to
terminate access to its Sites or Content.", and lists "Copying or downloading IMF Content in any systematic way" among
the uses that need the IMF's written permission; no page read says whether PortWatch's public data service comes with
such a permission. The owner's decision of 25 November 2026: the atlas keeps reading PortWatch as a person would, in
small pieces, one request at a time and slowly, and credits IMF PortWatch (the credit line of this section). How the
update script reads that decision: once a week it asks for one page (the days since the last one stored and the 14 days
before it, which PortWatch may revise); when it has to read more (the whole chokepoint table, about 41 pages, when it
has no working table or once every four weeks) it waits 8 to 14 seconds between two pages; and no request, one repeated
after an error included, starts less than 8 seconds after the one before. The figures in seconds are the script's, not
the owner's.

The CC BY 4.0 release of the atlas's own figures does not extend IMF's rights: the weekly averages stay subject to
the IMF conditions above.

Port traffic. For the ports of the infrastructure layer that have a PortWatch port, the atlas builds a weekly series from
PortWatch's daily table of port calls and estimated trade volumes (ArcGIS item "Daily_Ports_Data", registry id
`portwatch-port-traffic`; the licence field of the item points to the same IMF terms of use as the two other PortWatch items,
read in the item's metadata on 25 November 2026). What the atlas publishes of it, in `data/freight/port-traffic/` (one file
per PortWatch port, written by the series' first load, made by hand in small sittings, and then kept up to date by the weekly step of the PortWatch job; the "Weekly port traffic" block of the page of each port that has a file shows them): the weekly sums, Monday to Sunday and complete weeks only, of the
daily port calls and of PortWatch's estimated import and export tonnes, by ship type (tanker, dry bulk, container, and other,
which is general cargo and ro-ro together). Credit line: **IMF PortWatch (IMF and University of Oxford), data adapted**; the
item's own recommended citation is "Sources: UN Global Platform; IMF PortWatch (portwatch.imf.org)" (the UN Global Platform
supplies the ship signals: nothing of it is taken). The transformation, stated as the IMF's terms ask: the daily figures are
added into weeks; the atlas adds the ship types itself and does not use the table's own total columns; the tonnes are rounded
to the unit each file states; and the tonnes are PortWatch's estimate, made from each ship's dimensions and draught on
entering and leaving the port boundary, not a customs or port-authority statistic. On the page of a port the block names PortWatch's own port, calls the tonnes PortWatch's estimates,
and shows no figure of the port's own beside them. What the atlas does not publish or keep:
no daily row, no vessel, no position or track, no time finer than a day. No row of the table is kept in the repository (no
file under `pipeline/cache/`, nothing under `raw/`) or as a workflow artifact: the published weekly files are the only state
that the weekly step reads back. Pace: the same as for the chokepoint table, one request at a time with a pause of 8 to 14
seconds before the next (the script's reading of the owner's rule of 25 November 2026, not his figure), the first load in
small sittings; the weekly step, which runs after the chokepoint step of the same job on Wednesdays, reads only recent weeks of the ports and a longer stretch of a part of them in turn, and waits one such pause before its first request, because the
chokepoint step asks the same host from another process; the counts of requests are those of the script and of `docs/UPDATING.md`. The terms are those quoted above, with the same two
open points (PortWatch is not named among the page's examples of statistical data; the sentence on bulk download), which
now cover the chokepoint series, the ports database and the port series alike. The CSV of a port series is offered as the CSV
of a chokepoint series is, with its source and licence columns, because the registry licence text of the three PortWatch
entries opens with the same words: a choice made without the owner, listed in PROGRESS.md (he was asked how PortWatch is read
by script, not about the CSV).

Ports database. The ports of the infrastructure layer take their position and UN/LOCODE from the PortWatch ports
database (ArcGIS item "Ports", PortWatch_ports_database), whose licence field points to the same IMF terms of use as
the chokepoint tables (read on 23 November 2026). The atlas keeps the identity of each port (PortWatch port id, name,
country, UN/LOCODE, position and page id) in `pipeline/cache/portwatch_ports.csv`, published in the repository with
this credit; a port asset whose cited page is its PortWatch page links to it, the others cite another page. No vessel count or traffic figure of the database is
kept or shown. Credit line: **IMF PortWatch (IMF and University of Oxford), ports database, data adapted.**

### Baltic Exchange

The atlas is not affiliated with, sponsored by or endorsed by the Baltic Exchange. Benchmark route codes (for example
C3, TD3C, BLNG1), their definitions and the standard vessels are taken from the Baltic Exchange's Guide to Market
Benchmarks (version 7.09, December 2025), its service pages and its circulars, stated as facts in the atlas's own
words; the pages read are listed in `pipeline/freight/NOTES_routes.md`. The Baltic
indices and rate assessments are proprietary and are not shown.

The voyage calculator of the route pages computes, in the visitor's browser, with the speed and fuel of the standard vessels
that the class pages already state, on figures the visitor types. The atlas stores and publishes no figure derived from them,
and what the calculator gives is not a Baltic Exchange value. This is a new use of figures already on the site, and a choice made
without the owner, listed in PROGRESS.md. What the Baltic Exchange's pages say, read on 25 November 2026:

- Terms and Conditions, clause 5.1 (https://www.balticexchange.com/en/site-services/terms-and-conditions.html): no part of the
  website or its content "may be copied or reproduced (except for your personal use), shared with third parties, reverse
  engineered, reverse assembled, or used to create any derivative work (whether in physical or electronic form) without the
  prior written consent of the Baltic except to the extent specifically permitted under the terms of the level of your
  subscription for Baltic Data as set out in the Baltic Data Policy".
- Data Policy (https://www.balticexchange.com/en/site-services/data-policy.html): subscribers "have access to a range of
  indices and other market data produced by the Baltic" (clause 1.2); the holder of a Restricted Baltic Data Licence shall not
  "display Baltic Data on any intranet or public website" and shall not "use or permit their clients to use Baltic Data to create
  derived data, including pricing data or other information that would be created in whole or in part from Baltic Data" (clause
  2.2.3; clauses 2.3.3 and 4.2 are close in wording).

Neither page says whether the descriptions of the standard vessels are Baltic Data, or whether a reader without a licence is
bound by the policy: that is not settled. The method is in METHODOLOGY.md, section 3, "Voyage calculator".

The "Freight market now" page links to the Baltic Exchange's page of indices (the address of the registry entry `baltic`) and shows no value of them.

### Shanghai Shipping Exchange and USDA Agricultural Marketing Service (linked, no value shown)

The "Freight market now" page links to three publications and shows no value of any of them: the China Import Dry Bulk Freight Index and the China Import Crude Oil
Tanker Freight Index of the Shanghai Shipping Exchange (registry id `sse`), and the weekly count of grain vessels and the grain ocean freight rates of the USDA
Agricultural Marketing Service (`usda-ams`). Nothing of them is fetched, stored or offered for download, and a link has no source line. What the pages say, read on 25 November 2026:

- Shanghai Shipping Exchange, home page (https://en.sse.net.cn/): "© 2001-2026 Shanghai Shipping Exchange Institute(Prep.) All Rights Reserved." (spacing
  normalised). It is the only statement read on its pages; the list of indices and the two index pages
  (https://en.sse.net.cn/indices/cdfinew2.jsp and https://en.sse.net.cn/indices/ctfinew2.jsp) carry it too. The home page has a block headed laws that links to a page of laws and regulations, which was not read, and no page
  of terms was read. The index pages fill their tables by script and no value was read. The two indices measure freight into China only.
- USDA Agricultural Marketing Service, privacy page of its web site (https://www.ams.usda.gov/about-ams/privacy): "Information presented on the AMS web site is
  considered public information and may be distributed or copied. Use of appropriate byline/photo/image credits is requested." It names the AMS web site and not the AgTransport host
  (agtransport.usda.gov), whose tables carry the attribution "USDA Agricultural Marketing Service" for the vessel count and "O'Neil Commodity Consulting" for the grain vessel rates, and no licence
  field (https://agtransport.usda.gov/api/views/vh5k-mnyv.json and https://agtransport.usda.gov/api/views/ehs5-yac3.json).
- USDA Agricultural Marketing Service, datasets of the Grain Transportation Report (https://www.ams.usda.gov/services/transportation-analysis/gtr-datasets): "These data series
  are aggregated from non-confidential and non-copyrighted sources."; the table of the vessel count is named "Weekly port region grain ocean vessel activity (number of vessels)" and holds the "Weekly number of grain vessels
  loaded during the week and expected to be loaded within the next 10 days in the Gulf, PNW, and Vancouver, B.C."; and, for the grain vessel rates, U.S. to Japan, "SOURCE: O'Neil Commodity Consulting".

The atlas does not read the privacy sentence as covering rates credited to a private firm. Neither publisher is affiliated with the atlas or endorses it. The registry entries state the same sentences.

### Canal authorities (toll tariffs)

The voyage calculator has a field for the canal tolls of a round voyage, which the visitor types. Beside it, when the routing
chosen crosses the canal, it links the Panama Canal Authority's tariff
(https://pancanal.com/en/maritime-services/maritime-tariff/) and the Suez Canal Authority's tolls table
(https://www.suezcanal.gov.eg/English/Navigation/Tolls/Pages/TollsTable.aspx). No figure of either tariff is copied, stored or
shown: the pages are credited as linked, not copied, and they are not entries of the registry of sources, which lists the
sources of figures. Read on 25 November 2026: the Panama Canal Authority's Terms of Use (https://pancanal.com/en/terms-of-use/)
say that "their copying, distribution, transmission, reproduction or publication for commercial or lucrative purposes is
prohibited" and that their use for such purposes "requires prior express authorization from the Panama Canal Authority"; the
Suez Canal Authority's pages carry "Copyright 2017 | All Right Reserved Suez Canal Authority" and no page read states terms of
reuse. Terms to be confirmed.

## Use of the data

Not investment advice. Routes, lanes and distances are schematic and must not be used for navigation. The data are
provided as is, without warranty of any kind. The full text is in the "Disclaimer" section of
[README.md](README.md) and in the About window of the site.

A report opened through the site is a public issue of the repository under GitHub's terms: the site sends nothing to
GitHub until the visitor clicks "Report an error", and then only the address of the page, what is selected on it, its
heading and the release.

## Questions of terms still open

- The licence of the documentation (README, METHODOLOGY, DATA_SOURCES, this file) has not been decided.
- Whether the lane and route geometry computed on the SeaRoute network carries the EUPL 1.2 conditions, and the terms
  of the Oak Ridge network it is built on.
- Whether the CC BY 4.0 release is acceptable for figures derived from IMF PortWatch, given the IMF's conditions.
- Terms of the Panama Canal Authority, Suez Canal Authority, port authorities and the World Nuclear Association.
- Whether single points taken from OpenStreetMap make the infrastructure files a database derived from it under the
  ODbL's share-alike clause, or should be re-sourced.
- Terms of the Norwegian Offshore Directorate, Natural Resources Canada, Wilhelmsen and Cochilco.
- Whether the EIA's daily spot prices, which the EIA credits to Refinitiv, may be redistributed (registry entry `eia-spot`): the
  eight series stay on the site with that credit and are served as JSON for the charts, without a CSV button.
- The terms of use, and the edition, of the World Port Index file used: the statement read is on the 2017 edition of the
  publication and not on the file, the publisher's page held no text in the archived copies, and the file is the Internet Archive's
  copy of 29 September 2026, for which no terms of the archive's own were read.
