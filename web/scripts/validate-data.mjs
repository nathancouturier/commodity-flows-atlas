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
 *    data/commodities/history have one entry per year and end on the table of the page (3.4 MB budget for them all),
 *  - every country of the index has a profile file (data/countries/profiles/<ISO3>.json), and no other file is there,
 *    with data or with the words for a territory that has none; shares, ranks, series by year (their years in the one
 *    shared file countries/years.json), partners, passages and the basket are within their bounds; a country file stays
 *    under 400 kB,
 *  - the lane and pairs files are consistent with each other and with the chokepoints (scripts/validate-freight.mjs),
 *  - the port index of the search field is consistent with the pairs and lane files (scripts/validate-ports.mjs),
 *  - the infrastructure files follow their schema (scripts/validate-infra.mjs; every finding is an error, a file in the
 *    old shape gives warnings only with INFRA_OLD_SHAPE=1),
 *  - ranges in every file: coordinates of GeoJSON geometries and of `lat`/`lon` pairs on the globe (a swapped pair is
 *    caught; a line may run past 180 degrees of longitude where it crosses the antimeridian), shares (`share`, `estShare`, `shareDest`) between 0 and 1, the year `y` of a figure between 1950 and two
 *    years from now (prices excepted: their `y` is not a year), and every three-letter country code `c` in
 *    countries/index.json or places.json.
 * The comparison with the previous commit (a table that lost rows, a price that jumped) is scripts/guard-data.mjs.
 * Exits non-zero on failure so a broken data commit never reaches the live site.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateFreight } from './validate-freight.mjs';
import { validatePorts } from './validate-ports.mjs';
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
    let prevNow = null;
    for (const b of m.breaks ?? []) {
      if (!ym.test(b.at) || !inside(b.at) || b.at <= prev || !b.now) errors.push(`${at}: break ${b.at} is out of range, out of order or empty`);
      // the breaks form a chain: what a break replaces is what the previous one introduced
      if (prevNow !== null && b.before !== prevNow) errors.push(`${at}: break ${b.at} replaces "${b.before}", the previous break introduced "${prevNow}"`);
      prev = b.at;
      prevNow = b.now;
    }
    // an index is 100 in its base year: the mean of the twelve months (the value, for an annual series) is 100 once rounded
    if (/^index \(2010 = 100\)$/.test(m.unit) && m.freq !== 'D') {
      const at2010 = [];
      for (let i = 0; i < v.length; i++) {
        const y = m.freq === 'M' ? Number(m.start.slice(0, 4)) + Math.floor((Number(m.start.slice(5, 7)) - 1 + i) / 12) : Number(m.start) + i;
        if (y === 2010 && v[i] !== null) at2010.push(v[i]);
      }
      const want = m.freq === 'M' ? 12 : 1;
      const mean = at2010.reduce((a, b) => a + b, 0) / (at2010.length || 1);
      if (at2010.length !== want || mean < 99.5 || mean > 100.5) errors.push(`${at}: an index (2010 = 100) averages ${mean.toFixed(2)} over 2010 (${at2010.length} values)`);
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
  for (const f of fs.readdirSync(dir)) if (f.endsWith('.json') && f !== 'index.json' && f !== 'figures.json' && !ids.has(f.slice(0, -5))) errors.push(`prices/${f}: not listed in index.json`);
  checkPriceFigures(dir, idx);
}

/** figures.json is what a commodity page loads instead of the index: one entry per commodity, copied from the first
 * live series of the index; a commodity with a daily or monthly series never opens on an annual one. */
