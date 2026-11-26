/**
 * Builds the glyph file of the lettering on the map: signed-distance bitmaps of the characters the map writes, in the
 * protocol buffer layout that MapLibre reads (`glyphs: '.../{fontstack}/{range}.pbf'`).
 *
 *   node pipeline/geo/build_glyphs.mjs [fontfile] [--out <folder>]
 *
 *   fontfile   default raw/fonts/Inter-Medium.otf (not tracked: copy the file of the Debian package `fonts-inter`
 *              there, see docs/UPDATING.md)
 *   --out      default web/public/glyphs; the file is written to <folder>/inter-medium/0-255.pbf
 *
 * The characters are derived, not typed: printable ASCII (32 to 126) and every other character found in the final
 * label strings, that is the `name` of each country of data/countries/index.json, `assetLabel(name)` of each Point
 * feature of data/infrastructure/*.geojson (the pipelines and wpi.json are not named on the map), and each sea name
 * of data/geo/seas.json in upper case (the sea layers draw upper case). A character above U+00FF stops the script:
 * one range file holds U+0000 to U+00FF and a second one is not built here.
 *
 * Each glyph is 24 px, with a 3 px border; its bitmap holds, per pixel, 255 - 255 * (d / 8 + 0.25) clamped to 0 to 255,
 * where d is the exact distance from the pixel centre to the outline, positive outside the letter and negative
 * inside (radius 8, cutoff 0.25: the encoding MapLibre's text shader decodes). The outlines are those of the font,
 * unchanged, placed as MapLibre's layout expects (see ASCENDER); curves are cut into 8 (quadratic) or 10 (cubic)
 * straight pieces. The output is deterministic: a second run writes the same bytes. It was written for this atlas
 * and compared with no other glyph tool.
 *
 * The font file's own strings (copyright, licence, trademark, version) are printed, so that
 * web/public/glyphs/inter-medium/LICENSE.txt and the notices are written from what the file says. The script stops,
 * writing nothing, when the file does not state the SIL Open Font License 1.1, or when LICENSE.txt, if it is in the
 * output folder, does not hold the file's copyright line.
 *
 * Without the font file (a fresh clone, GitHub's runners) it prints one line, writes nothing and exits 0. Run by
 * hand when a character appears or Inter is updated; no workflow runs it.
 *
 * `fontkit` and `pbf` are not dependencies of the atlas: they are installed as dependencies of `mapshaper` and of
 * `maplibre-gl` and are read from web/node_modules. If an upgrade drops one, the script fails when run by hand and
 * nothing else does. Writing the protocol buffer without `pbf` is about fifteen lines (a varint, a length-delimited
 * field, the layout of the writeMessage calls below).
 *
 * It needs Node 22.18 or later, which runs the TypeScript file of the label rules as it is.
 */
import { createRequire } from 'node:module';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GLYPH_RANGE, GLYPH_STACK, assetLabel } from '../../web/src/map/labelRules.ts';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const require = createRequire(path.join(repo, 'web/package.json'));
const DEFAULT_FONT = 'raw/fonts/Inter-Medium.otf';
const DEFAULT_OUT = 'web/public/glyphs';
const USAGE = 'usage: node pipeline/geo/build_glyphs.mjs [fontfile] [--out <folder>]';

const FONT_PX = 24;
const BUFFER = 3;
const RADIUS = 8;
const CUTOFF = 0.25;
const MAX_CODE = 255;

const args = process.argv.slice(2);
let fontArg = null;
let outArg = null;
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--out') {
    outArg = args[++i];
    if (!outArg || outArg.startsWith('--')) {
      console.error(USAGE);
      process.exit(2);
    }
  } else if (args[i].startsWith('--') || fontArg !== null) {
    console.error(USAGE);
    process.exit(2);
  } else fontArg = args[i];
}
const fontFile = path.resolve(fontArg ?? path.join(repo, DEFAULT_FONT));
const outFolder = path.resolve(outArg ?? path.join(repo, DEFAULT_OUT));
const shown = (p) => (path.relative(repo, p).startsWith('..') ? p : path.relative(repo, p));

if (!fs.existsSync(fontFile)) {
  console.log(`font not found: ${shown(outFolder)} left as it is`);
  process.exit(0);
}

const fail = (message) => {
  console.error(`${message}; nothing written`);
  process.exit(1);
};

