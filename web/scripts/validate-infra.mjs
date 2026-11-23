/**
 * Checks of the infrastructure layer (data/infrastructure/*.geojson), against the schema of
 * pipeline/infrastructure/README.md:
 *  - each feature has id, name, type, c, k, s, url, read, status (and statusAsOf unless the status is "not-stated"),
 *    and a geometry; there is no feature-level `y` (a reading date is never the year of a figure);
 *  - `type`, `status`, the units of `capacity` and `output` and `output.what` are in their vocabularies;
 *    `capacity.y`, `output.y` and `opened` are numbers between 1850 and next year; `read` and `statusAsOf` are dates;
 *  - `k` ids exist in commodities/index.json, `s` exists in sources.json, ids are unique across the seven files;
 *  - coordinates are numbers in range and a point lies inside its country `c` or within 60 km of it (370 km for a
 *    field, which may be offshore; skipped, with a warning, when the country has no polygon in geo/countries.topo.json);
 *  - `note` holds no working-note phrase ("via search", "stripped", "latest on page").
 *
 * A file that is still in the old shape (a feature-level `y`, or no `read`) produces warnings, not errors, so that the
 * data packages can migrate one file at a time. STRICT_INFRA=1 turns every warning into an error.
 * Called by validate-data.mjs; `node validate-infra.mjs [data folder]` runs it alone.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const FILES = ['fields', 'refineries', 'lng', 'pipelines', 'mines', 'smelters', 'ports'];
const TYPES = ['mine', 'field', 'refinery', 'lng-export', 'lng-import', 'pipeline', 'smelter', 'port'];
const STATUSES = ['operating', 'damaged', 'suspended', 'idle', 'construction', 'planned', 'closed', 'not-stated'];
const UNITS = ['kb/d', 'bcm/y', 'Mtpa', 'Mt/y', 'kt/y', 't/y', 'tU/y'];
const WHAT = ['production', 'exports', 'throughput'];
const COORD = ['site', 'approx'];
const WORKING_NOTE = /via search|stripped|latest on page/i;
const NEAR_KM = 60;
/** Fields can be offshore: they may lie up to 200 nautical miles out (the limit of the exclusive economic zone). */
const FIELD_KM = 370;
const MIN_YEAR = 1850;

const isNum = (x) => typeof x === 'number' && Number.isFinite(x);
const isYear = (x, max) => isNum(x) && Number.isInteger(x) && x >= MIN_YEAR && x <= max;
const READ = /^\d{4}-(0[1-9]|1[0-2])$/;
const AS_OF = /^\d{4}(-(0[1-9]|1[0-2]))?$/;

// ---------------------------------------------------------------- country polygons (for the "point in its country" check)

async function countryRings(root, warnings) {
  let topology;
  let feature;
  try {
    topology = JSON.parse(fs.readFileSync(path.join(root, 'geo/countries.topo.json'), 'utf8'));
    ({ feature } = await import('topojson-client'));
  } catch (e) {
    warnings.push(`infrastructure: no country polygons available (${e.code ?? e.message}), the "point inside its country" check is skipped`);
    return null;
  }
  const fc = feature(topology, topology.objects.countries);
  const byIso = new Map();
  for (const f of fc.features) {
    const iso = f.properties?.c;
    if (!iso || !f.geometry) continue;
    const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.type === 'MultiPolygon' ? f.geometry.coordinates : [];
    byIso.set(iso, polys.map((rings) => ({ rings, box: boxOf(rings[0]) })));
  }
  return byIso;
}

function boxOf(ring) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [x, y] of ring) {
    if (x < x0) x0 = x;
    if (x > x1) x1 = x;
    if (y < y0) y0 = y;
    if (y > y1) y1 = y;
  }
  return [x0, y0, x1, y1];
}

function inRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Distance in km from a point to a segment, on a local flat projection (good to a few percent at 60 km). */
function segKm(px, py, ax, ay, bx, by) {
  const kx = 111.32 * Math.cos((py * Math.PI) / 180);
  const ky = 110.57;
  const x = (px - ax) * kx, y = (py - ay) * ky;
  const dx = (bx - ax) * kx, dy = (by - ay) * ky;
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, (x * dx + y * dy) / len2)) : 0;
  return Math.hypot(x - t * dx, y - t * dy);
}

/** Km from a point to the country (0 when inside); Infinity when clearly farther than the limit + margin. */
export function kmToCountry(polys, x, y, limit = NEAR_KM) {
  const padY = (limit + 5) / 110.57;
  const padX = (limit + 5) / Math.max(111.32 * Math.cos((y * Math.PI) / 180), 1);
  let best = Infinity;
  for (const { rings, box } of polys) {
    if (x < box[0] - padX || x > box[2] + padX || y < box[1] - padY || y > box[3] + padY) continue;
    if (inRing(x, y, rings[0]) && !rings.slice(1).some((h) => inRing(x, y, h))) return 0;
    for (const ring of rings) for (let i = 1; i < ring.length; i++) best = Math.min(best, segKm(x, y, ring[i - 1][0], ring[i - 1][1], ring[i][0], ring[i][1]));
  }
  return best;
}

