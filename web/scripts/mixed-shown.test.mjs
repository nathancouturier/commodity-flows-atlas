/** The line "Plus X by sea and overland" of the lane panel is printed from the size the year note uses, 0.005 Mt (GV6B.5). */
import assert from 'node:assert/strict';
import { MIXED_MIN_MT, mixedShown } from '../src/lib/mixedShown.ts';

assert.equal(MIXED_MIN_MT, 0.005);
assert.equal(mixedShown(0.24, 'Mt'), true);
assert.equal(mixedShown(0.005, 'Mt'), true, 'the threshold itself');
assert.equal(mixedShown(0.00102, 'Mt'), false, 'lead metal, 1 kt');
assert.equal(mixedShown(0, 'Mt'), false);
assert.equal(mixedShown(5.71, 'kt'), true, 'cobalt, 5.71 kt, is above 0.005 Mt');
assert.equal(mixedShown(0.799, 'kt'), false, 'lithium, 0.8 kt, is under it: a file in kt is read in kt');
assert.equal(mixedShown(1.87, 'kt'), false);
console.log('mixed shown: all checks passed');
