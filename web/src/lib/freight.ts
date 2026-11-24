/**
 * Freight data access and shared constants (vessel segments, colours, lane groups).
 * All loaders are cached by lib/data.ts.
 */
import { computed, signal } from '@preact/signals';
import type { CaveatEntry, CaveatsFile, Chokepoint, FreightEvent, Lane, LaneFile, PairsFile, PortRiver, PortwatchSeries, Route, Segment, VesselClass } from '../types';
import { load } from './data';
import { groupChipLabels, routeChipLabels } from './cargoChips';
import { atlasKind } from './format';
import { commodity, family, layers, select, selection, setFamily, toggleLayer, vesselClasses } from './store';

/** Customs product groups with lanes, per atlas commodity id. */
export const LANE_GROUPS: Record<string, string[]> = {
  'crude-oil': ['crude-oil'],
  'refined-products': ['refined-products'],
  lng: ['lng'],
  lpg: ['lpg'],
  'thermal-coal': ['coal'],
  'met-coal': ['coal', 'coke'],
  'iron-ore': ['iron-ore'],
  steel: ['steel'],
  copper: ['copper-ore', 'copper-refined'],
  aluminium: ['aluminium'],
  bauxite: ['bauxite', 'alumina'],
  nickel: ['nickel-ore', 'nickel-int', 'nickel-fe'],
  lithium: ['spodumene', 'lithium'],
  zinc: ['zinc-ore', 'zinc-metal'],
  lead: ['lead-ore', 'lead-metal'],
  tin: ['tin-metal', 'tin-ore'],
  cobalt: ['cobalt'],
  'rare-earths': ['rare-earths'],
  manganese: ['manganese'],
  chromium: ['chromium-ore'],
  'ferro-alloys': ['ferro-chromium', 'ferro-manganese', 'silico-manganese', 'ferro-silicon'],
  'ferrous-scrap': ['ferrous-scrap'],
  'pig-iron': ['pig-iron', 'dri'],
  wheat: ['wheat'],
  corn: ['corn'],
  soybeans: ['soybeans'],
  soymeal: ['soymeal'],
  soyoil: ['soyoil'],
  rice: ['rice'],
  sugar: ['sugar'],
  coffee: ['coffee'],
  cocoa: ['cocoa'],
  cotton: ['cotton'],
  'palm-oil': ['palm-oil'],
  rapeseed: ['rapeseed', 'rapeseed-oil', 'rapeseed-meal'],
  barley: ['barley'],
  sorghum: ['sorghum'],
  sunflower: ['sunflower-seed', 'sunflower-oil', 'sunflower-meal'],
  pulses: ['pulses'],
  potash: ['potash', 'potassium-sulphate'],
  phosphate: ['phosphate-rock', 'dap', 'monoammonium-phosphate', 'superphosphates', 'phosphoric-acid'],
  urea: ['urea', 'ammonia', 'ammonium-nitrate', 'ammonium-nitrate-limestone', 'uan', 'ammonium-sulphate'],
  sulphur: ['sulphur'],
  npk: ['npk', 'npk-two-nutrient'],
};

/** Groups shown in the default "global flows" overview, with how many lanes of each. */
export const OVERVIEW: { group: string; top: number }[] = [
  { group: 'crude-oil', top: 10 },
  { group: 'iron-ore', top: 5 },
  { group: 'coal', top: 8 },
  { group: 'lng', top: 8 },
  { group: 'soybeans', top: 4 },
  { group: 'refined-products', top: 6 },
  { group: 'bauxite', top: 2 },
  { group: 'corn', top: 4 },
  { group: 'wheat', top: 4 },
  { group: 'lpg', top: 4 },
];

export const SEGMENT_LABEL: Record<Segment, string> = {
  dry: 'Dry bulk',
  tanker: 'Tankers',
  gas: 'Gas carriers',
  container: 'Container',
};

/** Route line colours by vessel segment (freight layer). */
export const SEGMENT_COLOR: Record<Segment, string> = {
  dry: '#9db7ff',
  tanker: '#ffb547',
  gas: '#7ef0d8',
  container: '#c7a3ff',
};

