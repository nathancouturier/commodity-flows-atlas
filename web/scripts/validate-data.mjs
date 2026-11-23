/**
 * Validates every JSON file under /data before the site is built:
 *  - each file parses,
 *  - every `s` (source id) referenced anywhere exists in data/sources.json,
 *  - every sourced figure object ({v, s}) also carries a year `y`,
 *  - every chokepoint with a PortWatch counter has a complete weekly series file, and chokepoint-lanes.json only
 *    names chokepoints that exist,
 *  - the lane and pairs files are consistent with each other and with the chokepoints (scripts/validate-freight.mjs),
 *  - the infrastructure files follow their schema (scripts/validate-infra.mjs; every finding is an error, a file in the
 *    old shape gives warnings only with INFRA_OLD_SHAPE=1).
 * Exits non-zero on failure so a broken data commit never reaches the live site.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateFreight } from './validate-freight.mjs';
import { validateInfra, summariseWarnings } from './validate-infra.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../data');
const sources = new Set(JSON.parse(fs.readFileSync(path.join(root, 'sources.json'), 'utf8')).map((s) => s.id));
const errors = [];
let files = 0;

function walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (e.name.endsWith('.json') || e.name.endsWith('.geojson')) check(p);
  }
}

function check(file) {
  files++;
  let doc;
  try {
    doc = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (e) {
    errors.push(`${file}: invalid JSON (${e.message})`);
    return;
  }
  if (file.endsWith('sources.json') || file.includes(`${path.sep}geo${path.sep}`)) return;
  const visit = (o, trail) => {
    if (Array.isArray(o)) return o.forEach((x, i) => visit(x, `${trail}[${i}]`));
    if (!o || typeof o !== 'object') return;
    if (typeof o.s === 'string') {
      if (!sources.has(o.s)) errors.push(`${file}: unknown source "${o.s}" at ${trail}`);
      if ('v' in o && o.y === undefined) errors.push(`${file}: figure without year at ${trail}`);
    }
    for (const [k, v] of Object.entries(o)) visit(v, `${trail}.${k}`);
  };
  visit(doc, '$');
}

/** PortWatch series and the lane table of the chokepoint pages: a weekly job that built too few series, or a
 * build that lost chokepoint-lanes.json, must not pass. */
function checkChokepoints() {
  const read = (rel) => {
    try {
      return JSON.parse(fs.readFileSync(path.join(root, rel), 'utf8'));
    } catch {
      errors.push(`${rel}: missing or unreadable`);
      return null;
    }
  };
  const chk = read('freight/chokepoints.json');
  if (!Array.isArray(chk)) return;
  for (const c of chk) {
    if (!c.portwatch) continue;
    if (!c.traffic || !String(c.traffic.y).startsWith('28 days')) errors.push(`freight/chokepoints.json: ${c.id} has a PortWatch counter but no "28 days" traffic figure`);
    const doc = read(`freight/portwatch/${c.id}.json`);
    if (!doc) continue;
    const blocks = { 'counts': doc, 'vol': doc.vol };
    for (const [name, b] of Object.entries(blocks)) {
      const lens = ['tanker', 'dry', 'container', 'other', 'total'].map((k) => (Array.isArray(b?.[k]) ? b[k].length : -1));
      if (lens.some((n) => n <= 0 || n !== lens[0])) errors.push(`freight/portwatch/${c.id}.json: ${name} series missing or of unequal length (${lens.join(', ')})`);
    }
    if (!doc.annual || !Array.isArray(doc.annual.years)) errors.push(`freight/portwatch/${c.id}.json: no annual block`);
  }
  const lanes = read('freight/chokepoint-lanes.json');
  if (lanes) {
    const known = new Set(chk.map((c) => c.id));
    for (const id of Object.keys(lanes.chokepoints ?? {})) if (!known.has(id)) errors.push(`freight/chokepoint-lanes.json: unknown chokepoint "${id}"`);
  }
}

walk(root);
checkChokepoints();
validateFreight(root, errors);
const infraWarnings = [];
await validateInfra(root, errors, infraWarnings);
if (infraWarnings.length) console.warn(summariseWarnings(infraWarnings));
if (errors.length) {
  console.error(errors.slice(0, 50).join('\n'));
  console.error(`\n${errors.length} data error(s) in ${files} files`);
  process.exit(1);
}
console.log(`data OK: ${files} files`);
