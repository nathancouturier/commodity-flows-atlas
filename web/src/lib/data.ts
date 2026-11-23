/**
 * Lazy JSON loader with an in-memory cache. All data files are fetched on demand
 * (per commodity, per layer) so the first paint only needs the catalogue.
 */
import { signal } from '@preact/signals';
import type { CommodityHistory, CommodityMeta, CountryMeta, CountryProfile, Source } from '../types';

const BASE = './data/';
const cache = new Map<string, Promise<unknown>>();

export function load<T>(path: string): Promise<T> {
  let p = cache.get(path) as Promise<T> | undefined;
  if (!p) {
    p = fetch(BASE + path, { cache: 'default' }).then((r) => {
      if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
      return r.json() as Promise<T>;
    });
    // forget failures so a later retry can succeed
    p.catch(() => cache.delete(path));
    cache.set(path, p);
  }
  return p;
}

/** Load a file, resolving to null instead of throwing (for optional layers). */
export function loadOptional<T>(path: string): Promise<T | null> {
  return load<T>(path).catch(() => null);
}

/**
 * A country's profile (data/countries/profiles/<ISO3>.json, one file per country), null when it has none. The years and
 * world totals of the series its lines point to are the same for every country: one file (countries/years.json), loaded
 * once with the first profile.
 */
export function loadProfile(iso3: string): Promise<CountryProfile | null> {
  if (!/^[A-Z0-9]{3,5}$/.test(iso3)) return Promise.resolve(null);
  return loadOptional<CountryProfile>(`countries/profiles/${iso3}.json`).then((p) =>
    p && !p.none ? loadOptional<CountryProfile['years']>('countries/years.json').then((years) => ({ ...p, years: years ?? {} })) : p,
  );
}

/** A commodity's tables by country and year (data/commodities/history), null when it has none. */
export function loadHistory(id: string): Promise<CommodityHistory | null> {
  return loadOptional<CommodityHistory>(`commodities/history/${id}.json`);
}

// ---------------------------------------------------------------- catalogue (loaded at start)

export const sources = signal<Record<string, Source>>({});
export const commodities = signal<CommodityMeta[]>([]);
export const countries = signal<Record<string, CountryMeta>>({});
/** Names of the codes that customs data use but the country index does not have (Gibraltar, "Asia, not specified"...): plain text, no page. */
export const places = signal<Record<string, string>>({});

export async function loadCatalogue() {
  const [src, com, ctry, plc] = await Promise.all([
    load<Source[]>('sources.json'),
    load<CommodityMeta[]>('commodities/index.json'),
    load<CountryMeta[]>('countries/index.json'),
    loadOptional<{ c: string; name: string }[]>('countries/places.json'),
  ]);
  sources.value = Object.fromEntries(src.map((s) => [s.id, s]));
  commodities.value = com.sort((a, b) => a.rank - b.rank);
  countries.value = Object.fromEntries([...ctry, ...regionEntries(ctry)].map((c) => [c.c, c]));
  places.value = Object.fromEntries((plc ?? []).map((p) => [p.c, p.name]));
  // a link with an unknown commodity id (e.g. "#c=coal") falls back to the overview
  const { commodity } = await import('./store');
  if (commodity.value && !com.some((c) => c.id === commodity.value)) commodity.value = null;
}

/** Aggregate rows of the tables that are neither countries nor places (USDA PSD's European Union), with their name. */
const REGION_NAME: Record<string, string> = { EU27: 'European Union (27)' };

/** The 27 member states (the same list as pipeline/commodities/build_profiles.py EU27 and map/modules/choropleth.ts EU27). */
export const EU27_MEMBERS = [
  'AUT', 'BEL', 'BGR', 'HRV', 'CYP', 'CZE', 'DNK', 'EST', 'FIN', 'FRA', 'DEU', 'GRC', 'HUN', 'IRL',
  'ITA', 'LVA', 'LTU', 'LUX', 'MLT', 'NLD', 'POL', 'PRT', 'ROU', 'SVK', 'SVN', 'ESP', 'SWE',
];

/**
 * The European Union as an entry of the country index: it has a page (its member states link to it), a name, a region and
 * a search entry, but no polygon of its own. Its box is the union of its member states' boxes.
 */
function regionEntries(ctry: CountryMeta[]): CountryMeta[] {
  const boxes = ctry.filter((c) => EU27_MEMBERS.includes(c.c) && c.bb).map((c) => c.bb!);
  if (!boxes.length) return [];
  const bb: [number, number, number, number] = [
    Math.min(...boxes.map((b) => b[0])), Math.min(...boxes.map((b) => b[1])), Math.max(...boxes.map((b) => b[2])), Math.max(...boxes.map((b) => b[3])),
  ];
  return [{ c: 'EU27', name: REGION_NAME.EU27, at: [(bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2], bb, region: 'Europe' }];
}

export function countryName(iso3: string): string {
  return countries.value[iso3]?.name ?? places.value[iso3] ?? REGION_NAME[iso3] ?? iso3;
}

/** A country of the index (it has a page and can be isolated on the map), as opposed to a place that has only a name. */
export function isCountry(code: string): boolean {
  return code in countries.value;
}

export function commodityMeta(id: string): CommodityMeta | undefined {
  return commodities.value.find((c) => c.id === id);
}

export function sourceLabel(id: string): string {
  // the atlas's own figures: the method is in the About window (the registry's name points to a file of the repository)
  if (id === 'atlas') return 'Commodity Flows Atlas estimate (derived; method in About)';
  return sources.value[id]?.name ?? id;
}
