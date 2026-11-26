/**
 * Builds the names and label points of the oceans, seas, bays and gulfs drawn on the map, from Natural Earth's
 * marine areas 1:50m (Physical Labels).
 *
 *   node pipeline/geo/build_seas.mjs [shapefile] [--out <file>] [--accept-fewer]
 *
 *   shapefile       default raw/naturalearth/ne_50m_marine/ne_50m_geography_marine_polys.shp (not tracked: unzip the
 *                   marine areas 1:50m of https://www.naturalearthdata.com/downloads/50m-physical-vectors/ there)
 *   --out <file>    default data/geo/seas.json
 *   --accept-fewer  write a table that has fewer rows than the tracked file (stopped otherwise)
 *
 * Output  { s, n, seas: [{ n: name, r: Natural Earth's scalerank 0 to 3, at: [lon, lat] }] }, sorted by r then n.
 *   The classes kept are ocean, sea, bay and gulf. Straits, channels, rivers, reefs and sounds are left out: the atlas
 *   draws its passages as markers (data/freight/chokepoints.json), and a passage must not be named twice.
 *   `at` is the pole of inaccessibility of the polygon (mapshaper `-points inner`), rounded to 0.1 degree. A point that the rounding
 *   puts outside its polygon (a thin one, the Scotia Sea) is rounded to 0.01, then to 0.001 degree, the fewest decimals that
 *   keep it inside; the script stops if no rounding is inside.
 *   There is no `y`: no page read gives the year of the release, so `n` carries the version (read from the
 *   VERSION file next to the shapefile) and the day the files were read.
 *
 * Without the shapefile (a fresh clone, GitHub's runners) it prints one line, writes nothing and exits 0.
 * It stops without writing (exit 1) when a field it reads is missing, when a name holds a bracket or repeats, when it
 * would write fewer than MIN_ROWS rows, or fewer rows than the tracked file. Run by hand; no workflow runs it.
 *
 * Natural Earth's terms (https://www.naturalearthdata.com/about/terms-of-use/) are quoted in NOTICE.md.
 */
import mapshaper from '../../web/node_modules/mapshaper/mapshaper.js';
import { roundInside } from './polygon.mjs';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const DEFAULT_SHP = 'raw/naturalearth/ne_50m_marine/ne_50m_geography_marine_polys.shp';
const DEFAULT_OUT = 'data/geo/seas.json';
// The day the zip and Natural Earth's terms page were read. Edited by hand when the files are read again (a refresh).
const READ_ON = '25 November 2026';
const SOURCE_ID = 'naturalearth-marine';
const KEEP = new Set(['ocean', 'sea', 'bay', 'gulf']);
const FIELDS = ['name', 'name_en', 'featurecla', 'scalerank'];
const MAX_RANK = 3;
const MIN_ROWS = 60;
const USAGE = 'usage: node pipeline/geo/build_seas.mjs [shapefile] [--out <file>] [--accept-fewer]';

const args = process.argv.slice(2);
let shpArg = null;
let outArg = null;
let acceptFewer = false;
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--out') {
    outArg = args[++i];
    if (!outArg || outArg.startsWith('--')) {
      console.error(USAGE);
      process.exit(2);
    }
  }
  else if (args[i] === '--accept-fewer') acceptFewer = true;
  else if (args[i].startsWith('--') || shpArg !== null) {
    console.error(USAGE);
    process.exit(2);
  } else shpArg = args[i];
}
const shp = path.resolve(shpArg ?? path.join(repo, DEFAULT_SHP));
const out = path.resolve(outArg ?? path.join(repo, DEFAULT_OUT));

function stop(message) {
  console.error(`build_seas: ${message}; nothing written`);
  process.exit(1);
}

if (!fs.existsSync(shp)) {
  console.log('marine areas not found: data/geo/seas.json left as it is');
  process.exit(0);
}

const versionFile = shp.replace(/\.shp$/i, '.VERSION.txt');
if (!fs.existsSync(versionFile)) stop(`${path.basename(versionFile)} is not next to the shapefile, so the version is unknown`);
const version = fs.readFileSync(versionFile, 'utf8').trim();
if (!version) stop(`${path.basename(versionFile)} is empty`);

