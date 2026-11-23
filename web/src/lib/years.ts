/** Years of a source line, for the citation (no import: scripts/years.test.mjs runs this file as it is). */
/** The years, dates, seasons and periods a source line names: "2005–2024" is one period, "2024/25" one season, "2026-11-15" one date. */
export function yearsOf(text: string): string[] {
  const found: string[] = [];
  let rest = text;
  const take = (re: RegExp, tidy = (m: string) => m) => {
    rest = rest.replace(re, (m) => {
      found.push(tidy(m));
      return ' ';
    });
  };
  take(/\d{4}-\d{2}-\d{2}/g);
  take(/\d{4}\s*[–—-]\s*\d{4}/g, (m) => m.replace(/\s*[–—-]\s*/, '–'));
  take(/\d{4}\/\d{2,4}/g);
  take(/\d[QH]\d{2}/g);
  take(/\d{4}-\d{2}(?!\d)/g);
  take(/\b\d{4}\b/g);
  return found.length ? found : text.trim() ? [text.trim()] : [];
}
