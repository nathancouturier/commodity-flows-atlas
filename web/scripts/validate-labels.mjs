/**
 * The files the place names of the map read, and nothing else of the map:
 *  - data/geo/seas.json (built by pipeline/geo/build_seas.mjs): the keys of the file, its source, 60 to 120 names with a rank and a
 *    point, no name twice, no bracket in a name, and no name that is also the name of a passage of freight/chokepoints.json (the atlas draws its
 *    passages as markers; a strait must never be named twice);
 *  - data/countries/index.json as the country names read it: a name, a point and a box on every row (a row without them would silently
 *    have no name on the map).
 * validate-data.mjs skips every file under data/geo in its own checks, which is why this one is needed.
 * Called by validate-data.mjs; `node validate-labels.mjs [data folder]` runs it alone.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const MIN_SEAS = 60;
export const MAX_SEAS = 120;
export const MAX_RANK = 3;

const BRACKET = /[()[\]{}]/;
const isObject = (o) => o !== null && typeof o === 'object' && !Array.isArray(o);
const text = (x) => typeof x === 'string' && x.trim() !== '';
const inRange = (p) => Array.isArray(p) && p.length === 2 && p.every((x) => typeof x === 'number' && Number.isFinite(x)) && Math.abs(p[0]) <= 180 && Math.abs(p[1]) <= 90;

export function validateLabels(root, errors) {
  const read = (rel) => JSON.parse(fs.readFileSync(path.join(root, rel), 'utf8'));
  const seasBad = (m) => errors.push(`geo/seas.json: ${m}`);
  const countryBad = (m) => errors.push(`countries/index.json: ${m}`);

  let doc;
  try {
    doc = read('geo/seas.json');
  } catch (e) {
    seasBad(`missing or unreadable (${e.message}); run pipeline/geo/build_seas.mjs`);
  }
  if (doc !== undefined) {
    if (!isObject(doc)) {
      seasBad('not an object');
    } else {
      const keys = Object.keys(doc).sort().join(',');
      if (!['n,s,seas', 'n,s,seas,y'].includes(keys)) seasBad(`the keys are "${Object.keys(doc).join('", "')}", expected s, n, seas and optionally y`);
      if ('y' in doc && !Number.isInteger(doc.y)) seasBad(`y ${JSON.stringify(doc.y)} is not an integer`);
      let sources = [];
      try {
        sources = read('sources.json').map((s) => s.id);
      } catch {
        seasBad('sources.json is missing or unreadable, so the source cannot be checked');
      }
      if (!text(doc.s) || !sources.includes(doc.s)) seasBad(`source ${JSON.stringify(doc.s)} is not an id of sources.json`);
      if (!text(doc.n)) seasBad('"n" (the note: version and day read) is not a non-empty string');
      if (!Array.isArray(doc.seas)) {
        seasBad('"seas" is not a list');
      } else {
        if (doc.seas.length < MIN_SEAS || doc.seas.length > MAX_SEAS) seasBad(`${doc.seas.length} names, expected ${MIN_SEAS} to ${MAX_SEAS}`);
        let passages = new Set();
        try {
          passages = new Set(read('freight/chokepoints.json').map((c) => String(c.name).trim().toLowerCase()));
        } catch {
          seasBad('freight/chokepoints.json is missing or unreadable, so the passage names cannot be compared');
        }
        const seen = new Set();
        doc.seas.forEach((r, i) => {
          const at = `row ${i}${isObject(r) && text(r.n) ? ` (${r.n})` : ''}`;
          if (!isObject(r)) return seasBad(`${at}: not an object`);
          if (Object.keys(r).sort().join(',') !== 'at,n,r') seasBad(`${at}: the keys are "${Object.keys(r).join('", "')}", expected n, r, at`);
          if (!text(r.n)) seasBad(`${at}: the name is empty or not a string`);
          else {
            if (BRACKET.test(r.n)) seasBad(`${at}: the name holds a bracket`);
            if (seen.has(r.n)) seasBad(`${at}: the name comes twice`);
            seen.add(r.n);
            if (passages.has(r.n.trim().toLowerCase())) seasBad(`${at}: the name is also a passage of freight/chokepoints.json`);
          }
          if (!Number.isInteger(r.r) || r.r < 0 || r.r > MAX_RANK) seasBad(`${at}: rank ${JSON.stringify(r.r)} is not an integer from 0 to ${MAX_RANK}`);
          if (!inRange(r.at)) seasBad(`${at}: "at" ${JSON.stringify(r.at)} is not [longitude, latitude] within +-180 and +-90`);
        });
      }
    }
  }

  let index;
  try {
    index = read('countries/index.json');
  } catch (e) {
    return countryBad(`missing or unreadable (${e.message})`);
  }
  if (!Array.isArray(index)) return countryBad('not a list');
  index.forEach((r, i) => {
    const at = `row ${i}${isObject(r) && text(r.c) ? ` (${r.c})` : ''}`;
    if (!isObject(r)) return countryBad(`${at}: not an object`);
    if (!text(r.name)) countryBad(`${at}: no name, so the map would draw none`);
    if (!inRange(r.at)) countryBad(`${at}: "at" ${JSON.stringify(r.at)} is not [longitude, latitude] within +-180 and +-90, so the map would draw no name`);
    if (!Array.isArray(r.bb) || r.bb.length !== 4 || !r.bb.every((x) => typeof x === 'number' && Number.isFinite(x))) countryBad(`${at}: "bb" ${JSON.stringify(r.bb)} is not four finite numbers, so the map would draw no name`);
  });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = path.resolve(process.argv[2] ?? path.join(path.dirname(fileURLToPath(import.meta.url)), '../../data'));
  const errors = [];
  validateLabels(root, errors);
  if (errors.length) {
    console.error(errors.join('\n'));
    process.exit(1);
  }
  console.log('labels OK');
}
