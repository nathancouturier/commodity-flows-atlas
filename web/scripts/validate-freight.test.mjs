/**
 * Negative tests of scripts/validate-freight.mjs: a small valid data folder passes, and each way of breaking it
 * (a port index out of range, a mask wider than the gate list, a lane that names a passage that does not exist...)
 * makes the validator report it and the command exit 1.
 *
 *     node web/scripts/validate-freight.test.mjs
 */
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateFreight } from './validate-freight.mjs';

const script = path.join(path.dirname(fileURLToPath(import.meta.url)), 'validate-freight.mjs');

const base = () => ({
  chokepoints: [{ id: 'suez' }, { id: 'panama' }, { id: 'malacca' }],
  countries: [{ c: 'AUS' }, { c: 'CHN' }, { c: 'MNG' }],
  places: [{ c: 'GIB' }],
  caveats: { 'crude-irn': { kind: 'unrecorded', text: 'x', group: 'crude-oil', o: 'IRN', d: null } },
  lane: {
    group: 'coal',
    k: 'thermal-coal',
    unit: 'Mt',
    y: 2024,
    s: 'baci',
    years: [2023, 2024],
    seaborne: [1, 2],
    world: [1, 2],
    ports: {
      AAAAA: { id: 'AAAAA', name: 'A', c: 'AUS', at: [0, 0], zone: 'z', s: 'wikipedia', url: 'https://example.org' },
      BBBBB: { id: 'BBBBB', name: 'B', c: 'CHN', at: [1, 1], zone: null, s: null },
    },
    lanes: [
      {
        id: 'coal:AUS-CHN', k: 'thermal-coal', p: 'coal', o: 'AUS', d: 'CHN', set: 'main', load: ['AAAAA'], discharge: ['BBBBB'], portBasis: 'open',
        opts: [{ load: 'AAAAA', discharge: 'BBBBB', nm: 10, days: 1, via: ['panama'], w: null }],
        vclass: ['panamax'], distanceNm: 100, days: 5, via: ['malacca'], viaAlt: [['suez', 'panama']],
        flow: { v: 1.2, u: 'Mt', y: 2024, s: 'baci' }, share: 0.1, hist: [1, 1.2], g: [],
      },
    ],
  },
  pairs: {
    group: 'coal', k: 'thermal-coal', y: 2024, s: 'baci', unit: 'kt', seaborne: 1200,
    ports: [['AAAAA', 'A', 'AUS', 'z'], ['BBBBB', 'B', 'CHN', null]],
    classes: ['panamax'], gates: ['suez', 'panama', 'malacca'],
    cols: ['o', 'd', 'kt', 'm', 'load', 'dis', 'nm', 'cls', 'via', 'alt', 'f'],
    rows: [['AUS', 'CHN', 1200, 0, 0, 1, 100, 0, 4, 3, 4], ['MNG', 'CHN', 800, 3, -1, -1, 0, -1, 0, 0, 0]],
  },
});

function write(root, d) {
  const put = (rel, doc) => {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), JSON.stringify(doc));
  };
  put('freight/chokepoints.json', d.chokepoints);
  put('freight/caveats.json', d.caveats);
  put('countries/index.json', d.countries);
  put('countries/places.json', d.places);
  put('freight/lanes/coal.json', d.lane);
  put(`freight/pairs/${d.pairsFile ?? 'coal'}.json`, d.pairs);
  if (d.routes) put('freight/routes.json', d.routes);
  if (d.events) put('freight/events.json', d.events);
  if (d.alerts) put('freight/alerts.json', d.alerts);
  if (d.commodities) put('commodities/index.json', d.commodities);
  if (d.assets) put('infrastructure/ports.geojson', { type: 'FeatureCollection', features: d.assets.map((id) => ({ properties: { id } })) });
}

