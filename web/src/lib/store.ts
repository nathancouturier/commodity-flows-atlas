/**
 * Global UI state, as Preact signals. Components read `.value` and re-render
 * automatically; the map subscribes with `effect()`.
 *
 * Progressive disclosure: only the `flows` layer is on at start.
 */
import { signal, computed } from '@preact/signals';
import type { Family, InfraType } from '../types';

export type FamilyFilter = Family | 'all';

/** Layers that can be toggled. Choropleth metrics are mutually exclusive. */
export type LayerId = 'flows' | 'routes' | 'chokepoints' | 'infrastructure';
export type Metric = 'none' | 'production' | 'reserves' | 'consumption' | 'exports' | 'imports';

export type Selection =
  | { kind: 'country'; id: string }
  | { kind: 'commodity'; id: string }
  | { kind: 'route'; id: string }
  | { kind: 'lane'; id: string }
  | { kind: 'chokepoint'; id: string }
  | { kind: 'infra'; id: string; layer: InfraType }
  | { kind: 'vessel'; id: string }
  | { kind: 'event'; id: string };

export const family = signal<FamilyFilter>('all');
export const commodity = signal<string | null>(null);
export const layers = signal<Record<LayerId, boolean>>({
  flows: true,
  routes: false,
  chokepoints: false,
  infrastructure: false,
});
export const metric = signal<Metric>('none');
export const infraTypes = signal<Set<InfraType>>(new Set());
export const vesselClasses = signal<Set<string>>(new Set());
export const companyFilter = signal<string | null>(null);
export const countryFilter = signal<string | null>(null);
export const year = signal<number | null>(null);
export const selection = signal<Selection | null>(null);
export const hovered = signal<{ x: number; y: number; html: string } | null>(null);
export const panelCollapsed = signal(false);

export const detailOpen = computed(() => selection.value !== null);

export function toggleLayer(id: LayerId, on?: boolean) {
  const next = { ...layers.value };
  next[id] = on ?? !next[id];
  layers.value = next;
}

export function toggleInSet<T>(sig: { value: Set<T> }, item: T) {
  const next = new Set(sig.value);
  if (next.has(item)) next.delete(item);
  else next.add(item);
  sig.value = next;
}

export function select(s: Selection | null) {
  selection.value = s;
}

// ---------------------------------------------------------------- URL hash sync
// The hash keeps the view shareable: #c=crude-oil&sel=country:SAU&m=production

function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  const f = p.get('f');
  if (f === 'energy' || f === 'metals' || f === 'softs' || f === 'freight') family.value = f;
  if (p.get('c')) commodity.value = p.get('c');
  const m = p.get('m') as Metric | null;
  if (m) metric.value = m;
  const y = p.get('y');
  if (y && /^\d{4}$/.test(y)) year.value = Number(y);
  const sel = p.get('sel');
  if (sel) {
    // ids may contain ':' (lane ids are "<group>:<o>-<d>"); only infra selections carry a trailing layer
    const i = sel.indexOf(':');
    const kind = sel.slice(0, i);
    let id = sel.slice(i + 1);
    let layer: string | undefined;
    if (kind === 'infra') {
      const j = id.lastIndexOf(':');
      layer = id.slice(j + 1);
      id = id.slice(0, j);
    }
    if (i > 0 && id) selection.value = { kind, id, layer } as Selection;
  }
}

export function writeHash() {
  const p = new URLSearchParams();
  if (family.value !== 'all') p.set('f', family.value);
  if (commodity.value) p.set('c', commodity.value);
  if (metric.value !== 'none') p.set('m', metric.value);
  if (year.value) p.set('y', String(year.value));
  const s = selection.value;
  if (s) p.set('sel', s.kind === 'infra' ? `${s.kind}:${s.id}:${s.layer}` : `${s.kind}:${s.id}`);
  const h = p.toString();
  history.replaceState(null, '', h ? `#${h}` : location.pathname + location.search);
}

readHash();
// a shared Freight-tab link opens with its routes and chokepoints visible
if (family.value === 'freight') layers.value = { ...layers.value, routes: true, chokepoints: true };

// ---------------------------------------------------------------- route finder (side panel)
// Kept in the store so the choice survives switching tabs.
export const routeFinderOpen = signal(false);
export const rfCommodity = signal<string>('thermal-coal');
export const rfOrigin = signal<string | null>(null);
export const rfDest = signal<string | null>(null);
