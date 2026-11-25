/**
 * The arithmetic of the voyage calculator (src/lib/voyage.ts): which routes have one, what its fields start from, and the formulas.
 * The routes, the vessel classes and the sources are read from data/, so the test follows the files and holds no figure of them:
 * `node web/scripts/voyage.test.mjs`.
 *
 * The worked example is written from the structure of a time-charter equivalent as the Baltic Exchange's Guide to Market Benchmarks
 * lays it out (Appendix 3, the structure only): TCE = (gross freight - fuel cost - voyage costs) / total voyage duration, where
 * the fuel cost is days x consumption x price for the laden leg, the ballast leg and the port, the voyage costs are the port costs
 * (and canal tolls), and the weather allowance and the commission are zero. It is written the way the guide writes it (a duration
 * in hours first, a cost per day, per-tonne last), not the way voyage.ts does, so that a slip in how the module reads the formula
 * shows. For the benchmark C3 the fields it reads are:
 *   routes.json   C3.parcel (cargo, t), C3.distanceNm (laden nm; the ballast leg is the same routing)
 *   vessel-classes.json   capesize.std.speed.laden / .ballast (kn), capesize.std.cons.laden / .ballast (t a day)
 *   laden days   = (C3.distanceNm / speed.laden) / 24            ballast days = (C3.distanceNm / speed.ballast) / 24
 *   duration     = laden days + ballast days + port days
 *   fuel cost    = price x (laden days x cons.laden + ballast days x cons.ballast + port fuel)
 *   voyage costs = port costs + canal tolls
 *   TCE          = (freight x C3.parcel - fuel cost - voyage costs) / duration
 *   the freight that covers a hire H is the gross freight at which TCE = H, per tonne: (H x duration + fuel cost + voyage costs) / C3.parcel.
 * The market figures are inputs of the test, defined once below: they are not market figures.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { emptyInputs, FIELD_LABEL, formatDays, formatUsd, MARKET_FIELDS, OPTIONAL_FIELDS, parseField, parseNumber, routingOptions, standardVessel, tollCanals, voyage, voyageDefaults, voyageEligible } from '../src/lib/voyage.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const data = (rel) => JSON.parse(fs.readFileSync(path.join(here, '../../data', rel), 'utf8'));
const routes = data('freight/routes.json');
const classes = data('freight/vessel-classes.json');
const sources = new Set(data('sources.json').map((s) => s.id));
const classOf = (id) => classes.find((c) => c.id === id);
const route = (id) => routes.find((r) => r.id === id);

/** Numbers typed into the test's calculator. They stand for nothing in the market. */
const TYPED = { portDays: 6, portFuelT: 40, bunkerUsdPerT: 500, portCostsUsd: 100000, tollsUsd: 0, hireUsdPerDay: 20000, freightUsdPerT: 25 };

const near = (a, b, msg) => assert.ok(Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(b)), `${msg ?? ''} ${a} is not ${b}`);
const full = (r, alt = null, typed = TYPED) => ({ ...voyageDefaults(r, alt, classes).values, ...typed });

// ---- the standard vessel, read from the class by a rule of the test's own (the class, else the class its `bench` names)
const legs = (std) => std?.speed?.laden > 0 && std.speed.ballast > 0 && std.cons?.laden > 0 && std.cons.ballast > 0;
function refStd(classId) {
  const c = classOf(classId);
  if (!c) return null;
  if (legs(c.std)) return c.std;
  const b = c.bench ? classOf(c.bench.id) : null;
  return b && legs(b.std) ? b.std : null;
}
/** The class whose standard vessel it is, for the test's own rule of the fuel exception. */
const refClassOfStd = (classId) => (legs(classOf(classId)?.std) ? classId : classOf(classId)?.bench?.id);

// ---- which routes
const FLAGS = [
  (r) => r.roundVoyage, (r) => r.drawnAs, (r) => r.standIn, (r) => r.discontinued, (r) => r.definition?.tc, (r) => r.definition?.duration, (r) => r.vclass === 'container',
];
const eligible = routes.filter(voyageEligible);

test('no route that is eligible has a flag of an ineligible one', (t) => {
  for (const r of eligible) {
    assert.ok(!FLAGS.some((f) => f(r)), `${r.id} is eligible and has a flag: roundVoyage, drawnAs, standIn, discontinued, definition.tc, definition.duration or class container`);
  }
  const eligibleByFlags = routes.filter((r) => !FLAGS.some((f) => f(r)));
  assert.deepEqual(eligible.map((r) => r.id), eligibleByFlags.map((r) => r.id));
  assert.ok(eligible.length > 100 && eligible.length < routes.length);
  t.diagnostic(`${eligible.length} of ${routes.length} routes are eligible`);
});

