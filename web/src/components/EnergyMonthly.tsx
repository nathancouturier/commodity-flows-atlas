/**
 * Monthly blocks of the energy pages (EIA International, monthly series; data/commodities/monthly/<id>.json, loaded on demand):
 * crude oil production by month with the latest month against the average of the year before, the disruption of the latest year for
 * the Gulf producers and the world, OECD imports by origin and petroleum stocks; the same stocks and the monthly oil demand on the
 * refined products page; natural gas plant liquids on the LPG page. Every figure is a published monthly figure or arithmetic on two of
 * them (the average of a year, a change in per cent, a stock over a demand), and names its month.
 */
import { useState } from 'preact/hooks';
import type { CommodityMonthly, MonthlyBlock, MonthlyRow } from '../types';
import { countryName, isCountry, loadOptional } from '../lib/data';
import { fmt } from '../lib/format';
import { select } from '../lib/store';
import { Section, SourceLine, TrendLine } from './ui';
import { useLoaded } from './views/shared';
import '../styles/energy-monthly.css';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
/** "2026-07" -> "Jul 2026" */
export const monthName = (m: string) => `${MONTHS[Number(m.slice(5)) - 1]} ${m.slice(0, 4)}`;
/** "−16.4%" / "+2.1%": a change with its sign. */
export const signedPct = (p: number | null | undefined) => (p == null ? '—' : `${p > 0 ? '+' : p < 0 ? '−' : ''}${Math.abs(p).toFixed(1)}%`);
const tone = (p: number | null | undefined) => (p == null || p === 0 ? '' : p < 0 ? ' mo-down' : ' mo-up');
const rowName = (r: MonthlyRow, names?: Record<string, string>) => r.name ?? names?.[r.o ?? ''] ?? (r.c ? countryName(r.c) : (r.o ?? ''));

/** The commodity pages that have a monthly file. */
const MONTHLY_PAGES = new Set(['crude-oil', 'refined-products', 'lpg', 'lng']);
const ORIGIN_NAME: Record<string, string> = { PERG: 'Persian Gulf', OPEC: 'OPEC', OPAF: 'OPEC Africa', OPSA: 'OPEC South America' };

/** A figure with its month under it. */
function Cell(props: { v: number | null | undefined; m?: string; strong?: boolean }) {
  return (
    <span class={`mo-cell${props.strong ? ' mo-strong' : ''}`}>
      {props.v == null ? '—' : fmt(props.v)}
      {props.m && <small>{monthName(props.m)}</small>}
    </span>
  );
}

