/**
 * A source line that prints the registry's name of a source and then the series' basis must not name the publisher twice in a row: when the name of the
 * source already starts with its publisher ("Federal Reserve Bank of Dallas, index of ...") and the basis starts by crediting it ("Federal Reserve Bank of
 * Dallas: “Updated index ..."), the basis is printed from what follows the credit. Pure, no import: scripts/market-now.test.mjs runs this file as it is.
 */
export function withoutCredit(basis: string, source?: { name: string; publisher?: string }): string {
  const pub = source?.publisher;
  if (!pub || !source.name.startsWith(pub) || !basis.startsWith(`${pub}: `)) return basis;
  return basis.slice(pub.length + 2);
}

/** The tail of a hover title that names the source and then the series' basis: " · <basis>", with the credit the source name already holds left out; "" with no basis. */
export const basisSuffix = (basis: string | undefined, source?: { name: string; publisher?: string }): string => (basis ? ` · ${withoutCredit(basis, source)}` : '');
