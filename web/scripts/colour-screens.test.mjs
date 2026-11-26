/**
 * The colours of the atlas are held to a rule, and this test keeps them to it.
 *   node --test web/scripts/colour-screens.test.mjs
 *
 * What is measured: the colours that are on one screen, taken from `src/lib/palette.ts` and never typed here, are compared
 * with the distance and the simulations of `scripts/cvd.mjs`, and every data colour is compared with the drawn ocean and
 * land. The thresholds are the constants of `cvd.mjs`: the atlas's own rule, taken from a validator, not a standard.
 *
 *  1. the matrices of `cvd.mjs` are not mistyped (each row sums to 1) and the conversions give the values they must;
 *  2. screens: two colours of a screen are at least NORMAL_FLOOR apart for unsimulated vision and at least CVD_TARGET apart
 *     under each of protan, deutan and tritan, or the pair is in ALLOWED with a cue that does not rest on colour (`dash`,
 *     `glyph`, `label`, `place`) and a reason. A pair in ALLOWED that is already far enough apart fails: remove it. A cue of
 *     `dash` or `glyph` is backed by a test of `palette.test.mjs`, which this test checks is still there; a cue of `label`
 *     or `place` is a statement, so its entry names the places where it is true and the test reads them;
 *  3. contrast: every data colour is at least CONTRAST_MIN against the ocean and against the land, and at least the figure
 *     of CONTRAST_FLOOR, which records what it was on the day, rounded down: a figure cannot go down. The contrast of the
 *     land on the ocean and of the country outline is stated, not required: the look of the map is not decided here;
 *  4. the section of METHODOLOGY.md that describes all of this holds the thresholds, the dash rule and the figures of
 *     this test, so that the text cannot drift from the code.
 *
 * A colour that is added goes in `lib/palette.ts`; if it lands on a screen below the thresholds, it needs a cue and an
 * entry of ALLOWED, and if it is a new data colour, a line in CONTRAST_FLOOR.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ALT_DASH, C, DASH_PERIOD_RATIO, DASH_SHARE_GAP, EVENT_COLOR, FAMILY_COLOR, HUES, NEUTRAL_LINE, PIPELINE_COLOR, PRICE_PALETTE, PW_COLORS, PW_DASH, ROUTE_DASH, SEGMENT_COLOR, STATUS_COLOR, dashDistinct } from '../src/lib/palette.ts';
import { CONTRAST_MIN, CVD_FLOOR, CVD_TARGET, MATRICES, NORMAL_FLOOR, contrast, deltaE, simulate } from './cvd.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(here, '../src');
const ROOT = path.resolve(here, '../..');
const read = (p) => fs.readFileSync(p, 'utf8');
const src = (rel) => read(path.join(SRC, rel));
const KINDS = ['protan', 'deutan', 'tritan'];

// ---------------------------------------------------------------- 1. the helper

test('the matrices are not mistyped: each row sums to 1, and the conversions give the values they must', () => {
  assert.deepEqual(Object.keys(MATRICES).sort(), [...KINDS].sort());
  for (const [kind, m] of Object.entries(MATRICES)) {
    assert.equal(m.length, 3, `${kind} has three rows`);
    for (const [i, row] of m.entries()) {
      assert.equal(row.length, 3, `${kind} row ${i} has three entries`);
      assert.ok(row.every(Number.isFinite), `${kind} row ${i} is made of numbers`);
      assert.ok(Math.abs(row.reduce((a, b) => a + b, 0) - 1) < 1e-5, `${kind} row ${i} sums to 1 (a grey stays grey): a digit was changed by hand`);
    }
  }
  // the conversions, on colours that are not in the palette: white, black and a mid grey
  assert.equal(contrast('#ffffff', '#000000'), 21, 'WCAG: white on black is 21:1');
  assert.equal(contrast('#ffffff', '#ffffff'), 1);
  assert.ok(Math.abs(deltaE('#ffffff', '#000000') - 100) < 0.01, 'OKLab: white and black are 100 apart');
  assert.equal(deltaE('#336699', '#336699'), 0);
  for (const kind of KINDS) {
    const g = simulate('#808080', kind);
    assert.ok(g.every((x) => Math.abs(x - g[0]) < 1e-4), `${kind}: a grey stays grey`);
  }
});

// ---------------------------------------------------------------- 2. the screens

const named = (prefix, o, keys = Object.keys(o)) => Object.fromEntries(keys.map((k) => [`${prefix}:${k}`, o[k]]));

/** Colour groups, by what is drawn. A name is `group:key`. */
const G = {
  lane: named('lane', FAMILY_COLOR, Object.keys(FAMILY_COLOR).filter((f) => f !== 'freight')), // the lanes of the three commodity families
  accent: { 'accent:freight': FAMILY_COLOR.freight }, // the Freight family's colour, the accent that rings the opened asset
  route: named('route', SEGMENT_COLOR),
  pipeline: named('pipeline', PIPELINE_COLOR),
  status: named('status', STATUS_COLOR), // the ring and badge of an asset that is not operating
  marker: { chokepoint: HUES.red, alert: HUES.orange }, // the chokepoint's ring; the colour of a warning
  icon: named('icon', FAMILY_COLOR), // the family colour of an asset's icon, under its ring
  series: named('series', PW_COLORS),
  price: Object.fromEntries(PRICE_PALETTE.slice(0, 3).map((c, i) => [`price:${i + 1}`, c])), // the drawer charts three series at most, in this order
  event: named('event', EVENT_COLOR),
};

