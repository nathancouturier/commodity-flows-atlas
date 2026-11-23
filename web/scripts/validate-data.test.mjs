/**
 * Tests of the range checks of scripts/validate-data.mjs on a copy of the data folder: the copy passes as the real
 * folder does, and a swapped coordinate pair, a share above 1, an implausible year and an unknown country code each fail.
 *
 *     node web/scripts/validate-data.test.mjs
 */
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'validate-data-'));
// the validator reads ../../data from its own folder: copy the scripts and the data side by side
fs.mkdirSync(path.join(tmp, 'web', 'scripts'), { recursive: true });
for (const f of fs.readdirSync(here)) if (f.endsWith('.mjs') && !f.endsWith('.test.mjs')) fs.copyFileSync(path.join(here, f), path.join(tmp, 'web', 'scripts', f));
fs.cpSync(path.resolve(here, '../../data'), path.join(tmp, 'data'), { recursive: true, dereference: true });
const data = path.join(tmp, 'data');
const run = () => spawnSync(process.execPath, [path.join(tmp, 'web', 'scripts', 'validate-data.mjs')], { encoding: 'utf8' });
const edit = (rel, fn) => {
  const p = path.join(data, rel);
  const before = fs.readFileSync(p, 'utf8');
  const doc = JSON.parse(before);
  fn(doc);
  fs.writeFileSync(p, JSON.stringify(doc));
  return () => fs.writeFileSync(p, before);
};
let n = 0;
const ok = (name, fn) => {
  fn();
  n++;
  console.log(`ok   ${name}`);
};

try {
  const base = run();
  const real = spawnSync(process.execPath, [path.join(here, 'validate-data.mjs')], { encoding: 'utf8' });
  ok('the copy of the data folder gives the same verdict as the real one', () => assert.equal(base.status, real.status, base.stderr.slice(0, 2000)));
  // the cases below need a folder that passes: the real one, as published
  assert.equal(base.status, 0, `the data folder does not pass the validator:\n${base.stderr.slice(0, 2000)}`);
  const geo = fs.readdirSync(path.join(data, 'infrastructure')).find((f) => f.endsWith('.geojson'));
  const findPoint = (doc) => doc.features.find((f) => f.geometry?.type === 'Point');
  ok('a point with longitude and latitude swapped is refused', () => {
    const undo = edit(`infrastructure/${geo}`, (doc) => {
      const f = findPoint(doc);
      f.geometry.coordinates = [10, 120];
    });
    const r = run();
    undo();
    assert.equal(r.status, 1);
    assert.match(r.stderr, /coordinates \[10, 120\] are not a longitude and a latitude/);
  });
  ok('a share above 1 is refused', () => {
    const lane = fs.readdirSync(path.join(data, 'freight', 'lanes'))[0];
    const undo = edit(`freight/lanes/${lane}`, (doc) => {
      const visit = (o) => {
        if (Array.isArray(o)) return o.some(visit);
        if (!o || typeof o !== 'object') return false;
        if (typeof o.share === 'number') {
          o.share = 7;
          return true;
        }
        return Object.values(o).some(visit);
      };
      assert.ok(visit(doc), 'no share in the lane file');
    });
    const r = run();
    undo();
    assert.equal(r.status, 1);
    assert.match(r.stderr, /share 7 is not between 0 and 1/);
  });
  ok('a figure dated in year 20240 is refused', () => {
    const undo = edit('commodities/copper.json', (doc) => {
      const visit = (o) => {
        if (Array.isArray(o)) return o.some(visit);
        if (!o || typeof o !== 'object') return false;
        if (typeof o.y === 'number' && typeof o.s === 'string') {
          o.y = 20240;
          return true;
        }
        return Object.values(o).some(visit);
      };
      assert.ok(visit(doc), 'no dated figure in copper.json');
    });
    const r = run();
    undo();
    assert.equal(r.status, 1);
    assert.match(r.stderr, /year 20240 is not plausible/);
  });
  ok('an unknown country code is refused', () => {
    const undo = edit('commodities/copper.json', (doc) => {
      const visit = (o) => {
        if (Array.isArray(o)) return o.some(visit);
        if (!o || typeof o !== 'object') return false;
        if (typeof o.c === 'string' && /^[A-Z]{3}$/.test(o.c)) {
          o.c = 'XQZ';
          return true;
        }
        return Object.values(o).some(visit);
      };
      assert.ok(visit(doc), 'no country code in copper.json');
    });
    const r = run();
    undo();
    assert.equal(r.status, 1);
    assert.match(r.stderr, /country code "XQZ" is not in countries\/index.json or places.json/);
  });
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}
console.log(`validate-data: ${n} checks passed`);
