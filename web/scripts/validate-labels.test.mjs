/**
 * Tests of scripts/validate-labels.mjs: a small valid data folder passes, each way of breaking the sea names or the country index is reported as
 * an error, and the real data folder passes.
 *
 *     node web/scripts/validate-labels.test.mjs
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { MAX_RANK, MAX_SEAS, MIN_SEAS, validateLabels } from './validate-labels.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const realData = path.resolve(here, '../../data');

const goodSeas = () => ({
  s: 'naturalearth-marine',
  n: 'Natural Earth Physical Labels, marine areas 1:50m, version 1.0.0, read 1 January 2000',
  seas: Array.from({ length: MIN_SEAS + 8 }, (_, i) => ({ n: `Test sea ${i}`, r: i % (MAX_RANK + 1), at: [(i % 36) * 10 - 175, (i % 17) * 10 - 80] })),
});
const goodCountries = () => [
  { c: 'AAA', name: 'Aland', at: [10, 20], bb: [0, 10, 20, 30] },
  { c: 'BBB', name: 'Bland', at: [-170, -60], bb: [-175, -65, -165, -55] },
];
const chokepoints = [{ id: 'hormuz', name: 'Strait of Hormuz' }, { id: 'suez', name: 'Suez Canal' }];

/** A data folder with the four files the validator reads; `mutate` gets the parsed seas file, the country index and the chokepoints. */
function folder(mutate) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'labels-test-'));
  const seas = goodSeas();
  const countries = goodCountries();
  const cps = structuredClone(chokepoints);
  const sources = [{ id: 'naturalearth-marine' }, { id: 'atlas' }];
  mutate?.({ seas, countries, cps, sources, dir });
  for (const d of ['geo', 'countries', 'freight']) fs.mkdirSync(path.join(dir, d));
  fs.writeFileSync(path.join(dir, 'geo/seas.json'), JSON.stringify(seas));
  fs.writeFileSync(path.join(dir, 'countries/index.json'), JSON.stringify(countries));
  fs.writeFileSync(path.join(dir, 'freight/chokepoints.json'), JSON.stringify(cps));
  fs.writeFileSync(path.join(dir, 'sources.json'), JSON.stringify(sources));
  return dir;
}

function run(mutate) {
  const dir = folder(mutate);
  const errors = [];
  validateLabels(dir, errors);
  fs.rmSync(dir, { recursive: true, force: true });
  return errors;
}

// a valid folder passes, with or without `y`
assert.deepEqual(run(), []);
assert.deepEqual(run(({ seas }) => (seas.y = 2022)), []);

// the real data folder passes, and says its row count as the file has it
{
  const errors = [];
  validateLabels(realData, errors);
  assert.deepEqual(errors, []);
  const real = JSON.parse(fs.readFileSync(path.join(realData, 'geo/seas.json'), 'utf8'));
  assert.ok(real.seas.length >= MIN_SEAS && real.seas.length <= MAX_SEAS);
  assert.equal('y' in real, false, 'the file carries no year: no page read gives one');
}

