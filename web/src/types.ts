/**
 * Data model for Commodity Flows Atlas.
 *
 * Every number shown in the UI must be traceable to a source and a year.
 * The canonical data lives in /data (repo root) and is served at ./data/.
 * See docs/DATA_MODEL.md for the full description of each file.
 */

export type Family = 'energy' | 'metals' | 'softs' | 'freight';

/** ISO 3166-1 alpha-3 country code, or a region code such as "EU27" / "WLD". */
export type Iso3 = string;

/** A sourced, dated figure. */
export interface Fig {
  /** value */
  v: number;
  /** unit, e.g. "Mt", "kb/d", "bcm", "%" */
  u: string;
  /** reference year (number) or period label such as "2024/25" or "2025-Q2" */
  y: number | string;
  /** source id, key into sources.json */
  s: string;
  /** optional note (method, discrepancy, scope) */
  n?: string;
  /** the figure is an Atlas estimate (computed by the atlas, not converted): printed with two significant digits */
  est?: boolean;
  /** the same quantity in a second unit, printed in brackets: an Atlas conversion (`s` is `atlas`), its factor is in `n` */
  alt?: { v: number; u: string; s: string; y: number | string; n: string };
}

/** Entry of data/sources.json */
export interface Source {
  id: string;
  name: string;
  publisher: string;
  url: string;
  licence: string;
  /** human-readable update cadence, e.g. "annual (January)" */
  update: string;
}

/** A ranked country table (production, reserves, exports...). Shares are computed against `world`. */
export interface Ranked {
  y: number | string;
  /** USDA PSD: what the market year is in USDA's words (the newest one is its forecast, the one before its estimate) */
  yk?: 'forecast' | 'estimate';
  /** USDA PSD: the month of the report that last revised the year, "2026-11" */
  rel?: string;
  s: string;
  u: string;
  /** world total in the same unit, if known (from the same source) */
  world?: number;
  /** `name`: the source's entity of a past year when it is not the usual one (tableAt: "EU-25") */
  rows: { c: Iso3; v: number; n?: string; est?: boolean; conv?: boolean; name?: string; usd?: number; uv?: number; s?: string }[];
  /** the total the shares are of, when it is not the world's ("China's declared imports", "Australia's exports"); absent: the world */
  shareOf?: string;
  /** the sources of a table whose rows come from different ones (each row names its own in `s`); the table's `s` is the first */
  srcs?: string[];
  /** what the atlas converted in this table (a row with `conv` is an Atlas conversion of the source's figure), and `convWorld`: the world total too */
  conv?: string;
  convWorld?: boolean;
  /** the whole table is an Atlas estimate (rows without `est` too); a table of source `atlas` whose note does not start "Atlas estimate" is a conversion */
  est?: boolean;
  /** the source's own "Other countries" line, in the same unit: its own row, "Other countries (as published)" */
  other?: number;
  /** the countries the table names beyond its first `from` rows: `v` is their sum in table units, `n` names them */
  hidden?: { v: number; k: number; from: number; n: string };
  /** the world total the source publishes, when `world` (the sum the shares use) differs from it */
  worldPublished?: number;
  /** `EU`: a table of the European Union's member states, whose `world` is the total of the 27 (shares are of the EU, not of the world) */
  scope?: 'EU';
  /** a scope table: the name of the scope, for a total row or a column of the table ("EU member states"); `world` is the scope's total */
  scopeLabel?: string;
  /** a scope table: the world total of the same source and year, the base of the map colours of the member states */
  worldAll?: number;
  /** a scope table that does not paint the map: another basis than the USDA table (paddy against milled rice, beet against sugar), or another
   * definition (customs trade includes trade between members): the member states keep the value of USDA's row for the European Union */
  noMap?: boolean;
  /** a scope table of customs trade: the total of the 27 member states and the part of it inside the EU and outside it */
  split?: { total: number; intra: number; extra: number };
  /** the USDA trade table of a crop: what the customs data say of the 27 members together, inside the EU and outside it */
  eu?: { y: number; s: string; u: string; total: number; intra: number; extra: number };
  n?: string;
  /** what the tonnage measures when it is not the finished commodity, e.g. "ores and concentrates, gross weight" */
  basis?: string;
  /** warning that applies to the whole table (trade hubs, unit mismatch); also part of `n` */
  caveat?: string;
  /** the caveat in a few words (country profiles; a past-year table when the caveat holds for other years only) */
  caveatShort?: string;
  /** the years the caveat holds for, when not every year of the table's series (a past-year table: tableAt) */
  caveatYears?: number[];
  /** the part of the caveat that holds in the other years */
  caveatPast?: string;
  /** the order of the rows is not a world ranking (a source that understates some countries): country profiles print no rank */
  norank?: boolean;
  /** customs tables of the metals pages: the value of the whole table (USD) and its unit value (USD per tonne); a row has its own `usd` and `uv`, none where its tonnage is mostly estimated */
  usd?: number;
  uv?: number;
}

/** A sanctions designation of a company, from the authority's own notice (pipeline/companies/README.md). */
export interface CompanySanction {
  by: 'OFAC' | 'EU' | 'UK';
  /** YYYY or YYYY-MM */
  since: string;
  url: string;
}

/** One comparable figure of a company for the commodity (or the fleet) it stands under. */
export interface CompanyFig {
  v: number;
  /** a unit only (Mt, kt, t, kb/d, Mboe/d, bcm, Mtpa, Mt/y, ships, Mdwt, Mcbm, TEU) */
  u: string;
  /** what is counted and on which basis ("copper production, own mines", "fleet, owned and chartered-in") */
  what: string;
  /** the year the figure refers to (a fiscal year: the calendar year in which it ends) */
  y: number;
  s: string;
  url: string;
  /** a conversion or a basis, as the page states it */
  n?: string;
}

export type CompanyOwn = 'state' | 'state-listed' | 'listed' | 'private' | 'cooperative';

export interface Company {
  name: string;
  /** headquarters country */
  hq?: Iso3;
  /** e.g. "producer", "refiner", "smelter", "trader", "shipowner" */
  role: string;
  own?: CompanyOwn;
  /** the controlling shareholder or parent as the page states it */
  parent?: string;
  /** the page that states the parent's share, when it is not the entry's Wikipedia article */
  parentUrl?: string;
  detail?: string;
  fig?: CompanyFig;
  sanction?: CompanySanction | CompanySanction[];
  s?: string;
  /** the year the entry's facts refer to (not the year of reading) */
  y?: number;
  /** source page */
  url?: string;
  /** YYYY-MM: the month the page was read */
  read?: string;
  /** commodity id(s) the company is listed for (country profiles) */
  k?: string | string[];
  /** shipping companies: the vessel classes it operates */
  classes?: string[];
  /** country pages: the shipping segments a shipping company is listed under */
  seg?: string[];
}

/** data/freight/shipping-companies.json: shipping companies by segment. */
export type ShippingCompanies = Partial<Record<'dry-bulk' | 'tankers' | 'gas' | 'charterers' | 'brokers' | 'terminals', Company[]>>;