// ---- the characters
const readJson = (file) => JSON.parse(fs.readFileSync(path.join(repo, file), 'utf8'));
const labels = [];
for (const row of readJson('data/countries/index.json')) {
  if (typeof row.name !== 'string' || !row.name) fail(`data/countries/index.json: a row has no name (${JSON.stringify(row.c)})`);
  labels.push({ from: 'country names', text: row.name });
}
for (const file of fs.readdirSync(path.join(repo, 'data/infrastructure')).sort()) {
  if (!file.endsWith('.geojson') || file === 'pipelines.geojson') continue;
  for (const f of readJson(`data/infrastructure/${file}`).features) {
    if (f.geometry?.type !== 'Point') continue;
    if (typeof f.properties?.name !== 'string') fail(`data/infrastructure/${file}: a point has no name`);
    labels.push({ from: 'port and asset names', text: assetLabel(f.properties.name) });
  }
}
for (const sea of readJson('data/geo/seas.json').seas) labels.push({ from: 'sea names', text: sea.n.toUpperCase() });

const codes = new Set();
for (let c = 32; c <= 126; c++) codes.add(c);
const outside = new Map();
for (const { from, text } of labels) {
  for (const ch of text) {
    const c = ch.codePointAt(0);
    if (c < 32 || (c > 126 && c < 160) || c > MAX_CODE) outside.set(ch, `${from}: ${text}`);
    else codes.add(c);
  }
}
if (outside.size) {
  const list = [...outside].map(([ch, where]) => `U+${ch.codePointAt(0).toString(16).toUpperCase().padStart(4, '0')} in ${where}`).join('; ');
  fail(`characters outside ${GLYPH_RANGE} (a second range file is not built here): ${list}`);
}

// ---- the font
const fontkit = require('fontkit');
const _pbf = require('pbf');
const Pbf = _pbf.default ?? _pbf;
const font = fontkit.openSync(fontFile);
const strings = Object.fromEntries(['copyright', 'license', 'licenseURL', 'trademark', 'version', 'fullName', 'postscriptName'].map((k) => [k, font.getName(k)]));
const sha = crypto.createHash('sha256').update(fs.readFileSync(fontFile)).digest('hex');
console.log(`font ${shown(fontFile)} sha256 ${sha}, ${font.unitsPerEm} units per em, ${font.numGlyphs} glyphs`);
for (const [k, v] of Object.entries(strings)) console.log(`  ${k}: ${JSON.stringify(v)}`);

if (!strings.copyright) fail('the font file carries no copyright line');
if (!/SIL Open Font License, Version 1\.1/.test(strings.license ?? '')) fail('the font file does not state the SIL Open Font License, Version 1.1: the notices say it does');
const licenceFile = path.join(outFolder, GLYPH_STACK, 'LICENSE.txt');
if (fs.existsSync(licenceFile) && !fs.readFileSync(licenceFile, 'utf8').includes(strings.copyright)) {
  fail(`${shown(licenceFile)} does not hold the font's copyright line (${JSON.stringify(strings.copyright)}): it was written for another font`);
}
const missing = [...codes].filter((c) => !font.hasGlyphForCodePoint(c));
if (missing.length) fail(`the font has no glyph for ${missing.map((c) => `U+${c.toString(16).toUpperCase().padStart(4, '0')}`).join(', ')}`);

// ---- the glyphs
const scale = FONT_PX / font.unitsPerEm;
// MapLibre's text layout measures the top of a glyph from the ascender line of a 24 px line, not from the baseline (it
// adds a fixed offset of -17 px and centres the line box on the anchor). The `top` written is therefore the height of
// the glyph above the baseline minus the font's ascender in pixels; with the height above the baseline, a name
// anchored at its centre sits about one em above its point (seen on a test page, see docs/UPDATING.md).
const ASCENDER = Math.round(font.ascent * scale);

/** The outline as closed polygons in pixels, y up, from the font's path commands. */
function flatten(commands) {
  const polys = [];
  let cur = null;
  let x = 0;
  let y = 0;
  for (const { command, args: a } of commands) {
    if (command === 'moveTo') {
      cur = [[a[0], a[1]]];
      polys.push(cur);
      [x, y] = a;
    } else if (command === 'lineTo') {
      cur.push([a[0], a[1]]);
      [x, y] = a;
    } else if (command === 'quadraticCurveTo') {
      for (let i = 1; i <= 8; i++) {
        const t = i / 8;
        const p = (1 - t) * (1 - t);
        const q = 2 * (1 - t) * t;
        const r = t * t;
        cur.push([p * x + q * a[0] + r * a[2], p * y + q * a[1] + r * a[3]]);
      }
      [x, y] = [a[2], a[3]];
    } else if (command === 'bezierCurveTo') {
      for (let i = 1; i <= 10; i++) {
        const t = i / 10;
        const u = 1 - t;
        cur.push([
          u * u * u * x + 3 * u * u * t * a[0] + 3 * u * t * t * a[2] + t * t * t * a[4],
          u * u * u * y + 3 * u * u * t * a[1] + 3 * u * t * t * a[3] + t * t * t * a[5],
        ]);
      }
      [x, y] = [a[4], a[5]];
    } else if (command !== 'closePath') fail(`unknown path command ${command}`);
  }
  return polys.map((p) => p.map(([px, py]) => [px * scale, py * scale]));
}

