/**
 * Validates every JSON file under /data before the site is built:
 *  - each file parses,
 *  - every `s` (source id) referenced anywhere exists in data/sources.json,
 *  - every sourced figure object ({v, s}) also carries a year `y`,
 *  - every chokepoint with a PortWatch counter has a complete weekly series file, and chokepoint-lanes.json only
 *    names chokepoints that exist,
 *  - the price files agree with prices/index.json: ordered dates, range, frequency, source id, breaks and estimate
 *    ranges inside the series, real-price pairs, board statistics equal to the last observation, no orphan file,
 *  - the commodity tables list every country once, largest first, within the world total, and the series by year of
 *    data/commodities/history have one entry per year and end on the table of the page (3 MB budget for them all),
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

/** Price series: index.json and the series files must agree (the site trusts both without looking). */
function checkPrices() {
  const dir = path.join(root, 'prices');
  let idx;
  try {
    idx = JSON.parse(fs.readFileSync(path.join(dir, 'index.json'), 'utf8'));
  } catch {
    errors.push('prices/index.json: missing or unreadable');
    return;
  }
  if (!Array.isArray(idx) || !idx.length) {
    errors.push('prices/index.json: not a list of series');
    return;
  }
  const ym = /^\d{4}-(0[1-9]|1[0-2])$/;
  const ymd = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;
  const ids = new Set();
  const byId = new Map(idx.map((m) => [m.id, m]));
  for (const m of idx) {
    const at = `prices/${m?.id}`;
    if (!m || typeof m.id !== 'string' || !/^[a-z0-9-]+$/.test(m.id)) {
      errors.push(`prices/index.json: a series without a valid id`);
      continue;
    }
    if (ids.has(m.id)) errors.push(`${at}: listed twice`);
    ids.add(m.id);
    for (const f of ['k', 'name', 'unit', 's', 'start', 'end']) if (typeof m[f] !== 'string' || !m[f]) errors.push(`${at}: no ${f}`);
    if (!['D', 'M', 'A'].includes(m.freq)) errors.push(`${at}: frequency ${m.freq}`);
    if (!sources.has(m.s)) errors.push(`${at}: unknown source "${m.s}"`);
    let doc;
    try {
      doc = JSON.parse(fs.readFileSync(path.join(dir, `${m.id}.json`), 'utf8'));
    } catch {
      errors.push(`${at}: listed but its file is missing or unreadable`);
      continue;
    }
    if (doc.id !== m.id || doc.freq !== m.freq) errors.push(`${at}: file says ${doc.id}/${doc.freq}, index says ${m.id}/${m.freq}`);
    const v = doc.v;
    if (!Array.isArray(v) || v.some((x) => x !== null && (typeof x !== 'number' || !Number.isFinite(x)))) {
      errors.push(`${at}: values are not numbers`);
      continue;
    }
    const last = v.length - 1 - [...v].reverse().findIndex((x) => x !== null);
    if (v.every((x) => x === null)) errors.push(`${at}: no value`);
    let first, end;
    if (m.freq === 'D') {
      const d = doc.d;
      if (!Array.isArray(d) || d.length !== v.length) {
        errors.push(`${at}: d and v differ in length`);
        continue;
      }
      if (d.some((x, i) => !Number.isInteger(x) || (i && x <= d[i - 1]))) errors.push(`${at}: days are not strictly increasing`);
      const iso = (n) => new Date(n * 86400000).toISOString().slice(0, 10);
      first = iso(d[0]);
      end = iso(d[d.length - 1]);
      if (!ymd.test(m.start) || !ymd.test(m.end)) errors.push(`${at}: start/end are not YYYY-MM-DD`);
    } else if (m.freq === 'M') {
      if (!ym.test(m.start) || !ym.test(m.end) || doc.start !== m.start) errors.push(`${at}: start/end are not YYYY-MM or differ from the file`);
      else {
        const [y, mo] = m.start.split('-').map(Number);
        const k = y * 12 + mo - 1 + v.length - 1;
        first = m.start;
        end = `${Math.floor(k / 12)}-${String((k % 12) + 1).padStart(2, '0')}`;
      }
    } else {
      if (!/^\d{4}$/.test(m.start) || !/^\d{4}$/.test(m.end) || doc.start !== m.start) errors.push(`${at}: start/end are not YYYY or differ from the file`);
      else {
        first = m.start;
        end = String(Number(m.start) + v.length - 1);
      }
    }
    if (first !== undefined && (first !== m.start || end !== m.end)) errors.push(`${at}: the file runs ${first} to ${end}, the index says ${m.start} to ${m.end}`);
    if (v.length && (v[0] === null || v[v.length - 1] === null)) errors.push(`${at}: starts or ends on an empty value`);
    // the board reads the statistics: they must be about the last observation
    const st = m.stats;
    if (m.freq !== 'A') {
      if (!st || !st.last || st.last.v !== v[last]) errors.push(`${at}: stats.last is not the last value of the file`);
      else if (String(st.last.t).slice(0, m.freq === 'D' ? 10 : 7) !== m.end) errors.push(`${at}: stats.last.t is not the end of the series`);
      if (st && st.rng && !(st.rng.lo <= st.last.v && st.last.v <= st.rng.hi)) errors.push(`${at}: the last value is outside its 52-week range`);
    }
    // breaks, annual runs and estimates must sit inside the series and in order
    const inside = (s) => (m.freq === 'A' ? String(s).slice(0, 4) >= m.start && String(s).slice(0, 4) <= m.end : s >= m.start.slice(0, 7) && s <= m.end.slice(0, 7));
    let prev = '';
    for (const b of m.breaks ?? []) {
      if (!ym.test(b.at) || !inside(b.at) || b.at <= prev || !b.now) errors.push(`${at}: break ${b.at} is out of range, out of order or empty`);
      prev = b.at;
    }
    for (const r of m.annual ?? []) {
      if (!Array.isArray(r) || r[0] > r[1] || String(r[0]) < m.start.slice(0, 4) || String(r[1]) > m.end.slice(0, 4)) errors.push(`${at}: annual run ${r} is out of range`);
    }
    for (const r of m.est ?? []) if (!ym.test(r[0]) || !ym.test(r[1]) || r[0] > r[1] || !inside(r[0])) errors.push(`${at}: estimate range ${r} is out of range`);
    // a real counterpart is an annual series of the same commodity (a daily series points at its monthly benchmark's one)
    if (m.real) {
      const r = byId.get(m.real);
      if (!r || r.freq !== 'A' || r.k !== m.k || !r.realOf) errors.push(`${at}: real counterpart ${m.real} is missing or is not an annual series of ${m.k}`);
    }
    if (m.realOf && (!byId.has(m.realOf) || byId.get(m.realOf).real !== m.id)) errors.push(`${at}: realOf ${m.realOf} is missing or does not point back`);
  }
  for (const f of fs.readdirSync(dir)) if (f.endsWith('.json') && f !== 'index.json' && !ids.has(f.slice(0, -5))) errors.push(`prices/${f}: not listed in index.json`);
}

