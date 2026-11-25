/** A mixed flow says its split by mode where a source measures it for the year, and "split not known" otherwise (Main flows rows, tooltips and CSV). */
import assert from 'node:assert/strict';
import test from 'node:test';
import { mixedModeText } from '../src/lib/flowMode.ts';

test('a flow with a share by sea says it, with its year', () => {
  assert.equal(mixedModeText({ seaShare: 0.72, y: 2024 }), 'sea and overland, 72% by sea in 2024');
});

test('a flow without the field keeps "split not known"', () => {
  assert.equal(mixedModeText({ y: 2024 }), 'sea and overland, split not known');
});

test('a share of 0 is a known share, not a missing one', () => {
  assert.equal(mixedModeText({ seaShare: 0, y: 2024 }), 'sea and overland, 0% by sea in 2024');
});

test('the CSV and the row tooltip print the text of the function, not a text of their own', async () => {
  const { readFileSync } = await import('node:fs');
  for (const file of ['../src/lib/blockCsv.ts', '../src/components/views/CommodityView.tsx']) {
    const src = readFileSync(new URL(file, import.meta.url), 'utf8');
    assert.ok(src.includes('mixedModeText('), file);
    assert.ok(!src.includes("' · by sea and overland, split not known") && !src.includes("'sea and overland, split not known'"), `${file} words the split on its own`);
  }
});
