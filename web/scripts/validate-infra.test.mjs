/**
 * Tests of scripts/validate-infra.mjs: a small valid data folder passes, each way of breaking the schema is reported
 * as an error, and a file in the old shape gives warnings only behind the switch INFRA_OLD_SHAPE=1.
 *
 *     node web/scripts/validate-infra.test.mjs
 */
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateInfra, validateWpi } from './validate-infra.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const realData = path.resolve(here, '../../data');
const script = path.join(here, 'validate-infra.mjs');

const mine = () => ({
  id: 'cerro-test',
  name: 'Cerro test',
  type: 'mine',
  c: 'PER',
  k: ['copper'],
  operator: 'Test Co',
  opened: 2006,
  capacity: { v: 453.6, u: 'kt/y', y: 2024, n: 'copper in concentrate', orig: '1 billion lb Cu/y' },
  output: { v: 480, u: 'kt/y', y: 2025, what: 'production', n: 'FY2025' },
  status: 'operating',
  statusAsOf: '2026-11',
  s: 'wikipedia',
  url: 'https://en.wikipedia.org/wiki/Cerro_Verde_mine',
  read: '2026-11',
  coord: 'site',
  note: 'About 32 km SW of Arequipa.',
});
const feat = (p, coordinates = [-71.6, -16.5]) => ({ type: 'Feature', properties: p, geometry: { type: 'Point', coordinates } });

const FILE_OF = { field: 'fields', refinery: 'refineries', 'lng-export': 'lng', 'lng-import': 'lng', pipeline: 'pipelines', mine: 'mines', smelter: 'smelters', port: 'ports', storage: 'storage' };

/** A data folder with one valid mine and empty files for the other seven; each feature goes to the file of its type, unless `place` is false. */
function folder(mutate, place = true) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'infra-test-'));
  fs.mkdirSync(path.join(dir, 'infrastructure'), { recursive: true });
  for (const f of ['fields', 'refineries', 'lng', 'pipelines', 'smelters', 'ports', 'storage'])
    fs.writeFileSync(path.join(dir, 'infrastructure', `${f}.geojson`), JSON.stringify({ type: 'FeatureCollection', features: [] }));
  fs.mkdirSync(path.join(dir, 'commodities'));
  fs.writeFileSync(path.join(dir, 'commodities/index.json'), JSON.stringify([{ id: 'copper' }, { id: 'crude-oil' }]));
  fs.mkdirSync(path.join(dir, 'countries'));
  fs.writeFileSync(path.join(dir, 'countries/index.json'), JSON.stringify([{ c: 'PER' }, { c: 'CHL' }, { c: 'AUS' }, { c: 'IDN' }]));
  fs.writeFileSync(path.join(dir, 'sources.json'), JSON.stringify([{ id: 'wikipedia' }]));
  fs.mkdirSync(path.join(dir, 'freight'));
  fs.writeFileSync(path.join(dir, 'freight/vessel-classes.json'), JSON.stringify([{ id: 'capesize', segment: 'dry' }, { id: 'suezmax', segment: 'tanker' }]));
  fs.mkdirSync(path.join(dir, 'prices'));
  fs.writeFileSync(path.join(dir, 'prices/index.json'), JSON.stringify([{ id: 'wti-d' }]));
  fs.mkdirSync(path.join(dir, 'geo'));
  fs.copyFileSync(path.join(realData, 'geo/countries.topo.json'), path.join(dir, 'geo/countries.topo.json'));
  const features = [feat(mine())];
  mutate?.(features, dir);
  const files = {};
  for (const ft of features) (files[place ? (FILE_OF[ft.properties.type] ?? 'mines') : 'mines'] ??= []).push(ft);
  files.mines ??= [];
  for (const [name, list] of Object.entries(files)) fs.writeFileSync(path.join(dir, `infrastructure/${name}.geojson`), JSON.stringify({ type: 'FeatureCollection', features: list }));
  return dir;
}

// a PortWatch ports table of three rows (the name of one is quoted and holds a comma): port88 and port89 in Peru, port90 in Chile
const portTable = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'infra-table-')), 'portwatch_ports.csv');
fs.writeFileSync(portTable, 'portid,name,iso3,locode,lat,lon,pageid\nport88,Matarani,PER,PEMRI,-17.0,-72.1,a\nport89,"Callao, Lima",PER,PECLL,-12.0,-77.1,b\nport90,Antofagasta,CHL,CLANF,-23.6,-70.4,c\n');

