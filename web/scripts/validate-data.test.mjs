/**
 * Tests of the range checks of scripts/validate-data.mjs on a copy of the data folder: the copy passes as the real
 * folder does, and a swapped coordinate pair, a share above 1, an implausible year and an unknown country code each fail.
 *
 *     node web/scripts/validate-data.test.mjs
 */
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'validate-data-'));
// the validator reads ../../data from its own folder: copy the scripts and the data side by side
fs.mkdirSync(path.join(tmp, 'web', 'scripts'), { recursive: true });
for (const f of fs.readdirSync(here)) if (f.endsWith('.mjs') && !f.endsWith('.test.mjs')) fs.copyFileSync(path.join(here, f), path.join(tmp, 'web', 'scripts', f));
fs.cpSync(path.resolve(here, '../../data'), path.join(tmp, 'data'), { recursive: true, dereference: true });
const data = path.join(tmp, 'data');
const run = () => spawnSync(process.execPath, [path.join(tmp, 'web', 'scripts', 'validate-data.mjs')], { encoding: 'utf8' });
const edit = (rel, fn) => {
  const p = path.join(data, rel);
  const before = fs.readFileSync(p, 'utf8');
  const doc = JSON.parse(before);
  fn(doc);
  fs.writeFileSync(p, JSON.stringify(doc));
  return () => fs.writeFileSync(p, before);
};
let n = 0;
const ok = (name, fn) => {
  fn();
  n++;
  console.log(`ok   ${name}`);
};

