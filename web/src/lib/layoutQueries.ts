/**
 * The three layouts, by what the screen can hold:
 *  - phone: up to 1024 px wide and not the tablet, which is every screen up to 760 px wide and every screen up to
 *    1024 px wide that is 500 px tall or less (a phone held sideways): the controls and the page are bottom sheets
 *    (or, held sideways, a column for the page);
 *  - tablet: 761 to 1024 px wide and at least 501 px tall: the controls and the page are columns, and a page folds
 *    the controls into their button;
 *  - desktop: 1025 px wide and more.
 * TABLET_QUERY is the condition of the one @media rule of styles/tablet.css (web/scripts/tablet-css.test.mjs keeps
 * them equal). The phone is defined as what is left up to 1024 px, so that no height or width falls between two layouts.
 * This file imports nothing, so that a test can run it as it is.
 */
export const TABLET_QUERY = '(min-width: 761px) and (max-width: 1024px) and (min-height: 501px)';
export const SHEET_QUERY = '(max-width: 1024px)';

export type MatchMedia = (query: string) => { matches: boolean };

const browserMatchMedia: MatchMedia = (q) => window.matchMedia(q);

export function isTabletLayout(mm: MatchMedia = browserMatchMedia): boolean {
  return mm(TABLET_QUERY).matches;
}

/** The phone layout: bottom sheets. A tablet is not one, though its width is under 1025 px. */
export function isSheetLayout(mm: MatchMedia = browserMatchMedia): boolean {
  return mm(SHEET_QUERY).matches && !mm(TABLET_QUERY).matches;
}

export interface FoldState {
  /** a page is open */
  open: boolean;
  isTablet: boolean;
  /** whether the controls were folded before a page folded them; null while no page has folded them */
  before: boolean | null;
  /** whether the controls are folded now */
  collapsed: boolean;
}

/**
 * The fold of the controls on a tablet: a page opens and folds them, its closing gives them back as they were,
 * unless the visitor opened them over the page (then they stay open). Off a tablet nothing folds.
 */
export function foldStep({ open, isTablet, before, collapsed }: FoldState): { before: boolean | null; collapsed: boolean } {
  if (!isTablet) return { before: null, collapsed };
  if (open && before === null) return { before: collapsed, collapsed: true };
  if (!open && before !== null) return { before: null, collapsed: collapsed ? before : collapsed };
  return { before, collapsed };
}
