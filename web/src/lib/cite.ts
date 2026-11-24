/**
 * "Copy link" and "Copy citation" of the detail panel. The citation is one line of plain text: the title of the page,
 * the atlas, the sources of the page with their years, the address and the date of access. The sources are read from
 * the page itself: every source line, key figure, price figure and banner figure carries its source ids and years (data-src,
 * data-srcs), so a citation cannot name a source the page does not show. A folded block is not rendered: its sources are not
 * cited, since the reader did not see its figures.
 */
import { sourceLabel } from './data';
import { selection } from './store';
import { yearsOf } from './years';
import { detailTitle } from './view';

const ACCESS = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });

/** A source the page names only as a pointer to its own links ("see the page linked on each asset") says nothing as a citation. */
const POINTER = /see the page linked/i;

/**
 * The source lines written by hand (an event, an asset): "Source: eia.gov ↗ · Wikipedia, Russian invasion of Ukraine ↗". Each
 * link is kept with its address, so that the article the page rests on is named, without the lead word or the arrow glyph.
 */
function handWrittenSources(panel: Element): string[] {
  // one entry per source and address: a page that names the same article on two lines (the limits and the foot of a port page) cites it once
  const out: { base: string; read?: string }[] = [];
  for (const line of panel.querySelectorAll('.src-line:not([data-src]):not([data-srcs])')) {
    const clean = (t: string | null) => (t ?? '').replace(/↗/g, '').replace(/\s+/g, ' ').trim();
    const text = clean(line.textContent);
    // other lines of this class are notes, not sources
    if (!/^Sources?:/i.test(text)) continue;
    const links = [...line.querySelectorAll('a')].map((a) => ({ text: clean(a.textContent), href: a.href }));
    for (const seg of text.replace(/^Sources?:\s*/i, '').split(' · ')) {
      // a sentence that follows a source on its line is a remark, not a source; the citation adds its own full stop
      const t = seg.trim().replace(/^(read [A-Za-z]+ \d{4})\..*$/i, '$1').replace(/\.+$/, '');
      if (!t) continue;
      const l = links.find((x) => x.text === t);
      // "read November 2026" belongs to the source before it
      if (/^read /i.test(t) && out.length) out[out.length - 1].read ??= t;
      else {
        const base = l?.href ? `${t} (${l.href})` : t;
        if (!out.some((o) => o.base === base)) out.push({ base });
      }
    }
  }
  return out.map((o) => (o.read ? `${o.base}, ${o.read}` : o.base));
}

/** Source ids of the page with their years, in the order the page shows them. */
function pageSources(panel: Element): { label: string; years: string[] }[] {
  const by = new Map<string, Set<string>>();
  const add = (label: string, y?: string | number | null) => {
    if (POINTER.test(label)) return;
    const set = by.get(label) ?? new Set<string>();
    for (const t of y == null ? [] : yearsOf(String(y))) set.add(t);
    by.set(label, set);
  };
  for (const el of panel.querySelectorAll<HTMLElement>('[data-src], [data-srcs]')) {
    if (el.dataset.srcs) {
      try {
        for (const [s, ys] of JSON.parse(el.dataset.srcs) as [string, string[]][]) {
          if (!ys.length) add(sourceLabel(s));
          for (const y of ys) add(sourceLabel(s), y);
        }
      } catch {
        // a malformed attribute is left out, the rest of the page still gives its sources
      }
    } else if (el.dataset.src) add(sourceLabel(el.dataset.src), el.dataset.y);
  }
  // what the page's own text cites comes first (an event's articles: the fact being cited), then the data behind its charts and tables
  const own = [...new Set(handWrittenSources(panel))].map((label) => ({ label, years: [] as string[] }));
  return [...own, ...[...by].map(([label, ys]) => ({ label, years: [...ys].sort() }))];
}

/** The atlas's own work a page of this kind rests on, which no source line of the page names. */
const OWN_WORK: Record<string, string> = { lane: 'Commodity Flows Atlas routing of the pair (sea route computed by the Atlas)' };

/** The citation of the page open in `panel` (the detail panel), at address `url`. */
export function citationOf(panel: Element, url = location.href, now = new Date()): string {
  const title = (detailTitle.peek() ?? document.title.replace(/ · [^·]*$/, '')).replace(/\s+/g, ' ').trim();
  const kind = selection.peek()?.kind;
  const own = kind && OWN_WORK[kind] ? [{ label: OWN_WORK[kind], years: [] as string[] }] : [];
  const sources = [...pageSources(panel), ...own].map((s) => (s.years.length ? `${s.label} ${s.years.join(', ')}` : s.label));
  return [`${title}. Commodity Flows Atlas.`, sources.length ? `Sources: ${sources.join('; ')}.` : '', `${url}`, `Accessed ${ACCESS.format(now)}.`].filter(Boolean).join(' ');
}

/** Put text on the clipboard; true when it worked. */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // no clipboard permission (an insecure page, an embedded frame): the old way, through a selection
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand('copy');
    } catch {
      ok = false;
    }
    ta.remove();
    return ok;
  }
}