async function run(mutate, tolerateOldShape = false, place = true, extra = {}) {
  const dir = folder(mutate, place);
  const errors = [];
  const warnings = [];
  await validateInfra(dir, errors, warnings, { tolerateOldShape, portwatchPorts: portTable, ...extra });
  fs.rmSync(dir, { recursive: true, force: true });
  return { errors, warnings, all: [...errors, ...warnings].join('\n') };
}

// a valid folder passes without a warning about the data
{
  const r = await run();
  assert.deepEqual(r.errors, []);
  assert.deepEqual(r.warnings, []);
}

// each break is reported as an error
const breaks = {
  'no status': [(p) => delete p.status, /status ""/],
  'status outside the vocabulary': [(p) => (p.status = 'running'), /status "running"/],
  'status without a date': [(p) => delete p.statusAsOf, /needs "statusAsOf"/],
  'bad statusAsOf': [(p) => (p.statusAsOf = 'March 2026'), /statusAsOf/],
  'bad read': [(p) => (p.read = '2026'), /"read" must be/],
  'feature-level y': [(p) => (p.y = 2026), /feature-level "y"/],
  'unit outside the vocabulary': [(p) => (p.capacity.u = 'Mt Cu'), /capacity\.u "Mt Cu"/],
  'output unit': [(p) => (p.output.u = 'tonnes'), /output\.u/],
  'output without a year': [(p) => delete p.output.y, /output\.y is required/],
  'output year as text': [(p) => (p.output.y = 'FY2025'), /output\.y is required/],
  'output.what': [(p) => (p.output.what = 'capacity'), /output\.what/],
  'capacity year as text': [(p) => (p.capacity.y = 'undated'), /capacity\.y/],
  'opened out of range': [(p) => (p.opened = 1700), /"opened"/],
  'unknown commodity': [(p) => (p.k = ['molybdenum']), /commodity "molybdenum"/],
  'empty commodities': [(p) => (p.k = []), /non-empty list/],
  'no url': [(p) => delete p.url, /"url"/],
  'bad coord': [(p) => (p.coord = 'town'), /coord "town"/],
  'working note': [(p) => (p.note = 'Output 290 Mt (via search summary).'), /working phrase/],
  'working note 2': [(p) => (p.note = 'figures were stripped'), /working phrase/],
  'unknown type': [(p) => (p.type = 'dam'), /type "dam"/],
  'zero capacity': [(p) => (p.capacity.v = 0), /capacity\.v/],
  'no coord': [(p) => delete p.coord, /coord ""/],
  'a mine in kb/d': [(p) => (p.capacity.u = 'kb/d'), /does not fit a mine/],
  'not-stated keeps its date': [(p) => (p.status = 'not-stated'), /remove "statusAsOf"/],
  'working phrase in statusNote': [(p) => (p.statusNote = 'Shut (via search summary)'), /statusNote holds a working phrase/],
  'working phrase in capacity.n': [(p) => (p.capacity.n = 'Platts roundup; the page could not be re-read'), /capacity\.n holds a working phrase/],
  'working phrase in output.n': [(p) => (p.output.n = 'figures were stripped'), /output\.n holds a working phrase/],
  'planned on an output': [(p) => (p.output.planned = true), /"planned" is only/],
  'planned that is not true': [(p) => (p.capacity.planned = 'yes'), /"planned" is only/],
};
for (const [name, [edit, re]] of Object.entries(breaks)) {
  const r = await run((fs) => edit(fs[0].properties));
  assert.ok(r.errors.some((e) => re.test(e)), `${name}: expected an error matching ${re}, got ${JSON.stringify(r.errors)}`);
}

