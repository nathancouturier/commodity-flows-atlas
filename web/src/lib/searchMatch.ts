/**
 * Matching of the search field: no dependency, so that scripts/search-match.test.mjs can run it as it is.
 * Case and accents are ignored; a word may be typed in part; an exact code or name comes first; a missing, added,
 * wrong or swapped letter is tolerated (one in a word of 4 to 6 letters, two from 7: fewer than a third of its letters),
 * when the first letter is right, the word holds no digit, and no item has the word whole or as the beginning of a word.
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
  /** the names of the cargoes or commodities the item is about (they are also in `x`): with the names and the codes, the only words that make a whole-word match a promotion */
  k: string[];
}

/** `cargo`: the cargo or commodity names of the item, in `extra` as well (a route's ports and regions are in `extra` only). */
export function prepare(names: string[], codes: string[] = [], extra: string[] = [], cargo: string[] = []): Searchable {
  const uniq = (l: string[]) => [...new Set(l.map(norm).filter(Boolean))];
  return { n: uniq(names), c: uniq(codes), x: uniq(extra), k: uniq(cargo) };
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

/**
 * How well a match is, from the weakest to the best; the group of results and the item inside it are ordered by it first,
 * then by score. A typo-tolerant or inside-a-word match (1) never outranks an exact or prefix one.
 *  4  the whole query is a name or a code of the item ("TD3C", "Panama Canal")
 *  3  every word is a word, or the beginning of a word, of a name or a code
 *  2  as 3, but a word is found only in the secondary text (operator, country, route ends)
 *  1  a word is found inside another word, or with a wrong letter
 */
export type Tier = 0 | 1 | 2 | 3 | 4;

/**
 * The order of the kinds of results when two groups match equally well (same tier): the first comes first. The only place
 * it is written. A commodity, a country, a chokepoint, a vessel class, a route or a company that is named by the query
 * comes before an asset, a port, an event or a price series that only holds the word.
 */
export const TIE_ORDER = ['commodity', 'country', 'chokepoint', 'vessel', 'route', 'company', 'infra', 'port', 'event', 'price'] as const;

interface Hit {
  s: number;
  lvl: number;
}

/** How well one typed word matches a list of normalised phrases: a score 0 (not at all) to 100 (the phrase), and its level (see Tier). */
function wordScore(t: string, phrases: string[], exact: number, prefix: number, inside: number, fuzzy: number, strong: number, typo: boolean): Hit {
  const best: Hit = { s: 0, lvl: 0 };
  const take = (s: number, lvl: number) => {
    if (s > best.s) best.s = s;
    if (lvl > best.lvl) best.lvl = lvl;
  };
  for (const p of phrases) {
    if (p === t) return { s: exact, lvl: strong };
    for (const w of p.split(' ')) {
      if (w === t) take(exact - 20, strong);
      else if (w.startsWith(t)) take(prefix, strong);
      // inside a word: only from four letters ("gas" is not in "Antofagasta")
      else if (t.length >= 4 && typo && w.includes(t)) take(inside, 1);
      else if (t.length >= 4 && typo && fuzzy > best.s && t[0] === w[0]) {
        const tol = tolerance(t.length);
        // the whole word, or its beginning when the typed word is shorter ("singapor" for "singapore")
        const head = t.length >= 5 ? distance(t, w.slice(0, t.length), 1) : tol + 1;
        const d = Math.min(distance(t, w, tol), head <= 1 ? head : tol + 1);
        // fewer edits than a third of the typed word, and the word it is mistaken for is not mostly changed ("cobalt" is not "coal" or "coast")
        if (d <= tol && d * 3 < t.length && d * 2 < w.length) take(fuzzy - 6 * d, 1);
      }
    }
  }
  return best;
}

/**
 * Score of one typed word against an item: codes, then names, then the secondary text. `typo`: a word found inside another
 * or with a wrong letter counts; never for a word with a digit ("2026" is not "2023").
 */
function tokenScore(t: string, d: Searchable, typo = true): Hit {
  typo = typo && !/[0-9]/.test(t);
  const best: Hit = { s: 0, lvl: 0 };
  const take = (h: Hit) => {
    if (h.s > best.s) best.s = h.s;
    if (h.lvl > best.lvl) best.lvl = h.lvl;
  };
  for (const c of d.c) {
    if (c === t) return { s: 100, lvl: 3 };
    if (t.length >= 2 && c.startsWith(t)) take({ s: 55, lvl: 3 });
  }
  take(wordScore(t, d.n, 95, 70, 45, 42, 3, typo));
  if (best.s < 60) take(wordScore(t, d.x, 35, 30, 20, 10, 2, typo));
  return best;
}

/**
 * The typed words that some item has whole or as the beginning of a word: for them a typo is not looked for ("iran" is
 * the name of Iran, so it does not also find Iraq). A company's name does not count: there are hundreds, and "coper" (the
 * beginning of Copersucar) must still find Copper.
 */
export function exactWords(q: string[], items: { d: Searchable; kind?: string }[]): Set<string> {
  const out = new Set<string>();
  for (const t of q) if (items.some((it) => it.kind !== 'company' && tokenScore(t, it.d, false).lvl >= 2)) out.add(t);
  return out;
}

export interface Rank {
  s: number;
  tier: Tier;
  /** every typed word is a whole word (or a whole code) of the item, not the beginning of a longer one */
  whole: boolean;
}

/**
 * Every typed word is a whole word of a name, a code or a cargo name of the item: "dri" is a word of "Pig iron & DRI", the beginning of
 * "Dried pulses". A word found only in the rest of the secondary text (a port, a region, a country, an operator) does not count: "chi" is
 * a whole word of the port "Ho Chi Minh City", and it must not put that route before the routes of China.
 */
export function wholeWords(q: string[], d: Searchable): boolean {
  const words = new Set([...d.n, ...(d.k ?? [])].flatMap((p) => p.split(' ')));
  return q.length > 0 && q.every((t) => words.has(t) || d.c.includes(t));
}

/**
 * Rank of a query (its words, from `tokens`) against an item: score 0 when a word matches nothing, otherwise the mean of
 * the words' scores, plus a bonus for the whole query being the name, or whole words of it, or the beginning of it.
 * Every word has to match, in the name, a code or the secondary text. `exact`: the words not to look for with a typo (exactWords).
 */
export function rank(q: string[], d: Searchable, exact?: Set<string>): Rank {
  if (!q.length) return { s: 1, tier: 1, whole: false };
  // a code typed whole with its suffix ("S15_63", "P1A_82"): its words are not each a word of the item
  if (q.length > 1 && d.c.includes(q.join(' '))) return { s: 160, tier: 4, whole: true };
  let sum = 0;
  let lvl = 4;
  for (const t of q) {
    const h = tokenScore(t, d, !exact?.has(t));
    if (!h.s) return { s: 0, tier: 0, whole: false };
    sum += h.s;
    lvl = Math.min(lvl, h.lvl);
  }
  const whole = q.join(' ');
  let bonus = 0;
  if (d.n.includes(whole) || d.c.includes(whole)) {
    bonus = 60;
    lvl = 4;
  } else if (d.n.some((n) => n.startsWith(`${whole} `))) bonus = q.length > 1 ? 20 : 15;
  else if (d.n.some((n) => ` ${n} `.includes(` ${whole} `))) bonus = q.length > 1 ? 20 : 12;
  else if (d.n.some((n) => n.startsWith(whole))) bonus = 6;
  return { s: sum / q.length + bonus, tier: lvl as Tier, whole: wholeWords(q, d) };
}

export const score = (q: string[], d: Searchable): number => rank(q, d).s;

/** What the grouping needs of an item. */
export interface Matchable {
  kind: string;
  label: string;
  d: Searchable;
  /** position in the kind's own order (a list with no query) */
  order: string | number;
  /** among items that match a query equally well, the one with the lower number comes first (default 0); the list with no query ignores it */
  tie?: number;
}

/**
 * The items of one kind that match, best first; with no query, the kind's own order. An item that has every typed word whole comes
 * before one that has a word only as the beginning of another ("DRI": the pig iron and DRI routes, then the "Dried pulses" ones,
 * which are not hidden); inside each, tier, then score, then the kind's own order.
 */
export function matchKind<T extends Matchable>(q: string[], items: T[], kind: string, exact = exactWords(q, items)): { item: T; s: number; tier: Tier; whole: boolean }[] {
  const out: { item: T; s: number; tier: Tier; whole: boolean }[] = [];
  for (const it of items) {
    if (it.kind !== kind) continue;
    const r = rank(q, it.d, exact);
    if (r.s > 0) out.push({ item: it, ...r });
  }
  return out.sort(
    (a, b) =>
      (q.length ? Number(b.whole) - Number(a.whole) || b.tier - a.tier || b.s - a.s || (a.item.tie ?? 0) - (b.item.tie ?? 0) : 0) || (a.item.order < b.item.order ? -1 : a.item.order > b.item.order ? 1 : 0) || a.item.label.localeCompare(b.item.label),
  );
}

const groupTier = (m: { tier: Tier }[]): Tier => Math.max(...m.map((x) => x.tier)) as Tier;

/**
 * The kinds that have a match, best group first: by the tier of its best item, then by TIE_ORDER (not by the raw score:
 * a prefix of a long word at the start of an event's title must not lead the commodity named by the query), then by score.
 */
export function groupKinds<T extends Matchable>(q: string[], items: T[], per: number): { kind: string; items: T[]; total: number; tier: Tier; s: number }[] {
  const out: { kind: string; items: T[]; total: number; tier: Tier; s: number }[] = [];
  const exact = exactWords(q, items);
  for (const kind of TIE_ORDER) {
    const m = matchKind(q, items, kind, exact);
    // the group is as good as its best item, which is not the first when a whole-word item of a lower tier leads it
    if (m.length) out.push({ kind, items: m.slice(0, per).map((x) => x.item), total: m.length, tier: groupTier(m), s: Math.max(...m.filter((x) => x.tier === groupTier(m)).map((x) => x.s)) });
  }
  return out.sort((a, b) => b.tier - a.tier || TIE_ORDER.indexOf(a.kind as (typeof TIE_ORDER)[number]) - TIE_ORDER.indexOf(b.kind as (typeof TIE_ORDER)[number]) || b.s - a.s);
}