test('each flag takes a route out, and a plain route stays in', () => {
  const plain = eligible[0];
  assert.equal(voyageEligible(plain), true);
  for (const extra of [{ roundVoyage: true }, { drawnAs: 'typical laden leg' }, { standIn: 'C3' }, { discontinued: '2025-01' }, { vclass: 'container' }]) {
    assert.equal(voyageEligible({ ...plain, ...extra }), false, JSON.stringify(extra));
  }
  assert.equal(voyageEligible({ ...plain, definition: { ...plain.definition, tc: true } }), false);
  assert.equal(voyageEligible({ ...plain, definition: { ...plain.definition, duration: '25-30 days' } }), false);
});

test('the counts follow the data', (t) => {
  let withVessel = 0;
  let withFuel = 0;
  let withCargo = 0;
  let withTolls = 0;
  for (const r of routes) {
    if (FLAGS.some((f) => f(r))) continue;
    const std = refStd(r.vclass);
    if (std) withVessel++;
    if (std && refClassOfStd(r.vclass) !== 'lng') withFuel++;
    if (r.parcelUnit === 't' && r.parcel > 0) withCargo++;
    if ((r.via ?? []).some((c) => c === 'suez' || c === 'panama')) withTolls++;
  }
  const counts = {
    withVessel: eligible.filter((r) => standardVessel(r, classes)).length,
    withFuel: eligible.filter((r) => standardVessel(r, classes)?.fuel).length,
    withCargo: eligible.filter((r) => voyageDefaults(r, null, classes).values.cargoT != null).length,
    withTolls: eligible.filter((r) => voyageDefaults(r, null, classes).canals.length > 0).length,
  };
  assert.deepEqual(counts, { withVessel, withFuel, withCargo, withTolls });
  t.diagnostic(`eligible ${eligible.length}; with a standard vessel ${withVessel}; with its fuel as a default ${withFuel}; with a cargo size in tonnes ${withCargo}; main routing crosses Suez or Panama ${withTolls}`);
});

// ---- the defaults
test('the defaults equal the files, for every eligible route and every routing', () => {
  for (const r of eligible) {
    const std = refStd(r.vclass);
    const noFuel = refClassOfStd(r.vclass) === 'lng';
    const options = [null, ...routingOptions(r).map((_, i) => i)];
    assert.deepEqual(routingOptions(r), (r.alts ?? []).filter((a) => a.distanceNm > 0));
    for (const alt of options) {
      const d = voyageDefaults(r, alt, classes);
      const v = d.values;
      const nm = alt == null ? r.distanceNm : routingOptions(r)[alt].distanceNm;
      assert.equal(v.cargoT, r.parcelUnit === 't' ? r.parcel : null, `${r.id} cargo`);
      assert.equal(v.ladenNm, nm, `${r.id} laden distance`);
      assert.equal(v.ballastNm, nm, `${r.id} ballast distance`);
      if (std) {
        assert.equal(v.ladenKn, std.speed.laden, `${r.id} laden speed`);
        assert.equal(v.ballastKn, std.speed.ballast, `${r.id} ballast speed`);
        assert.equal(v.ladenFuel, noFuel ? null : std.cons.laden, `${r.id} laden fuel`);
        assert.equal(v.ballastFuel, noFuel ? null : std.cons.ballast, `${r.id} ballast fuel`);
      } else {
        assert.equal(v.ladenKn, classOf(r.vclass).speed.v, `${r.id}: the class's assumed speed`);
        assert.equal(v.ballastKn, v.ladenKn);
        assert.equal(v.ladenFuel, null);
        assert.equal(v.ballastFuel, null);
      }
      for (const f of MARKET_FIELDS) assert.equal(v[f], null, `${r.id}: ${f} is a market figure and has no default`);
      const via = alt == null ? r.via : routingOptions(r)[alt].via;
      assert.deepEqual(d.canals, via.filter((c) => c === 'suez' || c === 'panama'), `${r.id} canals`);
      assert.deepEqual(tollCanals(via), d.canals);
      assert.equal(d.routing.label, alt == null ? null : routingOptions(r)[alt].label);
    }
  }
});

test('no market field is read from a route', () => {
  // a route that carries a stray field of the kind must not leak into a default
  const r = { ...eligible[0], hireUsdPerDay: 1, bunkerUsdPerT: 2, portDays: 3 };
  const v = voyageDefaults(r, null, classes).values;
  for (const f of MARKET_FIELDS) assert.equal(v[f], null);
});

