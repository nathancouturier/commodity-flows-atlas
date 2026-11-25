/**
 * Tests of the rule that decides how a Main flows block names its sources (src/lib/flowSources.ts): one source, two sources, and the atlas's own
 * rows beside one source. `node web/scripts/flow-sources.test.mjs`
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import { hasSeveralSources, showsSourceTag } from '../src/lib/flowSources.ts';

const row = (s) => ({ s });
const tags = (flows, rows = flows) => rows.map((f) => showsSourceTag(f, flows, rows));

test('one source: no tag on any row, and the footer is the single-source line', () => {
  const flows = [row('baci'), row('baci'), row('baci')];
  assert.equal(hasSeveralSources(flows), false);
  assert.deepEqual(tags(flows), [false, false, false]);
});

test('two sources (the Metallurgical coal page): every row names its source', () => {
  const flows = [row('qld-coal-sales'), row('eia-coal'), row('qld-coal-sales')];
  assert.equal(hasSeveralSources(flows), true);
  assert.deepEqual(tags(flows), [true, true, true]);
});

test('the atlas and one source: the atlas rows say so, the others do not, and the footer is the single-source line', () => {
  const flows = [row('baci'), row('atlas'), row('baci')];
  assert.equal(hasSeveralSources(flows), false, 'the atlas is not a source of its own');
  assert.deepEqual(tags(flows), [false, true, false]);
});

test('the atlas first in the list: the source of the footer is the first row that is not the atlas', () => {
  const flows = [row('atlas'), row('baci')];
  assert.deepEqual(tags(flows), [true, false]);
});

test('only rows of the atlas: no tag (they are the footer\'s source)', () => {
  const flows = [row('atlas'), row('atlas')];
  assert.equal(hasSeveralSources(flows), false);
  assert.deepEqual(tags(flows), [false, false]);
});

test('the rows on screen are the first ten, the rule reads the whole list', () => {
  const flows = [row('baci'), row('baci'), row('eia-coal')];
  assert.deepEqual(tags(flows, flows.slice(0, 2)), [true, true], 'a second source further down the list still names the sources above');
});

test('the tag "all coal" is the Thermal coal page only', async () => {
  const { allCoalTag } = await import('../src/lib/flowSources.ts');
  assert.equal(allCoalTag('thermal-coal'), 'all coal');
  for (const id of ['met-coal', 'coal', 'lpg', 'copper']) assert.equal(allCoalTag(id), undefined, id);
});

test('an overland arc says "customs" only for a flow with a declared customs value', async () => {
  const { customsMark } = await import('../src/lib/flowSources.ts');
  assert.equal(customsMark({ usd: 1.2e9 }), ' (customs)');
  assert.equal(customsMark({ usd: 0 }), ' (customs)', 'a declared value of zero is still a customs flow');
  assert.equal(customsMark({}), '');
  assert.equal(customsMark({ usd: null }), '');
});
