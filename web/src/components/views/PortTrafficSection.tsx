/**
 * The "Weekly port traffic" block of a port page: IMF PortWatch's weekly port calls and its estimated export and import tonnes
 * of the PortWatch port the asset is paired with (data/freight/port-traffic/<id>.json), drawn as the chokepoint page draws its
 * series. The tonnes are PortWatch's estimates, said so wherever they are printed. Nothing here reads the port's own figures
 * (`output`): the two are never added, compared or reconciled.
 */
import { useMemo, useRef, useState } from 'preact/hooks';
import type { PortTraffic } from '../../types';
import { sources } from '../../lib/data';
import { fmt } from '../../lib/format';
import { loadPortTraffic } from '../../lib/freight';
import { downloadCsv, licenceColumn, licenceTexts, publisherOf, slug, sourceColumn, sourceName, toCsv } from '../../lib/csv';
import { MEASURES, SHIP_TYPES, csvRows, defaultMeasure, holeGaps, readoutFormatter, rolling52, sameName, sumText, weekCount, weekEnd, weekTimes, type Measure, type Stretch } from '../../lib/portTraffic';
import { Section, shortSource } from '../ui';
import { CsvAction } from '../CsvAction';
import { TimeChart, fmtTime, parseDate } from '../charts/TimeChart';
import { PW_COLORS, RANGES } from '../charts/pwChart';
import { useLoaded } from './shared';
import '../../styles/infra.css';

const TITLE = 'Weekly port traffic';
const MEASURE_LABEL: Record<Measure, string> = { calls: 'Calls', exports: 'Exports', imports: 'Imports' };
const MEASURE_TITLE: Record<Measure, string> = {
  calls: "Port calls per week: ships entering PortWatch's boundary of the port",
  exports: "IMF PortWatch's estimate of cargo exported through the port, thousand tonnes per week",
  imports: "IMF PortWatch's estimate of cargo imported through the port, thousand tonnes per week",
};
const CHART_UNIT: Record<Measure, string> = { calls: 'calls/week', exports: 'kt/week, estimate', imports: 'kt/week, estimate' };

/** The whole weekly series of the port: one row per week, ship type and measure, with its source and licence. */
function portCsv(doc: PortTraffic): string {
  const src = sourceColumn();
  const source = () => src(sourceName(doc.s), publisherOf(doc.s));
  const lic = licenceColumn();
  const licence = () => lic(...licenceTexts([doc.s]));
  const rows = csvRows(doc).map(([week, type, what, value, unit]) => [doc.id, doc.name, week, type, what, value, unit, source(), licence()]);
  return toCsv(['portwatch_port_id', 'portwatch_port', 'week_start', 'ship_type', 'measure', 'value', 'unit', 'source', 'licence'], rows);
}

const dayText = (iso: string) => fmtTime(parseDate(iso), 'date');

/** "52 weeks to 15 Nov 2026"; "51 of 52 weeks to ..." when PortWatch did not give every week. */
function stretchLabel(doc: PortTraffic, s: Stretch): string {
  const weeks = s.calls.weeks;
  return `${weeks < s.calls.span ? `${weeks} of ${s.calls.span}` : s.calls.span} weeks to ${dayText(s.end)}`;
}