/** A bilateral physical trade flow. */
export interface Flow {
  /** origin country */
  o: Iso3;
  /** destination country */
  d: Iso3;
  v: number;
  u: string;
  y: number | string;
  s: string;
  /** how the flow moves: `sea` includes cargo that sails through a foreign port (`transit`); `mixed` = by sea and overland, split not known */
  mode?: 'sea' | 'land' | 'mixed' | 'pipeline';
  /** sea through a foreign port (landlocked end), mode `sea` only */
  transit?: LaneTransit;
  /** the tonnage is an Atlas estimate (computed from the declared value), source id `atlas` */
  est?: boolean;
  /** the estimate is made from a volume in the United States' own export statistics, not from the declared value */
  estBy?: 'volume';
  /** share by sea (0 to 1) of a mixed flow whose split by mode a source measures for the year `y` (the note gives the source); the other part is read as overland */
  seaShare?: number;
  /** the estimate was above the customs gross weight and is capped there: `v` is the cap, printed as it is */
  cap?: boolean;
  /** declared customs value of the flow (USD) and its unit value (USD per tonne; none where the tonnage is an Atlas estimate from the value) */
  usd?: number;
  uv?: number;
  /** lane id in freight/lanes (sea geometry), when available */
  lane?: string;
  /** id in data/freight/caveats.json: a reporting gap or relabelled origin that applies to this flow */
  caveat?: string;
  n?: string;
}

export interface CommodityMeta {
  id: string;
  name: string;
  family: Family;
  /** short one-line description */
  blurb: string;
  /** main physical unit */
  unit: string;
  hs?: string[];
  /** price series ids available for this commodity */
  prices?: string[];
  /** which panels/layers have data */
  has: Array<'production' | 'reserves' | 'consumption' | 'exports' | 'imports' | 'flows' | 'infrastructure' | 'prices' | 'companies'>;
  /** display order inside its family */
  rank: number;
  /** sub-heading in the commodity list ("Fertilisers"), shown before the first commodity that has it */
  sub?: string;
}

export interface CommodityData {
  id: string;
  summary: Partial<Record<'production' | 'exports' | 'reserves' | 'consumption' | 'seaborne', Fig>>;
  /** KPI labels that replace the default wording, e.g. seaborne: "Seaborne trade (all coal)" */
  kpis?: Partial<Record<'production' | 'exports' | 'reserves' | 'consumption' | 'seaborne', string>>;
  /** section titles that replace the default wording, e.g. flows: "Main flows — all coal, customs data 2024" */
  labels?: Partial<Record<'production' | 'reserves' | 'consumption' | 'exports' | 'imports' | 'flows', string>>;
  production?: Ranked;
  /** additional ranked tables (refined copper, alumina, USDA ending stocks...) */
  extra?: { key: string; title: string; table: Ranked }[];
  /** USDA PSD crops: the balance of the estimate year and the forecast year side by side (CropBalance.tsx) */
  balance?: CropBalance;
  /** an exporter whose customs record is below USDA's figure (Russian grain): a visible note beside the flows (AgriBlocks.tsx) */
  gaps?: { o: Iso3; text: string; s: string; y: number }[];
  /** refinery / smelter output by country */
  refinery?: Ranked;
  reserves?: Ranked;
  consumption?: Ranked;
  exports?: Ranked;
  imports?: Ranked;
  flows?: Flow[];
  /** one short sentence per source of a list of flows that come from several sources: what each figure counts (printed in the footer of the block) */
  flowDefs?: string[];
  companies?: { producers?: Company[]; processors?: Company[]; traders?: Company[] };
  /** the United States as the USGS file states it: apparent consumption and net import reliance (published figures) */
  us?: UsFigures;
  /** concentration of each table that has a world total, by table key (production, exports, an extra table's key...) */
  concentration?: Record<string, Concentration>;
  /** products of this page that are on another commodity page: one line each, "See <page> for <text>." with a link (`k`: the other page) */
  see?: { k: string; text: string }[];
  notes?: string[];
  discrepancies?: string[];
}

export interface UsFigures {
  s: string;
  consumption?: { label: string; u: string; vals: { y: number; v: number; est: boolean }[]; n?: string }[];
  reliance?: { what: string; pct: string; y: number; src?: string; srcYears?: string; n?: string }[];
}

/** Share of the first country, of the first three and Herfindahl index (0 to 10,000) of a table, on the table's world total. `cov`: share of the total the countries cover; `eq`: number of equal-sized countries with the same index. */
export interface Concentration {
  top1: { c: Iso3; p: number };
  top3: number;
  hhi: number;
  eq: number | null;
  k: number;
  cov: number;
  est?: boolean;
}

/** One line of a crop balance: `v` is the value of each year of `years`; a line with source `atlas` is arithmetic on two USDA figures of the same year (`n` says which) */
export interface CropBalanceRow {
  k: string;
  label: string;
  u: string;
  v: number[];
  sub?: boolean;
  s?: string;
  n?: string;
}

/** The balance of a USDA PSD crop for the estimate year and the forecast year (pipeline/commodities/build_commodities.py, Psd.balance). */
export interface CropBalance {
  s: string;
  years: { y: string; yk: 'forecast' | 'estimate' | null; rel: string }[];
  rows: CropBalanceRow[];
  n: string;
}

/** One table of a commodity by country and year (pipeline/commodities/history.py); the last year is the table of the page. */
export interface HistTable {
  u: string;
  s: string;
  years: number[];
  /** how each year is printed when it is not the year itself (USDA PSD market years, "2010/11") */
  labels?: string[];
  /** world total per year, the basis of the shares */
  world: number[];
  /** years (indexes) whose world total holds a tenth or more of Atlas estimates */
  worldEst?: number[];
  /** the published world total per year, where the shares rest on the sum of the lines */
  pub?: number[];
  /** the source's own "Other countries" line per year (USGS) */
  other?: (number | null)[];
  /** what each year is, in the words the source supports (USGS MCS: "as published in USGS MCS 2026") */
  yl?: string[];
  /** USDA PSD: "forecast" for the newest market year, "estimate" for the one before, null for the others */
  kinds?: ('forecast' | 'estimate' | null)[];
  /** one value per year; null = no figure that year */
  c: Record<Iso3, (number | null)[]>;
  /** years (indexes) in which the source's value is far out of line with the years around it: kept, not ranked or drawn */
  out?: Record<Iso3, number[]>;
  /** years (indexes) whose world total holds such a value */
  worldOut?: number[];
  /** the name of a row in the years where the source's entity is another one (USDA PSD's European Union); null = its usual name */
  cl?: Record<Iso3, (string | null)[]>;
  /** years (indexes) at which the series of a row breaks (its entity changes): no line and no change across them */
  brk?: Record<Iso3, number[]>;
  /** notes on the series as a whole (first year of a rule, change of membership or coverage, a country that split) */
  n?: string[];
  /** years (indexes) in which the row is mostly an Atlas estimate */
  est?: Record<Iso3, number[]>;
  /** years (indexes) in which the value is the source's own estimate */
  srcEst?: Record<Iso3, number[]>;
  /** years (indexes) in which the value is the atlas's conversion of the source's figure, and the years whose world total is one */
  conv?: Record<Iso3, number[]>;
  convWorld?: number[];
  /** years (indexes) in which the source's "Other countries" line is itself marked as an estimate */
  otherEst?: number[];
}

