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
const COLS = ['o', 'd', 'kt', 'm', 'load', 'dis', 'nm', 'cls', 'via', 'alt', 'f'];
/** Smallest tonnage (Mt) of a main lane: 0.05 unless the group is listed (PLAN 2.2). */
const FLOOR = { coffee: 0.02, cocoa: 0.02, cotton: 0.02, 'nickel-int': 0.02, 'copper-refined': 0.02, 'zinc-ore': 0.02, aluminium: 0.03, soyoil: 0.03 };
const floorOf = (g) => FLOOR[g] ?? 0.05;

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
    // the basis of a port (optional fifth element): an index in the file's `bases`
    if (doc.bases !== undefined && !(Array.isArray(doc.bases) && doc.bases.every((b) => typeof b === 'string'))) bad(file, 'bases is not a list of strings');
    for (const p of doc.ports) {
      if (Array.isArray(p) && p[4] != null && !(Number.isInteger(p[4]) && p[4] >= 0 && p[4] < (doc.bases?.length ?? 0))) bad(file, `port ${p[0]}: basis index ${p[4]} is not in bases`);
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
    // the shares are taken over `seaborne`: it must be the tonnes of the sea and transit rows (the rows keep 0.1 kt)
    if (typeof doc.seaborne !== 'number' || Math.abs(seaKt - doc.seaborne) > Math.max(0.001 * doc.seaborne, 0.1))
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
      if (lane.set === 'main' && !(lane.flow?.v >= floorOf(lane.p) - 1e-9)) bad(file, `${at}: a main lane of ${lane.flow?.v} Mt is under the ${floorOf(lane.p)} Mt floor of its group`);
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
  // a port that no gateway row sources (the typical ports of the older tables) is allowed with s = null, and said once
  if (unsourced.size) console.warn(`freight: ${unsourced.size} lane ports have no source yet (s = null): ${[...unsourced].sort().slice(0, 12).join(', ')}...`);
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
