/** Chokepoint status board: every passage with IMF PortWatch traffic over the last 28 days against the 2023 average. */
import { useMemo, useState } from 'preact/hooks';
import type { Chokepoint, PortwatchSeries } from '../../types';
import { fmt, pctText } from '../../lib/format';
import { loadChokepoints, loadPortwatch } from '../../lib/freight';
import { select } from '../../lib/store';
import { Section, SourceLine, Skeleton, Placeholder } from '../ui';
import { useFreightCatalogue, useLoaded } from './shared';

const DAYS = 28;
const DAY_MS = 86400000;
const SPARK_WEEKS = 104;

interface Row {
  id: string;
  name: string;
  /** the counter's own name when the page borrows another passage's series */
  counter?: string;
  partial?: string;
  transits: number | null;
  transits2023: number | null;
  mt: number | null;
  mt2023: number | null;
  gap: number | null;
  gapMt: number | null;
  spark: number[];
  /** 2023 average, vessels per day */
  base: number | null;
  to: string;
}

const gapOf = (now: number | null, ref: number | null) => (now != null && ref ? (100 * (now - ref)) / ref : null);

/** The measures of one series: the `compare` block the build writes, else the same figures from the weekly averages. */
function measure(pw: PortwatchSeries) {
  const c = pw.compare;
  const t0 = Date.parse(pw.start);
  const weeks = pw.total.length;
  const inYear = (i: number) => new Date(t0 + i * 7 * DAY_MS).getUTCFullYear() === 2023;
  const mean = (a: number[], pick: (i: number) => boolean) => {
    const v = a.filter((_, i) => pick(i));
    return v.length >= 50 ? v.reduce((s, x) => s + x, 0) / v.length : null;
  };
  const last = (a: number[]) => (a.length >= DAYS / 7 ? (a.slice(-DAYS / 7).reduce((s, x) => s + x, 0) * 7) : null);
  const per2023 = mean(pw.total, inYear);
  const mt2023 = pw.vol ? mean(pw.vol.total, inYear) : null;
  return {
    to: c?.to ?? pw.y,
    transits: c ? c.transits.now : last(pw.total),
    transits2023: c ? c.transits.avg2023 : per2023 != null ? per2023 * DAYS : null,
    mt: c ? c.mt.now : pw.vol ? last(pw.vol.total) : null,
    mt2023: c ? c.mt.avg2023 : mt2023 != null ? mt2023 * DAYS : null,
    base: per2023,
    spark: pw.total.slice(Math.max(0, weeks - SPARK_WEEKS)),
  };
}

type SortKey = 'gap' | 'gapMt' | 'transits' | 'name';
const SORTS: { key: SortKey; label: string }[] = [
  { key: 'gap', label: 'Gap in transits' },
  { key: 'gapMt', label: 'Gap in tonnes' },
  { key: 'transits', label: 'Transits' },
  { key: 'name', label: 'Name' },
];

function Spark({ values, base }: { values: number[]; base: number | null }) {
  const w = 72;
  const h = 22;
  if (values.length < 2) return <span style={{ width: `${w}px` }} />;
  const max = Math.max(...values, base ?? 0, 1e-9);
  const x = (i: number) => (i / (values.length - 1)) * (w - 2) + 1;
  const y = (v: number) => h - 2 - (v / max) * (h - 4);
  const d = values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join('');
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Weekly transits over the last two years, with the 2023 average as a dashed line">
      {base != null && <line x1="0" x2={w} y1={y(base)} y2={y(base)} stroke="var(--ink-2, #7d8a99)" stroke-dasharray="2 2" stroke-width="1" />}
      <path d={d} fill="none" stroke="var(--accent, #9db7ff)" stroke-width="1.4" />
    </svg>
  );
}

