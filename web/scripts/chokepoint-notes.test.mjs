/**
 * The passage records (data/freight/chokepoints.json): the figure a note of an estimate says is the one the page prints (the page rounds
 * the stored tonnage with Intl.NumberFormat, three significant digits, or one decimal of a kt; GV6D.9), and the comparison of a ship type
 * with IMF PortWatch is written once on the passage (`typeNotes`), not in each estimate (GV6D.1): `node --test web/scripts/chokepoint-notes.test.mjs`.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

// CHOKEPOINTS: another copy of the file to read (to show that the test fails on the earlier one)
const chk = JSON.parse(readFileSync(process.env.CHOKEPOINTS ?? new URL('../../data/freight/chokepoints.json', import.meta.url), 'utf8'));
// the formatters of ChokepointView.tsx
const nf3 = new Intl.NumberFormat('en-US', { maximumSignificantDigits: 3 });
const nf1 = new Intl.NumberFormat('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const printed = (v, kt) => (kt ? `${nf1.format(v * 1e3)} kt` : `${nf3.format(v)} Mt`);
const FIG = '([\\d,.]+ (?:Mt|kt)|under 0\\.1 kt)';

test('the figure of the note is the figure of the page, in every estimate', () => {
  let n = 0;
  for (const c of chk) {
    for (const e of c.estimates ?? []) {
      const lo = new RegExp(`^at least ${FIG} of `).exec(e.f.n);
      const small = /([\d,.]+) (Mt|kt) of seaborne/.exec(e.f.n)?.[2] === 'kt'; // a group under 1 Mt is printed in kt
      if (lo) {
        assert.equal(lo[1], printed(e.mt[0], small), `${c.id} ${e.p}: "at least" of the note against the page`);
        n++;
      }
      if (e.hi) {
        const up = new RegExp(`^up to ${FIG}`).exec(e.hi.n);
        assert.ok(up, `${c.id} ${e.p}: the note of the "up to" figure starts with it`);
        assert.equal(up[1], printed(e.mt[1], small), `${c.id} ${e.p}: "up to" of the note against the page`);
        n++;
      }
    }
  }
  assert.ok(n > 800, `${n} figures compared`);
});

test('the example of the review: sunflower meal at the Bosphorus is 5.87 Mt in the note as on the page', () => {
  const e = chk.find((c) => c.id === 'bosphorus').estimates.find((x) => x.p === 'sunflower-meal');
  assert.equal(nf3.format(e.mt[0]), '5.87');
  assert.match(e.f.n, /^at least 5\.87 Mt of /);
});

test('the note of a ship type is on the passage and not repeated in the estimates', () => {
  let types = 0;
  for (const c of chk) {
    for (const e of c.estimates ?? []) assert.doesNotMatch(`${e.f.n} ${e.hi?.n ?? ''}`.replace(/capped at IMF PortWatch's estimate/g, ''), /PortWatch's (?:volume|estimate)|best full year/, `${c.id} ${e.p}`);
    for (const [t, tn] of Object.entries(c.typeNotes ?? {})) {
      types++;
      assert.ok(['dry', 'tanker', 'cargo'].includes(t), `${c.id}: ship type ${t}`);
      assert.ok(c.estimates?.some((e) => e.p), `${c.id}: a note of a type belongs to a passage with estimates`);
      assert.ok(tn.line.length > 40 && tn.line.length < 260, `${c.id} ${t}: one short line (${tn.line.length} characters)`);
      assert.ok(tn.n.length > tn.line.length, `${c.id} ${t}: the reason is longer than the line`);
      assert.ok(['whole', 'none', 'sub', null].includes(tn.regime), `${c.id} ${t}: regime ${tn.regime}`);
      assert.ok(tn.groups >= tn.capped && tn.groups > 0, `${c.id} ${t}: groups and capped`);
      assert.match(tn.n, /estimate made from ship movements/, `${c.id} ${t}: PortWatch's volume is said to be an estimate`);
      assert.match(tn.n, /not all the cargo these ships carry/, `${c.id} ${t}: the atlas's groups are a part of the cargo`);
      if (tn.cmp === 'above') assert.ok(tn.low > (tn.ref ?? 0) || tn.low > 1.1 * tn.best, `${c.id} ${t}: "above" says the atlas is above PortWatch`);
      else assert.ok(tn.low <= tn.ref && tn.low > 0.85 * tn.ref, `${c.id} ${t}: "near" is within 85% to 100%`);
      if (tn.regime === 'whole') assert.match(tn.n, /cannot exceed the whole of PortWatch's volume/);
      if (tn.regime === 'none') assert.match(tn.n, /not capped at PortWatch's volume here/);
      // the cap is said where it binds: the number of capped figures of the type is the number of estimates tagged
      const tagged = (c.estimates ?? []).filter((e) => /capped/i.test(e.hi?.n ?? '') && typeOf(e.p) === t).length;
      if (tn.regime === 'whole') assert.equal(tn.capped, tagged, `${c.id} ${t}: capped figures`);
    }
  }
  assert.ok(types >= 10, `${types} notes of ship types`);
});

// the ship type of a group, as build_freight.py names it (only the groups that appear in a note matter here)
const TANKER = new Set(['crude-oil', 'refined-products', 'lng', 'lpg', 'palm-oil', 'soyoil', 'ammonia', 'uan', 'phosphoric-acid', 'sunflower-oil', 'rapeseed-oil']);
function typeOf(p) {
  return TANKER.has(p) ? 'tanker' : cargoGroups.has(p) ? 'cargo' : 'dry';
}
const cargoGroups = new Set(['steel', 'copper-refined', 'aluminium', 'coffee', 'cocoa', 'cotton']);
