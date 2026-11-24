/**
 * The search field's index and what a result does. The index is built in the browser, the first time the field gets the
 * focus, from the catalogues the site loads anyway (commodities, countries, routes, chokepoints, vessel classes,
 * infrastructure) and small ones: the events, the price series, the ports of the lanes, the two company lists and, when a
 * country and a commodity are typed together, the pairs file of that commodity.
 *
 * A result does what the click on the map or on a list of the site does: the same selection, so the same link.
 */
import { batch } from '@preact/signals';
import type { Chokepoint, Company, FreightEvent, Route, ShippingCompanies, VesselClass } from '../types';
import { commodities, commodityMeta, countries, countryName, isCountry, load, loadCatalogue } from './data';
import { FAMILY_LABEL } from './format';
import { GROUP_LABEL, LANE_GROUPS, SEGMENT_LABEL, finderCommodity, loadEvents, loadPairs, loadRoutes, loadChokepoints, loadVesselClasses, decodePairs, openVesselClass } from './freight';
import { loadPriceIndex, openPrices, spreadMetas, FREQ_WORD, type PriceMeta } from './prices';
import {
  panelCollapsed, rfCommodity, rfDest, rfFrom, rfGroup, rfOrigin, routeFinderOpen, select, setFamily, family, commodity, vesselClasses, sheetSnap,
  companyFilter,
} from './store';
import { groupKinds, matchKind, norm, prepare, rank, tokens, type Searchable, type Tier } from './searchMatch';
import { loadInfra } from '../map/modules/infrastructure';
import { flyToWorld, isSheetLayout } from '../map/controller';
import { INFRA_META } from '../components/ui';
import { companySlug, loadAllCompanies, type CompanyMap } from '../components/Companies';
import { nameForms } from './companyAssets';

export type Kind = 'commodity' | 'country' | 'route' | 'chokepoint' | 'vessel' | 'company' | 'infra' | 'port' | 'event' | 'price';

/** Every year an event spans, as text: "2024" finds an event that began in 2023 and ended in 2025. */
function eventYears(date: string, end?: string | null): string[] {
  const a = Number(date.slice(0, 4));
  const b = Number((end ?? date).slice(0, 4));
  const out: string[] = [];
  for (let y = a; y <= b && out.length < 60; y++) out.push(String(y));
  return out;
}

/** Kinds in the order the lists show them, with the words the site uses for them. */
export const KINDS: { kind: Kind; label: string; one: string }[] = [
  { kind: 'commodity', label: 'Commodities', one: 'commodity' },
  { kind: 'country', label: 'Countries', one: 'country' },
  { kind: 'route', label: 'Freight routes', one: 'freight route' },
  { kind: 'chokepoint', label: 'Chokepoints', one: 'chokepoint' },
  { kind: 'vessel', label: 'Vessel classes', one: 'vessel class' },
  { kind: 'company', label: 'Companies', one: 'company' },
  { kind: 'infra', label: 'Infrastructure', one: 'infrastructure asset' },
  { kind: 'port', label: 'Ports of the lanes', one: 'port of the lanes' },
  { kind: 'event', label: 'Events', one: 'event' },
  { kind: 'price', label: 'Price series', one: 'price series' },
];
const KIND_ORDER = Object.fromEntries(KINDS.map((k, i) => [k.kind, i])) as Record<Kind, number>;

export interface Item {
  /** `kind:id`, unique */
  key: string;
  kind: Kind;
  label: string;
  /** one line under the label: what it is, where, who runs it */
  sub: string;
  /** a code shown on the right (a route code, an ISO code) */
  badge?: string;
  d: Searchable;
  /** position in the kind's own order (a list with no query) */
  order: string | number;
  open: () => void;
}

export interface Group {
  kind: Kind | 'pair';
  label: string;
  /** the items shown */
  items: Item[];
  /** how many items match (more than are shown when the group is cut) */
  total: number;
  /** how well its best item matches (see Tier): 4 is an exact name or code */
  tier: Tier;
}

// ---------------------------------------------------------------- opening what a result names

/** The commodity picked from the panel's list: its family follows, the filters of other tabs are dropped, the map frames the world. */
function openCommodity(id: string) {
  const meta = commodityMeta(id);
  if (!meta) return;
  batch(() => {
    if (family.peek() !== meta.family) setFamily(meta.family);
    vesselClasses.value = new Set();
    commodity.value = id;
    select({ kind: 'commodity', id });
  });
  flyToWorld(true);
}

