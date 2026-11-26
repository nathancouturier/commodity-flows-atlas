/**
 * Every colour that carries a meaning in the code, typed once. Values and nothing else: no value import (a type import at
 * most), so that a node test runs this file as it is. A package that adds a colour puts it here; scripts/palette.test.mjs
 * fails when a hue of this file is typed again in another source file, and counts the other hex literals per file.
 *
 * `styles/tokens.css` holds the same family and alert hues as custom properties (CSS cannot import TypeScript); the test
 * compares them. Its surfaces differ from `C` below on purpose: the map draws `C`, the CSS gradient behind it is hidden.
 */
import type { Family, FreightEvent, Segment } from '../types';
import type { StatusClass } from './infra';

/** The named hues of the codes. The names are conveniences; each hue says where it is used. */
export const HUES = {
  /** Energy family, Tankers, market events, price series, the estimate ribbon */
  amber: '#ffb547',
  /** Metals family, Dry bulk, weather events, price series */
  lavender: '#9db7ff',
  /** Softs family, infrastructure events, price series */
  green: '#7ee0a1',
  /** Freight family and the accent, canal events, price series, the History bar's default */
  cyan: '#3ee6ff',
  /** Container, policy events, price series */
  violet: '#c7a3ff',
  /** Chokepoint, conflict events */
  red: '#ff5c7a',
  /** Alert, accident events */
  orange: '#ff7a59',
  /** Gas carriers */
  teal: '#7ef0d8',
  /** The "Other" series of the port and passage charts */
  grey: '#7d8a99',
  /** `--positive` of tokens.css; no code of the map uses it */
  mint: '#5be3a6',
} as const;

/** Flow, chip and accent colour of each family (tokens.css: `--energy`, `--metals`, `--softs`, `--freight`). */
export const FAMILY_COLOR: Record<Family, string> = {
  energy: HUES.amber,
  metals: HUES.lavender,
  softs: HUES.green,
  freight: HUES.cyan,
};

/** Route line colours by vessel segment (freight layer). */
export const SEGMENT_COLOR: Record<Segment, string> = {
  dry: HUES.lavender,
  tanker: HUES.amber,
  gas: HUES.teal,
  container: HUES.violet,
};

/*
 * Dash patterns of the lines of the map, as MapLibre takes them: lengths in multiples of the line width, alternating
 * drawn and empty, so a rule on ratios holds at every width. A dash already means "overland, alternative or not operating"
 * (ALT_DASH, PIPELINE_DASH and the legend's overland swatch); the patterns of the vessel classes must not be read as any
 * of them, which `dashDistinct` checks and scripts/palette.test.mjs tests.
 */
/** Alternative routings of a selected route, the mixed lanes and the overland arcs. */
export const ALT_DASH: number[] = [2, 2];
/** Pipelines that are not operating. */
export const PIPELINE_DASH: number[] = [2.5, 2];

/**
 * The line of a freight route by vessel segment, which tells it from a lane of the same colour (Tankers and the Energy
 * lanes are one amber, Dry bulk and the Metals lanes one lavender). Dry bulk long dashes, Tankers dash and dot, Gas
 * carriers dots, Container short dashes far apart. An Atlas convention: a route drawn solid is a route of an unknown
 * class or the selected one. Container's is not the first thought, `[3, 2.5]`: it cannot be told from ALT_DASH.
 */
export const ROUTE_DASH: Record<Segment, number[]> = {
  dry: [6, 3],
  tanker: [6, 2, 1, 2],
  gas: [1, 2.2],
  container: [3, 6],
};

/** Every dash pattern the map draws, each with its name. A pattern typed anywhere else makes the palette test fail. */
export const DASH_VOCABULARY: { name: string; dash: number[] }[] = [
  { name: 'Alternative routing, mixed lane, overland arc', dash: ALT_DASH },
  { name: 'Pipeline not operating', dash: PIPELINE_DASH },
  { name: 'Dry bulk route', dash: ROUTE_DASH.dry },
  { name: 'Tankers route', dash: ROUTE_DASH.tanker },
  { name: 'Gas carriers route', dash: ROUTE_DASH.gas },
  { name: 'Container route', dash: ROUTE_DASH.container },
];

/** The Atlas's rule of distinct dash patterns, written once; two patterns are told apart when the counts of their elements differ, or: a difference of the dash share (drawn length over the period) of at least this. */
export const DASH_SHARE_GAP = 0.15;
/** A longer period at least this many times the shorter one. */
export const DASH_PERIOD_RATIO = 1.5;

function dashShape(a: number[]): { count: number; period: number; share: number } {
  const e = a.length % 2 ? [...a, ...a] : a; // an odd list is read twice, as the renderer does
  const period = e.reduce((x, y) => x + y, 0);
  const drawn = e.reduce((x, y, i) => (i % 2 ? x : x + y), 0);
  return { count: e.length, period, share: drawn / period };
}