/** data/commodities/history/<id>.json: `t` is keyed by table (production, exports... or the key of an extra table). */
export interface CommodityHistory {
  id: string;
  t: Record<string, HistTable>;
}

/** A month of a monthly series ("YYYY-MM") with its figure. */
export interface MonthlyPoint {
  v: number;
  m: string;
}

/**
 * One monthly series of data/commodities/monthly/<id>.json (EIA International, pipeline/commodities/monthly.py): the last months
 * (`v`, oldest first, null where the source gives none), the average of the baseline year (`b`), the lowest month and the latest month of
 * the year of the latest month (`lo`, `la`) and the change of the latest month against `b`, in per cent (`p`). All are arithmetic on
 * published monthly figures.
 */
export interface MonthlyRow {
  /** ISO3 of a country, or the code of a group the source publishes (OECD, OEEU) */
  c?: Iso3 | string;
  /** name of a group; a country is named by `c` */
  name?: string;
  v: (number | null)[];
  b: number | null;
  lo: MonthlyPoint;
  la: MonthlyPoint;
  p?: number;
  /** stocks: the end of the year before the latest month, the same month a year before, and the days of cover */
  end?: MonthlyPoint;
  ya?: MonthlyPoint;
  cover?: number;
  cons?: number;
  /** imports by origin: the EIA code of the origin (PERG = the Persian Gulf) */
  o?: string;
}

/**
 * One origin of the imports by origin. EIA leaves a month out when it has no figure (and says nowhere that it means no imports), so
 * `v` holds null there and: `la` is null when the table's month has no figure (`last` is then the latest figure before it); `lo` is null
 * when a month of the year so far has none (`miss` counts them); `b` is null when a month of the baseline year has none (`nb` counts the
 * months that have one).
 */
export interface ImportRow extends Omit<MonthlyRow, 'lo' | 'la'> {
  lo: MonthlyPoint | null;
  la: MonthlyPoint | null;
  last?: MonthlyPoint;
  miss?: number;
  nb?: number;
}

/** A block of monthly rows: `from` to `to` ("YYYY-MM") are the months of `v`. */
export interface MonthlyBlock {
  u: string;
  from: string;
  to: string;
  baseYear?: number;
  rows: MonthlyRow[];
  world?: MonthlyRow | null;
  /** the Gulf producers added up, month by month (only the months in which all of them have a figure) */
  gulf?: (MonthlyRow & { members: string[] }) | null;
}

/** data/commodities/monthly/<id>.json, loaded by the commodity page on demand. */
export interface CommodityMonthly {
  id: string;
  s: string;
  production?: MonthlyBlock;
  consumption?: MonthlyBlock;
  ngl?: MonthlyBlock;
  imports?: { u: string; importers: { id: string; name: string; from: string; to: string; rows: ImportRow[] }[] };
  stocks?: MonthlyBlock & { withheld: string[] };
  /** what the EIA file does not hold month by month, in words for the page */
  gaps?: string[];
}

export interface CountryMeta {
  c: Iso3;
  name: string;
  /** label anchor [lon, lat] */
  at: [number, number];
  /** bounding box [west, south, east, north]; east may exceed 180 for antimeridian countries */
  bb?: [number, number, number, number];
  region: string;
}

/**
 * A country's profile, data/countries/profiles/<ISO3>.json, generated by pipeline/commodities/build_profiles.py. A country
 * of the index without data has only `c` and `none` (what it is, and why it has no data).
 */
export interface CountryProfile {
  c: Iso3;
  /** the exact words for a territory that has no data */
  none?: string;
  exports: ProfileEntry[];
  imports: ProfileEntry[];
  /** production lines, refinery output and the extra production tables */
  production: ProfileEntry[];
  consumption?: ProfileEntry[];
  reserves?: ProfileEntry[];
  /** ending stocks (USDA PSD) and generating capacity (EIA nuclear), from the extra tables of the commodity files */
  stocks?: ProfileEntry[];
  capacity?: ProfileEntry[];
  /** headings of the raw-material chapters outside the atlas catalogue (HS4, CEPII BACI) */
  other?: ProfileEntry[];
  basket?: ProfileBasket;
  balance?: ProfileBalance[];
  freight?: ProfileFreight;
  /** caveats of the trade-flow engine for this origin: exports that customs data miss, trade hubs */
  gaps?: { id: string; k: string; g: string; kind: string; text: string }[];
  infra?: string[];
  /** headquarters in the country */
  companies?: Company[];
  /** operators of the assets of the infrastructure layer in the country, with the assets */
  operators?: { name: string; assets: string[] }[];
  /** catalogue commodities in which the country ranks in the world top 10 of production, exports or imports */
  top10?: number;
  /** EU member state: the code of the EU aggregate (USDA PSD gives one row for the Union) */
  eu?: string;
  /** the EU aggregate: its member states */
  members?: Iso3[];
  /** the customs data have no code of their own for this entry of the index */
  noCode?: string;
  /** the years of each series the lines point to (`hk`), with the world total of each year: data/countries/years.json, one
   * file for every country, attached by the loader (lib/data.ts loadProfile) */
  years?: Record<string, { y: number[]; l?: string[]; w: (number | null)[] }>;
}

/** Largest exports and imports at HS4, every chapter, latest BACI year. */
export interface ProfileBasket {
  y: number;
  s: string;
  exports?: { total: number; rows: BasketRow[] };
  imports?: { total: number; rows: BasketRow[] };
}

export interface BasketRow {
  hs4: string;
  label: string;
  /** bn USD */
  usd: number;
  /** of the country's total merchandise exports (or imports) */
  share: number;
  /** atlas commodity of the heading, when it maps to one */
  k?: string;
  /** the first parts of its six-digit descriptions, when the name lists several (the archive gives no four-digit wording) */
  d?: string;
}

export interface ProfilePartners {
  rows: { c: Iso3; share: number; est?: boolean }[];
  /** number of partners */
  n: number;
  /** Herfindahl index of the partner shares, 0 to 10,000 */
  hhi: number;
  g: string;
  y: number;
  s: string;
  est?: boolean;
  estShare?: number;
  /** of `estShare`, the part made from a volume in the United States' own export statistics (the rest is from the declared value) */
  estVolShare?: number;
  /** "declared value" when the shares are of value, not tonnes (precious metals) */
  basis?: string;
}

/** One traded product of a commodity in a country: net position, partners, import dependence, hub label. */
export interface ProfileBalance {
  k: string;
  /** table key of the exports side (exports, refined-exports...) */
  t: string;
  label?: string;
  net?: { v: number; exp: number | null; imp: number | null; u: string; y: number | string; s: string; est?: boolean; n?: string };
  customers?: ProfilePartners;
  suppliers?: ProfilePartners;
  /** imports over consumption, same unit and year */
  dep?: { v: number; y: number | string; s: string; u: string; imp: number; cons: number };
  /** derived label: exports and imports both large, and no line in a production table that lists every producing country */
  hub?: { exp: number; imp: number; prodS: string; prodY: number | string };
}

/** A passage of a country's seaborne tonnes: "at least" and "up to" shares; `capped`: no "up to" is printed, because the
 * passage's page caps its own at IMF PortWatch (`high` is then `low`). */
