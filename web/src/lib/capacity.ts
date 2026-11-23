/**
 * Reads the figures of an infrastructure asset so that a list ranks assets among comparable figures only.
 *
 * Migrated files (pipeline/infrastructure/README.md): `capacity` and `output` carry a unit of the vocabulary,
 * a year of their own and, in `n`, what they count. Two figures are comparable when they have the same kind
 * (capacity with capacity, production with production), the same unit, the same commodity and the same form.
 *
 * LEGACY: the files not yet migrated have a feature-level `y` and a free-text unit ("1.28 Mt Cu (2024)",
 * "745 koz Au (2023)"). `legacyFigures`, `splitUnit`, `UNITS`, `SUBJECTS`, `PLANNED` and the unit conversion of
 * `readCapacity` exist only for them and can be deleted once data/infrastructure has no feature with a `y`
 * (validate-infra.mjs with STRICT_INFRA=1 says so).
 *
 * Nothing here changes a published figure: a row prints the source's own number and unit. The factors below
 * are unit definitions (pound, troy ounce, short ton, cubic foot) and serve the order of the legacy rows alone.
 */
import type { InfraProps } from '../types';
import { figureOf, isLegacy, type Figure, type FigureKind } from './infra';

type Dim = 'mass' | 'liquid' | 'gas';

/** Unit at the start of capacity.u -> dimension and factor to that dimension's base (t, kb/d, bcm/y). */
const UNITS: [string, Dim, number][] = [
  ['million short tons', 'mass', 907184.74],
  ['billion lb', 'mass', 453592.37],
  ['Mlb', 'mass', 453.59237],
  ['koz', 'mass', 0.0311034768],
  ['Mtpa', 'mass', 1e6],
  ['Mt', 'mass', 1e6],
  ['kt', 'mass', 1e3],
  ['tU', 'mass', 1],
  ['t', 'mass', 1],
  ['mb/d', 'liquid', 1e3],
  ['kb/d', 'liquid', 1],
  ['bcm/y', 'gas', 1],
  ['Bcf/d', 'gas', 0.028316846592 * 365],
  ['MMcf/d', 'gas', 0.000028316846592 * 365],
];

const unitOf = (u: string) => UNITS.find(([name]) => u === name || u.startsWith(name + ' ') || u.startsWith(name + '/y'));

/**
 * "billion lb Cu/y capacity" -> ["billion lb", "Cu/y capacity"]: the unit proper, then what it counts.
 * An unknown unit splits at its first space.
 */
export function splitUnit(u: string): [string, string] {
  const unit = unitOf(u);
  const head = unit ? (u.startsWith(unit[0] + '/y') ? unit[0] + '/y' : unit[0]) : u.split(' ')[0];
  return [head, u.slice(head.length).trim()];
}

/** What the unit text says the figure counts. 'coal' covers both coal commodities, 'cereal' the grains. */
const SUBJECTS: [RegExp, string][] = [
  [/\bU3O8\b|uranium/i, 'uranium'],
  [/\bCu\b|copper/i, 'copper'],
  [/\bAu\b|\bgold\b/, 'gold'],
  [/\bCo\b|cobalt/, 'cobalt'],
  [/iron ore|magnetite/i, 'iron-ore'],
  [/\bcoal\b/i, 'coal'],
  [/\bAl\b|alumini?um/, 'aluminium'],
  [/bauxite/i, 'bauxite'],
  [/\bKCl\b|potash/i, 'potash'],
  [/\bMn\b|manganese/, 'manganese'],
  [/\bREO\b|rare earth/i, 'rare-earths'],
  [/\bZn\b|\bzinc\b/, 'zinc'],
  [/spodumene|lithium|\bLCE\b/i, 'lithium'],
  [/\bNi\b|\bnickel\b/, 'nickel'],
  [/cereal|\bgrain/i, 'cereal'],
];