/** Human labels for chokepoint share keys that are not commodity ids. */
export const SHARE_LABEL: Record<string, string> = {
  'petroleum-liquids': 'All oil (crude + products)',
};

// ---------------------------------------------------------------- loaders

export const loadLaneFile = (group: string) => load<LaneFile>(`freight/lanes/${group}.json`);
export const loadPairs = (group: string) => load<PairsFile>(`freight/pairs/${group}.json`);
export const loadCaveats = () => load<CaveatsFile>('freight/caveats.json');
export const loadRoutes = () => load<Route[]>('freight/routes.json');
export const loadRouteGeo = () => load<GeoJSON.FeatureCollection<GeoJSON.LineString, { id: string; kind: 'route' | 'alt' }>>('freight/routes.geo.json');
export const loadChokepoints = () => load<Chokepoint[]>('freight/chokepoints.json');
export const loadVesselClasses = () => load<VesselClass[]>('freight/vessel-classes.json');
export const loadEvents = () => load<FreightEvent[]>('freight/events.json');
export const loadPortwatch = (id: string) => load<PortwatchSeries>(`freight/portwatch/${id}.json`);

// ---------------------------------------------------------------- pairs table

/** What a recorded pair is: `sea`, `transit` (sea through a foreign port), `mixed` (sea and overland, split not known) or `land`. */
export type PairKind = 'sea' | 'transit' | 'mixed' | 'land';
const PAIR_KINDS: PairKind[] = ['sea', 'transit', 'mixed', 'land'];

/** A port of a pairs file. */
export interface PairPort {
  id: string;
  name: string;
  c: string;
  zone: string | null;
  /** why the atlas uses the port (PortRef.basis), when the file says */
  basis?: string;
  /** the port is up a river: the distance of the pair includes the leg */
  river?: PortRiver;
}

/** One row of a pairs file, decoded. */
export interface Pair {
  group: string;
  o: string;
  d: string;
  /** customs tonnes, thousands */
  kt: number;
  kind: PairKind;
  /** null when the pair is not routed (no sea leg, no gateway, or the same port at both ends) */
  load: PairPort | null;
  dis: PairPort | null;
  /** distance of the main route, nautical miles (0 = not routed) */
  nm: number;
  /** primary vessel class */
  cls: string | null;
  /** passages every option has to cross */
  via: string[];
  /** passages only some coast options or parallel passages cross */
  viaAlt: string[];
  /** the same, as lists of which one is used (see altLists) */
  viaAltLists: string[][];
  /** tonnage estimated from the declared value (an Atlas estimate) */
  est: boolean;
  /** a caveat of freight/caveats.json applies */
  caveat: boolean;
  /** a main lane exists, id `<group>:<o>-<d>` */
  lane: boolean;
  /** a check flags the pair (a large change against the previous year, or against a national statistic) */
  flagged: boolean;
}

/** Gate ids of a bit mask (bit i = gates[i]). Masks are at most 31 bits wide, so they stay in JavaScript's 32-bit integers. */
/** A lane's latest flow is an Atlas estimate: flagged so, or credited to the atlas with a note that says so (a group the atlas
 * reads from a mixed customs code). Estimates are printed with two significant digits and the "Atlas estimate" mark. */
export function laneEst(lane: { flow: { s: string; est?: boolean; n?: string } }): boolean {
  return atlasKind(lane.flow) === 'est';
}

/** A lane figure in Mt, whatever the unit of its file: a group under 1 Mt a year is published in kt (build_lanes.py SMALL_MT),
 * so figures of several files are compared, summed or scaled in Mt. */
export const laneMt = (v: number, unit: string | undefined): number => (unit === 'kt' ? v / 1e3 : v);

/** Who ships through the foreign port of "Sea via ...": "Zambia is landlocked", or for an end with a coast of its own that the
 * atlas sends through another country's port, "DR Congo ships through a port of Tanzania" (from the adjacency data the files
 * carry, not a list). */
export function transitWho(ends: { end: string; c: string; landlocked?: boolean }[], name: (iso3: string) => string): string {
  const parts = ends.map((e) => (e.landlocked === false ? `${name(e.end)} ships through a port of ${name(e.c)}` : `${name(e.end)} is landlocked`));
  return parts.length ? `${parts.join('; ')}.` : '';
}

