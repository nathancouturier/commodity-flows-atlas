/**
 * Lazy JSON loader with an in-memory cache. All data files are fetched on demand
 * (per commodity, per layer) so the first paint only needs the catalogue.
 */
import { signal } from '@preact/signals';
import type { CommodityMeta, CountryMeta, Source } from '../types';

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
  countries.value = Object.fromEntries(ctry.map((c) => [c.c, c]));
  places.value = Object.fromEntries((plc ?? []).map((p) => [p.c, p.name]));
  // a link with an unknown commodity id (e.g. "#c=coal") falls back to the overview
  const { commodity } = await import('./store');
  if (commodity.value && !com.some((c) => c.id === commodity.value)) commodity.value = null;
}

export function countryName(iso3: string): string {
  return countries.value[iso3]?.name ?? places.value[iso3] ?? iso3;
}

/** A country of the index (it has a page and can be isolated on the map), as opposed to a place that has only a name. */
export function isCountry(code: string): boolean {
  return code in countries.value;
}

export function commodityMeta(id: string): CommodityMeta | undefined {
  return commodities.value.find((c) => c.id === id);
}

export function sourceLabel(id: string): string {
  return sources.value[id]?.name ?? id;
}
