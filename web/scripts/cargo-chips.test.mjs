/**
 * Labels of the cargo chips of lanes and generated routes (src/lib/cargoChips.ts; package FNCE, review of FNCC): a chip that stands for one
 * product of a commodity page says the product, and still opens the page: `node web/scripts/cargo-chips.test.mjs`.
 * The tables are read from src/lib/freight.ts and the lanes and routes from data/, so that the test follows both.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { groupChipLabels, routeChipLabels } from '../src/lib/cargoChips.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const freight = fs.readFileSync(path.join(here, '../src/lib/freight.ts'), 'utf8');
/** The object literal of `export const <name>...= {` ... `};` of freight.ts. */
function table(name) {
  const at = freight.indexOf(`export const ${name}`);
  const from = freight.indexOf('= {', at) + 2;
  const to = freight.indexOf('\n};', from) + 2;
  return new Function(`return ${freight.slice(from, to)}`)();
}
const LANE_GROUPS = table('LANE_GROUPS');
const GROUP_LABEL = table('GROUP_LABEL');
const data = (rel) => JSON.parse(fs.readFileSync(path.join(here, '../../data', rel), 'utf8'));

test('a product of a page that is not its main group is named on the chip', () => {
  assert.deepEqual(groupChipLabels('urea', 'ammonia', LANE_GROUPS, GROUP_LABEL), { urea: 'Ammonia' });
  assert.deepEqual(groupChipLabels('urea', 'uan', LANE_GROUPS, GROUP_LABEL), { urea: 'UAN solution' });
  assert.deepEqual(groupChipLabels('phosphate', 'phosphoric-acid', LANE_GROUPS, GROUP_LABEL), { phosphate: 'Phosphoric acid' });
  assert.deepEqual(groupChipLabels('met-coal', 'coke', LANE_GROUPS, GROUP_LABEL), { 'met-coal': 'Coke and semi-coke' });
});

test('the main group of a page keeps the page name, and so does a cargo that is not one group', () => {
  assert.equal(groupChipLabels('urea', 'urea', LANE_GROUPS, GROUP_LABEL), undefined);
  assert.equal(groupChipLabels('thermal-coal', 'coal', LANE_GROUPS, GROUP_LABEL), undefined);
  assert.equal(groupChipLabels('met-coal', 'coal', LANE_GROUPS, GROUP_LABEL), undefined);
  assert.equal(groupChipLabels('urea', undefined, LANE_GROUPS, GROUP_LABEL), undefined);
  assert.equal(groupChipLabels('urea', 'no-such-group', LANE_GROUPS, GROUP_LABEL), undefined);
  assert.equal(routeChipLabels(undefined, LANE_GROUPS, GROUP_LABEL), undefined);
  assert.equal(routeChipLabels([], LANE_GROUPS, GROUP_LABEL), undefined);
  // two groups in one corridor, or an entry that names none (a hand-written route): the page's name
  assert.equal(routeChipLabels([{ k: 'urea', g: 'ammonia' }, { k: 'urea', g: 'uan' }], LANE_GROUPS, GROUP_LABEL), undefined);
  assert.equal(routeChipLabels([{ k: 'urea', g: 'ammonia' }, { k: 'urea' }], LANE_GROUPS, GROUP_LABEL), undefined);
  assert.equal(routeChipLabels([{ k: 'urea', g: 'ammonia' }, { k: 'phosphate', g: 'ammonia' }], LANE_GROUPS, GROUP_LABEL), undefined);
});

test('every lane of the lane files: the label is the group name exactly when the group is not the first of its page', () => {
  const dir = path.join(here, '../../data/freight/lanes');
  let labelled = 0;
  for (const f of fs.readdirSync(dir).filter((x) => x.endsWith('.json'))) {
    const file = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
    for (const l of file.lanes) {
      const got = groupChipLabels(l.k, l.p, LANE_GROUPS, GROUP_LABEL);
      if (LANE_GROUPS[l.k]?.[0] === l.p) assert.equal(got, undefined, l.id);
      else if (GROUP_LABEL[l.p]) {
        assert.deepEqual(got, { [l.k]: GROUP_LABEL[l.p] }, l.id);
        labelled++;
      }
    }
  }
  assert.ok(labelled > 50, `${labelled} lanes are labelled`);
});

test('the generated routes of ammonia, coke and the other products: the label, and the page it opens is on the route', () => {
  const routes = data('freight/routes.json');
  const byGroup = {};
  for (const r of routes) {
    const got = routeChipLabels(r.corridor, LANE_GROUPS, GROUP_LABEL);
    if (got) {
      assert.deepEqual(Object.keys(got), r.cargoes, r.id);  // the chip that is labelled is the route's own cargo chip
      byGroup[r.corridor[0].g] = (byGroup[r.corridor[0].g] ?? 0) + 1;
    }
    if (r.corridor?.every((c) => c.g && LANE_GROUPS[c.k]?.[0] === c.g)) assert.equal(got, undefined, r.id);
  }
  for (const g of ['ammonia', 'coke']) assert.ok(byGroup[g] >= 1, `a generated route of ${g} is labelled: ${JSON.stringify(byGroup)}`);
});

test('the chips that open a page keep their click: CommodityChips opens the page whatever the label', () => {
  const shared = fs.readFileSync(path.join(here, '../src/components/views/shared.tsx'), 'utf8');
  assert.match(shared, /onClick=\{\(\) => openCommodity\(k\)\}/);
  for (const view of ['LaneView', 'RouteView']) {
    const src = fs.readFileSync(path.join(here, `../src/components/views/${view}.tsx`), 'utf8');
    assert.match(src, /<CommodityChips ids=\{[^}]*\} labels=\{(laneChipLabels|routeCargoLabels)\(/, view);
  }
});
