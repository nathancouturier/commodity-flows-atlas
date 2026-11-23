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
- the caches in `pipeline/cache/`: `baci_flows.csv.gz`, `hs4_exports.csv.gz`, `hs4_exports_desc.csv`,
  `sea_flows.csv.gz`, `mixed_flows.csv.gz`, `seaborne_totals.json`, `baci_rice_forms.csv` and `baci_country_codes.csv` are
  derived from CEPII BACI (Etalab Open Licence 2.0); `faostat_cocoa_production.csv` and
  `faostat_fertilizer_production.csv` are FAOSTAT data (CC BY 4.0); `wna_uranium.json` is World Nuclear Association data
  (terms to be confirmed); `adjacency.json` is derived from Natural Earth (public domain); `geom_cache.json` and
  `route_cache.json` hold computed routes (see the next section); `trade_checks.json` holds the findings of the atlas's
  checks, which quote CEPII BACI, USDA PSD, EIA, USGS and IMF PortWatch figures under the terms of each.

## The atlas's own figures: CC BY 4.0

Figures that the atlas computes itself carry the source id `atlas` (and the label "Atlas estimate" where they are
estimates): shares of seaborne trade, vessel-class tonne-mile shares, computed totals, laden days and alternative
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

- `data/infrastructure/fields.geojson`, `mines.geojson`, `pipelines.geojson`, `ports.geojson`, `refineries.geojson`
  and `smelters.geojson`: 145 assets whose source id is `wikipedia`;
- `data/commodities/companies.json`: 231 company entries whose source id is `wikipedia`;
- the rows of `data/countries/profiles.json` whose source id is `wikipedia` (they repeat figures of the files above);
- the events of `data/freight/events.json` and `data/freight/alerts.json` whose `src` is a Wikipedia article;
- `data/freight/vessel-classes.json`: the size ranges and notes whose source id is `wikipedia-vessel-classes` or
  `vessel-size-conventions` (articles Suezmax, Malaccamax, Q-Max, Handymax, Handysize, Oil tanker, Bulk carrier);
- `data/freight/chokepoints.json`: the `limits` texts whose `limitsS` is `wikipedia-vessel-classes` (articles Malaccamax,
  Sunda Strait, Lombok Strait, Drogden, Strait of Dover);
- the notes of `data/freight/routes.json` and `data/infrastructure/lng.geojson` that say they take a fact or a
  coordinate from a Wikipedia article (Handysize; Ras Laffan Industrial City);
- the port tables of `data/freight/lanes/*.json` (the typical ports, transit ports and their notes whose source id is
  `wikipedia`, each with the `url` of its article) and the same ports in `data/freight/pairs/*.json`;
- the matching definition files under `pipeline/freight/` (see "Source code: MIT"), among them the rows of the
  gateway, transit-port, draught and mode tables listed below.

