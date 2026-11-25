/**
 * The arithmetic of the voyage calculator of the route pages: which routes have one, what its fields start from, and the
 * formulas. Pure (no Preact, no fetch, no storage): `node --test` loads it as it is (scripts/voyage.test.mjs).
 *
 * The calculator is a calculation on the figures a visitor types. It is not a market rate and not a Baltic Exchange value. Its
 * formulas are those of a time-charter equivalent as the Baltic's Guide to Market Benchmarks lays the structure out (revenue less
 * the voyage costs, over the voyage days), with a weather allowance of zero and a commission of zero: the visitor can put either
 * into the port costs. Nothing a market decides (hire, freight rate, bunker price, port costs, canal tolls, port days, port fuel)
 * has a default: those fields start empty.
 *
 * Every figure of a Baltic standard vessel is read through `standardVessel` and nowhere else, so that one line switches the
 * speed and fuel defaults off (the fields then start from the speed assumed for the class, and the fuel fields start empty).
 */
import type { AltRouting, Route, VesselClass, VesselStd } from '../types';

/** The fields of the calculator, in the order of the form. Distances in nm, speeds in kn, fuel in t/day, money in USD. */
export type Field =
  | 'cargoT'
  | 'portDays'
  | 'ladenNm'
  | 'ballastNm'
  | 'ladenKn'
  | 'ballastKn'
  | 'ladenFuel'
  | 'ballastFuel'
  | 'portFuelT'
  | 'bunkerUsdPerT'
  | 'portCostsUsd'
  | 'tollsUsd'
  | 'hireUsdPerDay'
  | 'freightUsdPerT';

export type Inputs = Record<Field, number | null>;

export const FIELDS: Field[] = [
  'cargoT', 'portDays', 'ladenNm', 'ballastNm', 'ladenKn', 'ballastKn', 'ladenFuel', 'ballastFuel', 'portFuelT',
  'bunkerUsdPerT', 'portCostsUsd', 'tollsUsd', 'hireUsdPerDay', 'freightUsdPerT',
];

/** What a market decides: these fields never have a default. */
export const MARKET_FIELDS: Field[] = ['portDays', 'portFuelT', 'bunkerUsdPerT', 'portCostsUsd', 'tollsUsd', 'hireUsdPerDay', 'freightUsdPerT'];

/** Fields that count as zero when empty, and are named in `excluded` when they are. */
export const OPTIONAL_FIELDS: Field[] = ['portDays', 'portFuelT', 'tollsUsd', 'portCostsUsd'];

/** The label of each field, as the form and the line of what is not counted print it (unit last). */
export const FIELD_LABEL: Record<Field, string> = {
  cargoT: 'Cargo, t',
  portDays: 'Port and canal days',
  ladenNm: 'Laden distance, nm',
  ballastNm: 'Ballast distance, nm',
  ladenKn: 'Laden speed, kn',
  ballastKn: 'Ballast speed, kn',
  ladenFuel: 'Laden fuel, t/day',
  ballastFuel: 'Ballast fuel, t/day',
  portFuelT: 'Port fuel, t',
  bunkerUsdPerT: 'Bunker price, USD/t',
  portCostsUsd: 'Port costs, USD',
  tollsUsd: 'Canal tolls, round voyage, USD',
  hireUsdPerDay: 'Hire, USD/day',
  freightUsdPerT: 'Freight, USD/t',
};

export const emptyInputs = (): Inputs => Object.fromEntries(FIELDS.map((f) => [f, null])) as Inputs;

// ------------------------------------------------------------------ which routes

/**
 * A route has a calculator when it is a laden voyage that a ship makes once, with a class that has a cargo. Not: a round-voyage
 * benchmark, a time-charter trip (`definition.tc`, or any benchmark with a duration as defined: delivery to redelivery, no return
 * leg to count), a trip drawn as its laden leg, a stand-in trace (the distance is another route's), an ended benchmark, a
 * container route (freight is per TEU).
 */
export function voyageEligible(r: Route): boolean {
  if (r.roundVoyage || r.drawnAs || r.standIn || r.discontinued) return false;
  if (r.definition?.tc || r.definition?.duration) return false;
  return r.vclass !== 'container';
}

// ------------------------------------------------------------------ the standard vessel

/**
 * Classes whose standard vessel burns something other than fuel oil, so that a fuel-oil figure beside the speed would mislead:
 * the Baltic's LNG benchmark is a carrier that burns its cargo (priced as LNG, not as bunkers), and the figure the atlas holds
 * for it is fuel oil. Its speed is a default; its fuel fields start empty.
 */