export interface Passage {
  id: string;
  low: number;
  high: number;
  capped?: boolean;
}

export interface FreightProduct {
  g: string;
  k: string;
  kt: number;
  /** shares of the tonnes by mode */
  modes: Partial<Record<'sea' | 'transit' | 'mixed' | 'land', number>>;
  est?: boolean;
  /** kt of `kt` that are an Atlas estimate from the declared value, when only a part of the group's tonnes is */
  estKt?: number;
  /** of `estKt`, the kt made from a volume in the United States' own export statistics (the rest is from the declared value) */
  estVolKt?: number;
  /** kt of `kt` that the atlas adds from the importer's own declaration (not in the customs file), and the source id of that figure */
  added?: { kt: number; s: string };
  /** `atlas` when the tonnes of the whole group are an Atlas estimate (spodumene); absent when they are the block's source */
  s?: string;
  seaKt?: number;
  unrouted?: number;
  ports?: { name: string; c: Iso3; share: number; basis?: string }[];
  /** share of the seaborne tonnes whose assumed route has to cross (`low`) or may cross (`high`) each passage */
  via?: Passage[];
}

export interface ProfileFreight {
  y: number;
  s: string;
  /** what a port's percentage is (an allocation by the atlas's rules); the block prints it before the figures */
  note?: string;
  exports: FreightProduct[];
  imports: FreightProduct[];
  exportsTotal?: { kt: number; sea: number; mixed: number; seaKt?: number; via?: Passage[] };
  importsTotal?: { kt: number; sea: number; mixed: number; seaKt?: number; via?: Passage[] };
}

export interface ProfileEntry {
  /** commodity id */
  k: string;
  /** label for non-catalogue commodities */
  label?: string;
  v: number;
  u: string;
  /** share of world total, 0..1 */
  share?: number;
  /** world rank */
  rank?: number;
  y: number | string;
  s: string;
  n?: string;
  /** the tonnage is an Atlas estimate (source `atlas`): printed with two significant digits and marked */
  est?: boolean;
  /** trade value in bn USD, when known */
  usd?: number;
  /** source id and year of `usd` (the tonnage may come from another source and year) */
  usdS?: string;
  usdY?: number | string;
  /** what the tonnage measures, e.g. "ores and concentrates, gross weight", "contained cobalt" */
  basis?: string;
  /** warning carried from the commodity table (trade hubs, gross weight against contained metal) */
  warn?: string;
  /** a table of part of the world (the EU member states): its name */
  scope?: string;
  /** reserves over production of the same source and unit (years), and the year of that production */
  rp?: number;
  rpY?: number | string;
  /** key of the series in `CountryProfile.years`; the country's value and world rank by year */
  hk?: string;
  hv?: (number | null)[];
  hr?: (number | null)[];
  /** years (indexes) mostly an Atlas estimate, out of line (not ranked), at which the series breaks, the source's own estimate */
  hest?: number[];
  hout?: number[];
  hbrk?: number[];
  hsrc?: number[];
  /** the line is the atlas's conversion of the source's figure; years (indexes) in which it is */
  conv?: boolean;
  hconv?: number[];
  /** the row's name in the years its entity is another one (USDA PSD's European Union) */
  hcl?: (string | null)[];
}

// ---------------------------------------------------------------- freight

export type Segment = 'dry' | 'tanker' | 'gas' | 'container';

export interface VesselClass {
  id: string;
  name: string;
  segment: Segment;
  /** deadweight range in tonnes (or cbm for gas carriers, see unit) */
  /** typicalS: source id of the typical size when it is not the class's own source (the atlas, for a convention) */
  /** s, url, y, n: the page and year of the band (`atlas` for an Atlas convention) and what it says; typicalUrl, typicalY: the same for the typical size */
  size: {
    min: number; max: number; typical: number; typicalS?: string; typicalUrl?: string; typicalY?: number; u: 'dwt' | 'cbm' | 'teu';
    s?: string; url?: string; y?: number; n?: string;
  };
  dims?: { loa?: number; beam?: number; draft?: number; s?: string };
  /** standard vessel of the class as a page describes it: metres, knots, tonnes of fuel a day; n names the fuel and the wording */
  std?: VesselStd;
  /** a class without its own benchmark routes: the class whose benchmarks apply */
  bench?: { id: string; n: string };
  /** UNCTADstat ship type of the class (data/freight/fleet.json); null when UNCTADstat does not single out its kind of ship */
  fleetType?: string | null;
  cargoes: string[];
  /** the product of a cargo page when only one group of the page sails in this class (urea page -> "Ammonia" on a gas carrier) */
  cargoLabels?: Record<string, string>;
  constraints: string[];
  canals: { suez: string; panama: string };
  fleet?: Fig;
  routes: string[];
  notes?: string;
  s: string;
  /** typical laden speed, knots (Atlas assumption, see speedNote): laden days = distance / (speed x 24) */
  speedKn?: number;
  speedNote?: string;
  /** the same speed as a figure: an assumed laden service speed, `s` is `atlas` */
  speed?: Fig;
}

export interface VesselStd {
  dwt?: number;
  loa?: number;
  beam?: number;
  draught?: number;
  cubic?: number;
  speed?: { laden?: number; ballast?: number };
  cons?: { laden?: number; ballast?: number };
  n: string;
  s: string;
  url?: string;
  y: number;
}

/** data/freight/fleet.json: world fleet by UNCTADstat ship type, latest year and the last years */
export interface FleetFile {
  s: string;
  url: string;
  y: number;
  types: { name: string; ships: Fig | null; dwt: Fig | null; age: Fig | null; hist: { years: number[]; ships: (number | null)[]; dwt: (number | null)[] } }[];
}

/** A port up a river that the sea network does not follow (pipeline/freight/river_legs.py): every distance through it includes the leg. */
export interface PortRiver {
  river: string;
  /** where the sea route of the atlas joins the river */
  mouth: string;
  km: number;
  /** the leg in nautical miles, included in the distances; the line is drawn straight from the port to the mouth */
  nm: number;
  s: string;
  url: string;
  /** the sentence the pages print */
  n: string;
}

export interface PortRef {
  id: string;
  name: string;
  c: Iso3;
  at: [number, number];
  /** freight zone id, see data/freight/zones.json; null for a port outside the zone table */
  zone?: string | null;
  /** source id and page of the gateway row (typical ports are an Atlas assumption); null when no page was read */
  s?: string | null;
  url?: string;
  /**
   * why the atlas uses this port: "page names the cargo", "page names the cargo in the other direction",
   * "page names the plant, not the cargo", "general port of the country", "port used before, no page read" or "nearest seaport"
   */
  basis?: string;
  /** set for a port up a river: the distance of every lane through it includes the leg */
  river?: PortRiver;
}

export interface AltRouting {
  /** e.g. "Avoiding Suez Canal and Bab el-Mandeb (via Cape of Good Hope)" */
  label: string;
  avoids?: string[];
  via: string[];
  distanceNm: number;
  /** extra laden days vs the main routing (negative = the alternative is shorter) */
  extraDays: number;
  when?: string;
  /** dated notes that apply to this alternative (the Red Sea diversion for a Suez routing) */
  status?: StatusNote[];
}