// unknown source: always an error; a type and an id identify one asset
{
  const r = await run((fs) => (fs[0].properties.s = 'nobody'));
  assert.ok(r.errors.some((e) => /unknown source "nobody"/.test(e)));
}
{
  const r = await run((fs, dir) => {
    fs.push(feat({ ...mine(), name: 'Other' }, [-71.6, -16.6]));
  });
  assert.ok(r.errors.some((e) => /mine:cerro-test is also in/.test(e)), r.all);
}
{
  // the same id under another type is another asset ("ras-tanura", a refinery and a port)
  const r = await run((fs) => {
    fs.push(feat({ ...mine(), type: 'smelter' }));
  });
  assert.deepEqual(r.errors, [], r.all);
}
{
  // a feature must sit in the file of its type
  const r = await run((fs) => (fs[0].properties.type = 'port'), false, false);
  assert.ok(r.errors.some((e) => /belongs in ports\.geojson/.test(e)), r.all);
}
{
  // a planned capacity is accepted
  const r = await run((fs) => (fs[0].properties.capacity.planned = true));
  assert.deepEqual(r.errors, [], r.all);
}

// pipelines: `cs` is required and starts with the country `c`; a refinery is in kb/d and an LNG terminal in Mtpa
{
  const pipe = () => {
    const p = { ...mine(), id: 'pipe-test', type: 'pipeline', k: ['crude-oil'], cs: ['PER', 'CHL'], capacity: { v: 500, u: 'kb/d' }, product: 'crude', length_km: 800 };
    delete p.output;
    return p;
  };
  const line = [[-71.6, -16.5], [-70.5, -18.3]];
  const geo = (p) => ({ type: 'Feature', properties: p, geometry: { type: 'LineString', coordinates: line } });
  const ok = await run((fs) => (fs[0] = geo(pipe())));
  assert.deepEqual(ok.errors, [], ok.all);
  const noCs = await run((fs) => { const p = pipe(); delete p.cs; fs[0] = geo(p); });
  assert.ok(noCs.errors.some((e) => /needs "cs"/.test(e)), noCs.all);
  const wrongStart = await run((fs) => (fs[0] = geo({ ...pipe(), cs: ['CHL', 'PER'] })));
  assert.ok(wrongStart.errors.some((e) => /must start with the country "PER"/.test(e)), wrongStart.all);
  const refinery = await run((fs) => (fs[0] = feat({ ...mine(), id: 'ref-test', type: 'refinery', k: ['crude-oil'], capacity: { v: 300, u: 'Mt/y' }, output: undefined })));
  assert.ok(refinery.errors.some((e) => /does not fit a refinery/.test(e)), refinery.all);
  const lng = await run((fs) => (fs[0] = feat({ ...mine(), id: 'lng-test', type: 'lng-export', k: ['lng'], capacity: { v: 5, u: 'kb/d' }, output: undefined })));
  assert.ok(lng.errors.some((e) => /does not fit a lng-export/.test(e)), lng.all);
}

// coordinates
{
  const r = await run((fs) => (fs[0].geometry.coordinates = [-71.6, 116.5]));
  assert.ok(r.errors.some((e) => /not a number in range/.test(e)), r.all);
}
{
  const r = await run((fs) => (fs[0].geometry.coordinates = ['-71.6', '-16.5']));
  assert.ok(r.errors.some((e) => /not a number in range/.test(e)), r.all);
}
{
  // a point in Chile stated as Peru
  const r = await run((fs) => (fs[0].geometry.coordinates = [-69.0, -23.5]));
  assert.ok(r.errors.some((e) => /km from PER/.test(e)), r.all);
}
{
  // a point 30 km off the coast is accepted; one on the coast is too
  const r = await run((fs) => (fs[0].geometry.coordinates = [-71.5, -17.0]));
  assert.deepEqual(r.errors, []);
}

// assets at sea: an LNG plant or a field may lie far from its country's polygon, but not nearer to another country
{
  const lng = (c) => {
    const p = { ...mine(), id: 'prelude-test', type: 'lng-export', c, k: ['crude-oil'], capacity: { v: 3.6, u: 'Mtpa', y: 2025 } };
    delete p.output;
    return p;
  };
  const prelude = [123.3, -13.78];
  const ok = await run((fs) => (fs[0] = feat(lng('AUS'), prelude)));
  assert.deepEqual(ok.errors, [], ok.all);
  // the same point stated as Indonesian is 320 km from Indonesia and nearer to Australia
  const wrong = await run((fs) => (fs[0] = feat(lng('IDN'), prelude)));
  assert.ok(wrong.errors.some((e) => /nearer to AUS/.test(e)), wrong.all);
  // a plant at sea is not exempt from the 370 km limit, and a mine at sea is not exempt at all
  const far = await run((fs) => (fs[0] = feat(lng('AUS'), [95, -13.78])));
  assert.ok(far.errors.some((e) => /from AUS/.test(e)), far.all);
  const mineAtSea = await run((fs) => (fs[0] = feat({ ...mine(), c: 'AUS', k: ['copper'] }, prelude)));
  assert.ok(mineAtSea.errors.some((e) => /the limit is 60 km/.test(e)), mineAtSea.all);
}

