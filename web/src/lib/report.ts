/**
 * The address of the "Report an error" form, filled in with the page the visitor is on.
 *
 * Pure and without import, so that Node runs the file as it is (web/scripts/report.test.mjs); the component passes the
 * values. The address sets no `labels`, `assignees` or `projects`: GitHub answers 404 to a visitor who may not set them.
 * Its length is capped, because GitHub refuses an address that is too long and gives no figure: 2,000 characters is an
 * Atlas assumption.
 */

/** The names of the form's fields that the address fills, as `.github/ISSUE_TEMPLATE/report-an-error.yml` names them (their `id`). */
export const REPORT_FIELDS = ['page', 'object', 'version'] as const;

export const REPORT_TEMPLATE = 'report-an-error.yml';
export const REPORT_MAX_URL = 2000;
export const REPORT_MAX_TITLE = 80;

export interface ReportInput {
  /** the repository's address, without a trailing slash */
  repo: string;
  /** number and date (YYYY-MM-DD) of the release; empty when unknown */
  release: { number: string; date: string };
  /** commit of the build; empty when unknown */
  build: string;
  /** the address of the page, as the browser shows it */
  href: string;
  /** the page's selection, null when nothing is selected (an infrastructure asset also has its layer) */
  selection: { kind: string; id: string; layer?: string } | null;
  /** the heading of the page */
  title: string;
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
/** The parts of the address that define the page, in the order the cap keeps them. */
const PAGE_KEYS = ['f', 'c', 'm', 'y', 'sel', 'co', 'rf'];

const clean = (s: string) => s.replace(/\s+/g, ' ').trim();
/** The first `n` characters (whole characters: a cut inside a surrogate pair would not encode). */
const cut = (s: string, n: number) => {
  const a = Array.from(s);
  return a.length <= n ? s : a.slice(0, n).join('');
};

/** "Error: Tin", at most 80 characters. */
export function reportTitle(page: string): string {
  const full = `Error: ${clean(page) || 'Commodity Flows Atlas'}`;
  const a = Array.from(full);
  return a.length <= REPORT_MAX_TITLE ? full : `${a.slice(0, REPORT_MAX_TITLE - 1).join('').trimEnd()}…`;
}

/** "commodity:tin (Tin)": the selection as the address writes it (`sel=`), then the heading in brackets. */
export function reportObject(selection: ReportInput['selection'], title: string): string {
  if (!selection) return '';
  const key = selection.kind === 'infra' && selection.layer ? `${selection.kind}:${selection.id}:${selection.layer}` : `${selection.kind}:${selection.id}`;
  const t = clean(title);
  return t ? `${key} (${cut(t, 120)})` : key;
}

/** "Release 7, 25 November 2026, build 3302ab6": what is known of the version running. */
export function reportVersion(release: ReportInput['release'], build: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(release.date);
  const parts: string[] = [];
  if (release.number) parts.push(m && MONTHS[Number(m[2]) - 1] ? `Release ${release.number}, ${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : `Release ${release.number}`);
  if (build) parts.push(`build ${build}`);
  return parts.join(', ');
}

/** The address of the page without what only describes the view (series of the price explorer, vessel filters). */
function essential(href: string): string {
  const i = href.indexOf('#');
  if (i < 0) return href;
  const params = href.slice(i + 1).split('&');
  const keep = PAGE_KEYS.flatMap((k) => params.filter((p) => p === k || p.startsWith(`${k}=`)));
  return keep.length ? `${href.slice(0, i)}#${keep.join('&')}` : href.slice(0, i);
}

export function reportUrl(i: ReportInput): string {
  const enc = encodeURIComponent;
  const make = (title: string, page: string, object: string, version: string) => {
    const field = (name: string, v: string) => (v ? `&${name}=${enc(v)}` : '');
    return `${i.repo}/issues/new?template=${REPORT_TEMPLATE}&title=${enc(title)}${field('page', page)}${field('object', object)}${field('version', version)}`;
  };
  const title = reportTitle(i.title);
  let page = i.href;
  let object = reportObject(i.selection, i.title);
  const version = reportVersion(i.release, i.build);
  const url = () => make(title, page, object, version);
  // the largest part of `value` that keeps the address within the cap
  const fit = (value: string, withPart: (part: string) => string) => {
    let lo = 0;
    let hi = Array.from(value).length;
    while (lo < hi) {
      const mid = Math.ceil((lo + hi) / 2);
      if (withPart(cut(value, mid)).length <= REPORT_MAX_URL) lo = mid;
      else hi = mid - 1;
    }
    return cut(value, lo);
  };
  if (url().length > REPORT_MAX_URL) page = essential(page);
  if (url().length > REPORT_MAX_URL) object = cut(object, 200);
  if (url().length > REPORT_MAX_URL) page = fit(page, (p) => make(title, p, object, version));
  if (url().length > REPORT_MAX_URL) object = fit(object, (o) => make(title, page, o, version));
  // what is left (title and version) is at most about a thousand characters once encoded: it never goes over the cap
  return url();
}
