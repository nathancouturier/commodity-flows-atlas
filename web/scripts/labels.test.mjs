/**
 * Tests of the names on the map (src/map/labelRules.ts, labels.ts, the glyph URL of basemap.ts, the call in controller.ts):
 * `node --test web/scripts/labels.test.mjs`. The rules module is pure and runs as it is; the files that import the map library
 * are read as text. Counts are read from the files; the only typed numbers are the colours' minimum contrast and the edge cases of the rule.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  COUNTRY_MINZOOM, COUNTRY_SIZE_STOPS, COUNTRY_TEXT, COUNTRY_TIERS, LABEL_COLOR, LABEL_FONT, LABEL_ON_FILL, GLYPH_STACK, SEA_MINZOOM, SEA_TEXT,
  BOX_MARGIN, EDGE_COPIES, ICON_LAYER, NAME_STACK,
  boxCrossesEdge, countryEdgeNames, countryFilter, countryLayerSpecs, countryPoints, countrySizeAt, countryTier, namesAtEdge, oceanEdgeNames,
  labelLayerSpecs, seaFilter, seaLayerSpecs, seaPoints, stackViolations, textBox,
  ASSET_LABEL_MINZOOM, ASSET_ORDER, assetLabel, assetLayerSpec, assetSelectedTextLayout, assetTextPaint,
} from '../src/map/labelRules.ts';
import { decode } from './glyph-file.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '../..');
const text = (rel) => fs.readFileSync(path.join(repo, rel), 'utf8');
const index = JSON.parse(text('data/countries/index.json'));
const seaFile = JSON.parse(text('data/geo/seas.json'));
const labelsSrc = text('web/src/map/labels.ts');
const basemapSrc = text('web/src/map/basemap.ts');
const controllerSrc = text('web/src/map/controller.ts');
const choroplethSrc = text('web/src/map/modules/choropleth.ts');
const infraSrc = text('web/src/map/modules/infrastructure.ts');

// ---------------------------------------------------------------- size classes

test('every country of the index has exactly one size class, and the four counts add up to the index', () => {
  const counts = [0, 0, 0, 0];
  for (const c of index) {
    assert.ok(c.bb && c.at, `${c.c} has a box and an anchor`);
    const t = countryTier(c.bb);
    assert.ok([0, 1, 2, 3].includes(t), c.c);
    counts[t]++;
  }
  assert.equal(counts.reduce((a, b) => a + b, 0), index.length);
  assert.ok(counts.every((n) => n > 0), 'no empty class');
});

test('the edges of the classes: the threshold belongs to the smaller names, a hair above to the larger', () => {
  COUNTRY_TIERS.forEach((limit, i) => {
    assert.equal(countryTier([0, 0, limit, 1]), i + 1, `area ${limit}`);
    assert.equal(countryTier([0, 0, limit + 0.01, 1]), i, `area ${limit + 0.01}`);
  });
  assert.equal(countryTier([10, 10, 10, 10]), 3);
});

test('METHODOLOGY gives the counts of the classes as the index has them', () => {
  const counts = [0, 0, 0, 0];
  for (const c of index) counts[countryTier(c.bb)]++;
  const md = text('METHODOLOGY.md').replace(/\s+/g, ' ');
  assert.ok(md.includes(`${counts[0]}, ${counts[1]}, ${counts[2]} and ${counts[3]} of the ${index.length} rows of the index`), counts.join(','));
});

// ---------------------------------------------------------------- the points

test('the points are the rows of the index: as many as the file, none for the European Union', () => {
  const fc = countryPoints(index);
  assert.equal(fc.features.length, index.length);
  assert.ok(!fc.features.some((f) => f.properties.n === 'European Union (27)'));
  assert.equal(new Set(fc.features.map((f) => f.properties.c)).size, index.length);
  index.forEach((c, i) => {
    const f = fc.features[i];
    assert.deepEqual(f.geometry.coordinates, c.at);
    assert.equal(f.properties.n, c.name);
    assert.equal(f.properties.t, countryTier(c.bb));
    assert.equal(f.properties.a, (c.bb[2] - c.bb[0]) * (c.bb[3] - c.bb[1]));
  });
});

test('a row with no anchor or no box has no name', () => {
  const rows = [
    { c: 'AAA', name: 'A', at: [1, 2], bb: [0, 0, 1, 1] },
    { c: 'BBB', name: 'B', bb: [0, 0, 1, 1] },
    { c: 'CCC', name: 'C', at: [1, 2] },
  ];
  assert.deepEqual(countryPoints(rows).features.map((f) => f.properties.c), ['AAA']);
});

test('the names are built from the index file, never from the signal of the pages (which holds the European Union)', () => {
  assert.ok(!/countries\.value/.test(labelsSrc));
  assert.ok(/load<CountryMeta\[\]>\('countries\/index\.json'\)/.test(labelsSrc));
});

// ---------------------------------------------------------------- the layers

test('four layers, added from the smallest names to the largest so that the largest are placed first', () => {
  const specs = countryLayerSpecs();
  assert.deepEqual(specs.map((s) => s.id), ['names-countries-3', 'names-countries-2', 'names-countries-1', 'names-countries-0']);
  for (const s of specs) {
    assert.equal(s.type, 'symbol');
    assert.equal(s.source, 'names-countries');
    assert.deepEqual(s.layout['text-font'], LABEL_FONT);
    assert.deepEqual(s.layout['text-field'], ['get', 'n']);
    assert.deepEqual(s.layout['symbol-sort-key'], ['-', 0, ['get', 'a']]);
  }
});

test('the largest names have no zoom limit and the others appear later as they get smaller', () => {
  const byTier = Object.fromEntries(countryLayerSpecs().map((s) => [Number(s.id.slice(-1)), s]));
  assert.ok(!('minzoom' in byTier[0]), 'a limit below zero is not allowed, and the phone first view is below it');
  assert.equal(byTier[1].minzoom, COUNTRY_MINZOOM[1]);
  assert.equal(byTier[2].minzoom, COUNTRY_MINZOOM[2]);
  assert.equal(byTier[3].minzoom, COUNTRY_MINZOOM[3]);
  assert.ok(byTier[1].minzoom < byTier[2].minzoom && byTier[2].minzoom < byTier[3].minzoom);
});

test('the size of a name is an interpolation on the zoom: its first stop is at or above 0.5 and the size stays there below it', () => {
  for (const s of countryLayerSpecs()) {
    const size = s.layout['text-size'];
    assert.equal(size[0], 'interpolate');
    assert.deepEqual(size[2], ['zoom']);
    const stops = size.slice(3);
    assert.ok(stops[0] >= 0.5, 'the first stop');
    for (let i = 2; i < stops.length; i += 2) assert.ok(stops[i] > stops[i - 2], 'stops rise');
    assert.ok(stops.every((v, i) => i % 2 === 0 || v > 0));
  }
});

test('the filter of a class holds the hidden ids and nothing else changes', () => {
  assert.deepEqual(countryFilter(2, ['FRA', 'BRA']), ['all', ['==', ['get', 't'], 2], ['!', ['in', ['get', 'c'], ['literal', ['FRA', 'BRA']]]]]);
  assert.deepEqual(countryFilter(0, []), ['all', ['==', ['get', 't'], 0], ['!', ['in', ['get', 'c'], ['literal', []]]]]);
  const ids = ['USA'];
  const f = countryFilter(1, ids);
  ids.push('CHN');
  assert.deepEqual(f[2][1][2], ['literal', ['USA']], 'the filter does not follow the list it was given');
  for (const s of countryLayerSpecs(['FRA'])) assert.deepEqual(s.filter, countryFilter(Number(s.id.slice(-1)), ['FRA']));
});

// ---------------------------------------------------------------- the colours

const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
const lin = (v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const lum = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
/** WCAG contrast of text of colour `fg` drawn at `opacity` over the colour `bg`. */
function contrast(fg, opacity, bg) {
  const f = rgb(fg);
  const b = rgb(bg);
  const blend = f.map((v, i) => v * opacity + b[i] * (1 - opacity));
  const [hi, lo] = [lum(blend), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
const base = (key) => {
  const m = basemapSrc.match(new RegExp(`\\b${key}: '(#[0-9a-f]{6})'`));
  assert.ok(m, `C.${key} in basemap.ts`);
  return m[1];
};

test('the names are legible: at least 4.5 to 1 over the colour they sit on', () => {
  assert.ok(contrast(LABEL_COLOR.country, LABEL_COLOR.countryOpacity, base('land')) >= 4.5, 'countries over the land');
  assert.ok(contrast(LABEL_COLOR.sea, LABEL_COLOR.seaOpacity, base('ocean')) >= 4.5, 'seas over the ocean');
  assert.ok(contrast(LABEL_COLOR.asset, 1, base('land')) >= 4.5, 'assets over the land');
});

test('the halo of a name is the ocean colour, and the layers use the colours of the module', () => {
  assert.equal(LABEL_COLOR.halo, base('ocean'));
  for (const s of countryLayerSpecs()) {
    assert.equal(s.paint['text-halo-color'], base('ocean'));
    assert.equal(s.paint['text-halo-width'], LABEL_COLOR.haloWidth);
    assert.equal(s.paint['text-color'], LABEL_COLOR.country);
    assert.equal(s.paint['text-opacity'], LABEL_COLOR.countryOpacity);
  }
});

// ---------------------------------------------------------------- the glue, read as text

test('the style names the glyph files of the site: an absolute address from the page, with no outside host', () => {
  const m = basemapSrc.match(/glyphs:\s*`([^`]*)`/);
  assert.ok(m, 'a glyphs key in baseStyle()');
  assert.ok(m[1].endsWith('{fontstack}/{range}.pbf'), m[1]);
  assert.ok(m[1].includes('document.baseURI'), 'built from the address of the page');
  // `new URL('/', ...)` would be the root of the site: on GitHub Pages the atlas is served under a sub-path and every glyph request would be a 404
  assert.ok(m[1].startsWith("${new URL('./', document.baseURI).href}"), `relative to the page's own address, not to the root: ${m[1]}`);
  assert.ok(!m[1].includes('http'), 'no address typed');
  assert.ok(/typeof document !== 'undefined'/.test(basemapSrc), 'a test that imports the file has no document');
  assert.ok(!/https?:\/\/[^\s'"`]*glyph/i.test(basemapSrc + labelsSrc + controllerSrc), 'no glyph server');
  assert.equal(GLYPH_STACK, 'inter-medium');
});

test('the controller installs the names when the map has loaded, before the countries and the modules', () => {
  const load = controllerSrc.indexOf("map.on('load'");
  assert.ok(load > 0);
  const install = controllerSrc.indexOf('installLabels(m)', load);
  const countries = controllerSrc.indexOf('await loadCountries(m)', load);
  const ready = controllerSrc.indexOf('readyCallbacks.splice(0)', load);
  assert.ok(install > load && install < countries && countries < ready, 'installLabels(m) before loadCountries(m)');
});

test('the names are not interactive: no layer is registered for a hover or a click', () => {
  assert.ok(!/registerInteractiveLayer|registerPointLayer/.test(labelsSrc));
  assert.ok(!/names-/.test(controllerSrc.replace(/installLabels/g, '')), 'the controller does not know a name layer');
});

test('the colouring leaves out the names under its share labels, and brings them back', () => {
  assert.ok(/hideCountryNames\(m, ranked\.map\(\(r\) => r\.c\)\.filter\(\(c\) => c !== 'EU27'\)\)/.test(choroplethSrc));
  assert.ok(/function clear\(m: MLMap\) \{[\s\S]*hideCountryNames\(m, \[\]\)/.test(choroplethSrc));
});

// ---------------------------------------------------------------- the seas

test('the sea points are the rows of the sea table: as many as the file, each at its anchor with its name and rank', () => {
  const fc = seaPoints(seaFile.seas);
  assert.equal(fc.features.length, seaFile.seas.length);
  assert.ok(fc.features.length > 0);
  seaFile.seas.forEach((s, i) => {
    assert.deepEqual(fc.features[i].geometry.coordinates, s.at);
    assert.deepEqual(fc.features[i].properties, { n: s.n, r: s.r });
  });
  assert.ok(seaFile.seas.every((s) => [0, 1, 2, 3].includes(s.r)), 'ranks 0 to 3');
});

test('the layers are added the seas first and the countries after, each from the smallest names to the largest: the last is the top', () => {
  assert.deepEqual(
    labelLayerSpecs().map((s) => s.id),
    [3, 2, 1, 0].map((r) => `names-seas-${r}`).concat([3, 2, 1, 0].map((t) => `names-countries-${t}`)),
  );
  assert.deepEqual(labelLayerSpecs(['FRA']).slice(4), countryLayerSpecs(['FRA']), 'the hidden ids reach the country layers');
  assert.deepEqual(labelLayerSpecs().slice(0, 4), seaLayerSpecs());
});

test('the oceans have no zoom limit and the other ranks appear later as they get smaller', () => {
  const byRank = Object.fromEntries(seaLayerSpecs().map((s) => [Number(s.id.slice(-1)), s]));
  assert.ok(!('minzoom' in byRank[0]), 'a limit below zero is not allowed, and the phone first view is below it');
  for (const r of [1, 2, 3]) assert.equal(byRank[r].minzoom, SEA_MINZOOM[r]);
  assert.ok(byRank[1].minzoom < byRank[2].minzoom && byRank[2].minzoom < byRank[3].minzoom);
  for (const s of seaLayerSpecs()) assert.deepEqual(s.filter, seaFilter(Number(s.id.slice(-1)), []));
});

test('a sea layer is a symbol layer of the sea source in the glyph file font, upper case, spaced, in the sea colour', () => {
  for (const s of seaLayerSpecs()) {
    assert.equal(s.type, 'symbol');
    assert.equal(s.source, 'names-seas');
    assert.deepEqual(s.layout['text-field'], ['get', 'n']);
    assert.deepEqual(s.layout['text-font'], LABEL_FONT);
    assert.equal(s.layout['text-transform'], 'uppercase', 'the glyph file is checked for the upper case of the sea names');
    assert.equal(s.layout['text-letter-spacing'], 0.16);
    assert.equal(s.layout['text-size'], s.id.endsWith('-0') ? 12 : 10.5);
    assert.ok(!('symbol-sort-key' in s.layout), 'the sort key belongs to the countries');
    assert.equal(s.paint['text-color'], LABEL_COLOR.sea);
    assert.equal(s.paint['text-opacity'], LABEL_COLOR.seaOpacity);
    assert.equal(s.paint['text-halo-color'], base('ocean'));
    assert.equal(s.paint['text-halo-width'], LABEL_COLOR.haloWidth);
  }
});

test('the colour the sea layers carry is legible over the ocean it sits on (at least 4.5 to 1)', () => {
  for (const s of seaLayerSpecs()) assert.ok(contrast(s.paint['text-color'], s.paint['text-opacity'], base('ocean')) >= 4.5, s.id);
});

test('a sea is never also a country of the index, and no name of the table is a strait or a channel', () => {
  const countries = new Set(index.map((c) => c.name.toLowerCase()));
  for (const s of seaFile.seas) {
    assert.ok(!countries.has(s.n.toLowerCase()), s.n);
    assert.ok(!/\b(strait|channel|passage)\b/i.test(s.n), `${s.n} is a passage: the atlas draws those as markers`);
  }
});

test('the sea names are read from the sea table, and a table that is missing leaves the seas without names and the countries with theirs', () => {
  assert.ok(/load<\{ seas: Sea\[\] \}>\('geo\/seas\.json'\)/.test(labelsSrc));
  const loads = labelsSrc.match(/\.catch\(\(\) => undefined\)/g) ?? [];
  assert.equal(loads.length, 2, 'one .catch for the countries and one for the seas');
  const seas = labelsSrc.slice(labelsSrc.indexOf("load<{ seas"));
  assert.ok(/\.catch\(/.test(seas.slice(0, seas.indexOf('\n}\n'))), 'the load of the seas has its own catch');
  assert.ok(/addSource\(SEA_SOURCE/.test(labelsSrc) && /labelLayerSpecs\(/.test(labelsSrc));
  // a colouring that is on before the layers are added must leave its names out from the first frame
  assert.ok(/for \(const spec of labelLayerSpecs\(hidden\)\) m\.addLayer\(spec\);/.test(labelsSrc), 'installLabels gives the hidden ids to the layer specs');
  assert.ok(!/countryLayerSpecs\(/.test(labelsSrc), 'the layers come from labelLayerSpecs');
});

test('the sea names are not interactive, and the sea source has no click handler', () => {
  assert.ok(!/names-seas/.test(controllerSrc));
  assert.ok(!/(registerInteractiveLayer|registerPointLayer)/.test(labelsSrc));
  assert.ok(!/\.on\('(click|dblclick|contextmenu|mouse\w+|touch\w+)'/.test(labelsSrc), 'no handler of a pointer on a name');
});

test('METHODOLOGY and the About window name the sea names as they are built', () => {
  const md = text('METHODOLOGY.md').replace(/\s+/g, ' ');
  const by = (r) => seaFile.seas.filter((s) => s.r === r).length;
  assert.ok(md.includes(`${seaFile.seas.length} names, of which ${by(0)} oceans (rank 0), ${by(1)} of rank 1, ${by(2)} of rank 2 and ${by(3)} of rank 3`));
  assert.ok(md.includes(seaFile.n.match(/version (\d+\.\d+\.\d+)/)[1]), 'the version of the file');
  assert.ok(md.includes('Straits and channels are left out'));
  assert.ok(/sea names from Natural Earth marine areas 1:50m; map lettering in Inter/.test(text('web/src/components/AboutDialog.tsx').replace(/\s+/g, ' ')));
});

// ---------------------------------------------------------------- the ports and assets

/** Every point feature of the infrastructure files (the pipelines are lines and have no name on the map). */
const infraPoints = fs
  .readdirSync(path.join(repo, 'data/infrastructure'))
  .filter((f) => f.endsWith('.geojson'))
  .flatMap((f) => JSON.parse(text(`data/infrastructure/${f}`)).features)
  .filter((f) => f.geometry.type === 'Point');

test('the name of every point asset is short, without a bracket at its end, and does not change when the rule is applied again', () => {
  assert.ok(infraPoints.length > 0);
  for (const f of infraPoints) {
    const name = f.properties.name;
    const label = assetLabel(name);
    assert.ok(label.length > 0, `${name} has a name on the map`);
    assert.ok(!/\)\s*$/.test(label), `${name}: the list of places in brackets at the end is dropped`);
    assert.ok(label.length <= 60, `${name} is ${label.length} characters (one short name, wrapped by the layer)`);
    assert.equal(assetLabel(label), label, `${name}: idempotent`);
  }
  assert.equal(assetLabel('Hydro aluminium smelters (Årdal, Husnes, Karmøy)'), 'Hydro aluminium smelters');
  assert.equal(assetLabel('Pernis (Shell), Rotterdam'), 'Pernis (Shell), Rotterdam', 'a bracket in the middle of a name stays');
});

test('every type of the point assets has a place in the priority table, and the table holds no other type', () => {
  const types = [...new Set(infraPoints.map((f) => f.properties.type))].sort();
  assert.deepEqual(Object.keys(ASSET_ORDER).sort(), types);
  assert.ok(!('pipeline' in ASSET_ORDER));
  const ranks = Object.values(ASSET_ORDER);
  assert.ok(ranks.every(Number.isInteger), 'integers');
  assert.equal(new Set(ranks).size, ranks.length, 'distinct');
  const counts = {};
  for (const f of infraPoints) counts[f.properties.type] = (counts[f.properties.type] ?? 0) + 1;
  assert.ok(Object.values(counts).every((n) => n > 0));
});

test('the layer of asset names: from the zoom of the module, one short name to the right of the icon, an icon never lost for its name', () => {
  const spec = assetLayerSpec('infra-pts');
  assert.equal(spec.id, 'infra-names');
  assert.equal(spec.type, 'symbol');
  assert.equal(spec.source, 'infra-pts');
  assert.equal(spec.minzoom, ASSET_LABEL_MINZOOM);
  assert.ok(ASSET_LABEL_MINZOOM >= 0, 'a layer limit below zero is not valid');
  assert.deepEqual(spec.layout['text-field'], ['get', 'label']);
  assert.deepEqual(spec.layout['text-font'], LABEL_FONT);
  assert.equal(spec.layout['text-optional'], true);
  assert.equal(spec.layout['text-anchor'], 'left');
  assert.ok(spec.layout['text-offset'][0] > 0 && spec.layout['text-offset'][1] === 0, 'to the right');
  assert.deepEqual(spec.layout['symbol-sort-key'], ['get', 'rank']);
  assert.ok(!('text-transform' in spec.layout), 'the glyph file holds no accented capital');
  assert.ok(!('text-allow-overlap' in spec.layout), 'a name that would overlap a placed name is not drawn');
  assert.ok(!('icon-image' in spec.layout), 'the names carry no icon');
});

test('a name is dimmed as its icon is, and its colour and halo are those of the module', () => {
  const paint = assetLayerSpec('s').paint;
  assert.deepEqual(paint['text-opacity'], ['get', 'op']);
  assert.equal(paint['text-color'], LABEL_COLOR.asset);
  assert.equal(paint['text-halo-color'], base('ocean'));
  assert.equal(paint['text-halo-width'], LABEL_COLOR.haloWidth);
  assert.deepEqual(assetTextPaint(), paint);
  assert.ok(contrast(paint['text-color'], 1, base('land')) >= 4.5, 'over the land');
});

test('the opened asset keeps its name at every zoom: the same text, allowed to overlap, with no zoom limit', () => {
  const sel = assetSelectedTextLayout();
  assert.equal(sel['text-allow-overlap'], true);
  assert.ok(!('minzoom' in sel));
  const { 'text-allow-overlap': _drop, ...rest } = sel;
  const { 'symbol-sort-key': _key, ...named } = assetLayerSpec('s').layout;
  assert.deepEqual(rest, named, 'the same text as the other names');
});

test('infrastructure.ts adds the names under the icons and leaves the icons as they were', () => {
  const add = 'm.addLayer(assetLayerSpec(SRC_PTS), ICON_LAYER);';
  assert.equal(ICON_LAYER, 'infra-pts-all');
  assert.ok(infraSrc.includes(add), 'the layer is added with the icon layer as its before-id');
  const icons = infraSrc.indexOf("id: 'infra-pts-all'");
  assert.ok(icons > 0 && infraSrc.indexOf(add) > icons, 'added after the icon layer exists');
  assert.ok(infraSrc.indexOf(add) < infraSrc.indexOf("id: 'infra-halo'"), 'before the selection layers');
  const lay = infraSrc.slice(infraSrc.indexOf('const iconLayout = {'), infraSrc.indexOf('} as const;'));
  assert.ok(/'icon-allow-overlap': true/.test(lay), 'icons may overlap');
  assert.ok(/'icon-ignore-placement': true/.test(lay), 'icons never take a place from another');
  assert.ok(/'symbol-sort-key': \['get', 'op'\]/.test(lay), 'the sort key of the icons');
  assert.ok(!/text-/.test(lay), 'no text property in the icon layout');
  const sel = infraSrc.slice(infraSrc.indexOf("id: 'infra-pts-sel'"));
  const selLayer = sel.slice(0, sel.indexOf('\n  });'));
  assert.ok(/assetSelectedTextLayout\(\)/.test(selLayer) && /assetTextPaint\(\)/.test(selLayer), 'the opened asset has the text properties');
  assert.ok(!/minzoom/.test(selLayer));
});

test('each point carries its name and its priority; the names are not interactive; the pipelines have no name', () => {
  assert.ok(/type PointProps = \{[^}]*label: string; rank: number/.test(infraSrc));
  assert.ok(/label: assetLabel\(f\.p\.name\)/.test(infraSrc));
  assert.ok(/rank: ASSET_ORDER\[/.test(infraSrc));
  assert.ok(/const hitLayers = \['infra-pts-all', 'infra-pts-sel', 'infra-lines-hit'\]/.test(infraSrc), 'the layers that answer a hover or a click');
  assert.ok(/\['infra-pts-all', 'infra-pts-sel'\]\.forEach\(registerPointLayer\)/.test(infraSrc));
  assert.ok(!/registerInteractiveLayer\('infra-names'|registerPointLayer\('infra-names'/.test(infraSrc));
  assert.ok(!/infra-names/.test(controllerSrc));
  const lines = infraSrc.slice(infraSrc.indexOf("f.p.type === 'pipeline'"), infraSrc.indexOf('} else if (f.geom.type'));
  assert.ok(!/assetLabel|rank:/.test(lines), 'a pipeline has no single point to name');
});

test('METHODOLOGY states how the names of ports and assets are placed', () => {
  const md = text('METHODOLOGY.md').replace(/\s+/g, ' ');
  assert.ok(md.includes('**Names of ports and assets.**'));
  assert.ok(md.includes(`from zoom ${ASSET_LABEL_MINZOOM}`));
  const words = { port: 'port', 'lng-export': 'LNG export terminal', 'lng-import': 'LNG import terminal', refinery: 'refinery', smelter: 'smelter', mine: 'mine', field: 'field', storage: 'store' };
  const byRank = Object.entries(ASSET_ORDER).sort((a, b) => a[1] - b[1]).map(([type]) => words[type]);
  assert.ok(byRank.every(Boolean), 'a word for every type');
  assert.ok(md.includes(byRank.join(', ')), 'the order of the table, in the words of the page');
});

// ---------------------------------------------------------------- a name is not drawn cut by an edge of the canvas

const glyphs = decode(fs.readFileSync(path.join(repo, 'web/public/glyphs', GLYPH_STACK, '0-255.pbf'))).glyphs;
/** The advance of a character in ems, read from the glyph file (its bitmaps are 24 px). */
const advance = (ch) => glyphs.get(ch.codePointAt(0)).advance / 24;
/** The widest line and the number of lines of a name set as the library sets it, with the true advances and a greedy break. */
function setTrue(text, maxWidth, spacing) {
  const width = (w) => [...w].reduce((a, ch) => a + advance(ch) + spacing, 0);
  let lines = 1;
  let widest = 0;
  let line = 0;
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const w = width(word);
    const gap = advance(' ') + spacing;
    if (line === 0) line = w;
    else if (line + gap + w <= maxWidth) line += gap + w;
    else {
      widest = Math.max(widest, line);
      line = w;
      lines++;
    }
  }
  return { widest: Math.max(widest, line), lines };
}

test('the estimated box of a name is never narrower or lower than the lettering: every ocean, and every country of the largest class at every size', () => {
  const seaRows = seaFile.seas.filter((s) => s.r === 0);
  assert.equal(seaRows.length, 7);
  for (const s of seaRows) {
    const text = s.n.toUpperCase();
    const box = textBox(text, SEA_TEXT.oceanSize, SEA_TEXT.maxWidth, SEA_TEXT.letterSpacing);
    const real = setTrue(text, SEA_TEXT.maxWidth, SEA_TEXT.letterSpacing);
    assert.ok(box.w >= real.widest * SEA_TEXT.oceanSize + 2 * BOX_MARGIN, `${s.n}: ${box.w} px for ${real.widest * SEA_TEXT.oceanSize}`);
    assert.ok(box.h >= real.lines * 1.2 * SEA_TEXT.oceanSize + 2 * BOX_MARGIN, `${s.n}: ${box.h} px high`);
  }
  const tier0 = index.filter((c) => countryTier(c.bb) === 0);
  assert.ok(tier0.length > 10);
  for (const c of tier0) {
    for (const size of [COUNTRY_SIZE_STOPS[1], COUNTRY_SIZE_STOPS[3], COUNTRY_SIZE_STOPS[5]]) {
      const box = textBox(c.name, size, COUNTRY_TEXT.maxWidth, 0);
      const real = setTrue(c.name, COUNTRY_TEXT.maxWidth, 0);
      assert.ok(box.w >= real.widest * size + 2 * BOX_MARGIN, `${c.name} at ${size}: ${box.w} px for ${real.widest * size}`);
      assert.ok(box.h >= real.lines * 1.2 * size + 2 * BOX_MARGIN, `${c.name} at ${size}: ${box.h} px high`);
    }
  }
});

test('a name wraps at its maximum width, a word wider than it keeps its own line, and the box grows with the size', () => {
  const one = textBox('ARCTIC', 12, 6, 0.16);
  const two = textBox('SOUTH PACIFIC', 12, 6, 0.16);
  assert.ok(two.h > one.h && two.w >= one.w, 'two lines');
  assert.equal(textBox('SOUTH PACIFIC OCEAN', 12, 6, 0.16).h, 3 * 1.2 * 12 + 2 * BOX_MARGIN, 'three lines of 12 px');
  assert.equal(textBox('Peru', 10, 6, 0).h, 1.2 * 10 + 2 * BOX_MARGIN);
  assert.ok(textBox('Peru', 20, 6, 0).w > textBox('Peru', 10, 6, 0).w);
  assert.ok(textBox('SOUTH PACIFIC OCEAN', 12, 100, 0.16).h < two.h * 2, 'a wide limit keeps one line');
});

test('a box is cut when it is partly on the canvas and partly off it, on each of the four edges', () => {
  const box = { w: 80, h: 30 };
  const [W, H] = [600, 400];
  assert.equal(boxCrossesEdge(300, 200, box, W, H), false, 'inside');
  assert.equal(boxCrossesEdge(40, 200, box, W, H), false, 'touching the left edge is inside');
  assert.equal(boxCrossesEdge(W - 40, 200, box, W, H), false, 'touching the right edge is inside');
  assert.equal(boxCrossesEdge(300, 15, box, W, H), false, 'touching the top edge');
  assert.equal(boxCrossesEdge(300, H - 15, box, W, H), false, 'touching the bottom edge');
  assert.equal(boxCrossesEdge(39, 200, box, W, H), true, 'left, by a pixel');
  assert.equal(boxCrossesEdge(W - 39, 200, box, W, H), true, 'right');
  assert.equal(boxCrossesEdge(300, 14, box, W, H), true, 'top');
  assert.equal(boxCrossesEdge(300, H - 14, box, W, H), true, 'bottom');
  assert.equal(boxCrossesEdge(0, 200, box, W, H), true, 'centred on the edge');
  assert.equal(boxCrossesEdge(-40, 200, box, W, H), false, 'wholly outside, on the left edge');
  assert.equal(boxCrossesEdge(-60, 200, box, W, H), false);
  assert.equal(boxCrossesEdge(W + 40, 200, box, W, H), false);
  assert.equal(boxCrossesEdge(300, -15, box, W, H), false);
  assert.equal(boxCrossesEdge(300, H + 15, box, W, H), false);
  assert.equal(boxCrossesEdge(-30, -10, box, W, H), true, 'across a corner');
});

test('the names the edge cuts: those that cross it on any copy of the world, and none of those wholly in or wholly out', () => {
  const [W, H] = [600, 500];
  const box = { w: 80, h: 30 };
  // ten px a degree, the camera on 170 degrees east: the point at 170 is on the middle of the canvas, the world is 3600 px wide
  const project = (lng, lat) => ({ x: W / 2 + (lng - 170) * 10, y: H / 2 - lat * 10 });
  const at = (id, lng, lat) => ({ id, at: [lng, lat], box });
  const names = [
    at('inside', 170, 0), // x 300
    at('left edge', 170 - 29, 0), // x 10, the box reaches x -30
    at('right edge', 170 + 29, 0), // x 590
    at('top edge', 170, 24), // y 10
    at('bottom edge', 170, -24),
    at('outside', 170 + 80, 0), // x 1100
    at('antimeridian copy', -161, 0), // its own copy is at x -3010, the copy 360 degrees east at 199 degrees is x 590
    at('antimeridian inside', -174, 0), // the copy at 186 degrees is x 460: inside
  ];
  assert.deepEqual(namesAtEdge(names, project, W, H).sort(), ['antimeridian copy', 'bottom edge', 'left edge', 'right edge', 'top edge']);
  assert.deepEqual(namesAtEdge(names, project, 0, H), [], 'a canvas with no size has no names to cut');
  assert.ok(EDGE_COPIES >= 2, 'at least the copies on each side of the camera');
  // the copy that crosses the edge is only found on the copy it is on
  assert.deepEqual(namesAtEdge([at('far copy', 170 - 29 + 720, 0)], project, W, H), ['far copy']);
});

test('the oceans are the seven rows of rank 0 and the largest class of countries is the rows of the index of that class', () => {
  const o = oceanEdgeNames(seaFile.seas);
  assert.deepEqual(o.map((x) => x.id), seaFile.seas.filter((s) => s.r === 0).map((s) => s.n));
  for (const x of o) assert.deepEqual(x.box, textBox(x.id.toUpperCase(), SEA_TEXT.oceanSize, SEA_TEXT.maxWidth, SEA_TEXT.letterSpacing));
  const c = countryEdgeNames(index, 1.5);
  assert.deepEqual(c.map((x) => x.id), index.filter((r) => countryTier(r.bb) === 0).map((r) => r.c));
  assert.ok(!c.some((x) => x.id === 'EU27'));
  for (const x of c) assert.deepEqual(x.box, textBox(index.find((r) => r.c === x.id).name, countrySizeAt(1.5), COUNTRY_TEXT.maxWidth, 0));
  assert.ok(countryEdgeNames(index, 4)[0].box.w > countryEdgeNames(index, 1)[0].box.w, 'the size follows the zoom');
});

test('the size of a country name at a zoom is the layer\'s interpolation, flat outside its first and last stops', () => {
  const size = countryLayerSpecs()[0].layout['text-size'];
  assert.deepEqual(size, ['interpolate', ['linear'], ['zoom'], ...COUNTRY_SIZE_STOPS]);
  const stops = COUNTRY_SIZE_STOPS;
  for (let i = 0; i < stops.length; i += 2) assert.equal(countrySizeAt(stops[i]), stops[i + 1]);
  assert.equal(countrySizeAt(-1), stops[1]);
  assert.equal(countrySizeAt(20), stops[stops.length - 1]);
  assert.equal(countrySizeAt((stops[0] + stops[2]) / 2), (stops[1] + stops[3]) / 2);
});

test('the edge rule runs when the camera comes to rest and when the canvas is resized, never during a move, and sets a filter only when the list changes', () => {
  assert.ok(/m\.on\('moveend', \(\) => leaveOutCut\(m\)\);/.test(labelsSrc));
  assert.ok(/m\.on\('resize', \(\) => leaveOutCut\(m\)\);/.test(labelsSrc));
  assert.ok(!/\.on\('(move|movestart|zoom|zoomstart|drag|render|data|sourcedata|idle|rotate|pitch)'/.test(labelsSrc), 'no handler of a move in progress');
  assert.equal((labelsSrc.match(/\.on\(/g) ?? []).length, 2, 'two handlers, no other');
  const fn = labelsSrc.slice(labelsSrc.indexOf('function leaveOutCut'));
  assert.ok(/if \(!same\(now, cutOceans\)\)/.test(fn) && /if \(!same\(now, cutCountries\)\)/.test(fn));
  assert.ok(/m\.setFilter\(OCEANS, seaFilter\(0, cutOceans\)\)/.test(fn));
  assert.ok(/m\.setFilter\(LARGEST, countryFilter\(0, \[\.\.\.hidden, \.\.\.cutCountries\]\)\)/.test(fn), 'the colouring\'s hidden ids stay in the filter of the largest class');
  assert.ok(/hideCountryNames[\s\S]*t === 0 \? \[\.\.\.hidden, \.\.\.cutCountries\] : hidden/.test(labelsSrc), 'and the cut names stay out when the colouring changes');
});

test('the filter of the oceans carries the names left out and nothing else changes', () => {
  assert.deepEqual(seaFilter(0, ['Arctic Ocean']), ['all', ['==', ['get', 'r'], 0], ['!', ['in', ['get', 'n'], ['literal', ['Arctic Ocean']]]]]);
  const left = seaLayerSpecs(['Arctic Ocean']);
  assert.deepEqual(left.find((s) => s.id === 'names-seas-0').filter, seaFilter(0, ['Arctic Ocean']));
  for (const s of left.filter((x) => x.id !== 'names-seas-0')) assert.deepEqual(s.filter, seaFilter(Number(s.id.slice(-1)), []), 'the other ranks are left as they are');
  assert.deepEqual(labelLayerSpecs(['FRA'], ['Arctic Ocean']).slice(0, 4), left);
});

// ---------------------------------------------------------------- the order of the layers

test('the names are stacked under the icons: seas, pipelines, asset names, country names, icons; a style in another order is told', () => {
  assert.deepEqual(stackViolations(NAME_STACK), []);
  assert.deepEqual(stackViolations(['land', ...NAME_STACK, 'ls-lanes-line']), []);
  assert.deepEqual(stackViolations(['names-countries-0', 'infra-names']), ['infra-names above names-countries-0'], 'the asset names above the country names');
  assert.deepEqual(stackViolations(['infra-names', 'names-countries-3', 'names-countries-2']), []);
  assert.equal(stackViolations(['names-countries-0', 'infra-pts-all', 'infra-names']).length > 0, true, 'asset names above the icons');
  assert.equal(stackViolations(['names-countries-0', 'names-seas-0']).length, 1, 'sea names above the country names');
  assert.equal(stackViolations(['infra-lines-glow', 'names-seas-3']).length, 1, 'sea names above the pipelines');
  assert.deepEqual(stackViolations(['land', 'borders']), [], 'layers outside the stack are not looked at');
  assert.equal(NAME_STACK.indexOf('infra-names') < NAME_STACK.indexOf('names-countries-3'), true, 'a country name is placed before an asset name');
  assert.equal(NAME_STACK.indexOf('names-countries-0') + 1, NAME_STACK.indexOf(ICON_LAYER), 'and is under the icons');
  assert.ok(NAME_STACK.indexOf('names-seas-0') < NAME_STACK.indexOf('infra-lines-glow'), 'sea names give way to both');
});

test('the specs add the country layers from the smallest to the largest and the module of the icons raises them above the asset names', () => {
  const asset = infraSrc.indexOf('m.addLayer(assetLayerSpec(SRC_PTS), ICON_LAYER);');
  const raise = infraSrc.indexOf('raiseCountryNames(m, ICON_LAYER);');
  assert.ok(asset > 0 && raise > asset && raise < infraSrc.indexOf("id: 'infra-halo'"), 'raised right after the asset names exist');
  assert.ok(/import \{ raiseCountryNames \} from '\.\.\/labels';/.test(infraSrc));
  // the other order of the two modules: the asset names are there already when the country layers are added
  assert.ok(/if \(m\.getLayer\(ICON_LAYER\)\) raiseCountryNames\(m, ICON_LAYER\);/.test(labelsSrc));
  assert.ok(labelsSrc.indexOf('labelLayerSpecs(hidden)') < labelsSrc.indexOf('raiseCountryNames(m, ICON_LAYER)'));
  const fn = labelsSrc.slice(labelsSrc.indexOf('export function raiseCountryNames'));
  assert.ok(/for \(const t of \[\.\.\.TIERS\]\.reverse\(\)\)/.test(fn) && /m\.moveLayer\(id, before\)/.test(fn), 'the smallest first, so the largest ends on top');
});

// ---------------------------------------------------------------- the names on a colouring

const hexOf = (c) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
const luminance = (c) => lum(c.map((v) => v / 255));
const ratio = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};
const blend = (fg, a, bg) => fg.map((v, i) => v * a + bg[i] * (1 - a));

test('the names on a colouring: the text against its halo, the halo against the brightest fill of the scale, the text against the land', () => {
  const format = text('web/src/lib/format.ts');
  const family = Object.fromEntries([...format.match(/FAMILY_COLOR: Record<Family, string> = \{([\s\S]*?)\};/)[1].matchAll(/(\w+): '(#[0-9a-f]{6})'/g)].map((m) => [m[1], m[2]]));
  assert.ok(Object.keys(family).length >= 3, JSON.stringify(family));
  const stops = [...format.match(/SHARE_STOPS: \[number, number\]\[\] = \[([\s\S]*?)\];/)[1].matchAll(/\[([\d.]+), ([\d.]+)\]/g)].map((m) => [Number(m[1]), Number(m[2])]);
  const top = stops[stops.length - 1][1];
  const land = hexOf(base('land'));
  const halo = hexOf(LABEL_ON_FILL.haloColor ?? LABEL_COLOR.halo);
  const ink = blend(hexOf(LABEL_ON_FILL.color), LABEL_ON_FILL.opacity, halo);
  assert.ok(ratio(ink, halo) >= 7, `text against its halo: ${ratio(ink, halo).toFixed(1)}`);
  assert.ok(ratio(blend(hexOf(LABEL_ON_FILL.color), LABEL_ON_FILL.opacity, land), land) >= 7, 'text against the land colour');
  for (const [name, color] of Object.entries(family)) {
    // the strongest tint of the scale over the land: the lightest fill a name sits on
    const fill = blend(hexOf(color), top, land);
    assert.ok(ratio(halo, fill) >= 4.5, `halo against the ${name} fill at its strongest tint: ${ratio(halo, fill).toFixed(1)}`);
  }
  assert.ok(LABEL_ON_FILL.haloWidth > LABEL_COLOR.haloWidth, 'a wider halo than on the plain land');
  assert.ok(ratio(hexOf(LABEL_ON_FILL.color), land) > ratio(hexOf(LABEL_COLOR.country), land), 'lighter than the grey of the plain land');
});

test('the colouring puts the paint on the names and the switch-off puts the plain one back', () => {
  const fn = labelsSrc.slice(labelsSrc.indexOf('export function colourNamesOnFill'));
  for (const [prop, on, off] of [['text-color', 'LABEL_ON_FILL.color', 'LABEL_COLOR.country'], ['text-opacity', 'LABEL_ON_FILL.opacity', 'LABEL_COLOR.countryOpacity'], ['text-halo-width', 'LABEL_ON_FILL.haloWidth', 'LABEL_COLOR.haloWidth']]) {
    assert.ok(fn.includes(`m.setPaintProperty(id, '${prop}', on ? ${on} : ${off});`), prop);
  }
  assert.ok(/colourNamesOnFill\(m, true\);/.test(choroplethSrc));
  assert.ok(/function clear\(m: MLMap\) \{[\s\S]*colourNamesOnFill\(m, false\)/.test(choroplethSrc));
  for (const s of countryLayerSpecs()) {
    assert.equal(s.paint['text-color'], LABEL_COLOR.country, 'the layers start with the plain paint');
    assert.equal(s.paint['text-halo-width'], LABEL_COLOR.haloWidth);
  }
});

// ---------------------------------------------------------------- what METHODOLOGY says of the names

test('METHODOLOGY counts the entries of NAME_FIX as the builder has them, and says which names are Natural Earth\'s', () => {
  const src = text('pipeline/geo/build_countries.mjs');
  const body = src.slice(src.indexOf('const NAME_FIX = {'), src.indexOf('};', src.indexOf('const NAME_FIX = {')));
  const entries = [...body.matchAll(/\b([A-Z]{3}): (?:'[^']*'|"[^"]*")/g)];
  assert.ok(entries.length > 20);
  const md = text('METHODOLOGY.md').replace(/\s+/g, ' ');
  assert.ok(md.includes(`except where the atlas writes the name itself in \`NAME_FIX\` of \`pipeline/geo/build_countries.mjs\` (${entries.length} entries;`), `${entries.length} entries`);
  assert.ok(!/short forms such as "Central African Rep\." come from Natural Earth through/.test(md), 'the wrong sentence is gone');
  // an abbreviation that stays Natural Earth's is a row of the index that NAME_FIX does not hold
  const fixed = new Set(entries.map((m) => m[1]));
  assert.ok(index.some((c) => c.name === 'Antigua and Barb.' && !fixed.has(c.c)), 'the example of an abbreviation that is Natural Earth\'s');
  assert.ok(md.includes('a name is covered by the flows and the icons that cross it'));
});

test('METHODOLOGY states the order of the layers, the names at the edge and the paint on a colouring', () => {
  const md = text('METHODOLOGY.md').replace(/\s+/g, ' ');
  assert.ok(md.includes('A country name wins a collision with the name of an asset'));
  assert.ok(md.includes('the sea names, the pipeline lines, the asset names, the country names, the icons and the opened asset, then every lane and route'));
  assert.ok(md.includes('`NAME_STACK`'));
  assert.ok(md.includes('**Names at the edge.**') && md.includes('`namesAtEdge`') && md.includes('never during a move'));
  assert.ok(md.includes('The names of a smaller rank may be cut by the edge of the screen'));
  assert.ok(md.includes('`LABEL_ON_FILL`') && md.includes('No contrast of a glyph against a coloured fill is claimed'));
  assert.ok(md.includes(`white at ${LABEL_ON_FILL.opacity} with a halo ${LABEL_ON_FILL.haloWidth} px wide instead of the grey with a halo of ${LABEL_COLOR.haloWidth} px`));
  assert.equal(LABEL_ON_FILL.color, '#ffffff');
  assert.ok(md.includes('about one turn of the world (a 1440 by 900 screen shows 358 degrees at its first view'), 'the width of a first view is given with its screen');
  assert.ok(!md.includes('the first view of a desktop spans'));
});
