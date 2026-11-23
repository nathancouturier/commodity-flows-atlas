/** Blocks of the metals pages that read figures already in the commodity files: two USGS years side by side, customs value and unit value,
 *  concentration of each table, and what the USGS file states for the United States (audit M-017, M-018, A-013, A-014). */
import { useEffect, useMemo, useState } from 'preact/hooks';
import type { CommodityData, CommodityHistory, Concentration, HistTable, Ranked } from '../../types';
import { commodityMeta, countryName, isCountry } from '../../lib/data';
import { fmt, fmtEst, pct } from '../../lib/format';
import { select } from '../../lib/store';
import { Section, SourceLine, EstMark, FoldNote } from '../ui';
import '../../styles/metal-figures.css';

/** "554 bn", "845 M", "12.3 k": a customs value in USD to three significant digits (the column says USD). */
export function fmtUsd(v: number): string {
  const [x, w] = v >= 1e9 ? [v / 1e9, 'bn'] : v >= 1e6 ? [v / 1e6, 'M'] : [v / 1e3, 'k'];
  return `${Number(x.toPrecision(3)).toLocaleString('en-US')} ${w}`;
}

/** USD per tonne to three significant digits ("2,540"). */
export const fmtUv = (v: number) => Number(v.toPrecision(3)).toLocaleString('en-US');