function checkPriceFigures(dir, idx) {
  let figures;
  try {
    figures = JSON.parse(fs.readFileSync(path.join(dir, 'figures.json'), 'utf8'));
  } catch {
    errors.push('prices/figures.json: missing or unreadable');
    return;
  }
  const rank = { D: 0, M: 1, A: 2 };
  const first = new Map();
  for (const m of idx) if (!m.hidden && !first.has(m.k)) first.set(m.k, m);
  for (const [k, m] of first) {
    if (k === 'index' || k === 'freight' || m.fam) continue;
    const best = Math.min(...idx.filter((x) => x.k === k && !x.hidden).map((x) => rank[x.freq]));
    if (rank[m.freq] !== best) errors.push(`prices/index.json: ${k} opens on ${m.id}, an annual series, although it has a daily or monthly one`);
  }
  const live = new Map();
  for (const m of idx) if (!m.hidden && !m.closed && m.stats && m.k !== 'freight' && !m.fam && !live.has(m.k)) live.set(m.k, m);
  // a commodity whose only series is closed (barley and sorghum, which the World Bank stopped in 2020) keeps its closed series as its figure
  for (const m of idx) if (!m.hidden && m.closed && m.stats && m.k !== 'freight' && !m.fam && !live.has(m.k)) live.set(m.k, m);
  for (const [k, m] of live) {
    const f = figures[k];
    if (!f) errors.push(`prices/figures.json: no figure for ${k}`);
    else if (f.id !== m.id || Object.entries(f).some(([a, b]) => JSON.stringify(b) !== JSON.stringify(m[a]))) errors.push(`prices/figures.json: the figure of ${k} is not the first series of the index (${m.id})`);
  }
  for (const k of Object.keys(figures)) if (!live.has(k)) errors.push(`prices/figures.json: ${k} has no series in the index`);
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
      // a caveat that holds in some years only names them; `caveatPast` replaces it in the others
      if ((t.caveatYears !== undefined || t.caveatPast !== undefined) && !t.caveat) errors.push(`${where}: caveatYears or caveatPast without a caveat`);
      if (t.caveatYears !== undefined && (!Array.isArray(t.caveatYears) || !t.caveatYears.length || t.caveatYears.some((y) => !Number.isInteger(y))))
        errors.push(`${where}: caveatYears must be a list of years`);
      if (t.caveatPast !== undefined && !(typeof t.caveatPast === 'string' && t.caveatPast)) errors.push(`${where}: caveatPast must be a sentence`);
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
      // an out-of-line value is a published value with its flag, never in the latest year (the table of the page)
      for (const [c, ix] of Object.entries(s.out ?? {}))
        if (!s.c?.[c] || ix.some((i) => !(i > 0 && i < n - 1) || s.c[c][i] == null)) errors.push(`${w}: out of ${c} names a year without a figure, or an end year`);
      if (s.out && JSON.stringify(s.worldOut) !== JSON.stringify([...new Set(Object.values(s.out).flat())].sort((a, b) => a - b))) errors.push(`${w}: worldOut does not list the years of out`);
      for (const [c, v] of Object.entries(s.cl ?? {})) if (!s.c?.[c] || !Array.isArray(v) || v.length !== n) errors.push(`${w}: cl of ${c} is not one label per year`);
      for (const [c, ix] of Object.entries(s.brk ?? {})) if (!s.c?.[c] || ix.some((i) => !(i > 0 && i < n))) errors.push(`${w}: brk of ${c} out of range`);
      if (s.n !== undefined && (!Array.isArray(s.n) || s.n.some((x) => typeof x !== 'string' || !x))) errors.push(`${w}: n must be a list of sentences`);
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
  // 3 MB until the metal bulks of package NC3 (audit A-010: six new pages, ten new groups): they take the series by year to 3.16 MB, and the budget
  // rises by what they need and a fifth of room
  if (bytes > 3.4e6) errors.push(`commodities/history: ${(bytes / 1e6).toFixed(2)} MB, above the 3.4 MB budget`);
}

/** The monthly files of the energy pages (data/commodities/monthly, pipeline/commodities/monthly.py): each series has one value per month of its
 * block, its latest month is the last figure, its lowest month is not above it, the change is the arithmetic of the two published figures, and
 * the average of the baseline year equals the annual figure of the page's own table where there is one. */
