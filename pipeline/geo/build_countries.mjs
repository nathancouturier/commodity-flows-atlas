/**
 * Builds the country base layer and country index from Natural Earth 1:50m admin-0.
 *
 *   node pipeline/geo/build_countries.mjs raw/naturalearth/ne_50m/ne_50m_admin_0_countries.shp
 *
 * Outputs
 *   data/geo/countries.topo.json   simplified TopoJSON, one object "countries", property c = ISO3
 *   data/countries/index.json      [{c, name, at:[lon,lat], bb:[w,s,e,n], region}]
 *
 * Natural Earth is public domain (https://www.naturalearthdata.com/about/terms-of-use/).
 */
import mapshaper from '../../web/node_modules/mapshaper/mapshaper.js';
import fs from 'node:fs';

const shp = process.argv[2];
if (!shp) throw new Error('usage: build_countries.mjs <ne_50m_admin_0_countries.shp>');

// Short, common English names where Natural Earth's NAME is abbreviated or formal.
const NAME_FIX = {
  COD: 'DR Congo', COG: 'Congo (Rep.)', CAF: 'Central African Rep.', USA: 'United States',
  GBR: 'United Kingdom', KOR: 'South Korea', PRK: 'North Korea', RUS: 'Russia', IRN: 'Iran',
  SYR: 'Syria', LAO: 'Laos', VNM: 'Vietnam', BOL: 'Bolivia', VEN: 'Venezuela', TZA: 'Tanzania',
  CZE: 'Czechia', MDA: 'Moldova', BIH: 'Bosnia and Herzegovina', DOM: 'Dominican Rep.',
  GNQ: 'Equatorial Guinea', SSD: 'South Sudan', ARE: 'United Arab Emirates', CIV: "Côte d'Ivoire",
  MKD: 'North Macedonia', SWZ: 'Eswatini', TWN: 'Taiwan', BRN: 'Brunei', TLS: 'Timor-Leste',
  PNG: 'Papua New Guinea', SLB: 'Solomon Islands', FLK: 'Falkland Islands', ESH: 'Western Sahara',
  PSE: 'Palestine', ATF: 'French Southern Lands', SAU: 'Saudi Arabia',
};

const cmd = [
  `-i "${shp}" encoding=utf8`,
  `-each "c = (ISO_A3_EH && ISO_A3_EH !== '-99') ? ISO_A3_EH : ADM0_A3, a2 = (ISO_A2_EH && ISO_A2_EH !== '-99') ? ISO_A2_EH : ISO_A2, nm = NAME, rg = SUBREGION, lx = LABEL_X, ly = LABEL_Y"`,
  `-filter "c !== 'ATA'"`, // Antarctica adds weight and no trade
  `-each "a = this.area"`,
  `-sort a descending`,
  // merge dependencies that share a code (e.g. Australian islands); keep attributes of the largest part
  `-dissolve c copy-fields=a2,nm,rg,lx,ly`,
  `-filter-fields c,a2,nm,rg,lx,ly`,
  `-simplify 35% keep-shapes`,
  `-o out.json format=geojson`,
].join(' ');

const out = await mapshaper.applyCommands(cmd);
const gj = JSON.parse(out['out.json']);

const index = [];
for (const f of gj.features) {
  const p = f.properties;
  // Camera bounds: parts that are large (>= 25% of the biggest part, by approximate km2) or
  // close to the label point (< 30 degrees). Overseas territories therefore do not widen the view.
  const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
  const parts = polys.map((poly) => {
    const ring = poly[0];
    let a = 0, cx = 0, cy = 0;
    for (let i = 0; i < ring.length - 1; i++) a += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1];
    for (const [x, y] of ring) { cx += x; cy += y; }
    cx /= ring.length; cy /= ring.length;
    return { ring, area: Math.abs(a / 2) * Math.cos((cy * Math.PI) / 180), cx, cy };
  });
  const big = Math.max(...parts.map((q) => q.area));
  const near = (q) => {
    let dx = Math.abs(q.cx - p.lx);
    if (dx > 180) dx = 360 - dx;
    return Math.hypot(dx, q.cy - p.ly) < 30;
  };
  const keep = parts.filter((q) => q.area >= big * 0.25 || near(q));
  const lons = [];
  const lats = [];
  for (const q of keep) for (const [x, y] of q.ring) { lons.push(x); lats.push(y); }
  let w = Math.min(...lons), e = Math.max(...lons);
  if (e - w > 180) {
    const shifted = lons.map((x) => (x < 0 ? x + 360 : x));
    w = Math.min(...shifted);
    e = Math.max(...shifted);
  }
  const r = (x) => Math.round(x * 100) / 100;
  index.push({ c: p.c, a2: p.a2, name: NAME_FIX[p.c] ?? p.nm, at: [r(p.lx), r(p.ly)], bb: [r(w), r(Math.min(...lats)), r(e), r(Math.max(...lats))], region: p.rg });
}
index.sort((a, b) => a.name.localeCompare(b.name));

// TopoJSON keeps only the ISO3 code; names come from the index.
const topoCmd = [
  `-i out.json`,
  `-filter-fields c`,
  `-rename-layers countries`,
  `-o countries.topo.json format=topojson quantization=60000`,
].join(' ');
const topo = await mapshaper.applyCommands(topoCmd, { 'out.json': out['out.json'] });

fs.mkdirSync('data/geo', { recursive: true });
fs.mkdirSync('data/countries', { recursive: true });
fs.writeFileSync('data/geo/countries.topo.json', topo['countries.topo.json']);
fs.writeFileSync('data/countries/index.json', JSON.stringify(index));
console.log(`countries: ${index.length}, topojson ${(topo['countries.topo.json'].length / 1024).toFixed(0)} KB`);