/** The Route finder with one end of a question filled in: the link form `rf=<commodity>:<o|d>:<origin>-<destination>`. */
function openFinder(k: string, from: 'o' | 'd', iso: string) {
  batch(() => {
    rfCommodity.value = finderCommodity(k);
    rfFrom.value = from;
    rfOrigin.value = from === 'o' ? iso : null;
    rfDest.value = from === 'd' ? iso : null;
    rfGroup.value = null;
    routeFinderOpen.value = true;
    panelCollapsed.value = false;
    // tablet and phone: the controls are a sheet under the page, so the page gives way to it
    if (isSheetLayout()) {
      select(null);
      sheetSnap.value = 'half';
    }
  });
}

// ---------------------------------------------------------------- the index

const COUNTRY_ALIASES: Record<string, string[]> = {
  USA: ['us', 'usa', 'america', 'united states of america'],
  GBR: ['uk', 'britain', 'great britain', 'england'],
  ARE: ['uae', 'emirates'],
  RUS: ['russian federation'],
  KOR: ['korea', 'republic of korea'],
  PRK: ['dprk'],
  CZE: ['czech republic'],
  TUR: ['turkiye'],
  MMR: ['burma'],
  CIV: ['ivory coast'],
  COD: ['drc', 'congo kinshasa', 'democratic republic of the congo'],
  COG: ['congo brazzaville', 'republic of the congo'],
  NLD: ['holland', 'the netherlands'],
  IRN: ['persia'],
  SWZ: ['swaziland'],
  MKD: ['macedonia'],
};

/** Trade names of the products that a commodity page holds besides the one in its name (the fertiliser pages hold several customs groups). */
const COMMODITY_ALIASES: Record<string, string[]> = {
  urea: ['ammonia', 'ammonium nitrate', 'calcium ammonium nitrate', 'CAN', 'ammonium nitrate with limestone', 'UAN', 'urea ammonium nitrate', 'ammonium sulphate', 'ammonium sulfate', 'nitrogen fertiliser', 'nitrogen fertilizer', 'fertiliser', 'fertilizer'],
  phosphate: ['phosphate rock', 'DAP', 'diammonium phosphate', 'MAP', 'monoammonium phosphate', 'TSP', 'triple superphosphate', 'superphosphate', 'phosphoric acid', 'phosphate fertiliser', 'fertilizer'],
  potash: ['potassium chloride', 'muriate of potash', 'MOP', 'SOP', 'sulphate of potash', 'potassium sulphate', 'potassium sulfate', 'potassium fertiliser', 'fertilizer'],
  sulphur: ['sulfur', 'brimstone', 'fertiliser', 'fertilizer'],
  // the grains and oilseeds (M-023): the pages hold the oils, meals and flour too
  wheat: ['wheat flour', 'flour'],
  corn: ['maize', 'distillers grains', 'DDGS', 'brewers grains', 'brewing and distilling dregs'],
  barley: ['malting barley', 'feed barley'],
  sorghum: ['milo', 'grain sorghum'],
  sunflower: ['sunflower seed', 'sunflower oil', 'sunflower meal', 'safflower oil'],
  rapeseed: ['rapeseed oil', 'canola oil', 'rapeseed meal', 'canola meal', 'colza', 'mustard oil'],
  // no alias with the word "dried": it would be found by "DRI", the direct-reduced iron of the pig iron page
  pulses: ['peas', 'chickpeas', 'lentils', 'beans', 'dry beans', 'dry peas', 'legumes', 'garbanzo'],
  npk: ['compound fertiliser', 'compound fertilizer', 'NPK', 'two-nutrient compound', 'NP fertiliser', 'PK fertiliser', 'ammonium phosphate nitrate', 'fertiliser', 'fertilizer'],
  // the metal bulks (A-010): the trade names of the raw materials of steel and of the ferro-alloys, as a buyer writes them
  'ferrous-scrap': ['scrap', 'steel scrap', 'iron scrap', 'metal scrap', 'ferrous waste', 'recycled steel', 'HMS', 'heavy melting scrap', 'shredded scrap'],
  'pig-iron': ['pig iron', 'DRI', 'HBI', 'hot briquetted iron', 'direct reduced iron', 'direct-reduced iron', 'sponge iron', 'spongy iron', 'spiegeleisen'],
  chromium: ['chromite', 'chrome', 'chrome ore', 'chromium ore'],
  'ferro-alloys': ['ferroalloys', 'ferro alloys', 'ferrochrome', 'ferrochromium', 'ferro-chromium', 'ferromanganese', 'ferro-manganese', 'silicomanganese', 'silico-manganese', 'ferrosilicon', 'ferro-silicon', 'ferromolybdenum', 'ferrovanadium', 'ferroniobium', 'ferrotungsten', 'ferrotitanium'],
  'met-coal': ['coke', 'metallurgical coke', 'semi-coke', 'coking coal'],
  molybdenum: ['molybdenite', 'moly', 'molybdenum concentrate'],
  graphite: ['natural graphite', 'flake graphite'],
};

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const joinSub = (...p: (string | undefined | false)[]) => p.filter(Boolean).join(' · ');

