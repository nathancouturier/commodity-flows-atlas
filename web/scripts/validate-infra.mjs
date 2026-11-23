/**
 * Checks of the infrastructure layer (data/infrastructure/*.geojson), against the schema of
 * pipeline/infrastructure/README.md:
 *  - each feature has id, name, type, c, k, s, url, read, status (and statusAsOf unless the status is "not-stated"),
 *    and a geometry; there is no feature-level `y` (a reading date is never the year of a figure);
 *  - `type`, `status`, the units of `capacity` and `output` and `output.what` are in their vocabularies;
 *    `capacity.y`, `output.y` and `opened` are numbers between 1800 and next year; `read` and `statusAsOf` are dates;
 *  - `k` ids exist in commodities/index.json, `s` exists in sources.json, ids are unique across the eight files;
 *  - coordinates are numbers in range and a point lies inside its country `c` or within 60 km of it. A field, an LNG
 *    terminal or a port may stand at sea (a field offshore, a floating plant, an island terminal): it may lie up to 370 km
 *    (200 nautical miles, the limit of the exclusive economic zone) from `c`, provided no other country is nearer to
 *    it (so a point in the wrong country is still caught). Skipped, with a warning, when the country has no polygon in
 *    geo/countries.topo.json;
 *  - a feature is identified by its type and its id: `type:id` is unique across the eight files (the site draws, selects
 *    and links an asset by `sel=infra:<id>:<type>`); the same id under two types ("ras-tanura", a refinery and a port)
 *    is allowed;
 *  - `note`, `statusNote`, `capacity.n` and `output.n` hold no working-note phrase ("via search", "stripped",
 *    "latest on page", "could not be re-read");
 *  - `coord` is required; a pipeline has `cs`, starting with its country `c`; a feature sits in the file of its type;
 *    a unit fits the type (a refinery in kb/d, an LNG terminal in Mtpa, ...); a status "not-stated" has no `statusAsOf`;
 *    `capacity.planned`, when present, is `true` and belongs to a capacity;
 *  - ports: `locode` is a five-character code and `portwatch` a PortWatch port id; `limits` (a port only) give at least
 *    one of draught, loa, beam (metres) and dwt, with `n`, `s`, `url` and an optional year, `seg` (a segment), `cls` (a
 *    class of that segment), `depth` (true: the draught is a water depth) and `at` (the berth); `maxClass` needs `limits`,
 *    names vessel classes of freight/vessel-classes.json by segment and says its method in `n`; `prices` are ids of
 *    prices/index.json.
 *
 * Every finding about the shape of a feature is an error. Only INFRA_OLD_SHAPE=1 (or `{ tolerateOldShape: true }`)
 * makes a file that is still in the old shape (a feature-level `y`, or no `read`) produce warnings instead, for a
 * data migration that goes one file at a time. STRICT_INFRA=1 is still accepted and changes nothing.
 * Called by validate-data.mjs; `node validate-infra.mjs [data folder]` runs it alone.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const FILES = ['fields', 'refineries', 'lng', 'pipelines', 'mines', 'smelters', 'ports', 'storage'];
const TYPES = ['mine', 'field', 'refinery', 'lng-export', 'lng-import', 'pipeline', 'smelter', 'port', 'storage'];
const STATUSES = ['operating', 'damaged', 'suspended', 'idle', 'construction', 'planned', 'closed', 'not-stated'];
const UNITS = ['kb/d', 'bcm/y', 'Mtpa', 'Mt/y', 'kt/y', 't/y', 'tU/y', 'Mb'];
const WHAT = ['production', 'exports', 'throughput'];
const COORD = ['site', 'approx'];
const WORKING_NOTE = /via search|search summary|stripped|latest on page|re-read|page could not/i;
/** The file each type belongs to, and the units each type may use. */
const FILE_OF = { field: 'fields', refinery: 'refineries', 'lng-export': 'lng', 'lng-import': 'lng', pipeline: 'pipelines', mine: 'mines', smelter: 'smelters', port: 'ports', storage: 'storage' };
const UNITS_OF = {
  field: ['kb/d', 'bcm/y'],
  refinery: ['kb/d'],
  'lng-export': ['Mtpa'],
  'lng-import': ['Mtpa'],
  pipeline: ['kb/d', 'bcm/y'],
  mine: ['Mt/y', 'kt/y', 't/y', 'tU/y'],
  smelter: ['Mt/y', 'kt/y', 't/y'],
  port: ['Mt/y', 'kb/d', 'Mb'],
  storage: ['Mb', 'kb/d'],
};
/** Port limits: metres and deadweight tonnes. */
const LIMIT_KEYS = ['draught', 'loa', 'beam', 'dwt'];
const SEGMENTS = ['dry', 'tanker', 'gas'];
const LOCODE = /^[A-Z]{2}[A-Z0-9]{3}$/;
const PORTWATCH_ID = /^(port|fso)\d+$/;
const NEAR_KM = 60;
/** Types that can stand at sea: they may lie up to 200 nautical miles out (the limit of the exclusive economic zone).
 * A port may be an island or offshore oil terminal (Halul Island, Zirku Island, LOOP). */