const NO_FUEL_DEFAULT = new Set(['lng']);

/** The speed and fuel of the Baltic standard vessel that applies to a route, with the page they come from. */
export interface StandardVessel {
  /** the class whose standard vessel it is: the route's own, or the one its `bench` names */
  classId: string;
  fromBench: boolean;
  dwt?: number;
  speed: { laden: number; ballast: number };
  /** tonnes of fuel oil a day at that speed; null when the class's figure is not a default (see NO_FUEL_DEFAULT) */
  fuel: { laden: number; ballast: number } | null;
  /** source id, year, page and the sentence the class page prints */
  s: string;
  y: number;
  url?: string;
  n: string;
}

const pos = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x) && x > 0;
const hasSpeedAndFuel = (std: VesselStd | undefined): std is VesselStd =>
  !!std && pos(std.speed?.laden) && pos(std.speed?.ballast) && pos(std.cons?.laden) && pos(std.cons?.ballast);

/**
 * The standard vessel of a route's class: its own `std` when it has speed and fuel for both legs, else that of the class
 * named by `bench` (Supramax takes the Ultramax ship, Panamax the Kamsarmax, Newcastlemax the Capesize), else nothing.
 * This is the only place the calculator reads a Baltic figure: returning null here switches every speed and fuel default off.
 */
export function standardVessel(r: Pick<Route, 'vclass'>, classes: VesselClass[]): StandardVessel | null {
  const own = classes.find((c) => c.id === r.vclass);
  if (!own) return null;
  let from = own;
  let fromBench = false;
  if (!hasSpeedAndFuel(own.std)) {
    const named = own.bench ? classes.find((c) => c.id === own.bench!.id) : undefined;
    if (!named || !hasSpeedAndFuel(named.std)) return null;
    from = named;
    fromBench = true;
  }
  const std = from.std!;
  return {
    classId: from.id,
    fromBench,
    dwt: std.dwt,
    speed: { laden: std.speed!.laden!, ballast: std.speed!.ballast! },
    fuel: NO_FUEL_DEFAULT.has(from.id) ? null : { laden: std.cons!.laden!, ballast: std.cons!.ballast! },
    s: std.s,
    y: std.y,
    url: std.url,
    n: std.n,
  };
}

// ------------------------------------------------------------------ defaults

/** Where a default comes from: a source id, the year of the page when a file gives one, and what the atlas did to it. */
export interface Trace {
  s: string;
  y?: number;
  /** "Atlas estimate" or "Atlas assumption" for a figure the atlas supplies itself */
  label?: string;
  n?: string;
}

export interface Defaults {
  values: Inputs;
  /** one entry per field that has a default */
  traces: Partial<Record<Field, Trace>>;
  /** the routing the distance is that of: null for the main one */
  routing: { label: string | null; via: string[] };
  /** the canals whose tolls the visitor may type: `suez` and `panama` in the routing's passages */
  canals: ('suez' | 'panama')[];
  /** null when the route's class has no standard vessel (or the defaults are off) */
  vessel: StandardVessel | null;
}

/** `suez` and `panama` among the passages of a routing, in the order crossed. Other passages' dues go into the port costs. */
export const tollCanals = (via: string[] | undefined): ('suez' | 'panama')[] =>
  (via ?? []).filter((c): c is 'suez' | 'panama' => c === 'suez' || c === 'panama');

/** The alternatives of a route that have a distance of their own (the `viaAlt` options of parallel straits have none). */
export const routingOptions = (r: Pick<Route, 'alts'>): AltRouting[] => (r.alts ?? []).filter((a) => pos(a.distanceNm));

/**
 * What each field starts from for a route and one of its routings (`alt`: an index into `routingOptions`, null for the main
 * routing). A field that no file holds and the atlas does not supply stays null.
 * - cargo: the parcel of the definition, when it is in tonnes;
 * - laden distance: the distance of the routing (SeaRoute, as the Distance tile shows it; no year);
 * - ballast distance: the laden one, an Atlas estimate (the ship is taken to return in ballast by the same routing);
 * - speeds and fuel: the standard vessel's, else the speed assumed for the class (Atlas assumption) and no fuel.
 */
