/**
 * Whether the registry's licence text of a source (data/sources.json, field `licence`) states a permission to reuse its
 * data, which is what a CSV download needs: a table or series is offered as a file only when every source of its rows
 * has one. The decision is made from the text alone, with one list of patterns; the terms of a third party are never
 * guessed, so a licence that says "terms to be confirmed" (or that no licence is stated, or that the terms were not read,
 * or that the data are proprietary) is not a permission, whatever else the text says.
 *
 * No import: scripts/licence.test.mjs runs this file as it is, against every source of the registry.
 */

/** A licence text that is no permission, even when it also names one ("CC BY 4.0 ... (terms to be confirmed)"). */
const NO_PERMISSION: RegExp[] = [
  /terms to be confirmed/i,
  /terms not read/i,
  /\bnot read\b/i,
  /no licen[cs]e (is )?stated/i,
  /states no reuse terms/i,
  /\bproprietary\b/i,
  /^copyright\b/i,
];

/** The licences that state a permission, with the short name each gives the licence column. */
const PERMISSION: { re: RegExp; short: (m: RegExpMatchArray) => string }[] = [
  { re: /public domain/i, short: () => 'Public domain' },
  { re: /\bCC0\b(?: 1\.0)?/, short: (m) => m[0] },
  { re: /\bCC BY(?:-SA|-NC|-ND)* \d(?:\.\d)?/, short: (m) => m[0] },
  { re: /\bEtalab Open Licen[cs]e \d(?:\.\d)?|\bEtalab\b/, short: (m) => m[0] },
  { re: /\bODbL(?: \d(?:\.\d)?)?/, short: (m) => m[0] },
  // the IMF's special terms for statistical data: reuse with attribution and the transformation stated, commercial reuse by permission
  { re: /IMF terms of use for statistical data/i, short: () => 'IMF terms of use for statistical data' },
  // the terms of two Federal Reserve Banks, quoted in the registry: reproduction with credit (Dallas: not for private gain)
  { re: /Dallas Fed Terms of Use/, short: () => 'Dallas Fed terms of use' },
  { re: /New York Fed Terms of Use/, short: () => 'New York Fed terms of use' },
];

/** True when the licence text states a permission to reuse the data. */
export function licenceAllows(text: string | null | undefined): boolean {
  const t = (text ?? '').trim();
  if (!t) return false;
  if (NO_PERMISSION.some((re) => re.test(t))) return false;
  return PERMISSION.some((p) => p.re.test(t));
}

/** The licence's short name ("Public domain", "CC BY 4.0"), or the first words of the text when it names none. */
export function licenceShort(text: string | null | undefined): string {
  const t = (text ?? '').trim();
  for (const p of PERMISSION) {
    const m = t.match(p.re);
    if (m) return p.short(m);
  }
  return t.length > 60 ? `${t.slice(0, 57).replace(/\s+\S*$/, '')}…` : t;
}
