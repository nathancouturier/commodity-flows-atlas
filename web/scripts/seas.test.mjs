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
import { inGeometry, inRing, onEdge, roundInside } from '../../pipeline/geo/polygon.mjs';

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

// ---- the point-in-polygon rule of the builder (runs everywhere)
{
  const square = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]];
  const hole = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]];
  assert.equal(inRing(5, 5, square), true);
  assert.equal(inRing(11, 5, square), false);
  assert.equal(inRing(5, -1, square), false);
  assert.equal(inGeometry([5, 5], { type: 'Polygon', coordinates: [square, hole] }), false, 'a hole is outside');
  assert.equal(inGeometry([2, 2], { type: 'Polygon', coordinates: [square, hole] }), true);
  const far = square.map(([x, y]) => [x + 100, y]);
  const multi = { type: 'MultiPolygon', coordinates: [[square], [far]] };
  assert.equal(inGeometry([105, 5], multi), true, 'any polygon of a multipolygon');
  assert.equal(inGeometry([50, 5], multi), false);
  assert.equal(inGeometry([5, 5], { type: 'Point', coordinates: [5, 5] }), false);

  // a sliver 0.009 degree high: the point rounds to 0.1 and to 0.01 outside it, to 0.001 inside
  const sliver = { type: 'Polygon', coordinates: [[[0, 0.0405], [1, 0.0405], [1, 0.0495], [0, 0.0495], [0, 0.0405]]] };
  assert.deepEqual(roundInside([0.5, 0.04491], sliver), { at: [0.5, 0.045], decimals: 3 });
  // a polygon that holds the point rounded to 0.1 keeps the 0.1
  assert.deepEqual(roundInside([5.04, 5.06], { type: 'Polygon', coordinates: [square] }), { at: [5, 5.1], decimals: 1 });
  // one decimal outside, two inside
  const strip = { type: 'Polygon', coordinates: [[[0, 0.11], [1, 0.11], [1, 0.19], [0, 0.19], [0, 0.11]]] };
  assert.deepEqual(roundInside([0.5, 0.1349], strip), { at: [0.5, 0.13], decimals: 2 });
  // none inside to 0.001 degree: no row is written from it
  const thread = { type: 'Polygon', coordinates: [[[0.1002, 0.2002], [0.1004, 0.2002], [0.1004, 0.2004], [0.1002, 0.2004], [0.1002, 0.2002]]] };
  assert.equal(roundInside([0.1003, 0.2003], thread), null);
  assert.equal(roundInside([50, 50], { type: 'Polygon', coordinates: [square] }), null, 'a point that is not inside to begin with');

  // a point on an edge: inRing counts the left and the bottom edges (and the corner they meet in) as inside, the right and the top as outside;
  // onEdge tells every one of them, and roundInside refuses it
  const squarePolygon = { type: 'Polygon', coordinates: [square] };
  const sides = { left: [0, 5], bottom: [5, 0], right: [10, 5], top: [5, 10] };
  assert.deepEqual(
    Object.fromEntries(Object.entries(sides).map(([side, [x, y]]) => [side, inRing(x, y, square)])),
    { left: true, bottom: true, right: false, top: false },
    'what the even-odd rule says of a point on each side',
  );
  for (const [side, at] of Object.entries(sides)) assert.equal(onEdge(at, squarePolygon), true, `a point on the ${side} side is on an edge`);
  for (const at of [[0, 0], [10, 0], [10, 10], [0, 10]]) assert.equal(onEdge(at, squarePolygon), true, `the corner ${at} is on an edge`);
  assert.equal(onEdge([5, 5], squarePolygon), false);
  assert.equal(onEdge([1e-6, 5], squarePolygon), false, 'a point a millionth of a degree from an edge is not on it');
  assert.equal(onEdge([5e-10, 5], squarePolygon), true, 'a point closer than 1e-9 degree is');
  assert.equal(onEdge([5, 5], { type: 'Point', coordinates: [5, 5] }), false);
  // the edge of a hole is an edge of the polygon: the point on the hole's left edge reads as in the hole (outside), on its right edge as in the polygon
  const holed = { type: 'Polygon', coordinates: [square, hole] };
  assert.equal(inGeometry([4, 5], holed), false);
  assert.equal(inGeometry([6, 5], holed), true);
  for (const at of [[4, 5], [6, 5], [5, 4], [5, 6]]) assert.equal(onEdge(at, holed), true, `a point on the hole's edge ${at}`);
  assert.equal(onEdge([5, 5], holed), false, 'the middle of the hole is on no edge');
  assert.equal(onEdge([105, 5], multi), false);
  assert.equal(onEdge([100, 5], multi), true, 'any polygon of a multipolygon');
  // a point that rounds onto an edge is refused there and taken at the next number of decimals, or by none
  const unit = { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]] };
  assert.equal(inGeometry([0, 0.5], unit), true, 'the left edge counts as inside for inRing');
  assert.deepEqual(roundInside([0.04, 0.5], unit), { at: [0.04, 0.5], decimals: 2 }, 'rounded to 0.1 the point is on the left edge: refused');
  const narrow = { type: 'Polygon', coordinates: [[[0, 0], [0.0004, 0], [0.0004, 10], [0, 10], [0, 0]]] };
  assert.equal(roundInside([0.00031, 5.0004], narrow), null, 'rounded at every number of decimals the point is on the left edge');
  // a point that is inside the polygon and far from every edge is unchanged by the rule
  assert.deepEqual(roundInside([5.04, 5.06], squarePolygon), { at: [5, 5.1], decimals: 1 });
}

