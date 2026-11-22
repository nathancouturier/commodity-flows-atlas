/**
 * Freight data access and shared constants (vessel segments, colours, lane groups).
 * All loaders are cached by lib/data.ts.
 */
import { computed, signal } from '@preact/signals';
import type { CaveatEntry, CaveatsFile, Chokepoint, FreightEvent, LaneFile, PairsFile, PortwatchSeries, Route, Segment, VesselClass } from '../types';
import { load } from './data';
import { commodity, family, layers, select, selection, setFamily, toggleLayer, vesselClasses } from './store';

/** Customs product groups with lanes, per atlas commodity id. */
export const LANE_GROUPS: Record<string, string[]> = {
  'crude-oil': ['crude-oil'],
  'refined-products': ['refined-products'],
  lng: ['lng'],
  lpg: ['lpg'],
  'thermal-coal': ['coal'],
  'met-coal': ['coal'],
  'iron-ore': ['iron-ore'],
  steel: ['steel'],
  copper: ['copper-ore', 'copper-refined'],
  aluminium: ['aluminium'],
  bauxite: ['bauxite', 'alumina'],
  nickel: ['nickel-ore', 'nickel-int'],
  zinc: ['zinc-ore'],
  manganese: ['manganese'],
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
  rapeseed: ['rapeseed'],
  potash: ['potash'],
  phosphate: ['phosphate-rock', 'dap'],
  urea: ['urea'],
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
  zone: string;
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
export function maskGates(mask: number, gates: string[]): string[] {
  const out: string[] = [];
  for (let i = 0; i < gates.length && i < 31; i++) if ((mask >>> i) & 1) out.push(gates[i]);
  return out;
}

/** Decode the rows of a pairs file (columns are found by name, so their order may change). */
export function decodePairs(file: PairsFile): Pair[] {
  const ix = Object.fromEntries(file.cols.map((c, i) => [c, i]));
  const port = (i: number): PairPort | null => {
    const p = i >= 0 ? file.ports[i] : undefined;
    return p ? { id: p[0], name: p[1], c: p[2], zone: p[3] } : null;
  };
  return file.rows.map((r) => {
    const f = Number(r[ix.f] ?? 0);
    const cls = Number(r[ix.cls]);
    return {
      group: file.group,
      o: String(r[ix.o]),
      d: String(r[ix.d]),
      kt: Number(r[ix.kt]),
      kind: PAIR_KINDS[Number(r[ix.m])] ?? 'land',
      load: port(Number(r[ix.load])),
      dis: port(Number(r[ix.dis])),
      nm: Number(r[ix.nm]) || 0,
      cls: cls >= 0 ? (file.classes[cls] ?? null) : null,
      via: maskGates(Number(r[ix.via]) || 0, file.gates),
      viaAlt: maskGates(Number(r[ix.alt]) || 0, file.gates),
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

/** Product names of the commodities that have two customs groups (the Route finder tells them apart). */
export const GROUP_LABEL: Record<string, string> = {
  'phosphate-rock': 'Phosphate rock',
  dap: 'DAP',
  'copper-ore': 'Copper concentrate',
  'copper-refined': 'Refined copper',
  bauxite: 'Bauxite',
  alumina: 'Alumina',
  'nickel-ore': 'Nickel ore',
  'nickel-int': 'Nickel intermediates',
};

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

export function vesselMatches(have: string | string[], selected: { has(id: string): boolean; size: number }): boolean {
  if (!selected.size) return true;
  const list = Array.isArray(have) ? have : [have];
  return list.some((c) => vesselFamily(c).some((m) => selected.has(m)));
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
  if (family.peek() !== 'freight') setFamily('freight');
  commodity.value = null;
  vesselClasses.value = new Set(vesselFamily(id));
  if (!layers.peek().routes) toggleLayer('routes', true);
  if (page) select({ kind: 'vessel', id });
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
