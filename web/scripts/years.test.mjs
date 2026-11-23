/** Tests of the years a citation names for a source line (src/lib/years.ts): `node web/scripts/years.test.mjs`. */
import assert from 'node:assert/strict';
import { yearsOf } from '../src/lib/years.ts';

assert.deepEqual(yearsOf('2024'), ['2024']);
assert.deepEqual(yearsOf('2005–2024'), ['2005–2024'], 'a period with an en dash is one period');
assert.deepEqual(yearsOf('2005-2024'), ['2005–2024']);
assert.deepEqual(yearsOf('2023 and 2024'), ['2023', '2024']);
assert.deepEqual(yearsOf('2024/25'), ['2024/25']);
assert.deepEqual(yearsOf('2Q26'), ['2Q26']);
assert.deepEqual(yearsOf('data to 2026-11-15'), ['2026-11-15'], 'a date is not a year and a month');
assert.deepEqual(yearsOf('data to 2026-11'), ['2026-11']);
assert.deepEqual(yearsOf('last revised'), ['last revised']);
assert.deepEqual(yearsOf(''), []);
console.log('years: all checks passed');
