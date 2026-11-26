/**
 * Tests of the glyph file of the map's lettering (public/glyphs/inter-medium/0-255.pbf) and of its builder
 * (pipeline/geo/build_glyphs.mjs): `node web/scripts/glyphs.test.mjs`.
 *
 * What runs everywhere: the file is decoded here (a small varint walker, no dependency) and checked against the names the map writes, read from the
 * data files; its licence file is checked; the builder run on a font that does not exist leaves the tracked file as it is. Where
 * raw/fonts/Inter-Medium.otf is present (raw/ is not tracked: a fresh clone and GitHub's runners do not have it) the builder is run on it, to a
 * temporary folder, and must write the tracked file byte for byte; those tests skip themselves elsewhere.
 */
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GLYPH_RANGE, GLYPH_STACK, LABEL_FONT, assetLabel } from '../src/map/labelRules.ts';
import { decode } from './glyph-file.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '../..');
const builder = path.join(repo, 'pipeline/geo/build_glyphs.mjs');
const folder = path.join(repo, 'web/public/glyphs', GLYPH_STACK);
const tracked = path.join(folder, `${GLYPH_RANGE}.pbf`);
const fontFile = path.join(repo, 'raw/fonts/Inter-Medium.otf');
const readJson = (rel) => JSON.parse(fs.readFileSync(path.join(repo, rel), 'utf8'));
const sha = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const build = (...args) => spawnSync(process.execPath, [builder, ...args], { encoding: 'utf8' });
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'glyphs-test-'));

// ---- the characters the map writes, read from the files
const labels = [];
for (const row of readJson('data/countries/index.json')) labels.push(row.name);
for (const file of fs.readdirSync(path.join(repo, 'data/infrastructure')).sort()) {
  if (!file.endsWith('.geojson') || file === 'pipelines.geojson') continue;
  for (const f of readJson(`data/infrastructure/${file}`).features) if (f.geometry.type === 'Point') labels.push(assetLabel(f.properties.name));
}
for (const sea of readJson('data/geo/seas.json').seas) labels.push(sea.n.toUpperCase());
const needed = new Set();
for (let c = 32; c <= 126; c++) needed.add(c);
for (const text of labels) for (const ch of text) needed.add(ch.codePointAt(0));

// ---- the file
const bytes = fs.readFileSync(tracked);
const file = decode(bytes);
assert.equal(file.name, GLYPH_STACK, 'the stack name is the one the style asks for');
assert.deepEqual(LABEL_FONT, [GLYPH_STACK]);
assert.equal(file.range, GLYPH_RANGE);
assert.ok(labels.length > 800, `names read: ${labels.length}`);

// every character of every label has a glyph (a missing one is dropped from the name by the library)
for (const text of labels) for (const ch of text) assert.ok(file.glyphs.has(ch.codePointAt(0)), `no glyph for ${JSON.stringify(ch)} (U+${ch.codePointAt(0).toString(16)}) of "${text}"`);
// and the file holds no more than it needs: the set is derived, so a name that left the data leaves the file at the next build
const hex = (codes) => codes.map((c) => `U+${c.toString(16).toUpperCase().padStart(4, '0')} ${String.fromCodePoint(c)}`).join(', ');
const extra = [...file.glyphs.keys()].filter((c) => !needed.has(c));
assert.equal(extra.length, 0, `no label writes ${hex(extra)} any more: rebuild the glyph file with node pipeline/geo/build_glyphs.mjs (docs/UPDATING.md, "The glyph file of the lettering")`);
assert.deepEqual([...file.glyphs.keys()].sort((a, b) => a - b), [...needed].sort((a, b) => a - b), 'the glyphs are exactly the characters of the labels and printable ASCII');
assert.ok([...file.glyphs.keys()].every((id) => id <= 255), 'one range: U+0000 to U+00FF');

for (const g of file.glyphs.values()) {
  const ch = String.fromCodePoint(g.id);
  assert.ok(Number.isInteger(g.advance) && g.advance > 0, `advance of ${ch}`);
  if (g.width && g.height) {
    assert.ok(g.bitmap, `${ch} has a bitmap`);
    assert.equal(g.bitmap.length, (g.width + 6) * (g.height + 6), `bitmap of ${ch}: (width + 2 x 3) x (height + 2 x 3)`);
    assert.ok(g.bitmap.some((v) => v > 192) && g.bitmap.some((v) => v < 64), `the bitmap of ${ch} has an inside and an outside`);
  } else assert.ok(!g.bitmap, `${ch} has no outline and no bitmap`);
}
assert.equal(file.glyphs.get(32).width, 0, 'the space has no outline');
// the top of a glyph is written from the ascender line, which is how the library's layout reads it: a capital sits at a negative top, not at its height above the baseline
assert.ok(file.glyphs.get('H'.charCodeAt(0)).top < 0 && file.glyphs.get('H'.charCodeAt(0)).top > -24, 'top of H is measured from the ascender line');

