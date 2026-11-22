/**
 * Validates every JSON file under /data before the site is built:
 *  - each file parses,
 *  - every `s` (source id) referenced anywhere exists in data/sources.json,
 *  - every sourced figure object ({v, s}) also carries a year `y`.
 * Exits non-zero on failure so a broken data commit never reaches the live site.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

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

walk(root);
if (errors.length) {
  console.error(errors.slice(0, 50).join('\n'));
  console.error(`\n${errors.length} data error(s) in ${files} files`);
  process.exit(1);
}
console.log(`data OK: ${files} files`);