export function maskGates(mask: number, gates: string[]): string[] {
  const out: string[] = [];
  for (let i = 0; i < gates.length && i < 31; i++) if ((mask >>> i) & 1) out.push(gates[i]);
  return out;
}

/** Decode the rows of a pairs file (columns are found by name, so their order may change). */
export function decodePairs(file: PairsFile): Pair[] {
  const ix = Object.fromEntries(file.cols.map((c, i) => [c, i]));
  // a port row carries its basis as a loading port (fifth element) and as a discharging port (sixth); an older
  // file has one basis for both
  const port = (i: number, discharge = false): PairPort | null => {
    const p = i >= 0 ? file.ports[i] : undefined;
    if (!p) return null;
    const b = discharge && p.length > 5 ? p[5] : p[4];
    return { id: p[0], name: p[1], c: p[2], zone: p[3] ?? null, basis: b != null ? file.bases?.[b] : undefined, river: file.rivers?.[p[0]] };
  };
  return file.rows.map((r) => {
    const f = Number(r[ix.f] ?? 0);
    const cls = Number(r[ix.cls]);
    const viaAlt = maskGates(Number(r[ix.alt]) || 0, file.gates);
    return {
      group: file.group,
      o: String(r[ix.o]),
      d: String(r[ix.d]),
      kt: Number(r[ix.kt]),
      kind: PAIR_KINDS[Number(r[ix.m])] ?? 'land',
      load: port(Number(r[ix.load])),
      dis: port(Number(r[ix.dis]), true),
      nm: Number(r[ix.nm]) || 0,
      cls: cls >= 0 ? (file.classes[cls] ?? null) : null,
      via: maskGates(Number(r[ix.via]) || 0, file.gates),
      viaAlt,
      viaAltLists: altLists(viaAlt),
      est: !!(f & 1),
      caveat: !!(f & 2),
      lane: !!(f & 4),
      flagged: !!(f & 8),
    };
  });
}

/**
 * The caveat that applies to a pair, or null: an entry for the exact pair wins over one for the origin
 * (same rule as pipeline/trade/caveats.py `lookup`).
 */
export function caveatFor(file: CaveatsFile | null, group: string, o: string, d: string): { id: string; entry: CaveatEntry } | null {
  let best: { id: string; entry: CaveatEntry } | null = null;
  for (const [id, entry] of Object.entries(file ?? {})) {
    if (entry.group !== group || entry.o !== o || (entry.d != null && entry.d !== d)) continue;
    if (entry.d === d) return { id, entry };
    best ??= { id, entry };
  }
  return best;
}

/** Caveats that name this origin and group but no destination (the origin's own reporting gap), for an origin with nothing recorded. */
export function originCaveats(file: CaveatsFile | null, groups: string[], o: string): { id: string; entry: CaveatEntry }[] {
  return Object.entries(file ?? {})
    .filter(([, e]) => e.o === o && e.d == null && e.group != null && groups.includes(e.group))
    .map(([id, entry]) => ({ id, entry }));
}

/** Laden days of a sea leg of `nm` nautical miles for a vessel class, at its assumed laden service speed (Atlas assumption); null when the class has no speed. */
export function ladenDays(nm: number, vclass: string | null): { days: number; speedKn: number; note?: string } | null {
  const v = vclass ? vesselById.value[vclass] : undefined;
  const kn = v?.speed?.v ?? v?.speedKn;
  if (!kn || !(nm > 0)) return null;
  return { days: Math.round((nm / (kn * 24)) * 10) / 10, speedKn: kn, note: v?.speed?.n ?? v?.speedNote };
}

/** Words for a class with no assumed speed in vessel-classes.json (container ships): the days of a leg cannot be computed from the catalogue. */
export const NO_SPEED = 'no assumed speed for this class';

/** True once the vessel catalogue is loaded and the class has no assumed laden speed in it. */
export function lacksSpeed(vclass: string | null | undefined): boolean {
  if (!vclass || !vesselClassList.value.length) return false;
  const v = vesselById.value[vclass];
  return !(v?.speed?.v ?? v?.speedKn);
}

// ---------------------------------------------------------------- passages that are crossed together