try {
  const base = run();
  const real = spawnSync(process.execPath, [path.join(here, 'validate-data.mjs')], { encoding: 'utf8' });
  ok('the copy of the data folder gives the same verdict as the real one', () => assert.equal(base.status, real.status, base.stderr.slice(0, 2000)));
  // the cases below need a folder that passes: the real one, as published
  assert.equal(base.status, 0, `the data folder does not pass the validator:\n${base.stderr.slice(0, 2000)}`);
  const geo = fs.readdirSync(path.join(data, 'infrastructure')).find((f) => f.endsWith('.geojson'));
  const findPoint = (doc) => doc.features.find((f) => f.geometry?.type === 'Point');
  ok('a point with longitude and latitude swapped is refused', () => {
    const undo = edit(`infrastructure/${geo}`, (doc) => {
      const f = findPoint(doc);
      f.geometry.coordinates = [10, 120];
    });
    const r = run();
    undo();
    assert.equal(r.status, 1);
    assert.match(r.stderr, /coordinates \[10, 120\] are not a longitude and a latitude/);
  });
  ok('a share above 1 is refused', () => {
    const lane = fs.readdirSync(path.join(data, 'freight', 'lanes'))[0];
    const undo = edit(`freight/lanes/${lane}`, (doc) => {
      const visit = (o) => {
        if (Array.isArray(o)) return o.some(visit);
        if (!o || typeof o !== 'object') return false;
        if (typeof o.share === 'number') {
          o.share = 7;
          return true;
        }
        return Object.values(o).some(visit);
      };
      assert.ok(visit(doc), 'no share in the lane file');
    });
    const r = run();
    undo();
    assert.equal(r.status, 1);
    assert.match(r.stderr, /share 7 is not between 0 and 1/);
  });
  ok('a figure dated in year 20240 is refused', () => {
    const undo = edit('commodities/copper.json', (doc) => {
      const visit = (o) => {
        if (Array.isArray(o)) return o.some(visit);
        if (!o || typeof o !== 'object') return false;
        if (typeof o.y === 'number' && typeof o.s === 'string') {
          o.y = 20240;
          return true;
        }
        return Object.values(o).some(visit);
      };
      assert.ok(visit(doc), 'no dated figure in copper.json');
    });
    const r = run();
    undo();
    assert.equal(r.status, 1);
    assert.match(r.stderr, /year 20240 is not plausible/);
  });
  ok('an unknown country code is refused', () => {
    const undo = edit('commodities/copper.json', (doc) => {
      const visit = (o) => {
        if (Array.isArray(o)) return o.some(visit);
        if (!o || typeof o !== 'object') return false;
        if (typeof o.c === 'string' && /^[A-Z]{3}$/.test(o.c)) {
          o.c = 'XQZ';
          return true;
        }
        return Object.values(o).some(visit);
      };
      assert.ok(visit(doc), 'no country code in copper.json');
    });
    const r = run();
    undo();
    assert.equal(r.status, 1);
    assert.match(r.stderr, /country code "XQZ" is not in countries\/index.json or places.json/);
  });
  // the coverage file: the walker that reads every `s` as a source id runs on it too, and its shape is checked
  const firstReason = (doc) => Object.keys(doc.reasons)[0];
  ok('the built coverage file passes, and the walker that reads every `s` as a source id does read it', () => {
    assert.equal(run().status, 0);
    const undo = edit('coverage.json', (doc) => {
      doc.reasons[firstReason(doc)].s = 'na';
    });
    const r = run();
    undo();
    assert.equal(r.status, 1);
    assert.match(r.stderr, /coverage\.json: unknown source "na" at \$\.reasons\.[a-z-]+/);
  });
  ok('a coverage file with a reason that has no state, or a state that is not one, is refused', () => {
    const undo = edit('coverage.json', (doc) => {
      doc.reasons[firstReason(doc)].st = 'missing';
    });
    const r = run();
    undo();
    assert.equal(r.status, 1);
    assert.match(r.stderr, /coverage\.json: reason [a-z-]+ needs a state \(na or nofree\) and a text/);
  });
  ok('a cell that names a reason that does not exist, or a state that does not match its reason, is refused', () => {
    let undo = edit('coverage.json', (doc) => {
      const cells = doc.pages.find((p) => Object.values(p.cells).some((c) => c.startsWith('na:'))).cells;
      const b = Object.keys(cells).find((k) => cells[k].startsWith('na:'));
      cells[b] = 'na:no-such-reason';
    });
    let r = run();
    undo();
    assert.equal(r.status, 1);
    assert.match(r.stderr, /names the reason "no-such-reason", which does not exist/);
    undo = edit('coverage.json', (doc) => {
      const cells = doc.pages.find((p) => Object.values(p.cells).some((c) => c.startsWith('na:'))).cells;
      const b = Object.keys(cells).find((k) => cells[k].startsWith('na:'));
      cells[b] = cells[b].replace('na:', 'nf:');
    });
    r = run();
    undo();
    assert.equal(r.status, 1);
    assert.match(r.stderr, /is nf: but the reason "[a-z-]+" is na/);
  });
  ok('a page of the index without a row, a row of no page and a cell that is not a state are refused', () => {
    let undo = edit('coverage.json', (doc) => {
      doc.pages.pop();
    });
    let r = run();
    undo();
    assert.equal(r.status, 1);
    assert.match(r.stderr, /coverage\.json: page [a-z-]+ has no row/);
    undo = edit('coverage.json', (doc) => {
      doc.pages.push({ id: 'unobtainium', cells: {} });
    });
    r = run();
    undo();
    assert.equal(r.status, 1);
    assert.match(r.stderr, /row "unobtainium" is not a page of commodities\/index\.json/);
    undo = edit('coverage.json', (doc) => {
      doc.pages[0].cells.production = 'yes';
    });
    r = run();
    undo();
    assert.equal(r.status, 1);
    assert.match(r.stderr, /production is "yes", not p, m, na:<reason> or nf:<reason>/);
  });
  ok('what the cells say about the data is not this check\'s business: a page that lost a block still passes (the guard decides, and can be overridden)', () => {
    const undo = edit('coverage.json', (doc) => {
      const row = doc.pages.find((p) => p.cells.price === 'p');
      row.cells.price = 'm';
      doc.work[row.id] = [...(doc.work[row.id] ?? []), 'price'];
    });
    const r = run();
    undo();
    assert.equal(r.status, 0, r.stderr.slice(0, 1000));
  });
  // the weekly port traffic folder: the cases build their own folder in the copy, from the PortWatch ids of its port assets
  const ptDir = path.join(data, 'freight', 'port-traffic');
  const ptIds = [...new Set(JSON.parse(fs.readFileSync(path.join(data, 'infrastructure', 'ports.geojson'), 'utf8')).features.map((f) => f.properties.portwatch).filter(Boolean))].sort();
  const TYPES = ['tanker', 'dry', 'container', 'other'];
  const portDoc = (id, weeks = 60) => {
    const block = (k) => Object.fromEntries(TYPES.map((t, j) => [t, Array.from({ length: weeks }, (_, i) => (k === 'calls' ? (i + j) % 7 : ((i * 3 + j) % 11)))]));
    const end = new Date(Date.UTC(2025, 0, 6) + (7 * weeks - 1) * 86_400_000).toISOString().slice(0, 10);
    return { id, name: `Port ${id}`, s: 'portwatch-port-traffic', y: end, start: '2025-01-06', step: 'week', u: 'kt', dp: 3, calls: block('calls'), exports: block('exports'), imports: block('imports') };
  };
  /** The folder: a file for each id of `have`, index.json with `none` and `pending`; `extra` is run on it afterwards. */
  const setPortTraffic = ({ have, none = [], pending = [], index = {}, extra } = {}) => {
    fs.rmSync(ptDir, { recursive: true, force: true });
    fs.mkdirSync(ptDir, { recursive: true });
    for (const id of have) fs.writeFileSync(path.join(ptDir, `${id}.json`), JSON.stringify(portDoc(id)));
    fs.writeFileSync(path.join(ptDir, 'index.json'), JSON.stringify({ checked: '2026-11-25', none, pending, ...index }));
    if (extra) extra();
  };
  const refused = (what) => {
    const r = run();
    assert.equal(r.status, 1, `${what}: the validator accepted it`);
    return r.stderr;
  };
  ok('the port traffic folder: a file for an id, an id in none and an id in pending each pass; the folder may be complete', () => {
    assert.ok(ptIds.length >= 3, 'the port assets carry fewer than three PortWatch ids');
    setPortTraffic({ have: [ptIds[0]], none: [ptIds[1]], pending: ptIds.slice(2) });
    const r = run();
    assert.equal(r.status, 0, r.stderr.slice(0, 1000));
    assert.match(r.stderr, /port traffic: \d+ of \d+ ports not read yet/);
    setPortTraffic({ have: ptIds.slice(1), none: [ptIds[0]] });
    assert.equal(run().status, 0);
    fs.writeFileSync(path.join(ptDir, 'index.json'), JSON.stringify({ checked: '2026-11-25', none: [ptIds[0]] }));
    assert.equal(run().status, 0, 'pending may be left out of a finished load');
  });
  ok('the port traffic folder: an id in neither a file, none nor pending is refused', () => {
    setPortTraffic({ have: ptIds.slice(1, -1), none: [ptIds[0]] });
    assert.match(refused('last id in neither'), new RegExp(`index-missing: ${ptIds.at(-1)} has no file and is in neither none nor pending`));
  });
  ok('the port traffic folder: an id with a file that is also in pending or in none is refused', () => {
    setPortTraffic({ have: ptIds.slice(1), pending: [ptIds[1], ptIds[0]].sort() });
    assert.match(refused('file and pending'), /index-both: port\w+ has a file and is in pending/);
    setPortTraffic({ have: ptIds.slice(1), none: [ptIds[0], ptIds[1]].sort() });
    assert.match(refused('file and none'), /index-both: port\w+ has a file and is in none/);
  });
  ok('the port traffic folder: an id that no port asset carries is refused, in a file, in none and in pending', () => {
    setPortTraffic({ have: ptIds, extra: () => fs.writeFileSync(path.join(ptDir, 'port99999.json'), JSON.stringify(portDoc('port99999'))) });
    assert.match(refused('orphan file'), /the file of port99999 is for no port asset/);
    setPortTraffic({ have: ptIds, pending: ['port99999'] });
    assert.match(refused('orphan pending'), /port99999 is in pending but no port asset carries it/);
  });
  ok('the port traffic folder: a file that breaks a rule, a file that is not the port\'s own and a leftover .tmp are refused', () => {
    setPortTraffic({ have: ptIds, extra: () => {
      const f = path.join(ptDir, `${ptIds[0]}.json`);
      const d = JSON.parse(fs.readFileSync(f, 'utf8'));
      d.exports.tanker.pop();
      fs.writeFileSync(f, JSON.stringify(d));
    } });
    assert.match(refused('unequal arrays'), new RegExp(`${ptIds[0]}.json: series: the twelve arrays are not all of the same length`));
    setPortTraffic({ have: ptIds, extra: () => {
      const f = path.join(ptDir, `${ptIds[0]}.json`);
      fs.writeFileSync(f, JSON.stringify({ ...portDoc(ptIds[0]), id: ptIds[1] }));
    } });
    assert.match(refused('another id'), new RegExp(`${ptIds[0]}.json: id:`));
    setPortTraffic({ have: ptIds, extra: () => fs.writeFileSync(path.join(ptDir, `${ptIds[0]}.json.tmp`), '{') });
    assert.match(refused('tmp'), /\.json\.tmp: not a port file or index\.json/);
  });
  ok('the port traffic folder: no index.json, or no folder while port assets carry ids, is refused', () => {
    setPortTraffic({ have: ptIds, extra: () => fs.rmSync(path.join(ptDir, 'index.json')) });
    assert.match(refused('no index'), /freight\/port-traffic\/index\.json: missing/);
    fs.rmSync(ptDir, { recursive: true, force: true });
    assert.match(refused('no folder'), /freight\/port-traffic: missing, and \d+ port assets carry a PortWatch id/);
  });
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}
console.log(`validate-data: ${n} checks passed`);
