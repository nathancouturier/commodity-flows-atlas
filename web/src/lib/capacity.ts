/**
 * Reads the free-text capacity of an infrastructure asset ("1.28 Mt Cu (2024)", "745 koz Au (2023)",
 * "1,261 Mt total cargo (2022)") so that a list ranks assets among comparable figures only.
 *
 * Nothing here changes a published figure: a row still prints the source's own number and unit. The
 * factors below are unit definitions (pound, troy ounce, short ton, cubic foot) and serve the order alone.
 */
import type { InfraProps } from '../types';

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
  /** planned: a figure of the planned / expected / potential / licensed kind, kept apart from operating figures */
  basis: 'operating' | 'planned';
}

const NONE: CapacityRead = { kind: 'none', key: 'none', rank: 0, form: 'product', basis: 'operating' };

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

/**
 * Capacity of an asset as seen from a commodity page (`id`), or from the asset itself when `id` is
 * omitted (country pages, where each figure is kept under the commodity it counts).
 */
export function readCapacity(p: InfraProps, id?: string): CapacityRead {
  const c = p.capacity;
  if (!c || !Number.isFinite(c.v)) return NONE;
  const u = c.u ?? '';
  const unit = unitOf(u);
  // an unknown unit is only comparable with itself
  const dim = unit ? unit[1] : `u:${u.split(' ')[0]}`;
  const rank = c.v * (unit ? unit[2] : 1);
  const rest = unit ? u.slice(unit[0].length).replace(/^\/y/, '').trim() : u;
  const form = formOf(rest);
  const basis = PLANNED.test(rest) ? 'planned' : 'operating';
  const sfx = basis === 'planned' ? '|planned' : '';
  const main = p.k[0];

  let subject = SUBJECTS.find(([re]) => re.test(rest))?.[1];
  if (!subject) {
    if (p.type === 'port' && (TOTAL_TRAFFIC.test(rest) || (ALL_CARGO.test(rest) && p.k.length !== 1))) {
      return { kind: 'cargo', key: `cargo|${dim}${sfx}`, rank, form, basis };
    }
    const family = dim === 'liquid' ? LIQUIDS : dim === 'gas' || p.type === 'lng-export' || p.type === 'lng-import' ? GASES : null;
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
  return { kind: 'own', key: `${dim}|${subject}|${form}${sfx}`, rank, subject, form, basis };
}