test('every default has a source that exists, and an estimate says so', () => {
  const year = new Date().getFullYear();
  let seen = 0;
  for (const r of eligible) {
    for (const alt of [null, ...routingOptions(r).map((_, i) => i)]) {
      const { traces, values } = voyageDefaults(r, alt, classes);
      for (const [f, t] of Object.entries(traces)) {
        seen++;
        assert.ok(sources.has(t.s), `${r.id} ${f}: source "${t.s}" is not in sources.json`);
        if (t.y !== undefined) assert.ok(Number.isInteger(t.y) && t.y >= 2020 && t.y <= year, `${r.id} ${f}: year ${t.y}`);
        assert.notEqual(values[f], null, `${r.id}: a trace for ${f}, which has no value`);
        if (t.s === 'atlas') assert.match(t.n ?? '', /^Atlas (estimate|assumption)/, `${r.id} ${f}: an atlas figure says what it is`);
      }
      for (const [f, v] of Object.entries(values)) if (v != null) assert.ok(traces[f], `${r.id} ${f}: a default with no source`);
      // the ballast distance: an estimate of the atlas, with no year (it is not a figure of a file)
      if (values.ballastNm != null) {
        const b = traces.ballastNm;
        assert.equal(b.s, 'atlas');
        assert.equal(b.label, 'Atlas estimate');
        assert.equal(b.y, undefined);
        assert.match(b.n, /^Atlas estimate/);
        assert.match(b.n, /same routing/);
      }
      // a standard vessel's figure carries the page and the year read in the class
      if (traces.ladenFuel) {
        const std = refStd(r.vclass);
        assert.equal(traces.ladenFuel.s, std.s);
        assert.equal(traces.ladenFuel.y, std.y);
      }
      // the cargo: the source and the year of the definition
      if (traces.cargoT) {
        assert.equal(traces.cargoT.s, r.s);
        assert.equal(traces.cargoT.y, r.definition?.y);
      }
    }
  }
  assert.ok(seen > 1000);
});

test('the class LNG has a speed but no fuel default, and the one function switches the defaults off', () => {
  const lng = eligible.find((r) => r.vclass === 'lng');
  assert.ok(lng, 'an eligible LNG route');
  const d = voyageDefaults(lng, null, classes);
  assert.equal(d.values.ladenKn, classOf('lng').std.speed.laden);
  assert.equal(d.values.ladenFuel, null);
  assert.equal(d.values.ballastFuel, null);
  assert.equal(standardVessel(lng, classes).fuel, null);
  // with every standard vessel gone, no speed or fuel of the Baltic remains: the class's assumed speed, no fuel
  const bare = classes.map(({ std, ...c }) => c);
  for (const r of eligible) {
    assert.equal(standardVessel(r, bare), null);
    const v = voyageDefaults(r, null, bare).values;
    assert.equal(v.ladenKn, classOf(r.vclass).speed.v);
    assert.equal(v.ladenFuel, null);
    assert.equal(v.ballastFuel, null);
  }
});

test('a class takes the standard vessel of the class its bench names, and the vessel says which', () => {
  const viaBench = classes.filter((c) => !legs(c.std) && c.bench && legs(classOf(c.bench.id)?.std));
  assert.ok(viaBench.length >= 3, 'the Supramax, Panamax and Newcastlemax classes name a benchmark class');
  for (const c of viaBench) {
    const v = standardVessel({ vclass: c.id }, classes);
    assert.equal(v.classId, c.bench.id);
    assert.equal(v.fromBench, true);
    assert.equal(v.speed.laden, classOf(c.bench.id).std.speed.laden);
  }
  const own = classes.find((c) => legs(c.std));
  assert.equal(standardVessel({ vclass: own.id }, classes).fromBench, false);
  const none = classes.find((c) => !legs(c.std) && !c.bench);
  assert.equal(standardVessel({ vclass: none.id }, classes), null);
  assert.equal(standardVessel({ vclass: 'no-such-class' }, classes), null);
});

