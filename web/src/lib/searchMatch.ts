/**
 * Matching of the search field: no dependency, so that scripts/search-match.test.mjs can run it as it is.
 * Case and accents are ignored; a word may be typed in part; an exact code or name comes first; a missing, added,
 * wrong or swapped letter is tolerated (one in a word of 4 or 5 letters, two from 6).
 */

/** Lower case, no accents, letters and digits only, one space between words: "Côte d'Ivoire" -> "cote d ivoire". */
export function norm(s: string): string {
  return s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/ß/g, 'ss')
    .replace(/[øØ]/g, 'o')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

export const tokens = (q: string): string[] => norm(q).split(' ').filter(Boolean);

/** What an item is found by. */
export interface Searchable {
  /** names (the first is the one shown), normalised */
  n: string[];
  /** codes: an exact one is the best match ("td3c", "jpn", "c5") */
  c: string[];
  /** secondary text (operator, country, route ends): a weaker match */
  x: string[];
}

export function prepare(names: string[], codes: string[] = [], extra: string[] = []): Searchable {
  const uniq = (l: string[]) => [...new Set(l.map(norm).filter(Boolean))];
  return { n: uniq(names), c: uniq(codes), x: uniq(extra) };
}

/** Greatest edit distance tolerated for a typed word of this length. */
export const tolerance = (len: number): number => (len >= 6 ? 2 : len >= 4 ? 1 : 0);

/** Optimal string alignment distance (insert, delete, replace, swap two neighbours), at most `max`+1. */
export function distance(a: string, b: string, max = 2): number {
  if (a === b) return 0;
  if (Math.abs(a.length - b.length) > max) return max + 1;
  const m = Array.from({ length: a.length + 1 }, (_, i) => [i, ...new Array<number>(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j++) m[0][j] = j;
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++) {
      m[i][j] = Math.min(m[i - 1][j] + 1, m[i][j - 1] + 1, m[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) m[i][j] = Math.min(m[i][j], m[i - 2][j - 2] + 1);
    }
  return Math.min(m[a.length][b.length], max + 1);
}

/** How well one typed word matches a list of normalised phrases: 0 (not at all) to 100 (the phrase or a word of it, exactly). */
function wordScore(t: string, phrases: string[], exact: number, prefix: number, inside: number, fuzzy: number): number {
  let best = 0;
  for (const p of phrases) {
    if (p === t) return exact;
    for (const w of p.split(' ')) {
      if (w === t) best = Math.max(best, exact - 20);
      else if (w.startsWith(t)) best = Math.max(best, prefix);
      else if (t.length >= 3 && w.includes(t)) best = Math.max(best, inside);
      else if (t.length >= 4 && fuzzy > best) {
        const tol = tolerance(t.length);
        // the whole word, or its beginning when the typed word is shorter ("singapor" for "singapore")
        const head = t.length >= 5 ? distance(t, w.slice(0, t.length), 1) : tol + 1;
        const d = Math.min(distance(t, w, tol), head <= 1 ? head : tol + 1);
        if (d <= tol) best = Math.max(best, fuzzy - 6 * d);
      }
    }
  }
  return best;
}

/** Score of one typed word against an item: codes, then names, then the secondary text. */
function tokenScore(t: string, d: Searchable): number {
  let best = 0;
  for (const c of d.c) {
    if (c === t) return 100;
    if (t.length >= 2 && c.startsWith(t)) best = Math.max(best, 55);
  }
  best = Math.max(best, wordScore(t, d.n, 95, 70, 45, 42));
  if (best < 60) best = Math.max(best, wordScore(t, d.x, 35, 30, 20, 10));
  return best;
}

/**
 * Score of a query (its words, from `tokens`) against an item: 0 when a word matches nothing, otherwise the mean of the
 * words' scores, plus a bonus for the whole query being the name, or the beginning of it. Every word has to match.
 */
export function score(q: string[], d: Searchable): number {
  if (!q.length) return 1;
  let sum = 0;
  for (const t of q) {
    const s = tokenScore(t, d);
    if (!s) return 0;
    sum += s;
  }
  const whole = q.join(' ');
  let bonus = 0;
  if (d.n.includes(whole) || d.c.includes(whole)) bonus = 60;
  else if (q.length > 1 && d.n.some((n) => n.startsWith(whole))) bonus = 20;
  else if (d.n.some((n) => n.startsWith(whole))) bonus = 12;
  return sum / q.length + bonus;
}
