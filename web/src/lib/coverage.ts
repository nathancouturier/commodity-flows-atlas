/**
 * The coverage matrix (data/coverage.json, built by pipeline/commodities/build_coverage.py): which blocks each commodity page holds.
 * Pure functions on the file, with no import, so that Node runs this file as it is (web/scripts/coverage.test.mjs). Every count the
 * site prints about the matrix comes from here, from the file: none is typed.
 */

/** p present, m missing (not in the atlas yet), na not applicable, nf not available for free. */
export type CellState = 'p' | 'm' | 'na' | 'nf';

export interface CoverageBlock {
  id: string;
  label: string;
  /** what makes the block present, in words */
  text: string;
  /** the families whose pages have this block at all; absent: every page */
  families?: string[];
}

export interface CoverageReason {
  /** na or nofree */
  st: 'na' | 'nofree';
  t: string;
}

export interface CoverageFile {
  version: number;
  /** the release the file was built for (release.json) */
  release: number;
  blocks: CoverageBlock[];
  reasons: Record<string, CoverageReason>;
  /** one row per commodity page; `cells` holds the blocks the page can have: p, m, na:<reason id> or nf:<reason id> */
  pages: { id: string; cells: Record<string, string> }[];
  /** page -> its missing blocks, the largest seaborne trade first (not drawn by the site) */
  work: Record<string, string[]>;
}

/**
 * Whether a commodity page lists the blocks that are missing (state m) beside the ones it cannot have. Off: the missing blocks are
 * shown in the Quality tab of the About window only, until the owner has said which blocks a page is expected to hold.
 */
export const SHOW_MISSING_ON_PAGES = false;

/** The names of the states. m is called "missing" in the Quality tab and said "not in the atlas yet" on a page. */
export const STATE_NAME: Record<CellState, string> = {
  p: 'present',
  m: 'missing',
  na: 'not applicable',
  nf: 'not available for free',
};
export const STATE_WORDS: Record<CellState, string> = { ...STATE_NAME, m: 'not in the atlas yet' };

/** A cell of the file: "p", "m", "na:<reason id>" or "nf:<reason id>". The reason is null for p and m. */
export function parseCell(file: CoverageFile, raw: string): { state: CellState; reason: string | null } {
  if (raw === 'p') return { state: 'p', reason: null };
  const i = raw.indexOf(':');
  const head = i < 0 ? raw : raw.slice(0, i);
  if (head === 'na' || head === 'nf') return { state: head, reason: file.reasons[raw.slice(i + 1)]?.t ?? null };
  return { state: 'm', reason: null };
}

/** Every cell of the file, page by page, blocks in the file's order. This is what the grid draws, one mark each. */
export function allCells(file: CoverageFile): { page: string; block: CoverageBlock; state: CellState; reason: string | null }[] {
  const out: { page: string; block: CoverageBlock; state: CellState; reason: string | null }[] = [];
  for (const p of file.pages)
    for (const block of file.blocks) {
      const raw = p.cells[block.id];
      if (raw !== undefined) out.push({ page: p.id, block, ...parseCell(file, raw) });
    }
  return out;
}

/** The cells of the file by state. `applicable` is every cell that is not marked not applicable. */
export function coverageCounts(file: CoverageFile): Record<CellState, number> & { total: number; applicable: number } {
  const n = { p: 0, m: 0, na: 0, nf: 0, total: 0, applicable: 0 };
  for (const c of allCells(file)) {
    n[c.state]++;
    n.total++;
  }
  n.applicable = n.total - n.na;
  return n;
}

/** Each reason of the table, in its order, with the number of cells that carry it. */
export function reasonCounts(file: CoverageFile): { id: string; st: 'na' | 'nofree'; t: string; cells: number }[] {
  const used = new Map<string, number>();
  for (const p of file.pages)
    for (const raw of Object.values(p.cells)) {
      const i = raw.indexOf(':');
      if (i > 0) used.set(raw.slice(i + 1), (used.get(raw.slice(i + 1)) ?? 0) + 1);
    }
  return Object.entries(file.reasons).map(([id, r]) => ({ id, st: r.st, t: r.t, cells: used.get(id) ?? 0 }));
}

/**
 * The blocks a commodity page lists in its folded section: the ones it cannot have (not applicable, not available for free) and,
 * only when `showMissing`, the missing ones. A page with none lists none and draws no section.
 */
export function pageGaps(file: CoverageFile, id: string, showMissing: boolean): { block: CoverageBlock; state: CellState; reason: string | null }[] {
  const page = file.pages.find((p) => p.id === id);
  if (!page) return [];
  const out: { block: CoverageBlock; state: CellState; reason: string | null }[] = [];
  for (const block of file.blocks) {
    const raw = page.cells[block.id];
    if (raw === undefined) continue;
    const c = parseCell(file, raw);
    if (c.state === 'p' || (c.state === 'm' && !showMissing)) continue;
    out.push({ block, state: c.state, reason: c.reason });
  }
  return out;
}