// ---- the arithmetic against the form of the Baltic's guide
/** The calculation as the guide lays it out: durations in hours first, a cost per day, the tonne last. Zero weather allowance, zero commission. */
function guide(r, std, typed) {
  const nm = r.distanceNm; // the ballast leg is the same routing
  const ladenDays = nm / std.speed.laden / 24;
  const ballastDays = nm / std.speed.ballast / 24;
  const duration = ladenDays + ballastDays + typed.portDays;
  const fuelCost = typed.bunkerUsdPerT * (ladenDays * std.cons.laden + ballastDays * std.cons.ballast + typed.portFuelT);
  const voyageCosts = typed.portCostsUsd + typed.tollsUsd;
  const tonnes = r.parcel;
  const grossFreight = typed.freightUsdPerT * tonnes;
  const grossToCoverHire = typed.hireUsdPerDay * duration + fuelCost + voyageCosts;
  return {
    ladenDays, ballastDays, duration, fuelCost,
    tce: (grossFreight - fuelCost - voyageCosts) / duration,
    freight: grossToCoverHire / tonnes,
    parts: { hire: (typed.hireUsdPerDay * duration) / tonnes, bunkers: fuelCost / tonnes, tolls: typed.tollsUsd / tonnes, portCosts: typed.portCostsUsd / tonnes },
    fuelT: ladenDays * std.cons.laden + ballastDays * std.cons.ballast + typed.portFuelT,
  };
}

test('the worked example C3 equals the calculation in the form of the Baltic guide', (t) => {
  const r = route('C3');
  assert.equal(voyageEligible(r), true);
  const std = classOf('capesize').std;
  const g = guide(r, std, TYPED);
  const res = voyage(full(r));
  near(res.ladenDays, g.ladenDays, 'laden days');
  near(res.ballastDays, g.ballastDays, 'ballast days');
  near(res.days, g.duration, 'days');
  near(res.fuelT, g.fuelT, 'fuel');
  near(res.bunkersUsd, g.fuelCost, 'bunkers');
  near(res.freight.usdPerT, g.freight, 'freight');
  for (const k of Object.keys(g.parts)) near(res.freight.parts[k], g.parts[k], k);
  near(res.tce.usdPerDay, g.tce, 'TCE');
  near(res.tce.revenueUsd, TYPED.freightUsdPerT * r.parcel, 'revenue');
  t.diagnostic(`C3: ${res.ladenDays.toFixed(4)} + ${res.ballastDays.toFixed(4)} + ${TYPED.portDays} = ${res.days.toFixed(4)} d; fuel ${res.fuelT.toFixed(1)} t; bunkers USD ${res.bunkersUsd.toFixed(0)}; freight to cover the hire ${res.freight.usdPerT.toFixed(4)} USD/t; TCE ${res.tce.usdPerDay.toFixed(2)} USD/day`);
});

test('the same holds for a class that takes its vessel from its bench, on every such class', () => {
  for (const c of classes.filter((x) => !legs(x.std) && x.bench && legs(classOf(x.bench.id)?.std))) {
    const r = eligible.find((x) => x.vclass === c.id && x.parcelUnit === 't');
    if (!r) continue;
    const g = guide(r, classOf(c.bench.id).std, TYPED);
    const res = voyage(full(r));
    near(res.days, g.duration, `${r.id} days`);
    near(res.freight.usdPerT, g.freight, `${r.id} freight`);
    near(res.tce.usdPerDay, g.tce, `${r.id} TCE`);
  }
});

test('with a speed and fuel typed in, a route of class LNG gets its results', () => {
  const r = eligible.find((x) => x.vclass === 'lng');
  const d = voyageDefaults(r, null, classes).values;
  const typed = { ...d, ...TYPED, cargoT: 100000, ladenFuel: 60, ballastFuel: 55 };
  assert.equal(voyage({ ...d, ...TYPED, cargoT: 100000 }).bunkersUsd, null, 'no fuel typed: no bunker cost');
  const res = voyage(typed);
  const sl = r.distanceNm / d.ladenKn / 24;
  const sb = r.distanceNm / d.ballastKn / 24;
  near(res.bunkersUsd, TYPED.bunkerUsdPerT * (60 * sl + 55 * sb + TYPED.portFuelT));
});

// ---- identities
test('the identities of the formulas', () => {
  for (const r of eligible.filter((x) => x.parcelUnit === 't' && refStd(x.vclass) && refClassOfStd(x.vclass) !== 'lng')) {
    const a = voyage(full(r));
    // the rate that covers the hire gives that hire back as a time-charter equivalent
    const back = voyage(full(r, null, { ...TYPED, freightUsdPerT: a.freight.usdPerT }));
    near(back.tce.usdPerDay, TYPED.hireUsdPerDay, `${r.id} round trip`);
    // the four parts add up to the freight
    const p = a.freight.parts;
    near(p.hire + p.bunkers + p.tolls + p.portCosts, a.freight.usdPerT, `${r.id} parts`);
  }
  // the laden sea days at the speed of the route are the days the page prints, to its one decimal (within 0.05 d)
  for (const r of eligible) {
    const v = voyage({ ...emptyInputs(), ladenNm: r.distanceNm, ladenKn: r.speedKn, ballastNm: 0 });
    assert.ok(Math.abs(v.ladenDays - r.days) <= 0.05 + 1e-9, `${r.id}: ${v.ladenDays} against the ${r.days} d of the page`);
  }
});