/** A valid events and alerts layer on top of base(). */
const withAlerts = (d) => {
  d.commodities = [{ id: 'thermal-coal' }, { id: 'lng' }];
  d.assets = ['fujairah'];
  d.events = [{ id: 'ev1', date: '2026-02-28', title: 't', kind: 'conflict', chokepoints: ['suez'], commodities: ['lng'], countries: ['AUS'], assets: ['fujairah'], summary: 's', src: 'https://example.org' }];
  d.alerts = [{
    id: 'a1', title: 'T', since: '2026-02', severity: 'high', severityNote: 'n', text: 'x', reviewed: '2026-11-23', event: 'ev1', src: 'https://example.org',
    chokepoints: ['suez'], commodities: ['lng'], countries: ['AUS'], exporters: [], importers: [],
    measures: [{ chokepoint: 'suez', to: '2026-11-15', transits: { now: 10, yearAgo: 20, avg2023: 30 }, s: 'portwatch' }],
  }];
};

function run(mutate) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'freight-validate-'));
  try {
    const d = base();
    mutate?.(d);
    write(root, d);
    const errors = [];
    const warn = console.warn;
    console.warn = () => {};
    try {
      validateFreight(root, errors);
    } finally {
      console.warn = warn;
    }
    const cli = spawnSync(process.execPath, [script, root], { encoding: 'utf8' });
    return { errors, status: cli.status };
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

let failed = 0;
function test(name, fn) {
  try {
    fn();
    console.log(`ok   ${name}`);
  } catch (e) {
    failed++;
    console.log(`FAIL ${name}\n     ${e.message}`);
  }
}
const rejects = (name, mutate, expected) =>
  test(name, () => {
    const { errors, status } = run(mutate);
    assert.ok(errors.some((e) => e.includes(expected)), `expected an error containing "${expected}", got ${JSON.stringify(errors)}`);
    assert.equal(status, 1, 'the command must exit 1');
  });

test('a valid folder passes and the command exits 0', () => {
  const { errors, status } = run();
  assert.deepEqual(errors, []);
  assert.equal(status, 0);
});
rejects('a port index out of range', (d) => (d.pairs.rows[0][4] = 9), 'load = 9');
rejects('a class index out of range', (d) => (d.pairs.rows[0][7] = 3), 'cls = 3');
rejects('a mode out of range', (d) => (d.pairs.rows[0][3] = 4), 'm = 4');
rejects('a mask wider than the gate list', (d) => (d.pairs.rows[0][8] = 8), 'via = 8');
rejects('a row shorter than the columns', (d) => d.pairs.rows[0].pop(), 'values for 11 columns');
rejects('a gate that is not a chokepoint', (d) => (d.pairs.gates[0] = 'nowhere'), 'gate "nowhere"');
rejects('more than 31 gates', (d) => (d.pairs.gates = Array.from({ length: 32 }, (_, i) => (i < 3 ? d.pairs.gates[i] : 'suez'))), '32 gates');
rejects('a lane that names a passage that does not exist', (d) => (d.lane.lanes[0].via = ['atlantis']), '"atlantis"');
rejects('a viaAlt passage that does not exist', (d) => (d.lane.lanes[0].viaAlt = [['suez', 'atlantis']]), '"atlantis"');
rejects('a lane port missing from the ports table', (d) => (d.lane.lanes[0].load = ['ZZZZZ']), 'port ZZZZZ');
rejects('a lane port without "s"', (d) => delete d.lane.ports.AAAAA.s, 'has no "s"');
rejects('a transit port without a source', (d) => (d.lane.lanes[0].transit = { port: 'AAAAA', c: 'AUS' }), 'transit port has no source');
rejects('a caveat that does not exist', (d) => (d.lane.lanes[0].caveat = 'nope'), 'caveat "nope"');
rejects('an estimated flow that keeps the source baci', (d) => (d.lane.lanes[0].flow.est = true), 'source id "atlas"');
rejects('a set that is neither main nor history', (d) => (d.lane.lanes[0].set = 'big'), 'set "big"');
rejects('a lane without a set once the pairs table exists', (d) => delete d.lane.lanes[0].set, 'no "set"');
rejects('a main lane under the floor of its group', (d) => (d.lane.lanes[0].flow.v = 0.01), 'floor');
rejects('a portBasis outside its list', (d) => (d.lane.lanes[0].portBasis = 'guess'), 'portBasis "guess"');
rejects('a duplicate lane id', (d) => d.lane.lanes.push({ ...d.lane.lanes[0] }), 'appears twice');
rejects('a row with a country code the atlas does not know', (d) => (d.pairs.rows[1][0] = 'ZZZ'), 'country code "ZZZ"');
rejects('a port in a country the atlas does not know', (d) => (d.pairs.ports[0][2] = 'ZZZ'), 'country "ZZZ"');
test('a place that has no country page is a known code', () => {
  const { errors } = run((d) => (d.pairs.rows[1][0] = 'GIB'));
  assert.deepEqual(errors, []);
});
rejects('bit 2 set for a pair that has no main lane', (d) => (d.pairs.rows[1][10] = 4), 'bit 2 of f disagrees');
rejects('bit 2 unset for a pair that has a main lane', (d) => (d.pairs.rows[0][10] = 0), 'bit 2 of f disagrees');
rejects('a history lane does not count as a main lane', (d) => (d.lane.lanes[0].set = 'history'), 'bit 2 of f disagrees');
rejects('seaborne that is not the sum of the sea rows', (d) => (d.pairs.seaborne = 1300), 'add up to 1200 kt');
test('seaborne within 0.1% of the sum passes', () => {
  const { errors } = run((d) => (d.pairs.seaborne = 1201));
  assert.deepEqual(errors, []);
});
rejects('a note for a pair that has no row', (d) => (d.pairs.notes = { 'AUS-JPN': 'x' }), 'note "AUS-JPN"');
rejects('a port basis index out of range', (d) => ((d.pairs.bases = ['page names the cargo']), (d.pairs.ports[0][4] = 3)), 'basis index 3');
rejects('a pairs basis outside the vocabulary of ports.py', (d) => (d.pairs.bases = ['nearest port']), 'bases names "nearest port"');
rejects('a lane port basis outside the vocabulary of ports.py', (d) => (d.lane.ports.AAAAA.basis = 'guess'), 'basis "guess"');
test('a lane port basis from ports.py passes', () => {
  const { errors } = run((d) => (d.lane.ports.AAAAA.basis = 'general port of the country'));
  assert.deepEqual(errors, []);
});
test('notes and a port basis that are well formed pass', () => {
  const { errors } = run((d) => ((d.pairs.bases = ['nearest seaport']), (d.pairs.ports[0][4] = 0), (d.pairs.notes = { 'AUS-CHN': 'Atlas estimate: x' })));
  assert.deepEqual(errors, []);
});
rejects('a second transit port without a source', (d) => ((d.lane.lanes[0].transit = { port: 'AAAAA', c: 'AUS', s: 'wikipedia' }), (d.lane.lanes[0].transit2 = { port: 'BBBBB', c: 'CHN' })), 'second transit port has no source');
rejects('a lane file without its pairs file', (d) => (d.pairsFile = 'other'), 'no pairs file');

test('a valid events and alerts layer passes', () => {
  const { errors, status } = run(withAlerts);
  assert.deepEqual(errors, []);
  assert.equal(status, 0);
});
const bad = (mut) => (d) => {
  withAlerts(d);
  mut(d);
};
rejects('an event that names a commodity the atlas does not have', bad((d) => (d.events[0].commodities = ['unobtainium'])), '"unobtainium"');
rejects('an event that names an unknown country', bad((d) => (d.events[0].countries = ['ZZZ'])), '"ZZZ"');
rejects('an event that names an unknown asset', bad((d) => (d.events[0].assets = ['nowhere-port'])), '"nowhere-port"');
rejects('an event whose commodities are not a list', bad((d) => (d.events[0].commodities = 'lng')), 'not a list of ids');
rejects('an event with a date that is not a date', bad((d) => (d.events[0].date = 'March 2026')), 'is not YYYY-MM');
rejects('two events with one id', bad((d) => d.events.push({ ...d.events[0] })), 'appears twice');
rejects('an alert without a review date', bad((d) => delete d.alerts[0].reviewed), '"reviewed"');
rejects('an alert that points to no event', bad((d) => (d.alerts[0].event = 'ev9')), 'event "ev9"');
rejects('an alert with a severity outside the list', bad((d) => (d.alerts[0].severity = 'critical')), 'severity "critical"');
rejects('an alert without a PortWatch figure', bad((d) => (d.alerts[0].measures = [])), 'no PortWatch figure');
rejects('an alert figure without a date', bad((d) => delete d.alerts[0].measures[0].to), 'no date of last observation');
rejects('an alert figure that does not credit PortWatch', bad((d) => (d.alerts[0].measures[0].s = 'atlas')), 'must credit portwatch');
rejects('an alert on a derived commodity that does not exist', bad((d) => (d.alerts[0].commodities = ['lng', 'x-ore'])), '"x-ore"');
rejects('an alert override without a reason', bad((d) => (d.alerts[0].override = { commodities: ['lng'] })), 'override needs a reason');
rejects('an alert on a passage that does not exist', bad((d) => (d.alerts[0].chokepoints = ['atlantis'])), '"atlantis"');

// ---- generated corridor routes (routes.json) against the pairs table of base(): the pair AUS-CHN, 100 nm, panamax, ports A and B
const route = (extra = {}) => ({
  id: 'gen-coal-z-z', name: 'Coal: Z to Z', benchmark: false, generated: true, vclass: 'panamax', cargoes: ['thermal-coal'], s: 'atlas',
  notes: 'Atlas corridor, generated from customs pairs: 1 pair', corridor: [{ k: 'thermal-coal', g: 'coal', o: ['AUS'], d: ['CHN'] }],
  from: { region: 'Z', ports: ['A'] }, to: { region: 'Z', ports: ['B'] }, distanceNm: 100, via: ['malacca'], viaAlt: [['suez', 'panama']], ...extra,
});
const withRoutes = (mutate) => (d) => {
  d.routes = [route()];
  mutate?.(d);
};
test('a valid generated route passes', () => {
  const { errors, status } = run(withRoutes());
  assert.deepEqual(errors, []);
  assert.equal(status, 0);
});
rejects('a generated route that is a benchmark', withRoutes((d) => (d.routes[0].benchmark = true)), 'never a benchmark');
rejects('a generated route with another source', withRoutes((d) => (d.routes[0].s = 'baci')), 'source id "atlas"');
rejects('a generated route without the note', withRoutes((d) => (d.routes[0].notes = 'x')), 'generated from customs pairs');
rejects('a generated route whose id is not gen-', withRoutes((d) => (d.routes[0].id = 'coal-z')), 'starts with "gen-"');
rejects('a hand-written route with a gen- id', withRoutes((d) => d.routes.push({ id: 'gen-x', benchmark: false, via: [] })), 'is for a generated route');
rejects("a generated route with a distance that is not its pair's", withRoutes((d) => (d.routes[0].distanceNm = 90)), 'largest pair');
rejects("a generated route with a class that is not its pair's", withRoutes((d) => (d.routes[0].vclass = 'vlcc')), 'vessel class vlcc');
rejects('a generated route with other ports', withRoutes((d) => (d.routes[0].to.ports = ['C'])), 'ports are not those');
rejects('a corridor entry without a customs group', withRoutes((d) => delete d.routes[0].corridor[0].g), 'names its customs group');
rejects('a corridor entry with neither g nor gs', withRoutes((d) => d.routes.push({ id: 'hand', benchmark: false, via: [], corridor: [{ k: 'copper', o: ['AUS'], d: ['CHN'] }] })), 'neither a customs group');
test('a hand-written corridor entry with gs passes', () => {
  const { errors } = run(withRoutes((d) => d.routes.push({ id: 'hand', benchmark: false, via: [], corridor: [{ k: 'copper', gs: ['copper-ore'], o: ['AUS'], d: ['CHN'] }] })));
  assert.deepEqual(errors, []);
});
rejects("a generated route whose passages are not its pair's", withRoutes((d) => (d.routes[0].via = ['malacca', 'suez'])), 'every port option');
rejects("a generated route whose alternatives are not its pair's", withRoutes((d) => (d.routes[0].viaAlt = [])), 'may cross');
rejects('a pair in two generated corridors', withRoutes((d) => d.routes.push(route({ id: 'gen-coal-y-y' }))), 'is in the corridor of');
rejects('two routes with one id', withRoutes((d) => d.routes.push(route())), 'appears twice');
rejects('a route that names a passage that does not exist', withRoutes((d) => (d.routes[0].via = ['atlantis'])), '"atlantis"');

if (failed) {
  console.error(`\n${failed} test(s) failed`);
  process.exit(1);
}
console.log('\nall validate-freight tests passed');