The text was written by Wikipedia contributors and is licensed under the Creative Commons Attribution-ShareAlike 4.0
International licence (<https://creativecommons.org/licenses/by-sa/4.0/>).

**Changes were made.** Passages were shortened and rewritten, figures were taken from the article text and infoboxes
and converted to the atlas's units, coordinates were located or approximated, and the entries were combined with
figures from other sources.

**Credit.** Every Wikipedia-sourced asset and company keeps the `url` of the article it comes from (checked for
all 145 assets and 231 companies); the infrastructure panel links it as "Open source page". Every Wikipedia-sourced
port of a lane file keeps the `url` of its article, which the lane page links beside the port. The history tab of each
article lists its authors. Event entries keep the article link in `src`; vessel-class, chokepoint and route notes name
the article in their text.

**Share-alike.** The files listed above are shared under CC BY-SA 4.0, with the credit above. A figure in them that
comes from another source keeps its own source id, and that source's terms.

Wikipedia is an accepted source for now; better sources will be looked for later. When a Wikipedia-sourced entry is
replaced by one from another source, it leaves this notice.

## Third-party datasets

Each dataset keeps the licence of its source. The credits the sources ask for:

- **CEPII BACI**: Etalab Open Licence 2.0. Gaulier, G. and Zignago, S. (2010) BACI: International Trade Database at
  the Product-Level. The 1994-2007 Version. CEPII Working Paper N°2010-23. The atlas filters and cleans the data
  (METHODOLOGY.md, section 1); it does not republish the database.
- **Natural Earth** (basemap): public domain, no credit required; "Made with Natural Earth" is shown as a courtesy
  (<https://www.naturalearthdata.com/about/terms-of-use/>).
- **World Bank Pink Sheet**, **FAOSTAT**: CC BY 4.0. FAOSTAT is also subject to the FAO statistical database terms of
  use (no endorsement by FAO, no promotion of a commercial product).
- **U.S. Energy Information Administration, USGS, USDA**: U.S. Government publications, public domain; EIA asks for an
  acknowledgment ("Source: U.S. Energy Information Administration").
- **FRED**: the deep-sea freight producer price index is a U.S. Bureau of Labor Statistics series, public domain with
  citation requested ("Source: U.S. Bureau of Labor Statistics via FRED"). This product uses the FRED API but is not
  endorsed or certified by the Federal Reserve Bank of St. Louis. Other FRED series are not all in the public domain
  (some are copyrighted by third parties); the atlas uses no other series.
- **SeaRoute**: the `searoute` Python package is under Apache 2.0; the maritime network of Eurostat's SeaRoute is
  under EUPL 1.2.

The use of data from the U.S. Bureau of Labor Statistics, the IMF, the FAO or any other publisher does not mean that
they endorse the atlas.

## Cited, not redistributed

Some third-party material is cited rather than copied. For each, the position the atlas takes; the owner can change a
verdict (redistribute, cite a few facts, link only).

| Source | Position |
|---|---|
| IMF PortWatch | Aggregated, transformed counts are published, with credit. See below. |
| Baltic Exchange route names and definitions | Names and codes of the benchmark routes and their public definitions are used as facts. No index value or rate is shown. Not affiliated with the Baltic Exchange. |
| GIIGNL and other association reports | A few cited figures with attribution. No table, text or file is redistributed. |
| Press reports (Bloomberg via gCaptain, Cyprus Mail, GMK Center and others) | Short facts with a link to the article. No article text is copied. |
| Panama Canal Authority, Suez Canal Authority, port authorities | Published statistics and transit limits are cited as facts with attribution. No licence is stated on the pages; terms to be confirmed. |
| Company reports | Facts cited with a link to the report. |
| World Nuclear Association | Annual uranium production figures cited with attribution. Terms to be confirmed. |

### IMF PortWatch

Credit line: **IMF PortWatch (IMF and University of Oxford), data adapted.**

The atlas publishes weekly averages of PortWatch's daily counts of chokepoint transits and of its estimates of the trade
volume carried, and a 28-day average. They are a transformation of the daily data, and are described as such in
`data/sources.json` and METHODOLOGY.md: "Atlas weekly averages of IMF PortWatch daily counts".

Terms, as read on 22 November 2026: the PortWatch dataset (ArcGIS item "Daily_Chokepoints_Data") points to the IMF
terms of use (<https://www.imf.org/external/terms.htm>). The IMF's "Special Terms for Statistical Data"
(<https://www.imf.org/en/About/Copyright-and-Terms>) allow users to download, copy, create derivative works and
distribute IMF statistical data with attribution to the IMF as the source and an explicit statement of any
transformation, without altering the nature or accuracy of the data; commercial reuse needs IMF permission
(copyright@imf.org). No Creative Commons licence is stated by PortWatch or the IMF: the atlas registry no longer says
"CC BY 4.0". PortWatch's own page on data and methodology shows no licence text. PortWatch is built from vessel
tracking signals; the atlas shows only aggregated counts and volumes, never a position or a track.

The CC BY 4.0 release of the atlas's own figures does not extend IMF's rights: the weekly averages stay subject to
the IMF conditions above.

### Baltic Exchange

The atlas is not affiliated with, sponsored by or endorsed by the Baltic Exchange. Benchmark route codes (for example
C3, TD3C, BLNG1) and their definitions are taken from public pages and from the Veson VesselsValue summary of the
Baltic definitions; the Baltic site refuses automated access, so no definition was read at its source and several
are marked uncertain in `pipeline/freight/NOTES_routes.md` (TC20, TC21, TD6, TD15, S10 and port names). The Baltic
indices and rate assessments are proprietary and are not shown.

## Use of the data

Not investment advice. Routes, lanes and distances are schematic and must not be used for navigation. The data are
provided as is, without warranty of any kind. The full text is in the "Disclaimer" section of
[README.md](README.md) and in the About window of the site.

## Questions of terms still open

- The licence of the documentation (README, METHODOLOGY, DATA_SOURCES, this file) has not been decided.
- Whether the lane and route geometry computed on the SeaRoute network carries the EUPL 1.2 conditions, and the terms
  of the Oak Ridge network it is built on.
- Whether the CC BY 4.0 release is acceptable for figures derived from IMF PortWatch, given the IMF's conditions.
- Terms of the Panama Canal Authority, Suez Canal Authority, port authorities and the World Nuclear Association.