// ---- the licence travels with the file
{
  assert.ok(fs.existsSync(path.join(folder, 'LICENSE.txt')), 'LICENSE.txt is next to the glyph file');
  const licence = fs.readFileSync(path.join(folder, 'LICENSE.txt'), 'utf8');
  assert.match(licence, /SIL OPEN FONT LICENSE Version 1\.1 - 26 February 2007/);
  assert.match(licence, /PERMISSION & CONDITIONS/);
  assert.match(licence, /Modified Version of that Font Software/);
  const copyright = licence.split('\n')[0];
  assert.match(copyright, /^Copyright \d{4} .*Inter Project Authors$/, 'the first line is the font\'s own copyright line');
  for (const notice of ['NOTICE.md', 'THIRD-PARTY-NOTICES.md']) {
    assert.ok(fs.readFileSync(path.join(repo, notice), 'utf8').includes(copyright), `${notice} holds the copyright line of LICENSE.txt`);
  }
  assert.ok(fs.readFileSync(path.join(repo, 'NOTICE.md'), 'utf8').includes('web/public/glyphs/inter-medium/0-255.pbf'), 'NOTICE.md names the glyph file');
  // where the font is on this machine, the line is the font's own
  if (fs.existsSync(fontFile)) {
    const font = createRequire(path.join(repo, 'web/package.json'))('fontkit').openSync(fontFile);
    assert.equal(copyright, font.getName('copyright'));
    assert.ok(licence.includes(font.getName('license')), 'the font\'s licence string is in LICENSE.txt');
    assert.ok(licence.includes(font.getName('trademark')), 'the font\'s trademark line is in LICENSE.txt');
    assert.ok(licence.includes(font.getName('version')), 'the font\'s version is in LICENSE.txt');
  }
}

// ---- the builder without the font: one line, nothing written, exit 0
{
  const before = sha(tracked);
  const r = build(path.join(tmp, 'no-such-font.otf'));
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.stdout.trim().split('\n').length, 1, `one line, got ${JSON.stringify(r.stdout)}`);
  assert.match(r.stdout, /font not found: web\/public\/glyphs left as it is/);
  assert.equal(r.stderr, '');
  assert.equal(sha(tracked), before, 'the tracked file is byte-identical');
  const out = path.join(tmp, 'out-none');
  assert.equal(build(path.join(tmp, 'no-such-font.otf'), '--out', out).status, 0);
  assert.equal(fs.existsSync(out), false, 'nothing is created');
  const usage = build('--bogus');
  assert.equal(usage.status, 2);
  assert.match(usage.stderr, /usage: node pipeline\/geo\/build_glyphs\.mjs/);
}

// ---- the builder with the font
if (!fs.existsSync(fontFile)) {
  console.log('glyphs: raw/fonts/Inter-Medium.otf is not on this machine, the tests that run the builder on the font are skipped');
} else {
  const trackedSha = sha(tracked);
  const out1 = path.join(tmp, 'out1');
  const r1 = build('--out', out1);
  assert.equal(r1.status, 0, r1.stderr);
  const built = path.join(out1, GLYPH_STACK, `${GLYPH_RANGE}.pbf`);
  assert.equal(sha(built), trackedSha, 'the tracked file is the builder\'s output, byte for byte');
  assert.match(r1.stdout, /copyright: "Copyright 2016 The Inter Project Authors"/, 'it prints the font\'s own strings');
  assert.match(r1.stdout, /license: "This Font Software is licensed under the SIL Open Font License, Version 1\.1\./);
  assert.match(r1.stdout, /trademark: /);
  assert.match(r1.stdout, /version: /);
  const out2 = path.join(tmp, 'out2');
  assert.equal(build('--out', out2).status, 0);
  assert.equal(sha(path.join(out2, GLYPH_STACK, `${GLYPH_RANGE}.pbf`)), trackedSha, 'a second run is byte-identical');
  assert.equal(sha(tracked), trackedSha, 'the tracked file was not touched by runs to another folder');
  assert.deepEqual(fs.readdirSync(path.join(out1, GLYPH_STACK)), [`${GLYPH_RANGE}.pbf`], 'the builder writes the glyph file only; the licence text is kept by hand');

  // a licence file that was written for another font stops the build, with nothing written
  const out3 = path.join(tmp, 'out3');
  fs.mkdirSync(path.join(out3, GLYPH_STACK), { recursive: true });
  fs.writeFileSync(path.join(out3, GLYPH_STACK, 'LICENSE.txt'), 'Copyright 1999 Another Font Foundry\n');
  const r3 = build('--out', out3);
  assert.equal(r3.status, 1);
  assert.match(r3.stderr, /does not hold the font's copyright line/);
  assert.match(r3.stderr, /nothing written/);
  assert.equal(fs.existsSync(path.join(out3, GLYPH_STACK, `${GLYPH_RANGE}.pbf`)), false);
}

fs.rmSync(tmp, { recursive: true, force: true });
console.log('glyphs: ok');