/** A tab or row label from the title of an extra table: "Exports, not alloyed (HS 760110)" for "…exporters: not alloyed (HS 760110)", else its words up to the first dash or bracket. */
const shortTitle = (t: string) => {
  const m = t.match(/(exporters|importers)(?: —[^:]*)?: (.+)$/i);
  if (m) return `${/exporters/i.test(m[1]) ? 'Exports' : 'Imports'}, ${m[2]}`;
  return t.split(/ — | \(/)[0].replace(/ (exporters|importers)$/i, (x) => (/exporters/i.test(x) ? ' exports' : ' imports'));
};

/** A short row label for a table key: "Production", "Exporters", or the label of an extra table. */
function shortKey(d: CommodityData, key: string): string {
  const base: Record<string, string> = { production: 'Production', refinery: 'Refinery output', reserves: 'Reserves', exports: 'Exporters', imports: 'Importers' };
  const x = d.extra?.find((e) => e.key === key);
  return base[key] ?? (x ? shortTitle(x.title) : key);
}

const SIDE_WORD: Record<string, string> = { exports: 'Exporters', imports: 'Importers' };

/** The title of a table by its key: the page's own words for the main ones, the title of an extra table otherwise. */
function tableTitle(d: CommodityData, key: string): string {
  const x = d.extra?.find((e) => e.key === key);
  if (x) return x.title;
  const base: Record<string, string> = { production: 'Production', refinery: 'Refinery / smelter output', reserves: 'Reserves', exports: 'Exporters', imports: 'Importers' };
  const basis = (d as unknown as Record<string, Ranked | undefined>)[key]?.basis;
  return basis && key !== 'refinery' ? `${base[key] ?? key} — ${basis}` : (base[key] ?? key);
}

// ------------------------------------------------------------------ two USGS years side by side
function UsgsYears({ d, hist, color }: { d: CommodityData; hist: CommodityHistory; color?: string }) {
  const keys = Object.entries(hist.t).filter(([, h]) => h.s === 'usgs-mcs' && h.years.length === 2).map(([k]) => k);
  if (!keys.length) return null;
  return (
    <Section title="Two years of USGS figures">
      {keys.map((k) => (
        <YearsTable key={k} title={tableTitle(d, k)} h={hist.t[k]} color={color} />
      ))}
    </Section>
  );
}

function YearsTable({ title, h, color }: { title: string; h: HistTable; color?: string }) {
  const [all, setAll] = useState(false);
  const rows = useMemo(
    () => Object.entries(h.c).map(([c, v]) => ({ c, v })).sort((a, b) => (b.v[1] ?? b.v[0] ?? 0) - (a.v[1] ?? a.v[0] ?? 0)),
    [h],
  );
  const shown = all ? rows : rows.slice(0, 10);
  const est = (c: string, i: number) => !!h.srcEst?.[c]?.includes(i);
  const chg = (a: number | null, b: number | null) => (a && b ? `${b >= a ? '+' : '−'}${pct(Math.abs(b / a - 1))}` : '');
  const val = (v: number | null, c: string, i: number) =>
    v == null ? '—' : (
      <>
        {fmt(v)}
        {est(c, i) && <i class="mf-e" title="USGS marks this value as an estimate">e</i>}
      </>
    );
  return (
    <div class="mf-block" style={{ '--bar-color': color }}>
      <div class="mf-head">{title}</div>
      <div class="mf-row mf-years mf-th">
        <span />
        <span class="num" title={h.yl?.[0]}>{h.years[0]}</span>
        <span class="num" title={h.yl?.[1]}>{h.years[1]}</span>
        <span class="num">Change</span>
      </div>
      {shown.map(({ c, v }) => {
        const Row = isCountry(c) ? 'button' : 'div';
        return (
          <Row class="mf-row mf-years" key={c} onClick={Row === 'button' ? () => select({ kind: 'country', id: c }) : undefined}>
            <span class="mf-name">{countryName(c)}</span>
            <span class="num">{val(v[0], c, 0)}</span>
            <span class="num">{val(v[1], c, 1)}</span>
            <span class="num mf-chg">{chg(v[0], v[1])}</span>
          </Row>
        );
      })}
      {h.other && (h.other[0] != null || h.other[1] != null) && (
        <div class="mf-row mf-years mf-other">
          <span class="mf-name">Other countries (as published)</span>
          <span class="num">{fmt(h.other[0])}</span>
          <span class="num">{fmt(h.other[1])}</span>
          <span class="num mf-chg">{chg(h.other[0], h.other[1])}</span>
        </div>
      )}
      <div class="mf-row mf-years mf-other">
        <span class="mf-name">World (sum of lines)</span>
        <span class="num">{fmt(h.world[0])}</span>
        <span class="num">{fmt(h.world[1])}</span>
        <span class="num mf-chg">{chg(h.world[0], h.world[1])}</span>
      </div>
      {rows.length > 10 && (
        <button class="act-btn" style={{ alignSelf: 'flex-start' }} onClick={() => setAll(!all)} aria-expanded={all}>
          {all ? 'Show fewer' : `Show all (${rows.length})`}
        </button>
      )}
      <SourceLine s={h.s} y={`${h.years[0]} and ${h.years[1]}`} n={`${h.u} · ${h.years[0]}: ${h.yl?.[0] ?? ''}; ${h.years[1]}: ${h.yl?.[1] ?? ''}. "e": a value USGS marks as estimated`} />
    </div>
  );
}

// ------------------------------------------------------------------ customs value and unit value
type TradeTab = { key: string; title: string; u: string; rows: { c?: string; name: string; v: number; usd: number; uv?: number; est?: boolean; click?: () => void }[]; usd?: number; uv?: number };

function tradeTabs(d: CommodityData): TradeTab[] {
  const out: TradeTab[] = [];
  const add = (key: string, title: string, t?: Ranked) => {
    if (!t || !t.rows.some((r) => r.usd != null)) return;
    out.push({
      key, title, u: t.u, usd: t.usd, uv: t.uv,
      rows: t.rows.filter((r) => r.usd != null).map((r) => ({ c: r.c, name: r.name ?? countryName(r.c), v: r.v, usd: r.usd!, uv: r.uv, est: r.est, click: isCountry(r.c) ? () => select({ kind: 'country', id: r.c }) : undefined })),
    });
  };
  add('exports', SIDE_WORD.exports + (d.exports?.basis ? ` — ${d.exports.basis}` : ''), d.exports);
  add('imports', SIDE_WORD.imports + (d.imports?.basis ? ` — ${d.imports.basis}` : ''), d.imports);
  for (const x of d.extra ?? []) if (/(exports|imports)$/.test(x.key)) add(x.key, x.title, x.table);
  if (out.length && d.flows?.some((f) => f.usd != null))
    out.push({
      key: 'flows', title: 'Main flows', u: d.flows[0].u,
      rows: d.flows.filter((f) => f.usd != null).sort((a, b) => b.v - a.v).map((f) => ({ name: `${countryName(f.o)} → ${countryName(f.d)}`, v: f.v, usd: f.usd!, uv: f.uv, est: f.est })),
    });
  return out;
}

function TradeValue({ d, color }: { d: CommodityData; color?: string }) {
  const tabs = useMemo(() => tradeTabs(d), [d]);
  const [i, setI] = useState(0);
  const [byValue, setByValue] = useState(false);
  const [all, setAll] = useState(false);
  useEffect(() => {
    setI(0);
    setAll(false);
  }, [d.id]);
  if (!tabs.length) return null;
  const tab = tabs[Math.min(i, tabs.length - 1)];
  const rows = byValue ? [...tab.rows].sort((a, b) => b.usd - a.usd) : tab.rows;
  const shown = all ? rows : rows.slice(0, 10);
  const anyHidden = tab.rows.some((r) => r.uv == null);
  return (
    <Section title="Value and unit value">
      <div class="mf-tabs" role="tablist">
        {tabs.map((t, k) => (
          <button class={`mf-tab${k === i ? ' on' : ''}`} role="tab" aria-selected={k === i} key={t.key} onClick={() => { setI(k); setAll(false); }}>
            {t.key === 'flows' ? 'Flows' : t.key === 'exports' ? 'Exports' : t.key === 'imports' ? 'Imports' : shortTitle(t.title)}
          </button>
        ))}
      </div>
      <div class="mf-head">
        {tab.title}
        <button class="mf-sort" onClick={() => setByValue(!byValue)} title="Change the order of the rows">
          {byValue ? 'Ordered by value' : 'Ordered by tonnes'}
        </button>
      </div>
      <div class="mf-row mf-trade mf-th">
        <span />
        <span class="num">{tab.u}</span>
        <span class="num">Value, USD</span>
        <span class="num">USD/t</span>
      </div>
      {shown.map((r, k) => {
        const Row = r.click ? 'button' : 'div';
        return (
          <Row class="mf-row mf-trade" key={`${r.name}-${k}`} onClick={r.click}>
            <span class="mf-name">
              {r.name}
              {r.est && <EstMark />}
            </span>
            <span class="num">{fmtEst(r.v, r.est)}</span>
            <span class="num">{fmtUsd(r.usd)}</span>
            <span class="num" title={r.uv == null ? 'No unit value: most of this tonnage was computed by the atlas from the declared value' : undefined}>
              {r.uv != null ? fmtUv(r.uv) : '—'}
            </span>
          </Row>
        );
      })}
      {tab.usd != null && (
        <div class="mf-row mf-trade mf-other">
          <span class="mf-name">World, all countries</span>
          <span />
          <span class="num">{fmtUsd(tab.usd)}</span>
          <span class="num">{tab.uv != null ? fmtUv(tab.uv) : '—'}</span>
        </div>
      )}
      {rows.length > 10 && (
        <button class="act-btn" style={{ alignSelf: 'flex-start' }} onClick={() => setAll(!all)} aria-expanded={all}>
          {all ? 'Show fewer' : `Show all (${rows.length})`}
        </button>
      )}
      <SourceLine
        s="baci"
        y={d.exports?.y ?? d.flows?.[0]?.y}
        n="value is the declared customs value in USD; unit value is value divided by tonnes (gross weight)"
      />
      {anyHidden && (
        <FoldNote
          class="src-line"
          style={{ marginTop: '2px' }}
          text="Unit values of estimated rows are not shown: for these flows the tonnage was computed from the declared value, so the quotient would only return the reference price of the estimate (a row with 10% or more of estimated tonnage counts as estimated)."
        />
      )}
    </Section>
  );
}

// ------------------------------------------------------------------ concentration
function ConcentrationBlock({ d }: { d: CommodityData }) {
  const c = d.concentration;
  if (!c) return null;
  const keys = Object.keys(c);
  if (!keys.length) return null;
  const hhi = (x: Concentration) => `${x.cov < 0.995 ? '≥ ' : ''}${x.hhi.toLocaleString('en-US')}`;
  return (
    <Section title="Concentration">
      <div class="mf-row mf-conc mf-th">
        <span />
        <span class="num">First</span>
        <span class="num">Top 3</span>
        <span class="num" title="Herfindahl index">Index</span>
      </div>
      {keys.map((k) => {
        const x = c[k];
        return (
          <div class="mf-row mf-conc" key={k}>
            <span class="mf-name" title={tableTitle(d, k)}>
              {shortKey(d, k)}
              {x.est && <EstMark />}
            </span>
            <span class="num" title={`${countryName(x.top1.c)}, ${pct(x.top1.p)} of the table`}>
              {countryName(x.top1.c)} {pct(x.top1.p)}
            </span>
            <span class="num">{pct(x.top3)}</span>
            <span class="num" title={x.eq ? `As if ${fmt(x.eq)} countries of the same size shared the total` : undefined}>
              {hhi(x)}
            </span>
          </div>
        );
      })}
      <FoldNote
        class="src-line"
        style={{ marginTop: '2px' }}
        text={
          'First: the largest country and its share; Top 3: the share of the three largest. Index: the Herfindahl index, the sum of the squares of the countries\' shares in percent. ' +
          'It runs from near 0 (very many countries of equal size) to 10,000 (one country holds everything); 2,500 reads as four equal countries. ' +
          'Shares are of the world total of each table, computed on the countries it lists. Where a source\'s "Other countries" line is large the countries cover less than the whole and the index is a lower bound ("≥"). Arithmetic on the figures of the tables above; an estimate in a table is marked.'
        }
      />
    </Section>
  );
}

// ------------------------------------------------------------------ the United States, as USGS states it
function UnitedStates({ d }: { d: CommodityData }) {
  const u = d.us;
  if (!u || (!u.consumption?.length && !u.reliance?.length)) return null;
  return (
    <Section title="United States, as USGS states it">
      {u.consumption?.map((c) => (
        <div class="mf-us" key={c.label}>
          <div class="mf-us-k">{c.label}</div>
          <div class="mf-us-v num">
            {c.vals.map((v) => (
              <span key={v.y}>
                {v.y}: {fmt(v.v)} {c.u}
                {v.est && <i class="mf-e" title="USGS marks this value as an estimate">e</i>}
              </span>
            ))}
          </div>
          {c.n && <FoldNote class="mf-us-n" text={c.n} />}
        </div>
      ))}
      {u.reliance?.map((r) => (
        <div class="mf-us" key={r.what}>
          <div class="mf-us-k">Net import reliance, {r.what}</div>
          <div class="mf-us-v num">
            <span>
              {r.y}: {/^\d/.test(r.pct) ? `${r.pct}%` : `${r.pct.replace(/^([<>])/, '$1 ')}%`}
              <i class="mf-e" title="USGS estimate for the year">e</i>
            </span>
          </div>
          {r.src && <div class="mf-us-n">Main import sources, 2021 to 2024: {r.src}</div>}
        </div>
      ))}
      <SourceLine s={u.s} y="2024 and 2025" n="published figures, as the Mineral Commodity Summaries state them (apparent consumption: its own definition, given under each figure)" />
    </Section>
  );
}

export function MetalFigures({ id, d, hist, color }: { id: string; d: CommodityData; hist?: CommodityHistory | null; color?: string }) {
  const metal = commodityMeta(id)?.family === 'metals';
  return (
    <>
      {hist && <UsgsYears d={d} hist={hist} color={color} />}
      {metal && <TradeValue d={d} color={color} />}
      <ConcentrationBlock d={d} />
      {metal && <UnitedStates d={d} />}
    </>
  );
}
