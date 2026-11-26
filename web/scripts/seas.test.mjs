/**
 * Tests of pipeline/geo/build_seas.mjs (the names of oceans, seas, bays and gulfs of data/geo/seas.json):
 *
 *     node web/scripts/seas.test.mjs
 *
 * Without the shapefile (raw/ is not tracked: a fresh clone, GitHub's runners) the builder leaves the tracked file as it is; that is tested
 * everywhere. Where raw/naturalearth/ne_50m_marine is present, the builder is run on it and on smaller copies of it made here, and the tracked file
 * is compared with the shapefile; those tests skip themselves elsewhere.
 */
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import mapshaper from 'mapshaper';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '../..');
const builder = path.join(repo, 'pipeline/geo/build_seas.mjs');
const tracked = path.join(repo, 'data/geo/seas.json');
const rawDir = path.join(repo, 'raw/naturalearth/ne_50m_marine');
const rawShp = path.join(rawDir, 'ne_50m_geography_marine_polys.shp');
const KEPT = ['ocean', 'sea', 'bay', 'gulf'];
const DROPPED = ['strait', 'channel', 'river', 'reef', 'sound'];

const sha = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const build = (...args) => spawnSync(process.execPath, [builder, ...args], { encoding: 'utf8' });
const trackedSha = sha(tracked);
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'seas-test-'));

// ---- without the shapefile: one line, nothing written, exit 0
{
  const before = sha(tracked);
  const r = build(path.join(tmp, 'no-such-folder', 'marine.shp'));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.stdout.trim().split('\n').length, 1, `one line, got ${JSON.stringify(r.stdout)}`);
  assert.match(r.stdout, /marine areas not found: data\/geo\/seas\.json left as it is/);
  assert.equal(r.stderr, '');
  assert.equal(sha(tracked), before, 'the tracked file is byte-identical');
  // and with --out: the output file is not created either
  const out = path.join(tmp, 'seas-out.json');
  const r2 = build(path.join(tmp, 'no-such-folder', 'marine.shp'), '--out', out);
  assert.equal(r2.status, 0);
  assert.equal(fs.existsSync(out), false);
  assert.equal(sha(tracked), before);
}

// a flag it does not know is a usage error and writes nothing
{
  const r = build('--bogus');
  assert.equal(r.status, 2);
  assert.match(r.stderr, /usage: node pipeline\/geo\/build_seas\.mjs/);
  assert.match(r.stderr, /--accept-fewer/);
}