/**
 * What "at least" and "up to" mean (the one definition, printed on the chokepoint page and in About).
 * "at least" counts the pairs whose assumed route has to cross the passage; "up to" adds the pairs that may cross it.
 */
export const ESTIMATE_DEFINITION =
  'At least: customs tonnage of every recorded seaborne pair whose assumed route has to cross this passage. Up to: adds the pairs that may cross it, because they can use a parallel passage of similar length or load on another coast. Mixed sea-and-overland pairs and trades that customs data do not record are in neither.';

/** Passages a ship crosses together on one parallel option (pipeline/freight/routing.py, PARALLEL). */
const CROSSED_TOGETHER: string[][] = [
  ['malacca', 'singapore'],
  ['lombok', 'makassar'],
];

/** Every passage of a parallel group: a pairs file keeps one mask for all of a pair's lists, which this splits again. */
const PARALLEL_GROUPS: string[][] = [
  ['sunda', 'malacca', 'singapore', 'lombok', 'makassar'],
  ['taiwan-strait', 'luzon'],
];

/** The options of a `viaAlt` list: the passages of one option are crossed together, so they stay together ([[sunda], [malacca, singapore]]). */
export function altOptions(list: string[]): string[][] {
  const out: string[][] = [];
  const done = new Set<string>();
  for (const id of list) {
    if (done.has(id)) continue;
    const set = CROSSED_TOGETHER.find((g) => g.includes(id));
    const option = set ? list.filter((x) => set.includes(x)) : [id];
    option.forEach((x) => done.add(x));
    out.push(option);
  }
  return out;
}

/** Two or more options: one is used. A single option: the passage is crossed only on some options, or on none of a similar length. */
export const altLabel = (list: string[]) => (altOptions(list).length > 1 ? 'One of:' : 'May also cross:');

/** "One of: Sunda Strait · Strait of Malacca and Singapore Strait", or "May also cross: Strait of Hormuz". */
export function altText(list: string[]): string {
  return `${altLabel(list)} ${altOptions(list)
    .map((o) => o.map(chokepointName).join(' and '))
    .join(' · ')}`;
}

/** The `viaAlt` lists of a pairs row, from its flat mask: each parallel group is one list, any other passage a list of its own. */
export function altLists(flat: string[]): string[][] {
  const out = PARALLEL_GROUPS.map((g) => flat.filter((id) => g.includes(id))).filter((l) => l.length);
  for (const id of flat) if (!PARALLEL_GROUPS.some((g) => g.includes(id))) out.push([id]);
  return out;
}

/** A port's source link is printed for these bases of a port (the page was read); the others read "no source page yet". */
export const SOURCED_BASES = ['page names the cargo', 'page names the cargo in the other direction', 'page names the plant, not the cargo', 'general port of the country'];

/** What a sourced port's basis adds to its source link, where it matters. */
export const BASIS_QUALIFIER: Record<string, string> = {
  'page names the cargo in the other direction': 'page names this cargo in the other direction',
  'page names the plant, not the cargo': 'page names the plant, not the cargo',
  'general port of the country': 'general port of the country',
};

