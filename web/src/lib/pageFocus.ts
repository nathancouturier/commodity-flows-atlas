/**
 * "The next page that opens takes the focus to its heading." Said by the search field when a result is chosen with
 * Enter: the page may open long after the key (the map and the lazy view are busy first), so a timing rule cannot tell
 * it from a click. The wish lapses after a while, so that a page opened later by a click does not take the focus.
 */
let until = 0;

export function wantPageFocus(ms = 20000): void {
  until = performance.now() + ms;
}

/** True once for the page that opens while the wish stands. */
export function takePageFocus(): boolean {
  const yes = performance.now() < until;
  until = 0;
  return yes;
}
