/**
 * The rules of the weekly port traffic files (data/freight/port-traffic/<PortWatch port id>.json and index.json), in one
 * pure function each, so that the site's data check (scripts/validate-data.mjs), a node test and, through node, the
 * Python test of the script that writes the files all run the same rules.
 *
 *   portTrafficProblems(doc, { id, sources })   the problems of one port file, each "code: message" (empty when it is good)
 *   portTrafficIndexProblems(index, { ids, files })
 *                                               the problems of index.json against the PortWatch ids of the port assets
 *                                               and the ids that have a file
 *
 * A file holds: id, name, s, y, start, step, u, dp, calls, exports, imports (no other key: never a daily value). `calls`,
 * `exports` and `imports` are each four arrays (tanker, dry, container, other), twelve in all, of the same length N >= 1,
 * one value per week from `start` (a Monday): calls are non-negative integers, tonnes thousand tonnes (`u` "kt") with at
 * most `dp` (3, the tonne) decimals and no more than the size of the value allows (whole from 100, one decimal from 10, two
 * from 1: three significant figures at least, as pipeline/freight/portwatch_ports.py round_tonnes gives them), a week that PortWatch did not give whole is null in all twelve arrays (never a zero), and the last
 * week (start + 7 N - 1 days) ends on or before `y`, the last day of data. index.json is {checked, none, pending}: `none` lists the
 * ports that returned no rows at the last check; every PortWatch id of the port assets has a file or is in `none`, and
 * no file is for an id that no asset carries. While the first load is made in sittings, index.json also holds `pending`,
 * the ids not read yet (sorted, distinct, no file, not in `none`): an id with a file, in `none` or in `pending` is
 * accounted for, so a release can go out between two sittings; the script takes an id out of `pending` when it writes the
 * file, and the list is empty once every port has been read. `pending` may be left out (an empty list).
 *
 * The same rules exist in Python (pipeline/freight/portwatch_ports.py validate_doc, so that the script writes nothing
 * that this file would refuse); pipeline/tests/test_portwatch_port_traffic.py runs both on the same documents.
 */
export const PORT_TRAFFIC_SOURCE = 'portwatch-port-traffic';
export const PORT_TRAFFIC_KEYS = ['id', 'name', 's', 'y', 'start', 'step', 'u', 'dp', 'calls', 'exports', 'imports'];
export const PORT_TRAFFIC_TYPES = ['tanker', 'dry', 'container', 'other'];
export const PORT_TRAFFIC_MEASURES = ['calls', 'exports', 'imports'];

const ID = /^(port|fso)\d+$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;
const DAY_MS = 86_400_000;

/** The time (ms, UTC) of an ISO day, or null when the text is not a real date. */
function dayMs(s) {
  if (typeof s !== 'string' || !DAY.test(s)) return null;
  const t = Date.parse(`${s}T00:00:00Z`);
  return Number.isFinite(t) && new Date(t).toISOString().slice(0, 10) === s ? t : null;
}

const isInt = (v) => typeof v === 'number' && Number.isFinite(v) && Number.isInteger(v);
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const MAX_DECIMALS = 3;

/** True when `v` (thousand tonnes) has no more decimals than the rule gives its size: none from 100, one from 10, two from 1, three below. */
function fitsRule(v) {
  const d = v >= 100 ? 0 : v >= 10 ? 1 : v >= 1 ? 2 : MAX_DECIMALS;
  return Math.abs(v * 10 ** d - Math.round(v * 10 ** d)) < 1e-6;
}