const OFFSHORE_TYPES = ['field', 'lng-export', 'lng-import', 'port'];
const OFFSHORE_KM = 370;
const MIN_YEAR = 1800;

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
 * @param opts { tolerateOldShape } a file in the old shape gives warnings, not errors (default: INFRA_OLD_SHAPE=1)
 */
export async function validateInfra(root, errors, warnings, opts = {}) {
  const tolerateOldShape = opts.tolerateOldShape ?? process.env.INFRA_OLD_SHAPE === '1';
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
  const classSegment = new Map((readJson('freight/vessel-classes.json') ?? []).map((v) => [v.id, v.segment]));
  const classes = new Set(classSegment.keys());
  const prices = new Set((readJson('prices/index.json') ?? []).map((m) => m.id));
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
    const soft = legacy && tolerateOldShape;
    const hard = (msg) => errors.push(`${rel}: ${msg}`);
    const shape = (msg) => (soft ? warnings : errors).push(`${rel}: ${msg}${soft ? ' [old shape]' : ''}`);

    for (const [i, f] of doc.features.entries()) {
      const p = f.properties ?? {};
      const at = `${p.id ?? `#${i}`}`;
      for (const k of ['id', 'name', 'type', 'c']) if (typeof p[k] !== 'string' || !p[k]) hard(`${at}: missing "${k}"`);
      if (typeof p.type === 'string' && !TYPES.includes(p.type)) hard(`${at}: type "${p.type}" is not one of ${TYPES.join(', ')}`);
      else if (typeof p.type === 'string' && FILE_OF[p.type] !== name) shape(`${at}: type "${p.type}" belongs in ${FILE_OF[p.type]}.geojson, not in ${name}.geojson`);
      if (!f.geometry) hard(`${at}: no geometry`);
      if (typeof p.id !== 'string') continue;

      // an asset is told apart by its type and its id, across the eight files (the site keeps the first of two equal pairs)
      const ident = `${p.type}:${p.id}`;
      if (seen.has(ident)) shape(`${at}: ${ident} is also in ${seen.get(ident)}: a type and an id identify one asset`);
      else seen.set(ident, name);

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
      else if (p.status === 'not-stated' && p.statusAsOf !== undefined) shape(`${at}: status "not-stated" has no date: remove "statusAsOf"`);
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
        else if (UNITS_OF[p.type] && !UNITS_OF[p.type].includes(g.u)) shape(`${at}: ${key}.u "${g.u}" does not fit a ${p.type} (${UNITS_OF[p.type].join(', ')})`);
        if (key === 'output') {
          if (!isYear(g.y, maxYear)) shape(`${at}: output.y is required and must be a year between ${MIN_YEAR} and ${maxYear}`);
          if (!WHAT.includes(g.what)) shape(`${at}: output.what "${g.what ?? ''}" is not one of ${WHAT.join(', ')}`);
        } else {
          if (g.y !== undefined && !isYear(g.y, maxYear)) shape(`${at}: capacity.y must be a year between ${MIN_YEAR} and ${maxYear} (leave it out when the source does not say)`);
          if (g.what !== undefined) shape(`${at}: capacity has no "what"; production, exports and throughput go in "output"`);
        }
        if (g.planned !== undefined && (key !== 'capacity' || g.planned !== true)) shape(`${at}: "planned" is only \`true\`, on a capacity (a planned or target capacity)`);
        if (typeof g.n === 'string' && WORKING_NOTE.test(g.n)) shape(`${at}: ${key}.n holds a working phrase ("${g.n.match(WORKING_NOTE)[0]}"): notes are for readers`);
        for (const t of ['n', 'orig']) if (g[t] !== undefined && typeof g[t] !== 'string') shape(`${at}: ${key}.${t} must be text`);
      }
      if (!COORD.includes(p.coord)) shape(`${at}: coord "${p.coord ?? ''}" must be "site" or "approx"`);
      if (p.type === 'pipeline') {
        if (p.length_km !== undefined && !(isNum(p.length_km) && p.length_km > 0)) shape(`${at}: length_km must be a positive number`);
        if (!Array.isArray(p.cs) || !p.cs.length) shape(`${at}: a pipeline needs "cs", the countries it crosses, starting with "${p.c}"`);
        else {
          if (p.cs.some((c) => countries.size && !countries.has(c))) shape(`${at}: "cs" must be a list of country codes`);
          if (p.cs[0] !== p.c) shape(`${at}: "cs" must start with the country "${p.c}", not "${p.cs[0]}"`);
        }
      }
      for (const t of ['note', 'statusNote']) {
        if (typeof p[t] === 'string' && WORKING_NOTE.test(p[t])) shape(`${at}: the ${t} holds a working phrase ("${p[t].match(WORKING_NOTE)[0]}"): notes are for readers`);
      }
      // ports: one identity with the trade engine and PortWatch, limits as a page states them, the class derived from them
      if (p.locode !== undefined && !(typeof p.locode === 'string' && LOCODE.test(p.locode))) shape(`${at}: "locode" must be a five-character code (country + place, "RUPRI")`);
      else if (p.locode !== undefined && p.locode.slice(0, 2) === 'XX') shape(`${at}: "locode" has no country`);
      if (p.portwatch !== undefined && !(typeof p.portwatch === 'string' && PORTWATCH_ID.test(p.portwatch))) shape(`${at}: "portwatch" must be a PortWatch port id ("port1020")`);
      if (p.limits !== undefined) {
        const l = p.limits;
        if (p.type !== 'port') shape(`${at}: "limits" belong to a port`);
        if (!l || typeof l !== 'object') shape(`${at}: "limits" must be an object`);
        else {
          const given = LIMIT_KEYS.filter((k) => l[k] !== undefined);
          if (!given.length) shape(`${at}: limits give none of ${LIMIT_KEYS.join(', ')}`);
          for (const k of given) if (!isNum(l[k]) || l[k] <= 0) shape(`${at}: limits.${k} must be a positive number`);
          if (isNum(l.draught) && l.draught > 40) shape(`${at}: limits.draught ${l.draught} is not in metres`);
          if (isNum(l.dwt) && l.dwt < 1000) shape(`${at}: limits.dwt ${l.dwt} is not in deadweight tonnes`);
          if (typeof l.n !== 'string' || !l.n) shape(`${at}: limits.n must say which berth or channel the limits are for`);
          else if (WORKING_NOTE.test(l.n)) shape(`${at}: limits.n holds a working phrase`);
          if (typeof l.s !== 'string' || (sources.size && !sources.has(l.s))) shape(`${at}: limits.s "${l.s ?? ''}" is not a source of sources.json`);
          if (typeof l.url !== 'string' || !/^https?:\/\//.test(l.url)) shape(`${at}: limits.url (the page that states the limits) is missing`);
          if (l.y !== undefined && !isYear(l.y, maxYear)) shape(`${at}: limits.y must be a year between ${MIN_YEAR} and ${maxYear}`);
          if (l.seg !== undefined && !SEGMENTS.includes(l.seg)) shape(`${at}: limits.seg "${l.seg}" is not a segment (${SEGMENTS.join(', ')})`);
          if (l.cls !== undefined) {
            if (classes.size && !classes.has(l.cls)) shape(`${at}: limits.cls "${l.cls}" is not a vessel class`);
            else if (l.seg !== undefined && classSegment.size && classSegment.get(l.cls) !== l.seg) shape(`${at}: limits.cls "${l.cls}" is not a class of the segment "${l.seg}"`);
          }
          if (l.depth !== undefined && !(l.depth === true && isNum(l.draught))) shape(`${at}: limits.depth must be true, and only with a draught (a water depth entered as draught)`);
          if (l.at !== undefined && !(typeof l.at === 'string' && l.at)) shape(`${at}: limits.at must name the berth or terminal`);
          for (const k of Object.keys(l)) if (![...LIMIT_KEYS, 'seg', 'cls', 'depth', 'at', 'n', 's', 'url', 'y'].includes(k)) shape(`${at}: limits.${k} is not a field of limits`);
        }
      }
      if (p.maxClass !== undefined) {
        const m = p.maxClass;
        if (!p.limits) shape(`${at}: "maxClass" is derived from "limits", which the feature lacks`);
        if (!m || typeof m !== 'object' || typeof m.n !== 'string' || !m.n) shape(`${at}: "maxClass" needs "n", the method`);
        else {
          for (const k of Object.keys(m)) {
            if (k === 'n') continue;
            if (!SEGMENTS.includes(k)) shape(`${at}: maxClass.${k} is not a segment (${SEGMENTS.join(', ')})`);
            else if (classes.size && !classes.has(m[k])) shape(`${at}: maxClass.${k} "${m[k]}" is not a vessel class`);
          }
        }
      }
      if (p.prices !== undefined) {
        if (!Array.isArray(p.prices) || !p.prices.length) shape(`${at}: "prices" must be a non-empty list of price series ids`);
        else for (const id of p.prices) if (prices.size && !prices.has(id)) shape(`${at}: price series "${id}" is not in prices/index.json`);
      }

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
          const [x, y] = g.coordinates;
          const offshore = OFFSHORE_TYPES.includes(p.type);
          const limit = offshore ? OFFSHORE_KM : NEAR_KM;
          const km = kmToCountry(cp, x, y, limit);
          if (km > limit) shape(`${at}: the point lies ${Number.isFinite(km) ? `${Math.round(km)} km` : `more than ${limit} km`} from ${p.c} (the limit is ${limit} km)`);
          else if (offshore && km > NEAR_KM) {
            // at sea: allowed only when no other country is nearer than the stated one
            const nearer = [...polys].find(([iso, other]) => iso !== p.c && kmToCountry(other, x, y, km) < km);
            if (nearer) shape(`${at}: the point lies ${Math.round(km)} km from ${p.c} and nearer to ${nearer[0]}: the country may be wrong`);
          }
        }
      }
    }
  }
  if (skipped.size) warnings.push(`infrastructure: no polygon for ${[...skipped].sort().join(', ')}: the country check is skipped for these`);
  if (legacyFiles && tolerateOldShape) warnings.push(`infrastructure: ${legacyFiles} of ${FILES.length} files are still in the old shape (INFRA_OLD_SHAPE=1 is set)`);
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

// node validate-infra.mjs [data folder]   (INFRA_OLD_SHAPE=1 tolerates a file still in the old shape)
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