// ---------------------------------------------------------------- the checks

/**
 * @param root data folder
 * @param errors array that receives the errors
 * @param warnings array that receives the warnings
 * @param opts { strict } warnings become errors
 */
export async function validateInfra(root, errors, warnings, opts = {}) {
  const strict = opts.strict ?? process.env.STRICT_INFRA === '1';
  const readJson = (rel) => {
    try {
      return JSON.parse(fs.readFileSync(path.join(root, rel), 'utf8'));
    } catch {
      return null;
    }
  };
  const dir = path.join(root, 'infrastructure');
  if (!fs.existsSync(dir)) return;
  const commodities = new Set((readJson('commodities/index.json') ?? []).map((c) => c.id));
  const sources = new Set((readJson('sources.json') ?? []).map((s) => s.id));
  const countries = new Set((readJson('countries/index.json') ?? []).map((c) => c.c));
  const polys = await countryRings(root, warnings);
  const maxYear = new Date().getFullYear() + 1;
  const seen = new Map();
  let skipped = new Set();
  let legacyFiles = 0;

  for (const name of FILES) {
    const rel = `infrastructure/${name}.geojson`;
    const doc = readJson(rel);
    if (!doc) {
      errors.push(`${rel}: missing or unreadable`);
      continue;
    }
    if (!Array.isArray(doc.features)) {
      errors.push(`${rel}: no features array`);
      continue;
    }
    // a file is still in the old shape while one of its features has a feature-level year or no `read`
    const legacy = doc.features.some((f) => f.properties && ('y' in f.properties || f.properties.read === undefined));
    if (legacy) legacyFiles++;
    const soft = legacy && !strict;
    const hard = (msg) => errors.push(`${rel}: ${msg}`);
    const shape = (msg) => (soft ? warnings : errors).push(`${rel}: ${msg}${soft ? ' [old shape]' : ''}`);

    for (const [i, f] of doc.features.entries()) {
      const p = f.properties ?? {};
      const at = `${p.id ?? `#${i}`}`;
      for (const k of ['id', 'name', 'type', 'c']) if (typeof p[k] !== 'string' || !p[k]) hard(`${at}: missing "${k}"`);
      if (typeof p.type === 'string' && !TYPES.includes(p.type)) hard(`${at}: type "${p.type}" is not one of ${TYPES.join(', ')}`);
      if (!f.geometry) hard(`${at}: no geometry`);
      if (typeof p.id !== 'string') continue;

      // ids are unique across the seven files
      if (seen.has(p.id)) shape(`${at}: id also used in ${seen.get(p.id)}`);
      else seen.set(p.id, name);

      if ('y' in p) shape(`${at}: has a feature-level "y" (the reading date is "read", each figure has its own year)`);
      if (!Array.isArray(p.k) || !p.k.length) shape(`${at}: "k" must be a non-empty list of commodity ids`);
      else for (const k of p.k) if (commodities.size && !commodities.has(k)) shape(`${at}: commodity "${k}" is not in commodities/index.json`);
      if (typeof p.s !== 'string' || !p.s) shape(`${at}: no source id "s"`);
      else if (sources.size && !sources.has(p.s)) hard(`${at}: unknown source "${p.s}"`);
      if (typeof p.url !== 'string' || !/^https?:\/\//.test(p.url)) shape(`${at}: "url" (the page that supports the figures) is missing`);
      if (typeof p.read !== 'string' || !READ.test(p.read)) shape(`${at}: "read" must be "YYYY-MM"`);
      if (countries.size && typeof p.c === 'string' && !countries.has(p.c)) shape(`${at}: country "${p.c}" is not in countries/index.json`);

      // status
      if (!STATUSES.includes(p.status)) shape(`${at}: status "${p.status ?? ''}" is not one of ${STATUSES.join(', ')}`);
      else if (p.status !== 'not-stated' && (typeof p.statusAsOf !== 'string' || !AS_OF.test(p.statusAsOf))) shape(`${at}: status "${p.status}" needs "statusAsOf" ("YYYY" or "YYYY-MM")`);
      if (p.statusAsOf !== undefined && !(typeof p.statusAsOf === 'string' && AS_OF.test(p.statusAsOf))) shape(`${at}: "statusAsOf" must be "YYYY" or "YYYY-MM"`);
      if (p.statusNote !== undefined && typeof p.statusNote !== 'string') shape(`${at}: "statusNote" must be text`);

      // figures
      if (p.opened !== undefined && !isYear(p.opened, maxYear)) shape(`${at}: "opened" must be a year between ${MIN_YEAR} and ${maxYear}`);
      for (const key of ['capacity', 'output']) {
        const g = p[key];
        if (g === undefined) continue;
        if (!g || typeof g !== 'object') {
          shape(`${at}: "${key}" must be an object`);
          continue;
        }
        if (!isNum(g.v) || g.v <= 0) shape(`${at}: ${key}.v must be a positive number`);
        if (!UNITS.includes(g.u)) shape(`${at}: ${key}.u "${g.u}" is not one of ${UNITS.join(', ')}`);
        if (key === 'output') {
          if (!isYear(g.y, maxYear)) shape(`${at}: output.y is required and must be a year between ${MIN_YEAR} and ${maxYear}`);
          if (!WHAT.includes(g.what)) shape(`${at}: output.what "${g.what ?? ''}" is not one of ${WHAT.join(', ')}`);
        } else {
          if (g.y !== undefined && !isYear(g.y, maxYear)) shape(`${at}: capacity.y must be a year between ${MIN_YEAR} and ${maxYear} (leave it out when the source does not say)`);
          if (g.what !== undefined) shape(`${at}: capacity has no "what"; production, exports and throughput go in "output"`);
        }
        for (const t of ['n', 'orig']) if (g[t] !== undefined && typeof g[t] !== 'string') shape(`${at}: ${key}.${t} must be text`);
      }
      if (p.coord !== undefined && !COORD.includes(p.coord)) shape(`${at}: coord "${p.coord}" is not "site" or "approx"`);
      if (p.type === 'pipeline') {
        if (p.length_km !== undefined && !(isNum(p.length_km) && p.length_km > 0)) shape(`${at}: length_km must be a positive number`);
        if (p.cs !== undefined && (!Array.isArray(p.cs) || p.cs.some((c) => countries.size && !countries.has(c)))) shape(`${at}: "cs" must be a list of country codes`);
      }
      if (typeof p.note === 'string' && WORKING_NOTE.test(p.note)) shape(`${at}: the note holds a working phrase ("${p.note.match(WORKING_NOTE)[0]}"): notes are for readers`);

      // coordinates
      const g = f.geometry;
      if (!g) continue;
      const pts = g.type === 'Point' ? [g.coordinates] : g.type === 'LineString' ? g.coordinates : g.type === 'MultiLineString' ? g.coordinates.flat() : null;
      if (!pts) {
        hard(`${at}: geometry ${g.type} is not a Point, LineString or MultiLineString`);
        continue;
      }
      if (pts.some((c) => !Array.isArray(c) || !isNum(c[0]) || !isNum(c[1]) || Math.abs(c[0]) > 180 || Math.abs(c[1]) > 90)) {
        shape(`${at}: a coordinate is not a number in range [lon -180..180, lat -90..90]`);
        continue;
      }
      if (g.type === 'Point' && polys && typeof p.c === 'string') {
        const cp = polys.get(p.c);
        if (!cp) skipped.add(p.c);
        else {
          const limit = p.type === 'field' ? FIELD_KM : NEAR_KM;
          const km = kmToCountry(cp, g.coordinates[0], g.coordinates[1], limit);
          if (km > limit) shape(`${at}: the point lies ${Number.isFinite(km) ? `${Math.round(km)} km` : `more than ${limit} km`} from ${p.c} (the limit is ${limit} km)`);
        }
      }
    }
  }
  if (skipped.size) warnings.push(`infrastructure: no polygon for ${[...skipped].sort().join(', ')}: the country check is skipped for these`);
  if (legacyFiles) warnings.push(`infrastructure: ${legacyFiles} of ${FILES.length} files are still in the old shape; STRICT_INFRA=1 turns these warnings into errors`);
}

/** Warnings as a short text: the count per kind of message, then a few examples. */
export function summariseWarnings(warnings, examples = 6) {
  const kinds = new Map();
  for (const w of warnings) {
    const kind = w.replace(/^[^:]+: [^:]+: /, '').replace(/"[^"]*"/g, '"…"').replace(/\d+ km/, 'N km');
    kinds.set(kind, (kinds.get(kind) ?? 0) + 1);
  }
  const lines = [...kinds.entries()].sort((a, b) => b[1] - a[1]).map(([k, n]) => `  ${String(n).padStart(4)} x ${k}`);
  return `${warnings.length} warning(s):\n${lines.join('\n')}\nexamples:\n${warnings.slice(0, examples).map((w) => `  ${w}`).join('\n')}`;
}

// node validate-infra.mjs [data folder]   (STRICT_INFRA=1 for the final check)
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = path.resolve(process.argv[2] ?? path.join(path.dirname(fileURLToPath(import.meta.url)), '../../data'));
  const errors = [];
  const warnings = [];
  await validateInfra(root, errors, warnings);
  if (warnings.length) console.warn(summariseWarnings(warnings, process.env.ALL ? warnings.length : 6));
  if (errors.length) {
    console.error(errors.slice(0, 50).join('\n'));
    console.error(`\n${errors.length} infrastructure error(s)`);
    process.exit(1);
  }
  console.log('infrastructure OK');
}
