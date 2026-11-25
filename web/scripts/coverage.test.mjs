/**
 * The Quality tab and the folded section of the commodity pages (lib/coverage.ts, components/Coverage.tsx, components/PageGaps.tsx).
 * The module has no import, so Node runs the TypeScript file as it is. The counts are read from data/coverage.json and recounted here
 * from the raw cell strings, so that no number is typed in a test or in a component.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { SHOW_MISSING_ON_PAGES, STATE_NAME, STATE_WORDS, allCells, coverageCounts, pageGaps, parseCell, reasonCounts } from '../src/lib/coverage.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const src = (rel) => fs.readFileSync(path.join(here, '../src', rel), 'utf8');
const file = JSON.parse(fs.readFileSync(path.join(here, '../../data/coverage.json'), 'utf8'));
const index = JSON.parse(fs.readFileSync(path.join(here, '../../data/commodities/index.json'), 'utf8'));
const raw = file.pages.flatMap((p) => Object.entries(p.cells).map(([block, c]) => ({ page: p.id, block, c })));

test('the pages show the missing blocks only when the constant says so, and today it says no', () => {
  assert.equal(SHOW_MISSING_ON_PAGES, false);
  assert.match(src('components/PageGaps.tsx'), /pageGaps\(file, props\.id, SHOW_MISSING_ON_PAGES\)/);
});

test('the section of a page lists exactly its cells that are not present and not hidden', () => {
  for (const hidden of [true, false]) {
    for (const p of file.pages) {
      const expect = Object.values(p.cells).filter((c) => c !== 'p' && !(c === 'm' && hidden)).length;
      assert.equal(pageGaps(file, p.id, !hidden).length, expect, `${p.id} (missing ${hidden ? 'hidden' : 'shown'})`);
    }
  }
  // with the missing blocks hidden, a line is a block the page cannot have and it always carries its reason
  for (const p of file.pages)
    for (const g of pageGaps(file, p.id, false)) {
      assert.ok(g.state === 'na' || g.state === 'nf', `${p.id} ${g.block.id}`);
      assert.ok(g.reason && g.reason.length > 0, `${p.id} ${g.block.id} has no reason`);
    }
  assert.deepEqual(pageGaps(file, 'no-such-page', true), []);
});

test('a page with no such block draws no section, and the lines follow the order of the blocks', () => {
  const none = file.pages.filter((p) => !Object.values(p.cells).some((c) => c !== 'p' && c !== 'm'));
  assert.ok(none.length > 0);
  for (const p of none) assert.equal(pageGaps(file, p.id, false).length, 0, p.id);
  const ids = file.blocks.map((b) => b.id);
  for (const p of file.pages) {
    const got = pageGaps(file, p.id, true).map((g) => ids.indexOf(g.block.id));
    assert.deepEqual(got, [...got].sort((a, b) => a - b), p.id);
  }
});

test('the grid has as many cells as the file, one per block the page can have', () => {
  const cells = allCells(file);
  assert.equal(cells.length, raw.length);
  // an independent recount by family: a block with `families` is a cell of those pages only
  const family = Object.fromEntries(index.map((c) => [c.id, c.family]));
  let expected = 0;
  for (const p of file.pages) for (const b of file.blocks) if (!b.families || b.families.includes(family[p.id])) expected++;
  assert.equal(cells.length, expected);
  assert.deepEqual(file.pages.map((p) => p.id), index.map((c) => c.id), 'one row per page of the index, in its order');
});

test('the counts the tab prints are the recount of the raw cells', () => {
  const n = coverageCounts(file);
  const head = (c) => c.split(':')[0];
  assert.equal(n.p, raw.filter((r) => r.c === 'p').length);
  assert.equal(n.m, raw.filter((r) => r.c === 'm').length);
  assert.equal(n.na, raw.filter((r) => head(r.c) === 'na').length);
  assert.equal(n.nf, raw.filter((r) => head(r.c) === 'nf').length);
  assert.equal(n.total, raw.length);
  assert.equal(n.p + n.m + n.na + n.nf, n.total);
  assert.equal(n.applicable, n.total - n.na);
  const reasons = reasonCounts(file);
  assert.deepEqual(reasons.map((r) => r.id), Object.keys(file.reasons), 'the reasons in the order of the table');
  assert.equal(reasons.reduce((a, r) => a + r.cells, 0), n.na + n.nf);
});

test('a cell names its state and its reason as the file gives them', () => {
  for (const r of raw) {
    const c = parseCell(file, r.c);
    if (r.c === 'p' || r.c === 'm') assert.deepEqual(c, { state: r.c, reason: null });
    else {
      const [st, id] = [r.c.split(':')[0], r.c.slice(r.c.indexOf(':') + 1)];
      assert.equal(c.state, st);
      assert.equal(c.reason, file.reasons[id].t, `${r.page}/${r.block}`);
      assert.equal(file.reasons[id].st, st === 'na' ? 'na' : 'nofree');
    }
  }
  assert.equal(STATE_NAME.na, 'not applicable');
  assert.equal(STATE_NAME.nf, 'not available for free');
  assert.equal(STATE_WORDS.m, 'not in the atlas yet');
  assert.equal(STATE_NAME.p, 'present');
  assert.equal(STATE_NAME.m, 'missing');
});

test('the Quality tab is the sixth tab, loads the file when it opens and keeps nothing', () => {
  assert.match(src('components/AboutHost.tsx'), /export type AboutTab = [^;]*'freshness' \| 'quality' \| 'method'/);
  const dialog = src('components/AboutDialog.tsx');
  assert.match(dialog, /\{ id: 'freshness', label: 'Data freshness' \},\n\s*\{ id: 'quality', label: 'Quality' \},/);
  assert.match(dialog, /tab === 'quality' \? \(\s*<QualityTabView \/>/);
  // the file is requested by the tab and by the commodity page, never at load, never by the window's own effect
  for (const f of ['components/AboutHost.tsx', 'components/AboutDialog.tsx', 'main.tsx', 'lib/data.ts']) assert.doesNotMatch(src(f), /coverage\.json/, f);
  assert.match(src('components/Coverage.tsx'), /useEffect\(\(\) => \{[\s\S]*loadOptional<CoverageFile>\('coverage\.json'\)/);
  // nothing is stored and the address is not touched
  for (const f of ['components/Coverage.tsx', 'components/PageGaps.tsx', 'lib/coverage.ts']) assert.doesNotMatch(src(f), /localStorage|sessionStorage|indexedDB|location\.|history\.|\.hash\b/, f);
  // the row opens the commodity page, as the chips of the panels do
  assert.match(src('components/Coverage.tsx'), /openCommodity\(r\.id\);\s*closeAbout\(\);/);
});

test('no count of the matrix is typed in a component, and no block is called verified or complete', () => {
  const n = coverageCounts(file);
  const typed = [n.total, n.applicable, n.p, n.m, n.na].map(String);
  for (const f of ['components/Coverage.tsx', 'components/PageGaps.tsx', 'lib/coverage.ts', 'styles/coverage.css'])
    for (const t of typed) assert.doesNotMatch(src(f).replace(/\d+(?:\.\d+)?(?:px|%|em)/g, ''), new RegExp(`(?<![\\w.#-])${t}(?![\\w.-])`), `${f} types ${t}`);
  for (const f of ['components/Coverage.tsx', 'components/PageGaps.tsx']) assert.doesNotMatch(src(f), /verified|complete/i, f);
});

test('the folded section sits at the foot of the commodity page, after the Notes', () => {
  const v = src('components/views/CommodityView.tsx');
  assert.ok(v.indexOf('<PageGaps id={id} />') > v.indexOf('title="Notes"'));
  assert.equal(v.split('<PageGaps').length - 1, 1);
});