function make(kind: Kind, id: string, label: string, sub: string, d: Searchable, order: string | number, open: () => void, badge?: string): Item {
  return { key: `${kind}:${id}`, kind, label, sub, badge, d, order, open };
}

/** "Crude oil, Saudi Arabia to China": what a lane id `<group>:<origin>-<destination>` opens, in the words of the lane page. */
function laneText(id: string): string {
  const [g, ends = ''] = id.split(':');
  const [o, d] = ends.split('-');
  return `${cap(GROUP_LABEL[g] ?? commodityMeta(g)?.name ?? g)}, ${countryName(o)} to ${countryName(d)}`;
}

let indexPromise: Promise<Item[]> | null = null;
/** Every item. Built once; a file that cannot be loaded leaves its kind out, the others still work. */
export function loadIndex(): Promise<Item[]> {
  if (!indexPromise) {
    indexPromise = build().catch((e) => {
      indexPromise = null;
      throw e;
    });
  }
  return indexPromise;
}

interface PortIndex {
  /** `asset`: the port asset of the infrastructure layer the row is (`port:busan`); `aka`: the names of that asset the routes and the trade engine use */
  ports: { id: string; name: string; c: string; n: number; g: string[]; lane: string | null; asset?: string; aka?: string[] }[];
}

/** A shipping segment in the words of the site, and the kind of vessel class page that lists its companies. */
const SHIP_SEGMENT: Record<string, { word: string; classSegment: string }> = {
  'dry-bulk': { word: 'dry bulk', classSegment: 'dry' },
  tankers: { word: 'tankers', classSegment: 'tanker' },
  gas: { word: 'gas carriers', classSegment: 'gas' },
  charterers: { word: 'charterer', classSegment: 'dry' },
  brokers: { word: 'shipbroking', classSegment: 'tanker' },
  terminals: { word: 'liquid bulk terminals', classSegment: 'tanker' },
};

/**
 * One item per company of the two lists, with the commodities (or shipping segments) it stands under. It opens the page
 * that lists it: the commodity page of its first commodity, or the vessel class page of its first class (of its segment's
 * first class when the page read names none), with the companies unfolded on its row (`co=` in the link).
 */
