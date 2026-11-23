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
import { validateInfra } from './validate-infra.mjs';

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

const FILE_OF = { field: 'fields', refinery: 'refineries', 'lng-export': 'lng', 'lng-import': 'lng', pipeline: 'pipelines', mine: 'mines', smelter: 'smelters', port: 'ports' };

/** A data folder with one valid mine and empty files for the other six; each feature goes to the file of its type, unless `place` is false. */
function folder(mutate, place = true) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'infra-test-'));
  fs.mkdirSync(path.join(dir, 'infrastructure'), { recursive: true });
  for (const f of ['fields', 'refineries', 'lng', 'pipelines', 'smelters', 'ports'])
    fs.writeFileSync(path.join(dir, 'infrastructure', `${f}.geojson`), JSON.stringify({ type: 'FeatureCollection', features: [] }));
  fs.mkdirSync(path.join(dir, 'commodities'));
  fs.writeFileSync(path.join(dir, 'commodities/index.json'), JSON.stringify([{ id: 'copper' }, { id: 'crude-oil' }]));
  fs.mkdirSync(path.join(dir, 'countries'));
  fs.writeFileSync(path.join(dir, 'countries/index.json'), JSON.stringify([{ c: 'PER' }, { c: 'CHL' }, { c: 'AUS' }, { c: 'IDN' }]));
  fs.writeFileSync(path.join(dir, 'sources.json'), JSON.stringify([{ id: 'wikipedia' }]));
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

async function run(mutate, tolerateOldShape = false, place = true) {
  const dir = folder(mutate, place);
  const errors = [];
  const warnings = [];
  await validateInfra(dir, errors, warnings, { tolerateOldShape });
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

console.log('validate-infra tests passed');
