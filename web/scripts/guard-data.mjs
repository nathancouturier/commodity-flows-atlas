/**
 * Before-and-after guard of a data update: compares each data file the job changed with its version in the last
 * commit, and refuses the update (exit 1) when a rebuild looks broken rather than new:
 *  - a table lost more than a tenth of its rows (any list of 10 or more entries, counted per place in the file: the
 *    lines of a country table, the features of a GeoJSON file, the entries of an index),
 *  - a file shrank to less than half its size (files of 1 kB or more),
 *  - a folder lost more than a tenth of its files (folders of 10 or more files),
 *  - a price series (data/prices/<id>.json) whose shape broke: its frequency changed, its days are not one per value
 *    in increasing order, or a value of the last commit is gone (a hole, or a series that ends earlier),
 *  - a price series in a price or index unit whose value at its previous last date was revised by more than half, or,
 *    for a daily or monthly series, whose new values move in one step by more than the series itself has ever moved
 *    in one step (a change of unit, a wrong column). The range is ×0.5 to ×1.5 for a quiet series, widened to the
 *    largest one-period move of the series' history raised to the power SCALE_POWER, and never wider than ×1/5 to ×5,
 *    so a value ten times too large or too small is always refused. Only steps between strictly positive values are
 *    tested. A series whose unit is a deviation (data/prices/index.json: it crosses zero, and its past months can be
 *    revised) is checked on its shape only. Annual series are left out of the step test: a yearly price can halve
 *    (lithium). The replay of the published history is in docs/UPDATING.md.
 *  - the coverage file (data/coverage.json) when a page lost a block that the floor file lists
 *    (pipeline/commodities/coverage_floor.json), unless the last commit already lacked it: a loss accepted by hand is
 *    refused once. This is the one rule that reads a hand-typed file, so it sits here, where "accept large moves"
 *    overrides it, and not in validate-data.mjs, which has no override.
 * The status files (data/_status) are not compared: they are rewritten on every run.
 *
 *    node web/scripts/guard-data.mjs            compare the working tree with HEAD (run by the update jobs)
 *    node web/scripts/guard-data.mjs <path>...  the same, for the files under these paths only (the paths a job owns)
 *
 * A real move that the guard refuses is accepted by running the workflow by hand with "accept large moves"
 * (DATA_GUARD=off in the environment): docs/UPDATING.md. Without git, or without a HEAD, the guard says so and passes.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROW_LOSS = 0.1;
export const MIN_ROWS = 10;
export const SHRINK = 0.5;
export const MIN_BYTES = 1024;
export const PRICE_MOVE = 0.5;
export const SCALE_POWER = 3;
export const MAX_RATIO = 5;
export const COVERAGE_FILE = 'data/coverage.json';
export const COVERAGE_FLOOR = 'pipeline/commodities/coverage_floor.json';

/** {place in the file: number of entries} of every list of the document (indices left out of the place). */
export function rowCounts(doc) {
  const out = new Map();
  const visit = (o, place) => {
    if (Array.isArray(o)) {
      out.set(place, (out.get(place) ?? 0) + o.length);
      for (const x of o) if (x && typeof x === 'object') visit(x, `${place}[]`);
    } else if (o && typeof o === 'object') {
      for (const [k, v] of Object.entries(o)) visit(v, `${place}.${k}`);
    }
  };
  visit(doc, '$');
  return out;
}

const lastIndex = (v) => {
  for (let i = v.length - 1; i >= 0; i--) if (typeof v[i] === 'number') return i;
  return -1;
};

/** Index in a packed series of the period `at` ('YYYY-MM', 'YYYY' or a day number), or -1. */
function indexOf(series, at) {
  if (series.freq === 'D') return Array.isArray(series.d) ? series.d.indexOf(at) : -1;
  const [y0, m0] = String(series.start).split('-').map(Number);
  const [y1, m1] = String(at).split('-').map(Number);
  return series.freq === 'M' ? (y1 - y0) * 12 + (m1 - m0) : y1 - y0;
}

/** Period of index i of a packed series. */
function periodOf(series, i) {
  if (series.freq === 'D') return series.d[i];
  const [y0, m0] = String(series.start).split('-').map(Number);
  if (series.freq === 'M') {
    const m = m0 - 1 + i;
    return `${y0 + Math.floor(m / 12)}-${String((m % 12) + 1).padStart(2, '0')}`;
  }
  return String(y0 + i);
}

/** Period of index i as written in a message (a day as YYYY-MM-DD). */
const labelOf = (series, i) => (series.freq === 'D' ? new Date(series.d[i] * 864e5).toISOString().slice(0, 10) : periodOf(series, i));

const moved = (a, b) => Math.abs(b - a) > PRICE_MOVE * Math.abs(a);

/** A unit measured from zero (a deviation from trend or from average): its moves are not proportional to its level. */
export const isDeviation = (unit) => /deviation/i.test(unit ?? '');