export interface Route {
  id: string;
  name: string;
  /** true for Baltic Exchange benchmark routes */
  benchmark: boolean;
  /** an Atlas corridor generated from the customs pairs table (never a benchmark): ports, class, distance and passages are those of its largest pair */
  generated?: boolean;
  discontinued?: string;
  roundVoyage?: boolean;
  /** "typical laden leg" when a time-charter trip is drawn as its laden leg */
  drawnAs?: string;
  /** set when the line, distance and days are borrowed from another route (the benchmark has no fixed ports) */
  standIn?: string;
  /** the largest recorded pair of the corridor as the Route finder runs it, when its ports are not the route's own (distance in nm) */
  finder?: { g: string; o: string; d: string; mt: number; y: number; from: string; to: string; nm: number };
  /** the ports of the route that are up a river: the distance includes the leg and the line is drawn straight from the port to the mouth */
  rivers?: (PortRiver & { port: string })[];
  vclass: string;
  cargoes: string[];
  /** why the cargoes are typical of the class and not those of the benchmark's definition */
  cargoNote?: string;
  /** `assets`: for each port, the infrastructure asset it is ("port:primorsk"), or null */
  from: { region: string; ports: string[]; assets?: (string | null)[] };
  to: { region: string; ports: string[]; assets?: (string | null)[] };
  parcel?: number;
  /** upper end when the definition gives two cargo sizes (160,000 or 170,000 t) */
  parcelMax?: number;
  parcelUnit?: 't' | 'cbm';
  /** a benchmark's published definition (Baltic Exchange), read by hand */
  definition?: BenchmarkDefinition;
  distanceNm: number;
  /** laden voyage days at the class's typical laden speed */
  days: number;
  speedKn: number;
  /** chokepoint ids crossed, in order */
  via: string[];
  /** route end points [lon, lat] */
  a: [number, number];
  b: [number, number];
  /** bilateral flows this route represents: commodity id, origin and destination ISO3 lists */
  corridor?: { k: string; /** customs group, named by a generated corridor */ g?: string; /** customs groups of an entry that has no `g` (the groups of its commodity) */ gs?: string[]; o: string[]; d: string[] }[];
  /** country (ISO3) of each end of the drawn leg: load area, discharge area */
  ends?: [string | null, string | null];
  /** share of each cargo's seaborne trade carried on this corridor */
  shares?: { k: string; g?: string; f: Fig }[];
  shareCommodity?: Fig;
  /** why the route has no corridor share (shown as "n/a") */
  shareNa?: string;
  /** the generated corridor that counts this route's flow, when shareNa says so (linked from the page) */
  shareOn?: string;
  /** share of the vessel size class's tonne-mile demand (Atlas estimate); only for classes whose cargo base the atlas covers */
  shareClass?: Fig;
  alt?: AltRouting;
  /** passages only some options cross: lists of which one is used (parallel straits), or one passage the route may avoid */
  viaAlt?: string[][];
  /** every alternative; `alt` is the first */
  alts?: AltRouting[];
  /** why no alternative is shown */
  altNote?: string;
  /** active disruptions touching this route */
  status?: StatusNote[];
  /** annual corridor volumes, all cargoes of the corridor */
  history?: { y: number; v: number }[];
  historyUnit?: string;
  historySrc?: string;
  /** e.g. "Isolated customs outlier removed for 2016" */
  historyNote?: string;
  notes?: string;
  s: string;
}

/** A Baltic benchmark as its definition gives it; index values are proprietary and never shown. */
export interface BenchmarkDefinition {
  /** the code as published (BLNG1-174, S1B_63) */
  code: string;
  vessel?: string;
  /** cargo and quantity as defined; absent when the definition names none */
  cargo?: string;
  /** load and discharge ports, or delivery and redelivery areas when `tc` */
  load?: string;
  discharge?: string;
  /** a time-charter trip or round voyage */
  tc?: boolean;
  /** duration as defined, e.g. "35-45 days" */
  duration?: string;
  state: 'active' | 'suspended' | 'ended';
  /** ISO date: when it went live, or when it ended */
  stateDate?: string;
  stateNote: string;
  stateUrl: string;
  /** the benchmark that replaced an ended one */
  replacedBy?: string;
  index?: BenchmarkIndex[];
  /** the page of the definition, and the month it was read */
  doc: string;
  url: string;
  read: string;
  /** the year of that document, shown with the figures taken from it */
  y?: number;
}

/** An index or average this benchmark belongs to, with its weight. */
export interface BenchmarkIndex {
  id: string;
  name: string;
  /** weight in %, null when the index gives none */
  w: number | null;
  equal?: boolean;
  /** built on the time-charter equivalent of the route */
  tce?: boolean;
  /** every member; `in`: the atlas has it */
  members: { r: string; w?: number; in: boolean }[];
  /** weight (%) of the members the atlas has */
  covered?: number;
  since?: string;
  note?: string;
  url: string;
  doc: string;
}

/** A short dated status line on a lane or route, linked to an event. */
export interface StatusNote {
  text: string;
  event?: string;
}

/** Comparison of one passage's traffic over the last days with the same days a year earlier and the 2023 average (IMF PortWatch). */
export interface AlertMeasure {
  chokepoint: string;
  name: string;
  /** last day observed (ISO date) */
  to: string;
  /** length of the window, days */
  days: number;
  yearAgoTo: string;
  refYear: number;
  /** vessel transits over the window, the same days a year earlier, and the average of the reference year scaled to the same length */
  transits: { now: number | null; yearAgo: number | null; avg2023: number | null };
  /** PortWatch's estimated trade volume of those vessels, Mt */
  mt: { now: number | null; yearAgo: number | null; avg2023: number | null };
  /** per cent against the same days a year earlier and against the reference year (negative: fewer) */
  gapYear: number | null;
  gap2023: number | null;
  gapMtYear: number | null;
  gapMt2023: number | null;
  s: string;
}

/** data/freight/alerts.json entry: an active disruption (text by hand, figures and lists from the data: build_alerts.py). */
export interface Alert {
  id: string;
  title: string;
  /** "YYYY-MM" */
  since: string;
  /** from the transits against the 2023 average; null when no figure exists */
  severity: 'low' | 'medium' | 'high' | null;
  /** the rule behind the severity, in words (title attribute) */
  severityNote: string;
  text: string;
  /** date the text was checked against its source (ISO); absent when it was not */
  checked?: string;
  /** the passage and the gap (per cent against the reference year) that decided the severity */
  decidedBy?: { chokepoint: string; name: string; gap: number; refYear: number };
  chokepoints: string[];
  measures: AlertMeasure[];
  /** commodities and countries derived from the chokepoint estimates and lanes */
  commodities: string[];
  countries: Iso3[];
  exporters: Iso3[];
  importers: Iso3[];
  /** how the lists are derived */
  derived: string;
  /** countries added (or lists replaced) by hand, with the reason */
  override?: { commodities?: string[]; countries?: Iso3[]; addCountries?: Iso3[]; reason: string };
  /** the main event of the alert: the source of `src` and `also` */
  event: string;
  /** all the events of the alert, the main one first */
  events: string[];
  /** source URL */
  src: string;
  /** other pages that support the text */
  also?: { label: string; url: string }[];
}

