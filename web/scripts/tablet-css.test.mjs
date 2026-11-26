/**
 * Tests of the tablet layout's stylesheet (src/styles/tablet.css) and of the three layouts' queries: `node --test web/scripts/tablet-css.test.mjs`.
 * The file must be one @media rule whose condition is TABLET_QUERY, every selector of it must beat the single-class rules it overrides,
 * the phone, the tablet and the desktop must share the widths and heights exactly, and the stylesheets it overrides must still hold
 * the rules it relies on. The stylesheets are read as text from the source, never from a build.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { TABLET_QUERY, SHEET_QUERY, isTabletLayout, isSheetLayout } from '../src/lib/layoutQueries.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (rel) => fs.readFileSync(path.join(here, '..', rel), 'utf8');
const stripComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '');
const norm = (s) => s.replace(/\s+/g, ' ').trim();

const tabletCss = read('src/styles/tablet.css');
const appCss = read('src/styles/app.css');
const drawersCss = read('src/styles/drawers.css');
const mainTsx = read('src/main.tsx');

/** The block of the one @media rule: its condition and its body, found by balancing the braces. */
function theBlock(css) {
  const text = stripComments(css).trim();
  assert.ok(text.startsWith('@media'), 'the file starts with its @media rule');
  const open = text.indexOf('{');
  let depth = 0;
  let end = -1;
  for (let i = open; i < text.length; i++) {
    if (text[i] === '{') depth++;
    else if (text[i] === '}' && --depth === 0) { end = i; break; }
  }
  assert.ok(end > 0, 'the braces balance');
  return { condition: norm(text.slice('@media'.length, open)), body: text.slice(open + 1, end), after: text.slice(end + 1).trim() };
}

test('the file is exactly one @media rule, and its condition is TABLET_QUERY', () => {
  const { condition, body, after } = theBlock(tabletCss);
  assert.equal(condition, norm(TABLET_QUERY));
  assert.equal(after, '', 'nothing follows the rule');
  assert.doesNotMatch(body, /@media|@container|@supports|@import|@font-face|@keyframes/, 'no at-rule inside it');
  assert.equal((body.match(/\{/g) || []).length, (body.match(/\}/g) || []).length, 'the braces of the body balance');
});

test('every selector starts with `html .app`, or is :root', () => {
  const { body } = theBlock(tabletCss);
  const rules = [...body.matchAll(/([^{}]+)\{([^{}]*)\}/g)];
  assert.ok(rules.length > 20, 'the rules were found');
  const bad = [];
  for (const [, sel] of rules) {
    for (const one of sel.split(',').map((s) => norm(s))) {
      if (!(one === ':root' || /^html \.app(\s|\.|:|$)/.test(one))) bad.push(one);
    }
  }
  assert.deepEqual(bad, [], 'selectors that would not beat the single-class rules of app.css and drawers.css');
});

test('every variable the file uses is defined somewhere', () => {
  const defined = new Set();
  const sources = [];
  const walk = (dir) => {
    for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, f.name);
      if (f.isDirectory()) walk(p);
      else if (/\.(css|tsx?)$/.test(f.name)) sources.push(fs.readFileSync(p, 'utf8'));
    }
  };
  walk(path.join(here, '../src'));
  for (const s of sources) {
    for (const m of s.matchAll(/(--[a-z0-9-]+)\s*:/g)) defined.add(m[1]);
    for (const m of s.matchAll(/setProperty\('(--[a-z0-9-]+)'/g)) defined.add(m[1]);
  }
  const used = new Set([...stripComments(tabletCss).matchAll(/var\((--[a-z0-9-]+)/g)].map((m) => m[1]));
  assert.ok(used.size >= 8, 'the file uses the variables of the layout');
  for (const v of used) assert.ok(defined.has(v), `${v} is defined`);
});

test('the folded Controls button keeps its width with History open', () => {
  // drawers.css gives the controls four-class selectors while the timeline is open; the button must out-weigh them
  const { body } = theBlock(tabletCss);
  const rule = [...body.matchAll(/([^{}]+)\{([^{}]*)\}/g)].find(([, , decl]) => /^\s*width: auto;\s*$/.test(decl));
  assert.ok(rule, 'a rule that gives the folded panel its own width');
  const sels = rule[1].split(',').map((x) => norm(x));
  for (const snap of ['snap-half', 'snap-full']) assert.ok(sels.includes(`html .app.tl-open .side-panel.${snap}.collapsed`), snap);
});

