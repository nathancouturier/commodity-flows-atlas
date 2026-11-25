/**
 * The structured data of web/index.html (JSON-LD) is valid JSON and says only what the atlas can say of its data: it does not call the data
 * "Open data", it credits the daily prices to the EIA with Refinitiv as their source, it says that some terms are to be confirmed, and it offers
 * no download of the price series catalogue (the daily EIA prices are not offered as a file).
 *
 *     node web/scripts/page-metadata.test.mjs
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.resolve(here, '../index.html'), 'utf8');
const blocks = [...html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)].map((m) => m[1]);
assert.ok(blocks.length >= 1, 'the page holds a JSON-LD block');
const nodes = blocks.flatMap((b) => {
  const doc = JSON.parse(b); // a block that does not parse fails here
  return doc['@graph'] ?? [doc];
});
const dataset = nodes.find((n) => n['@type'] === 'Dataset');
assert.ok(dataset, 'the JSON-LD holds a Dataset');

const description = dataset.description;
assert.ok(!/open data/i.test(description), 'the description does not call the data "Open data"');
assert.ok(/^Data compiled for the atlas, as JSON files/.test(description), 'the description starts "Data compiled for the atlas, as JSON files"');
assert.ok(/monthly commodity prices \(World Bank\) and daily spot prices \(U\.S\. Energy Information Administration, which gives Refinitiv as their source\)/.test(description), 'the daily prices are the EIA\'s, with Refinitiv as their source');
assert.ok(!/monthly and daily commodity prices/.test(description), 'the monthly and the daily prices are not named together under "World Bank, EIA"');
assert.ok(/Licences are mixed/.test(description) && /terms of some sources are still to be confirmed \(see NOTICE\.md\)/.test(description), 'the description says that licences are mixed and that some terms are to be confirmed');

const downloads = (dataset.distribution ?? []).map((d) => d.contentUrl);
assert.ok(downloads.length >= 1, 'the Dataset still lists its other downloads');
assert.ok(!downloads.some((u) => /\/data\/prices\//.test(u)), 'no download of the price series catalogue (data/prices/)');
for (const u of downloads) assert.ok(/\/data\/(commodities\/index|sources)\.json$/.test(u), `unexpected download ${u}`);
console.log('page metadata: all checks passed');