function checkCommodityMonthly() {
  const dir = path.join(root, 'commodities', 'monthly');
  if (!fs.existsSync(dir)) return;
  const months = (a, b) => (Number(b.slice(0, 4)) - Number(a.slice(0, 4))) * 12 + Number(b.slice(5)) - Number(a.slice(5)) + 1;
  const near = (a, b, tol) => Math.abs(a - b) <= tol * Math.max(Math.abs(a), Math.abs(b), 1e-9);
  for (const f of fs.readdirSync(dir)) {
    if (!f.endsWith('.json')) continue;
    let d;
    try {
      d = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
    } catch {
      continue; // reported by walk()
    }
    const id = f.slice(0, -5);
    if (d.id !== id) errors.push(`commodities/monthly/${f}: id ${d.id}`);
    let table = {};
    try {
      table = JSON.parse(fs.readFileSync(path.join(root, 'commodities', `${id}.json`), 'utf8'));
    } catch {
      errors.push(`commodities/monthly/${f}: no commodity file ${id}.json`);
    }
    // imports by origin (gappy): EIA leaves a month out when it has no figure; lo, la and b are then null, with miss / last / nb saying why
    const gappySeries = (where, r, from, to) => {
      const w = `commodities/monthly/${f} ${where} ${r.c ?? r.o ?? r.name}`;
      const n = months(from, to);
      if (!Array.isArray(r.v) || r.v.length > n || r.v.length < 1) return errors.push(`${w}: ${r.v?.length} values for ${n} months`);
      if (r.v.some((x) => x !== null && typeof x !== 'number')) errors.push(`${w}: a value that is not a number`);
      const val = (m) => {
        const i = r.v.length - months(m, to);
        return i < 0 || i >= r.v.length ? undefined : r.v[i];
      };
      const year = to.slice(0, 4);
      const thisYear = Array.from({ length: Number(to.slice(5)) }, (_, k) => `${year}-${String(k + 1).padStart(2, '0')}`);
      const miss = thisYear.filter((m) => val(m) == null).length;
      if ((r.miss ?? 0) !== miss) errors.push(`${w}: miss ${r.miss} but ${miss} months of ${year} have no figure`);
      if (miss === 0 ? !r.lo : r.lo !== null) errors.push(`${w}: the lowest month must be printed only when no month of ${year} lacks a figure`);
      if (r.lo) {
        if (val(r.lo.m) !== r.lo.v) errors.push(`${w}: lo (${r.lo.m}) is not the value of that month in the series`);
        const cur = thisYear.map(val).filter((x) => x != null);
        if (Math.min(...cur) !== r.lo.v) errors.push(`${w}: the lowest month is not the lowest of the year`);
      }
      const at = val(to);
      if (at == null ? r.la !== null : !r.la || r.la.m !== to || r.la.v !== at) errors.push(`${w}: la is not the figure of ${to} (or null when EIA gives none)`);
      if (r.la == null && r.last && val(r.last.m) !== r.last.v) errors.push(`${w}: last (${r.last.m}) is not the value of that month in the series`);
      const nb = Array.from({ length: 12 }, (_, k) => val(`${Number(year) - 1}-${String(k + 1).padStart(2, '0')}`)).filter((x) => x != null).length;
      if (r.b != null && nb !== 12) errors.push(`${w}: an average of ${Number(year) - 1} with ${nb} months`);
      if (r.b == null && (r.nb ?? 12) !== nb) errors.push(`${w}: nb ${r.nb} but ${nb} months of ${Number(year) - 1} have a figure`);
      if (r.b != null && r.nb != null) errors.push(`${w}: nb is only for a year with a month missing`);
      if (r.b != null && r.la && r.p != null && Math.abs(r.p - (r.la.v / r.b - 1) * 100) > 0.06) errors.push(`${w}: the change is not latest over average`);
      if (r.p != null && (r.b == null || !r.la)) errors.push(`${w}: a change without its average or its latest month`);
    };
    const series = (where, block, r, from, to, sorted) => {
      const w = `commodities/monthly/${f} ${where} ${r.c ?? r.o ?? r.name}`;
      const n = months(from, to);
      if (!Array.isArray(r.v) || r.v.length > n || r.v.length < 1) return errors.push(`${w}: ${r.v?.length} values for ${n} months`);
      if (r.v.some((x) => x !== null && typeof x !== 'number')) errors.push(`${w}: a value that is not a number`);
      const at = (m) => r.v.length - months(m, to); // index of month m in the last r.v.length months ending at `to`
      for (const k of ['lo', 'la']) {
        if (!r[k] || typeof r[k].v !== 'number' || !/^\d{4}-\d{2}$/.test(r[k].m)) {
          errors.push(`${w}: ${k} is not a figure with its month`);
          return;
        }
        const i = at(r[k].m);
        if (i < 0 || i >= r.v.length || r.v[i] !== r[k].v) errors.push(`${w}: ${k} (${r[k].m}) is not the value of that month in the series`);
      }
      if (r.lo.v > r.la.v) errors.push(`${w}: the lowest month is above the latest`);
      if (r.lo.m.slice(0, 4) !== r.la.m.slice(0, 4)) errors.push(`${w}: the lowest month is not of the year of the latest`);
      const cur = r.v.filter((x, i) => x !== null && String(shiftYear(to, r.v.length, i)) === r.la.m.slice(0, 4));
      if (cur.length && Math.min(...cur) !== r.lo.v) errors.push(`${w}: the lowest month is not the lowest of the year`);
      if (r.b != null && r.p != null && Math.abs(r.p - (r.la.v / r.b - 1) * 100) > 0.06) errors.push(`${w}: the change is not latest over average`);
      if (r.b != null && r.p == null && r.b !== 0) errors.push(`${w}: an average without its change`);
    };
    // year of the i-th value of a series of `len` values ending at month `to`
    const shiftYear = (to, len, i) => {
      const t = Number(to.slice(0, 4)) * 12 + Number(to.slice(5)) - 1 - (len - 1 - i);
      return Math.floor(t / 12);
    };
    for (const k of ['production', 'consumption', 'ngl']) {
      const b = d[k];
      if (!b) continue;
      let prev = Infinity;
      for (const r of b.rows) {
        series(k, b, r, b.from, b.to);
        if (k !== 'consumption' && r.b > prev) errors.push(`commodities/monthly/${f} ${k}: rows not sorted by the baseline average`);
        prev = r.b;
      }
      if (b.world) series(k, b, { ...b.world, name: 'world' }, b.from, b.to);
      if (b.gulf) {
        series(k, b, { ...b.gulf, name: 'gulf' }, b.from, b.to);
        for (const c of b.gulf.members) if (!b.rows.some((r) => r.c === c)) errors.push(`commodities/monthly/${f} ${k}: Gulf member ${c} has no row`);
      }
      // the baseline average is EIA's own annual figure of the table of the page, to its rounding
      const t = table[k];
      if (t && t.y === b.baseYear && t.s === d.s && t.u === b.u)
        for (const r of b.rows) {
          const row = t.rows.find((x) => x.c === r.c);
          if (row && !near(row.v, r.b, 2e-3)) errors.push(`commodities/monthly/${f} ${k} ${r.c}: the ${b.baseYear} average ${r.b} is not the annual figure ${row.v} of the table`);
        }
      if (t && t.y === b.baseYear && b.world && t.world && !near(t.world, b.world.b, 2e-3)) errors.push(`commodities/monthly/${f} ${k}: the ${b.baseYear} world average ${b.world.b} is not the annual world figure ${t.world}`);
    }
    for (const imp of d.imports?.importers ?? []) for (const r of imp.rows) gappySeries(`imports ${imp.id}`, r, imp.from, imp.to);
    if (d.stocks) {
      for (const r of d.stocks.rows) {
        series('stocks', d.stocks, r, d.stocks.from, d.stocks.to);
        if (r.cover != null && (r.cons == null || !near(r.cover, (r.la.v * 1000) / r.cons, 2e-3))) errors.push(`commodities/monthly/${f} stocks ${r.c}: the days of cover are not stock over demand`);
      }
    }
    if (!sources.has(d.s)) errors.push(`commodities/monthly/${f}: unknown source "${d.s}"`);
    if (d.gaps !== undefined && (!Array.isArray(d.gaps) || d.gaps.some((x) => typeof x !== 'string' || !x))) errors.push(`commodities/monthly/${f}: gaps must be a list of sentences`);
  }
}

