/**
 * Before-and-after guard of a data update: compares each data file the job changed with its version in the last
 * commit, and refuses the update (exit 1) when a rebuild looks broken rather than new:
 *  - a table lost more than a tenth of its rows (any list of 10 or more entries, counted per place in the file: the
 *    lines of a country table, the features of a GeoJSON file, the entries of an index),
 *  - a file shrank to less than half its size (files of 1 kB or more),
 *  - a folder lost more than a tenth of its files (folders of 10 or more files),
 *  - a price series (data/prices/<id>.json) whose value at its previous last date was revised by more than half, or,
 *    for a daily or monthly series, whose last value moved by more than half since the last commit (a change of
 *    unit, a wrong column). Annual series are left out of the second test: a yearly price can halve (lithium).
 * The status files (data/_status) are not compared: they are rewritten on every run.
 *
 *    node web/scripts/guard-data.mjs            compare the working tree with HEAD (run by the update jobs)
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

const moved = (a, b) => Math.abs(b - a) > PRICE_MOVE * Math.abs(a);

/** Problems of a price series file between two versions (packed {freq, start|d, v}). */
export function comparePrice(rel, before, after) {
  const out = [];
  if (!Array.isArray(before?.v) || !Array.isArray(after?.v) || before.freq !== after.freq) return out;
  const i0 = lastIndex(before.v);
  const i1 = lastIndex(after.v);
  if (i0 < 0 || i1 < 0) return out;
  const at = periodOf(before, i0);
  const j = indexOf(after, at);
  const old = before.v[i0];
  if (j >= 0 && j < after.v.length && typeof after.v[j] === 'number' && moved(old, after.v[j]))
    out.push(`${rel}: the value of ${at} was revised from ${old} to ${after.v[j]}, by more than half (a change of unit or column?)`);
  if (after.freq !== 'A' && moved(old, after.v[i1]))
    out.push(`${rel}: the last value moved from ${old} to ${after.v[i1]}, by more than half since the last commit`);
  return out;
}

/** Problems between two versions of one data file (texts); `rel` is its path under data/. */
export function compareFile(rel, beforeText, afterText) {
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
  if (/^prices\/[^/]+\.json$/.test(rel) && !/\/(index|figures)\.json$/.test(rel)) out.push(...comparePrice(rel, before, after));
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

/** Compare the data/ folder of the working tree at `repo` with HEAD; returns the list of problems. */
export function guardRepo(repo) {
  try {
    git(['rev-parse', '--verify', 'HEAD'], repo);
  } catch {
    console.log('data guard: no git history here, nothing to compare');
    return [];
  }
  const changed = git(['diff', '--name-only', '--no-renames', 'HEAD', '--', 'data'], repo).split('\n').filter(Boolean);
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
    let before;
    try {
      before = git(['show', `HEAD:${f}`], repo);
    } catch {
      continue; // a new file: nothing to compare with
    }
    problems.push(...compareFile(rel, before, fs.readFileSync(path.join(repo, f), 'utf8')));
  }
  return [...problems, ...compareFolders(folders)];
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
  const problems = guardRepo(repo);
  if (problems.length && (process.env.DATA_GUARD ?? '').toLowerCase() === 'off') {
    console.warn(`data guard: ${problems.length} large change(s) accepted by hand (DATA_GUARD=off):\n${problems.slice(0, 30).join('\n')}`);
  } else if (problems.length) {
    console.error(problems.slice(0, 30).join('\n'));
    console.error(`\ndata guard: ${problems.length} change(s) refused against the last commit; the previous data is kept`);
    process.exit(1);
  } else {
    console.log('data guard OK: no table lost rows, no file shrank, no price jumped');
  }
}