const COAL = ['thermal-coal', 'met-coal', 'coal'];
const CEREAL = ['wheat', 'corn', 'rice'];
/** Commodities a figure in barrels per day, or in a gas volume, can describe. */
const LIQUIDS = ['crude-oil', 'refined-products', 'lpg'];
const GASES = ['natural-gas', 'lng'];

/** Total port traffic: says how busy the port is, not how much of one commodity it handles. */
const ALL_CARGO = /\bcargo\b|\bthroughput\b|\btonnage\b|^total\b/i;
/** Wording that always means all traffic, whatever commodities the port is tagged with ("throughput" may be one commodity's). */
const TOTAL_TRAFFIC = /^total\b|\btonnage\b/i;

/** A figure that is not today's output or rated capacity: planned, expected, potential, a target or a licence limit. */
const PLANNED = /\bplanned\b|\bexpected\b|\bpotential\b|ramp-up|\btarget\b|\bregulated\b|\blimit\b|\blicen[cs]ed\b/i;

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
  /** value in the base unit of its dimension, for the order inside one key */
  rank: number;
  /** commodity the figure counts ('coal' and 'cereal' are group names), when known */
  subject?: string;
  form: Form;
  /**
   * planned: a figure of an asset that is planned or under construction (legacy files: a figure worded planned /
   * expected / potential / licensed), closed: an asset that no longer runs. Both are kept apart from operating figures.
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

/** LEGACY: the capacity of an old-shape feature, its free-text unit split into the unit and what it counts. */
function legacyFigures(p: InfraProps): { capacity?: Figure } {
  const c = p.capacity;
  if (!c || !Number.isFinite(c.v)) return {};
  const [u, n] = splitUnit(c.u ?? '');
  // a feature-level year that is not a number ("undated") is no year
  return { capacity: figureOf('capacity', { v: c.v, u, n: n || undefined, y: typeof p.y === 'number' ? p.y : undefined }) };
}

/** The figures of an asset: its capacity and its output, each with its own year. */
export function figuresOf(p: InfraProps): { capacity?: Figure; output?: Figure } {
  if (isLegacy(p)) return legacyFigures(p);
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
  const legacy = isLegacy(p);
  const u = fig.u;
  const unit = unitOf(u);
  // legacy: an unknown unit is only comparable with itself. Migrated files: the same unit string.
  const dim = legacy ? (unit ? unit[1] : `u:${u.split(' ')[0]}`) : u;
  const rank = fig.v * (unit ? unit[2] : 1);
  const rest = fig.n ?? '';
  const form = formOf(rest);
  const basis: CapacityRead['basis'] = legacy
    ? PLANNED.test(rest) ? 'planned' : 'operating'
    : p.status === 'planned' || p.status === 'construction' ? 'planned' : p.status === 'closed' ? 'closed' : 'operating';
  const sfx = basis === 'operating' ? '' : `|${basis}`;
  // capacity, production, exports and throughput are never ranked against each other
  const what = legacy ? '' : `${fig.kind}|`;
  const main = p.k[0];
  const base = { form, basis, fig, rank };
  // a figure counted as port traffic says how busy the port is when the text names no commodity
  const text = fig.kind === 'throughput' ? `${rest} throughput` : rest;

  let subject = SUBJECTS.find(([re]) => re.test(rest))?.[1];
  if (!subject) {
    if (p.type === 'port' && (TOTAL_TRAFFIC.test(text) || (ALL_CARGO.test(text) && p.k.length !== 1))) {
      return { kind: 'cargo', key: `cargo|${what}${dim}${sfx}`, ...base };
    }
    const lng = p.type === 'lng-export' || p.type === 'lng-import';
    const family = !legacy && u === 'kb/d' ? LIQUIDS : !legacy && (u === 'bcm/y' || (lng && u === 'Mtpa')) ? GASES : dim === 'liquid' ? LIQUIDS : dim === 'gas' || lng ? GASES : null;
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
