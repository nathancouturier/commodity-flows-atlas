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

/** Rings and badges of the assets whose status is not "operating". */
export const STATUS_COLOR: Record<Exclude<StatusClass, 'ok'>, string> = {
  damaged: '#ff4d5e',
  idle: '#ffc233',
  construction: '#e6edf5',
  planned: '#9aa7b5',
  closed: '#6f7b88',
};

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
