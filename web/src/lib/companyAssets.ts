/**
 * Which infrastructure assets a company runs or owns, from the operator field of the assets: no dependency, so that
 * scripts/company-assets.test.mjs can run it as it is.
 */

const CORP = /\s+(energy|corporation|corp\.?|group|plc|ltd\.?|limited|inc\.?|holdings|resources|mining|company|co\.|s\.?a\.?|ag|asa|nv|se|international)$/i;
const GENERIC = new Set(['china', 'saudi', 'national', 'united', 'royal', 'golden', 'star', 'pacific', 'general', 'global', 'coal', 'oil', 'gas', 'petroleum', 'the']);

/** The forms of a company's name an operator field may use: the name, the names in brackets, the name without "Energy", "Group"... */
export function nameForms(name: string): string[] {
  const out = new Set<string>();
  const add = (s: string, min: number) => {
    const t = s.trim().replace(/^(formerly|incl\.|ex-)\s*/i, '');
    if (t.length >= min && !t.endsWith('&') && !GENERIC.has(t.toLowerCase())) out.add(t);
  };
  const base = name.replace(/\s*\([^)]*\)\s*/g, ' ').trim();
  add(base, 2);
  for (const m of name.matchAll(/\(([^)]+)\)/g)) m[1].split(/[,;]/).forEach((p) => add(p, 3));
  let s = base;
  while (CORP.test(s)) {
    s = s.replace(CORP, '');
    add(s, 4);
  }
  return [...out];
}

const escRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * Words that make the name that follows them, in the same clause, a former owner: "sold by Shell in April 2025",
 * "Aster, ex-Shell", "formerly Adaro Energy", "previously BP", "bought from Rio Tinto", "which bought Mechel's stake".
 */
const FORMER = /(^|[^\p{L}\p{N}])(sold by|formerly|previously|bought|ex-)/iu;
/** What ends a clause of an operator field. */
const CLAUSE_END = [';', ',', '(', ')'];

/**
 * A test of an operator field for one company: true when the field names it as operator or as an owner, at least once
 * not as a former owner. `others`: the other companies of the lists; a name that begins one of theirs is theirs there
 * ("Gazprom" in "Gazprom Neft").
 */
export function operatorMatcher(name: string, others: string[] = []): (operator: string) => boolean {
  const forms = nameForms(name);
  const lower = forms.map((n) => n.toLowerCase());
  const longer = others
    .filter((o) => o !== name)
    .flatMap(nameForms)
    .map((o) => o.toLowerCase())
    .filter((o) => lower.some((n) => o.startsWith(`${n} `)));
  const res = forms.map((n) => new RegExp(`(^|[^\\p{L}\\p{N}])${escRe(n)}(?=$|[^\\p{L}\\p{N}])`, 'giu'));
  return (operator) =>
    res.some((r) => {
      for (const m of operator.matchAll(r)) {
        const at = m.index! + m[1].length;
        if (longer.some((o) => operator.slice(at, at + o.length).toLowerCase() === o)) continue;
        const before = operator.slice(0, at);
        const clause = before.slice(Math.max(...CLAUSE_END.map((c) => before.lastIndexOf(c))) + 1);
        if (!FORMER.test(clause)) return true;
      }
      return false;
    });
}