test('a ballast distance of 0 removes the ballast days and fuel; empty costs count as zero and are listed', () => {
  const r = route('C3');
  const withBallast = voyage(full(r));
  const without = voyage({ ...full(r), ballastNm: 0 });
  assert.equal(without.ballastDays, 0);
  near(without.days, withBallast.ladenDays + TYPED.portDays);
  near(without.seaFuelT, withBallast.ladenDays * classOf('capesize').std.cons.laden);
  // no ballast speed or fuel is needed when there is no ballast leg
  assert.notEqual(voyage({ ...full(r), ballastNm: 0, ballastKn: null, ballastFuel: null }).freight, null);
  // an empty ballast distance is not zero
  assert.equal(voyage({ ...full(r), ballastNm: null }).days, null);

  const none = voyage({ ...full(r), portDays: null, portFuelT: null, tollsUsd: null, portCostsUsd: null });
  assert.deepEqual(none.excluded, OPTIONAL_FIELDS);
  assert.equal(none.portDays, 0);
  assert.equal(none.portFuelT, 0);
  assert.equal(none.extrasUsd, 0);
  near(none.days, withBallast.ladenDays + withBallast.ballastDays);
  near(none.freight.usdPerT, (TYPED.hireUsdPerDay * none.days + none.bunkersUsd) / r.parcel);
  // a route with no canal does not list the tolls it does not show
  assert.deepEqual(voyage({ ...full(r), portDays: null, portFuelT: null, tollsUsd: null, portCostsUsd: null }, OPTIONAL_FIELDS.filter((f) => f !== 'tollsUsd')).excluded, ['portDays', 'portFuelT', 'portCostsUsd']);
  assert.deepEqual(voyage(full(r)).excluded, []);
});

test('port fuel is counted at the bunker price, and counted as zero when empty', () => {
  const r = route('C3');
  const a = voyage(full(r, null, { ...TYPED, portFuelT: null }));
  const b = voyage(full(r, null, { ...TYPED, portFuelT: 0 }));
  const c = voyage(full(r));
  near(a.bunkersUsd, b.bunkersUsd);
  near(c.bunkersUsd - a.bunkersUsd, TYPED.portFuelT * TYPED.bunkerUsdPerT);
  assert.equal(a.portFuelT, 0);
  assert.equal(c.portFuelT, TYPED.portFuelT);
});

test('an empty bunker price gives no money results and still gives days and fuel', () => {
  const res = voyage(full(route('C3'), null, { ...TYPED, bunkerUsdPerT: null }));
  assert.equal(res.bunkersUsd, null);
  assert.equal(res.freight, null);
  assert.equal(res.tce, null);
  assert.notEqual(res.days, null);
  assert.notEqual(res.fuelT, null);
});

test('without a cargo size the per-tonne results are empty and the voyage still has days, fuel and bunkers', () => {
  const r = eligible.find((x) => x.parcelUnit !== 't' && refStd(x.vclass) && refClassOfStd(x.vclass) !== 'lng');
  const res = voyage(full(r));
  assert.equal(res.freight, null);
  assert.equal(res.tce, null);
  assert.notEqual(res.days, null);
  assert.notEqual(res.bunkersUsd, null);
  assert.notEqual(voyage({ ...full(r), cargoT: 50000 }).freight, null);
});

test('a missing standard vessel gives no fuel result, not zero', () => {
  const r = eligible.find((x) => !refStd(x.vclass));
  assert.ok(r, 'a route with no standard vessel');
  const res = voyage({ ...full(r), cargoT: 30000 });
  assert.notEqual(res.days, null);
  assert.equal(res.fuelT, null);
  assert.equal(res.bunkersUsd, null);
  assert.equal(res.freight, null);
  assert.equal(res.tce, null);
});

