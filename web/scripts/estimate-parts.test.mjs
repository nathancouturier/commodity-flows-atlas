/**
 * The two parts of an estimated share (a volume of the United States' own statistics, the declared value) are printed beside their total on the
 * lane table, the commodity page and the country pages: each part is the true one at its own rounding, and the printed parts add to the printed
 * total within one unit of the last digit (three rounded figures cannot always add exactly). `node web/scripts/estimate-parts.test.mjs`
 */
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { test } from 'node:test';
import { estimateParts, estimatedShare, estimatedVolume } from '../src/lib/estimateShares.ts';

const data = new URL('../../data/', import.meta.url);
const json = (rel) => JSON.parse(readFileSync(new URL(rel, data), 'utf8'));
const lanes = readdirSync(new URL('freight/lanes/', data)).filter((f) => f.endsWith('.json')).map((f) => [f, json(`freight/lanes/${f}`)]);
const pct1 = (s) => (s * 100).toFixed(1);
const near = (a, b, step, msg) => assert.ok(Math.abs(a - b) <= step + 1e-9, msg);

test('lane files: every printed pair of parts adds to its total at the precision printed, and the value part is the true one', () => {
  let n = 0;
  for (const [name, f] of lanes) {
    for (const yr of f.years) {
      const e = estimatedShare(f, yr);
      if (!e) continue;
      const vol = estimatedVolume(f, e.year);
      if (vol <= 0) continue;
      const p = estimateParts(e.share, vol);
      near(Number(pct1(e.share)), Number(pct1(p.volume)) + Number(pct1(p.value)), 0.1, `${name} ${yr}: ${pct1(e.share)} against ${pct1(p.volume)} + ${pct1(p.value)}`);
      // the tonnes of the declared-value part are in the year's note: the share printed for them is the part
      const note = f.yearNotes?.[String(e.year)] ?? '';
      const t = /from declared value \(([\d.,]+) (Mt|kt)\)/.exec(note);
      if (t) {
        const mt = Number(t[1].replace(/,/g, '')) / (t[2] === 'kt' ? 1e3 : 1);
        const sea = f.seaborne[f.years.indexOf(e.year)];
        assert.equal(pct1(p.value), pct1(mt / sea), `${name} ${yr}: the declared-value part against its tonnes (${t[0]} of ${sea})`);
      }
      n++;
    }
  }
  assert.ok(n >= 1, 'at least the LPG file has a part made from a volume');
});

test('the latest year of the LPG file: 4.2% of which 2.9% from a volume and 1.2% from the declared value (it was 1.3%: two rounded shares subtracted)', () => {
  const f = lanes.find(([n]) => n === 'lpg.json')[1];
  const e = estimatedShare(f, null);
  const p = estimateParts(e.share, estimatedVolume(f, e.year));
  assert.deepEqual([pct1(e.share), pct1(p.volume), pct1(p.value)], ['4.2', '2.9', '1.2']);
});

test('country pages: a share or a tonnage of estimate and its part from a volume add up at the precision printed', () => {
  let n = 0;
  const walk = (v, where) => {
    if (Array.isArray(v)) return v.forEach((x, i) => walk(x, `${where}[${i}]`));
    if (!v || typeof v !== 'object') return;
    if (v.estShare != null && v.estVolShare) {
      const p = estimateParts(v.estShare, v.estVolShare);
      near(Number(pct1(v.estShare)), Number(pct1(p.volume)) + Number(pct1(p.value)), 0.1, `${where}: ${pct1(v.estShare)} against ${pct1(p.volume)} + ${pct1(p.value)}`);
      n++;
    }
    if (v.estKt != null && v.estVolKt) {
      const mt = (x) => (x / 1000).toFixed(2); // fmt() of a tonnage between 1 and 10 Mt
      near(Number(mt(v.estKt)), Number(mt(v.estVolKt)) + Number(mt(v.estKt - v.estVolKt)), 0.01, `${where}: ${mt(v.estKt)} against ${mt(v.estVolKt)} + ${mt(v.estKt - v.estVolKt)}`);
      n++;
    }
    for (const [k, x] of Object.entries(v)) walk(x, `${where}.${k}`);
  };
  for (const f of readdirSync(new URL('countries/profiles/', data)).filter((x) => x.endsWith('.json'))) walk(json(`countries/profiles/${f}`), f);
  assert.ok(n >= 4, 'the profiles of the United States and Mexico carry them');
});

test('estimateParts is the difference of the two shares to four decimals', () => {
  assert.deepEqual(estimateParts(0.0418, 0.0294), { volume: 0.0294, value: 0.0124 });
});
