/**
 * Checks of the freight files that the Route finder, the map and the chokepoint pages read together:
 *  - lanes (data/freight/lanes/<group>.json): unique ids, `set`, `mode` and `portBasis` in their lists, main lanes
 *    at or above the floor of their group, every passage named in `via`, `viaAlt`, `alts` and `opts` is a chokepoint,
 *    every port of a lane is in the file's `ports` table, every `transit` has a source and (once the pairs table
 *    exists) every port has an `s` (a source id, or null for a port of the older tables that no gateway row sources;
 *    those are counted in a warning), every `caveat` exists in caveats.json, an estimated flow carries the source id `atlas`;
 *  - pairs (data/freight/pairs/<group>.json): at most 31 gates, all of them chokepoints, every row as long as `cols`,
 *    mode in 0..3, port and class indexes in range, passage masks inside the gate list, country codes known to the atlas
 *    (countries/index.json and places.json), bit 2 of `f` set exactly when the group's lane file has a main lane for the pair,
 *    sea and transit tonnes adding up to `seaborne` (within 0.1%), the optional `bases` and `notes` well formed.
 *  - routes (freight/routes.json): unique ids, every passage named in `via` and `viaAlt` is a chokepoint; a generated corridor
 *    route (`generated`: id "gen-...", never a benchmark, source "atlas", a note that says how it was made, corridor entries
 *    that name a customs group with a pairs file) has no pair in common with another generated route, and its distance,
 *    vessel class, ports and passages (`via`, `viaAlt`) are those of the largest pair of its corridor in the pairs table;
 *    every corridor entry names its customs group (`g`) or the groups of its commodity (`gs`);
 *  - events (freight/events.json): unique ids, a date, every chokepoint, commodity, country and asset an event names
 *    exists in the atlas (the commodity catalogue, the country index, the infrastructure files); an optional date of
 *    check, other source pages (`also`) and price series (`series`: a commodity of the atlas and a series of prices/index.json
 *    that is of that commodity);
 *  - alerts (freight/alerts.json): unique ids, an optional date of check (`checked`: only a text that was read against its
 *    source carries one), an event that exists (and, when it lists several in `events`, events that exist, the main one first), passages that exist, a severity from the list, a PortWatch figure per
 *    passage with its date, derived commodities and countries that exist, and a reason on every override.
 * Called by validate-data.mjs; `node validate-freight.mjs [data folder]` runs it alone.
 * A tree from before the pairs table (no data/freight/pairs folder) is checked by the rules that its lane files
 * can meet; once the folder exists every lane file must also meet the rules of the new shape.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SETS = ['main', 'history'];
const MODES = ['mixed'];
const BASES = ['single', 'rule', 'measured', 'open'];
/** Why a port is used (pipeline/freight/ports.py, BASES): the values of a pairs file's `bases` and of a lane file's port `basis`. */
const PORT_BASES = ['page names the cargo', 'page names the cargo in the other direction', 'page names the plant, not the cargo', 'general port of the country', 'port used before, no page read', 'nearest seaport'];
const COLS = ['o', 'd', 'kt', 'm', 'load', 'dis', 'nm', 'cls', 'via', 'alt', 'f'];
/** Smallest tonnage (Mt) of a main lane: 0.05 unless the group is listed (PLAN 2.2). */
const FLOOR = {
  coffee: 0.02, cocoa: 0.02, cotton: 0.02, 'nickel-int': 0.02, 'copper-refined': 0.02, 'zinc-ore': 0.02, aluminium: 0.03, soyoil: 0.03,
  // the minor metals (build_lanes.py FLOOR)
  'lead-ore': 0.02, 'lead-metal': 0.01, 'zinc-metal': 0.015, 'tin-metal': 0.001, 'tin-ore': 0.002, cobalt: 0.002, lithium: 0.005, 'rare-earths': 0.002,
  // the fertilisers whose default floor left their main set under the coverage floor (build_lanes.py FLOOR, package NC1)
  'potassium-sulphate': 0.01, 'ammonium-nitrate': 0.02,
  // ammonium nitrate with limestone (build_lanes.py FLOOR, package FNCB)
  'ammonium-nitrate-limestone': 0.02,
  // sunflower seed and rapeseed oil trade in small parcels (build_lanes.py FLOOR, package NC2)
  'sunflower-seed': 0.01, 'rapeseed-oil': 0.01,
  // the ferro-alloys, which trade in parcels of a few thousand tonnes (build_lanes.py FLOOR, package NC3)
  'ferro-manganese': 0.02, 'silico-manganese': 0.02, 'ferro-silicon': 0.005,
};
const floorOf = (g) => FLOOR[g] ?? 0.05;
/** The river leg of a port up a river (pipeline/freight/river_legs.py): what a lane file's port (`river`) and a pairs file's `rivers` carry. */
const riverProblem = (r) =>
  !r || typeof r !== 'object'
    ? 'is not an object'
    : !(Number.isInteger(r.nm) && r.nm > 0) || !(r.km > 0) || [r.river, r.mouth, r.s, r.url, r.n].some((x) => typeof x !== 'string' || !x)
      ? 'needs river, mouth, km, nm (whole, above 0), s, url and n'
      : !/straight/.test(r.n) || !r.n.includes(`${r.nm} nm`)
        ? 'its note must give the leg in nm and say that the leg is drawn straight'
        : null;

