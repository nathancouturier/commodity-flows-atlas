/**
 * Tests of the fold of the controls on a tablet (src/lib/layoutQueries.ts `foldStep`, wired to the signals by
 * src/lib/tablet.ts) and of the layout predicates: `node --test web/scripts/tablet-fold.test.mjs`.
 * The pure module imports nothing, so it runs as it is; the wiring, which needs the signals, is checked as text here and in a browser.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { TABLET_QUERY, SHEET_QUERY, isTabletLayout, isSheetLayout, foldStep } from '../src/lib/layoutQueries.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (rel) => fs.readFileSync(path.join(here, '..', rel), 'utf8');

/** A visitor's session: each event is applied to the state the fold keeps (before) and the signal it writes (collapsed). */
function session(start = { collapsed: false }) {
  let before = null;
  let collapsed = start.collapsed;
  const step = (open, isTablet = true) => {
    const next = foldStep({ open, isTablet, before, collapsed });
    before = next.before;
    collapsed = next.collapsed;
  };
  return {
    step,
    openPage: (isTablet) => step(true, isTablet),
    closePage: (isTablet) => step(false, isTablet),
    visitorFolds: () => { collapsed = true; },
    visitorOpens: () => { collapsed = false; },
    get collapsed() { return collapsed; },
    get before() { return before; },
  };
}

test('a page opens: the controls fold; the page closes: they return', () => {
  const s = session();
  assert.equal(s.collapsed, false);
  s.openPage();
  assert.equal(s.collapsed, true);
  assert.equal(s.before, false);
  s.closePage();
  assert.equal(s.collapsed, false);
  assert.equal(s.before, null);
});

test('the controls were folded by the visitor before the page: they stay folded when it closes', () => {
  const s = session({ collapsed: true });
  s.openPage();
  assert.equal(s.collapsed, true);
  assert.equal(s.before, true);
  s.closePage();
  assert.equal(s.collapsed, true);
  assert.equal(s.before, null);
});

test('the visitor opens the controls over the page and the page closes: they stay open', () => {
  const s = session();
  s.openPage();
  s.visitorOpens();
  s.closePage();
  assert.equal(s.collapsed, false);
  const f = session({ collapsed: true });
  f.openPage();
  f.visitorOpens();
  f.closePage();
  assert.equal(f.collapsed, false, 'folded before, opened over the page: still open');
});

test('the visitor folds the controls again over the page: the close gives back what they were before the page', () => {
  const s = session();
  s.openPage();
  s.visitorOpens();
  s.visitorFolds();
  s.closePage();
  assert.equal(s.collapsed, false);
});

test('opening a second page while one is open does not overwrite what was kept', () => {
  const s = session();
  s.openPage();
  s.openPage();
  assert.equal(s.before, false);
  s.closePage();
  assert.equal(s.collapsed, false);
  const f = session({ collapsed: true });
  f.openPage();
  f.openPage();
  f.closePage();
  assert.equal(f.collapsed, true);
});

test('not a tablet: nothing folds and what was kept is forgotten', () => {
  const s = session();
  s.openPage(false);
  assert.equal(s.collapsed, false);
  assert.equal(s.before, null);
  s.closePage(false);
  assert.equal(s.collapsed, false);
  // a page opened on a tablet, then the next step happens on a desktop width: the memory is reset, the fold is left as it is
  const t = session();
  t.openPage(true);
  assert.equal(t.before, false);
  t.step(true, false);
  assert.equal(t.before, null);
  assert.equal(t.collapsed, true);
  t.closePage(true);
  assert.equal(t.collapsed, true, 'the next close on a tablet has nothing to give back');
});

test('a step that changes nothing returns the same state', () => {
  assert.deepEqual(foldStep({ open: false, isTablet: true, before: null, collapsed: false }), { before: null, collapsed: false });
  assert.deepEqual(foldStep({ open: false, isTablet: true, before: null, collapsed: true }), { before: null, collapsed: true });
  assert.deepEqual(foldStep({ open: true, isTablet: true, before: false, collapsed: true }), { before: false, collapsed: true });
});

// ---------------------------------------------------------------- the predicates with a fake matchMedia