let gj;
let polygons;
try {
  const res = await mapshaper.applyCommands(`-i "${shp}" encoding=utf8 -filter "scalerank <= ${MAX_RANK}" -points inner -o out.json format=geojson`);
  gj = JSON.parse(res['out.json']);
  // the same polygons, for the check that each rounded point is inside its own
  const shapes = await mapshaper.applyCommands(`-i "${shp}" encoding=utf8 -filter "scalerank <= ${MAX_RANK}" -o out.json format=geojson`);
  polygons = JSON.parse(shapes['out.json']);
} catch (e) {
  stop(`the shapefile could not be read (${e.message}); the builder reads ${FIELDS.join(', ')}`);
}
if (!Array.isArray(gj.features) || !gj.features.length) stop('no polygon of scale rank 3 or less in the shapefile');
if (polygons.features.length !== gj.features.length || polygons.features.some((f, i) => f.properties?.name !== gj.features[i].properties?.name)) {
  stop('the polygons and their label points do not match one to one');
}

for (const f of FIELDS) {
  if (gj.features.some((x) => !x.properties || !(f in x.properties))) stop(`the shapefile has no field "${f}" on every polygon`);
}

const rows = [];
for (const [i, f] of gj.features.entries()) {
  const p = f.properties;
  if (!KEEP.has(p.featurecla)) continue;
  // the oceans take `name`, not `name_en`: the two Atlantic polygons share one name_en and so do the two Pacific ones. Two of the seven
  // (INDIAN OCEAN, SOUTHERN OCEAN) are written in capitals in the file, the other five already in mixed case: all are set in title case
  const n = p.featurecla === 'ocean' ? String(p.name).toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()) : p.name_en || p.name;
  if (!Number.isInteger(p.scalerank) || p.scalerank < 0 || p.scalerank > MAX_RANK) stop(`"${n}" has scalerank ${JSON.stringify(p.scalerank)}`);
  const c = f.geometry?.coordinates;
  if (f.geometry?.type !== 'Point' || !Array.isArray(c) || c.length < 2 || !c.every(Number.isFinite)) stop(`"${n}" has no label point`);
  const placed = roundInside(c, polygons.features[i].geometry);
  if (!placed) stop(`the label point of "${n}" is not inside its polygon at any rounding to 0.001 degree`);
  rows.push({ n, r: p.scalerank, at: placed.at });
}
rows.sort((a, b) => a.r - b.r || (a.n < b.n ? -1 : a.n > b.n ? 1 : 0));

const bracket = rows.find((r) => /[()[\]{}]/.test(r.n));
if (bracket) stop(`the name "${bracket.n}" holds a bracket`);
const seen = new Set();
for (const r of rows) {
  if (!r.n.trim()) stop('a name is empty');
  if (seen.has(r.n)) stop(`the name "${r.n}" comes twice`);
  seen.add(r.n);
}
if (rows.length < MIN_ROWS) stop(`it would write ${rows.length} rows, fewer than ${MIN_ROWS}`);

let tracked = 0;
try {
  tracked = JSON.parse(fs.readFileSync(out, 'utf8')).seas.length;
} catch {
  // no file yet, or one that cannot be read: nothing to protect
}
if (rows.length < tracked && !acceptFewer) stop(`it would write ${rows.length} rows and ${path.relative(repo, out) || out} holds ${tracked} (--accept-fewer overrides)`);

const note = `Natural Earth Physical Labels, marine areas 1:50m, version ${version}, read ${READ_ON}`;
const text = JSON.stringify({ s: SOURCE_ID, n: note, seas: rows });
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, text);
const byRank = [0, 1, 2, 3].map((r) => rows.filter((x) => x.r === r).length).join(', ');
console.log(`${path.relative(repo, out) || out}: ${rows.length} names (rank 0 to 3: ${byRank}), ${Buffer.byteLength(text)} bytes`);