export function validateFreight(root, errors) {
  const read = (rel) => {
    try {
      return JSON.parse(fs.readFileSync(path.join(root, rel), 'utf8'));
    } catch {
      return null;
    }
  };
  const list = (rel) => {
    try {
      return fs.readdirSync(path.join(root, rel)).filter((f) => f.endsWith('.json')).sort();
    } catch {
      return [];
    }
  };
  const chk = read('freight/chokepoints.json');
  if (!Array.isArray(chk)) {
    errors.push('freight/chokepoints.json: missing or unreadable (the freight files are checked against it)');
    return;
  }
  const chokepoints = new Set(chk.map((c) => c.id));
  // the note of a ship type against PortWatch's volume is written once on the passage (`typeNotes`): a known type, a line and its reason,
  // a known regime of the cap, and no repetition of it in the estimates
  for (const c of chk) {
    for (const [t, tn] of Object.entries(c.typeNotes ?? {})) {
      const at = `chokepoints.json: ${c.id} typeNotes.${t}`;
      if (!['dry', 'tanker', 'cargo'].includes(t)) errors.push(`freight/${at}: not a ship type of the passage records`);
      if (typeof tn?.line !== 'string' || !tn.line) errors.push(`freight/${at}: no line`);
      if (typeof tn?.n !== 'string' || !tn.n) errors.push(`freight/${at}: no reason (n)`);
      if (!['sub', 'whole', 'none', null].includes(tn?.regime)) errors.push(`freight/${at}: regime "${tn?.regime}" is not sub, whole, none or null`);
      if (!c.estimates?.length) errors.push(`freight/${at}: a note of a ship type on a passage with no estimate`);
    }
    for (const e of c.estimates ?? []) {
      if (/PortWatch's (?:volume|estimate for all)/.test(e.f?.n ?? '')) errors.push(`freight/chokepoints.json: ${c.id} ${e.p ?? e.k}: the note of the ship type is repeated in the estimate (it belongs to typeNotes)`);
    }
  }
  const hasPairs = fs.existsSync(path.join(root, 'freight/pairs'));
  const caveats = read('freight/caveats.json');
  // country codes the atlas can name: the index plus the places customs data use that it has no page for (absent in a small test folder: no check)
  const codeList = [...(read('countries/index.json') ?? []), ...(read('countries/places.json') ?? [])];
  const knownCountries = codeList.length ? new Set(codeList.map((c) => c.c)) : null;
  const bad = (file, msg) => errors.push(`freight/${file}: ${msg}`);
  const passages = (file, where, ids) => {
    if (!Array.isArray(ids)) return bad(file, `${where} is not a list`);
    for (const id of ids) if (!chokepoints.has(id)) bad(file, `${where} names "${id}", which is not a chokepoint`);
  };

  // ------------------------------------------------------------ pairs
  const pairGroups = new Set();
  const pairDocs = new Map();
  for (const f of list('freight/pairs')) {
    const file = `pairs/${f}`;
    const doc = read(`freight/${file}`);
    if (!doc) {
      bad(file, 'unreadable');
      continue;
    }
    pairGroups.add(f.replace(/\.json$/, ''));
    if (doc.group !== f.replace(/\.json$/, '')) bad(file, `group "${doc.group}" does not match the file name`);
    const gates = doc.gates;
    if (!Array.isArray(gates) || !Array.isArray(doc.ports) || !Array.isArray(doc.classes) || !Array.isArray(doc.cols) || !Array.isArray(doc.rows)) {
      bad(file, 'gates, ports, classes, cols and rows must all be lists');
      continue;
    }
    if (gates.length > 31) bad(file, `${gates.length} gates: the passage masks are read with 32-bit operations, so 31 is the most`);
    for (const g of gates) if (!chokepoints.has(g)) bad(file, `gate "${g}" is not a chokepoint`);
    const ix = Object.fromEntries(doc.cols.map((c, i) => [c, i]));
    const missing = COLS.filter((c) => !(c in ix));
    if (missing.length) {
      bad(file, `columns missing: ${missing.join(', ')}`);
      continue;
    }
    for (const p of doc.ports) if (!Array.isArray(p) || p.length < 4 || typeof p[0] !== 'string') bad(file, `a port entry is not [code, name, country, zone]: ${JSON.stringify(p)}`);
    // the basis of a port as a loading port (optional fifth element) and as a discharging port (optional sixth): indexes in
    // the file's `bases`, null when no pair uses the port in that role
    if (doc.bases !== undefined && !(Array.isArray(doc.bases) && doc.bases.every((b) => typeof b === 'string'))) bad(file, 'bases is not a list of strings');
    else for (const b of doc.bases ?? []) if (!PORT_BASES.includes(b)) bad(file, `bases names "${b}", which is not one of the port bases of ports.py`);
    // the ports up a river, by code: the pairs of the file through them include the leg
    for (const [id, r] of Object.entries(doc.rivers ?? {})) {
      const why = riverProblem(r);
      if (why) bad(file, `rivers.${id} ${why}`);
      if (!doc.ports.some((p) => p[0] === id)) bad(file, `rivers.${id}: not a port of the file`);
    }
    for (const p of doc.ports) {
      for (const i of [4, 5]) if (Array.isArray(p) && p[i] != null && !(Number.isInteger(p[i]) && p[i] >= 0 && p[i] < (doc.bases?.length ?? 0))) bad(file, `port ${p[0]}: basis index ${p[i]} is not in bases`);
      if (knownCountries && Array.isArray(p) && !knownCountries.has(p[2])) bad(file, `port ${p[0]}: country "${p[2]}" is not in countries/index.json or places.json`);
    }
    const range = 2 ** Math.min(gates.length, 31);
    const unknownCodes = new Set();
    let seaKt = 0;
    let n = 0;
    for (const r of doc.rows) {
      const at = `row ${n++} (${r?.[ix.o]}-${r?.[ix.d]})`;
      if (!Array.isArray(r) || r.length !== doc.cols.length) {
        bad(file, `${at} has ${r?.length} values for ${doc.cols.length} columns`);
        if (errors.length > 200) return;
        continue;
      }
      const int = (c, lo, hi) => {
        const v = r[ix[c]];
        if (!Number.isInteger(v) || v < lo || v > hi) bad(file, `${at}: ${c} = ${v} is not an integer from ${lo} to ${hi}`);
      };
      int('m', 0, 3);
      int('load', -1, doc.ports.length - 1);
      int('dis', -1, doc.ports.length - 1);
      int('cls', -1, doc.classes.length - 1);
      int('via', 0, range - 1);
      int('alt', 0, range - 1);
      int('f', 0, 15);
      int('nm', 0, 1e6);
      const kt = r[ix.kt];
      if (typeof kt !== 'number' || !(kt >= 0)) bad(file, `${at}: kt = ${kt} is not a tonnage`);
      if (typeof r[ix.o] !== 'string' || typeof r[ix.d] !== 'string') bad(file, `${at}: origin and destination must be country codes`);
      else if (knownCountries) for (const c of [r[ix.o], r[ix.d]]) if (!knownCountries.has(c)) unknownCodes.add(c);
      if (r[ix.m] === 0 || r[ix.m] === 1) seaKt += typeof kt === 'number' ? kt : 0;
    }
    for (const c of unknownCodes) bad(file, `country code "${c}" is not in countries/index.json or places.json`);
    // the shares are taken over `seaborne`: it must be the tonnes of the sea and transit rows. `seaborne` is the unrounded
    // sum, as the lane file and the commodity page give it, and each row keeps 0.1 kt (a rounding of up to 0.05 kt per row)
    const seaRows = doc.rows.filter((r) => r?.[ix.m] === 0 || r?.[ix.m] === 1).length;
    if (typeof doc.seaborne !== 'number' || Math.abs(seaKt - doc.seaborne) > Math.max(0.001 * doc.seaborne, 0.1, 0.05 * seaRows))
      bad(file, `sea and transit rows add up to ${Math.round(seaKt * 10) / 10} kt, but seaborne is ${doc.seaborne}`);
    if (doc.notes !== undefined) {
      const keys = new Set(doc.rows.map((r) => `${r?.[ix.o]}-${r?.[ix.d]}`));
      if (!doc.notes || typeof doc.notes !== 'object' || Array.isArray(doc.notes)) bad(file, 'notes is not an object');
      else for (const [k, v] of Object.entries(doc.notes)) if (!keys.has(k) || typeof v !== 'string' || !v) bad(file, `note "${k}": no row for that pair, or the text is empty`);
    }
    pairDocs.set(f.replace(/\.json$/, ''), { file, doc, ix });
    if (errors.length > 200) return;
  }

  // ------------------------------------------------------------ lanes
  const unsourced = new Set();
  const mainLanes = new Map();
  for (const f of list('freight/lanes')) {
    const file = `lanes/${f}`;
    const doc = read(`freight/${file}`);
    if (!doc || !Array.isArray(doc.lanes)) {
      bad(file, 'unreadable or without a lane list');
      continue;
    }
    const group = f.replace(/\.json$/, '');
    if (hasPairs && !pairGroups.has(group)) bad(file, `no pairs file freight/pairs/${f}`);
    const ports = doc.ports ?? {};
    for (const [id, port] of Object.entries(ports)) if (port?.basis !== undefined && !PORT_BASES.includes(port.basis)) bad(file, `port ${id}: basis "${port.basis}" is not one of the port bases of ports.py`);
    for (const [id, port] of Object.entries(ports)) if (port?.river !== undefined && riverProblem(port.river)) bad(file, `port ${id}: river ${riverProblem(port.river)}`);
    const ids = new Set();
    const mains = new Set();
    mainLanes.set(group, mains);
    for (const lane of doc.lanes) {
      const at = lane.id;
      if (lane.set === 'main') mains.add(`${lane.o}-${lane.d}`);
      if (ids.has(lane.id)) bad(file, `lane id ${at} appears twice`);
      ids.add(lane.id);
      if (lane.id !== `${lane.p}:${lane.o}-${lane.d}`) bad(file, `lane id ${at} does not match its group, origin and destination`);
      if (hasPairs && lane.set === undefined) bad(file, `${at}: no "set" (main or history)`);
      if (lane.set !== undefined && !SETS.includes(lane.set)) bad(file, `${at}: set "${lane.set}" is not one of ${SETS.join(', ')}`);
      if (lane.mode !== undefined && !MODES.includes(lane.mode)) bad(file, `${at}: mode "${lane.mode}" is not one of ${MODES.join(', ')}`);
      if (lane.portBasis !== undefined && !BASES.includes(lane.portBasis)) bad(file, `${at}: portBasis "${lane.portBasis}" is not one of ${BASES.join(', ')}`);
      if (lane.portRule !== undefined && (lane.portRule !== true || lane.portBasis !== 'open')) bad(file, `${at}: portRule is true only on a lane whose portBasis is "open"`);
      // a group under 1 Mt a year is published in kt (the file's `unit`); the floor is in Mt
      const mt = (lane.flow?.v ?? NaN) / (lane.flow?.u === 'kt' ? 1e3 : 1);
      if (lane.set === 'main' && !(mt >= floorOf(lane.p) - 1e-9)) bad(file, `${at}: a main lane of ${lane.flow?.v} ${lane.flow?.u} is under the ${floorOf(lane.p)} Mt floor of its group`);
      if (lane.flow?.u !== undefined && lane.flow.u !== doc.unit) bad(file, `${at}: the flow is in ${lane.flow.u}, the file in ${doc.unit}`);
      passages(file, `${at}: via`, lane.via ?? []);
      for (const l of lane.viaAlt ?? []) passages(file, `${at}: viaAlt`, l);
      for (const a of lane.alts ?? []) passages(file, `${at}: alts[].via`, a.via ?? []);
      for (const o of lane.opts ?? []) passages(file, `${at}: opts[].via`, o.via ?? []);
      const portIds = [...(lane.load ?? []), ...(lane.discharge ?? []), ...(lane.opts ?? []).flatMap((o) => [o.load, o.discharge]), ...(lane.transit ? [lane.transit.port] : []), ...(lane.transit2 ? [lane.transit2.port] : [])];
      for (const p of new Set(portIds)) {
        if (!ports[p]) bad(file, `${at}: port ${p} is not in the file's ports table`);
        else if (hasPairs && ports[p].s === undefined) bad(file, `${at}: port ${p} has no "s" (source id, or null when none is recorded)`);
        else if (ports[p].s === null) unsourced.add(p);
        else if (ports[p].s === 'wikipedia' && !ports[p].url) bad(file, `${at}: port ${p} cites wikipedia without a url`);
      }
      if (lane.transit && !lane.transit.s) bad(file, `${at}: the transit port has no source (s)`);
      if (lane.transit2 && !lane.transit2.s) bad(file, `${at}: the second transit port has no source (s)`);
      if (lane.transit2 && !lane.transit) bad(file, `${at}: transit2 without transit`);
      if (lane.caveat !== undefined && !(caveats && lane.caveat in caveats)) bad(file, `${at}: caveat "${lane.caveat}" is not in freight/caveats.json`);
      if (lane.flow?.est && lane.flow.s !== 'atlas') bad(file, `${at}: an estimated flow must carry the source id "atlas", not "${lane.flow.s}"`);
    }
  }
  // bit 2 of `f` is the pairs table's statement that a main lane exists: it must agree with the lane file it points to
  for (const [group, { file, doc, ix }] of pairDocs) {
    const mains = mainLanes.get(group) ?? new Set();
    const off = doc.rows.filter((r) => Array.isArray(r) && !!(Number(r[ix.f]) & 4) !== mains.has(`${r[ix.o]}-${r[ix.d]}`)).map((r) => `${r[ix.o]}-${r[ix.d]}`);
    if (off.length) bad(file, `${off.length} row(s) where bit 2 of f disagrees with the main lanes of lanes/${group}.json: ${off.slice(0, 5).join(', ')}`);
  }
  validateRoutes(read('freight/routes.json'), pairDocs, chokepoints, bad);
  validateEvents(root, errors, { read, list, chokepoints, knownCountries });
  // a port that no gateway row sources (the typical ports of the older tables) is allowed with s = null, and said once
  if (unsourced.size) console.warn(`freight: ${unsourced.size} lane ports have no source yet (s = null): ${[...unsourced].sort().slice(0, 12).join(', ')}...`);
}

/** Routes (see the header). Checked only when the file exists; the comparison with the pairs table only for a group that has a pairs file. */
/** A benchmark's definition: a code, a status from the list with its page (an ended one with its date, and the route that
 * replaced it when the atlas has it), the page of the definition and the month it was read; in each index, members once,
 * weights that add up to 100% (or none), and `covered`, the weight of the members the atlas has. */
function checkDefinition(at, r, routes, bad) {
  const d = r.definition;
  const has = (id) => routes.some((x) => x.id === id);
  if (!r.benchmark) bad('routes.json', `${at}: a route that is not a benchmark has a definition`);
  if (!d.code) bad('routes.json', `${at}: the definition has no code`);
  if (!['active', 'suspended', 'ended'].includes(d.state)) bad('routes.json', `${at}: definition state "${d.state}" is not active, suspended or ended`);
  if (!d.stateNote || !/^https?:\/\//.test(d.stateUrl ?? '')) bad('routes.json', `${at}: the definition's status has no note or no page`);
  if (d.stateDate !== undefined && !/^\d{4}-\d{2}-\d{2}$/.test(d.stateDate)) bad('routes.json', `${at}: stateDate "${d.stateDate}" is not a date`);
  if (d.state === 'ended' && (!d.stateDate || !r.discontinued)) bad('routes.json', `${at}: an ended benchmark has a date and is marked discontinued`);
  if (d.state !== 'ended' && r.discontinued) bad('routes.json', `${at}: a discontinued route has a definition that is not ended`);
  if (d.replacedBy && !has(d.replacedBy)) bad('routes.json', `${at}: replacedBy "${d.replacedBy}" is not a route`);
  if (!d.doc || !/^https?:\/\//.test(d.url ?? '') || !d.read) bad('routes.json', `${at}: the definition has no page or no month of reading`);
  if (!Number.isInteger(d.y) || d.y < 1985 || d.y > 2100) bad('routes.json', `${at}: the definition has no year of its document (y)`);
  // a cargo the definition does not name is said so, and the atlas's reading of it is given in cargoNote, never in the definition
  if (/cargo not named/.test(d.cargo ?? '') && !/atlas's reading/.test(r.cargoNote ?? '')) bad('routes.json', `${at}: the definition names no cargo, but cargoNote does not give the atlas's reading`);
  for (const x of d.index ?? []) {
    const rs = x.members.map((m) => m.r);
    if (new Set(rs).size !== rs.length) bad('routes.json', `${at}: index ${x.id} lists a member twice`);
    if (!rs.includes(at)) bad('routes.json', `${at}: index ${x.id} does not list the route among its members`);
    for (const m of x.members) if (m.in !== has(m.r)) bad('routes.json', `${at}: index ${x.id} member ${m.r} has a wrong "in" flag`);
    const ws = x.members.map((m) => m.w).filter((w) => w != null);
    if (ws.length && (ws.length !== rs.length || Math.abs(ws.reduce((a, b) => a + b, 0) - 100) > 0.01)) bad('routes.json', `${at}: the weights of index ${x.id} do not add up to 100%`);
    if (x.covered != null) {
      const w = (m) => (x.equal ? 100 / rs.length : m.w);
      const cov = x.members.filter((m) => m.in).reduce((a, m) => a + w(m), 0);
      if (Math.abs(cov - x.covered) > 0.01) bad('routes.json', `${at}: index ${x.id} says ${x.covered}% of its weight is in the atlas, not ${cov.toFixed(2)}%`);
    }
  }
}

function validateRoutes(routes, pairDocs, chokepoints, bad) {
  if (routes == null) return;
  if (!Array.isArray(routes)) return bad('routes.json', 'is not a list');
  const ids = new Set();
  const owner = new Map();
  for (const r of routes) {
    const at = r?.id;
    if (ids.has(at)) bad('routes.json', `route id ${at} appears twice`);
    ids.add(at);
    for (const id of r.via ?? []) if (!chokepoints.has(id)) bad('routes.json', `${at}: via names "${id}", which is not a chokepoint`);
    for (const l of r.viaAlt ?? []) for (const id of l) if (!chokepoints.has(id)) bad('routes.json', `${at}: viaAlt names "${id}", which is not a chokepoint`);
    if (r.cargoNote !== undefined && (typeof r.cargoNote !== 'string' || !r.cargoNote)) bad('routes.json', `${at}: cargoNote is empty`);
    for (const x of r.rivers ?? []) if (riverProblem(x) || !x.port) bad('routes.json', `${at}: rivers entry ${riverProblem(x) ?? 'has no port'}`);
    // an entry without `g` lists the customs groups of its commodity (`gs`): the site matches a lane to a route by group, never by commodity alone
    for (const c of r.corridor ?? []) if (!c.g && !(Array.isArray(c.gs) && c.gs.length)) bad('routes.json', `${at}: a corridor entry has neither a customs group (g) nor a list of them (gs)`);
    if (r.definition) checkDefinition(at, r, routes, bad);
    else if (r.benchmark) bad('routes.json', `${at}: a benchmark has no definition`);
    if (r.shareOn !== undefined && (!r.shareNa || !routes.some((x) => x.id === r.shareOn && x.generated))) bad('routes.json', `${at}: shareOn "${r.shareOn}" is not a generated route, or the route has no shareNa that says why`);
    if (!r.generated) {
      if (String(at).startsWith('gen-')) bad('routes.json', `${at}: an id that starts with "gen-" is for a generated route`);
      continue;
    }
    if (!String(at).startsWith('gen-')) bad('routes.json', `${at}: a generated route has an id that starts with "gen-"`);
    if (r.benchmark) bad('routes.json', `${at}: a generated route is never a benchmark`);
    if (r.s !== 'atlas') bad('routes.json', `${at}: a generated route carries the source id "atlas", not "${r.s}"`);
    if (!String(r.notes ?? '').startsWith('Atlas corridor, generated from customs pairs')) bad('routes.json', `${at}: the note must say that the route is generated from customs pairs`);
    if (!Array.isArray(r.corridor) || !r.corridor.length) {
      bad('routes.json', `${at}: a generated route has a corridor`);
      continue;
    }
    let best = null;
    for (const c of r.corridor) {
      if (!c.g) bad('routes.json', `${at}: a corridor entry of a generated route names its customs group (g)`);
      const pd = pairDocs.get(c.g);
      if (c.g && pairDocs.size && !pd) bad('routes.json', `${at}: customs group "${c.g}" has no pairs file`);
      for (const o of c.o) {
        for (const d of c.d) {
          const key = `${c.g}:${o}-${d}`;
          if (owner.has(key) && owner.get(key) !== at) bad('routes.json', `pair ${key} is in the corridor of ${owner.get(key)} and of ${at}`);
          owner.set(key, at);
          if (!pd) continue;
          const row = pd.doc.rows.find((x) => x[pd.ix.o] === o && x[pd.ix.d] === d && x[pd.ix.load] >= 0 && (x[pd.ix.m] === 0 || x[pd.ix.m] === 1));
          if (row && (!best || row[pd.ix.kt] > best.row[pd.ix.kt])) best = { row, pd };
        }
      }
    }
    if (best) {
      const { row, pd } = best;
      const cls = pd.doc.classes[row[pd.ix.cls]];
      if (r.distanceNm !== row[pd.ix.nm]) bad('routes.json', `${at}: distance ${r.distanceNm} nm is not the ${row[pd.ix.nm]} nm of its largest pair in the pairs table`);
      if (r.vclass !== cls) bad('routes.json', `${at}: vessel class ${r.vclass} is not the ${cls} of its largest pair`);
      if (r.from?.ports?.[0] !== pd.doc.ports[row[pd.ix.load]][1] || r.to?.ports?.[0] !== pd.doc.ports[row[pd.ix.dis]][1]) bad('routes.json', `${at}: its ports are not those of its largest pair`);
      // the passages are the pair's own, as the Route finder gives them (the drawn line is one port option's and may cross more)
      const gates = pd.doc.gates;
      const maskSet = (m) => new Set(gates.filter((_, i) => (Number(m) >>> i) & 1));
      const via = maskSet(row[pd.ix.via]);
      const alt = [...maskSet(row[pd.ix.alt])].filter((x) => !via.has(x));
      const same = (a, b) => [...a].sort().join() === [...b].sort().join();
      if (!same(r.via ?? [], via)) bad('routes.json', `${at}: via [${(r.via ?? []).join(', ')}] is not the passages [${[...via].join(', ')}] that every port option of its largest pair crosses`);
      if (!same((r.viaAlt ?? []).flat().filter((x) => !via.has(x)), alt)) bad('routes.json', `${at}: its viaAlt is not the passages that its largest pair may cross`);
    }
  }
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const EVENT_DATE = /^\d{4}-\d{2}(-\d{2})?$/;
const SEVERITIES = ['low', 'medium', 'high'];

/** Events and alerts (see the header). Checked only when the files exist; a link to a catalogue is checked only when that catalogue is there. */
function validateEvents(root, errors, { read, list, chokepoints, knownCountries }) {
  const events = read('freight/events.json');
  const alerts = read('freight/alerts.json');
  const bad = (file, msg) => errors.push(`freight/${file}: ${msg}`);
  const commodityIds = Array.isArray(read('commodities/index.json')) ? new Set(read('commodities/index.json').map((c) => c.id)) : null;
  const prices = read('prices/index.json');
  const priceSeries = Array.isArray(prices) ? new Map(prices.map((m) => [m.id, m.k])) : null;
  let assetIds = null;
  try {
    const dir = path.join(root, 'infrastructure');
    const files = fs.readdirSync(dir).filter((f) => f.endsWith('.geojson'));
    assetIds = new Set(files.flatMap((f) => (JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')).features ?? []).map((x) => x.properties?.id)));
  } catch {
    /* no infrastructure folder in this data tree */
  }
  const ids = (file, at, v, known, what) => {
    if (v === undefined) return;
    if (!Array.isArray(v) || v.some((x) => typeof x !== 'string')) return bad(file, `${at}: ${what} is not a list of ids`);
    if (new Set(v).size !== v.length) bad(file, `${at}: ${what} lists an id twice`);
    if (known) for (const x of v) if (!known.has(x)) bad(file, `${at}: ${what} names "${x}", which the atlas does not have`);
  };
  const eventIds = new Set();
  if (events !== null) {
    if (!Array.isArray(events)) return bad('events.json', 'is not a list');
    for (const e of events) {
      const at = `event ${e.id}`;
      if (typeof e.id !== 'string' || !e.id) bad('events.json', 'an event has no id');
      else if (eventIds.has(e.id)) bad('events.json', `${at} appears twice`);
      eventIds.add(e.id);
      if (!EVENT_DATE.test(e.date ?? '')) bad('events.json', `${at}: date "${e.date}" is not YYYY-MM or YYYY-MM-DD`);
      if (e.end !== undefined && !EVENT_DATE.test(e.end)) bad('events.json', `${at}: end "${e.end}" is not YYYY-MM or YYYY-MM-DD`);
      ids('events.json', at, e.chokepoints, chokepoints, 'chokepoints');
      ids('events.json', at, e.commodities, commodityIds, 'commodities');
      ids('events.json', at, e.countries, knownCountries, 'countries');
      ids('events.json', at, e.assets, assetIds, 'assets');
      if (e.checked !== undefined && !ISO_DATE.test(e.checked)) bad('events.json', `${at}: "checked" must be a date (YYYY-MM-DD)`);
      if (e.also !== undefined && (!Array.isArray(e.also) || e.also.some((x) => !x?.label || !/^https?:\/\//.test(x?.url ?? '')))) bad('events.json', `${at}: "also" must be a list of {label, url}`);
      if (e.series !== undefined) {
        if (typeof e.series !== 'object' || e.series === null || Array.isArray(e.series)) bad('events.json', `${at}: "series" must map a commodity to a price series`);
        else
          for (const [k, sid] of Object.entries(e.series)) {
            if (commodityIds && !commodityIds.has(k)) bad('events.json', `${at}: series for "${k}", which the atlas does not have`);
            if (priceSeries && priceSeries.get(sid) !== k) bad('events.json', `${at}: series "${sid}" is not a price series of "${k}"`);
          }
      }
    }
  }
  if (alerts !== null) {
    if (!Array.isArray(alerts)) return bad('alerts.json', 'is not a list');
    const seen = new Set();
    for (const a of alerts) {
      const at = `alert ${a.id}`;
      if (typeof a.id !== 'string' || !a.id) bad('alerts.json', 'an alert has no id');
      else if (seen.has(a.id)) bad('alerts.json', `${at} appears twice`);
      seen.add(a.id);
      if (!a.title || !a.text) bad('alerts.json', `${at}: title and text are required`);
      if (a.checked !== undefined && !ISO_DATE.test(a.checked)) bad('alerts.json', `${at}: "checked" must be the date the text was checked against its source (YYYY-MM-DD)`);
      if (a.reviewed !== undefined) bad('alerts.json', `${at}: "reviewed" is replaced by "checked", which only a text read against its source carries`);
      if (events !== null && !eventIds.has(a.event)) bad('alerts.json', `${at}: event "${a.event}" is not in events.json`);
      if (a.events !== undefined) {
        if (!Array.isArray(a.events) || a.events.length === 0 || a.events.some((x) => typeof x !== 'string')) bad('alerts.json', `${at}: "events" must be a list of event ids`);
        else {
          if (a.events[0] !== a.event) bad('alerts.json', `${at}: "event" must be the first of "events"`);
          if (new Set(a.events).size !== a.events.length) bad('alerts.json', `${at}: "events" lists an event twice`);
          if (events !== null) for (const x of a.events) if (!eventIds.has(x)) bad('alerts.json', `${at}: events names "${x}", which is not in events.json`);
        }
      }
      if (a.severity !== null && !SEVERITIES.includes(a.severity)) bad('alerts.json', `${at}: severity "${a.severity}" is not one of ${SEVERITIES.join(', ')}`);
      ids('alerts.json', at, a.chokepoints, chokepoints, 'chokepoints');
      ids('alerts.json', at, a.commodities, commodityIds, 'commodities');
      ids('alerts.json', at, a.countries, knownCountries, 'countries');
      if (!Array.isArray(a.measures) || a.measures.length === 0) bad('alerts.json', `${at}: no PortWatch figure (measures)`);
      for (const m of a.measures ?? []) {
        if (!(a.chokepoints ?? []).includes(m.chokepoint)) bad('alerts.json', `${at}: a figure for "${m.chokepoint}", which is not one of its passages`);
        if (!ISO_DATE.test(m.to ?? '')) bad('alerts.json', `${at}: the figure of ${m.chokepoint} has no date of last observation`);
        if (typeof m.transits?.now !== 'number') bad('alerts.json', `${at}: the figure of ${m.chokepoint} has no transits`);
        if (m.s !== 'portwatch') bad('alerts.json', `${at}: the figure of ${m.chokepoint} must credit portwatch`);
      }
      if (a.override !== undefined && !a.override?.reason) bad('alerts.json', `${at}: an override needs a reason`);
      if (a.override !== undefined) ids('alerts.json', at, a.override.addCountries, knownCountries, 'override.addCountries');
    }
  }
}

// node validate-freight.mjs [data folder]
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = path.resolve(process.argv[2] ?? path.join(path.dirname(fileURLToPath(import.meta.url)), '../../data'));
  const errors = [];
  validateFreight(root, errors);
  if (errors.length) {
    console.error(errors.slice(0, 50).join('\n'));
    console.error(`\n${errors.length} freight error(s)`);
    process.exit(1);
  }
  console.log('freight OK');
}