// ---- with the shapefile
if (!fs.existsSync(rawShp)) {
  console.log('seas: raw/naturalearth/ne_50m_marine is not on this machine, the tests on the shapefile are skipped');
} else {
  const trackedDoc = JSON.parse(fs.readFileSync(tracked, 'utf8'));

  // the builder writes the bytes of the tracked file (and a second run changes nothing)
  {
    const out = path.join(tmp, 'seas-a.json');
    const r = build('--out', out);
    assert.equal(r.status, 0, r.stderr);
    assert.ok(fs.readFileSync(out).equals(fs.readFileSync(tracked)), 'the tracked file is what the builder writes');
    const r2 = build(rawShp, '--out', out);
    assert.equal(r2.status, 0, r2.stderr);
    assert.ok(fs.readFileSync(out).equals(fs.readFileSync(tracked)), 'a second run changes no byte');
    // the version is the one of the VERSION file, not typed in the builder
    const version = fs.readFileSync(rawShp.replace(/\.shp$/, '.VERSION.txt'), 'utf8').trim();
    assert.ok(trackedDoc.n.includes(`version ${version},`), trackedDoc.n);
    assert.equal(trackedDoc.s, 'naturalearth-marine');
    assert.equal('y' in trackedDoc, false);
  }

  // the tracked file holds only the four classes: read the class of each kept name again from the shapefile
  const all = JSON.parse((await mapshaper.applyCommands(`-i "${rawShp}" encoding=utf8 -o out.json format=geojson`))['out.json']).features.map((f) => f.properties);
  const nameOf = (p) => (p.featurecla === 'ocean' ? String(p.name).toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()) : p.name_en || p.name);
  {
    const classOf = new Map();
    for (const p of all) if (p.scalerank <= 3) classOf.set(nameOf(p), p.featurecla);
    const dropped = new Set(all.filter((p) => p.scalerank <= 3 && DROPPED.includes(p.featurecla)).map(nameOf));
    assert.ok(dropped.size > 0, 'the shapefile has straits and channels to drop');
    for (const r of trackedDoc.seas) {
      assert.ok(KEPT.includes(classOf.get(r.n)), `${r.n}: class ${classOf.get(r.n)}`);
      assert.ok(!dropped.has(r.n), `${r.n} is the name of a dropped class`);
      assert.ok(r.r <= 3);
    }
    // and every polygon of a kept class and of rank 3 or less is there
    const kept = [...classOf].filter(([, c]) => KEPT.includes(c)).map(([n]) => n).sort();
    assert.deepEqual(trackedDoc.seas.map((r) => r.n).sort(), kept);
  }

  // smaller copies of the shapefile: what the builder refuses
  const copyOf = async (name, commands) => {
    const dir = path.join(tmp, name);
    fs.mkdirSync(dir);
    const files = await mapshaper.applyCommands(`-i "${rawShp}" encoding=utf8 ${commands} -o ne_50m_geography_marine_polys.shp format=shapefile`);
    for (const [f, buf] of Object.entries(files)) fs.writeFileSync(path.join(dir, f), Buffer.from(buf));
    fs.copyFileSync(rawShp.replace(/\.shp$/, '.VERSION.txt'), path.join(dir, 'ne_50m_geography_marine_polys.VERSION.txt'));
    return path.join(dir, 'ne_50m_geography_marine_polys.shp');
  };
  const refuses = (r, re, out) => {
    assert.equal(r.status, 1, `${r.stdout}${r.stderr}`);
    assert.match(r.stderr, re);
    assert.match(r.stderr, /nothing written/);
    assert.equal(fs.existsSync(out), false, 'nothing is written');
  };

  // a field it reads is missing
  for (const field of ['name', 'name_en', 'featurecla', 'scalerank']) {
    const keep = ['name', 'name_en', 'featurecla', 'scalerank'].filter((f) => f !== field).join(',');
    const shp = await copyOf(`no-${field}`, `-filter-fields ${keep}`);
    const out = path.join(tmp, `no-${field}.json`);
    refuses(build(shp, '--out', out), new RegExp(field), out);
  }
  // a bracket in a name, a name that comes twice
  {
    const shp = await copyOf('bracket', `-each "if (name_en == 'Black Sea') name_en = 'Black Sea (west)'"`);
    const out = path.join(tmp, 'bracket.json');
    refuses(build(shp, '--out', out), /holds a bracket/, out);
  }
  {
    const shp = await copyOf('twice', `-each "if (name_en == 'Red Sea') name_en = 'Black Sea'"`);
    const out = path.join(tmp, 'twice.json');
    refuses(build(shp, '--out', out), /comes twice/, out);
  }
  // fewer than 60 names
  {
    const shp = await copyOf('few', '-filter "scalerank <= 1"');
    const out = path.join(tmp, 'few.json');
    refuses(build(shp, '--out', out), /fewer than 60/, out);
  }
  // fewer rows than the tracked file: stopped, and written only with --accept-fewer
  {
    const shp = await copyOf('lost', `-filter "name_en != 'Black Sea' && name_en != 'Red Sea'"`);
    const out = path.join(tmp, 'lost.json');
    fs.copyFileSync(tracked, out);
    const before = sha(out);
    const r = build(shp, '--out', out);
    assert.equal(r.status, 1, `${r.stdout}${r.stderr}`);
    assert.match(r.stderr, /--accept-fewer overrides/);
    assert.equal(sha(out), before, 'the file with more rows is not replaced');
    const r2 = build(shp, '--out', out, '--accept-fewer');
    assert.equal(r2.status, 0, r2.stderr);
    assert.equal(JSON.parse(fs.readFileSync(out, 'utf8')).seas.length, trackedDoc.seas.length - 2);
  }
  // the version file next to the shapefile is needed
  {
    const shp = await copyOf('no-version', '');
    fs.rmSync(shp.replace(/\.shp$/, '.VERSION.txt'));
    const out = path.join(tmp, 'no-version.json');
    refuses(build(shp, '--out', out), /VERSION\.txt is not next to the shapefile/, out);
  }
  assert.equal(sha(tracked), trackedSha, 'the tracked file was never touched');
}

assert.equal(sha(tracked), trackedSha, 'the tracked file was never touched');
fs.rmSync(tmp, { recursive: true, force: true });
console.log('seas: ok');
