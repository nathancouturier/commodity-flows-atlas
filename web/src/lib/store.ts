/**
 * Global UI state, as Preact signals. Components read `.value` and re-render
 * automatically; the map subscribes with `effect()`.
 *
 * Progressive disclosure: only the `flows` layer is on at start.
 */
import { signal, computed, batch, effect } from '@preact/signals';
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
  | { kind: 'event'; id: string }
  /** a page that lists things and has no id of its own: `board:chokepoints` */
  | { kind: 'board'; id: string };

export const family = signal<FamilyFilter>('all');
export const commodity = signal<string | null>(null);
// all layers visible by default (owner's choice); each one is a toggle in the legend
export const layers = signal<Record<LayerId, boolean>>({
  flows: true,
  routes: true,
  chokepoints: true,
  infrastructure: true,
});
export const metric = signal<Metric>('none');
/** Infrastructure types the user switched off (empty = every type shown, the default). */
export const infraHidden = signal<Set<InfraType>>(new Set());
/** Infrastructure types that exist for the current tab / commodity (set by the infrastructure layer). */
export const infraAvailable = signal<Set<InfraType> | null>(null);
export const vesselClasses = signal<Set<string>>(new Set());
export const companyFilter = signal<string | null>(null);
export const countryFilter = signal<string | null>(null);
export const year = signal<number | null>(null);
export const selection = signal<Selection | null>(null);
export const hovered = signal<{ x: number; y: number; html: string } | null>(null);
/** Side panel folded into its Controls button (desktop). Open on every load. */
export const panelCollapsed = signal(false);

export const detailOpen = computed(() => selection.value !== null);

/** Bottom-sheet snap heights of the side panel (tablet / phone layout). */
export type SheetSnap = 'peek' | 'half' | 'full';
export const sheetSnap = signal<SheetSnap>('half');

/** Chokepoints crossed by the lanes / routes kept on the map for a selected country (null = no country). */
export const laneVia = signal<Set<string> | null>(null);
export const routeVia = signal<Set<string> | null>(null);

/** Number of overland / pipeline flow arcs currently drawn (drives the legend). */
export const landFlowsShown = signal(0);
/** Small empty-state notice on the map (e.g. commodity without any mapped flows). */
export const mapNotice = signal<string | null>(null);
/** The map could not start (WebGL switched off or missing): the panels work without it. */
export const mapFailed = signal(false);

/** Active country colouring, for the colour-ramp legend. Shares are 0..1 of the world total. */
export interface ChoroInfo {
  metric: string;
  unit: string;
  year: number | string;
  source: string;
  color: string;
  min: number;
  max: number;
  commodity: string;
}
export const choroInfo = signal<ChoroInfo | null>(null);

/** Physical-flows state to restore when leaving the Freight tab. */
let layersBeforeFreight: Record<LayerId, boolean> | null = null;

/**
 * Switch the family tab. The Freight tab brings routes and chokepoints in and turns Physical flows
 * off (the lanes would bury the routes); leaving it restores the previous state.
 */
export function setFamily(next: FamilyFilter) {
  const was = family.value === 'freight';
  const to = next === 'freight';
  if (to && !was) {
    // the Freight tab is about routes: show them and the chokepoints, hide the flows; remember the rest
    layersBeforeFreight = { ...layers.value };
    layers.value = { ...layers.value, routes: true, chokepoints: true, flows: false };
  } else if (was && !to && layersBeforeFreight) {
    layers.value = layersBeforeFreight;
    layersBeforeFreight = null;
  }
  family.value = next;
}

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

const HASH_FAMILIES: readonly string[] = ['energy', 'metals', 'softs', 'freight'];
const HASH_METRICS: readonly string[] = ['production', 'reserves', 'consumption', 'exports', 'imports'];
const HASH_KINDS: readonly string[] = ['country', 'commodity', 'route', 'lane', 'chokepoint', 'infra', 'vessel', 'event', 'board'];