test('a speed, a distance or a figure that is zero, negative or not finite gives nothing', () => {
  const r = route('C3');
  const base = full(r);
  for (const [f, v] of [['ladenKn', 0], ['ladenKn', -14], ['ballastKn', 0], ['ladenNm', 0], ['ladenNm', -1], ['ladenFuel', 0], ['cargoT', 0], ['cargoT', Infinity], ['bunkerUsdPerT', 0], ['hireUsdPerDay', 0], ['portDays', -1], ['tollsUsd', -5], ['portFuelT', NaN]]) {
    const res = voyage({ ...base, [f]: v });
    assert.equal(res.freight, null, `${f} = ${v}`);
  }
  assert.equal(voyage({ ...base, ladenKn: 0 }).days, null);
  assert.equal(voyage({ ...base, freightUsdPerT: 0 }).tce, null);
  // a loss is a negative time-charter equivalent, not nothing
  assert.ok(voyage({ ...base, freightUsdPerT: 0.01 }).tce.usdPerDay < 0);
});

// ---- typed text
test('parseNumber', () => {
  for (const [text, want] of [['1,250.5', 1250.5], [' 12 ', 12], ['0', 0], ['.5', 0.5], ['12.', null], ['1,234,567', 1234567], ['20000', 20000], ['3.25', 3.25]]) {
    assert.equal(parseNumber(text), want, JSON.stringify(text));
  }
  for (const text of ['', '   ', '-3', '+3', 'abc', '1e9x', '1e9', '1,25', '12,34', '1.2.3', ',5', '1 000', '0x10', '--', '.', 'NaN', 'Infinity']) {
    assert.equal(parseNumber(text), null, JSON.stringify(text));
  }
  assert.deepEqual(parseField(''), { value: null, invalid: false });
  assert.deepEqual(parseField('  '), { value: null, invalid: false });
  assert.deepEqual(parseField('12'), { value: 12, invalid: false });
  assert.deepEqual(parseField('abc'), { value: null, invalid: true });
  assert.deepEqual(parseField('-3'), { value: null, invalid: true });
});

test('formatUsd and formatDays', () => {
  assert.equal(formatUsd(1591000), '1,591,000');
  assert.equal(formatUsd(18.452, true), '18.45');
  assert.equal(formatUsd(1234.5, true), '1,234.50');
  assert.equal(formatUsd(-1234.4), '−1,234');
  assert.equal(formatUsd(-0.2), '0');
  assert.equal(formatUsd(null), '—');
  assert.equal(formatUsd(NaN), '—');
  assert.equal(formatDays(72.2917), '72.3');
  assert.equal(formatDays(null), '—');
});

// ---- nothing is stored
test('the calculator keeps nothing in the browser and writes nothing to the address', () => {
  const FORBIDDEN = ['localStorage', 'sessionStorage', 'indexedDB', 'document.cookie', 'location.hash', 'history.pushState', 'history.replaceState'];
  for (const rel of ['../src/lib/voyage.ts', '../src/components/views/RouteVoyage.tsx']) {
    const file = path.join(here, rel);
    if (!fs.existsSync(file)) continue;
    const text = fs.readFileSync(file, 'utf8');
    for (const word of FORBIDDEN) assert.ok(!text.includes(word), `${rel} mentions ${word}`);
  }
});

test('the module has no import that a browser or a build would be needed for', () => {
  const text = fs.readFileSync(path.join(here, '../src/lib/voyage.ts'), 'utf8');
  const imports = [...text.matchAll(/^import\s+(.*?)\s+from\s+'(.*?)'/gm)];
  for (const [, what, from] of imports) assert.ok(/^type\b/.test(what) && from === '../types', `import ${what} from ${from}`);
});