/** The country profiles: one file per entry of the index (and the EU27 aggregate), and the years of their series (one file). */
function checkCountryProfiles() {
  const dir = path.join(root, 'countries', 'profiles');
  const index = JSON.parse(fs.readFileSync(path.join(root, 'countries', 'index.json'), 'utf8')).map((c) => c.c);
  const expected = new Set([...index, 'EU27']);
  if (fs.existsSync(path.join(root, 'countries', 'profiles.json'))) errors.push('countries/profiles.json: the light index is gone (the site never read it)');
  const years = JSON.parse(fs.readFileSync(path.join(root, 'countries', 'years.json'), 'utf8'));
  for (const [hk, ys] of Object.entries(years)) if (ys.w.length !== ys.y.length || (ys.l && ys.l.length !== ys.y.length)) errors.push(`countries/years.json ${hk}: not one entry per year`);
  const inUnit = (x) => typeof x === 'number' && x >= 0 && x <= 1.0001;
  for (const c of expected) {
    const f = path.join(dir, `${c}.json`);
    if (!fs.existsSync(f)) {
      errors.push(`countries/profiles/${c}.json: missing`);
      continue;
    }
    if (fs.statSync(f).size > 400_000) errors.push(`countries/profiles/${c}.json: ${fs.statSync(f).size} bytes, over 400 kB`);
    const p = JSON.parse(fs.readFileSync(f, 'utf8'));
    const where = `countries/profiles/${c}.json`;
    if (p.c !== c) errors.push(`${where}: c is ${p.c}`);
    if (p.none) {
      if (Object.keys(p).length !== 2) errors.push(`${where}: a territory without data holds c and none only`);
      continue;
    }
    if (p.years) errors.push(`${where}: the years of the series belong in countries/years.json`);
    const secs = ['exports', 'imports', 'production', 'consumption', 'reserves', 'stocks', 'capacity'];
    const top10 = new Set();
    for (const sec of secs) {
      for (const e of p[sec] ?? []) {
        if (['exports', 'imports', 'production'].includes(sec) && e.rank != null && e.rank <= 10) top10.add(e.k);
        if (!(e.v > 0)) errors.push(`${where} ${sec} ${e.k}: value ${e.v}`);
        if (e.share != null && !inUnit(e.share)) errors.push(`${where} ${sec} ${e.k}: share ${e.share}`);
        if (e.rank != null && !(Number.isInteger(e.rank) && e.rank >= 1)) errors.push(`${where} ${sec} ${e.k}: rank ${e.rank}`);
        if (e.hk) {
          const ys = years[e.hk];
          if (!ys) errors.push(`${where} ${sec} ${e.k}: series ${e.hk} has no years`);
          else if (e.hv.length !== ys.y.length || (e.hr && e.hr.length !== ys.y.length) || ys.w.length !== ys.y.length) errors.push(`${where} ${sec} ${e.k}: series ${e.hk} is not one value per year`);
          else if (e.hv[e.hv.length - 1] != null && Math.abs(e.hv[e.hv.length - 1] - e.v) > 1e-6 * Math.max(1, e.v) && String(ys.l?.[ys.y.length - 1] ?? ys.y[ys.y.length - 1]) === String(e.y))
            errors.push(`${where} ${sec} ${e.k}: the last year of the series (${e.hv[e.hv.length - 1]}) is not the line (${e.v})`);
        }
      }
    }
    if ((p.top10 ?? 0) !== top10.size) errors.push(`${where}: top10 ${p.top10} but ${top10.size} commodities rank in the top 10 of production, exports or imports`);
    for (const b of p.balance ?? []) {
      for (const side of ['customers', 'suppliers']) {
        const x = b[side];
        if (!x) continue;
        const sum = x.rows.reduce((a, r) => a + r.share, 0);
        if (sum > 1.0005 || x.rows.some((r) => !inUnit(r.share))) errors.push(`${where} ${b.k} ${side}: shares add up to ${sum}`);
        if (!(x.hhi >= 0 && x.hhi <= 10000)) errors.push(`${where} ${b.k} ${side}: Herfindahl index ${x.hhi}`);
      }
      if (b.dep && !(b.dep.v > 0)) errors.push(`${where} ${b.k}: import dependence ${b.dep.v}`);
    }
    for (const side of ['exports', 'imports']) {
      for (const x of [...(p.freight?.[side] ?? []), p.freight?.[`${side}Total`]].filter(Boolean)) {
        for (const v of x.via ?? []) {
          if (!(inUnit(v.low) && inUnit(v.high) && v.low <= v.high + 1e-9)) errors.push(`${where} freight ${side} ${x.g ?? 'total'} ${v.id}: at least ${v.low}, up to ${v.high}`);
          if (v.capped && v.high !== v.low) errors.push(`${where} freight ${side} ${x.g ?? 'total'} ${v.id}: no "up to" is printed where the passage page caps it`);
        }
        for (const pt of x.ports ?? []) if (!inUnit(pt.share)) errors.push(`${where} freight ${side} ${x.g}: port ${pt.name} share ${pt.share}`);
      }
      const bk = p.basket?.[side];
      if (bk && (bk.rows.length > 10 || bk.rows.some((r) => !inUnit(r.share)) || bk.rows.reduce((a, r) => a + r.share, 0) > 1.001)) errors.push(`${where} basket ${side}: shares out of bounds`);
    }
  }
  for (const f of fs.readdirSync(dir)) if (!expected.has(f.replace(/\.json$/, ''))) errors.push(`countries/profiles/${f}: not an entry of the country index`);
}