// the old shape: errors; with the switch, warnings
{
  const old = (fs) => {
    const p = fs[0].properties;
    delete p.read;
    p.y = 2026;
    p.capacity = { v: 1.28, u: 'Mt Cu (2024)' };
    delete p.output;
    delete p.status;
    delete p.statusAsOf;
  };
  const strict = await run(old);
  assert.ok(strict.errors.length >= 4, strict.all);
  const soft = await run(old, true);
  assert.deepEqual(soft.errors, [], soft.all);
  assert.ok(soft.warnings.length >= 4, soft.all);
  assert.ok(soft.warnings.some((w) => /still in the old shape/.test(w)));
  // the hint about the switch is printed only when the switch is set
  assert.ok(!strict.all.includes('INFRA_OLD_SHAPE=1 is set'), strict.all);
}

// the command exits 1 on an error, 0 otherwise, and INFRA_OLD_SHAPE=1 is read from the environment
{
  const dir = folder((fs) => (fs[0].properties.status = 'running'));
  const bad = spawnSync(process.execPath, [script, dir], { encoding: 'utf8' });
  fs.rmSync(dir, { recursive: true, force: true });
  assert.equal(bad.status, 1);
  const dir2 = folder();
  const good = spawnSync(process.execPath, [script, dir2], { encoding: 'utf8' });
  assert.equal(good.status, 0, good.stderr);
  const dir3 = folder((fs) => {
    delete fs[0].properties.read;
    fs[0].properties.y = 2026;
  });
  const strict = spawnSync(process.execPath, [script, dir3], { encoding: 'utf8' });
  const soft = spawnSync(process.execPath, [script, dir3], { encoding: 'utf8', env: { ...process.env, INFRA_OLD_SHAPE: '1' } });
  for (const d of [dir2, dir3]) fs.rmSync(d, { recursive: true, force: true });
  assert.equal(strict.status, 1);
  assert.equal(soft.status, 0, soft.stderr);
}