function Block({ doc, name, note }: { doc: PortTraffic; name: string; note?: string }) {
  const [pick, setPick] = useState<Measure | null>(null);
  const measure = pick ?? defaultMeasure(doc);
  // the chart's visible window survives a change of measure
  const win = useRef<{ min: number; max: number } | null>(null);
  const x = useMemo(() => weekTimes(doc), [doc]);
  const gaps = useMemo(() => holeGaps(doc), [doc]);
  const series = useMemo(
    () => SHIP_TYPES.map(([t, label]) => ({ label, values: doc[measure][t], color: PW_COLORS[t], ...(gaps.length ? { gaps } : {}) })),
    [doc, measure, gaps],
  );
  const readoutFormat = useMemo(() => readoutFormatter(measure, fmt), [measure]);
  const { last, before } = useMemo(() => rolling52(doc), [doc]);
  const src = sources.value[doc.s];
  const lastWeekEnd = weekEnd(doc, weekCount(doc) - 1);
  const rows: [Stretch, string][] = before ? [[last, stretchLabel(doc, last)], [before, stretchLabel(doc, before)]] : [[last, stretchLabel(doc, last)]];
  return (
    <Section
      title={TITLE}
      aside={
        <span class="tc-ranges" role="group" aria-label="Measure">
          {MEASURES.map((m) => (
            <button key={m} class="tc-btn" aria-pressed={measure === m} onClick={() => setPick(m)} title={MEASURE_TITLE[m]}>
              {MEASURE_LABEL[m]}
            </button>
          ))}
        </span>
      }
    >
      {!sameName(name, doc.name) && <div class="pt-port">PortWatch port: {doc.name}</div>}
      {note && <div class="muted small pt-note">{note}</div>}
      <TimeChart
        x={x}
        series={series}
        unit={CHART_UNIT[measure]}
        readoutFormat={readoutFormat}
        stacked
        ranges={RANGES}
        defaultRange="3Y"
        view={win.current}
        onRange={(min, max) => { win.current = { min, max }; }}
        height={190}
        ariaLabel={`${doc.name} weekly ${measure === 'calls' ? 'port calls' : `estimated ${measure} tonnes`}`}
      />
      <div class="pt-tab" role="table" aria-label="Sums of the last 52 weeks">
        <span role="columnheader" />
        <span class="pt-h" role="columnheader">Calls</span>
        <span class="pt-h" role="columnheader">Exports (est.)</span>
        <span class="pt-h" role="columnheader">Imports (est.)</span>
        {rows.map(([s, label]) => (
          <div class="pt-row" role="row" key={label}>
            <span class="pt-k" role="rowheader">{label}</span>
            <span class="num" role="cell">{sumText('calls', s.calls)}</span>
            <span class="num" role="cell">{sumText('exports', s.exports)}</span>
            <span class="num" role="cell">{sumText('imports', s.imports)}</span>
          </div>
        ))}
      </div>
      <div class="src-line" data-src={doc.s} data-y={doc.y}>
        Source:{' '}
        {src ? (
          <a href={src.url} target="_blank" rel="noopener">
            {shortSource(doc.s)}
          </a>
        ) : (
          shortSource(doc.s)
        )}{' '}
        ({sources.value[doc.s]?.publisher ?? 'IMF and University of Oxford'}), data adapted · {lastWeekEnd === doc.y ? `data to ${dayText(doc.y)}` : `weeks to ${dayText(lastWeekEnd)}, data to ${dayText(doc.y)}`} · weekly sums of daily figures; a call is a ship
        entering PortWatch's own boundary of the port, which is not always this asset's (PortWatch leaves out calls of less than 5 hours with no change of draught);
        tonnes are PortWatch's estimates from each ship's size and draught, not a port statistic; ships are counted from their AIS signals: PortWatch notes that
        "ships can turn off their AIS transponder to avoid being detected" and calls it "not common for container and other cargo ships" entering a port
      </div>
      <div class="lt-foot">
        <CsvAction
          sources={[doc.s]}
          onClick={() => downloadCsv(`commodity-flows-atlas-${slug(doc.name)}-weekly-port-traffic-to-${doc.y}.csv`, portCsv(doc))}
          title="The whole weekly series, by ship type, with its source and licence, as a CSV file"
        />
      </div>
    </Section>
  );
}

/**
 * `id` is the PortWatch port id of the asset, `name` the asset's name, `note` the sentence typed on the asset for a series that is not
 * quite its own. Nothing is shown while the file loads, and nothing for a port that has no series.
 */
export default function PortTrafficSection({ id, name, note }: { id: string; name: string; note?: string }) {
  const got = useLoaded<{ doc: PortTraffic | null; failed?: true }>(
    () => loadPortTraffic(id).then((doc) => ({ doc }), () => ({ doc: null, failed: true as const })),
    [id],
  );
  if (!got) return null;
  if (got.failed)
    return (
      <Section title={TITLE}>
        <div class="muted small">Weekly port traffic is not available.</div>
      </Section>
    );
  if (!got.doc || weekCount(got.doc) < 1) return null;
  return <Block key={id} doc={got.doc} name={name} note={note} />;
}
