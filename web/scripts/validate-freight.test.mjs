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
  if (d.classes) put('freight/vessel-classes.json', d.classes);
  if (d.sources) put('sources.json', d.sources);
  if (d.events) put('freight/events.json', d.events);
  if (d.alerts) put('freight/alerts.json', d.alerts);
  if (d.commodities) put('commodities/index.json', d.commodities);
  if (d.prices) put('prices/index.json', d.prices);
  if (d.market) put('freight/market-now.json', d.market);
  if (d.weekly) put('freight/portwatch/suez.json', d.weekly);
  if (d.laneRows) {
    put('freight/chokepoint-lanes.json', { s: 'atlas', y: 2024, unit: 'Mt', groups: {}, chokepoints: d.laneRows });
    for (const c of d.chokepoints) if (!d.noSplit?.includes(c.id)) put(`freight/chokepoint-lanes/${c.id}.json`, { s: 'atlas', y: 2024, unit: 'Mt', groups: {}, chokepoints: { [c.id]: d.splitRows?.[c.id] ?? d.laneRows[c.id] ?? [] } });
  }
  if (d.assets) put('infrastructure/ports.geojson', { type: 'FeatureCollection', features: d.assets.map((id) => ({ properties: { id } })) });
}

/** A valid events and alerts layer on top of base(). */
const withAlerts = (d) => {
  d.commodities = [{ id: 'thermal-coal' }, { id: 'lng' }];
  d.assets = ['fujairah'];
  d.prices = [{ id: 'lng-m', k: 'lng' }, { id: 'coal-m', k: 'thermal-coal' }];
  d.events = [{ id: 'ev1', date: '2026-02-28', title: 't', kind: 'conflict', chokepoints: ['suez'], commodities: ['lng'], countries: ['AUS'], assets: ['fujairah'], summary: 's', src: 'https://example.org' }];
  d.alerts = [{
    id: 'a1', title: 'T', since: '2026-02', severity: 'high', severityNote: 'n', text: 'x', checked: '2026-11-23', event: 'ev1', src: 'https://example.org',
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
rejects('bits of f above 5', (d) => (d.pairs.rows[0][10] = 64), 'f = 64');
// ---- rows added from the importer's own declaration (bit 4 of f) and the overland part of a pair cut by mode
test('a row added from a declaration, with its source, and a rest list pass', () => {
  const { errors } = run((d) => {
    d.pairs.rows[1][10] = 16;
    d.pairs.added = { 'MNG-CHN': 'comtrade' };
    d.pairs.rest = [['AUS', 'CHN', 300]];
  });
  assert.deepEqual(errors, []);
});
rejects('a row flagged as added with no source', (d) => (d.pairs.rows[1][10] = 16), 'has no source in added');
rejects('an added source for a row that is not flagged', (d) => (d.pairs.added = { 'MNG-CHN': 'comtrade' }), 'no flagged row for that pair');
rejects('a rest entry for a pair with no row', (d) => (d.pairs.rest = [['AUS', 'MNG', 3]]), 'rest entry');
// ---- the note of a ship type, written once on the passage (GV6D.1)
const withTypeNote = (extra = {}) => (d) => {
  d.chokepoints[0].estimates = [{ k: 'coal', p: 'coal', f: { v: 1, u: '%', y: 2024, s: 'atlas', n: 'at least 1 Mt of 2 Mt of seaborne coal' }, mt: [1, 1] }];
  d.chokepoints[0].typeNotes = { dry: { name: 'dry bulk', y: 2024, low: 2, ref: 1, best: 3, bestY: 2023, cmp: 'above', regime: 'whole', capped: 0, groups: 1, line: 'Dry bulk: a line', n: 'The reason', ...extra } };
};
test('a note of a ship type on the passage passes', () => {
  const { errors } = run(withTypeNote());
  assert.deepEqual(errors, []);
});
rejects('a note of an unknown ship type', (d) => { withTypeNote()(d); d.chokepoints[0].typeNotes.ship = d.chokepoints[0].typeNotes.dry; }, 'not a ship type');
rejects('a note of a ship type without its line', withTypeNote({ line: '' }), 'no line');
rejects('a note of a ship type with an unknown regime', withTypeNote({ regime: 'half' }), 'regime "half"');
rejects('a note of a ship type repeated in an estimate', (d) => { withTypeNote()(d); d.chokepoints[0].estimates[0].f.n += ". The 'at least' tonnage is above IMF PortWatch's estimate for all dry bulk ships"; }, 'repeated in the estimate');
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
rejects('a portRule on a lane whose ports are not an open choice', (d) => ((d.lane.lanes[0].portBasis = 'single'), (d.lane.lanes[0].portRule = true)), 'portRule');
rejects('a portRule that is not true', (d) => (d.lane.lanes[0].portRule = false), 'portRule');
test('a portRule on an open lane is valid', () => {
  const { errors } = run((d) => (d.lane.lanes[0].portRule = true));
  assert.deepEqual(errors, []);
});
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
// ---- the river leg of a port up a river (package FNCE) and the basis "page names the plant, not the cargo"
const RIVER = { river: 'Seine', mouth: 'Honfleur', km: 120, nm: 65, s: 'wikipedia', url: 'https://fr.wikipedia.org/wiki/Port_de_Rouen', n: 'Rouen is up the Seine: the distance includes about 65 nm of the Seine, and the line is drawn as one straight segment.' };
test('a lane port with its river leg and a pairs file with its rivers pass', () => {
  const { errors } = run((d) => ((d.lane.ports.AAAAA.river = RIVER), (d.pairs.rivers = { AAAAA: RIVER })));
  assert.deepEqual(errors, []);
});
rejects('a river leg without its length in nm', (d) => (d.lane.ports.AAAAA.river = { ...RIVER, nm: 0 }), 'river needs river, mouth, km, nm');
rejects('a river leg whose note does not say the line is straight', (d) => (d.lane.ports.AAAAA.river = { ...RIVER, n: 'about 65 nm of the Seine' }), 'drawn straight');
rejects('a river leg of a pairs file for a port that is not in it', (d) => (d.pairs.rivers = { ZZZZZ: RIVER }), 'rivers.ZZZZZ: not a port of the file');
test('the basis "page names the plant, not the cargo" is one of the port bases', () => {
  const { errors } = run((d) => ((d.pairs.bases = ['page names the plant, not the cargo']), (d.pairs.ports[0][4] = 0), (d.lane.ports.AAAAA.basis = 'page names the plant, not the cargo')));
  assert.deepEqual(errors, []);
});
rejects('a second transit port without a source', (d) => ((d.lane.lanes[0].transit = { port: 'AAAAA', c: 'AUS', s: 'wikipedia' }), (d.lane.lanes[0].transit2 = { port: 'BBBBB', c: 'CHN' })), 'second transit port has no source');
rejects('a lane file without its pairs file', (d) => (d.pairsFile = 'other'), 'no pairs file');

test('a valid events and alerts layer passes', () => {
  const { errors, status } = run(withAlerts);
  assert.deepEqual(errors, []);
  assert.equal(status, 0);
});
test('an alert that points to a list of events passes', () => {
  const { errors, status } = run((d) => {
    withAlerts(d);
    d.events.push({ ...d.events[0], id: 'ev2' });
    d.alerts[0].events = ['ev1', 'ev2'];
  });
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
rejects('an alert with a check date that is not a date', bad((d) => (d.alerts[0].checked = 'yesterday')), '"checked"');
rejects('an alert that still carries the old "reviewed" date', bad((d) => (d.alerts[0].reviewed = '2026-11-23')), '"reviewed"');
rejects('an alert that adds a country the atlas does not have', bad((d) => (d.alerts[0].override = { addCountries: ['ZZZ'], reason: 'r' })), '"ZZZ"');
rejects('an event that reads a price series of another commodity', bad((d) => (d.events[0].series = { lng: 'coal-m' })), 'is not a price series of "lng"');
rejects('an event that reads a price series that does not exist', bad((d) => (d.events[0].series = { lng: 'nope-m' })), 'is not a price series of "lng"');
rejects('an event with a check date that is not a date', bad((d) => (d.events[0].checked = 'today')), '"checked"');
rejects('an event whose other sources are not links', bad((d) => (d.events[0].also = [{ label: 'x', url: 'ftp://x' }])), '"also"');
rejects('an alert that points to no event', bad((d) => (d.alerts[0].event = 'ev9')), 'event "ev9"');
rejects('an alert whose list of events names an event that does not exist', bad((d) => (d.alerts[0].events = ['ev1', 'ev9'])), 'events names "ev9"');
rejects('an alert whose list of events does not start with its main event', bad((d) => (d.alerts[0].events = ['ev9', 'ev1'])), '"event" must be the first');
rejects('an alert whose list of events names one event twice', bad((d) => (d.alerts[0].events = ['ev1', 'ev1'])), 'lists an event twice');
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
rejects('a generated route with a river leg that has no port', withRoutes((d) => (d.routes[0].rivers = [RIVER])), 'rivers entry');
test('a generated route with its river leg passes', () => {
  const { errors } = run(withRoutes((d) => (d.routes[0].rivers = [{ ...RIVER, port: 'Rouen' }])));
  assert.deepEqual(errors, []);
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
rejects('a route whose shareOn is not a generated route', withRoutes((d) => d.routes.push({ id: 'hand', benchmark: false, via: [], shareNa: 'x', shareOn: 'hand' })), 'shareOn "hand"');
test('a route whose shareOn is a generated route passes', () => {
  const { errors } = run(withRoutes((d) => d.routes.push({ id: 'hand', benchmark: false, via: [], shareNa: 'x', shareOn: 'gen-coal-z-z' })));
  assert.deepEqual(errors, []);
});
// ---- a benchmark's definition
const bench = (dx = {}, extra = {}) => ({
  id: 'TD1X', benchmark: true, via: [], ...extra,
  definition: { code: 'TD1X', cargo: '70,000 t (cargo not named in the definition)', state: 'active', stateNote: 'listed', stateUrl: 'https://x.org/a', doc: 'Guide (December 2025)', url: 'https://x.org/b', read: 'November 2026', y: 2025, ...dx },
});
test('a benchmark whose unnamed cargo is read in cargoNote passes', () => {
  const { errors } = run(withRoutes((d) => d.routes.push(bench({}, { cargoNote: "crude oil is the atlas's reading" }))));
  assert.deepEqual(errors, []);
});
rejects('a benchmark whose unnamed cargo has no reading in cargoNote', withRoutes((d) => d.routes.push(bench())), 'cargoNote does not give');
rejects('a definition without the year of its document', withRoutes((d) => d.routes.push(bench({ y: undefined }, { cargoNote: "atlas's reading" }))), 'no year of its document');
// ---- the standard vessels of the classes (the voyage calculator reads them)
const STD = () => ({ speed: { laden: 14, ballast: 14 }, cons: { laden: 52, ballast: 44 }, n: 'x', s: 'baltic', y: 2026 });
const withClasses = (mutate) => (d) => {
  d.sources = [{ id: 'baltic' }, { id: 'atlas' }];
  d.classes = [{ id: 'big', std: STD() }, { id: 'bigger', bench: { id: 'big', n: 'Benchmarks: the big routes' } }, { id: 'odd', std: { dwt: 400000, s: 'atlas', y: 2026, n: 'x' } }];
  mutate?.(d);
};
test('vessel classes with a standard vessel, a bench and a std of dimensions only pass', () => {
  const { errors, status } = run(withClasses());
  assert.deepEqual(errors, []);
  assert.equal(status, 0);
});
rejects('a standard vessel with a missing ballast speed', withClasses((d) => delete d.classes[0].std.speed.ballast), 'class big: std.speed needs a laden and a ballast figure');
rejects('a standard vessel with a zero fuel figure', withClasses((d) => (d.classes[0].std.cons.laden = 0)), 'class big: std.cons needs');
rejects('a standard vessel with a fuel figure that is not a number', withClasses((d) => (d.classes[0].std.cons.ballast = '44')), 'class big: std.cons needs');
rejects('a standard vessel with speed and no fuel', withClasses((d) => delete d.classes[0].std.cons), 'std gives speed but no fuel');
rejects('a standard vessel with fuel and no speed', withClasses((d) => delete d.classes[0].std.speed), 'std gives fuel but no speed');
rejects('a standard vessel whose source is not in sources.json', withClasses((d) => (d.classes[0].std.s = 'nobody')), 'std.s "nobody"');
rejects('a standard vessel with no year', withClasses((d) => (d.classes[0].std.y = '2026')), 'std has no year');
rejects('a bench that names a class that does not exist', withClasses((d) => (d.classes[1].bench.id = 'nowhere')), 'bench names "nowhere"');
rejects('a bench that names a class with no standard vessel', withClasses((d) => (d.classes[1].bench.id = 'odd')), 'bench names odd');
rejects('a bench whose class lost the legs of its standard vessel', withClasses((d) => delete d.classes[0].std.cons.laden), 'bench names big');

// ---- the digest of the freight market page: its shape only, never stricter than the builder (a rule here discards the whole weekly update)
// the example is the builder's own file (a digest of the real weekly files): its passages are not those of chokepoints.json of base(),
// so the digest is checked on its own
const publishedDigest = path.join(path.dirname(script), '../../data/freight/market-now.json');
const market = () => JSON.parse(fs.readFileSync(publishedDigest, 'utf8'));
const marketRow = (id, rank) => ({ ...market().types.tanker[0], id, rankMt: rank });
const withMarket = (mutate) => (d) => {
  d.sources = [{ id: 'portwatch' }, { id: 'atlas' }];
  d.market = market();
  mutate?.(d.market, d);
};
test('a valid digest passes, whatever the chokepoint file holds', () => {
  const { errors, status } = run(withMarket());
  assert.deepEqual(errors, []);
  assert.equal(status, 0);
});
test('a folder with no digest passes: the file is checked only when it exists', () => {
  assert.deepEqual(run().errors, []);
});
test('a tie in the ranking figure is accepted: the figures are rounded to three significant figures', () => {
  const { errors, status } = run(withMarket((m) => {
    m.types.tanker[1].rankMt = m.types.tanker[0].rankMt;
    m.types.tanker[4].rankMt = m.types.tanker[3].rankMt;
  }));
  assert.deepEqual(errors, []);
  assert.equal(status, 0);
});
test('a digest older than the weekly files is accepted: the weekly job keeps it when the builder refuses the new files', () => {
  const { errors, status } = run(withMarket((m, d) => {
    m.to = '2026-11-15';
    m.yearAgoTo = '2025-11-16';
    d.weekly = { id: 'suez', start: '2018-12-31', y: '2026-11-22', tanker: [], dry: [], vol: { tanker: [], dry: [] } }; // a file that ends a week after the digest, and is not even whole
  }));
  assert.deepEqual(errors, []);
  assert.equal(status, 0);
});
test('a passage that chokepoints.json does not hold is accepted: the page says so, the week\'s data is not discarded', () => {
  const { errors, status } = run(withMarket((m) => {
    m.types.tanker[0].id = 'renamed-last-month';
  }));
  assert.deepEqual(errors, []);
  assert.equal(status, 0);
});
test('a passage in both lists, a figure of 0 and a whole-tonne cargo are accepted', () => {
  const { errors } = run(withMarket((m) => {
    m.types.tanker[0].mt = { now: 0, ago: m.types.tanker[0].mt.ago, pct: -100 };
    m.types.tanker[0].now = 0;
    m.types.tanker[0].pct = -100;
    m.types.dry[0].pct = null; // nothing a year earlier: no change
    m.types.dry[0].mt.pct = null;
  }));
  assert.deepEqual(errors, []);
});
const market_rejects = (name, mutate, expected) => rejects(name, withMarket(mutate), expected);
market_rejects('a digest whose source is not in the registry', (m) => (m.s = 'nobody'), 's "nobody" is not a source id');
market_rejects('a date that is not ISO', (m) => (m.to = '22 Nov 2026'), 'to "22 Nov 2026" is not a date');
market_rejects('a date that does not exist', (m) => (m.yearAgoTo = '2025-02-30'), 'yearAgoTo "2025-02-30" is not a date');
market_rejects('two dates 363 days apart', (m) => (m.yearAgoTo = '2025-11-24'), 'are not 364 days apart');
market_rejects('a window of three weeks', (m) => (m.weeks = 3), 'weeks, days and rankWeeks must be 4, 28 and 52');
market_rejects('a window of 27 days', (m) => (m.days = 27), 'weeks, days and rankWeeks must be 4, 28 and 52');
market_rejects('a unit that is not a text', (m) => (m.unit = 28), 'unit must be a text');
market_rejects('an unknown key', (m) => (m.generated = '2026-11-25'), 'exactly the keys');
market_rejects('a missing key', (m) => delete m.mtUnit, 'exactly the keys');
market_rejects('a name in a row (the atlas names are read from chokepoints.json by the page)', (m) => (m.types.dry[0].name = 'Bohai Strait'), 'types.dry[0] must have exactly the keys');
market_rejects('a gas list', (m) => (m.types.gas = []), 'types must have exactly the ship types tanker and dry');
market_rejects('a list of four passages', (m) => m.types.tanker.pop(), 'types.tanker must be a list of 5 rows');
market_rejects('a list of six passages', (m) => m.types.dry.push(marketRow('p10', 1)), 'types.dry must be a list of 5 rows');
market_rejects('a passage twice in a list', (m) => (m.types.tanker[3].id = m.types.tanker[0].id), `passage ${market().types.tanker[0].id} appears twice`);
market_rejects('a row without an id', (m) => (m.types.tanker[2].id = ''), 'types.tanker[2]: no id');
market_rejects('a negative count', (m) => (m.types.tanker[0].now = -1), 'types.tanker[0].now: -1 is not a finite number');
market_rejects('a count that is a text', (m) => (m.types.tanker[0].ago = String(m.types.tanker[0].ago)), `types.tanker[0].ago: "${market().types.tanker[0].ago}"`);
market_rejects('a cargo that is not a number (null: NaN in a JSON file)', (m) => (m.types.dry[1].mt.now = null), 'types.dry[1].mt.now: null');
market_rejects('a negative cargo a year back', (m) => (m.types.dry[1].mt.ago = -0.5), 'types.dry[1].mt.ago: -0.5');
market_rejects('a cargo block with a fourth key', (m) => (m.types.dry[1].mt.avg = 3), 'types.dry[1].mt must have exactly now, ago and pct');
market_rejects('a cargo block without its change', (m) => delete m.types.dry[1].mt.pct, 'types.dry[1].mt must have exactly now, ago and pct');
market_rejects('a row without its change', (m) => delete m.types.tanker[1].pct, 'types.tanker[1] must have exactly the keys');
market_rejects('a change of the transits that is a text', (m) => (m.types.tanker[1].pct = '-9.9'), 'types.tanker[1].pct: "-9.9" is not a finite number or null');
market_rejects('a change of the cargo that is a boolean', (m) => (m.types.dry[2].mt.pct = true), 'types.dry[2].mt.pct: true is not a finite number or null');
market_rejects('a ranking figure that is missing', (m) => (m.types.tanker[4].rankMt = null), 'types.tanker[4].rankMt: null');
market_rejects('a ranking figure that increases down the list', (m) => (m.types.tanker[2].rankMt = m.types.tanker[1].rankMt + 1), `rankMt ${market().types.tanker[1].rankMt + 1} is larger than the one above it`);
market_rejects('a digest that is not an object', (m, d) => (d.market = [1, 2]), 'must be an object with exactly the keys');
test('a digest file that is not JSON is reported', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'freight-validate-'));
  try {
    const d = base();
    write(root, d);
    fs.writeFileSync(path.join(root, 'freight/market-now.json'), '{"s":');
    const errors = [];
    validateFreight(root, errors);
    assert.ok(errors.some((e) => e.includes('freight/market-now.json: unreadable')), JSON.stringify(errors));
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

// ---- the split lane files of the chokepoint pages: one for every passage of the catalogue
const withLaneRows = (d) => (d.laneRows = { suez: [['coal', 'AUS', 'CHN', 1.2, 1]] });
test('a split file for every passage, empty where no lane crosses it, passes', () => {
  const { errors } = run(withLaneRows);
  assert.deepEqual(errors, []);
});
rejects('a passage of the catalogue without its split file', (d) => { withLaneRows(d); d.noSplit = ['panama']; }, 'chokepoint-lanes/panama.json: missing');
rejects('a passage with lanes and without its split file', (d) => { withLaneRows(d); d.noSplit = ['suez']; }, 'chokepoint-lanes/suez.json: missing');
rejects('a split file that does not hold the rows of the table', (d) => { withLaneRows(d); d.splitRows = { suez: [] }; }, 'chokepoint-lanes/suez.json: does not hold the rows');
rejects('a split file that holds rows the table does not', (d) => { withLaneRows(d); d.splitRows = { malacca: [['coal', 'AUS', 'CHN', 1.2, 1]] }; }, 'chokepoint-lanes/malacca.json: does not hold the rows');
test('a folder with no table of lanes is not checked for split files', () => {
  const { errors } = run();
  assert.deepEqual(errors, []);
});

if (failed) {
  console.error(`\n${failed} test(s) failed`);
  process.exit(1);
}
console.log('\nall validate-freight tests passed');
