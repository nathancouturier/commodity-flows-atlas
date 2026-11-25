/**
 * The "World Port Index" block of a port page: the publication's own figures for the entry that matches the port
 * (data/infrastructure/wpi.json), under their own source. Shown beside "Limits", never merged with it. A port with no
 * entry (a doubtful or absent match) has no block: nothing is written in its place.
 */
import { Fragment } from 'preact';
import { sources, sourceLabel } from '../../lib/data';
import { loadWpi, monthYear } from '../../lib/infra';
import { wpiEntryText, wpiRows } from '../../lib/wpi';
import { Section, shortSource } from '../ui';
import { useLoaded } from './shared';
import '../../styles/infra.css';

export default function PortWpi({ id }: { id: string }) {
  const file = useLoaded(loadWpi, []);
  const e = file && Object.hasOwn(file.ports, id) ? file.ports[id] : undefined;
  const rows = e ? wpiRows(e) : [];
  if (!file || !e || !rows.length) return null;
  // the file has no year of its own: the month the atlas read it, or the publication's edition when one is typed
  const name = `${sourceLabel(file.s)}, ${shortSource(file.s)}`;
  const when = file.edition ? null : `read ${monthYear(file.read)}`;
  const url = sources.value[file.s]?.url;
  const link = file.edition ? `${name}, ${file.edition}` : name;
  return (
    <Section title="World Port Index">
      <p class="infra-limits-note">Entry: {wpiEntryText(e)}</p>
      <dl class="wpi-rows">
        {rows.map((r) => (
          <Fragment key={r.label}>
            <dt>{r.label}</dt>
            <dd title={`${name} · ${when ?? file.edition}`}>{r.value}</dd>
          </Fragment>
        ))}
      </dl>
      <div class="src-line">
        Source:{' '}
        {url ? (
          <a href={url} target="_blank" rel="noopener">
            {link} ↗
          </a>
        ) : (
          link
        )}
        {when && <> · {when}</>}
      </div>
    </Section>
  );
}
