/**
 * Tests of the address of the "Report an error" form (src/lib/report.ts): `node web/scripts/report.test.mjs`.
 * The module has no import, so Node runs the TypeScript file as it is. No `fetch` exists in the test: a call would throw.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { REPORT_FIELDS, REPORT_MAX_TITLE, REPORT_MAX_URL, reportObject, reportTitle, reportUrl, reportVersion } from '../src/lib/report.ts';

globalThis.fetch = () => {
  throw new Error('the address is built without a request');
};

const REPO = 'https://github.com/example-owner/example-repo';
const SITE = 'https://example-owner.github.io/example-repo/';
const RELEASE = { number: '7', date: '2026-11-25' };
const base = (o) => ({ repo: REPO, release: RELEASE, build: '3302ab6', href: `${SITE}`, selection: null, title: '', ...o });
const query = (url) => {
  const u = new URL(url);
  return { origin: u.origin + u.pathname, p: Object.fromEntries(u.searchParams) };
};
const FORBIDDEN = /[?&](labels|assignees|projects|milestone)=/;

// a commodity page
{
  const href = `${SITE}#c=tin&sel=commodity%3Atin`;
  const url = reportUrl(base({ href, selection: { kind: 'commodity', id: 'tin' }, title: 'Tin' }));
  const { origin, p } = query(url);
  assert.equal(origin, `${REPO}/issues/new`);
  assert.equal(p.template, 'report-an-error.yml');
  assert.equal(p.title, 'Error: Tin');
  assert.equal(p.page, href, 'a short address is kept whole, and decodes to the input');
  assert.equal(p.object, 'commodity:tin (Tin)');
  assert.equal(p.version, 'Release 7, 25 November 2026, build 3302ab6');
  assert.ok(!FORBIDDEN.test(url));
  assert.ok(!/labels/.test(url));
  assert.ok(url.length < 500);
}

// a lane: its id holds colons; the address encodes them again and gives them back
{
  const id = 'AUS:CHN:iron-ore:capesize';
  const href = `${SITE}#c=iron-ore&sel=lane%3A${encodeURIComponent(id)}`;
  const { p } = query(reportUrl(base({ href, selection: { kind: 'lane', id }, title: 'Australia to China' })));
  assert.equal(p.object, `lane:${id} (Australia to China)`);
  assert.equal(p.page, href);
}

// a country, a passage and an infrastructure asset (its layer is part of the object)
assert.equal(query(reportUrl(base({ selection: { kind: 'country', id: 'CHN' }, title: 'China' }))).p.object, 'country:CHN (China)');
assert.equal(query(reportUrl(base({ selection: { kind: 'chokepoint', id: 'hormuz' }, title: 'Strait of Hormuz' }))).p.object, 'chokepoint:hormuz (Strait of Hormuz)');
assert.equal(
  query(reportUrl(base({ selection: { kind: 'infra', id: 'ras-tanura', layer: 'port' }, title: 'Ras Tanura' }))).p.object,
  'infra:ras-tanura:port (Ras Tanura)',
);

// nothing selected: no object, a title with the site's name; the window of the About
{
  const { p } = query(reportUrl(base({})));
  assert.equal(p.title, 'Error: Commodity Flows Atlas');
  assert.equal(p.object, undefined);
  assert.equal(p.page, SITE);
  const about = query(reportUrl(base({ title: 'About window' }))).p;
  assert.equal(about.title, 'Error: About window');
  assert.equal(about.object, undefined);
}

// the version says only what is known
assert.equal(reportVersion(RELEASE, ''), 'Release 7, 25 November 2026');
assert.equal(reportVersion({ number: '', date: '' }, 'abc1234'), 'build abc1234');
assert.equal(reportVersion({ number: '', date: '' }, ''), '');
assert.equal(query(reportUrl(base({ release: { number: '', date: '' }, build: '' }))).p.version, undefined);

// a very long title is cut to 80 characters and says so; text with & # ? and a non-ASCII letter round-trips
{
  const long = 'A very long heading '.repeat(30);
  const t = reportTitle(long);
  assert.ok(Array.from(t).length <= REPORT_MAX_TITLE);
  assert.ok(t.endsWith('…') && t.startsWith('Error: A very long heading'));
  const { p } = query(reportUrl(base({ title: long, selection: { kind: 'commodity', id: 'tin' } })));
  assert.equal(p.title, t);
  assert.ok(p.object.length < 200);
  const odd = 'Côte d’Ivoire & co #1 ? 100%';
  assert.equal(query(reportUrl(base({ title: odd, selection: { kind: 'country', id: 'CIV' } }))).p.title, `Error: ${odd}`);
  assert.equal(reportTitle('  two\n  lines '), 'Error: two lines');
}

// the cap: the longest address the hash can write, a long heading and a wide character set never go over it
{
  const vessels = Array.from({ length: 20 }, (_, i) => `vessel-class-${i}`).join(',');
  const series = Array.from({ length: 6 }, (_, i) => `spread%3Abrent-wti-${i}`).join('%2C');
  const hash = `#f=metals&c=copper&m=exports&v=${vessels}&y=2019&sel=lane%3A${'x'.repeat(80)}&co=${'c'.repeat(60)}&rf=coal%3Ao%3AAUS-CHN&p=${series}&pr=2020-01-01_2024-12-31&pd=2024-06-30&pf=ir`;
  const input = base({ href: `${SITE}${hash}`, selection: { kind: 'lane', id: 'x'.repeat(80) }, title: 'é'.repeat(300) });
  const url = reportUrl(input);
  assert.ok(url.length <= REPORT_MAX_URL, `${url.length} characters`);
  assert.ok(!FORBIDDEN.test(url));
  const { p } = query(url);
  assert.ok(p.page.includes('sel=lane%3Ax'), 'the keys that define the page stay');
  assert.ok(!p.page.includes('&v=') && !p.page.includes('&p='), 'the view-only keys go first');
  // an address that cannot be kept even in part: still within the cap, still a valid address
  const huge = reportUrl(base({ href: `${SITE}#sel=${'%C3%A9'.repeat(3000)}`, selection: { kind: 'commodity', id: 'tin' }, title: '€'.repeat(500) }));
  assert.ok(huge.length <= REPORT_MAX_URL, `${huge.length} characters`);
  assert.doesNotThrow(() => new URL(huge));
  // an emoji is never cut in two
  const emoji = reportUrl(base({ href: `${SITE}#sel=${'😀'.repeat(2500)}` }));
  assert.ok(emoji.length <= REPORT_MAX_URL);
  assert.doesNotThrow(() => decodeURIComponent(emoji));
}

// an object longer than its cap is cut; a short address is not touched
assert.equal(reportObject({ kind: 'commodity', id: 'tin' }, 'x'.repeat(500)), `commodity:tin (${'x'.repeat(120)})`);
assert.equal(reportObject(null, 'Tin'), '');

// the address never names a label, whatever the input
for (const title of ['labels=bug', '&labels=data-update', 'data-update']) {
  assert.ok(!FORBIDDEN.test(reportUrl(base({ title, selection: { kind: 'commodity', id: 'tin' } }))));
}
assert.ok(!/data-update/.test(reportUrl(base({ selection: { kind: 'commodity', id: 'tin' }, title: 'Tin' }))));

// the field names are the ids of the form, and the form's fields are the ones the address fills
{
  const here = path.dirname(fileURLToPath(import.meta.url));
  const form = fs.readFileSync(path.join(here, '..', '..', '.github', 'ISSUE_TEMPLATE', 'report-an-error.yml'), 'utf8');
  const ids = [...form.matchAll(/^\s*id:\s*(\S+)/gm)].map((m) => m[1]);
  for (const f of REPORT_FIELDS) assert.ok(ids.includes(f), `the form has no field "${f}"`);
  assert.ok(!/^\s*labels\s*:/m.test(form), 'the form sets no label');
  const src = fs.readFileSync(path.join(here, '..', 'src', 'lib', 'report.ts'), 'utf8');
  assert.ok(!/^import\s/m.test(src), 'report.ts has no import, so that Node can run it');
}

console.log('report: ok');