// ---- the wording of the block
test('the block says it is a calculation, has no placeholder text, and its result tiles cite no source', () => {
  const text = fs.readFileSync(path.join(here, '../src/components/views/RouteVoyage.tsx'), 'utf8');
  assert.ok(text.includes('A calculation on the figures above, not a market rate or a quote, and not a Baltic Exchange assessment.'));
  assert.ok(!/placeholder/i.test(text), 'a field shows no text of its own');
  assert.ok(!text.includes('data-src'), 'the component writes no data-src of its own');
  const tiles = [...text.matchAll(/<Kpi\b[^>]*\/>/g)].map((m) => m[0]);
  assert.equal(tiles.length, 2, 'two result tiles');
  for (const tile of tiles) assert.ok(!/\b(?:s|y|f)=/.test(tile), `a result tile cites a source: ${tile}`);
  // a toll figure is never typed into the block: the canal authorities' own pages are linked, nothing else is
  assert.deepEqual([...text.matchAll(/https?:\/\/[^'"\s]+/g)].map((m) => new URL(m[0]).hostname).sort(), ['pancanal.com', 'www.suezcanal.gov.eg']);
});

// ---- the method text and the credits say what the code does
// METHODOLOGY.md ("Voyage calculator"), NOTICE.md, the registry and the About window are read here, so that a change of the code
// that the texts do not follow fails this file.
const root = path.join(here, '../..');
const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8');
const oneLine = (s) => s.replace(/\s+/g, ' ');
const methodText = (() => {
  const m = read('METHODOLOGY.md');
  const start = m.indexOf('\n### Voyage calculator\n');
  assert.ok(start > 0, 'METHODOLOGY.md has the subsection "Voyage calculator"');
  const end = m.indexOf('\n## ', start);
  return m.slice(start, end);
})();
const methodFlat = oneLine(methodText);
/** The name a field has in a sentence: its label up to the first comma, in lower case ("Canal tolls, round voyage, USD" is "canal tolls"). */
const nameOf = (f) => FIELD_LABEL[f].split(',')[0].toLowerCase();
const listAfter = (re) => {
  const m = re.exec(methodFlat);
  assert.ok(m, `the method text has ${re}`);
  return m[1].split(/, /);
};

test('the formulas of the method text, evaluated, give the results of the code', () => {
  const block = /```\n([\s\S]*?)```/.exec(methodText);
  assert.ok(block, 'a block of formulas');
  const r = route('C3');
  // the figures typed into the test's calculator, with a toll so that the term is not zero
  const i = { ...voyageDefaults(r, null, classes).values, ...TYPED, tollsUsd: 250000 };
  const vars = { Q: i.cargoT, Dl: i.ladenNm, Db: i.ballastNm, vl: i.ladenKn, vb: i.ballastKn, cl: i.ladenFuel, cb: i.ballastFuel, P: i.portDays,
    Fp: i.portFuelT, p: i.bunkerUsdPerT, H: i.hireUsdPerDay, F: i.freightUsdPerT, tolls: i.tollsUsd, portcosts: i.portCostsUsd };
  const got = {};
  let lines = 0;
  for (const line of block[1].split('\n').filter((l) => l.trim())) {
    const m = /^(\w+)\s*=\s*(.+?)(?:\s{2,}\S.*)?$/.exec(line);
    assert.ok(m, `a formula line: ${line}`);
    const scope = { ...vars, ...got };
    got[m[1]] = new Function(...Object.keys(scope), `return (${m[2]});`)(...Object.values(scope));
    lines++;
  }
  assert.equal(lines, 8, 'eight formulas');
  const res = voyage(i);
  near(got.Sl, res.ladenDays, 'Sl');
  near(got.Sb, res.ballastDays, 'Sb');
  near(got.T, res.days, 'T');
  near(got.M, res.fuelT, 'M');
  near(got.B, res.bunkersUsd, 'B');
  near(got.X, res.extrasUsd, 'X');
  near(got.freight, res.freight.usdPerT, 'freight');
  near(got.TCE, res.tce.usdPerDay, 'TCE');
});

test('the method text lists what is counted as zero and what has no default as the code does', () => {
  assert.deepEqual(listAfter(/Counted as zero when empty: ([^.]+)\./), OPTIONAL_FIELDS.map(nameOf));
  assert.deepEqual(listAfter(/No default: ([^.]+)\. They are typed/), MARKET_FIELDS.map(nameOf));
  // what the form shows as not entered is the same list, minus the tolls of a route that crosses no canal
  const r = eligible.find((x) => voyageDefaults(x, null, classes).canals.length === 0);
  assert.deepEqual(voyage(voyageDefaults(r, null, classes).values, OPTIONAL_FIELDS.filter((f) => f !== 'tollsUsd')).excluded, ['portDays', 'portFuelT', 'portCostsUsd']);
});

test('the reasons a route has no block, in the method text, are the ones the code applies', () => {
  const m = /A route has none when it is: (.+?) \(freight is per TEU/.exec(methodFlat);
  assert.ok(m, 'the sentence of the reasons');
  const reasons = m[1].split('; ');
  const REASON = [
    [/round-voyage/, (r) => r.roundVoyage],
    [/time-charter trip/, (r) => r.definition?.tc || r.definition?.duration],
    [/drawn as its laden leg/, (r) => r.drawnAs],
    [/stand-in trace or an ended benchmark/, (r) => r.standIn || r.discontinued],
  ];
  assert.equal(reasons.length, REASON.length + 1, 'five reasons, the container route last');
  REASON.forEach(([re], k) => assert.match(reasons[k], re));
  assert.match(m[1].split('; ').at(-1), /container/);
  const named = (r) => REASON.some(([, f]) => f(r)) || r.vclass === 'container';
  for (const r of routes) assert.equal(voyageEligible(r), !named(r), `${r.id}: eligible exactly when none of the reasons of the text holds`);
  for (const [re, f] of REASON) assert.ok(routes.some(f), `a route of the reason ${re}`);
  assert.ok(routes.some((r) => r.vclass === 'container'));
});

test('the standard vessels the method text names are the ones the code uses', () => {
  // the class that takes the standard vessel of another
  const pairs = classes
    .filter((c) => c.bench && !legs(c.std) && legs(classOf(c.bench.id)?.std))
    .map((c) => `${c.name}: ${classOf(c.bench.id).name}`)
    .sort();
  assert.deepEqual(listAfter(/takes that of the class its benchmark names \(([^)]+)\)/)[0].split('; ').sort(), pairs);
  // the classes whose standard vessel gives a speed and no fuel default
  const noFuel = classes.filter((c) => { const v = standardVessel({ vclass: c.id }, classes); return v && !v.fuel; }).map((c) => c.id);
  assert.deepEqual(noFuel, ['lng']);
  assert.ok(methodFlat.includes('The LNG carrier takes its speed but no fuel'));
  // the classes of eligible routes with no standard vessel at all
  const none = [...new Set(eligible.filter((r) => !standardVessel(r, classes)).map((r) => classOf(r.vclass).name.toLowerCase()))].sort();
  assert.ok(none.length > 0);
  const m = /\(the ([^)]+)\) takes the laden speed assumed/.exec(methodFlat);
  assert.ok(m, 'the sentence of the classes with none');
  assert.deepEqual(m[1].split(/, the /).sort(), none);
});

test('the texts say it is not a market rate, not a quote and not a Baltic Exchange assessment, as the block does', () => {
  const block = read('web/src/components/views/RouteVoyage.tsx');
  assert.ok(block.includes('not a market rate or a quote, and not a Baltic Exchange assessment'));
  assert.ok(methodFlat.includes('not a market rate, not a quote and not a Baltic Exchange assessment'));
  assert.ok(methodFlat.includes('"Freight to cover the hire" and "Time-charter equivalent"'));
  for (const label of ['Freight to cover the hire', 'Time-charter equivalent']) assert.ok(block.includes(`label="${label}"`), label);
  const about = oneLine(read('web/src/components/AboutDialog.tsx'));
  assert.ok(about.includes('The voyage calculator of a route page is a calculation on figures the visitor types'));
  assert.ok(about.includes('not a market rate and not a Baltic Exchange assessment'));
});

test('the canal authorities are credited where the block links them, and are not entries of the registry', () => {
  const block = read('web/src/components/views/RouteVoyage.tsx');
  const urls = [block.match(/SUEZ_URL = '([^']+)'/)[1], block.match(/PANAMA_URL = '([^']+)'/)[1]];
  const notice = oneLine(read('NOTICE.md'));
  for (const url of urls) {
    assert.ok(notice.includes(url), `NOTICE.md credits ${url}`);
    assert.ok(methodFlat.includes(url), `the method text names ${url}`);
  }
  // linked pages are not sources of figures: the registry counts every entry as one in the About window
  const registry = data('sources.json');
  for (const s of registry) assert.ok(!urls.includes(s.url), `${s.id} is a linked page`);
  // no toll figure is typed in the code, the texts or the registry for them: the pages are linked, not copied
  assert.ok(!/\$\s?\d/.test(oneLine(methodText.split('Canal tolls.')[1].split('The Baltic Exchange')[0])));
});

test('the registry entry of the Baltic Exchange names the calculator and keeps the clause of its terms', () => {
  const baltic = data('sources.json').find((s) => s.id === 'baltic');
  assert.match(baltic.use, /voyage calculator/);
  assert.match(baltic.use, /stores and publishes no figure derived/);
  assert.ok(baltic.licence.includes('without the prior written consent of the Baltic'));
  assert.match(data('sources.json').find((s) => s.id === 'atlas').use, /voyage calculator/);
  const notice = oneLine(read('NOTICE.md'));
  for (const clause of ['clause 5.1', 'Data Policy', 'read on 25 November 2026', 'that is not settled', 'a choice made without the owner, listed in PROGRESS.md']) {
    assert.ok(notice.includes(clause) || methodFlat.includes(clause), `NOTICE.md or the method text says "${clause}"`);
  }
});
