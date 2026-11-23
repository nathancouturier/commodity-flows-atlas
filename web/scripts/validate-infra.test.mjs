/**
 * Tests of scripts/validate-infra.mjs: a small valid data folder passes, each way of breaking the schema is reported,
 * a file in the old shape gives warnings (and errors with STRICT_INFRA=1).
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

/** A data folder with one valid mine and empty files for the other six. */
function folder(mutate) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'infra-test-'));
  fs.mkdirSync(path.join(dir, 'infrastructure'), { recursive: true });
  for (const f of ['fields', 'refineries', 'lng', 'pipelines', 'smelters', 'ports'])
    fs.writeFileSync(path.join(dir, 'infrastructure', `${f}.geojson`), JSON.stringify({ type: 'FeatureCollection', features: [] }));
  fs.mkdirSync(path.join(dir, 'commodities'));
  fs.writeFileSync(path.join(dir, 'commodities/index.json'), JSON.stringify([{ id: 'copper' }, { id: 'crude-oil' }]));
  fs.mkdirSync(path.join(dir, 'countries'));
  fs.writeFileSync(path.join(dir, 'countries/index.json'), JSON.stringify([{ c: 'PER' }, { c: 'CHL' }]));
  fs.writeFileSync(path.join(dir, 'sources.json'), JSON.stringify([{ id: 'wikipedia' }]));
  fs.mkdirSync(path.join(dir, 'geo'));
  fs.copyFileSync(path.join(realData, 'geo/countries.topo.json'), path.join(dir, 'geo/countries.topo.json'));
  const features = [feat(mine())];
  mutate?.(features, dir);
  fs.writeFileSync(path.join(dir, 'infrastructure/mines.geojson'), JSON.stringify({ type: 'FeatureCollection', features }));
  return dir;
}

async function run(mutate, strict = false) {
  const dir = folder(mutate);
  const errors = [];
  const warnings = [];
  await validateInfra(dir, errors, warnings, { strict });
  fs.rmSync(dir, { recursive: true, force: true });
  return { errors, warnings, all: [...errors, ...warnings].join('\n') };
}

// a valid folder passes without a warning about the data
{
  const r = await run();
  assert.deepEqual(r.errors, []);
  assert.deepEqual(r.warnings, []);
}

// each break is reported as an error (a file of the new shape, or STRICT_INFRA=1; a `y` alone makes a file old-shape)
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
};
for (const [name, [edit, re]] of Object.entries(breaks)) {
  const r = await run((fs) => edit(fs[0].properties), true);
  assert.ok(r.errors.some((e) => re.test(e)), `${name}: expected an error matching ${re}, got ${JSON.stringify(r.errors)}`);
}

// unknown source: always an error; duplicate id across files
{
  const r = await run((fs) => (fs[0].properties.s = 'nobody'));
  assert.ok(r.errors.some((e) => /unknown source "nobody"/.test(e)));
}
{
  const r = await run((fs, dir) => {
    fs.push(feat({ ...mine(), name: 'Other' }, [-71.6, -16.6]));
  });
  assert.ok(r.errors.some((e) => /id also used/.test(e)));
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

// the old shape: warnings, not errors; with the strict switch, errors
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
  const soft = await run(old);
  assert.deepEqual(soft.errors, [], soft.all);
  assert.ok(soft.warnings.length >= 4, soft.all);
  assert.ok(soft.warnings.some((w) => /still in the old shape/.test(w)));
  const strict = await run(old, true);
  assert.ok(strict.errors.length >= 4, strict.all);
}

// the command exits 1 on an error, 0 otherwise, and STRICT_INFRA=1 is read from the environment
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
  const soft = spawnSync(process.execPath, [script, dir3], { encoding: 'utf8' });
  const strict = spawnSync(process.execPath, [script, dir3], { encoding: 'utf8', env: { ...process.env, STRICT_INFRA: '1' } });
  for (const d of [dir2, dir3]) fs.rmSync(d, { recursive: true, force: true });
  assert.equal(soft.status, 0, soft.stderr);
  assert.equal(strict.status, 1);
}

console.log('validate-infra tests passed');
