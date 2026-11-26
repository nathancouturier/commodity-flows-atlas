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
  COUNTRY_MINZOOM, COUNTRY_TIERS, LABEL_COLOR, LABEL_FONT, GLYPH_STACK, SEA_MINZOOM, countryFilter, countryLayerSpecs, countryPoints, countryTier,
  labelLayerSpecs, seaLayerSpecs, seaPoints,
} from '../src/map/labelRules.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '../..');
const text = (rel) => fs.readFileSync(path.join(repo, rel), 'utf8');
const index = JSON.parse(text('data/countries/index.json'));
const seaFile = JSON.parse(text('data/geo/seas.json'));
const labelsSrc = text('web/src/map/labels.ts');
const basemapSrc = text('web/src/map/basemap.ts');
const controllerSrc = text('web/src/map/controller.ts');
const choroplethSrc = text('web/src/map/modules/choropleth.ts');

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
  for (const s of seaLayerSpecs()) assert.deepEqual(s.filter, ['==', ['get', 'r'], Number(s.id.slice(-1))]);
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
  assert.ok(/\.catch\(/.test(seas.slice(0, seas.indexOf(';'))), 'the load of the seas has its own catch');
  assert.ok(/addSource\(SEA_SOURCE/.test(labelsSrc) && /labelLayerSpecs\(/.test(labelsSrc));
  assert.ok(!/countryLayerSpecs\(/.test(labelsSrc), 'the layers come from labelLayerSpecs');
});

test('the sea names are not interactive, and the sea source has no click handler', () => {
  assert.ok(!/names-seas/.test(controllerSrc));
  assert.ok(!/(registerInteractiveLayer|registerPointLayer|\.on\()/.test(labelsSrc));
});

test('METHODOLOGY and the About window name the sea names as they are built', () => {
  const md = text('METHODOLOGY.md').replace(/\s+/g, ' ');
  const by = (r) => seaFile.seas.filter((s) => s.r === r).length;
  assert.ok(md.includes(`${seaFile.seas.length} names, of which ${by(0)} oceans (rank 0), ${by(1)} of rank 1, ${by(2)} of rank 2 and ${by(3)} of rank 3`));
  assert.ok(md.includes(seaFile.n.match(/version (\d+\.\d+\.\d+)/)[1]), 'the version of the file');
  assert.ok(md.includes('Straits and channels are left out'));
  assert.ok(/sea names from Natural Earth marine areas 1:50m; map lettering in Inter/.test(text('web/src/components/AboutDialog.tsx').replace(/\s+/g, ' ')));
});