/** Evaluates the width and height features the atlas's queries use (clauses joined by "and", alternatives by commas). */
function fake(w, h) {
  const clause = (c) => {
    const m = /^\(\s*(min|max)-(width|height)\s*:\s*([\d.]+)px\s*\)$/.exec(c.trim());
    assert.ok(m, `a clause the evaluator knows: ${c}`);
    const v = m[2] === 'width' ? w : h;
    return m[1] === 'min' ? v >= Number(m[3]) : v <= Number(m[3]);
  };
  return (q) => ({ matches: q.split(',').some((alt) => alt.split(/\s+and\s+/).every(clause)) });
}

test('the predicates follow the queries', () => {
  assert.equal(isTabletLayout(fake(820, 1180)), true);
  assert.equal(isSheetLayout(fake(820, 1180)), false, 'a tablet is not the sheet layout');
  assert.equal(isSheetLayout(fake(390, 844)), true);
  assert.equal(isTabletLayout(fake(390, 844)), false);
  assert.equal(isSheetLayout(fake(844, 390)), true, 'a phone held sideways');
  assert.equal(isTabletLayout(fake(844, 390)), false);
  assert.equal(isSheetLayout(fake(1440, 900)), false);
  assert.equal(isTabletLayout(fake(1440, 900)), false);
  assert.equal(isSheetLayout(fake(1024, 500)), true);
  assert.equal(isTabletLayout(fake(1024, 501)), true);
  assert.equal(isSheetLayout(fake(900, 500.5)), true, 'a fractional height between 500 and 501 is the phone, in the script as in the CSS');
  assert.equal(isTabletLayout(fake(900, 500.5)), false);
  assert.equal(isSheetLayout(fake(760, 1000)), true);
  assert.equal(isTabletLayout(fake(761, 1000)), true);
  assert.equal(isSheetLayout(fake(1025, 768)), false);
});

test('the predicates read matchMedia only when no function is given', () => {
  const asked = [];
  isTabletLayout((q) => (asked.push(q), { matches: false }));
  isSheetLayout((q) => (asked.push(q), { matches: false }));
  assert.deepEqual(asked, [TABLET_QUERY, SHEET_QUERY], 'the second predicate stops at the first false query');
  assert.equal(typeof window, 'undefined', 'this test runs without a window');
});

// ---------------------------------------------------------------- the wiring, as text

test('the effect hands the fold to foldStep and writes panelCollapsed', () => {
  const t = read('src/lib/tablet.ts');
  assert.match(t, /import \{ effect \} from '@preact\/signals';/);
  assert.match(t, /import \{[^}]*\bpanelCollapsed\b[^}]*\} from '\.\/store';/);
  assert.match(t, /import \{[^}]*\bselection\b[^}]*\} from '\.\/store';/);
  assert.match(t, /import \{[^}]*\bfoldStep\b[^}]*\} from '\.\/layoutQueries';/);
  assert.match(t, /foldStep\(\{/);
  assert.match(t, /selection\.value/);
  assert.match(t, /panelCollapsed\.value\s*=/);
  assert.doesNotMatch(t, /localStorage|sessionStorage|indexedDB/, 'nothing is stored in the browser');
});

test('the query module imports nothing and nothing stores the fold', () => {
  const q = read('src/lib/layoutQueries.ts');
  assert.doesNotMatch(q, /^\s*import\s/m);
  assert.doesNotMatch(q, /localStorage|sessionStorage/);
});

test('main starts the fold before the catalogue loads', () => {
  const m = read('src/main.tsx');
  assert.match(m, /import \{ startTabletFold \} from '\.\/lib\/tablet';/);
  const call = m.search(/^startTabletFold\(\);/m);
  assert.ok(call > 0, 'main.tsx calls startTabletFold()');
  assert.ok(call < m.indexOf('loadCatalogue()'), 'the call comes before loadCatalogue()');
  assert.ok(call < m.indexOf('render('), 'the call comes before the first render');
});

test('the controller and the finder use the predicates of the query module', () => {
  const c = read('src/map/controller.ts');
  assert.match(c, /from '\.\.\/lib\/layoutQueries';/);
  assert.match(c, /export \{ isSheetLayout, isTabletLayout \};/);
  assert.doesNotMatch(c, /SHEET_BP|sheetQuery|window\.matchMedia\(sheet/);
  const s = read('src/lib/search.ts');
  assert.match(s, /if \(isSheetLayout\(\) \|\| isTabletLayout\(\)\) \{\s*select\(null\);/);
});