function RowName(props: { r: MonthlyRow; names?: Record<string, string> }) {
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

/** Average of the baseline year, lowest month and latest month of the year of the latest month, each with its month. */
function RangeTable(props: { rows: MonthlyRow[]; from: string; to: string; baseYear: number; u: string; label: string; names?: Record<string, string>; lead?: MonthlyRow[] }) {
  const year = props.to.slice(0, 4);
  const line = (r: MonthlyRow, extra = '') => (
    <div class={`mo-row mo-range${extra}`} key={`${r.c ?? ''}${r.o ?? ''}${r.name ?? ''}`}>
      <RowName r={r} names={props.names} />
      <Cell v={r.b} />
      <Cell v={r.lo.v} m={r.lo.m} />
      <Cell v={r.la.v} m={r.la.m} strong />
      <span class={`mo-pct${tone(r.p)}`}>{signedPct(r.p)}</span>
    </div>
  );
  return (
    <div class="mo-table">
      <div class="mo-row mo-range mo-head" aria-hidden="true">
        <span>{props.label}</span>
        <span>{props.baseYear} avg</span>
        <span>Lowest {year}</span>
        <span>Latest</span>
        <span>Change</span>
      </div>
      {props.rows.map((r) => line(r))}
      {props.lead?.map((r) => line(r, ' mo-lead'))}
    </div>
  );
}

function Disruption({ m }: { m: CommodityMonthly }) {
  const p = m.production;
  if (!p || !p.gulf) return null;
  const gulf = p.gulf.members.map((c) => p.rows.find((r) => r.c === c)).filter((r): r is MonthlyRow => !!r);
  const total: MonthlyRow = { ...p.gulf, name: 'Gulf total' };
  const world: MonthlyRow | null = p.world ? { ...p.world, name: 'World' } : null;
  const year = p.to.slice(0, 4);
  const base = p.baseYear ?? Number(year) - 1;
  const last36 = (r: MonthlyRow): MonthlyRow => ({ ...r, v: r.v.slice(-36) });
  return (
    <Section title={`${year} disruption, crude oil production`} aside={<span class="year-tag">{monthName(p.to)}</span>}>
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
        Average of {base}: the twelve months of {base} weighted by their days, which is EIA's own annual figure. Lowest and latest: the lowest month of {year} so far and the latest month of the file. The Gulf total
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
  return (
    <Section title="OECD imports from OPEC, by origin" aside={<span class="year-tag">{monthName(cur.to)}</span>}>
      <div class="chips mo-chips" role="group" aria-label="Importer">
        {imp.importers.map((x, k) => (
          <button class="chip" key={x.id} aria-pressed={k === i} onClick={() => setI(k)}>
            {x.name}
          </button>
        ))}
      </div>
      <RangeTable rows={cur.rows} from={cur.from} to={cur.to} baseYear={Number(year) - 1} u={imp.u} label={`${cur.name}, kb/d`} names={ORIGIN_NAME} />
      <div class="muted small mo-note">
        Gross imports of petroleum and other liquids (crude oil and products together, not crude alone) from the OPEC origins that EIA gives month by month: the file has no other origin. "Persian Gulf" and "OPEC" are EIA's own groups. Origins with
        an average under 1 kb/d in {Number(year) - 1} are left out.
      </div>
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
    <Section title="Petroleum stocks" aside={<span class="year-tag">{monthName(st.to)}</span>}>
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
        Stocks of crude oil and products together (EIA "petroleum and other liquids stocks"): the file does not split them. Days = the stock of the month divided by the oil demand of the same month, both from
        the EIA file: arithmetic on two published figures, not an EIA figure. The change is against the end of {year - 1}.
        {st.withheld.length > 0 && ` EIA marks the monthly figures of ${st.withheld.length} other OECD countries as withheld (${st.withheld.slice(0, 6).map(countryName).join(', ')}${st.withheld.length > 6 ? ' and others' : ''}): the atlas shows none for them.`}
      </div>
      <SourceLine s={m.s} y={`monthly, to ${monthName(st.to)}`} />
    </Section>
  );
}

function Gaps({ m }: { m: CommodityMonthly }) {
  if (!m.gaps?.length) return null;
  return (
    <Section title="Monthly data">
      {m.gaps.map((g) => (
        <div class="muted small mo-note" key={g}>
          {g}
        </div>
      ))}
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
        <Section title="Crude oil production by month" aside={<span class="year-tag">{monthName(m.production.to)}</span>}>
          <LatestTable block={m.production} rows={m.production.rows} lead={m.production.world ? [{ ...m.production.world, name: 'World' }] : []} label="kb/d" />
          <div class="muted small mo-note">
            Latest month of each producer against its {m.production.baseYear} average, from EIA's monthly series (crude oil including lease condensate). Click a producer to open its page.
          </div>
          <SourceLine s={m.s} y={`monthly, to ${monthName(m.production.to)}`} />
        </Section>
      )}
      <Disruption m={m} />
      <Imports m={m} />
      {m.ngl && (
        <Section title="Natural gas plant liquids by month" aside={<span class="year-tag">{monthName(m.ngl.to)}</span>}>
          <LatestTable block={m.ngl} rows={m.ngl.rows} lead={m.ngl.world ? [{ ...m.ngl.world, name: 'World' }] : []} label="kb/d" />
          <div class="muted small mo-note">
            Ethane, propane, butanes and heavier liquids recovered from natural gas: the monthly series nearest to LPG supply in the EIA file, not LPG alone.
          </div>
          <SourceLine s={m.s} y={`monthly, to ${monthName(m.ngl.to)}`} />
        </Section>
      )}
      {m.consumption && (
        <Section title="Oil demand by month" aside={<span class="year-tag">{monthName(m.consumption.to)}</span>}>
          <LatestTable block={m.consumption} rows={m.consumption.rows} label="kb/d" />
          <div class="muted small mo-note">
            Refined petroleum products consumption, the OECD and the countries for which EIA gives a monthly figure. Latest month against the {m.consumption.baseYear} average.
          </div>
          <SourceLine s={m.s} y={`monthly, to ${monthName(m.consumption.to)}`} />
        </Section>
      )}
      <Stocks m={m} />
      <Gaps m={m} />
    </>
  );
}
