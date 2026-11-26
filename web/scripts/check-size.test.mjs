/**
 * Tests of the size budgets of scripts/check-size.mjs, on folders built here: `node web/scripts/check-size.test.mjs`.
 * They cover the glyph files of the map's lettering (dist/glyphs), which are neither in assets/ nor in data/.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { BUDGET, measure } from './check-size.mjs';

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'check-size-test-'));
const dist = (name, files) => {
  const root = path.join(tmp, name);
  for (const [rel, size] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), Buffer.alloc(size, 97));
  }
  return root;
};

// the glyph budget exists and is the sum over dist/glyphs/**
assert.ok(BUDGET.glyphs > 0, 'the glyphs budget exists');
{
  const root = dist('ok', { 'assets/x.js': 1000, 'glyphs/a/0-255.pbf': 40000, 'glyphs/a/LICENSE.txt': 5000, 'glyphs/b/256-511.pbf': 123 });
  const { m, problems } = measure(root);
  assert.equal(m.glyphs, 45123, 'every file of dist/glyphs is summed, in every folder');
  assert.equal(m.otherJs, 1000);
  assert.deepEqual(problems, []);
}

// a missing folder is 0, and the build is still a build
{
  const { m, problems } = measure(dist('none', { 'assets/x.js': 10 }));
  assert.equal(m.glyphs, 0);
  assert.deepEqual(problems, []);
}

// over the budget: reported, with the largest file's name
{
  const root = dist('over', { 'assets/x.js': 10, 'glyphs/a/0-255.pbf': BUDGET.glyphs + 1000, 'glyphs/a/LICENSE.txt': 100 });
  const { problems } = measure(root);
  assert.equal(problems.length, 1, problems.join('; '));
  assert.match(problems[0], /^glyphs: /);
  assert.match(problems[0], /over its budget of/);
  assert.match(problems[0], /glyphs\/a\/0-255\.pbf/);
}

// exactly the budget is not over it
{
  const { problems } = measure(dist('edge', { 'assets/x.js': 10, 'glyphs/a/0-255.pbf': BUDGET.glyphs }));
  assert.deepEqual(problems, []);
}

fs.rmSync(tmp, { recursive: true, force: true });
console.log('check-size: ok');
