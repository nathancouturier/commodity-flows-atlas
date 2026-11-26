/**
 * The palette lives in one module, `src/lib/palette.ts`, and this test keeps it there.
 *   node --test web/scripts/palette.test.mjs
 *
 * Four parts:
 *  1. the family and alert hues of `styles/tokens.css` equal the module's (CSS cannot import TypeScript). The CSS surfaces
 *     are not compared: the map draws its own set (`C`), the CSS gradient behind it is hidden, the two differ on purpose;
 *  2. a hue that carries a code (a family, a vessel segment, a status, a pipeline, an event kind, a chart series, the map
 *     surfaces) is typed in no source file but the module, except the entries of HUE_LITERALS_ALLOWED, each with its reason;
 *  3. every other hex colour is counted per file against OTHER_LITERALS, as measured on the day. The test fails when a
 *     count is above its allowance and when it is under it ("lower the allowance"), so the list cannot rot; a file that is
 *     not on the list has none;
 *  4. the three copies of the event colours are gone, and the old names re-export the module;
 *  5. the status rings: each of the five differs from the others in something that is not its colour or its stroke width
 *     (a dash array or a badge path), and the map and the legend both draw them with the module's functions.
 *
 * `rgb()` and `rgba()` strings are outside this test. A package that adds a colour puts it in `lib/palette.ts`; for a
 * one-off neutral that is not a code it raises its file's allowance by exactly the literals added and says why in its report.
 * A hex literal is `#rrggbb` (with or without two more digits) anywhere, or a whole string `'#rgb'`.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { C, EVENT_COLOR, FAMILY_COLOR, HUES, NEUTRAL_LINE, PIPELINE_COLOR, PRICE_PALETTE, PW_COLORS, SEGMENT_COLOR, STATUS_COLOR, statusDecoration, statusRingSvg } from '../src/lib/palette.ts';
import { LABEL_COLOR } from '../src/map/labelRules.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(here, '../src');
const PALETTE_FILE = 'lib/palette.ts';

/** A hex colour of the code that is typed outside the module on purpose: file, colour, how many times, why. */
const HUE_LITERALS_ALLOWED = [
  { file: 'components/ui.tsx', hex: '#3ee6ff', count: 1, reason: 'the brand mark (the arc of the logo), not a code' },
  { file: 'components/ui.tsx', hex: '#ffb547', count: 1, reason: 'the brand mark (the dot of the logo), not a code' },
  { file: 'components/LayerSwitches.tsx', hex: '#3ee6ff', count: 1, reason: 'the accent of an infrastructure switch that is on' },
  { file: 'components/charts/TimeChart.tsx', hex: '#7d8a99', count: 1, reason: 'the muted ink of the chart axes and readout (its own constant)' },
  { file: 'components/charts/TimeChart.tsx', hex: '#ff5c7a', count: 3, reason: 'the colour of a marker that has none: the ribbon, the tick and the hover list' },
  { file: 'components/views/BoardView.tsx', hex: '#7d8a99', count: 1, reason: 'fallback of a CSS variable inside an SVG attribute' },
  { file: 'components/views/BoardView.tsx', hex: '#9db7ff', count: 1, reason: 'fallback of a CSS variable inside an SVG attribute' },
  { file: 'map/modules/choropleth.ts', hex: '#3ee6ff', count: 1, reason: 'the colouring of a commodity that has no family' },
  { file: 'map/modules/infrastructure.ts', hex: '#3ee6ff', count: 1, reason: 'the selected-asset ring, the accent' },
  { file: 'map/labelRules.ts', hex: '#05090f', count: 1, reason: 'the halo of the names is the ocean colour; a pure module with no value import (checked below against `C.ocean`)' },
];

