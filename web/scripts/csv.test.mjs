/** Tests of how a CSV cell is written (src/lib/csvCore.ts): `node web/scripts/csv.test.mjs`. */
import assert from 'node:assert/strict';
import { LONG_LICENCE, csvCell, numberText, onceColumn, toCsv } from '../src/lib/csvCore.ts';

// no floating-point noise: the values the review found in the files
assert.equal(csvCell(153.81379999997444), '153.8138');
assert.equal(csvCell(0.632000000000005), '0.632');
assert.equal(csvCell(15593.699999999997), '15593.7');
assert.equal(csvCell(1.0499999999999972), '1.05');
assert.equal(csvCell(6.800000000000011), '6.8');
assert.equal(csvCell(2.260000000000005), '2.26');
assert.equal(csvCell(3.1899999999999977), '3.19');
assert.equal(csvCell(0.30000000000000004), '0.3');
// a figure of the data files is written as it stands
assert.equal(csvCell(26.607), '26.607');
assert.equal(csvCell(553876257000), '553876257000');
assert.equal(csvCell(-0.5), '-0.5');
assert.equal(csvCell(0.0659), '0.0659');
assert.equal(numberText(1e-7), '1e-7');
assert.equal(csvCell(null), '');
// text with a comma, a quote or a line break is quoted
assert.equal(csvCell('Rapeseed, canola'), '"Rapeseed, canola"');
assert.equal(csvCell('say "x"'), '"say ""x"""');
assert.equal(toCsv(['a', 'b'], [[1, 'x,y']]), 'a,b\r\n1,"x,y"\r\n');

// a long cell is written in full once, then by its short form
const lic = onceColumn(LONG_LICENCE, 'full text');
const long = 'IMF terms of use for statistical data: ' + 'x'.repeat(150);
assert.equal(lic(long, 'IMF terms'), long);
assert.equal(lic(long, 'IMF terms'), 'IMF terms (full text on the first row of this source)');
assert.equal(lic('CC BY 4.0'), 'CC BY 4.0');
assert.equal(lic('CC BY 4.0'), 'CC BY 4.0');
// no short form: the full text each time
const lic2 = onceColumn(10, 'full text');
assert.equal(lic2('a'.repeat(30)), 'a'.repeat(30));
assert.equal(lic2('a'.repeat(30)), 'a'.repeat(30));
// a weekly series of 4110 rows does not repeat the long text
const rows = Array.from({ length: 4110 }, () => lic(long, 'IMF terms'));
assert.ok(rows.join('').length < 4110 * 80);
console.log('csv: all checks passed');