/** Ranges and country codes, in every file but the status files and the price files. */
function checkRanges() {
  const read = (rel) => {
    try {
      return JSON.parse(fs.readFileSync(path.join(root, rel), 'utf8'));
    } catch {
      return [];
    }
  };
  const codes = new Set([...read('countries/index.json'), ...read('countries/places.json')].map((x) => x?.c).filter(Boolean));
  const lastYear = new Date().getUTCFullYear() + 2;
  const onGlobe = (lon, lat) => Number.isFinite(lon) && Number.isFinite(lat) && Math.abs(lon) <= 180 && Math.abs(lat) <= 90;
  const positions = (c, out) => {
    if (Array.isArray(c) && typeof c[0] === 'number') out.push(c);
    else if (Array.isArray(c)) c.forEach((x) => positions(x, out));
    return out;
  };
  const visit = (o, rel, trail, n) => {
    if (n.bad > 5) return; // five findings per file are enough to find the fault
    if (Array.isArray(o)) return o.forEach((x, i) => visit(x, rel, `${trail}[${i}]`, n));
    if (!o || typeof o !== 'object') return;
    const err = (m) => {
      n.bad++;
      errors.push(`${rel}: ${m} at ${trail}`);
    };
    if (typeof o.type === 'string' && Array.isArray(o.coordinates)) {
      // a line that crosses the antimeridian keeps going past 180 degrees, so that the map draws it in one piece
      const wrap = /LineString$/.test(o.type) ? 360 : 180;
      const bad = positions(o.coordinates, []).find((p) => !onGlobe(Math.abs(p[0]) <= wrap ? 0 : p[0], p[1]));
      if (bad) err(`coordinates [${bad[0]}, ${bad[1]}] are not a longitude and a latitude`);
    }
    const lon = o.lon ?? o.lng;
    if (typeof o.lat === 'number' && typeof lon === 'number' && !onGlobe(lon, o.lat)) err(`lat ${o.lat}, lon ${lon} are not on the globe`);
    for (const k of ['share', 'estShare', 'shareDest'])
      if (typeof o[k] === 'number' && !(o[k] >= 0 && o[k] <= 1)) err(`${k} ${o[k]} is not between 0 and 1`);
    if (typeof o.y === 'number' && !(Number.isInteger(o.y) && o.y >= 1950 && o.y <= lastYear)) err(`year ${o.y} is not plausible`);
    if (typeof o.c === 'string' && /^[A-Z]{3}$/.test(o.c) && codes.size && !codes.has(o.c)) err(`country code "${o.c}" is not in countries/index.json or places.json`);
    for (const [k, v] of Object.entries(o)) if (v && typeof v === 'object') visit(v, rel, `${trail}.${k}`, n);
  };
  const walkRanges = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      const rel = path.relative(root, p).split(path.sep).join('/');
      if (e.isDirectory()) {
        if (rel !== '_status' && rel !== 'prices') walkRanges(p);
      } else if (/\.(geo)?json$/.test(e.name) && rel !== 'sources.json') {
        let doc;
        try {
          doc = JSON.parse(fs.readFileSync(p, 'utf8'));
        } catch {
          continue; // reported by check()
        }
        visit(doc, rel, '$', { bad: 0 });
      }
    }
  };
  walkRanges(root);
}

walk(root);
checkRanges();
checkCountryProfiles();
checkChokepoints();
checkCommodityTables();
checkCommodityMonthly();
checkPrices();
validateFreight(root, errors);
validatePorts(root, errors);
const infraWarnings = [];
await validateInfra(root, errors, infraWarnings);
if (infraWarnings.length) console.warn(summariseWarnings(infraWarnings));
if (errors.length) {
  console.error(errors.slice(0, 50).join('\n'));
  console.error(`\n${errors.length} data error(s) in ${files} files`);
  process.exit(1);
}
console.log(`data OK: ${files} files`);
