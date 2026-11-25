/**
 * Which sources a list of flows names (Main flows block). A list whose rows come from more than one source (the Metallurgical coal page: two
 * exporters' own statistics) names the source of each row and every source in the footer; a list with one source is drawn as before; the rows of
 * the atlas's own estimates are not a source of their own.
 */
type HasSource = { s: string };

/** True when the rows of the list come from more than one source, the atlas's own rows (`atlas`) not counted. */
export const hasSeveralSources = (flows: HasSource[]): boolean => new Set(flows.filter((f) => f.s !== 'atlas').map((f) => f.s)).size > 1;

/** The definitions printed under the block, one sentence per source: only a list with several sources has them (a list with one source has its
 * single-source line), and only when the page file gives some. Empty when none is printed. */
export const flowDefinitions = (flows: HasSource[], defs?: string[]): string => (hasSeveralSources(flows) && defs?.length ? defs.join(' ') : '');

/** Whether a shown row carries its source tag: every row of a list with several sources; in a list with one source only a row of the atlas
 * beside rows of a source (the tag names what is not the footer's source). `rows` are the rows on screen, `flows` the whole list. */
export function showsSourceTag(f: HasSource, flows: HasSource[], rows: HasSource[]): boolean {
  const first = rows.find((r) => r.s !== 'atlas') ?? rows[0];
  return f.s === 'atlas' ? f.s !== first.s : hasSeveralSources(flows);
}

/** The tag of the rows of a Main flows block: customs codes do not separate thermal from metallurgical coal, so the flows of the Thermal coal
 * page are all coal and say so; the Metallurgical coal page lists the exporters' own statistics of metallurgical coal instead and carries no tag. */
export const allCoalTag = (id: string): string | undefined => (id === 'thermal-coal' ? 'all coal' : undefined);

/** " (customs)" after the mode of an overland arc: only a flow that carries a declared customs value is a customs flow (an exporter's own statistic does not). */
export const customsMark = (f: { usd?: number | null }): string => (f.usd != null ? ' (customs)' : '');