export function portTrafficProblems(doc, { id, sources } = {}) {
  if (!doc || typeof doc !== 'object' || Array.isArray(doc)) return [`shape: not an object with exactly the keys ${PORT_TRAFFIC_KEYS.join(',')}`];
  const keys = Object.keys(doc);
  if (keys.length !== PORT_TRAFFIC_KEYS.length || PORT_TRAFFIC_KEYS.some((k) => !keys.includes(k))) return [`shape: not an object with exactly the keys ${PORT_TRAFFIC_KEYS.join(',')}`];
  const p = [];
  if (typeof doc.id !== 'string' || !ID.test(doc.id) || (id !== undefined && doc.id !== id)) p.push(`id: ${JSON.stringify(doc.id)} is not the id of its file`);
  if (typeof doc.name !== 'string' || !doc.name.trim()) p.push('name: empty');
  if (doc.s !== PORT_TRAFFIC_SOURCE || (sources && !sources.has(doc.s))) p.push(`source: ${JSON.stringify(doc.s)}`);
  const y = dayMs(doc.y);
  const start = dayMs(doc.start);
  if (y === null || start === null) p.push('date: y or start is not an ISO date');
  else if (new Date(start).getUTCDay() !== 1) p.push('monday: start is not a Monday');
  if (doc.step !== 'week') p.push('step: not week');
  if (doc.u !== 'kt' || doc.dp !== MAX_DECIMALS) p.push(`unit: u must be kt and dp ${MAX_DECIMALS}`);
  const arrays = [];
  for (const k of PORT_TRAFFIC_MEASURES) {
    const b = doc[k];
    const ts = b && typeof b === 'object' && !Array.isArray(b) ? Object.keys(b) : [];
    if (ts.length !== PORT_TRAFFIC_TYPES.length || PORT_TRAFFIC_TYPES.some((t) => !ts.includes(t) || !Array.isArray(b[t]))) {
      p.push(`series: ${k} is not four arrays (${PORT_TRAFFIC_TYPES.join(',')})`);
      return p;
    }
    for (const t of PORT_TRAFFIC_TYPES) arrays.push([k, t, b[t]]);
  }
  const lens = new Set(arrays.map(([, , a]) => a.length));
  if (lens.size !== 1 || lens.has(0)) {
    p.push('series: the twelve arrays are not all of the same length, at least one week');
    return p;
  }
  const n = [...lens][0];
  let holes = null;
  for (const [k, t, a] of arrays) {
    for (const v of a) {
      if (v === null) continue;
      if (k === 'calls') {
        if (!(isInt(v) && v >= 0)) {
          p.push(`calls: ${k} ${t} holds ${JSON.stringify(v)}, not a non-negative integer`);
          break;
        }
      } else if (!(isNum(v) && v >= 0 && fitsRule(v))) {
        p.push(`tonnes: ${k} ${t} holds ${JSON.stringify(v)}, not a non-negative number with the decimals its size allows`);
        break;
      }
    }
    const h = a.flatMap((v, i) => (v === null ? [i] : [])).join(',');
    if (holes === null) holes = h;
    else if (h !== holes) {
      p.push(`holes: the missing weeks of ${k} ${t} differ from those of the other arrays`);
      break;
    }
  }
  if (y !== null && start !== null && start + (7 * n - 1) * DAY_MS > y) p.push('end: the last week ends after y');
  return p;
}

/** index.json against the PortWatch ids of the port assets (`ids`, an array) and the ids that have a file (`files`, an array). */
export function portTrafficIndexProblems(index, { ids, files }) {
  const shape = !index || typeof index !== 'object' || Array.isArray(index) ? '' : Object.keys(index).sort().join();
  if (shape !== 'checked,none' && shape !== 'checked,none,pending') return ['index-shape: not {checked, none, pending}'];
  const p = [];
  if (dayMs(index.checked) === null) p.push('index-date: checked is not an ISO date');
  const lists = { none: index.none, pending: index.pending ?? [] };
  for (const [name, list] of Object.entries(lists)) {
    if (!Array.isArray(list) || list.some((i) => typeof i !== 'string' || !ID.test(i))) {
      p.push(`index-${name}: ${name} is not a list of PortWatch port ids`);
      return p;
    }
    if (new Set(list).size !== list.length || list.join() !== [...list].sort().join()) p.push(`index-${name}: the ids are not sorted and distinct`);
  }
  const asset = new Set(ids);
  const have = new Set(files);
  const none = new Set(lists.none);
  const pending = new Set(lists.pending);
  for (const i of lists.none) {
    if (!asset.has(i)) p.push(`index-orphan: ${i} is in none but no port asset carries it`);
    if (have.has(i)) p.push(`index-both: ${i} has a file and is in none`);
  }
  for (const i of lists.pending) {
    if (!asset.has(i)) p.push(`index-orphan: ${i} is in pending but no port asset carries it`);
    if (have.has(i)) p.push(`index-both: ${i} has a file and is in pending`);
    if (none.has(i)) p.push(`index-both: ${i} is in none and in pending`);
  }
  for (const i of files) if (!asset.has(i)) p.push(`index-orphan: the file of ${i} is for no port asset`);
  for (const i of ids) if (!have.has(i) && !none.has(i) && !pending.has(i)) p.push(`index-missing: ${i} has no file and is in neither none nor pending`);
  return p;
}

/** The codes of a list of problems, sorted and distinct. */
export const problemCodes = (list) => [...new Set(list.map((s) => s.split(':')[0]))].sort();