export interface ChokepointTypeNote {
  name: string;
  y: number;
  /** the atlas's "at least" tonnage of the type (Mt) */
  low: number;
  /** PortWatch's volume of the type in the year (Mt), when it has one */
  ref: number | null;
  /** PortWatch's best full year since 2019 for the type (Mt) and its year */
  best: number;
  bestY: number | string;
  cmp: 'above' | 'near';
  regime: 'sub' | 'whole' | 'none' | null;
  capped: number;
  groups: number;
  /** the line the page prints, and the reason (folded) */
  line: string;
  n: string;
}

export interface Chokepoint {
  id: string;
  name: string;
  kind: 'strait' | 'canal' | 'cape' | 'channel' | 'passage';
  at: [number, number];
  limits?: string;
  /** source id of the depth figures quoted in `limits`, when they do not come from `s` */
  limitsS?: string;
  traffic?: Fig;
  /** PortWatch's estimated trade volume of the vessels counted, last 28 days (Mt/day) */
  trafficVol?: Fig;
  /** reference traffic figure from the operator (e.g. Panama Canal Authority fiscal-year transits) */
  trafficRef?: Fig;
  /** typical extra distance and days of the main alternative route on mapped lanes (Atlas estimate) */
  detour?: { nm: number; days: number; lanes: number; y: number | string; s: string; n?: string };
  /** published commodity flows through the chokepoint; k may be a commodity id or "petroleum-liquids" */
  shares?: { k: string; f: Fig }[];
  /** Atlas estimates: share of the seaborne trade of a lane group whose route has to cross it (`f`, "at least") and may cross it (`hi`, "up to"); `mt` = [at least, up to] in Mt */
  estimates?: { k: string; p?: string; f: Fig; hi?: Fig; mt?: [number, number] }[];
  /**
   * What the atlas's own tonnage of a ship type says against IMF PortWatch's volume of the same ships, once for the passage and not
   * in each estimate. Present for the types whose "at least" tonnage is above that volume or within 85% of it. `line` is the line the
   * page prints, `n` the reason (folded); `regime` is how the "up to" figures of the type are capped ("sub": PortWatch's volume less
   * the other groups, "whole": the whole volume, "none": not capped); `capped` of the `groups` of the type carry a capped figure.
   */
  typeNotes?: Partial<Record<'dry' | 'tanker' | 'cargo', ChokepointTypeNote>>;
  /** a route of similar length around this passage that the atlas does not count as a choice (or counts as one), one sentence */
  parallelNote?: string;
  alternatives?: { label: string; extraNm?: number; extraDays?: number; note?: string }[];
  events?: string[];
  portwatch?: string;
  /** PortWatch's own name for the counter behind `traffic` and the weekly series (e.g. "Oresund Strait") */
  portwatchName?: string;
  /** label of the series when the counter covers only part of the chokepoint */
  portwatchLabel?: string;
  /** what PortWatch does or does not count here */
  portwatchNote?: string;
  /** chokepoint id whose PortWatch series is shown on this page, under that chokepoint's own name */
  seriesFrom?: string;
  /** related chokepoint ids offered as links */
  seeAlso?: string[];
  summary: string;
  s: string;
}

/** data/freight/portwatch/<id>.json — weekly averages of daily transits since 2019 */
export interface PortwatchSeries {
  id: string;
  s: string;
  /** last date in the data */
  y: string;
  unit: string;
  /** first week start, ISO date */
  start: string;
  step: 'week';
  tanker: number[];
  dry: number[];
  container: number[];
  other: number[];
  total: number[];
  /** PortWatch's name for the counter */
  name?: string;
  /** PortWatch's estimated trade volume of the transiting vessels (tonnes of cargo, not deadweight), Mt per day */
  vol?: { unit: string; tanker: number[]; dry: number[]; container: number[]; other: number[]; total: number[] };
  /** complete calendar years: transits and estimated trade volume (Mt) */
  annual?: { years: number[]; transits: number[]; mt: number[] };
  headline?: Fig;
  headlineVol?: Fig;
  /** the last `days` days against the same days a year earlier and the average of `refYear` scaled to the same length (transits; Mt of estimated trade volume) */
  compare?: {
    to: string;
    days: number;
    yearAgoTo: string;
    refYear: number;
    transits: { now: number | null; yearAgo: number | null; avg2023: number | null };
    mt: { now: number | null; yearAgo: number | null; avg2023: number | null };
  };
}

/** data/freight/chokepoint-lanes.json — mapped lanes that cross each chokepoint (from the lanes' `via`). */
export interface ChokepointLanes {
  s: string;
  y: number | string;
  unit: string;
  n?: string;
  /** lane group -> commodity id, label, year, customs source and seaborne trade of the group (Mt) */
  groups: Record<string, { k: string; label: string | null; y: number; s: string; seaborne: number }>;
  /** chokepoint id -> [group, origin ISO3, destination ISO3, Mt, certain], largest first; certain is 1 when the passage is in the pair's `via`, 0 when it is one of several it may use */
  chokepoints: Record<string, [string, string, string, number, (0 | 1)?][]>;
}

export interface FreightEvent {
  id: string;
  date: string;
  end?: string;
  title: string;
  kind: 'conflict' | 'canal' | 'weather' | 'policy' | 'accident' | 'market' | 'infrastructure';
  chokepoints?: string[];
  routes?: string[];
  /** commodity, country and asset ids the event's own text names */
  commodities?: string[];
  countries?: Iso3[];
  assets?: string[];
  summary: string;
  impact?: string;
  src: string;
  /** other pages that support the text */
  also?: { label: string; url: string }[];
  /** date the text was checked against its source (ISO); absent when it was not */
  checked?: string;
  /** price series (ids of data/prices/index.json) to read for a commodity when the catalogue has several markets, e.g. { "natural-gas": "ttf-m" } */
  series?: Record<string, string>;
}

/** Sea through a foreign port: the landlocked end's cargo sails from (or to) this port. */
export interface LaneTransit {
  port: string;
  /** country of the port */
  c: Iso3;
  s: string;
  url?: string;
  /** the end has no coast at all (adjacency data); false: it has one and still ships through this foreign port (DR Congo) */
  landlocked?: boolean;
}

/** One load and discharge port pair of a lane whose ports are not decided by a rule (a coast option). */
export interface LaneOption {
  load: string;
  discharge: string;
  nm: number;
  days: number;
  via: string[];
  /** share of the trade, when a measured split exists */
  w: number | null;
}

/** What a history point stands for: estimated from value, kept although it looks odd, no customs record, hidden as suspect, repaired, flagged by a check. */
export type HistFlag = 'est' | 'kept' | 'nodata' | 'suspect' | 'repaired' | 'check';

