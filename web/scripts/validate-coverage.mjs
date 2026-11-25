/**
 * Shape of data/coverage.json (built by pipeline/commodities/build_coverage.py), and nothing else:
 *  - the keys of the file, the version, the release number;
 *  - the blocks (unique ids, a label and a text, the families that can have the block);
 *  - the reasons (an object keyed by id: a state `na` or `nofree` and a text);
 *  - one row per page of commodities/index.json and no other, with one cell for each block the page's family can
 *    have and no other; a cell is `p`, `m`, `na:<reason>` or `nf:<reason>`, and the reason it names exists with the
 *    matching state;
 *  - the work list names pages of the index and blocks that are missing on them.
 * What the cells say about the data (a page that lost a block, a reason on a block that is present) is not checked
 * here: this check has no override and a failure of it discards the update of every path of a job. The floor is
 * checked by guard-data.mjs, which "accept large moves" overrides, and by the tests of pipeline/tests.
 * Called by validate-data.mjs and by update_annual.py after it builds the file (a file of the wrong shape is not
 * kept, so that this check never refuses a whole update); `node validate-coverage.mjs [data folder]` runs it alone.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const STATES = { na: 'na', nf: 'nofree' };
const ID = /^[a-z0-9]+(-[a-z0-9]+)*$/;

export function validateCoverage(root, errors) {
  const bad = (m) => errors.push(`coverage.json: ${m}`);
  const read = (rel) => JSON.parse(fs.readFileSync(path.join(root, rel), 'utf8'));
  const isObject = (o) => o !== null && typeof o === 'object' && !Array.isArray(o);
  const text = (x) => typeof x === 'string' && x.trim() !== '';
  let doc;
  let index;
  try {
    doc = read('coverage.json');
  } catch (e) {
    return bad(`missing or unreadable (${e.message}); run pipeline/commodities/build_coverage.py`);
  }
  try {
    index = read('commodities/index.json');
  } catch {
    return bad('commodities/index.json is missing or unreadable, so the pages cannot be compared');
  }
  if (!isObject(doc)) return bad('not an object');
  for (const k of ['version', 'release', 'blocks', 'reasons', 'pages', 'work'])
    if (!(k in doc)) bad(`no "${k}"`);
  if (doc.version !== 1) bad(`version ${JSON.stringify(doc.version)} is not 1`);
  if (!Number.isInteger(doc.release) || doc.release < 1) bad(`release ${JSON.stringify(doc.release)} is not a release number`);
  if (!Array.isArray(doc.blocks) || !Array.isArray(doc.pages) || !isObject(doc.reasons) || !isObject(doc.work)) return bad('"blocks" and "pages" are lists, "reasons" and "work" are objects');
  const families = new Set(index.map((p) => p.family));

  const blocks = new Map();
  for (const b of doc.blocks) {
    if (!isObject(b) || !ID.test(b.id ?? '') || !text(b.label) || !text(b.text)) {
      bad(`a block without an id, a label and a text: ${JSON.stringify(b)?.slice(0, 80)}`);
      continue;
    }
    if (blocks.has(b.id)) bad(`block ${b.id} is listed twice`);
    const fam = b.families;
    if (fam !== undefined && (!Array.isArray(fam) || !fam.length || fam.some((f) => !families.has(f))))
      bad(`block ${b.id}: "families" must list families of commodities/index.json`);
    blocks.set(b.id, Array.isArray(fam) ? fam : null);
  }

  for (const [id, r] of Object.entries(doc.reasons)) {
    if (!ID.test(id)) bad(`reason "${id}" is not an id`);
    if (!isObject(r) || !['na', 'nofree'].includes(r.st) || !text(r.t)) bad(`reason ${id} needs a state (na or nofree) and a text`);
  }

  const byId = new Map(index.map((p) => [p.id, p]));
  const seen = new Set();
  const cellOf = new Map();
  for (const row of doc.pages) {
    const id = row?.id;
    const page = byId.get(id);
    if (!page) {
      bad(`row "${id}" is not a page of commodities/index.json`);
      continue;
    }
    if (seen.has(id)) bad(`page ${id} has two rows`);
    seen.add(id);
    if (!isObject(row.cells)) {
      bad(`page ${id}: no cells`);
      continue;
    }
    cellOf.set(id, row.cells);
    const expected = [...blocks].filter(([, fam]) => !fam || fam.includes(page.family)).map(([b]) => b);
    for (const b of expected) if (!(b in row.cells)) bad(`page ${id}: no cell for ${b}`);
    for (const [b, c] of Object.entries(row.cells)) {
      if (!blocks.has(b)) {
        bad(`page ${id}: cell for ${b}, which is not a block`);
        continue;
      }
      if (!expected.includes(b)) bad(`page ${id}: cell for ${b}, a block its family cannot have`);
      const m = /^(?:(p|m)|(na|nf):(.+))$/.exec(typeof c === 'string' ? c : '');
      if (!m) {
        bad(`page ${id}: ${b} is ${JSON.stringify(c)}, not p, m, na:<reason> or nf:<reason>`);
        continue;
      }
      if (m[2]) {
        const r = doc.reasons[m[3]];
        if (!r) bad(`page ${id}: ${b} names the reason "${m[3]}", which does not exist`);
        else if (r.st !== STATES[m[2]]) bad(`page ${id}: ${b} is ${m[2]}: but the reason "${m[3]}" is ${r.st}`);
      }
    }
  }
  for (const id of byId.keys()) if (!seen.has(id)) bad(`page ${id} has no row`);

  for (const [id, list] of Object.entries(doc.work)) {
    const cells = cellOf.get(id);
    if (!cells) {
      bad(`the work list names ${id}, which has no row`);
      continue;
    }
    if (!Array.isArray(list) || !list.length) bad(`work list of ${id}: no blocks`);
    else for (const b of list) if (cells[b] !== 'm') bad(`work list of ${id}: ${b} is not a missing block`);
  }
}

// node validate-coverage.mjs [data folder]
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = path.resolve(process.argv[2] ?? path.join(path.dirname(fileURLToPath(import.meta.url)), '../../data'));
  const errors = [];
  validateCoverage(root, errors);
  if (errors.length) {
    console.error(errors.slice(0, 50).join('\n'));
    // the last line is what update_annual.py records when it refuses the file: the first finding says what is wrong
    console.error(`\n${errors.length} coverage error(s), the first: ${errors[0]}`);
    process.exit(1);
  }
  console.log('coverage OK');
}