/** Largest |log ratio| between consecutive strictly positive values of a packed series: its own scale of moves. */
export function largestStep(v) {
  let prev = null;
  let m = 0;
  for (const x of v) {
    if (typeof x !== 'number') continue;
    if (prev > 0 && x > 0) m = Math.max(m, Math.abs(Math.log(x / prev)));
    prev = x;
  }
  return m;
}

/** Range [lo, hi] of the ratio a value may move by in one step, after a history whose largest step is `scale`. */
export function stepRange(scale) {
  const hi = Math.min(MAX_RATIO, Math.max(1 + PRICE_MOVE, Math.exp(SCALE_POWER * scale)));
  const lo = Math.max(1 / MAX_RATIO, Math.min(1 - PRICE_MOVE, Math.exp(-SCALE_POWER * scale)));
  return [lo, hi];
}

/** Shape problems of a price series between two versions: frequency, days, values of the last commit that are gone. */
function compareShape(rel, before, after) {
  if (before.freq !== after.freq) return [`${rel}: the frequency changed from ${before.freq} to ${after.freq}`];
  if (before.freq === 'D' && (!Array.isArray(after.d) || after.d.length !== after.v.length || after.d.some((d, i) => i > 0 && !(d > after.d[i - 1]))))
    return [`${rel}: the days are no longer one per value in increasing order`];
  const have = new Set();
  after.v.forEach((x, i) => typeof x === 'number' && have.add(periodOf(after, i)));
  const lost = [];
  before.v.forEach((x, i) => typeof x === 'number' && !have.has(periodOf(before, i)) && lost.push(labelOf(before, i)));
  return lost.length ? [`${rel}: ${lost.length} value(s) of the last commit are missing (from ${lost[0]} to ${lost.at(-1)})`] : [];
}

/** Problems of a price series file between two versions (packed {freq, start|d, v}); `unit` from data/prices/index.json. */
export function comparePrice(rel, before, after, unit) {
  if (!Array.isArray(before?.v) || !Array.isArray(after?.v)) return [];
  const out = compareShape(rel, before, after);
  if (out.length || isDeviation(unit)) return out;
  const i0 = lastIndex(before.v);
  const i1 = lastIndex(after.v);
  if (i0 < 0 || i1 < 0) return out;
  const at = periodOf(before, i0);
  const j = indexOf(after, at);
  const old = before.v[i0];
  if (j < 0 || j >= after.v.length) return out;
  if (typeof after.v[j] === 'number' && old > 0 && after.v[j] > 0 && moved(old, after.v[j]))
    out.push(`${rel}: the value of ${labelOf(before, i0)} was revised from ${old} to ${after.v[j]}, by more than half (a change of unit or column?)`);
  if (after.freq === 'A') return out;
  const [lo, hi] = stepRange(largestStep(before.v));
  let prev = old;
  let from = labelOf(before, i0);
  for (let i = j + 1; i <= i1; i++) {
    const x = after.v[i];
    if (typeof x !== 'number') continue;
    if (prev > 0 && x > 0 && (x / prev > hi || x / prev < lo)) {
      out.push(`${rel}: the value moved from ${prev} (${from}) to ${x} (${labelOf(after, i)}), outside ×${lo.toFixed(2)} to ×${hi.toFixed(2)}, the range of one step of this series`);
      break;
    }
    prev = x;
    from = labelOf(after, i);
  }
  return out;
}

/** Problems between two versions of one data file (texts); `rel` is its path under data/, `units` {series id: unit}. */
export function compareFile(rel, beforeText, afterText, units = new Map()) {
  const out = [];
  const b = Buffer.byteLength(beforeText);
  const a = Buffer.byteLength(afterText);
  if (b >= MIN_BYTES && a < SHRINK * b) out.push(`${rel}: the file shrank from ${b} to ${a} bytes, to less than half`);
  let before;
  let after;
  try {
    before = JSON.parse(beforeText);
    after = JSON.parse(afterText);
  } catch {
    return out; // a file that does not parse is the validator's finding
  }
  const rb = rowCounts(before);
  const ra = rowCounts(after);
  for (const [place, n] of rb) {
    const m = ra.get(place) ?? 0;
    if (n >= MIN_ROWS && m < (1 - ROW_LOSS) * n) out.push(`${rel}: ${place} lost ${n - m} of its ${n} rows, more than a tenth`);
  }
  if (/^prices\/[^/]+\.json$/.test(rel) && !/\/(index|figures)\.json$/.test(rel))
    out.push(...comparePrice(rel, before, after, units.get(path.posix.basename(rel, '.json'))));
  return out;
}

/** {page: {block: cell}} of a data/coverage.json text, or null when it does not read as one. */
function coverageCells(text) {
  try {
    const doc = JSON.parse(text);
    return Object.fromEntries(doc.pages.map((p) => [p.id, p.cells]));
  } catch {
    return null;
  }
}