/**
 * The colours that are on one screen. Marks are compared with marks of their kind: lines with lines, points with points, a
 * ring with the icon it circles. A line and a point are told apart by their shape before their colour.
 */
const SCREENS = [
  { name: 'map lines', within: [G.lane, G.accent, G.route, G.pipeline] },
  { name: 'map points', within: [G.status, G.marker] },
  { name: 'map rings over icons', between: [G.status, G.icon] },
  { name: 'port and passage charts', within: [G.series] },
  { name: 'price drawer', within: [G.price] },
  { name: 'History bar and event pages', within: [G.event] },
];

const CUES = ['dash', 'glyph', 'label', 'place'];

/** Where a statement is true: a file of `src` and what it holds, or a check of the data. */
const FILE = (rel, re, says) => ({ says, ok: () => re.test(src(rel)) });
const EV = {
  laneLegend: FILE('components/Legend.tsx', /background: FAMILY_COLOR\[f\] \}\} \/>\s*\{FAMILY_LABEL\[f\]\}/, 'the legend names each family beside its lane colour (components/Legend.tsx)'),
  laneHover: FILE('map/modules/lanes.ts', /commodityMeta\(lane\.k\)\?\.name/, 'the hover of a lane names its commodity (map/modules/lanes.ts)'),
  routeLegend: FILE('components/Legend.tsx', /<RouteSwatch segment=\{s\} \/>\s*\{SEGMENT_LABEL\[s\]\}/, 'the legend names each vessel class beside its swatch (components/Legend.tsx)'),
  routeHover: FILE('map/modules/routes.ts', /vesselName\(r\.vclass\)/, 'the hover of a route names its vessel class (map/modules/routes.ts)'),
  pipelineHover: FILE('map/modules/infrastructure.ts', /label: f\.p\.name/, 'the hover of a pipeline names it (map/modules/infrastructure.ts)'),
  pipelineOnLand: FILE('map/modules/infrastructure.ts', /f\.p\.type === 'pipeline'/, 'a pipeline is an asset of the infrastructure layer, drawn from its own geometry on land (map/modules/infrastructure.ts); a route is a sea route (data/freight/routes.geo.json)'),
  accentRing: FILE('map/modules/infrastructure.ts', new RegExp(`'circle-stroke-color': '${HUES.cyan}'`), 'the accent is the ring of the opened asset (map/modules/infrastructure.ts)'),
  noFreightCommodity: {
    says: 'no commodity of the atlas is of the Freight family, so no lane takes the accent (data/commodities)',
    ok: () => {
      const dir = path.join(ROOT, 'data/commodities');
      const families = new Set();
      for (const n of fs.readdirSync(dir).filter((f) => f.endsWith('.json'))) {
        const j = JSON.parse(read(path.join(dir, n)));
        for (const x of Array.isArray(j) ? j : (j.commodities ?? [])) if (x?.family) families.add(x.family);
      }
      return families.size > 0 && !families.has('freight');
    },
  },
  statuses: { says: 'the five status rings differ in something that is not their colour (the test "cues exist for statuses" of palette.test.mjs)', ok: () => read(path.join(here, 'palette.test.mjs')).includes("test('cues exist for statuses") },
  alertNotOnMap: {
    says: 'the alert colour is the colour of a word or a badge on a page (styles/views.css, tables-by-year.css), and no file of map/ draws it',
    ok: () => {
      const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]));
      const mapFiles = walk(path.join(SRC, 'map')).filter((f) => /\.tsx?$/.test(f));
      return mapFiles.length > 0 && mapFiles.every((f) => !new RegExp(`HUES\\.orange|--alert|${HUES.orange}`, 'i').test(read(f))) && /\.badge-warn \{ color: var\(--alert\)/.test(src('styles/views.css'));
    },
  },
  eventPage: FILE('components/views/EventView.tsx', /EVENT_KIND_LABEL\[ev\.kind\]/, 'the page of an event shows its kind as a word in a badge (components/views/EventView.tsx)'),
  eventList: FILE('components/EventList.tsx', /title=\{EVENT_KIND_LABEL\[e\.kind\]\}/, 'the dot of an event in a list carries its kind as a title (components/EventList.tsx)'),
  priceKinds: FILE('components/PriceDrawer.tsx', /EVENT_KINDS\.map\(\(k\) => \(\s*<span key=\{k\} style=\{\{ '--c': EVENT_COLOR\[k\] \}\}>\s*<i \/>\s*\{k\}/, 'the price drawer lists the seven kinds by name beside their colour (components/PriceDrawer.tsx)'),
  priceChip: FILE('components/PriceDrawer.tsx', /<span class="pd-chip-name" title=\{d\.meta\.name\}>/, 'the price drawer names each charted series beside its colour (components/PriceDrawer.tsx)'),
};

/** Proofs for the cue `dash`: a function that is true when the two marks of the pair are drawn with patterns that differ. */
const dashRouteRoute = (x, y) => () => dashDistinct(ROUTE_DASH[x], ROUTE_DASH[y]);
const dashLaneRoute = (x) => () => ROUTE_DASH[x].length > 0 && dashDistinct(ALT_DASH, ROUTE_DASH[x]); // a solid lane, or a mixed lane or overland arc drawn ALT_DASH
const dashChart = (x, y) => () => Boolean(PW_DASH[x]) !== Boolean(PW_DASH[y]);

/** The test of `palette.test.mjs` that backs each cue that is built, by the beginning of its title. */
const BACKED_BY = { dash: ['cues exist for routes', 'cues exist for charts'], glyph: ['cues exist for statuses'] };

const SEA_LAND = 'a route is a sea route and a pipeline is on land';
const ACCENT = 'the freight cyan is the accent that rings the opened asset and marks the Freight family; it is the colour of no lane, route or pipeline';
const WORDS_LANE = 'a lane is named by its commodity in its hover and its family in the legend';
const KIND_WORDS = 'the kind of an event is a word on its page and in the lists of events and in the price drawer; the tick of the History bar gives the date and the title, not the kind';

/**
 * The pairs that fall under a threshold on a screen, each with its cue and its reason. An entry is
 * [screen, a, b, cue, reason, evidence (a list of EV keys, for `label` and `place`) or proof (a function, for `dash`)].
 */
const ALLOWED = [
  // ---- map lines
  ['map lines', 'lane:energy', 'route:tanker', 'dash', 'one amber: a Tankers route is drawn dash and dot, an Energy lane solid (a mixed lane or an overland arc is [2, 2])', dashLaneRoute('tanker')],
  ['map lines', 'lane:metals', 'route:dry', 'dash', 'one lavender: a Dry bulk route is drawn in long dashes, a Metals lane solid (a mixed lane or an overland arc is [2, 2])', dashLaneRoute('dry')],
  ['map lines', 'lane:metals', 'route:container', 'dash', 'a Container route is drawn in short dashes far apart, a Metals lane solid or [2, 2]', dashLaneRoute('container')],
  ['map lines', 'route:dry', 'route:container', 'dash', 'the Dry bulk and Container patterns differ by the rule of dashDistinct, and the deuteranope sees one colour', dashRouteRoute('dry', 'container')],
  ['map lines', 'lane:softs', 'route:dry', 'dash', 'a Dry bulk route is dashed, a Softs lane solid or [2, 2]; the two differ only under tritanopia', dashLaneRoute('dry')],
  ['map lines', 'lane:softs', 'route:gas', 'dash', 'a Gas carriers route is drawn in dots, a Softs lane solid or [2, 2]', dashLaneRoute('gas')],
  ['map lines', 'lane:energy', 'pipeline:products', 'label', `two ambers; ${'the hover of a pipeline names it, the hover of a lane names its commodity'}`, ['pipelineHover', 'laneHover']],
  ['map lines', 'route:tanker', 'pipeline:products', 'place', `two ambers; ${SEA_LAND}`, ['pipelineOnLand', 'routeHover']],
  ['map lines', 'lane:metals', 'lane:softs', 'label', `the two differ only under tritanopia; ${WORDS_LANE}`, ['laneLegend', 'laneHover']],
  ['map lines', 'lane:metals', 'pipeline:gas', 'label', `the two differ only under tritanopia; the hover of a pipeline names it, ${WORDS_LANE}`, ['pipelineHover', 'laneHover']],
  ['map lines', 'lane:softs', 'pipeline:products', 'label', 'a pale amber and a green, one colour to a protanope; the hover of a pipeline names it, a lane is named by its commodity', ['pipelineHover', 'laneHover']],
  ['map lines', 'lane:softs', 'pipeline:gas', 'label', `two greens; the hover of a pipeline names it, ${WORDS_LANE}`, ['pipelineHover', 'laneHover']],
  ['map lines', 'lane:metals', 'accent:freight', 'place', ACCENT, ['accentRing', 'noFreightCommodity']],
  ['map lines', 'lane:softs', 'accent:freight', 'place', ACCENT, ['accentRing', 'noFreightCommodity']],
  ['map lines', 'accent:freight', 'route:dry', 'place', ACCENT, ['accentRing', 'noFreightCommodity']],
  ['map lines', 'accent:freight', 'route:gas', 'place', ACCENT, ['accentRing', 'noFreightCommodity']],
  ['map lines', 'accent:freight', 'route:container', 'place', ACCENT, ['accentRing', 'noFreightCommodity']],
  ['map lines', 'accent:freight', 'pipeline:gas', 'place', ACCENT, ['accentRing', 'noFreightCommodity']],
  ['map lines', 'route:dry', 'pipeline:gas', 'place', `lavender and teal, close under tritanopia; ${SEA_LAND}`, ['pipelineOnLand', 'routeLegend']],
  ['map lines', 'route:gas', 'pipeline:gas', 'place', `two teals; ${SEA_LAND}, and the legend names the vessel class of a route`, ['pipelineOnLand', 'routeLegend']],
  // ---- map points
  ['map points', 'status:damaged', 'status:closed', 'glyph', 'a round badge with an exclamation mark against a round badge with a cross; the two rings differ in width', ['statuses']],
  ['map points', 'status:damaged', 'chokepoint', 'glyph', 'one red: the ring of a damaged asset sits on an icon and carries a round badge, the chokepoint is a round marker with a pulse and no icon', ['statuses']],
  ['map points', 'status:closed', 'chokepoint', 'glyph', 'a grey ring with a cross badge, on an icon, against a round marker with a pulse', ['statuses']],
  ['map points', 'status:planned', 'status:closed', 'glyph', 'a dotted ring with no badge against a continuous ring with a cross badge', ['statuses']],
  ['map points', 'status:damaged', 'alert', 'place', 'the alert colour is not drawn on the map: it colours a word or a badge on a page, which carries its words', ['alertNotOnMap']],
  ['map points', 'chokepoint', 'alert', 'place', 'the alert colour is not drawn on the map: it colours a word or a badge on a page, which carries its words', ['alertNotOnMap']],
  // ---- map rings over icons
  ['map rings over icons', 'status:idle', 'icon:energy', 'glyph', 'a ring of the colour of the icon: the ring is drawn outside the icon, 1.8 px wide, with a round badge holding two bars', ['statuses']],
  ['map rings over icons', 'status:construction', 'icon:freight', 'glyph', 'the ring of an asset under construction is dashed, the ring of the icon is not', ['statuses']],
  ['map rings over icons', 'status:planned', 'icon:metals', 'glyph', 'the ring of a planned asset is dotted, the ring of the icon is not', ['statuses']],
  // ---- charts
  ['port and passage charts', 'series:dry', 'series:container', 'dash', 'the Container series has a dashed edge and a dashed sample in the readout, the Dry bulk series is solid; the deuteranope sees one colour', dashChart('dry', 'container')],
  // ---- price drawer
  ['price drawer', 'price:1', 'price:3', 'label', 'the two differ only under deuteranopia; the drawer names each charted series beside its colour', ['priceChip']],
  // ---- History bar and event pages
  ['History bar and event pages', 'event:conflict', 'event:accident', 'label', KIND_WORDS, ['eventPage', 'eventList', 'priceKinds']],
  ['History bar and event pages', 'event:canal', 'event:infrastructure', 'label', KIND_WORDS, ['eventPage', 'eventList', 'priceKinds']],
  ['History bar and event pages', 'event:canal', 'event:weather', 'label', KIND_WORDS, ['eventPage', 'eventList', 'priceKinds']],
  ['History bar and event pages', 'event:canal', 'event:policy', 'label', KIND_WORDS, ['eventPage', 'eventList', 'priceKinds']],
  ['History bar and event pages', 'event:weather', 'event:policy', 'label', `one colour to a deuteranope; ${KIND_WORDS}`, ['eventPage', 'eventList', 'priceKinds']],
  ['History bar and event pages', 'event:weather', 'event:infrastructure', 'label', KIND_WORDS, ['eventPage', 'eventList', 'priceKinds']],
  ['History bar and event pages', 'event:accident', 'event:market', 'label', KIND_WORDS, ['eventPage', 'eventList', 'priceKinds']],
].map(([screen, a, b, cue, reason, proof]) => ({ screen, a, b, cue, reason, proof }));

const pairsOf = (screen) => {
  const pairs = [];
  const cross = (A, B) => {
    for (const a of Object.keys(A)) for (const b of Object.keys(B)) pairs.push([a, b, A[a], B[b]]);
  };
  if (screen.between) cross(...screen.between);
  if (screen.within) {
    const all = Object.assign({}, ...screen.within);
    const names = Object.keys(all);
    for (let i = 0; i < names.length; i++) for (let j = i + 1; j < names.length; j++) pairs.push([names[i], names[j], all[names[i]], all[names[j]]]);
  }
  return pairs;
};

const measure = (ca, cb) => {
  const [protan, deutan, tritan] = KINDS.map((k) => deltaE(ca, cb, k));
  const normal = deltaE(ca, cb);
  return { normal, protan, deutan, tritan, worst: Math.min(protan, deutan, tritan), ok: normal >= NORMAL_FLOOR && Math.min(protan, deutan, tritan) >= CVD_TARGET };
};
const key = (screen, a, b) => `${screen}|${[a, b].sort().join('|')}`;
const f1 = (x) => x.toFixed(1);

test('screens: every pair is far enough apart, or listed with a cue that does not rest on colour', () => {
  const allowed = new Map(ALLOWED.map((e) => [key(e.screen, e.a, e.b), e]));
  assert.equal(allowed.size, ALLOWED.length, 'no pair twice');
  const seen = new Set();
  for (const screen of SCREENS) {
    assert.ok(pairsOf(screen).length > 0, `${screen.name} holds colours`);
    for (const [a, b, ca, cb] of pairsOf(screen)) {
      const k = key(screen.name, a, b);
      seen.add(k);
      const m = measure(ca, cb);
      const entry = allowed.get(k);
      const figures = `${f1(m.normal)} normal, ${f1(m.protan)} protan, ${f1(m.deutan)} deutan, ${f1(m.tritan)} tritan`;
      if (!m.ok) {
        assert.ok(entry, `${screen.name}: ${a} and ${b} are too close (${figures}; ${NORMAL_FLOOR} and ${CVD_TARGET} are needed): change a colour in lib/palette.ts, or add an entry to ALLOWED with a cue (${CUES.join(', ')}) and its reason`);
      } else {
        assert.ok(!entry, `${screen.name}: ${a} and ${b} are far enough apart (${figures}): remove them from ALLOWED, the list cannot rot`);
      }
    }
  }
  for (const k of allowed.keys()) assert.ok(seen.has(k), `${k} is not a pair of its screen: remove it from ALLOWED`);
});

test('screens: each allowed pair names a cue of the closed list, a reason, and the place where the cue is true', () => {
  const palette = read(path.join(here, 'palette.test.mjs'));
  for (const e of ALLOWED) {
    const what = `${e.screen}: ${e.a} and ${e.b}`;
    assert.ok(CUES.includes(e.cue), `${what}: the cue is one of ${CUES.join(', ')}`);
    assert.ok(e.reason.length > 30, `${what}: a reason in words`);
    if (e.cue === 'dash') {
      assert.equal(typeof e.proof, 'function', `${what}: a dash cue is proved by the module's patterns`);
      assert.ok(e.proof(), `${what}: the two marks are drawn with patterns that differ (lib/palette.ts)`);
    } else {
      assert.ok(Array.isArray(e.proof) && e.proof.length > 0, `${what}: a ${e.cue} cue names the places where it is true`);
      for (const id of e.proof) {
        assert.ok(EV[id], `${what}: ${id} is a known place`);
        assert.ok(EV[id].ok(), `${what}: not true any more: ${EV[id].says}`);
      }
    }
    // a cue that is built is backed by the test that builds it: the test is still in palette.test.mjs
    if (BACKED_BY[e.cue]) {
      const titles = BACKED_BY[e.cue].filter((t) => palette.includes(`test('${t}`));
      assert.ok(titles.length > 0, `${what}: the ${e.cue} cue rests on a test of palette.test.mjs ("${BACKED_BY[e.cue].join('" or "')}") that is not there any more`);
      if (e.cue === 'dash') {
        const chart = e.screen === 'port and passage charts';
        assert.ok(palette.includes(`test('${chart ? 'cues exist for charts' : 'cues exist for routes'}`), `${what}: the dash test of ${chart ? 'the charts' : 'the routes'} is not in palette.test.mjs`);
      }
    }
  }
  assert.ok(CVD_FLOOR < CVD_TARGET, 'the floor lies under the target');
});

test('screens: the figures of every pair under a threshold are printed', (t) => {
  const rows = [];
  for (const screen of SCREENS) {
    for (const [a, b, ca, cb] of pairsOf(screen)) {
      const m = measure(ca, cb);
      if (!m.ok) rows.push(`${screen.name}: ${a} / ${b}: ${f1(m.normal)} / ${f1(m.protan)} / ${f1(m.deutan)} / ${f1(m.tritan)}${m.worst < CVD_FLOOR ? ' (under the floor)' : ''}`);
    }
  }
  t.diagnostic(`normal / protan / deutan / tritan, OKLab distance x 100 (thresholds ${NORMAL_FLOOR} and ${CVD_TARGET}, floor ${CVD_FLOOR}); ${rows.length} pairs under them`);
  for (const screen of SCREENS) {
    const mine = rows.filter((r) => r.startsWith(`${screen.name}: `));
    if (mine.length) t.diagnostic(mine.map((r) => r.slice(screen.name.length + 2)).join('; '));
  }
});

// ---------------------------------------------------------------- 3. contrast

/**
 * The contrast of every data colour against the drawn ocean and the drawn land, as measured when this test was written,
 * rounded down to one decimal: [on the ocean, on the land]. A colour may not fall under its figures.
 */
const CONTRAST_FLOOR = {
  'HUES.amber': [11.3, 10.1],
  'HUES.lavender': [10.1, 9.0],
  'HUES.green': [12.4, 11.1],
  'HUES.cyan': [13.2, 11.8],
  'HUES.violet': [9.6, 8.5],
  'HUES.red': [6.7, 6.0],
  'HUES.orange': [7.7, 6.9],
  'HUES.teal': [14.5, 13.0],
  'HUES.grey': [5.6, 5.0],
  'HUES.mint': [12.3, 11.0],
  'STATUS_COLOR.damaged': [6.1, 5.5],
  'STATUS_COLOR.idle': [12.3, 11.0],
  'STATUS_COLOR.construction': [16.9, 15.1],
  'STATUS_COLOR.planned': [8.1, 7.2],
  'STATUS_COLOR.closed': [4.6, 4.1],
  'PIPELINE_COLOR.crude': [5.2, 4.7],
  'PIPELINE_COLOR.products': [13.9, 12.4],
  'PIPELINE_COLOR.gas': [11.2, 10.0],
  NEUTRAL_LINE: [7.4, 6.6],
};

/** Every data colour of the module, by the name of its first appearance. */
function dataColours() {
  const out = new Map();
  const collections = [
    ['HUES', HUES],
    ['STATUS_COLOR', STATUS_COLOR],
    ['PIPELINE_COLOR', PIPELINE_COLOR],
    ['NEUTRAL_LINE', { '': NEUTRAL_LINE }],
    ['FAMILY_COLOR', FAMILY_COLOR],
    ['SEGMENT_COLOR', SEGMENT_COLOR],
    ['EVENT_COLOR', EVENT_COLOR],
    ['PW_COLORS', PW_COLORS],
    ['PRICE_PALETTE', PRICE_PALETTE],
  ];
  for (const [coll, o] of collections) for (const [k, v] of Object.entries(o)) if (!out.has(v)) out.set(v, k === '' ? coll : `${coll}.${k}`);
  return out;
}
const lowestOf = (surface) => {
  let low = null;
  for (const [hex, label] of dataColours()) {
    const r = contrast(hex, surface);
    if (!low || r < low.r) low = { label, hex, r };
  }
  return low;
};

test('contrast: every data colour keeps its contrast on the ocean and on the land, and none is under the minimum', () => {
  const colours = dataColours();
  for (const [hex, label] of colours) {
    const floor = CONTRAST_FLOOR[label];
    assert.ok(floor, `${label} is a data colour with no line in CONTRAST_FLOOR: record its contrast on the ocean and on the land, rounded down to one decimal`);
    for (const [i, [surface, name]] of [[C.ocean, 'ocean'], [C.land, 'land']].entries()) {
      const r = contrast(hex, surface);
      assert.ok(r >= CONTRAST_MIN, `${label} on the ${name} is ${r.toFixed(2)}:1, under the minimum of ${CONTRAST_MIN.toFixed(1)}:1`);
      assert.ok(r >= floor[i], `${label} on the ${name} is ${r.toFixed(2)}:1, under the ${floor[i]}:1 it had: a figure cannot go down`);
    }
  }
  for (const label of Object.keys(CONTRAST_FLOOR)) assert.ok([...colours.values()].includes(label), `${label} is in CONTRAST_FLOOR and is no data colour of the module any more: remove the line`);
});

/** The contrast of the surfaces of the map, stated and not required: the look of the map is not decided here. */
const STATED = () => ({
  landOnOcean: contrast(C.land, C.ocean),
  borderOnOcean: contrast(C.border, C.ocean),
  borderOnLand: contrast(C.border, C.land),
  coastOnOcean: contrast(C.coast, C.ocean),
});

test('contrast: the land on the ocean and the country outline are stated, and nothing is required of them', (t) => {
  const s = STATED();
  for (const v of Object.values(s)) assert.ok(Number.isFinite(v) && v >= 1 && v <= 21);
  const lo = lowestOf(C.ocean);
  const ll = lowestOf(C.land);
  t.diagnostic(
    `land on ocean ${s.landOnOcean.toFixed(2)}:1; country outline (C.border) ${s.borderOnOcean.toFixed(2)}:1 on the ocean and ${s.borderOnLand.toFixed(2)}:1 on the land; C.coast, drawn by no layer, ${s.coastOnOcean.toFixed(2)}:1 on the ocean; ` +
      `lowest data colour ${lo.label} ${lo.r.toFixed(2)}:1 on the ocean, ${ll.label} ${ll.r.toFixed(2)}:1 on the land`,
  );
});

// ---------------------------------------------------------------- 4. the text

const md = read(path.join(ROOT, 'METHODOLOGY.md'));
const TITLE = 'Colours and the cues that do not rest on colour';
const heading = md.match(new RegExp(`^## \\d+\\. ${TITLE}$`, 'm'));
const section = heading ? md.slice(heading.index + heading[0].length).split(/^## /m)[0].replace(/\s+/g, ' ') : '';
const num = (s) => Number(s);

test('METHODOLOGY holds a section on the colours, and it says what the code does', () => {
  assert.ok(heading, `METHODOLOGY.md has a section titled "${TITLE}"`);
  assert.match(section, /not a standard/, 'the thresholds are called the atlas\'s own rule, not a standard');
  assert.match(section, /Machado, Oliveira & Fernandes \(2009\)/, 'the model of the simulation is named as the validator names it');
  assert.match(section, /severity 1\.0/);
  assert.match(section, /a model of colour vision, not a measure of any person's/, 'the simulation is a model');
  assert.match(section, /OKLab/);
  assert.match(section, /web\/src\/lib\/palette\.ts/, 'the module is named');
  assert.match(section, /web\/scripts\/colour-screens\.test\.mjs/, 'the test is named');
  assert.doesNotMatch(section, /\bowner (decided|accepted|chose|approved|agreed)\b/i, 'no sentence says that the owner decided or accepted anything');
  // the cues that the test knows are the ones the text names
  for (const cue of CUES) assert.ok(section.includes(`\`${cue}\``), `the section names the cue ${cue}`);
});

test('METHODOLOGY states the thresholds, the dash rule and the figures that the code holds', () => {
  const m = section.match(
    /at least (\d+(?:\.\d+)?) apart for unsimulated vision and at least (\d+(?:\.\d+)?) apart under each of the three simulations; a pair between (\d+(?:\.\d+)?) and (\d+(?:\.\d+)?) is accepted only with a second cue; a data colour must reach a contrast ratio of (\d+\.\d+):1/,
  );
  assert.ok(m, 'the section states the five thresholds in the sentence the test reads');
  assert.equal(num(m[1]), NORMAL_FLOOR, 'the unsimulated floor');
  assert.equal(num(m[2]), CVD_TARGET, 'the target under each simulation');
  assert.equal(num(m[3]), CVD_FLOOR, 'the floor under the target');
  assert.equal(num(m[4]), CVD_TARGET, 'the band reaches up to the target');
  assert.equal(num(m[5]), CONTRAST_MIN, 'the contrast minimum');
  assert.equal(m[5], CONTRAST_MIN.toFixed(1), 'the minimum is written with one decimal');

  const dash = section.match(/shares of the drawn length differ by at least (\d+\.\d+), or the longer period is at least (\d+(?:\.\d+)?) times the shorter/);
  assert.ok(dash, 'the section states the rule that tells two dash patterns apart');
  assert.equal(num(dash[1]), DASH_SHARE_GAP);
  assert.equal(num(dash[2]), DASH_PERIOD_RATIO);

  const pat = section.match(/dashed with (\d+) px drawn and (\d+) px empty/);
  assert.ok(pat, 'the section states the pattern of the Container series');
  assert.deepEqual([num(pat[1]), num(pat[2])], PW_DASH.container);

  const s = STATED();
  const stated = section.match(/[Tt]he land is (\d+\.\d+):1 on the ocean; the country outline is (\d+\.\d+):1 on the ocean and (\d+\.\d+):1 on the land/);
  assert.ok(stated, 'the section states the contrast of the land and of the outline');
  assert.equal(stated[1], s.landOnOcean.toFixed(2));
  assert.equal(stated[2], s.borderOnOcean.toFixed(2));
  assert.equal(stated[3], s.borderOnLand.toFixed(2));

  const low = section.match(/the lowest, the Closed status ring, is (\d+\.\d+):1 on the ocean and (\d+\.\d+):1 on the land/);
  assert.ok(low, 'the section names the lowest data colour');
  assert.equal(lowestOf(C.ocean).label, 'STATUS_COLOR.closed', 'the lowest data colour on the ocean is the Closed ring');
  assert.equal(lowestOf(C.land).label, 'STATUS_COLOR.closed', 'the lowest data colour on the land is the Closed ring');
  assert.equal(low[1], contrast(STATUS_COLOR.closed, C.ocean).toFixed(1));
  assert.equal(low[2], contrast(STATUS_COLOR.closed, C.land).toFixed(1));
});

test('METHODOLOGY counts the container routes as the data does, and the legend does not name the class', () => {
  const routes = JSON.parse(read(path.join(ROOT, 'data/freight/routes.json')));
  const n = (Array.isArray(routes) ? routes : routes.routes).filter((r) => r.vclass === 'container').length;
  const WORD = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'];
  assert.ok(n >= 1 && n < WORD.length, 'the number of container routes has a word');
  assert.match(section, new RegExp(`Container class is drawn on ${WORD[n]} routes`), `the section says that ${WORD[n]} routes are Container (data/freight/routes.json)`);
  assert.match(src('components/Legend.tsx'), /const SEGMENTS: Segment\[\] = \['dry', 'tanker', 'gas'\];/, 'the legend of the routes lists three classes, and Container is not one');
});
