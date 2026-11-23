/**
 * Reads the figures of an infrastructure asset so that a list ranks assets among comparable figures only.
 *
 * `capacity` and `output` carry a unit of the vocabulary (pipeline/infrastructure/README.md), a year of their own
 * and, in `n`, what they count. Two figures are comparable when they have the same kind (capacity with capacity,
 * production with production), the same unit, the same commodity and the same form.
 *
 * Nothing here changes a published figure: a row prints the source's own number and unit.
 */
import type { InfraProps } from '../types';
import { figureOf, type Figure, type FigureKind } from './infra';

/** A figure that counts "cereals" or "grain" belongs to every grain the asset handles. */
const CEREAL_TEXT = /cereal|\bgrains?\b/i;

const COAL = ['thermal-coal', 'met-coal', 'coal'];
const CEREAL = ['wheat', 'corn', 'rice'];
/** Commodities a figure in barrels per day, or in a gas volume, can describe. */
const LIQUIDS = ['crude-oil', 'refined-products', 'lpg'];
const GASES = ['natural-gas', 'lng'];

/** Total port traffic: says how busy the port is, not how much of one commodity it handles. */
const ALL_CARGO = /\bcargo\b|\bthroughput\b|\btonnage\b|^total\b/i;
/** Wording that always means all traffic, whatever commodities the port is tagged with ("throughput" may be one commodity's). */
const TOTAL_TRAFFIC = /^total\b|\btonnage\b/i;

export type Form = 'product' | 'concentrate' | 'ore' | 'feed';

export interface CapacityRead {
  /**
   * own: a figure for the page's commodity (or, with no page commodity, for the asset's own);
   * cargo: all cargo of a port that handles several commodities;
   * other: a figure for another commodity, not to be printed on this page; none: no figure.
   */
  kind: 'own' | 'cargo' | 'other' | 'none';
  /** figures with the same key are comparable: same dimension, same subject, same form */
  key: string;
  /** value in the unit of the key, for the order inside one key */
  rank: number;
  /** commodity the figure counts ('coal' and 'cereal' are group names) */
  subject?: string;
  form: Form;
  /**
   * planned: a figure of an asset that is planned or under construction, closed: an asset that no longer runs.
   * Both are kept apart from operating figures.
   */
  basis: 'operating' | 'planned' | 'closed';
  /** the figure the asset is ranked and printed by: its capacity, else its output */
  fig: Figure | null;
}

const NONE: CapacityRead = { kind: 'none', key: 'none', rank: 0, form: 'product', basis: 'operating', fig: null };

function concerns(subject: string, id: string): boolean {
  if (subject === 'coal') return COAL.includes(id);
  if (subject === 'cereal') return CEREAL.includes(id);
  return subject === id;
}

function formOf(rest: string): Form {
  // "in concentrate" is metal content; a source that does not say what its figure counts is not reclassified
  if (/\bin concentrate\b|does not say/i.test(rest)) return 'product';
  if (/concentrate feed|feed capacity/i.test(rest)) return 'feed';
  if (/concentrate/i.test(rest)) return 'concentrate';
  if (/ore processing|processing capacity/i.test(rest)) return 'ore';
  return 'product';
}

/** The figures of an asset: its capacity and its output, each with its own year. */
export function figuresOf(p: InfraProps): { capacity?: Figure; output?: Figure } {
  const out: { capacity?: Figure; output?: Figure } = {};
  if (p.capacity && Number.isFinite(p.capacity.v)) out.capacity = figureOf('capacity', p.capacity);
  if (p.output && Number.isFinite(p.output.v)) out.output = figureOf(p.output.what as FigureKind, p.output);
  return out;
}

/** The figure a row prints and ranks by: the capacity when there is one, else the output. */
export function mainFigure(p: InfraProps): Figure | null {
  const f = figuresOf(p);
  return f.capacity ?? f.output ?? null;
}

/**
 * Figure of an asset as seen from a commodity page (`id`), or from the asset itself when `id` is
 * omitted (country pages, where each figure is kept under the commodity it counts).
 */
export function readCapacity(p: InfraProps, id?: string): CapacityRead {
  const fig = mainFigure(p);
  if (!fig) return NONE;
  // figures are comparable in the same unit of the vocabulary
  const dim = fig.u;
  const rank = fig.v;
  const rest = fig.n ?? '';
  const form = formOf(rest);
  const basis: CapacityRead['basis'] = p.status === 'planned' || p.status === 'construction' ? 'planned' : p.status === 'closed' ? 'closed' : 'operating';
  const sfx = basis === 'operating' ? '' : `|${basis}`;
  // capacity, production, exports and throughput are never ranked against each other
  const what = `${fig.kind}|`;
  const main = p.k[0];
  const base = { form, basis, fig, rank };
  // a figure counted as port traffic says how busy the port is when the text names no commodity
  const text = fig.kind === 'throughput' ? `${rest} throughput` : rest;

  let subject = CEREAL_TEXT.test(rest) ? 'cereal' : undefined;
  if (!subject) {
    if (p.type === 'port' && (TOTAL_TRAFFIC.test(text) || (ALL_CARGO.test(text) && p.k.length !== 1))) {
      return { kind: 'cargo', key: `cargo|${what}${dim}${sfx}`, ...base };
    }
    const lng = p.type === 'lng-export' || p.type === 'lng-import';
    const family = dim === 'kb/d' ? LIQUIDS : dim === 'bcm/y' || lng ? GASES : null;
    if (family) {
      if (id && !family.includes(id)) return { ...NONE, kind: 'other' };
      subject = id ?? p.k.find((k) => family.includes(k)) ?? family[0];
    } else {
      // the text names no commodity: the figure is read as the asset's main commodity
      subject = COAL.includes(main) ? 'coal' : main;
    }
  }
  if (!subject) return NONE;
  if (id && !concerns(subject, id)) return { ...NONE, kind: 'other' };
  return { kind: 'own', key: `${what}${dim}|${subject}|${form}${sfx}`, subject, ...base };
}
