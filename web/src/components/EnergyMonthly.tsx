/**
 * Monthly blocks of the energy pages (EIA International, monthly series; data/commodities/monthly/<id>.json, loaded on demand):
 * crude oil production by month with the latest month against the average of the year before, the latest year so far against it for
 * the Gulf producers and the world, OECD imports by origin and petroleum stocks; the same stocks and the monthly oil demand on the
 * refined products page; natural gas plant liquids on the LPG page. Every figure is a published monthly figure or arithmetic on two of
 * them (the average of a year, a change in per cent, a stock over a demand), and names its month.
 */
import { useState } from 'preact/hooks';
import type { CommodityMonthly, ImportRow, MonthlyBlock, MonthlyRow } from '../types';
import { commodityMeta, countryName, isCountry, loadOptional } from '../lib/data';
import { fmt } from '../lib/format';
import { select } from '../lib/store';
import { Section, SourceLine, TrendLine } from './ui';
import { useLoaded } from './views/shared';
import '../styles/energy-monthly.css';
import { CsvAction } from './CsvAction';
import { downloadMonthly } from '../lib/blockCsv';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
/** "2026-07" -> "Jul 2026" */
export const monthName = (m: string) => `${MONTHS[Number(m.slice(5)) - 1]} ${m.slice(0, 4)}`;
/** "−16.4%" / "+2.1%": a change with its sign. */
export const signedPct = (p: number | null | undefined) => (p == null ? '—' : `${p > 0 ? '+' : p < 0 ? '−' : ''}${Math.abs(p).toFixed(1)}%`);
const tone = (p: number | null | undefined) => (p == null || p === 0 ? '' : p < 0 ? ' mo-down' : ' mo-up');
const rowName = (r: MonthlyRow | ImportRow, names?: Record<string, string>) => r.name ?? names?.[r.o ?? ''] ?? (r.c ? countryName(r.c) : (r.o ?? ''));

/** The commodity pages that have a monthly file. */
const MONTHLY_PAGES = new Set(['crude-oil', 'refined-products', 'lpg', 'lng']);
const ORIGIN_NAME: Record<string, string> = { PERG: 'Persian Gulf', OPEC: 'OPEC', OPAF: 'OPEC Africa', OPSA: 'OPEC South America' };

/** A figure with its month (or another short line) under it; `none` is printed instead of a missing figure. */
function Cell(props: { v: number | null | undefined; m?: string; sub?: string; none?: string; title?: string; strong?: boolean }) {
  return (
    <span class={`mo-cell${props.strong ? ' mo-strong' : ''}`} title={props.title}>
      {props.v == null ? <span class={props.none ? 'mo-none' : undefined}>{props.none ?? '—'}</span> : fmt(props.v)}
      {(props.sub ?? (props.m && monthName(props.m))) && <small>{props.sub ?? monthName(props.m as string)}</small>}
    </span>
  );
}

function RowName(props: { r: MonthlyRow | ImportRow; names?: Record<string, string> }) {
  const { r } = props;
  const name = rowName(r, props.names);
  return r.c && isCountry(r.c) ? (
    <button class="mo-name" title={name} onClick={() => select({ kind: 'country', id: r.c as string })}>
      {name}
    </button>
  ) : (
    <span class="mo-name" title={name}>
      {name}
    </span>
  );
}