// ports: trade-engine code, PortWatch id, limits, the class derived from them, prices; storage hubs in Mb
{
  const port = (extra = {}) => {
    const p = { ...mine(), id: 'port-test', name: 'Port test', type: 'port', k: ['iron-ore'], locode: 'PEMRI', portwatch: 'port88', ...extra };
    delete p.capacity;
    delete p.output;
    p.k = ['copper'];
    return p;
  };
  const lim = { draught: 18.2, dwt: 200000, depth: true, seg: 'dry', cls: 'capesize', at: 'Berth 1', n: 'Berth 1 at high tide', s: 'wikipedia', url: 'https://en.wikipedia.org/wiki/Port', y: 2025 };
  const one = { id: 'capesize', by: 'By deadweight', basis: 'The limit is in the band.' };
  const ok = await run((fs) => (fs[0] = feat(port({ limits: lim, maxClass: { dry: { classes: [{ id: 'capesize', by: 'By deadweight', basis: 'The limit is in the band.' }] }, n: 'Atlas estimate' }, prices: ['wti-d'] }), [-72.1, -17.0])));
  assert.deepEqual(ok.errors, [], ok.all);
  const cases = {
    'bad locode': [{ locode: 'RU PRI' }, /"locode" must be/],
    'bad portwatch id': [{ portwatch: '1020' }, /"portwatch" must be/],
    'portwatch id not in the table': [{ portwatch: 'port999' }, /port999 is not in the PortWatch ports table/],
    'portwatch id of another country': [{ portwatch: 'port90' }, /port90 is a port of CHL, the asset is in PER/],
    'limits without a figure': [{ limits: { n: 'x', s: 'wikipedia', url: lim.url } }, /limits give none/],
    'draught in feet': [{ limits: { ...lim, draught: 45 } }, /not in metres/],
    'limits without n': [{ limits: { ...lim, n: '' } }, /limits\.n must say/],
    'limits of an unknown source': [{ limits: { ...lim, s: 'nobody' } }, /limits\.s "nobody"/],
    'limits without a page': [{ limits: { ...lim, url: undefined } }, /limits\.url/],
    'limits with a stray field': [{ limits: { ...lim, tide: 'high' } }, /limits\.tide is not a field/],
    'limits of no segment': [{ limits: { ...lim, seg: 'bulk' } }, /limits\.seg "bulk" is not a segment/],
    'named class of another segment': [{ limits: { ...lim, seg: 'tanker', cls: 'capesize' } }, /not a class of the segment "tanker"/],
    'named class unknown': [{ limits: { ...lim, cls: 'megamax' } }, /limits\.cls "megamax"/],
    'depth without a draught': [{ limits: { dwt: 1e5, depth: true, n: 'x', s: 'wikipedia', url: lim.url } }, /limits\.depth must be true/],
    'class without limits': [{ maxClass: { dry: { classes: [one] }, n: 'x' } }, /derived from "limits"/],
    'class of no segment': [{ limits: lim, maxClass: { bulk: { classes: [one] }, n: 'x' } }, /maxClass\.bulk is not a segment/],
    'unknown class': [{ limits: lim, maxClass: { dry: { classes: [{ ...one, id: 'megamax' }] }, n: 'x' } }, /"megamax" is not a vessel class/],
    'class of another segment': [{ limits: lim, maxClass: { tanker: { classes: [one] }, n: 'x' } }, /not a class of that segment/],
    'segment without its classes': [{ limits: lim, maxClass: { dry: 'capesize', n: 'x' } }, /must hold one class, or two/],
    'three classes': [{ limits: lim, maxClass: { dry: { classes: [one, { ...one, id: 'vloc' }, { ...one, id: 'kamsarmax' }] }, n: 'x' } }, /must hold one class, or two/],
    'class without basis': [{ limits: lim, maxClass: { dry: { classes: [{ id: 'capesize', by: 'By deadweight' }] }, n: 'x' } }, /needs "by" and "basis"/],
    'or larger as a word': [{ limits: lim, maxClass: { dry: { classes: [{ ...one, orLarger: 'yes' }] }, n: 'x' } }, /orLarger can only be true/],
    'the same class twice': [{ limits: lim, maxClass: { dry: { classes: [one, one] }, n: 'x' } }, /same class twice/],
    'class without method': [{ limits: lim, maxClass: { dry: { classes: [one] } } }, /needs "n"/],
    'unknown price series': [{ prices: ['brent-x'] }, /price series "brent-x"/],
  };
  for (const [name, [extra, re]] of Object.entries(cases)) {
    const r = await run((fs) => (fs[0] = feat(port(extra), [-72.1, -17.0])));
    assert.ok(r.errors.some((e) => re.test(e)), `${name}: expected an error matching ${re}, got ${JSON.stringify(r.errors)}`);
  }
  // a PortWatch port serves one asset; a quoted name in the table does not shift its columns; no table, no check and a warning
  const twice = await run((fs) => {
    fs[0] = feat(port({ portwatch: 'port89' }), [-72.1, -17.0]);
    fs.push(feat(port({ id: 'port-two', name: 'Port two', portwatch: 'port89' }), [-72.2, -17.0]));
  });
  assert.equal(twice.errors.length, 1, twice.all);
  assert.match(twice.errors[0], /port-two: "portwatch" port89 is also the id of port-test/);
  const noTable = await run((fs) => (fs[0] = feat(port({ portwatch: 'port999' }), [-72.1, -17.0])), false, true, { portwatchPorts: path.join(os.tmpdir(), 'no-such-table.csv') });
  assert.deepEqual(noTable.errors, [], noTable.all);
  assert.ok(noTable.warnings.some((w) => /PortWatch ports table .* not available/.test(w)), noTable.all);
  // limits belong to a port
  const onMine = await run((fs) => (fs[0].properties.limits = lim));
  assert.ok(onMine.errors.some((e) => /"limits" belong to a port/.test(e)), onMine.all);
  // a storage hub sits in storage.geojson and gives its capacity in Mb; a mine cannot
  const hub = { ...mine(), id: 'hub-test', type: 'storage', k: ['crude-oil'], capacity: { v: 78.4, u: 'Mb', y: 2024 } };
  delete hub.output;
  const st = await run((fs) => (fs[0] = feat(hub)));
  assert.deepEqual(st.errors, [], st.all);
  const misplaced = await run((fs) => (fs[0] = feat(hub)), false, false);
  assert.ok(misplaced.errors.some((e) => /belongs in storage\.geojson/.test(e)), misplaced.all);
  const mb = await run((fs) => (fs[0].properties.capacity.u = 'Mb'));
  assert.ok(mb.errors.some((e) => /does not fit a mine/.test(e)), mb.all);
  // an island oil terminal may stand offshore, like an LNG terminal
  const offshore = await run((fs) => (fs[0] = feat(port(), [-73.2, -17.8])));
  assert.deepEqual(offshore.errors, [], offshore.all);
}

