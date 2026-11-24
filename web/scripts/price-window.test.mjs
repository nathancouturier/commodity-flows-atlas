/** The window of the price drawer across the switch to real prices (GV6C.6): kept when the loaded series covers it, opened afresh when not. */
import assert from 'node:assert/strict';
import { seriesCovers } from '../src/lib/priceWindow.ts';

const t = (iso) => Date.parse(`${iso}T00:00:00Z`) / 1000;
// the real twin of a monthly series: annual, 1960 to 2025
const real = [t('1960-01-01'), t('2025-01-01')];
assert.equal(seriesCovers({ min: t('2011-11-17'), max: t('2019-11-12') }, ...real), true, 'a window chosen by hand inside the annual series stays');
assert.equal(seriesCovers({ min: t('2005-01-01'), max: t('2025-01-01') }, ...real), true, 'the default window of the annual series stays');
assert.equal(seriesCovers({ min: t('2021-11-16'), max: t('2026-11-17') }, ...real), false, 'the last five years of the monthly series reach past the end of its annual twin');
assert.equal(seriesCovers({ min: t('1950-01-01'), max: t('1970-01-01') }, ...real), false, 'a window that starts before the series');
// back to the monthly series (1960 to 2026-10): the annual window is inside it
assert.equal(seriesCovers({ min: t('2005-01-01'), max: t('2025-01-01') }, t('1960-01-01'), t('2026-10-01')), true);
console.log('price window: all checks passed');