function companyItems(map: CompanyMap | null, shipping: ShippingCompanies | null, vessels: VesselClass[] | null): Item[] {
  const found = new Map<string, { c: Company; k: string[]; seg: string[]; classes: string[] }>();
  const entry = (c: Company) => {
    let e = found.get(c.name);
    if (!e) found.set(c.name, (e = { c, k: [], seg: [], classes: [] }));
    return e;
  };
  for (const [k, groups] of Object.entries(map ?? {}))
    for (const list of [groups.producers, groups.processors, groups.traders]) for (const c of list ?? []) if (!entry(c).k.includes(k)) entry(c).k.push(k);
  for (const [seg, list] of Object.entries(shipping ?? {}))
    for (const c of list ?? []) {
      const e = entry(c);
      if (!e.seg.includes(seg)) e.seg.push(seg);
      for (const v of c.classes ?? []) if (!e.classes.includes(v)) e.classes.push(v);
    }
  const out: Item[] = [];
  for (const { c, k, seg, classes } of found.values()) {
    const kNames = k.map((x) => commodityMeta(x)?.name ?? x);
    const segWords = seg.map((s) => SHIP_SEGMENT[s]?.word ?? s);
    const what = [kNames.length > 3 ? `${kNames.slice(0, 3).join(', ')} and ${kNames.length - 3} more` : kNames.join(', '), segWords.length ? `shipping: ${segWords.join(', ')}` : '']
      .filter(Boolean)
      .join('; ');
    const vclass = classes[0] ?? vessels?.find((v) => v.segment === SHIP_SEGMENT[seg[0]]?.classSegment)?.id;
    const slug = companySlug(c.name);
    const open = () =>
      batch(() => {
        if (k.length) openCommodity(k[0]);
        else if (vclass) openVesselClass(vclass);
        else return;
        companyFilter.value = slug;
      });
    out.push(
      make(
        'company', slug, c.name, joinSub('Company', c.hq ? countryName(c.hq) : '', what),
        prepare([c.name, ...nameForms(c.name)], [], [c.hq ? countryName(c.hq) : '', c.role, ...kNames, ...segWords, ...(seg.length ? ['shipping'] : []), 'company']),
        c.name, open,
      ),
    );
  }
  return out;
}