// infrastructure/wpi.json: a good file passes; each rule has a case; an entry must be a port of ports.geojson
{
  const good = () => ({
    s: 'nga-wpi',
    read: '2026-11',
    captured: '2026-09-29',
    edition: null,
    ports: {
      'port-one': { n: 100, name: 'Port One', lc: 'AAONE', by: 'code', km: 1.2, size: 'Medium', type: 'River (Natural)', tide: 3, chan: 14, anch: 4.9, loa: 340, beam: 60, draft: 11.8, pilot: 'Yes', tideRes: 'No' },
      'port-two': { n: 200, name: 'Port Two', by: 'review', km: 6, why: 'a sentence', oil: 23.2 },
    },
  });
  const wpiRun = (mutate, { file = true, ports = ['port-one', 'port-two'], registry = ['nga-wpi'] } = {}) => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wpi-test-'));
    fs.mkdirSync(path.join(dir, 'infrastructure'));
    const features = ports.map((id) => feat({ id, name: id, type: 'port' }));
    features.push(feat({ id: 'mine-one', name: 'mine-one', type: 'mine' }));
    fs.writeFileSync(path.join(dir, 'infrastructure/ports.geojson'), JSON.stringify({ type: 'FeatureCollection', features }));
    fs.writeFileSync(path.join(dir, 'sources.json'), JSON.stringify(registry.map((id) => ({ id }))));
    const doc = good();
    const text = mutate?.(doc);
    if (file) fs.writeFileSync(path.join(dir, 'infrastructure/wpi.json'), text?.raw !== undefined ? text.raw : JSON.stringify(doc));
    const errors = [];
    const warnings = [];
    validateWpi(dir, errors, warnings);
    fs.rmSync(dir, { recursive: true, force: true });
    return { errors, warnings, all: [...errors, ...warnings].join('\n') };
  };
  const ok = wpiRun();
  assert.deepEqual(ok.errors, [], ok.all);
  assert.deepEqual(ok.warnings, []);
  const one = (d) => d.ports['port-one'];
  const wpiBreaks = {
    'not JSON': [() => ({ raw: '{"s":' }), /invalid JSON/],
    'not an object': [() => ({ raw: '[]' }), /not an object/],
    'unknown top-level key': [(d) => (d.y = 2026), /unknown key "y"/],
    'source is another id': [(d) => (d.s = 'wikipedia'), /"s" must be "nga-wpi"/],
    'no month': [(d) => (d.read = '2026'), /"read" must be a month/],
    'a month out of range': [(d) => (d.read = '2026-13'), /"read" must be a month/],
    'a capture that is not a day': [(d) => (d.captured = '2026-09'), /"captured" must be a day/],
    'a capture day out of range': [(d) => (d.captured = '2026-02-32'), /"captured" must be a day/],
    'empty edition': [(d) => (d.edition = ' '), /"edition"/],
    'ports is a list': [(d) => (d.ports = []), /"ports" must be an object/],
    'no entry': [(d) => (d.ports = {}), /"ports" is empty/],
    'an id that is not a port id': [(d) => (d.ports['Port One'] = d.ports['port-two']), /not a port id/],
    'a feature that is not a port': [(d) => (d.ports['mine-one'] = d.ports['port-two']), /ports\.mine-one: not a port of ports\.geojson/],
    'an id that is not in ports.geojson': [(d) => (d.ports['port-three'] = d.ports['port-two']), /ports\.port-three: not a port of ports\.geojson/],
    'an entry that is not an object': [(d) => (d.ports['port-two'] = 5), /not an object/],
    'a key s on an entry': [(d) => (one(d).s = 'nga-wpi'), /unknown key "s"/],
    'a key y on an entry': [(d) => (one(d).y = 2026), /unknown key "y"/],
    'a key v on an entry': [(d) => (one(d).v = 14), /unknown key "v"/],
    'a key of a column that is not read': [(d) => (one(d).facilities = 'Yes'), /unknown key "facilities"/],
    'no entry number': [(d) => delete one(d).n, /"n" must be/],
    'an entry number that is not an integer': [(d) => (one(d).n = 100.5), /"n" must be/],
    'a number as text': [(d) => (one(d).n = '100'), /"n" must be/],
    'no name': [(d) => delete one(d).name, /"name"/],
    'a name with a double space': [(d) => (one(d).name = 'Port  One'), /"name"/],
    'a code of the wrong shape': [(d) => (one(d).lc = 'AA ONE'), /"lc"/],
    'a match that is none of the three': [(d) => (one(d).by = 'position'), /"by" must be/],
    'no distance': [(d) => delete one(d).km, /"km"/],
    'a negative distance': [(d) => (one(d).km = -1), /"km"/],
    'a reason on a match by code': [(d) => (one(d).why = 'a sentence'), /"why" is given if and only if/],
    'a review without a reason': [(d) => delete d.ports['port-two'].why, /"why" is given if and only if/],
    'an empty reason': [(d) => (d.ports['port-two'].why = ' '), /"why" must be a text/],
    'a size outside the classes': [(d) => (one(d).size = 'Huge'), /"size" must be/],
    'an empty type': [(d) => (one(d).type = ''), /"type" must be a text/],
    'pilotage as Unknown': [(d) => (one(d).pilot = 'Unknown'), /"pilot" must be Yes or No/],
    'a tide flag as true': [(d) => (one(d).tideRes = true), /"tideRes" must be Yes or No/],
    'a zero depth': [(d) => (one(d).chan = 0), /"chan" must be a positive number/],
    'a negative figure': [(d) => (one(d).draft = -11.8), /"draft" must be a positive number/],
    'a null figure': [(d) => (one(d).anch = null), /"anch" must be a positive number/],
    'a figure as text': [(d) => (one(d).loa = '340'), /"loa" must be a positive number/],
    'a figure above 1,000': [(d) => (one(d).oil = 1200), /"oil" must be a positive number of at most 1000/],
    'a tidal range alone': [(d) => ((d.ports['port-two'] = { n: 200, name: 'Port Two', by: 'code', km: 1, tide: 3 }), 0), /no depth and no maximum vessel figure/],
  };
  for (const [name, [mutate, re]] of Object.entries(wpiBreaks)) {
    const r = wpiRun(mutate);
    assert.ok(r.errors.some((e) => re.test(e)), `wpi ${name}: expected an error matching ${re}, got ${JSON.stringify(r.errors)}`);
  }
  // the source must be in the registry; a missing file is a warning, never an error; nothing is stored for a port that has no entry
  const noRegistry = wpiRun(null, { registry: ['wikipedia'] });
  assert.ok(noRegistry.errors.some((e) => /"s" nga-wpi is not in sources\.json/.test(e)), noRegistry.all);
  const missing = wpiRun(null, { file: false });
  assert.deepEqual(missing.errors, []);
  assert.ok(missing.warnings.some((w) => /wpi\.json: the file is not there/.test(w)), missing.all);
  const fewer = wpiRun(null, { ports: ['port-one'] });
  assert.ok(fewer.errors.some((e) => /ports\.port-two: not a port of ports\.geojson/.test(e)), fewer.all);
  // the real file passes against the real data folder
  const real = [];
  validateWpi(realData, real, []);
  assert.deepEqual(real, []);
}

console.log('validate-infra tests passed');