/**
 * Problems of a rebuilt coverage file against the floor ({"version": 1, "present": {page: [blocks]}}): a block the floor
 * lists that the new file no longer shows as present. A block the last commit's file already lacked is not reported
 * again (a loss accepted by hand, until the floor is lowered). Texts that do not read give no finding: the shape is
 * the validator's.
 */
export function compareCoverage(afterText, floorText, beforeText = null) {
  const after = coverageCells(afterText);
  let floor;
  try {
    floor = JSON.parse(floorText).present;
  } catch {
    return [];
  }
  if (!after || !floor || typeof floor !== 'object') return [];
  const before = beforeText == null ? null : coverageCells(beforeText);
  const out = [];
  for (const [page, blocks] of Object.entries(floor))
    for (const block of blocks) {
      if (after[page]?.[block] === 'p') continue;
      if (before && before[page]?.[block] !== 'p') continue;
      out.push(`${COVERAGE_FILE}: page ${page} lost the block ${block} that ${COVERAGE_FLOOR} lists`);
    }
  return out;
}

/** Problems of the files that left a folder: {folder: [count before, count after]}. */
export function compareFolders(counts) {
  const out = [];
  for (const [dir, [n, m]] of Object.entries(counts))
    if (n >= MIN_ROWS && m < (1 - ROW_LOSS) * n) out.push(`${dir}/: ${n - m} of its ${n} files were removed, more than a tenth`);
  return out;
}

function git(args, cwd) {
  return execFileSync('git', args, { cwd, encoding: 'utf8', maxBuffer: 1 << 28, stdio: ['ignore', 'pipe', 'ignore'] });
}

/** {series id: unit} of data/prices/index.json, from the working tree or else from HEAD (empty when neither reads). */
function priceUnits(repo) {
  const rel = 'data/prices/index.json';
  for (const read of [() => fs.readFileSync(path.join(repo, rel), 'utf8'), () => git(['show', `HEAD:${rel}`], repo)]) {
    try {
      const doc = JSON.parse(read());
      const list = Array.isArray(doc) ? doc : (doc.series ?? []);
      return new Map(list.map((s) => [s.id, s.unit]));
    } catch {
      // try the next version
    }
  }
  return new Map();
}

/** Compare the data/ folder of the working tree at `repo` (or the part of it under `paths`) with HEAD; returns the list of problems. */
export function guardRepo(repo, paths = []) {
  try {
    git(['rev-parse', '--verify', 'HEAD'], repo);
  } catch {
    console.log('data guard: no git history here, nothing to compare');
    return [];
  }
  const changed = git(['diff', '--name-only', '--no-renames', 'HEAD', '--', ...(paths.length ? paths : ['data'])], repo)
    .split('\n')
    .filter((f) => f.startsWith('data/'));
  const units = priceUnits(repo);
  const problems = [];
  const folders = {};
  for (const f of changed) {
    if (f.startsWith('data/_status/') || !/\.(json|geojson)$/.test(f)) continue;
    const rel = f.slice('data/'.length);
    const dir = path.posix.dirname(f);
    if (!fs.existsSync(path.join(repo, f))) {
      if (!folders[dir]) {
        const n = git(['ls-tree', '--name-only', 'HEAD', `${dir}/`], repo).split('\n').filter(Boolean).length;
        const m = fs.existsSync(path.join(repo, dir)) ? fs.readdirSync(path.join(repo, dir)).length : 0;
        folders[dir] = [n, m];
      }
      continue;
    }
    let before = null;
    try {
      before = git(['show', `HEAD:${f}`], repo);
    } catch {
      // a new file: nothing to compare with, except the floor
    }
    const after = fs.readFileSync(path.join(repo, f), 'utf8');
    if (f === COVERAGE_FILE) {
      const floor = path.join(repo, COVERAGE_FLOOR);
      if (fs.existsSync(floor)) problems.push(...compareCoverage(after, fs.readFileSync(floor, 'utf8'), before));
    }
    if (before !== null) problems.push(...compareFile(rel, before, after, units));
  }
  return [...problems, ...compareFolders(folders)];
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
  const problems = guardRepo(repo, process.argv.slice(2));
  if (problems.length && (process.env.DATA_GUARD ?? '').toLowerCase() === 'off') {
    console.warn(`data guard: ${problems.length} large change(s) accepted by hand (DATA_GUARD=off):\n${problems.slice(0, 30).join('\n')}`);
  } else if (problems.length) {
    console.error(problems.slice(0, 30).join('\n'));
    console.error(`\ndata guard: ${problems.length} change(s) refused against the last commit; the previous data is kept`);
    process.exit(1);
  } else {
    console.log('data guard OK: no table lost rows, no file shrank, no price jumped, no page lost a block');
  }
}