export function voyageDefaults(r: Route, alt: number | null, classes: VesselClass[]): Defaults {
  const values = emptyInputs();
  const traces: Partial<Record<Field, Trace>> = {};
  const options = routingOptions(r);
  const chosen = alt != null ? options[alt] : undefined;
  const via = chosen ? chosen.via : r.via;

  if (r.parcelUnit === 't' && pos(r.parcel)) {
    values.cargoT = r.parcel;
    traces.cargoT = { s: r.s, y: r.definition?.y, n: 'Cargo size of the benchmark definition' };
  }

  const ladenNm = chosen ? chosen.distanceNm : r.distanceNm;
  if (pos(ladenNm)) {
    values.ladenNm = ladenNm;
    traces.ladenNm = { s: 'eurostat-searoute', n: 'SeaRoute network, Atlas routing' };
    values.ballastNm = ladenNm;
    traces.ballastNm = {
      s: 'atlas',
      label: 'Atlas estimate',
      n: 'Atlas estimate: the ship is taken to return in ballast by the same routing, so the ballast distance is the laden distance of the routing chosen. The benchmark definitions give no ballast leg.',
    };
  }

  const vessel = standardVessel(r, classes);
  if (vessel) {
    const how = vessel.fromBench ? `standard ${vessel.classId} vessel` : 'standard vessel of the class';
    const note = `${vessel.s === 'baltic' ? 'Baltic Exchange ' : ''}${how}${vessel.dwt ? `, ${vessel.dwt.toLocaleString('en-US')} dwt` : ''}: ${vessel.fuel ? 'speed and fuel at the speed shown' : 'speed at the speed shown, no fuel default'}`;
    values.ladenKn = vessel.speed.laden;
    values.ballastKn = vessel.speed.ballast;
    traces.ladenKn = { s: vessel.s, y: vessel.y, n: note };
    traces.ballastKn = { s: vessel.s, y: vessel.y, n: note };
    if (vessel.fuel) {
      values.ladenFuel = vessel.fuel.laden;
      values.ballastFuel = vessel.fuel.ballast;
      traces.ladenFuel = { s: vessel.s, y: vessel.y, n: note };
      traces.ballastFuel = { s: vessel.s, y: vessel.y, n: note };
    }
  } else {
    const cls = classes.find((c) => c.id === r.vclass);
    const kn = cls?.speed?.v ?? cls?.speedKn ?? r.speedKn;
    if (pos(kn)) {
      values.ladenKn = kn;
      traces.ladenKn = { s: 'atlas', y: typeof cls?.speed?.y === 'number' ? cls.speed.y : undefined, label: 'Atlas assumption', n: cls?.speed?.n ?? 'Atlas assumption: the laden service speed assumed for the class' };
      values.ballastKn = kn;
      traces.ballastKn = { s: 'atlas', label: 'Atlas estimate', n: 'Atlas estimate: the ballast speed is taken equal to the laden speed' };
    }
  }
  return { values, traces, routing: { label: chosen ? chosen.label : null, via: via ?? [] }, canals: tollCanals(via), vessel };
}

// ------------------------------------------------------------------ the arithmetic

export interface Result {
  /** sea days of the laden leg Sl = Dl / (24 vl) and of the ballast leg Sb = Db / (24 vb); the ballast leg is 0 when Db is 0 */
  ladenDays: number | null;
  ballastDays: number | null;
  /** the port and canal days counted: the typed figure, 0 when empty */
  portDays: number | null;
  /** round-voyage days T = Sl + Sb + P */
  days: number | null;
  /** tonnes of fuel at sea M = cl Sl + cb Sb; fuel burned in port as typed; their sum, the tonnes paid for */
  seaFuelT: number | null;
  portFuelT: number | null;
  fuelT: number | null;
  /** bunker cost B = fuel x bunker price (USD) */
  bunkersUsd: number | null;
  /** canal tolls + port costs, as typed (0 when empty) */
  extrasUsd: number | null;
  /** freight that covers the hire H: (H T + B + X) / Q, USD/t, with its parts (they add up to it) */
  freight: { usdPerT: number; parts: { hire: number; bunkers: number; tolls: number; portCosts: number } } | null;
  /** time-charter equivalent of the typed rate F: (F Q - B - X) / T, USD/day, negative when the rate does not cover the costs */
  tce: { usdPerDay: number; revenueUsd: number } | null;
  /** the optional fields that were empty and counted as zero */
  excluded: Field[];
}

/** An optional figure: empty counts as zero, a negative or non-finite one makes the calculation impossible (null). */
const optional = (x: number | null): number | null => (x == null ? 0 : Number.isFinite(x) && x >= 0 ? x : null);

