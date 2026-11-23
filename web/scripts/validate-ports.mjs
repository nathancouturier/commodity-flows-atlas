/**
 * Checks of the port index of the search field (data/freight/ports.json, built by pipeline/freight/build_port_index.py):
 *  - every port has an id, a name and a country of countries/index.json or places.json, ids are unique;
 *  - `n` is a positive integer and `g` lists customs groups that have a lane file;
 *  - `lane`, when set, is the id of a lane of its lane file (the search opens that lane page), and every port that a
 *    pairs file names for a seaborne pair is in the index (a port the file lacks cannot be found);
 *  - the other way round, a port of the index is used by some pair, `n` is the number of pairs that use it, each group of
 *    `g` is a group that uses it, and its `lane` is a pair with a lane page that uses it (a port the pairs files no longer
 *    name, or a wrong count, would stay searchable until the next build);
 *  - every port that a main lane page names, in its `load` or `discharge` list or in one of its options, is in the index;
 *    a port that only lane pages name has `n` = the main lanes that name it, `g` their groups and `lane` one of them.
 * Called by validate-data.mjs; `node validate-ports.mjs [data folder]` runs it alone.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export function validatePorts(root, errors) {
  const file = path.join(root, 'freight/ports.json');
  const bad = (m) => errors.push(`freight/ports.json: ${m}`);
  if (!fs.existsSync(file)) return bad('missing (run pipeline/freight/build_port_index.py)');
  const doc = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (!Array.isArray(doc.ports) || !doc.ports.length) return bad('no ports');
  const countries = new Set(JSON.parse(fs.readFileSync(path.join(root, 'countries/index.json'), 'utf8')).map((c) => c.c));
  // places that customs data name and the country index lacks (Gibraltar, Christmas Island): plain text, no page
  const placesFile = path.join(root, 'countries/places.json');
  if (fs.existsSync(placesFile)) for (const p of JSON.parse(fs.readFileSync(placesFile, 'utf8'))) countries.add(p.c);
  const laneIds = new Map();
  const lanesOf = (g) => {
    if (!laneIds.has(g)) {
      const f = path.join(root, `freight/lanes/${g}.json`);
      laneIds.set(g, fs.existsSync(f) ? new Set(JSON.parse(fs.readFileSync(f, 'utf8')).lanes.map((l) => l.id)) : null);
    }
    return laneIds.get(g);
  };
  const seen = new Set();
  for (const p of doc.ports) {
    const at = `port ${p.id}`;
    if (!p.id || typeof p.name !== 'string' || !p.name) bad(`${at}: id and name are required`);
    if (seen.has(p.id)) bad(`${at}: duplicate id`);
    seen.add(p.id);
    if (typeof p.c !== 'string' || !/^[A-Z]{3}$/.test(p.c)) bad(`${at}: country code "${p.c}" is not an ISO 3 code`);
    else if (!countries.has(p.c)) bad(`${at}: country ${p.c} is in neither countries/index.json nor countries/places.json`);
    if (!Number.isInteger(p.n) || p.n < 1) bad(`${at}: n must be a positive integer`);
    if (!Array.isArray(p.g) || !p.g.length) bad(`${at}: g must list at least one group`);
    for (const g of p.g ?? []) if (!lanesOf(g)) bad(`${at}: group "${g}" has no lane file`);
    if (p.lane != null) {
      const g = String(p.lane).split(':')[0];
      if (!lanesOf(g)?.has(p.lane)) bad(`${at}: lane "${p.lane}" is not in freight/lanes/${g}.json`);
    }
  }
  // the ports the main lanes name (their lists and their options): port -> ids of the lanes, and the groups
  const laneNamed = new Map();
  const lanesDir = path.join(root, 'freight/lanes');
  if (fs.existsSync(lanesDir))
    for (const f of fs.readdirSync(lanesDir).filter((x) => x.endsWith('.json'))) {
      const d = JSON.parse(fs.readFileSync(path.join(lanesDir, f), 'utf8'));
      for (const l of d.lanes ?? []) {
        if (l.set !== 'main') continue;
        const named = new Set();
        for (const part of [l, ...(l.opts ?? [])])
          for (const c of ['load', 'discharge']) for (const id of [].concat(part[c] ?? [])) named.add(id);
        for (const id of named) {
          if (!laneNamed.has(id)) laneNamed.set(id, { lanes: new Set(), groups: new Set() });
          laneNamed.get(id).lanes.add(l.id);
          laneNamed.get(id).groups.add(d.group);
          if (!seen.has(id) && !laneNamed.get(id).missing) {
            laneNamed.get(id).missing = true; // said once per port
            bad(`lanes/${f}: port ${id} is not in the index (rebuild it)`);
          }
        }
      }
    }
  const pairsDir = path.join(root, 'freight/pairs');
  if (fs.existsSync(pairsDir)) {
    const count = new Map(); // port -> number of pairs that use it, as build_port_index.py counts them
    const groupsOf = new Map(); // port -> groups that use it
    const laneRows = new Map(); // port -> ids of the pairs with a lane page (flag 4) that use it
    for (const f of fs.readdirSync(pairsDir).filter((x) => x.endsWith('.json'))) {
      const d = JSON.parse(fs.readFileSync(path.join(pairsDir, f), 'utf8'));
      const ix = Object.fromEntries(d.cols.map((c, i) => [c, i]));
      const used = new Set();
      for (const r of d.rows)
        for (const c of ['load', 'dis']) {
          if (r[ix[c]] == null || r[ix[c]] < 0) continue;
          const id = d.ports[r[ix[c]]][0];
          used.add(id);
          count.set(id, (count.get(id) ?? 0) + 1);
          if (!groupsOf.has(id)) groupsOf.set(id, new Set());
          groupsOf.get(id).add(d.group);
          if (r[ix.f] & 4) {
            if (!laneRows.has(id)) laneRows.set(id, new Set());
            laneRows.get(id).add(`${d.group}:${r[ix.o]}-${r[ix.d]}`);
          }
        }
      for (const id of used) if (!seen.has(id)) bad(`pairs/${f}: port ${id} is not in the index (rebuild it)`);
    }
    for (const p of doc.ports) {
      const at = `port ${p.id}`;
      if (!count.has(p.id)) {
        const l = laneNamed.get(p.id);
        if (!l) bad(`${at}: no pairs file and no lane page uses it any more (rebuild the index)`);
        else {
          if (p.n !== l.lanes.size) bad(`${at}: n is ${p.n}, the lane pages that name it are ${l.lanes.size} (rebuild the index)`);
          for (const g of p.g ?? []) if (!l.groups.has(g)) bad(`${at}: group "${g}" has no lane page that names it`);
          if (p.lane != null && !l.lanes.has(p.lane)) bad(`${at}: lane "${p.lane}" does not name it`);
        }
      } else {
        if (p.n !== count.get(p.id)) bad(`${at}: n is ${p.n}, the pairs files have ${count.get(p.id)} pairs that use it (rebuild the index)`);
        for (const g of p.g ?? []) if (!groupsOf.get(p.id).has(g)) bad(`${at}: group "${g}" does not use it in the pairs files`);
        if (p.lane != null && !laneRows.get(p.id)?.has(p.lane)) bad(`${at}: lane "${p.lane}" is not a pair with a lane page that uses it`);
        if (p.lane == null && laneRows.get(p.id)?.size) bad(`${at}: it has no lane, but a pair with a lane page uses it`);
      }
    }
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = path.resolve(process.argv[2] ?? path.join(path.dirname(fileURLToPath(import.meta.url)), '../../data'));
  const errors = [];
  validatePorts(root, errors);
  if (errors.length) {
    console.error(errors.slice(0, 30).join('\n'));
    process.exit(1);
  }
  console.log('ports OK');
}