/** Every other hex colour, per file, as measured on the day. Lower a number when a literal goes; never raise one without a reason. */
const OTHER_LITERALS = [
  { file: 'components/LayerSwitches.tsx', count: 1, reason: 'the interface ink of an infrastructure switch that is off (`--ink-3`)' },
  { file: 'components/PriceDrawer.tsx', count: 1, reason: 'the marker of an unchanged year: the interface ink (`--ink-2`)' },
  { file: 'components/Timeline.tsx', count: 1, reason: 'the tick of an event whose kind is unknown' },
  { file: 'components/charts/TimeChart.tsx', count: 1, reason: 'the fill of a point of the chart (`--panel-solid`)' },
  { file: 'components/ui.tsx', count: 3, reason: 'the ring of the brand mark, the fill of the icon badge, the default icon ink' },
  { file: 'components/views/CountryView.tsx', count: 1, reason: 'the colour of a flow whose commodity is unknown' },
  { file: 'map/basemap.ts', count: 1, reason: 'the border of a selected country (the outline layer)' },
  { file: 'map/labelRules.ts', count: 4, reason: 'the colours of the names on the map: country, sea, asset, and the white of a name on a coloured fill; a pure module, they stay with their contrast test' },
  { file: 'map/controller.ts', count: 1, reason: '`#000` of an invisible hit layer (opacity 0): not drawn' },
  { file: 'map/modules/infrastructure.ts', count: 1, reason: '`#000` of an invisible hit layer (opacity 0): not drawn' },
];

// ---------------------------------------------------------------- reading the sources

function walk(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p));
    else if (/\.tsx?$/.test(e.name)) out.push(p);
  }
  return out;
}
const files = walk(SRC).map((p) => ({ rel: path.relative(SRC, p).split(path.sep).join('/'), text: fs.readFileSync(p, 'utf8') }));
const byRel = Object.fromEntries(files.map((f) => [f.rel, f.text]));
const HEX = /#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?(?![0-9a-fA-F])|(?<=['"`])#[0-9a-fA-F]{3}(?=['"`])/g;
const literalsOf = (text) => (text.match(HEX) ?? []).map((h) => h.toLowerCase());