/** Product names of the commodities that have two customs groups (the Route finder tells them apart). */
export const GROUP_LABEL: Record<string, string> = {
  'phosphate-rock': 'Phosphate rock',
  dap: 'DAP',
  'monoammonium-phosphate': 'MAP',
  superphosphates: 'Superphosphates',
  'phosphoric-acid': 'Phosphoric acid',
  potash: 'Potassium chloride',
  'potassium-sulphate': 'Potassium sulphate (SOP)',
  urea: 'Urea',
  ammonia: 'Ammonia',
  'ammonium-nitrate': 'Ammonium nitrate',
  'ammonium-nitrate-limestone': 'Ammonium nitrate with limestone',
  npk: 'NPK (three nutrients)',
  'npk-two-nutrient': 'Two-nutrient compounds',
  uan: 'UAN solution',
  'ammonium-sulphate': 'Ammonium sulphate',
  rapeseed: 'Rapeseed',
  'rapeseed-oil': 'Rapeseed, canola & mustard oil',
  'rapeseed-meal': 'Rapeseed meal',
  'sunflower-seed': 'Sunflower seed',
  'sunflower-oil': 'Sunflower & safflower oil',
  'sunflower-meal': 'Sunflower meal',
  coke: 'Coke and semi-coke',
  'pig-iron': 'Pig iron',
  dri: 'Direct-reduced iron & spongy iron',
  'chromium-ore': 'Chromium ore',
  'ferrous-scrap': 'Ferrous scrap',
  'ferro-chromium': 'Ferro-chromium',
  'ferro-manganese': 'Ferro-manganese',
  'silico-manganese': 'Silico-manganese',
  'ferro-silicon': 'Ferro-silicon',
  'copper-ore': 'Copper concentrate',
  'copper-refined': 'Refined copper',
  bauxite: 'Bauxite',
  alumina: 'Alumina',
  'nickel-ore': 'Nickel ore',
  'nickel-int': 'Nickel intermediates',
  'nickel-fe': 'Ferro-nickel & NPI',
  spodumene: 'Spodumene concentrate (Atlas estimate)',
  lithium: 'Lithium carbonate & hydroxide',
  'zinc-ore': 'Zinc concentrate',
  'zinc-metal': 'Unwrought zinc',
  'lead-ore': 'Lead concentrate',
  'lead-metal': 'Unwrought lead',
  'tin-metal': 'Unwrought tin',
  'tin-ore': 'Tin concentrate',
};

/** Chip labels of a lane's commodity page when the lane is one product of it (see cargoChips.ts). */
export const laneChipLabels = (l: { k: string; p?: string }) => groupChipLabels(l.k, l.p, LANE_GROUPS, GROUP_LABEL);
/** Chip labels of a route's cargo page when its corridor is one product of it. */
export const routeCargoLabels = (r: { corridor?: { k: string; g?: string }[] }) => routeChipLabels(r.corridor, LANE_GROUPS, GROUP_LABEL);

/** The Route finder offers one "Coal" for thermal and metallurgical coal: customs data do not separate them. */
export const finderCommodity = (k: string) => (k === 'thermal-coal' || k === 'met-coal' ? 'coal' : k);

// small eagerly-loaded freight catalogue used by filters and labels
export const vesselClassList = signal<VesselClass[]>([]);
export const chokepointList = signal<Chokepoint[]>([]);
export const vesselById = computed(() => Object.fromEntries(vesselClassList.value.map((v) => [v.id, v])));
export const chokepointById = computed(() => Object.fromEntries(chokepointList.value.map((c) => [c.id, c])));

export async function loadFreightCatalogue() {
  const [v, c] = await Promise.all([loadVesselClasses(), loadChokepoints()]);
  vesselClassList.value = v;
  chokepointList.value = c;
}

/**
 * A lane's share of its group's seaborne trade in the file's latest year, computed from the flow and the total as the
 * chokepoint list does: the `share` the file stores is rounded to four decimals, which a second rounding turns into a
 * different figure for the same pair.
 */
export function laneShare(l: Lane, f: LaneFile): number | null {
  if (l.mode === 'mixed') return null;
  const tot = f.seaborne[f.years.indexOf(f.y)];
  return tot > 0 && l.flow.v >= 0 ? l.flow.v / tot : l.share;
}

export function vesselName(id: string): string {
  return vesselById.value[id]?.name ?? (id === 'container' ? 'Container ship' : id);
}

export function chokepointName(id: string): string {
  return chokepointById.value[id]?.name ?? id;
}

/** Group id of a lane id "<group>:<o>-<d>". */
export function laneGroup(laneId: string): string {
  return laneId.split(':')[0];
}

/** Segment of a vessel class id (container ships are not in the class list). */
export function segmentOf(vclass: string): Segment {
  return vesselById.value[vclass]?.segment ?? (vclass === 'container' ? 'container' : 'dry');
}

// ---------------------------------------------------------------- vessel families

/** Vessel classes that trade interchangeably on a lane (Atlas grouping; tankers stay exact except Handy tanker / MR). */
const FAMILIES: string[][] = [
  ['panamax', 'kamsarmax'],
  ['capesize', 'newcastlemax', 'vloc'],
  ['supramax', 'ultramax'],
  ['handy-tanker', 'mr'],
];
const FAMILY_OF = new Map<string, string[]>();
for (const f of FAMILIES) for (const id of f) FAMILY_OF.set(id, f);

