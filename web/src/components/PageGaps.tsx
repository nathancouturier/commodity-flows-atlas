/**
 * The folded section at the foot of a commodity page: the blocks the page cannot have, each with its reason (data/coverage.json,
 * lib/coverage.ts). A page with none draws no section, and so does a page whose file could not be loaded. The blocks that are
 * missing are listed only when SHOW_MISSING_ON_PAGES is on.
 */
import { useEffect, useState } from 'preact/hooks';
import { loadOptional } from '../lib/data';
import { SHOW_MISSING_ON_PAGES, STATE_WORDS, pageGaps, type CoverageFile } from '../lib/coverage';
import { Section } from './ui';

export function PageGaps(props: { id: string }) {
  const [file, setFile] = useState<CoverageFile | null>(null);
  useEffect(() => {
    let live = true;
    loadOptional<CoverageFile>('coverage.json').then((f) => live && setFile(f));
    return () => {
      live = false;
    };
  }, []);
  const gaps = file ? pageGaps(file, props.id, SHOW_MISSING_ON_PAGES) : [];
  if (!gaps.length) return null;
  return (
    <Section fold title={SHOW_MISSING_ON_PAGES ? 'What this page does not have' : 'What does not apply here'} aside={<span class="muted num">{gaps.length}</span>}>
      <ul class="bullets small-print">
        {gaps.map((g) => (
          <li key={g.block.id}>
            {g.block.label} · {STATE_WORDS[g.state]}
            {g.reason ? `: ${g.reason}` : ''}
          </li>
        ))}
      </ul>
    </Section>
  );
}
