/**
 * Freight data access and shared constants (vessel segments, colours, lane groups).
 * All loaders are cached by lib/data.ts.
 */
import { computed, signal } from '@preact/signals';
import type { Chokepoint, FreightEvent, LaneFile, PortwatchSeries, Route, Segment, VesselClass } from '../types';
import { load } from './data';

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
export const loadRoutes = () => load<Route[]>('freight/routes.json');
export const loadRouteGeo = () => load<GeoJSON.FeatureCollection<GeoJSON.LineString, { id: string; kind: 'route' | 'alt' }>>('freight/routes.geo.json');
export const loadChokepoints = () => load<Chokepoint[]>('freight/chokepoints.json');
export const loadVesselClasses = () => load<VesselClass[]>('freight/vessel-classes.json');
export const loadEvents = () => load<FreightEvent[]>('freight/events.json');
export const loadPortwatch = (id: string) => load<PortwatchSeries>(`freight/portwatch/${id}.json`);

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
