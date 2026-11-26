/**
 * The publishers the atlas only links to: a registry entry (data/sources.json) whose `use` says that no value is stored or shown. The Sources tab of
 * the About window counts them from the registry, as pipeline/common/sources_table.py does for DATA_SOURCES.md.
 *
 * No import: scripts/about-sources.test.mjs runs this file as it is.
 */
export const LINK_ONLY_MARK = 'no value is stored or shown';

export const isLinkOnly = (s: { use?: string }): boolean => (s.use ?? '').includes(LINK_ONLY_MARK);

const NUMBER_WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six'];

/** The clause the introduction of the Sources tab adds after "lists every source with its licence": empty when there is no such publisher. */
export function linkOnlyClause(n: number): string {
  if (n <= 0) return '';
  return `, and also ${NUMBER_WORDS[n] ?? n} ${n === 1 ? 'publisher the atlas only links' : 'publishers the atlas only links'} to, of which it shows no value`;
}