async function build(): Promise<Item[]> {
  if (!commodities.value.length) await loadCatalogue();
  const opt = <T,>(p: Promise<T>): Promise<T | null> => p.catch(() => null);
  const [routes, cps, vessels, events, prices, infra, ports, cos] = await Promise.all([
    opt<Route[]>(loadRoutes()),
    opt<Chokepoint[]>(loadChokepoints()),
    opt<VesselClass[]>(loadVesselClasses()),
    opt<FreightEvent[]>(loadEvents()),
    opt<PriceMeta[]>(loadPriceIndex()),
    opt(loadInfra()),
    opt(load<PortIndex>('freight/ports.json')),
    opt(loadAllCompanies()),
  ]);
  const out: Item[] = [];
  const vesselName = (id: string) => vessels?.find((v) => v.id === id)?.name ?? id;
  const cpName = (id: string) => cps?.find((c) => c.id === id)?.name ?? id;

  for (const c of commodities.value) {
    out.push(make('commodity', c.id, c.name, FAMILY_LABEL[c.family], prepare([c.name, ...(COMMODITY_ALIASES[c.id] ?? [])], [c.id], [FAMILY_LABEL[c.family], 'commodity']), c.rank, () => openCommodity(c.id)));
  }
  for (const c of Object.values(countries.value)) {
    out.push(
      make('country', c.c, c.name, c.region ?? 'Country', prepare([c.name, ...(COUNTRY_ALIASES[c.c] ?? [])], [c.c, (c as { a2?: string }).a2 ?? ''], [c.region ?? '', 'country']), c.name, () => select({ kind: 'country', id: c.c }), c.c),
    );
  }
  // a short code that two routes share (C14 and C14_182, C10_14 and C10_182) would be one badge on both: those show their full id
  const shortCodes = new Map<string, number>();
  for (const r of routes ?? []) if (r.benchmark) shortCodes.set(r.id.split('_')[0], (shortCodes.get(r.id.split('_')[0]) ?? 0) + 1);
  for (const r of routes ?? []) {
    const code = r.benchmark ? r.id.split('_')[0] : '';
    const badge = code && (shortCodes.get(code) ?? 0) > 1 && r.id !== code ? r.id : code;
    const kindText = r.benchmark ? 'Benchmark route' : 'Atlas corridor';
    out.push(
      make(
        // an ended route says so: "C10" finds the ended C10_14 and the C10_182 that replaced it, with the same badge
        'route', r.id, r.name, joinSub(kindText, vesselName(r.vclass), r.discontinued ? 'ended' : ''),
        prepare([r.name], code ? [r.id, code] : [], [r.from.region, r.to.region, ...r.from.ports, ...r.to.ports, vesselName(r.vclass), 'freight route', ...r.cargoes.map((k) => commodityMeta(k)?.name ?? k)]),
        `${r.benchmark ? 0 : 1}${r.name}`, () => select({ kind: 'route', id: r.id }), badge || undefined,
      ),
    );
  }
  for (const c of cps ?? []) {
    out.push(make('chokepoint', c.id, c.name, cap(c.kind), prepare([c.name], [c.id], [c.kind, 'chokepoint']), c.name, () => select({ kind: 'chokepoint', id: c.id })));
  }
  for (const v of vessels ?? []) {
    out.push(make('vessel', v.id, v.name, SEGMENT_LABEL[v.segment] ?? cap(v.segment), prepare([v.name], [v.id], [SEGMENT_LABEL[v.segment] ?? v.segment, 'vessel class', 'ship']), v.name, () => openVesselClass(v.id)));
  }
  for (const v of companyItems(cos?.map ?? null, cos?.shipping ?? null, vessels)) out.push(v);
  // the names the routes and the trade engine use for a port asset ("Pusan" for Busan, "Odessa" for Odesa)
  const akaOf = new Map<string, string[]>();
  for (const p of ports?.ports ?? []) if (p.asset) akaOf.set(p.asset, [...(akaOf.get(p.asset) ?? []), ...(p.aka ?? [p.name])]);
  for (const f of infra ?? []) {
    const p = f.p;
    const type = INFRA_META[p.type]?.label ?? p.type;
    out.push(
      make(
        'infra', `${p.id}:${p.type}`, p.name, joinSub(type, countryName(p.c), p.operator),
        prepare([p.name, ...(akaOf.get(`${p.type}:${p.id}`) ?? [])], [p.id], [p.operator ?? '', countryName(p.c), type, ...(p.cs ?? []).map(countryName), ...p.k.map((k) => commodityMeta(k)?.name ?? k)]),
        p.name, () => select({ kind: 'infra', id: p.id, layer: p.type }),
      ),
    );
  }
  // a port the infrastructure layer has (Port Hedland) is found as that asset; the lanes' ports it lacks (Jurong) are found here,
  // and each says what it opens: the largest lane that uses it, or the page of its country. A port that would open nothing is not listed.
  const portAssets = (infra ?? []).filter((f) => f.p.type === 'port');
  for (const p of ports?.ports ?? []) {
    const n = norm(p.name);
    if (p.asset) continue; // the same place as a port asset (its locode): found as the asset
    if (portAssets.some((f) => f.p.c === p.c && (norm(f.p.name) === n || norm(f.p.name).startsWith(`${n} `)))) continue;
    if (!p.lane && !isCountry(p.c)) continue;
    const cargo = p.g.map((g) => GROUP_LABEL[g] ?? commodityMeta(g)?.name ?? g).join(', ');
    out.push(
      make(
        'port', p.id, p.name, joinSub('Port', countryName(p.c), p.lane ? `opens ${laneText(p.lane)}` : `opens the page of ${countryName(p.c)}`), prepare([p.name], [p.id], [countryName(p.c), cargo, 'port']), p.name,
        () => (p.lane ? select({ kind: 'lane', id: p.lane }) : select({ kind: 'country', id: p.c })), p.id,
      ),
    );
  }
  for (const e of events ?? []) {
    out.push(
      make(
        'event', e.id, e.title, joinSub(cap(e.kind), e.end ? `${e.date} to ${e.end}` : e.date), prepare([e.title], [e.id], [e.id, ...eventYears(e.date, e.end), e.kind, 'event', ...(e.countries ?? []).map(countryName), ...(e.chokepoints ?? []).map(cpName), ...(e.commodities ?? []).map((k) => commodityMeta(k)?.name ?? k)]),
        // newest first
        -Date.parse(e.date.length === 4 ? `${e.date}-01-01` : e.date.length === 7 ? `${e.date}-01` : e.date), () => select({ kind: 'event', id: e.id }),
      ),
    );
  }
  if (prices) {
    for (const m of [...prices.filter((x) => !x.hidden && !x.realOf), ...spreadMetas(prices)]) {
      const k = commodityMeta(m.k)?.name;
      out.push(
        make(
          'price', m.id, m.name, joinSub(k, m.unit, FREQ_WORD[m.freq], `${m.start.slice(0, 4)} to ${m.end.slice(0, 4)}`),
          prepare([m.name], [m.id], [k ?? '', m.unit, FREQ_WORD[m.freq], 'price']), m.name, () => openPrices({ commodity: m.k === 'index' || m.k === 'freight' ? null : m.k, series: [m.id] }),
        ),
      );
    }
  }
  return out;
}

