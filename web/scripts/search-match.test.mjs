/**
 * Tests of the search field's matching (src/lib/searchMatch.ts): `node web/scripts/search-match.test.mjs`.
 * The module has no import, so Node runs the TypeScript file as it is.
 */
import assert from 'node:assert/strict';
import { distance, norm, prepare, score, tokens } from '../src/lib/searchMatch.ts';

const S = (q, names, codes = [], extra = []) => score(tokens(q), prepare(names, codes, extra));

// normalisation
assert.equal(norm("Côte d'Ivoire"), 'cote d ivoire');
assert.equal(norm('  Tubarao – Qingdao '), 'tubarao qingdao');
assert.equal(norm('TC2_37'), 'tc2 37');
assert.equal(norm('Curaçao'), 'curacao');

// edit distance: insertion, deletion, replacement, swap
assert.equal(distance('hormuz', 'hormuz'), 0);
assert.equal(distance('hormz', 'hormuz'), 1);
assert.equal(distance('hormoz', 'hormuz'), 1);
assert.equal(distance('hrmuoz', 'hormuz', 2), 2);
assert.equal(distance('abcdef', 'uvwxyz', 2), 3);
assert.equal(distance('singapoer', 'singapore'), 1);

// exact code beats everything, case and accents ignored
const td3c = prepare(['Middle East Gulf – China'], ['TD3C']);
assert.ok(score(tokens('TD3C'), td3c) >= 100);
assert.ok(score(tokens('td3c'), td3c) > score(tokens('middle'), td3c));
assert.ok(S('c5', ['West Australia – Qingdao'], ['C5']) > S('c5', ['Strait of Hormuz'], ['hormuz'], ['c5 something']));

// words may be typed in part, in any order, accents or not
assert.ok(S('hor', ['Strait of Hormuz'], ['hormuz']) > 0);
assert.ok(S('hormuz strait', ['Strait of Hormuz']) > 0);
assert.ok(S('cote', ["Côte d'Ivoire"]) > 0);
assert.ok(S('curacao', ['Curaçao']) > 0);
assert.ok(S('zürich', ['Zurich']) > 0);

// a wrong, missing or swapped letter is tolerated from four letters on
assert.ok(S('hormz', ['Strait of Hormuz']) > 0);
assert.ok(S('hormoz', ['Strait of Hormuz']) > 0);
assert.ok(S('singapor', ['Singapore Strait']) > 0);
assert.ok(S('jurng', ['Jurong']) > 0);
assert.ok(S('braizl', ['Brazil']) > 0);
assert.ok(S('jpn', ['Japan'], ['JPN']) >= 100);
assert.equal(S('jpx', ['Japan'], ['JPN']), 0, 'short words are not fuzzy');
assert.equal(S('xyzzy', ['Strait of Hormuz']), 0);

// a word that is far from every word of the item matches nothing (no fuzzy match through the cap of the prefix test)
assert.equal(S('hormuz', ['Afghanistan'], ['AFG', 'AF'], ['Southern Asia']), 0);
assert.equal(S('abadan', ['Afghanistan'], ['AFG', 'AF'], ['Southern Asia']), 0);

// the secondary text tolerates one wrong letter, not two ("hedland" is not "zealand")
assert.equal(S('hedland', ['Tauranga'], [], ['New Zealand']), 0);
assert.ok(S('zealnd', ['Tauranga'], [], ['New Zealand']) > 0);

// every word has to match; a word may match the secondary text
assert.equal(S('japan crude', ['Japan']), 0);
assert.ok(S('abadan refinery', ['Abadan'], [], ['refinery', 'iran']) > 0);
assert.ok(S('iran', ['Abadan'], [], ['iran']) > 0);

// an exact name or code is ahead of a longer name that merely contains it
assert.ok(S('oman', ['Oman']) > S('oman', ['Gulf of Oman']));
assert.ok(S('india', ['India']) > S('india', ['British Indian Ocean Territory'], [], ['india']));
assert.ok(S('port hedland', ['Port Hedland']) > S('port hedland', ['Port of Hedland Pilot']));
// the name beats the secondary text
assert.ok(S('japan', ['Japan']) > S('japan', ['Strait of Korea'], [], ['japan']));

console.log('search-match: all checks passed');