/**
 * The formulas, with Q the cargo, Dl and Db the distances, vl and vb the speeds, cl and cb the fuel a day, P the port and canal
 * days, Fp the port fuel, p the bunker price, X = tolls + port costs, H the hire and F the freight:
 *   Sl = Dl / (24 vl), Sb = Db / (24 vb), T = Sl + Sb + P, M = cl Sl + cb Sb + Fp, B = M p,
 *   freight that covers the hire = (H T + B + X) / Q, time-charter equivalent = (F Q - B - X) / T.
 * Each result is null when one of its inputs is missing or is not a positive number (P, Fp, tolls and port costs may be zero; a
 * ballast distance of 0 needs neither a ballast speed nor ballast fuel). `shown` names the optional fields the form shows (a
 * route that crosses no canal has no tolls field): those that are empty are listed in `excluded`.
 */
export function voyage(i: Inputs, shown: Field[] = OPTIONAL_FIELDS): Result {
  const ladenDays = pos(i.ladenNm) && pos(i.ladenKn) ? i.ladenNm / (24 * i.ladenKn) : null;
  const noBallast = i.ballastNm === 0;
  const ballastDays = noBallast ? 0 : pos(i.ballastNm) && pos(i.ballastKn) ? i.ballastNm / (24 * i.ballastKn) : null;
  const portDays = optional(i.portDays);
  const portFuelT = optional(i.portFuelT);
  const tolls = optional(i.tollsUsd);
  const portCosts = optional(i.portCostsUsd);
  const extrasUsd = tolls != null && portCosts != null ? tolls + portCosts : null;
  const days = ladenDays != null && ballastDays != null && portDays != null ? ladenDays + ballastDays + portDays : null;

  let seaFuelT: number | null = null;
  if (ladenDays != null && ballastDays != null && pos(i.ladenFuel) && (noBallast || pos(i.ballastFuel))) {
    seaFuelT = i.ladenFuel * ladenDays + (noBallast ? 0 : i.ballastFuel! * ballastDays);
  }
  const fuelT = seaFuelT != null && portFuelT != null ? seaFuelT + portFuelT : null;
  const bunkersUsd = fuelT != null && pos(i.bunkerUsdPerT) ? fuelT * i.bunkerUsdPerT : null;

  let freight: Result['freight'] = null;
  if (days != null && bunkersUsd != null && extrasUsd != null && tolls != null && portCosts != null && pos(i.cargoT) && pos(i.hireUsdPerDay)) {
    const q = i.cargoT;
    const parts = { hire: (i.hireUsdPerDay * days) / q, bunkers: bunkersUsd / q, tolls: tolls / q, portCosts: portCosts / q };
    freight = { usdPerT: parts.hire + parts.bunkers + parts.tolls + parts.portCosts, parts };
  }
  let tce: Result['tce'] = null;
  if (days != null && days > 0 && bunkersUsd != null && extrasUsd != null && pos(i.cargoT) && pos(i.freightUsdPerT)) {
    const revenueUsd = i.freightUsdPerT * i.cargoT;
    tce = { usdPerDay: (revenueUsd - bunkersUsd - extrasUsd) / days, revenueUsd };
  }
  const excluded = shown.filter((f) => i[f] == null);
  return { ladenDays, ballastDays, portDays, days, seaFuelT, portFuelT, fuelT, bunkersUsd, extrasUsd, freight, tce, excluded };
}

// ------------------------------------------------------------------ typed text

/**
 * A typed number: digits with an optional decimal point and thousands commas ("1,250.5", " 12 ", ".5"). Empty text, a sign,
 * letters and an exponent are not numbers (null); so is the value that is not finite.
 */
export function parseNumber(text: string): number | null {
  const t = text.trim();
  if (!/^(?:\d+|\d{1,3}(?:,\d{3})+)?(?:\.\d+)?$/.test(t) || !/\d/.test(t)) return null;
  const v = Number(t.replace(/,/g, ''));
  return Number.isFinite(v) ? v : null;
}

/** A typed field: its value, and whether the text is something other than empty or a number (the field takes the warning colour). */
export function parseField(text: string): { value: number | null; invalid: boolean } {
  const value = parseNumber(text);
  return { value, invalid: value == null && text.trim() !== '' };
}

const usd0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const usd2 = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const d1 = new Intl.NumberFormat('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const MINUS = '−';

/** Money with thousands separators: 2 decimals for a figure per tonne, none otherwise; a minus sign for a loss; a dash for nothing. */
export function formatUsd(v: number | null | undefined, perTonne = false): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const s = (perTonne ? usd2 : usd0).format(Math.abs(v));
  return v < 0 && /[1-9]/.test(s) ? MINUS + s : s;
}

/** Days with one decimal. */
export function formatDays(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? '—' : d1.format(v);
}
