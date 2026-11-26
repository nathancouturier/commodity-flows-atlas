/**
 * The introduction of the Sources tab of the About window, which names the publishers the atlas only links to by counting them in the registry
 * (src/lib/linkOnly.ts): `node web/scripts/about-sources.test.mjs`. The words of the tab and their agreement with the Method tab are pinned in
 * pipeline/tests/test_market_now_texts.py.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { LINK_ONLY_MARK, isLinkOnly, linkOnlyClause } from '../src/lib/linkOnly.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const registry = JSON.parse(fs.readFileSync(path.join(here, '../../data/sources.json'), 'utf8'));

test('the publishers the atlas only links to are the entries whose use says that no value is stored or shown', () => {
  assert.equal(LINK_ONLY_MARK, 'no value is stored or shown');
  assert.equal(isLinkOnly({ use: 'Links only: no value is stored or shown' }), true);
  assert.equal(isLinkOnly({ use: 'Mine and smelter production' }), false);
  assert.equal(isLinkOnly({}), false);
  // the real registry: read as the table of DATA_SOURCES.md reads it (pipeline/common/sources_table.py)
  const linked = registry.filter(isLinkOnly).map((s) => s.id);
  assert.ok(linked.length > 0);
  for (const id of linked) assert.ok(/no value is stored or shown/.test(registry.find((s) => s.id === id).use));
  assert.ok(!registry.filter((s) => !linked.includes(s.id)).some((s) => /no value is stored or shown/.test(s.use ?? '')));
});

test('the clause that follows "lists every source with its licence": the number is the registry\'s, and nothing is printed when there is none', () => {
  assert.equal(linkOnlyClause(0), '');
  assert.equal(linkOnlyClause(-1), '');
  assert.equal(linkOnlyClause(1), ', and also one publisher the atlas only links to, of which it shows no value');
  assert.equal(linkOnlyClause(2), ', and also two publishers the atlas only links to, of which it shows no value');
  assert.equal(linkOnlyClause(9), ', and also 9 publishers the atlas only links to, of which it shows no value');
  const n = registry.filter(isLinkOnly).length;
  assert.ok(linkOnlyClause(n).includes(['no', 'one', 'two', 'three', 'four', 'five', 'six'][n] ?? String(n)));
});