// ---------------------------------------------------------------- searching

const PER_GROUP = 5;

function best(q: string[], items: Item[], kind: Kind): { item: Item; s: number } | null {
  let top: { item: Item; s: number } | null = null;
  for (const it of items) {
    if (it.kind !== kind) continue;
    const r = rank(q, it.d);
    // a name or a code typed whole or in part: no fuzzy half-match, no word found inside another ("canal" is not "canola")
    if (r.tier >= 3 && (!top || r.s > top.s)) top = { item: it, s: r.s };
  }
  return top;
}

/**
 * "japan crude", "soy brazil": the words split in two, one half a country and the other a commodity. Returns the two
 * items, the best split. Each half has to name its object, whole or in part (a word of the name or its beginning).
 */
export function countryAndCommodity(q: string[], items: Item[]): { country: Item; commodity: Item } | null {
  if (q.length < 2) return null;
  let found: { country: Item; commodity: Item; s: number } | null = null;
  for (let i = 1; i < q.length; i++) {
    for (const [a, b] of [[q.slice(0, i), q.slice(i)], [q.slice(i), q.slice(0, i)]]) {
      const c = best(a, items, 'country');
      const k = best(b, items, 'commodity');
      if (c && k && (!found || c.s + k.s > found.s)) found = { country: c.item, commodity: k.item, s: c.s + k.s };
    }
  }
  return found;
}

/**
 * The groups of results for a query. `scope`: one kind, every match of it (the list of a kind). With no query and no
 * scope the result is empty: the field then shows the kinds with their counts (`counts`). The order of the groups is
 * `groupKinds`'s (searchMatch.ts).
 */
export function search(query: string, items: Item[], scope: Kind | null): Group[] {
  const q = tokens(query);
  if (scope) {
    const m = matchKind(q, items, scope);
    return m.length ? [{ kind: scope, label: KINDS[KIND_ORDER[scope]].label, items: m.map((x) => x.item), total: m.length, tier: Math.max(...m.map((x) => x.tier)) as Tier }] : [];
  }
  if (!q.length) return [];
  return groupKinds(q, items, PER_GROUP).map((g) => ({ kind: g.kind as Kind, label: KINDS[KIND_ORDER[g.kind as Kind]].label, items: g.items, total: g.total, tier: g.tier }));
}

export function counts(items: Item[]): { kind: Kind; label: string; one: string; n: number }[] {
  const n = new Map<Kind, number>();
  for (const it of items) n.set(it.kind, (n.get(it.kind) ?? 0) + 1);
  return KINDS.map((k) => ({ ...k, n: n.get(k.kind) ?? 0 })).filter((k) => k.n > 0);
}

/**
 * The lanes between a country and a commodity: the Route finder questions the pairs table allows, "into" the country
 * (it is the destination of a recorded pair) and "out of" it (the origin). Empty when the commodity has no lanes.
 */
export async function finderQuestions(country: Item, k: Item): Promise<Item[]> {
  const kid = k.key.slice(k.kind.length + 1);
  const iso = country.key.slice(country.kind.length + 1);
  const groups = LANE_GROUPS[kid] ?? [];
  const files = (await Promise.all(groups.map((g) => loadPairs(g).catch(() => null)))).filter((f) => !!f);
  const pairs = files.flatMap((f) => decodePairs(f!));
  const out: { kt: number; item: Item }[] = [];
  for (const [from, side] of [['d', 'into'], ['o', 'out of']] as const) {
    const mine = pairs.filter((p) => (from === 'd' ? p.d : p.o) === iso && p.kt > 0);
    if (!mine.length) continue;
    const n = mine.length;
    out.push({
      kt: mine.reduce((a, p) => a + p.kt, 0),
      item: make(
        'route', `finder-${kid}-${from}-${iso}`, `${k.label} ${side} ${country.label}`, `Route finder · ${n} recorded ${n === 1 ? 'pair' : 'pairs'} of the latest year`,
        prepare([`${k.label} ${side} ${country.label}`]), 0, () => openFinder(kid, from, iso),
      ),
    });
  }
  // the direction that carries more tonnes first
  return out.sort((a, b) => b.kt - a.kt).map((x) => x.item);
}