function distanceToSegment(px, py, ax, ay, bx, by) {
  const dx = bx - ax;
  const dy = by - ay;
  const len = dx * dx + dy * dy;
  const t = len ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len)) : 0;
  return Math.hypot(ax + t * dx - px, ay + t * dy - py);
}

/** Winding number of the outline around a point (non-zero: inside). */
function winding(px, py, polys) {
  let w = 0;
  for (const p of polys) {
    for (let i = 0; i < p.length; i++) {
      const [ax, ay] = p[i];
      const [bx, by] = p[(i + 1) % p.length];
      const side = (bx - ax) * (py - ay) - (px - ax) * (by - ay);
      if (ay <= py) {
        if (by > py && side > 0) w++;
      } else if (by <= py && side < 0) w--;
    }
  }
  return w;
}

function glyph(code) {
  const g = font.glyphForCodePoint(code);
  const advance = Math.round(g.advanceWidth * scale);
  const polys = flatten(g.path.commands);
  if (!polys.length) return { id: code, width: 0, height: 0, left: 0, top: ASCENDER, advance };
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const p of polys) {
    for (const [x, y] of p) {
      x0 = Math.min(x0, x);
      x1 = Math.max(x1, x);
      y0 = Math.min(y0, y);
      y1 = Math.max(y1, y);
    }
  }
  const left = Math.floor(x0);
  const bottom = Math.floor(y0);
  const width = Math.ceil(x1) - left;
  const top = Math.ceil(y1);
  const height = top - bottom;
  const W = width + 2 * BUFFER;
  const H = height + 2 * BUFFER;
  const bitmap = Buffer.alloc(W * H);
  for (let j = 0; j < H; j++) {
    for (let i = 0; i < W; i++) {
      const px = left - BUFFER + i + 0.5;
      const py = top + BUFFER - j - 0.5; // y is up in the outline
      let d = Infinity;
      for (const p of polys) {
        for (let k = 0; k < p.length; k++) {
          const a = p[k];
          const b = p[(k + 1) % p.length];
          d = Math.min(d, distanceToSegment(px, py, a[0], a[1], b[0], b[1]));
        }
      }
      const signed = winding(px, py, polys) !== 0 ? -d : d;
      bitmap[j * W + i] = Math.max(0, Math.min(255, Math.round(255 - 255 * (signed / RADIUS + CUTOFF))));
    }
  }
  return { id: code, bitmap, width, height, left, top, advance };
}

const glyphs = [...codes].sort((a, b) => a - b).map(glyph);

// ---- MapLibre's glyph message: fontstack { 1: name, 2: range, 3: glyph { 1 id, 2 bitmap, 3 width, 4 height, 5 left, 6 top, 7 advance } }
const pbf = new Pbf();
pbf.writeMessage(
  1,
  (_, p) => {
    p.writeStringField(1, GLYPH_STACK);
    p.writeStringField(2, GLYPH_RANGE);
    for (const g of glyphs) {
      p.writeMessage(
        3,
        (gl, q) => {
          q.writeVarintField(1, gl.id);
          if (gl.bitmap) q.writeBytesField(2, gl.bitmap);
          q.writeVarintField(3, gl.width);
          q.writeVarintField(4, gl.height);
          q.writeSVarintField(5, gl.left);
          q.writeSVarintField(6, gl.top - ASCENDER);
          q.writeVarintField(7, gl.advance);
        },
        g,
      );
    }
  },
  {},
);
const bytes = Buffer.from(pbf.finish());
const target = path.join(outFolder, GLYPH_STACK, `${GLYPH_RANGE}.pbf`);
fs.mkdirSync(path.dirname(target), { recursive: true });
fs.writeFileSync(target, bytes);
const accented = glyphs.filter((g) => g.id > 126).map((g) => String.fromCodePoint(g.id)).join(' ');
console.log(`${shown(target)}: ${glyphs.length} glyphs (${glyphs.length - glyphs.filter((g) => g.id > 126).length} ASCII and ${glyphs.filter((g) => g.id > 126).length} others: ${accented}), ${bytes.length} bytes`);