// each break is reported as an error
const breaks = {
  'an extra key': [({ seas }) => (seas.extra = 1), /the keys are/],
  'no note key': [({ seas }) => delete seas.n, /the keys are/],
  'y that is not an integer': [({ seas }) => (seas.y = '2022'), /y "2022" is not an integer/],
  'a source that is not in the registry': [({ seas }) => (seas.s = 'nobody'), /source "nobody" is not an id of sources.json/],
  'an empty note': [({ seas }) => (seas.n = ' '), /"n" \(the note/],
  'seas that is not a list': [({ seas }) => (seas.seas = {}), /"seas" is not a list/],
  'too few names': [({ seas }) => seas.seas.splice(MIN_SEAS - 1), new RegExp(`${MIN_SEAS - 1} names, expected ${MIN_SEAS} to ${MAX_SEAS}`)],
  'too many names': [({ seas }) => { while (seas.seas.length <= MAX_SEAS) seas.seas.push({ n: `More ${seas.seas.length}`, r: 0, at: [0, 0] }); }, /names, expected/],
  'a duplicate name': [({ seas }) => (seas.seas[5].n = seas.seas[4].n), /the name comes twice/],
  'a bracket in a name': [({ seas }) => (seas.seas[3].n = 'Test sea (north)'), /the name holds a bracket/],
  'a square bracket in a name': [({ seas }) => (seas.seas[3].n = 'Test sea [north]'), /the name holds a bracket/],
  'an empty name': [({ seas }) => (seas.seas[3].n = ''), /the name is empty/],
  'rank 4': [({ seas }) => (seas.seas[2].r = MAX_RANK + 1), /rank 4 is not an integer from 0 to 3/],
  'a rank that is not an integer': [({ seas }) => (seas.seas[2].r = 1.5), /rank 1.5/],
  'a negative rank': [({ seas }) => (seas.seas[2].r = -1), /rank -1/],
  'a longitude out of range': [({ seas }) => (seas.seas[2].at = [181, 0]), /within \+-180 and \+-90/],
  'a latitude out of range': [({ seas }) => (seas.seas[2].at = [0, -90.5]), /within \+-180 and \+-90/],
  'a point that is not finite': [({ seas }) => (seas.seas[2].at = [null, 0]), /within \+-180 and \+-90/],
  'a point of three numbers': [({ seas }) => (seas.seas[2].at = [0, 0, 0]), /within \+-180 and \+-90/],
  'no point': [({ seas }) => delete seas.seas[2].at, /the keys are/],
  'a row with another key': [({ seas }) => (seas.seas[2].k = 'sea'), /the keys are/],
  'a name that is a passage': [({ seas }) => (seas.seas[7].n = 'Strait of Hormuz'), /also a passage of freight\/chokepoints.json/],
  'a name that is a passage in other letters': [({ seas }) => (seas.seas[7].n = 'SUEZ canal'), /also a passage/],
  'a country with no name': [({ countries }) => (countries[0].name = ''), /AAA\): no name/],
  'a country with no point': [({ countries }) => delete countries[1].at, /BBB\): "at" undefined/],
  'a country point out of range': [({ countries }) => (countries[1].at = [10, 95]), /BBB\): "at"/],
  'a country with no box': [({ countries }) => delete countries[0].bb, /AAA\): "bb" undefined/],
  'a country box of three numbers': [({ countries }) => (countries[0].bb = [0, 1, 2]), /AAA\): "bb"/],
  'a country box that is not finite': [({ countries }) => (countries[0].bb = [0, 1, 2, NaN]), /AAA\): "bb"/],
};
for (const [name, [edit, re]] of Object.entries(breaks)) {
  const errors = run(edit);
  assert.ok(errors.some((e) => re.test(e)), `${name}: expected an error matching ${re}, got ${JSON.stringify(errors)}`);
  assert.ok(errors.length >= 1);
}

// a missing file is one error each, not a crash
{
  const dir = folder();
  fs.rmSync(path.join(dir, 'geo/seas.json'));
  fs.rmSync(path.join(dir, 'countries/index.json'));
  const errors = [];
  validateLabels(dir, errors);
  fs.rmSync(dir, { recursive: true, force: true });
  assert.ok(errors.some((e) => /geo\/seas.json: missing or unreadable/.test(e)), JSON.stringify(errors));
  assert.ok(errors.some((e) => /countries\/index.json: missing or unreadable/.test(e)), JSON.stringify(errors));
}
{
  const dir = folder();
  fs.writeFileSync(path.join(dir, 'countries/index.json'), '{}');
  const errors = [];
  validateLabels(dir, errors);
  fs.rmSync(dir, { recursive: true, force: true });
  assert.deepEqual(errors, ['countries/index.json: not a list']);
}

console.log(`validate-labels: ${Object.keys(breaks).length} breaks, all reported`);