/** Route finder state of a link: `rf=<commodity>:<o|d>:<origin>-<destination>[:<group>]`. */
interface FinderState {
  commodity: string;
  from: 'o' | 'd';
  origin: string | null;
  dest: string | null;
  /** customs group, only for a commodity that has two (phosphate: rock or DAP) */
  group: string | null;
}

/** The part of the view a link carries. */
interface HashState {
  family: FamilyFilter;
  commodity: string | null;
  metric: Metric;
  vessels: string[];
  year: number | null;
  selection: Selection | null;
  finder: FinderState | null;
  /** the price explorer, open as the link describes it; null = closed */
  prices: PriceDrawerState | null;
}

/** Route finder part of a link, null when it is absent or unreadable (ids are checked later, against the data). */
function parseFinder(raw: string | null): FinderState | null {
  const m = raw?.match(/^([a-z0-9-]+):([od]):([A-Z]{3})?-([A-Z]{3})?(?::([a-z0-9-]+))?$/);
  if (!m || (!m[3] && !m[4])) return null;
  return { commodity: m[1], from: m[2] as 'o' | 'd', origin: m[3] ?? null, dest: m[4] ?? null, group: m[5] ?? null };
}

const SERIES_ID = /^[a-z0-9][a-z0-9:_-]*$/i;
const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
const toSec = (d: string): number => {
  const m = ISO_DAY.exec(d);
  return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) / 1000 : NaN;
};
const isoDay = (t: number): string => new Date(t * 1000).toISOString().slice(0, 10);

/**
 * Price explorer part of a link: `p=<series>[,<series>...]` (empty = the commodity's own series) opens it, with `pr=<from>_<to>`
 * (the period shown, two dates), `pd=<date>` (the date looked up: 2008, 2008-Q3, 2008-03, 2008-03-14) and `pf=` (`i` index to 100,
 * `r` real prices). Null when the link has no `p`. Series ids are checked against the price index by the drawer.
 */
function parsePrices(p: URLSearchParams): PriceDrawerState | null {
  const raw = p.get('p');
  if (raw === null) return null;
  const series = raw.split(',').filter((id) => SERIES_ID.test(id)).slice(0, 3);
  const r = /^(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})$/.exec(p.get('pr') ?? '');
  const range: [number, number] | undefined = r && toSec(r[1]) < toSec(r[2]) ? [toSec(r[1]), toSec(r[2])] : undefined;
  const date = p.get('pd');
  const flags = p.get('pf') ?? '';
  return {
    series: series.length ? series : undefined,
    date: date && /^\d{4}(-(Q[1-4]|\d{2}(-\d{2})?))?$/.test(date) ? date : undefined,
    range,
    index: flags.includes('i'),
    real: flags.includes('r'),
  };
}

function finderHash(): string | null {
  const o = rfOrigin.value;
  const d = rfDest.value;
  if (!o && !d) return null;
  return `${rfCommodity.value}:${rfFrom.value}:${o ?? ''}-${d ?? ''}${rfGroup.value ? ':' + rfGroup.value : ''}`;
}

/**
 * The view a hash describes. A key the hash does not carry is at its default, and so is a key whose value
 * the atlas cannot read (an unknown tab, colouring or kind of page). Ids are checked later, against the
 * catalogues, by the code that owns them.
 */
