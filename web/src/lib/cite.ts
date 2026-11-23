/**
 * "Copy link" and "Copy citation" of the detail panel. The citation is one line of plain text: the title of the page,
 * the atlas, the sources of the page with their years, the address and the date of access. The sources are read from
 * the page itself: every source line carries its source ids and years (data-src, data-srcs), so a citation cannot name
 * a source the page does not show.
 */
import { sourceLabel } from './data';
import { detailTitle } from './view';

const ACCESS = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });

/** Source ids of the page with their years, in the order the page shows them. */
function pageSources(panel: Element): { label: string; years: string[] }[] {
  const by = new Map<string, Set<string>>();
  const add = (label: string, y?: string | number | null) => {
    const set = by.get(label) ?? new Set<string>();
    // a year, a season ("2024/25") or a quarter ("2Q26"): a line that gives "2023 and 2024" names two years
    const text = y == null ? '' : String(y);
    for (const t of text.match(/\d{4}(?:[/-]\d{2,4})?|\d[QH]\d{2}/g) ?? (text.trim() ? [text.trim()] : [])) set.add(t);
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
  if (by.size) return [...by].map(([label, ys]) => ({ label, years: [...ys].sort() }));
  // a page whose source lines are written by hand (an asset, an event): the text of the line, without its lead word
  const lines = [...panel.querySelectorAll('.src-line')].map((e) => (e.textContent ?? '').replace(/^\s*Sources?:\s*/i, '').replace(/\s+/g, ' ').trim());
  return [...new Set(lines.filter(Boolean))].map((label) => ({ label: label.length > 160 ? label.slice(0, 157) + '…' : label, years: [] }));
}

/** The citation of the page open in `panel` (the detail panel), at address `url`. */
export function citationOf(panel: Element, url = location.href, now = new Date()): string {
  const title = (detailTitle.peek() ?? document.title.replace(/ · [^·]*$/, '')).replace(/\s+/g, ' ').trim();
  const sources = pageSources(panel).map((s) => (s.years.length ? `${s.label} ${s.years.join(', ')}` : s.label));
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