/** A seaborne lane: origin-destination country pair for one commodity group, with geometry. */
export interface Lane {
  /** "<group>:<o>-<d>" */
  id: string;
  /** atlas commodity id */
  k: string;
  /** commodity group (customs product group), e.g. "copper-ore" */
  p: string;
  o: Iso3;
  d: Iso3;
  /** "main" (drawn with no year chosen) or "history" (drawn only in a year when it was large); absent in files from before the pairs table */
  set?: 'main' | 'history';
  /** `mixed`: the trade moves by sea and overland and the split is not known; absent = sea */
  mode?: 'mixed';
  /** sea through a foreign port, for a landlocked end (the loading end when both ends are landlocked) */
  transit?: LaneTransit;
  /** the discharging end's transit port, when both ends are landlocked */
  transit2?: LaneTransit;
  /** port ids, see LaneFile.ports */
  load: string[];
  discharge: string[];
  /** how the ports were chosen: one gateway, a coast rule, a measured split, or several coasts with nothing to decide between them */
  portBasis?: 'single' | 'rule' | 'measured' | 'open';
  /** with `portBasis` "open": a coast rule of the atlas chose the principal port of one end or both */
  portRule?: boolean;
  /** the other coasts, with their distances, when `portBasis` is "open" or "measured" */
  opts?: LaneOption[];
  /** typical vessel classes, primary first (Atlas assumption) */
  vclass: string[];
  distanceNm: number;
  days: number;
  /** passages every option of the lane has to cross */
  via: string[];
  /** lists of passages of which one is used (parallel straits, other coasts) */
  viaAlt?: string[][];
  /** latest-year flow; `est` = tonnage estimated from the declared value (source id `atlas`) */
  flow: Fig & { est?: boolean };
  /** share of the group's seaborne trade, 0..1 (latest year); null for a mixed lane */
  share: number | null;
  /** share of the destination's imports of this group, 0..1; absent when the tonnage is estimated */
  shareDest?: number | null;
  /** annual volumes (LaneFile.unit) for LaneFile.years; null = no figure shown that year (see histFlags) */
  hist: (number | null)[];
  histNote?: string;
  /** flag and note per year (keys are years) */
  histFlags?: Record<string, HistFlag>;
  histNotes?: Record<string, string>;
  /** the years of `histFlags` marked `est` whose tonnage is made from a volume in the United States' own export statistics, not from the declared value */
  histVolume?: string[];
  /** the source id of the volume of each of those years (the chart's source line names them) */
  histSrc?: Record<string, string>;
  /** `hist` is the pair in all modes, while the lane's own tonnage is its share by sea (a pair whose split by mode is known) */
  histAll?: boolean;
  /** id in data/freight/caveats.json */
  caveat?: string;
  /** geometry [lon, lat][]; longitudes are unwrapped (may exceed ±180) */
  g: [number, number][];
  /** the first of `alts`, for views that show one */
  alt?: AltRouting & { g: [number, number][] };
  alts?: (AltRouting & { g: [number, number][] })[];
  /** why no alternative is shown */
  altNote?: string;
  status?: StatusNote[];
}

/** data/freight/lanes/<group>.json */
export interface LaneFile {
  group: string;
  k: string;
  label?: string | null;
  unit: string;
  y: number;
  s: string;
  years: number[];
  /** seaborne total per year (unit): sea and transit pairs, after cleaning */
  seaborne: number[];
  /** tonnage of the mixed (sea and overland) pairs per year */
  mixed?: number[];
  /** all-modes world trade per year (unit) */
  world: number[];
  /** group-level warnings per year (keys are years) */
  yearNotes?: Record<string, string>;
  /** share of the latest year's seaborne tonnes estimated from value, 0..1 */
  est?: number;
  /** the same share for every year of `years` */
  estY?: number[];
  /** of `est` and `estY`, the part made from a volume in the United States' own export statistics (the rest is from the declared value); absent when none is */
  estVol?: number;
  estVolY?: (number | null)[];
  /** where a pair whose split by mode is known for some years only enters the seaborne series: one sentence, built from the data */
  breakNote?: string;
  coverage?: { lanes: number; share: number };
  /** per exporter: seaborne tonnes not on a main lane, the number of pairs and, of those tonnes, the part that is an Atlas estimate */
  rest?: { o: Iso3; v: number; n: number; est?: number }[];
  ports: Record<string, PortRef>;
  lanes: Lane[];
}

/**
 * data/freight/pairs/<group>.json: every recorded pair of the latest year, one row each, whatever its mode.
 * `cols` names the columns of `rows`: o, d, kt (customs tonnes, thousands), m (mode: 0 sea, 1 sea via a
 * transit port, 2 mixed, 3 land), load and dis (index in `ports`, -1 when not routed), nm (distance of the
 * main route), cls (index in `classes`, -1 none), via and alt (bit masks over `gates`: passages every option
 * has to cross, and passages only some options cross), f (bit 0 tonnage estimated from value, bit 1 a caveat
 * applies, bit 2 a main lane exists, bit 3 a check flags the pair, bit 4 the row is added from the importer's declaration, bit 5 with bit 0:
 * the estimate is made from a volume in the United States' own export statistics, not from the declared value).
 */
export interface PairsFile {
  group: string;
  k: string;
  y: number;
  s: string;
  unit: 'kt';
  /** sea + transit tonnes (kt): the denominator of the shares */
  seaborne: number;
  /** [code, name, country, zone, basis]: the zone is null outside the zone table; basis (an index in `bases`) is absent in older files */
  ports: [string, string, string, string | null, (number | null)?, (number | null)?][];
  /** why a port is used, see PortRef.basis */
  bases?: string[];
  /** the ports of the file that are up a river, by code: the distance of every pair through them includes the leg */
  rivers?: Record<string, PortRiver>;
  /** for estimated, checked or added pairs that have no lane: the note the lane would carry, keyed "<o>-<d>" */
  notes?: Record<string, string>;
  /** the pairs the atlas adds from the importer's own declaration (bit 4 of `f`), keyed "<o>-<d>": the source id of the row, which is not the file's */
  added?: Record<string, string>;
  /** a pair whose split by mode is known has its row for the part by sea; the rest of its tonnage went overland: [o, d, kt] */
  rest?: [Iso3, Iso3, number][];
  classes: string[];
  /** chokepoint ids, bit order of the `via` and `alt` masks (at most 31) */
  gates: string[];
  cols: string[];
  rows: (string | number)[][];
  /** ends of routed rows that ship through a foreign port and have no coast at all (adjacency data) */
  landlocked?: Iso3[];
}

/** data/freight/caveats.json: reporting gaps and relabelled origins, by id. `d` null = every destination of the origin. */
export interface CaveatEntry {
  kind: string;
  text: string;
  group: string | null;
  o: Iso3 | null;
  d: Iso3 | null;
  check?: string;
}
export type CaveatsFile = Record<string, CaveatEntry>;

// ---------------------------------------------------------------- infra & prices

export type InfraType =
  | 'mine'
  | 'field'
  | 'refinery'
  | 'lng-export'
  | 'lng-import'
  | 'pipeline'
  | 'smelter'
  | 'port'
  | 'storage';

/** Status vocabulary of an infrastructure asset (pipeline/infrastructure/README.md). */
export type InfraStatus = 'operating' | 'damaged' | 'suspended' | 'idle' | 'construction' | 'planned' | 'closed' | 'not-stated';