const trendTitle = (r: MonthlyRow, from: string, n: number, u: string) => {
  const v = r.v.slice(-n);
  const first = v.findIndex((x) => x != null);
  return first < 0 ? '' : `${monthName(shift(from, r.v.length - n + first))} ${fmt(v[first])} → ${monthName(shift(from, r.v.length - 1))} ${fmt(v[v.length - 1])} ${u}`;
};
/** The month `n` months after `from`. */
function shift(from: string, n: number): string {
  const t = Number(from.slice(0, 4)) * 12 + Number(from.slice(5)) - 1 + n;
  return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, '0')}`;
}

/** Latest month against the average of the baseline year: a 24-month line, the latest figure with its month, and the change. */
function LatestTable(props: { block: MonthlyBlock; rows: MonthlyRow[]; lead?: MonthlyRow[]; limit?: number; label: string }) {
  const { block } = props;
  const limit = props.limit ?? 10;
  const [all, setAll] = useState(false);
  const rows = all ? props.rows : props.rows.slice(0, limit);
  const base = block.baseYear ?? Number(block.to.slice(0, 4)) - 1;
  const line = (r: MonthlyRow, extra = '') => (
    <div class={`mo-row mo-latest${extra}`} key={`${r.c ?? r.name}`}>
      <RowName r={r} />
      <TrendLine vals={r.v.slice(-24)} at={r.v.slice(-24).length - 1} w={56} title={trendTitle(r, block.from, 24, block.u)} />
      <Cell v={r.la.v} m={r.la.m} />
      <span class={`mo-pct${tone(r.p)}`} title={r.b != null ? `${base} average ${fmt(r.b)} ${block.u}` : undefined}>
        {signedPct(r.p)}
      </span>
    </div>
  );
  return (
    <div class="mo-table">
      <div class="mo-row mo-latest mo-head" aria-hidden="true">
        <span>{props.label}</span>
        <span>24 months</span>
        <span>Latest month</span>
        <span>vs {base}</span>
      </div>
      {props.lead?.map((r) => line(r, ' mo-lead'))}
      {rows.map((r) => line(r))}
      {props.rows.length > limit && (
        <div class="lt-foot" style={{ marginTop: '10px' }}>
          <button class="act-btn" onClick={() => setAll(!all)} aria-expanded={all}>
            {all ? 'Show fewer' : `Show all (${props.rows.length})`}
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Average of the baseline year, lowest month and latest month of the year of the latest month, each with its month. A month without a
 * figure (imports by origin) is printed as "no figure", never as a zero, and no lowest month is printed for a year that has such a month.
 */
function RangeTable(props: { rows: (MonthlyRow | ImportRow)[]; from: string; to: string; baseYear: number; u: string; label: string; names?: Record<string, string>; lead?: MonthlyRow[]; latest?: string }) {
  const year = props.to.slice(0, 4);
  const line = (r: MonthlyRow | ImportRow, extra = '') => {
    const imp = r as ImportRow;
    return (
      <div class={`mo-row mo-range${extra}`} key={`${r.c ?? ''}${r.o ?? ''}${r.name ?? ''}`}>
        <RowName r={r} names={props.names} />
        <Cell v={r.b} sub={r.b == null && imp.nb != null ? `${imp.nb} of 12` : undefined} title={r.b == null && imp.nb != null ? `${props.baseYear}: EIA gives a figure for ${imp.nb} of the 12 months, so no average is shown` : undefined} />
        <Cell v={r.lo?.v} m={r.lo?.m} sub={r.lo == null && imp.miss ? `${imp.miss} missing` : undefined} title={r.lo == null && imp.miss ? `${year}: EIA gives no figure for ${imp.miss} of the months so far, so no lowest month is shown` : undefined} />
        <Cell
          v={r.la?.v}
          m={r.la?.m}
          none="no figure"
          sub={r.la == null && imp.last ? `last ${monthName(imp.last.m)}` : undefined}
          title={r.la == null && imp.last ? `EIA gives no figure for ${monthName(props.to)}; its latest figure is ${fmt(imp.last.v)} ${props.u} in ${monthName(imp.last.m)}` : undefined}
          strong
        />
        <span class={`mo-pct${tone(r.p)}`}>{signedPct(r.p)}</span>
      </div>
    );
  };
  return (
    <div class="mo-table">
      <div class="mo-row mo-range mo-head" aria-hidden="true">
        <span>{props.label}</span>
        <span>{props.baseYear} avg</span>
        <span>Lowest {year}</span>
        <span>{props.latest ?? 'Latest'}</span>
        <span>Change</span>
      </div>
      {props.rows.map((r) => line(r))}
      {props.lead?.map((r) => line(r, ' mo-lead'))}
    </div>
  );
}

/** The CSV of a monthly block: every month of every row (all importers for the imports by origin). */
function MonthlyCsv(props: { m: CommodityMonthly; title: string; parts: Parameters<typeof downloadMonthly>[3] }) {
  const { m } = props;
  return (
    <div class="lt-foot">
      <CsvAction sources={[m.s]} onClick={() => downloadMonthly(commodityMeta(m.id)?.name ?? m.id, props.title, m.s, props.parts)} title="Every month of this series, with its source and licence, as a CSV file" />
    </div>
  );
}

/** The block compares a year so far with the year before: it needs three months of that year to say anything. */
const MIN_MONTHS = 3;

function Disruption({ m }: { m: CommodityMonthly }) {
  const p = m.production;
  if (!p || !p.gulf || Number(p.to.slice(5)) < MIN_MONTHS) return null;
  const gulf = p.gulf.members.map((c) => p.rows.find((r) => r.c === c)).filter((r): r is MonthlyRow => !!r);
  const total: MonthlyRow = { ...p.gulf, name: 'Gulf total' };
  const world: MonthlyRow | null = p.world ? { ...p.world, name: 'World' } : null;
  const year = p.to.slice(0, 4);
  const base = p.baseYear ?? Number(year) - 1;
  const last36 = (r: MonthlyRow): MonthlyRow => ({ ...r, v: r.v.slice(-36) });
  return (
    <Section fold latest title={`Monthly production in ${year} against the ${base} average`} aside={<span class="year-tag">{monthName(p.to)}</span>}>
      <RangeTable
        rows={[...gulf, total].map(last36)}
        lead={world ? [last36(world)] : []}
        from={shift(p.from, (gulf[0]?.v.length ?? 36) - 36)}
        to={p.to}
        baseYear={base}
        u={p.u}
        label="kb/d"
      />
      <div class="muted small mo-note">
        Crude oil production of the Gulf producers and the world. Average of {base}: the twelve months of {base} weighted by their days, which is EIA's own annual figure. Lowest and latest: the lowest month of {year} so far and the latest month EIA gives. The Gulf total
        adds the seven producers month by month. Change = latest month against the {base} average. The 24-month line of each producer is in the table above.
      </div>
      <SourceLine s={m.s} y={`monthly, to ${monthName(p.to)}`} n="crude oil including lease condensate" />
    </Section>
  );
}

function Imports({ m }: { m: CommodityMonthly }) {
  const imp = m.imports;
  const [i, setI] = useState(0);
  if (!imp || !imp.importers.length) return null;
  const cur = imp.importers[Math.min(i, imp.importers.length - 1)];
  const year = cur.to.slice(0, 4);
  const base = Number(year) - 1;
  // origins with a month that EIA gives no figure for, in the year so far and in the baseline year
  const lateRows = cur.rows.filter((r) => r.miss);
  const lateMonths = lateRows.reduce((n, r) => n + (r.miss ?? 0), 0);
  const baseRows = cur.rows.filter((r) => r.nb != null);
  const baseMonths = baseRows.reduce((n, r) => n + 12 - (r.nb ?? 12), 0);
  const some = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  return (
    <Section fold latest title="OECD imports by origin" aside={<span class="year-tag">{monthName(cur.to)}</span>}>
      <div class="chips mo-chips" role="group" aria-label="Importer">
        {imp.importers.map((x, k) => (
          <button class="chip" key={x.id} aria-pressed={k === i} onClick={() => setI(k)}>
            {x.name}
          </button>
        ))}
      </div>
      <RangeTable rows={cur.rows} from={cur.from} to={cur.to} baseYear={base} u={imp.u} label={`${cur.name}, kb/d`} names={ORIGIN_NAME} latest={monthName(cur.to)} />
      <div class="muted small mo-note">
        Gross imports of petroleum and other liquids (crude oil and products together, not crude alone) from the origins that EIA gives month by month: its OPEC members and two groups, "Persian Gulf" and "OPEC". The Persian Gulf group
        includes Qatar, which is not in OPEC: the two groups overlap and are not additive. EIA gives no other origin. Origins that average under 1 kb/d in the months of {base} that have a figure are left out.
      </div>
      <div class="muted small mo-note">
        EIA leaves out a month for which it has no figure; its data and its documentation do not say that such a month had no imports (it publishes zeros elsewhere). The atlas shows "no figure", not a zero, no average for a year
        that lacks a month and no lowest month for an origin that lacks one.{' '}
        {lateRows.length
          ? `In ${year}, ${some(lateRows.length, 'origin lacks', 'origins lack')} at least one month (${some(lateMonths, 'month', 'months')} in all).`
          : `In ${year}, every origin of this table has a figure for each month.`}{' '}
        {baseRows.length ? `In ${base}, ${some(baseRows.length, 'origin lacks', 'origins lack')} at least one month (${some(baseMonths, 'month', 'months')} in all).` : `In ${base}, every origin has twelve months.`}
      </div>
      <MonthlyCsv m={m} title="OECD imports by origin" parts={imp.importers.map((x) => ({ group: x.name, u: imp.u, from: x.from, to: x.to, rows: x.rows, names: ORIGIN_NAME }))} />
      <SourceLine s={m.s} y={`monthly, to ${monthName(cur.to)}`} />
    </Section>
  );
}

function Stocks({ m }: { m: CommodityMonthly }) {
  const st = m.stocks;
  if (!st || !st.rows.length) return null;
  const year = Number(st.to.slice(0, 4));
  const dec = st.rows.find((r) => r.end)?.end?.m;
  return (
    <Section fold latest title="Petroleum stocks" aside={<span class="year-tag">{monthName(st.to)}</span>}>
      <div class="mo-table">
        <div class="mo-row mo-stock mo-head" aria-hidden="true">
          <span>Mbbl</span>
          <span>24 months</span>
          <span>Latest</span>
          <span>{dec ? `vs ${monthName(dec)}` : 'Change'}</span>
          <span>Days</span>
        </div>
        {st.rows.map((r) => {
          const chg = r.end ? (r.la.v / r.end.v - 1) * 100 : null;
          return (
            <div class="mo-row mo-stock" key={r.c}>
              <RowName r={r} />
              <TrendLine vals={r.v.slice(-24)} at={r.v.slice(-24).length - 1} w={44} title={trendTitle(r, st.from, 24, st.u)} />
              <Cell v={r.la.v} m={r.la.m} />
              <span class={`mo-pct${tone(chg)}`} title={r.ya ? `${monthName(r.ya.m)}: ${fmt(r.ya.v)} Mbbl` : undefined}>
                {signedPct(chg)}
              </span>
              <span class="mo-cell" title={r.cons != null ? `Stocks of ${monthName(r.la.m)} over oil demand of the same month, ${fmt(r.cons)} kb/d (EIA)` : undefined}>
                {r.cover != null ? Math.round(r.cover) : '—'}
              </span>
            </div>
          );
        })}
      </div>
      <div class="muted small mo-note">
        Stocks of crude oil and products together (EIA "petroleum and other liquids stocks"): EIA does not split them. Days = the stock of the month divided by the oil demand of the same month, both from
        EIA: arithmetic on two published figures, not an EIA figure. The change is against the end of {year - 1}.
        {st.withheld.length > 0 && ` EIA marks the monthly figures of ${st.withheld.length} other OECD countries as withheld (${st.withheld.slice(0, 6).map(countryName).join(', ')}${st.withheld.length > 6 ? ' and others' : ''}): the atlas shows none for them.`}
      </div>
      <MonthlyCsv m={m} title="Petroleum stocks" parts={[st]} />
      <SourceLine s={m.s} y={`monthly, to ${monthName(st.to)}`} />
    </Section>
  );
}

/** The monthly blocks of one commodity page: nothing for a commodity that has no monthly file. */
export function EnergyMonthly({ id }: { id: string }) {
  const m = useLoaded<CommodityMonthly>(() => (MONTHLY_PAGES.has(id) ? loadOptional<CommodityMonthly>(`commodities/monthly/${id}.json`) : Promise.resolve(null)), [id]);
  if (!m) return null;
  return (
    <>
      {m.production && (
        <Section fold latest title="Crude oil production by month" aside={<span class="year-tag">{monthName(m.production.to)}</span>}>
          <LatestTable block={m.production} rows={m.production.rows} lead={m.production.world ? [{ ...m.production.world, name: 'World' }] : []} label="kb/d" />
          <div class="muted small mo-note">
            Latest month of each producer against its {m.production.baseYear} average, from EIA's monthly series (crude oil including lease condensate). Click a producer to open its page.
          </div>
          <MonthlyCsv m={m} title="Crude oil production by month" parts={[{ ...m.production, rows: [...(m.production.world ? [{ ...m.production.world, name: 'World' }] : []), ...m.production.rows] }]} />
          <SourceLine s={m.s} y={`monthly, to ${monthName(m.production.to)}`} />
        </Section>
      )}
      <Disruption m={m} />
      <Imports m={m} />
      {m.ngl && (
        <Section fold latest title="Natural gas plant liquids by month" aside={<span class="year-tag">{monthName(m.ngl.to)}</span>}>
          <LatestTable block={m.ngl} rows={m.ngl.rows} lead={m.ngl.world ? [{ ...m.ngl.world, name: 'World' }] : []} label="kb/d" />
          <div class="muted small mo-note">
            Ethane, propane, butanes and heavier liquids recovered from natural gas: the monthly series nearest to LPG supply in the EIA data, not LPG alone.
          </div>
          <MonthlyCsv m={m} title="Natural gas plant liquids by month" parts={[{ ...m.ngl, rows: [...(m.ngl.world ? [{ ...m.ngl.world, name: 'World' }] : []), ...m.ngl.rows] }]} />
          <SourceLine s={m.s} y={`monthly, to ${monthName(m.ngl.to)}`} />
        </Section>
      )}
      {m.consumption && (
        <Section fold latest title="Oil demand by month" aside={<span class="year-tag">{monthName(m.consumption.to)}</span>}>
          <LatestTable block={m.consumption} rows={m.consumption.rows} label="kb/d" />
          <div class="muted small mo-note">
            Refined petroleum products consumption, the OECD and the countries for which EIA gives a monthly figure. Latest month against the {m.consumption.baseYear} average.
          </div>
          <MonthlyCsv m={m} title="Oil demand by month" parts={[m.consumption]} />
          <SourceLine s={m.s} y={`monthly, to ${monthName(m.consumption.to)}`} />
        </Section>
      )}
      <Stocks m={m} />
    </>
  );
}