/** Whether two dash patterns are told apart by the Atlas's rule (the same count of elements, then the shares, then the periods). */
export function dashDistinct(a: number[], b: number[]): boolean {
  const A = dashShape(a);
  const B = dashShape(b);
  if (A.count !== B.count) return true;
  if (Math.abs(A.share - B.share) >= DASH_SHARE_GAP - 1e-9) return true;
  return Math.max(A.period, B.period) / Math.min(A.period, B.period) >= DASH_PERIOD_RATIO - 1e-9;
}

/** Rings and badges of the assets whose status is not "operating". */
export const STATUS_COLOR: Record<Exclude<StatusClass, 'ok'>, string> = {
  damaged: '#ff4d5e',
  idle: '#ffc233',
  construction: '#e6edf5',
  planned: '#9aa7b5',
  closed: '#6f7b88',
};

/**
 * What the map draws over the base 28x28 icon of an asset whose status is not "operating": a ring, and for three of the
 * statuses a round badge at the top right ("!" damaged, two bars idle, a cross closed). Under construction is a dashed ring
 * and planned a dotted one. The strings are inserted before the closing `</svg>` of the icon; the legend draws the same
 * strings by `statusRingSvg`, so that the two cannot drift apart. The badge ink is the ocean colour: the badge sits on the map.
 */
export function statusDecoration(st: StatusClass): string {
  if (st === 'ok') return '';
  const c = STATUS_COLOR[st];
  const ink = C.ocean;
  if (st === 'planned') return `<circle cx="14" cy="14" r="12.9" fill="none" stroke="${c}" stroke-width="2.2" stroke-dasharray="0.1 3.2" stroke-linecap="round"/>`;
  if (st === 'construction') return `<circle cx="14" cy="14" r="12.9" fill="none" stroke="${c}" stroke-width="2.2" stroke-dasharray="3 2.4"/>`;
  if (st === 'closed')
    return (
      `<circle cx="14" cy="14" r="12.9" fill="none" stroke="${c}" stroke-width="1.6"/>` +
      `<circle cx="23" cy="5" r="4.6" fill="${c}" stroke="${ink}" stroke-width="1"/>` +
      `<path d="M21.2 3.2l3.6 3.6M24.8 3.2l-3.6 3.6" stroke="${ink}" stroke-width="1.4" stroke-linecap="round"/>`
    );
  const ring = `<circle cx="14" cy="14" r="12.9" fill="none" stroke="${c}" stroke-width="${st === 'damaged' ? 2.4 : 1.8}"/>`;
  const badge =
    `<circle cx="23" cy="5" r="4.6" fill="${c}" stroke="${ink}" stroke-width="1"/>` +
    (st === 'damaged'
      ? `<path d="M23 2.6v3M23 7.1v.3" stroke="${ink}" stroke-width="1.5" stroke-linecap="round"/>`
      : `<path d="M21.7 3.2v3.6M24.3 3.2v3.6" stroke="${ink}" stroke-width="1.4" stroke-linecap="round"/>`);
  return ring + badge;
}

/** The ring and badge of a status on their own, as a small standalone image (the legend's key). */
export function statusRingSvg(st: StatusClass, opts: { size: number }): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28" width="${opts.size}" height="${opts.size}" aria-hidden="true">${statusDecoration(st)}</svg>`;
}

/** Pipeline lines by what they carry. */
export const PIPELINE_COLOR = {
  crude: '#b8741a',
  products: '#ffd08a',
  gas: '#3ed8c3',
};

/** The seven kinds of freight event: ribbons, ticks and dots of the event pages, the History bar and the price drawer. */
export const EVENT_COLOR: Record<FreightEvent['kind'], string> = {
  conflict: HUES.red,
  canal: HUES.cyan,
  weather: HUES.lavender,
  policy: HUES.violet,
  accident: HUES.orange,
  market: HUES.amber,
  infrastructure: HUES.green,
};

/** Ship-type series of the port and passage charts. */
export const PW_COLORS: Record<'tanker' | 'dry' | 'container' | 'other', string> = { tanker: HUES.amber, dry: HUES.lavender, container: HUES.violet, other: HUES.grey };

/**
 * The stroke pattern, in px, of the one ship-type series that is dashed: Container, whose violet and the lavender of
 * Dry bulk are one colour to a deuteranope. The other three series are solid.
 */
export const PW_DASH: { container: number[] } = { container: [6, 4] };

/** Colours the price drawer gives its series, in the order it takes them (at most three at a time). */
export const PRICE_PALETTE: string[] = [HUES.cyan, HUES.amber, HUES.violet, HUES.green, HUES.lavender];

/** The line of a flow with no family (lanes, overland arcs) and the ribbon of a flagged year that is not an estimate. */
export const NEUTRAL_LINE = '#8aa0b8';

/** The surfaces of the drawn map. */
export const C = {
  ocean: '#05090f',
  land: '#111821',
  landHover: '#1b2734',
  landSelected: '#233a52',
  border: '#24313f',
  coast: '#2d3e53',
  graticule: 'rgba(120, 150, 190, 0.07)',
};