/** The class itself plus its family members. */
export function vesselFamily(id: string): string[] {
  return FAMILY_OF.get(id) ?? [id];
}

/** Family label for the classes of a multi-member family, e.g. "Panamax family"; null for single classes. */
export function familyLabel(id: string): string | null {
  const f = FAMILY_OF.get(id);
  if (!f) return null;
  const head: Record<string, string> = { panamax: 'Panamax', capesize: 'Capesize', supramax: 'Supramax', 'handy-tanker': 'Handy tanker / MR' };
  return `${head[f[0]] ?? vesselName(f[0])} family`;
}

/** Same family (including identical)? */
export function sameVesselFamily(a: string, b: string): boolean {
  return a === b || vesselFamily(a).includes(b);
}

/** Does any of the vessel classes `have` match the selected set, by family? */
/** Does the route load or discharge in this country (its drawn ends, or its trade corridor)? */
export function routeTouches(r: Route, iso3: string): boolean {
  if (r.ends?.includes(iso3)) return true;
  return r.corridor?.some((c) => c.o.includes(iso3) || c.d.includes(iso3)) ?? false;
}

/** Does the route's corridor hold this recorded pair of a customs group? (an entry without `g` or `gs` stands for the group of its commodity) */
export function corridorHas(r: Route, group: string, o: string, d: string): boolean {
  return r.corridor?.some((c) => (c.g ? c.g === group : (c.gs ?? [c.k]).includes(group)) && c.o.includes(o) && c.d.includes(d)) ?? false;
}

export function vesselMatches(have: string | string[], selected: { has(id: string): boolean; size: number }): boolean {
  if (!selected.size) return true;
  const list = Array.isArray(have) ? have : [have];
  return list.some((c) => vesselFamily(c).some((m) => selected.has(m)));
}

/** Does a route belong to the selected classes: its own class (by family), or a class page that lists it as a route it also serves? */
export function routeMatches(r: { id: string; vclass: string }, selected: ReadonlySet<string>): boolean {
  return vesselMatches(r.vclass, selected) || [...selected].some((id) => vesselById.value[id]?.routes.includes(r.id));
}

/** Chokepoints shown at world zoom on the Freight tab. */
export const MAJOR_CHOKEPOINTS = new Set([
  'hormuz', 'malacca', 'suez', 'bab-el-mandeb', 'panama', 'cape-good-hope', 'bosphorus', 'gibraltar', 'taiwan-strait', 'danish-straits',
]);

/** Lane/route status notes carried by the lane files (e.g. Red Sea diversion). */
export interface LaneStatus { text: string; event?: string }

/**
 * Open a vessel class the way the Routes by vessel class list does: Freight view, the map's routes
 * filtered to the class's family, the routes layer on and (unless `page` is false) the class page.
 */
export function openVesselClass(id: string, page = true) {
  // once the catalogue is known, an id that it lacks has no page and no routes: leave the view as it is
  if (vesselClassList.peek().length && !vesselById.peek()[id]) return;
  if (family.peek() !== 'freight') setFamily('freight');
  commodity.value = null;
  vesselClasses.value = new Set(vesselFamily(id));
  if (!layers.peek().routes) toggleLayer('routes', true);
  if (page) select({ kind: 'vessel', id });
}

/** The Freight view with every route and no page open: the way back from a route that no longer exists (what "All routes" of the Routes by vessel class list does). */
export function openFreightView() {
  setFamily('freight');
  commodity.value = null;
  vesselClasses.value = new Set();
  select(null);
}

// a link that opens a vessel class without its filter (#sel=vessel:vlcc) gets the same Freight view
{
  const s0 = selection.peek();
  if (s0?.kind === 'vessel' && !vesselClasses.peek().size) openVesselClass(s0.id, false);
}

// unknown classes in a link are dropped once the catalogue is known
vesselClassList.subscribe((list) => {
  if (!list.length) return;
  const known = new Set(list.map((v) => v.id));
  const vc = vesselClasses.peek();
  if ([...vc].some((id) => !known.has(id))) vesselClasses.value = new Set([...vc].filter((id) => known.has(id)));
  // an unknown class stays selected: its page says that it is not in the catalogue
});