const hexOf = (v) => (typeof v === 'string' && /^#[0-9a-f]{6}$/i.test(v) ? [v.toLowerCase()] : []);
const CODE_HUES = new Set(
  [HUES, FAMILY_COLOR, SEGMENT_COLOR, STATUS_COLOR, PIPELINE_COLOR, EVENT_COLOR, PW_COLORS, PRICE_PALETTE, [NEUTRAL_LINE], C].flatMap((o) => Object.values(o).flatMap(hexOf)),
);

// ---------------------------------------------------------------- 1. the stylesheet

test('single source: the family and alert hues of tokens.css equal the module', () => {
  const css = fs.readFileSync(path.join(SRC, 'styles/tokens.css'), 'utf8');
  const token = (name) => {
    const m = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})\\s*;`));
    assert.ok(m, `--${name} is a hex value in tokens.css`);
    return m[1].toLowerCase();
  };
  // the mapping from a custom property to a hue is written here once
  const MAP = {
    energy: FAMILY_COLOR.energy,
    metals: FAMILY_COLOR.metals,
    softs: FAMILY_COLOR.softs,
    freight: FAMILY_COLOR.freight,
    chokepoint: HUES.red,
    alert: HUES.orange,
    positive: HUES.mint,
  };
  for (const [name, hue] of Object.entries(MAP)) assert.equal(token(name), hue.toLowerCase(), `--${name} equals the module`);
  // the surfaces are not compared: two sets on purpose (see the header)
});

test('the module has no value import, and the halo of the names is the drawn ocean', () => {
  const imports = byRel[PALETTE_FILE].match(/^import\s.*$/gm) ?? [];
  for (const i of imports) assert.match(i, /^import type\s/, `a node test runs the module as TypeScript: ${i}`);
  assert.equal(LABEL_COLOR.halo, C.ocean);
});

// ---------------------------------------------------------------- 2 and 3. the literals

const counts = new Map(); // `${file} ${hex}` -> n, for the hues of the codes
const others = new Map(); // file -> n
for (const f of files) {
  if (f.rel === PALETTE_FILE) continue;
  for (const h of literalsOf(f.text)) {
    if (CODE_HUES.has(h.slice(0, 7))) counts.set(`${f.rel} ${h}`, (counts.get(`${f.rel} ${h}`) ?? 0) + 1);
    else others.set(f.rel, (others.get(f.rel) ?? 0) + 1);
  }
}

test('the hues of the codes are typed nowhere but in the module, except the allowed list', () => {
  for (const a of HUE_LITERALS_ALLOWED) assert.ok(a.reason.length > 10, `${a.file} ${a.hex} has a reason`);
  const allowed = new Map(HUE_LITERALS_ALLOWED.map((a) => [`${a.file} ${a.hex}`, a.count]));
  assert.equal(allowed.size, HUE_LITERALS_ALLOWED.length, 'no entry twice');
  for (const [key, n] of counts) {
    const ok = allowed.get(key) ?? 0;
    assert.ok(n <= ok, `${key}: ${n} typed, ${ok} allowed: a hue of a code is imported from lib/palette.ts, not typed again`);
  }
  for (const [key, ok] of allowed) {
    const n = counts.get(key) ?? 0;
    assert.ok(n >= ok, `${key}: ${n} typed, ${ok} allowed: lower the allowance`);
  }
});

test('every other hex colour is counted per file against its allowance, in both directions', () => {
  const allowed = new Map(OTHER_LITERALS.map((a) => [a.file, a.count]));
  assert.equal(allowed.size, OTHER_LITERALS.length, 'no file twice');
  for (const a of OTHER_LITERALS) assert.ok(a.reason.length > 10, `${a.file} has a reason`);
  for (const [file, n] of others) {
    const ok = allowed.get(file) ?? 0;
    assert.ok(n <= ok, `${file}: ${n} hex literals, ${ok} allowed: a colour that carries a code goes in lib/palette.ts; a one-off neutral raises the allowance by exactly what it adds, with its reason in the report`);
  }
  for (const [file, ok] of allowed) {
    const n = others.get(file) ?? 0;
    assert.ok(n >= ok, `${file}: ${n} hex literals, ${ok} allowed: lower the allowance`);
  }
});

// ---------------------------------------------------------------- 4. the copies are gone

test('the event colours have one copy, and the old names re-export the module', () => {
  for (const f of ['components/PriceDrawer.tsx', 'components/Timeline.tsx', 'components/views/EventView.tsx']) {
    assert.match(byRel[f], /import\s*\{[^}]*\bEVENT_COLOR\b[^}]*\}\s*from\s*'[./]*\/lib\/palette'/, `${f} imports EVENT_COLOR from the module`);
  }
  for (const f of files) {
    if (f.rel === PALETTE_FILE) continue;
    assert.doesNotMatch(f.text, /\binfrastructure:\s*['"]#[0-9a-fA-F]{3,8}['"]/, `${f.rel} declares no table of event colours`);
  }
  const REEXPORT = [
    ['lib/format.ts', /export\s*\{\s*FAMILY_COLOR\s*\}\s*from\s*'\.\/palette'/],
    ['lib/freight.ts', /export\s*\{\s*SEGMENT_COLOR\s*\}\s*from\s*'\.\/palette'/],
    ['components/charts/pwChart.ts', /export\s*\{\s*PW_COLORS\s*\}\s*from\s*'\.\.\/\.\.\/lib\/palette'/],
    ['components/views/EventView.tsx', /export\s*\{\s*EVENT_COLOR\s*\}/],
    ['map/basemap.ts', /import\s*\{\s*C\s*\}\s*from\s*'\.\.\/lib\/palette'/],
    ['map/modules/infrastructure.ts', /import\s*\{[^}]*\bSTATUS_COLOR\b[^}]*\}\s*from\s*'\.\.\/\.\.\/lib\/palette'/],
    ['map/modules/infrastructure.ts', /export\s*\{\s*STATUS_COLOR\s*\}/],
    ['map/modules/infrastructure.ts', /PIPELINE_COLOR\.crude/],
    ['map/modules/lanes.ts', /NEUTRAL_LINE/],
    ['map/modules/landflows.ts', /NEUTRAL_LINE/],
    ['components/views/shared.tsx', /NEUTRAL_LINE/],
  ];
  for (const [f, re] of REEXPORT) assert.match(byRel[f], re, `${f} reads the module (${re})`);
});

// ---------------------------------------------------------------- 5. cues exist for statuses

const STATUSES = ['damaged', 'idle', 'construction', 'planned', 'closed'];

/** What tells one status ring from another once colours and stroke widths are taken out: the elements, their dash arrays and their paths. */
function signatureOf(svg) {
  let t = svg;
  for (const c of Object.values(STATUS_COLOR)) t = t.split(c).join('X');
  t = t.replace(/\sstroke-width="[^"]*"/g, '');
  return [...t.matchAll(/<(\w+)([^>]*)\/>/g)]
    .map(([, name, attrs]) => `${name}|${attrs.match(/stroke-dasharray="([^"]*)"/)?.[1] ?? ''}|${attrs.match(/\sd="([^"]*)"/)?.[1] ?? ''}`)
    .join(' ');
}

test('cues exist for statuses: the five rings differ in something that is not their colour or their stroke width', () => {
  const sigs = STATUSES.map((st) => [st, signatureOf(statusDecoration(st))]);
  for (const [st, sig] of sigs) assert.ok(sig.length > 0, `${st} has a drawing`);
  for (let i = 0; i < sigs.length; i++) {
    for (let j = i + 1; j < sigs.length; j++) assert.notEqual(sigs[i][1], sigs[j][1], `${sigs[i][0]} and ${sigs[j][0]} differ by colour or stroke width only`);
  }
  assert.equal(statusDecoration('ok'), '', 'an operating asset has no decoration');
  // the legend's key is the decoration alone, in a standalone image of the requested size
  for (const st of STATUSES) {
    assert.equal(
      statusRingSvg(st, { size: 20 }),
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28" width="20" height="20" aria-hidden="true">${statusDecoration(st)}</svg>`,
    );
  }
});