/** A figure of an asset: capacity (what it can do) or output (what it did in a year). */
export interface InfraFigure {
  v: number;
  /** one unit of the vocabulary: kb/d, bcm/y, Mtpa, Mt/y, kt/y, t/y, tU/y */
  u: string;
  /** year the figure refers to; absent when the source does not say */
  y?: number;
  /** what the figure counts ("iron ore", "100% basis") */
  n?: string;
  /** the source's own figure and unit, when v was converted */
  orig?: string;
  /** capacity only: a planned or target capacity (after ramp-up, at full production), not one the asset has reached */
  planned?: true;
}

export interface InfraOutput extends InfraFigure {
  y: number;
  what: 'production' | 'exports' | 'throughput';
}

export interface InfraProps {
  id: string;
  name: string;
  type: InfraType;
  k: string[];
  c: Iso3;
  operator?: string;
  capacity?: InfraFigure;
  output?: InfraOutput;
  opened?: number;
  status: InfraStatus;
  /** "YYYY" or "YYYY-MM": when the status was true */
  statusAsOf?: string;
  statusNote?: string;
  note?: string;
  s: string;
  /** "YYYY-MM": the month the page was read. Never the year of a figure. */
  read?: string;
  /** "approx": the point is a town, a centroid or a schematic position */
  coord?: 'site' | 'approx';
  /** countries crossed (pipelines) */
  cs?: Iso3[];
  /** pipelines */
  product?: string;
  length_km?: number;
  /** source page */
  url?: string;
  /** ports: the code of the place in the trade engine (pipeline/freight/ports.py), a UN/LOCODE where it has one */
  locode?: string;
  /** ports: the IMF PortWatch port id */
  portwatch?: string;
  /** ports: the largest ship or the deepest berth a page states */
  limits?: PortLimits;
  /** ports: the largest vessel class of the atlas each segment can take by the published limits (derived by the atlas) */
  maxClass?: PortMaxClass;
  /** ids of the price series quoted at this place (data/prices/index.json) */
  prices?: string[];
}

/** The class a segment of a port can take (pipeline/infrastructure/port_limits.py): one class, or two when the rules disagree. */
export interface PortClassEntry {
  id: string;
  /** the limit is above the band of the largest class of the segment */
  orLarger?: true;
  /** classes between this one and the next one ruled out that have no standard vessel to compare: not ruled out */
  also?: string[];
  /** "By deadweight", "By the 14 m draught" */
  by: string;
  /** one sentence: what the class rests on */
  basis: string;
}
export interface PortMaxClass {
  dry?: { classes: PortClassEntry[] };
  tanker?: { classes: PortClassEntry[] };
  gas?: { classes: PortClassEntry[] };
  /** the method, an Atlas estimate */
  n: string;
}

/** Physical limits of a port: metres and deadweight tonnes, as a page states them. */
export interface PortLimits {
  draught?: number;
  loa?: number;
  beam?: number;
  dwt?: number;
  /** true: `draught` is a water depth (of a berth or channel), not a ship's draught */
  depth?: true;
  /** the segment of the berths the limits are stated for */
  seg?: 'dry' | 'tanker' | 'gas';
  /** the vessel class the page itself names for these berths */
  cls?: string;
  /** the berth or terminal the limits are stated for, when not the whole port ("Jurong Port bulk berths") */
  at?: string;
  /** which berth or channel, and at which tide when stated */
  n: string;
  s: string;
  url: string;
  /** year of the statement; absent when the page does not say */
  y?: number;
}

/**
 * One entry of the World Port Index for a port (data/infrastructure/wpi.json, pipeline/infrastructure/wpi_limits.py): the
 * publication's own figures in metres, as it lists them. A figure the publication does not state is absent. There is no
 * `s`, `y` or `v` key: the source is the file's, and the file has no year of its own.
 */
export interface WpiEntry {
  /** the publication's port number and the entry's name */
  n: number;
  name: string;
  /** UN/LOCODE of the entry */
  lc?: string;
  /** how the entry was matched to the port, and the distance in km: audit trail, not shown */
  by: 'code' | 'name' | 'review';
  km: number;
  why?: string;
  size?: 'Very Small' | 'Small' | 'Medium' | 'Large';
  type?: string;
  /** tidal range */
  tide?: number;
  /** least depths: channel, anchorage, cargo pier, oil terminal, LNG terminal */
  chan?: number;
  anch?: number;
  pier?: number;
  oil?: number;
  lng?: number;
  /** the largest ship the publication states: length, beam, draught; and the same for offshore berths */
  loa?: number;
  beam?: number;
  draft?: number;
  oloa?: number;
  obeam?: number;
  odraft?: number;
  pilot?: 'Yes' | 'No';
  tideRes?: 'Yes' | 'No';
}

/** data/infrastructure/wpi.json: `read` is the month the atlas read the file; `edition` is the publication's own, or null when it is not stated. */
export interface WpiFile {
  s: string;
  read: string;
  edition: string | null;
  ports: Record<string, WpiEntry>;
}

/** A change of basis read from the source's own description: `now` starts at `at` ("YYYY-MM"), replacing `before`. */
export interface PriceBreak {
  at: string;
  now: string;
  before: string;
  /** end of a bounded period ("YYYY-MM") */
  to?: string;
}

/** Board figures precomputed by the builder from the published values: percent changes, 52-week range. */
export interface PriceStats {
  last: { v: number; t: string };
  /** percent: w 1 week (daily series), m 1 month, q 3 months, ytd since the last observation of the previous year, y 1 year */
  chg?: { w?: number; m?: number; q?: number; ytd?: number; y?: number };
  /** lowest and highest of the last 52 weeks (12 months for a monthly series) and where the last value stands in it, 0 to 1; none for an annual series */
  rng?: { lo: number; hi: number; pos?: number };
}

export interface PriceSeriesMeta {
  id: string;
  /** commodity id of the atlas, "freight", or "index" */
  k: string;
  name: string;
  unit: string;
  /** D daily, M monthly, A annual */
  freq: 'D' | 'M' | 'A';
  s: string;
  /** "YYYY-MM-DD" (D), "YYYY-MM" (M), "YYYY" (A) */
  start: string;
  end: string;
  /** e.g. "Updated on November 03, 2026" */
  note?: string;
  /** what the price measures, from the source's own description */
  basis?: string;
  /** dates the basis changed (monthly series) */
  breaks?: PriceBreak[];
  /** runs of calendar years whose twelve monthly values are one and the same number (what is observed, not what the source says it publishes) */
  annual?: [number, number][];
  /** months the source marks as estimates */
  est?: [string, string][];
  stats?: PriceStats;
  /** the series has no page in the atlas: the family it is listed under */
  fam?: string;
  /** annual real-price counterpart (constant 2010 US dollars) */
  real?: string;
  /** daily series: the monthly series of the same benchmark (it covers a month the daily file has too few quotes for) */
  monthly?: string;
  /** a real-price series: the nominal series it deflates. Not listed in the picker or on the board */
  realOf?: string;
  hidden?: boolean;
  /** the source stopped publishing it (kept as history) */
  closed?: boolean;
}

/** Packed price series. Monthly: start "YYYY-MM" + consecutive values. Annual: start "YYYY". Daily: d = days since 1970-01-01. */
export interface PriceSeries {
  id: string;
  freq: 'D' | 'M' | 'A';
  start?: string;
  d?: number[];
  v: (number | null)[];
}