function parseHash(hash: string): HashState {
  const p = new URLSearchParams(hash.replace(/^#/, ''));
  const f = p.get('f');
  const m = p.get('m');
  const y = p.get('y');
  let sel: Selection | null = null;
  const raw = p.get('sel');
  if (raw) {
    // ids may contain ':' (lane ids are "<group>:<o>-<d>"); only infra selections carry a trailing layer
    const i = raw.indexOf(':');
    const kind = raw.slice(0, i);
    let id = raw.slice(i + 1);
    let layer: string | undefined;
    if (kind === 'infra') {
      const j = id.lastIndexOf(':');
      layer = j > 0 ? id.slice(j + 1) : '';
      id = j > 0 ? id.slice(0, j) : '';
    }
    if (i > 0 && id && HASH_KINDS.includes(kind) && layer !== '') sel = { kind, id, layer } as Selection;
  }
  return {
    family: f && HASH_FAMILIES.includes(f) ? (f as FamilyFilter) : 'all',
    commodity: p.get('c') || null,
    metric: m && HASH_METRICS.includes(m) ? (m as Metric) : 'none',
    vessels: (p.get('v') ?? '').split(',').filter(Boolean),
    year: y && /^\d{4}$/.test(y) ? Number(y) : null,
    selection: sel,
    finder: parseFinder(p.get('rf')),
    prices: parsePrices(p),
  };
}

const selKey = (s: Selection | null) => (s ? (s.kind === 'infra' ? `${s.kind}:${s.id}:${s.layer}` : `${s.kind}:${s.id}`) : '');

/**
 * Set each time an address is applied to the open atlas. `own` is true for Back or Forward to a view the
 * atlas wrote itself (restored as it was), false for a link that came from outside (pasted or edited
 * address, bookmark), which is treated like a fresh load of that link.
 */
export const linkApplied = signal<{ own: boolean } | null>(null);

/** Put the whole view in the state a link describes, in one go (nothing is written to the address meanwhile). */
function applyHash(st: HashState) {
  batch(() => {
    // a shared Freight-tab link opens with its routes and chokepoints visible; leaving the tab restores the layers
    setFamily(st.family);
    commodity.value = st.commodity;
    metric.value = st.metric;
    const vc = vesselClasses.peek();
    if (vc.size !== st.vessels.length || st.vessels.some((v) => !vc.has(v))) vesselClasses.value = new Set(st.vessels);
    year.value = st.year;
    // the timeline is what sets a year: a link with #y=2016 opens it, a link without closes it
    historyOpen.value = st.year != null;
    if (selKey(st.selection) !== selKey(selection.peek())) selection.value = st.selection;
    // a link without a finder question leaves the finder's commodity alone (it follows the panel's) and empties the question
    if (st.finder) {
      rfCommodity.value = st.finder.commodity;
      // a link that brings a question shows it, even when it is pasted into the open atlas
      routeFinderOpen.value = true;
    }
    rfFrom.value = st.finder?.from ?? 'o';
    rfOrigin.value = st.finder?.origin ?? null;
    rfDest.value = st.finder?.dest ?? null;
    rfGroup.value = st.finder?.group ?? null;
    // the price explorer: a link with `p` opens it as described, one without closes it (as for the timeline)
    if (st.prices) priceDrawer.value = { ...st.prices, nonce: --linkNonce };
    else if (priceDrawer.peek()) priceDrawer.value = null;
  });
}
/** Nonces of the requests that come from an address count down, those of openPrices() count up: they never collide. */
let linkNonce = 0;

function currentHash(): string {
  const p = new URLSearchParams();
  if (family.value !== 'all') p.set('f', family.value);
  if (commodity.value) p.set('c', commodity.value);
  if (metric.value !== 'none') p.set('m', metric.value);
  if (vesselClasses.value.size) p.set('v', [...vesselClasses.value].join(','));
  if (year.value) p.set('y', String(year.value));
  const s = selection.value;
  if (s) p.set('sel', selKey(s));
  const rf = finderHash();
  if (rf) p.set('rf', rf);
  if (priceDrawer.value) {
    p.set('p', priceSeries.value.join(','));
    const v = priceView.value;
    if (v?.range) p.set('pr', `${isoDay(v.range[0])}_${isoDay(v.range[1])}`);
    if (v?.date) p.set('pd', v.date);
    const flags = (v?.index ? 'i' : '') + (v?.real ? 'r' : '');
    if (flags) p.set('pf', flags);
  }
  // the question reads as written (`rf=coal:o:AUS-CHN`): its ids hold only letters, digits and hyphens; so do the series of `p`,
  // apart from the colon of a spread (`spread:brent-wti-d`)
  const h = p.toString().replace(/(^|&)(rf|p)=[^&]*/g, (m) => m.replace(/%3A/gi, ':').replace(/%2C/gi, ','));
  return h ? `#${h}` : '';
}

/** Page (selection) shown by the history entry the address is on. */
let entrySel = '';
/** State of the history entries the atlas writes, to tell them from the addresses that come from outside. */
const OWN_ENTRY = { atlas: true };
let writePending = false;

/**
 * Mirror the view in the address. Opening or closing a page adds a history entry, so Back returns to the
 * page before; everything else (tab, commodity, colouring, year) updates the current entry. The write
 * waits for the end of the current task, so one action that changes several signals makes one entry.
 */
export function writeHash() {
  if (writePending) return;
  writePending = true;
  queueMicrotask(() => {
    writePending = false;
    const h = currentHash();
    const sel = selKey(selection.peek());
    if (h !== location.hash) {
      const url = h || location.pathname + location.search;
      if (sel !== entrySel) history.pushState(OWN_ENTRY, '', url);
      else history.replaceState(OWN_ENTRY, '', url);
    }
    entrySel = sel;
  });
}

/**
 * A link pasted into the address bar, an edited hash, Back or Forward: show exactly the view the address
 * describes. pushState and replaceState fire neither event, so the atlas's own writes do not come back here.
 */
function onNavigate() {
  if (location.hash === currentHash()) return;
  const st = parseHash(location.hash);
  entrySel = selKey(st.selection);
  applyHash(st);
  linkApplied.value = { own: history.state?.atlas === true };
}

// ---------------------------------------------------------------- route finder (side panel)
// Kept in the store so the choice survives switching tabs.
export const routeFinderOpen = signal(false);
export const rfCommodity = signal<string>('coal');
export const rfOrigin = signal<string | null>(null);
export const rfDest = signal<string | null>(null);
/** Which end the finder starts from: the origin (default) or the destination. */
export const rfFrom = signal<'o' | 'd'>('o');
/** Customs group of the question, for a commodity with two (null = the larger one). In the address (`rf=`) only. */
export const rfGroup = signal<string | null>(null);

// ---------------------------------------------------------------- price explorer & history timeline
/**
 * Price drawer. `null` = closed. Set it (or call openPrices() from lib/prices.ts) to open the drawer:
 * `{ commodity: 'copper' }` loads that commodity's price series, `{ series: ['brent-d'] }` an explicit list,
 * `date` ("1986", "2008-03", "2008-03-14") also zooms to and reads out that date.
 */
export interface PriceDrawerState {
  commodity?: string | null;
  series?: string[];
  date?: string;
  /** the period to show, seconds [from, to] (an address carries it) */
  range?: [number, number];
  /** index to 100 / real prices on or off (an address carries them; an open request that leaves them out keeps the drawer's own) */
  index?: boolean;
  real?: boolean;
  /** changes on every open request so the drawer re-applies identical requests */
  nonce?: number;
}
export const priceDrawer = signal<PriceDrawerState | null>(null);
/** What the open drawer shows beyond its series (the drawer writes it, the address carries it): period, date looked up, flags. */
export const priceView = signal<{ range: [number, number] | null; date: string | null; index: boolean; real: boolean } | null>(null);
/** Selected price series ids (max 3), in display order. */
export const priceSeries = signal<string[]>([]);
/** History timeline open (drives `year` while open). */
export const historyOpen = signal(false);

// ---------------------------------------------------------------- start
// Last, because the view a link describes touches signals declared all over this file.
{
  const st = parseHash(location.hash);
  entrySel = selKey(st.selection);
  applyHash(st);
  window.addEventListener('popstate', onNavigate);
  window.addEventListener('hashchange', onNavigate);
  // the finder's question is part of the address; the first run (the link just applied) writes nothing
  let first = true;
  effect(() => {
    void [rfCommodity.value, rfFrom.value, rfOrigin.value, rfDest.value, rfGroup.value];
    if (first) first = false;
    else writeHash();
  });
  // the price explorer is part of the address too: open or closed, its series, period, date and flags
  let firstPrices = true;
  effect(() => {
    void [priceDrawer.value !== null, priceSeries.value, priceView.value];
    if (firstPrices) firstPrices = false;
    else writeHash();
  });
}