test('the page ends above the History bar', () => {
  const { body } = theBlock(tabletCss);
  assert.match(body, /html \.app\.tl-open \.detail-panel[^{}]*\{\s*bottom: calc\(var\(--tl-h, 0px\) \+ var\(--gap\) \* 2\);/);
});

// ---------------------------------------------------------------- the partition of the three layouts

/** A small evaluator of the width and height features of a media query: clauses joined by "and", alternatives by commas. */
function matches(query, w, h) {
  const clause = (c) => {
    const m = /^\(\s*(min|max)-(width|height)\s*:\s*([\d.]+)px\s*\)$/.exec(c.trim());
    assert.ok(m, `a clause the evaluator knows: ${c}`);
    const v = m[2] === 'width' ? w : h;
    return m[1] === 'min' ? v >= Number(m[3]) : v <= Number(m[3]);
  };
  return query.split(',').some((alt) => alt.split(/\s+and\s+/).every(clause));
}
const layoutsOf = (w, h) => {
  const mm = (q) => ({ matches: matches(q, w, h) });
  return { phone: isSheetLayout(mm), tablet: isTabletLayout(mm), desktop: matches('(min-width: 1025px)', w, h) };
};
const only = (l) => Object.keys(l).filter((k) => l[k]);

test('every width from 320 to 2560 is one layout and one only, at every height', () => {
  for (const h of [350, 500, 500.5, 501, 700, 1366]) {
    for (let w = 320; w <= 2560; w++) {
      const l = layoutsOf(w, h);
      assert.equal(only(l).length, 1, `${w}x${h}: ${JSON.stringify(l)}`);
    }
  }
});

test('the edges of the tablet', () => {
  for (let w = 761; w <= 1024; w++) {
    assert.deepEqual(only(layoutsOf(w, 500)), ['phone'], `${w}x500`);
    assert.deepEqual(only(layoutsOf(w, 501)), ['tablet'], `${w}x501`);
    assert.deepEqual(only(layoutsOf(w, 500.5)), ['phone'], `${w}x500.5`);
  }
  assert.deepEqual(only(layoutsOf(760, 1000)), ['phone']);
  assert.deepEqual(only(layoutsOf(761, 1000)), ['tablet']);
  assert.deepEqual(only(layoutsOf(1024, 1000)), ['tablet']);
  assert.deepEqual(only(layoutsOf(1025, 1000)), ['desktop']);
  assert.deepEqual(only(layoutsOf(1025, 500)), ['desktop'], 'a wide short window is a desktop');
  assert.deepEqual(only(layoutsOf(844, 390)), ['phone']);
  assert.deepEqual(only(layoutsOf(932, 430)), ['phone']);
  for (const [w, h] of [[768, 1024], [820, 1180], [1024, 768], [1024, 1366]]) assert.deepEqual(only(layoutsOf(w, h)), ['tablet'], `${w}x${h}`);
  for (const [w, h] of [[390, 844], [360, 740], [1440, 900]]) assert.notDeepEqual(only(layoutsOf(w, h)), ['tablet'], `${w}x${h}`);
});

test('the phone is what the 1024 px rules of the stylesheets give', () => {
  assert.equal(SHEET_QUERY, '(max-width: 1024px)');
});

// ---------------------------------------------------------------- what the file overrides is still there

test('the stylesheets it overrides still hold the rules it relies on', () => {
  const app = stripComments(appCss);
  const drawers = stripComments(drawersCss);
  assert.match(app, /@media \(max-width: 1024px\) \{/, 'app.css: the sheet layout');
  assert.match(app, /@media \(min-width: 1025px\) \{/, 'app.css: the desktop');
  assert.match(drawers, /@media \(max-width: 1024px\) and \(max-height: 500px\) \{/, 'drawers.css: the phone held sideways');
  assert.match(drawers, /@media \(max-width: 1024px\) \{/, 'drawers.css: the sheets of the drawers');
  // the desktop rules the tablet copies: the Controls button and its folded state
  assert.match(app, /\.side-panel\.collapsed \.panel-scroll \{\s*display: none;/);
  assert.match(app, /\.panel-head \{[^}]*display: flex;/);
  // the phone rules it overrides: the controls hidden behind a page, the head of the sheet
  assert.match(app, /\.app\.detail-open \.side-panel \{\s*visibility: hidden;/);
  assert.match(app, /\.sheet-head \{\s*display: block;/);
});

// ---------------------------------------------------------------- the order of the stylesheets in the bundle

test('main imports tablet.css after every other import', () => {
  const lines = mainTsx.split('\n');
  const at = lines.findIndex((l) => /^import '\.\/styles\/tablet\.css';/.test(l));
  assert.ok(at > 0, 'main.tsx imports tablet.css');
  const others = lines.map((l, i) => [l, i]).filter(([l, i]) => /^import\s/.test(l) && i !== at && !/lib\/tablet'/.test(l));
  assert.ok(others.length >= 8);
  for (const [l, i] of others) assert.ok(i < at, `${l} comes before the tablet stylesheet`);
  assert.ok(lines.findIndex((l) => /from '\.\/App'/.test(l)) < at, 'after ./App');
  assert.ok(lines.findIndex((l) => /^import '\.\/map\/modules';/.test(l)) < at, 'after ./map/modules');
  const css = lines.map((l, i) => [l, i]).filter(([l, i]) => /\.css';/.test(l) && i !== at);
  assert.ok(css.length >= 4);
  for (const [l, i] of css) assert.ok(i < at, `${l} comes before the tablet stylesheet`);
});
