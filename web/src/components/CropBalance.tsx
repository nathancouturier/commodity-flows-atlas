/**
 * Balance of a USDA PSD crop: the estimate year and the forecast year side by side (data/commodities/<id>.json, `balance`).
 * Every line is a USDA figure; a line marked "computed" (yield, world excluding China, stocks-to-use) is arithmetic on two USDA
 * figures of the same year, not an Atlas estimate.
 */
import type { CropBalance, CropBalanceRow } from '../types';
import { fmt } from '../lib/format';
import { year } from '../lib/store';
import { Section, SourceLine } from './ui';
import '../styles/crop-balance.css';

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

/** "2026-11" as "November 2026". */
export function reportMonth(rel?: string): string | null {
  const m = /^(\d{4})-(\d{2})$/.exec(rel ?? '');
  return m ? `${MONTHS[Number(m[2]) - 1]} ${m[1]}` : null;
}

/** A line's value: a ratio keeps one decimal and the percent sign. */
const val = (r: CropBalanceRow, v: number) => (r.u === '%' ? `${v.toFixed(1)}%` : fmt(v));

/** The change from the first year to the second: points for a ratio, a percentage otherwise. */
function change(r: CropBalanceRow): { text: string; dir: number } {
  const [a, b] = r.v;
  if (r.u === '%') {
    const d = b - a;
    return { text: Math.abs(d) < 0.05 ? '0 pts' : `${d > 0 ? '+' : '−'}${Math.abs(d).toFixed(1)} pts`, dir: Math.sign(d) };
  }
  if (!a) return { text: '', dir: 0 };
  const p = ((b - a) / a) * 100;
  return { text: Math.abs(p) < 0.05 ? '0%' : `${p > 0 ? '+' : '−'}${Math.abs(p).toFixed(1)}%`, dir: Math.sign(p) };
}

export default function CropBalanceSection({ bal, color }: { bal: CropBalance; color?: string }) {
  if (!bal || bal.years.length < 2 || !bal.rows.length) return null;
  const [a, b] = bal.years;
  const head = (y: CropBalance['years'][number]) => (
    <span class="cb-col" title={reportMonth(y.rel) ? `USDA report of ${reportMonth(y.rel)}` : undefined}>
      <b class="num">{y.y}</b>
      {y.yk && <span>{y.yk}</span>}
    </span>
  );
  const computed = bal.rows.some((r) => r.s === 'atlas');
  // the unit of the production line is the unit of the table: only the lines in another unit say theirs
  const main = bal.rows.find((r) => r.k === 'production')?.u;
  return (
    <Section title="Balance" aside={<span class="year-tag">{year.value != null ? 'latest: ' : ''}{a.y} {a.yk} and {b.y} {b.yk}</span>}>
      <div class="cb" style={{ '--bar-color': color }}>
        <div class="cb-row cb-head">
          <span />
          {head(a)}
          {head(b)}
          <span class="cb-col">change</span>
        </div>
        {bal.rows.map((r) => {
          const c = change(r);
          return (
            <div class={`cb-row${r.sub ? ' cb-sub' : ''}${r.s === 'atlas' ? ' cb-calc' : ''}`} key={r.k} title={r.n}>
              <span class="cb-label">
                {r.label}
                {r.u !== '%' && r.u !== main && <span class="cb-tag">{r.u}</span>}
              </span>
              <span class="num">{val(r, r.v[0])}</span>
              <span class="num">{val(r, r.v[1])}</span>
              <span class={`num cb-chg${c.dir > 0 ? ' up' : c.dir < 0 ? ' down' : ''}`}>{c.text}</span>
            </div>
          );
        })}
      </div>
      <SourceLine
        s={bal.s}
        y={`${a.y} ${a.yk ?? ''}, USDA report of ${reportMonth(a.rel) ?? a.rel}; ${b.y} ${b.yk ?? ''}, USDA report of ${reportMonth(b.rel) ?? b.rel}`}
        n={`${main ? `${main} unless stated; ` : ''}${bal.n}${computed ? '. Lines in italics are arithmetic on two USDA figures of the same year, not Atlas estimates; the others are USDA figures as published' : ''}`}
      />
    </Section>
  );
}