// METHODOLOGY says how a point that the rounding puts outside its polygon is kept (runs everywhere)
assert.ok(
  fs.readFileSync(path.join(repo, 'METHODOLOGY.md'), 'utf8').replace(/\s+/g, ' ').includes('the builder keeps the fewest decimals at which every point is inside its polygon'),
  'METHODOLOGY states the rule of the label points',
);

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

  // what METHODOLOGY says of the oceans' names: `name`, not `name_en` (two polygons share one), and only some are in capitals in the file
  {
    const oceans = all.filter((p) => p.featurecla === 'ocean');
    assert.equal(oceans.length, trackedDoc.seas.filter((r) => r.r === 0).length);
    assert.ok(new Set(oceans.map((p) => p.name_en)).size < oceans.length, 'two polygons share a name_en, which is why the oceans take `name`');
    const capitals = oceans.filter((p) => p.name === p.name.toUpperCase()).map(nameOf).sort();
    assert.deepEqual(capitals, ['Indian Ocean', 'Southern Ocean']);
    const md = fs.readFileSync(path.join(repo, 'METHODOLOGY.md'), 'utf8').replace(/\s+/g, ' ');
    assert.ok(md.includes('for the oceans `name`, because the two Atlantic polygons share one `name_en` and so do the two Pacific ones; two of the seven, the Indian and the Southern, are written in capitals in the file'));
    assert.ok(!md.includes('the oceans are written in capitals in the file'));
  }

  // each label point is inside its own polygon, rounded as it is in the file (the Scotia Sea is a sliver: 0.1 degree would put its point outside)
  {
    const shapes = JSON.parse((await mapshaper.applyCommands(`-i "${rawShp}" encoding=utf8 -filter "scalerank <= 3" -o out.json format=geojson`))['out.json']).features;
    const polygonOf = new Map(shapes.map((f) => [nameOf(f.properties), f.geometry]));
    for (const r of trackedDoc.seas) assert.ok(inGeometry(r.at, polygonOf.get(r.n)), `${r.n} ${JSON.stringify(r.at)} is outside its polygon`);
    const scotia = trackedDoc.seas.find((r) => r.n === 'Scotia Sea');
    assert.ok(scotia && scotia.at.some((v) => Math.abs(v * 10 - Math.round(v * 10)) > 1e-9), 'the Scotia Sea keeps more than one decimal');
    const others = trackedDoc.seas.filter((r) => r.n !== 'Scotia Sea');
    assert.ok(others.every((r) => r.at.every((v) => Math.abs(v * 10 - Math.round(v * 10)) < 1e-9)), 'every other row is rounded to 0.1 degree');
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