const signed = (v: number | null) => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${pctText(Math.abs(v))}`);

export default function BoardView({ id }: { id: string }) {
  useFreightCatalogue();
  const rows = useLoaded<{ rows: Row[]; none: string[] }>(async () => {
    if (id !== 'chokepoints') return null;
    const chk = await loadChokepoints();
    const own = (c: Chokepoint) => c.seriesFrom ?? (c.portwatch ? c.id : null);
    const series = new Map<string, PortwatchSeries | null>();
    await Promise.all(
      [...new Set(chk.map(own).filter((x): x is string => !!x))].map((s) =>
        loadPortwatch(s).then((p) => series.set(s, p), () => series.set(s, null)),
      ),
    );
    const out: Row[] = [];
    const none: string[] = [];
    for (const c of chk) {
      const sid = own(c);
      const pw = sid ? series.get(sid) : null;
      if (!pw) {
        none.push(c.name);
        continue;
      }
      const m = measure(pw);
      out.push({
        id: c.id,
        name: c.name,
        counter: c.seriesFrom ? pw.name ?? sid ?? undefined : undefined,
        partial: c.portwatchLabel,
        ...m,
        gap: gapOf(m.transits, m.transits2023),
        gapMt: gapOf(m.mt, m.mt2023),
      });
    }
    return { rows: out, none };
  }, [id]);
  const [sort, setSort] = useState<SortKey>('gap');
  const [desc, setDesc] = useState(false);
  const sorted = useMemo(() => {
    const list = [...(rows?.rows ?? [])];
    const val = (r: Row) => (sort === 'name' ? r.name : sort === 'gap' ? r.gap : sort === 'gapMt' ? r.gapMt : r.transits);
    list.sort((a, b) => {
      const x = val(a);
      const y = val(b);
      if (x == null || y == null) return x == null && y == null ? a.name.localeCompare(b.name) : x == null ? 1 : -1; // no figure last
      const c = typeof x === 'string' ? x.localeCompare(y as string) : (x as number) - (y as number);
      return (desc ? -c : c) || a.name.localeCompare(b.name);
    });
    return list;
  }, [rows, sort, desc]);

  const head = (
    <div class="detail-head" style={{ '--kicker': 'var(--chokepoint)' }}>
      <div class="detail-kicker">Chokepoints</div>
      <h2 class="detail-title">All passages: traffic against 2023</h2>
    </div>
  );
  if (rows === undefined) return (<>{head}<div class="panel-scroll"><Skeleton lines={8} /></div></>);
  if (rows === null) return (<>{head}<div class="panel-scroll"><Placeholder>This page is not in the atlas catalogue.</Placeholder></div></>);
  const to = rows.rows[0]?.to;
  return (
    <>
      {head}
      <div class="panel-scroll">
        <p class="prose" style={{ margin: '8px 0 0' }}>
          Vessel transits and PortWatch's estimated trade volume over the last {DAYS} days{to ? ` (to ${to})` : ''}, against the average of 2023 over the same number of days. 2023 is the last full year before the Red Sea diversions and the closure of Hormuz.
        </p>
        <Section title="Passages">
          <div class="chips" role="group" aria-label="Sort by" style={{ marginBottom: '8px' }}>
            {SORTS.map((s) => (
              <button
                key={s.key}
                class="chip"
                aria-pressed={sort === s.key}
                title={sort === s.key ? 'Select again to reverse the order' : `Sort by ${s.label.toLowerCase()}`}
                onClick={() => {
                  if (sort === s.key) setDesc(!desc);
                  else {
                    setSort(s.key);
                    setDesc(s.key === 'transits');
                  }
                }}
              >
                {s.label}
                {sort === s.key ? (desc ? ' ↓' : ' ↑') : ''}
              </button>
            ))}
          </div>
          {sorted.map((r) => (
            <button
              key={r.id}
              class="list-btn"
              style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: '2px 10px', alignItems: 'center', width: '100%', textAlign: 'left' }}
              onClick={() => select({ kind: 'chokepoint', id: r.id })}
              title={`Open ${r.name}`}
            >
              <span>
                <b>{r.name}</b>
                {r.counter && <span class="muted small"> · counter: {r.counter}</span>}
                {r.partial && <span class="muted small"> · {r.partial}</span>}
              </span>
              <Spark values={r.spark} base={r.base} />
              <span class="muted small num" style={{ gridColumn: '1 / -1' }}>
                <span style={{ display: 'block' }}>Transits {r.transits != null ? fmt(r.transits) : '—'} vs {r.transits2023 != null ? fmt(r.transits2023) : '—'} in 2023: <b>{signed(r.gap)}</b></span>
                <span style={{ display: 'block' }}>Tonnes {r.mt != null ? `${fmt(r.mt)} Mt` : '—'} vs {r.mt2023 != null ? `${fmt(r.mt2023)} Mt` : '—'} in 2023: <b>{signed(r.gapMt)}</b></span>
              </span>
            </button>
          ))}
          {rows.none.length > 0 && <div class="muted small" style={{ marginTop: '8px' }}>No PortWatch counter of its own: {rows.none.join(', ')}.</div>}
        </Section>
        <SourceLine s="portwatch" y={to ? `28 days to ${to}` : undefined} n="vessels counted are tankers, dry bulk, container, general cargo and ro-ro; the volume is PortWatch's estimate of the cargo they carry, not a customs statistic" />
      </div>
    </>
  );
}