/** The commodity tables list every country (largest first, each once, lines within the world total) and the series by
 * year of data/commodities/history agree with them: same shape per year, and the latest year is the table of the page. */
function checkCommodityTables() {
  const dir = path.join(root, 'commodities');
  const tablesOf = (d) => [
    ...['production', 'refinery', 'reserves', 'consumption', 'exports', 'imports'].filter((k) => d[k] && typeof d[k] === 'object').map((k) => [k, d[k]]),
    ...(d.extra ?? []).map((x) => [x.key, x.table]),
  ];
  const docs = {};
  for (const f of fs.readdirSync(dir)) {
    if (!f.endsWith('.json') || f === 'index.json' || f === 'companies.json') continue;
    let d;
    try {
      d = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
    } catch {
      continue; // reported by walk()
    }
    docs[f.slice(0, -5)] = d;
    for (const [k, t] of tablesOf(d)) {
      const where = `commodities/${f} ${k}`;
      const rows = Array.isArray(t.rows) ? t.rows : [];
      const seen = new Set();
      let sum = 0;
      rows.forEach((r, i) => {
        if (seen.has(r.c)) errors.push(`${where}: ${r.c} listed twice`);
        seen.add(r.c);
        if (!(typeof r.v === 'number' && r.v > 0)) errors.push(`${where}: row ${r.c} without a positive value`);
        if (i > 0 && r.v > rows[i - 1].v) errors.push(`${where}: rows not in descending order at ${r.c}`);
        sum += r.v;
      });
      if (typeof t.world === 'number' && sum + (t.other ?? 0) > t.world * (1 + 5e-4) + 1e-6) errors.push(`${where}: the lines add up to more than the world total`);
      if (t.hidden && t.hidden.k !== rows.length - t.hidden.from) errors.push(`${where}: hidden.k does not match the rows after the first ${t.hidden.from}`);
    }
  }
  const hdir = path.join(dir, 'history');
  if (!fs.existsSync(hdir)) return;
  let bytes = 0;
  for (const f of fs.readdirSync(hdir)) {
    if (!f.endsWith('.json')) continue;
    const where = `commodities/history/${f}`;
    const txt = fs.readFileSync(path.join(hdir, f), 'utf8');
    bytes += Buffer.byteLength(txt);
    let h;
    try {
      h = JSON.parse(txt);
    } catch {
      continue;
    }
    const id = f.slice(0, -5);
    const d = docs[id];
    if (h.id !== id || !d) {
      errors.push(`${where}: no commodity file for "${h.id}"`);
      continue;
    }
    const tabs = Object.fromEntries(tablesOf(d));
    for (const [k, s] of Object.entries(h.t ?? {})) {
      const w = `${where} ${k}`;
      const n = Array.isArray(s.years) ? s.years.length : 0;
      if (n < 2 || s.years.some((y, i) => !Number.isInteger(y) || (i > 0 && y <= s.years[i - 1]))) errors.push(`${w}: years must be two or more increasing integers`);
      for (const f2 of ['world', 'labels', 'pub', 'other', 'yl']) if (s[f2] !== undefined && (!Array.isArray(s[f2]) || s[f2].length !== n)) errors.push(`${w}: ${f2} is not one entry per year`);
      for (const f2 of ['est', 'srcEst']) for (const [c, ix] of Object.entries(s[f2] ?? {})) if (!s.c?.[c] || ix.some((i) => !(i >= 0 && i < n) || s.c[c][i] == null)) errors.push(`${w}: ${f2} of ${c} names a year without a figure`);
      if ((s.worldEst ?? []).some((i) => !(i >= 0 && i < n))) errors.push(`${w}: worldEst out of range`);
      for (const [c, v] of Object.entries(s.c ?? {})) {
        if (!Array.isArray(v) || v.length !== n) errors.push(`${w}: series of ${c} is not one value per year`);
        else if (v.some((x) => x !== null && !(typeof x === 'number' && x > 0))) errors.push(`${w}: series of ${c} holds a value that is not positive`);
      }
      const t = tabs[k];
      if (!t) {
        errors.push(`${w}: no such table in commodities/${id}.json`);
        continue;
      }
      if (s.u !== t.u || s.s !== t.s) errors.push(`${w}: unit or source differs from the table (${s.u}, ${s.s} against ${t.u}, ${t.s})`);
      const last = n - 1;
      const want = new Map(t.rows.map((r) => [r.c, r.v]));
      const got = Object.entries(s.c ?? {}).filter(([, v]) => v[last] != null);
      if (got.length !== want.size || got.some(([c, v]) => want.get(c) !== v[last]) || s.world?.[last] !== t.world)
        errors.push(`${w}: the latest year of the series is not the table of the page`);
    }
  }
  if (bytes > 3e6) errors.push(`commodities/history: ${(bytes / 1e6).toFixed(2)} MB, above the 3 MB budget`);
}

walk(root);
checkChokepoints();
checkCommodityTables();
checkPrices();
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