test('the legend and the map draw the status rings with the module', () => {
  const legend = byRel['components/Legend.tsx'];
  assert.match(legend, /import\s*\{[^}]*\bstatusRingSvg\b[^}]*\}\s*from\s*'\.\.\/lib\/palette'/, 'Legend.tsx imports statusRingSvg from the module');
  for (const st of STATUSES) assert.match(legend, new RegExp(`statusRingSvg\\(\\s*'${st}'`), `Legend.tsx draws the ${st} key with statusRingSvg`);
  assert.doesNotMatch(legend, /borderColor:\s*STATUS_COLOR/, 'Legend.tsx draws no status key as a coloured border');
  const infra = byRel['map/modules/infrastructure.ts'];
  assert.match(infra, /import\s*\{[^}]*\bstatusDecoration\b[^}]*\}\s*from\s*'\.\.\/\.\.\/lib\/palette'/, 'the map imports statusDecoration from the module');
  assert.match(infra, /\$\{statusDecoration\(st\)\}/, 'the map icon calls statusDecoration');
  assert.doesNotMatch(infra, /stroke-dasharray|<circle|function statusSvg/, 'infrastructure.ts holds no drawing of a status of its own');
  for (const f of files) assert.doesNotMatch(f.text, /status-key/, `${f.rel} has no status-key`);
  for (const css of fs.readdirSync(path.join(SRC, 'styles')).filter((n) => n.endsWith('.css'))) {
    assert.doesNotMatch(fs.readFileSync(path.join(SRC, 'styles', css), 'utf8'), /\.status-key/, `${css} has no .status-key rule`);
  }
});
